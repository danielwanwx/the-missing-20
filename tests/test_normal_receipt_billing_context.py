from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path

from the_missing_20.adapters.normal_receipt_billing_context import (
    NormalReceiptBillingContext,
    build_normal_receipt_billing_context,
)
from the_missing_20.adapters.normal_receipt_billing_journal import BillingIntentJournal
from the_missing_20.adapters.normal_receipt_billing_native_request import (
    NativeDraftAcknowledgement,
    NativeInsertRequest,
    bind_native_insert_request,
    validate_native_draft_acknowledgement,
)
from the_missing_20.adapters.normal_receipt_billing_preview import (
    SyntheticBillingBasis,
    validate_billing_preview,
)
from the_missing_20.adapters.normal_receipt_billing_source import NormalReceiptBillingSourceRead

NOW = datetime(2026, 9, 9, 22, 0, tzinfo=UTC)
MANAGER = "m20-demo-manager"


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


def _mapper() -> dict[str, object]:
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


def _related(documents: list[dict[str, object]]) -> dict[str, object]:
    basis = _basis()
    return {
        "status": "COMPLETE",
        "pagination": {"complete": True, "pages": 1},
        "pagination_complete": True,
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
        "documents": documents,
    }


def _source_read(
    documents: list[dict[str, object]],
    *,
    observed_at: str = "2026-09-09T21:10:00Z",
    snapshot_digest: str = "a" * 64,
) -> NormalReceiptBillingSourceRead:
    basis = _basis()
    purchase_order = _purchase_order()
    purchase_receipt = _purchase_receipt()
    mapped_invoice = _mapper()
    related_documents_read = _related(documents)
    related_documents_read["observed_at"] = observed_at
    preview = validate_billing_preview(
        basis,
        purchase_order=purchase_order,
        purchase_receipt=purchase_receipt,
        mapped_invoice=mapped_invoice,
        related_documents_read=related_documents_read,
    )
    return NormalReceiptBillingSourceRead(
        purchase_order=purchase_order,
        purchase_receipt=purchase_receipt,
        mapped_invoice=mapped_invoice,
        related_documents_read=related_documents_read,
        evidence_manifest={
            "read_only": True,
            "requests": [{"sequence": 1, "path": "/captured"}],
            "pages": [],
            "failures": [],
        },
        observed_at=observed_at,
        snapshot_digest=snapshot_digest,
        preview=preview,
    )


def _request() -> NativeInsertRequest:
    basis = _basis()
    source_read = _source_read([])
    purchase_order = source_read.purchase_order
    purchase_receipt = source_read.purchase_receipt
    mapped_invoice = source_read.mapped_invoice
    assert isinstance(purchase_order, Mapping)
    assert isinstance(purchase_receipt, Mapping)
    assert isinstance(mapped_invoice, Mapping)
    return bind_native_insert_request(
        basis,
        purchase_order=purchase_order,
        purchase_receipt=purchase_receipt,
        mapper_document=mapped_invoice,
        related_documents_read=source_read.related_documents_read,
        preview=source_read.preview,
    )


def _draft(request: NativeInsertRequest, *, name: str = "ACC-PINV-2026-00008") -> dict[str, object]:
    record = request.record()["body"]
    assert isinstance(record, dict)
    document = deepcopy(record)
    document["name"] = name
    document["docstatus"] = 0
    return document


def _acknowledged_draft(
    request: NativeInsertRequest,
) -> tuple[dict[str, object], NativeDraftAcknowledgement]:
    basis = _basis()
    draft = _draft(request)
    acknowledgement = validate_native_draft_acknowledgement(
        basis,
        purchase_order=_purchase_order(),
        purchase_receipt=_purchase_receipt(),
        insert_request=request,
        document=draft,
    )
    return draft, acknowledgement


def _unrelated_invoice(request: NativeInsertRequest, *, name: str) -> dict[str, object]:
    document = _draft(request, name=name)
    document["bill_no"] = "OTHER-SUPPLIER-BILL"
    items = document["items"]
    assert isinstance(items, list)
    assert isinstance(items[0], dict)
    items[0]["purchase_receipt"] = "MAT-PRE-OTHER"
    items[0]["pr_detail"] = "pr-other"
    return document


def _context_with_ack(
    source_read: NormalReceiptBillingSourceRead,
    request: NativeInsertRequest,
    acknowledgement: NativeDraftAcknowledgement,
    direct_document: dict[str, object],
) -> NormalReceiptBillingContext:
    return build_normal_receipt_billing_context(
        _basis(),
        source_read,
        stored_insert_request=request,
        acknowledgement=acknowledgement,
        direct_known_document=direct_document,
    )


def test_proven_own_draft_is_temporary_context_only_after_raw_source_reports_draft_exists() -> None:
    basis = _basis()
    request = _request()
    draft, acknowledgement = _acknowledged_draft(request)
    source_read = _source_read([draft])

    assert source_read.preview.status == "DRAFT_EXISTS"
    context = build_normal_receipt_billing_context(
        basis,
        source_read,
        stored_insert_request=request,
        acknowledgement=acknowledgement,
        direct_known_document=deepcopy(draft),
    )

    assert context.ready is True
    assert context.preview.status == "READY"
    assert context.hold_reason is None
    raw_audit = context.audit.record()
    audit_source = raw_audit["source_read"]
    audit_direct = raw_audit["direct_known_document"]
    assert isinstance(audit_source, dict)
    assert isinstance(audit_direct, dict)
    audit_related = audit_source["related_documents_read"]
    assert isinstance(audit_related, dict)
    audit_documents = audit_related["documents"]
    assert isinstance(audit_documents, list)
    assert isinstance(audit_documents[0], dict)
    assert audit_documents[0]["name"] == acknowledgement.draft_name
    assert audit_direct["name"] == acknowledgement.draft_name


def test_foreign_same_bill_is_not_excluded_with_the_proven_own_draft() -> None:
    basis = _basis()
    request = _request()
    draft, acknowledgement = _acknowledged_draft(request)
    foreign = _draft(request, name="ACC-PINV-2026-00009")
    foreign_item = foreign["items"]
    assert isinstance(foreign_item, list)
    assert isinstance(foreign_item[0], dict)
    foreign_item[0]["purchase_receipt"] = "MAT-PRE-OTHER"
    foreign_item[0]["pr_detail"] = "pr-other"
    source_read = _source_read([draft, foreign])

    assert source_read.preview.status == "HOLD"
    context = build_normal_receipt_billing_context(
        basis,
        source_read,
        stored_insert_request=request,
        acknowledgement=acknowledgement,
        direct_known_document=deepcopy(draft),
    )

    assert context.ready is False
    assert context.hold_reason == "COMPARISON_PREVIEW_NOT_READY"


def test_unfiltered_draft_cannot_be_excluded_before_a_journal_acknowledgement() -> None:
    request = _request()
    draft, _ = _acknowledged_draft(request)

    context = build_normal_receipt_billing_context(_basis(), _source_read([draft]))

    assert context.ready is False
    assert context.preview.status == "DRAFT_EXISTS"
    assert context.hold_reason == "UNFILTERED_PREVIEW_NOT_READY"


def test_duplicate_or_return_survives_the_temporary_own_draft_exclusion() -> None:
    request = _request()
    draft, acknowledgement = _acknowledged_draft(request)
    duplicate = deepcopy(draft)
    receipt_return: dict[str, object] = {
        "doctype": "Purchase Receipt",
        "name": "MAT-PRE-RETURN-00001",
        "return_against": _basis().purchase_receipt,
    }

    duplicate_context = _context_with_ack(
        _source_read([draft, duplicate]), request, acknowledgement, deepcopy(draft)
    )
    return_context = _context_with_ack(
        _source_read([draft, receipt_return]), request, acknowledgement, deepcopy(draft)
    )

    assert duplicate_context.ready is False
    assert duplicate_context.hold_reason == "ACKNOWLEDGED_DRAFT_NOT_EXACTLY_ONCE"
    assert return_context.ready is False
    assert return_context.hold_reason == "COMPARISON_PREVIEW_NOT_READY"


def test_incomplete_coverage_or_direct_get_shape_difference_holds() -> None:
    request = _request()
    draft, acknowledgement = _acknowledged_draft(request)
    incomplete_read = _source_read([draft])
    coverage = incomplete_read.related_documents_read["coverage"]
    assert isinstance(coverage, dict)
    coverage["receipt_returns"] = False
    changed_direct = deepcopy(draft)
    changed_direct["owner"] = "different-reader@example.test"

    incomplete = _context_with_ack(incomplete_read, request, acknowledgement, deepcopy(draft))
    mismatch = _context_with_ack(_source_read([draft]), request, acknowledgement, changed_direct)

    assert incomplete.ready is False
    assert incomplete.hold_reason == "RELATED_SOURCE_INCOMPLETE"
    assert mismatch.ready is False
    assert mismatch.hold_reason == "ACKNOWLEDGED_DRAFT_MISMATCH"


def test_wrong_stored_request_binding_cannot_use_an_acknowledged_draft() -> None:
    request = _request()
    draft, acknowledgement = _acknowledged_draft(request)
    wrong_body = request.record()["body"]
    assert isinstance(wrong_body, dict)
    wrong_body["remarks"] = "different-current-mapper-body"
    wrong_request = NativeInsertRequest(
        method=request.method,
        path=request.path,
        body=wrong_body,
        bill_digest=request.bill_digest,
    )

    context = _context_with_ack(
        _source_read([draft]), wrong_request, acknowledgement, deepcopy(draft)
    )

    assert context.ready is False
    assert context.hold_reason == "ACKNOWLEDGED_DRAFT_MISMATCH"


def test_commercial_fingerprint_excludes_audit_only_changes_and_document_order() -> None:
    request = _request()
    draft, acknowledgement = _acknowledged_draft(request)
    first_unrelated = _unrelated_invoice(request, name="ACC-PINV-2026-00009")
    second_unrelated = _unrelated_invoice(request, name="ACC-PINV-2026-00010")
    first = _context_with_ack(
        _source_read([draft, first_unrelated, second_unrelated]),
        request,
        acknowledgement,
        deepcopy(draft),
    )
    reordered = _source_read(
        [deepcopy(second_unrelated), deepcopy(draft), deepcopy(first_unrelated)],
        observed_at="2026-09-09T21:12:00Z",
        snapshot_digest="b" * 64,
    )
    related = reordered.related_documents_read
    manifest = reordered.evidence_manifest
    assert isinstance(related, dict)
    assert isinstance(manifest, dict)
    pagination = related["pagination"]
    assert isinstance(pagination, dict)
    pagination["pages"] = 3
    related["source_revision"] = "related-audit-only-revision"
    manifest["pages"] = [{"page": 1}, {"page": 2}, {"page": 3}]
    second = _context_with_ack(reordered, request, acknowledgement, deepcopy(draft))

    assert first.ready is True
    assert second.ready is True
    assert first.commercial_source is not None
    assert second.commercial_source is not None
    assert (
        first.commercial_source.commercial_record() == second.commercial_source.commercial_record()
    )
    assert first.commercial_source.record() != second.commercial_source.record()
    assert first.audit.record() != second.audit.record()


def test_business_and_parent_revision_drift_change_the_commercial_fingerprint() -> None:
    request = _request()
    draft, acknowledgement = _acknowledged_draft(request)
    unrelated = _unrelated_invoice(request, name="ACC-PINV-2026-00009")
    baseline = _context_with_ack(
        _source_read([draft, unrelated]), request, acknowledgement, deepcopy(draft)
    )
    changed_document = _unrelated_invoice(request, name="ACC-PINV-2026-00009")
    changed_document["docstatus"] = 1
    document_drift = _context_with_ack(
        _source_read([deepcopy(draft), changed_document]),
        request,
        acknowledgement,
        deepcopy(draft),
    )
    parent_drift_read = _source_read([deepcopy(draft), deepcopy(unrelated)])
    purchase_order = parent_drift_read.purchase_order
    purchase_receipt = parent_drift_read.purchase_receipt
    assert isinstance(purchase_order, dict)
    assert isinstance(purchase_receipt, dict)
    purchase_order["modified"] = "2026-09-09T22:00:00Z"
    purchase_receipt["modified"] = "2026-09-09T22:01:00Z"
    parent_drift = _context_with_ack(parent_drift_read, request, acknowledgement, deepcopy(draft))

    assert baseline.ready is True
    assert document_drift.ready is True
    assert parent_drift.ready is True
    assert baseline.commercial_source is not None
    assert document_drift.commercial_source is not None
    assert parent_drift.commercial_source is not None
    assert (
        baseline.commercial_source.commercial_record()
        != document_drift.commercial_source.commercial_record()
    )
    assert (
        baseline.commercial_source.commercial_record()
        != parent_drift.commercial_source.commercial_record()
    )


def test_context_and_audit_do_not_share_mutable_source_material() -> None:
    request = _request()
    draft, acknowledgement = _acknowledged_draft(request)
    source_read = _source_read([draft])
    context = _context_with_ack(source_read, request, acknowledgement, deepcopy(draft))
    assert context.ready is True
    assert context.commercial_source is not None
    commercial_before = context.commercial_source.record()
    audit_before = context.audit.record()
    purchase_order = source_read.purchase_order
    related = source_read.related_documents_read
    assert isinstance(purchase_order, dict)
    assert isinstance(related, dict)
    purchase_order["modified"] = "MUTATED-AFTER-CONTEXT"
    documents = related["documents"]
    assert isinstance(documents, list)
    assert isinstance(documents[0], dict)
    documents[0]["bill_no"] = "MUTATED-AFTER-CONTEXT"

    assert context.commercial_source.record() == commercial_before
    assert context.audit.record() == audit_before


def test_context_stitches_to_existing_journal_without_sticky_audit_refresh(tmp_path: Path) -> None:
    basis = _basis()
    initial = build_normal_receipt_billing_context(basis, _source_read([]))
    assert initial.ready is True
    assert initial.commercial_source is not None
    assert initial.source_insert_request is not None
    journal = BillingIntentJournal(tmp_path / "normal-billing.sqlite3")
    prepared = journal.prepare(
        basis,
        initial.preview,
        initial.commercial_source,
        insert_request=initial.source_insert_request,
    )
    assert prepared.accepted is True
    approval = journal.approve(
        prepared.intent_id,
        case_id=basis.case_id,
        manager_id=MANAGER,
        expires_at=NOW + timedelta(minutes=10),
        now=NOW,
    )
    assert approval.granted is True
    claim = journal.claim_insert(
        prepared.intent_id,
        case_id=basis.case_id,
        manager_id=MANAGER,
        approval_token=approval.token or "",
        worker_id="context-seam",
        now=NOW,
    )
    assert claim.granted is True
    bound_request = journal.bound_insert_request(prepared.intent_id)
    assert bound_request is not None
    draft, acknowledgement = _acknowledged_draft(bound_request)
    assert (
        journal.admit_insert_acknowledgement(prepared.intent_id, acknowledgement).admitted is True
    )
    stored_acknowledgement = journal.acknowledged_draft(prepared.intent_id)
    assert stored_acknowledgement is not None

    own_draft = _context_with_ack(
        _source_read([draft]),
        bound_request,
        stored_acknowledgement,
        deepcopy(draft),
    )
    assert own_draft.ready is True
    assert own_draft.commercial_source is not None
    stable = journal.refresh_source(prepared.intent_id, own_draft.commercial_source, now=NOW)
    assert stable.commercial_changed is False
    assert stable.snapshot.source_changed is False

    audit_only_read = _source_read(
        [deepcopy(draft)],
        observed_at="2026-09-09T22:01:00Z",
        snapshot_digest="b" * 64,
    )
    audit_related = audit_only_read.related_documents_read
    audit_manifest = audit_only_read.evidence_manifest
    assert isinstance(audit_related, dict)
    assert isinstance(audit_manifest, dict)
    audit_related["source_revision"] = "audit-only"
    audit_manifest["pages"] = [{"page": 1}, {"page": 2}]
    audit_only = _context_with_ack(
        audit_only_read,
        bound_request,
        stored_acknowledgement,
        deepcopy(draft),
    )
    assert audit_only.ready is True
    assert audit_only.commercial_source is not None
    stable_again = journal.refresh_source(prepared.intent_id, audit_only.commercial_source, now=NOW)
    assert stable_again.commercial_changed is False
    assert stable_again.snapshot.source_changed is False

    changed_parent_read = _source_read([deepcopy(draft)])
    changed_purchase_order = changed_parent_read.purchase_order
    assert isinstance(changed_purchase_order, dict)
    changed_purchase_order["modified"] = "2026-09-09T22:02:00Z"
    changed_parent = _context_with_ack(
        changed_parent_read,
        bound_request,
        stored_acknowledgement,
        deepcopy(draft),
    )
    assert changed_parent.ready is True
    assert changed_parent.commercial_source is not None
    changed = journal.refresh_source(prepared.intent_id, changed_parent.commercial_source, now=NOW)
    assert changed.commercial_changed is True
    assert changed.snapshot.source_changed is True
