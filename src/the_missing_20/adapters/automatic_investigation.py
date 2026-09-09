"""Durable, bounded dispatch of read-only investigations in the local console.

The platform still owns claims, evidence validation and every business effect.
This journal owns only standing read permission and source-version deduplication.
An interrupted model attempt is not silently replayed after a restart.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any


class AutomaticInvestigation:
    def __init__(self, database: Path, platform: Any, advisory: Any) -> None:
        database.parent.mkdir(parents=True, exist_ok=True)
        self.database = database
        self.platform = platform
        self.advisory = advisory
        self.control = threading.RLock()
        self.tick_lock = threading.Lock()
        self.wake = threading.Event()
        self.closed = threading.Event()
        self.thread: threading.Thread | None = None
        with self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS permission (
                    id INTEGER PRIMARY KEY CHECK(id=1), enabled INTEGER NOT NULL,
                    case_id TEXT NOT NULL, operator_id TEXT NOT NULL,
                    status TEXT NOT NULL, remaining INTEGER NOT NULL
                );
                INSERT OR IGNORE INTO permission VALUES (1,0,'','','PAUSED',8);
                CREATE TABLE IF NOT EXISTS attempts (
                    case_id TEXT NOT NULL, digest TEXT NOT NULL, status TEXT NOT NULL,
                    run_id TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    attempt INTEGER NOT NULL DEFAULT 1,
                    PRIMARY KEY(case_id,digest,attempt)
                );
                CREATE TABLE IF NOT EXISTS retries (
                    case_id TEXT NOT NULL, digest TEXT NOT NULL, PRIMARY KEY(case_id,digest)
                );
            """)
            columns = {row["name"] for row in db.execute("PRAGMA table_info(attempts)")}
            if "attempt" not in columns:
                db.execute("BEGIN IMMEDIATE")
                db.execute("""CREATE TABLE attempts_v2 (
                    case_id TEXT NOT NULL, digest TEXT NOT NULL, status TEXT NOT NULL,
                    run_id TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    attempt INTEGER NOT NULL DEFAULT 1, PRIMARY KEY(case_id,digest,attempt)
                )""")
                db.execute("INSERT INTO attempts_v2 SELECT *,1 FROM attempts")
                db.execute("DROP TABLE attempts")
                db.execute("ALTER TABLE attempts_v2 RENAME TO attempts")
            # Do not restart a paid request whose final outcome was never recorded.
            if db.execute("SELECT 1 FROM attempts WHERE status='RUNNING'").fetchone():
                db.execute("UPDATE permission SET enabled=0,status='INTERRUPTED'")
                db.execute("UPDATE attempts SET status='INTERRUPTED' WHERE status='RUNNING'")

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.database, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def current(self) -> dict[str, Any]:
        with self._db() as db:
            state = dict(db.execute("SELECT * FROM permission WHERE id=1").fetchone())
            latest = db.execute(
                "SELECT status,run_id,created_at,attempt FROM attempts WHERE case_id=? "
                "ORDER BY rowid DESC LIMIT 1",
                (state["case_id"],),
            ).fetchone()
        return {
            "enabled": bool(state["enabled"]),
            "status": state["status"],
            "case_id": state["case_id"],
            "remaining_runs": state["remaining"],
            "last_attempt": dict(latest) if latest else None,
            "read_only": True,
        }

    def configure(self, enabled: bool, case_id: str, operator_id: str) -> dict[str, Any]:
        if type(enabled) is not bool or not case_id.strip() or not operator_id.strip():
            raise ValueError("Automatic investigation requires case and operator identity.")
        if len(case_id) > 160 or len(operator_id) > 160:
            raise ValueError("Automatic investigation identity is too long.")
        with self.control:
            projection = self.platform.current()
            if projection["case_id"] != case_id:
                raise ValueError("Automatic investigation must target the current case.")
            if enabled:
                self.platform.resume_automatic_investigation()
            with self._db() as db:
                previous = db.execute("SELECT * FROM permission WHERE id=1").fetchone()
                remaining = previous["remaining"]
                if enabled:
                    db.execute(
                        "INSERT OR IGNORE INTO retries SELECT case_id,digest FROM attempts "
                        "WHERE case_id=? AND status IN ('INTERRUPTED','CANCELLED')",
                        (case_id,),
                    )
                db.execute(
                    "UPDATE permission SET enabled=?,case_id=?,operator_id=?,status=?,"
                    "remaining=? WHERE id=1",
                    (
                        int(enabled),
                        case_id,
                        operator_id.strip(),
                        (
                            "WAITING_SOURCE"
                            if projection.get("source_freshness", {}).get("status") == "UNAVAILABLE"
                            else "WATCHING"
                        )
                        if enabled
                        else "PAUSED",
                        remaining,
                    ),
                )
            if not enabled:
                self.platform.cancel_automatic_investigation()
        self.wake.set()
        return self.current()

    def pause(self, status: str = "PAUSED") -> None:
        with self.control, self._db() as db:
            db.execute("UPDATE permission SET enabled=0,status=? WHERE id=1", (status,))
            self.platform.cancel_automatic_investigation()

    def _status(self, status: str) -> None:
        with self._db() as db:
            db.execute("UPDATE permission SET status=? WHERE id=1 AND enabled=1", (status,))

    def tick(self) -> None:
        if not self.tick_lock.acquire(blocking=False):
            return
        try:
            permission = self.current()
            if not permission["enabled"] or self.closed.is_set():
                return
            observed = self.platform.automatic_investigation_observation()
            with self.control:
                current = self.current()
                if not current["enabled"] or self.closed.is_set():
                    return
                if observed["case_id"] != current["case_id"]:
                    self.pause("CASE_CHANGED")
                    return
                if observed["status"] == "STOPPED":
                    self.pause()
                    return
                if observed["status"] != "READY":
                    self._status(observed["status"])
                    return
                case_id, digest = observed["case_id"], observed["digest"]
                with self._db() as db:
                    db.execute("BEGIN IMMEDIATE")
                    prior = db.execute(
                        "SELECT attempt,status FROM attempts WHERE case_id=? AND digest=? "
                        "ORDER BY attempt DESC LIMIT 1",
                        (case_id, digest),
                    ).fetchone()
                    retry = db.execute(
                        "SELECT 1 FROM retries WHERE case_id=? AND digest=?",
                        (case_id, digest),
                    ).fetchone()
                    if prior and not (retry and prior["status"] in {"INTERRUPTED", "CANCELLED"}):
                        db.execute(
                            "UPDATE permission SET status=? WHERE id=1 AND enabled=1",
                            (
                                "AWAITING_REVIEW"
                                if prior["status"] == "PLAN_READY"
                                else "WATCHING"
                                if prior["status"] == "VERIFIED"
                                else "NEEDS_ATTENTION",
                            ),
                        )
                        return
                    if current["remaining_runs"] <= 0:
                        db.execute("UPDATE permission SET enabled=0,status='BUDGET_EXHAUSTED'")
                        return
                    attempt = prior["attempt"] + 1 if prior else 1
                    db.execute(
                        "DELETE FROM retries WHERE case_id=? AND digest=?", (case_id, digest)
                    )
                    db.execute(
                        "INSERT INTO attempts(case_id,digest,status,attempt) "
                        "VALUES (?,?,'RUNNING',?)",
                        (case_id, digest, attempt),
                    )
                    db.execute("UPDATE permission SET remaining=remaining-1,status='INVESTIGATING'")
                projection, started = self.platform.claim_changed_diagnosis(case_id, digest)
                if not started:
                    # Nothing was dispatched; the changed evidence can be observed next tick.
                    with self._db() as db:
                        db.execute(
                            "DELETE FROM attempts WHERE case_id=? AND digest=? AND attempt=?",
                            (case_id, digest, attempt),
                        )
                        db.execute("UPDATE permission SET remaining=remaining+1 WHERE id=1")
                    return
                run_id = projection["agent_run"]["run_id"]
                with self._db() as db:
                    db.execute(
                        "UPDATE attempts SET run_id=? WHERE case_id=? AND digest=? AND attempt=?",
                        (run_id, case_id, digest, attempt),
                    )
            try:
                result = self.advisory.investigate(projection)
            except Exception:
                result = {"status": "AGENT_UNAVAILABLE", "mode": "not_completed", "tool_calls": []}
            terminal = self.platform.finish_automatic_investigation(result, run_id=run_id)
            with self._db() as db:
                db.execute(
                    "UPDATE attempts SET status=? WHERE case_id=? AND digest=? AND attempt=?",
                    (terminal, case_id, digest, attempt),
                )
            self._status(
                "AWAITING_REVIEW"
                if terminal == "PLAN_READY"
                else "WATCHING"
                if terminal == "VERIFIED"
                else "NEEDS_ATTENTION"
            )
        except Exception:
            # Expose a failure without leaking provider payloads or looping on paid calls.
            self.pause("NEEDS_ATTENTION")
        finally:
            self.tick_lock.release()

    def start(self) -> None:
        if self.thread is not None:
            return
        self.thread = threading.Thread(
            target=self._run, name="automatic-investigation", daemon=True
        )
        self.thread.start()

    def _run(self) -> None:
        while not self.closed.is_set():
            self.tick()
            self.wake.wait(30)
            self.wake.clear()

    def close(self) -> None:
        self.closed.set()
        self.wake.set()
        self.platform.cancel_automatic_investigation()
        if self.thread is not None:
            self.thread.join(timeout=1)
