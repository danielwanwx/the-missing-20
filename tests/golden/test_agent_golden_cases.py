from __future__ import annotations

import hashlib
import json
from pathlib import Path
from shutil import copyfile

from the_missing_20.authority_b.provider import AUTHORITY_B_CLAIM_PATH, AUTHORITY_B_FAILURE_PATH
from the_missing_20.evaluation.agent_golden_runner import (
    AUTHORITY_B_ADVISORY_ARTIFACT,
    AUTHORITY_B_USEFULNESS_ARTIFACT,
    AgentGoldenRunner,
)

ROOT = Path(__file__).resolve().parents[2]


def test_scripted_agent_profiles_prove_business_loop(tmp_path: Path) -> None:
    result = AgentGoldenRunner(ROOT, tmp_path / "artifacts").run_scripted()

    assert result["status"] == "PASS"
    assert result["profile_count"] == 4
    assert result["runs_per_profile"] == 2
    assert result["byte_identical"] is True
    assert all(profile["status"] == "PASS" for profile in result["profiles"])
    assert all(profile["scripted_runs"]["byte_identical"] for profile in result["profiles"])
    assert result["profiles"][0]["workflow"]["links"]["replayed_case_status"] == "CLOSED"
    assert all(
        profile["workflow"]["forbidden_grants"] == 0
        and profile["workflow"]["forbidden_effects"] == 0
        for profile in result["profiles"]
    )


def test_golden_v2_composer_is_offline_and_discloses_real_degradation(tmp_path: Path) -> None:
    result = AgentGoldenRunner(ROOT, tmp_path / "artifacts").run_all()

    assert result["safety_regression"]["status"] == "PASS"
    assert result["scripted_strands_proof"]["status"] == "PASS"
    assert result["bedrock_model_proof"]["status"] == "NOT_RUN"
    assert result["version_matrix"]["agent_contract_version"] == "agent-contract/v9"
    assert result["version_matrix"]["envelope_version"] == "agent-protocol-envelope/v1"
    assert (
        result["scripted_strands_proof"]["profiles"][0]["agent_run"]["trace"]["schema_digest"]
        == result["version_matrix"]["schema_digest"]
    )
    assert result["status"] == "PASS_WITH_DISCLOSED_AI_DEGRADATION"
    assert result["promotion"]["promotable"] is True
    assert result["promotion"]["status"] == "PASS_WITH_DISCLOSED_AI_DEGRADATION"
    assert result["authority_b_real_proof"]["status"] == "NOT_PROVEN"
    assert result["authority_b_real_proof"]["outcome_status"] == "DEGRADED"
    assert result["authority_b_real_proof"]["usefulness_status"] == "FAIL"
    assert result["ai_usefulness_proof"]["status"] == "NOT_PROVEN"
    assert result["ai_usefulness_proof"]["evidence_class"] == "NOT_PROVEN"
    assert result["evidence_taxonomy"]["scripted_synthetic_advisory"]["class"] == ("SCRIPTED_PROOF")
    assert result["evidence_taxonomy"]["real_nova_integration_and_degradation"]["class"] == (
        "PROVEN"
    )
    assert result["evidence_taxonomy"]["stable_real_nova_usefulness"]["status"] == ("NOT_PROVEN")


def _copy_degradation_artifacts(tmp_path: Path, *, advisory: bool = True) -> Path:
    repository = tmp_path / "repository"
    for relative in (AUTHORITY_B_CLAIM_PATH, AUTHORITY_B_FAILURE_PATH):
        destination = repository / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        copyfile(ROOT / relative, destination)
    if advisory:
        destination = repository / AUTHORITY_B_ADVISORY_ARTIFACT
        destination.parent.mkdir(parents=True, exist_ok=True)
        copyfile(ROOT / AUTHORITY_B_ADVISORY_ARTIFACT, destination)
        destination = repository / AUTHORITY_B_USEFULNESS_ARTIFACT
        destination.parent.mkdir(parents=True, exist_ok=True)
        copyfile(ROOT / AUTHORITY_B_USEFULNESS_ARTIFACT, destination)
    return repository


def _artifact_only_runner(repository: Path) -> AgentGoldenRunner:
    runner = object.__new__(AgentGoldenRunner)
    runner.repository_root = repository
    return runner


def test_degradation_promotion_fails_closed_when_required_advisory_is_missing(
    tmp_path: Path,
) -> None:
    runner = _artifact_only_runner(_copy_degradation_artifacts(tmp_path, advisory=False))

    proof = runner._authority_b_proof()

    assert proof["evidence_valid"] is False
    assert proof["status"] == "NOT_RUN"


def test_degradation_promotion_fails_closed_when_outcome_claim_is_tampered(
    tmp_path: Path,
) -> None:
    repository = _copy_degradation_artifacts(tmp_path)
    outcome_path = repository / AUTHORITY_B_FAILURE_PATH
    outcome = json.loads(outcome_path.read_text(encoding="utf-8"))
    outcome["claim_id"] = "tampered-claim"
    outcome_path.write_text(json.dumps(outcome), encoding="utf-8")
    runner = _artifact_only_runner(repository)

    proof = runner._authority_b_proof()

    assert proof["evidence_valid"] is False
    assert proof["status"] == "NOT_RUN"


def test_coordinated_rewrite_and_self_rehash_fails_frozen_anchor(
    tmp_path: Path,
) -> None:
    repository = _copy_degradation_artifacts(tmp_path)
    claim_path = repository / AUTHORITY_B_CLAIM_PATH
    claim = json.loads(claim_path.read_text(encoding="utf-8"))
    claim["created_at"] = "2026-08-27T22:31:20Z"
    unsigned = dict(claim)
    unsigned.pop("claim_digest")
    claim["claim_digest"] = hashlib.sha256(
        (json.dumps(unsigned, sort_keys=True, separators=(",", ":")) + "\n").encode()
    ).hexdigest()
    claim_path.write_text(json.dumps(claim), encoding="utf-8")
    for relative in (
        AUTHORITY_B_FAILURE_PATH,
        AUTHORITY_B_ADVISORY_ARTIFACT,
        AUTHORITY_B_USEFULNESS_ARTIFACT,
    ):
        path = repository / relative
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["estimated_cost_usd"] = (
            "0.014117" if relative == AUTHORITY_B_FAILURE_PATH else 0.014117
        )
        path.write_text(json.dumps(payload), encoding="utf-8")

    proof = _artifact_only_runner(repository)._authority_b_proof()

    assert proof["evidence_valid"] is False
    assert proof["status"] == "NOT_RUN"
    assert "frozen source anchor" in proof["reason"]
