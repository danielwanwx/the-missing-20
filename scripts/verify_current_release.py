"""Verify the public current-hero evidence package used by judges and Devpost."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PROOF = ROOT / "artifacts" / "audits" / "2026-09-07-current-hero-proof.json"
LIVE_CAPTURE = ROOT / "artifacts" / "audits" / "2026-09-07-current-hero-live-snapshot.json"


def _require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    proof_path = Path(os.environ.get("MISSING20_RELEASE_PROOF", PROOF))
    capture_path = Path(os.environ.get("MISSING20_RELEASE_CAPTURE", LIVE_CAPTURE))
    try:
        proof: dict[str, Any] = json.loads(proof_path.read_text(encoding="utf-8"))
        capture_bytes = capture_path.read_bytes()
        snapshot: dict[str, Any] = json.loads(capture_bytes)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Current hero release: BLOCKED ({exc})")
        return 2

    source_capture = proof.get("source_capture", {})
    environment = proof.get("environment", {})
    agent = proof.get("agent", {})
    approval = proof.get("approval", {})
    execution = proof.get("execution", {})
    post = proof.get("verified_postconditions", {})
    boundary = proof.get("claim_boundary", {})
    mode = snapshot.get("mode", {})
    judge = snapshot.get("judge_proof", {})
    raw_execution = snapshot.get("execution", {})
    resolution = snapshot.get("resolution_packet", {})
    raw_approval = resolution.get("approval", {})
    effects = resolution.get("effects", {})
    raw_post = resolution.get("post_state", {})
    value_proof = snapshot.get("value_proof", {})
    observed_value = value_proof.get("observed", {})
    value_assertions = value_proof.get("assertions", {})
    evidence_catalog = snapshot.get("evidence_catalog", {})
    ledger = evidence_catalog.get("MAT-PRE-2026-00001:ledger", {})
    ledger_assertions = ledger.get("assertions", {})
    ledger_totals = ledger.get("totals", {})
    activity = snapshot.get("activity", [])
    failures: list[str] = []

    capture_digest = hashlib.sha256(capture_bytes).hexdigest()
    _require(
        source_capture.get("path") == str(LIVE_CAPTURE.relative_to(ROOT)),
        "proof does not name the raw live capture",
        failures,
    )
    _require(
        source_capture.get("sha256") == capture_digest,
        "raw live capture digest does not match the release manifest",
        failures,
    )
    _require(
        snapshot.get("schema_version") == "missing20-agent-platform/v1",
        "unexpected live capture schema",
        failures,
    )
    _require(
        environment.get("source_provenance") == mode.get("provenance") == "live-read",
        "source is not a live read",
        failures,
    )
    _require(
        environment.get("provider_writes") == mode.get("provider_writes") == "DEMO_GUARDED",
        "write scope is not guarded",
        failures,
    )
    _require(
        agent.get("runtime") == judge.get("runtime") == "real_strands",
        "real Strands runtime is not evidenced",
        failures,
    )
    _require(
        agent.get("provider") == judge.get("provider", {}).get("provider") == "bedrock",
        "Bedrock provider is not evidenced",
        failures,
    )
    raw_trace = snapshot.get("diagnosis", {}).get("strands_investigation", {})
    _require(
        agent.get("tool_calls") == raw_trace.get("tool_calls")
        and len(agent.get("tool_calls", [])) == judge.get("source_checks") == 6,
        "six scoped tool calls are not evidenced",
        failures,
    )
    _require(
        agent.get("sdk_hook_events") == judge.get("sdk_hook_events") == 22,
        "SDK lifecycle trace is incomplete",
        failures,
    )
    _require(
        agent.get("write_performed") is raw_trace.get("result", {}).get("write_performed") is False,
        "agent crossed the no-write boundary",
        failures,
    )
    _require(
        approval.get("approval_id")
        == raw_approval.get("approval_id")
        == raw_execution.get("approval_id"),
        "approval identity is not bound through execution",
        failures,
    )
    _require(
        approval.get("plan_digest") == raw_approval.get("plan_digest")
        and approval.get("scope") == raw_approval.get("scope")
        and approval.get("run_id") == raw_approval.get("run_id"),
        "approval is not bound to the captured plan, scope, and run",
        failures,
    )
    _require(
        execution.get("status")
        == raw_execution.get("status")
        == resolution.get("status")
        == "VERIFIED",
        "execution is not verified",
        failures,
    )
    _require(
        execution.get("provenance") == resolution.get("provenance") == "live-provider-write",
        "external write is not evidenced",
        failures,
    )
    effect_pairs = {
        "quality_release_transfer": "quality_release_transfer",
        "sales_order": "sales_order",
        "delivery_note": "delivery_note",
        "sales_invoice": "sales_invoice",
        "celigo_receipt": "celigo_receipt",
    }
    for proof_key, raw_key in effect_pairs.items():
        _require(
            execution.get(proof_key) == effects.get(raw_key),
            f"captured effect mismatch for {proof_key}",
            failures,
        )
    _require(raw_execution.get("erp_verified") is True, "ERP reread is not verified", failures)
    _require(
        raw_execution.get("order_to_cash_verified") is True,
        "order-to-cash is not verified",
        failures,
    )
    _require(
        post.get("available_quantity") == raw_post.get("available") == 20.0,
        "available quantity is not 20",
        failures,
    )
    _require(
        post.get("delivered_quantity") == observed_value.get("delivered_quantity") == 20.0,
        "delivered quantity is not 20",
        failures,
    )
    _require(
        post.get("customer_billed_revenue")
        == raw_post.get("customer_billed_revenue")
        == observed_value.get("billed_revenue")
        == 42000.0,
        "billed revenue is not 42000",
        failures,
    )
    _require(
        value_proof.get("provenance") == "ERPNext / Frappe Cloud live reread"
        and value_assertions.get("order_to_cash_closed_loop_verified") is True,
        "value proof is not an authoritative live reread",
        failures,
    )
    _require(
        ledger.get("provenance") == "live-provider-read"
        and ledger_assertions.get("stock_ledger_present") is True
        and ledger_assertions.get("general_ledger_present") is True
        and ledger_assertions.get("debits_equal_credits") is True,
        "ledger evidence is incomplete",
        failures,
    )
    _require(
        ledger_totals.get("debit") == ledger_totals.get("credit") == 94800.0,
        "ledger is not balanced",
        failures,
    )
    event_types = [event.get("event_type") for event in activity if isinstance(event, dict)]
    for event_type in (
        "manager.approval.granted",
        "agent.execution.completed",
        "agent.resolution_packet.issued",
        "agent.execution.verified",
    ):
        _require(event_type in event_types, f"missing lifecycle event {event_type}", failures)
    _require(
        len(
            {effects.get("sales_order"), effects.get("delivery_note"), effects.get("sales_invoice")}
        )
        == 3,
        "order-to-cash effects are not uniquely identified",
        failures,
    )
    _require(
        boundary.get("causal_revenue_increase_proven") is False,
        "causal claim boundary is missing",
        failures,
    )

    if failures:
        print("Current hero release: BLOCKED (" + "; ".join(failures) + ")")
        return 2
    print(
        "Current hero release: PASS "
        "(real_strands, live_provider_write, manager_gate, 20 delivered, "
        "USD 42000 billed)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
