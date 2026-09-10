"""Prepare or explicitly run one private fresh-synthesis-context diagnostic.

Default execution is offline preparation only.  ``--execute`` is the explicit
opt-in for one read-only model invocation after independent implementation
review.  The diagnostic uses the original frozen investigation packet and
question, but never restores the withdrawn effect-view treatment.
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
from the_missing_20.agents.live_advisory import (
    AdvisoryUnavailable,
    AdvisoryValidationError,
    model_source_payloads,
    run_fresh_synthesis_context_diagnostic,
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
    "src/the_missing_20/agents/fresh_synthesis_context.py",
    "src/the_missing_20/adapters/investigation_case_sources.py",
    "scripts/diagnostics/probe_fresh_synthesis_context.py",
)


class FrozenProjection:
    """Expose only the archived synthetic projection to the normal packet builder."""

    def __init__(self, projection: dict[str, Any]) -> None:
        self._projection = projection

    def current(self) -> dict[str, Any]:
        return self._projection


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


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


def _first_candidate(diagnostics: object) -> dict[str, Any] | None:
    if not isinstance(diagnostics, list):
        return None
    for item in diagnostics:
        if isinstance(item, Mapping) and isinstance(item.get("candidate"), Mapping):
            return dict(item["candidate"])
    return None


def _private_first_structured_capture(
    error: AdvisoryUnavailable | AdvisoryValidationError | BaseException,
) -> dict[str, Any]:
    """Read diagnostic-only raw capture without widening normal advisory diagnostics."""

    capture = getattr(error, "_fresh_synthesis_diagnostic_capture", None)
    if isinstance(capture, Mapping):
        return dict(capture)
    return {"status": "NOT_RECEIVED", "first_structured_raw_value": None}


def _build_packet(
    source_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    projection = json.loads(source_path.read_text(encoding="utf-8"))
    if not isinstance(projection, Mapping):
        raise ValueError("source projection must be a JSON object")
    packet = dict(competition_investigation_packet(projection))
    packet["explanation_scope"] = "full_investigation"
    model_sources = model_source_payloads(packet)
    canonical_reconciliation = correlate_investigation_sources(dict(model_sources))
    return (
        dict(projection),
        model_sources,
        canonical_reconciliation,
        packet,
    )


def _run(report: dict[str, Any], packet: dict[str, Any]) -> None:
    gateway = DashboardAdvisoryGateway(FrozenProjection(report["source_projection"]))
    factory = gateway._factory()
    report["model_id"] = factory.config.model_id
    report["provider_config"] = _provider_config(factory)
    try:
        run = run_fresh_synthesis_context_diagnostic(packet, factory=factory, question=QUESTION)
    except (AdvisoryUnavailable, AdvisoryValidationError) as error:
        candidate = _first_candidate(error.diagnostics)
        report.update(
            {
                "status": type(error).__name__,
                "candidate": candidate,
                "candidates": [candidate] if candidate is not None else [],
                "diagnostics": error.diagnostics,
                "usage": error.usage,
                "fresh_synthesis_context": error.fresh_synthesis_context,
                "private_first_structured_capture": _private_first_structured_capture(error),
            }
        )
    except Exception as error:  # pragma: no cover - live provider boundary
        report.update(
            {
                "status": "UNEXPECTED_ERROR",
                "error": f"{type(error).__name__}: {error}",
                "usage": getattr(error, "usage", {}),
                "diagnostics": getattr(error, "diagnostics", []),
                "fresh_synthesis_context": getattr(error, "fresh_synthesis_context", {}),
                "private_first_structured_capture": _private_first_structured_capture(error),
            }
        )
    else:
        candidate = run.result.model_dump(mode="json")
        report.update(
            {
                "status": "COMPLETE_DIAGNOSTIC_ONLY_FIRST_CANDIDATE",
                "candidate": candidate,
                "candidates": [candidate],
                "usage": run.usage,
                "tool_calls": run.tool_calls,
                "latency_ms": run.latency_ms,
                "runtime_events": run.runtime_events,
                "fresh_synthesis_context": run.fresh_synthesis_context,
                "private_first_structured_capture": {
                    "status": "VALIDATED",
                    "first_structured_raw_value": candidate,
                },
            }
        )
    finally:
        report["factory_usage"] = {
            "provenance": factory.provenance(),
            "ledger": factory.ledger.snapshot(),
            "ledger_request_count_scope": (
                "logical BudgetedModel request reservations; not a provider HTTP-attempt count"
            ),
            "provider_http_attempts": {
                "count": None,
                "status": "NOT_EXPOSED_BY_FACTORY_LEDGER",
                "note": (
                    "Strands may retry a tool-result-turn ValidationException with a request-local "
                    "normalization; this ledger does not expose that extra HTTP attempt."
                ),
            },
        }
        report["ledger"] = factory.ledger.snapshot()


def _write_private_report(output: Path, report: Mapping[str, Any]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(
        output,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, default=str)
        handle.write("\n")
    output.chmod(0o600)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="explicitly run one private, read-only first-candidate diagnostic",
    )
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    source = args.source.expanduser().resolve()
    if output.exists():
        parser.error(f"refusing to overwrite existing output: {output}")
    if not source.is_file():
        parser.error(f"source projection does not exist: {source}")
    if os.environ.get("MISSING20_AGENT_WORKFLOW", "single") != "single":
        parser.error("fresh-synthesis diagnostic is frozen to the single-agent workflow")

    source_projection, model_sources, canonical_reconciliation, packet = _build_packet(source)
    report: dict[str, Any] = {
        "scope": "private fresh-synthesis-context diagnostic; no business writes",
        "treatment": {
            "name": "fresh_synthesis_context",
            "effect_view": False,
            "first_candidate_only": True,
            "repairs": "disabled",
            "workflow": "single",
        },
        "comparison_limit": (
            "This first-candidate diagnostic omits repairs and is not the same workload as "
            "the prior eight-request repaired effect-view run."
        ),
        "status": "READY_OFFLINE",
        "started_at": datetime.now(UTC).isoformat(),
        "finished_at": None,
        "source_path": str(source),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "model_sources_sha256": _sha256(model_sources),
        "source_payload_sha256": {name: _sha256(value) for name, value in model_sources.items()},
        "canonical_reconciliation_sha256": _sha256(canonical_reconciliation),
        "source_projection": source_projection,
        "model_sources": model_sources,
        "packet_context": {
            "case_id": packet.get("case_id"),
            "case_class": packet.get("case_class"),
            "canonical_reconciliation": canonical_reconciliation,
        },
        "question": QUESTION,
        "sdk_version": _sdk_version(),
        "code_provenance": _code_provenance(),
        "provider_config": None,
        "factory_usage": {},
        "fresh_synthesis_context": {"message_sha256": None},
        "private_first_structured_capture": {
            "status": "NOT_RUN",
            "first_structured_raw_value": None,
        },
        "transport_boundary": {
            "fresh_context_message_sha256_scope": (
                "canonical application context before Bedrock SDK request formatting or "
                "retry normalization"
            ),
            "bedrock_sdk_tool_result_turn_retry": (
                "A tool-result-only user turn followed by the synthesis user prompt can be retried "
                "by Strands with a request-local neutral assistant separator after its specific "
                "ValidationException; persisted fresh context is not mutated."
            ),
            "request_accounting": (
                "Factory ledger request_count measures logical BudgetedModel requests. "
                "Provider HTTP "
                "attempts, including the native retry, are not exposed by that ledger."
            ),
        },
        "candidate_capture_scope": (
            "The first structured candidate only. A raw schema-rejected value is retained only in "
            "private_first_structured_capture with status UNVALIDATED; no repair or later "
            "candidate is requested."
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
    _write_private_report(output, report)
    print(f"status={report['status']} path={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
