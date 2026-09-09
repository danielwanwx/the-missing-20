import asyncio
from types import SimpleNamespace

import strands

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
