"""Offline regressions for current ERP facts versus historical recovery evidence."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from the_missing_20.adapters.agent_platform import AgentPlatform


class Reader:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def current(self) -> dict[str, Any]:
        return deepcopy(self.payload)


class NoWriteExecutor:
    def execute(self, plan: object) -> object:
        raise AssertionError("Read projections must not execute provider effects")


def erp_snapshot(quantity: int = 20) -> dict[str, Any]:
    return {
        "status": "CONNECTED",
        "provider": "ERPNext / Frappe Cloud",
        "case_id": "LOCAL-FRESHNESS-CASE",
        "sequence": 4,
        "received_at": "2026-09-08T00:00:00Z",
        "activity": [],
        "documents": [
            {
                "kind": "purchase_order",
                "name": "PO-LOCAL",
                "quantity": quantity,
                "currency": "USD",
                "unit_rate": 1200,
                "line_value": quantity * 1200,
            },
            {
                "kind": "purchase_receipt",
                "name": "PR-LOCAL",
                "received": quantity,
                "accepted": quantity,
                "rejected": 0,
            },
            {
                "kind": "purchase_invoice",
                "name": "PI-LOCAL",
                "status": "OPEN",
                "currency": "USD",
                "grand_total": quantity * 1200,
            },
            {
                "kind": "sales_order",
                "name": "SO-LOCAL",
                "quantity": quantity,
                "booked_value": quantity * 2100,
                "currency": "USD",
                "billed_percent": 100,
            },
            {
                "kind": "sales_invoice",
                "name": "SI-LOCAL",
                "status": "SUBMITTED",
                "billed_revenue": quantity * 2100,
                "currency": "USD",
                "quantity": quantity,
            },
            {
                "kind": "delivery_note",
                "name": "DN-LOCAL",
                "status": "SUBMITTED",
                "quantity": quantity,
            },
        ],
    }


def platform_for(erp: Reader, **kwargs: Any) -> AgentPlatform:
    return AgentPlatform(
        erp, Reader({"status": "CONNECTED", "sources": [], "activity": []}), **kwargs
    )


def assert_unavailable(projection: dict[str, Any]) -> None:
    assert projection["source_freshness"]["status"] == "UNAVAILABLE"
    case = projection["case_projection"]
    assert case["provenance"] == "live-read" and case["status"] == "UNAVAILABLE"
    assert all(value is None for value in case["case"]["quantities"].values())
    assert case["case"]["invoice_held"] is None
    impact = projection["business_impact"]
    assert impact["status"] == "UNAVAILABLE"
    for key in (
        "billed_revenue",
        "booked_revenue",
        "working_capital_at_risk",
        "invoice_hold_value",
    ):
        assert impact[key] is None
    assert impact["supplier_status"] == impact["invoice_status"] == "UNKNOWN"
    assert impact["supplier_payment_hold"] is None
    proof = projection["value_proof"]
    assert proof["status"] == "UNAVAILABLE"
    assert all(value is None for value in proof["observed"].values())
    assert not any(proof["assertions"].values())
    assert projection["judge_proof"]["verified"] is False
    assert projection["execution"]["available"] is False
    assert projection["execution"]["fresh_read_verified"] is False
    assert projection["human_review"]["status"] == "SOURCE_UNAVAILABLE"
    constellation = projection["evidence_constellation"]
    assert constellation["conclusion"]["status"] == "UNAVAILABLE"
    assert next(node for node in constellation["nodes"] if node["id"] == "erpnext")["status"] in {
        "DEGRADED",
        "NOT_CONFIGURED",
        "UNAVAILABLE",
    }
    assert next(item for item in projection["systems"] if item["id"] == "erpnext")["status"] in {
        "DEGRADED",
        "NOT_CONFIGURED",
        "UNAVAILABLE",
    }


@pytest.mark.parametrize("status", ["DEGRADED", "NOT_CONFIGURED", "CONNECTED"])
def test_empty_erp_read_is_unavailable_even_when_transport_claims_connected(status: str) -> None:
    projection = platform_for(Reader({"status": status, "documents": [], "activity": []})).current()

    assert_unavailable(projection)
    assert projection["source_freshness"]["missing_document_kinds"] == [
        "purchase_order",
        "purchase_receipt",
        "purchase_invoice",
    ]
    assert projection["resolution_packet"] is None


@pytest.mark.parametrize("missing", ["purchase_order", "purchase_receipt", "purchase_invoice"])
def test_incomplete_connected_case_does_not_project_partial_facts_as_complete(missing: str) -> None:
    payload = erp_snapshot()
    payload["documents"] = [item for item in payload["documents"] if item["kind"] != missing]

    projection = platform_for(Reader(payload)).current()

    assert_unavailable(projection)
    assert projection["source_freshness"]["missing_document_kinds"] == [missing]


def test_connected_zero_quantities_are_still_observed_zero() -> None:
    projection = platform_for(Reader(erp_snapshot(0))).current()

    assert projection["source_freshness"]["status"] == "CURRENT"
    quantities = projection["case_projection"]["case"]["quantities"]
    assert quantities["available_to_promise"] is None
    assert quantities["invoice_count"] == 1
    assert all(
        value == 0
        for key, value in quantities.items()
        if key not in {"available_to_promise", "invoice_count"}
    )
    assert projection["business_impact"]["billed_revenue"] == 0
    assert projection["value_proof"]["observed"]["booked_revenue"] == 0
    assert projection["value_proof"]["observed"]["billed_revenue"] == 0
    assert projection["case_projection"]["case"]["invoice_held"] is False


def test_absent_customer_commercial_scope_is_unknown_not_zero_revenue() -> None:
    payload = erp_snapshot(1)
    payload["documents"] = [
        doc
        for doc in payload["documents"]
        if doc["kind"]
        not in {
            "sales_order",
            "sales_invoice",
            "delivery_note",
        }
    ]
    projection = platform_for(Reader(payload)).current()
    proof = projection["value_proof"]
    assert proof["status"] == "NOT_CONFIGURED"
    assert proof["observed"]["booked_revenue"] is None
    assert proof["observed"]["billed_revenue"] is None
    assert proof["observed"]["delivered_quantity"] is None
    assert proof["counterfactual"]["revenue_at_risk_if_hold_persists"] is None
    impact = projection["business_impact"]
    assert impact["value_protected_classification"] == "NOT_CONFIGURED"
    for name in ("value_protected", "booked_revenue", "billed_revenue", "revenue_at_risk"):
        assert impact[name] is None


def test_failed_read_preserves_historical_packet_and_fresh_read_restores_current_values(
    tmp_path: Path,
) -> None:
    packet = {
        "packet_id": "historical-verified-packet",
        "status": "VERIFIED",
        "post_state": {"available": 20, "customer_billed_revenue": 42000},
        "effects": {"invoice": "PI-LOCAL"},
    }
    state_path = tmp_path / "platform.json"
    state_path.write_text(
        json.dumps(
            {
                "sequence": 109,
                "agent_run": {"state": "VERIFIED"},
                "execution": {"status": "VERIFIED"},
                "resolution_packet": packet,
            }
        )
    )
    original_state = state_path.read_bytes()
    reader = Reader(erp_snapshot())
    platform = platform_for(reader, executor=NoWriteExecutor(), state_path=state_path)
    current = platform.current()
    assert current["case_projection"]["case"]["quantities"]["available"] == 0
    assert current["case_projection"]["case"]["quantities"]["received_cumulative"] == 20
    assert current["business_impact"]["billed_revenue"] == 42000

    reader.payload = {"status": "DEGRADED", "documents": [], "activity": [], "sequence": 5}
    failed = platform.current()
    assert_unavailable(failed)
    assert failed["latest_sequence"] == 109
    assert failed["agent_run"]["state"] == failed["execution"]["status"] == "VERIFIED"
    assert failed["agent_run"]["freshness"] == "HISTORICAL"
    assert failed["resolution_packet"] == {
        **packet,
        "freshness": "HISTORICAL",
        "fresh_read_verified": False,
    }
    assert state_path.read_bytes() == original_state
    restarted = platform_for(reader, executor=NoWriteExecutor(), state_path=state_path).current()
    assert restarted["resolution_packet"] == failed["resolution_packet"]

    reader.payload = erp_snapshot()
    reader.payload["sequence"] = 6
    restored = platform.current()
    assert restored["source_freshness"]["status"] == "CURRENT"
    assert restored["case_projection"]["case"]["quantities"]["available"] == 0
    assert restored["business_impact"]["billed_revenue"] == 42000


def test_degraded_read_cannot_claim_current_values_from_remaining_documents() -> None:
    payload = erp_snapshot()
    payload["status"] = "DEGRADED"
    payload["activity"] = [{"source_id": "erpnext-missing20", "status": "DEGRADED"}]

    projection = platform_for(Reader(payload)).current()

    assert_unavailable(projection)
    assert all("metrics" not in event for event in projection["activity"])


def test_degraded_source_blocks_existing_approval_even_if_document_bytes_are_unchanged(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "ready.json"
    reader = Reader(erp_snapshot())
    reader.payload["documents"][2]["status"] = "PAYMENT_HOLD"
    saas = Reader(
        {
            "status": "CONNECTED",
            "correlation_id": "LOCAL-FRESHNESS-CASE",
            "sources": [
                {
                    "source_id": "airtable-quality-registry",
                    "status": "VERIFIED",
                    "correlation": {
                        "case_id": "LOCAL-FRESHNESS-CASE",
                        "purchase_order": "PO-LOCAL",
                        "purchase_receipt": "PR-LOCAL",
                        "purchase_invoice": "PI-LOCAL",
                        "supplier_lot": "LOT-LOCAL",
                        "certificate_id": "CERT-LOCAL",
                        "quantity": 0,
                        "evidence_revision": "R1",
                    },
                }
            ],
            "activity": [],
        }
    )
    platform = AgentPlatform(reader, saas, executor=NoWriteExecutor(), state_path=state_path)
    platform.diagnose()
    approved = platform.approve("local-manager")
    reader.payload["status"] = "DEGRADED"

    with pytest.raises(ValueError, match="fresh verified plan"):
        platform.approve("local-manager")
    with pytest.raises(ValueError, match="fully verified evidence"):
        platform.execute(str(approved["execution"]["approval_id"]), "m20-local-stale-source")
