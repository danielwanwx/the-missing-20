"""Deterministic validation and adaptation of agent responses."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from datetime import datetime

from the_missing_20.agents.policy import ActionRecommendation
from the_missing_20.agents.schemas import (
    HYPOTHESIS_TO_INVESTIGATOR,
    REQUIRED_AUTHORITATIVE_SOURCES,
    AgentEvaluationResult,
    AgentProtocolEnvelope,
    ClaimRelation,
    EvaluatorCitation,
    EvaluatorCitationClosure,
    EvaluatorSourceCoverage,
    InvestigatorResult,
    SourceAvailability,
    SourceAvailabilitySet,
    SynthesisResult,
    derived_contradicting_evidence_ids,
    derived_supporting_evidence_ids,
    validate_protocol_envelope,
)
from the_missing_20.domain.assessment import validate_investigation_assessment
from the_missing_20.domain.enterprise import EvidenceReadStatus
from the_missing_20.domain.errors import InvalidEventPayload
from the_missing_20.domain.models import (
    EvaluationDecision,
    EvaluationResult,
    EvidenceItem,
    EvidenceSourceType,
    HypothesisConclusion,
    HypothesisResult,
    HypothesisType,
    InvestigationAssessment,
    InvestigationDecision,
)
from the_missing_20.ports.knowledge import KnowledgeRepository


class AgentValidationError(ValueError):
    """A structured response cannot cross the deterministic harness boundary."""


class AgentStageFailure(AgentValidationError):
    """A bounded stage failed with redacted, machine-readable context."""

    def __init__(
        self,
        message: str,
        *,
        stage: str,
        role: str | None = None,
        validator_code: str = "AGENT_VALIDATION_ERROR",
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.role = role
        self.validator_code = validator_code


def stable_agent_error_code(error: BaseException) -> str:
    """Return a deterministic, prose-free code for a stage failure manifest."""

    if isinstance(error, AgentStageFailure):
        return error.validator_code
    if isinstance(error, AgentValidationError):
        return "AGENT_VALIDATION_ERROR"
    name = type(error).__name__
    # Keep codes portable across provider SDK versions without retaining exception
    # messages, which may contain model prose, evidence, or local paths.
    code = re.sub(r"(?<!^)(?=[A-Z])", "_", name).upper()
    return code or "UNKNOWN_ERROR"


def _unique(values: Iterable[str]) -> bool:
    values_tuple = tuple(values)
    return len(values_tuple) == len(set(values_tuple))


def _validated_evidence_catalog(
    *,
    evidence: tuple[EvidenceItem, ...],
    source_availability: SourceAvailabilitySet,
    case_id: str | None,
    trace_id: str | None,
) -> tuple[str, str, dict[str, EvidenceItem], tuple[SourceAvailability, ...]]:
    """Validate and index the immutable detector-owned evidence catalog."""

    if not evidence:
        raise AgentValidationError("citation closure requires admitted evidence")
    expected_case_id = case_id or evidence[0].case_id
    expected_trace_id = trace_id or evidence[0].trace_id
    if not expected_case_id.strip() or not expected_trace_id.strip():
        raise AgentValidationError("citation closure requires case and trace identity")
    if any(item.source_type not in REQUIRED_AUTHORITATIVE_SOURCES for item in evidence):
        raise AgentValidationError("knowledge-only evidence cannot provide authoritative coverage")
    try:
        source_availability.validate_against_evidence(evidence)
    except ValueError as exc:
        raise AgentValidationError(str(exc)) from exc
    by_id: dict[str, EvidenceItem] = {}
    by_source: dict[EvidenceSourceType, EvidenceItem] = {}
    for item in evidence:
        if item.case_id != expected_case_id or item.trace_id != expected_trace_id:
            raise AgentValidationError("admitted evidence context does not match invocation")
        if item.evidence_id in by_id:
            raise AgentValidationError("admitted evidence contains duplicate IDs")
        if item.source_type in by_source:
            raise AgentValidationError("admitted evidence contains duplicate source records")
        encoded = json.dumps(
            item.admitted_fields,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        if hashlib.sha256(encoded.encode()).hexdigest() != item.content_digest:
            raise AgentValidationError("admitted evidence content digest changed")
        if not item.source_record_id.strip():
            raise AgentValidationError("admitted evidence source identity is missing")
        by_id[item.evidence_id] = item
        by_source[item.source_type] = item
    return (
        expected_case_id,
        expected_trace_id,
        by_id,
        tuple(sorted(source_availability.sources, key=lambda item: item.source_type.value)),
    )


def build_evaluator_citation_closure(
    *,
    evidence: tuple[EvidenceItem, ...],
    synthesis: SynthesisResult,
    validated_claim_ids: Iterable[str],
    source_availability: SourceAvailabilitySet,
    case_id: str | None = None,
    trace_id: str | None = None,
    protocol: AgentProtocolEnvelope | None = None,
) -> EvaluatorCitationClosure:
    """Derive exact, relation-aware citations from semantic claim IDs.

    The provider can select claim IDs only.  This function resolves those IDs against
    the validated synthesis and admitted evidence catalog, and computes every evidence
    projection.  It intentionally permits an incomplete closure for REJECT/
    MORE_EVIDENCE records so the reason remains auditable, while malformed or
    tampered records fail closed before a closure is persisted.
    """

    expected_case_id, expected_trace_id, by_id, availability = _validated_evidence_catalog(
        evidence=evidence,
        source_availability=source_availability,
        case_id=case_id,
        trace_id=trace_id,
    )
    if protocol is not None:
        try:
            validate_protocol_envelope(protocol)
        except ValueError as exc:
            raise AgentValidationError(str(exc)) from exc

    synthesis_claims = tuple(synthesis.factual_claims)
    synthesis_claim_ids = tuple(sorted(claim.claim_id for claim in synthesis_claims))
    by_claim = {claim.claim_id: claim for claim in synthesis_claims}
    selected_ids = tuple(validated_claim_ids)
    if not _unique(selected_ids):
        raise AgentValidationError("evaluator validated claim IDs contain duplicates")
    if any(not isinstance(item, str) or not item.strip() for item in selected_ids):
        raise AgentValidationError("evaluator validated claim IDs are malformed")
    if not set(selected_ids).issubset(by_claim):
        raise AgentValidationError("evaluator validated an unknown synthesis claim")

    availability_by_source = {item.source_type: item for item in availability}
    supporting_ids = {
        evidence_id
        for claim in synthesis_claims
        if claim.relation is ClaimRelation.SUPPORTS_HYPOTHESIS
        for evidence_id in claim.evidence_ids
    }
    contradicting_ids = {
        evidence_id
        for claim in synthesis_claims
        if claim.relation is ClaimRelation.CONTRADICTS_HYPOTHESIS
        for evidence_id in claim.evidence_ids
    }
    relation_valid = not supporting_ids.intersection(contradicting_ids)
    availability_valid = all(item.status is EvidenceReadStatus.AVAILABLE for item in availability)
    citations: list[EvaluatorCitation] = []
    for claim_id in sorted(selected_ids):
        claim = by_claim[claim_id]
        # AgentClaim's own validator rejects duplicate/empty citations.  Retain the
        # explicit checks here because this is the trust boundary for persisted data.
        if not claim.evidence_ids or not _unique(claim.evidence_ids):
            raise AgentValidationError(f"claim {claim_id} has invalid evidence citations")
        citation_ids: list[str] = []
        for evidence_id in claim.evidence_ids:
            item = by_id.get(evidence_id)
            if item is None:
                raise AgentValidationError(
                    f"claim {claim_id} cites an unadmitted or stale evidence ID"
                )
            if item.source_type not in REQUIRED_AUTHORITATIVE_SOURCES:
                raise AgentValidationError("knowledge-only evidence cannot close a citation")
            source_status = availability_by_source[item.source_type].status
            if source_status is not EvidenceReadStatus.AVAILABLE:
                availability_valid = False
            citation_ids.append(evidence_id)
        if claim.relation not in set(ClaimRelation):
            relation_valid = False
        citations.append(
            EvaluatorCitation(
                claim_id=claim.claim_id,
                relation=claim.relation,
                evidence_ids=tuple(sorted(citation_ids)),
            )
        )

    citations_tuple = tuple(sorted(citations, key=lambda item: item.claim_id))
    closure_ids = tuple(sorted({eid for item in citations_tuple for eid in item.evidence_ids}))
    all_claims = set(selected_ids) == set(synthesis_claim_ids)
    all_admitted = set(closure_ids) == set(by_id)
    identity_valid = all(
        item.case_id == expected_case_id
        and item.trace_id == expected_trace_id
        and bool(item.evidence_id.strip())
        and bool(item.source_record_id.strip())
        for item in evidence
    )
    integrity_valid = all(
        hashlib.sha256(
            json.dumps(
                item.admitted_fields,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode()
        ).hexdigest()
        == item.content_digest
        for item in evidence
    )
    protocol_consistent = True
    if not availability_valid:
        reason_code = "AUTHORITATIVE_SOURCE_UNAVAILABLE"
    elif not all_claims:
        reason_code = "SYNTHESIS_CLAIM_COVERAGE_INCOMPLETE"
    elif not all_admitted:
        reason_code = "EVIDENCE_CITATION_CLOSURE_INCOMPLETE"
    elif not relation_valid:
        reason_code = "CLAIM_RELATION_INVALID"
    elif not identity_valid or not integrity_valid:
        reason_code = "EVIDENCE_INTEGRITY_INVALID"
    elif not protocol_consistent:
        reason_code = "PROTOCOL_INCONSISTENT"
    else:
        reason_code = "CITATION_CLOSURE_COMPLETE"
    try:
        return EvaluatorCitationClosure(
            case_id=expected_case_id,
            trace_id=expected_trace_id,
            synthesis_claim_ids=synthesis_claim_ids,
            validated_claim_ids=tuple(sorted(selected_ids)),
            validated_evidence_ids=closure_ids,
            claim_citations=citations_tuple,
            all_synthesis_claims_validated=all_claims,
            all_admitted_evidence_covered=all_admitted,
            identity_valid=identity_valid,
            integrity_valid=integrity_valid,
            relation_valid=relation_valid,
            availability_valid=availability_valid,
            protocol_consistent=protocol_consistent,
            reason_code=reason_code,
        )
    except ValueError as exc:
        raise AgentValidationError(str(exc)) from exc


def build_evaluator_source_coverage(
    *,
    evidence: tuple[EvidenceItem, ...],
    source_availability: SourceAvailabilitySet,
    citation_closure: EvaluatorCitationClosure | None = None,
    validated_evidence_ids: Iterable[str] | None = None,
    case_id: str | None = None,
    trace_id: str | None = None,
    protocol: AgentProtocolEnvelope | None = None,
) -> EvaluatorSourceCoverage:
    """Derive v2 source coverage from an application-owned citation closure.

    ``validated_evidence_ids`` remains an optional migration seam for historical v8
    callers.  The active v9 harness always supplies ``citation_closure``; when both
    are supplied they must agree byte-for-byte on the projected IDs.
    """

    expected_case_id, expected_trace_id, by_id, availability = _validated_evidence_catalog(
        evidence=evidence,
        source_availability=source_availability,
        case_id=case_id,
        trace_id=trace_id,
    )
    if citation_closure is not None:
        if (
            citation_closure.case_id != expected_case_id
            or citation_closure.trace_id != expected_trace_id
        ):
            raise AgentValidationError("citation closure identity does not match invocation")
        projected_ids = citation_closure.validated_evidence_ids
        if (
            validated_evidence_ids is not None
            and tuple(sorted(validated_evidence_ids)) != projected_ids
        ):
            raise AgentValidationError("source coverage IDs do not match citation closure")
    elif validated_evidence_ids is not None:
        projected_ids = tuple(validated_evidence_ids)
    else:
        raise AgentValidationError("source coverage requires an application-owned citation closure")
    if not _unique(projected_ids):
        raise AgentValidationError("source coverage evidence IDs contain duplicates")
    if any(not isinstance(item, str) or not item.strip() for item in projected_ids):
        raise AgentValidationError("source coverage evidence IDs are malformed")
    if not set(projected_ids).issubset(by_id):
        raise AgentValidationError("source coverage contains an unknown or stale evidence ID")

    validated_items = tuple(by_id[item] for item in projected_ids)
    validated_source_types = tuple(
        sorted({item.source_type for item in validated_items}, key=lambda source: source.value)
    )
    all_admitted = set(projected_ids) == set(by_id)
    all_available = all(item.status is EvidenceReadStatus.AVAILABLE for item in availability)
    identity_valid = all(
        item.case_id == expected_case_id
        and item.trace_id == expected_trace_id
        and bool(item.evidence_id.strip())
        and bool(item.source_record_id.strip())
        for item in evidence
    )
    integrity_valid = all(
        hashlib.sha256(
            json.dumps(
                item.admitted_fields,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode()
        ).hexdigest()
        == item.content_digest
        for item in evidence
    )
    protocol_consistent = True
    if protocol is not None:
        try:
            validate_protocol_envelope(protocol)
        except ValueError as exc:
            raise AgentValidationError(str(exc)) from exc
    closure_valid = citation_closure is None or (
        citation_closure.all_synthesis_claims_validated
        and citation_closure.relation_valid
        and citation_closure.availability_valid
        and citation_closure.protocol_consistent
    )
    all_sources_validated = (
        all_admitted
        and all_available
        and set(validated_source_types) == set(REQUIRED_AUTHORITATIVE_SOURCES)
        and identity_valid
        and integrity_valid
        and protocol_consistent
        and closure_valid
    )
    if not all_available:
        reason_code = "AUTHORITATIVE_SOURCE_UNAVAILABLE"
    elif not all_admitted:
        reason_code = "EVIDENCE_COVERAGE_INCOMPLETE"
    elif not identity_valid or not integrity_valid:
        reason_code = "EVIDENCE_INTEGRITY_INVALID"
    elif not all_sources_validated:
        reason_code = "AUTHORITATIVE_SOURCE_COVERAGE_INCOMPLETE"
    else:
        reason_code = "ALL_REQUIRED_SOURCES_VALIDATED"
    try:
        return EvaluatorSourceCoverage(
            case_id=expected_case_id,
            trace_id=expected_trace_id,
            validated_evidence_ids=tuple(sorted(projected_ids)),
            validated_source_types=validated_source_types,
            source_availability=availability,
            citation_closure=citation_closure,
            all_admitted_evidence_validated=all_admitted,
            all_required_sources_available=all_available,
            all_required_sources_validated=all_sources_validated,
            identity_valid=identity_valid,
            integrity_valid=integrity_valid,
            protocol_consistent=protocol_consistent,
            reason_code=reason_code,
        )
    except ValueError as exc:
        raise AgentValidationError(str(exc)) from exc


# Compatibility spellings for callers that use the verbs from prior design documents.
derive_evaluator_citation_closure = build_evaluator_citation_closure
derive_evaluator_source_coverage = build_evaluator_source_coverage
derive_source_coverage = build_evaluator_source_coverage


class AgentEvidenceValidator:
    """Fail-closed checks over typed, normalized agent outputs."""

    def __init__(
        self,
        admitted_evidence: tuple[EvidenceItem, ...],
        *,
        trace_id: str,
        source_availability: SourceAvailabilitySet,
        knowledge: KnowledgeRepository | None = None,
    ) -> None:
        self.admitted = admitted_evidence
        self.trace_id = trace_id
        self.evidence_ids = frozenset(item.evidence_id for item in admitted_evidence)
        self.source_by_id = {item.evidence_id: item.source_type.value for item in admitted_evidence}
        try:
            source_availability.validate_against_evidence(admitted_evidence)
        except ValueError as exc:
            raise AgentValidationError(str(exc)) from exc
        self.source_availability = source_availability
        self.knowledge = knowledge

    @staticmethod
    def _evidence_digest(item: EvidenceItem) -> str:
        encoded = json.dumps(
            item.admitted_fields,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        return hashlib.sha256(encoded.encode()).hexdigest()

    def _check_evidence_integrity(self) -> None:
        if any(item.source_type not in REQUIRED_AUTHORITATIVE_SOURCES for item in self.admitted):
            raise AgentValidationError(
                "knowledge-only evidence cannot provide authoritative coverage"
            )
        if any(self._evidence_digest(item) != item.content_digest for item in self.admitted):
            raise AgentValidationError("admitted evidence content digest changed")
        if any(item.trace_id != self.trace_id for item in self.admitted):
            raise AgentValidationError("admitted evidence trace does not match invocation")

    def _ids(
        self, values: Iterable[str], *, label: str, allowed: Iterable[str] | None = None
    ) -> None:
        ids = tuple(values)
        if not _unique(ids):
            raise AgentValidationError(f"{label} contains duplicate IDs")
        permitted = self.evidence_ids if allowed is None else frozenset(allowed)
        if not set(ids).issubset(permitted):
            raise AgentValidationError(f"{label} contains an unadmitted evidence ID")

    def _claims(
        self,
        result: InvestigatorResult | SynthesisResult,
        *,
        allowed: Iterable[str],
        label: str,
    ) -> tuple[str, ...]:
        """Validate all relation-aware citations and return referenced evidence IDs."""

        claim_ids = tuple(claim.claim_id for claim in result.factual_claims)
        if not _unique(claim_ids):
            raise AgentValidationError(f"{label} contains duplicate claim IDs")
        referenced: set[str] = set()
        for claim in result.factual_claims:
            self._ids(claim.evidence_ids, label=f"{label} claim:{claim.claim_id}", allowed=allowed)
            referenced.update(claim.evidence_ids)
        return tuple(sorted(referenced))

    def validate_investigator(
        self,
        result: InvestigatorResult,
        *,
        allowed_evidence_ids: frozenset[str] | None = None,
        read_evidence_ids: Iterable[str] | None = None,
    ) -> InvestigatorResult:
        self._check_evidence_integrity()
        allowed = self.evidence_ids if allowed_evidence_ids is None else allowed_evidence_ids
        if not allowed.issubset(self.evidence_ids):
            raise AgentValidationError("investigator allowlist contains unadmitted evidence ID")
        self._claims(result, allowed=allowed, label="investigator")
        supporting_evidence_ids = derived_supporting_evidence_ids(result)
        contradicting_evidence_ids = derived_contradicting_evidence_ids(result)
        if read_evidence_ids is not None:
            read_ids = tuple(read_evidence_ids)
            self._ids(
                read_ids,
                label="successful evidence reads",
                allowed=allowed,
            )
            referenced_ids = {
                evidence_id for claim in result.factual_claims for evidence_id in claim.evidence_ids
            }
            if not referenced_ids.issubset(set(read_ids)):
                raise AgentValidationError(
                    "investigator cites evidence that was not successfully read"
                )
        missing_evidence_sources = self.source_availability.missing_evidence_sources
        if (
            result.conclusion is HypothesisConclusion.NEEDS_EVIDENCE
            and not missing_evidence_sources
        ):
            raise AgentValidationError(
                "uncertain investigator requires an authoritative unavailable source"
            )
        if result.conclusion is HypothesisConclusion.SUPPORTED and not supporting_evidence_ids:
            raise AgentValidationError("supported investigator must cite supporting evidence")
        if result.conclusion is HypothesisConclusion.SUPPORTED and contradicting_evidence_ids:
            raise AgentValidationError(
                "supported investigator contains an unresolved contradicting claim"
            )
        if result.conclusion is HypothesisConclusion.SUPPORTED and missing_evidence_sources:
            raise AgentValidationError(
                "supported investigator cannot proceed while an authoritative source is unavailable"
            )
        if (
            result.conclusion is HypothesisConclusion.SUPPORTED
            and read_evidence_ids is not None
            and not set(self.evidence_ids).issubset(set(read_evidence_ids))
        ):
            raise AgentValidationError(
                "supported investigator must successfully read every admitted evidence record"
            )
        expected_hypothesis = {
            investigator: hypothesis
            for hypothesis, investigator in HYPOTHESIS_TO_INVESTIGATOR.items()
        }[result.investigator_id]
        if result.hypothesis_type is not expected_hypothesis:
            raise AgentValidationError("investigator hypothesis does not match its fixed role")
        return result

    def validate_synthesis(
        self,
        result: SynthesisResult,
        investigators: tuple[InvestigatorResult, ...],
    ) -> SynthesisResult:
        self._check_evidence_integrity()
        self._claims(result, allowed=self.evidence_ids, label="synthesis")
        supporting_evidence_ids = derived_supporting_evidence_ids(result)
        contradicting_evidence_ids = derived_contradicting_evidence_ids(result)
        if result.conclusion is HypothesisConclusion.SUPPORTED and contradicting_evidence_ids:
            raise AgentValidationError(
                "supported synthesis contains an unresolved contradicting claim"
            )
        expected_ids = {item.investigator_id for item in investigators}
        if len(expected_ids) != len(investigators) or len(expected_ids) != len(
            HYPOTHESIS_TO_INVESTIGATOR
        ):
            raise AgentValidationError("synthesis requires every fixed investigator exactly once")
        if expected_ids != set(HYPOTHESIS_TO_INVESTIGATOR.values()):
            raise AgentValidationError("synthesis must preserve every investigator exactly once")
        if any(
            HYPOTHESIS_TO_INVESTIGATOR.get(item.hypothesis_type) is not item.investigator_id
            for item in investigators
        ):
            raise AgentValidationError("investigator role and hypothesis mapping is inconsistent")
        selected_role = HYPOTHESIS_TO_INVESTIGATOR.get(result.selected_hypothesis)
        selected = next(
            (item for item in investigators if item.investigator_id is selected_role), None
        )
        if selected is None:
            raise AgentValidationError("synthesis selected hypothesis has no fixed investigator")
        if selected.hypothesis_type is not result.selected_hypothesis:
            raise AgentValidationError("synthesis selected hypothesis does not match fixed role")
        missing_evidence_sources = self.source_availability.missing_evidence_sources
        if missing_evidence_sources:
            if result.conclusion is not HypothesisConclusion.NEEDS_EVIDENCE:
                raise AgentValidationError(
                    "synthesis must request evidence while an authoritative source is unavailable"
                )
        elif result.conclusion is HypothesisConclusion.NEEDS_EVIDENCE:
            raise AgentValidationError(
                "synthesis cannot request evidence when all authoritative sources are available"
            )
        if result.conclusion is HypothesisConclusion.SUPPORTED and not supporting_evidence_ids:
            raise AgentValidationError("supported synthesis must cite supporting evidence")
        if (
            result.conclusion is HypothesisConclusion.SUPPORTED
            and selected.conclusion is not HypothesisConclusion.SUPPORTED
        ):
            raise AgentValidationError(
                "synthesis cannot upgrade a rejected or uncertain investigator"
            )
        return result

    def validate_evaluator(
        self,
        result: AgentEvaluationResult,
        synthesis: SynthesisResult,
        *,
        citation_closure: EvaluatorCitationClosure | None = None,
    ) -> AgentEvaluationResult:
        self._check_evidence_integrity()
        claim_ids = {claim.claim_id for claim in synthesis.factual_claims}
        if not _unique(result.validated_claim_ids):
            raise AgentValidationError("evaluator validated claim IDs contain duplicates")
        if not set(result.validated_claim_ids).issubset(claim_ids):
            raise AgentValidationError("evaluator validated an unknown claim")
        missing_evidence_sources = self.source_availability.missing_evidence_sources
        if missing_evidence_sources and result.decision is not EvaluationDecision.MORE_EVIDENCE:
            raise AgentValidationError(
                "an authoritative source is unavailable; evaluator must request more evidence"
            )
        if not missing_evidence_sources and result.decision is EvaluationDecision.MORE_EVIDENCE:
            raise AgentValidationError(
                "evaluator cannot request more evidence while all authoritative sources "
                "are available"
            )
        if result.decision is EvaluationDecision.ACCEPT:
            if set(result.validated_claim_ids) != claim_ids:
                raise AgentValidationError("accepted synthesis has an unvalidated claim")
            if result.failed_invariants:
                raise AgentValidationError("accepted evaluation contains failed invariants")
            if citation_closure is not None and (
                not citation_closure.all_synthesis_claims_validated
                or not citation_closure.all_admitted_evidence_covered
            ):
                raise AgentValidationError(
                    "accepted synthesis does not have complete citation closure"
                )
        return result

    def derive_evaluator_source_coverage(
        self,
        result: AgentEvaluationResult,
        *,
        synthesis: SynthesisResult | None = None,
        citation_closure: EvaluatorCitationClosure | None = None,
        case_id: str | None = None,
        protocol: AgentProtocolEnvelope | None = None,
    ) -> EvaluatorSourceCoverage:
        """Build application-owned coverage from one immutable citation closure."""

        if citation_closure is None:
            if synthesis is None:
                raise AgentValidationError(
                    "source coverage derivation requires synthesis or citation closure"
                )
            citation_closure = build_evaluator_citation_closure(
                evidence=self.admitted,
                synthesis=synthesis,
                validated_claim_ids=result.validated_claim_ids,
                source_availability=self.source_availability,
                case_id=case_id,
                trace_id=self.trace_id,
                protocol=protocol,
            )

        return build_evaluator_source_coverage(
            evidence=self.admitted,
            source_availability=self.source_availability,
            citation_closure=citation_closure,
            case_id=case_id,
            trace_id=self.trace_id,
            protocol=protocol,
        )

    def build_assessment(
        self,
        *,
        assessment_id: str,
        case_id: str,
        synthesis: SynthesisResult,
        evaluation: AgentEvaluationResult,
        assessed_at: datetime,
        protocol: AgentProtocolEnvelope,
        citation_closure: EvaluatorCitationClosure,
        recommendation: ActionRecommendation | None = None,
    ) -> InvestigationAssessment:
        try:
            validate_protocol_envelope(protocol)
        except ValueError as exc:
            raise AgentValidationError(str(exc)) from exc
        if citation_closure.case_id != case_id or citation_closure.trace_id != self.trace_id:
            raise AgentValidationError("assessment citation closure identity mismatch")
        if tuple(evaluation.validated_claim_ids) != citation_closure.validated_claim_ids:
            raise AgentValidationError("assessment evaluator claims do not match citation closure")
        validated_ids = tuple(sorted(citation_closure.validated_evidence_ids))
        missing = self.source_availability.missing_evidence_sources
        hypothesis = HypothesisResult(
            hypothesis_type=synthesis.selected_hypothesis,
            conclusion=synthesis.conclusion,
            confidence_band=synthesis.confidence_band,
            supporting_evidence_ids=derived_supporting_evidence_ids(synthesis),
            contradicting_evidence_ids=derived_contradicting_evidence_ids(synthesis),
            missing_evidence=missing,
        )
        recommendation = recommendation or ActionRecommendation(
            action=None,
            reason_code="NO_ACTION_POLICY_NOT_RUN",
            selected_investigator=HYPOTHESIS_TO_INVESTIGATOR[synthesis.selected_hypothesis],
            selected_hypothesis=synthesis.selected_hypothesis,
        )
        domain_decision = evaluation.decision
        failed_invariants = set(evaluation.failed_invariants)
        if (
            synthesis.selected_hypothesis is HypothesisType.RETRYABLE_MESSAGE
            and synthesis.conclusion is HypothesisConclusion.SUPPORTED
            and recommendation.action is None
            and not missing
        ):
            domain_decision = EvaluationDecision.REJECT
            failed_invariants.add(recommendation.reason_code)
        domain_evaluation = EvaluationResult(
            decision=domain_decision,
            validated_evidence_ids=validated_ids,
            citation_closure=citation_closure.model_dump(mode="json"),
            failed_invariants=tuple(sorted(failed_invariants)),
            allowed_next_action=recommendation.action,
            evaluator_version=protocol.evaluator_version,
            trace_id=self.trace_id,
        )
        if missing:
            decision = InvestigationDecision.REQUIRE_EVIDENCE
            reason_codes = ("SOURCE_UNAVAILABLE",)
        elif synthesis.selected_hypothesis is HypothesisType.ALREADY_POSTED:
            decision = InvestigationDecision.RECEIPT_ALREADY_POSTED
            reason_codes = ("RECEIPT_ALREADY_POSTED",)
        elif synthesis.selected_hypothesis is HypothesisType.GENUINE_SHORT_SHIPMENT:
            decision = InvestigationDecision.PROTECT
            reason_codes = ("PHYSICAL_SHORT_SHIPMENT",)
        elif evaluation.decision is EvaluationDecision.ACCEPT and recommendation.action is not None:
            decision = InvestigationDecision.RECOMMEND_RECEIPT_RESTART
            reason_codes = ("RETRYABLE_MESSAGE",)
        else:
            decision = InvestigationDecision.EVALUATOR_REJECTED
            reason_codes = ("EVALUATOR_REJECTED",)
        assessment = InvestigationAssessment(
            assessment_id=assessment_id,
            case_id=case_id,
            trace_id=self.trace_id,
            hypothesis=hypothesis,
            evaluation=domain_evaluation,
            admitted_evidence_ids=tuple(sorted(self.evidence_ids)),
            missing_evidence_sources=missing,
            decision=decision,
            reason_codes=reason_codes,
            assessed_at=assessed_at,
        )
        try:
            validate_investigation_assessment(
                assessment,
                admitted_evidence=self.admitted,
                trace_id=self.trace_id,
            )
        except InvalidEventPayload as exc:
            raise AgentValidationError(str(exc)) from exc
        return assessment
