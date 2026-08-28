from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from the_missing_20.adapters.clocks import ManualClock
from the_missing_20.adapters.local_knowledge import LocalKnowledgeRepository
from the_missing_20.adapters.sqlite_case_store import SQLiteCaseStore
from the_missing_20.adapters.strands_models import ScriptedStrandsFactory
from the_missing_20.adapters.synthetic_enterprise import SyntheticEnterprise
from the_missing_20.agents import harness as harness_module
from the_missing_20.agents.harness import AgentHarness
from the_missing_20.agents.investigators import run_investigator as original_run_investigator
from the_missing_20.agents.schemas import (
    REQUIRED_AUTHORITATIVE_SOURCES,
    InvestigatorID,
    SourceAvailability,
    SourceAvailabilitySet,
)
from the_missing_20.agents.validation import AgentStageFailure
from the_missing_20.application.detector import DiscrepancyDetector
from the_missing_20.domain.enterprise import EvidenceReadStatus
from the_missing_20.evaluation import agent_golden_runner as golden_module
from the_missing_20.evaluation.agent_golden_runner import AgentGoldenRunner
from the_missing_20.ports.agent_model import AgentBudget, AgentBudgetLedger, AgentStage

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "fixtures/scenarios/retryable-document-lock.json"


@dataclass
class _FakeBedrockFactory:
    ledger: AgentBudgetLedger
    config: SimpleNamespace


def _all_available() -> SourceAvailabilitySet:
    return SourceAvailabilitySet(
        sources=tuple(
            SourceAvailability(source_type=source, status=EvidenceReadStatus.AVAILABLE)
            for source in REQUIRED_AUTHORITATIVE_SOURCES
        )
    )


def _case_evidence(tmp_path: Path, *, suffix: str) -> tuple[Any, ...]:
    enterprise = SyntheticEnterprise.seed_from_fixture(
        tmp_path / f"enterprise-{suffix}.sqlite", FIXTURE
    )
    store = SQLiteCaseStore(tmp_path / f"case-{suffix}.sqlite")
    _case, evidence = DiscrepancyDetector(
        enterprise,
        store,
        ManualClock(datetime(2026, 8, 26, tzinfo=UTC)),
    ).detect(
        case_id=f"case-failure-{suffix}",
        trace_id=f"trace-failure-{suffix}",
        fixture_path=FIXTURE,
    )
    return evidence


def _install_generic_failure(monkeypatch: pytest.MonkeyPatch, stage: AgentStage) -> None:
    async def fail(**_kwargs: Any) -> Any:
        raise RuntimeError("MODEL_PROSE_SECRET case-failure:warehouse /local/path")

    if stage in {
        AgentStage.RETRYABLE_INVESTIGATOR,
        AgentStage.SHORT_SHIPMENT_INVESTIGATOR,
        AgentStage.DUPLICATE_POSTING_INVESTIGATOR,
    }:
        target_role = {
            AgentStage.RETRYABLE_INVESTIGATOR: InvestigatorID.RETRYABLE_MESSAGE,
            AgentStage.SHORT_SHIPMENT_INVESTIGATOR: InvestigatorID.SHORT_SHIPMENT,
            AgentStage.DUPLICATE_POSTING_INVESTIGATOR: InvestigatorID.DUPLICATE_POSTING,
        }[stage]

        async def fail_investigator(**kwargs: Any) -> Any:
            if kwargs["role"] is target_role:
                return await fail()
            return await original_run_investigator(**kwargs)

        monkeypatch.setattr(harness_module, "run_investigator", fail_investigator)
    elif stage is AgentStage.SYNTHESIS:
        monkeypatch.setattr(harness_module, "run_synthesis", fail)
    else:
        monkeypatch.setattr(harness_module, "run_evaluator", fail)


@pytest.mark.parametrize(
    ("stage", "role"),
    (
        (AgentStage.RETRYABLE_INVESTIGATOR, InvestigatorID.RETRYABLE_MESSAGE.value),
        (AgentStage.SHORT_SHIPMENT_INVESTIGATOR, InvestigatorID.SHORT_SHIPMENT.value),
        (AgentStage.DUPLICATE_POSTING_INVESTIGATOR, InvestigatorID.DUPLICATE_POSTING.value),
        (AgentStage.SYNTHESIS, None),
        (AgentStage.EVALUATOR, None),
    ),
)
def test_stage_failures_are_redacted_and_never_promoted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage: AgentStage,
    role: str | None,
) -> None:
    evidence = _case_evidence(tmp_path, suffix=stage.value)
    _install_generic_failure(monkeypatch, stage)
    harness = AgentHarness(
        model_factory=ScriptedStrandsFactory(),
        knowledge=LocalKnowledgeRepository(ROOT / "fixtures/knowledge"),
        source_availability=_all_available(),
    )

    with pytest.raises(AgentStageFailure) as failure_info:
        harness.run(
            case_id=f"case-failure-{stage.value}",
            trace_id=f"trace-failure-{stage.value}",
            evidence=evidence,
        )
    failure = failure_info.value
    assert failure.stage == stage.value
    assert failure.role == role
    assert failure.validator_code == "RUNTIME_ERROR"

    budget = AgentBudget(
        max_requests=40,
        max_input_tokens=400_000,
        max_output_tokens=62_040,
    )
    ledger = AgentBudgetLedger(budget)
    ledger.reserve_request(input_token_upper_bound=2_000, output_token_upper_bound=1_000)
    ledger.record_usage(input_tokens=1234, output_tokens=321)
    factory = _FakeBedrockFactory(
        ledger=ledger,
        config=SimpleNamespace(model_id="us.amazon.nova-pro-v1:0"),
    )
    runner = object.__new__(AgentGoldenRunner)
    runner.repository_root = tmp_path
    monkeypatch.setattr(golden_module, "_agent_profile_manifest", lambda *_args: object())

    def raise_stage_failure(*_args: Any, **_kwargs: Any) -> Any:
        raise failure

    monkeypatch.setattr(runner, "run_profile", raise_stage_failure)
    with pytest.raises(AgentStageFailure):
        runner.run_bedrock(factory)

    manifest_path = tmp_path / golden_module.BEDROCK_FAILURE_MANIFEST
    pass_path = tmp_path / golden_module.BEDROCK_ARTIFACT
    assert manifest_path.is_file()
    assert not pass_path.exists()
    assert manifest_path.name == "bedrock-failure-manifest-v5.json"
    assert (tmp_path / golden_module.BEDROCK_CLAIM).is_file()
    assert not (tmp_path / "artifacts/agent/bedrock-failure-manifest-v2.json").exists()
    assert not (tmp_path / "artifacts/agent/bedrock-failure-manifest-v3.json").exists()
    assert runner._bedrock_proof()["status"] == "NOT_RUN"

    raw = manifest_path.read_text(encoding="utf-8")
    manifest = json.loads(raw)
    assert manifest["schema_version"] == "agent-failure/v5"
    assert manifest["attempt_claim"]["agent_contract_version"] == "agent-contract/v9"
    assert manifest["attempt_claim"]["envelope_version"] == "agent-protocol-envelope/v1"
    assert manifest["profile_key"] == golden_module.PROFILE_KEYS[0]
    assert manifest["assigned_stage"] == stage.value
    assert manifest["assigned_role"] == role
    assert manifest["validator_code"] == "RUNTIME_ERROR"
    assert manifest["request_count"] == 1
    assert manifest["input_tokens"] == 1234
    assert manifest["output_tokens"] == 321
    assert manifest["request_cap"] == 40
    assert manifest["input_token_cap"] == 400_000
    assert manifest["output_token_cap"] == 62_040
    assert manifest["estimated_cost_usd"] == pytest.approx(0.0020144)
    for forbidden in (
        "MODEL_PROSE_SECRET",
        "case-failure:warehouse",
        "/local/path",
        str(tmp_path),
        "failed-message",
    ):
        assert forbidden not in raw
