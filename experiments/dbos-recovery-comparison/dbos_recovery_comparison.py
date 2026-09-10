"""Local DBOS SQLite recovery probe.

This is an isolated comparison artifact.  It uses only paths supplied on the
command line and does not import the application under test.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dbos import DBOS, DBOSConfig, SetWorkflowID

APPLICATION_NAME = "m20-dbos-recovery-comparison"
APPLICATION_VERSION = "dbos-2.31.1-probe-v1"
EXECUTOR_ID = "m20-dbos-recovery-probe"
STRUCTURE_INTENT = "structure-intent-001"
STRUCTURE_WORKFLOW_ID = "m20-dbos-structure-intent-001"
EXTERNAL_INTENT_ID = "normal-receipt-billing-intent-001"
WORKFLOW_ID = "m20-dbos-normal-receipt-billing-intent-001"
NO_UNIQUE_INTENT_KEY = "A-no-unique-intent-key"
UNIQUE_INTENT_KEY = "B-unique-intent-key"
VARIANTS = (NO_UNIQUE_INTENT_KEY, UNIQUE_INTENT_KEY)
CRASH_AFTER_EFFECT_ENVIRONMENT = "M20_DBOS_CRASH_AFTER_FAKE_ERP_EFFECT"
CRASH_EXIT_CODE = 97
MAX_CHILD_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True)
class ChildRun:
    """A parent-owned subprocess record used to prove bounded crash handling."""

    phase: str
    pid: int
    returncode: int
    stderr: str
    stdout: str

    def record(self) -> dict[str, object]:
        return {
            "phase": self.phase,
            "pid": self.pid,
            "returncode": self.returncode,
        }


class ChildProcessTimeout(RuntimeError):
    """A phase did not finish inside the explicitly bounded parent timeout."""


def _sqlite_url(path: Path) -> str:
    return f"sqlite:///{path}"


def _config(system_database: Path) -> DBOSConfig:
    return {
        "name": APPLICATION_NAME,
        "application_version": APPLICATION_VERSION,
        "executor_id": EXECUTOR_ID,
        "system_database_url": _sqlite_url(system_database),
        "enable_otlp": False,
        "run_admin_server": False,
        "max_executor_threads": 4,
        "notification_listener_polling_interval_sec": 0.01,
        "notification_coalesce_sec": 0.01,
        "log_level": "WARNING",
    }


@DBOS.step()
def _structure_effect(effect_database: str, intent_id: str) -> dict[str, object]:
    """Commit one deliberately local effect so the SDK has a real step to checkpoint."""
    with sqlite3.connect(effect_database) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS structure_effects ("
            "id INTEGER PRIMARY KEY, intent_id TEXT NOT NULL)"
        )
        cursor = connection.execute(
            "INSERT INTO structure_effects (intent_id) VALUES (?)", (intent_id,)
        )
        effect_id = cursor.lastrowid
    return {"effect_id": effect_id, "intent_id": intent_id}


@DBOS.workflow()
def _structure_workflow(effect_database: str, intent_id: str) -> dict[str, object]:
    return _structure_effect(effect_database, intent_id)


def _effect_count(effect_database: Path) -> int:
    with sqlite3.connect(effect_database) as connection:
        return int(connection.execute("SELECT COUNT(*) FROM structure_effects").fetchone()[0])


def run_structure_probe(runtime_directory: Path) -> dict[str, object]:
    """Run one successful workflow against a DBOS SQLite system database."""
    runtime_directory.mkdir(parents=True, exist_ok=True)
    system_database = runtime_directory / "dbos-system.sqlite"
    effect_database = runtime_directory / "structure-effect.sqlite"
    DBOS(config=_config(system_database))
    DBOS.launch()
    try:
        with SetWorkflowID(STRUCTURE_WORKFLOW_ID):
            handle = DBOS.start_workflow(
                _structure_workflow,
                str(effect_database),
                STRUCTURE_INTENT,
            )
        result = handle.get_result(polling_interval_sec=0.01)
        workflow_status = DBOS.get_workflow_status(STRUCTURE_WORKFLOW_ID)
        return {
            "dbos_system_database": str(system_database),
            "effect_count": _effect_count(effect_database),
            "result": result,
            "workflow_id": STRUCTURE_WORKFLOW_ID,
            "workflow_status": getattr(workflow_status, "status", None),
        }
    finally:
        DBOS.destroy()


def _validate_variant(variant: str) -> None:
    if variant not in VARIANTS:
        raise ValueError(f"unknown comparison variant: {variant!r}")


def _initialize_fake_erp(database: Path, variant: str) -> None:
    """Create only the fake ERP's independent durable tables."""
    _validate_variant(variant)
    database.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS effect_attempts ("
            "attempt_id INTEGER PRIMARY KEY, intent_id TEXT NOT NULL)"
        )
        unique_clause = " UNIQUE" if variant == UNIQUE_INTENT_KEY else ""
        connection.execute(
            "CREATE TABLE IF NOT EXISTS purchase_invoice_effects ("
            "effect_id INTEGER PRIMARY KEY, "
            f"intent_id TEXT NOT NULL{unique_clause}, "
            "payload TEXT NOT NULL)"
        )


def _effect_record(row: tuple[object, object, object], *, created: bool) -> dict[str, object]:
    effect_id, intent_id, payload = row
    if (
        not isinstance(effect_id, int)
        or not isinstance(intent_id, str)
        or not isinstance(payload, str)
    ):
        raise RuntimeError("fake ERP returned a malformed effect record")
    return {
        "created": created,
        "effect_id": effect_id,
        "intent_id": intent_id,
        "payload": payload,
    }


def _write_fake_erp_effect(
    fake_erp_database: Path, intent_id: str, variant: str
) -> dict[str, object]:
    """Commit an independent fake ERP effect and return its exact persisted identity."""
    _initialize_fake_erp(fake_erp_database, variant)
    payload = "fake-purchase-invoice"
    with sqlite3.connect(fake_erp_database) as connection:
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("INSERT INTO effect_attempts (intent_id) VALUES (?)", (intent_id,))
        connection.commit()
        if variant == NO_UNIQUE_INTENT_KEY:
            cursor = connection.execute(
                "INSERT INTO purchase_invoice_effects (intent_id, payload) VALUES (?, ?)",
                (intent_id, payload),
            )
            connection.commit()
            effect_id = cursor.lastrowid
            if not isinstance(effect_id, int):
                raise RuntimeError("fake ERP did not return a new row identity")
            row = connection.execute(
                "SELECT effect_id, intent_id, payload FROM purchase_invoice_effects "
                "WHERE effect_id = ?",
                (effect_id,),
            ).fetchone()
            if row is None:
                raise RuntimeError("fake ERP could not reread its committed effect")
            return _effect_record(row, created=True)

        try:
            cursor = connection.execute(
                "INSERT INTO purchase_invoice_effects (intent_id, payload) VALUES (?, ?)",
                (intent_id, payload),
            )
            connection.commit()
            effect_id = cursor.lastrowid
            if not isinstance(effect_id, int):
                raise RuntimeError("fake ERP did not return a new row identity")
            row = connection.execute(
                "SELECT effect_id, intent_id, payload FROM purchase_invoice_effects "
                "WHERE effect_id = ?",
                (effect_id,),
            ).fetchone()
            if row is None:
                raise RuntimeError("fake ERP could not reread its committed effect")
            return _effect_record(row, created=True)
        except sqlite3.IntegrityError as error:
            connection.rollback()
            row = connection.execute(
                "SELECT effect_id, intent_id, payload FROM purchase_invoice_effects "
                "WHERE intent_id = ?",
                (intent_id,),
            ).fetchone()
            if row is None:
                raise RuntimeError("fake ERP unique-key conflict had no original record") from error
            return _effect_record(row, created=False)


@DBOS.step()
def _commit_fake_erp_effect(
    fake_erp_database: str, intent_id: str, variant: str
) -> dict[str, object]:
    """The intentionally at-least-once external step under comparison."""
    result = _write_fake_erp_effect(Path(fake_erp_database), intent_id, variant)
    if os.environ.get(CRASH_AFTER_EFFECT_ENVIRONMENT) == "1":
        # The SQLite effect is committed and closed.  This process exits before
        # DBOS can checkpoint this step's return value.
        os._exit(CRASH_EXIT_CODE)
    return result


@DBOS.workflow()
def _billing_workflow(fake_erp_database: str, intent_id: str, variant: str) -> dict[str, object]:
    return _commit_fake_erp_effect(fake_erp_database, intent_id, variant)


def _snapshot_fake_erp(fake_erp_database: Path) -> dict[str, object]:
    with sqlite3.connect(fake_erp_database) as connection:
        attempts = int(connection.execute("SELECT COUNT(*) FROM effect_attempts").fetchone()[0])
        rows = connection.execute(
            "SELECT effect_id, intent_id, payload FROM purchase_invoice_effects ORDER BY effect_id"
        ).fetchall()
    effects = [_effect_record(row, created=True) for row in rows]
    return {
        "attempt_count": attempts,
        "effects": effects,
        "fake_erp_effect_row_count": len(effects),
    }


def _status_name(workflow_id: str) -> str:
    status = DBOS.get_workflow_status(workflow_id)
    name = getattr(status, "status", None)
    if not isinstance(name, str):
        raise RuntimeError(f"DBOS did not return a workflow status for {workflow_id}")
    return name


def _wait_for_success(workflow_id: str, timeout_seconds: float) -> dict[str, object]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        status = _status_name(workflow_id)
        if status == "SUCCESS":
            result = DBOS.get_result(workflow_id)
            if not isinstance(result, dict):
                raise RuntimeError("DBOS completed with a non-object workflow result")
            return result
        if status not in {"PENDING", "ENQUEUED", "DELAYED"}:
            raise RuntimeError(f"DBOS workflow entered terminal non-success status {status!r}")
        time.sleep(0.02)
    raise TimeoutError(f"DBOS workflow {workflow_id} did not reach SUCCESS")


def _paths(runtime_directory: Path) -> tuple[Path, Path]:
    return runtime_directory / "dbos-system.sqlite", runtime_directory / "fake-erp.sqlite"


def _start_workflow(fake_erp_database: Path, variant: str) -> object:
    with SetWorkflowID(WORKFLOW_ID):
        return DBOS.start_workflow(
            _billing_workflow,
            str(fake_erp_database),
            EXTERNAL_INTENT_ID,
            variant,
        )


def _run_crash_phase(runtime_directory: Path, variant: str) -> None:
    system_database, fake_erp_database = _paths(runtime_directory)
    _initialize_fake_erp(fake_erp_database, variant)
    DBOS(config=_config(system_database))
    DBOS.launch()
    try:
        handle = _start_workflow(fake_erp_database, variant)
        handle.get_result(polling_interval_sec=0.01)
        raise RuntimeError("fault injection did not exit after the fake ERP commit")
    finally:
        DBOS.destroy()


def _run_recovery_phase(runtime_directory: Path, variant: str) -> dict[str, object]:
    system_database, _ = _paths(runtime_directory)
    DBOS(config=_config(system_database))
    DBOS.launch()
    try:
        result = _wait_for_success(WORKFLOW_ID, MAX_CHILD_TIMEOUT_SECONDS - 1)
        return {
            "result": result,
            "workflow_id": WORKFLOW_ID,
            "workflow_status": _status_name(WORKFLOW_ID),
        }
    finally:
        DBOS.destroy()


def _run_replay_phase(runtime_directory: Path, variant: str) -> dict[str, object]:
    system_database, fake_erp_database = _paths(runtime_directory)
    DBOS(config=_config(system_database))
    DBOS.launch()
    try:
        handle = _start_workflow(fake_erp_database, variant)
        result = handle.get_result(polling_interval_sec=0.01)
        if not isinstance(result, dict):
            raise RuntimeError("DBOS replay returned a non-object workflow result")
        return {
            "result": result,
            "workflow_id": WORKFLOW_ID,
            "workflow_status": _status_name(WORKFLOW_ID),
        }
    finally:
        DBOS.destroy()


def _phase_command(phase: str, runtime_directory: Path, variant: str) -> list[str]:
    return [
        sys.executable,
        str(Path(__file__).resolve()),
        phase,
        "--runtime-dir",
        str(runtime_directory),
        "--variant",
        variant,
    ]


def _append_attempt_record(runtime_directory: Path, record: dict[str, object]) -> None:
    """Preserve each owned subprocess attempt, including a failed one, in its runtime."""
    runtime_directory.mkdir(parents=True, exist_ok=True)
    with (runtime_directory / "phase-attempts.jsonl").open("a", encoding="utf-8") as output:
        output.write(json.dumps(record, sort_keys=True) + "\n")


def _run_child(
    phase: str,
    runtime_directory: Path,
    variant: str,
    timeout_seconds: float,
    *,
    crash_after_effect: bool = False,
) -> ChildRun:
    if not 0 < timeout_seconds <= MAX_CHILD_TIMEOUT_SECONDS:
        raise ValueError(f"child timeout must be between 0 and {MAX_CHILD_TIMEOUT_SECONDS} seconds")
    environment = os.environ.copy()
    if crash_after_effect:
        environment[CRASH_AFTER_EFFECT_ENVIRONMENT] = "1"
    else:
        environment.pop(CRASH_AFTER_EFFECT_ENVIRONMENT, None)
    process = subprocess.Popen(
        _phase_command(phase, runtime_directory, variant),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=environment,
    )
    _append_attempt_record(
        runtime_directory,
        {
            "event": "started",
            "phase": phase,
            "pid": process.pid,
            "timeout_seconds": timeout_seconds,
        },
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired as error:
        # This Popen instance was created here.  Do not inspect or terminate
        # unrelated processes when a bounded probe phase fails to finish.
        process.terminate()
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate(timeout=5)
        _append_attempt_record(
            runtime_directory,
            {
                "event": "timed_out",
                "phase": phase,
                "pid": process.pid,
                "returncode": process.returncode,
                "stderr": stderr,
                "stdout": stdout,
                "timeout_seconds": timeout_seconds,
            },
        )
        raise ChildProcessTimeout(
            f"{phase} child pid {process.pid} exceeded {timeout_seconds} seconds"
        ) from error
    child = ChildRun(
        phase=phase,
        pid=process.pid,
        returncode=process.returncode,
        stdout=stdout,
        stderr=stderr,
    )
    _append_attempt_record(
        runtime_directory,
        {
            "event": "finished",
            "phase": child.phase,
            "pid": child.pid,
            "returncode": child.returncode,
            "stderr": child.stderr,
            "stdout": child.stdout,
        },
    )
    return child


def _child_json_output(child: ChildRun) -> dict[str, object]:
    for line in reversed(child.stdout.splitlines()):
        try:
            candidate = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict):
            return candidate
    raise RuntimeError(f"{child.phase} child pid {child.pid} did not emit a JSON result")


def _require_returncode(child: ChildRun, expected: int) -> None:
    if child.returncode != expected:
        raise RuntimeError(
            f"{child.phase} child pid {child.pid} returned {child.returncode}, "
            f"expected {expected}; "
            f"stdout={child.stdout!r}; stderr={child.stderr!r}"
        )


def _returned_identity(result: dict[str, object]) -> int:
    identity = result.get("effect_id")
    if not isinstance(identity, int):
        raise RuntimeError("workflow result did not retain the fake ERP record identity")
    return identity


def run_comparison(
    runtime_directory: Path,
    variant: str,
    *,
    timeout_seconds: float = MAX_CHILD_TIMEOUT_SECONDS,
) -> dict[str, object]:
    """Crash then recover one DBOS workflow against one fake ERP variant."""
    _validate_variant(variant)
    if not 0 < timeout_seconds <= MAX_CHILD_TIMEOUT_SECONDS:
        raise ValueError(f"child timeout must be between 0 and {MAX_CHILD_TIMEOUT_SECONDS} seconds")
    runtime_directory.mkdir(parents=True, exist_ok=True)
    _, fake_erp_database = _paths(runtime_directory)
    _initialize_fake_erp(fake_erp_database, variant)

    crash = _run_child(
        "crash",
        runtime_directory,
        variant,
        timeout_seconds,
        crash_after_effect=True,
    )
    _require_returncode(crash, CRASH_EXIT_CODE)
    after_crash = _snapshot_fake_erp(fake_erp_database)
    if after_crash["fake_erp_effect_row_count"] != 1 or after_crash["attempt_count"] != 1:
        raise RuntimeError(
            "crash phase did not leave exactly one committed fake ERP attempt and effect"
        )

    recovery = _run_child("recover", runtime_directory, variant, timeout_seconds)
    _require_returncode(recovery, 0)
    recovery_output = _child_json_output(recovery)
    recovered_result = recovery_output.get("result")
    if not isinstance(recovered_result, dict):
        raise RuntimeError("recovery phase did not return a workflow result")
    after_recovery = _snapshot_fake_erp(fake_erp_database)

    replay = _run_child("replay", runtime_directory, variant, timeout_seconds)
    _require_returncode(replay, 0)
    replay_output = _child_json_output(replay)
    replay_result = replay_output.get("result")
    if not isinstance(replay_result, dict):
        raise RuntimeError("replay phase did not return a workflow result")
    after_replay = _snapshot_fake_erp(fake_erp_database)
    result = {
        "after_crash": after_crash,
        "after_recovery": {
            **after_recovery,
            "returned_identity": _returned_identity(recovered_result),
            "returned_record": recovered_result,
            "workflow_status": recovery_output.get("workflow_status"),
        },
        "after_replay": {
            **after_replay,
            "returned_identity": _returned_identity(replay_result),
            "returned_record": replay_result,
            "workflow_status": replay_output.get("workflow_status"),
        },
        "children": [crash.record(), recovery.record(), replay.record()],
        "external_intent_id": EXTERNAL_INTENT_ID,
        "phase_attempt_log": str(runtime_directory / "phase-attempts.jsonl"),
        "variant": variant,
        "workflow_id": WORKFLOW_ID,
    }
    (runtime_directory / "comparison-result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def run_all_comparisons(
    runtime_directory: Path, *, timeout_seconds: float = MAX_CHILD_TIMEOUT_SECONDS
) -> dict[str, object]:
    """Run the deliberately non-idempotent and unique-key fake ERP alternatives."""
    runtime_directory.mkdir(parents=True, exist_ok=True)
    results = {
        variant: run_comparison(
            runtime_directory / variant,
            variant,
            timeout_seconds=timeout_seconds,
        )
        for variant in VARIANTS
    }
    outcome: dict[str, object] = {"comparisons": results}
    (runtime_directory / "all-comparisons-result.json").write_text(
        json.dumps(outcome, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return outcome


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("structure", "crash", "recover", "replay", "compare"))
    parser.add_argument("--runtime-dir", required=True, type=Path)
    parser.add_argument("--variant", choices=VARIANTS)
    parser.add_argument("--timeout-seconds", type=float, default=MAX_CHILD_TIMEOUT_SECONDS)
    return parser.parse_args()


def main() -> int:
    arguments = _parse_args()
    if arguments.command == "structure":
        result: dict[str, Any] = run_structure_probe(arguments.runtime_dir)
        print(json.dumps(result, sort_keys=True))
        return 0
    if arguments.command == "compare":
        result = run_all_comparisons(
            arguments.runtime_dir,
            timeout_seconds=arguments.timeout_seconds,
        )
        print(json.dumps(result, sort_keys=True))
        return 0
    if arguments.variant is None:
        raise SystemExit(f"{arguments.command} requires --variant")
    if arguments.command == "crash":
        _run_crash_phase(arguments.runtime_dir, arguments.variant)
        return 0
    if arguments.command == "recover":
        print(
            json.dumps(
                _run_recovery_phase(arguments.runtime_dir, arguments.variant), sort_keys=True
            )
        )
        return 0
    if arguments.command == "replay":
        print(
            json.dumps(_run_replay_phase(arguments.runtime_dir, arguments.variant), sort_keys=True)
        )
        return 0
    raise AssertionError(f"unreachable command: {arguments.command}")


if __name__ == "__main__":
    raise SystemExit(main())
