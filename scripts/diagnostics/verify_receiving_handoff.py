"""Read-only acceptance of one posted photo receipt and its real SaaS readbacks."""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

from the_missing_20.adapters.demo_executor import ERPNextDemoExecutor
from the_missing_20.adapters.receiving_destinations import (
    AirtableReceipt,
    CeligoSlackReceipt,
    ReceivingAPI,
)
from the_missing_20.adapters.receiving_handoff import receipt_event, same_stock_effects
from the_missing_20.adapters.saas_evidence import SaaSEvidenceSource

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-directory", type=Path, required=True)
    parser.add_argument("--capture-id", required=True)
    parser.add_argument("--phase", choices=("before_restart", "after_restart"), required=True)
    parser.add_argument("--port", type=int, default=8893)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    runtime = args.runtime_directory.resolve()
    with sqlite3.connect(f"file:{runtime / 'photo-receiving.sqlite3'}?mode=ro", uri=True) as db:
        state = json.loads(
            db.execute("SELECT state FROM captures WHERE id=?", (args.capture_id,)).fetchone()[0]
        )
    event = receipt_event(state)
    assert event and event["quantity"] > 0
    client = ERPNextDemoExecutor.from_environment(ROOT)
    assert client is not None
    assert event["tenant"] == client._credentials.base_url
    doc = client._document("Purchase Receipt", event["receipt"])
    marker = doc["supplier_delivery_note"]
    assert marker == "M20 PHOTO " + args.capture_id and doc["docstatus"] == 1

    def rows(doctype, filters, fields):
        query = urlencode(
            {"filters": json.dumps(filters), "fields": json.dumps(fields), "limit_page_length": 5}
        )
        result = client._request(f"/api/resource/{doctype}?{query}")["data"]
        assert len(result) < 5, "Truncated lookup cannot prove unique effects"
        return result

    matches = rows(
        "Purchase%20Receipt", [["supplier_delivery_note", "=", marker]], ["name", "docstatus"]
    )
    assert matches == [{"name": event["receipt"], "docstatus": 1}]
    ledger = rows(
        "Stock%20Ledger%20Entry",
        [["voucher_no", "=", event["receipt"]], ["is_cancelled", "=", 0]],
        [
            "name",
            "actual_qty",
            "item_code",
            "warehouse",
            "voucher_detail_no",
            "voucher_type",
            "voucher_no",
            "company",
            "is_cancelled",
        ],
    )
    assert same_stock_effects(state["receipt"]["stock_ledger"], ledger)
    assert sum(row["actual_qty"] for row in ledger) == event["quantity"]
    assert len(doc["items"]) == 1
    line = doc["items"][0]
    assert line["purchase_order"] == event["purchase_order"]
    assert line["qty"] == event["quantity"] and line["stock_uom"] == event["uom"]
    assert line["item_code"] == event["item_code"]
    assert all(row["voucher_detail_no"] == line["name"] for row in ledger)

    config = json.loads((runtime / "handoff-config.json").read_text())
    api = ReceivingAPI(SaaSEvidenceSource.from_environment(repository_root=ROOT)._config)
    targets = [
        CeligoSlackReceipt(api, config["celigo_import_id"], config["celigo_connection_id"]),
        AirtableReceipt(api, config["airtable_table_id"]),
    ]
    with sqlite3.connect(f"file:{runtime / 'receiving-handoffs.sqlite3'}?mode=ro", uri=True) as db:
        handoffs = [
            (key, json.loads(payload), json.loads(raw))
            for key, payload, raw in db.execute("SELECT key, payload, state FROM handoffs")
        ]
    proofs = []
    for target in targets:
        matched = [
            (key, payload, raw)
            for key, payload, raw in handoffs
            if raw["route"] == target.route and payload["capture_id"] == args.capture_id
        ]
        assert len(matched) == 1
        key, retained_event, retained = matched[0]
        assert retained_event == event and retained["status"] == "VERIFIED"
        proof = target.find(event, key)  # GET only; detects duplicates or mismatched content.
        assert proof and proof["record_id"] == retained["evidence"]["record_id"]
        proofs.append({"key": key, "route": target.route, **proof})

    def local(path):
        with urlopen(f"http://127.0.0.1:{args.port}{path}", timeout=30) as response:
            return json.load(response)

    projection = local("/api/v1/agent-platform")
    history = local("/api/v1/agent-platform/history")
    assert projection["case_id"] == event["case_id"]
    quantities = projection["case_projection"]["case"]["quantities"]
    assert quantities["receipt_posted_quantity"] == event["quantity"]
    assert quantities["outstanding_order_quantity"] == quantities["ordered"] - event["quantity"]
    snapshot = {
        "checked_at": datetime.now(UTC).isoformat(),
        "case_id": event["case_id"],
        "capture_id": args.capture_id,
        "purchase_order": event["purchase_order"],
        "receipt": event["receipt"],
        "quantity": event["quantity"],
        "uom": event["uom"],
        "matching_receipts": matches,
        "stock_ledger": ledger,
        "ledger_ids_at_posting": event["stock_ledger_ids"],
        "ledger_ids_current": sorted(row["name"] for row in ledger),
        "same_stock_effects": True,
        "destinations": proofs,
        "quantities": quantities,
        "history_points": len(history.get("points", [])),
        "history_retained_records": history.get("coverage", {}).get("total_points"),
        "history_projection_revisions": history.get("projection_revisions", []),
        "history_metric_corrections": history.get("metric_corrections", []),
        "conversation_turns": len(projection.get("conversation", [])),
        "conversation": [
            {key: turn.get(key) for key in (
                "question", "answer", "evidence_ids", "tool_calls", "provider",
                "latency_ms", "usage", "context_turns",
            )}
            for turn in projection.get("conversation", [])
        ],
        "passed": True,
    }
    report = (
        json.loads(args.output.read_text())
        if args.output.exists()
        else {
            "scope": "Actual external GET readbacks; demo public photo is not real shipment proof.",
            "business_writes_in_verifier": 0,
        }
    )
    report[args.phase] = snapshot
    if args.phase == "after_restart":
        before = report["before_restart"]
        fields = (
            "receipt",
            "quantity",
            "uom",
            "matching_receipts",
            "destinations",
            "quantities",
            "history_points",
        )
        assert all(before[name] == snapshot[name] for name in fields), (
            "Unexpected effect or fabricated history after restart"
        )
        # Older reports retained a shorter field projection. The complete fresh
        # ledger has already been matched against the immutable receipt readback.
        stable = ("actual_qty", "item_code", "warehouse", "voucher_detail_no")
        assert sorted(
            tuple(row[key] for key in stable) for row in before["stock_ledger"]
        ) == sorted(tuple(row[key] for key in stable) for row in ledger), (
            "Stock effects changed after restart"
        )
        report["restart_no_duplicate_effects"] = True
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(snapshot, indent=2))


if __name__ == "__main__":
    main()
