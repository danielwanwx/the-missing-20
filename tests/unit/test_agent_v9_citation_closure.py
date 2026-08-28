from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pytest
from pydantic import ValidationError

from the_missing_20.adapters.clocks import ManualClock
from the_missing_20.adapters.local_knowledge import LocalKnowledgeRepository
from the_missing_20.adapters.sqlite_case_store import SQLiteCaseStore
from the_missing_20.adapters.strands_models import ScriptedStrandsFactory
from the_missing_20.adapters.synthetic_enterprise import SyntheticEnterprise
from the_missing_20.agents.harness import AgentHarness
from the_missing_20.agents.schemas import (
    AgentClaim,
    AgentEvaluationResult,
    ClaimRelation,
    SourceAvailability,
    SourceAvailabilitySet,
    SynthesisResult,
)
from the_missing_20.agents.validation import (
    AgentValidationError,
    build_evaluator_citation_closure,
)
from the_missing_20.application.detector import DiscrepancyDetector
from the_missing_20.domain.enterprise import EvidenceReadStatus
from the_missing_20.domain.models import (
    ConfidenceBand,
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
        ).detect(case_id="case-v9", trace_id="trace-v9", fixture_path=FIXTURE)
        return evidence, source_availability_from_genesis(store.get_genesis("case-v9"), evidence)


def _synthesis(evidence: tuple[Any, ...], *claims: AgentClaim) -> SynthesisResult:
    return SynthesisResult(
        selected_hypothesis=HypothesisType.RETRYABLE_MESSAGE,
        conclusion=HypothesisConclusion.SUPPORTED,
        confidence_band=ConfidenceBand.HIGH,
        factual_claims=claims,
    )


def test_v9_evaluator_schema_has_no_deterministic_evidence_authority() -> None:
    assert set(AgentEvaluationResult.model_json_schema()["properties"]) == {
        "decision",
        "validated_claim_ids",
        "failed_invariants",
    }
    with pytest.raises(ValidationError, match="validated_evidence_ids"):
        AgentEvaluationResult.model_validate(
            {
                "decision": "ACCEPT",
                "validated_claim_ids": [],
                "validated_evidence_ids": [],
                "failed_invariants": [],
            }
        )


def test_citation_closure_is_stable_and_derived_from_claims() -> None:
    evidence, availability = _case()
    claim = AgentClaim(
        claim_id="claim-v9",
        statement="The admitted records support the retryable message hypothesis.",
        relation=ClaimRelation.SUPPORTS_HYPOTHESIS,
        evidence_ids=tuple(reversed(tuple(item.evidence_id for item in evidence))),
    )
    synthesis = _synthesis(evidence, claim)
    closure = build_evaluator_citation_closure(
        evidence=evidence,
        synthesis=synthesis,
        validated_claim_ids=("claim-v9",),
        source_availability=availability,
        case_id="case-v9",
        trace_id="trace-v9",
    )
    reversed_closure = build_evaluator_citation_closure(
        evidence=tuple(reversed(evidence)),
        synthesis=synthesis,
        validated_claim_ids=("claim-v9",),
        source_availability=SourceAvailabilitySet(sources=tuple(reversed(availability.sources))),
        case_id="case-v9",
        trace_id="trace-v9",
    )
    assert closure == reversed_closure
    assert closure.all_synthesis_claims_validated is True
    assert closure.all_admitted_evidence_covered is True
    assert closure.validated_evidence_ids == tuple(sorted(item.evidence_id for item in evidence))
    assert closure.claim_citations[0].evidence_ids == closure.validated_evidence_ids


def test_incomplete_semantic_claim_selection_cannot_close_admitted_catalog() -> None:
    evidence, availability = _case()
    claims = tuple(
        AgentClaim(
            claim_id=f"claim-{index}",
            statement="An admitted record supports the hypothesis.",
            relation=ClaimRelation.SUPPORTS_HYPOTHESIS,
            evidence_ids=(item.evidence_id,),
        )
        for index, item in enumerate(evidence[:2])
    )
    closure = build_evaluator_citation_closure(
        evidence=evidence,
        synthesis=_synthesis(evidence, *claims),
        validated_claim_ids=(claims[0].claim_id,),
        source_availability=availability,
    )
    assert closure.all_synthesis_claims_validated is False
    assert closure.all_admitted_evidence_covered is False


def test_relation_overlap_is_not_a_valid_citation_closure() -> None:
    evidence, availability = _case()
    evidence_id = evidence[0].evidence_id
    synthesis = _synthesis(
        evidence,
        AgentClaim(
            claim_id="supporting",
            statement="The record supports the hypothesis.",
            relation=ClaimRelation.SUPPORTS_HYPOTHESIS,
            evidence_ids=(evidence_id,),
        ),
        AgentClaim(
            claim_id="contradicting",
            statement="The record contradicts the hypothesis.",
            relation=ClaimRelation.CONTRADICTS_HYPOTHESIS,
            evidence_ids=(evidence_id,),
        ),
    )
    closure = build_evaluator_citation_closure(
        evidence=evidence,
        synthesis=synthesis,
        validated_claim_ids=("contradicting", "supporting"),
        source_availability=availability,
    )
    assert closure.relation_valid is False
    assert closure.all_admitted_evidence_covered is False


@pytest.mark.parametrize("kind", ("unknown_claim", "cross_case", "tampered", "knowledge_only"))
def test_citation_closure_rejects_untrusted_joins(kind: str) -> None:
    evidence, availability = _case()
    claim = AgentClaim(
        claim_id="claim-v9",
        statement="The record supports the hypothesis.",
        relation=ClaimRelation.SUPPORTS_HYPOTHESIS,
        evidence_ids=(evidence[0].evidence_id,),
    )
    synthesis = _synthesis(evidence, claim)
    bad_evidence = evidence
    bad_availability = availability
    claim_ids = ("missing-claim",)
    if kind == "cross_case":
        bad_evidence = (evidence[0].model_copy(update={"case_id": "other"}),) + evidence[1:]
        claim_ids = (claim.claim_id,)
    elif kind == "tampered":
        bad_evidence = (evidence[0].model_copy(update={"content_digest": "0" * 64}),) + evidence[1:]
        claim_ids = (claim.claim_id,)
    elif kind == "knowledge_only":
        bad_evidence = (
            evidence[0].model_copy(update={"source_type": EvidenceSourceType.KNOWLEDGE_BASE}),
        ) + evidence[1:]
        claim_ids = (claim.claim_id,)
    with pytest.raises(AgentValidationError):
        build_evaluator_citation_closure(
            evidence=bad_evidence,
            synthesis=synthesis,
            validated_claim_ids=claim_ids,
            source_availability=bad_availability,
            case_id="case-v9",
            trace_id="trace-v9",
        )


def test_unavailable_authoritative_source_is_non_promotable_closure() -> None:
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
    closure = build_evaluator_citation_closure(
        evidence=admitted,
        synthesis=SynthesisResult(
            selected_hypothesis=HypothesisType.RETRYABLE_MESSAGE,
            conclusion=HypothesisConclusion.NEEDS_EVIDENCE,
            confidence_band=ConfidenceBand.LOW,
        ),
        validated_claim_ids=(),
        source_availability=unavailable,
        case_id="case-v9",
        trace_id="trace-v9",
    )
    assert closure.availability_valid is False
    assert closure.all_admitted_evidence_covered is False
    assert closure.reason_code == "AUTHORITATIVE_SOURCE_UNAVAILABLE"


def test_scripted_harness_persists_closure_into_assessment_trace_and_ledger(tmp_path: Path) -> None:
    enterprise = SyntheticEnterprise.seed_from_fixture(tmp_path / "enterprise.sqlite", FIXTURE)
    store = SQLiteCaseStore(tmp_path / "case.sqlite")
    _case, evidence = DiscrepancyDetector(
        enterprise,
        store,
        ManualClock(datetime(2026, 8, 26, tzinfo=UTC)),
    ).detect(case_id="case-v9-run", trace_id="trace-v9-run", fixture_path=FIXTURE)
    availability = source_availability_from_genesis(store.get_genesis("case-v9-run"), evidence)
    run = AgentHarness(
        model_factory=ScriptedStrandsFactory(),
        knowledge=LocalKnowledgeRepository(ROOT / "fixtures/knowledge"),
        source_availability=availability,
    ).run(case_id="case-v9-run", trace_id="trace-v9-run", evidence=evidence)
    assert run.evaluator_citation_closure.schema_version == "evaluator-citation-closure/v1"
    assert run.evaluator_source_coverage.schema_version == "evaluator-source-coverage/v2"
    assert run.evaluator_source_coverage.citation_closure == run.evaluator_citation_closure
    assert run.assessment.evaluation.citation_closure is not None
    assert run.trace.citation_closure is not None
    assert run.coverage_ledger.evaluator_citation_closure == run.evaluator_citation_closure
    assert run.public()["evaluator_citation_closure"] == run.evaluator_citation_closure.model_dump(
        mode="json"
    )
