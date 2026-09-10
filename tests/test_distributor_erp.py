from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from typing import Any, cast
from urllib.parse import ParseResult, parse_qs, unquote, urlparse

from the_missing_20.adapters.demo_executor import DemoExecutionBlocked
from the_missing_20.adapters.distributor_erp import DistributorERP

COMPANY = "Missing 20 Automotive Demo"
SUPPLIER = "M20 Controller Systems Ltd."
ITEM = "M20-DEMO-CARTON"
PO = "PUR-ORD-2026-00016"
PO_ITEM = "po16-item"
WAREHOUSE = "M20 Distributor R4 Accepted - M20"
QUARANTINE = "M20 Distributor R4 Inspection - M20"
ORDER_24 = "SAL-ORD-M20-24"
ORDER_15 = "SAL-ORD-M20-15"


class _PublicCredentials:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url


def r4_config() -> dict[str, Any]:
    return {
        "case_id": "M20-DIST-R4-PO16",
        "case_label": "Synthetic PO16 follow-on distribution",
        "synthetic_input": True,
        "company": COMPANY,
        "supplier": SUPPLIER,
        "item_code": ITEM,
        "uom": "Box",
        "stock_uom": "Box",
        "expected_pack_quantity": 1,
        "cartons": 39,
        "purchase_order": PO,
        "purchase_order_item": PO_ITEM,
        "marker": "M20 DIST R4 PO16 SYNTHETIC",
        "currency": "USD",
        "unit_rate": 50,
        "warehouses": {"accepted": WAREHOUSE, "quarantine": QUARANTINE},
        "receipt_plans": [
            {
                "lot": "R4-ARRIVAL-20",
                "marker": "M20 DIST R4 PO16 SYNTHETIC ARRIVAL 20",
                "quantity": 20,
                "cartons": 20,
                "expected_pack_quantity": 1,
                "warehouse": WAREHOUSE,
            },
            {
                "lot": "R4-ARRIVAL-19",
                "marker": "M20 DIST R4 PO16 SYNTHETIC ARRIVAL 19",
                "quantity": 19,
                "cartons": 19,
                "expected_pack_quantity": 1,
                "warehouse": WAREHOUSE,
            },
        ],
        "lots": [
            {"lot": "R4-ARRIVAL-20", "expected_quantity": 20, "cartons": 20},
            {"lot": "R4-ARRIVAL-19", "expected_quantity": 19, "cartons": 19},
        ],
        "allocations": [
            {"customer_order": ORDER_24, "requested_quantity": 24, "priority": 1},
            {"customer_order": ORDER_15, "requested_quantity": 15, "priority": 2},
        ],
        "customer_orders": [ORDER_24, ORDER_15],
        "pick_tranches": [
            {"customer_order": ORDER_24, "lot": "R4-ARRIVAL-20", "quantity": 20},
            {"customer_order": ORDER_24, "lot": "R4-ARRIVAL-19", "quantity": 4},
            {"customer_order": ORDER_15, "lot": "R4-ARRIVAL-19", "quantity": 15},
        ],
        "policy": {"inspection_required": False, "reservation_supported": False},
        "shipping": {
            "native_read_enabled": True,
            "shipments": {
                ORDER_24: {
                    "shipment_id_prefix": "M20-DIST-R4-PO16-SHIP-24",
                    "pickup_address": "ADDR-M20-WAREHOUSE",
                    "delivery_address": "ADDR-M20-CUSTOMER-24",
                    "delivery_contact": "CONTACT-M20-CUSTOMER-24",
                    "pickup_date": "2026-09-10",
                    "pickup_from": "09:00:00",
                    "pickup_to": "17:00:00",
                    "parcel_weight": 1,
                },
                ORDER_15: {
                    "shipment_id_prefix": "M20-DIST-R4-PO16-SHIP-15",
                    "pickup_address": "ADDR-M20-WAREHOUSE",
                    "delivery_address": "ADDR-M20-CUSTOMER-15",
                    "delivery_contact": "CONTACT-M20-CUSTOMER-15",
                    "pickup_date": "2026-09-10",
                    "pickup_from": "09:00:00",
                    "pickup_to": "17:00:00",
                    "parcel_weight": 1,
                },
            },
        },
    }


class NativeERP:
    """Small native-document fake; it does not fake bridge outcomes."""

    _environment = "demo"

    def __init__(self) -> None:
        self._credentials = _PublicCredentials("https://erp.example.test")
        self.documents: dict[str, dict[str, dict[str, Any]]] = {
            "Purchase Order": {
                PO: {
                    "doctype": "Purchase Order",
                    "name": PO,
                    "docstatus": 1,
                    "company": COMPANY,
                    "supplier": SUPPLIER,
                    "items": [
                        {
                            "name": PO_ITEM,
                            "item_code": ITEM,
                            "qty": 40,
                            "received_qty": 1,
                            "uom": "Box",
                            "stock_uom": "Box",
                            "conversion_factor": 1,
                            "schedule_date": "2026-09-10",
                        }
                    ],
                }
            },
            "Sales Order": {
                ORDER_24: self._sales_order(ORDER_24, "M20 Customer 24", 24),
                ORDER_15: self._sales_order(ORDER_15, "M20 Customer 15", 15),
            },
            "Purchase Receipt": {},
            "Pick List": {},
            "Delivery Note": {},
            "Shipment": {},
        }
        self.ledger: list[dict[str, object]] = []
        self.calls: list[tuple[str, str, object | None]] = []
        self.sequence = 0

    @staticmethod
    def _sales_order(name: str, customer: str, quantity: int) -> dict[str, object]:
        return {
            "doctype": "Sales Order",
            "name": name,
            "docstatus": 1,
            "company": COMPANY,
            "customer": customer,
            "items": [
                {
                    "name": f"{name}-ITEM",
                    "item_code": ITEM,
                    "qty": quantity,
                    "uom": "Box",
                    "stock_reserved_qty": 0,
                }
            ],
        }

    def _document(self, doctype: str, name: str) -> Mapping[str, object]:
        return copy.deepcopy(self.documents[doctype][name])

    def _request(self, path: str, *, method: str = "GET", payload: object | None = None) -> object:
        self.calls.append((path, method, copy.deepcopy(payload)))
        parsed = urlparse(path)
        if method == "GET":
            return self._get(parsed)
        if method == "POST" and parsed.path.startswith("/api/method/"):
            return self._method(parsed.path, payload)
        if method == "POST" and parsed.path.startswith("/api/resource/"):
            return self._create(unquote(parsed.path.rsplit("/", 1)[-1]), payload)
        if method == "PUT" and parsed.path.startswith("/api/resource/Pick%20List/"):
            name = unquote(parsed.path.rsplit("/", 1)[-1])
            body: dict[str, Any] = dict(payload) if isinstance(payload, Mapping) else {}
            self.documents["Pick List"][name]["locations"] = copy.deepcopy(body["locations"])
            return {"data": copy.deepcopy(self.documents["Pick List"][name])}
        raise AssertionError(f"unexpected request {method} {path}")

    def _get(self, parsed: ParseResult) -> dict[str, object]:
        doctype = unquote(parsed.path.rsplit("/", 1)[-1])
        filters = cast(list[list[object]], json.loads(parse_qs(parsed.query)["filters"][0]))
        if doctype == "Stock Ledger Entry":
            return {
                "data": copy.deepcopy([row for row in self.ledger if self._matches(row, filters)])
            }
        rows = [
            {"name": name, "docstatus": document["docstatus"]}
            for name, document in self.documents.get(doctype, {}).items()
            if self._matches(document, filters)
        ]
        return {"data": rows}

    @staticmethod
    def _matches(document: Mapping[str, object], filters: list[list[object]]) -> bool:
        for field, operator, expected in filters:
            actual = document.get(str(field))
            if operator == "=" and actual == expected:
                continue
            if (
                operator == "like"
                and isinstance(actual, str)
                and isinstance(expected, str)
                and expected.endswith("%")
                and actual.startswith(expected[:-1])
            ):
                continue
            return False
        return True

    def _method(self, path: str, payload: object | None) -> dict[str, object]:
        body: dict[str, Any] = dict(payload) if isinstance(payload, Mapping) else {}
        if path.endswith("create_pick_list"):
            source = str(body["source_name"])
            order = self.documents["Sales Order"][source]
            row = order["items"][0]
            target = body.get("target_doc")
            parsed_target = json.loads(target) if isinstance(target, str) else {}
            target_warehouse = parsed_target.get("parent_warehouse")
            if target_warehouse == WAREHOUSE:
                locations = [
                    {
                        "sales_order": source,
                        "sales_order_item": row["name"],
                        "item_code": ITEM,
                        "warehouse": WAREHOUSE,
                        "qty": row["qty"],
                        "stock_qty": row["qty"],
                        "picked_qty": 0,
                        "actual_qty": 20,
                    }
                ]
            else:
                locations = [
                    {
                        "sales_order": source,
                        "sales_order_item": row["name"],
                        "item_code": ITEM,
                        "warehouse": "Stores - M20",
                        "qty": 6,
                        "stock_qty": 6,
                        "picked_qty": 0,
                        "actual_qty": 6,
                    },
                    {
                        "sales_order": source,
                        "sales_order_item": row["name"],
                        "item_code": ITEM,
                        "warehouse": WAREHOUSE,
                        "qty": row["qty"] - 6,
                        "stock_qty": row["qty"] - 6,
                        "picked_qty": 0,
                        "actual_qty": 20,
                    },
                ]
            return {
                "message": {
                    "doctype": "Pick List",
                    "company": COMPANY,
                    "customer": order["customer"],
                    "purpose": "Delivery",
                    "locations": locations,
                }
            }
        if path.endswith("create_delivery_note"):
            pick = self.documents["Pick List"][str(body["source_name"])]
            location = pick["locations"][0]
            order = self.documents["Sales Order"][str(location["sales_order"])]
            # ERPNext v16's mapper saves a Delivery Note draft itself.  The
            # bridge must submit this exact native draft rather than POST it
            # again as a second document.
            created = self._create(
                "Delivery Note",
                {
                    "doctype": "Delivery Note",
                    "company": COMPANY,
                    "customer": order["customer"],
                    "grand_total": location["picked_qty"] * 50,
                    "items": [
                        {
                            "item_code": ITEM,
                            "qty": location["picked_qty"],
                            "warehouse": location["warehouse"],
                            "against_sales_order": location["sales_order"],
                            "against_pick_list": pick["name"],
                        }
                    ],
                },
            )
            return {"message": created["data"]}
        if path.endswith("frappe.client.submit"):
            document = dict(body["doc"])
            doctype = str(document["doctype"])
            name = str(document["name"])
            stored = self.documents[doctype][name]
            stored["docstatus"] = 1
            stored["status"] = "Submitted"
            if doctype == "Purchase Receipt":
                item = stored["items"][0]
                po_item = self.documents["Purchase Order"][PO]["items"][0]
                po_item["received_qty"] += item["qty"]
                self.ledger.append(
                    {
                        "name": f"SLE-{name}",
                        "voucher_type": "Purchase Receipt",
                        "voucher_no": name,
                        "voucher_detail_no": item["name"],
                        "item_code": ITEM,
                        "warehouse": item["warehouse"],
                        "actual_qty": item["qty"],
                        "is_cancelled": 0,
                    }
                )
            return {"message": copy.deepcopy(stored)}
        raise AssertionError(f"unexpected method {path}")

    def _create(self, doctype: str, payload: object | None) -> dict[str, object]:
        self.sequence += 1
        document: dict[str, Any] = copy.deepcopy(
            dict(payload) if isinstance(payload, Mapping) else {}
        )
        name = f"{doctype[:2].upper()}-{self.sequence:03}"
        document.update(name=name, docstatus=0, status="Draft")
        if doctype == "Purchase Receipt":
            document["items"][0]["name"] = f"{name}-ITEM"
        self.documents[doctype][name] = document
        return {"data": copy.deepcopy(document)}


def _arrival(lot: str, quantity: int) -> dict[str, object]:
    return {
        "kind": "receive_arrival",
        "item_code": ITEM,
        "lot": lot,
        "cartons": quantity,
        "expected_pack_quantity": 1,
        "observed_stock_quantity": quantity,
        "evidence_ref": f"synthetic:{lot}",
        "synthetic": True,
    }


def _pick_operation(
    kind: str,
    *,
    order: str,
    lot: str,
    quantity: int,
    prepared: Mapping[str, object] | None = None,
) -> dict[str, object]:
    operation: dict[str, object] = {
        "kind": kind,
        "customer_order": order,
        "lot": lot,
        "quantity": quantity,
    }
    if prepared is not None:
        operation["prepared_tranches"] = [
            {
                "event_id": prepared["event_id"],
                "quantity": quantity,
                "documents": prepared["documents"],
            }
        ]
    return operation


def _result(value: Mapping[str, object]) -> dict[str, Any]:
    """The bridge's public JSON mapping is a concrete dict in this fixture."""

    return cast(dict[str, Any], value)


def _run_tranche(
    bridge: DistributorERP,
    settings: Mapping[str, object],
    *,
    order: str,
    lot: str,
    quantity: int,
    event_id: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    priority = 1 if order == ORDER_24 else 2
    prepared = _result(
        bridge.apply_operation(
            settings,
            {
                "kind": "prepare_pick",
                "customer_order": order,
                "quantity": quantity,
                "priority": priority,
            },
            f"prepare-{event_id}",
        )
    )
    assert prepared["status"] == "APPLIED"
    picked = _result(
        bridge.apply_operation(
            settings,
            _pick_operation(
                "submit_pick", order=order, lot=lot, quantity=quantity, prepared=prepared
            ),
            event_id,
        )
    )
    assert picked["status"] == "APPLIED"
    delivery = _result(
        bridge.apply_operation(
            settings,
            _pick_operation("submit_delivery_note", order=order, lot=lot, quantity=quantity),
            f"delivery-{event_id}",
        )
    )
    assert delivery["status"] == "APPLIED"
    shipment = _result(
        bridge.apply_operation(
            settings,
            {
                **_pick_operation("create_shipment", order=order, lot=lot, quantity=quantity),
                "shipment_id": DistributorERP._shipment_id(settings, order, event_id),
            },
            event_id,
        )
    )
    assert shipment["status"] == "APPLIED"
    return prepared, delivery, shipment


def test_r4_two_receipts_three_partial_native_pick_delivery_and_shipments() -> None:
    client = NativeERP()
    bridge = DistributorERP(client)
    settings = r4_config()

    before = _result(bridge.read_case(settings))
    assert before["source_status"] == "CURRENT"
    assert before["quantities"] == {
        "ordered": 39.0,
        "received": 0.0,
        "usable": 0.0,
        "held": 0.0,
        "missing": 39.0,
        "allocated": 0.0,
        "dispatched": 0.0,
        "delivery_confirmed": 0.0,
        "uom": "Box",
        "cartons": 0.0,
    }
    assert before["parent_purchase_order"] == {
        "name": PO,
        "ordered": 40.0,
        "received": 1.0,
        "uom": "Box",
    }

    for lot, quantity, event_id in (
        ("R4-ARRIVAL-20", 20, "arrival-r4-20"),
        ("R4-ARRIVAL-19", 19, "arrival-r4-19"),
    ):
        receipt = _result(bridge.apply_operation(settings, _arrival(lot, quantity), event_id))
        assert receipt["status"] == "APPLIED"
        assert receipt["documents"][0]["kind"] == "Purchase Receipt"
    assert (
        bridge.apply_operation(settings, _arrival("R4-ARRIVAL-20", 20), "replay-arrival-20")[
            "status"
        ]
        == "ALREADY_APPLIED"
    )

    after_receipts = _result(bridge.read_case(settings))
    assert after_receipts["quantities"]["ordered"] == 39
    assert after_receipts["quantities"]["received"] == after_receipts["quantities"]["usable"] == 39
    assert after_receipts["quantities"]["cartons"] == 39
    assert after_receipts["parent_purchase_order"]["received"] == 40
    assert [row["allocated"] for row in after_receipts["allocations"]] == [24.0, 15.0]

    results = [
        _run_tranche(
            bridge,
            settings,
            order=ORDER_24,
            lot="R4-ARRIVAL-20",
            quantity=20,
            event_id="picked-r4-20",
        ),
        _run_tranche(
            bridge,
            settings,
            order=ORDER_24,
            lot="R4-ARRIVAL-19",
            quantity=4,
            event_id="picked-r4-4",
        ),
        _run_tranche(
            bridge,
            settings,
            order=ORDER_15,
            lot="R4-ARRIVAL-19",
            quantity=15,
            event_id="picked-r4-15",
        ),
    ]
    final = _result(bridge.read_case(settings))
    assert final["quantities"]["dispatched"] == 39
    assert final["quantities"]["usable"] == final["quantities"]["held"] == 0
    assert final["quantities"]["delivery_confirmed"] == 0
    assert [
        (row["customer_order"], row["dispatched"], row["backordered"])
        for row in final["allocations"]
    ] == [
        (ORDER_24, 24.0, 0.0),
        (ORDER_15, 15.0, 0.0),
    ]
    assert len(client.documents["Pick List"]) == len(client.documents["Delivery Note"]) == 3
    assert len(client.documents["Shipment"]) == 3
    assert all(
        pick["parent_warehouse"] == WAREHOUSE and pick["pick_manually"] == 1
        for pick in client.documents["Pick List"].values()
    )
    assert all(
        len(pick["locations"]) == 1 and pick["locations"][0]["warehouse"] == WAREHOUSE
        for pick in client.documents["Pick List"].values()
    )
    mapper_payloads = [
        payload
        for path, method, payload in client.calls
        if method == "POST" and path.endswith("sales_order.create_pick_list")
    ]
    assert mapper_payloads and all(
        isinstance(payload, Mapping)
        and json.loads(cast(str, payload.get("target_doc")))
        == {"doctype": "Pick List", "parent_warehouse": WAREHOUSE}
        for payload in mapper_payloads
    )
    assert all(
        str(document["url"]).startswith("https://erp.example.test/app/")
        for document in final["documents"]
    )
    shipment_names = [
        shipment["documents"][0]["name"] for _prepared, _delivery, shipment in results
    ]
    assert len(set(shipment_names)) == 3
    assert {
        shipment["delivery_address_name"] for shipment in client.documents["Shipment"].values()
    } == {
        "ADDR-M20-CUSTOMER-24",
        "ADDR-M20-CUSTOMER-15",
    }
    assert all(
        shipment["carrier"] == "Synthetic event feed only; no carrier booking"
        for shipment in client.documents["Shipment"].values()
    )


def test_wrong_lot_for_partial_tranche_stops_before_native_write() -> None:
    client = NativeERP()
    bridge = DistributorERP(client)
    result = _result(
        bridge.apply_operation(
            r4_config(),
            _pick_operation("submit_pick", order=ORDER_24, lot="R4-ARRIVAL-20", quantity=4),
            "picked-r4-4",
        )
    )
    assert result["status"] == "BLOCKED"
    assert result["error_code"] == "PICK_TRANCHE_SCOPE_MISMATCH"
    assert not [call for call in client.calls if call[1] == "POST"]


def test_saved_submitted_delivery_wins_over_a_matching_stale_draft_for_shipment() -> None:
    client = NativeERP()
    bridge = DistributorERP(client)
    settings = r4_config()
    assert (
        _result(bridge.apply_operation(settings, _arrival("R4-ARRIVAL-20", 20), "arrival-r4-20"))[
            "status"
        ]
        == "APPLIED"
    )
    prepared = _result(
        bridge.apply_operation(
            settings,
            {"kind": "prepare_pick", "customer_order": ORDER_24, "quantity": 20, "priority": 1},
            "prepare-picked-r4-20",
        )
    )
    assert (
        _result(
            bridge.apply_operation(
                settings,
                _pick_operation(
                    "submit_pick",
                    order=ORDER_24,
                    lot="R4-ARRIVAL-20",
                    quantity=20,
                    prepared=prepared,
                ),
                "picked-r4-20",
            )
        )["status"]
        == "APPLIED"
    )
    assert (
        _result(
            bridge.apply_operation(
                settings,
                _pick_operation(
                    "submit_delivery_note", order=ORDER_24, lot="R4-ARRIVAL-20", quantity=20
                ),
                "delivery-picked-r4-20",
            )
        )["status"]
        == "APPLIED"
    )

    submitted = next(
        document
        for document in client.documents["Delivery Note"].values()
        if document["docstatus"] == 1
    )
    stale = copy.deepcopy(submitted)
    stale.update(name="DN-STALE-DRAFT", docstatus=0, status="Draft")
    client.documents["Delivery Note"]["DN-STALE-DRAFT"] = stale

    shipment = _result(
        bridge.apply_operation(
            settings,
            {
                **_pick_operation(
                    "create_shipment", order=ORDER_24, lot="R4-ARRIVAL-20", quantity=20
                ),
                "shipment_id": DistributorERP._shipment_id(settings, ORDER_24, "picked-r4-20"),
            },
            "picked-r4-20",
        )
    )
    assert shipment["status"] == "APPLIED"
    native_shipment = next(iter(client.documents["Shipment"].values()))
    assert native_shipment["shipment_delivery_note"] == [
        {"delivery_note": submitted["name"], "grand_total": 1000}
    ]


def test_source_scope_drift_and_pack_mismatch_stop_before_a_write() -> None:
    client = NativeERP()
    bridge = DistributorERP(client)
    settings = r4_config()
    settings["receipt_plans"][0]["expected_pack_quantity"] = 10

    result = _result(bridge.apply_operation(settings, _arrival("R4-ARRIVAL-20", 20), "bad-pack"))
    assert result["status"] == "BLOCKED"
    assert result["error_code"] == "PACK_QUANTITY_MISMATCH"
    assert not [call for call in client.calls if call[1] == "POST"]

    settings = r4_config()
    client.documents["Purchase Order"][PO]["items"][0]["uom"] = "Nos"
    assert _result(bridge.read_case(settings))["source_error"] == "PURCHASE_ORDER_LINE_MISMATCH"


def test_quality_reservation_and_permission_refusal_do_not_fabricate_effects() -> None:
    client = NativeERP()
    bridge = DistributorERP(client)
    settings = r4_config()
    quality = bridge.apply_operation(
        settings, {"kind": "record_inspection", "lot": "R4-ARRIVAL-20"}, "qi-1"
    )
    reservation = bridge.apply_operation(
        settings,
        {"kind": "reserve_allocation", "customer_order": ORDER_24, "quantity": 24},
        "reserve-1",
    )
    assert quality["status"] == reservation["status"] == "BLOCKED"
    assert quality["error_code"] == "QUALITY_WORKFLOW_NOT_PROVISIONED"
    assert reservation["error_code"] == "ALLOCATION_PLAN_ONLY"

    class DeniedERP(NativeERP):
        def _request(
            self, path: str, *, method: str = "GET", payload: object | None = None
        ) -> object:
            if path.endswith("create_pick_list"):
                raise DemoExecutionBlocked("ERPNext rejected POST /api/method (403): denied")
            return super()._request(path, method=method, payload=payload)

    denied = DistributorERP(DeniedERP())
    result = _result(
        denied.apply_operation(
            r4_config(),
            {"kind": "prepare_pick", "customer_order": ORDER_24, "quantity": 20, "priority": 1},
            "prepare-picked-r4-20",
        )
    )
    assert result["status"] == "BLOCKED"
    assert result["error_code"] == "ERP_ACCESS_DENIED"
