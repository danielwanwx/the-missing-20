from datetime import UTC, datetime, timedelta
from itertools import product

import pytest
from pydantic import ValidationError

from the_missing_20.domain.errors import (
    InvalidEventPayload,
    InvalidTransition,
    VersionConflict,
)
from the_missing_20.domain.events import TransitionCommand
from the_missing_20.domain.models import (
    ActionTool,
    Case,
    ClosureFacts,
    ConfidenceBand,
    Discrepancy,
    EvaluationDecision,
    EvaluationResult,
    EvidenceItem,
    EvidenceProvenance,
    EvidenceSourceType,
    HypothesisConclusion,
    HypothesisResult,
    HypothesisType,
    InvestigationAssessment,
    InvestigationDecision,
    InvoiceState,
    MessageResolution,
)
from the_missing_20.domain.state_machine import advance_case
from the_missing_20.domain.states import TRANSITIONS, CaseStatus, TransitionEvent

NOW = datetime(2026, 8, 25, 16, 0, tzinfo=UTC)

EXPECTED_TRANSITIONS: dict[tuple[CaseStatus, TransitionEvent], CaseStatus] = {
    (CaseStatus.OPEN, TransitionEvent.INVESTIGATION_STARTED): CaseStatus.INVESTIGATING,
    (CaseStatus.INVESTIGATING, TransitionEvent.EVIDENCE_REQUIRED): CaseStatus.NEEDS_EVIDENCE,
    (CaseStatus.NEEDS_EVIDENCE, TransitionEvent.EVIDENCE_ADMITTED): CaseStatus.INVESTIGATING,
    (
        CaseStatus.RECEIPT_ACTION_AUTHORIZED,
        TransitionEvent.EVIDENCE_ADMITTED,
    ): CaseStatus.INVESTIGATING,
    (
        CaseStatus.INVESTIGATING,
        TransitionEvent.INVESTIGATION_ASSESSED,
    ): CaseStatus.INVESTIGATING,
    (CaseStatus.INVESTIGATING, TransitionEvent.ACTION_PROTECTED): CaseStatus.PROTECTED,
    (
        CaseStatus.INVESTIGATING,
        TransitionEvent.RECEIPT_ALREADY_POSTED,
    ): CaseStatus.RECEIPT_ALREADY_VERIFIED,
    (
        CaseStatus.RECEIPT_ALREADY_VERIFIED,
        TransitionEvent.INVOICE_APPROVAL_REQUESTED,
    ): CaseStatus.AWAITING_INVOICE_APPROVAL,
    (
        CaseStatus.INVESTIGATING,
        TransitionEvent.RECEIPT_RESTART_RECOMMENDED,
    ): CaseStatus.RECEIPT_RESTART_RECOMMENDED,
    (
        CaseStatus.RECEIPT_RESTART_RECOMMENDED,
        TransitionEvent.RECEIPT_APPROVAL_REQUESTED,
    ): CaseStatus.AWAITING_RECEIPT_APPROVAL,
    (
        CaseStatus.AWAITING_RECEIPT_APPROVAL,
        TransitionEvent.RECEIPT_APPROVAL_ACCEPTED,
    ): CaseStatus.RECEIPT_ACTION_AUTHORIZED,
    (
        CaseStatus.RECEIPT_ACTION_AUTHORIZED,
        TransitionEvent.RECEIPT_EXECUTION_STARTED,
    ): CaseStatus.RECEIPT_EXECUTING,
    (
        CaseStatus.RECEIPT_EXECUTING,
        TransitionEvent.RECEIPT_POSTCONDITIONS_VERIFIED,
    ): CaseStatus.RECEIPT_VERIFIED,
    (
        CaseStatus.RECEIPT_VERIFIED,
        TransitionEvent.INVOICE_APPROVAL_REQUESTED,
    ): CaseStatus.AWAITING_INVOICE_APPROVAL,
    (
        CaseStatus.AWAITING_INVOICE_APPROVAL,
        TransitionEvent.INVOICE_APPROVAL_ACCEPTED,
    ): CaseStatus.INVOICE_ACTION_AUTHORIZED,
    (
        CaseStatus.INVOICE_ACTION_AUTHORIZED,
        TransitionEvent.INVOICE_EXECUTION_STARTED,
    ): CaseStatus.INVOICE_EXECUTING,
    (
        CaseStatus.INVOICE_EXECUTING,
        TransitionEvent.INVOICE_POSTCONDITIONS_VERIFIED,
    ): CaseStatus.CLOSED,
}


def make_case(status: CaseStatus, *, version: int = 3, evidence_revision: int = 2) -> Case:
    return Case(
        case_id="case-001",
        case_version=version,
        scenario_id="retryable-document-lock",
        status=status,
        discrepancy=Discrepancy(
            expected_quantity=100,
            observed_quantity=80,
            missing_quantity=20,
            unit="EA",
        ),
        current_evidence_revision=evidence_revision,
        created_at=NOW,
        updated_at=NOW,
    )


def make_evidence(*, case_id: str = "case-001") -> EvidenceItem:
    return EvidenceItem(
        evidence_id="evidence-queue-001",
        case_id=case_id,
        trace_id="trace-001",
        subject="failed receipt message",
        source_type=EvidenceSourceType.FAILED_MESSAGE_QUEUE,
        source_record_id="message-020",
        observed_at=NOW,
        content_digest="sha256:evidence-queue-001",
        admitted_fields={"retry_eligible": True, "quantity": 20},
        provenance=EvidenceProvenance(
            source_system="synthetic-queue",
            collection_method="typed-read-tool",
            collected_by="retryable-message-investigator",
        ),
    )


def valid_closure(**overrides: object) -> ClosureFacts:
    values: dict[str, object] = {
        "expected_receipt_quantity": 100,
        "erp_receipt_quantity": 100,
        "duplicate_material_document_count": 0,
        "message_resolution": MessageResolution.SAFELY_CONSUMED,
        "invoice_state": InvoiceState.RELEASED,
    }
    values.update(overrides)
    return ClosureFacts(**values)  # type: ignore[arg-type]


def make_command(event: TransitionEvent, *, case_id: str = "case-001") -> TransitionCommand:
    evidence = None
    closure_facts = None
    hypothesis = None
    evaluation = None
    assessment = None
    if event is TransitionEvent.EVIDENCE_ADMITTED:
        evidence = make_evidence(case_id=case_id)
    if event is TransitionEvent.INVOICE_POSTCONDITIONS_VERIFIED:
        closure_facts = valid_closure()
    if event is TransitionEvent.RECEIPT_RESTART_RECOMMENDED:
        hypothesis = HypothesisResult(
            hypothesis_type=HypothesisType.RETRYABLE_MESSAGE,
            conclusion=HypothesisConclusion.SUPPORTED,
            confidence_band=ConfidenceBand.HIGH,
            supporting_evidence_ids=("evidence-queue-001",),
            contradicting_evidence_ids=(),
            missing_evidence=(),
        )
        evaluation = EvaluationResult(
            decision=EvaluationDecision.ACCEPT,
            validated_evidence_ids=("evidence-queue-001",),
            failed_invariants=(),
            allowed_next_action=ActionTool.RESTART_RECEIPT_MESSAGE,
            evaluator_version="deterministic-v1",
            trace_id="trace-001",
        )
        assessment = InvestigationAssessment(
            assessment_id="assessment-receipt-restart-recommended",
            case_id=case_id,
            trace_id="trace-001",
            hypothesis=hypothesis,
            evaluation=evaluation,
            admitted_evidence_ids=("evidence-queue-001",),
            missing_evidence_sources=(),
            decision=InvestigationDecision.RECOMMEND_RECEIPT_RESTART,
            reason_codes=("test-assessment",),
            assessed_at=NOW + timedelta(minutes=1),
        )
        hypothesis = None
        evaluation = None
    investigation_decisions = {
        TransitionEvent.EVIDENCE_REQUIRED: (
            HypothesisType.RETRYABLE_MESSAGE,
            HypothesisConclusion.NEEDS_EVIDENCE,
            EvaluationDecision.MORE_EVIDENCE,
            InvestigationDecision.REQUIRE_EVIDENCE,
            ("MATERIAL_DOCUMENT",),
        ),
        TransitionEvent.ACTION_PROTECTED: (
            HypothesisType.GENUINE_SHORT_SHIPMENT,
            HypothesisConclusion.SUPPORTED,
            EvaluationDecision.REJECT,
            InvestigationDecision.PROTECT,
            (),
        ),
        TransitionEvent.RECEIPT_ALREADY_POSTED: (
            HypothesisType.ALREADY_POSTED,
            HypothesisConclusion.SUPPORTED,
            EvaluationDecision.ACCEPT,
            InvestigationDecision.RECEIPT_ALREADY_POSTED,
            (),
        ),
        TransitionEvent.INVESTIGATION_ASSESSED: (
            HypothesisType.RETRYABLE_MESSAGE,
            HypothesisConclusion.SUPPORTED,
            EvaluationDecision.REJECT,
            InvestigationDecision.EVALUATOR_REJECTED,
            (),
        ),
    }
    if event in investigation_decisions:
        hypothesis_type, conclusion, decision, assessment_decision, missing = (
            investigation_decisions[event]
        )
        outcome_hypothesis = HypothesisResult(
            hypothesis_type=hypothesis_type,
            conclusion=conclusion,
            confidence_band=ConfidenceBand.HIGH,
            supporting_evidence_ids=("evidence-queue-001",),
            contradicting_evidence_ids=(),
            missing_evidence=missing,
        )
        outcome_evaluation = EvaluationResult(
            decision=decision,
            validated_evidence_ids=("evidence-queue-001",),
            failed_invariants=(() if decision is EvaluationDecision.ACCEPT else ("blocked",)),
            allowed_next_action=None,
            evaluator_version="deterministic-v1",
            trace_id="trace-001",
        )
        assessment = InvestigationAssessment(
            assessment_id=f"assessment-{event.value.lower()}",
            case_id=case_id,
            trace_id="trace-001",
            hypothesis=outcome_hypothesis,
            evaluation=outcome_evaluation,
            admitted_evidence_ids=("evidence-queue-001",),
            missing_evidence_sources=missing,
            decision=assessment_decision,
            reason_codes=("test-assessment",),
            assessed_at=NOW + timedelta(minutes=1),
        )
    return TransitionCommand(
        case_id=case_id,
        expected_version=3,
        event=event,
        idempotency_key=f"idempotency-{event.value.lower()}",
        trace_id="trace-001",
        occurred_at=NOW + timedelta(minutes=1),
        evidence=evidence,
        closure_facts=closure_facts,
        hypothesis=hypothesis,
        evaluation=evaluation,
        assessment=assessment,
    )


def test_production_transition_table_matches_the_frozen_spec() -> None:
    assert TRANSITIONS == EXPECTED_TRANSITIONS


@pytest.mark.parametrize(("source_event", "target"), list(EXPECTED_TRANSITIONS.items()))
def test_every_approved_transition(
    source_event: tuple[CaseStatus, TransitionEvent], target: CaseStatus
) -> None:
    source, event_type = source_event
    case = make_case(source)
    command = make_command(event_type)

    updated, event = advance_case(case, command)

    assert updated.status is target
    assert updated.case_version == case.case_version + 1
    assert event.prior_status is source
    assert event.new_status is target
    assert event.prior_version == case.case_version
    assert event.new_version == updated.case_version
    assert len(event.payload_digest) == 64


INVALID_TRANSITIONS = [
    (status, event)
    for status, event in product(CaseStatus, TransitionEvent)
    if (status, event) not in EXPECTED_TRANSITIONS
]


@pytest.mark.parametrize(("status", "event"), INVALID_TRANSITIONS)
def test_every_unapproved_transition_is_rejected(
    status: CaseStatus, event: TransitionEvent
) -> None:
    with pytest.raises(InvalidTransition):
        advance_case(make_case(status), make_command(event))


def test_stale_case_version_is_rejected() -> None:
    command = make_command(TransitionEvent.INVESTIGATION_STARTED).model_copy(
        update={"expected_version": 2}
    )

    with pytest.raises(VersionConflict, match="expected case version"):
        advance_case(make_case(CaseStatus.OPEN), command)


def test_typed_evidence_returns_to_investigation_and_increments_revision_once() -> None:
    case = make_case(CaseStatus.NEEDS_EVIDENCE)

    updated, event = advance_case(case, make_command(TransitionEvent.EVIDENCE_ADMITTED))

    assert updated.status is CaseStatus.INVESTIGATING
    assert updated.current_evidence_revision == case.current_evidence_revision + 1
    assert event.payload_digest != ""


def test_evidence_for_another_case_cannot_satisfy_the_request() -> None:
    command = make_command(TransitionEvent.EVIDENCE_ADMITTED, case_id="case-other").model_copy(
        update={"case_id": "case-001"}
    )

    with pytest.raises(InvalidEventPayload, match="evidence"):
        advance_case(make_case(CaseStatus.NEEDS_EVIDENCE), command)


@pytest.mark.parametrize(
    "unsafe_facts",
    [
        valid_closure(erp_receipt_quantity=80),
        valid_closure(duplicate_material_document_count=1),
        valid_closure(message_resolution=MessageResolution.UNRESOLVED),
        valid_closure(invoice_state=InvoiceState.HELD),
    ],
)
def test_closed_requires_every_verified_postcondition(unsafe_facts: ClosureFacts) -> None:
    command = make_command(TransitionEvent.INVOICE_POSTCONDITIONS_VERIFIED).model_copy(
        update={"closure_facts": unsafe_facts}
    )

    with pytest.raises(InvalidEventPayload, match="closure"):
        advance_case(make_case(CaseStatus.INVOICE_EXECUTING), command)


def test_closure_quantity_is_bound_to_the_case_discrepancy() -> None:
    command = make_command(TransitionEvent.INVOICE_POSTCONDITIONS_VERIFIED).model_copy(
        update={
            "closure_facts": valid_closure(
                expected_receipt_quantity=80,
                erp_receipt_quantity=80,
            )
        }
    )

    with pytest.raises(InvalidEventPayload, match="case discrepancy"):
        advance_case(make_case(CaseStatus.INVOICE_EXECUTING), command)


def test_callers_cannot_supply_a_target_status() -> None:
    with pytest.raises(ValidationError, match="target_status"):
        TransitionCommand(
            case_id="case-001",
            expected_version=3,
            event=TransitionEvent.INVESTIGATION_STARTED,
            idempotency_key="idempotency-001",
            trace_id="trace-001",
            occurred_at=NOW + timedelta(minutes=1),
            target_status=CaseStatus.CLOSED,  # type: ignore[call-arg]
        )


@pytest.mark.parametrize(
    ("event", "payload"),
    [
        (TransitionEvent.EVIDENCE_ADMITTED, {}),
        (TransitionEvent.EVIDENCE_ADMITTED, {"closure_facts": valid_closure()}),
        (TransitionEvent.INVOICE_POSTCONDITIONS_VERIFIED, {}),
        (
            TransitionEvent.INVOICE_POSTCONDITIONS_VERIFIED,
            {"evidence": make_evidence()},
        ),
        (TransitionEvent.INVESTIGATION_STARTED, {"evidence": make_evidence()}),
        (TransitionEvent.INVESTIGATION_STARTED, {"closure_facts": valid_closure()}),
    ],
)
def test_event_payload_channels_are_exact(
    event: TransitionEvent, payload: dict[str, object]
) -> None:
    command_data: dict[str, object] = {
        "case_id": "case-001",
        "expected_version": 3,
        "event": event,
        "idempotency_key": "idempotency-001",
        "trace_id": "trace-001",
        "occurred_at": NOW + timedelta(minutes=1),
    }
    command_data.update(payload)

    with pytest.raises(ValidationError):
        TransitionCommand.model_validate(command_data)


def test_event_identity_is_deterministic_for_a_retry() -> None:
    case = make_case(CaseStatus.OPEN)
    command = make_command(TransitionEvent.INVESTIGATION_STARTED)

    _, first = advance_case(case, command)
    _, retry = advance_case(case, command)

    assert first.event_id == retry.event_id
    assert first.payload_digest == retry.payload_digest
