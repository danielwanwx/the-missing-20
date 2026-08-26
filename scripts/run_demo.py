"""Run the deterministic SQLite-backed main case and write its proof artifact."""

from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from the_missing_20.adapters.clocks import ManualClock
from the_missing_20.adapters.local_signer import LocalSigner
from the_missing_20.adapters.sqlite_case_store import SQLiteCaseStore
from the_missing_20.adapters.synthetic_enterprise import SyntheticEnterprise
from the_missing_20.application.authorization_service import (
    AuthorizationService,
    LocalPolicy,
    TrustedIdentities,
)
from the_missing_20.application.case_service import CaseService
from the_missing_20.application.detector import DiscrepancyDetector
from the_missing_20.application.diagnosis import diagnose_retryable_message
from the_missing_20.application.executor import ControlledExecutor
from the_missing_20.domain.errors import AuthorizationDenied
from the_missing_20.domain.execution import (
    ReleaseInvoiceParameters,
    RestartReceiptMessageParameters,
)
from the_missing_20.domain.models import ActionTool, HumanRole
from the_missing_20.domain.states import CaseStatus

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE = REPOSITORY_ROOT / "fixtures/scenarios/retryable-document-lock.json"
DEFAULT_ARTIFACT = REPOSITORY_ROOT / "artifacts/demo/main-case.json"
BASE_TIME = datetime(2026, 8, 25, 17, 0, tzinfo=UTC)


def _as_json(value: object) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    raise TypeError(f"cannot serialize {type(value)}")


def run_main_case(
    *,
    work_directory: Path,
    fixture_path: Path = DEFAULT_FIXTURE,
    artifact_path: Path | None = None,
) -> dict[str, Any]:
    enterprise_path = work_directory / "enterprise.sqlite"
    case_path = work_directory / "case.sqlite"
    enterprise = SyntheticEnterprise.seed_from_fixture(enterprise_path, fixture_path)
    store = SQLiteCaseStore(case_path)
    identities = TrustedIdentities(
        {
            "operator-001": HumanRole.INTEGRATION_OPERATOR,
            "ap-approver-001": HumanRole.AP_APPROVER,
        }
    )
    signer = LocalSigner(b"synthetic-demo-key-not-for-production")
    clock = ManualClock(BASE_TIME)
    authorization = AuthorizationService(
        store=store, signer=signer, identities=identities, clock=clock
    )
    policy = LocalPolicy(store=store, signer=signer, identities=identities, clock=clock)
    executor = ControlledExecutor(store=store, enterprise=enterprise, policy=policy, clock=clock)
    cases = CaseService(store, clock)
    initial_snapshot = enterprise.read_snapshot()

    detected_case, evidence = DiscrepancyDetector(enterprise, store, clock).detect(
        case_id="case-main-001",
        trace_id="trace-main-001",
        fixture_path=fixture_path,
    )
    hypothesis, evaluation = diagnose_retryable_message(evidence, trace_id="trace-main-001")
    clock.set(BASE_TIME + timedelta(seconds=1))
    case, _ = cases.recommend_receipt_restart(
        case_id=detected_case.case_id,
        expected_version=detected_case.case_version,
        idempotency_key="diagnosis-retryable-message",
        hypothesis=hypothesis,
        evaluation=evaluation,
    )
    clock.set(BASE_TIME + timedelta(seconds=2))
    case, _ = cases.request_receipt_approval(
        case_id=case.case_id,
        expected_version=case.case_version,
        idempotency_key="receipt-approval-requested",
    )

    early_invoice_parameters = ReleaseInvoiceParameters(
        invoice_id=initial_snapshot.invoice.invoice_id,
        invoice_revision=initial_snapshot.invoice.revision,
        purchase_order_id=initial_snapshot.invoice.purchase_order_id,
        line_id=initial_snapshot.invoice.line_id,
        quantity=initial_snapshot.invoice.quantity,
        expected_hold_reason="RECEIPT_MISMATCH",
    )
    effect_count_before_deny = len(enterprise.read_snapshot().business_effects)
    clock.set(BASE_TIME + timedelta(seconds=3))
    try:
        authorization.approve(
            case_id=case.case_id,
            principal_id="ap-approver-001",
            tool=ActionTool.RELEASE_INVOICE,
            parameters=early_invoice_parameters,
            approval_id="approval-early-invoice-deny",
            authorization_id="authorization-early-invoice-deny",
        )
    except AuthorizationDenied:
        pass
    else:
        raise AssertionError("early invoice release must be denied")
    effects_after_deny = enterprise.read_snapshot().business_effects
    early_deny = store.list_policy_decisions(case.case_id)[-1]

    receipt_parameters = RestartReceiptMessageParameters(
        message_id=initial_snapshot.failed_message.message_id,
        message_revision=initial_snapshot.failed_message.revision,
        purchase_order_id=initial_snapshot.failed_message.purchase_order_id,
        line_id=initial_snapshot.failed_message.line_id,
        quantity=initial_snapshot.failed_message.quantity,
        expected_error_code="DOCUMENT_LOCKED_RETRYABLE",
        expected_message_status="FAILED",
    )
    clock.set(BASE_TIME + timedelta(seconds=4))
    receipt_grant = authorization.approve(
        case_id=case.case_id,
        principal_id="operator-001",
        tool=ActionTool.RESTART_RECEIPT_MESSAGE,
        parameters=receipt_parameters,
        approval_id="approval-receipt-001",
        authorization_id="authorization-receipt-001",
    )
    clock.set(BASE_TIME + timedelta(seconds=5))
    receipt, _ = executor.execute(
        authorization_id=receipt_grant.authorization_id,
        principal_id="operator-001",
        parameters=receipt_parameters,
        execution_id="execution-receipt-001",
        idempotency_key="effect-receipt-001",
    )

    case = store.get_case(case.case_id)
    clock.set(BASE_TIME + timedelta(seconds=6))
    case, _ = cases.request_invoice_approval(
        case_id=case.case_id,
        expected_version=case.case_version,
        idempotency_key="invoice-approval-requested",
    )
    after_receipt = enterprise.read_snapshot()
    invoice_parameters = ReleaseInvoiceParameters(
        invoice_id=after_receipt.invoice.invoice_id,
        invoice_revision=after_receipt.invoice.revision,
        purchase_order_id=after_receipt.invoice.purchase_order_id,
        line_id=after_receipt.invoice.line_id,
        quantity=after_receipt.invoice.quantity,
        expected_hold_reason="RECEIPT_MISMATCH",
    )
    clock.set(BASE_TIME + timedelta(seconds=7))
    invoice_grant = authorization.approve(
        case_id=case.case_id,
        principal_id="ap-approver-001",
        tool=ActionTool.RELEASE_INVOICE,
        parameters=invoice_parameters,
        approval_id="approval-invoice-001",
        authorization_id="authorization-invoice-001",
    )
    clock.set(BASE_TIME + timedelta(seconds=8))
    invoice_receipt, _ = executor.execute(
        authorization_id=invoice_grant.authorization_id,
        principal_id="ap-approver-001",
        parameters=invoice_parameters,
        execution_id="execution-invoice-001",
        idempotency_key="effect-invoice-001",
    )

    final_case = store.get_case(case.case_id)
    replayed_case = store.replay_case(case.case_id)
    final_snapshot = enterprise.read_snapshot()
    events = store.list_events(case.case_id)
    decisions = store.list_policy_decisions(case.case_id)
    approvals = store.list_approvals(case.case_id)
    grants = store.list_grants(case.case_id)
    attempts = store.list_attempts(case.case_id)
    receipts = store.list_receipts(case.case_id)
    genesis = store.get_genesis(case.case_id)
    invariant_results = (
        {
            "name": "case_closed",
            "passed": final_case.status is CaseStatus.CLOSED,
            "evidence": ["/final_case/status", "/event_timeline/9/new_status"],
        },
        {
            "name": "projection_replays_exactly",
            "passed": replayed_case == final_case,
            "evidence": ["/genesis", "/event_timeline", "/final_case"],
        },
        {
            "name": "receipt_is_complete",
            "passed": final_snapshot.erp_receipt.quantity == 100,
            "evidence": ["/final_authoritative_records/erp_receipt/quantity"],
        },
        {
            "name": "invoice_is_released",
            "passed": final_snapshot.invoice.state.value == "RELEASED",
            "evidence": ["/final_authoritative_records/invoice/state"],
        },
        {
            "name": "two_distinct_approvers",
            "passed": len({item.principal_id for item in approvals}) == 2,
            "evidence": ["/approvals/0/principal_id", "/approvals/1/principal_id"],
        },
        {
            "name": "early_invoice_deny_had_zero_effects",
            "passed": len(effects_after_deny) == 0,
            "evidence": [
                "/controlled_deny_probe/policy_decision_id",
                "/controlled_deny_probe/business_effect_count_before",
                "/controlled_deny_probe/business_effect_count_after",
            ],
        },
        {
            "name": "one_receipt_business_effect",
            "passed": sum(
                effect.effect_type.value == "RECEIPT_RESTART"
                for effect in final_snapshot.business_effects
            )
            == 1,
            "evidence": ["/business_effect_ledger/0/effect_type"],
        },
        {
            "name": "one_invoice_business_effect",
            "passed": sum(
                effect.effect_type.value == "INVOICE_RELEASE"
                for effect in final_snapshot.business_effects
            )
            == 1,
            "evidence": ["/business_effect_ledger/1/effect_type"],
        },
        {
            "name": "shared_trace_id",
            "passed": all(
                getattr(record, "trace_id", None) == "trace-main-001"
                for record in (
                    genesis,
                    *evidence,
                    *events,
                    *decisions,
                    *approvals,
                    *grants,
                    *attempts,
                    *receipts,
                    *final_snapshot.business_effects,
                )
            ),
            "evidence": [
                "/genesis/trace_id",
                "/detector_evidence",
                "/event_timeline",
                "/policy_decisions",
                "/approvals",
                "/grants",
                "/execution_attempts",
                "/execution_receipts",
                "/business_effect_ledger",
            ],
        },
    )
    if not all(result["passed"] for result in invariant_results):
        raise AssertionError(f"main-case invariants failed: {invariant_results}")

    artifact: dict[str, Any] = {
        "fixture": {
            "path": "fixtures/scenarios/retryable-document-lock.json",
            "sha256": genesis.fixture_digest,
        },
        "diagnosis_mode": "deterministic_stub",
        "initial_authoritative_records": _as_json(initial_snapshot),
        "detector_evidence": [_as_json(item) for item in evidence],
        "diagnosis": {
            "hypothesis": _as_json(hypothesis),
            "evaluation": _as_json(evaluation),
        },
        "genesis": _as_json(genesis),
        "event_timeline": [_as_json(item) for item in events],
        "approvals": [_as_json(item) for item in approvals],
        "grants": [_as_json(item) for item in grants],
        "policy_decisions": [_as_json(item) for item in decisions],
        "controlled_deny_probe": {
            "policy_decision_id": early_deny.decision_id,
            "business_effect_count_before": effect_count_before_deny,
            "business_effect_count_after": len(effects_after_deny),
        },
        "execution_attempts": [_as_json(item) for item in attempts],
        "execution_receipts": [_as_json(receipt), _as_json(invoice_receipt)],
        "execution_state_evidence": {
            "receipt": {
                "authoritative_pre_read": _as_json(initial_snapshot),
                "authoritative_post_read": _as_json(after_receipt),
            },
            "invoice": {
                "authoritative_pre_read": _as_json(after_receipt),
                "authoritative_post_read": _as_json(final_snapshot),
            },
        },
        "business_effect_ledger": [_as_json(item) for item in final_snapshot.business_effects],
        "final_authoritative_records": _as_json(final_snapshot),
        "final_case": _as_json(final_case),
        "invariants": list(invariant_results),
    }
    if artifact_path is not None:
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")
    return artifact


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="missing20-demo-") as temporary:
        artifact = run_main_case(
            work_directory=Path(temporary),
            fixture_path=DEFAULT_FIXTURE,
            artifact_path=DEFAULT_ARTIFACT,
        )
    print("The Missing 20 deterministic timeline")
    for event in artifact["event_timeline"]:
        print(
            f"v{event['new_version']:02d} {event['prior_status']} -> "
            f"{event['new_status']} ({event['event']})"
        )
    print("All invariants passed; artifact written to artifacts/demo/main-case.json")


if __name__ == "__main__":
    main()
