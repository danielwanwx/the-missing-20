"""Durable notifications of verified receipts, not stock/accounting authority.

One local SQLite journal claims each destination/tenant/receipt effect. Unknown
writes are reconciled by source lookup only. This is not distributed exactly-once
delivery: two independent deployments need a shared journal or provider unique key.
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Any, Protocol
from urllib.error import HTTPError


def receipt_event(state: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(state, dict):
        return None
    receipt, work = state.get("receipt") or {}, state.get("work_item") or {}
    if not isinstance(receipt, dict) or not isinstance(work, dict):
        return None
    if (
        state.get("status") != "RECEIPT_SUBMITTED"
        or state.get("stock_posted") is not True
        or receipt.get("docstatus") != 1
        or receipt.get("verified_receipt") is not True
        or receipt.get("stock_posted") is not True
        or not receipt.get("stock_ledger")
        or not work.get("case_id")
    ):
        return None
    for data, keys in (
        (state, ("tenant", "id", "purchase_order")),
        (work, ("case_id", "arrival_id", "item_code")),
        (receipt, ("name", "stock_uom", "url", "verified_at")),
    ):
        if any(not isinstance(data.get(key), str) or not data[key] for key in keys):
            return None
    quantity = receipt.get("quantity")
    rows = receipt["stock_ledger"]
    if (
        not isinstance(quantity, (float, int))
        or isinstance(quantity, bool)
        or not math.isfinite(quantity)
        or quantity <= 0
        or not isinstance(rows, list)
        or any(
            not isinstance(row, dict) or not isinstance(row.get("name"), str) or not row["name"]
            for row in rows
        )
    ):
        return None
    return {
        "kind": "receipt_posted",
        "tenant": state["tenant"],
        "case_id": work["case_id"],
        "arrival_id": work["arrival_id"],
        "capture_id": state["id"],
        "purchase_order": state["purchase_order"],
        "receipt": receipt["name"],
        "quantity": receipt["quantity"],
        "uom": receipt["stock_uom"],
        "item_code": work["item_code"],
        "erp_url": receipt["url"],
        "verified_at": receipt["verified_at"],
        "stock_ledger_ids": sorted(row["name"] for row in receipt["stock_ledger"]),
    }


class Destination(Protocol):
    def find(self, event: dict[str, Any], key: str) -> dict[str, Any] | None: ...
    def send(self, event: dict[str, Any], key: str) -> None: ...


def same_stock_effects(original: object, current: object) -> bool:
    """Compare accounting identity, not ERPNext's temporary SLE names.

    ERPNext asynchronously renames hash IDs to its ledger naming series. Never
    rewrite a delivered event; require the complete unchanged voucher/line facts.
    """
    fields = (
        "voucher_type",
        "voucher_no",
        "voucher_detail_no",
        "item_code",
        "warehouse",
        "company",
    )

    def identities(rows: object) -> list[tuple[Any, ...]] | None:
        if not isinstance(rows, list) or not rows:
            return None
        result = []
        for row in rows:
            if not isinstance(row, dict) or any(
                not isinstance(row.get(key), str) or not row[key] for key in fields
            ):
                return None
            quantity = row.get("actual_qty")
            if (
                row.get("is_cancelled") != 0
                or isinstance(quantity, bool)
                or not isinstance(quantity, (int, float))
                or not math.isfinite(quantity)
                or quantity <= 0
            ):
                return None
            result.append((*[row[key] for key in fields], quantity))
        return sorted(result) if len(set(result)) == len(result) else None

    before, after = identities(original), identities(current)
    return before is not None and before == after


class HandoffJournal:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False, timeout=10)
        self.lock = RLock()
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS handoffs "
            "(key TEXT PRIMARY KEY, route TEXT, payload TEXT, state TEXT)"
        )
        self.db.commit()

    def current(self, key: str) -> dict[str, Any]:
        with self.lock:
            row = self.db.execute("SELECT state FROM handoffs WHERE key=?", (key,)).fetchone()
        if row is None:
            raise ValueError("Unknown receiving handoff")
        state: dict[str, Any] = json.loads(row[0])
        return state

    def for_capture(self, capture_id: str) -> list[dict[str, Any]]:
        with self.lock:
            rows = self.db.execute(
                "SELECT state FROM handoffs WHERE json_extract(payload,'$.capture_id')=? "
                "ORDER BY rowid",
                (capture_id,),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def _transition(self, key: str, status: str, **values: Any) -> None:
        with self.lock:
            state = self.current(key)
            if state["status"] == "VERIFIED":
                return
            next_state = {**state, "status": status, **values}
            if status == "VERIFIED" or next_state.get("last_failure") is None:
                next_state.pop("last_failure", None)
            if next_state != state:
                next_state["updated_at"] = datetime.now(UTC).isoformat()
                self.db.execute(
                    "UPDATE handoffs SET state=? WHERE key=?", (json.dumps(next_state), key)
                )
                self.db.commit()

    def deliver(
        self,
        route: str,
        event: dict[str, Any],
        target: Destination,
        *,
        business_key: str | None = None,
    ) -> dict[str, Any]:
        key = (
            "m20-receipt-"
            + hashlib.sha256(
                json.dumps(
                    [route, event["tenant"], business_key or event["receipt"]],
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()[:32]
        )
        payload = json.dumps(event, sort_keys=True)
        with self.lock:
            state = {
                "key": key,
                "route": route,
                "status": "PENDING",
                "updated_at": datetime.now(UTC).isoformat(),
            }
            self.db.execute(
                "INSERT OR IGNORE INTO handoffs VALUES (?,?,?,?)",
                (key, route, payload, json.dumps(state)),
            )
            self.db.commit()
            stored = self.db.execute("SELECT payload FROM handoffs WHERE key=?", (key,)).fetchone()
            if stored[0] != payload:
                raise ValueError("Receiving handoff payload changed for the same receipt")
        if self.current(key)["status"] == "VERIFIED":
            return self.current(key)
        phase = "lookup"
        try:
            found = target.find(event, key)
            if found:
                self._transition(key, "VERIFIED", evidence=found)
                return self.current(key)
            prior = self.current(key)
            if (prior.get("last_failure") or {}).get("phase") == "lookup":
                # Access recovered, but absence is NOT permission to resend an
                # uncertain write. Remove only the obsolete lookup warning.
                self._transition(key, prior["status"], last_failure=None)
            with self.lock:
                state = self.current(key)
                claimed = {
                    **state,
                    "status": "UNKNOWN",
                    "updated_at": datetime.now(UTC).isoformat(),
                }
                changed = self.db.execute(
                    "UPDATE handoffs SET state=? WHERE key=? "
                    "AND json_extract(state,'$.status')='PENDING'",
                    (json.dumps(claimed), key),
                ).rowcount
                self.db.commit()  # Durable intent BEFORE contacting the provider.
            if not changed:
                return self.current(key)  # Uncertain effect: lookup only, never a second send.
            phase = "send"
            target.send(event, key)
            phase = "readback"
            found = target.find(event, key)
            if found:
                self._transition(key, "VERIFIED", evidence=found)
        except (OSError, ValueError, TimeoutError) as error:
            # Credentials and provider bodies are never persisted/displayed here.
            # PENDING remains resumable; UNKNOWN remains lookup-only.
            # Allowlisted diagnostics only: never retain response bodies, URLs or credentials.
            failure: dict[str, Any] = {"phase": phase, "kind": "provider_unavailable"}
            if isinstance(error, HTTPError):
                failure["http_status"] = error.code
                failure["kind"] = (
                    "access_denied" if error.code in (401, 403) else "provider_rejected"
                )
            elif isinstance(error, ValueError):
                failure["kind"] = "evidence_mismatch"
            self._transition(
                key,
                self.current(key)["status"],
                last_failure=failure,
                **({"send_failure": failure} if phase == "send" else {}),
            )
        return self.current(key)
