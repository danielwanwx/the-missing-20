"""Focused, offline coverage for the event-driven distributor demo boundary."""

from __future__ import annotations

import json
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from test_distributor_erp import NativeERP
from test_distributor_erp import r4_config as native_r4_config

import scripts.decision_workspace_server as workspace_server
from scripts.decision_workspace_server import DecisionWorkspaceHandler
from the_missing_20.adapters.distributor_allocation import compile_plan
from the_missing_20.adapters.distributor_erp import DistributorERP as NativeDistributorERP
from the_missing_20.adapters.distributor_operations import (
    DistributorEventConflict,
    DistributorOperations,
)
from the_missing_20.adapters.strands_models import (
    OPUS46_MODEL_ID,
    BedrockNovaProFactory,
    BedrockOpus46Factory,
)
from the_missing_20.config import Settings
from the_missing_20.ports.agent_model import AgentProvider


class _Bridge:
    """Canonical local bridge double; it never calls a provider."""

    def __init__(self, config: dict[str, object]) -> None:
        self.config = config
        self.reads = 0
        self.calls: list[tuple[str, str, dict[str, object]]] = []
        self.reconcile_calls: list[tuple[str, dict[str, object]]] = []
        self.statuses: dict[str, str] = {}
        self.state_provider: Any = None
        self.source_override: dict[str, object] | None = None

    def read_case(self, config: Mapping[str, object]) -> Mapping[str, object]:
        assert config == self.config
        self.reads += 1
        if self.source_override is not None:
            return deepcopy(self.source_override)
        state = self.state_provider() if self.state_provider is not None else None
        if isinstance(state, dict):
            quantities = deepcopy(cast(dict[str, object], state["quantities"]))
            quantities["delivery_confirmed"] = 0
            return {
                "case_id": config["case_id"],
                "case_label": config["case_label"],
                "synthetic_input": config["synthetic_input"],
                "source_status": "CURRENT",
                "quantities": quantities,
                "lots": deepcopy(state["lots"]),
                "allocations": deepcopy(state["allocations"]),
                "documents": deepcopy(state["documents"]),
            }
        raw_lots = config["lots"]
        assert isinstance(raw_lots, list)
        planned = sum(
            int(expected_quantity)
            for row in raw_lots
            if isinstance(row, Mapping)
            and isinstance(expected_quantity := row.get("expected_quantity"), int | float)
        )
        return {
            "case_id": config["case_id"],
            "case_label": config["case_label"],
            "synthetic_input": config["synthetic_input"],
            "source_status": "CURRENT",
            "quantities": {
                "ordered": planned,
                "received": 0,
                "usable": 0,
                "held": 0,
                "missing": planned,
                "allocated": 0,
                "dispatched": 0,
                "delivery_confirmed": 0,
                "cartons": 0,
                "uom": config["uom"],
            },
            "lots": [
                {
                    "lot": row["lot"],
                    "expected_quantity": row["expected_quantity"],
                    "cartons": 0,
                    "received": 0,
                    "usable": 0,
                    "held": 0,
                    "status": "AWAITING_ARRIVAL",
                }
                for row in cast(list[dict[str, object]], config["lots"])
            ],
            "allocations": [
                {
                    "customer_order": row["customer_order"],
                    "requested_quantity": row["requested_quantity"],
                    "priority": row["priority"],
                    "allocated": 0,
                    "backordered": row["requested_quantity"],
                    "dispatched": 0,
                    "reservation": "LOCAL_PLAN",
                }
                for row in cast(list[dict[str, object]], config["allocations"])
            ],
            "documents": [],
        }

    def apply_operation(
        self, config: Mapping[str, object], operation: Mapping[str, object], event_id: str
    ) -> Mapping[str, object]:
        assert config == self.config
        kind = operation["kind"]
        assert isinstance(kind, str)
        self.calls.append((kind, event_id, deepcopy(dict(operation))))
        status = self.statuses.get(kind, "APPLIED")
        documents = (
            [{"kind": "Shipment", "name": f"SHIP-{event_id}", "status": "Submitted"}]
            if kind == "create_shipment" and status in {"APPLIED", "ALREADY_APPLIED"}
            else [{"kind": "Pick List", "name": f"PICK-{event_id}", "status": "Submitted"}]
            if kind == "submit_pick" and status in {"APPLIED", "ALREADY_APPLIED"}
            else [
                {
                    "kind": kind,
                    "name": f"{kind.upper()}-{event_id}",
                    "status": "Submitted",
                }
            ]
            if status in {"APPLIED", "ALREADY_APPLIED"}
            else []
        )
        return {
            "operation": kind,
            "event_id": event_id,
            "status": status,
            "documents": documents,
            "error_code": "ERP_UNAVAILABLE" if status == "UNKNOWN_OUTCOME" else None,
        }

    def reconcile_receive_arrival(
        self, config: Mapping[str, object], event: Mapping[str, object], event_id: str
    ) -> Mapping[str, object]:
        assert config == self.config
        self.reconcile_calls.append((event_id, deepcopy(dict(event))))
        source = self.read_case(config)
        return {
            "operation": "receive_arrival",
            "event_id": event_id,
            "status": "APPLIED",
            "documents": [
                {
                    "kind": "Purchase Receipt",
                    "name": "PR-CONFIRMED-LOT-A",
                    "status": "Submitted",
                }
            ],
            "snapshot": source,
        }


def _component_config() -> dict[str, object]:
    return {
        "case_id": "M20-DIST-COMPONENT-01",
        "case_label": "Component shortage and quality",
        "synthetic_input": True,
        "company": "M20 Demo Company",
        "item_code": "M20-COMPONENT-NOS",
        "uom": "Nos",
        "cartons": 5,
        "expected_pack_quantity": 10,
        "purchase_order": "PO-COMP-1",
        "accepted_warehouse": "Stores-M20",
        "quarantine_warehouse": "Quality Hold-M20",
        "lots": [
            {
                "lot": "LOT-A",
                "expected_quantity": 20,
                "cartons": 2,
                "expected_pack_quantity": 10,
            },
            {
                "lot": "LOT-B",
                "expected_quantity": 18,
                "cartons": 2,
                "expected_pack_quantity": 10,
            },
            {
                "lot": "LOT-C",
                "expected_quantity": 2,
                "cartons": 1,
                "expected_pack_quantity": 2,
                "replacement_for_lot": "LOT-B",
            },
        ],
        "allocations": [
            {"customer_order": "SO-PRIORITY", "requested_quantity": 25, "priority": 1},
            {"customer_order": "SO-STANDARD", "requested_quantity": 15, "priority": 2},
        ],
        "customer_orders": ["SO-PRIORITY", "SO-STANDARD"],
        "policy": {
            "inspection_required": True,
            "reservation_supported": False,
            "inspection_criteria": {"diameter_mm": {"minimum": 9.9, "maximum": 10.1}},
        },
    }


def _r4_config() -> dict[str, object]:
    return {
        "case_id": "M20-DIST-R4-FOLLOW-ON",
        "case_label": "R4 remaining 39 Box",
        "synthetic_input": True,
        "company": "M20 Demo Company",
        "item_code": "M20-DEMO-CARTON",
        "uom": "Box",
        "cartons": 39,
        "expected_pack_quantity": 1,
        "purchase_order": "PUR-ORD-2026-00016",
        "accepted_warehouse": "Stores-M20-Follow-On",
        "quarantine_warehouse": "Quality Hold-M20-Follow-On",
        "lots": [
            {"lot": "R4-ARRIVAL-20", "expected_quantity": 20},
            {"lot": "R4-ARRIVAL-19", "expected_quantity": 19},
        ],
        "allocations": [
            {"customer_order": "SO-R4-PRIORITY", "requested_quantity": 24, "priority": 1},
            {"customer_order": "SO-R4-STANDARD", "requested_quantity": 15, "priority": 2},
        ],
        "customer_orders": ["SO-R4-PRIORITY", "SO-R4-STANDARD"],
        "policy": {"inspection_required": False, "reservation_supported": False},
        "shipping": {
            "shipments": {
                "SO-R4-PRIORITY": {
                    "delivery_address": "ADDR-M20-CUSTOMER-24",
                    "shipment_id_prefix": "M20-DIST-R4-SHIP-24",
                },
                "SO-R4-STANDARD": {
                    "delivery_address": "ADDR-M20-CUSTOMER-15",
                    "shipment_id_prefix": "M20-DIST-R4-SHIP-15",
                },
            }
        },
    }


def _contract_config() -> dict[str, object]:
    config = _r4_config()
    config["allocation_policy"] = {"version": "v1"}
    config["allocations"] = [
        {
            "customer_order": "SO-R4-PRIORITY",
            "requested_quantity": 24,
            "priority": 1,
            "promised_delivery_at": "2026-09-12T09:00:00+00:00",
            "customer_priority": 2,
            "partial_dispatch": True,
            "minimum_dispatch_quantity": 10,
            "allow_final_remainder": True,
        },
        {
            "customer_order": "SO-R4-STANDARD",
            "requested_quantity": 15,
            "priority": 2,
            "promised_delivery_at": "2026-09-11T09:00:00+00:00",
            "customer_priority": 9,
            "partial_dispatch": True,
            "minimum_dispatch_quantity": 10,
            "allow_final_remainder": False,
        },
    ]
    config["pick_tranches"] = [
        {"customer_order": "SO-R4-STANDARD", "lot": "R4-ARRIVAL-20", "quantity": 15},
        {"customer_order": "SO-R4-PRIORITY", "lot": "R4-ARRIVAL-19", "quantity": 24},
    ]
    return config


def _service(
    tmp_path: Path, config: dict[str, object] | None = None
) -> tuple[DistributorOperations, _Bridge]:
    configured = config or _component_config()
    bridge = _Bridge(configured)
    service = DistributorOperations(tmp_path / "distributor-operations.sqlite3", configured, bridge)
    bridge.state_provider = service._latest_state
    return service, bridge


def _event(event_id: str, event_type: str, **fields: object) -> dict[str, object]:
    return {
        "event_id": event_id,
        "type": event_type,
        "occurred_at": "2026-09-10T09:00:00+00:00",
        "evidence_ref": f"synthetic:{event_id}",
        "synthetic": True,
        **fields,
    }


def _arrival(
    event_id: str,
    *,
    lot: str,
    cartons: int,
    observed: int,
    pack: int = 10,
    item_code: str = "M20-COMPONENT-NOS",
) -> dict[str, object]:
    return _event(
        event_id,
        "arrival",
        cartons=cartons,
        expected_pack_quantity=pack,
        observed_stock_quantity=observed,
        item_code=item_code,
        lot=lot,
    )


def _r4_arrival(event_id: str, lot: str, cartons: int) -> dict[str, object]:
    return _event(
        event_id,
        "arrival",
        cartons=cartons,
        expected_pack_quantity=1,
        observed_stock_quantity=cartons,
        item_code="M20-DEMO-CARTON",
        lot=lot,
    )


def _component_source_after_confirmed_arrival(config: Mapping[str, object]) -> dict[str, object]:
    lots = cast(list[Mapping[str, object]], config["lots"])
    allocations = cast(list[Mapping[str, object]], config["allocations"])
    return {
        "case_id": config["case_id"],
        "case_label": config["case_label"],
        "synthetic_input": config["synthetic_input"],
        "source_status": "CURRENT",
        "quantities": {
            "ordered": 40,
            "received": 20,
            "usable": 0,
            "held": 20,
            "missing": 20,
            "allocated": 0,
            "dispatched": 0,
            "delivery_confirmed": 0,
            "cartons": 2,
            "uom": config["uom"],
        },
        "lots": [
            {
                "lot": row["lot"],
                "expected_quantity": row["expected_quantity"],
                "cartons": 2 if row["lot"] == "LOT-A" else 0,
                "received": 20 if row["lot"] == "LOT-A" else 0,
                "usable": 0,
                "held": 20 if row["lot"] == "LOT-A" else 0,
                "status": "HELD" if row["lot"] == "LOT-A" else "AWAITING_ARRIVAL",
            }
            for row in lots
        ],
        "allocations": [
            {
                "customer_order": row["customer_order"],
                "requested_quantity": row["requested_quantity"],
                "priority": row["priority"],
                "allocated": 0,
                "backordered": row["requested_quantity"],
                "dispatched": 0,
                "reservation": "LOCAL_PLAN",
            }
            for row in allocations
        ],
        "documents": [
            {
                "kind": "Purchase Receipt",
                "name": "PR-CONFIRMED-LOT-A",
                "status": "Submitted",
            }
        ],
    }


def _codes(projection: dict[str, object]) -> set[str]:
    alerts = projection["alerts"]
    assert isinstance(alerts, list)
    return {
        str(alert["code"])
        for alert in alerts
        if isinstance(alert, dict) and alert.get("status") == "OPEN"
    }


def test_projection_keeps_optional_financial_facts_local_to_current_erp_source(
    tmp_path: Path,
) -> None:
    config = _r4_config()
    service, bridge = _service(tmp_path, config)
    missing = service.projection()
    assert missing["available"] is True
    assert missing["financials"] == {
        "status": "UNAVAILABLE",
        "reason": "FINANCIAL_NOT_PROVIDED",
    }

    source = cast(dict[str, object], bridge.read_case(config))
    orders = cast(list[Mapping[str, object]], config["allocations"])
    source["financials"] = {
        "status": "CURRENT",
        "purchase_order": {
            "document": {
                "kind": "Purchase Order",
                "name": config["purchase_order"],
                "status": "Submitted",
            },
            "supplier": "M20 Supplier",
            "currency": "USD",
            "line": {"quantity": 40, "received_quantity": 0, "rate": 50, "net_amount": 2000},
        },
        "sales_orders": [
            {
                "document": {
                    "kind": "Sales Order",
                    "name": row["customer_order"],
                    "status": "Submitted",
                },
                "customer": f"Customer {row['customer_order']}",
                "currency": "USD",
                "line": {
                    "quantity": row["requested_quantity"],
                    "rate": 50,
                    "net_amount": row["requested_quantity"] * 50,
                },
                "value_scope": "ORDER_LINE_NET_AMOUNT_NOT_INVOICE_OR_REVENUE",
            }
            for row in orders
        ],
        "purchase_invoices": {"status": "MISSING", "records": []},
        "sales_invoices": [
            {"customer_order": row["customer_order"], "status": "MISSING", "records": []}
            for row in orders
        ],
    }
    bridge.source_override = source

    current = service.projection()
    assert current["available"] is True
    financials = cast(Mapping[str, object], current["financials"])
    assert financials["status"] == "CURRENT"
    assert cast(Mapping[str, object], financials["purchase_order"])["line"] == {
        "quantity": 40,
        "rate": 50,
        "net_amount": 2000,
        "received_quantity": 0,
    }
    assert cast(Mapping[str, object], financials["purchase_invoices"])["status"] == "MISSING"

    source["financials"] = {"status": "CURRENT", "purchase_order": "malformed"}
    malformed = service.projection()
    assert malformed["available"] is True
    assert malformed["financials"] == {
        "status": "UNAVAILABLE",
        "reason": "FINANCIAL_SOURCE_MALFORMED",
    }


def test_r4_remaining_arrivals_allocate_then_pick_pickup_and_delivery(tmp_path: Path) -> None:
    service, bridge = _service(tmp_path, _r4_config())
    first = service.record_event(_r4_arrival("arrival-r4-20", "R4-ARRIVAL-20", 20))
    assert first["quantities"] == {
        "ordered": 39,
        "received": 20,
        "usable": 20,
        "held": 0,
        "missing": 19,
        "allocated": 20,
        "dispatched": 0,
        "delivery_confirmed": 0,
        "uom": "Box",
        "cartons": 20,
        "initial_expected_cartons": 39,
        "observed_outer_packages": 20,
    }
    final = service.record_event(_r4_arrival("arrival-r4-19", "R4-ARRIVAL-19", 19))
    assert final["quantities"]["received"] == final["quantities"]["usable"] == 39
    assert final["quantities"]["allocated"] == 39
    allocations = cast(list[dict[str, object]], final["allocations"])
    assert [
        (row["customer_order"], row["allocated"], row["backordered"]) for row in allocations
    ] == [
        ("SO-R4-PRIORITY", 24, 0),
        ("SO-R4-STANDARD", 15, 0),
    ]
    picked_twenty = service.record_event(
        _event(
            "picked-r4-20",
            "picked",
            customer_order="SO-R4-PRIORITY",
            lot="R4-ARRIVAL-20",
            quantity=20,
            pick_evidence_ref="synthetic:pick-r4-20",
        )
    )
    picked_four = service.record_event(
        _event(
            "picked-r4-4",
            "picked",
            customer_order="SO-R4-PRIORITY",
            lot="R4-ARRIVAL-19",
            quantity=4,
            pick_evidence_ref="synthetic:pick-r4-4",
        )
    )
    picked_fifteen = service.record_event(
        _event(
            "picked-r4-15",
            "picked",
            customer_order="SO-R4-STANDARD",
            lot="R4-ARRIVAL-19",
            quantity=15,
            pick_evidence_ref="synthetic:pick-r4-15",
        )
    )
    assert picked_fifteen["quantities"]["dispatched"] == 39
    assert picked_fifteen["quantities"]["delivery_confirmed"] == 0
    shipments = [
        document["name"]
        for document in cast(list[dict[str, object]], picked_fifteen["documents"])
        if document["kind"] == "Shipment"
    ]
    assert len(shipments) == 3
    shipments_by_event = {
        event_id: operation["shipment_id"]
        for kind, event_id, operation in bridge.calls
        if kind == "create_shipment"
    }
    assert set(shipments_by_event) == {"picked-r4-20", "picked-r4-4", "picked-r4-15"}
    shipment_id_20 = shipments_by_event["picked-r4-20"]
    shipment_id_4 = shipments_by_event["picked-r4-4"]
    shipment_id_15 = shipments_by_event["picked-r4-15"]
    assert isinstance(shipment_id_20, str) and shipment_id_20.startswith("M20-DIST-R4-SHIP-24-")
    assert isinstance(shipment_id_4, str) and shipment_id_4.startswith("M20-DIST-R4-SHIP-24-")
    assert isinstance(shipment_id_15, str) and shipment_id_15.startswith("M20-DIST-R4-SHIP-15-")
    assert len({shipment_id_20, shipment_id_4, shipment_id_15}) == 3
    shipment_20 = "SHIP-picked-r4-20"
    shipment_4 = "SHIP-picked-r4-4"
    shipment_15 = "SHIP-picked-r4-15"
    assert {shipment_20, shipment_4, shipment_15} == set(shipments)
    for event_id, shipment in (
        ("pickup-r4-20", shipment_20),
        ("pickup-r4-4", shipment_4),
        ("pickup-r4-15", shipment_15),
    ):
        service.record_event(_event(event_id, "carrier_pickup", shipment_id=shipment))
    b_delivered = service.record_event(
        _event("delivery-r4-15", "delivery", shipment_id=shipment_15)
    )
    shipment_rows = {
        row["name"]: row for row in cast(list[dict[str, object]], b_delivered["shipments"])
    }
    assert shipment_rows[shipment_15] == {
        "name": shipment_15,
        "customer_order": "SO-R4-STANDARD",
        "lot": "R4-ARRIVAL-19",
        "quantity": 15,
        "picked_up": True,
        "delivered": True,
        "synthetic": True,
    }
    assert shipment_rows[shipment_20]["delivered"] is False
    allocation_rows = {
        row["customer_order"]: row
        for row in cast(list[dict[str, object]], b_delivered["allocations"])
    }
    assert allocation_rows["SO-R4-STANDARD"].get("picked") == 15
    assert allocation_rows["SO-R4-STANDARD"].get("delivery_confirmed") == 15
    assert allocation_rows["SO-R4-STANDARD"].get("status") == "DELIVERY_CONFIRMED"
    assert allocation_rows["SO-R4-PRIORITY"].get("picked") == 24
    assert allocation_rows["SO-R4-PRIORITY"].get("delivery_confirmed") == 0
    assert allocation_rows["SO-R4-PRIORITY"].get("status") == "PICKED"
    event_rows = {
        row["event_id"]: row for row in cast(list[dict[str, object]], b_delivered["events"])
    }
    assert event_rows["arrival-r4-20"]["observed_stock_quantity"] == 20
    assert event_rows["picked-r4-15"].get("customer_order") == "SO-R4-STANDARD"
    assert event_rows["picked-r4-15"].get("quantity") == 15
    assert event_rows["pickup-r4-15"].get("shipment_id") == shipment_15
    assert event_rows["delivery-r4-15"].get("shipment_id") == shipment_15
    packet = workspace_server._distributor_native_packet(b_delivered)
    sources = cast(dict[str, object], cast(dict[str, object], packet["tool_payload"])["sources"])
    erp_facts = cast(dict[str, object], sources["read_erp_evidence"])
    assert cast(list[dict[str, object]], erp_facts["shipments"])[0]["name"]
    retained_events = cast(
        list[dict[str, object]],
        cast(dict[str, object], sources["read_collaboration_evidence"])["retained_physical_events"],
    )
    assert (
        next(row for row in retained_events if row["event_id"] == "picked-r4-15")["customer_order"]
        == "SO-R4-STANDARD"
    )
    service.record_event(_event("delivery-r4-20", "delivery", shipment_id=shipment_20))
    delivered = service.record_event(_event("delivery-r4-4", "delivery", shipment_id=shipment_4))
    assert delivered["quantities"]["delivery_confirmed"] == 39
    assert [kind for kind, _event_id, _operation in bridge.calls] == [
        "receive_arrival",
        "prepare_pick",
        "receive_arrival",
        "prepare_pick",
        "prepare_pick",
        "submit_pick",
        "submit_delivery_note",
        "create_shipment",
        "submit_pick",
        "submit_delivery_note",
        "create_shipment",
        "submit_pick",
        "submit_delivery_note",
        "create_shipment",
    ]
    prepared = [operation for kind, _event_id, operation in bridge.calls if kind == "prepare_pick"]
    assert [(call["customer_order"], call["quantity"], call["priority"]) for call in prepared] == [
        ("SO-R4-PRIORITY", 20, 1),
        ("SO-R4-PRIORITY", 4, 1),
        ("SO-R4-STANDARD", 15, 2),
    ]
    submitted_picks = [
        operation for kind, _event_id, operation in bridge.calls if kind == "submit_pick"
    ]
    assert [
        (call["customer_order"], call["lot"], call["quantity"]) for call in submitted_picks
    ] == [
        ("SO-R4-PRIORITY", "R4-ARRIVAL-20", 20),
        ("SO-R4-PRIORITY", "R4-ARRIVAL-19", 4),
        ("SO-R4-STANDARD", "R4-ARRIVAL-19", 15),
    ]
    assert picked_twenty["quantities"]["dispatched"] == 20
    assert picked_four["quantities"]["dispatched"] == 24


def test_projection_hydrates_legacy_event_briefs_from_retained_payload(tmp_path: Path) -> None:
    service, _bridge = _service(tmp_path, _r4_config())
    service.record_event(_r4_arrival("arrival-r4-20", "R4-ARRIVAL-20", 20))
    service.record_event(
        _event(
            "picked-r4-20",
            "picked",
            customer_order="SO-R4-PRIORITY",
            lot="R4-ARRIVAL-20",
            quantity=20,
            pick_evidence_ref="synthetic:pick-r4-20",
        )
    )
    row = service._db.execute(
        "SELECT state_json FROM distributor_operation_events WHERE event_id='picked-r4-20'"
    ).fetchone()
    assert row is not None and isinstance(row[0], str)
    retained_state = json.loads(row[0])
    assert isinstance(retained_state, dict)
    events = retained_state.get("events")
    assert isinstance(events, list)
    for event in events:
        if not isinstance(event, dict):
            continue
        for field in (
            "cartons",
            "expected_pack_quantity",
            "observed_stock_quantity",
            "item_code",
            "lot",
            "customer_order",
            "quantity",
            "pick_evidence_ref",
            "shipment_id",
        ):
            event.pop(field, None)
    service._db.execute(
        "UPDATE distributor_operation_events SET state_json=? WHERE event_id='picked-r4-20'",
        (json.dumps(retained_state, sort_keys=True, separators=(",", ":")),),
    )

    projection = service.projection()
    events_by_id = {
        event["event_id"]: event for event in cast(list[dict[str, object]], projection["events"])
    }
    assert events_by_id["arrival-r4-20"]["cartons"] == 20
    assert events_by_id["arrival-r4-20"]["observed_stock_quantity"] == 20
    assert events_by_id["picked-r4-20"]["customer_order"] == "SO-R4-PRIORITY"
    assert events_by_id["picked-r4-20"]["lot"] == "R4-ARRIVAL-20"
    assert events_by_id["picked-r4-20"]["quantity"] == 20
    assert events_by_id["picked-r4-20"]["pick_evidence_ref"] == "synthetic:pick-r4-20"


def test_projection_marks_a_partial_order_delivery_without_closing_the_order(
    tmp_path: Path,
) -> None:
    service, _bridge = _service(tmp_path, _r4_config())
    service.record_event(_r4_arrival("arrival-r4-20", "R4-ARRIVAL-20", 20))
    picked = service.record_event(
        _event(
            "picked-r4-20",
            "picked",
            customer_order="SO-R4-PRIORITY",
            lot="R4-ARRIVAL-20",
            quantity=20,
            pick_evidence_ref="synthetic:pick-r4-20",
        )
    )
    shipment = next(
        document["name"]
        for document in cast(list[dict[str, object]], picked["documents"])
        if document["kind"] == "Shipment"
    )
    service.record_event(_event("pickup-r4-20", "carrier_pickup", shipment_id=shipment))
    delivered = service.record_event(_event("delivery-r4-20", "delivery", shipment_id=shipment))

    allocation = next(
        row
        for row in cast(list[dict[str, object]], delivered["allocations"])
        if row["customer_order"] == "SO-R4-PRIORITY"
    )
    assert allocation["requested_quantity"] == 24
    assert allocation["picked"] == allocation["delivery_confirmed"] == 20
    assert allocation["status"] == "PARTIALLY_DELIVERED"


def test_picked_evidence_recovers_a_blocked_prepare_without_replaying_arrival(
    tmp_path: Path,
) -> None:
    service, bridge = _service(tmp_path, _r4_config())
    bridge.statuses["prepare_pick"] = "BLOCKED"

    blocked = service.record_event(_r4_arrival("arrival-r4-20", "R4-ARRIVAL-20", 20))
    assert [kind for kind, _event_id, _operation in bridge.calls] == [
        "receive_arrival",
        "prepare_pick",
    ]
    blocked_prepare = next(
        alert
        for alert in cast(list[dict[str, object]], blocked["alerts"])
        if alert["code"] == "NATIVE_OPERATION_BLOCKED" and alert.get("operation") == "prepare_pick"
    )
    assert blocked_prepare["status"] == "OPEN"

    bridge.statuses["prepare_pick"] = "APPLIED"
    resumed = service.record_event(
        _event(
            "picked-r4-20",
            "picked",
            customer_order="SO-R4-PRIORITY",
            lot="R4-ARRIVAL-20",
            quantity=20,
            pick_evidence_ref="synthetic:pick-r4-20",
        )
    )

    assert resumed["quantities"]["dispatched"] == 20
    assert [kind for kind, _event_id, _operation in bridge.calls] == [
        "receive_arrival",
        "prepare_pick",
        "prepare_pick",
        "submit_pick",
        "submit_delivery_note",
        "create_shipment",
    ]
    assert all(
        alert["status"] == "RESOLVED"
        for alert in cast(list[dict[str, object]], resumed["alerts"])
        if alert["code"] == "NATIVE_OPERATION_BLOCKED" and alert.get("operation") == "prepare_pick"
    )


def test_next_successful_picked_event_completes_only_the_prior_blocked_shipment(
    tmp_path: Path,
) -> None:
    service, bridge = _service(tmp_path, _r4_config())
    service.record_event(_r4_arrival("arrival-r4-20", "R4-ARRIVAL-20", 20))
    bridge.statuses["create_shipment"] = "BLOCKED"
    blocked = service.record_event(
        _event(
            "picked-r4-20",
            "picked",
            customer_order="SO-R4-PRIORITY",
            lot="R4-ARRIVAL-20",
            quantity=20,
            pick_evidence_ref="synthetic:pick-r4-20",
        )
    )
    assert blocked["quantities"]["dispatched"] == 20
    blocked_shipment = next(
        alert
        for alert in cast(list[dict[str, object]], blocked["alerts"])
        if alert["code"] == "NATIVE_OPERATION_BLOCKED"
        and alert.get("operation") == "create_shipment"
    )
    assert blocked_shipment["status"] == "OPEN"

    bridge.statuses["prepare_pick"] = "BLOCKED"
    arrival = service.record_event(_r4_arrival("arrival-r4-19", "R4-ARRIVAL-19", 19))
    assert arrival["quantities"]["received"] == 39
    assert [kind for kind, _event_id, _operation in bridge.calls].count("create_shipment") == 1

    bridge.statuses["prepare_pick"] = "APPLIED"
    bridge.statuses["create_shipment"] = "APPLIED"
    resumed = service.record_event(
        _event(
            "picked-r4-15",
            "picked",
            customer_order="SO-R4-STANDARD",
            lot="R4-ARRIVAL-19",
            quantity=15,
            pick_evidence_ref="synthetic:pick-r4-15",
        )
    )

    kinds = [kind for kind, _event_id, _operation in bridge.calls]
    assert kinds.count("receive_arrival") == 2
    assert kinds.count("submit_pick") == kinds.count("submit_delivery_note") == 2
    assert kinds.count("create_shipment") == 3
    resumed_shipment = next(
        operation
        for event in cast(list[dict[str, object]], resumed["events"])
        if event["event_id"] == "picked-r4-15"
        for operation in cast(list[dict[str, object]], event["operations"])
        if operation["kind"] == "create_shipment"
        and operation.get("resumed_from_event_id") == "picked-r4-20"
    )
    assert resumed_shipment["resumed_from_event_id"] == "picked-r4-20"
    assert all(
        alert["status"] == "RESOLVED"
        for alert in cast(list[dict[str, object]], resumed["alerts"])
        if alert["code"] == "NATIVE_OPERATION_BLOCKED"
        and alert.get("operation") == "create_shipment"
    )
    assert any(
        document["kind"] == "Shipment"
        for document in cast(list[dict[str, object]], resumed["documents"])
    )


def test_r4_core_drives_real_native_bridge_two_arrivals_and_three_exact_tranches(
    tmp_path: Path,
) -> None:
    """Exercise the core's physical evidence sequence through the native document fake."""

    client = NativeERP()
    native = NativeDistributorERP(client)  # type: ignore[arg-type]
    operations: list[dict[str, object]] = []

    class RecordingBridge:
        def read_case(self, config: Mapping[str, object]) -> Mapping[str, object]:
            return native.read_case(config)

        def apply_operation(
            self, config: Mapping[str, object], operation: Mapping[str, object], event_id: str
        ) -> Mapping[str, object]:
            operations.append({**deepcopy(dict(operation)), "event_id": event_id})
            return native.apply_operation(config, operation, event_id)

    service = DistributorOperations(
        tmp_path / "native-r4.sqlite3", native_r4_config(), RecordingBridge()
    )
    service.record_event(_r4_arrival("arrival-r4-20", "R4-ARRIVAL-20", 20))
    after_arrivals = service.record_event(_r4_arrival("arrival-r4-19", "R4-ARRIVAL-19", 19))
    assert after_arrivals["quantities"]["received"] == 39
    current_after_arrivals = service.projection()
    assert current_after_arrivals["parent_purchase_order"] == {
        "name": "PUR-ORD-2026-00016",
        "ordered": 40,
        "received": 40,
        "outside_case_received": 1,
        "uom": "Box",
    }
    packet = workspace_server._distributor_native_packet(current_after_arrivals)
    erp_facts = cast(
        dict[str, object],
        cast(dict[str, object], packet["tool_payload"])["sources"],
    )["read_erp_evidence"]
    assert cast(dict[str, object], erp_facts)["parent_purchase_order"] == {
        "name": "PUR-ORD-2026-00016",
        "ordered": 40,
        "received": 40,
        "outside_case_received": 1,
        "uom": "Box",
    }
    assert cast(dict[str, object], erp_facts)["event_provenance"] == {
        "recorded_events": (
            "Arrival, pickup, and delivery are recorded synthetic test events; they are not "
            "actual sensor, carrier, or customer-receipt proof."
        ),
        "quantity_evidence": (
            "Carton and inner counts establish recorded quantities and any observed "
            "discrepancy; they do not establish its cause or responsible party."
        ),
        "attribution_evidence": (
            "This packet contains no supplier packing verification or transit/custody "
            "investigation establishing attribution for that discrepancy."
        ),
        "inspection_evidence": (
            "Quality Inspection records are declared report measurements and stated coverage; "
            "they are not independent physical tests performed by the agent."
        ),
        "native_inventory_accounting": (
            "Native Purchase Order received quantities, Purchase Receipts, and Stock Ledger "
            "Entries support inventory accounting only; they do not prove carrier pickup or "
            "customer receipt."
        ),
    }
    assert "physical_event_note" not in cast(dict[str, object], erp_facts)
    declared_packet = workspace_server._distributor_native_packet(
        {**current_after_arrivals, "synthetic_input": False}
    )
    declared_facts = cast(
        dict[str, object],
        cast(dict[str, object], declared_packet["tool_payload"])["sources"],
    )["read_erp_evidence"]
    assert cast(dict[str, object], declared_facts)["event_provenance"] == {
        "recorded_events": (
            "Arrival, pickup, and delivery are recorded operational events; this packet does "
            "not assert independent sensor, carrier, or customer-receipt verification."
        ),
        "quantity_evidence": (
            "Carton and inner counts establish recorded quantities and any observed "
            "discrepancy; they do not establish its cause or responsible party."
        ),
        "attribution_evidence": (
            "This packet contains no supplier packing verification or transit/custody "
            "investigation establishing attribution for that discrepancy."
        ),
        "inspection_evidence": (
            "Quality Inspection records are declared report measurements and stated coverage; "
            "they are not independent physical tests performed by the agent."
        ),
        "native_inventory_accounting": (
            "Native Purchase Order received quantities, Purchase Receipts, and Stock Ledger "
            "Entries support inventory accounting only; they do not prove carrier pickup or "
            "customer receipt."
        ),
    }
    assert [
        (operation["customer_order"], operation["quantity"], operation["priority"])
        for operation in operations
        if operation["kind"] == "prepare_pick"
    ] == [
        ("SAL-ORD-M20-24", 20, 1),
        ("SAL-ORD-M20-24", 4, 1),
        ("SAL-ORD-M20-15", 15, 2),
    ]

    for event_id, order, lot, quantity in (
        ("picked-r4-20", "SAL-ORD-M20-24", "R4-ARRIVAL-20", 20),
        ("picked-r4-4", "SAL-ORD-M20-24", "R4-ARRIVAL-19", 4),
        ("picked-r4-15", "SAL-ORD-M20-15", "R4-ARRIVAL-19", 15),
    ):
        projection = service.record_event(
            _event(
                event_id,
                "picked",
                customer_order=order,
                lot=lot,
                quantity=quantity,
                pick_evidence_ref=f"synthetic:{event_id}",
            )
        )
    assert projection["quantities"]["dispatched"] == 39
    assert [
        (operation["customer_order"], operation["lot"], operation["quantity"])
        for operation in operations
        if operation["kind"] == "submit_pick"
    ] == [
        ("SAL-ORD-M20-24", "R4-ARRIVAL-20", 20),
        ("SAL-ORD-M20-24", "R4-ARRIVAL-19", 4),
        ("SAL-ORD-M20-15", "R4-ARRIVAL-19", 15),
    ]
    assert all(
        operation.get("prepared_tranches")
        for operation in operations
        if operation["kind"] == "submit_pick"
    )
    assert len(client.documents["Pick List"]) == 3
    assert len(client.documents["Delivery Note"]) == 3
    assert len(client.documents["Shipment"]) == 3
    assert {
        shipment["delivery_address_name"] for shipment in client.documents["Shipment"].values()
    } == {"ADDR-M20-CUSTOMER-24", "ADDR-M20-CUSTOMER-15"}
    assert (
        client.documents["Purchase Order"]["PUR-ORD-2026-00016"]["items"][0]["received_qty"] == 40
    )


def test_cartons_do_not_become_parts_and_shortage_stays_visible(tmp_path: Path) -> None:
    service, bridge = _service(tmp_path)
    service.record_event(_arrival("arrival-a", lot="LOT-A", cartons=2, observed=20))
    result = service.record_event(_arrival("arrival-b", lot="LOT-B", cartons=2, observed=18))
    quantities = cast(dict[str, object], result["quantities"])
    assert quantities["cartons"] == 4
    assert quantities["received"] == 38
    assert quantities["missing"] == 2
    assert "PARTS_SHORTAGE" in _codes(result)
    assert [kind for kind, _event_id, _operation in bridge.calls] == [
        "receive_arrival",
        "receive_arrival",
    ]


def test_native_packet_scopes_quantity_attribution_and_inspection_evidence() -> None:
    expected = {
        "quantity_evidence": (
            "Carton and inner counts establish recorded quantities and any observed "
            "discrepancy; they do not establish its cause or responsible party."
        ),
        "attribution_evidence": (
            "This packet contains no supplier packing verification or transit/custody "
            "investigation establishing attribution for that discrepancy."
        ),
        "inspection_evidence": (
            "Quality Inspection records are declared report measurements and stated coverage; "
            "they are not independent physical tests performed by the agent."
        ),
    }
    projection = {
        "case_id": "M20-DIST-TEST",
        "case_label": "Packet evidence boundary test",
        "quantities": {},
        "lots": [],
        "allocations": [],
        "documents": [],
        "shipments": [],
        "events": [],
    }

    for synthetic_input in (True, False):
        packet = workspace_server._distributor_native_packet(
            {**projection, "synthetic_input": synthetic_input}
        )
        sources = cast(
            dict[str, object], cast(dict[str, object], packet["tool_payload"])["sources"]
        )
        facts = cast(dict[str, object], sources["read_erp_evidence"])
        provenance = cast(dict[str, object], facts["event_provenance"])
        assert {key: provenance[key] for key in expected} == expected
        assert ("synthetic test events" in provenance["recorded_events"]) is synthetic_input


def test_native_packet_projects_independent_per_order_fulfillment_facts() -> None:
    projection = {
        "case_id": "M20-DIST-FULFILLMENT-FACTS",
        "case_label": "Fulfillment arithmetic test",
        "quantities": {"uom": "Nos"},
        "lots": [],
        "allocations": [
            {
                "customer_order": "SO10",
                "requested_quantity": 15,
                "picked": 13,
                "dispatched": 0,
                "delivery_confirmed": 0,
            }
        ],
        "documents": [],
        "shipments": [],
        "events": [],
    }

    packet = workspace_server._distributor_native_packet(projection)
    facts = cast(
        dict[str, object],
        cast(dict[str, object], cast(dict[str, object], packet["tool_payload"])["sources"])[
            "read_erp_evidence"
        ],
    )

    assert facts["fulfillment_facts"] == [
        {
            "customer_order": "SO10",
            "uom": "Nos",
            "requested": 15,
            "picked": 13,
            "dispatched": 0,
            "delivery_confirmed": 0,
            "delivery_confirmation_evidence": {
                "kind": "UNSPECIFIED",
                "independent_physical_receipt": "NOT_VERIFIED",
                "definition": (
                    "delivery_confirmed is a recorded confirmation quantity, not an "
                    "independently verified physical receipt."
                ),
            },
            "remaining_to_pick": 2,
            "remaining_to_dispatch": 15,
            "remaining_delivery_confirmation": 15,
        }
    ]


def test_native_packet_keeps_bounded_complete_history_financials_and_selected_plan() -> None:
    events = [{"event_id": f"event-{index}"} for index in range(19)]
    packet = workspace_server._distributor_native_packet(
        {
            "case_id": "M20-DIST-PACKET-01",
            "case_label": "Bounded source packet",
            "synthetic_input": True,
            "quantities": {"uom": "Nos"},
            "lots": [],
            "allocations": [],
            "documents": [],
            "shipments": [],
            "events": events,
            "financials": {
                "status": "CURRENT",
                "purchase_invoices": {"status": "MISSING", "records": []},
            },
            "allocation_decision": {
                "status": "SELECTED",
                "plan_id": "plan-01",
                "contract_refs": ["SO-A", "SO-B"],
            },
        }
    )

    sources = cast(dict[str, object], cast(dict[str, object], packet["tool_payload"])["sources"])
    control = cast(dict[str, object], sources["read_control_context"])
    facts = cast(dict[str, object], sources["read_erp_evidence"])
    collaboration = cast(dict[str, object], sources["read_collaboration_evidence"])
    assert control["retained_event_count"] == 19
    assert control["retained_event_limit"] == 64
    assert control["retained_event_history_complete"] is True
    assert collaboration["retained_physical_events"] == events
    assert facts["financials"] == {
        "status": "CURRENT",
        "purchase_invoices": {"status": "MISSING", "records": []},
    }
    assert facts["retained_allocation_decision"] == {
        "status": "SELECTED",
        "plan_id": "plan-01",
        "contract_refs": ["SO-A", "SO-B"],
    }

    missing_history = workspace_server._distributor_native_packet(
        {
            "case_id": "M20-DIST-PACKET-02",
            "quantities": {"uom": "Nos"},
            "lots": [],
            "allocations": [],
            "documents": [],
            "shipments": [],
        }
    )
    missing_control = cast(
        dict[str, object],
        cast(dict[str, object], missing_history["tool_payload"])["sources"],
    )["read_control_context"]
    assert cast(Mapping[str, object], missing_control)["retained_event_history_complete"] is False


@pytest.mark.parametrize(
    ("synthetic_input", "kind"),
    [
        (True, "SYNTHETIC_RECORDED_EVENT"),
        (False, "RECORDED_EVENT"),
        (None, "UNSPECIFIED"),
    ],
)
def test_fulfillment_confirmation_evidence_never_claims_physical_receipt(
    synthetic_input: object, kind: str
) -> None:
    facts = workspace_server.distributor_fulfillment_facts(
        {"uom": "Nos"},
        [
            {
                "customer_order": "SO10",
                "requested_quantity": 15,
                "picked": 15,
                "dispatched": 15,
                "delivery_confirmed": 15,
            }
        ],
        synthetic_input,
    )

    assert facts[0]["delivery_confirmation_evidence"] == {
        "kind": kind,
        "independent_physical_receipt": "NOT_VERIFIED",
        "definition": (
            "delivery_confirmed is a recorded confirmation quantity, not an independently "
            "verified physical receipt."
        ),
    }


def test_fulfillment_facts_omit_missing_invalid_or_inconsistent_counts() -> None:
    assert (
        workspace_server.distributor_fulfillment_facts(
            {"uom": "Nos"},
            [
                {"customer_order": "SO-MISSING", "requested_quantity": 15, "dispatched": 0},
                {
                    "customer_order": "SO-NEGATIVE",
                    "requested_quantity": 15,
                    "picked": -1,
                    "dispatched": 0,
                    "delivery_confirmed": 0,
                },
                {
                    "customer_order": "SO-OVERPICKED",
                    "requested_quantity": 15,
                    "picked": 16,
                    "dispatched": 0,
                    "delivery_confirmed": 0,
                },
                {
                    "customer_order": "SO-CONFIRMED-WITHOUT-DISPATCH",
                    "requested_quantity": 15,
                    "picked": 15,
                    "dispatched": 0,
                    "delivery_confirmed": 15,
                },
                {
                    "customer_order": "SO-DISPATCHED-WITHOUT-PICK",
                    "requested_quantity": 15,
                    "picked": 0,
                    "dispatched": 15,
                    "delivery_confirmed": 0,
                },
            ],
        )
        == []
    )


def test_component_replacement_closes_only_the_supported_parent_shortage_and_keeps_quality_facts(
    tmp_path: Path,
) -> None:
    service, bridge = _service(tmp_path)
    service.record_event(_arrival("arrival-a", lot="LOT-A", cartons=2, observed=20))
    service.record_event(
        _event(
            "inspection-a-sample-fail",
            "inspection",
            lot="LOT-A",
            result="FAIL",
            scope="SAMPLE",
            metric="diameter_mm",
            measured=10.4,
            sample_quantity=2,
            inspection_report_ref="synthetic:qi-a-sample-fail",
        )
    )
    shortage_state = service.record_event(
        _arrival("arrival-b", lot="LOT-B", cartons=2, observed=18)
    )
    assert shortage_state["quantities"]["initial_expected_cartons"] == 4
    assert shortage_state["quantities"]["observed_outer_packages"] == 4
    replacement = service.record_event(
        _arrival("arrival-c-replacement", lot="LOT-C", cartons=1, observed=2, pack=2)
    )

    assert replacement["quantities"]["received"] == 40
    assert replacement["quantities"]["missing"] == 0
    shortage = next(
        alert
        for alert in cast(list[dict[str, object]], replacement["alerts"])
        if alert["code"] == "PARTS_SHORTAGE" and alert.get("lot") == "LOT-B"
    )
    assert shortage["quantity"] == 2
    assert shortage["status"] == "RESOLVED"
    assert "PACK_QUANTITY_MISMATCH" not in _codes(replacement)
    assert [kind for kind, _event_id, _operation in bridge.calls].count("receive_arrival") == 3

    packet = workspace_server._distributor_native_packet(replacement)
    sources = cast(dict[str, object], cast(dict[str, object], packet["tool_payload"])["sources"])
    control = cast(dict[str, object], sources["read_control_context"])
    quality_policy = cast(dict[str, object], control["quality_policy"])
    assert quality_policy["inspection_criteria"] == {
        "diameter_mm": {"minimum": 9.9, "maximum": 10.1}
    }
    erp_facts = cast(dict[str, object], sources["read_erp_evidence"])
    erp_quantities = cast(dict[str, object], erp_facts["quantities"])
    assert erp_quantities["initial_expected_cartons"] == 4
    assert erp_quantities["observed_outer_packages"] == erp_quantities["cartons"] == 5
    assert [
        (lot["lot"], lot["expected_pack_quantity"], lot.get("replacement_for_lot"))
        for lot in cast(list[dict[str, object]], erp_facts["lots"])
    ] == [
        ("LOT-A", 10, None),
        ("LOT-B", 10, None),
        ("LOT-C", 2, "LOT-B"),
    ]
    quality_alert = next(
        alert
        for alert in cast(list[dict[str, object]], control["active_alerts"])
        if alert["code"] == "QUALITY_FAILED"
    )
    assert quality_alert == {
        "code": "QUALITY_FAILED",
        "status": "OPEN",
        "message": (
            "A sample measurement failed. The lot is held pending supported disposition; "
            "this does not establish every held unit is defective."
        ),
        "event_id": "inspection-a-sample-fail",
        "evidence_ref": "synthetic:inspection-a-sample-fail",
        "synthetic": True,
        "lot": "LOT-A",
        "quantity": 20,
        "held_quantity": 20,
        "scope": "SAMPLE",
        "sample_quantity": 2,
        "metric": "diameter_mm",
        "measured": 10.4,
        "criterion": {"minimum": 9.9, "maximum": 10.1},
        "required_lot_quantity": 20,
        "inspection_report_ref": "synthetic:qi-a-sample-fail",
    }


def test_failed_sample_holds_lot_without_calling_every_piece_defective_and_full_release_resumes(
    tmp_path: Path,
) -> None:
    service, bridge = _service(tmp_path)
    service.record_event(_arrival("arrival-a", lot="LOT-A", cartons=2, observed=20))
    failed = service.record_event(
        _event(
            "inspection-a-fail",
            "inspection",
            lot="LOT-A",
            result="FAIL",
            scope="SAMPLE",
            metric="diameter_mm",
            measured=10.4,
            sample_quantity=2,
            inspection_report_ref="synthetic:qi-a-sample-fail",
        )
    )
    lot = next(
        row for row in cast(list[dict[str, object]], failed["lots"]) if row["lot"] == "LOT-A"
    )
    assert lot["held"] == 20 and lot["usable"] == 0
    quality_alert = next(
        alert
        for alert in cast(list[dict[str, object]], failed["alerts"])
        if alert["code"] == "QUALITY_FAILED"
    )
    assert quality_alert["scope"] == "SAMPLE" and quality_alert["sample_quantity"] == 2
    assert "does not establish every held unit is defective" in quality_alert["message"]
    released = service.record_event(
        _event(
            "inspection-a-release",
            "inspection",
            lot="LOT-A",
            result="PASS",
            scope="WHOLE_LOT",
            metric="diameter_mm",
            measured=10.0,
            sample_quantity=20,
            inspection_report_ref="synthetic:qi-a-full-pass",
        )
    )
    released_lot = next(
        row for row in cast(list[dict[str, object]], released["lots"]) if row["lot"] == "LOT-A"
    )
    assert released_lot["usable"] == 20 and released_lot["held"] == 0
    assert released["quantities"]["allocated"] == 20
    assert {kind for kind, _event_id, _operation in bridge.calls} >= {
        "record_inspection",
        "release_from_quality",
        "prepare_pick",
    }


def test_client_cannot_widen_quality_spec_or_call_a_partial_reading_whole_lot_pass(
    tmp_path: Path,
) -> None:
    service, bridge = _service(tmp_path)
    service.record_event(_arrival("arrival-a", lot="LOT-A", cartons=2, observed=20))
    contradictory = service.record_event(
        _event(
            "inspection-a-contradictory",
            "inspection",
            lot="LOT-A",
            result="PASS",
            scope="WHOLE_LOT",
            metric="diameter_mm",
            measured=10.4,
            sample_quantity=20,
            inspection_report_ref="synthetic:qi-a-contradictory",
        )
    )
    incomplete = service.record_event(
        _event(
            "inspection-a-incomplete",
            "inspection",
            lot="LOT-A",
            result="PASS",
            scope="WHOLE_LOT",
            metric="diameter_mm",
            measured=10.0,
            sample_quantity=2,
            inspection_report_ref="synthetic:qi-a-not-full",
        )
    )
    assert {"INSPECTION_RESULT_CONFLICT", "WHOLE_LOT_EVIDENCE_INCOMPLETE"} <= _codes(incomplete)
    assert all(kind != "release_from_quality" for kind, _event_id, _operation in bridge.calls)
    assert contradictory["quantities"]["usable"] == incomplete["quantities"]["usable"] == 0


def test_held_or_wrong_sku_input_never_creates_pick_or_delivery(tmp_path: Path) -> None:
    service, bridge = _service(tmp_path)
    service.record_event(_arrival("arrival-a", lot="LOT-A", cartons=2, observed=20))
    held_pick = service.record_event(
        _event(
            "picked-held",
            "picked",
            customer_order="SO-PRIORITY",
            lot="LOT-A",
            quantity=1,
            pick_evidence_ref="synthetic:held-pick",
        )
    )
    wrong_sku = service.record_event(
        _arrival("arrival-wrong", lot="LOT-B", cartons=2, observed=20, item_code="OTHER-SKU")
    )
    unknown_lot = service.record_event(
        _arrival("arrival-unknown", lot="LOT-UNKNOWN", cartons=1, observed=10)
    )
    assert "PICK_NOT_ELIGIBLE" in _codes(held_pick)
    assert "WRONG_SKU" in _codes(wrong_sku)
    assert "UNKNOWN_LOT" in _codes(unknown_lot)
    assert not {kind for kind, _event_id, _operation in bridge.calls}.intersection(
        {"submit_pick", "submit_delivery_note", "create_shipment"}
    )


def test_duplicate_event_replays_without_native_repeat_and_changed_payload_is_rejected(
    tmp_path: Path,
) -> None:
    service, bridge = _service(tmp_path)
    event = _arrival("arrival-a", lot="LOT-A", cartons=2, observed=20)
    first = service.record_event(event)
    replay = service.record_event(deepcopy(event))
    assert replay == first
    assert [kind for kind, _event_id, _operation in bridge.calls] == ["receive_arrival"]
    changed = {**event, "observed_stock_quantity": 19}
    with pytest.raises(DistributorEventConflict):
        service.record_event(changed)
    assert [kind for kind, _event_id, _operation in bridge.calls] == ["receive_arrival"]


def test_outbound_facts_deduplicate_reissued_pick_list_document_identity() -> None:
    projection: dict[str, object] = {
        "allocations": [
            {
                "customer_order": "SO10",
                "requested_quantity": 15,
                "status": "ALLOCATED",
            }
        ]
    }
    events: list[dict[str, object]] = [
        {
            "event_id": "picked-so10-b13-original",
            "type": "picked",
            "status": "APPLIED",
            "customer_order": "SO10",
            "quantity": 13,
            "operations": [
                {
                    "kind": "submit_pick",
                    "status": "APPLIED",
                    "documents": [
                        {"kind": "Pick List", "name": "MAT-PICK-00006", "status": "Submitted"}
                    ],
                }
            ],
        },
        {
            "event_id": "picked-so10-b13-continuation",
            "type": "picked",
            "status": "APPLIED",
            "customer_order": "SO10",
            "quantity": 13,
            "operations": [
                {
                    "kind": "submit_pick",
                    "status": "ALREADY_APPLIED",
                    "documents": [
                        {"kind": "Pick List", "name": "MAT-PICK-00006", "status": "Submitted"}
                    ],
                }
            ],
        },
        {
            "event_id": "picked-so10-c2",
            "type": "picked",
            "status": "APPLIED",
            "customer_order": "SO10",
            "quantity": 2,
            "operations": [
                {
                    "kind": "submit_pick",
                    "status": "APPLIED",
                    "documents": [
                        {"kind": "Pick List", "name": "MAT-PICK-00007", "status": "Submitted"}
                    ],
                }
            ],
        },
        {
            "event_id": "picked-so10-c2-blocked",
            "type": "picked",
            "status": "BLOCKED",
            "customer_order": "SO10",
            "quantity": 2,
            "operations": [
                {
                    "kind": "submit_pick",
                    "status": "BLOCKED",
                    "documents": [
                        {"kind": "Pick List", "name": "MAT-PICK-00008", "status": "Submitted"}
                    ],
                }
            ],
        },
    ]

    DistributorOperations._add_outbound_facts(projection, events, [])

    allocation = cast(list[dict[str, object]], projection["allocations"])[0]
    assert allocation["picked"] == 15
    assert allocation["status"] == "PICKED"
    assert [event["status"] for event in events] == ["APPLIED", "APPLIED", "APPLIED", "BLOCKED"]


def test_unreconciled_current_source_holds_without_overwriting_local_case_facts(
    tmp_path: Path,
) -> None:
    service, bridge = _service(tmp_path, _r4_config())
    service.record_event(_r4_arrival("arrival-r4-20", "R4-ARRIVAL-20", 20))
    current = bridge.read_case(bridge.config)
    assert isinstance(current, dict)
    quantities = cast(dict[str, object], current["quantities"])
    quantities["usable"] = 19
    quantities["held"] = 1
    quantities["allocated"] = 19
    lots = cast(list[dict[str, object]], current["lots"])
    lots[0]["usable"] = 19
    lots[0]["held"] = 1
    allocations = cast(list[dict[str, object]], current["allocations"])
    allocations[0]["allocated"] = 19
    allocations[0]["backordered"] = 5
    bridge.source_override = current

    held = service.projection()

    assert held["available"] is False
    assert held["stage"] == "SOURCE_UNAVAILABLE"
    alert = next(
        row
        for row in cast(list[dict[str, object]], held["alerts"])
        if row["code"] == "SOURCE_UNAVAILABLE"
    )
    assert alert["error_code"] == "ERP_SOURCE_RECONCILIATION_UNKNOWN"
    assert held["quantities"]["received"] == 20
    blocked = service.record_event(_r4_arrival("arrival-r4-19", "R4-ARRIVAL-19", 19))
    assert blocked["available"] is False
    assert [kind for kind, _event_id, _operation in bridge.calls] == [
        "receive_arrival",
        "prepare_pick",
    ]


def test_get_derives_deadline_alerts_without_inventing_loss_or_starting_a_write(
    tmp_path: Path,
) -> None:
    config = _r4_config()
    config["expected_at"] = "2026-09-10T08:00:00+00:00"
    config["promised_delivery_at"] = "2026-09-10T08:30:00+00:00"
    bridge = _Bridge(config)
    service = DistributorOperations(
        tmp_path / "deadline.sqlite3",
        config,
        bridge,
        clock=lambda: datetime(2026, 9, 10, 9, tzinfo=UTC),
    )
    bridge.state_provider = service._latest_state
    initial = service.projection()
    assert "RECEIPT_OVERDUE" in _codes(initial)
    assert "no loss cause is inferred" in str(initial).lower()
    service.record_event(_r4_arrival("arrival-r4-20", "R4-ARRIVAL-20", 20))
    received = service.record_event(_r4_arrival("arrival-r4-19", "R4-ARRIVAL-19", 19))
    shipment = next(
        document["name"]
        for document in cast(
            list[dict[str, object]],
            service.record_event(
                _event(
                    "picked-r4-20",
                    "picked",
                    customer_order="SO-R4-PRIORITY",
                    lot="R4-ARRIVAL-20",
                    quantity=20,
                    pick_evidence_ref="synthetic:pick-r4-20",
                )
            )["documents"],
        )
        if document["kind"] == "Shipment"
    )
    service.record_event(_event("pickup-r4-20", "carrier_pickup", shipment_id=shipment))
    polled = service.projection()
    assert "RECEIPT_OVERDUE" not in _codes(received)
    assert "DELIVERY_CONFIRMATION_DUE" in _codes(polled)
    assert [kind for kind, _event_id, _operation in bridge.calls].count("create_shipment") == 1


def test_http_projection_and_event_route_use_the_same_service(tmp_path: Path) -> None:
    service, _bridge = _service(tmp_path)
    handler = cast(Any, object.__new__(DecisionWorkspaceHandler))
    handler.server = SimpleNamespace(distributor_operations=service)
    sent: list[object] = []
    handler._send_json = lambda _status, value: sent.append(value)

    handler._v1_get("/api/v1/distributor-operations", {})
    initial = cast(dict[str, object], sent[-1])["distributor_operations"]
    assert isinstance(initial, dict) and initial["case_id"] == "M20-DIST-COMPONENT-01"
    handler._v1_post(
        "/api/v1/distributor-operations/events",
        _arrival("arrival-a", lot="LOT-A", cartons=2, observed=20),
    )
    event_projection = cast(dict[str, object], sent[-1])["distributor_operations"]
    assert isinstance(event_projection, dict) and event_projection["quantities"]["received"] == 20


def test_receive_reconciliation_admits_exact_submitted_receipt_without_replaying_event(
    tmp_path: Path,
) -> None:
    service, bridge = _service(tmp_path)
    bridge.statuses["receive_arrival"] = "UNKNOWN_OUTCOME"
    retained = service.record_event(_arrival("arrival-a", lot="LOT-A", cartons=2, observed=20))
    retained_quantities = cast(Mapping[str, object], retained["quantities"])
    assert retained_quantities["received"] == 0
    assert [kind for kind, _event_id, _operation in bridge.calls] == ["receive_arrival"]

    bridge.source_override = _component_source_after_confirmed_arrival(bridge.config)
    handler = cast(Any, object.__new__(DecisionWorkspaceHandler))
    handler.server = SimpleNamespace(distributor_operations=service)
    sent: list[object] = []
    handler._send_json = lambda _status, value: sent.append(value)

    handler._v1_post("/api/v1/distributor-operations/reconcile-receive", {"event_id": "arrival-a"})
    reconciled = cast(dict[str, object], sent[-1])["distributor_operations"]
    assert isinstance(reconciled, dict)
    assert reconciled["quantities"]["received"] == reconciled["quantities"]["held"] == 20
    lot_a = next(
        row for row in cast(list[dict[str, object]], reconciled["lots"]) if row["lot"] == "LOT-A"
    )
    assert lot_a["expected_pack_quantity"] == 10
    event = cast(list[dict[str, object]], reconciled["events"])[0]
    assert event["status"] == "UNKNOWN_OUTCOME"
    assert event["operations"] == [
        {
            "kind": "receive_arrival",
            "status": "UNKNOWN_OUTCOME",
            "documents": [],
            "error_code": "ERP_UNAVAILABLE",
        }
    ]
    reconciliations = cast(list[Mapping[str, object]], event["reconciliations"])
    assert reconciliations[0]["status"] == "NATIVE_CONFIRMED"
    alerts = cast(list[dict[str, object]], reconciled["alerts"])
    unknown = next(alert for alert in alerts if alert["code"] == "NATIVE_OPERATION_UNKNOWN")
    assert unknown["status"] == "RESOLVED"
    assert "QUALITY_EVIDENCE_REQUIRED" in _codes(reconciled)
    assert [kind for kind, _event_id, _operation in bridge.calls] == ["receive_arrival"]
    assert bridge.reconcile_calls == [
        ("arrival-a", _arrival("arrival-a", lot="LOT-A", cartons=2, observed=20))
    ]

    handler._v1_post("/api/v1/distributor-operations/reconcile-receive", {"event_id": "arrival-a"})
    assert len(bridge.reconcile_calls) == 1
    assert [kind for kind, _event_id, _operation in bridge.calls] == ["receive_arrival"]


def test_native_ask_packet_is_current_read_only_and_static_ui_files_are_allowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, _bridge = _service(tmp_path, _r4_config())
    projection = service.record_event(_r4_arrival("arrival-r4-20", "R4-ARRIVAL-20", 20))
    observed: dict[str, object] = {}

    def fake_native_run(**kwargs: object) -> SimpleNamespace:
        observed.update(kwargs)
        return SimpleNamespace(
            answer="The current case has 20 Box received and 19 Box still missing.",
            provider={"provider": "test"},
            session_id="native-session-test",
        )

    monkeypatch.setattr(workspace_server, "run_native_receiving_turn", fake_native_run)
    ask_turn = workspace_server._distributor_native_ask_turn(
        settings=Settings(agent_provider=AgentProvider.BEDROCK),
        session_root=tmp_path / "native-sessions",
    )
    result = ask_turn("What is currently received?", projection)

    assert result["status"] == "COMPLETE"
    packet = cast(dict[str, object], observed["packet"])
    sources = cast(dict[str, object], cast(dict[str, object], packet["tool_payload"])["sources"])
    erp = cast(dict[str, object], sources["read_erp_evidence"])
    assert erp["quantities"] == projection["quantities"]
    assert erp["documents"] == projection["documents"]
    assert sources["read_airtable_evidence"] == {
        "status": "UNAVAILABLE",
        "reason": "NOT_CONNECTED_FOR_DISTRIBUTOR_CASE",
        "records": [],
    }
    assert observed["runtime_instance_id"] == "distributor-operations:M20-DIST-R4-FOLLOW-ON"
    assert observed["conversation_id"] == "operator"
    assert workspace_server.STATIC_FILES["/operations"][0] == "distributor-operations.html"
    assert "/distributor-operations.js" in workspace_server.STATIC_FILES
    assert "/distributor-operations.css" in workspace_server.STATIC_FILES


def test_distributor_model_selection_is_explicit_and_opus_history_is_isolated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(agent_provider=AgentProvider.BEDROCK)
    assert isinstance(
        workspace_server._distributor_model_factory(settings=settings, configured_model=None),
        BedrockNovaProFactory,
    )
    opus_factory = workspace_server._distributor_model_factory(
        settings=settings, configured_model="opus46"
    )
    assert isinstance(opus_factory, BedrockOpus46Factory)
    assert opus_factory.config.model_id == OPUS46_MODEL_ID
    assert opus_factory.config.max_tokens == 3_072
    assert opus_factory.config.budget.max_requests == 16
    assert opus_factory.provenance()["cost_attribution"] == {
        "currency": "USD",
        "input_usd_per_million_tokens": "5.5",
        "output_usd_per_million_tokens": "27.5",
        "per_turn_output_token_cap": 3_072,
        "request_count_cap": 16,
        "aggregate_cost_cap_usd": "3.00",
    }
    bounded_opus_factory = workspace_server._distributor_model_factory(
        settings=replace(settings, max_aws_spend_usd=Decimal("0.39")),
        configured_model="opus46",
    )
    assert bounded_opus_factory.provenance()["cost_attribution"]["aggregate_cost_cap_usd"] == "0.39"
    assert isinstance(
        workspace_server._distributor_model_factory(
            settings=settings, configured_model=OPUS46_MODEL_ID
        ),
        BedrockOpus46Factory,
    )
    with pytest.raises(ValueError, match="MISSING20_DISTRIBUTOR_MODEL"):
        workspace_server._distributor_model_factory(settings=settings, configured_model="opus")

    service, _bridge = _service(tmp_path, _r4_config())
    observed: dict[str, object] = {}

    def fake_native_run(**kwargs: object) -> SimpleNamespace:
        observed.update(kwargs)
        return SimpleNamespace(
            answer="The source has no dispatched quantity.",
            provider={"provider": "test"},
            session_id="native-session-test",
        )

    monkeypatch.setattr(workspace_server, "run_native_receiving_turn", fake_native_run)
    ask_turn = workspace_server._distributor_native_ask_turn(
        settings=settings,
        session_root=tmp_path / "native-sessions",
        factory=opus_factory,
    )
    assert ask_turn("What is dispatched?", service.projection())["status"] == "COMPLETE"
    assert observed["factory"] is opus_factory
    assert observed["runtime_instance_id"] == "distributor-operations:opus46:M20-DIST-R4-FOLLOW-ON"
    assert observed["conversation_id"] == "opus46:operator"


def test_distributor_allocation_selector_builds_the_selected_factory_per_operation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(agent_provider=AgentProvider.BEDROCK)
    created: list[BedrockOpus46Factory] = []
    observed: dict[str, object] = {}

    def fresh_opus_factory(**_kwargs: object) -> BedrockOpus46Factory:
        factory = BedrockOpus46Factory()
        created.append(factory)
        return factory

    def fake_select_contract_plan(
        *, plan: Mapping[str, object], factory: object
    ) -> Mapping[str, object]:
        observed["factory"] = factory
        return {"plan_id": plan["plan_id"]}

    monkeypatch.setattr(workspace_server, "_distributor_model_factory", fresh_opus_factory)
    monkeypatch.setattr(workspace_server, "select_contract_plan", fake_select_contract_plan)
    selector = workspace_server._distributor_native_allocation_selector(
        settings=settings, configured_model="opus46"
    )
    assert selector({"plan_id": "plan-1"}) == {"plan_id": "plan-1"}
    assert selector({"plan_id": "plan-2"}) == {"plan_id": "plan-2"}
    assert len(created) == 2
    assert observed["factory"] is created[-1]


def test_distributor_ask_builds_a_fresh_selected_factory_per_invocation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(agent_provider=AgentProvider.BEDROCK)
    service, _bridge = _service(tmp_path, _r4_config())
    created: list[BedrockOpus46Factory] = []
    used: list[object] = []

    def fresh_opus_factory(**_kwargs: object) -> BedrockOpus46Factory:
        factory = BedrockOpus46Factory()
        created.append(factory)
        return factory

    def fake_native_run(**kwargs: object) -> SimpleNamespace:
        used.append(kwargs["factory"])
        return SimpleNamespace(
            answer="The source has no dispatched quantity.",
            provider={"provider": "test"},
            session_id="native-session-test",
        )

    monkeypatch.setattr(workspace_server, "_distributor_model_factory", fresh_opus_factory)
    monkeypatch.setattr(workspace_server, "run_native_receiving_turn", fake_native_run)
    ask_turn = workspace_server._distributor_native_ask_turn(
        settings=settings,
        session_root=tmp_path / "native-sessions",
        configured_model="opus46",
    )
    assert ask_turn("What is dispatched?", service.projection())["status"] == "COMPLETE"
    assert ask_turn("What is dispatched?", service.projection())["status"] == "COMPLETE"
    assert used == created
    assert len(created) == 2
    assert created[0] is not created[1]


def test_native_operations_answer_rejects_non_english_model_prose(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, _bridge = _service(tmp_path, _r4_config())
    projection = service.projection()

    def fake_native_run(**_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(
            answer="\u8bf7\u67e5\u770b SO-R4-PRIORITY 20 Box",
            provider={"provider": "test"},
            session_id="native-session-test",
        )

    monkeypatch.setattr(workspace_server, "run_native_receiving_turn", fake_native_run)
    ask_turn = workspace_server._distributor_native_ask_turn(
        settings=Settings(agent_provider=AgentProvider.BEDROCK),
        session_root=tmp_path / "native-sessions",
    )

    result = ask_turn("\u8bf7\u7528\u4e2d\u6587\u56de\u7b54 current quantity", projection)

    assert result == {
        "status": "UNAVAILABLE",
        "detail": (
            "The native read-only distributor conversation is unavailable; "
            "no fallback answer was used."
        ),
        "error_type": "ProductLanguageViolation",
    }


def test_contract_plan_selects_date_first_then_prepares_once_and_replays_read_only(
    tmp_path: Path,
) -> None:
    config = _contract_config()
    bridge = _Bridge(config)
    selections: list[dict[str, object]] = []

    def selector(plan: Mapping[str, object]) -> Mapping[str, object]:
        selections.append(dict(plan))
        return {
            "plan_id": plan["plan_id"],
            "rationale": "Earlier promised customer order is feasible.",
            "contract_refs": ["SO-R4-STANDARD"],
        }

    service = DistributorOperations(
        tmp_path / "contract.sqlite3", config, bridge, allocation_selector=selector
    )
    bridge.state_provider = service._latest_state
    first = service.record_event(_r4_arrival("contract-arrival", "R4-ARRIVAL-20", 20))

    assert len(selections) == 1
    assert [kind for kind, _event, _operation in bridge.calls] == [
        "receive_arrival",
        "prepare_pick",
    ]
    prepared = bridge.calls[-1][2]
    assert prepared["customer_order"] == "SO-R4-STANDARD"
    event = cast(list[dict[str, object]], first["events"])[-1]
    assert cast(dict[str, object], event["allocation_decision"])["status"] == "SELECTED"

    replay = service.record_event(_r4_arrival("contract-arrival", "R4-ARRIVAL-20", 20))
    assert replay == first
    assert len(selections) == 1
    assert [kind for kind, _event, _operation in bridge.calls] == [
        "receive_arrival",
        "prepare_pick",
    ]

    picked = service.record_event(
        _event(
            "contract-picked",
            "picked",
            customer_order="SO-R4-STANDARD",
            lot="R4-ARRIVAL-20",
            quantity=15,
            pick_evidence_ref="SYN-PICK-CONTRACT-15",
        )
    )
    assert picked["events"][-1]["status"] == "APPLIED"
    assert [kind for kind, _event, _operation in bridge.calls][-3:] == [
        "submit_pick",
        "submit_delivery_note",
        "create_shipment",
    ]


def test_contract_rejected_selection_does_not_start_pick_preparation(tmp_path: Path) -> None:
    config = _contract_config()
    bridge = _Bridge(config)
    service = DistributorOperations(
        tmp_path / "contract-rejected.sqlite3",
        config,
        bridge,
        allocation_selector=lambda _plan: {
            "plan_id": "cap-stale",
            "rationale": "stale selection",
            "contract_refs": ["SO-R4-STANDARD"],
        },
    )
    bridge.state_provider = service._latest_state

    result = service.record_event(_r4_arrival("contract-rejected", "R4-ARRIVAL-20", 20))
    assert [kind for kind, _event, _operation in bridge.calls] == ["receive_arrival"]
    assert "ALLOCATION_SELECTION_PENDING" in _codes(result)
    assert result["events"][-1]["status"] == "APPLIED"


@pytest.mark.parametrize(
    "refs",
    [
        ["SO-R4-PRIORITY"],
        ["SO-R4-STANDARD", "SO-R4-STANDARD"],
        ["SO-R4-STANDARD", "SO-UNKNOWN"],
    ],
)
def test_contract_selection_requires_exact_unique_compiler_references(
    tmp_path: Path, refs: list[str]
) -> None:
    config = _contract_config()
    bridge = _Bridge(config)
    calls = 0

    def selector(plan: Mapping[str, object]) -> Mapping[str, object]:
        nonlocal calls
        calls += 1
        return {"plan_id": plan["plan_id"], "rationale": "bad refs", "contract_refs": refs}

    service = DistributorOperations(
        tmp_path / "contract-refs.sqlite3", config, bridge, allocation_selector=selector
    )
    bridge.state_provider = service._latest_state
    result = service.record_event(_r4_arrival("contract-refs", "R4-ARRIVAL-20", 20))

    assert calls == 1
    assert [kind for kind, _event, _operation in bridge.calls] == ["receive_arrival"]
    assert "ALLOCATION_SELECTION_PENDING" in _codes(result)


@pytest.mark.parametrize("change", ["duplicate", "insufficient_lot"])
def test_contract_native_tranche_guard_blocks_before_selector(tmp_path: Path, change: str) -> None:
    config = _contract_config()
    tranches = cast(list[dict[str, object]], config["pick_tranches"])
    if change == "duplicate":
        tranches.append(
            {"customer_order": "SO-R4-STANDARD", "lot": "R4-ARRIVAL-19", "quantity": 15}
        )
    else:
        tranches[0]["lot"] = "R4-ARRIVAL-19"
    bridge = _Bridge(config)
    selections = 0

    def selector(_plan: Mapping[str, object]) -> Mapping[str, object]:
        nonlocal selections
        selections += 1
        raise AssertionError("selector must not be reached")

    service = DistributorOperations(
        tmp_path / f"contract-{change}.sqlite3", config, bridge, allocation_selector=selector
    )
    bridge.state_provider = service._latest_state
    result = service.record_event(_r4_arrival(f"contract-{change}", "R4-ARRIVAL-20", 20))

    assert selections == 0
    assert [kind for kind, _event, _operation in bridge.calls] == ["receive_arrival"]
    assert "ALLOCATION_PLAN_NATIVE_TRANCHE_UNSUPPORTED" in _codes(result)


def test_contract_native_tranche_guard_conserves_collective_lot_availability(
    tmp_path: Path,
) -> None:
    config = _contract_config()
    allocations = cast(list[dict[str, object]], config["allocations"])
    allocations[0]["requested_quantity"] = 10
    allocations[0]["minimum_dispatch_quantity"] = 5
    allocations[1]["requested_quantity"] = 10
    allocations[1]["minimum_dispatch_quantity"] = 5
    config["pick_tranches"] = [
        {"customer_order": "SO-R4-STANDARD", "lot": "R4-ARRIVAL-20", "quantity": 10},
        {"customer_order": "SO-R4-PRIORITY", "lot": "R4-ARRIVAL-20", "quantity": 10},
    ]
    service = DistributorOperations(tmp_path / "collective.sqlite3", config, None)
    state = service._initial_state()
    lots = cast(list[dict[str, object]], state["lots"])
    lots[0]["usable"] = 15
    lots[1]["usable"] = 5
    service._recompute_allocations(state)

    assert service._contract_plan_native_tranches(service._contract_plan(state), state) is None


def test_contract_selection_is_durable_before_prepare_fault(tmp_path: Path) -> None:
    config = _contract_config()

    class CheckpointBridge(_Bridge):
        service: DistributorOperations | None = None
        checkpoint: dict[str, object] | None = None

        def apply_operation(
            self, config: Mapping[str, object], operation: Mapping[str, object], event_id: str
        ) -> Mapping[str, object]:
            if operation["kind"] == "prepare_pick":
                assert self.service is not None
                self.checkpoint = cast(dict[str, object], self.service._latest_state())
                raise RuntimeError("prepare transport failed")
            return super().apply_operation(config, operation, event_id)

    bridge = CheckpointBridge(config)
    service = DistributorOperations(
        tmp_path / "contract-checkpoint.sqlite3",
        config,
        bridge,
        allocation_selector=lambda plan: {
            "plan_id": plan["plan_id"],
            "rationale": "Exact candidate is feasible.",
            "contract_refs": ["SO-R4-STANDARD"],
        },
    )
    bridge.service = service
    bridge.state_provider = service._latest_state

    result = service.record_event(_r4_arrival("contract-checkpoint", "R4-ARRIVAL-20", 20))
    assert result["events"][-1]["status"] == "UNKNOWN_OUTCOME"
    assert bridge.checkpoint is not None
    decision = cast(dict[str, object], bridge.checkpoint["allocation_decision"])
    assert decision["status"] == "SELECTED"
    assert cast(dict[str, object], decision["plan"])["version"] == "v1"
    assert decision["event_id"] == "contract-checkpoint"


def test_contract_compiler_preserves_prepared_commitment_and_allows_only_final_remainder() -> None:
    allocations = [
        {
            "customer_order": "SO-A",
            "requested_quantity": 15,
            "dispatched": 0,
            "promised_delivery_at": "2026-09-11T09:00:00+00:00",
            "customer_priority": 1,
            "partial_dispatch": True,
            "minimum_dispatch_quantity": 10,
            "allow_final_remainder": True,
        },
        {
            "customer_order": "SO-B",
            "requested_quantity": 15,
            "dispatched": 0,
            "promised_delivery_at": "2026-09-12T09:00:00+00:00",
            "customer_priority": 1,
            "partial_dispatch": True,
            "minimum_dispatch_quantity": 10,
            "allow_final_remainder": False,
        },
    ]
    plan = compile_plan(
        allocations=allocations,
        lots=[{"usable": 20}],
        prepared_picks=[{"customer_order": "SO-A", "remaining": 13}],
    )

    assert plan["new_quantity"] == 2
    assert plan["rows"] == [
        {
            "customer_order": "SO-A",
            "promised_delivery_at": "2026-09-11T09:00:00+00:00",
            "customer_priority": 1,
            "partial_dispatch": True,
            "minimum_dispatch_quantity": 10,
            "allow_final_remainder": True,
            "prepared_commitment": 13,
            "remaining_to_dispatch_before_new": 2,
            "new_quantity": 2,
            "quantity": 15,
            "remaining_after_dispatch": 0,
            "dispatch_candidate": True,
            "dispatch_eligibility": "FINAL_REMAINDER_ALLOWED",
        },
        {
            "customer_order": "SO-B",
            "promised_delivery_at": "2026-09-12T09:00:00+00:00",
            "customer_priority": 1,
            "partial_dispatch": True,
            "minimum_dispatch_quantity": 10,
            "allow_final_remainder": False,
            "prepared_commitment": 0,
            "remaining_to_dispatch_before_new": 15,
            "new_quantity": 0,
            "quantity": 0,
            "remaining_after_dispatch": 15,
            "dispatch_candidate": False,
            "dispatch_eligibility": "NOT_EXECUTABLE",
        },
    ]


def test_contract_promises_are_timezone_normalized_and_malformed_dates_are_rejected(
    tmp_path: Path,
) -> None:
    config = _contract_config()
    allocations = cast(list[dict[str, object]], config["allocations"])
    allocations[0]["promised_delivery_at"] = "2026-09-12T11:00:00+02:00"
    service, _bridge = _service(tmp_path, config)
    assert (
        cast(list[dict[str, object]], service._config["allocations"])[0]["promised_delivery_at"]
        == "2026-09-12T09:00:00+00:00"
    )

    malformed = _contract_config()
    cast(list[dict[str, object]], malformed["allocations"])[0]["promised_delivery_at"] = "Sep 12"
    with pytest.raises(ValueError, match="promised_delivery_at"):
        DistributorOperations(tmp_path / "bad-contract.sqlite3", malformed, None)


def _pending_remainder_service(tmp_path: Path) -> tuple[DistributorOperations, _Bridge]:
    """Persist the B2/A0 regression state without inventing another physical event."""

    config = _contract_config()
    allocations = cast(list[dict[str, object]], config["allocations"])
    allocations[0]["requested_quantity"] = 24
    allocations[1]["requested_quantity"] = 15
    allocations[1]["minimum_dispatch_quantity"] = 5
    allocations[1]["allow_final_remainder"] = True
    config["pick_tranches"] = [
        {"customer_order": "SO-R4-STANDARD", "lot": "R4-ARRIVAL-20", "quantity": 2}
    ]
    bridge = _Bridge(config)
    service = DistributorOperations(tmp_path / "pending-remainder.sqlite3", config, bridge)
    bridge.state_provider = service._latest_state
    state = service._initial_state()
    lots = cast(list[dict[str, object]], state["lots"])
    lots[0].update({"received": 20, "usable": 2, "held": 0, "status": "USABLE"})
    lots[1].update({"received": 19, "usable": 0, "held": 0, "status": "DISPATCHED"})
    rows = cast(list[dict[str, object]], state["allocations"])
    rows[0]["dispatched"] = 24
    rows[1]["dispatched"] = 13
    service._recompute_allocations(state)
    service._recompute_quantities(state)
    pending_event = _event(
        "pending-remainder-selection",
        "inspection",
        lot="R4-ARRIVAL-20",
        result="PASS",
        scope="WHOLE_LOT",
        metric="visual_check",
        measured=1,
        sample_quantity=1,
        inspection_report_ref="SYN-R4-REMAINDER-INSPECTION",
    )
    state["events"] = [
        {
            "event_id": pending_event["event_id"],
            "type": pending_event["type"],
            "status": "APPLIED",
            "occurred_at": pending_event["occurred_at"],
            "evidence_ref": pending_event["evidence_ref"],
            "synthetic": pending_event["synthetic"],
            "operations": [],
        }
    ]
    plan = service._contract_plan(state)
    state["allocation_decision"] = {
        "status": "PENDING",
        "case_id": config["case_id"],
        "plan_id": plan["plan_id"],
        "state_revision": plan["state_revision"],
        "event_id": pending_event["event_id"],
        "rationale": "The prior selection had incomplete references.",
        "plan": plan,
        "selection": {"plan_id": plan["plan_id"], "rationale": "old", "contract_refs": []},
        "validation_failures": ["EXECUTABLE_CONTRACT_REFS_INVALID"],
    }
    state["alerts"] = [
        {
            "code": "ALLOCATION_SELECTION_PENDING",
            "status": "OPEN",
            "message": (
                "The contract allocation plan was deferred or malformed; "
                "no pick preparation was started."
            ),
            "event_id": pending_event["event_id"],
            "evidence_ref": pending_event["evidence_ref"],
            "synthetic": True,
        }
    ]
    service._db.execute(
        "INSERT INTO distributor_operation_events "
        "(event_id, payload_json, result_json, state_json, recorded_at) VALUES (?, ?, ?, ?, ?)",
        (
            pending_event["event_id"],
            json.dumps(pending_event, sort_keys=True, separators=(",", ":")),
            "{}",
            json.dumps(state, sort_keys=True, separators=(",", ":")),
            pending_event["occurred_at"],
        ),
    )
    return service, bridge


def test_pending_contract_reselection_uses_only_executable_b2_reference_and_replays(
    tmp_path: Path,
) -> None:
    service, bridge = _pending_remainder_service(tmp_path)
    selections: list[Mapping[str, object]] = []

    def selector(plan: Mapping[str, object]) -> Mapping[str, object]:
        selections.append(plan)
        return {
            "plan_id": plan["plan_id"],
            "rationale": "The remaining B quantity is an allowed final remainder.",
            "contract_refs": ["SO-R4-STANDARD"],
        }

    service._allocation_selector = selector
    request = {"retry_id": "retry-remainder-b2", "pending_event_id": "pending-remainder-selection"}
    result = service.retry_pending_allocation(request)

    assert len(selections) == 1
    plan_rows = cast(list[dict[str, object]], selections[0]["rows"])
    priority = next(row for row in plan_rows if row["customer_order"] == "SO-R4-PRIORITY")
    standard = next(row for row in plan_rows if row["customer_order"] == "SO-R4-STANDARD")
    assert priority["remaining_to_dispatch_before_new"] == priority["new_quantity"] == 0
    assert priority["dispatch_candidate"] is False
    assert priority["dispatch_eligibility"] == "NO_DISPATCH_REMAINING"
    assert standard["new_quantity"] == 2
    assert standard["dispatch_eligibility"] == "FINAL_REMAINDER_ALLOWED"
    assert [kind for kind, event_id, _operation in bridge.calls] == ["prepare_pick"]
    assert bridge.calls[0][1] == "retry-remainder-b2"
    assert bridge.calls[0][2]["customer_order"] == "SO-R4-STANDARD"
    retry = cast(list[dict[str, object]], result["allocation_retries"])[-1]
    assert retry["status"] == "APPLIED"
    assert (
        next(
            alert
            for alert in cast(list[dict[str, object]], result["alerts"])
            if alert["code"] == "ALLOCATION_SELECTION_PENDING"
        )["status"]
        == "RESOLVED"
    )

    assert service.retry_pending_allocation(request) == result
    assert [kind for kind, _event_id, _operation in bridge.calls] == ["prepare_pick"]

    handler = cast(Any, object.__new__(DecisionWorkspaceHandler))
    handler.server = SimpleNamespace(distributor_operations=service)
    sent: list[object] = []
    handler._send_json = lambda _status, value: sent.append(value)
    handler._v1_post("/api/v1/distributor-operations/reselect-pending-allocation", request)
    assert cast(dict[str, object], sent[-1])["distributor_operations"] == {**result, "handoffs": []}

    continued = service.record_event(
        _event(
            "picked-after-retry",
            "picked",
            customer_order="SO-R4-STANDARD",
            lot="R4-ARRIVAL-20",
            quantity=2,
            pick_evidence_ref="SYN-R4-PICK-2",
        )
    )
    assert continued["events"][-1]["event_id"] == "picked-after-retry"
    assert continued["events"][-1]["status"] == "APPLIED"
    assert [kind for kind, _event_id, _operation in bridge.calls] == [
        "prepare_pick",
        "submit_pick",
        "submit_delivery_note",
        "create_shipment",
    ]


def test_pending_contract_reselection_keeps_origin_alert_open_when_prepare_is_blocked(
    tmp_path: Path,
) -> None:
    service, bridge = _pending_remainder_service(tmp_path)
    bridge.statuses["prepare_pick"] = "BLOCKED"
    service._allocation_selector = lambda plan: {
        "plan_id": plan["plan_id"],
        "rationale": "The remaining B quantity is an allowed final remainder.",
        "contract_refs": ["SO-R4-STANDARD"],
    }

    result = service.retry_pending_allocation(
        {"retry_id": "retry-remainder-blocked", "pending_event_id": "pending-remainder-selection"}
    )

    retry = cast(list[dict[str, object]], result["allocation_retries"])[-1]
    assert retry["status"] == "BLOCKED"
    assert (
        next(
            alert
            for alert in cast(list[dict[str, object]], result["alerts"])
            if alert["code"] == "ALLOCATION_SELECTION_PENDING"
        )["status"]
        == "OPEN"
    )
    assert (
        service.retry_pending_allocation(
            {
                "retry_id": "retry-remainder-blocked",
                "pending_event_id": "pending-remainder-selection",
            }
        )
        == result
    )
    assert [kind for kind, _event_id, _operation in bridge.calls] == ["prepare_pick"]
