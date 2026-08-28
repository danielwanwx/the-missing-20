"""Application-owned coverage and action recommendation policy.

The model stages in Milestone 4 interpret evidence, but they never decide whether an
operational action is eligible.  This module is intentionally pure: it consumes typed
detector facts, audited reads, validated model records, and evaluator output and
returns a stable recommendation.  It does not call a model or the legacy diagnosis
oracle.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from typing import cast

from pydantic import Field, model_validator

from the_missing_20.agents.schemas import (
    HYPOTHESIS_TO_INVESTIGATOR,
    REQUIRED_AUTHORITATIVE_SOURCES,
    AgentEvaluationResult,
    AgentProtocolEnvelope,
    ClaimRelation,
    EvaluatorCitationClosure,
    EvaluatorSourceCoverage,
    InvestigatorID,
    InvestigatorResult,
    SourceAvailabilitySet,
    SynthesisResult,
    derived_claim_ids_by_relation,
    derived_contradicting_evidence_ids,
    derived_supporting_evidence_ids,
)
from the_missing_20.domain.enterprise import EvidenceReadStatus
from the_missing_20.domain.models import (
    ActionTool,
    ContractModel,
    EvaluationDecision,
    EvidenceItem,
    EvidenceSourceType,
    HypothesisConclusion,
    HypothesisType,
    NonEmptyStr,
)

POLICY_VERSION = "action-policy/v2"
LEDGER_SCHEMA_VERSION = "coverage-ledger/v2"

RECOMMEND_RESTART = "RECOMMEND_RESTART_RECEIPT_MESSAGE"
NO_ACTION_NON_RETRYABLE = "NON_RETRYABLE_HYPOTHESIS"
NO_ACTION_SYNTHESIS_UNSUPPORTED = "SYNTHESIS_NOT_SUPPORTED"
NO_ACTION_SELECTED_UNSUPPORTED = "SELECTED_INVESTIGATOR_NOT_SUPPORTED"
NO_ACTION_SOURCE_UNAVAILABLE = "AUTHORITATIVE_SOURCE_UNAVAILABLE"
NO_ACTION_COVERAGE_INCOMPLETE = "SELECTED_COVERAGE_INCOMPLETE"
NO_ACTION_UNRESOLVED_CONTRADICTING_CLAIM = "UNRESOLVED_CONTRADICTING_CLAIM"
# Kept as a source-compatible name for application callers; v2 uses the more
# precise claim-level reason above.
NO_ACTION_CONFLICT = NO_ACTION_UNRESOLVED_CONTRADICTING_CLAIM
NO_ACTION_EVALUATOR_REJECTED = "EVALUATOR_NOT_ACCEPTED"
NO_ACTION_CLAIM_UNVALIDATED = "EVALUATOR_CLAIM_COVERAGE_INCOMPLETE"
NO_ACTION_EVIDENCE_UNVALIDATED = "EVALUATOR_EVIDENCE_COVERAGE_INCOMPLETE"
NO_ACTION_SOURCE_UNVALIDATED = "EVALUATOR_SOURCE_COVERAGE_INCOMPLETE"
NO_ACTION_INVARIANTS = "EVALUATOR_FAILED_INVARIANT"
NO_ACTION_RETRYABLE_INVARIANT = "RETRYABLE_DOMAIN_INVARIANT_FAILED"
NO_ACTION_DISSENT = "DISSENT_NOT_PRESERVED"


class CoverageLedgerError(ValueError):
    """The application could not build a trustworthy coverage ledger."""


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _content_digest(item: EvidenceItem) -> str:
    return hashlib.sha256(_canonical(item.admitted_fields).encode()).hexdigest()


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


class EvidenceCoverageRecord(ContractModel):
    """Public, content-free coverage facts for one authoritative source."""

    source_type: EvidenceSourceType
    status: EvidenceReadStatus
    unavailability_reason: NonEmptyStr | None = None
    admitted_evidence_id: NonEmptyStr | None = None
    admitted_content_digest: NonEmptyStr | None = None
    selected_investigator_read: bool
    integrity_valid: bool
    identity_valid: bool
    evaluator_validated: bool

    @model_validator(mode="after")
    def status_and_identity_are_consistent(self) -> EvidenceCoverageRecord:
        if self.status is EvidenceReadStatus.AVAILABLE:
            if self.unavailability_reason is not None:
                raise ValueError("available coverage cannot have an unavailability reason")
            if self.admitted_evidence_id is None or self.admitted_content_digest is None:
                raise ValueError("available coverage requires an admitted evidence identity")
        else:
            if self.unavailability_reason is None:
                raise ValueError("unavailable coverage requires a reason")
            if self.admitted_evidence_id is not None or self.admitted_content_digest is not None:
                raise ValueError("unavailable coverage cannot have admitted evidence")
            if self.selected_investigator_read or self.integrity_valid or self.identity_valid:
                raise ValueError("unavailable coverage cannot report successful validation")
            if self.evaluator_validated:
                raise ValueError("unavailable coverage cannot be evaluator validated")
        return self


def _empty_claim_relation_groups() -> dict[ClaimRelation, tuple[str, ...]]:
    return {relation: () for relation in ClaimRelation}


class EvidenceCoverageLedger(ContractModel):
    """Immutable application-owned source coverage for the selected diagnosis."""

    schema_version: str = Field(default=LEDGER_SCHEMA_VERSION, pattern=r"^coverage-ledger/v2$")
    policy_version: str = Field(default=POLICY_VERSION, pattern=r"^action-policy/v2$")
    selected_investigator: InvestigatorID
    selected_hypothesis: HypothesisType
    sources: tuple[EvidenceCoverageRecord, ...] = Field(
        min_length=len(REQUIRED_AUTHORITATIVE_SOURCES),
        max_length=len(REQUIRED_AUTHORITATIVE_SOURCES),
    )
    selected_result_supported: bool
    complete_coverage: bool
    conflict_free: bool
    unresolved_conflict: bool = False
    selected_claim_ids_by_relation: dict[ClaimRelation, tuple[NonEmptyStr, ...]] = Field(
        default_factory=_empty_claim_relation_groups
    )
    evaluator_citation_closure: EvaluatorCitationClosure | None = None
    evaluator_source_coverage: EvaluatorSourceCoverage | None = None
    outcome_reason: NonEmptyStr = "PENDING_POLICY_EVALUATION"
    protocol: AgentProtocolEnvelope | None = None

    @property
    def claim_ids_by_relation(self) -> dict[ClaimRelation, tuple[NonEmptyStr, ...]]:
        """Portable alias for the selected investigator's validated claim groups."""

        return self.selected_claim_ids_by_relation

    @property
    def validated_claim_ids_by_relation(self) -> dict[ClaimRelation, tuple[NonEmptyStr, ...]]:
        """Name used by the public contract to emphasize deterministic validation."""

        return self.selected_claim_ids_by_relation

    @model_validator(mode="after")
    def exact_source_set(self) -> EvidenceCoverageLedger:
        observed = tuple(item.source_type for item in self.sources)
        if len(observed) != len(set(observed)):
            raise ValueError("coverage ledger contains a duplicate source")
        if set(observed) != set(REQUIRED_AUTHORITATIVE_SOURCES):
            raise ValueError("coverage ledger must contain every required source exactly once")
        expected = HYPOTHESIS_TO_INVESTIGATOR.get(self.selected_hypothesis)
        if expected is not self.selected_investigator:
            raise ValueError("selected hypothesis does not map to its fixed investigator")
        expected_complete = (
            self.selected_result_supported
            and self.conflict_free
            and all(
                item.status is EvidenceReadStatus.AVAILABLE
                and item.selected_investigator_read
                and item.integrity_valid
                and item.identity_valid
                and item.evaluator_validated
                for item in self.sources
            )
        )
        if self.complete_coverage != expected_complete:
            raise ValueError("coverage ledger complete flag is not deterministically derived")
        if self.unresolved_conflict == self.conflict_free:
            raise ValueError("coverage ledger conflict flags are inconsistent")
        if set(self.selected_claim_ids_by_relation) != set(ClaimRelation):
            raise ValueError("coverage ledger must contain every claim relation exactly once")
        claim_ids = tuple(
            claim_id
            for relation in ClaimRelation
            for claim_id in self.selected_claim_ids_by_relation[relation]
        )
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("coverage ledger contains duplicate claim IDs")
        if (
            self.evaluator_citation_closure is not None
            and self.evaluator_source_coverage is not None
            and self.evaluator_source_coverage.citation_closure is not None
            and self.evaluator_citation_closure != self.evaluator_source_coverage.citation_closure
        ):
            raise ValueError("coverage ledger citation closure does not match source coverage")
        if (
            self.evaluator_source_coverage is not None
            and self.evaluator_source_coverage.all_required_sources_validated
            and not self.complete_coverage
        ):
            raise ValueError("complete evaluator source coverage cannot produce incomplete ledger")
        if self.protocol is not None:
            if self.protocol.coverage_ledger_version != self.schema_version:
                raise ValueError("coverage ledger protocol version mismatch")
            if self.protocol.action_policy_version != self.policy_version:
                raise ValueError("coverage ledger policy version mismatch")
        return self


class ActionRecommendation(ContractModel):
    """Pure policy output; action is only a recommendation, never an authorization."""

    policy_version: str = Field(default=POLICY_VERSION, pattern=r"^action-policy/v2$")
    action: ActionTool | None = None
    reason_code: NonEmptyStr
    selected_investigator: InvestigatorID
    selected_hypothesis: HypothesisType
    protocol: AgentProtocolEnvelope | None = None

    @model_validator(mode="after")
    def protocol_metadata_is_consistent(self) -> ActionRecommendation:
        if self.protocol is not None and self.protocol.action_policy_version != self.policy_version:
            raise ValueError("action recommendation policy version mismatch")
        return self


def build_evidence_coverage_ledger(
    *,
    evidence: tuple[EvidenceItem, ...],
    source_availability: SourceAvailabilitySet,
    selected_hypothesis: HypothesisType,
    selected_investigator: InvestigatorResult,
    selected_investigator_read_ids: Iterable[str],
    evaluator: AgentEvaluationResult,
    conflict_free: bool | None = None,
    selected_synthesis: SynthesisResult | None = None,
    evaluator_citation_closure: EvaluatorCitationClosure | None = None,
    evaluator_source_coverage: EvaluatorSourceCoverage | None = None,
    outcome_reason: str = "PENDING_POLICY_EVALUATION",
    protocol: AgentProtocolEnvelope | None = None,
) -> EvidenceCoverageLedger:
    """Build a deterministic ledger from detector state and audited application data."""

    # Import lazily to avoid the policy <-> validation import cycle.  Recompute the
    # expected projection even when one was supplied so a caller cannot smuggle a
    # hand-authored source aggregate into the policy ledger.
    from the_missing_20.agents.validation import build_evaluator_source_coverage

    if evaluator_citation_closure is None:
        if evaluator_source_coverage is not None:
            evaluator_citation_closure = evaluator_source_coverage.citation_closure
        if evaluator_citation_closure is None:
            raise CoverageLedgerError(
                "coverage ledger requires an application-owned citation closure"
            )
    expected_source_coverage = build_evaluator_source_coverage(
        evidence=evidence,
        source_availability=source_availability,
        citation_closure=evaluator_citation_closure,
        protocol=protocol,
    )
    if (
        evaluator_source_coverage is not None
        and evaluator_source_coverage != expected_source_coverage
    ):
        raise CoverageLedgerError("evaluator source coverage does not match admitted evidence")
    evaluator_source_coverage = expected_source_coverage

    try:
        source_availability.validate_against_evidence(evidence)
    except ValueError as exc:
        raise CoverageLedgerError(str(exc)) from exc
    evidence_by_source: dict[EvidenceSourceType, EvidenceItem] = {}
    evidence_by_id: dict[str, EvidenceItem] = {}
    context_case_id = evidence[0].case_id if evidence else None
    context_trace_id = evidence[0].trace_id if evidence else None
    for item in evidence:
        if item.source_type not in REQUIRED_AUTHORITATIVE_SOURCES:
            raise CoverageLedgerError("coverage ledger contains a non-authoritative source")
        if item.case_id != context_case_id or item.trace_id != context_trace_id:
            raise CoverageLedgerError("coverage ledger evidence context is inconsistent")
        if item.evidence_id in evidence_by_id:
            raise CoverageLedgerError("admitted evidence contains duplicate IDs")
        if item.source_type in evidence_by_source:
            raise CoverageLedgerError("admitted evidence contains duplicate source records")
        evidence_by_id[item.evidence_id] = item
        evidence_by_source[item.source_type] = item
    read_ids = tuple(selected_investigator_read_ids)
    if len(read_ids) != len(set(read_ids)):
        raise CoverageLedgerError("selected investigator read IDs contain duplicates")
    if not all(isinstance(item, str) and item.strip() for item in read_ids):
        raise CoverageLedgerError("selected investigator read IDs are malformed")
    if not set(read_ids).issubset(evidence_by_id):
        raise CoverageLedgerError("selected investigator read ID is not admitted")
    evaluator_ids = tuple(evaluator_citation_closure.validated_evidence_ids)
    if len(evaluator_ids) != len(set(evaluator_ids)):
        raise CoverageLedgerError("evaluator validated evidence IDs contain duplicates")
    if not set(evaluator_ids).issubset(evidence_by_id):
        raise CoverageLedgerError("evaluator validated an unadmitted evidence ID")
    if (
        selected_investigator.investigator_id
        is not HYPOTHESIS_TO_INVESTIGATOR.get(selected_hypothesis)
        or selected_investigator.hypothesis_type is not selected_hypothesis
    ):
        raise CoverageLedgerError("selected investigator does not match the fixed hypothesis")
    selected_supported = selected_investigator.conclusion is HypothesisConclusion.SUPPORTED
    selected_claim_ids = derived_claim_ids_by_relation(selected_investigator)
    unresolved_conflict = bool(
        derived_contradicting_evidence_ids(selected_investigator)
        or (
            selected_synthesis is not None
            and derived_contradicting_evidence_ids(selected_synthesis)
        )
    )
    derived_conflict_free = not unresolved_conflict
    if conflict_free is not None and conflict_free is not derived_conflict_free:
        raise CoverageLedgerError(
            "coverage ledger conflict flag does not match relation-aware claims"
        )
    conflict_free = derived_conflict_free
    records: list[EvidenceCoverageRecord] = []
    for availability in source_availability.sources:
        evidence_item = evidence_by_source.get(availability.source_type)
        if availability.status is EvidenceReadStatus.UNAVAILABLE:
            try:
                records.append(
                    EvidenceCoverageRecord(
                        source_type=availability.source_type,
                        status=availability.status,
                        unavailability_reason=availability.unavailability_reason,
                        selected_investigator_read=False,
                        integrity_valid=False,
                        identity_valid=False,
                        evaluator_validated=False,
                    )
                )
            except ValueError as exc:
                raise CoverageLedgerError(str(exc)) from exc
            continue
        if evidence_item is None:
            raise CoverageLedgerError("available source has no admitted evidence")
        integrity_valid = _content_digest(evidence_item) == evidence_item.content_digest
        identity_valid = bool(
            evidence_item.evidence_id
            and evidence_item.case_id
            and evidence_item.trace_id
            and evidence_item.source_record_id
        )
        try:
            records.append(
                EvidenceCoverageRecord(
                    source_type=availability.source_type,
                    status=availability.status,
                    admitted_evidence_id=evidence_item.evidence_id,
                    admitted_content_digest=evidence_item.content_digest,
                    selected_investigator_read=evidence_item.evidence_id in read_ids,
                    integrity_valid=integrity_valid,
                    identity_valid=identity_valid,
                    evaluator_validated=evidence_item.evidence_id in evaluator_ids,
                )
            )
        except ValueError as exc:
            raise CoverageLedgerError(str(exc)) from exc
    complete = (
        selected_supported
        and conflict_free
        and evaluator_source_coverage.all_required_sources_validated
        and all(
            item.status is EvidenceReadStatus.AVAILABLE
            and item.selected_investigator_read
            and item.integrity_valid
            and item.identity_valid
            and item.evaluator_validated
            for item in records
        )
    )
    try:
        return EvidenceCoverageLedger(
            selected_investigator=selected_investigator.investigator_id,
            selected_hypothesis=selected_hypothesis,
            sources=tuple(records),
            selected_result_supported=selected_supported,
            complete_coverage=complete,
            conflict_free=conflict_free,
            unresolved_conflict=unresolved_conflict,
            selected_claim_ids_by_relation=selected_claim_ids,
            evaluator_citation_closure=evaluator_citation_closure,
            evaluator_source_coverage=evaluator_source_coverage,
            outcome_reason=outcome_reason,
            protocol=protocol,
        )
    except ValueError as exc:
        raise CoverageLedgerError(str(exc)) from exc


def _retryable_invariants(evidence: tuple[EvidenceItem, ...]) -> bool:
    by_source = {item.source_type: item for item in evidence}
    if set(by_source) != set(REQUIRED_AUTHORITATIVE_SOURCES):
        return False
    queue = by_source[EvidenceSourceType.FAILED_MESSAGE_QUEUE].admitted_fields
    erp = by_source[EvidenceSourceType.ERP_RECEIPT].admitted_fields
    material = by_source[EvidenceSourceType.MATERIAL_DOCUMENT].admitted_fields
    warehouse = by_source[EvidenceSourceType.WAREHOUSE].admitted_fields
    if (
        queue.get("status") != "FAILED"
        or queue.get("error_code") != "DOCUMENT_LOCKED_RETRYABLE"
        or queue.get("retry_eligible") is not True
        or queue.get("lock_cleared") is not True
        or material.get("material_documents") != []
    ):
        return False
    message_quantity = queue.get("quantity")
    warehouse_quantity = warehouse.get("quantity")
    erp_quantity = erp.get("quantity")
    if (
        not _is_int(message_quantity)
        or not _is_int(warehouse_quantity)
        or not _is_int(erp_quantity)
    ):
        return False
    message = cast(int, message_quantity)
    warehouse_value = cast(int, warehouse_quantity)
    erp_value = cast(int, erp_quantity)
    return message > 0 and warehouse_value - erp_value == message


def _ledger_is_complete(ledger: EvidenceCoverageLedger) -> bool:
    """Recompute completion instead of trusting a serialized completion bit."""

    return (
        ledger.selected_result_supported
        and ledger.conflict_free
        and not ledger.unresolved_conflict
        and all(
            source.status is EvidenceReadStatus.AVAILABLE
            and source.admitted_evidence_id is not None
            and source.admitted_content_digest is not None
            and source.selected_investigator_read
            and source.integrity_valid
            and source.identity_valid
            and source.evaluator_validated
            for source in ledger.sources
        )
    )


def _recommendation(
    *,
    action: ActionTool | None,
    reason_code: str,
    synthesis: SynthesisResult,
    protocol: AgentProtocolEnvelope | None = None,
) -> ActionRecommendation:
    return ActionRecommendation(
        action=action,
        reason_code=reason_code,
        selected_investigator=HYPOTHESIS_TO_INVESTIGATOR[synthesis.selected_hypothesis],
        selected_hypothesis=synthesis.selected_hypothesis,
        protocol=protocol,
    )


class ActionRecommendationPolicy:
    """Pure v1 policy for deriving the only allowed action recommendation."""

    VERSION = POLICY_VERSION

    @classmethod
    def evaluate(
        cls,
        *,
        synthesis: SynthesisResult,
        investigators: tuple[InvestigatorResult, ...],
        evaluator: AgentEvaluationResult,
        evidence: tuple[EvidenceItem, ...],
        ledger: EvidenceCoverageLedger,
        evaluator_citation_closure: EvaluatorCitationClosure | None = None,
        evaluator_source_coverage: EvaluatorSourceCoverage | None = None,
        source_coverage: EvaluatorSourceCoverage | None = None,
    ) -> ActionRecommendation:
        """Return a recommendation without selecting or repairing model output."""

        if synthesis.selected_hypothesis is not HypothesisType.RETRYABLE_MESSAGE:
            return _recommendation(
                action=None,
                reason_code=NO_ACTION_NON_RETRYABLE,
                synthesis=synthesis,
            )
        if synthesis.conclusion is not HypothesisConclusion.SUPPORTED:
            return _recommendation(
                action=None,
                reason_code=NO_ACTION_SYNTHESIS_UNSUPPORTED,
                synthesis=synthesis,
            )
        selected_role = HYPOTHESIS_TO_INVESTIGATOR[synthesis.selected_hypothesis]
        selected = next(
            (item for item in investigators if item.investigator_id is selected_role), None
        )
        if selected is None or selected.hypothesis_type is not synthesis.selected_hypothesis:
            return _recommendation(
                action=None,
                reason_code=NO_ACTION_SELECTED_UNSUPPORTED,
                synthesis=synthesis,
            )
        if (
            derived_contradicting_evidence_ids(synthesis)
            or derived_contradicting_evidence_ids(selected)
            or ledger.unresolved_conflict
            or not ledger.conflict_free
        ):
            return _recommendation(
                action=None,
                reason_code=NO_ACTION_UNRESOLVED_CONTRADICTING_CLAIM,
                synthesis=synthesis,
            )
        if selected.conclusion is not HypothesisConclusion.SUPPORTED:
            return _recommendation(
                action=None,
                reason_code=NO_ACTION_SELECTED_UNSUPPORTED,
                synthesis=synthesis,
            )
        if (
            ledger.selected_investigator is not selected_role
            or ledger.selected_hypothesis is not synthesis.selected_hypothesis
        ):
            return _recommendation(
                action=None,
                reason_code=NO_ACTION_SELECTED_UNSUPPORTED,
                synthesis=synthesis,
            )
        coverage = evaluator_source_coverage or source_coverage or ledger.evaluator_source_coverage
        closure = evaluator_citation_closure or ledger.evaluator_citation_closure
        if closure is None:
            return _recommendation(
                action=None, reason_code=NO_ACTION_EVIDENCE_UNVALIDATED, synthesis=synthesis
            )
        if (
            ledger.evaluator_citation_closure is not None
            and closure != ledger.evaluator_citation_closure
        ):
            return _recommendation(
                action=None, reason_code=NO_ACTION_EVIDENCE_UNVALIDATED, synthesis=synthesis
            )
        if coverage is not None and coverage.citation_closure not in (None, closure):
            return _recommendation(
                action=None, reason_code=NO_ACTION_SOURCE_UNVALIDATED, synthesis=synthesis
            )
        if coverage is None:
            return _recommendation(
                action=None, reason_code=NO_ACTION_SOURCE_UNVALIDATED, synthesis=synthesis
            )
        if (
            ledger.evaluator_source_coverage is not None
            and coverage != ledger.evaluator_source_coverage
        ):
            return _recommendation(
                action=None, reason_code=NO_ACTION_SOURCE_UNVALIDATED, synthesis=synthesis
            )
        if not coverage.all_required_sources_available:
            return _recommendation(
                action=None, reason_code=NO_ACTION_SOURCE_UNAVAILABLE, synthesis=synthesis
            )
        if (
            not coverage.all_admitted_evidence_validated
            or not coverage.all_required_sources_validated
            or not coverage.identity_valid
            or not coverage.integrity_valid
            or not coverage.protocol_consistent
            or set(coverage.validated_source_types) != set(REQUIRED_AUTHORITATIVE_SOURCES)
        ):
            return _recommendation(
                action=None, reason_code=NO_ACTION_SOURCE_UNVALIDATED, synthesis=synthesis
            )
        if (
            not closure.all_synthesis_claims_validated
            or not closure.all_admitted_evidence_covered
            or not closure.identity_valid
            or not closure.integrity_valid
            or not closure.relation_valid
            or not closure.availability_valid
            or not closure.protocol_consistent
        ):
            return _recommendation(
                action=None, reason_code=NO_ACTION_EVIDENCE_UNVALIDATED, synthesis=synthesis
            )
        if not ledger.complete_coverage or not _ledger_is_complete(ledger):
            if any(item.status is EvidenceReadStatus.UNAVAILABLE for item in ledger.sources):
                reason_code = NO_ACTION_SOURCE_UNAVAILABLE
            elif not all(
                item.selected_investigator_read
                for item in ledger.sources
                if item.admitted_evidence_id
            ):
                reason_code = NO_ACTION_COVERAGE_INCOMPLETE
            else:
                reason_code = NO_ACTION_COVERAGE_INCOMPLETE
            return _recommendation(action=None, reason_code=reason_code, synthesis=synthesis)
        if ledger.selected_claim_ids_by_relation != derived_claim_ids_by_relation(selected):
            return _recommendation(
                action=None, reason_code=NO_ACTION_CLAIM_UNVALIDATED, synthesis=synthesis
            )
        claim_ids = {item.claim_id for item in synthesis.factual_claims}
        if len(evaluator.validated_claim_ids) != len(set(evaluator.validated_claim_ids)):
            return _recommendation(
                action=None, reason_code=NO_ACTION_CLAIM_UNVALIDATED, synthesis=synthesis
            )
        if set(evaluator.validated_claim_ids) != claim_ids:
            return _recommendation(
                action=None, reason_code=NO_ACTION_CLAIM_UNVALIDATED, synthesis=synthesis
            )
        if len(closure.validated_evidence_ids) != len(set(closure.validated_evidence_ids)):
            return _recommendation(
                action=None, reason_code=NO_ACTION_EVIDENCE_UNVALIDATED, synthesis=synthesis
            )
        if set(closure.validated_evidence_ids) != {item.evidence_id for item in evidence}:
            return _recommendation(
                action=None, reason_code=NO_ACTION_EVIDENCE_UNVALIDATED, synthesis=synthesis
            )
        if evaluator.decision is not EvaluationDecision.ACCEPT:
            return _recommendation(
                action=None, reason_code=NO_ACTION_EVALUATOR_REJECTED, synthesis=synthesis
            )
        if evaluator.failed_invariants:
            return _recommendation(
                action=None, reason_code=NO_ACTION_INVARIANTS, synthesis=synthesis
            )
        if derived_supporting_evidence_ids(synthesis) != tuple(
            sorted(derived_supporting_evidence_ids(selected))
        ):
            return _recommendation(
                action=None, reason_code=NO_ACTION_COVERAGE_INCOMPLETE, synthesis=synthesis
            )
        if not _retryable_invariants(evidence):
            return _recommendation(
                action=None, reason_code=NO_ACTION_RETRYABLE_INVARIANT, synthesis=synthesis
            )
        return _recommendation(
            action=ActionTool.RESTART_RECEIPT_MESSAGE,
            reason_code=RECOMMEND_RESTART,
            synthesis=synthesis,
        )

    recommend = evaluate
