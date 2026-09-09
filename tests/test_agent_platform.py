from __future__ import annotations

import json
import threading
from copy import deepcopy
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from scripts.decision_workspace_server import DecisionWorkspaceServer
from the_missing_20.adapters.agent_platform import AgentPlatform

ROOT = Path(__file__).resolve().parents[1]


class _Reader:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def current(self) -> dict[str, object]:
        return deepcopy(self.payload)


def test_chat_tool_activity_is_immediate_and_cannot_change_control_state() -> None:
    platform = AgentPlatform(_Reader(_erp()), _Reader(_saas()))
    before = platform.current()
    platform.record_conversation_tool_progress("read_erp_evidence", "started", "chat-1")
    platform.record_conversation_tool_progress("read_erp_evidence", "succeeded", "chat-1")
    after = platform.current()
    events = [
        row for row in after["activity"] if row["event_type"].startswith("conversation.tool.")
    ]
    assert [row["status"] for row in events] == ["STARTED", "SUCCEEDED"]
    assert all(row["read_only"] and row["record_id"] == "chat-1" for row in events)
    for key in ("agent_run", "diagnosis", "execution", "approval"):
        assert after.get(key) == before.get(key)


def _erp(*, status: str = "CONNECTED", quality_hold: bool = True) -> dict[str, object]:
    return {
        "sequence": 1,
        "case_id": "M20-ECU-2026-00011-LOT-A",
        "status": status,
        "activity": [
            {
                "source_id": "erpnext-missing20",
                "provider": "ERPNext / Frappe Cloud",
                "status": "HELD" if quality_hold else "VERIFIED",
                "record_id": "MAT-PRE-2026-00001",
                "label": "ERP read · receipt MAT-PRE-2026-00001",
                "detail": "12 accepted · 8 in Quality Hold · 20 received",
            }
        ],
        "documents": [
            {
                "kind": "purchase_order",
                "name": "PUR-ORD-2026-00011",
                "quantity": 20,
                "unit_rate": 1200,
                "line_value": 24000,
                "currency": "USD",
            },
            {
                "kind": "purchase_receipt",
                "name": "MAT-PRE-2026-00001",
                "status": "PARTIAL_QUALITY_HOLD" if quality_hold else "RECEIVED",
                "received": 20,
                "accepted": 12 if quality_hold else 20,
                "rejected": 8 if quality_hold else 0,
            },
            {
                "kind": "purchase_invoice",
                "name": "ACC-PINV-2026-00007",
                "status": "PAYMENT_HOLD" if quality_hold else "OPEN",
                "on_hold": quality_hold,
                "grand_total": 24000,
                "currency": "USD",
            },
        ],
    }


def _saas(*, status: str = "CONNECTED") -> dict[str, object]:
    row = {
        "source_id": "airtable-quality-registry",
        "provider": "Airtable · Supplier Quality Registry",
        "status": "VERIFIED",
        "record_id": "rec-1",
        "label": "Registry read · APPROVED",
        "detail": "Lot A · 20 approved · correlation matched",
    }
    return {
        "sequence": 1,
        "status": status,
        "correlation_id": "M20-ECU-2026-00011-LOT-A",
        "sources": [
            row,
            {
                "source_id": "jira-capa",
                "provider": "Jira · CAPA",
                "status": "VERIFIED",
                "record_id": "QRC-1",
                "label": "CAPA read · Open",
                "detail": "Journal item",
            },
        ],
        "activity": [row],
    }


def test_live_projection_and_chart_metrics_come_from_the_same_erp_read() -> None:
    platform = AgentPlatform(_Reader(_erp()), _Reader(_saas()))

    projection = platform.current()

    case = projection["case_projection"]["case"]
    assert case["quantities"] == {
        "ordered": 20.0,
        "physically_arrived": 20.0,
        "available": 12.0,
        "quality_hold": 8.0,
        "receipt_unresolved": 0.0,
        "received": 20.0,
        "outstanding_order_quantity": 0.0,
        "available_to_promise": None,
        "received_cumulative": 20.0,
        "accepted_cumulative": 12.0,
        "released_quantity": 0.0,
        "delivered_quantity": 0.0,
        "case_balance": 12.0,
        "receipt_posted_quantity": 20.0,
        "invoice_count": 1.0,
    }
    assert case["invoice_held"] is True
    assert projection["business_impact"]["working_capital_at_risk"] == 9600.0
    metric_events = [event for event in projection["activity"] if "metrics" in event]
    assert metric_events
    assert metric_events[0]["metrics"]["expected"] == 20.0
    assert metric_events[0]["metrics"]["recorded"] == 12.0
    assert metric_events[0]["metrics"]["gap"] == 8.0
    assert metric_events[0]["provenance"] == "live"


def test_platform_admits_provider_rows_once_with_global_monotonic_sequence() -> None:
    platform = AgentPlatform(_Reader(_erp()), _Reader(_saas()))

    first = platform.current()
    second = platform.current()

    assert first["mode"]["provider_writes"] == "DISABLED"
    assert first["execution"]["available"] is False
    assert [event["sequence"] for event in first["activity"]] == [1, 2]
    assert second["latest_sequence"] == 2
    assert second["correlation"]["status"] == "PARTIAL_CORRELATION"
    assert second["agent_run"]["state"] == "IDLE"
    constellation = second["evidence_constellation"]
    assert {node["id"] for node in constellation["nodes"]} == {
        "erpnext",
        "airtable",
        "celigo",
        "jira",
        "slack",
    }
    assert (
        next(node for node in constellation["nodes"] if node["id"] == "erpnext")["latest_sequence"]
        > 0
    )
    jira = next(system for system in first["systems"] if system["id"] == "jira")
    assert jira["authority"] == "Journal only; cannot prove a release"


def test_diagnosis_detects_hold_without_claiming_release_or_provider_write() -> None:
    platform = AgentPlatform(_Reader(_erp()), _Reader(_saas()))

    projection = platform.diagnose()

    diagnosis = projection["diagnosis"]
    assert diagnosis["finding"] == "QUALITY_HOLD_DETECTED"
    assert diagnosis["status"] == "BLOCKED"
    assert "no release is executed" in diagnosis["summary"]
    assert projection["execution"]["status"] == "WRITE_DISABLED"
    assert projection["agent_run"]["run_id"] == "agent-run-0001"
    assert projection["agent_run"]["state"] == "BLOCKED"
    assert [step["status"] for step in projection["plan"]] == [
        "DONE",
        "DONE",
        "NOT_REQUIRED_YET",
        "BLOCKED",
    ]
    assert [event["sequence"] for event in projection["activity"]] == list(
        range(1, projection["latest_sequence"] + 1)
    )
    assert {
        "agent.run.observing",
        "agent.run.planning",
        "agent.run.reasoning",
        "agent.diagnosis.completed",
    } <= {event["event_type"] for event in projection["activity"]}


def test_degraded_erp_leaves_diagnosis_inconclusive() -> None:
    platform = AgentPlatform(_Reader(_erp(status="DEGRADED")), _Reader(_saas(status="DEGRADED")))

    projection = platform.diagnose()

    assert projection["diagnosis"]["finding"] == "INCONCLUSIVE"
    assert projection["diagnosis"]["status"] == "BLOCKED"
    assert projection["agent_run"]["state"] == "BLOCKED"
    assert "cannot diagnose" in projection["diagnosis"]["summary"]


def test_question_answer_is_read_only_and_does_not_claim_release() -> None:
    platform = AgentPlatform(_Reader(_erp()), _Reader(_saas()))

    projection = platform.answer("Can the agent release this receipt?")

    assert "writes are disabled" in projection["answer"]
    assert projection["activity"][-1]["event_type"] == "agent.evidence.question_answered"
    assert projection["activity"][-1]["status"] == "READ_ONLY"


def test_server_live_case_console_mode_selects_authorized_read_adapter(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("MISSING20_CASE_CONSOLE_SOURCE", "live")
    monkeypatch.delenv("MISSING20_ENVIRONMENT", raising=False)
    try:
        server = DecisionWorkspaceServer(
            ("127.0.0.1", 0), ROOT, runtime_directory=tmp_path / "runtime"
        )
    except PermissionError:
        pytest.skip("the managed test sandbox disallows loopback sockets")
    try:
        assert isinstance(server.agent_platform, AgentPlatform)
        projection = server.agent_platform.current()
        assert projection["mode"]["provenance"] == "live-read"
        assert projection["mode"]["provider_writes"] == "DISABLED"
    finally:
        server.server_close()


def test_server_exposes_only_read_only_agent_platform_commands(tmp_path: Path) -> None:
    platform = AgentPlatform(_Reader(_erp()), _Reader(_saas()))
    try:
        server = DecisionWorkspaceServer(
            ("127.0.0.1", 0),
            ROOT,
            runtime_directory=tmp_path / "runtime",
            agent_platform=platform,
        )
    except PermissionError:
        pytest.skip("the managed test sandbox disallows loopback sockets")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(f"{base}/api/v1/agent-platform", timeout=5) as response:
            current = json.loads(response.read())
        assert current["execution"]["status"] == "WRITE_DISABLED"

        request = Request(
            f"{base}/api/v1/agent-platform/ask",
            data=b'{"question":"Can the agent release this receipt?"}',
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=5) as response:
            answer = json.loads(response.read())
        assert "no fallback answer" in answer["answer"]
        assert answer["agent_advisory"]["status"] == "AGENT_UNAVAILABLE"
        assert answer["execution"]["available"] is False

        missing_authorization = Request(
            f"{base}/api/v1/agent-platform/diagnose",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(HTTPError) as authorization_error:
            urlopen(missing_authorization, timeout=5)
        assert authorization_error.value.code == 400
        assert json.loads(authorization_error.value.read())["error"]["code"] == (
            "diagnosis_authorization_required"
        )

        diagnosis_request = Request(
            f"{base}/api/v1/agent-platform/diagnose",
            data=b'{"operator_id":"manager-4817"}',
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(diagnosis_request, timeout=5) as response:
            diagnosis = json.loads(response.read())
        assert diagnosis["agent_run"]["state"] == "BLOCKED"
        assert diagnosis["execution"]["status"] == "WRITE_DISABLED"

        unsafe_request = Request(
            f"{base}/api/v1/agent-platform/diagnose",
            data=b'{"command":"execute"}',
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(HTTPError) as unsafe_error:
            urlopen(unsafe_request, timeout=5)
        assert unsafe_error.value.code == 400
        assert json.loads(unsafe_error.value.read())["error"]["code"] == "unexpected_payload"

        write_request = Request(
            f"{base}/api/v1/agent-platform/execute",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(HTTPError) as write_error:
            urlopen(write_request, timeout=5)
        assert write_error.value.code == 400
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
