"""Append-only, scoped observations of external business state.

This is observation history, not a reconstructed ERP ledger or a time-weighted
benchmark. The caller supplies a normalized evidence projection; only explicit
document references, cohort metadata and allowlisted metrics cross this boundary.
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from statistics import fmean
from typing import Any

from .operational_metrics import _posted, receiving_receipt_conflicts
from .operational_metrics import documents as posted_documents

SCHEMA_VERSION = "operational-history.v1"
MAX_POINTS = 1000
MIN_BASELINE_SAMPLES = 3
QUANTITY_METRICS = (
    "expected",
    "physically_arrived",
    "received",
    "accepted",
    "recorded",
    "case_balance",
    "available_to_promise",
    "on_hand",
    "outstanding_order_quantity",
    "quality_hold",
    "receipt_unresolved",
    "gap",
    "delivered_quantity",
    "customer_order_quantity",
    "received_cumulative",
    "accepted_cumulative",
    "released_quantity",
    "receipt_posted_quantity",
)
MONEY_METRICS = (
    "booked_revenue",
    "billed_revenue",
    "billed_amount",
    "net_billed_sales",
    "purchase_price_variance",
    "invoice_hold_value",
    "working_capital_at_risk",
    "revenue_at_risk",
    "value_protected",
    "po_unit_cost",
)
METRICS = QUANTITY_METRICS + MONEY_METRICS
_STATUSES = {"CONNECTED", "DEGRADED", "NOT_CONFIGURED", "DISCONNECTED", "UNAVAILABLE"}


def _receiving_revenue_correction(point: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Read compatibility for the v1 empty-sales-scope zero bug; never edit stored rows."""
    if (
        point.get("metric_version") != "operational-facts.v1"
        or posted_documents(point, "sales_order")
        or posted_documents(point, "sales_invoice")
    ):
        return point, []
    metrics = point.get("metrics", {})
    changed = [
        key
        for key in ("booked_revenue", "billed_revenue", "value_protected")
        if metrics.get(key) == 0 and not isinstance(metrics.get(key), bool)
    ]
    return (
        {**point, "metrics": {**metrics, **dict.fromkeys(changed)}} if changed else point
    ), changed


def _same_projection_after_correction(previous: dict[str, Any], current: dict[str, Any]) -> bool:
    corrected, changed = _receiving_revenue_correction(previous)
    # Only the exact known 0 -> unknown correction may be treated as a software
    # revision. Quantity, document version, source health and physical evidence
    # changes remain independent observations, including corrections/reversions.
    if not changed or not all(current.get("metrics", {}).get(key) is None for key in changed):
        return False
    ignored = {"observed_at", "id"}
    return {key: value for key, value in corrected.items() if key not in ignored} == {
        key: value for key, value in current.items() if key not in ignored
    }


def _unreflected_receipts(point: dict[str, Any]) -> list[str]:
    posted = {doc["name"] for doc in posted_documents(point, "purchase_receipt")}
    return sorted({
        row["receipt_name"] for row in point.get("receiving_refs", [])
        if row.get("receipt_name") and row.get("posted_quantity") is not None
        and row["receipt_name"] not in posted
    })


def _label(value: object, field: str, *, required: bool = False) -> str | None:
    if value is None or value == "":
        if required:
            raise ValueError(f"{field} is required")
        return None
    if not isinstance(value, str) or len(value) > 200 or any(ord(c) < 32 for c in value):
        raise ValueError(f"invalid {field}")
    result = value.strip()
    if not result:
        if required:
            raise ValueError(f"{field} is required")
        return None
    return result


def _instant(value: object, field: str) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str) or len(value) > 64:
        raise ValueError(f"invalid {field}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"invalid {field}") from None
    if parsed.tzinfo is None:
        raise ValueError(f"{field} requires a timezone")
    return parsed.astimezone(UTC).isoformat(timespec="microseconds")


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        result = float(value)
    except (OverflowError, ValueError):
        return None
    return result if math.isfinite(result) and abs(result) <= 1e15 else None


def _documents(erp: Mapping[str, object]) -> list[dict[str, object]]:
    raw = erp.get("documents", [])
    if not isinstance(raw, list) or len(raw) > 128:
        raise ValueError("documents must contain at most 128 references")
    documents: dict[str, dict[str, object]] = {}
    for doc in raw:
        if not isinstance(doc, Mapping):
            raise ValueError("invalid document reference")
        name = _label(doc.get("name"), "document name", required=True)
        kind = _label(doc.get("kind"), "document kind", required=True)
        version = doc.get("version")
        if version is None or version == "":
            version = doc.get("modified")
        if isinstance(version, int) and not isinstance(version, bool):
            version = str(version)
        reference: dict[str, object] = {
            "kind": kind,
            "name": name,
            "version": _label(version, "document version"),
            "status": _label(doc.get("status"), "document status"),
            "effective_at": _instant(doc.get("effective_at"), "document effective_at"),
        }
        # Preserve an explicit lifecycle that contradicts the text label. Avoid
        # changing every existing reference for the ordinary, agreeing case.
        if "docstatus" in doc and _posted(doc) != _posted({"status": doc.get("status", "")}):
            reference["docstatus"] = doc["docstatus"]
        documents[json.dumps(reference, sort_keys=True)] = reference
    return [documents[key] for key in sorted(documents)]


def _receiving_refs(erp: Mapping[str, object], case_id: str) -> list[dict[str, object]]:
    work = erp.get("receiving_work")
    if not isinstance(work, Mapping) or work.get("case_id") != case_id:
        return []
    rows = work.get("arrivals", [])
    if not isinstance(rows, list) or len(rows) > 50:
        raise ValueError("Invalid receiving history scope.")
    refs: list[dict[str, object]] = []
    for row in rows:
        if (
            row.get("capture_id")
            or row.get("scans", {}).get("events")
            or row.get("scans", {}).get("conflicts")
            or row.get("barcode_matches")
        ):
            receipt = row.get("receipt") or {}
            reference: dict[str, object] = {
                key: _label(value, key)
                for key, value in {
                    "arrival_id": row["arrival_id"],
                    "capture_id": row.get("capture_id"),
                    "photo_digest": row.get("photo_digest"),
                    "receipt_name": receipt.get("name"),
                    "receipt_version": receipt.get("modified"),
                    "origin": row["origin"],
                    "photo_evidence_id": row.get("photo_evidence_id"),
                    "scan_status": row.get("scans", {}).get("status"),
                }.items()
            }
            reference.update(
                observed_quantity=_number(row.get("observed_quantity")),
                posted_quantity=_number(row.get("posted_quantity")),
            )
            reference["scans"] = [
                {
                    "id": _label(event["source_event_id"], "scan ID", required=True),
                    "occurred_at": _instant(event["occurred_at"], "scan time"),
                    "ingested_at": _instant(event["ingested_at"], "scan arrival time"),
                    **(
                        {
                            "observation_method": _label(
                                event["observation_method"], "scan method"
                            ),
                            "barcode_format": _label(event["barcode_format"], "barcode format"),
                        }
                        if event.get("observation_method")
                        else {}
                    ),
                }
                for event in row.get("scans", {}).get("events", [])
            ]
            if row.get("scans", {}).get("conflicts"):
                reference["scan_conflicts"] = [
                    {
                        "id": _label(event["conflict_id"], "scan conflict ID", required=True),
                        "detected_at": _instant(event["detected_at"], "scan conflict time"),
                    }
                    for event in row["scans"]["conflicts"]
                ]
            refs.append(reference)
            if row.get("barcode_matches"):
                reference["barcode_evidence_ids"] = sorted(
                    _label(match["evidence_id"], "barcode evidence ID", required=True)
                    for match in row["barcode_matches"]
                )
    return refs


def _cohort_label(erp: Mapping[str, object], metrics: Mapping[str, object], key: str) -> str | None:
    # An explicit null from the projector means mixed/unknown; do not override it.
    if key in metrics:
        return _label(metrics[key], key)
    raw = erp.get("documents", [])
    values = (
        {_label(doc.get(key), key) for doc in raw if isinstance(doc, Mapping) and doc.get(key)}
        if isinstance(raw, list)
        else set()
    )
    return next(iter(values)) if len(values) == 1 else None


def _observation(erp: Mapping[str, object], metrics: Mapping[str, object]) -> dict[str, Any]:
    case_id = _label(erp.get("case_id") or metrics.get("case_id"), "case_id", required=True)
    source = _label(erp.get("source_id"), "source_id", required=True)
    observed = _instant(erp.get("received_at") or erp.get("observed_at"), "observed_at")
    # The projection combines a cached ERP read with independently ingested
    # physical evidence. A new scan must not be backdated to that ERP cache.
    # Use server ingestion times, never scanner-supplied occurrence times or a
    # polling clock; unchanged evidence still deduplicates below.
    work = erp.get("receiving_work")
    if isinstance(work, Mapping) and work.get("case_id") == case_id:
        timestamps = [observed] if observed else []
        for arrival in work.get("arrivals", []):
            for scan in arrival.get("scans", {}).get("events", []):
                timestamps.append(_instant(scan.get("ingested_at"), "scan ingestion time"))
            for conflict in arrival.get("scans", {}).get("conflicts", []):
                timestamps.append(_instant(conflict.get("detected_at"), "scan conflict time"))
            for match in arrival.get("barcode_matches", []):
                timestamps.append(_instant(match.get("observed_at"), "barcode observation time"))
            for event in arrival.get("events", []):
                timestamps.append(_instant(event.get("at"), "capture event time"))
        observed = max((stamp for stamp in timestamps if stamp), default=observed)
    effective = _instant(erp.get("effective_at"), "effective_at")
    kind = erp.get("observation_kind", "live_observation")
    if kind not in ("live_observation", "backfill"):
        raise ValueError("invalid observation_kind")
    if kind == "backfill" and effective is None:
        raise ValueError("backfill requires an effective_at")
    status = erp.get("status")
    status = status if isinstance(status, str) and status in _STATUSES else "UNAVAILABLE"
    return {
        "case_id": case_id,
        "source_id": source,
        "observed_at": observed or datetime.now(UTC).isoformat(timespec="microseconds"),
        "effective_at": effective,
        "observation_kind": kind,
        "time_basis": "observed_at",
        "source_status": status,
        "provenance": _label(erp.get("provenance"), "provenance") or "external-observation",
        "metric_version": _label(metrics.get("metric_version"), "metric_version") or "v1",
        "currency": _cohort_label(erp, metrics, "currency") if status == "CONNECTED" else None,
        "uom": _cohort_label(erp, metrics, "uom") if status == "CONNECTED" else None,
        "item_code": _cohort_label(erp, metrics, "item_code") if status == "CONNECTED" else None,
        "documents": _documents(erp),
        "receiving_refs": _receiving_refs(erp, str(case_id)),
        "metrics": {
            key: _number(metrics.get(key)) if status == "CONNECTED" else None for key in METRICS
        },
    }


def _baseline(points: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "kind": "internal_observation_baseline",
        "status": "INSUFFICIENT_DATA",
        "minimum_samples": MIN_BASELINE_SAMPLES,
        "sample_count": 0,
        "calculation": "arithmetic_mean_of_prior_comparable_observations",
        "time_weighted": False,
        "industry_benchmark": False,
        "metrics": {},
        "cohort": None,
    }
    if not points:
        return result
    current = points[-1]
    keys = (
        "case_id",
        "source_id",
        "currency",
        "uom",
        "item_code",
        "provenance",
        "metric_version",
        "observation_kind",
    )
    result["cohort"] = {key: current[key] for key in keys}
    previous = [
        point
        for point in points[:-1]
        if point["source_status"] == "CONNECTED" and all(point[key] == current[key] for key in keys)
    ]
    result["sample_count"] = len(previous)
    if current["source_status"] != "CONNECTED":
        result["status"] = "SOURCE_UNAVAILABLE"
        return result
    for key in METRICS:
        value = current["metrics"][key]
        samples = [point["metrics"][key] for point in previous if point["metrics"][key] is not None]
        comparable = bool(current["currency"] if key in MONEY_METRICS else current["uom"])
        metric: dict[str, Any] = {
            "current": value,
            "sample_count": len(samples),
            "status": "INSUFFICIENT_DATA",
            "previous_mean": None,
            "change": None,
            "change_percent": None,
        }
        if not comparable:
            metric["status"] = "UNKNOWN_UNIT"
        elif value is None:
            metric["status"] = "UNAVAILABLE"
        elif len(samples) >= MIN_BASELINE_SAMPLES:
            mean = fmean(samples)
            metric.update(
                status="AVAILABLE",
                previous_mean=mean,
                change=value - mean,
                change_percent=_number((value - mean) / abs(mean) * 100) if mean else None,
            )
            result["status"] = "AVAILABLE"
        result["metrics"][key] = metric
    return result


class OperationalHistory:
    """Persist semantic source changes, without duplicating unchanged polls.

    Each operation uses its own connection. BEGIN IMMEDIATE makes comparison and
    append atomic across threads/processes; the database is never pruned here.
    Queries are observations ordered by observation time, not source-effective
    time. A backdated correction consequently remains visible as a new fact.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS operational_observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    semantic_hash TEXT NOT NULL,
                    observation_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS operational_scope_time
                    ON operational_observations(case_id, observed_at, id);
                CREATE INDEX IF NOT EXISTS operational_source_latest
                    ON operational_observations(case_id, source_id, id);
                """
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def record(self, erp: Mapping[str, object], metrics: Mapping[str, object]) -> bool:
        """Append a changed normalized observation; reject malformed scope/time input."""
        if receiving_receipt_conflicts(erp):
            return False
        point = _observation(erp, metrics)
        semantic = {key: value for key, value in point.items() if key != "observed_at"}
        fingerprint = hashlib.sha256(
            json.dumps(semantic, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            latest = connection.execute(
                "SELECT semantic_hash, observation_json FROM operational_observations "
                "WHERE case_id = ? AND source_id = ? ORDER BY id DESC LIMIT 1",
                (point["case_id"], point["source_id"]),
            ).fetchone()
            if latest is not None and latest["semantic_hash"] == fingerprint:
                return False
            if latest is not None and _same_projection_after_correction(
                json.loads(latest["observation_json"]), point
            ):
                return False
            if point["observation_kind"] == "backfill":
                previous = connection.execute(
                    "SELECT 1 FROM operational_observations "
                    "WHERE case_id = ? AND source_id = ? AND semantic_hash = ? LIMIT 1",
                    (point["case_id"], point["source_id"], fingerprint),
                ).fetchone()
                if previous is not None:
                    return False
            connection.execute(
                "INSERT INTO operational_observations"
                "(case_id, source_id, observed_at, semantic_hash, observation_json) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    point["case_id"],
                    point["source_id"],
                    point["observed_at"],
                    fingerprint,
                    json.dumps(point, sort_keys=True, separators=(",", ":")),
                ),
            )
        return True

    def query(
        self,
        case_id: str,
        *,
        limit: int = 96,
        since: str | None = None,
        source_id: str | None = None,
    ) -> dict[str, Any]:
        """Return at most 1,000 recent points and a same-cohort, prior-sample baseline."""
        case = _label(case_id, "case_id", required=True)
        source = _label(source_id, "source_id")
        start = _instant(since, "since")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_POINTS:
            raise ValueError(f"limit must be between 1 and {MAX_POINTS}")
        clause = "o.case_id = ?"
        params: list[object] = [case]
        if source is not None:
            clause += " AND o.source_id = ?"
            params.append(source)
        if start is not None:
            clause += " AND o.observed_at >= ?"
            params.append(start)
        with self._connect() as connection:
            # Coverage and returned points must describe one read snapshot even
            # when a provider poll is appending concurrently.
            connection.execute("BEGIN")
            summary = connection.execute(
                "SELECT COUNT(*) AS count, MIN(observed_at) AS first, MAX(observed_at) AS last "
                f"FROM operational_observations o WHERE {clause}",
                params,
            ).fetchone()
            rows = connection.execute(
                "SELECT o.id, o.observation_json, p.id AS previous_id, "
                "p.observation_json AS previous_json FROM operational_observations o "
                "LEFT JOIN operational_observations p ON p.id = ("
                "SELECT MAX(previous.id) FROM operational_observations previous "
                "WHERE previous.case_id = o.case_id AND previous.source_id = o.source_id "
                "AND previous.id < o.id) "
                f"WHERE {clause} ORDER BY o.observed_at DESC, o.id DESC LIMIT ?",
                [*params, limit],
            ).fetchall()
        points, projection_revisions, metric_corrections, excluded = [], [], [], []
        for row in reversed(rows):
            raw = json.loads(row["observation_json"])
            pending = _unreflected_receipts(raw)
            if pending:
                excluded.append({
                    "stored_record_id": row["id"], "observed_at": raw["observed_at"],
                    "receipt_names": pending, "reason": "RECEIVING_RECEIPT_NOT_REFRESHED",
                })
                continue  # Keep raw evidence; never chart or benchmark a mixed snapshot.
            previous = json.loads(row["previous_json"]) if row["previous_json"] else None
            if previous is not None and _same_projection_after_correction(previous, raw):
                projection_revisions.append(
                    {
                        "stored_record_id": row["id"],
                        "previous_record_id": row["previous_id"],
                        "observed_at": raw["observed_at"],
                        "reason": "EMPTY_SALES_SCOPE_ZERO_CORRECTION",
                    }
                )
                continue
            corrected, changed = _receiving_revenue_correction(raw)
            if changed:
                metric_corrections.append(
                    {
                        "stored_record_id": row["id"],
                        "fields": changed,
                        "stored_value": 0,
                        "corrected_value": None,
                        "reason": "EMPTY_SALES_SCOPE_ZERO_CORRECTION",
                    }
                )
            points.append({**corrected, "id": row["id"]})
        return {
            "schema_version": SCHEMA_VERSION,
            "case_id": case,
            "source_id": source,
            "points": points,
            "projection_revisions": projection_revisions,
            "metric_corrections": metric_corrections,
            "excluded_observations": excluded,
            "coverage": {
                "status": "OBSERVED"
                if points
                else "INCONSISTENT_ONLY" if excluded else "REVISION_ONLY"
                if projection_revisions
                else "EMPTY",
                "since": start,
                "total_points": summary["count"],
                "total_points_basis": "RETAINED_RECORDS_INCLUDING_PROJECTION_REVISIONS",
                "returned_points": len(points),
                "truncated": summary["count"] > len(rows),
                "first_observed_at": points[0]["observed_at"] if points else None,
                "last_observed_at": points[-1]["observed_at"] if points else None,
                "first_retained_at": summary["first"],
                "last_retained_at": summary["last"],
                "business_history_complete": False,
                "time_basis": "observed_at",
            },
            "baseline": _baseline(points),
        }
