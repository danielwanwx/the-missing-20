"""Synthesis stage runner."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

from the_missing_20.agents.events import (
    AgentEventSink,
    AgentOperationEvent,
    AgentOperationEventType,
)
from the_missing_20.agents.schemas import (
    InvestigatorResult,
    KnowledgeCitation,
    SourceAvailabilitySet,
    SynthesisResult,
    public_investigator_result,
)
from the_missing_20.agents.tools import ToolAudit
from the_missing_20.agents.validation import AgentValidationError
from the_missing_20.ports.agent_model import (
    MAX_OUTPUT_TOKENS_PER_REQUEST,
    AgentModelFactory,
    AgentStage,
)


@dataclass(frozen=True, slots=True)
class SynthesisRun:
    result: SynthesisResult
    model_result: Any
    audit: ToolAudit
    retry_count: int = 0


def _synthesis_prompt(context: dict[str, Any]) -> str:
    """Build the bounded synthesis instruction around validated agent records."""

    return (
        "Synthesize these validated investigator results. Preserve exactly one record "
        "for each fixed investigator in the supplied context, but select only one "
        "hypothesis. Never upgrade a REJECTED or NEEDS_EVIDENCE investigator to "
        "SUPPORTED. When the synthesis conclusion is SUPPORTED, factual_claims may "
        "include evidence-backed SUPPORTS_HYPOTHESIS and CONTEXT_ONLY claims for the "
        "selected hypothesis, but must contain zero CONTRADICTS_HYPOTHESIS claims. "
        "Rejected investigators' contradictory claims are application-owned dissent "
        "and must not be copied into supported synthesis factual_claims. NEEDS_EVIDENCE "
        "is allowed only when detector source availability contains an unavailable "
        "authoritative source; when all sources are AVAILABLE, do not use NEEDS_EVIDENCE. "
        "Every admitted evidence ID present in the validated investigator context or its "
        "read_evidence_ids must be cited at least once in synthesis factual_claims. For a "
        "selected SUPPORTED hypothesis, evidence that does not directly support it may be "
        "represented only by a truthful CONTEXT_ONLY claim; never invent a claim or change "
        "a relation merely to fill coverage. Claim IDs must be unique, and evidence IDs "
        "must be copied exactly from the supplied validated context. "
        "Remain advisory and read-only; never recommend, authorize, or execute an action."
        "\n\nVALIDATED INVESTIGATOR CONTEXT:\n"
        + json.dumps(context, sort_keys=True)
    )


def _structured_retry_count(result: Any) -> int:
    metrics = getattr(result, "metrics", None)
    tool_metrics = getattr(metrics, "tool_metrics", {}) if metrics is not None else {}
    metric = tool_metrics.get(SynthesisResult.__name__)
    retries = int(getattr(metric, "error_count", 0)) if metric is not None else 0
    if retries > 1:
        raise AgentValidationError("structured output remained invalid after one retry")
    return retries


async def run_synthesis(
    *,
    model_factory: AgentModelFactory,
    output_payload: dict[str, Any],
    investigators: tuple[InvestigatorResult, ...],
    source_availability: SourceAvailabilitySet,
    investigator_knowledge_citations: tuple[tuple[KnowledgeCitation, ...], ...] | None = None,
    investigator_read_evidence_ids: tuple[tuple[str, ...], ...] | None = None,
    case_id: str,
    trace_id: str,
    event_sink: AgentEventSink | None = None,
    operation_id: str | None = None,
    system_prompt: str | None = None,
    timeout_seconds: float = 45.0,
) -> SynthesisRun:
    try:
        from strands import Agent
        from strands.types.agent import Limits
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("strands-agents is required for the agent harness") from exc

    citations_by_investigator = investigator_knowledge_citations or tuple(() for _ in investigators)
    if len(citations_by_investigator) != len(investigators):
        raise ValueError("knowledge provenance must accompany every investigator")

    model = model_factory.create(stage=AgentStage.SYNTHESIS, output_payload=output_payload)
    agent = Agent(
        model=model,
        tools=[],
        system_prompt=system_prompt
        or (
            "Synthesize validated investigator records; never recommend, authorize, or "
            "execute an action."
        ),
        structured_output_model=SynthesisResult,
        callback_handler=None,
        agent_id="synthesis-v3",
        name="synthesis",
    )
    context = {
        "case_id": case_id,
        "trace_id": trace_id,
        "source_availability": source_availability.model_dump(mode="json"),
        "investigators": [
            public_investigator_result(
                item,
                missing_evidence_sources=source_availability.missing_evidence_sources,
                knowledge_citations=knowledge_citations,
                read_evidence_ids=read_ids,
            )
            for item, knowledge_citations, read_ids in zip(
                investigators,
                citations_by_investigator,
                investigator_read_evidence_ids or tuple(() for _ in investigators),
                strict=True,
            )
        ],
    }
    operation_id = operation_id or f"synthesis:{trace_id}"
    if event_sink is not None:
        event_sink.emit(
            AgentOperationEvent(
                event_type=AgentOperationEventType.SYNTHESIS_STARTED,
                case_id=case_id,
                trace_id=trace_id,
                actor="synthesis",
                operation_id=operation_id,
                status="RUNNING",
                correlation_id=trace_id,
                stage=AgentStage.SYNTHESIS.value,
            )
        )
    try:
        result = await asyncio.wait_for(
            agent.invoke_async(
                _synthesis_prompt(context),
                structured_output_model=SynthesisResult,
                structured_output_prompt="Return the complete synthesis result now.",
                limits=Limits(
                    turns=5,
                    output_tokens=MAX_OUTPUT_TOKENS_PER_REQUEST,
                    total_tokens=8_000,
                ),
            ),
            timeout=timeout_seconds,
        )
        structured = getattr(result, "structured_output", None)
        if not isinstance(structured, SynthesisResult):
            raise ValueError("synthesis did not return structured output")
    except Exception as exc:
        if event_sink is not None:
            event_sink.emit(
                AgentOperationEvent(
                    event_type=AgentOperationEventType.SYNTHESIS_COMPLETED,
                    case_id=case_id,
                    trace_id=trace_id,
                    actor="synthesis",
                    operation_id=operation_id,
                    status="FAILED",
                    correlation_id=trace_id,
                    stage=AgentStage.SYNTHESIS.value,
                    payload={"error_code": type(exc).__name__},
                )
            )
        raise
    if event_sink is not None:
        event_sink.emit(
            AgentOperationEvent(
                event_type=AgentOperationEventType.SYNTHESIS_COMPLETED,
                case_id=case_id,
                trace_id=trace_id,
                actor="synthesis",
                operation_id=operation_id,
                status="COMPLETED",
                correlation_id=trace_id,
                stage=AgentStage.SYNTHESIS.value,
                payload={
                    "selected_hypothesis": structured.selected_hypothesis.value,
                    "conclusion": structured.conclusion.value,
                    "claim_ids": [item.claim_id for item in structured.factual_claims],
                },
            )
        )
    return SynthesisRun(
        result=structured,
        model_result=result,
        audit=ToolAudit(),
        retry_count=_structured_retry_count(result),
    )
