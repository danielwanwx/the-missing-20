"""Strict case-matrix regressions for the read-only Agent Platform.

These tests drive the real coordinator seam with changing provider projections.
They deliberately cover both a fully evidenced *plan* and cases which must be
blocked.  No assertion permits an external write or a verified recovery.
"""

from __future__ import annotations

from copy import deepcopy

from the_missing_20.adapters.agent_platform import AgentPlatform
from the_missing_20.adapters.demo_executor import DemoExecutionResult


class _MutableReader:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls = 0

    def current(self) -> dict[str, object]:
        self.calls += 1
        return deepcopy(self.payload)


def _erp(*, quality_hold: bool = True, status: str = "CONNECTED") -> dict[str, object]:
    return {
        "status": status,
        "activity": [
            {
                "source_id": "erpnext-missing20",
                "provider": "ERPNext",
                "status": "HELD" if quality_hold else "VERIFIED",
                "record_id": "PR-20",
                "label": "Receipt PR-20",
                "detail": "8 held" if quality_hold else "20 accepted",
            }
        ],
        "documents": [
            {"kind": "purchase_order", "name": "PO-20"},
            {
                "kind": "purchase_receipt",
                "name": "PR-20",
                "status": "PARTIAL_QUALITY_HOLD" if quality_hold else "RECEIVED",
                "rejected": 8 if quality_hold else 0,
            },
            {"kind": "purchase_invoice", "name": "PI-20", "status": "PAYMENT_HOLD"},
        ],
    }


def _registry(*, mismatch: bool = False) -> dict[str, object]:
    return {
        "case_id": "M20-CASE-20",
        "purchase_order": "WRONG-PO" if mismatch else "PO-20",
        "purchase_receipt": "PR-20",
        "purchase_invoice": "PI-20",
        "supplier_lot": "LOT-20",
        "certificate_id": "CERT-20",
        "quantity": 8,
        "evidence_revision": "rev-3",
    }


def _saas(
    *,
    direct_receipt: bool,
    receipt_matches: bool = True,
    registry_mismatch: bool = False,
    include_registry: bool = True,
) -> dict[str, object]:
    sources: list[dict[str, object]] = []
    if include_registry:
        sources.append(
            {
                "source_id": "airtable-quality-registry",
                "provider": "Airtable",
                "status": "VERIFIED",
                "record_id": "rec-20",
                "label": "Registry approved",
                "detail": "quality release registry",
                "correlation": _registry(mismatch=registry_mismatch),
            }
        )
    sources.extend(
        [
            {
                "source_id": "celigo-quality-release",
                "provider": "Celigo",
                "status": "VERIFIED",
                "record_id": "run-20" if direct_receipt else "flow-20",
                "label": "Run receipt" if direct_receipt else "Flow enabled",
                "detail": "ERP acknowledged" if direct_receipt else "Control-plane only",
                "evidence_kind": "RUN_RECEIPT" if direct_receipt else "CONTROL_PLANE",
                "correlation": _registry(mismatch=not receipt_matches),
                "erp_acknowledged": direct_receipt,
            },
            {
                "source_id": "jira-capa",
                "provider": "Jira",
                "status": "VERIFIED",
                "record_id": "CAPA-20",
                "label": "CAPA journal",
                "detail": "context only",
            },
            {
                "source_id": "slack-quality-alerts",
                "provider": "Slack",
                "status": "VERIFIED",
                "record_id": "171.20",
                "label": "Alert journal",
                "detail": "context only",
            },
        ]
    )
    return {
        "status": "CONNECTED",
        "correlation_id": "M20-CASE-20",
        "sources": sources,
        "activity": sources,
    }


def _step(projection: dict[str, object], step_id: str) -> dict[str, object]:
    return next(
        step
        for step in projection["plan"]
        if isinstance(step, dict) and step.get("id") == step_id
    )


def test_full_tuple_and_exact_celigo_receipt_only_prepare_a_guarded_plan() -> None:
    """A plan may be ready, but a provider mutation remains unreachable."""

    erp = _MutableReader(_erp())
    saas = _MutableReader(_saas(direct_receipt=True))

    projection = AgentPlatform(erp, saas).diagnose()

    assert projection["correlation"]["status"] == "FULLY_CORRELATED"
    assert projection["integration_receipt"]["status"] == "VERIFIED"
    assert projection["agent_run"]["state"] == "PLAN_READY"
    assert _step(projection, "validate_run")["status"] == "DONE"
    assert projection["execution"] == {
        "available": False,
        "status": "WRITE_DISABLED",
        "detail": "External provider mutations are intentionally disabled in this demo build.",
    }
    assert erp.calls == saas.calls == 1


def test_enabled_flow_is_not_a_run_receipt_even_with_a_complete_registry_tuple() -> None:
    projection = AgentPlatform(
        _MutableReader(_erp()), _MutableReader(_saas(direct_receipt=False))
    ).diagnose()

    assert projection["correlation"]["status"] == "FULLY_CORRELATED"
    assert projection["integration_receipt"]["status"] == "CONTROL_PLANE_ONLY"
    assert projection["agent_run"]["state"] == "BLOCKED"
    assert _step(projection, "validate_run")["status"] == "BLOCKED"


def test_verified_plan_needs_manager_approval_before_a_guarded_executor_runs() -> None:
    class _Executor:
        def __init__(self) -> None:
            self.calls = 0

        def execute(self, plan):  # type: ignore[no-untyped-def]
            self.calls += 1
            assert plan.case_id == "M20-CASE-20"
            assert plan.quantity == 8
            return DemoExecutionResult("MAT-STE-20", "PI-20", False, True)

    executor = _Executor()
    platform = AgentPlatform(_MutableReader(_erp()), _MutableReader(_saas(direct_receipt=True)), executor=executor)
    ready = platform.diagnose()

    assert ready["execution"]["status"] == "AWAITING_MANAGER_APPROVAL"
    approved = platform.approve("M20 Demo Manager")
    result = platform.execute(approved["execution"]["approval_id"], "m20-run-20")

    assert executor.calls == 1
    assert result["execution"]["status"] == "VERIFIED"


def test_normal_receipt_uses_the_same_guarded_evidence_path_without_an_incident() -> None:
    saas = _saas(direct_receipt=True)
    for row in saas["sources"]:  # type: ignore[union-attr]
        if isinstance(row, dict) and isinstance(row.get("correlation"), dict):
            row["correlation"]["quantity"] = 0
    projection = AgentPlatform(
        _MutableReader(_erp(quality_hold=False)), _MutableReader(saas)
    ).diagnose()

    assert projection["diagnosis"]["finding"] == "NO_QUALITY_HOLD_DETECTED"
    assert projection["agent_run"]["state"] == "PLAN_READY"
    assert projection["evidence_constellation"]["conclusion"]["status"] == "CLEAR"
    assert projection["execution"]["available"] is False


def test_mismatched_registry_or_receipt_is_blocked_and_names_the_mismatch() -> None:
    registry_mismatch = AgentPlatform(
        _MutableReader(_erp()), _MutableReader(_saas(direct_receipt=True, registry_mismatch=True))
    ).diagnose()
    receipt_mismatch = AgentPlatform(
        _MutableReader(_erp()), _MutableReader(_saas(direct_receipt=True, receipt_matches=False))
    ).diagnose()

    assert registry_mismatch["correlation"]["status"] == "MISMATCHED_CORRELATION"
    assert registry_mismatch["correlation"]["mismatched_fields"] == ["purchase_order"]
    assert registry_mismatch["agent_run"]["state"] == "BLOCKED"
    assert receipt_mismatch["integration_receipt"]["status"] == "MISMATCHED_RECEIPT"
    assert receipt_mismatch["agent_run"]["state"] == "BLOCKED"


def test_registry_that_is_held_cannot_be_used_to_complete_a_correlation() -> None:
    saas = _saas(direct_receipt=True)
    saas["sources"][0]["status"] = "HELD"  # type: ignore[index]
    saas["activity"][0]["status"] = "HELD"  # type: ignore[index]

    projection = AgentPlatform(_MutableReader(_erp()), _MutableReader(saas)).diagnose()

    assert projection["correlation"]["status"] == "PARTIAL_CORRELATION"
    assert projection["agent_run"]["state"] == "BLOCKED"


def test_repeated_polls_deduplicate_but_a_changed_provider_record_gets_one_new_sequence() -> None:
    erp = _MutableReader(_erp())
    saas = _MutableReader(_saas(direct_receipt=False))
    platform = AgentPlatform(erp, saas)

    first = platform.current()
    second = platform.current()
    assert second["latest_sequence"] == first["latest_sequence"]

    saas.payload["sources"][0]["status"] = "HELD"  # type: ignore[index]
    saas.payload["activity"][0]["status"] = "HELD"  # type: ignore[index]
    changed = platform.current()
    assert changed["latest_sequence"] == first["latest_sequence"] + 1
    assert changed["activity"][-1]["source_id"] == "airtable-quality-registry"

    saas.payload["sources"][0]["correlation"]["evidence_revision"] = "rev-4"  # type: ignore[index]
    revised = platform.current()
    assert revised["latest_sequence"] == changed["latest_sequence"] + 1
    assert revised["activity"][-1]["source_id"] == "airtable-quality-registry"
