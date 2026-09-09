"""Receiving source semantics and reference candidates; never execution authority."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def receipt_relations(source: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Join actual voucher IDs to admitted ERP records, retaining every stock row."""
    records = [row for row in source.get("records", []) if isinstance(row, Mapping)]
    admitted = set(source.get("evidence_ids", []))
    identities = {
        row.get("evidence_id")
        for row in records
        if str(row.get("provider", "")).startswith("ERPNext")
    }
    relations = []
    for record in records:
        if record.get("evidence_id") not in admitted or not str(
            record.get("provider", "")
        ).startswith("ERPNext"):
            continue
        for row in record.get("stock_entries", []):
            if not isinstance(row, Mapping):
                continue
            receipt, ledger = row.get("voucher_no"), row.get("name")
            if (
                not isinstance(receipt, str)
                or receipt not in identities
                or receipt not in admitted
                or not isinstance(ledger, str)
                or not ledger
                or row.get("voucher_type") != "Purchase Receipt"
            ):
                continue
            relations.append(
                {
                    "receipt_id": receipt,
                    "stock_ledger_id": ledger,
                    "evidence_id": record["evidence_id"],
                    "revision": record.get("revision"),
                    "observed_at": record.get("observed_at"),
                }
            )
    return relations


def model_receiving_source(source: Mapping[str, Any]) -> dict[str, Any]:
    """Keep the retained/UI packet intact; qualify physical amounts for model reads."""
    quantities = dict(source.get("quantities", {}))
    physical = quantities.pop("physically_arrived", None)
    basis = source.get("physical_observation_basis")
    quantities.update(
        independently_observed_quantity=physical if basis == "INDEPENDENT_OBSERVATION" else None,
        receipt_confirmed_lower_bound=physical if basis == "RECEIPT_CONFIRMED" else None,
    )
    return {**source, "quantities": quantities, "receipt_relations": receipt_relations(source)}


def reference_candidates(
    previous: Mapping[str, Any],
    *,
    case_id: str,
    relations: list[dict[str, Any]],
    source_sequence: Any,
) -> dict[str, Any]:
    """Prior citations are referents only; missing members must not select survivors."""
    if previous.get("case_id") != case_id or previous.get("status") != "COMPLETE":
        return {"status": "UNAVAILABLE", "case_id": case_id}
    raw = previous.get("receipt_ids", [])
    if not isinstance(raw, list) or not raw or not all(isinstance(v, str) and v for v in raw):
        return {"status": "UNAVAILABLE", "case_id": case_id}
    prior = sorted(set(raw))
    current_ids = {row["receipt_id"] for row in relations}
    current = [value for value in prior if value in current_ids]
    missing = [value for value in prior if value not in current_ids]
    return {
        "status": "CHANGED"
        if missing
        else ("MULTIPLE_CANDIDATES" if len(current) > 1 else "ONE_CANDIDATE"),
        "case_id": case_id,
        "previous_receipt_ids": prior,
        "current_receipt_ids": current,
        "missing_receipt_ids": missing,
        "previous_source_sequence": previous.get("source_sequence"),
        "source_sequence": source_sequence,
        "authority": "Prior citations only, not selected receipt, current facts or approval.",
    }
