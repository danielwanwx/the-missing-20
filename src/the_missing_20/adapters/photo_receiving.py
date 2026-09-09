"""Durable photo intake and fail-closed ERP draft preparation for a demo PO."""

from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import math
import re
import sqlite3
import threading
import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

from the_missing_20.adapters.demo_executor import DemoExecutionBlocked, ERPNextDemoExecutor
from the_missing_20.adapters.receiving_arrivals import ReceivingArrivals
from the_missing_20.agents.photo_receiving import PhotoAssessment, normalize_photo

COUNT_SEMANTICS = "Each capture is a replacement observation, never an additive batch."
MAX_STORED_PHOTO_BYTES = 100_000_000
# StrandsPhotoReader has a hard 75-second deadline. This small persisted grace
# distinguishes an in-flight owner from a process that cannot finish its claim.
ANALYSIS_LEASE_SECONDS = 90
COMMERCIAL_FIELDS = (
    "currency",
    "conversion_rate",
    "buying_price_list",
    "price_list_currency",
    "plc_conversion_rate",
    "taxes_and_charges",
    "tc_name",
    "terms",
    "payment_terms_template",
    "incoterm",
    "named_place",
    "supplier_address",
    "shipping_address",
    "contact_person",
    "project",
    "additional_discount_percentage",
    "apply_discount_on",
)
TAX_FIELDS = (
    "charge_type",
    "account_head",
    "description",
    "rate",
    "row_id",
    "cost_center",
    "included_in_print_rate",
    "included_in_paid_amount",
    "category",
    "add_deduct_tax",
)
ITEM_COMMERCIAL_FIELDS = ("item_tax_template", "item_tax_rate", "expense_account", "cost_center")


def _provider_failure(error: Exception, operation: str) -> dict[str, Any]:
    """Keep an actionable category, never provider bodies, URLs or credentials."""
    code = "UNCONFIRMED"
    status = None
    if isinstance(error, DemoExecutionBlocked):
        match = re.search(r"\((\d{3})\):", str(error))
        status = int(match[1]) if match else None
        if status in (401, 403):
            code = "ACCESS_DENIED"
        elif status == 429:
            code = "RATE_LIMITED"
        elif status in (400, 409, 417, 422):
            code = "VALIDATION_REJECTED"
    return {
        "operation": operation,
        "code": code,
        "http_status": status,
        "effect": "UNKNOWN",
        "observed_at": datetime.now(UTC).isoformat(),
    }


def _analysis_claim_is_active(state: Mapping[str, Any]) -> bool:
    claim = state.get("analysis_claim")
    if (
        not isinstance(claim, Mapping)
        or not isinstance(claim.get("owner"), str)
        or not claim["owner"]
        or not isinstance(claim.get("expires_at"), str)
    ):
        return False
    try:
        expires_at = datetime.fromisoformat(claim["expires_at"])
    except ValueError:
        return False
    return expires_at.tzinfo is not None and expires_at > datetime.now(UTC)


def _positive(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"PO {field} must be an authoritative finite positive number.")
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"PO {field} must be an authoritative finite positive number.")
    return float(value)


def _commercial_fields(po: Mapping[str, Any]) -> dict[str, Any]:
    """Copy commercial inputs, never whole-order totals into a partial receipt."""
    fields = {key: po[key] for key in COMMERCIAL_FIELDS if po.get(key) not in (None, "")}
    for key in ("conversion_rate", "plc_conversion_rate"):
        if key in fields:
            _positive(fields[key], key)
    discount_percentage = po.get("additional_discount_percentage") or 0
    if discount_percentage:
        if _positive(discount_percentage, "discount percentage") > 100:
            raise ValueError("PO discount percentage is invalid.")
    elif po.get("discount_amount"):
        raise ValueError("PO fixed discount allocation requires native ERP/manual review.")
    taxes = []
    for row in po.get("taxes") or []:
        # A whole-order fixed charge cannot safely be assigned to this photographed subset.
        if row.get("charge_type") not in {
            "On Net Total",
            "On Previous Row Amount",
            "On Previous Row Total",
            "On Item Quantity",
        }:
            raise ValueError("PO tax allocation requires native ERP/manual review.")
        rate = row.get("rate")
        if (
            isinstance(rate, bool)
            or not isinstance(rate, (int, float))
            or not math.isfinite(rate)
            or rate < 0
            or not row.get("account_head")
        ):
            raise ValueError("PO tax rate/account needs authoritative review.")
        taxes.append({key: row[key] for key in TAX_FIELDS if key in row})
    if taxes:
        fields["taxes"] = taxes
    return fields


class PhotoReceiptERP:
    """Configured demo transport; submission is a separate human-confirmed operation."""

    def __init__(self, client: ERPNextDemoExecutor, purchase_order: str) -> None:
        self.client = client
        self.purchase_order = purchase_order

    def candidate(self, assessment: PhotoAssessment) -> dict[str, Any]:
        po = self.client._document("Purchase Order", self.purchase_order)
        rows = [
            item for item in po.get("items", []) if item.get("item_code") == assessment.item_code
        ]
        if (
            po.get("name") != self.purchase_order
            or po.get("docstatus") != 1
            or not po.get("modified")
            or len(rows) != 1
        ):
            raise ValueError(
                "Photo identity does not match one submitted PO line. Photograph its SKU."
            )
        item = rows[0]
        count = len(assessment.objects)
        if count <= 0:
            raise ValueError("A receipt requires a positive observed quantity.")
        if not str(item.get("item_code", "")).startswith("M20-"):
            raise ValueError("Only the isolated M20 demo item is eligible.")
        receiving_uoms = {"piece": {"Nos", "Each", "Unit"}, "carton": {"Carton", "Box"}}
        if (
            item.get("uom") not in receiving_uoms.get(assessment.receiving_unit, set())
            or item.get("stock_uom") != item.get("uom")
            or float(item.get("conversion_factor") or 0) != 1
        ):
            raise ValueError("Photo receiving unit cannot be converted to the PO unit safely.")
        remaining = float(item.get("qty") or 0) - float(item.get("received_qty") or 0)
        if not math.isfinite(remaining) or count > remaining or not item.get("warehouse"):
            raise ValueError("PO remaining quantity or receiving warehouse needs review.")
        _positive(item.get("rate"), "rate")
        return {
            "doctype": "Purchase Receipt",
            "company": po["company"],
            "supplier": po["supplier"],
            "purchase_order": self.purchase_order,
            "po_version": po.get("modified"),
            "quantity": count,
            **_commercial_fields(po),
            "items": [
                {
                    "item_code": item["item_code"],
                    "qty": count,
                    "uom": item["uom"],
                    "stock_uom": item["stock_uom"],
                    "conversion_factor": 1,
                    "rate": item["rate"],
                    "warehouse": item["warehouse"],
                    "purchase_order": self.purchase_order,
                    "purchase_order_item": item["name"],
                    **{key: item[key] for key in ITEM_COMMERCIAL_FIELDS if item.get(key)},
                }
            ],
        }

    def draft(
        self, candidate: dict[str, Any], key: str, *, lookup_only: bool = False
    ) -> dict[str, Any]:
        if self.client._environment != "demo":
            raise ValueError("Photo receipt drafts are restricted to the demo tenant.")
        marker = f"M20 PHOTO {key}"
        query = urlencode(
            {
                "fields": json.dumps(["name", "docstatus"]),
                "filters": json.dumps([["supplier_delivery_note", "=", marker]]),
                "limit_page_length": 2,
            }
        )
        found = self.client._request(f"/api/resource/Purchase%20Receipt?{query}").get("data")
        if not isinstance(found, list) or len(found) > 1:
            raise ValueError("Receipt lookup is ambiguous; reconcile before another write.")
        if found:
            doc = self.client._document("Purchase Receipt", found[0]["name"])
        else:
            if lookup_only:
                raise ValueError("Draft is still unconfirmed. No second write is permitted.")
            payload = {
                k: v
                for k, v in candidate.items()
                if k not in {"po_version", "quantity", "purchase_order"}
            }
            self.client._request(
                "/api/resource/Purchase%20Receipt",
                method="POST",
                payload={**payload, "docstatus": 0, "supplier_delivery_note": marker},
            )
            # Query by business key after the write, not only trust the POST response.
            found = self.client._request(f"/api/resource/Purchase%20Receipt?{query}").get("data")
            if not isinstance(found, list) or len(found) != 1:
                raise ValueError("ERP draft result is unknown; reconcile before retrying.")
            doc = self.client._document("Purchase Receipt", found[0]["name"])
        if doc.get("name") != found[0]["name"]:
            raise ValueError("ERP reread returned a different receipt identity.")
        self._verify_receipt(doc, candidate, key, docstatus=0)
        return {
            "name": doc["name"],
            "docstatus": 0,
            "modified": doc.get("modified"),
            "stock_posted": False,
            "url": self._url(str(doc["name"])),
            "verified_draft": True,
        }

    def _url(self, name: str) -> str:
        return f"{self.client._credentials.base_url}/app/purchase-receipt/{quote(name, safe='')}"

    @staticmethod
    def _verify_receipt(
        doc: Mapping[str, Any], candidate: dict[str, Any], key: str, *, docstatus: int
    ) -> None:
        lines = doc.get("items", [])
        expected = candidate["items"][0]
        if (
            doc.get("doctype") != "Purchase Receipt"
            or doc.get("docstatus") != docstatus
            or doc.get("supplier_delivery_note") != f"M20 PHOTO {key}"
            or any(doc.get(k) != candidate[k] for k in ("company", "supplier"))
            or doc.get("is_return", 0) not in (0, None)
            or doc.get("return_against")
            or len(lines) != 1
            or lines[0].get("rejected_qty", 0) not in (0, None)
            or any(
                lines[0].get(k) != expected[k]
                for k in (
                    "item_code",
                    "purchase_order",
                    "purchase_order_item",
                    "qty",
                    "warehouse",
                    "uom",
                    "stock_uom",
                    "conversion_factor",
                    "rate",
                )
            )
        ):
            raise ValueError("ERP reread does not match the requested draft.")
        if any(doc.get(key) != candidate[key] for key in COMMERCIAL_FIELDS if key in candidate):
            raise ValueError("ERP commercial terms do not match the authoritative PO.")
        if any(
            lines[0].get(key) != expected[key] for key in ITEM_COMMERCIAL_FIELDS if key in expected
        ):
            raise ValueError("ERP item tax/account inputs do not match the authoritative PO.")
        actual_taxes = doc.get("taxes") or []
        expected_taxes = candidate.get("taxes") or []
        if len(actual_taxes) != len(expected_taxes) or any(
            any(actual.get(key) != value for key, value in expected_tax.items())
            for actual, expected_tax in zip(actual_taxes, expected_taxes, strict=True)
        ):
            raise ValueError("ERP tax inputs do not match the authoritative PO.")

    def submission_document(
        self, candidate: dict[str, Any], key: str, draft: dict[str, Any]
    ) -> dict[str, Any]:
        """Read-only preflight of the exact draft; caller must still persist write intent."""
        if self.client._environment != "demo":
            raise ValueError("Photo receipt submission is restricted to the demo tenant.")
        if candidate.get("purchase_order") != self.purchase_order:
            raise ValueError("Configured purchase order changed.")
        if not candidate.get("currency"):
            raise ValueError("PO currency must be known before stock submission.")
        doc = dict(self.client._document("Purchase Receipt", draft["name"]))
        self._verify_receipt(doc, candidate, key, docstatus=0)
        if not draft.get("modified") or doc.get("modified") != draft["modified"]:
            raise ValueError("ERP draft version changed; inspect the existing receipt.")
        return doc

    def submit(
        self,
        candidate: dict[str, Any],
        key: str,
        draft: dict[str, Any],
        *,
        document: dict[str, Any] | None = None,
        lookup_only: bool = False,
    ) -> dict[str, Any]:
        if self.client._environment != "demo":
            raise ValueError("Photo receipt submission is restricted to the demo tenant.")
        if not lookup_only:
            if document is None:
                raise ValueError("A revalidated existing draft is required.")
            self._verify_receipt(document, candidate, key, docstatus=0)
            if document.get("name") != draft["name"]:
                raise ValueError("Only the existing receipt may be submitted.")
            # Frappe's optimistic document-version check rejects a concurrent ERP edit.
            self.client._request(
                "/api/method/frappe.client.submit", method="POST", payload={"doc": document}
            )
        doc = self.client._document("Purchase Receipt", draft["name"])
        self._verify_receipt(doc, candidate, key, docstatus=1)
        if doc.get("name") != draft["name"] or not doc["items"][0].get("name"):
            raise ValueError("Submitted receipt identity is unverified.")
        query = urlencode(
            {
                "fields": json.dumps(
                    [
                        "name",
                        "voucher_type",
                        "voucher_no",
                        "voucher_detail_no",
                        "item_code",
                        "warehouse",
                        "actual_qty",
                        "is_cancelled",
                        "company",
                    ]
                ),
                "filters": json.dumps(
                    [
                        ["voucher_type", "=", "Purchase Receipt"],
                        ["voucher_no", "=", draft["name"]],
                    ]
                ),
                "limit_page_length": 101,
            }
        )
        rows = self.client._request(f"/api/resource/Stock%20Ledger%20Entry?{query}").get("data")
        expected = candidate["items"][0]
        if not isinstance(rows, list) or not rows or len(rows) >= 101:
            raise ValueError("Stock ledger evidence is missing or incomplete.")
        names: set[str] = set()
        total = 0.0
        for row in rows:
            if (
                not isinstance(row, dict)
                or not row.get("name")
                or row["name"] in names
                or row.get("voucher_type") != "Purchase Receipt"
                or row.get("voucher_no") != draft["name"]
                or row.get("voucher_detail_no") != doc["items"][0]["name"]
                or row.get("item_code") != expected["item_code"]
                or row.get("warehouse") != expected["warehouse"]
                or row.get("company") != candidate["company"]
                or row.get("is_cancelled") != 0
            ):
                raise ValueError("Stock ledger identity does not match this receipt.")
            total += _positive(row.get("actual_qty"), "stock ledger quantity")
            names.add(row["name"])
        if total != expected["qty"]:
            raise ValueError("Stock ledger quantity does not match this receipt.")
        return {
            "name": doc["name"],
            "docstatus": 1,
            "modified": doc.get("modified"),
            "stock_posted": True,
            "verified_receipt": True,
            "stock_ledger": rows,
            "quantity": expected["qty"],
            "stock_uom": expected["stock_uom"],
            "url": self._url(str(doc["name"])),
            "verified_at": datetime.now(UTC).isoformat(),
        }


class PhotoReceiving:
    def __init__(
        self,
        database: Path,
        reader: Callable[[bytes], dict[str, Any]],
        *,
        erp: PhotoReceiptERP | None = None,
        drafts_enabled: bool = False,
        manifest: Mapping[str, Any] | None = None,
        auto_prepare: bool = False,
    ) -> None:
        if auto_prepare and (not drafts_enabled or manifest is None or erp is None):
            raise ValueError(
                "Automatic draft preparation requires authorized drafts and an arrival manifest."
            )
        database.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(database, check_same_thread=False)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS captures "
            "(id TEXT PRIMARY KEY, digest TEXT, image BLOB, state TEXT)"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS capture_images "
            "(capture_id TEXT, image_version INTEGER, digest TEXT, image BLOB, state TEXT, "
            "PRIMARY KEY (capture_id, image_version))"
        )
        self.db.execute("CREATE INDEX IF NOT EXISTS capture_image_digest ON capture_images(digest)")
        self.reader, self.erp, self.drafts_enabled = reader, erp, drafts_enabled
        self.auto_prepare = auto_prepare
        self._draft_cursor = ""
        self._submit_cursor = ""
        self.lock = threading.RLock()
        self.work = threading.Lock()
        self.arrivals = None
        if (
            manifest is None
            and self.db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='receiving_manifests'"
            ).fetchone()
            and self.db.execute("SELECT 1 FROM receiving_manifests LIMIT 1").fetchone()
        ):
            raise ValueError(
                "Configured arrival manifest is required to reopen this receiving store."
            )
        if manifest is not None:
            if erp is None or manifest.get("purchase_order") != erp.purchase_order:
                raise ValueError("Receiving manifest and ERP purchase order must match.")
            self.arrivals = ReceivingArrivals(self.db, manifest, erp.client._credentials.base_url)
        for raw, digest, image in self.db.execute(
            "SELECT state, digest, image FROM captures"
        ).fetchall():
            state = json.loads(raw)
            # Migration preserves the last actually retained image, not invented earlier retakes.
            state.setdefault("version", len(state["events"]))
            state.setdefault("image_version", 1 if image is not None else 0)
            state.setdefault("count_semantics", COUNT_SEMANTICS)
            if any(
                key not in json.loads(raw)
                for key in ("version", "image_version", "count_semantics")
            ):
                changed = self.db.execute(
                    "UPDATE captures SET state=? WHERE id=? AND state=?",
                    (json.dumps(state), state["id"], raw),
                ).rowcount
                if not changed:
                    continue  # Another instance already advanced this capture.
            if image is not None:
                self.db.execute(
                    "INSERT OR IGNORE INTO capture_images VALUES (?, ?, ?, ?, ?)",
                    (state["id"], state["image_version"], digest, image, json.dumps(state)),
                )
            self._recover_stale_analysis(state)
        self.db.commit()

    def _event(
        self, state: dict[str, Any], status: str, detail: str, *, claim_version: int | None = None
    ) -> None:
        if state["events"] and (
            state["events"][-1]["status"] == status and state["events"][-1]["detail"] == detail
        ):
            return  # Repeated unchanged reconciliation is not another business event.
        old_version = state.get("version", 0)
        next_state = json.loads(json.dumps(state))
        next_state["status"] = status
        if status != "ANALYZING":
            next_state.pop("analysis_claim", None)
        next_state["version"] = old_version + 1
        next_state["updated_at"] = datetime.now(UTC).isoformat()
        next_state["events"].append(
            {"status": status, "detail": detail, "at": next_state["updated_at"]}
        )
        with self.lock:
            changed = self.db.execute(
                "UPDATE captures SET state=? WHERE id=? AND json_extract(state, '$.version')=?",
                (
                    json.dumps(next_state),
                    state["id"],
                    old_version if claim_version is None else claim_version,
                ),
            ).rowcount
            if changed != 1:
                self.db.rollback()
                raise ValueError("Capture changed during confirmation; reload the evidence.")
            if state.get("image_version"):
                self.db.execute(
                    "UPDATE capture_images SET state=? WHERE capture_id=? AND image_version=?",
                    (json.dumps(next_state), state["id"], state["image_version"]),
                )
            self.db.commit()
            if status != "ANALYZING":
                state.pop("analysis_claim", None)
            state.update(next_state)

    def _recover_stale_analysis(self, state: dict[str, Any]) -> dict[str, Any]:
        if state["status"] != "ANALYZING" or _analysis_claim_is_active(state):
            return state
        with contextlib.suppress(ValueError):
            self._event(state, "UNAVAILABLE", "Analysis interrupted. Upload the photo again.")
            return state
        # A concurrent owner or recovery won the version claim. Return that durable fact.
        with self.lock:
            row = self.db.execute(
                "SELECT state FROM captures WHERE id=?", (state["id"],)
            ).fetchone()
        return dict(json.loads(row[0])) if row is not None else state

    def current(self, capture_id: str) -> dict[str, Any]:
        with self.lock:
            row = self.db.execute("SELECT state FROM captures WHERE id=?", (capture_id,)).fetchone()
        if row is None:
            raise ValueError("Receiving session not found.")
        return self._recover_stale_analysis(dict(json.loads(row[0])))

    def receiving_identity(self) -> dict[str, Any]:
        """Read-only selection of actual M20 lines; no operator-invented catalog or money."""
        if self.erp is None:
            raise ValueError("ERP receiving identity is unavailable.")
        po = self.erp.client._document("Purchase Order", self.erp.purchase_order)
        if (
            po.get("name") != self.erp.purchase_order
            or po.get("docstatus") != 1
            or not po.get("modified")
        ):
            raise ValueError("Configured receiving order is not a current submitted PO.")
        items = []
        for row in po.get("items", []):
            remaining = float(row.get("qty") or 0) - float(row.get("received_qty") or 0)
            if (
                str(row.get("item_code", "")).startswith("M20-")
                and math.isfinite(remaining)
                and remaining > 0
            ):
                items.append(
                    {
                        "item_code": row["item_code"],
                        "item_name": row.get("item_name"),
                        "uom": row.get("uom"),
                        "stock_uom": row.get("stock_uom"),
                        "remaining_quantity": remaining,
                    }
                )
        if len(items) > 20:
            raise ValueError("Receiving order exceeds the bounded pilot identity selection.")
        return {
            "purchase_order": self.erp.purchase_order,
            "po_version": po["modified"],
            "items": items,
        }

    def _require_scope(self, state: dict[str, Any]) -> None:
        if self.erp is None or self.erp.purchase_order != state.get("purchase_order"):
            raise ValueError("Receiving order changed; reopen the original configured work.")
        if state.get("tenant") != self.erp.client._credentials.base_url:
            raise ValueError("Receiving tenant is unverified; original evidence remains read-only.")
        work = state.get("work_item")
        if work and work["tenant"] != self.erp.client._credentials.base_url:
            raise ValueError("Receiving tenant changed; no cross-tenant action is permitted.")
        if self.arrivals is not None and (
            not work or self.arrivals.resolve(work["arrival_id"]) != work
        ):
            raise ValueError("Capture does not belong to this configured receiving arrival.")

    def _candidate(self, state: dict[str, Any], assessment: PhotoAssessment) -> dict[str, Any]:
        erp = self.erp
        if erp is None:
            raise ValueError("Receiving order changed; reopen the original configured work.")
        self._require_scope(state)
        work = state.get("work_item")
        candidate = erp.candidate(assessment)
        if work:
            ReceivingArrivals.check_candidate(work, candidate)
            if (
                self.arrivals is None
                or self.arrivals.scans(work["arrival_id"])["status"] == "CONFLICT"
            ):
                raise ValueError("Receiving input conflict requires review before writing.")
        return candidate

    def scan(self, event: Mapping[str, Any]) -> dict[str, Any]:
        if self.arrivals is None:
            raise ValueError("Receiving arrivals are not configured.")
        with self.lock:
            # The input event and capture version move atomically, including across processes.
            # A confirmation obtained before this event must not win the later write claim.
            self.db.execute("BEGIN IMMEDIATE")
            try:
                before = self.db.total_changes
                result = self.arrivals.scan(event)
                if self.db.total_changes != before:
                    scopes = {
                        (self.arrivals.case_id, event["arrival_id"]),
                        (result["event"]["case_id"], result["event"]["arrival_id"]),
                    }
                    for case_id, arrival_id in scopes:
                        # A reused source event can dispute a different case. Invalidate
                        # that persisted work too, not a similarly named current arrival.
                        row = self.db.execute(
                            "SELECT state FROM captures "
                            "WHERE json_extract(state, '$.work_item.tenant')=? "
                            "AND json_extract(state, '$.work_item.case_id')=? "
                            "AND json_extract(state, '$.work_item.arrival_id')=?",
                            (self.arrivals.tenant, case_id, arrival_id),
                        ).fetchone()
                        if not row:
                            continue
                        state = json.loads(row[0])
                        state["version"] += 1
                        state["updated_at"] = datetime.now(UTC).isoformat()
                        state["events"].append(
                            {
                                "status": state["status"],
                                "at": state["updated_at"],
                                "detail": f"Scan {result['status'].lower()}: "
                                f"{event['source_event_id']}. "
                                "Review current evidence before confirmation.",
                            }
                        )
                        encoded = json.dumps(state)
                        self.db.execute(
                            "UPDATE captures SET state=? WHERE id=?", (encoded, state["id"])
                        )
                        self.db.execute(
                            "UPDATE capture_images SET state=? "
                            "WHERE capture_id=? AND image_version=?",
                            (encoded, state["id"], state["image_version"]),
                        )
                self.db.commit()
                if result["event"]["case_id"] != self.arrivals.case_id:
                    # The original scope is needed internally to invalidate its
                    # work, but must not escape through this case's HTTP response.
                    return {
                        "status": "CONFLICT",
                        "source_event_id": event["source_event_id"],
                        "inventory_changed": False,
                    }
                return result
            except Exception:
                self.db.rollback()
                raise

    def barcode(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        from the_missing_20.adapters.receiving_barcode import resolve_barcode

        if (
            set(payload) != {"arrival_id", "code", "format"}
            or self.arrivals is None
            or self.erp is None
        ):
            raise ValueError("Select a configured arrival and provide a code and format.")
        work = self.arrivals.resolve(payload["arrival_id"])
        result = resolve_barcode(self.erp, work, payload["code"], payload["format"])
        with self.lock, self.db:
            self.db.execute("BEGIN IMMEDIATE")
            self.db.execute(
                "CREATE TABLE IF NOT EXISTS receiving_barcode_reads "
                "(tenant TEXT, case_id TEXT, arrival_id TEXT, identity TEXT, payload TEXT, "
                "PRIMARY KEY(tenant, case_id, arrival_id, identity))"
            )
            encoded = json.dumps(result, sort_keys=True)
            identity = hashlib.sha256(encoded.encode()).hexdigest()
            existing = self.db.execute(
                "SELECT payload FROM receiving_barcode_reads WHERE tenant=? AND case_id=? "
                "AND arrival_id=? AND identity=?",
                (work["tenant"], work["case_id"], work["arrival_id"], identity),
            ).fetchone()
            if existing:
                self.db.commit()
                return json.loads(existing[0])
            scoped_count = self.db.execute(
                "SELECT count(*) FROM receiving_barcode_reads WHERE tenant=? AND case_id=? "
                "AND arrival_id=?",
                (work["tenant"], work["case_id"], work["arrival_id"]),
            ).fetchone()[0]
            if (
                scoped_count >= 20
                or self.db.execute("SELECT count(*) FROM receiving_barcode_reads").fetchone()[0]
                >= 5000
            ):
                self.db.rollback()
                raise ValueError(
                    "Barcode evidence limit reached; review the retained observations."
                )
            result.update(
                evidence_id=f"barcode:{identity}", observed_at=datetime.now(UTC).isoformat()
            )
            self.db.execute(
                "INSERT OR IGNORE INTO receiving_barcode_reads VALUES (?, ?, ?, ?, ?)",
                (work["tenant"], work["case_id"], work["arrival_id"], identity, json.dumps(result)),
            )
            retained = self.db.execute(
                "SELECT payload FROM receiving_barcode_reads WHERE tenant=? AND case_id=? "
                "AND arrival_id=? AND identity=?",
                (work["tenant"], work["case_id"], work["arrival_id"], identity),
            ).fetchone()[0]
            self.db.commit()
            return json.loads(retained)

    def _barcode_reads(self, work: Mapping[str, Any]) -> list[dict[str, Any]]:
        if not self.db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='receiving_barcode_reads'"
        ).fetchone():
            return []
        return [
            json.loads(row[0])
            for row in self.db.execute(
                "SELECT payload FROM receiving_barcode_reads WHERE tenant=? AND case_id=? "
                "AND arrival_id=? ORDER BY rowid DESC LIMIT 20",
                (work["tenant"], work["case_id"], work["arrival_id"]),
            )
        ]

    def receiving_work(self, case_id: str, purchase_order: str) -> dict[str, Any]:
        """Rebuild case linkage from persisted inputs. Plans are not arrivals or stock."""
        if (
            self.arrivals is None
            or self.arrivals.case_id != case_id
            or self.arrivals.purchase_order != purchase_order
        ):
            return {"case_id": case_id, "status": "NOT_CONFIGURED", "arrivals": []}
        rows = []
        with self.lock:
            for work in self.arrivals.items.values():
                stored = self.db.execute(
                    "SELECT state FROM captures WHERE id=?", (work["capture_id"],)
                ).fetchone()
                state = json.loads(stored[0]) if stored else {}
                scans = self.arrivals.scans(work["arrival_id"])
                count = state.get("count") if state.get("candidate") else None
                observed = count if count is not None else scans["quantity"]
                if scans["status"] == "CONFLICT":
                    observed = None
                receipt = state.get("receipt")
                rows.append(
                    {
                        **work,
                        "status": state.get("status", "AWAITING_PHOTO"),
                        "observed_quantity": observed,
                        "expected_quantity": len(work["handling_unit_ids"]),
                        "scans": scans,
                        "barcode_matches": self._barcode_reads(work),
                        "capture_id": state.get("id"),
                        "photo_version": state.get("image_version", 0),
                        "photo_evidence_id": (
                            f"{state['id']}:photo:{state['image_version']}:{state['digest'][:12]}"
                        )
                        if state.get("digest")
                        else None,
                        "photo_digest": state.get("digest"),
                        "photo_url": (
                            f"/api/v1/photo-receiving/image?id={state['id']}"
                            f"&image_version={state['image_version']}"
                        )
                        if state.get("digest")
                        else None,
                        "receipt": receipt,
                        "posted_quantity": receipt["quantity"] if receipt else None,
                        "events": state.get("events", []),
                        "inventory_authority": "ERPNext ledger, never input observations",
                    }
                )
        return {
            "case_id": case_id,
            "purchase_order": purchase_order,
            "status": "CONFIGURED",
            "arrivals": rows,
        }

    @staticmethod
    def _assessment(state: dict[str, Any]) -> PhotoAssessment:
        assessment = PhotoAssessment.model_validate(state["analysis"]["assessment"])
        confirmation = state.get("identity_confirmation")
        if confirmation:
            if (
                assessment.item_code.strip()
                or confirmation["digest"] != state["digest"]
                or confirmation["image_version"] != state["image_version"]
            ):
                raise ValueError("Identity confirmation no longer matches the original photo.")
            return assessment.model_copy(update={"item_code": confirmation["item_code"]})
        return assessment

    def confirm_identity(
        self,
        capture_id: str,
        *,
        item_code: str,
        expected_version: int,
        confirm_match: bool,
        barcode_evidence_id: str | None = None,
    ) -> dict[str, Any]:
        from the_missing_20.adapters.receiving_barcode import resolve_barcode

        if confirm_match is not True or type(expected_version) is not int:
            raise ValueError("Explicit identity confirmation and current version are required.")
        if (
            not isinstance(item_code, str)
            or not item_code.startswith("M20-")
            or len(item_code) > 100
        ):
            raise ValueError("Select an existing isolated M20 purchase order item.")
        if self.erp is None:
            raise ValueError("ERP receiving identity is unavailable.")
        if not self.work.acquire(blocking=False):
            raise ValueError("A photo operation is in progress.")
        try:
            state = self.current(capture_id)
            if state["version"] != expected_version:
                raise ValueError("Capture version changed; reopen the current evidence.")
            if (
                state["status"] not in {"COUNT_CANDIDATE", "NEEDS_REVIEW"}
                or state.get("draft_attempted")
                or state.get("duplicate_of")
            ):
                raise ValueError("Capture is not eligible for missing-identity confirmation.")
            assessment = PhotoAssessment.model_validate(state["analysis"]["assessment"])
            if (
                assessment.item_code.strip()
                or not assessment.countable
                or assessment.visibility != "clear"
                or assessment.issues
                or assessment.visible_condition != "no_visible_damage"
                or assessment.receiving_unit == "unknown"
            ):
                raise ValueError("Identity confirmation cannot override photo conflicts or safety.")
            candidate = self._candidate(
                state, assessment.model_copy(update={"item_code": item_code})
            )
            barcode_binding = {}
            if barcode_evidence_id is not None:
                if not isinstance(barcode_evidence_id, str) or self.arrivals is None:
                    raise ValueError("Select a barcode from this receiving arrival.")
                work = self.arrivals.resolve(state["work_item"]["arrival_id"])
                matches = [
                    row
                    for row in self._barcode_reads(work)
                    if row["evidence_id"] == barcode_evidence_id
                ]
                if len(matches) != 1 or matches[0]["item_code"] != item_code:
                    raise ValueError("Barcode evidence does not match this arrival and item.")
                match = matches[0]
                fresh = resolve_barcode(self.erp, work, match["code"], match["format"])
                if fresh != {
                    key: value
                    for key, value in match.items()
                    if key not in {"evidence_id", "observed_at"}
                }:
                    raise ValueError("Barcode item or order changed; scan again before confirming.")
                if fresh["po_version"] != candidate["po_version"]:
                    raise ValueError("Order changed during barcode confirmation; refresh evidence.")
                barcode_binding = {
                    "barcode_evidence_id": barcode_evidence_id,
                    "barcode_observed_at": match["observed_at"],
                    "barcode_item_version": fresh["item_version"],
                }
            state["identity_confirmation"] = {
                "item_code": item_code,
                "source": "operator_confirmed_barcode_photo"
                if barcode_binding
                else "explicit_human_confirmation",
                **barcode_binding,
                "confirmed_at": datetime.now(UTC).isoformat(),
                "digest": state["digest"],
                "image_version": state["image_version"],
                "po_version": candidate["po_version"],
                "purchase_order": candidate["purchase_order"],
            }
            state["candidate"] = candidate
            self._event(
                state,
                "RECEIPT_PREPARED",
                "Operator confirmed the missing SKU against "
                "the configured PO. Original model evidence is retained; no stock posted.",
            )
            return state
        finally:
            self.work.release()

    def list_captures(self, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        """Persisted observations only: gallery counts are never inventory or batch totals."""
        if type(limit) is not int or not 1 <= limit <= 50 or type(offset) is not int or offset < 0:
            raise ValueError("Capture pagination requires limit 1..50 and a nonnegative offset.")
        with self.lock:
            total = self.db.execute("SELECT count(*) FROM captures").fetchone()[0]
            rows = self.db.execute(
                "SELECT state FROM captures ORDER BY rowid DESC LIMIT ? OFFSET ?", (limit, offset)
            ).fetchall()
        return {
            "captures": [json.loads(row[0]) for row in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
            "count_semantics": COUNT_SEMANTICS,
        }

    def history(self, capture_id: str) -> dict[str, Any]:
        self.current(capture_id)
        with self.lock:
            rows = self.db.execute(
                "SELECT state FROM capture_images WHERE capture_id=? ORDER BY image_version",
                (capture_id,),
            ).fetchall()
        return {
            "capture_id": capture_id,
            "versions": [json.loads(row[0]) for row in rows],
            "count_semantics": COUNT_SEMANTICS,
        }

    def historical_image(self, capture_id: str, version: int) -> bytes:
        if type(version) is not int or version < 1:
            raise ValueError("Photo version must be a positive integer.")
        with self.lock:
            row = self.db.execute(
                "SELECT image FROM capture_images WHERE capture_id=? AND image_version=?",
                (capture_id, version),
            ).fetchone()
        if row is None:
            raise ValueError("Photo not found.")
        return bytes(row[0])

    def image(self, capture_id: str, digest: str = "") -> bytes:
        with self.lock:
            row = self.db.execute(
                "SELECT image, digest FROM captures WHERE id=?", (capture_id,)
            ).fetchone()
        if row is None or row[0] is None or (digest and digest != row[1]):
            raise ValueError("Photo not found.")
        return bytes(row[0])

    def create(self, *, arrival_id: str | None = None) -> dict[str, Any]:
        work = self.arrivals.resolve(arrival_id) if self.arrivals is not None else None
        if arrival_id is not None and work is None:
            raise ValueError("Receiving arrivals are not configured.")
        with self.lock:
            capture_id = work["capture_id"] if work else uuid.uuid4().hex
            existing = self.db.execute(
                "SELECT state FROM captures WHERE id=?", (capture_id,)
            ).fetchone()
            if existing:
                existing_state: dict[str, Any] = json.loads(existing[0])
                return existing_state
            if self.db.execute("SELECT count(*) FROM captures").fetchone()[0] >= 200:
                raise ValueError("Pilot storage limit reached; archive captures before continuing.")
            state: dict[str, Any] = {
                "id": capture_id,
                "status": "AWAITING_PHOTO",
                "events": [],
                "stock_posted": False,
                "drafts_enabled": self.drafts_enabled,
                "purchase_order": self.erp.purchase_order if self.erp else None,
                "tenant": self.erp.client._credentials.base_url if self.erp else None,
                "version": 0,
                "image_version": 0,
                "created_at": datetime.now(UTC).isoformat(),
                "count_semantics": COUNT_SEMANTICS,
            }
            if work:
                state["work_item"] = work
            self.db.execute(
                "INSERT OR IGNORE INTO captures VALUES (?, ?, ?, ?)",
                (state["id"], "", None, json.dumps(state)),
            )
            self.db.commit()
        return self.current(capture_id)

    def reconcile_next_submission(self) -> None:
        """Read back one already-confirmed intent; never authorize a first stock write."""
        if not self.drafts_enabled or self.erp is None:
            return
        with self.lock:
            query = "SELECT id FROM captures WHERE json_extract(state,'$.status')='SUBMIT_UNKNOWN' "
            row = (self.db.execute(query + "AND id>? ORDER BY id LIMIT 1",
                                   (self._submit_cursor,)).fetchone()
                   or self.db.execute(query + "ORDER BY id LIMIT 1").fetchone())
        if not row:
            return
        self._submit_cursor = row[0]
        state = self.current(row[0])
        confirmation = state.get("physical_receiving_confirmation", {})
        draft = state.get("draft", {})
        if not all(isinstance(value, dict) for value in (
            confirmation, draft, state.get("candidate"),
        )):
            return
        if not (
            state.get("submit_attempted") is True
            and type(state.get("submit_confirmation_version")) is int
            and confirmation.get("receipt_name") == draft.get("name")
            and draft.get("name")
            and isinstance(state.get("digest"), str) and len(state["digest"]) == 64
            and type(state.get("image_version")) is int and state["image_version"] > 0
            and isinstance(confirmation.get("confirmed_at"), str)
            and confirmation["confirmed_at"]
            and confirmation.get("digest") == state.get("digest")
            and confirmation.get("image_version") == state.get("image_version")
            and confirmation.get("candidate") == state.get("candidate")
        ):
            return
        try:
            self.submit(
                state["id"], receipt_name=draft["name"],
                expected_version=state["submit_confirmation_version"], confirm_received=True,
            )  # submit_attempted forces lookup-only, including after restart.
        except (KeyError, TypeError):
            # A malformed legacy scope is not authority. Leave its intent untouched;
            # the cursor allows a different valid record to progress next tick.
            return

    def prepare_next_draft(self) -> None:
        """Advance one candidate fairly; unknown effects are lookup-only, never rewritten."""
        if not self.auto_prepare:
            return
        with self.lock:
            query = (
                "SELECT id FROM captures WHERE json_extract(state,'$.status') "
                "IN ('RECEIPT_PREPARED','DRAFT_UNKNOWN') "
            )
            row = (
                self.db.execute(
                    query + "AND id>? ORDER BY id LIMIT 1", (self._draft_cursor,)
                ).fetchone()
                or self.db.execute(query + "ORDER BY id LIMIT 1").fetchone()
            )
        if row:
            self._draft_cursor = row[0]
            try:
                self.draft(row[0])  # Existing scope, PO reread, CAS and idempotency guards.
            except ValueError:
                raise  # Active operation/scope conflict: do not override another owner's state.
            except Exception:
                state = self.current(row[0])
                if state["status"] == "RECEIPT_PREPARED" and not state.get("draft_attempted"):
                    self._event(
                        state, "NEEDS_REVIEW", "ERP draft preparation needs a fresh order read."
                    )

    def upload(self, capture_id: str, encoded: str) -> dict[str, Any]:
        state = self._upload(capture_id, encoded)
        if self.auto_prepare and state["status"] == "RECEIPT_PREPARED":
            try:
                return self.draft(capture_id)
            except ValueError:
                # A competing operation/changed PO leaves a persisted candidate for review.
                return self.current(capture_id)
        return state

    def _upload(self, capture_id: str, encoded: str) -> dict[str, Any]:
        if not isinstance(encoded, str) or len(encoded) > 7_000_000:
            raise ValueError("Upload must be a base64 JPEG or PNG smaller than 5 MB.")
        photo = normalize_photo(base64.b64decode(encoded, validate=True))
        digest = hashlib.sha256(photo).hexdigest()
        if not self.work.acquire(blocking=False):
            raise ValueError("A photo operation is in progress. Wait for it to finish.")
        try:
            baseline = self.current(capture_id)
            with self.lock:
                try:
                    # Serialize upload claims across service instances. The image bytes,
                    # versioned history, and ANALYZING/duplicate transition are one fact.
                    self.db.execute("BEGIN IMMEDIATE")
                    stored = self.db.execute(
                        "SELECT state FROM captures WHERE id=?", (capture_id,)
                    ).fetchone()
                    if stored is None:
                        raise ValueError("Receiving session not found.")
                    state: dict[str, Any] = json.loads(stored[0])
                    if state.get("version") != baseline.get("version"):
                        raise ValueError(
                            "Capture changed during upload; reload the current evidence."
                        )
                    if state.get("draft") or state.get("draft_attempted"):
                        raise ValueError(
                            "A draft was attempted for this capture. "
                            "Reconcile it before reshooting."
                        )
                    if state.get("digest") == digest and state["status"] != "UNAVAILABLE":
                        self.db.rollback()
                        return state
                    if len(state["events"]) >= 30:
                        raise ValueError(
                            "Session retry limit reached. Review the capture conditions."
                        )
                    stored_bytes = self.db.execute(
                        "SELECT coalesce(sum(length(image)), 0) FROM capture_images"
                    ).fetchone()[0]
                    if stored_bytes + len(photo) > MAX_STORED_PHOTO_BYTES:
                        raise ValueError(
                            "Photo history storage limit reached; review retained evidence."
                        )
                    duplicate = self.db.execute(
                        "SELECT capture_id FROM capture_images WHERE digest=? AND capture_id<>? "
                        "ORDER BY rowid LIMIT 1",
                        (digest, capture_id),
                    ).fetchone()
                    for key in (
                        "analysis",
                        "candidate",
                        "count",
                        "problem",
                        "duplicate_of",
                        "identity_confirmation",
                        "analysis_claim",
                    ):
                        state.pop(key, None)
                    state["digest"] = digest
                    state["image_version"] = state.get("image_version", 0) + 1
                    if duplicate is not None:
                        state["duplicate_of"] = duplicate[0]
                        status = "DUPLICATE_EVIDENCE"
                        detail = (
                            "This exact photo already belongs to another capture. "
                            "Reopen that capture; a repeated photo is not another delivery "
                            "and cannot create another receipt."
                        )
                    else:
                        status = "ANALYZING"
                        detail = "Photo received; requesting real Strands analysis."
                        state["analysis_claim"] = {
                            "owner": uuid.uuid4().hex,
                            "expires_at": (
                                datetime.now(UTC) + timedelta(seconds=ANALYSIS_LEASE_SECONDS)
                            ).isoformat(),
                        }
                    state["status"] = status
                    state["version"] += 1
                    state["updated_at"] = datetime.now(UTC).isoformat()
                    state["events"].append(
                        {"status": status, "detail": detail, "at": state["updated_at"]}
                    )
                    encoded_state = json.dumps(state)
                    changed = self.db.execute(
                        "UPDATE captures SET digest=?, image=?, state=? WHERE id=? "
                        "AND json_extract(state, '$.version')=?",
                        (digest, photo, encoded_state, capture_id, baseline["version"]),
                    ).rowcount
                    if changed != 1:
                        raise ValueError(
                            "Capture changed during upload; reload the current evidence."
                        )
                    self.db.execute(
                        "INSERT INTO capture_images VALUES (?, ?, ?, ?, ?)",
                        (capture_id, state["image_version"], digest, photo, encoded_state),
                    )
                    self.db.commit()
                except sqlite3.Error as error:
                    self.db.rollback()
                    raise ValueError(
                        "Photo evidence transaction failed; reload the current evidence."
                    ) from error
                except Exception:
                    self.db.rollback()
                    raise
            if duplicate is not None:
                return state
            try:
                result = self.reader(photo)
                assessment = PhotoAssessment.model_validate(result["assessment"])
                state["analysis"] = {**result, "assessment": assessment.model_dump()}
                visible = assessment.visibility == "clear"
                state["count"] = (
                    len(assessment.objects) if assessment.countable and visible else None
                )
                if (
                    not assessment.countable
                    or not visible
                    or assessment.issues
                    or assessment.receiving_unit == "unknown"
                ):
                    self._event(
                        state,
                        "NEEDS_PHOTO",
                        "Place the receiving items apart and step back so each complete item "
                        "is visible in one photo. Include its SKU label when available.",
                    )
                elif assessment.visible_condition != "no_visible_damage":
                    self._event(
                        state, "NEEDS_REVIEW", "Visible condition needs inspection; no stock write."
                    )
                elif not assessment.item_code or self.erp is None:
                    self._event(
                        state,
                        "COUNT_CANDIDATE",
                        "Visible count candidate only; SKU/ERP matching is pending.",
                    )
                else:
                    try:
                        state["candidate"] = self._candidate(state, assessment)
                        self._event(
                            state,
                            "RECEIPT_PREPARED",
                            "PO matched; receipt candidate prepared. No stock posted.",
                        )
                    except Exception:
                        self._event(
                            state,
                            "NEEDS_REVIEW",
                            "ERP order match unavailable or incompatible. "
                            "Check the SKU, unit and remaining PO quantity.",
                        )
            except Exception:
                self._event(
                    state,
                    "UNAVAILABLE",
                    "Real photo analysis failed. Check AWS access or reshoot; "
                    "no fallback count was used.",
                )
            return state
        finally:
            self.work.release()

    def submit(
        self, capture_id: str, *, receipt_name: str, expected_version: int, confirm_received: bool
    ) -> dict[str, Any]:
        """Explicit confirmation of this physical receiving, never autonomous photo posting.

        The client must show the exact quantity/UOM/PO/warehouse and state version. A retake
        replaces evidence; another view or upload is not proof of a separate arrival. Once a
        submit has been attempted, repeated requests only reconcile the original receipt.
        """
        if not self.drafts_enabled or self.erp is None:
            raise ValueError("ERP receipt submission is not enabled for this pilot.")
        if confirm_received is not True or type(expected_version) is not int:
            raise ValueError("Explicit physical-receiving confirmation and version are required.")
        if not self.work.acquire(blocking=False):
            raise ValueError("A photo operation is in progress.")
        try:
            state = self.current(capture_id)
            draft = state.get("draft")
            if not draft or receipt_name != draft["name"]:
                raise ValueError("Confirm the exact existing receipt, not a new receipt.")
            attempted = bool(state.get("submit_attempted"))
            if attempted:
                self._require_scope(state)
            allowed_versions = {state["version"]}
            if attempted:
                allowed_versions.add(state["submit_confirmation_version"])
            if expected_version not in allowed_versions:
                raise ValueError("Capture version changed; reopen the current evidence.")
            if state.get("receipt"):
                return state
            if state["status"] not in {"DRAFT_VERIFIED", "SUBMIT_UNKNOWN"}:
                raise ValueError("Capture is not ready to submit its existing ERP draft.")
            document = None
            if not attempted:
                try:
                    fresh = self._candidate(state, self._assessment(state))
                    if fresh != state["candidate"]:
                        raise ValueError("PO changed.")
                    document = self.erp.submission_document(state["candidate"], capture_id, draft)
                except Exception:
                    self._event(
                        state,
                        "NEEDS_REVIEW",
                        "PO, price, tax, tenant or draft version changed "
                        "or could not be verified. No submission was attempted.",
                    )
                    return state
                state["submit_attempted"] = True
                state["stock_posted"] = None  # Unknown, not evidence that inventory is unchanged.
                state["submit_confirmation_version"] = expected_version
                state["physical_receiving_confirmation"] = {
                    "confirmed_at": datetime.now(UTC).isoformat(),
                    "receipt_name": receipt_name,
                    "candidate": state["candidate"],
                    "image_version": state["image_version"],
                    "digest": state["digest"],
                    "meaning": "Human confirmed this exact physical receiving, not another view "
                    "of previously received goods. Not a quality release or payment approval.",
                }
                # Compare-and-set prevents two service instances claiming the same confirmation.
                self._event(
                    state,
                    "SUBMIT_UNKNOWN",
                    "Confirmed receipt submission requested; "
                    "waiting for submitted document and stock ledger reread.",
                    claim_version=expected_version,
                )
            try:
                receipt = self.erp.submit(
                    state["candidate"], capture_id, draft, document=document, lookup_only=attempted
                )
                # Source inputs may arrive after the durable submit intent. Preserve
                # those events, then attach the authoritative result of the same intent.
                state = self.current(capture_id)
                state["receipt"] = receipt
                state["stock_posted"] = True
                self._event(
                    state,
                    "RECEIPT_SUBMITTED",
                    "Existing receipt submitted and exact stock "
                    "ledger quantity verified. This is not a quality release or payment.",
                )
            except Exception as error:
                state = self.current(capture_id)
                if state.get("receipt"):
                    return state
                state.setdefault("provider_failure", _provider_failure(error, "submit"))
                self._event(
                    state,
                    "SUBMIT_UNKNOWN",
                    "Submission or stock effect is unconfirmed. "
                    "Reconciliation only reads the original receipt; it never submits again. "
                    f"Provider status: {state['provider_failure']['code']}.",
                )
            return state
        finally:
            self.work.release()

    def draft(self, capture_id: str) -> dict[str, Any]:
        if not self.drafts_enabled or self.erp is None:
            raise ValueError("ERP draft creation is not enabled for this pilot.")
        if not self.work.acquire(blocking=False):
            raise ValueError("A photo operation is in progress.")
        try:
            state = self.current(capture_id)
            if state.get("draft"):
                return state
            if state["status"] not in {"RECEIPT_PREPARED", "DRAFT_UNKNOWN"}:
                raise ValueError("Capture is not ready for an ERP draft.")
            was_attempted = bool(state.get("draft_attempted"))
            if was_attempted:
                self._require_scope(state)
            if not was_attempted:
                with self.lock:
                    original = self.db.execute(
                        "SELECT capture_id FROM capture_images WHERE digest=? "
                        "ORDER BY rowid LIMIT 1",
                        (state["digest"],),
                    ).fetchone()
                if original is not None and original[0] != capture_id:
                    state["duplicate_of"] = original[0]
                    self._event(
                        state,
                        "DUPLICATE_EVIDENCE",
                        "Reopen the original capture; "
                        "this repeated photo cannot create another receipt.",
                    )
                    return state
            # Reconciliation verifies the original effect even if the PO has since changed.
            fresh = (
                state["candidate"]
                if was_attempted
                else self._candidate(state, self._assessment(state))
            )
            if not was_attempted and fresh != state.get("candidate"):
                self._event(
                    state, "NEEDS_REVIEW", "PO changed; refresh receiving evidence before a draft."
                )
                return state
            if not was_attempted:
                state["draft_attempted"] = True
                self._event(
                    state,
                    "DRAFT_UNKNOWN",
                    "ERP draft requested; waiting for authoritative reread.",
                    claim_version=state["version"],
                )
            try:
                state["draft"] = self.erp.draft(fresh, capture_id, lookup_only=was_attempted)
                self._event(
                    state, "DRAFT_VERIFIED", "ERP draft reread verified. Inventory is unchanged."
                )
            except Exception as error:
                # Preserve the original failure. A later empty lookup must not
                # overwrite the reason for the write's uncertain outcome.
                state.setdefault("provider_failure", _provider_failure(error, "draft"))
                self._event(
                    state,
                    "DRAFT_UNKNOWN",
                    "Draft outcome needs reconciliation. "
                    "Reconciliation only looks up the original key; it never writes again. "
                    f"Provider status: {state['provider_failure']['code']}.",
                )
            return state
        finally:
            self.work.release()
