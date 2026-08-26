"""Typed transition commands and append-only audit events."""

from __future__ import annotations

from typing import Annotated

from pydantic import AwareDatetime, Field, model_validator

from the_missing_20.domain.models import (
    ClosureFacts,
    ContractModel,
    EvaluationResult,
    EvidenceItem,
    HypothesisResult,
    NonEmptyStr,
)
from the_missing_20.domain.states import CaseStatus, TransitionEvent

NonNegativeInt = Annotated[int, Field(ge=0)]


class TransitionCommand(ContractModel):
    case_id: NonEmptyStr
    expected_version: NonNegativeInt
    event: TransitionEvent
    idempotency_key: NonEmptyStr
    trace_id: NonEmptyStr
    occurred_at: AwareDatetime
    evidence: EvidenceItem | None = None
    closure_facts: ClosureFacts | None = None
    hypothesis: HypothesisResult | None = None
    evaluation: EvaluationResult | None = None

    @model_validator(mode="after")
    def payload_matches_event(self) -> TransitionCommand:
        if self.event is TransitionEvent.EVIDENCE_ADMITTED:
            if (
                self.evidence is None
                or self.closure_facts is not None
                or self.hypothesis is not None
                or self.evaluation is not None
            ):
                raise ValueError("EVIDENCE_ADMITTED requires only typed evidence")
        elif self.event is TransitionEvent.RECEIPT_RESTART_RECOMMENDED:
            if (
                self.hypothesis is None
                or self.evaluation is None
                or self.evidence is not None
                or self.closure_facts is not None
            ):
                raise ValueError("RECEIPT_RESTART_RECOMMENDED requires hypothesis and evaluation")
        elif self.event is TransitionEvent.INVOICE_POSTCONDITIONS_VERIFIED:
            if (
                self.closure_facts is None
                or self.evidence is not None
                or self.hypothesis is not None
                or self.evaluation is not None
            ):
                raise ValueError("INVOICE_POSTCONDITIONS_VERIFIED requires only closure_facts")
        elif any(
            value is not None
            for value in (self.evidence, self.closure_facts, self.hypothesis, self.evaluation)
        ):
            raise ValueError("this transition event does not accept a payload")
        return self


class CaseEvent(ContractModel):
    event_id: NonEmptyStr
    case_id: NonEmptyStr
    event: TransitionEvent
    prior_status: CaseStatus
    new_status: CaseStatus
    prior_version: NonNegativeInt
    new_version: NonNegativeInt
    idempotency_key: NonEmptyStr
    trace_id: NonEmptyStr
    occurred_at: AwareDatetime
    payload_json: str
    payload_digest: NonEmptyStr

    @model_validator(mode="after")
    def version_advances_once(self) -> CaseEvent:
        if self.new_version != self.prior_version + 1:
            raise ValueError("case events must advance the version exactly once")
        return self
