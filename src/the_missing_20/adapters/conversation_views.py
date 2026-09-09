"""Freeze tool-returned history into a display attachment; never accept model numbers."""

from __future__ import annotations

import re
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

HISTORY_METRICS = (
    "received",
    "recorded",
    "quality_hold",
    "invoice_hold_value",
    "outstanding_order_quantity",
    "net_billed_sales",
)


def requests_history(question: str) -> bool:
    """Select the optional history reader from the current request, not old turns."""
    return bool(re.search(
        r"\b(?:histor\w*|trends?|baselines?|benchmarks?|averages?|means?|charts?|"
        r"increas\w*|decreas\w*|over time|net change)\b|历史|趋势|基准|平均|图表|增长|变化",
        question, re.I,
    ))


def requested_history_metric(question: str) -> str | None:
    """Resolve only an unambiguous human-named metric, never a model guess."""
    aliases = {
        "received": r"\b(?:receiving|received)\b|收货",
        "recorded": r"\b(?:recorded|posted receipts?)\b|入账",
        "quality_hold": r"\bquality hold\b|质量冻结",
        "invoice_hold_value": r"\binvoice hold\b|发票冻结",
        "outstanding_order_quantity": r"\boutstanding order\b|待交付",
        "net_billed_sales": r"\b(?:net billed sales|billed revenue)\b|已开票",
    }
    selected = [key for key, pattern in aliases.items() if re.search(pattern, question, re.I)]
    return selected[0] if len(selected) == 1 else None


def retained_history_view(
    projection: Mapping[str, Any], question: str,
) -> list[dict[str, Any]]:
    """Offer an existing chart beside a blocked answer, not an inferred answer.

    This narrow display convenience grants no tool invocation or authority. An
    ambiguous metric request gets no automatic selection; the dashboard remains
    available for selecting other metrics explicitly.
    """
    history_intent = r"\b(?:histor\w*|trends?|baselines?|benchmarks?)\b|历史|趋势|基准"
    if not re.search(history_intent, question, re.I):
        return []
    selected = requested_history_metric(question)
    history = projection.get("operational_history")
    case_id = projection.get("case_id")
    if selected is None or not case_id or not isinstance(history, Mapping):
        return []
    points = history.get("points")
    if history.get("case_id") != case_id or not isinstance(points, list) or not points:
        return []
    if any(not isinstance(point, Mapping) or point.get("case_id") != case_id for point in points):
        return []
    snapshot = deepcopy(dict(history))
    snapshot["points"] = snapshot["points"][-32:]
    snapshot["selection"] = {"returned": len(snapshot["points"]), "truncated": len(points) > 32}
    return [{"kind": "history", "metric": selected, "history": snapshot}]


def history_attachment(
    packet: Mapping[str, Any], metric: str | None, tool_calls: tuple[str, ...],
    *, question: str = "",
) -> list[dict[str, Any]]:
    """Use the exact case-scoped snapshot read in this turn, not a later projection."""
    if "read_operational_history" not in tool_calls:
        return []
    sources = packet.get("tool_payload", {}).get("sources", {})
    history = sources.get("read_operational_history")
    if not isinstance(history, Mapping) or history.get("case_id") != packet.get("case_id"):
        return []
    if metric is None:
        # A clear request for an existing chart should not disappear because the
        # model omitted an optional display field. This never fabricates an
        # answer or a read: only the exact snapshot actually read in this turn.
        views = retained_history_view(
            {"case_id": packet.get("case_id"), "operational_history": history}, question
        )
        return [{**view, "selection_basis": "explicit_human_request"} for view in views]
    if metric not in HISTORY_METRICS:
        return []
    points = history.get("points", [])
    if not isinstance(points, list) or any(
        not isinstance(point, Mapping) or point.get("case_id") != packet["case_id"]
        for point in points
    ):
        return []
    return [{"kind": "history", "metric": metric, "history": deepcopy(dict(history))}]
