"""Synthesis stage runner."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

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
    result = await asyncio.wait_for(
        agent.invoke_async(
            "Synthesize these validated investigator results:\n"
            + json.dumps(context, sort_keys=True),
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
    return SynthesisRun(
        result=structured,
        model_result=result,
        audit=ToolAudit(),
        retry_count=_structured_retry_count(result),
    )
