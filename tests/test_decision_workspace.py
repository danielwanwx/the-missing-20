from __future__ import annotations

import hashlib
import io
import json
import threading
from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from scripts.decision_workspace_server import DecisionWorkspaceHandler, DecisionWorkspaceServer
from the_missing_20.authority_b import workspace_demo
from the_missing_20.authority_b.lifecycle import (
    LIFECYCLE_ARTIFACT_PATH,
    load_lifecycle_bundle,
)
from the_missing_20.authority_b.models import canonical_json
from the_missing_20.authority_b.workspace_demo import (
    WORKSPACE_SCHEMA_VERSION,
    WorkspaceEvidenceClass,
    WorkspaceMode,
    WorkspaceUnavailable,
    _hypotheses_from_golden,
    build_decision_workspace,
)
from the_missing_20.experiment.session import ExperimentSession
from the_missing_20.live_sources import (
    LiveSourceRegistry,
    LiveSourceSnapshot,
    LiveSourceStatus,
)

ROOT = Path(__file__).resolve().parents[1]


def _resign_payload(payload: dict[str, object]) -> None:
    payload["bundle_digest"] = hashlib.sha256(
        canonical_json(
            {key: value for key, value in payload.items() if key != "bundle_digest"}
        ).encode()
    ).hexdigest()


@pytest.mark.parametrize("mode", ("complete", "degraded"))
def test_workspace_artifact_is_typed_stable_and_claim_classified(mode: str) -> None:
    artifact = build_decision_workspace(ROOT, mode=mode)
    assert not isinstance(artifact, WorkspaceUnavailable)
    payload = artifact.model_dump(mode="json")
    assert payload["schema_version"] == WORKSPACE_SCHEMA_VERSION
    assert set(item["label"] for item in payload["evidence_taxonomy"]) == {
        "PROVEN",
        "SCRIPTED SYNTHETIC PROOF",
        "NOT PROVEN",
    }
    assert {item["evidence_class"] for item in payload["claims"]} <= {
        item.value for item in WorkspaceEvidenceClass
    }
    assert payload["human_control"]["controls_enabled"] is False
    assert payload["execution"]["replay_effect_delta"] == 0
    assert payload["m6_aws_proof"]["status"] == "PASS"
    assert payload["case"]["discrepancy_statement"] == "100 expected, 80 recorded, 20 missing."
    hypotheses = payload["advisory"]["hypotheses"]
    if mode == "complete":
        assert [
            (
                item["hypothesis_type"],
                len(item["supporting_evidence_ids"]),
                len(item["contradicting_evidence_ids"]),
            )
            for item in hypotheses
        ] == [
            ("RETRYABLE_MESSAGE", 5, 0),
            ("GENUINE_SHORT_SHIPMENT", 0, 5),
            ("ALREADY_POSTED", 0, 5),
        ]
    assert all(
        item["supporting_evidence_ids"] or item["contradicting_evidence_ids"] for item in hypotheses
    )
    assert all(
        evidence_id.startswith("m5-authority-b-case:")
        for item in hypotheses
        for evidence_id in (
            *item["supporting_evidence_ids"],
            *item["contradicting_evidence_ids"],
        )
    )
    assert payload["m6_aws_proof"]["real_provider_integration"]["outcome_status"] == "DEGRADED"
    assert (
        payload["m6_aws_proof"]["real_provider_integration"]["stable_real_usefulness"]
        == "NOT_PROVEN"
    )
    agentcore_status = {
        item["capability_id"]: item["status"]
        for item in payload["m6_aws_proof"]["capabilities"]
        if item["capability_id"].startswith("agentcore_")
    }
    assert agentcore_status == {
        "agentcore_runtime": "PROVEN",
        "agentcore_observability": "PROVEN",
        "agentcore_deployment": "PROVEN",
        "agentcore_gateway": "NOT_PROVEN",
        "agentcore_policy": "NOT_PROVEN",
    }
    parsed = type(artifact).model_validate_json(json.dumps(payload))
    assert parsed.artifact_digest == artifact.artifact_digest
    if mode == "complete":
        assert parsed.advisory.status == "COMPLETE"
        assert len(parsed.advisory.hypotheses) == 3
        assert (
            parsed.advisory.usefulness_evidence_class
            is WorkspaceEvidenceClass.SCRIPTED_SYNTHETIC_PROOF
        )
    else:
        assert parsed.advisory.status == "DEGRADED"
        assert parsed.advisory.hypotheses == ()
        assert parsed.advisory.usefulness_evidence_class is WorkspaceEvidenceClass.NOT_PROVEN


def test_workspace_rejects_tampered_digest() -> None:
    artifact = build_decision_workspace(ROOT, mode=WorkspaceMode.COMPLETE)
    payload = artifact.model_dump(mode="json")
    payload["artifact_digest"] = "tampered"
    with pytest.raises(ValueError, match="artifact digest mismatch"):
        type(artifact).model_validate_json(json.dumps(payload))


def test_scripted_citation_with_unknown_evidence_fails_closed() -> None:
    golden = json.loads((ROOT / "artifacts/golden/golden-v2.json").read_text(encoding="utf-8"))
    claim = golden["scripted_strands_proof"]["profiles"][0]["agent_run"]["investigators"][0][
        "factual_claims"
    ][0]
    claim["evidence_ids"] = ["case-01-retryable-lock-main-path:unknown-record"]
    with pytest.raises(ValueError, match="citation is not admitted"):
        _hypotheses_from_golden(golden, "m5-authority-b-case", {"m5-authority-b-case:erp-receipt"})


def test_scripted_hypothesis_without_evidence_fails_closed() -> None:
    golden = json.loads((ROOT / "artifacts/golden/golden-v2.json").read_text(encoding="utf-8"))
    investigator = golden["scripted_strands_proof"]["profiles"][0]["agent_run"]["investigators"][0]
    investigator["factual_claims"] = []
    with pytest.raises(ValueError, match="no admitted evidence"):
        _hypotheses_from_golden(
            golden,
            "m5-authority-b-case",
            {
                "m5-authority-b-case:erp-receipt",
                "m5-authority-b-case:failed-message",
                "m5-authority-b-case:invoice",
                "m5-authority-b-case:material-documents",
                "m5-authority-b-case:warehouse",
            },
        )


def test_workspace_case_rejects_inconsistent_headline_numbers() -> None:
    artifact = build_decision_workspace(ROOT, mode=WorkspaceMode.COMPLETE)
    assert not isinstance(artifact, WorkspaceUnavailable)
    payload = artifact.model_dump(mode="json")
    payload["case"]["missing_quantity"] = 19
    with pytest.raises(ValueError, match="quantities are inconsistent"):
        type(artifact).model_validate_json(json.dumps(payload))


def test_workspace_exposes_final_case_and_initial_decision_as_different_times() -> None:
    artifact = build_decision_workspace(ROOT, mode=WorkspaceMode.COMPLETE)
    assert not isinstance(artifact, WorkspaceUnavailable)
    assert artifact.case.status == "CLOSED"
    assert artifact.deterministic_decision.eligibility == "PENDING_APPROVAL"


def test_workspace_is_backed_by_distinct_authoritative_lifecycle_actions() -> None:
    bundle = load_lifecycle_bundle(ROOT)
    assert bundle.schema_version == "AuthorityBLifecycleDemo/v1"
    assert len(bundle.actions) == 2
    assert {item.tool.value for item in bundle.actions} == {
        "restart_receipt_message",
        "release_invoice",
    }
    assert len({item.intent_id for item in bundle.actions}) == 2
    assert len({item.grant_id for item in bundle.actions}) == 2
    assert len({item.effect_id for item in bundle.actions}) == 2
    assert bundle.final_state.case.status.value == "CLOSED"
    assert len(bundle.final_state.enterprise.business_effects) == 2
    complete = build_decision_workspace(ROOT, mode=WorkspaceMode.COMPLETE)
    degraded = build_decision_workspace(ROOT, mode=WorkspaceMode.DEGRADED)
    assert not isinstance(complete, WorkspaceUnavailable)
    assert not isinstance(degraded, WorkspaceUnavailable)
    assert complete.operational_projection_digest == degraded.operational_projection_digest
    assert len(complete.human_control.approvals) == 4
    assert {item.action_id for item in complete.human_control.approvals} == {
        "receipt-restart",
        "invoice-release",
    }


def test_lifecycle_mutation_or_deletion_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = ROOT / LIFECYCLE_ARTIFACT_PATH
    baseline = json.loads(source.read_text(encoding="utf-8"))
    mutations: tuple[tuple[str, Callable[[dict[str, Any]], object]], ...] = (
        ("intent", lambda value: value["intents"].pop()),
        ("attestation", lambda value: value["attestations"].pop()),
        ("grant", lambda value: value["grants"].pop()),
        ("signature", lambda value: value["grants"][0].update({"signature": "0" * 64})),
        ("version", lambda value: value["decisions"][0].update({"case_version": 99})),
        (
            "parameters",
            lambda value: value["intents"][0]["complete_parameters"].update({"quantity": 99}),
        ),
        ("attempt", lambda value: value["attempts"].pop()),
        ("effect", lambda value: value["effects"].pop()),
        ("verification", lambda value: value["verifications"].pop()),
        ("replay", lambda value: value["replays"].pop()),
        ("final_state", lambda value: value["final_state"].pop("state_digest")),
    )
    for category, mutate in mutations:
        payload = deepcopy(baseline)
        mutate(payload)
        _resign_payload(payload)
        candidate = tmp_path / f"invalid-{category}.json"
        candidate.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(ValueError):
            load_lifecycle_bundle(ROOT, path=candidate)
        monkeypatch.setattr(workspace_demo, "LIFECYCLE_ARTIFACT_PATH", str(candidate))
        unavailable = build_decision_workspace(ROOT, mode=WorkspaceMode.COMPLETE)
        assert isinstance(unavailable, WorkspaceUnavailable), category
        assert unavailable.status == "UNAVAILABLE"
        assert unavailable.operational_projection is None

    with pytest.raises(ValueError, match="lifecycle bundle is unreadable"):
        load_lifecycle_bundle(ROOT, path=tmp_path / "absent.json")


def test_invalid_workspace_mode_is_explicitly_unavailable() -> None:
    artifact = build_decision_workspace(ROOT, mode=WorkspaceMode.INVALID)
    assert isinstance(artifact, WorkspaceUnavailable)
    payload = artifact.model_dump(mode="json")
    assert payload["status"] == "UNAVAILABLE"
    assert payload["reason_code"] == "LIFECYCLE_BUNDLE_INCOMPLETE"
    assert payload["operational_projection"] is None
    assert payload["human_controls"] is None


def _request(url: str, method: str = "GET") -> tuple[int, bytes, dict[str, str]]:
    try:
        with urlopen(Request(url, method=method), timeout=5) as response:
            return response.status, response.read(), dict(response.headers.items())
    except HTTPError as exc:
        return exc.code, exc.read(), dict(exc.headers.items())


def test_workspace_server_is_local_with_scoped_synthetic_commands() -> None:
    try:
        server = DecisionWorkspaceServer(("127.0.0.1", 0), ROOT)
    except PermissionError:
        pytest.skip("the managed test sandbox disallows loopback sockets")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        status, body, headers = _request(f"{base}/api/workspace?mode=complete")
        assert status == 200
        assert json.loads(body)["mode"] == "complete"
        assert headers["Content-Security-Policy"].startswith("default-src 'self'")
        status, body, _headers = _request(f"{base}/api/workspace?mode=degraded")
        assert status == 200
        assert json.loads(body)["advisory"]["status"] == "DEGRADED"
        status, body, _headers = _request(f"{base}/api/workspace?mode=invalid")
        assert status == 200
        unavailable = json.loads(body)
        assert unavailable["status"] == "UNAVAILABLE"
        assert unavailable["operational_projection"] is None
        assert "human_control" not in unavailable
        status, _body, headers = _request(f"{base}/api/workspace?mode=complete", method="POST")
        assert status == 405
        assert headers["Allow"] == "GET"
        status, _body, _headers = _request(f"{base}/api/workspace?mode=unexpected")
        assert status == 400
        status, body, _headers = _request(f"{base}/healthz")
        assert status == 200
        health = json.loads(body)
        assert health["local_synthetic_commands"] is True
        assert health["provider_calls"] is False
        assert health["write_scope"] == "local_synthetic_only"
        assert health["advisory_tools_read_only"] is True

        asset_expectations = {
            "/assets/phosphor-regular.css": "text/css; charset=utf-8",
            "/assets/phosphor-bold.css": "text/css; charset=utf-8",
            "/assets/Phosphor.woff2": "font/woff2",
            "/assets/Phosphor-Bold.woff2": "font/woff2",
        }
        for route, content_type in asset_expectations.items():
            status, body, headers = _request(f"{base}{route}")
            assert status == 200
            assert body
            assert headers["Content-Type"] == content_type

        for route in (
            "/assets/../style.css",
            "/assets/%2e%2e/style.css",
            "/assets/phosphor-regular.css/../style.css",
        ):
            status, _body, _headers = _request(f"{base}{route}")
            assert status == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_live_source_routes_are_read_only_and_use_injected_public_context(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 8, 29, 8, 0, tzinfo=UTC)

    class StubAdapter:
        source_id = "stub-public-source"
        provider = "Public Stub"
        source_type = "route_observation"
        poll_interval_seconds = 60.0

        def fetch(self, captured_at: datetime) -> LiveSourceSnapshot:
            return LiveSourceSnapshot(
                provider=self.provider,
                source_id=self.source_id,
                source_type=self.source_type,
                location="Port of Los Angeles",
                status=LiveSourceStatus.CONNECTED,
                observed_at=captured_at,
                received_at=captured_at,
                freshness_seconds=0,
                metrics={"observations": 1},
                alerts=(),
                provenance_url="https://example.test/public-observation",
            )

    live_sources = LiveSourceRegistry((StubAdapter(),), clock=lambda: now)
    try:
        server = DecisionWorkspaceServer(
            ("127.0.0.1", 0),
            ROOT,
            runtime_directory=tmp_path / "runtime",
            live_sources=live_sources,
        )
    except PermissionError:
        pytest.skip("the managed test sandbox disallows loopback sockets")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        status, body, _headers = _request(f"{base}/api/v1/live-sources")
        assert status == 200
        current = json.loads(body)
        assert current["scope"]["external_context_only"] is True
        assert current["scope"]["operational_authority"] == "synthetic_enterprise_twin"
        assert current["sources"][0]["source_id"] == "stub-public-source"
        assert current["sources"][0]["external_context_only"] is True
        assert current["risk"]["advisory_only"] is True
        assert current["risk"]["creates_operational_incident"] is False

        status, body, _headers = _request(f"{base}/api/v1/live-sources/events?after=0")
        assert status == 200
        events = json.loads(body)
        assert events["external_context_only"] is True
        assert events["events"][0]["snapshot"]["source_id"] == "stub-public-source"
        assert events["events"][0]["new_observation"] is True
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_server_suppresses_only_expected_sse_disconnect_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    forwarded: list[tuple[object, object]] = []

    def record_error(_server: object, request: object, client_address: object) -> None:
        forwarded.append((request, client_address))

    monkeypatch.setattr(ThreadingHTTPServer, "handle_error", record_error)
    server = object.__new__(DecisionWorkspaceServer)
    request = object()
    client_address = ("127.0.0.1", 1)

    for error in (BrokenPipeError(), ConnectionResetError()):
        try:
            raise error
        except (BrokenPipeError, ConnectionResetError):
            server.handle_error(request, client_address)
    assert forwarded == []

    try:
        raise RuntimeError("unexpected server failure")
    except RuntimeError:
        server.handle_error(request, client_address)
    assert forwarded == [(request, client_address)]


class _SSEStopBuffer(io.BytesIO):
    """Stop a direct SSE handler probe after it emits the desired frames."""

    def __init__(self, stop_after_flushes: int) -> None:
        super().__init__()
        self.flushes = 0
        self.stop_after_flushes = stop_after_flushes

    def flush(self) -> None:
        self.flushes += 1
        if self.flushes >= self.stop_after_flushes:
            raise BrokenPipeError


class _SSEProbeLedger:
    def __init__(self) -> None:
        self.latest = 1

    def latest_sequence(self, _incident_id: str) -> int:
        return self.latest


class _SSEProbeSession:
    incident_id = "probe-incident"

    def __init__(self) -> None:
        self.ledger = _SSEProbeLedger()
        self.wait_calls = 0
        self.timeouts: list[float] = []
        self.first = type(
            "ProbeEvent",
            (),
            {
                "sequence": 1,
                "event_type": type("ProbeEventType", (), {"value": "incident.detected"})(),
                "model_dump": lambda self, mode: {
                    "sequence": self.sequence,
                    "event_type": self.event_type.value,
                },
            },
        )()
        self.second = type(
            "ProbeEvent",
            (),
            {
                "sequence": 2,
                "event_type": type("ProbeEventType", (), {"value": "verification.completed"})(),
                "model_dump": lambda self, mode: {
                    "sequence": self.sequence,
                    "event_type": self.event_type.value,
                },
            },
        )()

    def events_since(self, after: int) -> tuple[object, ...]:
        if after < 1:
            return (self.first,)
        if after < 2 and self.ledger.latest >= 2:
            return (self.second,)
        return ()

    def wait_for_events(self, _after: int, *, timeout: float) -> tuple[object, ...]:
        self.wait_calls += 1
        self.timeouts.append(timeout)
        if self.wait_calls >= 2:
            self.ledger.latest = 2
        return ()


class _SSEProbeHandler(DecisionWorkspaceHandler):
    def __init__(self, buffer: io.BytesIO) -> None:
        # The probe calls the handler method directly and never starts an HTTP
        # request, so only the response sink and header lookup are required.
        self.headers = cast(Any, {})
        self.wfile = buffer

    def send_response(self, _code: int, _message: str | None = None) -> None:
        return

    def send_header(self, _keyword: str, _value: str) -> None:
        return

    def end_headers(self) -> None:
        return


def _sse_probe_handler(buffer: io.BytesIO) -> _SSEProbeHandler:
    return _SSEProbeHandler(buffer)


def test_sse_stays_open_through_idle_heartbeats_then_delivers_event() -> None:
    buffer = _SSEStopBuffer(stop_after_flushes=4)
    session = _SSEProbeSession()
    handler = _sse_probe_handler(buffer)

    DecisionWorkspaceHandler._send_sse(handler, cast(ExperimentSession, session), {"after": ["0"]})

    payload = buffer.getvalue().decode("utf-8")
    assert payload.count(": heartbeat\n\n") == 2
    assert "event: incident.detected" in payload
    assert "event: verification.completed" in payload
    assert session.wait_calls == 2


def test_sse_emits_typed_reset_when_cursor_rewinds() -> None:
    class ResetSession(_SSEProbeSession):
        def wait_for_events(self, _after: int, *, timeout: float) -> tuple[object, ...]:
            self.wait_calls += 1
            self.timeouts.append(timeout)
            self.ledger.latest = 0
            return ()

    buffer = io.BytesIO()
    session = ResetSession()
    handler = _sse_probe_handler(buffer)

    DecisionWorkspaceHandler._send_sse(handler, cast(ExperimentSession, session), {"after": ["1"]})

    payload = buffer.getvalue().decode("utf-8")
    assert "event: stream.reset\n" in payload
    assert '"safe_cursor":0' in payload
