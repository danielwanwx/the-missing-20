"""One bounded native Strands selection for a compiled customer-contract plan."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from time import monotonic

from pydantic import BaseModel, Field
from strands import Agent
from strands.types.agent import Limits

from the_missing_20.agents.product_language import english_product_text
from the_missing_20.ports.agent_model import (
    AgentBudgetLedger,
    AgentModelFactory,
    AgentStage,
    actual_provider_metadata,
)

ALLOCATION_SELECTION_OUTPUT_TOKENS = 256
# A representative two-order plan plus the generated Pydantic schema is about
# 1,200 input bytes.  Leave room for the native SDK's structured-output turn
# without turning this bounded selection into a general reasoning loop.
ALLOCATION_SELECTION_TOTAL_TOKENS = 2_048


class ContractAllocationSelection(BaseModel):
    """The model may select a supplied plan ID or defer; it cannot author quantities."""

    plan_id: str = Field(min_length=1, max_length=128)
    rationale: str = Field(min_length=1, max_length=480)
    contract_refs: list[str] = Field(default_factory=list, max_length=16)


def select_contract_plan(
    *, plan: Mapping[str, object], factory: AgentModelFactory
) -> dict[str, object]:
    """Use a single structured Nova/Strands turn; the caller validates the result."""

    async def invoke() -> tuple[ContractAllocationSelection, dict[str, object]]:
        model = factory.create(stage=AgentStage.SYNTHESIS, output_payload={})
        agent = Agent(
            model=model,
            system_prompt=(
                "You select only a supplied customer-contract allocation plan. "
                "Do not invent quantities, alter terms, use external facts, or perform writes. "
                "Return the exact plan_id when the fixed date-first contract policy is feasible; "
                "otherwise return DEFER. Write the rationale in concise English-only product text; "
                "do not translate or use another writing system."
            ),
            callback_handler=None,
            retry_strategy=None,
            checkpointing=False,
        )
        response = await agent.invoke_async(
            "Current verified candidate (all quantities are application-calculated):\n"
            + json.dumps(plan, sort_keys=True, ensure_ascii=False)
            + "\nReturn ContractAllocationSelection now. contract_refs must be exact "
            "customer_order identifiers from candidate rows.",
            structured_output_model=ContractAllocationSelection,
            structured_output_prompt=(
                "Return only the complete ContractAllocationSelection. plan_id must be "
                "the candidate plan_id or DEFER. Keep the rationale under 60 words and use "
                "English-only product text."
            ),
            limits=Limits(
                turns=2,
                output_tokens=ALLOCATION_SELECTION_OUTPUT_TOKENS,
                total_tokens=ALLOCATION_SELECTION_TOTAL_TOKENS,
            ),
        )
        result = getattr(response, "structured_output", None)
        if not isinstance(result, ContractAllocationSelection):
            raise ValueError("native allocation selection did not return structured data")
        return result, actual_provider_metadata(model)

    started = monotonic()
    selected, provider = asyncio.run(invoke())
    usage: dict[str, object] = {"elapsed_ms": round((monotonic() - started) * 1000)}
    ledger = getattr(factory, "ledger", None)
    if isinstance(ledger, AgentBudgetLedger):
        usage.update(ledger.snapshot())
    if not provider:
        provenance = getattr(factory, "provenance", None)
        observed = provenance() if callable(provenance) else {}
        provider = dict(observed) if isinstance(observed, Mapping) else {}
    rationale = english_product_text(selected.rationale, field="allocation rationale")
    return {
        "plan_id": selected.plan_id,
        "rationale": rationale,
        "contract_refs": list(selected.contract_refs),
        "provider": provider,
        "usage": usage,
    }
