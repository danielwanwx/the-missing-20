from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from the_missing_20.adapters.clocks import ManualClock
from the_missing_20.adapters.local_knowledge import LocalKnowledgeRepository
from the_missing_20.adapters.sqlite_case_store import SQLiteCaseStore
from the_missing_20.adapters.strands_models import ScriptedStrandsFactory
from the_missing_20.adapters.synthetic_enterprise import SyntheticEnterprise
from the_missing_20.agents.harness import AgentHarness
from the_missing_20.agents.schemas import (
    REQUIRED_AUTHORITATIVE_SOURCES,
    AgentClaim,
    ClaimRelation,
    InvestigatorID,
    InvestigatorResult,
    SourceAvailability,
    SourceAvailabilitySet,
)
from the_missing_20.agents.tools import (
    ToolAudit,
    ToolScope,
    derive_knowledge_citations,
    derive_read_evidence_ids,
    make_search_synthetic_knowledge_tool,
)
from the_missing_20.agents.validation import AgentEvidenceValidator, AgentValidationError
from the_missing_20.application.detector import DiscrepancyDetector
from the_missing_20.domain.enterprise import EvidenceReadStatus
from the_missing_20.domain.models import (
    ConfidenceBand,
    EvidenceItem,
    EvidenceSourceType,
    HypothesisConclusion,
    HypothesisType,
)
from the_missing_20.evaluation.agent_golden_runner import source_availability_from_genesis

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "fixtures/scenarios/retryable-document-lock.json"


def _evidence(
    tmp_path: Path,
    *,
    material_unavailable: bool = False,
) -> tuple[EvidenceItem, ...]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    enterprise = SyntheticEnterprise.seed_from_fixture(tmp_path / "enterprise.sqlite", FIXTURE)
    if material_unavailable:
        enterprise.set_material_document_source_unavailable("SOURCE_UNAVAILABLE")
    store = SQLiteCaseStore(tmp_path / "case.sqlite")
    clock = ManualClock(datetime(2026, 8, 26, tzinfo=UTC))
    _case, evidence = DiscrepancyDetector(enterprise, store, clock).detect(
        case_id="case-agent-validation",
        trace_id="trace-agent-validation",
        fixture_path=FIXTURE,
    )
    return evidence


def _availability(
    *,
    unavailable: frozenset[EvidenceSourceType] = frozenset(),
) -> SourceAvailabilitySet:
    return SourceAvailabilitySet(
        sources=tuple(
            SourceAvailability(
                source_type=source,
                status=(
                    EvidenceReadStatus.UNAVAILABLE
                    if source in unavailable
                    else EvidenceReadStatus.AVAILABLE
                ),
                unavailability_reason=("SOURCE_UNAVAILABLE" if source in unavailable else None),
            )
            for source in REQUIRED_AUTHORITATIVE_SOURCES
        )
    )


def test_content_digest_tampering_is_rejected(tmp_path: Path) -> None:
    evidence = _evidence(tmp_path)
    tampered = evidence[0].model_copy(
        update={"admitted_fields": {"tampered": True}},
    )
    validator = AgentEvidenceValidator(
        (tampered, *evidence[1:]),
        trace_id="trace-agent-validation",
        source_availability=_availability(),
    )

    with pytest.raises(AgentValidationError, match="digest"):
        validator.validate_investigator(
            InvestigatorResult(
                investigator_id=InvestigatorID.RETRYABLE_MESSAGE,
                hypothesis_type=HypothesisType.RETRYABLE_MESSAGE,
                conclusion=HypothesisConclusion.REJECTED,
                confidence_band=ConfidenceBand.LOW,
                factual_claims=(
                    AgentClaim(
                        claim_id="tampered-claim",
                        statement="The tampered record contradicts the hypothesis.",
                        relation=ClaimRelation.CONTRADICTS_HYPOTHESIS,
                        evidence_ids=(tampered.evidence_id,),
                    ),
                ),
            )
        )


def test_uncited_claim_is_rejected(tmp_path: Path) -> None:
    evidence = _evidence(tmp_path)
    knowledge = LocalKnowledgeRepository(ROOT / "fixtures/knowledge")
    harness = AgentHarness(
        model_factory=ScriptedStrandsFactory(),
        knowledge=knowledge,
        source_availability=_availability(),
    )
    result = harness.run(
        case_id="case-agent-validation",
        trace_id="trace-agent-validation",
        evidence=evidence,
    )
    invalid = result.investigators[0].model_copy(
        update={
            "factual_claims": (
                AgentClaim(
                    claim_id="unsupported",
                    statement="This claim has no supporting admitted record.",
                    relation=ClaimRelation.SUPPORTS_HYPOTHESIS,
                    evidence_ids=("case-agent-validation:not-admitted",),
                ),
            ),
        },
    )
    validator = AgentEvidenceValidator(
        evidence,
        trace_id="trace-agent-validation",
        source_availability=_availability(),
        knowledge=knowledge,
    )

    with pytest.raises(AgentValidationError, match="unadmitted"):
        validator.validate_investigator(invalid)


def test_unknown_knowledge_audit_fails_closed(tmp_path: Path) -> None:
    _evidence(tmp_path)
    knowledge = LocalKnowledgeRepository(ROOT / "fixtures/knowledge")
    audit = ToolAudit()
    audit.record(
        name="search_synthetic_knowledge",
        arguments={"query": "procedure", "version": knowledge.version},
        result_knowledge_records=(
            {
                "knowledge_id": "not-in-corpus",
                "version": knowledge.version,
                "allowed_use": "PROCEDURE_ONLY",
                "content_digest": "unknown",
            },
        ),
    )

    with pytest.raises(ValueError, match="unknown or stale"):
        derive_knowledge_citations((audit,), knowledge)


def _knowledge_row(
    knowledge: LocalKnowledgeRepository,
    knowledge_id: str,
    *,
    version: str | None = None,
    allowed_use: str | None = None,
    content_digest: str | None = None,
) -> dict[str, str]:
    record = knowledge.get(knowledge_id, knowledge.version)
    assert record is not None
    return {
        "knowledge_id": record.knowledge_id,
        "version": record.version if version is None else version,
        "allowed_use": record.allowed_use if allowed_use is None else allowed_use,
        "content_digest": record.content_digest if content_digest is None else content_digest,
    }


def test_successful_knowledge_searches_derive_sorted_unique_provenance() -> None:
    knowledge = LocalKnowledgeRepository(ROOT / "fixtures/knowledge")
    rows = (
        _knowledge_row(knowledge, "retryable-document-lock"),
        _knowledge_row(knowledge, "receipt-message-recovery"),
    )
    first = ToolAudit()
    first.record(
        name="search_synthetic_knowledge",
        arguments={"query": "retryable", "version": knowledge.version},
        result_knowledge_records=rows,
    )
    repeat = ToolAudit()
    repeat.record(
        name="search_synthetic_knowledge",
        arguments={"query": "recovery", "version": knowledge.version},
        result_knowledge_records=(rows[0],),
    )

    citations = derive_knowledge_citations((first, repeat), knowledge)

    assert [item.knowledge_id for item in citations] == [
        "receipt-message-recovery",
        "retryable-document-lock",
    ]
    assert all(item.content_digest for item in citations)
    assert all("excerpt" not in item.model_dump(mode="json") for item in citations)


def test_search_tool_audit_retains_only_exact_provenance_fields() -> None:
    knowledge = LocalKnowledgeRepository(ROOT / "fixtures/knowledge")
    audit = ToolAudit()
    scope = ToolScope(
        case_id="case-knowledge",
        trace_id="trace-knowledge",
        admitted_evidence=(),
        allowed_evidence_ids=frozenset(),
        knowledge=knowledge,
        knowledge_version=knowledge.version,
    )
    search = make_search_synthetic_knowledge_tool(scope, audit)

    result = search("retryable document lock", knowledge.version)

    assert result["results"][0]["excerpt"]
    records = audit.calls[0]["result_knowledge_records"]
    assert records and set(records[0]) == {
        "knowledge_id",
        "version",
        "allowed_use",
        "content_digest",
    }
    assert "excerpt" not in audit.calls[0]


def test_successful_evidence_reads_derive_unique_sorted_ids() -> None:
    audit = ToolAudit()
    audit.record(
        name="read_admitted_evidence",
        arguments={"evidence_id": "case-1:warehouse"},
        result_evidence_ids=("case-1:warehouse",),
    )
    audit.record(
        name="read_admitted_evidence",
        arguments={"evidence_id": "case-1:failed-message"},
        result_evidence_ids=("case-1:failed-message",),
    )
    audit.record(
        name="read_admitted_evidence",
        arguments={"evidence_id": "case-1:warehouse"},
        result_evidence_ids=("case-1:warehouse",),
    )

    assert derive_read_evidence_ids(audit) == (
        "case-1:failed-message",
        "case-1:warehouse",
    )


@pytest.mark.parametrize(
    "record_kwargs",
    [
        {
            "name": "read_admitted_evidence",
            "arguments": {"evidence_id": "case-1:warehouse"},
            "error_code": "EVIDENCE_NOT_FOUND",
        },
        {
            "name": "read_admitted_evidence",
            "arguments": {"evidence_id": "case-1:warehouse"},
            "result_evidence_ids": (),
        },
    ],
)
def test_error_or_malformed_evidence_read_audit_fails_closed(
    record_kwargs: dict[str, Any],
) -> None:
    audit = ToolAudit()
    audit.record(**record_kwargs)

    with pytest.raises(ValueError, match=r"evidence[- ]read"):
        derive_read_evidence_ids(audit)


def test_default_evidence_read_plan_covers_all_five_authoritative_sources(
    tmp_path: Path,
) -> None:
    from the_missing_20.agents.investigators import default_tool_plan

    evidence = _evidence(tmp_path)
    knowledge = LocalKnowledgeRepository(ROOT / "fixtures/knowledge")
    scope = ToolScope(
        case_id="case-agent-validation",
        trace_id="trace-agent-validation",
        admitted_evidence=evidence,
        allowed_evidence_ids=frozenset(item.evidence_id for item in evidence),
        knowledge=knowledge,
        knowledge_version=knowledge.version,
    )

    plan = default_tool_plan(scope)
    reads = tuple(
        item["arguments"]["evidence_id"]
        for item in plan
        if item["tool"] == "read_admitted_evidence"
    )
    assert len(reads) == len(REQUIRED_AUTHORITATIVE_SOURCES)
    assert set(reads) == {item.evidence_id for item in evidence}


def test_admitted_but_unread_investigator_citation_is_rejected(tmp_path: Path) -> None:
    evidence = _evidence(tmp_path)
    validator = AgentEvidenceValidator(
        evidence,
        trace_id="trace-agent-validation",
        source_availability=_availability(),
    )
    result = InvestigatorResult(
        investigator_id=InvestigatorID.RETRYABLE_MESSAGE,
        hypothesis_type=HypothesisType.RETRYABLE_MESSAGE,
        conclusion=HypothesisConclusion.REJECTED,
        confidence_band=ConfidenceBand.LOW,
        factual_claims=(
            AgentClaim(
                claim_id="unread-claim",
                statement="The admitted record contradicts the hypothesis.",
                relation=ClaimRelation.CONTRADICTS_HYPOTHESIS,
                evidence_ids=(evidence[0].evidence_id,),
            ),
        ),
    )

    with pytest.raises(AgentValidationError, match="was not successfully read"):
        validator.validate_investigator(result, read_evidence_ids=())


def test_zero_successful_knowledge_searches_derive_empty_provenance() -> None:
    knowledge = LocalKnowledgeRepository(ROOT / "fixtures/knowledge")

    assert derive_knowledge_citations(ToolAudit(), knowledge) == ()


def test_failed_knowledge_search_has_no_results_and_fails_closed() -> None:
    knowledge = LocalKnowledgeRepository(ROOT / "fixtures/knowledge")
    audit = ToolAudit()
    audit.record(
        name="search_synthetic_knowledge",
        arguments={"query": "retryable", "version": knowledge.version},
        error_code="TOOL_BUDGET_EXHAUSTED",
    )

    assert audit.calls[0]["result_knowledge_records"] == []
    with pytest.raises(ValueError, match="error-bearing"):
        derive_knowledge_citations(audit, knowledge)


@pytest.mark.parametrize(
    ("row_kwargs", "message"),
    [
        ({"version": "knowledge-v0"}, "unknown or stale"),
        ({"allowed_use": "PROCEDURE_ONLY"}, "frozen corpus"),
        ({"content_digest": "tampered"}, "frozen corpus"),
    ],
)
def test_stale_wrong_use_and_digest_tampering_fail_closed(
    row_kwargs: dict[str, str], message: str
) -> None:
    knowledge = LocalKnowledgeRepository(ROOT / "fixtures/knowledge")
    audit = ToolAudit()
    audit.record(
        name="search_synthetic_knowledge",
        arguments={"query": "retryable", "version": knowledge.version},
        result_knowledge_records=(
            _knowledge_row(knowledge, "retryable-document-lock", **row_kwargs),
        ),
    )

    with pytest.raises(ValueError, match=message):
        derive_knowledge_citations(audit, knowledge)


def test_duplicate_and_conflicting_knowledge_audit_records_fail_closed() -> None:
    knowledge = LocalKnowledgeRepository(ROOT / "fixtures/knowledge")
    row = _knowledge_row(knowledge, "retryable-document-lock")
    duplicate = ToolAudit()
    duplicate.record(
        name="search_synthetic_knowledge",
        arguments={"query": "retryable", "version": knowledge.version},
        result_knowledge_records=(row, row),
    )
    with pytest.raises(ValueError, match="duplicate provenance"):
        derive_knowledge_citations(duplicate, knowledge)

    conflicting = ToolAudit()
    conflicting.record(
        name="search_synthetic_knowledge",
        arguments={"query": "retryable", "version": knowledge.version},
        result_knowledge_records=(row,),
    )
    conflicting_row = {**row, "content_digest": "different"}
    conflicting.record(
        name="search_synthetic_knowledge",
        arguments={"query": "lock", "version": knowledge.version},
        result_knowledge_records=(conflicting_row,),
    )
    with pytest.raises(ValueError, match="conflicting provenance"):
        derive_knowledge_citations(conflicting, knowledge)


def test_cross_case_allowlist_fails_closed(tmp_path: Path) -> None:
    evidence = _evidence(tmp_path)
    knowledge = LocalKnowledgeRepository(ROOT / "fixtures/knowledge")
    result = AgentHarness(
        model_factory=ScriptedStrandsFactory(),
        knowledge=knowledge,
        source_availability=_availability(),
    ).run(
        case_id="case-agent-validation",
        trace_id="trace-agent-validation",
        evidence=evidence,
    )
    validator = AgentEvidenceValidator(
        evidence,
        trace_id="trace-agent-validation",
        source_availability=_availability(),
        knowledge=knowledge,
    )

    with pytest.raises(AgentValidationError, match="allowlist"):
        validator.validate_investigator(
            result.investigators[0],
            allowed_evidence_ids=frozenset({"case-other:failed-message"}),
        )


def test_mixed_claim_relations_are_valid_but_supported_conflict_fails_closed(
    tmp_path: Path,
) -> None:
    evidence = _evidence(tmp_path)
    validator = AgentEvidenceValidator(
        evidence,
        trace_id="trace-agent-validation",
        source_availability=_availability(),
    )
    invalid = InvestigatorResult(
        investigator_id=InvestigatorID.RETRYABLE_MESSAGE,
        hypothesis_type=HypothesisType.RETRYABLE_MESSAGE,
        conclusion=HypothesisConclusion.SUPPORTED,
        confidence_band=ConfidenceBand.HIGH,
        factual_claims=(
            AgentClaim(
                claim_id="supporting-claim",
                statement="The record supports the hypothesis.",
                relation=ClaimRelation.SUPPORTS_HYPOTHESIS,
                evidence_ids=(evidence[0].evidence_id,),
            ),
            AgentClaim(
                claim_id="contradicting-claim",
                statement="Another fact contradicts the hypothesis.",
                relation=ClaimRelation.CONTRADICTS_HYPOTHESIS,
                evidence_ids=(evidence[0].evidence_id,),
            ),
        ),
    )

    representable = invalid.model_copy(update={"conclusion": HypothesisConclusion.REJECTED})
    assert validator.validate_investigator(representable) == representable

    with pytest.raises(AgentValidationError, match="unresolved contradicting"):
        validator.validate_investigator(invalid)


def test_supported_diagnosis_is_not_action_authority(tmp_path: Path) -> None:
    evidence = _evidence(tmp_path)
    validator = AgentEvidenceValidator(
        evidence,
        trace_id="trace-agent-validation",
        source_availability=_availability(),
    )
    invalid = InvestigatorResult(
        investigator_id=InvestigatorID.RETRYABLE_MESSAGE,
        hypothesis_type=HypothesisType.RETRYABLE_MESSAGE,
        conclusion=HypothesisConclusion.SUPPORTED,
        confidence_band=ConfidenceBand.HIGH,
        factual_claims=(
            AgentClaim(
                claim_id="partial-claim",
                statement="One admitted record supports the hypothesis.",
                relation=ClaimRelation.SUPPORTS_HYPOTHESIS,
                evidence_ids=(evidence[0].evidence_id,),
            ),
        ),
    )

    assert validator.validate_investigator(invalid) == invalid


def test_source_availability_must_match_admitted_evidence(tmp_path: Path) -> None:
    evidence = _evidence(tmp_path)

    with pytest.raises(AgentValidationError, match="unavailable source MATERIAL_DOCUMENT"):
        AgentEvidenceValidator(
            evidence,
            trace_id="trace-agent-validation",
            source_availability=_availability(
                unavailable=frozenset({EvidenceSourceType.MATERIAL_DOCUMENT})
            ),
        )


def test_source_availability_uses_immutable_genesis_status(tmp_path: Path) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    enterprise = SyntheticEnterprise.seed_from_fixture(tmp_path / "enterprise.sqlite", FIXTURE)
    enterprise.set_material_document_source_unavailable("SOURCE_UNAVAILABLE")
    store = SQLiteCaseStore(tmp_path / "case.sqlite")
    _case, evidence = DiscrepancyDetector(
        enterprise,
        store,
        ManualClock(datetime(2026, 8, 26, tzinfo=UTC)),
    ).detect(
        case_id="case-agent-validation",
        trace_id="trace-agent-validation",
        fixture_path=FIXTURE,
    )
    genesis = store.get_genesis("case-agent-validation")
    availability = source_availability_from_genesis(genesis, evidence)
    assert availability.missing_evidence_sources == ("MATERIAL_DOCUMENT",)

    tampered_facts = {
        **genesis.detection_facts,
        "material_document_source_status": "AVAILABLE",
        "material_document_source_reason": None,
    }
    tampered_genesis = genesis.model_copy(update={"detection_facts": tampered_facts})
    with pytest.raises(AgentValidationError, match="available source MATERIAL_DOCUMENT"):
        source_availability_from_genesis(tampered_genesis, evidence)


def test_rejected_investigator_remains_valid_when_source_is_unavailable(tmp_path: Path) -> None:
    evidence = _evidence(tmp_path, material_unavailable=True)
    availability = _availability(unavailable=frozenset({EvidenceSourceType.MATERIAL_DOCUMENT}))
    validator = AgentEvidenceValidator(
        evidence,
        trace_id="trace-agent-validation",
        source_availability=availability,
    )
    rejected = InvestigatorResult(
        investigator_id=InvestigatorID.SHORT_SHIPMENT,
        hypothesis_type=HypothesisType.GENUINE_SHORT_SHIPMENT,
        conclusion=HypothesisConclusion.REJECTED,
        confidence_band=ConfidenceBand.LOW,
        factual_claims=(
            AgentClaim(
                claim_id="rejected-claim",
                statement="The available records contradict the hypothesis.",
                relation=ClaimRelation.CONTRADICTS_HYPOTHESIS,
                evidence_ids=tuple(item.evidence_id for item in evidence),
            ),
        ),
    )

    assert validator.validate_investigator(rejected) == rejected

    actionable = rejected.model_copy(
        update={
            "conclusion": HypothesisConclusion.SUPPORTED,
            "factual_claims": (
                AgentClaim(
                    claim_id="actionable-claim",
                    statement="All admitted records support a retry.",
                    relation=ClaimRelation.SUPPORTS_HYPOTHESIS,
                    evidence_ids=tuple(item.evidence_id for item in evidence),
                ),
            ),
        }
    )
    with pytest.raises(AgentValidationError, match="source is unavailable"):
        validator.validate_investigator(actionable)


def test_missing_sources_are_derived_for_public_results_and_assessment(tmp_path: Path) -> None:
    evidence = _evidence(tmp_path, material_unavailable=True)
    knowledge = LocalKnowledgeRepository(ROOT / "fixtures/knowledge")
    availability = _availability(unavailable=frozenset({EvidenceSourceType.MATERIAL_DOCUMENT}))
    result = AgentHarness(
        model_factory=ScriptedStrandsFactory(),
        knowledge=knowledge,
        source_availability=availability,
    ).run(
        case_id="case-agent-validation",
        trace_id="trace-agent-validation",
        evidence=evidence,
    )

    assert result.assessment.missing_evidence_sources == ("MATERIAL_DOCUMENT",)
    assert all(
        item["missing_evidence_sources"] == ["MATERIAL_DOCUMENT"]
        for item in (
            result.public()["investigators"][0],
            result.public()["investigators"][1],
            result.public()["investigators"][2],
        )
    )
    assert "missing_evidence_sources" not in result.investigators[0].model_dump(mode="json")
    assert result.public()["synthesis"]["missing_evidence_sources"] == ["MATERIAL_DOCUMENT"]


def test_synthesis_must_follow_authoritative_source_availability(tmp_path: Path) -> None:
    evidence = _evidence(tmp_path, material_unavailable=True)
    knowledge = LocalKnowledgeRepository(ROOT / "fixtures/knowledge")
    missing_availability = _availability(
        unavailable=frozenset({EvidenceSourceType.MATERIAL_DOCUMENT})
    )
    missing_result = AgentHarness(
        model_factory=ScriptedStrandsFactory(),
        knowledge=knowledge,
        source_availability=missing_availability,
    ).run(
        case_id="case-agent-validation",
        trace_id="trace-agent-validation",
        evidence=evidence,
    )
    validator = AgentEvidenceValidator(
        evidence,
        trace_id="trace-agent-validation",
        source_availability=missing_availability,
        knowledge=knowledge,
    )
    invalid_supported = missing_result.synthesis.model_copy(
        update={"conclusion": HypothesisConclusion.SUPPORTED}
    )
    with pytest.raises(AgentValidationError, match="must request evidence"):
        validator.validate_synthesis(invalid_supported, missing_result.investigators)

    available_evidence = _evidence(tmp_path / "available")
    available = _availability()
    available_result = AgentHarness(
        model_factory=ScriptedStrandsFactory(),
        knowledge=knowledge,
        source_availability=available,
    ).run(
        case_id="case-agent-validation",
        trace_id="trace-agent-validation",
        evidence=available_evidence,
    )
    available_validator = AgentEvidenceValidator(
        available_evidence,
        trace_id="trace-agent-validation",
        source_availability=available,
        knowledge=knowledge,
    )
    invalid_uncertain = available_result.synthesis.model_copy(
        update={"conclusion": HypothesisConclusion.NEEDS_EVIDENCE}
    )
    with pytest.raises(AgentValidationError, match="cannot request evidence"):
        available_validator.validate_synthesis(invalid_uncertain, available_result.investigators)
