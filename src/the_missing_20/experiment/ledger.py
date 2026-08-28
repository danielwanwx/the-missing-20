"""SQLite-backed ordered public event ledger."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any

from the_missing_20.experiment.events import PublicEventType, PublicIncidentEvent


class EventLedgerError(RuntimeError):
    """The persisted public event stream is malformed or cannot be advanced."""


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class PublicEventLedger:
    """Append-only per-incident event stream with idempotent commands."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self._lock = Lock()
        self._create_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _create_schema(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS public_events (
                    incident_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    event_id TEXT NOT NULL UNIQUE,
                    idempotency_key TEXT NOT NULL,
                    event_json TEXT NOT NULL,
                    PRIMARY KEY (incident_id, sequence),
                    UNIQUE (incident_id, idempotency_key)
                );
                CREATE TABLE IF NOT EXISTS command_fingerprints (
                    incident_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    command_kind TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    PRIMARY KEY (incident_id, idempotency_key)
                );
                """
            )

    @staticmethod
    def _command_digest(
        *, command_kind: str, identity: Mapping[str, Any], payload: Mapping[str, Any]
    ) -> str:
        envelope = {
            "command_kind": command_kind,
            "identity": identity,
            "payload": payload,
        }
        return hashlib.sha256(_canonical(envelope).encode("utf-8")).hexdigest()

    def register_command(
        self,
        *,
        incident_id: str,
        idempotency_key: str,
        command_kind: str,
        identity: Mapping[str, Any],
        payload: Mapping[str, Any],
    ) -> bool:
        """Durably bind a command key to its immutable envelope.

        ``True`` means the exact envelope was already registered and callers may
        return their cached/projection response.  A changed command under the same
        key fails closed, even after a process restart.
        """

        if not incident_id or not idempotency_key or not command_kind:
            raise EventLedgerError("command envelope identity is incomplete")
        fingerprint = self._command_digest(
            command_kind=command_kind,
            identity=identity,
            payload=payload,
        )
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT command_kind, fingerprint FROM command_fingerprints "
                "WHERE incident_id = ? AND idempotency_key = ?",
                (incident_id, idempotency_key),
            ).fetchone()
            if row is not None:
                if row["command_kind"] != command_kind or row["fingerprint"] != fingerprint:
                    raise EventLedgerError(
                        "command idempotency key was reused for a different command envelope"
                    )
                return True
            connection.execute(
                "INSERT INTO command_fingerprints VALUES (?, ?, ?, ?)",
                (incident_id, idempotency_key, command_kind, fingerprint),
            )
            return False

    def append(
        self,
        *,
        incident_id: str,
        trace_id: str,
        case_version: int,
        event_type: PublicEventType,
        actor: str,
        status: str,
        correlation_id: str,
        payload: dict[str, Any] | None = None,
        idempotency_key: str,
        occurred_at: datetime | None = None,
    ) -> PublicIncidentEvent:
        """Append one event, or return the identical event for a repeated command."""

        timestamp = occurred_at or datetime.now(UTC)
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT event_json FROM public_events WHERE incident_id = ? "
                "AND idempotency_key = ?",
                (incident_id, idempotency_key),
            ).fetchone()
            if existing is not None:
                event = PublicIncidentEvent.model_validate_json(existing["event_json"])
                candidate = event.model_copy(
                    update={
                        "trace_id": trace_id,
                        "case_version": case_version,
                        "event_type": event_type,
                        "actor": actor,
                        "status": status,
                        "correlation_id": correlation_id,
                        "payload": payload or {},
                    }
                )
                if candidate != event:
                    raise EventLedgerError("idempotency key was reused for a different event")
                return event
            row = connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 AS next_sequence "
                "FROM public_events WHERE incident_id = ?",
                (incident_id,),
            ).fetchone()
            sequence = int(row["next_sequence"])
            event = PublicIncidentEvent(
                event_id=f"event:{incident_id}:{sequence:06d}",
                incident_id=incident_id,
                trace_id=trace_id,
                sequence=sequence,
                case_version=case_version,
                event_type=event_type,
                actor=actor,
                status=status,
                occurred_at=timestamp,
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
                payload=payload or {},
            )
            connection.execute(
                "INSERT INTO public_events VALUES (?, ?, ?, ?, ?)",
                (
                    incident_id,
                    sequence,
                    event.event_id,
                    idempotency_key,
                    event.model_dump_json(),
                ),
            )
            return event

    def list_events(
        self,
        incident_id: str,
        *,
        after_sequence: int = 0,
        limit: int = 1000,
    ) -> tuple[PublicIncidentEvent, ...]:
        if after_sequence < 0:
            raise ValueError("after_sequence cannot be negative")
        if limit <= 0 or limit > 10_000:
            raise ValueError("event limit must be between one and ten thousand")
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT event_json FROM public_events WHERE incident_id = ? "
                "AND sequence > ? ORDER BY sequence LIMIT ?",
                (incident_id, after_sequence, limit),
            ).fetchall()
        events = tuple(PublicIncidentEvent.model_validate_json(row["event_json"]) for row in rows)
        self.validate(events, after_sequence=after_sequence, incident_id=incident_id)
        return events

    def all_events(self, incident_id: str) -> tuple[PublicIncidentEvent, ...]:
        return self.list_events(incident_id, limit=10_000)

    def latest_sequence(self, incident_id: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) AS latest FROM public_events "
                "WHERE incident_id = ?",
                (incident_id,),
            ).fetchone()
            return int(row["latest"])

    @staticmethod
    def validate(
        events: tuple[PublicIncidentEvent, ...],
        *,
        after_sequence: int = 0,
        incident_id: str | None = None,
    ) -> None:
        """Validate continuity and event identity before exposing a replay."""

        expected = after_sequence + 1
        seen_ids: set[str] = set()
        expected_trace: str | None = None
        for event in events:
            if event.sequence != expected:
                raise EventLedgerError("public event sequence contains a gap or duplicate")
            if incident_id is not None and event.incident_id != incident_id:
                raise EventLedgerError("public event belongs to a different incident")
            if expected_trace is None:
                expected_trace = event.trace_id
            elif event.trace_id != expected_trace:
                raise EventLedgerError("public event sequence contains a trace identity mismatch")
            if event.event_id != f"event:{event.incident_id}:{event.sequence:06d}":
                raise EventLedgerError("public event identity does not match its sequence")
            if event.event_id in seen_ids:
                raise EventLedgerError("public event sequence contains a duplicate identity")
            seen_ids.add(event.event_id)
            expected += 1

    def replay(self, incident_id: str) -> tuple[PublicIncidentEvent, ...]:
        """Read and validate the complete durable stream without mutating it."""

        return self.all_events(incident_id)
