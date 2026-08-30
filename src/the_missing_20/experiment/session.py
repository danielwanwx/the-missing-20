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
import os
import re
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Condition, Event, RLock, Thread, current_thread
from typing import Any

from the_missing_20.adapters.clocks import ManualClock
from the_missing_20.adapters.local_knowledge import LocalKnowledgeRepository
from the_missing_20.adapters.local_signer import LocalSigner
from the_missing_20.adapters.sqlite_case_store import SQLiteCaseStore
from the_missing_20.adapters.strands_models import build_model_factory
from the_missing_20.adapters.synthetic_enterprise import (
    SourceConditionOutbox,
    SyntheticEnterprise,
)
from the_missing_20.agents.events import (
    AgentEventSink,
    AgentOperationEvent,
    AgentOperationEventType,
)
from the_missing_20.agents.harness import (
    AdvisoryStageResult,
    AgentHarness,
    HarnessRun,
)
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
    AdvisoryStatus,
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
    DetectionGenesis,
    ReleaseInvoiceParameters,
    RestartReceiptMessageParameters,
)
from the_missing_20.domain.models import (
    ActionTool,
    Case,
    Discrepancy,
    EvidenceItem,
    EvidenceProvenance,
    EvidenceSourceType,
    HumanRole,
)
from the_missing_20.domain.states import CaseStatus
from the_missing_20.experiment.events import PublicEventType, PublicIncidentEvent
from the_missing_20.experiment.ledger import EventLedgerError, PublicEventLedger
from the_missing_20.ports.agent_model import AgentModelFactory, AgentProvider
from the_missing_20.ports.enterprise_systems import EnterprisePreconditionFailed

BASE_TIME = datetime(2026, 8, 28, 0, 0, tzinfo=UTC)
SIGNING_KEY = b"missing20-local-experiment-only"
DEFAULT_FIXTURE_RELATIVE = Path("fixtures/scenarios/retryable-document-lock.json")
HEALTHY_FIXTURE_RELATIVE = Path("fixtures/scenarios/healthy-flow.json")
TELEMETRY_INTERVAL_SECONDS = 4.0
TELEMETRY_WINDOW_SIZE = 20

# Case Console actions are deliberately a small, typed vocabulary.  The browser
# may render labels, but it must dispatch by these stable identifiers rather than
# trying to infer an operation from assistant prose.
CASE_CONSOLE_ACTIONS: tuple[dict[str, str], ...] = (
    {
        "id": "continue_investigation",
        "label": "Continue investigation",
        "kind": "start",
    },
    {"id": "compare_causes", "label": "Compare causes", "kind": "chat"},
    {"id": "show_evidence", "label": "Show evidence", "kind": "chat"},
    {"id": "explain_decision", "label": "Explain decision", "kind": "chat"},
    {"id": "prepare_recovery", "label": "Prepare recovery", "kind": "decision"},
)


class ScenarioTransitionDenied(RuntimeError):
    """Raised when a scenario change would discard an active incident run."""


class ChatSecurityError(ValueError):
    """Raised when untrusted chat input attempts to cross the advisory boundary."""


_CHAT_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bignore\s+(?:all|any|the|previous|prior|system|developer)\b", re.I),
    re.compile(r"\b(?:reveal|show|print|expose)\b.{0,32}\b(?:system|developer)\s+prompt\b", re.I),
    re.compile(r"\b(?:jailbreak|prompt\s*injection|\bdan\b)\b", re.I),
    re.compile(
        r"\b(?:bypass|skip|without)\b.{0,32}\b(?:approval|policy|safety|authorization)\b",
        re.I,
    ),
    re.compile(r"\byou\s+are\s+now\s+(?:an?\s+)?(?:admin|developer|system|root)\b", re.I),
)


def _validate_chat_input(question: str, agent_id: str) -> str:
    """Validate operator text and role identity before any model invocation."""

    if not isinstance(agent_id, str) or agent_id not in {
        "orchestrator",
        "retryable_message_investigator",
        "short_shipment_investigator",
        "duplicate_posting_investigator",
    }:
        raise ChatSecurityError("chat agent is not allowlisted")
    text = question.strip()
    if not text or len(text) > 2_000:
        raise ChatSecurityError("chat question must contain one to two thousand characters")
    if any(pattern.search(text) for pattern in _CHAT_INJECTION_PATTERNS):
        raise ChatSecurityError("chat input attempted to bypass the advisory role boundary")
    return text


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

    def __init__(self, session: ExperimentSession, *, operation_namespace: str = "") -> None:
        self._session = session
        # Operation IDs generated by the harness are stable within a run.  A
        # conversational read is a new bounded run, however, and must leave an
        # independently auditable trace instead of being silently collapsed into
        # the initial investigation by the public event idempotency key.
        self._operation_namespace = operation_namespace.strip(":")

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
        # Completion records are the durable run boundary used by a restarted
        # workspace.  Preserve the same redacted provider attribution that the
        # in-memory trace/chat projection exposes so a fresh AgentCore run does
        # not collapse to ``mode: agentcore`` after persistence.  This is
        # metadata only: it contains no runtime ARN, prompt, credentials, or
        # operational authority.
        if event.event_type in {
            AgentOperationEventType.AGENT_COMPLETED,
            AgentOperationEventType.SYNTHESIS_COMPLETED,
            AgentOperationEventType.EVALUATION_COMPLETED,
        }:
            payload["provider_metadata"] = self._session._provider_attribution(
                operation_id=event.operation_id,
                status=event.status,
                stage=event.stage,
                existing=payload.get("provider_metadata"),
                error_code=(
                    str(payload["error_code"])
                    if payload.get("error_code") is not None
                    else None
                ),
            )
        self._session._append(
            event_type,
            actor=event.actor,
            status=event.status,
            case_version=self._session._current_case_version(),
            correlation_id=event.correlation_id,
            idempotency_key=(
                "experiment:agent-operation:"
                f"{self._operation_namespace + ':' if self._operation_namespace else ''}"
                f"{event.event_type.value}:{event.operation_id}"
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
        detection_fixture_path: Path | None = None,
        auto_start: bool = False,
        auto_start_after_detection: bool = False,
        telemetry_enabled: bool = False,
        defer_detection: bool = False,
        telemetry_clock: Callable[[], datetime] | Any | None = None,
        provider_mode: AgentProvider | str | None = None,
        model_factory: AgentModelFactory | None = None,
        aws_profile: str | None = None,
        agentcore_runtime_arn: str | None = None,
        agentcore_qualifier: str | None = None,
    ) -> None:
        self.repository_root = repository_root.resolve()
        self.incident_id = incident_id
        self.case_id = f"case:{incident_id}"
        self.trace_id = f"trace:{incident_id}"
        # A Scenario Lab run starts from the healthy source state.  The incident
        # fixture is retained separately as the detector's expected post-change
        # contract; no browser action is allowed to mutate records directly.
        default_fixture = HEALTHY_FIXTURE_RELATIVE if defer_detection else DEFAULT_FIXTURE_RELATIVE
        self.fixture_path = (fixture_path or self.repository_root / default_fixture).resolve()
        if not self.fixture_path.is_relative_to(self.repository_root):
            raise ValueError("experiment fixture must remain inside the repository")
        default_detection_fixture = (
            self.repository_root / DEFAULT_FIXTURE_RELATIVE
            if defer_detection
            else self.fixture_path
        )
        self.detection_fixture_path = (
            detection_fixture_path or default_detection_fixture
        ).resolve()
        if not self.detection_fixture_path.is_relative_to(self.repository_root):
            raise ValueError("detection fixture must remain inside the repository")
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
        self._run: HarnessRun | AdvisoryStageResult | None = None
        self._run_error: str | None = None
        requested_provider = provider_mode
        if requested_provider is None and model_factory is not None:
            requested_provider = model_factory.provider
        self.provider_mode = AgentProvider.parse(
            requested_provider or os.environ.get("MISSING20_AGENT_PROVIDER", "scripted")
        )
        if model_factory is not None and model_factory.provider is not self.provider_mode:
            raise ValueError("model factory provider does not match provider mode")
        self._model_factory = model_factory
        self._aws_profile = aws_profile or os.environ.get("MISSING20_AWS_PROFILE")
        self._agentcore_runtime_arn = (
            agentcore_runtime_arn
            if agentcore_runtime_arn is not None
            else os.environ.get("MISSING20_AGENTCORE_RUNTIME_ARN") or None
        )
        self._agentcore_qualifier = (
            agentcore_qualifier or os.environ.get("MISSING20_AGENTCORE_QUALIFIER", "DEFAULT")
        ).strip()
        # Normal Operations has a bounded local producer that reads the same
        # enterprise snapshot used by the incident flow and appends observations
        # to the same public ledger.  It never mutates business records or case
        # state; its only purpose is to make the connected source visibly alive.
        self._telemetry_enabled = telemetry_enabled
        # Normal-flow capture time is wall-clock arrival time, independent of the
        # deterministic lifecycle clock used for case/event transitions. Tests may
        # inject a callable or a clock object with ``now()`` to avoid sleeping.
        self._telemetry_clock = telemetry_clock
        self._telemetry_stop = Event()
        self._telemetry_thread: Thread | None = None
        self._telemetry_index = 0
        self._normal_flow = incident_id == "missing-20-normal"
        self._deferred_detection = defer_detection
        # Scenario Lab uses detector-triggered handoff.  Keep this separate from
        # ``auto_start`` (the legacy constructor escape hatch) so a detection can
        # become the only launch boundary while direct test/CLI sessions retain
        # their explicit start semantics.
        self._auto_start_after_detection = auto_start_after_detection
        self._intents: dict[str, AuthorizationIntent] = {}
        self._command_results: dict[str, dict[str, Any]] = {}

        self.ledger = PublicEventLedger(self.data_directory / "public-events.sqlite")
        self._agent_event_sink = _SessionAgentEventSink(self)
        self.enterprise = self._load_enterprise()
        self.store = SQLiteCaseStore(self.data_directory / "case.sqlite")
        # A caller reopening a persisted Scenario Lab directory may not know
        # that the original run was deferred.  The enterprise outbox is the
        # durable source of that fact: if it exists before the public source
        # event, recover as a deferred run instead of attempting to construct
        # an incident from an absent Case record.
        if (
            not self._deferred_detection
            and self.enterprise.read_source_condition_outbox() is not None
            and not self._source_condition_committed()
        ):
            self._deferred_detection = True
        self._quorum = QuorumAuthorizationService(
            principals={
                "integration-operator": HumanRole.INTEGRATION_OPERATOR,
                "ap-approver": HumanRole.AP_APPROVER,
            },
            signer=LocalSigner(SIGNING_KEY),
            clock=self._clock,
            storage_path=self.data_directory / "quorum-ledger.json",
        )
        # Restore the durable ledger clock before replaying a source outbox or
        # completing a partially published detection.  A process can crash
        # after the source event commits but before detection; deriving the
        # next event from BASE_TIME in that window would preserve sequence
        # numbers but give the recovered detector an earlier timestamp than
        # its source event.
        self._restore_event_clock()
        self._recover_persisted_source_transition()
        self._ensure_detection()
        self._restore_telemetry_index()
        if self._telemetry_enabled:
            self._start_telemetry()
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
        events = self.ledger.tail_events(self.incident_id)
        if events:
            latest = max(item.occurred_at for item in events)
            self._event_time = latest
            self._clock.set(max(BASE_TIME, latest))

    def _restore_telemetry_index(self) -> None:
        """Restore the durable observation counter once when opening a session."""

        for event in self.ledger.tail_events(self.incident_id):
            if event.event_type is not PublicEventType.TELEMETRY_OBSERVED:
                continue
            raw_index = event.payload.get("observation_index", 0)
            if isinstance(raw_index, (int, float, str)):
                self._telemetry_index = max(self._telemetry_index, int(raw_index))

    def _start_telemetry(self) -> None:
        """Start the normal-flow observation producer once per session."""

        if self._telemetry_thread is not None:
            return
        # Publish the first observation before returning the scenario snapshot so
        # the first browser paint already has a real stream record to render.
        self.publish_telemetry()
        self._telemetry_thread = Thread(
            target=self._telemetry_worker,
            name=f"missing20-telemetry-{self.incident_id}",
            daemon=True,
        )
        self._telemetry_thread.start()

    def _telemetry_worker(self) -> None:
        """Append one authoritative normal-flow observation per interval."""

        while not self._telemetry_stop.wait(TELEMETRY_INTERVAL_SECONDS):
            try:
                self.publish_telemetry()
            except (OSError, ValueError):
                # A temporary/session database failure must not spin a busy
                # producer.  The browser will surface a disconnected stream and
                # reconnect from the durable cursor when the source returns.
                return

    def stop_telemetry(self) -> None:
        """Stop the optional producer for deterministic test/server teardown."""

        self._telemetry_stop.set()
        thread = self._telemetry_thread
        if thread is not None and thread is not current_thread():
            thread.join(timeout=2)
        self._telemetry_thread = None

    def publish_telemetry(self) -> PublicIncidentEvent | None:
        """Read enterprise truth and append one normal-flow telemetry event.

        The observation is deliberately not a synthetic UI tick: all business
        quantities are read from ``SyntheticEnterprise.read_snapshot`` and the
        resulting event receives the ledger's contiguous sequence and timestamp.
        The same capture path is used before and after Scenario Lab injects its
        source condition.  It always reads the current SyntheticEnterprise
        snapshot; it never accepts counts from the browser or from the source
        transition envelope.
        """

        # Serialize observations with source-condition commands.  Otherwise a
        # worker could read the faulted enterprise rows and publish them before
        # ``source.condition.injected`` has established the public transition.
        with self._command_lock, self._lock:
            if not self._telemetry_enabled:
                return None
            captured_at = self._telemetry_capture_time()
            enterprise = self.enterprise.read_snapshot()
            counts = self._unit_counts(enterprise)
            self._telemetry_index += 1
            observation_index = self._telemetry_index
            recorded_ids = tuple(
                item.unit_id
                for item in enterprise.supply_units
                if item.status is SupplyUnitStatus.ERP_RECORDED
            )
            if recorded_ids:
                window_size = min(TELEMETRY_WINDOW_SIZE, len(recorded_ids))
                offset = ((observation_index - 1) * window_size) % len(recorded_ids)
                observed_unit_ids = tuple(
                    recorded_ids[(offset + index) % len(recorded_ids)]
                    for index in range(window_size)
                )
            else:
                observed_unit_ids = ()
            # Unit IDs identify inventory, not observations.  Each telemetry
            # window therefore receives its own immutable flow-record IDs so a
            # dashboard cannot mistake a recycled order item for throughput.
            batch_id = f"{self.incident_id}:flow-batch:{observation_index:06d}"
            batch_record_ids = tuple(
                f"{batch_id}:record:{index:03d}"
                for index in range(len(observed_unit_ids))
            )
            observed_record_count = len(batch_record_ids)
            return self._append(
                PublicEventType.TELEMETRY_OBSERVED,
                actor="synthetic-enterprise-source",
                status="OBSERVED",
                case_version=self._current_case_version(),
                correlation_id=self.trace_id,
                idempotency_key=f"experiment:telemetry:{observation_index}",
                occurred_at=captured_at,
                payload={
                    "observation_id": f"{self.incident_id}:telemetry:{observation_index:06d}",
                    "observation_index": observation_index,
                    "captured_at": captured_at.isoformat(),
                    "source_stage": "WAREHOUSE_TO_ERP",
                    "throughput_window": 60,
                    "window_seconds": 60,
                    "batch_id": batch_id,
                    "batch_record_ids": list(batch_record_ids),
                    "batch_record_count": observed_record_count,
                    "observed_record_count": observed_record_count,
                    "window_record_count": observed_record_count,
                    "observed_unit_ids": list(observed_unit_ids),
                    # Kept as a compatibility alias for older consumers. Charts
                    # must use the authoritative unit_counts fields below, not
                    # this bounded observation-window size.
                    "throughput_units": observed_record_count,
                    "queue_depth": counts["queue_failed"],
                    # The dashboard's invoice lane is sourced from the same
                    # enterprise read as the other counts.  Keeping it on the
                    # ordered telemetry event avoids making the browser infer
                    # invoice state from ERP state.
                    "invoice_count": enterprise.invoice.quantity,
                    "unit_counts": counts,
                },
            )

    def _source_condition_committed(self) -> bool:
        """Return whether Scenario Lab has recorded its source transaction."""

        return any(
            event.event_type is PublicEventType.SOURCE_CONDITION_INJECTED
            for event in self.ledger.all_events(self.incident_id)
        )

    def _source_condition_outbox(self) -> SourceConditionOutbox | None:
        """Read the enterprise-owned transition envelope awaiting projection."""

        return self.enterprise.read_source_condition_outbox()

    def _source_transition_pending(self) -> bool:
        """Whether source rows committed but their public event is not durable yet."""

        return (
            self._deferred_detection
            and not self._source_condition_committed()
            and self._source_condition_outbox() is not None
        )

    def _awaiting_source_condition(self) -> bool:
        """Whether this deferred run still exposes its healthy pre-incident state."""

        return (
            self._deferred_detection
            and not self._source_condition_committed()
            and self._source_condition_outbox() is None
        )

    @staticmethod
    def _healthy_case_projection(snapshot: Any, *, case_id: str) -> Case:
        """Build a read-only healthy projection before the detector creates a case."""

        return Case(
            case_id=case_id,
            case_version=0,
            scenario_id="healthy-flow",
            status=CaseStatus.OPEN,
            discrepancy=Discrepancy(
                expected_quantity=snapshot.purchase_order.ordered_quantity,
                observed_quantity=snapshot.erp_receipt.quantity,
                missing_quantity=0,
                unit=snapshot.purchase_order.unit,
            ),
            current_evidence_revision=0,
            created_at=BASE_TIME,
            updated_at=BASE_TIME,
        )

    @staticmethod
    def _source_transition_case_projection(snapshot: Any, *, case_id: str) -> Case:
        """Project a committed-but-unpublished source state without claiming detection."""

        missing = snapshot.purchase_order.ordered_quantity - snapshot.erp_receipt.quantity
        return Case(
            case_id=case_id,
            case_version=0,
            scenario_id="retryable-document-lock-pending",
            status=CaseStatus.OPEN,
            discrepancy=Discrepancy(
                expected_quantity=snapshot.purchase_order.ordered_quantity,
                observed_quantity=snapshot.erp_receipt.quantity,
                missing_quantity=missing,
                unit=snapshot.purchase_order.unit,
            ),
            current_evidence_revision=0,
            created_at=BASE_TIME,
            updated_at=BASE_TIME,
        )

    def _append_source_condition_event(
        self, outbox: SourceConditionOutbox
    ) -> PublicIncidentEvent:
        """Publish the exact immutable source envelope, idempotently."""

        return self._append(
            PublicEventType.SOURCE_CONDITION_INJECTED,
            actor="scenario-lab",
            status="INJECTED",
            case_version=0,
            correlation_id=self.trace_id,
            idempotency_key="experiment:source-condition-injected",
            payload={
                "condition": outbox.condition,
                "source_system": "synthetic-enterprise",
                "transaction_status": "COMMITTED",
                "transition_id": outbox.transition_id,
                "committed_at": outbox.committed_at.isoformat(),
                "source_record_id": outbox.post_state.failed_message.message_id,
                "observed_message_status": outbox.post_state.failed_message.status.value,
                "observed_unit_ids": list(outbox.affected_unit_ids),
                "queue_depth": len(outbox.affected_unit_ids),
                "pre_state": self._source_state_payload(outbox.pre_state),
                "post_state": self._source_state_payload(outbox.post_state),
                "committed_post_state": self._source_state_payload(outbox.post_state),
            },
        )

    def _recover_persisted_source_transition(self) -> None:
        """Recover an enterprise outbox before detection on process reopen."""

        if not self._deferred_detection or self._source_condition_committed():
            return
        outbox = self._source_condition_outbox()
        if outbox is None:
            return
        self._append_source_condition_event(outbox)

    def _ensure_detection(self, *, force: bool = False) -> None:
        if self._normal_flow:
            self._ensure_normal_case()
            return
        existing = self.ledger.tail_events(self.incident_id)
        if not force and any(
            item.event_type is PublicEventType.INCIDENT_DETECTED for item in existing
        ):
            self._auto_start_detected_investigation()
            return
        # Deferred Scenario Lab runs may be reopened after the source mutation
        # committed. Detection is allowed only once the immutable source event is
        # present in the public ledger; a forced caller cannot bypass that gate.
        if self._deferred_detection and not self._source_condition_committed():
            return
        from the_missing_20.application.detector import DiscrepancyDetector

        try:
            case = self.store.get_case(self.case_id)
        except LookupError:
            detector = DiscrepancyDetector(self.enterprise, self.store, self._clock)
            initial_units = self.enterprise.list_units()
            case, evidence = detector.detect(
                case_id=self.case_id,
                trace_id=self.trace_id,
                fixture_path=self.detection_fixture_path,
                failed_unit_ids=tuple(
                    item.unit_id
                    for item in initial_units
                    if item.status is SupplyUnitStatus.QUEUE_FAILED
                ),
            )
        else:
            # Detection state is committed atomically in the case store. If the
            # public event append failed after that commit, recover the event from
            # the authoritative case/evidence rather than trying to create genesis
            # a second time.
            evidence = self.store.list_evidence(self.case_id)
            if not evidence:
                raise EventLedgerError("detected case has no authoritative evidence")
        snapshot = self.enterprise.read_snapshot()
        self._append(
            PublicEventType.INCIDENT_DETECTED,
            actor="deterministic-detector",
            status="DETECTED",
            case_version=case.case_version,
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
        # The handoff is deliberately after the durable detection append.  The
        # browser therefore observes a real source -> detector -> harness order,
        # and a reopened session can resume the same idempotent handoff.
        self._auto_start_detected_investigation()

    def _auto_start_detected_investigation(self) -> None:
        """Launch the local harness once after durable deterministic detection."""

        if not self._auto_start_after_detection:
            return
        # A provider/advisory failure is terminal for this immutable incident.
        # Reopening such a session must expose the degraded state, not fail while
        # reconstructing the control plane.
        if self._advisory_terminally_degraded():
            return
        self.start_investigation()

    def _ensure_normal_case(self) -> None:
        """Create the healthy projection without manufacturing an incident."""

        try:
            self.store.get_case(self.case_id)
            return
        except LookupError:
            pass
        occurred_at = BASE_TIME
        snapshot = self.enterprise.read_snapshot()
        case = self._healthy_case_projection(snapshot, case_id=self.case_id)
        genesis = DetectionGenesis(
            case_id=self.case_id,
            trace_id=self.trace_id,
                fixture_path="fixtures/scenarios/healthy-flow.json",
                fixture_digest=hashlib.sha256(self.fixture_path.read_bytes()).hexdigest(),
            initial_case_json=case.model_dump_json(),
            detection_facts={
                "ordered_quantity": snapshot.purchase_order.ordered_quantity,
                "warehouse_quantity": snapshot.warehouse_receipt.quantity,
                "erp_receipt_quantity": snapshot.erp_receipt.quantity,
                "invoice_quantity": snapshot.invoice.quantity,
                "missing_quantity": 0,
                "mode": "NORMAL",
            },
            detector_evidence_ids=(),
            created_at=occurred_at,
        )
        self.store.create_case(case, genesis)

    def inject_source_condition(self) -> PublicIncidentEvent:
        """Commit a source anomaly, then let deterministic detection fresh-read it.

        Scenario Lab is deliberately the only caller of the source mutation.  The
        transaction and its event are serialized so the public ordering always
        shows ``source.condition.injected`` before ``incident.detected``.
        """

        if self._normal_flow:
            raise QuorumDenied("normal flow cannot inject an incident condition")
        if not self._deferred_detection:
            raise QuorumDenied("source condition is only injectable in Scenario Lab sessions")
        with self._command_lock:
            existing = self.ledger.tail_events(self.incident_id)
            prior = next(
                (
                    item
                    for item in existing
                    if item.event_type is PublicEventType.SOURCE_CONDITION_INJECTED
                ),
                None,
            )
            if prior is not None:
                if any(item.event_type is PublicEventType.INCIDENT_DETECTED for item in existing):
                    self._auto_start_detected_investigation()
                    return prior
                self._ensure_detection(force=True)
                return prior

            # The source adapter stores an immutable outbox record in the same
            # SQLite transaction as its 80/20 mutation. If a public-ledger append
            # failed after that commit, reuse the preserved envelope verbatim
            # rather than attempting a second source mutation.
            outbox = self._source_condition_outbox()
            if outbox is None:
                self.enterprise.inject_retryable_document_lock()
                outbox = self._source_condition_outbox()
            if outbox is None:  # pragma: no cover - defensive durability boundary
                raise EnterprisePreconditionFailed("source transition outbox is unavailable")
            event = self._append_source_condition_event(outbox)
            # The detector is intentionally invoked only after the source event is
            # durable.  It then reads the committed source snapshot, rather than
            # receiving the mutation object or a browser-provided unit list.
            self._ensure_detection(force=True)
            # Capture the post-fault source state immediately so the browser has
            # an ordered 100/100/0 -> 100/80/20 transition even before the
            # background cadence emits its next observation.
            self.publish_telemetry()
            return event

    def _mark_investigation_started(self) -> None:
        """Persist the start only when the bounded harness actually begins."""

        self._append(
            PublicEventType.INVESTIGATION_STARTED,
            actor="orchestrator",
            status="RUNNING",
            case_version=self._current_case_version(),
            correlation_id=self.trace_id,
            idempotency_key="experiment:investigation-started",
            payload={
                "investigator_count": 3,
                "mode": self.provider_mode.value,
                "advisory": True,
            },
        )

    def _next_event_time(self) -> datetime:
        self._event_time += timedelta(seconds=1)
        if self._event_time < self._clock.now():
            self._event_time = self._clock.now() + timedelta(seconds=1)
        self._clock.set(self._event_time)
        return self._event_time

    def _telemetry_capture_time(self) -> datetime:
        """Read wall-clock arrival time, with a deterministic test seam."""

        source = self._telemetry_clock
        if source is None:
            captured_at = datetime.now(UTC)
        elif callable(source):
            captured_at = source()
        else:
            captured_at = source.now()
        if captured_at.tzinfo is None or captured_at.utcoffset() is None:
            raise ValueError("telemetry capture clock must return an aware datetime")
        return captured_at

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
        occurred_at: datetime | None = None,
    ) -> PublicIncidentEvent:
        # The worker can receive callbacks from concurrent investigator tasks.  Keep
        # timestamp allocation and durable append in one critical section so a public
        # event never observes a duplicated/non-monotonic local timestamp.
        with self._lock:
            timestamp = self._next_event_time() if occurred_at is None else occurred_at
            if timestamp.tzinfo is None or timestamp.utcoffset() is None:
                raise ValueError("event timestamp must be timezone aware")
            if occurred_at is not None and timestamp <= self._event_time:
                # The ledger remains monotonic even if a wall-clock source is
                # adjusted backwards or two captures share a timestamp. Keep
                # the correction at microsecond precision rather than applying
                # the one-second lifecycle clock to telemetry.
                timestamp = self._event_time + timedelta(microseconds=1)
            if timestamp > self._event_time:
                self._event_time = timestamp
            event = self.ledger.append(
                incident_id=self.incident_id,
                trace_id=self.trace_id,
                case_version=case_version,
                event_type=event_type,
                actor=actor,
                status=status,
                occurred_at=timestamp,
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

    def _source_state_payload(self, snapshot: Any) -> dict[str, Any]:
        """Return the redacted aggregate state committed by the source system."""

        return {
            "purchase_order": _json(snapshot.purchase_order),
            "warehouse_receipt": _json(snapshot.warehouse_receipt),
            "failed_message": _json(snapshot.failed_message),
            "erp_receipt": _json(snapshot.erp_receipt),
            "invoice": _json(snapshot.invoice),
            "unit_counts": self._unit_counts(snapshot),
            "failed_unit_ids": [
                item.unit_id
                for item in snapshot.supply_units
                if item.status is SupplyUnitStatus.QUEUE_FAILED
            ],
            "material_document_count": len(snapshot.material_documents),
            "business_effect_count": len(snapshot.business_effects),
        }

    def start_investigation(self) -> bool:
        """Start the actual local Strands investigation once.

        The thread is intentionally bounded and uses the scripted provider.  It
        allows a browser to subscribe before agent/tool events are appended while
        keeping provider degradation honest and avoiding any AWS call.
        """

        with self._condition:
            if self._normal_flow:
                return False
            if self._awaiting_source_condition() or self._source_transition_pending():
                raise QuorumDenied("source condition must be injected before investigation")
            if self._advisory_terminally_degraded():
                raise QuorumDenied(
                    "advisory workflow is durably degraded; start a fresh incident"
                )
            if self.store.get_case(self.case_id).status is CaseStatus.CLOSED:
                raise QuorumDenied(
                    "closed incident can only replay its existing investigation ledger"
                )
            if self._running or self._run is not None:
                return False
            if any(
                item.event_type
                in {
                    PublicEventType.SYNTHESIS_COMPLETED,
                    PublicEventType.EVALUATION_COMPLETED,
                }
                for item in self.ledger.all_events(self.incident_id)
            ):
                return False
            self._mark_investigation_started()
            self._running = True
            Thread(
                target=self._investigation_worker,
                name="missing20-investigation",
                daemon=True,
            ).start()
            return True

    def run_investigation(self) -> HarnessRun | AdvisoryStageResult | None:
        """Run synchronously for tests or a CLI caller; idempotent after success."""

        with self._condition:
            if self._normal_flow:
                return None
            if self._awaiting_source_condition() or self._source_transition_pending():
                raise QuorumDenied("source condition must be injected before investigation")
            # A provider failure is terminal for the advisory attempt, but it is
            # not a terminal condition for the deterministic decision path.  Do
            # not relaunch the provider; callers such as ``prepare_decision`` may
            # continue with the authoritative case/evidence classification.
            if self._advisory_terminally_degraded():
                return None
            if self._run is not None:
                return self._run
            if self.investigation_is_available() or (
                self.store.get_case(self.case_id).status is CaseStatus.CLOSED
            ):
                return None
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

    def _advisory_terminally_degraded(self) -> bool:
        """Keep provider failure terminal for this immutable incident run."""

        return any(
            item.event_type is PublicEventType.PROVIDER_DEGRADED
            for item in self.ledger.all_events(self.incident_id)
        )

    def _source_availability(self) -> SourceAvailabilitySet:
        return SourceAvailabilitySet(
            sources=tuple(
                SourceAvailability(
                    source_type=source,
                    status=EvidenceReadStatus.AVAILABLE,
                )
                for source in REQUIRED_AUTHORITATIVE_SOURCES
            )
        )

    def _agent_model_factory(self) -> AgentModelFactory:
        """Lazily resolve the explicit advisory provider for this session.

        Construction is intentionally side-effect free.  Bedrock and AgentCore
        clients are created only by a model invocation, so scripted sessions and
        offline tests never contact AWS.
        """

        if self._model_factory is None:
            self._model_factory = build_model_factory(
                self.provider_mode,
                aws_profile=self._aws_profile,
                agentcore_runtime_arn=self._agentcore_runtime_arn,
                agentcore_qualifier=self._agentcore_qualifier,
            )
        return self._model_factory

    def _provider_attribution(
        self,
        *,
        operation_id: str,
        status: str,
        stage: str | None = None,
        existing: object | None = None,
        error_code: str | None = None,
    ) -> dict[str, Any]:
        """Return a bounded redacted projection of actual adapter attribution.

        A completion event is an application lifecycle marker, not provider proof.
        The adapter must supply ``provider_metadata`` after a response returned;
        missing metadata remains missing rather than being reconstructed from
        configuration, a started event, or the public operation ID.
        """

        del operation_id
        metadata = dict(existing) if isinstance(existing, dict) else {}
        if error_code is not None:
            metadata["error_code"] = error_code
            metadata.setdefault("status", "DEGRADED")
            metadata.setdefault("invocation_status", "FAILED")
        if metadata:
            metadata.setdefault("read_only", True)
            metadata.setdefault("authority", "ADVISORY_NOT_OPERATIONAL_DECISION")
        if stage is not None:
            metadata.setdefault("stage", stage)
        # A provider implementation must not be able to smuggle a secret or a
        # resource identifier into a public completion record through custom
        # provenance.  Keep the allowlist explicit and bounded.
        allowed = {
            "mode",
            "provider",
            "model",
            "transport",
            "region",
            "runtime_configured",
            "qualifier",
            "request_count",
            "input_tokens",
            "output_tokens",
            "latency_ms",
            "incremental_cost_usd",
            "cumulative_cost_usd",
            "remaining_cumulative_cost_usd",
            "request_cap",
            "input_token_cap",
            "output_token_cap",
            "status",
            "invocation_status",
            "invocation_id",
            "invocation_proof",
            "read_only",
            "authority",
            "stage",
            "agent_id",
            "error_code",
        }
        return {key: value for key, value in metadata.items() if key in allowed}

    def _run_read_only_harness(
        self, *, operation_namespace: str
    ) -> HarnessRun | AdvisoryStageResult:
        """Run one bounded, read-only Strands turn and persist its operations.

        Copilot turns intentionally do not reuse the initial in-memory run.  Each
        question gets a fresh scripted Strands session so the ledger records the
        actual read-tool calls and evidence handoff that grounded that answer.
        The namespace keeps those otherwise-stable harness operation IDs distinct
        across turns while preserving the same case/trace identity.
        """

        evidence = latest_authoritative_evidence(tuple(self.store.list_evidence(self.case_id)))
        harness = AgentHarness(
            model_factory=self._agent_model_factory(),
            knowledge=LocalKnowledgeRepository(self.repository_root / "fixtures/knowledge"),
            source_availability=self._source_availability(),
            event_sink=_SessionAgentEventSink(
                self,
                operation_namespace=operation_namespace,
            ),
        )
        return harness.run(
            case_id=self.case_id,
            trace_id=self.trace_id,
            evidence=evidence,
        )

    def _run_chat_harness(
        self,
        *,
        operation_namespace: str,
        question: str,
        agent_id: str,
    ) -> Any:
        """Run one selected-role advisory turn through the configured provider."""

        evidence = latest_authoritative_evidence(tuple(self.store.list_evidence(self.case_id)))
        harness = AgentHarness(
            model_factory=self._agent_model_factory(),
            knowledge=LocalKnowledgeRepository(self.repository_root / "fixtures/knowledge"),
            source_availability=self._source_availability(),
            event_sink=_SessionAgentEventSink(
                self,
                operation_namespace=operation_namespace,
            ),
        )
        return harness.run_chat(
            case_id=self.case_id,
            trace_id=self.trace_id,
            evidence=evidence,
            user_question=question,
            selected_agent_id=agent_id,
        )

    def chat_command(
        self,
        question: str,
        *,
        idempotency_key: str,
        agent_id: str = "orchestrator",
    ) -> dict[str, Any]:
        """Run a browser Copilot command without blocking operation-event workers."""

        # Do not hold the snapshot/event lock while the conversational turn invokes the
        # harness.  Strands executes audited tools in worker threads; those workers
        # must be able to append their actual-operation events to the same session
        # ledger before the harness completes.  Durable command fingerprints provide
        # the idempotency boundary.  The separate command lock serializes turns
        # without preventing those event appends.
        with self._command_lock:
            return self.chat(question, idempotency_key=idempotency_key, agent_id=agent_id)

    def decision_command(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Run a structured decision command with durable command idempotency."""

        # ``prepare`` may run the actual agent harness to establish an advisory
        # decision.  As with chat, worker threads need the snapshot/event lock for
        # their durable callbacks, so command serialization uses its own lock.
        with self._command_lock:
            return self.decide(payload)

    def _investigation_worker(self) -> None:
        try:
            harness = AgentHarness(
                model_factory=self._agent_model_factory(),
                knowledge=LocalKnowledgeRepository(self.repository_root / "fixtures/knowledge"),
                source_availability=self._source_availability(),
                event_sink=self._agent_event_sink,
                allow_stage_retries=self.provider_mode is AgentProvider.SCRIPTED,
            )
            evidence = tuple(self.store.list_evidence(self.case_id))
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
                    "provider": self.provider_mode.value,
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
        try:
            return self.store.get_case(self.case_id).case_version
        except LookupError:
            # Deferred Scenario Lab sessions intentionally have no Case until
            # the detector reads the committed source mutation.  Healthy
            # telemetry still belongs to case version zero.
            if self._deferred_detection:
                return 0
            raise

    def _current_decision(self) -> Any:
        case = self.store.get_case(self.case_id)
        evidence = latest_authoritative_evidence(tuple(self.store.list_evidence(self.case_id)))
        if not evidence:
            raise QuorumDenied("no authoritative evidence is available")
        return classify_operational_state(evidence, case=case, trace_id=self.trace_id)

    def _case_console_actions(self) -> list[dict[str, Any]]:
        """Project the bounded Case Console command palette from current truth.

        This is metadata for the UI, not an authority surface.  Every enabled
        action still re-enters the corresponding command method, which performs
        the authoritative case/version/policy checks.  Returning disabled actions
        as well keeps the console stable while making fail-closed reasons visible.
        """

        try:
            case = self.store.get_case(self.case_id)
        except LookupError:
            case = None
        case_version = case.case_version if case is not None else 0
        normal = self._normal_flow or self._awaiting_source_condition()
        source_pending = self._source_transition_pending()
        incident_ready = not normal and not source_pending and case is not None
        advisory_degraded = self._advisory_terminally_degraded()
        investigation_complete = self.investigation_is_available()
        closed = case is not None and case.status is CaseStatus.CLOSED
        if advisory_degraded:
            continue_reason = "Advisory stopped safely; deterministic recovery remains available"
        elif not incident_ready:
            continue_reason = "Waiting for a detected incident"
        elif closed:
            continue_reason = "Case is closed"
        elif self._running:
            continue_reason = "Investigation is already running"
        elif investigation_complete:
            continue_reason = "Investigation is complete"
        else:
            continue_reason = "Ready to launch the investigators"
        common_chat_enabled = incident_ready and not advisory_degraded
        chat_reason = (
            "Available after incident detection"
            if common_chat_enabled
            else (
                "Advisory stopped safely; start a fresh incident"
                if advisory_degraded
                else "Waiting for a detected incident"
            )
        )
        # Hydrate the two bounded intent IDs before deciding whether the
        # prepare control is available after a browser/process restart.
        for tool in (ActionTool.RESTART_RECEIPT_MESSAGE, ActionTool.RELEASE_INVOICE):
            self._load_intent(f"intent:{self.incident_id}:{tool.value}")
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
        decision: Any | None = None
        if incident_ready:
            try:
                decision = self._current_decision()
            except (LookupError, QuorumDenied):
                decision = None
        prepare_enabled = bool(
            incident_ready
            and (investigation_complete or advisory_degraded)
            and not closed
            and active_intent is None
            and decision is not None
            and decision.eligibility.value == "PENDING_APPROVAL"
            and decision.allowed_action is not None
        )
        if advisory_degraded:
            prepare_reason = "Advisory unavailable; deterministic recovery can still be prepared"
        elif not incident_ready:
            prepare_reason = "Waiting for a detected incident"
        elif closed:
            prepare_reason = "Case is closed"
        elif not investigation_complete:
            prepare_reason = "Continue the investigation first"
        elif active_intent is not None:
            prepare_reason = "An action intent is already open"
        elif decision is None or decision.eligibility.value != "PENDING_APPROVAL":
            prepare_reason = "Deterministic policy has no eligible recovery"
        else:
            prepare_reason = "Ready for a structured recovery proposal"

        enabled_by_id = {
            "continue_investigation": incident_ready
            and not advisory_degraded
            and not closed
            and not self._running
            and not investigation_complete,
            "compare_causes": common_chat_enabled,
            "show_evidence": common_chat_enabled,
            "explain_decision": common_chat_enabled,
            "prepare_recovery": prepare_enabled,
        }
        reasons_by_id = {
            "continue_investigation": continue_reason,
            "compare_causes": chat_reason,
            "show_evidence": chat_reason,
            "explain_decision": chat_reason,
            "prepare_recovery": prepare_reason,
        }
        return [
            {
                **definition,
                "enabled": enabled_by_id[definition["id"]],
                "case_version": case_version,
                "reason": reasons_by_id[definition["id"]],
            }
            for definition in CASE_CONSOLE_ACTIONS
        ]

    def _workflow_status(self) -> str:
        """Return a concise status sentence grounded in the current ledger."""

        if self._normal_flow or self._awaiting_source_condition():
            return "healthy source flow; waiting for an incident"
        if self._source_transition_pending():
            return "source transition committed; waiting for public detection"
        if self._advisory_terminally_degraded():
            return "advisory unavailable; deterministic recovery remains available"
        if self._running:
            return "multi-agent investigation is running"
        if self.store.get_case(self.case_id).status is CaseStatus.CLOSED:
            return "case is closed after verified recovery"
        if self.investigation_is_available():
            return "investigation complete; deterministic recovery decision is pending"
        return "incident detected; investigation has not started"

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

    def _ensure_intent_events(self, intent: AuthorizationIntent) -> None:
        """Finish a partially persisted prepare command after a process crash."""

        # ``register_command`` is committed before the command's work starts.  A
        # crash can therefore leave a valid intent with one or both public events
        # absent.  Re-entering the exact same command must complete that durable
        # envelope; returning a blank snapshot would strand the UI forever.
        case_version = self._current_case_version()
        slug = intent.tool.value
        self._append(
            PublicEventType.RECOVERY_PREPARED,
            actor="orchestrator",
            status="PREPARED",
            case_version=case_version,
            correlation_id=intent.intent_id,
            idempotency_key=f"experiment:recovery-prepared:{slug}",
            payload={
                "tool": intent.tool.value,
                "intent_id": intent.intent_id,
                "intent_digest": intent.intent_digest,
                "decision_digest": intent.decision_digest,
                "parameters_digest": intent.parameters_digest,
            },
        )
        self._append(
            PublicEventType.APPROVAL_REQUESTED,
            actor="deterministic-authority",
            status="QUORUM_PENDING",
            case_version=case_version,
            correlation_id=intent.intent_id,
            idempotency_key=f"experiment:approval-requested:{slug}",
            payload={
                "intent_id": intent.intent_id,
                "required_roles": ["INTEGRATION_OPERATOR", "AP_APPROVER"],
            },
        )

    def prepare_decision(self, tool_value: object, *, idempotency_key: str) -> dict[str, Any]:
        tool = self._action_tool(tool_value)
        # Bind the command before any harness or refresh work.  A reused key must
        # not trigger a new investigation/evidence refresh before the durable
        # envelope rejects a changed action.
        command_seen = self._register_command(
            idempotency_key=idempotency_key,
            command_kind="prepare_recovery",
            # The command envelope is bound to the requested tool.  The case
            # version is intentionally not part of this fingerprint: a retry
            # after the associated action has advanced the lifecycle must still
            # resolve the original prepare command idempotently.
            identity={},
            payload={"tool": tool.value},
        )
        if command_seen:
            cached = self._command_results.get(idempotency_key)
            if cached is not None:
                return cached
        run = self.run_investigation()
        if (
            run is None
            and not self.investigation_is_available()
            and not self._advisory_terminally_degraded()
        ):
            raise QuorumDenied("agent investigation is unavailable")
        if tool is ActionTool.RELEASE_INVOICE:
            self._refresh_evidence()
        decision = self._current_decision()
        if decision.allowed_action is not tool or decision.eligibility.value != "PENDING_APPROVAL":
            raise QuorumDenied("deterministic authority does not permit this action")
        intent_id = f"intent:{self.incident_id}:{tool.value}"
        existing = self._load_intent(intent_id)
        if existing is not None:
            if existing.status in {
                QuorumStatus.OPEN,
                QuorumStatus.QUORUM_PENDING,
                QuorumStatus.GRANTED,
            }:
                self._ensure_intent_events(existing)
                response = self.snapshot()
                self._command_results[idempotency_key] = response
                return response
            # A consumed/rejected/expired intent is already terminal.  Returning
            # the projection is safe and preserves command idempotency; callers
            # cannot use it to create another effect.
            response = self.snapshot()
            self._command_results[idempotency_key] = response
            return response
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
        command_seen = self._register_command(
            idempotency_key=idempotency_key,
            command_kind="approve",
            identity={"intent_id": intent_id, "case_version": intent.case_version},
            payload={
                "principal_id": principal_id,
                "decision": AttestationDecision.APPROVED.value,
            },
        )
        if command_seen:
            cached = self._command_results.get(idempotency_key)
            if cached is not None:
                return cached
            prior = next(
                (
                    item
                    for item in self._quorum.list_attestations(intent_id)
                    if item.principal_id == principal_id
                    and item.attestation_id
                    == f"attestation:{self.incident_id}:{principal_id}:{intent_id}"
                ),
                None,
            )
            if prior is not None:
                current = self._quorum.get_intent(intent_id)
                self._intents[intent_id] = current
                self._append(
                    PublicEventType.APPROVAL_RECORDED,
                    actor=principal_id,
                    status=current.status.value,
                    case_version=self._current_case_version(),
                    correlation_id=intent_id,
                    idempotency_key=f"experiment:approval-recorded:{idempotency_key}",
                    payload={
                        "intent_id": intent_id,
                        "principal_id": principal_id,
                        "role": prior.role.value,
                        "attestation_id": prior.attestation_id,
                        "quorum_status": current.status.value,
                    },
                )
                response = self.snapshot()
                self._command_results[idempotency_key] = response
                return response
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
        command_seen = self._register_command(
            idempotency_key=idempotency_key,
            command_kind="execute",
            identity={
                "intent_id": intent_id,
                "execution_id": execution_id,
                "case_version": intent.case_version,
            },
            payload={"effect_key": effect_key},
        )
        if command_seen:
            cached = self._command_results.get(idempotency_key)
            if cached is not None:
                return cached
        if status is QuorumStatus.CONSUMED:
            response = self.snapshot()
            self._command_results[idempotency_key] = response
            return response
        # The Authority-B adapter may advance the case during its preparation
        # transitions before a process crashes.  Re-entering the exact command
        # must therefore reuse the original execution.started case version;
        # appending the same event with the post-reservation version would be
        # interpreted by the public ledger as an idempotency collision.
        self._append_execution_started(
            intent_id=intent_id,
            execution_id=execution_id,
            tool=intent.tool.value,
            slug=slug,
        )
        executor = AuthorityBControlledExecutor(
            store=self.store,
            enterprise=self.enterprise,
            quorum=self._quorum,
            clock=self._clock,
        )
        effects_before = len(self.enterprise.read_snapshot().business_effects)
        try:
            receipt, _ = executor.execute(
                grant,
                execution_id=execution_id,
                idempotency_key=effect_key,
            )
            effects_after_first = len(self.enterprise.read_snapshot().business_effects)
            replay_receipt, _ = executor.execute(
                grant,
                execution_id=execution_id,
                idempotency_key=effect_key,
            )
            effects_after_replay = len(self.enterprise.read_snapshot().business_effects)
        except Exception as exc:
            # The executor can fail after the enterprise commit but before its
            # durable receipt is persisted.  The public blocked event must not
            # claim that no effect exists in that crash window; the next exact
            # command fingerprint is then allowed to resume the reserved attempt.
            effect_created = self.enterprise.get_business_effect(effect_key) is not None
            self._append(
                PublicEventType.WORKFLOW_BLOCKED,
                actor="controlled-executor",
                status="BLOCKED",
                case_version=self._current_case_version(),
                correlation_id=execution_id,
                idempotency_key=f"experiment:execution-blocked:{slug}",
                payload={"reason": type(exc).__name__, "effect_created": effect_created},
            )
            raise
        # AuthorityBControlledExecutor advances the durable quorum intent to
        # CONSUMED.  Refresh the session cache before projecting the next action;
        # retaining the old GRANTED object would make the UI pair a new decision
        # with stale approvals.
        self._intents[intent_id] = self._quorum.get_intent(intent_id)
        replay_effect_delta = effects_after_replay - effects_after_first
        if replay_effect_delta < 0:
            # The synthetic enterprise is append-only.  A negative delta means
            # the replay proof is malformed and must never be presented as safe.
            raise QuorumDenied("replay effect count moved backwards")
        self._append(
            PublicEventType.EXECUTION_COMPLETED,
            actor="controlled-executor",
            status=receipt.operation_result.value,
            case_version=self._current_case_version(),
            correlation_id=execution_id,
            idempotency_key=f"experiment:execution-completed:{slug}",
            payload={
                "execution_id": receipt.execution_id,
                "tool": intent.tool.value,
                "effect_id": self.enterprise.read_snapshot().business_effects[-1].effect_id,
                "material_document_ids": list(receipt.material_document_ids),
                "replay_same_receipt": replay_receipt == receipt,
                "effect_count_before": effects_before,
                "effect_count_after_first": effects_after_first,
                "effect_count_after_replay": effects_after_replay,
                "replay_effect_delta": replay_effect_delta,
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
                "replay_effect_delta": replay_effect_delta,
                "replay_same_receipt": replay_receipt == receipt,
            },
        )
        self._refresh_evidence()
        response = self.snapshot()
        self._command_results[idempotency_key] = response
        return response

    def _append_execution_started(
        self,
        *,
        intent_id: str,
        execution_id: str,
        tool: str,
        slug: str,
    ) -> PublicIncidentEvent:
        """Append or replay the stable public execution-start marker.

        A crash after Authority-B reservation/commit can leave the enterprise and
        case ledger at a later version while the public marker already exists at
        the version observed by the original command.  Public event idempotency
        includes ``case_version``; retaining that durable version makes an exact
        retry resume the executor rather than fail before reaching it.
        """

        idempotency_key = f"experiment:execution-started:{slug}"
        prior = next(
            (
                event
                for event in self.ledger.all_events(self.incident_id)
                if event.idempotency_key == idempotency_key
            ),
            None,
        )
        return self._append(
            PublicEventType.EXECUTION_STARTED,
            actor="controlled-executor",
            status="RUNNING",
            case_version=prior.case_version if prior is not None else self._current_case_version(),
            correlation_id=execution_id,
            idempotency_key=idempotency_key,
            payload={
                "intent_id": intent_id,
                "execution_id": execution_id,
                "tool": tool,
            },
        )

    def chat(
        self,
        question: str,
        *,
        idempotency_key: str,
        agent_id: str = "orchestrator",
    ) -> dict[str, Any]:
        """Answer a bounded read-only Copilot question from current records."""

        text = _validate_chat_input(question, agent_id)
        if (
            self._normal_flow
            or self._awaiting_source_condition()
            or self._source_transition_pending()
        ):
            raise QuorumDenied("case console is available after a source incident is detected")
        if self._advisory_terminally_degraded():
            raise QuorumDenied(
                "advisory workflow is durably degraded; start a fresh incident"
            )
        command_seen = self._register_command(
            idempotency_key=idempotency_key,
            command_kind="chat",
            # A read request remains the same idempotent command even if a
            # separate structured action advances the case before a retry.
            identity={"agent_id": agent_id},
            payload={"question": text, "agent_id": agent_id},
        )
        if command_seen:
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
                    "intent": cached_payload.get("intent", "inspect_incident"),
                    "read_only": True,
                    "agent_id": cached_payload.get("agent_id", agent_id),
                    "provider_metadata": cached_payload.get("provider_metadata", {}),
                    "next_actions": cached_payload.get(
                        "next_actions", self._case_console_actions()
                    ),
                }
                self._command_results[idempotency_key] = response
                return response
        # The envelope is checked before consulting the in-memory result cache.  A
        # caller reusing a key with a changed question must fail closed even when the
        # original response still exists in this process.
        cached_result = self._command_results.get(idempotency_key)
        if cached_result is not None:
            return cached_result
        # Every conversational turn goes through a fresh bounded Strands session
        # and its audited read tools.  The selected role receives a narrower
        # allowlist; the deterministic router below only chooses how to explain
        # those results and never replaces the investigation or reaches a
        # decision/control-plane method.
        chat_run = None
        provider_metadata: dict[str, Any] = {}
        try:
            chat_run = self._run_chat_harness(
                operation_namespace=f"chat:{idempotency_key}",
                question=text,
                agent_id=agent_id,
            )
            provider_metadata = dict(chat_run.provider_metadata)
        except Exception as exc:
            # Real-provider failures are visible and terminal for this advisory
            # run.  There is no scripted fallback and no operational side effect.
            if self.provider_mode is AgentProvider.SCRIPTED:
                raise
            provider_metadata = self._provider_attribution(
                operation_id=f"chat:{idempotency_key}",
                status="FAILED",
                stage="retryable_investigator",
                existing=getattr(exc, "provider_metadata", None),
                error_code=type(exc).__name__,
            )
            provider_metadata["agent_id"] = agent_id
            case_version = self._current_case_version()
            self._append(
                PublicEventType.PROVIDER_DEGRADED,
                actor="incident-copilot",
                status="DEGRADED",
                case_version=case_version,
                correlation_id=f"chat:{idempotency_key}",
                idempotency_key=f"experiment:chat-provider-degraded:{idempotency_key}",
                payload=provider_metadata,
            )
            response = {
                "incident_id": self.incident_id,
                "trace_id": self.trace_id,
                "case_version": case_version,
                "projection_sequence": self.ledger.latest_sequence(self.incident_id),
                "message": (
                    "The selected advisory provider is unavailable. No diagnosis or "
                    "operational action was produced; the case remains fail-closed."
                ),
                "citations": [],
                "intent": "advisory_provider_degraded",
                "agent_id": agent_id,
                "read_only": True,
                "provider_metadata": provider_metadata,
                "next_actions": self._case_console_actions(),
            }
            self._command_results[idempotency_key] = response
            return response

        run = self._run
        # Preserve the historical full scripted run for direct chat-first callers
        # that rely on compare/evaluator explanations.  A real provider turn never
        # launches this second workflow, which keeps one chat request bounded.
        if run is None and self.provider_mode is AgentProvider.SCRIPTED:
            run = self._run_read_only_harness(operation_namespace=f"chat:{idempotency_key}:team")
            with self._condition:
                self._run = run
                self._run_error = None
        snapshot = self.enterprise.read_snapshot()
        failed_ids = [
            item.unit_id
            for item in snapshot.supply_units
            if item.status is SupplyUnitStatus.QUEUE_FAILED
        ]
        evidence = tuple(self.store.list_evidence(self.case_id))
        latest_evidence = latest_authoritative_evidence(evidence)
        citations = [
            item.evidence_id
            for item in latest_evidence
            if item.source_type
                in {
                EvidenceSourceType.FAILED_MESSAGE_QUEUE,
                EvidenceSourceType.ERP_RECEIPT,
                EvidenceSourceType.WAREHOUSE,
                EvidenceSourceType.INVOICE,
                EvidenceSourceType.MATERIAL_DOCUMENT,
                }
        ]
        if chat_run is not None:
            citations = [
                evidence_id
                for evidence_id in citations
                if evidence_id in set(chat_run.read_evidence_ids)
            ]
        lowered = text.lower()
        current_case_version = self._current_case_version()
        current_decision: Any | None = None
        try:
            current_decision = self._current_decision()
        except (LookupError, QuorumDenied):
            current_decision = None
        intent = ""
        status_question = any(
            phrase in lowered
            for phrase in (
                "what is happening",
                "happening now",
                "current status",
                "what's happening",
                "status now",
            )
        )
        next_step_question = "next" in lowered
        retryable_question = (
            "retryable" in lowered
            and any(word in lowered for word in ("evidence", "queue", "message", "prove"))
        )
        status_proof_next_question = (
            status_question
            and next_step_question
            and retryable_question
            and any(word in lowered for word in ("evidence", "prove", "proof"))
        )
        if status_proof_next_question:
            canonical_sources = (
                EvidenceSourceType.FAILED_MESSAGE_QUEUE,
                EvidenceSourceType.ERP_RECEIPT,
                EvidenceSourceType.WAREHOUSE,
            )
            read_ids = set(citations)
            canonical_citations = [
                item.evidence_id
                for source_type in canonical_sources
                for item in latest_evidence
                if item.source_type is source_type and item.evidence_id in read_ids
            ]
            if len(canonical_citations) != len(canonical_sources):
                answer = (
                    "The complete RETRYABLE_MESSAGE proof is not available in the "
                    "selected evidence, so no governed action is recommended."
                )
                citations = canonical_citations
                intent = "retrieve_evidence"
            else:
                counts = self._unit_counts(snapshot)
                answer = (
                    "RETRYABLE_MESSAGE is SUPPORTED. Current status: "
                    f"{counts['total']} expected, {counts['erp_recorded']} in ERP, and "
                    f"{counts['queue_failed']} stopped at the message queue—the "
                    "20-unit gap. Proof: "
                    f"{', '.join(canonical_citations)}. Next: prepare Receipt Message "
                    "Restart for two-role approval; chat is read-only and cannot "
                    "approve or execute autonomously."
                )
                citations = canonical_citations
                intent = "inspect_current_status"
        elif status_question:
            counts = self._unit_counts(snapshot)
            workflow = self._workflow_status()
            answer = (
                f"The source currently shows {counts['total']} expected, "
                f"{counts['erp_recorded']} recorded in ERP, and "
                f"{counts['queue_failed']} stopped at the queue. "
                f"Workflow status: {workflow} (Case v{current_case_version})."
            )
            intent = "inspect_current_status"
        elif any(
            phrase in lowered
            for phrase in (
                "what should we do next",
                "what do we do next",
                "next step",
                "what should happen next",
                "do now",
            )
        ):
            if current_decision is None:
                answer = (
                    f"Case v{current_case_version} has no actionable deterministic decision yet. "
                    "The console will keep the workflow fail-closed."
                )
            elif (
                current_decision.eligibility.value == "PENDING_APPROVAL"
                and current_decision.allowed_action
            ):
                answer = (
                    f"Case v{current_case_version}: prepare "
                    f"{current_decision.allowed_action.value.replace('_', ' ')} "
                    "as a structured proposal. Then the two required roles approve it; "
                    "chat cannot approve or execute."
                )
            else:
                answer = (
                    f"Case v{current_case_version}: deterministic policy reports "
                    f"{current_decision.eligibility.value.replace('_', ' ').lower()}; "
                    "no controlled action is eligible right now."
                )
            intent = "explain_next_step"
        if not intent and retryable_question:
            queue_evidence = next(
                (
                    item
                    for item in latest_authoritative_evidence(evidence)
                    if item.source_type is EvidenceSourceType.FAILED_MESSAGE_QUEUE
                ),
                None,
            )
            if queue_evidence is None:
                answer = "No failed-message evidence is admitted, so retryability is not proven."
                intent = "retrieve_evidence"
            else:
                fields = queue_evidence.admitted_fields
                error_code = fields.get("error_code", "not recorded")
                retry_eligible = fields.get("retry_eligible", "not recorded")
                lock_cleared = fields.get("lock_cleared", "not recorded")
                answer = (
                    f"Evidence {queue_evidence.evidence_id} is the failed-message record. "
                    f"Its authoritative retryability fields are error_code={error_code}, "
                    f"retry_eligible={retry_eligible}, and lock_cleared={lock_cleared}. "
                    "Together they show whether the message can be retried."
                )
                citations = [queue_evidence.evidence_id]
                intent = "retrieve_evidence"
        elif not intent and any(
            word in lowered for word in ("where", "missing", "gone", "twenty", "20")
        ):
            shown_ids = ", ".join(failed_ids[:3]) or "none"
            answer = (
                f"The current authoritative read classifies this as RETRYABLE_MESSAGE: "
                f"{len(failed_ids)} units stopped at the "
                f"message queue. They are the exact unit records {shown_ids}"
                f"{'…' if len(failed_ids) > 3 else ''}."
            )
            intent = "inspect_incident"
        elif not intent and any(
            word in lowered for word in ("evaluator", "evaluation", "decision", "score", "judge")
        ):
            if run is None or current_decision is None:
                answer = (
                    f"Case v{current_case_version} has no complete advisory evaluation to explain. "
                    "The deterministic workflow remains fail-closed."
                )
            else:
                failed = tuple(run.evaluation.failed_invariants)
                failure_text = ", ".join(failed) if failed else "none"
                answer = (
                    f"The evaluator returned {run.evaluation.decision.value} for "
                    f"Case v{current_case_version}; "
                    f"{len(run.evaluation.validated_claim_ids)} claims were validated and "
                    "failed invariants are "
                    f"{failure_text}. Deterministic policy maps that result to "
                    f"{current_decision.eligibility.value.replace('_', ' ').lower()}"
                    + (
                        f" for {current_decision.allowed_action.value.replace('_', ' ')}."
                        if current_decision.allowed_action
                        else "."
                    )
                )
            intent = "explain_evaluator_decision"
        elif not intent and "compare" not in lowered and any(
            word in lowered for word in ("why", "reason", "cause", "hypothesis")
        ):
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
        elif not intent and any(
            word in lowered for word in ("compare", "alternative", "other", "different")
        ):
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
        elif not intent and any(
            word in lowered for word in ("evidence", "cite", "record", "proof")
        ):
            answer = f"The current read is grounded in {len(citations)} admitted evidence records."
            intent = "retrieve_evidence"
        elif not intent and any(
            word in lowered for word in ("prepare", "proposal", "recover", "fix")
        ):
            answer = (
                "I can explain the recovery path, but chat cannot prepare, approve, or execute "
                "an action. Use the structured recovery control; it binds the current intent "
                "and exact two-role gate."
            )
            intent = "explain_authority_boundary"
        elif not intent and any(word in lowered for word in ("approve", "execute")):
            answer = (
                "I can explain or prepare the recovery, but chat cannot approve or execute "
                "it. Use the structured recovery control so the exact two-role authority "
                "gate remains visible."
            )
            intent = "explain_authority_boundary"
        elif not intent:
            answer = (
                "I ran the bounded investigator session. I can inspect the current unit "
                "flow, explain the selected hypothesis, compare alternatives, cite "
                "evidence, or prepare a recovery proposal."
            )
            intent = "inspect_incident"
        next_actions = self._case_console_actions()
        response = {
            "incident_id": self.incident_id,
            "trace_id": self.trace_id,
            "case_version": current_case_version,
            "projection_sequence": self.ledger.latest_sequence(self.incident_id),
            "message": answer,
            "citations": citations,
            "intent": intent,
            "agent_id": agent_id,
            "read_only": True,
            "provider_metadata": provider_metadata,
            "next_actions": next_actions,
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
                "agent_id": agent_id,
                "read_only": True,
                "provider_metadata": provider_metadata,
                "next_actions": next_actions,
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

    def metrics(self) -> dict[str, Any]:
        """Return a compact metrics projection from the authoritative session.

        This is intentionally a projection, not a second source of truth.  The
        native dashboard and an optional Prometheus scrape both consume the same
        enterprise snapshot and ordered public ledger used by the decision flow.
        """

        snapshot = self.snapshot()
        events = snapshot.get("events", [])
        counts = snapshot.get("unit_counts", {})
        by_type: dict[str, int] = {}
        for event in events:
            event_type = str(event.get("event_type") or event.get("event") or "")
            if event_type:
                by_type[event_type] = by_type.get(event_type, 0) + 1
        latest = events[-1] if events else None
        telemetry = snapshot.get("telemetry", {})
        latest_telemetry = telemetry.get("latest") if isinstance(telemetry, dict) else None
        observed_records = 0
        if isinstance(latest_telemetry, dict):
            raw_observed_records: object = latest_telemetry.get("observed_record_count")
            if raw_observed_records is None:
                raw_observed_records = latest_telemetry.get("batch_record_count")
            if raw_observed_records is None:
                raw_observed_records = latest_telemetry.get("window_record_count")
            if raw_observed_records is None:
                raw_observed_records = latest_telemetry.get("throughput_units")
            if isinstance(raw_observed_records, (int, float, str)):
                observed_records = int(raw_observed_records)
        timeline = [
            {
                "sequence": int(event.get("sequence", 0)),
                "timestamp": event.get("occurred_at"),
                "expected": event.get("payload", {}).get(
                    "expected_quantity", counts.get("total", 0)
                ),
                "recorded": event.get("payload", {}).get(
                    "recorded_quantity", counts.get("erp_recorded", 0)
                ),
                "missing": event.get("payload", {}).get(
                    "missing_quantity", counts.get("queue_failed", 0)
                ),
            }
            for event in events
            if event.get("event_type") in {
                PublicEventType.INCIDENT_DETECTED.value,
                PublicEventType.VERIFICATION_COMPLETED.value,
            }
        ]
        return {
            "schema_version": "missing20-metrics/v1",
            "incident_id": snapshot["incident_id"],
            "trace_id": snapshot["trace_id"],
            "case_version": snapshot["case_version"],
            "projection_sequence": snapshot["projection_sequence"],
            "source": "authoritative_snapshot_and_public_ledger",
            "timestamp": (latest or {}).get("occurred_at"),
            "expected_units": counts.get("total", 0),
            "recorded_units": counts.get("erp_recorded", 0),
            "queue_units": counts.get("queue_failed", 0),
            "observed_records": observed_records,
            "flow_event_count": observed_records,
            # Compatibility alias for existing consumers; the UI and new API
            # contract use the unambiguous observed-records name above.
            "throughput_units": observed_records,
            "incident_status": snapshot.get("incident", {}).get("status"),
            "active_agents": snapshot.get("active_agents", 0),
            "tool_calls": by_type.get(PublicEventType.TOOL_COMPLETED.value, 0),
            "evidence_packets": by_type.get(PublicEventType.EVIDENCE_RETURNED.value, 0),
            "event_counts": by_type,
            "latest_event": latest,
            "timeline": timeline,
            "telemetry": {
                "status": telemetry.get("status") if isinstance(telemetry, dict) else "WAITING",
                "latest": latest_telemetry,
                "history": telemetry.get("history", []) if isinstance(telemetry, dict) else [],
            },
            "sse": {
                "latest_sequence": snapshot["projection_sequence"],
                "source": "public_event_ledger",
                "status": "READY",
            },
        }

    def snapshot(self) -> dict[str, Any]:
        """Return one API snapshot whose business values come from authoritative reads."""

        with self._lock:
            enterprise = self.enterprise.read_snapshot()
            try:
                case = self.store.get_case(self.case_id)
            except LookupError:
                if self._source_transition_pending():
                    # Source rows may already be 80/20 while their outbox event
                    # is waiting for a public-ledger retry. Keep that state
                    # truthful and explicitly distinguish it from detection.
                    case = self._source_transition_case_projection(
                        enterprise, case_id=self.case_id
                    )
                elif not self._awaiting_source_condition():
                    raise
                else:
                    # Before injection the deferred run has no incident Case by
                    # design. Expose a read-only healthy projection from the
                    # same authoritative source snapshot; do not create a ledger
                    # record or let this state enter investigation.
                    case = self._healthy_case_projection(enterprise, case_id=self.case_id)
            # Keep browser payloads bounded while ensuring the tail reaches the
            # ledger's true latest sequence. The full immutable stream remains
            # available through cursor-based SSE replay.
            events = self.ledger.tail_events(self.incident_id, limit=2_000)
            counts = self._unit_counts(enterprise)
            unit_rows = [_json(item) for item in enterprise.supply_units]
            event_rows = [_json(item) for item in events]
            telemetry_events = tuple(
                event
                for event in events
                if event.event_type is PublicEventType.TELEMETRY_OBSERVED
            )
            latest_telemetry = telemetry_events[-1] if telemetry_events else None
            telemetry_history = [
                {
                    "sequence": event.sequence,
                    "observed_at": event.occurred_at.isoformat(),
                    **dict(event.payload),
                }
                for event in telemetry_events[-24:]
            ]
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
                advisory_status = getattr(run, "advisory_status", AdvisoryStatus.COMPLETE)
                if isinstance(advisory_status, AdvisoryStatus):
                    advisory_status_value = advisory_status.value
                else:
                    advisory_status_value = str(advisory_status)
                advisory = {
                    "status": advisory_status_value,
                    "provider": run.trace.provider,
                    "model": run.trace.model,
                    "usefulness": (
                        "SCRIPTED_SYNTHETIC_PROOF"
                        if run.trace.provider == AgentProvider.SCRIPTED.value
                        else "LIVE_PROVIDER_ADVISORY"
                    ),
                    "authority": "ADVISORY_NOT_OPERATIONAL_DECISION",
                    "provider_metadata": run.trace.provider_metadata or {},
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
                if isinstance(run, AdvisoryStageResult):
                    # Keep the model branch and the detector-owned catalog as
                    # separate projections.  In particular, do not add omitted
                    # IDs to the model's claim list to make a partial result look
                    # complete.
                    advisory.update(
                        {
                            "warnings": list(run.warnings),
                            "ai_coverage": run.ai_coverage,
                            "authoritative_catalog": run.authoritative_catalog,
                            "evaluator_citation_closure": run.evaluator_citation_closure.model_dump(
                                mode="json"
                            ),
                            "evaluator_source_coverage": run.evaluator_source_coverage.model_dump(
                                mode="json"
                            ),
                            "advisory_stage": run.public(),
                        }
                    )
            elif self._run_error or any(
                item.event_type is PublicEventType.PROVIDER_DEGRADED for item in events
            ):
                advisory = {
                    "status": "DEGRADED",
                    "provider": self.provider_mode.value,
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
                evaluation_event = next(
                    item
                    for item in reversed(events)
                    if item.event_type is PublicEventType.EVALUATION_COMPLETED
                )
                persisted_metadata = evaluation_event.payload.get("provider_metadata")
                provider_metadata = self._provider_attribution(
                    operation_id=evaluation_event.idempotency_key,
                    status=evaluation_event.status,
                    stage="evaluation",
                    existing=persisted_metadata,
                )
                provider_name = provider_metadata.get("provider", self.provider_mode.value)
                model_name = provider_metadata.get("model")
                provider_complete = (
                    provider_metadata.get("status") == "COMPLETE"
                    and provider_metadata.get("invocation_proof") == "returned"
                )
                advisory = {
                    "status": "COMPLETE" if provider_complete else "DEGRADED",
                    "provider": provider_name,
                    "usefulness": (
                        "SCRIPTED_SYNTHETIC_PROOF"
                        if provider_name == AgentProvider.SCRIPTED.value and provider_complete
                        else "LIVE_PROVIDER_ADVISORY"
                        if provider_complete
                        else "NOT_PROVEN"
                    ),
                    "authority": "ADVISORY_NOT_OPERATIONAL_DECISION",
                    "provider_metadata": provider_metadata,
                    "trace_id": self.trace_id,
                    "durable_projection": True,
                }
                if model_name is not None:
                    advisory["model"] = model_name
            else:
                advisory = {
                    "status": "NOT_STARTED",
                    "provider": self.provider_mode.value,
                    "usefulness": (
                        "SCRIPTED_SYNTHETIC_PROOF"
                        if self.provider_mode is AgentProvider.SCRIPTED
                        else "NOT_PROVEN"
                    ),
                    "authority": "ADVISORY_NOT_OPERATIONAL_DECISION",
                }
            decisions: list[dict[str, Any]] = []
            try:
                current_decision = self._current_decision()
            except (LookupError, QuorumDenied):
                current_decision = None
            if current_decision is not None and current_decision.case_version == case.case_version:
                # ``_current_decision`` is a single current classification.  Do not
                # duplicate it once per possible tool: a client must never pair the
                # latest invoice decision with an older receipt intent.
                decisions.append(_json(current_decision))
            approvals: list[dict[str, Any]] = []
            # The quorum ledger is durable across process restarts, while the
            # session's small intent cache is intentionally in-memory.  Hydrate
            # the two bounded action IDs before projecting the active gate so a
            # restarted browser cannot lose an approval or pair it with a stale
            # decision.
            for tool in (ActionTool.RESTART_RECEIPT_MESSAGE, ActionTool.RELEASE_INVOICE):
                self._load_intent(f"intent:{self.incident_id}:{tool.value}")
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
            intent_history = [
                {
                    "intent_id": intent.intent_id,
                    "tool": intent.tool.value,
                    "status": intent.status.value,
                    "case_version": intent.case_version,
                    "intent_digest": intent.intent_digest,
                }
                for intent in sorted(
                    self._intents.values(),
                    key=lambda item: (item.created_at, item.case_version, item.intent_id),
                )
            ]
            active_decision: dict[str, Any] | None = None
            if active_intent is not None:
                active_decision = next(
                    (
                        decision
                        for decision in decisions
                        if decision.get("allowed_action") == active_intent.tool.value
                        and decision.get("case_version") == active_intent.case_version
                    ),
                    None,
                )
            replay_completed = next(
                (
                    event
                    for event in reversed(events)
                    if event.event_type is PublicEventType.VERIFICATION_COMPLETED
                    and event.payload.get("replay_effect_delta") is not None
                ),
                None,
            )
            replay_execution = None
            if replay_completed is not None:
                execution_id = replay_completed.payload.get("execution_id")
                replay_execution = next(
                    (
                        event
                        for event in reversed(events)
                        if event.event_type is PublicEventType.EXECUTION_COMPLETED
                        and event.payload.get("execution_id") == execution_id
                    ),
                    None,
                )
            replay_delta: int | None = None
            replay_safe = False
            if replay_completed is not None and replay_execution is not None:
                candidate_delta = replay_completed.payload.get("replay_effect_delta")
                same_receipt = replay_execution.payload.get("replay_same_receipt") is True
                if isinstance(candidate_delta, int) and not isinstance(candidate_delta, bool):
                    replay_delta = candidate_delta
                    replay_safe = (
                        replay_completed.status == "PASS" and same_receipt and candidate_delta == 0
                    )
            receipts = self.store.list_receipts(self.case_id)
            effects = [_json(item) for item in enterprise.business_effects]
            execution_status = "COMPLETE" if receipts else "NOT_STARTED"
            projection_sequence = events[-1].sequence if events else 0
            current_eligibility = (
                current_decision.eligibility.value if current_decision is not None else None
            )
            source_transition_pending = self._source_transition_pending()
            is_normal = self._normal_flow or self._awaiting_source_condition()
            operational_state = (
                "NORMAL"
                if is_normal
                else "SOURCE_TRANSITION_PENDING"
                if source_transition_pending
                else "INCIDENT"
            )
            health = "HEALTHY" if is_normal else operational_state
            source_outbox = self._source_condition_outbox()
            approval_status = (
                current_eligibility
                if current_eligibility == "NO_ACTION" and active_intent is None
                else active_intent.status.value
                if active_intent
                else "NOT_REQUESTED"
            )
            return {
                "schema_version": "missing20-experiment/v1",
                "incident_id": self.incident_id,
                "trace_id": self.trace_id,
                "case_id": self.case_id,
                "case_version": case.case_version,
                "projection_sequence": projection_sequence,
                "operational_state": operational_state,
                "health": health,
                "source_transition": {
                    "status": "PENDING_PUBLICATION"
                    if source_transition_pending
                    else "PUBLISHED"
                    if self._source_condition_committed()
                    else "NOT_STARTED",
                    "transition_id": source_outbox.transition_id if source_outbox else None,
                },
                # A snapshot is a point-in-time read; the browser's EventSource
                # owns live connection state and reports it separately.
                "connection": {"status": "SNAPSHOT", "source": "SYNTHETIC_EXPERIMENT"},
                "mode": "SCRIPTED_SYNTHETIC",
                "telemetry": {
                    "status": "STREAMING" if latest_telemetry is not None else "WAITING",
                    "source": "synthetic-enterprise-snapshot",
                    "latest": telemetry_history[-1] if telemetry_history else None,
                    "history": telemetry_history,
                },
                "incident": {
                    "status": (
                        "NORMAL"
                        if is_normal
                        else "SOURCE_TRANSITION_PENDING"
                        if source_transition_pending
                        else case.status.value
                    ),
                    "health": health,
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
                    # The UI summary is a projection of every flow node.  The
                    # browser still recomputes these values from ``nodes`` so
                    # no queue-only shortcut can mask an unhealthy ERP or
                    # invoice node.
                    "summary": {
                        "expected": counts["total"],
                        "recorded": counts["erp_recorded"],
                        "queue_exception": counts["queue_failed"],
                        "invoice": enterprise.invoice.quantity,
                        "healthy_nodes": sum(
                            value in {"HEALTHY", "RELEASED"}
                            for value in (
                                "HEALTHY",
                                "ANOMALY" if counts["queue_failed"] else "HEALTHY",
                                "HEALTHY" if counts["queue_failed"] == 0 else "PARTIAL",
                                enterprise.invoice.state.value,
                            )
                        ),
                    },
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
                            "label": "Invoice Hold"
                            if enterprise.invoice.hold_reason
                            else "Invoice",
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
                    "status": approval_status,
                    "tool": active_intent.tool.value if active_intent else None,
                    "decision_eligibility": current_eligibility,
                    "decision_id": (
                        active_decision.get("decision_id") if active_decision is not None else None
                    ),
                    "required_roles": ["INTEGRATION_OPERATOR", "AP_APPROVER"],
                    "history": intent_history,
                },
                "execution": {
                    "status": execution_status,
                    "effects": effects,
                    "receipts": [_json(item) for item in receipts],
                    "replay_effect_delta": replay_delta,
                    "recorded_units": counts["erp_recorded"],
                    "missing_units": counts["queue_failed"],
                    "verified": bool(
                        receipts and all(all(item.postconditions.values()) for item in receipts)
                    ),
                },
                "events": event_rows,
                "activity": event_rows,
                "replay": {
                    "latest_sequence": projection_sequence,
                    "replayed": replay_execution is not None,
                    "replay_safe": replay_safe,
                    "effect_delta": replay_delta,
                },
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

    def __init__(
        self,
        repository_root: Path,
        *,
        data_directory: Path | None = None,
        provider_mode: AgentProvider | str | None = None,
    ) -> None:
        self.repository_root = repository_root.resolve()
        self.data_directory = (
            data_directory or Path(tempfile.mkdtemp(prefix="missing20-registry-"))
        ).resolve()
        self.data_directory.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._sessions: dict[str, ExperimentSession] = {}
        self.provider_mode = AgentProvider.parse(
            provider_mode or os.environ.get("MISSING20_AGENT_PROVIDER", "scripted")
        )
        self._incident_generation = 0
        # Scenario selection is a server-side control-plane state. The browser
        # also persists the selected scenario and exact incident ID in its URL,
        # but the registry must reject a second Incident command until Normal has
        # explicitly reset the active run.
        self._active_scenario = "normal"
        self._active_incident_id = "missing-20-normal"
        self._scenario_candidate_id: str | None = None

    def get(self, incident_id: str = "missing-20-normal") -> ExperimentSession:
        """Look up a registered session without creating arbitrary incidents.

        The healthy control-room session is a known bootstrap resource and may be
        opened lazily.  Every other ID must have been allocated by an explicit
        Scenario Lab command first.  In particular, a typo in a deep link cannot
        seed a new SQLite database, source state, or authoritative ledger.
        """

        if not incident_id or "/" in incident_id or ".." in incident_id:
            raise ValueError("invalid incident ID")
        with self._lock:
            session = self._sessions.get(incident_id)
            if session is not None:
                return session
            persisted_path = self.data_directory / incident_id
            if incident_id != "missing-20-normal" and not persisted_path.exists():
                raise LookupError(f"incident ID is not registered: {incident_id}")
            if incident_id != "missing-20-normal":
                # A previously allocated run remains a valid deep-link target
                # after a process restart. Opening its existing durable state is
                # a lookup; it never seeds a missing directory.
                deferred = incident_id.startswith("missing-20-001-run-")
                session = ExperimentSession(
                    self.repository_root,
                    data_directory=persisted_path,
                    incident_id=incident_id,
                    defer_detection=deferred,
                    telemetry_enabled=deferred,
                    auto_start_after_detection=deferred,
                    provider_mode=self.provider_mode,
                )
                self._sessions[incident_id] = session
                return session
            session = ExperimentSession(
                self.repository_root,
                data_directory=self.data_directory / incident_id,
                incident_id=incident_id,
                fixture_path=self.repository_root / "fixtures/scenarios/healthy-flow.json",
                telemetry_enabled=True,
                provider_mode=self.provider_mode,
            )
            self._sessions[incident_id] = session
            return session

    def _reserve_incident_id_locked(self) -> str:
        """Reserve an identity for the Scenario catalog, without persisting it."""

        if self._scenario_candidate_id is not None:
            return self._scenario_candidate_id
        while True:
            self._incident_generation += 1
            incident_id = f"missing-20-001-run-{self._incident_generation}"
            if incident_id not in self._sessions and not (
                self.data_directory / incident_id
            ).exists():
                self._scenario_candidate_id = incident_id
                return incident_id

    def _new_incident_locked(
        self,
        *,
        defer_detection: bool,
        telemetry_enabled: bool = False,
        auto_start_after_detection: bool = False,
        incident_id: str | None = None,
    ) -> ExperimentSession:
        """Allocate a fresh run ID without reusing an existing persisted directory."""

        if incident_id is None:
            while True:
                self._incident_generation += 1
                incident_id = f"missing-20-001-run-{self._incident_generation}"
                if incident_id not in self._sessions and not (
                    self.data_directory / incident_id
                ).exists():
                    break
        elif incident_id in self._sessions or (self.data_directory / incident_id).exists():
            raise ScenarioTransitionDenied("incident ID is already registered")
        session = ExperimentSession(
            self.repository_root,
            data_directory=self.data_directory / incident_id,
            incident_id=incident_id,
            defer_detection=defer_detection,
            telemetry_enabled=telemetry_enabled,
            auto_start_after_detection=auto_start_after_detection,
            provider_mode=self.provider_mode,
        )
        self._sessions[incident_id] = session
        return session

    def scenario_incident_candidate(self) -> ExperimentSession:
        """Return the one healthy candidate shown by the Scenario catalog."""

        with self._lock:
            candidate_id = self._reserve_incident_id_locked()
            session = self._sessions.get(candidate_id)
            if session is not None:
                return session
            # Kept for direct Scenario Lab callers.  The HTTP catalog uses
            # ``scenario_incident_identity`` so a read never creates a session;
            # the normal browser path allocates this identity only on POST.
            return self._new_incident_locked(
                defer_detection=True,
                telemetry_enabled=True,
                auto_start_after_detection=True,
                incident_id=candidate_id,
            )

    def scenario_incident_identity(self) -> dict[str, object]:
        """Return a catalog identity without creating its backing session."""

        with self._lock:
            incident_id = self._reserve_incident_id_locked()
            return {
                "schema_version": "missing20-experiment-api/v1",
                "incident_id": incident_id,
                "trace_id": f"trace:{incident_id}",
                "case_version": 0,
                "projection_sequence": 0,
            }

    def select_normal(self) -> ExperimentSession:
        """Explicitly reset selection to the healthy flow without deleting history."""

        with self._lock:
            self._active_scenario = "normal"
            self._active_incident_id = "missing-20-normal"
            # A subsequent Incident gets a new candidate; prior runs remain
            # durable and inspectable through their exact IDs.
            self._scenario_candidate_id = None
            return self.get("missing-20-normal")

    def select_incident(self, *, requested_incident_id: str | None = None) -> ExperimentSession:
        """Inject the catalog candidate once, requiring Normal before another run."""

        with self._lock:
            if self._active_scenario != "normal":
                raise ScenarioTransitionDenied(
                    "return to Normal before starting another incident"
                )
            candidate_id = self._reserve_incident_id_locked()
            if requested_incident_id and requested_incident_id != candidate_id:
                raise ScenarioTransitionDenied("incident ID does not match the scenario catalog")
            candidate = self._sessions.get(candidate_id)
            if candidate is None:
                candidate = self._new_incident_locked(
                    defer_detection=True,
                    telemetry_enabled=True,
                    auto_start_after_detection=True,
                    incident_id=candidate_id,
                )
            candidate.inject_source_condition()
            self._active_scenario = "incident"
            self._active_incident_id = candidate.incident_id
            self._scenario_candidate_id = None
            return candidate

    def select_golden(self) -> ExperimentSession:
        """Start a fresh guided run only after an explicit Normal reset."""

        with self._lock:
            if self._active_scenario != "normal":
                raise ScenarioTransitionDenied(
                    "return to Normal before starting another incident"
                )
            session = self._new_incident_locked(defer_detection=True, telemetry_enabled=True)
            session.inject_source_condition()
            self._active_scenario = "golden"
            self._active_incident_id = session.incident_id
            self._scenario_candidate_id = None
            return session

    def select_recovery(self) -> ExperimentSession | None:
        """Select the latest verified run, if one exists, without fabricating state."""

        with self._lock:
            session = self.latest_verified()
            if session is not None:
                self._active_scenario = "recovery"
                self._active_incident_id = session.incident_id
            return session

    def active_scenario(self) -> tuple[str, str]:
        with self._lock:
            return self._active_scenario, self._active_incident_id

    def fresh_incident(self, *, defer_detection: bool = False) -> ExperimentSession:
        """Create a new persisted incident run without replacing prior history.

        Scenario changes are control-room commands, not browser resets.  Once a
        run is verified and closed, a later Incident or Golden Incident must get
        its own enterprise database, event ledger, and evidence IDs so the
        previous Recovery view remains an inspectable authoritative record.
        """

        with self._lock:
            return self._new_incident_locked(defer_detection=defer_detection)

    def fresh_injected_incident(self) -> ExperimentSession:
        """Create a Scenario Lab run whose source condition precedes detection."""

        session = self.fresh_incident(defer_detection=True)
        session.inject_source_condition()
        return session

    def latest_verified(self) -> ExperimentSession | None:
        """Return the newest closed run whose verification is authoritative."""

        with self._lock:
            for session in reversed(tuple(self._sessions.values())):
                snapshot = session.snapshot()
                if (
                    snapshot.get("incident", {}).get("status") == "CLOSED"
                    and snapshot.get("execution", {}).get("verified") is True
                ):
                    return session
        return None

    def close(self) -> None:
        """Stop background producers before releasing the registry."""

        with self._lock:
            sessions = tuple(self._sessions.values())
        for session in sessions:
            session.stop_telemetry()

    def list(self) -> tuple[ExperimentSession, ...]:
        with self._lock:
            if not self._sessions:
                return (self.get("missing-20-normal"),)
            return tuple(self._sessions.values())

    def provider_truth(self) -> dict[str, Any]:
        """Summarize configured and observed provider use without starting a run.

        The health endpoint is intentionally observational.  It must not create
        the normal session (or invoke a provider) merely to answer a health
        check, but it should stop claiming ``provider_calls: false`` after a real
        AgentCore/Bedrock completion has been durably recorded.
        """

        with self._lock:
            sessions = tuple(self._sessions.values())
            provider_mode = self.provider_mode.value
        calls_observed = False
        for session in sessions:
            for event in session.events_since():
                if event.event_type not in {
                    PublicEventType.AGENT_COMPLETED,
                    PublicEventType.SYNTHESIS_COMPLETED,
                    PublicEventType.EVALUATION_COMPLETED,
                }:
                    continue
                payload = event.payload
                metadata = payload.get("provider_metadata")
                if not isinstance(metadata, dict):
                    continue
                provider = metadata.get("provider")
                event_status = str(event.status).strip().upper()
                if (
                    provider is not None
                    and str(provider) != AgentProvider.SCRIPTED.value
                    and metadata.get("invocation_proof") == "returned"
                    and metadata.get("status") == "COMPLETE"
                    and metadata.get("invocation_status") == "COMPLETED"
                    and event_status not in {"FAILED", "DEGRADED", "ERROR", "BLOCKED"}
                ):
                    calls_observed = True
                    break
            if calls_observed:
                break
        return {
            "mode": provider_mode,
            "configured": provider_mode != AgentProvider.SCRIPTED.value,
            "calls_observed": calls_observed,
        }


__all__ = ["ExperimentRegistry", "ExperimentSession"]
