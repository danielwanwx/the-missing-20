from __future__ import annotations

from pathlib import Path

import pytest

from the_missing_20.agents.live_advisory import (
    SOURCE_TOOL_NAMES,
    AdvisoryDisposition,
    AdvisoryValidationError,
    LiveAdvisoryResult,
    admitted_evidence_ids,
    source_payloads,
    validate_advisory,
)
from the_missing_20.evaluation.real_strands_matrix import (
    assess_answer,
    expected_disposition,
    load_fixture_packet,
)


def test_expected_disposition_maps_deterministic_case_outcomes() -> None:
    assert expected_disposition("CLOSED") == ("RECOVERY_READY", "RECOVERY_COMPLETE")
    assert expected_disposition("PROTECTED") == "PROTECT"
    assert expected_disposition("NEEDS_EVIDENCE") == "NEEDS_EVIDENCE"
    assert expected_disposition("DENIED") == "DENY"
    assert expected_disposition("SAFE_NOOP") == "SAFE_NOOP"
    assert expected_disposition("EXECUTING_HARD_STOP") == "HARD_STOP"


def test_rubric_requires_tool_evidence_expected_disposition_and_no_write_claim() -> None:
    result = assess_answer(
        answer=(
            "Disposition: PROTECT\n"
            "Evidence IDs: case-04-genuine-short-shipment:erp-receipt\n"
            "No provider write was performed."
        ),
        tool_calls=SOURCE_TOOL_NAMES,
        expected="PROTECT",
        evidence_ids=("case-04-genuine-short-shipment:erp-receipt",),
    )

    assert result["passed"] is True
    assert result["checks"] == {
        "tool_called": True,
        "expected_disposition": True,
        "evidence_cited": True,
        "no_write_claim": True,
        "source_consistency": True,
    }


def test_rubric_accepts_the_safe_pre_or_post_recovery_state() -> None:
    result = assess_answer(
        answer=(
            "Disposition: RECOVERY_READY\n"
            "Evidence IDs: case-01-retryable-lock-main-path:failed-message\n"
            "No provider write was performed."
        ),
        tool_calls=SOURCE_TOOL_NAMES,
        expected=("RECOVERY_READY", "RECOVERY_COMPLETE"),
        evidence_ids=("case-01-retryable-lock-main-path:failed-message",),
    )

    assert result["passed"] is True


def test_rubric_flags_missing_evidence_and_a_claimed_write() -> None:
    result = assess_answer(
        answer="Disposition: DENY. I released the invoice.",
        tool_calls=(),
        expected="DENY",
        evidence_ids=("case-13-operator-requests-invoice-release:invoice",),
    )

    assert result["passed"] is False
    assert result["checks"]["tool_called"] is False
    assert result["checks"]["evidence_cited"] is False
    assert result["checks"]["no_write_claim"] is False


def test_rubric_rejects_transfer_contradiction_when_source_proves_completion() -> None:
    result = assess_answer(
        answer=(
            "Disposition: RECOVERY_READY. Evidence: transfer-1. "
            "Invoice remains held; the exact held lot is approved with no transfer."
        ),
        tool_calls=SOURCE_TOOL_NAMES,
        expected="RECOVERY_READY",
        evidence_ids=("transfer-1",),
        completed_quality_transfer=True,
    )

    assert result["passed"] is False
    assert result["checks"]["source_consistency"] is False


def test_rubric_rejects_transfer_not_present_wording() -> None:
    result = assess_answer(
        answer=(
            "Disposition: RECOVERY_READY. Evidence: transfer-1. "
            "Invoice remains held; exact held lot transfer not present."
        ),
        tool_calls=SOURCE_TOOL_NAMES,
        expected="RECOVERY_READY",
        evidence_ids=("transfer-1",),
        completed_quality_transfer=True,
    )

    assert result["passed"] is False
    assert result["checks"]["source_consistency"] is False


def test_fixture_packet_includes_predecision_control_context_without_outcome_leakage() -> None:
    packet = load_fixture_packet(Path("artifacts/golden/cases/06-expired-grant.json"))

    context = packet["tool_payload"]["sources"]["read_control_context"]
    assert context["temporal_hook"] == "ADVANCE_CLOCK_BEYOND_GRANT_TTL"
    assert context["request"]["receipt_principal_id"] == "operator-001"
    assert context["authorization_reuse"] == "NONE"
    assert context["evaluator_rejects"] is False
    assert context["receipt_principal_id"] == "operator-001"
    assert context["policy_gate"] == {
        "disposition": "DENY",
        "reason": "authorization grant expired",
    }
    assert context["evidence_ids"] == [
        "case-06-expired-grant:control-context",
        "case-06-expired-grant:policy-gate",
    ]
    assert "scenario_title" not in context
    assert "actual_outcome" not in packet["tool_payload"]
    assert "expected" not in packet["tool_payload"]
    assert "invariants" not in packet["tool_payload"]


def test_fixture_packet_separates_named_source_payloads() -> None:
    packet = load_fixture_packet(Path("artifacts/golden/cases/01-retryable-lock-main-path.json"))

    sources = source_payloads(packet)
    assert tuple(sources) == SOURCE_TOOL_NAMES
    assert sources["read_erp_evidence"]["invoice"]["state"] == "HELD"
    assert sources["read_celigo_evidence"]["failed_message"]["retry_eligible"] is True
    assert sources["read_celigo_evidence"]["records"][0]["fields"]["status"] == "FAILED"
    rendered = str(sources)
    assert "actual_outcome" not in rendered
    assert "required_invariants" not in rendered


def test_fixture_packet_resolves_closed_pre_and_post_action_states() -> None:
    recovery_ready = load_fixture_packet(
        Path("artifacts/golden/cases/01-retryable-lock-main-path.json")
    )
    recovery_complete = load_fixture_packet(
        Path("artifacts/golden/cases/02-receipt-already-posted.json")
    )

    assert recovery_ready["expected_disposition"] == "RECOVERY_READY"
    assert "Manager approval" in recovery_ready["expected_safe_next_step"]
    assert recovery_complete["expected_disposition"] == "RECOVERY_COMPLETE"
    assert "No recovery action remains" in recovery_complete["expected_safe_next_step"]


@pytest.mark.parametrize(
    ("case_name", "expected_gate"),
    (
        ("07-replayed-authorization", "DENY"),
        ("04-genuine-short-shipment", "PROTECT"),
        ("08-old-case-version", "DENY"),
        ("09-tampered-parameters", "DENY"),
        ("10-duplicate-executor-request", "SAFE_NOOP"),
        ("12-receipt-postcondition-fails", "HARD_STOP"),
        ("13-operator-requests-invoice-release", "DENY"),
        ("14-ap-requests-receipt-restart", "DENY"),
    ),
)
def test_fixture_packet_exposes_deterministic_authorization_gates(
    case_name: str, expected_gate: str
) -> None:
    packet = load_fixture_packet(Path(f"artifacts/golden/cases/{case_name}.json"))

    gate = packet["tool_payload"]["sources"]["read_control_context"]["policy_gate"]

    assert gate["disposition"] == expected_gate


def test_advisory_validation_requires_every_source_and_exact_citations() -> None:
    packet = load_fixture_packet(Path("artifacts/golden/cases/01-retryable-lock-main-path.json"))
    result = LiveAdvisoryResult(
        disposition=AdvisoryDisposition.RECOVERY_COMPLETE,
        evidence_ids=("case-01-retryable-lock-main-path:failed-message",),
        reason="The failed message is retry eligible after its document lock cleared.",
        safe_next_step="Hand the approved recovery intent to the deterministic control plane.",
        write_performed=False,
    )

    validate_advisory(
        result,
        calls=SOURCE_TOOL_NAMES,
        evidence_ids=admitted_evidence_ids(packet),
    )
    with pytest.raises(AdvisoryValidationError, match="required source"):
        validate_advisory(
            result,
            calls=("read_control_context",),
            evidence_ids=admitted_evidence_ids(packet),
        )
    with pytest.raises(AdvisoryValidationError, match="exactly once"):
        validate_advisory(
            result,
            calls=SOURCE_TOOL_NAMES + ("read_erp_evidence",),
            evidence_ids=admitted_evidence_ids(packet),
        )
