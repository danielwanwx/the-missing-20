"""Fail-closed gateway from the dashboard to the real read-only advisory agent."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from decimal import Decimal
from typing import Any, Protocol
from uuid import uuid4

from the_missing_20.adapters.conversation_views import history_attachment, retained_history_view
from the_missing_20.adapters.investigation_case_sources import investigation_packet
from the_missing_20.adapters.role_task_journal import RoleTaskJournal
from the_missing_20.adapters.strands_models import BedrockNovaProConfig, BedrockNovaProFactory
from the_missing_20.agents.live_advisory import (
    ADVISORY_OUTPUT_TOKENS,
    AdvisoryRun,
    AdvisoryUnavailable,
    AdvisoryValidationError,
    live_recovery_packet,
    run_live_advisory,
)
from the_missing_20.agents.receiving_facts import receipt_relations, reference_candidates
from the_missing_20.config import Settings
from the_missing_20.ports.agent_model import AgentBudget, AgentBudgetLedger, AgentProvider

AdvisoryRunner = Callable[..., AdvisoryRun]
PacketFactory = Callable[[Mapping[str, object]], Mapping[str, Any]]


def public_validation_diagnostics(diagnostics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep rejected model prose in private audit artifacts, never in the browser response."""
    allowed = {"stage", "case_id", "attempt", "disposition", "tool_calls", "failure", "stop_reason"}
    return [
        {key: value for key, value in attempt.items() if key in allowed} for attempt in diagnostics
    ]


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
    """Keep connection proof separate from an isolated synthetic case's facts.

    Current external records can belong to another PO or a later business state.
    A successful read does not admit those records as evidence for this synthetic
    case. Actual live-case investigation uses live_recovery_packet instead.
    """

    packet = dict(competition_investigation_packet(projection))
    receipts: list[dict[str, object]] = []

    if str(erp_evidence.get("status", "")).upper() == "CONNECTED":
        documents = erp_evidence.get("documents", [])
        receipts.append(
            {
                "source_id": "erpnext-missing20",
                "provider": str(erp_evidence.get("provider", "ERPNext")),
                "status": "CONNECTED",
                "sequence": erp_evidence.get("sequence"),
                "received_at": erp_evidence.get("received_at"),
                "read_only": True,
                "record_count": len(documents) if isinstance(documents, list) else 0,
                "case_evidence": False,
            }
        )

    provider_ids = {
        "airtable-quality-registry",
        "celigo-quality-release",
        "jira-capa",
        "slack-quality-alerts",
    }
    raw_saas_sources = saas_evidence.get("sources", [])
    if str(saas_evidence.get("status", "")).upper() == "CONNECTED" and isinstance(
        raw_saas_sources, list
    ):
        for item in raw_saas_sources:
            if not isinstance(item, Mapping):
                continue
            source_id = str(item.get("source_id", ""))
            if source_id not in provider_ids or not item.get("record_id"):
                continue
            receipts.append(
                {
                    "source_id": source_id,
                    "provider": str(item.get("provider", "")),
                    "status": item.get("status"),
                    "sequence": saas_evidence.get("sequence"),
                    "received_at": saas_evidence.get("received_at") or item.get("occurred_at"),
                    "read_only": True,
                    "record_count": 1,
                    "case_evidence": False,
                }
            )
    packet["connection_receipts"] = receipts
    packet["connected_sources"] = len(receipts)
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
        delegation_journal: RoleTaskJournal | None = None,
    ) -> None:
        self._platform = platform
        self._settings = settings or Settings.from_env()
        self._runner = runner
        self._packet_factory = packet_factory
        self._delegation_journal = delegation_journal

    def runtime_truth(self) -> dict[str, object]:
        """Expose non-secret provider configuration without making a provider call."""

        configured = self._settings.agent_provider is AgentProvider.BEDROCK
        return {
            "provider_mode": self._settings.agent_provider.value,
            "provider_configured": configured,
            "region": self._settings.aws_region if configured else "",
        }

    def _run(
        self,
        packet: Mapping[str, Any],
        *,
        question: str,
        emit_progress: bool = False,
        conversation_id: str = "",
    ) -> AdvisoryRun:
        if conversation_id and self._delegation_journal is not None:
            # Each human turn has independent work ownership, not the last diagnosis's run.
            packet = {**packet, "run_id": f"conversation:{conversation_id}"}
        kwargs: dict[str, Any] = {"factory": self._factory(), "question": question}
        if (
            self._delegation_journal is not None
            and packet.get("case_class") == "source_investigation"
        ):
            kwargs["delegation_journal"] = self._delegation_journal
            is_active = getattr(self._platform, "agent_run_is_active", None)
            if emit_progress:
                if not callable(is_active):
                    raise AdvisoryUnavailable("role workflow requires a parent-run guard")
                kwargs["continue_requested"] = lambda: is_active(str(packet.get("run_id", "")))
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
        if conversation_id and self._runner is run_live_advisory:
            chat_progress = getattr(self._platform, "record_conversation_tool_progress", None)
            if callable(chat_progress):
                kwargs["on_tool_call"] = lambda name, phase="started": chat_progress(
                    name, phase, conversation_id
                )
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
        record_request = getattr(self._platform, "record_human_request", None)
        prior_projection = dict(projection)
        if callable(record_request):
            projection = {
                **projection,
                **record_request(clean_question, str(projection.get("case_id", ""))),
            }
        if self._settings.agent_provider is not AgentProvider.BEDROCK:
            return self._unavailable(
                projection,
                code="AGENT_UNAVAILABLE",
                detail="Real Strands Agent is not configured; no fallback answer was generated.",
            )
        freshness = projection.get("source_freshness")
        if isinstance(freshness, Mapping) and freshness.get("status") == "UNAVAILABLE":
            response = self._unavailable(
                projection,
                code="SOURCE_UNAVAILABLE",
                detail="Current ERP evidence is unavailable; no model request was started. "
                "Retained observations remain available in Dashboard trends.",
            )
            unavailable_advisory = response["agent_advisory"]
            if isinstance(unavailable_advisory, dict):
                unavailable_advisory["mode"] = "not_invoked"
                retained_views = retained_history_view(projection, clean_question)
                if retained_views:
                    unavailable_advisory["retained_views"] = retained_views
            return response
        try:
            packet = dict(self._packet_factory(projection))
            raw_intent = projection.get("human_intent", {})
            intent = raw_intent if isinstance(raw_intent, Mapping) else {}
            packet["read_only_requested"] = bool(intent.get("read_only_requested"))
            # Broad diagnosis requires the complete discrepancy partition. A
            # focused dialogue turn must answer its actual question; safety and
            # contradiction checks still use the unchanged current-case facts.
            broad_question = any(
                word in clean_question.lower()
                for word in (
                    "attention",
                    "diagnos",
                    "all discrep",
                    "overall",
                    "current status",
                    "what is wrong",
                    "注意",
                    "诊断",
                    "整体",
                    "所有问题",
                )
            )
            if broad_question:
                packet["explanation_scope"] = "full_investigation"
            else:
                packet["expected_reason_quantities"] = ()
            if packet.get("case_class") == "receiving_operations":
                sources = packet["tool_payload"]["sources"]
                turns = prior_projection.get("conversation", [])
                last = turns[-1] if isinstance(turns, list) and turns else {}
                previous = last.get("receiving_references", {}) if isinstance(last, Mapping) else {}
                sources["read_control_context"] = {
                    **sources["read_control_context"],
                    "prior_reference_candidates": reference_candidates(
                        previous if isinstance(previous, Mapping) else {},
                        case_id=packet["case_id"],
                        relations=receipt_relations(sources["read_erp_evidence"]),
                        source_sequence=projection.get("case_projection", {}).get(
                            "source_sequence"
                        ),
                    ),
                }
            history = self._conversation_history(prior_projection)
            contextual_question = self._contextual_question(
                history,
                clean_question,
                include_prior_answers=packet.get("case_class") != "receiving_operations",
            )
            if packet["read_only_requested"]:
                contextual_question += (
                    "\nRetained human constraint: decline/refusal/read-only remains active. "
                    "Acknowledge it; continuing investigation does not authorize a write. "
                    "This preserves the authority constraint, not earlier question topics."
                )
            if "read_operational_history" in packet.get("tool_payload", {}).get("sources", {}):
                contextual_question += (
                    "\nIf this asks for trends or benchmarks, read_operational_history and select "
                    "chart_metric; the server will render its actual source data. Never invent "
                    "history. Offer up to three useful read-only follow_up_questions."
                )
            # Keep the actual current request last, after context and retained
            # authority. Repeating the entire old refusal message here used to
            # accidentally reactivate its unrelated history/revenue questions.
            if contextual_question != clean_question:
                contextual_question += "\nNewest human question: " + clean_question
            run = self._run(packet, question=contextual_question, conversation_id=uuid4().hex)
        except AdvisoryValidationError as error:
            failed = self._unavailable(
                projection,
                code="VALIDATION_FAILED",
                detail="The real Agent response failed safety validation; no conclusion was shown.",
            )
            failed["validation_diagnostics"] = public_validation_diagnostics(error.diagnostics)
            advisory_failure = failed["agent_advisory"]
            if isinstance(advisory_failure, dict):
                advisory_failure["usage"] = error.usage
            return failed
        except (AdvisoryUnavailable, OSError, ValueError) as error:
            failed = self._unavailable(
                projection,
                code="AGENT_UNAVAILABLE",
                detail="The real Strands Agent is unavailable; no fallback answer was generated.",
            )
            if isinstance(error, AdvisoryUnavailable):
                failed["validation_diagnostics"] = public_validation_diagnostics(error.diagnostics)
                advisory_failure = failed["agent_advisory"]
                if isinstance(advisory_failure, dict):
                    advisory_failure["usage"] = error.usage
            return failed
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
            "attachments": history_attachment(
                packet, run.result.chart_metric, run.tool_calls, question=clean_question
            ),
            "follow_up_questions": [question[:160] for question in run.result.follow_up_questions],
        }
        if packet.get("case_class") == "receiving_operations":
            relations = receipt_relations(packet["tool_payload"]["sources"]["read_erp_evidence"])
            cited = set(result.get("evidence_ids", []))
            advisory["receiving_references"] = {
                "case_id": packet["case_id"],
                "status": "COMPLETE",
                "source_sequence": projection.get("case_projection", {}).get("source_sequence"),
                "receipt_ids": sorted(
                    {
                        row["receipt_id"]
                        for row in relations
                        if row["receipt_id"] in cited or row["evidence_id"] in cited
                    }
                ),
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
        # Include requests whose model turn failed; never include rejected prose.
        requests = projection.get("human_requests", [])
        if isinstance(requests, list):
            for request in requests[-3:]:
                if not isinstance(request, Mapping):
                    continue
                question = str(request.get("question", ""))[:300]
                if question and not any(turn["human"] == question for turn in history):
                    history.append({"human": question, "agent": "No validated answer recorded."})
        return history[-3:]

    @staticmethod
    def _contextual_question(
        history: list[dict[str, str]],
        question: str,
        *,
        include_prior_answers: bool = True,
    ) -> str:
        if not history:
            return question
        transcript = "\n".join(
            f"Human: {turn['human']}"
            + (f"\nEvidence Agent: {turn['agent']}" if include_prior_answers else "")
            for turn in history
        )
        return (
            "Continue the evidence conversation below. Treat prior dialogue only as context, "
            "not as current evidence or a list of questions to answer again. Resolve references "
            "in the new question, but answer ONLY the newest question. Do not add old trend, "
            "baseline or revenue topics unless this newest question asks for them. "
            "Before answering this turn, you MUST call read_control_context, read_erp_evidence, "
            "read_airtable_evidence, read_celigo_evidence, read_collaboration_evidence exactly "
            "once. If reconcile_source_records is available for this lifecycle, use it after "
            "those reads. Do not request tools absent from this lifecycle. "
            "Do not answer from the transcript alone.\n\n"
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
            packet = dict(self._packet_factory(projection))
            packet["explanation_scope"] = "full_investigation"
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
                "validation_diagnostics": public_validation_diagnostics(error.diagnostics),
                "usage": error.usage,
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
                "validation_diagnostics": (
                    error.diagnostics if isinstance(error, AdvisoryUnavailable) else []
                ),
                "usage": error.usage if isinstance(error, AdvisoryUnavailable) else {},
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
            # A team can consume several bounded expert turns in addition to
            # the coordinator. Token/request/time ceilings remain independent.
            max_requests=32 if self._delegation_journal is not None else 16,
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
            # Real three-turn receiving/history acceptance reached ~USD 0.04
            # before the conservative byte-as-token reservation for synthesis.
            # USD 0.08 could reject that final request despite low actual use.
            # Reserve room for the bounded evidence + synthesis workflow; never
            # relax pre-request accounting or turn an exhausted run into a fallback.
            incremental_cost_cap_usd=Decimal("0.16"),
            cumulative_cost_cap_usd=Decimal("0.16"),
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
