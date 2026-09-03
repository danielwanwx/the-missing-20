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


def _erp(*, status: str = "CONNECTED", quality_hold: bool = True) -> dict[str, object]:
    return {
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
            {"kind": "purchase_order", "name": "PUR-ORD-2026-00011"},
            {
                "kind": "purchase_receipt",
                "name": "MAT-PRE-2026-00001",
                "status": "PARTIAL_QUALITY_HOLD" if quality_hold else "RECEIVED",
                "rejected": 8 if quality_hold else 0,
            },
            {"kind": "purchase_invoice", "name": "ACC-PINV-2026-00007"},
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
        "jira_slack",
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
        "BLOCKED",
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
        assert "writes are disabled" in answer["answer"]
        assert answer["execution"]["available"] is False

        diagnosis_request = Request(
            f"{base}/api/v1/agent-platform/diagnose",
            data=b"{}",
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
