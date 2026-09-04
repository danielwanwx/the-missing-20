from __future__ import annotations

import json
import threading
from pathlib import Path
from urllib.request import Request, urlopen

import pytest

from scripts.decision_workspace_server import DecisionWorkspaceServer
from the_missing_20.adapters.ambiguous_case_platform import AmbiguousCasePlatform
from the_missing_20.domain.ambiguous_receipt import QualityDisposition, primary_case

ROOT = Path(__file__).resolve().parents[1]


def test_primary_case_runs_from_agent_diagnosis_to_idempotent_verified_recovery() -> None:
    platform = AmbiguousCasePlatform()

    diagnosis = platform.diagnose()
    assert diagnosis["agent_run"]["state"] == "PLAN_READY"
    assert diagnosis["diagnosis"]["finding"] == "AMBIGUOUS_RECEIPT_RESOLVED"
    assert diagnosis["diagnosis"]["tool_calls"][-1] == {
        "tool": "read_collaboration_evidence",
        "status": "COMPLETE",
    }

    approved = platform.approve("manager-4817")
    approval_id = approved["execution"]["approval_id"]
    executing = platform.execute(str(approval_id), "m20-4817-recovery-v1")
    assert executing["execution"]["status"] == "VERIFYING"
    assert executing["demo_case"]["case"]["quantities"] == {
        "physically_arrived": 100,
        "available": 100,
        "quality_hold": 0,
        "receipt_unresolved": 0,
    }

    verified = platform.verify()
    assert verified["execution"]["status"] == "VERIFIED"
    assert verified["diagnosis"]["finding"] == "RECOVERY_VERIFIED"
    assert verified["demo_case"]["case"]["invoice_held"] is False

    replay = platform.execute(str(approval_id), "m20-4817-recovery-v1")
    assert replay["latest_sequence"] == verified["latest_sequence"]


def test_existing_business_key_cannot_be_retried() -> None:
    platform = AmbiguousCasePlatform(
        primary_case().model_copy(update={"erp_receipt_key_found": True})
    )

    projection = platform.diagnose()

    assert projection["agent_run"]["state"] == "BLOCKED"
    assert projection["diagnosis"]["finding"] == "EFFECT_ALREADY_PRESENT"
    with pytest.raises(ValueError, match="requires a current recovery-ready"):
        platform.approve("manager-4817")


def test_nonapproved_quality_evidence_stops_before_approval() -> None:
    platform = AmbiguousCasePlatform(
        primary_case().model_copy(update={"quality_disposition": QualityDisposition.REJECTED})
    )

    projection = platform.diagnose()

    assert projection["agent_run"]["state"] == "BLOCKED"
    assert projection["diagnosis"]["finding"] == "QUALITY_EVIDENCE_INELIGIBLE"
    assert projection["demo_case"]["case"]["invoice_held"] is True


def test_local_http_flow_reaches_verified_recovery(tmp_path: Path) -> None:
    try:
        server = DecisionWorkspaceServer(
            ("127.0.0.1", 0), ROOT, runtime_directory=tmp_path / "runtime"
        )
    except PermissionError:
        pytest.skip("the managed test sandbox disallows loopback sockets")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}/api/v1/agent-platform"

    def post(path: str, payload: dict[str, str]) -> dict[str, object]:
        request = Request(
            f"{base}/{path}",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=5) as response:
            return json.loads(response.read())

    try:
        diagnosis = post("diagnose", {})
        assert diagnosis["agent_run"]["state"] == "PLAN_READY"
        approved = post("approve", {"manager_id": "manager-4817"})
        approval_id = approved["execution"]["approval_id"]
        execution = post(
            "execute",
            {"approval_id": str(approval_id), "idempotency_key": "m20-http-recovery-v1"},
        )
        assert execution["execution"]["status"] == "VERIFYING"
        verified = post("verify", {})
        assert verified["execution"]["status"] == "VERIFIED"
        assert verified["demo_case"]["case"]["quantities"]["available"] == 100
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
