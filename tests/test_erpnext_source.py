from __future__ import annotations

import json
from datetime import datetime
from urllib.request import Request

from the_missing_20.adapters.erpnext_source import ERPNextCredentials, ERPNextEvidenceSource


def _transport(request: Request, _timeout: float) -> bytes:
    url = request.full_url
    assert request.get_header("Authorization") == "token public-key:private-secret"
    if "Stock%20Entry?" in url:
        payload = {"data": []}
    elif "Purchase%20Order" in url:
        payload = {
            "data": {
                "name": "PO-1",
                "docstatus": 1,
                "supplier": "Controller Systems",
                "items": [{"qty": 20}],
            }
        }
    elif "Purchase%20Receipt" in url:
        payload = {
            "data": {
                "name": "PR-1",
                "supplier_delivery_note": "DOCK-1",
                "items": [
                    {
                        "received_qty": 20,
                        "qty": 12,
                        "rejected_qty": 8,
                        "rejected_warehouse": "Quality Hold",
                    }
                ],
            }
        }
    elif "Purchase%20Invoice" in url:
        payload = {
            "data": {
                "name": "PI-1",
                "bill_no": "VENDOR-1",
                "on_hold": 1,
                "hold_comment": "Awaiting three-way match",
                "items": [{"purchase_receipt": "PR-1"}],
            }
        }
    else:  # pragma: no cover - proves the adapter did not expand its read scope
        raise AssertionError(url)
    return json.dumps(payload).encode()


def test_erpnext_evidence_projection_is_scoped_and_read_only() -> None:
    source = ERPNextEvidenceSource(
        ERPNextCredentials("https://example.invalid", "public-key", "private-secret"),
        transport=_transport,
        purchase_order="PO-1",
        purchase_receipt="PR-1",
        purchase_invoice="PI-1",
    )

    projection = source.current()

    assert projection["status"] == "CONNECTED"
    assert projection["read_only"] is True
    assert projection["sequence"] == 1
    documents = projection["documents"]
    assert isinstance(documents, list)
    assert documents[1] == {
        "kind": "purchase_receipt",
        "name": "PR-1",
        "status": "PARTIAL_QUALITY_HOLD",
        "delivery_note": "DOCK-1",
        "received": 20.0,
        "accepted": 12.0,
        "rejected": 8.0,
        "quality_hold_warehouse": "Quality Hold",
    }
    assert documents[2]["status"] == "PAYMENT_HOLD"
    assert documents[2]["linked_receipts"] == ["PR-1"]
    activity = projection["activity"]
    assert isinstance(activity, list)
    assert [item["status"] for item in activity] == ["VERIFIED", "HELD", "HELD"]
    assert {item["source_id"] for item in activity} == {"erpnext-missing20"}
    assert {item["provider"] for item in activity} == {"ERPNext / Frappe Cloud"}
    assert all(datetime.fromisoformat(str(item["occurred_at"])) for item in activity)


def test_erpnext_evidence_is_explicit_when_not_configured() -> None:
    projection = ERPNextEvidenceSource(None, transport=_transport).current()

    assert projection["status"] == "NOT_CONFIGURED"
    assert projection["documents"] == []
    assert projection["activity"] == []


def test_erpnext_evidence_proves_a_completed_m20_release_from_the_stock_transfer() -> None:
    def recovered_transport(request: Request, _timeout: float) -> bytes:
        url = request.full_url
        if "Stock%20Entry?" in url:
            return json.dumps({"data": [{"name": "MAT-STE-20", "docstatus": 1}]}).encode()
        if "Stock%20Entry/MAT-STE-20" in url:
            return json.dumps(
                {
                    "data": {
                        "name": "MAT-STE-20",
                        "docstatus": 1,
                        "remarks": "M20 DEMO release M20-CASE-20",
                        "items": [
                            {"qty": 8, "s_warehouse": "Quality Hold", "t_warehouse": "Stores"}
                        ],
                    }
                }
            ).encode()
        if "Purchase%20Order" in url:
            return json.dumps(
                {
                    "data": {
                        "name": "PO-20",
                        "docstatus": 1,
                        "supplier": "Controller Systems",
                        "items": [{"qty": 20}],
                    }
                }
            ).encode()
        if "Purchase%20Receipt" in url:
            return json.dumps(
                {
                    "data": {
                        "name": "PR-20",
                        "supplier_delivery_note": "M20-DOCK-20",
                        "items": [{"received_qty": 20, "qty": 12, "rejected_qty": 8}],
                    }
                }
            ).encode()
        if "Purchase%20Invoice" in url:
            return json.dumps(
                {
                    "data": {
                        "name": "PI-20",
                        "docstatus": 1,
                        "on_hold": 0,
                        "items": [{"purchase_receipt": "PR-20"}],
                    }
                }
            ).encode()
        raise AssertionError(url)

    projection = ERPNextEvidenceSource(
        ERPNextCredentials("https://example.invalid", "public-key", "private-secret"),
        transport=recovered_transport,
        purchase_order="PO-20",
        purchase_receipt="PR-20",
        purchase_invoice="PI-20",
        case_id="M20-CASE-20",
    ).current()

    documents = projection["documents"]
    assert isinstance(documents, list)
    assert documents[-1] == {
        "kind": "quality_release_transfer",
        "name": "MAT-STE-20",
        "status": "SUBMITTED",
        "quantity": 8.0,
        "source_warehouse": "Quality Hold",
        "target_warehouse": "Stores",
    }
    activity = projection["activity"]
    assert isinstance(activity, list)
    assert activity[-1]["status"] == "VERIFIED"
