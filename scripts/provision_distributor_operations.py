"""Plan or provision the narrow synthetic R4 distributor follow-on.

Use ``--mode execute --execute`` only after an independent review.  The script
never touches the original R4 receipt/invoice; it creates a new scoped
warehouse, customers and sales orders for the remaining 39 Box.
"""

from __future__ import annotations

import argparse
import json
import os
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
_ORDER_24: Final = "REQUIRES_PROVISION_CUSTOMER_ORDER_24"
_ORDER_15: Final = "REQUIRES_PROVISION_CUSTOMER_ORDER_15"


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
) -> Mapping[str, object]:
    customer_name = customer.get("name")
    if not isinstance(customer_name, str) or not customer_name:
        raise ProvisioningBlocked("customer has no stable ERP identity")
    marker = f"{MARKER} CUSTOMER-{priority}"

    def matches(document: Mapping[str, object]) -> bool:
        items = document.get("items")
        return (
            document.get("company") == COMPANY
            and document.get("customer") == customer_name
            and document.get("po_no") == marker
            and isinstance(items, list)
            and len(items) == 1
            and isinstance(items[0], Mapping)
            and items[0].get("item_code") == ITEM
            and items[0].get("qty") == quantity
            and items[0].get("uom") == "Box"
            and items[0].get("warehouse") == warehouse
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
            "delivery_date": date,
            "currency": "USD",
            "selling_price_list": "Standard Selling",
            "conversion_rate": 1,
            "plc_conversion_rate": 1,
            "po_no": marker,
            "items": [
                {
                    "item_code": ITEM,
                    "description": marker,
                    "qty": quantity,
                    "uom": "Box",
                    "stock_uom": "Box",
                    "conversion_factor": 1,
                    "warehouse": warehouse,
                    "rate": SALES_RATE,
                    "delivery_date": date,
                }
            ],
        },
        verify=matches,
    )
    return _submit(client, document) if document.get("docstatus") == 0 else document


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
        "--execute", action="store_true", help="required together with --mode execute"
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--date", required=True, help="ERP business date, YYYY-MM-DD")
    args = parser.parse_args()
    datetime.fromisoformat(f"{args.date}T00:00:00+00:00")
    if args.mode == "execute" and not args.execute:
        raise ProvisioningBlocked("--mode execute requires explicit --execute")
    if args.execute and args.mode != "execute":
        raise ProvisioningBlocked("--execute is valid only with --mode execute")
    if args.mode == "dry":
        template = _plan(
            {"name": "REQUIRES_READ_PO16_ITEM"},
            supplier="REQUIRES_READ_PO16_SUPPLIER",
            date=args.date,
        )
        value: dict[str, object] = {
            "mode": "dry",
            "write_authorized": False,
            "scenario": "r4-follow-on",
            "config_template": template,
            "unresolved_source_fields": ["supplier", "purchase_order_item"],
            "unresolved_provisioned_fields": [
                "warehouses",
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
            value = {
                "mode": "read",
                "write_authorized": False,
                "scenario": "r4-follow-on",
                "purchase_order_item": po_item["name"],
                "config_plan": _plan(po_item, supplier=supplier, date=args.date),
            }
        else:
            value = {
                "mode": "execute",
                "write_authorized": True,
                "executed_at": datetime.now(UTC).isoformat(),
                "scenario": "r4-follow-on",
                "config": provision_r4(client, date=args.date),
            }
    _write_private(args.output, value)
    print(json.dumps({"mode": value["mode"], "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
