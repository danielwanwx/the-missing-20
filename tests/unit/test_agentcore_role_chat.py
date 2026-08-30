"""Regression coverage for the AgentCore role-chat event-loop transport."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from the_missing_20.adapters.local_knowledge import LocalKnowledgeRepository
from the_missing_20.adapters.strands_models import (
    AgentCoreRuntimeConfig,
    AgentCoreRuntimeFactory,
    AgentCoreRuntimeModel,
)
from the_missing_20.agents.harness import AgentHarness
from the_missing_20.agents.schemas import (
    REQUIRED_AUTHORITATIVE_SOURCES,
    SourceAvailability,
    SourceAvailabilitySet,
)
from the_missing_20.agents.validation import AgentValidationError
from the_missing_20.domain.enterprise import EvidenceReadStatus
from the_missing_20.domain.models import EvidenceSourceType
from the_missing_20.experiment.events import PublicEventType
from the_missing_20.experiment.session import ExperimentSession, _SessionAgentEventSink

ROOT = Path(__file__).resolve().parents[2]


def test_retryable_role_chat_uses_outer_strands_loop_before_one_remote_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    remote_calls: list[str] = []
    remote_loop_states: list[bool] = []
    factory = AgentCoreRuntimeFactory(
        config=AgentCoreRuntimeConfig(
            runtime_arn="arn:aws:bedrock-agentcore:us-west-2:123456789012:runtime/fake"
        )
    )
    session = ExperimentSession(
        ROOT,
        data_directory=tmp_path / "session",
        model_factory=factory,
    )
    evidence = tuple(session.store.list_evidence(session.case_id))
    queue_evidence = next(
        item for item in evidence if item.source_type is EvidenceSourceType.FAILED_MESSAGE_QUEUE
    )
    output = {
        "investigator_id": "retryable_message_investigator",
        "hypothesis_type": "RETRYABLE_MESSAGE",
        "conclusion": "SUPPORTED",
        "confidence_band": "HIGH",
        "factual_claims": [
            {
                "claim_id": "queue-claim",
                "statement": "The failed receipt message is retryable.",
                "relation": "SUPPORTS_HYPOTHESIS",
                "evidence_ids": [queue_evidence.evidence_id],
            }
        ],
    }

    def fake_invoke(
        self: AgentCoreRuntimeModel, prompt: str
    ) -> tuple[Any, int, int, dict[str, object]]:
        del self
        remote_calls.append(prompt)
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            remote_loop_states.append(False)
        else:
            remote_loop_states.append(True)
        return (
            {"output": output},
            12,
            8,
            {
                "mode": "agentcore",
                "provider": "agentcore",
                "model": "agentcore-runtime",
                "transport": "agentcore_invoke_agent_runtime",
                "region": "us-west-2",
                "qualifier": "DEFAULT",
                "runtime_configured": True,
                "invocation_id": "runtime-chat-123",
                "invocation_proof": "returned",
                "status": "RETURNED",
                "invocation_status": "RETURNED",
            },
        )

    monkeypatch.setattr(AgentCoreRuntimeModel, "_invoke", fake_invoke)
    harness = AgentHarness(
        model_factory=factory,
        knowledge=LocalKnowledgeRepository(ROOT / "fixtures/knowledge"),
        source_availability=SourceAvailabilitySet(
            sources=tuple(
                SourceAvailability(source_type=source, status=EvidenceReadStatus.AVAILABLE)
                for source in REQUIRED_AUTHORITATIVE_SOURCES
            )
        ),
    )

    result = harness.run_chat(
        case_id=session.case_id,
        trace_id=session.trace_id,
        evidence=evidence,
        user_question="Why did the receipt message fail?",
        selected_agent_id="retryable_message_investigator",
    )

    assert result.investigator.result.investigator_id.value == "retryable_message_investigator"
    assert result.investigator.read_evidence_ids
    assert set(result.investigator.read_evidence_ids).issubset(
        {
            item.evidence_id
            for item in evidence
            if item.source_type
            in {
                EvidenceSourceType.FAILED_MESSAGE_QUEUE,
                EvidenceSourceType.WAREHOUSE,
                EvidenceSourceType.ERP_RECEIPT,
            }
        }
    )
    assert {
        call["tool"] for call in result.investigator.audit.calls
    }.issubset({"read_admitted_evidence", "search_synthetic_knowledge"})
    assert len(remote_calls) == 1
    assert remote_loop_states == [False]
    assert result.knowledge_citations
    assert result.provider_metadata["request_count"] > 0
    assert result.provider_metadata["provider"] == "agentcore"
    assert result.provider_metadata["invocation_id"] == "runtime-chat-123"

    response = session.chat_command(
        "Why did the receipt message fail?",
        idempotency_key="chat:retryable:agentcore",
        agent_id="retryable_message_investigator",
    )
    assert response["intent"] != "advisory_provider_degraded"
    assert response["provider_metadata"]["request_count"] > 0
    assert response["provider_metadata"]["invocation_id"] == "runtime-chat-123"


def test_role_chat_validation_failure_persists_returned_provider_attribution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A returned response that fails role validation remains a redacted failure record."""

    factory = AgentCoreRuntimeFactory(
        config=AgentCoreRuntimeConfig(
            runtime_arn="arn:aws:bedrock-agentcore:us-west-2:123456789012:runtime/fake"
        )
    )
    session = ExperimentSession(
        ROOT,
        data_directory=tmp_path / "session-invalid-role",
        model_factory=factory,
    )
    evidence = tuple(session.store.list_evidence(session.case_id))
    queue_evidence = next(
        item for item in evidence if item.source_type is EvidenceSourceType.FAILED_MESSAGE_QUEUE
    )
    invalid_output = {
        "investigator_id": "short_shipment_investigator",
        "hypothesis_type": "GENUINE_SHORT_SHIPMENT",
        "conclusion": "REJECTED",
        "confidence_band": "LOW",
        "factual_claims": [
            {
                "claim_id": "wrong-role-claim",
                "statement": "The response belongs to a different investigator.",
                "relation": "CONTEXT_ONLY",
                "evidence_ids": [queue_evidence.evidence_id],
            }
        ],
    }

    def fake_invoke(
        self: AgentCoreRuntimeModel, prompt: str
    ) -> tuple[Any, int, int, dict[str, object]]:
        del self, prompt
        return (
            {"output": invalid_output},
            12,
            8,
            {
                "mode": "agentcore",
                "provider": "agentcore",
                "model": "agentcore-runtime",
                "transport": "agentcore_invoke_agent_runtime",
                "region": "us-west-2",
                "qualifier": "DEFAULT",
                "runtime_configured": True,
                "invocation_id": "runtime-chat-invalid-role",
                "invocation_proof": "returned",
                "status": "RETURNED",
                "invocation_status": "RETURNED",
            },
        )

    monkeypatch.setattr(AgentCoreRuntimeModel, "_invoke", fake_invoke)
    harness = AgentHarness(
        model_factory=factory,
        knowledge=LocalKnowledgeRepository(ROOT / "fixtures/knowledge"),
        source_availability=SourceAvailabilitySet(
            sources=tuple(
                SourceAvailability(source_type=source, status=EvidenceReadStatus.AVAILABLE)
                for source in REQUIRED_AUTHORITATIVE_SOURCES
            )
        ),
        event_sink=_SessionAgentEventSink(session),
    )

    with pytest.raises(AgentValidationError, match="does not match assigned role"):
        harness.run_chat(
            case_id=session.case_id,
            trace_id=session.trace_id,
            evidence=evidence,
            user_question="Why did the receipt message fail?",
            selected_agent_id="retryable_message_investigator",
        )

    event = next(
        event
        for event in reversed(session.events_since())
        if event.event_type is PublicEventType.AGENT_COMPLETED
    )
    metadata = event.payload["provider_metadata"]
    assert isinstance(metadata, dict)
    assert metadata["provider"] == "agentcore"
    assert metadata["invocation_id"] == "runtime-chat-invalid-role"
    assert metadata["invocation_proof"] == "returned"
    assert metadata["status"] == "DEGRADED"
    assert metadata["invocation_status"] == "FAILED"
    assert "runtime_arn" not in str(metadata)
    assert "123456789012" not in str(metadata)
