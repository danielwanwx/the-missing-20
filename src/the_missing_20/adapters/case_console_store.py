"""Durable, append-only state for the Case Console demo tenant.

The console has a single scoped case.  This adapter deliberately stores only
that disclosed demo state; it is not a substitute for a production ERP ledger.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class CaseConsoleStore:
    """Persist console snapshots and immutable activity frames by case id."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS console_snapshots (
                    case_id TEXT PRIMARY KEY,
                    snapshot_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS console_events (
                    case_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    event_json TEXT NOT NULL,
                    PRIMARY KEY (case_id, sequence)
                );
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def load(self, case_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT snapshot_json FROM console_snapshots WHERE case_id = ?", (case_id,)
            ).fetchone()
            event_rows = connection.execute(
                "SELECT event_json FROM console_events WHERE case_id = ? ORDER BY sequence ASC",
                (case_id,),
            ).fetchall()
        if row is None:
            return None
        snapshot = json.loads(row["snapshot_json"])
        snapshot["events"] = [json.loads(event["event_json"]) for event in event_rows]
        return snapshot

    def save(
        self,
        case_id: str,
        snapshot: dict[str, Any],
        *,
        event: dict[str, Any] | None = None,
    ) -> None:
        durable_snapshot = {key: value for key, value in snapshot.items() if key != "events"}
        encoded = json.dumps(durable_snapshot, sort_keys=True, separators=(",", ":"))
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT INTO console_snapshots(case_id, snapshot_json) VALUES (?, ?) "
                "ON CONFLICT(case_id) DO UPDATE SET snapshot_json=excluded.snapshot_json",
                (case_id, encoded),
            )
            if event is not None and isinstance(event.get("sequence"), int):
                connection.execute(
                    (
                        "INSERT OR IGNORE INTO console_events(case_id, sequence, event_json) "
                        "VALUES (?, ?, ?)"
                    ),
                    (
                        case_id,
                        event["sequence"],
                        json.dumps(event, sort_keys=True, separators=(",", ":")),
                    ),
                )

    def reset(self, case_id: str) -> None:
        """Clear one isolated demo case before admitting a fresh run."""

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DELETE FROM console_events WHERE case_id = ?", (case_id,))
            connection.execute("DELETE FROM console_snapshots WHERE case_id = ?", (case_id,))

    def events_since(self, case_id: str, after: int) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT event_json FROM console_events WHERE case_id = ? AND sequence > ? "
                "ORDER BY sequence ASC",
                (case_id, after),
            ).fetchall()
        return [json.loads(row["event_json"]) for row in rows]
