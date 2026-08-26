"""Deterministic diagnosis seam later replaced by the bounded agent harness."""

from __future__ import annotations

from the_missing_20.domain.models import (
    ActionTool,
    ConfidenceBand,
    EvaluationDecision,
    EvaluationResult,
    EvidenceItem,
    HypothesisConclusion,
    HypothesisResult,
    HypothesisType,
)


def diagnose_retryable_message(
    evidence: tuple[EvidenceItem, ...], *, trace_id: str
) -> tuple[HypothesisResult, EvaluationResult]:
    by_source = {item.source_type.value: item for item in evidence}
    required = {"FAILED_MESSAGE_QUEUE", "ERP_RECEIPT", "MATERIAL_DOCUMENT", "WAREHOUSE"}
    missing = sorted(required.difference(by_source))
    if missing:
        return (
            HypothesisResult(
                hypothesis_type=HypothesisType.RETRYABLE_MESSAGE,
                conclusion=HypothesisConclusion.NEEDS_EVIDENCE,
                confidence_band=ConfidenceBand.LOW,
                supporting_evidence_ids=(),
                contradicting_evidence_ids=(),
                missing_evidence=tuple(missing),
            ),
            EvaluationResult(
                decision=EvaluationDecision.MORE_EVIDENCE,
                validated_evidence_ids=(),
                failed_invariants=("required_evidence_missing",),
                allowed_next_action=None,
                evaluator_version="deterministic-v1",
                trace_id=trace_id,
            ),
        )
    queue = by_source["FAILED_MESSAGE_QUEUE"]
    erp = by_source["ERP_RECEIPT"]
    material = by_source["MATERIAL_DOCUMENT"]
    warehouse = by_source["WAREHOUSE"]
    failures: list[str] = []
    if queue.admitted_fields.get("status") != "FAILED":
        failures.append("message_not_failed")
    if queue.admitted_fields.get("error_code") != "DOCUMENT_LOCKED_RETRYABLE":
        failures.append("failure_not_retryable_document_lock")
    if queue.admitted_fields.get("retry_eligible") is not True:
        failures.append("message_not_retry_eligible")
    if queue.admitted_fields.get("lock_cleared") is not True:
        failures.append("document_lock_not_cleared")
    if material.admitted_fields.get("material_documents") != []:
        failures.append("source_material_document_already_exists")
    warehouse_quantity = warehouse.admitted_fields.get("quantity")
    erp_quantity = erp.admitted_fields.get("quantity")
    message_quantity = queue.admitted_fields.get("quantity")
    if (
        not isinstance(warehouse_quantity, int)
        or isinstance(warehouse_quantity, bool)
        or not isinstance(erp_quantity, int)
        or isinstance(erp_quantity, bool)
        or not isinstance(message_quantity, int)
        or isinstance(message_quantity, bool)
        or warehouse_quantity - erp_quantity != message_quantity
        or message_quantity <= 0
    ):
        failures.append("message_quantity_does_not_close_discrepancy")
    validated = tuple(sorted(item.evidence_id for item in evidence))
    if failures:
        return (
            HypothesisResult(
                hypothesis_type=HypothesisType.RETRYABLE_MESSAGE,
                conclusion=HypothesisConclusion.REJECTED,
                confidence_band=ConfidenceBand.HIGH,
                supporting_evidence_ids=(),
                contradicting_evidence_ids=validated,
                missing_evidence=(),
            ),
            EvaluationResult(
                decision=EvaluationDecision.REJECT,
                validated_evidence_ids=validated,
                failed_invariants=tuple(failures),
                allowed_next_action=None,
                evaluator_version="deterministic-v1",
                trace_id=trace_id,
            ),
        )
    return (
        HypothesisResult(
            hypothesis_type=HypothesisType.RETRYABLE_MESSAGE,
            conclusion=HypothesisConclusion.SUPPORTED,
            confidence_band=ConfidenceBand.HIGH,
            supporting_evidence_ids=validated,
            contradicting_evidence_ids=(),
            missing_evidence=(),
        ),
        EvaluationResult(
            decision=EvaluationDecision.ACCEPT,
            validated_evidence_ids=validated,
            failed_invariants=(),
            allowed_next_action=ActionTool.RESTART_RECEIPT_MESSAGE,
            evaluator_version="deterministic-v1",
            trace_id=trace_id,
        ),
    )
