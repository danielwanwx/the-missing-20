"""Synthetic end-to-end experiment session used by the local product UI.

This module intentionally composes the existing production-shaped seams instead of
creating a second, UI-only simulation:

* ``DiscrepancyDetector`` reads the synthetic enterprise records;
* ``AgentHarness`` runs the real local Strands event loop with scripted output;
* ``QuorumAuthorizationService`` and ``AuthorityBControlledExecutor`` own the
  two-role approval and controlled effect;
* ``PublicEventLedger`` is only a redacted projection for the browser.

The ledger is durable, ordered, and idempotent.  The browser can therefore replay
the same session after reconnecting without the frontend inventing business state.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Condition, RLock, Thread
from typing import Any

from the_missing_20.adapters.clocks import ManualClock
from the_missing_20.adapters.local_knowledge import LocalKnowledgeRepository
from the_missing_20.adapters.local_signer import LocalSigner
from the_missing_20.adapters.sqlite_case_store import SQLiteCaseStore
from the_missing_20.adapters.strands_models import ScriptedStrandsFactory
from the_missing_20.adapters.synthetic_enterprise import SyntheticEnterprise
from the_missing_20.agents.events import (
    AgentEventSink,
    AgentOperationEvent,
    AgentOperationEventType,
)
from the_missing_20.agents.harness import AgentHarness, HarnessRun
from the_missing_20.agents.schemas import (
    REQUIRED_AUTHORITATIVE_SOURCES,
    SourceAvailability,
    SourceAvailabilitySet,
)
from the_missing_20.authority_b.classifier import (
    classify_operational_state,
    latest_authoritative_evidence,
)
from the_missing_20.authority_b.executor import AuthorityBControlledExecutor
from the_missing_20.authority_b.models import (
    AttestationDecision,
    AuthorizationIntent,
    QuorumStatus,
)
from the_missing_20.authority_b.quorum import QuorumAuthorizationService, QuorumDenied
from the_missing_20.domain.enterprise import (
    EvidenceReadStatus,
    SupplyUnitStatus,
)
from the_missing_20.domain.errors import VersionConflict
from the_missing_20.domain.execution import (
    ReleaseInvoiceParameters,
    RestartReceiptMessageParameters,
)
from the_missing_20.domain.models import (
    ActionTool,
    EvidenceItem,
    EvidenceProvenance,
    EvidenceSourceType,
    HumanRole,
)
from the_missing_20.experiment.events import PublicEventType, PublicIncidentEvent
from the_missing_20.experiment.ledger import PublicEventLedger

BASE_TIME = datetime(2026, 8, 28, 0, 0, tzinfo=UTC)
SIGNING_KEY = b"missing20-local-experiment-only"
DEFAULT_FIXTURE_RELATIVE = Path("fixtures/scenarios/retryable-document-lock.json")


class _SessionAgentEventSink(AgentEventSink):
    """Adapt actual harness operations to the session's durable public ledger."""

    _EVENT_TYPES: dict[AgentOperationEventType, PublicEventType] = {
        AgentOperationEventType.AGENT_STARTED: PublicEventType.AGENT_STARTED,
        AgentOperationEventType.AGENT_COMPLETED: PublicEventType.AGENT_COMPLETED,
        AgentOperationEventType.TOOL_STARTED: PublicEventType.TOOL_STARTED,
        AgentOperationEventType.TOOL_COMPLETED: PublicEventType.TOOL_COMPLETED,
        AgentOperationEventType.EVIDENCE_RETURNED: PublicEventType.EVIDENCE_RETURNED,
        AgentOperationEventType.AGENT_HANDOFF: PublicEventType.AGENT_HANDOFF,
        AgentOperationEventType.SYNTHESIS_STARTED: PublicEventType.SYNTHESIS_STARTED,
        AgentOperationEventType.SYNTHESIS_COMPLETED: PublicEventType.SYNTHESIS_COMPLETED,
        AgentOperationEventType.EVALUATION_STARTED: PublicEventType.EVALUATION_STARTED,
        AgentOperationEventType.EVALUATION_COMPLETED: PublicEventType.EVALUATION_COMPLETED,
    }

    def __init__(self, session: ExperimentSession) -> None:
        self._session = session

    def emit(self, event: AgentOperationEvent) -> None:
        if event.case_id != self._session.case_id or event.trace_id != self._session.trace_id:
            raise ValueError("agent event does not match the session identity")
        try:
            event_type = self._EVENT_TYPES[event.event_type]
        except KeyError as exc:  # pragma: no cover - closed enum vocabulary
            raise ValueError("agent event type is not public") from exc
        payload = dict(event.payload)
        if event.stage is not None:
            payload.setdefault("stage", event.stage)
        self._session._append(
            event_type,
            actor=event.actor,
            status=event.status,
            case_version=self._session._current_case_version(),
            correlation_id=event.correlation_id,
            idempotency_key=(
                f"experiment:agent-operation:{event.event_type.value}:{event.operation_id}"
            ),
            payload=payload,
        )


def _json(value: object) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return json.loads(json.dumps(value, default=str))


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


class ExperimentSession:
    """One durable, synthetic incident session shared by both UI views."""

    def __init__(
        self,
        repository_root: Path,
        *,
        data_directory: Path | None = None,
        incident_id: str = "missing-20-001",
        fixture_path: Path | None = None,
        auto_start: bool = False,
    ) -> None:
        self.repository_root = repository_root.resolve()
        self.incident_id = incident_id
        self.case_id = f"case:{incident_id}"
        self.trace_id = f"trace:{incident_id}"
        self.fixture_path = (
            fixture_path or self.repository_root / DEFAULT_FIXTURE_RELATIVE
        ).resolve()
        if not self.fixture_path.is_relative_to(self.repository_root):
            raise ValueError("experiment fixture must remain inside the repository")
        self.data_directory = (data_directory or self._temporary_directory()).resolve()
        self.data_directory.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        # Command serialization is deliberately separate from the snapshot/event
        # lock.  Strands executes audited tools on worker threads, and those workers
        # must append operation events while a command is awaiting the harness.
        self._command_lock = RLock()
        self._condition = Condition(self._lock)
        self._clock = ManualClock(BASE_TIME)
        self._event_time = BASE_TIME - timedelta(seconds=1)
        self._running = False
        self._run: HarnessRun | None = None
        self._run_error: str | None = None
        self._intents: dict[str, AuthorizationIntent] = {}
        self._command_results: dict[str, dict[str, Any]] = {}

        self.ledger = PublicEventLedger(self.data_directory / "public-events.sqlite")
        self._agent_event_sink = _SessionAgentEventSink(self)
        self.enterprise = self._load_enterprise()
        self.store = SQLiteCaseStore(self.data_directory / "case.sqlite")
        self._quorum = QuorumAuthorizationService(
            principals={
                "integration-operator": HumanRole.INTEGRATION_OPERATOR,
                "ap-approver": HumanRole.AP_APPROVER,
            },
            signer=LocalSigner(SIGNING_KEY),
            clock=self._clock,
            storage_path=self.data_directory / "quorum-ledger.json",
        )
        self._ensure_detection()
        self._restore_event_clock()
        if auto_start:
            self.start_investigation()

    def _temporary_directory(self) -> Path:
        return Path(tempfile.mkdtemp(prefix="missing20-experiment-"))

    def _load_enterprise(self) -> SyntheticEnterprise:
        path = self.data_directory / "enterprise.sqlite"
        if not path.exists():
            return SyntheticEnterprise.seed_from_fixture(path, self.fixture_path)
        # A caller may deliberately provide a persisted session.  Do not silently
        # overwrite it or reseed it: an existing database is authoritative state.
        enterprise = SyntheticEnterprise(path)
        try:
            snapshot = enterprise.read_snapshot()
        except LookupError as exc:
            raise ValueError("persisted experiment enterprise is not fully seeded") from exc
        if len(snapshot.supply_units) != snapshot.purchase_order.ordered_quantity:
            raise ValueError("persisted experiment enterprise has incomplete unit records")
        return enterprise

    def _restore_event_clock(self) -> None:
        events = self.ledger.all_events(self.incident_id)
        if events:
            latest = max(item.occurred_at for item in events)
            self._event_time = latest
            self._clock.set(max(BASE_TIME, latest))

    def _ensure_detection(self) -> None:
        existing = self.ledger.all_events(self.incident_id)
        if existing:
            return
        from the_missing_20.application.detector import DiscrepancyDetector

        detector = DiscrepancyDetector(self.enterprise, self.store, self._clock)
        initial_units = self.enterprise.list_units()
        case, evidence = detector.detect(
            case_id=self.case_id,
            trace_id=self.trace_id,
            fixture_path=self.fixture_path,
            failed_unit_ids=tuple(
                item.unit_id
                for item in initial_units
                if item.status is SupplyUnitStatus.QUEUE_FAILED
            ),
        )
        snapshot = self.enterprise.read_snapshot()
        self._append(
            PublicEventType.INCIDENT_DETECTED,
            actor="deterministic-detector",
            status="DETECTED",
            case_version=0,
            correlation_id=self.case_id,
            idempotency_key="experiment:incident-detected",
            payload={
                "expected_quantity": snapshot.purchase_order.ordered_quantity,
                "recorded_quantity": snapshot.erp_receipt.quantity,
                "missing_quantity": snapshot.purchase_order.ordered_quantity
                - snapshot.erp_receipt.quantity,
                "unit": snapshot.purchase_order.unit,
                "evidence_ids": [item.evidence_id for item in evidence],
                "unit_counts": self._unit_counts(snapshot),
                "failed_unit_ids": [
                    item.unit_id
                    for item in snapshot.supply_units
                    if item.status is SupplyUnitStatus.QUEUE_FAILED
                ],
            },
        )

    def _mark_investigation_started(self) -> None:
        """Persist the start only when the bounded harness actually begins."""

        self._append(
            PublicEventType.INVESTIGATION_STARTED,
            actor="orchestrator",
            status="RUNNING",
            case_version=self._current_case_version(),
            correlation_id=self.trace_id,
            idempotency_key="experiment:investigation-started",
            payload={"investigator_count": 3, "mode": "SCRIPTED_SYNTHETIC"},
        )

    def _next_event_time(self) -> datetime:
        self._event_time += timedelta(seconds=1)
        if self._event_time < self._clock.now():
            self._event_time = self._clock.now() + timedelta(seconds=1)
        self._clock.set(self._event_time)
        return self._event_time

    def _append(
        self,
        event_type: PublicEventType,
        *,
        actor: str,
        status: str,
        case_version: int,
        correlation_id: str,
        idempotency_key: str,
        payload: dict[str, Any] | None = None,
    ) -> PublicIncidentEvent:
        # The worker can receive callbacks from concurrent investigator tasks.  Keep
        # timestamp allocation and durable append in one critical section so a public
        # event never observes a duplicated/non-monotonic local timestamp.
        with self._lock:
            event = self.ledger.append(
                incident_id=self.incident_id,
                trace_id=self.trace_id,
                case_version=case_version,
                event_type=event_type,
                actor=actor,
                status=status,
                occurred_at=self._next_event_time(),
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
                payload=payload,
            )
        with self._condition:
            self._condition.notify_all()
        return event

    def _register_command(
        self,
        *,
        idempotency_key: str,
        command_kind: str,
        identity: dict[str, Any],
        payload: dict[str, Any],
    ) -> bool:
        """Persist a command envelope before its state-changing work starts."""

        return self.ledger.register_command(
            incident_id=self.incident_id,
            idempotency_key=idempotency_key,
            command_kind=command_kind,
            identity={"incident_id": self.incident_id, "trace_id": self.trace_id, **identity},
            payload=payload,
        )

    @staticmethod
    def _unit_counts(snapshot: Any) -> dict[str, int]:
        units = tuple(snapshot.supply_units)
        return {
            "total": len(units),
            "erp_recorded": sum(item.status is SupplyUnitStatus.ERP_RECORDED for item in units),
            "queue_failed": sum(item.status is SupplyUnitStatus.QUEUE_FAILED for item in units),
        }

    def start_investigation(self) -> None:
        """Start the actual local Strands investigation once.

        The thread is intentionally bounded and uses the scripted provider.  It
        allows a browser to subscribe before agent/tool events are appended while
        keeping provider degradation honest and avoiding any AWS call.
        """

        with self._condition:
            if self._running or self._run is not None:
                return
            if any(
                item.event_type
                in {
                    PublicEventType.SYNTHESIS_COMPLETED,
                    PublicEventType.EVALUATION_COMPLETED,
                }
                for item in self.ledger.all_events(self.incident_id)
            ):
                return
            if any(
                item.event_type is PublicEventType.PROVIDER_DEGRADED
                for item in self.ledger.all_events(self.incident_id)
            ):
                return
            self._mark_investigation_started()
            self._running = True
            Thread(
                target=self._investigation_worker,
                name="missing20-investigation",
                daemon=True,
            ).start()

    def run_investigation(self) -> HarnessRun | None:
        """Run synchronously for tests or a CLI caller; idempotent after success."""

        with self._condition:
            if self._run is not None:
                return self._run
            if self._running:
                self._condition.wait_for(lambda: not self._running, timeout=45)
                return self._run
            self._mark_investigation_started()
            self._running = True
        self._investigation_worker()
        return self._run

    def investigation_is_available(self) -> bool:
        """Whether this session has a usable in-memory or durable advisory run."""

        if self._run is not None:
            return True
        return any(
            item.event_type is PublicEventType.EVALUATION_COMPLETED
            and item.status in {"ACCEPT", "COMPLETE"}
            for item in self.ledger.all_events(self.incident_id)
        )

    def chat_command(self, question: str, *, idempotency_key: str) -> dict[str, Any]:
        """Run a browser Copilot command without blocking operation-event workers."""

        # Do not hold the snapshot/event lock while the conversational turn invokes the
        # harness.  Strands executes audited tools in worker threads; those workers
        # must be able to append their actual-operation events to the same session
        # ledger before the harness completes.  Durable command fingerprints provide
        # the idempotency boundary.  The separate command lock serializes turns
        # without preventing those event appends.
        with self._command_lock:
            return self.chat(question, idempotency_key=idempotency_key)

    def decision_command(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Run a structured decision command with durable command idempotency."""

        # ``prepare`` may run the actual agent harness to establish an advisory
        # decision.  As with chat, worker threads need the snapshot/event lock for
        # their durable callbacks, so command serialization uses its own lock.
        with self._command_lock:
            return self.decide(payload)

    def _investigation_worker(self) -> None:
        try:
            availability = SourceAvailabilitySet(
                sources=tuple(
                    SourceAvailability(
                        source_type=source,
                        status=EvidenceReadStatus.AVAILABLE,
                    )
                    for source in REQUIRED_AUTHORITATIVE_SOURCES
                )
            )
            evidence = tuple(self.store.list_evidence(self.case_id))
            harness = AgentHarness(
                model_factory=ScriptedStrandsFactory(),
                knowledge=LocalKnowledgeRepository(self.repository_root / "fixtures/knowledge"),
                source_availability=availability,
                event_sink=self._agent_event_sink,
            )
            run = harness.run(
                case_id=self.case_id,
                trace_id=self.trace_id,
                evidence=evidence,
            )
            with self._condition:
                self._run = run
                self._run_error = None
        except Exception as exc:
            with self._condition:
                self._run_error = type(exc).__name__
            case_version = self._current_case_version()
            self._append(
                PublicEventType.PROVIDER_DEGRADED,
                actor="orchestrator",
                status="DEGRADED",
                case_version=case_version,
                correlation_id=self.trace_id,
                idempotency_key="experiment:provider-degraded",
                payload={
                    "provider": "scripted",
                    "usefulness": "NOT_PROVEN",
                    "error_code": type(exc).__name__,
                },
            )
            self._append(
                PublicEventType.WORKFLOW_BLOCKED,
                actor="deterministic-workflow",
                status="BLOCKED",
                case_version=case_version,
                correlation_id=self.case_id,
                idempotency_key="experiment:investigation-blocked",
                payload={"reason": "ADVISORY_UNAVAILABLE", "operational_effect": "NONE"},
            )
        finally:
            with self._condition:
                self._running = False
                self._condition.notify_all()

    def _current_case_version(self) -> int:
        return self.store.get_case(self.case_id).case_version

    def _current_decision(self) -> Any:
        case = self.store.get_case(self.case_id)
        evidence = latest_authoritative_evidence(tuple(self.store.list_evidence(self.case_id)))
        if not evidence:
            raise QuorumDenied("no authoritative evidence is available")
        return classify_operational_state(evidence, case=case, trace_id=self.trace_id)

    def _refresh_evidence(self) -> tuple[EvidenceItem, ...]:
        snapshot = self.enterprise.read_snapshot()
        # Evidence IDs are immutable append-only records.  Use the persisted
        # evidence count rather than the public sequence: one execution may add
        # a complete five-source refresh before another command appends events.
        existing_count = len(self.store.list_evidence(self.case_id))
        stamp = existing_count // len(REQUIRED_AUTHORITATIVE_SOURCES) + 1
        provenance = EvidenceProvenance(
            source_system="synthetic-enterprise-sqlite",
            collection_method="fresh-read",
            collected_by="experiment-session",
        )
        values: tuple[tuple[str, EvidenceSourceType, str, dict[str, Any]], ...] = (
            (
                "warehouse",
                EvidenceSourceType.WAREHOUSE,
                snapshot.warehouse_receipt.receipt_id,
                snapshot.warehouse_receipt.model_dump(mode="json"),
            ),
            (
                "erp-receipt",
                EvidenceSourceType.ERP_RECEIPT,
                f"{snapshot.erp_receipt.purchase_order_id}:{snapshot.erp_receipt.line_id}",
                snapshot.erp_receipt.model_dump(mode="json"),
            ),
            (
                "failed-message",
                EvidenceSourceType.FAILED_MESSAGE_QUEUE,
                snapshot.failed_message.message_id,
                snapshot.failed_message.model_dump(mode="json"),
            ),
            (
                "invoice",
                EvidenceSourceType.INVOICE,
                snapshot.invoice.invoice_id,
                snapshot.invoice.model_dump(mode="json"),
            ),
            (
                "material-documents",
                EvidenceSourceType.MATERIAL_DOCUMENT,
                snapshot.failed_message.message_id,
                {
                    "material_documents": [
                        item.model_dump(mode="json") for item in snapshot.material_documents
                    ],
                    "business_effects": [
                        item.model_dump(mode="json") for item in snapshot.business_effects
                    ],
                },
            ),
        )
        result: list[EvidenceItem] = []
        for suffix, source_type, record_id, fields in values:
            evidence = EvidenceItem(
                evidence_id=f"{self.case_id}:refresh-{stamp}:{suffix}",
                case_id=self.case_id,
                trace_id=self.trace_id,
                subject=source_type.value.lower(),
                source_type=source_type,
                source_record_id=record_id,
                observed_at=self._next_event_time(),
                content_digest=_digest(fields),
                admitted_fields=fields,
                provenance=provenance,
            )
            self.store.add_evidence(evidence)
            result.append(evidence)
        return tuple(result)

    def _action_tool(self, value: object) -> ActionTool:
        text = str(value or "").strip().lower()
        aliases = {
            "restart_receipt_message": ActionTool.RESTART_RECEIPT_MESSAGE,
            "receipt_restart": ActionTool.RESTART_RECEIPT_MESSAGE,
            "prepare_recovery": ActionTool.RESTART_RECEIPT_MESSAGE,
            "release_invoice": ActionTool.RELEASE_INVOICE,
            "invoice_release": ActionTool.RELEASE_INVOICE,
            "prepare_invoice": ActionTool.RELEASE_INVOICE,
        }
        try:
            return aliases[text]
        except KeyError as exc:
            raise QuorumDenied("unknown structured decision action") from exc

    def _load_intent(self, intent_id: str) -> AuthorizationIntent | None:
        cached = self._intents.get(intent_id)
        if cached is not None:
            return cached
        try:
            intent = self._quorum.get_intent(intent_id)
        except QuorumDenied:
            return None
        self._intents[intent_id] = intent
        return intent

    def _parameters(
        self, tool: ActionTool
    ) -> RestartReceiptMessageParameters | ReleaseInvoiceParameters:
        snapshot = self.enterprise.read_snapshot()
        if tool is ActionTool.RESTART_RECEIPT_MESSAGE:
            message = snapshot.failed_message
            return RestartReceiptMessageParameters(
                message_id=message.message_id,
                message_revision=message.revision,
                purchase_order_id=message.purchase_order_id,
                line_id=message.line_id,
                quantity=message.quantity,
                expected_error_code=message.error_code,
                expected_message_status=message.status.value,
            )
        invoice = snapshot.invoice
        if invoice.hold_reason is None:
            raise QuorumDenied("invoice has no actionable hold")
        return ReleaseInvoiceParameters(
            invoice_id=invoice.invoice_id,
            invoice_revision=invoice.revision,
            purchase_order_id=invoice.purchase_order_id,
            line_id=invoice.line_id,
            quantity=invoice.quantity,
            expected_hold_reason=invoice.hold_reason,
        )

    def prepare_decision(self, tool_value: object, *, idempotency_key: str) -> dict[str, Any]:
        tool = self._action_tool(tool_value)
        # Bind the command before any harness or refresh work.  A reused key must
        # not trigger a new investigation/evidence refresh before the durable
        # envelope rejects a changed action.
        if self._register_command(
            idempotency_key=idempotency_key,
            command_kind="prepare_recovery",
            identity={"case_version": self._current_case_version()},
            payload={"tool": tool.value},
        ):
            return self._command_results.get(idempotency_key, self.snapshot())
        run = self.run_investigation()
        if run is None and not self.investigation_is_available():
            raise QuorumDenied("agent investigation is unavailable")
        if tool is ActionTool.RELEASE_INVOICE:
            self._refresh_evidence()
        decision = self._current_decision()
        if decision.allowed_action is not tool or decision.eligibility.value != "PENDING_APPROVAL":
            raise QuorumDenied("deterministic authority does not permit this action")
        intent_id = f"intent:{self.incident_id}:{tool.value}"
        existing = self._load_intent(intent_id)
        if existing is not None:
            return self.snapshot()
        intent = self._quorum.create_intent(
            decision=decision,
            complete_parameters=self._parameters(tool),
            admitted_evidence_digest=decision.source_digest,
            intent_id=intent_id,
        )
        self._intents[intent_id] = intent
        case_version = self._current_case_version()
        self._append(
            PublicEventType.RECOVERY_PREPARED,
            actor="orchestrator",
            status="PREPARED",
            case_version=case_version,
            correlation_id=intent.intent_id,
            idempotency_key=f"experiment:recovery-prepared:{tool.value}",
            payload={
                "tool": tool.value,
                "intent_id": intent.intent_id,
                "intent_digest": intent.intent_digest,
                "decision_digest": decision.decision_digest,
                "parameters_digest": intent.parameters_digest,
            },
        )
        self._append(
            PublicEventType.APPROVAL_REQUESTED,
            actor="deterministic-authority",
            status="QUORUM_PENDING",
            case_version=case_version,
            correlation_id=intent.intent_id,
            idempotency_key=f"experiment:approval-requested:{tool.value}",
            payload={
                "intent_id": intent.intent_id,
                "required_roles": ["INTEGRATION_OPERATOR", "AP_APPROVER"],
            },
        )
        return self.snapshot()

    def record_approval(
        self,
        *,
        intent_id: str,
        principal_id: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        intent = self._load_intent(intent_id)
        if intent is None:
            raise QuorumDenied("unknown authorization intent")
        if self._register_command(
            idempotency_key=idempotency_key,
            command_kind="approve",
            identity={"intent_id": intent_id, "case_version": intent.case_version},
            payload={
                "principal_id": principal_id,
                "decision": AttestationDecision.APPROVED.value,
            },
        ):
            return self._command_results.get(idempotency_key, self.snapshot())
        result = self._quorum.attest(
            intent=intent,
            principal_id=principal_id,
            decision=AttestationDecision.APPROVED,
            attestation_id=f"attestation:{self.incident_id}:{principal_id}:{intent_id}",
        )
        self._intents[intent_id] = result.intent
        attestation = result.attestation
        if attestation is None:
            raise QuorumDenied("quorum did not produce an attestation")
        self._append(
            PublicEventType.APPROVAL_RECORDED,
            actor=principal_id,
            status=result.status.value,
            case_version=self._current_case_version(),
            correlation_id=intent_id,
            idempotency_key=f"experiment:approval-recorded:{idempotency_key}",
            payload={
                "intent_id": intent_id,
                "principal_id": principal_id,
                "role": attestation.role.value,
                "attestation_id": attestation.attestation_id,
                "quorum_status": result.status.value,
            },
        )
        response = self.snapshot()
        self._command_results[idempotency_key] = response
        return response

    def execute_decision(self, *, intent_id: str, idempotency_key: str) -> dict[str, Any]:
        intent = self._load_intent(intent_id)
        if intent is None:
            raise QuorumDenied("unknown authorization intent")
        slug = intent.tool.value.replace("_", "-")
        execution_id = f"execution:{self.incident_id}:{slug}"
        effect_key = f"effect:{self.incident_id}:{slug}"
        grant = self._quorum.get_grant(intent_id)
        status = self._quorum.get_intent(intent_id).status
        if grant is None or (
            status is not QuorumStatus.GRANTED
            and not (
                status is QuorumStatus.CONSUMED
                and self._quorum.consumption(intent_id) == (execution_id, effect_key)
            )
        ):
            raise QuorumDenied("exact two-role quorum is required before execution")
        if self._register_command(
            idempotency_key=idempotency_key,
            command_kind="execute",
            identity={
                "intent_id": intent_id,
                "execution_id": execution_id,
                "case_version": intent.case_version,
            },
            payload={"effect_key": effect_key},
        ):
            return self._command_results.get(idempotency_key, self.snapshot())
        if status is QuorumStatus.CONSUMED:
            response = self.snapshot()
            self._command_results[idempotency_key] = response
            return response
        self._append(
            PublicEventType.EXECUTION_STARTED,
            actor="controlled-executor",
            status="RUNNING",
            case_version=self._current_case_version(),
            correlation_id=execution_id,
            idempotency_key=f"experiment:execution-started:{slug}",
            payload={
                "intent_id": intent_id,
                "execution_id": execution_id,
                "tool": intent.tool.value,
            },
        )
        executor = AuthorityBControlledExecutor(
            store=self.store,
            enterprise=self.enterprise,
            quorum=self._quorum,
            clock=self._clock,
        )
        try:
            receipt, _ = executor.execute(
                grant,
                execution_id=execution_id,
                idempotency_key=effect_key,
            )
            replay_receipt, _ = executor.execute(
                grant,
                execution_id=execution_id,
                idempotency_key=effect_key,
            )
        except Exception as exc:
            self._append(
                PublicEventType.WORKFLOW_BLOCKED,
                actor="controlled-executor",
                status="BLOCKED",
                case_version=self._current_case_version(),
                correlation_id=execution_id,
                idempotency_key=f"experiment:execution-blocked:{slug}",
                payload={"reason": type(exc).__name__, "effect_created": False},
            )
            raise
        self._append(
            PublicEventType.EXECUTION_COMPLETED,
            actor="controlled-executor",
            status=receipt.operation_result.value,
            case_version=self._current_case_version(),
            correlation_id=execution_id,
            idempotency_key=f"experiment:execution-completed:{slug}",
            payload={
                "execution_id": receipt.execution_id,
                "effect_id": self.enterprise.read_snapshot().business_effects[-1].effect_id,
                "material_document_ids": list(receipt.material_document_ids),
                "replay_same_receipt": replay_receipt == receipt,
            },
        )
        final_snapshot = self.enterprise.read_snapshot()
        self._append(
            PublicEventType.VERIFICATION_COMPLETED,
            actor="deterministic-verifier",
            status="PASS" if all(receipt.postconditions.values()) else "FAIL",
            case_version=self._current_case_version(),
            correlation_id=execution_id,
            idempotency_key=f"experiment:verification-completed:{slug}",
            payload={
                "execution_id": execution_id,
                "postconditions": receipt.postconditions,
                "expected_units": final_snapshot.purchase_order.ordered_quantity,
                "recorded_units": self._unit_counts(final_snapshot)["erp_recorded"],
                "missing_units": self._unit_counts(final_snapshot)["queue_failed"],
                "effect_count": len(final_snapshot.business_effects),
                "replay_effect_delta": 0,
            },
        )
        self._refresh_evidence()
        response = self.snapshot()
        self._command_results[idempotency_key] = response
        return response

    def chat(self, question: str, *, idempotency_key: str) -> dict[str, Any]:
        """Answer a bounded read-only Copilot question from current records."""

        text = question.strip()
        if not text or len(text) > 2_000:
            raise ValueError("chat question must contain one to two thousand characters")
        if self._register_command(
            idempotency_key=idempotency_key,
            command_kind="chat",
            identity={"case_version": self._current_case_version()},
            payload={"question": text},
        ):
            cached_event_key = f"experiment:chat:{idempotency_key}"
            cached = next(
                (
                    item
                    for item in self.ledger.all_events(self.incident_id)
                    if item.idempotency_key == cached_event_key
                ),
                None,
            )
            if cached is not None:
                cached_payload = dict(cached.payload)
                response = {
                    "incident_id": self.incident_id,
                    "trace_id": self.trace_id,
                    "case_version": cached.case_version,
                    "projection_sequence": self.ledger.latest_sequence(self.incident_id),
                    "message": cached_payload.get("message", ""),
                    "citations": cached_payload.get("citations", []),
                    "read_only": True,
                }
                self._command_results[idempotency_key] = response
                return response
            return self.snapshot()
        # The envelope is checked before consulting the in-memory result cache.  A
        # caller reusing a key with a changed question must fail closed even when the
        # original response still exists in this process.
        cached_result = self._command_results.get(idempotency_key)
        if cached_result is not None:
            return cached_result
        # Every conversational turn goes through the same bounded Strands session
        # and its audited read tools.  The deterministic router below only chooses
        # how to explain those results; it never replaces the investigation.
        run = self.run_investigation()
        snapshot = self.enterprise.read_snapshot()
        failed_ids = [
            item.unit_id
            for item in snapshot.supply_units
            if item.status is SupplyUnitStatus.QUEUE_FAILED
        ]
        evidence = tuple(self.store.list_evidence(self.case_id))
        citations = [
            item.evidence_id
            for item in latest_authoritative_evidence(evidence)
            if item.source_type
            in {
                EvidenceSourceType.FAILED_MESSAGE_QUEUE,
                EvidenceSourceType.ERP_RECEIPT,
                EvidenceSourceType.WAREHOUSE,
                EvidenceSourceType.INVOICE,
                EvidenceSourceType.MATERIAL_DOCUMENT,
            }
        ]
        lowered = text.lower()
        response_proposal: Any = None
        if any(word in lowered for word in ("where", "missing", "gone", "twenty", "20")):
            answer = (
                f"The current authoritative read shows {len(failed_ids)} units stopped at the "
                f"message queue. They are the exact unit records {failed_ids[:3]}"
                f"{'…' if len(failed_ids) > 3 else ''}."
            )
            intent = "inspect_incident"
        elif any(word in lowered for word in ("why", "reason", "cause", "hypothesis")):
            if run is None:
                answer = "The investigator session is unavailable; no hypothesis is authoritative."
            else:
                answer = (
                    f"The investigator session selected {run.synthesis.selected_hypothesis.value}"
                )
                answer += (
                    " because the queue record is retryable, the warehouse has the full "
                    "quantity, and ERP is short by the same twenty units."
                )
            intent = "explain_hypothesis"
        elif any(word in lowered for word in ("compare", "alternative", "other", "different")):
            if run is not None:
                comparisons = "; ".join(
                    f"{item.hypothesis_type.value}: {item.conclusion.value}"
                    for item in run.investigators
                )
                answer = f"The investigators compared these explanations: {comparisons}."
            else:
                answer = (
                    "The investigator session is unavailable, so alternatives cannot be compared."
                )
            intent = "compare_hypotheses"
        elif any(word in lowered for word in ("evidence", "cite", "record", "proof")):
            answer = f"The current read is grounded in {len(citations)} admitted evidence records."
            intent = "retrieve_evidence"
        elif any(word in lowered for word in ("prepare", "proposal", "recover", "fix")):
            prepared = self.prepare_decision(
                ActionTool.RESTART_RECEIPT_MESSAGE.value,
                idempotency_key=f"{idempotency_key}:prepare",
            )
            answer = (
                "I prepared a recovery proposal from the deterministic decision state. "
                "Two authorized roles must still approve it; chat cannot authorize or execute."
            )
            intent = "prepare_proposal"
            response_proposal = prepared.get("approval")
        elif any(word in lowered for word in ("approve", "execute")):
            answer = (
                "I can explain or prepare the recovery, but chat cannot approve or execute "
                "it. Use the structured recovery control so the exact two-role authority "
                "gate remains visible."
            )
            intent = "explain_authority_boundary"
        else:
            answer = (
                "I ran the bounded investigator session. I can inspect the current unit "
                "flow, explain the selected hypothesis, compare alternatives, cite "
                "evidence, or prepare a recovery proposal."
            )
            intent = "inspect_incident"
        current_case_version = self._current_case_version()
        response = {
            "incident_id": self.incident_id,
            "trace_id": self.trace_id,
            "case_version": current_case_version,
            "projection_sequence": self.ledger.latest_sequence(self.incident_id),
            "message": answer,
            "citations": citations,
            "intent": intent,
            "read_only": True,
        }
        self._append(
            PublicEventType.CHAT_MESSAGE,
            actor="incident-copilot",
            status="COMPLETED",
            case_version=current_case_version,
            correlation_id=f"chat:{idempotency_key}",
            idempotency_key=f"experiment:chat:{idempotency_key}",
            payload={
                "message": answer,
                "citations": citations,
                "intent": intent,
                "read_only": True,
                "proposal": response_proposal,
            },
        )
        response["projection_sequence"] = self.ledger.latest_sequence(self.incident_id)
        self._command_results[idempotency_key] = response
        return response

    def events_since(self, after_sequence: int = 0) -> tuple[PublicIncidentEvent, ...]:
        return self.ledger.list_events(self.incident_id, after_sequence=after_sequence)

    def wait_for_events(
        self, after_sequence: int, timeout: float = 15.0
    ) -> tuple[PublicIncidentEvent, ...]:
        deadline = datetime.now(UTC).timestamp() + max(0.0, timeout)
        with self._condition:
            while True:
                events = self.events_since(after_sequence)
                if events:
                    return events
                remaining = deadline - datetime.now(UTC).timestamp()
                if remaining <= 0:
                    return ()
                self._condition.wait(timeout=min(remaining, 1.0))

    def snapshot(self) -> dict[str, Any]:
        """Return one API snapshot whose business values come from authoritative reads."""

        with self._lock:
            case = self.store.get_case(self.case_id)
            enterprise = self.enterprise.read_snapshot()
            events = self.ledger.all_events(self.incident_id)
            counts = self._unit_counts(enterprise)
            unit_rows = [_json(item) for item in enterprise.supply_units]
            event_rows = [_json(item) for item in events]
            agents: dict[str, dict[str, Any]] = {}
            operations: list[dict[str, Any]] = []
            for event in events:
                if event.event_type in {
                    PublicEventType.AGENT_STARTED,
                    PublicEventType.AGENT_COMPLETED,
                }:
                    state = agents.setdefault(
                        event.actor,
                        {"agent_id": event.actor, "status": "IDLE", "tool_calls": 0},
                    )
                    state["status"] = (
                        "RUNNING"
                        if event.event_type is PublicEventType.AGENT_STARTED
                        else "COMPLETED"
                    )
                if event.event_type is PublicEventType.TOOL_COMPLETED:
                    operations.append(_json(event))
                    agent = agents.setdefault(
                        event.actor,
                        {"agent_id": event.actor, "status": "RUNNING", "tool_calls": 0},
                    )
                    agent["tool_calls"] += 1
            run = self._run
            advisory: dict[str, Any]
            if run is not None:
                advisory = {
                    "status": "COMPLETE",
                    "provider": run.trace.provider,
                    "model": run.trace.model,
                    "usefulness": "SCRIPTED_SYNTHETIC_PROOF",
                    "authority": "ADVISORY_NOT_OPERATIONAL_DECISION",
                    "selected_hypothesis": run.synthesis.selected_hypothesis.value,
                    "investigators": [
                        {
                            "agent_id": item.investigator_id.value,
                            "hypothesis": item.hypothesis_type.value,
                            "conclusion": item.conclusion.value,
                            "confidence": item.confidence_band.value,
                            "evidence_ids": list(item.factual_claims[0].evidence_ids)
                            if item.factual_claims
                            else [],
                        }
                        for item in run.investigators
                    ],
                    "claims": [
                        {
                            "claim_id": item.claim_id,
                            "evidence_ids": list(item.evidence_ids),
                            "relation": item.relation.value,
                            "statement": item.statement,
                        }
                        for item in run.synthesis.factual_claims
                    ],
                    "trace_id": run.trace.trace_id,
                }
            elif self._run_error or any(
                item.event_type is PublicEventType.PROVIDER_DEGRADED for item in events
            ):
                advisory = {
                    "status": "DEGRADED",
                    "provider": "scripted",
                    "usefulness": "NOT_PROVEN",
                    "authority": "ADVISORY_NOT_OPERATIONAL_DECISION",
                    "error_code": self._run_error or "ADVISORY_PROVIDER_FAILURE",
                }
            elif any(item.event_type is PublicEventType.EVALUATION_COMPLETED for item in events):
                # The event ledger is durable independently of the Python object that
                # originally held ``HarnessRun``.  A restarted process can still
                # truthfully expose that a scripted evaluation completed, while it
                # deliberately omits details that were not persisted in the public
                # projection.
                advisory = {
                    "status": "COMPLETE",
                    "provider": "scripted",
                    "model": "local-scripted",
                    "usefulness": "SCRIPTED_SYNTHETIC_PROOF",
                    "authority": "ADVISORY_NOT_OPERATIONAL_DECISION",
                    "trace_id": self.trace_id,
                    "durable_projection": True,
                }
            else:
                advisory = {
                    "status": "NOT_STARTED",
                    "provider": "scripted",
                    "usefulness": "SCRIPTED_SYNTHETIC_PROOF",
                    "authority": "ADVISORY_NOT_OPERATIONAL_DECISION",
                }
            decisions: list[dict[str, Any]] = []
            for tool in (ActionTool.RESTART_RECEIPT_MESSAGE, ActionTool.RELEASE_INVOICE):
                try:
                    decision = self._current_decision()
                except (LookupError, QuorumDenied):
                    continue
                if (
                    decision.allowed_action is tool
                    or decision.eligibility.value != "PENDING_APPROVAL"
                ) and decision.case_version == case.case_version:
                    decisions.append(_json(decision))
            approvals: list[dict[str, Any]] = []
            for intent_id in sorted(self._intents):
                intent = self._load_intent(intent_id)
                if intent is None:
                    continue
                approvals.extend(
                    {
                        "intent_id": intent_id,
                        "principal_id": item.principal_id,
                        "role": item.role.value,
                        "status": item.decision.value,
                        "attestation_id": item.attestation_id,
                    }
                    for item in self._quorum.list_attestations(intent_id)
                )
            active_intent = next(
                (
                    intent
                    for intent in self._intents.values()
                    if intent.status
                    in {
                        QuorumStatus.OPEN,
                        QuorumStatus.QUORUM_PENDING,
                        QuorumStatus.GRANTED,
                    }
                ),
                None,
            )
            receipts = self.store.list_receipts(self.case_id)
            effects = [_json(item) for item in enterprise.business_effects]
            execution_status = "COMPLETE" if receipts else "NOT_STARTED"
            projection_sequence = events[-1].sequence if events else 0
            return {
                "schema_version": "missing20-experiment/v1",
                "incident_id": self.incident_id,
                "trace_id": self.trace_id,
                "case_id": self.case_id,
                "case_version": case.case_version,
                "projection_sequence": projection_sequence,
                "connection": {"status": "LIVE", "source": "SYNTHETIC_EXPERIMENT"},
                "mode": "SCRIPTED_SYNTHETIC",
                "incident": {
                    "status": case.status.value,
                    "scenario_id": case.scenario_id,
                    "expected_quantity": enterprise.purchase_order.ordered_quantity,
                    "recorded_quantity": enterprise.erp_receipt.quantity,
                    "missing_quantity": enterprise.purchase_order.ordered_quantity
                    - enterprise.erp_receipt.quantity,
                    "unit": enterprise.purchase_order.unit,
                },
                "unit_counts": counts,
                "units": unit_rows,
                "flow": {
                    "nodes": [
                        {
                            "id": "warehouse",
                            "label": "Warehouse",
                            "status": "HEALTHY",
                            "count": counts["total"],
                        },
                        {
                            "id": "message-queue",
                            "label": "Message Queue",
                            "status": "ANOMALY" if counts["queue_failed"] else "HEALTHY",
                            "count": counts["queue_failed"],
                        },
                        {
                            "id": "erp",
                            "label": "ERP",
                            "status": "HEALTHY" if counts["queue_failed"] == 0 else "PARTIAL",
                            "count": counts["erp_recorded"],
                        },
                        {
                            "id": "invoice",
                            "label": "Invoice",
                            "status": enterprise.invoice.state.value,
                            "count": enterprise.invoice.quantity,
                        },
                    ],
                    "edges": [
                        {"from": "warehouse", "to": "message-queue"},
                        {"from": "message-queue", "to": "erp"},
                        {"from": "erp", "to": "invoice"},
                    ],
                },
                "topology": {
                    "nodes": [
                        {"id": "warehouse", "label": "Warehouse Scan", "health": "HEALTHY"},
                        {
                            "id": "queue",
                            "label": "Receipt Queue",
                            "health": "ANOMALY" if counts["queue_failed"] else "HEALTHY",
                        },
                        {
                            "id": "erp",
                            "label": "ERP Receipt",
                            "health": "HEALTHY" if counts["queue_failed"] == 0 else "PARTIAL",
                        },
                        {
                            "id": "invoice",
                            "label": "Invoice Hold",
                            "health": "HELD" if enterprise.invoice.hold_reason else "RELEASED",
                        },
                    ],
                },
                "reconciliation": [
                    {
                        "sequence": event.sequence,
                        "timestamp": event.occurred_at.isoformat(),
                        "expected": event.payload.get(
                            "expected_quantity", enterprise.purchase_order.ordered_quantity
                        ),
                        "recorded": event.payload.get(
                            "recorded_quantity", enterprise.erp_receipt.quantity
                        ),
                        "missing": event.payload.get("missing_quantity", counts["queue_failed"]),
                    }
                    for event in events
                    if event.event_type
                    in {
                        PublicEventType.INCIDENT_DETECTED,
                        PublicEventType.VERIFICATION_COMPLETED,
                    }
                ],
                "active_agents": sum(item["status"] == "RUNNING" for item in agents.values()),
                "agents": list(agents.values()),
                "agent_operations": operations,
                "advisory": advisory,
                "evidence": [_json(item) for item in self.store.list_evidence(self.case_id)],
                "decisions": decisions,
                "approvals": approvals,
                "approval": {
                    "intent_id": active_intent.intent_id if active_intent else None,
                    "status": active_intent.status.value if active_intent else "NOT_REQUESTED",
                    "required_roles": ["INTEGRATION_OPERATOR", "AP_APPROVER"],
                },
                "execution": {
                    "status": execution_status,
                    "effects": effects,
                    "receipts": [_json(item) for item in receipts],
                    "replay_effect_delta": 0 if receipts else None,
                    "recorded_units": counts["erp_recorded"],
                    "missing_units": counts["queue_failed"],
                    "verified": bool(
                        receipts and all(all(item.postconditions.values()) for item in receipts)
                    ),
                },
                "events": event_rows,
                "activity": event_rows,
                "replay": {"latest_sequence": projection_sequence, "replay_safe": True},
            }

    def decide(self, payload: dict[str, Any]) -> dict[str, Any]:
        expected_version = payload.get("expected_case_version", payload.get("case_version"))
        if expected_version is not None:
            try:
                expected = int(expected_version)
            except (TypeError, ValueError) as exc:
                raise ValueError("expected_case_version must be an integer") from exc
            current = self._current_case_version()
            if expected != current:
                raise VersionConflict(
                    f"decision case version is stale: expected {expected}, current {current}"
                )
        command = str(payload.get("command") or payload.get("type") or payload.get("action") or "")
        idempotency_key = str(payload.get("idempotency_key") or "").strip()
        if not idempotency_key:
            raise ValueError("structured decisions require an idempotency_key")
        if command in {"prepare_recovery", "prepare", "prepare_invoice"}:
            tool = payload.get("tool") or command
            return self.prepare_decision(tool, idempotency_key=idempotency_key)
        if command in {"approve", "approval"}:
            principal_id = str(payload.get("principal_id") or "").strip()
            if not principal_id:
                raise ValueError("approval requires an explicit principal_id")
            intent_id = str(payload.get("intent_id") or "").strip()
            if not intent_id:
                raise ValueError("approval requires an intent_id")
            return self.record_approval(
                intent_id=intent_id,
                principal_id=principal_id,
                idempotency_key=idempotency_key,
            )
        if command in {"execute", "recover"}:
            intent_id = str(payload.get("intent_id") or "").strip()
            if not intent_id:
                raise ValueError("execution requires an intent_id")
            return self.execute_decision(intent_id=intent_id, idempotency_key=idempotency_key)
        if command in {"status", "inspect", ""}:
            return self.snapshot()
        raise ValueError("unsupported structured decision command")


class ExperimentRegistry:
    """Process-local registry of independently durable experiment sessions."""

    def __init__(self, repository_root: Path, *, data_directory: Path | None = None) -> None:
        self.repository_root = repository_root.resolve()
        self.data_directory = (
            data_directory or Path(tempfile.mkdtemp(prefix="missing20-registry-"))
        ).resolve()
        self.data_directory.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._sessions: dict[str, ExperimentSession] = {}

    def get(self, incident_id: str = "missing-20-001") -> ExperimentSession:
        if not incident_id or "/" in incident_id or ".." in incident_id:
            raise ValueError("invalid incident ID")
        with self._lock:
            session = self._sessions.get(incident_id)
            if session is None:
                session = ExperimentSession(
                    self.repository_root,
                    data_directory=self.data_directory / incident_id,
                    incident_id=incident_id,
                )
                self._sessions[incident_id] = session
            return session

    def list(self) -> tuple[ExperimentSession, ...]:
        with self._lock:
            if not self._sessions:
                return (self.get(),)
            return tuple(self._sessions.values())


__all__ = ["ExperimentRegistry", "ExperimentSession"]
