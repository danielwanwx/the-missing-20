from __future__ import annotations

from typing import Any

import pytest

from the_missing_20.adapters.operational_metrics import (
    business_impact,
    live_flow_metrics,
    source_freshness,
)


def _packet(*, received: float = 20, delivered: float = 0) -> dict[str, Any]:
    return {
        "status": "CONNECTED",
        "sequence": 3,
        "documents": [
            {
                "kind": "purchase_order",
                "name": "PO-40",
                "docstatus": 1,
                "quantity": 40,
                "line_value": 2000,
                "unit_rate": 50,
                "currency": "USD",
                "items": [
                    {
                        "name": "PO-L1",
                        "item_code": "ECU",
                        "qty": 40,
                        "uom": "Nos",
                        "net_rate": 50,
                        "net_amount": 2000,
                    }
                ],
            },
            {
                "kind": "purchase_receipt",
                "name": "PR-20",
                "docstatus": 1,
                "received": received,
                "accepted": received,
                "rejected": 0,
                "items": [{"name": "PR-L1", "item_code": "ECU", "uom": "Nos"}],
            },
            {
                "kind": "purchase_invoice",
                "name": "PI-20",
                "docstatus": 1,
                "grand_total": 2200,
                "currency": "USD",
                "on_hold": False,
                "items": [
                    {
                        "name": "PI-L1",
                        "purchase_order": "PO-40",
                        "po_detail": "PO-L1",
                        "item_code": "ECU",
                        "uom": "Nos",
                        "qty": 40,
                        "net_rate": 50,
                        "net_amount": 2000,
                    }
                ],
            },
            {
                "kind": "delivery_note",
                "name": "DN-20",
                "docstatus": 1,
                "quantity": delivered,
                "items": [{"item_code": "ECU", "uom": "Nos"}],
            },
        ],
    }


def test_po_only_is_connected_awaiting_future_documents_not_an_outage() -> None:
    packet = _packet()
    packet["documents"] = packet["documents"][:1]
    packet["document_lifecycle"] = {
        "purchase_receipt": "AWAITING_RECEIPT",
        "purchase_invoice": "AWAITING_INVOICE",
    }
    assert source_freshness(packet)["status"] == "CURRENT"
    assert source_freshness(packet)["pending_document_kinds"] == [
        "purchase_receipt",
        "purchase_invoice",
    ]
    metrics = live_flow_metrics(packet)
    assert metrics["outstanding_order_quantity"] == 40
    assert metrics["receipt_unresolved"] == metrics["gap"] == 0


def test_normal_partial_receipt_is_remaining_work_not_twenty_missing_goods() -> None:
    metrics = live_flow_metrics(_packet())
    assert metrics["outstanding_order_quantity"] == 20
    assert metrics["physically_arrived"] == 20
    assert metrics["physically_arrived_basis"] == "RECEIPT_CONFIRMED"
    assert metrics["receipt_unresolved"] == metrics["gap"] == 0


def test_receiving_without_customer_scope_does_not_claim_zero_revenue() -> None:
    packet = _packet()
    for projection in (live_flow_metrics(packet), business_impact(packet)):
        for name in ("value_protected", "booked_revenue", "billed_revenue", "revenue_at_risk"):
            assert projection[name] is None
    assert business_impact(packet)["value_protected_classification"] == "NOT_CONFIGURED"


@pytest.mark.parametrize("billed", [None, 0, 100])
def test_known_customer_order_preserves_observed_unbilled_or_billed_values(
    billed: int | None,
) -> None:
    packet = _packet()
    packet["documents"].append(
        {
            "kind": "sales_order",
            "name": "SO-1",
            "docstatus": 1,
            "currency": "USD",
            "quantity": 1,
            "booked_value": 100,
        }
    )
    if billed is not None:
        packet["documents"].append(
            {
                "kind": "sales_invoice",
                "name": "SI-1",
                "docstatus": 1,
                "currency": "USD",
                "billed_revenue": billed,
                "billed_amount": billed,
            }
        )
    impact = business_impact(packet)
    assert impact["booked_revenue"] == 100
    assert impact["billed_revenue"] == (billed or 0)
    assert impact["value_protected_classification"] == (
        "OBSERVED_BILLING_NOT_INCREMENTAL_REVENUE" if billed else "NOT_REALIZED"
    )


def test_observed_invoice_does_not_invent_a_zero_customer_order() -> None:
    packet = _packet()
    packet["documents"].append(
        {
            "kind": "sales_invoice",
            "name": "SI-1",
            "docstatus": 1,
            "currency": "USD",
            "billed_revenue": 100,
            "billed_amount": 100,
        }
    )
    impact = business_impact(packet)
    assert impact["booked_revenue"] is None
    assert impact["billed_revenue"] == 100
    assert impact["revenue_at_risk"] is None


def test_incomparable_customer_currency_is_unavailable_not_zero() -> None:
    packet = _packet()
    packet["documents"].append(
        {
            "kind": "sales_invoice",
            "name": "SI-1",
            "docstatus": 1,
            "currency": "EUR",
            "billed_revenue": 100,
            "billed_amount": 100,
        }
    )
    impact = business_impact(packet)
    assert impact["billed_revenue"] is None
    assert impact["value_protected_classification"] == "UNAVAILABLE"


def test_delivery_reduces_case_balance_not_cumulative_receipts() -> None:
    metrics = live_flow_metrics(_packet(received=40, delivered=20))
    assert metrics["received_cumulative"] == metrics["accepted_cumulative"] == 40
    assert metrics["case_balance"] == metrics["recorded"] == 20
    assert metrics["on_hand"] is metrics["available_to_promise"] is None


def test_invoice_tax_is_not_purchase_price_variance() -> None:
    impact = business_impact(_packet())
    assert impact["invoice_value"] == 2200
    assert impact["purchase_price_variance"] == 0
    assert impact["invoice_unit_price"] == 50
    assert impact["price_comparison_status"] == "MATCHED_NET_LINES"


def test_multiple_receipts_deduplicate_before_latest_cancelled_revision() -> None:
    packet = _packet(received=10)
    receipt = packet["documents"][1]
    packet["documents"] += [
        dict(receipt),
        {**receipt, "name": "PR-2"},
        {**receipt, "name": "PR-DRAFT", "docstatus": 0},
        {**receipt, "name": "PR-CANCEL", "modified": "2026-09-01"},
        {**receipt, "name": "PR-CANCEL", "docstatus": 2, "modified": "2026-09-02"},
    ]
    assert live_flow_metrics(packet)["received"] == 20


def test_signed_supplier_return_reduces_receipts_without_clamping_signed_facts() -> None:
    packet = _packet(received=40)
    packet["documents"].append(
        {
            **packet["documents"][1],
            "name": "RETURN-1",
            "is_return": 1,
            "received": -5,
            "accepted": -5,
        }
    )
    assert live_flow_metrics(packet)["received"] == 35


def test_independent_observation_establishes_twelve_unposted_and_eight_held() -> None:
    packet = _packet(received=28)
    packet["documents"][1].update(accepted=20, rejected=8)
    packet["physical_evidence"] = {"verified": True, "received_quantity": 40}
    metrics = live_flow_metrics(packet)
    assert metrics["receipt_unresolved"] == 12
    assert metrics["quality_hold"] == 8
    assert metrics["gap"] == 20
    assert metrics["working_capital_at_risk"] == 1000


def test_unverified_photo_observation_cannot_establish_discrepancy() -> None:
    packet = _packet()
    packet["physical_evidence"] = {"received_quantity": 40}
    assert live_flow_metrics(packet)["receipt_unresolved"] == 0


@pytest.mark.parametrize(
    "change",
    [
        {"currency": "EUR"},
        {"items": []},
        {
            "items": [
                {
                    "purchase_order": "PO-40",
                    "po_detail": "PO-L1",
                    "item_code": "ECU",
                    "uom": "Box",
                    "qty": 40,
                    "net_rate": 50,
                }
            ]
        },
        {
            "items": [
                {
                    "purchase_order": "PO-OTHER",
                    "po_detail": "PO-L1",
                    "item_code": "ECU",
                    "uom": "Nos",
                    "qty": 40,
                    "net_rate": 50,
                }
            ]
        },
        {
            "items": [
                {
                    "purchase_order": "PO-40",
                    "po_detail": "PO-L1",
                    "item_code": "ECU",
                    "uom": "Nos",
                    "qty": 40,
                    "rate": 50,
                }
            ]
        },
    ],
)
def test_incomparable_invoice_does_not_show_zero_or_fabricated_price(
    change: dict[str, Any],
) -> None:
    packet = _packet()
    packet["documents"][2].update(change)
    assert business_impact(packet)["purchase_price_variance"] is None
    assert business_impact(packet)["invoice_unit_price"] is None


def test_price_variance_compares_only_quantity_actually_invoiced() -> None:
    packet = _packet()
    packet["documents"][2]["items"][0].update(qty=10, net_rate=55, net_amount=550)
    impact = business_impact(packet)
    assert impact["purchase_price_variance"] == 50
    assert impact["invoice_price_delta_percent"] == 10


def test_mixed_item_or_unit_is_not_one_misleading_total() -> None:
    packet = _packet()
    packet["documents"][0]["items"].append(
        {"name": "PO-L2", "item_code": "BRAKE", "uom": "Box", "qty": 3}
    )
    metrics = live_flow_metrics(packet)
    assert metrics["expected"] is metrics["recorded"] is metrics["gap"] is None
    assert metrics["po_unit_cost"] is None


@pytest.mark.parametrize("status", ["DEGRADED", "NOT_CONFIGURED"])
def test_outage_is_unknown_not_healthy_zero(status: str) -> None:
    packet = _packet()
    packet["status"] = status
    metrics = live_flow_metrics(packet)
    assert metrics["expected"] is metrics["gap"] is metrics["invoice_held"] is None
    assert business_impact(packet)["purchase_price_variance"] is None
    assert source_freshness(packet)["status"] == "UNAVAILABLE"


def test_non_finite_provider_quantity_is_unknown() -> None:
    packet = _packet()
    packet["documents"][1]["received"] = float("nan")
    assert live_flow_metrics(packet)["received"] is None


def test_unique_po_item_can_match_invoice_without_row_id_but_ambiguity_cannot() -> None:
    packet = _packet()
    packet["documents"][2]["items"][0].pop("po_detail")
    assert business_impact(packet)["purchase_price_variance"] == 0
    packet["documents"][0]["items"].append(
        {**packet["documents"][0]["items"][0], "name": "PO-L2", "net_rate": 70}
    )
    assert business_impact(packet)["purchase_price_variance"] is None


def test_unsigned_supplier_return_does_not_increase_received_inventory() -> None:
    packet = _packet()
    packet["documents"][1]["is_return"] = 1
    assert live_flow_metrics(packet)["received"] is None


def test_cancelled_purchase_invoice_has_no_financial_effect() -> None:
    packet = _packet()
    packet["documents"][2].update(docstatus=2, on_hold=True)
    assert live_flow_metrics(packet)["invoice_hold_value"] == 0
    assert business_impact(packet)["invoice_status"] == "NOT YET INVOICED"
