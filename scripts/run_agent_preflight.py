"""Run the read-only preflight for the single gated Nova Pro acceptance batch.

This command validates identity, region, model allowlists, and the frozen cost
arithmetic. It deliberately does not instantiate an agent, call a model, or perform
a compatibility probe; the acceptance batch is the only provider product path.
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
from the_missing_20.config import ConfigurationError, Settings
from the_missing_20.evaluation.agent_golden_runner import _atomic_json
from the_missing_20.ports.agent_model import (
    CUMULATIVE_COST_CAP_USD,
    INCREMENTAL_COST_CAP_USD,
    INPUT_PRICE_PER_TOKEN,
    MAX_INPUT_TOKENS,
    MAX_OUTPUT_TOKENS,
    MAX_REQUESTS,
    OUTPUT_PRICE_PER_TOKEN,
    PRIOR_ESTIMATED_COST_USD,
    AgentBudget,
    AgentProvider,
)

ROOT = Path(__file__).resolve().parents[1]


def _confirm() -> None:
    if os.getenv("BEDROCK_CONFIRM") != "1":
        raise PreflightError("set BEDROCK_CONFIRM=1 for the individual Bedrock preflight run")
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
        budget = AgentBudget(
            max_requests=MAX_REQUESTS,
            max_input_tokens=MAX_INPUT_TOKENS,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            per_call_timeout_seconds=45,
            whole_run_timeout_seconds=120,
        )
        config = BedrockNovaProConfig(
            region=settings.aws_region,
            aws_profile=settings.aws_profile,
            max_tokens=budget.max_output_tokens_per_request,
            budget=budget,
        )
        maximum_incremental = (
            Decimal(MAX_INPUT_TOKENS) * INPUT_PRICE_PER_TOKEN
            + Decimal(MAX_OUTPUT_TOKENS) * OUTPUT_PRICE_PER_TOKEN
        )
        maximum_cumulative = PRIOR_ESTIMATED_COST_USD + maximum_incremental
        if maximum_incremental > INCREMENTAL_COST_CAP_USD:
            raise PreflightError("maximum incremental cost exceeds the frozen credit budget")
        if maximum_cumulative > CUMULATIVE_COST_CAP_USD:
            raise PreflightError("maximum cumulative cost exceeds the frozen credit budget")
        proof = {
            "schema_version": "agent-preflight/v2",
            "status": "PASS",
            "provider": "amazon-bedrock-promotional-credit",
            "model_id": config.model_id,
            "region": config.region,
            "expected_account_verified": True,
            "provider_calls": 0,
            "compatibility_probe": False,
            "request_cap": MAX_REQUESTS,
            "token_caps": {"input": MAX_INPUT_TOKENS, "output": MAX_OUTPUT_TOKENS},
            "max_output_tokens_per_request": budget.max_output_tokens_per_request,
            "estimated_max_incremental_cost_usd": float(maximum_incremental),
            "estimated_max_cumulative_cost_usd": float(maximum_cumulative),
            "boto3_version": importlib.metadata.version("boto3"),
            "strands_version": importlib.metadata.version("strands-agents"),
        }
        _atomic_json(ROOT / "artifacts/agent/model-compatibility.json", proof)
    except (ConfigurationError, PreflightError, OSError, KeyError, ValueError) as exc:
        print(f"Agent preflight: BLOCKED ({exc})", file=sys.stderr)
        return 2
    print("Agent preflight: PASS (read-only identity and capped Nova Pro configuration verified)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
