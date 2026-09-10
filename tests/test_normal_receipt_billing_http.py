from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from urllib.parse import parse_qs, unquote, urlparse

import pytest

from scripts.decision_workspace_server import (
    APIRequestError,
    DecisionWorkspaceHandler,
    NormalBillingConsole,
)
from the_missing_20.adapters.normal_receipt_billing_coordinator import (
    NormalReceiptBillingCoordinator,
)
from the_missing_20.adapters.normal_receipt_billing_journal import BillingIntentJournal
from the_missing_20.adapters.normal_receipt_billing_native_request import (
    validate_native_draft_acknowledgement,
    validate_native_submitted_readback,
)
from the_missing_20.adapters.normal_receipt_billing_preview import SyntheticBillingBasis

CASE_ID = "M20-GOODS-20260909-40-R4"
MAPPER_PATH = (
    "/api/method/erpnext.stock.doctype.purchase_receipt.purchase_receipt.make_purchase_invoice"
)
INSERT_PATH = "/api/resource/Purchase%20Invoice"
SUBMIT_PATH = "/api/method/frappe.client.submit"


def _basis() -> SyntheticBillingBasis:
    return SyntheticBillingBasis(
        case_id=CASE_ID,
        company="Missing 20 Automotive Demo",
        supplier="M20 Controller Systems Ltd.",
        bill_reference="SUP-BILL-R4-0001",
        bill_date="2026-09-09",
        purchase_order="PUR-ORD-2026-00016",
        purchase_order_item="458j82kp8e",
        purchase_receipt="MAT-PRE-2026-00007",
        purchase_receipt_item="068bbdr0mb",
        item_code="M20-DEMO-CARTON",
        source_revision="r4-native-preflight-2026-09-09",
        posting_date="2026-09-09",
        credit_to="Creditors - M20",
        expense_account="Stock Received But Not Billed - M20",
    )


def _purchase_order() -> dict[str, Any]:
    basis = _basis()
    return {
        "doctype": "Purchase Order",
        "name": basis.purchase_order,
        "docstatus": 1,
        "modified": "2026-09-09 13:33:06.587269",
        "company": basis.company,
        "supplier": basis.supplier,
        "currency": "USD",
        "discount_amount": 0,
        "rounding_adjustment": 0,
        "taxes": [],
        "items": [
            {
                "doctype": "Purchase Order Item",
                "name": basis.purchase_order_item,
                "item_code": basis.item_code,
                "qty": 40,
                "uom": "Box",
                "stock_uom": "Box",
                "conversion_factor": 1,
                "rate": 50,
                "net_rate": 50,
                "amount": 2000,
                "net_amount": 2000,
                "stock_qty": 40,
                "received_qty": 1,
                "returned_qty": 0,
            }
        ],
    }


def _purchase_receipt() -> dict[str, Any]:
    basis = _basis()
    return {
        "doctype": "Purchase Receipt",
        "name": basis.purchase_receipt,
        "docstatus": 1,
        "modified": "2026-09-09 13:33:06.525238",
        "company": basis.company,
        "supplier": basis.supplier,
        "currency": "USD",
        "discount_amount": 0,
        "rounding_adjustment": 0,
        "is_return": 0,
        "taxes": [],
        "items": [
            {
                "doctype": "Purchase Receipt Item",
                "name": basis.purchase_receipt_item,
                "item_code": basis.item_code,
                "qty": 1,
                "received_qty": 1,
                "rejected_qty": 0,
                "uom": "Box",
                "stock_uom": "Box",
                "conversion_factor": 1,
                "received_stock_qty": 1,
                "stock_qty": 1,
                "returned_qty": 0,
                "rate": 50,
                "net_rate": 50,
                "amount": 50,
                "net_amount": 50,
                "purchase_order": basis.purchase_order,
                "purchase_order_item": basis.purchase_order_item,
            }
        ],
    }


def _mapped_invoice() -> dict[str, Any]:
    basis = _basis()
    return {
        "doctype": "Purchase Invoice",
        "name": None,
        "docstatus": 0,
        "company": basis.company,
        "supplier": basis.supplier,
        "credit_to": basis.credit_to,
        "posting_date": basis.posting_date,
        "currency": "USD",
        "update_stock": 0,
        "is_return": 0,
        "is_paid": 0,
        "paid_amount": 0,
        "write_off_amount": 0,
        "discount_amount": 0,
        "rounding_adjustment": 0,
        "taxes": [],
        "grand_total": 50,
        "items": [
            {
                "doctype": "Purchase Invoice Item",
                "item_code": basis.item_code,
                "qty": 1,
                "received_qty": 1,
                "rejected_qty": 0,
                "uom": "Box",
                "stock_uom": "Box",
                "conversion_factor": 1,
                "rate": 50,
                "net_rate": 50,
                "amount": 50,
                "net_amount": 50,
                "stock_qty": 1,
                "expense_account": basis.expense_account,
                "purchase_order": basis.purchase_order,
                "po_detail": basis.purchase_order_item,
                "purchase_receipt": basis.purchase_receipt,
                "pr_detail": basis.purchase_receipt_item,
            }
        ],
    }


class _FakeERP:
    def __init__(self) -> None:
        self.purchase_order = _purchase_order()
        self.purchase_receipt = _purchase_receipt()
        self.mapped_invoice = _mapped_invoice()
        self.invoices: dict[str, dict[str, Any]] = {}
        self.insert_calls = 0
        self.submit_calls = 0

    def __call__(self, path: str, *, method: str = "GET", payload: object | None = None) -> object:
        parsed = urlparse(path)
        decoded = unquote(parsed.path)
        basis = _basis()
        if decoded == f"/api/resource/Purchase Order/{basis.purchase_order}":
            return {"data": deepcopy(self.purchase_order)}
        if decoded == f"/api/resource/Purchase Receipt/{basis.purchase_receipt}":
            return {"data": deepcopy(self.purchase_receipt)}
        if path == MAPPER_PATH:
            return {"message": deepcopy(self.mapped_invoice)}
        if decoded == "/api/resource/Purchase Invoice":
            if method == "POST":
                return self._insert(payload)
            return self._discover(parsed.query, self.invoices)
        if decoded == "/api/resource/Purchase Receipt":
            return {"data": []}
        if decoded.startswith("/api/resource/Purchase Invoice/"):
            name = decoded.removeprefix("/api/resource/Purchase Invoice/")
            return {"data": deepcopy(self.invoices.get(name))}
        if path == SUBMIT_PATH:
            return self._submit(payload)
        raise AssertionError(f"unexpected request: {method} {path}")

    @staticmethod
    def _discover(query: str, documents: dict[str, dict[str, Any]]) -> dict[str, object]:
        offset = int(parse_qs(query).get("limit_start", ["0"])[0])
        names = sorted(documents)
        return {"data": [{"name": name} for name in names[offset : offset + 50]]}

    def _insert(self, payload: object | None) -> dict[str, object]:
        assert isinstance(payload, dict)
        self.insert_calls += 1
        name = f"ACC-PINV-2026-{self.insert_calls:05d}"
        document = deepcopy(payload)
        document.update(
            name=name,
            docstatus=0,
            owner="coordinator@example.test",
            creation="2026-09-09 22:00:00.000000",
            modified="2026-09-09 22:00:00.000000",
        )
        self.invoices[name] = document
        return {"data": deepcopy(document)}

    def _submit(self, payload: object | None) -> dict[str, object]:
        assert isinstance(payload, dict)
        document = payload.get("doc")
        assert isinstance(document, dict)
        name = document.get("name")
        assert isinstance(name, str)
        self.submit_calls += 1
        self.invoices[name]["docstatus"] = 1
        self.invoices[name]["modified"] = "2026-09-09 22:05:00.000000"
        return {"message": deepcopy(self.invoices[name])}


def _console(tmp_path: Path, fake: _FakeERP) -> NormalBillingConsole:
    basis = _basis()
    journal = BillingIntentJournal(tmp_path / "normal-billing.sqlite3")

    def resolve(case_id: str) -> SyntheticBillingBasis:
        if case_id != basis.case_id:
            raise ValueError("unknown case")
        return basis

    coordinator = NormalReceiptBillingCoordinator(journal, resolve, fake)
    return NormalBillingConsole(
        journal,
        coordinator,
        basis,
        operator_id="m20-demo-manager",
        invoice_base_url="https://erp.example.test",
    )


def _handler(console: NormalBillingConsole) -> tuple[DecisionWorkspaceHandler, list[object]]:
    handler = cast(Any, object.__new__(DecisionWorkspaceHandler))
    handler.server = SimpleNamespace(normal_billing=console)
    sent: list[object] = []
    handler._send_json = lambda _status, value: sent.append(value)
    return cast(DecisionWorkspaceHandler, handler), sent


def _latest_normal(sent: list[object]) -> dict[str, object]:
    response = sent[-1]
    assert isinstance(response, dict)
    projection = response["normal_billing"]
    assert isinstance(projection, dict)
    return projection


def test_normal_billing_console_prepares_approves_executes_and_survives_restart(
    tmp_path: Path,
) -> None:
    fake = _FakeERP()
    console = _console(tmp_path, fake)
    handler, sent = _handler(console)
    route = "/api/v1/agent-platform/normal-billing"
    handler._v1_get(route, {})
    initial = _latest_normal(sent)
    assert initial["phase"] == "NOT_PREPARED"
    assert initial["available_actions"] == ["prepare"]
    assert initial["financial_verification"] == "NOT_VERIFIED"

    handler._v1_post(f"{route}/prepare", {"case_id": CASE_ID})
    prepared = _latest_normal(sent)
    assert prepared["phase"] == "PREPARED"
    assert prepared["available_actions"] == ["approve"]
    intent_id = prepared["intent_id"]
    version = prepared["version"]
    assert isinstance(intent_id, str) and isinstance(version, int)

    handler._v1_post(
        f"{route}/approve", {"case_id": CASE_ID, "intent_id": intent_id, "version": version}
    )
    approved = _latest_normal(sent)
    assert approved["phase"] == "APPROVED"
    assert "token" not in json.dumps(approved).lower()

    handler._v1_post(
        f"{route}/execute", {"case_id": CASE_ID, "intent_id": intent_id, "version": version}
    )
    executed = _latest_normal(sent)
    assert executed["phase"] == "SUBMITTED_READBACK_ADMITTED"
    assert executed["invoice_name"] == "ACC-PINV-2026-00001"
    invoice_url = executed["invoice_url"]
    assert isinstance(invoice_url, str)
    assert invoice_url == "https://erp.example.test/app/purchase-invoice/ACC-PINV-2026-00001"
    assert executed["financial_verification"] == "NOT_VERIFIED"
    assert fake.insert_calls == fake.submit_calls == 1

    handler._v1_post(
        f"{route}/execute", {"case_id": CASE_ID, "intent_id": intent_id, "version": version}
    )
    repeated = _latest_normal(sent)
    assert repeated["phase"] == "SUBMITTED_READBACK_ADMITTED"
    assert fake.insert_calls == fake.submit_calls == 1

    restarted_console = _console(tmp_path, fake)
    restored = restarted_console.current()
    assert restored["intent_id"] == intent_id
    assert restored["phase"] == "SUBMITTED_READBACK_ADMITTED"
    assert restored["invoice_name"] == "ACC-PINV-2026-00001"


def test_normal_billing_console_renews_only_the_expired_acknowledged_draft_submit(
    tmp_path: Path,
) -> None:
    fake = _FakeERP()
    console = _console(tmp_path, fake)
    prepared = console.prepare(CASE_ID)
    intent_id = prepared["intent_id"]
    version = prepared["version"]
    assert isinstance(intent_id, str) and isinstance(version, int)

    journal = console._journal
    request = journal.bound_insert_request(intent_id)
    assert request is not None
    prior_now = datetime(2026, 9, 9, 22, 0, tzinfo=UTC)
    prior_approval = journal.approve(
        intent_id,
        case_id=CASE_ID,
        manager_id="m20-demo-manager",
        expires_at=prior_now + timedelta(seconds=1),
        now=prior_now,
    )
    assert prior_approval.token is not None
    assert journal.claim_insert(
        intent_id,
        case_id=CASE_ID,
        manager_id="m20-demo-manager",
        approval_token=prior_approval.token,
        worker_id="prior-insert",
        now=prior_now,
    ).granted
    insert_body = request.record()["body"]
    assert isinstance(insert_body, dict)
    insert_response = fake._insert(insert_body)
    document = insert_response["data"]
    assert isinstance(document, dict)
    acknowledgement = validate_native_draft_acknowledgement(
        _basis(),
        purchase_order=fake.purchase_order,
        purchase_receipt=fake.purchase_receipt,
        insert_request=request,
        document=document,
    )
    assert journal.admit_insert_acknowledgement(intent_id, acknowledgement).admitted

    expired = console.current()
    assert expired["phase"] == "DRAFT_READBACK_ADMITTED"
    assert expired["status"] == "HOLD"
    assert expired["available_actions"] == ["approve"]
    assert "no new invoice" in cast(str, expired["message"]).lower()

    handler, sent = _handler(console)
    route = "/api/v1/agent-platform/normal-billing"
    handler._v1_post(
        f"{route}/approve", {"case_id": CASE_ID, "intent_id": intent_id, "version": version}
    )
    renewed = _latest_normal(sent)
    assert renewed["phase"] == "DRAFT_READBACK_ADMITTED"
    assert renewed["available_actions"] == ["execute"]

    handler._v1_post(
        f"{route}/execute", {"case_id": CASE_ID, "intent_id": intent_id, "version": version}
    )
    submitted = _latest_normal(sent)
    assert submitted["phase"] == "SUBMITTED_READBACK_ADMITTED"
    assert fake.insert_calls == 1
    assert fake.submit_calls == 1


def test_normal_billing_console_keeps_expired_submitted_readback_visible_and_readonly(
    tmp_path: Path,
) -> None:
    fake = _FakeERP()
    console = _console(tmp_path, fake)
    prepared = console.prepare(CASE_ID)
    intent_id = prepared["intent_id"]
    version = prepared["version"]
    assert isinstance(intent_id, str) and isinstance(version, int)

    journal = console._journal
    request = journal.bound_insert_request(intent_id)
    assert request is not None
    prior_now = datetime(2026, 9, 9, 22, 0, tzinfo=UTC)
    approval = journal.approve(
        intent_id,
        case_id=CASE_ID,
        manager_id="m20-demo-manager",
        expires_at=prior_now + timedelta(seconds=1),
        now=prior_now,
    )
    assert approval.token is not None
    assert journal.claim_insert(
        intent_id,
        case_id=CASE_ID,
        manager_id="m20-demo-manager",
        approval_token=approval.token,
        worker_id="prior-insert",
        now=prior_now,
    ).granted
    insert_body = request.record()["body"]
    assert isinstance(insert_body, dict)
    inserted = fake._insert(insert_body)["data"]
    assert isinstance(inserted, dict)
    acknowledgement = validate_native_draft_acknowledgement(
        _basis(),
        purchase_order=fake.purchase_order,
        purchase_receipt=fake.purchase_receipt,
        insert_request=request,
        document=inserted,
    )
    assert journal.admit_insert_acknowledgement(intent_id, acknowledgement).admitted
    assert journal.claim_submit(
        intent_id,
        case_id=CASE_ID,
        manager_id="m20-demo-manager",
        worker_id="prior-submit",
        now=prior_now + timedelta(microseconds=500),
    ).granted
    submitted = fake._submit({"doc": {"name": acknowledgement.draft_name}})["message"]
    assert isinstance(submitted, dict)
    proof = validate_native_submitted_readback(
        _basis(),
        purchase_order=fake.purchase_order,
        purchase_receipt=fake.purchase_receipt,
        draft=acknowledgement,
        document=submitted,
    )
    assert journal.admit_submitted_readback(intent_id, proof).admitted

    handler, sent = _handler(console)
    route = "/api/v1/agent-platform/normal-billing"
    handler._v1_get(route, {})
    expired_terminal = _latest_normal(sent)
    assert expired_terminal["phase"] == "SUBMITTED_READBACK_ADMITTED"
    assert expired_terminal["status"] == "SUBMITTED_READBACK_ADMITTED"
    assert expired_terminal["available_actions"] == ["reconcile"]

    handler._v1_post(
        f"{route}/reconcile", {"case_id": CASE_ID, "intent_id": intent_id, "version": version}
    )
    reconciled = _latest_normal(sent)
    assert reconciled["phase"] == "SUBMITTED_READBACK_ADMITTED"
    assert fake.insert_calls == fake.submit_calls == 1

    changed_readback = deepcopy(submitted)
    changed_readback["modified"] = "2026-09-10 08:01:12.692288"
    conflicting_proof = validate_native_submitted_readback(
        _basis(),
        purchase_order=fake.purchase_order,
        purchase_receipt=fake.purchase_receipt,
        draft=acknowledgement,
        document=changed_readback,
    )
    assert not journal.admit_submitted_readback(intent_id, conflicting_proof).admitted

    handler._v1_get(route, {})
    conflict = _latest_normal(sent)
    assert conflict["phase"] == "SUBMITTED_READBACK_ADMITTED"
    assert conflict["status"] == "HOLD"
    assert conflict["available_actions"] == []
    assert conflict["invoice_name"] == "ACC-PINV-2026-00001"
    assert conflict["message"] == (
        "The invoice was already submitted. A subsequent read-only reconciliation found "
        "a mismatch that needs review. Use the invoice link to inspect it."
    )


def test_http_normal_billing_dispatch_rejects_foreign_case_and_unexpected_body(
    tmp_path: Path,
) -> None:
    handler, sent = _handler(_console(tmp_path, _FakeERP()))
    with pytest.raises(ValueError, match="not configured"):
        handler._v1_post("/api/v1/agent-platform/normal-billing/prepare", {"case_id": "M20-NOT-R4"})
    with pytest.raises(APIRequestError) as extra:
        handler._v1_post(
            "/api/v1/agent-platform/normal-billing/prepare",
            {"case_id": CASE_ID, "manager_id": "caller"},
        )
    assert extra.value.status == 400

    handler._v1_post("/api/v1/agent-platform/normal-billing/prepare", {"case_id": CASE_ID})
    assert len(sent) == 1
    response = sent[0]
    assert isinstance(response, dict)
    assert set(response) == {"normal_billing"}
