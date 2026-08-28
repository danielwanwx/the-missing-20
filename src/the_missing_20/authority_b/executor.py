"""Typed Authority-B adapter for the repository-backed controlled executor.

The historical executor owns the hard parts of an enterprise write: reservation,
idempotency, authoritative reread, postcondition verification, receipt persistence,
and crash recovery.  Authority-B does not bypass that path.  It validates the
application-signed two-role grant, atomically creates a private bridge record in the
case ledger, and then delegates only to ``ControlledExecutor``.  An arbitrary effect
callback is intentionally not part of this API.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from the_missing_20.application.authorization_service import (
    LocalPolicy,
    TrustedIdentities,
    action_digest,
    canonical_json,
    evidence_digest,
    unsigned_grant_payload,
)
from the_missing_20.application.diagnosis import diagnose_retryable_message
from the_missing_20.application.executor import ControlledExecutor, SimulatedPersistenceFault
from the_missing_20.authority_b.classifier import (
    classify_operational_state,
    latest_authoritative_evidence,
)
from the_missing_20.authority_b.models import QuorumActionGrant
from the_missing_20.authority_b.quorum import (
    AuthorityBExecutor,
    QuorumAuthorizationService,
    QuorumDenied,
)
from the_missing_20.domain.events import TransitionCommand
from the_missing_20.domain.execution import (
    DecisionStage,
    ExecutionAttempt,
    ExecutionAttemptStatus,
    PolicyDecision,
    PolicyOutcome,
    ReleaseInvoiceParameters,
    RestartReceiptMessageParameters,
    uses_external_id_namespace,
)
from the_missing_20.domain.models import (
    ActionGrant,
    ActionTool,
    Case,
    EvaluationDecision,
    HumanRole,
    InvestigationAssessment,
    InvestigationDecision,
)
from the_missing_20.domain.states import CaseStatus, TransitionEvent
from the_missing_20.ports.case_store import CaseStore
from the_missing_20.ports.clock import Clock
from the_missing_20.ports.enterprise_systems import EnterpriseSystems
from the_missing_20.ports.signer import Signer

ActionParameters = RestartReceiptMessageParameters | ReleaseInvoiceParameters


def _role_for_tool(tool: ActionTool) -> HumanRole:
    if tool is ActionTool.RESTART_RECEIPT_MESSAGE:
        return HumanRole.INTEGRATION_OPERATOR
    if tool is ActionTool.RELEASE_INVOICE:
        return HumanRole.AP_APPROVER
    raise QuorumDenied("Authority-B grant contains an unsupported controlled tool")


def _parameter_type(tool: ActionTool) -> type[ActionParameters]:
    if tool is ActionTool.RESTART_RECEIPT_MESSAGE:
        return RestartReceiptMessageParameters
    if tool is ActionTool.RELEASE_INVOICE:
        return ReleaseInvoiceParameters
    raise QuorumDenied("Authority-B grant contains an unsupported controlled tool")


class AuthorityBControlledExecutor:
    """Execute only an exact, verified Authority-B grant through real recovery code."""

    def __init__(
        self,
        *,
        store: CaseStore,
        enterprise: EnterpriseSystems,
        quorum: QuorumAuthorizationService,
        clock: Clock,
        signer: Signer | None = None,
    ) -> None:
        if not hasattr(store, "bind_and_reserve_authority_b_attempt"):
            raise TypeError("Authority-B controlled execution requires a repository binding")
        self.store = store
        self.enterprise = enterprise
        self.quorum = quorum
        self.clock = clock
        self.signer = signer or quorum.signer
        self.guard = AuthorityBExecutor(signer=self.signer, clock=clock)

    def _parameters(self, grant: QuorumActionGrant) -> ActionParameters:
        model = _parameter_type(grant.tool)
        try:
            parameters = model.model_validate(grant.complete_parameters)
        except (TypeError, ValueError) as exc:
            raise QuorumDenied("Authority-B grant parameters are malformed") from exc
        if parameters.model_dump(mode="json") != grant.complete_parameters:
            raise QuorumDenied("Authority-B grant parameters are not the typed envelope")
        return parameters

    @staticmethod
    def _principal_for_grant(grant: QuorumActionGrant) -> tuple[str, HumanRole]:
        required_role = _role_for_tool(grant.tool)
        pairs = dict(zip(grant.roles, grant.principal_ids, strict=True))
        try:
            return pairs[required_role], required_role
        except KeyError as exc:
            raise QuorumDenied(
                "Authority-B grant has no principal for its controlled tool"
            ) from exc

    def _verify_decision(self, grant: QuorumActionGrant, case: Case) -> None:
        # The case ledger retains every detector/reread record for audit.  Policy
        # verification must classify the latest authoritative read for each source,
        # while the complete history remains bound into the execution bridge ledger.
        evidence = latest_authoritative_evidence(tuple(self.store.list_evidence(grant.case_id)))
        if not evidence:
            raise QuorumDenied("Authority-B execution requires admitted authoritative evidence")
        decision = classify_operational_state(
            evidence,
            case=case,
            trace_id=grant.trace_id,
        )
        if (
            decision.decision_digest != grant.decision_digest
            or decision.source_digest != grant.admitted_evidence_digest
            or decision.eligibility.value != "PENDING_APPROVAL"
            or decision.allowed_action is not grant.tool
        ):
            raise QuorumDenied(
                "Authority-B grant is not bound to the current deterministic decision"
            )

    def _preparation_transitions(
        self,
        grant: QuorumActionGrant,
        case: Case,
    ) -> tuple[TransitionCommand, ...]:
        """Build deterministic lifecycle preparation in one store transaction."""

        now = self.clock.now()
        if grant.tool is ActionTool.RESTART_RECEIPT_MESSAGE:
            if case.status is CaseStatus.RECEIPT_ACTION_AUTHORIZED:
                return ()
            if case.status is CaseStatus.INVESTIGATING:
                evidence = tuple(self.store.list_evidence(grant.case_id))
                hypothesis, evaluation = diagnose_retryable_message(
                    evidence, trace_id=grant.trace_id
                )
                if not (
                    evaluation.decision is EvaluationDecision.ACCEPT
                    and evaluation.allowed_next_action is ActionTool.RESTART_RECEIPT_MESSAGE
                ):
                    raise QuorumDenied("deterministic diagnosis no longer permits receipt restart")
                assessment = InvestigationAssessment(
                    assessment_id=f"authority-b:{grant.intent_id}:assessment",
                    case_id=grant.case_id,
                    trace_id=grant.trace_id,
                    hypothesis=hypothesis,
                    evaluation=evaluation,
                    admitted_evidence_ids=tuple(sorted(item.evidence_id for item in evidence)),
                    missing_evidence_sources=(),
                    decision=InvestigationDecision.RECOMMEND_RECEIPT_RESTART,
                    reason_codes=("AUTHORITY_B_DETERMINISTIC_PREPARATION",),
                    assessed_at=now,
                )
                return (
                    TransitionCommand(
                        case_id=grant.case_id,
                        expected_version=case.case_version,
                        event=TransitionEvent.RECEIPT_RESTART_RECOMMENDED,
                        idempotency_key=f"authority-b:{grant.intent_id}:recommend",
                        trace_id=grant.trace_id,
                        occurred_at=now,
                        assessment=assessment,
                    ),
                    TransitionCommand(
                        case_id=grant.case_id,
                        expected_version=case.case_version + 1,
                        event=TransitionEvent.RECEIPT_APPROVAL_REQUESTED,
                        idempotency_key=f"authority-b:{grant.intent_id}:request",
                        trace_id=grant.trace_id,
                        occurred_at=now,
                    ),
                    TransitionCommand(
                        case_id=grant.case_id,
                        expected_version=case.case_version + 2,
                        event=TransitionEvent.RECEIPT_APPROVAL_ACCEPTED,
                        idempotency_key=f"authority-b:{grant.intent_id}:accept",
                        trace_id=grant.trace_id,
                        occurred_at=now,
                    ),
                )
            if case.status is CaseStatus.AWAITING_RECEIPT_APPROVAL:
                return (
                    TransitionCommand(
                        case_id=grant.case_id,
                        expected_version=case.case_version,
                        event=TransitionEvent.RECEIPT_APPROVAL_ACCEPTED,
                        idempotency_key=f"authority-b:{grant.intent_id}:accept",
                        trace_id=grant.trace_id,
                        occurred_at=now,
                    ),
                )
            if case.status is not CaseStatus.RECEIPT_RESTART_RECOMMENDED:
                raise QuorumDenied("case is not in a receipt-recovery lifecycle state")
            return (
                TransitionCommand(
                    case_id=grant.case_id,
                    expected_version=case.case_version,
                    event=TransitionEvent.RECEIPT_APPROVAL_REQUESTED,
                    idempotency_key=f"authority-b:{grant.intent_id}:request",
                    trace_id=grant.trace_id,
                    occurred_at=now,
                ),
                TransitionCommand(
                    case_id=grant.case_id,
                    expected_version=case.case_version + 1,
                    event=TransitionEvent.RECEIPT_APPROVAL_ACCEPTED,
                    idempotency_key=f"authority-b:{grant.intent_id}:accept",
                    trace_id=grant.trace_id,
                    occurred_at=now,
                ),
            )

        if grant.tool is ActionTool.RELEASE_INVOICE:
            if case.status is CaseStatus.INVOICE_ACTION_AUTHORIZED:
                return ()
            if case.status is CaseStatus.AWAITING_INVOICE_APPROVAL:
                return (
                    TransitionCommand(
                        case_id=grant.case_id,
                        expected_version=case.case_version,
                        event=TransitionEvent.INVOICE_APPROVAL_ACCEPTED,
                        idempotency_key=f"authority-b:{grant.intent_id}:accept",
                        trace_id=grant.trace_id,
                        occurred_at=now,
                    ),
                )
            if case.status in {
                CaseStatus.RECEIPT_ALREADY_VERIFIED,
                CaseStatus.RECEIPT_VERIFIED,
            }:
                return (
                    TransitionCommand(
                        case_id=grant.case_id,
                        expected_version=case.case_version,
                        event=TransitionEvent.INVOICE_APPROVAL_REQUESTED,
                        idempotency_key=f"authority-b:{grant.intent_id}:request",
                        trace_id=grant.trace_id,
                        occurred_at=now,
                    ),
                    TransitionCommand(
                        case_id=grant.case_id,
                        expected_version=case.case_version + 1,
                        event=TransitionEvent.INVOICE_APPROVAL_ACCEPTED,
                        idempotency_key=f"authority-b:{grant.intent_id}:accept",
                        trace_id=grant.trace_id,
                        occurred_at=now,
                    ),
                )
            raise QuorumDenied("case is not in an invoice-recovery lifecycle state")
        raise QuorumDenied("Authority-B grant contains an unsupported controlled tool")

    def _bridge_grant(
        self,
        grant: QuorumActionGrant,
        *,
        parameters: ActionParameters,
        case_version: int,
    ) -> ActionGrant:
        principal_id, role = self._principal_for_grant(grant)
        parameter_data = parameters.model_dump(mode="json")
        legacy_evidence_digest = evidence_digest(tuple(self.store.list_evidence(grant.case_id)))
        unsigned = ActionGrant(
            authorization_id=f"authority-b:{grant.grant_id}",
            case_id=grant.case_id,
            trace_id=grant.trace_id,
            case_version=case_version,
            principal_id=principal_id,
            role=role,
            tool=grant.tool,
            complete_parameters=parameter_data,
            evidence_digest=legacy_evidence_digest,
            action_digest=action_digest(
                case_id=grant.case_id,
                case_version=case_version,
                principal_id=principal_id,
                role=role,
                tool=grant.tool,
                parameters=parameter_data,
                admitted_evidence_digest=legacy_evidence_digest,
            ),
            issued_at=self.clock.now(),
            expires_at=grant.expires_at,
            signature="pending",
        )
        return unsigned.model_copy(
            update={"signature": self.signer.sign(unsigned_grant_payload(unsigned))}
        )

    def _reservation_records(
        self,
        bridge: ActionGrant,
        *,
        parameters: ActionParameters,
        execution_id: str,
        idempotency_key: str,
    ) -> tuple[ExecutionAttempt, PolicyDecision, TransitionCommand]:
        parameter_data = parameters.model_dump(mode="json")
        request_digest = hashlib.sha256(
            canonical_json(
                {
                    "grant": bridge.model_dump(mode="json"),
                    "execution_id": execution_id,
                    "idempotency_key": idempotency_key,
                    "principal_id": bridge.principal_id,
                    "parameters": parameter_data,
                }
            ).encode()
        ).hexdigest()
        evidence_value = evidence_digest(tuple(self.store.list_evidence(bridge.case_id)))
        parameter_digest = hashlib.sha256(canonical_json(parameter_data).encode()).hexdigest()
        now = self.clock.now()
        decision = PolicyDecision(
            decision_id=f"decision-execution-{execution_id}",
            case_id=bridge.case_id,
            trace_id=bridge.trace_id,
            authorization_id=bridge.authorization_id,
            execution_id=execution_id,
            principal_id=bridge.principal_id,
            trusted_role=bridge.role,
            tool=bridge.tool,
            decision=PolicyOutcome.ALLOW,
            decision_stage=DecisionStage.EXECUTION_GATE,
            reason_codes=("ALL_CHECKS_PASSED",),
            case_version=bridge.case_version,
            parameters_digest=parameter_digest,
            evidence_digest=evidence_value,
            action_digest=bridge.action_digest,
            decided_at=now,
        )
        attempt = ExecutionAttempt(
            execution_id=execution_id,
            authorization_id=bridge.authorization_id,
            case_id=bridge.case_id,
            trace_id=bridge.trace_id,
            idempotency_key=idempotency_key,
            tool=bridge.tool,
            canonical_parameters=parameter_data,
            command_digest=request_digest,
            status=ExecutionAttemptStatus.RESERVED,
            reserved_at=now,
            completed_at=None,
        )
        execution_event = {
            ActionTool.RESTART_RECEIPT_MESSAGE: TransitionEvent.RECEIPT_EXECUTION_STARTED,
            ActionTool.RELEASE_INVOICE: TransitionEvent.INVOICE_EXECUTION_STARTED,
        }[bridge.tool]
        transition = TransitionCommand(
            case_id=bridge.case_id,
            expected_version=bridge.case_version,
            event=execution_event,
            idempotency_key=f"execution-start:{execution_id}",
            trace_id=bridge.trace_id,
            occurred_at=now,
        )
        return attempt, decision, transition

    def execute(
        self,
        grant: object,
        *,
        execution_id: str,
        idempotency_key: str,
        fail_after_reservation: bool = False,
        fail_after_enterprise_commit: bool = False,
        now: datetime | None = None,
    ) -> tuple[Any, Any | None]:
        """Run a verified quorum through reservation, mutation, reread, and replay."""

        if uses_external_id_namespace(execution_id) or uses_external_id_namespace(idempotency_key):
            raise QuorumDenied("local Authority-B requests cannot use the external ID namespace")
        checked = self.guard.validate_grant(grant, now=now)
        self.quorum.ensure_execution_available(
            checked,
            execution_id=execution_id,
            idempotency_key=idempotency_key,
            at=now,
        )
        parameters = self._parameters(checked)
        binding = self.store.get_authority_b_binding(checked.intent_id)
        if binding is None:
            current = self.store.get_case(checked.case_id)
            if current.case_version != checked.case_version:
                raise QuorumDenied("Authority-B quorum intent is stale for the current case")
            self._verify_decision(checked, current)
            preparations = self._preparation_transitions(checked, current)
            bridge = self._bridge_grant(
                checked,
                parameters=parameters,
                case_version=checked.case_version + len(preparations),
            )
            attempt, reservation_decision, execution_transition = self._reservation_records(
                bridge,
                parameters=parameters,
                execution_id=execution_id,
                idempotency_key=idempotency_key,
            )
            binding_grant, reserved = self.store.bind_and_reserve_authority_b_attempt(
                grant=checked,
                bridge_grant=bridge,
                preparation_transitions=preparations,
                attempt=attempt,
                decision=reservation_decision,
                execution_transition=execution_transition,
            )
            if reserved and fail_after_reservation:
                raise SimulatedPersistenceFault(
                    "Authority-B attempt reserved before enterprise mutation"
                )
        else:
            bound_grant, binding_grant = binding
            if bound_grant.grant_digest != checked.grant_digest:
                raise QuorumDenied("Authority-B binding is for a different quorum grant")

        # The bridge's role-specific principal is the only execution identity accepted
        # by LocalPolicy.  Both quorum principals remain present in the trusted map.
        identity_map = {
            principal: role
            for role, principal in zip(checked.roles, checked.principal_ids, strict=True)
        }
        policy = LocalPolicy(
            store=self.store,
            signer=self.signer,
            identities=TrustedIdentities(identity_map),
            clock=self.clock,
        )
        controlled = ControlledExecutor(
            store=self.store,
            enterprise=self.enterprise,
            policy=policy,
            clock=self.clock,
        )
        try:
            result = controlled.execute(
                authorization_id=binding_grant.authorization_id,
                principal_id=binding_grant.principal_id,
                parameters=parameters,
                execution_id=execution_id,
                idempotency_key=idempotency_key,
                fail_after_reservation=fail_after_reservation,
                fail_after_enterprise_commit=fail_after_enterprise_commit,
            )
        except BaseException:
            recovered_attempt = self.store.get_attempt(execution_id)
            if recovered_attempt is not None and recovered_attempt.status.value != "RESERVED":
                self.quorum.mark_consumed(
                    checked,
                    execution_id=execution_id,
                    idempotency_key=idempotency_key,
                    at=now,
                )
            raise
        self.quorum.mark_consumed(
            checked,
            execution_id=execution_id,
            idempotency_key=idempotency_key,
            at=now,
        )
        return result


__all__ = ["AuthorityBControlledExecutor"]
