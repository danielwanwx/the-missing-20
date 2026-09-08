"""Run the current HTTP case path with real Strands and an isolated demo store.

Expected outcomes stay application-side, outside model tools. This is one
case's acceptance run, not a complete quality evaluation. No external business
system writes are permitted.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen
from uuid import uuid4

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.aws_preflight import load_identity, validate_identity
from scripts.decision_workspace_server import DecisionWorkspaceServer
from the_missing_20.adapters.ambiguous_case_platform import AmbiguousCasePlatform
from the_missing_20.adapters.erpnext_source import ERPNextEvidenceSource, _read_env_file
from the_missing_20.adapters.live_advisory_gateway import (
    DashboardAdvisoryGateway,
    connected_competition_investigation_packet,
)
from the_missing_20.adapters.saas_evidence import SaaSEvidenceSource
from the_missing_20.config import Settings

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm", choices=("1",), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    settings = Settings.from_env(
        {
            **_read_env_file(ROOT / ".env"),
            "MISSING20_AGENT_PROVIDER": "bedrock",
            "MISSING20_ALLOW_AWS_MUTATIONS": "0",
        }
    )
    validate_identity(load_identity(settings), settings)
    run_id = f"backend-real-{uuid4().hex}"
    store_path = args.output.parent / run_id / "case-console.sqlite3"
    platform = AmbiguousCasePlatform(store_path=store_path)
    erp_evidence = ERPNextEvidenceSource.from_environment(repository_root=ROOT)
    saas_evidence = SaaSEvidenceSource.from_environment(repository_root=ROOT)
    gateway = DashboardAdvisoryGateway(
        platform,
        settings=settings,
        packet_factory=lambda projection: connected_competition_investigation_packet(
            projection,
            erp_evidence=erp_evidence.current(),
            saas_evidence=saas_evidence.current(),
        ),
    )
    server = DecisionWorkspaceServer(
        ("127.0.0.1", 0),
        ROOT,
        runtime_directory=store_path.parent,
        agent_platform=platform,
        agent_advisory=gateway,
        live_sources_autostart=False,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}/api/v1/agent-platform"
    report: dict[str, Any] = {
        "run_id": run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "scope": "real Strands/Bedrock; local synthetic business writes only",
        "identity_verified": True,
        "maximum_model_runs": 3,
        "estimated_cost_cap_usd": "0.24 (three per-run 0.08 engineering caps)",
        "limitations": [
            "Normalized business records are synthetic demo data; each Agent turn also "
            "carries fresh read-only receipts from the connected demo SaaS records.",
            "Execution changes only the local synthetic tenant; external SaaS writes are disabled.",
            "The four-case counterfactual probe separately measures broad diagnosis behavior.",
        ],
        "steps": [],
    }
    steps = report["steps"]

    def post(action: str, payload: dict[str, object]) -> dict[str, Any]:
        started = time.monotonic()
        request = Request(
            f"{base}/{action}",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=130) as response:
            result: dict[str, Any] = json.load(response)
        steps.append(
            {
                "action": action,
                "latency_ms": round((time.monotonic() - started) * 1000),
                "response": result,
            }
        )
        print(f"Completed {action}", flush=True)
        return result

    def require_real(response: dict[str, Any], diagnosis: bool = False) -> None:
        trace = (
            response["diagnosis"]["strands_investigation"]
            if diagnosis
            else response["agent_advisory"]
        )
        if trace.get("status") != "COMPLETE" or not trace.get("tool_calls"):
            raise RuntimeError(f"Real agent did not complete: {trace.get('status')}")

    try:
        initial = platform.current()
        initial_mode = initial["mode"]
        assert isinstance(initial_mode, dict)
        assert initial_mode["provider_writes"] == "LOCAL_SYNTHETIC_ONLY"
        diagnosed = post("diagnose", {"operator_id": "Backend acceptance demo manager"})
        require_real(diagnosed, diagnosis=True)
        answer = post(
            "ask",
            {
                "question": (
                    "Why is the invoice held? Investigate the competing explanations, "
                    "cite source evidence and quantities, and explain the safe next step."
                )
            },
        )
        require_real(answer)
        verified = post(
            "approve-and-execute",
            {
                "manager_id": "Backend acceptance demo manager",
                "idempotency_key": run_id,
            },
        )
        assert verified["execution"]["status"] == "VERIFIED"
        assert verified["demo_case"]["case"]["quantities"]["available"] == 100
        assert verified["demo_case"]["case"]["invoice_held"] is False
        closing = post(
            "ask",
            {
                "question": (
                    "Is this case now resolved? Cite the post-recovery evidence, "
                    "state the quantities "
                    "and invoice status, and identify whether the effects were local synthetic "
                    "or external provider writes."
                )
            },
        )
        require_real(closing)
        assert closing["agent_advisory"]["result"]["disposition"] == "RECOVERY_COMPLETE"
        explanations = {
            "diagnosis": diagnosed["diagnosis"]["strands_investigation"]["result"]["reason"],
            "answer": answer["agent_advisory"]["result"]["reason"],
        }
        # Minimal completeness check, not a semantic judge: a disposition alone
        # must not pass a demo whose value is explaining two distinct quantities.
        report["explanation_quantity_coverage"] = {
            name: all(re.search(rf"\b{quantity}\b", text) for quantity in (12, 8))
            for name, text in explanations.items()
        }
        if not all(report["explanation_quantity_coverage"].values()):
            raise RuntimeError("Agent explanation omitted one or both causal quantities")
        report["status"] = "PASS_SOURCE_SEPARATED_E2E"
    except Exception as exc:
        report["status"] = "FAILED"
        report["error"] = {"type": type(exc).__name__, "detail": str(exc)}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        report["completed_at"] = datetime.now(UTC).isoformat()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n")
    print(f"{report['status']}: {args.output}", flush=True)
    return 0 if report["status"] == "PASS_SOURCE_SEPARATED_E2E" else 1


if __name__ == "__main__":
    raise SystemExit(main())
