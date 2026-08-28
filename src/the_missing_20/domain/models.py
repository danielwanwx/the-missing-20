"""Immutable contracts shared across deterministic application boundaries."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    model_validator,
)

from the_missing_20.domain.states import CaseStatus

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
NonNegativeInt = Annotated[int, Field(ge=0)]
PositiveInt = Annotated[int, Field(gt=0)]


class ContractModel(BaseModel):
    """Fail-closed base configuration for every public contract."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True, allow_inf_nan=False)


class HumanRole(StrEnum):
    INTEGRATION_OPERATOR = "INTEGRATION_OPERATOR"
    AP_APPROVER = "AP_APPROVER"


class ActionTool(StrEnum):
    RESTART_RECEIPT_MESSAGE = "restart_receipt_message"
    RELEASE_INVOICE = "release_invoice"


AUTHORIZED_TOOLS_BY_ROLE: dict[HumanRole, frozenset[ActionTool]] = {
    HumanRole.INTEGRATION_OPERATOR: frozenset({ActionTool.RESTART_RECEIPT_MESSAGE}),
    HumanRole.AP_APPROVER: frozenset({ActionTool.RELEASE_INVOICE}),
}


def validate_role_tool_pair(role: HumanRole, tool: ActionTool) -> None:
    if tool not in AUTHORIZED_TOOLS_BY_ROLE[role]:
        raise ValueError(f"role {role.value} cannot authorize tool {tool.value}")


class ApprovalDecision(StrEnum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class EvidenceSourceType(StrEnum):
    WAREHOUSE = "WAREHOUSE"
    FAILED_MESSAGE_QUEUE = "FAILED_MESSAGE_QUEUE"
    ERP_RECEIPT = "ERP_RECEIPT"
    MATERIAL_DOCUMENT = "MATERIAL_DOCUMENT"
    INVOICE = "INVOICE"
    KNOWLEDGE_BASE = "KNOWLEDGE_BASE"


class HypothesisType(StrEnum):
    RETRYABLE_MESSAGE = "RETRYABLE_MESSAGE"
    GENUINE_SHORT_SHIPMENT = "GENUINE_SHORT_SHIPMENT"
    ALREADY_POSTED = "ALREADY_POSTED"


class HypothesisConclusion(StrEnum):
    SUPPORTED = "SUPPORTED"
    REJECTED = "REJECTED"
    NEEDS_EVIDENCE = "NEEDS_EVIDENCE"


class ConfidenceBand(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class EvaluationDecision(StrEnum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    MORE_EVIDENCE = "MORE_EVIDENCE"


class OperationResult(StrEnum):
    EXECUTED = "EXECUTED"
    SAFE_NOOP = "SAFE_NOOP"
    FAILED = "FAILED"


class InvoiceState(StrEnum):
    HELD = "HELD"
    RELEASED = "RELEASED"


class MessageResolution(StrEnum):
    UNRESOLVED = "UNRESOLVED"
    CLEARED = "CLEARED"
    SAFELY_CONSUMED = "SAFELY_CONSUMED"


class Discrepancy(ContractModel):
    expected_quantity: PositiveInt
    observed_quantity: NonNegativeInt
    missing_quantity: NonNegativeInt
    unit: NonEmptyStr

    @model_validator(mode="after")
    def quantity_math_is_consistent(self) -> Discrepancy:
        if self.expected_quantity - self.observed_quantity != self.missing_quantity:
            raise ValueError("missing_quantity must equal expected_quantity - observed_quantity")
        return self


class Case(ContractModel):
    case_id: NonEmptyStr
    case_version: NonNegativeInt
    scenario_id: NonEmptyStr
    status: CaseStatus
    discrepancy: Discrepancy
    current_evidence_revision: NonNegativeInt
    created_at: AwareDatetime
    updated_at: AwareDatetime

    @model_validator(mode="after")
    def timestamps_are_monotonic(self) -> Case:
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot precede created_at")
        return self


class EvidenceProvenance(ContractModel):
    source_system: NonEmptyStr
    collection_method: NonEmptyStr
    collected_by: NonEmptyStr


class EvidenceItem(ContractModel):
    evidence_id: NonEmptyStr
    case_id: NonEmptyStr
    trace_id: NonEmptyStr
    subject: NonEmptyStr
    source_type: EvidenceSourceType
    source_record_id: NonEmptyStr
    observed_at: AwareDatetime
    content_digest: NonEmptyStr
    admitted_fields: Annotated[dict[NonEmptyStr, JsonValue], Field(min_length=1)]
    provenance: EvidenceProvenance


class HypothesisResult(ContractModel):
    hypothesis_type: HypothesisType
    conclusion: HypothesisConclusion
    confidence_band: ConfidenceBand
    supporting_evidence_ids: tuple[NonEmptyStr, ...]
    contradicting_evidence_ids: tuple[NonEmptyStr, ...]
    missing_evidence: tuple[NonEmptyStr, ...]


class EvaluationResult(ContractModel):
    decision: EvaluationDecision
    validated_evidence_ids: tuple[NonEmptyStr, ...]
    citation_closure: Annotated[dict[NonEmptyStr, JsonValue], Field(min_length=1)] | None = None
    failed_invariants: tuple[NonEmptyStr, ...]
    allowed_next_action: ActionTool | None
    evaluator_version: NonEmptyStr
    trace_id: NonEmptyStr


class InvestigationDecision(StrEnum):
    RECOMMEND_RECEIPT_RESTART = "RECOMMEND_RECEIPT_RESTART"
    RECEIPT_ALREADY_POSTED = "RECEIPT_ALREADY_POSTED"
    REQUIRE_EVIDENCE = "REQUIRE_EVIDENCE"
    PROTECT = "PROTECT"
    EVALUATOR_REJECTED = "EVALUATOR_REJECTED"


class InvestigationAssessment(ContractModel):
    assessment_id: NonEmptyStr
    case_id: NonEmptyStr
    trace_id: NonEmptyStr
    hypothesis: HypothesisResult
    evaluation: EvaluationResult
    admitted_evidence_ids: tuple[NonEmptyStr, ...]
    missing_evidence_sources: tuple[NonEmptyStr, ...]
    decision: InvestigationDecision
    reason_codes: tuple[NonEmptyStr, ...]
    assessed_at: AwareDatetime


class Approval(ContractModel):
    approval_id: NonEmptyStr
    case_id: NonEmptyStr
    trace_id: NonEmptyStr
    case_version: NonNegativeInt
    principal_id: NonEmptyStr
    role: HumanRole
    tool: ActionTool
    parameters_digest: NonEmptyStr
    decision: ApprovalDecision
    decided_at: AwareDatetime

    @model_validator(mode="after")
    def role_can_authorize_tool(self) -> Approval:
        validate_role_tool_pair(self.role, self.tool)
        return self


class ActionGrant(ContractModel):
    authorization_id: NonEmptyStr
    case_id: NonEmptyStr
    trace_id: NonEmptyStr
    case_version: NonNegativeInt
    principal_id: NonEmptyStr
    role: HumanRole
    tool: ActionTool
    complete_parameters: Annotated[dict[NonEmptyStr, JsonValue], Field(min_length=1)]
    evidence_digest: NonEmptyStr
    action_digest: NonEmptyStr
    issued_at: AwareDatetime
    expires_at: AwareDatetime
    signature: NonEmptyStr

    @model_validator(mode="after")
    def grant_is_authorized_and_current(self) -> ActionGrant:
        validate_role_tool_pair(self.role, self.tool)
        if self.expires_at <= self.issued_at:
            raise ValueError("expires_at must follow issued_at")
        return self


class ExecutionReceipt(ContractModel):
    execution_id: NonEmptyStr
    authorization_id: NonEmptyStr
    case_id: NonEmptyStr
    pre_state_digest: NonEmptyStr
    operation_result: OperationResult
    post_state_digest: NonEmptyStr
    postconditions: Annotated[dict[NonEmptyStr, bool], Field(min_length=1)]
    material_document_ids: tuple[NonEmptyStr, ...]
    executed_at: AwareDatetime
    trace_id: NonEmptyStr


class ClosureFacts(ContractModel):
    expected_receipt_quantity: PositiveInt
    erp_receipt_quantity: NonNegativeInt
    duplicate_material_document_count: NonNegativeInt
    message_resolution: MessageResolution
    invoice_state: InvoiceState

    def satisfies_closure(self) -> bool:
        return (
            self.erp_receipt_quantity == self.expected_receipt_quantity
            and self.duplicate_material_document_count == 0
            and self.message_resolution
            in {MessageResolution.CLEARED, MessageResolution.SAFELY_CONSUMED}
            and self.invoice_state is InvoiceState.RELEASED
        )
