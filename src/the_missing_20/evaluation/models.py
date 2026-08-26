"""Strict public contracts for Golden v1 manifests and reports."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from the_missing_20.domain.execution import uses_external_id_namespace
from the_missing_20.domain.models import ContractModel, NonEmptyStr, NonNegativeInt


class GoldenWorkflow(StrEnum):
    FULL_RESOLUTION = "FULL_RESOLUTION"
    INVESTIGATION_ONLY = "INVESTIGATION_ONLY"
    RECEIPT_AUTHORIZATION = "RECEIPT_AUTHORIZATION"
    RECEIPT_EXECUTION = "RECEIPT_EXECUTION"
    INVOICE_AUTHORIZATION = "INVOICE_AUTHORIZATION"


class TemporalHook(StrEnum):
    NONE = "NONE"
    EXTERNAL_RECEIPT_POSTED_AFTER_APPROVAL = "EXTERNAL_RECEIPT_POSTED_AFTER_APPROVAL"
    MATERIAL_DOCUMENT_SOURCE_UNAVAILABLE = "MATERIAL_DOCUMENT_SOURCE_UNAVAILABLE"
    ADVANCE_CLOCK_BEYOND_GRANT_TTL = "ADVANCE_CLOCK_BEYOND_GRANT_TTL"
    CORRUPT_AUTHORITATIVE_RECEIPT_AFTER_COMMIT = "CORRUPT_AUTHORITATIVE_RECEIPT_AFTER_COMMIT"
    CRASH_AFTER_ENTERPRISE_COMMIT = "CRASH_AFTER_ENTERPRISE_COMMIT"


class AuthorizationReuse(StrEnum):
    NONE = "NONE"
    REPLAY = "REPLAY"
    DUPLICATE = "DUPLICATE"


class InvoiceRequestStage(StrEnum):
    BEFORE_RECEIPT_VERIFIED = "BEFORE_RECEIPT_VERIFIED"
    AFTER_RECEIPT_VERIFIED = "AFTER_RECEIPT_VERIFIED"


class TamperTarget(StrEnum):
    NONE = "NONE"
    RECEIPT_PARAMETERS = "RECEIPT_PARAMETERS"
    EVIDENCE_DIGEST = "EVIDENCE_DIGEST"


class GoldenOutcome(StrEnum):
    CLOSED = "CLOSED"
    PROTECTED = "PROTECTED"
    NEEDS_EVIDENCE = "NEEDS_EVIDENCE"
    DENIED = "DENIED"
    SAFE_NOOP = "SAFE_NOOP"
    EXECUTING_HARD_STOP = "EXECUTING_HARD_STOP"


class GoldenRequest(ContractModel):
    receipt_principal_id: NonEmptyStr = "operator-001"
    invoice_principal_id: NonEmptyStr = "ap-approver-001"
    receipt_execution_id: NonEmptyStr
    receipt_idempotency_key: NonEmptyStr
    invoice_execution_id: NonEmptyStr
    invoice_idempotency_key: NonEmptyStr
    authorization_reuse: AuthorizationReuse = AuthorizationReuse.NONE
    tamper_target: TamperTarget = TamperTarget.NONE
    evaluator_rejects: bool = False
    admit_evidence_after_approval: bool = False
    invoice_request_stage: InvoiceRequestStage = InvoiceRequestStage.AFTER_RECEIPT_VERIFIED

    @model_validator(mode="after")
    def local_ids_do_not_use_external_namespace(self) -> GoldenRequest:
        values = (
            self.receipt_execution_id,
            self.receipt_idempotency_key,
            self.invoice_execution_id,
            self.invoice_idempotency_key,
        )
        if any(uses_external_id_namespace(item) for item in values):
            raise ValueError("local request identities cannot use external namespace")
        return self


class GoldenExpected(ContractModel):
    outcome: GoldenOutcome
    case_status: NonEmptyStr
    hypothesis: NonEmptyStr
    receipt_action_eligible: bool
    invoice_action_eligible: bool
    receipt_effect_count: NonNegativeInt
    invoice_effect_count: NonNegativeInt
    reason_code: NonEmptyStr | None = None


class GoldenManifest(ContractModel):
    schema_version: str = Field(pattern=r"^golden-case/v1$")
    case_key: NonEmptyStr
    title: NonEmptyStr
    fixture: NonEmptyStr
    workflow: GoldenWorkflow
    request: GoldenRequest
    temporal_hook: TemporalHook
    expected: GoldenExpected
    required_invariants: tuple[NonEmptyStr, ...]


class InvariantResult(ContractModel):
    name: NonEmptyStr
    passed: bool
    expected: object
    observed: object
    evidence: NonEmptyStr
