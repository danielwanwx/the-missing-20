"""Deterministic, disclosed-synthetic manufacturing context for the demo tenant.

The records in this module are intentionally linked to the admitted receipt case.
They make the downstream production and customer impact inspectable without
pretending that the hackathon tenant is a real production MES or finance system.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any


def _rounded(value: float, digits: int = 1) -> float:
    return round(float(value), digits)


def build_connected_operations(
    *,
    expected_units: int,
    available_units: int,
    quality_hold_units: int,
    receipt_unresolved_units: int,
    business_impact: Mapping[str, Any],
    scenario_variant: str,
    verified: bool,
) -> dict[str, object]:
    """Build one internally consistent 90-day plant, demand, supplier and cash view."""

    unresolved_units = (
        0
        if verified or scenario_variant == "normal_complete"
        else max(0, quality_hold_units + receipt_unresolved_units)
    )
    vehicle_sales_value = Decimal("45000")
    vehicle_contribution_margin = Decimal("6500")
    planned_today = max(120, expected_units)
    actual_today = max(0, planned_today - unresolved_units)
    schedule_attainment = actual_today * 100 / planned_today if planned_today else 100.0
    availability = 96.2 if unresolved_units == 0 else max(65.0, 96.2 - unresolved_units * 0.72)
    performance = 96.8
    quality = 99.1
    oee = availability * performance * quality / 10000
    revenue_at_risk = float(vehicle_sales_value * unresolved_units)
    margin_at_risk = float(vehicle_contribution_margin * unresolved_units)
    average_daily_requirement = 24
    days_of_supply = available_units / average_daily_requirement

    gap_ratio = unresolved_units / max(1, expected_units)
    schedule_gap = max(0.0, 1 - schedule_attainment / 100)
    quality_ratio = quality_hold_units / max(1, expected_units) if unresolved_units else 0.0
    risk_score = min(
        100.0,
        min(1.0, gap_ratio / 0.20) * 30
        + min(1.0, quality_ratio / 0.10) * 15
        + min(1.0, schedule_gap / 0.20) * 20
        + min(1.0, (unresolved_units / max(1, planned_today)) / 0.17) * 20
        + min(1.0, revenue_at_risk / 1_000_000) * 10
        + (5 if bool(business_impact.get("supplier_payment_hold")) else 0),
    )
    risk_score = _rounded(risk_score)
    risk_band = (
        "CRITICAL"
        if risk_score >= 75
        else "HIGH"
        if risk_score >= 50
        else "WATCH"
        if risk_score >= 25
        else "NORMAL"
    )

    end_day = datetime.now(UTC).date()
    history: list[dict[str, object]] = []
    for index in range(90):
        day = end_day - timedelta(days=89 - index)
        planned = (112, 118, 120, 116, 124, 110, 114)[index % 7]
        baseline_attainment = (96.4, 94.9, 97.1, 93.8, 95.6, 96.9, 94.4)[index % 7]
        day_availability = (95.4, 96.1, 94.8, 96.6, 95.9)[index % 5]
        day_performance = (96.1, 95.7, 97.0, 96.4)[index % 4]
        day_quality = (99.0, 99.2, 98.9, 99.3, 99.1, 99.4)[index % 6]
        day_oee = day_availability * day_performance * day_quality / 10000
        day_actual = round(planned * baseline_attainment / 100)
        day_risk = _rounded(max(4.0, (100 - baseline_attainment) * 2.1))
        day_units_at_risk = 0
        day_revenue_at_risk = 0.0
        if index == 89:
            planned = planned_today
            day_actual = actual_today
            baseline_attainment = schedule_attainment
            day_availability = availability
            day_performance = performance
            day_quality = quality
            day_oee = oee
            day_risk = risk_score
            day_units_at_risk = unresolved_units
            day_revenue_at_risk = revenue_at_risk
        history.append(
            {
                "date": day.isoformat(),
                "planned_units": planned,
                "actual_units": day_actual,
                "schedule_attainment_percent": _rounded(baseline_attainment),
                "availability_percent": _rounded(day_availability),
                "performance_percent": _rounded(day_performance),
                "quality_percent": _rounded(day_quality),
                "oee_percent": _rounded(day_oee),
                "risk_score": day_risk,
                "units_at_risk": day_units_at_risk,
                "revenue_at_risk": day_revenue_at_risk,
            }
        )

    return {
        "schema_version": "missing20-connected-operations/v1",
        "window": {
            "days": 90,
            "started_on": history[0]["date"],
            "ended_on": history[-1]["date"],
        },
        "risk_signal": {
            "score": risk_score,
            "band": risk_band,
            "units_at_risk": unresolved_units,
            "reasons": [
                reason
                for active, reason in (
                    (receipt_unresolved_units > 0 and not verified, "ERP receipt is unresolved"),
                    (quality_hold_units > 0 and not verified, "Exact supplier lot is quality-held"),
                    (schedule_attainment < 95, "Current shift schedule is at risk"),
                    (revenue_at_risk > 0, "Customer commitments depend on the missing units"),
                )
                if active
            ],
            "formula": (
                "receipt gap 30 + quality hold 15 + schedule 20 + demand 20 + "
                "revenue 10 + supplier control 5"
            ),
        },
        "current_shift": {
            "plant": "Fremont Final Assembly",
            "work_center": "FA-ECU-04",
            "production_order": "MO-EV-4817",
            "planned_units": planned_today,
            "actual_units": actual_today,
            "component_starved_units": unresolved_units,
            "schedule_attainment_percent": _rounded(schedule_attainment),
            "availability_percent": _rounded(availability),
            "performance_percent": _rounded(performance),
            "quality_percent": _rounded(quality),
            "oee_percent": _rounded(oee),
        },
        "customer_commitments": {
            "orders_due_48h": 64,
            "units_due_48h": planned_today,
            "units_at_risk": unresolved_units,
            "vehicle_sales_value": float(vehicle_sales_value),
            "revenue_at_risk": revenue_at_risk,
            "contribution_margin_at_risk": margin_at_risk,
            "customer_otif_percent_90d": 96.7,
        },
        "supplier_performance": {
            "receipts_90d": 18,
            "otif_receipts_90d": 17,
            "inbound_otif_percent_90d": 94.4,
            "inspected_units_90d": 10000,
            "rejected_units_90d": 12,
            "supplier_ppm_90d": 1200,
        },
        "inventory": {
            "available_component_units": available_units,
            "average_daily_requirement": average_daily_requirement,
            "days_of_supply": _rounded(days_of_supply),
            "inventory_value": float(business_impact.get("available_inventory_value", 0.0)),
        },
        "cash_cycle": {
            "days_inventory_outstanding": 28.4,
            "days_sales_outstanding": 36.2,
            "days_payables_outstanding": 31.0,
            "cash_conversion_cycle_days": 33.6,
        },
        "history": history,
        "source_links": {
            "mes": ["MO-EV-4817", "FA-ECU-04"],
            "demand": ["SO-EV-9001..9064"],
            "supplier": ["SUP-CTRL-07", "LOT-4817-QA"],
            "finance": ["PO-4817", "PINV-4817"],
        },
        "basis": (
            "90-day disclosed-synthetic MES, demand, supplier and finance records "
            "linked by production order, item, lot and PO"
        ),
        "provenance": "synthetic-demo-workspace",
    }
