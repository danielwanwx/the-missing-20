from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

import pytest

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
