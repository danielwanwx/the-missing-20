"""Narrow, idempotent ERPNext executor for the isolated M20 demo tenant.

This adapter is intentionally not a general ERP client.  It can release a
validated M20 quality hold only after the Agent has produced a guarded plan.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from the_missing_20.adapters.erpnext_source import ERPNextCredentials
from the_missing_20.adapters.erpnext_source import _read_env_file


class DemoExecutionBlocked(ValueError):
    """Raised when a request falls outside the dedicated demo tenant."""


@dataclass(frozen=True, slots=True)
class DemoReleasePlan:
    case_id: str
    purchase_receipt: str
    purchase_invoice: str
    quantity: float
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class DemoExecutionResult:
    transfer_name: str
    invoice_name: str
    idempotent: bool
    verified: bool


class ERPNextDemoExecutor:
    """Perform exactly one material transfer and one invoice unblock per case."""

    def __init__(
        self,
        credentials: ERPNextCredentials,
        *,
        environment: str,
        transport: Callable[[Request, float], bytes] | None = None,
        timeout_seconds: float = 8.0,
    ) -> None:
        self._credentials = credentials
        self._environment = environment.strip().lower()
        self._transport = transport or self._default_transport
        self._timeout_seconds = timeout_seconds

    @classmethod
    def from_environment(cls, repository_root: Path) -> ERPNextDemoExecutor | None:
        values = {**_read_env_file(repository_root / ".env"), **os.environ}
        credentials = ERPNextCredentials(
            base_url=values.get("ERPNEXT_BASE_URL", "").rstrip("/"),
            api_key=values.get("ERPNEXT_API_KEY", ""),
            api_secret=values.get("ERPNEXT_API_SECRET", ""),
        )
        if not all((credentials.base_url, credentials.api_key, credentials.api_secret)):
            return None
        return cls(credentials, environment=values.get("MISSING20_ENVIRONMENT", "local"))

    @staticmethod
    def _default_transport(request: Request, timeout: float) -> bytes:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - configured HTTPS endpoint
            return bytes(response.read())

    def _request(self, path: str, *, method: str = "GET", payload: object | None = None) -> Any:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(
            f"{self._credentials.base_url.rstrip('/')}{path}",
            data=data,
            method=method,
            headers={
                "Authorization": f"token {self._credentials.api_key}:{self._credentials.api_secret}",
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "TheMissing20/0.1 demo-guarded-executor",
            },
        )
        return json.loads(self._transport(request, self._timeout_seconds).decode("utf-8"))

    def _document(self, doctype: str, name: str) -> Mapping[str, Any]:
        payload = self._request(f"/api/resource/{quote(doctype, safe='')}/{quote(name, safe='')}")
        document = payload.get("data") if isinstance(payload, Mapping) else None
        if not isinstance(document, Mapping):
            raise DemoExecutionBlocked(f"ERPNext returned no {doctype} document")
        return document

    @staticmethod
    def _m20_text(value: object) -> bool:
        return "M20" in str(value).upper()

    def _validate(self, plan: DemoReleasePlan, receipt: Mapping[str, Any], invoice: Mapping[str, Any]) -> None:
        if self._environment != "demo":
            raise DemoExecutionBlocked("provider writes require MISSING20_ENVIRONMENT=demo")
        if not plan.case_id.startswith("M20-") or not plan.idempotency_key.startswith("m20-"):
            raise DemoExecutionBlocked("case and idempotency key must be M20-scoped")
        if receipt.get("docstatus") != 1 or invoice.get("docstatus") != 1:
            raise DemoExecutionBlocked("only submitted M20 demo documents may be released")
        if not self._m20_text(receipt.get("supplier_delivery_note")):
            raise DemoExecutionBlocked("receipt is not an M20 demo resource")
        if not self._m20_text(invoice.get("hold_comment")):
            raise DemoExecutionBlocked("invoice is not an M20 demo resource")

    @staticmethod
    def _transfer_item(receipt: Mapping[str, Any], requested_quantity: float) -> Mapping[str, Any]:
        items = receipt.get("items")
        if not isinstance(items, list):
            raise DemoExecutionBlocked("receipt has no item rows")
        matching = next(
            (
                item
                for item in items
                if isinstance(item, Mapping)
                and float(item.get("rejected_qty") or 0) == requested_quantity
                and item.get("rejected_warehouse")
                and item.get("warehouse")
                and str(item.get("item_code", "")).startswith("M20-")
            ),
            None,
        )
        if not isinstance(matching, Mapping):
            raise DemoExecutionBlocked("requested release quantity is not a held M20 receipt row")
        return matching

    def _existing_transfer(self, plan: DemoReleasePlan) -> str:
        filters = [["remarks", "=", f"M20 DEMO release {plan.case_id}"]]
        query = urlencode({"fields": json.dumps(["name"]), "filters": json.dumps(filters)})
        payload = self._request(f"/api/resource/Stock%20Entry?{query}")
        rows = payload.get("data") if isinstance(payload, Mapping) else None
        if isinstance(rows, list) and rows and isinstance(rows[0], Mapping):
            return str(rows[0].get("name", ""))
        return ""

    def _warehouse_company(self, warehouse: object) -> str:
        document = self._document("Warehouse", str(warehouse))
        company = str(document.get("company") or "").strip()
        if not company:
            raise DemoExecutionBlocked("M20 warehouse does not have an owning company")
        return company

    def _submit_transfer(self, plan: DemoReleasePlan, item: Mapping[str, Any]) -> str:
        source_company = self._warehouse_company(item["rejected_warehouse"])
        target_company = self._warehouse_company(item["warehouse"])
        if source_company != target_company:
            raise DemoExecutionBlocked("M20 transfer warehouses belong to different companies")
        draft = self._request(
            "/api/resource/Stock%20Entry",
            method="POST",
            payload={
                "doctype": "Stock Entry",
                "stock_entry_type": "Material Transfer",
                "company": source_company,
                "remarks": f"M20 DEMO release {plan.case_id}",
                "items": [
                    {
                        "doctype": "Stock Entry Detail",
                        "item_code": item["item_code"],
                        "qty": plan.quantity,
                        "uom": item.get("uom") or "Nos",
                        "stock_uom": item.get("stock_uom") or "Nos",
                        "s_warehouse": item["rejected_warehouse"],
                        "t_warehouse": item["warehouse"],
                        "basic_rate": item.get("valuation_rate") or item.get("rate") or 0,
                        "allow_zero_valuation_rate": 1,
                    }
                ],
            },
        )
        document = draft.get("data") if isinstance(draft, Mapping) else None
        if not isinstance(document, Mapping) or not document.get("name"):
            raise DemoExecutionBlocked("ERPNext did not create a transfer draft")
        return self._submit_document(document)

    def _submit_document(self, document: Mapping[str, Any]) -> str:
        """Submit an existing M20 transfer and require an explicit submitted read."""

        submitted = self._request(
            "/api/method/frappe.client.submit", method="POST", payload={"doc": document}
        )
        result = submitted.get("message") if isinstance(submitted, Mapping) else None
        if not isinstance(result, Mapping) or not result.get("name"):
            raise DemoExecutionBlocked("ERPNext did not submit the transfer")
        return str(result["name"])

    def _discard_unsubmitted_transfer(self, name: str, plan: DemoReleasePlan) -> None:
        """Remove only our exact unsubmitted, invalid draft before retrying safely."""

        document = self._document("Stock Entry", name)
        if (
            document.get("docstatus") != 0
            or document.get("remarks") != f"M20 DEMO release {plan.case_id}"
        ):
            raise DemoExecutionBlocked("existing transfer is not the exact unsubmitted M20 draft")
        self._request(
            f"/api/resource/Stock%20Entry/{quote(name, safe='')}",
            method="DELETE",
        )

    def _unblock_invoice(self, invoice_name: str) -> None:
        self._request(
            "/api/method/run_doc_method",
            method="POST",
            payload={
                "dt": "Purchase Invoice",
                "dn": invoice_name,
                "method": "unblock_invoice",
                "args": {},
            },
        )

    def execute(self, plan: DemoReleasePlan) -> DemoExecutionResult:
        receipt = self._document("Purchase Receipt", plan.purchase_receipt)
        invoice = self._document("Purchase Invoice", plan.purchase_invoice)
        self._validate(plan, receipt, invoice)
        item = self._transfer_item(receipt, plan.quantity)
        existing = self._existing_transfer(plan)
        if existing:
            existing_document = self._document("Stock Entry", existing)
            if existing_document.get("docstatus") == 1:
                transfer_name = existing
            else:
                self._discard_unsubmitted_transfer(existing, plan)
                transfer_name = self._submit_transfer(plan, item)
        else:
            transfer_name = self._submit_transfer(plan, item)
        if invoice.get("on_hold"):
            self._unblock_invoice(plan.purchase_invoice)
        verified_transfer = self._document("Stock Entry", transfer_name)
        verified_invoice = self._document("Purchase Invoice", plan.purchase_invoice)
        verified = verified_transfer.get("docstatus") == 1 and not bool(verified_invoice.get("on_hold"))
        return DemoExecutionResult(
            transfer_name=transfer_name,
            invoice_name=plan.purchase_invoice,
            idempotent=bool(existing),
            verified=verified,
        )
