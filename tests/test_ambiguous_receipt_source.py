from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen

import pytest

from scripts.decision_workspace_server import DecisionWorkspaceServer
from the_missing_20.adapters.ambiguous_receipt_source import AmbiguousReceiptEvidenceSource

ROOT = Path(__file__).resolve().parents[1]


def test_source_exposes_independent_records_without_mislabeling_fixture_as_live() -> None:
    projection = AmbiguousReceiptEvidenceSource().current()

    assert projection["status"] == "CONNECTED"
    assert projection["provenance"] == "synthetic-demo-fixture"
    assert projection["read_only"] is True
    case = projection["case"]
    assert isinstance(case, dict)
    assert case["disposition"] == "RECOVERY_READY"
    assert case["allowed_actions"] == (
        "POST_IDEMPOTENT_RECEIPT",
        "TRANSFER_APPROVED_QUALITY_STOCK",
        "REVALIDATE_LINKED_INVOICE",
    )
    assert case["quantities"] == {
        "physically_arrived": 100,
        "available": 80,
        "quality_hold": 8,
        "receipt_unresolved": 12,
    }
    activity = projection["activity"]
    assert isinstance(activity, list)
    assert [entry["source_id"] for entry in activity] == [
        "warehouse-asn",
        "erp-business-key",
        "supplier-quality",
        "integration-attempt",
    ]
    assert all(entry["correlation_id"] == "M20-PO-4817" for entry in activity)
    assert all(datetime.fromisoformat(str(entry["observed_at"])) for entry in activity)


def test_server_exposes_the_case_fixture_with_synthetic_provenance(tmp_path: Path) -> None:
    try:
        server = DecisionWorkspaceServer(
            ("127.0.0.1", 0), ROOT, runtime_directory=tmp_path / "runtime"
        )
    except PermissionError:
        pytest.skip("the managed test sandbox disallows loopback sockets")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urlopen(
            f"http://127.0.0.1:{server.server_port}/api/v1/ambiguous-receipt-case", timeout=5
        ) as response:
            payload = json.loads(response.read())
        assert payload["provenance"] == "synthetic-demo-fixture"
        assert payload["case"]["disposition"] == "RECOVERY_READY"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
