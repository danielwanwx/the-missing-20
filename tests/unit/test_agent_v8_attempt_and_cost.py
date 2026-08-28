from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path

from the_missing_20.evaluation.provider_claim import (
    V8AttemptAlreadyClaimed,
    claim_digest,
    claim_v8_attempt,
    load_v8_attempt_claim,
)
from the_missing_20.ports.agent_model import (
    CUMULATIVE_COST_CAP_USD,
    INCREMENTAL_COST_CAP_USD,
    MAX_INPUT_TOKENS,
    MAX_OUTPUT_TOKENS,
    MAX_OUTPUT_TOKENS_PER_REQUEST,
    MAX_REQUESTS,
    PRIOR_ESTIMATED_COST_USD,
    AgentBudget,
    AgentBudgetLedger,
)


def test_v8_attempt_claim_is_durable_exclusive_and_prose_free(tmp_path: Path) -> None:
    path = tmp_path / "artifacts/agent/bedrock-attempt-claim-v2.json"
    claim = claim_v8_attempt(path)
    assert load_v8_attempt_claim(path) == claim
    assert claim_digest(claim) == claim.claim_digest
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["agent_contract_version"] == "agent-contract/v8"
    assert payload["prior_cost_usd"] == 0.0551848
    assert payload["output_token_cap"] == 70_240
    assert payload["max_output_tokens_per_request"] == 1_756
    for forbidden in (str(tmp_path), "account", "credential", "password", "MODEL_PROSE"):
        assert forbidden not in path.read_text(encoding="utf-8")
    try:
        claim_v8_attempt(path)
    except V8AttemptAlreadyClaimed:
        pass
    else:  # pragma: no cover - assertion is clearer than a context manager here
        raise AssertionError("a second v8 claim must be refused")


def test_v8_concurrent_claimers_have_one_winner(tmp_path: Path) -> None:
    path = tmp_path / "claim.json"

    def attempt(_index: int) -> object:
        try:
            return claim_v8_attempt(path)
        except V8AttemptAlreadyClaimed:
            return None

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(attempt, range(8)))
    assert sum(item is not None for item in results) == 1
    assert sum(item is None for item in results) == 7


def test_v8_budget_constants_reserve_under_the_cumulative_hard_cap() -> None:
    assert MAX_REQUESTS == 40
    assert MAX_INPUT_TOKENS == 400_000
    assert MAX_OUTPUT_TOKENS == 62_040
    assert MAX_OUTPUT_TOKENS_PER_REQUEST == 1_551
    assert Decimal("0.0814368") == PRIOR_ESTIMATED_COST_USD
    assert Decimal("0.5185632") == INCREMENTAL_COST_CAP_USD
    budget = AgentBudget()
    ledger = AgentBudgetLedger(budget)
    reservations = [
        ledger.reserve_request(
            input_token_upper_bound=MAX_INPUT_TOKENS // MAX_REQUESTS,
            output_token_upper_bound=MAX_OUTPUT_TOKENS_PER_REQUEST,
        )
        for _ in range(MAX_REQUESTS)
    ]
    snapshot = ledger.snapshot()
    assert len(reservations) == MAX_REQUESTS
    assert snapshot["reserved_incremental_cost_usd"] <= float(INCREMENTAL_COST_CAP_USD)
    assert snapshot["reserved_cumulative_cost_usd"] <= float(CUMULATIVE_COST_CAP_USD)
