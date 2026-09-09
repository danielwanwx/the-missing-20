from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from the_missing_20.adapters.agent_platform import AgentPlatform
from the_missing_20.adapters.investigation_case_sources import (
    correlate_investigation_sources,
    evaluate_investigation_policy,
    investigation_packet,
)


def _section(value: Mapping[str, object], key: str) -> dict[str, Any]:
    section = value[key]
    assert isinstance(section, dict)
    return section


def _snapshot() -> dict[str, Any]:
    packet: dict[str, Any] = {
        "status": "CONNECTED",
        "case_id": "CASE-40",
        "source_id": "erpnext-missing20",
        "documents": [
            {
                "kind": "purchase_order",
                "name": "PO-40",
                "quantity": 40,
                "unit_rate": 50,
                "line_value": 2000,
                "currency": "USD",
                "uom": "Nos",
            },
            {
                "kind": "purchase_receipt",
                "name": "PR-20",
                "received": 20,
                "accepted": 20,
                "rejected": 0,
                "uom": "Nos",
            },
            {"kind": "purchase_invoice", "name": "PI-20", "status": "OPEN"},
            {
                "kind": "sales_order",
                "name": "SO-20",
                "quantity": 20,
                "booked_value": 1320,
                "currency": "USD",
                "billed_percent": 100,
            },
            {
                "kind": "delivery_note",
                "name": "DN-20",
                "status": "SUBMITTED",
                "quantity": 20,
                "uom": "Nos",
            },
            {
                "kind": "sales_invoice",
                "name": "SI-20",
                "status": "SUBMITTED",
                "quantity": 20,
                "billed_revenue": 1200,
                "billed_amount": 1320,
                "currency": "USD",
            },
        ],
    }
    for document in packet["documents"]:
        if document["kind"] in {"purchase_order", "sales_invoice"}:
            document["items"] = [{"item_code": "ECU", "uom": "Nos"}]
    return packet


def test_issued_goods_and_taxed_billing_are_complete_without_cash_or_delivery_claims() -> None:
    erp = _snapshot()
    case = AgentPlatform._case_projection(erp)["case"]
    assert isinstance(case, dict)
    assert case["quantities"]["case_balance"] == 0
    assert case["quantities"]["received_cumulative"] == 20
    assert case["quantities"]["delivered_quantity"] == 20
    assert case["balance_basis"] == "CASE_ACCEPTED_LESS_RECORDED_ISSUES"
    proof = AgentPlatform._value_proof(erp)
    observed, estimated, assertions = (
        _section(proof, key) for key in ("observed", "estimated", "assertions")
    )
    assert proof["status"] == "BILLED_VERIFIED"
    assert observed["billing_complete"] is True
    assert observed["gross_spread"] is None
    assert estimated["gross_spread"] == 200
    assert assertions["order_to_billing_closed_loop_verified"] is True
    assert assertions["order_to_cash_closed_loop_verified"] is False
    assert assertions["carrier_delivery_verified"] is False
    assert AgentPlatform._live_flow_metrics(erp)["revenue_at_risk"] == 0


def test_negative_estimated_spread_is_not_clamped_to_look_profitable() -> None:
    erp = _snapshot()
    erp["documents"][-1]["billed_revenue"] = 800
    assert _section(AgentPlatform._value_proof(erp), "estimated")["gross_spread"] == -200


def test_foreign_currency_invoice_does_not_produce_a_cross_currency_margin() -> None:
    erp = _snapshot()
    erp["documents"][-1]["currency"] = "EUR"
    assert _section(AgentPlatform._value_proof(erp), "estimated")["gross_spread"] is None


def test_different_billed_item_does_not_produce_a_spurious_margin() -> None:
    erp = _snapshot()
    erp["documents"][-1]["items"][0]["item_code"] = "OTHER-SKU"
    assert _section(AgentPlatform._value_proof(erp), "estimated")["gross_spread"] is None


def test_all_receipts_visible_but_only_explicit_primary_is_an_operation_target() -> None:
    erp = _snapshot()
    erp["documents"].append({**erp["documents"][1], "name": "PR-OTHER"})
    assert "purchase_receipt" not in AgentPlatform._documents_by_kind(erp)
    erp["primary_document_names"] = {"purchase_receipt": "PR-20"}
    assert AgentPlatform._documents_by_kind(erp)["purchase_receipt"]["name"] == "PR-20"
    catalog = AgentPlatform._evidence_catalog(erp, {})
    assert {"PR-20", "PR-OTHER"}.issubset(catalog)


class _Reader:
    def current(self) -> dict[str, object]:
        return {}


def test_recovery_reread_does_not_invent_pre_execution_inventory() -> None:
    platform = AgentPlatform(_Reader(), _Reader())
    packet = platform._resolution_packet_projection(_snapshot(), {}, {}, {}, True)
    assert packet is not None
    assert _section(packet, "pre_state")["available"] is None
    assert _section(packet, "post_state")["case_balance"] == 0
    assert _section(packet, "post_state")["received_cumulative"] == 20


def test_cumulative_receipt_with_issue_does_not_look_like_an_unposted_receipt() -> None:
    packet = investigation_packet("normal_complete")
    sources = deepcopy(packet["tool_payload"]["sources"])
    erp = sources["read_erp_evidence"]
    row = erp["ledger_read"]["records"][0]
    row["stock_type"] = "ACCEPTED_RECEIPT"
    erp["ledger_read"]["recorded_issues"] = [
        {"id": "DN-ISSUE", "po": row["po"], "line": row["line"], "quantity": 100}
    ]
    erp["customer_order"] = {
        "id": "SO-100",
        "quantity": 100,
        "delivered_quantity": 100,
        "booked_revenue": 5500,
        "billed_revenue": 5000,
        "billing_complete": True,
        "delivery_note": "DN-ISSUE",
        "sales_invoice": "SI-100",
    }
    findings = correlate_investigation_sources(sources)
    observed = findings["observations"]
    assert observed["erp_available_quantity"] == 0
    assert observed["erp_accounted_quantity"] == 100
    assert observed["erp_recorded_issue_quantity"] == 100
    decision = evaluate_investigation_policy(findings)
    assert decision["disposition"] == "RECOVERY_COMPLETE"
    assert decision["checks"]["customer_order_complete"] is True


def test_unknown_commercial_price_is_missing_evidence_not_an_approved_zero() -> None:
    sources = deepcopy(investigation_packet("normal_complete")["tool_payload"]["sources"])
    sources["read_erp_evidence"]["invoice"]["unit_price"] = None
    sources["read_erp_evidence"]["purchase_order"]["unit_price"] = None
    decision = evaluate_investigation_policy(correlate_investigation_sources(sources))
    assert decision["disposition"] == "NEEDS_EVIDENCE"
