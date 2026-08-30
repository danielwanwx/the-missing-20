from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

import the_missing_20.agents.harness as harness_module
from the_missing_20.adapters.clocks import ManualClock
from the_missing_20.adapters.local_knowledge import LocalKnowledgeRepository
from the_missing_20.adapters.sqlite_case_store import SQLiteCaseStore
from the_missing_20.adapters.strands_models import ScriptedStrandsFactory
from the_missing_20.adapters.synthetic_enterprise import SyntheticEnterprise
from the_missing_20.agents.harness import AdvisoryStageResult, AgentHarness
from the_missing_20.agents.schemas import SourceAvailabilitySet
from the_missing_20.application.detector import DiscrepancyDetector
from the_missing_20.authority_b.advisory import advisory_from_harness_run
from the_missing_20.authority_b.classifier import classify_operational_state
from the_missing_20.authority_b.models import AdvisoryStatus
from the_missing_20.authority_b.workflow import run_authority_b
from the_missing_20.domain.models import Case, EvidenceItem
from the_missing_20.evaluation.agent_golden_runner import source_availability_from_genesis
from the_missing_20.experiment.events import PublicEventType
from the_missing_20.experiment.session import ExperimentSession

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "fixtures/scenarios/retryable-document-lock.json"


def _detected(tmp_path: Path) -> tuple[Case, tuple[EvidenceItem, ...], SourceAvailabilitySet]:
    enterprise = SyntheticEnterprise.seed_from_fixture(tmp_path / "enterprise.sqlite", FIXTURE)
    store = SQLiteCaseStore(tmp_path / "case.sqlite")
    case, evidence = DiscrepancyDetector(
        enterprise,
        store,
        ManualClock(datetime(2026, 8, 26, tzinfo=UTC)),
    ).detect(case_id="rebaseline-case", trace_id="rebaseline-trace", fixture_path=FIXTURE)
    availability = source_availability_from_genesis(store.get_genesis(case.case_id), evidence)
    return case, evidence, availability


def test_accepted_partial_closure_is_advisory_only_and_never_fills_omitted_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case, evidence, availability = _detected(tmp_path)
    outputs, synthesis, evaluator = harness_module._profile_outputs(
        evidence=evidence,
        trace_id="rebaseline-trace",
        source_availability=availability,
    )
    original_ids = tuple(synthesis["factual_claims"][0]["evidence_ids"])
    synthesis["factual_claims"][0]["evidence_ids"] = list(original_ids[:-1])
    monkeypatch.setattr(
        harness_module,
        "_profile_outputs",
        lambda **_kwargs: (outputs, synthesis, evaluator),
    )

    result = AgentHarness(
        model_factory=ScriptedStrandsFactory(),
        knowledge=LocalKnowledgeRepository(ROOT / "fixtures/knowledge"),
        source_availability=availability,
    ).run(case_id=case.case_id, trace_id="rebaseline-trace", evidence=evidence)

    assert isinstance(result, AdvisoryStageResult)
    assert result.status == AdvisoryStatus.PARTIAL.value
    assert result.warnings == ("AI_CITATION_CLOSURE_INCOMPLETE",)
    covered_ids = set(result.evaluator_citation_closure.validated_evidence_ids)
    admitted_ids = {item.evidence_id for item in evidence}
    assert len(covered_ids) == 4
    assert covered_ids < admitted_ids
    assert result.ai_coverage["coverage"] == "4/5"
    assert set(result.ai_coverage["omitted_evidence_ids"]) == admitted_ids - covered_ids
    assert set(result.public()["synthesis"]["factual_claims"][0]["evidence_ids"]) == covered_ids
    assert set(result.public()["authoritative_catalog"]["evidence_ids"]) == admitted_ids
    assert result.trace.coverage_ledger is None
    assert result.trace.action_recommendation is None

    advisory = advisory_from_harness_run(
        result,
        case_id=case.case_id,
        trace_id="rebaseline-trace",
        now=datetime(2026, 8, 26, tzinfo=UTC),
        admitted_evidence_ids=admitted_ids,
    )
    assert advisory.status is AdvisoryStatus.PARTIAL
    assert "AI_CITATION_CLOSURE_INCOMPLETE" in advisory.warnings


def test_authority_b_decision_is_identical_when_advisory_is_partial(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case, evidence, availability = _detected(tmp_path)
    outputs, synthesis, evaluator = harness_module._profile_outputs(
        evidence=evidence,
        trace_id="rebaseline-trace",
        source_availability=availability,
    )
    synthesis["factual_claims"][0]["evidence_ids"] = synthesis["factual_claims"][0][
        "evidence_ids"
    ][:-1]
    monkeypatch.setattr(
        harness_module,
        "_profile_outputs",
        lambda **_kwargs: (outputs, synthesis, evaluator),
    )
    partial = AgentHarness(
        model_factory=ScriptedStrandsFactory(),
        knowledge=LocalKnowledgeRepository(ROOT / "fixtures/knowledge"),
        source_availability=availability,
    ).run(case_id=case.case_id, trace_id="rebaseline-trace", evidence=evidence)
    assert isinstance(partial, AdvisoryStageResult)

    expected = classify_operational_state(
        evidence,
        case=case,
        trace_id="rebaseline-trace",
        source_availability=availability,
    )
    joined = run_authority_b(
        case=case,
        evidence=evidence,
        source_availability=availability,
        advisory_execute=lambda: partial,
    )
    assert joined.operational_decision == expected
    assert joined.advisory.status is AdvisoryStatus.PARTIAL


def test_provider_failure_does_not_block_deterministic_recovery_preparation(
    tmp_path: Path,
) -> None:
    session = ExperimentSession(ROOT, data_directory=tmp_path / "session")
    session._append(
        PublicEventType.PROVIDER_DEGRADED,
        actor="orchestrator",
        status="DEGRADED",
        case_version=session._current_case_version(),
        correlation_id=session.trace_id,
        idempotency_key="test:provider-degraded",
        payload={"provider": "agentcore", "error_code": "ADVISORY_PROVIDER_FAILURE"},
    )

    actions = {item["id"]: item for item in session._case_console_actions()}
    assert actions["prepare_recovery"]["enabled"] is True
    prepared = session.prepare_decision(
        "restart_receipt_message",
        idempotency_key="test:prepare-after-provider-failure",
    )
    assert prepared["approval"]["status"] == "OPEN"
    assert session.snapshot()["advisory"]["status"] == "DEGRADED"
