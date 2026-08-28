from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from the_missing_20.adapters.clocks import ManualClock
from the_missing_20.adapters.local_knowledge import LocalKnowledgeRepository
from the_missing_20.adapters.local_signer import LocalSigner
from the_missing_20.adapters.sqlite_case_store import SQLiteCaseStore
from the_missing_20.adapters.strands_models import ScriptedStrandsFactory
from the_missing_20.adapters.synthetic_enterprise import SyntheticEnterprise
from the_missing_20.agents.harness import AgentHarness
from the_missing_20.application.detector import DiscrepancyDetector
from the_missing_20.authority_b.advisory import (
    ADVISORY_READ_ONLY_TOOLS,
    AdvisoryOrchestrator,
    advisory_from_harness_run,
    normalize_advisory_failure,
    validate_advisory_tool_names,
)
from the_missing_20.authority_b.classifier import (
    DeterministicDecisionLedger,
    OperationalDecisionConflict,
    classify_operational_state,
)
from the_missing_20.authority_b.models import (
    ADVISORY_AUTHORITY_LABEL,
    AdvisoryStatus,
    AttestationDecision,
    OperationalClassification,
    OperationalEligibility,
    QuorumStatus,
    transition_advisory_status,
)
from the_missing_20.authority_b.proofs import build_ai_usefulness_proof, build_safety_proof
from the_missing_20.authority_b.provider import (
    AUTHORITY_B_INCREMENTAL_COST_CAP_USD,
    AUTHORITY_B_INPUT_TOKEN_CAP,
    AUTHORITY_B_MAX_OUTPUT_TOKENS_PER_REQUEST,
    AUTHORITY_B_PRIOR_ESTIMATED_COST_USD,
    AUTHORITY_B_REQUEST_CAP,
    AuthorityBAttemptAlreadyClaimed,
    claim_authority_b_attempt,
    claim_digest,
    load_authority_b_attempt_claim,
)
from the_missing_20.authority_b.quorum import (
    AuthorityBExecutor,
    QuorumAuthorizationService,
    QuorumDenied,
)
from the_missing_20.authority_b.workflow import run_authority_b
from the_missing_20.domain.execution import RestartReceiptMessageParameters
from the_missing_20.domain.models import ActionGrant, Case, EvidenceItem, HumanRole

ROOT = Path(__file__).resolve().parents[2]
RETRYABLE = ROOT / "fixtures/scenarios/retryable-document-lock.json"
SHORTAGE = ROOT / "fixtures/scenarios/golden/genuine-short-shipment.json"
POSTED = ROOT / "fixtures/scenarios/golden/receipt-already-posted.json"
NOW = datetime(2026, 8, 27, tzinfo=UTC)


def _detected(
    tmp_path: Path, fixture: Path = RETRYABLE, *, unavailable: bool = False
) -> tuple[
    SyntheticEnterprise,
    SQLiteCaseStore,
    ManualClock,
    Case,
    tuple[EvidenceItem, ...],
]:
    enterprise = SyntheticEnterprise.seed_from_fixture(tmp_path / "enterprise.sqlite", fixture)
    if unavailable:
        enterprise.set_material_document_source_unavailable("SOURCE_UNAVAILABLE")
    store = SQLiteCaseStore(tmp_path / "case.sqlite")
    clock = ManualClock(NOW)
    case, evidence = DiscrepancyDetector(enterprise, store, clock).detect(
        case_id="authority-b-case",
        trace_id="authority-b-trace",
        fixture_path=fixture,
    )
    return enterprise, store, clock, case, evidence


def test_classifier_has_exact_four_profiles_and_ledger_is_byte_stable(tmp_path: Path) -> None:
    expected = {
        RETRYABLE: (
            OperationalClassification.RETRYABLE_MESSAGE,
            OperationalEligibility.PENDING_APPROVAL,
        ),
        POSTED: (
            OperationalClassification.RECEIPT_ALREADY_POSTED,
            OperationalEligibility.NO_ACTION,
        ),
        SHORTAGE: (
            OperationalClassification.GENUINE_SHORT_SHIPMENT,
            OperationalEligibility.NO_ACTION,
        ),
    }
    for fixture, result in expected.items():
        with TemporaryDirectory() as raw:
            _enterprise, _store, _clock, case, evidence = _detected(Path(raw), fixture)
            ledger = DeterministicDecisionLedger()
            first = classify_operational_state(
                evidence, case=case, trace_id=evidence[0].trace_id, ledger=ledger
            )
            reversed_result = classify_operational_state(
                tuple(reversed(evidence)),
                case=case,
                trace_id=evidence[0].trace_id,
                ledger=ledger,
            )
            assert (first.classification, first.eligibility) == result
            assert first == reversed_result
            assert first.model_dump_json() == reversed_result.model_dump_json()


def test_missing_source_fails_closed_and_advisory_cannot_change_decision(tmp_path: Path) -> None:
    _enterprise, _store, _clock, case, evidence = _detected(tmp_path, unavailable=True)
    decision = classify_operational_state(evidence, case=case, trace_id=evidence[0].trace_id)
    assert decision.classification is OperationalClassification.REQUIRE_EVIDENCE
    assert decision.allowed_action is None
    advisory = normalize_advisory_failure(
        case_id=case.case_id,
        trace_id=evidence[0].trace_id,
        case_version=case.case_version,
        error=ValueError("provider prose must not escape"),
        now=NOW,
    )
    run = run_authority_b(case=case, evidence=evidence, advisory_execute=lambda: advisory)
    assert run.operational_decision == decision
    assert run.advisory.status is AdvisoryStatus.DEGRADED


def test_advisory_failure_is_one_call_and_status_transitions_are_monotonic() -> None:
    calls = 0

    def fail() -> object:
        nonlocal calls
        calls += 1
        raise TimeoutError("not persisted")

    result = AdvisoryOrchestrator().run(
        case_id="case",
        trace_id="trace",
        execute=fail,
        now=NOW,
    )
    assert calls == 1
    assert result.status is AdvisoryStatus.DEGRADED
    assert result.error_code == "ADVISORY_PROVIDER_TIMEOUT"
    transition_advisory_status(AdvisoryStatus.NOT_REQUESTED, AdvisoryStatus.RUNNING)
    transition_advisory_status(AdvisoryStatus.RUNNING, AdvisoryStatus.PARTIAL)
    with pytest.raises(ValueError):
        transition_advisory_status(AdvisoryStatus.PARTIAL, AdvisoryStatus.RUNNING)
    assert validate_advisory_tool_names(ADVISORY_READ_ONLY_TOOLS) == tuple(
        sorted(ADVISORY_READ_ONLY_TOOLS)
    )
    with pytest.raises(ValueError):
        validate_advisory_tool_names(("execute_write",))


def test_scripted_harness_projects_to_useful_advisory_record(tmp_path: Path) -> None:
    enterprise, store, clock, case, evidence = _detected(tmp_path)
    del enterprise, clock
    from the_missing_20.evaluation.agent_golden_runner import source_availability_from_genesis

    availability = source_availability_from_genesis(store.get_genesis(case.case_id), evidence)
    harness_run = AgentHarness(
        model_factory=ScriptedStrandsFactory(),
        knowledge=LocalKnowledgeRepository(ROOT / "fixtures/knowledge"),
        source_availability=availability,
    ).run(case_id=case.case_id, trace_id=evidence[0].trace_id, evidence=evidence)
    advisory = advisory_from_harness_run(harness_run, now=NOW)
    assert advisory.authority_label == ADVISORY_AUTHORITY_LABEL
    assert advisory.status is AdvisoryStatus.COMPLETE
    assert len(advisory.hypotheses) == 3
    assert advisory.incident_report
    assert advisory.knowledge_citations


def test_quorum_first_approval_has_no_grant_and_second_is_exact(tmp_path: Path) -> None:
    enterprise, _store, clock, case, evidence = _detected(tmp_path)
    decision = classify_operational_state(evidence, case=case, trace_id=evidence[0].trace_id)
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
    service = QuorumAuthorizationService(
        principals={
            "operator": HumanRole.INTEGRATION_OPERATOR,
            "approver": HumanRole.AP_APPROVER,
        },
        signer=LocalSigner(b"authority-b-test"),
        clock=clock,
    )
    intent = service.create_intent(
        decision=decision,
        complete_parameters=parameters,
        admitted_evidence_digest=decision.source_digest,
        intent_id="intent-1",
    )
    pending = service.attest(intent=intent, principal_id="operator", attestation_id="approval-1")
    assert pending.status is QuorumStatus.QUORUM_PENDING
    assert pending.grant is None
    granted = service.attest(intent=intent, principal_id="approver", attestation_id="approval-2")
    assert granted.status is QuorumStatus.GRANTED
    assert granted.grant is not None
    assert set(granted.grant.roles) == {
        HumanRole.INTEGRATION_OPERATOR,
        HumanRole.AP_APPROVER,
    }
    with pytest.raises(QuorumDenied):
        service.attest(intent=intent, principal_id="operator", attestation_id="approval-3")


def test_quorum_rejection_expiry_duplicate_and_legacy_grant_are_denied(tmp_path: Path) -> None:
    _enterprise, _store, clock, case, evidence = _detected(tmp_path)
    decision = classify_operational_state(evidence, case=case, trace_id=evidence[0].trace_id)
    snapshot = _enterprise.read_snapshot()
    parameters = RestartReceiptMessageParameters(
        message_id=snapshot.failed_message.message_id,
        message_revision=snapshot.failed_message.revision,
        purchase_order_id=snapshot.failed_message.purchase_order_id,
        line_id=snapshot.failed_message.line_id,
        quantity=snapshot.failed_message.quantity,
        expected_error_code=snapshot.failed_message.error_code,
        expected_message_status=snapshot.failed_message.status.value,
    )
    service = QuorumAuthorizationService(
        principals={"operator": HumanRole.INTEGRATION_OPERATOR, "approver": HumanRole.AP_APPROVER},
        signer=LocalSigner(b"authority-b-test"),
        clock=clock,
    )
    rejected = service.create_intent(
        decision=decision,
        complete_parameters=parameters,
        admitted_evidence_digest=decision.source_digest,
        intent_id="intent-rejected",
    )
    result = service.attest(
        intent=rejected,
        principal_id="operator",
        attestation_id="reject",
        decision=AttestationDecision.REJECTED,
    )
    assert result.status is QuorumStatus.REJECTED
    with pytest.raises(QuorumDenied):
        service.attest(intent=rejected, principal_id="approver", attestation_id="late")

    expiring = service.create_intent(
        decision=decision,
        complete_parameters=parameters,
        admitted_evidence_digest=decision.source_digest,
        intent_id="intent-expiring",
        created_at=NOW,
    )
    clock.set(NOW + timedelta(minutes=5, seconds=1))
    with pytest.raises(QuorumDenied):
        service.attest(intent=expiring, principal_id="operator", attestation_id="expired")
    assert service.get_intent(expiring.intent_id).status is QuorumStatus.EXPIRED
    with pytest.raises(QuorumDenied):
        AuthorityBExecutor().validate_grant(ActionGrant.model_construct())


def test_provider_claim_is_exclusive_and_frozen(tmp_path: Path) -> None:
    path = tmp_path / "claim.json"
    claim = claim_authority_b_attempt(path)
    assert load_authority_b_attempt_claim(path) == claim
    assert claim_digest(claim) == claim.claim_digest
    assert claim.prior_cost_usd == AUTHORITY_B_PRIOR_ESTIMATED_COST_USD
    assert claim.request_cap == AUTHORITY_B_REQUEST_CAP
    assert claim.input_token_cap == AUTHORITY_B_INPUT_TOKEN_CAP
    assert claim.max_output_tokens_per_request == AUTHORITY_B_MAX_OUTPUT_TOKENS_PER_REQUEST
    assert claim.incremental_cost_cap_usd == AUTHORITY_B_INCREMENTAL_COST_CAP_USD
    with pytest.raises(AuthorityBAttemptAlreadyClaimed):
        claim_authority_b_attempt(path)

    def claim_once(_: int) -> object | None:
        try:
            return claim_authority_b_attempt(tmp_path / "concurrent.json")
        except AuthorityBAttemptAlreadyClaimed:
            return None

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = tuple(executor.map(claim_once, range(4)))
    assert sum(item is not None for item in results) == 1


def test_record_ledger_rejects_different_decision_for_same_case_version(tmp_path: Path) -> None:
    _enterprise, _store, _clock, case, evidence = _detected(tmp_path)
    ledger = DeterministicDecisionLedger()
    decision = classify_operational_state(evidence, case=case, trace_id=evidence[0].trace_id)
    ledger.put(decision)
    changed = decision.model_copy(
        update={"reason_codes": ("tampered",), "decision_digest": "f" * 64}
    )
    with pytest.raises(OperationalDecisionConflict):
        ledger.put(changed)


def test_safety_and_usefulness_proofs_are_separate(tmp_path: Path) -> None:
    enterprise, store, _clock, case, evidence = _detected(tmp_path)
    decision = classify_operational_state(evidence, case=case, trace_id=evidence[0].trace_id)
    safety = build_safety_proof(
        proof_id="safety",
        operational_decision=decision,
        safety_counters={"false_effects": 0},
        metamorphic_results=(True, True),
    )
    assert safety.status.value == "PASS"
    unavailable = AdvisoryOrchestrator().run(
        case_id=case.case_id,
        trace_id=evidence[0].trace_id,
        case_version=case.case_version,
    )
    usefulness = build_ai_usefulness_proof(proof_id="usefulness", advisory=unavailable)
    assert usefulness.status.value == "FAIL"
    assert str(safety.schema_version) != str(usefulness.schema_version)
    del enterprise, store
