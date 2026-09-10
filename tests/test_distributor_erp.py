from __future__ import annotations

import copy
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast
from urllib.parse import ParseResult, parse_qs, unquote, urlparse

import pytest

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
    logged_user = "qa.operator@example.test"

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
        if method == "GET" and parsed.path == "/api/method/frappe.auth.get_logged_user":
            return {"message": self.logged_user}
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
        if doctype == "Quality Inspection":
            inspected_by = document.get("inspected_by")
            if (
                not isinstance(inspected_by, str)
                or not inspected_by.strip()
                or inspected_by.strip().lower() == "user"
                or inspected_by.strip() != self.logged_user
            ):
                raise AssertionError("Quality Inspection requires the authenticated ERP user")
        name = f"{doctype[:2].upper()}-{self.sequence:03}"
        document.update(name=name, docstatus=0, status="Draft")
        if doctype == "Purchase Receipt":
            document["items"][0]["name"] = f"{name}-ITEM"
        self.documents[doctype][name] = document
        return {"data": copy.deepcopy(document)}


COMPONENT_ITEM = "M20-DIST-COMPONENT-NOS"
COMPONENT_PO = "PUR-ORD-M20-COMPONENT-40"
COMPONENT_PO_ITEM = "M20-COMPONENT-PO-ITEM"
COMPONENT_ACCEPTED = "M20 Distributor Component Accepted - M20"
COMPONENT_INSPECTION = "M20 Distributor Component Inspection - M20"
COMPONENT_ORDER_25 = "SAL-ORD-M20-COMPONENT-25"
COMPONENT_ORDER_15 = "SAL-ORD-M20-COMPONENT-15"


def component_config() -> dict[str, Any]:
    return {
        "case_id": "M20-DIST-COMPONENT-40",
        "case_label": "Synthetic component count and quality release",
        "synthetic_input": True,
        "company": COMPANY,
        "supplier": SUPPLIER,
        "item_code": COMPONENT_ITEM,
        "uom": "Nos",
        "stock_uom": "Nos",
        "expected_pack_quantity": 10,
        "cartons": 5,
        "purchase_order": COMPONENT_PO,
        "purchase_order_item": COMPONENT_PO_ITEM,
        "marker": "M20 DIST COMPONENT 40 SYNTHETIC",
        "currency": "USD",
        "unit_rate": 4,
        "warehouses": {"accepted": COMPONENT_ACCEPTED, "quarantine": COMPONENT_INSPECTION},
        "receipt_plans": [
            {
                "lot": "LOT-A",
                "marker": "M20 DIST COMPONENT 40 SYNTHETIC LOT-A",
                "quantity": 20,
                "cartons": 2,
                "expected_pack_quantity": 10,
                "warehouse": COMPONENT_INSPECTION,
                "batch_no": "M20-DIST-COMP-BATCH-A",
            },
            {
                "lot": "LOT-B",
                "marker": "M20 DIST COMPONENT 40 SYNTHETIC LOT-B",
                "quantity": 18,
                "cartons": 2,
                "expected_pack_quantity": 10,
                "warehouse": COMPONENT_INSPECTION,
                "batch_no": "M20-DIST-COMP-BATCH-B",
            },
            {
                "lot": "LOT-C",
                "marker": "M20 DIST COMPONENT 40 SYNTHETIC LOT-C",
                "quantity": 2,
                "cartons": 1,
                "expected_pack_quantity": 2,
                "warehouse": COMPONENT_INSPECTION,
                "batch_no": "M20-DIST-COMP-BATCH-C",
            },
        ],
        "lots": [
            {"lot": "LOT-A", "expected_quantity": 20, "cartons": 2, "expected_pack_quantity": 10},
            {"lot": "LOT-B", "expected_quantity": 18, "cartons": 2, "expected_pack_quantity": 10},
            {
                "lot": "LOT-C",
                "expected_quantity": 2,
                "cartons": 1,
                "expected_pack_quantity": 2,
                "replacement_for_lot": "LOT-B",
            },
        ],
        "allocations": [
            {"customer_order": COMPONENT_ORDER_25, "requested_quantity": 25, "priority": 1},
            {"customer_order": COMPONENT_ORDER_15, "requested_quantity": 15, "priority": 2},
        ],
        "customer_orders": [COMPONENT_ORDER_25, COMPONENT_ORDER_15],
        "pick_tranches": [
            {"customer_order": COMPONENT_ORDER_25, "lot": "LOT-A", "quantity": 20},
            {"customer_order": COMPONENT_ORDER_25, "lot": "LOT-B", "quantity": 5},
            {"customer_order": COMPONENT_ORDER_15, "lot": "LOT-B", "quantity": 13},
            {"customer_order": COMPONENT_ORDER_15, "lot": "LOT-C", "quantity": 2},
        ],
        "policy": {
            "inspection_required": True,
            "reservation_supported": False,
            "inspection_criteria": {"diameter_mm": {"minimum": 9.9, "maximum": 10.1}},
        },
        "quality_parameters": {"diameter_mm": "M20 Distributor Diameter"},
        "shipping": {
            "native_read_enabled": True,
            "shipments": {
                COMPONENT_ORDER_25: {
                    "shipment_id_prefix": "M20-DIST-COMPONENT-40-SHIP-25",
                    "pickup_address": "ADDR-M20-COMPONENT-PICKUP",
                    "delivery_address": "ADDR-M20-COMPONENT-25",
                    "pickup_date": "2026-09-10",
                    "pickup_from": "09:00:00",
                    "pickup_to": "17:00:00",
                    "parcel_weight": 1,
                },
                COMPONENT_ORDER_15: {
                    "shipment_id_prefix": "M20-DIST-COMPONENT-40-SHIP-15",
                    "pickup_address": "ADDR-M20-COMPONENT-PICKUP",
                    "delivery_address": "ADDR-M20-COMPONENT-15",
                    "pickup_date": "2026-09-10",
                    "pickup_from": "09:00:00",
                    "pickup_to": "17:00:00",
                    "parcel_weight": 1,
                },
            },
        },
    }


def contract_component_config() -> dict[str, Any]:
    """Fresh-case terms: promise date precedes the numeric customer priority."""

    config = component_config()
    config["allocation_policy"] = {"version": "v1"}
    config["allocations"] = [
        {
            "customer_order": COMPONENT_ORDER_25,
            "requested_quantity": 25,
            "priority": 2,
            "promised_delivery_at": "2026-09-11T09:00:00+00:00",
            "customer_priority": 2,
            "partial_dispatch": True,
            "minimum_dispatch_quantity": 10,
            "allow_final_remainder": True,
        },
        {
            "customer_order": COMPONENT_ORDER_15,
            "requested_quantity": 15,
            "priority": 1,
            "promised_delivery_at": "2026-09-12T09:00:00+00:00",
            "customer_priority": 1,
            "partial_dispatch": True,
            "minimum_dispatch_quantity": 5,
            "allow_final_remainder": True,
        },
    ]
    return config


class ComponentNativeERP(NativeERP):
    """Focused native-document fake for the component QI → stock-release path."""

    def __init__(self) -> None:
        self._credentials = _PublicCredentials("https://erp.example.test")
        self.documents: dict[str, dict[str, dict[str, Any]]] = {
            "Purchase Order": {
                COMPONENT_PO: {
                    "doctype": "Purchase Order",
                    "name": COMPONENT_PO,
                    "docstatus": 1,
                    "company": COMPANY,
                    "supplier": SUPPLIER,
                    "items": [
                        {
                            "name": COMPONENT_PO_ITEM,
                            "item_code": COMPONENT_ITEM,
                            "qty": 40,
                            "received_qty": 0,
                            "uom": "Nos",
                            "stock_uom": "Nos",
                            "conversion_factor": 1,
                            "schedule_date": "2026-09-10",
                        }
                    ],
                }
            },
            "Sales Order": {
                COMPONENT_ORDER_25: self._component_order(
                    COMPONENT_ORDER_25, "M20 Component 25", 25
                ),
                COMPONENT_ORDER_15: self._component_order(
                    COMPONENT_ORDER_15, "M20 Component 15", 15
                ),
            },
            "Purchase Receipt": {},
            "Stock Entry": {},
            "Quality Inspection": {},
            "Pick List": {},
            "Delivery Note": {},
            "Shipment": {},
        }
        self.ledger: list[dict[str, object]] = []
        self.calls: list[tuple[str, str, object | None]] = []
        self.sequence = 0

    @staticmethod
    def _component_order(name: str, customer: str, quantity: int) -> dict[str, object]:
        return {
            "doctype": "Sales Order",
            "name": name,
            "docstatus": 1,
            "company": COMPANY,
            "customer": customer,
            "items": [
                {
                    "name": f"{name}-ITEM",
                    "item_code": COMPONENT_ITEM,
                    "qty": quantity,
                    "uom": "Nos",
                    "stock_reserved_qty": 0,
                }
            ],
        }

    def _method(self, path: str, payload: object | None) -> dict[str, object]:
        body: dict[str, Any] = dict(payload) if isinstance(payload, Mapping) else {}
        if path.endswith("create_pick_list"):
            order = self.documents["Sales Order"][str(body["source_name"])]
            row = order["items"][0]
            locations = [
                {
                    "sales_order": order["name"],
                    "sales_order_item": row["name"],
                    "item_code": COMPONENT_ITEM,
                    "warehouse": COMPONENT_ACCEPTED,
                    "qty": transfer["items"][0]["qty"],
                    "stock_qty": transfer["items"][0]["qty"],
                    "picked_qty": 0,
                    "actual_qty": transfer["items"][0]["qty"],
                    "batch_no": transfer["items"][0]["batch_no"],
                    "use_serial_batch_fields": 1,
                }
                for transfer in self.documents["Stock Entry"].values()
                if transfer["docstatus"] == 1
                and transfer["items"][0]["t_warehouse"] == COMPONENT_ACCEPTED
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
            created = self._create(
                "Delivery Note",
                {
                    "doctype": "Delivery Note",
                    "company": COMPANY,
                    "customer": order["customer"],
                    "grand_total": location["picked_qty"] * 4,
                    "items": [
                        {
                            "item_code": COMPONENT_ITEM,
                            "qty": location["picked_qty"],
                            "warehouse": location["warehouse"],
                            "batch_no": location["batch_no"],
                            "use_serial_batch_fields": 1,
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
                self.documents["Purchase Order"][COMPONENT_PO]["items"][0]["received_qty"] += item[
                    "qty"
                ]
                self.ledger.append(
                    {
                        "name": f"SLE-{name}",
                        "voucher_type": "Purchase Receipt",
                        "voucher_no": name,
                        "voucher_detail_no": item["name"],
                        "item_code": COMPONENT_ITEM,
                        "warehouse": item["warehouse"],
                        "actual_qty": item["qty"],
                        "is_cancelled": 0,
                    }
                )
            elif doctype == "Quality Inspection":
                reading = stored["readings"][0]
                measured = float(reading["reading_1"])
                accepted = float(reading["min_value"]) <= measured <= float(reading["max_value"])
                reading["status"] = "Accepted" if accepted else "Rejected"
                stored["status"] = "Accepted" if accepted else "Rejected"
                transfer = self.documents["Stock Entry"][str(stored["reference_name"])]
                transfer["items"][0]["quality_inspection"] = name
            return {"message": copy.deepcopy(stored)}
        raise AssertionError(f"unexpected method {path}")


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


def _component_arrival(lot: str, cartons: int, quantity: int, pack: int) -> dict[str, object]:
    return {
        "kind": "receive_arrival",
        "item_code": COMPONENT_ITEM,
        "lot": lot,
        "cartons": cartons,
        "expected_pack_quantity": pack,
        "observed_stock_quantity": quantity,
        "evidence_ref": f"synthetic:{lot}:arrival",
        "synthetic": True,
    }


def _inspection(
    lot: str,
    *,
    result: str,
    scope: str,
    measured: float,
    sample_quantity: int,
) -> dict[str, object]:
    return {
        "kind": "record_inspection",
        "lot": lot,
        "result": result,
        "scope": scope,
        "metric": "diameter_mm",
        "measured": measured,
        "criterion": {"minimum": 9.9, "maximum": 10.1},
        "sample_quantity": sample_quantity,
        "inspection_report_ref": f"synthetic:{lot}:{scope}:{result}",
        "evidence_ref": f"synthetic:{lot}:{scope}:{result}:evidence",
        "synthetic": True,
    }


def _release(lot: str) -> dict[str, object]:
    return {
        "kind": "release_from_quality",
        "lot": lot,
        "scope": "WHOLE_LOT",
        "inspection_evidence_ref": f"synthetic:{lot}:whole:evidence",
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


def _run_component_tranche(
    bridge: DistributorERP,
    settings: Mapping[str, object],
    *,
    order: str,
    lot: str,
    quantity: int,
    priority: int,
    event_id: str,
) -> None:
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
    assert (
        _result(
            bridge.apply_operation(
                settings,
                _pick_operation(
                    "submit_pick", order=order, lot=lot, quantity=quantity, prepared=prepared
                ),
                event_id,
            )
        )["status"]
        == "APPLIED"
    )
    assert (
        _result(
            bridge.apply_operation(
                settings,
                _pick_operation("submit_delivery_note", order=order, lot=lot, quantity=quantity),
                f"delivery-{event_id}",
            )
        )["status"]
        == "APPLIED"
    )
    assert (
        _result(
            bridge.apply_operation(
                settings,
                {
                    **_pick_operation("create_shipment", order=order, lot=lot, quantity=quantity),
                    "shipment_id": DistributorERP._shipment_id(settings, order, event_id),
                },
                event_id,
            )
        )["status"]
        == "APPLIED"
    )


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


def test_component_batches_hold_failed_sample_then_release_whole_lot_and_trace_dispatch() -> None:
    client = ComponentNativeERP()
    bridge = DistributorERP(client)
    settings = component_config()

    for lot, cartons, quantity, pack in (("LOT-A", 2, 20, 10), ("LOT-B", 2, 18, 10)):
        assert (
            _result(
                bridge.apply_operation(
                    settings,
                    _component_arrival(lot, cartons, quantity, pack),
                    f"arrival-{lot.lower()}",
                )
            )["status"]
            == "APPLIED"
        )
    held = _result(bridge.read_case(settings))
    assert held["quantities"] == {
        "ordered": 40.0,
        "received": 38.0,
        "usable": 0.0,
        "held": 38.0,
        "missing": 2.0,
        "allocated": 0.0,
        "dispatched": 0.0,
        "delivery_confirmed": 0.0,
        "uom": "Nos",
        "cartons": 4.0,
    }

    whole_a = _inspection(
        "LOT-A", result="PASS", scope="WHOLE_LOT", measured=10.0, sample_quantity=20
    )
    assert _result(bridge.apply_operation(settings, whole_a, "qi-a-release"))["status"] == "APPLIED"
    assert (
        _result(bridge.apply_operation(settings, _release("LOT-A"), "qi-a-release"))["status"]
        == "APPLIED"
    )

    failed_b = _inspection("LOT-B", result="FAIL", scope="SAMPLE", measured=10.4, sample_quantity=1)
    assert _result(bridge.apply_operation(settings, failed_b, "qi-b-sample"))["status"] == "APPLIED"
    after_failure = _result(bridge.read_case(settings))
    lot_b = next(row for row in after_failure["lots"] if row["lot"] == "LOT-B")
    assert lot_b["received"] == lot_b["held"] == 18.0
    assert lot_b["usable"] == 0.0 and lot_b["status"] == "HELD"
    failed_qi = next(
        qi
        for qi in client.documents["Quality Inspection"].values()
        if qi["batch_no"] == "M20-DIST-COMP-BATCH-B"
    )
    assert failed_qi["status"] == "Rejected"
    failed_transfer = client.documents["Stock Entry"][failed_qi["reference_name"]]
    assert failed_transfer["docstatus"] == 0
    assert failed_transfer["naming_series"] == "MAT-STE-.YYYY.-"
    assert failed_qi["naming_series"] == "MAT-QA-.YYYY.-"

    whole_b = _inspection(
        "LOT-B", result="PASS", scope="WHOLE_LOT", measured=10.0, sample_quantity=18
    )
    assert _result(bridge.apply_operation(settings, whole_b, "qi-b-release"))["status"] == "APPLIED"
    assert (
        _result(bridge.apply_operation(settings, _release("LOT-B"), "qi-b-release"))["status"]
        == "APPLIED"
    )
    assert (
        _result(
            bridge.apply_operation(
                settings, _component_arrival("LOT-C", 1, 2, 2), "arrival-lot-c-replacement"
            )
        )["status"]
        == "APPLIED"
    )
    whole_c = _inspection(
        "LOT-C", result="PASS", scope="WHOLE_LOT", measured=10.0, sample_quantity=2
    )
    assert _result(bridge.apply_operation(settings, whole_c, "qi-c-release"))["status"] == "APPLIED"
    assert (
        _result(bridge.apply_operation(settings, _release("LOT-C"), "qi-c-release"))["status"]
        == "APPLIED"
    )

    released = _result(bridge.read_case(settings))
    assert released["quantities"]["received"] == released["quantities"]["usable"] == 40.0
    assert released["quantities"]["held"] == released["quantities"]["missing"] == 0.0
    _run_component_tranche(
        bridge,
        settings,
        order=COMPONENT_ORDER_25,
        lot="LOT-A",
        quantity=20,
        priority=1,
        event_id="picked-component-a-20",
    )
    _run_component_tranche(
        bridge,
        settings,
        order=COMPONENT_ORDER_25,
        lot="LOT-B",
        quantity=5,
        priority=1,
        event_id="picked-component-b-05",
    )
    _run_component_tranche(
        bridge,
        settings,
        order=COMPONENT_ORDER_15,
        lot="LOT-B",
        quantity=13,
        priority=2,
        event_id="picked-component-b-13",
    )
    _run_component_tranche(
        bridge,
        settings,
        order=COMPONENT_ORDER_15,
        lot="LOT-C",
        quantity=2,
        priority=2,
        event_id="picked-component-c-02",
    )
    final = _result(bridge.read_case(settings))
    assert final["quantities"]["dispatched"] == 40.0
    assert final["quantities"]["usable"] == final["quantities"]["held"] == 0.0
    assert len(client.documents["Pick List"]) == len(client.documents["Delivery Note"]) == 4
    assert all(
        row["items"][0]["batch_no"].startswith("M20-DIST-COMP-BATCH-")
        and row["items"][0]["use_serial_batch_fields"] == 1
        for row in client.documents["Delivery Note"].values()
    )


def test_contract_source_readback_uses_promise_date_and_conserves_native_dispatch() -> None:
    client = ComponentNativeERP()
    bridge = DistributorERP(client)
    settings = contract_component_config()

    for lot, cartons, quantity, pack in (("LOT-A", 2, 20, 10), ("LOT-B", 2, 18, 10)):
        assert (
            _result(
                bridge.apply_operation(
                    settings,
                    _component_arrival(lot, cartons, quantity, pack),
                    f"arrival-contract-{lot.lower()}",
                )
            )["status"]
            == "APPLIED"
        )
    for lot, quantity in (("LOT-A", 20),):
        inspection = _inspection(
            lot, result="PASS", scope="WHOLE_LOT", measured=10, sample_quantity=quantity
        )
        assert (
            _result(bridge.apply_operation(settings, inspection, f"qi-contract-{lot}"))["status"]
            == "APPLIED"
        )
        assert (
            _result(bridge.apply_operation(settings, _release(lot), f"qi-contract-{lot}"))["status"]
            == "APPLIED"
        )

    def allocations() -> dict[str, Mapping[str, object]]:
        return {
            str(row["customer_order"]): row
            for row in cast(list[Mapping[str, object]], bridge.read_case(settings)["allocations"])
        }

    first = allocations()
    assert (first[COMPONENT_ORDER_25]["allocated"], first[COMPONENT_ORDER_15]["allocated"]) == (
        20.0,
        0.0,
    )

    inspection = _inspection(
        "LOT-B", result="PASS", scope="WHOLE_LOT", measured=10, sample_quantity=18
    )
    assert (
        _result(bridge.apply_operation(settings, inspection, "qi-contract-lot-b"))["status"]
        == "APPLIED"
    )
    assert (
        _result(bridge.apply_operation(settings, _release("LOT-B"), "qi-contract-lot-b"))["status"]
        == "APPLIED"
    )
    second = allocations()
    assert (second[COMPONENT_ORDER_25]["allocated"], second[COMPONENT_ORDER_15]["allocated"]) == (
        25.0,
        13.0,
    )

    assert (
        _result(
            bridge.apply_operation(
                settings,
                _component_arrival("LOT-C", 1, 2, 2),
                "arrival-contract-lot-c",
            )
        )["status"]
        == "APPLIED"
    )
    inspection = _inspection(
        "LOT-C", result="PASS", scope="WHOLE_LOT", measured=10, sample_quantity=2
    )
    assert (
        _result(bridge.apply_operation(settings, inspection, "qi-contract-lot-c"))["status"]
        == "APPLIED"
    )
    assert (
        _result(bridge.apply_operation(settings, _release("LOT-C"), "qi-contract-lot-c"))["status"]
        == "APPLIED"
    )
    third = allocations()
    assert (third[COMPONENT_ORDER_25]["allocated"], third[COMPONENT_ORDER_15]["allocated"]) == (
        25.0,
        15.0,
    )

    for order, lot, quantity, priority, event_id in (
        (COMPONENT_ORDER_25, "LOT-A", 20, 2, "contract-picked-a-20"),
        (COMPONENT_ORDER_25, "LOT-B", 5, 2, "contract-picked-b-05"),
        (COMPONENT_ORDER_15, "LOT-B", 13, 1, "contract-picked-b-13"),
        (COMPONENT_ORDER_15, "LOT-C", 2, 1, "contract-picked-c-02"),
    ):
        _run_component_tranche(
            bridge,
            settings,
            order=order,
            lot=lot,
            quantity=quantity,
            priority=priority,
            event_id=event_id,
        )

    final = _result(bridge.read_case(settings))
    rows = {
        str(row["customer_order"]): row
        for row in cast(list[Mapping[str, object]], final["allocations"])
    }
    assert final["quantities"]["dispatched"] == 40.0
    assert (
        rows[COMPONENT_ORDER_25]["allocated"],
        rows[COMPONENT_ORDER_25]["dispatched"],
        rows[COMPONENT_ORDER_25]["backordered"],
    ) == (0.0, 25.0, 0.0)
    assert (
        rows[COMPONENT_ORDER_15]["allocated"],
        rows[COMPONENT_ORDER_15]["dispatched"],
        rows[COMPONENT_ORDER_15]["backordered"],
    ) == (0.0, 15.0, 0.0)


def test_quality_inspection_uses_authenticated_erp_identity() -> None:
    client = ComponentNativeERP()
    client.logged_user = "component.inspector@example.test"
    bridge = DistributorERP(client)
    settings = component_config()

    for invalid in (
        {"doctype": "Quality Inspection"},
        {"doctype": "Quality Inspection", "inspected_by": "user"},
    ):
        with pytest.raises(AssertionError, match="authenticated ERP user"):
            client._create("Quality Inspection", invalid)

    arrival = _result(
        bridge.apply_operation(settings, _component_arrival("LOT-A", 2, 20, 10), "arrival-a")
    )
    assert arrival["status"] == "APPLIED"
    inspection = _inspection(
        "LOT-A", result="PASS", scope="WHOLE_LOT", measured=10.0, sample_quantity=20
    )

    result = _result(bridge.apply_operation(settings, inspection, "qi-a"))

    assert result["status"] == "APPLIED"
    assert any(
        path == "/api/method/frappe.auth.get_logged_user" and method == "GET"
        for path, method, _payload in client.calls
    )
    quality_payloads = [
        payload
        for path, method, payload in client.calls
        if method == "POST" and path.endswith("/Quality%20Inspection")
    ]
    assert len(quality_payloads) == 1
    assert isinstance(quality_payloads[0], Mapping)
    assert quality_payloads[0]["inspected_by"] == client.logged_user


def test_receive_reconciliation_reads_exact_submitted_component_receipt_without_writing() -> None:
    client = ComponentNativeERP()
    bridge = DistributorERP(client)
    settings = component_config()
    arrival = _component_arrival("LOT-A", 2, 20, 10)
    initial = _result(bridge.apply_operation(settings, arrival, "arrival-a"))
    assert initial["status"] == "APPLIED"
    receipt = initial["documents"][0]
    receipt_name = cast(str, receipt["name"])
    before_reconciliation = len(client.calls)

    reconciled = _result(
        bridge.reconcile_receive_arrival(settings, {**arrival, "type": "arrival"}, "arrival-a")
    )

    assert reconciled["status"] == "APPLIED"
    assert reconciled["documents"] == [receipt]
    snapshot = cast(dict[str, object], reconciled["snapshot"])
    assert snapshot["source_status"] == "CURRENT"
    quantities = cast(Mapping[str, object], snapshot["quantities"])
    assert quantities["received"] == quantities["held"] == 20.0
    assert all(method == "GET" for _path, method, _payload in client.calls[before_reconciliation:])

    client.documents["Purchase Receipt"][receipt_name]["remarks"] = "different retained event"
    mismatched = _result(
        bridge.reconcile_receive_arrival(settings, {**arrival, "type": "arrival"}, "arrival-a")
    )
    assert mismatched["status"] == "BLOCKED"
    assert mismatched["error_code"] == "RECEIPT_RECONCILIATION_EVENT_MISMATCH"
    assert all(method == "GET" for _path, method, _payload in client.calls[before_reconciliation:])


def test_quality_release_requires_persisted_whole_lot_sample_coverage() -> None:
    client = ComponentNativeERP()
    bridge = DistributorERP(client)
    settings = component_config()
    assert (
        _result(
            bridge.apply_operation(settings, _component_arrival("LOT-A", 2, 20, 10), "arrival-a")
        )["status"]
        == "APPLIED"
    )
    sampled = _inspection("LOT-A", result="PASS", scope="SAMPLE", measured=10.0, sample_quantity=1)
    assert (
        _result(bridge.apply_operation(settings, sampled, "qi-a-sample-pass"))["status"]
        == "APPLIED"
    )

    release = _result(bridge.apply_operation(settings, _release("LOT-A"), "qi-a-sample-pass"))

    assert release["status"] == "BLOCKED"
    assert release["error_code"] == "WHOLE_LOT_EVIDENCE_INCOMPLETE"
    transfer = next(iter(client.documents["Stock Entry"].values()))
    assert transfer["docstatus"] == 0


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


def test_explicit_picked_event_submits_existing_matching_delivery_draft_once() -> None:
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
    pick = next(iter(client.documents["Pick List"].values()))
    draft = client._create(
        "Delivery Note",
        {
            "doctype": "Delivery Note",
            "company": COMPANY,
            "customer": "M20 Customer 24",
            "grand_total": 1000,
            "items": [
                {
                    "item_code": ITEM,
                    "qty": 20,
                    "warehouse": WAREHOUSE,
                    "against_sales_order": ORDER_24,
                    "against_pick_list": pick["name"],
                }
            ],
        },
    )["data"]

    result = _result(
        bridge.apply_operation(
            settings,
            _pick_operation(
                "submit_delivery_note", order=ORDER_24, lot="R4-ARRIVAL-20", quantity=20
            ),
            "picked-r4-20-explicit-reissue",
        )
    )

    assert result["status"] == "APPLIED"
    assert result["documents"][0]["name"] == draft["name"]
    assert client.documents["Delivery Note"][draft["name"]]["docstatus"] == 1
    assert not [
        path for path, _method, _payload in client.calls if path.endswith("create_delivery_note")
    ]
    delivery_submits = [
        payload
        for path, method, payload in client.calls
        if path.endswith("frappe.client.submit")
        and method == "POST"
        and isinstance(payload, Mapping)
        and isinstance(payload.get("doc"), Mapping)
        and payload["doc"].get("doctype") == "Delivery Note"
    ]
    assert len(delivery_submits) == 1
    before_replay = len(client.calls)
    replay = _result(
        bridge.apply_operation(
            settings,
            _pick_operation(
                "submit_delivery_note", order=ORDER_24, lot="R4-ARRIVAL-20", quantity=20
            ),
            "picked-r4-20-explicit-replay",
        )
    )
    assert replay["status"] == "ALREADY_APPLIED"
    assert all(method == "GET" for _path, method, _payload in client.calls[before_replay:])


def test_existing_delivery_draft_requires_submitted_pick_and_exact_scope() -> None:
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
    pick = next(iter(client.documents["Pick List"].values()))
    draft = client._create(
        "Delivery Note",
        {
            "doctype": "Delivery Note",
            "company": COMPANY,
            "customer": "M20 Customer 24",
            "grand_total": 1000,
            "items": [
                {
                    "item_code": ITEM,
                    "qty": 20,
                    "warehouse": WAREHOUSE,
                    "against_sales_order": ORDER_24,
                    "against_pick_list": pick["name"],
                }
            ],
        },
    )["data"]
    before_unsubmitted = len(client.calls)

    unsubmitted = _result(
        bridge.apply_operation(
            settings,
            _pick_operation(
                "submit_delivery_note", order=ORDER_24, lot="R4-ARRIVAL-20", quantity=20
            ),
            "picked-r4-20-unsubmitted",
        )
    )
    assert unsubmitted["status"] == "BLOCKED"
    assert unsubmitted["error_code"] == "SUBMITTED_PICK_REQUIRED"
    assert all(method == "GET" for _path, method, _payload in client.calls[before_unsubmitted:])

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
    client.documents["Delivery Note"][draft["name"]]["items"][0]["warehouse"] = "Stores - M20"
    before_mismatch = len(client.calls)

    mismatched = _result(
        bridge.apply_operation(
            settings,
            _pick_operation(
                "submit_delivery_note", order=ORDER_24, lot="R4-ARRIVAL-20", quantity=20
            ),
            "picked-r4-20-mismatched",
        )
    )
    assert mismatched["status"] == "BLOCKED"
    assert mismatched["error_code"] == "DELIVERY_NOTE_SCOPE_MISMATCH"
    assert all(method == "GET" for _path, method, _payload in client.calls[before_mismatch:])


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


def test_component_provision_plan_declares_batched_quarantine_and_replacement_scope() -> None:
    from scripts.provision_distributor_operations import _component_plan

    plan = _component_plan(
        supplier=SUPPLIER,
        date="2026-09-10",
        purchase_order="PUR-ORD-COMPONENT-40",
        purchase_order_item="COMPONENT-PO-ITEM",
    )
    assert plan["case_id"] == "M20-DIST-COMPONENT-40"
    assert plan["item_code"] == COMPONENT_ITEM
    assert plan["uom"] == plan["stock_uom"] == "Nos"
    assert plan["cartons"] == 5 and plan["expected_pack_quantity"] == 10
    assert plan["policy"] == {
        "inspection_required": True,
        "reservation_supported": False,
        "inspection_criteria": {"diameter_mm": {"minimum": 9.9, "maximum": 10.1}},
    }
    plans = cast(list[Mapping[str, object]], plan["receipt_plans"])
    assert [
        (row["lot"], row["quantity"], row["cartons"], row["expected_pack_quantity"])
        for row in plans
    ] == [("LOT-A", 20, 2, 10), ("LOT-B", 18, 2, 10), ("LOT-C", 2, 1, 2)]
    lots = cast(list[Mapping[str, object]], plan["lots"])
    assert lots[2]["replacement_for_lot"] == "LOT-B"
    assert plan["purchase_order"] == "PUR-ORD-COMPONENT-40"
    assert plan["purchase_order_item"] == "COMPONENT-PO-ITEM"


def test_component_dry_provision_cli_writes_only_the_explicit_template(tmp_path: Path) -> None:
    from scripts import provision_distributor_operations as provision

    output = tmp_path / "component-plan.json"
    original_argv = sys.argv
    try:
        sys.argv = [
            "provision_distributor_operations.py",
            "--mode",
            "dry",
            "--scenario",
            "component-quality",
            "--date",
            "2026-09-10",
            "--output",
            str(output),
        ]
        assert provision.main() == 0
    finally:
        sys.argv = original_argv
    value = json.loads(output.read_text(encoding="utf-8"))
    assert value["mode"] == "dry" and value["write_authorized"] is False
    assert value["scenario"] == "component-quality"
    assert value["config_template"]["purchase_order"].startswith("REQUIRES_PROVISION_")
    assert value["config_template"]["receipt_plans"][2]["expected_pack_quantity"] == 2
