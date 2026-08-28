"""Contract proof for durable public-session crash recovery."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest

from the_missing_20.authority_b.executor import (  # type: ignore[attr-defined]
    AuthorityBControlledExecutor,
    SimulatedPersistenceFault,
)
from the_missing_20.competition.package import M7PackageError
from the_missing_20.experiment.events import PublicEventType
from the_missing_20.experiment.session import ExperimentSession

ROOT = Path(__file__).resolve().parents[2]


def _copy_package_inputs(destination: Path) -> None:
    for directory in (
        "artifacts",
        "fixtures",
        "workspace",
        "docs",
        "scripts",
        "src",
        "tests",
    ):
        shutil.copytree(ROOT / directory, destination / directory)


@pytest.mark.parametrize("failure_flag", ("fail_after_reservation", "fail_after_enterprise_commit"))
def test_exact_retry_resumes_the_same_effect_after_persistence_fault(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_flag: str,
) -> None:
    session = ExperimentSession(ROOT, data_directory=tmp_path / "session")
    prepared = session.decision_command(
        {
            "command": "prepare_recovery",
            "tool": "restart_receipt_message",
            "idempotency_key": f"contract:{failure_flag}:prepare",
        }
    )
    intent_id = prepared["approval"]["intent_id"]
    for principal, suffix in (
        ("integration-operator", "operator"),
        ("ap-approver", "ap"),
    ):
        session.decision_command(
            {
                "command": "approve",
                "intent_id": intent_id,
                "principal_id": principal,
                "idempotency_key": f"contract:{failure_flag}:{suffix}",
            }
        )

    original_execute = AuthorityBControlledExecutor.execute
    calls = 0

    def fail_once(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        if calls == 1:
            kwargs[failure_flag] = True
        return original_execute(*args, **kwargs)

    monkeypatch.setattr(AuthorityBControlledExecutor, "execute", fail_once)
    execute_key = f"contract:{failure_flag}:execute"
    with pytest.raises(SimulatedPersistenceFault):
        session.decision_command(
            {
                "command": "execute",
                "intent_id": intent_id,
                "idempotency_key": execute_key,
            }
        )

    retried = session.decision_command(
        {
            "command": "execute",
            "intent_id": intent_id,
            "idempotency_key": execute_key,
        }
    )
    started = [
        event
        for event in session.events_since()
        if event.event_type is PublicEventType.EXECUTION_STARTED
    ]

    assert calls == 3  # resume once, then invoke the replay proof once
    assert started and len(started) == 1
    assert started[0].case_version == prepared["case_version"]
    assert retried["execution"]["verified"] is True
    assert retried["execution"]["replay_effect_delta"] == 0
    assert len(retried["execution"]["effects"]) == 1
    assert len(session.enterprise.read_snapshot().business_effects) == 1


def test_m7_runtime_proof_fails_closed_when_chat_replays_read_tools(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A chat retry that reruns the harness cannot make M7 ready."""

    import the_missing_20.competition.package as package

    _copy_package_inputs(tmp_path)
    monkeypatch.setattr(package, "_validate_browser_smoke", lambda _value: None)
    original_chat_command = ExperimentSession.chat_command
    calls = 0

    def regressed_chat_command(
        session: ExperimentSession,
        question: str,
        *,
        idempotency_key: str,
    ) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        session._run_read_only_harness(operation_namespace=f"regression:{idempotency_key}:{calls}")
        return original_chat_command(
            session,
            question,
            idempotency_key=idempotency_key,
        )

    monkeypatch.setattr(ExperimentSession, "chat_command", regressed_chat_command)
    with pytest.raises(M7PackageError, match="chat exact-retry proof"):
        package.build_private_audit(tmp_path)


def test_m7_runtime_proof_fails_closed_when_reload_uses_new_execution_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A retry that reuses the post-crash case version cannot make M7 ready."""

    import the_missing_20.competition.package as package

    _copy_package_inputs(tmp_path)
    monkeypatch.setattr(package, "_validate_browser_smoke", lambda _value: None)

    def regressed_execution_marker(
        session: ExperimentSession,
        *,
        intent_id: str,
        execution_id: str,
        tool: str,
        slug: str,
    ) -> Any:
        return session._append(
            PublicEventType.EXECUTION_STARTED,
            actor="controlled-executor",
            status="RUNNING",
            case_version=session._current_case_version(),
            correlation_id=execution_id,
            idempotency_key=f"experiment:execution-started:{slug}",
            payload={"intent_id": intent_id, "execution_id": execution_id, "tool": tool},
        )

    monkeypatch.setattr(
        ExperimentSession,
        "_append_execution_started",
        regressed_execution_marker,
    )
    with pytest.raises(M7PackageError, match="crash proof failed after reload"):
        package.build_private_audit(tmp_path)
