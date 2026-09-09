"""One non-posting diagnostic draft; never retry a recorded write or change a capture.

The diagnostic is not a receiving observation and must never be submitted.
Reusing this script after a recorded attempt only looks up its stable marker.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode

from the_missing_20.adapters.demo_executor import ERPNextDemoExecutor

ROOT = Path(__file__).resolve().parents[2]
CAPTURE = "396d287426f42cc762a427b07c4b0d2a"
MARKER = "M20 DIAGNOSTIC PHOTO SCHEMA 20260908-01"
REPORT = ROOT / "artifacts/agent/2026-09-08-photo-draft-schema-probe.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-diagnostic-draft", action="store_true")
    args = parser.parse_args()
    client = ERPNextDemoExecutor.from_environment(ROOT)
    if client is None or client._environment != "demo":
        raise ValueError("Configured demo credentials required")
    database = ROOT / ".missing20-goods-live-20260908/photo-receiving.sqlite3"
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as db:
        row = db.execute("SELECT state FROM captures WHERE id=?", (CAPTURE,)).fetchone()
    state = json.loads(row[0])
    candidate = state["candidate"]
    assert candidate["purchase_order"] == "PUR-ORD-2026-00012"
    assert candidate["quantity"] == 1
    assert candidate["items"][0]["item_code"] == "M20-DEMO-CARTON"
    assert candidate["items"][0]["uom"] == "Box"
    report = (
        json.loads(REPORT.read_text())
        if REPORT.exists()
        else {
            "marker": MARKER,
            "purpose": "schema diagnosis only; never submit",
            "purchase_order": candidate["purchase_order"],
            "writes_attempted": 0,
        }
    )
    query = urlencode(
        {
            "filters": json.dumps([["supplier_delivery_note", "=", MARKER]]),
            "fields": json.dumps(["name", "docstatus"]),
            "limit_page_length": 2,
        }
    )
    matches = client._request(f"/api/resource/Purchase%20Receipt?{query}")["data"]
    assert len(matches) <= 1
    if args.write_diagnostic_draft and not matches and not report["writes_attempted"]:
        report.update(writes_attempted=1, attempted_at=datetime.now(UTC).isoformat())
        REPORT.write_text(json.dumps(report, indent=2) + "\n")
        payload = {
            k: v
            for k, v in candidate.items()
            if k not in {"po_version", "quantity", "purchase_order"}
        }
        try:
            result = client._request(
                "/api/resource/Purchase%20Receipt",
                method="POST",
                payload={**payload, "docstatus": 0, "supplier_delivery_note": MARKER},
            )
            report["returned_name"] = result.get("data", {}).get("name")
        except Exception as error:
            detail = str(error)
            for secret in (client._credentials.api_key, client._credentials.api_secret):
                detail = detail.replace(secret, "[credential]") if secret else detail
            detail = re.sub(r"[\w.+-]+@[\w.-]+", "[account]", detail)
            detail = re.sub(r"https?://\S+", "[provider]", detail)
            report["failure"] = {"type": type(error).__name__, "detail": detail[:500]}
        matches = client._request(f"/api/resource/Purchase%20Receipt?{query}")["data"]
    report.update(matches=matches, checked_at=datetime.now(UTC).isoformat())
    if matches:
        doc = client._document("Purchase Receipt", matches[0]["name"])
        assert doc["docstatus"] == 0, "Diagnostic must never be submitted"
    REPORT.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
