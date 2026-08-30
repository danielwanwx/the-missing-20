"""Focused contracts for the API-backed Missing 20 experiment session."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event, Thread
from time import monotonic
from typing import Any, cast
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from scripts.decision_workspace_server import DecisionWorkspaceServer
from the_missing_20.adapters.local_knowledge import LocalKnowledgeRepository
from the_missing_20.adapters.strands_models import (
    AgentCoreRuntimeConfig,
    AgentCoreRuntimeFactory,
    AgentCoreRuntimeModel,
    ScriptedStrandsFactory,
)
from the_missing_20.adapters.synthetic_enterprise import SyntheticEnterprise
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
from the_missing_20.application.executor import SimulatedPersistenceFault
from the_missing_20.authority_b.classifier import latest_authoritative_evidence
from the_missing_20.authority_b.executor import AuthorityBControlledExecutor
from the_missing_20.authority_b.quorum import QuorumDenied
from the_missing_20.domain.enterprise import EvidenceReadStatus
from the_missing_20.domain.models import EvidenceSourceType
from the_missing_20.experiment.events import PublicEventType, PublicIncidentEvent
from the_missing_20.experiment.ledger import EventLedgerError, PublicEventLedger
from the_missing_20.experiment.session import (
    ExperimentRegistry,
    ExperimentSession,
    _SessionAgentEventSink,
)
from the_missing_20.ports.enterprise_systems import EnterprisePreconditionFailed

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


def test_agentcore_completion_events_persist_redacted_provider_attribution(
    tmp_path: Path,
) -> None:
    """A returned runtime response, not config, supplies durable attribution."""

    factory = AgentCoreRuntimeFactory(
        config=AgentCoreRuntimeConfig(
            runtime_arn="arn:aws:bedrock-agentcore:us-west-2:123456789012:runtime/fake"
        )
    )
    session = ExperimentSession(ROOT, data_directory=tmp_path / "agentcore", model_factory=factory)
    sink = _SessionAgentEventSink(session)
    completion_stages = (
        (AgentOperationEventType.AGENT_COMPLETED, "investigator"),
        (AgentOperationEventType.SYNTHESIS_COMPLETED, "synthesis"),
        (AgentOperationEventType.EVALUATION_COMPLETED, "evaluation"),
    )
    for index, (event_type, stage) in enumerate(completion_stages, start=1):
        provider_metadata = {
            "mode": "agentcore",
            "provider": "agentcore",
            "model": "agentcore-runtime",
            "transport": "agentcore_invoke_agent_runtime",
            "region": "us-west-2",
            "runtime_configured": True,
            "qualifier": "DEFAULT",
            "invocation_id": f"runtime-session-{index}",
            "invocation_proof": "returned",
            "status": "COMPLETE",
            "invocation_status": "COMPLETED",
        }
        sink.emit(
            AgentOperationEvent(
                event_type=event_type,
                case_id=session.case_id,
                trace_id=session.trace_id,
                actor="agentcore-advisor",
                operation_id=f"agentcore-operation-{index}",
                status=(
                    "ACCEPT"
                    if event_type is AgentOperationEventType.EVALUATION_COMPLETED
                    else "COMPLETED"
                ),
                correlation_id=session.trace_id,
                stage=stage,
                payload={"provider_metadata": provider_metadata},
            )
        )

    completion_events = [
        event
        for event in session.events_since()
        if event.event_type
        in {
            PublicEventType.AGENT_COMPLETED,
            PublicEventType.SYNTHESIS_COMPLETED,
            PublicEventType.EVALUATION_COMPLETED,
        }
    ]
    assert len(completion_events) == len(completion_stages)
    required = {
        "provider",
        "model",
        "mode",
        "transport",
        "region",
        "runtime_configured",
        "qualifier",
        "read_only",
        "authority",
        "invocation_id",
        "invocation_proof",
    }
    for event in completion_events:
        metadata = cast(dict[str, Any], event.payload["provider_metadata"])
        assert required.issubset(metadata)
        assert metadata["provider"] == "agentcore"
        assert metadata["model"] == "agentcore-runtime"
        assert metadata["mode"] == "agentcore"
        assert metadata["transport"] == "agentcore_invoke_agent_runtime"
        assert metadata["region"] == "us-west-2"
        assert metadata["runtime_configured"] is True
        assert metadata["read_only"] is True
        assert metadata["authority"] == "ADVISORY_NOT_OPERATIONAL_DECISION"
        assert "runtime_arn" not in metadata
        assert "123456789012" not in json.dumps(metadata)

    # The durable fallback uses the persisted evaluation completion rather than
    # dropping back to a mode-only summary.
    snapshot = session.snapshot()
    assert snapshot["advisory"]["provider_metadata"]["provider"] == "agentcore"
    assert snapshot["advisory"]["provider_metadata"]["transport"] == (
        "agentcore_invoke_agent_runtime"
    )


def test_provider_truth_reports_observed_real_provider_without_invoking_it(
    tmp_path: Path,
) -> None:
    """Health can distinguish configured AgentCore from an observed call."""

    registry = ExperimentRegistry(
        ROOT,
        data_directory=tmp_path / "registry",
        provider_mode="agentcore",
    )
    assert registry.provider_truth() == {
        "mode": "agentcore",
        "configured": True,
        "calls_observed": False,
    }
    session = registry.get("missing-20-normal")
    _SessionAgentEventSink(session).emit(
        AgentOperationEvent(
            event_type=AgentOperationEventType.AGENT_COMPLETED,
            case_id=session.case_id,
            trace_id=session.trace_id,
            actor="agentcore-advisor",
            operation_id="agentcore-health-operation",
            status="COMPLETED",
            correlation_id=session.trace_id,
            stage="investigator",
        )
    )
    # A lifecycle marker alone cannot prove that a provider returned anything.
    assert registry.provider_truth()["calls_observed"] is False
    _SessionAgentEventSink(session).emit(
        AgentOperationEvent(
            event_type=AgentOperationEventType.AGENT_COMPLETED,
            case_id=session.case_id,
            trace_id=session.trace_id,
            actor="agentcore-advisor",
            operation_id="agentcore-health-returned",
            status="COMPLETED",
            correlation_id=session.trace_id,
            stage="investigator",
            payload={
                "provider_metadata": {
                    "mode": "agentcore",
                    "provider": "agentcore",
                    "model": "agentcore-runtime",
                    "transport": "agentcore_invoke_agent_runtime",
                    "invocation_id": "runtime-session-health",
                    "invocation_proof": "returned",
                    "status": "COMPLETE",
                    "invocation_status": "COMPLETED",
                }
            },
        )
    )
    assert registry.provider_truth()["calls_observed"] is True
    registry.close()


def test_provider_truth_ignores_returned_but_invalid_completion(
    tmp_path: Path,
) -> None:
    """Returned proof is not a completed call after durable validation failure."""

    registry = ExperimentRegistry(
        ROOT,
        data_directory=tmp_path / "registry-invalid-return",
        provider_mode="agentcore",
    )
    session = registry.get("missing-20-normal")
    _SessionAgentEventSink(session).emit(
        AgentOperationEvent(
            event_type=AgentOperationEventType.SYNTHESIS_COMPLETED,
            case_id=session.case_id,
            trace_id=session.trace_id,
            actor="agentcore-advisor",
            operation_id="agentcore-invalid-return",
            status="FAILED",
            correlation_id=session.trace_id,
            stage="synthesis",
            payload={
                "provider_metadata": {
                    "mode": "agentcore",
                    "provider": "agentcore",
                    "model": "agentcore-runtime",
                    "transport": "agentcore_invoke_agent_runtime",
                    "invocation_id": "runtime-session-invalid",
                    "invocation_proof": "returned",
                    "status": "DEGRADED",
                    "invocation_status": "FAILED",
                }
            },
        )
    )

    assert registry.provider_truth()["calls_observed"] is False
    registry.close()


def test_precompletion_failure_does_not_infer_provider_attribution(
    tmp_path: Path,
) -> None:
    """A failed completion retains failure context but no fabricated call proof."""

    registry = ExperimentRegistry(
        ROOT,
        data_directory=tmp_path / "registry-failure",
        provider_mode="agentcore",
    )
    session = registry.get("missing-20-normal")
    _SessionAgentEventSink(session).emit(
        AgentOperationEvent(
            event_type=AgentOperationEventType.SYNTHESIS_COMPLETED,
            case_id=session.case_id,
            trace_id=session.trace_id,
            actor="agentcore-advisor",
            operation_id="agentcore-precompletion-failure",
            status="FAILED",
            correlation_id=session.trace_id,
            stage="synthesis",
            payload={"error_code": "AgentProviderUnavailable"},
        )
    )
    event = next(
        event
        for event in session.events_since()
        if event.event_type is PublicEventType.SYNTHESIS_COMPLETED
    )
    metadata = cast(dict[str, Any], event.payload["provider_metadata"])
    assert metadata["status"] == "DEGRADED"
    assert metadata["invocation_status"] == "FAILED"
    assert "provider" not in metadata
    assert "transport" not in metadata
    assert "invocation_id" not in metadata
    assert registry.provider_truth()["calls_observed"] is False
    registry.close()


def test_normal_flow_telemetry_is_ordered_and_snapshot_derived(tmp_path: Path) -> None:
    """Normal Operations receives durable observations without changing business state."""

    session = ExperimentSession(
        ROOT,
        data_directory=tmp_path / "normal",
        incident_id="missing-20-normal",
        fixture_path=ROOT / "fixtures/scenarios/healthy-flow.json",
        telemetry_enabled=True,
    )
    session.stop_telemetry()
    initial = session.snapshot()
    assert initial["operational_state"] == "NORMAL"
    assert initial["health"] == "HEALTHY"
    assert initial["incident"]["status"] == "NORMAL"
    assert initial["incident"]["health"] == "HEALTHY"
    assert not any(
        event.event_type is PublicEventType.INCIDENT_DETECTED
        for event in session.events_since()
    )
    first = initial["telemetry"]["latest"]
    assert first is not None
    assert first["source_stage"] == "WAREHOUSE_TO_ERP"
    assert first["throughput_window"] == 60
    assert first["queue_depth"] == 0
    assert first["unit_counts"] == initial["unit_counts"]
    assert first["throughput_units"] == len(first["observed_unit_ids"])
    assert 0 < first["throughput_units"] < initial["unit_counts"]["total"]
    known_unit_ids = {item["unit_id"] for item in initial["units"]}
    assert set(first["observed_unit_ids"]).issubset(known_unit_ids)

    event = session.publish_telemetry()
    assert event is not None
    after = session.snapshot()
    latest = after["telemetry"]["latest"]
    assert latest is not None
    assert latest["sequence"] == event.sequence
    assert latest["observed_at"] == event.occurred_at.isoformat()
    assert latest["observation_id"].endswith("telemetry:000002")
    assert latest["unit_counts"] == after["unit_counts"]
    assert latest["throughput_units"] == len(latest["observed_unit_ids"])
    assert event.sequence == initial["projection_sequence"] + 1
    assert latest["observed_at"] > first["observed_at"]


def test_registry_normal_stream_advances_without_client_timer(tmp_path: Path) -> None:
    """The normal scenario producer advances the same cursor consumed by SSE."""

    from the_missing_20.experiment.session import ExperimentRegistry

    registry = ExperimentRegistry(ROOT, data_directory=tmp_path / "registry")
    session = registry.get("missing-20-normal")
    try:
        baseline = session.snapshot()
        # The demo producer intentionally uses a human-readable cadence; allow
        # one complete interval plus scheduler jitter instead of racing it.
        events = session.wait_for_events(baseline["projection_sequence"], timeout=5.5)
        telemetry = tuple(
            event for event in events if event.event_type is PublicEventType.TELEMETRY_OBSERVED
        )
        assert telemetry
        current = session.snapshot()
        assert current["projection_sequence"] > baseline["projection_sequence"]
        assert current["telemetry"]["latest"]["sequence"] == current["projection_sequence"]
        assert (
            current["telemetry"]["latest"]["observed_at"]
            > baseline["telemetry"]["latest"]["observed_at"]
        )
        assert current["unit_counts"] == {"total": 100, "erp_recorded": 100, "queue_failed": 0}
    finally:
        session.stop_telemetry()


def test_persisted_normal_telemetry_index_continues_after_restart(tmp_path: Path) -> None:
    """A reopened ledger continues observation IDs without rescanning on every tick."""

    data_directory = tmp_path / "normal-restart"
    first = ExperimentSession(
        ROOT,
        data_directory=data_directory,
        incident_id="missing-20-normal",
        fixture_path=ROOT / "fixtures/scenarios/healthy-flow.json",
        telemetry_enabled=True,
    )
    first.stop_telemetry()
    first_event = first.publish_telemetry()
    assert first_event is not None
    assert first_event.payload["observation_index"] == 2

    second = ExperimentSession(
        ROOT,
        data_directory=data_directory,
        incident_id="missing-20-normal",
        fixture_path=ROOT / "fixtures/scenarios/healthy-flow.json",
        telemetry_enabled=True,
    )
    try:
        latest = second.snapshot()["telemetry"]["latest"]
        assert latest is not None
        assert latest["observation_index"] == 3
        assert latest["observation_id"].endswith("telemetry:000003")
        resumed_event = second.publish_telemetry()
        assert resumed_event is not None
        assert resumed_event.payload["observation_index"] == 4
    finally:
        second.stop_telemetry()


def test_registry_close_stops_normal_telemetry_producer(tmp_path: Path) -> None:
    """Registry shutdown joins the producer instead of relying on daemon exit."""

    from the_missing_20.experiment.session import ExperimentRegistry

    registry = ExperimentRegistry(ROOT, data_directory=tmp_path / "registry-close")
    session = registry.get("missing-20-normal")
    producer = session._telemetry_thread
    assert producer is not None
    assert producer.is_alive()

    registry.close()

    assert session._telemetry_thread is None
    assert not producer.is_alive()


def test_scenario_lab_source_event_precedes_authoritative_detection(tmp_path: Path) -> None:
    """The Scenario Lab changes the source before the detector creates a case."""

    from the_missing_20.experiment.session import ExperimentRegistry

    registry = ExperimentRegistry(ROOT, data_directory=tmp_path / "scenario-lab")
    try:
        session = registry.fresh_injected_incident()
        events = session.events_since()
        assert [event.event_type for event in events[:2]] == [
            PublicEventType.SOURCE_CONDITION_INJECTED,
            PublicEventType.INCIDENT_DETECTED,
        ]
        source = events[0]
        detected = events[1]
        assert source.payload["condition"] == "retryable_document_lock"
        assert source.payload["observed_unit_ids"]
        assert detected.payload["failed_unit_ids"] == source.payload["observed_unit_ids"]
    finally:
        registry.close()


def test_scenario_lab_starts_healthy_and_commits_exact_source_transition(
    tmp_path: Path,
) -> None:
    """The source transaction is the only path from healthy flow to detection."""

    from the_missing_20.experiment.session import ExperimentRegistry

    registry = ExperimentRegistry(ROOT, data_directory=tmp_path / "source-transition")
    try:
        session = registry.fresh_incident(defer_detection=True)
        before = session.snapshot()
        assert before["unit_counts"] == {"total": 100, "erp_recorded": 100, "queue_failed": 0}
        assert before["incident"]["status"] == "NORMAL"
        assert before["execution"]["effects"] == []
        assert before["events"] == []
        assert before["telemetry"]["status"] == "WAITING"

        source_event = session.inject_source_condition()
        after = session.snapshot()
        events = session.events_since()
        assert [item.event_type for item in events[:2]] == [
            PublicEventType.SOURCE_CONDITION_INJECTED,
            PublicEventType.INCIDENT_DETECTED,
        ]
        assert after["unit_counts"] == {"total": 100, "erp_recorded": 80, "queue_failed": 20}
        assert source_event.payload["transaction_status"] == "COMMITTED"
        assert source_event.payload["pre_state"]["unit_counts"] == {
            "total": 100,
            "erp_recorded": 100,
            "queue_failed": 0,
        }
        assert source_event.payload["post_state"]["unit_counts"] == after["unit_counts"]
        assert source_event.payload["post_state"]["failed_message"]["status"] == "FAILED"
        assert source_event.payload["post_state"]["erp_receipt"]["quantity"] == 80
        assert source_event.payload["post_state"]["invoice"]["state"] == "HELD"
        assert source_event.payload["post_state"]["failed_unit_ids"] == (
            events[1].payload["failed_unit_ids"]
        )
    finally:
        registry.close()


def test_incident_telemetry_captures_healthy_to_fault_transition(tmp_path: Path) -> None:
    """Telemetry proves the source change without using a client-side tick."""

    session = ExperimentSession(
        ROOT,
        data_directory=tmp_path / "incident-telemetry",
        incident_id="missing-20-telemetry-incident",
        fixture_path=ROOT / "fixtures/scenarios/healthy-flow.json",
        telemetry_enabled=True,
        defer_detection=True,
    )
    session.stop_telemetry()
    try:
        baseline = session.snapshot()
        baseline_point = baseline["telemetry"]["latest"]
        assert baseline_point is not None
        assert baseline_point["unit_counts"] == {
            "total": 100,
            "erp_recorded": 100,
            "queue_failed": 0,
        }

        source_event = session.inject_source_condition()
        after = session.snapshot()
        telemetry_points = after["telemetry"]["history"]
        assert len(telemetry_points) >= 2
        assert telemetry_points[0]["unit_counts"] == {
            "total": 100,
            "erp_recorded": 100,
            "queue_failed": 0,
        }
        assert telemetry_points[-1]["unit_counts"] == {
            "total": 100,
            "erp_recorded": 80,
            "queue_failed": 20,
        }

        events = session.events_since()
        detected_event = next(
            event for event in events if event.event_type is PublicEventType.INCIDENT_DETECTED
        )
        fault_point = telemetry_points[-1]
        assert baseline_point["sequence"] < source_event.sequence < detected_event.sequence
        assert detected_event.sequence < fault_point["sequence"]
    finally:
        session.stop_telemetry()


def test_source_transition_outbox_recovers_after_ledger_append_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A source commit is recoverable when public publication fails afterward."""

    from the_missing_20.experiment.session import ExperimentRegistry

    registry = ExperimentRegistry(ROOT, data_directory=tmp_path / "source-outbox")
    try:
        session = registry.fresh_incident(defer_detection=True)
        original_append = session.ledger.append

        def fail_source_publication(*args: Any, **kwargs: Any) -> Any:
            event_type = kwargs.get("event_type")
            if event_type is None and args:
                # PublicEventLedger.append is keyword-only today; retain this
                # guard so the fault remains scoped if its adapter signature is
                # relaxed later.
                event_type = args[0]
            if event_type is PublicEventType.SOURCE_CONDITION_INJECTED:
                raise RuntimeError("public ledger unavailable")
            return original_append(*args, **kwargs)

        monkeypatch.setattr(session.ledger, "append", fail_source_publication)
        with pytest.raises(RuntimeError, match="public ledger unavailable"):
            session.inject_source_condition()

        # The enterprise mutation and its complete envelope commit together,
        # while no public event is visible yet.
        assert session.events_since() == ()
        assert session.enterprise.read_snapshot().erp_receipt.quantity == 80
        outbox = session.enterprise.read_source_condition_outbox()
        assert outbox is not None
        assert outbox.pre_state.erp_receipt.quantity == 100
        assert outbox.post_state.erp_receipt.quantity == 80

        monkeypatch.undo()
        recovered_source = session.inject_source_condition()
        events = session.events_since()
        assert [event.sequence for event in events[:2]] == [1, 2]
        assert [event.event_type for event in events[:2]] == [
            PublicEventType.SOURCE_CONDITION_INJECTED,
            PublicEventType.INCIDENT_DETECTED,
        ]
        assert recovered_source.payload["post_state"] == session.events_since()[0].payload[
            "post_state"
        ]
        assert session.inject_source_condition() == recovered_source
        assert len(
            [
                event
                for event in session.events_since()
                if event.event_type is PublicEventType.SOURCE_CONDITION_INJECTED
            ]
        ) == 1

        # A new registry instance recovers the same durable envelope rather than
        # allocating a second mutation or publishing a different source state.
        reopened = ExperimentRegistry(ROOT, data_directory=tmp_path / "source-outbox")
        try:
            resumed = reopened.get(session.incident_id)
            resumed_events = resumed.events_since()
            assert [event.sequence for event in resumed_events[:2]] == [1, 2]
            assert resumed_events[0].payload == recovered_source.payload
            assert resumed.enterprise.read_snapshot().erp_receipt.quantity == 80
        finally:
            reopened.close()
    finally:
        registry.close()


def test_source_event_reopen_completes_detection_in_timestamp_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A crash after source publication cannot timestamp detection before it."""

    from the_missing_20.experiment.session import ExperimentRegistry

    registry = ExperimentRegistry(ROOT, data_directory=tmp_path / "source-reopen-order")
    try:
        session = registry.fresh_incident(defer_detection=True)
        # Simulate the narrow crash window after the durable source event but
        # before the detector can publish its fresh read.
        monkeypatch.setattr(session, "_ensure_detection", lambda **_: None)
        source_event = session.inject_source_condition()
        assert session.events_since() == (source_event,)
    finally:
        registry.close()

    reopened = ExperimentRegistry(ROOT, data_directory=tmp_path / "source-reopen-order")
    try:
        events = reopened.get(session.incident_id).events_since()
        lifecycle_events = tuple(
            event for event in events if event.event_type is not PublicEventType.TELEMETRY_OBSERVED
        )
        assert [event.event_type for event in lifecycle_events[:2]] == [
            PublicEventType.SOURCE_CONDITION_INJECTED,
            PublicEventType.INCIDENT_DETECTED,
        ]
        assert lifecycle_events[1].occurred_at > lifecycle_events[0].occurred_at
        assert lifecycle_events[2].event_type is PublicEventType.INVESTIGATION_STARTED
        assert lifecycle_events[2].occurred_at > lifecycle_events[1].occurred_at
    finally:
        reopened.close()


def test_detection_handoff_is_exactly_once_across_duplicate_and_reopen(
    tmp_path: Path,
) -> None:
    """A repeated source command or persisted reopen cannot launch a second run."""

    from the_missing_20.experiment.session import ExperimentRegistry

    data_directory = tmp_path / "auto-handoff"
    registry = ExperimentRegistry(ROOT, data_directory=data_directory)
    try:
        session = registry.select_incident()
        incident_id = session.incident_id
        first_source = session.inject_source_condition()
        assert first_source.event_type is PublicEventType.SOURCE_CONDITION_INJECTED
        assert session.inject_source_condition() == first_source
        deadline = monotonic() + 10
        while monotonic() < deadline and not any(
            event.event_type is PublicEventType.EVALUATION_COMPLETED
            for event in session.events_since()
        ):
            session.wait_for_events(session.ledger.latest_sequence(incident_id), timeout=0.25)
        first_events = session.events_since()
        assert sum(
            event.event_type is PublicEventType.INVESTIGATION_STARTED
            for event in first_events
        ) == 1
    finally:
        registry.close()

    reopened_registry = ExperimentRegistry(ROOT, data_directory=data_directory)
    try:
        reopened = reopened_registry.get(incident_id)
        reopened_events = reopened.events_since()
        assert sum(
            event.event_type is PublicEventType.INVESTIGATION_STARTED
            for event in reopened_events
        ) == 1
        assert sum(
            event.event_type is PublicEventType.SOURCE_CONDITION_INJECTED
            for event in reopened_events
        ) == 1
        assert any(
            event.event_type is PublicEventType.EVALUATION_COMPLETED
            for event in reopened_events
        )
    finally:
        reopened_registry.close()


def test_detection_event_recovers_after_case_store_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A crash after atomic detection state cannot strand the public event stream."""

    from the_missing_20.experiment.session import ExperimentRegistry

    data_directory = tmp_path / "detection-publication-recovery"
    registry = ExperimentRegistry(ROOT, data_directory=data_directory)
    session = registry.fresh_incident(defer_detection=True)
    incident_id = session.incident_id
    original_append = session.ledger.append
    failed = False

    def fail_detection_append(**kwargs: object) -> object:
        nonlocal failed
        if kwargs.get("event_type") is PublicEventType.INCIDENT_DETECTED and not failed:
            failed = True
            raise EventLedgerError("simulated detection publication failure")
        return original_append(**kwargs)

    monkeypatch.setattr(session.ledger, "append", fail_detection_append)
    with pytest.raises(EventLedgerError, match="simulated detection publication failure"):
        session.inject_source_condition()

    assert [item.event_type for item in session.events_since()] == [
        PublicEventType.SOURCE_CONDITION_INJECTED
    ]
    assert session.store.get_case(session.case_id).case_version == 1
    assert session.store.list_evidence(session.case_id)
    registry.close()

    reopened = ExperimentRegistry(ROOT, data_directory=data_directory)
    try:
        recovered = reopened.get(incident_id)
        events = recovered.events_since()
        assert [item.event_type for item in events[:2]] == [
            PublicEventType.SOURCE_CONDITION_INJECTED,
            PublicEventType.INCIDENT_DETECTED,
        ]
        assert recovered.store.get_case(recovered.case_id).case_version == 1
        assert recovered.snapshot()["unit_counts"] == {
            "total": 100,
            "erp_recorded": 80,
            "queue_failed": 20,
        }
    finally:
        reopened.close()


def test_source_transition_fails_closed_on_stale_or_unexpected_preconditions(
    tmp_path: Path,
) -> None:
    """A second or differently targeted injection cannot partially mutate source state."""

    enterprise = SyntheticEnterprise.seed_from_fixture(
        tmp_path / "enterprise.sqlite",
        ROOT / "fixtures/scenarios/healthy-flow.json",
    )
    first = enterprise.inject_retryable_document_lock()
    assert first.pre_state.erp_receipt.quantity == 100
    assert first.post_state.erp_receipt.quantity == 80
    with pytest.raises(EnterprisePreconditionFailed):
        enterprise.inject_retryable_document_lock()
    with pytest.raises(EnterprisePreconditionFailed):
        enterprise.inject_retryable_document_lock(quantity=19)
    current = enterprise.read_snapshot()
    assert current.erp_receipt.quantity == 80
    assert current.failed_message.status.value == "FAILED"
    assert sum(item.status.value == "QUEUE_FAILED" for item in current.supply_units) == 20


def test_normal_telemetry_uses_unique_flow_record_ids(tmp_path: Path) -> None:
    """Observed records are distinct event records, not recycled inventory IDs."""

    session = ExperimentSession(
        ROOT,
        data_directory=tmp_path / "normal-unique-records",
        incident_id="missing-20-normal",
        fixture_path=ROOT / "fixtures/scenarios/healthy-flow.json",
        telemetry_enabled=True,
    )
    try:
        session.stop_telemetry()
        first = session.snapshot()["telemetry"]["latest"]
        second_event = session.publish_telemetry()
        assert first is not None
        assert second_event is not None
        second = second_event.payload
        assert first["batch_id"] != second["batch_id"]
        assert set(first["batch_record_ids"]).isdisjoint(second["batch_record_ids"])
        assert first["observed_record_count"] == len(first["batch_record_ids"])
        assert second["observed_record_count"] == len(second["batch_record_ids"])
        assert first["observed_unit_ids"] != second["batch_record_ids"]
    finally:
        session.stop_telemetry()


def test_telemetry_occurred_at_uses_capture_clock_not_event_tick(tmp_path: Path) -> None:
    """Telemetry timestamps represent capture cadence while ledger order stays intact."""

    from datetime import UTC, datetime, timedelta

    capture_times = iter(
        (
            datetime(2026, 8, 28, 12, 0, 10, tzinfo=UTC),
            datetime(2026, 8, 28, 12, 0, 16, tzinfo=UTC),
        )
    )
    session = ExperimentSession(
        ROOT,
        data_directory=tmp_path / "telemetry-capture-clock",
        incident_id="missing-20-normal",
        fixture_path=ROOT / "fixtures/scenarios/healthy-flow.json",
        telemetry_enabled=True,
        telemetry_clock=lambda: next(capture_times),
    )
    try:
        session.stop_telemetry()
        first = session.snapshot()["telemetry"]["latest"]
        second_event = session.publish_telemetry()
        assert first is not None
        assert second_event is not None
        assert first["observed_at"] == "2026-08-28T12:00:10+00:00"
        assert second_event.occurred_at.isoformat() == "2026-08-28T12:00:16+00:00"
        assert (
            second_event.occurred_at
            - datetime.fromisoformat(first["observed_at"])
            == timedelta(seconds=6)
        )
        assert second_event.sequence == first["sequence"] + 1
        assert first["observation_id"] != second_event.payload["observation_id"]
    finally:
        session.stop_telemetry()


def test_ledger_tail_ends_at_latest_sequence_beyond_replay_limit(tmp_path: Path) -> None:
    """Tail restoration must not return the stale first ten thousand events."""

    from datetime import UTC, datetime, timedelta

    ledger = PublicEventLedger(tmp_path / "tail.sqlite")
    base = datetime(2026, 8, 28, tzinfo=UTC)
    for sequence in range(1, 10_006):
        ledger.append(
            incident_id="tail-test",
            trace_id="trace:tail-test",
            case_version=0,
            event_type=PublicEventType.TELEMETRY_OBSERVED,
            actor="synthetic-enterprise-source",
            status="OBSERVED",
            correlation_id="trace:tail-test",
            idempotency_key=f"tail:{sequence}",
            occurred_at=base + timedelta(seconds=sequence),
            payload={"observation_index": sequence},
        )
    tail = ledger.tail_events("tail-test", limit=2)
    assert [event.sequence for event in tail] == [10_004, 10_005]
    assert [event.payload["observation_index"] for event in tail] == [10_004, 10_005]


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


def test_chat_exact_retry_after_reload_preserves_intent(tmp_path: Path) -> None:
    session = _session(tmp_path)
    first = session.chat_command(
        "Why did the queue stop the units?",
        idempotency_key="chat:durable-intent:1",
    )

    reloaded = ExperimentSession(ROOT, data_directory=tmp_path / "session")
    retried = reloaded.chat_command(
        "Why did the queue stop the units?",
        idempotency_key="chat:durable-intent:1",
    )

    assert retried["intent"] == first["intent"] == "explain_hypothesis"
    assert retried["message"] == first["message"]
    assert retried["citations"] == first["citations"]
    assert retried["read_only"] is True


@pytest.mark.parametrize(
    "failure_flag",
    ("fail_after_reservation", "fail_after_enterprise_commit"),
)
def test_execute_exact_retry_resumes_after_crash_without_duplicate_effect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_flag: str,
) -> None:
    session = _session(tmp_path)
    prepared = session.decision_command(
        {
            "command": "prepare_recovery",
            "tool": "restart_receipt_message",
            "idempotency_key": f"decision:crash:{failure_flag}:prepare",
        }
    )
    intent_id = prepared["approval"]["intent_id"]
    for principal, key in (
        ("integration-operator", f"decision:crash:{failure_flag}:operator"),
        ("ap-approver", f"decision:crash:{failure_flag}:ap"),
    ):
        session.decision_command(
            {
                "command": "approve",
                "intent_id": intent_id,
                "principal_id": principal,
                "idempotency_key": key,
            }
        )

    original_execute = AuthorityBControlledExecutor.execute
    calls = 0

    def fail_once(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        if calls == 1:
            kwargs[failure_flag] = True
        return original_execute(*args, **kwargs)

    monkeypatch.setattr(AuthorityBControlledExecutor, "execute", fail_once)
    execute_key = f"decision:crash:{failure_flag}:execute"
    with pytest.raises(SimulatedPersistenceFault):
        session.decision_command(
            {
                "command": "execute",
                "intent_id": intent_id,
                "idempotency_key": execute_key,
            }
        )

    started = [
        item
        for item in session.events_since()
        if item.event_type is PublicEventType.EXECUTION_STARTED
    ]
    assert len(started) == 1
    # The marker was written before Authority-B preparation advanced the case;
    # this is the prior event whose exact version must be reused on retry.
    assert started[0].case_version == prepared["case_version"]

    retried = session.decision_command(
        {
            "command": "execute",
            "intent_id": intent_id,
            "idempotency_key": execute_key,
        }
    )

    # The retry performs one recovery call and one deterministic replay proof;
    # only the first invocation is fault-injected.
    assert calls == 3
    assert retried["execution"]["verified"] is True
    assert retried["execution"]["replay_effect_delta"] == 0
    assert len(retried["execution"]["effects"]) == 1
    assert len(session.enterprise.read_snapshot().business_effects) == 1
    assert (
        len(
            [
                item
                for item in session.events_since()
                if item.event_type is PublicEventType.EXECUTION_STARTED
            ]
        )
        == 1
    )


def test_snapshot_connection_is_a_point_in_time_read(tmp_path: Path) -> None:
    session = _session(tmp_path)
    assert session.snapshot()["connection"] == {
        "status": "SNAPSHOT",
        "source": "SYNTHETIC_EXPERIMENT",
    }


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


def test_chat_prepare_language_never_creates_a_recovery_intent(tmp_path: Path) -> None:
    session = _session(tmp_path)
    before = session.enterprise.read_snapshot()
    before_case = session.store.get_case(session.case_id)
    before_case_bytes = (tmp_path / "session" / "case.sqlite").read_bytes()
    quorum_path = tmp_path / "session" / "quorum-ledger.json"
    before_quorum_bytes = quorum_path.read_bytes() if quorum_path.exists() else None
    first_operation_count = len(
        [item for item in session.events_since() if item.event_type is PublicEventType.TOOL_STARTED]
    )

    response = session.chat_command(
        "Please prepare and recover the units.",
        idempotency_key="chat:read-only-prepare:1",
    )

    assert response["read_only"] is True
    assert response["intent"] == "explain_authority_boundary"
    assert before == session.enterprise.read_snapshot()
    assert before_case == session.store.get_case(session.case_id)
    assert before_case_bytes == (tmp_path / "session" / "case.sqlite").read_bytes()
    after_quorum_bytes = quorum_path.read_bytes() if quorum_path.exists() else None
    assert before_quorum_bytes == after_quorum_bytes
    event_types = {item.event_type for item in session.events_since()}
    assert PublicEventType.RECOVERY_PREPARED not in event_types
    assert PublicEventType.APPROVAL_REQUESTED not in event_types
    assert PublicEventType.APPROVAL_RECORDED not in event_types
    assert PublicEventType.EXECUTION_STARTED not in event_types
    assert (
        len(
            [
                item
                for item in session.events_since()
                if item.event_type is PublicEventType.TOOL_STARTED
            ]
        )
        > first_operation_count
    )


def test_each_chat_turn_records_a_distinct_read_harness_trace(tmp_path: Path) -> None:
    session = _session(tmp_path)
    first = session.chat_command("Where did the units go?", idempotency_key="chat:trace:1")
    first_events = session.events_since()
    first_tools = len(
        [item for item in first_events if item.event_type is PublicEventType.TOOL_STARTED]
    )
    second = session.chat_command("Why this cause?", idempotency_key="chat:trace:2")
    second_events = session.events_since()
    second_tools = len(
        [item for item in second_events if item.event_type is PublicEventType.TOOL_STARTED]
    )

    assert first["read_only"] is True and second["read_only"] is True
    assert second_tools > first_tools
    assert (
        len(
            {
                item.idempotency_key
                for item in second_events
                if item.event_type is PublicEventType.TOOL_STARTED
            }
        )
        == second_tools
    )


def test_case_console_answers_current_case_and_exposes_typed_next_actions(
    tmp_path: Path,
) -> None:
    """Every Case Console choice is grounded and leaves an auditable boundary."""

    session = _session(tmp_path)
    initial_actions = {item["id"]: item for item in session._case_console_actions()}
    assert set(initial_actions) == {
        "continue_investigation",
        "compare_causes",
        "show_evidence",
        "explain_decision",
        "prepare_recovery",
    }
    assert initial_actions["continue_investigation"]["enabled"] is True
    assert initial_actions["prepare_recovery"]["enabled"] is False

    status = session.chat_command(
        "What is happening now?",
        idempotency_key="case-console:status",
    )
    assert "100 expected" in status["message"]
    assert "80 recorded in ERP" in status["message"]
    assert "20 stopped at the queue" in status["message"]
    assert "Case v1" in status["message"]
    assert status["read_only"] is True
    assert {item["id"] for item in status["next_actions"]} == set(initial_actions)
    assert {item["id"]: item for item in status["next_actions"]}["continue_investigation"][
        "enabled"
    ] is False
    assert {item["id"]: item for item in status["next_actions"]}["prepare_recovery"][
        "enabled"
    ] is True
    chat_event = next(
        item
        for item in reversed(session.events_since())
        if item.event_type is PublicEventType.CHAT_MESSAGE
    )
    assert chat_event.payload["next_actions"] == status["next_actions"]

    next_step = session.chat_command(
        "What should we do next?",
        idempotency_key="case-console:next-step",
    )
    assert "Case v1" in next_step["message"]
    assert "prepare" in next_step["message"]
    compare = session.chat_command(
        "Compare causes for this case.",
        idempotency_key="case-console:compare",
    )
    assert compare["intent"] == "compare_hypotheses"
    assert compare["citations"]
    evidence = session.chat_command(
        "Show the evidence supporting the case.",
        idempotency_key="case-console:evidence",
    )
    assert evidence["intent"] == "retrieve_evidence"
    assert evidence["citations"]
    explanation = session.chat_command(
        "Explain the evaluator decision.",
        idempotency_key="case-console:evaluator",
    )
    assert explanation["intent"] == "explain_evaluator_decision"
    assert "evaluator returned" in explanation["message"]

    prepared = session.decision_command(
        {
            "command": "prepare_recovery",
            "tool": "restart_receipt_message",
            "idempotency_key": "case-console:prepare",
        }
    )
    assert prepared["approval"]["status"] == "OPEN"
    event_types = {item.event_type for item in session.events_since()}
    assert PublicEventType.RECOVERY_PREPARED in event_types
    assert PublicEventType.APPROVAL_REQUESTED in event_types
    assert PublicEventType.APPROVAL_RECORDED not in event_types
    assert PublicEventType.EXECUTION_STARTED not in event_types


def test_case_console_cannot_revive_a_durably_degraded_advisory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Provider failure stays terminal for chat but not deterministic preparation."""

    session = _session(tmp_path)
    session._append(
        PublicEventType.PROVIDER_DEGRADED,
        actor="orchestrator",
        status="DEGRADED",
        case_version=session._current_case_version(),
        correlation_id=session.trace_id,
        idempotency_key="test:provider-degraded",
        payload={"provider": "scripted", "error_code": "SIMULATED_FAILURE"},
    )
    session._append(
        PublicEventType.WORKFLOW_BLOCKED,
        actor="deterministic-workflow",
        status="BLOCKED",
        case_version=session._current_case_version(),
        correlation_id=session.case_id,
        idempotency_key="test:workflow-blocked",
        payload={"reason": "ADVISORY_UNAVAILABLE", "operational_effect": "NONE"},
    )

    def unexpected_harness(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("terminally degraded case must not rerun the harness")

    monkeypatch.setattr(session, "_run_read_only_harness", unexpected_harness)
    with pytest.raises(QuorumDenied, match="durably degraded"):
        session.chat_command(
            "What is happening now?",
            idempotency_key="degraded:chat",
        )
    prepared = session.decision_command(
        {
            "command": "prepare_recovery",
            "tool": "restart_receipt_message",
            "idempotency_key": "degraded:prepare",
        }
    )
    assert prepared["approval"]["status"] == "OPEN"

    actions = {item["id"]: item for item in session._case_console_actions()}
    assert actions["prepare_recovery"]["enabled"] is False
    assert all(
        item["enabled"] is False
        for key, item in actions.items()
        if key != "prepare_recovery"
    )
    event_types = [item.event_type for item in session.events_since()]
    assert PublicEventType.EVALUATION_COMPLETED not in event_types
    assert PublicEventType.RECOVERY_PREPARED in event_types
    assert PublicEventType.APPROVAL_REQUESTED in event_types
    assert PublicEventType.EXECUTION_STARTED not in event_types


def test_replay_projection_is_not_claimed_before_execution(tmp_path: Path) -> None:
    session = _session(tmp_path)
    initial = session.snapshot()
    assert initial["replay"]["replayed"] is False
    assert initial["replay"]["replay_safe"] is False
    assert initial["replay"]["effect_delta"] is None
    assert initial["execution"]["replay_effect_delta"] is None

    prepared = session.decision_command(
        {
            "command": "prepare_recovery",
            "tool": "restart_receipt_message",
            "idempotency_key": "decision:replay-derived:prepare",
        }
    )
    intent_id = prepared["approval"]["intent_id"]
    for principal, key in (
        ("integration-operator", "decision:replay-derived:operator"),
        ("ap-approver", "decision:replay-derived:ap"),
    ):
        session.decision_command(
            {
                "command": "approve",
                "intent_id": intent_id,
                "principal_id": principal,
                "idempotency_key": key,
            }
        )
    completed = session.decision_command(
        {
            "command": "execute",
            "intent_id": intent_id,
            "idempotency_key": "decision:replay-derived:execute",
        }
    )
    assert completed["replay"]["replayed"] is True
    assert completed["replay"]["replay_safe"] is True
    assert completed["replay"]["effect_delta"] == 0
    verification = next(
        item
        for item in session.events_since()
        if item.event_type is PublicEventType.VERIFICATION_COMPLETED
    )
    execution = next(
        item
        for item in session.events_since()
        if item.event_type is PublicEventType.EXECUTION_COMPLETED
    )
    replay_after = execution.payload.get("effect_count_after_replay")
    replay_first = execution.payload.get("effect_count_after_first")
    assert isinstance(replay_after, int)
    assert isinstance(replay_first, int)
    assert verification.payload["replay_effect_delta"] == (replay_after - replay_first)


def test_next_action_has_no_inherited_quorum_after_receipt_recovery(tmp_path: Path) -> None:
    session = _session(tmp_path)
    prepared = session.decision_command(
        {
            "command": "prepare_recovery",
            "tool": "restart_receipt_message",
            "idempotency_key": "decision:next-action:prepare-receipt",
        }
    )
    receipt_intent = prepared["approval"]["intent_id"]
    for principal, key in (
        ("integration-operator", "decision:next-action:receipt-operator"),
        ("ap-approver", "decision:next-action:receipt-ap"),
    ):
        session.decision_command(
            {
                "command": "approve",
                "intent_id": receipt_intent,
                "principal_id": principal,
                "idempotency_key": key,
            }
        )
    session.decision_command(
        {
            "command": "execute",
            "intent_id": receipt_intent,
            "idempotency_key": "decision:next-action:execute-receipt",
        }
    )
    next_action = session.decision_command(
        {
            "command": "prepare_recovery",
            "tool": "release_invoice",
            "idempotency_key": "decision:next-action:prepare-invoice",
        }
    )
    assert next_action["approval"]["intent_id"].endswith(":release_invoice")
    assert next_action["approval"]["status"] == "OPEN"
    assert all(
        item["intent_id"] != next_action["approval"]["intent_id"]
        for item in next_action["approvals"]
    )


def test_two_action_completion_projects_closed_no_action_gate(tmp_path: Path) -> None:
    session = _session(tmp_path)

    def execute_action(tool: str, prefix: str) -> dict[str, Any]:
        prepared = session.decision_command(
            {
                "command": "prepare_recovery",
                "tool": tool,
                "idempotency_key": f"decision:closed:{prefix}:prepare",
            }
        )
        intent_id = prepared["approval"]["intent_id"]
        for principal, role in (
            ("integration-operator", "operator"),
            ("ap-approver", "ap"),
        ):
            session.decision_command(
                {
                    "command": "approve",
                    "intent_id": intent_id,
                    "principal_id": principal,
                    "idempotency_key": f"decision:closed:{prefix}:{role}",
                }
            )
        return session.decision_command(
            {
                "command": "execute",
                "intent_id": intent_id,
                "idempotency_key": f"decision:closed:{prefix}:execute",
            }
        )

    execute_action("restart_receipt_message", "receipt")
    completed = execute_action("release_invoice", "invoice")

    assert completed["incident"]["status"] == "CLOSED"
    assert completed["decisions"][0]["eligibility"] == "NO_ACTION"
    assert completed["approval"]["status"] == "NO_ACTION"
    assert completed["approval"]["intent_id"] is None
    assert completed["execution"]["verified"] is True
    assert completed["approval"]["history"][-1]["tool"] == "release_invoice"
    assert completed["approval"]["history"][-1]["status"] == "CONSUMED"
    with pytest.raises(QuorumDenied, match="only replay"):
        session.start_investigation()


def test_command_key_reuse_is_rejected_after_cached_chat_response(tmp_path: Path) -> None:
    session = _session(tmp_path)
    session.chat_command("Where did the missing units go?", idempotency_key="chat:reuse:1")

    with pytest.raises(EventLedgerError, match="different command envelope"):
        session.chat_command("Approve and execute it.", idempotency_key="chat:reuse:1")


def test_reused_command_envelope_resumes_when_result_cache_is_missing(tmp_path: Path) -> None:
    session = _session(tmp_path)

    prepare_key = "decision:resume:prepare"
    assert (
        session._register_command(
            idempotency_key=prepare_key,
            command_kind="prepare_recovery",
            identity={},
            payload={"tool": "restart_receipt_message"},
        )
        is False
    )
    prepared = session.prepare_decision("restart_receipt_message", idempotency_key=prepare_key)
    intent_id = prepared["approval"]["intent_id"]

    for principal, key in (
        ("integration-operator", "decision:resume:operator"),
        ("ap-approver", "decision:resume:ap"),
    ):
        session.decision_command(
            {
                "command": "approve",
                "intent_id": intent_id,
                "principal_id": principal,
                "idempotency_key": key,
            }
        )
    intent = session._load_intent(intent_id)
    assert intent is not None
    slug = intent.tool.value.replace("_", "-")
    execution_id = f"execution:{session.incident_id}:{slug}"
    effect_key = f"effect:{session.incident_id}:{slug}"
    execute_key = "decision:resume:execute"
    assert (
        session._register_command(
            idempotency_key=execute_key,
            command_kind="execute",
            identity={
                "intent_id": intent_id,
                "execution_id": execution_id,
                "case_version": intent.case_version,
            },
            payload={"effect_key": effect_key},
        )
        is False
    )
    completed = session.execute_decision(intent_id=intent_id, idempotency_key=execute_key)
    assert completed["execution"]["verified"] is True
    assert len(completed["execution"]["effects"]) == 1


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

        status, body = request("/healthz")
        assert status == 200
        health = json.loads(body)
        assert health["local_synthetic_commands"] is True
        assert health["provider_calls"] is False
        assert health["write_scope"] == "local_synthetic_only"
        assert health["advisory_tools_read_only"] is True

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

        before_replay = json.loads(request(f"/api/v1/incidents/{incident_id}")[1])
        replay_request = Request(f"{base}/api/v1/incidents/{incident_id}/events?after=0&replay=1")
        with urlopen(replay_request, timeout=20) as replay_stream:
            replay_body = replay_stream.read()
        assert b"event: investigation.started" in replay_body
        assert b"event: evaluation.completed" in replay_body
        after_replay = json.loads(request(f"/api/v1/incidents/{incident_id}")[1])
        assert after_replay["projection_sequence"] == before_replay["projection_sequence"]
        assert len(after_replay["events"]) == len(before_replay["events"])
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_live_scenario_and_metrics_routes_use_authoritative_session_state(
    tmp_path: Path,
) -> None:
    """Scenario controls and the observability scrape share the session projection."""

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
    ) -> tuple[int, bytes]:
        body = None if payload is None else json.dumps(payload).encode()
        headers = {"Content-Type": "application/json"} if body is not None else {}
        request_value = Request(base + path, method=method, data=body, headers=headers)
        try:
            with urlopen(request_value, timeout=5) as response:
                return response.status, response.read()
        except HTTPError as exc:
            return exc.code, exc.read()

    try:
        status, raw = request("/api/v1/scenarios")
        assert status == 200
        scenarios = json.loads(raw)
        assert [item["id"] for item in scenarios["scenarios"]] == [
            "normal",
            "incident",
            "recovery",
        ]
        assert scenarios["scenarios"][0]["status"] == "READY"
        assert scenarios["scenarios"][2]["status"] == "LOCKED"
        catalog_incident_id = scenarios["scenarios"][1]["incident_id"]
        assert catalog_incident_id != "missing-20-001"

        status, raw = request(
            "/api/v1/scenarios", method="POST", payload={"scenario": "normal"}
        )
        assert status == 200
        normal = json.loads(raw)
        assert normal["scenario"] == "normal"
        assert normal["incident_id"] == "missing-20-normal"
        assert normal["unit_counts"] == {"total": 100, "erp_recorded": 100, "queue_failed": 0}
        flow_nodes = {item["id"]: item for item in normal["flow"]["nodes"]}
        assert flow_nodes["warehouse"]["count"] == 100
        assert flow_nodes["message-queue"]["count"] == 0
        assert flow_nodes["erp"]["count"] == 100
        assert flow_nodes["invoice"]["status"] == "RELEASED"
        assert normal["flow"]["summary"] == {
            "expected": 100,
            "recorded": 100,
            "queue_exception": 0,
            "invoice": 100,
            "healthy_nodes": 4,
        }
        assert normal["topology"]["nodes"][-1] == {
            "id": "invoice",
            "label": "Invoice",
            "health": "RELEASED",
        }
        assert normal["command"] == "scenario_selected"

        status, raw = request(
            "/api/v1/scenarios",
            method="POST",
            payload={"scenario": "incident", "incident_id": catalog_incident_id},
        )
        assert status == 200
        incident = json.loads(raw)
        assert incident["incident_id"] == catalog_incident_id
        assert incident["projection_sequence"] >= 4
        event_types = [event["event_type"] for event in incident["events"]]
        source_index = event_types.index("source.condition.injected")
        detected_index = event_types.index("incident.detected")
        assert source_index < detected_index
        telemetry = [
            event for event in incident["events"] if event["event_type"] == "telemetry.observed"
        ]
        assert len(telemetry) >= 2
        assert telemetry[0]["payload"]["unit_counts"] == {
            "total": 100,
            "erp_recorded": 100,
            "queue_failed": 0,
        }
        assert telemetry[-1]["payload"]["unit_counts"] == {
            "total": 100,
            "erp_recorded": 80,
            "queue_failed": 20,
        }

        # Detection is the handoff boundary: no browser /start command is
        # issued, yet the same durable session advances through the local
        # multi-agent harness and its scripted evaluation.
        incident_session = server.registry.get(catalog_incident_id)
        deadline = monotonic() + 10
        while monotonic() < deadline and not any(
            event.event_type is PublicEventType.EVALUATION_COMPLETED
            for event in incident_session.events_since()
        ):
            incident_session.wait_for_events(
                incident_session.ledger.latest_sequence(catalog_incident_id),
                timeout=0.25,
            )
        incident_events = incident_session.events_since()
        incident_types = [event.event_type for event in incident_events]
        source_index = incident_types.index(PublicEventType.SOURCE_CONDITION_INJECTED)
        detected_index = incident_types.index(PublicEventType.INCIDENT_DETECTED)
        started_index = incident_types.index(PublicEventType.INVESTIGATION_STARTED)
        assert source_index < detected_index < started_index
        assert sum(
            event.event_type is PublicEventType.INVESTIGATION_STARTED
            for event in incident_events
        ) == 1
        assert any(
            event.event_type is PublicEventType.AGENT_STARTED for event in incident_events
        )
        assert any(
            event.event_type is PublicEventType.EVALUATION_COMPLETED for event in incident_events
        )
        assert incident_session.snapshot()["execution"]["effects"] == []

        status, raw = request(
            "/api/v1/scenarios",
            method="POST",
            payload={"scenario": "incident", "incident_id": catalog_incident_id},
        )
        assert status == 409
        assert json.loads(raw)["error"]["code"] == "scenario_transition_required"

        status, raw = request("/api/v1/scenarios")
        assert status == 200
        active_catalog = json.loads(raw)
        active_incident = next(
            item for item in active_catalog["scenarios"] if item["id"] == "incident"
        )
        assert active_incident["incident_id"] == catalog_incident_id

        status, raw = request("/api/v1/incidents/missing-20-normal/metrics")
        assert status == 200
        metrics = json.loads(raw)
        assert metrics["source"] == "authoritative_snapshot_and_public_ledger"
        assert metrics["expected_units"] == metrics["recorded_units"] == 100
        assert metrics["queue_units"] == 0
        assert metrics["projection_sequence"] == metrics["sse"]["latest_sequence"]

        status, raw = request("/metrics")
        assert status == 200
        prometheus = raw.decode()
        assert 'missing20_expected_units{incident_id="missing-20-normal"} 100' in prometheus
        assert 'missing20_queue_units{incident_id="missing-20-normal"} 0' in prometheus

        status, raw = request(
            "/api/v1/scenarios", method="POST", payload={"scenario": "unsupported"}
        )
        assert status == 400
        assert json.loads(raw)["error"]["code"] == "invalid_scenario"

        status, raw = request(
            "/api/v1/scenarios", method="POST", payload={"scenario": "recovery"}
        )
        assert status == 409
        assert json.loads(raw)["error"]["code"] == "scenario_not_ready"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_unknown_incident_lookup_is_fail_closed_and_does_not_seed_a_session(
    tmp_path: Path,
) -> None:
    """A bad deep link is a lookup failure, never an implicit Scenario Lab write."""

    try:
        server = DecisionWorkspaceServer(
            ("127.0.0.1", 0), ROOT, runtime_directory=tmp_path / "runtime"
        )
    except PermissionError:
        pytest.skip("the managed test sandbox disallows loopback sockets")
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with pytest.raises(HTTPError) as error_info, urlopen(
            Request(f"{base}/api/v1/incidents/does-not-exist"), timeout=5
        ) as response:
            response.read()
        assert error_info.value.code == 404
        payload = json.loads(error_info.value.read())
        assert payload["error"]["code"] == "incident_not_found"
        assert "does-not-exist" in payload["error"]["detail"]
        assert "does-not-exist" not in server.registry._sessions
        assert not (tmp_path / "runtime" / "does-not-exist").exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_copilot_answers_retryable_queue_evidence_with_exact_citation(tmp_path: Path) -> None:
    """The supported retryability question names the authoritative queue record."""

    session = _session(tmp_path)
    response = session.chat_command(
        "Which evidence proves the queue message is retryable?",
        idempotency_key="chat:retryable-evidence:1",
    )

    assert response["intent"] == "retrieve_evidence"
    assert len(response["citations"]) == 1
    citation = str(response["citations"][0])
    assert citation.endswith(":failed-message")
    assert citation in response["message"]
    assert "error_code=DOCUMENT_LOCKED_RETRYABLE" in response["message"]
    assert "retry_eligible=True" in response["message"]
    assert "lock_cleared=True" in response["message"]


def test_copilot_composes_status_proof_and_governed_next_step(tmp_path: Path) -> None:
    """A combined operator question receives one concise, grounded answer."""

    session = _session(tmp_path)
    response = session.chat_command(
        "What is the current status, which exact evidence proves RETRYABLE_MESSAGE "
        "and the 20-unit gap, and what should the human do next?",
        idempotency_key="chat:status-proof-next:scripted",
    )

    evidence = tuple(session.store.list_evidence(session.case_id))
    latest = latest_authoritative_evidence(evidence)
    expected_citations = [
        next(
            item.evidence_id
            for item in latest
            if item.source_type is source_type
        )
        for source_type in (
            EvidenceSourceType.FAILED_MESSAGE_QUEUE,
            EvidenceSourceType.ERP_RECEIPT,
            EvidenceSourceType.WAREHOUSE,
        )
    ]
    assert response["intent"] == "inspect_current_status"
    assert response["citations"] == expected_citations
    assert "RETRYABLE_MESSAGE is SUPPORTED" in response["message"]
    assert "20 stopped at the message queue" in response["message"]
    assert all(citation in response["message"] for citation in expected_citations)
    assert "prepare Receipt Message Restart for two-role approval" in response["message"]
    assert "cannot approve or execute autonomously" in response["message"]


def test_agentcore_shaped_chat_composes_status_proof_and_next_step(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The direct answer remains grounded when the role turn has provider-shaped output."""

    factory = AgentCoreRuntimeFactory(
        config=AgentCoreRuntimeConfig(
            runtime_arn="arn:aws:bedrock-agentcore:us-west-2:123456789012:runtime/fake"
        )
    )
    session = ExperimentSession(
        ROOT,
        data_directory=tmp_path / "agentcore-chat",
        model_factory=factory,
    )
    evidence = tuple(session.store.list_evidence(session.case_id))
    by_source = {item.source_type: item.evidence_id for item in evidence}
    output = {
        "investigator_id": "retryable_message_investigator",
        "hypothesis_type": "RETRYABLE_MESSAGE",
        "conclusion": "SUPPORTED",
        "confidence_band": "HIGH",
        "factual_claims": [
            {
                "claim_id": "retryable-status-proof",
                "statement": "Twenty units are stopped at a retryable message queue.",
                "relation": "SUPPORTS_HYPOTHESIS",
                "evidence_ids": [
                    by_source[EvidenceSourceType.FAILED_MESSAGE_QUEUE],
                    by_source[EvidenceSourceType.ERP_RECEIPT],
                    by_source[EvidenceSourceType.WAREHOUSE],
                ],
            }
        ],
    }

    def fake_invoke(
        self: AgentCoreRuntimeModel, prompt: str
    ) -> tuple[Any, int, int, dict[str, object]]:
        del self, prompt
        return (
            {"output": output},
            12,
            8,
            {
                "mode": "agentcore",
                "provider": "agentcore",
                "model": "agentcore-runtime",
                "transport": "agentcore_invoke_agent_runtime",
                "region": "us-west-2",
                "qualifier": "DEFAULT",
                "runtime_configured": True,
                "invocation_id": "runtime-status-proof-next",
                "invocation_proof": "returned",
                "status": "RETURNED",
                "invocation_status": "RETURNED",
            },
        )

    monkeypatch.setattr(AgentCoreRuntimeModel, "_invoke", fake_invoke)
    response = session.chat_command(
        "What is the current status, which exact evidence proves RETRYABLE_MESSAGE "
        "and the 20-unit gap, and what should the human do next?",
        idempotency_key="chat:status-proof-next:agentcore",
    )

    assert response["provider_metadata"]["provider"] == "agentcore"
    assert response["provider_metadata"]["invocation_id"] == "runtime-status-proof-next"
    assert response["citations"] == [
        by_source[EvidenceSourceType.FAILED_MESSAGE_QUEUE],
        by_source[EvidenceSourceType.ERP_RECEIPT],
        by_source[EvidenceSourceType.WAREHOUSE],
    ]
    assert "RETRYABLE_MESSAGE is SUPPORTED" in response["message"]
    assert "prepare Receipt Message Restart for two-role approval" in response["message"]


def test_scenario_reentry_after_recovery_uses_a_fresh_authoritative_incident(
    tmp_path: Path,
) -> None:
    """Recovery stays inspectable while a later Incident starts a new ledger."""

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
    ) -> tuple[int, bytes]:
        body = None if payload is None else json.dumps(payload).encode()
        headers = {"Content-Type": "application/json"} if body is not None else {}
        request_value = Request(base + path, method=method, data=body, headers=headers)
        try:
            with urlopen(request_value, timeout=10) as response:
                return response.status, response.read()
        except HTTPError as exc:
            return exc.code, exc.read()

    def post(path: str, payload: object) -> dict[str, Any]:
        status, raw = request(path, method="POST", payload=payload)
        assert status == 200, raw
        parsed = json.loads(raw)
        assert isinstance(parsed, dict)
        return parsed

    try:
        first = post("/api/v1/scenarios", {"scenario": "incident"})
        first_id = str(first["incident_id"])
        assert first["unit_counts"] == {"total": 100, "erp_recorded": 80, "queue_failed": 20}

        first_session = server.registry.get(first_id)
        first_session.run_investigation()
        command_url = f"/api/v1/incidents/{first_id}/decisions"
        prepared = post(
            command_url,
            {
                "command": "prepare_recovery",
                "tool": "restart_receipt_message",
                "idempotency_key": "scenario-reentry:prepare",
            },
        )
        intent_id = str(prepared["approval"]["intent_id"])
        for principal in ("integration-operator", "ap-approver"):
            post(
                command_url,
                {
                    "command": "approve",
                    "intent_id": intent_id,
                    "principal_id": principal,
                    "idempotency_key": f"scenario-reentry:approve:{principal}",
                },
            )
        post(
            command_url,
            {
                "command": "execute",
                "intent_id": intent_id,
                "idempotency_key": "scenario-reentry:execute",
            },
        )
        invoice_prepared = post(
            command_url,
            {
                "command": "prepare_recovery",
                "tool": "release_invoice",
                "idempotency_key": "scenario-reentry:invoice:prepare",
            },
        )
        invoice_intent_id = str(invoice_prepared["approval"]["intent_id"])
        for principal in ("integration-operator", "ap-approver"):
            post(
                command_url,
                {
                    "command": "approve",
                    "intent_id": invoice_intent_id,
                    "principal_id": principal,
                    "idempotency_key": f"scenario-reentry:invoice:approve:{principal}",
                },
            )
        post(
            command_url,
            {
                "command": "execute",
                "intent_id": invoice_intent_id,
                "idempotency_key": "scenario-reentry:invoice:execute",
            },
        )
        recovered = first_session.snapshot()
        assert recovered["incident"]["status"] == "CLOSED"
        assert recovered["execution"]["verified"] is True

        recovery = post("/api/v1/scenarios", {"scenario": "recovery"})
        assert recovery["incident_id"] == first_id
        assert recovery["execution"]["verified"] is True

        # A fresh incident is an explicit reset transition, not an implicit
        # replacement of the active run. The old recovery remains inspectable.
        post("/api/v1/scenarios", {"scenario": "normal"})
        fresh = post("/api/v1/scenarios", {"scenario": "incident"})
        fresh_id = str(fresh["incident_id"])
        assert fresh_id != first_id
        assert fresh["unit_counts"] == {
            "total": 100,
            "erp_recorded": 80,
            "queue_failed": 20,
        }
        assert fresh["execution"]["verified"] is False
        assert fresh["incident"]["status"] != "CLOSED"
        fresh_events = [event for event in fresh["events"] if isinstance(event, dict)]
        fresh_sequences = [
            int(event["sequence"])
            for event in fresh_events
            if isinstance(event.get("sequence"), (int, float))
        ]
        assert isinstance(fresh["projection_sequence"], int)
        assert fresh_sequences == list(range(1, fresh["projection_sequence"] + 1))
        fresh_by_type = {
            event_type: next(
                int(event["sequence"])
                for event in fresh_events
                if event.get("event_type") == event_type
            )
            for event_type in ("source.condition.injected", "incident.detected")
        }
        assert fresh_by_type["source.condition.injected"] < fresh_by_type["incident.detected"]
        fresh_telemetry = fresh["telemetry"]["history"]
        assert len(fresh_telemetry) >= 2
        assert fresh_telemetry[0]["unit_counts"] == {
            "total": 100,
            "erp_recorded": 100,
            "queue_failed": 0,
        }
        assert fresh_telemetry[-1]["unit_counts"] == {
            "total": 100,
            "erp_recorded": 80,
            "queue_failed": 20,
        }

        fresh_session = server.registry.get(fresh_id)
        fresh_session.run_investigation()
        chat = fresh_session.chat_command(
            "Where did the missing units go?",
            idempotency_key="scenario-reentry:chat",
        )
        assert chat["citations"]
        fresh_evidence_ids = {
            item.evidence_id for item in fresh_session.store.list_evidence(fresh_session.case_id)
        }
        assert set(chat["citations"]).issubset(fresh_evidence_ids)

        post("/api/v1/scenarios", {"scenario": "normal"})
        golden = post("/api/v1/scenarios", {"scenario": "golden"})
        assert golden["incident_id"] not in {first_id, fresh_id}
        assert golden["unit_counts"] == {
            "total": 100,
            "erp_recorded": 80,
            "queue_failed": 20,
        }
        assert golden["execution"]["verified"] is False
        golden_session = server.registry.get(str(golden["incident_id"]))
        deadline = monotonic() + 10
        golden_snapshot = golden_session.snapshot()
        while not any(
            event.get("event_type") == "evaluation.completed"
            for event in golden_snapshot.get("events", [])
            if isinstance(event, dict)
        ) and monotonic() < deadline:
            Event().wait(0.05)
            golden_snapshot = golden_session.snapshot()
        assert any(
            event.get("event_type") == "evaluation.completed"
            for event in golden_snapshot.get("events", [])
            if isinstance(event, dict)
        ), {
            "incident_id": golden_snapshot.get("incident_id"),
            "projection_sequence": golden_snapshot.get("projection_sequence"),
            "events": [
                event.get("event_type")
                for event in golden_snapshot.get("events", [])
                if isinstance(event, dict)
            ],
        }
        assert golden_snapshot["advisory"]["status"] == "COMPLETE"
        assert golden_snapshot["execution"]["verified"] is False
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
