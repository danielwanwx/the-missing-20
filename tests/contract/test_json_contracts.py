import json
from pathlib import Path
from typing import Any, cast

import pytest

from the_missing_20.domain.enterprise import (
    BusinessEffect,
    EnterpriseMutationResult,
    EnterpriseSnapshot,
    ErpReceipt,
    FailedReceiptMessage,
    Invoice,
    MaterialDocument,
    PurchaseOrderLine,
    ScenarioFixture,
    WarehouseReceipt,
)
from the_missing_20.domain.events import CaseEvent, TransitionCommand
from the_missing_20.domain.execution import (
    DetectionGenesis,
    ExecutionAttempt,
    PolicyDecision,
    ReleaseInvoiceParameters,
    RestartReceiptMessageParameters,
)
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

CONTRACTS_FILES = (
    Path("fixtures/contracts/public-contracts.json"),
    Path("fixtures/contracts/milestone-2-contracts.json"),
)
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
    "PolicyDecision": PolicyDecision,
    "ExecutionAttempt": ExecutionAttempt,
    "RestartReceiptMessageParameters": RestartReceiptMessageParameters,
    "ReleaseInvoiceParameters": ReleaseInvoiceParameters,
    "DetectionGenesis": DetectionGenesis,
    "PurchaseOrderLine": PurchaseOrderLine,
    "WarehouseReceipt": WarehouseReceipt,
    "FailedReceiptMessage": FailedReceiptMessage,
    "ErpReceipt": ErpReceipt,
    "Invoice": Invoice,
    "MaterialDocument": MaterialDocument,
    "BusinessEffect": BusinessEffect,
    "EnterpriseSnapshot": EnterpriseSnapshot,
    "ScenarioFixture": ScenarioFixture,
    "EnterpriseMutationResult": EnterpriseMutationResult,
}


@pytest.fixture(scope="module")
def contract_examples() -> dict[str, dict[str, Any]]:
    examples: dict[str, dict[str, Any]] = {}
    for path in CONTRACTS_FILES:
        examples.update(
            cast(dict[str, dict[str, Any]], json.loads(path.read_text(encoding="utf-8")))
        )
    return examples


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
