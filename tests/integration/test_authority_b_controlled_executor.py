"""Authority-B quorum integration and advisory metamorphic proofs."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest

from the_missing_20.adapters.clocks import ManualClock
from the_missing_20.adapters.local_signer import LocalSigner
from the_missing_20.adapters.sqlite_case_store import SQLiteCaseStore
from the_missing_20.adapters.synthetic_enterprise import SyntheticEnterprise
from the_missing_20.application.detector import DiscrepancyDetector
from the_missing_20.application.executor import SimulatedPersistenceFault
from the_missing_20.authority_b.advisory import normalize_advisory_failure
from the_missing_20.authority_b.classifier import classify_operational_state
from the_missing_20.authority_b.executor import AuthorityBControlledExecutor
from the_missing_20.authority_b.models import (
    ADVISORY_AUTHORITY_LABEL,
    AdvisoryDissent,
    AdvisoryHypothesis,
    AdvisoryInvestigation,
    AdvisoryStatus,
    AdvisoryUsage,
    OperationalDecision,
    QuorumActionGrant,
    QuorumStatus,
)
from the_missing_20.authority_b.quorum import AuthorityBExecutor, QuorumAuthorizationService
from the_missing_20.authority_b.workflow import run_authority_b
from the_missing_20.domain.execution import RestartReceiptMessageParameters
from the_missing_20.domain.models import (
    Case,
    ConfidenceBand,
    EvidenceItem,
    HumanRole,
    HypothesisConclusion,
    HypothesisType,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "fixtures/scenarios/retryable-document-lock.json"
NOW = datetime(2026, 8, 27, tzinfo=UTC)


def _context(
    tmp_path: Path,
) -> tuple[
    SyntheticEnterprise,
    SQLiteCaseStore,
    ManualClock,
    Case,
    tuple[EvidenceItem, ...],
    tuple[OperationalDecision, RestartReceiptMessageParameters],
]:
    enterprise = SyntheticEnterprise.seed_from_fixture(tmp_path / "enterprise.sqlite", FIXTURE)
    store = SQLiteCaseStore(tmp_path / "case.sqlite")
    clock = ManualClock(NOW)
    case, evidence = DiscrepancyDetector(enterprise, store, clock).detect(
        case_id="authority-b-case",
        trace_id="authority-b-trace",
        fixture_path=FIXTURE,
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
    decision = classify_operational_state(evidence, case=case, trace_id="authority-b-trace")
    return enterprise, store, clock, case, evidence, (decision, parameters)


def _grant(
    store: SQLiteCaseStore,
    clock: ManualClock,
    case: Case,
    evidence: tuple[EvidenceItem, ...],
    parameters: RestartReceiptMessageParameters,
    *,
    ledger_path: Path | None = None,
) -> tuple[QuorumActionGrant, QuorumAuthorizationService, OperationalDecision]:
    decision = classify_operational_state(evidence, case=case, trace_id=evidence[0].trace_id)
    service = QuorumAuthorizationService(
        principals={"operator": HumanRole.INTEGRATION_OPERATOR, "approver": HumanRole.AP_APPROVER},
        signer=LocalSigner(b"authority-b-integration-key"),
        clock=clock,
        storage_path=ledger_path,
    )
    intent = service.create_intent(
        decision=decision,
        complete_parameters=parameters,
        admitted_evidence_digest=decision.source_digest,
        intent_id="authority-b-intent",
    )
    pending = service.attest(
        intent=intent,
        principal_id="operator",
        attestation_id="authority-b-operator",
    )
    assert pending.status is QuorumStatus.QUORUM_PENDING
    assert pending.grant is None
    assert store.get_authority_b_binding(intent.intent_id) is None
    granted = service.attest(
        intent=intent,
        principal_id="approver",
        attestation_id="authority-b-approver",
    )
    assert granted.grant is not None
    return granted.grant, service, decision


def test_authority_b_recovery_path_is_durable_and_first_approval_is_inert(
    tmp_path: Path,
) -> None:
    enterprise, store, clock, case, evidence, (_decision, parameters) = _context(tmp_path)
    ledger_path = tmp_path / "authority-b-quorum.json"
    grant, service, _decision = _grant(
        store, clock, case, evidence, parameters, ledger_path=ledger_path
    )
    assert store.get_case(case.case_id).status.value == "INVESTIGATING"
    assert enterprise.read_snapshot().business_effects == ()

    adapter = AuthorityBControlledExecutor(
        store=store, enterprise=enterprise, quorum=service, clock=clock
    )
    receipt, _ = adapter.execute(
        grant,
        execution_id="authority-b-execution",
        idempotency_key="authority-b-effect",
    )
    assert receipt.operation_result.value == "EXECUTED"
    assert len(enterprise.read_snapshot().business_effects) == 1
    assert service.get_intent(grant.intent_id).status is QuorumStatus.CONSUMED

    reloaded_service = QuorumAuthorizationService(
        principals={"operator": HumanRole.INTEGRATION_OPERATOR, "approver": HumanRole.AP_APPROVER},
        signer=LocalSigner(b"authority-b-integration-key"),
        clock=clock,
        storage_path=ledger_path,
    )
    reloaded_store = SQLiteCaseStore(tmp_path / "case.sqlite")
    reloaded_enterprise = SyntheticEnterprise(tmp_path / "enterprise.sqlite")
    replay, _ = AuthorityBControlledExecutor(
        store=reloaded_store,
        enterprise=reloaded_enterprise,
        quorum=reloaded_service,
        clock=clock,
    ).execute(
        grant,
        execution_id="authority-b-execution",
        idempotency_key="authority-b-effect",
    )
    assert replay == receipt
    assert len(reloaded_enterprise.read_snapshot().business_effects) == 1
    assert reloaded_service.get_intent(grant.intent_id).status is QuorumStatus.CONSUMED


def test_authority_b_reserved_attempt_recovers_without_second_effect(tmp_path: Path) -> None:
    enterprise, store, clock, case, evidence, (_decision, parameters) = _context(tmp_path)
    ledger_path = tmp_path / "authority-b-quorum.json"
    grant, service, _decision = _grant(
        store, clock, case, evidence, parameters, ledger_path=ledger_path
    )
    adapter = AuthorityBControlledExecutor(
        store=store, enterprise=enterprise, quorum=service, clock=clock
    )
    with pytest.raises(SimulatedPersistenceFault):
        adapter.execute(
            grant,
            execution_id="authority-b-crash-reservation",
            idempotency_key="authority-b-crash-effect",
            fail_after_reservation=True,
        )
    assert enterprise.read_snapshot().business_effects == ()
    assert service.get_intent(grant.intent_id).status is QuorumStatus.GRANTED

    recovered, _ = adapter.execute(
        grant,
        execution_id="authority-b-crash-reservation",
        idempotency_key="authority-b-crash-effect",
    )
    assert recovered.operation_result.value == "EXECUTED"
    assert len(enterprise.read_snapshot().business_effects) == 1
    assert service.get_intent(grant.intent_id).status is QuorumStatus.CONSUMED


def _advisory(
    status: AdvisoryStatus,
    case_id: str,
    trace_id: str,
    *,
    conflicting: bool = False,
    incomplete: bool = False,
) -> AdvisoryInvestigation:
    if status is AdvisoryStatus.UNAVAILABLE:
        return normalize_advisory_failure(
            case_id=case_id, trace_id=trace_id, started=False, now=NOW
        )
    warning = () if status is AdvisoryStatus.COMPLETE else ("ADVISORY_VARIANT",)
    hypotheses: tuple[AdvisoryHypothesis, ...] = ()
    dissent: tuple[AdvisoryDissent, ...] = ()
    if conflicting:
        hypotheses = (
            AdvisoryHypothesis(
                hypothesis_id="h-retryable",
                investigator_role="retryable-investigator",
                hypothesis_type=HypothesisType.RETRYABLE_MESSAGE,
                conclusion=HypothesisConclusion.SUPPORTED,
                confidence_band=ConfidenceBand.HIGH,
                explanation="A retryable document lock is plausible.",
            ),
            AdvisoryHypothesis(
                hypothesis_id="h-shortage",
                investigator_role="shortage-investigator",
                hypothesis_type=HypothesisType.GENUINE_SHORT_SHIPMENT,
                conclusion=HypothesisConclusion.SUPPORTED,
                confidence_band=ConfidenceBand.LOW,
                explanation="A physical shortage is also plausible.",
            ),
        )
        dissent = (
            AdvisoryDissent(
                investigator_role="shortage-investigator",
                statement="The investigators disagree.",
                hypothesis_type=HypothesisType.GENUINE_SHORT_SHIPMENT,
                confidence_band=ConfidenceBand.LOW,
            ),
        )
    elif incomplete:
        hypotheses = (
            AdvisoryHypothesis(
                hypothesis_id="h-incomplete",
                investigator_role="retryable-investigator",
                hypothesis_type=HypothesisType.RETRYABLE_MESSAGE,
                conclusion=HypothesisConclusion.NEEDS_EVIDENCE,
                confidence_band=ConfidenceBand.LOW,
                explanation="A citation could not be resolved.",
                supporting_evidence_ids=("unadmitted-evidence",),
            ),
        )
    return AdvisoryInvestigation(
        advisory_id=f"advisory:{case_id}:{status.value}",
        case_id=case_id,
        trace_id=trace_id,
        case_version=1,
        status=status,
        hypotheses=hypotheses,
        dissent=dissent,
        warnings=warning,
        usage=AdvisoryUsage(),
        created_at=NOW,
        updated_at=NOW,
        authority_label=ADVISORY_AUTHORITY_LABEL,
    )


@pytest.mark.parametrize(
    "variant",
    (
        "COMPLETE",
        "CONFLICTING",
        "INCOMPLETE_CITATIONS_PARTIAL",
        "MALFORMED",
        "TIMEOUT_DEGRADED",
        "ABSENT_UNAVAILABLE",
    ),
)
def test_advisory_variants_are_metamorphic_over_authority_b_effects(
    tmp_path: Path, variant: str
) -> None:
    work = tmp_path / variant.lower()
    work.mkdir()
    enterprise, store, clock, case, evidence, (_decision, parameters) = _context(work)
    advisory_execute: Callable[[], object] | None
    if variant == "MALFORMED":

        def malformed() -> object:
            return object()

        advisory_execute = malformed
    elif variant == "TIMEOUT_DEGRADED":

        def timeout() -> object:
            raise TimeoutError("provider timeout")

        advisory_execute = timeout
    elif variant == "ABSENT_UNAVAILABLE":
        advisory_execute = None
    else:
        status = (
            AdvisoryStatus.COMPLETE
            if variant == "COMPLETE"
            else AdvisoryStatus.PARTIAL
            if variant == "INCOMPLETE_CITATIONS_PARTIAL"
            else AdvisoryStatus.COMPLETE
        )

        def complete() -> object:
            return _advisory(
                status,
                case.case_id,
                evidence[0].trace_id,
                conflicting=variant == "CONFLICTING",
                incomplete=variant == "INCOMPLETE_CITATIONS_PARTIAL",
            )

        advisory_execute = complete

    run = run_authority_b(
        case=case,
        evidence=evidence,
        advisory_execute=advisory_execute,
        advisory_now=NOW,
    )
    grant, service, decision = _grant(store, clock, case, evidence, parameters)
    assert run.operational_decision.model_dump_json() == decision.model_dump_json()
    assert enterprise.read_snapshot().business_effects == ()

    adapter = AuthorityBControlledExecutor(
        store=store, enterprise=enterprise, quorum=service, clock=clock
    )
    receipt, _ = adapter.execute(
        grant,
        execution_id="authority-b-metamorphic-execution",
        idempotency_key="authority-b-metamorphic-effect",
    )
    replay, _ = adapter.execute(
        grant,
        execution_id="authority-b-metamorphic-execution",
        idempotency_key="authority-b-metamorphic-effect",
    )
    assert grant.grant_digest == grant._computed_digest()
    assert receipt == replay
    assert receipt.postconditions and all(receipt.postconditions.values())
    assert len(enterprise.read_snapshot().business_effects) == 1


def test_authority_b_boundary_rejects_legacy_grant_and_arbitrary_callback() -> None:
    with pytest.raises(TypeError):
        AuthorityBExecutor().execute(object(), effect=lambda _grant: None)  # type: ignore[call-arg]
