"""Cancel only our unreceived, unbilled, future-dated test PO; preserve its audit trail."""

import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode

from the_missing_20.adapters.demo_executor import ERPNextDemoExecutor

ROOT = Path(__file__).resolve().parents[2]
NAME = "PUR-ORD-2026-00012"
REPORT = ROOT / "artifacts/agent/2026-09-08-future-order-cancellation.json"


def main() -> None:
    client = ERPNextDemoExecutor.from_environment(ROOT)
    if client is None or client._environment != "demo":
        raise ValueError("Configured demo credentials required")
    doc = client._document("Purchase Order", NAME)
    assert doc["name"] == NAME and doc["company"] == "Missing 20 Automotive Demo"
    assert doc["transaction_date"] == "2026-09-09"
    assert len(doc["items"]) == 1 and doc["items"][0]["item_code"] == "M20-DEMO-CARTON"
    assert doc["items"][0]["qty"] == 40 and doc["items"][0]["uom"] == "Box"
    assert doc["per_received"] == 0 and doc["per_billed"] == 0
    for kind in ("Purchase Receipt", "Purchase Invoice"):
        query = urlencode(
            {
                "fields": json.dumps(["name", "docstatus"]),
                "filters": json.dumps([[kind + " Item", "purchase_order", "=", NAME]]),
                "limit_page_length": 2,
            }
        )
        assert (
            client._request("/api/resource/" + kind.replace(" ", "%20") + "?" + query)["data"] == []
        )
    record = (
        json.loads(REPORT.read_text())
        if REPORT.exists()
        else {
            "order": NAME,
            "reason": "Host UTC date was ahead of ERP site date",
            "prior_docstatus": doc["docstatus"],
            "cancel_attempted": False,
            "linked_receipts": [],
            "linked_invoices": [],
        }
    )
    if doc["docstatus"] == 1 and not record["cancel_attempted"]:
        record.update(cancel_attempted=True, attempted_at=datetime.now(UTC).isoformat())
        REPORT.write_text(json.dumps(record, indent=2) + "\n")
        client._request(
            "/api/method/frappe.client.cancel",
            method="POST",
            payload={"doctype": "Purchase Order", "name": NAME},
        )
    after = client._document("Purchase Order", NAME)
    record.update(docstatus=after["docstatus"], verified_at=datetime.now(UTC).isoformat())
    REPORT.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record, indent=2))
    assert after["docstatus"] == 2, "Cancellation unknown; do not amend or retry"


if __name__ == "__main__":
    main()
