"""Read only source collection for the narrow normal-receipt bill preview.

The only POST in this module is ERPNext's native Purchase Receipt to Purchase
Invoice mapper.  It returns an unsaved proposal and is never an insert,
submit, update, or payment request.  This adapter deliberately owns neither
approval nor durable attempt state; those are separate later boundaries.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from types import MappingProxyType
from typing import Any, Protocol
from urllib.parse import quote, urlencode

from the_missing_20.adapters.normal_receipt_billing_preview import (
    BillingPreview,
    ExactIds,
    SyntheticBillingBasis,
    validate_billing_preview,
)

RELATED_PAGE_SIZE = 50
MAX_RELATED_PAGES = 4
MAX_RELATED_DOCUMENTS = 100
MAX_RESPONSE_BYTES = 128 * 1024
READ_ELAPSED_BUDGET_SECONDS = 30.0

NATIVE_MAPPER_PATH = (
    "/api/method/erpnext.stock.doctype.purchase_receipt.purchase_receipt.make_purchase_invoice"
)
_RESOURCE_PATH = "/api/resource"
_RELATED_DOCTYPES = ("Purchase Invoice", "Purchase Receipt")
_COVERAGE_FIELDS = (
    "receipt_line_invoices",
    "receipt_returns",
    "bill_reference_collisions",
)
_BILL_REFERENCE_ALIASES = ("bill_no", "supplier_invoice_no")
_PURCHASE_ORDER_ALIASES = ("purchase_order", "po_no")
_PURCHASE_ORDER_ITEM_ALIASES = ("po_detail", "purchase_order_item")
_PURCHASE_RECEIPT_ALIASES = ("purchase_receipt", "receipt")
_PURCHASE_RECEIPT_ITEM_ALIASES = ("pr_detail", "purchase_receipt_item")


class ERPRequest(Protocol):
    """The existing configured ERPNext request callable (for example, ``_request``)."""

    def __call__(
        self, path: str, *, method: str = "GET", payload: object | None = None
    ) -> object: ...


@dataclass(frozen=True, slots=True)
class NormalReceiptBillingSourceRead:
    """Detached source snapshots, collection evidence, and a read-only preview."""

    purchase_order: object
    purchase_receipt: object
    mapped_invoice: object
    related_documents_read: Mapping[str, object]
    evidence_manifest: Mapping[str, object]
    observed_at: str
    snapshot_digest: str
    preview: BillingPreview


class _SourceReadFailure(Exception):
    def __init__(self, stage: str, detail: str) -> None:
        super().__init__(detail)
        self.stage = stage
        self.detail = detail


def _jsonable(value: object) -> object:
    """Canonicalize JSON-like evidence without normalizing mapping keys."""

    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("source evidence mapping keys must be strings")
            result[key] = _jsonable(item)
        return result
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, float):
        return value if math.isfinite(value) else {"__nonfinite__": str(value).lower()}
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    return {"__unsupported_type__": type(value).__qualname__, "repr": repr(value)}


def _digest(value: object) -> str:
    encoded = json.dumps(_jsonable(value), sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _copy(value: object) -> object:
    """Detach a transport payload before preview validation can inspect it."""

    return deepcopy(value)


def _scope(basis: SyntheticBillingBasis) -> dict[str, str]:
    return {
        "company": basis.company,
        "supplier": basis.supplier,
        "purchase_order": basis.purchase_order,
        "purchase_order_item": basis.purchase_order_item,
        "purchase_receipt": basis.purchase_receipt,
        "purchase_receipt_item": basis.purchase_receipt_item,
    }


def _coverage(complete: bool) -> dict[str, bool]:
    return {field_name: complete for field_name in _COVERAGE_FIELDS}


class NormalReceiptBillingSourceReader:
    """Collect one server-bound bill basis through an allowlisted read surface."""

    def __init__(
        self,
        request: ERPRequest,
        *,
        clock: Callable[[], float] = time.monotonic,
        elapsed_budget_seconds: float = READ_ELAPSED_BUDGET_SECONDS,
    ) -> None:
        if isinstance(elapsed_budget_seconds, bool) or not isinstance(
            elapsed_budget_seconds, (int, float)
        ):
            raise ValueError("elapsed budget must be a finite positive number")
        budget = float(elapsed_budget_seconds)
        if not math.isfinite(budget) or budget <= 0:
            raise ValueError("elapsed budget must be a finite positive number")
        self._request = request
        self._clock = clock
        self._elapsed_budget_seconds = budget
        self._started_at = 0.0
        self._manifest: dict[str, object] = {}

    def read(self, basis: SyntheticBillingBasis) -> NormalReceiptBillingSourceRead:
        """Return a detached, complete-or-held read packet for one fixed bill basis."""

        if not isinstance(basis, SyntheticBillingBasis):
            raise TypeError("normal receipt billing source requires SyntheticBillingBasis")
        self._started_at = self._now("read start")
        self._manifest = {
            "read_only": True,
            "bounds": {
                "page_size": RELATED_PAGE_SIZE,
                "max_pages_per_doctype": MAX_RELATED_PAGES,
                "max_documents": MAX_RELATED_DOCUMENTS,
                "max_response_bytes": MAX_RESPONSE_BYTES,
                "elapsed_budget_seconds": self._elapsed_budget_seconds,
                "elapsed_budget_mode": (
                    "checked before and after each transport call; not an interrupt"
                ),
            },
            "requests": [],
            "pages": [],
            "failures": [],
        }
        purchase_order: object = {}
        purchase_receipt: object = {}
        mapped_invoice: object = {}
        documents: list[dict[str, Any]] = []
        complete = False

        try:
            purchase_order = self._read_exact_document("Purchase Order", basis.purchase_order)
            self._validate_parent(purchase_order, "Purchase Order", basis.purchase_order, basis)
            purchase_receipt = self._read_exact_document("Purchase Receipt", basis.purchase_receipt)
            self._validate_parent(
                purchase_receipt, "Purchase Receipt", basis.purchase_receipt, basis
            )
            mapped_invoice = self._read_mapper(basis)
            self._validate_mapper(mapped_invoice)

            invoice_names, _ = self._discover_parent_names("Purchase Invoice", basis, known_count=0)
            receipt_names, _ = self._discover_parent_names(
                "Purchase Receipt", basis, known_count=len(invoice_names)
            )

            for name in invoice_names:
                document = self._read_related_document("Purchase Invoice", name)
                self._preserve_related_document(documents, document)
                self._validate_parent(document, "Purchase Invoice", name, basis)
                self._validate_related_schema(document, "Purchase Invoice", name, basis)
            for name in receipt_names:
                document = self._read_related_document("Purchase Receipt", name)
                self._preserve_related_document(documents, document)
                self._validate_parent(document, "Purchase Receipt", name, basis)
                self._validate_related_schema(document, "Purchase Receipt", name, basis)
            complete = True
        except _SourceReadFailure as error:
            self._record_failure(error.stage, error.detail)
        except Exception as error:  # Defensive conversion of a caller's transport error to HOLD.
            self._record_failure("unexpected", f"{type(error).__name__}: {error}")

        observed_at = datetime.now(UTC).isoformat()
        page_count = len(self._pages())
        snapshot_digest = _digest(
            {
                "basis": basis.record(),
                "purchase_order": purchase_order,
                "purchase_receipt": purchase_receipt,
                "mapped_invoice": mapped_invoice,
                "related_documents": documents,
                "manifest": self._manifest,
            }
        )
        related_documents_read: dict[str, object] = {
            "status": "COMPLETE" if complete else "INCOMPLETE",
            "pagination": {"complete": complete, "pages": page_count},
            "pagination_complete": complete,
            "scope": _scope(basis),
            "coverage": _coverage(complete),
            "observed_at": observed_at,
            "source_revision": snapshot_digest,
            "documents": documents,
        }
        preview = self._preview(
            basis,
            purchase_order,
            purchase_receipt,
            mapped_invoice,
            related_documents_read,
            snapshot_digest,
        )
        return NormalReceiptBillingSourceRead(
            purchase_order=purchase_order,
            purchase_receipt=purchase_receipt,
            mapped_invoice=mapped_invoice,
            related_documents_read=related_documents_read,
            evidence_manifest=self._manifest,
            observed_at=observed_at,
            snapshot_digest=snapshot_digest,
            preview=preview,
        )

    def _preview(
        self,
        basis: SyntheticBillingBasis,
        purchase_order: object,
        purchase_receipt: object,
        mapped_invoice: object,
        related_documents_read: Mapping[str, object],
        snapshot_digest: str,
    ) -> BillingPreview:
        try:
            return validate_billing_preview(
                basis,
                purchase_order=(purchase_order if isinstance(purchase_order, Mapping) else {}),
                purchase_receipt=(
                    purchase_receipt if isinstance(purchase_receipt, Mapping) else {}
                ),
                mapped_invoice=(mapped_invoice if isinstance(mapped_invoice, Mapping) else {}),
                related_documents_read=related_documents_read,
            )
        except Exception as error:  # No malformed input may escape as a viable proposal.
            detail = f"preview construction failed: {type(error).__name__}: {error}"
            self._record_failure("preview", detail)
            return BillingPreview(
                source_digest=snapshot_digest,
                bill_digest=basis.bill_digest,
                exact_ids=ExactIds(
                    basis.case_id,
                    basis.purchase_order,
                    basis.purchase_order_item,
                    basis.purchase_receipt,
                    basis.purchase_receipt_item,
                ),
                quantity=basis.quantity,
                uom=basis.uom,
                stock_uom=basis.stock_uom,
                conversion_factor=basis.conversion_factor,
                net_amount=basis.net_amount,
                gross_amount=basis.gross_amount,
                required_inputs=(detail,),
                status="HOLD",
                reasons=(detail,),
                source=MappingProxyType({"read_only": True}),
            )

    def _read_exact_document(self, doctype: str, name: str) -> object:
        payload = self._request_json(
            f"{_RESOURCE_PATH}/{quote(doctype, safe='')}/{quote(name, safe='')}",
            stage=f"{doctype} {name}",
        )
        document = self._response_value(payload, "data", f"{doctype} {name}")
        return _copy(document)

    def _read_mapper(self, basis: SyntheticBillingBasis) -> object:
        payload = self._request_json(
            NATIVE_MAPPER_PATH,
            method="POST",
            payload={
                "source_name": basis.purchase_receipt,
                "args": {"filtered_children": [basis.purchase_receipt_item]},
            },
            stage="native Purchase Receipt to Purchase Invoice mapper",
        )
        mapped = _copy(
            self._response_value(
                payload,
                "message",
                "native Purchase Receipt to Purchase Invoice mapper",
            )
        )
        return mapped

    def _validate_mapper(self, mapped: object) -> None:
        if not isinstance(mapped, Mapping):
            raise _SourceReadFailure("mapper", "native mapper did not return a document mapping")
        self._validate_children(mapped, "native mapper")

    def _discover_parent_names(
        self,
        doctype: str,
        basis: SyntheticBillingBasis,
        *,
        known_count: int,
    ) -> tuple[list[str], int]:
        if doctype not in _RELATED_DOCTYPES:
            raise _SourceReadFailure("discovery", "doctype is outside the related-read allowlist")
        names: list[str] = []
        seen: set[str] = set()
        for page_index in range(MAX_RELATED_PAGES):
            offset = page_index * RELATED_PAGE_SIZE
            query = urlencode(
                {
                    "fields": json.dumps(["name"], separators=(",", ":")),
                    "filters": json.dumps(
                        [
                            ["company", "=", basis.company],
                            ["supplier", "=", basis.supplier],
                        ],
                        separators=(",", ":"),
                    ),
                    "order_by": "name asc",
                    "limit_page_length": str(RELATED_PAGE_SIZE),
                    "limit_start": str(offset),
                }
            )
            payload = self._request_json(
                f"{_RESOURCE_PATH}/{quote(doctype, safe='')}?{query}",
                stage=f"{doctype} discovery page {page_index + 1}",
            )
            rows = self._response_value(
                payload, "data", f"{doctype} discovery page {page_index + 1}"
            )
            page_record: dict[str, object] = {
                "doctype": doctype,
                "page": page_index + 1,
                "offset": offset,
                "rows": _copy(rows),
            }
            self._pages().append(page_record)
            if not isinstance(rows, list):
                raise _SourceReadFailure(
                    "pagination", f"{doctype} discovery page {page_index + 1} was malformed"
                )
            if len(rows) > RELATED_PAGE_SIZE:
                raise _SourceReadFailure(
                    "pagination",
                    f"{doctype} discovery page {page_index + 1} exceeded the page-size bound",
                )
            page_names: list[str] = []
            for row in rows:
                if not isinstance(row, Mapping):
                    raise _SourceReadFailure(
                        "pagination",
                        f"{doctype} discovery page {page_index + 1} contains a malformed row",
                    )
                name = row.get("name")
                if not isinstance(name, str) or not name.strip():
                    raise _SourceReadFailure(
                        "pagination",
                        f"{doctype} discovery page {page_index + 1} has no parent name",
                    )
                if name in seen:
                    raise _SourceReadFailure(
                        "pagination", f"{doctype} discovery repeated parent {name}"
                    )
                seen.add(name)
                page_names.append(name)
            if page_names != sorted(page_names):
                raise _SourceReadFailure(
                    "pagination", f"{doctype} discovery page {page_index + 1} was not in name order"
                )
            if names and page_names and page_names[0] <= names[-1]:
                raise _SourceReadFailure(
                    "pagination",
                    f"{doctype} discovery page {page_index + 1} broke stable name ordering",
                )
            page_record["names"] = list(page_names)
            if known_count + len(names) + len(page_names) > MAX_RELATED_DOCUMENTS:
                raise _SourceReadFailure(
                    "limit",
                    "related parent document limit reached before complete pagination was observed",
                )
            names.extend(page_names)
            if len(page_names) < RELATED_PAGE_SIZE:
                return names, page_index + 1
        raise _SourceReadFailure(
            "limit",
            f"{doctype} discovery page limit reached before complete pagination was observed",
        )

    def _read_related_document(self, doctype: str, name: str) -> object:
        payload = self._request_json(
            f"{_RESOURCE_PATH}/{quote(doctype, safe='')}/{quote(name, safe='')}",
            stage=f"{doctype} parent {name}",
        )
        return _copy(self._response_value(payload, "data", f"{doctype} parent {name}"))

    def _validate_parent(
        self, document: object, doctype: str, name: str, basis: SyntheticBillingBasis
    ) -> None:
        if not isinstance(document, Mapping):
            raise _SourceReadFailure(
                "parent", f"{doctype} parent {name} was not a document mapping"
            )
        if document.get("doctype") != doctype or document.get("name") != name:
            raise _SourceReadFailure(
                "identity", f"{doctype} parent {name} returned a different identity"
            )
        if document.get("company") != basis.company or document.get("supplier") != basis.supplier:
            raise _SourceReadFailure(
                "scope", f"{doctype} parent {name} is outside company/supplier scope"
            )
        status = document.get("docstatus")
        if isinstance(status, bool) or not isinstance(status, (int, float)):
            raise _SourceReadFailure(
                "status", f"{doctype} parent {name} has an unknown document status"
            )
        numeric_status = float(status)
        if not numeric_status.is_integer() or int(numeric_status) not in {0, 1, 2}:
            raise _SourceReadFailure(
                "status", f"{doctype} parent {name} has an unknown document status"
            )
        self._validate_children(document, f"{doctype} parent {name}")

    def _preserve_related_document(self, documents: list[dict[str, Any]], document: object) -> None:
        if isinstance(document, Mapping):
            documents.append(dict(document))

    def _validate_children(self, document: Mapping[str, object], label: str) -> None:
        children = document.get("items")
        if not isinstance(children, list) or any(
            not isinstance(child, Mapping) for child in children
        ):
            raise _SourceReadFailure(
                "children", f"{label} does not expose a complete native child list"
            )

    def _validate_related_schema(
        self,
        document: object,
        doctype: str,
        name: str,
        basis: SyntheticBillingBasis,
    ) -> None:
        if not isinstance(document, Mapping):
            raise _SourceReadFailure("schema", f"{doctype} parent {name} is not a mapping")
        children = document.get("items")
        assert isinstance(children, list)
        if doctype == "Purchase Invoice":
            self._validate_related_invoice(document, children, name, basis)
            return
        if doctype == "Purchase Receipt":
            self._validate_related_receipt(document, children, name, basis)
            return
        raise _SourceReadFailure("schema", f"{doctype} is outside related schema allowlist")

    def _validate_related_invoice(
        self,
        document: Mapping[object, object],
        children: list[object],
        name: str,
        basis: SyntheticBillingBasis,
    ) -> None:
        label = f"Purchase Invoice parent {name}"
        self._identifier(
            document,
            _BILL_REFERENCE_ALIASES,
            f"{label} supplier bill reference",
            required=True,
        )
        self._identifier(
            document,
            ("return_against",),
            f"{label} return reference",
            required=False,
        )
        self._require_known_flag(document, "is_return", label)
        if not children:
            raise _SourceReadFailure("schema", f"{label} has no child rows")
        for index, child in enumerate(children, start=1):
            assert isinstance(child, Mapping)
            child_label = f"{label} child {index}"
            po_declared, _ = self._identifier(
                child,
                _PURCHASE_ORDER_ALIASES,
                f"{child_label} purchase order",
                required=False,
            )
            po_item_declared, _ = self._identifier(
                child,
                _PURCHASE_ORDER_ITEM_ALIASES,
                f"{child_label} purchase order row",
                required=False,
            )
            pr_declared, receipt = self._identifier(
                child,
                _PURCHASE_RECEIPT_ALIASES,
                f"{child_label} purchase receipt",
                required=True,
            )
            pr_item_declared, receipt_item = self._identifier(
                child,
                _PURCHASE_RECEIPT_ITEM_ALIASES,
                f"{child_label} purchase receipt row",
                required=False,
            )
            assert pr_declared
            if receipt != basis.purchase_receipt:
                continue
            if not pr_item_declared or receipt_item in (None, ""):
                raise _SourceReadFailure(
                    "schema", f"{child_label} target receipt has no exact row identity"
                )
            if receipt_item != basis.purchase_receipt_item:
                continue
            if not po_declared or not po_item_declared:
                raise _SourceReadFailure(
                    "schema", f"{child_label} target receipt row has no declared purchase-order row"
                )

    def _validate_related_receipt(
        self,
        document: Mapping[object, object],
        children: list[object],
        name: str,
        basis: SyntheticBillingBasis,
    ) -> None:
        label = f"Purchase Receipt parent {name}"
        self._require_known_flag(document, "is_return", label)
        _, return_against = self._identifier(
            document,
            ("return_against",),
            f"{label} return reference",
            required=False,
        )
        child_links: list[tuple[bool, str | None, bool, str | None]] = []
        for index, child in enumerate(children, start=1):
            assert isinstance(child, Mapping)
            child_label = f"{label} child {index}"
            po_declared, purchase_order = self._identifier(
                child,
                _PURCHASE_ORDER_ALIASES,
                f"{child_label} purchase order",
                required=False,
            )
            po_item_declared, purchase_order_item = self._identifier(
                child,
                _PURCHASE_ORDER_ITEM_ALIASES,
                f"{child_label} purchase order row",
                required=False,
            )
            self._identifier(
                child,
                _PURCHASE_RECEIPT_ALIASES,
                f"{child_label} purchase receipt",
                required=False,
            )
            self._identifier(
                child,
                _PURCHASE_RECEIPT_ITEM_ALIASES,
                f"{child_label} purchase receipt row",
                required=False,
            )
            child_links.append((po_declared, purchase_order, po_item_declared, purchase_order_item))
        if document["is_return"] != 1:
            return
        if return_against == basis.purchase_receipt:
            return
        has_target_child = any(
            purchase_order == basis.purchase_order
            and purchase_order_item == basis.purchase_order_item
            for _, purchase_order, _, purchase_order_item in child_links
        )
        if return_against not in (None, "") or has_target_child:
            return
        if not child_links:
            raise _SourceReadFailure("schema", f"{label} return has no header or child identity")
        for index, (
            po_declared,
            purchase_order,
            po_item_declared,
            purchase_order_item,
        ) in enumerate(child_links, start=1):
            if (
                not po_declared
                or not po_item_declared
                or purchase_order in (None, "")
                or purchase_order_item in (None, "")
            ):
                raise _SourceReadFailure(
                    "schema",
                    f"{label} child {index} cannot exclude the target purchase-order row",
                )

    def _identifier(
        self,
        document: Mapping[object, object],
        field_names: tuple[str, ...],
        label: str,
        *,
        required: bool,
    ) -> tuple[bool, str | None]:
        present = [field_name for field_name in field_names if field_name in document]
        if not present:
            if required:
                raise _SourceReadFailure("schema", f"{label} is missing {'/'.join(field_names)}")
            return False, None
        non_null: list[str] = []
        effective: str | None = None
        for field_name in field_names:
            if field_name not in document:
                continue
            value = document[field_name]
            if value is None:
                continue
            if not isinstance(value, str) or (value != "" and not value.strip()):
                raise _SourceReadFailure("schema", f"{label} has an invalid {field_name}")
            non_null.append(value)
            if effective is None:
                effective = value
        if any(value != non_null[0] for value in non_null[1:]):
            raise _SourceReadFailure("schema", f"{label} aliases disagree")
        return True, effective

    def _require_known_flag(
        self, document: Mapping[object, object], field_name: str, label: str
    ) -> None:
        if field_name not in document:
            raise _SourceReadFailure("schema", f"{label} is missing {field_name}")
        value = document[field_name]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value not in {0, 1}:
            raise _SourceReadFailure("schema", f"{label} has unknown {field_name}")

    def _request_json(
        self,
        path: str,
        *,
        method: str = "GET",
        payload: object | None = None,
        stage: str,
    ) -> object:
        self._check_elapsed(f"before {stage}")
        record: dict[str, object] = {
            "sequence": len(self._requests()) + 1,
            "stage": stage,
            "method": method,
            "path": path,
            "payload": _copy(payload),
        }
        self._requests().append(record)
        try:
            response = self._request(path, method=method, payload=payload)
        except Exception as error:
            record.update(
                outcome="ERROR",
                error=f"{type(error).__name__}: {error}",
            )
            raise _SourceReadFailure(stage, f"{type(error).__name__}: {error}") from error
        record.update(outcome="OK", response=_copy(response))
        self._check_response_size(response, stage)
        self._check_elapsed(f"after {stage}")
        return response

    def _response_value(self, payload: object, key: str, stage: str) -> object:
        if not isinstance(payload, Mapping) or key not in payload:
            raise _SourceReadFailure(stage, f"response did not contain {key}")
        return payload[key]

    def _now(self, stage: str) -> float:
        try:
            value = self._clock()
        except Exception as error:
            raise _SourceReadFailure(
                stage, f"clock failed: {type(error).__name__}: {error}"
            ) from error
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise _SourceReadFailure(stage, "clock returned a non-numeric value")
        numeric = float(value)
        if not math.isfinite(numeric):
            raise _SourceReadFailure(stage, "clock returned a non-finite value")
        return numeric

    def _check_elapsed(self, stage: str) -> None:
        elapsed = self._now(stage) - self._started_at
        if elapsed < 0:
            raise _SourceReadFailure(
                "elapsed", "monotonic clock moved backwards during source read"
            )
        if elapsed > self._elapsed_budget_seconds:
            raise _SourceReadFailure(
                "elapsed",
                "elapsed source-read budget exceeded; no further transport calls were started",
            )

    def _check_response_size(self, response: object, stage: str) -> None:
        try:
            encoded = json.dumps(_jsonable(response), sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        except (TypeError, ValueError) as error:
            raise _SourceReadFailure(
                "size",
                f"{stage} response could not be size-bounded: {type(error).__name__}: {error}",
            ) from error
        if len(encoded) > MAX_RESPONSE_BYTES:
            raise _SourceReadFailure(
                "size",
                f"{stage} response exceeded the post-read size bound",
            )

    def _record_failure(self, stage: str, detail: str) -> None:
        self._failures().append({"stage": stage, "detail": detail})

    def _requests(self) -> list[dict[str, object]]:
        requests = self._manifest["requests"]
        assert isinstance(requests, list)
        return requests

    def _pages(self) -> list[dict[str, object]]:
        pages = self._manifest["pages"]
        assert isinstance(pages, list)
        return pages

    def _failures(self) -> list[dict[str, object]]:
        failures = self._manifest["failures"]
        assert isinstance(failures, list)
        return failures
