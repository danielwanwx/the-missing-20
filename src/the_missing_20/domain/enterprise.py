"""Typed synthetic enterprise records used by the deterministic slice."""

from __future__ import annotations

from enum import StrEnum

from pydantic import AwareDatetime, Field, model_validator

from the_missing_20.domain.execution import EXTERNAL_ID_NAMESPACE, EffectType
from the_missing_20.domain.models import ContractModel, NonEmptyStr, NonNegativeInt, PositiveInt


class MessageStatus(StrEnum):
    FAILED = "FAILED"
    CONSUMED = "CONSUMED"


class EnterpriseInvoiceState(StrEnum):
    HELD = "HELD"
    RELEASED = "RELEASED"


class EnterpriseActionOutcome(StrEnum):
    EXECUTED = "EXECUTED"
    SAFE_NOOP = "SAFE_NOOP"


class EvidenceReadStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class PurchaseOrderLine(ContractModel):
    purchase_order_id: NonEmptyStr
    line_id: NonEmptyStr
    ordered_quantity: PositiveInt
    unit: NonEmptyStr


class WarehouseReceipt(ContractModel):
    receipt_id: NonEmptyStr
    purchase_order_id: NonEmptyStr
    line_id: NonEmptyStr
    quantity: NonNegativeInt


class FailedReceiptMessage(ContractModel):
    message_id: NonEmptyStr
    revision: NonNegativeInt
    purchase_order_id: NonEmptyStr
    line_id: NonEmptyStr
    quantity: PositiveInt
    error_code: NonEmptyStr
    status: MessageStatus
    retry_eligible: bool
    lock_cleared: bool
    consumed_by_execution_id: NonEmptyStr | None


class ErpReceipt(ContractModel):
    purchase_order_id: NonEmptyStr
    line_id: NonEmptyStr
    quantity: NonNegativeInt
    revision: NonNegativeInt


class Invoice(ContractModel):
    invoice_id: NonEmptyStr
    revision: NonNegativeInt
    purchase_order_id: NonEmptyStr
    line_id: NonEmptyStr
    quantity: PositiveInt
    state: EnterpriseInvoiceState
    hold_reason: NonEmptyStr | None
    other_blocking_holds: tuple[NonEmptyStr, ...]
    released_by_execution_id: NonEmptyStr | None


class MaterialDocument(ContractModel):
    material_document_id: NonEmptyStr
    source_message_id: NonEmptyStr
    purchase_order_id: NonEmptyStr
    line_id: NonEmptyStr
    quantity: PositiveInt
    execution_id: NonEmptyStr
    idempotency_key: NonEmptyStr


class BusinessEffect(ContractModel):
    effect_id: NonEmptyStr
    case_id: NonEmptyStr
    trace_id: NonEmptyStr
    execution_id: NonEmptyStr
    idempotency_key: NonEmptyStr
    effect_type: EffectType
    source_record_id: NonEmptyStr
    result_record_ids: tuple[NonEmptyStr, ...]
    committed_at: AwareDatetime


class EnterpriseSnapshot(ContractModel):
    purchase_order: PurchaseOrderLine
    warehouse_receipt: WarehouseReceipt
    failed_message: FailedReceiptMessage
    erp_receipt: ErpReceipt
    invoice: Invoice
    material_documents: tuple[MaterialDocument, ...] = Field(default=())
    business_effects: tuple[BusinessEffect, ...] = Field(default=())


class ScenarioFixture(ContractModel):
    scenario_id: NonEmptyStr
    purchase_order: PurchaseOrderLine
    warehouse_receipt: WarehouseReceipt
    failed_message: FailedReceiptMessage
    erp_receipt: ErpReceipt
    invoice: Invoice
    material_documents: tuple[MaterialDocument, ...] = Field(default=())
    business_effects: tuple[BusinessEffect, ...] = Field(default=())

    @model_validator(mode="after")
    def records_share_one_purchase_order_line(self) -> ScenarioFixture:
        expected = (self.purchase_order.purchase_order_id, self.purchase_order.line_id)
        related = (
            (self.warehouse_receipt.purchase_order_id, self.warehouse_receipt.line_id),
            (self.failed_message.purchase_order_id, self.failed_message.line_id),
            (self.erp_receipt.purchase_order_id, self.erp_receipt.line_id),
            (self.invoice.purchase_order_id, self.invoice.line_id),
        )
        if any(identity != expected for identity in related):
            raise ValueError("all scenario records must share one purchase-order line")
        for document in self.material_documents:
            if (document.purchase_order_id, document.line_id) != expected:
                raise ValueError("material documents must share the scenario purchase-order line")
        receipt_effects = tuple(
            effect
            for effect in self.business_effects
            if effect.effect_type is EffectType.EXTERNAL_RECEIPT
        )
        invoice_effects = tuple(
            effect
            for effect in self.business_effects
            if effect.effect_type is EffectType.EXTERNAL_INVOICE_RELEASE
        )
        if len(receipt_effects) > 1 or len(invoice_effects) > 1:
            raise ValueError("seeded external source history must be unique")
        if len(receipt_effects) == 1:
            if len(self.material_documents) != 1:
                raise ValueError("external receipt history requires exactly one document")
            document = self.material_documents[0]
            effect = receipt_effects[0]
            if (
                self.failed_message.status is not MessageStatus.CONSUMED
                or self.failed_message.consumed_by_execution_id is None
                or document.source_message_id != self.failed_message.message_id
                or document.execution_id != self.failed_message.consumed_by_execution_id
                or document.quantity != self.failed_message.quantity
                or not document.execution_id.startswith(EXTERNAL_ID_NAMESPACE)
                or not document.idempotency_key.startswith(EXTERNAL_ID_NAMESPACE)
                or effect.execution_id != document.execution_id
                or effect.idempotency_key != document.idempotency_key
                or effect.source_record_id != document.source_message_id
                or effect.result_record_ids != (document.material_document_id,)
                or not effect.execution_id.startswith(EXTERNAL_ID_NAMESPACE)
                or not effect.idempotency_key.startswith(EXTERNAL_ID_NAMESPACE)
            ):
                raise ValueError(
                    "external receipt history must link the exact message quantity to one document"
                )
        elif self.material_documents:
            raise ValueError("seeded material documents require one external receipt effect")
        if len(invoice_effects) == 1:
            effect = invoice_effects[0]
            if (
                self.invoice.state is not EnterpriseInvoiceState.RELEASED
                or self.invoice.released_by_execution_id != effect.execution_id
                or effect.source_record_id != self.invoice.invoice_id
                or effect.result_record_ids != (self.invoice.invoice_id,)
                or not effect.execution_id.startswith(EXTERNAL_ID_NAMESPACE)
                or not effect.idempotency_key.startswith(EXTERNAL_ID_NAMESPACE)
            ):
                raise ValueError("external invoice history must link the released invoice exactly")
        if any(
            effect.effect_type
            not in {
                EffectType.EXTERNAL_RECEIPT,
                EffectType.EXTERNAL_INVOICE_RELEASE,
            }
            for effect in self.business_effects
        ):
            raise ValueError("seeded business effects must be externally attributed")
        if self.business_effects and not (receipt_effects or invoice_effects):
            raise ValueError("seeded effects require supported authoritative result records")
        return self


class MaterialDocumentRead(ContractModel):
    status: EvidenceReadStatus
    documents: tuple[MaterialDocument, ...] = Field(default=())
    business_effects: tuple[BusinessEffect, ...] = Field(default=())
    source: NonEmptyStr = "MATERIAL_DOCUMENT"
    reason_code: NonEmptyStr | None = None

    @model_validator(mode="after")
    def availability_is_consistent(self) -> MaterialDocumentRead:
        if self.status is EvidenceReadStatus.AVAILABLE and self.reason_code is not None:
            raise ValueError("available evidence cannot have an unavailability reason")
        if self.status is EvidenceReadStatus.UNAVAILABLE and (
            self.documents or self.business_effects or self.reason_code is None
        ):
            raise ValueError("unavailable evidence requires a reason and no records")
        return self


class EnterpriseMutationResult(ContractModel):
    outcome: EnterpriseActionOutcome
    effect: BusinessEffect
    pre_state: EnterpriseSnapshot
    post_state: EnterpriseSnapshot
