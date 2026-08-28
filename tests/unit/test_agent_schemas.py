from __future__ import annotations

import pytest
from pydantic import ValidationError

from the_missing_20.agents.schemas import (
    REQUIRED_AUTHORITATIVE_SOURCES,
    AgentClaim,
    ClaimRelation,
    InvestigatorID,
    InvestigatorResult,
    KnowledgeCitation,
    KnowledgeUse,
    SourceAvailability,
    SourceAvailabilitySet,
    SynthesisResult,
    derive_preserved_dissent,
    derived_claim_ids_by_relation,
    derived_context_evidence_ids,
    derived_contradicting_evidence_ids,
    derived_supporting_evidence_ids,
)
from the_missing_20.domain.enterprise import EvidenceReadStatus
from the_missing_20.domain.models import (
    ConfidenceBand,
    EvidenceSourceType,
    HypothesisConclusion,
    HypothesisType,
)


def _wire_result() -> dict[str, object]:
    return {
        "investigator_id": "retryable_message_investigator",
        "hypothesis_type": "RETRYABLE_MESSAGE",
        "conclusion": "SUPPORTED",
        "confidence_band": "HIGH",
        "factual_claims": [
            {
                "claim_id": "claim-1",
                "statement": "The admitted record supports the hypothesis.",
                "relation": "SUPPORTS_HYPOTHESIS",
                "evidence_ids": ["case-1:failed-message"],
            }
        ],
    }


def test_wire_json_is_normalized_into_strict_frozen_contract() -> None:
    result = InvestigatorResult.model_validate(_wire_result())

    assert result.investigator_id is InvestigatorID.RETRYABLE_MESSAGE
    assert result.hypothesis_type is HypothesisType.RETRYABLE_MESSAGE
    assert result.conclusion is HypothesisConclusion.SUPPORTED
    assert result.confidence_band is ConfidenceBand.HIGH
    assert isinstance(result.factual_claims[0], AgentClaim)


def test_model_cannot_author_knowledge_citations() -> None:
    payload = _wire_result()
    payload["knowledge_citations"] = [
        {
            "knowledge_id": "retryable-document-lock",
            "version": "knowledge-v1",
            "allowed_use": "ERROR_DEFINITION_ONLY",
            "content_digest": "fabricated",
        }
    ]

    with pytest.raises(ValidationError, match="knowledge_citations"):
        InvestigatorResult.model_validate(payload)

    assert "knowledge_citations" not in InvestigatorResult.model_fields

    synthesis = {
        "selected_hypothesis": "RETRYABLE_MESSAGE",
        "conclusion": "SUPPORTED",
        "confidence_band": "HIGH",
        "factual_claims": [],
        "synthesis_version": "synthesis-v3",
        "knowledge_citations": payload["knowledge_citations"],
    }
    with pytest.raises(ValidationError, match="knowledge_citations"):
        SynthesisResult.model_validate(synthesis)


def test_model_cannot_author_action_fields() -> None:
    investigator = _wire_result()
    investigator["proposed_action"] = "restart_receipt_message"
    with pytest.raises(ValidationError, match="proposed_action"):
        InvestigatorResult.model_validate(investigator)

    synthesis = {
        "selected_hypothesis": "RETRYABLE_MESSAGE",
        "conclusion": "SUPPORTED",
        "confidence_band": "HIGH",
        "factual_claims": [],
        "synthesis_version": "synthesis-v3",
        "proposed_action": "restart_receipt_message",
    }
    with pytest.raises(ValidationError, match="proposed_action"):
        SynthesisResult.model_validate(synthesis)

    evaluator = {
        "decision": "ACCEPT",
        "validated_claim_ids": [],
        "validated_evidence_ids": [],
        "failed_invariants": [],
        "required_evidence_sources": [],
        "evaluator_version": "evaluator-v3",
        "allowed_next_action": "restart_receipt_message",
    }
    from the_missing_20.agents.schemas import AgentEvaluationResult

    with pytest.raises(ValidationError, match="allowed_next_action"):
        AgentEvaluationResult.model_validate(evaluator)


def test_public_knowledge_citation_is_a_strict_derived_record() -> None:
    citation = KnowledgeCitation.model_validate(
        {
            "knowledge_id": "retryable-document-lock",
            "version": "knowledge-v1",
            "allowed_use": "ERROR_DEFINITION_ONLY",
            "content_digest": "sha256:record",
        }
    )

    assert citation.allowed_use is KnowledgeUse.ERROR_DEFINITION_ONLY
    assert citation.model_dump(mode="json") == {
        "knowledge_id": "retryable-document-lock",
        "version": "knowledge-v1",
        "allowed_use": "ERROR_DEFINITION_ONLY",
        "content_digest": "sha256:record",
    }


def test_unknown_wire_fields_are_rejected() -> None:
    payload = _wire_result()
    payload["unexpected"] = "must not cross the boundary"

    with pytest.raises(ValidationError, match="unexpected"):
        InvestigatorResult.model_validate(payload)


def test_model_cannot_authenticate_support_with_a_separate_field() -> None:
    payload = _wire_result()
    payload["supporting_evidence_ids"] = ["case-1:failed-message"]

    with pytest.raises(ValidationError, match="supporting_evidence_ids"):
        InvestigatorResult.model_validate(payload)

    assert "supporting_evidence_ids" not in InvestigatorResult.model_fields
    assert "supporting_evidence_ids" not in SynthesisResult.model_fields


def test_model_cannot_author_missing_sources() -> None:
    payload = _wire_result()
    payload["missing_evidence_sources"] = ["MATERIAL_DOCUMENT"]

    with pytest.raises(ValidationError, match="missing_evidence_sources"):
        InvestigatorResult.model_validate(payload)

    synthesis = {
        "selected_hypothesis": "RETRYABLE_MESSAGE",
        "conclusion": "SUPPORTED",
        "confidence_band": "HIGH",
        "factual_claims": [],
        "synthesis_version": "synthesis-v3",
        "missing_evidence_sources": ["MATERIAL_DOCUMENT"],
    }
    with pytest.raises(ValidationError, match="missing_evidence_sources"):
        SynthesisResult.model_validate(synthesis)


def test_relation_projections_are_the_exact_union_of_claim_citations() -> None:
    result = InvestigatorResult.model_validate(
        {
            **_wire_result(),
            "factual_claims": [
                {
                    "claim_id": "claim-1",
                    "statement": "The admitted record supports the hypothesis.",
                    "relation": "SUPPORTS_HYPOTHESIS",
                    "evidence_ids": ["case-1:warehouse", "case-1:failed-message"],
                },
                {
                    "claim_id": "claim-2",
                    "statement": "The second admitted record confirms the hypothesis.",
                    "relation": "CONTEXT_ONLY",
                    "evidence_ids": ["case-1:warehouse"],
                },
            ],
        }
    )

    assert derived_supporting_evidence_ids(result) == (
        "case-1:failed-message",
        "case-1:warehouse",
    )
    assert derived_contradicting_evidence_ids(result) == ()
    assert derived_context_evidence_ids(result) == ("case-1:warehouse",)
    assert derived_claim_ids_by_relation(result)[ClaimRelation.SUPPORTS_HYPOTHESIS] == ("claim-1",)
    assert "supporting_evidence_ids" not in result.model_dump(mode="json")


def test_mixed_relations_can_cite_the_same_evidence_record() -> None:
    result = InvestigatorResult.model_validate(
        {
            **_wire_result(),
            "conclusion": "REJECTED",
            "factual_claims": [
                {
                    "claim_id": "supports-fact",
                    "statement": "One fact supports the hypothesis.",
                    "relation": "SUPPORTS_HYPOTHESIS",
                    "evidence_ids": ["case-1:warehouse"],
                },
                {
                    "claim_id": "contradicts-fact",
                    "statement": "Another fact contradicts the hypothesis.",
                    "relation": "CONTRADICTS_HYPOTHESIS",
                    "evidence_ids": ["case-1:warehouse"],
                },
            ],
        }
    )

    assert derived_supporting_evidence_ids(result) == ("case-1:warehouse",)
    assert derived_contradicting_evidence_ids(result) == ("case-1:warehouse",)


def test_model_cannot_author_legacy_polarity_or_dissent_fields() -> None:
    for field in ("contradicting_evidence_ids", "preserved_dissent"):
        payload = _wire_result()
        payload[field] = []
        with pytest.raises(ValidationError, match=field):
            InvestigatorResult.model_validate(payload)

    synthesis = {
        "selected_hypothesis": "RETRYABLE_MESSAGE",
        "conclusion": "NEEDS_EVIDENCE",
        "confidence_band": "LOW",
        "factual_claims": [],
        "synthesis_version": "synthesis-v3",
        "preserved_dissent": [],
    }
    with pytest.raises(ValidationError, match="preserved_dissent"):
        SynthesisResult.model_validate(synthesis)


def test_dissent_projection_preserves_relation_meaning() -> None:
    investigators = (
        InvestigatorResult.model_validate(_wire_result()),
        InvestigatorResult.model_validate(
            {
                "investigator_id": "short_shipment_investigator",
                "hypothesis_type": "GENUINE_SHORT_SHIPMENT",
                "conclusion": "REJECTED",
                "confidence_band": "LOW",
                "factual_claims": [
                    {
                        "claim_id": "short-claim",
                        "statement": "The record contradicts the hypothesis.",
                        "relation": "CONTRADICTS_HYPOTHESIS",
                        "evidence_ids": ["case-1:warehouse"],
                    }
                ],
            }
        ),
        InvestigatorResult.model_validate(
            {
                "investigator_id": "duplicate_posting_investigator",
                "hypothesis_type": "ALREADY_POSTED",
                "conclusion": "REJECTED",
                "confidence_band": "LOW",
                "factual_claims": [],
            }
        ),
    )
    dissent = derive_preserved_dissent(investigators)
    assert [item.investigator_id.value for item in dissent] == [
        "duplicate_posting_investigator",
        "retryable_message_investigator",
        "short_shipment_investigator",
    ]
    assert dissent[2].claim_ids_by_relation[ClaimRelation.CONTRADICTS_HYPOTHESIS] == (
        "short-claim",
    )


def test_strict_contract_does_not_coerce_non_json_values() -> None:
    payload = _wire_result()
    payload["confidence_band"] = 1

    with pytest.raises(ValidationError):
        InvestigatorResult.model_validate(payload)


def _all_available() -> SourceAvailabilitySet:
    return SourceAvailabilitySet(
        sources=tuple(
            SourceAvailability(source_type=source, status=EvidenceReadStatus.AVAILABLE)
            for source in REQUIRED_AUTHORITATIVE_SOURCES
        )
    )


def test_source_availability_is_exactly_once_and_derives_missing_sources() -> None:
    availability = SourceAvailabilitySet(
        sources=tuple(
            SourceAvailability(
                source_type=source,
                status=(
                    EvidenceReadStatus.UNAVAILABLE
                    if source is EvidenceSourceType.MATERIAL_DOCUMENT
                    else EvidenceReadStatus.AVAILABLE
                ),
                unavailability_reason=(
                    "SOURCE_UNAVAILABLE" if source is EvidenceSourceType.MATERIAL_DOCUMENT else None
                ),
            )
            for source in REQUIRED_AUTHORITATIVE_SOURCES
        )
    )

    assert availability.missing_evidence_sources == ("MATERIAL_DOCUMENT",)


def test_source_availability_rejects_duplicate_and_status_reason_mismatch() -> None:
    available = SourceAvailability(
        source_type=EvidenceSourceType.INVOICE,
        status=EvidenceReadStatus.AVAILABLE,
    )
    with pytest.raises(ValidationError, match="duplicate"):
        SourceAvailabilitySet(
            sources=(available, available, *(_all_available().sources[2:])),
        )
    with pytest.raises(ValidationError, match="5 items"):
        SourceAvailabilitySet(sources=_all_available().sources[:-1])

    with pytest.raises(ValidationError, match="unavailability reason"):
        SourceAvailability(
            source_type=EvidenceSourceType.INVOICE,
            status=EvidenceReadStatus.AVAILABLE,
            unavailability_reason="WRONG",
        )
    with pytest.raises(ValidationError, match="requires"):
        SourceAvailability(
            source_type=EvidenceSourceType.INVOICE,
            status=EvidenceReadStatus.UNAVAILABLE,
        )
