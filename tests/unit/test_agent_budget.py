from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from strands.models import BedrockModel

from the_missing_20.adapters.strands_models import BudgetedModel
from the_missing_20.ports.agent_model import AgentBudget, AgentBudgetExceeded, AgentBudgetLedger


class FakeProvider:
    """Offline delegate whose counter represents the network boundary."""

    def __init__(self, *, input_tokens: int = 1, output_tokens: int = 1) -> None:
        self.calls = 0
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens

    def update_config(self, **model_config: Any) -> None:
        del model_config

    def get_config(self) -> dict[str, Any]:
        return {}

    async def count_tokens(self, *args: Any, **kwargs: Any) -> int:
        del args, kwargs
        return 1

    async def stream(self, *args: Any, **kwargs: Any) -> AsyncGenerator[dict[str, Any], None]:
        del args, kwargs
        self.calls += 1
        yield {
            "metadata": {
                "usage": {
                    "inputTokens": self.input_tokens,
                    "outputTokens": self.output_tokens,
                }
            }
        }


async def _consume(model: BudgetedModel) -> None:
    async for _event in model.stream([], None):
        pass


def test_request_cap_is_reserved_before_delegate_network_boundary() -> None:
    budget = AgentBudget(max_requests=40, max_input_tokens=200, max_output_tokens=100)
    delegate = FakeProvider()
    model = BudgetedModel(delegate, AgentBudgetLedger(budget))

    for _ in range(40):
        asyncio.run(_consume(model))

    with pytest.raises(AgentBudgetExceeded, match="request"):
        asyncio.run(_consume(model))
    assert delegate.calls == 40


def test_token_cap_blocks_next_delegate_call_after_metadata_usage() -> None:
    budget = AgentBudget(max_requests=10, max_input_tokens=200, max_output_tokens=10)
    delegate = FakeProvider(input_tokens=136, output_tokens=1)
    model = BudgetedModel(delegate, AgentBudgetLedger(budget))

    asyncio.run(_consume(model))
    with pytest.raises(AgentBudgetExceeded, match="input-token"):
        asyncio.run(_consume(model))
    assert delegate.calls == 1


class BedrockTransport:
    """Capture the actual SDK request at an offline external-service boundary."""

    def __init__(self) -> None:
        self.meta = SimpleNamespace(region_name="us-west-2")
        self.requests: list[dict[str, Any]] = []

    def converse(self, **request: Any) -> dict[str, Any]:
        self.requests.append(request)
        return {
            "output": {"message": {"role": "assistant", "content": [{"text": "ok"}]}},
            "stopReason": "end_turn",
            "usage": {"inputTokens": 2, "outputTokens": 1, "totalTokens": 3},
            "metrics": {"latencyMs": 1},
        }


class BedrockSession:
    region_name = "us-west-2"

    def __init__(self, transport: BedrockTransport) -> None:
        self.transport = transport

    def client(self, **kwargs: Any) -> BedrockTransport:
        del kwargs
        return self.transport


def test_bedrock_budget_counts_provider_input_without_local_event_loop_trace() -> None:
    transport = BedrockTransport()
    delegate = BedrockModel(
        boto_session=BedrockSession(transport),
        model_id="us.amazon.nova-pro-v1:0",
        streaming=False,
        max_tokens=100,
    )
    budget = AgentBudget(
        incremental_cost_cap_usd=Decimal("0.08"),
        cumulative_cost_cap_usd=Decimal("0.08"),
        prior_cost_usd=Decimal("0"),
    )
    model = BudgetedModel(delegate, AgentBudgetLedger(budget))

    async def consume() -> None:
        async for _event in model.stream(
            [{"role": "user", "content": [{"text": "Inspect the returned evidence."}]}],
            invocation_state={"event_loop_cycle_trace": "local trace " * 10_000},
            model_state={"local_state": "not a provider message " * 10_000},
        ):
            pass

    asyncio.run(consume())
    assert len(transport.requests) == 1
    assert transport.requests[0]["messages"] == [
        {"role": "user", "content": [{"text": "Inspect the returned evidence."}]}
    ]
    assert "invocation_state" not in transport.requests[0]
    assert "model_state" not in transport.requests[0]
    assert model.ledger.snapshot()["input_tokens"] == 2


@pytest.mark.parametrize("large_field", ["message", "system", "tool", "configuration"])
def test_bedrock_wire_content_still_exhausts_the_budget_before_provider_io(
    large_field: str,
) -> None:
    transport = BedrockTransport()
    delegate = BedrockModel(
        boto_session=BedrockSession(transport),
        model_id="us.amazon.nova-pro-v1:0",
        streaming=False,
        max_tokens=100,
    )
    model = BudgetedModel(
        delegate,
        AgentBudgetLedger(AgentBudget(max_input_tokens=2_000, max_output_tokens=100)),
    )
    content = "物理收货" * 2_000
    if large_field == "configuration":
        delegate.update_config(additional_args={"requestMetadata": {"context": content}})

    async def consume() -> None:
        async for _event in model.stream(
            [
                {
                    "role": "user",
                    "content": [{"text": content if large_field == "message" else "ok"}],
                }
            ],
            tool_specs=[
                {
                    "name": "read_evidence",
                    "description": content if large_field == "tool" else "Read evidence.",
                    "inputSchema": {"json": {"type": "object", "properties": {}}},
                }
            ],
            system_prompt=content if large_field == "system" else "Use supported evidence.",
        ):
            pass

    with pytest.raises(AgentBudgetExceeded, match="input-token"):
        asyncio.run(consume())
    assert not transport.requests
