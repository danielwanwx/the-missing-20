"""Provision one explicitly synthetic 40-carton order in the authorized M20 demo ERP.

No inventory, invoice or payment is created here. Repeated invocations resolve
the same business keys; an uncertain write must be inspected before a rerun.
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Mapping
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from the_missing_20.adapters.demo_executor import ERPNextDemoExecutor

ROOT = Path(__file__).resolve().parents[1]
ITEM = "M20-DEMO-CARTON"
MARKER = "M20 GOODS DEMO 20260908 40 CARTONS - SYNTHETIC TEST ORDER"
REFERENCE_PO = "PUR-ORD-2026-00011"
CASE_ID = "M20-GOODS-20260908-40"


def case_marker(case_id: str) -> str:
    if not isinstance(case_id, str) or not re.fullmatch(
        r"M20-GOODS-\d{8}-40(?:-R[1-9][0-9]?)?", case_id
    ):
        raise ValueError("A pilot case requires M20-GOODS-YYYYMMDD-40 with optional -R1..R99.")
    date.fromisoformat(case_id[10:18])
    return MARKER if case_id == CASE_ID else f"{case_id} - SYNTHETIC TEST ORDER"


def _batch_plan(first: int, additional: tuple[int, ...]) -> tuple[int, ...]:
    if not isinstance(additional, tuple):
        raise ValueError("Additional batch sizes must be an immutable tuple.")
    sizes = (first, *additional)
    if any(type(size) is not int or not 1 <= size <= 20 for size in sizes):
        raise ValueError("Each batch requires 1..20 planned cartons.")
    if len(sizes) > 50 or sum(sizes) > 40:
        raise ValueError("Planned arrival quantities cannot exceed the 40-Box purchase order.")
    return sizes


def first_receiving_manifest(
    order: Mapping[str, Any],
    *,
    first_batch_size: int = 10,
    case_id: str = CASE_ID,
    additional_batch_sizes: tuple[int, ...] = (),
) -> dict[str, Any]:
    """Bind the first normal batch to actual ERP line identity, never a guessed row.

    Later quality/exception batches need their own validated disposition/location.
    This does not mark any handling unit as scanned, delivered or posted.
    """
    marker = case_marker(case_id)
    sizes = _batch_plan(first_batch_size, additional_batch_sizes)
    lines = order.get("items", [])
    if (
        order.get("docstatus") != 1
        or order.get("company") != "Missing 20 Automotive Demo"
        or order.get("currency") != "USD"
        or not order.get("name")
        or len(lines) != 1
    ):
        raise ValueError("Receiving scope requires the verified demo purchase order.")
    line = lines[0]
    expected = {
        "item_code": ITEM,
        "qty": 40,
        "rate": 50,
        "uom": "Box",
        "stock_uom": "Box",
        "conversion_factor": 1,
        "warehouse": "Stores - M20",
        "description": marker,
    }
    if not line.get("name") or any(line.get(key) != value for key, value in expected.items()):
        raise ValueError("Receiving scope requires exact ERP row, unit, conversion and warehouse.")
    arrivals = []
    offset = 0
    for index, size in enumerate(sizes, start=1):
        arrivals.append(
            {
                "arrival_id": f"ARRIVAL-{index:02}",
                "purchase_order_item": line["name"],
                "item_code": ITEM,
                "uom": "Box",
                "warehouse": line["warehouse"],
                "handling_unit_ids": [
                    f"{'M20-CARTON' if case_id == CASE_ID else case_id}-{n:03}"
                    for n in range(offset + 1, offset + size + 1)
                ],
                "origin": "demo_scan",
            }
        )
        offset += size
    return {
        "case_id": case_id,
        "purchase_order": order["name"],
        "arrivals": arrivals,
    }


def provision(
    client: ERPNextDemoExecutor,
    *,
    business_date: str,
    first_batch_size: int = 10,
    case_id: str = CASE_ID,
    additional_batch_sizes: tuple[int, ...] = (),
) -> dict[str, Any]:
    marker = case_marker(case_id)
    # Explicit site business date, not the workstation's UTC calendar day.
    if date.fromisoformat(business_date).isoformat() != business_date:
        raise ValueError("Business date must use YYYY-MM-DD.")
    if date.fromisoformat(case_id[10:18]).isoformat() != business_date:
        raise ValueError("Pilot case date must match the ERP business date.")
    _batch_plan(first_batch_size, additional_batch_sizes)
    if client._environment != "demo":
        raise ValueError("Only the authorized M20 demo environment is allowed.")
    reference = client._document("Purchase Order", REFERENCE_PO)
    if reference.get("company") != "Missing 20 Automotive Demo":
        raise ValueError("Unexpected company: no test records created.")

    def find(doctype: str, field: str, value: str) -> list[dict[str, Any]]:
        query = urlencode(
            {
                "fields": json.dumps(["name", "docstatus"] if doctype != "Item" else ["name"]),
                "filters": json.dumps([[field, "=", value]]),
                "limit_page_length": 2,
            }
        )
        rows = client._request(f"/api/resource/{doctype.replace(' ', '%20')}?{query}").get("data")
        if not isinstance(rows, list) or len(rows) > 1:
            raise ValueError("Ambiguous test business key.")
        return rows

    if not find("Item", "item_code", ITEM):
        client._request(
            "/api/resource/Item",
            method="POST",
            payload={
                "doctype": "Item",
                "item_code": ITEM,
                "item_name": "Demo shipping carton",
                "description": (
                    "Synthetic demo article: the visible carton itself; contents are not inferred."
                ),
                "item_group": "Demo Item Group",
                "stock_uom": "Box",
                "is_stock_item": 1,
                "is_purchase_item": 1,
                "is_sales_item": 1,
            },
        )
    item = client._document("Item", ITEM)
    if item.get("stock_uom") != "Box" or not item.get("is_stock_item"):
        raise ValueError("Existing demo item has incompatible semantics.")

    def find_orders() -> list[dict[str, Any]]:
        # This deployed ERP has no PO remarks field. Bound parent discovery by
        # tenant company/supplier, then verify the dedicated item and stored
        # description. Do not silently miss a truncated result and create twice.
        query = urlencode(
            {
                "fields": json.dumps(["name"]),
                "filters": json.dumps(
                    [
                        ["company", "=", reference["company"]],
                        ["supplier", "=", reference["supplier"]],
                    ]
                ),
                "limit_page_length": 50,
            }
        )
        rows = client._request(f"/api/resource/Purchase%20Order?{query}").get("data")
        if not isinstance(rows, list) or len(rows) >= 50:
            raise ValueError("Demo order discovery is incomplete; inspect before creating.")
        matches = []
        for row in rows:
            document = client._document("Purchase Order", row["name"])
            lines = document.get("items", [])
            if any(line.get("item_code") == ITEM for line in lines):
                description = lines[0].get("description") if len(lines) == 1 else None
                # Other explicitly marked pilot orders are independent work. Never
                # amend, resubmit or reuse their receipts for this case.
                known_other = description == MARKER
                if (
                    not known_other
                    and isinstance(description, str)
                    and description.endswith(" - SYNTHETIC TEST ORDER")
                ):
                    try:
                        other_case = description.removesuffix(" - SYNTHETIC TEST ORDER")
                        known_other = case_marker(other_case) == description
                    except ValueError:
                        known_other = False
                if description != marker and known_other:
                    continue
                if len(lines) != 1 or description != marker:
                    raise ValueError("Dedicated demo item already belongs to unverified work.")
                matches.append(dict(document))
        active = [doc for doc in matches if doc.get("docstatus") != 2]
        cancelled = [doc for doc in matches if doc.get("docstatus") == 2]
        if len(active) > 1 or len(cancelled) > 1:
            raise ValueError("Ambiguous test business key; no additional order is allowed.")
        if active and cancelled and active[0].get("amended_from") != cancelled[0]["name"]:
            raise ValueError("Active order is not the verified amendment.")
        return active or cancelled

    found = find_orders()
    if not found or found[0].get("docstatus") == 2:
        amendment = {"amended_from": found[0]["name"]} if found else {}
        client._request(
            "/api/resource/Purchase%20Order",
            method="POST",
            payload={
                "doctype": "Purchase Order",
                "company": reference["company"],
                "supplier": reference["supplier"],
                "currency": "USD",
                "conversion_rate": 1,
                # Let ERP apply its own Today default, then verify before submit.
                "schedule_date": business_date,
                **amendment,
                "items": [
                    {
                        "item_code": ITEM,
                        "description": marker,
                        "qty": 40,
                        "uom": "Box",
                        "stock_uom": "Box",
                        "conversion_factor": 1,
                        "rate": 50,
                        "warehouse": "Stores - M20",
                        "schedule_date": business_date,
                    }
                ],
            },
        )
        found = find_orders()
        if len(found) != 1:
            raise ValueError("Unknown purchase-order outcome; inspect ERP before retrying.")
    order = client._document("Purchase Order", found[0]["name"])
    lines = order.get("items", [])
    if (
        len(lines) != 1
        or order.get("company") != reference["company"]
        or order.get("supplier") != reference["supplier"]
        or lines[0].get("description") != marker
        or lines[0].get("item_code") != ITEM
        or lines[0].get("qty") != 40
        or lines[0].get("rate") != 50
        or lines[0].get("uom") != "Box"
        or lines[0].get("stock_uom") != "Box"
        or lines[0].get("conversion_factor") != 1
        or lines[0].get("warehouse") != "Stores - M20"
        or order.get("currency") != "USD"
    ):
        raise ValueError("Existing demo order differs from the authorized fixture.")
    if order.get("transaction_date") != business_date:
        raise ValueError("ERP business date differs; inspect for cancellation/amendment first.")
    if order.get("docstatus") == 0:
        client._submit_document(order)
    reread = client._document("Purchase Order", found[0]["name"])
    if (
        reread.get("docstatus") != 1
        or reread.get("supplier") != reference["supplier"]
        or reread.get("transaction_date") != business_date
    ):
        raise ValueError("Demo order submission is not verified.")
    return {
        "case_id": case_id,
        "purchase_order": reread["name"],
        "item_code": ITEM,
        "quantity": 40,
        "uom": "Box",
        "currency": "USD",
        "unit_rate": 50,
        "price_basis": "explicit synthetic demo order, not market price",
        "company": reread["company"],
        "docstatus": 1,
        "inventory_writes": 0,
        "physical_goods": "public photo stand-in until operator supplies physical holdout",
        "verified_at": datetime.now(UTC).isoformat(),
        "receiving_manifest": first_receiving_manifest(
            reread,
            first_batch_size=first_batch_size,
            case_id=case_id,
            additional_batch_sizes=additional_batch_sizes,
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", required=True, choices=["m20-photo-receiving"])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest-output", type=Path)
    parser.add_argument("--first-batch-size", type=int, required=True, choices=range(1, 21))
    parser.add_argument(
        "--next-batch-size",
        action="append",
        type=int,
        default=[],
        choices=range(1, 21),
        help="Preplan another arrival before runtime starts",
    )
    parser.add_argument("--case-id", default=CASE_ID)
    parser.add_argument("--business-date", required=True, help="Verified ERP site date, YYYY-MM-DD")
    args = parser.parse_args()
    client = ERPNextDemoExecutor.from_environment(ROOT)
    if client is None:
        raise ValueError("Demo ERP credentials are not configured.")
    result = provision(
        client,
        business_date=args.business_date,
        first_batch_size=args.first_batch_size,
        case_id=args.case_id,
        additional_batch_sizes=tuple(args.next_batch_size),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    if args.manifest_output:
        args.manifest_output.parent.mkdir(parents=True, exist_ok=True)
        args.manifest_output.write_text(json.dumps(result["receiving_manifest"], indent=2) + "\n")
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
