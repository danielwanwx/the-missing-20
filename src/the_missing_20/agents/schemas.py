"""Strict structured contracts emitted by the Milestone 4 agents.

The contracts intentionally contain conclusions and citations, never hidden reasoning.
They are separate from the existing business-ledger contracts so an agent response must
pass a deterministic adapter before it can influence a case transition.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType, UnionType
from typing import Annotated, Any, Literal, Union, get_args, get_origin

from pydantic import BaseModel, Field, field_validator, model_validator

from the_missing_20.domain.enterprise import EvidenceReadStatus
from the_missing_20.domain.models import (
    ConfidenceBand,
    ContractModel,
    EvaluationDecision,
    EvidenceItem,
    EvidenceSourceType,
    HypothesisConclusion,
    HypothesisType,
    InvestigationAssessment,
    NonEmptyStr,
)

AGENT_CONTRACT_VERSION = "agent-contract/v9"
ENVELOPE_VERSION = "agent-protocol-envelope/v1"
SYNTHESIS_PROTOCOL_VERSION = "synthesis-protocol/v1"
EVALUATOR_PROTOCOL_VERSION = "evaluator-protocol/v3"
EVALUATOR_VERSION = "evaluator-v4"
HARNESS_VERSION = "harness-v6"
TRACE_VERSION = "agent-trace/v2"
ARTIFACT_VERSION = "agent-run/v2"
ATTEMPT_CLAIM_SCHEMA_VERSION = "agent-attempt-claim/v1"
EVALUATOR_CITATION_CLOSURE_VERSION = "evaluator-citation-closure/v1"
EVALUATOR_SOURCE_COVERAGE_VERSION = "evaluator-source-coverage/v2"
SOURCE_COVERAGE_VERSION = EVALUATOR_SOURCE_COVERAGE_VERSION

# These are the authoritative records required before an actionable diagnosis can
# proceed.  Knowledge-base records are intentionally excluded: they explain a
# procedure, but they are not current-state evidence for a case.
REQUIRED_AUTHORITATIVE_SOURCES: tuple[EvidenceSourceType, ...] = (
    EvidenceSourceType.FAILED_MESSAGE_QUEUE,
    EvidenceSourceType.ERP_RECEIPT,
    EvidenceSourceType.MATERIAL_DOCUMENT,
    EvidenceSourceType.WAREHOUSE,
    EvidenceSourceType.INVOICE,
)


def _coerce_wire_value(annotation: Any, value: Any) -> Any:
    """Convert JSON wire values into strict contract values before validation.

    ``ContractModel`` deliberately uses strict Pydantic validation.  A model provider,
    however, returns JSON primitives (strings/lists/dicts) over the Strands tool
    boundary.  This small adapter keeps the contracts strict after the boundary while
    accepting only the canonical JSON representation of enums, tuples, and nested
    models.  Unknown fields are intentionally left untouched so ``extra='forbid'``
    remains authoritative.
    """

    if value is None or annotation is Any:
        return value
    origin = get_origin(annotation)
    if origin is Annotated:
        return _coerce_wire_value(get_args(annotation)[0], value)
    if origin in (Union, UnionType):
        if value is None:
            return None
        for candidate in get_args(annotation):
            if candidate is type(None):
                continue
            try:
                return _coerce_wire_value(candidate, value)
            except (TypeError, ValueError):
                continue
        return value
    if origin is tuple:
        args = get_args(annotation)
        if not isinstance(value, (list, tuple)):
            return value
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_coerce_wire_value(args[0], item) for item in value)
        return tuple(
            _coerce_wire_value(args[index], item) if index < len(args) else item
            for index, item in enumerate(value)
        )
    if origin is list:
        args = get_args(annotation)
        item_annotation = args[0] if args else Any
        if isinstance(value, list):
            return [_coerce_wire_value(item_annotation, item) for item in value]
        return value
    if origin is dict:
        args = get_args(annotation)
        key_annotation = args[0] if args else Any
        value_annotation = args[1] if len(args) > 1 else Any
        if isinstance(value, Mapping):
            return {
                _coerce_wire_value(key_annotation, key): _coerce_wire_value(value_annotation, item)
                for key, item in value.items()
            }
        return value
    if isinstance(annotation, type) and issubclass(annotation, StrEnum):
        if isinstance(value, annotation):
            return value
        if isinstance(value, str):
            return annotation(value)
        return value
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        if isinstance(value, annotation):
            return value
        if isinstance(value, Mapping):
            return annotation.model_validate(value)
    return value


class AgentContractModel(ContractModel):
    """Strict, frozen agent contract with a JSON-wire normalization seam."""

    @model_validator(mode="before")
    @classmethod
    def normalize_json_wire(cls, value: Any) -> Any:
        if not isinstance(value, Mapping):
            return value
        fields = cls.model_fields
        return {
            key: _coerce_wire_value(fields[key].annotation, item) if key in fields else item
            for key, item in value.items()
        }


class InvestigatorID(StrEnum):
    RETRYABLE_MESSAGE = "retryable_message_investigator"
    SHORT_SHIPMENT = "short_shipment_investigator"
    DUPLICATE_POSTING = "duplicate_posting_investigator"


# Model output may select only one of these hypotheses.  The corresponding
# investigator is fixed by the application; neither synthesis nor evaluation may
# substitute a different role for a selected hypothesis.
HYPOTHESIS_TO_INVESTIGATOR = MappingProxyType(
    {
        HypothesisType.RETRYABLE_MESSAGE: InvestigatorID.RETRYABLE_MESSAGE,
        HypothesisType.GENUINE_SHORT_SHIPMENT: InvestigatorID.SHORT_SHIPMENT,
        HypothesisType.ALREADY_POSTED: InvestigatorID.DUPLICATE_POSTING,
    }
)
INVESTIGATOR_TO_HYPOTHESIS = MappingProxyType(
    {investigator: hypothesis for hypothesis, investigator in HYPOTHESIS_TO_INVESTIGATOR.items()}
)


class KnowledgeUse(StrEnum):
    PROCEDURE_ONLY = "PROCEDURE_ONLY"
    ERROR_DEFINITION_ONLY = "ERROR_DEFINITION_ONLY"


class ClaimRelation(StrEnum):
    """The implication of one cited claim for its fixed hypothesis."""

    SUPPORTS_HYPOTHESIS = "SUPPORTS_HYPOTHESIS"
    CONTRADICTS_HYPOTHESIS = "CONTRADICTS_HYPOTHESIS"
    CONTEXT_ONLY = "CONTEXT_ONLY"


class AgentClaim(AgentContractModel):
    claim_id: NonEmptyStr
    statement: NonEmptyStr
    relation: ClaimRelation
    evidence_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def citations_are_unique(self) -> AgentClaim:
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("claim evidence IDs contain duplicates")
        return self


class KnowledgeCitation(AgentContractModel):
    """A public citation derived from an audited knowledge-tool result.

    This record is deliberately not a field on any model-authored structured
    output.  The harness creates it only after re-resolving the exact tool audit
    record against the frozen corpus.
    """

    knowledge_id: NonEmptyStr
    version: NonEmptyStr
    allowed_use: KnowledgeUse
    content_digest: NonEmptyStr


class SourceAvailability(AgentContractModel):
    """Deterministic availability asserted by the detector, not by a model."""

    source_type: EvidenceSourceType
    status: EvidenceReadStatus
    unavailability_reason: NonEmptyStr | None = None

    @model_validator(mode="after")
    def status_reason_is_consistent(self) -> SourceAvailability:
        if self.status is EvidenceReadStatus.AVAILABLE and self.unavailability_reason is not None:
            raise ValueError("available source cannot have an unavailability reason")
        if self.status is EvidenceReadStatus.UNAVAILABLE and self.unavailability_reason is None:
            raise ValueError("unavailable source requires an unavailability reason")
        return self


class SourceAvailabilitySet(AgentContractModel):
    """The fixed, exactly-once source status supplied to every agent stage."""

    sources: tuple[SourceAvailability, ...] = Field(
        min_length=len(REQUIRED_AUTHORITATIVE_SOURCES),
        max_length=len(REQUIRED_AUTHORITATIVE_SOURCES),
    )

    @model_validator(mode="after")
    def contains_every_required_source_once(self) -> SourceAvailabilitySet:
        observed = tuple(item.source_type for item in self.sources)
        required = set(REQUIRED_AUTHORITATIVE_SOURCES)
        if len(observed) != len(set(observed)):
            raise ValueError("source availability contains a duplicate source")
        if set(observed) != required:
            raise ValueError("source availability must contain every required source exactly once")
        return self

    @property
    def missing_evidence_sources(self) -> tuple[str, ...]:
        """Return the sorted authoritative source names unavailable to the harness."""

        return tuple(
            sorted(
                item.source_type.value
                for item in self.sources
                if item.status is EvidenceReadStatus.UNAVAILABLE
            )
        )

    def validate_against_evidence(self, admitted_evidence: tuple[EvidenceItem, ...]) -> None:
        """Ensure immutable source status agrees with the admitted evidence set."""

        for availability in self.sources:
            matches = tuple(
                item for item in admitted_evidence if item.source_type is availability.source_type
            )
            if availability.status is EvidenceReadStatus.AVAILABLE and len(matches) != 1:
                raise ValueError(
                    f"available source {availability.source_type.value} must match "
                    "one admitted evidence record"
                )
            if availability.status is EvidenceReadStatus.UNAVAILABLE and matches:
                raise ValueError(
                    f"unavailable source {availability.source_type.value} must not "
                    "have admitted evidence"
                )


class InvestigatorResult(AgentContractModel):
    investigator_id: InvestigatorID
    hypothesis_type: HypothesisType
    conclusion: HypothesisConclusion
    confidence_band: ConfidenceBand
    factual_claims: tuple[AgentClaim, ...] = Field(default=())

    @model_validator(mode="after")
    def claim_ids_are_unique(self) -> InvestigatorResult:
        claim_ids = tuple(claim.claim_id for claim in self.factual_claims)
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("investigator claim IDs contain duplicates")
        return self


class PreservedDissent(AgentContractModel):
    """Application-owned dissent projection for one fixed investigator."""

    investigator_id: InvestigatorID
    hypothesis_type: HypothesisType
    conclusion: HypothesisConclusion
    confidence_band: ConfidenceBand
    claim_ids_by_relation: dict[ClaimRelation, tuple[NonEmptyStr, ...]]

    @model_validator(mode="after")
    def relation_groups_are_complete(self) -> PreservedDissent:
        required = set(ClaimRelation)
        if set(self.claim_ids_by_relation) != required:
            raise ValueError("dissent must contain every claim relation exactly once")
        claim_ids = tuple(
            claim_id
            for relation in ClaimRelation
            for claim_id in self.claim_ids_by_relation[relation]
        )
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("dissent claim IDs contain duplicates")
        return self


class SynthesisResult(AgentContractModel):
    selected_hypothesis: HypothesisType
    conclusion: HypothesisConclusion
    confidence_band: ConfidenceBand
    factual_claims: tuple[AgentClaim, ...] = Field(default=())

    @model_validator(mode="after")
    def claim_ids_are_unique(self) -> SynthesisResult:
        claim_ids = tuple(claim.claim_id for claim in self.factual_claims)
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("synthesis claim IDs contain duplicates")
        return self


class AgentEvaluationResult(AgentContractModel):
    """Semantic evaluator output crossing the provider boundary in v9.

    Evidence citation closure is deliberately absent.  A model may decide which
    synthesis claims are semantically valid, but the harness resolves those claims
    against the immutable application records and owns every evidence projection.
    """

    decision: EvaluationDecision
    validated_claim_ids: tuple[NonEmptyStr, ...] = Field(default=())
    failed_invariants: tuple[NonEmptyStr, ...] = Field(default=())

    @model_validator(mode="after")
    def invariant_ids_are_unique(self) -> AgentEvaluationResult:
        if len(self.failed_invariants) != len(set(self.failed_invariants)):
            raise ValueError("evaluator failed invariants contain duplicates")
        return self


class AgentEvaluationResultV8(AgentContractModel):
    """Historical v8 evaluator contract retained for migration/audit tooling.

    New provider paths must use :class:`AgentEvaluationResult`; keeping this named
    class lets old manifests and offline migration tests be parsed without making the
    v9 provider schema permissive.
    """

    decision: EvaluationDecision
    validated_claim_ids: tuple[NonEmptyStr, ...] = Field(default=())
    validated_evidence_ids: tuple[NonEmptyStr, ...] = Field(default=())
    failed_invariants: tuple[NonEmptyStr, ...] = Field(default=())

    @model_validator(mode="after")
    def invariant_ids_are_unique(self) -> AgentEvaluationResultV8:
        if len(self.failed_invariants) != len(set(self.failed_invariants)):
            raise ValueError("evaluator failed invariants contain duplicates")
        return self


class EvaluatorCitation(AgentContractModel):
    """One harness-owned, relation-aware claim citation projection."""

    claim_id: NonEmptyStr
    relation: ClaimRelation
    evidence_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def citation_ids_are_stable_and_unique(self) -> EvaluatorCitation:
        if self.evidence_ids != tuple(sorted(self.evidence_ids)):
            raise ValueError("evaluator citation evidence IDs are not stably ordered")
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("evaluator citation evidence IDs contain duplicates")
        return self


class EvaluatorCitationClosure(AgentContractModel):
    """Immutable citation closure derived by the application harness.

    The closure is an audit record, not provider output.  ``validated_claim_ids``
    originates from the semantic evaluator, while every evidence ID and claim-to-
    evidence relationship is resolved from the validated synthesis and admitted
    catalog by deterministic application code.
    """

    schema_version: Literal["evaluator-citation-closure/v1"] = "evaluator-citation-closure/v1"
    case_id: NonEmptyStr
    trace_id: NonEmptyStr
    synthesis_claim_ids: tuple[NonEmptyStr, ...] = Field(default=())
    validated_claim_ids: tuple[NonEmptyStr, ...] = Field(default=())
    validated_evidence_ids: tuple[NonEmptyStr, ...] = Field(default=())
    claim_citations: tuple[EvaluatorCitation, ...] = Field(default=())
    all_synthesis_claims_validated: bool
    all_admitted_evidence_covered: bool
    identity_valid: bool
    integrity_valid: bool
    relation_valid: bool
    availability_valid: bool
    protocol_consistent: bool
    reason_code: NonEmptyStr

    @property
    def entries(self) -> tuple[EvaluatorCitation, ...]:
        """Compatibility alias for consumers that call entries a closure."""

        return self.claim_citations

    @property
    def evidence_ids(self) -> tuple[NonEmptyStr, ...]:
        """Short application-owned alias for the exact closure set."""

        return self.validated_evidence_ids

    @model_validator(mode="after")
    def closure_is_stable_and_self_consistent(self) -> EvaluatorCitationClosure:
        claim_ids = tuple(self.validated_claim_ids)
        if claim_ids != tuple(sorted(claim_ids)):
            raise ValueError("evaluator closure claim IDs are not stably ordered")
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("evaluator closure claim IDs contain duplicates")
        synthesis_claim_ids = tuple(self.synthesis_claim_ids)
        if synthesis_claim_ids != tuple(sorted(synthesis_claim_ids)):
            raise ValueError("evaluator closure synthesis claim IDs are not stably ordered")
        if len(synthesis_claim_ids) != len(set(synthesis_claim_ids)):
            raise ValueError("evaluator closure synthesis claim IDs contain duplicates")
        evidence_ids = tuple(self.validated_evidence_ids)
        if evidence_ids != tuple(sorted(evidence_ids)):
            raise ValueError("evaluator closure evidence IDs are not stably ordered")
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("evaluator closure evidence IDs contain duplicates")
        entries = tuple(self.claim_citations)
        entry_ids = tuple(entry.claim_id for entry in entries)
        if entry_ids != tuple(sorted(entry_ids)):
            raise ValueError("evaluator closure claim citations are not stably ordered")
        if len(entry_ids) != len(set(entry_ids)):
            raise ValueError("evaluator closure contains duplicate claim citations")
        if set(entry_ids) != set(claim_ids):
            raise ValueError("evaluator closure entries do not match validated claims")
        derived = tuple(sorted({eid for entry in entries for eid in entry.evidence_ids}))
        if derived != evidence_ids:
            raise ValueError("evaluator closure evidence IDs are not the citation union")
        expected_claims = set(claim_ids) == set(synthesis_claim_ids)
        if self.all_synthesis_claims_validated != expected_claims:
            raise ValueError("evaluator closure claim completeness is not deterministic")
        if not self.identity_valid and self.all_admitted_evidence_covered:
            raise ValueError("invalid identity cannot produce complete evidence closure")
        if not self.integrity_valid and self.all_admitted_evidence_covered:
            raise ValueError("invalid integrity cannot produce complete evidence closure")
        if not self.relation_valid and self.all_admitted_evidence_covered:
            raise ValueError("invalid relation cannot produce complete evidence closure")
        if not self.availability_valid and self.all_admitted_evidence_covered:
            raise ValueError("invalid availability cannot produce complete evidence closure")
        if not self.protocol_consistent and self.all_admitted_evidence_covered:
            raise ValueError("inconsistent protocol cannot produce complete evidence closure")
        return self


class EvaluatorSourceCoverage(AgentContractModel):
    """Harness-owned source coverage derived after semantic evaluator output.

    This record is intentionally not part of ``AgentEvaluationResult``.  It is built
    only from the detector-owned availability, admitted evidence catalog, and the
    harness-owned citation closure. Consequently a provider cannot claim a source is
    present, available, or covered by supplying a convenient aggregate field.
    """

    schema_version: Literal["evaluator-source-coverage/v2"] = "evaluator-source-coverage/v2"
    case_id: NonEmptyStr
    trace_id: NonEmptyStr
    validated_evidence_ids: tuple[NonEmptyStr, ...] = Field(default=())
    validated_source_types: tuple[EvidenceSourceType, ...] = Field(default=())
    source_availability: tuple[SourceAvailability, ...] = Field(
        min_length=len(REQUIRED_AUTHORITATIVE_SOURCES),
        max_length=len(REQUIRED_AUTHORITATIVE_SOURCES),
    )
    citation_closure: EvaluatorCitationClosure | None = None
    all_admitted_evidence_validated: bool
    all_required_sources_available: bool
    all_required_sources_validated: bool
    identity_valid: bool
    integrity_valid: bool
    protocol_consistent: bool
    reason_code: NonEmptyStr

    @model_validator(mode="before")
    @classmethod
    def normalize_availability_wire(cls, value: Any) -> Any:
        if not isinstance(value, Mapping):
            return value
        data = dict(value)
        raw = data.get("source_availability", data.get("availability"))
        if isinstance(raw, SourceAvailabilitySet):
            data["source_availability"] = raw.sources
        elif isinstance(raw, Mapping) and set(raw) == {"sources"}:
            data["source_availability"] = raw["sources"]
        if "availability" in data:
            data.pop("availability")
        return data

    @property
    def availability_entries(self) -> tuple[SourceAvailability, ...]:
        """Stable alias used by public projections and audit consumers."""

        return self.source_availability

    @property
    def source_types(self) -> tuple[EvidenceSourceType, ...]:
        """Short alias for the derived source projection."""

        return self.validated_source_types

    @property
    def closure(self) -> EvaluatorCitationClosure | None:
        """Short alias for the immutable citation closure projection."""

        return self.citation_closure

    @model_validator(mode="after")
    def exact_source_projection(self) -> EvaluatorSourceCoverage:
        observed_sources = tuple(item.source_type for item in self.source_availability)
        required = set(REQUIRED_AUTHORITATIVE_SOURCES)
        if len(observed_sources) != len(set(observed_sources)):
            raise ValueError("evaluator source coverage contains a duplicate source")
        if set(observed_sources) != required:
            raise ValueError(
                "evaluator source coverage must contain every required source exactly once"
            )
        if observed_sources != tuple(sorted(observed_sources, key=lambda source: source.value)):
            raise ValueError("evaluator source coverage availability is not stably ordered")
        evidence_ids = tuple(self.validated_evidence_ids)
        if evidence_ids != tuple(sorted(evidence_ids)):
            raise ValueError("evaluator source coverage evidence IDs are not stably ordered")
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("evaluator source coverage contains duplicate evidence IDs")
        if self.citation_closure is not None:
            if self.citation_closure.validated_evidence_ids != evidence_ids:
                raise ValueError("source coverage evidence IDs do not match citation closure")
            if self.citation_closure.case_id != self.case_id:
                raise ValueError("source coverage case does not match citation closure")
            if self.citation_closure.trace_id != self.trace_id:
                raise ValueError("source coverage trace does not match citation closure")
            if (
                self.all_admitted_evidence_validated
                != self.citation_closure.all_admitted_evidence_covered
            ):
                raise ValueError("source coverage completeness does not match citation closure")
            if self.identity_valid != self.citation_closure.identity_valid:
                raise ValueError("source coverage identity does not match citation closure")
            if self.integrity_valid != self.citation_closure.integrity_valid:
                raise ValueError("source coverage integrity does not match citation closure")
            if self.protocol_consistent != self.citation_closure.protocol_consistent:
                raise ValueError("source coverage protocol does not match citation closure")
        source_types = tuple(self.validated_source_types)
        if source_types != tuple(sorted(source_types, key=lambda source: source.value)):
            raise ValueError("evaluator source coverage source types are not stably ordered")
        if len(source_types) != len(set(source_types)):
            raise ValueError("evaluator source coverage contains duplicate source types")
        if any(source not in required for source in source_types):
            raise ValueError("evaluator source coverage contains a non-authoritative source")
        expected_available = all(
            item.status is EvidenceReadStatus.AVAILABLE for item in self.source_availability
        )
        if self.all_required_sources_available != expected_available:
            raise ValueError("evaluator source availability flag is not deterministically derived")
        expected_validated = (
            self.all_admitted_evidence_validated
            and self.all_required_sources_available
            and set(source_types) == required
            and self.identity_valid
            and self.integrity_valid
            and self.protocol_consistent
        )
        if self.all_required_sources_validated != expected_validated:
            raise ValueError("evaluator source validation flag is not deterministically derived")
        if not self.all_required_sources_available:
            expected_reason = "AUTHORITATIVE_SOURCE_UNAVAILABLE"
        elif not self.all_admitted_evidence_validated:
            expected_reason = "EVIDENCE_COVERAGE_INCOMPLETE"
        elif not self.identity_valid or not self.integrity_valid:
            expected_reason = "EVIDENCE_INTEGRITY_INVALID"
        elif not self.all_required_sources_validated:
            expected_reason = "AUTHORITATIVE_SOURCE_COVERAGE_INCOMPLETE"
        else:
            expected_reason = "ALL_REQUIRED_SOURCES_VALIDATED"
        if self.reason_code != expected_reason:
            raise ValueError("evaluator source coverage reason is not deterministically derived")
        return self


class AgentProtocolEnvelope(AgentContractModel):
    """Immutable application-owned metadata for one agent workflow invocation.

    This record is created by the harness after semantic model output has crossed the
    strict contract boundary.  It is never included in provider prompts and no model
    output can supply or mutate any of its values.
    """

    envelope_version: Literal["agent-protocol-envelope/v1"] = "agent-protocol-envelope/v1"
    agent_contract_version: Literal[
        "agent-contract/v9", "agent-contract/v8", "agent-contract/v7"
    ] = "agent-contract/v9"
    prompt_version: NonEmptyStr
    prompt_digest: NonEmptyStr
    schema_digest: NonEmptyStr
    synthesis_protocol_version: Literal["synthesis-protocol/v1"] = "synthesis-protocol/v1"
    evaluator_protocol_version: Literal["evaluator-protocol/v3"] = "evaluator-protocol/v3"
    evaluator_version: Literal["evaluator-v4"] = "evaluator-v4"
    harness_version: Literal["harness-v6"] = "harness-v6"
    evaluator_citation_closure_version: Literal["evaluator-citation-closure/v1"] = (
        "evaluator-citation-closure/v1"
    )
    evaluator_source_coverage_version: Literal["evaluator-source-coverage/v2"] = (
        "evaluator-source-coverage/v2"
    )
    coverage_ledger_version: Literal["coverage-ledger/v2"] = "coverage-ledger/v2"
    action_policy_version: Literal["action-policy/v2"] = "action-policy/v2"
    trace_version: Literal["agent-trace/v2"] = "agent-trace/v2"
    artifact_version: Literal["agent-run/v2"] = "agent-run/v2"
    knowledge_version: NonEmptyStr


def semantic_schema_digest() -> str:
    """Digest only the model-authored provider-visible semantic schemas."""

    payload = {
        "investigator": InvestigatorResult.model_json_schema(),
        "synthesis": SynthesisResult.model_json_schema(),
        "evaluator": AgentEvaluationResult.model_json_schema(),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def build_protocol_envelope(
    *,
    prompt_version: str,
    prompt_digest: str,
    knowledge_version: str,
) -> AgentProtocolEnvelope:
    """Stamp one immutable protocol envelope from harness-owned constants."""

    return AgentProtocolEnvelope(
        prompt_version=prompt_version,
        prompt_digest=prompt_digest,
        schema_digest=semantic_schema_digest(),
        knowledge_version=knowledge_version,
    )


def validate_protocol_envelope(
    envelope: AgentProtocolEnvelope,
    *,
    prompt_version: str | None = None,
    prompt_digest: str | None = None,
    knowledge_version: str | None = None,
) -> None:
    """Fail closed if a projection carries stale, missing, or tampered metadata."""

    if envelope.envelope_version != ENVELOPE_VERSION:
        raise ValueError("unsupported protocol envelope version")
    if envelope.agent_contract_version != AGENT_CONTRACT_VERSION:
        raise ValueError("unsupported agent contract version")
    if envelope.synthesis_protocol_version != SYNTHESIS_PROTOCOL_VERSION:
        raise ValueError("unsupported synthesis protocol version")
    if envelope.evaluator_protocol_version != EVALUATOR_PROTOCOL_VERSION:
        raise ValueError("unsupported evaluator protocol version")
    if envelope.evaluator_version != EVALUATOR_VERSION:
        raise ValueError("unsupported evaluator version")
    if envelope.harness_version != HARNESS_VERSION:
        raise ValueError("unsupported harness version")
    if envelope.evaluator_citation_closure_version != EVALUATOR_CITATION_CLOSURE_VERSION:
        raise ValueError("unsupported evaluator citation closure version")
    if envelope.evaluator_source_coverage_version != EVALUATOR_SOURCE_COVERAGE_VERSION:
        raise ValueError("unsupported evaluator source coverage version")
    if envelope.coverage_ledger_version != "coverage-ledger/v2":
        raise ValueError("unsupported coverage ledger version")
    if envelope.action_policy_version != "action-policy/v2":
        raise ValueError("unsupported action policy version")
    if envelope.trace_version != TRACE_VERSION:
        raise ValueError("unsupported trace version")
    if envelope.artifact_version != ARTIFACT_VERSION:
        raise ValueError("unsupported artifact version")
    if envelope.schema_digest != semantic_schema_digest():
        raise ValueError("protocol envelope schema digest mismatch")
    if prompt_version is not None and envelope.prompt_version != prompt_version:
        raise ValueError("protocol envelope prompt version mismatch")
    if prompt_digest is not None and envelope.prompt_digest != prompt_digest:
        raise ValueError("protocol envelope prompt digest mismatch")
    if knowledge_version is not None and envelope.knowledge_version != knowledge_version:
        raise ValueError("protocol envelope knowledge version mismatch")


def _derived_evidence_ids(
    result: InvestigatorResult | SynthesisResult,
    relation: ClaimRelation,
) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                evidence_id
                for claim in result.factual_claims
                if claim.relation is relation
                for evidence_id in claim.evidence_ids
            }
        )
    )


def _derived_claim_ids(
    result: InvestigatorResult | SynthesisResult,
    relation: ClaimRelation,
) -> tuple[str, ...]:
    return tuple(
        sorted(claim.claim_id for claim in result.factual_claims if claim.relation is relation)
    )


def derived_supporting_evidence_ids(
    result: InvestigatorResult | SynthesisResult,
) -> tuple[str, ...]:
    """Return the application-derived evidence projection for supporting claims."""

    return _derived_evidence_ids(result, ClaimRelation.SUPPORTS_HYPOTHESIS)


def derived_contradicting_evidence_ids(
    result: InvestigatorResult | SynthesisResult,
) -> tuple[str, ...]:
    """Return the application-derived evidence projection for contradicting claims."""

    return _derived_evidence_ids(result, ClaimRelation.CONTRADICTS_HYPOTHESIS)


def derived_context_evidence_ids(
    result: InvestigatorResult | SynthesisResult,
) -> tuple[str, ...]:
    """Return the application-derived evidence projection for context-only claims."""

    return _derived_evidence_ids(result, ClaimRelation.CONTEXT_ONLY)


def derived_evidence_ids_by_relation(
    result: InvestigatorResult | SynthesisResult,
) -> dict[ClaimRelation, tuple[str, ...]]:
    """Return deterministic evidence IDs grouped by claim relation."""

    return {relation: _derived_evidence_ids(result, relation) for relation in ClaimRelation}


def derived_claim_ids_by_relation(
    result: InvestigatorResult | SynthesisResult,
) -> dict[ClaimRelation, tuple[str, ...]]:
    """Return deterministic claim IDs grouped by claim relation."""

    return {relation: _derived_claim_ids(result, relation) for relation in ClaimRelation}


def derive_preserved_dissent(
    investigators: Iterable[InvestigatorResult],
) -> tuple[PreservedDissent, ...]:
    """Project every investigator's meaning without model-authored aggregation."""

    ordered = tuple(investigators)
    observed_ids = tuple(item.investigator_id for item in ordered)
    if len(observed_ids) != len(set(observed_ids)) or set(observed_ids) != set(
        HYPOTHESIS_TO_INVESTIGATOR.values()
    ):
        raise ValueError("dissent projection requires every fixed investigator exactly once")
    if any(
        HYPOTHESIS_TO_INVESTIGATOR.get(item.hypothesis_type) is not item.investigator_id
        for item in ordered
    ):
        raise ValueError("dissent projection contains a role and hypothesis mismatch")
    return tuple(
        PreservedDissent(
            investigator_id=item.investigator_id,
            hypothesis_type=item.hypothesis_type,
            conclusion=item.conclusion,
            confidence_band=item.confidence_band,
            claim_ids_by_relation=derived_claim_ids_by_relation(item),
        )
        for item in sorted(ordered, key=lambda value: value.investigator_id.value)
    )


def public_investigator_result(
    result: InvestigatorResult,
    *,
    missing_evidence_sources: Iterable[str] = (),
    knowledge_citations: Iterable[KnowledgeCitation] = (),
    read_evidence_ids: Iterable[str] = (),
    protocol: AgentProtocolEnvelope | None = None,
) -> dict[str, Any]:
    """Serialize a validated investigator with harness-derived fields."""

    payload = result.model_dump(mode="json")
    payload["supporting_evidence_ids"] = list(derived_supporting_evidence_ids(result))
    payload["contradicting_evidence_ids"] = list(derived_contradicting_evidence_ids(result))
    payload["context_evidence_ids"] = list(derived_context_evidence_ids(result))
    payload["claim_ids_by_relation"] = {
        relation.value: list(claim_ids)
        for relation, claim_ids in derived_claim_ids_by_relation(result).items()
    }
    payload["evidence_ids_by_relation"] = {
        relation.value: list(evidence_ids)
        for relation, evidence_ids in derived_evidence_ids_by_relation(result).items()
    }
    payload["missing_evidence_sources"] = list(sorted(missing_evidence_sources))
    payload["read_evidence_ids"] = list(sorted(set(read_evidence_ids)))
    payload["knowledge_citations"] = [
        item.model_dump(mode="json")
        for item in sorted(
            knowledge_citations,
            key=lambda item: (item.knowledge_id, item.version, item.allowed_use.value),
        )
    ]
    if protocol is not None:
        validate_protocol_envelope(protocol)
        payload["protocol"] = protocol.model_dump(mode="json")
    return payload


def public_synthesis_result(
    result: SynthesisResult,
    *,
    missing_evidence_sources: Iterable[str] = (),
    preserved_dissent: Iterable[PreservedDissent] = (),
    protocol: AgentProtocolEnvelope | None = None,
) -> dict[str, Any]:
    """Serialize a validated synthesis with harness-derived fields."""

    payload = result.model_dump(mode="json")
    payload["supporting_evidence_ids"] = list(derived_supporting_evidence_ids(result))
    payload["contradicting_evidence_ids"] = list(derived_contradicting_evidence_ids(result))
    payload["context_evidence_ids"] = list(derived_context_evidence_ids(result))
    payload["claim_ids_by_relation"] = {
        relation.value: list(claim_ids)
        for relation, claim_ids in derived_claim_ids_by_relation(result).items()
    }
    payload["evidence_ids_by_relation"] = {
        relation.value: list(evidence_ids)
        for relation, evidence_ids in derived_evidence_ids_by_relation(result).items()
    }
    payload["missing_evidence_sources"] = list(sorted(missing_evidence_sources))
    payload["preserved_dissent"] = [
        item.model_dump(mode="json")
        for item in sorted(preserved_dissent, key=lambda item: item.investigator_id.value)
    ]
    if protocol is not None:
        validate_protocol_envelope(protocol)
        payload["protocol"] = protocol.model_dump(mode="json")
    return payload


class AgentFailure(AgentContractModel):
    code: NonEmptyStr
    stage: NonEmptyStr
    message: NonEmptyStr
    retry_count: int = Field(ge=0, le=1)


class AgentProviderAttemptClaimV7(AgentContractModel):
    """Immutable, prose-free record consuming the one v7 provider attempt."""

    schema_version: Literal["agent-attempt-claim/v1"] = "agent-attempt-claim/v1"
    claim_id: NonEmptyStr
    state: Literal["CLAIMED"] = "CLAIMED"
    created_at: datetime
    agent_contract_version: Literal["agent-contract/v7"] = "agent-contract/v7"
    envelope_version: Literal["agent-protocol-envelope/v1"] = "agent-protocol-envelope/v1"
    prior_cost_usd: float = Field(ge=0)
    request_cap: int = Field(ge=0)
    input_token_cap: int = Field(ge=0)
    output_token_cap: int = Field(ge=0)
    max_output_tokens_per_request: int = Field(ge=0)
    incremental_cost_cap_usd: float = Field(ge=0)
    cumulative_cost_cap_usd: float = Field(ge=0)
    claim_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("created_at", mode="before")
    @classmethod
    def parse_wire_created_at(cls, value: object) -> object:
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value

    @model_validator(mode="after")
    def claim_is_self_consistent(self) -> AgentProviderAttemptClaimV7:
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("attempt claim created_at must be timezone-aware")
        payload = self.model_dump(mode="json")
        observed = payload.pop("claim_digest")
        canonical = (
            json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
        expected = hashlib.sha256(canonical).hexdigest()
        if observed != expected:
            raise ValueError("attempt claim digest mismatch")
        return self


class AgentProviderAttemptClaimV8(AgentContractModel):
    """Immutable, prose-free record consuming the exclusive v8 provider attempt."""

    schema_version: Literal["agent-attempt-claim/v1"] = "agent-attempt-claim/v1"
    claim_id: NonEmptyStr
    state: Literal["CLAIMED"] = "CLAIMED"
    created_at: datetime
    agent_contract_version: Literal["agent-contract/v8"] = "agent-contract/v8"
    envelope_version: Literal["agent-protocol-envelope/v1"] = "agent-protocol-envelope/v1"
    prior_cost_usd: float = Field(ge=0)
    request_cap: int = Field(ge=0)
    input_token_cap: int = Field(ge=0)
    output_token_cap: int = Field(ge=0)
    max_output_tokens_per_request: int = Field(ge=0)
    incremental_cost_cap_usd: float = Field(ge=0)
    cumulative_cost_cap_usd: float = Field(ge=0)
    claim_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("created_at", mode="before")
    @classmethod
    def parse_wire_created_at(cls, value: object) -> object:
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value

    @model_validator(mode="after")
    def claim_is_self_consistent(self) -> AgentProviderAttemptClaimV8:
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("attempt claim created_at must be timezone-aware")
        payload = self.model_dump(mode="json")
        observed = payload.pop("claim_digest")
        canonical = (
            json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
        ).encode("utf-8")
        expected = hashlib.sha256(canonical).hexdigest()
        if observed != expected:
            raise ValueError("attempt claim digest mismatch")
        return self


class AgentProviderAttemptClaimV9(AgentContractModel):
    """Immutable, prose-free record consuming the exclusive v9 provider attempt."""

    schema_version: Literal["agent-attempt-claim/v1"] = "agent-attempt-claim/v1"
    claim_id: NonEmptyStr
    state: Literal["CLAIMED"] = "CLAIMED"
    created_at: datetime
    agent_contract_version: Literal["agent-contract/v9"] = "agent-contract/v9"
    envelope_version: Literal["agent-protocol-envelope/v1"] = "agent-protocol-envelope/v1"
    prior_cost_usd: float = Field(ge=0)
    request_cap: int = Field(ge=0)
    input_token_cap: int = Field(ge=0)
    output_token_cap: int = Field(ge=0)
    max_output_tokens_per_request: int = Field(ge=0)
    incremental_cost_cap_usd: float = Field(ge=0)
    cumulative_cost_cap_usd: float = Field(ge=0)
    claim_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("created_at", mode="before")
    @classmethod
    def parse_wire_created_at(cls, value: object) -> object:
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value

    @model_validator(mode="after")
    def claim_is_self_consistent(self) -> AgentProviderAttemptClaimV9:
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("attempt claim created_at must be timezone-aware")
        payload = self.model_dump(mode="json")
        observed = payload.pop("claim_digest")
        canonical = (
            json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
        ).encode("utf-8")
        expected = hashlib.sha256(canonical).hexdigest()
        if observed != expected:
            raise ValueError("attempt claim digest mismatch")
        return self


# The unqualified claim name is the active v9 contract.  Historical v7/v8 callers
# use their explicit classes and retain their original schemas unchanged.
AgentProviderAttemptClaim = AgentProviderAttemptClaimV9


class AgentFailureManifestV8(AgentContractModel):
    """Redacted v8 diagnostics with the v8 harness-owned protocol envelope."""

    schema_version: str = Field(default="agent-failure/v4", pattern=r"^agent-failure/v4$")
    profile_key: NonEmptyStr
    assigned_stage: NonEmptyStr
    assigned_role: NonEmptyStr | None = None
    validator_code: NonEmptyStr
    provider: NonEmptyStr
    model: NonEmptyStr
    request_count: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    request_cap: int = Field(ge=0)
    input_token_cap: int = Field(ge=0)
    output_token_cap: int = Field(ge=0)
    estimated_cost_usd: float | None = Field(default=None, ge=0)
    incremental_cost_usd: float | None = Field(default=None, ge=0)
    cumulative_cost_usd: float | None = Field(default=None, ge=0)
    attempt_claim: AgentProviderAttemptClaimV8 | None = None
    protocol: AgentProtocolEnvelope | None = None
    envelope_version: str = Field(default=ENVELOPE_VERSION, pattern=r"^agent-protocol-envelope/v1$")
    agent_contract_version: str = Field(default="agent-contract/v8", pattern=r"^agent-contract/v8$")
    synthesis_protocol_version: str = Field(
        default=SYNTHESIS_PROTOCOL_VERSION, pattern=r"^synthesis-protocol/v1$"
    )
    evaluator_protocol_version: str = Field(
        default="evaluator-protocol/v2", pattern=r"^evaluator-protocol/v2$"
    )
    evaluator_source_coverage_version: str = Field(
        default=EVALUATOR_SOURCE_COVERAGE_VERSION,
        pattern=r"^evaluator-source-coverage/v1$",
    )
    prompt_version: str = "agent-v4"
    prompt_digest: str = "prompt-digest-unavailable"
    schema_digest: str = "schema-digest-unavailable"
    knowledge_version: str = "knowledge-v1"
    harness_version: str = Field(default="harness-v5", pattern=r"^harness-v5$")
    evaluator_version: str = Field(default=EVALUATOR_VERSION, pattern=r"^evaluator-v3$")
    coverage_ledger_version: str = Field(
        default="coverage-ledger/v2", pattern=r"^coverage-ledger/v2$"
    )
    action_policy_version: str = Field(default="action-policy/v2", pattern=r"^action-policy/v2$")
    trace_version: str = Field(default=TRACE_VERSION, pattern=r"^agent-trace/v2$")
    artifact_version: str = Field(default=ARTIFACT_VERSION, pattern=r"^agent-run/v2$")

    @model_validator(mode="after")
    def protocol_metadata_is_consistent(self) -> AgentFailureManifestV8:
        if self.protocol is not None:
            validate_protocol_envelope(self.protocol)
            fields = (
                ("envelope_version", self.envelope_version),
                ("agent_contract_version", self.agent_contract_version),
                ("synthesis_protocol_version", self.synthesis_protocol_version),
                ("evaluator_protocol_version", self.evaluator_protocol_version),
                ("evaluator_source_coverage_version", self.evaluator_source_coverage_version),
                ("prompt_version", self.prompt_version),
                ("prompt_digest", self.prompt_digest),
                ("schema_digest", self.schema_digest),
                ("knowledge_version", self.knowledge_version),
                ("harness_version", self.harness_version),
                ("evaluator_version", self.evaluator_version),
                ("coverage_ledger_version", self.coverage_ledger_version),
                ("action_policy_version", self.action_policy_version),
                ("trace_version", self.trace_version),
                ("artifact_version", self.artifact_version),
            )
            for name, value in fields:
                if getattr(self.protocol, name) != value:
                    raise ValueError(f"failure manifest {name} mismatch")
        return self


class AgentFailureManifestV7(AgentContractModel):
    """Redacted diagnostic written when a real-provider profile fails.

    This contract intentionally has no provider message, prompt, model output, or raw
    tool content.  It is safe to retain alongside the non-promotable smoke artifact.
    """

    schema_version: str = Field(default="agent-failure/v3", pattern=r"^agent-failure/v3$")
    profile_key: NonEmptyStr
    assigned_stage: NonEmptyStr
    assigned_role: NonEmptyStr | None = None
    validator_code: NonEmptyStr
    provider: NonEmptyStr
    model: NonEmptyStr
    request_count: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    request_cap: int = Field(ge=0)
    input_token_cap: int = Field(ge=0)
    output_token_cap: int = Field(ge=0)
    estimated_cost_usd: float | None = Field(default=None, ge=0)
    incremental_cost_usd: float | None = Field(default=None, ge=0)
    cumulative_cost_usd: float | None = Field(default=None, ge=0)
    attempt_claim: AgentProviderAttemptClaim | None = None
    protocol: AgentProtocolEnvelope | None = None
    envelope_version: str = Field(default=ENVELOPE_VERSION, pattern=r"^agent-protocol-envelope/v1$")
    agent_contract_version: str = Field(
        default="agent-contract/v7",
        pattern=r"^agent-contract/v7$",
    )
    synthesis_protocol_version: str = Field(
        default=SYNTHESIS_PROTOCOL_VERSION,
        pattern=r"^synthesis-protocol/v1$",
    )
    evaluator_protocol_version: str = Field(
        default="evaluator-protocol/v1",
        pattern=r"^evaluator-protocol/v1$",
    )
    prompt_version: str = "agent-v3"
    prompt_digest: str = "prompt-digest-unavailable"
    schema_digest: str = "schema-digest-unavailable"
    knowledge_version: str = "knowledge-v1"
    harness_version: str = Field(default="harness-v4", pattern=r"^harness-v4$")
    evaluator_version: str = Field(default="evaluator-v3", pattern=r"^evaluator-v3$")
    coverage_ledger_version: str = Field(
        default="coverage-ledger/v2",
        pattern=r"^coverage-ledger/v2$",
    )
    action_policy_version: str = Field(
        default="action-policy/v2",
        pattern=r"^action-policy/v2$",
    )
    trace_version: str = Field(default=TRACE_VERSION, pattern=r"^agent-trace/v2$")
    artifact_version: str = Field(default=ARTIFACT_VERSION, pattern=r"^agent-run/v2$")

    @model_validator(mode="after")
    def protocol_metadata_is_consistent(self) -> AgentFailureManifestV7:
        if self.protocol is not None:
            validate_protocol_envelope(self.protocol)
            if self.protocol.envelope_version != self.envelope_version:
                raise ValueError("failure manifest envelope version mismatch")
            if self.protocol.agent_contract_version != self.agent_contract_version:
                raise ValueError("failure manifest contract version mismatch")
            if self.protocol.synthesis_protocol_version != self.synthesis_protocol_version:
                raise ValueError("failure manifest synthesis protocol mismatch")
            if self.protocol.evaluator_protocol_version != self.evaluator_protocol_version:
                raise ValueError("failure manifest evaluator protocol mismatch")
            if self.protocol.prompt_version != self.prompt_version:
                raise ValueError("failure manifest prompt version mismatch")
            if self.protocol.prompt_digest != self.prompt_digest:
                raise ValueError("failure manifest prompt digest mismatch")
            if self.protocol.schema_digest != self.schema_digest:
                raise ValueError("failure manifest schema digest mismatch")
            if self.protocol.knowledge_version != self.knowledge_version:
                raise ValueError("failure manifest knowledge version mismatch")
            if self.protocol.harness_version != self.harness_version:
                raise ValueError("failure manifest harness version mismatch")
            if self.protocol.evaluator_version != self.evaluator_version:
                raise ValueError("failure manifest evaluator version mismatch")
            if self.protocol.coverage_ledger_version != self.coverage_ledger_version:
                raise ValueError("failure manifest coverage ledger version mismatch")
            if self.protocol.action_policy_version != self.action_policy_version:
                raise ValueError("failure manifest action policy version mismatch")
            if self.protocol.trace_version != self.trace_version:
                raise ValueError("failure manifest trace version mismatch")
            if self.protocol.artifact_version != self.artifact_version:
                raise ValueError("failure manifest artifact version mismatch")
        return self


class AgentFailureManifestV9(AgentContractModel):
    """Redacted v9 diagnostics with citation-closure protocol metadata."""

    schema_version: str = Field(default="agent-failure/v5", pattern=r"^agent-failure/v5$")
    profile_key: NonEmptyStr
    assigned_stage: NonEmptyStr
    assigned_role: NonEmptyStr | None = None
    validator_code: NonEmptyStr
    provider: NonEmptyStr
    model: NonEmptyStr
    request_count: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    request_cap: int = Field(ge=0)
    input_token_cap: int = Field(ge=0)
    output_token_cap: int = Field(ge=0)
    estimated_cost_usd: float | None = Field(default=None, ge=0)
    incremental_cost_usd: float | None = Field(default=None, ge=0)
    cumulative_cost_usd: float | None = Field(default=None, ge=0)
    attempt_claim: AgentProviderAttemptClaimV9 | None = None
    protocol: AgentProtocolEnvelope | None = None
    envelope_version: str = Field(default=ENVELOPE_VERSION, pattern=r"^agent-protocol-envelope/v1$")
    agent_contract_version: str = Field(default="agent-contract/v9", pattern=r"^agent-contract/v9$")
    synthesis_protocol_version: str = Field(
        default=SYNTHESIS_PROTOCOL_VERSION, pattern=r"^synthesis-protocol/v1$"
    )
    evaluator_protocol_version: str = Field(
        default="evaluator-protocol/v3", pattern=r"^evaluator-protocol/v3$"
    )
    evaluator_version: str = Field(default=EVALUATOR_VERSION, pattern=r"^evaluator-v4$")
    evaluator_citation_closure_version: str = Field(
        default=EVALUATOR_CITATION_CLOSURE_VERSION,
        pattern=r"^evaluator-citation-closure/v1$",
    )
    evaluator_source_coverage_version: str = Field(
        default=EVALUATOR_SOURCE_COVERAGE_VERSION,
        pattern=r"^evaluator-source-coverage/v2$",
    )
    prompt_version: str = "agent-v5"
    prompt_digest: str = "prompt-digest-unavailable"
    schema_digest: str = "schema-digest-unavailable"
    knowledge_version: str = "knowledge-v1"
    harness_version: str = Field(default="harness-v6", pattern=r"^harness-v6$")
    coverage_ledger_version: str = Field(
        default="coverage-ledger/v2", pattern=r"^coverage-ledger/v2$"
    )
    action_policy_version: str = Field(default="action-policy/v2", pattern=r"^action-policy/v2$")
    trace_version: str = Field(default=TRACE_VERSION, pattern=r"^agent-trace/v2$")
    artifact_version: str = Field(default=ARTIFACT_VERSION, pattern=r"^agent-run/v2$")

    @model_validator(mode="after")
    def protocol_metadata_is_consistent(self) -> AgentFailureManifestV9:
        if self.protocol is not None:
            validate_protocol_envelope(self.protocol)
            fields = (
                ("envelope_version", self.envelope_version),
                ("agent_contract_version", self.agent_contract_version),
                ("synthesis_protocol_version", self.synthesis_protocol_version),
                ("evaluator_protocol_version", self.evaluator_protocol_version),
                ("evaluator_version", self.evaluator_version),
                ("evaluator_citation_closure_version", self.evaluator_citation_closure_version),
                ("evaluator_source_coverage_version", self.evaluator_source_coverage_version),
                ("prompt_version", self.prompt_version),
                ("prompt_digest", self.prompt_digest),
                ("schema_digest", self.schema_digest),
                ("knowledge_version", self.knowledge_version),
                ("harness_version", self.harness_version),
                ("coverage_ledger_version", self.coverage_ledger_version),
                ("action_policy_version", self.action_policy_version),
                ("trace_version", self.trace_version),
                ("artifact_version", self.artifact_version),
            )
            for name, value in fields:
                if getattr(self.protocol, name) != value:
                    raise ValueError(f"failure manifest {name} mismatch")
        if (
            self.attempt_claim is not None
            and self.attempt_claim.agent_contract_version != self.agent_contract_version
        ):
            raise ValueError("failure manifest attempt claim contract mismatch")
        return self


# Keep the historical v7 class addressable while making the unqualified manifest
# name refer to the active v9 contract for new callers.
AgentFailureManifest = AgentFailureManifestV9


class AgentStageTrace(AgentContractModel):
    stage: NonEmptyStr
    outcome: NonEmptyStr
    tool_calls: tuple[NonEmptyStr, ...] = Field(default=())
    tool_call_details: tuple[dict[str, Any], ...] = Field(default=())
    read_evidence_ids: tuple[NonEmptyStr, ...] = Field(default=())
    knowledge_citations: tuple[KnowledgeCitation, ...] = Field(default=())
    request_count: int = Field(default=0, ge=0)
    retry_count: int = Field(ge=0, le=1)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    latency_ms: int = Field(ge=0)
    evaluator_citation_closure: EvaluatorCitationClosure | None = None
    evaluator_source_coverage: EvaluatorSourceCoverage | None = None
    protocol: AgentProtocolEnvelope | None = None

    @property
    def source_coverage(self) -> EvaluatorSourceCoverage | None:
        return self.evaluator_source_coverage

    @property
    def citation_closure(self) -> EvaluatorCitationClosure | None:
        return self.evaluator_citation_closure


class AgentRunManifest(AgentContractModel):
    """Portable trace envelope used by Golden v2 and smoke artifacts."""

    schema_version: str = Field(pattern=r"^agent-run/v2$")
    run_id: NonEmptyStr
    case_id: NonEmptyStr
    trace_id: NonEmptyStr
    provider: NonEmptyStr
    model: NonEmptyStr
    prompt_version: NonEmptyStr
    schema_digest: NonEmptyStr
    knowledge_version: NonEmptyStr
    harness_version: NonEmptyStr
    evaluator_version: NonEmptyStr
    prompt_digest: NonEmptyStr = "prompt-digest-unavailable"
    agent_contract_version: str = Field(
        default=AGENT_CONTRACT_VERSION,
        pattern=r"^agent-contract/v9$",
    )
    protocol: AgentProtocolEnvelope | None = None
    evaluator_citation_closure: EvaluatorCitationClosure | None = None
    evaluator_source_coverage: EvaluatorSourceCoverage | None = None
    stages: tuple[AgentStageTrace, ...] = Field(default=())
    stop_reason: NonEmptyStr
    assessment: InvestigationAssessment | None = None
    failure: AgentFailure | None = None

    @model_validator(mode="after")
    def assessment_or_failure(self) -> AgentRunManifest:
        if (self.assessment is None) == (self.failure is None):
            raise ValueError("agent run must contain exactly one assessment or failure")
        if self.protocol is not None:
            validate_protocol_envelope(
                self.protocol,
                prompt_version=self.prompt_version,
                prompt_digest=self.prompt_digest,
                knowledge_version=self.knowledge_version,
            )
            if self.protocol.agent_contract_version != self.agent_contract_version:
                raise ValueError("agent run contract version mismatch")
            if self.protocol.prompt_version != self.prompt_version:
                raise ValueError("agent run prompt version mismatch")
            if self.protocol.prompt_digest != self.prompt_digest:
                raise ValueError("agent run prompt digest mismatch")
            if self.protocol.knowledge_version != self.knowledge_version:
                raise ValueError("agent run knowledge version mismatch")
            if self.protocol.harness_version != self.harness_version:
                raise ValueError("agent run harness version mismatch")
            if self.protocol.evaluator_version != self.evaluator_version:
                raise ValueError("agent run evaluator version mismatch")
            if (
                self.evaluator_citation_closure is not None
                and self.protocol.evaluator_citation_closure_version
                != self.evaluator_citation_closure.schema_version
            ):
                raise ValueError("agent run citation closure version mismatch")
            if (
                self.evaluator_source_coverage is not None
                and self.protocol.evaluator_source_coverage_version
                != self.evaluator_source_coverage.schema_version
            ):
                raise ValueError("agent run source coverage version mismatch")
        return self
