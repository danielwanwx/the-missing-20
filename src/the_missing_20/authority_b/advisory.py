"""Non-authoritative advisory investigation orchestration.

The adapter deliberately treats the model branch as best-effort work.  A provider or
validator failure is normalized into an immutable status record and never escapes into
the deterministic decision path.  The default runner accepts a single stage callable,
which makes the no-corrective-call rule explicit and easy to test.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from typing import Any

from the_missing_20.authority_b.models import (
    ADVISORY_AUTHORITY_LABEL,
    AdvisoryDissent,
    AdvisoryHypothesis,
    AdvisoryInvestigation,
    AdvisoryKnowledgeCitation,
    AdvisoryStatus,
    AdvisoryUsage,
)
from the_missing_20.domain.models import (
    ConfidenceBand,
    HypothesisConclusion,
    HypothesisType,
)

ADVISORY_READ_ONLY_TOOLS = frozenset({"read_admitted_evidence", "search_synthetic_knowledge"})


def validate_advisory_tool_names(tool_names: Iterable[str]) -> tuple[str, ...]:
    """Reject any advisory tool plan that could authorize or mutate state."""

    observed = tuple(sorted(set(tool_names)))
    forbidden = tuple(name for name in observed if name not in ADVISORY_READ_ONLY_TOOLS)
    if forbidden:
        raise ValueError("advisory tool plan contains a non-read-only capability")
    return observed


def _now(value: datetime | None) -> datetime:
    result = value or datetime.now(UTC)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("advisory timestamps must be timezone-aware")
    return result


def _stable_error_code(error: BaseException) -> str:
    name = type(error).__name__.upper()
    if isinstance(error, (TimeoutError, asyncio.TimeoutError)) or "TIMEOUT" in name:
        return "ADVISORY_PROVIDER_TIMEOUT"
    if "VALID" in name or "MALFORM" in name or "STRUCTURED" in name:
        return "ADVISORY_MALFORMED_OUTPUT"
    if "BUDGET" in name or "COST" in name:
        return "ADVISORY_BUDGET_EXHAUSTED"
    return "ADVISORY_PROVIDER_FAILURE"


def _warning_code(error: BaseException) -> str:
    return _stable_error_code(error)


def _harness_hypothesis(item: Any, index: int) -> AdvisoryHypothesis:
    claims = tuple(getattr(item, "factual_claims", ()))
    supporting = tuple(
        sorted(
            {
                evidence_id
                for claim in claims
                if getattr(getattr(claim, "relation", None), "value", None) == "SUPPORTS_HYPOTHESIS"
                for evidence_id in getattr(claim, "evidence_ids", ())
            }
        )
    )
    contradicting = tuple(
        sorted(
            {
                evidence_id
                for claim in claims
                if getattr(getattr(claim, "relation", None), "value", None)
                == "CONTRADICTS_HYPOTHESIS"
                for evidence_id in getattr(claim, "evidence_ids", ())
            }
        )
    )
    hypothesis = getattr(item, "hypothesis_type", HypothesisType.RETRYABLE_MESSAGE)
    conclusion = getattr(item, "conclusion", HypothesisConclusion.NEEDS_EVIDENCE)
    confidence = getattr(item, "confidence_band", ConfidenceBand.LOW)
    role = str(getattr(getattr(item, "investigator_id", None), "value", "investigator"))
    statement = "; ".join(str(getattr(claim, "statement", "")) for claim in claims).strip()
    if not statement:
        statement = f"The {hypothesis.value} hypothesis was investigated."
    return AdvisoryHypothesis(
        hypothesis_id=f"advisory-hypothesis-{index}-{hypothesis.value.lower()}",
        investigator_role=role,
        hypothesis_type=hypothesis,
        conclusion=conclusion,
        confidence_band=confidence,
        explanation=statement,
        supporting_evidence_ids=supporting,
        contradicting_evidence_ids=contradicting,
    )


def advisory_from_harness_run(
    run: Any,
    *,
    case_id: str | None = None,
    trace_id: str | None = None,
    case_version: int = 0,
    now: datetime | None = None,
    deterministic_evidence_gaps: Iterable[str] = (),
    admitted_evidence_ids: Iterable[str] | None = None,
) -> AdvisoryInvestigation:
    """Project an existing Strands ``HarnessRun`` into the Authority B advisory record."""

    timestamp = _now(now)
    assessment = getattr(run, "assessment", None)
    resolved_case_id = case_id or getattr(assessment, "case_id", None)
    resolved_trace_id = trace_id or getattr(assessment, "trace_id", None)
    if not resolved_case_id or not resolved_trace_id:
        raise ValueError("harness run is missing case identity")
    investigators = tuple(getattr(run, "investigators", ()))
    allowed_ids = None if admitted_evidence_ids is None else frozenset(admitted_evidence_ids)
    hypotheses = tuple(_harness_hypothesis(item, index) for index, item in enumerate(investigators))
    warnings_set: set[str] = set()
    stage_warnings = getattr(run, "warnings", ())
    warnings_set.update(str(item) for item in stage_warnings)
    stage_closure = getattr(run, "evaluator_citation_closure", None)
    if stage_closure is not None and (
        not bool(getattr(stage_closure, "all_synthesis_claims_validated", False))
        or not bool(getattr(stage_closure, "all_admitted_evidence_covered", False))
    ):
        warnings_set.add("AI_CITATION_CLOSURE_INCOMPLETE")
    if allowed_ids is not None:
        filtered: list[AdvisoryHypothesis] = []
        for item in hypotheses:
            unknown = (
                set(item.supporting_evidence_ids) | set(item.contradicting_evidence_ids)
            ) - allowed_ids
            if unknown:
                warnings_set.add("UNKNOWN_ADVISORY_CITATION")
            filtered.append(
                item.model_copy(
                    update={
                        "supporting_evidence_ids": tuple(
                            value for value in item.supporting_evidence_ids if value in allowed_ids
                        ),
                        "contradicting_evidence_ids": tuple(
                            value
                            for value in item.contradicting_evidence_ids
                            if value in allowed_ids
                        ),
                    }
                )
            )
        hypotheses = tuple(filtered)
    hypothesis_types = {item.hypothesis_type for item in hypotheses}
    dissent = tuple(
        AdvisoryDissent(
            investigator_role=item.investigator_role,
            statement=(
                f"{item.investigator_role} concluded {item.conclusion.value} for "
                f"{item.hypothesis_type.value}."
            ),
            hypothesis_type=item.hypothesis_type,
            confidence_band=item.confidence_band,
        )
        for item in hypotheses
        if item.conclusion is not HypothesisConclusion.SUPPORTED or len(hypothesis_types) > 1
    )
    citations: dict[tuple[str, str], AdvisoryKnowledgeCitation] = {}
    for group in tuple(getattr(run, "investigator_knowledge_citations", ())):
        for item in group:
            key = (item.knowledge_id, item.version)
            citations[key] = AdvisoryKnowledgeCitation(
                knowledge_id=item.knowledge_id,
                version=item.version,
                content_digest=item.content_digest,
                allowed_use=item.allowed_use.value,
            )
    synthesis = getattr(run, "synthesis", None)
    report = None
    if synthesis is not None:
        claims = tuple(getattr(synthesis, "factual_claims", ()))
        report = "; ".join(str(getattr(claim, "statement", "")) for claim in claims).strip()
        if not report:
            selected = getattr(getattr(synthesis, "selected_hypothesis", None), "value", "unknown")
            report = f"Advisory synthesis selected {selected}."
    trace = getattr(run, "trace", None)
    usage = AdvisoryUsage(
        request_count=int(getattr(trace, "request_count", 0)),
        input_tokens=int(getattr(trace, "input_tokens", 0)),
        output_tokens=int(getattr(trace, "output_tokens", 0)),
        latency_ms=sum(
            int(getattr(stage, "latency_ms", 0)) for stage in getattr(trace, "stages", ())
        ),
        estimated_cost_usd=0.0,
    )
    missing = tuple(sorted(set(getattr(assessment, "missing_evidence_sources", ()))))
    if not missing:
        source_coverage = getattr(run, "evaluator_source_coverage", None)
        missing = tuple(
            sorted(
                {
                    getattr(getattr(item, "source_type", None), "value", "")
                    for item in getattr(source_coverage, "source_availability", ())
                    if getattr(getattr(item, "status", None), "value", None) == "UNAVAILABLE"
                }
                - {""}
            )
        )
    proposed_gaps = missing or ("NO_MISSING_AUTHORITATIVE_EVIDENCE",)
    warnings_set.update(missing)
    warnings: tuple[str, ...] = tuple(sorted(warnings_set))
    stage_status = getattr(run, "advisory_status", None)
    if stage_status is None:
        status = (
            AdvisoryStatus.PARTIAL
            if "UNKNOWN_ADVISORY_CITATION" in warnings_set
            else AdvisoryStatus.COMPLETE
        )
    else:
        try:
            status = AdvisoryStatus(getattr(stage_status, "value", stage_status))
        except ValueError as exc:
            raise ValueError("harness run has an unknown advisory status") from exc
    return AdvisoryInvestigation(
        advisory_id=f"advisory:{resolved_case_id}:{resolved_trace_id}",
        case_id=resolved_case_id,
        trace_id=resolved_trace_id,
        case_version=case_version,
        provider=str(getattr(trace, "provider", "scripted")),
        model=str(getattr(trace, "model", "unknown")),
        prompt_digest=getattr(trace, "prompt_digest", None),
        status=status,
        hypotheses=hypotheses,
        proposed_evidence_gaps=proposed_gaps,
        deterministic_evidence_gaps=tuple(sorted(set(deterministic_evidence_gaps))),
        dissent=dissent,
        knowledge_citations=tuple(citations[key] for key in sorted(citations)),
        incident_report=report,
        warnings=warnings,
        usage=usage,
        created_at=timestamp,
        updated_at=timestamp,
        authority_label=ADVISORY_AUTHORITY_LABEL,
    )


def normalize_advisory_failure(
    *,
    case_id: str,
    trace_id: str,
    case_version: int = 0,
    error: BaseException | None = None,
    started: bool = True,
    now: datetime | None = None,
    usage: AdvisoryUsage | None = None,
) -> AdvisoryInvestigation:
    """Create a redacted degraded/unavailable advisory record without raising."""

    timestamp = _now(now)
    if started:
        status = AdvisoryStatus.DEGRADED
        code = _stable_error_code(error or RuntimeError("provider failure"))
        warning = code
        failed_stage = "advisory_provider"
    else:
        status = AdvisoryStatus.UNAVAILABLE
        code = "ADVISORY_NOT_STARTED"
        warning = code
        failed_stage = None
    return AdvisoryInvestigation(
        advisory_id=f"advisory:{case_id}:{trace_id}",
        case_id=case_id,
        trace_id=trace_id,
        case_version=case_version,
        status=status,
        warnings=(warning,),
        usage=usage or AdvisoryUsage(),
        error_code=code,
        failed_stage=failed_stage,
        created_at=timestamp,
        updated_at=timestamp,
    )


class AdvisoryOrchestrator:
    """Run one bounded advisory provider callable and normalize every outcome."""

    def __init__(self, *, provider_name: str | None = None, model_name: str | None = None) -> None:
        self.provider_name = provider_name
        self.model_name = model_name

    def run(
        self,
        *,
        case_id: str,
        trace_id: str,
        case_version: int = 0,
        execute: Callable[[], Any] | None = None,
        now: datetime | None = None,
        deterministic_evidence_gaps: Iterable[str] = (),
        admitted_evidence_ids: Iterable[str] | None = None,
    ) -> AdvisoryInvestigation:
        """Execute ``execute`` at most once; no corrective provider call is attempted."""

        timestamp = _now(now)
        if execute is None:
            return normalize_advisory_failure(
                case_id=case_id,
                trace_id=trace_id,
                case_version=case_version,
                started=False,
                now=timestamp,
            )
        try:
            result = execute()
        except BaseException as error:
            return normalize_advisory_failure(
                case_id=case_id,
                trace_id=trace_id,
                case_version=case_version,
                error=error,
                started=True,
                now=timestamp,
            )
        if isinstance(result, AdvisoryInvestigation):
            if (
                result.case_id != case_id
                or result.trace_id != trace_id
                or result.case_version != case_version
            ):
                return normalize_advisory_failure(
                    case_id=case_id,
                    trace_id=trace_id,
                    case_version=case_version,
                    error=ValueError("advisory identity mismatch"),
                    started=True,
                    now=timestamp,
                )
            return result
        try:
            projected = advisory_from_harness_run(
                result,
                case_id=case_id,
                trace_id=trace_id,
                case_version=case_version,
                now=timestamp,
                deterministic_evidence_gaps=deterministic_evidence_gaps,
                admitted_evidence_ids=admitted_evidence_ids,
            )
            updates: dict[str, str] = {}
            if self.provider_name is not None:
                updates["provider"] = self.provider_name
            if self.model_name is not None:
                updates["model"] = self.model_name
            return projected.model_copy(update=updates) if updates else projected
        except BaseException as error:
            return normalize_advisory_failure(
                case_id=case_id,
                trace_id=trace_id,
                case_version=case_version,
                error=error,
                started=True,
                now=timestamp,
            )


__all__ = [
    "ADVISORY_READ_ONLY_TOOLS",
    "AdvisoryOrchestrator",
    "advisory_from_harness_run",
    "normalize_advisory_failure",
    "validate_advisory_tool_names",
]
