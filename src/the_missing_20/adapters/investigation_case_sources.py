"""Unsolved, source-separated records for the isolated procurement demo.

These are synthetic business records, not production SaaS data. Only the
application-side packet carries the evaluation label; no source carries a
computed discrepancy partition or recommended repair.
"""

from collections.abc import Mapping
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

Variant = Literal[
    "uncommitted_receipt",
    "lost_ack",
    "wrong_quality_lot",
    "lookup_unavailable",
    "physical_shortage",
    "transfer_already_present",
    "evidence_conflict",
    "duplicate_invoice",
    "unit_price_variance",
    "uom_conversion_missing",
    "po_revision_race",
    "supplier_hold",
    "lot_trace_mismatch",
    "normal_complete",
]

INVESTIGATION_VARIANTS: tuple[Variant, ...] = (
    "uncommitted_receipt",
    "lost_ack",
    "wrong_quality_lot",
    "lookup_unavailable",
    "physical_shortage",
    "transfer_already_present",
    "evidence_conflict",
    "duplicate_invoice",
    "unit_price_variance",
    "uom_conversion_missing",
    "po_revision_race",
    "supplier_hold",
    "lot_trace_mismatch",
    "normal_complete",
)


def investigation_case_catalog() -> tuple[dict[str, str], ...]:
    """Describe the reusable hidden-cause matrix shown in the demo console."""

    return (
        {
            "id": "uncommitted_receipt",
            "label": "Split recovery",
            "signal": "Invoice match failed",
            "hidden_cause": "12-unit write never committed; 8-unit lot is approved but unmoved",
            "expected_control": "MANAGER_REVIEW",
        },
        {
            "id": "lost_ack",
            "label": "Lost acknowledgement",
            "signal": "Invoice match failed",
            "hidden_cause": "Timed-out receipt is already present in ERP",
            "expected_control": "SAFE_NOOP",
        },
        {
            "id": "wrong_quality_lot",
            "label": "Wrong quality lot",
            "signal": "Invoice match failed",
            "hidden_cause": "Equal-quantity approval belongs to another lot",
            "expected_control": "HARD_STOP",
        },
        {
            "id": "lookup_unavailable",
            "label": "Authority unavailable",
            "signal": "Invoice match failed",
            "hidden_cause": "ERP business-key lookup is incomplete, not empty",
            "expected_control": "REQUEST_EVIDENCE",
        },
        {
            "id": "physical_shortage",
            "label": "Physical shortage",
            "signal": "Invoice match failed",
            "hidden_cause": "Warehouse scans do not reconcile to the ordered quantity",
            "expected_control": "PROTECT",
        },
        {
            "id": "transfer_already_present",
            "label": "Transfer replay",
            "signal": "Invoice match failed",
            "hidden_cause": "Quality transfer effect already exists",
            "expected_control": "SAFE_NOOP",
        },
        {
            "id": "evidence_conflict",
            "label": "Cross-source conflict",
            "signal": "Invoice match failed",
            "hidden_cause": "Integration quantity conflicts with the authoritative ERP gap",
            "expected_control": "REQUEST_EVIDENCE",
        },
        {
            "id": "duplicate_invoice",
            "label": "Duplicate supplier invoice",
            "signal": "Invoice match failed",
            "hidden_cause": "Supplier invoice number already exists on another ERP document",
            "expected_control": "HARD_STOP",
        },
        {
            "id": "unit_price_variance",
            "label": "Commercial variance",
            "signal": "Invoice match failed",
            "hidden_cause": "Invoice unit price exceeds the approved PO line price",
            "expected_control": "HARD_STOP",
        },
        {
            "id": "uom_conversion_missing",
            "label": "UOM ambiguity",
            "signal": "Invoice match failed",
            "hidden_cause": (
                "Integration reports cases while ERP expects eaches and no conversion is admitted"
            ),
            "expected_control": "REQUEST_EVIDENCE",
        },
        {
            "id": "po_revision_race",
            "label": "PO revision race",
            "signal": "Invoice match failed",
            "hidden_cause": "Integration attempt used an older PO revision than the invoice match",
            "expected_control": "REQUEST_EVIDENCE",
        },
        {
            "id": "supplier_hold",
            "label": "Supplier compliance hold",
            "signal": "Invoice match failed",
            "hidden_cause": "Vendor master is blocked even though receipt evidence reconciles",
            "expected_control": "HARD_STOP",
        },
        {
            "id": "lot_trace_mismatch",
            "label": "Lot trace mismatch",
            "signal": "Invoice match failed",
            "hidden_cause": "ERP quality lot is not present in the physical receiving scans",
            "expected_control": "HARD_STOP",
        },
        {
            "id": "normal_complete",
            "label": "Recovered baseline",
            "signal": "Invoice open",
            "hidden_cause": "All quantities and idempotency keys reconcile",
            "expected_control": "NO_ACTION",
        },
    )


def investigation_packet(
    variant: Variant = "uncommitted_receipt", *, case: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Return equal visible entry symptoms backed by different source records."""
    if variant not in INVESTIGATION_VARIANTS:
        raise ValueError("unknown investigation variant")
    posted = variant in {"lost_ack", "normal_complete"}
    unavailable = variant == "lookup_unavailable"
    disposition = (
        "RECOVERY_COMPLETE"
        if variant == "normal_complete"
        else "NEEDS_EVIDENCE"
        if unavailable
        or variant in {"evidence_conflict", "uom_conversion_missing", "po_revision_race"}
        else "DENY"
        if variant
        in {
            "lost_ack",
            "wrong_quality_lot",
            "physical_shortage",
            "transfer_already_present",
            "duplicate_invoice",
            "unit_price_variance",
            "supplier_hold",
            "lot_trace_mismatch",
        }
        else "RECOVERY_READY"
    )
    safe_next_step = {
        "RECOVERY_READY": "Request Manager approval for the bounded receipt and quality transfer.",
        "DENY": "Stop the combined recovery and preserve the evidence for reconciliation.",
        "NEEDS_EVIDENCE": "Restore the authoritative ERP ledger read before deciding.",
        "RECOVERY_COMPLETE": "No recovery action remains; keep monitoring the open invoice.",
    }[disposition]
    receipt_rows = [
        {
            "id": "MAT-401",
            "po": "PO-4817",
            "line": 1,
            "quantity": 80,
            "stock_type": "AVAILABLE",
            "business_key": "RCPT-4817-L1",
        },
        {
            "id": "MAT-402",
            "po": "PO-4817",
            "line": 1,
            "quantity": 8,
            "stock_type": "QUALITY_INSPECTION",
            "lot": "LOT-B",
        },
    ]
    if posted:
        receipt_rows.append(
            {
                "id": "MAT-403",
                "po": "PO-4817",
                "line": 1,
                "quantity": 12,
                "stock_type": "AVAILABLE",
                "business_key": "RCPT-4817-L2",
            }
        )
    sources: dict[str, dict[str, Any]] = {
        "read_control_context": {
            "case_id": "INVESTIGATION-4817",
            "evidence_ids": ["ALERT-4817"],
            "alert": {
                "id": "ALERT-4817",
                "invoice": "INV-4817",
                "event": "INVOICE_MATCH_FAILED",
                "root_cause": "UNKNOWN",
            },
            "policy": "Read-only investigation. Manager approval is required for writes. "
            "FOUR_WAY matching requires received and quality-accepted quantities. "
            "Do not retry a receipt whose business key already exists.",
        },
        "read_erp_evidence": {
            "evidence_ids": ["INV-4817", "PO-4817", "ERP-READ-4817"]
            + ([] if unavailable else [record["id"] for record in receipt_rows]),
            "invoice": {
                "id": "INV-4817",
                "supplier": "SUP-204",
                "supplier_invoice_number": "ACME-8841",
                "po": "PO-4817",
                "line": 1,
                "quantity": 100,
                "uom": "EA",
                "unit_price": "50.00",
                "currency": "USD",
                "match_level": "FOUR_WAY",
                "status": "HELD",
            },
            "purchase_order": {
                "id": "PO-4817",
                "revision": 4,
                "supplier": "SUP-204",
                "line": 1,
                "ordered": 100,
                "uom": "EA",
                "unit_price": "50.00",
                "currency": "USD",
                "shipment": "ASN-902",
            },
            "duplicate_invoice_read": {
                "status": "COMPLETE",
                "supplier": "SUP-204",
                "supplier_invoice_number": "ACME-8841",
                "records": [],
            },
            "supplier_master": {
                "id": "SUP-204",
                "status": "ACTIVE",
                "payment_hold": False,
            },
            "ledger_read": {
                "id": "ERP-READ-4817",
                "po": "PO-4817",
                "line": 1,
                "status": "UNAVAILABLE" if unavailable else "COMPLETE",
                "pagination_complete": not unavailable,
                "records": [] if unavailable else receipt_rows,
            },
        },
        "read_collaboration_evidence": {
            "evidence_ids": ["ASN-902", "SCAN-701", "SCAN-702", "SCAN-703"],
            "warehouse_receipt": {
                "id": "ASN-902",
                "po": "PO-4817",
                "line": 1,
                "status": "RECEIVED",
            },
            "scans": [
                {"id": "SCAN-701", "asn": "ASN-902", "lot": "LOT-A", "quantity": 80},
                {"id": "SCAN-702", "asn": "ASN-902", "lot": "LOT-B", "quantity": 8},
                {"id": "SCAN-703", "asn": "ASN-902", "lot": "LOT-C", "quantity": 12},
            ],
        },
        "read_airtable_evidence": {
            "evidence_ids": ["QA-901", "QA-902", "QA-XFER-READ"],
            "quality_records": [
                {
                    "id": "QA-901",
                    "lot": "LOT-B",
                    "quantity": 8,
                    "disposition": "PENDING" if variant == "wrong_quality_lot" else "APPROVED",
                },
                {"id": "QA-902", "lot": "LOT-X", "quantity": 8, "disposition": "APPROVED"},
            ],
            "transfer_read": {
                "id": "QA-XFER-READ",
                "lot": "LOT-B",
                "status": "COMPLETE",
                "records": [],
            },
        },
        "read_celigo_evidence": {
            "evidence_ids": ["ATTEMPT-551"],
            "attempts": [
                {
                    "id": "ATTEMPT-551",
                    "po": "PO-4817",
                    "line": 1,
                    "asn": "ASN-902",
                    "lot": "LOT-C",
                    "quantity": 12,
                    "uom": "EA",
                    "conversion_factor_to_po_uom": 1,
                    "source_po_revision": 4,
                    "business_key": "RCPT-4817-L2",
                    "response": "TIMEOUT",
                }
            ],
        },
    }
    if case is not None:
        quantities = case.get("quantities")
        if not isinstance(quantities, Mapping):
            raise ValueError("case projection lacks quantities")
        replacements = {
            "INVESTIGATION-4817": str(case["case_id"]),
            "INV-4817": str(case["invoice_id"]),
            "PO-4817": str(case["purchase_order_id"]),
            "LOT-B": str(case["supplier_lot"]),
            "RCPT-4817-L2": str(case["receipt_business_key"]),
        }

        def replace_ids(value: Any) -> Any:
            if isinstance(value, str):
                return replacements.get(value, value)
            if isinstance(value, list):
                return [replace_ids(item) for item in value]
            if isinstance(value, dict):
                return {key: replace_ids(item) for key, item in value.items()}
            return value

        sources = replace_ids(sources)
        erp = sources["read_erp_evidence"]
        warehouse = sources["read_collaboration_evidence"]
        quality = sources["read_airtable_evidence"]
        integration = sources["read_celigo_evidence"]
        physical = int(quantities["physically_arrived"])
        available = int(quantities["available"])
        held = int(quantities["quality_hold"])
        unresolved = int(quantities["receipt_unresolved"])
        # The shortage case must keep the business expectation (100 ordered)
        # separate from the physical observation (80 scanned). Collapsing both
        # to the same number erases the very discrepancy the Agent must explain.
        if variant != "physical_shortage":
            erp["invoice"]["quantity"] = physical
            erp["purchase_order"]["ordered"] = physical
        records = erp["ledger_read"]["records"]
        if records:
            records[0]["quantity"] = available
            if len(records) > 1:
                records[1]["quantity"] = held
            if len(records) > 2:
                records[2]["quantity"] = unresolved
        scans = warehouse["scans"]
        scans[0]["quantity"] = available
        scans[1]["quantity"] = held
        scans[2]["quantity"] = unresolved
        quality["quality_records"][0]["quantity"] = held
        integration["attempts"][0]["quantity"] = unresolved

    # Apply the hidden cause after the optional case-identity/quantity overlay.
    # Otherwise a scoped live case could accidentally erase the counterfactual
    # distinction and make different buttons feed identical evidence to Strands.
    erp = sources["read_erp_evidence"]
    warehouse = sources["read_collaboration_evidence"]
    quality = sources["read_airtable_evidence"]
    integration = sources["read_celigo_evidence"]
    held = int(quality["quality_records"][0]["quantity"])
    unresolved = int(integration["attempts"][0]["quantity"])
    if variant == "physical_shortage":
        warehouse["scans"][2]["quantity"] = max(0, unresolved - 1)
    elif variant == "transfer_already_present":
        quality["transfer_read"]["records"] = [
            {"id": "XFER-4817", "lot": quality["transfer_read"]["lot"], "quantity": held}
        ]
        quality["evidence_ids"].append("XFER-4817")
    elif variant == "evidence_conflict":
        integration["attempts"][0]["quantity"] = max(0, unresolved - 2)
    elif variant == "duplicate_invoice":
        duplicate = erp["duplicate_invoice_read"]
        duplicate["records"] = [
            {
                "id": "PINV-4701",
                "supplier": duplicate["supplier"],
                "supplier_invoice_number": duplicate["supplier_invoice_number"],
                "status": "POSTED",
            }
        ]
        erp["evidence_ids"].append("PINV-4701")
    elif variant == "unit_price_variance":
        erp["invoice"]["unit_price"] = "54.50"
    elif variant == "uom_conversion_missing":
        integration["attempts"][0].update(
            {
                "quantity": 2,
                "uom": "CASE",
                "conversion_factor_to_po_uom": None,
            }
        )
    elif variant == "po_revision_race":
        integration["attempts"][0]["source_po_revision"] = 3
    elif variant == "supplier_hold":
        erp["supplier_master"].update({"status": "BLOCKED_COMPLIANCE", "payment_hold": True})
    elif variant == "lot_trace_mismatch":
        warehouse["scans"][1]["lot"] = "LOT-UNSCOPED"
    elif variant == "normal_complete":
        ordered = int(erp["purchase_order"]["ordered"])
        business_key = integration["attempts"][0]["business_key"]
        erp["invoice"]["status"] = "OPEN"
        integration["attempts"][0]["quantity"] = ordered
        integration["attempts"][0]["response"] = "ACKNOWLEDGED"
        erp["ledger_read"]["records"] = [
            {
                "id": "MAT-401",
                "po": erp["invoice"]["po"],
                "line": erp["invoice"]["line"],
                "quantity": ordered,
                "stock_type": "AVAILABLE",
                "business_key": business_key,
            }
        ]
        erp["evidence_ids"] = [
            erp["invoice"]["id"],
            erp["purchase_order"]["id"],
            erp["ledger_read"]["id"],
            "MAT-401",
        ]

    for index, source in enumerate(sources.values(), start=1):
        source["revision"] = f"synthetic-r{index}"
        source["observed_at"] = "2026-09-05T12:00:00Z"
        source["freshness"] = "CURRENT_DEMO_RUN"

    # Validation metadata stays outside the model-visible source dictionary.
    return {
        "case_id": str(case["case_id"]) if case is not None else "INVESTIGATION-4817",
        "case_class": "source_investigation",
        "expected_disposition": disposition,
        "expected_safe_next_step": safe_next_step,
        "expected_reason_quantities": {
            "uncommitted_receipt": (
                (
                    int(case["quantities"]["receipt_unresolved"]),
                    int(case["quantities"]["quality_hold"]),
                )
                if case is not None
                else (12, 8)
            ),
            "lost_ack": (),
            "wrong_quality_lot": (),
            "lookup_unavailable": (),
            "physical_shortage": (),
            "transfer_already_present": (),
            "evidence_conflict": (),
            "duplicate_invoice": (),
            "unit_price_variance": (),
            "uom_conversion_missing": (),
            "po_revision_race": (),
            "supplier_hold": (),
            "lot_trace_mismatch": (),
            "normal_complete": (),
        }[variant],
        "evidence_ids": tuple(
            identifier for source in sources.values() for identifier in source["evidence_ids"]
        ),
        "tool_payload": {"sources": deepcopy(sources)},
        "source": "synthetic-demo-fixture",
    }


def correlate_investigation_sources(sources: dict[str, Any]) -> dict[str, Any]:
    """Join raw fixture records into checkable facts without choosing an action."""
    erp = sources["read_erp_evidence"]
    warehouse = sources["read_collaboration_evidence"]
    quality = sources["read_airtable_evidence"]
    integration = sources["read_celigo_evidence"]
    invoice = erp["invoice"]
    ledger = erp["ledger_read"]
    scans = warehouse["scans"]
    records = ledger["records"]
    attempts = integration["attempts"]
    attempt = attempts[0]
    physical_quantity = sum(
        row["quantity"] for row in scans if row["asn"] == erp["purchase_order"]["shipment"]
    )
    matched_records = [
        row for row in records if row["po"] == invoice["po"] and row["line"] == invoice["line"]
    ]
    legacy_available_quantity = sum(
        row["quantity"] for row in matched_records if row["stock_type"] == "AVAILABLE"
    )
    accepted_records = [row for row in matched_records if row["stock_type"] == "ACCEPTED_RECEIPT"]
    accepted_quantity = (
        sum(row["quantity"] for row in accepted_records)
        if accepted_records
        else legacy_available_quantity
    )
    issued_quantity = sum(
        row["quantity"]
        for row in ledger.get("recorded_issues", [])
        if row.get("po") == invoice["po"] and row.get("line") == invoice["line"]
    )
    available_quantity = accepted_quantity - issued_quantity
    quality_quantity = sum(
        row["quantity"] for row in matched_records if row["stock_type"] == "QUALITY_INSPECTION"
    )
    held_lots = {
        row["lot"]
        for row in matched_records
        if row["stock_type"] == "QUALITY_INSPECTION" and row.get("lot")
    }
    exact_quality = [row for row in quality["quality_records"] if row["lot"] in held_lots]
    transfer_records = quality["transfer_read"]["records"]
    scanned_lots = {row.get("lot") for row in scans if row.get("lot")}
    conversion = attempt.get("conversion_factor_to_po_uom")
    normalized_attempt_quantity = (
        attempt["quantity"] * conversion if isinstance(conversion, (int, float)) else None
    )
    duplicate_invoice_records = erp["duplicate_invoice_read"]["records"]
    customer_order = erp.get("customer_order")
    customer_order_present = isinstance(customer_order, dict) and bool(customer_order.get("id"))
    customer_order_quantity = customer_order.get("quantity") if customer_order_present else None
    customer_delivered_quantity = (
        customer_order.get("delivered_quantity") if customer_order_present else None
    )
    customer_booked_revenue = (
        customer_order.get("booked_revenue") if customer_order_present else None
    )
    customer_billed_revenue = (
        customer_order.get("billed_revenue") if customer_order_present else None
    )
    causal_revenue_increase_proven = (
        customer_order.get("causal_revenue_increase_proven") if customer_order_present else None
    )
    key_present = (
        None
        if ledger["status"] != "COMPLETE" or not ledger["pagination_complete"]
        else any(row.get("business_key") == attempt["business_key"] for row in matched_records)
    )
    return {
        "evidence_ids": tuple(
            identifier for source in sources.values() for identifier in source["evidence_ids"]
        ),
        "join_keys": {
            "purchase_order": invoice["po"],
            "line": invoice["line"],
            "shipment": erp["purchase_order"]["shipment"],
            "integration_lot": attempt["lot"],
            "integration_business_key": attempt["business_key"],
        },
        "observations": {
            "invoice_quantity": invoice["quantity"],
            "invoice_status": invoice["status"],
            "physical_received_quantity": physical_quantity,
            "erp_available_quantity": available_quantity,
            "erp_accepted_receipt_quantity": accepted_quantity,
            "erp_recorded_issue_quantity": issued_quantity,
            "erp_quality_inspection_quantity": quality_quantity,
            "erp_accounted_quantity": accepted_quantity + quality_quantity,
            "ledger_read_status": ledger["status"],
            "ledger_pagination_complete": ledger["pagination_complete"],
            "integration_attempt_quantity": attempt["quantity"],
            "integration_attempt_uom": attempt.get("uom"),
            "integration_conversion_factor": conversion,
            "integration_normalized_quantity": normalized_attempt_quantity,
            "integration_source_po_revision": attempt.get("source_po_revision"),
            "integration_attempt_response": attempt["response"],
            "integration_business_key_present_in_erp": key_present,
            "held_lots": tuple(sorted(held_lots)),
            "exact_held_lot_quality_dispositions": tuple(
                sorted(row["disposition"] for row in exact_quality)
            ),
            "exact_held_lot_transfer_present": any(
                row.get("lot") in held_lots for row in transfer_records
            ),
            "completed_quality_transfer_present": bool(transfer_records),
            "held_lots_present_in_physical_scans": held_lots.issubset(scanned_lots),
            "duplicate_supplier_invoice_present": bool(duplicate_invoice_records),
            "duplicate_supplier_invoice_ids": tuple(row["id"] for row in duplicate_invoice_records),
            "invoice_unit_price": invoice.get("unit_price"),
            "po_unit_price": erp["purchase_order"].get("unit_price"),
            "invoice_currency": invoice.get("currency"),
            "po_currency": erp["purchase_order"].get("currency"),
            "po_revision": erp["purchase_order"].get("revision"),
            "supplier_status": erp["supplier_master"].get("status"),
            "supplier_payment_hold": erp["supplier_master"].get("payment_hold"),
            "customer_order_present": customer_order_present,
            "customer_order_status": (
                customer_order.get("status") if customer_order_present else None
            ),
            "customer_order_quantity": customer_order_quantity,
            "customer_delivered_quantity": customer_delivered_quantity,
            "customer_booked_revenue": customer_booked_revenue,
            "customer_billed_revenue": customer_billed_revenue,
            "customer_billing_complete": (
                customer_order.get("billing_complete") if customer_order_present else None
            ),
            "causal_revenue_increase_proven": causal_revenue_increase_proven,
            "customer_delivery_note": (
                customer_order.get("delivery_note") if customer_order_present else None
            ),
            "customer_sales_invoice": (
                customer_order.get("sales_invoice") if customer_order_present else None
            ),
        },
    }


def evaluate_investigation_policy(findings: dict[str, Any]) -> dict[str, Any]:
    """Apply the deterministic safety policy to correlated, source-derived facts."""

    observed = findings["observations"]
    complete = (
        observed["ledger_read_status"] == "COMPLETE" and observed["ledger_pagination_complete"]
    )
    exact_lot_approved = observed["exact_held_lot_quality_dispositions"] == ("APPROVED",)
    physical_reconciles = observed["physical_received_quantity"] == observed["invoice_quantity"]
    key_present = observed["integration_business_key_present_in_erp"]
    transfer_present = observed["exact_held_lot_transfer_present"]
    duplicate_invoice = observed["duplicate_supplier_invoice_present"]

    def price(value: object) -> Decimal | None:
        try:
            amount = Decimal(str(value))
            return amount if amount.is_finite() and amount >= 0 else None
        except InvalidOperation:
            return None

    invoice_price, po_price = (
        price(observed["invoice_unit_price"]),
        price(observed["po_unit_price"]),
    )
    commercial_known = (
        invoice_price is not None
        and po_price is not None
        and bool(observed["invoice_currency"])
        and bool(observed["po_currency"])
    )
    commercial_match = commercial_known and (
        invoice_price == po_price and observed["invoice_currency"] == observed["po_currency"]
    )
    supplier_active = (
        observed["supplier_status"] == "ACTIVE" and observed["supplier_payment_hold"] is False
    )
    conversion_known = observed["integration_normalized_quantity"] is not None
    po_revision_matches = observed["integration_source_po_revision"] == observed["po_revision"]
    lot_trace_matches = observed["held_lots_present_in_physical_scans"]
    integration_gap = observed["invoice_quantity"] - observed["erp_accounted_quantity"]
    integration_matches_gap = observed["integration_normalized_quantity"] == max(0, integration_gap)
    already_complete = (
        complete
        and observed["erp_accounted_quantity"] == observed["invoice_quantity"]
        and observed["erp_quality_inspection_quantity"] == 0
        and observed["invoice_status"] == "OPEN"
    )
    customer_order_present = observed.get("customer_order_present") is True
    explicit_billing_complete = observed.get("customer_billing_complete")
    customer_order_read_complete = not customer_order_present or (
        all(
            isinstance(observed.get(key), (int, float))
            for key in (
                "customer_order_quantity",
                "customer_delivered_quantity",
            )
        )
        and (
            isinstance(explicit_billing_complete, bool)
            or all(
                isinstance(observed.get(key), (int, float))
                for key in ("customer_booked_revenue", "customer_billed_revenue")
            )
        )
    )
    billing_complete = (
        explicit_billing_complete
        if isinstance(explicit_billing_complete, bool)
        else bool(
            customer_order_read_complete
            and customer_order_present
            and observed["customer_booked_revenue"] > 0
            and observed["customer_billed_revenue"] >= observed["customer_booked_revenue"]
        )
    )
    customer_order_requires_fulfillment = (
        customer_order_present
        and customer_order_read_complete
        and (
            observed.get("customer_order_status") == "ORDER_HELD"
            or observed["customer_delivered_quantity"] < observed["customer_order_quantity"]
            or not billing_complete
        )
    )
    customer_order_complete = (
        customer_order_present
        and customer_order_read_complete
        and observed["customer_order_quantity"] > 0
        and observed["customer_delivered_quantity"] >= observed["customer_order_quantity"]
        and billing_complete
        and bool(observed.get("customer_delivery_note"))
        and bool(observed.get("customer_sales_invoice"))
    )
    invoice_release_ready = (
        complete
        and observed["erp_accounted_quantity"] == observed["invoice_quantity"]
        and observed["erp_quality_inspection_quantity"] == 0
        and observed["invoice_status"] == "PAYMENT_HOLD"
    )
    if duplicate_invoice:
        disposition, reason = (
            "DENY",
            "The supplier invoice number already exists on another posted ERP document.",
        )
    elif not commercial_known:
        disposition, reason = (
            "NEEDS_EVIDENCE",
            "Matched net invoice/PO prices and currency are not available for comparison.",
        )
    elif not commercial_match:
        disposition, reason = (
            "DENY",
            "The invoice price or currency conflicts with the approved purchase-order line.",
        )
    elif not supplier_active:
        disposition, reason = (
            "DENY",
            "The supplier master is blocked or payment-held; inventory recovery cannot release it.",
        )
    elif not lot_trace_matches:
        disposition, reason = (
            "DENY",
            "The ERP-held quality lot is not present in the physical receiving scans.",
        )
    elif not conversion_known or not po_revision_matches:
        disposition, reason = (
            "NEEDS_EVIDENCE",
            "The UOM conversion or source PO revision is not authoritative for comparison.",
        )
    elif customer_order_present and not customer_order_read_complete:
        disposition, reason = (
            "NEEDS_EVIDENCE",
            "The customer issue and billing read is incomplete.",
        )
    elif already_complete and customer_order_requires_fulfillment:
        disposition, reason = (
            "RECOVERY_READY",
            "Procurement is reconciled, but the customer order remains undelivered or unbilled; "
            "Manager approval is required for bounded fulfillment and billing.",
        )
    elif already_complete and customer_order_complete:
        disposition, reason = (
            "RECOVERY_COMPLETE",
            "Procurement, recorded goods issue, and billing are authoritatively reconciled; "
            "carrier delivery and cash collection are not asserted.",
        )
    elif already_complete:
        disposition, reason = (
            "RECOVERY_COMPLETE",
            "ERP is fully reconciled and the invoice is open; no recovery remains.",
        )
    elif invoice_release_ready:
        disposition, reason = (
            "RECOVERY_READY",
            "Inventory is fully reconciled but the matched invoice remains payment-held; "
            "Manager approval is required for the bounded release.",
        )
    elif not complete or key_present is None:
        disposition, reason = (
            "NEEDS_EVIDENCE",
            "The authoritative ERP ledger read is unavailable or incomplete.",
        )
    elif key_present:
        disposition, reason = (
            "DENY",
            "The timed-out receipt business key already exists; retry would duplicate the effect.",
        )
    elif not integration_matches_gap:
        disposition, reason = (
            "NEEDS_EVIDENCE",
            "The integration attempt quantity conflicts with the authoritative ERP gap.",
        )
    elif not exact_lot_approved:
        disposition, reason = (
            "DENY",
            "The exact ERP-held quality lot is not approved for release.",
        )
    elif not physical_reconciles or transfer_present:
        disposition, reason = (
            "DENY",
            "The physical or quality-transfer postconditions do not permit combined recovery.",
        )
    else:
        disposition, reason = (
            "RECOVERY_READY",
            "The missing receipt and approved exact-lot transfer are eligible for "
            "bounded recovery.",
        )
    return {
        "disposition": disposition,
        "reason": reason,
        "checks": {
            "authoritative_read_complete": complete,
            "physical_quantity_reconciles": physical_reconciles,
            "integration_business_key_present": key_present,
            "exact_held_lot_approved": exact_lot_approved,
            "exact_held_lot_transfer_present": transfer_present,
            "integration_attempt_matches_gap": integration_matches_gap,
            "already_complete": already_complete,
            "customer_order_read_complete": customer_order_read_complete,
            "customer_order_requires_fulfillment": customer_order_requires_fulfillment,
            "customer_order_complete": customer_order_complete,
            "invoice_release_ready": invoice_release_ready,
            "duplicate_supplier_invoice_absent": not duplicate_invoice,
            "commercial_terms_match": commercial_match,
            "supplier_active": supplier_active,
            "uom_conversion_known": conversion_known,
            "source_po_revision_matches": po_revision_matches,
            "lot_trace_matches": lot_trace_matches,
        },
        "write_authority": "NONE",
        "manager_approval_required": disposition == "RECOVERY_READY",
    }
