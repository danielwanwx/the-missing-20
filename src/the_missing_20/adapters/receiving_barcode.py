"""Read identity and commercial facts; optical observations never post stock."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import quote, urlencode

FORMATS = {"ean_13", "upc_a", "code_128", "qr_code", "manual"}


def validate_code(code: Any, barcode_format: Any) -> str:
    if (
        not isinstance(barcode_format, str)
        or barcode_format not in FORMATS
        or not isinstance(code, str)
    ):
        raise ValueError("Unsupported barcode format.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_. -]{0,99}", code):
        raise ValueError("Use a supported item or handling-unit code, not a URL or GS1 payload.")
    if barcode_format in {"ean_13", "upc_a"}:
        length = 13 if barcode_format == "ean_13" else 12
        if not code.isascii() or not code.isdecimal() or len(code) != length:
            raise ValueError("Invalid product barcode length.")
        total = sum(
            int(digit) * (3 if index % 2 == 0 else 1)
            for index, digit in enumerate(reversed(code[:-1]))
        )
        if (10 - total % 10) % 10 != int(code[-1]):
            raise ValueError("Invalid product barcode checksum.")
    return code


def resolve_barcode(erp: Any, work: Mapping[str, Any], code: str, barcode_format: str) -> dict:
    code = validate_code(code, barcode_format)
    client = erp.client
    if (
        client._credentials.base_url != work["tenant"]
        or erp.purchase_order != work["purchase_order"]
    ):
        raise ValueError("Barcode receiving scope changed.")
    po = client._document("Purchase Order", work["purchase_order"])
    lines = [
        line for line in po.get("items", []) if line.get("name") == work["purchase_order_item"]
    ]
    if (
        po.get("name") != work["purchase_order"]
        or po.get("docstatus") != 1
        or not po.get("modified")
        or len(lines) != 1
    ):
        raise ValueError("A current submitted order line is required.")
    line = lines[0]
    if any(line.get(key) != work[key] for key in ("item_code", "uom", "warehouse")):
        raise ValueError("The barcode task no longer matches its order line.")
    if line.get("stock_uom") != work["uom"] or line.get("conversion_factor") != 1:
        raise ValueError("This receiving flow requires a verified one-to-one stock unit.")
    rate = line.get("rate")
    if (
        isinstance(rate, bool)
        or not isinstance(rate, (float, int))
        or not math.isfinite(rate)
        or rate <= 0
        or not po.get("currency")
    ):
        raise ValueError("Order price or currency is unavailable.")
    item = client._document("Item", work["item_code"])
    if (
        item.get("name") != work["item_code"]
        or item.get("disabled")
        or item.get("stock_uom") != work["uom"]
        or not item.get("modified")
    ):
        raise ValueError("Item master is unavailable or incompatible with receiving.")
    unique_unit = code in work["handling_unit_ids"]
    if not unique_unit:
        matches = [row for row in item.get("barcodes", []) if row.get("barcode") == code]
        if len(matches) != 1 or matches[0].get("uom") != work["uom"]:
            raise ValueError("Barcode does not uniquely match this item and packaging unit.")
        native = client._request(
            "/api/method/erpnext.stock.utils.scan_barcode?" + urlencode({"search_value": code})
        ).get("message")
        if (
            not isinstance(native, Mapping)
            or native.get("item_code") != work["item_code"]
            or native.get("barcode") != code
            or native.get("uom") != work["uom"]
        ):
            raise ValueError("ERP barcode lookup conflicts with the current item mapping.")
    base = work["tenant"]
    return {
        "case_id": work["case_id"],
        "arrival_id": work["arrival_id"],
        "code": code,
        "format": barcode_format,
        "kind": "handling_unit" if unique_unit else "product",
        "item_code": item["name"],
        "item_name": item.get("item_name") or item["name"],
        "item_group": item.get("item_group"),
        "item_version": item["modified"],
        "uom": work["uom"],
        "unit_price": rate,
        "currency": po["currency"],
        "purchase_order": po["name"],
        "purchase_order_item": line["name"],
        "po_version": po["modified"],
        "inventory_changed": False,
        "price_basis": "PURCHASE_ORDER_LINE",
        "item_url": f"{base}/app/item/{quote(item['name'], safe='')}",
        "order_url": f"{base}/app/purchase-order/{quote(po['name'], safe='')}",
        "quantity_basis": "CONFIGURED_UNIQUE_UNIT" if unique_unit else "REQUIRES_PHYSICAL_QUANTITY",
    }
