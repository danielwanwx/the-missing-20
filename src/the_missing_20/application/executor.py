"""Reserved-attempt executor with idempotent enterprise writes and verification."""

from __future__ import annotations

import hashlib
from collections.abc import Callable

from the_missing_20.application.authorization_service import (
    ActionParameters,
    LocalPolicy,
    canonical_json,
)
from the_missing_20.application.verifier import (
    closure_facts,
    verify_invoice_release,
    verify_receipt_restart,
)
from the_missing_20.domain.enterprise import (
    BusinessEffect,
    EnterpriseActionOutcome,
    EnterpriseSnapshot,
)
from the_missing_20.domain.errors import AuthorizationDenied, IdempotencyConflict
from the_missing_20.domain.events import TransitionCommand
from the_missing_20.domain.execution import (
    DecisionStage,
    ExecutionAttempt,
    ExecutionAttemptStatus,
    GrantStatus,
    PolicyDecision,
    PolicyOutcome,
    ReleaseInvoiceParameters,
    RestartReceiptMessageParameters,
)
from the_missing_20.domain.models import ActionTool, ExecutionReceipt, OperationResult
from the_missing_20.domain.states import TransitionEvent
from the_missing_20.ports.case_store import CaseStore
from the_missing_20.ports.clock import Clock
from the_missing_20.ports.enterprise_systems import EnterprisePreconditionFailed, EnterpriseSystems


class SimulatedPersistenceFault(RuntimeError):
    """Raised only by the deterministic crash-consistency test seam."""


def _verify_authoritative_state(
    snapshot: EnterpriseSnapshot,
    *,
    grant_case_id: str,
    grant_trace_id: str,
    execution_id: str,
    idempotency_key: str,
    parameters: ActionParameters,
    effect: BusinessEffect | None,
    outcome: EnterpriseActionOutcome | None,
) -> dict[str, bool]:
    if isinstance(parameters, RestartReceiptMessageParameters):
        return verify_receipt_restart(
            snapshot,
            case_id=grant_case_id,
            trace_id=grant_trace_id,
            execution_id=execution_id,
            idempotency_key=idempotency_key,
            parameters=parameters,
            effect=effect,
            outcome=outcome,
        )
    return verify_invoice_release(
        snapshot,
        case_id=grant_case_id,
        trace_id=grant_trace_id,
        execution_id=execution_id,
        idempotency_key=idempotency_key,
        parameters=parameters,
        effect=effect,
        outcome=outcome,
    )


class ControlledExecutor:
    def __init__(
        self,
        *,
        store: CaseStore,
        enterprise: EnterpriseSystems,
        policy: LocalPolicy,
        clock: Clock,
    ) -> None:
        self.store = store
        self.enterprise = enterprise
        self.policy = policy
        self.clock = clock

    def execute(
        self,
        *,
        authorization_id: str,
        principal_id: str,
        parameters: ActionParameters,
        execution_id: str,
        idempotency_key: str,
        fail_after_reservation: bool = False,
        fail_after_enterprise_commit: bool = False,
        post_commit_hook: Callable[[EnterpriseSystems], None] | None = None,
    ) -> tuple[ExecutionReceipt, PolicyDecision | None]:
        occurred_at = self.clock.now()
        grant, grant_status = self.store.get_grant(authorization_id)
        request_digest = hashlib.sha256(
            canonical_json(
                {
                    "grant": grant.model_dump(mode="json"),
                    "execution_id": execution_id,
                    "idempotency_key": idempotency_key,
                    "principal_id": principal_id,
                    "parameters": parameters.model_dump(mode="json"),
                }
            ).encode()
        ).hexdigest()
        attempt = self.store.get_attempt(execution_id)
        decision: PolicyDecision | None = None
        if attempt is None:
            if grant_status is not GrantStatus.ISSUED:
                raise AuthorizationDenied("authorization is not available for a new attempt")
            decision = self.policy.evaluate_execution(
                grant=grant,
                principal_id=principal_id,
                execution_id=execution_id,
                parameters=parameters,
            )
            if decision.decision is PolicyOutcome.DENY:
                self.store.save_policy_decision(decision)
                raise AuthorizationDenied(",".join(decision.reason_codes))
            attempt = ExecutionAttempt(
                execution_id=execution_id,
                authorization_id=grant.authorization_id,
                case_id=grant.case_id,
                trace_id=grant.trace_id,
                idempotency_key=idempotency_key,
                tool=grant.tool,
                canonical_parameters=parameters.model_dump(mode="json"),
                command_digest=request_digest,
                status=ExecutionAttemptStatus.RESERVED,
                reserved_at=occurred_at,
                completed_at=None,
            )
            case = self.store.get_case(grant.case_id)
            transition_event = {
                ActionTool.RESTART_RECEIPT_MESSAGE: TransitionEvent.RECEIPT_EXECUTION_STARTED,
                ActionTool.RELEASE_INVOICE: TransitionEvent.INVOICE_EXECUTION_STARTED,
            }[grant.tool]
            self.store.reserve_attempt(
                attempt=attempt,
                decision=decision,
                transition=TransitionCommand(
                    case_id=grant.case_id,
                    expected_version=case.case_version,
                    event=transition_event,
                    idempotency_key=f"execution-start:{execution_id}",
                    trace_id=grant.trace_id,
                    occurred_at=occurred_at,
                ),
            )
            if fail_after_reservation:
                raise SimulatedPersistenceFault("attempt reserved before enterprise mutation")
        else:
            recovery_reasons = self.policy.validate_reserved_recovery(
                grant=grant,
                attempt=attempt,
                principal_id=principal_id,
                parameters=parameters,
            )
            if recovery_reasons:
                reservation_decision = next(
                    item
                    for item in self.store.list_policy_decisions(attempt.case_id)
                    if item.execution_id == execution_id and item.decision is PolicyOutcome.ALLOW
                )
                self.store.save_policy_decision(
                    PolicyDecision(
                        decision_id=f"decision-deny-recovery-{execution_id}",
                        case_id=attempt.case_id,
                        trace_id=attempt.trace_id,
                        authorization_id=attempt.authorization_id,
                        execution_id=execution_id,
                        principal_id=principal_id,
                        trusted_role=reservation_decision.trusted_role,
                        tool=attempt.tool,
                        decision=PolicyOutcome.DENY,
                        decision_stage=DecisionStage.EXECUTION_GATE,
                        reason_codes=recovery_reasons,
                        case_version=self.store.get_case(attempt.case_id).case_version,
                        parameters_digest=hashlib.sha256(
                            canonical_json(parameters.model_dump(mode="json")).encode()
                        ).hexdigest(),
                        evidence_digest=grant.evidence_digest,
                        action_digest=grant.action_digest,
                        decided_at=occurred_at,
                    )
                )
                raise AuthorizationDenied("reserved recovery validation failed")
            if (
                attempt.command_digest != request_digest
                or attempt.idempotency_key != idempotency_key
            ):
                raise IdempotencyConflict("recovery request does not match the reserved attempt")
            if attempt.status is not ExecutionAttemptStatus.RESERVED:
                if grant_status is not GrantStatus.CONSUMED:
                    raise IdempotencyConflict("completed attempt does not have a consumed grant")
                receipts = self.store.list_receipts(grant.case_id)
                for receipt in receipts:
                    if receipt.execution_id == execution_id:
                        return receipt, None
                raise IdempotencyConflict("completed attempt is missing its execution receipt")
            if grant_status is not GrantStatus.RESERVED:
                raise AuthorizationDenied("reserved attempt does not have a reserved grant")

        committed_effect = self.enterprise.get_business_effect(idempotency_key)
        if occurred_at > grant.expires_at and committed_effect is None:
            reason = "RESERVED_GRANT_EXPIRED_WITHOUT_EFFECT"
            if not any(
                existing.execution_id == execution_id and reason in existing.reason_codes
                for existing in self.store.list_policy_decisions(grant.case_id)
            ):
                self.store.save_policy_decision(
                    PolicyDecision(
                        decision_id=f"decision-deny-expired-{execution_id}",
                        case_id=grant.case_id,
                        trace_id=grant.trace_id,
                        authorization_id=grant.authorization_id,
                        execution_id=execution_id,
                        principal_id=principal_id,
                        trusted_role=grant.role,
                        tool=grant.tool,
                        decision=PolicyOutcome.DENY,
                        decision_stage=DecisionStage.EXECUTION_GATE,
                        reason_codes=(reason,),
                        case_version=self.store.get_case(grant.case_id).case_version,
                        parameters_digest=hashlib.sha256(
                            canonical_json(parameters.model_dump(mode="json")).encode()
                        ).hexdigest(),
                        evidence_digest=grant.evidence_digest,
                        action_digest=grant.action_digest,
                        decided_at=occurred_at,
                    )
                )
            raise AuthorizationDenied("reserved grant expired before any enterprise effect")

        try:
            if grant.tool is ActionTool.RESTART_RECEIPT_MESSAGE:
                if not isinstance(parameters, RestartReceiptMessageParameters):
                    raise TypeError("receipt grant requires receipt parameters")
                mutation = self.enterprise.restart_receipt_message(
                    case_id=grant.case_id,
                    trace_id=grant.trace_id,
                    execution_id=execution_id,
                    idempotency_key=idempotency_key,
                    parameters=parameters,
                    committed_at=occurred_at,
                )
                verified_event = TransitionEvent.RECEIPT_POSTCONDITIONS_VERIFIED
            else:
                if not isinstance(parameters, ReleaseInvoiceParameters):
                    raise TypeError("invoice grant requires invoice parameters")
                mutation = self.enterprise.release_invoice(
                    case_id=grant.case_id,
                    trace_id=grant.trace_id,
                    execution_id=execution_id,
                    idempotency_key=idempotency_key,
                    parameters=parameters,
                    committed_at=occurred_at,
                )
                verified_event = TransitionEvent.INVOICE_POSTCONDITIONS_VERIFIED
        except EnterprisePreconditionFailed as exc:
            authoritative_state = self.enterprise.read_snapshot()
            state_digest = hashlib.sha256(
                authoritative_state.model_dump_json().encode()
            ).hexdigest()
            denial = PolicyDecision(
                decision_id=f"decision-deny-precondition-{execution_id}",
                case_id=grant.case_id,
                trace_id=grant.trace_id,
                authorization_id=grant.authorization_id,
                execution_id=execution_id,
                principal_id=principal_id,
                trusted_role=grant.role,
                tool=grant.tool,
                decision=PolicyOutcome.DENY,
                decision_stage=DecisionStage.EXECUTION_GATE,
                reason_codes=("ENTERPRISE_PRECONDITION_FAILED",),
                case_version=self.store.get_case(grant.case_id).case_version,
                parameters_digest=hashlib.sha256(
                    canonical_json(parameters.model_dump(mode="json")).encode()
                ).hexdigest(),
                evidence_digest=grant.evidence_digest,
                action_digest=grant.action_digest,
                decided_at=occurred_at,
            )
            self.store.save_policy_decision(denial)
            failed_receipt = ExecutionReceipt(
                execution_id=execution_id,
                authorization_id=grant.authorization_id,
                case_id=grant.case_id,
                pre_state_digest=state_digest,
                operation_result=OperationResult.FAILED,
                post_state_digest=state_digest,
                postconditions=_verify_authoritative_state(
                    authoritative_state,
                    grant_case_id=grant.case_id,
                    grant_trace_id=grant.trace_id,
                    execution_id=execution_id,
                    idempotency_key=idempotency_key,
                    parameters=parameters,
                    effect=None,
                    outcome=None,
                ),
                material_document_ids=tuple(
                    document.material_document_id
                    for document in authoritative_state.material_documents
                ),
                executed_at=occurred_at,
                trace_id=grant.trace_id,
            )
            self.store.complete_attempt(
                receipt=failed_receipt,
                completed_attempt=attempt.model_copy(
                    update={
                        "status": ExecutionAttemptStatus.VERIFICATION_FAILED,
                        "completed_at": occurred_at,
                    }
                ),
                transition=None,
            )
            raise AuthorizationDenied("enterprise preconditions changed before execution") from exc

        if post_commit_hook is not None:
            post_commit_hook(self.enterprise)
        if fail_after_enterprise_commit:
            raise SimulatedPersistenceFault("enterprise committed before case receipt persistence")

        authoritative_post_state = self.enterprise.read_snapshot()
        postconditions = _verify_authoritative_state(
            authoritative_post_state,
            grant_case_id=grant.case_id,
            grant_trace_id=grant.trace_id,
            execution_id=execution_id,
            idempotency_key=idempotency_key,
            parameters=parameters,
            effect=mutation.effect,
            outcome=mutation.outcome,
        )

        successful = all(postconditions.values())
        receipt = ExecutionReceipt(
            execution_id=execution_id,
            authorization_id=grant.authorization_id,
            case_id=grant.case_id,
            pre_state_digest=hashlib.sha256(
                mutation.pre_state.model_dump_json().encode()
            ).hexdigest(),
            operation_result=(
                OperationResult(mutation.outcome.value) if successful else OperationResult.FAILED
            ),
            post_state_digest=hashlib.sha256(
                authoritative_post_state.model_dump_json().encode()
            ).hexdigest(),
            postconditions=postconditions,
            material_document_ids=tuple(
                document.material_document_id
                for document in authoritative_post_state.material_documents
            ),
            executed_at=occurred_at,
            trace_id=grant.trace_id,
        )
        completed_attempt = attempt.model_copy(
            update={
                "status": (
                    ExecutionAttemptStatus.COMPLETED
                    if successful
                    else ExecutionAttemptStatus.VERIFICATION_FAILED
                ),
                "completed_at": occurred_at,
            }
        )
        transition = None
        if successful:
            case = self.store.get_case(grant.case_id)
            transition = TransitionCommand(
                case_id=grant.case_id,
                expected_version=case.case_version,
                event=verified_event,
                idempotency_key=f"execution-verified:{execution_id}",
                trace_id=grant.trace_id,
                occurred_at=occurred_at,
                closure_facts=(
                    closure_facts(authoritative_post_state)
                    if verified_event is TransitionEvent.INVOICE_POSTCONDITIONS_VERIFIED
                    else None
                ),
            )
        self.store.complete_attempt(
            receipt=receipt,
            completed_attempt=completed_attempt,
            transition=transition,
        )
        return receipt, decision
