"""Authoritative, synthetic Authority-B lifecycle records for the M5 workspace.

This module is intentionally separate from the browser projection.  A lifecycle
bundle is produced by executing the real local quorum and controlled-executor path,
then validated from its persisted records.  Advisory traces are joined only by the
workspace layer and can never provide an operational record.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated, Any, Final, Literal, cast

from pydantic import Field, model_validator

from the_missing_20.adapters.clocks import ManualClock
from the_missing_20.adapters.local_signer import LocalSigner
from the_missing_20.adapters.sqlite_case_store import SQLiteCaseStore
from the_missing_20.adapters.synthetic_enterprise import SyntheticEnterprise
from the_missing_20.application.authorization_service import (
    action_digest,
    evidence_digest,
    unsigned_grant_payload,
)
from the_missing_20.application.detector import DiscrepancyDetector
from the_missing_20.application.executor import _verify_authoritative_state
from the_missing_20.authority_b.classifier import (
    classify_operational_state,
    latest_authoritative_evidence,
)
from the_missing_20.authority_b.executor import AuthorityBControlledExecutor
from the_missing_20.authority_b.models import (
    AuthorityModel,
    AuthorizationIntent,
    OperationalDecision,
    QuorumActionGrant,
    QuorumAttestation,
    QuorumStatus,
    canonical_json,
    evidence_content_digest,
)
from the_missing_20.authority_b.quorum import QuorumAuthorizationService
from the_missing_20.domain.enterprise import (
    BusinessEffect,
    EnterpriseActionOutcome,
    EnterpriseSnapshot,
)
from the_missing_20.domain.events import CaseEvent
from the_missing_20.domain.execution import (
    DecisionStage,
    EffectType,
    ExecutionAttempt,
    ExecutionAttemptStatus,
    PolicyDecision,
    PolicyOutcome,
    ReleaseInvoiceParameters,
    RestartReceiptMessageParameters,
)
from the_missing_20.domain.models import (
    ActionGrant,
    ActionTool,
    Case,
    EvidenceItem,
    EvidenceProvenance,
    EvidenceSourceType,
    ExecutionReceipt,
    HumanRole,
)
from the_missing_20.domain.states import TRANSITIONS, CaseStatus, TransitionEvent

LIFECYCLE_SCHEMA_VERSION: Final[str] = "AuthorityBLifecycleDemo/v1"
LIFECYCLE_ARTIFACT_PATH: Final[str] = "artifacts/workspace/authority-b-lifecycle-v1.json"
LIFECYCLE_CASE_ID: Final[str] = "m5-authority-b-case"
LIFECYCLE_TRACE_ID: Final[str] = "m5-authority-b-trace"
LIFECYCLE_GENERATED_AT: Final[str] = "2026-08-27T00:00:00Z"
LIFECYCLE_SIGNING_KEY: Final[bytes] = b"missing20-authority-b-m5-lifecycle"


def _sha(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _snapshot_digest(snapshot: EnterpriseSnapshot) -> str:
    """Use the exact digest algorithm emitted by ``ControlledExecutor`` receipts."""

    return hashlib.sha256(snapshot.model_dump_json().encode("utf-8")).hexdigest()


def _model_digest(value: object) -> str:
    if hasattr(value, "model_dump"):
        return _sha(cast(Any, value).model_dump(mode="json"))
    return _sha(value)


def _case_event_digest(event: CaseEvent) -> str:
    """Digest the complete event using the bundle's canonical JSON contract."""

    return _sha(event.model_dump(mode="json"))


def _case_event_id(event: CaseEvent) -> str:
    """Reproduce the deterministic state-machine event identity."""

    identity = ":".join(
        (
            event.case_id,
            str(event.prior_version),
            event.event.value,
            event.idempotency_key,
            event.payload_digest,
        )
    )
    return f"evt_{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:32]}"


class LifecycleReread(AuthorityModel):
    reread_id: Annotated[str, Field(min_length=1)]
    action_id: Annotated[str, Field(min_length=1)]
    phase: Literal["BEFORE", "AFTER"]
    observed_at: datetime
    snapshot: EnterpriseSnapshot
    snapshot_digest: Annotated[str, Field(min_length=1)]

    @model_validator(mode="after")
    def digest_matches_snapshot(self) -> LifecycleReread:
        if self.snapshot_digest != _snapshot_digest(self.snapshot):
            raise ValueError("lifecycle reread snapshot digest mismatch")
        return self


class LifecycleReplay(AuthorityModel):
    replay_id: Annotated[str, Field(min_length=1)]
    action_id: Annotated[str, Field(min_length=1)]
    execution_id: Annotated[str, Field(min_length=1)]
    idempotency_key: Annotated[str, Field(min_length=1)]
    receipt: ExecutionReceipt
    receipt_digest: Annotated[str, Field(min_length=1)]
    effect_count_before: int = Field(ge=0)
    effect_count_after: int = Field(ge=0)
    effect_delta: int = Field(ge=0)
    status: Literal["PASS"] = "PASS"

    @model_validator(mode="after")
    def replay_is_idempotent(self) -> LifecycleReplay:
        if self.receipt_digest != _model_digest(self.receipt):
            raise ValueError("lifecycle replay receipt digest mismatch")
        if self.effect_count_after - self.effect_count_before != self.effect_delta:
            raise ValueError("lifecycle replay effect delta is inconsistent")
        if self.effect_delta != 0:
            raise ValueError("lifecycle replay must have zero effect delta")
        if self.receipt.execution_id != self.execution_id:
            raise ValueError("lifecycle replay receipt execution does not match")
        return self


class LifecyclePreparationTransition(AuthorityModel):
    """A typed projection of one executor-owned preparation ``CaseEvent``.

    The projection is deliberately not trusted on its own.  The lifecycle validator
    resolves ``event_id`` into the persisted full ``CaseEvent`` and compares every
    field and digest before accepting a bridge or execution record.
    """

    schema_version: Literal["lifecycle-preparation-transition/v1"] = (
        "lifecycle-preparation-transition/v1"
    )
    transition_id: Annotated[str, Field(min_length=1)]
    action_id: Annotated[str, Field(min_length=1)]
    intent_id: Annotated[str, Field(min_length=1)]
    event_id: Annotated[str, Field(min_length=1)]
    event: TransitionEvent
    before_version: int = Field(ge=0)
    after_version: int = Field(ge=1)
    before_status: CaseStatus
    after_status: CaseStatus
    idempotency_key: Annotated[str, Field(min_length=1)]
    payload_digest: Annotated[str, Field(min_length=1)]
    event_digest: Annotated[str, Field(min_length=1)]

    @model_validator(mode="after")
    def advances_once(self) -> LifecyclePreparationTransition:
        if self.after_version != self.before_version + 1:
            raise ValueError("preparation transition must advance case version exactly once")
        return self


class LifecycleAction(AuthorityModel):
    """References tying one action's records together without merging actions."""

    action_id: Annotated[str, Field(min_length=1)]
    tool: ActionTool
    decision_id: Annotated[str, Field(min_length=1)]
    intent_id: Annotated[str, Field(min_length=1)]
    attestation_ids: tuple[Annotated[str, Field(min_length=1)], ...] = Field(min_length=2)
    grant_id: Annotated[str, Field(min_length=1)]
    bridge_authorization_id: Annotated[str, Field(min_length=1)]
    execution_id: Annotated[str, Field(min_length=1)]
    idempotency_key: Annotated[str, Field(min_length=1)]
    before_reread_id: Annotated[str, Field(min_length=1)]
    after_reread_id: Annotated[str, Field(min_length=1)]
    effect_id: Annotated[str, Field(min_length=1)]
    verification_execution_id: Annotated[str, Field(min_length=1)]
    replay_id: Annotated[str, Field(min_length=1)]
    preparation_transition_ids: tuple[Annotated[str, Field(min_length=1)], ...] = Field(
        min_length=1
    )
    execution_start_event_id: Annotated[str, Field(min_length=1)]


class LifecycleFinalState(AuthorityModel):
    case: Case
    enterprise: EnterpriseSnapshot
    state_digest: Annotated[str, Field(min_length=1)]

    @model_validator(mode="after")
    def final_digest_matches(self) -> LifecycleFinalState:
        expected = _sha(
            {
                "case": self.case.model_dump(mode="json"),
                "enterprise": self.enterprise.model_dump(mode="json"),
            }
        )
        if self.state_digest != expected:
            raise ValueError("lifecycle final state digest mismatch")
        return self


class AuthorityBLifecycleBundle(AuthorityModel):
    """Complete source bundle for the immutable M5 operational projection."""

    schema_version: Literal["AuthorityBLifecycleDemo/v1"] = "AuthorityBLifecycleDemo/v1"
    generated_at: Literal["2026-08-27T00:00:00Z"] = "2026-08-27T00:00:00Z"
    scenario_id: Annotated[str, Field(min_length=1)]
    fixture_path: Annotated[str, Field(min_length=1)]
    fixture_digest: Annotated[str, Field(min_length=1)]
    case_id: Annotated[str, Field(min_length=1)]
    trace_id: Annotated[str, Field(min_length=1)]
    initial_case: Case
    evidence: tuple[EvidenceItem, ...] = Field(min_length=5)
    decisions: tuple[OperationalDecision, ...] = Field(min_length=2)
    intents: tuple[AuthorizationIntent, ...] = Field(min_length=2)
    attestations: tuple[QuorumAttestation, ...] = Field(min_length=4)
    grants: tuple[QuorumActionGrant, ...] = Field(min_length=2)
    bridge_grants: tuple[ActionGrant, ...] = Field(min_length=2)
    attempts: tuple[ExecutionAttempt, ...] = Field(min_length=2)
    policy_decisions: tuple[PolicyDecision, ...] = Field(min_length=2)
    case_events: tuple[CaseEvent, ...] = Field(min_length=1)
    preparation_transitions: tuple[LifecyclePreparationTransition, ...] = Field(min_length=1)
    rereads: tuple[LifecycleReread, ...] = Field(min_length=4)
    effects: tuple[BusinessEffect, ...] = Field(min_length=2)
    verifications: tuple[ExecutionReceipt, ...] = Field(min_length=2)
    replays: tuple[LifecycleReplay, ...] = Field(min_length=2)
    actions: tuple[LifecycleAction, ...] = Field(min_length=2)
    final_state: LifecycleFinalState
    bundle_digest: str = ""

    @model_validator(mode="after")
    def set_or_check_digest(self) -> AuthorityBLifecycleBundle:
        if not self.bundle_digest:
            object.__setattr__(self, "bundle_digest", lifecycle_bundle_digest(self))
        elif self.bundle_digest != lifecycle_bundle_digest(self):
            raise ValueError("lifecycle bundle digest mismatch")
        return self


def lifecycle_bundle_digest(bundle: AuthorityBLifecycleBundle) -> str:
    return _sha(bundle.model_dump(mode="json", exclude={"bundle_digest"}))


def _read_evidence(
    *,
    snapshot: EnterpriseSnapshot,
    case_id: str,
    trace_id: str,
    observed_at: datetime,
    suffix: str,
) -> tuple[EvidenceItem, ...]:
    """Create detector-shaped fresh-read evidence from one authoritative snapshot."""

    provenance = EvidenceProvenance(
        source_system="synthetic-enterprise-sqlite",
        collection_method="fresh-read",
        collected_by="deterministic-lifecycle-runner",
    )
    fields: tuple[tuple[str, EvidenceSourceType, str, dict[str, Any]], ...] = (
        (
            "warehouse",
            EvidenceSourceType.WAREHOUSE,
            snapshot.warehouse_receipt.receipt_id,
            snapshot.warehouse_receipt.model_dump(mode="json"),
        ),
        (
            "erp-receipt",
            EvidenceSourceType.ERP_RECEIPT,
            f"{snapshot.erp_receipt.purchase_order_id}:{snapshot.erp_receipt.line_id}",
            snapshot.erp_receipt.model_dump(mode="json"),
        ),
        (
            "failed-message",
            EvidenceSourceType.FAILED_MESSAGE_QUEUE,
            snapshot.failed_message.message_id,
            snapshot.failed_message.model_dump(mode="json"),
        ),
        (
            "invoice",
            EvidenceSourceType.INVOICE,
            snapshot.invoice.invoice_id,
            snapshot.invoice.model_dump(mode="json"),
        ),
        (
            "material-documents",
            EvidenceSourceType.MATERIAL_DOCUMENT,
            snapshot.failed_message.message_id,
            {
                "material_documents": [
                    item.model_dump(mode="json") for item in snapshot.material_documents
                ],
                "business_effects": [
                    item.model_dump(mode="json") for item in snapshot.business_effects
                ],
            },
        ),
    )
    result: list[EvidenceItem] = []
    for source, source_type, record_id, admitted_fields in fields:
        item = EvidenceItem(
            evidence_id=f"{case_id}:{suffix}:{source}",
            case_id=case_id,
            trace_id=trace_id,
            subject=source,
            source_type=source_type,
            source_record_id=record_id,
            observed_at=observed_at,
            content_digest=_sha(admitted_fields),
            admitted_fields=admitted_fields,
            provenance=provenance,
        )
        # Guard against accidental divergence from the contract helper used by the
        # classifier; this is also a useful invariant in generated artifacts.
        if item.content_digest != evidence_content_digest(item):
            raise ValueError(f"fresh-read evidence digest mismatch for {source}")
        result.append(item)
    return tuple(result)


def _parameters_for_receipt(snapshot: EnterpriseSnapshot) -> RestartReceiptMessageParameters:
    message = snapshot.failed_message
    return RestartReceiptMessageParameters(
        message_id=message.message_id,
        message_revision=message.revision,
        purchase_order_id=message.purchase_order_id,
        line_id=message.line_id,
        quantity=message.quantity,
        expected_error_code=message.error_code,
        expected_message_status=message.status.value,
    )


def _parameters_for_invoice(snapshot: EnterpriseSnapshot) -> ReleaseInvoiceParameters:
    invoice = snapshot.invoice
    if invoice.hold_reason is None:
        raise ValueError("invoice release lifecycle requires a receipt mismatch hold")
    return ReleaseInvoiceParameters(
        invoice_id=invoice.invoice_id,
        invoice_revision=invoice.revision,
        purchase_order_id=invoice.purchase_order_id,
        line_id=invoice.line_id,
        quantity=invoice.quantity,
        expected_hold_reason=invoice.hold_reason,
    )


def _action_records(
    *,
    action_id: str,
    tool: ActionTool,
    decision: OperationalDecision,
    intent: AuthorizationIntent,
    grant: QuorumActionGrant,
    service: QuorumAuthorizationService,
    bridge: ActionGrant,
    store: SQLiteCaseStore,
    rereads: tuple[LifecycleReread, LifecycleReread],
    receipt: ExecutionReceipt,
    replay: LifecycleReplay,
    preparation_transitions: tuple[LifecyclePreparationTransition, ...],
    execution_start_event_id: str,
) -> tuple[
    LifecycleAction,
    tuple[QuorumAttestation, ...],
    ExecutionAttempt,
    PolicyDecision,
    BusinessEffect,
]:
    attestations = service.list_attestations(intent.intent_id)
    if len(attestations) != 2:
        raise ValueError("lifecycle action requires exactly two persisted attestations")
    attempt = store.get_attempt(receipt.execution_id)
    if attempt is None:
        raise ValueError("lifecycle execution attempt is missing")
    policies = tuple(
        item
        for item in store.list_policy_decisions(intent.case_id)
        if item.execution_id == receipt.execution_id
    )
    if len(policies) != 1:
        raise ValueError("lifecycle action requires exactly one execution policy decision")
    effects = tuple(
        item
        for item in rereads[1].snapshot.business_effects
        if item.execution_id == receipt.execution_id
    )
    if len(effects) != 1:
        raise ValueError("lifecycle action requires exactly one authoritative effect")
    action = LifecycleAction(
        action_id=action_id,
        tool=tool,
        decision_id=decision.decision_id,
        intent_id=intent.intent_id,
        attestation_ids=tuple(item.attestation_id for item in attestations),
        grant_id=grant.grant_id,
        bridge_authorization_id=bridge.authorization_id,
        execution_id=receipt.execution_id,
        idempotency_key=replay.idempotency_key,
        before_reread_id=rereads[0].reread_id,
        after_reread_id=rereads[1].reread_id,
        effect_id=effects[0].effect_id,
        verification_execution_id=receipt.execution_id,
        replay_id=replay.replay_id,
        preparation_transition_ids=tuple(item.transition_id for item in preparation_transitions),
        execution_start_event_id=execution_start_event_id,
    )
    return action, attestations, attempt, policies[0], effects[0]


def _preparation_records(
    *,
    action_id: str,
    intent_id: str,
    events: tuple[CaseEvent, ...],
) -> tuple[LifecyclePreparationTransition, ...]:
    """Project the actual Authority-B preparation events into typed records."""

    prefix = f"authority-b:{intent_id}:"
    selected = tuple(item for item in events if item.idempotency_key.startswith(prefix))
    if not selected:
        raise ValueError(f"no persisted preparation events for {intent_id}")
    return tuple(
        LifecyclePreparationTransition(
            transition_id=f"preparation:{event.event_id}",
            action_id=action_id,
            intent_id=intent_id,
            event_id=event.event_id,
            event=event.event,
            before_version=event.prior_version,
            after_version=event.new_version,
            before_status=event.prior_status,
            after_status=event.new_status,
            idempotency_key=event.idempotency_key,
            payload_digest=event.payload_digest,
            event_digest=_case_event_digest(event),
        )
        for event in selected
    )


def _assert_distinct_actions(actions: tuple[LifecycleAction, ...]) -> None:
    if len({item.intent_id for item in actions}) != len(actions):
        raise ValueError("lifecycle actions share an intent")
    if len({item.grant_id for item in actions}) != len(actions):
        raise ValueError("lifecycle actions share a quorum grant")
    if len({item.execution_id for item in actions}) != len(actions):
        raise ValueError("lifecycle actions share an execution")
    if len({item.idempotency_key for item in actions}) != len(actions):
        raise ValueError("lifecycle actions share an idempotency key")


def _run_lifecycle(repository_root: Path) -> AuthorityBLifecycleBundle:
    fixture_path = repository_root / "fixtures/scenarios/retryable-document-lock.json"
    if not fixture_path.is_file():
        raise ValueError("synthetic lifecycle fixture is missing")
    with TemporaryDirectory(prefix="missing20-m5-lifecycle-") as raw:
        work = Path(raw)
        enterprise = SyntheticEnterprise.seed_from_fixture(work / "enterprise.sqlite", fixture_path)
        store = SQLiteCaseStore(work / "case.sqlite")
        clock = ManualClock(datetime(2026, 8, 27, tzinfo=UTC))
        case_after_detect, initial_evidence = DiscrepancyDetector(enterprise, store, clock).detect(
            case_id=LIFECYCLE_CASE_ID,
            trace_id=LIFECYCLE_TRACE_ID,
            fixture_path=fixture_path,
        )
        genesis = store.get_genesis(LIFECYCLE_CASE_ID)
        initial_case = Case.model_validate_json(genesis.initial_case_json)
        decision_a = classify_operational_state(
            initial_evidence,
            case=case_after_detect,
            trace_id=LIFECYCLE_TRACE_ID,
        )
        if decision_a.allowed_action is not ActionTool.RESTART_RECEIPT_MESSAGE:
            raise ValueError("synthetic lifecycle did not produce receipt restart eligibility")
        service = QuorumAuthorizationService(
            principals={
                "integration-operator": HumanRole.INTEGRATION_OPERATOR,
                "ap-approver": HumanRole.AP_APPROVER,
            },
            signer=LocalSigner(LIFECYCLE_SIGNING_KEY),
            clock=clock,
            storage_path=work / "quorum-ledger.json",
        )
        parameters_a = _parameters_for_receipt(enterprise.read_snapshot())
        intent_a = service.create_intent(
            decision=decision_a,
            complete_parameters=parameters_a,
            admitted_evidence_digest=decision_a.source_digest,
            intent_id="m5-intent-receipt-restart",
        )
        pending_a = service.attest(
            intent=intent_a,
            principal_id="integration-operator",
            attestation_id="m5-attestation-receipt-operator",
        )
        if pending_a.status is not QuorumStatus.QUORUM_PENDING or pending_a.grant is not None:
            raise ValueError("first receipt attestation was not inert")
        if enterprise.read_snapshot().business_effects:
            raise ValueError("receipt effect existed before the second attestation")
        granted_a = service.attest(
            intent=intent_a,
            principal_id="ap-approver",
            attestation_id="m5-attestation-receipt-ap",
        )
        grant_a = granted_a.grant
        if grant_a is None:
            raise ValueError("receipt quorum did not create a grant")
        before_a_snapshot = enterprise.read_snapshot()
        reread_before_a = LifecycleReread(
            reread_id="m5-reread-receipt-before",
            action_id="receipt-restart",
            phase="BEFORE",
            observed_at=clock.now(),
            snapshot=before_a_snapshot,
            snapshot_digest=_snapshot_digest(before_a_snapshot),
        )
        controlled_a = AuthorityBControlledExecutor(
            store=store,
            enterprise=enterprise,
            quorum=service,
            clock=clock,
        )
        receipt_a, _ = controlled_a.execute(
            grant_a,
            execution_id="m5-execution-receipt-restart",
            idempotency_key="m5-effect-receipt-restart",
        )
        after_a_snapshot = enterprise.read_snapshot()
        reread_after_a = LifecycleReread(
            reread_id="m5-reread-receipt-after",
            action_id="receipt-restart",
            phase="AFTER",
            observed_at=clock.now(),
            snapshot=after_a_snapshot,
            snapshot_digest=_snapshot_digest(after_a_snapshot),
        )
        effects_before_replay_a = len(after_a_snapshot.business_effects)
        replay_receipt_a, _ = controlled_a.execute(
            grant_a,
            execution_id="m5-execution-receipt-restart",
            idempotency_key="m5-effect-receipt-restart",
        )
        effects_after_replay_a = len(enterprise.read_snapshot().business_effects)
        if replay_receipt_a != receipt_a or effects_before_replay_a != effects_after_replay_a:
            raise ValueError("receipt replay was not idempotent")
        replay_a = LifecycleReplay(
            replay_id="m5-replay-receipt-restart",
            action_id="receipt-restart",
            execution_id=receipt_a.execution_id,
            idempotency_key="m5-effect-receipt-restart",
            receipt=replay_receipt_a,
            receipt_digest=_model_digest(replay_receipt_a),
            effect_count_before=effects_before_replay_a,
            effect_count_after=effects_after_replay_a,
            effect_delta=0,
        )
        refreshed_evidence = _read_evidence(
            snapshot=after_a_snapshot,
            case_id=LIFECYCLE_CASE_ID,
            trace_id=LIFECYCLE_TRACE_ID,
            observed_at=clock.now(),
            suffix="reread-receipt",
        )
        for item in refreshed_evidence:
            store.add_evidence(item)
        all_evidence = tuple(store.list_evidence(LIFECYCLE_CASE_ID))
        latest_evidence = latest_authoritative_evidence(all_evidence)
        case_after_a = store.get_case(LIFECYCLE_CASE_ID)
        decision_b = classify_operational_state(
            latest_evidence,
            case=case_after_a,
            trace_id=LIFECYCLE_TRACE_ID,
        )
        if decision_b.allowed_action is not ActionTool.RELEASE_INVOICE:
            raise ValueError("synthetic lifecycle did not produce invoice release eligibility")
        parameters_b = _parameters_for_invoice(after_a_snapshot)
        intent_b = service.create_intent(
            decision=decision_b,
            complete_parameters=parameters_b,
            admitted_evidence_digest=decision_b.source_digest,
            intent_id="m5-intent-invoice-release",
        )
        pending_b = service.attest(
            intent=intent_b,
            principal_id="integration-operator",
            attestation_id="m5-attestation-invoice-operator",
        )
        if pending_b.status is not QuorumStatus.QUORUM_PENDING or pending_b.grant is not None:
            raise ValueError("first invoice attestation was not inert")
        if len(enterprise.read_snapshot().business_effects) != len(
            after_a_snapshot.business_effects
        ):
            raise ValueError("invoice effect existed before the second attestation")
        granted_b = service.attest(
            intent=intent_b,
            principal_id="ap-approver",
            attestation_id="m5-attestation-invoice-ap",
        )
        grant_b = granted_b.grant
        if grant_b is None:
            raise ValueError("invoice quorum did not create a grant")
        before_b_snapshot = enterprise.read_snapshot()
        reread_before_b = LifecycleReread(
            reread_id="m5-reread-invoice-before",
            action_id="invoice-release",
            phase="BEFORE",
            observed_at=clock.now(),
            snapshot=before_b_snapshot,
            snapshot_digest=_snapshot_digest(before_b_snapshot),
        )
        controlled_b = AuthorityBControlledExecutor(
            store=store,
            enterprise=enterprise,
            quorum=service,
            clock=clock,
        )
        receipt_b, _ = controlled_b.execute(
            grant_b,
            execution_id="m5-execution-invoice-release",
            idempotency_key="m5-effect-invoice-release",
        )
        after_b_snapshot = enterprise.read_snapshot()
        reread_after_b = LifecycleReread(
            reread_id="m5-reread-invoice-after",
            action_id="invoice-release",
            phase="AFTER",
            observed_at=clock.now(),
            snapshot=after_b_snapshot,
            snapshot_digest=_snapshot_digest(after_b_snapshot),
        )
        effects_before_replay_b = len(after_b_snapshot.business_effects)
        replay_receipt_b, _ = controlled_b.execute(
            grant_b,
            execution_id="m5-execution-invoice-release",
            idempotency_key="m5-effect-invoice-release",
        )
        effects_after_replay_b = len(enterprise.read_snapshot().business_effects)
        if replay_receipt_b != receipt_b or effects_before_replay_b != effects_after_replay_b:
            raise ValueError("invoice replay was not idempotent")
        replay_b = LifecycleReplay(
            replay_id="m5-replay-invoice-release",
            action_id="invoice-release",
            execution_id=receipt_b.execution_id,
            idempotency_key="m5-effect-invoice-release",
            receipt=replay_receipt_b,
            receipt_digest=_model_digest(replay_receipt_b),
            effect_count_before=effects_before_replay_b,
            effect_count_after=effects_after_replay_b,
            effect_delta=0,
        )
        case_events = store.list_events(LIFECYCLE_CASE_ID)
        preparation_a = _preparation_records(
            action_id="receipt-restart",
            intent_id=intent_a.intent_id,
            events=case_events,
        )
        preparation_b = _preparation_records(
            action_id="invoice-release",
            intent_id=intent_b.intent_id,
            events=case_events,
        )
        start_events = {
            execution_id: tuple(
                item
                for item in case_events
                if item.idempotency_key == f"execution-start:{execution_id}"
            )
            for execution_id in (receipt_a.execution_id, receipt_b.execution_id)
        }
        if any(len(items) != 1 for items in start_events.values()):
            raise ValueError("lifecycle execution-start events are not unique")
        binding_a = store.get_authority_b_binding(intent_a.intent_id)
        binding_b = store.get_authority_b_binding(intent_b.intent_id)
        if binding_a is None or binding_b is None:
            raise ValueError("lifecycle Authority-B binding is missing")
        bridge_a = binding_a[1]
        bridge_b = binding_b[1]
        action_a, attestations_a, attempt_a, policy_a, effect_a = _action_records(
            action_id="receipt-restart",
            tool=ActionTool.RESTART_RECEIPT_MESSAGE,
            decision=decision_a,
            intent=service.get_intent(intent_a.intent_id),
            grant=grant_a,
            service=service,
            bridge=bridge_a,
            store=store,
            rereads=(reread_before_a, reread_after_a),
            receipt=receipt_a,
            replay=replay_a,
            preparation_transitions=preparation_a,
            execution_start_event_id=start_events[receipt_a.execution_id][0].event_id,
        )
        action_b, attestations_b, attempt_b, policy_b, effect_b = _action_records(
            action_id="invoice-release",
            tool=ActionTool.RELEASE_INVOICE,
            decision=decision_b,
            intent=service.get_intent(intent_b.intent_id),
            grant=grant_b,
            service=service,
            bridge=bridge_b,
            store=store,
            rereads=(reread_before_b, reread_after_b),
            receipt=receipt_b,
            replay=replay_b,
            preparation_transitions=preparation_b,
            execution_start_event_id=start_events[receipt_b.execution_id][0].event_id,
        )
        actions = (action_a, action_b)
        _assert_distinct_actions(actions)
        final_case = store.get_case(LIFECYCLE_CASE_ID)
        final_state = LifecycleFinalState(
            case=final_case,
            enterprise=after_b_snapshot,
            state_digest=_sha(
                {
                    "case": final_case.model_dump(mode="json"),
                    "enterprise": after_b_snapshot.model_dump(mode="json"),
                }
            ),
        )
        return AuthorityBLifecycleBundle(
            scenario_id=genesis.fixture_path.split("/")[-1].replace(".json", ""),
            fixture_path=genesis.fixture_path,
            fixture_digest=genesis.fixture_digest,
            case_id=LIFECYCLE_CASE_ID,
            trace_id=LIFECYCLE_TRACE_ID,
            initial_case=initial_case,
            evidence=all_evidence,
            decisions=(decision_a, decision_b),
            intents=(
                service.get_intent(intent_a.intent_id),
                service.get_intent(intent_b.intent_id),
            ),
            attestations=(*attestations_a, *attestations_b),
            grants=(grant_a, grant_b),
            bridge_grants=(bridge_a, bridge_b),
            attempts=(attempt_a, attempt_b),
            policy_decisions=(policy_a, policy_b),
            case_events=case_events,
            preparation_transitions=(*preparation_a, *preparation_b),
            rereads=(reread_before_a, reread_after_a, reread_before_b, reread_after_b),
            effects=(effect_a, effect_b),
            verifications=(receipt_a, receipt_b),
            replays=(replay_a, replay_b),
            actions=actions,
            final_state=final_state,
        )


def validate_lifecycle_bundle(
    bundle: AuthorityBLifecycleBundle,
    *,
    repository_root: Path | None = None,
) -> AuthorityBLifecycleBundle:
    """Validate the complete deterministic lifecycle before projecting a workspace.

    This validator intentionally repeats relations that could be inferred from a
    locally rehashed bundle.  The bundle is an audit record, not a trust root: fixed
    event sequences, state-machine transitions, executor receipt digests, and the
    synthetic scenario's typed effect semantics are the independent constraints.
    """

    def unique(records: tuple[Any, ...], field: str, label: str) -> dict[str, Any]:
        indexed = {str(getattr(item, field)): item for item in records}
        if len(indexed) != len(records):
            raise ValueError(f"lifecycle {label} IDs are not unique")
        return indexed

    lifecycle_clock = datetime.fromisoformat(LIFECYCLE_GENERATED_AT.replace("Z", "+00:00"))
    lifecycle_expiry = lifecycle_clock + timedelta(minutes=5)

    def require_fixed_time(value: datetime, label: str) -> None:
        if value != lifecycle_clock:
            raise ValueError(f"lifecycle {label} is not consistent with the fixed clock")

    if bundle.schema_version != LIFECYCLE_SCHEMA_VERSION:
        raise ValueError("unsupported lifecycle schema version")
    if bundle.case_id != LIFECYCLE_CASE_ID or bundle.trace_id != LIFECYCLE_TRACE_ID:
        raise ValueError("lifecycle case or trace identity is invalid")
    if repository_root is not None:
        fixture = repository_root / bundle.fixture_path
        if (
            not fixture.is_file()
            or hashlib.sha256(fixture.read_bytes()).hexdigest() != bundle.fixture_digest
        ):
            raise ValueError("lifecycle fixture identity or digest is invalid")
    if bundle.initial_case.case_id != bundle.case_id:
        raise ValueError("lifecycle initial case identity is invalid")
    require_fixed_time(bundle.initial_case.created_at, "initial case creation time")
    require_fixed_time(bundle.initial_case.updated_at, "initial case update time")

    unique(bundle.evidence, "evidence_id", "evidence")
    if any(
        item.case_id != bundle.case_id or item.trace_id != bundle.trace_id
        for item in bundle.evidence
    ):
        raise ValueError("lifecycle evidence identity is invalid")
    if any(item.content_digest != evidence_content_digest(item) for item in bundle.evidence):
        raise ValueError("lifecycle evidence integrity is invalid")

    decisions = unique(bundle.decisions, "decision_id", "decision")
    intents = unique(bundle.intents, "intent_id", "intent")
    grants = unique(bundle.grants, "grant_id", "grant")
    bridges = unique(bundle.bridge_grants, "authorization_id", "bridge")
    attempts = unique(bundle.attempts, "execution_id", "execution")
    policies = unique(bundle.policy_decisions, "execution_id", "policy")
    rereads = unique(bundle.rereads, "reread_id", "reread")
    effects = unique(bundle.effects, "effect_id", "effect")
    verifications = unique(bundle.verifications, "execution_id", "verification")
    replays = unique(bundle.replays, "replay_id", "replay")
    unique(bundle.actions, "action_id", "action")
    case_events = unique(bundle.case_events, "event_id", "case event")
    preparations = unique(bundle.preparation_transitions, "transition_id", "preparation")

    expected_action_ids = ("receipt-restart", "invoice-release")
    if tuple(item.action_id for item in bundle.actions) != expected_action_ids:
        raise ValueError("lifecycle actions are not the fixed two-action sequence")
    if len(bundle.actions) != 2:
        raise ValueError("lifecycle requires exactly two controlled actions")

    # The persisted event collection must be a complete append-only replay of this
    # generated synthetic case.  This catches missing/extra/reordered events before
    # any action-local relation can be considered valid.
    expected_events = (
        TransitionEvent.INVESTIGATION_STARTED,
        TransitionEvent.RECEIPT_RESTART_RECOMMENDED,
        TransitionEvent.RECEIPT_APPROVAL_REQUESTED,
        TransitionEvent.RECEIPT_APPROVAL_ACCEPTED,
        TransitionEvent.RECEIPT_EXECUTION_STARTED,
        TransitionEvent.RECEIPT_POSTCONDITIONS_VERIFIED,
        TransitionEvent.INVOICE_APPROVAL_REQUESTED,
        TransitionEvent.INVOICE_APPROVAL_ACCEPTED,
        TransitionEvent.INVOICE_EXECUTION_STARTED,
        TransitionEvent.INVOICE_POSTCONDITIONS_VERIFIED,
    )
    if len(bundle.case_events) != len(expected_events):
        raise ValueError("lifecycle case-event collection is incomplete")
    previous_status = bundle.initial_case.status
    previous_version = bundle.initial_case.case_version
    previous_time = bundle.initial_case.updated_at
    ordered_events: list[CaseEvent] = []
    for index, event in enumerate(bundle.case_events):
        if event.event is not expected_events[index]:
            raise ValueError("lifecycle case events are missing, extra, or reordered")
        if (
            event.case_id != bundle.case_id
            or event.trace_id != bundle.trace_id
            or event.prior_version != previous_version
            or event.prior_status is not previous_status
            or event.new_version != previous_version + 1
            or event.occurred_at < previous_time
            or event.occurred_at != lifecycle_clock
            or TRANSITIONS.get((event.prior_status, event.event)) is not event.new_status
            or event.event_id != _case_event_id(event)
        ):
            raise ValueError("lifecycle case-event state-machine chain is invalid")
        try:
            payload = json.loads(event.payload_json)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("lifecycle case-event payload is unreadable") from exc
        if (
            not isinstance(payload, dict)
            or event.payload_json != canonical_json(payload)
            or event.payload_digest != _sha(payload)
        ):
            raise ValueError("lifecycle case-event payload digest is invalid")
        if (
            event.event
            not in {
                TransitionEvent.RECEIPT_RESTART_RECOMMENDED,
                TransitionEvent.INVOICE_POSTCONDITIONS_VERIFIED,
            }
            and payload
        ):
            raise ValueError("lifecycle preparation/execution event carries an unexpected payload")
        previous_version = event.new_version
        previous_status = event.new_status
        previous_time = event.occurred_at
        ordered_events.append(event)
    if (
        bundle.final_state.case.case_version != previous_version
        or bundle.final_state.case.status is not previous_status
    ):
        raise ValueError("lifecycle final case does not close the event chain")
    require_fixed_time(bundle.final_state.case.created_at, "final case creation time")
    require_fixed_time(bundle.final_state.case.updated_at, "final case update time")

    # Every preparation projection must resolve to an actual append-only event.  The
    # projection is never treated as an independent source of truth.
    expected_preparation_event_ids: set[str] = set()
    for action in bundle.actions:
        intent = intents.get(action.intent_id)
        if intent is None:
            raise ValueError("lifecycle action references a missing intent")
        prefix = f"authority-b:{intent.intent_id}:"
        expected = tuple(
            event for event in ordered_events if event.idempotency_key.startswith(prefix)
        )
        expected_preparation_event_ids.update(event.event_id for event in expected)
        selected_ids = action.preparation_transition_ids
        if len(selected_ids) != len(set(selected_ids)):
            raise ValueError("lifecycle preparation transitions are duplicated")
        try:
            selected = tuple(preparations[item] for item in selected_ids)
        except KeyError as exc:
            raise ValueError(
                "lifecycle action references a missing preparation transition"
            ) from exc
        if tuple(item.event_id for item in selected) != tuple(item.event_id for item in expected):
            raise ValueError("lifecycle preparation event sequence is missing, extra, or reordered")
        for projection, event in zip(selected, expected, strict=True):
            if (
                projection.action_id != action.action_id
                or projection.intent_id != intent.intent_id
                or projection.event_id != event.event_id
                or projection.event is not event.event
                or projection.before_version != event.prior_version
                or projection.after_version != event.new_version
                or projection.before_status is not event.prior_status
                or projection.after_status is not event.new_status
                or projection.idempotency_key != event.idempotency_key
                or projection.payload_digest != event.payload_digest
                or projection.event_digest != _case_event_digest(event)
                or event.event_id not in case_events
            ):
                raise ValueError("lifecycle preparation transition is not bound to its CaseEvent")
    if (
        len(bundle.preparation_transitions) != len(expected_preparation_event_ids)
        or set(item.event_id for item in bundle.preparation_transitions)
        != expected_preparation_event_ids
    ):
        raise ValueError("lifecycle preparation collection contains an unrelated event")

    signer = LocalSigner(LIFECYCLE_SIGNING_KEY)
    for action_index, action in enumerate(bundle.actions):
        try:
            decision = decisions[action.decision_id]
            intent = intents[action.intent_id]
            grant = grants[action.grant_id]
            bridge = bridges[action.bridge_authorization_id]
            attempt = attempts[action.execution_id]
            policy = policies[action.execution_id]
            before = rereads[action.before_reread_id]
            after = rereads[action.after_reread_id]
            effect = effects[action.effect_id]
            verification = verifications[action.verification_execution_id]
            replay = replays[action.replay_id]
            start_event = case_events[action.execution_start_event_id]
            selected_preparations = tuple(
                preparations[item] for item in action.preparation_transition_ids
            )
        except KeyError as exc:
            raise ValueError("lifecycle action references a missing record") from exc

        expected_tool = (
            ActionTool.RESTART_RECEIPT_MESSAGE if action_index == 0 else ActionTool.RELEASE_INVOICE
        )
        expected_case_version = 1 if action_index == 0 else 6
        expected_event = (
            TransitionEvent.RECEIPT_EXECUTION_STARTED
            if action.tool is ActionTool.RESTART_RECEIPT_MESSAGE
            else TransitionEvent.INVOICE_EXECUTION_STARTED
        )
        if action.tool is not expected_tool:
            raise ValueError("lifecycle action tool sequence is invalid")
        if before.action_id != action.action_id or before.phase != "BEFORE":
            raise ValueError("lifecycle before reread reference is invalid")
        if after.action_id != action.action_id or after.phase != "AFTER":
            raise ValueError("lifecycle after reread reference is invalid")
        if before.observed_at != lifecycle_clock or after.observed_at != lifecycle_clock:
            raise ValueError("lifecycle reread chronology is inconsistent with the fixed clock")
        if (
            decision.case_id != bundle.case_id
            or decision.trace_id != bundle.trace_id
            or decision.case_version != expected_case_version
            or decision.allowed_action is not action.tool
            or intent.case_id != bundle.case_id
            or intent.trace_id != bundle.trace_id
            or intent.case_version != expected_case_version
            or intent.decision_digest != decision.decision_digest
            or intent.tool is not action.tool
            or intent.intent_digest != grant.intent_digest
            or grant.intent_id != intent.intent_id
            or grant.grant_id != action.grant_id
            or grant.case_id != bundle.case_id
            or grant.trace_id != bundle.trace_id
            or grant.case_version != expected_case_version
            or grant.tool is not action.tool
            or grant.decision_digest != decision.decision_digest
            or intent.status is not QuorumStatus.CONSUMED
            or len(selected_preparations) < 1
            or selected_preparations[0].before_version != grant.case_version
            or selected_preparations[-1].after_version != bridge.case_version
            or start_event.event is not expected_event
            or start_event.prior_version != bridge.case_version
            or start_event.new_version != bridge.case_version + 1
            or start_event.idempotency_key != f"execution-start:{action.execution_id}"
            or start_event.trace_id != bundle.trace_id
            or start_event.case_id != bundle.case_id
            or start_event.prior_status
            != (
                CaseStatus.RECEIPT_ACTION_AUTHORIZED
                if action.tool is ActionTool.RESTART_RECEIPT_MESSAGE
                else CaseStatus.INVOICE_ACTION_AUTHORIZED
            )
            or start_event.new_status
            != (
                CaseStatus.RECEIPT_EXECUTING
                if action.tool is ActionTool.RESTART_RECEIPT_MESSAGE
                else CaseStatus.INVOICE_EXECUTING
            )
            or any(
                item_event.occurred_at != lifecycle_clock
                or item_event.occurred_at < grant.issued_at
                or item_event.occurred_at >= grant.expires_at
                for item_event in (case_events[item.event_id] for item in selected_preparations)
            )
            or start_event.occurred_at != lifecycle_clock
            or start_event.occurred_at < bridge.issued_at
            or start_event.occurred_at >= bridge.expires_at
        ):
            raise ValueError("lifecycle decision, grant, or preparation version closure is invalid")
        if (
            ordered_events.index(start_event)
            != ordered_events.index(case_events[selected_preparations[-1].event_id]) + 1
        ):
            raise ValueError("lifecycle execution-start event is not adjacent to preparation")

        attestations = tuple(
            item for item in bundle.attestations if item.intent_id == intent.intent_id
        )
        if (
            len(attestations) != 2
            or set(item.attestation_id for item in attestations) != set(action.attestation_ids)
            or set(item.attestation_id for item in attestations) != set(grant.approval_ids)
            or set(item.principal_id for item in attestations) != set(grant.principal_ids)
            or set(item.role for item in attestations) != set(grant.roles)
            or len({item.principal_id for item in attestations}) != 2
            or {item.role for item in attestations}
            != {HumanRole.INTEGRATION_OPERATOR, HumanRole.AP_APPROVER}
            or any(item.intent_digest != intent.intent_digest for item in attestations)
            or any(item.decision.value != "APPROVED" for item in attestations)
            or not signer.verify(
                canonical_json(grant.model_dump(mode="json", exclude={"signature"})),
                grant.signature,
            )
        ):
            raise ValueError("lifecycle quorum closure is invalid")
        if (
            intent.created_at != lifecycle_clock
            or intent.expires_at != lifecycle_expiry
            or attestations[0].role is not HumanRole.INTEGRATION_OPERATOR
            or attestations[1].role is not HumanRole.AP_APPROVER
            or any(
                item.attested_at < intent.created_at
                or item.attested_at >= intent.expires_at
                or item.attested_at != lifecycle_clock
                for item in attestations
            )
            or attestations[1].attested_at < attestations[0].attested_at
            or grant.issued_at < attestations[1].attested_at
            or grant.issued_at != lifecycle_clock
            or grant.expires_at != intent.expires_at
            or bridge.issued_at < grant.issued_at
            or bridge.issued_at != lifecycle_clock
            or bridge.expires_at != grant.expires_at
        ):
            raise ValueError("lifecycle authorization temporal closure is invalid")
        attestation_by_id = {item.attestation_id: item for item in attestations}
        if any(
            attestation_by_id[approval_id].principal_id != principal_id
            or attestation_by_id[approval_id].role is not role
            for approval_id, principal_id, role in zip(
                grant.approval_ids, grant.principal_ids, grant.roles, strict=True
            )
        ):
            raise ValueError("lifecycle quorum approval identity ordering is invalid")

        parameters = intent.complete_parameters
        if (
            intent.parameters_digest != _sha(parameters)
            or grant.complete_parameters != parameters
            or grant.parameters_digest != intent.parameters_digest
            or bridge.complete_parameters != parameters
            or _sha(bridge.complete_parameters) != intent.parameters_digest
            or attempt.canonical_parameters != parameters
            or policy.parameters_digest != intent.parameters_digest
        ):
            raise ValueError("lifecycle typed parameter closure is invalid")
        expected_principal_role = (
            ("integration-operator", HumanRole.INTEGRATION_OPERATOR)
            if action.tool is ActionTool.RESTART_RECEIPT_MESSAGE
            else ("ap-approver", HumanRole.AP_APPROVER)
        )
        if (
            bridge.authorization_id != action.bridge_authorization_id
            or bridge.authorization_id != f"authority-b:{grant.grant_id}"
            or bridge.case_id != bundle.case_id
            or bridge.trace_id != bundle.trace_id
            or bridge.case_version != selected_preparations[-1].after_version
            or bridge.tool is not action.tool
            or (bridge.principal_id, bridge.role) != expected_principal_role
            or bridge.evidence_digest
            != evidence_digest(
                tuple(
                    item
                    for item in bundle.evidence
                    if item.evidence_id.startswith(f"{bundle.case_id}:")
                    and (action_index == 1 or ":reread-receipt:" not in item.evidence_id)
                )
            )
            or bridge.action_digest
            != action_digest(
                case_id=bridge.case_id,
                case_version=bridge.case_version,
                principal_id=bridge.principal_id,
                role=bridge.role,
                tool=bridge.tool,
                parameters=parameters,
                admitted_evidence_digest=bridge.evidence_digest,
            )
            or not signer.verify(unsigned_grant_payload(bridge), bridge.signature)
        ):
            raise ValueError("lifecycle bridge grant closure is invalid")

        request_digest = _sha(
            {
                "grant": bridge.model_dump(mode="json"),
                "execution_id": action.execution_id,
                "idempotency_key": action.idempotency_key,
                "principal_id": bridge.principal_id,
                "parameters": parameters,
            }
        )
        if (
            action.idempotency_key != attempt.idempotency_key
            or attempt.execution_id != action.execution_id
            or attempt.authorization_id != bridge.authorization_id
            or attempt.case_id != bundle.case_id
            or attempt.trace_id != bundle.trace_id
            or attempt.tool is not action.tool
            or attempt.status is not ExecutionAttemptStatus.COMPLETED
            or attempt.command_digest != request_digest
            or policy.execution_id != action.execution_id
            or policy.authorization_id != bridge.authorization_id
            or policy.case_id != bundle.case_id
            or policy.trace_id != bundle.trace_id
            or policy.tool is not action.tool
            or policy.trusted_role is not bridge.role
            or policy.principal_id != bridge.principal_id
            or policy.decision is not PolicyOutcome.ALLOW
            or policy.decision_stage is not DecisionStage.EXECUTION_GATE
            or policy.case_version != bridge.case_version
            or policy.evidence_digest != bridge.evidence_digest
            or policy.action_digest != bridge.action_digest
            or attempt.reserved_at != lifecycle_clock
            or attempt.completed_at != lifecycle_clock
            or attempt.reserved_at < bridge.issued_at
            or attempt.reserved_at >= bridge.expires_at
            or attempt.completed_at < attempt.reserved_at
            or attempt.completed_at >= bridge.expires_at
            or policy.decided_at != lifecycle_clock
            or policy.decided_at < attempt.reserved_at
            or policy.decided_at >= bridge.expires_at
        ):
            raise ValueError("lifecycle attempt and execution-policy closure is invalid")

        if (
            _snapshot_digest(before.snapshot) != before.snapshot_digest
            or _snapshot_digest(after.snapshot) != after.snapshot_digest
            or verification.pre_state_digest != before.snapshot_digest
            or verification.post_state_digest != after.snapshot_digest
            or verification.execution_id != action.execution_id
            or verification.authorization_id != bridge.authorization_id
            or verification.case_id != bundle.case_id
            or verification.trace_id != bundle.trace_id
            or verification.operation_result.value != "EXECUTED"
            or verification.executed_at != effect.committed_at
            or verification.executed_at != lifecycle_clock
            or verification.executed_at < policy.decided_at
            or verification.executed_at >= bridge.expires_at
            or effect.committed_at < bridge.issued_at
            or effect.committed_at >= bridge.expires_at
            or tuple(verification.material_document_ids)
            != tuple(item.material_document_id for item in after.snapshot.material_documents)
            or effect.effect_id != f"effect-{action.execution_id}"
            or effect.case_id != bundle.case_id
            or effect.trace_id != bundle.trace_id
            or effect.execution_id != action.execution_id
            or effect.idempotency_key != action.idempotency_key
            or effect.committed_at != verification.executed_at
            or (
                action.tool is ActionTool.RESTART_RECEIPT_MESSAGE
                and effect.effect_type is not EffectType.RECEIPT_RESTART
            )
            or (
                action.tool is ActionTool.RELEASE_INVOICE
                and effect.effect_type is not EffectType.INVOICE_RELEASE
            )
        ):
            raise ValueError("lifecycle reread and receipt identity closure is invalid")
        after_document_ids = tuple(
            item.material_document_id for item in after.snapshot.material_documents
        )
        if action.tool is ActionTool.RESTART_RECEIPT_MESSAGE:
            typed_receipt = RestartReceiptMessageParameters.model_validate(parameters)
            if (
                not after_document_ids
                or effect.source_record_id != typed_receipt.message_id
                or effect.result_record_ids != (after_document_ids[-1],)
                or before.snapshot.failed_message.status.value != "FAILED"
                or after.snapshot.failed_message.status.value != "CONSUMED"
                or after.snapshot.failed_message.consumed_by_execution_id != action.execution_id
                or after.snapshot.failed_message.revision
                != before.snapshot.failed_message.revision + 1
                or after.snapshot.erp_receipt.quantity
                != before.snapshot.erp_receipt.quantity + typed_receipt.quantity
                or after.snapshot.erp_receipt.revision != before.snapshot.erp_receipt.revision + 1
                or len(after.snapshot.material_documents)
                != len(before.snapshot.material_documents) + 1
                or any(
                    item.execution_id == action.execution_id
                    for item in before.snapshot.business_effects
                )
            ):
                raise ValueError("receipt restart reread/effect relation is invalid")
            expected_postconditions = _verify_authoritative_state(
                after.snapshot,
                grant_case_id=bundle.case_id,
                grant_trace_id=bundle.trace_id,
                execution_id=action.execution_id,
                idempotency_key=action.idempotency_key,
                parameters=typed_receipt,
                effect=effect,
                outcome=EnterpriseActionOutcome.EXECUTED,
            )
        else:
            typed_invoice = ReleaseInvoiceParameters.model_validate(parameters)
            if (
                effect.source_record_id != typed_invoice.invoice_id
                or effect.result_record_ids != (typed_invoice.invoice_id,)
                or before.snapshot.invoice.state.value != "HELD"
                or before.snapshot.invoice.hold_reason != typed_invoice.expected_hold_reason
                or after.snapshot.invoice.state.value != "RELEASED"
                or after.snapshot.invoice.hold_reason is not None
                or after.snapshot.invoice.released_by_execution_id != action.execution_id
                or after.snapshot.invoice.revision != before.snapshot.invoice.revision + 1
                or after.snapshot.material_documents != before.snapshot.material_documents
            ):
                raise ValueError("invoice release reread/effect relation is invalid")
            expected_postconditions = _verify_authoritative_state(
                after.snapshot,
                grant_case_id=bundle.case_id,
                grant_trace_id=bundle.trace_id,
                execution_id=action.execution_id,
                idempotency_key=action.idempotency_key,
                parameters=typed_invoice,
                effect=effect,
                outcome=EnterpriseActionOutcome.EXECUTED,
            )
        if verification.postconditions != expected_postconditions or not all(
            expected_postconditions.values()
        ):
            raise ValueError("lifecycle verification postconditions are invalid")

        before_effects = {item.effect_id: item for item in before.snapshot.business_effects}
        after_effects = {item.effect_id: item for item in after.snapshot.business_effects}
        if (
            action.execution_id in {item.execution_id for item in before.snapshot.business_effects}
            or action.idempotency_key
            in {item.idempotency_key for item in before.snapshot.business_effects}
            or after_effects.get(effect.effect_id) != effect
            or set(after_effects) != set(before_effects) | {effect.effect_id}
            or any(after_effects[key] != value for key, value in before_effects.items())
            or len(
                [
                    item
                    for item in after.snapshot.business_effects
                    if item.execution_id == action.execution_id
                ]
            )
            != 1
        ):
            raise ValueError("lifecycle business-effect ledger closure is invalid")
        if (
            replay.action_id != action.action_id
            or replay.execution_id != action.execution_id
            or replay.idempotency_key != action.idempotency_key
            or replay.receipt != verification
            or replay.receipt_digest != _model_digest(verification)
            or replay.effect_count_before != len(after.snapshot.business_effects)
            or replay.effect_count_after != len(after.snapshot.business_effects)
            or replay.effect_delta != 0
            or replay.status != "PASS"
        ):
            raise ValueError("lifecycle replay closure is invalid")

    if bundle.actions[1].before_reread_id not in rereads:
        raise ValueError("lifecycle continuity reread is missing")
    first_after = rereads[bundle.actions[0].after_reread_id]
    second_before = rereads[bundle.actions[1].before_reread_id]
    if (
        first_after.snapshot != second_before.snapshot
        or first_after.snapshot_digest != second_before.snapshot_digest
        or bundle.actions[0].execution_start_event_id == bundle.actions[1].execution_start_event_id
    ):
        raise ValueError("lifecycle cross-action reread continuity is invalid")
    if (
        bundle.final_state.case.case_id != bundle.case_id
        or bundle.final_state.case.scenario_id != bundle.initial_case.scenario_id
        or bundle.final_state.case.discrepancy != bundle.initial_case.discrepancy
        or bundle.final_state.case.created_at != bundle.initial_case.created_at
        or bundle.final_state.case.current_evidence_revision
        != bundle.initial_case.current_evidence_revision
        or bundle.final_state.case.case_version != 10
        or bundle.final_state.case.status is not CaseStatus.CLOSED
        or bundle.final_state.enterprise != rereads[bundle.actions[1].after_reread_id].snapshot
        or len(bundle.final_state.enterprise.business_effects) != len(bundle.actions)
    ):
        raise ValueError("lifecycle final state is not derived from authoritative records")
    return bundle


def build_lifecycle_bundle(repository_root: Path) -> AuthorityBLifecycleBundle:
    return validate_lifecycle_bundle(
        _run_lifecycle(repository_root), repository_root=repository_root
    )


def load_lifecycle_bundle(
    repository_root: Path,
    *,
    path: Path | None = None,
) -> AuthorityBLifecycleBundle:
    artifact_path = path or (repository_root / LIFECYCLE_ARTIFACT_PATH)
    try:
        bundle = AuthorityBLifecycleBundle.model_validate_json(
            artifact_path.read_text(encoding="utf-8")
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("lifecycle bundle is unreadable") from exc
    return validate_lifecycle_bundle(bundle, repository_root=repository_root)


def write_lifecycle_bundle(
    repository_root: Path,
    *,
    output: Path | None = None,
) -> AuthorityBLifecycleBundle:
    bundle = build_lifecycle_bundle(repository_root)
    artifact_path = output or (repository_root / LIFECYCLE_ARTIFACT_PATH)
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(
        canonical_json(bundle.model_dump(mode="json")) + "\n",
        encoding="utf-8",
    )
    return bundle


__all__ = [
    "AuthorityBLifecycleBundle",
    "LIFECYCLE_ARTIFACT_PATH",
    "LIFECYCLE_CASE_ID",
    "LIFECYCLE_GENERATED_AT",
    "LIFECYCLE_SCHEMA_VERSION",
    "LIFECYCLE_TRACE_ID",
    "LifecycleAction",
    "LifecycleFinalState",
    "LifecyclePreparationTransition",
    "LifecycleReplay",
    "LifecycleReread",
    "build_lifecycle_bundle",
    "lifecycle_bundle_digest",
    "load_lifecycle_bundle",
    "validate_lifecycle_bundle",
    "write_lifecycle_bundle",
]
