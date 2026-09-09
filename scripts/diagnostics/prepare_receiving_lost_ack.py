"""One real demo receipt with an explicitly injected lost application ACK.

Use a fresh, pre-provisioned one-carton demo arrival. This exercises actual ERP
posting, not a fake transport. The public photo and typed scan stand in for the
operator's physical input and explicit receipt confirmation. No invoice/payment.
Restart the normal workspace afterwards to test automatic lookup-only recovery.
Never rerun this command to recover an uncertain write.
"""

from __future__ import annotations

import argparse
import base64
import json
from datetime import UTC, datetime
from pathlib import Path

from the_missing_20.adapters.demo_executor import ERPNextDemoExecutor
from the_missing_20.adapters.photo_receiving import PhotoReceiptERP, PhotoReceiving
from the_missing_20.agents.photo_receiving import StrandsPhotoReader
from the_missing_20.config import Settings
from the_missing_20.ports.agent_model import AgentProvider

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-directory", required=True, type=Path)
    parser.add_argument("--photo", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--confirm-demo-receipt", required=True, choices=["one-synthetic-carton"])
    args = parser.parse_args()
    runtime = args.runtime_directory.resolve()
    manifest = json.loads((runtime / "receiving-manifest.json").read_text())
    assert len(manifest["arrivals"]) == 1
    arrival = manifest["arrivals"][0]
    assert len(arrival["handling_unit_ids"]) == 1
    assert not (runtime / "photo-receiving.sqlite3").exists(), "Use a fresh runtime; never reset."
    client = ERPNextDemoExecutor.from_environment(ROOT)
    assert client is not None and client._environment == "demo"
    po = client._document("Purchase Order", manifest["purchase_order"])
    assert po["company"] == "Missing 20 Automotive Demo" and po["docstatus"] == 1
    assert po["items"][0]["received_qty"] == 0
    assert po["items"][0]["description"] == manifest["case_id"] + " - SYNTHETIC TEST ORDER"
    erp = PhotoReceiptERP(client, manifest["purchase_order"])
    service = PhotoReceiving(
        runtime / "photo-receiving.sqlite3",
        StrandsPhotoReader(
            Settings(
                environment="demo",
                aws_profile="missing20-sandbox",
                agent_provider=AgentProvider.BEDROCK,
            )
        ),
        erp=erp,
        drafts_enabled=True,
        manifest=manifest,
        auto_prepare=False,
    )
    report = {
        "case_id": manifest["case_id"],
        "purchase_order": manifest["purchase_order"],
        "scope": "Real ERP receipt; public photo + typed demo scan, not shipment proof.",
        "fault": "Discard successful ERP submit response at application boundary once.",
        "steps": [],
        "submit_calls": 0,
        "payment_calls": 0,
    }

    def checkpoint(stage, state):
        report["steps"].append(
            {"stage": stage, "at": datetime.now(UTC).isoformat(), "state": state}
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")

    try:
        state = service.create(arrival_id=arrival["arrival_id"])
        checkpoint("capture", state)
        state = service.upload(state["id"], base64.b64encode(args.photo.read_bytes()).decode())
        checkpoint("real-strands-photo", state)
        assert state["analysis"]["assessment"]["countable"] is True
        assert len(state["analysis"]["assessment"]["objects"]) == 1
        binding = service.barcode(
            {
                "arrival_id": arrival["arrival_id"],
                "code": arrival["handling_unit_ids"][0],
                "format": "qr_code",
            }
        )
        state = service.current(state["id"])
        state = service.confirm_identity(
            state["id"],
            item_code=arrival["item_code"],
            expected_version=state["version"],
            confirm_match=True,
            barcode_evidence_id=binding["evidence_id"],
        )
        checkpoint("operator-confirms-demo-photo-binding", state)
        state = service.draft(state["id"])
        checkpoint("real-erp-draft", state)
        assert state["status"] == "DRAFT_VERIFIED"
        original = erp.submit

        def drop_ack(*a, **kw):
            assert not kw.get("lookup_only"), "Only this first explicitly confirmed write."
            report["submit_calls"] += 1
            result = original(*a, **kw)
            report["committed_receipt"] = result
            raise TimeoutError("Diagnostic injected: real submit completed, ACK discarded.")

        erp.submit = drop_ack
        state = service.submit(
            state["id"],
            receipt_name=state["draft"]["name"],
            expected_version=state["version"],
            confirm_received=True,
        )
        checkpoint("lost-ack-durable-intent", state)
        assert state["status"] == "SUBMIT_UNKNOWN" and report["submit_calls"] == 1
        print(
            json.dumps(
                {
                    "capture_id": state["id"],
                    "status": state["status"],
                    "receipt": state["draft"]["name"],
                    "submit_calls": 1,
                }
            )
        )
    finally:
        service.db.close()


if __name__ == "__main__":
    main()
