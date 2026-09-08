"""Real Strands probe over unsolved, synthetic, source-separated counterfactuals."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.aws_preflight import load_identity, validate_identity
from the_missing_20.adapters.ambiguous_case_platform import AmbiguousCasePlatform
from the_missing_20.adapters.erpnext_source import _read_env_file
from the_missing_20.adapters.investigation_case_sources import (
    INVESTIGATION_VARIANTS,
    Variant,
    investigation_packet,
)
from the_missing_20.adapters.live_advisory_gateway import DashboardAdvisoryGateway
from the_missing_20.agents.live_advisory import (
    AdvisoryUnavailable,
    AdvisoryValidationError,
    run_live_advisory,
)
from the_missing_20.config import Settings

ROOT = Path(__file__).resolve().parents[1]
VARIANTS: tuple[Variant, ...] = INVESTIGATION_VARIANTS


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", choices=("1",), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--variant", choices=VARIANTS)
    parser.add_argument("--repetitions", type=int, default=1)
    args = parser.parse_args()
    if args.repetitions < 1:
        parser.error("--repetitions must be positive")
    settings = Settings.from_env(
        {
            **_read_env_file(ROOT / ".env"),
            "MISSING20_AGENT_PROVIDER": "bedrock",
            "MISSING20_ALLOW_AWS_MUTATIONS": "0",
        }
    )
    validate_identity(load_identity(settings), settings)
    rows = []
    selected_variants = (args.variant,) if args.variant else VARIANTS
    for repetition in range(1, args.repetitions + 1):
        for variant in selected_variants:
            rows.append(_run_variant(variant, repetition, settings))
            print(f"{variant} #{repetition}: {rows[-1]['status']}", flush=True)
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "scope": "Real Bedrock model; synthetic raw business records; no writes",
        "limitations": [
            "Business sources are production-shaped synthetic records, not customer "
            "production data",
            "Tools are case/run scoped and accept a query, but this fixture returns an "
            "admitted batch",
            "Quantity coverage is a deterministic completeness check, not a semantic judge",
            "Repairs receive evidence-derived evaluator feedback; inspect validation_retries",
        ],
        "repetitions": args.repetitions,
        "cases": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    expected_count = len(selected_variants) * args.repetitions
    return 0 if len(rows) == expected_count and all(row["status"] == "PASS" for row in rows) else 1


def _run_variant(variant: Variant, repetition: int, settings: Settings) -> dict[str, object]:
    gateway = DashboardAdvisoryGateway(AmbiguousCasePlatform(), settings=settings)
    packet = investigation_packet(variant)
    row: dict[str, object] = {
        "variant": variant,
        "repetition": repetition,
        "expected": packet["expected_disposition"],
    }
    try:
        run = run_live_advisory(
            packet,
            factory=gateway._factory(),
            question="Invoice INV-4817 failed matching. Investigate the source records, "
            "explain the causes and quantities, rule out alternatives, and tell "
            "the operator what can safely happen next.",
        )
        row.update(
            {
                "status": "PASS",
                "result": run.result.model_dump(mode="json"),
                "tools": run.tool_calls,
                "usage": run.usage,
                "latency_ms": run.latency_ms,
            }
        )
        if variant == "uncommitted_receipt" and not all(
            re.search(rf"\b{quantity}\b", run.result.reason) for quantity in (12, 8)
        ):
            row["status"] = "INCOMPLETE_EXPLANATION"
        required = {
            "uncommitted_receipt": {
                "read_erp_evidence",
                "read_collaboration_evidence",
                "read_airtable_evidence",
                "read_celigo_evidence",
            },
            "lost_ack": {"read_erp_evidence", "read_celigo_evidence"},
            "wrong_quality_lot": {"read_erp_evidence", "read_airtable_evidence"},
            "lookup_unavailable": {"read_erp_evidence"},
            "physical_shortage": {"read_erp_evidence", "read_collaboration_evidence"},
            "transfer_already_present": {"read_erp_evidence", "read_airtable_evidence"},
            "evidence_conflict": {"read_erp_evidence", "read_celigo_evidence"},
            "duplicate_invoice": {"read_erp_evidence"},
            "unit_price_variance": {"read_erp_evidence"},
            "uom_conversion_missing": {"read_erp_evidence", "read_celigo_evidence"},
            "po_revision_race": {"read_erp_evidence", "read_celigo_evidence"},
            "supplier_hold": {"read_erp_evidence"},
            "lot_trace_mismatch": {
                "read_erp_evidence",
                "read_airtable_evidence",
                "read_collaboration_evidence",
            },
            "normal_complete": {"read_erp_evidence"},
        }[variant]
        row["decisive_sources_read"] = required.issubset(run.tool_calls)
        if not row["decisive_sources_read"]:
            row["status"] = "INSUFFICIENT_SOURCE_COVERAGE"
    except (AdvisoryUnavailable, AdvisoryValidationError) as error:
        row.update({"status": "FAILED", "error": str(error)})
        if isinstance(error, AdvisoryValidationError):
            row["diagnostics"] = error.diagnostics
    return row


if __name__ == "__main__":
    raise SystemExit(main())
