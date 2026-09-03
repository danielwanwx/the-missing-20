"""Read-only ERPNext evidence adapter for the live competition demo.

The adapter deliberately exposes a narrow, case-scoped projection.  Browser
clients never receive credentials and this process never mutates ERPNext; all
writes are performed by the separate, explicit seed script.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

ERP_NEXT_SCHEMA_VERSION = "missing20-erpnext-evidence/v1"
DEFAULT_PO = "PUR-ORD-2026-00011"
DEFAULT_RECEIPT = "MAT-PRE-2026-00001"
DEFAULT_INVOICE = "ACC-PINV-2026-00007"
DEFAULT_CASE_ID = "M20-ECU-2026-00011-LOT-A"


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
    ) -> None:
        self._credentials = credentials
        self._transport = transport or self._default_transport
        self._timeout_seconds = timeout_seconds
        self._purchase_order = purchase_order
        self._purchase_receipt = purchase_receipt
        self._purchase_invoice = purchase_invoice
        self._case_id = case_id
        self._sequence = 0

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
            case_id=values.get("MISSING20_CASE_ID", DEFAULT_CASE_ID),
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
        return document

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

    @staticmethod
    def _items(document: Mapping[str, Any]) -> list[Mapping[str, Any]]:
        raw = document.get("items")
        return [item for item in raw if isinstance(item, Mapping)] if isinstance(raw, list) else []

    def current(self) -> dict[str, object]:
        """Return an API-safe evidence projection or a safe degraded state."""

        now = datetime.now(UTC)
        self._sequence += 1
        base: dict[str, object] = {
            "schema_version": ERP_NEXT_SCHEMA_VERSION,
            "source_id": "erpnext-missing20",
            "provider": "ERPNext / Frappe Cloud",
            "read_only": True,
            "sequence": self._sequence,
            "received_at": now.isoformat(),
        }
        if self._credentials is None:
            return {
                **base,
                "status": "NOT_CONFIGURED",
                "documents": [],
                "activity": [],
            }
        try:
            po = self._get_document("Purchase Order", self._purchase_order)
            receipt = self._get_document("Purchase Receipt", self._purchase_receipt)
            invoice = self._get_document("Purchase Invoice", self._purchase_invoice)
            recovery_transfer = self._find_recovery_transfer()
        except (OSError, URLError, TimeoutError, ValueError, json.JSONDecodeError):
            return {
                **base,
                "status": "DEGRADED",
                "documents": [],
                "activity": [],
            }

        po_items = self._items(po)
        receipt_items = self._items(receipt)
        invoice_items = self._items(invoice)
        received = sum(float(item.get("received_qty") or 0) for item in receipt_items)
        accepted = sum(float(item.get("qty") or 0) for item in receipt_items)
        rejected = sum(float(item.get("rejected_qty") or 0) for item in receipt_items)
        quantity = sum(float(item.get("qty") or 0) for item in po_items)
        held = bool(invoice.get("on_hold"))
        transfer_items = self._items(recovery_transfer) if recovery_transfer else []
        transfer_quantity = sum(float(item.get("qty") or 0) for item in transfer_items)
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
        documents = [
            {
                "kind": "purchase_order",
                "name": str(po.get("name", "")),
                "status": "SUBMITTED" if po.get("docstatus") == 1 else "DRAFT",
                "quantity": quantity,
                "supplier": str(po.get("supplier", "")),
            },
            {
                "kind": "purchase_receipt",
                "name": str(receipt.get("name", "")),
                "status": "PARTIAL_QUALITY_HOLD" if rejected else "RECEIVED",
                "delivery_note": str(receipt.get("supplier_delivery_note", "")),
                "received": received,
                "accepted": accepted,
                "rejected": rejected,
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
        ]
        activity = [
            {
                "id": f"erp-po-{po.get('name', '')}",
                "source_id": "erpnext-missing20",
                "provider": "ERPNext / Frappe Cloud",
                "occurred_at": now.isoformat(),
                "status": "VERIFIED",
                "label": f"ERP read · purchase order {po.get('name', '')}",
                "detail": f"{quantity:g} ECU controllers ordered from {po.get('supplier', '')}",
            },
            {
                "id": f"erp-receipt-{receipt.get('name', '')}",
                "source_id": "erpnext-missing20",
                "provider": "ERPNext / Frappe Cloud",
                "occurred_at": now.isoformat(),
                "status": "HELD" if rejected else "VERIFIED",
                "label": f"ERP read · receipt {receipt.get('name', '')}",
                "detail": (
                    f"{accepted:g} accepted · {rejected:g} in Quality Hold · {received:g} received"
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
        ]
        return {**base, "status": "CONNECTED", "documents": documents, "activity": activity}
