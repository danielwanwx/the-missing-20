"""Application-owned Strands workflow with deterministic safety gates."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from the_missing_20.agents.evaluator import EvaluationRun, run_evaluator
from the_missing_20.agents.events import (
    AgentEventSink,
    AgentOperationEvent,
    AgentOperationEventType,
)
from the_missing_20.agents.investigators import (
    InvestigatorRun,
    default_tool_plan,
    run_investigator,
)
from the_missing_20.agents.policy import (
    ActionRecommendation,
    ActionRecommendationPolicy,
    EvidenceCoverageLedger,
    build_evidence_coverage_ledger,
)
from the_missing_20.agents.prompts import PromptSet
from the_missing_20.agents.schemas import (
    AGENT_CONTRACT_VERSION,
    EVALUATOR_VERSION,
    HARNESS_VERSION,
    HYPOTHESIS_TO_INVESTIGATOR,
    AgentEvaluationResult,
    AgentProtocolEnvelope,
    ClaimRelation,
    EvaluatorCitationClosure,
    EvaluatorSourceCoverage,
    InvestigatorID,
    InvestigatorResult,
    KnowledgeCitation,
    SourceAvailabilitySet,
    SynthesisResult,
    build_protocol_envelope,
    derive_preserved_dissent,
    public_investigator_result,
    public_synthesis_result,
)
from the_missing_20.agents.synthesis import SynthesisRun, run_synthesis
from the_missing_20.agents.tools import ToolScope
from the_missing_20.agents.tracing import NormalizedTrace, normalize_stage_trace
from the_missing_20.agents.validation import (
    AgentEvidenceValidator,
    AgentStageFailure,
    AgentValidationError,
    build_evaluator_citation_closure,
    build_evaluator_source_coverage,
    stable_agent_error_code,
)
from the_missing_20.domain.models import (
    EvidenceItem,
    EvidenceSourceType,
    HypothesisConclusion,
    HypothesisType,
    InvestigationAssessment,
)
from the_missing_20.ports.agent_model import (
    AgentBudget,
    AgentModelFactory,
    AgentProvider,
    AgentStage,
)
from the_missing_20.ports.knowledge import KnowledgeRepository

PROMPT_VERSION = "agent-v5"
FIXED_ASSESSMENT_TIME = datetime(2026, 8, 26, 0, 0, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class HarnessRun:
    assessment: InvestigationAssessment
    investigators: tuple[InvestigatorResult, ...]
    investigator_knowledge_citations: tuple[tuple[KnowledgeCitation, ...], ...]
    investigator_read_evidence_ids: tuple[tuple[str, ...], ...]
    synthesis: SynthesisResult
    evaluation: AgentEvaluationResult
    evaluator_citation_closure: EvaluatorCitationClosure
    evaluator_source_coverage: EvaluatorSourceCoverage
    coverage_ledger: EvidenceCoverageLedger
    action_recommendation: ActionRecommendation
    trace: NormalizedTrace
    protocol: AgentProtocolEnvelope

    def public(self) -> dict[str, Any]:
        ledger = self.coverage_ledger.model_dump(mode="json")
        claim_groups = ledger["selected_claim_ids_by_relation"]
        ledger["claim_ids_by_relation"] = claim_groups
        ledger["validated_claim_ids_by_relation"] = claim_groups
        return {
            "schema_version": "agent-run/v2",
            "run_id": self.trace.run_id,
            "case_id": self.assessment.case_id,
            "trace_id": self.assessment.trace_id,
            "provider": self.trace.provider,
            "model": self.trace.model,
            "prompt_version": self.trace.prompt_version,
            "agent_contract_version": self.trace.agent_contract_version,
            "schema_digest": self.trace.schema_digest,
            "knowledge_version": self.trace.knowledge_version,
            "harness_version": self.trace.harness_version,
            "evaluator_version": self.trace.evaluator_version,
            "protocol": self.protocol.model_dump(mode="json"),
            "investigators": [
                public_investigator_result(
                    item,
                    missing_evidence_sources=self.assessment.missing_evidence_sources,
                    knowledge_citations=knowledge_citations,
                    read_evidence_ids=read_ids,
                    protocol=self.protocol,
                )
                for item, knowledge_citations, read_ids in zip(
                    self.investigators,
                    self.investigator_knowledge_citations,
                    self.investigator_read_evidence_ids,
                    strict=True,
                )
            ],
            "synthesis": public_synthesis_result(
                self.synthesis,
                missing_evidence_sources=self.assessment.missing_evidence_sources,
                preserved_dissent=derive_preserved_dissent(self.investigators),
                protocol=self.protocol,
            ),
            "evaluation": {
                **self.evaluation.model_dump(mode="json"),
                "evaluator_version": self.protocol.evaluator_version,
                "evaluator_citation_closure": self.evaluator_citation_closure.model_dump(
                    mode="json"
                ),
                "evaluator_source_coverage": self.evaluator_source_coverage.model_dump(mode="json"),
                "source_coverage": self.evaluator_source_coverage.model_dump(mode="json"),
                "protocol": self.protocol.model_dump(mode="json"),
            },
            "evaluator_source_coverage": self.evaluator_source_coverage.model_dump(mode="json"),
            "evaluator_citation_closure": self.evaluator_citation_closure.model_dump(mode="json"),
            "coverage_ledger": ledger,
            "action_recommendation": self.action_recommendation.model_dump(mode="json"),
            "assessment": self.assessment.model_dump(mode="json"),
            "trace": self.trace.public(),
        }


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _usage_metric(result: Any, name: str) -> int:
    metrics = getattr(result, "metrics", None)
    usage = getattr(metrics, "accumulated_usage", {}) if metrics is not None else {}
    return int((usage or {}).get(name, 0))


def _claim_payload(
    *,
    hypothesis: HypothesisType,
    evidence: tuple[EvidenceItem, ...],
    missing: tuple[str, ...],
    relation: ClaimRelation = ClaimRelation.SUPPORTS_HYPOTHESIS,
) -> tuple[dict[str, Any], ...]:
    if (
        missing
        or not evidence
        or hypothesis
        not in {
            HypothesisType.RETRYABLE_MESSAGE,
            HypothesisType.GENUINE_SHORT_SHIPMENT,
            HypothesisType.ALREADY_POSTED,
        }
    ):
        return ()
    ids = tuple(sorted(item.evidence_id for item in evidence))
    statement = {
        HypothesisType.RETRYABLE_MESSAGE: (
            "The admitted records support a retryable receipt message."
        ),
        HypothesisType.GENUINE_SHORT_SHIPMENT: (
            "The admitted records support a physical short shipment."
        ),
        HypothesisType.ALREADY_POSTED: "The admitted records support an already-posted receipt.",
    }[hypothesis]
    if relation is ClaimRelation.CONTRADICTS_HYPOTHESIS:
        statement = statement.replace("support", "contradict")
    elif relation is ClaimRelation.CONTEXT_ONLY:
        statement = statement.replace("support", "provide context for")
    return (
        {
            "claim_id": f"{hypothesis.value.lower()}-{relation.value.lower()}-evidence",
            "statement": statement,
            "relation": relation.value,
            "evidence_ids": ids,
        },
    )


def _profile_outputs(
    *,
    evidence: tuple[EvidenceItem, ...],
    trace_id: str,
    source_availability: SourceAvailabilitySet,
) -> tuple[
    dict[InvestigatorID, dict[str, Any]],
    dict[str, Any],
    dict[str, Any],
]:
    """Build deterministic offline provider payloads without a diagnosis oracle.

    The scripted provider is a frozen stand-in for model responses.  It mirrors the
    synthetic profile outcomes, while validators and the action policy—not this
    fixture builder—remain authoritative for eligibility.
    """

    del trace_id
    missing = source_availability.missing_evidence_sources
    by_source = {item.source_type: item for item in evidence}
    selected = HypothesisType.RETRYABLE_MESSAGE
    conclusion = HypothesisConclusion.SUPPORTED
    confidence = "HIGH"
    evaluator_decision = "ACCEPT"
    evaluator_failed: tuple[str, ...] = ()
    if missing:
        conclusion = HypothesisConclusion.NEEDS_EVIDENCE
        confidence = "LOW"
        evaluator_decision = "MORE_EVIDENCE"
        evaluator_failed = ("required_evidence_missing",)
    else:
        queue = by_source[EvidenceSourceType.FAILED_MESSAGE_QUEUE].admitted_fields
        material = by_source[EvidenceSourceType.MATERIAL_DOCUMENT].admitted_fields
        warehouse_quantity = by_source[EvidenceSourceType.WAREHOUSE].admitted_fields.get("quantity")
        erp_quantity = by_source[EvidenceSourceType.ERP_RECEIPT].admitted_fields.get("quantity")
        invoice_quantity = by_source[EvidenceSourceType.INVOICE].admitted_fields.get("quantity")
        if queue.get("status") == "CONSUMED" and material.get("material_documents"):
            selected = HypothesisType.ALREADY_POSTED
        elif (
            isinstance(warehouse_quantity, int)
            and not isinstance(warehouse_quantity, bool)
            and warehouse_quantity == erp_quantity
            and isinstance(invoice_quantity, int)
            and not isinstance(invoice_quantity, bool)
            and warehouse_quantity < invoice_quantity
        ):
            selected = HypothesisType.GENUINE_SHORT_SHIPMENT
            evaluator_decision = "REJECT"
            evaluator_failed = ("physical_quantity_below_ordered_quantity",)
    selected_role = HYPOTHESIS_TO_INVESTIGATOR[selected]
    all_ids = tuple(sorted(item.evidence_id for item in evidence))
    outputs: dict[InvestigatorID, dict[str, Any]] = {}
    for role, role_hypothesis in (
        (InvestigatorID.RETRYABLE_MESSAGE, HypothesisType.RETRYABLE_MESSAGE),
        (InvestigatorID.SHORT_SHIPMENT, HypothesisType.GENUINE_SHORT_SHIPMENT),
        (InvestigatorID.DUPLICATE_POSTING, HypothesisType.ALREADY_POSTED),
    ):
        is_selected = role is selected_role
        claims: tuple[dict[str, Any], ...]
        if is_selected:
            role_conclusion = conclusion
            role_confidence = confidence
            claims = (
                _claim_payload(hypothesis=selected, evidence=evidence, missing=tuple(missing))
                if role_conclusion is HypothesisConclusion.SUPPORTED
                else ()
            )
        else:
            role_conclusion = HypothesisConclusion.REJECTED
            role_confidence = confidence
            claims = (
                _claim_payload(
                    hypothesis=role_hypothesis,
                    evidence=evidence,
                    missing=(),
                    relation=ClaimRelation.CONTRADICTS_HYPOTHESIS,
                )
                if all_ids
                else ()
            )
        outputs[role] = {
            "investigator_id": role.value,
            "hypothesis_type": role_hypothesis.value,
            "conclusion": (
                role_conclusion.value if hasattr(role_conclusion, "value") else role_conclusion
            ),
            "confidence_band": (
                role_confidence.value if hasattr(role_confidence, "value") else role_confidence
            ),
            "factual_claims": list(claims),
        }
    selected_result = InvestigatorResult.model_validate(outputs[selected_role])
    synthesis = {
        "selected_hypothesis": selected.value,
        "conclusion": conclusion.value,
        "confidence_band": confidence,
        # Strands serializes the structured-output tool input as JSON primitives.  Do
        # not pass strict Pydantic objects here; the real StructuredOutputTool will
        # reconstruct and validate them at the SDK boundary.
        "factual_claims": [
            claim.model_dump(mode="json") for claim in selected_result.factual_claims
        ],
    }
    evaluator = {
        "decision": evaluator_decision,
        "validated_claim_ids": [
            claim["claim_id"]
            for claim in (
                _claim_payload(
                    hypothesis=selected,
                    evidence=evidence,
                    missing=tuple(missing),
                )
                if conclusion is HypothesisConclusion.SUPPORTED
                else ()
            )
        ],
        "failed_invariants": list(evaluator_failed),
    }
    return outputs, synthesis, evaluator


def _retryable_stage_error(error: BaseException) -> bool:
    if isinstance(error, (AgentValidationError, ValueError, TimeoutError, asyncio.TimeoutError)):
        return True
    # Keep the SDK optional for commands that only run deterministic Golden v1.
    if type(error).__name__ == "StructuredOutputException":
        return True
    original = getattr(error, "original_exception", None)
    return isinstance(original, BaseException) and _retryable_stage_error(original)


def _stage_failure(
    error: BaseException,
    *,
    stage: AgentStage,
    role: InvestigatorID | None = None,
) -> AgentStageFailure:
    """Attach only stable stage metadata; provider/model prose stays out of manifests."""

    expected_stage = stage.value
    expected_role = role.value if role is not None else None
    if (
        isinstance(error, AgentStageFailure)
        and error.stage == expected_stage
        and error.role == expected_role
    ):
        return error
    return AgentStageFailure(
        str(error),
        stage=expected_stage,
        role=expected_role,
        validator_code=stable_agent_error_code(error),
    )


async def _run_checked_once[T](
    operation: Callable[[], Awaitable[T]],
    check: Callable[[T], Any],
    *,
    allow_retry: bool = True,
) -> tuple[T, Any]:
    """Run a stage with the caller's bounded retry policy."""

    attempts = 2 if allow_retry else 1
    for attempt in range(attempts):
        try:
            result = await operation()
            checked = check(result)
        except Exception as error:
            if attempt == attempts - 1 or not allow_retry or not _retryable_stage_error(error):
                raise
            continue
        provider_retries = int(getattr(result, "retry_count", 0))
        if not allow_retry and provider_retries:
            raise AgentValidationError("advisory stage reported a corrective provider retry")
        used_retries = max(attempt, provider_retries)
        if used_retries > 1:
            raise AgentValidationError("stage exceeded the one-retry budget")
        if used_retries and provider_retries != used_retries:
            result = cast(T, replace(cast(Any, result), retry_count=used_retries))
        return result, checked
    raise AssertionError("bounded stage retry loop did not return or raise")


class AgentHarness:
    """Run the fixed three-investigator, synthesis, evaluator workflow."""

    def __init__(
        self,
        *,
        model_factory: AgentModelFactory,
        knowledge: KnowledgeRepository,
        source_availability: SourceAvailabilitySet,
        budget: AgentBudget | None = None,
        prompt_root: Path | None = None,
        allow_stage_retries: bool = True,
        event_sink: AgentEventSink | None = None,
    ) -> None:
        self.model_factory = model_factory
        self.knowledge = knowledge
        self.source_availability = source_availability
        self.budget = budget or AgentBudget()
        self.prompt_root = prompt_root
        self.allow_stage_retries = allow_stage_retries
        self.event_sink = event_sink

    def _emit(
        self,
        *,
        event_type: AgentOperationEventType,
        case_id: str,
        trace_id: str,
        actor: str,
        operation_id: str,
        status: str,
        correlation_id: str,
        stage: AgentStage | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Forward one actual-operation event to the configured durable sink."""

        if self.event_sink is None:
            return
        self.event_sink.emit(
            AgentOperationEvent(
                event_type=event_type,
                case_id=case_id,
                trace_id=trace_id,
                actor=actor,
                operation_id=operation_id,
                status=status,
                correlation_id=correlation_id,
                stage=stage.value if stage is not None else None,
                payload=payload or {},
            )
        )

    async def run_async(
        self,
        *,
        case_id: str,
        trace_id: str,
        evidence: tuple[EvidenceItem, ...],
        assessed_at: datetime = FIXED_ASSESSMENT_TIME,
    ) -> HarnessRun:
        if not evidence:
            raise AgentValidationError("agent harness requires admitted evidence")
        if any(item.case_id != case_id or item.trace_id != trace_id for item in evidence):
            raise AgentValidationError("agent evidence does not match case and trace")
        prompts = PromptSet.load(self.prompt_root)
        protocol = build_protocol_envelope(
            prompt_version=prompts.version,
            prompt_digest=prompts.digest,
            knowledge_version=self.knowledge.version,
        )
        scope = ToolScope(
            case_id=case_id,
            trace_id=trace_id,
            admitted_evidence=evidence,
            allowed_evidence_ids=frozenset(item.evidence_id for item in evidence),
            knowledge=self.knowledge,
            knowledge_version=self.knowledge.version,
        )
        scripted_outputs, synthesis_payload, evaluator_payload = _profile_outputs(
            evidence=evidence,
            trace_id=trace_id,
            source_availability=self.source_availability,
        )
        validator = AgentEvidenceValidator(
            evidence,
            trace_id=trace_id,
            source_availability=self.source_availability,
            knowledge=self.knowledge,
        )
        roles = (
            (InvestigatorID.RETRYABLE_MESSAGE, AgentStage.RETRYABLE_INVESTIGATOR),
            (InvestigatorID.SHORT_SHIPMENT, AgentStage.SHORT_SHIPMENT_INVESTIGATOR),
            (InvestigatorID.DUPLICATE_POSTING, AgentStage.DUPLICATE_POSTING_INVESTIGATOR),
        )

        async def invoke(role: InvestigatorID, stage: AgentStage) -> InvestigatorRun:
            attempt = 0
            operation_id = f"agent:{stage.value}:attempt:1"
            self._emit(
                event_type=AgentOperationEventType.AGENT_STARTED,
                case_id=case_id,
                trace_id=trace_id,
                actor=role.value,
                operation_id=operation_id,
                status="RUNNING",
                correlation_id=trace_id,
                stage=stage,
                payload={"stage": stage.value, "mode": "SCRIPTED_SYNTHETIC"},
            )

            async def operation() -> InvestigatorRun:
                nonlocal attempt
                attempt += 1
                operation_id = f"agent:{stage.value}:attempt:{attempt}"
                if attempt > 1:
                    self._emit(
                        event_type=AgentOperationEventType.AGENT_STARTED,
                        case_id=case_id,
                        trace_id=trace_id,
                        actor=role.value,
                        operation_id=operation_id,
                        status="RUNNING",
                        correlation_id=trace_id,
                        stage=stage,
                        payload={"stage": stage.value, "mode": "SCRIPTED_SYNTHETIC"},
                    )
                return await run_investigator(
                    role=role,
                    stage=stage,
                    model_factory=self.model_factory,
                    output_payload=scripted_outputs[role],
                    tool_plan=default_tool_plan(scope),
                    scope=scope,
                    source_availability=self.source_availability,
                    event_sink=self.event_sink,
                    operation_prefix=f"{stage.value}:attempt:{attempt}",
                    system_prompt=prompts.investigator,
                    timeout_seconds=self.budget.per_call_timeout_seconds,
                )

            try:
                run, _ = await _run_checked_once(
                    operation,
                    lambda result: validator.validate_investigator(
                        result.result,
                        read_evidence_ids=result.read_evidence_ids,
                    ),
                    allow_retry=self.allow_stage_retries,
                )
                self._emit(
                    event_type=AgentOperationEventType.AGENT_COMPLETED,
                    case_id=case_id,
                    trace_id=trace_id,
                    actor=role.value,
                    operation_id=f"agent:{stage.value}:attempt:{attempt}",
                    status="COMPLETED",
                    correlation_id=trace_id,
                    stage=stage,
                    payload={
                        "read_evidence_ids": list(run.read_evidence_ids),
                        "knowledge_citation_count": len(run.knowledge_citations),
                    },
                )
                self._emit(
                    event_type=AgentOperationEventType.AGENT_HANDOFF,
                    case_id=case_id,
                    trace_id=trace_id,
                    actor=role.value,
                    operation_id=f"handoff:{stage.value}:attempt:{attempt}",
                    status="HANDED_OFF",
                    correlation_id=trace_id,
                    stage=stage,
                    payload={
                        "target": AgentStage.SYNTHESIS.value,
                        "evidence_ids": list(run.read_evidence_ids),
                    },
                )
                return run
            except Exception as error:
                self._emit(
                    event_type=AgentOperationEventType.AGENT_COMPLETED,
                    case_id=case_id,
                    trace_id=trace_id,
                    actor=role.value,
                    operation_id=f"agent:{stage.value}:attempt:{max(attempt, 1)}",
                    status="FAILED",
                    correlation_id=trace_id,
                    stage=stage,
                    payload={"error_code": type(error).__name__},
                )
                raise _stage_failure(error, stage=stage, role=role) from error

        # The fixed topology is application-owned; the three independent agents are the
        # only concurrent branch in the workflow.
        investigator_runs = cast(
            tuple[InvestigatorRun, InvestigatorRun, InvestigatorRun],
            await asyncio.wait_for(
                asyncio.gather(*(invoke(role, stage) for role, stage in roles)),
                timeout=self.budget.whole_run_timeout_seconds,
            ),
        )
        _assert_fixed_investigator_runs(investigator_runs, roles)
        validated_investigators = tuple(
            validator.validate_investigator(
                run.result,
                read_evidence_ids=run.read_evidence_ids,
            )
            for run in investigator_runs
        )
        investigator_knowledge_citations = tuple(
            run.knowledge_citations for run in investigator_runs
        )
        try:
            synthesis_attempt = 0

            async def synthesis_operation() -> SynthesisRun:
                nonlocal synthesis_attempt
                synthesis_attempt += 1
                return await run_synthesis(
                    model_factory=self.model_factory,
                    output_payload=synthesis_payload,
                    investigators=validated_investigators,
                    case_id=case_id,
                    trace_id=trace_id,
                    source_availability=self.source_availability,
                    investigator_knowledge_citations=investigator_knowledge_citations,
                    investigator_read_evidence_ids=tuple(
                        run.read_evidence_ids for run in investigator_runs
                    ),
                    event_sink=self.event_sink,
                    operation_id=f"synthesis:{trace_id}:attempt:{synthesis_attempt}",
                    system_prompt=prompts.synthesis,
                    timeout_seconds=self.budget.per_call_timeout_seconds,
                )

            synthesis_run, synthesis = await _run_checked_once(
                synthesis_operation,
                lambda result: validator.validate_synthesis(result.result, validated_investigators),
                allow_retry=self.allow_stage_retries,
            )
        except Exception as error:
            raise _stage_failure(error, stage=AgentStage.SYNTHESIS) from error
        try:
            evaluator_attempt = 0

            async def evaluator_operation() -> EvaluationRun:
                nonlocal evaluator_attempt
                evaluator_attempt += 1
                return await run_evaluator(
                    model_factory=self.model_factory,
                    output_payload=evaluator_payload,
                    synthesis=synthesis,
                    investigator_knowledge_citations=investigator_knowledge_citations,
                    investigator_read_evidence_ids=tuple(
                        run.read_evidence_ids for run in investigator_runs
                    ),
                    admitted_evidence_ids=tuple(sorted(item.evidence_id for item in evidence)),
                    source_types=tuple(sorted(item.source_type.value for item in evidence)),
                    case_id=case_id,
                    trace_id=trace_id,
                    source_availability=self.source_availability,
                    event_sink=self.event_sink,
                    operation_id=f"evaluator:{trace_id}:attempt:{evaluator_attempt}",
                    preserved_dissent=derive_preserved_dissent(validated_investigators),
                    system_prompt=prompts.evaluator,
                    timeout_seconds=self.budget.per_call_timeout_seconds,
                )

            evaluation_run, evaluation = await _run_checked_once(
                evaluator_operation,
                lambda result: validator.validate_evaluator(result.result, synthesis),
                allow_retry=self.allow_stage_retries,
            )
        except Exception as error:
            raise _stage_failure(error, stage=AgentStage.EVALUATOR) from error
        try:
            evaluator_citation_closure = build_evaluator_citation_closure(
                evidence=evidence,
                synthesis=synthesis,
                validated_claim_ids=evaluation.validated_claim_ids,
                source_availability=self.source_availability,
                case_id=case_id,
                trace_id=trace_id,
                protocol=protocol,
            )
            if evaluation.decision.value == "ACCEPT" and (
                not evaluator_citation_closure.all_synthesis_claims_validated
                or not evaluator_citation_closure.all_admitted_evidence_covered
            ):
                raise AgentValidationError(
                    "accepted synthesis does not have complete citation closure"
                )
            evaluator_source_coverage = build_evaluator_source_coverage(
                evidence=evidence,
                source_availability=self.source_availability,
                citation_closure=evaluator_citation_closure,
                case_id=case_id,
                trace_id=trace_id,
                protocol=protocol,
            )
        except Exception as error:
            raise _stage_failure(error, stage=AgentStage.EVALUATOR) from error
        selected_role = HYPOTHESIS_TO_INVESTIGATOR[synthesis.selected_hypothesis]
        selected_index = next(
            index
            for index, item in enumerate(validated_investigators)
            if item.investigator_id is selected_role
        )
        selected_investigator = validated_investigators[selected_index]
        selected_read_ids = investigator_runs[selected_index].read_evidence_ids
        coverage_ledger = build_evidence_coverage_ledger(
            evidence=evidence,
            source_availability=self.source_availability,
            selected_hypothesis=synthesis.selected_hypothesis,
            selected_investigator=selected_investigator,
            selected_investigator_read_ids=selected_read_ids,
            evaluator=evaluation,
            selected_synthesis=synthesis,
            evaluator_citation_closure=evaluator_citation_closure,
            evaluator_source_coverage=evaluator_source_coverage,
            protocol=protocol,
        )
        action_recommendation = ActionRecommendationPolicy.evaluate(
            synthesis=synthesis,
            investigators=validated_investigators,
            evaluator=evaluation,
            evidence=evidence,
            ledger=coverage_ledger,
            evaluator_citation_closure=evaluator_citation_closure,
            evaluator_source_coverage=evaluator_source_coverage,
        )
        action_recommendation = action_recommendation.model_copy(update={"protocol": protocol})
        coverage_ledger = coverage_ledger.model_copy(
            update={"outcome_reason": action_recommendation.reason_code}
        )
        assessment = validator.build_assessment(
            assessment_id=f"assessment:agent:{case_id}",
            case_id=case_id,
            synthesis=synthesis,
            evaluation=evaluation,
            assessed_at=assessed_at,
            protocol=protocol,
            citation_closure=evaluator_citation_closure,
            recommendation=action_recommendation,
        )
        provider = self.model_factory.provider.value
        model = (
            "scripted-strands-v1"
            if provider == AgentProvider.SCRIPTED.value
            else "us.amazon.nova-pro-v1:0"
        )
        trace = NormalizedTrace(
            run_id=f"agent-run:{case_id}",
            case_id=case_id,
            trace_id=trace_id,
            provider=provider,
            model=model,
            prompt_version=prompts.version,
            prompt_digest=prompts.digest,
            knowledge_version=self.knowledge.version,
            harness_version=HARNESS_VERSION,
            evaluator_version=EVALUATOR_VERSION,
            agent_contract_version=AGENT_CONTRACT_VERSION,
            stop_reason="ASSESSMENT_VALIDATED",
            evaluator_source_coverage=evaluator_source_coverage.model_dump(mode="json"),
            evaluator_citation_closure=evaluator_citation_closure.model_dump(mode="json"),
            coverage_ledger=coverage_ledger.model_dump(mode="json"),
            action_recommendation=action_recommendation.model_dump(mode="json"),
            protocol=protocol,
        )
        deterministic = self.model_factory.provider is AgentProvider.SCRIPTED
        for (role, stage), run in zip(roles, investigator_runs, strict=True):
            del role
            trace.add(
                normalize_stage_trace(
                    stage=stage.value,
                    result=run.model_result,
                    audit=run.audit,
                    read_evidence_ids=run.read_evidence_ids,
                    knowledge_citations=run.knowledge_citations,
                    retry_count=run.retry_count,
                    deterministic=deterministic,
                    protocol=protocol,
                )
            )
        trace.add(
            normalize_stage_trace(
                stage=AgentStage.SYNTHESIS.value,
                result=synthesis_run.model_result,
                audit=synthesis_run.audit,
                retry_count=synthesis_run.retry_count,
                deterministic=deterministic,
                protocol=protocol,
            )
        )
        trace.add(
            normalize_stage_trace(
                stage=AgentStage.EVALUATOR.value,
                result=evaluation_run.model_result,
                audit=evaluation_run.audit,
                retry_count=evaluation_run.retry_count,
                deterministic=deterministic,
                evaluator_source_coverage=evaluator_source_coverage,
                evaluator_citation_closure=evaluator_citation_closure,
                protocol=protocol,
            )
        )
        return HarnessRun(
            assessment=assessment,
            investigators=validated_investigators,
            synthesis=synthesis,
            evaluation=evaluation,
            evaluator_citation_closure=evaluator_citation_closure,
            evaluator_source_coverage=evaluator_source_coverage,
            investigator_knowledge_citations=investigator_knowledge_citations,
            investigator_read_evidence_ids=tuple(
                run.read_evidence_ids for run in investigator_runs
            ),
            coverage_ledger=coverage_ledger,
            action_recommendation=action_recommendation,
            trace=trace,
            protocol=protocol,
        )

    def run(
        self,
        *,
        case_id: str,
        trace_id: str,
        evidence: tuple[EvidenceItem, ...],
        assessed_at: datetime = FIXED_ASSESSMENT_TIME,
    ) -> HarnessRun:
        return asyncio.run(
            self.run_async(
                case_id=case_id,
                trace_id=trace_id,
                evidence=evidence,
                assessed_at=assessed_at,
            )
        )


def _assert_fixed_investigator_runs(
    runs: tuple[InvestigatorRun, ...],
    roles: tuple[tuple[InvestigatorID, AgentStage], ...],
) -> None:
    """Fail closed if collection does not contain one run per assigned role."""

    expected_roles = tuple(role for role, _stage in roles)
    observed_roles = tuple(run.result.investigator_id for run in runs)
    if len(runs) != len(expected_roles):
        raise AgentValidationError("harness collected an unexpected investigator count")
    if len(observed_roles) != len(set(observed_roles)) or set(observed_roles) != set(
        expected_roles
    ):
        raise AgentValidationError(
            "harness requires exactly one result for each fixed investigator role"
        )
    if observed_roles != expected_roles:
        raise AgentValidationError("investigator result does not match its assigned stage")
    for run, role in zip(runs, expected_roles, strict=True):
        if run.result.investigator_id is not role:
            raise AgentValidationError("investigator result role mismatch")
