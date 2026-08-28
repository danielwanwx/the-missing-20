from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pytest
from pydantic import ValidationError

from the_missing_20.adapters.clocks import ManualClock
from the_missing_20.adapters.sqlite_case_store import SQLiteCaseStore
from the_missing_20.adapters.synthetic_enterprise import SyntheticEnterprise
from the_missing_20.agents.schemas import (
    REQUIRED_AUTHORITATIVE_SOURCES,
    AgentClaim,
    AgentEvaluationResult,
    ClaimRelation,
    SourceAvailability,
    SourceAvailabilitySet,
    SynthesisResult,
)
from the_missing_20.agents.validation import (
    AgentEvidenceValidator,
    AgentValidationError,
    build_evaluator_source_coverage,
)
from the_missing_20.application.detector import DiscrepancyDetector
from the_missing_20.domain.enterprise import EvidenceReadStatus
from the_missing_20.domain.models import (
    ConfidenceBand,
    EvaluationDecision,
    EvidenceSourceType,
    HypothesisConclusion,
    HypothesisType,
)
from the_missing_20.evaluation.agent_golden_runner import source_availability_from_genesis

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "fixtures/scenarios/retryable-document-lock.json"


def _case() -> tuple[tuple[Any, ...], SourceAvailabilitySet]:
    with TemporaryDirectory() as raw:
        root = Path(raw)
        enterprise = SyntheticEnterprise.seed_from_fixture(root / "enterprise.sqlite", FIXTURE)
        store = SQLiteCaseStore(root / "case.sqlite")
        _case, evidence = DiscrepancyDetector(
            enterprise,
            store,
            ManualClock(datetime(2026, 8, 26, tzinfo=UTC)),
        ).detect(
            case_id="case-v8",
            trace_id="trace-v8",
            fixture_path=FIXTURE,
        )
        availability = source_availability_from_genesis(store.get_genesis("case-v8"), evidence)
        return evidence, availability


def _ids(evidence: tuple[Any, ...]) -> tuple[str, ...]:
    return tuple(item.evidence_id for item in evidence)


def test_evaluator_contract_is_semantic_only() -> None:
    properties = AgentEvaluationResult.model_json_schema()["properties"]
    assert set(properties) == {
        "decision",
        "validated_claim_ids",
        "failed_invariants",
    }
    for field in ("required_evidence_sources", "validated_source_types", "source_availability"):
        with pytest.raises(ValidationError, match=field):
            AgentEvaluationResult.model_validate({"decision": "ACCEPT", field: []})


def test_source_projection_is_harness_owned_and_stably_ordered() -> None:
    evidence, availability = _case()
    coverage = build_evaluator_source_coverage(
        evidence=evidence,
        source_availability=availability,
        validated_evidence_ids=_ids(evidence),
        case_id="case-v8",
        trace_id="trace-v8",
    )
    reversed_coverage = build_evaluator_source_coverage(
        evidence=tuple(reversed(evidence)),
        source_availability=SourceAvailabilitySet(sources=tuple(reversed(availability.sources))),
        validated_evidence_ids=tuple(reversed(_ids(evidence))),
        case_id="case-v8",
        trace_id="trace-v8",
    )
    assert coverage == reversed_coverage
    assert coverage.validated_source_types == tuple(
        sorted(REQUIRED_AUTHORITATIVE_SOURCES, key=lambda source: source.value)
    )
    assert coverage.all_admitted_evidence_validated is True
    assert coverage.all_required_sources_available is True
    assert coverage.all_required_sources_validated is True


@pytest.mark.parametrize("bad_kind", ("duplicate", "unknown", "cross_case", "stale"))
def test_invalid_evaluator_ids_fail_closed(bad_kind: str) -> None:
    evidence, availability = _case()
    ids = _ids(evidence)
    bad_ids = ids + (ids[0],) if bad_kind == "duplicate" else ids[:-1] + ("unknown",)
    bad_evidence = evidence
    if bad_kind == "cross_case":
        bad_evidence = (evidence[0].model_copy(update={"case_id": "other-case"}),) + evidence[1:]
        bad_ids = _ids(bad_evidence)
    if bad_kind == "stale":
        bad_evidence = (evidence[0].model_copy(update={"content_digest": "0" * 64}),) + evidence[1:]
        bad_ids = _ids(bad_evidence)
    with pytest.raises(AgentValidationError):
        build_evaluator_source_coverage(
            evidence=bad_evidence,
            source_availability=availability,
            validated_evidence_ids=bad_ids,
            case_id="case-v8",
            trace_id="trace-v8",
        )


def test_knowledge_only_record_cannot_count_as_source_coverage() -> None:
    evidence, availability = _case()
    knowledge = evidence[0].model_copy(update={"source_type": EvidenceSourceType.KNOWLEDGE_BASE})
    with pytest.raises(AgentValidationError, match="knowledge-only"):
        build_evaluator_source_coverage(
            evidence=(knowledge,) + evidence[1:],
            source_availability=availability,
            validated_evidence_ids=_ids(evidence),
            case_id="case-v8",
            trace_id="trace-v8",
        )


def test_unavailable_source_is_a_non_promotable_projection() -> None:
    evidence, availability = _case()
    available_evidence = tuple(
        item for item in evidence if item.source_type is not EvidenceSourceType.MATERIAL_DOCUMENT
    )
    unavailable = SourceAvailabilitySet(
        sources=tuple(
            SourceAvailability(
                source_type=item.source_type,
                status=(
                    EvidenceReadStatus.UNAVAILABLE
                    if item.source_type is EvidenceSourceType.MATERIAL_DOCUMENT
                    else item.status
                ),
                unavailability_reason=(
                    "SOURCE_UNAVAILABLE"
                    if item.source_type is EvidenceSourceType.MATERIAL_DOCUMENT
                    else item.unavailability_reason
                ),
            )
            for item in availability.sources
        )
    )
    coverage = build_evaluator_source_coverage(
        evidence=available_evidence,
        source_availability=unavailable,
        validated_evidence_ids=_ids(available_evidence),
        case_id="case-v8",
        trace_id="trace-v8",
    )
    assert coverage.all_required_sources_available is False
    assert coverage.all_required_sources_validated is False
    assert coverage.reason_code == "AUTHORITATIVE_SOURCE_UNAVAILABLE"


def test_unavailable_source_requires_more_evidence_evaluator_decision() -> None:
    evidence, availability = _case()
    admitted = tuple(
        item for item in evidence if item.source_type is not EvidenceSourceType.MATERIAL_DOCUMENT
    )
    unavailable = SourceAvailabilitySet(
        sources=tuple(
            SourceAvailability(
                source_type=item.source_type,
                status=(
                    EvidenceReadStatus.UNAVAILABLE
                    if item.source_type is EvidenceSourceType.MATERIAL_DOCUMENT
                    else item.status
                ),
                unavailability_reason=(
                    "SOURCE_UNAVAILABLE"
                    if item.source_type is EvidenceSourceType.MATERIAL_DOCUMENT
                    else item.unavailability_reason
                ),
            )
            for item in availability.sources
        )
    )
    validator = AgentEvidenceValidator(
        admitted,
        trace_id="trace-v8",
        source_availability=unavailable,
    )
    synthesis = SynthesisResult(
        selected_hypothesis=HypothesisType.RETRYABLE_MESSAGE,
        conclusion=HypothesisConclusion.NEEDS_EVIDENCE,
        confidence_band=ConfidenceBand.LOW,
        factual_claims=(
            AgentClaim(
                claim_id="claim-v8",
                statement="The available records are not enough to decide.",
                relation=ClaimRelation.SUPPORTS_HYPOTHESIS,
                evidence_ids=(admitted[0].evidence_id,),
            ),
        ),
    )
    for decision in (EvaluationDecision.REJECT, EvaluationDecision.ACCEPT):
        invalid = AgentEvaluationResult(
            decision=decision,
            validated_claim_ids=("claim-v8",),
        )
        with pytest.raises(AgentValidationError, match="must request more evidence"):
            validator.validate_evaluator(invalid, synthesis)

    more_evidence = AgentEvaluationResult(
        decision=EvaluationDecision.MORE_EVIDENCE,
        validated_claim_ids=("claim-v8",),
    )
    assert validator.validate_evaluator(more_evidence, synthesis) == more_evidence


def test_more_evidence_is_rejected_when_all_authoritative_sources_are_available() -> None:
    evidence, availability = _case()
    validator = AgentEvidenceValidator(
        evidence,
        trace_id="trace-v8",
        source_availability=availability,
    )
    synthesis = SynthesisResult(
        selected_hypothesis=HypothesisType.RETRYABLE_MESSAGE,
        conclusion=HypothesisConclusion.SUPPORTED,
        confidence_band=ConfidenceBand.HIGH,
    )
    more_evidence = AgentEvaluationResult(decision=EvaluationDecision.MORE_EVIDENCE)
    with pytest.raises(AgentValidationError, match="all authoritative sources are available"):
        validator.validate_evaluator(more_evidence, synthesis)
