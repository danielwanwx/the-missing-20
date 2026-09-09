"""Real coordinator + durable dispatch; model/provider doubles are explicit."""

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from test_agent_platform import ROOT, _erp, _Reader, _saas

from scripts.decision_workspace_server import DecisionWorkspaceServer
from the_missing_20.adapters.agent_platform import AgentPlatform
from the_missing_20.adapters.automatic_investigation import AutomaticInvestigation


class Advisory:
    def __init__(self):
        self.calls = []

    def investigate(self, projection):
        self.calls.append(projection)
        return {"status": "AGENT_UNAVAILABLE", "tool_calls": []}


def test_legacy_dispatch_journal_migrates_without_losing_attempt(tmp_path):
    path = tmp_path / "dispatch.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE attempts(case_id TEXT, digest TEXT, status TEXT, "
            "run_id TEXT, created_at TEXT, PRIMARY KEY(case_id,digest))"
        )
        db.execute("INSERT INTO attempts VALUES ('case','digest','VERIFIED','run-1','2026-09-08')")
    source, platform, advisory, dispatch = setup(tmp_path)
    with dispatch._db() as db:
        row = dict(db.execute("SELECT * FROM attempts WHERE case_id='case'").fetchone())
    assert row == {
        "case_id": "case",
        "digest": "digest",
        "status": "VERIFIED",
        "run_id": "run-1",
        "created_at": "2026-09-08",
        "attempt": 1,
    }


def setup(tmp_path, *, healthy=False):
    source = _Reader(_erp(quality_hold=not healthy))
    platform = AgentPlatform(source, _Reader(_saas()), state_path=tmp_path / "platform.json")
    advisory = Advisory()
    dispatcher = AutomaticInvestigation(tmp_path / "dispatch.sqlite3", platform, advisory)
    dispatcher.configure(True, source.payload["case_id"], "test operator")
    return source, platform, advisory, dispatcher


def test_normal_partial_receipts_do_not_trigger_but_quality_change_does(tmp_path):
    source, platform, advisory, dispatch = setup(tmp_path, healthy=True)
    source.payload["documents"][0]["quantity"] = 40
    dispatch.tick()
    assert advisory.calls == []  # Ordered 40, received 20 is not an exception.
    assert dispatch.current()["status"] == "WATCHING"
    source.payload["documents"][1]["rejected"] = 8
    dispatch.tick()
    assert len(advisory.calls) == 1
    assert platform.current()["execution"]["available"] is False


def test_duplicate_ticks_and_restart_do_not_repeat_same_paid_request(tmp_path):
    source, platform, advisory, dispatch = setup(tmp_path)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: dispatch.tick(), range(8)))
    assert len(advisory.calls) == 1
    restarted = AutomaticInvestigation(dispatch.database, platform, advisory)
    restarted.tick()
    assert len(advisory.calls) == 1
    source.payload["documents"][1]["rejected"] = 9
    restarted.tick()
    assert len(advisory.calls) == 2


def test_unavailable_source_waits_without_spending_and_recovers(tmp_path):
    source, _, advisory, dispatch = setup(tmp_path)
    source.payload["status"] = "DEGRADED"
    dispatch.tick()
    assert dispatch.current()["status"] == "WAITING_SOURCE"
    assert advisory.calls == []
    source.payload["status"] = "CONNECTED"
    dispatch.tick()
    assert len(advisory.calls) == 1


def test_case_change_revokes_permission(tmp_path):
    source, _, advisory, dispatch = setup(tmp_path)
    source.payload["case_id"] = "different-case"
    dispatch.tick()
    assert not dispatch.current()["enabled"]
    assert dispatch.current()["status"] == "CASE_CHANGED"
    assert advisory.calls == []


def test_pause_during_model_cannot_be_undone_by_late_result_or_source_change(tmp_path):
    source, platform, _, dispatch = setup(tmp_path)
    entered, release = Event(), Event()

    class Slow:
        def investigate(self, projection):
            entered.set()
            assert release.wait(5)
            return {"status": "COMPLETE", "tool_calls": []}

    dispatch.advisory = Slow()
    worker = Thread(target=dispatch.tick)
    worker.start()
    assert entered.wait(5)
    dispatch.pause()
    assert not dispatch.current()["enabled"]
    release.set()
    worker.join(5)
    assert not worker.is_alive()
    source.payload["documents"][1]["rejected"] = 9
    dispatch.tick()
    assert platform.current()["agent_run"]["state"] == "STOPPED"
    assert platform.current()["execution"]["available"] is False
    assert dispatch.current()["last_attempt"]["status"] == "CANCELLED"


def test_interrupted_attempt_requires_human_attention_not_restart_replay(tmp_path):
    source, platform, advisory, dispatch = setup(tmp_path)
    digest = platform.automatic_investigation_observation()["digest"]
    platform.claim_changed_diagnosis(source.payload["case_id"], digest)
    with dispatch._db() as db:
        db.execute(
            "INSERT INTO attempts(case_id,digest,status) VALUES (?,?,'RUNNING')",
            (source.payload["case_id"], digest),
        )
    platform = AgentPlatform(source, _Reader(_saas()), state_path=tmp_path / "platform.json")
    reopened = AutomaticInvestigation(dispatch.database, platform, advisory)
    reopened.tick()
    assert reopened.current()["status"] == "INTERRUPTED"
    assert advisory.calls == []
    reopened.configure(True, source.payload["case_id"], "operator")
    reopened.tick()
    reopened.tick()
    assert len(advisory.calls) == 1
    assert reopened.current()["last_attempt"]["attempt"] == 2
    with reopened._db() as db:
        assert (
            db.execute("SELECT status FROM attempts WHERE attempt=1").fetchone()[0] == "INTERRUPTED"
        )


def test_validated_plan_immediately_shows_human_review_not_watching(tmp_path):
    _, platform, _, dispatch = setup(tmp_path)
    platform.finish_automatic_investigation = lambda result, run_id: "PLAN_READY"
    dispatch.tick()
    assert dispatch.current()["status"] == "AWAITING_REVIEW"


def test_verified_result_does_not_reintroduce_manager_review(tmp_path):
    _, platform, _, _ = setup(tmp_path)
    digest = platform.automatic_investigation_observation()["digest"]
    platform._agent_run["state"] = "VERIFIED"
    platform._model_gate = {"status": "VALIDATED", "evidence_digest": digest}
    assert platform.automatic_investigation_observation()["status"] == "WATCHING"


def test_http_control_starts_worker_and_pause_is_persisted(tmp_path):
    platform = AgentPlatform(_Reader(_erp()), _Reader(_saas()))
    observed = Event()
    advisory = Advisory()
    invoke = advisory.investigate

    def signal(projection):
        result = invoke(projection)
        observed.set()
        return result

    advisory.investigate = signal
    server = DecisionWorkspaceServer(
        ("127.0.0.1", 0),
        ROOT,
        runtime_directory=tmp_path,
        agent_platform=platform,
        agent_advisory=advisory,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}/api/v1/agent-platform"

    def configure(enabled, case_id=None, **headers):
        return urlopen(
            Request(
                base + "/automation",
                method="POST",
                headers={"Content-Type": "application/json", **headers},
                data=json.dumps(
                    {
                        "enabled": enabled,
                        "case_id": case_id or _erp()["case_id"],
                        "operator_id": "test operator",
                    }
                ).encode(),
            ),
            timeout=5,
        )

    try:
        with pytest.raises(HTTPError) as wrong_case:
            configure(True, case_id="other-case")
        assert wrong_case.value.code == 400
        with pytest.raises(HTTPError) as foreign_origin:
            configure(True, Origin="https://example.com")
        assert foreign_origin.value.code == 403
        with configure(True) as response:
            assert json.load(response)["enabled"] is True
        assert observed.wait(5)
        with configure(False) as response:
            assert json.load(response)["enabled"] is False
        with urlopen(base, timeout=5) as response:
            projection = json.load(response)
        assert projection["automation"]["status"] == "PAUSED"
        assert projection["execution"]["available"] is False
        assert len(advisory.calls) == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)


def test_run_budget_is_persistent_and_not_reset_by_repeated_enable(tmp_path):
    source, _, advisory, dispatch = setup(tmp_path)
    for quantity in range(8, 18):
        source.payload["documents"][1]["rejected"] = quantity
        dispatch.tick()
    assert len(advisory.calls) == 8
    assert dispatch.current()["status"] == "BUDGET_EXHAUSTED"
    assert not dispatch.current()["enabled"]
    dispatch.configure(False, source.payload["case_id"], "operator")
    dispatch.configure(True, source.payload["case_id"], "operator")
    dispatch.tick()
    assert len(advisory.calls) == 8
    assert dispatch.current()["remaining_runs"] == 0


def test_model_claiming_success_is_not_recorded_as_validated_success(tmp_path):
    _, platform, advisory, dispatch = setup(tmp_path)
    advisory.investigate = lambda _: {"status": "COMPLETE", "tool_calls": []}
    dispatch.tick()
    assert dispatch.current()["last_attempt"]["status"] == "BLOCKED"
    assert platform.current()["execution"]["available"] is False


def test_pause_immediately_before_completion_is_authoritatively_cancelled(tmp_path):
    _, platform, advisory, dispatch = setup(tmp_path)
    advisory.investigate = lambda _: {"status": "COMPLETE", "tool_calls": []}
    finish = platform.finish_automatic_investigation

    def pause_then_finish(result, *, run_id):
        dispatch.pause()
        return finish(result, run_id=run_id)

    platform.finish_automatic_investigation = pause_then_finish
    dispatch.tick()
    assert dispatch.current()["last_attempt"]["status"] == "CANCELLED"


def test_manual_pending_run_not_duplicated(tmp_path):
    _, platform, advisory, dispatch = setup(tmp_path)
    platform.claim_diagnosis()
    dispatch.tick()
    assert advisory.calls == []
    assert dispatch.current()["status"] == "BUSY"


def test_source_changes_between_observation_and_claim_do_not_dispatch(tmp_path):
    source, platform, advisory, dispatch = setup(tmp_path)
    original = platform.claim_changed_diagnosis

    def change(case_id, digest):
        source.payload["status"] = "DEGRADED"
        return original(case_id, digest)

    platform.claim_changed_diagnosis = change
    dispatch.tick()
    assert advisory.calls == []
    assert dispatch.current()["remaining_runs"] == 8
