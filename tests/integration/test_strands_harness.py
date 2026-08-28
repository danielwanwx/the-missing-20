from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from the_missing_20.adapters.clocks import ManualClock
from the_missing_20.adapters.local_knowledge import LocalKnowledgeRepository
from the_missing_20.adapters.sqlite_case_store import SQLiteCaseStore
from the_missing_20.adapters.strands_models import ScriptedStrandsFactory
from the_missing_20.adapters.synthetic_enterprise import SyntheticEnterprise
from the_missing_20.agents.harness import AgentHarness, HarnessRun
from the_missing_20.agents.prompts import PromptSet
from the_missing_20.agents.schemas import (
    REQUIRED_AUTHORITATIVE_SOURCES,
    SourceAvailability,
    SourceAvailabilitySet,
)
from the_missing_20.application.detector import DiscrepancyDetector
from the_missing_20.domain.enterprise import EvidenceReadStatus

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "fixtures/scenarios/retryable-document-lock.json"


def _run(tmp_path: Path) -> HarnessRun:
    tmp_path.mkdir(parents=True, exist_ok=True)
    enterprise = SyntheticEnterprise.seed_from_fixture(tmp_path / "enterprise.sqlite", FIXTURE)
    store = SQLiteCaseStore(tmp_path / "case.sqlite")
    _case, evidence = DiscrepancyDetector(
        enterprise,
        store,
        ManualClock(datetime(2026, 8, 26, tzinfo=UTC)),
    ).detect(
        case_id="case-agent-integration",
        trace_id="trace-agent-integration",
        fixture_path=FIXTURE,
    )
    return AgentHarness(
        model_factory=ScriptedStrandsFactory(),
        knowledge=LocalKnowledgeRepository(ROOT / "fixtures/knowledge"),
        source_availability=SourceAvailabilitySet(
            sources=tuple(
                SourceAvailability(source_type=source, status=EvidenceReadStatus.AVAILABLE)
                for source in REQUIRED_AUTHORITATIVE_SOURCES
            )
        ),
    ).run(
        case_id="case-agent-integration",
        trace_id="trace-agent-integration",
        evidence=evidence,
    )


def test_scripted_provider_drives_real_strands_workflow(tmp_path: Path) -> None:
    result = _run(tmp_path)

    assert result.assessment.decision.value == "RECOMMEND_RECEIPT_RESTART"
    assert len(result.investigators) == 3
    assert [stage.stage for stage in result.trace.stages] == [
        "retryable_investigator",
        "short_shipment_investigator",
        "duplicate_posting_investigator",
        "synthesis",
        "evaluator",
    ]
    assert all(
        set(stage.tool_calls).issubset({"read_admitted_evidence", "search_synthetic_knowledge"})
        for stage in result.trace.stages
    )
    assert result.trace.prompt_digest == PromptSet.load(ROOT).digest
    assert "supporting_evidence_ids" not in result.investigators[0].model_dump(mode="json")
    assert "missing_evidence_sources" not in result.investigators[0].model_dump(mode="json")
    assert "supporting_evidence_ids" not in result.synthesis.model_dump(mode="json")
    assert "missing_evidence_sources" not in result.synthesis.model_dump(mode="json")
    assert result.public()["investigators"][0]["supporting_evidence_ids"] == sorted(
        result.investigators[0].factual_claims[0].evidence_ids
    )
    assert result.public()["investigators"][0]["knowledge_citations"] == [
        {
            "knowledge_id": "retryable-document-lock",
            "version": "knowledge-v1",
            "allowed_use": "ERROR_DEFINITION_ONLY",
            "content_digest": "fcf4e80a0780dd07421f9b8e1a8168d2168fa94829f96bcc89a4ab2440ac14d4",
        }
    ]
    assert result.public()["synthesis"]["supporting_evidence_ids"] == sorted(
        result.synthesis.factual_claims[0].evidence_ids
    )
    assert result.public()["investigators"][0]["missing_evidence_sources"] == []
    assert result.public()["synthesis"]["missing_evidence_sources"] == []
    assert result.trace.agent_contract_version == "agent-contract/v9"
    assert result.trace.prompt_version == "agent-v5"
    assert result.trace.harness_version == "harness-v6"
    assert result.trace.evaluator_version == "evaluator-v4"
    assert result.protocol.evaluator_protocol_version == "evaluator-protocol/v3"
    assert result.evaluator_citation_closure.all_admitted_evidence_covered is True
    assert result.evaluator_source_coverage.schema_version == "evaluator-source-coverage/v2"
    assert result.evaluator_source_coverage.all_required_sources_validated is True
    assert result.investigators[0].factual_claims[0].relation.value == "SUPPORTS_HYPOTHESIS"
    assert result.public()["synthesis"]["preserved_dissent"]
    assert result.action_recommendation.action is not None
    assert result.action_recommendation.action.value == "restart_receipt_message"
    assert result.coverage_ledger.complete_coverage is True
    assert result.public()["action_recommendation"]["action"] == "restart_receipt_message"
    assert tuple(result.trace.knowledge_citations) == result.investigator_knowledge_citations[0]
    assert result.trace.stages[0].knowledge_citations == result.investigator_knowledge_citations[0]
    expected_read_ids = tuple(sorted(result.assessment.admitted_evidence_ids))
    assert all(stage.read_evidence_ids == expected_read_ids for stage in result.trace.stages[:3])
    assert result.trace.public()["stages"][0]["read_evidence_ids"] == list(expected_read_ids)
    assert "excerpt" not in json.dumps(result.trace.public(), sort_keys=True)
    assert result.trace.request_count == sum(stage.request_count for stage in result.trace.stages)
    assert result.trace.input_tokens == sum(stage.input_tokens for stage in result.trace.stages)
    assert result.trace.output_tokens == sum(stage.output_tokens for stage in result.trace.stages)


def test_normalized_scripted_runs_are_byte_identical(tmp_path: Path) -> None:
    first = _run(tmp_path / "first")
    second = _run(tmp_path / "second")

    assert json.dumps(first.public(), sort_keys=True, separators=(",", ":")) == json.dumps(
        second.public(), sort_keys=True, separators=(",", ":")
    )
