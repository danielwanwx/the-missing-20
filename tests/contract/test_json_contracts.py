import json
from pathlib import Path
from typing import Any, cast

import pytest

from the_missing_20.domain.events import CaseEvent, TransitionCommand
from the_missing_20.domain.models import (
    ActionGrant,
    Approval,
    Case,
    ClosureFacts,
    ContractModel,
    Discrepancy,
    EvaluationResult,
    EvidenceItem,
    EvidenceProvenance,
    ExecutionReceipt,
    HypothesisResult,
)

CONTRACTS_FILE = Path("fixtures/contracts/public-contracts.json")
MODEL_TYPES: dict[str, type[ContractModel]] = {
    "Discrepancy": Discrepancy,
    "Case": Case,
    "EvidenceProvenance": EvidenceProvenance,
    "EvidenceItem": EvidenceItem,
    "HypothesisResult": HypothesisResult,
    "EvaluationResult": EvaluationResult,
    "Approval": Approval,
    "ActionGrant": ActionGrant,
    "ExecutionReceipt": ExecutionReceipt,
    "ClosureFacts": ClosureFacts,
    "TransitionCommand": TransitionCommand,
    "CaseEvent": CaseEvent,
}


@pytest.fixture(scope="module")
def contract_examples() -> dict[str, dict[str, Any]]:
    return cast(
        dict[str, dict[str, Any]],
        json.loads(CONTRACTS_FILE.read_text(encoding="utf-8")),
    )


def test_every_public_contract_has_an_example(
    contract_examples: dict[str, dict[str, Any]],
) -> None:
    assert contract_examples.keys() == MODEL_TYPES.keys()


@pytest.mark.parametrize("model_name", MODEL_TYPES)
def test_contract_examples_round_trip_as_strict_json(
    model_name: str, contract_examples: dict[str, dict[str, Any]]
) -> None:
    model_type = MODEL_TYPES[model_name]
    encoded = json.dumps(contract_examples[model_name])

    parsed = model_type.model_validate_json(encoded)
    reparsed = model_type.model_validate_json(parsed.model_dump_json())

    assert reparsed == parsed
