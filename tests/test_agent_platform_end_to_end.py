"""Strict case-matrix regressions for the read-only Agent Platform.

These tests drive the real coordinator seam with changing provider projections.
They deliberately cover both a fully evidenced *plan* and cases which must be
blocked.  No assertion permits an external write or a verified recovery.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from the_missing_20.adapters.agent_platform import AgentPlatform
from the_missing_20.adapters.demo_executor import DemoExecutionResult


class _MutableReader:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls = 0

    def current(self) -> dict[str, object]:
        self.calls += 1
        return deepcopy(self.payload)


def _erp(
    *, quality_hold: bool = True, status: str = "CONNECTED", recovered: bool = False
) -> dict[str, object]:
    return {
        "status": status,
        "activity": [
            {
                "source_id": "erpnext-missing20",
                "provider": "ERPNext",
                "status": "HELD" if quality_hold else "VERIFIED",
                "record_id": "PR-20",
                "label": "Receipt PR-20",
                "detail": "8 held" if quality_hold else "20 accepted",
            }
        ],
        "documents": [
            {"kind": "purchase_order", "name": "PO-20"},
            {
                "kind": "purchase_receipt",
                "name": "PR-20",
                "status": "PARTIAL_QUALITY_HOLD" if quality_hold else "RECEIVED",
                "rejected": 8 if quality_hold else 0,
            },
            {
                "kind": "purchase_invoice",
                "name": "PI-20",
                "status": "OPEN" if recovered else "PAYMENT_HOLD",
            },
            *(
                [
                    {
                        "kind": "quality_release_transfer",
                        "name": "MAT-STE-20",
                        "status": "SUBMITTED",
                        "quantity": 8,
                    }
                ]
                if recovered
                else []
            ),
        ],
    }


def _registry(*, mismatch: bool = False) -> dict[str, object]:
    return {
        "case_id": "M20-CASE-20",
        "purchase_order": "WRONG-PO" if mismatch else "PO-20",
        "purchase_receipt": "PR-20",
        "purchase_invoice": "PI-20",
        "supplier_lot": "LOT-20",
        "certificate_id": "CERT-20",
        "quantity": 8,
        "evidence_revision": "rev-3",
    }


def _saas(
    *,
    direct_receipt: bool,
    receipt_matches: bool = True,
    registry_mismatch: bool = False,
    include_registry: bool = True,
) -> dict[str, object]:
    sources: list[dict[str, object]] = []
    if include_registry:
        sources.append(
            {
                "source_id": "airtable-quality-registry",
                "provider": "Airtable",
                "status": "VERIFIED",
                "record_id": "rec-20",
                "label": "Registry approved",
                "detail": "quality release registry",
                "correlation": _registry(mismatch=registry_mismatch),
            }
        )
    sources.extend(
        [
            {
                "source_id": "celigo-quality-release",
                "provider": "Celigo",
                "status": "VERIFIED",
                "record_id": "run-20" if direct_receipt else "flow-20",
                "label": "Run receipt" if direct_receipt else "Flow enabled",
                "detail": "ERP acknowledged" if direct_receipt else "Control-plane only",
                "evidence_kind": "RUN_RECEIPT" if direct_receipt else "CONTROL_PLANE",
                "correlation": _registry(mismatch=not receipt_matches),
                "erp_acknowledged": direct_receipt,
            },
            {
                "source_id": "jira-capa",
                "provider": "Jira",
                "status": "VERIFIED",
                "record_id": "CAPA-20",
                "label": "CAPA journal",
                "detail": "context only",
            },
            {
                "source_id": "slack-quality-alerts",
                "provider": "Slack",
                "status": "VERIFIED",
                "record_id": "171.20",
                "label": "Alert journal",
                "detail": "context only",
            },
        ]
    )
    return {
        "status": "CONNECTED",
        "correlation_id": "M20-CASE-20",
        "sources": sources,
        "activity": sources,
    }


def _step(projection: dict[str, object], step_id: str) -> dict[str, object]:
    return next(
        step for step in projection["plan"] if isinstance(step, dict) and step.get("id") == step_id
    )


def test_full_tuple_and_exact_celigo_receipt_only_prepare_a_guarded_plan() -> None:
    """A plan may be ready, but a provider mutation remains unreachable."""

    erp = _MutableReader(_erp())
    saas = _MutableReader(_saas(direct_receipt=True))

    projection = AgentPlatform(erp, saas).diagnose()

    assert projection["correlation"]["status"] == "FULLY_CORRELATED"
    assert projection["integration_receipt"]["status"] == "VERIFIED"
    assert projection["agent_run"]["state"] == "PLAN_READY"
    assert _step(projection, "validate_run")["status"] == "DONE"
    assert projection["execution"] == {
        "available": False,
        "status": "WRITE_DISABLED",
        "detail": "External provider mutations are intentionally disabled in this demo build.",
    }
    assert projection["human_review"]["status"] == "MANAGER_REVIEW_REQUIRED"
    assert projection["resolution_packet"] is None
    assert erp.calls == saas.calls == 1


def test_enabled_flow_does_not_block_a_pre_execution_guarded_plan() -> None:
    projection = AgentPlatform(
        _MutableReader(_erp()), _MutableReader(_saas(direct_receipt=False))
    ).diagnose()

    assert projection["correlation"]["status"] == "FULLY_CORRELATED"
    assert projection["integration_receipt"]["status"] == "CONTROL_PLANE_ONLY"
    assert projection["agent_run"]["state"] == "PLAN_READY"
    assert _step(projection, "validate_run")["status"] == "NOT_REQUIRED_YET"


def test_guarded_executor_waits_for_post_execution_receipt_before_closure() -> None:
    class _Executor:
        def __init__(self) -> None:
            self.calls = 0

        def execute(self, plan):  # type: ignore[no-untyped-def]
            self.calls += 1
            assert plan.case_id == "M20-CASE-20"
            assert plan.quantity == 8
            return DemoExecutionResult("MAT-STE-20", "PI-20", False, True)

    executor = _Executor()
    saas = _MutableReader(_saas(direct_receipt=False))
    platform = AgentPlatform(_MutableReader(_erp()), saas, executor=executor)
    ready = platform.diagnose()

    assert ready["execution"]["status"] == "AWAITING_MANAGER_APPROVAL"
    approved = platform.approve("M20 Demo Manager")
    result = platform.execute(approved["execution"]["approval_id"], "m20-run-20")

    assert executor.calls == 1
    assert result["execution"]["status"] == "VERIFYING"
    waiting = platform.verify()
    assert waiting["execution"]["status"] == "VERIFYING"

    row = next(
        item for item in saas.payload["sources"] if item["source_id"] == "celigo-quality-release"
    )  # type: ignore[index]
    row.update(
        {
            "status": "VERIFIED",
            "record_id": "run-20",
            "label": "Run receipt",
            "detail": "ERP acknowledged",
            "evidence_kind": "RUN_RECEIPT",
            "erp_acknowledged": True,
        }
    )
    activity_row = next(
        item for item in saas.payload["activity"] if item["source_id"] == "celigo-quality-release"
    )  # type: ignore[index]
    activity_row.update(row)
    verified = platform.verify()
    assert verified["execution"]["status"] == "VERIFIED"
    assert verified["diagnosis"]["status"] == "VERIFIED"
    assert verified["diagnosis"]["integration_receipt_status"] == "VERIFIED"
    assert verified["evidence_constellation"]["conclusion"]["label"] == "RECOVERY VERIFIED"
    assert verified["resolution_packet"]["status"] == "VERIFIED"
    assert verified["resolution_packet"]["approval"]["manager_id"] == "M20 Demo Manager"
    assert verified["resolution_packet"]["execution"]["idempotency_key"] == "m20-run-20"
    assert verified["resolution_packet"]["case_tuple"]["receipt_post_quantity"] == 0
    assert (
        verified["resolution_packet"]["pre_state"]["available"]
        == verified["resolution_packet"]["post_state"]["available"]
    )
    assert verified["resolution_packet"]["policy"]["authority"] == "DETERMINISTIC_CONTROL_PLANE"
    assert all(verified["resolution_packet"]["timestamps"].values())
    assert verified["human_review"]["status"] == "COMPLETE"
    answer = platform.answer("What evidence proves this recovery is complete?")
    assert "Recovery is complete" in answer["answer"]
    assert "MAT-STE-20" in answer["answer"]


def test_live_erp_ledger_is_exposed_as_finance_grade_citation() -> None:
    erp = _erp()
    erp.update(
        {
            "provider": "ERPNext / Frappe Cloud",
            "received_at": "2026-09-07T16:49:12+00:00",
            "ledger_evidence": {
                "status": "CONNECTED",
                "stock_entries": [
                    {
                        "name": "SLE-20",
                        "voucher_no": "PR-20",
                        "item_code": "M20-ECU",
                        "warehouse": "Stores",
                        "actual_qty": 20,
                        "stock_value_difference": 24000,
                        "posting_date": "2026-09-07",
                        "company": "M20 Demo",
                    }
                ],
                "general_ledger_entries": [
                    {"name": "GLE-20A", "account": "Stock In Hand", "debit": 24000, "credit": 0},
                    {"name": "GLE-20B", "account": "SRBNB", "debit": 0, "credit": 24000},
                ],
                "totals": {"debit": 24000, "credit": 24000, "stock_value_difference": 24000},
                "assertions": {
                    "stock_ledger_present": True,
                    "general_ledger_present": True,
                    "debits_equal_credits": True,
                },
            },
        }
    )
    projection = AgentPlatform(
        _MutableReader(erp), _MutableReader(_saas(direct_receipt=True))
    ).current()

    citation = projection["evidence_catalog"]["PR-20:ledger"]
    assert citation["provider"] == "ERPNext / Frappe Cloud"
    assert citation["provenance"] == "live-provider-read"
    assert citation["observed_at"] == "2026-09-07T16:49:12+00:00"
    assert citation["revision"] != ""
    assert citation["assertions"]["debits_equal_credits"] is True
    assert citation["totals"]["debit"] == citation["totals"]["credit"] == 24000
    assert citation["stock_entries"][0]["name"] == "SLE-20"
    assert len(citation["general_ledger_entries"]) == 2


def test_live_platform_supports_one_manager_action_for_guarded_execution() -> None:
    class _Executor:
        def execute(self, plan):  # type: ignore[no-untyped-def]
            assert plan.case_id == "M20-CASE-20"
            assert plan.idempotency_key == "m20-live-one-click"
            return DemoExecutionResult("MAT-STE-20", "PI-20", True, True)

    live_erp = _erp()
    live_erp["provider"] = "ERPNext / Frappe Cloud"
    platform = AgentPlatform(
        _MutableReader(live_erp),
        _MutableReader(_saas(direct_receipt=True)),
        executor=_Executor(),
    )
    platform.diagnose()

    verified = platform.approve_execute_verify("M20 Demo Manager", "m20-live-one-click")

    assert verified["execution"]["status"] == "VERIFIED"
    assert verified["human_review"]["status"] == "COMPLETE"
    assert verified["resolution_packet"]["execution"]["idempotency_key"] == ("m20-live-one-click")
    assert verified["resolution_packet"]["execution"]["approval_id"] == ("m20-approval-0001")
    assert verified["resolution_packet"]["provenance"] == "live-provider-write"
    assert verified["systems"][0]["read_only"] is False
    assert verified["systems"][0]["write_state"] == "MANAGER_GATED"
    assert verified["activity"][-2]["read_only"] is False


def test_live_customer_order_is_manager_gated_and_verified_to_billed_revenue() -> None:
    erp = _MutableReader(_erp(recovered=True))
    erp.payload["provider"] = "ERPNext / Frappe Cloud"
    next(row for row in erp.payload["documents"] if row.get("kind") == "purchase_order")[  # type: ignore[union-attr]
        "line_value"
    ] = 24000
    erp.payload["documents"].extend(  # type: ignore[union-attr]
        [
            {
                "kind": "sales_order",
                "name": "SO-M20-20",
                "status": "On Hold",
                "quantity": 20,
                "booked_value": 42000,
                "currency": "USD",
                "delivered_percent": 0,
                "billed_percent": 0,
            }
        ]
    )

    class _ValueExecutor:
        def execute(self, plan):  # type: ignore[no-untyped-def]
            assert plan.quantity == 8
            assert plan.sales_order == "SO-M20-20"
            assert plan.sales_order_quantity == 20
            order = next(
                row
                for row in erp.payload["documents"]
                if row.get("kind") == "sales_order"  # type: ignore[union-attr]
            )
            order.update({"status": "Completed", "delivered_percent": 100, "billed_percent": 100})
            erp.payload["documents"].extend(  # type: ignore[union-attr]
                [
                    {
                        "kind": "delivery_note",
                        "name": "DN-M20-20",
                        "status": "SUBMITTED",
                        "quantity": 20,
                    },
                    {
                        "kind": "sales_invoice",
                        "name": "SI-M20-20",
                        "status": "SUBMITTED",
                        "billed_revenue": 42000,
                        "currency": "USD",
                    },
                ]
            )
            return DemoExecutionResult(
                "MAT-STE-20",
                "PI-20",
                True,
                True,
                sales_order="SO-M20-20",
                delivery_note="DN-M20-20",
                sales_invoice="SI-M20-20",
                order_to_cash_verified=True,
            )

    platform = AgentPlatform(
        erp,
        _MutableReader(_saas(direct_receipt=True)),
        executor=_ValueExecutor(),
    )
    pending_answer = platform.answer("How much revenue is at risk and has it been billed?")
    assert "booked revenue USD 42,000.00" in pending_answer["answer"]
    assert "billed revenue USD 0.00" in pending_answer["answer"]
    assert "explicitly counterfactual" in pending_answer["answer"]
    ready = platform.diagnose()
    assert ready["agent_run"]["state"] == "PLAN_READY"
    assert ready["diagnosis"]["finding"] == "CUSTOMER_ORDER_AWAITING_VERIFIED_FULFILLMENT"
    assert ready["value_proof"]["counterfactual"]["revenue_at_risk_if_hold_persists"] == 42000
    assert ready["value_proof"]["assertions"]["causal_revenue_increase_proven"] is False

    agent_ready = platform.record_strands_investigation(
        {
            "status": "COMPLETE",
            "tool_calls": ["read_erp_evidence", "reconcile_source_records"],
            "evidence_findings": {
                "evidence_ids": ["SO-M20-20", "PI-20"],
                "policy": {
                    "disposition": "RECOVERY_READY",
                    "checks": {"customer_order_requires_fulfillment": True},
                },
            },
            "result": {
                "disposition": "RECOVERY_READY",
                "reason": "The customer order is held, undelivered, and unbilled.",
                "write_performed": False,
            },
        }
    )
    assert agent_ready["diagnosis"]["finding"] == "CUSTOMER_ORDER_AWAITING_VERIFIED_FULFILLMENT"

    verified = platform.approve_execute_verify("M20 Demo Manager", "m20-value-proof")

    assert verified["execution"]["status"] == "VERIFIED"
    assert verified["value_proof"]["status"] == "BILLED_VERIFIED"
    assert verified["value_proof"]["observed"]["billed_revenue"] == 42000
    assert verified["value_proof"]["observed"]["gross_spread"] == 18000
    assert (
        verified["business_impact"]["value_protected_classification"] == "OBSERVED_BILLED_REVENUE"
    )
    assert verified["resolution_packet"]["effects"]["sales_invoice"] == "SI-M20-20"
    assert verified["human_review"]["status"] == "COMPLETE"
    billed_answer = platform.answer("Show the customer delivery and billed revenue.")
    assert "BILLED_VERIFIED" in billed_answer["answer"]
    assert "billed revenue USD 42,000.00" in billed_answer["answer"]


def test_customer_invoice_without_delivery_evidence_cannot_close_the_loop() -> None:
    erp = _MutableReader(_erp(recovered=True))
    erp.payload["documents"].extend(  # type: ignore[union-attr]
        [
            {
                "kind": "sales_order",
                "name": "SO-M20-20",
                "status": "Completed",
                "quantity": 20,
                "booked_value": 42000,
                "currency": "USD",
                "delivered_percent": 100,
                "billed_percent": 100,
            },
            {
                "kind": "sales_invoice",
                "name": "SI-M20-20",
                "status": "SUBMITTED",
                "billed_revenue": 42000,
                "currency": "USD",
            },
        ]
    )

    proof = AgentPlatform._value_proof(erp.current())

    assert proof["status"] == "INVOICE_POSTED_AWAITING_DELIVERY_EVIDENCE"
    assert proof["assertions"]["customer_invoice_posted"] is True
    assert proof["assertions"]["delivery_posted"] is False
    assert proof["assertions"]["order_to_cash_closed_loop_verified"] is False
    assert AgentPlatform._value_pending(erp.current()) is True


def test_fresh_reread_blocks_verified_execution_when_delivery_document_is_missing() -> None:
    erp = _MutableReader(_erp(recovered=True))
    erp.payload["documents"].append(  # type: ignore[union-attr]
        {
            "kind": "sales_order",
            "name": "SO-M20-20",
            "status": "On Hold",
            "quantity": 20,
            "booked_value": 42000,
            "currency": "USD",
            "delivered_percent": 0,
            "billed_percent": 0,
        }
    )

    class _InvoiceOnlyExecutor:
        def execute(self, plan):  # type: ignore[no-untyped-def]
            order = next(
                row
                for row in erp.payload["documents"]
                if row.get("kind") == "sales_order"  # type: ignore[union-attr]
            )
            order.update({"status": "Completed", "delivered_percent": 100, "billed_percent": 100})
            erp.payload["documents"].append(  # type: ignore[union-attr]
                {
                    "kind": "sales_invoice",
                    "name": "SI-M20-20",
                    "status": "SUBMITTED",
                    "billed_revenue": 42000,
                    "currency": "USD",
                }
            )
            return DemoExecutionResult(
                "MAT-STE-20",
                "PI-20",
                True,
                True,
                sales_order="SO-M20-20",
                delivery_note="DN-RETURNED-BUT-NOT-REREAD",
                sales_invoice="SI-M20-20",
                order_to_cash_verified=True,
            )

    platform = AgentPlatform(
        erp,
        _MutableReader(_saas(direct_receipt=True)),
        executor=_InvoiceOnlyExecutor(),
    )
    platform.diagnose()

    projection = platform.approve_execute_verify("M20 Demo Manager", "m20-missing-delivery")

    assert projection["execution"]["status"] == "VERIFYING"
    assert "Delivery Note and Sales Invoice" in projection["execution"]["detail"]
    assert projection["value_proof"]["status"] == "INVOICE_POSTED_AWAITING_DELIVERY_EVIDENCE"
    assert projection["resolution_packet"] is None


def test_operator_pause_preserves_evidence_and_requires_explicit_resume() -> None:
    platform = AgentPlatform(_MutableReader(_erp()), _MutableReader(_saas(direct_receipt=False)))
    ready = platform.diagnose()
    assert ready["agent_run"]["state"] == "PLAN_READY"

    paused = platform.stop()
    assert paused["agent_run"]["state"] == "STOPPED"
    assert paused["human_review"]["status"] == "PAUSED_BY_HUMAN"
    assert paused["activity"][-1]["event_type"] == "human.investigation.paused"

    resumed = platform.diagnose()
    assert resumed["agent_run"]["state"] == "PLAN_READY"


def test_pause_or_changed_evidence_invalidates_a_manager_approval() -> None:
    class _Executor:
        def execute(self, plan):  # type: ignore[no-untyped-def]
            raise AssertionError("stale or paused plan must not reach the executor")

    erp = _MutableReader(_erp())
    saas = _MutableReader(_saas(direct_receipt=True))
    platform = AgentPlatform(erp, saas, executor=_Executor())
    platform.diagnose()
    approved = platform.approve("M20 Demo Manager")
    approval_id = approved["execution"]["approval_id"]
    platform.stop()

    with pytest.raises(ValueError, match="unchanged plan"):
        platform.execute(approval_id, "m20-paused-plan")

    platform.diagnose()
    approved = platform.approve("M20 Demo Manager")
    approval_id = approved["execution"]["approval_id"]
    saas.payload["sources"][0]["status"] = "HELD"  # type: ignore[index]
    with pytest.raises(ValueError, match="unchanged plan"):
        platform.execute(approval_id, "m20-stale-plan")


def test_live_conversation_and_verified_control_trail_survive_restart(tmp_path: Path) -> None:
    class _Executor:
        def execute(self, plan):  # type: ignore[no-untyped-def]
            return DemoExecutionResult("MAT-STE-20", "PI-20", True, True)

    state_path = tmp_path / "agent-platform-state.json"
    erp = _MutableReader(_erp())
    saas = _MutableReader(_saas(direct_receipt=True))
    platform = AgentPlatform(erp, saas, executor=_Executor(), state_path=state_path)
    platform.diagnose()
    platform.record_conversation_turn(
        "Which evidence proves the quantity?",
        "ERP receipt PR-20 and registry rec-20 reconcile eight held units.",
        {
            "evidence_ids": ["PR-20", "rec-20"],
            "tool_calls": ["read_erp_evidence", "read_airtable_evidence"],
            "provider": {"model": "us.amazon.nova-pro-v1:0"},
            "usage": {"input_tokens": 100},
            "latency_ms": 1200,
            "context_turns": 0,
        },
    )
    verified = platform.approve_execute_verify("M20 Demo Manager", "m20-restart-proof")
    assert verified["resolution_packet"]["approval"]["plan_digest"]

    restarted = AgentPlatform(erp, saas, executor=_Executor(), state_path=state_path).current()

    assert restarted["execution"]["status"] == "VERIFIED"
    assert restarted["resolution_packet"]["execution"]["approval_id"] == "m20-approval-0001"
    assert restarted["resolution_packet"]["execution"]["idempotency_key"] == ("m20-restart-proof")
    assert restarted["conversation"][0]["turn_id"] == "turn-001"


def test_restart_quarantines_a_historical_unsupported_causal_claim(tmp_path: Path) -> None:
    state_path = tmp_path / "agent-platform-state.json"
    state_path.write_text(
        json.dumps(
            {
                "sequence": 0,
                "run_number": 1,
                "conversation": [
                    {
                        "turn_id": "turn-001",
                        "question": "Did the platform cause more revenue?",
                        "answer": "Causal revenue uplift proven.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    projection = AgentPlatform(
        _MutableReader(_erp()),
        _MutableReader(_saas(direct_receipt=True)),
        state_path=state_path,
    ).current()

    turn = projection["conversation"][0]
    assert turn["validation_status"] == "REJECTED_CAUSAL_CLAIM"
    assert "does not prove" in turn["answer"]


def test_normal_receipt_uses_the_same_guarded_evidence_path_without_an_incident() -> None:
    erp = _erp(quality_hold=False)
    next(
        document
        for document in erp["documents"]  # type: ignore[union-attr]
        if document["kind"] == "purchase_invoice"
    )["status"] = "OPEN"
    saas = _saas(direct_receipt=True)
    for row in saas["sources"]:  # type: ignore[union-attr]
        if isinstance(row, dict) and isinstance(row.get("correlation"), dict):
            row["correlation"]["quantity"] = 0
    projection = AgentPlatform(_MutableReader(erp), _MutableReader(saas)).diagnose()

    assert projection["diagnosis"]["finding"] == "NO_QUALITY_HOLD_DETECTED"
    assert projection["agent_run"]["state"] == "BLOCKED"
    assert projection["evidence_constellation"]["conclusion"]["status"] == "CLEAR"
    assert projection["execution"]["available"] is False


def test_completed_strands_projection_replaces_stale_quality_hold_with_live_invoice_hold() -> None:
    erp = _erp()
    erp["documents"].append(  # type: ignore[union-attr]
        {
            "kind": "quality_release_transfer",
            "name": "MAT-STE-20",
            "status": "SUBMITTED",
            "quantity": 8,
        }
    )
    saas = _saas(direct_receipt=True)
    platform = AgentPlatform(_MutableReader(erp), _MutableReader(saas), executor=object())
    deterministic = platform.diagnose()
    assert deterministic["diagnosis"]["finding"] == "INVOICE_PAYMENT_HOLD"
    assert deterministic["diagnosis"]["hypotheses"][0]["status"] == "ELIMINATED"

    projection = platform.record_strands_investigation(
        {
            "status": "COMPLETE",
            "mode": "Strands SDK",
            "provider": {"model": "us.amazon.nova-pro-v1:0"},
            "tool_calls": ["read_erp_evidence", "reconcile_source_records"],
            "runtime_events": [{"type": "model"}, {"type": "tool"}],
            "evidence_findings": {
                "evidence_ids": ["PO-20", "PR-20", "PI-20"],
                "policy": {
                    "disposition": "RECOVERY_READY",
                    "manager_approval_required": True,
                },
            },
            "result": {
                "disposition": "RECOVERY_READY",
                "evidence_ids": ["PO-20", "PI-20"],
                "reason": (
                    "Invoice PI-20 is in PAYMENT_HOLD while inventory and physical quantity "
                    "are fully reconciled."
                ),
                "write_performed": False,
            },
        }
    )

    assert projection["agent_run"]["state"] == "PLAN_READY"
    assert projection["diagnosis"]["finding"] == "INVOICE_PAYMENT_HOLD"
    assert "PAYMENT_HOLD" in projection["diagnosis"]["summary"]
    hypotheses = {item["id"]: item["status"] for item in projection["diagnosis"]["hypotheses"]}
    assert hypotheses["quality_hold"] == "ELIMINATED"
    assert hypotheses["invoice_payment_hold"] == "SUPPORTED"
    assert projection["judge_proof"]["evidence_records"] == 3
    assert projection["judge_proof"]["source_checks"] == 2
    assert projection["judge_proof"]["sdk_hook_events"] == 2
    assert projection["execution"]["status"] == "AWAITING_MANAGER_APPROVAL"


def test_fresh_server_projection_recognizes_a_previously_verified_external_recovery() -> None:
    platform = AgentPlatform(
        _MutableReader(_erp(recovered=True)), _MutableReader(_saas(direct_receipt=True))
    )

    projection = platform.current()

    assert projection["execution"]["status"] == "VERIFIED"
    assert projection["evidence_constellation"]["conclusion"]["label"] == "RECOVERY VERIFIED"
    assert _step(projection, "guarded_plan")["status"] == "DONE"
    assert projection["resolution_packet"]["guard"] == "PRIOR_GUARDED_RECOVERY_VERIFIED_BY_REREAD"

    diagnosed = platform.diagnose()
    assert diagnosed["agent_run"]["state"] == "VERIFIED"
    assert diagnosed["diagnosis"]["finding"] == "RECOVERY_VERIFIED_FROM_LIVE_READS"
    assert diagnosed["execution"]["status"] == "VERIFIED"


def test_mismatched_registry_or_receipt_is_blocked_and_names_the_mismatch() -> None:
    registry_mismatch = AgentPlatform(
        _MutableReader(_erp()), _MutableReader(_saas(direct_receipt=True, registry_mismatch=True))
    ).diagnose()
    receipt_mismatch = AgentPlatform(
        _MutableReader(_erp()), _MutableReader(_saas(direct_receipt=True, receipt_matches=False))
    ).diagnose()

    assert registry_mismatch["correlation"]["status"] == "MISMATCHED_CORRELATION"
    assert registry_mismatch["correlation"]["mismatched_fields"] == ["purchase_order"]
    assert registry_mismatch["agent_run"]["state"] == "BLOCKED"
    assert receipt_mismatch["integration_receipt"]["status"] == "MISMATCHED_RECEIPT"
    assert receipt_mismatch["agent_run"]["state"] == "PLAN_READY"


def test_registry_that_is_held_cannot_be_used_to_complete_a_correlation() -> None:
    saas = _saas(direct_receipt=True)
    saas["sources"][0]["status"] = "HELD"  # type: ignore[index]
    saas["activity"][0]["status"] = "HELD"  # type: ignore[index]

    projection = AgentPlatform(_MutableReader(_erp()), _MutableReader(saas)).diagnose()

    assert projection["correlation"]["status"] == "PARTIAL_CORRELATION"
    assert projection["agent_run"]["state"] == "BLOCKED"


def test_repeated_polls_deduplicate_but_a_changed_provider_record_gets_one_new_sequence() -> None:
    erp = _MutableReader(_erp())
    saas = _MutableReader(_saas(direct_receipt=False))
    platform = AgentPlatform(erp, saas)

    first = platform.current()
    second = platform.current()
    assert second["latest_sequence"] == first["latest_sequence"]

    saas.payload["sources"][0]["status"] = "HELD"  # type: ignore[index]
    saas.payload["activity"][0]["status"] = "HELD"  # type: ignore[index]
    changed = platform.current()
    assert changed["latest_sequence"] == first["latest_sequence"] + 1
    assert changed["activity"][-1]["source_id"] == "airtable-quality-registry"

    saas.payload["sources"][0]["correlation"]["evidence_revision"] = "rev-4"  # type: ignore[index]
    revised = platform.current()
    assert revised["latest_sequence"] == changed["latest_sequence"] + 1
    assert revised["activity"][-1]["source_id"] == "airtable-quality-registry"
