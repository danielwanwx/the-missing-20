from __future__ import annotations

import json
import threading
from collections.abc import Mapping
from pathlib import Path
from urllib.request import Request, urlopen

import pytest

from scripts.decision_workspace_server import DecisionWorkspaceServer
from the_missing_20.adapters.ambiguous_case_platform import AmbiguousCasePlatform
from the_missing_20.adapters.case_console_store import CaseConsoleStore
from the_missing_20.adapters.live_advisory_gateway import DashboardAdvisoryGateway
from the_missing_20.domain.ambiguous_receipt import (
    AmbiguousReceiptCase,
    QualityDisposition,
    primary_case,
)

ROOT = Path(__file__).resolve().parents[1]


def test_specialist_event_and_stop_are_fenced_and_traceable(tmp_path: Path) -> None:
    platform = AmbiguousCasePlatform(store_path=tmp_path / "case.sqlite3")
    platform.authorize_diagnosis("manager")
    projection, claimed = platform.claim_diagnosis()
    assert claimed
    run_id = str(projection["agent_run"]["run_id"])
    assert platform.agent_run_is_active(run_id)
    event = {"type": "task.completed", "role": "inventory", "task_id": "TASK-1"}
    barrier = threading.Barrier(2)

    def complete() -> None:
        barrier.wait(timeout=2)
        platform.record_agent_runtime_progress(event, run_id)

    worker = threading.Thread(target=complete)
    worker.start()
    barrier.wait(timeout=2)
    platform.stop()
    worker.join(timeout=2)
    assert not worker.is_alive()
    platform.record_agent_runtime_progress(event, run_id)
    events = platform.events_since()
    paused = next(e["sequence"] for e in events if e["event_type"] == "human.investigation.paused")
    task_events = [e for e in events if e["event_type"] == "agent.task.completed"]
    assert all(e["sequence"] < paused and e["task"]["task_id"] == "TASK-1" for e in task_events)
    assert not platform.agent_run_is_active(run_id)


def test_failed_specialist_tool_is_not_projected_as_another_start() -> None:
    platform = AmbiguousCasePlatform()
    platform.authorize_diagnosis("manager")
    projection, claimed = platform.claim_diagnosis()
    assert claimed
    platform.record_agent_tool_progress(
        "consult_quality", "failed", str(projection["agent_run"]["run_id"])
    )
    event = platform.events_since()[-1]
    assert event["event_type"] == "agent.strands.tool.failed"
    assert event["status"] == "FAILED"
    assert event["label"] == "Quality specialist"


def test_primary_case_runs_from_agent_diagnosis_to_idempotent_verified_recovery() -> None:
    platform = AmbiguousCasePlatform()

    initial = platform.current()
    assert initial["agent_run"]["state"] == "IDLE"
    assert initial["evidence_constellation"]["conclusion"]["label"] == "NO RELEASE"
    assert initial["evidence_constellation"]["conclusion"]["confidence"] == 0.0
    assert {system["id"] for system in initial["systems"]} == {
        "erpnext",
        "airtable",
        "celigo",
        "jira",
        "slack",
    }
    assert {node["id"] for node in initial["evidence_constellation"]["nodes"]} == {
        "erpnext",
        "airtable",
        "celigo",
        "jira",
        "slack",
    }
    assert initial["human_review"] == {
        "status": "HUMAN_DIAGNOSIS_REQUIRED",
        "required": True,
        "action": "AUTHORIZE_DIAGNOSIS",
        "reason": "Question the evidence Agent first or authorize a bounded read-only diagnosis.",
        "can_stop": False,
    }
    assert all("metrics" in event for event in initial["activity"])
    assert initial["judge_proof"]["autonomous_until_review"] is False
    assert initial["judge_proof"]["diagnosis_authorized"] is False
    assert initial["judge_proof"]["evidence_records"] == 15
    assert initial["business_impact"] == {
        "currency": "USD",
        "po_unit_cost": 50.0,
        "invoice_unit_price": 50.0,
        "po_line_value": 5000.0,
        "invoice_value": 5000.0,
        "available_inventory_value": 4000.0,
        "invoice_hold_value": 5000.0,
        "working_capital_at_risk": 1000.0,
        "quality_hold_value": 400.0,
        "receipt_gap_value": 600.0,
        "purchase_price_variance": 0.0,
        "invoice_price_delta_percent": 0.0,
        "inventory_availability_percent": 80.0,
        "erp_reconciliation_percent": 88.0,
        "quality_hold_percent": 8.0,
        "receipt_gap_percent": 12.0,
        "supplier_delivery_completion_percent": 100.0,
        "value_protected": 0.0,
        "supplier_status": "ACTIVE",
        "supplier_payment_hold": False,
        "invoice_status": "HELD",
        "basis": "current admitted PO, receipt, quality, supplier, and invoice records",
        "provenance": "synthetic-demo-fixture",
    }
    assert initial["activity"][-1]["metrics"]["working_capital_at_risk"] == 1000.0
    operations = initial["connected_operations"]
    assert operations["window"]["days"] == 90
    assert len(operations["history"]) == 90
    assert operations["risk_signal"]["band"] == "CRITICAL"
    assert operations["risk_signal"]["score"] >= 75
    assert operations["current_shift"]["component_starved_units"] == 20
    assert operations["current_shift"]["schedule_attainment_percent"] == 83.3
    assert operations["customer_commitments"]["units_at_risk"] == 20
    assert operations["customer_commitments"]["revenue_at_risk"] == 900000.0
    assert operations["customer_commitments"]["contribution_margin_at_risk"] == 130000.0
    assert operations["supplier_performance"]["inbound_otif_percent_90d"] == 94.4
    assert operations["inventory"]["days_of_supply"] == 3.3
    assert initial["activity"][-1]["metrics"]["operational_risk_score"] >= 75

    diagnosis = platform.diagnose()
    assert diagnosis["agent_run"]["state"] == "PLAN_READY"
    assert diagnosis["diagnosis"]["finding"] == "AMBIGUOUS_RECEIPT_RESOLVED"
    assert diagnosis["diagnosis"]["tool_calls"][-1] == {
        "tool": "read_collaboration_evidence",
        "status": "COMPLETE",
    }
    assert {row["id"]: row["status"] for row in diagnosis["diagnosis"]["hypotheses"]} == {
        "missing_erp_receipt": "SUPPORTED",
        "duplicate_post": "ELIMINATED",
        "physical_shortage": "ELIMINATED",
        "quality_not_approved": "ELIMINATED",
    }

    approved = platform.approve("manager-4817")
    approval_id = approved["execution"]["approval_id"]
    executing = platform.execute(str(approval_id), "m20-4817-recovery-v1")
    assert executing["execution"]["status"] == "VERIFYING"
    assert executing["evidence_constellation"]["conclusion"]["label"] == "VERIFYING RECOVERY"
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
    assert verified["connected_operations"]["risk_signal"]["band"] == "NORMAL"
    assert verified["connected_operations"]["risk_signal"]["score"] == 0.0
    assert verified["connected_operations"]["current_shift"]["component_starved_units"] == 0
    assert verified["connected_operations"]["customer_commitments"]["revenue_at_risk"] == 0.0
    packet = verified["resolution_packet"]
    assert packet["packet_id"] == "resolution-m20-4817"
    assert packet["approval"]["manager_id"] == "manager-4817"
    assert packet["pre_state"]["available"] == 80
    assert packet["post_state"]["available"] == 100
    assert packet["case_tuple"]["receipt_post_quantity"] == 12
    assert packet["case_tuple"]["quality_transfer_quantity"] == 8
    assert packet["execution"]["idempotency_key"] == "m20-4817-recovery-v1"
    assert packet["policy"]["authority"] == "DETERMINISTIC_CONTROL_PLANE"
    assert all(packet["timestamps"].values())
    assert verified["activity"][-1]["event_type"] == "agent.resolution_packet.issued"
    assert verified["activity"][-1]["read_only"] is True
    assert verified["business_impact"]["working_capital_at_risk"] == 0.0
    assert verified["business_impact"]["invoice_hold_value"] == 0.0
    assert verified["business_impact"]["value_protected"] == 1000.0

    replay = platform.execute(str(approval_id), "m20-4817-recovery-v1")
    assert replay["latest_sequence"] == verified["latest_sequence"]


def test_http_diagnosis_claim_requires_and_records_human_authorization() -> None:
    platform = AmbiguousCasePlatform()

    with pytest.raises(ValueError, match="human authorization"):
        platform.claim_diagnosis()

    authorized = platform.authorize_diagnosis("operator-4817")
    assert authorized["diagnosis_authorization"]["operator_id"] == "operator-4817"
    assert authorized["diagnosis_authorization"]["scope"] == ("READ_ONLY_CROSS_SYSTEM_DIAGNOSIS")
    assert authorized["judge_proof"]["diagnosis_authorized"] is True
    assert authorized["activity"][-1]["event_type"] == "human.diagnosis.authorized"

    _, started = platform.claim_diagnosis()
    assert started is True


def test_reset_opens_a_fresh_case_and_preserves_source_snapshot_time() -> None:
    platform = AmbiguousCasePlatform()
    initial = platform.current()
    observed_at = initial["judge_proof"]["evidence_observed_at"]
    assert platform.current()["judge_proof"]["evidence_observed_at"] == observed_at

    platform.diagnose()
    approval_id = str(platform.approve("manager")["execution"]["approval_id"])
    platform.execute(approval_id, "reset-proof")
    platform.verify()

    reset = platform.reset()
    assert reset["agent_run"]["state"] == "IDLE"
    assert reset["execution"]["status"] == "WAITING_FOR_INVESTIGATION"
    assert reset["demo_case"]["case"]["quantities"]["available"] == 80
    assert reset["latest_sequence"] == 4
    assert all(event["run_id"] == "" for event in reset["activity"])


def test_legacy_resolution_does_not_invent_missing_before_state(tmp_path: Path) -> None:
    store_path = tmp_path / "legacy.sqlite3"
    platform = AmbiguousCasePlatform(store_path=store_path)
    platform.diagnose()
    approval_id = str(platform.approve("manager")["execution"]["approval_id"])
    platform.execute(approval_id, "legacy-recovery")
    platform.verify()
    store = CaseConsoleStore(store_path)
    snapshot = store.load(primary_case().case_id)
    assert snapshot is not None
    snapshot.pop("pre_execution_case")
    store.save(primary_case().case_id, snapshot)
    restored = AmbiguousCasePlatform(store_path=store_path).current()
    assert restored["resolution_packet"]["pre_state"] is None
    assert restored["resolution_packet"]["post_state"]["available"] == 100


def test_existing_business_key_cannot_be_retried() -> None:
    platform = AmbiguousCasePlatform(
        primary_case().model_copy(update={"erp_receipt_key_found": True})
    )

    projection = platform.diagnose()

    assert projection["agent_run"]["state"] == "BLOCKED"
    assert projection["diagnosis"]["finding"] == "EFFECT_ALREADY_PRESENT"
    with pytest.raises(ValueError, match="requires a current recovery-ready"):
        platform.approve("manager-4817")


@pytest.mark.parametrize(
    ("variant", "finding"),
    [
        ("already-posted", "EFFECT_ALREADY_PRESENT"),
        ("quality-rejected", "QUALITY_EVIDENCE_INELIGIBLE"),
        ("lost_ack", "EFFECT_ALREADY_PRESENT"),
        ("wrong_quality_lot", "QUALITY_EVIDENCE_INELIGIBLE"),
        ("lookup_unavailable", "NEEDS_ERP_KEY_REREAD"),
        ("physical_shortage", "PHYSICAL_SHORTAGE_CONFIRMED"),
        ("transfer_already_present", "EFFECT_ALREADY_PRESENT"),
        ("evidence_conflict", "CROSS_SOURCE_QUANTITY_CONFLICT"),
        ("duplicate_invoice", "DUPLICATE_SUPPLIER_INVOICE"),
        ("unit_price_variance", "COMMERCIAL_TERMS_MISMATCH"),
        ("uom_conversion_missing", "UOM_CONVERSION_EVIDENCE_REQUIRED"),
        ("po_revision_race", "PO_REVISION_EVIDENCE_REQUIRED"),
        ("supplier_hold", "SUPPLIER_COMPLIANCE_HOLD"),
        ("lot_trace_mismatch", "LOT_TRACE_MISMATCH"),
    ],
)
def test_counterfactual_same_alert_stops_without_a_write(variant: str, finding: str) -> None:
    platform = AmbiguousCasePlatform()

    platform.reset_variant(variant)
    projection = platform.diagnose()

    assert projection["agent_run"]["state"] == "BLOCKED"
    assert projection["diagnosis"]["finding"] == finding
    assert projection["human_review"]["required"] is False
    assert projection["human_review"]["status"] == "SAFE_STOP"
    assert projection["execution"]["available"] is False
    assert projection["execution"]["status"] == "SAFE_STOP"
    assert projection["resolution_packet"] is None


def test_case_catalog_exposes_reusable_hidden_cause_matrix() -> None:
    projection = AmbiguousCasePlatform().current()

    assert projection["scenario"]["variant"] == "uncommitted_receipt"
    catalog = projection["scenario"]["catalog"]
    assert len(catalog) == 14
    assert {item["expected_control"] for item in catalog} >= {
        "MANAGER_REVIEW",
        "SAFE_NOOP",
        "HARD_STOP",
        "REQUEST_EVIDENCE",
        "PROTECT",
    }
    assert projection["framework"]["validation_harness"]["case_families"] == 14


def test_manager_can_reject_a_ready_plan_without_any_effect() -> None:
    platform = AmbiguousCasePlatform()
    platform.diagnose()

    rejected = platform.reject_plan("manager-4817", "Supplier owner requested manual review")

    assert rejected["agent_run"]["state"] == "BLOCKED"
    assert rejected["diagnosis"]["finding"] == "HUMAN_REJECTED_PLAN"
    assert rejected["human_decision"]["status"] == "REJECTED"
    assert rejected["human_decision"]["manager_id"] == "manager-4817"
    assert rejected["execution"]["available"] is False
    assert rejected["resolution_packet"] is None
    assert rejected["activity"][-1]["event_type"] == "manager.plan.rejected"


def test_normal_complete_counterfactual_requires_no_human_or_effect() -> None:
    platform = AmbiguousCasePlatform()

    platform.reset_variant("normal_complete")
    projection = platform.diagnose()

    assert projection["agent_run"]["state"] == "RECOVERY_COMPLETE"
    assert projection["human_review"]["required"] is False
    assert projection["execution"]["status"] == "NO_ACTION_REQUIRED"


@pytest.mark.parametrize("available,hold,unresolved", [(90, 4, 6), (180, 7, 13)])
def test_resolution_preserves_actual_before_state_across_restart_and_replay(
    tmp_path: Path, available: int, hold: int, unresolved: int
) -> None:
    case = AmbiguousReceiptCase.model_validate(
        {
            **primary_case().model_dump(),
            "physically_arrived": available + hold + unresolved,
            "available_quantity": available,
            "quality_hold_quantity": hold,
            "receipt_unresolved_quantity": unresolved,
        }
    )
    store_path = tmp_path / "case.sqlite3"
    platform = AmbiguousCasePlatform(case, store_path=store_path)
    platform.diagnose()
    approval_id = str(platform.approve("manager")["execution"]["approval_id"])
    platform.execute(approval_id, "recovery")
    restored = AmbiguousCasePlatform(case, store_path=store_path)
    verified = restored.verify()
    packet = verified["resolution_packet"]
    assert packet["pre_state"] == {
        "available": available,
        "quality_hold": hold,
        "receipt_unresolved": unresolved,
        "invoice_held": True,
    }
    assert packet["post_state"]["available"] == available + hold + unresolved
    replay = AmbiguousCasePlatform(case, store_path=store_path).execute(approval_id, "recovery")
    assert replay["resolution_packet"] == packet
    assert replay["latest_sequence"] == verified["latest_sequence"]


def test_nonapproved_quality_evidence_stops_before_approval() -> None:
    platform = AmbiguousCasePlatform(
        primary_case().model_copy(update={"quality_disposition": QualityDisposition.REJECTED})
    )

    projection = platform.diagnose()

    assert projection["agent_run"]["state"] == "BLOCKED"
    assert projection["diagnosis"]["finding"] == "QUALITY_EVIDENCE_INELIGIBLE"
    assert projection["demo_case"]["case"]["invoice_held"] is True
    assert projection["human_review"]["status"] == "SAFE_STOP"
    assert projection["resolution_packet"] is None


def test_operator_can_pause_and_resume_a_read_only_investigation() -> None:
    platform = AmbiguousCasePlatform()
    platform.diagnose()

    paused = platform.stop()
    assert paused["agent_run"]["state"] == "STOPPED"
    assert paused["human_review"]["action"] == "RESUME_INVESTIGATION"
    assert paused["activity"][-1]["event_type"] == "human.investigation.paused"

    resumed = platform.diagnose()
    assert resumed["agent_run"]["state"] == "PLAN_READY"


def test_case_console_restores_manager_state_and_event_cursor(tmp_path: Path) -> None:
    store_path = tmp_path / "case-console.sqlite3"
    first = AmbiguousCasePlatform(store_path=store_path)
    first.diagnose()
    approved = first.approve("manager-4817")
    cursor = approved["latest_sequence"]

    restored = AmbiguousCasePlatform(store_path=store_path)

    restored_execution = restored.current()["execution"]
    assert str(restored_execution["approval_id"]).startswith("m20-approval-")
    assert restored_execution["plan_digest"]
    assert restored_execution["case_version"] == 1
    assert restored_execution["demo_tenant"] == "missing-20-synthetic-tenant"
    assert restored.current()["latest_sequence"] == cursor
    assert restored.events_since(int(cursor) - 1)[0]["event_type"] == "manager.approval.granted"


def test_durable_event_ledger_is_append_only_and_reset_replaces_the_run(tmp_path: Path) -> None:
    store_path = tmp_path / "append-only.sqlite3"
    platform = AmbiguousCasePlatform(store_path=store_path)
    platform.diagnose()
    assert len(platform.events_since(0)) > 4

    reset = platform.reset()
    persisted = CaseConsoleStore(store_path).load(primary_case().case_id)

    assert persisted is not None
    assert len(persisted["events"]) == 4
    assert [event["sequence"] for event in persisted["events"]] == [1, 2, 3, 4]
    assert reset["latest_sequence"] == 4


def test_local_http_flow_reaches_verified_recovery(tmp_path: Path) -> None:
    class SuccessfulAdvisoryDouble(DashboardAdvisoryGateway):
        def investigate(self, projection: Mapping[str, object]) -> dict[str, object]:
            run = projection["agent_run"]
            assert isinstance(run, Mapping)
            return {
                "status": "COMPLETE",
                "run_id": run["run_id"],
                "mode": "test_double",
                "provider": {"provider": "test_double"},
                "tool_calls": [],
                "runtime_events": [],
                "result": {"disposition": "RECOVERY_READY", "write_performed": False},
            }

    platform = AmbiguousCasePlatform(store_path=tmp_path / "case-console.sqlite3")
    try:
        server = DecisionWorkspaceServer(
            ("127.0.0.1", 0),
            ROOT,
            runtime_directory=tmp_path / "runtime",
            agent_platform=platform,
            agent_advisory=SuccessfulAdvisoryDouble(platform),
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
        diagnosis = post("diagnose", {"operator_id": "manager-4817"})
        assert diagnosis["agent_run"]["state"] == "PLAN_READY"
        assert diagnosis["diagnosis"]["strands_investigation"]["mode"] == "test_double"
        verified = post(
            "approve-and-execute",
            {"manager_id": "manager-4817", "idempotency_key": "m20-http-recovery-v1"},
        )
        assert verified["execution"]["status"] == "VERIFIED"
        assert verified["demo_case"]["case"]["quantities"]["available"] == 100
        assert verified["resolution_packet"]["execution"]["approval_id"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_http_diagnose_is_idempotent_for_one_paid_agent_run(tmp_path: Path) -> None:
    class AdvisoryProbe:
        def __init__(self) -> None:
            self.calls = 0

        def investigate(self, projection):
            self.calls += 1
            return {
                "status": "COMPLETE",
                "run_id": projection["agent_run"]["run_id"],
                "tool_calls": [],
                "runtime_events": [],
                "result": {"disposition": "RECOVERY_READY"},
            }

    platform = AmbiguousCasePlatform(store_path=tmp_path / "case-console.sqlite3")
    advisory = AdvisoryProbe()
    try:
        server = DecisionWorkspaceServer(
            ("127.0.0.1", 0),
            ROOT,
            runtime_directory=tmp_path / "runtime",
            agent_platform=platform,
            agent_advisory=advisory,  # type: ignore[arg-type]
        )
    except PermissionError:
        pytest.skip("the managed test sandbox disallows loopback sockets")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    endpoint = f"http://127.0.0.1:{server.server_port}/api/v1/agent-platform/diagnose"

    def post() -> dict[str, object]:
        request = Request(
            endpoint,
            data=b'{"operator_id":"manager-4817"}',
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=5) as response:
            return json.loads(response.read())

    try:
        first = post()
        second = post()
        assert first["agent_run"]["run_id"] == second["agent_run"]["run_id"]
        assert advisory.calls == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_case_console_activity_endpoint_replays_server_events(tmp_path: Path) -> None:
    try:
        server = DecisionWorkspaceServer(
            ("127.0.0.1", 0), ROOT, runtime_directory=tmp_path / "runtime"
        )
    except PermissionError:
        pytest.skip("the managed test sandbox disallows loopback sockets")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        endpoint = f"http://127.0.0.1:{server.server_port}/api/v1/agent-platform/events?after=0"
        with urlopen(endpoint, timeout=5) as response:
            first = response.readline().decode().strip()
            event = response.readline().decode().strip()
            data = response.readline().decode().strip()
        assert first == "id: 1"
        assert event == "event: case.activity"
        assert json.loads(data.removeprefix("data: "))["event_type"] == "source.warehouse.read"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_real_tool_progress_is_visible_and_completion_restores_plan_state() -> None:
    platform = AmbiguousCasePlatform()
    diagnosed = platform.diagnose()
    run_id = str(diagnosed["agent_run"]["run_id"])

    platform.record_agent_runtime_progress(
        {"type": "model.started", "projected_input_tokens": 2432}, run_id
    )
    reasoning = platform.current()
    assert reasoning["agent_run"]["state"] == "REASONING"
    assert reasoning["activity"][-1]["event_type"] == "agent.strands.model.started"
    assert "2432" in reasoning["activity"][-1]["detail"]
    assert reasoning["diagnosis"]["strands_investigation"]["status"] == "RUNNING"
    assert reasoning["diagnosis"]["strands_investigation"]["runtime_events"] == [
        {"type": "model.started", "projected_input_tokens": 2432}
    ]

    platform.record_agent_runtime_progress({"type": "model.succeeded"}, run_id)
    assert platform.current()["activity"][-1]["label"] == "Model turn complete"

    platform.record_agent_tool_progress("read_erp_evidence")
    gathering = platform.current()
    assert gathering["agent_run"]["state"] == "GATHERING"
    assert gathering["activity"][-1]["label"] == "ERPNext ledger"
    assert gathering["activity"][-1]["event_type"] == "agent.strands.tool.started"

    platform.record_agent_tool_progress("read_erp_evidence", "succeeded")
    returned = platform.current()
    assert returned["activity"][-1]["event_type"] == "agent.strands.tool.succeeded"
    assert returned["activity"][-1]["agent_state"] == "GATHERING"

    platform.record_agent_tool_progress("reconcile_source_records")
    synthesizing = platform.current()
    assert synthesizing["agent_run"]["state"] == "SYNTHESIZING"

    completed = platform.record_strands_investigation(
        {
            "status": "COMPLETE",
            "tool_calls": ["read_erp_evidence", "reconcile_source_records"],
            "runtime_events": [
                {"sequence": 1, "type": "model.started"},
                {"sequence": 2, "type": "model.succeeded", "duration_ms": 42},
            ],
            "result": {
                "disposition": "RECOVERY_READY",
                "reason": "The source records reconcile to a bounded recovery.",
            },
        }
    )
    assert completed["agent_run"]["state"] == "PLAN_READY"
    assert completed["diagnosis"]["summary"].startswith("The source records")
    assert completed["judge_proof"]["sdk_hook_events"] == 2


def test_only_one_concurrent_diagnosis_claim_can_start_a_paid_run() -> None:
    platform = AmbiguousCasePlatform()
    platform.authorize_diagnosis("operator-4817")
    barrier = threading.Barrier(3)
    outcomes: list[bool] = []

    def claim() -> None:
        barrier.wait()
        _, started = platform.claim_diagnosis()
        outcomes.append(started)

    workers = [threading.Thread(target=claim) for _ in range(2)]
    for worker in workers:
        worker.start()
    barrier.wait()
    for worker in workers:
        worker.join(timeout=2)

    assert sorted(outcomes) == [False, True]
    assert platform.current()["agent_run"]["state"] == "SYNTHESIZING"


def test_failed_real_agent_run_retracts_plan_and_fails_closed() -> None:
    platform = AmbiguousCasePlatform()
    platform.authorize_diagnosis("operator-4817")
    pending, started = platform.claim_diagnosis()

    assert started is True
    assert pending["agent_run"]["state"] == "SYNTHESIZING"
    assert pending["diagnosis"]["finding"] == "PENDING_AGENT_VALIDATION"
    assert pending["diagnosis"]["tool_calls"] == []
    assert {item["status"] for item in pending["diagnosis"]["hypotheses"]} == {"PENDING"}
    assert pending["execution"]["status"] == "INVESTIGATION_RUNNING"

    failed = platform.record_strands_investigation(
        {"status": "AGENT_UNAVAILABLE", "tool_calls": [], "result": None}
    )

    assert failed["agent_run"]["state"] == "BLOCKED"
    assert failed["diagnosis"]["finding"] == "AGENT_UNAVAILABLE"
    assert failed["agent_run"]["confidence"] == 0.0
    assert failed["execution"]["status"] == "SAFE_STOP"
    assert failed["execution"]["available"] is False
    assert failed["human_review"]["action"] == "RETRY_INVESTIGATION"
    with pytest.raises(ValueError, match="requires a current recovery-ready"):
        platform.approve("manager")


def test_physical_shortage_separates_ordered_from_scanned_quantity() -> None:
    platform = AmbiguousCasePlatform()

    projection = platform.reset_variant("physical_shortage")

    quantities = projection["demo_case"]["case"]["quantities"]
    assert quantities == {
        "physically_arrived": 80,
        "available": 72,
        "quality_hold": 8,
        "receipt_unresolved": 0,
    }


def test_business_impact_reflects_price_variance_and_supplier_controls() -> None:
    platform = AmbiguousCasePlatform()

    variance = platform.reset_variant("unit_price_variance")["business_impact"]
    assert variance["po_unit_cost"] == 50.0
    assert variance["invoice_unit_price"] == 54.5
    assert variance["purchase_price_variance"] == 450.0
    assert variance["invoice_price_delta_percent"] == 9.0

    supplier_hold = platform.reset_variant("supplier_hold")["business_impact"]
    assert supplier_hold["supplier_status"] == "BLOCKED_COMPLIANCE"
    assert supplier_hold["supplier_payment_hold"] is True
    assert supplier_hold["invoice_hold_value"] == 5000.0


def test_paused_or_stale_run_cannot_advance_or_execute() -> None:
    platform = AmbiguousCasePlatform()
    diagnosed = platform.diagnose()
    run_id = str(diagnosed["agent_run"]["run_id"])
    approved = platform.approve("manager")
    approval_id = str(approved["execution"]["approval_id"])
    platform.stop()

    with pytest.raises(ValueError, match="paused investigation"):
        platform.execute(approval_id, "paused-write")
    sequence = int(platform.current()["latest_sequence"])
    platform.record_agent_tool_progress("read_erp_evidence", run_id=run_id)
    stale = platform.record_strands_investigation(
        {"status": "COMPLETE", "run_id": run_id, "tool_calls": [], "result": {}}
    )
    assert stale["agent_run"]["state"] == "STOPPED"
    assert stale["latest_sequence"] == sequence


def test_single_manager_action_executes_and_verifies_bound_scope() -> None:
    platform = AmbiguousCasePlatform()
    platform.diagnose()

    verified = platform.approve_execute_verify("manager", "single-human-action")

    assert verified["execution"]["status"] == "VERIFIED"
    packet = verified["resolution_packet"]
    assert packet["execution"]["approval_id"] == packet["approval"]["approval_id"]
    assert packet["approval"]["scope"]["receipt_post_quantity"] == 12
    assert packet["approval"]["scope"]["quality_transfer_quantity"] == 8


def test_validation_failure_reports_answer_review_not_provider_outage(tmp_path: Path) -> None:
    store = tmp_path / "validation.sqlite3"
    platform = AmbiguousCasePlatform(store_path=store)
    platform.authorize_diagnosis("operator")
    platform.claim_diagnosis()
    failed = platform.record_strands_investigation(
        {"status": "VALIDATION_FAILED", "tool_calls": ["read_erp_evidence"], "result": None}
    )
    for projection in (failed, AmbiguousCasePlatform(store_path=store).current()):
        assert projection["diagnosis"]["finding"] == "AGENT_VALIDATION_FAILED"
        assert "did not pass business validation" in projection["diagnosis"]["summary"]
        assert "provider" not in projection["diagnosis"]["summary"].lower()
        assert projection["execution"]["available"] is False
        assert projection["execution"]["status"] == "SAFE_STOP"
        assert projection["evidence_constellation"]["conclusion"]["label"] == "ANSWER NEEDS REVIEW"
        assert projection["activity"][-1]["label"] == "Agent answer needs review"
    with pytest.raises(ValueError, match="requires a current recovery-ready"):
        platform.approve("manager")
