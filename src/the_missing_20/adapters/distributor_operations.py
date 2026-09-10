"""Small event dispatcher for the configured distributor demonstration cases.

The dispatcher retains operator inputs and their native-operation outcomes in a
local SQLite file.  It delegates ERP reads and writes to the narrowly scoped
``DistributorERP`` adapter.  It never turns a packaging count into stock, or a
Delivery Note or Shipment into proof of customer delivery.
"""

from __future__ import annotations

import json
import math
import sqlite3
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from pathlib import Path
from threading import RLock
from typing import Any, Protocol, cast

from the_missing_20.adapters.distributor_allocation import (
    ContractAllocationError,
    compile_plan,
    contract_mode,
    validate_contract_config,
)

DISTRIBUTOR_OPERATIONS_SCHEMA_VERSION = "missing20-distributor-operations/v1"
_SUCCESS = frozenset({"APPLIED", "ALREADY_APPLIED"})
_WRITE_STATUSES = _SUCCESS | frozenset({"UNKNOWN_OUTCOME", "BLOCKED"})
_EVENT_BRIEF_FIELDS: dict[str, tuple[str, ...]] = {
    "arrival": (
        "cartons",
        "expected_pack_quantity",
        "observed_stock_quantity",
        "item_code",
        "lot",
    ),
    "inspection": (
        "lot",
        "result",
        "scope",
        "metric",
        "measured",
        "sample_quantity",
        "inspection_report_ref",
    ),
    "picked": ("customer_order", "lot", "quantity", "pick_evidence_ref"),
    "carrier_pickup": ("shipment_id",),
    "delivery": ("shipment_id",),
}


class DistributorERP(Protocol):
    """The one small native ERP boundary used by the operations dispatcher."""

    def read_case(self, config: Mapping[str, object]) -> Mapping[str, object]: ...

    def apply_operation(
        self, config: Mapping[str, object], operation: Mapping[str, object], event_id: str
    ) -> Mapping[str, object]: ...


class DistributorEventConflict(ValueError):
    """An event ID was replayed with a different declared physical input."""


class _NativeOutcome:
    def __init__(
        self,
        *,
        kind: str,
        status: str,
        documents: list[dict[str, object]],
        error_code: str | None,
    ) -> None:
        self.kind = kind
        self.status = status
        self.documents = documents
        self.error_code = error_code

    @property
    def succeeded(self) -> bool:
        return self.status in _SUCCESS

    def record(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "status": self.status,
            "documents": _copy(self.documents),
            "error_code": self.error_code,
        }


def _copy(value: object) -> Any:
    """Detach a strict JSON value; reject non-finite or non-JSON inputs."""

    return json.loads(_encode(value))


def _json_value(value: object) -> object:
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("JSON mapping keys must be strings")
            result[key] = _json_value(item)
        return result
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("JSON numbers must be finite")
        return value
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    raise ValueError(f"unsupported JSON value: {type(value).__name__}")


def _encode(value: object) -> str:
    return json.dumps(_json_value(value), sort_keys=True, separators=(",", ":"), allow_nan=False)


def _decoded(value: str, label: str) -> dict[str, object]:
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError as error:  # pragma: no cover - corrupt local store only
        raise RuntimeError(f"corrupt distributor operations {label}") from error
    if not isinstance(decoded, dict):  # pragma: no cover - corrupt local store only
        raise RuntimeError(f"corrupt distributor operations {label}")
    return cast(dict[str, object], _json_value(decoded))


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 256:
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


def _quantity(value: object, label: str, *, positive: bool = False) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a JSON number")
    try:
        result = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError(f"{label} must be a JSON number") from error
    if not result.is_finite() or result < 0 or (positive and result <= 0):
        raise ValueError(f"{label} must be {'positive' if positive else 'non-negative'}")
    return result


def _whole(value: object, label: str, *, positive: bool = False) -> int:
    quantity = _quantity(value, label, positive=positive)
    if quantity != quantity.to_integral_value():
        raise ValueError(f"{label} must be a whole number")
    return int(quantity)


def _wire(value: Decimal) -> int | float:
    return int(value) if value == value.to_integral_value() else float(value)


def _utc(value: object, label: str) -> str:
    text = _text(value, label)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{label} must be an ISO-8601 time with timezone") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must be an ISO-8601 time with timezone")
    return parsed.astimezone(UTC).isoformat()


def _deadline(value: object, label: str) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(_utc(value, label))


def _documents(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    records: list[dict[str, object]] = []
    for raw in value:
        if not isinstance(raw, Mapping):
            continue
        kind = raw.get("kind")
        name = raw.get("name")
        status = raw.get("status")
        if not (
            isinstance(kind, str)
            and kind.strip()
            and isinstance(name, str)
            and name.strip()
            and isinstance(status, str)
            and status.strip()
        ):
            continue
        record: dict[str, object] = {
            "kind": kind.strip(),
            "name": name.strip(),
            "status": status.strip(),
        }
        url = raw.get("url")
        if isinstance(url, str) and url.strip():
            record["url"] = url.strip()
        records.append(record)
    return records


def _merge_documents(*groups: list[dict[str, object]]) -> list[dict[str, object]]:
    by_identity: dict[tuple[str, str], dict[str, object]] = {}
    for group in groups:
        for document in group:
            kind = document.get("kind")
            name = document.get("name")
            if isinstance(kind, str) and isinstance(name, str):
                by_identity[(kind, name)] = dict(document)
    return [by_identity[key] for key in sorted(by_identity)]


class DistributorOperations:
    """Serialize one configured case's physical events and native terminal effects.

    A bridge call is never retried by this class after an ``UNKNOWN_OUTCOME``.
    The local lock is intentionally one operator/runtime lock rather than a
    distributed workflow protocol.
    """

    def __init__(
        self,
        database: Path,
        config: Mapping[str, object],
        erp: DistributorERP | None,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        ask_turn: Callable[[str, Mapping[str, object]], Mapping[str, object]] | None = None,
        allocation_selector: Callable[[Mapping[str, object]], Mapping[str, object]] | None = None,
    ) -> None:
        self._config = self._validate_config(config)
        self._erp = erp
        self._clock = clock
        self._ask_turn = ask_turn
        self._allocation_selector = allocation_selector
        database.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(
            database, check_same_thread=False, isolation_level=None, timeout=10
        )
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS distributor_operation_events "
            "(event_id TEXT PRIMARY KEY, payload_json TEXT NOT NULL, result_json TEXT, "
            "state_json TEXT, recorded_at TEXT NOT NULL)"
        )
        self._lock = RLock()

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def projection(self) -> dict[str, object]:
        """Return a current read-only projection; a source poll never writes."""

        with self._lock:
            source = self._read_source()
            state = self._latest_state() or self._initial_state()
            state, source = self._merge_source(state, source)
            return self._projection(state, source)

    def record_event(self, event: Mapping[str, object]) -> dict[str, object]:
        """Retain one physical event and run only its allowed native consequences."""

        validated = self._validate_event(event)
        event_id = cast(str, validated["event_id"])
        encoded = _encode(validated)
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                row = self._db.execute(
                    "SELECT payload_json, result_json FROM distributor_operation_events "
                    "WHERE event_id=?",
                    (event_id,),
                ).fetchone()
                if row is not None:
                    stored_payload, stored_result = cast(tuple[str, str | None], row)
                    if stored_payload != encoded:
                        raise DistributorEventConflict(
                            "A duplicate distributor event ID has different input."
                        )
                    self._db.commit()
                    if stored_result is not None:
                        return self._projection_from_record(stored_result)
                    return self._pending_projection(event_id)
                self._db.execute(
                    "INSERT INTO distributor_operation_events "
                    "(event_id, payload_json, result_json, state_json, recorded_at) "
                    "VALUES (?, ?, NULL, NULL, ?)",
                    (event_id, encoded, self._now().isoformat()),
                )
                self._db.commit()
            except Exception:
                self._db.rollback()
                raise

            source = self._read_source()
            state = self._latest_state() or self._initial_state()
            state, source = self._merge_source(state, source)
            try:
                next_state, event_status = self._advance(state, validated, source)
            except Exception:  # pragma: no cover - defensive local persistence boundary
                next_state = _copy(state)
                self._alert(
                    next_state,
                    code="LOCAL_OPERATION_UNAVAILABLE",
                    message="The event was retained, but no additional native action was started.",
                    event=validated,
                )
                event_status = "UNKNOWN_OUTCOME"
                self._append_event(next_state, validated, event_status, [])
            else:
                if event_status == "APPLIED" and validated["type"] in {"arrival", "picked"}:
                    self._resume_blocked_shipment(next_state, validated)
            projection = self._projection(next_state, source)
            self._db.execute("BEGIN IMMEDIATE")
            try:
                self._db.execute(
                    "UPDATE distributor_operation_events SET result_json=?, state_json=? "
                    "WHERE event_id=?",
                    (_encode(projection), _encode(next_state), event_id),
                )
                self._db.commit()
            except Exception:
                self._db.rollback()
                raise
            return projection

    def reconcile_receive_arrival(self, event_id: str) -> dict[str, object]:
        """Admit an exact submitted receipt for the latest unknown arrival without retrying it."""

        identifier = _text(event_id, "event_id")
        with self._lock:
            state = self._latest_state()
            if state is None:
                raise ValueError("No retained distributor event can be reconciled.")
            event = self._reconcilable_receive_event(state, identifier)
            if self._has_receive_reconciliation(state, identifier):
                source = self._read_source()
                state, source = self._merge_source(state, source)
                return self._projection(state, source)
            bridge = self._erp
            reconcile = getattr(bridge, "reconcile_receive_arrival", None)
            if not callable(reconcile):
                return self._receive_reconciliation_projection(
                    state, identifier, "UNAVAILABLE", "ERP_RECONCILIATION_UNAVAILABLE"
                )
            try:
                raw = reconcile(self._config, event, identifier)
            except Exception:
                return self._receive_reconciliation_projection(
                    state, identifier, "UNAVAILABLE", "ERP_RECONCILIATION_READ_FAILED"
                )
            if not isinstance(raw, Mapping) or raw.get("operation") != "receive_arrival":
                return self._receive_reconciliation_projection(
                    state, identifier, "UNAVAILABLE", "ERP_RECONCILIATION_MALFORMED"
                )
            status = raw.get("status")
            error_code = raw.get("error_code")
            if status != "APPLIED" or raw.get("event_id") != identifier:
                return self._receive_reconciliation_projection(
                    state,
                    identifier,
                    status if isinstance(status, str) else "UNAVAILABLE",
                    error_code if isinstance(error_code, str) and error_code else None,
                )
            snapshot = raw.get("snapshot")
            if not isinstance(snapshot, Mapping) or snapshot.get("source_status") != "CURRENT":
                return self._receive_reconciliation_projection(
                    state, identifier, "UNAVAILABLE", "ERP_RECONCILIATION_SOURCE_UNAVAILABLE"
                )
            if (
                snapshot.get("case_id") != self._config["case_id"]
                or snapshot.get("case_label") != self._config["case_label"]
                or snapshot.get("synthetic_input") is not self._config["synthetic_input"]
            ):
                return self._receive_reconciliation_projection(
                    state, identifier, "UNAVAILABLE", "ERP_RECONCILIATION_SCOPE_MISMATCH"
                )
            try:
                source = self._canonical_source(snapshot)
            except ValueError:
                return self._receive_reconciliation_projection(
                    state, identifier, "UNAVAILABLE", "ERP_RECONCILIATION_SOURCE_MALFORMED"
                )
            documents = _documents(raw.get("documents"))
            if len(documents) != 1 or documents[0].get("kind") != "Purchase Receipt":
                return self._receive_reconciliation_projection(
                    state, identifier, "UNAVAILABLE", "ERP_RECONCILIATION_RECEIPT_MALFORMED"
                )
            updated = self._apply_receive_reconciliation(state, event, source, documents)
            projection = self._projection(updated, source)
            self._db.execute("BEGIN IMMEDIATE")
            try:
                self._db.execute(
                    "UPDATE distributor_operation_events SET state_json=? WHERE event_id=?",
                    (_encode(updated), identifier),
                )
                self._db.commit()
            except Exception:
                self._db.rollback()
                raise
            return projection

    def _reconcilable_receive_event(
        self, state: Mapping[str, object], event_id: str
    ) -> dict[str, object]:
        """Return only the latest retained arrival with an unknown native receipt outcome."""

        events = state.get("events")
        if not isinstance(events, list) or not events:
            raise ValueError("No retained distributor event can be reconciled.")
        latest = events[-1]
        if not isinstance(latest, Mapping) or latest.get("event_id") != event_id:
            raise ValueError("Only the latest retained event can be reconciled.")
        operations = latest.get("operations")
        if (
            latest.get("type") != "arrival"
            or latest.get("status") != "UNKNOWN_OUTCOME"
            or not isinstance(operations, list)
            or not any(
                isinstance(operation, Mapping)
                and operation.get("kind") == "receive_arrival"
                and operation.get("status") == "UNKNOWN_OUTCOME"
                for operation in operations
            )
        ):
            raise ValueError("This event is not an unknown arrival outcome.")
        event = self._stored_event(event_id)
        if event is None or event.get("type") != "arrival":
            raise ValueError("The retained arrival payload is unavailable.")
        return event

    @staticmethod
    def _has_receive_reconciliation(state: Mapping[str, object], event_id: str) -> bool:
        events = state.get("events")
        if not isinstance(events, list):
            return False
        for event in events:
            if not isinstance(event, Mapping) or event.get("event_id") != event_id:
                continue
            reconciliations = event.get("reconciliations")
            return isinstance(reconciliations, list) and any(
                isinstance(record, Mapping)
                and record.get("operation") == "receive_arrival"
                and record.get("status") == "NATIVE_CONFIRMED"
                for record in reconciliations
            )
        return False

    def _receive_reconciliation_projection(
        self,
        state: Mapping[str, object],
        event_id: str,
        status: str,
        error_code: str | None,
    ) -> dict[str, object]:
        """Expose a read-only failed admission without changing retained event history."""

        source = self._read_source()
        merged, source = self._merge_source(state, source)
        projection = self._projection(merged, source)
        projection["reconciliation"] = {
            "event_id": event_id,
            "operation": "receive_arrival",
            "status": status,
            **({"error_code": error_code} if error_code else {}),
        }
        return projection

    def _apply_receive_reconciliation(
        self,
        state: Mapping[str, object],
        event: Mapping[str, object],
        source: Mapping[str, object],
        documents: list[dict[str, object]],
    ) -> dict[str, object]:
        """Project exact read-back facts while retaining the original unknown operation."""

        updated = cast(dict[str, object], _copy(state))
        source_quantities = cast(Mapping[str, object], source["quantities"])
        quantities = cast(dict[str, object], updated["quantities"])
        initial_expected_cartons = quantities.get("initial_expected_cartons")
        quantities.update(_copy(source_quantities))
        if initial_expected_cartons is not None:
            quantities["initial_expected_cartons"] = initial_expected_cartons
        quantities["observed_outer_packages"] = source_quantities["cartons"]

        old_lots = {
            row.get("lot"): row
            for row in cast(list[Mapping[str, object]], updated["lots"])
            if isinstance(row.get("lot"), str)
        }
        reconciled_lots: list[dict[str, object]] = []
        for raw_lot in cast(list[Mapping[str, object]], source["lots"]):
            lot_name = _text(raw_lot.get("lot"), "source lot")
            prior = old_lots.get(lot_name)
            if prior is None:  # pragma: no cover - canonical source already checks scope
                raise ValueError("source lot scope mismatch")
            row = cast(dict[str, object], _copy(prior))
            for field in ("expected_quantity", "cartons", "received", "usable", "held", "status"):
                row[field] = _copy(raw_lot[field])
            reconciled_lots.append(row)
        updated["lots"] = reconciled_lots
        updated["allocations"] = _copy(source["allocations"])
        updated["documents"] = _merge_documents(
            _documents(updated.get("documents")),
            _documents(source.get("documents")),
            documents,
        )
        parent_purchase_order = source.get("parent_purchase_order")
        if isinstance(parent_purchase_order, Mapping):
            updated["parent_purchase_order"] = _copy(parent_purchase_order)
        else:
            updated.pop("parent_purchase_order", None)
        updated["source_status"] = "CURRENT"
        updated["source_error"] = None
        updated["source_observation"] = {
            "quantities": _copy(source["quantities"]),
            "lots": _copy(source["lots"]),
            "allocations": _copy(source["allocations"]),
            "documents": _copy(source["documents"]),
            "parent_purchase_order": _copy(parent_purchase_order)
            if isinstance(parent_purchase_order, Mapping)
            else None,
        }

        event_id = _text(event["event_id"], "event_id")
        reconciliation = {
            "operation": "receive_arrival",
            "status": "NATIVE_CONFIRMED",
            "documents": _copy(documents),
            "reconciled_at": self._now().isoformat(),
        }
        events = cast(list[dict[str, object]], updated["events"])
        matching = [row for row in events if row.get("event_id") == event_id]
        if len(matching) != 1:  # pragma: no cover - retained state is internal
            raise RuntimeError("reconciliation event history is unavailable")
        record = matching[0]
        reconciliations = record.get("reconciliations")
        if not isinstance(reconciliations, list):
            reconciliations = []
            record["reconciliations"] = reconciliations
        reconciliations.append(reconciliation)
        self._resolve_receive_unknown_alert(updated, event_id)

        lot_name = _text(event["lot"], "lot")
        lot = self._lot(updated, lot_name)
        policy = cast(Mapping[str, object], self._config["policy"])
        if (
            policy["inspection_required"] is True
            and lot is not None
            and _quantity(lot.get("held"), "lot held") > 0
        ):
            self._alert(
                updated,
                code="QUALITY_EVIDENCE_REQUIRED",
                message="Received stock is held until configured inspection evidence is recorded.",
                event=event,
                lot=lot_name,
                quantity=_quantity(lot["held"], "lot held"),
            )
        return updated

    @staticmethod
    def _resolve_receive_unknown_alert(state: dict[str, object], event_id: str) -> None:
        for alert in cast(list[dict[str, object]], state["alerts"]):
            if (
                alert.get("code") == "NATIVE_OPERATION_UNKNOWN"
                and alert.get("operation") == "receive_arrival"
                and alert.get("event_id") == event_id
                and alert.get("status") == "OPEN"
            ):
                alert["status"] = "RESOLVED"

    def ask(self, question: str) -> dict[str, object]:
        """Run an injected read-only conversation turn, never an event or ERP write."""

        clean = " ".join(question.split()) if isinstance(question, str) else ""
        if not clean or len(question) > 500:
            raise ValueError(
                "Ask a specific distributor evidence question using at most 500 characters."
            )
        projection = self.projection()
        if self._ask_turn is None:
            prior_conversation = projection.get("conversation")
            return {
                **projection,
                "conversation": list(prior_conversation)
                if isinstance(prior_conversation, list)
                else [],
                "conversation_status": "UNAVAILABLE",
                "conversation_message": "The distributor read-only conversation is not configured.",
            }
        result = self._ask_turn(clean, projection)
        if not isinstance(result, Mapping):
            raise ValueError("Distributor conversation returned an invalid read-only result.")
        if result.get("status") != "COMPLETE":
            detail = result.get("detail")
            message = (
                detail.strip()
                if isinstance(detail, str) and detail.strip()
                else (
                    "The distributor read-only conversation is unavailable; "
                    "no fallback answer was used."
                )
            )
            return {
                **projection,
                "conversation": {"status": "UNAVAILABLE", "message": message},
                "conversation_status": "UNAVAILABLE",
                "conversation_message": message,
            }
        answer = result.get("answer")
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("Distributor conversation returned no displayable answer.")
        conversation = {
            "status": "COMPLETE",
            "answer": answer.strip(),
            "provider": result.get("provider"),
            "session_id": result.get("session_id"),
            "context": "Current case-scoped ERP facts and retained physical event evidence",
            "read_only": True,
        }
        return {**projection, "conversation": conversation}

    def _validate_config(self, config: Mapping[str, object]) -> dict[str, object]:
        normalized = cast(dict[str, object], _copy(config))
        for field in (
            "case_id",
            "case_label",
            "company",
            "item_code",
            "uom",
        ):
            _text(normalized.get(field), field)
        if type(normalized.get("synthetic_input")) is not bool:
            raise ValueError("synthetic_input must be a boolean")
        _whole(normalized.get("cartons"), "cartons", positive=True)
        _quantity(normalized.get("expected_pack_quantity"), "expected_pack_quantity", positive=True)
        policy = normalized.get("policy")
        if not isinstance(policy, Mapping) or any(
            type(policy.get(name)) is not bool
            for name in ("inspection_required", "reservation_supported")
        ):
            raise ValueError(
                "policy requires inspection_required and reservation_supported booleans"
            )
        criteria = policy.get("inspection_criteria")
        if policy["inspection_required"] is True:
            if not isinstance(criteria, Mapping) or not criteria:
                raise ValueError("inspection-required policy needs configured inspection_criteria")
            for metric, bounds in criteria.items():
                _text(metric, "inspection metric")
                if not isinstance(bounds, Mapping) or set(bounds) != {"minimum", "maximum"}:
                    raise ValueError("inspection criteria require minimum and maximum")
                if _quantity(bounds["minimum"], "inspection minimum") > _quantity(
                    bounds["maximum"], "inspection maximum"
                ):
                    raise ValueError("inspection criterion minimum cannot exceed maximum")
        elif criteria is not None:
            raise ValueError("inspection_criteria requires inspection_required")
        lots = normalized.get("lots")
        if not isinstance(lots, list) or not lots:
            raise ValueError("lots requires at least one configured lot")
        seen_lots: set[str] = set()
        replacement_lots: dict[str, str] = {}
        for row in lots:
            if not isinstance(row, Mapping):
                raise ValueError("lots must contain JSON objects")
            lot = _text(row.get("lot"), "lot")
            if lot in seen_lots:
                raise ValueError("lot identities must be unique")
            seen_lots.add(lot)
            _quantity(row.get("expected_quantity"), "expected_quantity", positive=True)
            if "cartons" in row:
                _whole(row["cartons"], "lot cartons", positive=True)
            if "expected_pack_quantity" in row:
                _quantity(row["expected_pack_quantity"], "expected_pack_quantity", positive=True)
            replacement = row.get("replacement_for_lot")
            if replacement is not None:
                replacement_lots[lot] = _text(replacement, "replacement_for_lot")
        if any(
            target not in seen_lots or target == lot for lot, target in replacement_lots.items()
        ):
            raise ValueError("replacement_for_lot must name another configured lot")
        allocations = normalized.get("allocations")
        if not isinstance(allocations, list) or not allocations:
            raise ValueError("allocations requires at least one configured customer order")
        seen_orders: set[str] = set()
        for row in allocations:
            if not isinstance(row, Mapping):
                raise ValueError("allocations must contain JSON objects")
            order = _text(row.get("customer_order"), "customer_order")
            if order in seen_orders:
                raise ValueError("customer orders must be unique")
            seen_orders.add(order)
            _quantity(row.get("requested_quantity"), "requested_quantity", positive=True)
            _whole(row.get("priority"), "priority", positive=True)
        try:
            validate_contract_config(normalized)
        except ContractAllocationError as error:
            raise ValueError(str(error)) from error
        if contract_mode(normalized):
            for row in allocations:
                row["promised_delivery_at"] = _utc(
                    row["promised_delivery_at"], "promised_delivery_at"
                )
            tranches = normalized.get("pick_tranches")
            if not isinstance(tranches, list) or not tranches:
                raise ValueError("contract allocation requires configured native pick_tranches")
            for tranche in tranches:
                if not isinstance(tranche, Mapping):
                    raise ValueError("contract native pick tranche must be an object")
                _text(tranche.get("customer_order"), "contract native pick tranche customer_order")
                _quantity(
                    tranche.get("quantity"), "contract native pick tranche quantity", positive=True
                )
        for name in ("expected_at", "promised_delivery_at"):
            if name in normalized:
                _deadline(normalized[name], name)
        shipping = normalized.get("shipping")
        if shipping is not None:
            if not isinstance(shipping, Mapping) or not isinstance(
                shipping.get("shipments"), Mapping
            ):
                raise ValueError("shipping shipments must be a mapping when configured")
            for order, details in shipping["shipments"].items():
                _text(order, "shipping customer order")
                if order not in seen_orders or not isinstance(details, Mapping):
                    raise ValueError("shipping must contain configured customer-order details")
                _text(details.get("delivery_address"), "shipping delivery address")
                _text(details.get("shipment_id_prefix"), "shipping shipment ID prefix")
        return normalized

    def _validate_event(self, event: Mapping[str, object]) -> dict[str, object]:
        payload = cast(dict[str, object], _copy(event))
        event_type = payload.get("type")
        required = {
            "arrival": {
                "event_id",
                "type",
                "occurred_at",
                "evidence_ref",
                "synthetic",
                "cartons",
                "expected_pack_quantity",
                "observed_stock_quantity",
                "item_code",
                "lot",
            },
            "inspection": {
                "event_id",
                "type",
                "occurred_at",
                "evidence_ref",
                "synthetic",
                "lot",
                "result",
                "scope",
                "metric",
                "measured",
                "sample_quantity",
                "inspection_report_ref",
            },
            "picked": {
                "event_id",
                "type",
                "occurred_at",
                "evidence_ref",
                "synthetic",
                "customer_order",
                "lot",
                "quantity",
                "pick_evidence_ref",
            },
            "carrier_pickup": {
                "event_id",
                "type",
                "occurred_at",
                "evidence_ref",
                "synthetic",
                "shipment_id",
            },
            "delivery": {
                "event_id",
                "type",
                "occurred_at",
                "evidence_ref",
                "synthetic",
                "shipment_id",
            },
        }
        if (
            not isinstance(event_type, str)
            or event_type not in required
            or set(payload) != required[event_type]
        ):
            raise ValueError("Distributor event has missing or unexpected fields.")
        _text(payload.get("event_id"), "event_id")
        _utc(payload.get("occurred_at"), "occurred_at")
        _text(payload.get("evidence_ref"), "evidence_ref")
        if (
            type(payload.get("synthetic")) is not bool
            or payload["synthetic"] != self._config["synthetic_input"]
        ):
            raise ValueError("event synthetic flag must match this configured case")
        if event_type == "arrival":
            _whole(payload.get("cartons"), "cartons", positive=True)
            _quantity(
                payload.get("expected_pack_quantity"), "expected_pack_quantity", positive=True
            )
            _quantity(
                payload.get("observed_stock_quantity"), "observed_stock_quantity", positive=True
            )
            _text(payload.get("item_code"), "item_code")
            _text(payload.get("lot"), "lot")
        elif event_type == "inspection":
            _text(payload.get("lot"), "lot")
            if payload.get("result") not in {"PASS", "FAIL"}:
                raise ValueError("inspection result must be PASS or FAIL")
            if payload.get("scope") not in {"SAMPLE", "WHOLE_LOT"}:
                raise ValueError("inspection scope must be SAMPLE or WHOLE_LOT")
            _text(payload.get("metric"), "metric")
            _quantity(payload.get("measured"), "measured")
            _quantity(payload.get("sample_quantity"), "sample_quantity", positive=True)
            _text(payload.get("inspection_report_ref"), "inspection_report_ref")
        elif event_type == "picked":
            _text(payload.get("customer_order"), "customer_order")
            _text(payload.get("lot"), "lot")
            _quantity(payload.get("quantity"), "quantity", positive=True)
            _text(payload.get("pick_evidence_ref"), "pick_evidence_ref")
        else:
            _text(payload.get("shipment_id"), "shipment_id")
        return payload

    def _read_source(self) -> dict[str, object]:
        if self._erp is None:
            return self._source_unavailable("ERP_ADAPTER_UNAVAILABLE")
        try:
            source = self._erp.read_case(self._config)
        except Exception:
            return self._source_unavailable("ERP_SOURCE_UNAVAILABLE")
        if not isinstance(source, Mapping):
            return self._source_unavailable("ERP_SOURCE_MALFORMED")
        try:
            copied = cast(dict[str, object], _copy(source))
            if copied.get("source_status") != "CURRENT":
                return self._source_unavailable(
                    _text(copied.get("source_error") or "ERP_SOURCE_UNAVAILABLE", "source_error")
                )
            if (
                copied.get("case_id") != self._config["case_id"]
                or copied.get("case_label") != self._config["case_label"]
                or copied.get("synthetic_input") is not self._config["synthetic_input"]
            ):
                return self._source_unavailable("ERP_SOURCE_SCOPE_MISMATCH")
            return self._canonical_source(copied)
        except ValueError:
            return self._source_unavailable("ERP_SOURCE_MALFORMED")

    @staticmethod
    def _source_unavailable(error_code: str) -> dict[str, object]:
        return {"source_status": "UNAVAILABLE", "source_error": error_code}

    def _canonical_source(self, source: Mapping[str, object]) -> dict[str, object]:
        raw_quantities = source.get("quantities")
        if not isinstance(raw_quantities, Mapping):
            raise ValueError("source quantities are required")
        expected = sum(
            (
                _quantity(row["expected_quantity"], "expected_quantity")
                for row in cast(list[Mapping[str, object]], self._config["lots"])
            ),
            Decimal(),
        )
        quantity_fields = (
            "ordered",
            "received",
            "usable",
            "held",
            "missing",
            "allocated",
            "dispatched",
            "delivery_confirmed",
        )
        quantities: dict[str, object] = {
            field: _wire(_quantity(raw_quantities.get(field), f"source {field}"))
            for field in quantity_fields
        }
        quantities["cartons"] = _whole(raw_quantities.get("cartons"), "source cartons")
        quantities["uom"] = _text(raw_quantities.get("uom"), "source uom")
        if (
            quantities["uom"] != self._config["uom"]
            or _quantity(quantities["ordered"], "source ordered") != expected
        ):
            raise ValueError("source case quantity mismatch")
        received = _quantity(quantities["received"], "source received")
        if (
            _quantity(quantities["missing"], "source missing") != expected - received
            or _quantity(quantities["usable"], "source usable")
            + _quantity(quantities["held"], "source held")
            + _quantity(quantities["dispatched"], "source dispatched")
            != received
        ):
            raise ValueError("source quantities do not conserve stock")
        lots = self._canonical_source_lots(source.get("lots"))
        allocations = self._canonical_source_allocations(source.get("allocations"))
        parent_purchase_order = self._canonical_parent_purchase_order(
            source.get("parent_purchase_order"), quantities
        )
        raw_documents = source.get("documents")
        documents = _documents(raw_documents)
        if not isinstance(raw_documents, list) or len(documents) != len(raw_documents):
            raise ValueError("source documents are malformed")
        canonical: dict[str, object] = {
            "source_status": "CURRENT",
            "documents": documents,
            "quantities": quantities,
            "lots": lots,
            "allocations": allocations,
        }
        if parent_purchase_order is not None:
            canonical["parent_purchase_order"] = parent_purchase_order
        return canonical

    def _canonical_parent_purchase_order(
        self, raw_parent: object, quantities: Mapping[str, object]
    ) -> dict[str, object] | None:
        """Expose the verified full PO balance separately from this configured case."""

        if raw_parent is None:
            return None
        if not isinstance(raw_parent, Mapping):
            raise ValueError("parent purchase order is malformed")
        name = _text(raw_parent.get("name"), "parent purchase order name")
        ordered = _quantity(raw_parent.get("ordered"), "parent purchase order ordered")
        received = _quantity(raw_parent.get("received"), "parent purchase order received")
        uom = _text(raw_parent.get("uom"), "parent purchase order uom")
        case_received = _quantity(quantities.get("received"), "source received")
        case_ordered = _quantity(quantities.get("ordered"), "source ordered")
        if (
            name != self._config["purchase_order"]
            or uom != self._config["uom"]
            or ordered < case_ordered
            or received < case_received
            or received > ordered
        ):
            raise ValueError("parent purchase order scope mismatch")
        return {
            "name": name,
            "ordered": _wire(ordered),
            "received": _wire(received),
            "outside_case_received": _wire(received - case_received),
            "uom": uom,
        }

    def _canonical_source_lots(self, raw_lots: object) -> list[dict[str, object]]:
        if not isinstance(raw_lots, list):
            raise ValueError("source lots are required")
        expected = {
            _text(row["lot"], "lot"): _quantity(row["expected_quantity"], "expected_quantity")
            for row in cast(list[Mapping[str, object]], self._config["lots"])
        }
        result: dict[str, dict[str, object]] = {}
        for raw in raw_lots:
            if not isinstance(raw, Mapping):
                raise ValueError("source lot is malformed")
            name = _text(raw.get("lot"), "source lot")
            if name not in expected or name in result:
                raise ValueError("source lot scope mismatch")
            received = _quantity(raw.get("received"), "source lot received")
            usable = _quantity(raw.get("usable"), "source lot usable")
            held = _quantity(raw.get("held"), "source lot held")
            if (
                _quantity(raw.get("expected_quantity"), "source expected quantity")
                != expected[name]
                or received > expected[name]
                or usable + held > received
            ):
                raise ValueError("source lot facts conflict")
            result[name] = {
                "lot": name,
                "expected_quantity": _wire(expected[name]),
                "cartons": _whole(raw.get("cartons"), "source lot cartons"),
                "received": _wire(received),
                "usable": _wire(usable),
                "held": _wire(held),
                "status": _text(raw.get("status"), "source lot status"),
            }
        if set(result) != set(expected):
            raise ValueError("source lots are incomplete")
        return [result[name] for name in sorted(result)]

    def _canonical_source_allocations(self, raw_allocations: object) -> list[dict[str, object]]:
        if not isinstance(raw_allocations, list):
            raise ValueError("source allocations are required")
        expected = {
            _text(row["customer_order"], "customer_order"): (
                _quantity(row["requested_quantity"], "requested_quantity"),
                _whole(row["priority"], "priority", positive=True),
            )
            for row in cast(list[Mapping[str, object]], self._config["allocations"])
        }
        result: dict[str, dict[str, object]] = {}
        for raw in raw_allocations:
            if not isinstance(raw, Mapping):
                raise ValueError("source allocation is malformed")
            order = _text(raw.get("customer_order"), "source customer order")
            configured = expected.get(order)
            if configured is None or order in result:
                raise ValueError("source allocation scope mismatch")
            requested = _quantity(raw.get("requested_quantity"), "source requested quantity")
            priority = _whole(raw.get("priority"), "source priority", positive=True)
            allocated = _quantity(raw.get("allocated"), "source allocated")
            backordered = _quantity(raw.get("backordered"), "source backordered")
            dispatched = _quantity(raw.get("dispatched"), "source dispatched")
            if (
                requested != configured[0]
                or priority != configured[1]
                or allocated + backordered + dispatched != requested
            ):
                raise ValueError("source allocation facts conflict")
            result[order] = {
                "customer_order": order,
                "requested_quantity": _wire(requested),
                "priority": priority,
                "allocated": _wire(allocated),
                "backordered": _wire(backordered),
                "dispatched": _wire(dispatched),
                "reservation": _text(raw.get("reservation"), "source reservation"),
            }
        if set(result) != set(expected):
            raise ValueError("source allocations are incomplete")
        return [result[name] for name in sorted(result)]

    def _initial_state(self) -> dict[str, object]:
        allocations = cast(list[Mapping[str, object]], self._config["allocations"])
        lots = cast(list[Mapping[str, object]], self._config["lots"])
        planned = sum(
            (_quantity(row["requested_quantity"], "requested_quantity") for row in allocations),
            Decimal(),
        )
        lot_rows = [
            {
                "lot": _text(row["lot"], "lot"),
                "expected_quantity": _wire(
                    _quantity(row["expected_quantity"], "expected_quantity")
                ),
                "expected_pack_quantity": _wire(
                    _quantity(
                        row.get("expected_pack_quantity", self._config["expected_pack_quantity"]),
                        "expected_pack_quantity",
                        positive=True,
                    )
                ),
                "cartons": 0,
                "received": 0,
                "usable": 0,
                "held": 0,
                "status": "AWAITING_ARRIVAL",
            }
            for row in lots
        ]
        for row, lot in zip(lots, lot_rows, strict=True):
            replacement = row.get("replacement_for_lot")
            if replacement is not None:
                lot["replacement_for_lot"] = _text(replacement, "replacement_for_lot")
        initial_expected_cartons = self._initial_expected_cartons(lots)
        return {
            "case_id": self._config["case_id"],
            "case_label": self._config["case_label"],
            "synthetic_input": self._config["synthetic_input"],
            "quantities": {
                "ordered": _wire(planned),
                "received": 0,
                "usable": 0,
                "held": 0,
                "missing": _wire(planned),
                "allocated": 0,
                "dispatched": 0,
                "delivery_confirmed": 0,
                "uom": self._config["uom"],
                "cartons": 0,
                "initial_expected_cartons": initial_expected_cartons,
                "observed_outer_packages": 0,
            },
            "lots": lot_rows,
            "allocations": [
                {
                    "customer_order": _text(row["customer_order"], "customer_order"),
                    "requested_quantity": _wire(
                        _quantity(row["requested_quantity"], "requested_quantity")
                    ),
                    "priority": _whole(row["priority"], "priority", positive=True),
                    "allocated": 0,
                    "backordered": _wire(
                        _quantity(row["requested_quantity"], "requested_quantity")
                    ),
                    "dispatched": 0,
                    "reservation": "LOCAL_PLAN",
                    **(
                        {
                            "promised_delivery_at": row["promised_delivery_at"],
                            "customer_priority": row["customer_priority"],
                            "partial_dispatch": row["partial_dispatch"],
                            "minimum_dispatch_quantity": row["minimum_dispatch_quantity"],
                            "allow_final_remainder": row["allow_final_remainder"],
                        }
                        if contract_mode(self._config)
                        else {}
                    ),
                }
                for row in allocations
            ],
            "alerts": [],
            "events": [],
            "documents": [],
            "shipments": {},
            "prepared_picks": [],
            "conversation": [],
            "source_status": "UNAVAILABLE",
            "source_error": "ERP_SOURCE_NOT_READ",
            "source_observation": None,
        }

    def _initial_expected_cartons(self, lots: list[Mapping[str, object]]) -> int:
        if all("cartons" in row for row in lots):
            return sum(
                (
                    _whole(row["cartons"], "lot cartons", positive=True)
                    for row in lots
                    if row.get("replacement_for_lot") is None
                ),
                0,
            )
        return _whole(self._config["cartons"], "cartons", positive=True)

    def _latest_state(self) -> dict[str, object] | None:
        row = self._db.execute(
            "SELECT state_json FROM distributor_operation_events WHERE state_json IS NOT NULL "
            "ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
        return _decoded(cast(str, row[0]), "state") if row is not None else None

    def _projection_from_record(self, record: str) -> dict[str, object]:
        return _decoded(record, "event result")

    def _pending_projection(self, event_id: str) -> dict[str, object]:
        projection = self.projection()
        projection["stage"] = "HOLD"
        projection["alerts"] = [
            *cast(list[object], projection["alerts"]),
            {
                "code": "EVENT_OUTCOME_UNKNOWN",
                "status": "OPEN",
                "message": (
                    "This retained event has no completed native outcome; it will not be retried."
                ),
                "event_id": event_id,
            },
        ]
        return projection

    def _merge_source(
        self, state: Mapping[str, object], source: Mapping[str, object]
    ) -> tuple[dict[str, object], dict[str, object]]:
        next_state = cast(dict[str, object], _copy(state))
        current = cast(dict[str, object], _copy(source))
        if current["source_status"] == "CURRENT" and not self._source_matches_state(
            next_state, current
        ):
            current = self._source_unavailable("ERP_SOURCE_RECONCILIATION_UNKNOWN")
        next_state["source_status"] = current["source_status"]
        next_state["source_error"] = current.get("source_error")
        if current["source_status"] == "CURRENT":
            next_state["documents"] = _merge_documents(
                _documents(next_state.get("documents")), _documents(current.get("documents"))
            )
            parent_purchase_order = current.get("parent_purchase_order")
            if isinstance(parent_purchase_order, Mapping):
                next_state["parent_purchase_order"] = _copy(parent_purchase_order)
            else:
                next_state.pop("parent_purchase_order", None)
            next_state["source_observation"] = {
                "quantities": _copy(current["quantities"]),
                "lots": _copy(current["lots"]),
                "allocations": _copy(current["allocations"]),
                "documents": _copy(current["documents"]),
                "parent_purchase_order": _copy(parent_purchase_order)
                if isinstance(parent_purchase_order, Mapping)
                else None,
            }
        else:
            next_state.pop("parent_purchase_order", None)
        return next_state, current

    def _source_matches_state(
        self, state: Mapping[str, object], source: Mapping[str, object]
    ) -> bool:
        source_quantities = source.get("quantities")
        state_quantities = state.get("quantities")
        if not isinstance(source_quantities, Mapping) or not isinstance(state_quantities, Mapping):
            return False
        for field in (
            "ordered",
            "received",
            "usable",
            "held",
            "missing",
            "allocated",
            "dispatched",
            "cartons",
        ):
            try:
                if _quantity(source_quantities.get(field), f"source {field}") != _quantity(
                    state_quantities.get(field), field
                ):
                    return False
            except ValueError:
                return False
        if source_quantities.get("uom") != state_quantities.get("uom"):
            return False
        if not self._source_lots_match_state(state, source):
            return False
        return self._source_allocations_match_state(state, source)

    def _source_lots_match_state(
        self, state: Mapping[str, object], source: Mapping[str, object]
    ) -> bool:
        raw_state = state.get("lots")
        raw_source = source.get("lots")
        if not isinstance(raw_state, list) or not isinstance(raw_source, list):
            return False
        state_lots = {
            row.get("lot"): row
            for row in raw_state
            if isinstance(row, Mapping) and isinstance(row.get("lot"), str)
        }
        source_lots = {
            row.get("lot"): row
            for row in raw_source
            if isinstance(row, Mapping) and isinstance(row.get("lot"), str)
        }
        if set(state_lots) != set(source_lots) or len(state_lots) != len(raw_state):
            return False
        inspection_required = (
            cast(Mapping[str, object], self._config["policy"])["inspection_required"] is True
        )
        for lot, source_lot in source_lots.items():
            state_lot = state_lots[lot]
            try:
                for field in ("expected_quantity", "cartons", "received"):
                    if _quantity(source_lot.get(field), f"source lot {field}") != _quantity(
                        state_lot.get(field), f"lot {field}"
                    ):
                        return False
                # A non-batched R4 Delivery Note has no native lot-level outbound link.
                # Its retained pick evidence remains visible but cannot be presented as
                # native lot attribution. Quality cases do have a scoped stock movement.
                if inspection_required:
                    for field in ("usable", "held"):
                        if _quantity(source_lot.get(field), f"source lot {field}") != _quantity(
                            state_lot.get(field), f"lot {field}"
                        ):
                            return False
            except ValueError:
                return False
        return True

    @staticmethod
    def _source_allocations_match_state(
        state: Mapping[str, object], source: Mapping[str, object]
    ) -> bool:
        raw_state = state.get("allocations")
        raw_source = source.get("allocations")
        if not isinstance(raw_state, list) or not isinstance(raw_source, list):
            return False
        state_rows = {
            row.get("customer_order"): row
            for row in raw_state
            if isinstance(row, Mapping) and isinstance(row.get("customer_order"), str)
        }
        source_rows = {
            row.get("customer_order"): row
            for row in raw_source
            if isinstance(row, Mapping) and isinstance(row.get("customer_order"), str)
        }
        if set(state_rows) != set(source_rows) or len(state_rows) != len(raw_state):
            return False
        for order, source_row in source_rows.items():
            state_row = state_rows[order]
            try:
                for field in (
                    "requested_quantity",
                    "priority",
                    "allocated",
                    "backordered",
                    "dispatched",
                ):
                    if _quantity(source_row.get(field), f"source allocation {field}") != _quantity(
                        state_row.get(field), f"allocation {field}"
                    ):
                        return False
            except ValueError:
                return False
            if source_row.get("reservation") != state_row.get("reservation"):
                return False
        return True

    def _advance(
        self, state: dict[str, object], event: Mapping[str, object], source: Mapping[str, object]
    ) -> tuple[dict[str, object], str]:
        next_state = cast(dict[str, object], _copy(state))
        if source["source_status"] != "CURRENT":
            self._alert(
                next_state,
                code="SOURCE_UNAVAILABLE",
                message="Current ERP evidence is unavailable; no native operation was started.",
                event=event,
                error_code=cast(str, source.get("source_error") or "ERP_SOURCE_UNAVAILABLE"),
            )
            self._append_event(next_state, event, "UNAVAILABLE", [])
            return next_state, "UNAVAILABLE"
        event_type = cast(str, event["type"])
        if event_type == "arrival":
            return self._arrival(next_state, event)
        if event_type == "inspection":
            return self._inspection(next_state, event)
        if event_type == "picked":
            return self._picked(next_state, event)
        return self._carrier(next_state, event)

    def _arrival(
        self, state: dict[str, object], event: Mapping[str, object]
    ) -> tuple[dict[str, object], str]:
        operations: list[_NativeOutcome] = []
        item_code = _text(event["item_code"], "item_code")
        lot_name = _text(event["lot"], "lot")
        lot = self._lot(state, lot_name)
        observed = _quantity(
            event["observed_stock_quantity"], "observed_stock_quantity", positive=True
        )
        cartons = _whole(event["cartons"], "cartons", positive=True)
        pack = _quantity(event["expected_pack_quantity"], "expected_pack_quantity", positive=True)
        if item_code != self._config["item_code"]:
            self._alert(
                state,
                code="WRONG_SKU",
                message=(
                    "The arrival SKU does not match this configured case; no stock was received."
                ),
                event=event,
                lot=lot_name,
            )
            self._append_event(state, event, "BLOCKED", operations)
            return state, "BLOCKED"
        if lot is None:
            self._alert(
                state,
                code="UNKNOWN_LOT",
                message="The arrival lot is not configured for this case; no stock was received.",
                event=event,
                lot=lot_name,
            )
            self._append_event(state, event, "BLOCKED", operations)
            return state, "BLOCKED"
        configured_pack = self._expected_pack_for_lot(lot_name)
        if pack != configured_pack:
            self._alert(
                state,
                code="PACK_QUANTITY_MISMATCH",
                message=(
                    "The declared package quantity conflicts with the configured package quantity."
                ),
                event=event,
                lot=lot_name,
            )
            self._append_event(state, event, "BLOCKED", operations)
            return state, "BLOCKED"
        expected_for_cartons = Decimal(cartons) * pack
        if observed > expected_for_cartons:
            self._alert(
                state,
                code="OBSERVED_COUNT_EXCEEDS_PACKING",
                message=(
                    "The observed stock count exceeds the declared packing count; "
                    "no stock was received."
                ),
                event=event,
                lot=lot_name,
            )
            self._append_event(state, event, "BLOCKED", operations)
            return state, "BLOCKED"
        existing = _quantity(lot["received"], "lot received")
        allowed = _quantity(lot["expected_quantity"], "expected_quantity")
        if existing + observed > allowed:
            self._alert(
                state,
                code="LOT_OVER_RECEIPT",
                message=(
                    "The arrival would exceed the configured lot quantity; no stock was received."
                ),
                event=event,
                lot=lot_name,
            )
            self._append_event(state, event, "BLOCKED", operations)
            return state, "BLOCKED"
        receipt = self._native(
            "receive_arrival",
            event,
            {
                "item_code": item_code,
                "lot": lot_name,
                "cartons": cartons,
                "expected_pack_quantity": _wire(pack),
                "observed_stock_quantity": _wire(observed),
                "evidence_ref": event["evidence_ref"],
                "synthetic": event["synthetic"],
            },
        )
        operations.append(receipt)
        if not receipt.succeeded:
            self._native_alert(state, event, receipt, lot_name)
            self._append_event(state, event, receipt.status, operations)
            return state, receipt.status
        lot["cartons"] = _whole(lot["cartons"], "lot cartons") + cartons
        lot["received"] = _wire(existing + observed)
        if cast(Mapping[str, object], self._config["policy"])["inspection_required"] is True:
            lot["held"] = _wire(_quantity(lot["held"], "lot held") + observed)
            lot["status"] = "PENDING_INSPECTION"
            self._alert(
                state,
                code="QUALITY_EVIDENCE_REQUIRED",
                message="Received stock is held until configured inspection evidence is recorded.",
                event=event,
                lot=lot_name,
                quantity=observed,
            )
        else:
            lot["usable"] = _wire(_quantity(lot["usable"], "lot usable") + observed)
            lot["status"] = "USABLE"
            self._recompute_allocations(state)
            prepared = self._prepare_pick(state, event)
            operations.extend(prepared)
        if observed < expected_for_cartons:
            self._alert(
                state,
                code="PARTS_SHORTAGE",
                message=(
                    "Observed stock is below the declared package count; "
                    "the short quantity remains unreceived."
                ),
                event=event,
                lot=lot_name,
                quantity=expected_for_cartons - observed,
            )
        self._recompute_quantities(state)
        replacement_for_lot = self._replacement_for_lot(lot_name)
        quantities = cast(Mapping[str, object], state["quantities"])
        if (
            replacement_for_lot is not None
            and _quantity(lot["received"], "lot received")
            == _quantity(lot["expected_quantity"], "expected_quantity")
            and _quantity(quantities["received"], "received")
            == _quantity(quantities["ordered"], "ordered")
        ):
            self._resolve_alerts(state, {"PARTS_SHORTAGE"}, replacement_for_lot)
        status = self._operations_status(operations)
        self._append_event(state, event, status, operations)
        return state, status

    def _inspection(
        self, state: dict[str, object], event: Mapping[str, object]
    ) -> tuple[dict[str, object], str]:
        operations: list[_NativeOutcome] = []
        lot_name = _text(event["lot"], "lot")
        lot = self._lot(state, lot_name)
        if lot is None or _quantity(lot["received"], "lot received") == 0:
            self._alert(
                state,
                code="UNKNOWN_LOT",
                message=(
                    "Inspection references no received configured lot; no quality release was made."
                ),
                event=event,
                lot=lot_name,
            )
            self._append_event(state, event, "BLOCKED", operations)
            return state, "BLOCKED"
        criteria = cast(Mapping[str, object], self._config["policy"]).get("inspection_criteria")
        bounds = criteria.get(event["metric"]) if isinstance(criteria, Mapping) else None
        if not isinstance(bounds, Mapping):
            self._alert(
                state,
                code="INSPECTION_CRITERION_UNAVAILABLE",
                message=(
                    "No configured quality criterion covers this measurement; the lot remains held."
                ),
                event=event,
                lot=lot_name,
            )
            self._append_event(state, event, "BLOCKED", operations)
            return state, "BLOCKED"
        measured = _quantity(event["measured"], "measured")
        minimum = _quantity(bounds["minimum"], "inspection minimum")
        maximum = _quantity(bounds["maximum"], "inspection maximum")
        derived_result = "PASS" if minimum <= measured <= maximum else "FAIL"
        if event["result"] != derived_result:
            self._alert(
                state,
                code="INSPECTION_RESULT_CONFLICT",
                message=(
                    "The declared inspection result conflicts with the configured "
                    "measurement criterion."
                ),
                event=event,
                lot=lot_name,
            )
            self._append_event(state, event, "BLOCKED", operations)
            return state, "BLOCKED"
        tested = _quantity(event["sample_quantity"], "sample_quantity", positive=True)
        lot_received = _quantity(lot["received"], "lot received")
        inspection_evidence = self._inspection_evidence(event, bounds, lot_received)
        if event["scope"] == "WHOLE_LOT" and tested < lot_received:
            self._alert(
                state,
                code="WHOLE_LOT_EVIDENCE_INCOMPLETE",
                message="Whole-lot release needs a report covering the received lot quantity.",
                event=event,
                lot=lot_name,
                quantity=lot_received - tested,
                extra=inspection_evidence,
            )
            self._append_event(state, event, "BLOCKED", operations)
            return state, "BLOCKED"
        inspection = self._native(
            "record_inspection",
            event,
            {
                "lot": lot_name,
                "result": event["result"],
                "scope": event["scope"],
                "metric": event["metric"],
                "measured": event["measured"],
                "criterion": _copy(bounds),
                "sample_quantity": event["sample_quantity"],
                "inspection_report_ref": event["inspection_report_ref"],
                "evidence_ref": event["evidence_ref"],
                "synthetic": event["synthetic"],
            },
        )
        operations.append(inspection)
        if not inspection.succeeded:
            self._native_alert(state, event, inspection, lot_name)
            self._append_event(state, event, inspection.status, operations)
            return state, inspection.status
        if event["result"] == "FAIL":
            quantity = _quantity(lot["received"], "lot received")
            lot["usable"] = 0
            lot["held"] = _wire(quantity)
            lot["status"] = "QUALITY_HOLD"
            self._resolve_alerts(state, {"QUALITY_EVIDENCE_REQUIRED"}, lot_name)
            self._alert(
                state,
                code="QUALITY_FAILED",
                message=(
                    "A sample measurement failed. The lot is held pending supported disposition; "
                    "this does not establish every held unit is defective."
                ),
                event=event,
                lot=lot_name,
                quantity=quantity,
                extra={**inspection_evidence, "held_quantity": _wire(quantity)},
            )
            self._recompute_allocations(state)
        elif event["scope"] != "WHOLE_LOT":
            self._alert(
                state,
                code="QUALITY_EVIDENCE_REQUIRED",
                message=(
                    "A sample pass does not release this configured lot; whole-lot evidence is due."
                ),
                event=event,
                lot=lot_name,
                extra=inspection_evidence,
            )
        else:
            release = self._native(
                "release_from_quality",
                event,
                {
                    "lot": lot_name,
                    "inspection_evidence_ref": event["evidence_ref"],
                    "scope": event["scope"],
                    "synthetic": event["synthetic"],
                },
            )
            operations.append(release)
            if release.succeeded:
                quantity = _quantity(lot["received"], "lot received")
                lot["usable"] = _wire(quantity)
                lot["held"] = 0
                lot["status"] = "USABLE"
                self._resolve_alerts(
                    state, {"QUALITY_EVIDENCE_REQUIRED", "QUALITY_FAILED"}, lot_name
                )
                self._recompute_allocations(state)
                operations.extend(self._prepare_pick(state, event))
            else:
                self._native_alert(state, event, release, lot_name)
        self._recompute_quantities(state)
        status = self._operations_status(operations)
        self._append_event(state, event, status, operations)
        return state, status

    def _picked(
        self, state: dict[str, object], event: Mapping[str, object]
    ) -> tuple[dict[str, object], str]:
        operations: list[_NativeOutcome] = []
        order = _text(event["customer_order"], "customer_order")
        lot_name = _text(event["lot"], "lot")
        quantity = _quantity(event["quantity"], "quantity", positive=True)
        lot = self._lot(state, lot_name)
        allocation = self._allocation(state, order)
        available = _quantity(lot["usable"], "lot usable") if lot is not None else Decimal()
        eligible = (
            _quantity(allocation["allocated"], "allocated") if allocation is not None else Decimal()
        )
        prepared = self._prepared_tranches(state, order, quantity)
        if (
            prepared is None
            and lot is not None
            and allocation is not None
            and quantity <= available
            and quantity <= eligible
        ):
            operations.extend(self._prepare_pick(state, event))
            prepared = self._prepared_tranches(state, order, quantity)
        if (
            lot is None
            or allocation is None
            or quantity > available
            or quantity > eligible
            or prepared is None
        ):
            self._alert(
                state,
                code="PICK_NOT_ELIGIBLE",
                message=(
                    "The picked quantity is not backed by usable stock and an eligible allocation."
                ),
                event=event,
                lot=lot_name,
                quantity=quantity,
                orders=[order],
            )
            status = (
                "UNKNOWN_OUTCOME"
                if any(outcome.status == "UNKNOWN_OUTCOME" for outcome in operations)
                else "BLOCKED"
            )
            self._append_event(state, event, status, operations)
            return state, status
        picked = self._native(
            "submit_pick",
            event,
            {
                "customer_order": order,
                "lot": lot_name,
                "quantity": _wire(quantity),
                "pick_evidence_ref": event["pick_evidence_ref"],
                "prepared_tranches": prepared or [],
                "synthetic": event["synthetic"],
            },
        )
        operations.append(picked)
        if not picked.succeeded:
            self._native_alert(state, event, picked, lot_name)
            self._append_event(state, event, picked.status, operations)
            return state, picked.status
        delivery = self._native(
            "submit_delivery_note",
            event,
            {
                "customer_order": order,
                "lot": lot_name,
                "quantity": _wire(quantity),
                "pick_evidence_ref": event["pick_evidence_ref"],
                "synthetic": event["synthetic"],
            },
        )
        operations.append(delivery)
        if not delivery.succeeded:
            self._native_alert(state, event, delivery, lot_name)
            self._append_event(state, event, delivery.status, operations)
            return state, delivery.status
        lot["usable"] = _wire(available - quantity)
        allocation["dispatched"] = _wire(
            _quantity(allocation["dispatched"], "dispatched") + quantity
        )
        self._consume_prepared(state, order, quantity)
        shipment_id = self._shipment_id(order, _text(event["event_id"], "event_id"))
        if shipment_id is None:
            self._alert(
                state,
                code="SHIPMENT_POLICY_MISSING",
                message="No exact configured shipment identity covers this picked event.",
                event=event,
                lot=lot_name,
                quantity=quantity,
                orders=[order],
            )
            self._append_event(state, event, "BLOCKED", operations)
            return state, "BLOCKED"
        shipment = self._native(
            "create_shipment",
            event,
            {
                "customer_order": order,
                "lot": lot_name,
                "quantity": _wire(quantity),
                "shipment_id": shipment_id,
                "pick_evidence_ref": event["pick_evidence_ref"],
                "synthetic": event["synthetic"],
            },
        )
        operations.append(shipment)
        self._recompute_allocations(state)
        if shipment.succeeded:
            self._track_shipment(state, event, shipment, order, lot_name, quantity)
        else:
            self._native_alert(state, event, shipment, lot_name)
        self._recompute_quantities(state)
        status = self._operations_status(operations)
        self._append_event(state, event, status, operations)
        return state, status

    def _carrier(
        self, state: dict[str, object], event: Mapping[str, object]
    ) -> tuple[dict[str, object], str]:
        shipment_id = _text(event["shipment_id"], "shipment_id")
        shipments = cast(dict[str, object], state["shipments"])
        raw = shipments.get(shipment_id)
        shipment = raw if isinstance(raw, dict) else None
        if shipment is None:
            self._alert(
                state,
                code="SHIPMENT_NOT_FOUND",
                message=(
                    "Carrier evidence does not reference an exact shipment created for this case."
                ),
                event=event,
            )
            self._append_event(state, event, "BLOCKED", [])
            return state, "BLOCKED"
        if event["type"] == "carrier_pickup":
            shipment["picked_up"] = True
            self._append_event(state, event, "APPLIED", [])
            return state, "APPLIED"
        if shipment.get("picked_up") is not True:
            self._alert(
                state,
                code="PICKUP_EVIDENCE_REQUIRED",
                message=(
                    "Delivery confirmation needs prior carrier pickup evidence "
                    "for this exact shipment."
                ),
                event=event,
            )
            self._append_event(state, event, "BLOCKED", [])
            return state, "BLOCKED"
        if shipment.get("delivered") is not True:
            shipment["delivered"] = True
            quantities = cast(dict[str, object], state["quantities"])
            quantities["delivery_confirmed"] = _wire(
                _quantity(quantities["delivery_confirmed"], "delivery_confirmed")
                + _quantity(shipment["quantity"], "shipment quantity")
            )
        self._append_event(state, event, "APPLIED", [])
        return state, "APPLIED"

    def _native(
        self,
        kind: str,
        event: Mapping[str, object],
        fields: Mapping[str, object],
    ) -> _NativeOutcome:
        if self._erp is None:
            return _NativeOutcome(
                kind=kind,
                status="UNKNOWN_OUTCOME",
                documents=[],
                error_code="ERP_ADAPTER_UNAVAILABLE",
            )
        operation = {"kind": kind, **cast(dict[str, object], _copy(fields))}
        try:
            raw = self._erp.apply_operation(
                self._config, operation, _text(event["event_id"], "event_id")
            )
        except Exception:
            return _NativeOutcome(
                kind=kind,
                status="UNKNOWN_OUTCOME",
                documents=[],
                error_code="ERP_OPERATION_UNAVAILABLE",
            )
        if not isinstance(raw, Mapping) or raw.get("operation") != kind:
            return _NativeOutcome(
                kind=kind,
                status="UNKNOWN_OUTCOME",
                documents=[],
                error_code="ERP_OPERATION_MALFORMED",
            )
        status = raw.get("status")
        if not isinstance(status, str) or status not in _WRITE_STATUSES:
            return _NativeOutcome(
                kind=kind,
                status="UNKNOWN_OUTCOME",
                documents=[],
                error_code="ERP_OPERATION_MALFORMED",
            )
        error_code = raw.get("error_code")
        return _NativeOutcome(
            kind=kind,
            status=status,
            documents=_documents(raw.get("documents")),
            error_code=error_code if isinstance(error_code, str) and error_code else None,
        )

    def _prepare_pick(
        self, state: dict[str, object], event: Mapping[str, object]
    ) -> list[_NativeOutcome]:
        if contract_mode(self._config):
            plan = self._contract_plan(state)
            if _quantity(plan["new_quantity"], "contract plan new quantity") <= 0:
                return []
            tranches = self._contract_plan_native_tranches(plan, state)
            if tranches is None:
                self._alert(
                    state,
                    code="ALLOCATION_PLAN_NATIVE_TRANCHE_UNSUPPORTED",
                    message=(
                        "The compiled contract quantities do not match configured native pick "
                        "tranches; no pick preparation was started."
                    ),
                    event=event,
                )
                return []
            plan = {**plan, "native_tranches": tranches}
            if not self._select_contract_plan(state, event, plan):
                return []
        allocations = cast(list[dict[str, object]], state["allocations"])
        prepared_rows = cast(list[dict[str, object]], state["prepared_picks"])
        already_prepared: dict[str, Decimal] = {}
        for row in prepared_rows:
            order = row.get("customer_order")
            if isinstance(order, str):
                already_prepared[order] = already_prepared.get(order, Decimal()) + _quantity(
                    row.get("remaining", 0), "prepared pick quantity"
                )
        planned = [
            {
                "customer_order": row["customer_order"],
                "quantity": _wire(
                    _quantity(row["allocated"], "allocated")
                    - already_prepared.get(cast(str, row["customer_order"]), Decimal())
                ),
                "priority": row["priority"],
            }
            for row in allocations
            if _quantity(row["allocated"], "allocated")
            > already_prepared.get(cast(str, row["customer_order"]), Decimal())
        ]
        if contract_mode(self._config):
            native_tranches = cast(list[Mapping[str, object]], plan["native_tranches"])
            lots_by_order = {
                _text(row["customer_order"], "contract plan customer order"): _text(
                    row["lot"], "contract plan lot"
                )
                for row in native_tranches
            }
            for row in planned:
                row["lot"] = lots_by_order[_text(row["customer_order"], "customer_order")]
        if not planned:
            return []
        outcomes: list[_NativeOutcome] = []
        policy = cast(Mapping[str, object], self._config["policy"])
        if policy["reservation_supported"] is True:
            reservation = self._native("reserve_allocation", event, {"allocations": planned})
            outcomes.append(reservation)
            if not reservation.succeeded:
                self._native_alert(state, event, reservation, None)
                return outcomes
            for row in allocations:
                if _quantity(row["allocated"], "allocated") > 0:
                    row["reservation"] = "NATIVE_RESERVED"
        else:
            for row in allocations:
                if _quantity(row["allocated"], "allocated") > 0:
                    row["reservation"] = "LOCAL_PLAN"
        retained = cast(list[dict[str, object]], state["prepared_picks"])
        for row in planned:
            prepared_outcome = self._native(
                "prepare_pick",
                event,
                {
                    "customer_order": row["customer_order"],
                    "quantity": row["quantity"],
                    "priority": row["priority"],
                },
            )
            outcomes.append(prepared_outcome)
            if prepared_outcome.succeeded:
                retained.append(
                    {
                        "customer_order": row["customer_order"],
                        "remaining": row["quantity"],
                        "event_id": event["event_id"],
                        "documents": _copy(prepared_outcome.documents),
                        **({"lot": row["lot"]} if "lot" in row else {}),
                    }
                )
            else:
                self._native_alert(state, event, prepared_outcome, None)
        if outcomes and all(outcome.succeeded for outcome in outcomes):
            self._resolve_native_operation_alerts(state, "prepare_pick")
        return outcomes

    def _contract_plan_native_tranches(
        self, plan: Mapping[str, object], state: Mapping[str, object]
    ) -> list[dict[str, object]] | None:
        configured = self._config.get("pick_tranches")
        if not isinstance(configured, list):
            return None
        rows = plan.get("rows")
        if not isinstance(rows, list):
            return None
        selected: list[dict[str, object]] = []
        for row in rows:
            if not isinstance(row, Mapping):
                return None
            quantity = _quantity(row.get("new_quantity"), "contract plan new quantity")
            if not quantity:
                continue
            matches = [
                tranche
                for tranche in configured
                if isinstance(tranche, Mapping)
                and tranche.get("customer_order") == row.get("customer_order")
                and _quantity(tranche.get("quantity"), "configured pick tranche quantity")
                == quantity
            ]
            if len(matches) != 1:
                return None
            tranche = matches[0]
            lot = tranche.get("lot")
            if not isinstance(lot, str) or not lot:
                return None
            selected.append(
                {
                    "customer_order": row["customer_order"],
                    "quantity": _wire(quantity),
                    "lot": lot,
                }
            )
        lots = {
            row.get("lot"): _quantity(row.get("usable"), "lot usable")
            for row in cast(list[Mapping[str, object]], state.get("lots", []))
            if isinstance(row.get("lot"), str)
        }
        committed: dict[str, Decimal] = {}
        prepared = state.get("prepared_picks")
        if not isinstance(prepared, list):
            return None
        for row in prepared:
            if not isinstance(row, Mapping) or not isinstance(row.get("lot"), str):
                return None
            lot = cast(str, row["lot"])
            committed[lot] = committed.get(lot, Decimal()) + _quantity(
                row.get("remaining"), "prepared pick quantity"
            )
        for row in selected:
            lot = cast(str, row["lot"])
            committed[lot] = committed.get(lot, Decimal()) + _quantity(
                row["quantity"], "contract plan tranche quantity"
            )
        if any(lot not in lots or quantity > lots[lot] for lot, quantity in committed.items()):
            return None
        return selected

    def _prepared_tranches(
        self, state: Mapping[str, object], order: str, quantity: Decimal
    ) -> list[dict[str, object]] | None:
        remaining = quantity
        result: list[dict[str, object]] = []
        rows = state.get("prepared_picks")
        if not isinstance(rows, list):
            return None
        for row in rows:
            if not isinstance(row, Mapping) or row.get("customer_order") != order:
                continue
            available = _quantity(row.get("remaining", 0), "prepared pick quantity")
            if available <= 0:
                continue
            selected = min(available, remaining)
            result.append(
                {
                    "event_id": row.get("event_id"),
                    "quantity": _wire(selected),
                    "documents": _copy(row.get("documents", [])),
                }
            )
            remaining -= selected
            if remaining == 0:
                return result
        return None

    def _shipment_id(self, customer_order: str, event_id: str) -> str | None:
        shipping = self._config.get("shipping")
        if not isinstance(shipping, Mapping):
            return None
        shipments = shipping.get("shipments")
        if not isinstance(shipments, Mapping):
            return None
        details = shipments.get(customer_order)
        if not isinstance(details, Mapping):
            return None
        try:
            prefix = _text(details.get("shipment_id_prefix"), "shipment ID prefix")
        except ValueError:
            return None
        identity = "|".join((str(self._config["case_id"]), customer_order, event_id))
        return f"{prefix}-{sha256(identity.encode()).hexdigest()[:12]}"

    def _resume_blocked_shipment(
        self, state: dict[str, object], current_event: Mapping[str, object]
    ) -> None:
        prior_event_id = self._pending_blocked_shipment_event(state)
        if prior_event_id is None:
            return
        prior_event = self._stored_picked_event(prior_event_id)
        if prior_event is None:
            return
        order = _text(prior_event["customer_order"], "customer_order")
        lot_name = _text(prior_event["lot"], "lot")
        quantity = _quantity(prior_event["quantity"], "quantity", positive=True)
        shipment_id = self._shipment_id(order, prior_event_id)
        if shipment_id is None:
            return
        shipment = self._native(
            "create_shipment",
            prior_event,
            {
                "customer_order": order,
                "lot": lot_name,
                "quantity": _wire(quantity),
                "shipment_id": shipment_id,
                "pick_evidence_ref": prior_event["pick_evidence_ref"],
                "synthetic": prior_event["synthetic"],
            },
        )
        self._append_resumed_operation(state, prior_event_id, shipment)
        if shipment.succeeded:
            if self._track_shipment(state, current_event, shipment, order, lot_name, quantity):
                self._resolve_native_operation_alerts(state, "create_shipment", prior_event_id)
        else:
            self._native_alert(state, current_event, shipment, lot_name)

    def _pending_blocked_shipment_event(self, state: Mapping[str, object]) -> str | None:
        events = state.get("events")
        if not isinstance(events, list):
            return None
        resumed = {
            operation.get("resumed_from_event_id")
            for event in events
            if isinstance(event, Mapping)
            for operation in event.get("operations", [])
            if isinstance(operation, Mapping)
            and isinstance(operation.get("resumed_from_event_id"), str)
        }
        for event in reversed(events):
            if not isinstance(event, Mapping) or event.get("type") != "picked":
                continue
            event_id = event.get("event_id")
            operations = event.get("operations")
            if (
                not isinstance(event_id, str)
                or event_id in resumed
                or not isinstance(operations, list)
            ):
                continue
            submitted = any(
                isinstance(operation, Mapping)
                and operation.get("kind") == "submit_delivery_note"
                and operation.get("status") in _SUCCESS
                for operation in operations
            )
            shipment_blocked = any(
                isinstance(operation, Mapping)
                and operation.get("kind") == "create_shipment"
                and operation.get("status") == "BLOCKED"
                for operation in operations
            )
            if submitted and shipment_blocked:
                return event_id
        return None

    def _stored_picked_event(self, event_id: str) -> dict[str, object] | None:
        payload = self._stored_event(event_id)
        return payload if payload is not None and payload.get("type") == "picked" else None

    def _stored_event(self, event_id: str) -> dict[str, object] | None:
        row = self._db.execute(
            "SELECT payload_json FROM distributor_operation_events WHERE event_id=?", (event_id,)
        ).fetchone()
        if row is None:
            return None
        try:
            payload = self._validate_event(_decoded(cast(str, row[0]), "event payload"))
        except (RuntimeError, ValueError):
            return None
        return payload

    def _append_resumed_operation(
        self, state: dict[str, object], prior_event_id: str, outcome: _NativeOutcome
    ) -> None:
        events = cast(list[dict[str, object]], state["events"])
        if not events:  # pragma: no cover - caller appends the new physical event first
            return
        record = outcome.record()
        record["resumed_from_event_id"] = prior_event_id
        current = events[-1]
        operations = cast(list[dict[str, object]], current["operations"])
        operations.append(record)
        if not outcome.succeeded:
            current["status"] = outcome.status
        state["documents"] = _merge_documents(_documents(state.get("documents")), outcome.documents)

    def _track_shipment(
        self,
        state: dict[str, object],
        event: Mapping[str, object],
        shipment: _NativeOutcome,
        order: str,
        lot_name: str,
        quantity: Decimal,
    ) -> bool:
        shipment_names = [
            name
            for document in shipment.documents
            if document.get("kind") == "Shipment" and isinstance(name := document.get("name"), str)
        ]
        if not shipment_names:
            self._alert(
                state,
                code="SHIPMENT_ID_UNAVAILABLE",
                message=(
                    "Dispatch is recorded, but no exact shipment identifier was returned "
                    "for carrier evidence."
                ),
                event=event,
                lot=lot_name,
                quantity=quantity,
                orders=[order],
            )
            return False
        tracked = cast(dict[str, object], state["shipments"])
        for name in shipment_names:
            tracked[name] = {
                "quantity": _wire(quantity),
                "customer_order": order,
                "lot": lot_name,
                "picked_up": False,
                "delivered": False,
                "synthetic": event["synthetic"],
            }
        return True

    def _expected_pack_for_lot(self, lot_name: str) -> Decimal:
        configured = self._configured_lot(lot_name)
        return _quantity(
            configured.get("expected_pack_quantity", self._config["expected_pack_quantity"]),
            "expected_pack_quantity",
            positive=True,
        )

    def _replacement_for_lot(self, lot_name: str) -> str | None:
        replacement = self._configured_lot(lot_name).get("replacement_for_lot")
        return _text(replacement, "replacement_for_lot") if replacement is not None else None

    def _configured_lot(self, lot_name: str) -> Mapping[str, object]:
        lots = cast(list[Mapping[str, object]], self._config["lots"])
        matches = [row for row in lots if row.get("lot") == lot_name]
        if len(matches) != 1:  # pragma: no cover - constructor validates configured identities
            raise RuntimeError("configured lot is unavailable")
        return matches[0]

    @staticmethod
    def _inspection_evidence(
        event: Mapping[str, object], bounds: Mapping[str, object], lot_received: Decimal
    ) -> dict[str, object]:
        return {
            "scope": event["scope"],
            "sample_quantity": event["sample_quantity"],
            "metric": event["metric"],
            "measured": event["measured"],
            "criterion": _copy(bounds),
            "required_lot_quantity": _wire(lot_received),
            "inspection_report_ref": event["inspection_report_ref"],
        }

    @staticmethod
    def _consume_prepared(state: dict[str, object], order: str, quantity: Decimal) -> None:
        remaining = quantity
        rows = cast(list[dict[str, object]], state["prepared_picks"])
        for row in rows:
            if row.get("customer_order") != order or remaining <= 0:
                continue
            available = _quantity(row.get("remaining", 0), "prepared pick quantity")
            consumed = min(available, remaining)
            row["remaining"] = _wire(available - consumed)
            remaining -= consumed

    def _lot(self, state: Mapping[str, object], lot_name: str) -> dict[str, object] | None:
        lots = state.get("lots")
        if not isinstance(lots, list):
            return None
        return next(
            (
                cast(dict[str, object], lot)
                for lot in lots
                if isinstance(lot, dict) and lot.get("lot") == lot_name
            ),
            None,
        )

    def _allocation(self, state: Mapping[str, object], order: str) -> dict[str, object] | None:
        allocations = state.get("allocations")
        if not isinstance(allocations, list):
            return None
        return next(
            (
                cast(dict[str, object], row)
                for row in allocations
                if isinstance(row, dict) and row.get("customer_order") == order
            ),
            None,
        )

    def _recompute_allocations(self, state: dict[str, object]) -> None:
        if contract_mode(self._config):
            plan = self._contract_plan(state)
            by_order = {
                row["customer_order"]: row for row in cast(list[Mapping[str, object]], plan["rows"])
            }
            for row in cast(list[dict[str, object]], state["allocations"]):
                selected = by_order[cast(str, row["customer_order"])]
                quantity = _quantity(selected["quantity"], "contract allocation")
                requested = _quantity(row["requested_quantity"], "requested_quantity")
                dispatched = _quantity(row["dispatched"], "dispatched")
                row["allocated"] = _wire(quantity)
                row["backordered"] = _wire(max(Decimal(), requested - dispatched - quantity))
            state["feasible_allocation_plan"] = _copy(plan)
            return
        lots = cast(list[dict[str, object]], state["lots"])
        available = sum((_quantity(row["usable"], "lot usable") for row in lots), Decimal())
        allocations = cast(list[dict[str, object]], state["allocations"])
        for row in sorted(allocations, key=lambda item: cast(int, item["priority"])):
            requested = _quantity(row["requested_quantity"], "requested_quantity")
            dispatched = _quantity(row["dispatched"], "dispatched")
            remaining = max(Decimal(), requested - dispatched)
            allocation = min(remaining, available)
            row["allocated"] = _wire(allocation)
            row["backordered"] = _wire(remaining - allocation)
            available -= allocation

    def _contract_plan(self, state: Mapping[str, object]) -> dict[str, object]:
        try:
            return compile_plan(
                allocations=state.get("allocations"),
                lots=state.get("lots"),
                prepared_picks=state.get("prepared_picks"),
            )
        except ContractAllocationError as error:  # validated config; malformed retained state only
            raise RuntimeError(str(error)) from error

    @staticmethod
    def _selection_refs_are_exact(plan: Mapping[str, object], choice: Mapping[str, object]) -> bool:
        refs = choice.get("contract_refs")
        if not isinstance(refs, list) or any(not isinstance(ref, str) for ref in refs):
            return False
        valid = {
            row.get("customer_order")
            for row in cast(list[Mapping[str, object]], plan.get("rows", []))
            if isinstance(row.get("customer_order"), str)
        }
        return len(refs) == len(valid) and len(set(refs)) == len(refs) and set(refs) == valid

    def _select_contract_plan(
        self, state: dict[str, object], event: Mapping[str, object], plan: Mapping[str, object]
    ) -> bool:
        existing = state.get("allocation_decision")
        if (
            isinstance(existing, Mapping)
            and existing.get("status") == "SELECTED"
            and existing.get("plan_id") == plan.get("plan_id")
            and existing.get("state_revision") == plan.get("state_revision")
        ):
            return True
        selector = self._allocation_selector
        if selector is None:
            choice: Mapping[str, object] = {"plan_id": "DEFER", "rationale": "selector unavailable"}
        else:
            try:
                raw = selector(plan)
                choice = raw if isinstance(raw, Mapping) else {}
            except Exception:
                choice = {"plan_id": "DEFER", "rationale": "selector unavailable"}
        plan_id = choice.get("plan_id")
        rationale = choice.get("rationale")
        if (
            plan_id == plan.get("plan_id")
            and isinstance(rationale, str)
            and rationale.strip()
            and self._selection_refs_are_exact(plan, choice)
        ):
            decision: dict[str, object] = {
                "status": "SELECTED",
                "case_id": self._config["case_id"],
                "plan_id": plan_id,
                "state_revision": plan["state_revision"],
                "event_id": event["event_id"],
                "rationale": rationale.strip(),
                "contract_refs": list(cast(list[str], choice["contract_refs"])),
                "plan": _copy(plan),
            }
            for field in ("provider", "usage"):
                value = choice.get(field)
                if isinstance(value, Mapping):
                    decision[field] = _copy(value)
            state["allocation_decision"] = decision
            self._checkpoint_allocation_decision(event["event_id"], state)
            for alert in cast(list[dict[str, object]], state["alerts"]):
                if alert.get("code") == "ALLOCATION_SELECTION_PENDING":
                    alert["status"] = "RESOLVED"
            return True
        state["allocation_decision"] = {
            "status": "PENDING",
            "case_id": self._config["case_id"],
            "plan_id": plan["plan_id"],
            "state_revision": plan["state_revision"],
            "event_id": event["event_id"],
            "rationale": rationale.strip()
            if isinstance(rationale, str) and rationale.strip()
            else "deferred",
            "plan": _copy(plan),
        }
        self._checkpoint_allocation_decision(event["event_id"], state)
        self._alert(
            state,
            code="ALLOCATION_SELECTION_PENDING",
            message=(
                "The contract allocation plan was deferred or malformed; no pick preparation "
                "was started."
            ),
            event=event,
        )
        return False

    def _checkpoint_allocation_decision(
        self, event_id: object, state: Mapping[str, object]
    ) -> None:
        """Persist an accepted/deferred selection before a native prepare can begin."""

        identifier = _text(event_id, "event_id")
        self._db.execute("BEGIN IMMEDIATE")
        try:
            updated = self._db.execute(
                "UPDATE distributor_operation_events SET state_json=? "
                "WHERE event_id=? AND result_json IS NULL",
                (_encode(state), identifier),
            ).rowcount
            if updated != 1:
                raise RuntimeError("allocation decision checkpoint is unavailable")
            self._db.commit()
        except Exception:
            self._db.rollback()
            raise

    def _recompute_quantities(self, state: dict[str, object]) -> None:
        quantities = cast(dict[str, object], state["quantities"])
        lots = cast(list[dict[str, object]], state["lots"])
        allocations = cast(list[dict[str, object]], state["allocations"])
        received = sum((_quantity(row["received"], "lot received") for row in lots), Decimal())
        usable = sum((_quantity(row["usable"], "lot usable") for row in lots), Decimal())
        held = sum((_quantity(row["held"], "lot held") for row in lots), Decimal())
        cartons = sum((_whole(row["cartons"], "lot cartons") for row in lots), 0)
        ordered = _quantity(quantities["ordered"], "ordered")
        dispatched = sum(
            (_quantity(row["dispatched"], "dispatched") for row in allocations), Decimal()
        )
        quantities.update(
            {
                "received": _wire(received),
                "usable": _wire(usable),
                "held": _wire(held),
                "missing": _wire(max(Decimal(), ordered - received)),
                "allocated": _wire(
                    sum(
                        (_quantity(row["allocated"], "allocated") for row in allocations), Decimal()
                    )
                ),
                "dispatched": _wire(dispatched),
                "cartons": cartons,
                "observed_outer_packages": cartons,
            }
        )

    def _native_alert(
        self,
        state: dict[str, object],
        event: Mapping[str, object],
        outcome: _NativeOutcome,
        lot: str | None,
    ) -> None:
        self._alert(
            state,
            code=(
                "NATIVE_OPERATION_UNKNOWN"
                if outcome.status == "UNKNOWN_OUTCOME"
                else "NATIVE_OPERATION_BLOCKED"
            ),
            message=(
                "A native operation has an unknown outcome and will not be retried automatically."
                if outcome.status == "UNKNOWN_OUTCOME"
                else (
                    "The native operation was blocked; review the retained evidence "
                    "before continuing."
                )
            ),
            event=event,
            lot=lot,
            error_code=outcome.error_code,
            extra={"operation": outcome.kind},
        )

    def _alert(
        self,
        state: dict[str, object],
        *,
        code: str,
        message: str,
        event: Mapping[str, object],
        lot: str | None = None,
        quantity: Decimal | None = None,
        orders: list[str] | None = None,
        error_code: str | None = None,
        extra: Mapping[str, object] | None = None,
    ) -> None:
        alerts = cast(list[dict[str, object]], state["alerts"])
        identity = (code, lot or "", _text(event["event_id"], "event_id"))
        if any(
            (alert.get("code"), str(alert.get("lot") or ""), alert.get("event_id")) == identity
            for alert in alerts
        ):
            return
        alert: dict[str, object] = {
            "code": code,
            "status": "OPEN",
            "message": message,
            "event_id": event["event_id"],
            "evidence_ref": event["evidence_ref"],
            "synthetic": event["synthetic"],
        }
        if lot is not None:
            alert["lot"] = lot
        if quantity is not None:
            alert["quantity"] = _wire(quantity)
        if orders:
            alert["orders"] = sorted(orders)
        if error_code:
            alert["error_code"] = error_code
        if extra:
            alert.update(cast(dict[str, object], _copy(extra)))
        alerts.append(alert)

    @staticmethod
    def _resolve_alerts(state: dict[str, object], codes: set[str], lot: str) -> None:
        for alert in cast(list[dict[str, object]], state["alerts"]):
            if (
                alert.get("code") in codes
                and alert.get("lot") == lot
                and alert.get("status") == "OPEN"
            ):
                alert["status"] = "RESOLVED"

    @staticmethod
    def _resolve_native_operation_alerts(
        state: dict[str, object], operation: str, event_id: str | None = None
    ) -> None:
        for alert in cast(list[dict[str, object]], state["alerts"]):
            if (
                alert.get("code") == "NATIVE_OPERATION_BLOCKED"
                and alert.get("operation") == operation
                and (event_id is None or alert.get("event_id") == event_id)
                and alert.get("status") == "OPEN"
            ):
                alert["status"] = "RESOLVED"

    def _append_event(
        self,
        state: dict[str, object],
        event: Mapping[str, object],
        status: str,
        operations: list[_NativeOutcome],
    ) -> None:
        events = cast(list[dict[str, object]], state["events"])
        record: dict[str, object] = {
            "event_id": event["event_id"],
            "type": event["type"],
            "status": status,
            "occurred_at": event["occurred_at"],
            "evidence_ref": event["evidence_ref"],
            "synthetic": event["synthetic"],
            "operations": [outcome.record() for outcome in operations],
        }
        decision = state.get("allocation_decision")
        if isinstance(decision, Mapping) and decision.get("event_id") == event["event_id"]:
            record["allocation_decision"] = _copy(decision)
        event_type = cast(str, event["type"])
        for field in _EVENT_BRIEF_FIELDS[event_type]:
            record[field] = _copy(event[field])
        events.append(record)
        for outcome in operations:
            state["documents"] = _merge_documents(
                _documents(state.get("documents")), outcome.documents
            )

    @staticmethod
    def _operations_status(operations: list[_NativeOutcome]) -> str:
        if any(outcome.status == "UNKNOWN_OUTCOME" for outcome in operations):
            return "UNKNOWN_OUTCOME"
        if any(outcome.status == "BLOCKED" for outcome in operations):
            return "BLOCKED"
        return "APPLIED"

    def _projection(
        self, state: Mapping[str, object], source: Mapping[str, object]
    ) -> dict[str, object]:
        result = cast(dict[str, object], _copy(state))
        result["schema_version"] = DISTRIBUTOR_OPERATIONS_SCHEMA_VERSION
        result["available"] = source["source_status"] == "CURRENT"
        result["documents"] = _documents(result.get("documents"))
        result["conversation"] = list(cast(list[object], result.get("conversation", [])))
        event_briefs = self._event_briefs(result.get("events"))
        shipment_rows = self._shipment_rows(result.get("shipments"))
        result["events"] = event_briefs
        result["shipments"] = shipment_rows
        self._add_outbound_facts(result, event_briefs, shipment_rows)
        policy = cast(Mapping[str, object], self._config["policy"])
        result["quality_policy"] = {
            "inspection_required": policy["inspection_required"],
            "inspection_criteria": _copy(policy.get("inspection_criteria") or {}),
        }
        alerts = cast(list[dict[str, object]], result["alerts"])
        if source["source_status"] != "CURRENT" and not any(
            alert.get("code") == "SOURCE_UNAVAILABLE" and alert.get("derived") is True
            for alert in alerts
        ):
            alerts.append(
                {
                    "code": "SOURCE_UNAVAILABLE",
                    "status": "OPEN",
                    "message": (
                        "Current ERP evidence is unavailable; no native operation can start."
                    ),
                    "error_code": source.get("source_error") or "ERP_SOURCE_UNAVAILABLE",
                    "derived": True,
                }
            )
        self._deadline_alerts(result, alerts)
        result["stage"] = self._stage(result, alerts)
        result["available_event_templates"] = self._event_templates()
        result.pop("prepared_picks", None)
        result.pop("source_status", None)
        result.pop("source_error", None)
        result.pop("source_observation", None)
        return result

    def _event_briefs(self, raw_events: object) -> list[dict[str, object]]:
        if not isinstance(raw_events, list):
            return []
        result: list[dict[str, object]] = []
        for raw in raw_events:
            if not isinstance(raw, Mapping):
                continue
            record = cast(dict[str, object], _copy(raw))
            event_id = record.get("event_id")
            event_type = record.get("type")
            fields = _EVENT_BRIEF_FIELDS.get(event_type) if isinstance(event_type, str) else None
            if isinstance(event_id, str) and fields is not None:
                payload = self._stored_event(event_id)
                if payload is not None and payload.get("type") == event_type:
                    for field in fields:
                        record[field] = _copy(payload[field])
            result.append(record)
        return result

    def _shipment_rows(self, raw_shipments: object) -> list[dict[str, object]]:
        if not isinstance(raw_shipments, Mapping):
            return []
        result: list[dict[str, object]] = []
        for raw_name, raw in raw_shipments.items():
            if not isinstance(raw_name, str) or not isinstance(raw, Mapping):
                continue
            try:
                name = _text(raw_name, "shipment name")
                row = {
                    "name": name,
                    "customer_order": _text(raw.get("customer_order"), "shipment order"),
                    "lot": _text(raw.get("lot"), "shipment lot"),
                    "quantity": _wire(
                        _quantity(raw.get("quantity"), "shipment quantity", positive=True)
                    ),
                    "picked_up": raw.get("picked_up") is True,
                    "delivered": raw.get("delivered") is True,
                    "synthetic": (
                        raw.get("synthetic")
                        if type(raw.get("synthetic")) is bool
                        else self._config["synthetic_input"]
                    ),
                }
            except ValueError:
                continue
            result.append(row)
        return sorted(result, key=lambda row: cast(str, row["name"]))

    @staticmethod
    def _add_outbound_facts(
        projection: dict[str, object],
        events: list[dict[str, object]],
        shipments: list[dict[str, object]],
    ) -> None:
        picked_by_order: dict[str, Decimal] = {}
        counted_pick_lists: set[str] = set()
        for event in events:
            if event.get("type") != "picked":
                continue
            order = event.get("customer_order")
            operations = event.get("operations")
            if not isinstance(order, str) or not isinstance(operations, list):
                continue
            pick_lists = {
                name
                for operation in operations
                if isinstance(operation, Mapping)
                and operation.get("kind") == "submit_pick"
                and operation.get("status") in _SUCCESS
                for document in _documents(operation.get("documents"))
                if document.get("kind") == "Pick List"
                and isinstance(name := document.get("name"), str)
            }
            if not pick_lists or pick_lists.intersection(counted_pick_lists):
                continue
            try:
                quantity = _quantity(event.get("quantity"), "picked quantity", positive=True)
            except ValueError:
                continue
            counted_pick_lists.update(pick_lists)
            picked_by_order[order] = picked_by_order.get(order, Decimal()) + quantity
        delivered_by_order: dict[str, Decimal] = {}
        for shipment in shipments:
            if shipment.get("delivered") is not True:
                continue
            order = shipment.get("customer_order")
            if not isinstance(order, str):
                continue
            try:
                quantity = _quantity(
                    shipment.get("quantity"), "delivered shipment quantity", positive=True
                )
            except ValueError:
                continue
            delivered_by_order[order] = delivered_by_order.get(order, Decimal()) + quantity
        allocations = projection.get("allocations")
        if not isinstance(allocations, list):
            return
        for raw in allocations:
            if not isinstance(raw, dict):
                continue
            order = raw.get("customer_order")
            if not isinstance(order, str):
                continue
            picked = picked_by_order.get(order)
            delivered = delivered_by_order.get(order, Decimal())
            if picked is not None:
                raw["picked"] = _wire(picked)
            if delivered > 0:
                raw["delivery_confirmed"] = _wire(delivered)
            elif picked is not None:
                raw["delivery_confirmed"] = 0
            if delivered > 0:
                requested = _quantity(
                    raw.get("requested_quantity"), "requested quantity", positive=True
                )
                raw["status"] = (
                    "DELIVERY_CONFIRMED" if delivered >= requested else "PARTIALLY_DELIVERED"
                )
            elif picked is not None:
                raw["status"] = "PICKED"

    def _deadline_alerts(
        self, projection: Mapping[str, object], alerts: list[dict[str, object]]
    ) -> None:
        now = self._now()
        quantities = cast(Mapping[str, object], projection["quantities"])
        ordered = _quantity(quantities["ordered"], "ordered")
        received = _quantity(quantities["received"], "received")
        dispatched = _quantity(quantities["dispatched"], "dispatched")
        delivered = _quantity(quantities["delivery_confirmed"], "delivery_confirmed")
        deadlines = (
            (
                "expected_at",
                "RECEIPT_OVERDUE",
                received < ordered,
                "Receipt evidence is overdue; no loss cause is inferred.",
            ),
            (
                "promised_delivery_at",
                "DELIVERY_CONFIRMATION_DUE",
                dispatched > delivered,
                (
                    "Delivery confirmation is overdue for dispatched stock; "
                    "a Delivery Note is not proof of receipt."
                ),
            ),
        )
        for field, code, active, message in deadlines:
            deadline = _deadline(self._config.get(field), field) if field in self._config else None
            if (
                deadline is None
                or now <= deadline
                or not active
                or any(
                    alert.get("code") == code and alert.get("derived") is True for alert in alerts
                )
            ):
                continue
            alerts.append(
                {
                    "code": code,
                    "status": "OPEN",
                    "message": message,
                    "deadline": deadline.isoformat(),
                    "derived": True,
                }
            )

    @staticmethod
    def _stage(projection: Mapping[str, object], alerts: list[dict[str, object]]) -> str:
        if projection.get("source_status") == "UNAVAILABLE":
            return "SOURCE_UNAVAILABLE"
        if any(alert.get("status") == "OPEN" for alert in alerts):
            return "HOLD"
        quantities = cast(Mapping[str, object], projection["quantities"])
        ordered = _quantity(quantities["ordered"], "ordered")
        delivery = _quantity(quantities["delivery_confirmed"], "delivery_confirmed")
        dispatched = _quantity(quantities["dispatched"], "dispatched")
        allocated = _quantity(quantities["allocated"], "allocated")
        received = _quantity(quantities["received"], "received")
        if ordered > 0 and delivery >= ordered:
            return "DELIVERY_CONFIRMED"
        if dispatched > 0:
            return "DISPATCHED"
        if allocated > 0:
            return "PICK_PREPARED"
        if received > 0:
            return "RECEIVED"
        return "AWAITING_ARRIVAL"

    def _event_templates(self) -> list[dict[str, object]]:
        return [
            {"type": "arrival", "synthetic": self._config["synthetic_input"]},
            {"type": "inspection", "synthetic": self._config["synthetic_input"]},
            {"type": "picked", "synthetic": self._config["synthetic_input"]},
            {"type": "carrier_pickup", "synthetic": self._config["synthetic_input"]},
            {"type": "delivery", "synthetic": self._config["synthetic_input"]},
        ]

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise ValueError("operations clock must return a timezone-aware time")
        return value.astimezone(UTC)
