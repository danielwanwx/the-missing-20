"""Port for authoritative enterprise reads and controlled writes."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from the_missing_20.domain.enterprise import (
    BusinessEffect,
    EnterpriseMutationResult,
    EnterpriseSnapshot,
    MaterialDocumentRead,
)
from the_missing_20.domain.execution import (
    ReleaseInvoiceParameters,
    RestartReceiptMessageParameters,
)


class EnterpriseSystems(Protocol):
    def read_snapshot(self) -> EnterpriseSnapshot: ...

    def read_material_documents(self) -> MaterialDocumentRead: ...

    def restart_receipt_message(
        self,
        *,
        case_id: str,
        trace_id: str,
        execution_id: str,
        idempotency_key: str,
        parameters: RestartReceiptMessageParameters,
        committed_at: datetime,
    ) -> EnterpriseMutationResult: ...

    def release_invoice(
        self,
        *,
        case_id: str,
        trace_id: str,
        execution_id: str,
        idempotency_key: str,
        parameters: ReleaseInvoiceParameters,
        committed_at: datetime,
    ) -> EnterpriseMutationResult: ...

    def get_business_effect(self, idempotency_key: str) -> BusinessEffect | None: ...


class EnterprisePreconditionFailed(RuntimeError):
    """Raised before mutation when authoritative state cannot prove a safe action."""
