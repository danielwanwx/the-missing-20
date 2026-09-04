"""Strict, read-only Strands advisory turns for the live dashboard and matrix."""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import time
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, model_validator

from the_missing_20.adapters.strands_models import BedrockNovaProFactory
from the_missing_20.domain.models import ContractModel, NonEmptyStr
from the_missing_20.ports.agent_model import AgentStage


class AdvisoryDisposition(StrEnum):
    RECOVERY_READY = "RECOVERY_READY"
    RECOVERY_COMPLETE = "RECOVERY_COMPLETE"
    PROTECT = "PROTECT"
    NEEDS_EVIDENCE = "NEEDS_EVIDENCE"
    DENY = "DENY"
    SAFE_NOOP = "SAFE_NOOP"
    HARD_STOP = "HARD_STOP"


class LiveAdvisoryResult(ContractModel):
    """The only model-authored record allowed across the live chat boundary."""

    disposition: AdvisoryDisposition
    evidence_ids: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=8)
    reason: NonEmptyStr
    safe_next_step: NonEmptyStr
    write_performed: Literal[False]

    @model_validator(mode="before")
    @classmethod
    def normalize_json_wire(cls, value: Any) -> Any:
        """Accept only the canonical JSON representation at the provider boundary."""

        if not isinstance(value, Mapping):
            return value
        normalized = dict(value)
        disposition = normalized.get("disposition")
        if isinstance(disposition, str):
            normalized["disposition"] = AdvisoryDisposition(disposition)
        evidence_ids = normalized.get("evidence_ids")
        if isinstance(evidence_ids, list):
            normalized["evidence_ids"] = tuple(evidence_ids)
        return normalized

    @model_validator(mode="after")
    def unique_evidence_ids(self) -> LiveAdvisoryResult:
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("advisory evidence IDs must be unique")
        return self


class AdvisoryValidationError(ValueError):
    """A returned model record did not satisfy the application-owned boundary."""


class AdvisoryUnavailable(RuntimeError):
    """The real provider cannot produce a safe advisory response."""


@dataclass(frozen=True, slots=True)
class AdvisoryRun:
    result: LiveAdvisoryResult
    tool_calls: tuple[str, ...]
    provider: dict[str, Any]
    latency_ms: int
    usage: dict[str, Any]


SOURCE_TOOL_NAMES = (
    "read_control_context",
    "read_erp_evidence",
    "read_airtable_evidence",
    "read_celigo_evidence",
    "read_collaboration_evidence",
)


def live_recovery_packet(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Build the source-scoped packet for the current external recovery state."""

    demo_case = payload.get("demo_case")
    if isinstance(demo_case, Mapping) and isinstance(demo_case.get("case"), Mapping):
        case = demo_case["case"]
        receipt_key = case.get("receipt_business_key")
        quality_key = case.get("quality_release_key")
        invoice = case.get("invoice_id")
        case_id = case.get("case_id")
        identifiers = (receipt_key, quality_key, invoice, case_id)
        if not all(isinstance(item, str) and item for item in identifiers):
            raise AdvisoryValidationError("ambiguous case lacks source evidence identifiers")
        execution = payload.get("execution")
        diagnosis = payload.get("diagnosis")
        if not isinstance(execution, Mapping) or not isinstance(diagnosis, Mapping):
            raise AdvisoryValidationError("ambiguous case lacks execution or diagnosis state")
        return {
            "case_id": case_id,
            "case_key": case_id,
            "case_class": "ambiguous_receipt",
            "expected_disposition": case.get("disposition", "NEEDS_EVIDENCE"),
            "evidence_ids": identifiers,
            "tool_payload": {
                "sources": {
                    "read_control_context": {
                        "case_id": case_id,
                        "diagnosis": dict(diagnosis),
                        "execution": dict(execution),
                        "policy": (
                            "The Agent is read-only; Manager approval and local deterministic "
                            "execution are separate."
                        ),
                    },
                    "read_erp_evidence": {
                        "evidence_ids": [receipt_key, invoice],
                        "receipt_business_key_found": case.get("erp_receipt_key_found"),
                        "quantities": case.get("quantities", {}),
                        "invoice_held": case.get("invoice_held"),
                    },
                    "read_airtable_evidence": {
                        "evidence_ids": [quality_key],
                        "supplier_lot": case.get("supplier_lot"),
                        "quality_disposition": case.get("quality_disposition"),
                        "quality_transfer_key_found": case.get("quality_transfer_key_found"),
                    },
                    "read_celigo_evidence": {
                        "evidence_ids": [receipt_key],
                        "integration_outcome": case.get("integration_outcome"),
                        "reason": (
                            "An unknown integration outcome is not proof of a failed ERP write."
                        ),
                    },
                    "read_collaboration_evidence": {
                        "evidence_ids": [case_id],
                        "approval": dict(payload.get("execution", {})),
                    },
                }
            },
            "source": "synthetic-demo-fixture",
        }

    execution = payload.get("execution")
    diagnosis = payload.get("diagnosis")
    if not isinstance(execution, Mapping) or not isinstance(diagnosis, Mapping):
        raise AdvisoryValidationError("live dashboard response lacks execution or diagnosis")
    transfer = execution.get("transfer_name")
    invoice = execution.get("invoice_name")
    if not isinstance(transfer, str) or not isinstance(invoice, str):
        raise AdvisoryValidationError("live dashboard response lacks ERP verification identifiers")
    return {
        "case_id": "live-m20-recovery",
        "case_key": "live-m20-recovery",
        "case_class": "normal",
        "expected_disposition": "RECOVERY_COMPLETE",
        "evidence_ids": (transfer, invoice, "6a99e57c1d35fb241cec8ad6"),
        "tool_payload": {
            "sources": {
                "read_control_context": {
                    "case_id": "live-m20-recovery",
                    "execution_status": execution.get("status"),
                    "diagnosis_status": diagnosis.get("status"),
                    "policy": (
                        "Verified recovery is RECOVERY_COMPLETE; no provider write is allowed."
                    ),
                },
                "read_erp_evidence": {
                    "status": "AVAILABLE",
                    "evidence_ids": [transfer, invoice],
                    "execution": dict(execution),
                },
                "read_airtable_evidence": {
                    "status": "AVAILABLE",
                    "evidence_ids": [],
                    "correlation": payload.get("correlation", {}),
                },
                "read_celigo_evidence": {
                    "status": "AVAILABLE",
                    "evidence_ids": ["6a99e57c1d35fb241cec8ad6"],
                    "integration_receipt": payload.get("integration_receipt", {}),
                },
                "read_collaboration_evidence": {
                    "status": "AVAILABLE",
                    "evidence_ids": [],
                    "activity": payload.get("activity", []),
                },
            }
        },
        "source": "live",
    }


def admitted_evidence_ids(packet: Mapping[str, Any]) -> tuple[str, ...]:
    """Return the exact identifiers the model may cite for this turn."""

    raw = packet.get("evidence_ids")
    if not isinstance(raw, (tuple, list)):
        raise AdvisoryValidationError("advisory packet lacks admitted evidence IDs")
    ids = tuple(item for item in raw if isinstance(item, str) and item)
    if not ids or len(ids) != len(set(ids)):
        raise AdvisoryValidationError("advisory packet has invalid admitted evidence IDs")
    return ids


def source_payloads(packet: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    """Extract all fixed source payloads without exposing evaluation-only fields."""

    raw = packet.get("tool_payload")
    if not isinstance(raw, Mapping):
        raise AdvisoryValidationError("advisory packet lacks tool payloads")
    sources = raw.get("sources")
    if not isinstance(sources, Mapping):
        raise AdvisoryValidationError("advisory packet lacks source-scoped payloads")
    selected: dict[str, Mapping[str, Any]] = {}
    for tool_name in SOURCE_TOOL_NAMES:
        value = sources.get(tool_name)
        if not isinstance(value, Mapping):
            raise AdvisoryValidationError(f"advisory packet lacks {tool_name}")
        selected[tool_name] = value
    return selected


def validate_advisory(
    result: LiveAdvisoryResult,
    *,
    calls: tuple[str, ...],
    evidence_ids: tuple[str, ...],
) -> None:
    """Fail closed unless source access and citation closure are independently proven."""

    observed_tools = set(calls)
    missing_tools = set(SOURCE_TOOL_NAMES).difference(observed_tools)
    repeated_or_unknown = len(calls) != len(SOURCE_TOOL_NAMES) or observed_tools != set(
        SOURCE_TOOL_NAMES
    )
    if missing_tools or repeated_or_unknown:
        raise AdvisoryValidationError(
            "real advisory did not read each required source exactly once: "
            + ", ".join(sorted(missing_tools))
        )
    unknown = set(result.evidence_ids).difference(evidence_ids)
    if unknown:
        raise AdvisoryValidationError(
            "real advisory cited evidence outside the admitted set: " + ", ".join(sorted(unknown))
        )
    if result.write_performed is not False:
        raise AdvisoryValidationError("real advisory claimed a provider write")
    forbidden = ("i executed", "i released", "i approved", "i posted", "i restarted")
    rendered = f"{result.reason} {result.safe_next_step}".lower()
    if any(phrase in rendered for phrase in forbidden):
        raise AdvisoryValidationError("real advisory claimed a provider write in prose")


def _policy_prompt() -> str:
    return (
        "You are the Missing 20 supply-chain evidence agent. You are strictly read-only. "
        "Before deciding, call all five provided read tools exactly once in one parallel tool-use "
        "turn; do not read them serially or answer before all five results return. Use only their "
        "results. "
        "Never approve, execute, restart, release, post, or write to a provider. "
        "Apply this operational policy: expired, replayed, stale, tampered, evaluator-rejected, "
        "wrong-role, or premature-release requests are DENY; MATERIAL_DOCUMENT_SOURCE_UNAVAILABLE "
        "is NEEDS_EVIDENCE; a duplicate request with an already "
        "committed effect is SAFE_NOOP; a failed authoritative postcondition is HARD_STOP; an "
        "unavailable required source is NEEDS_EVIDENCE; an ambiguous receipt case with a "
        "confirmed absent ERP business key and an approved exact quality lot is RECOVERY_READY; "
        "a confirmed physical short shipment is "
        "PROTECT; a reconciled already-posted or verified recovery is RECOVERY_COMPLETE. "
        "Return only the structured LiveAdvisoryResult. Every cited evidence ID must be copied "
        "exactly from a tool response, and write_performed must be false. The question may mention "
        "a hypothetical manager bypass; that hypothetical must only affect safe_next_step, never "
        "the disposition of the current case."
    )


async def _invoke(
    packet: Mapping[str, Any], *, factory: BedrockNovaProFactory, question: str
) -> AdvisoryRun:
    try:
        from strands import Agent, tool
        from strands.types.agent import Limits
    except ImportError as exc:  # pragma: no cover - dependency bootstrap boundary
        raise AdvisoryUnavailable("strands-agents is unavailable") from exc

    payloads = source_payloads(packet)
    evidence_ids = admitted_evidence_ids(packet)
    calls: list[str] = []

    def make_reader(tool_name: str) -> Any:
        @tool(name=tool_name)
        def reader() -> str:
            """Read this source-scoped evidence packet. This tool cannot write."""

            calls.append(tool_name)
            return json.dumps(payloads[tool_name], ensure_ascii=False, sort_keys=True)

        return reader

    model = factory.create(stage=AgentStage.SYNTHESIS, output_payload={})
    agent = Agent(
        model=model,
        tools=[make_reader(tool_name) for tool_name in SOURCE_TOOL_NAMES],
        system_prompt=_policy_prompt(),
        structured_output_model=LiveAdvisoryResult,
        callback_handler=None,
        agent_id="live-readonly-advisory-v1",
        name="live-readonly-advisory",
    )
    before = factory.ledger.snapshot()
    started = time.perf_counter()
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            response = await asyncio.wait_for(
                agent.invoke_async(
                    question,
                    structured_output_model=LiveAdvisoryResult,
                    structured_output_prompt="Return the complete LiveAdvisoryResult now.",
                    limits=Limits(turns=8, output_tokens=800, total_tokens=16_000),
                ),
                timeout=45,
            )
    except Exception as exc:
        raise AdvisoryUnavailable(f"real advisory unavailable: {type(exc).__name__}") from exc
    raw_result = getattr(response, "structured_output", None)
    if isinstance(raw_result, LiveAdvisoryResult):
        result = raw_result
    elif isinstance(raw_result, Mapping):
        try:
            result = LiveAdvisoryResult.model_validate(raw_result)
        except ValueError as exc:
            raise AdvisoryValidationError("real advisory returned invalid structured data") from exc
    else:
        raise AdvisoryValidationError("real advisory did not return structured data")
    validate_advisory(result, calls=tuple(calls), evidence_ids=evidence_ids)
    after = factory.ledger.snapshot()
    return AdvisoryRun(
        result=result,
        tool_calls=tuple(calls),
        provider=factory.provenance(),
        latency_ms=round((time.perf_counter() - started) * 1000),
        usage=_usage_delta(before, after),
    )


def run_live_advisory(
    packet: Mapping[str, Any], *, factory: BedrockNovaProFactory, question: str
) -> AdvisoryRun:
    """Synchronously execute one bounded real Strands turn for the local HTTP gateway."""

    clean_question = " ".join(question.split())
    if not clean_question or len(clean_question) > 500:
        raise AdvisoryValidationError("question must contain between 1 and 500 visible characters")
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_invoke(packet, factory=factory, question=clean_question))
    raise AdvisoryUnavailable("real advisory cannot run inside an active event loop")


def _usage_delta(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: after.get(key, 0) - before.get(key, 0)
        for key in ("request_count", "input_tokens", "output_tokens", "incremental_cost_usd")
    }
