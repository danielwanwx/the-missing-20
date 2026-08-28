"""Read-only preflight for the single Authority-B Nova advisory proof.

The command verifies identity, model/region, exclusive-attempt state, and the frozen
Authority-B cost envelope.  It never creates a model client or starts provider I/O.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import os
import sys
from decimal import Decimal
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.aws_preflight import PreflightError, load_identity, validate_identity
from the_missing_20.adapters.strands_models import BedrockNovaProConfig
from the_missing_20.authority_b.provider import (
    AUTHORITY_B_CLAIM_PATH,
    AUTHORITY_B_CUMULATIVE_COST_CAP_USD,
    AUTHORITY_B_INCREMENTAL_COST_CAP_USD,
    AUTHORITY_B_INPUT_TOKEN_CAP,
    AUTHORITY_B_MAX_OUTPUT_TOKENS_PER_REQUEST,
    AUTHORITY_B_OUTPUT_TOKEN_CAP,
    AUTHORITY_B_PRIOR_ESTIMATED_COST_USD,
)
from the_missing_20.config import ConfigurationError, Settings
from the_missing_20.evaluation.agent_golden_runner import _atomic_json
from the_missing_20.ports.agent_model import AgentBudget, AgentProvider

ROOT = Path(__file__).resolve().parents[1]


def _confirm() -> None:
    if os.getenv("BEDROCK_CONFIRM") != "1":
        raise PreflightError("set BEDROCK_CONFIRM=1 for the Authority-B preflight")
    if os.getenv("MISSING20_AGENT_PROVIDER", "").strip().lower() != AgentProvider.BEDROCK.value:
        raise PreflightError("MISSING20_AGENT_PROVIDER=bedrock is required")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm", choices=("0", "1"), default=None)
    args = parser.parse_args()
    if args.confirm is not None and "BEDROCK_CONFIRM" not in os.environ:
        os.environ["BEDROCK_CONFIRM"] = args.confirm
    try:
        _confirm()
        settings = Settings.from_env()
        identity = load_identity(settings)
        validate_identity(identity, settings)
        claim_path = ROOT / AUTHORITY_B_CLAIM_PATH
        if claim_path.exists():
            raise PreflightError("Authority-B provider attempt is already claimed")
        budget = AgentBudget(
            max_requests=12,
            max_input_tokens=AUTHORITY_B_INPUT_TOKEN_CAP,
            max_output_tokens=AUTHORITY_B_OUTPUT_TOKEN_CAP,
            max_output_tokens_per_request=AUTHORITY_B_MAX_OUTPUT_TOKENS_PER_REQUEST,
            prior_cost_usd=AUTHORITY_B_PRIOR_ESTIMATED_COST_USD,
            incremental_cost_cap_usd=AUTHORITY_B_INCREMENTAL_COST_CAP_USD,
            cumulative_cost_cap_usd=AUTHORITY_B_CUMULATIVE_COST_CAP_USD,
            per_call_timeout_seconds=45,
            whole_run_timeout_seconds=120,
        )
        config = BedrockNovaProConfig(
            region=settings.aws_region,
            aws_profile=settings.aws_profile,
            max_tokens=budget.max_output_tokens_per_request,
            budget=budget,
        )
        maximum_incremental = Decimal(AUTHORITY_B_INPUT_TOKEN_CAP) * Decimal("0.80") / Decimal(
            1_000_000
        ) + Decimal(AUTHORITY_B_OUTPUT_TOKEN_CAP) * Decimal("3.20") / Decimal(1_000_000)
        if maximum_incremental != AUTHORITY_B_INCREMENTAL_COST_CAP_USD:
            raise PreflightError("Authority-B incremental cost arithmetic is not frozen")
        if AUTHORITY_B_PRIOR_ESTIMATED_COST_USD + maximum_incremental != (
            AUTHORITY_B_CUMULATIVE_COST_CAP_USD
        ):
            raise PreflightError("Authority-B cumulative cost arithmetic is not frozen")
        proof = {
            "schema_version": "authority-b-preflight/v1",
            "status": "PASS",
            "provider": "amazon-bedrock-promotional-credit",
            "model_id": config.model_id,
            "region": config.region,
            "expected_account_verified": True,
            "provider_calls": 0,
            "compatibility_probe": False,
            "request_cap": budget.max_requests,
            "token_caps": {
                "input": budget.max_input_tokens,
                "output": budget.max_output_tokens,
            },
            "max_output_tokens_per_request": budget.max_output_tokens_per_request,
            "estimated_max_incremental_cost_usd": float(maximum_incremental),
            "estimated_max_cumulative_cost_usd": float(
                AUTHORITY_B_PRIOR_ESTIMATED_COST_USD + maximum_incremental
            ),
            "boto3_version": importlib.metadata.version("boto3"),
            "strands_version": importlib.metadata.version("strands-agents"),
        }
        _atomic_json(ROOT / "artifacts/agent/authority-b-preflight-v1.json", proof)
    except (ConfigurationError, PreflightError, OSError, KeyError, ValueError) as exc:
        print(f"Authority-B preflight: BLOCKED ({exc})", file=sys.stderr)
        return 2
    print(
        "Authority-B preflight: PASS (read-only identity and frozen single-attempt budget verified)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
