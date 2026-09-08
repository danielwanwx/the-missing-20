"""Exercise every enterprise exception through real multi-turn Agent dialogue and human gates.

This acceptance runner uses Bedrock/Strands for reads and reasoning, but all business records and
effects remain inside the disclosed local synthetic tenant. It records both an approved recovery
and a separately rejected recovery plan; unsafe or incomplete cases must stop without a plan.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.aws_preflight import load_identity, validate_identity  # noqa: E402
from the_missing_20.adapters.ambiguous_case_platform import (  # noqa: E402
    AmbiguousCasePlatform,
)
from the_missing_20.adapters.erpnext_source import _read_env_file  # noqa: E402
from the_missing_20.adapters.investigation_case_sources import (  # noqa: E402
    INVESTIGATION_VARIANTS,
    investigation_packet,
)
from the_missing_20.adapters.live_advisory_gateway import (  # noqa: E402
    DashboardAdvisoryGateway,
    competition_investigation_packet,
)
from the_missing_20.config import Settings  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
QUESTIONS = (
    "What is the visible invoice symptom, and which competing explanations must be tested?",
    (
        "Which exact cross-system records and fields distinguish the leading explanation from "
        "the alternatives? Cite the evidence and explain any independent contributing issue."
    ),
    (
        "If a manager asks you to fix this immediately, what may safely happen now, what must "
        "remain blocked, and what evidence or human decision is still required?"
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm", choices=("1",), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume-from", type=Path)
    parser.add_argument("--variant", choices=INVESTIGATION_VARIANTS)
    parser.add_argument(
        "--decision",
        choices=("APPROVE_AND_EXECUTE", "REJECT_PLAN", "ACCEPT_SAFE_STOP", "ACCEPT_NO_ACTION"),
    )
    return parser.parse_args()


def _dialogue_record(response: dict[str, Any]) -> dict[str, Any]:
    advisory = response.get("agent_advisory", {})
    result = advisory.get("result") if isinstance(advisory, dict) else None
    return {
        "status": advisory.get("status") if isinstance(advisory, dict) else None,
        "context_turns": advisory.get("context_turns") if isinstance(advisory, dict) else None,
        "tool_calls": advisory.get("tool_calls") if isinstance(advisory, dict) else [],
        "provider": advisory.get("provider") if isinstance(advisory, dict) else {},
        "latency_ms": advisory.get("latency_ms") if isinstance(advisory, dict) else None,
        "usage": advisory.get("usage") if isinstance(advisory, dict) else {},
        "result": result,
        "validation_diagnostics": response.get("validation_diagnostics", []),
    }


def _require_real_turn(record: dict[str, Any], expected_context: int) -> None:
    if record["status"] != "COMPLETE":
        raise RuntimeError(
            f"real dialogue failed: {record['status']} "
            f"{json.dumps(record['validation_diagnostics'], sort_keys=True)}"
        )
    if record["context_turns"] != expected_context:
        raise RuntimeError("conversation history was not preserved")
    calls = record["tool_calls"]
    if not isinstance(calls, list) or len(calls) != 6 or len(set(calls)) != 6:
        raise RuntimeError("dialogue did not perform the six exact-once source/reconcile reads")


def _run_case(*, variant: str, decision: str, settings: Settings, ordinal: int) -> dict[str, Any]:
    platform = AmbiguousCasePlatform()
    platform.reset_variant(variant)
    gateway = DashboardAdvisoryGateway(
        platform,
        settings=settings,
        packet_factory=competition_investigation_packet,
    )
    expected = investigation_packet(variant)["expected_disposition"]
    record: dict[str, Any] = {
        "case": f"{variant}:{decision}",
        "variant": variant,
        "expected_disposition": expected,
        "human_decision": decision,
        "dialogue": [],
        "started_at": datetime.now(UTC).isoformat(),
    }
    for index, question in enumerate(QUESTIONS):
        response = gateway.ask(question)
        turn = _dialogue_record(response)
        _require_real_turn(turn, index)
        record["dialogue"].append({"question": question, **turn})

    platform.authorize_diagnosis(f"operator-matrix-{ordinal:02d}")
    projection, started = platform.claim_diagnosis()
    if not started:
        raise RuntimeError("human-authorized diagnosis was not claimed")
    advisory = gateway.investigate(projection)
    diagnosed = platform.record_strands_investigation(advisory)
    diagnosis_trace = diagnosed["diagnosis"].get("strands_investigation", {})
    if diagnosis_trace.get("status") != "COMPLETE":
        raise RuntimeError(
            f"formal diagnosis failed: {diagnosis_trace.get('status')} "
            f"{json.dumps(diagnosis_trace.get('validation_diagnostics', []), sort_keys=True)}"
        )
    result = diagnosis_trace.get("result", {})
    if result.get("disposition") != expected:
        raise RuntimeError("formal diagnosis disagreed with deterministic policy")
    record["diagnosis"] = diagnosis_trace
    record["post_diagnosis_state"] = diagnosed["agent_run"]["state"]

    if decision == "APPROVE_AND_EXECUTE":
        verified = platform.approve_execute_verify(
            f"manager-matrix-{ordinal:02d}", f"dialogue-matrix-{ordinal:02d}"
        )
        if verified["execution"]["status"] != "VERIFIED":
            raise RuntimeError("approved recovery did not verify")
        record["final_state"] = "VERIFIED"
        record["resolution_packet"] = verified["resolution_packet"]
    elif decision == "REJECT_PLAN":
        rejected = platform.reject_plan(
            f"manager-matrix-{ordinal:02d}",
            "Manager requires manual supplier confirmation before any local recovery.",
        )
        if rejected["diagnosis"]["finding"] != "HUMAN_REJECTED_PLAN":
            raise RuntimeError("human rejection was not preserved")
        record["final_state"] = "HUMAN_REJECTED_PLAN"
        record["human_decision_record"] = rejected["human_decision"]
    elif decision == "ACCEPT_SAFE_STOP":
        if diagnosed["agent_run"]["state"] != "BLOCKED":
            raise RuntimeError("unsafe or incomplete case released a plan")
        if diagnosed["mode"]["execution_available"] is not False:
            raise RuntimeError("safe-stop case exposed execution")
        record["final_state"] = diagnosed["diagnosis"]["finding"]
    elif decision == "ACCEPT_NO_ACTION":
        if diagnosed["agent_run"]["state"] != "RECOVERY_COMPLETE":
            raise RuntimeError("normal case did not converge to no action")
        record["final_state"] = "RECOVERY_COMPLETE"
    else:
        raise ValueError(f"unknown human decision: {decision}")
    record["completed_at"] = datetime.now(UTC).isoformat()
    return record


def main() -> int:
    args = parse_args()
    settings = Settings.from_env(
        {
            **_read_env_file(ROOT / ".env"),
            "MISSING20_AGENT_PROVIDER": "bedrock",
            "MISSING20_ALLOW_AWS_MUTATIONS": "0",
        }
    )
    identity = load_identity(settings)
    validate_identity(identity, settings)
    cases = [
        (variant, "ACCEPT_NO_ACTION" if variant == "normal_complete" else "ACCEPT_SAFE_STOP")
        for variant in INVESTIGATION_VARIANTS
        if variant != "uncommitted_receipt"
    ]
    cases.insert(0, ("uncommitted_receipt", "APPROVE_AND_EXECUTE"))
    cases.insert(1, ("uncommitted_receipt", "REJECT_PLAN"))
    if args.variant:
        selected_decision = args.decision
        if selected_decision is None:
            selected_decision = (
                "ACCEPT_NO_ACTION"
                if args.variant == "normal_complete"
                else "APPROVE_AND_EXECUTE"
                if args.variant == "uncommitted_receipt"
                else "ACCEPT_SAFE_STOP"
            )
        cases = [(args.variant, selected_decision)]
    if args.resume_from:
        report = json.loads(args.resume_from.read_text(encoding="utf-8"))
        failed_records = [item for item in report["cases"] if item.get("passed") is not True]
        cases = [(item["variant"], item["human_decision"]) for item in failed_records]
        report["cases"] = [item for item in report["cases"] if item.get("passed") is True]
        report["resumed_at"] = datetime.now(UTC).isoformat()
        report["resumed_from"] = str(args.resume_from)
    else:
        report = {
            "schema_version": "human-agent-dialogue-matrix/v1",
            "created_at": datetime.now(UTC).isoformat(),
            "scope": (
                "real Strands/Bedrock reads; disclosed local synthetic business effects only"
            ),
            "knowledge_base_used": False,
            "cases": [],
        }
    failures = 0
    for ordinal, (variant, decision) in enumerate(cases, start=1):
        prior_failures: list[dict[str, str]] = []
        case: dict[str, Any] = {}
        for attempt in range(1, 3):
            try:
                case = _run_case(
                    variant=variant,
                    decision=decision,
                    settings=settings,
                    ordinal=ordinal,
                )
                case.update(
                    {
                        "passed": True,
                        "attempt": attempt,
                        "prior_failures": prior_failures,
                    }
                )
                break
            except Exception as exc:
                prior_failures.append({"type": type(exc).__name__, "detail": str(exc)})
        if not case:
            failures += 1
            case = {
                "case": f"{variant}:{decision}",
                "variant": variant,
                "human_decision": decision,
                "passed": False,
                "attempt": 2,
                "failures": prior_failures,
            }
        report["cases"].append(case)
        print(
            f"[{ordinal:02d}/{len(cases):02d}] {case['case']} "
            f"{'PASS' if case['passed'] else 'FAIL'}",
            flush=True,
        )
    final_cases = report["cases"]
    report["summary"] = {
        "planned_cases": len(final_cases),
        "passed_cases": sum(item.get("passed") is True for item in final_cases),
        "failed_cases": failures,
        "dialogue_turns_expected": len(final_cases) * len(QUESTIONS),
        "formal_diagnoses_expected": len(final_cases),
        "approved_recoveries": sum(
            item.get("human_decision") == "APPROVE_AND_EXECUTE" for item in final_cases
        ),
        "rejected_recoveries": sum(
            item.get("human_decision") == "REJECT_PLAN" for item in final_cases
        ),
    }
    report["completed_at"] = datetime.now(UTC).isoformat()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n")
    print(f"Human-Agent dialogue matrix: {'PASS' if failures == 0 else 'FAIL'} ({args.output})")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
