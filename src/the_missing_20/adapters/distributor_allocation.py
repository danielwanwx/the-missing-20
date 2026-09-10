"""Fixed v1 customer-contract allocation arithmetic.

This module has no ERP or model dependency.  It compiles the only quantities
that may later be prepared by the distributor operations service.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

CONTRACT_ALLOCATION_VERSION = "v1"


class ContractAllocationError(ValueError):
    """Configured contract terms or a candidate allocation are invalid."""


def _quantity(value: object, label: str, *, positive: bool = False) -> Decimal:
    if isinstance(value, bool):
        raise ContractAllocationError(f"{label} must be a quantity")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ContractAllocationError(f"{label} must be a quantity") from exc
    if not result.is_finite() or result < 0 or (positive and result <= 0):
        raise ContractAllocationError(
            f"{label} must be {'positive' if positive else 'non-negative'}"
        )
    return result


def _wire(value: Decimal) -> int | float:
    return int(value) if value == value.to_integral_value() else float(value)


def contract_mode(config: Mapping[str, object]) -> bool:
    """Return whether the optional, versioned contract allocator is enabled."""

    raw = config.get("allocation_policy")
    return isinstance(raw, Mapping) and raw.get("version") == CONTRACT_ALLOCATION_VERSION


def validate_contract_config(config: Mapping[str, object]) -> None:
    """Validate the opt-in terms without changing legacy allocation configs."""

    raw_policy = config.get("allocation_policy")
    if raw_policy is None:
        return
    if not isinstance(raw_policy, Mapping) or set(raw_policy) != {"version"}:
        raise ContractAllocationError("allocation_policy must be exactly version v1")
    if raw_policy.get("version") != CONTRACT_ALLOCATION_VERSION:
        raise ContractAllocationError("allocation_policy version is unsupported")
    rows = config.get("allocations")
    if not isinstance(rows, list):
        raise ContractAllocationError("allocations are required")
    for row in rows:
        if not isinstance(row, Mapping):
            raise ContractAllocationError("contract allocation must be an object")
        required = {
            "customer_order",
            "requested_quantity",
            "priority",
            "promised_delivery_at",
            "customer_priority",
            "partial_dispatch",
            "minimum_dispatch_quantity",
            "allow_final_remainder",
        }
        if set(row) != required:
            raise ContractAllocationError("contract allocation terms are incomplete")
        if not isinstance(row["promised_delivery_at"], str) or not row["promised_delivery_at"]:
            raise ContractAllocationError("promised_delivery_at is required")
        if (
            isinstance(row["customer_priority"], bool)
            or not isinstance(row["customer_priority"], int)
            or row["customer_priority"] <= 0
        ):
            raise ContractAllocationError("customer_priority must be positive")
        if (
            type(row["partial_dispatch"]) is not bool
            or type(row["allow_final_remainder"]) is not bool
        ):
            raise ContractAllocationError("contract dispatch flags must be booleans")
        _quantity(row["minimum_dispatch_quantity"], "minimum_dispatch_quantity", positive=True)


def state_revision(*, lots: object, allocations: object, prepared_picks: object) -> str:
    """Digest physical availability and fixed commitments, not display projections."""

    payload = {
        "lots": lots,
        "allocations": [
            {
                key: row.get(key)
                for key in (
                    "customer_order",
                    "requested_quantity",
                    "dispatched",
                    "promised_delivery_at",
                    "customer_priority",
                    "partial_dispatch",
                    "minimum_dispatch_quantity",
                    "allow_final_remainder",
                )
            }
            for row in allocations
            if isinstance(row, Mapping)
        ]
        if isinstance(allocations, list)
        else allocations,
        "prepared_picks": prepared_picks,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode()).hexdigest()[:24]


def compile_plan(
    *,
    allocations: object,
    lots: object,
    prepared_picks: object,
) -> dict[str, object]:
    """Compile the one v1-feasible plan from verified state facts.

    Prepared quantities are prior commitments.  They consume available stock before
    a new allocation is calculated, so a later receipt/inspection event cannot
    allocate the same stock twice.
    """

    if (
        not isinstance(allocations, list)
        or not isinstance(lots, list)
        or not isinstance(prepared_picks, list)
    ):
        raise ContractAllocationError("allocation state is malformed")
    prepared: dict[str, Decimal] = {}
    for row in prepared_picks:
        if not isinstance(row, Mapping):
            raise ContractAllocationError("prepared pick is malformed")
        order = row.get("customer_order")
        if not isinstance(order, str) or not order:
            raise ContractAllocationError("prepared pick customer order is missing")
        prepared[order] = prepared.get(order, Decimal()) + _quantity(
            row.get("remaining"), "prepared pick remaining"
        )
    available = sum(
        (_quantity(row.get("usable"), "lot usable") for row in lots if isinstance(row, Mapping)),
        Decimal(),
    )
    if len([row for row in lots if isinstance(row, Mapping)]) != len(lots):
        raise ContractAllocationError("lot state is malformed")
    committed = sum(prepared.values(), Decimal())
    if committed > available:
        raise ContractAllocationError("prepared commitments exceed usable stock")
    available -= committed

    terms: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in allocations:
        if not isinstance(raw, Mapping):
            raise ContractAllocationError("allocation state is malformed")
        order = raw.get("customer_order")
        promise = raw.get("promised_delivery_at")
        priority = raw.get("customer_priority")
        if not isinstance(order, str) or not order or order in seen:
            raise ContractAllocationError("contract customer order is invalid")
        if not isinstance(promise, str) or not promise:
            raise ContractAllocationError("contract promise is invalid")
        if isinstance(priority, bool) or not isinstance(priority, int) or priority <= 0:
            raise ContractAllocationError("contract customer priority is invalid")
        partial = raw.get("partial_dispatch")
        final_remainder = raw.get("allow_final_remainder")
        if type(partial) is not bool or type(final_remainder) is not bool:
            raise ContractAllocationError("contract dispatch flags are invalid")
        seen.add(order)
        terms.append(
            {
                "customer_order": order,
                "promised_delivery_at": promise,
                "customer_priority": priority,
                "partial_dispatch": partial,
                "minimum_dispatch_quantity": _quantity(
                    raw.get("minimum_dispatch_quantity"), "minimum_dispatch_quantity", positive=True
                ),
                "allow_final_remainder": final_remainder,
                "requested_quantity": _quantity(
                    raw.get("requested_quantity"), "requested_quantity"
                ),
                "dispatched": _quantity(raw.get("dispatched"), "dispatched"),
            }
        )
    rows: list[dict[str, object]] = []
    for term in sorted(
        terms,
        key=lambda item: (
            str(item["promised_delivery_at"]),
            int(item["customer_priority"]),
            str(item["customer_order"]),
        ),
    ):
        order = str(term["customer_order"])
        remaining = max(Decimal(), term["requested_quantity"] - term["dispatched"])
        fixed = min(prepared.get(order, Decimal()), remaining)
        unprepared_remaining = remaining - fixed
        new_quantity = min(unprepared_remaining, available)
        minimum = term["minimum_dispatch_quantity"]
        completes_remaining = new_quantity == unprepared_remaining
        if (
            not term["partial_dispatch"]
            and not completes_remaining
            or (
                new_quantity
                and new_quantity < minimum
                and not (completes_remaining and term["allow_final_remainder"])
            )
        ):
            new_quantity = Decimal()
        available -= new_quantity
        rows.append(
            {
                "customer_order": order,
                "promised_delivery_at": term["promised_delivery_at"],
                "customer_priority": term["customer_priority"],
                "partial_dispatch": term["partial_dispatch"],
                "minimum_dispatch_quantity": _wire(minimum),
                "allow_final_remainder": term["allow_final_remainder"],
                "prepared_commitment": _wire(fixed),
                "new_quantity": _wire(new_quantity),
                "quantity": _wire(fixed + new_quantity),
                "remaining_after_dispatch": _wire(remaining - fixed - new_quantity),
            }
        )
    revision = state_revision(lots=lots, allocations=allocations, prepared_picks=prepared_picks)
    identity = {"version": CONTRACT_ALLOCATION_VERSION, "state_revision": revision, "rows": rows}
    plan_id = (
        "cap-"
        + hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()[:20]
    )
    return {
        "version": CONTRACT_ALLOCATION_VERSION,
        "plan_id": plan_id,
        "state_revision": revision,
        "rows": rows,
        "new_quantity": _wire(
            sum((_quantity(row["new_quantity"], "new quantity") for row in rows), Decimal())
        ),
    }
