"""Real Strands probe over unsolved, synthetic, source-separated counterfactuals."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from scripts.aws_preflight import load_identity, validate_identity
from the_missing_20.adapters.ambiguous_case_platform import AmbiguousCasePlatform
from the_missing_20.adapters.erpnext_source import _read_env_file
from the_missing_20.adapters.investigation_case_sources import (
    INVESTIGATION_VARIANTS,
    Variant,
    investigation_packet,
)
from the_missing_20.adapters.live_advisory_gateway import DashboardAdvisoryGateway
from the_missing_20.adapters.role_task_journal import RoleTaskJournal
from the_missing_20.agents.live_advisory import (
    AdvisoryUnavailable,
    AdvisoryValidationError,
    run_live_advisory,
)
from the_missing_20.config import Settings

ROOT = Path(__file__).resolve().parents[1]
VARIANTS: tuple[Variant, ...] = INVESTIGATION_VARIANTS


def _acceptance_reporting(*, boundary_passed: bool) -> dict[str, object]:
    """Report only checks this probe performed, never infer business acceptance."""
    return {
        "status_scope": "MECHANICAL_BOUNDARY_ONLY",
        "boundary_status": "PASS" if boundary_passed else "FAIL",
        # The current result has no independently validated typed decision basis,
        # and this probe does not perform independent semantic answer review.
        "basis_status": "NOT_VALIDATED",
        "answer_quality_status": "NOT_REVIEWED",
        "business_acceptance": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", choices=("1",), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--variant", choices=VARIANTS)
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--workflow", choices=("single", "roles"), default="single")
    args = parser.parse_args()
    if args.repetitions < 1:
        parser.error("--repetitions must be positive")
    settings = Settings.from_env(
        {
            **_read_env_file(ROOT / ".env"),
            **os.environ,
            "MISSING20_AGENT_PROVIDER": "bedrock",
            "MISSING20_ALLOW_AWS_MUTATIONS": "0",
        }
    )
    validate_identity(load_identity(settings), settings)
    rows = []
    journal = (
        RoleTaskJournal(args.output.with_suffix(".tasks.sqlite3"))
        if args.workflow == "roles"
        else None
    )
    selected_variants = (args.variant,) if args.variant else VARIANTS
    for repetition in range(1, args.repetitions + 1):
        for variant in selected_variants:
            rows.append(_run_variant(variant, repetition, settings, journal=journal))
            row = rows[-1]
            print(
                f"{variant} #{repetition}: mechanical_status={row['status']}; "
                f"boundary={row['boundary_status']}; basis={row['basis_status']}; "
                f"answer_quality={row['answer_quality_status']}; business_acceptance=false",
                flush=True,
            )
    expected_count = len(selected_variants) * args.repetitions
    boundary_passed = len(rows) == expected_count and all(
        row["boundary_status"] == "PASS" for row in rows
    )
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "scope": "Real Bedrock model; synthetic raw business records; no writes",
        **_acceptance_reporting(boundary_passed=boundary_passed),
        "exit_code_scope": "MECHANICAL_BOUNDARY_ONLY",
        "limitations": [
            "Business sources are production-shaped synthetic records, not customer "
            "production data",
            "Tools are case/run scoped and accept a query, but this fixture returns an "
            "admitted batch",
            "Quantity coverage is a deterministic completeness check, not a semantic judge",
            "Repairs receive evidence-derived evaluator feedback; inspect validation_retries",
            "Legacy status and process exit code cover mechanical boundary checks only; "
            "neither establishes business acceptance",
        ],
        "repetitions": args.repetitions,
        "workflow": args.workflow,
        "cases": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    return 0 if boundary_passed else 1


def _run_variant(
    variant: Variant, repetition: int, settings: Settings, *, journal: RoleTaskJournal | None = None
) -> dict[str, object]:
    gateway = DashboardAdvisoryGateway(
        AmbiguousCasePlatform(), settings=settings, delegation_journal=journal
    )
    packet = investigation_packet(variant)
    from uuid import uuid4

    packet["run_id"] = uuid4().hex
    packet["explanation_scope"] = "full_investigation"
    row: dict[str, object] = {
        "variant": variant,
        "repetition": repetition,
        "expected": packet["expected_disposition"],
    }
    factory = gateway._factory()
    row["model_id"] = factory.config.model_id
    events: list[Mapping[str, Any]] = []
    started = time.perf_counter()
    try:
        run = run_live_advisory(
            packet,
            factory=factory,
            question="Invoice INV-4817 failed matching. Investigate the source records, "
            "explain the causes and quantities, rule out alternatives, and tell "
            "the operator what can safely happen next.",
            delegation_journal=journal,
            on_runtime_event=events.append,
        )
        row.update(
            {
                "status": "PASS",
                "result": run.result.model_dump(mode="json"),
                "tools": run.tool_calls,
                "usage": run.usage,
                "latency_ms": run.latency_ms,
                "runtime_events": run.runtime_events,
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
        row["diagnostics"] = error.diagnostics
        row["usage"] = error.usage
    finally:
        row["latency_ms"] = int((time.perf_counter() - started) * 1000)
        row["runtime_events"] = events
        if journal is not None:
            scopes = {str(event["case_scope"]) for event in events if "case_scope" in event}
            row["role_tasks"] = [task for scope in scopes for task in journal.tasks(scope)]
    row.update(_acceptance_reporting(boundary_passed=row["status"] == "PASS"))
    return row


if __name__ == "__main__":
    raise SystemExit(main())
