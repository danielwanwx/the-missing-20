"""Case orchestration that exposes named, versioned lifecycle commands."""

from __future__ import annotations

from the_missing_20.domain.assessment import validate_investigation_assessment
from the_missing_20.domain.errors import InvalidEventPayload
from the_missing_20.domain.events import CaseEvent, TransitionCommand
from the_missing_20.domain.models import (
    ActionTool,
    Case,
    EvaluationDecision,
    EvaluationResult,
    EvidenceItem,
    EvidenceSourceType,
    HypothesisConclusion,
    HypothesisResult,
    HypothesisType,
    InvestigationAssessment,
    InvestigationDecision,
)
from the_missing_20.domain.states import TransitionEvent
from the_missing_20.ports.case_store import CaseStore
from the_missing_20.ports.clock import Clock


class CaseService:
    def __init__(self, store: CaseStore, clock: Clock) -> None:
        self.store = store
        self.clock = clock

    def request_receipt_approval(
        self,
        *,
        case_id: str,
        expected_version: int,
        idempotency_key: str,
    ) -> tuple[Case, CaseEvent]:
        trace_id = self.store.get_genesis(case_id).trace_id
        return self.store.apply_transition(
            TransitionCommand(
                case_id=case_id,
                expected_version=expected_version,
                event=TransitionEvent.RECEIPT_APPROVAL_REQUESTED,
                idempotency_key=idempotency_key,
                trace_id=trace_id,
                occurred_at=self.clock.now(),
            )
        )

    def request_invoice_approval(
        self,
        *,
        case_id: str,
        expected_version: int,
        idempotency_key: str,
    ) -> tuple[Case, CaseEvent]:
        trace_id = self.store.get_genesis(case_id).trace_id
        return self.store.apply_transition(
            TransitionCommand(
                case_id=case_id,
                expected_version=expected_version,
                event=TransitionEvent.INVOICE_APPROVAL_REQUESTED,
                idempotency_key=idempotency_key,
                trace_id=trace_id,
                occurred_at=self.clock.now(),
            )
        )

    def recommend_receipt_restart(
        self,
        *,
        case_id: str,
        expected_version: int,
        idempotency_key: str,
        hypothesis: HypothesisResult,
        evaluation: EvaluationResult,
    ) -> tuple[Case, CaseEvent]:
        trace_id = self.store.get_genesis(case_id).trace_id
        admitted = self.store.list_evidence(case_id)
        admitted_ids = {item.evidence_id for item in admitted}
        validated_ids = set(evaluation.validated_evidence_ids)
        supporting_ids = set(hypothesis.supporting_evidence_ids)
        supporting_source_types = {
            item.source_type for item in admitted if item.evidence_id in supporting_ids
        }
        required_source_types = {
            EvidenceSourceType.FAILED_MESSAGE_QUEUE,
            EvidenceSourceType.ERP_RECEIPT,
            EvidenceSourceType.MATERIAL_DOCUMENT,
            EvidenceSourceType.WAREHOUSE,
            EvidenceSourceType.INVOICE,
        }
        if not (
            hypothesis.hypothesis_type is HypothesisType.RETRYABLE_MESSAGE
            and hypothesis.conclusion is HypothesisConclusion.SUPPORTED
            and evaluation.decision is EvaluationDecision.ACCEPT
            and evaluation.allowed_next_action is ActionTool.RESTART_RECEIPT_MESSAGE
            and not evaluation.failed_invariants
            and evaluation.trace_id == trace_id
            and validated_ids == admitted_ids
            and supporting_ids
            and supporting_ids.issubset(admitted_ids)
            and required_source_types.issubset(supporting_source_types)
            and not hypothesis.missing_evidence
            and not hypothesis.contradicting_evidence_ids
        ):
            raise InvalidEventPayload(
                "only an evidence-complete accepted diagnosis can recommend receipt restart"
            )
        return self.record_investigation_outcome(
            assessment=InvestigationAssessment(
                assessment_id=f"assessment:{idempotency_key}",
                case_id=case_id,
                trace_id=trace_id,
                hypothesis=hypothesis,
                evaluation=evaluation,
                admitted_evidence_ids=tuple(sorted(admitted_ids)),
                missing_evidence_sources=(),
                decision=InvestigationDecision.RECOMMEND_RECEIPT_RESTART,
                reason_codes=("RETRYABLE_MESSAGE",),
                assessed_at=self.clock.now(),
            ),
            expected_version=expected_version,
            idempotency_key=idempotency_key,
        )

    def record_investigation_outcome(
        self,
        *,
        assessment: InvestigationAssessment,
        expected_version: int,
        idempotency_key: str,
    ) -> tuple[Case, CaseEvent]:
        trace_id = self.store.get_genesis(assessment.case_id).trace_id
        admitted = self.store.list_evidence(assessment.case_id)
        validate_investigation_assessment(assessment, admitted_evidence=admitted, trace_id=trace_id)
        admitted_ids = {item.evidence_id for item in admitted}
        supporting_ids = set(assessment.hypothesis.supporting_evidence_ids)
        contradicting_ids = set(assessment.hypothesis.contradicting_evidence_ids)
        validated_ids = set(assessment.evaluation.validated_evidence_ids)
        if (
            assessment.trace_id != trace_id
            or assessment.evaluation.trace_id != trace_id
            or not assessment.reason_codes
            or set(assessment.admitted_evidence_ids) != admitted_ids
            or not supporting_ids.issubset(admitted_ids)
            or not contradicting_ids.issubset(admitted_ids)
            or not validated_ids.issubset(admitted_ids)
            or set(assessment.missing_evidence_sources)
            != set(assessment.hypothesis.missing_evidence)
        ):
            raise InvalidEventPayload("assessment does not match current admitted evidence")
        decision_event = {
            InvestigationDecision.RECOMMEND_RECEIPT_RESTART: (
                TransitionEvent.RECEIPT_RESTART_RECOMMENDED
            ),
            InvestigationDecision.RECEIPT_ALREADY_POSTED: TransitionEvent.RECEIPT_ALREADY_POSTED,
            InvestigationDecision.REQUIRE_EVIDENCE: TransitionEvent.EVIDENCE_REQUIRED,
            InvestigationDecision.PROTECT: TransitionEvent.ACTION_PROTECTED,
            InvestigationDecision.EVALUATOR_REJECTED: TransitionEvent.INVESTIGATION_ASSESSED,
        }
        compatible = {
            InvestigationDecision.RECOMMEND_RECEIPT_RESTART: (
                assessment.hypothesis.hypothesis_type is HypothesisType.RETRYABLE_MESSAGE
                and assessment.hypothesis.conclusion is HypothesisConclusion.SUPPORTED
                and assessment.evaluation.decision is EvaluationDecision.ACCEPT
                and assessment.evaluation.allowed_next_action is ActionTool.RESTART_RECEIPT_MESSAGE
                and validated_ids == admitted_ids
                and not assessment.evaluation.failed_invariants
                and not assessment.hypothesis.missing_evidence
                and not contradicting_ids
                and {
                    item.source_type
                    for item in self.store.list_evidence(assessment.case_id)
                    if item.evidence_id in supporting_ids
                }
                >= {
                    EvidenceSourceType.FAILED_MESSAGE_QUEUE,
                    EvidenceSourceType.ERP_RECEIPT,
                    EvidenceSourceType.MATERIAL_DOCUMENT,
                    EvidenceSourceType.WAREHOUSE,
                    EvidenceSourceType.INVOICE,
                }
            ),
            InvestigationDecision.RECEIPT_ALREADY_POSTED: (
                assessment.hypothesis.hypothesis_type is HypothesisType.ALREADY_POSTED
                and assessment.hypothesis.conclusion is HypothesisConclusion.SUPPORTED
                and assessment.evaluation.decision is EvaluationDecision.ACCEPT
                and assessment.evaluation.allowed_next_action is None
                and validated_ids == admitted_ids
                and not assessment.evaluation.failed_invariants
            ),
            InvestigationDecision.REQUIRE_EVIDENCE: (
                assessment.hypothesis.conclusion is HypothesisConclusion.NEEDS_EVIDENCE
                and assessment.evaluation.decision is EvaluationDecision.MORE_EVIDENCE
                and bool(assessment.missing_evidence_sources)
                and assessment.evaluation.allowed_next_action is None
            ),
            InvestigationDecision.PROTECT: (
                assessment.hypothesis.hypothesis_type is HypothesisType.GENUINE_SHORT_SHIPMENT
                and assessment.hypothesis.conclusion is HypothesisConclusion.SUPPORTED
                and assessment.evaluation.decision is EvaluationDecision.REJECT
                and assessment.evaluation.allowed_next_action is None
                and validated_ids == admitted_ids
                and not assessment.hypothesis.missing_evidence
            ),
            InvestigationDecision.EVALUATOR_REJECTED: (
                assessment.evaluation.decision is EvaluationDecision.REJECT
                and assessment.evaluation.allowed_next_action is None
            ),
        }[assessment.decision]
        if not compatible:
            raise InvalidEventPayload("assessment decision is incompatible with diagnosis")
        return self.store.apply_transition(
            TransitionCommand(
                case_id=assessment.case_id,
                expected_version=expected_version,
                event=decision_event[assessment.decision],
                idempotency_key=idempotency_key,
                trace_id=trace_id,
                occurred_at=self.clock.now(),
                assessment=assessment,
            )
        )

    def admit_current_evidence(
        self,
        *,
        evidence: EvidenceItem,
        expected_version: int,
        idempotency_key: str,
    ) -> tuple[Case, CaseEvent]:
        trace_id = self.store.get_genesis(evidence.case_id).trace_id
        if evidence.trace_id != trace_id:
            raise InvalidEventPayload("evidence trace does not match case")
        return self.store.admit_evidence_with_transition(
            evidence,
            TransitionCommand(
                case_id=evidence.case_id,
                expected_version=expected_version,
                event=TransitionEvent.EVIDENCE_ADMITTED,
                idempotency_key=idempotency_key,
                trace_id=trace_id,
                occurred_at=self.clock.now(),
                evidence=evidence,
            ),
        )
