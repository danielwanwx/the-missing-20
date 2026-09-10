"""Read-only commercial preview for one normal receiving bill.

The preview consumes already-read ERP documents and a disclosed synthetic
supplier-bill basis.  It has no transport, journal, approval, or write path.
The pilot is deliberately one accepted ``Box`` at USD 50 with no tax or
discount; evidence outside that envelope is held for a later design.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from types import MappingProxyType
from typing import Any, Literal, cast

EXPECTED_QUANTITY = Decimal("1")
EXPECTED_ORDERED_QUANTITY = Decimal("40")
EXPECTED_UOM = "Box"
EXPECTED_CURRENCY = "USD"
EXPECTED_RATE = Decimal("50")

PreviewStatus = Literal["READY", "ALREADY_SUBMITTED", "DRAFT_EXISTS", "ALREADY_BILLED", "HOLD"]


def _decimal(value: object, label: str) -> Decimal:
    if value is None or isinstance(value, bool):
        raise ValueError(f"{label} must be a finite decimal")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{label} must be a finite decimal") from None
    if not result.is_finite():
        raise ValueError(f"{label} must be a finite decimal")
    return result


def _number_matches(actual: object, expected: Decimal) -> bool:
    try:
        return _decimal(actual, "numeric field") == expected
    except ValueError:
        return False


def _jsonable(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {
            str(key): _jsonable(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, float):
        if math.isfinite(value):
            return value
        return {"__nonfinite__": str(value).lower()}
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    return str(value)


def _digest(value: object) -> str:
    encoded = json.dumps(_jsonable(value), sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} is required")
    return value.strip()


def _value(document: Mapping[str, Any], *names: str) -> object:
    for name in names:
        if name in document and document[name] is not None:
            return document[name]
    return None


def _require_equal(
    document: Mapping[str, Any], field_name: str, expected: object, label: str
) -> None:
    if field_name not in document or document[field_name] is None:
        raise ValueError(f"{label} {field_name} is missing")
    if document[field_name] != expected:
        raise ValueError(f"{label} {field_name} does not match the bill basis")


def _require_number(
    document: Mapping[str, Any], field_name: str, expected: Decimal, label: str
) -> Decimal:
    if field_name not in document:
        raise ValueError(f"{label} {field_name} is missing")
    try:
        actual = _decimal(document[field_name], f"{label} {field_name}")
    except ValueError as error:
        raise ValueError(str(error)) from None
    if actual != expected:
        raise ValueError(f"{label} {field_name} does not match the bill basis")
    return actual


def _require_zero(document: Mapping[str, Any], field_name: str, label: str) -> None:
    _require_number(document, field_name, Decimal("0"), label)


def _require_empty_list(document: Mapping[str, Any], field_name: str, label: str) -> None:
    if field_name not in document or not isinstance(document[field_name], list):
        raise ValueError(f"{label} {field_name} must be an explicit empty list")
    if document[field_name]:
        raise ValueError(f"{label} {field_name} must be an explicit empty list")


def _optional_equal(
    document: Mapping[str, Any], field_name: str, expected: object, label: str
) -> None:
    if (
        field_name in document
        and document[field_name] is not None
        and document[field_name] != expected
    ):
        raise ValueError(f"{label} {field_name} does not match the bill basis")


def _optional_zero(document: Mapping[str, Any], field_name: str, label: str) -> None:
    if field_name in document:
        _require_zero(document, field_name, label)


def _rows(document: Mapping[str, Any], label: str) -> list[Mapping[str, Any]]:
    rows = document.get("items")
    if not isinstance(rows, (list, tuple)) or any(not isinstance(row, Mapping) for row in rows):
        raise ValueError(f"{label} items are missing or malformed")
    return [cast(Mapping[str, Any], row) for row in rows]


def _exact_row(document: Mapping[str, Any], identifier: str, label: str) -> Mapping[str, Any]:
    rows = _rows(document, label)
    matches = [row for row in rows if row.get("name") == identifier]
    if len(matches) != 1:
        raise ValueError(f"{label} exact source row is missing or ambiguous")
    return matches[0]


def _docstatus(document: Mapping[str, Any], label: str) -> int:
    try:
        value = _decimal(document.get("docstatus"), f"{label} docstatus")
    except ValueError:
        return -1
    return int(value) if value in {Decimal("0"), Decimal("1"), Decimal("2")} else -1


def _truthy(value: object) -> bool:
    if value is None or value == "":
        return False
    try:
        return _decimal(value, "flag") != Decimal("0")
    except ValueError:
        return bool(value)


@dataclass(frozen=True, slots=True)
class SyntheticBillingBasis:
    """The complete, disclosed synthetic bill input for the narrow pilot."""

    case_id: str
    company: str
    supplier: str
    bill_reference: str
    bill_date: str
    purchase_order: str
    purchase_order_item: str
    purchase_receipt: str
    purchase_receipt_item: str
    item_code: str
    source_revision: str
    posting_date: str
    credit_to: str
    expense_account: str
    ordered_quantity: Decimal = EXPECTED_ORDERED_QUANTITY
    quantity: Decimal = EXPECTED_QUANTITY
    uom: str = EXPECTED_UOM
    stock_uom: str = EXPECTED_UOM
    conversion_factor: Decimal = Decimal("1")
    net_rate: Decimal = EXPECTED_RATE
    currency: str = EXPECTED_CURRENCY
    tax_amount: Decimal = Decimal("0")
    discount_amount: Decimal = Decimal("0")
    gross_amount: Decimal = Decimal("50")
    synthetic_only: bool = True

    def __post_init__(self) -> None:
        for name in (
            "case_id",
            "company",
            "supplier",
            "bill_reference",
            "bill_date",
            "purchase_order",
            "purchase_order_item",
            "purchase_receipt",
            "purchase_receipt_item",
            "item_code",
            "source_revision",
            "posting_date",
            "credit_to",
            "expense_account",
            "uom",
            "stock_uom",
            "currency",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if self.synthetic_only is not True:
            raise ValueError("preview accepts disclosed synthetic bills only")
        ordered = _decimal(self.ordered_quantity, "ordered quantity")
        quantity = _decimal(self.quantity, "bill quantity")
        conversion = _decimal(self.conversion_factor, "conversion factor")
        rate = _decimal(self.net_rate, "net rate")
        tax = _decimal(self.tax_amount, "tax amount")
        discount = _decimal(self.discount_amount, "discount amount")
        gross = _decimal(self.gross_amount, "gross amount")
        if ordered != EXPECTED_ORDERED_QUANTITY:
            raise ValueError("pilot source order must contain exactly 40 Box")
        if quantity != EXPECTED_QUANTITY or self.uom != EXPECTED_UOM:
            raise ValueError("pilot bill must contain exactly one Box")
        if conversion <= 0:
            raise ValueError("conversion factor must be positive")
        if rate != EXPECTED_RATE or self.currency != EXPECTED_CURRENCY:
            raise ValueError("pilot bill must be USD 50 net")
        if tax != 0 or discount != 0 or gross != quantity * rate:
            raise ValueError("pilot preview only supports USD 50 with no tax or discount")
        if tax < 0 or discount < 0:
            raise ValueError("tax and discount amounts must be non-negative")
        object.__setattr__(self, "ordered_quantity", ordered)
        object.__setattr__(self, "quantity", quantity)
        object.__setattr__(self, "conversion_factor", conversion)
        object.__setattr__(self, "net_rate", rate)
        object.__setattr__(self, "tax_amount", tax)
        object.__setattr__(self, "discount_amount", discount)
        object.__setattr__(self, "gross_amount", gross)

    @property
    def net_amount(self) -> Decimal:
        return self.quantity * self.net_rate

    @property
    def bill_digest(self) -> str:
        return _digest(self.record())

    @property
    def exact_line_key(self) -> str:
        return "|".join(
            (self.case_id, self.purchase_receipt, self.purchase_receipt_item, self.item_code)
        )

    def record(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "company": self.company,
            "supplier": self.supplier,
            "bill_reference": self.bill_reference,
            "bill_date": self.bill_date,
            "purchase_order": self.purchase_order,
            "purchase_order_item": self.purchase_order_item,
            "purchase_receipt": self.purchase_receipt,
            "purchase_receipt_item": self.purchase_receipt_item,
            "item_code": self.item_code,
            "ordered_quantity": str(self.ordered_quantity),
            "quantity": str(self.quantity),
            "uom": self.uom,
            "stock_uom": self.stock_uom,
            "conversion_factor": str(self.conversion_factor),
            "net_rate": str(self.net_rate),
            "net_amount": str(self.net_amount),
            "currency": self.currency,
            "tax_amount": str(self.tax_amount),
            "discount_amount": str(self.discount_amount),
            "gross_amount": str(self.gross_amount),
            "source_revision": self.source_revision,
            "posting_date": self.posting_date,
            "credit_to": self.credit_to,
            "expense_account": self.expense_account,
            "synthetic_only": self.synthetic_only,
        }


BillingBasis = SyntheticBillingBasis


@dataclass(frozen=True, slots=True)
class ExactIds:
    case_id: str
    purchase_order: str
    purchase_order_item: str
    purchase_receipt: str
    purchase_receipt_item: str
    existing_invoice_names: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BillingPreview:
    source_digest: str
    bill_digest: str
    exact_ids: ExactIds
    quantity: Decimal
    uom: str
    stock_uom: str
    conversion_factor: Decimal
    net_amount: Decimal
    gross_amount: Decimal
    required_inputs: tuple[str, ...]
    status: PreviewStatus
    reasons: tuple[str, ...]
    read_only: bool = True
    write_allowed: bool = False
    source: Mapping[str, object] = field(default_factory=dict)

    @property
    def exactids(self) -> ExactIds:
        """Compatibility spelling for the compact handoff contract."""

        return self.exact_ids

    def record(self) -> dict[str, object]:
        return {
            "source_digest": self.source_digest,
            "bill_digest": self.bill_digest,
            "exact_ids": {
                "case_id": self.exact_ids.case_id,
                "purchase_order": self.exact_ids.purchase_order,
                "purchase_order_item": self.exact_ids.purchase_order_item,
                "purchase_receipt": self.exact_ids.purchase_receipt,
                "purchase_receipt_item": self.exact_ids.purchase_receipt_item,
                "existing_invoice_names": list(self.exact_ids.existing_invoice_names),
            },
            "quantity": str(self.quantity),
            "uom": self.uom,
            "stock_uom": self.stock_uom,
            "conversion_factor": str(self.conversion_factor),
            "net_amount": str(self.net_amount),
            "gross_amount": str(self.gross_amount),
            "required_inputs": list(self.required_inputs),
            "status": self.status,
            "reasons": list(self.reasons),
            "read_only": self.read_only,
            "write_allowed": self.write_allowed,
            "source": _jsonable(self.source),
        }


def _public_source(metadata: Mapping[str, object] | None) -> Mapping[str, object]:
    payload: dict[str, object] = {"read_only": True}
    if metadata is not None:
        scope = metadata.get("scope")
        if isinstance(scope, Mapping):
            payload["lookup_scope"] = MappingProxyType(dict(scope))
        for name in ("source_revision", "observed_at"):
            if name in metadata:
                payload[name] = metadata[name]
    return MappingProxyType(payload)


def _hold(
    basis: SyntheticBillingBasis,
    source_digest: str,
    exact_ids: ExactIds,
    reasons: Sequence[str],
    *,
    status: PreviewStatus = "HOLD",
    source: Mapping[str, object] | None = None,
) -> BillingPreview:
    reason_tuple = tuple(reasons)
    return BillingPreview(
        source_digest=source_digest,
        bill_digest=basis.bill_digest,
        exact_ids=exact_ids,
        quantity=basis.quantity,
        uom=basis.uom,
        stock_uom=basis.stock_uom,
        conversion_factor=basis.conversion_factor,
        net_amount=basis.net_amount,
        gross_amount=basis.gross_amount,
        required_inputs=reason_tuple,
        status=status,
        reasons=reason_tuple,
        source=_public_source(source),
    )


def _related_documents(
    read: Mapping[str, Any], basis: SyntheticBillingBasis
) -> tuple[list[Mapping[str, Any]], Mapping[str, object]]:
    if not isinstance(read, Mapping) or read.get("status") != "COMPLETE":
        raise ValueError("related document read must be COMPLETE")
    pagination = read.get("pagination")
    if not isinstance(pagination, Mapping) or "complete" not in pagination:
        raise ValueError("related document read must declare pagination completeness")
    complete = pagination["complete"]
    if complete is not True:
        raise ValueError("related document read must declare complete pagination")
    if "pagination_complete" in read and read["pagination_complete"] is not complete:
        raise ValueError("related document read has contradictory pagination completeness")
    documents = read.get("documents")
    if not isinstance(documents, (list, tuple)) or any(
        not isinstance(document, Mapping) for document in documents
    ):
        raise ValueError("related document read has no complete document list")
    scope = read.get("scope")
    if not isinstance(scope, Mapping):
        raise ValueError("related document lookup scope is missing")
    coverage = read.get("coverage")
    required_coverage = (
        "receipt_line_invoices",
        "receipt_returns",
        "bill_reference_collisions",
    )
    if not isinstance(coverage, Mapping) or any(
        coverage.get(field_name) is not True for field_name in required_coverage
    ):
        raise ValueError("related document lookup coverage is incomplete")
    expected_scope = {
        "company": basis.company,
        "supplier": basis.supplier,
        "purchase_order": basis.purchase_order,
        "purchase_order_item": basis.purchase_order_item,
        "purchase_receipt": basis.purchase_receipt,
        "purchase_receipt_item": basis.purchase_receipt_item,
    }
    for field_name, expected in expected_scope.items():
        if scope.get(field_name) != expected:
            raise ValueError(f"related document lookup scope {field_name} is not exact")
    source_revision = _text(read.get("source_revision"), "related document source_revision")
    observed_at = _text(read.get("observed_at"), "related document observed_at")
    metadata = {
        "status": "COMPLETE",
        "pagination_complete": True,
        "scope": dict(scope),
        "source_revision": source_revision,
        "observed_at": observed_at,
    }
    return [cast(Mapping[str, Any], document) for document in documents], metadata


def _validate_document_header(
    basis: SyntheticBillingBasis, document: Mapping[str, Any], label: str, expected_doctype: str
) -> None:
    _require_equal(document, "doctype", expected_doctype, label)
    _require_number(document, "docstatus", Decimal("1"), label)
    _require_equal(document, "company", basis.company, label)
    _require_equal(document, "supplier", basis.supplier, label)
    _require_equal(document, "currency", basis.currency, label)
    _text(document.get("name"), f"{label} name")
    _text(document.get("modified"), f"{label} modified")
    _require_zero(document, "discount_amount", label)
    _require_zero(document, "rounding_adjustment", label)
    _require_empty_list(document, "taxes", label)
    for field_name in (
        "additional_discount_percentage",
        "taxes_and_charges_added",
        "taxes_and_charges_deducted",
        "total_taxes_and_charges",
    ):
        _optional_zero(document, field_name, label)


def _validate_sources(
    basis: SyntheticBillingBasis,
    purchase_order: Mapping[str, Any],
    purchase_receipt: Mapping[str, Any],
) -> Mapping[str, Any]:
    if purchase_order.get("name") != basis.purchase_order:
        raise ValueError("Purchase Order identity does not match the bill basis")
    if purchase_receipt.get("name") != basis.purchase_receipt:
        raise ValueError("Purchase Receipt identity does not match the bill basis")
    _validate_document_header(basis, purchase_order, "Purchase Order", "Purchase Order")
    _validate_document_header(basis, purchase_receipt, "Purchase Receipt", "Purchase Receipt")
    _require_zero(purchase_receipt, "is_return", "Purchase Receipt")
    _optional_equal(purchase_receipt, "purchase_order", basis.purchase_order, "Purchase Receipt")
    _optional_equal(purchase_receipt, "po_no", basis.purchase_order, "Purchase Receipt")

    po_row = _exact_row(purchase_order, basis.purchase_order_item, "Purchase Order")
    pr_row = _exact_row(purchase_receipt, basis.purchase_receipt_item, "Purchase Receipt")
    for row, label in ((po_row, "Purchase Order row"), (pr_row, "Purchase Receipt row")):
        _require_equal(row, "item_code", basis.item_code, label)
        _require_equal(row, "uom", basis.uom, label)
        _require_equal(row, "stock_uom", basis.stock_uom, label)
        _require_number(row, "conversion_factor", basis.conversion_factor, label)
        _require_number(row, "rate", basis.net_rate, label)
        _require_number(row, "net_rate", basis.net_rate, label)
        if "is_return" in row:
            _require_zero(row, "is_return", label)
        _require_zero(row, "returned_qty", label)

    po_amount = basis.ordered_quantity * basis.net_rate
    _require_number(po_row, "qty", basis.ordered_quantity, "Purchase Order row")
    _require_number(
        po_row,
        "stock_qty",
        basis.ordered_quantity * basis.conversion_factor,
        "Purchase Order row",
    )
    _require_number(po_row, "received_qty", basis.quantity, "Purchase Order row")
    _require_number(po_row, "amount", po_amount, "Purchase Order row")
    _require_number(po_row, "net_amount", po_amount, "Purchase Order row")

    _require_equal(pr_row, "purchase_order", basis.purchase_order, "Purchase Receipt row")
    _require_equal(pr_row, "purchase_order_item", basis.purchase_order_item, "Purchase Receipt row")
    _require_number(pr_row, "qty", basis.quantity, "Purchase Receipt row")
    _require_number(pr_row, "received_qty", basis.quantity, "Purchase Receipt row")
    _require_number(
        pr_row,
        "stock_qty",
        basis.quantity * basis.conversion_factor,
        "Purchase Receipt row",
    )
    _require_number(
        pr_row,
        "received_stock_qty",
        basis.quantity * basis.conversion_factor,
        "Purchase Receipt row",
    )
    _require_number(pr_row, "amount", basis.net_amount, "Purchase Receipt row")
    _require_number(pr_row, "net_amount", basis.net_amount, "Purchase Receipt row")
    _require_zero(pr_row, "rejected_qty", "Purchase Receipt row")
    return pr_row


def _validate_mapper(
    basis: SyntheticBillingBasis,
    invoice: Mapping[str, Any],
    receipt_row: Mapping[str, Any],
    *,
    allow_existing: bool = False,
    validate_bill_reference: bool = True,
) -> None:
    _require_equal(invoice, "doctype", "Purchase Invoice", "mapped Purchase Invoice")
    if not allow_existing and (
        invoice.get("name") not in (None, "") or _docstatus(invoice, "mapped invoice") != 0
    ):
        raise ValueError("mapped invoice must be an uninserted draft without a name")
    _require_zero(invoice, "update_stock", "mapped Purchase Invoice")
    for field_name in (
        "is_return",
        "is_paid",
        "paid_amount",
        "write_off_amount",
        "rounding_adjustment",
    ):
        _require_zero(invoice, field_name, "mapped Purchase Invoice")
    if "return_against" in invoice and invoice["return_against"] not in (None, ""):
        raise ValueError("mapped Purchase Invoice contains a return reference")
    _require_empty_list(invoice, "taxes", "mapped Purchase Invoice")
    _require_zero(invoice, "discount_amount", "mapped Purchase Invoice")
    _require_equal(invoice, "company", basis.company, "mapped Purchase Invoice")
    _require_equal(invoice, "supplier", basis.supplier, "mapped Purchase Invoice")
    _require_equal(invoice, "currency", basis.currency, "mapped Purchase Invoice")
    _require_equal(invoice, "posting_date", basis.posting_date, "mapped Purchase Invoice")
    if validate_bill_reference and ("bill_no" in invoice or "supplier_invoice_no" in invoice):
        bill_reference = _value(invoice, "bill_no", "supplier_invoice_no")
        if bill_reference != basis.bill_reference:
            raise ValueError(
                "mapped Purchase Invoice bill reference does not match the synthetic bill"
            )
    if "bill_date" in invoice:
        _require_equal(invoice, "bill_date", basis.bill_date, "mapped Purchase Invoice")
    _require_equal(invoice, "credit_to", basis.credit_to, "mapped Purchase Invoice")

    items = _rows(invoice, "mapped Purchase Invoice")
    if len(items) != 1:
        raise ValueError("native mapper must retain exactly one receipt line")
    row = items[0]
    for field_name, expected_text in (
        ("item_code", basis.item_code),
        ("uom", basis.uom),
        ("stock_uom", basis.stock_uom),
        ("purchase_order", basis.purchase_order),
        ("po_detail", basis.purchase_order_item),
        ("purchase_receipt", basis.purchase_receipt),
        ("pr_detail", basis.purchase_receipt_item),
        ("expense_account", basis.expense_account),
    ):
        _require_equal(row, field_name, expected_text, "mapped Purchase Invoice row")
    receipt_stock_qty = _require_number(
        receipt_row, "stock_qty", basis.quantity * basis.conversion_factor, "Purchase Receipt row"
    )
    numeric_fields: tuple[tuple[str, Decimal], ...] = (
        ("qty", basis.quantity),
        ("conversion_factor", basis.conversion_factor),
        ("rate", basis.net_rate),
        ("net_rate", basis.net_rate),
        ("amount", basis.net_amount),
        ("net_amount", basis.net_amount),
        ("stock_qty", receipt_stock_qty),
    )
    for field_name, numeric_expected in numeric_fields:
        _require_number(row, field_name, numeric_expected, "mapped Purchase Invoice row")
    for field_name in ("received_qty", "rejected_qty"):
        if field_name in row:
            if field_name == "received_qty":
                _require_number(row, field_name, basis.quantity, "mapped Purchase Invoice row")
            else:
                _require_zero(row, field_name, "mapped Purchase Invoice row")
    _require_number(invoice, "grand_total", basis.gross_amount, "mapped Purchase Invoice")
    for field_name in ("net_total", "total", "rounded_total"):
        if field_name in invoice:
            _require_number(invoice, field_name, basis.gross_amount, "mapped Purchase Invoice")
    for field_name in (
        "additional_discount_percentage",
        "taxes_and_charges_added",
        "taxes_and_charges_deducted",
        "total_taxes_and_charges",
    ):
        _optional_zero(invoice, field_name, "mapped Purchase Invoice")


def _is_native_receipt_return(basis: SyntheticBillingBasis, document: Mapping[str, Any]) -> bool:
    if document.get("doctype") != "Purchase Receipt":
        return False
    if document.get("return_against") == basis.purchase_receipt:
        return True
    if not _truthy(document.get("is_return")):
        return False
    try:
        items = _rows(document, "related Purchase Receipt")
    except ValueError:
        return False
    return any(
        _value(row, "purchase_order", "po_no") == basis.purchase_order
        and _value(row, "purchase_order_item", "po_detail") == basis.purchase_order_item
        for row in items
    )


def _linked_rows(
    basis: SyntheticBillingBasis, document: Mapping[str, Any]
) -> tuple[list[Mapping[str, Any]], list[Mapping[str, Any]]]:
    items = _rows(document, "related invoice")
    linked = [
        row
        for row in items
        if _value(row, "purchase_receipt", "receipt") == basis.purchase_receipt
        and _value(row, "pr_detail", "purchase_receipt_item") == basis.purchase_receipt_item
    ]
    return items, linked


def _related_effects(
    basis: SyntheticBillingBasis,
    receipt_row: Mapping[str, Any],
    documents: Sequence[Mapping[str, Any]],
) -> tuple[PreviewStatus | None, tuple[str, ...], tuple[str, ...]]:
    exact: list[Mapping[str, Any]] = []
    names: list[str] = []
    reasons: list[str] = []
    billed = Decimal("0")
    submitted_count = 0
    for document in documents:
        if _is_native_receipt_return(basis, document):
            reasons.append("related Purchase Receipt return affects the receipt line")
            continue
        try:
            items, linked = _linked_rows(basis, document)
        except ValueError as error:
            reasons.append(str(error))
            continue
        same_reference = _value(document, "bill_no", "supplier_invoice_no") == basis.bill_reference
        if same_reference:
            exact.append(document)
        if not linked:
            if same_reference:
                reasons.append("same supplier bill reference is linked to another receipt row")
            continue
        name = document.get("name")
        if not isinstance(name, str) or not name.strip():
            reasons.append("related linked invoice has no stable name")
        else:
            names.append(name)
        if len(items) != 1:
            reasons.append("existing linked invoice is mixed-line")
            continue
        row = linked[0]
        if (
            _value(row, "purchase_order", "po_no") != basis.purchase_order
            or _value(row, "po_detail", "purchase_order_item") != basis.purchase_order_item
        ):
            reasons.append("existing linked invoice does not retain the exact PO row")
        status = _docstatus(document, "related invoice")
        if status not in {0, 1, 2}:
            reasons.append("related invoice has an unknown document status")
            continue
        if "is_return" not in document:
            reasons.append("related invoice return flag is unknown")
        elif _truthy(document["is_return"]) or document["is_return"] is None:
            reasons.append("receipt line has a return or credit")
        if document.get("return_against") not in (None, ""):
            reasons.append("receipt line has a return or credit")
        if status == 2:
            reasons.append("existing linked invoice is cancelled")
            continue
        try:
            _validate_mapper(
                basis,
                document,
                receipt_row,
                allow_existing=True,
                validate_bill_reference=same_reference,
            )
        except ValueError as error:
            reasons.append(f"existing invoice commercial fields changed: {error}")
        if status == 0:
            if not same_reference:
                reasons.append("linked draft has a different supplier bill reference")
        elif status == 1:
            submitted_count += 1
            raw_quantity = _value(row, "qty", "quantity")
            try:
                quantity = _decimal(raw_quantity, "existing billed quantity")
            except ValueError as error:
                reasons.append(str(error))
                continue
            if quantity <= 0 or quantity != basis.quantity:
                reasons.append("existing submitted invoice has partial or invalid billed quantity")
                continue
            billed += quantity
    if len(exact) > 1:
        reasons.append("multiple invoices share the supplier bill reference")
    if submitted_count > 1:
        reasons.append("multiple submitted invoices cover the receipt line")
    if exact:
        if billed and any(_docstatus(document, "matching invoice") != 1 for document in exact):
            reasons.append("submitted and draft invoices conflict for the receipt line")
        if reasons:
            return "HOLD", tuple(reasons), tuple(names)
        status = _docstatus(exact[0], "matching invoice")
        return ("ALREADY_SUBMITTED" if status == 1 else "DRAFT_EXISTS"), (), tuple(names)
    if reasons:
        return "HOLD", tuple(reasons), tuple(names)
    if billed >= basis.quantity:
        return "ALREADY_BILLED", ("receipt line has already been billed",), tuple(names)
    return None, (), tuple(names)


def validate_billing_preview(
    basis: SyntheticBillingBasis,
    *,
    purchase_order: Mapping[str, Any],
    purchase_receipt: Mapping[str, Any],
    mapped_invoice: Mapping[str, Any],
    related_documents_read: Mapping[str, Any],
) -> BillingPreview:
    """Validate a read-only normal-billing proposal from already-read inputs."""

    exact_ids = ExactIds(
        basis.case_id,
        basis.purchase_order,
        basis.purchase_order_item,
        basis.purchase_receipt,
        basis.purchase_receipt_item,
    )
    metadata: Mapping[str, object] | None = None
    try:
        related, metadata = _related_documents(related_documents_read, basis)
        receipt_row = _validate_sources(basis, purchase_order, purchase_receipt)
        _validate_mapper(basis, mapped_invoice, receipt_row)
        effect_status, effect_reasons, names = _related_effects(basis, receipt_row, related)
    except ValueError as error:
        source_digest = _digest(
            {
                "basis": basis.record(),
                "purchase_order": purchase_order,
                "purchase_receipt": purchase_receipt,
                "mapped_invoice": mapped_invoice,
                "related_documents_read": related_documents_read,
                "error": str(error),
            }
        )
        return _hold(
            basis,
            source_digest,
            exact_ids,
            (str(error),),
            source=metadata,
        )
    exact_ids = ExactIds(
        basis.case_id,
        basis.purchase_order,
        basis.purchase_order_item,
        basis.purchase_receipt,
        basis.purchase_receipt_item,
        names,
    )
    source = {
        "basis": basis.record(),
        "purchase_order": purchase_order,
        "purchase_receipt": purchase_receipt,
        "mapped_invoice": mapped_invoice,
        "related_documents_read": related_documents_read,
    }
    source_digest = _digest(source)
    if effect_status is not None:
        return _hold(
            basis,
            source_digest,
            exact_ids,
            effect_reasons or ("existing effect found for this receipt line",),
            status=effect_status,
            source=metadata,
        )
    return BillingPreview(
        source_digest=source_digest,
        bill_digest=basis.bill_digest,
        exact_ids=exact_ids,
        quantity=basis.quantity,
        uom=basis.uom,
        stock_uom=basis.stock_uom,
        conversion_factor=basis.conversion_factor,
        net_amount=basis.net_amount,
        gross_amount=basis.gross_amount,
        required_inputs=(
            "DISCLOSED_SYNTHETIC_BILL",
            "COMPLETE_SCOPED_RELATED_DOCUMENT_READ",
            "NATIVE_PR_TO_PI_MAPPER",
            "SEPARATE_APPROVAL_REQUIRED",
        ),
        status="READY",
        reasons=(),
        read_only=True,
        write_allowed=False,
        source=_public_source(metadata),
    )
