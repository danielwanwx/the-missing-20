"""Authorization, policy, and execution audit contracts."""

from __future__ import annotations

from enum import StrEnum

from pydantic import AwareDatetime, JsonValue

from the_missing_20.domain.models import (
    ActionTool,
    ContractModel,
    HumanRole,
    NonEmptyStr,
    NonNegativeInt,
    PositiveInt,
)

EXTERNAL_ID_NAMESPACE = "external:"


def uses_external_id_namespace(value: str) -> bool:
    return value.startswith(EXTERNAL_ID_NAMESPACE)


class DecisionStage(StrEnum):
    APPROVAL_GATE = "APPROVAL_GATE"
    EXECUTION_GATE = "EXECUTION_GATE"


class PolicyOutcome(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"


class ExecutionAttemptStatus(StrEnum):
    RESERVED = "RESERVED"
    COMPLETED = "COMPLETED"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"


class GrantStatus(StrEnum):
    ISSUED = "ISSUED"
    RESERVED = "RESERVED"
    CONSUMED = "CONSUMED"


class EffectType(StrEnum):
    RECEIPT_RESTART = "RECEIPT_RESTART"
    INVOICE_RELEASE = "INVOICE_RELEASE"
    EXTERNAL_RECEIPT = "EXTERNAL_RECEIPT"
    EXTERNAL_INVOICE_RELEASE = "EXTERNAL_INVOICE_RELEASE"


class PolicyDecision(ContractModel):
    decision_id: NonEmptyStr
    case_id: NonEmptyStr
    trace_id: NonEmptyStr
    authorization_id: NonEmptyStr | None
    execution_id: NonEmptyStr | None
    principal_id: NonEmptyStr
    trusted_role: HumanRole
    tool: ActionTool
    decision: PolicyOutcome
    decision_stage: DecisionStage
    reason_codes: tuple[NonEmptyStr, ...]
    case_version: NonNegativeInt
    parameters_digest: NonEmptyStr
    evidence_digest: NonEmptyStr
    action_digest: NonEmptyStr
    decided_at: AwareDatetime


class ExecutionAttempt(ContractModel):
    execution_id: NonEmptyStr
    authorization_id: NonEmptyStr
    case_id: NonEmptyStr
    trace_id: NonEmptyStr
    idempotency_key: NonEmptyStr
    tool: ActionTool
    canonical_parameters: dict[str, JsonValue]
    command_digest: NonEmptyStr
    status: ExecutionAttemptStatus
    reserved_at: AwareDatetime
    completed_at: AwareDatetime | None


class RestartReceiptMessageParameters(ContractModel):
    message_id: NonEmptyStr
    message_revision: NonNegativeInt
    purchase_order_id: NonEmptyStr
    line_id: NonEmptyStr
    quantity: PositiveInt
    expected_error_code: NonEmptyStr
    expected_message_status: NonEmptyStr


class ReleaseInvoiceParameters(ContractModel):
    invoice_id: NonEmptyStr
    invoice_revision: NonNegativeInt
    purchase_order_id: NonEmptyStr
    line_id: NonEmptyStr
    quantity: PositiveInt
    expected_hold_reason: NonEmptyStr


class DetectionGenesis(ContractModel):
    case_id: NonEmptyStr
    trace_id: NonEmptyStr
    fixture_path: NonEmptyStr
    fixture_digest: NonEmptyStr
    initial_case_json: NonEmptyStr
    detection_facts: dict[str, JsonValue]
    detector_evidence_ids: tuple[NonEmptyStr, ...]
    created_at: AwareDatetime
