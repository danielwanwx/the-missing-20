"""Run the full, read-only real Strands/Nova Pro evaluation matrix."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from urllib.request import urlopen
from uuid import uuid4

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.aws_preflight import PreflightError, load_identity, validate_identity
from the_missing_20.adapters.erpnext_source import _read_env_file
from the_missing_20.adapters.strands_models import BedrockNovaProConfig, BedrockNovaProFactory
from the_missing_20.agents.live_advisory import live_recovery_packet
from the_missing_20.config import ConfigurationError, Settings
from the_missing_20.evaluation.real_strands_matrix import load_fixture_packet, run_case
from the_missing_20.ports.agent_model import (
    AgentBudget,
    AgentBudgetExceeded,
    AgentBudgetLedger,
    AgentProvider,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "artifacts/agent/real-strands-matrix-latest.json"
DEFAULT_LIVE_URL = "http://127.0.0.1:8765/api/v1/agent-platform"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm", choices=("0", "1"), default=None)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--live-url", default=DEFAULT_LIVE_URL)
    parser.add_argument("--skip-live", action="store_true")
    parser.add_argument("--live-only", action="store_true")
    parser.add_argument(
        "--case",
        action="append",
        default=[],
        help="Fixture case filename stem to run; repeat for a representative subset.",
    )
    return parser.parse_args()


def _confirm() -> None:
    if os.getenv("BEDROCK_CONFIRM") != "1":
        raise PreflightError("set BEDROCK_CONFIRM=1 for the real Strands case matrix")
    if os.getenv("MISSING20_AGENT_PROVIDER", "").strip().lower() != AgentProvider.BEDROCK:
        raise PreflightError("MISSING20_AGENT_PROVIDER=bedrock is required")


def _fetch_live_packet(url: str) -> dict[str, object]:
    with urlopen(url, timeout=30) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise ValueError("live dashboard response must be a JSON object")
    return live_recovery_packet(payload)


def _write_report(path: Path, report: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    temporary.replace(path)


def main() -> int:
    args = parse_args()
    if args.confirm is not None and "BEDROCK_CONFIRM" not in os.environ:
        os.environ["BEDROCK_CONFIRM"] = args.confirm
    try:
        _confirm()
        # Parse dotenv as data. Shell-sourcing this file is unsafe and also
        # breaks legitimate SaaS labels containing spaces.
        settings = Settings.from_env({**_read_env_file(ROOT / ".env"), **os.environ})
        identity = load_identity(settings)
        validate_identity(identity, settings)
        budget = AgentBudget(
            max_requests=40,
            max_input_tokens=200_000,
            max_output_tokens=24_000,
            max_output_tokens_per_request=800,
            prior_cost_usd=Decimal("0"),
            incremental_cost_cap_usd=Decimal("0.20"),
            cumulative_cost_cap_usd=Decimal("0.20"),
            per_call_timeout_seconds=45,
            whole_run_timeout_seconds=300,
        )
        ledger = AgentBudgetLedger(budget)
        factory = BedrockNovaProFactory(
            BedrockNovaProConfig(
                region=settings.aws_region,
                aws_profile=settings.aws_profile,
                max_tokens=800,
                temperature=0,
                budget=budget,
            ),
            ledger=ledger,
        )
        fixture_paths = sorted((ROOT / "artifacts/golden/cases").glob("*.json"))
        if args.case:
            selected = set(args.case)
            fixture_paths = [path for path in fixture_paths if path.stem in selected]
            missing = selected.difference(path.stem for path in fixture_paths)
            if missing:
                raise ValueError("unknown fixture cases: " + ", ".join(sorted(missing)))
        packets = [] if args.live_only else [load_fixture_packet(path) for path in fixture_paths]
        if not args.skip_live:
            packets.insert(0, _fetch_live_packet(args.live_url))

        records: list[dict[str, object]] = []
        stopped_reason: str | None = None
        for packet in packets:
            try:
                records.append(run_case(packet, factory=factory))
            except AgentBudgetExceeded as exc:
                stopped_reason = f"BUDGET_STOP: {exc}"
                break
            except Exception as exc:  # Provider errors become inspectable test records.
                records.append(
                    {
                        "case_id": packet["case_id"],
                        "case_key": packet["case_key"],
                        "case_class": packet["case_class"],
                        "source": packet["source"],
                        "status": "ERROR",
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    }
                )

        passed = 0
        for record in records:
            rubric = record.get("rubric")
            if isinstance(rubric, dict) and rubric.get("passed") is True:
                passed += 1
        completed = sum("rubric" in record for record in records)
        errors = sum(record.get("status") == "ERROR" for record in records)
        report: dict[str, object] = {
            "schema_version": "real-strands-case-matrix/v1",
            "batch_id": f"real-strands-{uuid4().hex}",
            "created_at": datetime.now(UTC).isoformat(),
            "provider": factory.provenance(),
            "input_sources": {
                "fixture_cases": 0 if args.live_only else len(fixture_paths),
                "live_case": not args.skip_live,
            },
            "records": records,
            "summary": {
                "planned_cases": len(packets),
                "completed_cases": completed,
                "passed_cases": passed,
                "failed_rubric_cases": completed - passed,
                "provider_error_cases": errors,
                "stopped_reason": stopped_reason,
                "usage": ledger.snapshot(),
            },
        }
        _write_report(args.output, report)
    except (ConfigurationError, PreflightError, OSError, ValueError) as exc:
        print(f"Real Strands matrix: BLOCKED ({exc})", file=sys.stderr)
        return 2

    print(
        "Real Strands matrix: COMPLETE "
        f"(completed={completed}, passed={passed}, errors={errors}, output={args.output})"
    )
    return 0 if stopped_reason is None and errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
