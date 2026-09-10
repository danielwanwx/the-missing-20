"""Focused offline proof for the native structured contract selector boundary."""

from __future__ import annotations

from typing import Any, cast

from the_missing_20.adapters.distributor_allocation import compile_plan
from the_missing_20.adapters.strands_models import ScriptedStrandsModel
from the_missing_20.agents.distributor_allocation import select_contract_plan
from the_missing_20.ports.agent_model import AgentProvider, AgentStage


class _SelectionFactory:
    provider = AgentProvider.SCRIPTED

    def __init__(self, plan_id: str) -> None:
        self._plan_id = plan_id

    def create(self, **_kwargs: Any) -> ScriptedStrandsModel:
        return ScriptedStrandsModel(
            stage=AgentStage.SYNTHESIS,
            output_payload={
                "plan_id": self._plan_id,
                "rationale": "Date-first terms select the provided plan.",
                "contract_refs": ["SO-DUE"],
            },
        )

    @staticmethod
    def provenance() -> dict[str, object]:
        return {"provider": "scripted"}


def test_native_structured_selector_returns_only_a_candidate_id_with_usage() -> None:
    plan = compile_plan(
        allocations=[
            {
                "customer_order": "SO-DUE",
                "requested_quantity": 10,
                "dispatched": 0,
                "promised_delivery_at": "2026-09-11T09:00:00+00:00",
                "customer_priority": 1,
                "partial_dispatch": True,
                "minimum_dispatch_quantity": 5,
                "allow_final_remainder": True,
            }
        ],
        lots=[{"usable": 10}],
        prepared_picks=[],
    )

    result = select_contract_plan(plan=plan, factory=_SelectionFactory(cast(str, plan["plan_id"])))
    assert result["plan_id"] == plan["plan_id"]
    assert result["contract_refs"] == ["SO-DUE"]
    assert cast(dict[str, object], result["provider"])["provider"] == "scripted"
    assert "elapsed_ms" in cast(dict[str, object], result["usage"])
