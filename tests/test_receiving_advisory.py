"""Lifecycle regression: live receiving must not require fabricated invoice evidence."""

from copy import deepcopy

import pytest
from test_live_advisory_operational_semantics import projection

from the_missing_20.agents.live_advisory import (
    AdvisoryValidationError,
    live_recovery_packet,
    model_source_payloads,
)


def partial_receipt():
    payload = projection()
    case = payload["case_projection"]["case"]
    case.update(
        purchase_invoice="",
        sales_order="",
        delivery_note="",
        sales_invoice="",
        quality_release_transfer="",
        uom="Box",
    )
    case["quantities"].update(
        ordered=40,
        physically_arrived=1,
        available=1,
        receipt_posted_quantity=1,
        outstanding_order_quantity=39,
        accepted_cumulative=1,
        released_quantity=0,
        delivered_quantity=0,
    )
    payload.update(
        source_freshness={"status": "CURRENT"},
        purchase_scope="ALL_LINKED_DOCUMENTS",
        document_lifecycle={"purchase_receipt": "PRESENT", "purchase_invoice": "AWAITING_INVOICE"},
        receiving_work={
            "case_id": "LIVE-CASE",
            "purchase_order": "PO",
            "status": "CONFIGURED",
            "arrivals": [],
        },
        evidence_catalog={
            name: {"evidence_id": name, "provider": "ERPNext", "fields": []}
            for name in ("PO", "PR")
        },
    )
    return payload


def test_partial_receipt_before_invoice_does_not_invent_invoice_or_shortage():
    packet = live_recovery_packet(partial_receipt())
    assert packet["case_class"] == "receiving_operations"
    assert packet["expected_disposition"] == "SAFE_NOOP"
    sources = model_source_payloads(packet)
    erp = sources["read_erp_evidence"]
    assert erp["invoice"] is None and "duplicate_invoice_read" not in erp
    assert erp["quantities"]["receipt_posted_quantity"] == 1
    assert erp["quantities"]["outstanding_order_quantity"] == 39
    assert erp["document_lifecycle"]["purchase_invoice"] == "AWAITING_INVOICE"
    assert set(packet["evidence_ids"]) == {"PO", "PR"}
    assert "quality_records" not in sources["read_airtable_evidence"]
    assert "attempts" not in sources["read_celigo_evidence"]
    assert "expected_disposition" not in str(sources)


@pytest.mark.parametrize("status", ["NEEDS_REVIEW", "NEEDS_PHOTO", "UNAVAILABLE",
                                    "DRAFT_UNKNOWN", "SUBMIT_UNKNOWN"])
def test_unposted_arrival_review_is_not_cleared_by_other_posted_stock(status):
    payload = partial_receipt()
    payload["receiving_work"]["arrivals"] = [{
        "arrival_id": "A1", "status": status, "observed_quantity": 1,
        "photo_evidence_id": "photo-A1-v1",
        "events": [{"detail": "PO changed before draft"}],
    }, {"arrival_id": "A2", "status": "RECEIPT_SUBMITTED", "posted_quantity": 1}]
    packet = live_recovery_packet(payload)
    assert packet["expected_disposition"] == "NEEDS_EVIDENCE"
    sources = model_source_payloads(packet)
    assert sources["read_erp_evidence"]["quantities"]["receipt_posted_quantity"] == 1
    assert sources["read_collaboration_evidence"]["receiving_work"]["arrivals"][0][
        "status"] == status
    assert "photo-A1-v1" in sources["read_collaboration_evidence"]["evidence_ids"]
    assert sources["read_erp_evidence"]["quantities"]["receipt_unresolved"] == 0


def test_unknown_arrival_status_cannot_become_safe_noop():
    payload = partial_receipt()
    payload["receiving_work"]["arrivals"] = [{"status": "NEW_UNHANDLED_STATE"}]
    with pytest.raises(AdvisoryValidationError):
        live_recovery_packet(payload)


@pytest.mark.parametrize("status", ["AWAITING_PHOTO", "COUNT_CANDIDATE", "RECEIPT_PREPARED"])
def test_ordinary_intake_is_not_an_incident(status):
    payload = partial_receipt()
    payload["receiving_work"]["arrivals"] = [{"arrival_id": "A1", "status": status}]
    assert live_recovery_packet(payload)["expected_disposition"] == "SAFE_NOOP"


def test_order_before_first_receipt_has_no_receipt_derived_ids():
    payload = partial_receipt()
    payload["case_projection"]["case"]["purchase_receipt"] = ""
    payload["case_projection"]["case"]["quantities"].update(
        receipt_posted_quantity=0,
        physically_arrived=0,
        available=0,
        accepted_cumulative=0,
        outstanding_order_quantity=40,
    )
    payload["document_lifecycle"]["purchase_receipt"] = "AWAITING_RECEIPT"
    del payload["evidence_catalog"]["PR"]
    packet = live_recovery_packet(payload)
    assert packet["expected_disposition"] == "SAFE_NOOP"
    assert packet["evidence_ids"] == ("PO",)
    erp = model_source_payloads(packet)["read_erp_evidence"]
    assert erp["purchase_receipt"] is None
    assert "ledger_read" not in erp


@pytest.mark.parametrize(
    "change",
    [
        {"document_lifecycle": {}},
        {"document_lifecycle": {"purchase_invoice": "PRESENT"}},
        {
            "document_lifecycle": {
                "purchase_invoice": "AWAITING_INVOICE",
                "purchase_receipt": "AWAITING_RECEIPT",
            }
        },
        {"source_freshness": {"status": "UNAVAILABLE"}},
        {"purchase_scope": "CONFIGURED_DOCUMENTS"},
        {"evidence_catalog": {}},
    ],
)
def test_unknown_or_conflicting_lifecycle_fails_closed(change):
    payload = {**partial_receipt(), **change}
    with pytest.raises(AdvisoryValidationError):
        live_recovery_packet(payload)


@pytest.mark.parametrize(
    "quantity,amount,expected",
    [
        ("quality_hold", 1, "NEEDS_EVIDENCE"),
        ("receipt_unresolved", 1, "NEEDS_EVIDENCE"),
        ("receipt_posted_quantity", 41, "PROTECT"),
    ],
)
def test_receiving_exception_does_not_auto_authorize_stock(quantity, amount, expected):
    payload = partial_receipt()
    payload["case_projection"]["case"]["quantities"][quantity] = amount
    if quantity == "receipt_posted_quantity":
        payload["case_projection"]["case"]["quantities"].update(
            physically_arrived=amount,
            accepted_cumulative=amount,
            available=amount,
        )
    packet = live_recovery_packet(payload)
    assert packet["expected_disposition"] == expected


def test_catalog_citations_are_closed_and_original_invoice_flow_unchanged():
    payload = partial_receipt()
    before = deepcopy(payload)
    packet = live_recovery_packet(payload)
    source_ids = [e for s in model_source_payloads(packet).values() for e in s["evidence_ids"]]
    assert all(isinstance(e, str) and e for e in source_ids)
    assert set(source_ids) <= set(packet["evidence_ids"])
    assert payload == before
    assert live_recovery_packet(projection())["case_class"] == "source_investigation"


@pytest.mark.parametrize(
    "field,value", [("available", 9), ("case_balance", 0), ("delivered_quantity", -1)]
)
def test_inconsistent_accounting_cannot_report_normal_receiving(field, value):
    payload = partial_receipt()
    payload["case_projection"]["case"]["quantities"][field] = value
    assert live_recovery_packet(payload)["expected_disposition"] == "NEEDS_EVIDENCE"


def test_mean_comparison_is_not_presented_to_model_as_temporal_growth():
    payload = partial_receipt()
    payload["operational_history"] = {
        "case_id": "LIVE-CASE",
        "points": [],
        "baseline": {
            "metrics": {
                "received": {"previous_mean": 1 / 6, "change": 5 / 6, "change_percent": 500}
            }
        },
    }
    packet = live_recovery_packet(payload)
    visible = model_source_payloads(packet)["read_operational_history"]
    metric = visible["baseline"]["metrics"]["received"]
    assert "change" not in metric and "change_percent" not in metric
    assert metric["difference_from_previous_observation_mean"] == 5 / 6
    assert (
        packet["tool_payload"]["sources"]["read_operational_history"]["baseline"]["metrics"][
            "received"
        ]["change"]
        == 5 / 6
    )


def test_temporal_receiving_change_uses_comparable_endpoints_not_mean():
    from the_missing_20.agents.live_advisory import _temporal_changes

    row = {
        "case_id": "case",
        "source_id": "erp",
        "uom": "Box",
        "currency": "USD",
        "item_code": "item",
        "metric_version": "v1",
        "provenance": "external",
        "observation_kind": "live",
        "source_status": "CONNECTED",
    }
    history = {
        "points": [
            {**row, "evidence_id": "other-uom", "uom": "Nos", "metrics": {"received": 100}},
            {**row, "evidence_id": "first", "metrics": {"received": 0}},
            {
                **row,
                "evidence_id": "unavailable",
                "source_status": "UNAVAILABLE",
                "metrics": {"received": 99},
            },
            {**row, "evidence_id": "last", "metrics": {"received": 1}},
        ]
    }
    change = _temporal_changes(history)["received"]
    assert change["first_value"] == 0 and change["latest_value"] == 1
    assert change["net_change_from_first_to_latest"] == 1
    assert change["first_evidence_id"] == "first" and change["latest_evidence_id"] == "last"
    assert _temporal_changes({"points": [history["points"][-1]]}) == {}


@pytest.mark.parametrize(
    "facts",
    [
        {"accepted_cumulative": 40, "available": 40, "case_balance": 40},
        {"delivered_quantity": 2, "available": -1, "case_balance": -1},
    ],
)
def test_accepted_stock_and_issues_must_reconcile_to_actual_receipts(facts):
    payload = partial_receipt()
    payload["case_projection"]["case"]["quantities"].update(facts)
    assert live_recovery_packet(payload)["expected_disposition"] == "NEEDS_EVIDENCE"
