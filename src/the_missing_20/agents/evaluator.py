"""Independent evaluator stage runner."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

from the_missing_20.agents.events import (
    AgentEventSink,
    AgentOperationEvent,
    AgentOperationEventType,
)
from the_missing_20.agents.schemas import (
    AgentEvaluationResult,
    KnowledgeCitation,
    PreservedDissent,
    SourceAvailabilitySet,
    SynthesisResult,
)
from the_missing_20.agents.tools import ToolAudit
from the_missing_20.agents.validation import AgentValidationError
from the_missing_20.ports.agent_model import (
    AgentModelFactory,
    AgentStage,
    actual_provider_metadata,
    mark_provider_failure,
)


@dataclass(frozen=True, slots=True)
class EvaluationRun:
    result: AgentEvaluationResult
    model_result: Any
    audit: ToolAudit
    retry_count: int = 0
    provider_metadata: dict[str, Any] = field(default_factory=dict)


def _evaluator_prompt(context: dict[str, Any]) -> str:
    """Build the bounded semantic-evaluation instruction around validated context."""

    return (
        "Evaluate this independently assembled record. The evaluator judges semantic "
        "claim quality only. Application code owns evidence identity, evidence integrity, "
        "source coverage, citation closure, policy, authorization, and execution. ACCEPT "
        "means every synthesis claim ID appears exactly once in validated_claim_ids and "
        "failed_invariants is empty. REJECT means do not validate unsupported claims and "
        "identify the semantic failures. MORE_EVIDENCE is allowed only when the supplied "
        "synthesis conclusion is NEEDS_EVIDENCE; do not use it for a SUPPORTED or REJECTED "
        "synthesis. Never invent claim IDs or evidence IDs; never recommend, authorize, "
        "or execute. Emit only the AgentEvaluationResult contract."
        "\n\nVALIDATED EVALUATION CONTEXT:\n"
        + json.dumps(context, sort_keys=True)
    )


def _structured_retry_count(result: Any) -> int:
    metrics = getattr(result, "metrics", None)
    tool_metrics = getattr(metrics, "tool_metrics", {}) if metrics is not None else {}
    metric = tool_metrics.get(AgentEvaluationResult.__name__)
    retries = int(getattr(metric, "error_count", 0)) if metric is not None else 0
    if retries > 1:
        raise AgentValidationError("structured output remained invalid after one retry")
    return retries


async def run_evaluator(
    *,
    model_factory: AgentModelFactory,
    output_payload: dict[str, Any],
    synthesis: SynthesisResult,
    investigator_knowledge_citations: tuple[tuple[KnowledgeCitation, ...], ...] | None = None,
    investigator_read_evidence_ids: tuple[tuple[str, ...], ...] | None = None,
    admitted_evidence_ids: tuple[str, ...],
    source_types: tuple[str, ...],
    case_id: str,
    trace_id: str,
    event_sink: AgentEventSink | None = None,
    operation_id: str | None = None,
    source_availability: SourceAvailabilitySet,
    preserved_dissent: tuple[PreservedDissent, ...] | None = None,
    system_prompt: str | None = None,
    timeout_seconds: float = 45.0,
) -> EvaluationRun:
    try:
        from strands import Agent
        from strands.types.agent import Limits
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("strands-agents is required for the agent harness") from exc

    citations_by_investigator = investigator_knowledge_citations or ()
    # All deterministic projections remain explicit function inputs for call-site
    # compatibility, but never cross the v9 evaluator prompt boundary.  The
    # evaluator judges claim semantics only; the harness later derives citation
    # closure, source coverage, policy, and action eligibility.
    del (
        source_types,
        source_availability,
        preserved_dissent,
        admitted_evidence_ids,
        investigator_read_evidence_ids,
    )

    model = model_factory.create(stage=AgentStage.EVALUATOR, output_payload=output_payload)
    agent = Agent(
        model=model,
        tools=[],
        system_prompt=system_prompt
        or (
            "Evaluate the assembled evidence record; never recommend, authorize, or execute "
            "an action."
        ),
        structured_output_model=AgentEvaluationResult,
        callback_handler=None,
        agent_id="evaluator-v4",
        name="evaluator",
    )
    context = {
        "case_id": case_id,
        "trace_id": trace_id,
        "synthesis": synthesis.model_dump(mode="json"),
        "investigator_knowledge_citations": [
            [citation.model_dump(mode="json") for citation in citations]
            for citations in citations_by_investigator
        ],
        "invariant_checklist": [
            "claims_are_cited",
            "evidence_is_admitted",
            "dissent_is_preserved",
            "knowledge_is_not_current_state_proof",
        ],
    }
    operation_id = operation_id or f"evaluator:{trace_id}"
    if event_sink is not None:
        event_sink.emit(
            AgentOperationEvent(
                event_type=AgentOperationEventType.EVALUATION_STARTED,
                case_id=case_id,
                trace_id=trace_id,
                actor="evaluator",
                operation_id=operation_id,
                status="RUNNING",
                correlation_id=trace_id,
                stage=AgentStage.EVALUATOR.value,
            )
        )
    try:
        result = await asyncio.wait_for(
            agent.invoke_async(
                _evaluator_prompt(context),
                structured_output_model=AgentEvaluationResult,
                structured_output_prompt="Return the complete evaluator result now.",
                limits=Limits(turns=5, output_tokens=1_500, total_tokens=8_000),
            ),
            timeout=timeout_seconds,
        )
        structured = getattr(result, "structured_output", None)
        if not isinstance(structured, AgentEvaluationResult):
            raise ValueError("evaluator did not return structured output")
    except Exception as exc:
        mark_provider_failure(model)
        provider_metadata = actual_provider_metadata(model)
        if event_sink is not None:
            event_sink.emit(
                AgentOperationEvent(
                    event_type=AgentOperationEventType.EVALUATION_COMPLETED,
                    case_id=case_id,
                    trace_id=trace_id,
                    actor="evaluator",
                    operation_id=operation_id,
                    status="FAILED",
                    correlation_id=trace_id,
                    stage=AgentStage.EVALUATOR.value,
                    payload={
                        "error_code": type(exc).__name__,
                        "provider_metadata": provider_metadata,
                    },
                )
            )
        raise
    provider_metadata = actual_provider_metadata(model)
    if provider_metadata.get("invocation_proof") == "returned":
        provider_metadata["status"] = "COMPLETE"
        provider_metadata["invocation_status"] = "COMPLETED"
    if event_sink is not None:
        event_sink.emit(
            AgentOperationEvent(
                event_type=AgentOperationEventType.EVALUATION_COMPLETED,
                case_id=case_id,
                trace_id=trace_id,
                actor="evaluator",
                operation_id=operation_id,
                status=structured.decision.value,
                correlation_id=trace_id,
                stage=AgentStage.EVALUATOR.value,
                payload={
                    "decision": structured.decision.value,
                    "failed_invariants": list(structured.failed_invariants),
                    "provider_metadata": provider_metadata,
                },
            )
        )
    return EvaluationRun(
        result=structured,
        model_result=result,
        audit=ToolAudit(),
        retry_count=_structured_retry_count(result),
        provider_metadata=provider_metadata,
    )
