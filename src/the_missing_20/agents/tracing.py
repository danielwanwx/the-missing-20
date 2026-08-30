"""Portable normalized traces for the bounded agent workflow."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from the_missing_20.agents.schemas import (
    AGENT_CONTRACT_VERSION,
    EVALUATOR_VERSION,
    HARNESS_VERSION,
    TRACE_VERSION,
    AgentProtocolEnvelope,
    AgentStageTrace,
    EvaluatorCitationClosure,
    EvaluatorSourceCoverage,
    KnowledgeCitation,
    validate_protocol_envelope,
)
from the_missing_20.agents.tools import ToolAudit


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def normalize_stage_trace(
    *,
    stage: str,
    result: Any,
    audit: ToolAudit,
    read_evidence_ids: tuple[str, ...] = (),
    knowledge_citations: tuple[KnowledgeCitation, ...] = (),
    retry_count: int = 0,
    deterministic: bool = False,
    evaluator_source_coverage: EvaluatorSourceCoverage | None = None,
    evaluator_citation_closure: EvaluatorCitationClosure | None = None,
    protocol: AgentProtocolEnvelope | None = None,
) -> AgentStageTrace:
    """Extract only stable SDK metrics and audited tool metadata."""

    usage = getattr(getattr(result, "metrics", None), "accumulated_usage", {}) or {}
    metrics = getattr(getattr(result, "metrics", None), "accumulated_metrics", {}) or {}
    if protocol is not None:
        validate_protocol_envelope(protocol)
    return AgentStageTrace(
        stage=stage,
        outcome=str(getattr(result, "stop_reason", "unknown")),
        tool_calls=tuple(call["tool"] for call in audit.calls),
        tool_call_details=tuple(
            {
                "tool": call["tool"],
                "arguments": call["arguments"],
                "result_evidence_ids": call["result_evidence_ids"],
                "result_knowledge_records": call.get("result_knowledge_records", []),
                "result_digest": call["result_digest"],
                "error_code": call["error_code"],
                "duration_ms": 0 if deterministic else call["duration_ms"],
            }
            for call in audit.calls
        ),
        read_evidence_ids=tuple(sorted(set(read_evidence_ids))),
        knowledge_citations=tuple(
            sorted(
                knowledge_citations,
                key=lambda item: (item.knowledge_id, item.version, item.allowed_use.value),
            )
        ),
        request_count=int(getattr(getattr(result, "metrics", None), "cycle_count", 0)),
        retry_count=retry_count,
        input_tokens=int(usage.get("inputTokens", 0)),
        output_tokens=int(usage.get("outputTokens", 0)),
        latency_ms=0 if deterministic else int(metrics.get("latencyMs", 0)),
        evaluator_source_coverage=evaluator_source_coverage,
        evaluator_citation_closure=evaluator_citation_closure,
        protocol=protocol,
    )


@dataclass(slots=True)
class NormalizedTrace:
    """In-memory trace that intentionally excludes prompts, messages, and raw SDK events."""

    run_id: str
    case_id: str
    trace_id: str
    provider: str
    model: str
    # Safe, redacted provider/request metadata.  This deliberately carries no
    # prompt, response, credential, or enterprise payload.
    provider_metadata: dict[str, Any] | None = None
    prompt_version: str = "agent-v5"
    prompt_digest: str = "prompt-digest-unavailable"
    knowledge_version: str = "knowledge-v1"
    harness_version: str = HARNESS_VERSION
    evaluator_version: str = EVALUATOR_VERSION
    agent_contract_version: str = AGENT_CONTRACT_VERSION
    protocol: AgentProtocolEnvelope | None = None
    request_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    stop_reason: str = "ASSESSMENT_VALIDATED"
    knowledge_citations: list[KnowledgeCitation] = field(default_factory=list)
    coverage_ledger: dict[str, Any] | None = None
    evaluator_source_coverage: dict[str, Any] | None = None
    evaluator_citation_closure: dict[str, Any] | None = None
    action_recommendation: dict[str, Any] | None = None
    stages: list[AgentStageTrace] = field(default_factory=list)

    @property
    def source_coverage(self) -> dict[str, Any] | None:
        return self.evaluator_source_coverage

    @property
    def citation_closure(self) -> dict[str, Any] | None:
        return self.evaluator_citation_closure

    def add(self, stage: AgentStageTrace) -> None:
        if self.protocol is not None:
            if stage.protocol != self.protocol:
                raise ValueError("stage trace protocol envelope mismatch")
        elif stage.protocol is not None:
            self.protocol = stage.protocol
        if stage.evaluator_source_coverage is not None:
            if (
                self.evaluator_source_coverage is not None
                and self.evaluator_source_coverage
                != stage.evaluator_source_coverage.model_dump(mode="json")
            ):
                raise ValueError("stage source coverage does not match trace coverage")
            self.evaluator_source_coverage = stage.evaluator_source_coverage.model_dump(mode="json")
        if stage.evaluator_citation_closure is not None:
            closure = stage.evaluator_citation_closure.model_dump(mode="json")
            if (
                self.evaluator_citation_closure is not None
                and self.evaluator_citation_closure != closure
            ):
                raise ValueError("stage citation closure does not match trace closure")
            self.evaluator_citation_closure = closure
        self.stages.append(stage)
        citations = {(item.knowledge_id, item.version): item for item in self.knowledge_citations}
        citations.update(
            {(item.knowledge_id, item.version): item for item in stage.knowledge_citations}
        )
        self.knowledge_citations = [
            citations[key] for key in sorted(citations, key=lambda value: (value[0], value[1]))
        ]
        self.request_count += stage.request_count
        self.input_tokens += stage.input_tokens
        self.output_tokens += stage.output_tokens

    @property
    def schema_digest(self) -> str:
        if self.protocol is not None:
            return self.protocol.schema_digest
        return _digest(
            {
                "agent_contract_version": self.agent_contract_version,
                "action_policy_version": (
                    self.action_recommendation.get("policy_version")
                    if self.action_recommendation
                    else "action-policy/v2"
                ),
                "investigator": "InvestigatorResult",
                "synthesis": "SynthesisResult",
                "evaluator": "AgentEvaluationResult",
            }
        )

    def public(self) -> dict[str, Any]:
        if self.protocol is not None:
            validate_protocol_envelope(
                self.protocol,
                prompt_version=self.prompt_version,
                prompt_digest=self.prompt_digest,
                knowledge_version=self.knowledge_version,
            )
            if (
                self.agent_contract_version != self.protocol.agent_contract_version
                or self.prompt_version != self.protocol.prompt_version
                or self.prompt_digest != self.protocol.prompt_digest
                or self.knowledge_version != self.protocol.knowledge_version
                or self.harness_version != self.protocol.harness_version
                or self.evaluator_version != self.protocol.evaluator_version
            ):
                raise ValueError("trace protocol envelope metadata mismatch")
        stage_coverages = [
            stage.evaluator_source_coverage.model_dump(mode="json")
            for stage in self.stages
            if stage.evaluator_source_coverage is not None
        ]
        if stage_coverages and any(item != stage_coverages[0] for item in stage_coverages[1:]):
            raise ValueError("trace contains inconsistent evaluator source coverage")
        if (
            self.evaluator_source_coverage is not None
            and stage_coverages
            and self.evaluator_source_coverage != stage_coverages[0]
        ):
            raise ValueError("trace source coverage does not match evaluator stage")
        stage_closures = [
            stage.evaluator_citation_closure.model_dump(mode="json")
            for stage in self.stages
            if stage.evaluator_citation_closure is not None
        ]
        if stage_closures and any(item != stage_closures[0] for item in stage_closures[1:]):
            raise ValueError("trace contains inconsistent evaluator citation closure")
        if (
            self.evaluator_citation_closure is not None
            and stage_closures
            and self.evaluator_citation_closure != stage_closures[0]
        ):
            raise ValueError("trace citation closure does not match evaluator stage")
        return {
            "schema_version": TRACE_VERSION,
            "run_id": self.run_id,
            "case_id": self.case_id,
            "trace_id": self.trace_id,
            "provider": self.provider,
            "model": self.model,
            "provider_metadata": self.provider_metadata,
            "prompt_version": self.prompt_version,
            "prompt_digest": self.prompt_digest,
            "agent_contract_version": self.agent_contract_version,
            "schema_digest": self.schema_digest,
            "knowledge_version": self.knowledge_version,
            "harness_version": self.harness_version,
            "evaluator_version": self.evaluator_version,
            "protocol": (
                self.protocol.model_dump(mode="json") if self.protocol is not None else None
            ),
            "request_count": self.request_count,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "knowledge_citations": [
                item.model_dump(mode="json") for item in self.knowledge_citations
            ],
            "coverage_ledger": self.coverage_ledger,
            "evaluator_source_coverage": self.evaluator_source_coverage,
            "source_coverage": self.evaluator_source_coverage,
            "evaluator_citation_closure": self.evaluator_citation_closure,
            "citation_closure": self.evaluator_citation_closure,
            "action_recommendation": self.action_recommendation,
            "stop_reason": self.stop_reason,
            "stages": [stage.model_dump(mode="json") for stage in self.stages],
        }
