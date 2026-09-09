"""Configured receiving work, distinct from observations and posted inventory.

The pilot accepts known, unique handling-unit IDs, not arbitrary SKU barcodes.
One arrival resolves one existing photo operation across sessions and restarts.
No network, inventory effect, or approval is performed by this registry.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_. -]{0,99}", value):
        raise ValueError(f"Invalid {label} in receiving manifest.")
    return value


class ReceivingArrivals:
    """Immutable configured identities in the same transaction store as captures."""

    def __init__(self, db: sqlite3.Connection, manifest: Mapping[str, Any], tenant: str) -> None:
        if set(manifest) != {"case_id", "purchase_order", "arrivals"} or not tenant:
            raise ValueError("Receiving manifest requires an exact case, PO and configured tenant.")
        self.case_id = _identifier(manifest["case_id"], "case")
        self.db = db
        self.tenant = tenant
        self.purchase_order = _identifier(manifest["purchase_order"], "purchase order")
        rows = manifest["arrivals"]
        if not isinstance(rows, list) or not 1 <= len(rows) <= 50:
            raise ValueError("Configure between 1 and 50 arrivals.")
        self.items: dict[str, dict[str, Any]] = {}
        seen_units: set[str] = set()
        required = {
            "arrival_id",
            "purchase_order_item",
            "item_code",
            "uom",
            "warehouse",
            "handling_unit_ids",
            "origin",
        }
        for row in rows:
            if not isinstance(row, Mapping) or set(row) != required:
                raise ValueError("Receiving arrival has missing or unexpected fields.")
            identity = {key: _identifier(row[key], key) for key in required - {"handling_unit_ids"}}
            units = row["handling_unit_ids"]
            if not isinstance(units, list) or not 1 <= len(units) <= 20:
                raise ValueError("Each arrival requires 1..20 unique handling units.")
            units = [_identifier(unit, "handling unit") for unit in units]
            if len(set(units)) != len(units) or seen_units.intersection(units):
                raise ValueError("A handling unit cannot belong to two receiving arrivals.")
            if identity["origin"] not in {"demo_scan", "operator"}:
                raise ValueError("Unknown physical-input origin; no carrier identity is inferred.")
            if identity["arrival_id"] in self.items:
                raise ValueError("Duplicate arrival identity.")
            seen_units.update(units)
            work = {
                **identity,
                "handling_unit_ids": sorted(units),
                "tenant": tenant,
                "case_id": self.case_id,
                "purchase_order": self.purchase_order,
                "operation": "receive",
            }
            key = [tenant, self.case_id, self.purchase_order, identity["arrival_id"], "receive"]
            work["capture_id"] = hashlib.sha256(json.dumps(key).encode()).hexdigest()[:32]
            self.items[identity["arrival_id"]] = work
        db.execute(
            "CREATE TABLE IF NOT EXISTS receiving_manifests "
            "(tenant TEXT, case_id TEXT, manifest TEXT, PRIMARY KEY(tenant, case_id))"
        )
        encoded = json.dumps(self.items, sort_keys=True)
        db.execute(
            "INSERT OR IGNORE INTO receiving_manifests VALUES (?, ?, ?)",
            (tenant, self.case_id, encoded),
        )
        stored = db.execute(
            "SELECT manifest FROM receiving_manifests WHERE tenant=? AND case_id=?",
            (tenant, self.case_id),
        ).fetchone()[0]
        if stored != encoded:
            db.rollback()
            raise ValueError("Receiving manifest changed; do not rebind an existing case.")
        # Bind physical identities across cases, not just within one manifest.
        # Backfill retained manifests in the same serialized write transaction.
        db.execute(
            "CREATE TABLE IF NOT EXISTS receiving_unit_bindings "
            "(tenant TEXT, unit TEXT, capture_id TEXT, PRIMARY KEY(tenant, unit))"
        )
        try:
            for (raw,) in db.execute(
                "SELECT manifest FROM receiving_manifests WHERE tenant=?", (tenant,)
            ).fetchall():
                for configured in json.loads(raw).values():
                    for unit in configured["handling_unit_ids"]:
                        db.execute(
                            "INSERT OR IGNORE INTO receiving_unit_bindings VALUES (?, ?, ?)",
                            (tenant, unit, configured["capture_id"]),
                        )
                        binding = db.execute(
                            "SELECT capture_id FROM receiving_unit_bindings "
                            "WHERE tenant=? AND unit=?",
                            (tenant, unit),
                        ).fetchone()[0]
                        if binding != configured["capture_id"]:
                            raise ValueError(
                                "Handling unit is already bound to another receiving operation."
                            )
        except Exception:
            db.rollback()
            raise
        db.commit()
        db.execute(
            "CREATE TABLE IF NOT EXISTS receiving_scans "
            "(tenant TEXT, event_id TEXT, payload TEXT, ingested_at TEXT, "
            "PRIMARY KEY(tenant, event_id))"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS receiving_scan_conflicts "
            "(tenant TEXT, event_id TEXT, payload TEXT, ingested_at TEXT, "
            "PRIMARY KEY(tenant, event_id, payload))"
        )
        db.commit()

    def resolve(self, arrival_id: str | None) -> dict[str, Any]:
        if not isinstance(arrival_id, str) or arrival_id not in self.items:
            raise ValueError("Select a known receiving arrival.")
        work: dict[str, Any] = json.loads(json.dumps(self.items[arrival_id]))
        return work

    def scan(self, event: Mapping[str, Any]) -> dict[str, Any]:
        required = {"source_event_id", "arrival_id", "handling_unit_id", "occurred_at"}
        optional = {"observation_method", "barcode_format"}
        if not required.issubset(event) or set(event) - required - optional:
            raise ValueError("A scan requires its event ID, arrival, unit ID and source time.")
        if optional.intersection(event) and (
            not optional.issubset(event)
            or event["observation_method"] not in ("manual", "camera", "video", "hid")
            or event["barcode_format"] not in ("manual", "ean_13", "upc_a", "code_128", "qr_code")
        ):
            raise ValueError("Scan method and format must both be supported.")
        event_id = _identifier(event["source_event_id"], "event ID")
        unit = _identifier(event["handling_unit_id"], "handling unit")
        work = self.resolve(event["arrival_id"])
        if unit not in work["handling_unit_ids"]:
            raise ValueError("Unknown handling unit for this arrival; no SKU quantity is inferred.")
        if not isinstance(event["occurred_at"], str):
            raise ValueError("Scan source time must include a timezone.")
        occurred = datetime.fromisoformat(event["occurred_at"].replace("Z", "+00:00"))
        if occurred.utcoffset() is None or (occurred - datetime.now(UTC)).total_seconds() > 300:
            raise ValueError("Scan source time must be timezone-aware and not in the future.")
        payload = json.dumps(
            {**event, "case_id": self.case_id, "origin": work["origin"]}, sort_keys=True
        )
        now = datetime.now(UTC).isoformat()
        if self.db.execute("SELECT count(*) FROM receiving_scans").fetchone()[0] >= 5000:
            existing = self.db.execute(
                "SELECT payload FROM receiving_scans WHERE tenant=? AND event_id=?",
                (self.tenant, event_id),
            ).fetchone()
            if not existing or existing[0] != payload:
                raise ValueError("Scan history limit reached; review retained inputs.")
        self.db.execute(
            "INSERT OR IGNORE INTO receiving_scans VALUES (?, ?, ?, ?)",
            (self.tenant, event_id, payload, now),
        )
        stored, ingested = self.db.execute(
            "SELECT payload, ingested_at FROM receiving_scans WHERE tenant=? AND event_id=?",
            (self.tenant, event_id),
        ).fetchone()
        conflict = stored != payload
        if conflict:
            self.db.execute(
                "INSERT OR IGNORE INTO receiving_scan_conflicts VALUES (?, ?, ?, ?)",
                (self.tenant, event_id, payload, now),
            )
        return {
            "status": "CONFLICT" if conflict else "RECORDED",
            "event": json.loads(stored),
            "ingested_at": ingested,
            "inventory_changed": False,
        }

    def scans(self, arrival_id: str) -> dict[str, Any]:
        self.resolve(arrival_id)
        rows = self.db.execute(
            "SELECT event_id, payload, ingested_at FROM receiving_scans "
            "WHERE tenant=? AND json_extract(payload, '$.case_id')=? "
            "AND json_extract(payload, '$.arrival_id')=? ORDER BY rowid",
            (self.tenant, self.case_id, arrival_id),
        ).fetchall()
        # Include a conflict for both its originally accepted arrival and the
        # attempted arrival, without exposing another case's payload.
        conflicts = self.db.execute(
            "SELECT c.event_id, c.payload, c.ingested_at FROM receiving_scan_conflicts c "
            "JOIN receiving_scans s ON s.tenant=c.tenant AND s.event_id=c.event_id "
            "WHERE c.tenant=? AND ((json_extract(c.payload, '$.case_id')=? "
            "AND json_extract(c.payload, '$.arrival_id')=?) OR "
            "(json_extract(s.payload, '$.case_id')=? "
            "AND json_extract(s.payload, '$.arrival_id')=?)) ORDER BY c.rowid",
            (self.tenant, self.case_id, arrival_id, self.case_id, arrival_id),
        ).fetchall()
        events = [{**json.loads(raw), "ingested_at": ingested} for _, raw, ingested in rows]
        events = [
            event
            for event in events
            if event["case_id"] == self.case_id and event["arrival_id"] == arrival_id
        ]
        disputed = bool(conflicts)
        units = sorted({event["handling_unit_id"] for event in events})
        return {
            "status": "CONFLICT" if disputed else "OBSERVED",
            "events": events,
            "conflicts": [
                {
                    "source_event_id": event_id,
                    "conflict_id": hashlib.sha256(payload.encode()).hexdigest(),
                    "detected_at": detected_at,
                }
                for event_id, payload, detected_at in conflicts
            ],
            "handling_unit_ids": units,
            "quantity": None if disputed else len(units),
        }

    @staticmethod
    def check_candidate(work: Mapping[str, Any], candidate: Mapping[str, Any]) -> None:
        line = candidate["items"][0]
        if (
            candidate["purchase_order"] != work["purchase_order"]
            or candidate["quantity"] != len(work["handling_unit_ids"])
            or any(
                line.get(key) != work[key]
                for key in ("purchase_order_item", "item_code", "uom", "warehouse")
            )
        ):
            raise ValueError("Photo count, unit or item conflicts with this receiving arrival.")
