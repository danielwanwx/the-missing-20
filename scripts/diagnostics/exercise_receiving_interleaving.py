"""Explicit staged demo actions through the same receiving HTTP API as the UI.

Public original photographs are test stand-ins, not proof of delivered goods.
No direct database edits, fabricated ERP responses or bypasses of receipt confirmation.
"""

from __future__ import annotations

import argparse
import base64
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import Request, urlopen


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--action", required=True,
                        choices=("prepare", "post-control", "provoke", "refresh", "post-reviewed"))
    parser.add_argument("--photo-one", type=Path)
    parser.add_argument("--photo-two", type=Path)
    parser.add_argument("--confirm", required=True, choices=("synthetic-demo-receiving",))
    args = parser.parse_args()
    base = f"http://127.0.0.1:{args.port}"
    endpoint = "/api/v1/photo-receiving"
    report = json.loads(args.output.read_text()) if args.output.exists() else {
        "case_id": args.case_id, "scope": "staged concurrent receipt changes the same PO",
        "source": "Original public photographs; real Strands/Bedrock and demo SaaS effects",
        "captures": {}, "steps": [],
    }
    assert report["case_id"] == args.case_id

    def save():
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")

    def request(path, payload=None):
        req = Request(base + path, data=None if payload is None else json.dumps(payload).encode(),
                      headers={"Content-Type": "application/json", "Origin": base})
        with urlopen(req, timeout=150) as response:
            return json.load(response)

    def record(name, state):
        report["steps"].append({"step": name, "at": datetime.now(UTC).isoformat(), "state": state})
        save()
        print(json.dumps({"step": name, "id": state.get("id"),
                          "status": state.get("status"), "version": state.get("version"),
                          "count": state.get("count"), "receipt": state.get("receipt")}),
              flush=True)

    def identify(arrival, state):
        barcode = request(endpoint + "/barcode", {
            "arrival_id": arrival, "code": "M20-CARTON-BOX", "format": "code_128",
        })
        record("barcode-" + arrival, barcode)
        state = request(endpoint + "/confirm-identity", {
            "id": state["id"], "item_code": "M20-DEMO-CARTON", "expected_version": state["version"],
            "confirm_match": True, "barcode_evidence_id": barcode["evidence_id"],
        })
        record("confirm-" + arrival, state)
        assert state["status"] == "RECEIPT_PREPARED"
        return state

    def current(arrival):
        return request(endpoint + "?id=" + report["captures"][arrival])

    def post(arrival):
        state = current(arrival)
        assert state["status"] == "RECEIPT_PREPARED" and not state.get("draft_attempted")
        state = request(endpoint + "/draft", {"id": state["id"]})
        record("draft-" + arrival, state)
        assert state.get("draft") and not state.get("stock_posted")
        state = request(endpoint + "/submit", {
            "id": state["id"], "receipt_name": state["draft"]["name"],
            "expected_version": state["version"], "confirm_received": True,
        })
        record("submit-" + arrival, state)
        assert state["status"] == "RECEIPT_SUBMITTED" and state["stock_posted"] is True

    arrivals = request(endpoint + "/arrivals")
    assert arrivals["case_id"] == args.case_id
    if args.action == "prepare":
        assert not report["captures"], "Do not blindly rerun an uncertain preparation"
        assert args.photo_one and args.photo_two
        assert args.photo_one.read_bytes() != args.photo_two.read_bytes()
        for arrival, photo in (("ARRIVAL-01", args.photo_one), ("ARRIVAL-02", args.photo_two)):
            assert next(row for row in arrivals["arrivals"] if row["arrival_id"] == arrival)[
                "capture_id"] is None
            state = request(endpoint, {"arrival_id": arrival})
            report["captures"][arrival] = state["id"]
            record("create-" + arrival, state)
            state = request(endpoint + "/upload", {
                "id": state["id"], "image": base64.b64encode(photo.read_bytes()).decode(),
            })
            record("photo-" + arrival, state)
            assert state["status"] == "COUNT_CANDIDATE" and state["count"] == 1
            identify(arrival, state)
    elif args.action == "post-control":
        post("ARRIVAL-02")
    elif args.action == "provoke":
        assert current("ARRIVAL-02")["stock_posted"] is True
        state = current("ARRIVAL-01")
        assert state["status"] == "RECEIPT_PREPARED" and not state.get("draft_attempted")
        state = request(endpoint + "/draft", {"id": state["id"]})
        record("stale-plan-blocked", state)
        assert state["status"] == "NEEDS_REVIEW"
        assert not any(state.get(key) for key in ("draft_attempted", "draft", "receipt"))
    elif args.action == "refresh":
        state = current("ARRIVAL-01")
        assert state["status"] == "NEEDS_REVIEW" and not state.get("draft_attempted")
        identify("ARRIVAL-01", state)
    elif args.action == "post-reviewed":
        post("ARRIVAL-01")


if __name__ == "__main__":
    main()
