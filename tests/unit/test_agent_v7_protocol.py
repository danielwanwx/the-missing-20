from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from the_missing_20.adapters.strands_models import BudgetedModel
from the_missing_20.agents.schemas import (
    AgentEvaluationResult,
    AgentProtocolEnvelope,
    SynthesisResult,
    build_protocol_envelope,
    public_synthesis_result,
    semantic_schema_digest,
    validate_protocol_envelope,
)
from the_missing_20.ports.agent_model import (
    MAX_OUTPUT_TOKENS_PER_REQUEST,
    AgentBudget,
    AgentBudgetExceeded,
    AgentBudgetLedger,
)


def _synthesis_payload() -> dict[str, Any]:
    return {
        "selected_hypothesis": "RETRYABLE_MESSAGE",
        "conclusion": "NEEDS_EVIDENCE",
        "confidence_band": "LOW",
        "factual_claims": [],
    }


def test_provider_schemas_have_only_semantic_model_owned_properties() -> None:
    forbidden_tokens = (
        "version",
        "protocol",
        "schema_digest",
        "prompt",
        "harness",
        "policy",
        "trace",
        "artifact",
    )
    for model in (SynthesisResult, AgentEvaluationResult):
        properties = model.model_json_schema()["properties"]
        assert all(
            not any(token in name.lower() for token in forbidden_tokens) for name in properties
        )


def test_legacy_model_authored_protocol_fields_are_rejected() -> None:
    with pytest.raises(ValidationError, match="synthesis_version"):
        SynthesisResult.model_validate(
            {**_synthesis_payload(), "synthesis_version": "synthesis-v3"}
        )
    with pytest.raises(ValidationError, match="evaluator_version"):
        AgentEvaluationResult.model_validate(
            {
                "decision": "MORE_EVIDENCE",
                "evaluator_version": "evaluator-v3",
            }
        )


def test_protocol_envelope_is_immutable_and_tamper_evident() -> None:
    envelope = build_protocol_envelope(
        prompt_version="agent-v4",
        prompt_digest="prompt-digest",
        knowledge_version="knowledge-v1",
    )
    assert envelope.schema_digest == semantic_schema_digest()
    with pytest.raises(ValidationError):
        envelope.agent_contract_version = "agent-contract/v8"

    tampered = envelope.model_copy(update={"agent_contract_version": "agent-contract/v7"})
    with pytest.raises(ValueError, match="contract version"):
        validate_protocol_envelope(tampered)
    with pytest.raises(ValueError, match="contract version"):
        public_synthesis_result(
            SynthesisResult.model_validate(_synthesis_payload()),
            protocol=tampered,
        )


def test_public_projection_carries_the_same_harness_owned_envelope() -> None:
    envelope = AgentProtocolEnvelope(
        prompt_version="agent-v4",
        prompt_digest="prompt-digest",
        schema_digest=semantic_schema_digest(),
        knowledge_version="knowledge-v1",
    )
    payload = public_synthesis_result(
        SynthesisResult.model_validate(_synthesis_payload()),
        protocol=envelope,
    )
    assert payload["protocol"] == envelope.model_dump(mode="json")


class _Provider:
    def __init__(self, *, usage: dict[str, Any] | None = None) -> None:
        self.calls = 0
        self.usage = usage or {"inputTokens": 0, "outputTokens": 0}

    def update_config(self, **kwargs: Any) -> None:
        del kwargs

    def get_config(self) -> dict[str, Any]:
        return {"max_tokens": MAX_OUTPUT_TOKENS_PER_REQUEST}

    async def count_tokens(self, *args: Any, **kwargs: Any) -> int:
        del args, kwargs
        return 1

    async def stream(self, *args: Any, **kwargs: Any) -> AsyncGenerator[dict[str, Any], None]:
        del args, kwargs
        self.calls += 1
        yield {"metadata": {"usage": self.usage}}


def test_request_reservation_uses_complete_utf8_serialized_request_before_io() -> None:
    messages: Any = [{"role": "user", "content": [{"text": "héllo 世界"}]}]
    serialized_length = BudgetedModel.serialized_request_byte_length(
        messages=messages,
        tool_specs=None,
        system_prompt="system",
        system_prompt_content=None,
        invocation_state=None,
        model_state=None,
        kwargs={},
    )
    expected = len(
        json.dumps(
            {
                "messages": messages,
                "tool_specs": [],
                "system_prompt": "system",
                "system_prompt_content": None,
                "invocation_state": None,
                "model_state": None,
                "kwargs": {},
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    )
    assert serialized_length == expected

    budget = AgentBudget(
        max_requests=1,
        max_input_tokens=serialized_length - 1,
        max_output_tokens=10,
    )
    provider = _Provider()
    model = BudgetedModel(provider, AgentBudgetLedger(budget))
    with pytest.raises(AgentBudgetExceeded, match="input-token"):
        asyncio.run(
            anext(
                model.stream(
                    messages,
                    system_prompt="system",
                )
            )
        )
    assert provider.calls == 0


def test_concurrent_reservations_and_cost_boundary_are_atomic() -> None:
    budget = AgentBudget(
        max_requests=2,
        max_input_tokens=10_000,
        max_output_tokens=3_970,
        prior_cost_usd=Decimal("0.0258576"),
        incremental_cost_cap_usd=Decimal("0.0198516"),
        cumulative_cost_cap_usd=Decimal("0.0457092"),
        output_price_per_token=Decimal("0.00001"),
    )
    ledger = AgentBudgetLedger(budget)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _item: _reserve_or_error(ledger), range(2)))
    assert sum(item is None for item in results) == 1
    assert sum(item == "incremental provider cost cap exhausted" for item in results) == 1
    assert ledger.snapshot()["request_count"] == 1


def test_malformed_provider_usage_fails_closed_after_a_reserved_call() -> None:
    budget = AgentBudget(max_requests=1, max_input_tokens=10_000, max_output_tokens=10)
    provider = _Provider(usage={"inputTokens": "not-an-int", "outputTokens": 0})
    model = BudgetedModel(provider, AgentBudgetLedger(budget))

    with pytest.raises(AgentBudgetExceeded, match="malformed"):
        asyncio.run(anext(model.stream([])))
    assert provider.calls == 1
    assert ledger_snapshot_has_budget_error(model.ledger.snapshot())


def _reserve_or_error(ledger: AgentBudgetLedger) -> str | None:
    try:
        ledger.reserve_request(input_token_upper_bound=1, output_token_upper_bound=1_985)
    except AgentBudgetExceeded as exc:
        return str(exc)
    return None


def ledger_snapshot_has_budget_error(snapshot: dict[str, int | float]) -> bool:
    return snapshot["budget_error_count"] == 1
