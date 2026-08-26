"""Deterministic diagnosis seam later replaced by the bounded agent harness."""

from __future__ import annotations

from typing import Any

from the_missing_20.domain.execution import uses_external_id_namespace
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


def _record(value: object) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


def _integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _proves_already_posted(
    *,
    queue: EvidenceItem,
    warehouse_quantity: object,
    erp_quantity: object,
    invoice: EvidenceItem,
    invoice_quantity: object,
    material: EvidenceItem,
) -> bool:
    documents = material.admitted_fields.get("material_documents")
    effects = material.admitted_fields.get("business_effects")
    if (
        queue.admitted_fields.get("status") != "CONSUMED"
        or invoice.admitted_fields.get("state") != "HELD"
        or not _integer(queue.admitted_fields.get("quantity"))
        or not _integer(warehouse_quantity)
        or warehouse_quantity != erp_quantity
        or warehouse_quantity != invoice_quantity
        or not isinstance(documents, list)
        or len(documents) != 1
        or not isinstance(effects, list)
        or len(effects) != 1
    ):
        return False
    document = _record(documents[0])
    effect = _record(effects[0])
    if document is None or effect is None:
        return False
    message_id = queue.admitted_fields.get("message_id")
    message_quantity = queue.admitted_fields.get("quantity")
    document_id = document.get("material_document_id")
    execution_id = document.get("execution_id")
    idempotency_key = document.get("idempotency_key")
    return (
        isinstance(message_id, str)
        and isinstance(document_id, str)
        and isinstance(execution_id, str)
        and isinstance(idempotency_key, str)
        and document.get("source_message_id") == message_id
        and document.get("purchase_order_id") == queue.admitted_fields.get("purchase_order_id")
        and document.get("line_id") == queue.admitted_fields.get("line_id")
        and document.get("quantity") == message_quantity
        and document.get("case_id", queue.case_id) == queue.case_id
        and document.get("trace_id", queue.trace_id) == queue.trace_id
        and queue.admitted_fields.get("consumed_by_execution_id") == execution_id
        and uses_external_id_namespace(execution_id)
        and uses_external_id_namespace(idempotency_key)
        and effect.get("effect_type") == "EXTERNAL_RECEIPT"
        and effect.get("execution_id") == execution_id
        and effect.get("idempotency_key") == idempotency_key
        and effect.get("source_record_id") == message_id
        and effect.get("result_record_ids") == [document_id]
        and effect.get("case_id") == queue.case_id
        and effect.get("trace_id") == queue.trace_id
    )


def diagnose_retryable_message(
    evidence: tuple[EvidenceItem, ...], *, trace_id: str
) -> tuple[HypothesisResult, EvaluationResult]:
    context_case_id = evidence[0].case_id if evidence else None
    if any(item.trace_id != trace_id or item.case_id != context_case_id for item in evidence):
        return (
            HypothesisResult(
                hypothesis_type=HypothesisType.RETRYABLE_MESSAGE,
                conclusion=HypothesisConclusion.REJECTED,
                confidence_band=ConfidenceBand.HIGH,
                supporting_evidence_ids=(),
                contradicting_evidence_ids=tuple(item.evidence_id for item in evidence),
                missing_evidence=(),
            ),
            EvaluationResult(
                decision=EvaluationDecision.REJECT,
                validated_evidence_ids=tuple(item.evidence_id for item in evidence),
                failed_invariants=("evidence_context_mismatch",),
                allowed_next_action=None,
                evaluator_version="deterministic-v1",
                trace_id=trace_id,
            ),
        )
    by_source = {item.source_type.value: item for item in evidence}
    required = {
        "FAILED_MESSAGE_QUEUE",
        "ERP_RECEIPT",
        "MATERIAL_DOCUMENT",
        "WAREHOUSE",
        "INVOICE",
    }
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
    invoice = by_source["INVOICE"]
    validated = tuple(sorted(item.evidence_id for item in evidence))
    warehouse_quantity = warehouse.admitted_fields.get("quantity")
    erp_quantity = erp.admitted_fields.get("quantity")
    invoice_quantity = invoice.admitted_fields.get("quantity")
    if _proves_already_posted(
        queue=queue,
        warehouse_quantity=warehouse_quantity,
        erp_quantity=erp_quantity,
        invoice=invoice,
        invoice_quantity=invoice_quantity,
        material=material,
    ):
        return (
            HypothesisResult(
                hypothesis_type=HypothesisType.ALREADY_POSTED,
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
                allowed_next_action=None,
                evaluator_version="deterministic-v1",
                trace_id=trace_id,
            ),
        )
    if (
        isinstance(warehouse_quantity, int)
        and not isinstance(warehouse_quantity, bool)
        and warehouse_quantity == erp_quantity
        and isinstance(invoice_quantity, int)
        and not isinstance(invoice_quantity, bool)
        and warehouse_quantity < invoice_quantity
    ):
        return (
            HypothesisResult(
                hypothesis_type=HypothesisType.GENUINE_SHORT_SHIPMENT,
                conclusion=HypothesisConclusion.SUPPORTED,
                confidence_band=ConfidenceBand.HIGH,
                supporting_evidence_ids=validated,
                contradicting_evidence_ids=(),
                missing_evidence=(),
            ),
            EvaluationResult(
                decision=EvaluationDecision.REJECT,
                validated_evidence_ids=validated,
                failed_invariants=("physical_quantity_below_ordered_quantity",),
                allowed_next_action=None,
                evaluator_version="deterministic-v1",
                trace_id=trace_id,
            ),
        )
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
