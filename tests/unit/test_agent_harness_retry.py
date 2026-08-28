from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from the_missing_20.agents.harness import _run_checked_once
from the_missing_20.agents.validation import AgentValidationError


@dataclass(frozen=True)
class StageResult:
    retry_count: int = 0


def test_validation_failure_allows_only_one_total_retry() -> None:
    calls = 0

    async def operation() -> StageResult:
        nonlocal calls
        calls += 1
        return StageResult()

    def reject(_result: StageResult) -> StageResult:
        raise AgentValidationError("invalid structured evidence")

    with pytest.raises(AgentValidationError, match="invalid structured evidence"):
        asyncio.run(_run_checked_once(operation, reject))

    assert calls == 2


def test_provider_failure_allows_only_one_total_retry() -> None:
    calls = 0

    async def operation() -> StageResult:
        nonlocal calls
        calls += 1
        raise ValueError("provider output failed")

    with pytest.raises(ValueError, match="provider output failed"):
        asyncio.run(_run_checked_once(operation, lambda result: result))

    assert calls == 2
