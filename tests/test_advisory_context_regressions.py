"""Case reasoning stays bounded, source-grounded, and relevant to the current question."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
import strands

from the_missing_20.adapters.ambiguous_case_platform import AmbiguousCasePlatform
from the_missing_20.adapters.live_advisory_gateway import (
    DashboardAdvisoryGateway,
    competition_investigation_packet,
)
from the_missing_20.agents import live_advisory as advisory
from the_missing_20.config import Settings


def test_case_model_context_excludes_dashboard_history_without_mutating_audit_packet() -> None:
    packet = competition_investigation_packet(AmbiguousCasePlatform().current())
    original = json.dumps(packet, sort_keys=True)
    visible = advisory.model_source_payloads(packet)
    assert "connected_operations" not in visible["read_control_context"]
    assert len(json.dumps(visible)) < 10_000
    assert json.dumps(packet, sort_keys=True) == original


def test_followup_does_not_force_unrelated_component_quantities() -> None:
    captured = []

    def runner(packet, **kwargs):
        captured.append(packet)
        raise advisory.AdvisoryUnavailable("controlled offline stop")

    platform = AmbiguousCasePlatform()
    gateway = DashboardAdvisoryGateway(
        platform,
        settings=Settings.from_env({"MISSING20_AGENT_PROVIDER": "bedrock"}),
        packet_factory=competition_investigation_packet,
        runner=runner,
    )
    gateway.ask("I decline approval. What can we inspect without writing?")
    assert not captured[0].get("expected_reason_quantities")
    assert captured[0]["expected_disposition"] == "RECOVERY_READY"
    gateway.investigate(platform.current())
    assert tuple(captured[1]["expected_reason_quantities"]) == (12, 8)


def test_all_repair_attempts_preserve_independent_reasoning_and_fail_closed(monkeypatch) -> None:
    prompts = []

    class Agent:
        def __init__(self, **kwargs):
            self.tools = kwargs["tools"]

        async def invoke_async(self, prompt, **kwargs):
            prompts.append(prompt)
            if len(prompts) == 1:
                for reader in self.tools:
                    reader()
            return SimpleNamespace(
                structured_output=advisory.LiveAdvisoryResult(
                    disposition=advisory.AdvisoryDisposition.NEEDS_EVIDENCE,
                    evidence_ids=("RCPT-4817-L2-001",),
                    reason="The evidence needs review.",
                    safe_next_step="Request the missing source record.",
                    write_performed=False,
                )
            )

    monkeypatch.setattr(strands, "Agent", Agent)
    factory = SimpleNamespace(
        create=lambda **kwargs: None,
        ledger=SimpleNamespace(snapshot=lambda: {}),
        provenance=lambda: {"provider": "test"},
    )
    packet = advisory.live_recovery_packet(AmbiguousCasePlatform().current())
    with pytest.raises(advisory.AdvisoryValidationError) as failure:
        asyncio.run(advisory._invoke(packet, factory=factory, question="Investigate."))
    assert len(prompts) == 3
    for prompt in prompts[1:]:
        assert "is RECOVERY_READY" not in prompt
        assert "Use that exact disposition" not in prompt
        assert "Copy this exact control-plane sentence" not in prompt
        assert (
            packet["tool_payload"]["sources"]["read_control_context"]["expected_safe_next_step"]
            not in prompt
        )
    assert len(failure.value.diagnostics) == 3


def test_provider_failure_retains_budget_evidence_without_returning_candidate() -> None:
    def runner(*args, **kwargs):
        failure = advisory.AdvisoryUnavailable("bounded provider stop")
        failure.diagnostics = [{"stage": "repair", "failure": "AgentBudgetExceeded"}]
        failure.usage = {"request_count": 3, "incremental_cost_usd": 0.02}
        raise failure

    platform = AmbiguousCasePlatform()
    gateway = DashboardAdvisoryGateway(
        platform,
        settings=Settings.from_env({"MISSING20_AGENT_PROVIDER": "bedrock"}),
        runner=runner,
    )
    result = gateway.investigate(platform.current())
    assert result["result"] is None
    assert result["usage"]["request_count"] == 3
    assert result["validation_diagnostics"][0]["failure"] == "AgentBudgetExceeded"


def test_history_is_case_scoped_bounded_and_separate_from_current_sources() -> None:
    raw = {
        "case_id": "case-1",
        "points": [
            {
                "id": index,
                "case_id": "case-1",
                "source_id": "erp",
                "metrics": {"received": index},
                "credential": "never expose",
            }
            for index in range(36)
        ]
        + [{"id": 99, "case_id": "other", "metrics": {"received": 999}}],
        "baseline": {"status": "INSUFFICIENT_DATA", "industry_benchmark": False},
    }
    original = json.dumps(raw, sort_keys=True)
    history = advisory._operational_history_source(raw, "case-1")
    assert history is not None
    assert len(history["points"]) == 32
    assert history["selection"]["truncated"] is True
    assert history["freshness"] == "HISTORICAL_OBSERVATIONS"
    assert all(point["case_id"] == "case-1" for point in history["points"])
    assert "never expose" not in json.dumps(history)
    assert json.dumps(raw, sort_keys=True) == original
    assert advisory._operational_history_source(raw, "another-case") is None


def test_optional_history_reader_is_not_required_for_current_case_diagnosis() -> None:
    result = advisory.LiveAdvisoryResult(
        disposition=advisory.AdvisoryDisposition.RECOVERY_COMPLETE,
        evidence_ids=("invoice",),
        reason="All 100 units reconcile and invoice is open.",
        safe_next_step="No recovery action; review current records.",
        write_performed=False,
    )
    calls = advisory.SOURCE_TOOL_NAMES + (advisory.CORRELATION_TOOL_NAME,)
    advisory.validate_advisory(
        result, calls=calls, evidence_ids=("invoice",), required_tools=frozenset(calls)
    )
    advisory.validate_advisory(
        result,
        calls=calls + (advisory.HISTORY_TOOL_NAME,),
        evidence_ids=("invoice",),
        required_tools=frozenset(calls),
    )


@pytest.mark.parametrize(
    "reason",
    [
        "Timed-out integration attempt for 12 units, but retrying is denied per policy.",
        "The 12-unit receipt does not exist in ERP; 8 units remain held.",
        "No receipt is posted in ERP for the 12-unit attempt. 8 units remain held.",
    ],
)
def test_recorded_retry_needs_observed_effect_not_just_a_deny_label(reason) -> None:
    result = advisory.LiveAdvisoryResult(
        disposition=advisory.AdvisoryDisposition.DENY,
        evidence_ids=("ERP-READ-4817",),
        reason=reason,
        safe_next_step="Do not retry; inspect the existing record.",
        write_performed=False,
    )
    with pytest.raises(advisory.AdvisoryValidationError, match="recorded receipt"):
        advisory._validate_source_explanation(
            result,
            {
                "integration_business_key_present_in_erp": True,
                "invoice_quantity": 100,
                "erp_accounted_quantity": 100,
                "erp_quality_inspection_quantity": 8,
                "integration_attempt_quantity": 12,
            },
        )


def test_recorded_retry_explanation_preserves_both_outstanding_components() -> None:
    result = advisory.LiveAdvisoryResult(
        disposition=advisory.AdvisoryDisposition.DENY,
        evidence_ids=("ERP-READ-4817", "MAT-403", "QA-901"),
        reason="ERP already recorded the 12-unit receipt despite the timeout. "
        "Do not retry that existing key; the separate 8-unit quality lot is still held.",
        safe_next_step="Do not retry; inspect the recorded effect and separate quality work.",
        write_performed=False,
    )
    advisory._validate_source_explanation(
        result,
        {
            "integration_business_key_present_in_erp": True,
            "invoice_quantity": 100,
            "erp_accounted_quantity": 100,
            "erp_quality_inspection_quantity": 8,
            "integration_attempt_quantity": 12,
        },
    )


def test_source_probe_requests_full_investigation_validation(monkeypatch) -> None:
    from scripts import run_source_investigation_probe as probe

    captured = []

    def run(packet, **kwargs):
        captured.append(packet)
        raise advisory.AdvisoryUnavailable("offline probe-boundary check")

    monkeypatch.setattr(probe, "run_live_advisory", run)
    row = probe._run_variant("lost_ack", 1, Settings.from_env({}))
    assert row["status"] == "FAILED"
    assert captured[0]["explanation_scope"] == "full_investigation"


def test_conflicting_attempt_cannot_be_described_as_matching() -> None:
    result = advisory.LiveAdvisoryResult(
        disposition=advisory.AdvisoryDisposition.NEEDS_EVIDENCE,
        evidence_ids=("attempt",),
        reason="The integration attempt quantity matches the ERP gap.",
        safe_next_step="Inspect the conflicting evidence.",
        write_performed=False,
    )
    with pytest.raises(advisory.AdvisoryValidationError, match="attempt/gap conflict"):
        advisory._validate_source_explanation(
            result,
            {
                "invoice_quantity": 100,
                "erp_accounted_quantity": 88,
                "integration_normalized_quantity": 13,
            },
        )


def test_equal_attempt_and_gap_cannot_be_described_as_a_conflict() -> None:
    result = advisory.LiveAdvisoryResult(
        disposition=advisory.AdvisoryDisposition.DENY,
        evidence_ids=("attempt",),
        reason="The attempted quantity of 12 does not match the ERP gap of 12.",
        safe_next_step="Inspect the physical shortage.",
        write_performed=False,
    )
    with pytest.raises(advisory.AdvisoryValidationError, match="invented an attempt/gap conflict"):
        advisory._validate_source_explanation(
            result,
            {
                "invoice_quantity": 100,
                "erp_accounted_quantity": 88,
                "integration_normalized_quantity": 12,
            },
        )


def test_declined_write_allows_read_only_next_step_but_not_execution() -> None:
    result = advisory.LiveAdvisoryResult(
        disposition=advisory.AdvisoryDisposition.RECOVERY_READY,
        evidence_ids=("receipt",),
        reason="Your decline is respected; no changes will be made.",
        safe_next_step="Inspect the receipt key while keeping changes stopped.",
        write_performed=False,
    )
    kwargs = dict(
        calls=("read_control_context", "read_erp_evidence"),
        evidence_ids=("receipt",),
        expected_disposition=advisory.AdvisoryDisposition.RECOVERY_READY,
        expected_safe_next_step="Manager approval before a write.",
        read_only_requested=True,
    )
    advisory.validate_advisory(result, **kwargs)
    with pytest.raises(advisory.AdvisoryValidationError, match="read-only boundary"):
        advisory.validate_advisory(
            result.model_copy(update={"safe_next_step": "Execute and then review."}), **kwargs
        )
