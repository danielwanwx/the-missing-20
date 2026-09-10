from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import cast

import pytest

from the_missing_20.adapters.normal_receipt_billing_preview import (
    BillingPreview,
    SyntheticBillingBasis,
    validate_billing_preview,
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


def _purchase_order() -> dict[str, object]:
    basis = _basis()
    return {
        "doctype": "Purchase Order",
        "name": basis.purchase_order,
        "docstatus": 1,
        "modified": "2026-09-09T21:00:00Z",
        "company": basis.company,
        "supplier": basis.supplier,
        "currency": "USD",
        "discount_amount": 0,
        "rounding_adjustment": 0,
        "taxes": [],
        "items": [
            {
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


def _purchase_receipt() -> dict[str, object]:
    basis = _basis()
    return {
        "doctype": "Purchase Receipt",
        "name": basis.purchase_receipt,
        "docstatus": 1,
        "modified": "2026-09-09T21:05:00Z",
        "company": basis.company,
        "supplier": basis.supplier,
        "currency": "USD",
        "discount_amount": 0,
        "rounding_adjustment": 0,
        "is_return": 0,
        "taxes": [],
        "items": [
            {
                "name": basis.purchase_receipt_item,
                "item_code": basis.item_code,
                "qty": 1,
                "uom": "Box",
                "stock_uom": "Box",
                "conversion_factor": 1,
                "purchase_order": basis.purchase_order,
                "purchase_order_item": basis.purchase_order_item,
                "rate": 50,
                "net_rate": 50,
                "amount": 50,
                "net_amount": 50,
                "stock_qty": 1,
                "received_qty": 1,
                "received_stock_qty": 1,
                "rejected_qty": 0,
                "returned_qty": 0,
            }
        ],
    }


def _mapped_invoice() -> dict[str, object]:
    basis = _basis()
    return {
        "doctype": "Purchase Invoice",
        "name": None,
        "docstatus": 0,
        "company": basis.company,
        "supplier": basis.supplier,
        "credit_to": "Creditors - M20",
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
                "item_code": basis.item_code,
                "qty": 1,
                "uom": "Box",
                "stock_uom": "Box",
                "conversion_factor": 1,
                "rate": 50,
                "net_rate": 50,
                "amount": 50,
                "net_amount": 50,
                "stock_qty": 1,
                "expense_account": "Stock Received But Not Billed - M20",
                "purchase_order": basis.purchase_order,
                "po_detail": basis.purchase_order_item,
                "purchase_receipt": basis.purchase_receipt,
                "pr_detail": basis.purchase_receipt_item,
            }
        ],
    }


def _related(*documents: dict[str, object], complete: bool = True) -> dict[str, object]:
    return {
        "status": "COMPLETE" if complete else "PARTIAL",
        "pagination": {"complete": complete, "pages": 1},
        "scope": {
            "company": _basis().company,
            "supplier": _basis().supplier,
            "purchase_order": _basis().purchase_order,
            "purchase_order_item": _basis().purchase_order_item,
            "purchase_receipt": _basis().purchase_receipt,
            "purchase_receipt_item": _basis().purchase_receipt_item,
        },
        "coverage": {
            "receipt_line_invoices": True,
            "receipt_returns": True,
            "bill_reference_collisions": True,
        },
        "observed_at": "2026-09-09T21:10:00Z",
        "source_revision": "related-r4-1",
        "documents": list(documents),
    }


def _valid_preview(**overrides: object) -> BillingPreview:
    values: dict[str, object] = {
        "basis": _basis(),
        "purchase_order": _purchase_order(),
        "purchase_receipt": _purchase_receipt(),
        "mapped_invoice": _mapped_invoice(),
        "related_documents_read": _related(),
    }
    values.update(overrides)
    return validate_billing_preview(**values)  # type: ignore[arg-type]


def test_preview_is_ready_digest_bound_and_does_not_mutate_sources() -> None:
    basis = _basis()
    po = _purchase_order()
    pr = _purchase_receipt()
    mapped = _mapped_invoice()
    related = _related()
    before = deepcopy((basis, po, pr, mapped, related))

    preview = validate_billing_preview(
        basis,
        purchase_order=po,
        purchase_receipt=pr,
        mapped_invoice=mapped,
        related_documents_read=related,
    )

    assert preview.status == "READY"
    assert preview.write_allowed is False
    assert preview.read_only is True
    assert preview.quantity == 1
    assert preview.uom == "Box"
    assert preview.net_amount == 50
    assert preview.gross_amount == 50
    assert preview.exact_ids.purchase_order_item == "458j82kp8e"
    assert preview.exact_ids.purchase_receipt_item == "068bbdr0mb"
    assert preview.bill_digest == basis.bill_digest
    assert len(preview.source_digest) == 64
    assert deepcopy((basis, po, pr, mapped, related)) == before


def test_preview_rejects_unknown_or_incomplete_related_read() -> None:
    preview = _valid_preview(related_documents_read={"documents": []})

    assert preview.status == "HOLD"
    assert preview.write_allowed is False
    assert any("COMPLETE" in reason for reason in preview.reasons)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("purchase_order", "PUR-ORD-WRONG"),
        ("purchase_receipt", "MAT-PRE-WRONG"),
        ("company", "Other Company"),
        ("supplier", "Other Supplier"),
        ("item_code", "OTHER-ITEM"),
        ("uom", "Nos"),
        ("stock_uom", "Nos"),
        ("conversion_factor", 2),
        ("quantity", 2),
        ("net_rate", 51),
        ("gross_amount", 51),
    ),
)
def test_basis_outside_pilot_is_rejected(field: str, value: object) -> None:
    try:
        basis = replace(_basis(), **{field: value})  # type: ignore[arg-type]
    except ValueError:
        return
    preview = _valid_preview(basis=basis)

    assert preview.status == "HOLD"
    assert preview.write_allowed is False


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        (
            lambda invoice: invoice["items"].__setitem__(
                0, {**invoice["items"][0], "po_detail": "wrong"}
            ),
            "po_detail",
        ),
        (
            lambda invoice: invoice["items"].__setitem__(
                0, {**invoice["items"][0], "pr_detail": "wrong"}
            ),
            "pr_detail",
        ),
        (
            lambda invoice: invoice["items"].__setitem__(0, {**invoice["items"][0], "qty": 2}),
            "qty",
        ),
        (
            lambda invoice: invoice["items"].__setitem__(0, {**invoice["items"][0], "uom": "Nos"}),
            "uom",
        ),
        (
            lambda invoice: invoice["items"].__setitem__(0, {**invoice["items"][0], "rate": 51}),
            "rate",
        ),
        (lambda invoice: invoice.__setitem__("grand_total", 51), "grand_total"),
        (
            lambda invoice: invoice.__setitem__(
                "taxes", [{"account_head": "Tax", "rate": 5, "tax_amount": 2}]
            ),
            "tax",
        ),
        (lambda invoice: invoice.__setitem__("is_paid", 1), "is_paid"),
        (lambda invoice: invoice.__setitem__("update_stock", 1), "update_stock"),
        (lambda invoice: invoice.__setitem__("name", "PI-ALREADY"), "uninserted"),
    ),
)
def test_mapper_contract_fail_closed(mutation: object, message: str) -> None:
    mapped = _mapped_invoice()
    cast_mutation = mutation
    cast_mutation(mapped)  # type: ignore[operator]
    preview = _valid_preview(mapped_invoice=mapped)

    assert preview.status == "HOLD"
    assert preview.write_allowed is False
    assert any(message.lower() in reason.lower() for reason in preview.reasons)


def test_wrong_source_child_row_is_held() -> None:
    po = _purchase_order()
    po["items"] = [{**po["items"][0], "name": "OTHER-ROW"}]  # type: ignore[index]

    preview = _valid_preview(purchase_order=po)

    assert preview.status == "HOLD"
    assert any("exact source row" in reason for reason in preview.reasons)


def test_existing_exact_submitted_invoice_is_reused_without_new_plan_permission() -> None:
    existing = _mapped_invoice()
    existing["name"] = "ACC-PINV-EXISTING"
    existing["docstatus"] = 1
    existing["bill_no"] = _basis().bill_reference

    preview = _valid_preview(related_documents_read=_related(existing))

    assert preview.status == "ALREADY_SUBMITTED"
    assert preview.write_allowed is False
    assert preview.exact_ids.existing_invoice_names == ("ACC-PINV-EXISTING",)


def test_existing_draft_is_visible_but_not_a_new_ready_write() -> None:
    existing = _mapped_invoice()
    existing["name"] = "ACC-PINV-DRAFT"
    existing["bill_no"] = _basis().bill_reference

    preview = _valid_preview(related_documents_read=_related(existing))

    assert preview.status == "DRAFT_EXISTS"
    assert preview.write_allowed is False
    assert preview.exact_ids.existing_invoice_names == ("ACC-PINV-DRAFT",)


def test_existing_return_or_already_billed_line_is_held() -> None:
    returned = _mapped_invoice()
    returned["name"] = "ACC-PINV-RETURN"
    returned["docstatus"] = 1
    returned["bill_no"] = _basis().bill_reference
    returned["is_return"] = 1
    billed = _mapped_invoice()
    billed["name"] = "ACC-PINV-OTHER"
    billed["docstatus"] = 1
    billed["bill_no"] = "OTHER-BILL"

    return_preview = _valid_preview(related_documents_read=_related(returned))
    billed_preview = _valid_preview(related_documents_read=_related(billed))

    assert return_preview.status == "HOLD"
    assert any("return" in reason for reason in return_preview.reasons)
    assert billed_preview.status == "ALREADY_BILLED"
    assert billed_preview.write_allowed is False


def test_source_modified_changes_digest_and_holds_fresh_confidence() -> None:
    first = _valid_preview()
    changed_pr = _purchase_receipt()
    changed_pr["modified"] = "2026-09-09T22:00:00Z"
    second = _valid_preview(purchase_receipt=changed_pr)

    assert first.source_digest != second.source_digest
    assert second.status == "READY"
    assert second.reasons == ()


def test_raw_mapper_can_omit_supplier_bill_number_while_basis_keeps_distinct_dates() -> None:
    basis = replace(_basis(), bill_date="2026-09-10")
    mapped = _mapped_invoice()

    assert "bill_no" not in mapped
    preview = _valid_preview(basis=basis, mapped_invoice=mapped)

    assert preview.status == "READY"
    assert preview.bill_digest == basis.bill_digest


@pytest.mark.parametrize(
    ("document", "field", "value", "message"),
    (
        ("purchase_receipt", "is_return", 1, "return"),
        ("purchase_receipt", "currency", "EUR", "currency"),
        (
            "purchase_receipt",
            "items",
            [
                {
                    "name": "068bbdr0mb",
                    "item_code": "M20-DEMO-CARTON",
                    "qty": 1,
                    "uom": "Box",
                    "stock_uom": "Box",
                    "conversion_factor": 99,
                    "purchase_order": "PUR-ORD-2026-00016",
                    "purchase_order_item": "458j82kp8e",
                    "rate": 50,
                    "net_rate": 50,
                    "amount": 50,
                    "net_amount": 50,
                    "stock_qty": 1,
                    "received_stock_qty": 1,
                    "rejected_qty": 0,
                    "returned_qty": 0,
                }
            ],
            "conversion",
        ),
        (
            "purchase_receipt",
            "items",
            [
                {
                    "name": "068bbdr0mb",
                    "item_code": "M20-DEMO-CARTON",
                    "qty": 1,
                    "uom": "Box",
                    "stock_uom": "Box",
                    "conversion_factor": 1,
                    "purchase_order": "WRONG",
                    "purchase_order_item": "458j82kp8e",
                    "rate": 50,
                    "net_rate": 50,
                    "amount": 50,
                    "net_amount": 50,
                    "stock_qty": 1,
                    "received_qty": 1,
                    "received_stock_qty": 1,
                    "rejected_qty": 0,
                    "returned_qty": 0,
                }
            ],
            "purchase_order",
        ),
        ("purchase_order", "currency", "EUR", "currency"),
        (
            "purchase_order",
            "items",
            [
                {
                    "name": "458j82kp8e",
                    "item_code": "M20-DEMO-CARTON",
                    "qty": 40,
                    "uom": "Box",
                    "stock_uom": "Box",
                    "conversion_factor": 1,
                    "rate": 51,
                    "net_rate": 51,
                    "amount": 2040,
                    "net_amount": 2040,
                    "stock_qty": 40,
                    "received_qty": 1,
                    "returned_qty": 0,
                }
            ],
            "rate",
        ),
    ),
)
def test_native_source_commercial_and_return_fields_fail_closed(
    document: str, field: str, value: object, message: str
) -> None:
    source = _purchase_receipt() if document == "purchase_receipt" else _purchase_order()
    source[field] = value

    preview = _valid_preview(**{document: source})

    assert preview.status == "HOLD"
    assert any(message.lower() in reason.lower() for reason in preview.reasons)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("credit_to", "WRONG ACCOUNT", "credit_to"),
        ("update_stock", None, "update_stock"),
        ("is_return", None, "return"),
        ("rounding_adjustment", None, "rounding"),
        ("paid_amount", None, "paid_amount"),
        ("discount_amount", None, "discount"),
        ("additional_discount_percentage", None, "discount"),
        ("total_taxes_and_charges", None, "taxes"),
    ),
)
def test_native_mapper_accounts_and_flags_are_explicit(
    field: str, value: object, message: str
) -> None:
    mapped = _mapped_invoice()
    mapped[field] = value

    preview = _valid_preview(mapped_invoice=mapped)

    assert preview.status == "HOLD"
    assert any(message.lower() in reason.lower() for reason in preview.reasons)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("expense_account", "WRONG ACCOUNT", "expense_account"),
        ("stock_qty", 999, "stock_qty"),
    ),
)
def test_native_mapper_line_accounts_and_stock_quantity_match_source(
    field: str, value: object, message: str
) -> None:
    mapped = _mapped_invoice()
    mapped["items"][0][field] = value  # type: ignore[index]

    preview = _valid_preview(mapped_invoice=mapped)

    assert preview.status == "HOLD"
    assert any(message.lower() in reason.lower() for reason in preview.reasons)


def test_malformed_nan_mapper_quantity_returns_hold() -> None:
    mapped = _mapped_invoice()
    mapped["items"][0]["qty"] = float("nan")  # type: ignore[index]

    preview = _valid_preview(mapped_invoice=mapped)

    assert preview.status == "HOLD"
    assert any("qty" in reason.lower() for reason in preview.reasons)


def test_lookup_scope_and_observation_are_required_and_digest_bound() -> None:
    first = _valid_preview()
    wrong_scope = _related()
    scope = cast(dict[str, object], wrong_scope["scope"])
    wrong_scope["scope"] = {**scope, "purchase_receipt": "OTHER"}
    wrong = _valid_preview(related_documents_read=wrong_scope)
    changed_observation = _related()
    changed_observation["observed_at"] = "2026-09-09T22:10:00Z"
    changed = _valid_preview(related_documents_read=changed_observation)

    assert wrong.status == "HOLD"
    assert any("scope" in reason.lower() for reason in wrong.reasons)
    assert changed.status == "READY"
    assert first.source_digest != changed.source_digest
    assert first.source_digest != wrong.source_digest


@pytest.mark.parametrize("qty", (None, -1, 0, 0.5))
def test_existing_submitted_partial_or_malformed_quantity_holds(qty: object) -> None:
    existing = _mapped_invoice()
    existing["name"] = "PI-PARTIAL"
    existing["docstatus"] = 1
    existing["bill_no"] = "OTHER-BILL"
    existing["items"][0]["qty"] = qty  # type: ignore[index]

    preview = _valid_preview(related_documents_read=_related(existing))

    assert preview.status == "HOLD"
    assert any("billed quantity" in reason.lower() for reason in preview.reasons)


def test_existing_linked_draft_with_different_bill_reference_holds() -> None:
    existing = _mapped_invoice()
    existing["name"] = "PI-OTHER-DRAFT"
    existing["docstatus"] = 0
    existing["bill_no"] = "OTHER-BILL"

    preview = _valid_preview(related_documents_read=_related(existing))

    assert preview.status == "HOLD"
    assert any("draft" in reason.lower() for reason in preview.reasons)


def test_contradictory_pagination_completeness_is_held() -> None:
    related = _related()
    related["pagination"]["complete"] = False  # type: ignore[index]
    related["pagination_complete"] = True

    preview = _valid_preview(related_documents_read=related)

    assert preview.status == "HOLD"
    assert any("pagination" in reason.lower() for reason in preview.reasons)


def test_source_docstatus_boolean_is_not_submitted_numeric_status() -> None:
    purchase_receipt = _purchase_receipt()
    purchase_receipt["docstatus"] = True

    preview = _valid_preview(purchase_receipt=purchase_receipt)

    assert preview.status == "HOLD"
    assert any("docstatus" in reason.lower() for reason in preview.reasons)


def test_native_purchase_receipt_return_is_held_from_related_read() -> None:
    basis = _basis()
    returned_receipt = _purchase_receipt()
    returned_receipt.update(
        name="RETURN-1",
        is_return=1,
        return_against=basis.purchase_receipt,
    )
    returned_receipt["items"][0]["qty"] = -1  # type: ignore[index]

    preview = _valid_preview(related_documents_read=_related(returned_receipt))

    assert preview.status == "HOLD"
    assert any("return" in reason.lower() for reason in preview.reasons)


@pytest.mark.parametrize("coverage", (None, {"receipt_line_invoices": True}))
def test_related_read_requires_explicit_billing_and_return_coverage(
    coverage: object,
) -> None:
    related = _related()
    related["coverage"] = coverage

    preview = _valid_preview(related_documents_read=related)

    assert preview.status == "HOLD"
    assert any("coverage" in reason.lower() for reason in preview.reasons)


def test_supplier_bill_reference_collision_on_another_receipt_is_held() -> None:
    collision = _mapped_invoice()
    collision.update(name="PI-COLLISION", docstatus=1, bill_no=_basis().bill_reference)
    collision["items"][0].update(  # type: ignore[index]
        purchase_receipt="OTHER-PR",
        pr_detail="OTHER-PR-ROW",
    )

    preview = _valid_preview(related_documents_read=_related(collision))

    assert preview.status == "HOLD"
    assert any("supplier bill reference" in reason.lower() for reason in preview.reasons)
