"""Real SQLite end-to-end proofs for Milestone 2 safety semantics."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from scripts.run_demo import BASE_TIME, DEFAULT_FIXTURE, run_main_case
from the_missing_20.adapters.clocks import ManualClock
from the_missing_20.adapters.local_signer import LocalSigner
from the_missing_20.adapters.sqlite_case_store import SQLiteCaseStore
from the_missing_20.adapters.synthetic_enterprise import SyntheticEnterprise
from the_missing_20.application.authorization_service import (
    AuthorizationService,
    IdentityContext,
    LocalPolicy,
    TrustedIdentities,
)
from the_missing_20.application.case_service import CaseService
from the_missing_20.application.detector import DiscrepancyDetector
from the_missing_20.application.diagnosis import diagnose_retryable_message
from the_missing_20.application.executor import ControlledExecutor, SimulatedPersistenceFault
from the_missing_20.domain.enterprise import ScenarioFixture
from the_missing_20.domain.errors import (
    AuthorizationDenied,
    InvalidEventPayload,
    InvalidTransition,
)
from the_missing_20.domain.events import TransitionCommand
from the_missing_20.domain.execution import (
    ExecutionAttemptStatus,
    GrantStatus,
    PolicyDecision,
    PolicyOutcome,
    ReleaseInvoiceParameters,
    RestartReceiptMessageParameters,
)
from the_missing_20.domain.models import (
    ActionGrant,
    ActionTool,
    ConfidenceBand,
    EvaluationDecision,
    EvaluationResult,
    ExecutionReceipt,
    HumanRole,
    HypothesisConclusion,
    HypothesisResult,
    HypothesisType,
    OperationResult,
)
from the_missing_20.domain.states import CaseStatus, TransitionEvent
from the_missing_20.ports.enterprise_systems import EnterpriseSystems


@dataclass(frozen=True)
class AwaitingReceiptContext:
    enterprise_path: Path
    case_path: Path
    enterprise: SyntheticEnterprise
    store: SQLiteCaseStore
    authorization: AuthorizationService
    policy: LocalPolicy
    parameters: RestartReceiptMessageParameters
    identity: IdentityContext
    clock: ManualClock
    case_id: str


@dataclass(frozen=True)
class ReceiptContext(AwaitingReceiptContext):
    grant: ActionGrant


@dataclass(frozen=True)
class InvoiceContext:
    enterprise: SyntheticEnterprise
    store: SQLiteCaseStore
    policy: LocalPolicy
    authorization: AuthorizationService
    parameters: ReleaseInvoiceParameters
    grant: ActionGrant
    identity: IdentityContext
    clock: ManualClock
    case_id: str


def prepare_awaiting_receipt_context(tmp_path: Path) -> AwaitingReceiptContext:
    enterprise_path = tmp_path / "enterprise.sqlite"
    case_path = tmp_path / "case.sqlite"
    enterprise = SyntheticEnterprise.seed_from_fixture(enterprise_path, DEFAULT_FIXTURE)
    store = SQLiteCaseStore(case_path)
    identities = TrustedIdentities(
        {
            "operator-001": HumanRole.INTEGRATION_OPERATOR,
            "ap-approver-001": HumanRole.AP_APPROVER,
        }
    )
    signer = LocalSigner(b"synthetic-integration-test-key")
    clock = ManualClock(BASE_TIME)
    authorization = AuthorizationService(
        store=store, signer=signer, identities=identities, clock=clock
    )
    policy = LocalPolicy(store=store, signer=signer, identities=identities, clock=clock)
    case, evidence = DiscrepancyDetector(enterprise, store, clock).detect(
        case_id="case-integration-001",
        trace_id="trace-integration-001",
        fixture_path=DEFAULT_FIXTURE,
    )
    service = CaseService(store, clock)
    hypothesis, evaluation = diagnose_retryable_message(evidence, trace_id="trace-integration-001")
    clock.set(BASE_TIME + timedelta(seconds=1))
    case, _ = service.recommend_receipt_restart(
        case_id=case.case_id,
        expected_version=case.case_version,
        idempotency_key="diagnosis-recommends-restart",
        hypothesis=hypothesis,
        evaluation=evaluation,
    )
    clock.set(BASE_TIME + timedelta(seconds=2))
    case, _ = service.request_receipt_approval(
        case_id=case.case_id,
        expected_version=case.case_version,
        idempotency_key="receipt-approval-requested",
    )
    snapshot = enterprise.read_snapshot()
    parameters = RestartReceiptMessageParameters(
        message_id=snapshot.failed_message.message_id,
        message_revision=snapshot.failed_message.revision,
        purchase_order_id=snapshot.failed_message.purchase_order_id,
        line_id=snapshot.failed_message.line_id,
        quantity=snapshot.failed_message.quantity,
        expected_error_code=snapshot.failed_message.error_code,
        expected_message_status=snapshot.failed_message.status.value,
    )
    return AwaitingReceiptContext(
        enterprise_path=enterprise_path,
        case_path=case_path,
        enterprise=enterprise,
        store=store,
        authorization=authorization,
        policy=policy,
        parameters=parameters,
        identity=IdentityContext("operator-001", HumanRole.INTEGRATION_OPERATOR),
        clock=clock,
        case_id=case.case_id,
    )


def prepare_receipt_context(tmp_path: Path) -> ReceiptContext:
    context = prepare_awaiting_receipt_context(tmp_path)
    context.clock.set(BASE_TIME + timedelta(seconds=3))
    grant = context.authorization.approve(
        case_id=context.case_id,
        principal_id="operator-001",
        tool=ActionTool.RESTART_RECEIPT_MESSAGE,
        parameters=context.parameters,
        approval_id="approval-receipt-integration",
        authorization_id="authorization-receipt-integration",
    )
    return ReceiptContext(
        enterprise_path=context.enterprise_path,
        case_path=context.case_path,
        enterprise=context.enterprise,
        store=context.store,
        authorization=context.authorization,
        policy=context.policy,
        parameters=context.parameters,
        identity=context.identity,
        clock=context.clock,
        case_id=context.case_id,
        grant=grant,
    )


def execute_receipt(
    context: ReceiptContext,
    *,
    executor: ControlledExecutor | None = None,
    occurred_at: datetime = BASE_TIME + timedelta(seconds=4),
    fail_after_reservation: bool = False,
    fail_after_enterprise_commit: bool = False,
    post_commit_hook: Callable[[EnterpriseSystems], None] | None = None,
) -> tuple[ExecutionReceipt, PolicyDecision | None]:
    active_executor = executor or ControlledExecutor(
        store=context.store,
        enterprise=context.enterprise,
        policy=context.policy,
        clock=context.clock,
    )
    context.clock.set(occurred_at)
    return active_executor.execute(
        authorization_id=context.grant.authorization_id,
        principal_id=context.identity.principal_id,
        parameters=context.parameters,
        execution_id="execution-receipt-integration",
        idempotency_key="effect-receipt-integration",
        fail_after_reservation=fail_after_reservation,
        fail_after_enterprise_commit=fail_after_enterprise_commit,
        post_commit_hook=post_commit_hook,
    )


def prepare_invoice_context(tmp_path: Path) -> InvoiceContext:
    receipt_context = prepare_receipt_context(tmp_path)
    execute_receipt(receipt_context, occurred_at=BASE_TIME + timedelta(seconds=4))
    case = receipt_context.store.get_case(receipt_context.case_id)
    receipt_context.clock.set(BASE_TIME + timedelta(seconds=5))
    CaseService(receipt_context.store, receipt_context.clock).request_invoice_approval(
        case_id=case.case_id,
        expected_version=case.case_version,
        idempotency_key="invoice-approval-requested-integration",
    )
    snapshot = receipt_context.enterprise.read_snapshot()
    parameters = ReleaseInvoiceParameters(
        invoice_id=snapshot.invoice.invoice_id,
        invoice_revision=snapshot.invoice.revision,
        purchase_order_id=snapshot.invoice.purchase_order_id,
        line_id=snapshot.invoice.line_id,
        quantity=snapshot.invoice.quantity,
        expected_hold_reason="RECEIPT_MISMATCH",
    )
    receipt_context.clock.set(BASE_TIME + timedelta(seconds=6))
    grant = receipt_context.authorization.approve(
        case_id=receipt_context.case_id,
        principal_id="ap-approver-001",
        tool=ActionTool.RELEASE_INVOICE,
        parameters=parameters,
        approval_id="approval-invoice-integration",
        authorization_id="authorization-invoice-integration",
    )
    return InvoiceContext(
        enterprise=receipt_context.enterprise,
        store=receipt_context.store,
        policy=receipt_context.policy,
        authorization=receipt_context.authorization,
        parameters=parameters,
        grant=grant,
        identity=IdentityContext("ap-approver-001", HumanRole.AP_APPROVER),
        clock=receipt_context.clock,
        case_id=receipt_context.case_id,
    )


def execute_invoice(
    context: InvoiceContext,
    *,
    occurred_at: datetime = BASE_TIME + timedelta(seconds=7),
    post_commit_hook: Callable[[EnterpriseSystems], None] | None = None,
) -> tuple[ExecutionReceipt, PolicyDecision | None]:
    context.clock.set(occurred_at)
    return ControlledExecutor(
        store=context.store,
        enterprise=context.enterprise,
        policy=context.policy,
        clock=context.clock,
    ).execute(
        authorization_id=context.grant.authorization_id,
        principal_id=context.identity.principal_id,
        parameters=context.parameters,
        execution_id="execution-invoice-integration",
        idempotency_key="effect-invoice-integration",
        post_commit_hook=post_commit_hook,
    )


def test_main_case_runs_from_json_through_two_sqlite_databases(tmp_path: Path) -> None:
    artifact_path = tmp_path / "artifact.json"

    artifact = run_main_case(
        work_directory=tmp_path,
        fixture_path=DEFAULT_FIXTURE,
        artifact_path=artifact_path,
    )

    assert artifact["final_case"]["status"] == "CLOSED"
    assert all(item["passed"] for item in artifact["invariants"])
    assert len(artifact["business_effect_ledger"]) == 2
    assert all(
        item["evidence_id"].startswith(f"{artifact['final_case']['case_id']}:")
        for item in artifact["detector_evidence"]
    )
    assert artifact == json.loads(artifact_path.read_text(encoding="utf-8"))
    assert (tmp_path / "enterprise.sqlite").is_file()
    assert (tmp_path / "case.sqlite").is_file()


def test_scenario_fixture_rejects_cross_record_purchase_order_identity() -> None:
    payload = json.loads(DEFAULT_FIXTURE.read_text(encoding="utf-8"))
    payload["invoice"]["line_id"] = "different-line"

    with pytest.raises(ValidationError, match="share one purchase-order line"):
        ScenarioFixture.model_validate_json(json.dumps(payload))


def test_rejected_diagnosis_cannot_advance_to_recommendation(tmp_path: Path) -> None:
    enterprise = SyntheticEnterprise.seed_from_fixture(
        tmp_path / "enterprise.sqlite", DEFAULT_FIXTURE
    )
    store = SQLiteCaseStore(tmp_path / "case.sqlite")
    clock = ManualClock(BASE_TIME)
    case, evidence = DiscrepancyDetector(enterprise, store, clock).detect(
        case_id="case-rejected-diagnosis",
        trace_id="trace-rejected-diagnosis",
        fixture_path=DEFAULT_FIXTURE,
    )
    altered = tuple(
        item.model_copy(
            update={
                "admitted_fields": {
                    **item.admitted_fields,
                    "retry_eligible": False,
                    "lock_cleared": False,
                }
            }
        )
        if item.source_type.value == "FAILED_MESSAGE_QUEUE"
        else item
        for item in evidence
    )
    hypothesis, evaluation = diagnose_retryable_message(
        altered, trace_id="trace-rejected-diagnosis"
    )
    clock.set(BASE_TIME + timedelta(seconds=1))

    with pytest.raises(InvalidEventPayload, match="evidence-complete accepted diagnosis"):
        CaseService(store, clock).recommend_receipt_restart(
            case_id=case.case_id,
            expected_version=case.case_version,
            idempotency_key="rejected-diagnosis",
            hypothesis=hypothesis,
            evaluation=evaluation,
        )

    assert store.get_case(case.case_id).status is CaseStatus.INVESTIGATING
    assert len(store.list_events(case.case_id)) == 1


def test_case_service_has_no_generic_privileged_transition_escape_hatch(
    tmp_path: Path,
) -> None:
    context = prepare_awaiting_receipt_context(tmp_path)
    service = CaseService(context.store, context.clock)

    assert not hasattr(service, "transition")
    assert context.store.list_approvals(context.case_id) == ()
    assert context.store.list_receipts(context.case_id) == ()
    assert context.enterprise.read_snapshot().business_effects == ()


def test_store_rejects_forged_trace_before_any_case_write(tmp_path: Path) -> None:
    context = prepare_awaiting_receipt_context(tmp_path)
    case = context.store.get_case(context.case_id)
    before_events = context.store.list_events(context.case_id)

    with pytest.raises(InvalidEventPayload, match="immutable case genesis"):
        context.store.apply_transition(
            TransitionCommand(
                case_id=case.case_id,
                expected_version=case.case_version,
                event=TransitionEvent.RECEIPT_APPROVAL_ACCEPTED,
                idempotency_key="forged-trace-approval",
                trace_id="forged-trace",
                occurred_at=context.clock.now(),
            )
        )

    assert context.store.get_case(context.case_id) == case
    assert context.store.list_events(context.case_id) == before_events


def test_accepted_label_without_required_citations_cannot_recommend(
    tmp_path: Path,
) -> None:
    enterprise = SyntheticEnterprise.seed_from_fixture(
        tmp_path / "enterprise.sqlite", DEFAULT_FIXTURE
    )
    store = SQLiteCaseStore(tmp_path / "case.sqlite")
    clock = ManualClock(BASE_TIME)
    case, evidence = DiscrepancyDetector(enterprise, store, clock).detect(
        case_id="case-empty-citations",
        trace_id="trace-empty-citations",
        fixture_path=DEFAULT_FIXTURE,
    )
    hypothesis = HypothesisResult(
        hypothesis_type=HypothesisType.RETRYABLE_MESSAGE,
        conclusion=HypothesisConclusion.SUPPORTED,
        confidence_band=ConfidenceBand.HIGH,
        supporting_evidence_ids=(),
        contradicting_evidence_ids=(),
        missing_evidence=("source_message_link",),
    )
    evaluation = EvaluationResult(
        decision=EvaluationDecision.ACCEPT,
        validated_evidence_ids=tuple(item.evidence_id for item in evidence),
        failed_invariants=(),
        allowed_next_action=ActionTool.RESTART_RECEIPT_MESSAGE,
        evaluator_version="malformed-test-evaluator",
        trace_id="trace-empty-citations",
    )
    clock.set(BASE_TIME + timedelta(seconds=1))

    with pytest.raises(InvalidEventPayload, match="evidence-complete accepted diagnosis"):
        CaseService(store, clock).recommend_receipt_restart(
            case_id=case.case_id,
            expected_version=case.case_version,
            idempotency_key="empty-citation-recommendation",
            hypothesis=hypothesis,
            evaluation=evaluation,
        )

    assert store.get_case(case.case_id).status is CaseStatus.INVESTIGATING


def test_tool_parameter_mismatch_is_rejected_before_approval_or_state_change(
    tmp_path: Path,
) -> None:
    context = prepare_awaiting_receipt_context(tmp_path)
    snapshot = context.enterprise.read_snapshot()
    wrong_parameters = ReleaseInvoiceParameters(
        invoice_id=snapshot.invoice.invoice_id,
        invoice_revision=snapshot.invoice.revision,
        purchase_order_id=snapshot.invoice.purchase_order_id,
        line_id=snapshot.invoice.line_id,
        quantity=snapshot.invoice.quantity,
        expected_hold_reason="RECEIPT_MISMATCH",
    )
    before = context.store.get_case(context.case_id)
    context.clock.set(BASE_TIME + timedelta(seconds=3))

    with pytest.raises(AuthorizationDenied, match="parameter envelope"):
        context.authorization.approve(
            case_id=context.case_id,
            principal_id="operator-001",
            tool=ActionTool.RESTART_RECEIPT_MESSAGE,
            parameters=wrong_parameters,
            approval_id="approval-invalid-envelope",
            authorization_id="authorization-invalid-envelope",
        )

    assert context.store.get_case(context.case_id) == before
    assert context.store.list_approvals(context.case_id) == ()
    assert context.store.list_grants(context.case_id) == ()
    assert context.enterprise.read_snapshot().business_effects == ()


def test_wrong_role_and_tool_produce_a_persisted_deny_and_zero_effects(
    tmp_path: Path,
) -> None:
    context = prepare_awaiting_receipt_context(tmp_path)
    snapshot = context.enterprise.read_snapshot()
    invoice_parameters = ReleaseInvoiceParameters(
        invoice_id=snapshot.invoice.invoice_id,
        invoice_revision=snapshot.invoice.revision,
        purchase_order_id=snapshot.invoice.purchase_order_id,
        line_id=snapshot.invoice.line_id,
        quantity=snapshot.invoice.quantity,
        expected_hold_reason="RECEIPT_MISMATCH",
    )
    before = context.store.get_case(context.case_id)
    context.clock.set(BASE_TIME + timedelta(seconds=3))

    with pytest.raises(AuthorizationDenied, match="not eligible"):
        context.authorization.approve(
            case_id=context.case_id,
            principal_id="ap-approver-001",
            tool=ActionTool.RELEASE_INVOICE,
            parameters=invoice_parameters,
            approval_id="approval-wrong-stage",
            authorization_id="authorization-wrong-stage",
        )

    assert context.store.get_case(context.case_id) == before
    assert context.store.list_policy_decisions(context.case_id)[0].decision is PolicyOutcome.DENY
    assert context.enterprise.read_snapshot().business_effects == ()


def test_stale_signed_grant_produces_zero_enterprise_writes(tmp_path: Path) -> None:
    context = prepare_receipt_context(tmp_path)
    case = context.store.get_case(context.case_id)
    context.clock.set(BASE_TIME + timedelta(seconds=4))
    context.store.apply_transition(
        TransitionCommand(
            case_id=case.case_id,
            expected_version=case.case_version,
            event=TransitionEvent.RECEIPT_EXECUTION_STARTED,
            idempotency_key="competing-execution-start",
            trace_id=context.grant.trace_id,
            occurred_at=context.clock.now(),
        )
    )

    with pytest.raises(AuthorizationDenied, match="CASE_VERSION_OR_STATUS_MISMATCH"):
        ControlledExecutor(
            store=context.store,
            enterprise=context.enterprise,
            policy=context.policy,
            clock=context.clock,
        ).execute(
            authorization_id=context.grant.authorization_id,
            principal_id=context.identity.principal_id,
            parameters=context.parameters,
            execution_id="stale-execution",
            idempotency_key="stale-effect",
        )

    assert context.enterprise.read_snapshot().business_effects == ()


def test_crash_after_business_commit_recovers_without_duplicate_effect(tmp_path: Path) -> None:
    context = prepare_receipt_context(tmp_path)

    with pytest.raises(SimulatedPersistenceFault):
        execute_receipt(context, fail_after_enterprise_commit=True)

    failed_snapshot = context.enterprise.read_snapshot()
    assert len(failed_snapshot.material_documents) == 1
    assert len(failed_snapshot.business_effects) == 1
    assert context.store.list_receipts(context.grant.case_id) == ()
    assert context.store.list_attempts(context.grant.case_id)[0].status is (
        ExecutionAttemptStatus.RESERVED
    )
    assert context.store.get_case(context.grant.case_id).status is CaseStatus.RECEIPT_EXECUTING

    rebuilt_enterprise = SyntheticEnterprise(context.enterprise_path)
    rebuilt_store = SQLiteCaseStore(context.case_path)
    rebuilt_identities = TrustedIdentities({"operator-001": HumanRole.INTEGRATION_OPERATOR})
    rebuilt_policy = LocalPolicy(
        store=rebuilt_store,
        signer=LocalSigner(b"synthetic-integration-test-key"),
        identities=rebuilt_identities,
        clock=context.clock,
    )
    rebuilt_authorization = AuthorizationService(
        store=rebuilt_store,
        signer=LocalSigner(b"synthetic-integration-test-key"),
        identities=rebuilt_identities,
        clock=context.clock,
    )
    rebuilt_executor = ControlledExecutor(
        store=rebuilt_store,
        enterprise=rebuilt_enterprise,
        policy=rebuilt_policy,
        clock=context.clock,
    )
    rebuilt_context = ReceiptContext(
        enterprise_path=context.enterprise_path,
        case_path=context.case_path,
        enterprise=rebuilt_enterprise,
        store=rebuilt_store,
        authorization=rebuilt_authorization,
        policy=rebuilt_policy,
        grant=context.grant,
        parameters=context.parameters,
        identity=context.identity,
        clock=context.clock,
        case_id=context.case_id,
    )

    receipt, _ = execute_receipt(rebuilt_context, executor=rebuilt_executor)
    repeated_receipt, _ = execute_receipt(rebuilt_context, executor=rebuilt_executor)

    final_snapshot = rebuilt_enterprise.read_snapshot()
    assert receipt.operation_result is OperationResult.SAFE_NOOP
    assert repeated_receipt == receipt
    assert len(final_snapshot.material_documents) == 1
    assert len(final_snapshot.business_effects) == 1
    assert rebuilt_store.get_case(context.grant.case_id).status is CaseStatus.RECEIPT_VERIFIED


@pytest.mark.parametrize("tamper", ["expiry", "signature", "context"])
def test_reserved_recovery_reloads_and_revalidates_the_stored_grant(
    tmp_path: Path, tamper: str
) -> None:
    context = prepare_receipt_context(tmp_path)
    with pytest.raises(SimulatedPersistenceFault):
        execute_receipt(context, fail_after_reservation=True)

    tamper_updates: dict[str, dict[str, object]] = {
        "expiry": {"expires_at": context.grant.expires_at + timedelta(days=1)},
        "signature": {"signature": "tampered-signature"},
        "context": {"trace_id": "tampered-trace"},
    }
    updates = tamper_updates[tamper]
    tampered = context.grant.model_copy(update=updates)
    with sqlite3.connect(context.case_path) as connection:
        connection.execute(
            "UPDATE grants SET grant_json = ? WHERE authorization_id = ?",
            (tampered.model_dump_json(), context.grant.authorization_id),
        )
    context.clock.set(context.grant.expires_at + timedelta(seconds=1))

    with pytest.raises(AuthorizationDenied, match="recovery validation failed"):
        execute_receipt(context, occurred_at=context.clock.now())

    assert context.enterprise.read_snapshot().business_effects == ()
    assert context.enterprise.read_snapshot().material_documents == ()


def test_expired_reserved_grant_cannot_create_first_effect(tmp_path: Path) -> None:
    context = prepare_receipt_context(tmp_path)

    with pytest.raises(SimulatedPersistenceFault):
        execute_receipt(context, fail_after_reservation=True)
    with pytest.raises(AuthorizationDenied, match="expired"):
        execute_receipt(
            context,
            occurred_at=context.grant.expires_at + timedelta(seconds=1),
        )

    snapshot = context.enterprise.read_snapshot()
    decisions = context.store.list_policy_decisions(context.grant.case_id)
    assert snapshot.material_documents == ()
    assert snapshot.business_effects == ()
    assert any(
        decision.decision is PolicyOutcome.DENY
        and "RESERVED_GRANT_EXPIRED_WITHOUT_EFFECT" in decision.reason_codes
        for decision in decisions
    )


def test_expired_reserved_grant_only_reconciles_an_existing_exact_effect(
    tmp_path: Path,
) -> None:
    context = prepare_receipt_context(tmp_path)
    with pytest.raises(SimulatedPersistenceFault):
        execute_receipt(context, fail_after_enterprise_commit=True)

    receipt, _ = execute_receipt(
        context,
        occurred_at=context.grant.expires_at + timedelta(seconds=1),
    )

    snapshot = context.enterprise.read_snapshot()
    assert receipt.operation_result is OperationResult.SAFE_NOOP
    assert len(snapshot.material_documents) == 1
    assert len(snapshot.business_effects) == 1
    assert context.store.get_case(context.grant.case_id).status is CaseStatus.RECEIPT_VERIFIED


def test_external_exact_effect_is_reconciled_as_safe_noop(tmp_path: Path) -> None:
    context = prepare_receipt_context(tmp_path)
    context.enterprise.simulate_external_receipt(
        case_id=context.grant.case_id,
        trace_id=context.grant.trace_id,
        parameters=context.parameters,
        committed_at=BASE_TIME + timedelta(seconds=4),
    )

    receipt, _ = execute_receipt(context, occurred_at=BASE_TIME + timedelta(seconds=5))

    snapshot = context.enterprise.read_snapshot()
    assert receipt.operation_result is OperationResult.SAFE_NOOP
    assert len(snapshot.material_documents) == 1
    assert len(snapshot.business_effects) == 1
    assert snapshot.business_effects[0].effect_type.value == "EXTERNAL_RECEIPT"


def test_receipt_external_drift_with_corrupt_execution_linkage_is_denied(
    tmp_path: Path,
) -> None:
    context = prepare_receipt_context(tmp_path)
    context.enterprise.simulate_external_receipt(
        case_id=context.case_id,
        trace_id=context.grant.trace_id,
        parameters=context.parameters,
        committed_at=BASE_TIME + timedelta(seconds=4),
    )
    with sqlite3.connect(context.enterprise_path) as connection:
        connection.execute("UPDATE material_documents SET execution_id = 'unrelated-execution'")

    with pytest.raises(AuthorizationDenied, match="preconditions changed"):
        execute_receipt(context, occurred_at=BASE_TIME + timedelta(seconds=5))

    snapshot = context.enterprise.read_snapshot()
    assert not any(
        effect.effect_type.value == "RECEIPT_RESTART" for effect in snapshot.business_effects
    )


def test_ambiguous_state_drift_is_denied_without_an_enterprise_effect(tmp_path: Path) -> None:
    context = prepare_receipt_context(tmp_path)
    context.enterprise.set_erp_receipt_quantity_for_test(100)

    with pytest.raises(AuthorizationDenied, match="preconditions changed"):
        execute_receipt(context)

    snapshot = context.enterprise.read_snapshot()
    assert snapshot.material_documents == ()
    assert snapshot.business_effects == ()
    assert context.store.list_receipts(context.grant.case_id)[0].operation_result is (
        OperationResult.FAILED
    )
    assert any(
        "ENTERPRISE_PRECONDITION_FAILED" in decision.reason_codes
        for decision in context.store.list_policy_decisions(context.grant.case_id)
    )


def test_failed_fresh_read_verification_is_a_hard_stop(tmp_path: Path) -> None:
    context = prepare_receipt_context(tmp_path)

    def corrupt_authoritative_state(enterprise: object) -> None:
        assert isinstance(enterprise, SyntheticEnterprise)
        enterprise.set_erp_receipt_quantity_for_test(90)

    receipt, _ = execute_receipt(context, post_commit_hook=corrupt_authoritative_state)

    assert receipt.operation_result is OperationResult.FAILED
    assert context.store.list_attempts(context.grant.case_id)[0].status is (
        ExecutionAttemptStatus.VERIFICATION_FAILED
    )
    assert context.store.get_grant_status(context.grant.authorization_id) is GrantStatus.CONSUMED
    case = context.store.get_case(context.grant.case_id)
    assert case.status is CaseStatus.RECEIPT_EXECUTING
    repeated, _ = execute_receipt(context)
    assert repeated == receipt
    assert len(context.enterprise.read_snapshot().business_effects) == 1

    with pytest.raises(InvalidTransition):
        context.clock.set(BASE_TIME + timedelta(seconds=6))
        CaseService(context.store, context.clock).request_invoice_approval(
            case_id=case.case_id,
            expected_version=case.case_version,
            idempotency_key="invoice-approval-must-not-open",
        )


def test_receipt_post_commit_linkage_corruption_cannot_verify(tmp_path: Path) -> None:
    context = prepare_receipt_context(tmp_path)

    def corrupt_linkage(enterprise: EnterpriseSystems) -> None:
        assert isinstance(enterprise, SyntheticEnterprise)
        with sqlite3.connect(enterprise.database_path) as connection:
            connection.execute("UPDATE material_documents SET execution_id = 'unrelated-execution'")

    receipt, _ = execute_receipt(context, post_commit_hook=corrupt_linkage)

    assert receipt.operation_result is OperationResult.FAILED
    assert receipt.postconditions["message_document_effect_linked"] is False
    assert context.store.get_grant_status(context.grant.authorization_id) is GrantStatus.CONSUMED
    assert context.store.get_case(context.case_id).status is CaseStatus.RECEIPT_EXECUTING


def test_receipt_post_commit_quantity_corruption_cannot_verify(tmp_path: Path) -> None:
    context = prepare_receipt_context(tmp_path)

    def corrupt_authorized_quantity(enterprise: EnterpriseSystems) -> None:
        assert isinstance(enterprise, SyntheticEnterprise)
        with sqlite3.connect(enterprise.database_path) as connection:
            connection.execute("UPDATE failed_messages SET quantity = 10")
            connection.execute("UPDATE material_documents SET quantity = 10")

    receipt, _ = execute_receipt(context, post_commit_hook=corrupt_authorized_quantity)

    assert receipt.operation_result is OperationResult.FAILED
    assert receipt.postconditions["message_identity_matches_parameters"] is False
    assert receipt.postconditions["material_document_quantity_matches"] is False
    assert context.store.get_grant_status(context.grant.authorization_id) is GrantStatus.CONSUMED
    assert context.store.get_case(context.case_id).status is CaseStatus.RECEIPT_EXECUTING


def test_external_invoice_release_is_reconciled_as_safe_noop(tmp_path: Path) -> None:
    context = prepare_invoice_context(tmp_path)
    context.enterprise.simulate_external_invoice_release(
        case_id=context.case_id,
        trace_id=context.grant.trace_id,
        parameters=context.parameters,
        committed_at=BASE_TIME + timedelta(seconds=7),
    )

    receipt, _ = execute_invoice(context, occurred_at=BASE_TIME + timedelta(seconds=8))

    snapshot = context.enterprise.read_snapshot()
    assert receipt.operation_result is OperationResult.SAFE_NOOP
    assert (
        sum(
            effect.effect_type.value == "EXTERNAL_INVOICE_RELEASE"
            for effect in snapshot.business_effects
        )
        == 1
    )
    assert context.store.get_case(context.case_id).status is CaseStatus.CLOSED


def test_invoice_external_drift_with_corrupt_execution_linkage_is_denied(
    tmp_path: Path,
) -> None:
    context = prepare_invoice_context(tmp_path)
    context.enterprise.simulate_external_invoice_release(
        case_id=context.case_id,
        trace_id=context.grant.trace_id,
        parameters=context.parameters,
        committed_at=BASE_TIME + timedelta(seconds=7),
    )
    with sqlite3.connect(context.enterprise.database_path) as connection:
        connection.execute("UPDATE invoices SET released_by_execution_id = 'unrelated-execution'")

    with pytest.raises(AuthorizationDenied, match="preconditions changed"):
        execute_invoice(context, occurred_at=BASE_TIME + timedelta(seconds=8))

    snapshot = context.enterprise.read_snapshot()
    assert not any(
        effect.effect_type.value == "INVOICE_RELEASE" for effect in snapshot.business_effects
    )


def test_ambiguous_invoice_drift_is_denied_without_invoice_effect(tmp_path: Path) -> None:
    context = prepare_invoice_context(tmp_path)
    with sqlite3.connect(context.enterprise.database_path) as connection:
        connection.execute(
            "UPDATE invoices SET state = 'RELEASED', hold_reason = NULL, revision = revision + 1"
        )

    with pytest.raises(AuthorizationDenied, match="preconditions changed"):
        execute_invoice(context)

    snapshot = context.enterprise.read_snapshot()
    assert not any(
        effect.effect_type.value in {"INVOICE_RELEASE", "EXTERNAL_INVOICE_RELEASE"}
        for effect in snapshot.business_effects
    )
    assert context.store.get_case(context.case_id).status is CaseStatus.INVOICE_EXECUTING


def test_invoice_postcondition_failure_is_audited_and_blocks_closure(tmp_path: Path) -> None:
    context = prepare_invoice_context(tmp_path)

    def reintroduce_hold(enterprise: EnterpriseSystems) -> None:
        assert isinstance(enterprise, SyntheticEnterprise)
        enterprise.set_invoice_hold_for_test("POST_COMMIT_REVIEW_HOLD")

    receipt, _ = execute_invoice(context, post_commit_hook=reintroduce_hold)

    assert receipt.operation_result is OperationResult.FAILED
    assert context.store.list_attempts(context.case_id)[-1].status is (
        ExecutionAttemptStatus.VERIFICATION_FAILED
    )
    assert context.store.get_grant_status(context.grant.authorization_id) is GrantStatus.CONSUMED
    assert context.store.get_case(context.case_id).status is CaseStatus.INVOICE_EXECUTING
    assert any(
        effect.effect_type.value == "INVOICE_RELEASE"
        for effect in context.enterprise.read_snapshot().business_effects
    )


def test_invoice_post_commit_linkage_corruption_cannot_close(tmp_path: Path) -> None:
    context = prepare_invoice_context(tmp_path)

    def corrupt_linkage(enterprise: EnterpriseSystems) -> None:
        assert isinstance(enterprise, SyntheticEnterprise)
        with sqlite3.connect(enterprise.database_path) as connection:
            connection.execute(
                "UPDATE invoices SET released_by_execution_id = 'unrelated-execution'"
            )

    receipt, _ = execute_invoice(context, post_commit_hook=corrupt_linkage)

    assert receipt.operation_result is OperationResult.FAILED
    assert receipt.postconditions["invoice_effect_linked"] is False
    assert context.store.get_grant_status(context.grant.authorization_id) is GrantStatus.CONSUMED
    assert context.store.get_case(context.case_id).status is CaseStatus.INVOICE_EXECUTING
