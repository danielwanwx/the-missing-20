"""Focused contracts for the API-backed Missing 20 experiment session."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event, Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from scripts.decision_workspace_server import DecisionWorkspaceServer
from the_missing_20.adapters.local_knowledge import LocalKnowledgeRepository
from the_missing_20.adapters.strands_models import ScriptedStrandsFactory
from the_missing_20.agents.events import (
    AgentEventSink,
    AgentOperationEvent,
    AgentOperationEventType,
)
from the_missing_20.agents.harness import AgentHarness
from the_missing_20.agents.schemas import (
    REQUIRED_AUTHORITATIVE_SOURCES,
    SourceAvailability,
    SourceAvailabilitySet,
)
from the_missing_20.agents.validation import AgentStageFailure
from the_missing_20.authority_b.quorum import QuorumDenied
from the_missing_20.domain.enterprise import EvidenceReadStatus
from the_missing_20.experiment.events import PublicEventType, PublicIncidentEvent
from the_missing_20.experiment.ledger import EventLedgerError, PublicEventLedger
from the_missing_20.experiment.session import ExperimentSession

ROOT = Path(__file__).resolve().parents[2]


def _session(tmp_path: Path) -> ExperimentSession:
    return ExperimentSession(ROOT, data_directory=tmp_path / "session")


def _harness(session: ExperimentSession, sink: AgentEventSink) -> AgentHarness:
    return AgentHarness(
        model_factory=ScriptedStrandsFactory(),
        knowledge=LocalKnowledgeRepository(ROOT / "fixtures/knowledge"),
        source_availability=SourceAvailabilitySet(
            sources=tuple(
                SourceAvailability(source_type=source, status=EvidenceReadStatus.AVAILABLE)
                for source in REQUIRED_AUTHORITATIVE_SOURCES
            )
        ),
        event_sink=sink,
    )


class _BlockingOperationObserver:
    """Hold the first tool invocation to prove the event precedes run completion."""

    def __init__(self) -> None:
        self.events: list[AgentOperationEvent] = []
        self.tool_started = Event()
        self.release = Event()

    def emit(self, event: AgentOperationEvent) -> None:
        self.events.append(event)
        if event.event_type is AgentOperationEventType.TOOL_STARTED:
            self.tool_started.set()
            assert self.release.wait(timeout=5)


class _FailingOperationObserver:
    """Fail at the actual tool boundary; later stages must never be entered."""

    def __init__(self) -> None:
        self.events: list[AgentOperationEvent] = []

    def emit(self, event: AgentOperationEvent) -> None:
        self.events.append(event)
        if event.event_type is AgentOperationEventType.TOOL_STARTED:
            raise RuntimeError("observer failure")


def test_experiment_starts_with_exact_stable_unit_split(tmp_path: Path) -> None:
    session = _session(tmp_path)
    snapshot = session.snapshot()

    assert snapshot["unit_counts"] == {"total": 100, "erp_recorded": 80, "queue_failed": 20}
    units = snapshot["units"]
    assert len(units) == 100
    assert [item["unit_id"] for item in units] == [
        f"PO-10001-10-unit-{index:03d}" for index in range(1, 101)
    ]
    assert {item["status"] for item in units[:80]} == {"ERP_RECORDED"}
    assert {item["status"] for item in units[80:]} == {"QUEUE_FAILED"}
    assert {item["source_message_id"] for item in units[80:]} == {"RECEIPT-MESSAGE-020"}
    assert all(item["source_message_id"] is None for item in units[:80])


def test_session_publishes_ordered_real_harness_events(tmp_path: Path) -> None:
    session = _session(tmp_path)
    assert [item.event_type for item in session.events_since()] == [
        PublicEventType.INCIDENT_DETECTED
    ]
    run = session.run_investigation()
    assert run is not None
    events = session.events_since()

    assert [item.sequence for item in events] == list(range(1, len(events) + 1))
    types = {item.event_type for item in events}
    assert {
        PublicEventType.INCIDENT_DETECTED,
        PublicEventType.INVESTIGATION_STARTED,
        PublicEventType.AGENT_STARTED,
        PublicEventType.TOOL_STARTED,
        PublicEventType.TOOL_COMPLETED,
        PublicEventType.EVIDENCE_RETURNED,
        PublicEventType.AGENT_COMPLETED,
        PublicEventType.AGENT_HANDOFF,
        PublicEventType.SYNTHESIS_COMPLETED,
        PublicEventType.EVALUATION_COMPLETED,
    } <= types
    detected = next(item for item in events if item.event_type is PublicEventType.INCIDENT_DETECTED)
    raw_failed_unit_ids = detected.payload["failed_unit_ids"]
    assert isinstance(raw_failed_unit_ids, list)
    assert all(isinstance(item, str) for item in raw_failed_unit_ids)
    failed_unit_ids = set(raw_failed_unit_ids)
    assert len(failed_unit_ids) == 20
    assert all(
        item["unit_id"] in failed_unit_ids
        for item in session.snapshot()["units"]
        if item["status"] == "QUEUE_FAILED"
    )
    assert all("excerpt" not in item.model_dump_json() for item in events)
    assert session.snapshot()["advisory"]["status"] == "COMPLETE"


def test_actual_operation_event_is_visible_before_harness_completion(tmp_path: Path) -> None:
    session = _session(tmp_path)
    observer = _BlockingOperationObserver()
    harness = _harness(session, observer)
    evidence = tuple(session.store.list_evidence(session.case_id))
    result: list[object] = []

    worker = Thread(
        target=lambda: result.append(
            harness.run(case_id=session.case_id, trace_id=session.trace_id, evidence=evidence)
        ),
        daemon=True,
    )
    worker.start()
    assert observer.tool_started.wait(timeout=5)
    assert worker.is_alive()
    observer.release.set()
    worker.join(timeout=10)

    assert not worker.is_alive()
    assert len(result) == 1
    assert observer.events[0].event_type is AgentOperationEventType.AGENT_STARTED
    assert any(
        event.event_type is AgentOperationEventType.TOOL_COMPLETED for event in observer.events
    )


def test_actual_tool_observer_failure_stops_before_synthesis(tmp_path: Path) -> None:
    session = _session(tmp_path)
    observer = _FailingOperationObserver()
    harness = _harness(session, observer)
    evidence = tuple(session.store.list_evidence(session.case_id))

    with pytest.raises(AgentStageFailure):
        harness.run(case_id=session.case_id, trace_id=session.trace_id, evidence=evidence)

    event_types = {event.event_type for event in observer.events}
    assert AgentOperationEventType.TOOL_STARTED in event_types
    assert AgentOperationEventType.SYNTHESIS_STARTED not in event_types
    assert AgentOperationEventType.EVALUATION_STARTED not in event_types


def test_chat_is_grounded_read_only_and_durable_projection_survives_reload(
    tmp_path: Path,
) -> None:
    session = _session(tmp_path)
    before = session.enterprise.read_snapshot()
    response = session.chat_command(
        "Where did the missing units go?",
        idempotency_key="chat:where:1",
    )
    after = session.enterprise.read_snapshot()

    assert response["read_only"] is True
    assert response["citations"]
    assert before == after
    assert session.snapshot()["projection_sequence"] > 2

    reloaded = ExperimentSession(ROOT, data_directory=tmp_path / "session")
    restored = reloaded.snapshot()
    assert restored["projection_sequence"] == session.snapshot()["projection_sequence"]
    # The run is represented by durable operation/evaluation events, so a fresh
    # process can truthfully expose completion even though it has no in-memory
    # HarnessRun object to reconstruct private model details from.
    assert restored["advisory"]["status"] == "COMPLETE"
    assert reloaded.investigation_is_available() is True


def test_chat_authority_prose_runs_agents_but_cannot_approve_or_execute(
    tmp_path: Path,
) -> None:
    session = _session(tmp_path)
    before = session.enterprise.read_snapshot()
    response = session.chat_command(
        "Please approve and execute the action now.",
        idempotency_key="chat:authority-boundary:1",
    )
    after = session.enterprise.read_snapshot()

    assert response["read_only"] is True
    assert response["intent"] == "explain_authority_boundary"
    assert before == after
    event_types = {event.event_type for event in session.events_since()}
    assert PublicEventType.AGENT_STARTED in event_types
    assert PublicEventType.TOOL_STARTED in event_types
    assert PublicEventType.EVIDENCE_RETURNED in event_types
    assert PublicEventType.APPROVAL_RECORDED not in event_types
    assert PublicEventType.EXECUTION_STARTED not in event_types


def test_command_key_reuse_is_rejected_after_cached_chat_response(tmp_path: Path) -> None:
    session = _session(tmp_path)
    session.chat_command("Where did the missing units go?", idempotency_key="chat:reuse:1")

    with pytest.raises(EventLedgerError, match="different command envelope"):
        session.chat_command("Approve and execute it.", idempotency_key="chat:reuse:1")


def test_two_role_quorum_is_required_and_recovery_is_exactly_once(tmp_path: Path) -> None:
    session = _session(tmp_path)
    prepared = session.decision_command(
        {
            "command": "prepare_recovery",
            "tool": "restart_receipt_message",
            "idempotency_key": "decision:prepare:1",
        }
    )
    intent_id = prepared["approval"]["intent_id"]

    with pytest.raises(QuorumDenied, match="exact two-role quorum"):
        session.decision_command(
            {
                "command": "execute",
                "intent_id": intent_id,
                "idempotency_key": "decision:execute:before-quorum",
            }
        )
    pending = session.decision_command(
        {
            "command": "approve",
            "intent_id": intent_id,
            "principal_id": "integration-operator",
            "idempotency_key": "decision:approval:operator",
        }
    )
    assert pending["approval"]["status"] == "QUORUM_PENDING"
    assert pending["execution"]["effects"] == []

    granted = session.decision_command(
        {
            "command": "approve",
            "intent_id": intent_id,
            "principal_id": "ap-approver",
            "idempotency_key": "decision:approval:ap",
        }
    )
    assert granted["approval"]["status"] == "GRANTED"
    completed = session.decision_command(
        {
            "command": "execute",
            "intent_id": intent_id,
            "idempotency_key": "decision:execute:1",
        }
    )
    assert completed["unit_counts"] == {"total": 100, "erp_recorded": 100, "queue_failed": 0}
    assert completed["execution"]["verified"] is True
    assert len(completed["execution"]["effects"]) == 1
    assert completed["execution"]["replay_effect_delta"] == 0

    replay = session.decision_command(
        {
            "command": "execute",
            "intent_id": intent_id,
            "idempotency_key": "decision:execute:replay",
        }
    )
    assert replay["execution"]["effects"] == completed["execution"]["effects"]
    assert len(session.enterprise.read_snapshot().business_effects) == 1


def test_event_ledger_rejects_idempotency_reuse_and_gaps(tmp_path: Path) -> None:
    ledger = PublicEventLedger(tmp_path / "events.sqlite")
    assert (
        ledger.register_command(
            incident_id="incident-1",
            idempotency_key="command-1",
            command_kind="chat",
            identity={"trace_id": "trace-1"},
            payload={"question": "hello"},
        )
        is False
    )
    assert (
        ledger.register_command(
            incident_id="incident-1",
            idempotency_key="command-1",
            command_kind="chat",
            identity={"trace_id": "trace-1"},
            payload={"question": "hello"},
        )
        is True
    )
    with pytest.raises(EventLedgerError, match="different command envelope"):
        ledger.register_command(
            incident_id="incident-1",
            idempotency_key="command-1",
            command_kind="chat",
            identity={"trace_id": "trace-1"},
            payload={"question": "approve"},
        )
    first = ledger.append(
        incident_id="incident-1",
        trace_id="trace-1",
        case_version=0,
        event_type=PublicEventType.INCIDENT_DETECTED,
        actor="detector",
        status="DETECTED",
        correlation_id="case-1",
        idempotency_key="event-1",
        payload={"missing": 20},
    )
    assert (
        ledger.append(
            incident_id="incident-1",
            trace_id="trace-1",
            case_version=0,
            event_type=PublicEventType.INCIDENT_DETECTED,
            actor="detector",
            status="DETECTED",
            correlation_id="case-1",
            idempotency_key="event-1",
            payload={"missing": 20},
        )
        == first
    )
    with pytest.raises(EventLedgerError, match="reused"):
        ledger.append(
            incident_id="incident-1",
            trace_id="trace-1",
            case_version=0,
            event_type=PublicEventType.INCIDENT_DETECTED,
            actor="detector",
            status="DETECTED",
            correlation_id="case-1",
            idempotency_key="event-1",
            payload={"missing": 19},
        )
    # The public validator is intentionally fail-closed if a caller feeds it an
    # event sequence with a missing middle record.
    second = first.model_copy(update={"sequence": 3, "event_id": "event:incident-1:000003"})
    with pytest.raises(EventLedgerError, match="gap"):
        PublicEventLedger.validate((first, second))
    identity_mismatch = first.model_copy(update={"event_id": "event:incident-1:999999"})
    with pytest.raises(EventLedgerError, match="identity"):
        PublicEventLedger.validate((identity_mismatch,))


def test_event_ledger_assigns_unique_contiguous_sequences_concurrently(tmp_path: Path) -> None:
    ledger = PublicEventLedger(tmp_path / "events.sqlite")

    def append(index: int) -> PublicIncidentEvent:
        return ledger.append(
            incident_id="incident-concurrent",
            trace_id="trace-concurrent",
            case_version=0,
            event_type=PublicEventType.AGENT_STARTED,
            actor=f"agent-{index}",
            status="RUNNING",
            correlation_id=f"run-{index}",
            idempotency_key=f"agent-{index}",
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        created = tuple(pool.map(append, range(20)))
    assert sorted(item.sequence for item in created) == list(range(1, 21))
    assert [item.sequence for item in ledger.all_events("incident-concurrent")] == list(
        range(1, 21)
    )


def test_local_api_binds_snapshot_chat_decisions_and_sse(tmp_path: Path) -> None:
    try:
        server = DecisionWorkspaceServer(
            ("127.0.0.1", 0), ROOT, runtime_directory=tmp_path / "runtime"
        )
    except PermissionError:
        pytest.skip("the managed test sandbox disallows loopback sockets")
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"

    def request(
        path: str,
        *,
        method: str = "GET",
        payload: object | None = None,
        content_type: str | None = "application/json",
        origin: str | None = None,
    ) -> tuple[int, bytes]:
        body = None if payload is None else json.dumps(payload).encode()
        headers: dict[str, str] = {}
        if body is not None and content_type is not None:
            headers["Content-Type"] = content_type
        if origin is not None:
            headers["Origin"] = origin
        request_value = Request(
            base + path,
            method=method,
            data=body,
            headers=headers,
        )
        try:
            with urlopen(request_value, timeout=5) as response:
                return response.status, response.read()
        except HTTPError as exc:
            return exc.code, exc.read()

    try:
        status, body = request("/api/v1/incidents")
        assert status == 200
        listing = json.loads(body)
        incident_id = listing["incidents"][0]["incident_id"]
        assert listing["incidents"][0]["unit_counts"] == {
            "total": 100,
            "erp_recorded": 80,
            "queue_failed": 20,
        }

        status, body = request(f"/api/v1/incidents/{incident_id}/units")
        assert status == 200
        assert len(json.loads(body)["units"]) == 100

        status, body = request(f"/api/v1/incidents/{incident_id}/start", method="POST", payload={})
        assert status == 200
        assert json.loads(body)["command"] == "investigation_started"

        status, body = request(
            f"/api/v1/incidents/{incident_id}/chat",
            method="POST",
            payload={"question": "Where did the missing units go?", "idempotency_key": "chat-1"},
        )
        assert status == 200
        assert json.loads(body)["read_only"] is True

        # The local boundary is intentionally strict: browser commands need JSON,
        # same-origin (or absent) Origin, and an SSE cursor that already exists.
        status, body = request(
            f"/api/v1/incidents/{incident_id}/chat",
            method="POST",
            payload={"question": "hello", "idempotency_key": "chat-no-content-type"},
            content_type="",
        )
        assert status == 415
        assert json.loads(body)["error"]["code"] == "json_required"
        status, body = request(
            f"/api/v1/incidents/{incident_id}/chat",
            method="POST",
            payload={"question": "hello", "idempotency_key": "chat-cross-origin"},
            content_type="application/json",
            origin="http://evil.invalid",
        )
        assert status == 403
        assert json.loads(body)["error"]["code"] == "origin_not_allowed"
        latest = json.loads(request(f"/api/v1/incidents/{incident_id}")[1])["projection_sequence"]
        status, body = request(f"/api/v1/incidents/{incident_id}/events?after={latest + 1}")
        assert status == 400
        assert json.loads(body)["error"]["code"] == "future_cursor"

        stream_request = Request(f"{base}/api/v1/incidents/{incident_id}/events?after=0")
        stream = urlopen(stream_request, timeout=5)
        try:
            status = stream.status
            body = stream.read(256)
        finally:
            stream.close()
        # This endpoint intentionally keeps the connection open briefly for live
        # delivery; the test only needs to assert its first SSE frame.
        assert status == 200
        assert body.startswith(b"id: 1\nevent: incident.detected")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
