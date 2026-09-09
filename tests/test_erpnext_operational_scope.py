from __future__ import annotations

import json
from email.message import Message
from typing import Any
from urllib.error import HTTPError
from urllib.parse import parse_qs, unquote, urlparse
from urllib.request import Request

import pytest

from the_missing_20.adapters.erpnext_source import ERPNextCredentials, ERPNextEvidenceSource
from the_missing_20.adapters.operational_metrics import live_flow_metrics, source_freshness


def _source(records: dict[str, list[dict[str, Any]]], *, fail: int = 0) -> ERPNextEvidenceSource:
    def transport(request: Request, _timeout: float) -> bytes:
        parsed = urlparse(request.full_url)
        path = unquote(parsed.path).split("/api/resource/")[1]
        kind, _, name = path.partition("/")
        if kind == "Purchase Order":
            data: Any = {
                "name": "PO-40",
                "docstatus": 1,
                "supplier": "Demo Supplier",
                "company": "Demo",
                "currency": "USD",
                "creation": "2026-09-01",
                "items": [
                    {
                        "name": "POL-1",
                        "item_code": "ECU",
                        "uom": "Nos",
                        "qty": 40,
                        "rate": 50,
                        "amount": 2000,
                        "net_rate": 50,
                        "net_amount": 2000,
                    }
                ],
            }
        elif kind in ("Stock Entry", "Stock Ledger Entry", "GL Entry"):
            data = []
        elif kind in ("Purchase Receipt", "Purchase Invoice"):
            if fail:
                raise HTTPError(request.full_url, fail, "redacted provider error", Message(), None)
            if name:
                data = next(row for row in records.get(kind, []) if row["name"] == name)
            else:
                query = parse_qs(parsed.query)
                filters = json.loads(query["filters"][0])
                assert ["supplier", "=", "Demo Supplier"] in filters
                assert ["company", "=", "Demo"] in filters
                assert int(query["limit_page_length"][0]) == 100
                data = [{"name": row["name"]} for row in records.get(kind, [])]
        else:
            raise AssertionError(path)
        return json.dumps({"data": data}).encode()

    return ERPNextEvidenceSource(
        ERPNextCredentials("https://example.invalid", "public", "private"),
        transport=transport,
        purchase_order="PO-40",
        purchase_receipt="",
        purchase_invoice="",
        case_id="CASE-40",
        discover_purchase_documents=True,
    )


def _receipt(name: str, quantity: int, *, po: str = "PO-40", status: int = 1) -> dict[str, Any]:
    return {
        "name": name,
        "docstatus": status,
        "currency": "USD",
        "posting_date": "2026-09-08",
        "posting_time": "10:00:00",
        "modified": "2026-09-08 10:01:00",
        "items": [
            {
                "name": name + "-L1",
                "purchase_order": po,
                "po_detail": "POL-1",
                "item_code": "ECU",
                "uom": "Nos",
                "qty": quantity,
                "received_qty": quantity,
                "rejected_qty": 0,
            }
        ],
    }


def test_all_linked_receipts_are_read_once_and_other_purchase_orders_do_not_leak() -> None:
    source = _source(
        {
            "Purchase Receipt": [
                _receipt("PR-1", 10),
                _receipt("PR-2", 10),
                _receipt("OTHER-PR", 900, po="OTHER-PO"),
                _receipt("PR-DRAFT", 12, status=0),
            ]
        }
    )
    packet = source.current()
    assert packet["status"] == "CONNECTED"
    assert packet["case_id"] == "CASE-40"
    assert packet["purchase_scope"] == "ALL_LINKED_DOCUMENTS"
    assert live_flow_metrics(packet)["received"] == 20
    assert live_flow_metrics(packet)["receipt_unresolved"] == 0
    documents = packet["documents"]
    assert isinstance(documents, list)
    assert {row["name"] for row in documents} == {"PO-40", "PR-1", "PR-2", "PR-DRAFT"}
    receipt = next(row for row in documents if row["name"] == "PR-2")
    assert receipt["posting_date"] == "2026-09-08"
    assert receipt["items"][0]["po_detail"] == "POL-1"


def test_po_only_discovery_is_valid_awaiting_receipt_and_invoice() -> None:
    packet = _source({}).current()
    assert packet["status"] == "CONNECTED"
    assert source_freshness(packet)["status"] == "CURRENT"
    assert packet["document_lifecycle"] == {
        "purchase_order": "PRESENT",
        "purchase_receipt": "AWAITING_RECEIPT",
        "purchase_invoice": "AWAITING_INVOICE",
    }
    assert live_flow_metrics(packet)["expected"] == 40
    assert live_flow_metrics(packet)["received"] == 0


@pytest.mark.parametrize("code", [401, 403, 404, 500])
def test_failed_discovery_never_becomes_healthy_empty_business_state(code: int) -> None:
    packet = _source({}, fail=code).current()
    assert packet["status"] == "DEGRADED"
    assert packet["case_id"] == "CASE-40"
    assert source_freshness(packet)["status"] == "UNAVAILABLE"
    assert live_flow_metrics(packet)["received"] is None


def test_bounded_discovery_refuses_to_publish_truncated_history_as_complete() -> None:
    packet = _source(
        {"Purchase Receipt": [_receipt(f"PR-{index}", 1) for index in range(100)]}
    ).current()
    assert packet["status"] == "DEGRADED"


def test_cancelled_latest_receipt_does_not_count_as_received() -> None:
    packet = _source({"Purchase Receipt": [_receipt("PR-1", 10, status=2)]}).current()
    assert live_flow_metrics(packet)["received"] == 0
    documents = packet["documents"]
    assert isinstance(documents, list)
    assert documents[1]["status"] == "CANCELLED"


@pytest.mark.parametrize("bad_quantity", [float("nan"), float("inf"), {"unexpected": 1}])
def test_malformed_provider_numbers_degrade_instead_of_crashing_or_reaching_json(
    bad_quantity: object,
) -> None:
    receipt = _receipt("PR-1", 10)
    receipt["items"][0]["qty"] = bad_quantity
    assert _source({"Purchase Receipt": [receipt]}).current()["status"] == "DEGRADED"
