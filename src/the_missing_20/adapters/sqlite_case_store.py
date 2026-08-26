"""SQLite case ledger with append-only events and optimistic projections."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from the_missing_20.domain.errors import IdempotencyConflict, InvalidEventPayload, VersionConflict
from the_missing_20.domain.events import CaseEvent, TransitionCommand
from the_missing_20.domain.execution import (
    DetectionGenesis,
    ExecutionAttempt,
    ExecutionAttemptStatus,
    GrantStatus,
    PolicyDecision,
)
from the_missing_20.domain.models import (
    ActionGrant,
    Approval,
    Case,
    EvidenceItem,
    ExecutionReceipt,
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
                    event.prior_version != case.case_version
                    or event.prior_status is not case.status
                ):
                    raise InvalidEventPayload("event does not follow the replayed projection")
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
        ):
            raise InvalidEventPayload("approval, grant, and transition context must match")
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
                "SELECT status FROM grants WHERE authorization_id = ?",
                (attempt.authorization_id,),
            ).fetchone()
            if grant_row is None or GrantStatus(grant_row["status"]) is not GrantStatus.ISSUED:
                raise IdempotencyConflict("authorization is not available for reservation")
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
