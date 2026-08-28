"""Execute the exactly-one Authority-B main-case Nova advisory proof.

The command is intentionally separate from the historical v9 four-profile smoke.  A
successful or degraded result is persisted by ``AgentGoldenRunner``; this wrapper
never retries, falls back, probes, or launches another profile.
"""

from __future__ import annotations

import argparse
import os
import sys
from decimal import Decimal
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.aws_preflight import PreflightError, load_identity, validate_identity
from the_missing_20.adapters.strands_models import BedrockNovaProConfig, BedrockNovaProFactory
from the_missing_20.authority_b.provider import (
    AUTHORITY_B_CUMULATIVE_COST_CAP_USD,
    AUTHORITY_B_INCREMENTAL_COST_CAP_USD,
    AUTHORITY_B_INPUT_TOKEN_CAP,
    AUTHORITY_B_MAX_OUTPUT_TOKENS_PER_REQUEST,
    AUTHORITY_B_OUTPUT_TOKEN_CAP,
    AUTHORITY_B_PRIOR_ESTIMATED_COST_USD,
)
from the_missing_20.config import ConfigurationError, Settings
from the_missing_20.evaluation.agent_golden_runner import AgentGoldenRunner
from the_missing_20.ports.agent_model import AgentBudget, AgentBudgetLedger, AgentProvider

ROOT = Path(__file__).resolve().parents[1]


def _confirm() -> None:
    if os.getenv("BEDROCK_CONFIRM") != "1":
        raise PreflightError("set BEDROCK_CONFIRM=1 for the single Authority-B proof")
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
        factory = BedrockNovaProFactory(config, ledger=AgentBudgetLedger(budget))
        runner = AgentGoldenRunner(ROOT, ROOT / "artifacts/golden")
        proof = runner.run_authority_b_advisory(factory)
        outcome = proof.get("outcome", {})
        input_tokens = int(outcome.get("input_tokens", 0))
        output_tokens = int(outcome.get("output_tokens", 0))
        request_count = int(outcome.get("request_count", 0))
        cost = Decimal(str(outcome.get("estimated_cost_usd", "0")))
        if request_count > budget.max_requests:
            raise PreflightError("Authority-B provider request cap was exceeded")
        if input_tokens > budget.max_input_tokens or output_tokens > budget.max_output_tokens:
            raise PreflightError("Authority-B provider token cap was exceeded")
        if cost > AUTHORITY_B_INCREMENTAL_COST_CAP_USD:
            raise PreflightError("Authority-B estimated cost exceeds the frozen incremental cap")
        if AUTHORITY_B_PRIOR_ESTIMATED_COST_USD + cost > AUTHORITY_B_CUMULATIVE_COST_CAP_USD:
            raise PreflightError("Authority-B estimated cost exceeds the frozen cumulative cap")
        print(
            f"Authority-B proof {proof.get('status')}: requests={request_count} "
            f"input={input_tokens} output={output_tokens} cost_usd={cost}"
        )
        return 0 if proof.get("status") == "PASS" else 1
    except (ConfigurationError, PreflightError, OSError, KeyError, ValueError) as exc:
        print(f"Authority-B proof: BLOCKED ({exc})", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
