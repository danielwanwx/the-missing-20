"""Plan or provision the narrow synthetic distributor demo scenarios.

Use ``--mode execute --execute`` only after an independent review.  The R4
follow-on never touches the original R4 receipt/invoice.  The component case
creates its own batched Nos item, PO, inspection warehouses and customer orders.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, cast
from urllib.parse import quote, urlencode

ROOT: Final = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from the_missing_20.adapters.demo_executor import (  # noqa: E402
    ERPNextDemoExecutor,
)

COMPANY: Final = "Missing 20 Automotive Demo"
ITEM: Final = "M20-DEMO-CARTON"
PURCHASE_ORDER: Final = "PUR-ORD-2026-00016"
CASE_ID: Final = "M20-DIST-R4-PO16"
MARKER: Final = "M20 DIST R4 PO16 SYNTHETIC"
SALES_RATE: Final = 75.0
CUSTOMER_GROUP: Final = "Demo Customer Group"
TERRITORY: Final = "United States"
ITEM_GROUP: Final = "Demo Item Group"
_ORDER_24: Final = "REQUIRES_PROVISION_CUSTOMER_ORDER_24"
_ORDER_15: Final = "REQUIRES_PROVISION_CUSTOMER_ORDER_15"

COMPONENT_CASE_ID: Final = "M20-DIST-COMPONENT-40"
COMPONENT_MARKER: Final = "M20 DIST COMPONENT 40 SYNTHETIC"
COMPONENT_ITEM: Final = "M20-DIST-COMPONENT-NOS"
COMPONENT_PO_MARKER: Final = f"{COMPONENT_MARKER} PURCHASE ORDER"
COMPONENT_SALES_RATE: Final = 6.0
COMPONENT_UNIT_RATE: Final = 4.0
COMPONENT_QUALITY_PARAMETER: Final = "M20 Distributor Diameter"
COMPONENT_ACCEPTED_WAREHOUSE: Final = "M20 Distributor Component Accepted"
COMPONENT_INSPECTION_WAREHOUSE: Final = "M20 Distributor Component Inspection"
_COMPONENT_ORDER_25: Final = "REQUIRES_PROVISION_COMPONENT_ORDER_25"
_COMPONENT_ORDER_15: Final = "REQUIRES_PROVISION_COMPONENT_ORDER_15"


def _component_identities(instance: str | None) -> dict[str, str]:
    """Return isolated identifiers; the existing fixture remains byte-for-byte unchanged."""

    if instance is None:
        return {
            "case_id": COMPONENT_CASE_ID,
            "marker": COMPONENT_MARKER,
            "po_marker": COMPONENT_PO_MARKER,
            "accepted_warehouse": COMPONENT_ACCEPTED_WAREHOUSE,
            "inspection_warehouse": COMPONENT_INSPECTION_WAREHOUSE,
            "batch_a": "M20-DIST-COMP-BATCH-A",
            "batch_b": "M20-DIST-COMP-BATCH-B",
            "batch_c": "M20-DIST-COMP-BATCH-C",
            "shipment_25": f"{COMPONENT_CASE_ID}-SHIP-25",
            "shipment_15": f"{COMPONENT_CASE_ID}-SHIP-15",
        }
    namespace = instance.strip()
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9-]{0,23}", namespace):
        raise ProvisioningBlocked("instance must be uppercase letters, digits, or hyphens")
    marker = f"M20 DIST COMPONENT {namespace} SYNTHETIC"
    case_id = f"M20-DIST-COMPONENT-{namespace}"
    return {
        "case_id": case_id,
        "marker": marker,
        "po_marker": f"{marker} PURCHASE ORDER",
        "accepted_warehouse": f"M20 Distributor Component {namespace} Accepted",
        "inspection_warehouse": f"M20 Distributor Component {namespace} Inspection",
        "batch_a": f"M20-DIST-COMP-{namespace}-BATCH-A",
        "batch_b": f"M20-DIST-COMP-{namespace}-BATCH-B",
        "batch_c": f"M20-DIST-COMP-{namespace}-BATCH-C",
        "shipment_25": f"{case_id}-SHIP-25",
        "shipment_15": f"{case_id}-SHIP-15",
    }


class ProvisioningBlocked(ValueError):
    """A read or write does not match the one authorized synthetic scope."""


def _request(
    client: ERPNextDemoExecutor, path: str, *, method: str = "GET", payload: object = None
) -> object:
    return client._request(path, method=method, payload=payload)


def _document(client: ERPNextDemoExecutor, doctype: str, name: str) -> Mapping[str, object]:
    document = client._document(doctype, name)
    if not isinstance(document, Mapping):
        raise ProvisioningBlocked(f"ERP returned no {doctype} document")
    return document


def _rows(payload: object) -> list[Mapping[str, object]]:
    if not isinstance(payload, Mapping) or not isinstance(payload.get("data"), list):
        raise ProvisioningBlocked("ERP returned an invalid list response")
    rows = payload["data"]
    if any(not isinstance(row, Mapping) for row in rows):
        raise ProvisioningBlocked("ERP returned an invalid list row")
    return list(rows)


def _required_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ProvisioningBlocked(f"{label} has no stable text value")
    return value


def _find(
    client: ERPNextDemoExecutor, doctype: str, field: str, value: str
) -> list[Mapping[str, object]]:
    query = urlencode(
        {
            "fields": json.dumps(["name", "docstatus"]),
            "filters": json.dumps([[field, "=", value]]),
            "limit_page_length": "3",
            "order_by": "creation asc",
        }
    )
    rows = _rows(_request(client, f"/api/resource/{quote(doctype, safe='')}?{query}"))
    if len(rows) >= 3:
        raise ProvisioningBlocked(f"{doctype} discovery is incomplete")
    names = [row.get("name") for row in rows]
    if any(not isinstance(name, str) or not name for name in names):
        raise ProvisioningBlocked(f"{doctype} discovery has no stable name")
    return [_document(client, doctype, str(name)) for name in names]


def _single_or_create(
    client: ERPNextDemoExecutor,
    *,
    doctype: str,
    lookup_field: str,
    lookup_value: str,
    payload: Mapping[str, object],
    verify: Callable[[Mapping[str, object]], bool],
) -> Mapping[str, object]:
    existing = _find(client, doctype, lookup_field, lookup_value)
    if len(existing) > 1:
        raise ProvisioningBlocked(f"ambiguous existing {doctype}")
    if existing:
        if not verify(existing[0]):
            raise ProvisioningBlocked(f"existing {doctype} does not match synthetic scope")
        return existing[0]
    response = _request(
        client, f"/api/resource/{quote(doctype, safe='')}", method="POST", payload=dict(payload)
    )
    if not isinstance(response, Mapping) or not isinstance(response.get("data"), Mapping):
        raise ProvisioningBlocked(f"unknown {doctype} insert outcome; inspect before rerun")
    created = response["data"]
    name = created.get("name")
    if not isinstance(name, str) or not name:
        raise ProvisioningBlocked(f"unknown {doctype} insert identity; inspect before rerun")
    reread = _document(client, doctype, name)
    if not verify(reread):
        raise ProvisioningBlocked(f"created {doctype} does not match synthetic scope")
    return reread


def _submit(client: ERPNextDemoExecutor, document: Mapping[str, object]) -> Mapping[str, object]:
    response = _request(
        client, "/api/method/frappe.client.submit", method="POST", payload={"doc": dict(document)}
    )
    if not isinstance(response, Mapping) or not isinstance(response.get("message"), Mapping):
        raise ProvisioningBlocked("unknown submission outcome; inspect before rerun")
    name = response["message"].get("name")
    doctype = document.get("doctype")
    if not isinstance(name, str) or not name or not isinstance(doctype, str) or not doctype:
        raise ProvisioningBlocked("submitted document has no identity")
    reread = _document(client, doctype, name)
    if reread.get("docstatus") != 1:
        raise ProvisioningBlocked("submitted document did not remain submitted")
    return reread


def _po_line(client: ERPNextDemoExecutor) -> tuple[Mapping[str, object], Mapping[str, object]]:
    order = _document(client, "Purchase Order", PURCHASE_ORDER)
    if order.get("docstatus") != 1 or order.get("company") != COMPANY:
        raise ProvisioningBlocked("PO16 is not the expected submitted M20 company scope")
    items = order.get("items")
    if not isinstance(items, list):
        raise ProvisioningBlocked("PO16 has no item rows")
    lines = [
        row
        for row in items
        if isinstance(row, Mapping)
        and row.get("item_code") == ITEM
        and row.get("qty") == 40
        and row.get("uom") == "Box"
        and row.get("stock_uom") == "Box"
        and row.get("conversion_factor") == 1
    ]
    if len(lines) != 1 or not isinstance(lines[0].get("name"), str):
        raise ProvisioningBlocked("PO16 does not have one exact Box=1 line")
    if float(lines[0].get("received_qty") or 0) < 1:
        raise ProvisioningBlocked("PO16 no longer retains the original one-Box receipt")
    return order, lines[0]


def _plan(po_item: Mapping[str, object], *, supplier: str, date: str) -> dict[str, object]:
    """Return the intended runtime config without a write or unverified identifier."""

    return {
        "case_id": CASE_ID,
        "case_label": "Synthetic R4 PO16 remaining-39 distributor follow-on",
        "synthetic_input": True,
        "company": COMPANY,
        "supplier": supplier,
        "item_code": ITEM,
        "uom": "Box",
        "stock_uom": "Box",
        "expected_pack_quantity": 1,
        "cartons": 39,
        "purchase_order": PURCHASE_ORDER,
        "purchase_order_item": po_item["name"],
        "marker": MARKER,
        "currency": "USD",
        "unit_rate": 50,
        "warehouses": {
            "accepted": "M20 Distributor R4 Accepted - M20",
            "quarantine": "M20 Distributor R4 Inspection - M20",
        },
        "receipt_plans": [
            {
                "lot": "R4-ARRIVAL-20",
                "marker": f"{MARKER} ARRIVAL 20",
                "quantity": 20,
                "cartons": 20,
                "expected_pack_quantity": 1,
                "warehouse": "M20 Distributor R4 Accepted - M20",
            },
            {
                "lot": "R4-ARRIVAL-19",
                "marker": f"{MARKER} ARRIVAL 19",
                "quantity": 19,
                "cartons": 19,
                "expected_pack_quantity": 1,
                "warehouse": "M20 Distributor R4 Accepted - M20",
            },
        ],
        "lots": [
            {"lot": "R4-ARRIVAL-20", "expected_quantity": 20, "cartons": 20},
            {"lot": "R4-ARRIVAL-19", "expected_quantity": 19, "cartons": 19},
        ],
        "allocations": [
            {"customer_order": _ORDER_24, "requested_quantity": 24, "priority": 1},
            {"customer_order": _ORDER_15, "requested_quantity": 15, "priority": 2},
        ],
        "customer_orders": [_ORDER_24, _ORDER_15],
        "pick_tranches": [
            {"customer_order": _ORDER_24, "lot": "R4-ARRIVAL-20", "quantity": 20},
            {"customer_order": _ORDER_24, "lot": "R4-ARRIVAL-19", "quantity": 4},
            {"customer_order": _ORDER_15, "lot": "R4-ARRIVAL-19", "quantity": 15},
        ],
        "policy": {"inspection_required": False, "reservation_supported": False},
        "shipping": {
            "native_read_enabled": True,
            "shipments": {
                _ORDER_24: {
                    "shipment_id_prefix": f"{CASE_ID}-SHIP-24",
                    "pickup_address": "REQUIRES_PROVISION_PICKUP_ADDRESS",
                    "delivery_address": "REQUIRES_PROVISION_DELIVERY_ADDRESS_24",
                    "pickup_date": date,
                    "pickup_from": "09:00:00",
                    "pickup_to": "17:00:00",
                    "parcel_weight": 1,
                },
                _ORDER_15: {
                    "shipment_id_prefix": f"{CASE_ID}-SHIP-15",
                    "pickup_address": "REQUIRES_PROVISION_PICKUP_ADDRESS",
                    "delivery_address": "REQUIRES_PROVISION_DELIVERY_ADDRESS_15",
                    "pickup_date": date,
                    "pickup_from": "09:00:00",
                    "pickup_to": "17:00:00",
                    "parcel_weight": 1,
                },
            },
        },
    }


def _component_plan(
    *,
    supplier: str,
    date: str,
    purchase_order: str,
    purchase_order_item: str,
    instance: str | None = None,
) -> dict[str, object]:
    """Return the isolated batch-and-quality runtime config without a write."""

    identities = _component_identities(instance)
    accepted_warehouse = (
        "REQUIRES_PROVISION_COMPONENT_ACCEPTED_WAREHOUSE"
        if instance is None
        else identities["accepted_warehouse"]
    )
    inspection_warehouse = (
        "REQUIRES_PROVISION_COMPONENT_INSPECTION_WAREHOUSE"
        if instance is None
        else identities["inspection_warehouse"]
    )
    allocations: list[dict[str, object]] = [
        {"customer_order": _COMPONENT_ORDER_25, "requested_quantity": 25, "priority": 1},
        {"customer_order": _COMPONENT_ORDER_15, "requested_quantity": 15, "priority": 2},
    ]
    if instance is not None:
        allocations = [
            {
                "customer_order": _COMPONENT_ORDER_25,
                "requested_quantity": 25,
                "priority": 2,
                "promised_delivery_at": "2026-09-11T09:00:00+00:00",
                "customer_priority": 2,
                "partial_dispatch": True,
                "minimum_dispatch_quantity": 10,
                "allow_final_remainder": True,
            },
            {
                "customer_order": _COMPONENT_ORDER_15,
                "requested_quantity": 15,
                "priority": 1,
                "promised_delivery_at": "2026-09-12T09:00:00+00:00",
                "customer_priority": 1,
                "partial_dispatch": True,
                "minimum_dispatch_quantity": 5,
                "allow_final_remainder": True,
            },
        ]
    return {
        "case_id": identities["case_id"],
        "case_label": "Synthetic component count, inspection and release",
        "synthetic_input": True,
        "company": COMPANY,
        "supplier": supplier,
        "item_code": COMPONENT_ITEM,
        "uom": "Nos",
        "stock_uom": "Nos",
        "expected_pack_quantity": 10,
        "cartons": 5,
        "purchase_order": purchase_order,
        "purchase_order_item": purchase_order_item,
        "marker": identities["marker"],
        "currency": "USD",
        "unit_rate": COMPONENT_UNIT_RATE,
        "warehouses": {
            "accepted": accepted_warehouse,
            "quarantine": inspection_warehouse,
        },
        "receipt_plans": [
            {
                "lot": "LOT-A",
                "marker": f"{identities['marker']} LOT-A",
                "quantity": 20,
                "cartons": 2,
                "expected_pack_quantity": 10,
                "warehouse": inspection_warehouse,
                "batch_no": identities["batch_a"],
            },
            {
                "lot": "LOT-B",
                "marker": f"{identities['marker']} LOT-B",
                "quantity": 18,
                "cartons": 2,
                "expected_pack_quantity": 10,
                "warehouse": inspection_warehouse,
                "batch_no": identities["batch_b"],
            },
            {
                "lot": "LOT-C",
                "marker": f"{identities['marker']} LOT-C REPLACEMENT",
                "quantity": 2,
                "cartons": 1,
                "expected_pack_quantity": 2,
                "warehouse": inspection_warehouse,
                "batch_no": identities["batch_c"],
            },
        ],
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
        "allocations": allocations,
        "customer_orders": [_COMPONENT_ORDER_25, _COMPONENT_ORDER_15],
        **({"allocation_policy": {"version": "v1"}} if instance is not None else {}),
        "pick_tranches": [
            {"customer_order": _COMPONENT_ORDER_25, "lot": "LOT-A", "quantity": 20},
            {"customer_order": _COMPONENT_ORDER_25, "lot": "LOT-B", "quantity": 5},
            {"customer_order": _COMPONENT_ORDER_15, "lot": "LOT-B", "quantity": 13},
            {"customer_order": _COMPONENT_ORDER_15, "lot": "LOT-C", "quantity": 2},
        ],
        "policy": {
            "inspection_required": True,
            "reservation_supported": False,
            "inspection_criteria": {"diameter_mm": {"minimum": 9.9, "maximum": 10.1}},
        },
        "quality_parameters": {"diameter_mm": COMPONENT_QUALITY_PARAMETER},
        "shipping": {
            "native_read_enabled": True,
            "shipments": {
                _COMPONENT_ORDER_25: {
                    "shipment_id_prefix": identities["shipment_25"],
                    "pickup_address": "REQUIRES_PROVISION_COMPONENT_PICKUP_ADDRESS",
                    "delivery_address": "REQUIRES_PROVISION_COMPONENT_DELIVERY_ADDRESS_25",
                    "pickup_date": date,
                    "pickup_from": "09:00:00",
                    "pickup_to": "17:00:00",
                    "parcel_weight": 1,
                },
                _COMPONENT_ORDER_15: {
                    "shipment_id_prefix": identities["shipment_15"],
                    "pickup_address": "REQUIRES_PROVISION_COMPONENT_PICKUP_ADDRESS",
                    "delivery_address": "REQUIRES_PROVISION_COMPONENT_DELIVERY_ADDRESS_15",
                    "pickup_date": date,
                    "pickup_from": "09:00:00",
                    "pickup_to": "17:00:00",
                    "parcel_weight": 1,
                },
            },
        },
    }


def _warehouse(client: ERPNextDemoExecutor, *, name: str) -> Mapping[str, object]:
    return _single_or_create(
        client,
        doctype="Warehouse",
        lookup_field="warehouse_name",
        lookup_value=name,
        payload={
            "doctype": "Warehouse",
            "warehouse_name": name,
            "company": COMPANY,
            "is_group": 0,
        },
        verify=lambda document: (
            document.get("warehouse_name") == name
            and document.get("company") == COMPANY
            and document.get("is_group") in (0, False)
        ),
    )


def _customer(client: ERPNextDemoExecutor, *, name: str) -> Mapping[str, object]:
    return _single_or_create(
        client,
        doctype="Customer",
        lookup_field="customer_name",
        lookup_value=name,
        payload={
            "doctype": "Customer",
            "customer_name": name,
            "customer_type": "Company",
            "customer_group": CUSTOMER_GROUP,
            "territory": TERRITORY,
        },
        verify=lambda document: (
            document.get("customer_name") == name
            and document.get("customer_group") == CUSTOMER_GROUP
            and document.get("territory") == TERRITORY
            and document.get("disabled") in (0, False, None)
        ),
    )


def _component_item(client: ERPNextDemoExecutor) -> Mapping[str, object]:
    return _single_or_create(
        client,
        doctype="Item",
        lookup_field="item_code",
        lookup_value=COMPONENT_ITEM,
        payload={
            "doctype": "Item",
            "item_code": COMPONENT_ITEM,
            "item_name": "M20 synthetic batched component",
            "description": (
                f"{COMPONENT_MARKER}; inbound stock is held in the inspection warehouse "
                "until a native whole-lot quality release."
            ),
            "item_group": ITEM_GROUP,
            "stock_uom": "Nos",
            "is_stock_item": 1,
            "is_purchase_item": 1,
            "is_sales_item": 1,
            "has_batch_no": 1,
            "create_new_batch": 0,
            "inspection_required_before_purchase": 0,
            "inspection_required_before_delivery": 0,
        },
        verify=lambda document: (
            document.get("item_code") == COMPONENT_ITEM
            and document.get("item_group") == ITEM_GROUP
            and document.get("stock_uom") == "Nos"
            and document.get("is_stock_item") in (1, True)
            and document.get("is_purchase_item") in (1, True)
            and document.get("is_sales_item") in (1, True)
            and document.get("has_batch_no") in (1, True)
            and document.get("create_new_batch") in (0, False, None)
            and document.get("inspection_required_before_purchase") in (0, False, None)
            and document.get("inspection_required_before_delivery") in (0, False, None)
        ),
    )


def _component_batch(
    client: ERPNextDemoExecutor, *, batch_id: str, item_code: str, description: str, date: str
) -> Mapping[str, object]:
    return _single_or_create(
        client,
        doctype="Batch",
        lookup_field="batch_id",
        lookup_value=batch_id,
        payload={
            "doctype": "Batch",
            "batch_id": batch_id,
            "item": item_code,
            "manufacturing_date": date,
            "description": description,
        },
        verify=lambda document: (
            document.get("batch_id") == batch_id
            and document.get("item") == item_code
            and document.get("disabled") in (0, False, None)
        ),
    )


def _component_quality_parameter(client: ERPNextDemoExecutor) -> Mapping[str, object]:
    return _single_or_create(
        client,
        doctype="Quality Inspection Parameter",
        lookup_field="parameter",
        lookup_value=COMPONENT_QUALITY_PARAMETER,
        payload={
            "doctype": "Quality Inspection Parameter",
            "parameter": COMPONENT_QUALITY_PARAMETER,
            "description": "Synthetic component diameter in millimetres for the M20 demo.",
        },
        verify=lambda document: document.get("parameter") == COMPONENT_QUALITY_PARAMETER,
    )


def _address(
    client: ERPNextDemoExecutor, *, title: str, link_doctype: str, link_name: str
) -> Mapping[str, object]:
    return _single_or_create(
        client,
        doctype="Address",
        lookup_field="address_title",
        lookup_value=title,
        payload={
            "doctype": "Address",
            "address_title": title,
            "address_type": "Shipping",
            "address_line1": "Synthetic M20 distributor demonstration address",
            "city": "San Francisco",
            "country": "United States",
            "links": [{"link_doctype": link_doctype, "link_name": link_name}],
        },
        verify=lambda document: document.get("address_title") == title,
    )


def _contact(
    client: ERPNextDemoExecutor, *, first_name: str, customer_name: str, email: str
) -> Mapping[str, object]:
    return _single_or_create(
        client,
        doctype="Contact",
        lookup_field="first_name",
        lookup_value=first_name,
        payload={
            "doctype": "Contact",
            "first_name": first_name,
            "email_ids": [{"email_id": email, "is_primary": 1}],
            "links": [{"link_doctype": "Customer", "link_name": customer_name}],
        },
        verify=lambda document: (
            document.get("first_name") == first_name
            and _contact_links_customer(document, customer_name)
        ),
    )


def _contact_links_customer(document: Mapping[str, object], customer_name: str) -> bool:
    links = document.get("links")
    return isinstance(links, list) and any(
        isinstance(link, Mapping)
        and link.get("link_doctype") == "Customer"
        and link.get("link_name") == customer_name
        for link in links
    )


def _sales_order(
    client: ERPNextDemoExecutor,
    *,
    customer: Mapping[str, object],
    warehouse: str,
    quantity: int,
    priority: int,
    date: str,
    item_code: str = ITEM,
    uom: str = "Box",
    marker_prefix: str = MARKER,
    unit_rate: float = SALES_RATE,
    delivery_date: str | None = None,
) -> Mapping[str, object]:
    customer_name = customer.get("name")
    if not isinstance(customer_name, str) or not customer_name:
        raise ProvisioningBlocked("customer has no stable ERP identity")
    marker = f"{marker_prefix} CUSTOMER-{priority}"
    promised_date = delivery_date or date

    def matches(document: Mapping[str, object]) -> bool:
        items = document.get("items")
        return (
            document.get("company") == COMPANY
            and document.get("customer") == customer_name
            and document.get("po_no") == marker
            and (delivery_date is None or document.get("delivery_date") == delivery_date)
            and isinstance(items, list)
            and len(items) == 1
            and isinstance(items[0], Mapping)
            and items[0].get("item_code") == item_code
            and items[0].get("qty") == quantity
            and items[0].get("uom") == uom
            and items[0].get("stock_uom") == uom
            and items[0].get("conversion_factor") == 1
            and items[0].get("warehouse") == warehouse
            and items[0].get("rate") == unit_rate
            and (delivery_date is None or items[0].get("delivery_date") == delivery_date)
        )

    document = _single_or_create(
        client,
        doctype="Sales Order",
        lookup_field="po_no",
        lookup_value=marker,
        payload={
            "doctype": "Sales Order",
            "company": COMPANY,
            "customer": customer_name,
            "transaction_date": date,
            "delivery_date": promised_date,
            "currency": "USD",
            "selling_price_list": "Standard Selling",
            "conversion_rate": 1,
            "plc_conversion_rate": 1,
            "po_no": marker,
            "items": [
                {
                    "item_code": item_code,
                    "description": marker,
                    "qty": quantity,
                    "uom": uom,
                    "stock_uom": uom,
                    "conversion_factor": 1,
                    "warehouse": warehouse,
                    "rate": unit_rate,
                    "delivery_date": promised_date,
                }
            ],
        },
        verify=matches,
    )
    return _submit(client, document) if document.get("docstatus") == 0 else document


def _component_purchase_order(
    client: ERPNextDemoExecutor,
    *,
    supplier: str,
    inspection_warehouse: str,
    date: str,
    instance: str | None = None,
) -> tuple[Mapping[str, object], Mapping[str, object]]:
    """Create or verify the one explicitly marked component PO.

    The deployed tenant does not expose a reliable PO remarks field, so parent
    discovery is bounded by the exact instance marker.  Other historical or
    differently namespaced component POs are not candidates.
    """

    po_marker = _component_identities(instance)["po_marker"]

    def candidates() -> list[Mapping[str, object]]:
        query = urlencode(
            {
                "fields": json.dumps(["name", "docstatus"]),
                "filters": json.dumps([["company", "=", COMPANY], ["supplier", "=", supplier]]),
                "limit_page_length": "50",
                "order_by": "creation asc",
            }
        )
        rows = _rows(_request(client, f"/api/resource/Purchase%20Order?{query}"))
        if len(rows) >= 50:
            raise ProvisioningBlocked("component PO discovery is incomplete")
        documents = [
            _document(client, "Purchase Order", _required_text(row.get("name"), "component PO row"))
            for row in rows
        ]
        matches: list[Mapping[str, object]] = []
        for document in documents:
            items = document.get("items")
            if not isinstance(items, list):
                raise ProvisioningBlocked("component PO has no item rows")
            component_rows = [
                row
                for row in items
                if isinstance(row, Mapping) and row.get("item_code") == COMPONENT_ITEM
            ]
            marked_rows = [row for row in component_rows if row.get("description") == po_marker]
            if not marked_rows:
                continue
            if len(component_rows) != 1 or len(marked_rows) != 1:
                raise ProvisioningBlocked("component PO has malformed exact instance marker rows")
            matches.append(document)
        if len(matches) > 1:
            raise ProvisioningBlocked("ambiguous existing component PO")
        return matches

    def line_for(order: Mapping[str, object]) -> Mapping[str, object]:
        items = order.get("items")
        if not isinstance(items, list):
            raise ProvisioningBlocked("component PO has no item rows")
        component_rows = [
            row
            for row in items
            if isinstance(row, Mapping) and row.get("item_code") == COMPONENT_ITEM
        ]
        lines = [row for row in component_rows if row.get("description") == po_marker]
        if len(component_rows) != 1 or len(lines) != 1:
            raise ProvisioningBlocked("component PO does not have one marked item row")
        line = lines[0]
        if (
            order.get("company") != COMPANY
            or order.get("supplier") != supplier
            or order.get("currency") != "USD"
            or line.get("qty") != 40
            or line.get("uom") != "Nos"
            or line.get("stock_uom") != "Nos"
            or line.get("conversion_factor") != 1
            or line.get("rate") != COMPONENT_UNIT_RATE
            or line.get("warehouse") != inspection_warehouse
            or not isinstance(line.get("name"), str)
        ):
            raise ProvisioningBlocked("component PO differs from the authorized fixture")
        return line

    matches = candidates()
    if not matches:
        response = _request(
            client,
            "/api/resource/Purchase%20Order",
            method="POST",
            payload={
                "doctype": "Purchase Order",
                "company": COMPANY,
                "supplier": supplier,
                "currency": "USD",
                "conversion_rate": 1,
                "transaction_date": date,
                "schedule_date": date,
                "items": [
                    {
                        "item_code": COMPONENT_ITEM,
                        "description": po_marker,
                        "qty": 40,
                        "uom": "Nos",
                        "stock_uom": "Nos",
                        "conversion_factor": 1,
                        "rate": COMPONENT_UNIT_RATE,
                        "warehouse": inspection_warehouse,
                        "schedule_date": date,
                    }
                ],
            },
        )
        if not isinstance(response, Mapping) or not isinstance(response.get("data"), Mapping):
            raise ProvisioningBlocked("unknown component PO insert outcome; inspect before rerun")
        matches = candidates()
        if len(matches) != 1:
            raise ProvisioningBlocked("component PO insert could not be uniquely reread")
    order = matches[0]
    if order.get("docstatus") == 2:
        raise ProvisioningBlocked("component PO is cancelled; inspect before a new write")
    line_for(order)
    submitted = _submit(client, order) if order.get("docstatus") == 0 else order
    if submitted.get("docstatus") != 1:
        raise ProvisioningBlocked("component PO is not submitted")
    reread = _document(
        client, "Purchase Order", _required_text(submitted.get("name"), "component PO name")
    )
    return reread, line_for(reread)


def provision_r4(client: ERPNextDemoExecutor, *, date: str) -> dict[str, object]:
    if client._environment != "demo":
        raise ProvisioningBlocked("writes require MISSING20_ENVIRONMENT=demo")
    order, po_item = _po_line(client)
    supplier = order.get("supplier")
    if not isinstance(supplier, str) or not supplier:
        raise ProvisioningBlocked("PO16 has no authoritative supplier")
    config = _plan(po_item, supplier=supplier, date=date)
    accepted = _warehouse(client, name="M20 Distributor R4 Accepted")
    quarantine = _warehouse(client, name="M20 Distributor R4 Inspection")
    accepted_name = accepted.get("name")
    quarantine_name = quarantine.get("name")
    if not isinstance(accepted_name, str) or not isinstance(quarantine_name, str):
        raise ProvisioningBlocked("warehouse insert has no stable ERP identity")
    config["warehouses"] = {"accepted": accepted_name, "quarantine": quarantine_name}
    plans = cast(list[dict[str, object]], config["receipt_plans"])
    for plan in plans:
        plan["warehouse"] = accepted_name
    customer_24 = _customer(client, name="M20 Distributor Customer 24")
    customer_15 = _customer(client, name="M20 Distributor Customer 15")
    order_24 = _sales_order(
        client,
        customer=customer_24,
        warehouse=accepted_name,
        quantity=24,
        priority=1,
        date=date,
    )
    order_15 = _sales_order(
        client,
        customer=customer_15,
        warehouse=accepted_name,
        quantity=15,
        priority=2,
        date=date,
    )
    customer_24_name = customer_24.get("name")
    customer_15_name = customer_15.get("name")
    order_24_name = order_24.get("name")
    order_15_name = order_15.get("name")
    if not all(
        isinstance(value, str) and value
        for value in (customer_24_name, customer_15_name, order_24_name, order_15_name)
    ):
        raise ProvisioningBlocked("synthetic customer/order has no stable ERP identity")
    pickup = _address(
        client, title="M20 Distributor R4 Pickup", link_doctype="Company", link_name=COMPANY
    )
    delivery_24 = _address(
        client,
        title="M20 Distributor R4 Customer 24",
        link_doctype="Customer",
        link_name=str(customer_24_name),
    )
    delivery_15 = _address(
        client,
        title="M20 Distributor R4 Customer 15",
        link_doctype="Customer",
        link_name=str(customer_15_name),
    )
    contact_24 = _contact(
        client,
        first_name="M20 Distributor R4 Contact 24",
        customer_name=str(customer_24_name),
        email="m20-distributor-r4-24@example.invalid",
    )
    contact_15 = _contact(
        client,
        first_name="M20 Distributor R4 Contact 15",
        customer_name=str(customer_15_name),
        email="m20-distributor-r4-15@example.invalid",
    )
    if not all(
        isinstance(document.get("name"), str) and document["name"]
        for document in (pickup, delivery_24, delivery_15, contact_24, contact_15)
    ):
        raise ProvisioningBlocked("synthetic address/contact has no stable ERP identity")
    config["allocations"] = [
        {"customer_order": order_24_name, "requested_quantity": 24, "priority": 1},
        {"customer_order": order_15_name, "requested_quantity": 15, "priority": 2},
    ]
    config["customer_orders"] = [order_24_name, order_15_name]
    config["pick_tranches"] = [
        {"customer_order": order_24_name, "lot": "R4-ARRIVAL-20", "quantity": 20},
        {"customer_order": order_24_name, "lot": "R4-ARRIVAL-19", "quantity": 4},
        {"customer_order": order_15_name, "lot": "R4-ARRIVAL-19", "quantity": 15},
    ]
    shipping = cast(Mapping[str, object], config["shipping"])
    config["shipping"] = {
        "native_read_enabled": shipping["native_read_enabled"],
        "shipments": {
            order_24_name: {
                "shipment_id_prefix": f"{CASE_ID}-SHIP-24",
                "pickup_address": pickup["name"],
                "delivery_address": delivery_24["name"],
                "delivery_contact": contact_24["name"],
                "pickup_date": date,
                "pickup_from": "09:00:00",
                "pickup_to": "17:00:00",
                "parcel_weight": 1,
            },
            order_15_name: {
                "shipment_id_prefix": f"{CASE_ID}-SHIP-15",
                "pickup_address": pickup["name"],
                "delivery_address": delivery_15["name"],
                "delivery_contact": contact_15["name"],
                "pickup_date": date,
                "pickup_from": "09:00:00",
                "pickup_to": "17:00:00",
                "parcel_weight": 1,
            },
        },
    }
    return config


def provision_component(
    client: ERPNextDemoExecutor, *, date: str, instance: str | None = None
) -> dict[str, object]:
    """Provision the isolated batched component case and return its exact config."""

    if client._environment != "demo":
        raise ProvisioningBlocked("writes require MISSING20_ENVIRONMENT=demo")
    reference_order, _ = _po_line(client)
    supplier = _required_text(reference_order.get("supplier"), "PO16 supplier")
    identities = _component_identities(instance)

    item = _component_item(client)
    item_name = _required_text(item.get("name"), "component item")
    accepted = _warehouse(client, name=identities["accepted_warehouse"])
    inspection = _warehouse(client, name=identities["inspection_warehouse"])
    accepted_name = _required_text(accepted.get("name"), "component accepted warehouse")
    inspection_name = _required_text(inspection.get("name"), "component inspection warehouse")
    parameter = _component_quality_parameter(client)
    if parameter.get("parameter") != COMPONENT_QUALITY_PARAMETER:
        raise ProvisioningBlocked(
            "component quality parameter does not match the configured metric"
        )
    batches = {
        lot: _component_batch(
            client,
            batch_id=batch_id,
            item_code=item_name,
            description=f"{identities['marker']} {lot}",
            date=date,
        )
        for lot, batch_id in {
            "LOT-A": identities["batch_a"],
            "LOT-B": identities["batch_b"],
            "LOT-C": identities["batch_c"],
        }.items()
    }
    batch_names = {
        lot: _required_text(batch.get("name"), f"component {lot} batch")
        for lot, batch in batches.items()
    }
    purchase_order, po_item = _component_purchase_order(
        client,
        supplier=supplier,
        inspection_warehouse=inspection_name,
        date=date,
        instance=instance,
    )
    config = _component_plan(
        supplier=supplier,
        date=date,
        purchase_order=_required_text(purchase_order.get("name"), "component PO"),
        purchase_order_item=_required_text(po_item.get("name"), "component PO item"),
        instance=instance,
    )
    config["warehouses"] = {"accepted": accepted_name, "quarantine": inspection_name}
    plans = cast(list[dict[str, object]], config["receipt_plans"])
    for plan in plans:
        lot = _required_text(plan.get("lot"), "component receipt plan lot")
        plan["warehouse"] = inspection_name
        plan["batch_no"] = batch_names[lot]

    customer_25 = _customer(client, name="M20 Component Customer 25")
    customer_15 = _customer(client, name="M20 Component Customer 15")
    order_25 = _sales_order(
        client,
        customer=customer_25,
        warehouse=accepted_name,
        quantity=25,
        priority=2 if instance is not None else 1,
        date=date,
        item_code=item_name,
        uom="Nos",
        marker_prefix=identities["marker"],
        unit_rate=COMPONENT_SALES_RATE,
        delivery_date="2026-09-11" if instance is not None else None,
    )
    order_15 = _sales_order(
        client,
        customer=customer_15,
        warehouse=accepted_name,
        quantity=15,
        priority=1 if instance is not None else 2,
        date=date,
        item_code=item_name,
        uom="Nos",
        marker_prefix=identities["marker"],
        unit_rate=COMPONENT_SALES_RATE,
        delivery_date="2026-09-12" if instance is not None else None,
    )
    customer_25_name = _required_text(customer_25.get("name"), "component customer 25")
    customer_15_name = _required_text(customer_15.get("name"), "component customer 15")
    order_25_name = _required_text(order_25.get("name"), "component order 25")
    order_15_name = _required_text(order_15.get("name"), "component order 15")
    pickup = _address(
        client,
        title="M20 Component Pickup",
        link_doctype="Company",
        link_name=COMPANY,
    )
    delivery_25 = _address(
        client,
        title="M20 Component Customer 25",
        link_doctype="Customer",
        link_name=customer_25_name,
    )
    delivery_15 = _address(
        client,
        title="M20 Component Customer 15",
        link_doctype="Customer",
        link_name=customer_15_name,
    )
    contact_25 = _contact(
        client,
        first_name="M20 Component Contact 25",
        customer_name=customer_25_name,
        email="m20-component-25@example.invalid",
    )
    contact_15 = _contact(
        client,
        first_name="M20 Component Contact 15",
        customer_name=customer_15_name,
        email="m20-component-15@example.invalid",
    )
    pickup_name = _required_text(pickup.get("name"), "component pickup address")
    delivery_25_name = _required_text(delivery_25.get("name"), "component delivery 25 address")
    delivery_15_name = _required_text(delivery_15.get("name"), "component delivery 15 address")
    contact_25_name = _required_text(contact_25.get("name"), "component contact 25")
    contact_15_name = _required_text(contact_15.get("name"), "component contact 15")
    allocation_templates = cast(list[Mapping[str, object]], config["allocations"])
    config["allocations"] = [
        {**dict(allocation_templates[0]), "customer_order": order_25_name},
        {**dict(allocation_templates[1]), "customer_order": order_15_name},
    ]
    config["customer_orders"] = [order_25_name, order_15_name]
    config["pick_tranches"] = [
        {"customer_order": order_25_name, "lot": "LOT-A", "quantity": 20},
        {"customer_order": order_25_name, "lot": "LOT-B", "quantity": 5},
        {"customer_order": order_15_name, "lot": "LOT-B", "quantity": 13},
        {"customer_order": order_15_name, "lot": "LOT-C", "quantity": 2},
    ]
    config["shipping"] = {
        "native_read_enabled": True,
        "shipments": {
            order_25_name: {
                "shipment_id_prefix": identities["shipment_25"],
                "pickup_address": pickup_name,
                "delivery_address": delivery_25_name,
                "delivery_contact": contact_25_name,
                "pickup_date": date,
                "pickup_from": "09:00:00",
                "pickup_to": "17:00:00",
                "parcel_weight": 1,
            },
            order_15_name: {
                "shipment_id_prefix": identities["shipment_15"],
                "pickup_address": pickup_name,
                "delivery_address": delivery_15_name,
                "delivery_contact": contact_15_name,
                "pickup_date": date,
                "pickup_from": "09:00:00",
                "pickup_to": "17:00:00",
                "parcel_weight": 1,
            },
        },
    }
    return config


def _write_private(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
    except Exception:
        os.close(descriptor)
        raise
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("dry", "read", "execute"), default="dry")
    parser.add_argument(
        "--scenario",
        choices=("r4-follow-on", "component-quality"),
        default="r4-follow-on",
    )
    parser.add_argument(
        "--execute", action="store_true", help="required together with --mode execute"
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--date", required=True, help="ERP business date, YYYY-MM-DD")
    parser.add_argument(
        "--instance",
        help="uppercase fresh component namespace; component-quality only",
    )
    args = parser.parse_args()
    datetime.fromisoformat(f"{args.date}T00:00:00+00:00")
    if args.mode == "execute" and not args.execute:
        raise ProvisioningBlocked("--mode execute requires explicit --execute")
    if args.execute and args.mode != "execute":
        raise ProvisioningBlocked("--execute is valid only with --mode execute")
    if args.instance is not None and args.scenario != "component-quality":
        raise ProvisioningBlocked("--instance is valid only with --scenario component-quality")
    if args.mode == "dry":
        if args.scenario == "r4-follow-on":
            template = _plan(
                {"name": "REQUIRES_READ_PO16_ITEM"},
                supplier="REQUIRES_READ_PO16_SUPPLIER",
                date=args.date,
            )
            unresolved_source_fields = ["supplier", "purchase_order_item"]
        else:
            template = _component_plan(
                supplier="REQUIRES_READ_PO16_SUPPLIER",
                date=args.date,
                purchase_order="REQUIRES_PROVISION_COMPONENT_PURCHASE_ORDER",
                purchase_order_item="REQUIRES_PROVISION_COMPONENT_PURCHASE_ORDER_ITEM",
                instance=args.instance,
            )
            unresolved_source_fields = ["supplier"]
        value: dict[str, object] = {
            "mode": "dry",
            "write_authorized": False,
            "scenario": args.scenario,
            "config_template": template,
            "unresolved_source_fields": unresolved_source_fields,
            "unresolved_provisioned_fields": [
                "warehouses",
                "purchase_order",
                "customer_orders",
                "shipping.shipments",
            ],
            "note": "No credentials or ERP reads were used; run --mode read before --execute.",
        }
    else:
        client = ERPNextDemoExecutor.from_environment(ROOT)
        if client is None:
            raise ProvisioningBlocked("demo ERP credentials are not configured")
        if args.mode == "read":
            order, po_item = _po_line(client)
            supplier = order.get("supplier")
            if not isinstance(supplier, str) or not supplier:
                raise ProvisioningBlocked("PO16 has no authoritative supplier")
            if args.scenario == "r4-follow-on":
                config_plan = _plan(po_item, supplier=supplier, date=args.date)
                purchase_order_item: object = po_item["name"]
            else:
                config_plan = _component_plan(
                    supplier=supplier,
                    date=args.date,
                    purchase_order="REQUIRES_PROVISION_COMPONENT_PURCHASE_ORDER",
                    purchase_order_item="REQUIRES_PROVISION_COMPONENT_PURCHASE_ORDER_ITEM",
                    instance=args.instance,
                )
                purchase_order_item = None
            value = {
                "mode": "read",
                "write_authorized": False,
                "scenario": args.scenario,
                "purchase_order_item": purchase_order_item,
                "config_plan": config_plan,
            }
        else:
            config = (
                provision_r4(client, date=args.date)
                if args.scenario == "r4-follow-on"
                else provision_component(client, date=args.date, instance=args.instance)
            )
            value = {
                "mode": "execute",
                "write_authorized": True,
                "executed_at": datetime.now(UTC).isoformat(),
                "scenario": args.scenario,
                "instance": args.instance,
                "config": config,
            }
    _write_private(args.output, value)
    print(json.dumps({"mode": value["mode"], "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
