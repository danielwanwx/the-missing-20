from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from the_missing_20.domain.models import (
    ActionGrant,
    ActionTool,
    Approval,
    ApprovalDecision,
    Case,
    ClosureFacts,
    Discrepancy,
    EvidenceItem,
    EvidenceProvenance,
    EvidenceSourceType,
    HumanRole,
    InvoiceState,
    MessageResolution,
)
from the_missing_20.domain.states import CaseStatus

NOW = datetime(2026, 8, 25, 16, 0, tzinfo=UTC)


def test_contracts_are_frozen_and_forbid_extra_fields() -> None:
    discrepancy = Discrepancy(
        expected_quantity=100,
        observed_quantity=80,
        missing_quantity=20,
        unit="EA",
    )

    with pytest.raises(ValidationError, match="frozen"):
        discrepancy.missing_quantity = 19

    with pytest.raises(ValidationError, match="Extra inputs"):
        Discrepancy(
            expected_quantity=100,
            observed_quantity=80,
            missing_quantity=20,
            unit="EA",
            target_status="CLOSED",  # type: ignore[call-arg]
        )


def test_discrepancy_rejects_inconsistent_quantity_math() -> None:
    with pytest.raises(ValidationError, match="missing_quantity"):
        Discrepancy(
            expected_quantity=100,
            observed_quantity=80,
            missing_quantity=10,
            unit="EA",
        )


def test_case_rejects_time_travel() -> None:
    with pytest.raises(ValidationError, match="updated_at"):
        Case(
            case_id="case-001",
            case_version=0,
            scenario_id="scenario-001",
            status=CaseStatus.OPEN,
            discrepancy=Discrepancy(
                expected_quantity=100,
                observed_quantity=80,
                missing_quantity=20,
                unit="EA",
            ),
            current_evidence_revision=0,
            created_at=NOW,
            updated_at=NOW - timedelta(seconds=1),
        )


def test_contracts_reject_naive_timestamps() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        Case(
            case_id="case-001",
            case_version=0,
            scenario_id="scenario-001",
            status=CaseStatus.OPEN,
            discrepancy=Discrepancy(
                expected_quantity=100,
                observed_quantity=80,
                missing_quantity=20,
                unit="EA",
            ),
            current_evidence_revision=0,
            created_at=datetime(2026, 8, 25, 16, 0),
            updated_at=NOW,
        )


def test_identifiers_cannot_be_whitespace_only() -> None:
    with pytest.raises(ValidationError, match="at least 1 character"):
        Case(
            case_id="   ",
            case_version=0,
            scenario_id="scenario-001",
            status=CaseStatus.OPEN,
            discrepancy=Discrepancy(
                expected_quantity=100,
                observed_quantity=80,
                missing_quantity=20,
                unit="EA",
            ),
            current_evidence_revision=0,
            created_at=NOW,
            updated_at=NOW,
        )


def test_action_grant_requires_a_future_expiry() -> None:
    with pytest.raises(ValidationError, match="expires_at"):
        ActionGrant(
            authorization_id="authorization-001",
            case_id="case-001",
            trace_id="trace-001",
            case_version=1,
            principal_id="operator-001",
            role=HumanRole.INTEGRATION_OPERATOR,
            tool=ActionTool.RESTART_RECEIPT_MESSAGE,
            complete_parameters={"message_id": "message-020"},
            evidence_digest="evidence-digest",
            action_digest="action-digest",
            issued_at=NOW,
            expires_at=NOW,
            signature="signature",
        )


@pytest.mark.parametrize(
    ("role", "tool"),
    [
        (HumanRole.AP_APPROVER, ActionTool.RESTART_RECEIPT_MESSAGE),
        (HumanRole.INTEGRATION_OPERATOR, ActionTool.RELEASE_INVOICE),
    ],
)
def test_approval_rejects_cross_role_tools(role: HumanRole, tool: ActionTool) -> None:
    with pytest.raises(ValidationError, match="cannot authorize tool"):
        Approval(
            approval_id="approval-001",
            case_id="case-001",
            trace_id="trace-001",
            case_version=1,
            principal_id="principal-001",
            role=role,
            tool=tool,
            parameters_digest="parameters-digest",
            decision=ApprovalDecision.APPROVED,
            decided_at=NOW,
        )


@pytest.mark.parametrize(
    ("role", "tool"),
    [
        (HumanRole.AP_APPROVER, ActionTool.RESTART_RECEIPT_MESSAGE),
        (HumanRole.INTEGRATION_OPERATOR, ActionTool.RELEASE_INVOICE),
    ],
)
def test_action_grant_rejects_cross_role_tools(role: HumanRole, tool: ActionTool) -> None:
    with pytest.raises(ValidationError, match="cannot authorize tool"):
        ActionGrant(
            authorization_id="authorization-001",
            case_id="case-001",
            trace_id="trace-001",
            case_version=1,
            principal_id="principal-001",
            role=role,
            tool=tool,
            complete_parameters={"record_id": "record-001"},
            evidence_digest="evidence-digest",
            action_digest="action-digest",
            issued_at=NOW,
            expires_at=NOW + timedelta(minutes=5),
            signature="signature",
        )


def test_json_contracts_reject_non_finite_numbers() -> None:
    with pytest.raises(ValidationError, match="finite number"):
        EvidenceItem(
            evidence_id="evidence-001",
            case_id="case-001",
            trace_id="trace-001",
            subject="queue message",
            source_type=EvidenceSourceType.FAILED_MESSAGE_QUEUE,
            source_record_id="message-001",
            observed_at=NOW,
            content_digest="content-digest",
            admitted_fields={"invalid_measurement": float("nan")},
            provenance=EvidenceProvenance(
                source_system="synthetic-queue",
                collection_method="typed-read-tool",
                collected_by="investigator",
            ),
        )

    with pytest.raises(ValidationError, match="finite number"):
        ActionGrant(
            authorization_id="authorization-001",
            case_id="case-001",
            trace_id="trace-001",
            case_version=1,
            principal_id="operator-001",
            role=HumanRole.INTEGRATION_OPERATOR,
            tool=ActionTool.RESTART_RECEIPT_MESSAGE,
            complete_parameters={"quantity": float("inf")},
            evidence_digest="evidence-digest",
            action_digest="action-digest",
            issued_at=NOW,
            expires_at=NOW + timedelta(minutes=5),
            signature="signature",
        )


@pytest.mark.parametrize(
    ("receipt", "duplicates", "message", "invoice", "expected"),
    [
        (100, 0, MessageResolution.CLEARED, InvoiceState.RELEASED, True),
        (100, 0, MessageResolution.SAFELY_CONSUMED, InvoiceState.RELEASED, True),
        (80, 0, MessageResolution.CLEARED, InvoiceState.RELEASED, False),
        (100, 1, MessageResolution.CLEARED, InvoiceState.RELEASED, False),
        (100, 0, MessageResolution.UNRESOLVED, InvoiceState.RELEASED, False),
        (100, 0, MessageResolution.CLEARED, InvoiceState.HELD, False),
    ],
)
def test_closure_facts_are_explicit(
    receipt: int,
    duplicates: int,
    message: MessageResolution,
    invoice: InvoiceState,
    expected: bool,
) -> None:
    facts = ClosureFacts(
        expected_receipt_quantity=100,
        erp_receipt_quantity=receipt,
        duplicate_material_document_count=duplicates,
        message_resolution=message,
        invoice_state=invoice,
    )

    assert facts.satisfies_closure() is expected
