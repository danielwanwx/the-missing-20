"""Focused tests for the AgentCore structured-output transport contract."""

from __future__ import annotations

import asyncio
import json

import pytest
from pydantic import BaseModel
from strands import Agent, tool
from strands.tools.structured_output import convert_pydantic_to_tool_spec
from strands.types.agent import Limits

from the_missing_20.adapters.strands_models import (
    AgentCoreRuntimeConfig,
    AgentCoreRuntimeModel,
)
from the_missing_20.ports.agent_model import AgentProviderUnavailable, AgentStage


class FakeStructuredResult(BaseModel):
    finding: str
    confidence: float


class SingletonOutputResult(BaseModel):
    output: str


def _model() -> AgentCoreRuntimeModel:
    return AgentCoreRuntimeModel(
        config=AgentCoreRuntimeConfig(
            runtime_arn="arn:aws:bedrock-agentcore:us-west-2:123456789012:runtime/fake"
        ),
        stage=AgentStage.SYNTHESIS,
    )


def _structured_tool_spec() -> dict[str, object]:
    return convert_pydantic_to_tool_spec(FakeStructuredResult)


async def _first_structured_output(
    model: AgentCoreRuntimeModel,
) -> dict[str, object]:
    return await anext(
        model.structured_output(
            FakeStructuredResult,
            [{"role": "user", "content": [{"text": "Summarize this incident."}]}],
        )
    )


def test_structured_output_sends_canonical_schema_to_fake_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = _model()
    captured_prompts: list[str] = []

    def fake_invoke(prompt: str) -> tuple[object, int, int]:
        captured_prompts.append(prompt)
        return {"output": {"finding": "queue lag", "confidence": 0.91}}, 12, 8

    monkeypatch.setattr(model, "_invoke", fake_invoke)

    event = asyncio.run(_first_structured_output(model))

    assert event["output"] == FakeStructuredResult(finding="queue lag", confidence=0.91)
    assert len(captured_prompts) == 1
    schema = json.dumps(
        FakeStructuredResult.model_json_schema(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    assert schema in captured_prompts[0]
    assert "Return exactly one JSON object that validates against this JSON Schema." in (
        captured_prompts[0]
    )
    assert len(schema.encode("utf-8")) <= model.MAX_STRUCTURED_SCHEMA_BYTES


def test_invalid_fake_runtime_response_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = _model()

    def fake_invoke(prompt: str) -> tuple[object, int, int]:
        del prompt
        return {"output": {"unexpected": "not the contract"}}, 12, 8

    monkeypatch.setattr(model, "_invoke", fake_invoke)

    with pytest.raises(AgentProviderUnavailable, match="invalid structured response"):
        asyncio.run(_first_structured_output(model))


def test_factory_preserves_frozen_read_plan_and_emits_it_before_remote(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from the_missing_20.adapters.strands_models import AgentCoreRuntimeFactory

    factory = AgentCoreRuntimeFactory(
        config=AgentCoreRuntimeConfig(
            runtime_arn="arn:aws:bedrock-agentcore:us-west-2:123456789012:runtime/fake"
        )
    )
    plan = (
        {"tool": "read_admitted_evidence", "arguments": {"evidence_id": "e-1"}},
    )
    model = factory.create(
        stage=AgentStage.RETRYABLE_INVESTIGATOR,
        output_payload={},
        tool_plan=plan,
    )
    assert model._tool_plan == plan

    def fail_remote(prompt: str) -> tuple[object, int, int]:
        del prompt
        raise AssertionError("read-tool turns must not call AgentCore")

    monkeypatch.setattr(model, "_invoke", fail_remote)
    events = asyncio.run(
        _collect_stream(
            model,
            messages=[{"role": "user", "content": [{"text": "Investigate."}]}],
            tool_specs=[
                {
                    "name": "read_admitted_evidence",
                    "description": "read",
                    "inputSchema": {"json": {"type": "object"}},
                },
                _structured_tool_spec(),
            ],
        )
    )
    assert events[1]["contentBlockStart"]["start"]["toolUse"]["name"] == (
        "read_admitted_evidence"
    )
    assert json.loads(events[2]["contentBlockDelta"]["delta"]["toolUse"]["input"]) == {
        "evidence_id": "e-1"
    }
    assert events[4]["messageStop"]["stopReason"] == "tool_use"


async def _collect_stream(
    model: AgentCoreRuntimeModel,
    *,
    messages: list[dict[str, object]],
    tool_specs: list[dict[str, object]],
) -> list[dict[str, object]]:
    return [
        event
        async for event in model.stream(
            messages,
            tool_specs=tool_specs,
        )
    ]


def test_outer_strands_loop_executes_reads_then_one_structured_runtime_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = _model_with_plan(
        ({"tool": "read_admitted_evidence", "arguments": {"evidence_id": "e-1"}},)
    )
    calls: list[str] = []

    def fake_invoke(prompt: str) -> tuple[object, int, int]:
        calls.append(prompt)
        return {"output": {"finding": "queue lag", "confidence": 0.91}}, 12, 8

    monkeypatch.setattr(model, "_invoke", fake_invoke)

    @tool
    def read_admitted_evidence(evidence_id: str) -> dict[str, str]:
        return {"evidence_id": evidence_id}

    async def invoke() -> object:
        agent = Agent(
            model=model,
            tools=[read_admitted_evidence],
            system_prompt="Use only the read tool.",
            callback_handler=None,
        )
        return await agent.invoke_async(
            "Investigate this case.",
            structured_output_model=FakeStructuredResult,
            structured_output_prompt="Return the result now.",
            limits=Limits(turns=5, output_tokens=1_000, total_tokens=3_000),
        )

    result = asyncio.run(invoke())
    assert result.structured_output == FakeStructuredResult(finding="queue lag", confidence=0.91)
    assert len(calls) == 1
    assert "APPLICATION-OWNED STRUCTURED TOOL CONTRACT" in calls[0]
    assert '"finding"' in calls[0]
    assert '"confidence"' in calls[0]
    assert "request_id" not in calls[0]


def test_structured_stream_uses_exact_input_schema_and_candidate_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = _model()
    captured_prompts: list[str] = []
    candidate = {"finding": "queue lag", "confidence": 0.91}

    def fake_invoke(prompt: str) -> tuple[object, int, int]:
        captured_prompts.append(prompt)
        return {"output": candidate, "metadata": {"request_id": "must-not-escape"}}, 12, 8

    monkeypatch.setattr(model, "_invoke", fake_invoke)
    spec = _structured_tool_spec()
    events = asyncio.run(
        _collect_stream(
            model,
            messages=[{"role": "user", "content": [{"text": "Summarize."}]}],
            tool_specs=[spec],
        )
    )
    expected_schema = json.dumps(
        spec["inputSchema"],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    assert len(captured_prompts) == 1
    assert expected_schema in captured_prompts[0]
    assert events[1]["contentBlockStart"]["start"]["toolUse"]["name"] == (
        "FakeStructuredResult"
    )
    assert json.loads(events[2]["contentBlockDelta"]["delta"]["toolUse"]["input"]) == candidate
    assert "must-not-escape" not in json.dumps(events, sort_keys=True)


def test_runtime_envelope_does_not_unwrap_valid_singleton_output_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = _model()

    def fake_invoke(prompt: str) -> tuple[object, int, int]:
        del prompt
        return {
            "output": {"output": "application result"},
            "metadata": {"request_id": "must-not-escape"},
        }, 12, 8

    monkeypatch.setattr(model, "_invoke", fake_invoke)
    events = asyncio.run(
        _collect_stream(
            model,
            messages=[{"role": "user", "content": [{"text": "Summarize."}]}],
            tool_specs=[convert_pydantic_to_tool_spec(SingletonOutputResult)],
        )
    )
    assert json.loads(events[2]["contentBlockDelta"]["delta"]["toolUse"]["input"]) == {
        "output": "application result"
    }


def _model_with_plan(plan: tuple[dict[str, object], ...]) -> AgentCoreRuntimeModel:
    return AgentCoreRuntimeModel(
        config=AgentCoreRuntimeConfig(
            runtime_arn="arn:aws:bedrock-agentcore:us-west-2:123456789012:runtime/fake"
        ),
        stage=AgentStage.RETRYABLE_INVESTIGATOR,
        tool_plan=plan,  # type: ignore[arg-type]
    )


def test_structured_stream_rejects_non_object_and_never_renders_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = _model()

    def fake_invoke(prompt: str) -> tuple[object, int, int]:
        del prompt
        return {
            "output": ["not", "an", "object"],
            "metadata": {"request_id": "must-not-escape"},
        }, 12, 8

    monkeypatch.setattr(model, "_invoke", fake_invoke)
    with pytest.raises(AgentProviderUnavailable, match="invalid structured output"):
        asyncio.run(
            _collect_stream(
                model,
                messages=[{"role": "user", "content": [{"text": "Summarize."}]}],
                tool_specs=[_structured_tool_spec()],
            )
        )


def test_text_stream_extracts_output_without_provider_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = _model()

    def fake_invoke(prompt: str) -> tuple[object, int, int]:
        del prompt
        return {"output": "safe advisory", "metadata": {"request_id": "secret"}}, 12, 8

    monkeypatch.setattr(model, "_invoke", fake_invoke)
    events = asyncio.run(
        _collect_stream(
            model,
            messages=[{"role": "user", "content": [{"text": "Explain."}]}],
            tool_specs=[],
        )
    )
    assert events[2]["contentBlockDelta"]["delta"]["text"] == "safe advisory"
    assert "secret" not in json.dumps(events, sort_keys=True)
