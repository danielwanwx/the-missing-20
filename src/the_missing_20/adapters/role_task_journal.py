"""Durable, fenced ownership for bounded read-only specialist work.

This journal is NOT an ERP transaction manager. Expired work may be re-read;
no specialist may use it to authorize or replay external writes.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4


class TaskUnavailable(RuntimeError):
    """A task is busy, cancelled, changed, or exhausted its attempts."""


class RoleTaskJournal:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self._connection() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS role_tasks ("
                "task_id TEXT PRIMARY KEY, scope TEXT NOT NULL, role TEXT NOT NULL, "
                "question TEXT NOT NULL, status TEXT NOT NULL, token TEXT NOT NULL, "
                "attempt INTEGER NOT NULL, lease_until REAL NOT NULL, result TEXT)"
            )

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def claim(
        self, scope: str, role: str, question: str, *, now: float | None = None
    ) -> tuple[str, str, dict[str, Any] | None]:
        """Return a lease or a completed cached result; one task per role/run."""
        instant = time.time() if now is None else now
        task_id = hashlib.sha256(f"{scope}:{role}".encode()).hexdigest()
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM role_tasks WHERE task_id=?", (task_id,)).fetchone()
            if row is not None:
                if row["question"] != question:
                    raise TaskUnavailable("role already has a different task in this run")
                if row["status"] == "CANCELLED":
                    raise TaskUnavailable("task was cancelled; a new authorized run is required")
                if row["status"] == "COMPLETED":
                    return task_id, "", json.loads(row["result"])
                if row["status"] == "RUNNING" and row["lease_until"] > instant:
                    raise TaskUnavailable("task already has an active owner")
                if row["attempt"] >= 2:
                    raise TaskUnavailable("task attempt limit reached")
            token = uuid4().hex
            attempt = row["attempt"] + 1 if row is not None else 1
            db.execute(
                "INSERT INTO role_tasks VALUES (?, ?, ?, ?, 'RUNNING', ?, ?, ?, NULL) "
                "ON CONFLICT(task_id) DO UPDATE SET status='RUNNING', token=excluded.token, "
                "attempt=excluded.attempt, lease_until=excluded.lease_until, result=NULL",
                (task_id, scope, role, question, token, attempt, instant + 90),
            )
            return task_id, token, None

    def finish(
        self, task_id: str, token: str, status: str, result: dict[str, Any] | None = None
    ) -> None:
        if status not in {"COMPLETED", "FAILED", "CANCELLED"}:
            raise ValueError("invalid terminal task status")
        if status == "COMPLETED" and result is None:
            raise ValueError("a completed task needs its verified result")
        encoded = (
            json.dumps(result, sort_keys=True, allow_nan=False) if result is not None else None
        )
        with self._connection() as db:
            changed = db.execute(
                "UPDATE role_tasks SET status=?, result=? "
                "WHERE task_id=? AND token=? AND status='RUNNING'",
                (status, encoded, task_id, token),
            ).rowcount
            if changed != 1:
                raise TaskUnavailable("task ownership changed; late result rejected")

    def tasks(self, scope: str) -> list[dict[str, Any]]:
        with self._connection() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT task_id, role, status, attempt FROM role_tasks WHERE scope=? "
                    "ORDER BY role",
                    (scope,),
                )
            ]
