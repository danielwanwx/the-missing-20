import copy
import json

import pytest

from the_missing_20.adapters.investigation_case_sources import investigation_packet
from the_missing_20.agents.investigation_effect_facts import investigation_effect_facts
from the_missing_20.agents.live_advisory import model_source_payloads


@pytest.mark.parametrize(
    "variant,present",
    [
        ("uncommitted_receipt", False),
        ("lost_ack", True),
        ("lookup_unavailable", None),
    ],
)
def test_transport_and_destination_are_separate(variant, present):
    sources = model_source_payloads(investigation_packet(variant))
    before = copy.deepcopy(sources)
    view = investigation_effect_facts(sources)
    assert view["receipt_attempt"]["transport_response"] == "TIMEOUT"
    assert view["destination_lookup"]["present"] is present
    assert sources == before
    assert view["destination_lookup"]["evidence_id"] == "ERP-READ-4817"
    for forbidden in (
        "RECOVERY_READY",
        "expected_disposition",
        "recommended_action",
        "allowed_actions",
    ):
        assert forbidden not in json.dumps(view)


@pytest.mark.parametrize(
    "field,value",
    [("po", "OTHER-PO"), ("line", 2), ("pagination_complete", False)],
)
def test_wrong_or_incomplete_lookup_cannot_prove_absence(field, value):
    sources = model_source_payloads(investigation_packet())
    sources["read_erp_evidence"]["ledger_read"][field] = value
    assert investigation_effect_facts(sources)["destination_lookup"]["present"] is None


@pytest.mark.parametrize(
    "status,lot,present",
    [
        ("COMPLETE", "LOT-B", False),
        ("UNAVAILABLE", "LOT-B", None),
        ("COMPLETE", "OTHER", None),
    ],
)
def test_quality_lookup_scope(status, lot, present):
    sources = model_source_payloads(investigation_packet())
    sources["read_airtable_evidence"]["transfer_read"].update(status=status, lot=lot)
    row = investigation_effect_facts(sources)["quality_lots"][0]
    assert row["held_quantity"] == 8
    assert row["approval_records"] == [
        {"evidence_id": "QA-901", "quantity": 8, "disposition": "APPROVED"}
    ]
    assert row["transfer_lookup"]["present"] is present


def test_mismatched_approval_and_existing_transfer_are_not_repaired():
    sources = model_source_payloads(investigation_packet("transfer_already_present"))
    sources["read_airtable_evidence"]["quality_records"][0]["quantity"] = 7
    row = investigation_effect_facts(sources)["quality_lots"][0]
    assert row["approval_records"][0]["quantity"] == 7
    assert row["transfer_lookup"]["present"] is True
    assert row["transfer_lookup"]["matching_record_ids"]


def test_relationship_view_retains_scope_and_conversion_evidence():
    sources = model_source_payloads(investigation_packet())
    view = investigation_effect_facts(sources)

    assert view["source_observed_at"]["read_erp_evidence"] == "2026-09-05T12:00:00Z"
    assert view["destination_lookup"]["scope"] == {
        "purchase_order": "PO-4817",
        "line": 1,
    }
    assert view["destination_lookup"]["requested_scope"] == {
        "purchase_order": "PO-4817",
        "line": 1,
    }
    assert view["destination_lookup"]["observed_at_source"] == "source"
    assert view["receipt_attempt"]["conversion_factor_to_po_uom"] == 1
    assert view["receipt_attempt"]["normalized_quantity"] == 12


@pytest.mark.parametrize("field,value", [("asn", "OTHER-ASN"), ("business_key", "")])
def test_attempt_scope_or_key_gap_keeps_destination_unknown(field, value):
    sources = model_source_payloads(investigation_packet())
    sources["read_celigo_evidence"]["attempts"][0][field] = value

    assert investigation_effect_facts(sources)["destination_lookup"]["present"] is None


def test_transfer_record_from_incomplete_read_stays_unknown():
    sources = model_source_payloads(investigation_packet())
    transfer = sources["read_airtable_evidence"]["transfer_read"]
    transfer.update(status="UNAVAILABLE", records=[{"id": "XFER-1", "lot": "LOT-B"}])

    row = investigation_effect_facts(sources)["quality_lots"][0]
    assert row["transfer_lookup"]["matching_record_ids"] == ["XFER-1"]
    assert row["transfer_lookup"]["present"] is None


def test_non_finite_quality_quantity_does_not_become_a_fact():
    sources = model_source_payloads(investigation_packet())
    sources["read_erp_evidence"]["ledger_read"]["records"][1]["quantity"] = float("nan")

    row = investigation_effect_facts(sources)["quality_lots"][0]
    assert row["held_quantity"] is None
