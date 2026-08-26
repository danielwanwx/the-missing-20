"""Case orchestration that exposes named, versioned lifecycle commands."""

from __future__ import annotations

from the_missing_20.domain.errors import InvalidEventPayload
from the_missing_20.domain.events import CaseEvent, TransitionCommand
from the_missing_20.domain.models import (
    ActionTool,
    Case,
    EvaluationDecision,
    EvaluationResult,
    EvidenceSourceType,
    HypothesisConclusion,
    HypothesisResult,
    HypothesisType,
)
from the_missing_20.domain.states import TransitionEvent
from the_missing_20.ports.case_store import CaseStore
from the_missing_20.ports.clock import Clock


class CaseService:
    def __init__(self, store: CaseStore, clock: Clock) -> None:
        self.store = store
        self.clock = clock

    def request_receipt_approval(
        self,
        *,
        case_id: str,
        expected_version: int,
        idempotency_key: str,
    ) -> tuple[Case, CaseEvent]:
        trace_id = self.store.get_genesis(case_id).trace_id
        return self.store.apply_transition(
            TransitionCommand(
                case_id=case_id,
                expected_version=expected_version,
                event=TransitionEvent.RECEIPT_APPROVAL_REQUESTED,
                idempotency_key=idempotency_key,
                trace_id=trace_id,
                occurred_at=self.clock.now(),
            )
        )

    def request_invoice_approval(
        self,
        *,
        case_id: str,
        expected_version: int,
        idempotency_key: str,
    ) -> tuple[Case, CaseEvent]:
        trace_id = self.store.get_genesis(case_id).trace_id
        return self.store.apply_transition(
            TransitionCommand(
                case_id=case_id,
                expected_version=expected_version,
                event=TransitionEvent.INVOICE_APPROVAL_REQUESTED,
                idempotency_key=idempotency_key,
                trace_id=trace_id,
                occurred_at=self.clock.now(),
            )
        )

    def recommend_receipt_restart(
        self,
        *,
        case_id: str,
        expected_version: int,
        idempotency_key: str,
        hypothesis: HypothesisResult,
        evaluation: EvaluationResult,
    ) -> tuple[Case, CaseEvent]:
        trace_id = self.store.get_genesis(case_id).trace_id
        admitted = self.store.list_evidence(case_id)
        admitted_ids = {item.evidence_id for item in admitted}
        validated_ids = set(evaluation.validated_evidence_ids)
        supporting_ids = set(hypothesis.supporting_evidence_ids)
        supporting_source_types = {
            item.source_type for item in admitted if item.evidence_id in supporting_ids
        }
        required_source_types = {
            EvidenceSourceType.FAILED_MESSAGE_QUEUE,
            EvidenceSourceType.ERP_RECEIPT,
            EvidenceSourceType.MATERIAL_DOCUMENT,
            EvidenceSourceType.WAREHOUSE,
        }
        if not (
            hypothesis.hypothesis_type is HypothesisType.RETRYABLE_MESSAGE
            and hypothesis.conclusion is HypothesisConclusion.SUPPORTED
            and evaluation.decision is EvaluationDecision.ACCEPT
            and evaluation.allowed_next_action is ActionTool.RESTART_RECEIPT_MESSAGE
            and not evaluation.failed_invariants
            and evaluation.trace_id == trace_id
            and validated_ids == admitted_ids
            and supporting_ids
            and supporting_ids.issubset(admitted_ids)
            and required_source_types.issubset(supporting_source_types)
            and not hypothesis.missing_evidence
            and not hypothesis.contradicting_evidence_ids
        ):
            raise InvalidEventPayload(
                "only an evidence-complete accepted diagnosis can recommend receipt restart"
            )
        return self.store.apply_transition(
            TransitionCommand(
                case_id=case_id,
                expected_version=expected_version,
                event=TransitionEvent.RECEIPT_RESTART_RECOMMENDED,
                idempotency_key=idempotency_key,
                trace_id=trace_id,
                occurred_at=self.clock.now(),
                hypothesis=hypothesis,
                evaluation=evaluation,
            )
        )
