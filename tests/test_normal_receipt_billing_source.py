from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import pytest

from the_missing_20.adapters.normal_receipt_billing_preview import SyntheticBillingBasis
from the_missing_20.adapters.normal_receipt_billing_source import (
    MAX_RELATED_DOCUMENTS,
    MAX_RESPONSE_BYTES,
    RELATED_PAGE_SIZE,
    NormalReceiptBillingSourceRead,
    NormalReceiptBillingSourceReader,
)

MAPPER_PATH = (
    "/api/method/erpnext.stock.doctype.purchase_receipt.purchase_receipt.make_purchase_invoice"
)


def _basis() -> SyntheticBillingBasis:
    return SyntheticBillingBasis(
        case_id="M20-R4-BILL-1",
        company="Missing 20 Automotive Demo",
        supplier="M20 Controller Systems Ltd.",
        bill_reference="SUP-BILL-R4-0001",
        bill_date="2026-09-09",
        purchase_order="PUR-ORD-2026-00016",
        purchase_order_item="458j82kp8e",
        purchase_receipt="MAT-PRE-2026-00007",
        purchase_receipt_item="068bbdr0mb",
        item_code="M20-DEMO-CARTON",
        source_revision="r4-read-1",
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


def _related_invoice(
    name: str,
    *,
    receipt: str = "OTHER-RECEIPT",
    receipt_item: str = "OTHER-RECEIPT-ITEM",
    bill_reference: str = "OTHER-BILL",
    docstatus: int = 1,
) -> dict[str, Any]:
    invoice = _mapped_invoice()
    invoice.update(
        name=name,
        docstatus=docstatus,
        bill_no=bill_reference,
    )
    item = invoice["items"][0]
    assert isinstance(item, dict)
    item.update(purchase_receipt=receipt, pr_detail=receipt_item)
    return invoice


def _receipt_return(name: str = "MAT-PRE-RETURN-1") -> dict[str, Any]:
    receipt = _purchase_receipt()
    receipt.update(name=name, is_return=1, return_against=_basis().purchase_receipt)
    item = receipt["items"][0]
    assert isinstance(item, dict)
    item.update(qty=-1, received_qty=-1, stock_qty=-1, received_stock_qty=-1)
    return receipt


@dataclass(frozen=True)
class _Call:
    path: str
    method: str
    payload: object | None


class _FakeERP:
    def __init__(
        self,
        *,
        purchase_order: dict[str, Any] | None = None,
        purchase_receipt: dict[str, Any] | None = None,
        mapped_invoice: object | None = None,
        invoice_pages: dict[int, list[str]] | None = None,
        receipt_pages: dict[int, list[str]] | None = None,
        invoices: dict[str, dict[str, Any]] | None = None,
        receipts: dict[str, dict[str, Any]] | None = None,
        blocked_documents: set[tuple[str, str]] | None = None,
    ) -> None:
        self.purchase_order = purchase_order if purchase_order is not None else _purchase_order()
        self.purchase_receipt = (
            purchase_receipt if purchase_receipt is not None else _purchase_receipt()
        )
        self.mapped_invoice = mapped_invoice if mapped_invoice is not None else _mapped_invoice()
        self.invoice_pages = invoice_pages if invoice_pages is not None else {0: []}
        self.receipt_pages = receipt_pages if receipt_pages is not None else {0: []}
        self.invoices = invoices if invoices is not None else {}
        self.receipts = receipts if receipts is not None else {}
        self.blocked_documents = blocked_documents if blocked_documents is not None else set()
        self.calls: list[_Call] = []

    def __call__(self, path: str, *, method: str = "GET", payload: object | None = None) -> object:
        self.calls.append(_Call(path, method, deepcopy(payload)))
        parsed = urlparse(path)
        decoded_path = unquote(parsed.path)
        basis = _basis()
        if decoded_path == f"/api/resource/Purchase Order/{basis.purchase_order}":
            return {"data": self.purchase_order}
        if decoded_path == f"/api/resource/Purchase Receipt/{basis.purchase_receipt}":
            return {"data": self.purchase_receipt}
        if path == MAPPER_PATH:
            return {"message": self.mapped_invoice}
        if decoded_path in {
            "/api/resource/Purchase Invoice",
            "/api/resource/Purchase Receipt",
        }:
            query = parse_qs(parsed.query)
            offset = int(query.get("limit_start", ["0"])[0])
            pages = (
                self.invoice_pages
                if decoded_path.endswith("Purchase Invoice")
                else self.receipt_pages
            )
            return {"data": [{"name": name} for name in pages.get(offset, [])]}
        for doctype, documents in (
            ("Purchase Invoice", self.invoices),
            ("Purchase Receipt", self.receipts),
        ):
            prefix = f"/api/resource/{doctype}/"
            if decoded_path.startswith(prefix):
                name = decoded_path.removeprefix(prefix)
                if (doctype, name) in self.blocked_documents:
                    raise RuntimeError(f"denied {doctype} {name}")
                if name not in documents:
                    raise RuntimeError(f"missing {doctype} {name}")
                return {"data": documents[name]}
        raise AssertionError(f"unexpected transport call: {method} {path}")


class _StepClock:
    def __init__(self, *values: float) -> None:
        self._values = iter(values)

    def __call__(self) -> float:
        return next(self._values)


def _coverage(result: NormalReceiptBillingSourceRead) -> object:
    return result.related_documents_read["coverage"]


def _failure_labels(result: NormalReceiptBillingSourceRead) -> list[str]:
    failures = result.evidence_manifest["failures"]
    assert isinstance(failures, list)
    return [str(failure) for failure in failures]


def test_partial_parent_read_is_incomplete_and_never_ready() -> None:
    fake = _FakeERP(
        invoice_pages={0: ["PI-PARTIAL"]},
        blocked_documents={("Purchase Invoice", "PI-PARTIAL")},
    )

    result = NormalReceiptBillingSourceReader(fake).read(_basis())

    assert result.preview.status == "HOLD"
    assert _coverage(result) == {
        "receipt_line_invoices": False,
        "receipt_returns": False,
        "bill_reference_collisions": False,
    }
    assert any("PI-PARTIAL" in failure for failure in _failure_labels(result))


def test_repeated_related_page_is_incomplete_and_never_ready() -> None:
    names = [f"PI-{index:03d}" for index in range(RELATED_PAGE_SIZE)]
    fake = _FakeERP(invoice_pages={0: names, RELATED_PAGE_SIZE: names})

    result = NormalReceiptBillingSourceReader(fake).read(_basis())

    assert result.preview.status == "HOLD"
    assert _coverage(result) == {
        "receipt_line_invoices": False,
        "receipt_returns": False,
        "bill_reference_collisions": False,
    }
    assert any("repeat" in failure.lower() for failure in _failure_labels(result))
    pages = result.evidence_manifest["pages"]
    assert isinstance(pages, list)
    assert len(pages) == 2


def test_oversized_related_page_is_incomplete_and_never_ready() -> None:
    names = [f"PI-{index:03d}" for index in range(RELATED_PAGE_SIZE + 1)]
    fake = _FakeERP(invoice_pages={0: names})

    result = NormalReceiptBillingSourceReader(fake).read(_basis())

    assert result.preview.status == "HOLD"
    assert _coverage(result) == {
        "receipt_line_invoices": False,
        "receipt_returns": False,
        "bill_reference_collisions": False,
    }
    assert any("page" in failure.lower() for failure in _failure_labels(result))


def test_out_of_order_related_pages_are_incomplete_and_never_ready() -> None:
    first_page = [f"PI-{index:03d}" for index in range(100, 100 + RELATED_PAGE_SIZE)]
    fake = _FakeERP(invoice_pages={0: first_page, RELATED_PAGE_SIZE: ["PI-000"]})

    result = NormalReceiptBillingSourceReader(fake).read(_basis())

    assert result.preview.status == "HOLD"
    assert _coverage(result) == {
        "receipt_line_invoices": False,
        "receipt_returns": False,
        "bill_reference_collisions": False,
    }
    assert any("order" in failure.lower() for failure in _failure_labels(result))


def test_parent_identity_or_scope_mismatch_is_incomplete_and_never_ready() -> None:
    wrong_scope = _related_invoice("PI-WRONG-SCOPE")
    wrong_scope["company"] = "Other Company"
    fake = _FakeERP(
        invoice_pages={0: ["PI-WRONG-SCOPE"]},
        invoices={"PI-WRONG-SCOPE": wrong_scope},
    )

    result = NormalReceiptBillingSourceReader(fake).read(_basis())

    assert result.preview.status == "HOLD"
    assert _coverage(result) == {
        "receipt_line_invoices": False,
        "receipt_returns": False,
        "bill_reference_collisions": False,
    }
    assert any("scope" in failure.lower() for failure in _failure_labels(result))


def test_renamed_parent_or_malformed_children_are_incomplete_and_never_ready() -> None:
    renamed = _related_invoice("PI-ACTUAL")
    malformed = _related_invoice("PI-MALFORMED")
    malformed["items"] = "not a full native child list"
    renamed_fake = _FakeERP(
        invoice_pages={0: ["PI-EXPECTED"]},
        invoices={"PI-EXPECTED": renamed},
    )
    malformed_fake = _FakeERP(
        invoice_pages={0: ["PI-MALFORMED"]},
        invoices={"PI-MALFORMED": malformed},
    )

    renamed_result = NormalReceiptBillingSourceReader(renamed_fake).read(_basis())
    malformed_result = NormalReceiptBillingSourceReader(malformed_fake).read(_basis())

    for result in (renamed_result, malformed_result):
        assert result.preview.status == "HOLD"
        assert _coverage(result) == {
            "receipt_line_invoices": False,
            "receipt_returns": False,
            "bill_reference_collisions": False,
        }
    assert any("identity" in failure.lower() for failure in _failure_labels(renamed_result))
    assert any("child" in failure.lower() for failure in _failure_labels(malformed_result))
    renamed_documents = renamed_result.related_documents_read["documents"]
    malformed_documents = malformed_result.related_documents_read["documents"]
    assert isinstance(renamed_documents, list)
    assert isinstance(malformed_documents, list)
    assert renamed_documents[0]["name"] == "PI-ACTUAL"
    assert malformed_documents[0]["name"] == "PI-MALFORMED"


def test_exhausted_document_cap_is_incomplete_and_never_ready() -> None:
    names = [f"PI-{index:03d}" for index in range(MAX_RELATED_DOCUMENTS + 1)]
    invoices = {name: _related_invoice(name) for name in names}
    pages = {
        offset: names[offset : offset + RELATED_PAGE_SIZE]
        for offset in range(0, len(names), RELATED_PAGE_SIZE)
    }
    fake = _FakeERP(invoice_pages=pages, invoices=invoices)

    result = NormalReceiptBillingSourceReader(fake).read(_basis())

    assert result.preview.status == "HOLD"
    assert _coverage(result) == {
        "receipt_line_invoices": False,
        "receipt_returns": False,
        "bill_reference_collisions": False,
    }
    assert any("limit" in failure.lower() for failure in _failure_labels(result))


def test_malformed_native_mapper_is_hold_even_when_related_pages_are_empty() -> None:
    fake = _FakeERP(mapped_invoice=["not", "a", "native", "document"])

    result = NormalReceiptBillingSourceReader(fake).read(_basis())

    assert result.preview.status == "HOLD"
    assert result.preview.write_allowed is False
    assert _coverage(result) == {
        "receipt_line_invoices": False,
        "receipt_returns": False,
        "bill_reference_collisions": False,
    }


def test_elapsed_budget_stops_starting_calls_after_a_slow_transport_call() -> None:
    fake = _FakeERP()
    clock = _StepClock(0, 0, 31)

    result = NormalReceiptBillingSourceReader(
        fake,
        clock=clock,
        elapsed_budget_seconds=30,
    ).read(_basis())

    assert result.preview.status == "HOLD"
    assert _coverage(result) == {
        "receipt_line_invoices": False,
        "receipt_returns": False,
        "bill_reference_collisions": False,
    }
    assert len(fake.calls) == 1
    assert any("elapsed" in failure.lower() for failure in _failure_labels(result))


def test_oversized_transport_response_is_incomplete_and_never_ready() -> None:
    fake = _FakeERP()
    fake.purchase_order["private_blob"] = "x" * MAX_RESPONSE_BYTES

    result = NormalReceiptBillingSourceReader(fake).read(_basis())

    assert result.preview.status == "HOLD"
    assert _coverage(result) == {
        "receipt_line_invoices": False,
        "receipt_returns": False,
        "bill_reference_collisions": False,
    }
    assert len(fake.calls) == 1
    assert any("size" in failure.lower() for failure in _failure_labels(result))


def test_complete_read_keeps_second_page_candidates_and_never_grants_a_write() -> None:
    names = [f"PI-{index:03d}" for index in range(RELATED_PAGE_SIZE)]
    second_page_name = "PI-SECOND-PAGE"
    invoices = {name: _related_invoice(name) for name in [*names, second_page_name]}
    fake = _FakeERP(
        invoice_pages={0: names, RELATED_PAGE_SIZE: [second_page_name]},
        invoices=invoices,
    )
    before = deepcopy((fake.purchase_order, fake.purchase_receipt, fake.mapped_invoice, invoices))

    result = NormalReceiptBillingSourceReader(fake).read(_basis())

    assert result.preview.status == "READY"
    assert result.preview.read_only is True
    assert result.preview.write_allowed is False
    assert _coverage(result) == {
        "receipt_line_invoices": True,
        "receipt_returns": True,
        "bill_reference_collisions": True,
    }
    related = result.related_documents_read
    assert isinstance(related, dict)
    assert second_page_name in {document["name"] for document in related["documents"]}
    assert (
        deepcopy((fake.purchase_order, fake.purchase_receipt, fake.mapped_invoice, invoices))
        == before
    )
    assert len(result.snapshot_digest) == 64

    post_calls = [call for call in fake.calls if call.method == "POST"]
    assert post_calls == [
        _Call(
            MAPPER_PATH,
            "POST",
            {
                "source_name": _basis().purchase_receipt,
                "args": {"filtered_children": [_basis().purchase_receipt_item]},
            },
        )
    ]
    assert {call.method for call in fake.calls} == {"GET", "POST"}
    assert all("frappe.client.submit" not in call.path for call in fake.calls)
    assert all(
        "/api/resource/Purchase%20Invoice" not in call.path or call.method == "GET"
        for call in fake.calls
    )

    for doctype in ("Purchase Invoice", "Purchase Receipt"):
        query_calls = [
            call
            for call in fake.calls
            if unquote(urlparse(call.path).path) == f"/api/resource/{doctype}"
        ]
        assert query_calls
        for call in query_calls:
            query = parse_qs(urlparse(call.path).query)
            filters = json.loads(query["filters"][0])
            assert filters == [
                ["company", "=", _basis().company],
                ["supplier", "=", _basis().supplier],
            ]
            assert query["order_by"] == ["name asc"]
            assert "docstatus" not in query
            assert "creation" not in query


def test_related_effects_are_preserved_including_own_draft_collision_and_return() -> None:
    basis = _basis()
    own_draft = _related_invoice(
        "PI-OWN-DRAFT",
        receipt=basis.purchase_receipt,
        receipt_item=basis.purchase_receipt_item,
        bill_reference=basis.bill_reference,
        docstatus=0,
    )
    collision = _related_invoice("PI-COLLISION", bill_reference=basis.bill_reference)
    returned_receipt = _receipt_return()
    fake = _FakeERP(
        invoice_pages={0: ["PI-COLLISION", "PI-OWN-DRAFT"]},
        receipt_pages={0: [returned_receipt["name"]]},
        invoices={"PI-OWN-DRAFT": own_draft, "PI-COLLISION": collision},
        receipts={str(returned_receipt["name"]): returned_receipt},
    )

    result = NormalReceiptBillingSourceReader(fake).read(basis)

    assert result.preview.status == "HOLD"
    related = result.related_documents_read
    assert isinstance(related, dict)
    names = {document["name"] for document in related["documents"]}
    assert names == {"PI-OWN-DRAFT", "PI-COLLISION", "MAT-PRE-RETURN-1"}
    assert _coverage(result) == {
        "receipt_line_invoices": True,
        "receipt_returns": True,
        "bill_reference_collisions": True,
    }


def test_draft_cancelled_credit_and_mixed_related_invoices_are_not_status_filtered() -> None:
    basis = _basis()
    draft = _related_invoice(
        "PI-DRAFT",
        receipt=basis.purchase_receipt,
        receipt_item=basis.purchase_receipt_item,
        docstatus=0,
    )
    cancelled = _related_invoice(
        "PI-CANCELLED",
        receipt=basis.purchase_receipt,
        receipt_item=basis.purchase_receipt_item,
        docstatus=2,
    )
    credit = _related_invoice(
        "PI-CREDIT",
        receipt=basis.purchase_receipt,
        receipt_item=basis.purchase_receipt_item,
    )
    credit.update(is_return=1, return_against="PI-ORIGINAL")
    mixed = _related_invoice(
        "PI-MIXED",
        receipt=basis.purchase_receipt,
        receipt_item=basis.purchase_receipt_item,
    )
    mixed_item = deepcopy(mixed["items"][0])
    assert isinstance(mixed_item, dict)
    mixed_item.update(purchase_receipt="OTHER-RECEIPT", pr_detail="OTHER-RECEIPT-ITEM")
    mixed["items"].append(mixed_item)
    invoices = {
        "PI-CANCELLED": cancelled,
        "PI-CREDIT": credit,
        "PI-DRAFT": draft,
        "PI-MIXED": mixed,
    }
    fake = _FakeERP(invoice_pages={0: sorted(invoices)}, invoices=invoices)

    result = NormalReceiptBillingSourceReader(fake).read(basis)

    assert result.preview.status == "HOLD"
    related = result.related_documents_read
    assert isinstance(related, dict)
    assert {document["name"] for document in related["documents"]} == set(invoices)
    assert _coverage(result) == {
        "receipt_line_invoices": True,
        "receipt_returns": True,
        "bill_reference_collisions": True,
    }


def test_missing_related_invoice_bill_or_association_fields_are_incomplete_not_unrelated() -> None:
    missing_bill = _related_invoice("PI-MISSING-BILL")
    del missing_bill["bill_no"]
    missing_association = _related_invoice("PI-MISSING-ASSOCIATION")
    missing_association["items"] = [{}]

    for name, invoice in (
        ("PI-MISSING-BILL", missing_bill),
        ("PI-MISSING-ASSOCIATION", missing_association),
    ):
        result = NormalReceiptBillingSourceReader(
            _FakeERP(invoice_pages={0: [name]}, invoices={name: invoice})
        ).read(_basis())

        assert result.preview.status == "HOLD"
        assert _coverage(result) == {
            "receipt_line_invoices": False,
            "receipt_returns": False,
            "bill_reference_collisions": False,
        }
        assert any("schema" in failure.lower() for failure in _failure_labels(result))


def test_explicit_null_related_invoice_fields_are_known_unlinked_not_missing() -> None:
    invoice = _related_invoice("PI-EXPLICITLY-UNLINKED")
    invoice["bill_no"] = None
    item = invoice["items"][0]
    assert isinstance(item, dict)
    item.update(
        purchase_order=None,
        po_detail=None,
        purchase_receipt=None,
        pr_detail=None,
    )
    fake = _FakeERP(
        invoice_pages={0: ["PI-EXPLICITLY-UNLINKED"]},
        invoices={"PI-EXPLICITLY-UNLINKED": invoice},
    )

    result = NormalReceiptBillingSourceReader(fake).read(_basis())

    assert result.preview.status == "READY"
    assert _coverage(result) == {
        "receipt_line_invoices": True,
        "receipt_returns": True,
        "bill_reference_collisions": True,
    }


@pytest.mark.parametrize(
    ("kind", "field"),
    (
        ("invoice_header", "bill_no"),
        ("invoice_header", "supplier_invoice_no"),
        ("invoice_header", "return_against"),
        ("invoice_item", "purchase_order"),
        ("invoice_item", "po_no"),
        ("invoice_item", "po_detail"),
        ("invoice_item", "purchase_order_item"),
        ("invoice_item", "purchase_receipt"),
        ("invoice_item", "receipt"),
        ("invoice_item", "pr_detail"),
        ("invoice_item", "purchase_receipt_item"),
        ("receipt_header", "return_against"),
        ("receipt_item", "purchase_order"),
        ("receipt_item", "po_no"),
        ("receipt_item", "purchase_order_item"),
        ("receipt_item", "po_detail"),
        ("receipt_item", "purchase_receipt"),
        ("receipt_item", "receipt"),
        ("receipt_item", "pr_detail"),
        ("receipt_item", "purchase_receipt_item"),
    ),
)
@pytest.mark.parametrize("bad_value", ({}, [], 7, True), ids=("mapping", "list", "int", "bool"))
def test_present_decisive_identifier_bad_types_are_incomplete(
    kind: str, field: str, bad_value: object
) -> None:
    if kind.startswith("invoice"):
        name = "PI-BAD-IDENTIFIER"
        document = _related_invoice(name)
        target = document if kind == "invoice_header" else document["items"][0]
        assert isinstance(target, dict)
        target[field] = deepcopy(bad_value)
        fake = _FakeERP(invoice_pages={0: [name]}, invoices={name: document})
    else:
        name = "MAT-PRE-BAD-IDENTIFIER"
        document = _purchase_receipt()
        document.update(name=name, is_return=0)
        target = document if kind == "receipt_header" else document["items"][0]
        assert isinstance(target, dict)
        target[field] = deepcopy(bad_value)
        fake = _FakeERP(receipt_pages={0: [name]}, receipts={name: document})

    result = NormalReceiptBillingSourceReader(fake).read(_basis())

    assert result.preview.status == "HOLD"
    assert _coverage(result) == {
        "receipt_line_invoices": False,
        "receipt_returns": False,
        "bill_reference_collisions": False,
    }
    assert any("schema" in failure.lower() for failure in _failure_labels(result))


def test_identifier_aliases_preserve_empty_and_reject_conflicting_or_whitespace_values() -> None:
    conflicting_bill = _related_invoice("PI-CONFLICTING-BILL")
    conflicting_bill.update(bill_no="", supplier_invoice_no="OTHER-BILL")
    conflicting_receipt = _related_invoice("PI-CONFLICTING-RECEIPT")
    conflicting_item = conflicting_receipt["items"][0]
    assert isinstance(conflicting_item, dict)
    conflicting_item.update(purchase_receipt="", receipt="OTHER-RECEIPT")
    whitespace = _related_invoice("PI-WHITESPACE")
    whitespace["bill_no"] = " \t"

    for name, invoice in (
        ("PI-CONFLICTING-BILL", conflicting_bill),
        ("PI-CONFLICTING-RECEIPT", conflicting_receipt),
        ("PI-WHITESPACE", whitespace),
    ):
        result = NormalReceiptBillingSourceReader(
            _FakeERP(invoice_pages={0: [name]}, invoices={name: invoice})
        ).read(_basis())

        assert result.preview.status == "HOLD"
        assert _coverage(result) == {
            "receipt_line_invoices": False,
            "receipt_returns": False,
            "bill_reference_collisions": False,
        }

    accepted = _related_invoice("PI-CONSISTENT-ALIASES")
    accepted.update(bill_no="OTHER-BILL", supplier_invoice_no="OTHER-BILL")
    accepted_item = accepted["items"][0]
    assert isinstance(accepted_item, dict)
    accepted_item.update(
        purchase_receipt=None,
        receipt="OTHER-RECEIPT",
        pr_detail=None,
        purchase_receipt_item="OTHER-RECEIPT-ITEM",
    )
    accepted_result = NormalReceiptBillingSourceReader(
        _FakeERP(
            invoice_pages={0: ["PI-CONSISTENT-ALIASES"]},
            invoices={"PI-CONSISTENT-ALIASES": accepted},
        )
    ).read(_basis())

    assert accepted_result.preview.status == "READY"
    assert _coverage(accepted_result) == {
        "receipt_line_invoices": True,
        "receipt_returns": True,
        "bill_reference_collisions": True,
    }


def test_other_receipt_native_invoice_needs_no_absent_row_ids() -> None:
    invoice = _related_invoice("PI-NATIVE-OTHER-RECEIPT")
    item = invoice["items"][0]
    assert isinstance(item, dict)
    item.update(
        purchase_order="PUR-ORD-OTHER",
        purchase_receipt="MAT-PRE-OTHER",
    )
    del item["po_detail"]
    del item["pr_detail"]

    result = NormalReceiptBillingSourceReader(
        _FakeERP(
            invoice_pages={0: ["PI-NATIVE-OTHER-RECEIPT"]},
            invoices={"PI-NATIVE-OTHER-RECEIPT": invoice},
        )
    ).read(_basis())

    assert result.preview.status == "READY"
    assert _coverage(result) == {
        "receipt_line_invoices": True,
        "receipt_returns": True,
        "bill_reference_collisions": True,
    }


def test_target_invoice_relation_needs_exact_pr_and_po_row_identity() -> None:
    basis = _basis()
    empty_pr_line = _related_invoice("PI-EMPTY-PR-LINE", receipt=basis.purchase_receipt)
    empty_item = empty_pr_line["items"][0]
    assert isinstance(empty_item, dict)
    empty_item["pr_detail"] = ""
    missing_po_rows = _related_invoice(
        "PI-MISSING-PO-ROWS",
        receipt=basis.purchase_receipt,
        receipt_item=basis.purchase_receipt_item,
    )
    missing_po_item = missing_po_rows["items"][0]
    assert isinstance(missing_po_item, dict)
    del missing_po_item["purchase_order"]
    del missing_po_item["po_detail"]
    empty_items = _related_invoice("PI-EMPTY-ITEMS")
    empty_items["items"] = []

    for name, invoice in (
        ("PI-EMPTY-PR-LINE", empty_pr_line),
        ("PI-MISSING-PO-ROWS", missing_po_rows),
        ("PI-EMPTY-ITEMS", empty_items),
    ):
        result = NormalReceiptBillingSourceReader(
            _FakeERP(invoice_pages={0: [name]}, invoices={name: invoice})
        ).read(basis)

        assert result.preview.status == "HOLD"
        assert _coverage(result) == {
            "receipt_line_invoices": False,
            "receipt_returns": False,
            "bill_reference_collisions": False,
        }

    mismatched_po = _related_invoice(
        "PI-TARGET-PR-WRONG-PO",
        receipt=basis.purchase_receipt,
        receipt_item=basis.purchase_receipt_item,
    )
    mismatch_item = mismatched_po["items"][0]
    assert isinstance(mismatch_item, dict)
    mismatch_item.update(purchase_order="PUR-ORD-OTHER", po_detail="OTHER-PO-ITEM")
    mismatch_result = NormalReceiptBillingSourceReader(
        _FakeERP(
            invoice_pages={0: ["PI-TARGET-PR-WRONG-PO"]},
            invoices={"PI-TARGET-PR-WRONG-PO": mismatched_po},
        )
    ).read(basis)

    assert mismatch_result.preview.status == "HOLD"
    assert _coverage(mismatch_result) == {
        "receipt_line_invoices": True,
        "receipt_returns": True,
        "bill_reference_collisions": True,
    }


def test_related_return_decision_schema_keeps_known_effects_but_holds_unknown_coverage() -> None:
    basis = _basis()
    direct_target = _receipt_return("MAT-PRE-DIRECT-TARGET-RETURN")
    direct_target["items"] = [{}]
    other_header_target_child = _receipt_return("MAT-PRE-OTHER-HEADER-TARGET-CHILD")
    other_header_target_child["return_against"] = "MAT-PRE-OTHER"

    for name, receipt in (
        ("MAT-PRE-DIRECT-TARGET-RETURN", direct_target),
        ("MAT-PRE-OTHER-HEADER-TARGET-CHILD", other_header_target_child),
    ):
        result = NormalReceiptBillingSourceReader(
            _FakeERP(receipt_pages={0: [name]}, receipts={name: receipt})
        ).read(basis)

        assert result.preview.status == "HOLD"
        assert _coverage(result) == {
            "receipt_line_invoices": True,
            "receipt_returns": True,
            "bill_reference_collisions": True,
        }

    for name, unknown_return_against in (
        ("MAT-PRE-MISSING-RETURN-HEADER", None),
        ("MAT-PRE-NULL-RETURN-HEADER", None),
        ("MAT-PRE-EMPTY-RETURN-HEADER", ""),
    ):
        unknown = _receipt_return(name)
        unknown["items"] = []
        if name == "MAT-PRE-MISSING-RETURN-HEADER":
            del unknown["return_against"]
        else:
            unknown["return_against"] = unknown_return_against
        result = NormalReceiptBillingSourceReader(
            _FakeERP(receipt_pages={0: [name]}, receipts={name: unknown})
        ).read(basis)

        assert result.preview.status == "HOLD"
        assert _coverage(result) == {
            "receipt_line_invoices": False,
            "receipt_returns": False,
            "bill_reference_collisions": False,
        }


def test_related_nonreturn_needs_no_unrelated_ids_but_validates_present_values() -> None:
    unrelated = _purchase_receipt()
    unrelated.update(name="MAT-PRE-NONRETURN-NO-LINKS", is_return=0, items=[{}])
    valid_result = NormalReceiptBillingSourceReader(
        _FakeERP(
            receipt_pages={0: ["MAT-PRE-NONRETURN-NO-LINKS"]},
            receipts={"MAT-PRE-NONRETURN-NO-LINKS": unrelated},
        )
    ).read(_basis())

    assert valid_result.preview.status == "READY"
    assert _coverage(valid_result) == {
        "receipt_line_invoices": True,
        "receipt_returns": True,
        "bill_reference_collisions": True,
    }
