"""Replay one already-posted demo receipt, retaining proof of no new local effect."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from the_missing_20.adapters.photo_receiving import normalize_photo


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--capture-id", required=True)
    parser.add_argument("--photo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    base = f"http://127.0.0.1:{args.port}"

    def request(path, payload=None):
        req = Request(
            base + path,
            data=None if payload is None else json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "Origin": base},
        )
        with urlopen(req, timeout=30) as response:
            return json.load(response)

    endpoint = "/api/v1/photo-receiving"
    state = request(endpoint + "?id=" + args.capture_id)
    assert state["status"] == "RECEIPT_SUBMITTED" and state["stock_posted"] is True
    photo = args.photo.read_bytes()
    assert hashlib.sha256(normalize_photo(photo)).hexdigest() == state["digest"]
    report = {
        "capture_id": args.capture_id,
        "checked_at": datetime.now(UTC).isoformat(),
        "receipt": state["receipt"]["name"],
        "version_before": state["version"],
        "scope": "Local replay assertions; pair with fresh external readback verifier.",
        "submits": [],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(3):
        result = request(
            endpoint + "/submit",
            {
                "id": args.capture_id,
                "receipt_name": state["receipt"]["name"],
                "expected_version": state["version"],
                "confirm_received": True,
            },
        )
        assert result["receipt"] == state["receipt"] and result["version"] == state["version"]
        report["submits"].append({"attempt": attempt + 1, "same_receipt_and_version": True})
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    try:
        request(
            endpoint + "/upload",
            {
                "id": args.capture_id,
                "image": base64.b64encode(photo).decode(),
            },
        )
        raise AssertionError("Posted receiving accepted another photo")
    except HTTPError as error:
        assert error.code == 400 and "draft" in error.read().decode().lower()
        report["duplicate_photo_http_status"] = error.code
    final = request(endpoint + "?id=" + args.capture_id)
    assert final["receipt"] == state["receipt"] and final["version"] == state["version"]
    report.update(passed=True, version_after=final["version"])
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
