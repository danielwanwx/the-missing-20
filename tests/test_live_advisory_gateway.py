from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import pytest
import strands

import the_missing_20.agents.live_advisory as advisory_module
from the_missing_20.adapters.ambiguous_case_platform import AmbiguousCasePlatform
from the_missing_20.adapters.live_advisory_gateway import (
    DashboardAdvisoryGateway,
    competition_investigation_packet,
    connected_competition_investigation_packet,
)
from the_missing_20.agents.live_advisory import (
    AdvisoryDisposition,
    AdvisoryRun,
    LiveAdvisoryResult,
    live_recovery_packet,
    model_source_payloads,
)
from the_missing_20.config import Settings
from the_missing_20.domain.ambiguous_receipt import QualityDisposition, primary_case
from the_missing_20.ports.agent_model import AgentProvider


def test_model_evidence_does_not_expose_expected_answers_or_solved_diagnosis() -> None:
    platform = AmbiguousCasePlatform()
    platform.diagnose()
    packet = live_recovery_packet(platform.current())
    original = json.dumps(packet, sort_keys=True)
    visible = model_source_payloads(packet)
    encoded = json.dumps(visible)
    for label in ("expected_disposition", "expected_safe_next_step", "AMBIGUOUS_RECEIPT_RESOLVED"):
        assert label not in encoded
    assert "diagnosis" not in visible["read_control_context"]
    assert visible["read_erp_evidence"]["quantities"]["available"] == 80
    assert visible["read_airtable_evidence"]["quality_disposition"] == "APPROVED"
    assert visible["read_erp_evidence"]["invoice_match_level"] == "FOUR_WAY"
    assert json.dumps(packet, sort_keys=True) == original


def test_gateway_model_budget_matches_structured_investigation_output_limit() -> None:
    factory = DashboardAdvisoryGateway(AmbiguousCasePlatform())._factory()
    assert factory.config.max_tokens == advisory_module.ADVISORY_OUTPUT_TOKENS
    assert factory.config.budget.max_output_tokens_per_request == factory.config.max_tokens


def test_sdk_hooks_emit_redacted_runtime_telemetry_and_progress() -> None:
    progress: list[tuple[str, str]] = []
    runtime_progress: list[dict[str, object]] = []
    hooks = advisory_module._RuntimeTelemetryHooks(
        lambda name, phase: progress.append((name, phase)),
        lambda event: runtime_progress.append(dict(event)),
    )
    tool_use = {"name": "read_erp_evidence", "toolUseId": "tool-1", "input": {"secret": 1}}

    hooks.before_model(SimpleNamespace(projected_input_tokens=420))
    hooks.after_model(SimpleNamespace(exception=None))
    hooks.before_tool(SimpleNamespace(tool_use=tool_use))
    hooks.after_tool(SimpleNamespace(tool_use=tool_use, duration=0.012, exception=None))

    assert progress == [
        ("read_erp_evidence", "started"),
        ("read_erp_evidence", "succeeded"),
    ]
    assert runtime_progress == hooks.events
    assert hooks.events[1]["duration_ms"] >= 0
    assert hooks.events[-1]["duration_ms"] == 12
    assert "secret" not in json.dumps(hooks.events)


def test_sdk_hook_observability_callbacks_fail_open() -> None:
    def broken_callback(*args, **kwargs):
        del args, kwargs
        raise OSError("telemetry sink unavailable")

    hooks = advisory_module._RuntimeTelemetryHooks(broken_callback, broken_callback)
    tool_use = {"name": "read_erp_evidence", "toolUseId": "tool-1"}

    hooks.before_model(SimpleNamespace(projected_input_tokens=12))
    hooks.after_model(SimpleNamespace(exception=None))
    hooks.before_tool(SimpleNamespace(tool_use=tool_use))
    hooks.after_tool(SimpleNamespace(tool_use=tool_use, duration=0.001, exception=None))

    assert [event["type"] for event in hooks.events] == [
        "model.started",
        "model.succeeded",
        "tool.started",
        "tool.succeeded",
    ]


def test_gateway_preserves_failure_diagnostics_without_publishing_an_answer() -> None:
    diagnostics = [{"stage": "validation", "attempt": 1, "disposition": "NEEDS_EVIDENCE"}]

    def runner(*args, **kwargs):
        error = advisory_module.AdvisoryValidationError("test rejection")
        error.diagnostics = diagnostics
        raise error

    platform = AmbiguousCasePlatform()
    gateway = DashboardAdvisoryGateway(
        platform, settings=_settings(AgentProvider.BEDROCK), runner=runner
    )
    answer = gateway.ask("Investigate")
    assert answer["agent_advisory"]["result"] is None
    assert answer["validation_diagnostics"] == diagnostics
    investigation = gateway.investigate(platform.current())
    assert investigation["result"] is None
    assert investigation["validation_diagnostics"] == diagnostics


def test_verified_answer_does_not_require_a_magic_completion_word() -> None:
    advisory_module.validate_advisory(
        LiveAdvisoryResult(
            disposition=AdvisoryDisposition.RECOVERY_COMPLETE,
            evidence_ids=("receipt",),
            reason="The receipt was successfully posted, quantities reconcile, invoice is open.",
            safe_next_step="No further action is required.",
            write_performed=False,
        ),
        calls=("read_control_context", "read_erp_evidence"),
        evidence_ids=("receipt",),
        expected_disposition=AdvisoryDisposition.RECOVERY_COMPLETE,
        expected_safe_next_step="No further action is required.",
    )


def test_source_explanation_cannot_collapse_receipt_gap_and_quality_hold() -> None:
    result = LiveAdvisoryResult(
        disposition=AdvisoryDisposition.RECOVERY_READY,
        evidence_ids=("ATTEMPT-551", "QA-901"),
        reason=(
            "The 12-unit receipt is absent and the 8-unit lot is held, but there is no second "
            "independent cause."
        ),
        safe_next_step="Manager approval is required before the bounded write.",
        write_performed=False,
    )

    with pytest.raises(advisory_module.AdvisoryValidationError, match="two independently"):
        advisory_module._validate_source_explanation(
            result,
            {
                "integration_attempt_quantity": 12,
                "erp_quality_inspection_quantity": 8,
            },
        )


def test_source_explanation_accepts_two_distinct_contributing_conditions() -> None:
    result = LiveAdvisoryResult(
        disposition=AdvisoryDisposition.RECOVERY_READY,
        evidence_ids=("ATTEMPT-551", "QA-901"),
        reason=(
            "A 12-unit receipt write never committed. Separately, an approved 8-unit lot "
            "remains in quality inspection without its stock transfer."
        ),
        safe_next_step="Manager approval is required before the bounded write.",
        write_performed=False,
    )

    advisory_module._validate_source_explanation(
        result,
        {
            "integration_attempt_quantity": 12,
            "erp_quality_inspection_quantity": 8,
        },
    )


@pytest.mark.parametrize(
    "updates",
    [
        {"erp_receipt_key_found": True},
        {"quality_disposition": QualityDisposition.REJECTED},
    ],
)
def test_domain_stop_states_remain_denied_in_model_boundary(updates) -> None:
    platform = AmbiguousCasePlatform(primary_case().model_copy(update=updates))
    platform.diagnose()
    packet = live_recovery_packet(platform.current())
    assert packet["expected_disposition"] == "DENY"
    assert "expected_disposition" not in model_source_payloads(packet)["read_control_context"]


@pytest.mark.parametrize(
    "repair_succeeds,provider_error", [(True, False), (False, False), (False, True)]
)
def test_unlabelled_advisory_uses_bounded_evaluator_feedback(
    monkeypatch: pytest.MonkeyPatch,
    repair_succeeds: bool,
    provider_error: bool,
) -> None:
    messages = []
    reads = []

    class Agent:
        def __init__(self, **kwargs):
            self.tools = kwargs["tools"]

        async def invoke_async(self, prompt, **kwargs):
            messages.append(prompt)
            if len(messages) == 2 and provider_error:
                raise RuntimeError("test provider failure")
            if len(messages) == 1:
                reads.extend(tool() for tool in self.tools)
                reads.append(self.tools[0]())
            result = LiveAdvisoryResult(
                disposition=(
                    AdvisoryDisposition.NEEDS_EVIDENCE
                    if len(messages) == 1 or not repair_succeeds
                    else AdvisoryDisposition.RECOVERY_READY
                ),
                evidence_ids=("RCPT-4817-L2-001", "QUALITY-4817-L1-001"),
                reason="Absent receipt and approved quality lot.",
                safe_next_step="Require manager approval before recovery.",
                write_performed=False,
            )
            return SimpleNamespace(structured_output=result)

    monkeypatch.setattr(strands, "Agent", Agent)
    platform = AmbiguousCasePlatform()
    platform.diagnose()
    factory = SimpleNamespace(
        create=lambda **kwargs: None,
        ledger=SimpleNamespace(snapshot=lambda: {}),
        provenance=lambda: {"provider": "test"},
    )
    invocation = advisory_module._invoke(
        live_recovery_packet(platform.current()), factory=factory, question="Investigate."
    )
    if repair_succeeds:
        run = asyncio.run(invocation)
        assert run.usage["validation_retries"] == 1
        assert run.usage["source_cache_hits"] == 1
        assert len(run.tool_calls) == len(set(run.tool_calls))
    elif provider_error:
        with pytest.raises(advisory_module.AdvisoryUnavailable):
            asyncio.run(invocation)
    else:
        with pytest.raises(advisory_module.AdvisoryValidationError) as rejected:
            asyncio.run(invocation)
        assert len(rejected.value.diagnostics) == 3
        assert rejected.value.diagnostics[-1]["attempt"] == 3
        assert "reason" not in rejected.value.diagnostics[-1]
    assert len(messages) == (3 if not repair_succeeds and not provider_error else 2)
    assert "Validation failed" in messages[1]
    assert "RECOVERY_READY" not in messages[1]
    if len(messages) == 3:
        assert "deterministic control-plane disposition" in messages[2]
    assert all("expected_disposition" not in read for read in reads)


class _Platform:
    def current(self) -> dict[str, object]:
        return {
            "execution": {
                "status": "VERIFIED",
                "transfer_name": "MAT-STE-2026-00001",
                "invoice_name": "ACC-PINV-2026-00007",
            },
            "diagnosis": {"status": "VERIFIED"},
            "activity": [],
            "correlation": {},
            "integration_receipt": {},
        }


def _settings(provider: AgentProvider) -> Settings:
    return Settings(agent_provider=provider)


def test_gateway_returns_explicit_unavailable_without_bedrock() -> None:
    gateway = DashboardAdvisoryGateway(_Platform(), settings=_settings(AgentProvider.SCRIPTED))  # type: ignore[arg-type]

    response = gateway.ask("What happened to the receipt?")

    assert response["answer"].startswith("Real Strands Agent is not configured")
    assert response["agent_advisory"] == {
        "status": "AGENT_UNAVAILABLE",
        "mode": "real_strands",
        "tool_calls": [],
        "result": None,
    }


def test_gateway_returns_provenanced_real_result() -> None:
    observed: dict[str, Any] = {}

    def runner(*args: Any, **kwargs: Any) -> AdvisoryRun:
        observed.update(kwargs)
        return AdvisoryRun(
            result=LiveAdvisoryResult(
                disposition=AdvisoryDisposition.RECOVERY_COMPLETE,
                evidence_ids=("MAT-STE-2026-00001",),
                reason="The ERP transfer is verified.",
                safe_next_step="Keep the deterministic control plane read-only.",
                write_performed=False,
            ),
            tool_calls=(
                "read_control_context",
                "read_erp_evidence",
                "read_airtable_evidence",
                "read_celigo_evidence",
                "read_collaboration_evidence",
            ),
            provider={"provider": "bedrock"},
            latency_ms=12,
            usage={"request_count": 2},
        )

    gateway = DashboardAdvisoryGateway(
        _Platform(),  # type: ignore[arg-type]
        settings=_settings(AgentProvider.BEDROCK),
        runner=runner,
    )
    response = gateway.ask("Is recovery complete?")

    assert observed["question"] == "Is recovery complete?"
    expected_answer = "Disposition: RECOVERY_COMPLETE. The ERP transfer is verified. "
    expected_answer += "Next: Keep the deterministic control plane read-only."
    assert response["answer"] == expected_answer
    advisory = response["agent_advisory"]
    assert advisory["status"] == "COMPLETE"
    assert advisory["result"]["write_performed"] is False


def test_gateway_carries_bounded_history_into_follow_up_turns() -> None:
    prompts: list[str] = []

    def runner(*args: Any, **kwargs: Any) -> AdvisoryRun:
        prompts.append(kwargs["question"])
        return AdvisoryRun(
            result=LiveAdvisoryResult(
                disposition=AdvisoryDisposition.RECOVERY_READY,
                evidence_ids=("ERP-READ-4817",),
                reason="The ERP receipt key is absent.",
                safe_next_step="Request human authorization for diagnosis.",
                write_performed=False,
            ),
            tool_calls=("read_control_context", "read_erp_evidence"),
            provider={"provider": "bedrock", "model": "nova-pro"},
            latency_ms=8,
            usage={"request_count": 1},
        )

    platform = AmbiguousCasePlatform()
    gateway = DashboardAdvisoryGateway(
        platform,
        settings=_settings(AgentProvider.BEDROCK),
        runner=runner,
        packet_factory=competition_investigation_packet,
    )

    gateway.ask("Which ERP key is missing?")
    response = gateway.ask("Does that explain all twenty units?")

    assert prompts[0] == "Which ERP key is missing?"
    assert "Prior conversation:" in prompts[1]
    assert "Which ERP key is missing?" in prompts[1]
    assert "Newest human question: Does that explain all twenty units?" in prompts[1]
    assert response["agent_advisory"]["context_turns"] == 1
    conversation = response["conversation"]
    assert len(conversation) == 2
    assert conversation[-1]["context_turns"] == 1
    assert conversation[-1]["tool_calls"] == ["read_control_context", "read_erp_evidence"]


def test_gateway_exposes_the_same_real_strands_boundary_for_primary_investigation() -> None:
    def runner(*args: Any, **kwargs: Any) -> AdvisoryRun:
        return AdvisoryRun(
            result=LiveAdvisoryResult(
                disposition=AdvisoryDisposition.RECOVERY_READY,
                evidence_ids=("RCPT-4817-L2-001",),
                reason="The receipt key is absent in ERP evidence.",
                safe_next_step="Request Manager review for the deterministic recovery packet.",
                write_performed=False,
            ),
            tool_calls=("read_control_context", "read_erp_evidence"),
            provider={"provider": "bedrock"},
            latency_ms=12,
            usage={"request_count": 1},
        )

    platform = AmbiguousCasePlatform()
    gateway = DashboardAdvisoryGateway(
        platform,
        settings=_settings(AgentProvider.BEDROCK),
        runner=runner,  # type: ignore[arg-type]
    )

    advisory = gateway.investigate(platform.diagnose())

    assert advisory["status"] == "COMPLETE"
    assert advisory["tool_calls"] == ["read_control_context", "read_erp_evidence"]
    assert advisory["result"]["write_performed"] is False


def test_live_packet_admits_only_current_ambiguous_case_evidence() -> None:
    platform = AmbiguousCasePlatform()

    packet = live_recovery_packet(platform.current())

    assert packet["case_class"] == "ambiguous_receipt"
    assert packet["expected_disposition"] == "RECOVERY_READY"
    assert packet["evidence_ids"] == (
        "RCPT-4817-L2-001",
        "QUALITY-4817-L1-001",
        "INV-4817",
        "M20-PO-4817",
    )
    sources = packet["tool_payload"]["sources"]
    assert sources["read_control_context"]["expected_safe_next_step"] == (
        "Manager approval is required before local synthetic recovery."
    )
    assert sources["read_erp_evidence"]["receipt_business_key_found"] is False
    assert sources["read_airtable_evidence"]["quality_disposition"] == "APPROVED"


def test_live_erp_projection_becomes_a_source_investigation_without_synthetic_ids() -> None:
    payload = {
        "received_at": "2026-09-07T06:00:00Z",
        "case_projection": {
            "provenance": "live-read",
            "source_sequence": 4,
            "case": {
                "case_id": "M20-LIVE-1",
                "purchase_order": "PO-LIVE-1",
                "purchase_receipt": "PR-LIVE-1",
                "purchase_invoice": "PI-LIVE-1",
                "quality_release_transfer": "MAT-STE-LIVE-1",
                "invoice_held": True,
                "quantities": {
                    "ordered": 20,
                    "physically_arrived": 20,
                    "available": 20,
                    "quality_hold": 0,
                    "receipt_unresolved": 0,
                },
            },
        },
        "correlation": {
            "status": "FULLY_CORRELATED",
            "tuple": {"supplier_lot": "LOT-LIVE", "quantity": 8},
            "registry_tuple": {
                "supplier_lot": "LOT-LIVE",
                "quantity": "8",
                "evidence_revision": "R4",
            },
        },
        "business_impact": {
            "po_unit_cost": 1200,
            "invoice_unit_price": 1200,
            "currency": "USD",
            "supplier_status": "ACTIVE",
        },
        "systems": [
            {"id": "airtable", "record_id": "rec-live"},
            {"id": "celigo", "record_id": "run-live"},
            {"id": "jira", "record_id": "QRC-1"},
            {"id": "slack", "record_id": "slack-1"},
        ],
        "diagnosis": {"status": "IDLE"},
        "execution": {"status": "AWAITING_MANAGER_APPROVAL"},
    }

    packet = live_recovery_packet(payload)

    assert packet["source"] == "live-external-read"
    assert packet["case_class"] == "source_investigation"
    assert packet["expected_disposition"] == "RECOVERY_READY"
    assert packet["source_sequence"] == 4
    assert "synthetic" not in json.dumps(packet).lower()
    assert {
        "PO-LIVE-1",
        "PR-LIVE-1",
        "PI-LIVE-1",
        "MAT-STE-LIVE-1",
        "rec-live",
        "run-live",
    } <= set(packet["evidence_ids"])
    sources = packet["tool_payload"]["sources"]
    assert sources["read_airtable_evidence"]["transfer_read"]["records"] == [
        {
            "id": "MAT-STE-LIVE-1",
            "lot": "LOT-LIVE",
            "source": "ERPNext Stock Entry",
        }
    ]
    findings = advisory_module.correlate_investigation_sources(sources)
    policy = advisory_module.evaluate_investigation_policy(findings)
    assert policy["disposition"] == "RECOVERY_READY"
    assert policy["checks"]["invoice_release_ready"] is True


def test_live_erp_projection_does_not_invent_a_quality_transfer_from_zero_hold() -> None:
    payload = {
        "received_at": "2026-09-07T06:00:00Z",
        "case_projection": {
            "provenance": "live-read",
            "source_sequence": 4,
            "case": {
                "case_id": "M20-LIVE-NO-TRANSFER",
                "purchase_order": "PO-LIVE-2",
                "purchase_receipt": "PR-LIVE-2",
                "purchase_invoice": "PI-LIVE-2",
                "invoice_held": True,
                "quantities": {
                    "ordered": 20,
                    "physically_arrived": 20,
                    "available": 20,
                    "quality_hold": 0,
                    "receipt_unresolved": 0,
                },
            },
        },
        "correlation": {
            "status": "FULLY_CORRELATED",
            "tuple": {"supplier_lot": "LOT-LIVE", "quantity": 0},
            "registry_tuple": {
                "supplier_lot": "LOT-LIVE",
                "quantity": "0",
                "evidence_revision": "R4",
            },
        },
        "business_impact": {
            "po_unit_cost": 1200,
            "invoice_unit_price": 1200,
            "currency": "USD",
            "supplier_status": "ACTIVE",
        },
        "systems": [
            {"id": "airtable", "record_id": "rec-live"},
            {"id": "celigo", "record_id": "run-live"},
        ],
        "diagnosis": {"status": "IDLE"},
        "execution": {"status": "AWAITING_MANAGER_APPROVAL"},
    }

    packet = live_recovery_packet(payload)

    transfer_read = packet["tool_payload"]["sources"]["read_airtable_evidence"]["transfer_read"]
    assert transfer_read["records"] == []
    assert not any("quality-transfer" in item for item in packet["evidence_ids"])


def test_live_customer_order_gap_is_visible_to_agent_and_requires_manager_gate() -> None:
    payload = {
        "received_at": "2026-09-07T06:00:00Z",
        "case_projection": {
            "provenance": "live-read",
            "source_sequence": 5,
            "case": {
                "case_id": "M20-LIVE-ORDER",
                "purchase_order": "PO-LIVE-ORDER",
                "purchase_receipt": "PR-LIVE-ORDER",
                "purchase_invoice": "PI-LIVE-ORDER",
                "quality_release_transfer": "STE-LIVE-ORDER",
                "sales_order": "SO-LIVE-ORDER",
                "delivery_note": "",
                "sales_invoice": "",
                "invoice_held": False,
                "quantities": {
                    "ordered": 20,
                    "physically_arrived": 20,
                    "available": 20,
                    "quality_hold": 0,
                    "receipt_unresolved": 0,
                },
            },
        },
        "correlation": {
            "status": "FULLY_CORRELATED",
            "tuple": {"supplier_lot": "LOT-LIVE", "quantity": 8},
            "registry_tuple": {
                "supplier_lot": "LOT-LIVE",
                "quantity": "8",
                "evidence_revision": "R5",
            },
        },
        "business_impact": {
            "po_unit_cost": 1200,
            "invoice_unit_price": 1200,
            "currency": "USD",
            "supplier_status": "ACTIVE",
        },
        "value_proof": {
            "status": "ORDER_HELD",
            "observed": {
                "order_quantity": 20,
                "delivered_quantity": 0,
                "booked_revenue": 42000,
                "billed_revenue": 0,
            },
        },
        "systems": [
            {"id": "airtable", "record_id": "rec-live"},
            {"id": "celigo", "record_id": "run-live"},
        ],
        "diagnosis": {"status": "PLAN_READY"},
        "execution": {"status": "AWAITING_MANAGER_APPROVAL"},
    }

    packet = live_recovery_packet(payload)
    sources = packet["tool_payload"]["sources"]
    findings = advisory_module.correlate_investigation_sources(sources)
    policy = advisory_module.evaluate_investigation_policy(findings)

    assert packet["expected_disposition"] == "RECOVERY_READY"
    assert "SO-LIVE-ORDER" in packet["evidence_ids"]
    assert sources["read_erp_evidence"]["customer_order"] == {
        "id": "SO-LIVE-ORDER",
        "status": "ORDER_HELD",
        "quantity": 20.0,
        "delivered_quantity": 0.0,
        "booked_revenue": 42000.0,
        "billed_revenue": 0.0,
        "currency": "USD",
        "delivery_note": None,
        "sales_invoice": None,
        "causal_revenue_increase_proven": False,
    }
    assert policy["disposition"] == "RECOVERY_READY"
    assert policy["checks"]["already_complete"] is True
    assert policy["checks"]["customer_order_requires_fulfillment"] is True


def test_live_invoice_only_case_rejects_a_quality_lot_explanation() -> None:
    result = LiveAdvisoryResult(
        disposition=AdvisoryDisposition.RECOVERY_READY,
        evidence_ids=("PI-LIVE-1",),
        reason="The exact held lot is not approved.",
        safe_next_step="Manager approval is required before the bounded external recovery.",
        write_performed=False,
    )

    with pytest.raises(advisory_module.AdvisoryValidationError, match="residual invoice hold"):
        advisory_module._validate_source_explanation(
            result,
            {
                "invoice_status": "PAYMENT_HOLD",
                "invoice_quantity": 20,
                "erp_accounted_quantity": 20,
                "erp_quality_inspection_quantity": 0,
                "integration_attempt_quantity": 0,
            },
        )


def test_source_explanation_rejects_unsupported_causal_revenue_claim() -> None:
    result = LiveAdvisoryResult(
        disposition=AdvisoryDisposition.RECOVERY_COMPLETE,
        evidence_ids=("SO-LIVE-ORDER", "SI-LIVE-ORDER"),
        reason=(
            "The delivery and invoice are submitted and billed revenue is USD 42,000. "
            "Causal revenue uplift proven."
        ),
        safe_next_step="No recovery action remains; review the verified resolution packet.",
        write_performed=False,
    )

    with pytest.raises(advisory_module.AdvisoryValidationError, match="causal revenue claim"):
        advisory_module._validate_source_explanation(
            result,
            {
                "causal_revenue_increase_proven": False,
                "integration_attempt_quantity": 0,
                "erp_quality_inspection_quantity": 0,
            },
        )


def test_source_explanation_accepts_observed_billing_without_causal_claim() -> None:
    result = LiveAdvisoryResult(
        disposition=AdvisoryDisposition.RECOVERY_COMPLETE,
        evidence_ids=("SO-LIVE-ORDER", "SI-LIVE-ORDER"),
        reason=(
            "The delivery and invoice are submitted and billed revenue is USD 42,000; "
            "this observed accounting outcome does not prove causal revenue uplift."
        ),
        safe_next_step="No recovery action remains; review the verified resolution packet.",
        write_performed=False,
    )

    advisory_module._validate_source_explanation(
        result,
        {
            "causal_revenue_increase_proven": False,
            "integration_attempt_quantity": 0,
            "erp_quality_inspection_quantity": 0,
        },
    )


def test_live_invoice_only_case_rejects_claim_that_completed_transfer_is_absent() -> None:
    result = LiveAdvisoryResult(
        disposition=AdvisoryDisposition.RECOVERY_READY,
        evidence_ids=("PI-LIVE-1",),
        reason=(
            "Invoice remains in PAYMENT_HOLD. The exact held lot is approved with no transfer."
        ),
        safe_next_step="Manager approval is required before the bounded external recovery.",
        write_performed=False,
    )

    with pytest.raises(advisory_module.AdvisoryValidationError, match="completed quality transfer"):
        advisory_module._validate_source_explanation(
            result,
            {
                "invoice_status": "PAYMENT_HOLD",
                "invoice_quantity": 20,
                "erp_accounted_quantity": 20,
                "erp_quality_inspection_quantity": 0,
                "exact_held_lot_transfer_present": True,
                "completed_quality_transfer_present": True,
                "integration_attempt_quantity": 0,
            },
        )


def test_live_invoice_only_case_rejects_transfer_not_present_wording() -> None:
    result = LiveAdvisoryResult(
        disposition=AdvisoryDisposition.RECOVERY_READY,
        evidence_ids=("PI-LIVE-1",),
        reason="Invoice remains in PAYMENT_HOLD. Exact held lot transfer not present.",
        safe_next_step="Manager approval is required before the bounded external recovery.",
        write_performed=False,
    )

    with pytest.raises(advisory_module.AdvisoryValidationError, match="completed quality transfer"):
        advisory_module._validate_source_explanation(
            result,
            {
                "invoice_status": "PAYMENT_HOLD",
                "invoice_quantity": 20,
                "erp_accounted_quantity": 20,
                "erp_quality_inspection_quantity": 0,
                "completed_quality_transfer_present": True,
                "integration_attempt_quantity": 0,
            },
        )


def test_live_invoice_only_case_rejects_false_need_for_more_evidence() -> None:
    result = LiveAdvisoryResult(
        disposition=AdvisoryDisposition.RECOVERY_READY,
        evidence_ids=("PI-LIVE-1", "MAT-STE-LIVE-1"),
        reason=(
            "ERP inventory is fully reconciled at 20 units, the completed quality transfer "
            "is present, and only the invoice remains in PAYMENT_HOLD. The integration "
            "attempt quantity is 0.0, which is a mismatch. This requires further evidence."
        ),
        safe_next_step="Manager approval is required before the bounded external recovery.",
        write_performed=False,
    )

    with pytest.raises(
        advisory_module.AdvisoryValidationError,
        match="deterministic recovery readiness",
    ):
        advisory_module._validate_source_explanation(
            result,
            {
                "invoice_status": "PAYMENT_HOLD",
                "invoice_quantity": 20,
                "erp_accounted_quantity": 20,
                "erp_quality_inspection_quantity": 0,
                "completed_quality_transfer_present": True,
                "integration_attempt_quantity": 0,
            },
        )


def test_verified_case_packet_requires_recovery_complete() -> None:
    platform = AmbiguousCasePlatform()
    platform.diagnose()
    approved = platform.approve("manager-4817")
    platform.execute(str(approved["execution"]["approval_id"]), "m20-verified-packet")
    verified = platform.verify()

    packet = live_recovery_packet(verified)

    assert packet["expected_disposition"] == "RECOVERY_COMPLETE"
    assert packet["tool_payload"]["sources"]["read_control_context"]["expected_disposition"] == (
        "RECOVERY_COMPLETE"
    )
    assert (
        packet["tool_payload"]["sources"]["read_control_context"]["expected_safe_next_step"]
        == "No recovery action remains; review the verified resolution packet."
    )


def test_competition_packet_starts_unsolved_and_switches_after_execution() -> None:
    platform = AmbiguousCasePlatform()
    initial = competition_investigation_packet(platform.current())
    assert initial["case_class"] == "source_investigation"
    assert initial["case_id"] == "M20-PO-4817"
    assert initial["tool_payload"]["sources"]["read_erp_evidence"]["invoice"]["id"] == "INV-4817"
    assert (
        initial["tool_payload"]["sources"]["read_airtable_evidence"]["quality_records"][0]["lot"]
        == "LOT-4817-QA"
    )
    assert (
        initial["tool_payload"]["sources"]["read_control_context"]["alert"]["root_cause"]
        == "UNKNOWN"
    )
    operating_context = initial["tool_payload"]["sources"]["read_control_context"][
        "connected_operations"
    ]
    assert operating_context["risk_signal"]["band"] == "CRITICAL"
    assert operating_context["customer_commitments"]["revenue_at_risk"] == 900000.0
    assert len(operating_context["history"]) == 90

    platform.diagnose()
    approved = platform.approve("manager-4817")
    executing = platform.execute(
        str(approved["execution"]["approval_id"]), "m20-competition-packet"
    )
    post_execution = competition_investigation_packet(executing)
    assert post_execution["case_class"] == "ambiguous_receipt"
    assert post_execution["expected_disposition"] == "DENY"


def test_connected_competition_packet_exposes_fresh_external_read_receipts() -> None:
    projection = AmbiguousCasePlatform().current()
    erp = {
        "status": "CONNECTED",
        "provider": "ERPNext / Frappe Cloud",
        "sequence": 31,
        "received_at": "2026-09-07T05:00:00Z",
        "documents": [
            {"kind": "purchase_order", "name": "PUR-ORD-2026-00011"},
            {"kind": "purchase_receipt", "name": "MAT-PRE-2026-00001"},
            {"kind": "purchase_invoice", "name": "ACC-PINV-2026-00007"},
        ],
    }
    saas = {
        "status": "CONNECTED",
        "sequence": 44,
        "received_at": "2026-09-07T05:00:01Z",
        "sources": [
            {
                "source_id": "airtable-quality-registry",
                "provider": "Airtable · Supplier Quality Registry",
                "record_id": "rec-real-4817",
                "status": "VERIFIED",
                "read_only": True,
            },
            {
                "source_id": "celigo-quality-release",
                "provider": "Celigo · quality.release",
                "record_id": "run-real-4817",
                "status": "VERIFIED",
                "read_only": True,
            },
            {
                "source_id": "jira-capa",
                "provider": "Jira · CAPA",
                "record_id": "QRC-1",
                "status": "VERIFIED",
                "read_only": True,
            },
            {
                "source_id": "slack-quality-alerts",
                "provider": "Slack · #quality-release-incidents",
                "record_id": "1788480444.928749",
                "status": "VERIFIED",
                "read_only": True,
            },
        ],
    }

    packet = connected_competition_investigation_packet(
        projection, erp_evidence=erp, saas_evidence=saas
    )

    assert packet["source"] == "connected-demo-evidence"
    assert packet["connected_sources"] == 5
    assert "PUR-ORD-2026-00011" in packet["evidence_ids"]
    assert "rec-real-4817" in packet["evidence_ids"]
    sources = packet["tool_payload"]["sources"]
    assert sources["read_erp_evidence"]["live_read"]["sequence"] == 31
    assert sources["read_airtable_evidence"]["live_read"]["record_id"] == "rec-real-4817"
    assert sources["read_celigo_evidence"]["live_read"]["record_id"] == "run-real-4817"
    collaboration = sources["read_collaboration_evidence"]["live_reads"]
    assert {item["source_id"] for item in collaboration} == {
        "jira-capa",
        "slack-quality-alerts",
    }


@pytest.mark.parametrize(
    ("variant", "expected"),
    [
        ("uncommitted_receipt", "RECOVERY_READY"),
        ("lost_ack", "DENY"),
        ("wrong_quality_lot", "DENY"),
        ("lookup_unavailable", "NEEDS_EVIDENCE"),
        ("physical_shortage", "DENY"),
        ("transfer_already_present", "DENY"),
        ("evidence_conflict", "NEEDS_EVIDENCE"),
        ("duplicate_invoice", "DENY"),
        ("unit_price_variance", "DENY"),
        ("uom_conversion_missing", "NEEDS_EVIDENCE"),
        ("po_revision_race", "NEEDS_EVIDENCE"),
        ("supplier_hold", "DENY"),
        ("lot_trace_mismatch", "DENY"),
    ],
)
def test_competition_packet_keeps_selected_counterfactual_source_truth(
    variant: str, expected: str
) -> None:
    platform = AmbiguousCasePlatform()
    projection = platform.reset_variant(variant)

    packet = competition_investigation_packet(projection)

    assert packet["expected_disposition"] == expected
    assert packet["case_id"] == projection["case_id"]
