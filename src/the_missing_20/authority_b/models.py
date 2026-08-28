"""Application-owned Authority Rebaseline B records.

The contracts in this module make the authority boundary visible in Python types.  An
advisory record is safe to display but is never a valid input to the deterministic
classifier, policy, or quorum grant.  All records are frozen and use canonical JSON
when digests are computed so repeated runs are byte-stable.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Annotated, Any, Final, Literal

from pydantic import Field, model_validator

from the_missing_20.domain.enterprise import EvidenceReadStatus
from the_missing_20.domain.models import (
    ActionTool,
    ConfidenceBand,
    ContractModel,
    EvidenceItem,
    EvidenceSourceType,
    HumanRole,
    HypothesisConclusion,
    HypothesisType,
    NonEmptyStr,
)

ADVISORY_AUTHORITY_LABEL: Final = "ADVISORY — NOT AN OPERATIONAL DECISION"
SAFETY_AUTHORITY_LABEL: Final = "DETERMINISTIC SAFETY PROOF"
USEFULNESS_AUTHORITY_LABEL: Final = "NON-AUTHORITATIVE AI USEFULNESS PROOF"
REQUIRED_AUTHORITY_ROLES: tuple[HumanRole, ...] = (
    HumanRole.INTEGRATION_OPERATOR,
    HumanRole.AP_APPROVER,
)


def canonical_json(value: object) -> str:
    """Encode a JSON-compatible value without process-dependent formatting."""

    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


class AuthorityModel(ContractModel):
    """Frozen strict contract base for Authority B records."""


class AdvisoryStatus(StrEnum):
    NOT_REQUESTED = "NOT_REQUESTED"
    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


class OperationalClassification(StrEnum):
    RETRYABLE_MESSAGE = "RETRYABLE_MESSAGE"
    RECEIPT_ALREADY_POSTED = "RECEIPT_ALREADY_POSTED"
    INVOICE_RELEASE_READY = "INVOICE_RELEASE_READY"
    GENUINE_SHORT_SHIPMENT = "GENUINE_SHORT_SHIPMENT"
    REQUIRE_EVIDENCE = "REQUIRE_EVIDENCE"


class OperationalEligibility(StrEnum):
    PENDING_APPROVAL = "PENDING_APPROVAL"
    NO_ACTION = "NO_ACTION"
    REQUIRE_EVIDENCE = "REQUIRE_EVIDENCE"


# Friendly aliases for callers that name the contract as a policy decision.
ActionEligibility = OperationalEligibility


class QuorumStatus(StrEnum):
    OPEN = "OPEN"
    QUORUM_PENDING = "QUORUM_PENDING"
    GRANTED = "GRANTED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CONSUMED = "CONSUMED"


class AttestationDecision(StrEnum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ProofStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_RUN = "NOT_RUN"


class EvidenceClass(StrEnum):
    """The strength of evidence behind a product-facing claim.

    ``ProofStatus`` answers whether a particular check passed.  This separate
    taxonomy answers what a passing (or failing) record is allowed to support.  In
    particular, a scripted trace can pass its own deterministic checks without
    becoming evidence of stable real-provider usefulness.
    """

    PROVEN = "PROVEN"
    SCRIPTED_PROOF = "SCRIPTED_PROOF"
    NOT_PROVEN = "NOT_PROVEN"


class M4PromotionStatus(StrEnum):
    """Top-level M4 promotion states under the degradation disclosure rebaseline."""

    NOT_READY = "NOT_READY"
    PASS_WITH_DISCLOSED_AI_DEGRADATION = "PASS_WITH_DISCLOSED_AI_DEGRADATION"


# Friendly aliases used by artifact/report adapters that call the taxonomy a
# disposition or acceptance status.  Keeping these aliases local avoids creating
# multiple wire-level vocabularies for the same three evidence classes.
EvidenceDisposition = EvidenceClass
M4AcceptanceStatus = M4PromotionStatus


class AdvisoryHypothesis(AuthorityModel):
    """A bounded, public-safe model hypothesis; citations are not authority."""

    hypothesis_id: NonEmptyStr
    investigator_role: NonEmptyStr
    hypothesis_type: HypothesisType
    conclusion: HypothesisConclusion
    confidence_band: ConfidenceBand
    explanation: NonEmptyStr
    supporting_evidence_ids: tuple[NonEmptyStr, ...] = Field(default=())
    contradicting_evidence_ids: tuple[NonEmptyStr, ...] = Field(default=())
    missing_evidence: tuple[NonEmptyStr, ...] = Field(default=())

    @model_validator(mode="after")
    def citation_ids_are_unique(self) -> AdvisoryHypothesis:
        for label, values in (
            ("supporting", self.supporting_evidence_ids),
            ("contradicting", self.contradicting_evidence_ids),
            ("missing", self.missing_evidence),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{label} advisory evidence IDs contain duplicates")
        return self


class AdvisoryDissent(AuthorityModel):
    """Preserved disagreement between advisory investigators."""

    investigator_role: NonEmptyStr
    statement: NonEmptyStr
    hypothesis_type: HypothesisType | None = None
    confidence_band: ConfidenceBand | None = None


class AdvisoryKnowledgeCitation(AuthorityModel):
    """Allowlisted procedural context, never current-state evidence."""

    knowledge_id: NonEmptyStr
    version: NonEmptyStr
    content_digest: NonEmptyStr
    allowed_use: Literal["PROCEDURE_ONLY", "ERROR_DEFINITION_ONLY"]


class AdvisoryUsage(AuthorityModel):
    request_count: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    latency_ms: int = Field(default=0, ge=0)
    estimated_cost_usd: float = Field(default=0.0, ge=0)


class AdvisoryInvestigation(AuthorityModel):
    """Versioned, immutable advisory branch output.

    The authority label is a required literal rather than presentation-only metadata;
    serialized artifacts therefore retain the warning even when rendered elsewhere.
    """

    schema_version: Literal["advisory-investigation/v1"] = "advisory-investigation/v1"
    advisory_id: NonEmptyStr
    case_id: NonEmptyStr
    trace_id: NonEmptyStr
    case_version: int = Field(ge=0)
    provider: NonEmptyStr | None = None
    model: NonEmptyStr | None = None
    prompt_digest: NonEmptyStr | None = None
    status: AdvisoryStatus
    hypotheses: tuple[AdvisoryHypothesis, ...] = Field(default=())
    proposed_evidence_gaps: tuple[NonEmptyStr, ...] = Field(default=())
    deterministic_evidence_gaps: tuple[NonEmptyStr, ...] = Field(default=())
    dissent: tuple[AdvisoryDissent, ...] = Field(default=())
    knowledge_citations: tuple[AdvisoryKnowledgeCitation, ...] = Field(default=())
    incident_report: NonEmptyStr | None = None
    warnings: tuple[NonEmptyStr, ...] = Field(default=())
    usage: AdvisoryUsage = Field(default_factory=AdvisoryUsage)
    error_code: NonEmptyStr | None = None
    failed_stage: NonEmptyStr | None = None
    created_at: datetime
    updated_at: datetime
    authority_label: Literal["ADVISORY — NOT AN OPERATIONAL DECISION"] = ADVISORY_AUTHORITY_LABEL

    @model_validator(mode="after")
    def status_metadata_is_consistent(self) -> AdvisoryInvestigation:
        if self.updated_at < self.created_at:
            raise ValueError("advisory updated_at cannot precede created_at")
        terminal = {
            AdvisoryStatus.DEGRADED,
            AdvisoryStatus.UNAVAILABLE,
            AdvisoryStatus.COMPLETE,
            AdvisoryStatus.PARTIAL,
        }
        if self.status in terminal and self.status is not AdvisoryStatus.COMPLETE:
            if self.status is AdvisoryStatus.PARTIAL and not self.warnings:
                raise ValueError("partial advisory requires a warning")
            if self.status in {AdvisoryStatus.DEGRADED, AdvisoryStatus.UNAVAILABLE} and not (
                self.error_code or self.warnings
            ):
                raise ValueError("degraded or unavailable advisory requires a reason")
        if self.status is AdvisoryStatus.RUNNING and self.error_code is not None:
            raise ValueError("running advisory cannot carry a terminal error")
        return self


class OperationalInvariant(AuthorityModel):
    name: NonEmptyStr
    passed: bool


class OperationalDecision(AuthorityModel):
    """Deterministic operational result with no advisory-shaped fields."""

    schema_version: Literal["operational-decision/v1"] = "operational-decision/v1"
    decision_id: NonEmptyStr
    case_id: NonEmptyStr
    trace_id: NonEmptyStr
    case_version: int = Field(ge=0)
    classification: OperationalClassification
    eligibility: OperationalEligibility
    allowed_action: ActionTool | None = None
    reason_codes: tuple[NonEmptyStr, ...] = Field(min_length=1)
    authoritative_evidence_ids: tuple[NonEmptyStr, ...] = Field(default=())
    authoritative_source_types: tuple[EvidenceSourceType, ...] = Field(default=())
    source_digest: NonEmptyStr
    invariants: tuple[OperationalInvariant, ...] = Field(default=())
    required_approval_roles: tuple[HumanRole, ...] = REQUIRED_AUTHORITY_ROLES
    decision_digest: str = Field(default="")

    @model_validator(mode="after")
    def decision_is_self_consistent(self) -> OperationalDecision:
        evidence = tuple(self.authoritative_evidence_ids)
        sources = tuple(self.authoritative_source_types)
        if evidence != tuple(sorted(evidence)) or len(evidence) != len(set(evidence)):
            raise ValueError("operational evidence IDs must be unique and stably ordered")
        if sources != tuple(sorted(sources, key=lambda item: item.value)) or len(sources) != len(
            set(sources)
        ):
            raise ValueError("operational source types must be unique and stably ordered")
        if self.required_approval_roles != REQUIRED_AUTHORITY_ROLES:
            raise ValueError("operational decisions require the exact two-role quorum")
        if self.eligibility is OperationalEligibility.PENDING_APPROVAL and (
            self.allowed_action is None
        ):
            raise ValueError("pending approval requires an allowed action")
        if self.eligibility is not OperationalEligibility.PENDING_APPROVAL and (
            self.allowed_action is not None
        ):
            raise ValueError("non-actionable decisions cannot carry an allowed action")
        expected = self._computed_digest()
        if not self.decision_digest:
            object.__setattr__(self, "decision_digest", expected)
        elif self.decision_digest != expected:
            raise ValueError("operational decision digest mismatch")
        return self

    def _computed_digest(self) -> str:
        return digest(self.model_dump(mode="json", exclude={"decision_digest"}))


class AuthorizationIntent(AuthorityModel):
    """Immutable intent to authorize one exact deterministic operation."""

    schema_version: Literal["authorization-intent/v1"] = "authorization-intent/v1"
    intent_id: NonEmptyStr
    case_id: NonEmptyStr
    trace_id: NonEmptyStr
    case_version: int = Field(ge=0)
    decision_digest: NonEmptyStr
    tool: ActionTool
    complete_parameters: Annotated[dict[NonEmptyStr, Any], Field(min_length=1)]
    parameters_digest: NonEmptyStr
    admitted_evidence_digest: NonEmptyStr
    created_at: datetime
    expires_at: datetime
    status: QuorumStatus = QuorumStatus.OPEN
    intent_digest: str = Field(default="")

    @model_validator(mode="after")
    def intent_is_bounded_and_self_consistent(self) -> AuthorizationIntent:
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("authorization intent must be timezone-aware")
        if self.expires_at <= self.created_at:
            raise ValueError("authorization intent must expire after creation")
        if self.expires_at > self.created_at + timedelta(minutes=5):
            raise ValueError("authorization intent expiry cannot exceed five minutes")
        expected_parameters = digest(self.complete_parameters)
        if self.parameters_digest != expected_parameters:
            raise ValueError("authorization intent parameters digest mismatch")
        # Status is a mutable lifecycle projection; the intent digest binds only
        # the immutable action request and never changes when the first approval
        # moves the intent to QUORUM_PENDING.
        expected = digest(self.model_dump(mode="json", exclude={"intent_digest", "status"}))
        if not self.intent_digest:
            object.__setattr__(self, "intent_digest", expected)
        elif self.intent_digest != expected:
            raise ValueError("authorization intent digest mismatch")
        return self


class QuorumAttestation(AuthorityModel):
    schema_version: Literal["quorum-attestation/v1"] = "quorum-attestation/v1"
    attestation_id: NonEmptyStr
    intent_id: NonEmptyStr
    intent_digest: NonEmptyStr
    principal_id: NonEmptyStr
    role: HumanRole
    decision: AttestationDecision
    attested_at: datetime
    attestation_digest: str = Field(default="")

    @model_validator(mode="after")
    def attestation_is_self_consistent(self) -> QuorumAttestation:
        expected = digest(self.model_dump(mode="json", exclude={"attestation_digest"}))
        if not self.attestation_digest:
            object.__setattr__(self, "attestation_digest", expected)
        elif self.attestation_digest != expected:
            raise ValueError("attestation digest mismatch")
        return self


class QuorumActionGrant(AuthorityModel):
    """Application-signed grant produced only by the exact two-role quorum."""

    schema_version: Literal["quorum-action-grant/v1"] = "quorum-action-grant/v1"
    grant_id: NonEmptyStr
    intent_id: NonEmptyStr
    intent_digest: NonEmptyStr
    case_id: NonEmptyStr
    trace_id: NonEmptyStr
    case_version: int = Field(ge=0)
    decision_digest: NonEmptyStr
    tool: ActionTool
    complete_parameters: Annotated[dict[NonEmptyStr, Any], Field(min_length=1)]
    parameters_digest: NonEmptyStr
    admitted_evidence_digest: NonEmptyStr
    approval_ids: tuple[NonEmptyStr, NonEmptyStr]
    principal_ids: tuple[NonEmptyStr, NonEmptyStr]
    roles: tuple[HumanRole, HumanRole]
    issued_at: datetime
    expires_at: datetime
    grant_status: Literal["ISSUED"] = "ISSUED"
    signature: NonEmptyStr
    grant_digest: str = Field(default="")

    @model_validator(mode="after")
    def grant_contains_exact_quorum(self) -> QuorumActionGrant:
        if self.expires_at <= self.issued_at:
            raise ValueError("quorum grant must expire after issuance")
        if set(self.roles) != set(REQUIRED_AUTHORITY_ROLES) or len(set(self.roles)) != 2:
            raise ValueError("quorum grant requires one operator and one AP approver")
        if len(set(self.principal_ids)) != 2:
            raise ValueError("quorum grant requires two distinct principals")
        if self.parameters_digest != digest(self.complete_parameters):
            raise ValueError("quorum grant parameters digest mismatch")
        expected = digest(self.model_dump(mode="json", exclude={"grant_digest", "signature"}))
        if not self.grant_digest:
            object.__setattr__(self, "grant_digest", expected)
        elif self.grant_digest != expected:
            raise ValueError("quorum grant digest mismatch")
        return self

    def _computed_digest(self) -> str:
        return digest(self.model_dump(mode="json", exclude={"grant_digest", "signature"}))


class QuorumResult(AuthorityModel):
    status: QuorumStatus
    intent: AuthorizationIntent
    attestation: QuorumAttestation
    grant: QuorumActionGrant | None = None

    @model_validator(mode="after")
    def result_matches_status(self) -> QuorumResult:
        if self.status is QuorumStatus.GRANTED and self.grant is None:
            raise ValueError("granted quorum result requires a grant")
        if self.status is not QuorumStatus.GRANTED and self.grant is not None:
            raise ValueError("non-granted quorum result cannot carry a grant")
        return self


class ProofCheck(AuthorityModel):
    check_id: NonEmptyStr
    status: ProofStatus
    detail: NonEmptyStr


class SafetyProof(AuthorityModel):
    schema_version: Literal["safety-proof/v1"] = "safety-proof/v1"
    proof_id: NonEmptyStr
    status: ProofStatus
    checks: tuple[ProofCheck, ...] = Field(min_length=1)
    authority_label: Literal["DETERMINISTIC SAFETY PROOF"] = SAFETY_AUTHORITY_LABEL
    model_independent: Literal[True] = True

    @model_validator(mode="after")
    def status_matches_checks(self) -> SafetyProof:
        all_passed = all(item.status is ProofStatus.PASS for item in self.checks)
        if (self.status is ProofStatus.PASS) != all_passed:
            raise ValueError("safety proof status does not match its checks")
        return self


class AIUsefulnessProof(AuthorityModel):
    schema_version: Literal["ai-usefulness-proof/v1"] = "ai-usefulness-proof/v1"
    proof_id: NonEmptyStr
    status: ProofStatus
    checks: tuple[ProofCheck, ...] = Field(min_length=1)
    advisory_status: AdvisoryStatus
    provider: NonEmptyStr | None = None
    requests: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    estimated_cost_usd: float = Field(default=0.0, ge=0)
    evidence_class: EvidenceClass = EvidenceClass.PROVEN
    authority_label: Literal["NON-AUTHORITATIVE AI USEFULNESS PROOF"] = USEFULNESS_AUTHORITY_LABEL
    operational_authority: Literal[False] = False

    @model_validator(mode="after")
    def status_matches_checks(self) -> AIUsefulnessProof:
        all_passed = all(item.status is ProofStatus.PASS for item in self.checks)
        if (self.status is ProofStatus.PASS) != all_passed:
            raise ValueError("AI usefulness proof status does not match its checks")
        if self.evidence_class is EvidenceClass.NOT_PROVEN and self.status is ProofStatus.PASS:
            raise ValueError("unproven AI usefulness cannot have PASS status")
        return self


class DecisionWorkspaceSnapshot(AuthorityModel):
    schema_version: Literal["decision-workspace-snapshot/v1"] = "decision-workspace-snapshot/v1"
    snapshot_id: NonEmptyStr
    case_id: NonEmptyStr
    trace_id: NonEmptyStr
    case_version: int = Field(ge=0)
    operational_decision: OperationalDecision
    advisory: AdvisoryInvestigation | None = None
    approval_state: QuorumStatus
    approval_ids: tuple[NonEmptyStr, ...] = Field(default=())
    effects: tuple[Mapping[str, Any], ...] = Field(default=())
    timeline: tuple[Mapping[str, Any], ...] = Field(default=())
    safety_proof_status: ProofStatus | None = None
    ai_usefulness_proof_status: ProofStatus | None = None
    authority_label: Literal["ADVISORY — NOT AN OPERATIONAL DECISION"] = ADVISORY_AUTHORITY_LABEL

    @model_validator(mode="after")
    def join_identity_is_consistent(self) -> DecisionWorkspaceSnapshot:
        if (
            self.operational_decision.case_id != self.case_id
            or self.operational_decision.trace_id != self.trace_id
            or self.operational_decision.case_version != self.case_version
        ):
            raise ValueError("workspace decision identity does not match snapshot")
        if self.advisory is not None and (
            self.advisory.case_id != self.case_id
            or self.advisory.trace_id != self.trace_id
            or self.advisory.case_version != self.case_version
        ):
            raise ValueError("workspace advisory identity does not match snapshot")
        return self


_ADVISORY_TRANSITIONS: dict[AdvisoryStatus, frozenset[AdvisoryStatus]] = {
    AdvisoryStatus.NOT_REQUESTED: frozenset({AdvisoryStatus.RUNNING, AdvisoryStatus.UNAVAILABLE}),
    AdvisoryStatus.RUNNING: frozenset(
        {AdvisoryStatus.COMPLETE, AdvisoryStatus.PARTIAL, AdvisoryStatus.DEGRADED}
    ),
    AdvisoryStatus.COMPLETE: frozenset(),
    AdvisoryStatus.PARTIAL: frozenset(),
    AdvisoryStatus.DEGRADED: frozenset(),
    AdvisoryStatus.UNAVAILABLE: frozenset(),
}


def transition_advisory_status(previous: AdvisoryStatus, current: AdvisoryStatus) -> None:
    """Enforce the monotonic advisory state machine."""

    if current not in _ADVISORY_TRANSITIONS[previous]:
        raise ValueError(f"invalid advisory transition {previous.value} -> {current.value}")


def evidence_content_digest(item: EvidenceItem) -> str:
    """Match the detector's canonical digest for an admitted evidence record."""

    return hashlib.sha256(canonical_json(item.admitted_fields).encode("utf-8")).hexdigest()


def source_status_map(
    availability: Mapping[EvidenceSourceType, EvidenceReadStatus]
    | tuple[tuple[EvidenceSourceType, EvidenceReadStatus], ...]
    | None,
) -> dict[EvidenceSourceType, EvidenceReadStatus]:
    if availability is None:
        return {}
    if isinstance(availability, Mapping):
        return dict(availability)
    return dict(availability)


__all__ = [
    "ADVISORY_AUTHORITY_LABEL",
    "EvidenceClass",
    "EvidenceDisposition",
    "M4AcceptanceStatus",
    "M4PromotionStatus",
    "REQUIRED_AUTHORITY_ROLES",
    "SAFETY_AUTHORITY_LABEL",
    "USEFULNESS_AUTHORITY_LABEL",
    "ActionEligibility",
    "AdvisoryDissent",
    "AdvisoryHypothesis",
    "AdvisoryInvestigation",
    "AdvisoryKnowledgeCitation",
    "AdvisoryStatus",
    "AdvisoryUsage",
    "AIUsefulnessProof",
    "AttestationDecision",
    "AuthorizationIntent",
    "DecisionWorkspaceSnapshot",
    "OperationalClassification",
    "OperationalDecision",
    "OperationalEligibility",
    "OperationalInvariant",
    "ProofCheck",
    "ProofStatus",
    "QuorumActionGrant",
    "QuorumAttestation",
    "QuorumResult",
    "QuorumStatus",
    "SafetyProof",
    "canonical_json",
    "digest",
    "evidence_content_digest",
    "source_status_map",
    "transition_advisory_status",
]
