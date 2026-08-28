"""Fixed-role investigator runners."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

from the_missing_20.agents.events import AgentEventSink
from the_missing_20.agents.schemas import (
    HYPOTHESIS_TO_INVESTIGATOR,
    InvestigatorID,
    InvestigatorResult,
    KnowledgeCitation,
    SourceAvailabilitySet,
)
from the_missing_20.agents.tools import (
    KnowledgeProvenanceError,
    ToolAudit,
    ToolScope,
    derive_knowledge_citations,
    derive_read_evidence_ids,
    make_read_admitted_evidence_tool,
    make_search_synthetic_knowledge_tool,
)
from the_missing_20.agents.validation import AgentValidationError
from the_missing_20.ports.agent_model import (
    MAX_OUTPUT_TOKENS_PER_REQUEST,
    AgentModelFactory,
    AgentStage,
)


def _structured_retry_count(result: Any, output_name: str) -> int:
    """Count failed structured-output attempts reported by Strands metrics."""

    metrics = getattr(result, "metrics", None)
    tool_metrics = getattr(metrics, "tool_metrics", {}) if metrics is not None else {}
    metric = tool_metrics.get(output_name)
    retries = int(getattr(metric, "error_count", 0)) if metric is not None else 0
    if retries > 1:
        raise AgentValidationError("structured output remained invalid after one retry")
    return retries


@dataclass(frozen=True, slots=True)
class InvestigatorRun:
    result: InvestigatorResult
    model_result: Any
    audit: ToolAudit
    read_evidence_ids: tuple[str, ...] = ()
    knowledge_citations: tuple[KnowledgeCitation, ...] = ()
    retry_count: int = 0


def _prompt(
    role: InvestigatorID,
    scope: ToolScope,
    source_availability: SourceAvailabilitySet,
) -> str:
    hypothesis = {
        InvestigatorID.RETRYABLE_MESSAGE: "RETRYABLE_MESSAGE",
        InvestigatorID.SHORT_SHIPMENT: "GENUINE_SHORT_SHIPMENT",
        InvestigatorID.DUPLICATE_POSTING: "ALREADY_POSTED",
    }[role]
    return (
        f"You are {role.value}. Test only the {hypothesis} hypothesis for case "
        f"{scope.case_id}. Call read_admitted_evidence exactly once for every ID in "
        f"{sorted(scope.allowed_evidence_ids)}; parallel tool calls are allowed. "
        f"If procedural context is useful, search only knowledge version "
        f"{scope.knowledge_version}. After the tool results, do not answer with prose: "
        "submit the complete InvestigatorResult structured output. Use only enum values "
        "defined by its schema, preserve conflicting evidence, and cite admitted "
        "evidence IDs for every factual claim. Set each claim's relation to exactly one of "
        "SUPPORTS_HYPOTHESIS, CONTRADICTS_HYPOTHESIS, or CONTEXT_ONLY. The relation belongs "
        "to the claim, not to the whole evidence record; the same record may support one "
        "claim and contradict another. Do not emit aggregate evidence-polarity fields. "
        "Never recommend, authorize, or execute an action. "
        "Authoritative source availability is supplied by the deterministic detector; "
        "do not infer or alter it: "
        + json.dumps(source_availability.model_dump(mode="json"), sort_keys=True)
    )


async def run_investigator(
    *,
    role: InvestigatorID,
    stage: AgentStage,
    model_factory: AgentModelFactory,
    output_payload: dict[str, Any],
    tool_plan: tuple[dict[str, Any], ...],
    scope: ToolScope,
    source_availability: SourceAvailabilitySet,
    event_sink: AgentEventSink | None = None,
    operation_prefix: str | None = None,
    system_prompt: str | None = None,
    timeout_seconds: float = 45.0,
) -> InvestigatorRun:
    """Run one real Strands Agent with only the two audited read tools."""

    try:
        from strands import Agent
        from strands.types.agent import Limits
    except ImportError as exc:  # pragma: no cover - before dependency bootstrap
        raise RuntimeError("strands-agents is required for the agent harness") from exc

    audit = ToolAudit(
        event_sink=event_sink,
        case_id=scope.case_id,
        trace_id=scope.trace_id,
        actor=role.value,
        stage=stage.value if operation_prefix is None else operation_prefix,
    )
    tools = [
        make_read_admitted_evidence_tool(scope, audit),
        make_search_synthetic_knowledge_tool(scope, audit),
    ]
    model = model_factory.create(stage=stage, output_payload=output_payload, tool_plan=tool_plan)
    agent = Agent(
        model=model,
        tools=tools,
        system_prompt=system_prompt or "Use only the provided read-only tools.",
        structured_output_model=InvestigatorResult,
        callback_handler=None,
        agent_id=f"{role.value}-v3",
        name=role.value,
    )
    model_result = await asyncio.wait_for(
        agent.invoke_async(
            _prompt(role, scope, source_availability),
            structured_output_model=InvestigatorResult,
            structured_output_prompt="Return the complete investigator result now.",
            limits=Limits(
                turns=8,
                output_tokens=MAX_OUTPUT_TOKENS_PER_REQUEST,
                total_tokens=16_000,
            ),
        ),
        timeout=timeout_seconds,
    )
    structured = getattr(model_result, "structured_output", None)
    if not isinstance(structured, InvestigatorResult):
        raise ValueError(f"investigator {role.value} did not return structured output")
    if structured.investigator_id is not role:
        raise AgentValidationError(
            f"investigator output role {structured.investigator_id.value} "
            f"does not match assigned role {role.value}"
        )
    if HYPOTHESIS_TO_INVESTIGATOR.get(structured.hypothesis_type) is not role:
        raise AgentValidationError(
            f"investigator hypothesis {structured.hypothesis_type.value} "
            f"does not match assigned role {role.value}"
        )
    try:
        read_evidence_ids = derive_read_evidence_ids((audit,))
        knowledge_citations = derive_knowledge_citations((audit,), scope.knowledge)
    except KnowledgeProvenanceError as exc:
        raise AgentValidationError(str(exc)) from exc
    return InvestigatorRun(
        result=structured,
        model_result=model_result,
        audit=audit,
        read_evidence_ids=read_evidence_ids,
        knowledge_citations=knowledge_citations,
        retry_count=_structured_retry_count(model_result, InvestigatorResult.__name__),
    )


def default_tool_plan(scope: ToolScope) -> tuple[dict[str, Any], ...]:
    """Stable scripted plan that reads every currently admitted evidence item once."""

    evidence_plan = tuple(
        {"tool": "read_admitted_evidence", "arguments": {"evidence_id": evidence_id}}
        for evidence_id in sorted(scope.allowed_evidence_ids)[: scope.max_evidence_reads]
    )
    knowledge_plan = (
        {
            "tool": "search_synthetic_knowledge",
            "arguments": {"query": "retryable", "version": scope.knowledge_version},
        },
    )
    return evidence_plan + knowledge_plan[: scope.max_knowledge_searches]
