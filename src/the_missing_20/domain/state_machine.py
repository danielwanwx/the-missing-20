"""Pure deterministic state transition engine."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from the_missing_20.domain.errors import (
    InvalidEventPayload,
    InvalidTransition,
    VersionConflict,
)
from the_missing_20.domain.events import CaseEvent, TransitionCommand
from the_missing_20.domain.models import Case
from the_missing_20.domain.states import TRANSITIONS, TransitionEvent


def _payload(command: TransitionCommand) -> dict[str, Any]:
    if command.evidence is not None:
        return {"evidence": command.evidence.model_dump(mode="json")}
    if command.closure_facts is not None:
        return {"closure_facts": command.closure_facts.model_dump(mode="json")}
    if command.hypothesis is not None and command.evaluation is not None:
        return {
            "hypothesis": command.hypothesis.model_dump(mode="json"),
            "evaluation": command.evaluation.model_dump(mode="json"),
        }
    return {}


def _digest(payload: dict[str, Any]) -> str:
    encoded = _canonical_json(payload).encode()
    return hashlib.sha256(encoded).hexdigest()


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def advance_case(case: Case, command: TransitionCommand) -> tuple[Case, CaseEvent]:
    """Apply one approved lifecycle event without performing persistence or I/O."""

    if command.case_id != case.case_id:
        raise InvalidEventPayload("command case_id does not match the current case")
    if command.expected_version != case.case_version:
        raise VersionConflict(
            f"expected case version {command.expected_version}, found {case.case_version}"
        )
    if command.occurred_at < case.updated_at:
        raise InvalidEventPayload("event time cannot precede the current case update")

    try:
        next_status = TRANSITIONS[(case.status, command.event)]
    except KeyError as exc:
        raise InvalidTransition(
            f"{command.event.value} cannot advance a case from {case.status.value}"
        ) from exc

    if command.event is TransitionEvent.EVIDENCE_ADMITTED and (
        command.evidence is None or command.evidence.case_id != case.case_id
    ):
        raise InvalidEventPayload("admitted evidence must match the current case")
    if command.event is TransitionEvent.INVOICE_POSTCONDITIONS_VERIFIED and (
        command.closure_facts is None or not command.closure_facts.satisfies_closure()
    ):
        raise InvalidEventPayload("verified closure facts do not satisfy all invariants")
    if (
        command.event is TransitionEvent.INVOICE_POSTCONDITIONS_VERIFIED
        and command.closure_facts is not None
        and command.closure_facts.expected_receipt_quantity != case.discrepancy.expected_quantity
    ):
        raise InvalidEventPayload("closure quantity does not match the case discrepancy")

    payload = _payload(command)
    payload_json = _canonical_json(payload)
    payload_digest = _digest(payload)
    new_version = case.case_version + 1
    event_identity = ":".join(
        (
            case.case_id,
            str(case.case_version),
            command.event.value,
            command.idempotency_key,
            payload_digest,
        )
    )
    event_id = f"evt_{hashlib.sha256(event_identity.encode()).hexdigest()[:32]}"
    evidence_revision = case.current_evidence_revision
    if command.event is TransitionEvent.EVIDENCE_ADMITTED:
        evidence_revision += 1

    updated_case = case.model_copy(
        update={
            "case_version": new_version,
            "status": next_status,
            "current_evidence_revision": evidence_revision,
            "updated_at": command.occurred_at,
        }
    )
    event = CaseEvent(
        event_id=event_id,
        case_id=case.case_id,
        event=command.event,
        prior_status=case.status,
        new_status=next_status,
        prior_version=case.case_version,
        new_version=new_version,
        idempotency_key=command.idempotency_key,
        trace_id=command.trace_id,
        occurred_at=command.occurred_at,
        payload_json=payload_json,
        payload_digest=payload_digest,
    )
    return updated_case, event
