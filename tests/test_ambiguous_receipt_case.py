from __future__ import annotations

import pytest

from the_missing_20.domain.ambiguous_receipt import (
    AmbiguousReceiptCase,
    CaseDisposition,
    IntegrationOutcome,
    QualityDisposition,
    primary_case,
)


def _replace(case: AmbiguousReceiptCase, **changes: object) -> AmbiguousReceiptCase:
    return AmbiguousReceiptCase.model_validate({**case.model_dump(), **changes})


def test_primary_case_requires_exactly_two_bounded_recovery_actions_before_revalidation() -> None:
    case = primary_case()

    assert case.disposition() is CaseDisposition.RECOVERY_READY
    assert case.allowed_actions() == (
        "POST_IDEMPOTENT_RECEIPT",
        "TRANSFER_APPROVED_QUALITY_STOCK",
        "REVALIDATE_LINKED_INVOICE",
    )
    projection = case.evidence_projection()
    assert projection["quantities"] == {
        "physically_arrived": 100,
        "available": 80,
        "quality_hold": 8,
        "receipt_unresolved": 12,
    }
    assert projection["receipt_business_key"] == "RCPT-4817-L2-001"


def test_unknown_integration_result_cannot_authorize_recovery_before_erp_key_read() -> None:
    case = _replace(primary_case(), erp_receipt_key_found=None)

    assert case.integration_outcome is IntegrationOutcome.UNKNOWN
    assert case.disposition() is CaseDisposition.NEEDS_EVIDENCE
    assert case.allowed_actions() == ()


def test_existing_erp_key_turns_a_retryable_signal_into_reconcile_only() -> None:
    case = _replace(primary_case(), erp_receipt_key_found=True)

    assert case.disposition() is CaseDisposition.RECONCILE_ONLY
    assert case.allowed_actions() == ()


@pytest.mark.parametrize(
    "disposition",
    (QualityDisposition.PENDING, QualityDisposition.REJECTED, QualityDisposition.EXPIRED),
)
def test_nonapproved_quality_evidence_preserves_hold(disposition: QualityDisposition) -> None:
    case = _replace(primary_case(), quality_disposition=disposition)

    assert case.disposition() is CaseDisposition.SAFE_STOP
    assert case.allowed_actions() == ()


def test_case_rejects_an_aggregate_that_hides_missing_units() -> None:
    with pytest.raises(ValueError, match="must total arrival"):
        _replace(primary_case(), available_quantity=81)


def test_acknowledged_integration_requires_the_erp_business_key() -> None:
    with pytest.raises(ValueError, match="requires the ERP receipt key"):
        _replace(
            primary_case(),
            integration_outcome=IntegrationOutcome.ACKNOWLEDGED,
            erp_receipt_key_found=False,
        )
