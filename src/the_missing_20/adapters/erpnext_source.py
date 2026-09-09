"""Read-only ERPNext evidence adapter for the live competition demo.

The adapter deliberately exposes a narrow, case-scoped projection.  Browser
clients never receive credentials and this process never mutates ERPNext; all
writes are performed by the separate, explicit seed script.
"""

from __future__ import annotations

import json
import math
import os
import threading
import time
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

ERP_NEXT_SCHEMA_VERSION = "missing20-erpnext-evidence/v1"
DEFAULT_PO = "PUR-ORD-2026-00011"
DEFAULT_RECEIPT = "MAT-PRE-2026-00001"
DEFAULT_INVOICE = "ACC-PINV-2026-00007"
DEFAULT_CASE_ID = "M20-ECU-2026-00011-LOT-A"
DEFAULT_CUSTOMER_PO = "M20-FLEET-PO-2026-0907-A"


def _read_env_file(path: Path) -> dict[str, str]:
    """Read simple dotenv entries without importing a dotenv dependency."""

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    values: dict[str, str] = {}
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


@dataclass(frozen=True, slots=True)
class ERPNextCredentials:
    base_url: str
    api_key: str
    api_secret: str


class ERPNextEvidenceSource:
    """Fetch exactly the documents needed to substantiate the Missing 20 case."""

    def __init__(
        self,
        credentials: ERPNextCredentials | None,
        *,
        transport: Callable[[Request, float], bytes] | None = None,
        timeout_seconds: float = 8.0,
        purchase_order: str = DEFAULT_PO,
        purchase_receipt: str = DEFAULT_RECEIPT,
        purchase_invoice: str = DEFAULT_INVOICE,
        case_id: str = DEFAULT_CASE_ID,
        customer_purchase_order: str = "",
        discover_purchase_documents: bool = False,
        cache_seconds: float = 0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._credentials = credentials
        self._transport = transport or self._default_transport
        self._timeout_seconds = timeout_seconds
        self._purchase_order = purchase_order
        self._purchase_receipt = purchase_receipt
        self._purchase_invoice = purchase_invoice
        self._case_id = case_id
        self._customer_purchase_order = customer_purchase_order
        self._discover_purchase_documents = discover_purchase_documents
        self._sequence = 0
        self._last_fingerprint = ""
        self._last_changed_at: datetime | None = None
        self._cache_seconds = max(0, cache_seconds)
        self._clock = clock
        self._read_lock = threading.RLock()
        self._cached: dict[str, object] | None = None
        self._cache_until = 0.0
        self._retry_not_before = 0.0

    def _finalize(self, projection: dict[str, object], now: datetime) -> dict[str, object]:
        """Version the projection by external business state, not polling cadence."""

        raw_activity = projection.get("activity", [])
        source_activity = raw_activity if isinstance(raw_activity, list) else []
        semantic = {
            "status": projection.get("status"),
            "documents": projection.get("documents", []),
            "document_lifecycle": projection.get("document_lifecycle", {}),
            "read_errors": projection.get("read_errors", []),
            "read_error": projection.get("read_error"),
            "primary_document_names": projection.get("primary_document_names", {}),
            "activity": [
                {key: value for key, value in item.items() if key != "occurred_at"}
                for item in source_activity
                if isinstance(item, Mapping)
            ],
        }
        fingerprint = json.dumps(semantic, sort_keys=True, separators=(",", ":"))
        if fingerprint != self._last_fingerprint:
            self._sequence += 1
            self._last_fingerprint = fingerprint
            self._last_changed_at = now
        changed_at = self._last_changed_at or now
        activity = [
            {**item, "occurred_at": changed_at.isoformat()}
            for item in source_activity
            if isinstance(item, Mapping)
        ]
        return {
            **projection,
            "sequence": self._sequence,
            "received_at": now.isoformat(),
            "changed_at": changed_at.isoformat(),
            "activity": activity,
        }

    @classmethod
    def from_environment(cls, *, repository_root: Path) -> ERPNextEvidenceSource:
        dotenv = _read_env_file(repository_root / ".env")
        values = {**dotenv, **os.environ}
        base_url = values.get("ERPNEXT_BASE_URL", "").rstrip("/")
        api_key = values.get("ERPNEXT_API_KEY", "")
        api_secret = values.get("ERPNEXT_API_SECRET", "")
        credentials = (
            ERPNextCredentials(base_url=base_url, api_key=api_key, api_secret=api_secret)
            if base_url and api_key and api_secret
            else None
        )
        return cls(
            credentials,
            purchase_order=values.get("MISSING20_ERPNEXT_PURCHASE_ORDER", DEFAULT_PO),
            purchase_receipt=values.get("MISSING20_ERPNEXT_PURCHASE_RECEIPT", DEFAULT_RECEIPT),
            purchase_invoice=values.get("MISSING20_ERPNEXT_PURCHASE_INVOICE", DEFAULT_INVOICE),
            case_id=values.get("MISSING20_CASE_ID", "").strip() or DEFAULT_CASE_ID,
            customer_purchase_order=values.get(
                "MISSING20_ERPNEXT_CUSTOMER_PO", DEFAULT_CUSTOMER_PO
            ),
            discover_purchase_documents=True,
            cache_seconds=30,
        )

    @staticmethod
    def _default_transport(request: Request, timeout: float) -> bytes:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - configured HTTPS endpoint
            return bytes(response.read())

    def _get_document(self, doctype: str, name: str) -> Mapping[str, Any]:
        assert self._credentials is not None
        url = (
            f"{self._credentials.base_url}/api/resource/"
            f"{quote(doctype, safe='')}/{quote(name, safe='')}"
        )
        request = Request(
            url,
            headers={
                "Authorization": (
                    f"token {self._credentials.api_key}:{self._credentials.api_secret}"
                ),
                "Accept": "application/json",
                "User-Agent": "TheMissing20/0.1 read-only evidence adapter",
            },
        )
        payload = json.loads(self._transport(request, self._timeout_seconds).decode("utf-8"))
        document = payload.get("data") if isinstance(payload, Mapping) else None
        if not isinstance(document, Mapping):
            raise ValueError(f"ERPNext returned no {doctype} document")
        numeric_fields = {
            "qty",
            "received_qty",
            "rejected_qty",
            "rate",
            "amount",
            "net_rate",
            "net_amount",
            "grand_total",
            "net_total",
            "total_qty",
            "docstatus",
        }
        for record in [document, *self._items(document)]:
            for key in numeric_fields.intersection(record):
                value = record[key]
                if value is not None and (
                    not isinstance(value, (str, int, float))
                    or isinstance(value, bool)
                    or not math.isfinite(float(value))
                ):
                    raise ValueError("ERPNext returned invalid numeric evidence")
        return document

    def _get_rows(
        self,
        doctype: str,
        *,
        fields: list[str],
        filters: list[list[object]],
        limit: int = 100,
    ) -> list[Mapping[str, Any]]:
        """Read a bounded report slice through Frappe's resource API."""

        assert self._credentials is not None
        query = urlencode(
            {
                "fields": json.dumps(fields),
                "filters": json.dumps(filters),
                "limit_page_length": str(limit),
                "order_by": "creation asc",
            }
        )
        url = f"{self._credentials.base_url}/api/resource/{quote(doctype, safe='')}?{query}"
        request = Request(
            url,
            headers={
                "Authorization": (
                    f"token {self._credentials.api_key}:{self._credentials.api_secret}"
                ),
                "Accept": "application/json",
                "User-Agent": "TheMissing20/0.1 read-only ledger evidence adapter",
            },
        )
        payload = json.loads(self._transport(request, self._timeout_seconds).decode("utf-8"))
        rows = payload.get("data") if isinstance(payload, Mapping) else None
        if not isinstance(rows, list):
            raise ValueError(f"ERPNext returned no {doctype} rows")
        return [row for row in rows if isinstance(row, Mapping)]

    def _optional_document(self, doctype: str, name: str) -> Mapping[str, Any]:
        # Only an unconfigured future document is optional. A configured ID
        # disappearing, access denial, malformed response or timeout is an outage.
        return self._get_document(doctype, name) if name else {}

    def _purchase_documents(
        self, po: Mapping[str, Any], doctype: str, configured: Mapping[str, Any]
    ) -> list[Mapping[str, Any]]:
        """Bound parent reads, then prove each exact PO child relationship.

        Direct child-table REST queries are denied to the least-privilege demo
        user. Do not quietly present the first page as a complete history.
        """
        if not self._discover_purchase_documents:
            return [configured] if configured else []
        if not po.get("supplier"):
            raise ValueError("Purchase order supplier is required for scoped discovery")
        filters: list[list[object]] = [["supplier", "=", po["supplier"]]]
        if po.get("company"):
            filters.append(["company", "=", po["company"]])
        if po.get("creation"):
            filters.append(["creation", ">=", po["creation"]])
        rows = self._get_rows(doctype, fields=["name"], filters=filters, limit=100)
        if len(rows) >= 100:
            raise ValueError("Scoped purchase document page is incomplete")
        names = sorted({str(row["name"]) for row in rows if row.get("name")})
        configured_name = str(configured.get("name", ""))
        names = [name for name in names if name != configured_name]
        with ThreadPoolExecutor(max_workers=4, thread_name_prefix="m20-purchase-read") as pool:
            fetched = list(pool.map(lambda name: self._get_document(doctype, name), names))
        candidates = ([configured] if configured else []) + fetched
        selected: list[Mapping[str, Any]] = []
        for document in candidates:
            items = self._items(document)
            matched = [item for item in items if item.get("purchase_order") == po.get("name")]
            if not matched:
                if document.get("name") == configured_name:
                    raise ValueError("Configured purchase document does not match this order")
                continue
            selected.append(
                {**document, "items": matched, "case_scope_complete": len(matched) == len(items)}
            )
        return selected

    @staticmethod
    def _business_metadata(document: Mapping[str, Any]) -> dict[str, object]:
        """Allowlist source identity and net accounting bases, never raw payloads."""
        fields = (
            "docstatus",
            "modified",
            "posting_date",
            "posting_time",
            "transaction_date",
            "schedule_date",
            "company",
            "currency",
            "net_total",
            "total_taxes_and_charges",
            "discount_amount",
            "is_return",
            "return_against",
            "case_scope_complete",
        )
        metadata: dict[str, object] = {key: document[key] for key in fields if key in document}
        item_fields = (
            "name",
            "item_code",
            "qty",
            "uom",
            "stock_uom",
            "conversion_factor",
            "net_rate",
            "net_amount",
            "rate",
            "amount",
            "purchase_order",
            "po_detail",
            "purchase_order_item",
            "purchase_receipt",
            "purchase_receipt_item",
            "warehouse",
            "batch_no",
            "received_qty",
            "rejected_qty",
            "rejected_warehouse",
            "schedule_date",
        )
        items = ERPNextEvidenceSource._items(document)
        if any(item.get("item_code") for item in items):
            metadata["items"] = [
                {key: item[key] for key in item_fields if key in item} for item in items
            ]
            units = {str(item.get("uom")) for item in items if item.get("uom")}
            if len(units) == 1 and all(item.get("uom") for item in items):
                metadata["uom"] = next(iter(units))
        return metadata

    def _purchase_summary(self, document: Mapping[str, Any], kind: str) -> dict[str, object]:
        items = self._items(document)
        lifecycle = document.get("docstatus")
        status = "CANCELLED" if lifecycle == 2 else "DRAFT" if lifecycle == 0 else "RECEIVED"
        summary: dict[str, object] = {
            "kind": kind,
            "name": str(document.get("name", "")),
            "status": status,
            **self._business_metadata(document),
        }
        if kind == "purchase_receipt":
            accepted = sum(float(item.get("qty") or 0) for item in items)
            rejected = sum(float(item.get("rejected_qty") or 0) for item in items)
            received = sum(
                float(item["received_qty"])
                if item.get("received_qty") is not None
                else float(item.get("qty") or 0) + float(item.get("rejected_qty") or 0)
                for item in items
            )
            summary.update(
                accepted=accepted,
                rejected=rejected,
                received=received,
                quality_hold_remaining=max(0.0, rejected),
                delivery_note=str(document.get("supplier_delivery_note", "")),
            )
            if lifecycle == 1 and rejected > 0:
                summary["status"] = "PARTIAL_QUALITY_HOLD"
        else:
            held = bool(document.get("on_hold"))
            summary.update(
                on_hold=held,
                bill_no=str(document.get("bill_no", "")),
                hold_comment=str(document.get("hold_comment", "")),
                grand_total=document.get("grand_total"),
                linked_receipts=sorted(
                    {
                        str(item["purchase_receipt"])
                        for item in items
                        if item.get("purchase_receipt")
                    }
                ),
            )
            if lifecycle == 1:
                summary["status"] = "PAYMENT_HOLD" if held else "OPEN"
            if document.get("case_scope_complete") is False:
                summary["grand_total"] = None
                summary["amount_status"] = "DOCUMENT_CONTAINS_OTHER_ORDERS"
        return summary

    def _ledger_evidence(
        self,
        *,
        purchase_receipt: str,
        purchase_invoice: str,
        recovery_transfer: str,
        delivery_note: str = "",
        sales_invoice: str = "",
        additional_purchase_documents: list[str] | None = None,
    ) -> dict[str, object]:
        """Read the exact stock and accounting postings behind the demo documents.

        Ledger evidence is intentionally non-authorizing: it proves what ERPNext
        posted after a submitted document, but it cannot approve or initiate a
        business effect.
        """

        voucher_names = [
            name
            for name in [purchase_receipt, purchase_invoice, *(additional_purchase_documents or [])]
            if name
        ]
        if recovery_transfer:
            voucher_names.append(recovery_transfer)
        if delivery_note:
            voucher_names.append(delivery_note)
        if sales_invoice:
            voucher_names.append(sales_invoice)
        try:
            with ThreadPoolExecutor(max_workers=2, thread_name_prefix="m20-ledger-read") as pool:
                stock_future = pool.submit(
                    self._get_rows,
                    "Stock Ledger Entry",
                    fields=[
                        "name",
                        "voucher_type",
                        "voucher_no",
                        "item_code",
                        "warehouse",
                        "actual_qty",
                        "qty_after_transaction",
                        "stock_value_difference",
                        "company",
                        "posting_date",
                        "posting_time",
                    ],
                    filters=[["voucher_no", "in", voucher_names]],
                )
                general_future = pool.submit(
                    self._get_rows,
                    "GL Entry",
                    fields=[
                        "name",
                        "voucher_type",
                        "voucher_no",
                        "account",
                        "debit",
                        "credit",
                        "company",
                        "posting_date",
                        "party_type",
                        "party",
                    ],
                    filters=[["voucher_no", "in", voucher_names]],
                )
                stock_rows = stock_future.result()
                general_rows = general_future.result()
        except (OSError, URLError, TimeoutError, ValueError, json.JSONDecodeError):
            return {
                "status": "DEGRADED",
                "source": "ERPNext / Frappe Cloud",
                "read_only": True,
                "stock_entries": [],
                "general_ledger_entries": [],
                "assertions": {
                    "stock_ledger_present": False,
                    "general_ledger_present": False,
                    "debits_equal_credits": False,
                },
            }

        stock_entries = [
            {
                "name": str(row.get("name", "")),
                "voucher_type": str(row.get("voucher_type", "")),
                "voucher_no": str(row.get("voucher_no", "")),
                "item_code": str(row.get("item_code", "")),
                "warehouse": str(row.get("warehouse", "")),
                "actual_qty": float(row.get("actual_qty") or 0),
                "qty_after_transaction": float(row.get("qty_after_transaction") or 0),
                "stock_value_difference": float(row.get("stock_value_difference") or 0),
                "company": str(row.get("company", "")),
                "posting_date": str(row.get("posting_date", "")),
                "posting_time": str(row.get("posting_time", "")),
            }
            for row in stock_rows
        ]
        general_entries = [
            {
                "name": str(row.get("name", "")),
                "voucher_type": str(row.get("voucher_type", "")),
                "voucher_no": str(row.get("voucher_no", "")),
                "account": str(row.get("account", "")),
                "debit": float(row.get("debit") or 0),
                "credit": float(row.get("credit") or 0),
                "company": str(row.get("company", "")),
                "posting_date": str(row.get("posting_date", "")),
                "party_type": str(row.get("party_type", "")),
                "party": str(row.get("party", "")),
            }
            for row in general_rows
        ]
        debit_total = sum(float(str(row["debit"])) for row in general_entries)
        credit_total = sum(float(str(row["credit"])) for row in general_entries)
        balanced = bool(general_entries) and abs(debit_total - credit_total) < 0.005
        return {
            "status": "CONNECTED",
            "source": "ERPNext / Frappe Cloud",
            "read_only": True,
            "voucher_names": voucher_names,
            "stock_entries": stock_entries,
            "general_ledger_entries": general_entries,
            "totals": {
                "stock_value_difference": sum(
                    float(str(row["stock_value_difference"])) for row in stock_entries
                ),
                "debit": debit_total,
                "credit": credit_total,
            },
            "assertions": {
                "stock_ledger_present": bool(stock_entries),
                "general_ledger_present": bool(general_entries),
                "debits_equal_credits": balanced,
            },
        }

    def _find_recovery_transfer(self) -> Mapping[str, Any] | None:
        """Read only the exact Stock Entry produced by this M20 recovery case."""

        assert self._credentials is not None
        remarks = f"M20 DEMO release {self._case_id}"
        query = urlencode(
            {
                "fields": json.dumps(["name", "docstatus"]),
                "filters": json.dumps([["remarks", "=", remarks]]),
                "limit_page_length": "1",
            }
        )
        url = f"{self._credentials.base_url}/api/resource/Stock%20Entry?{query}"
        request = Request(
            url,
            headers={
                "Authorization": (
                    f"token {self._credentials.api_key}:{self._credentials.api_secret}"
                ),
                "Accept": "application/json",
                "User-Agent": "TheMissing20/0.1 read-only evidence adapter",
            },
        )
        payload = json.loads(self._transport(request, self._timeout_seconds).decode("utf-8"))
        rows = payload.get("data") if isinstance(payload, Mapping) else None
        if not isinstance(rows, list) or not rows or not isinstance(rows[0], Mapping):
            return None
        name = str(rows[0].get("name", "")).strip()
        if not name:
            return None
        transfer = self._get_document("Stock Entry", name)
        if transfer.get("remarks") != remarks or transfer.get("docstatus") != 1:
            return None
        return transfer

    def _find_value_chain(
        self,
    ) -> tuple[Mapping[str, Any] | None, Mapping[str, Any] | None, Mapping[str, Any] | None]:
        """Read the live customer order and its linked delivery/billing documents.

        The order is located by the customer's external PO number, not by a
        locally invented document id. Child-row references provide the exact
        Delivery Note and Sales Invoice links used by ERPNext itself.
        """

        if not self._customer_purchase_order:
            return None, None, None
        orders = self._get_rows(
            "Sales Order",
            fields=["name"],
            filters=[["po_no", "=", self._customer_purchase_order]],
            limit=1,
        )
        if not orders or not orders[0].get("name"):
            return None, None, None
        order = self._get_document("Sales Order", str(orders[0]["name"]))
        order_name = str(order.get("name", ""))

        def linked(
            parent_doctype: str,
            remarks: str,
            link_field: str,
        ) -> Mapping[str, Any] | None:
            # Frappe blocks direct REST list access to child-table doctypes for
            # this least-privilege user and disallows filtering a long-text
            # remarks field. Bound the parent search to the exact customer, then
            # prove both the idempotency tag and Sales Order child relationship.
            rows = self._get_rows(
                parent_doctype,
                fields=["name"],
                filters=[["customer", "=", order.get("customer")], ["docstatus", "=", 1]],
                limit=20,
            )
            relationship_match: Mapping[str, Any] | None = None
            for row in rows:
                parent = str(row.get("name", ""))
                if not parent:
                    continue
                document = self._get_document(parent_doctype, parent)
                linked_to_order = any(
                    str(item.get(link_field, "")) == order_name for item in self._items(document)
                )
                if not linked_to_order:
                    continue
                # The Sales Order mapper can omit ``remarks`` on a Delivery
                # Note even when the caller supplied it.  ERPNext's child-row
                # relationship is authoritative; keep it as a bounded fallback
                # while preferring the idempotency tag when the provider stores
                # one (as Sales Invoice currently does).
                if document.get("remarks") == remarks:
                    return document
                relationship_match = relationship_match or document
            return relationship_match

        delivery = linked(
            "Delivery Note",
            f"M20 DEMO customer delivery {self._case_id}",
            "against_sales_order",
        )
        invoice = linked(
            "Sales Invoice",
            f"M20 DEMO customer billing {self._case_id}",
            "sales_order",
        )
        return order, delivery, invoice

    @staticmethod
    def _items(document: Mapping[str, Any]) -> list[Mapping[str, Any]]:
        raw = document.get("items")
        return [item for item in raw if isinstance(item, Mapping)] if isinstance(raw, list) else []

    def current(self) -> dict[str, object]:
        """Share one observed snapshot across UI polls; respect provider cooldowns."""
        with self._read_lock:
            if self._cached is not None and self._clock() < max(
                self._cache_until, self._retry_not_before
            ):
                return deepcopy(self._cached)
            self._cached = self._read_current()
            self._cache_until = self._clock() + self._cache_seconds
            return deepcopy(self._cached)

    def invalidate_cache(self) -> None:
        """Require a fresh write-boundary read without bypassing a provider's backoff."""
        with self._read_lock:
            self._cache_until = 0

    def _read_current(self) -> dict[str, object]:
        """Return an API-safe evidence projection or a safe degraded state."""

        now = datetime.now(UTC)
        base: dict[str, object] = {
            "schema_version": ERP_NEXT_SCHEMA_VERSION,
            "source_id": "erpnext-missing20",
            "case_id": self._case_id,
            "configured_document_names": {
                "purchase_order": self._purchase_order,
                "purchase_receipt": self._purchase_receipt,
                "purchase_invoice": self._purchase_invoice,
            },
            "provider": "ERPNext / Frappe Cloud",
            "read_only": True,
        }
        if self._credentials is None:
            return self._finalize(
                {
                    **base,
                    "status": "NOT_CONFIGURED",
                    "documents": [],
                    "activity": [],
                },
                now,
            )
        try:
            # These documents are independent read-only facts. Fetch them in
            # parallel so one slow provider round trip does not turn the first
            # dashboard paint into the sum of four network latencies.
            with ThreadPoolExecutor(max_workers=5, thread_name_prefix="m20-erp-read") as pool:
                po_future = pool.submit(self._get_document, "Purchase Order", self._purchase_order)
                receipt_future = pool.submit(
                    self._optional_document, "Purchase Receipt", self._purchase_receipt
                )
                invoice_future = pool.submit(
                    self._optional_document, "Purchase Invoice", self._purchase_invoice
                )
                recovery_future = pool.submit(self._find_recovery_transfer)
                value_future = pool.submit(self._find_value_chain)
                po = po_future.result()
                receipt = receipt_future.result()
                invoice = invoice_future.result()
                recovery_transfer = recovery_future.result()
                sales_order, delivery_note, sales_invoice = value_future.result()
            receipts = self._purchase_documents(po, "Purchase Receipt", receipt)
            invoices = self._purchase_documents(po, "Purchase Invoice", invoice)
            receipt = next(
                (row for row in receipts if row.get("name") == self._purchase_receipt),
                receipts[0] if receipts else {},
            )
            invoice = next(
                (row for row in invoices if row.get("name") == self._purchase_invoice),
                invoices[0] if invoices else {},
            )
        except (OSError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as error:
            rate_limited = isinstance(error, HTTPError) and error.code == 429
            if isinstance(error, HTTPError) and error.code == 429:
                raw_delay = error.headers.get("Retry-After", "60") if error.headers else "60"
                try:
                    delay = max(30.0, float(raw_delay))
                    if not math.isfinite(delay):
                        delay = 60.0
                except ValueError:
                    try:
                        delay = max(30.0, (parsedate_to_datetime(raw_delay) - now).total_seconds())
                    except (TypeError, ValueError, OverflowError):
                        delay = 60.0
                self._retry_not_before = self._clock() + delay
            return self._finalize(
                {
                    **base,
                    "status": "DEGRADED",
                    "documents": [],
                    "activity": [],
                    "read_error": {
                        "code": "RATE_LIMITED" if rate_limited else "SOURCE_READ_FAILED"
                    },
                },
                now,
            )

        po_items = self._items(po)
        receipt_items = self._items(receipt)
        invoice_items = self._items(invoice)
        received = sum(float(item.get("received_qty") or 0) for item in receipt_items)
        accepted = sum(float(item.get("qty") or 0) for item in receipt_items)
        rejected = sum(float(item.get("rejected_qty") or 0) for item in receipt_items)
        quantity = sum(float(item.get("qty") or 0) for item in po_items)
        po_line_value = sum(float(item.get("amount") or 0) for item in po_items)
        if not po_line_value:
            po_line_value = sum(
                float(item.get("qty") or 0) * float(item.get("rate") or 0) for item in po_items
            )
        po_unit_rate = po_line_value / quantity if quantity else 0.0
        held = bool(invoice.get("on_hold"))
        transfer_items = self._items(recovery_transfer) if recovery_transfer else []
        transfer_quantity = sum(float(item.get("qty") or 0) for item in transfer_items)
        remaining_quality_hold = max(0.0, rejected - transfer_quantity)
        transfer_source = next(
            (
                str(item.get("s_warehouse", ""))
                for item in transfer_items
                if item.get("s_warehouse")
            ),
            "",
        )
        transfer_target = next(
            (
                str(item.get("t_warehouse", ""))
                for item in transfer_items
                if item.get("t_warehouse")
            ),
            "",
        )
        ledger_evidence = self._ledger_evidence(
            purchase_receipt=str(receipt.get("name", "")),
            purchase_invoice=str(invoice.get("name", "")),
            recovery_transfer=str(recovery_transfer.get("name", "")) if recovery_transfer else "",
            delivery_note=str(delivery_note.get("name", "")) if delivery_note else "",
            sales_invoice=str(sales_invoice.get("name", "")) if sales_invoice else "",
            additional_purchase_documents=[
                str(row["name"])
                for row in [*receipts, *invoices]
                if row.get("name") not in {receipt.get("name"), invoice.get("name")}
            ],
        )
        documents: list[dict[str, Any]] = [
            {
                "kind": "purchase_order",
                "name": str(po.get("name", "")),
                "status": "SUBMITTED" if po.get("docstatus") == 1 else "DRAFT",
                "quantity": quantity,
                "supplier": str(po.get("supplier", "")),
                "unit_rate": po_unit_rate,
                "line_value": po_line_value,
                "currency": str(po.get("currency") or ""),
            },
            {
                "kind": "purchase_receipt",
                "name": str(receipt.get("name", "")),
                "status": (
                    "PARTIAL_QUALITY_HOLD"
                    if remaining_quality_hold
                    else "RELEASED_AFTER_QUALITY_HOLD"
                    if rejected and recovery_transfer
                    else "RECEIVED"
                ),
                "delivery_note": str(receipt.get("supplier_delivery_note", "")),
                "received": received,
                "accepted": accepted,
                "rejected": rejected,
                "quality_hold_remaining": remaining_quality_hold,
                "quality_hold_warehouse": next(
                    (
                        str(item.get("rejected_warehouse", ""))
                        for item in receipt_items
                        if item.get("rejected_warehouse")
                    ),
                    "",
                ),
            },
            {
                "kind": "purchase_invoice",
                "name": str(invoice.get("name", "")),
                "status": "PAYMENT_HOLD" if held else "OPEN",
                "bill_no": str(invoice.get("bill_no", "")),
                "on_hold": held,
                "hold_comment": str(invoice.get("hold_comment", "")),
                "grand_total": float(invoice.get("grand_total") or 0),
                "currency": str(invoice.get("currency") or ""),
                "linked_receipts": sorted(
                    {
                        str(item.get("purchase_receipt", ""))
                        for item in invoice_items
                        if item.get("purchase_receipt")
                    }
                ),
            },
            *(
                [
                    {
                        "kind": "quality_release_transfer",
                        "name": str(recovery_transfer.get("name", "")),
                        "status": "SUBMITTED",
                        "quantity": transfer_quantity,
                        "source_warehouse": transfer_source,
                        "target_warehouse": transfer_target,
                    }
                ]
                if recovery_transfer
                else []
            ),
            *(
                [
                    {
                        "kind": "sales_order",
                        "name": str(sales_order.get("name", "")),
                        "status": str(sales_order.get("status", "")),
                        "customer": str(
                            sales_order.get("customer_name") or sales_order.get("customer") or ""
                        ),
                        "customer_purchase_order": str(sales_order.get("po_no", "")),
                        "quantity": float(sales_order.get("total_qty") or 0),
                        "booked_value": float(sales_order.get("grand_total") or 0),
                        "currency": str(sales_order.get("currency") or ""),
                        "delivered_percent": float(sales_order.get("per_delivered") or 0),
                        "billed_percent": float(sales_order.get("per_billed") or 0),
                        "delivery_date": str(sales_order.get("delivery_date", "")),
                    }
                ]
                if sales_order
                else []
            ),
            *(
                [
                    {
                        "kind": "delivery_note",
                        "name": str(delivery_note.get("name", "")),
                        "status": "SUBMITTED" if delivery_note.get("docstatus") == 1 else "DRAFT",
                        "customer": str(
                            delivery_note.get("customer_name")
                            or delivery_note.get("customer")
                            or ""
                        ),
                        "quantity": float(delivery_note.get("total_qty") or 0),
                        "value": float(delivery_note.get("grand_total") or 0),
                        "currency": str(delivery_note.get("currency") or ""),
                    }
                ]
                if delivery_note
                else []
            ),
            *(
                [
                    {
                        "kind": "sales_invoice",
                        "name": str(sales_invoice.get("name", "")),
                        "status": "SUBMITTED" if sales_invoice.get("docstatus") == 1 else "DRAFT",
                        "customer": str(
                            sales_invoice.get("customer_name")
                            or sales_invoice.get("customer")
                            or ""
                        ),
                        "quantity": float(sales_invoice.get("total_qty") or 0),
                        "billed_revenue": sales_invoice.get("net_total"),
                        "billed_amount": sales_invoice.get("grand_total"),
                        "outstanding_amount": float(sales_invoice.get("outstanding_amount") or 0),
                        "currency": str(sales_invoice.get("currency") or ""),
                    }
                ]
                if sales_invoice
                else []
            ),
        ]
        source_documents = {
            str(row.get("name", "")): row
            for row in [
                po,
                receipt,
                invoice,
                recovery_transfer,
                sales_order,
                delivery_note,
                sales_invoice,
            ]
            if row
        }
        documents = [row for row in documents if row.get("name")]
        for row in documents:
            raw = source_documents[str(row["name"])]
            metadata = self._business_metadata(raw)
            if row["kind"] == "quality_release_transfer":
                metadata.pop("docstatus", None)  # already asserted submitted by the scoped finder
            row.update(metadata)
            if raw.get("docstatus") in (0, 2):
                row["status"] = "CANCELLED" if raw["docstatus"] == 2 else "DRAFT"
            if raw.get("case_scope_complete") is False and row["kind"] == "purchase_invoice":
                row["grand_total"] = None
                row["amount_status"] = "DOCUMENT_CONTAINS_OTHER_ORDERS"
        additional_documents = [
            self._purchase_summary(row, kind)
            for kind, rows, primary in (
                ("purchase_receipt", receipts, receipt),
                ("purchase_invoice", invoices, invoice),
            )
            for row in rows
            if row.get("name") != primary.get("name")
        ]
        documents.extend(additional_documents)
        activity: list[dict[str, Any]] = [
            {
                "id": f"erp-po-{po.get('name', '')}",
                "source_id": "erpnext-missing20",
                "provider": "ERPNext / Frappe Cloud",
                "occurred_at": now.isoformat(),
                "status": "VERIFIED",
                "label": f"ERP read · purchase order {po.get('name', '')}",
                "detail": f"Purchase order from {po.get('supplier', '')}",
            },
            {
                "id": f"erp-receipt-{receipt.get('name', '')}",
                "source_id": "erpnext-missing20",
                "provider": "ERPNext / Frappe Cloud",
                "occurred_at": now.isoformat(),
                "status": "HELD" if remaining_quality_hold else "VERIFIED",
                "label": f"ERP read · receipt {receipt.get('name', '')}",
                "detail": (
                    f"{accepted:g} accepted · {rejected:g} originally held · "
                    f"{remaining_quality_hold:g} remain · {received:g} received"
                    if transfer_quantity
                    else f"{accepted:g} accepted · {rejected:g} in Quality Hold · "
                    f"{received:g} received"
                ),
            },
            {
                "id": f"erp-invoice-{invoice.get('name', '')}",
                "source_id": "erpnext-missing20",
                "provider": "ERPNext / Frappe Cloud",
                "occurred_at": now.isoformat(),
                "status": "HELD" if held else "VERIFIED",
                "label": f"ERP read · invoice {invoice.get('name', '')}",
                "detail": "Payment hold confirmed" if held else "Invoice is not held",
            },
            *(
                [
                    {
                        "id": f"erp-transfer-{recovery_transfer.get('name', '')}",
                        "source_id": "erpnext-missing20",
                        "provider": "ERPNext / Frappe Cloud",
                        "occurred_at": now.isoformat(),
                        "status": "VERIFIED",
                        "label": (
                            "ERP read · verified quality release "
                            f"{recovery_transfer.get('name', '')}"
                        ),
                        "detail": (
                            f"{transfer_quantity:g} moved from {transfer_source} "
                            f"to {transfer_target}"
                        ),
                    }
                ]
                if recovery_transfer
                else []
            ),
            *(
                [
                    {
                        "id": f"erp-sales-order-{sales_order.get('name', '')}",
                        "source_id": "erpnext-missing20",
                        "provider": "ERPNext / Frappe Cloud",
                        "occurred_at": now.isoformat(),
                        "status": "HELD" if sales_order.get("status") == "On Hold" else "VERIFIED",
                        "label": f"ERP read · customer order {sales_order.get('name', '')}",
                        "detail": (
                            f"{float(sales_order.get('total_qty') or 0):g} units · "
                            f"{sales_order.get('currency', 'USD')} "
                            f"{float(sales_order.get('grand_total') or 0):,.0f} · "
                            f"{sales_order.get('status', '')}"
                        ),
                    }
                ]
                if sales_order
                else []
            ),
            *(
                [
                    {
                        "id": f"erp-delivery-{delivery_note.get('name', '')}",
                        "source_id": "erpnext-missing20",
                        "provider": "ERPNext / Frappe Cloud",
                        "occurred_at": now.isoformat(),
                        "status": "VERIFIED",
                        "label": f"ERP read · delivery {delivery_note.get('name', '')}",
                        "detail": (
                            f"{float(delivery_note.get('total_qty') or 0):g} units "
                            "posted from the customer order"
                        ),
                    }
                ]
                if delivery_note
                else []
            ),
            *(
                [
                    {
                        "id": f"erp-sales-invoice-{sales_invoice.get('name', '')}",
                        "source_id": "erpnext-missing20",
                        "provider": "ERPNext / Frappe Cloud",
                        "occurred_at": now.isoformat(),
                        "status": "VERIFIED",
                        "label": f"ERP read · customer invoice {sales_invoice.get('name', '')}",
                        "detail": (
                            f"Billed {sales_invoice.get('currency', 'USD')} "
                            f"{float(sales_invoice.get('grand_total') or 0):,.0f} "
                            "from the verified order"
                        ),
                    }
                ]
                if sales_invoice
                else []
            ),
        ]
        activity = [row for row in activity if not str(row["id"]).endswith("-")]
        activity.extend(
            {
                "id": f"erp-{row['kind']}-{row['name']}",
                "source_id": "erpnext-missing20",
                "provider": "ERPNext / Frappe Cloud",
                "occurred_at": now.isoformat(),
                "status": row.get("status", "UNKNOWN"),
                "label": f"ERP read · {str(row['kind']).replace('_', ' ')} {row['name']}",
                "detail": "Additional document linked to this purchase order",
            }
            for row in additional_documents
        )
        return self._finalize(
            {
                **base,
                "case_id": self._case_id,
                "status": "CONNECTED",
                "documents": documents,
                "primary_document_names": {
                    kind: str(document.get("name", ""))
                    for kind, document in (
                        ("purchase_order", po),
                        ("purchase_receipt", receipt),
                        ("purchase_invoice", invoice),
                        ("quality_release_transfer", recovery_transfer),
                        ("sales_order", sales_order),
                        ("delivery_note", delivery_note),
                        ("sales_invoice", sales_invoice),
                    )
                    if document
                },
                "ledger_evidence": ledger_evidence,
                "document_lifecycle": {
                    "purchase_order": "PRESENT",
                    "purchase_receipt": "PRESENT" if receipts else "AWAITING_RECEIPT",
                    "purchase_invoice": "PRESENT" if invoices else "AWAITING_INVOICE",
                },
                "purchase_scope": "ALL_LINKED_DOCUMENTS"
                if self._discover_purchase_documents
                else "CONFIGURED_DOCUMENTS",
                "activity": activity,
            },
            now,
        )
