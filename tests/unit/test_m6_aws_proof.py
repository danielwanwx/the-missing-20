from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path

import pytest

from the_missing_20.authority_b.aws_proof import (
    M6_AGENTCORE_NOT_PROVEN_CAPABILITIES,
    M6_AGENTCORE_PROVEN_CAPABILITIES,
    M6_AGENTCORE_RUNTIME_PROOF_PATH,
    M6_APPROVED_SOURCE_DIGESTS,
    M6_PROOF_ARTIFACT_PATH,
    M6ProofBundle,
    M6ProofError,
    build_m6_aws_proof,
    load_m6_aws_proof,
    write_m6_aws_proof,
)
from the_missing_20.authority_b.models import canonical_json

ROOT = Path(__file__).resolve().parents[2]


def _copy_approved_sources(destination: Path) -> None:
    for relative_path in M6_APPROVED_SOURCE_DIGESTS:
        source = ROOT / relative_path
        target = destination / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def _resign_bundle(payload: dict[str, object]) -> None:
    unsigned = {key: value for key, value in payload.items() if key != "proof_digest"}
    payload["proof_digest"] = hashlib.sha256(canonical_json(unsigned).encode("utf-8")).hexdigest()


def test_m6_existing_evidence_proof_is_truthful_and_byte_stable() -> None:
    first = build_m6_aws_proof(ROOT)
    second = build_m6_aws_proof(ROOT)

    assert first == second
    assert first.status == "PASS"
    assert first.acceptance_status == "PASS_WITH_DISCLOSED_AI_DEGRADATION"
    assert first.lifecycle.status == "PROVEN"
    assert first.scripted_advisory.status == "SCRIPTED_PROVEN"
    assert first.real_provider_integration.status == "PROVEN"
    assert first.real_provider_integration.outcome_status == "DEGRADED"
    assert first.real_provider_integration.stable_real_usefulness == "NOT_PROVEN"
    assert first.agentcore_runtime.status == "PROVEN"
    assert first.agentcore_runtime.runtime_status == "READY"
    assert first.agentcore_runtime.invocation_status == "PROVEN"
    assert first.agentcore_runtime.observability_status == "PROVEN"
    assert first.agentcore_runtime.advisory_status == "PARTIAL"
    assert first.agentcore_runtime.ai_citation_coverage == 1
    assert first.agentcore_runtime.ai_citation_admitted == 5
    assert first.agentcore_runtime.application_authoritative_validation == 5
    assert first.agentcore_runtime.application_authoritative_admitted == 5
    assert first.agentcore_runtime.role_chat_read_only is True
    assert first.agentcore_runtime.deterministic_replay_effect_delta == 0
    assert first.advisory_write_authority is False
    assert first.cost_boundary.prior_estimated_cost_usd == "0.1250496"
    assert first.cost_boundary.existing_incremental_cost_usd == "0.0498648"
    assert first.cost_boundary.runtime_known_token_cost_usd == "0.0489352"
    assert first.cost_boundary.runtime_acceptance_cost_usd == "0.0009296"
    assert first.cost_boundary.cumulative_estimated_cost_usd == "0.1749144"
    assert first.cost_boundary.authority_boundary_chat_cost_status == "NOT_RECORDED_EXCLUDED"
    assert first.cost_boundary.new_provider_calls == 0
    assert first.cost_boundary.new_aws_cost_usd == "0"
    assert {
        item.capability_id
        for item in first.capabilities
        if item.capability_id.startswith("agentcore_")
    } == {
        "agentcore_runtime",
        "agentcore_gateway",
        "agentcore_policy",
        "agentcore_observability",
        "agentcore_deployment",
    }
    capability_status = {
        item.capability_id: item.status
        for item in first.capabilities
        if item.capability_id.startswith("agentcore_")
    }
    assert capability_status == {
        **dict.fromkeys(M6_AGENTCORE_PROVEN_CAPABILITIES, "PROVEN"),
        **dict.fromkeys(M6_AGENTCORE_NOT_PROVEN_CAPABILITIES, "NOT_PROVEN"),
    }
    assert dict(first.claims[3].model_dump(mode="json"))["status"] == "PARTIAL"
    assert first.proof_digest
    assert canonical_json(first.model_dump(mode="json")) == canonical_json(
        second.model_dump(mode="json")
    )


def test_m6_proof_can_be_written_and_loaded_with_digest_validation(tmp_path: Path) -> None:
    _copy_approved_sources(tmp_path)
    bundle = write_m6_aws_proof(tmp_path)
    loaded = load_m6_aws_proof(tmp_path)

    assert loaded == bundle
    assert (tmp_path / M6_PROOF_ARTIFACT_PATH).read_text(encoding="utf-8").endswith("\n")
    assert (
        M6ProofBundle.model_validate_json((tmp_path / M6_PROOF_ARTIFACT_PATH).read_bytes())
        == bundle
    )


@pytest.mark.parametrize(
    ("relative_path", "mutation"),
    (
        ("artifacts/golden/golden-v2.json", lambda value: value.update({"status": "PASS"})),
        (
            "artifacts/agent/authority-b-failure-v1.json",
            lambda value: value.update({"status": "PASS"}),
        ),
    ),
)
def test_source_mutation_fails_closed_even_when_json_is_valid(
    tmp_path: Path, relative_path: str, mutation: Callable[[dict[str, object]], None]
) -> None:
    _copy_approved_sources(tmp_path)
    path = tmp_path / relative_path
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    mutation(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(M6ProofError, match="digest mismatch"):
        build_m6_aws_proof(tmp_path)


@pytest.mark.parametrize("relative_path", tuple(M6_APPROVED_SOURCE_DIGESTS))
def test_missing_or_malformed_approved_source_fails_closed(
    tmp_path: Path, relative_path: str
) -> None:
    _copy_approved_sources(tmp_path)
    path = tmp_path / relative_path
    path.unlink()
    with pytest.raises(M6ProofError):
        build_m6_aws_proof(tmp_path)

    _copy_approved_sources(tmp_path)
    path = tmp_path / relative_path
    path.write_text("{", encoding="utf-8")
    with pytest.raises(M6ProofError):
        build_m6_aws_proof(tmp_path)


def test_rehashed_bundle_mutation_cannot_promote_contradictory_claim(tmp_path: Path) -> None:
    _copy_approved_sources(tmp_path)
    write_m6_aws_proof(tmp_path)
    path = tmp_path / M6_PROOF_ARTIFACT_PATH
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    claims = payload["claims"]
    assert isinstance(claims, list)
    claims[3]["status"] = "PROVEN"
    _resign_bundle(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(M6ProofError, match="invalid"):
        load_m6_aws_proof(tmp_path)


def test_rehashed_bundle_mutation_cannot_promote_agentcore_or_authority_claim(
    tmp_path: Path,
) -> None:
    _copy_approved_sources(tmp_path)
    write_m6_aws_proof(tmp_path)
    path = tmp_path / M6_PROOF_ARTIFACT_PATH
    baseline = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(baseline, dict)
    for index, field, value in (
        (4, "evidence_class", "PROVEN"),
        (5, "write_authority", True),
    ):
        payload = deepcopy(baseline)
        claims = payload["claims"]
        assert isinstance(claims, list)
        claims[index][field] = value
        _resign_bundle(payload)
        path.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(M6ProofError, match="invalid"):
            load_m6_aws_proof(tmp_path)


def test_rehashed_bundle_mutation_cannot_repoint_claim_provenance(tmp_path: Path) -> None:
    _copy_approved_sources(tmp_path)
    write_m6_aws_proof(tmp_path)
    path = tmp_path / M6_PROOF_ARTIFACT_PATH
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    claims = payload["claims"]
    assert isinstance(claims, list)
    claims[0]["source_refs"] = ["artifacts/golden/golden-v2.json"]
    _resign_bundle(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(M6ProofError, match="invalid"):
        load_m6_aws_proof(tmp_path)


@pytest.mark.parametrize("identity_field", ("case_id", "trace_id"))
def test_rehashed_bundle_mutation_cannot_substitute_lifecycle_identity(
    tmp_path: Path, identity_field: str
) -> None:
    _copy_approved_sources(tmp_path)
    write_m6_aws_proof(tmp_path)
    path = tmp_path / M6_PROOF_ARTIFACT_PATH
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    lifecycle = payload["lifecycle"]
    assert isinstance(lifecycle, dict)
    lifecycle[identity_field] = f"substituted-{identity_field}"
    _resign_bundle(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(M6ProofError, match="identity"):
        load_m6_aws_proof(tmp_path)


def test_proof_loader_requires_persisted_artifact(tmp_path: Path) -> None:
    _copy_approved_sources(tmp_path)
    with pytest.raises(M6ProofError, match="missing"):
        load_m6_aws_proof(tmp_path)


def test_agentcore_runtime_source_is_digest_anchored(tmp_path: Path) -> None:
    _copy_approved_sources(tmp_path)
    path = tmp_path / M6_AGENTCORE_RUNTIME_PROOF_PATH
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    payload["runtime"]["status"] = "STOPPED"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(M6ProofError, match="digest mismatch"):
        build_m6_aws_proof(tmp_path)
