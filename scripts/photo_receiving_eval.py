"""Evaluate licensed public photos through real Strands + the durable intake service.

Ground truth is read only by the scorer, never passed to the model. This pilot
measures visible-object candidates, not warehouse accuracy or ERP stock effects.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from the_missing_20.adapters.erpnext_source import _read_env_file  # noqa: E402
from the_missing_20.adapters.photo_receiving import PhotoReceiving  # noqa: E402
from the_missing_20.agents.photo_receiving import (  # noqa: E402
    StrandsPhotoReader,
    normalize_photo,
)
from the_missing_20.config import Settings  # noqa: E402

DEFAULT_MANIFEST = ROOT / "tests/fixtures/photo_receiving/manifest.json"


def load_cases(manifest: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = json.loads(manifest.read_text())["cases"]
    if not cases or len({case["id"] for case in cases}) != len(cases):
        raise ValueError("Fixture IDs must be nonempty and unique.")
    for case in cases:
        path = (manifest.parent / case["file"]).resolve()
        if not path.is_relative_to(manifest.parent.resolve()):
            raise ValueError("Fixture path leaves the manifest directory.")
        if not all(case.get(key) for key in ("source_url", "license", "attribution", "truth")):
            raise ValueError("Every photo needs a source, license, attribution and visual truth.")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != case["sha256"]:
            raise ValueError(f"Fixture bytes changed: {case['id']}")
        normalize_photo(raw)
    return cases


def score(state: dict[str, Any], truth: dict[str, Any]) -> dict[str, bool]:
    analysis = state.get("analysis", {})
    assessment = analysis.get("assessment", {})
    checks = {
        "real_model_response": analysis.get("provider") == "bedrock"
        and analysis.get("transport") == "strands_multimodal",
        "expected_state": state.get("status") in truth["statuses"],
        "no_stock_effect": state.get("stock_posted") is False
        and not state.get("draft")
        and not state.get("candidate"),
        "no_invented_identity": assessment.get("item_code") in truth["item_codes"]
        and assessment.get("supplier_lot") in truth["supplier_lots"],
    }
    for key in ("countable", "visibility", "receiving_unit", "label_declared_quantity"):
        if key in truth:
            checks[key] = assessment.get(key) == truth[key]
    if "visible_count" in truth:
        checks["exact_visible_count"] = state.get("count") == truth["visible_count"]
    if truth.get("reshoot_required"):
        # Text presence is machine-checkable; actual helpfulness requires visual review.
        checks["reshoot_text_present"] = bool(assessment.get("next_photo", "").strip())
    return checks


def run_case(service: PhotoReceiving, raw: bytes, truth: dict[str, Any]) -> dict[str, Any]:
    capture_id = service.create()["id"]
    encoded = base64.b64encode(raw).decode()
    state = service.upload(capture_id, encoded)
    replay = service.upload(capture_id, encoded) if state["status"] != "UNAVAILABLE" else None
    checks = score(state, truth)
    checks["duplicate_upload_is_same_event"] = replay == state
    checks["durable_readback"] = service.current(capture_id) == state
    return {
        "passed": all(checks.values()),
        "behavior_passed": all(value for key, value in checks.items() if key != "visibility"),
        "checks": checks,
        "state": state,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case", action="append", dest="case_ids")
    parser.add_argument("--repeats", type=int, default=1, choices=range(1, 11))
    parser.add_argument("--model-id", default="us.amazon.nova-pro-v1:0")
    args = parser.parse_args()
    cases = load_cases(args.manifest)
    if args.case_ids:
        if set(args.case_ids) - {case["id"] for case in cases}:
            parser.error("Unknown case ID.")
        cases = [case for case in cases if case["id"] in args.case_ids]
    if args.output.exists():
        parser.error("Keep previous results; choose a new output path.")
    settings = Settings.from_env(
        {**_read_env_file(ROOT / ".env"), **os.environ, "MISSING20_AGENT_PROVIDER": "bedrock"}
    )
    report: dict[str, Any] = {
        "started_at": datetime.now(UTC).isoformat(),
        "scope": "public-photo development pilot; no ERP configured; not a physical holdout",
        "manifest_sha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
        "reader_sha256": hashlib.sha256(
            (ROOT / "src/the_missing_20/agents/photo_receiving.py").read_bytes()
        ).hexdigest(),
        "intake_sha256": hashlib.sha256(
            (ROOT / "src/the_missing_20/adapters/photo_receiving.py").read_bytes()
        ).hexdigest(),
        "evaluator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "external_stock_writes": 0,
        "requested_model": args.model_id,
        "runs": [],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # New temporary storage isolates this probe from the user's active demo case.
    with tempfile.TemporaryDirectory(prefix="m20-public-photo-eval-") as directory:
        # Independent model repetitions need independent evidence stores. Keep
        # the same-capture replay check inside run_case: never disable production
        # deduplication just to obtain a second inference on a public fixture.
        for repetition in range(1, args.repeats + 1):
            service = PhotoReceiving(
                Path(directory) / f"captures-{repetition}.sqlite3",
                StrandsPhotoReader(settings, model_id=args.model_id),
            )
            try:
                for case in cases:
                    raw = (args.manifest.parent / case["file"]).read_bytes()
                    run = run_case(service, raw, case["truth"])
                    report["runs"].append({"case_id": case["id"], "repetition": repetition, **run})
                    report["passed"] = sum(item["passed"] for item in report["runs"])
                    report["behavior_passed"] = sum(
                        item["behavior_passed"] for item in report["runs"]
                    )
                    report["total"] = len(report["runs"])
                    args.output.write_text(json.dumps(report, indent=2) + "\n")
                    print(
                        json.dumps(
                            {
                                "case": case["id"],
                                "repetition": repetition,
                                "status": run["state"]["status"],
                                "checks": run["checks"],
                            }
                        ),
                        flush=True,
                    )
            finally:
                service.db.close()
    report["finished_at"] = datetime.now(UTC).isoformat()
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
