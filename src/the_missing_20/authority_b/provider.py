"""Frozen, exclusive Authority-B advisory proof claim and redacted outcomes."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator

from the_missing_20.authority_b.models import AuthorityModel, EvidenceClass, ProofStatus

AUTHORITY_B_PRIOR_ESTIMATED_COST_USD = Decimal("0.1109336")
AUTHORITY_B_REQUEST_CAP = 12
AUTHORITY_B_INPUT_TOKEN_CAP = 120_000
AUTHORITY_B_OUTPUT_TOKEN_CAP = 18_000
AUTHORITY_B_MAX_OUTPUT_TOKENS_PER_REQUEST = 1_500
AUTHORITY_B_INCREMENTAL_COST_CAP_USD = Decimal("0.1536000")
AUTHORITY_B_CUMULATIVE_COST_CAP_USD = Decimal("0.2645336")
AUTHORITY_B_CLAIM_PATH = Path("artifacts/agent/authority-b-attempt-claim-v1.json")
AUTHORITY_B_SUCCESS_PATH = Path("artifacts/agent/authority-b-success-v1.json")
AUTHORITY_B_FAILURE_PATH = Path("artifacts/agent/authority-b-failure-v1.json")


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode("utf-8")


class AuthorityBAttemptClaim(AuthorityModel):
    schema_version: Literal["authority-b-attempt-claim/v1"] = "authority-b-attempt-claim/v1"
    claim_id: str = Field(min_length=1)
    state: Literal["CLAIMED"] = "CLAIMED"
    created_at: datetime
    authority_version: Literal["authority-rebaseline-b/v1"] = "authority-rebaseline-b/v1"
    prior_cost_usd: Decimal
    request_cap: int = Field(gt=0)
    input_token_cap: int = Field(gt=0)
    output_token_cap: int = Field(gt=0)
    max_output_tokens_per_request: int = Field(gt=0)
    incremental_cost_cap_usd: Decimal
    cumulative_cost_cap_usd: Decimal
    claim_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("created_at", mode="before")
    @classmethod
    def parse_created_at(cls, value: object) -> object:
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value

    @model_validator(mode="after")
    def frozen_caps_and_digest(self) -> AuthorityBAttemptClaim:
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("Authority-B claim timestamp must be timezone-aware")
        expected_values = {
            "prior_cost_usd": AUTHORITY_B_PRIOR_ESTIMATED_COST_USD,
            "request_cap": AUTHORITY_B_REQUEST_CAP,
            "input_token_cap": AUTHORITY_B_INPUT_TOKEN_CAP,
            "output_token_cap": AUTHORITY_B_OUTPUT_TOKEN_CAP,
            "max_output_tokens_per_request": AUTHORITY_B_MAX_OUTPUT_TOKENS_PER_REQUEST,
            "incremental_cost_cap_usd": AUTHORITY_B_INCREMENTAL_COST_CAP_USD,
            "cumulative_cost_cap_usd": AUTHORITY_B_CUMULATIVE_COST_CAP_USD,
        }
        for field, expected in expected_values.items():
            if getattr(self, field) != expected:
                raise ValueError(f"Authority-B claim {field} does not match frozen cap")
        payload = self.model_dump(mode="json")
        observed = payload.pop("claim_digest")
        expected_digest = hashlib.sha256(_canonical(payload)).hexdigest()
        if observed != expected_digest:
            raise ValueError("Authority-B claim digest mismatch")
        return self


class AuthorityBOutcome(AuthorityModel):
    schema_version: Literal["authority-b-outcome/v1"] = "authority-b-outcome/v1"
    claim_id: str = Field(min_length=1)
    status: Literal["PASS", "DEGRADED", "UNAVAILABLE"]
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    request_count: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    estimated_cost_usd: Decimal = Field(ge=0)
    usefulness_status: ProofStatus
    # This outcome is an integration/degradation record, not stable model-quality
    # evidence.  The default keeps the already-consumed redacted v1 artifact
    # readable while new records make the disclosure explicit on the wire.
    evidence_class: EvidenceClass = EvidenceClass.NOT_PROVEN
    stable_real_usefulness: Literal["NOT_PROVEN"] = "NOT_PROVEN"
    error_code: str | None = None


class AuthorityBAttemptAlreadyClaimed(RuntimeError):
    """The one allowed Authority-B provider attempt was already claimed."""


def _new_claim(claim_digest_value: str) -> AuthorityBAttemptClaim:
    return AuthorityBAttemptClaim.model_construct(
        schema_version="authority-b-attempt-claim/v1",
        claim_id=uuid.uuid4().hex,
        state="CLAIMED",
        created_at=datetime.now(UTC),
        authority_version="authority-rebaseline-b/v1",
        prior_cost_usd=AUTHORITY_B_PRIOR_ESTIMATED_COST_USD,
        request_cap=AUTHORITY_B_REQUEST_CAP,
        input_token_cap=AUTHORITY_B_INPUT_TOKEN_CAP,
        output_token_cap=AUTHORITY_B_OUTPUT_TOKEN_CAP,
        max_output_tokens_per_request=AUTHORITY_B_MAX_OUTPUT_TOKENS_PER_REQUEST,
        incremental_cost_cap_usd=AUTHORITY_B_INCREMENTAL_COST_CAP_USD,
        cumulative_cost_cap_usd=AUTHORITY_B_CUMULATIVE_COST_CAP_USD,
        claim_digest=claim_digest_value,
    )


def claim_digest(claim: AuthorityBAttemptClaim) -> str:
    payload = claim.model_dump(mode="json")
    payload.pop("claim_digest")
    return hashlib.sha256(_canonical(payload)).hexdigest()


def claim_authority_b_attempt(
    path: Path = AUTHORITY_B_CLAIM_PATH,
) -> AuthorityBAttemptClaim:
    """Atomically consume the sole provider attempt before any provider I/O."""

    path.parent.mkdir(parents=True, exist_ok=True)
    unsigned = _new_claim("0" * 64)
    payload = unsigned.model_dump(mode="json")
    payload.pop("claim_digest")
    digest_value = hashlib.sha256(_canonical(payload)).hexdigest()
    claim = unsigned.model_copy(update={"claim_digest": digest_value})
    encoded = _canonical(claim.model_dump(mode="json"))
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise AuthorityBAttemptAlreadyClaimed(
            "Authority-B provider attempt is already claimed"
        ) from exc
    try:
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException as exc:
        if descriptor >= 0:
            os.close(descriptor)
        raise RuntimeError("Authority-B claim write failed") from exc
    directory_descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_descriptor)
    finally:
        os.close(directory_descriptor)
    return claim


def load_authority_b_attempt_claim(
    path: Path = AUTHORITY_B_CLAIM_PATH,
) -> AuthorityBAttemptClaim:
    try:
        return AuthorityBAttemptClaim.model_validate_json(path.read_bytes())
    except (OSError, ValueError, TypeError) as exc:
        raise RuntimeError("Authority-B provider claim is unreadable") from exc


def save_authority_b_outcome(path: Path, outcome: AuthorityBOutcome) -> None:
    """Persist a redacted outcome exactly once; never include provider prose."""

    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = _canonical(outcome.model_dump(mode="json"))
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise AuthorityBAttemptAlreadyClaimed("Authority-B outcome path already exists") from exc
    try:
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        if descriptor >= 0:
            os.close(descriptor)


__all__ = [
    "AUTHORITY_B_CLAIM_PATH",
    "AUTHORITY_B_CUMULATIVE_COST_CAP_USD",
    "AUTHORITY_B_FAILURE_PATH",
    "AUTHORITY_B_INCREMENTAL_COST_CAP_USD",
    "AUTHORITY_B_INPUT_TOKEN_CAP",
    "AUTHORITY_B_MAX_OUTPUT_TOKENS_PER_REQUEST",
    "AUTHORITY_B_OUTPUT_TOKEN_CAP",
    "AUTHORITY_B_PRIOR_ESTIMATED_COST_USD",
    "AUTHORITY_B_REQUEST_CAP",
    "AUTHORITY_B_SUCCESS_PATH",
    "AuthorityBAttemptAlreadyClaimed",
    "AuthorityBAttemptClaim",
    "AuthorityBOutcome",
    "claim_authority_b_attempt",
    "claim_digest",
    "load_authority_b_attempt_claim",
    "save_authority_b_outcome",
]
