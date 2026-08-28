"""Offline M6 proof of the existing AWS/advisory integration boundary.

This module intentionally has no AWS, Bedrock, Strands, or AgentCore dependency.  It
only validates the reviewed, redacted artifacts already in the repository and composes
an auditable proof describing what those artifacts do and do not prove.  Raw-byte
anchors are part of the contract: rehashing a coordinated mutation cannot promote it.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Any, Final, Literal

from pydantic import Field, model_validator

from the_missing_20.authority_b.lifecycle import (
    LIFECYCLE_ARTIFACT_PATH,
    load_lifecycle_bundle,
)
from the_missing_20.authority_b.models import AuthorityModel, canonical_json

M6_SCHEMA_VERSION: Final[str] = "M6AWSProofBundle/v1"
M6_PROOF_SCHEMA_VERSION: Final[str] = M6_SCHEMA_VERSION
M6_PROOF_ARTIFACT_PATH: Final[str] = "artifacts/aws/m6-proof-bundle-v1.json"
M6_AWS_PROOF_ARTIFACT_PATH: Final[str] = M6_PROOF_ARTIFACT_PATH
M6_GENERATED_AT: Final[str] = "2026-08-27T00:00:00Z"
M6_PROVIDER: Final[str] = "bedrock"
M6_MODEL: Final[str] = "us.amazon.nova-pro-v1:0"
M6_REGION: Final[str] = "us-west-2"
M6_PRIOR_COST_USD: Final[str] = "0.1109336"
M6_INCREMENTAL_COST_USD: Final[str] = "0.014116"
M6_CUMULATIVE_COST_USD: Final[str] = "0.1250496"
M6_COST_CAP_USD: Final[str] = "0.60"

# These are deliberately fixed reviewed bytes, not values copied from the input at
# build time.  A source file must be both present and equal to the reviewed artifact.
M6_APPROVED_SOURCE_DIGESTS: Final[Mapping[str, str]] = {
    "artifacts/golden/golden-v2.json": (
        "d275470cfe5748105630f22d3c08c9c962001cf3957e62735b63d8b406352e69"
    ),
    "artifacts/agent/authority-b-preflight-v1.json": (
        "309cacde4419a6a975bf71e9cad27992e690cbc7810e9bea1e9b1113b2660a52"
    ),
    "artifacts/agent/authority-b-attempt-claim-v1.json": (
        "fa90b8b83089516f5ba2aa48293ebe1833a0490bc92d98f4b2488cd407be29dc"
    ),
    "artifacts/agent/authority-b-failure-v1.json": (
        "6e1d6830f15e34c8183e4be25e6406a755f0e89ddfd7247d7ae57f7d94f32ed0"
    ),
    "artifacts/agent/authority-b-advisory-v1.json": (
        "1d6c6c6cb6e3998d4412407558dbc934d4eb04cf2d54d7ad2655caa7dc77ad53"
    ),
    "artifacts/agent/authority-b-usefulness-proof-v1.json": (
        "f1a961dcafa34fb6936f6b466556720891bebbc4023081a0d00b4d1a12599469"
    ),
    LIFECYCLE_ARTIFACT_PATH: ("670b525cc5bfd9f673fd63de660a44d9db5ae000ce2cecb49fc053cacf4d7512"),
    "fixtures/scenarios/retryable-document-lock.json": (
        "b8c179b3f1becc02bdc41c42f025720f318697b4d31f1ae52a1ad7e36a38d5bf"
    ),
}

M6_APPROVED_SOURCE_SCHEMAS: Final[Mapping[str, str]] = {
    "artifacts/golden/golden-v2.json": "golden-suite/v2",
    "artifacts/agent/authority-b-preflight-v1.json": "authority-b-preflight/v1",
    "artifacts/agent/authority-b-attempt-claim-v1.json": "authority-b-attempt-claim/v1",
    "artifacts/agent/authority-b-failure-v1.json": "authority-b-outcome/v1",
    "artifacts/agent/authority-b-advisory-v1.json": "advisory-investigation/v1",
    "artifacts/agent/authority-b-usefulness-proof-v1.json": "ai-usefulness-proof/v1",
    LIFECYCLE_ARTIFACT_PATH: "AuthorityBLifecycleDemo/v1",
    # The scenario fixture predates explicit JSON schemas.  This value is the proof
    # contract's source classification, not a claim that the fixture declares it.
    "fixtures/scenarios/retryable-document-lock.json": "synthetic-fixture/v1",
}

M6_REQUIRED_SOURCE_PATHS: Final[tuple[str, ...]] = tuple(M6_APPROVED_SOURCE_DIGESTS)
M6_AGENTCORE_CAPABILITIES: Final[tuple[str, ...]] = (
    "agentcore_runtime",
    "agentcore_gateway",
    "agentcore_policy",
    "agentcore_observability",
    "agentcore_deployment",
)


class M6ProofError(ValueError):
    """A source or proof boundary cannot be trusted."""


class M6EvidenceClass(str):
    """String constants kept dependency-light for JSON consumers."""

    PROVEN = "PROVEN"
    SCRIPTED_PROVEN = "SCRIPTED_PROVEN"
    NOT_PROVEN = "NOT_PROVEN"


class M6SourceArtifact(AuthorityModel):
    path: Annotated[str, Field(min_length=1)]
    sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    schema_version: Annotated[str, Field(min_length=1)]
    role: Annotated[str, Field(min_length=1)]
    bytes_count: int = Field(ge=0)


class M6Claim(AuthorityModel):
    claim_id: Annotated[str, Field(min_length=1)]
    statement: Annotated[str, Field(min_length=1)]
    status: Literal["PROVEN", "DEGRADED", "NOT_PROVEN"]
    evidence_class: Literal["PROVEN", "SCRIPTED_PROVEN", "NOT_PROVEN"]
    source_refs: tuple[Annotated[str, Field(min_length=1)], ...] = Field(min_length=1)
    operational_authority: Literal[False] = False
    write_authority: Literal[False] = False

    @model_validator(mode="after")
    def advisory_claims_are_not_authority(self) -> M6Claim:
        lowered = self.statement.lower()
        if self.evidence_class == M6EvidenceClass.NOT_PROVEN and self.status == "PROVEN":
            raise ValueError("not-proven claim cannot have PROVEN status")
        if self.evidence_class == M6EvidenceClass.SCRIPTED_PROVEN and self.status != "PROVEN":
            raise ValueError("scripted proof claim must have PROVEN status")
        if "stable real nova" in lowered and self.status == "PROVEN":
            raise ValueError("stable real Nova usefulness cannot be proven")
        if "agentcore" in lowered and self.status == "PROVEN":
            raise ValueError("AgentCore capability cannot be proven by this bundle")
        if "write authority" in lowered and "no write authority" not in lowered:
            raise ValueError("advisory write authority claim is unsafe")
        return self


class M6Capability(AuthorityModel):
    capability_id: Annotated[str, Field(min_length=1)]
    status: Literal["PROVEN", "SCRIPTED_PROVEN", "DEGRADED", "NOT_PROVEN"]
    evidence_class: Literal["PROVEN", "SCRIPTED_PROVEN", "NOT_PROVEN"]
    scope: Annotated[str, Field(min_length=1)]
    source_refs: tuple[Annotated[str, Field(min_length=1)], ...] = Field(min_length=1)
    operational_authority: Literal[False] = False
    write_authority: Literal[False] = False

    @model_validator(mode="after")
    def capability_boundary(self) -> M6Capability:
        if self.capability_id in M6_AGENTCORE_CAPABILITIES and self.status != "NOT_PROVEN":
            raise ValueError("AgentCore capability must remain NOT_PROVEN")
        if self.capability_id in M6_AGENTCORE_CAPABILITIES and self.evidence_class != "NOT_PROVEN":
            raise ValueError("AgentCore capability evidence must remain NOT_PROVEN")
        if self.capability_id == "stable_real_nova_usefulness" and self.status != "NOT_PROVEN":
            raise ValueError("stable real Nova usefulness must remain NOT_PROVEN")
        if self.capability_id == "real_bedrock_nova_integration" and self.status != "PROVEN":
            raise ValueError("real integration status must be PROVEN")
        return self


class M6LifecycleProof(AuthorityModel):
    status: Literal["PROVEN"] = "PROVEN"
    evidence_class: Literal["PROVEN"] = "PROVEN"
    case_id: Annotated[str, Field(min_length=1)]
    trace_id: Annotated[str, Field(min_length=1)]
    lifecycle_bundle_digest: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    final_case_status: Literal["CLOSED"] = "CLOSED"
    action_count: int = Field(ge=1)
    effect_count: int = Field(ge=1)
    replay_effect_delta: int = Field(ge=0)
    source_refs: tuple[Annotated[str, Field(min_length=1)], ...] = Field(min_length=1)

    @model_validator(mode="after")
    def replay_is_closed(self) -> M6LifecycleProof:
        if self.replay_effect_delta != 0:
            raise ValueError("local lifecycle proof requires zero replay effects")
        return self


class M6ScriptedAdvisoryProof(AuthorityModel):
    status: Literal["SCRIPTED_PROVEN"] = "SCRIPTED_PROVEN"
    evidence_class: Literal["SCRIPTED_PROVEN"] = "SCRIPTED_PROVEN"
    provider: Literal["scripted"] = "scripted"
    profile_count: int = Field(ge=4)
    runs_per_profile: int = Field(ge=2)
    byte_identical: Literal[True] = True
    advisory_only: Literal[True] = True
    source_refs: tuple[Annotated[str, Field(min_length=1)], ...] = Field(min_length=1)


class M6RealIntegrationProof(AuthorityModel):
    status: Literal["PROVEN"] = "PROVEN"
    evidence_class: Literal["PROVEN"] = "PROVEN"
    scope: Literal["CONNECTIVITY_AND_DEGRADATION_OBSERVABILITY"] = (
        "CONNECTIVITY_AND_DEGRADATION_OBSERVABILITY"
    )
    provider: Annotated[str, Field(min_length=1)]
    model: Annotated[str, Field(min_length=1)]
    region: Annotated[str, Field(min_length=1)]
    outcome_status: Literal["DEGRADED"] = "DEGRADED"
    error_code: Annotated[str, Field(min_length=1)]
    request_count: int = Field(ge=1)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    estimated_cost_usd: Annotated[str, Field(pattern=r"^\d+(?:\.\d+)?$")]
    stable_real_usefulness: Literal["NOT_PROVEN"] = "NOT_PROVEN"
    advisory_authority_label: Literal["ADVISORY — NOT AN OPERATIONAL DECISION"] = (
        "ADVISORY — NOT AN OPERATIONAL DECISION"
    )
    operational_authority: Literal[False] = False
    write_authority: Literal[False] = False
    source_refs: tuple[Annotated[str, Field(min_length=1)], ...] = Field(min_length=1)


class M6CostBoundary(AuthorityModel):
    prior_estimated_cost_usd: Annotated[str, Field(pattern=r"^\d+(?:\.\d+)?$")]
    existing_incremental_cost_usd: Annotated[str, Field(pattern=r"^\d+(?:\.\d+)?$")]
    cumulative_estimated_cost_usd: Annotated[str, Field(pattern=r"^\d+(?:\.\d+)?$")]
    hard_cap_usd: Annotated[str, Field(pattern=r"^\d+(?:\.\d+)?$")]
    new_provider_calls: Literal[0] = 0
    new_aws_cost_usd: Literal["0"] = "0"
    source_refs: tuple[Annotated[str, Field(min_length=1)], ...] = Field(min_length=1)


class M6ProofBundle(AuthorityModel):
    schema_version: Literal["M6AWSProofBundle/v1"] = "M6AWSProofBundle/v1"
    generated_at: Literal["2026-08-27T00:00:00Z"] = "2026-08-27T00:00:00Z"
    status: Literal["PASS"] = "PASS"
    acceptance_status: Literal["PASS_WITH_DISCLOSED_AI_DEGRADATION"] = (
        "PASS_WITH_DISCLOSED_AI_DEGRADATION"
    )
    synthetic_only: Literal[True] = True
    advisory_write_authority: Literal[False] = False
    source_artifacts: tuple[M6SourceArtifact, ...] = Field(min_length=len(M6_REQUIRED_SOURCE_PATHS))
    lifecycle: M6LifecycleProof
    scripted_advisory: M6ScriptedAdvisoryProof
    real_provider_integration: M6RealIntegrationProof
    capabilities: tuple[M6Capability, ...] = Field(min_length=1)
    cost_boundary: M6CostBoundary
    claims: tuple[M6Claim, ...] = Field(min_length=1)
    proof_digest: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] = ""

    @model_validator(mode="after")
    def bundle_is_truthful_and_digest_bound(self) -> M6ProofBundle:
        paths = tuple(item.path for item in self.source_artifacts)
        if paths != tuple(sorted(M6_REQUIRED_SOURCE_PATHS)):
            raise ValueError("M6 source artifact ledger is incomplete or unordered")
        for source in self.source_artifacts:
            if source.sha256 != M6_APPROVED_SOURCE_DIGESTS.get(source.path):
                raise ValueError("M6 source artifact digest is not an approved anchor")
            if source.schema_version != M6_APPROVED_SOURCE_SCHEMAS.get(source.path):
                raise ValueError("M6 source artifact schema is not approved")
            if source.bytes_count <= 0:
                raise ValueError("M6 source artifact byte count is invalid")
        refs = set(paths)

        def check_refs(values: tuple[str, ...]) -> None:
            for ref in values:
                if ref.split("#", 1)[0] not in refs:
                    raise ValueError("M6 source reference is outside the approved source ledger")

        for capability in self.capabilities:
            check_refs(capability.source_refs)
        for claim in self.claims:
            check_refs(claim.source_refs)
        check_refs(self.lifecycle.source_refs)
        check_refs(self.scripted_advisory.source_refs)
        check_refs(self.real_provider_integration.source_refs)
        check_refs(self.cost_boundary.source_refs)
        required_capabilities = {
            "local_deterministic_lifecycle",
            "scripted_strands_advisory",
            "real_bedrock_nova_integration",
            "stable_real_nova_usefulness",
            *M6_AGENTCORE_CAPABILITIES,
        }
        observed_capabilities = {item.capability_id for item in self.capabilities}
        if observed_capabilities != required_capabilities:
            raise ValueError("M6 capability disposition is incomplete")
        capability_statuses = {
            item.capability_id: (item.status, item.evidence_class) for item in self.capabilities
        }
        expected_capability_statuses = {
            "local_deterministic_lifecycle": ("PROVEN", "PROVEN"),
            "scripted_strands_advisory": ("SCRIPTED_PROVEN", "SCRIPTED_PROVEN"),
            "real_bedrock_nova_integration": ("PROVEN", "PROVEN"),
            "stable_real_nova_usefulness": ("NOT_PROVEN", "NOT_PROVEN"),
            **{item: ("NOT_PROVEN", "NOT_PROVEN") for item in M6_AGENTCORE_CAPABILITIES},
        }
        if capability_statuses != expected_capability_statuses:
            raise ValueError("M6 capability status is contradictory")
        expected_claim_statuses = {
            "deterministic-lifecycle": ("PROVEN", "PROVEN"),
            "scripted-strands": ("PROVEN", "SCRIPTED_PROVEN"),
            "real-integration": ("DEGRADED", "PROVEN"),
            "real-usefulness": ("NOT_PROVEN", "NOT_PROVEN"),
            "agentcore-capabilities": ("NOT_PROVEN", "NOT_PROVEN"),
            "advisory-boundary": ("PROVEN", "PROVEN"),
        }
        observed_claim_statuses = {
            item.claim_id: (item.status, item.evidence_class) for item in self.claims
        }
        if observed_claim_statuses != expected_claim_statuses:
            raise ValueError("M6 claim status is contradictory")
        expected_claim_statements = {
            "deterministic-lifecycle": (
                "The local deterministic lifecycle is PROVEN through controlled execution, "
                "verification, and replay."
            ),
            "scripted-strands": (
                "The four-profile scripted Strands advisory trace is SCRIPTED_PROVEN and "
                "synthetic only."
            ),
            "real-integration": (
                "Real Bedrock/Nova connectivity and degradation observability are PROVEN as "
                "integration evidence only."
            ),
            "real-usefulness": "Stable real Nova usefulness is NOT_PROVEN.",
            "agentcore-capabilities": (
                "All AgentCore capabilities are NOT_PROVEN by this existing-evidence bundle."
            ),
            "advisory-boundary": "Model output is advisory only and has NO WRITE AUTHORITY.",
        }
        observed_claim_statements = {item.claim_id: item.statement for item in self.claims}
        if observed_claim_statements != expected_claim_statements:
            raise ValueError("M6 claim statement is contradictory")
        expected_claim_refs = {
            "deterministic-lifecycle": (
                LIFECYCLE_ARTIFACT_PATH,
                "fixtures/scenarios/retryable-document-lock.json",
            ),
            "scripted-strands": ("artifacts/golden/golden-v2.json",),
            "real-integration": (
                "artifacts/agent/authority-b-preflight-v1.json",
                "artifacts/agent/authority-b-failure-v1.json",
                "artifacts/agent/authority-b-advisory-v1.json",
            ),
            "real-usefulness": (
                "artifacts/agent/authority-b-usefulness-proof-v1.json",
                "artifacts/golden/golden-v2.json",
            ),
            "agentcore-capabilities": ("artifacts/golden/golden-v2.json",),
            "advisory-boundary": (
                "artifacts/agent/authority-b-advisory-v1.json",
                LIFECYCLE_ARTIFACT_PATH,
            ),
        }
        observed_claim_refs = {item.claim_id: item.source_refs for item in self.claims}
        if observed_claim_refs != expected_claim_refs:
            raise ValueError("M6 claim provenance is contradictory")
        expected_capability_refs = {
            "local_deterministic_lifecycle": (
                LIFECYCLE_ARTIFACT_PATH,
                "fixtures/scenarios/retryable-document-lock.json",
            ),
            "scripted_strands_advisory": ("artifacts/golden/golden-v2.json",),
            "real_bedrock_nova_integration": (
                "artifacts/agent/authority-b-preflight-v1.json",
                "artifacts/agent/authority-b-failure-v1.json",
                "artifacts/agent/authority-b-advisory-v1.json",
            ),
            "stable_real_nova_usefulness": (
                "artifacts/agent/authority-b-usefulness-proof-v1.json",
                "artifacts/golden/golden-v2.json",
            ),
            **{item: ("artifacts/golden/golden-v2.json",) for item in M6_AGENTCORE_CAPABILITIES},
        }
        observed_capability_refs = {
            item.capability_id: item.source_refs for item in self.capabilities
        }
        if observed_capability_refs != expected_capability_refs:
            raise ValueError("M6 capability provenance is contradictory")
        if self.real_provider_integration.stable_real_usefulness != "NOT_PROVEN":
            raise ValueError("real provider usefulness must remain NOT_PROVEN")
        if (
            self.real_provider_integration.provider != M6_PROVIDER
            or self.real_provider_integration.model != M6_MODEL
            or self.real_provider_integration.region != M6_REGION
            or self.real_provider_integration.outcome_status != "DEGRADED"
            or self.real_provider_integration.error_code != "ADVISORY_PROVIDER_FAILURE"
            or self.real_provider_integration.request_count != 6
            or self.real_provider_integration.input_tokens != 11073
            or self.real_provider_integration.output_tokens != 1643
            or self.real_provider_integration.estimated_cost_usd != M6_INCREMENTAL_COST_USD
        ):
            raise ValueError("M6 real integration evidence is contradictory")
        if (
            self.lifecycle.action_count != 2
            or self.lifecycle.effect_count != 2
            or self.scripted_advisory.profile_count != 4
            or self.scripted_advisory.runs_per_profile != 2
        ):
            raise ValueError("M6 proof counts are contradictory")
        if (
            self.cost_boundary.prior_estimated_cost_usd != M6_PRIOR_COST_USD
            or self.cost_boundary.existing_incremental_cost_usd != M6_INCREMENTAL_COST_USD
            or self.cost_boundary.cumulative_estimated_cost_usd != M6_CUMULATIVE_COST_USD
            or self.cost_boundary.hard_cap_usd != M6_COST_CAP_USD
        ):
            raise ValueError("M6 cost boundary is contradictory")
        if self.cost_boundary.new_provider_calls != 0 or self.cost_boundary.new_aws_cost_usd != "0":
            raise ValueError("M6 proof cannot include a new provider call or cost")
        expected = _proof_digest(self)
        if self.proof_digest and self.proof_digest != expected:
            raise ValueError("M6 proof digest mismatch")
        if not self.proof_digest:
            object.__setattr__(self, "proof_digest", expected)
        return self


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _proof_digest(bundle: M6ProofBundle) -> str:
    return hashlib.sha256(
        canonical_json(bundle.model_dump(mode="json", exclude={"proof_digest"})).encode("utf-8")
    ).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise M6ProofError(f"M6 source is missing or malformed: {path}") from exc
    if not isinstance(value, dict):
        raise M6ProofError(f"M6 source must be a JSON object: {path}")
    return value


def _read_approved_sources(repository_root: Path) -> dict[str, dict[str, Any]]:
    values: dict[str, dict[str, Any]] = {}
    for relative_path in sorted(M6_APPROVED_SOURCE_DIGESTS):
        path = repository_root / relative_path
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise M6ProofError(f"M6 approved source is missing: {relative_path}") from exc
        observed = _sha_bytes(raw)
        expected = M6_APPROVED_SOURCE_DIGESTS[relative_path]
        if observed != expected:
            raise M6ProofError(f"M6 source digest mismatch: {relative_path}")
        value = _load_json(path) if relative_path.endswith(".json") else {}
        expected_schema = M6_APPROVED_SOURCE_SCHEMAS[relative_path]
        if (
            relative_path != "fixtures/scenarios/retryable-document-lock.json"
            and value.get("schema_version") != expected_schema
        ):
            raise M6ProofError(f"M6 source schema mismatch: {relative_path}")
        values[relative_path] = value
    return values


def _source_artifacts(repository_root: Path) -> tuple[M6SourceArtifact, ...]:
    roles = {
        "artifacts/golden/golden-v2.json": "DETERMINISTIC_AND_SCRIPTED_GOLDEN",
        "artifacts/agent/authority-b-preflight-v1.json": "REAL_PROVIDER_PREFLIGHT",
        "artifacts/agent/authority-b-attempt-claim-v1.json": "REAL_PROVIDER_ATTEMPT_CLAIM",
        "artifacts/agent/authority-b-failure-v1.json": "REAL_PROVIDER_DEGRADED_OUTCOME",
        "artifacts/agent/authority-b-advisory-v1.json": "REAL_PROVIDER_ADVISORY_STATUS",
        "artifacts/agent/authority-b-usefulness-proof-v1.json": (
            "REAL_PROVIDER_USEFULNESS_DISCLOSURE"
        ),
        LIFECYCLE_ARTIFACT_PATH: "LOCAL_DETERMINISTIC_LIFECYCLE",
        "fixtures/scenarios/retryable-document-lock.json": "SYNTHETIC_FIXTURE",
    }
    result: list[M6SourceArtifact] = []
    for path in sorted(M6_APPROVED_SOURCE_DIGESTS):
        result.append(
            M6SourceArtifact(
                path=path,
                sha256=M6_APPROVED_SOURCE_DIGESTS[path],
                schema_version=M6_APPROVED_SOURCE_SCHEMAS[path],
                role=roles[path],
                bytes_count=(repository_root / path).stat().st_size,
            )
        )
    return tuple(result)


def _validate_golden(golden: Mapping[str, Any]) -> tuple[int, int]:
    if golden.get("status") != "PASS_WITH_DISCLOSED_AI_DEGRADATION":
        raise M6ProofError("Golden v2 promotion status is contradictory")
    safety = golden.get("authority_b_safety_proof")
    if not isinstance(safety, dict) or safety.get("status") != "PASS":
        raise M6ProofError("deterministic Golden safety proof is not PASS")
    counters = safety.get("safety_counters")
    if not isinstance(counters, dict) or any(value != 0 for value in counters.values()):
        raise M6ProofError("Golden safety counters are not all zero")
    scripted = golden.get("scripted_strands_proof")
    if not isinstance(scripted, dict) or scripted.get("status") != "PASS":
        raise M6ProofError("scripted Strands proof is not PASS")
    profiles = scripted.get("profiles")
    if not isinstance(profiles, list) or len(profiles) != 4:
        raise M6ProofError("Golden scripted proof must contain four profiles")
    if scripted.get("runs_per_profile") != 2 or scripted.get("provider") != "scripted":
        raise M6ProofError("Golden scripted proof run contract is invalid")
    for profile in profiles:
        if not isinstance(profile, dict) or profile.get("status") != "PASS":
            raise M6ProofError("Golden scripted profile is not PASS")
        runs = profile.get("scripted_runs", {})
        if not isinstance(runs, dict) or runs.get("byte_identical") is not True:
            raise M6ProofError("Golden scripted profile is not deterministic")
    taxonomy = golden.get("evidence_taxonomy")
    if not isinstance(taxonomy, dict):
        raise M6ProofError("Golden evidence taxonomy is missing")
    if taxonomy.get("deterministic_safety", {}).get("class") != "PROVEN":
        raise M6ProofError("Golden deterministic evidence class is contradictory")
    if taxonomy.get("scripted_synthetic_advisory", {}).get("class") != "SCRIPTED_PROOF":
        raise M6ProofError("Golden scripted evidence class is contradictory")
    real = taxonomy.get("real_nova_integration_and_degradation", {})
    usefulness = taxonomy.get("stable_real_nova_usefulness", {})
    if real.get("class") != "PROVEN" or real.get("status") != "DEGRADED":
        raise M6ProofError("Golden real integration disclosure is contradictory")
    if usefulness.get("class") != "NOT_PROVEN" or usefulness.get("status") != "NOT_PROVEN":
        raise M6ProofError("Golden real usefulness disclosure is contradictory")
    acceptance = golden.get("promotion", {}).get("acceptance", {})
    if acceptance.get("plain_pass_implies_real_usefulness") is not False:
        raise M6ProofError("Golden promotion must not imply real usefulness")
    return len(profiles), int(scripted.get("runs_per_profile", 0))


def _validate_real_provider(
    preflight: Mapping[str, Any],
    claim: Mapping[str, Any],
    failure: Mapping[str, Any],
    advisory: Mapping[str, Any],
    usefulness: Mapping[str, Any],
) -> tuple[int, int, int, str]:
    if preflight.get("status") != "PASS" or preflight.get("provider_calls") != 0:
        raise M6ProofError("provider preflight is missing or records a provider call")
    if preflight.get("compatibility_probe") is not False:
        raise M6ProofError("provider preflight records a compatibility probe")
    if preflight.get("model_id") != M6_MODEL or preflight.get("region") != M6_REGION:
        raise M6ProofError("provider preflight model or region is contradictory")
    if (
        claim.get("state") != "CLAIMED"
        or claim.get("authority_version") != "authority-rebaseline-b/v1"
    ):
        raise M6ProofError("provider attempt claim is not the approved Authority-B claim")
    if claim.get("prior_cost_usd") != M6_PRIOR_COST_USD:
        raise M6ProofError("provider attempt prior cost is contradictory")
    if failure.get("status") != "DEGRADED" or failure.get("provider") != M6_PROVIDER:
        raise M6ProofError("real provider outcome is not the approved degraded record")
    if not isinstance(failure.get("error_code"), str) or not failure.get("error_code"):
        raise M6ProofError("degraded provider outcome has no observable failure")
    if advisory.get("status") != "DEGRADED" or advisory.get("provider") != M6_PROVIDER:
        raise M6ProofError("advisory degraded status is contradictory")
    if advisory.get("model") != M6_MODEL or advisory.get("error_code") != failure.get("error_code"):
        raise M6ProofError("advisory and provider outcome identities differ")
    if advisory.get("authority_label") != "ADVISORY — NOT AN OPERATIONAL DECISION":
        raise M6ProofError("advisory authority label is missing")
    if (
        advisory.get("hypotheses")
        or advisory.get("knowledge_citations")
        or advisory.get("incident_report")
    ):
        raise M6ProofError("degraded provider advisory contains fabricated useful content")
    if usefulness.get("status") != "FAIL" or usefulness.get("evidence_class") != "NOT_PROVEN":
        raise M6ProofError("real provider usefulness is not disclosed as NOT_PROVEN")
    if usefulness.get("operational_authority") is not False:
        raise M6ProofError("provider usefulness artifact grants operational authority")
    usage = failure
    requests = int(usage.get("request_count", 0))
    inputs = int(usage.get("input_tokens", 0))
    outputs = int(usage.get("output_tokens", 0))
    cost = str(usage.get("estimated_cost_usd", ""))
    if requests <= 0 or inputs < 0 or outputs < 0 or cost != M6_INCREMENTAL_COST_USD:
        raise M6ProofError("provider outcome usage or cost is invalid")
    if failure.get("claim_id") != claim.get("claim_id"):
        raise M6ProofError("provider outcome does not match the attempt claim")
    if advisory.get("case_id") != "case-01-retryable-lock-main-path":
        raise M6ProofError("provider advisory case identity is unexpected")
    return requests, inputs, outputs, cost


def _build_capabilities(source_refs: Mapping[str, str]) -> tuple[M6Capability, ...]:
    return (
        M6Capability(
            capability_id="local_deterministic_lifecycle",
            status="PROVEN",
            evidence_class="PROVEN",
            scope="policy, exact quorum, controlled execution, verification, and replay",
            source_refs=(source_refs["lifecycle"], source_refs["fixture"]),
        ),
        M6Capability(
            capability_id="scripted_strands_advisory",
            status="SCRIPTED_PROVEN",
            evidence_class="SCRIPTED_PROVEN",
            scope="synthetic competing hypotheses, gaps, citations, and uncertainty",
            source_refs=(source_refs["golden"],),
        ),
        M6Capability(
            capability_id="real_bedrock_nova_integration",
            status="PROVEN",
            evidence_class="PROVEN",
            scope="connectivity and degraded-outcome observability only",
            source_refs=(source_refs["preflight"], source_refs["failure"], source_refs["advisory"]),
        ),
        M6Capability(
            capability_id="stable_real_nova_usefulness",
            status="NOT_PROVEN",
            evidence_class="NOT_PROVEN",
            scope="no stable real-provider usefulness claim",
            source_refs=(source_refs["usefulness"], source_refs["golden"]),
        ),
        *(
            M6Capability(
                capability_id=capability,
                status="NOT_PROVEN",
                evidence_class="NOT_PROVEN",
                scope="no approved M6 evidence; advisory has no write authority",
                source_refs=(source_refs["golden"],),
            )
            for capability in M6_AGENTCORE_CAPABILITIES
        ),
    )


def _build_claims(source_refs: Mapping[str, str]) -> tuple[M6Claim, ...]:
    return (
        M6Claim(
            claim_id="deterministic-lifecycle",
            statement=(
                "The local deterministic lifecycle is PROVEN through controlled execution, "
                "verification, and replay."
            ),
            status="PROVEN",
            evidence_class="PROVEN",
            source_refs=(source_refs["lifecycle"], source_refs["fixture"]),
        ),
        M6Claim(
            claim_id="scripted-strands",
            statement=(
                "The four-profile scripted Strands advisory trace is SCRIPTED_PROVEN and "
                "synthetic only."
            ),
            status="PROVEN",
            evidence_class="SCRIPTED_PROVEN",
            source_refs=(source_refs["golden"],),
        ),
        M6Claim(
            claim_id="real-integration",
            statement=(
                "Real Bedrock/Nova connectivity and degradation observability are PROVEN as "
                "integration evidence only."
            ),
            status="DEGRADED",
            evidence_class="PROVEN",
            source_refs=(source_refs["preflight"], source_refs["failure"], source_refs["advisory"]),
        ),
        M6Claim(
            claim_id="real-usefulness",
            statement="Stable real Nova usefulness is NOT_PROVEN.",
            status="NOT_PROVEN",
            evidence_class="NOT_PROVEN",
            source_refs=(source_refs["usefulness"], source_refs["golden"]),
        ),
        M6Claim(
            claim_id="agentcore-capabilities",
            statement="All AgentCore capabilities are NOT_PROVEN by this existing-evidence bundle.",
            status="NOT_PROVEN",
            evidence_class="NOT_PROVEN",
            source_refs=(source_refs["golden"],),
        ),
        M6Claim(
            claim_id="advisory-boundary",
            statement="Model output is advisory only and has NO WRITE AUTHORITY.",
            status="PROVEN",
            evidence_class="PROVEN",
            source_refs=(source_refs["advisory"], source_refs["lifecycle"]),
        ),
    )


def build_m6_aws_proof(repository_root: Path) -> M6ProofBundle:
    """Compose the M6 proof from reviewed local artifacts without I/O beyond files."""

    root = repository_root.resolve()
    values = _read_approved_sources(root)
    try:
        lifecycle = load_lifecycle_bundle(root, path=root / LIFECYCLE_ARTIFACT_PATH)
    except (OSError, TypeError, ValueError) as exc:
        raise M6ProofError("deterministic lifecycle source failed validation") from exc
    profile_count, runs_per_profile = _validate_golden(values["artifacts/golden/golden-v2.json"])
    requests, inputs, outputs, cost = _validate_real_provider(
        values["artifacts/agent/authority-b-preflight-v1.json"],
        values["artifacts/agent/authority-b-attempt-claim-v1.json"],
        values["artifacts/agent/authority-b-failure-v1.json"],
        values["artifacts/agent/authority-b-advisory-v1.json"],
        values["artifacts/agent/authority-b-usefulness-proof-v1.json"],
    )
    source_refs = {
        "golden": "artifacts/golden/golden-v2.json",
        "preflight": "artifacts/agent/authority-b-preflight-v1.json",
        "claim": "artifacts/agent/authority-b-attempt-claim-v1.json",
        "failure": "artifacts/agent/authority-b-failure-v1.json",
        "advisory": "artifacts/agent/authority-b-advisory-v1.json",
        "usefulness": "artifacts/agent/authority-b-usefulness-proof-v1.json",
        "lifecycle": LIFECYCLE_ARTIFACT_PATH,
        "fixture": "fixtures/scenarios/retryable-document-lock.json",
    }
    lifecycle_proof = M6LifecycleProof(
        case_id=lifecycle.case_id,
        trace_id=lifecycle.trace_id,
        lifecycle_bundle_digest=lifecycle.bundle_digest,
        action_count=len(lifecycle.actions),
        effect_count=len(lifecycle.effects),
        replay_effect_delta=sum(item.effect_delta for item in lifecycle.replays),
        source_refs=(source_refs["lifecycle"], source_refs["fixture"]),
    )
    scripted_proof = M6ScriptedAdvisoryProof(
        profile_count=profile_count,
        runs_per_profile=runs_per_profile,
        source_refs=(source_refs["golden"],),
    )
    real_proof = M6RealIntegrationProof(
        provider=M6_PROVIDER,
        model=M6_MODEL,
        region=M6_REGION,
        error_code=str(values["artifacts/agent/authority-b-failure-v1.json"]["error_code"]),
        request_count=requests,
        input_tokens=inputs,
        output_tokens=outputs,
        estimated_cost_usd=cost,
        source_refs=(
            source_refs["preflight"],
            source_refs["claim"],
            source_refs["failure"],
            source_refs["advisory"],
            source_refs["usefulness"],
        ),
    )
    cost_boundary = M6CostBoundary(
        prior_estimated_cost_usd=M6_PRIOR_COST_USD,
        existing_incremental_cost_usd=M6_INCREMENTAL_COST_USD,
        cumulative_estimated_cost_usd=M6_CUMULATIVE_COST_USD,
        hard_cap_usd=M6_COST_CAP_USD,
        source_refs=(source_refs["claim"], source_refs["failure"]),
    )
    bundle = M6ProofBundle(
        source_artifacts=_source_artifacts(root),
        lifecycle=lifecycle_proof,
        scripted_advisory=scripted_proof,
        real_provider_integration=real_proof,
        capabilities=_build_capabilities(source_refs),
        cost_boundary=cost_boundary,
        claims=_build_claims(source_refs),
    )
    # File-size metadata is informational but must match the approved bytes.  Build it
    # after the semantic checks so the output remains deterministic.
    object.__setattr__(bundle, "proof_digest", _proof_digest(bundle))
    return bundle


def load_m6_aws_proof(repository_root: Path, *, path: Path | None = None) -> M6ProofBundle:
    """Load a persisted M6 bundle and revalidate its source and proof digest."""

    root = repository_root.resolve()
    _read_approved_sources(root)
    artifact_path = path or root / M6_PROOF_ARTIFACT_PATH
    try:
        bundle = M6ProofBundle.model_validate_json(artifact_path.read_bytes())
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise M6ProofError("M6 proof bundle is missing, malformed, or invalid") from exc
    for source in bundle.source_artifacts:
        if source.sha256 != M6_APPROVED_SOURCE_DIGESTS.get(source.path):
            raise M6ProofError("M6 proof contains an unapproved source digest")
        try:
            actual_size = (root / source.path).stat().st_size
        except OSError as exc:
            raise M6ProofError("M6 proof source is missing") from exc
        if source.bytes_count != actual_size:
            raise M6ProofError("M6 proof source byte count mismatch")
    try:
        lifecycle = load_lifecycle_bundle(root, path=root / LIFECYCLE_ARTIFACT_PATH)
    except (OSError, TypeError, ValueError) as exc:
        raise M6ProofError("M6 lifecycle source failed validation") from exc
    if bundle.lifecycle.lifecycle_bundle_digest != lifecycle.bundle_digest:
        raise M6ProofError("M6 proof lifecycle digest is not bound to the source")
    if (
        bundle.lifecycle.case_id != lifecycle.case_id
        or bundle.lifecycle.trace_id != lifecycle.trace_id
    ):
        raise M6ProofError("M6 proof lifecycle identity is not bound to the source")
    return bundle


def write_m6_aws_proof(repository_root: Path, *, output: Path | None = None) -> M6ProofBundle:
    """Build and persist one canonical M6 proof artifact."""

    root = repository_root.resolve()
    bundle = build_m6_aws_proof(root)
    destination = output or root / M6_PROOF_ARTIFACT_PATH
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(canonical_json(bundle.model_dump(mode="json")) + "\n", encoding="utf-8")
    return bundle


__all__ = [
    "M6_AWS_PROOF_ARTIFACT_PATH",
    "M6_APPROVED_SOURCE_DIGESTS",
    "M6_APPROVED_SOURCE_SCHEMAS",
    "M6_COST_CAP_USD",
    "M6_GENERATED_AT",
    "M6_PROOF_ARTIFACT_PATH",
    "M6_PROOF_SCHEMA_VERSION",
    "M6_SCHEMA_VERSION",
    "M6_AGENTCORE_CAPABILITIES",
    "M6Capability",
    "M6Claim",
    "M6CostBoundary",
    "M6EvidenceClass",
    "M6LifecycleProof",
    "M6ProofBundle",
    "M6ProofError",
    "M6RealIntegrationProof",
    "M6ScriptedAdvisoryProof",
    "M6SourceArtifact",
    "build_m6_aws_proof",
    "load_m6_aws_proof",
    "write_m6_aws_proof",
]
