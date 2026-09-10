from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import replace
from typing import cast

import pytest

from the_missing_20.adapters.normal_receipt_billing_native_request import (
    INSERT_PATH,
    SUBMIT_PATH,
    NativeDraftAcknowledgement,
    NativeInsertRequest,
    NativeSubmitRequest,
    bind_native_insert_request,
    validate_native_draft_acknowledgement,
    validate_native_submitted_readback,
)
from the_missing_20.adapters.normal_receipt_billing_preview import (
    BillingPreview,
    SyntheticBillingBasis,
    validate_billing_preview,
    validate_native_purchase_invoice,
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
                "expense_account": basis.expense_account,
                "purchase_order": basis.purchase_order,
                "po_detail": basis.purchase_order_item,
                "purchase_receipt": basis.purchase_receipt,
                "pr_detail": basis.purchase_receipt_item,
            }
        ],
    }


def _related() -> dict[str, object]:
    basis = _basis()
    return {
        "status": "COMPLETE",
        "pagination": {"complete": True, "pages": 0},
        "scope": {
            "company": basis.company,
            "supplier": basis.supplier,
            "purchase_order": basis.purchase_order,
            "purchase_order_item": basis.purchase_order_item,
            "purchase_receipt": basis.purchase_receipt,
            "purchase_receipt_item": basis.purchase_receipt_item,
        },
        "coverage": {
            "receipt_line_invoices": True,
            "receipt_returns": True,
            "bill_reference_collisions": True,
        },
        "observed_at": "2026-09-09T21:10:00Z",
        "source_revision": "related-r4-1",
        "documents": [],
    }


def _preview_for(
    mapped_invoice: Mapping[str, object],
    *,
    purchase_order: Mapping[str, object],
    purchase_receipt: Mapping[str, object],
    related_documents_read: Mapping[str, object],
) -> BillingPreview:
    return validate_billing_preview(
        _basis(),
        purchase_order=purchase_order,
        purchase_receipt=purchase_receipt,
        mapped_invoice=mapped_invoice,
        related_documents_read=related_documents_read,
    )


def _preview(mapped_invoice: dict[str, object]) -> BillingPreview:
    return _preview_for(
        mapped_invoice,
        purchase_order=_purchase_order(),
        purchase_receipt=_purchase_receipt(),
        related_documents_read=_related(),
    )


def _bound_request() -> NativeInsertRequest:
    mapper = _mapped_invoice()
    return bind_native_insert_request(
        _basis(),
        purchase_order=_purchase_order(),
        purchase_receipt=_purchase_receipt(),
        mapper_document=mapper,
        related_documents_read=_related(),
        preview=_preview(mapper),
    )


def test_ready_raw_mapper_is_admitted_before_an_immutable_two_field_clone() -> None:
    basis = _basis()
    mapper = _mapped_invoice()
    before = deepcopy(mapper)
    preview = _preview(mapper)

    request = bind_native_insert_request(
        basis,
        purchase_order=_purchase_order(),
        purchase_receipt=_purchase_receipt(),
        mapper_document=mapper,
        related_documents_read=_related(),
        preview=preview,
    )

    assert preview.status == "READY"
    assert mapper == before
    assert request.method == "POST"
    assert request.path == INSERT_PATH
    assert request.bill_digest == basis.bill_digest
    assert request.body["bill_no"] == basis.bill_reference
    assert request.body["bill_date"] == basis.bill_date
    assert set(request.body) == {*mapper, "bill_no", "bill_date"}
    items = request.body["items"]
    assert isinstance(items, tuple)
    assert items[0]["purchase_receipt"] == basis.purchase_receipt
    with pytest.raises(TypeError):
        request.body["bill_no"] = "replacement"  # type: ignore[index]

    mapper["items"][0]["qty"] = 99  # type: ignore[index]
    assert items[0]["qty"] == 1


@pytest.mark.parametrize(
    "changed_input",
    (
        "purchase_order",
        "purchase_receipt",
        "mapper_document",
        "related_documents_read",
    ),
)
def test_detached_ready_preview_cannot_bind_a_changed_current_source_tuple(
    changed_input: str,
) -> None:
    basis = _basis()
    purchase_order_a = _purchase_order()
    purchase_receipt_a = _purchase_receipt()
    mapper_a = _mapped_invoice()
    related_a = _related()
    preview_a = _preview_for(
        mapper_a,
        purchase_order=purchase_order_a,
        purchase_receipt=purchase_receipt_a,
        related_documents_read=related_a,
    )
    purchase_order_b = deepcopy(purchase_order_a)
    purchase_receipt_b = deepcopy(purchase_receipt_a)
    mapper_b = deepcopy(mapper_a)
    related_b = deepcopy(related_a)
    if changed_input == "purchase_order":
        purchase_order_b["modified"] = "2026-09-09T22:00:00Z"
    elif changed_input == "purchase_receipt":
        purchase_receipt_b["modified"] = "2026-09-09T22:05:00Z"
    elif changed_input == "mapper_document":
        mapper_b["remarks"] = "DIFFERENT-RAW-MAPPER"
    else:
        related_b["source_revision"] = "related-r4-2"

    current_preview = _preview_for(
        mapper_b,
        purchase_order=purchase_order_b,
        purchase_receipt=purchase_receipt_b,
        related_documents_read=related_b,
    )

    assert preview_a.status == "READY"
    assert current_preview.status == "READY"
    assert current_preview.source_digest != preview_a.source_digest
    with pytest.raises(ValueError, match="source"):
        bind_native_insert_request(
            basis,
            purchase_order=purchase_order_b,
            purchase_receipt=purchase_receipt_b,
            mapper_document=mapper_b,
            related_documents_read=related_b,
            preview=preview_a,
        )


def test_detached_ready_preview_must_match_current_bill_and_exact_ids() -> None:
    basis = _basis()
    purchase_order = _purchase_order()
    purchase_receipt = _purchase_receipt()
    mapper = _mapped_invoice()
    related = _related()
    preview = _preview_for(
        mapper,
        purchase_order=purchase_order,
        purchase_receipt=purchase_receipt,
        related_documents_read=related,
    )
    wrong_bill = replace(preview, bill_digest="0" * 64)
    wrong_ids = replace(
        preview,
        exact_ids=replace(preview.exact_ids, purchase_order="PUR-ORD-OTHER"),
    )

    for detached_preview in (wrong_bill, wrong_ids):
        with pytest.raises(ValueError):
            bind_native_insert_request(
                basis,
                purchase_order=purchase_order,
                purchase_receipt=purchase_receipt,
                mapper_document=mapper,
                related_documents_read=related,
                preview=detached_preview,
            )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("bill_no", None),
        ("bill_no", "OTHER-BILL"),
        ("bill_date", None),
        ("bill_date", "2026-09-10"),
    ),
)
def test_binding_does_not_overwrite_a_raw_mapper_bill_field_that_failed_preview(
    field: str, value: object
) -> None:
    mapper = _mapped_invoice()
    mapper[field] = value
    preview = _preview(mapper)

    assert preview.status == "HOLD"
    with pytest.raises(ValueError):
        bind_native_insert_request(
            _basis(),
            purchase_order=_purchase_order(),
            purchase_receipt=_purchase_receipt(),
            mapper_document=mapper,
            related_documents_read=_related(),
            preview=preview,
        )


def test_shared_validator_enforces_exact_mapped_draft_and_submitted_states() -> None:
    basis = _basis()
    purchase_order = _purchase_order()
    purchase_receipt = _purchase_receipt()
    mapped = _mapped_invoice()

    validate_native_purchase_invoice(
        basis,
        purchase_order=purchase_order,
        purchase_receipt=purchase_receipt,
        document=mapped,
        state="MAPPED",
    )
    bound = _bound_request().record()["body"]
    assert isinstance(bound, dict)
    validate_native_purchase_invoice(
        basis,
        purchase_order=purchase_order,
        purchase_receipt=purchase_receipt,
        document=bound,
        state="MAPPED",
        expected_bill_reference=basis.bill_reference,
        expected_bill_date=basis.bill_date,
    )

    draft = deepcopy(dict(bound))
    draft.update(name="ACC-PINV-0001", docstatus=0)
    validate_native_purchase_invoice(
        basis,
        purchase_order=purchase_order,
        purchase_receipt=purchase_receipt,
        document=draft,
        state="DRAFT",
        expected_name="ACC-PINV-0001",
    )
    submitted = deepcopy(draft)
    submitted["docstatus"] = 1
    validate_native_purchase_invoice(
        basis,
        purchase_order=purchase_order,
        purchase_receipt=purchase_receipt,
        document=submitted,
        state="SUBMITTED",
        expected_name="ACC-PINV-0001",
    )

    wrong_state = deepcopy(draft)
    wrong_state["docstatus"] = 1
    with pytest.raises(ValueError, match="DRAFT"):
        validate_native_purchase_invoice(
            basis,
            purchase_order=purchase_order,
            purchase_receipt=purchase_receipt,
            document=wrong_state,
            state="DRAFT",
            expected_name="ACC-PINV-0001",
        )
    wrong_name = deepcopy(submitted)
    wrong_name["name"] = "ACC-PINV-OTHER"
    with pytest.raises(ValueError, match="name"):
        validate_native_purchase_invoice(
            basis,
            purchase_order=purchase_order,
            purchase_receipt=purchase_receipt,
            document=wrong_name,
            state="SUBMITTED",
            expected_name="ACC-PINV-0001",
        )
    wrong_child = deepcopy(submitted)
    wrong_child["items"][0]["po_detail"] = "OTHER-ROW"
    with pytest.raises(ValueError, match="po_detail"):
        validate_native_purchase_invoice(
            basis,
            purchase_order=purchase_order,
            purchase_receipt=purchase_receipt,
            document=wrong_child,
            state="SUBMITTED",
            expected_name="ACC-PINV-0001",
        )


def test_request_rejects_an_unallowlisted_method_or_path() -> None:
    request = _bound_request()

    with pytest.raises(ValueError, match="method"):
        NativeInsertRequest(
            method="GET",
            path=request.path,
            body=request.body,
            bill_digest=request.bill_digest,
        )
    with pytest.raises(ValueError, match="path"):
        NativeInsertRequest(
            method="POST",
            path="/api/resource/Purchase%20Invoice/ACC-PINV-0001",
            body=request.body,
            bill_digest=request.bill_digest,
        )


def _captured_shape_draft() -> dict[str, object]:
    """Representative frozen shape of the saved native Purchase Invoice response."""

    request = _bound_request()
    request_body = request.record()["body"]
    assert isinstance(request_body, Mapping)
    document: dict[str, object] = deepcopy(dict(cast(Mapping[str, object], request_body)))
    document.update(
        {
            "name": "ACC-PINV-2026-00008",
            "docstatus": 0,
            "owner": "demo@example.test",
            "creation": "2026-09-09 22:00:00.000000",
            "modified": "2026-09-09 22:00:00.000000",
            "modified_by": "demo@example.test",
            "idx": 0,
            "status": "Draft",
            "posting_time": "18:50:44.851612",
            "set_posting_time": 0,
            "outstanding_amount": 50,
            "total_advance": 0,
            "advances": [],
            "payment_schedule": [],
            "__islocal": 0,
            "__unsaved": 0,
            "__onload": {"can_submit": 1},
        }
    )
    items = document["items"]
    assert isinstance(items, list)
    assert len(items) == 1
    assert isinstance(items[0], dict)
    items[0].update(
        {
            "name": "pi-item-native-00008",
            "doctype": "Purchase Invoice Item",
            "parent": "ACC-PINV-2026-00008",
            "parenttype": "Purchase Invoice",
            "parentfield": "items",
            "idx": 1,
            "docstatus": 0,
            "owner": "demo@example.test",
            "creation": "2026-09-09 22:00:00.000000",
            "modified": "2026-09-09 22:00:00.000000",
            "modified_by": "demo@example.test",
        }
    )
    return document


def test_native_acknowledgement_and_submit_records_preserve_the_full_response_shape() -> None:
    basis = _basis()
    request = _bound_request()
    draft = _captured_shape_draft()

    acknowledgement = validate_native_draft_acknowledgement(
        basis,
        purchase_order=_purchase_order(),
        purchase_receipt=_purchase_receipt(),
        insert_request=request,
        document=draft,
    )
    assert acknowledgement.draft_name == "ACC-PINV-2026-00008"
    assert acknowledgement.insert_body_digest == request.body_digest
    assert acknowledgement.document["__onload"] == {"can_submit": 1}
    acknowledgement_items = acknowledgement.document["items"]
    assert isinstance(acknowledgement_items, tuple)
    assert len(acknowledgement_items) == 1
    assert isinstance(acknowledgement_items[0], Mapping)
    assert acknowledgement_items[0]["parent"] == acknowledgement.draft_name

    recovered_acknowledgement = NativeDraftAcknowledgement.from_record(acknowledgement.record())
    assert recovered_acknowledgement.document_digest == acknowledgement.document_digest

    submit = NativeSubmitRequest.from_draft(acknowledgement)
    assert submit.method == "POST"
    assert submit.path == SUBMIT_PATH
    assert submit.body == {"doc": acknowledgement.document}
    assert submit.document_digest == acknowledgement.document_digest

    submitted_document = deepcopy(draft)
    submitted_document["docstatus"] = 1
    submitted_document["status"] = "Submitted"
    submitted = validate_native_submitted_readback(
        basis,
        purchase_order=_purchase_order(),
        purchase_receipt=_purchase_receipt(),
        draft=acknowledgement,
        document=submitted_document,
    )
    assert submitted.draft_name == acknowledgement.draft_name
    assert submitted.draft_document_digest == acknowledgement.document_digest
    assert submitted.document_digest


@pytest.mark.parametrize("mismatch", ("bill_digest", "bill_no"))
def test_draft_acknowledgement_revalidates_the_frozen_insert_request_against_its_basis(
    mismatch: str,
) -> None:
    basis = _basis()
    request = _bound_request()
    draft = _captured_shape_draft()
    if mismatch == "bill_digest":
        request = replace(request, bill_digest="0" * 64)
    else:
        body = dict(request.body)
        body["bill_no"] = "OTHER-BILL"
        request = NativeInsertRequest(
            method=request.method,
            path=request.path,
            body=body,
            bill_digest=request.bill_digest,
        )

    with pytest.raises(ValueError):
        validate_native_draft_acknowledgement(
            basis,
            purchase_order=_purchase_order(),
            purchase_receipt=_purchase_receipt(),
            insert_request=request,
            document=draft,
        )


def test_submitted_readback_revalidates_the_acknowledged_draft_against_its_basis() -> None:
    basis = _basis()
    request = _bound_request()
    invalid_draft = _captured_shape_draft()
    invalid_draft["bill_no"] = "OTHER-BILL"
    acknowledgement = NativeDraftAcknowledgement(
        insert_body_digest=request.body_digest,
        draft_name="ACC-PINV-2026-00008",
        document=invalid_draft,
    )
    submitted_document = _captured_shape_draft()
    submitted_document["docstatus"] = 1
    submitted_document["status"] = "Submitted"

    with pytest.raises(ValueError):
        validate_native_submitted_readback(
            basis,
            purchase_order=_purchase_order(),
            purchase_receipt=_purchase_receipt(),
            draft=acknowledgement,
            document=submitted_document,
        )


@pytest.mark.parametrize(
    "mutation",
    (
        lambda record: record.__setitem__("body_digest", "0" * 64),
        lambda record: record.__setitem__("path", "/api/resource/Purchase%20Invoice/OTHER"),
    ),
)
def test_persisted_insert_request_record_rejects_tampering(mutation: object) -> None:
    record = _bound_request().record()
    assert callable(mutation)
    mutation(record)
    with pytest.raises(ValueError):
        NativeInsertRequest.from_record(record)
