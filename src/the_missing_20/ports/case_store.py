"""Port for the versioned case ledger and execution audit records."""

from __future__ import annotations

from typing import Protocol

from the_missing_20.authority_b.models import QuorumActionGrant
from the_missing_20.domain.events import CaseEvent, TransitionCommand
from the_missing_20.domain.execution import (
    DetectionGenesis,
    ExecutionAttempt,
    GrantStatus,
    PolicyDecision,
)
from the_missing_20.domain.models import (
    ActionGrant,
    Approval,
    Case,
    EvidenceItem,
    ExecutionReceipt,
)


class CaseStore(Protocol):
    def create_case(self, case: Case, genesis: DetectionGenesis) -> None: ...

    def create_detected_case(
        self,
        case: Case,
        genesis: DetectionGenesis,
        evidence: tuple[EvidenceItem, ...],
        transition: TransitionCommand,
    ) -> tuple[Case, CaseEvent]: ...

    def get_case(self, case_id: str) -> Case: ...

    def apply_transition(self, command: TransitionCommand) -> tuple[Case, CaseEvent]: ...

    def replay_case(self, case_id: str) -> Case: ...

    def add_evidence(self, evidence: EvidenceItem) -> None: ...

    def admit_evidence_with_transition(
        self, evidence: EvidenceItem, transition: TransitionCommand
    ) -> tuple[Case, CaseEvent]: ...

    def list_evidence(self, case_id: str) -> tuple[EvidenceItem, ...]: ...

    def save_approval_and_grant(
        self,
        approval: Approval,
        grant: ActionGrant,
        transition: TransitionCommand,
    ) -> tuple[Case, CaseEvent]: ...

    def save_policy_decision(self, decision: PolicyDecision) -> None: ...

    def list_policy_decisions(self, case_id: str) -> tuple[PolicyDecision, ...]: ...

    def get_grant(self, authorization_id: str) -> tuple[ActionGrant, GrantStatus]: ...

    def get_grant_status(self, authorization_id: str) -> GrantStatus: ...

    def save_attempt(self, attempt: ExecutionAttempt) -> None: ...

    def get_attempt(self, execution_id: str) -> ExecutionAttempt | None: ...

    def save_receipt(self, receipt: ExecutionReceipt) -> None: ...

    def reserve_attempt(
        self,
        *,
        attempt: ExecutionAttempt,
        decision: PolicyDecision,
        transition: TransitionCommand,
    ) -> tuple[Case, CaseEvent, ExecutionAttempt]: ...

    def complete_attempt(
        self,
        *,
        receipt: ExecutionReceipt,
        completed_attempt: ExecutionAttempt,
        transition: TransitionCommand | None,
    ) -> tuple[Case, CaseEvent | None]: ...

    def list_events(self, case_id: str) -> tuple[CaseEvent, ...]: ...

    def list_approvals(self, case_id: str) -> tuple[Approval, ...]: ...

    def list_receipts(self, case_id: str) -> tuple[ExecutionReceipt, ...]: ...

    def list_grants(self, case_id: str) -> tuple[ActionGrant, ...]: ...

    def list_attempts(self, case_id: str) -> tuple[ExecutionAttempt, ...]: ...

    def get_genesis(self, case_id: str) -> DetectionGenesis: ...

    def get_authority_b_binding(
        self, intent_id: str
    ) -> tuple[QuorumActionGrant, ActionGrant] | None: ...

    def bind_and_reserve_authority_b_attempt(
        self,
        *,
        grant: QuorumActionGrant,
        bridge_grant: ActionGrant,
        preparation_transitions: tuple[TransitionCommand, ...],
        attempt: ExecutionAttempt,
        decision: PolicyDecision,
        execution_transition: TransitionCommand,
    ) -> tuple[ActionGrant, bool]: ...
