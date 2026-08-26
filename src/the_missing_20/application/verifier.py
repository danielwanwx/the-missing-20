"""Deterministic postcondition checks over authoritative enterprise snapshots."""

from __future__ import annotations

from the_missing_20.domain.enterprise import (
    BusinessEffect,
    EnterpriseActionOutcome,
    EnterpriseInvoiceState,
    EnterpriseSnapshot,
    MessageStatus,
)
from the_missing_20.domain.execution import (
    EffectType,
    ReleaseInvoiceParameters,
    RestartReceiptMessageParameters,
)
from the_missing_20.domain.models import ClosureFacts, InvoiceState, MessageResolution


def verify_receipt_restart(
    snapshot: EnterpriseSnapshot,
    *,
    case_id: str,
    trace_id: str,
    execution_id: str,
    idempotency_key: str,
    parameters: RestartReceiptMessageParameters,
    effect: BusinessEffect | None,
    outcome: EnterpriseActionOutcome | None,
) -> dict[str, bool]:
    source_documents = [
        document
        for document in snapshot.material_documents
        if document.source_message_id == parameters.message_id
    ]
    source_effects = [
        item for item in snapshot.business_effects if item.source_record_id == parameters.message_id
    ]
    authoritative_effect = (
        source_effects[0]
        if effect is not None
        and len(source_effects) == 1
        and source_effects[0].effect_id == effect.effect_id
        else None
    )
    source_document = source_documents[0] if len(source_documents) == 1 else None
    expected_effect_type = (
        EffectType.EXTERNAL_RECEIPT
        if outcome is EnterpriseActionOutcome.SAFE_NOOP
        and effect is not None
        and effect.effect_type is EffectType.EXTERNAL_RECEIPT
        else EffectType.RECEIPT_RESTART
    )
    local_authority_matches = expected_effect_type is EffectType.EXTERNAL_RECEIPT or (
        authoritative_effect is not None
        and authoritative_effect.execution_id == execution_id
        and authoritative_effect.idempotency_key == idempotency_key
    )
    return {
        "erp_receipt_matches_expected": (
            snapshot.erp_receipt.quantity
            == snapshot.warehouse_receipt.quantity
            == snapshot.purchase_order.ordered_quantity
        ),
        "purchase_order_line_identity_matches": (
            snapshot.purchase_order.purchase_order_id == parameters.purchase_order_id
            and snapshot.purchase_order.line_id == parameters.line_id
            and snapshot.warehouse_receipt.purchase_order_id == parameters.purchase_order_id
            and snapshot.warehouse_receipt.line_id == parameters.line_id
            and snapshot.erp_receipt.purchase_order_id == parameters.purchase_order_id
            and snapshot.erp_receipt.line_id == parameters.line_id
        ),
        "message_identity_matches_parameters": (
            snapshot.failed_message.message_id == parameters.message_id
            and snapshot.failed_message.purchase_order_id == parameters.purchase_order_id
            and snapshot.failed_message.line_id == parameters.line_id
            and snapshot.failed_message.quantity == parameters.quantity
            and snapshot.failed_message.error_code == parameters.expected_error_code
            and snapshot.failed_message.revision == parameters.message_revision + 1
        ),
        "message_consumed": snapshot.failed_message.status is MessageStatus.CONSUMED,
        "exactly_one_source_material_document": len(source_documents) == 1,
        "material_document_quantity_matches": (
            len(source_documents) == 1 and source_documents[0].quantity == parameters.quantity
        ),
        "one_authoritative_effect": authoritative_effect is not None,
        "effect_context_matches": (
            authoritative_effect is not None
            and authoritative_effect.case_id == case_id
            and authoritative_effect.trace_id == trace_id
            and authoritative_effect.effect_type is expected_effect_type
            and authoritative_effect.source_record_id == parameters.message_id
        ),
        "effect_authority_matches_execution": local_authority_matches,
        "message_document_effect_linked": (
            authoritative_effect is not None
            and source_document is not None
            and snapshot.failed_message.consumed_by_execution_id
            == source_document.execution_id
            == authoritative_effect.execution_id
            and source_document.idempotency_key == authoritative_effect.idempotency_key
            and authoritative_effect.result_record_ids == (source_document.material_document_id,)
            and source_document.purchase_order_id == parameters.purchase_order_id
            and source_document.line_id == parameters.line_id
            and source_document.source_message_id == parameters.message_id
            and source_document.quantity == parameters.quantity
        ),
    }


def verify_invoice_release(
    snapshot: EnterpriseSnapshot,
    *,
    case_id: str,
    trace_id: str,
    execution_id: str,
    idempotency_key: str,
    parameters: ReleaseInvoiceParameters,
    effect: BusinessEffect | None,
    outcome: EnterpriseActionOutcome | None,
) -> dict[str, bool]:
    source_effects = [
        item for item in snapshot.business_effects if item.source_record_id == parameters.invoice_id
    ]
    authoritative_effect = (
        source_effects[0]
        if effect is not None
        and len(source_effects) == 1
        and source_effects[0].effect_id == effect.effect_id
        else None
    )
    expected_effect_type = (
        EffectType.EXTERNAL_INVOICE_RELEASE
        if outcome is EnterpriseActionOutcome.SAFE_NOOP
        and effect is not None
        and effect.effect_type is EffectType.EXTERNAL_INVOICE_RELEASE
        else EffectType.INVOICE_RELEASE
    )
    local_authority_matches = expected_effect_type is EffectType.EXTERNAL_INVOICE_RELEASE or (
        authoritative_effect is not None
        and authoritative_effect.execution_id == execution_id
        and authoritative_effect.idempotency_key == idempotency_key
    )
    return {
        "invoice_released": snapshot.invoice.state is EnterpriseInvoiceState.RELEASED,
        "receipt_complete": snapshot.erp_receipt.quantity == snapshot.warehouse_receipt.quantity,
        "purchase_order_line_identity_matches": (
            snapshot.purchase_order.purchase_order_id == parameters.purchase_order_id
            and snapshot.purchase_order.line_id == parameters.line_id
            and snapshot.purchase_order.ordered_quantity == parameters.quantity
            and snapshot.warehouse_receipt.purchase_order_id == parameters.purchase_order_id
            and snapshot.warehouse_receipt.line_id == parameters.line_id
            and snapshot.warehouse_receipt.quantity == parameters.quantity
            and snapshot.erp_receipt.purchase_order_id == parameters.purchase_order_id
            and snapshot.erp_receipt.line_id == parameters.line_id
            and snapshot.erp_receipt.quantity == parameters.quantity
        ),
        "receipt_mismatch_hold_cleared": snapshot.invoice.hold_reason is None,
        "no_other_blocking_hold": not snapshot.invoice.other_blocking_holds,
        "one_authoritative_effect": authoritative_effect is not None,
        "effect_context_matches": (
            authoritative_effect is not None
            and authoritative_effect.case_id == case_id
            and authoritative_effect.trace_id == trace_id
            and authoritative_effect.effect_type is expected_effect_type
            and authoritative_effect.source_record_id == parameters.invoice_id
            and authoritative_effect.result_record_ids == (parameters.invoice_id,)
        ),
        "effect_authority_matches_execution": local_authority_matches,
        "invoice_effect_linked": (
            authoritative_effect is not None
            and snapshot.invoice.released_by_execution_id == authoritative_effect.execution_id
            and snapshot.invoice.invoice_id == parameters.invoice_id
            and snapshot.invoice.purchase_order_id == parameters.purchase_order_id
            and snapshot.invoice.line_id == parameters.line_id
            and snapshot.invoice.quantity == parameters.quantity
        ),
    }


def closure_facts(snapshot: EnterpriseSnapshot) -> ClosureFacts:
    source_documents = [
        document
        for document in snapshot.material_documents
        if document.source_message_id == snapshot.failed_message.message_id
    ]
    message_resolution = (
        MessageResolution.SAFELY_CONSUMED
        if snapshot.failed_message.status is MessageStatus.CONSUMED
        else MessageResolution.UNRESOLVED
    )
    invoice_state = (
        InvoiceState.RELEASED
        if snapshot.invoice.state is EnterpriseInvoiceState.RELEASED
        else InvoiceState.HELD
    )
    return ClosureFacts(
        expected_receipt_quantity=snapshot.warehouse_receipt.quantity,
        erp_receipt_quantity=snapshot.erp_receipt.quantity,
        duplicate_material_document_count=max(0, len(source_documents) - 1),
        message_resolution=message_resolution,
        invoice_state=invoice_state,
    )
