"""Fail-closed gateway from the dashboard to the real read-only advisory agent."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from decimal import Decimal
from pathlib import Path
from threading import RLock
from typing import Any, Protocol
from uuid import uuid4

from the_missing_20.adapters import dialogue_intent
from the_missing_20.adapters.conversation_views import history_attachment, retained_history_view
from the_missing_20.adapters.investigation_case_sources import investigation_packet
from the_missing_20.adapters.native_receiving_dialogue import (
    NATIVE_RECEIVING_SCHEMA_VERSION,
    NativeReceivingRun,
    run_native_receiving_turn,
)
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
from the_missing_20.agents.receiving_advisory import post_invoice_receiving_packet
from the_missing_20.agents.receiving_facts import receipt_relations
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
        native_receiving_session_root: Path | None = None,
    ) -> None:
        self._platform = platform
        self._settings = settings or Settings.from_env()
        self._runner = runner
        self._packet_factory = packet_factory
        self._delegation_journal = delegation_journal
        self._native_receiving_session_root = native_receiving_session_root
        # This serializes one gateway instance only. The supported boundary is
        # one local operator/runtime, not a distributed multi-process lock.
        self._ask_lock = RLock()
        self._fallback_conversation_id = uuid4().hex

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

    def ask(self, question: str, *, new_conversation: bool = False) -> dict[str, object]:
        """Run one serialized, source-fresh advisory turn for this local runtime."""

        # Holding the lock before *both* source reads means a second request on
        # this gateway cannot construct a packet from a projection superseded by
        # the first request's saved human intent.
        with self._ask_lock:
            return self._ask_locked(question, new_conversation=new_conversation)

    def _ask_locked(self, question: str, *, new_conversation: bool) -> dict[str, object]:
        projection = self._platform.current()
        clean_question = " ".join(question.split())
        if not question.strip() or len(question) > 500:
            return self._unavailable(
                projection,
                code="VALIDATION_FAILED",
                detail="Ask a specific evidence question using at most 500 characters.",
            )

        # Keep the original bounded wording. Normalization remains validation
        # only; it is never used to replace a persisted user message.
        current_question = question
        case_id = str(projection.get("case_id", ""))
        recorded = self._record_human_request(
            current_question, case_id, new_conversation=new_conversation
        )
        fresh_projection = self._platform.current()
        if str(fresh_projection.get("case_id", "")) != case_id:
            return self._unavailable(
                fresh_projection,
                code="CONTEXT_SCOPE_CHANGED",
                detail=(
                    "The case changed while the human request was being saved; no model request "
                    "was started. Reread the current case before asking again."
                ),
            )
        projection = {**projection, **fresh_projection}
        for key in ("human_intent", "human_requests", "dialogue_context"):
            if key in recorded:
                projection[key] = recorded[key]

        # Saving the request precedes every failure path, including a source
        # outage or an unconfigured provider. The outage boundary comes first
        # because it must never consume a model request in any provider mode.
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
        if self._settings.agent_provider is not AgentProvider.BEDROCK:
            return self._unavailable(
                projection,
                code="AGENT_UNAVAILABLE",
                detail="Real Strands Agent is not configured; no fallback answer was generated.",
            )

        context_state = self._dialogue_context(projection)
        conversation_id = self._conversation_id(context_state)
        prior_requests = self._prior_human_requests(projection, current_question)
        authority_context = self._authority_context(projection)
        stored_omissions = self._stored_omissions(context_state)
        try:
            packet = dict(self._packet_factory(projection))
            raw_intent = projection.get("human_intent", {})
            intent = raw_intent if isinstance(raw_intent, Mapping) else {}
            packet["read_only_requested"] = bool(intent.get("read_only_requested"))
            native_session_root = self._native_receiving_session_root
            if native_session_root is None:
                native_packet = None
            else:
                try:
                    native_packet = self._native_receiving_packet(packet, projection)
                except ValueError:
                    failed = self._unavailable(
                        projection,
                        code="SOURCE_UNAVAILABLE",
                        detail=(
                            "Current supplier-invoice evidence is unavailable or does not match "
                            "this receiving workspace; no model request was started."
                        ),
                    )
                    failed_advisory = failed["agent_advisory"]
                    if isinstance(failed_advisory, dict):
                        failed_advisory["mode"] = "not_invoked"
                    return failed
            if native_packet is not None and native_session_root is not None:
                runtime_instance_id = context_state.get("runtime_instance_id")
                if not isinstance(runtime_instance_id, str):
                    raise RuntimeError("native receiving requires a persisted runtime identity")
                native_run = run_native_receiving_turn(
                    session_root=native_session_root,
                    runtime_instance_id=runtime_instance_id,
                    case_id=case_id,
                    conversation_id=conversation_id,
                    packet=native_packet,
                    question=current_question,
                    factory=self._factory(),
                )
                return self._complete_native_receiving(
                    projection=projection,
                    case_id=case_id,
                    conversation_id=conversation_id,
                    current_question=current_question,
                    context_state=context_state,
                    native_run=native_run,
                )
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

            relations: list[dict[str, Any]] = []
            if packet.get("case_class") == "receiving_operations":
                relations = self._attach_rejoined_reference_candidates(
                    packet,
                    projection=projection,
                    context_state=context_state,
                    current_question=current_question,
                )

            packed = self._pack_contextual_question(
                packet,
                prior_requests=prior_requests,
                current_question=current_question,
                authority_context=authority_context,
            )
            packed_omissions = packed.get("omitted_requests")
            omitted_turns = stored_omissions + (
                packed_omissions if isinstance(packed_omissions, int) else 0
            )
            if packed["input_limit"] is True:
                limited = self._unavailable(
                    projection,
                    code="CONTEXT_LIMIT",
                    detail=(
                        "The complete current question and required authority/context exceed the "
                        "accepted input limit; no model request was started."
                    ),
                )
                limited_advisory = limited["agent_advisory"]
                if isinstance(limited_advisory, dict):
                    limited_advisory.update(
                        {
                            "conversation_id": conversation_id,
                            "context_turns": 0,
                            "omitted_turns": omitted_turns,
                        }
                    )
                return limited
            contextual_question = str(packed["prompt"])
            run = self._run(packet, question=contextual_question, conversation_id=conversation_id)
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
        except (AdvisoryUnavailable, OSError, RuntimeError, ValueError) as error:
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

        # The gateway lock only protects asks that enter this instance. A case
        # reset or an explicit new conversation can still happen elsewhere
        # while inference is running, so never display or persist a completion
        # that no longer belongs to the captured scope.
        completion_projection = self._platform.current()
        if not self._scope_matches(completion_projection, case_id, conversation_id):
            return self._scope_changed(completion_projection)
        projection = completion_projection
        result = run.result.model_dump(mode="json")
        answer = (
            f"Disposition: {result['disposition']}. {result['reason']} "
            f"Next: {result['safe_next_step']}"
        )
        included_questions = packed.get("included_questions")
        advisory: dict[str, Any] = {
            "status": "COMPLETE",
            "mode": "real_strands",
            "provider": run.provider,
            "tool_calls": list(run.tool_calls),
            "latency_ms": run.latency_ms,
            "usage": run.usage,
            "result": result,
            "evidence_findings": run.evidence_findings,
            "runtime_events": list(run.runtime_events),
            "conversation_id": conversation_id,
            "context_turns": len(included_questions) if isinstance(included_questions, list) else 0,
            "omitted_turns": omitted_turns,
            "attachments": history_attachment(
                packet, run.result.chart_metric, run.tool_calls, question=clean_question
            ),
            "follow_up_questions": [question[:160] for question in run.result.follow_up_questions],
        }
        if packet.get("case_class") == "receiving_operations":
            receipt_ids = self._cited_receipt_ids(relations, result.get("evidence_ids", []))
            source_sequence = self._source_sequence(projection)
            advisory["receiving_references"] = {
                "case_id": packet["case_id"],
                "status": "COMPLETE",
                "source_sequence": source_sequence,
                "receipt_ids": receipt_ids,
                "question": current_question,
                "provenance": "runtime_validated",
            }
            if receipt_ids:
                advisory["dialogue_reference_group"] = {
                    "case_id": packet["case_id"],
                    "question": current_question,
                    "receipt_ids": receipt_ids,
                    "provenance": "runtime_validated",
                }
        record_turn = getattr(self._platform, "record_conversation_turn", None)
        if callable(record_turn):
            recorded_turn = record_turn(
                current_question,
                answer,
                {**advisory, "evidence_ids": result.get("evidence_ids", [])},
                expected_case_id=case_id,
                expected_conversation_id=conversation_id,
            )
            if isinstance(recorded_turn, Mapping):
                projection = dict(recorded_turn)
            if not self._scope_matches(projection, case_id, conversation_id):
                return self._scope_changed(projection)
        return {
            **projection,
            "answer": answer,
            "agent_advisory": advisory,
        }

    def _complete_native_receiving(
        self,
        *,
        projection: Mapping[str, object],
        case_id: str,
        conversation_id: str,
        current_question: str,
        context_state: Mapping[str, object],
        native_run: NativeReceivingRun,
    ) -> dict[str, object]:
        """Persist an N1 answer without inventing advisory-policy fields or citations."""

        completion_projection = self._platform.current()
        if not self._scope_matches(completion_projection, case_id, conversation_id):
            return self._scope_changed(completion_projection)
        projection = completion_projection
        advisory: dict[str, Any] = {
            "status": "COMPLETE",
            "mode": "native_receiving_n1",
            "provider": native_run.provider,
            "tool_calls": list(native_run.tool_calls),
            "latency_ms": native_run.latency_ms,
            "usage": native_run.usage,
            "result": {
                "answer": native_run.answer,
                "semantic_status": "NOT_EVALUATED",
                "session_id": native_run.session_id,
                "session_schema_version": NATIVE_RECEIVING_SCHEMA_VERSION,
            },
            "semantic_status": "NOT_EVALUATED",
            "runtime_events": list(native_run.runtime_events),
            "conversation_id": conversation_id,
            "context_turns": native_run.context_turns,
            "omitted_turns": self._stored_omissions(context_state),
            "attachments": [],
            "follow_up_questions": [],
        }
        record_turn = getattr(self._platform, "record_conversation_turn", None)
        if callable(record_turn):
            recorded_turn = record_turn(
                current_question,
                native_run.answer,
                {**advisory, "evidence_ids": []},
                expected_case_id=case_id,
                expected_conversation_id=conversation_id,
            )
            if isinstance(recorded_turn, Mapping):
                projection = dict(recorded_turn)
            if not self._scope_matches(projection, case_id, conversation_id):
                return self._scope_changed(projection)
        return {
            **projection,
            "answer": native_run.answer,
            "agent_advisory": advisory,
        }

    def _record_human_request(
        self, question: str, case_id: str, *, new_conversation: bool
    ) -> dict[str, object]:
        record_request = getattr(self._platform, "record_human_request", None)
        if not callable(record_request):
            return {}
        recorded = record_request(question, case_id, new_conversation=new_conversation)
        return dict(recorded) if isinstance(recorded, Mapping) else {}

    @staticmethod
    def _dialogue_context(projection: Mapping[str, object]) -> dict[str, object]:
        raw = projection.get("dialogue_context")
        return dict(raw) if isinstance(raw, Mapping) else {}

    def _conversation_id(self, context_state: Mapping[str, object]) -> str:
        conversation_id = context_state.get("conversation_id")
        if isinstance(conversation_id, str) and conversation_id:
            return conversation_id
        return self._fallback_conversation_id

    def _scope_matches(
        self, projection: Mapping[str, object], case_id: str, conversation_id: str
    ) -> bool:
        if str(projection.get("case_id", "")) != case_id:
            return False
        context_state = self._dialogue_context(projection)
        if not context_state:
            return conversation_id == self._fallback_conversation_id
        return self._conversation_id(context_state) == conversation_id

    @staticmethod
    def _scope_changed(projection: Mapping[str, object]) -> dict[str, object]:
        return DashboardAdvisoryGateway._unavailable(
            projection,
            code="CONTEXT_SCOPE_CHANGED",
            detail=(
                "The case or conversation changed while the model was running; its result was "
                "discarded. Reread the current case before asking again."
            ),
        )

    @staticmethod
    def _prior_human_requests(
        projection: Mapping[str, object], current_question: str
    ) -> list[dict[str, object]]:
        raw_requests = projection.get("human_requests")
        if not isinstance(raw_requests, list):
            return []
        requests: list[dict[str, object]] = []
        for index, request in enumerate(raw_requests):
            if not isinstance(request, Mapping):
                continue
            question = request.get("question")
            if not isinstance(question, str) or not question.strip() or len(question) > 500:
                continue
            request_id = request.get("request_id")
            requests.append(
                {
                    "request_id": request_id
                    if isinstance(request_id, str) and request_id
                    else f"visible-request-{index}",
                    "question": question,
                }
            )
        if requests:
            last_question = str(requests[-1]["question"])
            if last_question == current_question or " ".join(last_question.split()) == " ".join(
                current_question.split()
            ):
                requests.pop()
        return requests

    @staticmethod
    def _authority_context(projection: Mapping[str, object]) -> str:
        raw_intent = projection.get("human_intent")
        intent = raw_intent if isinstance(raw_intent, Mapping) else {}
        if intent.get("read_only_requested") is not True:
            return ""
        return (
            "\n\nRetained human constraint: decline/refusal/read-only remains active. "
            "Continuing investigation does not authorize a write."
        )

    @staticmethod
    def _stored_omissions(context_state: Mapping[str, object]) -> int:
        omitted = context_state.get("requests_omitted")
        return omitted if isinstance(omitted, int) and not isinstance(omitted, bool) else 0

    @staticmethod
    def _native_receiving_packet(
        packet: Mapping[str, Any], projection: Mapping[str, object]
    ) -> dict[str, Any] | None:
        """Choose the native receiving contract without changing legacy routing.

        Before an invoice exists, the established receiving packet is already
        complete.  Once a current supplier invoice exists, the legacy generic
        investigation packet deliberately has a different invoice summary;
        native N1 instead requires the current, case-scoped receiving packet.
        """

        if packet.get("case_class") == "receiving_operations":
            return dict(packet)
        if not (
            packet.get("case_class") == "source_investigation"
            and packet.get("source") == "live-external-read"
        ):
            return None
        work = projection.get("receiving_work")
        case_projection = projection.get("case_projection")
        case = case_projection.get("case") if isinstance(case_projection, Mapping) else None
        if not (
            isinstance(work, Mapping)
            and isinstance(case, Mapping)
            and work.get("status") == "CONFIGURED"
            and work.get("case_id") == case.get("case_id")
            and work.get("purchase_order") == case.get("purchase_order")
            and packet.get("case_id") == case.get("case_id")
        ):
            return None
        # A matching current receiving workspace is an opt-in native case.
        # Let missing or mismatched PI source facts fail closed through the
        # gateway's existing unavailable path rather than returning to the
        # known-inapplicable generic invoice summary.
        return post_invoice_receiving_packet(projection)

    @staticmethod
    def _context_prefix(packet: Mapping[str, Any]) -> str:
        prefix = (
            "Continue the evidence conversation below. Treat prior user requests only as context, "
            "not as current evidence or a list of questions to answer again. Resolve references "
            "in the new question, but answer ONLY the newest question. Do not add old trend, "
            "baseline or revenue topics unless this newest question asks for them. "
            "Before answering this turn, you MUST call read_control_context, read_erp_evidence, "
            "read_airtable_evidence, read_celigo_evidence, read_collaboration_evidence exactly "
            "once. If reconcile_source_records is available for this lifecycle, use it after "
            "those reads. Do not request tools absent from this lifecycle. Do not answer from "
            "the transcript alone."
        )
        tool_payload = packet.get("tool_payload")
        sources = tool_payload.get("sources") if isinstance(tool_payload, Mapping) else None
        if isinstance(sources, Mapping) and "read_operational_history" in sources:
            prefix += (
                " If this asks for trends or benchmarks, read_operational_history and select "
                "chart_metric; the server will render its actual source data. Never invent "
                "history. Offer up to three useful read-only follow_up_questions."
            )
        return prefix

    def _pack_contextual_question(
        self,
        packet: Mapping[str, Any],
        *,
        prior_requests: list[dict[str, object]],
        current_question: str,
        authority_context: str,
    ) -> dict[str, object]:
        tool_payload = packet.get("tool_payload")
        sources = tool_payload.get("sources") if isinstance(tool_payload, Mapping) else None
        needs_context = bool(prior_requests or authority_context) or (
            isinstance(sources, Mapping) and "read_operational_history" in sources
        )
        if not needs_context:
            return {
                "prompt": current_question,
                "included_questions": [],
                "included_request_ids": [],
                "omitted_requests": 0,
                "input_limit": False,
            }
        return dialogue_intent.build_model_context(
            prior_requests,
            current_question=current_question,
            authority_context=authority_context,
            max_chars=4000,
            prefix=self._context_prefix(packet),
        )

    @staticmethod
    def _source_sequence(projection: Mapping[str, object]) -> object:
        case_projection = projection.get("case_projection")
        return (
            case_projection.get("source_sequence") if isinstance(case_projection, Mapping) else None
        )

    @staticmethod
    def _explicit_receipt_ids(question: str, current_receipt_ids: list[str]) -> list[str]:
        """Find complete current-source identifiers explicitly named by the user."""

        explicit: list[str] = []
        for receipt_id in current_receipt_ids:
            if not receipt_id or receipt_id in explicit:
                continue
            start = 0
            while True:
                index = question.find(receipt_id, start)
                if index < 0:
                    break
                before = question[index - 1] if index else ""
                after_index = index + len(receipt_id)
                after = question[after_index] if after_index < len(question) else ""

                def boundary(value: str) -> bool:
                    return not value or not (value.isalnum() or value in "_-")

                if boundary(before) and boundary(after):
                    explicit.append(receipt_id)
                    break
                start = index + len(receipt_id)
        return explicit

    def _attach_rejoined_reference_candidates(
        self,
        packet: dict[str, Any],
        *,
        projection: Mapping[str, object],
        context_state: Mapping[str, object],
        current_question: str,
    ) -> list[dict[str, Any]]:
        tool_payload = packet.get("tool_payload")
        if not isinstance(tool_payload, Mapping):
            raise ValueError("receiving packet lacks tool payload")
        sources = tool_payload.get("sources")
        if not isinstance(sources, dict):
            raise ValueError("receiving packet lacks mutable source payload")
        control_context = sources.get("read_control_context")
        evidence = sources.get("read_erp_evidence")
        if not isinstance(control_context, Mapping) or not isinstance(evidence, Mapping):
            raise ValueError("receiving packet lacks current source facts")
        relations = receipt_relations(evidence)
        # A receipt may have several stock-ledger rows under one admitted ERP
        # evidence record; that is normal fan-out, not two receipt candidates.
        # The same voucher under distinct evidence records remains duplicated
        # below so the rejoin helper reports ambiguity rather than choosing one.
        evidence_by_receipt: dict[str, set[str]] = {}
        for relation in relations:
            receipt_id = relation.get("receipt_id")
            evidence_id = relation.get("evidence_id")
            if (
                isinstance(receipt_id, str)
                and receipt_id
                and isinstance(evidence_id, str)
                and evidence_id
            ):
                evidence_by_receipt.setdefault(receipt_id, set()).add(evidence_id)
        current_receipt_ids = [
            receipt_id
            for receipt_id, evidence_ids in evidence_by_receipt.items()
            for _ in evidence_ids
        ]
        case_id = str(packet.get("case_id", ""))
        explicit_ids = self._explicit_receipt_ids(current_question, current_receipt_ids)
        explicit_ambiguities = [
            receipt_id for receipt_id in explicit_ids if current_receipt_ids.count(receipt_id) > 1
        ]
        if explicit_ids:
            candidates: dict[str, object] = {
                "status": "AMBIGUOUS" if explicit_ambiguities else "CURRENT_QUESTION",
                "case_id": case_id,
                "current_receipt_ids": explicit_ids,
                "ambiguous_receipt_ids": explicit_ambiguities,
                "authority": (
                    "Receipt identifiers explicitly named in the current user question take "
                    "precedence and must be re-read from current sources."
                ),
            }
        else:
            group = dialogue_intent.latest_reference_group(context_state, case_id=case_id)
            candidates = (
                dialogue_intent.rejoin_reference_group(
                    group,
                    case_id=case_id,
                    current_receipt_ids=current_receipt_ids,
                    source_sequence=self._source_sequence(projection),
                )
                if group is not None
                else {"status": "UNAVAILABLE", "case_id": case_id}
            )
        sources["read_control_context"] = {
            **control_context,
            "prior_reference_candidates": candidates,
        }
        return relations

    @staticmethod
    def _cited_receipt_ids(relations: list[dict[str, Any]], evidence_ids: object) -> list[str]:
        cited = set(evidence_ids) if isinstance(evidence_ids, (list, tuple, set)) else set()
        receipt_ids: list[str] = []
        for relation in relations:
            receipt_id = relation.get("receipt_id")
            if (
                isinstance(receipt_id, str)
                and receipt_id
                and (receipt_id in cited or relation.get("evidence_id") in cited)
                and receipt_id not in receipt_ids
            ):
                receipt_ids.append(receipt_id)
        return receipt_ids

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
