"""Live advisory uses cumulative receipt and accounting bases without inventing facts."""

from __future__ import annotations

from the_missing_20.adapters.investigation_case_sources import correlate_investigation_sources
from the_missing_20.agents.live_advisory import (
    HISTORY_TOOL_NAME,
    live_recovery_packet,
    model_source_payloads,
)


def projection():
    return {
        "case_projection": {
            "provenance": "live-read",
            "source_sequence": 4,
            "case": {
                "case_id": "LIVE-CASE",
                "purchase_order": "PO",
                "purchase_receipt": "PR",
                "purchase_invoice": "PI",
                "sales_order": "SO",
                "delivery_note": "DN",
                "sales_invoice": "SI",
                "quality_release_transfer": "STE",
                "uom": "EA",
                "invoice_held": False,
                "physical_observation_basis": "RECEIPT_CONFIRMED",
                "quantities": {
                    "ordered": 20,
                    "physically_arrived": 20,
                    "available": 0,
                    "accepted_cumulative": 12,
                    "released_quantity": 8,
                    "delivered_quantity": 20,
                    "quality_hold": 0,
                    "receipt_unresolved": 0,
                },
            },
        },
        "correlation": {
            "status": "FULLY_CORRELATED",
            "tuple": {"supplier_lot": "LOT"},
            "registry_tuple": {"supplier_lot": "LOT", "quantity": 8},
        },
        "business_impact": {
            "po_unit_cost": 50,
            "invoice_unit_price": 50,
            "currency": "USD",
            "supplier_status": "ACTIVE",
        },
        "value_proof": {
            "status": "BILLED_VERIFIED",
            "observed": {
                "order_quantity": 20,
                "delivered_quantity": 20,
                "booked_revenue": 2200,
                "billed_revenue": 2000,
                "billing_complete": True,
                "issue_complete": True,
            },
            "money_basis": {"booked_revenue": "GROSS", "billed_revenue": "NET"},
        },
        "systems": [],
        "diagnosis": {"status": "VERIFIED"},
        "execution": {"status": "VERIFIED"},
    }


def test_fully_issued_and_taxed_order_is_not_a_new_receipt_gap() -> None:
    packet = live_recovery_packet(projection())
    sources = model_source_payloads(packet)
    observations = correlate_investigation_sources(sources)["observations"]
    assert observations["erp_accounted_quantity"] == 20
    assert observations["erp_recorded_issue_quantity"] == 20
    assert observations["erp_available_quantity"] == 0
    assert packet["expected_disposition"] == "RECOVERY_COMPLETE"
    assert sources["read_erp_evidence"]["customer_order"]["billing_complete"] is True
    assert (
        sources["read_collaboration_evidence"]["warehouse_receipt"]["independent_observation"]
        is False
    )
    assert sources["read_celigo_evidence"]["attempts"][0]["response"] == "ERP_RECEIPT_PROJECTION"


def test_unknown_price_currency_and_uom_remain_unknown_and_stop_recovery() -> None:
    payload = projection()
    payload["business_impact"].update(po_unit_cost=None, invoice_unit_price=None, currency=None)
    payload["case_projection"]["case"]["uom"] = None
    packet = live_recovery_packet(payload)
    sources = model_source_payloads(packet)
    assert packet["expected_disposition"] == "NEEDS_EVIDENCE"
    assert sources["read_erp_evidence"]["invoice"]["unit_price"] is None
    assert sources["read_erp_evidence"]["purchase_order"]["currency"] is None
    assert sources["read_celigo_evidence"]["attempts"][0]["conversion_factor_to_po_uom"] is None


def test_live_history_uses_separate_optional_source_and_citation_closure() -> None:
    payload = projection()
    payload["operational_history"] = {
        "case_id": "LIVE-CASE",
        "points": [
            {
                "case_id": "LIVE-CASE",
                "id": 4,
                "source_id": "ERP",
                "metrics": {"received_cumulative": 20},
            }
        ],
        "baseline": {"status": "INSUFFICIENT_DATA", "industry_benchmark": False},
    }
    packet = live_recovery_packet(payload)
    visible = model_source_payloads(packet)
    history = visible[HISTORY_TOOL_NAME]
    assert history["evidence_ids"] == ["operational-history:LIVE-CASE:4"]
    assert history["evidence_ids"][0] in packet["evidence_ids"]
    assert history["freshness"] == "HISTORICAL_OBSERVATIONS"
    assert "operational-history" not in str(visible["read_erp_evidence"])
