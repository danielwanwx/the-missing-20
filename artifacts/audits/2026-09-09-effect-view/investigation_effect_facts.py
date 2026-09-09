"""Relationship facts for model-visible investigation context.

The source correlation and policy modules retain the canonical audit view.  This
module intentionally exposes a smaller relationship view to the language model:
it joins a receipt attempt to the scoped ERP lookup and each exact quality-held
lot without deriving a disposition, action, or authority.
"""

from __future__ import annotations

from collections.abc import Mapping
from math import isfinite
from typing import Any

from the_missing_20.adapters.investigation_case_sources import correlate_investigation_sources

_SOURCE_ERP = "read_erp_evidence"
_SOURCE_QUALITY = "read_airtable_evidence"
_SOURCE_INTEGRATION = "read_celigo_evidence"


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _records(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _first_attempt(integration: Mapping[str, Any]) -> Mapping[str, Any]:
    attempts = _records(integration.get("attempts"))
    return attempts[0] if attempts else {}


def _identifier(record: Mapping[str, Any]) -> Any:
    """Keep the source identifier, including null when the source omitted it."""

    return record.get("id", record.get("evidence_id"))


def _source_metadata(record: Mapping[str, Any], source: Mapping[str, Any]) -> dict[str, Any]:
    """Carry source metadata through when a nested read omits it."""

    if record.get("revision") is not None:
        revision = record.get("revision")
    else:
        revision = source.get("revision")
    if record.get("observed_at") is not None:
        observed_at, observed_at_source = record.get("observed_at"), "record"
    else:
        observed_at, observed_at_source = source.get("observed_at"), "source"
    return {
        "revision": revision,
        "observed_at": observed_at,
        "observed_at_source": observed_at_source if observed_at is not None else None,
    }


def _scope_id_equal(left: Any, right: Any) -> bool:
    return (
        isinstance(left, str)
        and isinstance(right, str)
        and bool(left.strip())
        and bool(right.strip())
        and left == right
    )


def _line_equal(left: Any, right: Any) -> bool:
    return (
        isinstance(left, int)
        and not isinstance(left, bool)
        and isinstance(right, int)
        and not isinstance(right, bool)
        and left > 0
        and right > 0
        and left == right
    )


def _same_scope(
    left_purchase_order: Any,
    left_line: Any,
    right_purchase_order: Any,
    right_line: Any,
) -> bool:
    """Return true only for two fully specified, equal PO/line scopes."""

    return _scope_id_equal(left_purchase_order, right_purchase_order) and _line_equal(
        left_line, right_line
    )


def _finite_number(value: Any) -> int | float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value):
        return value
    return None


def _quantity_sum(rows: list[Mapping[str, Any]]) -> int | float | None:
    quantities: list[int | float] = []
    for row in rows:
        quantity = _finite_number(row.get("quantity"))
        if quantity is None:
            return None
        quantities.append(quantity)
    total = sum(quantities)
    return total if isfinite(total) else None


def _normalized_quantity(attempt: Mapping[str, Any]) -> int | float | None:
    quantity = _finite_number(attempt.get("quantity"))
    conversion = _finite_number(attempt.get("conversion_factor_to_po_uom"))
    if quantity is None or conversion is None:
        return None
    normalized = quantity * conversion
    return normalized if isfinite(normalized) else None


def _approval_records(quality_records: list[Mapping[str, Any]], lot: Any) -> list[dict[str, Any]]:
    return [
        {
            "evidence_id": _identifier(record),
            "quantity": record.get("quantity"),
            "disposition": record.get("disposition"),
        }
        for record in quality_records
        if record.get("lot") == lot
    ]


def _transfer_lookup(
    transfer: Mapping[str, Any], quality_source: Mapping[str, Any], lot: Any
) -> dict[str, Any]:
    transfer_records = _records(transfer.get("records"))
    matching_records = [record for record in transfer_records if record.get("lot") == lot]
    status = transfer.get("status")
    transfer_scope = transfer.get("lot")
    exact_scope = transfer_scope == lot
    complete_exact_scope = status == "COMPLETE" and exact_scope

    # Presence and absence use the same authority boundary here.  A record
    # from an unavailable, partial, or wrong-lot read remains listed for
    # inspection, but it cannot be promoted to an authoritative boolean.
    present: bool | None = bool(matching_records) if complete_exact_scope else None

    return {
        "evidence_id": _identifier(transfer),
        "scope": {"lot": transfer_scope},
        "status": status,
        "present": present,
        "matching_record_ids": [_identifier(record) for record in matching_records],
        **_source_metadata(transfer, quality_source),
    }


def investigation_effect_facts(
    sources: Mapping[str, Any],
    *,
    correlated_findings: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build relationship facts without mutating or classifying ``sources``.

    The ERP lookup can prove an absent receipt business key only when its own
    declared PO/line scope matches both the invoice and the integration
    attempt, and the read is complete and paginated.  Quality transfer absence
    follows the same fail-closed rule at exact-lot scope.
    """

    erp = _mapping(sources.get(_SOURCE_ERP))
    quality = _mapping(sources.get(_SOURCE_QUALITY))
    integration = _mapping(sources.get(_SOURCE_INTEGRATION))
    invoice = _mapping(erp.get("invoice"))
    ledger = _mapping(erp.get("ledger_read"))
    attempt = _first_attempt(integration)
    if correlated_findings is None:
        correlated_findings = correlate_investigation_sources(dict(sources))
    canonical_observations = _mapping(_mapping(correlated_findings).get("observations"))

    invoice_po = invoice.get("po")
    invoice_line = invoice.get("line")
    attempt_po = attempt.get("po")
    attempt_line = attempt.get("line")
    attempt_asn = attempt.get("asn")
    ledger_po = ledger.get("po")
    ledger_line = ledger.get("line")
    records = _records(ledger.get("records"))
    exact_invoice_records = [
        record
        for record in records
        if _same_scope(record.get("po"), record.get("line"), invoice_po, invoice_line)
    ]
    business_key = attempt.get("business_key")
    matching_destination_records = [
        record for record in exact_invoice_records if record.get("business_key") == business_key
    ]
    canonical_presence = canonical_observations.get("integration_business_key_present_in_erp")
    destination_present: bool | None = (
        canonical_presence if canonical_presence is True or canonical_presence is False else None
    )
    ledger_scope_matches = canonical_observations.get("ledger_scope_matches") is True

    destination_lookup = {
        "evidence_id": _identifier(ledger),
        "scope": {"purchase_order": ledger_po, "line": ledger_line},
        "requested_scope": {"purchase_order": invoice_po, "line": invoice_line},
        "scope_matches_requested": ledger_scope_matches,
        "status": ledger.get("status"),
        "pagination_complete": ledger.get("pagination_complete"),
        "queried_business_key": business_key,
        "present": destination_present,
        "matching_record_ids": [_identifier(record) for record in matching_destination_records],
        "revision": ledger.get("revision"),
        "observed_at": ledger.get("observed_at"),
    }

    quality_records = _records(quality.get("quality_records"))
    held_records = [
        record
        for record in exact_invoice_records
        if record.get("stock_type") == "QUALITY_INSPECTION"
        and isinstance(record.get("lot"), str)
        and bool(record["lot"].strip())
    ]
    held_lots = sorted({record.get("lot") for record in held_records}, key=str)
    quality_lots = []
    transfer = _mapping(quality.get("transfer_read"))
    for lot in held_lots:
        lot_records = [record for record in held_records if record.get("lot") == lot]
        quality_lots.append(
            {
                "lot": lot,
                "held_quantity": _quantity_sum(lot_records),
                "approval_records": _approval_records(quality_records, lot),
                "transfer_lookup": _transfer_lookup(transfer, quality, lot),
            }
        )

    return {
        "schema_version": "investigation-effect-facts.v1",
        "source_observed_at": {
            name: _mapping(sources.get(name)).get("observed_at")
            for name in (
                "read_control_context",
                _SOURCE_ERP,
                _SOURCE_QUALITY,
                _SOURCE_INTEGRATION,
                "read_collaboration_evidence",
            )
        },
        "receipt_attempt": {
            "attempt_id": _identifier(attempt),
            "business_key": business_key,
            "transport_response": attempt.get("response", attempt.get("transport_response")),
            "quantity": attempt.get("quantity"),
            "uom": attempt.get("uom"),
            "purchase_order": attempt_po,
            "line": attempt_line,
            "asn": attempt_asn,
            "conversion_factor_to_po_uom": attempt.get("conversion_factor_to_po_uom"),
            "normalized_quantity": (
                _finite_number(canonical_observations["integration_normalized_quantity"])
                if "integration_normalized_quantity" in canonical_observations
                else _normalized_quantity(attempt)
            ),
            "source_po_revision": attempt.get("source_po_revision"),
        },
        "destination_lookup": {
            **destination_lookup,
            **_source_metadata(ledger, erp),
        },
        "quality_lots": quality_lots,
    }
