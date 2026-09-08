from __future__ import annotations

import json
from datetime import datetime
from urllib.request import Request

from the_missing_20.adapters.erpnext_source import ERPNextCredentials, ERPNextEvidenceSource


def _transport(request: Request, _timeout: float) -> bytes:
    url = request.full_url
    assert request.get_header("Authorization") == "token public-key:private-secret"
    if "Stock%20Ledger%20Entry?" in url:
        payload = {
            "data": [
                {
                    "name": "SLE-1",
                    "voucher_type": "Purchase Receipt",
                    "voucher_no": "PR-1",
                    "item_code": "M20-ECU",
                    "warehouse": "Stores",
                    "actual_qty": 12,
                    "qty_after_transaction": 12,
                    "stock_value_difference": 14400,
                    "posting_date": "2026-09-01",
                    "posting_time": "10:17:00",
                }
            ]
        }
    elif "GL%20Entry?" in url:
        payload = {
            "data": [
                {
                    "name": "GLE-1",
                    "voucher_type": "Purchase Receipt",
                    "voucher_no": "PR-1",
                    "account": "Stock In Hand",
                    "debit": 14400,
                    "credit": 0,
                    "posting_date": "2026-09-01",
                },
                {
                    "name": "GLE-2",
                    "voucher_type": "Purchase Receipt",
                    "voucher_no": "PR-1",
                    "account": "Stock Received But Not Billed",
                    "debit": 0,
                    "credit": 14400,
                    "posting_date": "2026-09-01",
                },
            ]
        }
    elif "Stock%20Entry?" in url:
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
        "quality_hold_remaining": 8.0,
        "quality_hold_warehouse": "Quality Hold",
    }
    assert documents[2]["status"] == "PAYMENT_HOLD"
    assert documents[2]["linked_receipts"] == ["PR-1"]
    ledger = projection["ledger_evidence"]
    assert ledger["status"] == "CONNECTED"
    assert len(ledger["stock_entries"]) == 1
    assert len(ledger["general_ledger_entries"]) == 2
    assert ledger["totals"]["debit"] == 14400
    assert ledger["totals"]["credit"] == 14400
    assert ledger["assertions"] == {
        "stock_ledger_present": True,
        "general_ledger_present": True,
        "debits_equal_credits": True,
    }
    activity = projection["activity"]
    assert isinstance(activity, list)
    assert [item["status"] for item in activity] == ["VERIFIED", "HELD", "HELD"]
    assert {item["source_id"] for item in activity} == {"erpnext-missing20"}
    assert {item["provider"] for item in activity} == {"ERPNext / Frappe Cloud"}
    assert all(datetime.fromisoformat(str(item["occurred_at"])) for item in activity)


def test_erpnext_sequence_advances_only_when_external_business_state_changes() -> None:
    state = {"invoice_on_hold": 1}

    def changing_transport(request: Request, timeout: float) -> bytes:
        if "Purchase%20Invoice" not in request.full_url:
            return _transport(request, timeout)
        return json.dumps(
            {
                "data": {
                    "name": "PI-1",
                    "bill_no": "VENDOR-1",
                    "on_hold": state["invoice_on_hold"],
                    "hold_comment": "Awaiting three-way match",
                    "items": [{"purchase_receipt": "PR-1"}],
                }
            }
        ).encode()

    source = ERPNextEvidenceSource(
        ERPNextCredentials("https://example.invalid", "public-key", "private-secret"),
        transport=changing_transport,
        purchase_order="PO-1",
        purchase_receipt="PR-1",
        purchase_invoice="PI-1",
    )

    first = source.current()
    unchanged = source.current()
    state["invoice_on_hold"] = 0
    changed = source.current()

    assert first["sequence"] == 1
    assert unchanged["sequence"] == 1
    assert unchanged["changed_at"] == first["changed_at"]
    assert changed["sequence"] == 2
    assert changed["changed_at"] != ""


def test_erpnext_evidence_is_explicit_when_not_configured() -> None:
    projection = ERPNextEvidenceSource(None, transport=_transport).current()

    assert projection["status"] == "NOT_CONFIGURED"
    assert projection["documents"] == []
    assert projection["activity"] == []


def test_value_chain_finds_delivery_by_authoritative_sales_order_link_without_remarks() -> None:
    """ERPNext's Sales Order mapper may omit Delivery Note remarks.

    The child-row ``against_sales_order`` relationship is the authoritative
    link and must be sufficient for rediscovering the submitted delivery.
    """

    def value_transport(request: Request, _timeout: float) -> bytes:
        url = request.full_url
        if "Sales%20Order?" in url:
            payload = {"data": [{"name": "SO-M20-20"}]}
        elif "Sales%20Order/SO-M20-20" in url:
            payload = {
                "data": {
                    "name": "SO-M20-20",
                    "customer": "M20 Fleet",
                    "po_no": "M20-CUSTOMER-PO",
                }
            }
        elif "Delivery%20Note?" in url:
            payload = {"data": [{"name": "DN-M20-20"}]}
        elif "Delivery%20Note/DN-M20-20" in url:
            payload = {
                "data": {
                    "name": "DN-M20-20",
                    "customer": "M20 Fleet",
                    "docstatus": 1,
                    "remarks": None,
                    "items": [{"against_sales_order": "SO-M20-20", "qty": 20}],
                }
            }
        elif "Sales%20Invoice?" in url:
            payload = {"data": [{"name": "SI-M20-20"}]}
        elif "Sales%20Invoice/SI-M20-20" in url:
            payload = {
                "data": {
                    "name": "SI-M20-20",
                    "customer": "M20 Fleet",
                    "docstatus": 1,
                    "remarks": "M20 DEMO customer billing M20-CASE-20",
                    "items": [{"sales_order": "SO-M20-20", "qty": 20}],
                }
            }
        else:  # pragma: no cover - proves the finder remains narrowly scoped
            raise AssertionError(url)
        return json.dumps(payload).encode()

    source = ERPNextEvidenceSource(
        ERPNextCredentials("https://example.invalid", "public-key", "private-secret"),
        transport=value_transport,
        case_id="M20-CASE-20",
        customer_purchase_order="M20-CUSTOMER-PO",
    )

    order, delivery, invoice = source._find_value_chain()

    assert order["name"] == "SO-M20-20"
    assert delivery is not None
    assert delivery["name"] == "DN-M20-20"
    assert invoice is not None
    assert invoice["name"] == "SI-M20-20"


def test_erpnext_evidence_proves_a_completed_m20_release_from_the_stock_transfer() -> None:
    def recovered_transport(request: Request, _timeout: float) -> bytes:
        url = request.full_url
        if "Stock%20Ledger%20Entry?" in url:
            return json.dumps({"data": [{"name": "SLE-20", "actual_qty": 8}]}).encode()
        if "GL%20Entry?" in url:
            return json.dumps(
                {
                    "data": [
                        {"name": "GLE-20A", "debit": 24000, "credit": 0},
                        {"name": "GLE-20B", "debit": 0, "credit": 24000},
                    ]
                }
            ).encode()
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
    assert documents[1]["status"] == "RELEASED_AFTER_QUALITY_HOLD"
    assert documents[1]["quality_hold_remaining"] == 0.0
    assert activity[1]["status"] == "VERIFIED"
    assert "0 remain" in activity[1]["detail"]
    assert activity[-1]["status"] == "VERIFIED"
