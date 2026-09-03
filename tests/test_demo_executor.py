from __future__ import annotations

import json
from urllib.request import Request

import pytest

from the_missing_20.adapters.demo_executor import (
    DemoExecutionBlocked,
    DemoReleasePlan,
    ERPNextDemoExecutor,
)
from the_missing_20.adapters.erpnext_source import ERPNextCredentials


def _executor(*, environment: str = "demo") -> ERPNextDemoExecutor:
    def transport(request: Request, _timeout: float) -> bytes:
        path = request.full_url.split("https://erp.example", 1)[1]
        if path.startswith("/api/resource/Purchase%20Receipt/"):
            data = {"name": "MAT-PRE-2026-00001", "docstatus": 1, "supplier_delivery_note": "M20-DOCK-87421", "items": [{"item_code": "M20-ECU-CTRL", "rejected_qty": 8, "rejected_warehouse": "M20 Quality Hold - M20", "warehouse": "Stores - M20", "uom": "Nos", "stock_uom": "Nos"}]}
        elif path.startswith("/api/resource/Purchase%20Invoice/"):
            data = {"name": "ACC-PINV-2026-00007", "docstatus": 1, "on_hold": False, "hold_comment": "M20 DEMO hold"}
        elif path.startswith("/api/resource/Warehouse/"):
            data = {"company": "Missing 20 Automotive Demo"}
        elif path.startswith("/api/resource/Stock%20Entry?"):
            data = []
        elif path == "/api/resource/Stock%20Entry":
            data = {"name": "MAT-STE-2026-00001"}
        elif path == "/api/method/frappe.client.submit":
            return json.dumps({"message": {"name": "MAT-STE-2026-00001"}}).encode()
        elif path.startswith("/api/resource/Stock%20Entry/"):
            data = {"name": "MAT-STE-2026-00001", "docstatus": 1}
        else:
            raise AssertionError(path)
        return json.dumps({"data": data}).encode()

    return ERPNextDemoExecutor(
        ERPNextCredentials("https://erp.example", "key", "secret"),
        environment=environment,
        transport=transport,
    )


def _plan() -> DemoReleasePlan:
    return DemoReleasePlan(
        case_id="M20-ECU-2026-00011-LOT-A",
        purchase_receipt="MAT-PRE-2026-00001",
        purchase_invoice="ACC-PINV-2026-00007",
        quantity=8,
        idempotency_key="m20-demo-run-0001",
    )


def test_executes_only_submitted_m20_demo_documents() -> None:
    result = _executor().execute(_plan())

    assert result.transfer_name == "MAT-STE-2026-00001"
    assert result.verified is True
    assert result.idempotent is False


def test_rejects_provider_writes_outside_the_demo_environment() -> None:
    with pytest.raises(DemoExecutionBlocked, match="MISSING20_ENVIRONMENT=demo"):
        _executor(environment="local").execute(_plan())
