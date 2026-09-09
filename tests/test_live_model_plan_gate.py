"""A real-model request cannot expose an offline candidate as an approved plan."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from the_missing_20.adapters.agent_platform import AgentPlatform


class Reader:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def current(self) -> dict[str, Any]:
        return deepcopy(self.payload)


def platform_for_test(state_path: Path | None = None) -> tuple[AgentPlatform, Reader, Reader]:
    erp = Reader(
        {
            "sequence": 1,
            "status": "CONNECTED",
            "case_id": "CASE-20",
            "documents": [
                {"kind": "purchase_order", "name": "PO-20", "quantity": 20},
                {
                    "kind": "purchase_receipt",
                    "name": "PR-20",
                    "status": "PARTIAL_QUALITY_HOLD",
                    "received": 20,
                    "accepted": 12,
                    "rejected": 8,
                },
                {"kind": "purchase_invoice", "name": "PI-20", "status": "PAYMENT_HOLD"},
            ],
        }
    )
    saas = Reader(
        {
            "sequence": 1,
            "status": "CONNECTED",
            "correlation_id": "CASE-20",
            "sources": [
                {
                    "source_id": "airtable-quality-registry",
                    "status": "VERIFIED",
                    "record_id": "rec-20",
                    "provider": "Airtable",
                    "correlation": {
                        "case_id": "CASE-20",
                        "purchase_order": "PO-20",
                        "purchase_receipt": "PR-20",
                        "purchase_invoice": "PI-20",
                        "quantity": 8,
                        "supplier_lot": "LOT-20",
                        "certificate_id": "CERT-20",
                        "evidence_revision": "rev-1",
                    },
                }
            ],
        }
    )
    return AgentPlatform(erp, saas, executor=object(), state_path=state_path), erp, saas  # type: ignore[arg-type]


def ready_advisory() -> dict[str, Any]:
    return {
        "status": "COMPLETE",
        "tool_calls": ["read_erp_evidence", "reconcile_source_records"],
        "evidence_findings": {
            "evidence_ids": ["PR-20"],
            "policy": {"disposition": "RECOVERY_READY", "manager_approval_required": True},
        },
        "result": {
            "disposition": "RECOVERY_READY",
            "write_performed": False,
            "reason": "Eight units are held; the exact lot is approved for manager review.",
        },
    }


def claimed(platform: AgentPlatform) -> str:
    projection, started = platform.claim_diagnosis()
    assert started is True
    assert projection["agent_run"]["state"] == "REASONING"  # type: ignore[index]
    assert projection["execution"]["available"] is False  # type: ignore[index]
    return str(projection["agent_run"]["run_id"])  # type: ignore[index]


def test_live_platform_persists_only_current_run_task_events(tmp_path: Path) -> None:
    platform, _, _ = platform_for_test(tmp_path / "platform.json")
    run_id = claimed(platform)
    event = {"type": "task.started", "role": "inventory", "task_id": "TASK-1"}
    assert platform.agent_run_is_active(run_id)
    platform.record_agent_runtime_progress(event, run_id)
    assert any(e["record_id"] == "TASK-1" for e in platform.events_since())
    platform.stop()
    sequence = len(platform.events_since())
    platform.record_agent_runtime_progress({**event, "type": "task.completed"}, run_id)
    assert not platform.agent_run_is_active(run_id)
    assert len(platform.events_since()) == sequence
    saved = json.loads((tmp_path / "platform.json").read_text())
    assert any(e["record_id"] == "TASK-1" for e in saved["events"])


def assert_blocked(platform: AgentPlatform) -> None:
    current = platform.current()
    assert current["agent_run"]["state"] == "BLOCKED"  # type: ignore[index]
    assert current["execution"]["available"] is False  # type: ignore[index]
    with pytest.raises(ValueError, match="fresh verified plan"):
        platform.approve("Manager")


def test_pending_live_model_never_releases_plan_and_duplicate_claim_is_idempotent() -> None:
    platform, _, _ = platform_for_test()
    run_id = claimed(platform)
    with pytest.raises(ValueError, match="fresh verified plan"):
        platform.approve("Manager")
    repeated, started = platform.claim_diagnosis()
    assert started is False
    assert repeated["agent_run"]["run_id"] == run_id  # type: ignore[index]
    assert repeated["human_review"]["status"] != "MANAGER_REVIEW_REQUIRED"  # type: ignore[index]
    activity = repeated["activity"]
    assert isinstance(activity, list)
    assert not any(row["event_type"] == "agent.diagnosis.completed" for row in activity)


@pytest.mark.parametrize("status", ["AGENT_UNAVAILABLE", "VALIDATION_FAILED", "ERROR", ""])
def test_failed_model_blocks_candidate_and_allows_a_new_run(status: str) -> None:
    platform, _, _ = platform_for_test()
    run_id = claimed(platform)
    platform.record_live_strands_investigation({"status": status}, run_id=run_id)
    assert_blocked(platform)
    assert claimed(platform) != run_id


@pytest.mark.parametrize(
    "change", ["missing_policy", "deny_policy", "deny_result", "write", "missing_write", "empty"]
)
def test_complete_transport_does_not_imply_a_validated_recovery_plan(change: str) -> None:
    platform, _, _ = platform_for_test()
    run_id = claimed(platform)
    advisory = ready_advisory()
    if change == "missing_policy":
        advisory["evidence_findings"].pop("policy")
    elif change == "deny_policy":
        advisory["evidence_findings"]["policy"]["disposition"] = "DENY"
    elif change == "deny_result":
        advisory["result"]["disposition"] = "NEEDS_EVIDENCE"
    elif change == "write":
        advisory["result"]["write_performed"] = True
    elif change == "missing_write":
        advisory["result"].pop("write_performed")
    else:
        advisory = {"status": "COMPLETE"}
    platform.record_live_strands_investigation(advisory, run_id=run_id)
    assert_blocked(platform)


def test_validated_current_model_can_only_prepare_a_manager_gated_plan() -> None:
    platform, _, _ = platform_for_test()
    run_id = claimed(platform)
    current = platform.record_live_strands_investigation(ready_advisory(), run_id=run_id)
    assert current["agent_run"]["state"] == "PLAN_READY"  # type: ignore[index]
    assert current["execution"]["status"] == "AWAITING_MANAGER_APPROVAL"  # type: ignore[index]
    approved = platform.approve("Manager")
    assert approved["execution"]["status"] == "AUTHORIZED"  # type: ignore[index]
    assert approved["resolution_packet"] is None
    # A duplicate response, even an error, cannot revoke or change the settled run.
    settled = platform.record_live_strands_investigation({"status": "ERROR"}, run_id=run_id)
    assert settled["execution"]["status"] == "AUTHORIZED"  # type: ignore[index]


def test_stop_and_retry_ignore_late_callbacks_without_releasing_old_approval() -> None:
    platform, _, _ = platform_for_test()
    old_run = claimed(platform)
    platform.stop()
    stopped = platform.record_live_strands_investigation(ready_advisory(), run_id=old_run)
    assert stopped["agent_run"]["state"] == "STOPPED"  # type: ignore[index]
    new_run = claimed(platform)
    platform.record_live_strands_investigation(ready_advisory(), run_id=old_run)
    assert platform.current()["agent_run"]["state"] == "REASONING"  # type: ignore[index]
    platform.record_live_strands_investigation(ready_advisory(), run_id=new_run)
    platform.approve("Manager")
    third_run = claimed(platform)
    assert third_run not in {old_run, new_run}
    assert platform.current()["execution"]["status"] != "AUTHORIZED"  # type: ignore[index]


def test_tokenless_completion_cannot_bypass_a_live_claim() -> None:
    platform, _, _ = platform_for_test()
    claimed(platform)
    platform.record_strands_investigation(ready_advisory())
    assert platform.current()["agent_run"]["state"] == "REASONING"  # type: ignore[index]


def test_tokenless_completion_cannot_revive_a_failed_live_claim() -> None:
    platform, _, _ = platform_for_test()
    run_id = claimed(platform)
    platform.record_live_strands_investigation({"status": "AGENT_UNAVAILABLE"}, run_id=run_id)
    platform.record_strands_investigation(ready_advisory())
    assert_blocked(platform)


def test_source_drift_after_model_completion_cannot_be_approved() -> None:
    platform, erp, _ = platform_for_test()
    run_id = claimed(platform)
    platform.record_live_strands_investigation(ready_advisory(), run_id=run_id)
    erp.payload["documents"][1]["accepted"] = 11
    with pytest.raises(ValueError, match="fresh verified plan"):
        platform.approve("Manager")


@pytest.mark.parametrize("change", ["quantity", "outage", "correlation"])
def test_current_refresh_revokes_stale_visible_live_plan_and_approval(change: str) -> None:
    platform, erp, saas = platform_for_test()
    run_id = claimed(platform)
    platform.record_live_strands_investigation(ready_advisory(), run_id=run_id)
    platform.approve("Manager")
    if change == "quantity":
        erp.payload["documents"][1]["accepted"] = 11
    elif change == "outage":
        erp.payload["status"] = "DEGRADED"
    else:
        saas.payload["sources"][0]["correlation"]["purchase_order"] = "OTHER-PO"
    assert_blocked(platform)
    first = platform.current()
    second = platform.current()
    assert first["execution"]["status"] != "AUTHORIZED"  # type: ignore[index]
    assert first["human_review"]["status"] != "MANAGER_REVIEW_REQUIRED"  # type: ignore[index]
    assert first["latest_sequence"] == second["latest_sequence"]


def test_refresh_keeps_the_explicit_offline_diagnose_contract() -> None:
    platform, erp, _ = platform_for_test()
    platform.diagnose()
    erp.payload["documents"][1]["accepted"] = 11
    assert platform.current()["agent_run"]["state"] == "PLAN_READY"  # type: ignore[index]


@pytest.mark.parametrize("change", ["quantity", "status", "revision", "ledger"])
def test_source_drift_or_outage_requires_reinvestigation(change: str) -> None:
    platform, erp, saas = platform_for_test()
    run_id = claimed(platform)
    if change == "quantity":
        erp.payload["documents"][1]["accepted"] = 13
    elif change == "status":
        erp.payload["status"] = "DEGRADED"
    elif change == "revision":
        saas.payload["sources"][0]["correlation"]["evidence_revision"] = "rev-2"
    else:
        erp.payload["ledger_evidence"] = {"status": "CONNECTED", "stock_entries": [{"qty": 7}]}
    platform.record_live_strands_investigation(ready_advisory(), run_id=run_id)
    assert_blocked(platform)


def test_polls_do_not_invalidate_the_model_source_binding() -> None:
    platform, erp, saas = platform_for_test()
    run_id = claimed(platform)
    for reader in (erp, saas):
        reader.payload.update({"received_at": "2026-09-08T23:59:00+00:00", "sequence": 9})
    current = platform.record_live_strands_investigation(ready_advisory(), run_id=run_id)
    assert current["agent_run"]["state"] == "PLAN_READY"  # type: ignore[index]


@pytest.mark.parametrize("stop_first", [False, True])
def test_restart_never_resumes_a_pending_model_or_reverses_human_stop(
    tmp_path: Path, stop_first: bool
) -> None:
    path = tmp_path / "state.json"
    platform, erp, saas = platform_for_test(path)
    old_run = claimed(platform)
    if stop_first:
        platform.stop()
    restarted = AgentPlatform(erp, saas, executor=object(), state_path=path)  # type: ignore[arg-type]
    stale = restarted.record_live_strands_investigation(ready_advisory(), run_id=old_run)
    assert stale["agent_run"]["state"] == ("STOPPED" if stop_first else "BLOCKED")  # type: ignore[index]
    assert claimed(restarted) != old_run


def test_persisted_legacy_plan_is_not_model_completion_proof(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text(
        json.dumps(
            {
                "run_number": 2,
                "agent_run": {"state": "PLAN_READY", "run_id": "agent-run-0002"},
                "approval": {"approval_id": "old", "plan_digest": "legacy"},
            }
        )
    )
    platform, _, _ = platform_for_test(path)
    assert_blocked(platform)
    assert platform.current()["execution"]["status"] != "AUTHORIZED"  # type: ignore[index]


def test_offline_compatibility_does_not_preserve_plan_after_real_model_failure() -> None:
    platform, _, _ = platform_for_test()
    assert platform.diagnose()["agent_run"]["state"] == "PLAN_READY"  # type: ignore[index]
    platform.approve("Manager")
    platform.record_strands_investigation({"status": "AGENT_UNAVAILABLE"})
    assert_blocked(platform)


def test_model_cannot_override_deterministic_correlation_block() -> None:
    platform, _, saas = platform_for_test()
    saas.payload["sources"][0]["correlation"]["purchase_order"] = "OTHER-PO"
    run_id = claimed(platform)
    platform.record_live_strands_investigation(ready_advisory(), run_id=run_id)
    assert_blocked(platform)
