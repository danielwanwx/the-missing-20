import asyncio
from types import SimpleNamespace

import pytest
import strands
from test_receiving_advisory import partial_receipt

from the_missing_20.adapters.ambiguous_case_platform import AmbiguousCasePlatform
from the_missing_20.adapters.live_advisory_gateway import competition_investigation_packet
from the_missing_20.agents import live_advisory as advisory


def test_final_tool_requires_source_reads_and_reconciliation():
    calls = ["read_erp_evidence"]
    gate = advisory._EvidenceCompletionHook(
        calls, (*advisory.SOURCE_TOOL_NAMES, advisory.CORRELATION_TOOL_NAME)
    )
    premature = SimpleNamespace(tool_use={"name": "LiveAdvisoryResult"}, cancel_tool=False)
    gate.before_tool(premature)
    assert "read_collaboration_evidence" in premature.cancel_tool
    assert "RECOVERY_READY" not in premature.cancel_tool
    ordinary = SimpleNamespace(tool_use={"name": "read_celigo_evidence"}, cancel_tool=False)
    gate.before_tool(ordinary)
    assert ordinary.cancel_tool is False
    calls.extend((*advisory.SOURCE_TOOL_NAMES, advisory.CORRELATION_TOOL_NAME))
    complete = SimpleNamespace(tool_use={"name": "LiveAdvisoryResult"}, cancel_tool=False)
    gate.before_tool(complete)
    assert complete.cancel_tool is False


def test_partial_end_turn_keeps_readers_available_before_typed_synthesis(monkeypatch):
    invocations = []

    class Agent:
        def __init__(self, **kwargs):
            assert kwargs.get("structured_output_model") is None
            self.tools = kwargs["tools"]

        async def invoke_async(self, prompt, **kwargs):
            invocations.append(kwargs)
            if len(invocations) == 1:
                assert kwargs.get("structured_output_model") is None
                self.tools[1]()  # ERP only; ordinary end_turn must not force final-only mode.
                return SimpleNamespace(structured_output=None, stop_reason="end_turn")
            if len(invocations) == 2:
                assert kwargs.get("structured_output_model") is None
                for tool in self.tools:
                    tool()
                return SimpleNamespace(structured_output=None, stop_reason="end_turn")
            assert kwargs["structured_output_model"] is advisory.LiveAdvisoryResult
            return SimpleNamespace(
                structured_output=advisory.LiveAdvisoryResult(
                    disposition=advisory.AdvisoryDisposition.RECOVERY_READY,
                    evidence_ids=("ERP-READ-4817", "QA-901", "ATTEMPT-551", "SCAN-703"),
                    reason="100 arrived; ERP accounts for 88 including 8 quality-held units. "
                    "The 12-unit receipt key is confirmed absent. The exact held lot is "
                    "approved and its transfer absent, so these are two separate effects.",
                    safe_next_step="Request Manager approval for the bounded receipt "
                    "and quality transfer.",
                    write_performed=False,
                )
            )

    monkeypatch.setattr(strands, "Agent", Agent)
    factory = SimpleNamespace(
        create=lambda **kwargs: None,
        ledger=SimpleNamespace(snapshot=lambda: {}),
        provenance=lambda: {"provider": "offline-contract-test"},
    )
    packet = competition_investigation_packet(AmbiguousCasePlatform().current())
    run = asyncio.run(advisory._invoke(packet, factory=factory, question="Investigate."))
    assert len(invocations) == 3
    assert set(advisory.SOURCE_TOOL_NAMES).issubset(run.tool_calls)


@pytest.mark.parametrize("history_requested", [False, True])
@pytest.mark.parametrize("complete", [True, False])
@pytest.mark.parametrize("stop_reason", [None, "limit_total_tokens", "limit_output_tokens"])
def test_receiving_acquires_sources_before_structured_output(
    monkeypatch,
    complete,
    stop_reason,
    history_requested,
):
    invocations = []

    class Agent:
        def __init__(self, **kwargs):
            self.tools = kwargs["tools"]
            assert len(self.tools) == 5 + history_requested

        async def invoke_async(self, prompt, **kwargs):
            invocations.append(kwargs)
            if len(invocations) <= 2:
                assert kwargs.get("structured_output_model") is None
                if len(invocations) == 1 or not complete:
                    self.tools[1]()
                else:
                    for tool in self.tools:
                        tool()
                return SimpleNamespace(structured_output=None, stop_reason="end_turn")
            assert complete and kwargs["structured_output_model"] is advisory.LiveAdvisoryResult
            assert kwargs["limits"]["total_tokens"] == 80_000
            assert kwargs["limits"]["output_tokens"] == 4 * advisory.ADVISORY_OUTPUT_TOKENS
            assert '"PO", "PR"' in kwargs["structured_output_prompt"]
            assert "SAFE_NOOP" not in kwargs["structured_output_prompt"]
            if stop_reason:
                return SimpleNamespace(structured_output=None, stop_reason=stop_reason)
            return SimpleNamespace(
                structured_output=advisory.LiveAdvisoryResult(
                    disposition=advisory.AdvisoryDisposition.SAFE_NOOP,
                    evidence_ids=("PO", "PR"),
                    reason="1 of 40 Box is received and posted; 39 remain on order, not lost. "
                    "No invoice exists yet. The receipt needs no retry.",
                    safe_next_step="Monitor further arrivals without writing or changing stock.",
                    write_performed=False,
                )
            )

    monkeypatch.setattr(strands, "Agent", Agent)
    factory = SimpleNamespace(
        create=lambda **kwargs: None,
        ledger=SimpleNamespace(snapshot=lambda: {}),
        provenance=lambda: {"provider": "offline-contract-test"},
    )
    packet = advisory.live_recovery_packet(partial_receipt())
    packet["tool_payload"]["sources"][advisory.HISTORY_TOOL_NAME] = {
        "evidence_ids": ["HISTORY-1"],
        "case_id": packet["case_id"],
        "points": [],
    }
    packet["evidence_ids"] = (*packet["evidence_ids"], "HISTORY-1")
    question = "Prior conversation: show trends. Newest human question: " + (
        "Show the receiving trend" if history_requested else "Are 39 boxes missing?"
    )
    invocation = advisory._invoke(packet, factory=factory, question=question)
    if complete and stop_reason:
        with pytest.raises(advisory.AdvisoryUnavailable) as failure:
            asyncio.run(invocation)
        assert failure.value.diagnostics == [
            {
                "stage": "budget",
                "stop_reason": stop_reason,
                "failure": "SdkInvocationLimit",
            }
        ]
    elif complete:
        run = asyncio.run(invocation)
        assert set(packet["required_tools"]).issubset(run.tool_calls)
        assert len(invocations) == 3
    else:
        with pytest.raises(advisory.AdvisoryUnavailable, match="acquisition did not complete"):
            asyncio.run(invocation)
        assert len(invocations) == 2


def test_receiving_rejects_notification_copies_as_stock_authority(monkeypatch):
    typed_calls = []

    class Agent:
        def __init__(self, **kwargs):
            self.tools = kwargs["tools"]

        async def invoke_async(self, prompt, **kwargs):
            if not kwargs.get("structured_output_model"):
                for reader in self.tools:
                    reader()
                return SimpleNamespace(structured_output=None, stop_reason="end_turn")
            typed_calls.append(prompt)
            reason = (
                "Receipt verified by ERP, Airtable, Celigo, and collaboration tools."
                if len(typed_calls) == 1
                else "ERP receipt PR proves posted stock. Airtable and Celigo are notification "
                "copies, not independent stock verification."
            )
            return SimpleNamespace(
                structured_output=advisory.LiveAdvisoryResult(
                    disposition=advisory.AdvisoryDisposition.SAFE_NOOP,
                    evidence_ids=("PO", "PR"),
                    reason=reason,
                    safe_next_step="Monitor arrivals without retrying the posted receipt.",
                    write_performed=False,
                )
            )

    monkeypatch.setattr(strands, "Agent", Agent)
    factory = SimpleNamespace(
        create=lambda **kwargs: None,
        ledger=SimpleNamespace(snapshot=lambda: {}),
        provenance=lambda: {"provider": "offline-contract-test"},
    )
    run = asyncio.run(
        advisory._invoke(
            advisory.live_recovery_packet(partial_receipt()),
            factory=factory,
            question="Which records verify this receipt?",
        )
    )
    assert len(typed_calls) == 2
    assert "authority boundary" in typed_calls[1]
    assert run.usage["validation_retries"] == 1
    assert "notification copies" in run.result.reason
