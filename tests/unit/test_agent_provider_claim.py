from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from the_missing_20.evaluation import agent_golden_runner as golden_module
from the_missing_20.evaluation.agent_golden_runner import (
    BEDROCK_ARTIFACT,
    BEDROCK_ARTIFACT_V8,
    BEDROCK_CLAIM,
    BEDROCK_FAILURE_MANIFEST_V8,
    AgentGoldenRunner,
)
from the_missing_20.evaluation.provider_claim import (
    V7AttemptAlreadyClaimed,
    V9AttemptAlreadyClaimed,
    claim_digest,
    claim_v7_attempt,
    claim_v9_attempt,
    load_v7_attempt_claim,
)
from the_missing_20.ports.agent_model import AgentBudget, AgentBudgetLedger


def test_v7_claim_is_durable_exclusive_and_prose_free(tmp_path: Path) -> None:
    path = tmp_path / "artifacts/agent/claim.json"
    claim = claim_v7_attempt(path)

    assert load_v7_attempt_claim(path) == claim
    assert claim_digest(claim) == claim.claim_digest
    with pytest.raises(V7AttemptAlreadyClaimed):
        claim_v7_attempt(path)

    raw = path.read_text(encoding="utf-8")
    payload = json.loads(raw)
    assert payload["agent_contract_version"] == "agent-contract/v7"
    assert payload["envelope_version"] == "agent-protocol-envelope/v1"
    assert payload["state"] == "CLAIMED"
    assert payload["prior_cost_usd"] == pytest.approx(0.0258576)
    for forbidden in (str(tmp_path), "account", "credential", "password", "MODEL_PROSE"):
        assert forbidden not in raw


def test_concurrent_claimers_have_exactly_one_winner(tmp_path: Path) -> None:
    path = tmp_path / "claim.json"

    def attempt(_index: int) -> object:
        try:
            return claim_v7_attempt(path)
        except V7AttemptAlreadyClaimed:
            return None

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(attempt, range(8)))

    winners = [item for item in results if item is not None]
    assert len(winners) == 1
    assert sum(item is None for item in results) == 7
    assert path.is_file()


def test_incomplete_claim_consumes_the_attempt(tmp_path: Path) -> None:
    path = tmp_path / "claim.json"
    path.write_bytes(b"{")

    with pytest.raises(V7AttemptAlreadyClaimed):
        claim_v7_attempt(path)


@pytest.fixture
def _fake_factory() -> Any:
    budget = AgentBudget()
    return SimpleNamespace(
        ledger=AgentBudgetLedger(budget),
        config=SimpleNamespace(model_id="us.amazon.nova-pro-v1:0"),
    )


def test_existing_claim_refuses_before_provider_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    _fake_factory: Any,
) -> None:
    runner = object.__new__(AgentGoldenRunner)
    runner.repository_root = tmp_path
    claim_v9_attempt(tmp_path / BEDROCK_CLAIM)
    provider_path_calls = 0

    def unexpected_provider_path(*_args: Any, **_kwargs: Any) -> None:
        nonlocal provider_path_calls
        provider_path_calls += 1
        raise AssertionError("a losing launch must not enter the provider path")

    monkeypatch.setattr(runner, "run_profile", unexpected_provider_path)
    with pytest.raises(V9AttemptAlreadyClaimed):
        runner.run_bedrock(_fake_factory)
    assert provider_path_calls == 0


def test_concurrent_launches_have_one_provider_path_winner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    _fake_factory: Any,
) -> None:
    runner_one = object.__new__(AgentGoldenRunner)
    runner_one.repository_root = tmp_path
    runner_two = object.__new__(AgentGoldenRunner)
    runner_two.repository_root = tmp_path
    provider_path_calls = 0

    def failing_provider_path(*_args: Any, **_kwargs: Any) -> None:
        nonlocal provider_path_calls
        provider_path_calls += 1
        raise RuntimeError("synthetic provider path failure")

    monkeypatch.setattr(runner_one, "run_profile", failing_provider_path)
    monkeypatch.setattr(runner_two, "run_profile", failing_provider_path)
    monkeypatch.setattr(golden_module, "_agent_profile_manifest", lambda *_args: object())

    def launch(runner: AgentGoldenRunner) -> BaseException | None:
        try:
            runner.run_bedrock(_fake_factory)
        except BaseException as error:
            return error
        return None

    with ThreadPoolExecutor(max_workers=2) as executor:
        errors = list(executor.map(launch, (runner_one, runner_two)))

    assert provider_path_calls == 1
    assert sum(isinstance(error, V9AttemptAlreadyClaimed) for error in errors) == 1
    assert sum(type(error) is RuntimeError for error in errors) == 1


def test_v6_failure_artifact_path_is_not_replaced(tmp_path: Path) -> None:
    legacy_failure = tmp_path / "artifacts/agent/bedrock-failure-manifest-v2.json"
    legacy_failure.parent.mkdir(parents=True)
    legacy_bytes = b'{"schema_version":"agent-failure/v2","historical":true}\n'
    legacy_failure.write_bytes(legacy_bytes)

    assert BEDROCK_FAILURE_MANIFEST_V8 == "artifacts/agent/bedrock-failure-manifest-v4.json"
    assert BEDROCK_ARTIFACT_V8 == "artifacts/agent/bedrock-smoke-v4.json"
    assert legacy_failure.read_bytes() == legacy_bytes


def test_golden_accepts_only_matching_v9_pass_artifact(tmp_path: Path) -> None:
    runner = object.__new__(AgentGoldenRunner)
    runner.repository_root = tmp_path
    fixed_versions = {"agent_contract_version": "agent-contract/v9"}
    runner._version_digests = lambda: fixed_versions  # type: ignore[method-assign]
    claim = claim_v9_attempt(tmp_path / BEDROCK_CLAIM)

    v2_path = tmp_path / "artifacts/agent/bedrock-smoke-v2.json"
    v2_path.parent.mkdir(parents=True, exist_ok=True)
    v2_path.write_text(
        '{"schema_version":"bedrock-smoke/v2","status":"PASS"}',
        encoding="utf-8",
    )
    assert runner._bedrock_proof()["status"] == "NOT_RUN"

    profile = {
        "status": "PASS",
        "agent_run": {
            "evaluator_citation_closure": {
                "schema_version": "evaluator-citation-closure/v1",
                "all_synthesis_claims_validated": True,
                "all_admitted_evidence_covered": True,
            },
            "evaluator_source_coverage": {
                "schema_version": "evaluator-source-coverage/v2",
                "all_required_sources_validated": True,
                "all_required_sources_available": True,
            },
        },
    }
    proof = {
        "schema_version": "bedrock-smoke/v5",
        "status": "PASS",
        "profile_count": 4,
        "profiles": [profile] * 4,
        "attempt_claim": claim.model_dump(mode="json"),
        "attempt_claim_id": claim.claim_id,
        "attempt_claim_digest": claim_digest(claim),
        "version_digests": fixed_versions,
    }
    v4_path = tmp_path / BEDROCK_ARTIFACT
    v4_path.parent.mkdir(parents=True, exist_ok=True)
    v4_path.write_text(json.dumps(proof), encoding="utf-8")
    assert runner._bedrock_proof()["status"] == "PASS"

    tampered = {**proof, "attempt_claim_id": "tampered"}
    v4_path.write_text(json.dumps(tampered), encoding="utf-8")
    assert runner._bedrock_proof()["status"] == "NOT_RUN"
