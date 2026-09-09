"""Specialists are real bounded tasks, not permission-bearing source logos."""

import asyncio
import json
from contextlib import suppress
from types import SimpleNamespace

import pytest

from the_missing_20.adapters.role_task_journal import RoleTaskJournal, TaskUnavailable
from the_missing_20.agents.role_delegation import RoleDelegation, SpecialistFinding, task_activity


def test_task_is_exclusive_and_completed_findings_survive_restart(tmp_path):
    path = tmp_path / "roles.sqlite3"
    journal = RoleTaskJournal(path)
    task, token, cached = journal.claim("case-run-version", "inventory", "Check ACK", now=1)
    assert cached is None
    with pytest.raises(TaskUnavailable, match="active owner"):
        RoleTaskJournal(path).claim("case-run-version", "inventory", "Check ACK", now=2)
    journal.finish(task, token, "COMPLETED", {"evidence_ids": ["PR-1"]})
    same, owner, result = RoleTaskJournal(path).claim("case-run-version", "inventory", "Check ACK")
    assert same == task and owner == "" and result == {"evidence_ids": ["PR-1"]}
    with pytest.raises(TaskUnavailable, match="different task"):
        journal.claim("case-run-version", "inventory", "Release quality")


def test_expired_read_task_can_resume_but_old_owner_cannot_complete(tmp_path):
    journal = RoleTaskJournal(tmp_path / "roles.sqlite3")
    task, old, _ = journal.claim("scope", "quality", "Read QA", now=1)
    same, current, _ = journal.claim("scope", "quality", "Read QA", now=92)
    assert same == task and old != current
    with pytest.raises(TaskUnavailable, match="ownership changed"):
        journal.finish(task, old, "COMPLETED", {"wrong": True})
    journal.finish(task, current, "FAILED")
    with pytest.raises(TaskUnavailable, match="attempt limit"):
        journal.claim("scope", "quality", "Read QA", now=200)


def test_cancellation_is_durable_and_new_scope_does_not_inherit_findings(tmp_path):
    journal = RoleTaskJournal(tmp_path / "roles.sqlite3")
    task, token, _ = journal.claim("scope", "quality", "Read QA")
    journal.finish(task, token, "CANCELLED")
    with pytest.raises(TaskUnavailable, match="cancelled"):
        journal.claim("scope", "quality", "Read QA", now=10**12)
    other, _, cached = journal.claim("new-evidence-version", "quality", "Read QA")
    assert other != task and cached is None


def delegation(tmp_path, *, active=lambda: True):
    payloads = {
        name: {"evidence_ids": [name + ":record"], "case_id": "CASE-1"}
        for name in (
            "read_erp_evidence",
            "read_celigo_evidence",
            "read_airtable_evidence",
            "read_collaboration_evidence",
        )
    }
    events, calls = [], []

    def reader(name):
        def read(query=""):
            calls.append(name)
            return json.dumps(payloads[name])

        return read

    team = RoleDelegation(
        packet={"case_id": "CASE-1", "run_id": "RUN-1", "case_version": 1},
        payloads=payloads,
        factory=SimpleNamespace(create=lambda **kw: None),
        journal=RoleTaskJournal(tmp_path / "roles.sqlite3"),
        reader=reader,
        emit=lambda kind, **kw: events.append({"type": kind, **kw}),
        continue_requested=active,
    )
    return team, events, calls


def test_specialist_has_only_its_sources_and_returns_cited_finding(tmp_path, monkeypatch):
    class FakeAgent:
        def __init__(self, **kwargs):
            self.tools = kwargs["tools"]

        async def invoke_async(self, prompt, **kwargs):
            if "structured_output_model" not in kwargs:
                for tool in self.tools:
                    tool(query="Read the exact lot")
                    tool(query="Check the same admitted snapshot again")
                return None
            return SimpleNamespace(
                structured_output={
                    "summary": "The 8 held units need exact-lot QA evidence.",
                    "evidence_ids": ["read_airtable_evidence:record"],
                    "observations": [
                        {"source": name, "pointer": "/case_id", "value": "CASE-1"}
                        for name in ("read_erp_evidence", "read_airtable_evidence")
                    ],
                    "missing_fact": "Exact-lot approval",
                    "write_performed": False,
                }
            )

    monkeypatch.setattr("strands.Agent", FakeAgent)
    team, events, calls = delegation(tmp_path)
    result = asyncio.run(team.consult("quality", "Check held lot"))
    assert result["status"] == "COMPLETED"
    assert calls == ["read_erp_evidence", "read_airtable_evidence"]
    assert "summary" not in result["finding"]
    assert "missing_fact" not in result["finding"]
    assert result["finding"]["observations"]
    assert [e["type"] for e in events] == [
        "task.delegated",
        "task.started",
        "task.source_read",
        "task.source_cached",
        "task.source_read",
        "task.source_cached",
        "task.completed",
    ]
    cached = asyncio.run(team.consult("quality", "Check held lot"))
    assert cached["status"] == "CACHED" and len(calls) == 2
    assert cached["finding"] == result["finding"]
    assert cached["interpretation_status"] == "WITHHELD"
    _, _, retained = team.journal.claim(team.scope, "quality", "Check held lot")
    assert retained["finding"]["summary"] == "The 8 held units need exact-lot QA evidence."


def test_failure_never_emits_completion(tmp_path, monkeypatch):
    team, events, _ = delegation(tmp_path)

    async def fail(*args):
        raise ValueError("unread evidence")

    monkeypatch.setattr(team, "_investigate", fail)
    with pytest.raises(ValueError, match="unread"):
        asyncio.run(team.consult("inventory", "Check ACK"))
    assert team.failed
    assert events[-1]["type"] == "task.failed"
    assert team.journal.tasks(team.scope)[0]["status"] == "FAILED"


def test_stop_during_work_discards_late_finding(tmp_path, monkeypatch):
    active = [True]
    team, events, _ = delegation(tmp_path, active=lambda: active[0])

    async def finish_after_stop(*args):
        active[0] = False
        return valid_finding("inventory")

    monkeypatch.setattr(team, "_investigate", finish_after_stop)
    with pytest.raises(TaskUnavailable, match="stopped"):
        asyncio.run(team.consult("inventory", "Check ACK"))
    assert events[-1]["type"] == "task.cancelled"
    assert team.journal.tasks(team.scope)[0]["status"] == "CANCELLED"


def test_public_task_labels_do_not_render_model_prose_or_claim_recovery():
    assert task_activity({"type": "task.completed", "role": "quality", "summary": "<script>"}) == (
        "COMPLETE",
        "Quality · Findings returned",
        "Findings await whole-case validation.",
    )
    assert task_activity({"type": "task.executed", "role": "quality"}) is None


def valid_finding(role="quality"):
    from the_missing_20.agents.role_delegation import ROLE_SOURCES

    return SpecialistFinding(
        summary="Unverified opinion",
        evidence_ids=["read_erp_evidence:record"],
        observations=[
            {"source": name, "pointer": "/case_id", "value": "CASE-1"}
            for name in ROLE_SOURCES[role]
        ],
        write_performed=False,
    )


@pytest.mark.parametrize("invalid", ["quantity", "pointer", "source", "citation"])
def test_invalid_observation_cannot_be_completed_or_cached(tmp_path, monkeypatch, invalid):
    team, events, _ = delegation(tmp_path)
    finding = valid_finding()
    if invalid == "quantity":
        finding.observations[0].value = 88
    elif invalid == "pointer":
        finding.observations[0].pointer = "/absent"
    elif invalid == "source":
        finding.observations[0].source = "read_secret"
    else:
        finding.evidence_ids = ["UNREAD"]

    async def investigate(*args):
        return finding

    monkeypatch.setattr(team, "_investigate", investigate)
    with pytest.raises(ValueError):
        asyncio.run(team.consult("quality", "Check held lot"))
    assert team.journal.tasks(team.scope)[0]["status"] == "FAILED"
    assert not any(e["type"] == "task.completed" for e in events)
    assert events[-1]["failure_code"] in {
        "SOURCE_SCOPE",
        "SOURCE_VALUE_MISMATCH",
        "MISSING_SOURCE_PATH",
        "UNREAD_CITATION",
    }


def test_invalid_cached_contract_is_rejected(tmp_path):
    team, events, _ = delegation(tmp_path)
    task, token, _ = team.journal.claim(team.scope, "quality", "Check held lot")
    team.journal.finish(task, token, "COMPLETED", {"summary": "Old unchecked answer"})
    with pytest.raises(KeyError):
        asyncio.run(team.consult("quality", "Check held lot"))
    assert team.failed and not events


def test_scope_excludes_old_contract_and_changed_source_data(tmp_path):
    import hashlib

    team, _, _ = delegation(tmp_path)
    old = hashlib.sha256(
        json.dumps(
            [["CASE-1", "RUN-1", 1], team.payloads], sort_keys=True, allow_nan=False
        ).encode()
    ).hexdigest()
    assert team.scope != old
    changed_payloads = {**team.payloads, "read_erp_evidence": {"sequence": 2}}
    other = RoleDelegation(
        packet={"case_id": "CASE-1", "run_id": "RUN-1", "case_version": 1},
        payloads=changed_payloads,
        factory=team.factory,
        journal=team.journal,
        reader=team.reader,
        emit=team.emit,
        continue_requested=lambda: True,
    )
    assert other.scope != team.scope


@pytest.mark.parametrize("value,valid", [(0.0, True), (0, True), (False, False), ("0", False)])
def test_grounding_accepts_equivalent_numbers_but_not_boolean_or_string(tmp_path, value, valid):
    team, _, _ = delegation(tmp_path)
    team.payloads["read_erp_evidence"]["quantity"] = 0
    finding = valid_finding()
    finding.observations[0].pointer = "/quantity"
    finding.observations[0].value = value
    if valid:
        team._validate("quality", finding)
    else:
        with pytest.raises(ValueError, match="contradicts"):
            team._validate("quality", finding)


@pytest.mark.parametrize("records,count,valid", [([], 0, True), ([{"id": "X"}], 1, True),
                                                   ([{"id": "X"}], 0, False)])
def test_collection_count_is_computed_against_the_original_source(tmp_path, records, count, valid):
    from the_missing_20.agents.role_delegation import SourceObservation

    team, _, _ = delegation(tmp_path)
    team.payloads["read_airtable_evidence"]["records"] = records
    finding = valid_finding()
    finding.observations[1] = SourceObservation(
        source="read_airtable_evidence", pointer="/records", value=count, measurement="COUNT"
    )
    if valid:
        team._validate("quality", finding)
    else:
        with pytest.raises(ValueError, match="contradicts"):
            team._validate("quality", finding)


def test_count_does_not_turn_missing_or_scalar_source_into_an_empty_collection(tmp_path):
    from the_missing_20.agents.role_delegation import SourceObservation

    team, _, _ = delegation(tmp_path)
    finding = valid_finding()
    finding.observations[1] = SourceObservation(
        source="read_airtable_evidence", pointer="/case_id", value=0, measurement="COUNT"
    )
    with pytest.raises(ValueError, match="collection"):
        team._validate("quality", finding)
    finding.observations[1].pointer = "/absent"
    with pytest.raises(ValueError, match="absent"):
        team._validate("quality", finding)


def test_parent_close_settles_inflight_work_and_rejects_late_answer(tmp_path, monkeypatch):
    team, events, _ = delegation(tmp_path)

    async def run():
        started, resume = asyncio.Event(), asyncio.Event()

        async def investigate(*args):
            started.set()
            await resume.wait()
            return valid_finding()

        monkeypatch.setattr(team, "_investigate", investigate)
        pending = asyncio.create_task(team.consult("quality", "Check held lot"))
        await started.wait()
        team.close()
        assert team.journal.tasks(team.scope)[0]["status"] == "FAILED"
        resume.set()
        with pytest.raises(TaskUnavailable):
            await pending

    asyncio.run(run())
    assert [e["type"] for e in events].count("task.failed") == 1
    assert not any(e["type"] == "task.completed" for e in events)


def test_root_failure_always_settles_abandoned_specialist(tmp_path, monkeypatch):
    from the_missing_20.adapters.investigation_case_sources import investigation_packet
    from the_missing_20.agents.live_advisory import AdvisoryUnavailable, run_live_advisory

    started = None
    tasks = []

    async def investigate(*args):
        started.set()
        await asyncio.Event().wait()

    class BrokenRoot:
        def __init__(self, **kwargs):
            self.tools = kwargs["tools"]

        async def invoke_async(self, *args, **kwargs):
            nonlocal started
            started = asyncio.Event()
            tasks.append(asyncio.create_task(self.tools[-2](question="Check ACK")))
            await started.wait()
            raise RuntimeError("parent provider failed")

    monkeypatch.setattr("strands.Agent", BrokenRoot)
    monkeypatch.setattr(RoleDelegation, "_investigate", investigate)
    journal = RoleTaskJournal(tmp_path / "root.sqlite3")
    packet = investigation_packet("uncommitted_receipt")
    packet["run_id"] = "ROOT-FAIL"
    events = []
    with pytest.raises(AdvisoryUnavailable, match="RuntimeError"):
        run_live_advisory(
            packet,
            question="Investigate",
            delegation_journal=journal,
            factory=SimpleNamespace(
                create=lambda **kw: None, ledger=SimpleNamespace(snapshot=lambda: {})
            ),
            on_runtime_event=lambda event: events.append(event),
        )
    scope = next(e["case_scope"] for e in events if e["type"] == "task.delegated")
    assert journal.tasks(scope)[0]["status"] == "FAILED"
    assert any(e["type"] == "task.failed" for e in events)
    assert not any(e["type"] == "task.completed" for e in events)


def test_role_mode_request_envelope_preserves_cost_cap_and_single_default(tmp_path):
    from the_missing_20.adapters.ambiguous_case_platform import AmbiguousCasePlatform
    from the_missing_20.adapters.live_advisory_gateway import DashboardAdvisoryGateway

    single = DashboardAdvisoryGateway(AmbiguousCasePlatform())._factory().config.budget
    team = (
        DashboardAdvisoryGateway(
            AmbiguousCasePlatform(), delegation_journal=RoleTaskJournal(tmp_path / "roles.db")
        )
        ._factory()
        .config.budget
    )
    assert single.max_requests == 16 and team.max_requests == 32
    assert single.incremental_cost_cap_usd == team.incremental_cost_cap_usd
    assert single.whole_run_timeout_seconds == team.whole_run_timeout_seconds


def test_specialist_validation_failure_is_not_misreported_as_provider_outage(tmp_path, monkeypatch):
    from the_missing_20.adapters.investigation_case_sources import investigation_packet
    from the_missing_20.agents.live_advisory import AdvisoryUnavailable, run_live_advisory

    class Root:
        def __init__(self, **kwargs):
            self.tools = kwargs["tools"]

        async def invoke_async(self, *args, **kwargs):
            for reader in self.tools[:6]:
                reader()
            # The real tool loop returns the failed tool result to the model.
            with suppress(ValueError):
                await self.tools[-1](question="Check QA")
            return None

    async def fail(*args):
        raise ValueError("specialist observation contradicts source evidence")

    monkeypatch.setattr("strands.Agent", Root)
    monkeypatch.setattr(RoleDelegation, "_investigate", fail)
    packet = investigation_packet()
    packet["run_id"] = "BAD-SPECIALIST"
    with pytest.raises(AdvisoryUnavailable) as caught:
        run_live_advisory(
            packet, question="Investigate",
            delegation_journal=RoleTaskJournal(tmp_path / "failure.sqlite3"),
            factory=SimpleNamespace(
                create=lambda **kw: None, ledger=SimpleNamespace(snapshot=lambda: {})
            ),
        )
    assert "Specialist" in str(caught.value)
    assert caught.value.diagnostics[0]["stage"] == "specialist"
    assert caught.value.diagnostics[0]["failure"] == "SOURCE_VALUE_MISMATCH"
    assert caught.value.diagnostics[0]["role"] == "quality"


def test_sdk_wrapped_budget_failure_preserves_local_cause(monkeypatch):
    from strands.types.exceptions import EventLoopException

    from the_missing_20.adapters.investigation_case_sources import investigation_packet
    from the_missing_20.agents.live_advisory import AdvisoryUnavailable, run_live_advisory
    from the_missing_20.ports.agent_model import AgentBudgetExceeded

    class Root:
        def __init__(self, **kwargs):
            pass

        async def invoke_async(self, *args, **kwargs):
            try:
                raise AgentBudgetExceeded("local reservation exhausted")
            except AgentBudgetExceeded as cause:
                raise EventLoopException(cause, {}) from cause

    monkeypatch.setattr("strands.Agent", Root)
    with pytest.raises(AdvisoryUnavailable) as caught:
        run_live_advisory(
            investigation_packet(), question="Investigate",
            factory=SimpleNamespace(
                create=lambda **kw: None, ledger=SimpleNamespace(snapshot=lambda: {})
            ),
        )
    assert "AgentBudgetExceeded" in str(caught.value)
    assert caught.value.diagnostics[0]["stage"] == "budget"
    assert caught.value.diagnostics[0]["failure"] == "AgentBudgetExceeded"
