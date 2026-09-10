"""Small native ERPNext bridge for the synthetic distributor demo.

The service owns event validation and persistence.  This adapter owns only
case-scoped ERP reads and one event-bound native operation at a time.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from typing import Final, Protocol
from urllib.parse import quote, urlencode, urlsplit

from the_missing_20.adapters.demo_executor import DemoExecutionBlocked

_RESOURCE: Final = "/api/resource"
_WRITE_UNKNOWN: Final = "UNKNOWN_OUTCOME"
_APPLIED: Final = "APPLIED"
_ALREADY_APPLIED: Final = "ALREADY_APPLIED"
_BLOCKED: Final = "BLOCKED"
_OPERATIONS: Final = frozenset(
    {
        "receive_arrival",
        "record_inspection",
        "release_from_quality",
        "reserve_allocation",
        "prepare_pick",
        "submit_pick",
        "submit_delivery_note",
        "create_shipment",
    }
)


class _ScopeError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class _ERPClient(Protocol):
    """The narrow request/document surface used by this native bridge."""

    def _request(
        self, path: str, *, method: str = "GET", payload: object | None = None
    ) -> object: ...

    def _document(self, doctype: str, name: str) -> Mapping[str, object]: ...


def _map(value: object, code: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise _ScopeError(code)
    return value


def _rows(value: object, code: str) -> list[Mapping[str, object]]:
    if not isinstance(value, list):
        raise _ScopeError(code)
    return [_map(row, code) for row in value]


def _texts(value: object, code: str) -> list[str]:
    if not isinstance(value, list):
        raise _ScopeError(code)
    return [_text(item, code) for item in value]


def _text(value: object, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _ScopeError(code)
    return value.strip()


def _quantity(value: object, code: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _ScopeError(code)
    result = float(value)
    if not math.isfinite(result) or result < 0 or (positive and result == 0):
        raise _ScopeError(code)
    return result


def _equal(left: object, right: object) -> bool:
    if (
        isinstance(left, bool)
        or isinstance(right, bool)
        or not isinstance(left, (str, int, float))
        or not isinstance(right, (str, int, float))
    ):
        return False
    try:
        return math.isclose(float(left), float(right), rel_tol=0, abs_tol=1e-9)
    except ValueError:
        return False


def _status(document: Mapping[str, object]) -> str:
    raw = document.get("status")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    docstatus = document.get("docstatus")
    if docstatus == 0:
        return "Draft"
    if docstatus == 1:
        return "Submitted"
    if docstatus == 2:
        return "Cancelled"
    return "Unknown"


class DistributorERP:
    """The narrow injected bridge consumed by ``DistributorOperations``."""

    def __init__(self, executor: _ERPClient) -> None:
        self._executor = executor
        credentials = getattr(executor, "_credentials", None)
        base_url = getattr(credentials, "base_url", "")
        self._public_base_url = self._public_dashboard_base(base_url)

    @staticmethod
    def _public_dashboard_base(value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("ERP dashboard URL must be an absolute HTTP(S) URL")
        base_url = value.strip().rstrip("/")
        parsed = urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username:
            raise ValueError("ERP dashboard URL must be an absolute HTTP(S) URL")
        return base_url

    def _public_document(self, kind: str, document: Mapping[str, object]) -> dict[str, object]:
        name = _text(document.get("name"), "SOURCE_SCHEMA_MISMATCH")
        return {
            "kind": kind,
            "name": name,
            "status": _status(document),
            "url": (
                f"{self._public_base_url}/app/"
                f"{kind.lower().replace(' ', '-')}/{quote(name, safe='')}"
            ),
        }

    def read_case(self, config: Mapping[str, object]) -> Mapping[str, object]:
        try:
            scope = self._scope(config)
            order, po_item = self._purchase_order(scope)
            receipts = self._receipts(scope)
            orders = self._sales_orders(scope)
            picks = [pick for order_doc in orders for pick in self._picks(scope, order_doc)]
            deliveries = [
                note for order_doc in orders for note in self._deliveries(scope, order_doc)
            ]
            shipments = self._shipments(scope)
            return self._snapshot(
                scope, order, po_item, receipts, orders, picks, deliveries, shipments
            )
        except _ScopeError as error:
            return self._unavailable(config, error.code)
        except DemoExecutionBlocked:
            return self._unavailable(config, "ERP_READ_FAILED")
        except (OSError, TypeError, ValueError):
            return self._unavailable(config, "ERP_READ_FAILED")

    def apply_operation(
        self, config: Mapping[str, object], operation: Mapping[str, object], event_id: str
    ) -> Mapping[str, object]:
        try:
            scope = self._scope(config)
            kind = _text(operation.get("kind"), "OPERATION_INVALID")
            if kind not in _OPERATIONS:
                raise _ScopeError("OPERATION_NOT_ALLOWED")
            event = _text(event_id, "EVENT_ID_INVALID")
            if kind == "receive_arrival":
                return self._receive(scope, operation, event)
            if kind in {"record_inspection", "release_from_quality"}:
                return self._quality_operation(scope, operation, event)
            if kind == "reserve_allocation":
                return self._reservation(scope, operation, event)
            if kind == "prepare_pick":
                return self._prepare_pick(scope, operation, event)
            if kind == "submit_pick":
                return self._submit_pick(scope, operation, event)
            if kind == "submit_delivery_note":
                return self._submit_delivery(scope, operation, event)
            return self._shipment(scope, operation, event)
        except _ScopeError as error:
            return self._result(operation, event_id, _BLOCKED, error.code)
        except DemoExecutionBlocked as error:
            # A permission refusal is definitive and happens before a document
            # insert; do not report it as an unknown side effect.
            if "(401)" in str(error) or "(403)" in str(error):
                return self._result(operation, event_id, _BLOCKED, "ERP_ACCESS_DENIED")
            return self._result(operation, event_id, _WRITE_UNKNOWN, "ERP_WRITE_UNCONFIRMED")
        except (OSError, TypeError, ValueError):
            # Never retry an unknown ERP write from this adapter.
            return self._result(operation, event_id, _WRITE_UNKNOWN, "ERP_WRITE_UNCONFIRMED")

    @staticmethod
    def _result(
        operation: Mapping[str, object],
        event_id: str,
        status: str,
        error_code: str | None = None,
        documents: Sequence[Mapping[str, object]] = (),
        snapshot: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        kind = operation.get("kind")
        result: dict[str, object] = {
            "operation": kind if isinstance(kind, str) else "",
            "event_id": event_id,
            "status": status,
            "documents": [dict(document) for document in documents],
        }
        if error_code is not None:
            result["error_code"] = error_code
        if snapshot is not None:
            result["snapshot"] = dict(snapshot)
        return result

    @staticmethod
    def _unavailable(config: Mapping[str, object], error_code: str) -> dict[str, object]:
        case_id = config.get("case_id") if isinstance(config, Mapping) else ""
        label = config.get("case_label") if isinstance(config, Mapping) else ""
        return {
            "case_id": case_id if isinstance(case_id, str) else "",
            "case_label": label if isinstance(label, str) else "",
            "synthetic_input": bool(config.get("synthetic_input"))
            if isinstance(config, Mapping)
            else False,
            "quantities": {
                "ordered": 0.0,
                "received": 0.0,
                "usable": 0.0,
                "held": 0.0,
                "missing": 0.0,
                "allocated": 0.0,
                "dispatched": 0.0,
                "delivery_confirmed": 0.0,
                "uom": "",
                "cartons": 0.0,
            },
            "lots": [],
            "allocations": [],
            "documents": [],
            "source_status": "UNAVAILABLE",
            "source_error": error_code,
        }

    def _scope(self, raw: Mapping[str, object]) -> Mapping[str, object]:
        scope = _map(raw, "CONFIG_INVALID")
        if scope.get("synthetic_input") is not True:
            raise _ScopeError("SYNTHETIC_PROVENANCE_REQUIRED")
        for key in (
            "case_id",
            "case_label",
            "company",
            "supplier",
            "item_code",
            "uom",
            "stock_uom",
            "purchase_order",
            "purchase_order_item",
            "marker",
        ):
            value = _text(scope.get(key), "CONFIG_INVALID")
            if key == "case_id" and not value.startswith("M20-"):
                raise _ScopeError("CASE_ID_INVALID")
        _quantity(scope.get("expected_pack_quantity"), "CONFIG_INVALID", positive=True)
        _quantity(scope.get("cartons"), "CONFIG_INVALID")
        _quantity(scope.get("unit_rate"), "CONFIG_INVALID")
        warehouse = _map(scope.get("warehouses"), "CONFIG_INVALID")
        _text(warehouse.get("accepted"), "CONFIG_INVALID")
        _text(warehouse.get("quarantine"), "CONFIG_INVALID")
        policy = _map(scope.get("policy"), "CONFIG_INVALID")
        if not isinstance(policy.get("inspection_required"), bool) or not isinstance(
            policy.get("reservation_supported"), bool
        ):
            raise _ScopeError("CONFIG_INVALID")
        if not _rows(scope.get("receipt_plans"), "CONFIG_INVALID"):
            raise _ScopeError("CONFIG_INVALID")
        lots = _rows(scope.get("lots"), "CONFIG_INVALID")
        if not lots:
            raise _ScopeError("CONFIG_INVALID")
        allocations = _rows(scope.get("allocations"), "CONFIG_INVALID")
        if not allocations:
            raise _ScopeError("CONFIG_INVALID")
        order_names = _texts(scope.get("customer_orders"), "CONFIG_INVALID")
        allocation_names = [
            _text(row.get("customer_order"), "CONFIG_INVALID") for row in allocations
        ]
        if len(set(order_names)) != len(order_names) or set(order_names) != set(allocation_names):
            raise _ScopeError("CONFIG_INVALID")
        tranches = _rows(scope.get("pick_tranches"), "CONFIG_INVALID")
        if not tranches:
            raise _ScopeError("CONFIG_INVALID")
        shipping = _map(scope.get("shipping"), "CONFIG_INVALID")
        if shipping.get("native_read_enabled") is not True:
            raise _ScopeError("CONFIG_INVALID")
        shipment_orders = _map(shipping.get("shipments"), "CONFIG_INVALID")
        if set(shipment_orders) != set(order_names):
            raise _ScopeError("CONFIG_INVALID")
        plan_by_lot = {
            _text(plan.get("lot"), "CONFIG_INVALID"): plan for plan in self._plans(scope)
        }
        if len(plan_by_lot) != len(lots):
            raise _ScopeError("CONFIG_INVALID")
        for configured_lot in lots:
            name = _text(configured_lot.get("lot"), "CONFIG_INVALID")
            plan = plan_by_lot.get(name)
            if (
                plan is None
                or not _equal(configured_lot.get("expected_quantity"), plan.get("quantity"))
                or not _equal(configured_lot.get("cartons"), plan.get("cartons"))
            ):
                raise _ScopeError("CONFIG_INVALID")
        seen_tranches: set[tuple[str, str, float]] = set()
        tranche_totals = {lot: 0.0 for lot in plan_by_lot}
        for tranche in tranches:
            order_name = _text(tranche.get("customer_order"), "CONFIG_INVALID")
            tranche_lot = _text(tranche.get("lot"), "CONFIG_INVALID")
            quantity = _quantity(tranche.get("quantity"), "CONFIG_INVALID", positive=True)
            tranche_key = (order_name, tranche_lot, quantity)
            if (
                order_name not in order_names
                or tranche_lot not in plan_by_lot
                or tranche_key in seen_tranches
            ):
                raise _ScopeError("CONFIG_INVALID")
            if quantity > _quantity(plan_by_lot[tranche_lot].get("quantity"), "CONFIG_INVALID"):
                raise _ScopeError("CONFIG_INVALID")
            seen_tranches.add(tranche_key)
            tranche_totals[tranche_lot] += quantity
        if any(
            not _equal(total, plan_by_lot[lot].get("quantity"))
            for lot, total in tranche_totals.items()
        ):
            raise _ScopeError("CONFIG_INVALID")
        for order_name, raw_shipping in shipment_orders.items():
            _text(order_name, "CONFIG_INVALID")
            details = _map(raw_shipping, "CONFIG_INVALID")
            _text(details.get("pickup_address"), "CONFIG_INVALID")
            _text(details.get("delivery_address"), "CONFIG_INVALID")
            _text(details.get("pickup_date"), "CONFIG_INVALID")
            _text(details.get("pickup_from"), "CONFIG_INVALID")
            _text(details.get("pickup_to"), "CONFIG_INVALID")
            _quantity(details.get("parcel_weight"), "CONFIG_INVALID", positive=True)
        return scope

    def _request(self, path: str, *, method: str = "GET", payload: object | None = None) -> object:
        return self._executor._request(path, method=method, payload=payload)

    def _document(self, doctype: str, name: str) -> Mapping[str, object]:
        return _map(self._executor._document(doctype, name), "SOURCE_SCHEMA_MISMATCH")

    def _query(self, doctype: str, filters: list[list[object]]) -> list[str]:
        query = urlencode(
            {
                "fields": json.dumps(["name", "docstatus"]),
                "filters": json.dumps(filters),
                "limit_page_length": "50",
                "order_by": "creation asc",
            }
        )
        response = _map(
            self._request(f"{_RESOURCE}/{quote(doctype, safe='')}?{query}"),
            "SOURCE_SCHEMA_MISMATCH",
        )
        rows = _rows(response.get("data"), "SOURCE_SCHEMA_MISMATCH")
        if len(rows) >= 50:
            raise _ScopeError("SOURCE_SCHEMA_MISMATCH")
        names = [_text(row.get("name"), "SOURCE_SCHEMA_MISMATCH") for row in rows]
        if len(set(names)) != len(names):
            raise _ScopeError("SOURCE_SCHEMA_MISMATCH")
        return names

    def _find(self, doctype: str, field: str, value: str) -> Mapping[str, object] | None:
        names = self._query(doctype, [[field, "=", value]])
        if len(names) > 1:
            raise _ScopeError("SOURCE_AMBIGUOUS")
        return self._document(doctype, names[0]) if names else None

    def _purchase_order(
        self, scope: Mapping[str, object]
    ) -> tuple[Mapping[str, object], Mapping[str, object]]:
        order_name = _text(scope.get("purchase_order"), "CONFIG_INVALID")
        order = self._document("Purchase Order", order_name)
        if order.get("docstatus") != 1 or order.get("company") != scope.get("company"):
            raise _ScopeError("PURCHASE_ORDER_SCOPE_MISMATCH")
        expected = _text(scope.get("purchase_order_item"), "CONFIG_INVALID")
        matches = [
            row
            for row in _rows(order.get("items"), "SOURCE_SCHEMA_MISMATCH")
            if row.get("name") == expected
        ]
        if len(matches) != 1:
            raise _ScopeError("PURCHASE_ORDER_LINE_MISMATCH")
        line = matches[0]
        if (
            line.get("item_code") != scope.get("item_code")
            or line.get("uom") != scope.get("uom")
            or line.get("stock_uom") != scope.get("stock_uom")
            or not _equal(line.get("conversion_factor"), 1)
        ):
            raise _ScopeError("PURCHASE_ORDER_LINE_MISMATCH")
        return order, line

    def _plans(self, scope: Mapping[str, object]) -> list[Mapping[str, object]]:
        warehouse = _map(scope["warehouses"], "CONFIG_INVALID")
        valid_warehouses = {
            _text(warehouse.get("accepted"), "CONFIG_INVALID"),
            _text(warehouse.get("quarantine"), "CONFIG_INVALID"),
        }
        expected_pack = _quantity(scope["expected_pack_quantity"], "CONFIG_INVALID", positive=True)
        plans = _rows(scope.get("receipt_plans"), "CONFIG_INVALID")
        markers: set[str] = set()
        for plan in plans:
            marker = _text(plan.get("marker"), "CONFIG_INVALID")
            _text(plan.get("lot"), "CONFIG_INVALID")
            _quantity(plan.get("quantity"), "CONFIG_INVALID", positive=True)
            _quantity(plan.get("cartons"), "CONFIG_INVALID", positive=True)
            if marker in markers or plan.get("warehouse") not in valid_warehouses:
                raise _ScopeError("CONFIG_INVALID")
            if not _equal(plan.get("expected_pack_quantity"), expected_pack):
                raise _ScopeError("PACK_QUANTITY_MISMATCH")
            markers.add(marker)
        return plans

    def _tranches(self, scope: Mapping[str, object]) -> list[Mapping[str, object]]:
        return _rows(scope.get("pick_tranches"), "CONFIG_INVALID")

    def _tranche_for(
        self,
        scope: Mapping[str, object],
        operation: Mapping[str, object],
        *,
        require_lot: bool,
    ) -> Mapping[str, object]:
        order_name = _text(operation.get("customer_order"), "CUSTOMER_ORDER_REQUIRED")
        quantity = _quantity(operation.get("quantity"), "PICK_QUANTITY_REQUIRED", positive=True)
        lot = _text(operation.get("lot"), "PICK_LOT_REQUIRED") if require_lot else None
        matches = [
            tranche
            for tranche in self._tranches(scope)
            if tranche.get("customer_order") == order_name
            and _equal(tranche.get("quantity"), quantity)
            and (lot is None or tranche.get("lot") == lot)
        ]
        if len(matches) != 1:
            raise _ScopeError("PICK_TRANCHE_SCOPE_MISMATCH")
        return matches[0]

    def _receipts(self, scope: Mapping[str, object]) -> list[Mapping[str, object]]:
        receipts: list[Mapping[str, object]] = []
        for plan in self._plans(scope):
            marker = _text(plan.get("marker"), "CONFIG_INVALID")
            document = self._find("Purchase Receipt", "supplier_delivery_note", marker)
            if document is None:
                continue
            self._verify_receipt(scope, plan, document, submitted=True)
            receipts.append(document)
        return receipts

    def _sales_orders(self, scope: Mapping[str, object]) -> list[Mapping[str, object]]:
        names = [
            _text(row.get("customer_order"), "CONFIG_INVALID")
            for row in _rows(scope.get("allocations"), "CONFIG_INVALID")
        ]
        if len(set(names)) != len(names):
            raise _ScopeError("CONFIG_INVALID")
        orders: list[Mapping[str, object]] = []
        for name in names:
            order = self._document("Sales Order", name)
            if order.get("docstatus") != 1 or order.get("company") != scope.get("company"):
                raise _ScopeError("SALES_ORDER_SCOPE_MISMATCH")
            self._order_item(scope, order)
            orders.append(order)
        return orders

    def _order_item(
        self, scope: Mapping[str, object], order: Mapping[str, object]
    ) -> Mapping[str, object]:
        name = _text(order.get("name"), "SALES_ORDER_SCOPE_MISMATCH")
        allocation = next(
            (
                row
                for row in _rows(scope.get("allocations"), "CONFIG_INVALID")
                if row.get("customer_order") == name
            ),
            None,
        )
        if allocation is None:
            raise _ScopeError("SALES_ORDER_SCOPE_MISMATCH")
        expected = _quantity(allocation.get("requested_quantity"), "CONFIG_INVALID", positive=True)
        matches = [
            row
            for row in _rows(order.get("items"), "SOURCE_SCHEMA_MISMATCH")
            if row.get("item_code") == scope.get("item_code")
            and row.get("uom") == scope.get("uom")
            and _equal(row.get("qty"), expected)
        ]
        if len(matches) != 1:
            raise _ScopeError("SALES_ORDER_SCOPE_MISMATCH")
        return matches[0]

    def _picks(
        self, scope: Mapping[str, object], order: Mapping[str, object]
    ) -> list[Mapping[str, object]]:
        customer = _text(order.get("customer"), "SALES_ORDER_SCOPE_MISMATCH")
        order_name = _text(order.get("name"), "SALES_ORDER_SCOPE_MISMATCH")
        matches: list[Mapping[str, object]] = []
        for name in self._query("Pick List", [["customer", "=", customer]]):
            pick = self._document("Pick List", name)
            locations = _rows(pick.get("locations"), "SOURCE_SCHEMA_MISMATCH")
            if any(location.get("sales_order") == order_name for location in locations):
                self._verify_pick(scope, order, pick)
                quantity = self._pick_quantity(scope, order, pick)
                if not any(
                    tranche.get("customer_order") == order_name
                    and _equal(tranche.get("quantity"), quantity)
                    for tranche in self._tranches(scope)
                ):
                    raise _ScopeError("ERP_SOURCE_RECONCILIATION_UNKNOWN")
                matches.append(pick)
        return matches

    def _deliveries(
        self, scope: Mapping[str, object], order: Mapping[str, object]
    ) -> list[Mapping[str, object]]:
        customer = _text(order.get("customer"), "SALES_ORDER_SCOPE_MISMATCH")
        order_name = _text(order.get("name"), "SALES_ORDER_SCOPE_MISMATCH")
        matches: list[Mapping[str, object]] = []
        for name in self._query("Delivery Note", [["customer", "=", customer]]):
            note = self._document("Delivery Note", name)
            if self._delivery_matches(scope, note, order_name):
                _, quantity = self._delivery_quantity(scope, note)
                if not any(
                    tranche.get("customer_order") == order_name
                    and _equal(tranche.get("quantity"), quantity)
                    for tranche in self._tranches(scope)
                ):
                    raise _ScopeError("ERP_SOURCE_RECONCILIATION_UNKNOWN")
                matches.append(note)
        return matches

    def _shipments(self, scope: Mapping[str, object]) -> list[Mapping[str, object]]:
        shipping = _map(scope.get("shipping"), "CONFIG_INVALID")
        entries = _map(shipping.get("shipments"), "CONFIG_INVALID")
        for order_name, raw in entries.items():
            _text(order_name, "CONFIG_INVALID")
            _map(raw, "CONFIG_INVALID")
        prefix = f"{_text(scope.get('case_id'), 'CONFIG_INVALID')}-SHIP-"
        documents: list[Mapping[str, object]] = []
        for name in self._query("Shipment", [["shipment_id", "like", f"{prefix}%"]]):
            document = self._document("Shipment", name)
            shipment_id = _text(document.get("shipment_id"), "SOURCE_SCHEMA_MISMATCH")
            if not shipment_id.startswith(prefix):
                raise _ScopeError("ERP_SOURCE_RECONCILIATION_UNKNOWN")
            documents.append(document)
        return documents

    def _snapshot(
        self,
        scope: Mapping[str, object],
        order: Mapping[str, object],
        po_item: Mapping[str, object],
        receipts: Sequence[Mapping[str, object]],
        orders: Sequence[Mapping[str, object]],
        picks: Sequence[Mapping[str, object]],
        deliveries: Sequence[Mapping[str, object]],
        shipments: Sequence[Mapping[str, object]],
    ) -> dict[str, object]:
        plans = self._plans(scope)
        receipt_by_marker = {
            _text(document.get("supplier_delivery_note"), "SOURCE_SCHEMA_MISMATCH"): document
            for document in receipts
        }
        warehouse = _map(scope["warehouses"], "CONFIG_INVALID")
        accepted = _text(warehouse.get("accepted"), "CONFIG_INVALID")
        received = 0.0
        received_cartons = 0.0
        lots: list[dict[str, object]] = []
        lot_received: dict[str, float] = {}
        lot_held: dict[str, float] = {}
        for configured in _rows(scope.get("lots"), "CONFIG_INVALID"):
            lot = _text(configured.get("lot"), "CONFIG_INVALID")
            plan = next((row for row in plans if row.get("lot") == lot), None)
            if plan is None:
                raise _ScopeError("CONFIG_INVALID")
            receipt = receipt_by_marker.get(_text(plan["marker"], "CONFIG_INVALID"))
            quantity = 0.0
            location = ""
            if receipt is not None:
                item = self._receipt_item(scope, receipt)
                quantity = _quantity(item.get("qty"), "SOURCE_SCHEMA_MISMATCH")
                location = _text(item.get("warehouse"), "SOURCE_SCHEMA_MISMATCH")
            received += quantity
            received_cartons += (
                _quantity(plan.get("cartons"), "CONFIG_INVALID") if receipt is not None else 0.0
            )
            is_usable = location == accepted
            lot_received[lot] = quantity if is_usable else 0.0
            lot_held[lot] = quantity if location and not is_usable else 0.0
            lot_status = "USABLE" if is_usable else ("HELD" if location else "AWAITING_ARRIVAL")
            lots.append(
                {
                    "lot": lot,
                    "item_code": scope["item_code"],
                    "expected_quantity": _quantity(
                        configured.get("expected_quantity"), "CONFIG_INVALID"
                    ),
                    "cartons": (
                        _quantity(plan.get("cartons"), "CONFIG_INVALID")
                        if receipt is not None
                        else 0.0
                    ),
                    "received": quantity,
                    "usable": quantity if is_usable else 0.0,
                    "held": quantity if location and not is_usable else 0.0,
                    "status": lot_status,
                }
            )
        dispatched: dict[str, float] = {
            _text(order_doc.get("name"), "SALES_ORDER_SCOPE_MISMATCH"): 0.0 for order_doc in orders
        }
        dispatched_by_lot = {lot["lot"]: 0.0 for lot in lots}
        for delivery in deliveries:
            if delivery.get("docstatus") != 1:
                continue
            order_name, quantity = self._delivery_quantity(scope, delivery)
            matches = [
                tranche
                for tranche in self._tranches(scope)
                if tranche.get("customer_order") == order_name
                and _equal(tranche.get("quantity"), quantity)
            ]
            if len(matches) != 1:
                raise _ScopeError("ERP_SOURCE_RECONCILIATION_UNKNOWN")
            delivery_lot = _text(matches[0].get("lot"), "CONFIG_INVALID")
            dispatched[order_name] += quantity
            dispatched_by_lot[delivery_lot] += quantity
        usable = 0.0
        held = 0.0
        for lot_row in lots:
            name = _text(lot_row["lot"], "SOURCE_SCHEMA_MISMATCH")
            dispatched_from_lot = dispatched_by_lot[name]
            if dispatched_from_lot > lot_received[name]:
                raise _ScopeError("ERP_SOURCE_RECONCILIATION_UNKNOWN")
            lot_row["usable"] = lot_received[name] - dispatched_from_lot
            lot_row["held"] = lot_held[name]
            if lot_row["held"]:
                lot_row["status"] = "HELD"
            elif lot_row["received"] == 0:
                lot_row["status"] = "AWAITING_ARRIVAL"
            elif lot_row["usable"] == 0:
                lot_row["status"] = "DISPATCHED"
            else:
                lot_row["status"] = "USABLE"
            usable += _quantity(lot_row["usable"], "SOURCE_SCHEMA_MISMATCH")
            held += _quantity(lot_row["held"], "SOURCE_SCHEMA_MISMATCH")
        allocation_rows: list[dict[str, object]] = []
        remaining_usable = usable
        for allocation in sorted(
            _rows(scope.get("allocations"), "CONFIG_INVALID"),
            key=lambda row: _quantity(row.get("priority"), "CONFIG_INVALID", positive=True),
        ):
            name = _text(allocation.get("customer_order"), "CONFIG_INVALID")
            requested = _quantity(
                allocation.get("requested_quantity"), "CONFIG_INVALID", positive=True
            )
            complete = dispatched[name]
            if complete > requested:
                raise _ScopeError("ERP_SOURCE_RECONCILIATION_UNKNOWN")
            allocated = min(remaining_usable, requested - complete)
            remaining_usable -= allocated
            allocation_rows.append(
                {
                    "customer_order": name,
                    "priority": allocation.get("priority"),
                    "requested_quantity": requested,
                    # This is a case-local plan, never a native Stock Reservation Entry.
                    "allocated": allocated,
                    "backordered": requested - complete - allocated,
                    "uom": scope["uom"],
                    "dispatched": complete,
                    "reservation": "LOCAL_PLAN",
                }
            )
        for shipment in shipments:
            shipment_id = _text(shipment.get("shipment_id"), "ERP_SOURCE_RECONCILIATION_UNKNOWN")
            links = _rows(
                shipment.get("shipment_delivery_note"), "ERP_SOURCE_RECONCILIATION_UNKNOWN"
            )
            if len(links) != 1:
                raise _ScopeError("ERP_SOURCE_RECONCILIATION_UNKNOWN")
            note = self._document(
                "Delivery Note",
                _text(links[0].get("delivery_note"), "ERP_SOURCE_RECONCILIATION_UNKNOWN"),
            )
            order_name, quantity = self._delivery_quantity(scope, note)
            matches = [
                tranche
                for tranche in self._tranches(scope)
                if tranche.get("customer_order") == order_name
                and _equal(tranche.get("quantity"), quantity)
            ]
            if len(matches) != 1:
                raise _ScopeError("ERP_SOURCE_RECONCILIATION_UNKNOWN")
            self._verify_shipment(scope, shipment, shipment_id, order_name, matches[0])
        documents = [self._public_document("Purchase Order", order)]
        documents.extend(self._public_document("Purchase Receipt", receipt) for receipt in receipts)
        documents.extend(
            self._public_document("Sales Order", sales_order) for sales_order in orders
        )
        documents.extend(self._public_document("Pick List", pick) for pick in picks)
        documents.extend(self._public_document("Delivery Note", note) for note in deliveries)
        documents.extend(self._public_document("Shipment", shipment) for shipment in shipments)
        expected = sum(_quantity(plan["quantity"], "CONFIG_INVALID") for plan in plans)
        total_dispatched = sum(dispatched.values())
        quantities = {
            "ordered": expected,
            "received": received,
            "usable": usable,
            "held": held,
            "missing": max(0.0, expected - received),
            "allocated": sum(
                _quantity(row["allocated"], "SOURCE_SCHEMA_MISMATCH") for row in allocation_rows
            ),
            "dispatched": total_dispatched,
            # A submitted DN or Shipment is not carrier pickup or customer receipt.
            "delivery_confirmed": 0.0,
            "uom": scope["uom"],
            "cartons": received_cartons,
        }
        parent_purchase_order = {
            "name": _text(order.get("name"), "SOURCE_SCHEMA_MISMATCH"),
            "ordered": _quantity(po_item.get("qty"), "SOURCE_SCHEMA_MISMATCH"),
            "received": _quantity(po_item.get("received_qty") or 0, "SOURCE_SCHEMA_MISMATCH"),
            "uom": _text(po_item.get("uom"), "SOURCE_SCHEMA_MISMATCH"),
        }
        source_identity = {
            "case_id": scope["case_id"],
            "purchase_order": scope["purchase_order"],
            "purchase_order_item": scope["purchase_order_item"],
        }
        source_revision = self._revision(
            {
                "identity": source_identity,
                "parent_purchase_order": parent_purchase_order,
                "quantities": quantities,
                "lots": lots,
                "allocations": allocation_rows,
                "documents": documents,
            }
        )
        return {
            "case_id": scope["case_id"],
            "case_label": scope["case_label"],
            "synthetic_input": True,
            "quantities": quantities,
            "lots": lots,
            "allocations": allocation_rows,
            "documents": documents,
            "parent_purchase_order": parent_purchase_order,
            "source_identity": source_identity,
            "source_revision": source_revision,
            "source_status": "CURRENT",
        }

    @staticmethod
    def _revision(value: Mapping[str, object]) -> str:
        payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _receipt_item(
        self, scope: Mapping[str, object], receipt: Mapping[str, object]
    ) -> Mapping[str, object]:
        matches = [
            row
            for row in _rows(receipt.get("items"), "SOURCE_SCHEMA_MISMATCH")
            if row.get("item_code") == scope.get("item_code")
            and row.get("purchase_order") == scope.get("purchase_order")
            and row.get("purchase_order_item") == scope.get("purchase_order_item")
        ]
        if len(matches) != 1:
            raise _ScopeError("RECEIPT_SCOPE_MISMATCH")
        return matches[0]

    def _verify_receipt(
        self,
        scope: Mapping[str, object],
        plan: Mapping[str, object],
        receipt: Mapping[str, object],
        *,
        submitted: bool,
    ) -> None:
        item = self._receipt_item(scope, receipt)
        if (
            receipt.get("company") != scope.get("company")
            or receipt.get("supplier") != scope.get("supplier")
            or receipt.get("supplier_delivery_note") != plan.get("marker")
            or (submitted and receipt.get("docstatus") != 1)
            or not _equal(item.get("qty"), plan.get("quantity"))
            or item.get("uom") != scope.get("uom")
            or item.get("stock_uom") != scope.get("stock_uom")
            or not _equal(item.get("conversion_factor"), 1)
            or item.get("warehouse") != plan.get("warehouse")
            or not _equal(item.get("rejected_qty") or 0, 0)
        ):
            raise _ScopeError("RECEIPT_SCOPE_MISMATCH")

    def _verify_pick(
        self, scope: Mapping[str, object], order: Mapping[str, object], pick: Mapping[str, object]
    ) -> None:
        item = self._order_item(scope, order)
        name = _text(order.get("name"), "SALES_ORDER_SCOPE_MISMATCH")
        accepted = _text(
            _map(scope.get("warehouses"), "CONFIG_INVALID").get("accepted"),
            "CONFIG_INVALID",
        )
        matches = [
            row
            for row in _rows(pick.get("locations"), "SOURCE_SCHEMA_MISMATCH")
            if row.get("sales_order") == name
            and row.get("sales_order_item") == item.get("name")
            and row.get("item_code") == scope.get("item_code")
        ]
        if (
            pick.get("company") != scope.get("company")
            or pick.get("purpose") != "Delivery"
            or len(matches) != 1
            or matches[0].get("warehouse") != accepted
            or pick.get("parent_warehouse") != accepted
            or pick.get("pick_manually") not in (1, True)
        ):
            raise _ScopeError("PICK_LIST_SCOPE_MISMATCH")

    def _pick_quantity(
        self, scope: Mapping[str, object], order: Mapping[str, object], pick: Mapping[str, object]
    ) -> float:
        self._verify_pick(scope, order, pick)
        order_name = _text(order.get("name"), "SALES_ORDER_SCOPE_MISMATCH")
        locations = [
            row
            for row in _rows(pick.get("locations"), "SOURCE_SCHEMA_MISMATCH")
            if row.get("sales_order") == order_name
        ]
        if len(locations) != 1:
            raise _ScopeError("PICK_LIST_SCOPE_MISMATCH")
        return _quantity(locations[0].get("stock_qty"), "PICK_LIST_SCOPE_MISMATCH", positive=True)

    def _pick_for(
        self,
        scope: Mapping[str, object],
        order: Mapping[str, object],
        tranche: Mapping[str, object],
    ) -> Mapping[str, object] | None:
        expected = _quantity(tranche.get("quantity"), "CONFIG_INVALID", positive=True)
        matches = [
            pick
            for pick in self._picks(scope, order)
            if _equal(self._pick_quantity(scope, order, pick), expected)
        ]
        if len(matches) > 1:
            raise _ScopeError("PICK_LIST_AMBIGUOUS")
        return matches[0] if matches else None

    def _delivery_matches(
        self, scope: Mapping[str, object], delivery: Mapping[str, object], order_name: str
    ) -> bool:
        return (
            delivery.get("company") == scope.get("company")
            and len(
                [
                    row
                    for row in _rows(delivery.get("items"), "SOURCE_SCHEMA_MISMATCH")
                    if row.get("item_code") == scope.get("item_code")
                    and row.get("against_sales_order") == order_name
                ]
            )
            == 1
        )

    def _delivery_quantity(
        self, scope: Mapping[str, object], delivery: Mapping[str, object]
    ) -> tuple[str, float]:
        rows = [
            row
            for row in _rows(delivery.get("items"), "SOURCE_SCHEMA_MISMATCH")
            if row.get("item_code") == scope.get("item_code")
            and (row.get("against_sales_order") or row.get("sales_order")) is not None
        ]
        if len(rows) != 1:
            raise _ScopeError("DELIVERY_NOTE_SCOPE_MISMATCH")
        order_name = _text(
            rows[0].get("against_sales_order") or rows[0].get("sales_order"),
            "DELIVERY_NOTE_SCOPE_MISMATCH",
        )
        return order_name, _quantity(
            rows[0].get("qty"), "DELIVERY_NOTE_SCOPE_MISMATCH", positive=True
        )

    def _delivery_for(
        self,
        scope: Mapping[str, object],
        order: Mapping[str, object],
        tranche: Mapping[str, object],
    ) -> Mapping[str, object] | None:
        expected = _quantity(tranche.get("quantity"), "CONFIG_INVALID", positive=True)
        pick = self._pick_for(scope, order, tranche)
        if pick is None:
            return None
        pick_name = _text(pick.get("name"), "PICK_LIST_NOT_AVAILABLE")
        matches = [
            delivery
            for delivery in self._deliveries(scope, order)
            if self._delivery_matches_tranche(scope, delivery, order, tranche, pick_name)
            and _equal(self._delivery_quantity(scope, delivery)[1], expected)
        ]
        submitted = [delivery for delivery in matches if delivery.get("docstatus") == 1]
        if len(submitted) > 1:
            raise _ScopeError("DELIVERY_NOTE_AMBIGUOUS")
        if submitted:
            return submitted[0]
        drafts = [delivery for delivery in matches if delivery.get("docstatus") == 0]
        if len(drafts) > 1:
            raise _ScopeError("DELIVERY_NOTE_AMBIGUOUS")
        return drafts[0] if drafts else None

    def _delivery_matches_tranche(
        self,
        scope: Mapping[str, object],
        delivery: Mapping[str, object],
        order: Mapping[str, object],
        tranche: Mapping[str, object],
        pick_name: str,
    ) -> bool:
        if not self._delivery_matches(
            scope, delivery, _text(order.get("name"), "SALES_ORDER_SCOPE_MISMATCH")
        ):
            return False
        rows = [
            row
            for row in _rows(delivery.get("items"), "DELIVERY_NOTE_SCOPE_MISMATCH")
            if row.get("item_code") == scope.get("item_code")
        ]
        if len(rows) != 1:
            return False
        item = rows[0]
        accepted = _text(
            _map(scope.get("warehouses"), "CONFIG_INVALID").get("accepted"),
            "CONFIG_INVALID",
        )
        return (
            item.get("warehouse") == accepted
            and item.get("against_pick_list") == pick_name
            and _equal(item.get("qty"), tranche.get("quantity"))
        )

    def _verify_prepared_reference(
        self, operation: Mapping[str, object], pick: Mapping[str, object]
    ) -> None:
        raw = operation.get("prepared_tranches")
        if raw is None:
            return
        rows = _rows(raw, "PREPARED_PICK_REFERENCE_MISMATCH")
        pick_name = _text(pick.get("name"), "PICK_LIST_NOT_AVAILABLE")
        names: set[str] = set()
        for row in rows:
            documents = _rows(row.get("documents"), "PREPARED_PICK_REFERENCE_MISMATCH")
            for document in documents:
                if document.get("kind") == "Pick List":
                    names.add(_text(document.get("name"), "PREPARED_PICK_REFERENCE_MISMATCH"))
        if names != {pick_name}:
            raise _ScopeError("PREPARED_PICK_REFERENCE_MISMATCH")

    @staticmethod
    def _shipment_id(scope: Mapping[str, object], customer_order: str, event_id: str) -> str:
        shipping = _map(scope.get("shipping"), "SHIPPING_CONFIG_MISSING")
        shipments = _map(shipping.get("shipments"), "SHIPPING_CONFIG_MISSING")
        details = _map(shipments.get(customer_order), "SHIPPING_CONFIG_MISSING")
        prefix = _text(details.get("shipment_id_prefix"), "SHIPPING_CONFIG_MISSING")
        identity = f"{_text(scope.get('case_id'), 'CONFIG_INVALID')}|{customer_order}|{event_id}"
        return f"{prefix}-{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:12]}"

    def _verify_shipment(
        self,
        scope: Mapping[str, object],
        shipment: Mapping[str, object],
        shipment_id: str,
        customer_order: str,
        tranche: Mapping[str, object],
    ) -> None:
        shipping = _map(scope.get("shipping"), "SHIPPING_CONFIG_MISSING")
        details = _map(
            _map(shipping.get("shipments"), "SHIPPING_CONFIG_MISSING").get(customer_order),
            "SHIPPING_CONFIG_MISSING",
        )
        prefix = f"{_text(details.get('shipment_id_prefix'), 'SHIPPING_CONFIG_MISSING')}-"
        if (
            shipment.get("docstatus") != 1
            or shipment.get("shipment_id") != shipment_id
            or not shipment_id.startswith(prefix)
            or shipment.get("delivery_customer")
            != self._document("Sales Order", customer_order).get("customer")
            or shipment.get("delivery_address_name") != details.get("delivery_address")
        ):
            raise _ScopeError("SHIPMENT_SCOPE_MISMATCH")
        configured_contact = details.get("delivery_contact")
        if (
            configured_contact is not None
            and shipment.get("delivery_contact_name") != configured_contact
        ):
            raise _ScopeError("SHIPMENT_SCOPE_MISMATCH")
        notes = _rows(shipment.get("shipment_delivery_note"), "SHIPMENT_SCOPE_MISMATCH")
        if len(notes) != 1:
            raise _ScopeError("SHIPMENT_SCOPE_MISMATCH")
        note_name = _text(notes[0].get("delivery_note"), "SHIPMENT_SCOPE_MISMATCH")
        order = self._document("Sales Order", customer_order)
        note = self._delivery_for(scope, order, tranche)
        if note is None or note.get("name") != note_name:
            raise _ScopeError("SHIPMENT_SCOPE_MISMATCH")

    def _receipt_for(
        self, scope: Mapping[str, object], plan: Mapping[str, object]
    ) -> Mapping[str, object] | None:
        marker = _text(plan.get("marker"), "CONFIG_INVALID")
        document = self._find("Purchase Receipt", "supplier_delivery_note", marker)
        if document is not None:
            self._verify_receipt(scope, plan, document, submitted=True)
        return document

    def _receive(
        self, scope: Mapping[str, object], operation: Mapping[str, object], event_id: str
    ) -> Mapping[str, object]:
        _, po_item = self._purchase_order(scope)
        plan = self._plan(scope, operation)
        existing = self._receipt_for(scope, plan)
        if existing is not None:
            return self._result(
                operation,
                event_id,
                _ALREADY_APPLIED,
                documents=[self._public_document("Purchase Receipt", existing)],
                snapshot=self.read_case(scope),
            )
        payload = {
            "doctype": "Purchase Receipt",
            "company": scope["company"],
            "supplier": scope["supplier"],
            "currency": scope.get("currency", "USD"),
            "conversion_rate": 1,
            "supplier_delivery_note": plan["marker"],
            "remarks": f"{scope['marker']} event {event_id}",
            "items": [
                {
                    "item_code": scope["item_code"],
                    "purchase_order": scope["purchase_order"],
                    "purchase_order_item": scope["purchase_order_item"],
                    "qty": plan["quantity"],
                    "received_qty": plan["quantity"],
                    "rejected_qty": 0,
                    "uom": scope["uom"],
                    "stock_uom": scope["stock_uom"],
                    "conversion_factor": 1,
                    "warehouse": plan["warehouse"],
                    "rate": scope["unit_rate"],
                    "schedule_date": po_item.get("schedule_date"),
                }
            ],
        }
        draft = self._create("Purchase Receipt", payload)
        submitted = self._submit(draft)
        receipt_name = _text(submitted.get("name"), "ERP_WRITE_UNCONFIRMED")
        receipt = self._document("Purchase Receipt", receipt_name)
        self._verify_receipt(scope, plan, receipt, submitted=True)
        self._verify_receipt_ledger(scope, receipt)
        return self._result(
            operation,
            event_id,
            _APPLIED,
            documents=[self._public_document("Purchase Receipt", receipt)],
            snapshot=self.read_case(scope),
        )

    def _verify_receipt_ledger(
        self, scope: Mapping[str, object], receipt: Mapping[str, object]
    ) -> None:
        name = _text(receipt.get("name"), "SOURCE_SCHEMA_MISMATCH")
        item = self._receipt_item(scope, receipt)
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
                    ]
                ),
                "filters": json.dumps(
                    [["voucher_type", "=", "Purchase Receipt"], ["voucher_no", "=", name]]
                ),
                "limit_page_length": "50",
            }
        )
        response = _map(
            self._request(f"{_RESOURCE}/Stock%20Ledger%20Entry?{query}"),
            "RECEIPT_LEDGER_MISMATCH",
        )
        rows = _rows(response.get("data"), "RECEIPT_LEDGER_MISMATCH")
        total = 0.0
        for row in rows:
            if (
                row.get("voucher_type") != "Purchase Receipt"
                or row.get("voucher_no") != name
                or row.get("voucher_detail_no") != item.get("name")
                or row.get("item_code") != scope.get("item_code")
                or row.get("warehouse") != item.get("warehouse")
                or row.get("is_cancelled") not in (0, False, None)
            ):
                raise _ScopeError("RECEIPT_LEDGER_MISMATCH")
            total += _quantity(row.get("actual_qty"), "RECEIPT_LEDGER_MISMATCH")
        if not rows or not _equal(total, item.get("qty")):
            raise _ScopeError("RECEIPT_LEDGER_MISMATCH")

    def _quality_operation(
        self, scope: Mapping[str, object], operation: Mapping[str, object], event_id: str
    ) -> Mapping[str, object]:
        # The provisioner emits no component lot until its exact incoming-QI
        # behavior has been accepted in this tenant.  The public operation is
        # retained now so core never substitutes a non-native local result.
        _ = scope
        return self._result(operation, event_id, _BLOCKED, "QUALITY_WORKFLOW_NOT_PROVISIONED")

    def _reservation(
        self, scope: Mapping[str, object], operation: Mapping[str, object], event_id: str
    ) -> Mapping[str, object]:
        policy = _map(scope["policy"], "CONFIG_INVALID")
        code = (
            "NATIVE_RESERVATION_ENDPOINT_UNCONFIRMED"
            if policy["reservation_supported"]
            else "ALLOCATION_PLAN_ONLY"
        )
        return self._result(operation, event_id, _BLOCKED, code)

    def _order_for(
        self, scope: Mapping[str, object], operation: Mapping[str, object]
    ) -> Mapping[str, object]:
        name = _text(operation.get("customer_order"), "CUSTOMER_ORDER_REQUIRED")
        order = self._document("Sales Order", name)
        if order.get("docstatus") != 1:
            raise _ScopeError("SALES_ORDER_SCOPE_MISMATCH")
        self._order_item(scope, order)
        return order

    def _prepare_pick(
        self, scope: Mapping[str, object], operation: Mapping[str, object], event_id: str
    ) -> Mapping[str, object]:
        order = self._order_for(scope, operation)
        tranche = self._tranche_for(scope, operation, require_lot=False)
        existing = self._pick_for(scope, order, tranche)
        if existing is not None:
            return self._result(
                operation,
                event_id,
                _ALREADY_APPLIED,
                documents=[self._public_document("Pick List", existing)],
                snapshot=self.read_case(scope),
            )
        item = self._order_item(scope, order)
        if _quantity(item.get("stock_reserved_qty") or 0, "SOURCE_SCHEMA_MISMATCH") != 0:
            raise _ScopeError("PICK_LIST_REQUIRES_UNRESERVED_STOCK")
        if "priority" in operation:
            allocation = next(
                row
                for row in _rows(scope.get("allocations"), "CONFIG_INVALID")
                if row.get("customer_order") == order.get("name")
            )
            if not _equal(operation.get("priority"), allocation.get("priority")):
                raise _ScopeError("PICK_PRIORITY_MISMATCH")
        accepted = _text(
            _map(scope.get("warehouses"), "CONFIG_INVALID").get("accepted"),
            "CONFIG_INVALID",
        )
        mapped = self._mapped(
            "erpnext.selling.doctype.sales_order.sales_order.create_pick_list",
            _text(order.get("name"), "SALES_ORDER_SCOPE_MISMATCH"),
            target_doc={"doctype": "Pick List", "parent_warehouse": accepted},
        )
        locations = [dict(row) for row in _rows(mapped.get("locations"), "NATIVE_MAPPER_REJECTED")]
        order_name = _text(order.get("name"), "SALES_ORDER_SCOPE_MISMATCH")
        matching = [
            row
            for row in locations
            if row.get("sales_order") == order_name
            and row.get("sales_order_item") == item.get("name")
            and row.get("item_code") == scope.get("item_code")
            and row.get("warehouse") == accepted
        ]
        if len(matching) != 1:
            raise _ScopeError("SCOPED_PICK_LOCATION_UNAVAILABLE")
        expected = _quantity(tranche.get("quantity"), "CONFIG_INVALID", positive=True)
        if _quantity(matching[0].get("actual_qty"), "SCOPED_PICK_LOCATION_UNAVAILABLE") < expected:
            raise _ScopeError("SCOPED_PICK_LOCATION_UNAVAILABLE")
        location = matching[0]
        location["qty"] = expected
        location["stock_qty"] = expected
        location["picked_qty"] = 0
        # ERPNext v16 refreshes locations in before_save unless this native flag
        # is set.  Keep the exact accepted warehouse selected above rather than
        # letting a company-wide mapper reintroduce unrelated Stores stock.
        mapped = {
            **mapped,
            "parent_warehouse": accepted,
            "pick_manually": 1,
            "locations": [location],
        }
        draft = self._create("Pick List", mapped)
        pick = self._document("Pick List", _text(draft.get("name"), "ERP_WRITE_UNCONFIRMED"))
        self._verify_pick(scope, order, pick)
        if not _equal(self._pick_quantity(scope, order, pick), expected):
            raise _ScopeError("PICK_QUANTITY_MISMATCH")
        return self._result(
            operation,
            event_id,
            _APPLIED,
            documents=[self._public_document("Pick List", pick)],
            snapshot=self.read_case(scope),
        )

    def _submit_pick(
        self, scope: Mapping[str, object], operation: Mapping[str, object], event_id: str
    ) -> Mapping[str, object]:
        order = self._order_for(scope, operation)
        tranche = self._tranche_for(scope, operation, require_lot=True)
        pick = self._pick_for(scope, order, tranche)
        if pick is None:
            raise _ScopeError("PICK_LIST_NOT_AVAILABLE")
        self._verify_prepared_reference(operation, pick)
        if pick.get("docstatus") == 1:
            return self._result(
                operation,
                event_id,
                _ALREADY_APPLIED,
                documents=[self._public_document("Pick List", pick)],
                snapshot=self.read_case(scope),
            )
        if pick.get("docstatus") != 0:
            raise _ScopeError("PICK_LIST_NOT_DRAFT")
        expected = _quantity(tranche.get("quantity"), "CONFIG_INVALID", positive=True)
        order_name = _text(order.get("name"), "SALES_ORDER_SCOPE_MISMATCH")
        locations = [dict(row) for row in _rows(pick.get("locations"), "SOURCE_SCHEMA_MISMATCH")]
        matching = [row for row in locations if row.get("sales_order") == order_name]
        if len(matching) != 1 or not _equal(matching[0].get("stock_qty"), expected):
            raise _ScopeError("PICK_QUANTITY_MISMATCH")
        matching[0]["picked_qty"] = expected
        pick_name = _text(pick.get("name"), "PICK_LIST_NOT_AVAILABLE")
        response = _map(
            self._request(
                f"{_RESOURCE}/Pick%20List/{quote(pick_name, safe='')}",
                method="PUT",
                payload={"locations": locations},
            ),
            "ERP_WRITE_UNCONFIRMED",
        )
        draft = _map(response.get("data"), "ERP_WRITE_UNCONFIRMED")
        submitted = self._submit(draft)
        completed_name = _text(submitted.get("name"), "ERP_WRITE_UNCONFIRMED")
        completed = self._document("Pick List", completed_name)
        if completed.get("docstatus") != 1:
            raise _ScopeError("PICK_NOT_SUBMITTED")
        self._verify_pick(scope, order, completed)
        return self._result(
            operation,
            event_id,
            _APPLIED,
            documents=[self._public_document("Pick List", completed)],
            snapshot=self.read_case(scope),
        )

    def _submit_delivery(
        self, scope: Mapping[str, object], operation: Mapping[str, object], event_id: str
    ) -> Mapping[str, object]:
        order = self._order_for(scope, operation)
        tranche = self._tranche_for(scope, operation, require_lot=True)
        existing = self._delivery_for(scope, order, tranche)
        if existing is not None:
            note = existing
            if note.get("docstatus") != 1:
                raise _ScopeError("DELIVERY_NOTE_NOT_SUBMITTED")
            return self._result(
                operation,
                event_id,
                _ALREADY_APPLIED,
                documents=[self._public_document("Delivery Note", note)],
                snapshot=self.read_case(scope),
            )
        pick = self._pick_for(scope, order, tranche)
        if pick is None or pick.get("docstatus") != 1:
            raise _ScopeError("SUBMITTED_PICK_REQUIRED")
        mapped = self._mapped(
            "erpnext.stock.doctype.pick_list.pick_list.create_delivery_note",
            _text(pick.get("name"), "PICK_LIST_NOT_AVAILABLE"),
        )
        # ERPNext v16's native mapper saves and returns a draft Delivery Note.
        # Creating it again would duplicate a delivery and make a later shipment
        # ambiguous, so only submit that returned native draft.
        mapped_name = _text(mapped.get("name"), "NATIVE_MAPPER_REJECTED")
        draft = self._document("Delivery Note", mapped_name)
        if not self._delivery_matches_tranche(
            scope,
            draft,
            order,
            tranche,
            _text(pick.get("name"), "PICK_LIST_NOT_AVAILABLE"),
        ):
            raise _ScopeError("DELIVERY_NOTE_SCOPE_MISMATCH")
        if draft.get("docstatus") == 1:
            return self._result(
                operation,
                event_id,
                _ALREADY_APPLIED,
                documents=[self._public_document("Delivery Note", draft)],
                snapshot=self.read_case(scope),
            )
        if draft.get("docstatus") != 0:
            raise _ScopeError("DELIVERY_NOTE_NOT_DRAFT")
        submitted = self._submit(draft)
        note_name = _text(submitted.get("name"), "ERP_WRITE_UNCONFIRMED")
        note = self._document("Delivery Note", note_name)
        if (
            note.get("docstatus") != 1
            or not self._delivery_matches(
                scope, note, _text(order.get("name"), "SALES_ORDER_SCOPE_MISMATCH")
            )
            or not _equal(
                self._delivery_quantity(scope, note)[1],
                tranche.get("quantity"),
            )
        ):
            raise _ScopeError("DELIVERY_NOTE_SCOPE_MISMATCH")
        return self._result(
            operation,
            event_id,
            _APPLIED,
            documents=[self._public_document("Delivery Note", note)],
            snapshot=self.read_case(scope),
        )

    def _shipment(
        self, scope: Mapping[str, object], operation: Mapping[str, object], event_id: str
    ) -> Mapping[str, object]:
        order = self._order_for(scope, operation)
        tranche = self._tranche_for(scope, operation, require_lot=True)
        shipping = _map(scope.get("shipping"), "SHIPPING_CONFIG_MISSING")
        order_name = _text(order.get("name"), "SALES_ORDER_SCOPE_MISMATCH")
        shipment_id = _text(operation.get("shipment_id"), "SHIPMENT_ID_REQUIRED")
        if shipment_id != self._shipment_id(scope, order_name, event_id):
            raise _ScopeError("SHIPMENT_ID_SCOPE_MISMATCH")
        existing = self._find("Shipment", "shipment_id", shipment_id)
        if existing is not None:
            self._verify_shipment(scope, existing, shipment_id, order_name, tranche)
            return self._result(
                operation,
                event_id,
                _ALREADY_APPLIED,
                documents=[self._public_document("Shipment", existing)],
                snapshot=self.read_case(scope),
            )
        note = self._delivery_for(scope, order, tranche)
        if note is None or note.get("docstatus") != 1:
            raise _ScopeError("SUBMITTED_DELIVERY_NOTE_REQUIRED")
        per_order = _map(
            _map(shipping.get("shipments"), "SHIPPING_CONFIG_MISSING").get(order_name),
            "SHIPPING_CONFIG_MISSING",
        )
        value = _quantity(note.get("grand_total") or 0, "DELIVERY_VALUE_MISSING", positive=True)
        payload = {
            "doctype": "Shipment",
            "pickup_from_type": "Company",
            "pickup_company": scope["company"],
            "pickup_address_name": _text(
                per_order.get("pickup_address"), "SHIPPING_CONFIG_MISSING"
            ),
            "delivery_to_type": "Customer",
            "delivery_customer": order["customer"],
            "delivery_address_name": _text(
                per_order.get("delivery_address"), "SHIPPING_CONFIG_MISSING"
            ),
            "shipment_parcel": [
                {
                    "count": 1,
                    "weight": _quantity(
                        per_order.get("parcel_weight"), "SHIPPING_CONFIG_MISSING", positive=True
                    ),
                    "description": "Synthetic M20 demo goods; no carrier booking",
                }
            ],
            "shipment_delivery_note": [{"delivery_note": note["name"], "grand_total": value}],
            "value_of_goods": value,
            "pickup_date": _text(per_order.get("pickup_date"), "SHIPPING_CONFIG_MISSING"),
            "pickup_from": _text(per_order.get("pickup_from"), "SHIPPING_CONFIG_MISSING"),
            "pickup_to": _text(per_order.get("pickup_to"), "SHIPPING_CONFIG_MISSING"),
            "shipment_type": "Goods",
            "pickup_type": "Self delivery",
            "description_of_content": f"Synthetic demo {scope['item_code']} {scope['uom']}",
            "shipment_id": shipment_id,
            "carrier": "Synthetic event feed only; no carrier booking",
        }
        delivery_contact = per_order.get("delivery_contact")
        if delivery_contact is not None:
            payload["delivery_contact_name"] = _text(delivery_contact, "SHIPPING_CONFIG_MISSING")
        draft = self._create("Shipment", payload)
        submitted = self._submit(draft)
        shipment = self._document("Shipment", _text(submitted.get("name"), "ERP_WRITE_UNCONFIRMED"))
        self._verify_shipment(scope, shipment, shipment_id, order_name, tranche)
        return self._result(
            operation,
            event_id,
            _APPLIED,
            documents=[self._public_document("Shipment", shipment)],
            snapshot=self.read_case(scope),
        )

    def _plan(
        self, scope: Mapping[str, object], operation: Mapping[str, object]
    ) -> Mapping[str, object]:
        plans = self._plans(scope)
        target = _text(operation.get("lot"), "OPERATION_TARGET_REQUIRED")
        matches = [plan for plan in plans if plan.get("lot") == target]
        if len(matches) != 1:
            raise _ScopeError("OPERATION_TARGET_AMBIGUOUS")
        plan = matches[0]
        evidence_ref = operation.get("evidence_ref")
        if (
            operation.get("item_code") != scope.get("item_code")
            or operation.get("synthetic") is not True
            or not isinstance(evidence_ref, str)
            or not evidence_ref.strip()
            or not _equal(operation.get("cartons"), plan.get("cartons"))
            or not _equal(
                operation.get("expected_pack_quantity"), plan.get("expected_pack_quantity")
            )
            or not _equal(operation.get("observed_stock_quantity"), plan.get("quantity"))
        ):
            raise _ScopeError("ARRIVAL_EVIDENCE_SCOPE_MISMATCH")
        return plan

    def _mapped(
        self,
        method: str,
        source_name: str,
        *,
        target_doc: Mapping[str, object] | None = None,
    ) -> Mapping[str, object]:
        payload: dict[str, object] = {"source_name": source_name}
        if target_doc is not None:
            # Frappe's mapped-document endpoint accepts this argument as JSON
            # text; preserve the exact wire shape verified against v16.
            payload["target_doc"] = json.dumps(dict(target_doc), sort_keys=True)
        response = _map(
            self._request(
                f"/api/method/{method}", method="POST", payload=payload
            ),
            "NATIVE_MAPPER_REJECTED",
        )
        return dict(_map(response.get("message"), "NATIVE_MAPPER_REJECTED"))

    def _create(self, doctype: str, document: Mapping[str, object]) -> Mapping[str, object]:
        response = _map(
            self._request(
                f"{_RESOURCE}/{quote(doctype, safe='')}", method="POST", payload=dict(document)
            ),
            "ERP_WRITE_UNCONFIRMED",
        )
        return dict(_map(response.get("data"), "ERP_WRITE_UNCONFIRMED"))

    def _submit(self, document: Mapping[str, object]) -> Mapping[str, object]:
        response = _map(
            self._request(
                "/api/method/frappe.client.submit", method="POST", payload={"doc": dict(document)}
            ),
            "ERP_WRITE_UNCONFIRMED",
        )
        return dict(_map(response.get("message"), "ERP_WRITE_UNCONFIRMED"))
