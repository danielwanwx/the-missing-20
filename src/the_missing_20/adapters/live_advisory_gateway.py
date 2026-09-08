"""Fail-closed gateway from the dashboard to the real read-only advisory agent."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from decimal import Decimal
from typing import Any, Protocol

from the_missing_20.adapters.investigation_case_sources import investigation_packet
from the_missing_20.adapters.strands_models import BedrockNovaProConfig, BedrockNovaProFactory
from the_missing_20.agents.live_advisory import (
    ADVISORY_OUTPUT_TOKENS,
    AdvisoryRun,
    AdvisoryUnavailable,
    AdvisoryValidationError,
    live_recovery_packet,
    run_live_advisory,
)
from the_missing_20.config import Settings
from the_missing_20.ports.agent_model import AgentBudget, AgentBudgetLedger, AgentProvider

AdvisoryRunner = Callable[..., AdvisoryRun]
PacketFactory = Callable[[Mapping[str, object]], Mapping[str, Any]]


def competition_investigation_packet(projection: Mapping[str, object]) -> Mapping[str, Any]:
    """Use unsolved raw records before execution and current facts after execution."""

    execution = projection.get("execution")
    execution_status = str(execution.get("status", "")) if isinstance(execution, Mapping) else ""
    if execution_status in {"VERIFYING", "VERIFIED"}:
        return live_recovery_packet(projection)
    demo_case = projection.get("demo_case")
    case = demo_case.get("case") if isinstance(demo_case, Mapping) else None
    if not isinstance(case, Mapping):
        raise ValueError("current projection lacks a scoped demo case")
    scenario = projection.get("scenario")
    variant = (
        str(scenario.get("variant", "uncommitted_receipt"))
        if isinstance(scenario, Mapping)
        else "uncommitted_receipt"
    )
    packet = investigation_packet(variant, case=case)  # type: ignore[arg-type]
    connected_operations = projection.get("connected_operations")
    sources = packet.get("tool_payload", {}).get("sources")
    control_context = sources.get("read_control_context") if isinstance(sources, Mapping) else None
    if isinstance(connected_operations, Mapping) and isinstance(control_context, dict):
        # Keep the existing bounded tool contract stable while giving the Agent
        # the same derived cross-system risk signal visible to the operator.
        # The nested payload remains disclosed-synthetic and read-only.
        control_context["connected_operations"] = dict(connected_operations)
    agent_run = projection.get("agent_run")
    packet["run_id"] = str(agent_run.get("run_id", "")) if isinstance(agent_run, Mapping) else ""
    packet["case_version"] = projection.get("case_version")
    return packet


def connected_competition_investigation_packet(
    projection: Mapping[str, object],
    *,
    erp_evidence: Mapping[str, object],
    saas_evidence: Mapping[str, object],
) -> Mapping[str, Any]:
    """Attach fresh, redacted SaaS read receipts to the normalized case packet.

    The normalized records keep the synthetic demo scenario deterministic. The
    attached live reads prove which external records were actually fetched for
    this Agent turn; credentials and provider-write capabilities never enter the
    packet.
    """

    packet = dict(competition_investigation_packet(projection))
    tool_payload = packet.get("tool_payload")
    if not isinstance(tool_payload, Mapping):
        return packet
    raw_sources = tool_payload.get("sources")
    if not isinstance(raw_sources, Mapping):
        return packet
    sources = {
        name: dict(payload) for name, payload in raw_sources.items() if isinstance(payload, Mapping)
    }
    admitted = [str(item) for item in packet.get("evidence_ids", ()) if str(item)]
    connected_sources = 0
    receipts: list[dict[str, object]] = []

    if str(erp_evidence.get("status", "")).upper() == "CONNECTED":
        documents = [
            dict(item) for item in erp_evidence.get("documents", []) if isinstance(item, Mapping)
        ]
        names = [str(item.get("name", "")) for item in documents if item.get("name")]
        live_read = {
            "source_id": "erpnext-missing20",
            "provider": str(erp_evidence.get("provider", "ERPNext")),
            "status": "CONNECTED",
            "sequence": erp_evidence.get("sequence"),
            "received_at": erp_evidence.get("received_at"),
            "read_only": True,
            "documents": documents,
        }
        sources.setdefault("read_erp_evidence", {})["live_read"] = live_read
        sources["read_erp_evidence"].setdefault("evidence_ids", []).extend(names)
        admitted.extend(names)
        receipts.append(live_read)
        connected_sources += 1

    provider_map = {
        "airtable-quality-registry": "read_airtable_evidence",
        "celigo-quality-release": "read_celigo_evidence",
    }
    collaboration_reads: list[dict[str, object]] = []
    raw_saas_sources = saas_evidence.get("sources", [])
    if str(saas_evidence.get("status", "")).upper() == "CONNECTED" and isinstance(
        raw_saas_sources, list
    ):
        for item in raw_saas_sources:
            if not isinstance(item, Mapping):
                continue
            source_id = str(item.get("source_id", ""))
            record_id = str(item.get("record_id", ""))
            if not source_id or not record_id:
                continue
            live_read = {
                key: value
                for key, value in item.items()
                if key
                in {
                    "source_id",
                    "provider",
                    "record_id",
                    "status",
                    "read_only",
                    "occurred_at",
                    "detail",
                    "correlation",
                    "erp_acknowledged",
                }
            }
            tool_name = provider_map.get(source_id)
            if tool_name:
                sources.setdefault(tool_name, {})["live_read"] = live_read
                sources[tool_name].setdefault("evidence_ids", []).append(record_id)
            elif source_id in {"jira-capa", "slack-quality-alerts"}:
                collaboration_reads.append(live_read)
                sources.setdefault("read_collaboration_evidence", {}).setdefault(
                    "evidence_ids", []
                ).append(record_id)
            else:
                continue
            admitted.append(record_id)
            receipts.append(live_read)
            connected_sources += 1
    if collaboration_reads:
        sources.setdefault("read_collaboration_evidence", {})["live_reads"] = collaboration_reads

    control = sources.get("read_control_context")
    if isinstance(control, dict):
        control["connected_source_receipts"] = [
            {
                "source_id": receipt.get("source_id"),
                "provider": receipt.get("provider"),
                "status": receipt.get("status"),
                "received_at": receipt.get("received_at") or receipt.get("occurred_at"),
            }
            for receipt in receipts
        ]
    packet["tool_payload"] = {"sources": sources}
    packet["evidence_ids"] = tuple(dict.fromkeys(admitted))
    packet["connected_sources"] = connected_sources
    packet["source"] = "connected-demo-evidence" if connected_sources else packet.get("source")
    return packet


class AdvisoryProjection(Protocol):
    def current(self) -> dict[str, object]: ...


class DashboardAdvisoryGateway:
    """Expose real agent results while making every provider failure explicit."""

    def __init__(
        self,
        platform: AdvisoryProjection,
        *,
        settings: Settings | None = None,
        runner: AdvisoryRunner = run_live_advisory,
        packet_factory: PacketFactory = live_recovery_packet,
    ) -> None:
        self._platform = platform
        self._settings = settings or Settings.from_env()
        self._runner = runner
        self._packet_factory = packet_factory

    def runtime_truth(self) -> dict[str, object]:
        """Expose non-secret provider configuration without making a provider call."""

        configured = self._settings.agent_provider is AgentProvider.BEDROCK
        return {
            "provider_mode": self._settings.agent_provider.value,
            "provider_configured": configured,
            "region": self._settings.aws_region if configured else "",
        }

    def _run(
        self, packet: Mapping[str, Any], *, question: str, emit_progress: bool = False
    ) -> AdvisoryRun:
        kwargs: dict[str, Any] = {"factory": self._factory(), "question": question}
        progress = getattr(self._platform, "record_agent_tool_progress", None)
        runtime_progress = getattr(self._platform, "record_agent_runtime_progress", None)
        if emit_progress and self._runner is run_live_advisory:
            run_id = str(packet.get("run_id", ""))
            if callable(progress):
                kwargs["on_tool_call"] = lambda tool_name, phase="started": progress(
                    tool_name, phase, run_id
                )
            if callable(runtime_progress):
                kwargs["on_runtime_event"] = lambda event: runtime_progress(event, run_id)
        return self._runner(packet, **kwargs)

    def ask(self, question: str) -> dict[str, object]:
        """Run real advisory chat or return an unmistakably unavailable result."""

        projection = self._platform.current()
        clean_question = " ".join(question.split())
        if not clean_question or len(clean_question) > 500:
            return self._unavailable(
                projection,
                code="VALIDATION_FAILED",
                detail="Ask a specific evidence question using at most 500 characters.",
            )
        if self._settings.agent_provider is not AgentProvider.BEDROCK:
            return self._unavailable(
                projection,
                code="AGENT_UNAVAILABLE",
                detail="Real Strands Agent is not configured; no fallback answer was generated.",
            )
        try:
            packet = self._packet_factory(projection)
            history = self._conversation_history(projection)
            contextual_question = self._contextual_question(history, clean_question)
            run = self._run(packet, question=contextual_question)
        except AdvisoryValidationError as error:
            failed = self._unavailable(
                projection,
                code="VALIDATION_FAILED",
                detail="The real Agent response failed safety validation; no conclusion was shown.",
            )
            failed["validation_diagnostics"] = error.diagnostics
            return failed
        except (AdvisoryUnavailable, OSError, ValueError):
            return self._unavailable(
                projection,
                code="AGENT_UNAVAILABLE",
                detail="The real Strands Agent is unavailable; no fallback answer was generated.",
            )
        result = run.result.model_dump(mode="json")
        answer = (
            f"Disposition: {result['disposition']}. {result['reason']} "
            f"Next: {result['safe_next_step']}"
        )
        advisory = {
            "status": "COMPLETE",
            "mode": "real_strands",
            "provider": run.provider,
            "tool_calls": list(run.tool_calls),
            "latency_ms": run.latency_ms,
            "usage": run.usage,
            "result": result,
            "evidence_findings": run.evidence_findings,
            "runtime_events": list(run.runtime_events),
            "context_turns": len(history),
        }
        record_turn = getattr(self._platform, "record_conversation_turn", None)
        if callable(record_turn):
            projection = record_turn(
                clean_question,
                answer,
                {**advisory, "evidence_ids": result.get("evidence_ids", [])},
            )
        return {
            **projection,
            "answer": answer,
            "agent_advisory": advisory,
        }

    @staticmethod
    def _conversation_history(projection: Mapping[str, object]) -> list[dict[str, str]]:
        """Return a bounded, display-safe history for a continuing evidence dialogue."""

        raw = projection.get("conversation", [])
        if not isinstance(raw, list):
            return []
        history: list[dict[str, str]] = []
        for turn in raw[-3:]:
            if not isinstance(turn, Mapping):
                continue
            question = " ".join(str(turn.get("question", "")).split())[:300]
            answer = " ".join(str(turn.get("answer", "")).split())[:650]
            if question and answer:
                history.append({"human": question, "agent": answer})
        return history

    @staticmethod
    def _contextual_question(history: list[dict[str, str]], question: str) -> str:
        if not history:
            return question
        transcript = "\n".join(
            f"Human: {turn['human']}\nEvidence Agent: {turn['agent']}" for turn in history
        )
        return (
            "Continue the evidence conversation below. Treat prior dialogue only as context, "
            "not as current evidence. Resolve references in the new question. Before answering "
            "this turn, you MUST call read_control_context, read_erp_evidence, "
            "read_airtable_evidence, read_celigo_evidence, read_collaboration_evidence, and then "
            "reconcile_source_records exactly once. Do not answer from the transcript alone.\n\n"
            f"Prior conversation:\n{transcript}\n\nNewest human question: {question}"
        )

    def investigate(self, projection: Mapping[str, object]) -> dict[str, object]:
        """Run the same real Strands boundary used by chat for the primary case flow.

        The returned record is deliberately advisory-only.  The caller persists it
        beside deterministic policy events; it never gives a model authority to
        approve or execute a provider change.
        """

        if self._settings.agent_provider is not AgentProvider.BEDROCK:
            return {
                "status": "AGENT_UNAVAILABLE",
                "mode": "real_strands",
                "tool_calls": [],
                "result": None,
                "detail": "Real Strands Agent is not configured; no fallback conclusion was used.",
            }
        try:
            packet = self._packet_factory(projection)
            run = self._run(
                packet,
                emit_progress=True,
                question=(
                    "Investigate this case. Read the source evidence you need, compare "
                    "the competing hypotheses, and explain each discrepancy with its "
                    "observed quantity and source evidence. Then state a safe next step."
                ),
            )
        except AdvisoryValidationError as error:
            return {
                "validation_diagnostics": error.diagnostics,
                "status": "VALIDATION_FAILED",
                "mode": "real_strands",
                "tool_calls": [],
                "result": None,
                "detail": (
                    "The real Strands response failed safety validation; no conclusion was used."
                ),
            }
        except (AdvisoryUnavailable, OSError, ValueError) as error:
            return {
                "status": "AGENT_UNAVAILABLE",
                "mode": "real_strands",
                "tool_calls": [],
                "result": None,
                "detail": "The real Strands Agent is unavailable; no fallback conclusion was used.",
                "diagnostic": f"{type(error).__name__}: {error}",
            }
        return {
            "status": "COMPLETE",
            "case_id": packet.get("case_id"),
            "run_id": packet.get("run_id"),
            "case_version": packet.get("case_version"),
            "mode": "real_strands",
            "provider": run.provider,
            "tool_calls": list(run.tool_calls),
            "latency_ms": run.latency_ms,
            "usage": run.usage,
            "result": run.result.model_dump(mode="json"),
            "evidence_findings": run.evidence_findings,
            "runtime_events": list(run.runtime_events),
        }

    def _factory(self) -> BedrockNovaProFactory:
        budget = AgentBudget(
            max_requests=16,
            max_input_tokens=250_000,
            # A source investigation uses six tool/model turns and may need up to
            # two typed-output repairs.  Four thousand tokens could exhaust the
            # shared ledger before the bounded repair path was allowed to run,
            # turning a valid read into an avoidable safe-stop.  Keep the strict
            # per-request ceiling and cost cap, but size the run-level envelope
            # for the workflow it actually permits.
            max_output_tokens=12_000,
            max_output_tokens_per_request=ADVISORY_OUTPUT_TOKENS,
            prior_cost_usd=Decimal("0"),
            incremental_cost_cap_usd=Decimal("0.08"),
            cumulative_cost_cap_usd=Decimal("0.08"),
            per_call_timeout_seconds=90,
            whole_run_timeout_seconds=120,
        )
        return BedrockNovaProFactory(
            BedrockNovaProConfig(
                region=self._settings.aws_region,
                aws_profile=self._settings.aws_profile,
                max_tokens=ADVISORY_OUTPUT_TOKENS,
                temperature=0,
                budget=budget,
            ),
            ledger=AgentBudgetLedger(budget),
        )

    @staticmethod
    def _unavailable(
        projection: Mapping[str, object], *, code: str, detail: str
    ) -> dict[str, object]:
        return {
            **projection,
            "answer": detail,
            "agent_advisory": {
                "status": code,
                "mode": "real_strands",
                "tool_calls": [],
                "result": None,
            },
        }
