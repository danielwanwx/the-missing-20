from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest

from the_missing_20.adapters.clocks import ManualClock
from the_missing_20.adapters.local_knowledge import LocalKnowledgeRepository
from the_missing_20.adapters.sqlite_case_store import SQLiteCaseStore
from the_missing_20.adapters.strands_models import ScriptedStrandsFactory
from the_missing_20.adapters.synthetic_enterprise import SyntheticEnterprise
from the_missing_20.agents.harness import (
    AgentHarness,
    HarnessRun,
    _assert_fixed_investigator_runs,
)
from the_missing_20.agents.investigators import InvestigatorRun, run_investigator
from the_missing_20.agents.policy import (
    NO_ACTION_COVERAGE_INCOMPLETE,
    NO_ACTION_EVALUATOR_REJECTED,
    NO_ACTION_SELECTED_UNSUPPORTED,
    NO_ACTION_UNRESOLVED_CONTRADICTING_CLAIM,
    ActionRecommendationPolicy,
)
from the_missing_20.agents.schemas import (
    REQUIRED_AUTHORITATIVE_SOURCES,
    AgentClaim,
    ClaimRelation,
    InvestigatorID,
    SourceAvailability,
    SourceAvailabilitySet,
)
from the_missing_20.agents.tools import ToolAudit, ToolScope
from the_missing_20.agents.validation import AgentValidationError
from the_missing_20.application.detector import DiscrepancyDetector
from the_missing_20.domain.enterprise import EvidenceReadStatus
from the_missing_20.domain.models import EvidenceItem, HypothesisConclusion, HypothesisType
from the_missing_20.ports.agent_model import AgentStage

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "fixtures/scenarios/retryable-document-lock.json"


def _run(tmp_path: Path) -> tuple[HarnessRun, tuple[EvidenceItem, ...]]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    enterprise = SyntheticEnterprise.seed_from_fixture(tmp_path / "enterprise.sqlite", FIXTURE)
    store = SQLiteCaseStore(tmp_path / "case.sqlite")
    _case, evidence = DiscrepancyDetector(
        enterprise,
        store,
        ManualClock(datetime(2026, 8, 26, tzinfo=UTC)),
    ).detect(
        case_id="case-agent-policy",
        trace_id="trace-agent-policy",
        fixture_path=FIXTURE,
    )
    availability = SourceAvailabilitySet(
        sources=tuple(
            SourceAvailability(source_type=source, status=EvidenceReadStatus.AVAILABLE)
            for source in REQUIRED_AUTHORITATIVE_SOURCES
        )
    )
    result = AgentHarness(
        model_factory=ScriptedStrandsFactory(),
        knowledge=LocalKnowledgeRepository(ROOT / "fixtures/knowledge"),
        source_availability=availability,
    ).run(
        case_id="case-agent-policy",
        trace_id="trace-agent-policy",
        evidence=evidence,
    )
    return result, evidence


def test_policy_recommends_only_the_accepted_retryable_path(tmp_path: Path) -> None:
    result, _evidence = _run(tmp_path)

    assert result.action_recommendation.action is not None
    assert result.action_recommendation.reason_code == "RECOMMEND_RESTART_RECEIPT_MESSAGE"
    assert result.coverage_ledger.complete_coverage is True


def test_complete_evidence_without_selected_reads_cannot_recommend(tmp_path: Path) -> None:
    result, evidence = _run(tmp_path)

    # Reconstructing from public stage data is intentionally impossible; use the
    # admitted IDs and ledger source identities to prove the policy's read gate.
    ledger = result.coverage_ledger.model_copy(
        update={
            "sources": tuple(
                source.model_copy(update={"selected_investigator_read": False})
                for source in result.coverage_ledger.sources
            ),
            "complete_coverage": False,
        }
    )
    recommendation = ActionRecommendationPolicy.evaluate(
        synthesis=result.synthesis,
        investigators=result.investigators,
        evaluator=result.evaluation,
        evidence=evidence,
        ledger=ledger,
    )
    assert recommendation.action is None
    assert recommendation.reason_code == NO_ACTION_COVERAGE_INCOMPLETE


def test_policy_does_not_upgrade_rejected_selected_investigator(tmp_path: Path) -> None:
    result, evidence = _run(tmp_path)
    selected = result.investigators[0].model_copy(
        update={"conclusion": HypothesisConclusion.REJECTED}
    )
    investigators = (selected, *result.investigators[1:])
    ledger = result.coverage_ledger.model_copy(
        update={"selected_result_supported": False, "complete_coverage": False}
    )
    recommendation = ActionRecommendationPolicy.evaluate(
        synthesis=result.synthesis,
        investigators=investigators,
        evaluator=result.evaluation,
        evidence=evidence,
        ledger=ledger,
    )

    assert recommendation.action is None
    assert recommendation.reason_code == NO_ACTION_SELECTED_UNSUPPORTED


def test_policy_rejects_evaluator_not_accepting_a_supported_diagnosis(tmp_path: Path) -> None:
    result, evidence = _run(tmp_path)
    evaluator = result.evaluation.model_copy(
        update={"decision": "REJECT", "failed_invariants": ("manual_review",)}
    )
    recommendation = ActionRecommendationPolicy.evaluate(
        synthesis=result.synthesis,
        investigators=result.investigators,
        evaluator=evaluator,
        evidence=evidence,
        ledger=result.coverage_ledger,
    )

    assert recommendation.action is None
    assert recommendation.reason_code == NO_ACTION_EVALUATOR_REJECTED


def test_selected_path_contradicting_claim_blocks_action_even_when_record_id_overlaps(
    tmp_path: Path,
) -> None:
    result, evidence = _run(tmp_path)
    selected_claim = AgentClaim(
        claim_id="selected-contradiction",
        statement="A second fact in the same record contradicts the hypothesis.",
        relation=ClaimRelation.CONTRADICTS_HYPOTHESIS,
        evidence_ids=(evidence[0].evidence_id,),
    )
    synthesis = result.synthesis.model_copy(
        update={
            "factual_claims": (*result.synthesis.factual_claims, selected_claim),
        }
    )
    selected = result.investigators[0].model_copy(
        update={
            "factual_claims": (*result.investigators[0].factual_claims, selected_claim),
        }
    )
    ledger = result.coverage_ledger.model_copy(
        update={"conflict_free": False, "unresolved_conflict": True, "complete_coverage": False}
    )
    recommendation = ActionRecommendationPolicy.evaluate(
        synthesis=synthesis,
        investigators=(selected, *result.investigators[1:]),
        evaluator=result.evaluation,
        evidence=evidence,
        ledger=ledger,
    )

    assert recommendation.action is None
    assert recommendation.reason_code == NO_ACTION_UNRESOLVED_CONTRADICTING_CLAIM


def test_run_investigator_rejects_structured_output_from_another_role() -> None:
    knowledge = LocalKnowledgeRepository(ROOT / "fixtures/knowledge")
    scope = ToolScope(
        case_id="case-role-check",
        trace_id="trace-role-check",
        admitted_evidence=(),
        allowed_evidence_ids=frozenset(),
        knowledge=knowledge,
        knowledge_version=knowledge.version,
    )
    availability = SourceAvailabilitySet(
        sources=tuple(
            SourceAvailability(
                source_type=source,
                status=EvidenceReadStatus.UNAVAILABLE,
                unavailability_reason="SOURCE_UNAVAILABLE",
            )
            for source in REQUIRED_AUTHORITATIVE_SOURCES
        )
    )
    impersonating_payload = {
        "investigator_id": InvestigatorID.SHORT_SHIPMENT.value,
        "hypothesis_type": HypothesisType.GENUINE_SHORT_SHIPMENT.value,
        "conclusion": "REJECTED",
        "confidence_band": "LOW",
        "factual_claims": [],
    }

    with pytest.raises(AgentValidationError, match="does not match assigned role"):
        asyncio.run(
            run_investigator(
                role=InvestigatorID.RETRYABLE_MESSAGE,
                stage=AgentStage.RETRYABLE_INVESTIGATOR,
                model_factory=ScriptedStrandsFactory(),
                output_payload=impersonating_payload,
                tool_plan=(),
                scope=scope,
                source_availability=availability,
            )
        )


@pytest.mark.parametrize("indexes", ((0, 0, 2), (1, 2, 0)))
def test_harness_rejects_duplicate_or_cyclic_investigator_roles(
    tmp_path: Path,
    indexes: tuple[int, int, int],
) -> None:
    result, _evidence = _run(tmp_path)
    runs = tuple(
        InvestigatorRun(
            result=result.investigators[index],
            model_result=None,
            audit=ToolAudit(),
            read_evidence_ids=result.investigator_read_evidence_ids[index],
        )
        for index in indexes
    )
    roles = (
        (InvestigatorID.RETRYABLE_MESSAGE, AgentStage.RETRYABLE_INVESTIGATOR),
        (InvestigatorID.SHORT_SHIPMENT, AgentStage.SHORT_SHIPMENT_INVESTIGATOR),
        (InvestigatorID.DUPLICATE_POSTING, AgentStage.DUPLICATE_POSTING_INVESTIGATOR),
    )

    with pytest.raises(AgentValidationError, match="fixed investigator role|assigned stage"):
        _assert_fixed_investigator_runs(runs, roles)
