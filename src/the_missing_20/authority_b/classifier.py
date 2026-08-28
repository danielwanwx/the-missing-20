"""Deterministic operational classification and policy.

This module intentionally imports no advisory contract.  Its only inputs are the
detector's admitted evidence, case identity, source availability, and explicit
invariant observations.  That import boundary is part of the Authority B safety
proof: model output cannot become an operational fact by accident.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from threading import Lock
from typing import Any

from the_missing_20.authority_b.models import (
    REQUIRED_AUTHORITY_ROLES,
    OperationalClassification,
    OperationalDecision,
    OperationalEligibility,
    OperationalInvariant,
    canonical_json,
    evidence_content_digest,
)
from the_missing_20.domain.enterprise import EvidenceReadStatus
from the_missing_20.domain.models import (
    ActionTool,
    Case,
    EvidenceItem,
    EvidenceSourceType,
)
from the_missing_20.domain.states import CaseStatus

REQUIRED_AUTHORITATIVE_SOURCES: tuple[EvidenceSourceType, ...] = (
    EvidenceSourceType.FAILED_MESSAGE_QUEUE,
    EvidenceSourceType.ERP_RECEIPT,
    EvidenceSourceType.MATERIAL_DOCUMENT,
    EvidenceSourceType.WAREHOUSE,
    EvidenceSourceType.INVOICE,
)


def latest_authoritative_evidence(
    evidence: tuple[EvidenceItem, ...] | list[EvidenceItem],
) -> tuple[EvidenceItem, ...]:
    """Return one deterministic fresh-read record per authoritative source.

    A lifecycle can contain the initial detector read and later authoritative rereads.
    The classifier never treats that history as duplicate current state: it selects the
    newest observed record for each source, with the evidence ID as a deterministic tie
    breaker.  Callers still retain the complete append-only evidence history for audit.
    """

    latest: dict[EvidenceSourceType, EvidenceItem] = {}
    for item in evidence:
        if item.source_type not in REQUIRED_AUTHORITATIVE_SOURCES:
            continue
        previous = latest.get(item.source_type)
        if previous is None or (item.observed_at, item.evidence_id) > (
            previous.observed_at,
            previous.evidence_id,
        ):
            latest[item.source_type] = item
    return tuple(latest[source] for source in sorted(latest, key=lambda value: value.value))


@dataclass(frozen=True, slots=True)
class OperationalPolicyResult:
    """A deterministic policy projection; it carries no advisory fields."""

    decision_digest: str
    eligibility: OperationalEligibility
    allowed_action: ActionTool | None
    reason_codes: tuple[str, ...]
    required_approval_roles: tuple[Any, ...] = REQUIRED_AUTHORITY_ROLES

    @property
    def action_allowed(self) -> bool:
        return self.eligibility is OperationalEligibility.PENDING_APPROVAL


class OperationalDecisionConflict(RuntimeError):
    """The same case version was assigned two different deterministic decisions."""


class DeterministicDecisionLedger:
    """Small append-only in-memory ledger for one immutable decision per case version."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._decisions: dict[tuple[str, int], OperationalDecision] = {}

    def put(self, decision: OperationalDecision) -> OperationalDecision:
        key = (decision.case_id, decision.case_version)
        with self._lock:
            existing = self._decisions.get(key)
            if existing is not None and existing.decision_digest != decision.decision_digest:
                raise OperationalDecisionConflict(
                    "case version already has a different operational decision"
                )
            if existing is not None:
                return existing
            self._decisions[key] = decision
            return decision

    def get(self, case_id: str, case_version: int) -> OperationalDecision | None:
        with self._lock:
            return self._decisions.get((case_id, case_version))

    def snapshot(self) -> tuple[OperationalDecision, ...]:
        with self._lock:
            return tuple(
                self._decisions[key]
                for key in sorted(self._decisions, key=lambda item: (item[0], item[1]))
            )


def _canonical_digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _normalise_source_statuses(
    source_availability: object | None,
    evidence: tuple[EvidenceItem, ...],
) -> dict[EvidenceSourceType, EvidenceReadStatus]:
    """Accept detector status records without importing an advisory schema."""

    if source_availability is None:
        present = {item.source_type for item in evidence}
        return {
            source: (
                EvidenceReadStatus.AVAILABLE
                if source in present
                else EvidenceReadStatus.UNAVAILABLE
            )
            for source in REQUIRED_AUTHORITATIVE_SOURCES
        }
    if isinstance(source_availability, Mapping):
        result: dict[EvidenceSourceType, EvidenceReadStatus] = {}
        for key, value in source_availability.items():
            try:
                source = key if isinstance(key, EvidenceSourceType) else EvidenceSourceType(key)
                status = (
                    value if isinstance(value, EvidenceReadStatus) else EvidenceReadStatus(value)
                )
            except (TypeError, ValueError) as exc:
                raise ValueError("source availability contains an unsupported value") from exc
            result[source] = status
        return result
    sources = getattr(source_availability, "sources", None)
    if sources is None:
        raise ValueError("source availability must be a mapping or source record")
    result = {}
    for record in sources:
        try:
            source_value = record.source_type
            status_value = record.status
            source = (
                source_value
                if isinstance(source_value, EvidenceSourceType)
                else EvidenceSourceType(source_value)
            )
            status = (
                status_value
                if isinstance(status_value, EvidenceReadStatus)
                else EvidenceReadStatus(status_value)
            )
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError("source availability record is malformed") from exc
        result[source] = status
    return result


def _identity_and_integrity(
    evidence: tuple[EvidenceItem, ...],
    *,
    case_id: str,
    trace_id: str,
) -> tuple[tuple[str, ...], tuple[OperationalInvariant, ...]]:
    ids = tuple(sorted(item.evidence_id for item in evidence))
    invariants: list[OperationalInvariant] = []
    invariants.append(
        OperationalInvariant(
            name="evidence_identity",
            passed=all(item.case_id == case_id and item.trace_id == trace_id for item in evidence)
            and len(ids) == len(set(ids)),
        )
    )
    invariants.append(
        OperationalInvariant(
            name="evidence_integrity",
            passed=all(item.content_digest == evidence_content_digest(item) for item in evidence),
        )
    )
    return ids, tuple(invariants)


def _source_digest(
    evidence: tuple[EvidenceItem, ...],
    statuses: Mapping[EvidenceSourceType, EvidenceReadStatus],
) -> str:
    return _canonical_digest(
        {
            "evidence": [
                {
                    "evidence_id": item.evidence_id,
                    "source_type": item.source_type.value,
                    "source_record_id": item.source_record_id,
                    "content_digest": item.content_digest,
                }
                for item in sorted(evidence, key=lambda value: value.evidence_id)
            ],
            "source_availability": {
                source.value: statuses.get(source, EvidenceReadStatus.UNAVAILABLE).value
                for source in sorted(REQUIRED_AUTHORITATIVE_SOURCES, key=lambda value: value.value)
            },
        }
    )


def _decision(
    *,
    decision_id: str,
    case_id: str,
    trace_id: str,
    case_version: int,
    classification: OperationalClassification,
    eligibility: OperationalEligibility,
    allowed_action: ActionTool | None,
    reason_codes: Iterable[str],
    evidence: tuple[EvidenceItem, ...],
    statuses: Mapping[EvidenceSourceType, EvidenceReadStatus],
    invariants: tuple[OperationalInvariant, ...],
) -> OperationalDecision:
    return OperationalDecision(
        decision_id=decision_id,
        case_id=case_id,
        trace_id=trace_id,
        case_version=case_version,
        classification=classification,
        eligibility=eligibility,
        allowed_action=allowed_action,
        reason_codes=tuple(sorted(set(reason_codes))),
        authoritative_evidence_ids=tuple(sorted(item.evidence_id for item in evidence)),
        authoritative_source_types=tuple(
            sorted(
                {
                    item.source_type
                    for item in evidence
                    if item.source_type in REQUIRED_AUTHORITATIVE_SOURCES
                },
                key=lambda value: value.value,
            )
        ),
        source_digest=_source_digest(evidence, statuses),
        invariants=invariants,
    )


def classify_operational_state(
    evidence: tuple[EvidenceItem, ...] | list[EvidenceItem],
    *,
    case: Case | None = None,
    case_id: str | None = None,
    trace_id: str | None = None,
    case_version: int | None = None,
    source_availability: object | None = None,
    invariants: Mapping[str, bool] | None = None,
    decision_id: str | None = None,
    ledger: DeterministicDecisionLedger | None = None,
) -> OperationalDecision:
    """Classify a synthetic case using detector-owned evidence only.

    The function accepts no model/advisory value.  Missing source, identity, integrity,
    or relation-independent invariant failures fail closed to ``REQUIRE_EVIDENCE`` or
    ``NO_ACTION``.  A valid retryable message is the only profile eligible for a
    controlled restart.
    """

    records = tuple(evidence)
    resolved_case_id = case.case_id if case is not None else case_id
    resolved_trace_id = case_id if False else trace_id  # keep the branch explicit for mypy
    if case is not None:
        resolved_trace_id = resolved_trace_id or ""
        resolved_case_version = case.case_version
        resolved_case_id = case.case_id
    else:
        resolved_case_version = 0 if case_version is None else case_version
    if not resolved_case_id or not resolved_trace_id:
        raise ValueError("case_id and trace_id are required for deterministic classification")
    statuses = _normalise_source_statuses(source_availability, records)
    evidence_ids, base_invariants = _identity_and_integrity(
        records, case_id=resolved_case_id, trace_id=resolved_trace_id
    )
    by_source = {item.source_type: item for item in records}
    required_set = set(REQUIRED_AUTHORITATIVE_SOURCES)
    available_set = {
        source
        for source in REQUIRED_AUTHORITATIVE_SOURCES
        if statuses.get(source) is EvidenceReadStatus.AVAILABLE
    }
    missing_sources = tuple(sorted((required_set - available_set), key=lambda value: value.value))
    extra_or_duplicate_sources = len(by_source) != len(records) or not set(by_source).issubset(
        required_set
    )
    identity_or_integrity_failed = not all(item.passed for item in base_invariants)
    custom_failed = tuple(sorted(name for name, passed in (invariants or {}).items() if not passed))
    all_invariants = base_invariants + tuple(
        OperationalInvariant(name=name, passed=bool(passed))
        for name, passed in sorted((invariants or {}).items())
    )
    if missing_sources or extra_or_duplicate_sources or identity_or_integrity_failed:
        reasons = ["REQUIRED_AUTHORITATIVE_SOURCE_MISSING"] if missing_sources else []
        if extra_or_duplicate_sources:
            reasons.append("SOURCE_CATALOG_INVALID")
        if not base_invariants[0].passed:
            reasons.append("EVIDENCE_IDENTITY_INVALID")
        if not base_invariants[1].passed:
            reasons.append("EVIDENCE_INTEGRITY_INVALID")
        reasons.extend(custom_failed)
        result = _decision(
            decision_id=decision_id or f"decision:{resolved_case_id}:{resolved_case_version}",
            case_id=resolved_case_id,
            trace_id=resolved_trace_id,
            case_version=resolved_case_version,
            classification=OperationalClassification.REQUIRE_EVIDENCE,
            eligibility=OperationalEligibility.REQUIRE_EVIDENCE,
            allowed_action=None,
            reason_codes=reasons or ["AUTHORITATIVE_INPUT_INVALID"],
            evidence=records,
            statuses=statuses,
            invariants=all_invariants,
        )
        return ledger.put(result) if ledger is not None else result

    queue = by_source[EvidenceSourceType.FAILED_MESSAGE_QUEUE].admitted_fields
    material = by_source[EvidenceSourceType.MATERIAL_DOCUMENT].admitted_fields
    warehouse = by_source[EvidenceSourceType.WAREHOUSE].admitted_fields
    erp = by_source[EvidenceSourceType.ERP_RECEIPT].admitted_fields
    invoice = by_source[EvidenceSourceType.INVOICE].admitted_fields
    warehouse_quantity = warehouse.get("quantity")
    erp_quantity = erp.get("quantity")
    invoice_quantity = invoice.get("quantity")

    # Once the receipt-restart effect is verified, the next controlled action is a
    # separate deterministic invoice release decision.  This branch is intentionally
    # case-state/evidence only; advisory output is not an input and cannot make an
    # invoice eligible.
    if case is not None and case.status is CaseStatus.RECEIPT_VERIFIED:
        invoice_ready_failures: list[str] = []
        if queue.get("status") != "CONSUMED":
            invoice_ready_failures.append("RECEIPT_MESSAGE_NOT_CONSUMED")
        documents = material.get("material_documents")
        if not isinstance(documents, list) or len(documents) != 1:
            invoice_ready_failures.append("RECEIPT_MATERIAL_DOCUMENT_NOT_EXACTLY_ONE")
        if erp_quantity != warehouse_quantity:
            invoice_ready_failures.append("RECEIPT_QUANTITY_NOT_COMPLETE")
        if invoice.get("state") != "HELD":
            invoice_ready_failures.append("INVOICE_NOT_HELD")
        if invoice.get("hold_reason") != "RECEIPT_MISMATCH":
            invoice_ready_failures.append("INVOICE_HOLD_NOT_RECEIPT_MISMATCH")
        if invoice.get("other_blocking_holds") != []:
            invoice_ready_failures.append("OTHER_INVOICE_HOLDS_PRESENT")
        if invoice_ready_failures:
            classification = OperationalClassification.INVOICE_RELEASE_READY
            eligibility = OperationalEligibility.NO_ACTION
            action = None
            reasons = ["DETERMINISTIC_INVARIANT_FAILED", *invoice_ready_failures]
        else:
            classification = OperationalClassification.INVOICE_RELEASE_READY
            eligibility = OperationalEligibility.PENDING_APPROVAL
            action = ActionTool.RELEASE_INVOICE
            reasons = ["RECEIPT_VERIFIED", "TWO_ROLE_APPROVAL_REQUIRED"]
    elif queue.get("status") == "CONSUMED" and material.get("material_documents"):
        classification = OperationalClassification.RECEIPT_ALREADY_POSTED
        eligibility = OperationalEligibility.NO_ACTION
        action = None
        reasons = ["RECEIPT_ALREADY_POSTED"]
    elif (
        isinstance(warehouse_quantity, int)
        and not isinstance(warehouse_quantity, bool)
        and warehouse_quantity == erp_quantity
        and isinstance(invoice_quantity, int)
        and not isinstance(invoice_quantity, bool)
        and warehouse_quantity < invoice_quantity
    ):
        classification = OperationalClassification.GENUINE_SHORT_SHIPMENT
        eligibility = OperationalEligibility.NO_ACTION
        action = None
        reasons = ["PHYSICAL_QUANTITY_BELOW_ORDERED_QUANTITY"]
    else:
        failures: list[str] = []
        if queue.get("status") != "FAILED":
            failures.append("MESSAGE_NOT_FAILED")
        if queue.get("error_code") != "DOCUMENT_LOCKED_RETRYABLE":
            failures.append("FAILURE_NOT_RETRYABLE_DOCUMENT_LOCK")
        if queue.get("retry_eligible") is not True:
            failures.append("MESSAGE_NOT_RETRY_ELIGIBLE")
        if queue.get("lock_cleared") is not True:
            failures.append("DOCUMENT_LOCK_NOT_CLEARED")
        if material.get("material_documents") != []:
            failures.append("SOURCE_MATERIAL_DOCUMENT_ALREADY_EXISTS")
        message_quantity = queue.get("quantity")
        if (
            not isinstance(warehouse_quantity, int)
            or isinstance(warehouse_quantity, bool)
            or not isinstance(erp_quantity, int)
            or isinstance(erp_quantity, bool)
            or not isinstance(message_quantity, int)
            or isinstance(message_quantity, bool)
            or warehouse_quantity - erp_quantity != message_quantity
            or message_quantity <= 0
        ):
            failures.append("MESSAGE_QUANTITY_DOES_NOT_CLOSE_DISCREPANCY")
        failures.extend(custom_failed)
        classification = OperationalClassification.RETRYABLE_MESSAGE
        if failures:
            eligibility = OperationalEligibility.NO_ACTION
            action = None
            reasons = ["DETERMINISTIC_INVARIANT_FAILED", *failures]
        else:
            eligibility = OperationalEligibility.PENDING_APPROVAL
            action = ActionTool.RESTART_RECEIPT_MESSAGE
            reasons = ["RETRYABLE_MESSAGE", "TWO_ROLE_APPROVAL_REQUIRED"]

    result = _decision(
        decision_id=decision_id or f"decision:{resolved_case_id}:{resolved_case_version}",
        case_id=resolved_case_id,
        trace_id=resolved_trace_id,
        case_version=resolved_case_version,
        classification=classification,
        eligibility=eligibility,
        allowed_action=action,
        reason_codes=reasons,
        evidence=records,
        statuses=statuses,
        invariants=all_invariants,
    )
    return ledger.put(result) if ledger is not None else result


def evaluate_operational_policy(decision: OperationalDecision) -> OperationalPolicyResult:
    """Re-evaluate deterministic eligibility from one operational decision."""

    failed = tuple(sorted(item.name for item in decision.invariants if not item.passed))
    reasons = list(decision.reason_codes)
    if failed:
        return OperationalPolicyResult(
            decision_digest=decision.decision_digest,
            eligibility=OperationalEligibility.NO_ACTION,
            allowed_action=None,
            reason_codes=tuple(sorted(set((*reasons, "INVARIANT_FAILED", *failed)))),
        )
    if decision.eligibility is not OperationalEligibility.PENDING_APPROVAL:
        return OperationalPolicyResult(
            decision_digest=decision.decision_digest,
            eligibility=decision.eligibility,
            allowed_action=None,
            reason_codes=tuple(reasons),
        )
    if decision.allowed_action is None:
        return OperationalPolicyResult(
            decision_digest=decision.decision_digest,
            eligibility=OperationalEligibility.NO_ACTION,
            allowed_action=None,
            reason_codes=tuple(sorted(set((*reasons, "ACTION_MISSING")))),
        )
    return OperationalPolicyResult(
        decision_digest=decision.decision_digest,
        eligibility=OperationalEligibility.PENDING_APPROVAL,
        allowed_action=decision.allowed_action,
        reason_codes=tuple(reasons),
    )


__all__ = [
    "DeterministicDecisionLedger",
    "OperationalDecisionConflict",
    "OperationalPolicyResult",
    "REQUIRED_AUTHORITATIVE_SOURCES",
    "classify_operational_state",
    "evaluate_operational_policy",
    "latest_authoritative_evidence",
]
