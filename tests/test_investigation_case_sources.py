import json

import pytest

from the_missing_20.adapters.investigation_case_sources import (
    correlate_investigation_sources,
    evaluate_investigation_policy,
    investigation_packet,
)
from the_missing_20.agents.live_advisory import model_source_payloads
from the_missing_20.domain.ambiguous_receipt import primary_case


@pytest.mark.parametrize(
    "variant,expected",
    [
        ("uncommitted_receipt", "RECOVERY_READY"),
        ("lost_ack", "DENY"),
        ("wrong_quality_lot", "DENY"),
        ("lookup_unavailable", "NEEDS_EVIDENCE"),
        ("physical_shortage", "DENY"),
        ("transfer_already_present", "DENY"),
        ("evidence_conflict", "NEEDS_EVIDENCE"),
        ("duplicate_invoice", "DENY"),
        ("unit_price_variance", "DENY"),
        ("uom_conversion_missing", "NEEDS_EVIDENCE"),
        ("po_revision_race", "NEEDS_EVIDENCE"),
        ("supplier_hold", "DENY"),
        ("lot_trace_mismatch", "DENY"),
        ("normal_complete", "RECOVERY_COMPLETE"),
    ],
)
def test_same_alert_has_distinct_source_evidence_and_no_answer_label(variant, expected):
    packet = investigation_packet(variant)
    sources = model_source_payloads(packet)
    assert packet["expected_disposition"] == expected
    assert (
        sources["read_control_context"]
        == model_source_payloads(investigation_packet())["read_control_context"]
    )
    serialized = json.dumps(sources)
    for forbidden in (
        "expected_disposition",
        "expected_safe_next_step",
        "receipt_unresolved",
        "allowed_actions",
        "RECOVERY_READY",
    ):
        assert forbidden not in serialized
    assert "scans" not in sources["read_erp_evidence"]
    assert "quality_records" not in sources["read_erp_evidence"]
    assert "attempts" not in sources["read_erp_evidence"]


def test_lost_ack_is_distinguished_by_authoritative_ledger_not_timeout():
    absent = model_source_payloads(investigation_packet())
    present = model_source_payloads(investigation_packet("lost_ack"))
    assert absent["read_celigo_evidence"] == present["read_celigo_evidence"]
    assert len(absent["read_erp_evidence"]["ledger_read"]["records"]) == 2
    assert present["read_erp_evidence"]["ledger_read"]["records"][-1]["business_key"] == (
        "RCPT-4817-L2"
    )
    for record in present["read_erp_evidence"]["ledger_read"]["records"]:
        assert record["id"] in present["read_erp_evidence"]["evidence_ids"]


def test_unavailable_read_is_not_a_complete_empty_result():
    source = model_source_payloads(investigation_packet("lookup_unavailable"))
    ledger = source["read_erp_evidence"]["ledger_read"]
    assert ledger["records"] == []
    assert ledger["status"] == "UNAVAILABLE"
    assert ledger["pagination_complete"] is False


def test_quality_approval_for_equal_quantity_wrong_lot_is_not_eligible():
    source = model_source_payloads(investigation_packet("wrong_quality_lot"))
    exact, unrelated = source["read_airtable_evidence"]["quality_records"]
    assert exact["quantity"] == unrelated["quantity"]
    assert exact["lot"] != unrelated["lot"]
    assert exact["disposition"] == "PENDING"
    assert unrelated["disposition"] == "APPROVED"


@pytest.mark.parametrize(
    "variant,key_present,quality_quantity,quality_status,ledger_status",
    [
        ("uncommitted_receipt", False, 8, ("APPROVED",), "COMPLETE"),
        ("lost_ack", True, 8, ("APPROVED",), "COMPLETE"),
        ("wrong_quality_lot", False, 8, ("PENDING",), "COMPLETE"),
        ("lookup_unavailable", None, 0, (), "UNAVAILABLE"),
    ],
)
def test_deterministic_correlation_exposes_observations_not_action(
    variant, key_present, quality_quantity, quality_status, ledger_status
):
    sources = model_source_payloads(investigation_packet(variant))
    findings = correlate_investigation_sources(sources)
    observed = findings["observations"]
    assert observed["physical_received_quantity"] == 100
    assert observed["integration_attempt_quantity"] == 12
    assert observed["erp_quality_inspection_quantity"] == quality_quantity
    assert observed["integration_business_key_present_in_erp"] is key_present
    assert observed["exact_held_lot_quality_dispositions"] == quality_status
    assert observed["ledger_read_status"] == ledger_status
    serialized = json.dumps(findings)
    for forbidden in ("RECOVERY_READY", "DENY", "NEEDS_EVIDENCE", "safe_next_step"):
        assert forbidden not in serialized


@pytest.mark.parametrize(
    "variant,expected",
    [
        ("uncommitted_receipt", "RECOVERY_READY"),
        ("lost_ack", "DENY"),
        ("wrong_quality_lot", "DENY"),
        ("lookup_unavailable", "NEEDS_EVIDENCE"),
    ],
)
def test_deterministic_policy_gate_classifies_correlated_facts(variant, expected):
    findings = correlate_investigation_sources(model_source_payloads(investigation_packet(variant)))
    decision = evaluate_investigation_policy(findings)
    assert decision["disposition"] == expected
    assert decision["write_authority"] == "NONE"
    assert decision["manager_approval_required"] is (expected == "RECOVERY_READY")


@pytest.mark.parametrize(
    ("variant", "expected"),
    [
        ("physical_shortage", "DENY"),
        ("evidence_conflict", "NEEDS_EVIDENCE"),
        ("normal_complete", "RECOVERY_COMPLETE"),
    ],
)
def test_scoped_case_overlay_preserves_each_hidden_cause(variant, expected):
    case = primary_case().evidence_projection()
    packet = investigation_packet(variant, case=case)
    sources = model_source_payloads(packet)
    findings = correlate_investigation_sources(sources)
    decision = evaluate_investigation_policy(findings)

    assert decision["disposition"] == expected


def test_physical_shortage_keeps_order_expectation_separate_from_scans():
    case = {
        **primary_case().evidence_projection(),
        "quantities": {
            "physically_arrived": 80,
            "available": 72,
            "quality_hold": 8,
            "receipt_unresolved": 0,
        },
    }

    sources = model_source_payloads(investigation_packet("physical_shortage", case=case))

    assert sources["read_erp_evidence"]["purchase_order"]["ordered"] == 100
    assert sources["read_erp_evidence"]["invoice"]["quantity"] == 100
    assert sum(row["quantity"] for row in sources["read_collaboration_evidence"]["scans"]) == 80


@pytest.mark.parametrize(
    ("variant", "expected_check"),
    [
        ("duplicate_invoice", "duplicate_supplier_invoice_absent"),
        ("unit_price_variance", "commercial_terms_match"),
        ("uom_conversion_missing", "uom_conversion_known"),
        ("po_revision_race", "source_po_revision_matches"),
        ("supplier_hold", "supplier_active"),
        ("lot_trace_mismatch", "lot_trace_matches"),
    ],
)
def test_enterprise_exception_variants_fail_their_specific_control(
    variant: str, expected_check: str
) -> None:
    sources = model_source_payloads(investigation_packet(variant))
    findings = correlate_investigation_sources(sources)
    decision = evaluate_investigation_policy(findings)

    assert decision["checks"][expected_check] is False


def test_scoped_normal_complete_reconstructs_a_single_reconciled_ledger_row():
    packet = investigation_packet("normal_complete", case=primary_case().evidence_projection())
    erp = model_source_payloads(packet)["read_erp_evidence"]

    assert erp["invoice"]["status"] == "OPEN"
    assert erp["ledger_read"]["records"] == [
        {
            "id": "MAT-401",
            "po": "PO-4817",
            "line": 1,
            "quantity": 100,
            "stock_type": "AVAILABLE",
            "business_key": "RCPT-4817-L2-001",
        }
    ]


@pytest.mark.parametrize("status,scope", [("UNAVAILABLE", "LOT-B"), ("COMPLETE", "LOT-X")])
def test_quality_transfer_absence_requires_complete_exact_lot_lookup(status, scope):
    sources = model_source_payloads(investigation_packet())
    lookup = sources["read_airtable_evidence"]["transfer_read"]
    lookup.update(status=status, lot=scope, records=[])
    findings = correlate_investigation_sources(sources)
    assert findings["observations"]["exact_held_lot_transfer_present"] is None
    policy = evaluate_investigation_policy(findings)
    assert policy["disposition"] == "NEEDS_EVIDENCE"
    assert policy["write_authority"] == "NONE"
    assert policy["manager_approval_required"] is False


@pytest.mark.parametrize("quantity", [7, 9, None, "8", True, float("nan"), float("inf")])
def test_quality_approval_must_cover_exact_held_quantity(quantity):
    sources = model_source_payloads(investigation_packet())
    sources["read_airtable_evidence"]["quality_records"][0]["quantity"] = quantity
    policy = evaluate_investigation_policy(correlate_investigation_sources(sources))
    assert policy["disposition"] != "RECOVERY_READY"
    assert policy["checks"]["exact_held_lot_approved"] is False
    assert policy["write_authority"] == "NONE"


@pytest.mark.parametrize("change", ["missing_quantity", "duplicate_approval", "multiple_lots"])
def test_unsupported_quality_evidence_requests_evidence(change):
    sources = model_source_payloads(investigation_packet())
    quality = sources["read_airtable_evidence"]
    if change == "missing_quantity":
        quality["quality_records"][0].pop("quantity")
    elif change == "duplicate_approval":
        quality["quality_records"].append(dict(quality["quality_records"][0]))
    else:
        ledger = sources["read_erp_evidence"]["ledger_read"]
        extra = dict(
            next(row for row in ledger["records"] if row["stock_type"] == "QUALITY_INSPECTION")
        )
        extra.update(lot="LOT-C", quantity=1, id="SECOND-HELD")
        ledger["records"].append(extra)
    policy = evaluate_investigation_policy(correlate_investigation_sources(sources))
    assert policy["disposition"] == "NEEDS_EVIDENCE"
    assert policy["manager_approval_required"] is False


def test_completed_inventory_does_not_require_unused_quality_lookup():
    sources = model_source_payloads(investigation_packet("normal_complete"))
    sources["read_airtable_evidence"]["transfer_read"]["status"] = "UNAVAILABLE"
    assert (
        evaluate_investigation_policy(correlate_investigation_sources(sources))["disposition"]
        == "RECOVERY_COMPLETE"
    )


def test_receipt_only_gap_does_not_require_quality_approval_or_lookup():
    sources = model_source_payloads(investigation_packet())
    for row in sources["read_erp_evidence"]["ledger_read"]["records"]:
        if row["stock_type"] == "QUALITY_INSPECTION":
            row["stock_type"] = "AVAILABLE"
    sources["read_airtable_evidence"]["transfer_read"]["status"] = "UNAVAILABLE"
    policy = evaluate_investigation_policy(correlate_investigation_sources(sources))
    assert policy["disposition"] == "RECOVERY_READY"
    assert policy["write_authority"] == "NONE"
    assert "quality transfer" not in policy["reason"].lower()


def test_explicit_pending_quality_is_denied_even_without_quantity():
    sources = model_source_payloads(investigation_packet("wrong_quality_lot"))
    sources["read_airtable_evidence"]["quality_records"][0].pop("quantity")
    policy = evaluate_investigation_policy(correlate_investigation_sources(sources))
    assert policy["disposition"] == "DENY"
