"""Mechanical completeness is a floor, not semantic/business acceptance."""

import pytest
from pydantic import ValidationError

from the_missing_20.agents.live_advisory import LiveAdvisoryResult, _repair_instruction
from the_missing_20.agents.receiving_advisory import receiving_answer_gaps


def sources(count=2):
    return {
        "read_erp_evidence": {
            "uom": "Box",
            "quantities": {"ordered": 40, "physically_arrived": 1,
                           "receipt_posted_quantity": 1},
            "records": [{"stock_entries": [{"voucher_no": "PR-5", "name": "SLE-9"}]}],
        },
        "read_operational_history": {
            "baseline": {"minimum_samples": 3, "metrics": {
                "received": {"sample_count": count, "status": "INSUFFICIENT_DATA"}}},
        },
    }


def test_compound_quantity_answer_cannot_omit_all_requested_numbers():
    gaps = receiving_answer_gaps(
        "Compare ordered, physically received and posted quantities.",
        "Arrival one needs review and arrival two is posted.", sources(), None)
    assert "requested ordered/received/posted quantities with source UOM" in gaps
    assert not receiving_answer_gaps(
        "Compare ordered, physically received and posted quantities.",
        "Ordered 40 Box, received 1 Box, posted 1 Box.", sources(), None)


def test_record_answer_requires_linked_receipt_and_stock_row_in_prose():
    q = "Which records independently verify that receipt, and should we retry it?"
    assert "requested receipt and its stock-ledger identifier" in receiving_answer_gaps(
        q, "No need to retry the verified receipt.", sources(), None)
    assert not receiving_answer_gaps(
        q, "PR-5 and SLE-9 verify the receipt. Do not retry it.", sources(), None)
    assert receiving_answer_gaps(q, "PR-5 and SLE-OTHER. Do not retry.", sources(), None)


def test_baseline_uses_selected_metric_sample_count_not_hardcoded_fixture():
    q = "Show receiving trend and baseline."
    assert "requested baseline comparable sample count and required minimum" in (
        receiving_answer_gaps(q, "Insufficient baseline.", sources(), "received"))
    assert not receiving_answer_gaps(q, "Only 2 prior samples; 3 required.", sources(), "received")
    assert receiving_answer_gaps(q, "Only 2 prior samples; 3 required.", sources(1), "received")


def test_no_extra_obligations_for_unrelated_questions_or_unavailable_records():
    assert not receiving_answer_gaps(
        "What needs attention?", "Review arrival one.", sources(), None)
    assert not receiving_answer_gaps("Which records verify this receipt?", "Unavailable.", {}, None)
    assert not receiving_answer_gaps("Explain baseline.", "No metric selected.", sources(), None)


def test_supported_identifier_must_not_match_a_longer_unrelated_identifier():
    q = "Which records verify the receipt?"
    assert receiving_answer_gaps(q, "PR-50 and SLE-90 prove it.", sources(), None)


def test_ledger_omission_repair_points_to_source_fields_not_an_invented_answer():
    feedback = _repair_instruction(
        "Answer omitted requested receipt and its stock-ledger identifier", [])
    assert "stock_entries[]" in feedback
    assert "voucher_no and name" in feedback
    assert "evidence_ids restricted" in feedback
    assert "SLE-9" not in feedback


def test_numeric_equivalence_is_not_an_identifier_substring():
    q = "Compare ordered, received and posted quantities."
    assert not receiving_answer_gaps(
        q, "Ordered 40.0 Box, received 1.0 Box and posted 1.0 Box.", sources(), None)
    assert receiving_answer_gaps(q, "40.5 Box and 1.5 Box.", sources(), None)
    assert receiving_answer_gaps(q, "PR-40 and SLE-1 in Box.", sources(), None)


def test_omitted_chart_selection_does_not_bypass_clear_receiving_baseline_request():
    assert receiving_answer_gaps(
        "Show receiving trend and baseline.", "Insufficient baseline.", sources(), None)
    assert not receiving_answer_gaps(
        "Show receiving baseline.", "Only 2 prior samples; 3 needed.", sources(), None)


def test_no_invoice_cannot_be_rendered_as_an_open_or_paid_invoice():
    packet = sources()
    packet["read_erp_evidence"]["invoice"] = None
    for state in ("open", "paid", "closed", "held", "on hold"):
        assert receiving_answer_gaps(
            "What is the receiving status?", f"The invoice is {state}.", packet, None)
    assert not receiving_answer_gaps(
        "What is the receiving status?", "No supplier invoice exists yet.", packet, None)


def test_suggested_questions_cannot_duplicate_with_cosmetic_changes():
    with pytest.raises(ValidationError, match="follow-up questions must be distinct"):
        LiveAdvisoryResult.model_validate({
            "disposition": "SAFE_NOOP", "evidence_ids": ["PR-5"],
            "reason": "Receipt is posted.", "safe_next_step": "Inspect the receipt.",
            "write_performed": False,
            "follow_up_questions": ["Show the ledger?", "show the ledger!"],
        })


def test_available_baseline_cannot_be_omitted_in_favor_of_only_net_change():
    packet = sources()
    packet["read_operational_history"]["baseline"]["metrics"]["received"] = {
        "status": "AVAILABLE", "sample_count": 3, "previous_mean": 2 / 3,
    }
    q = "Explain receiving trend and historical baseline."
    assert receiving_answer_gaps(q, "Net change is 2 Box; no revenue proof.", packet, "received")
    assert not receiving_answer_gaps(
        q, "Prior mean is 0.67 Box across 3 observations, net change 2 Box.", packet, "received")
