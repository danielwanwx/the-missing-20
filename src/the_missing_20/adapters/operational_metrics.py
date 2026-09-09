"""Pure, source-backed operational measures; planned work is not a discrepancy.

Document totals describe this case, not the warehouse's entire stock position.
Unknown monetary bases stay null; a submitted invoice is billing, not cash.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

Document = Mapping[str, Any]


def _number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)  # type: ignore[arg-type]
    except (ValueError, TypeError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _items(document: Document) -> list[Document]:
    rows = document.get("items", [])
    return [row for row in rows if isinstance(row, Mapping)] if isinstance(rows, list) else []


def documents(erp: Document, kind: str, *, posted: bool = True) -> list[Document]:
    """Deduplicate source versions before filtering cancelled/draft documents."""
    raw = erp.get("documents", [])
    unique: dict[str, Document] = {}
    for row in raw if isinstance(raw, list) else []:
        if not isinstance(row, Mapping) or row.get("kind") != kind or not row.get("name"):
            continue
        name = str(row["name"])
        previous = unique.get(name)
        if previous is None or str(row.get("modified", "")) >= str(previous.get("modified", "")):
            unique[name] = row
    return [row for row in unique.values() if not posted or _posted(row)]


def _posted(row: Document) -> bool:
    if "docstatus" in row:
        return bool(row["docstatus"] == 1)
    # Older API projections encoded document lifecycle in status alone.
    return str(row.get("status", "")).upper() not in {
        "DRAFT",
        "CANCELLED",
        "CANCELED",
        "NOT_CREATED",
        "MISSING",
        "UNKNOWN",
    }


def _sum(rows: Sequence[Document], field: str) -> float | None:
    values = [_number(row.get(field)) for row in rows]
    if any(value is None for value in values):
        return None
    if field in {"quantity", "received", "accepted", "rejected"} and any(
        row.get("is_return") and value is not None and value > 0
        for row, value in zip(rows, values, strict=True)
    ):
        return None  # ERP returns must carry signed quantities, not inferred direction.
    return sum(value for value in values if value is not None)


def _consensus(values: Sequence[object]) -> str | None:
    if not values or any(not value for value in values):
        return None
    unique = {str(value) for value in values}
    return next(iter(unique)) if len(unique) == 1 else None


def _quantity_basis(rows: Sequence[Document]) -> tuple[str | None, bool]:
    items = [item for row in rows for item in _items(row)]
    if not items:
        # Legacy case projections have homogeneous quantities but no UOM metadata.
        units = [row.get("uom") for row in rows]
        return _consensus(units), len({value for value in units if value}) <= 1
    bases = {(item.get("item_code"), item.get("uom")) for item in items}
    return _consensus([item.get("uom") for item in items]), len(bases) == 1


def _product(left: object, right: object) -> float | None:
    a, b = _number(left), _number(right)
    return a * b if a is not None and b is not None else None


def _percent(numerator: object, denominator: object) -> float | None:
    top, bottom = _number(numerator), _number(denominator)
    return top / bottom * 100 if top is not None and bottom is not None and bottom > 0 else None


def receiving_receipt_conflicts(erp: Document) -> list[str]:
    """Local submission proof must be reflected by the aggregate ERP snapshot."""
    work = erp.get("receiving_work")
    if not isinstance(work, Mapping) or work.get("case_id") != erp.get("case_id"):
        return []
    posted = {row["name"]: row for row in documents(erp, "purchase_receipt")}
    conflicts = []
    for arrival in work.get("arrivals", []):
        receipt = arrival.get("receipt") or {}
        name = receipt.get("name")
        if not name:
            continue
        doc = posted.get(name)
        quantity = _number(arrival.get("posted_quantity"))
        if doc is None or quantity is None or _number(doc.get("received")) != quantity:
            conflicts.append(str(name))
    return sorted(set(conflicts))


def source_freshness(erp: Document) -> dict[str, object]:
    status = str(erp.get("status", "UNAVAILABLE"))
    present = {
        kind
        for kind in ("purchase_order", "purchase_receipt", "purchase_invoice")
        if documents(erp, kind, posted=False)
    }
    missing = [
        kind
        for kind in ("purchase_order", "purchase_receipt", "purchase_invoice")
        if kind not in present
    ]
    lifecycle = erp.get("document_lifecycle", {})
    lifecycle = lifecycle if isinstance(lifecycle, Mapping) else {}
    pending = [
        kind
        for kind in missing
        if lifecycle.get(kind) in {"AWAITING_RECEIPT", "AWAITING_INVOICE", "NOT_YET_CREATED"}
    ]
    required_missing = [kind for kind in missing if kind == "purchase_order" or kind not in pending]
    errors = erp.get("read_errors", [])
    read_error = erp.get("read_error")
    conflicts = receiving_receipt_conflicts(erp)
    return {
        "status": "CURRENT"
        if status == "CONNECTED" and not required_missing and not errors and not conflicts
        else "UNAVAILABLE",
        "scope": "erp_case_documents",
        "erp_status": status,
        "missing_document_kinds": missing,
        "pending_document_kinds": pending,
        "document_lifecycle": erp.get("document_lifecycle", {}),
        "observed_at": erp.get("received_at"),
        "error_code": "RECEIVING_RECEIPT_NOT_REFRESHED" if conflicts else (
            read_error.get("code", "") if isinstance(read_error, Mapping) else ""
        ),
        **({"pending_receipt_readbacks": conflicts} if conflicts else {}),
    }


def _net_rate(item: Document) -> float | None:
    rate = _number(item.get("net_rate"))
    if rate is not None:
        return rate
    amount, quantity = _number(item.get("net_amount")), _number(item.get("qty"))
    return amount / quantity if amount is not None and quantity else None


def _price_comparison(pos: list[Document], invoices: list[Document]) -> dict[str, object]:
    unknown: dict[str, object] = {
        "purchase_price_variance": None,
        "invoice_price_delta_percent": None,
        "invoice_unit_price": None,
        "price_comparison_status": "INCOMPARABLE",
        "matched_invoice_quantity": None,
    }
    po_lines = {
        (str(po["name"]), str(item.get("name", ""))): (po, item)
        for po in pos
        for item in _items(po)
        if item.get("name")
    }
    comparisons: list[tuple[float, float, float, tuple[object, ...]]] = []
    for invoice in invoices:
        items = _items(invoice)
        if not items:
            return unknown
        for item in items:
            match = po_lines.get(
                (str(item.get("purchase_order", "")), str(item.get("po_detail", "")))
            )
            if match is None and not item.get("po_detail"):
                candidates = [
                    (po, line)
                    for (po_name, _), (po, line) in po_lines.items()
                    if po_name == item.get("purchase_order")
                    and line.get("item_code") == item.get("item_code")
                    and line.get("uom") == item.get("uom")
                ]
                if len(candidates) == 1:
                    match = candidates[0]
            if match is None:
                return unknown
            po, po_item = match
            basis = (invoice.get("currency"), item.get("item_code"), item.get("uom"))
            if not all(basis) or basis != (
                po.get("currency"),
                po_item.get("item_code"),
                po_item.get("uom"),
            ):
                return unknown
            actual, expected, quantity = (
                _net_rate(item),
                _net_rate(po_item),
                _number(item.get("qty")),
            )
            if actual is None or expected is None or quantity is None or expected <= 0:
                return unknown
            if invoice.get("is_return") and quantity > 0:
                return unknown
            comparisons.append((actual, expected, quantity, basis))
    if not comparisons or len({value[3][0] for value in comparisons}) != 1:
        return unknown
    variance = sum((actual - expected) * quantity for actual, expected, quantity, _ in comparisons)
    expected_amount = sum(expected * quantity for _, expected, quantity, _ in comparisons)
    quantity = sum(quantity for _, _, quantity, _ in comparisons)
    homogeneous = len({value[3] for value in comparisons}) == 1
    return {
        "purchase_price_variance": variance,
        "invoice_price_delta_percent": _percent(variance, expected_amount),
        "invoice_unit_price": (
            sum(actual * qty for actual, _, qty, _ in comparisons) / quantity
            if homogeneous and quantity > 0
            else None
        ),
        "price_comparison_status": "MATCHED_NET_LINES",
        "matched_invoice_quantity": quantity if homogeneous else None,
    }


def live_flow_metrics(erp: Document) -> dict[str, object]:
    """Project one complete read. None is unknown; zero is a known empty quantity."""
    pos = documents(erp, "purchase_order")
    receipts = documents(erp, "purchase_receipt")
    invoices = documents(erp, "purchase_invoice")
    transfers = documents(erp, "quality_release_transfer")
    orders = documents(erp, "sales_order")
    deliveries = documents(erp, "delivery_note")
    sales_invoices = documents(erp, "sales_invoice")
    ordered, accepted = _sum(pos, "quantity"), _sum(receipts, "accepted")
    received, rejected = _sum(receipts, "received"), _sum(receipts, "rejected")
    released, delivered = _sum(transfers, "quantity"), _sum(deliveries, "quantity")
    quality = (
        max(0.0, rejected - released) if rejected is not None and released is not None else None
    )
    balance = (
        accepted + released - delivered
        if accepted is not None and released is not None and delivered is not None
        else None
    )
    outstanding = (
        max(0.0, ordered - received) if ordered is not None and received is not None else None
    )
    physical = erp.get("physical_evidence", {})
    physical = physical if isinstance(physical, Mapping) else {}
    observed = (
        _number(physical.get("received_quantity")) if physical.get("verified") is True else None
    )
    # Receiving documents confirm a lower bound of physical arrival, not outstanding cartons.
    arrived = observed if observed is not None else received
    explicit = _number(erp.get("receipt_exception_quantity"))
    unresolved = (
        max(0.0, observed - received)
        if observed is not None and received is not None
        else (max(0.0, explicit) if explicit is not None else 0.0)
    )
    gap = quality + unresolved if quality is not None else None
    currency = _consensus([po.get("currency") for po in pos])
    uom, compatible = _quantity_basis([*pos, *receipts, *transfers, *deliveries])
    costs = [_number(po.get("unit_rate")) for po in pos]
    unit_cost = costs[0] if len(costs) == 1 and compatible and currency else None
    invoice_held = any(
        bool(row.get("on_hold")) or row.get("status") == "PAYMENT_HOLD" for row in invoices
    )
    same_currency = (
        all(row.get("currency") == currency for row in invoices) and currency is not None
    )
    invoice_hold = (
        _sum(
            [row for row in invoices if row.get("on_hold") or row.get("status") == "PAYMENT_HOLD"],
            "grand_total",
        )
        if same_currency
        else None
    )
    # An upstream receiving case need not have a customer commercial scope.
    # Its missing sales documents are not evidence of zero revenue. A known
    # customer order with no posted invoice, however, has zero billed revenue.
    booked = _sum(orders, "booked_value") if orders else None
    billed = _sum(sales_invoices, "billed_revenue") if orders or sales_invoices else None
    sales_currency = _consensus([row.get("currency") for row in [*orders, *sales_invoices]])
    if (orders or sales_invoices) and (sales_currency is None or sales_currency != currency):
        booked = billed = None
    billed_amount = _sum(sales_invoices, "billed_amount") if sales_currency == currency else None
    fully_billed = bool(orders) and all(
        (percent := _number(row.get("billed_percent"))) is not None and percent >= 100
        for row in orders
    )
    price = _price_comparison(pos, invoices)
    stock = erp.get("stock_balance", {})
    stock = stock if isinstance(stock, Mapping) and stock.get("verified") is True else {}
    result: dict[str, object] = {
        "metric_version": "operational-facts.v1",
        "item_code": _consensus([item.get("item_code") for po in pos for item in _items(po)]),
        "source_sequence": int(_number(erp.get("sequence")) or 0),
        "currency": currency,
        "uom": uom,
        "expected": ordered,
        "physically_arrived": arrived,
        "physically_arrived_basis": "INDEPENDENT_OBSERVATION"
        if observed is not None
        else "RECEIPT_CONFIRMED",
        "received": received,
        "received_cumulative": received,
        "receipt_posted_quantity": received,
        "accepted": accepted,
        "accepted_cumulative": accepted,
        "released_quantity": released,
        "recorded": balance,
        "case_balance": balance,
        "recorded_basis": "CASE_ACCEPTED_LESS_RECORDED_ISSUES",
        "on_hand": _number(stock.get("on_hand")),
        "available_to_promise": _number(stock.get("available_to_promise")),
        "outstanding_order_quantity": outstanding,
        "quality_hold": quality,
        "receipt_unresolved": unresolved,
        "gap": gap,
        "invoice_held": invoice_held,
        "invoice_count": float(len(invoices)),
        "invoice_hold_value": invoice_hold,
        "working_capital_at_risk": _product(gap, unit_cost),
        "purchase_price_variance": price["purchase_price_variance"],
        "value_protected": billed,
        "booked_revenue": booked,
        "billed_revenue": billed,
        "billed_amount": billed_amount,
        "net_billed_sales": _sum(sales_invoices, "net_total")
        if sales_currency == currency
        else None,
        "revenue_at_risk": (
            0.0
            if fully_billed
            else max(0.0, booked - billed_amount)
            if booked is not None and billed_amount is not None
            else None
        ),
        "delivered_quantity": delivered,
        "customer_order_quantity": _sum(orders, "quantity"),
        "po_unit_cost": unit_cost,
    }
    if not compatible:
        for key in (
            "expected",
            "physically_arrived",
            "received",
            "received_cumulative",
            "receipt_posted_quantity",
            "accepted",
            "accepted_cumulative",
            "recorded",
            "case_balance",
            "outstanding_order_quantity",
            "quality_hold",
            "gap",
            "receipt_unresolved",
            "delivered_quantity",
            "released_quantity",
        ):
            result[key] = None
        result["quantity_status"] = "INCOMPARABLE_ITEM_OR_UOM"
    else:
        result["quantity_status"] = "CASE_QUANTITIES"
    if source_freshness(erp)["status"] != "CURRENT":
        for key, value in result.items():
            if isinstance(value, (int, float, bool)) and key != "source_sequence":
                result[key] = None
        result["currency"] = result["uom"] = None
        result["quantity_status"] = "UNAVAILABLE"
    return result


def business_impact(erp: Document) -> dict[str, object]:
    metrics = live_flow_metrics(erp)
    pos, invoices = documents(erp, "purchase_order"), documents(erp, "purchase_invoice")
    price = _price_comparison(pos, invoices)
    current = source_freshness(erp)["status"] == "CURRENT"
    currency = metrics["currency"]
    invoice_value = (
        _sum(invoices, "grand_total")
        if currency and all(row.get("currency") == currency for row in invoices)
        else None
    )
    result: dict[str, object] = {
        "provenance": "ERPNext / Frappe Cloud live read",
        "status": "CURRENT" if current else "UNAVAILABLE",
        "source_sequence": metrics["source_sequence"],
        "currency": currency,
        "inventory_availability_percent": _percent(metrics["recorded"], metrics["expected"]),
        "inventory_availability_basis": "CASE_BALANCE_NOT_AVAILABLE_TO_PROMISE",
        "erp_reconciliation_percent": _percent(metrics["received"], metrics["physically_arrived"]),
        "working_capital_at_risk": metrics["working_capital_at_risk"],
        "invoice_hold_value": metrics["invoice_hold_value"],
        "quality_hold_value": _product(metrics["quality_hold"], metrics["po_unit_cost"]),
        "receipt_gap_value": _product(metrics["receipt_unresolved"], metrics["po_unit_cost"]),
        "receipt_gap_percent": _percent(metrics["gap"], metrics["expected"]),
        "quality_hold_percent": _percent(metrics["quality_hold"], metrics["expected"]),
        "available_inventory_value": _product(metrics["case_balance"], metrics["po_unit_cost"]),
        "value_protected": metrics["billed_revenue"],
        "value_protected_classification": "NOT_CONFIGURED"
        if not documents(erp, "sales_order") and not documents(erp, "sales_invoice")
        else "UNAVAILABLE"
        if metrics["billed_revenue"] is None
        else "OBSERVED_BILLING_NOT_INCREMENTAL_REVENUE"
        if metrics["billed_revenue"]
        else "NOT_REALIZED",
        "booked_revenue": metrics["booked_revenue"],
        "billed_revenue": metrics["billed_revenue"],
        "revenue_at_risk": metrics["revenue_at_risk"],
        "po_line_value": _sum(pos, "line_value") if currency else None,
        "po_unit_cost": metrics["po_unit_cost"],
        "invoice_value": invoice_value,
        **price,
        "supplier_delivery_completion_percent": _percent(metrics["received"], metrics["expected"]),
        "supplier_status": erp.get("supplier_status") or "UNKNOWN" if current else "UNKNOWN",
        "supplier_payment_hold": (
            erp.get("supplier_payment_hold")
            if current and isinstance(erp.get("supplier_payment_hold"), bool)
            else None
        ),
        "invoice_status": ("PAYMENT HOLD" if metrics["invoice_held"] else "OPEN")
        if invoices
        else "NOT YET INVOICED",
    }
    if not current:
        for key, value in result.items():
            if isinstance(value, (int, float, bool)) and key != "source_sequence":
                result[key] = None
        result.update(
            invoice_status="UNKNOWN",
            price_comparison_status="UNAVAILABLE",
            value_protected_classification="UNAVAILABLE",
        )
    return result
