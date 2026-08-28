"""Run the explicitly confirmed Bedrock four-profile smoke and compose Golden v2."""

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
from the_missing_20.adapters.strands_models import BedrockNovaProConfig, BedrockNovaProFactory
from the_missing_20.config import ConfigurationError, Settings
from the_missing_20.evaluation.agent_golden_runner import (
    BEDROCK_ARTIFACT,
    AgentGoldenRunner,
    _atomic_json,
)
from the_missing_20.ports.agent_model import (
    CUMULATIVE_COST_CAP_USD,
    INCREMENTAL_COST_CAP_USD,
    INPUT_PRICE_PER_TOKEN,
    MAX_INPUT_TOKENS,
    MAX_OUTPUT_TOKENS,
    MAX_OUTPUT_TOKENS_PER_REQUEST,
    MAX_REQUESTS,
    OUTPUT_PRICE_PER_TOKEN,
    PRIOR_ESTIMATED_COST_USD,
    AgentBudget,
    AgentBudgetLedger,
    AgentProvider,
)

ROOT = Path(__file__).resolve().parents[1]
REQUEST_CAP = MAX_REQUESTS
INPUT_TOKEN_CAP = MAX_INPUT_TOKENS
OUTPUT_TOKEN_CAP = MAX_OUTPUT_TOKENS
MAX_ESTIMATED_COST = INCREMENTAL_COST_CAP_USD


def _confirm() -> None:
    if os.getenv("BEDROCK_CONFIRM") != "1":
        raise PreflightError("set BEDROCK_CONFIRM=1 for the individual Bedrock smoke run")
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
            max_requests=REQUEST_CAP,
            max_input_tokens=INPUT_TOKEN_CAP,
            max_output_tokens=OUTPUT_TOKEN_CAP,
            per_call_timeout_seconds=45,
            whole_run_timeout_seconds=120,
        )
        ledger = AgentBudgetLedger(budget)
        config = BedrockNovaProConfig(
            region=settings.aws_region,
            aws_profile=settings.aws_profile,
            # Forty requests at this per-request ceiling cannot cross the accepted
            # 70,240 output-token budget even before post-response accounting.
            max_tokens=MAX_OUTPUT_TOKENS_PER_REQUEST,
            budget=budget,
        )
        factory = BedrockNovaProFactory(config, ledger=ledger)
        proof = AgentGoldenRunner(ROOT, ROOT / "artifacts/golden").run_bedrock(factory)
        budget_usage = proof["budget"]
        usage = {
            "inputTokens": budget_usage["input_tokens"],
            "outputTokens": budget_usage["output_tokens"],
        }
        request_count = int(budget_usage["request_count"])
        if proof["status"] != "PASS":
            raise PreflightError("Bedrock smoke did not pass all four profiles")
        if proof["request_count"] != request_count or proof["token_usage"] != usage:
            raise PreflightError(
                "Bedrock smoke report is not sourced from the shared budget ledger"
            )
        if request_count > REQUEST_CAP:
            raise PreflightError("Bedrock smoke request cap was exceeded")
        if (
            int(usage["inputTokens"]) > INPUT_TOKEN_CAP
            or int(usage["outputTokens"]) > OUTPUT_TOKEN_CAP
        ):
            raise PreflightError("Bedrock smoke token cap was exceeded")
        estimated_cost = (
            Decimal(int(usage["inputTokens"])) * INPUT_PRICE_PER_TOKEN
            + Decimal(int(usage["outputTokens"])) * OUTPUT_PRICE_PER_TOKEN
        )
        if estimated_cost > MAX_ESTIMATED_COST:
            raise PreflightError("Bedrock smoke estimated cost exceeds the frozen credit budget")
        if PRIOR_ESTIMATED_COST_USD + estimated_cost > CUMULATIVE_COST_CAP_USD:
            raise PreflightError("Bedrock smoke cumulative cost exceeds the frozen credit budget")
        proof["boto3_version"] = importlib.metadata.version("boto3")
        proof["strands_version"] = importlib.metadata.version("strands-agents")
        proof["request_cap"] = REQUEST_CAP
        proof["token_caps"] = {"input": INPUT_TOKEN_CAP, "output": OUTPUT_TOKEN_CAP}
        proof["estimated_max_cost_usd"] = float(estimated_cost)
        _atomic_json(ROOT / BEDROCK_ARTIFACT, proof)
        composed = AgentGoldenRunner(ROOT, ROOT / "artifacts/golden").run_all()
        if not composed["promotion"]["promotable"]:
            raise PreflightError("Golden v2 was not promotable after Bedrock smoke")
    except (ConfigurationError, PreflightError, OSError, KeyError, ValueError) as exc:
        print(f"Agent smoke: BLOCKED ({exc})", file=sys.stderr)
        return 2
    print("Agent smoke: PASS (four profiles verified within frozen caps)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
