"""Typed synthetic enterprise records used by the deterministic slice."""

from __future__ import annotations

from enum import StrEnum

from pydantic import AwareDatetime, Field, model_validator

from the_missing_20.domain.execution import EffectType
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
        return self


class EnterpriseMutationResult(ContractModel):
    outcome: EnterpriseActionOutcome
    effect: BusinessEffect
    pre_state: EnterpriseSnapshot
    post_state: EnterpriseSnapshot
