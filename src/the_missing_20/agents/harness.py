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
    REQUIRED_AUTHORITATIVE_SOURCES,
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

# These are the only roles exposed by the browser chat control.  ``orchestrator``
# is a team-facing alias that uses the first investigator contract while retaining
# the full source allowlist; it never gains authority to approve or execute.
CHAT_AGENT_ROLES: dict[str, InvestigatorID] = {
    "orchestrator": InvestigatorID.RETRYABLE_MESSAGE,
    InvestigatorID.RETRYABLE_MESSAGE.value: InvestigatorID.RETRYABLE_MESSAGE,
    InvestigatorID.SHORT_SHIPMENT.value: InvestigatorID.SHORT_SHIPMENT,
    InvestigatorID.DUPLICATE_POSTING.value: InvestigatorID.DUPLICATE_POSTING,
}
CHAT_AGENT_SOURCE_TYPES: dict[str, frozenset[EvidenceSourceType]] = {
    "orchestrator": frozenset(REQUIRED_AUTHORITATIVE_SOURCES),
    InvestigatorID.RETRYABLE_MESSAGE.value: frozenset(
        {
            EvidenceSourceType.FAILED_MESSAGE_QUEUE,
            EvidenceSourceType.WAREHOUSE,
            EvidenceSourceType.ERP_RECEIPT,
        }
    ),
    InvestigatorID.SHORT_SHIPMENT.value: frozenset(
        {
            EvidenceSourceType.WAREHOUSE,
            EvidenceSourceType.ERP_RECEIPT,
            EvidenceSourceType.INVOICE,
        }
    ),
    InvestigatorID.DUPLICATE_POSTING.value: frozenset(
        {
            EvidenceSourceType.FAILED_MESSAGE_QUEUE,
            EvidenceSourceType.ERP_RECEIPT,
            EvidenceSourceType.MATERIAL_DOCUMENT,
        }
    ),
}


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


@dataclass(frozen=True, slots=True)
class AdvisoryStageResult:
    """Auditable advisory output when semantic acceptance lacks citation closure.

    ``HarnessRun`` deliberately remains the legacy full-closure result consumed by
    the deterministic policy.  A provider can still produce a semantically accepted
    synthesis whose claims cover only part of the admitted catalog; that output is
    useful to show, but it must not be coerced into an ``InvestigationAssessment`` or
    an action recommendation.  This separate result carries the exact model stages
    and the application-owned closure/source projections for that case.
    """

    investigators: tuple[InvestigatorResult, ...]
    investigator_knowledge_citations: tuple[tuple[KnowledgeCitation, ...], ...]
    investigator_read_evidence_ids: tuple[tuple[str, ...], ...]
    synthesis: SynthesisResult
    evaluation: AgentEvaluationResult
    evaluator_citation_closure: EvaluatorCitationClosure
    evaluator_source_coverage: EvaluatorSourceCoverage
    trace: NormalizedTrace
    protocol: AgentProtocolEnvelope
    authoritative_evidence_ids: tuple[str, ...]
    authoritative_source_types: tuple[EvidenceSourceType, ...]
    advisory_status: str = "PARTIAL"
    warnings: tuple[str, ...] = ("AI_CITATION_CLOSURE_INCOMPLETE",)

    @property
    def status(self) -> str:
        """Compatibility alias for consumers that call the result status."""

        return self.advisory_status

    @property
    def warning_codes(self) -> tuple[str, ...]:
        return self.warnings

    @property
    def ai_coverage(self) -> dict[str, Any]:
        """Expose model-cited coverage without filling omitted IDs."""

        covered_ids = tuple(sorted(self.evaluator_citation_closure.validated_evidence_ids))
        admitted_ids = tuple(sorted(self.authoritative_evidence_ids))
        covered_sources = tuple(
            sorted(
                {source.value for source in self.evaluator_source_coverage.validated_source_types}
            )
        )
        authoritative_sources = tuple(
            sorted({source.value for source in self.authoritative_source_types})
        )
        omitted_ids = tuple(
            evidence_id for evidence_id in admitted_ids if evidence_id not in covered_ids
        )
        omitted_sources = tuple(
            source for source in authoritative_sources if source not in covered_sources
        )
        return {
            "covered_evidence_ids": list(covered_ids),
            "covered_source_types": list(covered_sources),
            "omitted_evidence_ids": list(omitted_ids),
            "omitted_source_types": list(omitted_sources),
            "covered_count": len(covered_ids),
            "admitted_count": len(admitted_ids),
            "coverage": f"{len(covered_ids)}/{len(admitted_ids)}",
        }

    @property
    def authoritative_catalog(self) -> dict[str, Any]:
        """Expose the detector-owned catalog as a separate truth surface."""

        evidence_ids = tuple(sorted(self.authoritative_evidence_ids))
        source_types = tuple(sorted({source.value for source in self.authoritative_source_types}))
        return {
            "evidence_ids": list(evidence_ids),
            "source_types": list(source_types),
            "evidence_count": len(evidence_ids),
            "source_count": len(source_types),
        }

    def public(self) -> dict[str, Any]:
        """Return the bounded advisory projection, never operational authority."""

        return {
            "schema_version": "advisory-stage/v1",
            "status": self.advisory_status,
            "warnings": list(self.warnings),
            "provider": self.trace.provider,
            "model": self.trace.model,
            "protocol": self.protocol.model_dump(mode="json"),
            "investigators": [item.model_dump(mode="json") for item in self.investigators],
            "investigator_knowledge_citations": [
                [citation.model_dump(mode="json") for citation in citations]
                for citations in self.investigator_knowledge_citations
            ],
            "investigator_read_evidence_ids": [
                list(read_ids) for read_ids in self.investigator_read_evidence_ids
            ],
            "synthesis": self.synthesis.model_dump(mode="json"),
            "evaluation": self.evaluation.model_dump(mode="json"),
            "evaluator_citation_closure": self.evaluator_citation_closure.model_dump(
                mode="json"
            ),
            "evaluator_source_coverage": self.evaluator_source_coverage.model_dump(
                mode="json"
            ),
            "ai_coverage": self.ai_coverage,
            "authoritative_catalog": self.authoritative_catalog,
            "trace": self.trace.public(),
        }


@dataclass(frozen=True, slots=True)
class ChatRun:
    """One bounded, role-scoped advisory turn.

    Chat deliberately stops at a single investigator.  It does not create a
    synthesis, evaluation, decision, approval, or execution record; the session's
    deterministic router remains responsible for the user-facing operational
    explanation and authority boundary.
    """

    agent_id: str
    investigator: InvestigatorRun
    provider_metadata: dict[str, Any]

    @property
    def read_evidence_ids(self) -> tuple[str, ...]:
        return self.investigator.read_evidence_ids

    @property
    def knowledge_citations(self) -> tuple[KnowledgeCitation, ...]:
        return self.investigator.knowledge_citations


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _usage_metric(result: Any, name: str) -> int:
    metrics = getattr(result, "metrics", None)
    usage = getattr(metrics, "accumulated_usage", {}) if metrics is not None else {}
    return int((usage or {}).get(name, 0))


def _provider_metadata(
    factory: AgentModelFactory,
    result: Any | None = None,
    *,
    agent_id: str | None = None,
    error_code: str | None = None,
) -> dict[str, Any]:
    """Build a redacted provider record from the model boundary.

    The record is intentionally made from factory configuration and stable SDK
    metrics only.  Prompts, raw model text, credentials, account IDs, and tool
    payloads never cross this boundary.
    """

    provenance = getattr(factory, "provenance", None)
    metadata = provenance() if callable(provenance) else {}
    if not isinstance(metadata, dict):
        metadata = {}
    metrics = getattr(result, "metrics", None) if result is not None else None
    usage = getattr(metrics, "accumulated_usage", {}) or {}
    accumulated = getattr(metrics, "accumulated_metrics", {}) or {}
    try:
        input_tokens = int(usage.get("inputTokens", 0))
        output_tokens = int(usage.get("outputTokens", 0))
        request_count = int(getattr(metrics, "cycle_count", 0))
        latency_ms = int(accumulated.get("latencyMs", 0))
    except (AttributeError, TypeError, ValueError):
        input_tokens = output_tokens = request_count = latency_ms = 0
    metadata.update(
        {
            "request_count": max(0, request_count),
            "input_tokens": max(0, input_tokens),
            "output_tokens": max(0, output_tokens),
            "latency_ms": max(0, latency_ms),
            "read_only": True,
            "authority": "ADVISORY_NOT_OPERATIONAL_DECISION",
        }
    )
    if agent_id is not None:
        metadata["agent_id"] = agent_id
    if error_code is not None:
        metadata["error_code"] = error_code
        metadata["status"] = "DEGRADED"
    else:
        metadata.setdefault("status", "COMPLETE")
    ledger = getattr(factory, "ledger", None)
    if ledger is not None:
        try:
            ledger_snapshot = ledger.snapshot()
        except Exception:  # pragma: no cover - defensive provider adapter boundary
            ledger_snapshot = {}
        if isinstance(ledger_snapshot, dict):
            for key in (
                "incremental_cost_usd",
                "cumulative_cost_usd",
                "remaining_cumulative_cost_usd",
                "request_cap",
                "input_token_cap",
                "output_token_cap",
            ):
                if key in ledger_snapshot:
                    metadata[key] = ledger_snapshot[key]
    return metadata


def _validate_chat_investigator(
    result: InvestigatorResult,
    *,
    allowed_evidence_ids: frozenset[str],
    read_evidence_ids: tuple[str, ...],
) -> InvestigatorResult:
    """Validate a role-scoped advisory result without widening its read scope.

    The full diagnosis validator requires every authoritative source to be read
    before a supported conclusion can drive the action policy.  A chat turn is
    intentionally narrower: it may inspect only the selected role's sources and
    can never produce a synthesis or operational decision.  This validator keeps
    the same citation/read integrity at that smaller boundary.
    """

    if not set(read_evidence_ids).issubset(allowed_evidence_ids):
        raise AgentValidationError("chat investigator read an unallowlisted evidence ID")
    referenced = {
        evidence_id
        for claim in result.factual_claims
        for evidence_id in claim.evidence_ids
    }
    if not referenced.issubset(allowed_evidence_ids):
        raise AgentValidationError("chat investigator cited an unallowlisted evidence ID")
    if not referenced.issubset(set(read_evidence_ids)):
        raise AgentValidationError("chat investigator cited evidence that was not read")
    supporting = {
        evidence_id
        for claim in result.factual_claims
        if claim.relation is ClaimRelation.SUPPORTS_HYPOTHESIS
        for evidence_id in claim.evidence_ids
    }
    contradicting = {
        evidence_id
        for claim in result.factual_claims
        if claim.relation is ClaimRelation.CONTRADICTS_HYPOTHESIS
        for evidence_id in claim.evidence_ids
    }
    if result.conclusion is HypothesisConclusion.SUPPORTED and not supporting:
        raise AgentValidationError("supported chat result must cite supporting evidence")
    if result.conclusion is HypothesisConclusion.SUPPORTED and contradicting:
        raise AgentValidationError("supported chat result contains contradictory evidence")
    return result


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
    ) -> HarnessRun | AdvisoryStageResult:
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
                payload={
                    "stage": stage.value,
                    "mode": self.model_factory.provider.value,
                    "advisory": True,
                },
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
                        payload={
                            "stage": stage.value,
                            "mode": self.model_factory.provider.value,
                            "advisory": True,
                        },
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
        partial_advisory = evaluation.decision.value == "ACCEPT" and (
            not evaluator_citation_closure.all_synthesis_claims_validated
            or not evaluator_citation_closure.all_admitted_evidence_covered
        )
        coverage_ledger: EvidenceCoverageLedger | None = None
        action_recommendation: ActionRecommendation | None = None
        assessment: InvestigationAssessment | None = None
        if not partial_advisory:
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
            action_recommendation = action_recommendation.model_copy(
                update={"protocol": protocol}
            )
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
            else "agentcore-runtime"
            if provider == AgentProvider.AGENTCORE.value
            else "us.amazon.nova-pro-v1:0"
        )
        trace = NormalizedTrace(
            run_id=f"agent-run:{case_id}",
            case_id=case_id,
            trace_id=trace_id,
            provider=provider,
            model=model,
            provider_metadata=_provider_metadata(self.model_factory),
            prompt_version=prompts.version,
            prompt_digest=prompts.digest,
            knowledge_version=self.knowledge.version,
            harness_version=HARNESS_VERSION,
            evaluator_version=EVALUATOR_VERSION,
            agent_contract_version=AGENT_CONTRACT_VERSION,
            stop_reason=(
                "ADVISORY_PARTIAL_CITATION_CLOSURE"
                if partial_advisory
                else "ASSESSMENT_VALIDATED"
            ),
            evaluator_source_coverage=evaluator_source_coverage.model_dump(mode="json"),
            evaluator_citation_closure=evaluator_citation_closure.model_dump(mode="json"),
            coverage_ledger=(
                coverage_ledger.model_dump(mode="json") if coverage_ledger is not None else None
            ),
            action_recommendation=(
                action_recommendation.model_dump(mode="json")
                if action_recommendation is not None
                else None
            ),
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
        trace.provider_metadata = _provider_metadata(self.model_factory)
        trace.provider_metadata.update(
            {
                "request_count": trace.request_count,
                "input_tokens": trace.input_tokens,
                "output_tokens": trace.output_tokens,
                "latency_ms": sum(stage.latency_ms for stage in trace.stages),
            }
        )
        if partial_advisory:
            return AdvisoryStageResult(
                investigators=validated_investigators,
                synthesis=synthesis,
                evaluation=evaluation,
                evaluator_citation_closure=evaluator_citation_closure,
                evaluator_source_coverage=evaluator_source_coverage,
                investigator_knowledge_citations=investigator_knowledge_citations,
                investigator_read_evidence_ids=tuple(
                    run.read_evidence_ids for run in investigator_runs
                ),
                trace=trace,
                protocol=protocol,
                authoritative_evidence_ids=tuple(sorted(item.evidence_id for item in evidence)),
                authoritative_source_types=tuple(
                    sorted(
                        {item.source_type for item in evidence},
                        key=lambda source: source.value,
                    )
                ),
            )
        assert assessment is not None
        assert coverage_ledger is not None
        assert action_recommendation is not None
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

    async def run_chat_async(
        self,
        *,
        case_id: str,
        trace_id: str,
        evidence: tuple[EvidenceItem, ...],
        user_question: str,
        selected_agent_id: str = "orchestrator",
    ) -> ChatRun:
        """Run one bounded read-only turn for the selected investigator role.

        Chat deliberately does not invoke synthesis or evaluation.  The selected
        role receives a smaller evidence allowlist and its own system context;
        deterministic policy, approvals, and execution remain outside this path.
        """

        if not evidence:
            raise AgentValidationError("chat harness requires admitted evidence")
        if any(item.case_id != case_id or item.trace_id != trace_id for item in evidence):
            raise AgentValidationError("chat evidence does not match case and trace")
        question = user_question.strip()
        if not question or len(question) > 2_000:
            raise AgentValidationError("chat question must contain one to two thousand characters")
        role = CHAT_AGENT_ROLES.get(selected_agent_id)
        if role is None:
            raise AgentValidationError("chat agent is not allowlisted")
        allowed_types = CHAT_AGENT_SOURCE_TYPES[selected_agent_id]
        allowed_ids = frozenset(
            item.evidence_id for item in evidence if item.source_type in allowed_types
        )
        if not allowed_ids:
            raise AgentValidationError("selected chat role has no admitted evidence")
        prompts = PromptSet.load(self.prompt_root)
        scope = ToolScope(
            case_id=case_id,
            trace_id=trace_id,
            admitted_evidence=evidence,
            allowed_evidence_ids=allowed_ids,
            knowledge=self.knowledge,
            knowledge_version=self.knowledge.version,
            max_evidence_reads=len(allowed_ids),
        )
        scripted_outputs, _synthesis_payload, _evaluator_payload = _profile_outputs(
            evidence=evidence,
            trace_id=trace_id,
            source_availability=self.source_availability,
        )
        # The scripted fixture is only used for the offline provider.  Restrict its
        # citations as well so offline chat exercises the same role boundary as a
        # real provider response.
        output_payload = json.loads(json.dumps(scripted_outputs[role]))
        filtered_claims: list[dict[str, Any]] = []
        for claim in output_payload.get("factual_claims", []):
            claim_ids = [
                evidence_id
                for evidence_id in claim.get("evidence_ids", [])
                if evidence_id in allowed_ids
            ]
            if claim_ids:
                filtered = dict(claim)
                filtered["evidence_ids"] = claim_ids
                filtered_claims.append(filtered)
        output_payload["factual_claims"] = filtered_claims
        if (
            output_payload.get("conclusion") == HypothesisConclusion.SUPPORTED.value
            and not filtered_claims
        ):
            output_payload["conclusion"] = HypothesisConclusion.REJECTED.value
        operation_id = f"chat-agent:{selected_agent_id}:{trace_id}"
        self._emit(
            event_type=AgentOperationEventType.AGENT_STARTED,
            case_id=case_id,
            trace_id=trace_id,
            actor=role.value,
            operation_id=operation_id,
            status="RUNNING",
            correlation_id=trace_id,
            stage=AgentStage.RETRYABLE_INVESTIGATOR,
            payload={
                "agent_id": selected_agent_id,
                "mode": self.model_factory.provider.value,
                "chat": True,
                "allowlisted_evidence_count": len(allowed_ids),
            },
        )
        stage = {
            InvestigatorID.RETRYABLE_MESSAGE: AgentStage.RETRYABLE_INVESTIGATOR,
            InvestigatorID.SHORT_SHIPMENT: AgentStage.SHORT_SHIPMENT_INVESTIGATOR,
            InvestigatorID.DUPLICATE_POSTING: AgentStage.DUPLICATE_POSTING_INVESTIGATOR,
        }[role]
        try:
            run = await run_investigator(
                role=role,
                stage=stage,
                model_factory=self.model_factory,
                output_payload=output_payload,
                tool_plan=default_tool_plan(scope),
                scope=scope,
                source_availability=self.source_availability,
                event_sink=self.event_sink,
                operation_prefix=operation_id,
                system_prompt=(
                    f"{prompts.investigator}\n\n"
                    f"You are the selected {selected_agent_id} role."
                    " This is advisory, read-only investigation; do not approve or execute."
                ),
                user_question=question,
                role_label=selected_agent_id,
                agent_id_override=selected_agent_id,
                timeout_seconds=self.budget.per_call_timeout_seconds,
            )
            result = _validate_chat_investigator(
                run.result,
                allowed_evidence_ids=allowed_ids,
                read_evidence_ids=run.read_evidence_ids,
            )
            del result
            metadata = _provider_metadata(
                self.model_factory,
                run.model_result,
                agent_id=selected_agent_id,
            )
            self._emit(
                event_type=AgentOperationEventType.AGENT_COMPLETED,
                case_id=case_id,
                trace_id=trace_id,
                actor=role.value,
                operation_id=operation_id,
                status="COMPLETED",
                correlation_id=trace_id,
                stage=stage,
                payload={
                    "agent_id": selected_agent_id,
                    "chat": True,
                    "read_evidence_ids": list(run.read_evidence_ids),
                    "provider_metadata": metadata,
                },
            )
            return ChatRun(
                agent_id=selected_agent_id,
                investigator=run,
                provider_metadata=metadata,
            )
        except Exception as error:
            metadata = _provider_metadata(
                self.model_factory,
                agent_id=selected_agent_id,
                error_code=type(error).__name__,
            )
            self._emit(
                event_type=AgentOperationEventType.AGENT_COMPLETED,
                case_id=case_id,
                trace_id=trace_id,
                actor=role.value,
                operation_id=operation_id,
                status="FAILED",
                correlation_id=trace_id,
                stage=stage,
                payload={
                    "agent_id": selected_agent_id,
                    "chat": True,
                    "error_code": type(error).__name__,
                    "provider_metadata": metadata,
                },
            )
            raise

    def run(
        self,
        *,
        case_id: str,
        trace_id: str,
        evidence: tuple[EvidenceItem, ...],
        assessed_at: datetime = FIXED_ASSESSMENT_TIME,
    ) -> HarnessRun | AdvisoryStageResult:
        return asyncio.run(
            self.run_async(
                case_id=case_id,
                trace_id=trace_id,
                evidence=evidence,
                assessed_at=assessed_at,
            )
        )

    def run_chat(
        self,
        *,
        case_id: str,
        trace_id: str,
        evidence: tuple[EvidenceItem, ...],
        user_question: str,
        selected_agent_id: str = "orchestrator",
    ) -> ChatRun:
        return asyncio.run(
            self.run_chat_async(
                case_id=case_id,
                trace_id=trace_id,
                evidence=evidence,
                user_question=user_question,
                selected_agent_id=selected_agent_id,
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
