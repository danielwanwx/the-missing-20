"""Pure validation shared by assessment writes and audit-log replay."""

from __future__ import annotations

from typing import cast

from the_missing_20.domain.errors import InvalidEventPayload
from the_missing_20.domain.models import (
    ActionTool,
    EvaluationDecision,
    EvidenceItem,
    EvidenceSourceType,
    HypothesisConclusion,
    HypothesisType,
    InvestigationAssessment,
    InvestigationDecision,
)


def validate_investigation_assessment(
    assessment: InvestigationAssessment,
    *,
    admitted_evidence: tuple[EvidenceItem, ...],
    trace_id: str,
) -> None:
    """Reject tampered assessments against the exact admitted evidence set."""
    admitted_ids = {item.evidence_id for item in admitted_evidence}
    validated_ids = set(assessment.evaluation.validated_evidence_ids)
    supporting_ids = set(assessment.hypothesis.supporting_evidence_ids)
    contradicting_ids = set(assessment.hypothesis.contradicting_evidence_ids)
    closure = assessment.evaluation.citation_closure
    raw_closure_ids = closure.get("validated_evidence_ids") if isinstance(closure, dict) else None
    closure_ids = (
        set(cast(list[str] | tuple[str, ...], raw_closure_ids))
        if isinstance(raw_closure_ids, (list, tuple))
        and all(isinstance(item, str) for item in raw_closure_ids)
        else None
    )
    closure_identity_valid = closure is None or (
        closure.get("case_id") == assessment.case_id
        and closure.get("trace_id") == trace_id
        and closure_ids == validated_ids
        and closure.get("all_admitted_evidence_covered") is True
        if assessment.evaluation.decision is EvaluationDecision.ACCEPT
        else closure.get("case_id") == assessment.case_id
        and closure.get("trace_id") == trace_id
        and closure_ids == validated_ids
    )
    supporting_sources = {
        item.source_type for item in admitted_evidence if item.evidence_id in supporting_ids
    }
    if (
        assessment.trace_id != trace_id
        or assessment.evaluation.trace_id != trace_id
        or not assessment.reason_codes
        or set(assessment.admitted_evidence_ids) != admitted_ids
        or (
            assessment.evaluation.decision is not EvaluationDecision.MORE_EVIDENCE
            and validated_ids != admitted_ids
        )
        or not supporting_ids.issubset(admitted_ids)
        or not contradicting_ids.issubset(admitted_ids)
        or set(assessment.missing_evidence_sources) != set(assessment.hypothesis.missing_evidence)
        or not closure_identity_valid
    ):
        raise InvalidEventPayload("assessment does not match current admitted evidence")
    compatible = {
        InvestigationDecision.RECOMMEND_RECEIPT_RESTART: (
            assessment.hypothesis.hypothesis_type is HypothesisType.RETRYABLE_MESSAGE
            and assessment.hypothesis.conclusion is HypothesisConclusion.SUPPORTED
            and assessment.evaluation.decision is EvaluationDecision.ACCEPT
            and assessment.evaluation.allowed_next_action is ActionTool.RESTART_RECEIPT_MESSAGE
            and not assessment.evaluation.failed_invariants
            and not assessment.hypothesis.missing_evidence
            and not contradicting_ids
            and {
                EvidenceSourceType.FAILED_MESSAGE_QUEUE,
                EvidenceSourceType.ERP_RECEIPT,
                EvidenceSourceType.MATERIAL_DOCUMENT,
                EvidenceSourceType.WAREHOUSE,
                EvidenceSourceType.INVOICE,
            }.issubset(supporting_sources)
        ),
        InvestigationDecision.RECEIPT_ALREADY_POSTED: (
            assessment.hypothesis.hypothesis_type is HypothesisType.ALREADY_POSTED
            and assessment.hypothesis.conclusion is HypothesisConclusion.SUPPORTED
            and assessment.evaluation.decision is EvaluationDecision.ACCEPT
            and assessment.evaluation.allowed_next_action is None
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
            and not assessment.hypothesis.missing_evidence
        ),
        InvestigationDecision.EVALUATOR_REJECTED: (
            assessment.evaluation.decision is EvaluationDecision.REJECT
            and assessment.evaluation.allowed_next_action is None
        ),
    }[assessment.decision]
    if not compatible:
        raise InvalidEventPayload("assessment decision is incompatible with diagnosis")
