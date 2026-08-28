"""Durable exactly-once claims for the versioned provider acceptance batches."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from the_missing_20.agents.schemas import (
    ATTEMPT_CLAIM_SCHEMA_VERSION,
    ENVELOPE_VERSION,
    AgentProtocolEnvelope,
    AgentProviderAttemptClaimV7,
    AgentProviderAttemptClaimV8,
    AgentProviderAttemptClaimV9,
)
from the_missing_20.ports.agent_model import (
    CUMULATIVE_COST_CAP_USD,
    INCREMENTAL_COST_CAP_USD,
    MAX_INPUT_TOKENS,
    MAX_OUTPUT_TOKENS,
    MAX_OUTPUT_TOKENS_PER_REQUEST,
    MAX_REQUESTS,
    PRIOR_ESTIMATED_COST_USD,
)


class ProviderAttemptClaimError(RuntimeError):
    """The v7 attempt claim could not be created or read."""


class V7AttemptAlreadyClaimed(ProviderAttemptClaimError):
    """An existing claim consumes the only permitted v7 provider attempt."""


class V8AttemptAlreadyClaimed(ProviderAttemptClaimError):
    """An existing claim consumes the only permitted v8 provider attempt."""


class V9AttemptAlreadyClaimed(ProviderAttemptClaimError):
    """An existing claim consumes the only permitted v9 provider attempt."""


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode("utf-8")


def claim_digest(
    claim: AgentProviderAttemptClaimV7 | AgentProviderAttemptClaimV8 | AgentProviderAttemptClaimV9,
) -> str:
    """Return the digest over every claim field except its self-digest."""

    payload = claim.model_dump(mode="json")
    payload.pop("claim_digest")
    return hashlib.sha256(_canonical(payload)).hexdigest()


def _claim_payload(
    protocol: AgentProtocolEnvelope | None,
    *,
    agent_contract_version: str,
    prior_cost_usd: Decimal | None = None,
    output_token_cap: int | None = None,
    max_output_tokens_per_request: int | None = None,
    incremental_cost_cap_usd: Decimal | None = None,
) -> dict[str, object]:
    prior = PRIOR_ESTIMATED_COST_USD if prior_cost_usd is None else prior_cost_usd
    output_cap = MAX_OUTPUT_TOKENS if output_token_cap is None else output_token_cap
    per_request = (
        MAX_OUTPUT_TOKENS_PER_REQUEST
        if max_output_tokens_per_request is None
        else max_output_tokens_per_request
    )
    incremental_cap = (
        INCREMENTAL_COST_CAP_USD if incremental_cost_cap_usd is None else incremental_cost_cap_usd
    )
    return {
        "schema_version": ATTEMPT_CLAIM_SCHEMA_VERSION,
        "claim_id": uuid.uuid4().hex,
        "state": "CLAIMED",
        "created_at": datetime.now(UTC),
        "agent_contract_version": agent_contract_version,
        "envelope_version": protocol.envelope_version if protocol is not None else ENVELOPE_VERSION,
        "prior_cost_usd": float(prior),
        "request_cap": MAX_REQUESTS,
        "input_token_cap": MAX_INPUT_TOKENS,
        "output_token_cap": output_cap,
        "max_output_tokens_per_request": per_request,
        "incremental_cost_cap_usd": float(incremental_cap),
        "cumulative_cost_cap_usd": float(CUMULATIVE_COST_CAP_USD),
    }


def _fsync_directory(directory: Path) -> None:
    directory_fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def claim_v7_attempt(
    path: Path,
    *,
    protocol: AgentProtocolEnvelope | None = None,
) -> AgentProviderAttemptClaimV7:
    """Exclusively and durably consume the one v7 provider attempt.

    ``O_EXCL`` is the source of truth.  Once the path is created, even a crash during
    the subsequent write leaves an incomplete claim that must block every later launch.
    The record contains only fixed protocol/cost metadata; it never contains a path,
    account identifier, credentials, or model prose.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    if protocol is not None and str(protocol.agent_contract_version) != "agent-contract/v7":
        raise ProviderAttemptClaimError("v7 provider claim requires a v7 protocol envelope")
    payload = _claim_payload(
        protocol,
        agent_contract_version="agent-contract/v7",
        prior_cost_usd=Decimal("0.0258576"),
        output_token_cap=79_400,
        max_output_tokens_per_request=1_985,
        incremental_cost_cap_usd=Decimal("0.5741424"),
    )
    unsigned = AgentProviderAttemptClaimV7.model_construct(
        **payload,  # type: ignore[arg-type]
        claim_digest="0" * 64,
    )
    digest_payload = unsigned.model_dump(mode="json")
    digest_payload.pop("claim_digest")
    digest = hashlib.sha256(_canonical(digest_payload)).hexdigest()
    claim = AgentProviderAttemptClaimV7(**payload, claim_digest=digest)  # type: ignore[arg-type]
    encoded = _canonical(claim.model_dump(mode="json"))
    try:
        file_descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except FileExistsError as exc:
        raise V7AttemptAlreadyClaimed("v7 provider attempt is already claimed") from exc

    try:
        with os.fdopen(file_descriptor, "wb") as handle:
            file_descriptor = -1
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException as exc:
        # Do not unlink a partially written claim.  Its existence is intentionally
        # sufficient to consume the attempt after a crash or local write failure.
        if file_descriptor >= 0:
            os.close(file_descriptor)
        raise ProviderAttemptClaimError("v7 provider claim write failed") from exc
    _fsync_directory(path.parent)
    return claim


def load_v7_attempt_claim(path: Path) -> AgentProviderAttemptClaimV7:
    """Load and validate a durable claim without exposing raw file contents."""

    try:
        return AgentProviderAttemptClaimV7.model_validate_json(path.read_bytes())
    except (OSError, ValueError, TypeError) as exc:
        raise ProviderAttemptClaimError("v7 provider claim is unreadable") from exc


def claim_v8_attempt(
    path: Path,
    *,
    protocol: AgentProtocolEnvelope | None = None,
) -> AgentProviderAttemptClaimV8:
    """Exclusively and durably consume the one v8 provider attempt."""

    if protocol is not None and protocol.agent_contract_version != "agent-contract/v8":
        raise ProviderAttemptClaimError("v8 provider claim requires a v8 protocol envelope")
    # Historical v8 evidence remains immutable even though the active budget now
    # belongs to v9.
    payload = _claim_payload(
        protocol,
        agent_contract_version="agent-contract/v8",
        prior_cost_usd=Decimal("0.0551848"),
        output_token_cap=70_240,
        max_output_tokens_per_request=1_756,
        incremental_cost_cap_usd=Decimal("0.5448152"),
    )
    unsigned = AgentProviderAttemptClaimV8.model_construct(
        **payload,  # type: ignore[arg-type]
        claim_digest="0" * 64,
    )
    digest_payload = unsigned.model_dump(mode="json")
    digest_payload.pop("claim_digest")
    digest = hashlib.sha256(_canonical(digest_payload)).hexdigest()
    claim = AgentProviderAttemptClaimV8(**payload, claim_digest=digest)  # type: ignore[arg-type]
    encoded = _canonical(claim.model_dump(mode="json"))
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        file_descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise V8AttemptAlreadyClaimed("v8 provider attempt is already claimed") from exc
    try:
        with os.fdopen(file_descriptor, "wb") as handle:
            file_descriptor = -1
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException as exc:
        if file_descriptor >= 0:
            os.close(file_descriptor)
        raise ProviderAttemptClaimError("v8 provider claim write failed") from exc
    _fsync_directory(path.parent)
    return claim


def load_v8_attempt_claim(path: Path) -> AgentProviderAttemptClaimV8:
    """Load and validate a durable v8 claim without exposing raw contents."""

    try:
        return AgentProviderAttemptClaimV8.model_validate_json(path.read_bytes())
    except (OSError, ValueError, TypeError) as exc:
        raise ProviderAttemptClaimError("v8 provider claim is unreadable") from exc


def claim_v9_attempt(
    path: Path,
    *,
    protocol: AgentProtocolEnvelope | None = None,
) -> AgentProviderAttemptClaimV9:
    """Exclusively and durably consume the one v9 provider attempt."""

    if protocol is not None and protocol.agent_contract_version != "agent-contract/v9":
        raise ProviderAttemptClaimError("v9 provider claim requires a v9 protocol envelope")
    payload = _claim_payload(protocol, agent_contract_version="agent-contract/v9")
    unsigned = AgentProviderAttemptClaimV9.model_construct(
        **payload,  # type: ignore[arg-type]
        claim_digest="0" * 64,
    )
    digest_payload = unsigned.model_dump(mode="json")
    digest_payload.pop("claim_digest")
    digest = hashlib.sha256(_canonical(digest_payload)).hexdigest()
    claim = AgentProviderAttemptClaimV9(**payload, claim_digest=digest)  # type: ignore[arg-type]
    encoded = _canonical(claim.model_dump(mode="json"))
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        file_descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise V9AttemptAlreadyClaimed("v9 provider attempt is already claimed") from exc
    try:
        with os.fdopen(file_descriptor, "wb") as handle:
            file_descriptor = -1
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException as exc:
        if file_descriptor >= 0:
            os.close(file_descriptor)
        raise ProviderAttemptClaimError("v9 provider claim write failed") from exc
    _fsync_directory(path.parent)
    return claim


def load_v9_attempt_claim(path: Path) -> AgentProviderAttemptClaimV9:
    """Load and validate a durable v9 claim without exposing raw file contents."""

    try:
        return AgentProviderAttemptClaimV9.model_validate_json(path.read_bytes())
    except (OSError, ValueError, TypeError) as exc:
        raise ProviderAttemptClaimError("v9 provider claim is unreadable") from exc
