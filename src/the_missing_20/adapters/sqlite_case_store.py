"""SQLite case ledger with append-only events and optimistic projections."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from the_missing_20.authority_b.models import QuorumActionGrant
from the_missing_20.domain.assessment import validate_investigation_assessment
from the_missing_20.domain.errors import IdempotencyConflict, InvalidEventPayload, VersionConflict
from the_missing_20.domain.events import CaseEvent, TransitionCommand
from the_missing_20.domain.execution import (
    DecisionStage,
    DetectionGenesis,
    ExecutionAttempt,
    ExecutionAttemptStatus,
    GrantStatus,
    PolicyDecision,
    PolicyOutcome,
)
from the_missing_20.domain.models import (
    ActionGrant,
    Approval,
    Case,
    ClosureFacts,
    EvaluationDecision,
    EvidenceItem,
    ExecutionReceipt,
    HypothesisConclusion,
    HypothesisType,
    InvestigationAssessment,
    InvestigationDecision,
    validate_role_tool_pair,
)
from the_missing_20.domain.state_machine import advance_case
from the_missing_20.domain.states import TRANSITIONS, TransitionEvent


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


class SQLiteCaseStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self._create_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _create_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS case_genesis (
                    case_id TEXT PRIMARY KEY,
                    trace_id TEXT NOT NULL,
                    genesis_json TEXT NOT NULL,
                    genesis_digest TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS case_projection (
                    case_id TEXT PRIMARY KEY,
                    case_version INTEGER NOT NULL,
                    case_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS case_events (
                    event_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    new_version INTEGER NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    command_digest TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    event_json TEXT NOT NULL,
                    result_case_json TEXT NOT NULL,
                    UNIQUE (case_id, idempotency_key),
                    UNIQUE (case_id, new_version)
                );
                CREATE TABLE IF NOT EXISTS evidence (
                    evidence_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    trace_id TEXT NOT NULL,
                    evidence_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS approvals (
                    approval_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    trace_id TEXT NOT NULL,
                    approval_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS grants (
                    authorization_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    trace_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    grant_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS authority_b_bindings (
                    intent_id TEXT PRIMARY KEY,
                    grant_digest TEXT NOT NULL UNIQUE,
                    grant_json TEXT NOT NULL,
                    bridge_authorization_id TEXT NOT NULL UNIQUE,
                    bridge_grant_json TEXT NOT NULL,
                    bound_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS policy_decisions (
                    decision_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    trace_id TEXT NOT NULL,
                    decision_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS execution_attempts (
                    execution_id TEXT PRIMARY KEY,
                    authorization_id TEXT NOT NULL UNIQUE,
                    case_id TEXT NOT NULL,
                    trace_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    command_digest TEXT NOT NULL,
                    attempt_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS execution_receipts (
                    execution_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    trace_id TEXT NOT NULL,
                    receipt_json TEXT NOT NULL
                );
                """
            )

    def create_case(self, case: Case, genesis: DetectionGenesis) -> None:
        if case.case_id != genesis.case_id:
            raise InvalidEventPayload("genesis case_id does not match the case")
        if case.model_dump_json() != genesis.initial_case_json:
            raise InvalidEventPayload("genesis initial projection does not match the case")
        genesis_json = genesis.model_dump_json()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO case_genesis VALUES (?, ?, ?, ?)",
                (case.case_id, genesis.trace_id, genesis_json, _digest(json.loads(genesis_json))),
            )
            connection.execute(
                "INSERT INTO case_projection VALUES (?, ?, ?)",
                (case.case_id, case.case_version, case.model_dump_json()),
            )

    def get_case(self, case_id: str) -> Case:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT case_json FROM case_projection WHERE case_id = ?", (case_id,)
            ).fetchone()
            if row is None:
                raise LookupError(f"unknown case {case_id}")
            return Case.model_validate_json(row["case_json"])

    @staticmethod
    def _require_trace(connection: sqlite3.Connection, case_id: str, trace_id: str) -> None:
        row = connection.execute(
            "SELECT trace_id FROM case_genesis WHERE case_id = ?", (case_id,)
        ).fetchone()
        if row is None:
            raise LookupError(f"unknown case {case_id}")
        if row["trace_id"] != trace_id:
            raise InvalidEventPayload("trace_id does not match immutable case genesis")

    def _apply_transition(
        self, connection: sqlite3.Connection, command: TransitionCommand
    ) -> tuple[Case, CaseEvent]:
        self._require_trace(connection, command.case_id, command.trace_id)
        command_data = command.model_dump(mode="json")
        command_digest = _digest(command_data)
        previous = connection.execute(
            "SELECT command_digest, event_json, result_case_json FROM case_events "
            "WHERE case_id = ? AND idempotency_key = ?",
            (command.case_id, command.idempotency_key),
        ).fetchone()
        if previous is not None:
            if previous["command_digest"] != command_digest:
                raise IdempotencyConflict("idempotency key was reused for a different command")
            return (
                Case.model_validate_json(previous["result_case_json"]),
                CaseEvent.model_validate_json(previous["event_json"]),
            )

        row = connection.execute(
            "SELECT case_version, case_json FROM case_projection WHERE case_id = ?",
            (command.case_id,),
        ).fetchone()
        if row is None:
            raise LookupError(f"unknown case {command.case_id}")
        case = Case.model_validate_json(row["case_json"])
        updated, event = advance_case(case, command)
        connection.execute(
            "INSERT INTO case_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                event.event_id,
                event.case_id,
                event.new_version,
                event.idempotency_key,
                command_digest,
                event.payload_json,
                event.model_dump_json(),
                updated.model_dump_json(),
            ),
        )
        changed = connection.execute(
            "UPDATE case_projection SET case_version = ?, case_json = ? "
            "WHERE case_id = ? AND case_version = ?",
            (
                updated.case_version,
                updated.model_dump_json(),
                updated.case_id,
                command.expected_version,
            ),
        ).rowcount
        if changed != 1:
            raise VersionConflict("case projection changed during the transition")
        return updated, event

    def apply_transition(self, command: TransitionCommand) -> tuple[Case, CaseEvent]:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            return self._apply_transition(connection, command)

    @staticmethod
    def _validate_replay_payload(
        connection: sqlite3.Connection,
        event: CaseEvent,
        payload: object,
        case: Case,
        admitted_evidence_ids: set[str],
    ) -> None:
        if not isinstance(payload, dict):
            raise InvalidEventPayload("event payload must be a JSON object")
        assessment_events = {
            TransitionEvent.INVESTIGATION_ASSESSED: InvestigationDecision.EVALUATOR_REJECTED,
            TransitionEvent.EVIDENCE_REQUIRED: InvestigationDecision.REQUIRE_EVIDENCE,
            TransitionEvent.ACTION_PROTECTED: InvestigationDecision.PROTECT,
            TransitionEvent.RECEIPT_ALREADY_POSTED: InvestigationDecision.RECEIPT_ALREADY_POSTED,
            TransitionEvent.RECEIPT_RESTART_RECOMMENDED: (
                InvestigationDecision.RECOMMEND_RECEIPT_RESTART
            ),
        }
        if event.event in assessment_events:
            if set(payload) != {"assessment"}:
                raise InvalidEventPayload("assessment event payload is incomplete")
            try:
                assessment = InvestigationAssessment.model_validate_json(
                    json.dumps(payload["assessment"])
                )
            except ValueError as exc:
                raise InvalidEventPayload("assessment event payload is invalid") from exc
            if (
                assessment.case_id != event.case_id
                or assessment.trace_id != event.trace_id
                or assessment.evaluation.trace_id != event.trace_id
                or assessment.decision is not assessment_events[event.event]
                or not assessment.reason_codes
                or set(assessment.admitted_evidence_ids) != admitted_evidence_ids
                or not set(assessment.hypothesis.supporting_evidence_ids).issubset(
                    admitted_evidence_ids
                )
                or not set(assessment.hypothesis.contradicting_evidence_ids).issubset(
                    admitted_evidence_ids
                )
                or not set(assessment.evaluation.validated_evidence_ids).issubset(
                    admitted_evidence_ids
                )
                or set(assessment.missing_evidence_sources)
                != set(assessment.hypothesis.missing_evidence)
            ):
                raise InvalidEventPayload("assessment event payload does not match replay state")
            evidence_rows = connection.execute(
                "SELECT evidence_json FROM evidence WHERE case_id = ? ORDER BY rowid",
                (event.case_id,),
            ).fetchall()
            validate_investigation_assessment(
                assessment,
                admitted_evidence=tuple(
                    evidence
                    for row in evidence_rows
                    for evidence in (EvidenceItem.model_validate_json(row["evidence_json"]),)
                    if evidence.evidence_id in admitted_evidence_ids
                ),
                trace_id=event.trace_id,
            )
            hypothesis = assessment.hypothesis
            evaluation = assessment.evaluation
            compatible = {
                InvestigationDecision.RECOMMEND_RECEIPT_RESTART: (
                    hypothesis.hypothesis_type is HypothesisType.RETRYABLE_MESSAGE
                    and hypothesis.conclusion is HypothesisConclusion.SUPPORTED
                    and evaluation.decision is EvaluationDecision.ACCEPT
                    and evaluation.allowed_next_action is not None
                    and evaluation.allowed_next_action.value == "restart_receipt_message"
                    and not evaluation.failed_invariants
                    and not hypothesis.missing_evidence
                    and not hypothesis.contradicting_evidence_ids
                ),
                InvestigationDecision.RECEIPT_ALREADY_POSTED: (
                    hypothesis.hypothesis_type is HypothesisType.ALREADY_POSTED
                    and hypothesis.conclusion is HypothesisConclusion.SUPPORTED
                    and evaluation.decision is EvaluationDecision.ACCEPT
                    and evaluation.allowed_next_action is None
                    and not evaluation.failed_invariants
                ),
                InvestigationDecision.REQUIRE_EVIDENCE: (
                    hypothesis.conclusion is HypothesisConclusion.NEEDS_EVIDENCE
                    and evaluation.decision is EvaluationDecision.MORE_EVIDENCE
                    and bool(assessment.missing_evidence_sources)
                    and evaluation.allowed_next_action is None
                ),
                InvestigationDecision.PROTECT: (
                    hypothesis.hypothesis_type is HypothesisType.GENUINE_SHORT_SHIPMENT
                    and hypothesis.conclusion is HypothesisConclusion.SUPPORTED
                    and evaluation.decision is EvaluationDecision.REJECT
                    and evaluation.allowed_next_action is None
                    and not hypothesis.missing_evidence
                ),
                InvestigationDecision.EVALUATOR_REJECTED: (
                    evaluation.decision is EvaluationDecision.REJECT
                    and evaluation.allowed_next_action is None
                ),
            }[assessment.decision]
            if not compatible:
                raise InvalidEventPayload("assessment decision is incompatible on replay")
            return
        if event.event is TransitionEvent.EVIDENCE_ADMITTED:
            if set(payload) != {"evidence"}:
                raise InvalidEventPayload("evidence event payload is incomplete")
            try:
                evidence = EvidenceItem.model_validate_json(json.dumps(payload["evidence"]))
            except ValueError as exc:
                raise InvalidEventPayload("evidence event payload is invalid") from exc
            if (
                evidence.case_id != event.case_id
                or evidence.trace_id != event.trace_id
                or evidence.evidence_id in admitted_evidence_ids
            ):
                raise InvalidEventPayload("evidence event payload does not match replay state")
            stored = connection.execute(
                "SELECT evidence_json FROM evidence WHERE evidence_id = ?",
                (evidence.evidence_id,),
            ).fetchone()
            if stored is None or (
                EvidenceItem.model_validate_json(stored["evidence_json"]) != evidence
            ):
                raise InvalidEventPayload("replayed evidence is not the admitted evidence")
            admitted_evidence_ids.add(evidence.evidence_id)
            return
        if event.event is TransitionEvent.INVOICE_POSTCONDITIONS_VERIFIED:
            if set(payload) != {"closure_facts"}:
                raise InvalidEventPayload("closure event payload is incomplete")
            try:
                closure = ClosureFacts.model_validate_json(json.dumps(payload["closure_facts"]))
            except ValueError as exc:
                raise InvalidEventPayload("closure event payload is invalid") from exc
            if (
                not closure.satisfies_closure()
                or closure.expected_receipt_quantity != case.discrepancy.expected_quantity
            ):
                raise InvalidEventPayload("replayed closure facts are not valid")
            return
        if payload:
            raise InvalidEventPayload("event payload is not allowed for this event")

    def replay_case(self, case_id: str) -> Case:
        with self._connect() as connection:
            genesis_row = connection.execute(
                "SELECT genesis_json, genesis_digest FROM case_genesis WHERE case_id = ?",
                (case_id,),
            ).fetchone()
            if genesis_row is None:
                raise LookupError(f"unknown case {case_id}")
            genesis_data = json.loads(genesis_row["genesis_json"])
            if _digest(genesis_data) != genesis_row["genesis_digest"]:
                raise InvalidEventPayload("genesis digest mismatch")
            genesis = DetectionGenesis.model_validate_json(genesis_row["genesis_json"])
            case = Case.model_validate_json(genesis.initial_case_json)
            admitted_evidence_ids = set(genesis.detector_evidence_ids)
            rows = connection.execute(
                "SELECT event_json FROM case_events WHERE case_id = ? ORDER BY new_version",
                (case_id,),
            ).fetchall()
            for row in rows:
                event = CaseEvent.model_validate_json(row["event_json"])
                payload = json.loads(event.payload_json)
                if _digest(payload) != event.payload_digest:
                    raise InvalidEventPayload("event payload digest mismatch")
                if (
                    event.case_id != case_id
                    or event.trace_id != genesis.trace_id
                    or event.prior_version != case.case_version
                    or event.prior_status is not case.status
                ):
                    raise InvalidEventPayload("event does not follow the replayed projection")
                self._validate_replay_payload(
                    connection, event, payload, case, admitted_evidence_ids
                )
                expected_status = TRANSITIONS.get((case.status, event.event))
                if expected_status is not event.new_status:
                    raise InvalidEventPayload("event transition is not allowed")
                evidence_revision = case.current_evidence_revision
                if event.event is TransitionEvent.EVIDENCE_ADMITTED:
                    evidence_revision += 1
                case = case.model_copy(
                    update={
                        "case_version": event.new_version,
                        "status": event.new_status,
                        "current_evidence_revision": evidence_revision,
                        "updated_at": event.occurred_at,
                    }
                )
            return case

    def add_evidence(self, evidence: EvidenceItem) -> None:
        with self._connect() as connection:
            self._require_trace(connection, evidence.case_id, evidence.trace_id)
            connection.execute(
                "INSERT INTO evidence VALUES (?, ?, ?, ?)",
                (
                    evidence.evidence_id,
                    evidence.case_id,
                    evidence.trace_id,
                    evidence.model_dump_json(),
                ),
            )

    def admit_evidence_with_transition(
        self, evidence: EvidenceItem, transition: TransitionCommand
    ) -> tuple[Case, CaseEvent]:
        if evidence.case_id != transition.case_id or evidence.trace_id != transition.trace_id:
            raise InvalidEventPayload("evidence and transition context must match")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._require_trace(connection, evidence.case_id, evidence.trace_id)
            existing = connection.execute(
                "SELECT evidence_json FROM evidence WHERE evidence_id = ?",
                (evidence.evidence_id,),
            ).fetchone()
            if existing is not None:
                if EvidenceItem.model_validate_json(existing["evidence_json"]) != evidence:
                    raise IdempotencyConflict("evidence ID was reused with different content")
            else:
                connection.execute(
                    "INSERT INTO evidence VALUES (?, ?, ?, ?)",
                    (
                        evidence.evidence_id,
                        evidence.case_id,
                        evidence.trace_id,
                        evidence.model_dump_json(),
                    ),
                )
            return self._apply_transition(connection, transition)

    def list_evidence(self, case_id: str) -> tuple[EvidenceItem, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT evidence_json FROM evidence WHERE case_id = ? ORDER BY evidence_id",
                (case_id,),
            ).fetchall()
            return tuple(EvidenceItem.model_validate_json(row["evidence_json"]) for row in rows)

    def save_approval_and_grant(
        self,
        approval: Approval,
        grant: ActionGrant,
        transition: TransitionCommand,
    ) -> tuple[Case, CaseEvent]:
        if not (
            approval.case_id == grant.case_id == transition.case_id
            and approval.trace_id == grant.trace_id == transition.trace_id
            and approval.principal_id == grant.principal_id
            and approval.role is grant.role
            and approval.tool is grant.tool
            and approval.case_version + 1 == grant.case_version
            and approval.parameters_digest == _digest(grant.complete_parameters)
        ):
            raise InvalidEventPayload("approval, grant, and transition binding does not match")
        try:
            validate_role_tool_pair(grant.role, grant.tool)
        except ValueError as exc:
            raise InvalidEventPayload("grant role and tool are not authorized together") from exc
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            updated, event = self._apply_transition(connection, transition)
            connection.execute(
                "INSERT INTO approvals VALUES (?, ?, ?, ?)",
                (
                    approval.approval_id,
                    approval.case_id,
                    approval.trace_id,
                    approval.model_dump_json(),
                ),
            )
            connection.execute(
                "INSERT INTO grants VALUES (?, ?, ?, ?, ?)",
                (
                    grant.authorization_id,
                    grant.case_id,
                    grant.trace_id,
                    GrantStatus.ISSUED.value,
                    grant.model_dump_json(),
                ),
            )
            return updated, event

    def bind_authority_b_grant(
        self,
        *,
        grant: QuorumActionGrant,
        bridge_grant: ActionGrant,
        preparation_transitions: tuple[TransitionCommand, ...] = (),
    ) -> ActionGrant:
        """Atomically bind a verified quorum to the existing execution ledger.

        Authority-B keeps its two-role grant in its own contract and ledger.  The
        historical ``ControlledExecutor`` still uses the ``ActionGrant``-shaped
        execution record, so this method creates one private bridge record in the
        same SQLite transaction as the case authorization transition.  The bridge is
        never accepted by the Authority-B boundary itself; callers can only create it
        after they have validated a ``QuorumActionGrant``.  Preparation transitions
        (used when a deterministic decision starts at ``INVESTIGATING``) and the
        bridge insertion are one transaction, preventing a crash from leaving a
        partially advanced case without a durable binding.
        """

        if not (
            bridge_grant.authorization_id == f"authority-b:{grant.grant_id}"
            and bridge_grant.case_id == grant.case_id
            and bridge_grant.trace_id == grant.trace_id
            and bridge_grant.tool is grant.tool
            and bridge_grant.complete_parameters == grant.complete_parameters
            and bridge_grant.expires_at == grant.expires_at
        ):
            raise InvalidEventPayload("Authority-B bridge grant is not bound to the quorum")
        try:
            validate_role_tool_pair(bridge_grant.role, bridge_grant.tool)
        except ValueError as exc:
            raise InvalidEventPayload(
                "Authority-B bridge role and tool are not authorized"
            ) from exc
        for transition in preparation_transitions:
            if transition.case_id != grant.case_id or transition.trace_id != grant.trace_id:
                raise InvalidEventPayload("Authority-B preparation context does not match grant")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT grant_digest, grant_json, bridge_grant_json "
                "FROM authority_b_bindings WHERE intent_id = ?",
                (grant.intent_id,),
            ).fetchone()
            if existing is not None:
                if (
                    existing["grant_digest"] != grant.grant_digest
                    or existing["grant_json"] != grant.model_dump_json()
                    or existing["bridge_grant_json"] != bridge_grant.model_dump_json()
                ):
                    raise IdempotencyConflict("Authority-B intent is already bound differently")
                return ActionGrant.model_validate_json(existing["bridge_grant_json"])

            row = connection.execute(
                "SELECT case_version, case_json FROM case_projection WHERE case_id = ?",
                (grant.case_id,),
            ).fetchone()
            if row is None:
                raise LookupError(f"unknown case {grant.case_id}")
            current = Case.model_validate_json(row["case_json"])
            if current.case_version != grant.case_version:
                raise VersionConflict("Authority-B intent was created for a stale case version")
            for transition in preparation_transitions:
                current, _event = self._apply_transition(connection, transition)

            expected_status = {
                "restart_receipt_message": "RECEIPT_ACTION_AUTHORIZED",
                "release_invoice": "INVOICE_ACTION_AUTHORIZED",
            }[grant.tool.value]
            if current.status.value != expected_status:
                raise InvalidEventPayload(
                    "Authority-B binding did not reach the controlled action state"
                )
            if bridge_grant.case_version != current.case_version:
                raise InvalidEventPayload(
                    "Authority-B bridge version does not match the authorized case"
                )
            bridge_row = connection.execute(
                "SELECT grant_json FROM grants WHERE authorization_id = ?",
                (bridge_grant.authorization_id,),
            ).fetchone()
            if bridge_row is not None:
                if bridge_row["grant_json"] != bridge_grant.model_dump_json():
                    raise IdempotencyConflict("Authority-B bridge authorization ID is reused")
                return ActionGrant.model_validate_json(bridge_row["grant_json"])
            connection.execute(
                "INSERT INTO grants VALUES (?, ?, ?, ?, ?)",
                (
                    bridge_grant.authorization_id,
                    bridge_grant.case_id,
                    bridge_grant.trace_id,
                    GrantStatus.ISSUED.value,
                    bridge_grant.model_dump_json(),
                ),
            )
            connection.execute(
                "INSERT INTO authority_b_bindings VALUES (?, ?, ?, ?, ?, ?)",
                (
                    grant.intent_id,
                    grant.grant_digest,
                    grant.model_dump_json(),
                    bridge_grant.authorization_id,
                    bridge_grant.model_dump_json(),
                    grant.issued_at.isoformat(),
                ),
            )
            return bridge_grant

    def get_authority_b_binding(
        self, intent_id: str
    ) -> tuple[QuorumActionGrant, ActionGrant] | None:
        """Load an Authority-B quorum/bridge binding after process restart."""

        with self._connect() as connection:
            row = connection.execute(
                "SELECT grant_json, bridge_grant_json FROM authority_b_bindings "
                "WHERE intent_id = ?",
                (intent_id,),
            ).fetchone()
            if row is None:
                return None
            return (
                QuorumActionGrant.model_validate_json(row["grant_json"]),
                ActionGrant.model_validate_json(row["bridge_grant_json"]),
            )

    def bind_and_reserve_authority_b_attempt(
        self,
        *,
        grant: QuorumActionGrant,
        bridge_grant: ActionGrant,
        preparation_transitions: tuple[TransitionCommand, ...],
        attempt: ExecutionAttempt,
        decision: PolicyDecision,
        execution_transition: TransitionCommand,
    ) -> tuple[ActionGrant, bool]:
        """Bind a quorum and reserve its first execution in one SQLite transaction.

        This is the Authority-B entry point used by the typed executor.  The private
        bridge, any deterministic lifecycle preparation, the execution-start event,
        policy record, and reserved attempt are committed together.  A returned
        ``False`` means an earlier binding already exists; the caller then uses the
        historical executor's normal idempotent recovery path.
        """

        if not (
            bridge_grant.authorization_id == f"authority-b:{grant.grant_id}"
            and bridge_grant.case_id == grant.case_id
            and bridge_grant.trace_id == grant.trace_id
            and bridge_grant.tool is grant.tool
            and bridge_grant.complete_parameters == grant.complete_parameters
            and bridge_grant.expires_at == grant.expires_at
            and attempt.authorization_id == bridge_grant.authorization_id
            and attempt.case_id == bridge_grant.case_id
            and attempt.trace_id == bridge_grant.trace_id
            and attempt.tool is bridge_grant.tool
            and decision.authorization_id == bridge_grant.authorization_id
            and decision.case_id == bridge_grant.case_id
            and decision.trace_id == bridge_grant.trace_id
            and decision.execution_id == attempt.execution_id
            and decision.tool is bridge_grant.tool
            and execution_transition.case_id == grant.case_id
            and execution_transition.trace_id == grant.trace_id
        ):
            raise InvalidEventPayload("Authority-B reservation records are not bound")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT grant_digest, grant_json, bridge_grant_json "
                "FROM authority_b_bindings WHERE intent_id = ?",
                (grant.intent_id,),
            ).fetchone()
            if existing is not None:
                if (
                    existing["grant_digest"] != grant.grant_digest
                    or existing["grant_json"] != grant.model_dump_json()
                    or existing["bridge_grant_json"] != bridge_grant.model_dump_json()
                ):
                    raise IdempotencyConflict("Authority-B intent is already bound differently")
                return ActionGrant.model_validate_json(existing["bridge_grant_json"]), False
            row = connection.execute(
                "SELECT case_version, case_json FROM case_projection WHERE case_id = ?",
                (grant.case_id,),
            ).fetchone()
            if row is None:
                raise LookupError(f"unknown case {grant.case_id}")
            current = Case.model_validate_json(row["case_json"])
            if current.case_version != grant.case_version:
                raise VersionConflict("Authority-B intent was created for a stale case version")
            for transition in preparation_transitions:
                current, _event = self._apply_transition(connection, transition)
            expected_status = {
                "restart_receipt_message": "RECEIPT_ACTION_AUTHORIZED",
                "release_invoice": "INVOICE_ACTION_AUTHORIZED",
            }[grant.tool.value]
            if current.status.value != expected_status:
                raise InvalidEventPayload(
                    "Authority-B reservation did not reach the controlled action state"
                )
            if bridge_grant.case_version != current.case_version:
                raise InvalidEventPayload(
                    "Authority-B bridge version does not match the authorized case"
                )
            if execution_transition.expected_version != current.case_version:
                raise VersionConflict("Authority-B execution transition has a stale version")
            if attempt.status is not ExecutionAttemptStatus.RESERVED:
                raise InvalidEventPayload("Authority-B initial attempt must be RESERVED")
            if decision.decision is not PolicyOutcome.ALLOW:
                raise InvalidEventPayload("Authority-B reservation requires an allow decision")
            grant_row = connection.execute(
                "SELECT grant_json FROM grants WHERE authorization_id = ?",
                (bridge_grant.authorization_id,),
            ).fetchone()
            if grant_row is not None:
                raise IdempotencyConflict("Authority-B bridge authorization ID is reused")
            connection.execute(
                "INSERT INTO grants VALUES (?, ?, ?, ?, ?)",
                (
                    bridge_grant.authorization_id,
                    bridge_grant.case_id,
                    bridge_grant.trace_id,
                    GrantStatus.ISSUED.value,
                    bridge_grant.model_dump_json(),
                ),
            )
            updated, _event = self._apply_transition(connection, execution_transition)
            del updated
            connection.execute(
                "INSERT INTO policy_decisions VALUES (?, ?, ?, ?)",
                (
                    decision.decision_id,
                    decision.case_id,
                    decision.trace_id,
                    decision.model_dump_json(),
                ),
            )
            connection.execute(
                "INSERT INTO execution_attempts VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    attempt.execution_id,
                    attempt.authorization_id,
                    attempt.case_id,
                    attempt.trace_id,
                    attempt.idempotency_key,
                    attempt.command_digest,
                    attempt.model_dump_json(),
                ),
            )
            connection.execute(
                "UPDATE grants SET status = ? WHERE authorization_id = ?",
                (GrantStatus.RESERVED.value, bridge_grant.authorization_id),
            )
            connection.execute(
                "INSERT INTO authority_b_bindings VALUES (?, ?, ?, ?, ?, ?)",
                (
                    grant.intent_id,
                    grant.grant_digest,
                    grant.model_dump_json(),
                    bridge_grant.authorization_id,
                    bridge_grant.model_dump_json(),
                    grant.issued_at.isoformat(),
                ),
            )
            return bridge_grant, True

    def save_policy_decision(self, decision: PolicyDecision) -> None:
        with self._connect() as connection:
            self._require_trace(connection, decision.case_id, decision.trace_id)
            connection.execute(
                "INSERT INTO policy_decisions VALUES (?, ?, ?, ?)",
                (
                    decision.decision_id,
                    decision.case_id,
                    decision.trace_id,
                    decision.model_dump_json(),
                ),
            )

    def list_policy_decisions(self, case_id: str) -> tuple[PolicyDecision, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT decision_json FROM policy_decisions WHERE case_id = ? ORDER BY rowid",
                (case_id,),
            ).fetchall()
            return tuple(PolicyDecision.model_validate_json(row["decision_json"]) for row in rows)

    def save_attempt(self, attempt: ExecutionAttempt) -> None:
        with self._connect() as connection:
            self._require_trace(connection, attempt.case_id, attempt.trace_id)
            connection.execute(
                "INSERT INTO execution_attempts VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    attempt.execution_id,
                    attempt.authorization_id,
                    attempt.case_id,
                    attempt.trace_id,
                    attempt.idempotency_key,
                    attempt.command_digest,
                    attempt.model_dump_json(),
                ),
            )

    def get_attempt(self, execution_id: str) -> ExecutionAttempt | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT attempt_json FROM execution_attempts WHERE execution_id = ?",
                (execution_id,),
            ).fetchone()
            return (
                None if row is None else ExecutionAttempt.model_validate_json(row["attempt_json"])
            )

    def get_grant(self, authorization_id: str) -> tuple[ActionGrant, GrantStatus]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT grant_json, status FROM grants WHERE authorization_id = ?",
                (authorization_id,),
            ).fetchone()
            if row is None:
                raise LookupError(f"unknown authorization {authorization_id}")
            return ActionGrant.model_validate_json(row["grant_json"]), GrantStatus(row["status"])

    def get_grant_status(self, authorization_id: str) -> GrantStatus:
        return self.get_grant(authorization_id)[1]

    def reserve_attempt(
        self,
        *,
        attempt: ExecutionAttempt,
        decision: PolicyDecision,
        transition: TransitionCommand,
    ) -> tuple[Case, CaseEvent, ExecutionAttempt]:
        if not (
            attempt.case_id == decision.case_id == transition.case_id
            and attempt.trace_id == decision.trace_id == transition.trace_id
        ):
            raise InvalidEventPayload("attempt, decision, and transition context must match")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT attempt_json, command_digest FROM execution_attempts "
                "WHERE authorization_id = ?",
                (attempt.authorization_id,),
            ).fetchone()
            if existing is not None:
                if existing["command_digest"] != attempt.command_digest:
                    raise IdempotencyConflict("authorization is reserved by another attempt")
                stored = ExecutionAttempt.model_validate_json(existing["attempt_json"])
                return (
                    self.get_case(stored.case_id),
                    CaseEvent.model_validate_json(
                        connection.execute(
                            "SELECT event_json FROM case_events "
                            "WHERE case_id = ? AND idempotency_key = ?",
                            (stored.case_id, transition.idempotency_key),
                        ).fetchone()["event_json"]
                    ),
                    stored,
                )
            grant_row = connection.execute(
                "SELECT status, grant_json FROM grants WHERE authorization_id = ?",
                (attempt.authorization_id,),
            ).fetchone()
            if grant_row is None:
                raise IdempotencyConflict("authorization is not available for reservation")
            grant = ActionGrant.model_validate_json(grant_row["grant_json"])
            if GrantStatus(grant_row["status"]) is not GrantStatus.ISSUED:
                raise IdempotencyConflict("authorization is not available for reservation")
            try:
                validate_role_tool_pair(grant.role, grant.tool)
            except ValueError as exc:
                raise InvalidEventPayload(
                    "grant role and tool are not authorized together"
                ) from exc
            if (
                decision.decision is not PolicyOutcome.ALLOW
                or decision.decision_stage is not DecisionStage.EXECUTION_GATE
                or decision.authorization_id != grant.authorization_id
                or decision.execution_id != attempt.execution_id
                or decision.principal_id != grant.principal_id
                or decision.trusted_role is not grant.role
                or decision.tool is not grant.tool
                or attempt.authorization_id != grant.authorization_id
                or attempt.case_id != grant.case_id
                or attempt.trace_id != grant.trace_id
                or attempt.tool is not grant.tool
            ):
                raise InvalidEventPayload("allow decision, grant, and attempt are not bound")
            updated, event = self._apply_transition(connection, transition)
            connection.execute(
                "INSERT INTO policy_decisions VALUES (?, ?, ?, ?)",
                (
                    decision.decision_id,
                    decision.case_id,
                    decision.trace_id,
                    decision.model_dump_json(),
                ),
            )
            connection.execute(
                "INSERT INTO execution_attempts VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    attempt.execution_id,
                    attempt.authorization_id,
                    attempt.case_id,
                    attempt.trace_id,
                    attempt.idempotency_key,
                    attempt.command_digest,
                    attempt.model_dump_json(),
                ),
            )
            connection.execute(
                "UPDATE grants SET status = ? WHERE authorization_id = ?",
                (GrantStatus.RESERVED.value, attempt.authorization_id),
            )
            return updated, event, attempt

    def save_receipt(self, receipt: ExecutionReceipt) -> None:
        with self._connect() as connection:
            self._require_trace(connection, receipt.case_id, receipt.trace_id)
            connection.execute(
                "INSERT INTO execution_receipts VALUES (?, ?, ?, ?)",
                (
                    receipt.execution_id,
                    receipt.case_id,
                    receipt.trace_id,
                    receipt.model_dump_json(),
                ),
            )

    def complete_attempt(
        self,
        *,
        receipt: ExecutionReceipt,
        completed_attempt: ExecutionAttempt,
        transition: TransitionCommand | None,
    ) -> tuple[Case, CaseEvent | None]:
        if not (
            receipt.execution_id == completed_attempt.execution_id
            and receipt.authorization_id == completed_attempt.authorization_id
            and receipt.case_id == completed_attempt.case_id
            and receipt.trace_id == completed_attempt.trace_id
        ):
            raise InvalidEventPayload("receipt and completed attempt context must match")
        if transition is not None and (
            transition.case_id != receipt.case_id or transition.trace_id != receipt.trace_id
        ):
            raise InvalidEventPayload("receipt and transition context must match")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._require_trace(connection, receipt.case_id, receipt.trace_id)
            current = connection.execute(
                "SELECT attempt_json FROM execution_attempts WHERE execution_id = ?",
                (receipt.execution_id,),
            ).fetchone()
            if current is None:
                raise LookupError(f"unknown execution {receipt.execution_id}")
            stored = ExecutionAttempt.model_validate_json(current["attempt_json"])
            if stored.status is not ExecutionAttemptStatus.RESERVED:
                existing_receipt = connection.execute(
                    "SELECT receipt_json FROM execution_receipts WHERE execution_id = ?",
                    (receipt.execution_id,),
                ).fetchone()
                if (
                    existing_receipt is None
                    or existing_receipt["receipt_json"] != receipt.model_dump_json()
                ):
                    raise IdempotencyConflict("execution was already completed differently")
                return self.get_case(receipt.case_id), None
            connection.execute(
                "INSERT INTO execution_receipts VALUES (?, ?, ?, ?)",
                (
                    receipt.execution_id,
                    receipt.case_id,
                    receipt.trace_id,
                    receipt.model_dump_json(),
                ),
            )
            connection.execute(
                "UPDATE execution_attempts SET attempt_json = ? WHERE execution_id = ?",
                (completed_attempt.model_dump_json(), completed_attempt.execution_id),
            )
            connection.execute(
                "UPDATE grants SET status = ? WHERE authorization_id = ?",
                (GrantStatus.CONSUMED.value, completed_attempt.authorization_id),
            )
            if transition is None:
                return self.get_case(receipt.case_id), None
            case, event = self._apply_transition(connection, transition)
            return case, event

    def list_events(self, case_id: str) -> tuple[CaseEvent, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT event_json FROM case_events WHERE case_id = ? ORDER BY new_version",
                (case_id,),
            ).fetchall()
            return tuple(CaseEvent.model_validate_json(row["event_json"]) for row in rows)

    def list_approvals(self, case_id: str) -> tuple[Approval, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT approval_json FROM approvals WHERE case_id = ? ORDER BY rowid", (case_id,)
            ).fetchall()
            return tuple(Approval.model_validate_json(row["approval_json"]) for row in rows)

    def list_receipts(self, case_id: str) -> tuple[ExecutionReceipt, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT receipt_json FROM execution_receipts WHERE case_id = ? ORDER BY rowid",
                (case_id,),
            ).fetchall()
            return tuple(ExecutionReceipt.model_validate_json(row["receipt_json"]) for row in rows)

    def list_grants(self, case_id: str) -> tuple[ActionGrant, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT grant_json FROM grants WHERE case_id = ? ORDER BY rowid", (case_id,)
            ).fetchall()
            return tuple(ActionGrant.model_validate_json(row["grant_json"]) for row in rows)

    def list_attempts(self, case_id: str) -> tuple[ExecutionAttempt, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT attempt_json FROM execution_attempts WHERE case_id = ? ORDER BY rowid",
                (case_id,),
            ).fetchall()
            return tuple(ExecutionAttempt.model_validate_json(row["attempt_json"]) for row in rows)

    def get_genesis(self, case_id: str) -> DetectionGenesis:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT genesis_json FROM case_genesis WHERE case_id = ?", (case_id,)
            ).fetchone()
            if row is None:
                raise LookupError(f"unknown case {case_id}")
            return DetectionGenesis.model_validate_json(row["genesis_json"])
