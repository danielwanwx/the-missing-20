"""Prepare or run one private effect-view screening probe.

The default mode is offline: it reconstructs the frozen source packet and
checks the relationship-view contract without calling a model.  ``--execute``
is an explicit opt-in for the root agent after review.  Both modes refuse to
overwrite an output file; an executed report retains the raw packet, every
candidate exposed by validation diagnostics, usage, ledger, and digests.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from the_missing_20.adapters.investigation_case_sources import (
    correlate_investigation_sources,
)
from the_missing_20.adapters.live_advisory_gateway import (
    DashboardAdvisoryGateway,
    competition_investigation_packet,
)
from the_missing_20.agents.investigation_effect_facts import investigation_effect_facts
from the_missing_20.agents.live_advisory import (
    AdvisoryUnavailable,
    AdvisoryValidationError,
    model_source_payloads,
    run_live_advisory,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = ROOT / "artifacts/audits/2026-09-09-current-ui/02-diagnosis-failure.json"
QUESTION = (
    "Investigate this case. Read the source evidence you need, compare the competing "
    "hypotheses, and explain each discrepancy with its observed quantity and source "
    "evidence. Then state a safe next step."
)
RELATED_FILES = (
    "src/the_missing_20/agents/live_advisory.py",
    "src/the_missing_20/agents/investigation_effect_facts.py",
    "src/the_missing_20/adapters/investigation_case_sources.py",
    "scripts/diagnostics/probe_investigation_effect_view.py",
)


class FrozenProjection:
    def __init__(self, projection: dict[str, object]) -> None:
        self._projection = projection

    def current(self) -> dict[str, object]:
        return self._projection


def _digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def _candidates(diagnostics: object) -> list[dict[str, Any]]:
    if not isinstance(diagnostics, list):
        return []
    return [
        dict(item["candidate"])
        for item in diagnostics
        if isinstance(item, Mapping) and isinstance(item.get("candidate"), Mapping)
    ]


def _cost(report: Mapping[str, Any]) -> object:
    usage = report.get("usage")
    if isinstance(usage, Mapping):
        for key in (
            "cost_usd",
            "estimated_cost_usd",
            "provider_cost_usd",
            "incremental_cost_usd",
        ):
            if usage.get(key) is not None:
                return usage[key]
    ledger = report.get("ledger")
    if isinstance(ledger, Mapping):
        for key in (
            "cost_usd",
            "estimated_cost_usd",
            "provider_cost_usd",
            "incremental_cost_usd",
        ):
            if ledger.get(key) is not None:
                return ledger[key]
    return 0


def _sdk_version() -> str | None:
    try:
        return importlib.metadata.version("strands-agents")
    except importlib.metadata.PackageNotFoundError:
        return None


def _code_provenance() -> dict[str, Any]:
    digests = {
        relative: hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
        for relative in RELATED_FILES
        if (ROOT / relative).is_file()
    }
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        code_sha = completed.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        code_sha = None
    return {"git_sha": code_sha, "related_file_sha256": digests}


def _provider_config(factory: Any) -> dict[str, Any]:
    config = factory.config
    budget = config.budget
    return {
        "provider": "bedrock",
        "model_id": config.model_id,
        "region": config.region,
        "max_tokens": config.max_tokens,
        "temperature": config.temperature,
        "streaming": config.streaming,
        "aws_profile": config.aws_profile,
        "budget": {
            "max_requests": budget.max_requests,
            "max_input_tokens": budget.max_input_tokens,
            "max_output_tokens": budget.max_output_tokens,
            "max_output_tokens_per_request": budget.max_output_tokens_per_request,
            "prior_cost_usd": str(budget.prior_cost_usd),
            "incremental_cost_cap_usd": str(budget.incremental_cost_cap_usd),
            "cumulative_cost_cap_usd": str(budget.cumulative_cost_cap_usd),
            "input_price_per_token": str(budget.input_price_per_token),
            "output_price_per_token": str(budget.output_price_per_token),
            "per_call_timeout_seconds": budget.per_call_timeout_seconds,
            "whole_run_timeout_seconds": budget.whole_run_timeout_seconds,
        },
    }


def _build_packet(
    source_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    projection = json.loads(source_path.read_text(encoding="utf-8"))
    if not isinstance(projection, Mapping):
        raise ValueError("source projection must be a JSON object")
    packet = dict(competition_investigation_packet(projection))
    packet["explanation_scope"] = "full_investigation"
    model_sources = model_source_payloads(packet)
    canonical = correlate_investigation_sources(dict(model_sources))
    effect_facts = investigation_effect_facts(
        model_sources,
        correlated_findings=canonical,
    )
    return (
        dict(projection),
        model_sources,
        {
            "case_id": packet.get("case_id"),
            "question": QUESTION,
            "effect_facts": effect_facts,
        },
        packet,
    )


def _run(report: dict[str, Any], packet: dict[str, Any]) -> None:
    gateway = DashboardAdvisoryGateway(FrozenProjection(report["source_projection"]))
    factory = gateway._factory()
    report["model_id"] = factory.config.model_id
    report["provider_config"] = _provider_config(factory)
    try:
        run = run_live_advisory(packet, factory=factory, question=QUESTION)
    except (AdvisoryUnavailable, AdvisoryValidationError) as error:
        candidates = _candidates(error.diagnostics)
        report.update(
            {
                "status": type(error).__name__,
                "candidate": candidates[-1] if candidates else None,
                "candidates": candidates,
                "diagnostics": error.diagnostics,
                "usage": error.usage,
            }
        )
    except Exception as error:  # pragma: no cover - live provider boundary
        report.update(
            {
                "status": "UNEXPECTED_ERROR",
                "error": f"{type(error).__name__}: {error}",
                "usage": getattr(error, "usage", {}),
                "diagnostics": getattr(error, "diagnostics", []),
            }
        )
    else:
        candidate = run.result.model_dump(mode="json")
        report.update(
            {
                "status": "COMPLETE_DIAGNOSTIC_ONLY",
                "candidate": candidate,
                "candidates": [candidate],
                "usage": run.usage,
                "tool_calls": run.tool_calls,
                "latency_ms": run.latency_ms,
                "runtime_events": run.runtime_events,
            }
        )
    finally:
        report["ledger"] = factory.ledger.snapshot()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="run one real read-only model probe after offline review",
    )
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    source = args.source.expanduser().resolve()
    if output.exists():
        parser.error(f"refusing to overwrite existing output: {output}")
    if not source.is_file():
        parser.error(f"source projection does not exist: {source}")
    if os.environ.get("MISSING20_AGENT_WORKFLOW", "single") != "single":
        parser.error("effect-view screening is frozen to the single-agent workflow")

    started_at = datetime.now(UTC).isoformat()
    source_projection, model_sources, packet_context, packet = _build_packet(source)
    report: dict[str, Any] = {
        "scope": "single private effect-view screening; no business writes",
        "status": "READY_OFFLINE",
        "started_at": started_at,
        "finished_at": None,
        "source_path": str(source),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "model_sources_sha256": _digest(model_sources),
        "source_projection": source_projection,
        "model_sources": model_sources,
        "packet_context": packet_context,
        "question": QUESTION,
        "sdk_version": _sdk_version(),
        "code_provenance": _code_provenance(),
        "provider_config": None,
        "candidate_capture_scope": (
            "Final accepted candidate plus candidates exposed in validation diagnostics; "
            "provider responses hidden before validation are not available through the "
            "run API."
        ),
        "writer_invoked": False,
        "candidate": None,
        "candidates": [],
        "usage": {},
        "ledger": {},
    }
    if args.execute:
        _run(report, packet)
    report["finished_at"] = datetime.now(UTC).isoformat()
    output.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor = os.open(
        output,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, default=str)
        handle.write("\n")
    output.chmod(0o600)
    print(f"status={report['status']} cost_usd={_cost(report)} path={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
