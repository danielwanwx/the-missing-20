"""Trusted identity approvals, signed grants, and deny-by-default local policy."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from the_missing_20.domain.errors import AuthorizationDenied
from the_missing_20.domain.events import TransitionCommand
from the_missing_20.domain.execution import (
    DecisionStage,
    ExecutionAttempt,
    PolicyDecision,
    PolicyOutcome,
    ReleaseInvoiceParameters,
    RestartReceiptMessageParameters,
)
from the_missing_20.domain.models import (
    ActionGrant,
    ActionTool,
    Approval,
    ApprovalDecision,
    EvidenceItem,
    HumanRole,
)
from the_missing_20.domain.states import CaseStatus, TransitionEvent
from the_missing_20.ports.case_store import CaseStore
from the_missing_20.ports.clock import Clock
from the_missing_20.ports.signer import Signer

ActionParameters = RestartReceiptMessageParameters | ReleaseInvoiceParameters


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def evidence_digest(evidence: tuple[EvidenceItem, ...]) -> str:
    return digest(
        [
            {"evidence_id": item.evidence_id, "content_digest": item.content_digest}
            for item in sorted(evidence, key=lambda item: item.evidence_id)
        ]
    )


def action_digest(
    *,
    case_id: str,
    case_version: int,
    principal_id: str,
    role: HumanRole,
    tool: ActionTool,
    parameters: dict[str, Any],
    admitted_evidence_digest: str,
) -> str:
    return digest(
        {
            "case_id": case_id,
            "case_version": case_version,
            "principal_id": principal_id,
            "role": role.value,
            "tool": tool.value,
            "parameters": parameters,
            "evidence_digest": admitted_evidence_digest,
        }
    )


def unsigned_grant_payload(grant: ActionGrant) -> str:
    return canonical_json(grant.model_dump(mode="json", exclude={"signature"}))


@dataclass(frozen=True, slots=True)
class IdentityContext:
    principal_id: str
    role: HumanRole


class TrustedIdentities:
    def __init__(self, assignments: dict[str, HumanRole]) -> None:
        self._assignments = dict(assignments)

    def resolve(self, principal_id: str) -> IdentityContext:
        try:
            return IdentityContext(principal_id=principal_id, role=self._assignments[principal_id])
        except KeyError as exc:
            raise AuthorizationDenied("principal is not in the trusted identity context") from exc


class AuthorizationService:
    def __init__(
        self,
        *,
        store: CaseStore,
        signer: Signer,
        identities: TrustedIdentities,
        clock: Clock,
        grant_ttl: timedelta = timedelta(minutes=5),
    ) -> None:
        self.store = store
        self.signer = signer
        self.identities = identities
        self.clock = clock
        self.grant_ttl = grant_ttl

    def approve(
        self,
        *,
        case_id: str,
        principal_id: str,
        tool: ActionTool,
        parameters: ActionParameters,
        approval_id: str,
        authorization_id: str,
    ) -> ActionGrant:
        occurred_at = self.clock.now()
        trace_id = self.store.get_genesis(case_id).trace_id
        expected_parameter_type = {
            ActionTool.RESTART_RECEIPT_MESSAGE: RestartReceiptMessageParameters,
            ActionTool.RELEASE_INVOICE: ReleaseInvoiceParameters,
        }[tool]
        if type(parameters) is not expected_parameter_type:
            raise AuthorizationDenied("tool and parameter envelope do not match")
        identity = self.identities.resolve(principal_id)
        case = self.store.get_case(case_id)
        parameter_data = parameters.model_dump(mode="json")
        parameter_digest = digest(parameter_data)
        admitted_digest = evidence_digest(self.store.list_evidence(case_id))
        required = {
            ActionTool.RESTART_RECEIPT_MESSAGE: (
                HumanRole.INTEGRATION_OPERATOR,
                CaseStatus.AWAITING_RECEIPT_APPROVAL,
                TransitionEvent.RECEIPT_APPROVAL_ACCEPTED,
            ),
            ActionTool.RELEASE_INVOICE: (
                HumanRole.AP_APPROVER,
                CaseStatus.AWAITING_INVOICE_APPROVAL,
                TransitionEvent.INVOICE_APPROVAL_ACCEPTED,
            ),
        }[tool]
        required_role, required_status, accepted_event = required
        if identity.role is not required_role or case.status is not required_status:
            denied_action_digest = action_digest(
                case_id=case_id,
                case_version=case.case_version,
                principal_id=principal_id,
                role=identity.role,
                tool=tool,
                parameters=parameter_data,
                admitted_evidence_digest=admitted_digest,
            )
            self.store.save_policy_decision(
                PolicyDecision(
                    decision_id=f"decision-deny-{approval_id}",
                    case_id=case_id,
                    trace_id=trace_id,
                    authorization_id=None,
                    execution_id=None,
                    principal_id=principal_id,
                    trusted_role=identity.role,
                    tool=tool,
                    decision=PolicyOutcome.DENY,
                    decision_stage=DecisionStage.APPROVAL_GATE,
                    reason_codes=("ROLE_OR_CASE_STATUS_NOT_ELIGIBLE",),
                    case_version=case.case_version,
                    parameters_digest=parameter_digest,
                    evidence_digest=admitted_digest,
                    action_digest=denied_action_digest,
                    decided_at=occurred_at,
                )
            )
            raise AuthorizationDenied("role or case status is not eligible for this approval")

        grant_version = case.case_version + 1
        bound_action_digest = action_digest(
            case_id=case_id,
            case_version=grant_version,
            principal_id=principal_id,
            role=identity.role,
            tool=tool,
            parameters=parameter_data,
            admitted_evidence_digest=admitted_digest,
        )
        unsigned = ActionGrant(
            authorization_id=authorization_id,
            case_id=case_id,
            trace_id=trace_id,
            case_version=grant_version,
            principal_id=principal_id,
            role=identity.role,
            tool=tool,
            complete_parameters=parameter_data,
            evidence_digest=admitted_digest,
            action_digest=bound_action_digest,
            issued_at=occurred_at,
            expires_at=occurred_at + self.grant_ttl,
            signature="pending",
        )
        grant = unsigned.model_copy(
            update={"signature": self.signer.sign(unsigned_grant_payload(unsigned))}
        )
        approval = Approval(
            approval_id=approval_id,
            case_id=case_id,
            trace_id=trace_id,
            case_version=case.case_version,
            principal_id=principal_id,
            role=identity.role,
            tool=tool,
            parameters_digest=parameter_digest,
            decision=ApprovalDecision.APPROVED,
            decided_at=occurred_at,
        )
        transition = TransitionCommand(
            case_id=case_id,
            expected_version=case.case_version,
            event=accepted_event,
            idempotency_key=f"approval:{approval_id}",
            trace_id=trace_id,
            occurred_at=occurred_at,
        )
        self.store.save_approval_and_grant(approval, grant, transition)
        return grant


class LocalPolicy:
    def __init__(
        self,
        *,
        store: CaseStore,
        signer: Signer,
        identities: TrustedIdentities,
        clock: Clock,
    ) -> None:
        self.store = store
        self.signer = signer
        self.identities = identities
        self.clock = clock

    def evaluate_execution(
        self,
        *,
        grant: ActionGrant,
        principal_id: str,
        execution_id: str,
        parameters: ActionParameters,
    ) -> PolicyDecision:
        decided_at = self.clock.now()
        identity = self.identities.resolve(principal_id)
        case = self.store.get_case(grant.case_id)
        parameter_data = parameters.model_dump(mode="json")
        parameter_digest = digest(parameter_data)
        admitted_digest = evidence_digest(self.store.list_evidence(grant.case_id))
        recomputed_action = action_digest(
            case_id=grant.case_id,
            case_version=grant.case_version,
            principal_id=grant.principal_id,
            role=grant.role,
            tool=grant.tool,
            parameters=parameter_data,
            admitted_evidence_digest=admitted_digest,
        )
        required_status = {
            ActionTool.RESTART_RECEIPT_MESSAGE: CaseStatus.RECEIPT_ACTION_AUTHORIZED,
            ActionTool.RELEASE_INVOICE: CaseStatus.INVOICE_ACTION_AUTHORIZED,
        }[grant.tool]
        reasons: list[str] = []
        if identity.principal_id != grant.principal_id or identity.role is not grant.role:
            reasons.append("IDENTITY_MISMATCH")
        if case.case_version != grant.case_version or case.status is not required_status:
            reasons.append("CASE_VERSION_OR_STATUS_MISMATCH")
        if decided_at > grant.expires_at:
            reasons.append("GRANT_EXPIRED")
        if parameter_data != grant.complete_parameters:
            reasons.append("PARAMETERS_MISMATCH")
        if parameter_digest != digest(grant.complete_parameters):
            reasons.append("PARAMETERS_DIGEST_MISMATCH")
        if admitted_digest != grant.evidence_digest:
            reasons.append("EVIDENCE_DIGEST_MISMATCH")
        if recomputed_action != grant.action_digest:
            reasons.append("ACTION_DIGEST_MISMATCH")
        if not self.signer.verify(unsigned_grant_payload(grant), grant.signature):
            reasons.append("SIGNATURE_INVALID")
        outcome = PolicyOutcome.DENY if reasons else PolicyOutcome.ALLOW
        return PolicyDecision(
            decision_id=f"decision-execution-{execution_id}",
            case_id=grant.case_id,
            trace_id=grant.trace_id,
            authorization_id=grant.authorization_id,
            execution_id=execution_id,
            principal_id=principal_id,
            trusted_role=identity.role,
            tool=grant.tool,
            decision=outcome,
            decision_stage=DecisionStage.EXECUTION_GATE,
            reason_codes=tuple(reasons) if reasons else ("ALL_CHECKS_PASSED",),
            case_version=case.case_version,
            parameters_digest=parameter_digest,
            evidence_digest=admitted_digest,
            action_digest=recomputed_action,
            decided_at=decided_at,
        )

    def validate_reserved_recovery(
        self,
        *,
        grant: ActionGrant,
        attempt: ExecutionAttempt,
        principal_id: str,
        parameters: ActionParameters,
    ) -> tuple[str, ...]:
        identity = self.identities.resolve(principal_id)
        parameter_data = parameters.model_dump(mode="json")
        admitted_digest = evidence_digest(self.store.list_evidence(grant.case_id))
        recomputed_action = action_digest(
            case_id=grant.case_id,
            case_version=grant.case_version,
            principal_id=grant.principal_id,
            role=grant.role,
            tool=grant.tool,
            parameters=parameter_data,
            admitted_evidence_digest=admitted_digest,
        )
        expected_parameter_type = {
            ActionTool.RESTART_RECEIPT_MESSAGE: RestartReceiptMessageParameters,
            ActionTool.RELEASE_INVOICE: ReleaseInvoiceParameters,
        }[grant.tool]
        reasons: list[str] = []
        if type(parameters) is not expected_parameter_type:
            reasons.append("TOOL_PARAMETER_MISMATCH")
        if identity.principal_id != grant.principal_id or identity.role is not grant.role:
            reasons.append("IDENTITY_MISMATCH")
        if (
            attempt.authorization_id != grant.authorization_id
            or attempt.case_id != grant.case_id
            or attempt.trace_id != grant.trace_id
            or attempt.tool is not grant.tool
        ):
            reasons.append("ATTEMPT_GRANT_CONTEXT_MISMATCH")
        if parameter_data != grant.complete_parameters:
            reasons.append("PARAMETERS_MISMATCH")
        if attempt.canonical_parameters != parameter_data:
            reasons.append("ATTEMPT_PARAMETERS_MISMATCH")
        if admitted_digest != grant.evidence_digest:
            reasons.append("EVIDENCE_DIGEST_MISMATCH")
        if recomputed_action != grant.action_digest:
            reasons.append("ACTION_DIGEST_MISMATCH")
        if not self.signer.verify(unsigned_grant_payload(grant), grant.signature):
            reasons.append("SIGNATURE_INVALID")
        return tuple(reasons)
