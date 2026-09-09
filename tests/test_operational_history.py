"""Offline persistence/meaning tests; these do not certify an external ERP effect."""

from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

from the_missing_20.adapters.operational_history import MAX_POINTS, OperationalHistory


def packet(*, day: int = 1, version: str = "1", case: str = "M20-history") -> dict[str, Any]:
    return {
        "case_id": case,
        "source_id": "erpnext-missing20",
        "status": "CONNECTED",
        "provenance": "live-read",
        "received_at": f"2026-09-{day:02d}T10:00:00+00:00",
        "sequence": day,
        "documents": [
            {
                "name": "M20-PR-1",
                "kind": "purchase_receipt",
                "version": version,
                "currency": "USD",
                "uom": "Nos",
                "item_code": "M20-ECU",
                "status": "SUBMITTED",
            }
        ],
    }


def values(quantity: float = 10, *, currency: str | None = "USD") -> dict[str, object]:
    return {
        "received_cumulative": quantity,
        "recorded": quantity,
        "currency": currency,
        "uom": "Nos",
        "po_unit_cost": 50.0,
        "invoice_hold_value": 100.0,
    }


def test_empty_history_has_no_fabricated_baseline(tmp_path: Path) -> None:
    result = OperationalHistory(tmp_path / "history.db").query("M20-new")
    assert result["points"] == []
    assert result["coverage"]["status"] == "EMPTY"
    assert result["coverage"]["first_observed_at"] is None
    assert result["coverage"]["business_history_complete"] is False
    assert result["baseline"]["status"] == "INSUFFICIENT_DATA"
    assert result["baseline"]["sample_count"] == 0


@pytest.mark.parametrize("physical_kind", ["barcode", "scan", "photo", "conflict"])
def test_physical_evidence_is_not_backdated_to_cached_erp(
    tmp_path: Path, physical_kind: str
) -> None:
    store = OperationalHistory(tmp_path / "history.db")
    erp = packet()
    assert store.record(erp, values())
    timestamp = "2026-09-01T10:01:00+00:00"
    row = {"arrival_id": "arrival-1", "origin": "physical"}
    if physical_kind == "barcode":
        row["barcode_matches"] = [{"evidence_id": "barcode:1", "observed_at": timestamp}]
    elif physical_kind == "scan":
        row["scans"] = {
            "events": [
                {
                    "source_event_id": "scan-1",
                    "occurred_at": "2027-01-01T00:00:00+00:00",
                    "ingested_at": timestamp,
                }
            ]
        }
    elif physical_kind == "photo":
        row.update(capture_id="capture-1", events=[{"at": timestamp}])
    else:
        row["scans"] = {"conflicts": [{"conflict_id": "conflict-1", "detected_at": timestamp}]}
    erp["receiving_work"] = {"case_id": "M20-history", "arrivals": [row]}
    assert store.record(erp, values())
    point = store.query("M20-history")["points"][-1]
    assert point["observed_at"] == "2026-09-01T10:01:00.000000+00:00"
    assert point["metrics"]["recorded"] == 10, "physical evidence is not a stock posting"
    assert not store.record(erp, values()), "polling must not create artificial activity"


def test_other_case_physical_evidence_does_not_shift_observation_time(tmp_path: Path) -> None:
    erp = packet()
    erp["receiving_work"] = {
        "case_id": "another-case",
        "arrivals": [{"barcode_matches": [{"observed_at": "2027-01-01T00:00:00+00:00"}]}],
    }
    store = OperationalHistory(tmp_path / "history.db")
    assert store.record(erp, values())
    assert store.query("M20-history")["points"][0]["observed_at"].startswith("2026-09-01")


def test_pre_fix_mixed_receipt_snapshot_is_retained_but_not_charted(tmp_path):
    path = tmp_path / "history.db"
    store = OperationalHistory(path)
    erp = packet()
    erp["documents"][0]["received"] = 1
    erp["receiving_work"] = {"case_id": "M20-history", "arrivals": [{
        "arrival_id": "arrival-1", "origin": "demo_scan", "capture_id": "capture-1",
        "receipt": {"name": "M20-PR-1"}, "posted_quantity": 1,
    }]}
    assert store.record(erp, values(1))
    # Reproduce the exact persisted pre-fix mixed snapshot, without rewriting
    # production history or relying on the newly guarded writer to create it.
    with sqlite3.connect(path) as db:
        raw = json.loads(db.execute(
            "SELECT observation_json FROM operational_observations"
        ).fetchone()[0])
        raw["documents"][0]["status"] = "DRAFT"
        raw["metrics"]["received_cumulative"] = 0
        db.execute("UPDATE operational_observations SET observation_json=?", (json.dumps(raw),))
    result = store.query("M20-history")
    assert result["points"] == []
    assert result["baseline"]["sample_count"] == 0
    assert result["excluded_observations"][0]["reason"] == "RECEIVING_RECEIPT_NOT_REFRESHED"
    assert result["coverage"]["status"] == "INCONSISTENT_ONLY"
    assert result["coverage"]["total_points"] == 1
    with sqlite3.connect(path) as db:
        assert json.loads(db.execute(
            "SELECT observation_json FROM operational_observations"
        ).fetchone()[0]) == raw


def test_restart_poll_dedup_and_reversion_are_append_only(tmp_path: Path) -> None:
    path = tmp_path / "history.db"
    store = OperationalHistory(path)
    assert store.record(packet(), values())
    assert not OperationalHistory(path).record(packet(day=2), values())
    assert store.record(packet(day=3, version="2"), values(8))
    # Correcting back to a previous value is a new observation, not a global hash duplicate.
    assert store.record(packet(day=4), values())
    points = OperationalHistory(path).query("M20-history")["points"]
    assert len(points) == 3
    assert [point["metrics"]["recorded"] for point in points] == [10, 8, 10]
    assert points[0]["documents"][0]["version"] == "1"
    assert points[1]["documents"][0]["version"] == "2"
    assert points[0]["observed_at"].startswith("2026-09-01")


def receiving_values(quantity: float = 1, *, fixed: bool = False) -> dict[str, object]:
    return {
        **values(quantity),
        "metric_version": "operational-facts.v1",
        **dict.fromkeys(
            ("booked_revenue", "billed_revenue", "value_protected"), None if fixed else 0
        ),
    }


def test_missing_sales_scope_correction_does_not_invent_a_new_arrival(tmp_path: Path) -> None:
    path = tmp_path / "history.db"
    store = OperationalHistory(path)
    assert store.record(packet(), receiving_values())
    assert not OperationalHistory(path).record(packet(day=2), receiving_values(fixed=True))
    projected = store.query("M20-history")
    assert len(projected["points"]) == 1
    assert projected["points"][0]["metrics"]["billed_revenue"] is None
    assert projected["points"][0]["observed_at"].startswith("2026-09-01")
    assert projected["metric_corrections"][0]["stored_value"] == 0
    with sqlite3.connect(path) as db:
        stored = json.loads(
            db.execute("SELECT observation_json FROM operational_observations").fetchone()[0]
        )
    assert stored["metrics"]["billed_revenue"] == 0, "original evidence is not overwritten"


def test_retained_projection_revision_is_disclosed_but_not_a_business_sample(
    tmp_path: Path,
) -> None:
    path = tmp_path / "history.db"
    store = OperationalHistory(path)
    store.record(packet(), receiving_values())
    # Reproduce the old writer already appending a corrected projection on restart.
    with sqlite3.connect(path) as db:
        raw = json.loads(
            db.execute("SELECT observation_json FROM operational_observations").fetchone()[0]
        )
        raw["metrics"].update(
            dict.fromkeys(("booked_revenue", "billed_revenue", "value_protected"))
        )
        raw["observed_at"] = "2026-09-02T10:00:00.000000+00:00"
        db.execute(
            "INSERT INTO operational_observations"
            "(case_id,source_id,observed_at,semantic_hash,observation_json) "
            "VALUES (?,?,?,?,?)",
            (raw["case_id"], raw["source_id"], raw["observed_at"], "old-writer", json.dumps(raw)),
        )
    result = store.query("M20-history")
    assert len(result["points"]) == 1
    assert len(result["projection_revisions"]) == 1
    assert result["projection_revisions"][0]["stored_record_id"] == 2
    assert result["coverage"]["total_points"] == 2
    assert result["coverage"]["truncated"] is False
    assert result["coverage"]["last_observed_at"].startswith("2026-09-01")
    assert result["baseline"]["sample_count"] == 0
    # Window/limit boundaries cannot turn the standalone revision into a sample.
    for query in ({"limit": 1}, {"since": "2026-09-02T00:00:00Z"}):
        scoped = store.query("M20-history", **query)
        assert scoped["points"] == []
        assert len(scoped["projection_revisions"]) == 1
        assert scoped["coverage"]["status"] == "REVISION_ONLY"
        assert scoped["coverage"]["last_retained_at"].startswith("2026-09-02")
    assert store.record(packet(day=3, version="2"), receiving_values(2, fixed=True))
    for query in ({"limit": 2}, {"since": "2026-09-02T00:00:00Z"}):
        mixed = store.query("M20-history", **query)
        assert len(mixed["points"]) == 1
        assert mixed["coverage"]["first_observed_at"].startswith("2026-09-03")
        assert mixed["coverage"]["last_observed_at"].startswith("2026-09-03")
        assert len(mixed["projection_revisions"]) == 1


@pytest.mark.parametrize("change", ["quantity", "document", "outage", "new_source"])
def test_projection_correction_never_hides_actual_source_changes(
    tmp_path: Path, change: str
) -> None:
    store = OperationalHistory(tmp_path / "history.db")
    store.record(packet(), receiving_values())
    current, metrics = packet(day=2), receiving_values(fixed=True)
    if change == "quantity":
        metrics = receiving_values(2, fixed=True)
    elif change == "document":
        current["documents"][0]["version"] = "2"
    elif change == "outage":
        current["status"] = "DEGRADED"
    else:
        current["source_id"] = "other-erp"
    assert store.record(current, metrics)
    assert len(store.query("M20-history")["points"]) == 2


def test_known_sales_scope_zero_is_not_reinterpreted_as_missing(tmp_path: Path) -> None:
    store = OperationalHistory(tmp_path / "history.db")
    evidence = packet()
    evidence["documents"].append({"kind": "sales_order", "name": "SO-1", "version": "1"})
    store.record(evidence, receiving_values())
    result = store.query("M20-history")
    assert result["points"][0]["metrics"]["billed_revenue"] == 0
    assert result["metric_corrections"] == []


@pytest.mark.parametrize(
    "lifecycle",
    [
        {"status": "DRAFT"},
        {"status": "CANCELLED"},
        {"status": "UNKNOWN"},
        {"status": "MISSING"},
        {"status": "SUBMITTED", "docstatus": 0},
        {"status": "TO_DELIVER", "docstatus": 2},
    ],
)
def test_nonposted_sales_document_does_not_create_a_commercial_scope(
    tmp_path: Path,
    lifecycle: dict[str, object],
) -> None:
    store = OperationalHistory(tmp_path / "history.db")
    evidence = packet()
    evidence["documents"].append(
        {
            "kind": "sales_order",
            "name": "SO-1",
            "version": "1",
            **lifecycle,
        }
    )
    store.record(evidence, receiving_values())
    assert not store.record(
        {**evidence, "received_at": packet(day=2)["received_at"]}, receiving_values(fixed=True)
    )
    result = store.query("M20-history")
    assert len(result["points"]) == 1
    assert result["points"][0]["metrics"]["billed_revenue"] is None
    assert result["metric_corrections"]


def test_explicit_posted_sales_document_overrides_stale_draft_label(tmp_path: Path) -> None:
    store = OperationalHistory(tmp_path / "history.db")
    evidence = packet()
    evidence["documents"].append(
        {
            "kind": "sales_invoice",
            "name": "SI-1",
            "version": "1",
            "status": "DRAFT",
            "docstatus": 1,
        }
    )
    store.record(evidence, receiving_values())
    result = store.query("M20-history")
    assert result["points"][0]["metrics"]["billed_revenue"] == 0
    assert result["metric_corrections"] == []


def test_late_source_effective_time_does_not_rewrite_observation_order(tmp_path: Path) -> None:
    store = OperationalHistory(tmp_path / "history.db")
    original = {**packet(), "effective_at": "2026-08-30T12:00:00Z"}
    correction = {**packet(day=2, version="2"), "effective_at": "2026-08-29T12:00:00Z"}
    assert store.record(original, values())
    assert store.record(correction, values(9))
    points = store.query("M20-history")["points"]
    assert points[0]["effective_at"] > points[1]["effective_at"]
    assert points[0]["observed_at"] < points[1]["observed_at"]
    assert all(point["time_basis"] == "observed_at" for point in points)


def test_backfill_is_explicit_and_overlapping_import_is_deduplicated(tmp_path: Path) -> None:
    store = OperationalHistory(tmp_path / "history.db")
    first = {**packet(), "observation_kind": "backfill", "effective_at": "2026-08-01T00:00:00Z"}
    second = {
        **packet(day=2),
        "observation_kind": "backfill",
        "effective_at": "2026-08-02T00:00:00Z",
    }
    assert store.record(first, values())
    assert store.record(second, values(20))
    assert not store.record({**first, "received_at": "2026-09-03T00:00:00Z"}, values())
    assert len(store.query("M20-history")["points"]) == 2
    with pytest.raises(ValueError, match="effective_at"):
        store.record({**packet(), "observation_kind": "backfill"}, values())


def test_missing_effective_time_is_not_invented(tmp_path: Path) -> None:
    store = OperationalHistory(tmp_path / "history.db")
    store.record(packet(), values())
    point = store.query("M20-history")["points"][0]
    assert point["effective_at"] is None
    assert point["documents"][0]["effective_at"] is None


def test_explicit_zero_source_version_and_document_effective_time_are_retained(
    tmp_path: Path,
) -> None:
    store = OperationalHistory(tmp_path / "history.db")
    evidence = packet()
    evidence["documents"][0].update(version=0, effective_at="2026-08-31T16:00:00-07:00")
    store.record(evidence, values())
    point = store.query("M20-history")["points"][0]
    assert point["documents"][0]["version"] == "0"
    assert point["documents"][0]["effective_at"] == "2026-08-31T23:00:00.000000+00:00"
    assert point["effective_at"] is None


def test_unknown_or_unbounded_metrics_are_null_and_private_payload_is_omitted(
    tmp_path: Path,
) -> None:
    store = OperationalHistory(tmp_path / "history.db")
    evidence = {
        **packet(),
        "api_secret": "secret-do-not-store",
        "credentials": {"token": "private"},
    }
    evidence["documents"][0]["raw_payload"] = {"token": "private"}
    evidence["documents"][0]["external_url"] = "https://example.com/?token=private"
    metrics = {
        **values(),
        "recorded": float("nan"),
        "po_unit_cost": float("inf"),
        "invoice_hold_value": 1e300,
        "gap": "12",
        "quality_hold": True,
        "purchase_price_variance": None,
        "prompt": "do-not-store",
    }
    assert store.record(evidence, metrics)
    result = store.query("M20-history")
    point = result["points"][0]
    for key in (
        "recorded",
        "po_unit_cost",
        "invoice_hold_value",
        "gap",
        "quality_hold",
        "purchase_price_variance",
    ):
        assert point["metrics"][key] is None
    encoded = json.dumps(result, allow_nan=False)
    assert "private" not in encoded
    assert "secret" not in encoded
    assert "prompt" not in encoded
    with sqlite3.connect(store.path) as connection:
        assert (
            "private"
            not in connection.execute(
                "SELECT observation_json FROM operational_observations"
            ).fetchone()[0]
        )


def test_outage_is_new_observation_not_healthy_zero(tmp_path: Path) -> None:
    store = OperationalHistory(tmp_path / "history.db")
    store.record(packet(), values())
    outage = {**packet(day=2), "status": "DEGRADED", "documents": []}
    assert store.record(outage, values())
    assert not store.record({**outage, "received_at": "2026-09-03T00:00:00Z"}, {})
    result = store.query("M20-history")
    assert all(value is None for value in result["points"][-1]["metrics"].values())
    assert result["baseline"]["status"] == "SOURCE_UNAVAILABLE"
    assert store.record(packet(day=4), values())
    assert len(store.query("M20-history")["points"]) == 3


def test_prior_comparable_baseline_excludes_current_and_other_currency(tmp_path: Path) -> None:
    store = OperationalHistory(tmp_path / "history.db")
    for day, quantity in enumerate((10, 20, 30), 1):
        store.record(packet(day=day), values(quantity))
    store.record(packet(day=4), values(1000, currency="EUR"))
    store.record(packet(day=5), values(40))
    baseline = store.query("M20-history")["baseline"]
    assert baseline["sample_count"] == 3
    assert baseline["status"] == "AVAILABLE"
    assert baseline["cohort"]["currency"] == "USD"
    assert baseline["time_weighted"] is False
    metric = baseline["metrics"]["recorded"]
    assert metric["previous_mean"] == 20
    assert metric["change"] == 20
    assert metric["change_percent"] == 100


@pytest.mark.parametrize(
    "field,value", [("uom", "Carton"), ("item_code", "M20-OTHER"), ("metric_version", "v2")]
)
def test_changed_cohort_does_not_borrow_baseline(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    store = OperationalHistory(tmp_path / "history.db")
    for day in range(1, 4):
        store.record(packet(day=day), values(day))
    store.record(packet(day=4), {**values(4), field: value})
    assert store.query("M20-history")["baseline"]["sample_count"] == 0


def test_zero_denominator_and_explicit_unknown_units_are_not_invented(tmp_path: Path) -> None:
    store = OperationalHistory(tmp_path / "history.db")
    for day in range(1, 5):
        store.record(packet(day=day, version=str(day)), values(0 if day < 4 else 5))
    metric = store.query("M20-history")["baseline"]["metrics"]["recorded"]
    assert metric["previous_mean"] == 0
    assert metric["change"] == 5
    assert metric["change_percent"] is None
    store.record(packet(day=5), {**values(5), "currency": None, "uom": None})
    point = store.query("M20-history")["points"][-1]
    assert point["currency"] is None
    assert point["uom"] is None


def test_source_and_case_scope_and_query_bounds(tmp_path: Path) -> None:
    store = OperationalHistory(tmp_path / "history.db")
    for day in range(1, 5):
        store.record(packet(day=day), values(day))
    store.record(packet(case="M20-other"), values(999))
    store.record({**packet(day=5), "source_id": "warehouse"}, values(25))
    result = store.query(
        "M20-history", limit=2, source_id="erpnext-missing20", since="2026-09-02T12:00:00+02:00"
    )
    assert [point["metrics"]["recorded"] for point in result["points"]] == [3, 4]
    assert result["coverage"]["total_points"] == 3
    assert result["coverage"]["truncated"] is True
    assert len(store.query("M20-other")["points"]) == 1
    assert store.query("' OR 1=1 --")["points"] == []


@pytest.mark.parametrize("limit", [0, -1, MAX_POINTS + 1, True, 1.5, "5"])
def test_invalid_limit_is_rejected(tmp_path: Path, limit: Any) -> None:
    with pytest.raises(ValueError, match="limit"):
        OperationalHistory(tmp_path / "history.db").query("M20", limit=limit)


@pytest.mark.parametrize("since", ["yesterday", "2026-09-01", "2026-09-01T12:00:00"])
def test_invalid_or_timezone_free_since_is_rejected(tmp_path: Path, since: str) -> None:
    with pytest.raises(ValueError, match="since"):
        OperationalHistory(tmp_path / "history.db").query("M20", since=since)


@pytest.mark.parametrize(
    "changes",
    [
        {"case_id": ""},
        {"source_id": ""},
        {"case_id": "M20\nother"},
        {"case_id": "x" * 201},
        {"received_at": "2026-09-01T00:00:00"},
    ],
)
def test_malformed_observation_is_rejected(tmp_path: Path, changes: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        OperationalHistory(tmp_path / "history.db").record({**packet(), **changes}, values())


def test_parallel_duplicate_writers_append_once(tmp_path: Path) -> None:
    path = tmp_path / "history.db"
    stores = [OperationalHistory(path) for _ in range(6)]
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = [executor.submit(store.record, packet(), values()) for store in stores]
        inserted = [future.result() for future in futures]
    assert sum(inserted) == 1
    assert len(stores[0].query("M20-history")["points"]) == 1


def test_duplicate_document_order_and_poll_metadata_do_not_create_change(tmp_path: Path) -> None:
    store = OperationalHistory(tmp_path / "history.db")
    original = packet()
    original["documents"].append({"kind": "purchase_order", "name": "M20-PO", "version": "2"})
    assert store.record(original, values())
    reordered = {**original, "documents": list(reversed(original["documents"]))}
    reordered["documents"].append(original["documents"][0])
    assert not store.record(reordered, {**values(), "source_sequence": 500})
