"""Source-correlated facts for the production-shaped procurement demo case.

This model deliberately separates a queue timeout from an ERP write result.  It
is the compact case truth used by the demo; adapters may project it into ERP,
quality-registry and integration records, but none may infer a retry from the
integration attempt alone.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import model_validator

from the_missing_20.domain.models import ContractModel, NonEmptyStr, NonNegativeInt, PositiveInt


class MatchLevel(StrEnum):
    THREE_WAY = "THREE_WAY"
    FOUR_WAY = "FOUR_WAY"


class QualityDisposition(StrEnum):
    APPROVED = "APPROVED"
    PENDING = "PENDING"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    LOT_MISMATCH = "LOT_MISMATCH"


class IntegrationOutcome(StrEnum):
    UNKNOWN = "UNKNOWN"
    ACKNOWLEDGED = "ACKNOWLEDGED"


class CaseDisposition(StrEnum):
    RECOVERY_READY = "RECOVERY_READY"
    RECONCILE_ONLY = "RECONCILE_ONLY"
    SAFE_STOP = "SAFE_STOP"
    NEEDS_EVIDENCE = "NEEDS_EVIDENCE"


class AmbiguousReceiptCase(ContractModel):
    """The minimal evidence facts behind the 100/80/8/12 investigation.

    ``erp_receipt_key_found`` is intentionally nullable.  An integration
    timeout leaves it unknown until the agent performs the ERP business-key
    reread.  A value of ``False`` is a proven absence, not a guess.
    """

    case_id: NonEmptyStr
    purchase_order_id: NonEmptyStr
    invoice_id: NonEmptyStr
    supplier_lot: NonEmptyStr
    receipt_business_key: NonEmptyStr
    quality_release_key: NonEmptyStr
    match_level: MatchLevel
    physically_arrived: PositiveInt
    available_quantity: NonNegativeInt
    quality_hold_quantity: NonNegativeInt
    receipt_unresolved_quantity: NonNegativeInt
    invoice_held: bool
    quality_disposition: QualityDisposition
    integration_outcome: IntegrationOutcome
    erp_receipt_key_found: bool | None = None
    quality_transfer_key_found: bool | None = None

    @model_validator(mode="after")
    def quantities_form_a_complete_visible_state(self) -> AmbiguousReceiptCase:
        if (
            self.available_quantity + self.quality_hold_quantity + self.receipt_unresolved_quantity
            != self.physically_arrived
        ):
            raise ValueError(
                "available, quality-held, and unresolved quantities must total arrival"
            )
        if self.receipt_unresolved_quantity == 0 and self.erp_receipt_key_found is None:
            raise ValueError("resolved receipt quantity requires an ERP business-key result")
        if (
            self.integration_outcome is IntegrationOutcome.ACKNOWLEDGED
            and self.erp_receipt_key_found is not True
        ):
            raise ValueError("an acknowledged integration outcome requires the ERP receipt key")
        return self

    @property
    def evidence_complete(self) -> bool:
        return (
            self.erp_receipt_key_found is not None and self.quality_transfer_key_found is not None
        )

    def disposition(self) -> CaseDisposition:
        """Return the deterministic action class after source reads complete."""

        if not self.evidence_complete:
            return CaseDisposition.NEEDS_EVIDENCE
        if self.quality_disposition is not QualityDisposition.APPROVED:
            return CaseDisposition.SAFE_STOP
        if self.erp_receipt_key_found or self.quality_transfer_key_found:
            return CaseDisposition.RECONCILE_ONLY
        return CaseDisposition.RECOVERY_READY

    def allowed_actions(self) -> tuple[str, ...]:
        """Return the smallest bounded recovery packet, never inferred from a timeout."""

        if self.disposition() is not CaseDisposition.RECOVERY_READY:
            return ()
        actions: list[str] = []
        if self.receipt_unresolved_quantity:
            actions.append("POST_IDEMPOTENT_RECEIPT")
        if self.quality_hold_quantity:
            actions.append("TRANSFER_APPROVED_QUALITY_STOCK")
        if self.invoice_held:
            actions.append("REVALIDATE_LINKED_INVOICE")
        return tuple(actions)

    def evidence_projection(self) -> dict[str, object]:
        """Provide a display-safe source tuple; no result is hidden in prose."""

        return {
            "case_id": self.case_id,
            "purchase_order_id": self.purchase_order_id,
            "invoice_id": self.invoice_id,
            "supplier_lot": self.supplier_lot,
            "receipt_business_key": self.receipt_business_key,
            "quality_release_key": self.quality_release_key,
            "match_level": self.match_level,
            "quantities": {
                "physically_arrived": self.physically_arrived,
                "available": self.available_quantity,
                "quality_hold": self.quality_hold_quantity,
                "receipt_unresolved": self.receipt_unresolved_quantity,
            },
            "invoice_held": self.invoice_held,
            "quality_disposition": self.quality_disposition,
            "integration_outcome": self.integration_outcome,
            "erp_receipt_key_found": self.erp_receipt_key_found,
            "quality_transfer_key_found": self.quality_transfer_key_found,
            "disposition": self.disposition(),
            "allowed_actions": self.allowed_actions(),
        }


def primary_case() -> AmbiguousReceiptCase:
    """Return the recorded branch after the agent's authoritative key reads."""

    return AmbiguousReceiptCase(
        case_id="M20-PO-4817",
        purchase_order_id="PO-4817",
        invoice_id="INV-4817",
        supplier_lot="LOT-4817-QA",
        receipt_business_key="RCPT-4817-L2-001",
        quality_release_key="QUALITY-4817-L1-001",
        match_level=MatchLevel.FOUR_WAY,
        physically_arrived=100,
        available_quantity=80,
        quality_hold_quantity=8,
        receipt_unresolved_quantity=12,
        invoice_held=True,
        quality_disposition=QualityDisposition.APPROVED,
        integration_outcome=IntegrationOutcome.UNKNOWN,
        erp_receipt_key_found=False,
        quality_transfer_key_found=False,
    )
