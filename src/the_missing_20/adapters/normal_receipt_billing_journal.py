"""Durable, offline fences for one normal-receipt billing intent.

This module deliberately owns only the journal boundary.  It does not call an
ERP, make an HTTP request, authenticate a manager, or assert that a provider
effect happened.  A later trusted transport can take an :class:`AttemptClaim`
after its marker has committed, perform one external operation outside any
SQLite transaction, and return structured readback evidence for admission.
"""

from __future__ import annotations

import hashlib
import json
import math
import secrets
import sqlite3
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, cast

from the_missing_20.adapters.normal_receipt_billing_native_request import (
    NativeDraftAcknowledgement,
    NativeInsertRequest,
    NativeSubmitRequest,
    NativeSubmittedReadback,
)
from the_missing_20.adapters.normal_receipt_billing_preview import (
    BillingPreview,
    SyntheticBillingBasis,
)

ACTION_NORMAL_RECEIPT_BILLING = "NORMAL_RECEIPT_BILLING"

Phase = Literal[
    "PREPARED",
    "APPROVED",
    "INSERT_ATTEMPTED",
    "DRAFT_READBACK_ADMITTED",
    "SUBMIT_ATTEMPTED",
    "SUBMITTED_READBACK_ADMITTED",
]
AuthorityStatus = Literal[
    "PENDING_APPROVAL",
    "APPROVED",
    "REFUSED",
    "STALE_SOURCE",
    "CONFLICT_HOLD",
    "EXPIRED",
]
AttemptKind = Literal["INSERT", "SUBMIT"]


class _AdmissionError(ValueError):
    """A deterministic envelope-admission failure."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} is required")
    return value.strip()


def _canonical(value: object) -> object:
    """Return JSON-safe immutable-source material or reject it deterministically."""

    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        for key, item in sorted(value.items(), key=lambda pair: str(pair[0])):
            if not isinstance(key, str):
                raise ValueError("mapping keys must be strings")
            result[key] = _canonical(item)
        return result
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite values are not admissible")
        return value
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    raise ValueError(f"unsupported immutable record value: {type(value).__name__}")


def _mapping(value: Mapping[str, object], label: str) -> dict[str, object]:
    try:
        result = _canonical(value)
    except ValueError as error:
        raise ValueError(f"{label}: {error}") from None
    if not isinstance(result, dict):
        raise ValueError(f"{label} must be a mapping")
    return result


def _encoded(value: object) -> str:
    return json.dumps(_canonical(value), sort_keys=True, separators=(",", ":"), allow_nan=False)


def _decoded_mapping(value: str, label: str) -> dict[str, object]:
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError as error:  # pragma: no cover - corrupt local database only
        raise RuntimeError(f"corrupt normal-billing {label}") from error
    if not isinstance(decoded, dict):  # pragma: no cover - corrupt local database only
        raise RuntimeError(f"corrupt normal-billing {label}")
    return cast(dict[str, object], _canonical(decoded))


def _frozen(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _frozen(item) for key, item in value.items()})
    if isinstance(value, list | tuple):
        return tuple(_frozen(item) for item in value)
    return value


def _frozen_mapping(value: Mapping[str, object]) -> Mapping[str, Any]:
    return cast(Mapping[str, Any], _frozen(value))


def _digest(value: object) -> str:
    return hashlib.sha256(_encoded(value).encode("utf-8")).hexdigest()


def _key(*parts: str) -> str:
    return _digest({"identity": list(parts)})


def _time(now: datetime | None) -> str:
    value = now or datetime.now(UTC)
    if value.tzinfo is None:
        raise ValueError("journal timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat()


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:  # pragma: no cover - journal always writes aware timestamps
        raise RuntimeError("corrupt normal-billing timestamp")
    return parsed.astimezone(UTC)


def _sqlite_true(value: object) -> bool:
    """Decode only the integer representation written by this journal's SQLite schema."""

    return type(value) is int and value == 1


@dataclass(frozen=True, slots=True)
class CommercialSource:
    """A compact source fingerprint separate from volatile audit observation data.

    ``identity``, ``revisions`` and ``decisive_values`` form the commercial
    fingerprint.  ``audit_snapshot_digest`` and ``observed_at`` are retained
    for audit freshness only and never form an idempotency or approval key.
    """

    identity: Mapping[str, object]
    revisions: Mapping[str, object]
    decisive_values: Mapping[str, object]
    audit_snapshot_digest: str
    observed_at: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "identity", _frozen_mapping(_mapping(self.identity, "identity")))
        object.__setattr__(
            self, "revisions", _frozen_mapping(_mapping(self.revisions, "revisions"))
        )
        object.__setattr__(
            self,
            "decisive_values",
            _frozen_mapping(_mapping(self.decisive_values, "decisive values")),
        )
        object.__setattr__(
            self,
            "audit_snapshot_digest",
            _text(self.audit_snapshot_digest, "audit snapshot digest"),
        )
        object.__setattr__(self, "observed_at", _text(self.observed_at, "observed_at"))

    def commercial_record(self) -> dict[str, object]:
        return {
            "identity": _canonical(self.identity),
            "revisions": _canonical(self.revisions),
            "decisive_values": _canonical(self.decisive_values),
        }

    def record(self) -> dict[str, object]:
        return {
            **self.commercial_record(),
            "audit_snapshot_digest": self.audit_snapshot_digest,
            "observed_at": self.observed_at,
        }


@dataclass(frozen=True, slots=True)
class ExactDraftReadback:
    """Structured adapter testimony for one exact draft readback.

    The journal checks this proof against its original frozen envelope.  The
    proof is not a generic ``verified`` boolean and does not establish provider
    truth by itself.
    """

    draft_name: str
    company: str
    supplier: str
    bill_reference: str
    purchase_receipt: str
    purchase_receipt_item: str
    bill_digest: str
    commercial_version: str
    candidate_count: int
    lookup_complete: bool
    audit_snapshot_digest: str
    observed_at: str

    def __post_init__(self) -> None:
        _validate_exact_readback(self)

    def record(self) -> dict[str, object]:
        return _exact_readback_record(self)


def _validate_exact_readback(proof: ExactDraftReadback) -> None:
    for field_name in (
        "draft_name",
        "company",
        "supplier",
        "bill_reference",
        "purchase_receipt",
        "purchase_receipt_item",
        "bill_digest",
        "commercial_version",
        "audit_snapshot_digest",
        "observed_at",
    ):
        object.__setattr__(proof, field_name, _text(getattr(proof, field_name), field_name))
    if type(proof.candidate_count) is not int or proof.candidate_count < 0:
        raise ValueError("candidate_count must be a non-negative integer")
    if type(proof.lookup_complete) is not bool:
        raise ValueError("lookup_complete must be a boolean")


def _exact_readback_record(proof: ExactDraftReadback) -> dict[str, object]:
    return {
        "name": proof.draft_name,
        "company": proof.company,
        "supplier": proof.supplier,
        "bill_reference": proof.bill_reference,
        "purchase_receipt": proof.purchase_receipt,
        "purchase_receipt_item": proof.purchase_receipt_item,
        "bill_digest": proof.bill_digest,
        "commercial_version": proof.commercial_version,
        "candidate_count": proof.candidate_count,
        "lookup_complete": proof.lookup_complete,
        "audit_snapshot_digest": proof.audit_snapshot_digest,
        "observed_at": proof.observed_at,
    }


@dataclass(frozen=True, slots=True)
class ReadbackObservation:
    """An auditable no-hit or unknown result; it cannot reopen a write fence."""

    kind: str
    audit_snapshot_digest: str
    observed_at: str
    details: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind not in {"NO_HIT", "UNKNOWN"}:
            raise ValueError("readback kind must be NO_HIT or UNKNOWN")
        object.__setattr__(
            self,
            "audit_snapshot_digest",
            _text(self.audit_snapshot_digest, "audit snapshot digest"),
        )
        object.__setattr__(self, "observed_at", _text(self.observed_at, "observed_at"))
        object.__setattr__(self, "details", _frozen_mapping(_mapping(self.details, "details")))

    def record(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "audit_snapshot_digest": self.audit_snapshot_digest,
            "observed_at": self.observed_at,
            "details": _canonical(self.details),
        }


@dataclass(frozen=True, slots=True)
class IntentSnapshot:
    intent_id: str
    action: str
    case_id: str
    company: str
    supplier: str
    bill_reference: str
    purchase_receipt: str
    purchase_receipt_item: str
    intent_version: int
    phase: Phase
    authority_status: AuthorityStatus
    approval_granted: bool
    insert_attempted: bool
    submit_attempted: bool
    source_changed: bool
    effect_conflict: bool
    effect_conflict_reason: str | None
    business_idempotency_key: str
    receipt_line_idempotency_key: str
    commercial_version: str
    audit_snapshot_digest: str
    last_readback_kind: str | None
    draft_name: str | None
    submitted_invoice_name: str | None
    frozen_basis: Mapping[str, Any]
    frozen_preview: Mapping[str, Any]
    frozen_source: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class PrepareResult:
    accepted: bool
    created: bool
    reason: str | None
    snapshot: IntentSnapshot

    @property
    def intent_id(self) -> str:
        return self.snapshot.intent_id


@dataclass(frozen=True, slots=True)
class ApprovalResult:
    granted: bool
    reason: str | None
    token: str | None
    action: str
    case_id: str
    manager_id: str
    intent_version: int


@dataclass(frozen=True, slots=True)
class AttemptClaim:
    granted: bool
    reason: str | None
    attempt_kind: AttemptKind | None
    attempt_id: str | None
    idempotency_key: str
    payload: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class ReadbackAdmission:
    admitted: bool
    reason: str | None
    snapshot: IntentSnapshot


@dataclass(frozen=True, slots=True)
class SourceRefreshResult:
    commercial_changed: bool
    snapshot: IntentSnapshot


@dataclass(frozen=True, slots=True)
class JournalEvent:
    kind: str
    recorded_at: str
    payload: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class _Envelope:
    basis: dict[str, object]
    preview: dict[str, object]
    source: dict[str, object]
    commercial_version: str
    business_key: str
    receipt_line_key: str
    insert_request: NativeInsertRequest | None


class BillingIntentJournal:
    """SQLite-backed one-way attempt fences for normal-receipt billing.

    Every mutating method uses ``BEGIN IMMEDIATE`` and commits before returning
    an attempt claim.  The class has no transport hooks, which keeps all
    network I/O outside its database transaction by construction.
    """

    def __init__(self, database: str | Path) -> None:
        self._database = str(Path(database))
        self._initialize()

    def prepare(
        self,
        basis: SyntheticBillingBasis,
        preview: BillingPreview,
        source: CommercialSource,
        *,
        insert_request: NativeInsertRequest | None = None,
    ) -> PrepareResult:
        """Persist or retrieve an admitted read-only proposal, with no authority."""

        try:
            envelope = _admit_envelope(basis, preview, source, insert_request=insert_request)
        except _AdmissionError as error:
            return self._rejected_existing(basis, error.code)
        now = _time(None)
        try:
            with self._write_connection() as connection:
                existing = self._find_conflict(connection, envelope)
                if existing is not None:
                    return self._prepare_conflict(existing, envelope)
                intent_id = uuid.uuid4().hex
                binding = _make_insert_binding(intent_id, 1, envelope)
                connection.execute(
                    """
                    INSERT INTO normal_receipt_billing_intents (
                        intent_id, action, case_id, company, supplier, bill_reference,
                        purchase_receipt, purchase_receipt_item, business_key, receipt_line_key,
                        intent_version, basis_json, preview_json, source_json, latest_source_json,
                        commercial_version, audit_snapshot_digest, observed_at, source_changed,
                        effect_conflict, effect_conflict_reason, refused_at, refused_reason,
                        approval_manager_id, approval_token_hash,
                        approval_token_issued_at, approval_token_used_at, approval_expires_at,
                        insert_attempted_at, insert_attempt_id, insert_worker_id,
                        insert_payload_json, insert_binding_json,
                        draft_name, draft_readback_json, submit_attempted_at, submit_attempt_id,
                        submit_worker_id, submit_payload_json, submitted_invoice_name,
                        submitted_readback_json, last_readback_kind, created_at, updated_at
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, 0, 0, NULL,
                        NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
                        ?, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, ?, ?
                    )
                    """,
                    (
                        intent_id,
                        ACTION_NORMAL_RECEIPT_BILLING,
                        basis.case_id,
                        basis.company,
                        basis.supplier,
                        basis.bill_reference,
                        basis.purchase_receipt,
                        basis.purchase_receipt_item,
                        envelope.business_key,
                        envelope.receipt_line_key,
                        _encoded(envelope.basis),
                        _encoded(envelope.preview),
                        _encoded(envelope.source),
                        _encoded(envelope.source),
                        envelope.commercial_version,
                        source.audit_snapshot_digest,
                        source.observed_at,
                        _encoded(binding) if binding is not None else None,
                        now,
                        now,
                    ),
                )
                self._insert_version(connection, intent_id, 1, envelope, source, now)
                self._event(
                    connection,
                    intent_id,
                    "PREPARED",
                    {
                        "basis": envelope.basis,
                        "preview": envelope.preview,
                        "source": envelope.source,
                        "commercial_version": envelope.commercial_version,
                        "insert_binding": binding,
                    },
                    now,
                )
                snapshot = self._snapshot(connection, self._intent(connection, intent_id))
                return PrepareResult(True, True, None, snapshot)
        except sqlite3.IntegrityError:
            return self._conflict_after_race(envelope)

    def reprepare(
        self,
        intent_id: str,
        basis: SyntheticBillingBasis,
        preview: BillingPreview,
        source: CommercialSource,
        *,
        insert_request: NativeInsertRequest | None = None,
        now: datetime | None = None,
    ) -> PrepareResult:
        """Version an unattempted stopped/stale intent and clear its old authority."""

        envelope = _admit_envelope(basis, preview, source, insert_request=insert_request)
        recorded_at = _time(now)
        with self._write_connection() as connection:
            row = self._intent(connection, intent_id)
            current = self._snapshot(connection, row)
            if current.insert_attempted:
                return PrepareResult(False, False, "INSERT_ALREADY_ATTEMPTED", current)
            if not current.source_changed and current.authority_status != "REFUSED":
                return PrepareResult(
                    False, False, "REPREPARE_REQUIRES_STOP_OR_SOURCE_CHANGE", current
                )
            if (
                row["business_key"] != envelope.business_key
                or row["receipt_line_key"] != envelope.receipt_line_key
            ):
                return PrepareResult(False, False, "IDENTITY_MISMATCH", current)
            next_version = current.intent_version + 1
            binding = _make_insert_binding(intent_id, next_version, envelope)
            connection.execute(
                """
                UPDATE normal_receipt_billing_intents
                SET intent_version = ?, basis_json = ?, preview_json = ?, source_json = ?,
                    latest_source_json = ?, commercial_version = ?, audit_snapshot_digest = ?,
                    observed_at = ?, source_changed = 0, refused_at = NULL, refused_reason = NULL,
                    effect_conflict = 0, effect_conflict_reason = NULL,
                    insert_binding_json = ?,
                    approval_manager_id = NULL, approval_token_hash = NULL,
                    approval_token_issued_at = NULL, approval_token_used_at = NULL,
                    approval_expires_at = NULL, draft_name = NULL, draft_readback_json = NULL,
                    last_readback_kind = NULL, updated_at = ?
                WHERE intent_id = ?
                """,
                (
                    next_version,
                    _encoded(envelope.basis),
                    _encoded(envelope.preview),
                    _encoded(envelope.source),
                    _encoded(envelope.source),
                    envelope.commercial_version,
                    source.audit_snapshot_digest,
                    source.observed_at,
                    _encoded(binding) if binding is not None else None,
                    recorded_at,
                    intent_id,
                ),
            )
            self._insert_version(connection, intent_id, next_version, envelope, source, recorded_at)
            self._event(
                connection,
                intent_id,
                "REPREPARED",
                {
                    "prior_version": current.intent_version,
                    "intent_version": next_version,
                    "basis": envelope.basis,
                    "preview": envelope.preview,
                    "source": envelope.source,
                    "commercial_version": envelope.commercial_version,
                    "insert_binding": binding,
                },
                recorded_at,
            )
            return PrepareResult(
                True, False, None, self._snapshot(connection, self._intent(connection, intent_id))
            )

    def approve(
        self,
        intent_id: str,
        *,
        case_id: str,
        manager_id: str,
        expires_at: datetime,
        now: datetime | None = None,
    ) -> ApprovalResult:
        """Issue exactly one server-generated token for the current intent version."""

        recorded_at = _time(now)
        expiry = _time(expires_at)
        if _parse_time(expiry) <= _parse_time(recorded_at):
            raise ValueError("approval expiry must be in the future")
        with self._write_connection() as connection:
            row = self._intent(connection, intent_id)
            current = self._snapshot(connection, row, recorded_at)
            if case_id != current.case_id:
                return self._approval_denial(current, manager_id, "CASE_MISMATCH")
            if current.authority_status == "REFUSED":
                return self._approval_denial(current, manager_id, "REFUSED")
            if current.effect_conflict:
                return self._approval_denial(current, manager_id, "EFFECT_IDENTITY_CONFLICT")
            if current.source_changed:
                return self._approval_denial(current, manager_id, "COMMERCIAL_SOURCE_CHANGED")
            if current.insert_attempted:
                return self._approval_denial(current, manager_id, "INSERT_ALREADY_ATTEMPTED")
            try:
                _stored_insert_binding(row)
            except _AdmissionError as error:
                return self._approval_denial(current, manager_id, error.code)
            if row["approval_token_hash"] is not None:
                return self._approval_denial(current, manager_id, "APPROVAL_ALREADY_ISSUED")
            manager = _text(manager_id, "manager_id")
            token = secrets.token_urlsafe(32)
            token_hash = _digest({"approval_token": token})
            connection.execute(
                """
                UPDATE normal_receipt_billing_intents
                SET approval_manager_id = ?, approval_token_hash = ?, approval_token_issued_at = ?,
                    approval_expires_at = ?, updated_at = ?
                WHERE intent_id = ?
                """,
                (manager, token_hash, recorded_at, expiry, recorded_at, intent_id),
            )
            self._event(
                connection,
                intent_id,
                "APPROVED",
                {
                    "action": ACTION_NORMAL_RECEIPT_BILLING,
                    "case_id": current.case_id,
                    "manager_id": manager,
                    "intent_version": current.intent_version,
                    "expires_at": expiry,
                    "token_hash": token_hash,
                },
                recorded_at,
            )
            return ApprovalResult(
                True,
                None,
                token,
                ACTION_NORMAL_RECEIPT_BILLING,
                current.case_id,
                manager,
                current.intent_version,
            )

    def refuse(
        self,
        intent_id: str,
        *,
        case_id: str,
        manager_id: str,
        reason: str,
        now: datetime | None = None,
    ) -> IntentSnapshot:
        """Persist a stop request without erasing any attempted/readback phase."""

        recorded_at = _time(now)
        with self._write_connection() as connection:
            row = self._intent(connection, intent_id)
            current = self._snapshot(connection, row, recorded_at)
            if case_id != current.case_id:
                raise ValueError("CASE_MISMATCH")
            approved_manager = row["approval_manager_id"]
            if approved_manager is not None and manager_id != approved_manager:
                raise ValueError("MANAGER_MISMATCH")
            if row["refused_at"] is None:
                stop_reason = _text(reason, "refusal reason")
                connection.execute(
                    """
                    UPDATE normal_receipt_billing_intents
                    SET refused_at = ?, refused_reason = ?, updated_at = ?
                    WHERE intent_id = ?
                    """,
                    (recorded_at, stop_reason, recorded_at, intent_id),
                )
                self._event(
                    connection,
                    intent_id,
                    "REFUSED",
                    {"case_id": current.case_id, "manager_id": manager_id, "reason": stop_reason},
                    recorded_at,
                )
            return self._snapshot(connection, self._intent(connection, intent_id), recorded_at)

    def refresh_source(
        self,
        intent_id: str,
        source: CommercialSource,
        *,
        now: datetime | None = None,
    ) -> SourceRefreshResult:
        """Record current evidence; commercial change is sticky until explicit reprepare."""

        recorded_at = _time(now)
        with self._write_connection() as connection:
            row = self._intent(connection, intent_id)
            frozen_source = _decoded_mapping(cast(str, row["source_json"]), "source")
            frozen_commercial = {
                "identity": frozen_source["identity"],
                "revisions": frozen_source["revisions"],
                "decisive_values": frozen_source["decisive_values"],
            }
            commercial_changed = _encoded(frozen_commercial) != _encoded(source.commercial_record())
            changed = _sqlite_true(row["source_changed"]) or commercial_changed
            connection.execute(
                """
                UPDATE normal_receipt_billing_intents
                SET latest_source_json = ?, audit_snapshot_digest = ?, observed_at = ?,
                    source_changed = ?, updated_at = ?
                WHERE intent_id = ?
                """,
                (
                    _encoded(source.record()),
                    source.audit_snapshot_digest,
                    source.observed_at,
                    int(changed),
                    recorded_at,
                    intent_id,
                ),
            )
            self._event(
                connection,
                intent_id,
                "SOURCE_REFRESHED",
                {
                    **source.record(),
                    "commercial_changed": commercial_changed,
                    "source_changed": changed,
                },
                recorded_at,
            )
            snapshot = self._snapshot(connection, self._intent(connection, intent_id), recorded_at)
            return SourceRefreshResult(commercial_changed, snapshot)

    def claim_insert(
        self,
        intent_id: str,
        *,
        case_id: str,
        manager_id: str,
        approval_token: str,
        worker_id: str,
        now: datetime | None = None,
    ) -> AttemptClaim:
        """Commit the one insert marker and immutable payload before any future I/O."""

        recorded_at = _time(now)
        with self._write_connection() as connection:
            row = self._intent(connection, intent_id)
            current = self._snapshot(connection, row, recorded_at)
            denial = self._insert_denial(
                row, current, case_id, manager_id, approval_token, recorded_at
            )
            if denial is not None:
                return denial
            attempt_id = uuid.uuid4().hex
            binding, request = _stored_insert_binding(row)
            payload = self._attempt_payload(
                row,
                "INSERT",
                attempt_id=attempt_id,
                binding=binding,
                request=request,
            )
            connection.execute(
                """
                UPDATE normal_receipt_billing_intents
                SET insert_attempted_at = ?, insert_attempt_id = ?, insert_worker_id = ?,
                    insert_payload_json = ?, approval_token_used_at = ?, updated_at = ?
                WHERE intent_id = ? AND insert_attempted_at IS NULL
                """,
                (
                    recorded_at,
                    attempt_id,
                    _text(worker_id, "worker_id"),
                    _encoded(payload),
                    recorded_at,
                    recorded_at,
                    intent_id,
                ),
            )
            self._event(
                connection,
                intent_id,
                "INSERT_ATTEMPT_MARKED",
                {"attempt_id": attempt_id, "worker_id": worker_id, "payload": payload},
                recorded_at,
            )
            return AttemptClaim(
                True,
                None,
                "INSERT",
                attempt_id,
                current.business_idempotency_key,
                _frozen_mapping(payload),
            )

    def admit_insert_acknowledgement(
        self, intent_id: str, acknowledgement: NativeDraftAcknowledgement
    ) -> ReadbackAdmission:
        """Persist the one known-name insert response bound to the marked request."""

        if not isinstance(acknowledgement, NativeDraftAcknowledgement):
            raise TypeError("insert acknowledgement requires NativeDraftAcknowledgement")
        with self._write_connection() as connection:
            row = self._intent(connection, intent_id)
            current = self._snapshot(connection, row)
            if not current.insert_attempted:
                return ReadbackAdmission(False, "INSERT_ATTEMPT_REQUIRED", current)
            try:
                binding, request = _stored_insert_binding(row)
            except _AdmissionError as error:
                return ReadbackAdmission(False, error.code, current)
            basis = _decoded_mapping(cast(str, row["basis_json"]), "basis")
            if (
                not _insert_marker_matches(row, binding, request)
                or acknowledgement.insert_body_digest != request.body_digest
                or _native_document_local_reason(
                    acknowledgement.document,
                    basis,
                    expected_name=acknowledgement.draft_name,
                    expected_docstatus=0,
                )
                is not None
            ):
                return ReadbackAdmission(False, "INSERT_ACKNOWLEDGEMENT_MISMATCH", current)
            recorded_at = _time(None)
            if row["draft_readback_json"] is not None:
                try:
                    _, _, known = _stored_draft_acknowledgement(row)
                except _AdmissionError:
                    return ReadbackAdmission(False, "DRAFT_ACKNOWLEDGEMENT_REQUIRED", current)
                if (
                    acknowledgement.draft_name != known.draft_name
                    or acknowledgement.document_digest != known.document_digest
                ):
                    return self._identity_conflict(
                        connection,
                        intent_id,
                        reason="DRAFT_ACKNOWLEDGEMENT_CONFLICT",
                        event_kind="DRAFT_ACKNOWLEDGEMENT_CONFLICT",
                        known_name=known.draft_name,
                        proof=acknowledgement.record(),
                        recorded_at=recorded_at,
                    )
                self._event(
                    connection,
                    intent_id,
                    "INSERT_ACKNOWLEDGEMENT_REAFFIRMED",
                    _draft_acknowledgement_envelope(row, binding, acknowledgement),
                    recorded_at,
                )
                return ReadbackAdmission(
                    True, None, self._snapshot(connection, self._intent(connection, intent_id))
                )
            envelope = _draft_acknowledgement_envelope(row, binding, acknowledgement)
            connection.execute(
                """
                UPDATE normal_receipt_billing_intents
                SET draft_name = ?, draft_readback_json = ?, last_readback_kind = 'DRAFT',
                    updated_at = ?
                WHERE intent_id = ?
                """,
                (acknowledgement.draft_name, _encoded(envelope), recorded_at, intent_id),
            )
            self._event(
                connection,
                intent_id,
                "INSERT_ACKNOWLEDGEMENT_ADMITTED",
                envelope,
                recorded_at,
            )
            return ReadbackAdmission(
                True, None, self._snapshot(connection, self._intent(connection, intent_id))
            )

    def admit_draft_readback(self, intent_id: str, proof: ExactDraftReadback) -> ReadbackAdmission:
        """Record a legacy exact proof only after a bound native acknowledgement exists."""

        with self._write_connection() as connection:
            row = self._intent(connection, intent_id)
            current = self._snapshot(connection, row)
            if not current.insert_attempted:
                return ReadbackAdmission(False, "INSERT_ATTEMPT_REQUIRED", current)
            reason = self._exact_proof_reason(row, proof)
            if reason is not None:
                return ReadbackAdmission(False, reason, current)
            try:
                _, _, acknowledgement = _stored_draft_acknowledgement(row)
            except _AdmissionError as error:
                if error.code == "DRAFT_ACKNOWLEDGEMENT_REQUIRED":
                    return ReadbackAdmission(False, "INSERT_ACKNOWLEDGEMENT_REQUIRED", current)
                return ReadbackAdmission(False, error.code, current)
            recorded_at = _time(None)
            if proof.draft_name != acknowledgement.draft_name:
                return self._identity_conflict(
                    connection,
                    intent_id,
                    reason="DRAFT_IDENTITY_CONFLICT",
                    event_kind="DRAFT_READBACK_CONFLICT",
                    known_name=acknowledgement.draft_name,
                    proof=proof.record(),
                    recorded_at=recorded_at,
                )
            self._event(
                connection,
                intent_id,
                "DRAFT_READBACK_REAFFIRMED",
                proof.record(),
                recorded_at,
            )
            return ReadbackAdmission(
                True, None, self._snapshot(connection, self._intent(connection, intent_id))
            )

    def claim_submit(
        self,
        intent_id: str,
        *,
        case_id: str,
        manager_id: str,
        worker_id: str,
        now: datetime | None = None,
    ) -> AttemptClaim:
        """Commit the separate one submit marker before any future I/O."""

        recorded_at = _time(now)
        with self._write_connection() as connection:
            row = self._intent(connection, intent_id)
            current = self._snapshot(connection, row, recorded_at)
            denial = self._submit_denial(row, current, case_id, manager_id, recorded_at)
            if denial is not None:
                return denial
            attempt_id = uuid.uuid4().hex
            binding, _, acknowledgement = _stored_draft_acknowledgement(row)
            submit_request = NativeSubmitRequest.from_draft(acknowledgement)
            payload = self._attempt_payload(
                row,
                "SUBMIT",
                attempt_id=attempt_id,
                binding=binding,
                request=submit_request,
                acknowledgement=acknowledgement,
            )
            connection.execute(
                """
                UPDATE normal_receipt_billing_intents
                SET submit_attempted_at = ?, submit_attempt_id = ?, submit_worker_id = ?,
                    submit_payload_json = ?, updated_at = ?
                WHERE intent_id = ? AND submit_attempted_at IS NULL
                """,
                (
                    recorded_at,
                    attempt_id,
                    _text(worker_id, "worker_id"),
                    _encoded(payload),
                    recorded_at,
                    intent_id,
                ),
            )
            self._event(
                connection,
                intent_id,
                "SUBMIT_ATTEMPT_MARKED",
                {"attempt_id": attempt_id, "worker_id": worker_id, "payload": payload},
                recorded_at,
            )
            return AttemptClaim(
                True,
                None,
                "SUBMIT",
                attempt_id,
                current.business_idempotency_key,
                _frozen_mapping(payload),
            )

    def admit_submitted_readback(
        self, intent_id: str, proof: NativeSubmittedReadback
    ) -> ReadbackAdmission:
        """Admit an exact full-document submit readback without reopening a marker."""

        if not isinstance(proof, NativeSubmittedReadback):
            raise TypeError("submitted readback requires NativeSubmittedReadback")
        with self._write_connection() as connection:
            row = self._intent(connection, intent_id)
            current = self._snapshot(connection, row)
            if not current.submit_attempted:
                return ReadbackAdmission(False, "SUBMIT_ATTEMPT_REQUIRED", current)
            try:
                binding, _, acknowledgement = _stored_draft_acknowledgement(row)
                submit_request = NativeSubmitRequest.from_draft(acknowledgement)
            except _AdmissionError as error:
                return ReadbackAdmission(False, error.code, current)
            if not _submit_marker_matches(row, binding, acknowledgement, submit_request):
                return ReadbackAdmission(False, "SUBMITTED_READBACK_BINDING_INVALID", current)
            basis = _decoded_mapping(cast(str, row["basis_json"]), "basis")
            if (
                proof.draft_name != acknowledgement.draft_name
                or proof.draft_document_digest != acknowledgement.document_digest
            ):
                return self._identity_conflict(
                    connection,
                    intent_id,
                    reason="SUBMITTED_DRAFT_DOCUMENT_MISMATCH",
                    event_kind="SUBMITTED_READBACK_CONFLICT",
                    known_name=acknowledgement.draft_name,
                    proof=proof.record(),
                    recorded_at=_time(None),
                )
            if (
                _native_document_local_reason(
                    proof.document,
                    basis,
                    expected_name=acknowledgement.draft_name,
                    expected_docstatus=1,
                )
                is not None
            ):
                return ReadbackAdmission(False, "SUBMITTED_READBACK_MISMATCH", current)
            recorded_at = _time(None)
            if current.submitted_invoice_name is not None:
                try:
                    known = _decoded_mapping(
                        cast(str, row["submitted_readback_json"]), "submitted readback"
                    )
                    known_proof = known["submitted_readback"]
                    known_digest = (
                        known_proof.get("document_digest")
                        if isinstance(known_proof, Mapping)
                        else None
                    )
                except (RuntimeError, KeyError, TypeError):
                    return ReadbackAdmission(False, "SUBMITTED_READBACK_INVALID", current)
                if (
                    proof.draft_name != current.submitted_invoice_name
                    or proof.document_digest != known_digest
                ):
                    return self._identity_conflict(
                        connection,
                        intent_id,
                        reason="SUBMITTED_IDENTITY_CONFLICT",
                        event_kind="SUBMITTED_READBACK_CONFLICT",
                        known_name=current.submitted_invoice_name,
                        proof=proof.record(),
                        recorded_at=recorded_at,
                    )
                self._event(
                    connection,
                    intent_id,
                    "SUBMITTED_READBACK_REAFFIRMED",
                    proof.record(),
                    recorded_at,
                )
                return ReadbackAdmission(
                    True, None, self._snapshot(connection, self._intent(connection, intent_id))
                )
            submit_attempt_id = row["submit_attempt_id"]
            binding_digest = binding.get("binding_digest")
            if not isinstance(submit_attempt_id, str) or not isinstance(binding_digest, str):
                return ReadbackAdmission(False, "SUBMITTED_READBACK_BINDING_INVALID", current)
            envelope = {
                "submit_attempt_id": submit_attempt_id,
                "intent_version": row["intent_version"],
                "insert_binding_digest": binding_digest,
                "submitted_readback": proof.record(),
            }
            connection.execute(
                """
                UPDATE normal_receipt_billing_intents
                SET submitted_invoice_name = ?, submitted_readback_json = ?,
                    last_readback_kind = 'SUBMITTED', updated_at = ?
                WHERE intent_id = ?
                """,
                (proof.draft_name, _encoded(envelope), recorded_at, intent_id),
            )
            self._event(
                connection,
                intent_id,
                "SUBMITTED_READBACK_ADMITTED",
                envelope,
                recorded_at,
            )
            return ReadbackAdmission(
                True, None, self._snapshot(connection, self._intent(connection, intent_id))
            )

    def record_no_hit(
        self, intent_id: str, observation: ReadbackObservation, *, now: datetime | None = None
    ) -> IntentSnapshot:
        if observation.kind != "NO_HIT":
            raise ValueError("record_no_hit requires NO_HIT")
        return self._record_readback(intent_id, observation, now=now)

    def record_unknown(
        self, intent_id: str, observation: ReadbackObservation, *, now: datetime | None = None
    ) -> IntentSnapshot:
        if observation.kind != "UNKNOWN":
            raise ValueError("record_unknown requires UNKNOWN")
        return self._record_readback(intent_id, observation, now=now)

    def get(self, intent_id: str) -> IntentSnapshot:
        with self._connect() as connection:
            return self._snapshot(connection, self._intent(connection, intent_id))

    def history(self, intent_id: str) -> tuple[JournalEvent, ...]:
        with self._connect() as connection:
            self._intent(connection, intent_id)
            rows = connection.execute(
                """
                SELECT kind, recorded_at, payload_json
                FROM normal_receipt_billing_events
                WHERE intent_id = ? ORDER BY event_id
                """,
                (intent_id,),
            ).fetchall()
        return tuple(
            JournalEvent(
                kind=cast(str, row["kind"]),
                recorded_at=cast(str, row["recorded_at"]),
                payload=_frozen_mapping(
                    _decoded_mapping(cast(str, row["payload_json"]), "event payload")
                ),
            )
            for row in rows
        )

    def _record_readback(
        self, intent_id: str, observation: ReadbackObservation, *, now: datetime | None
    ) -> IntentSnapshot:
        recorded_at = _time(now)
        with self._write_connection() as connection:
            self._intent(connection, intent_id)
            connection.execute(
                """
                UPDATE normal_receipt_billing_intents
                SET last_readback_kind = ?, updated_at = ? WHERE intent_id = ?
                """,
                (observation.kind, recorded_at, intent_id),
            )
            self._event(connection, intent_id, observation.kind, observation.record(), recorded_at)
            return self._snapshot(connection, self._intent(connection, intent_id), recorded_at)

    def _rejected_existing(self, basis: SyntheticBillingBasis, reason: str) -> PrepareResult:
        business_key = _key(basis.company, basis.supplier, basis.bill_reference)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM normal_receipt_billing_intents WHERE business_key = ?",
                (business_key,),
            ).fetchone()
            if row is None:
                raise ValueError(reason)
            return PrepareResult(False, False, reason, self._snapshot(connection, row))

    def _conflict_after_race(self, envelope: _Envelope) -> PrepareResult:
        with self._connect() as connection:
            row = self._find_conflict(connection, envelope)
            if row is None:  # pragma: no cover - SQLite conflict must leave a committed row
                raise RuntimeError("normal-billing conflict disappeared")
            return self._prepare_conflict(row, envelope)

    def _prepare_conflict(self, row: sqlite3.Row, envelope: _Envelope) -> PrepareResult:
        snapshot = self._snapshot_from_row(row)
        if row["business_key"] == envelope.business_key:
            if row["commercial_version"] == envelope.commercial_version:
                if row["insert_binding_json"] is None and envelope.insert_request is None:
                    return PrepareResult(True, False, None, snapshot)
                try:
                    _, stored_request = _stored_insert_binding(row)
                except _AdmissionError as error:
                    return PrepareResult(False, False, error.code, snapshot)
                if envelope.insert_request is not None and _encoded(
                    stored_request.record()
                ) == _encoded(envelope.insert_request.record()):
                    return PrepareResult(True, False, None, snapshot)
                return PrepareResult(False, False, "REPREPARE_REQUIRED", snapshot)
            return PrepareResult(False, False, "REPREPARE_REQUIRED", snapshot)
        return PrepareResult(False, False, "RECEIPT_LINE_CONFLICT", snapshot)

    def _approval_denial(
        self, snapshot: IntentSnapshot, manager_id: str, reason: str
    ) -> ApprovalResult:
        return ApprovalResult(
            False,
            reason,
            None,
            ACTION_NORMAL_RECEIPT_BILLING,
            snapshot.case_id,
            manager_id,
            snapshot.intent_version,
        )

    def _insert_denial(
        self,
        row: sqlite3.Row,
        snapshot: IntentSnapshot,
        case_id: str,
        manager_id: str,
        approval_token: str,
        recorded_at: str,
    ) -> AttemptClaim | None:
        if case_id != snapshot.case_id:
            return self._denied_claim(snapshot, "CASE_MISMATCH")
        if snapshot.effect_conflict:
            return self._denied_claim(snapshot, "EFFECT_IDENTITY_CONFLICT")
        if snapshot.authority_status == "REFUSED":
            return self._denied_claim(snapshot, "REFUSED")
        if snapshot.source_changed:
            return self._denied_claim(snapshot, "COMMERCIAL_SOURCE_CHANGED")
        if snapshot.insert_attempted:
            return self._denied_claim(snapshot, "INSERT_ALREADY_ATTEMPTED")
        try:
            _stored_insert_binding(row)
        except _AdmissionError as error:
            return self._denied_claim(snapshot, error.code)
        if row["approval_token_hash"] is None:
            return self._denied_claim(snapshot, "APPROVAL_REQUIRED")
        if row["approval_manager_id"] != manager_id:
            return self._denied_claim(snapshot, "MANAGER_MISMATCH")
        if _expired(row, recorded_at):
            return self._denied_claim(snapshot, "APPROVAL_EXPIRED")
        if row["approval_token_used_at"] is not None:
            return self._denied_claim(snapshot, "APPROVAL_TOKEN_USED")
        if _digest({"approval_token": approval_token}) != row["approval_token_hash"]:
            return self._denied_claim(snapshot, "APPROVAL_REQUIRED")
        return None

    def _submit_denial(
        self,
        row: sqlite3.Row,
        snapshot: IntentSnapshot,
        case_id: str,
        manager_id: str,
        recorded_at: str,
    ) -> AttemptClaim | None:
        if case_id != snapshot.case_id:
            return self._denied_claim(snapshot, "CASE_MISMATCH")
        if snapshot.effect_conflict:
            return self._denied_claim(snapshot, "EFFECT_IDENTITY_CONFLICT")
        if snapshot.authority_status == "REFUSED":
            return self._denied_claim(snapshot, "REFUSED")
        if snapshot.source_changed:
            return self._denied_claim(snapshot, "COMMERCIAL_SOURCE_CHANGED")
        if snapshot.submit_attempted:
            return self._denied_claim(snapshot, "SUBMIT_ALREADY_ATTEMPTED")
        if not snapshot.insert_attempted:
            return self._denied_claim(snapshot, "INSERT_ATTEMPT_REQUIRED")
        if row["draft_readback_json"] is None:
            return self._denied_claim(snapshot, "DRAFT_ACKNOWLEDGEMENT_REQUIRED")
        try:
            _stored_draft_acknowledgement(row)
        except _AdmissionError as error:
            return self._denied_claim(snapshot, error.code)
        if row["approval_token_hash"] is None:
            return self._denied_claim(snapshot, "APPROVAL_REQUIRED")
        if row["approval_manager_id"] != manager_id:
            return self._denied_claim(snapshot, "MANAGER_MISMATCH")
        if _expired(row, recorded_at):
            return self._denied_claim(snapshot, "APPROVAL_EXPIRED")
        return None

    def _denied_claim(self, snapshot: IntentSnapshot, reason: str) -> AttemptClaim:
        return AttemptClaim(
            False,
            reason,
            None,
            None,
            snapshot.business_idempotency_key,
            MappingProxyType({}),
        )

    def _identity_conflict(
        self,
        connection: sqlite3.Connection,
        intent_id: str,
        *,
        reason: str,
        event_kind: str,
        known_name: str | None,
        proof: Mapping[str, object],
        recorded_at: str,
    ) -> ReadbackAdmission:
        """Hold future writes while retaining the first admitted effect evidence."""

        connection.execute(
            """
            UPDATE normal_receipt_billing_intents
            SET effect_conflict = 1, effect_conflict_reason = ?, updated_at = ?
            WHERE intent_id = ?
            """,
            (reason, recorded_at, intent_id),
        )
        self._event(
            connection,
            intent_id,
            event_kind,
            {"reason": reason, "known_name": known_name, "incoming_proof": proof},
            recorded_at,
        )
        return ReadbackAdmission(
            False,
            reason,
            self._snapshot(connection, self._intent(connection, intent_id)),
        )

    def _exact_proof_reason(self, row: sqlite3.Row, proof: ExactDraftReadback) -> str | None:
        prefix = "DRAFT"
        if not proof.lookup_complete:
            return f"{prefix}_READBACK_INCOMPLETE"
        if proof.candidate_count != 1:
            return f"{prefix}_READBACK_NOT_UNIQUE"
        preview = _decoded_mapping(cast(str, row["preview_json"]), "preview")
        expected = {
            "company": row["company"],
            "supplier": row["supplier"],
            "bill_reference": row["bill_reference"],
            "purchase_receipt": row["purchase_receipt"],
            "purchase_receipt_item": row["purchase_receipt_item"],
            "bill_digest": preview["bill_digest"],
            "commercial_version": row["commercial_version"],
        }
        actual = {
            "company": proof.company,
            "supplier": proof.supplier,
            "bill_reference": proof.bill_reference,
            "purchase_receipt": proof.purchase_receipt,
            "purchase_receipt_item": proof.purchase_receipt_item,
            "bill_digest": proof.bill_digest,
            "commercial_version": proof.commercial_version,
        }
        return None if actual == expected else f"{prefix}_READBACK_MISMATCH"

    def _attempt_payload(
        self,
        row: sqlite3.Row,
        kind: AttemptKind,
        *,
        attempt_id: str,
        binding: Mapping[str, object],
        request: NativeInsertRequest | NativeSubmitRequest,
        acknowledgement: NativeDraftAcknowledgement | None = None,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "action": ACTION_NORMAL_RECEIPT_BILLING,
            "attempt_kind": kind,
            "attempt_id": attempt_id,
            "intent_id": row["intent_id"],
            "intent_version": row["intent_version"],
            "business_idempotency_key": row["business_key"],
            "receipt_line_idempotency_key": row["receipt_line_key"],
            "basis": _decoded_mapping(cast(str, row["basis_json"]), "basis"),
            "preview": _decoded_mapping(cast(str, row["preview_json"]), "preview"),
            "commercial_version": row["commercial_version"],
            "request_binding": dict(binding),
            "native_request": request.record(),
        }
        if kind == "SUBMIT":
            payload["draft_name"] = row["draft_name"]
            if acknowledgement is None:
                raise ValueError("submit payload requires acknowledged draft")
            payload["insert_acknowledgement"] = acknowledgement.record()
        return cast(dict[str, object], _canonical(payload))

    def _snapshot(
        self, connection: sqlite3.Connection, row: sqlite3.Row, now: str | None = None
    ) -> IntentSnapshot:
        return self._snapshot_from_row(row, now)

    def _snapshot_from_row(self, row: sqlite3.Row, now: str | None = None) -> IntentSnapshot:
        phase = _phase(row)
        authority_status = _authority_status(row, now)
        return IntentSnapshot(
            intent_id=cast(str, row["intent_id"]),
            action=cast(str, row["action"]),
            case_id=cast(str, row["case_id"]),
            company=cast(str, row["company"]),
            supplier=cast(str, row["supplier"]),
            bill_reference=cast(str, row["bill_reference"]),
            purchase_receipt=cast(str, row["purchase_receipt"]),
            purchase_receipt_item=cast(str, row["purchase_receipt_item"]),
            intent_version=cast(int, row["intent_version"]),
            phase=phase,
            authority_status=authority_status,
            approval_granted=row["approval_token_hash"] is not None,
            insert_attempted=row["insert_attempted_at"] is not None,
            submit_attempted=row["submit_attempted_at"] is not None,
            source_changed=_sqlite_true(row["source_changed"]),
            effect_conflict=_sqlite_true(row["effect_conflict"]),
            effect_conflict_reason=cast(str | None, row["effect_conflict_reason"]),
            business_idempotency_key=cast(str, row["business_key"]),
            receipt_line_idempotency_key=cast(str, row["receipt_line_key"]),
            commercial_version=cast(str, row["commercial_version"]),
            audit_snapshot_digest=cast(str, row["audit_snapshot_digest"]),
            last_readback_kind=cast(str | None, row["last_readback_kind"]),
            draft_name=cast(str | None, row["draft_name"]),
            submitted_invoice_name=cast(str | None, row["submitted_invoice_name"]),
            frozen_basis=_frozen_mapping(_decoded_mapping(cast(str, row["basis_json"]), "basis")),
            frozen_preview=_frozen_mapping(
                _decoded_mapping(cast(str, row["preview_json"]), "preview")
            ),
            frozen_source=_frozen_mapping(
                _decoded_mapping(cast(str, row["source_json"]), "source")
            ),
        )

    def _find_conflict(
        self, connection: sqlite3.Connection, envelope: _Envelope
    ) -> sqlite3.Row | None:
        row = connection.execute(
            """
            SELECT * FROM normal_receipt_billing_intents
            WHERE business_key = ? OR receipt_line_key = ?
            """,
            (envelope.business_key, envelope.receipt_line_key),
        ).fetchone()
        return cast(sqlite3.Row | None, row)

    def _intent(self, connection: sqlite3.Connection, intent_id: str) -> sqlite3.Row:
        row = cast(
            sqlite3.Row | None,
            connection.execute(
                "SELECT * FROM normal_receipt_billing_intents WHERE intent_id = ?", (intent_id,)
            ).fetchone(),
        )
        if row is None:
            raise KeyError(intent_id)
        return row

    def _insert_version(
        self,
        connection: sqlite3.Connection,
        intent_id: str,
        version: int,
        envelope: _Envelope,
        source: CommercialSource,
        recorded_at: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO normal_receipt_billing_versions (
                intent_id, intent_version, basis_json, preview_json, source_json,
                commercial_version, audit_snapshot_digest, observed_at, recorded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                intent_id,
                version,
                _encoded(envelope.basis),
                _encoded(envelope.preview),
                _encoded(envelope.source),
                envelope.commercial_version,
                source.audit_snapshot_digest,
                source.observed_at,
                recorded_at,
            ),
        )

    def _event(
        self,
        connection: sqlite3.Connection,
        intent_id: str,
        kind: str,
        payload: Mapping[str, object],
        recorded_at: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO normal_receipt_billing_events (intent_id, kind, recorded_at, payload_json)
            VALUES (?, ?, ?, ?)
            """,
            (intent_id, kind, recorded_at, _encoded(payload)),
        )

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS normal_receipt_billing_intents (
                    intent_id TEXT PRIMARY KEY,
                    action TEXT NOT NULL,
                    case_id TEXT NOT NULL,
                    company TEXT NOT NULL,
                    supplier TEXT NOT NULL,
                    bill_reference TEXT NOT NULL,
                    purchase_receipt TEXT NOT NULL,
                    purchase_receipt_item TEXT NOT NULL,
                    business_key TEXT NOT NULL UNIQUE,
                    receipt_line_key TEXT NOT NULL UNIQUE,
                    intent_version INTEGER NOT NULL,
                    basis_json TEXT NOT NULL,
                    preview_json TEXT NOT NULL,
                    source_json TEXT NOT NULL,
                    latest_source_json TEXT NOT NULL,
                    commercial_version TEXT NOT NULL,
                    audit_snapshot_digest TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    source_changed INTEGER NOT NULL,
                    effect_conflict INTEGER NOT NULL,
                    effect_conflict_reason TEXT,
                    refused_at TEXT,
                    refused_reason TEXT,
                    approval_manager_id TEXT,
                    approval_token_hash TEXT,
                    approval_token_issued_at TEXT,
                    approval_token_used_at TEXT,
                    approval_expires_at TEXT,
                    insert_attempted_at TEXT,
                    insert_attempt_id TEXT,
                    insert_worker_id TEXT,
                    insert_payload_json TEXT,
                    insert_binding_json TEXT,
                    draft_name TEXT,
                    draft_readback_json TEXT,
                    submit_attempted_at TEXT,
                    submit_attempt_id TEXT,
                    submit_worker_id TEXT,
                    submit_payload_json TEXT,
                    submitted_invoice_name TEXT,
                    submitted_readback_json TEXT,
                    last_readback_kind TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE (company, supplier, bill_reference),
                    UNIQUE (company, purchase_receipt, purchase_receipt_item)
                );
                CREATE TABLE IF NOT EXISTS normal_receipt_billing_versions (
                    intent_id TEXT NOT NULL,
                    intent_version INTEGER NOT NULL,
                    basis_json TEXT NOT NULL,
                    preview_json TEXT NOT NULL,
                    source_json TEXT NOT NULL,
                    commercial_version TEXT NOT NULL,
                    audit_snapshot_digest TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    PRIMARY KEY (intent_id, intent_version),
                    FOREIGN KEY (intent_id) REFERENCES normal_receipt_billing_intents(intent_id)
                );
                CREATE TABLE IF NOT EXISTS normal_receipt_billing_events (
                    event_id INTEGER PRIMARY KEY,
                    intent_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    FOREIGN KEY (intent_id) REFERENCES normal_receipt_billing_intents(intent_id)
                );
                """
            )
        with self._write_connection() as connection:
            columns = {
                cast(str, row["name"])
                for row in connection.execute("PRAGMA table_info(normal_receipt_billing_intents)")
            }
            if "insert_binding_json" not in columns:
                connection.execute(
                    "ALTER TABLE normal_receipt_billing_intents ADD COLUMN insert_binding_json TEXT"
                )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database, timeout=10.0, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 10000")
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @contextmanager
    def _write_connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()


def _admit_envelope(
    basis: SyntheticBillingBasis,
    preview: BillingPreview,
    source: CommercialSource,
    *,
    insert_request: NativeInsertRequest | None,
) -> _Envelope:
    if (
        preview.status != "READY"
        or preview.read_only is not True
        or preview.write_allowed is not False
    ):
        raise _AdmissionError("PREVIEW_NOT_READ_ONLY_READY")
    if preview.reasons:
        raise _AdmissionError("PREVIEW_HAS_REASONS")
    if preview.bill_digest != basis.bill_digest:
        raise _AdmissionError("PREVIEW_BASIS_MISMATCH")
    exact_ids = preview.exact_ids
    if (
        exact_ids.case_id != basis.case_id
        or exact_ids.purchase_order != basis.purchase_order
        or exact_ids.purchase_order_item != basis.purchase_order_item
        or exact_ids.purchase_receipt != basis.purchase_receipt
        or exact_ids.purchase_receipt_item != basis.purchase_receipt_item
        or preview.quantity != basis.quantity
        or preview.uom != basis.uom
        or preview.stock_uom != basis.stock_uom
        or preview.conversion_factor != basis.conversion_factor
        or preview.net_amount != basis.net_amount
        or preview.gross_amount != basis.gross_amount
    ):
        raise _AdmissionError("PREVIEW_BASIS_MISMATCH")
    if len(preview.source_digest) != 64:
        raise _AdmissionError("PREVIEW_SOURCE_DIGEST_INVALID")
    try:
        int(preview.source_digest, 16)
    except ValueError:
        raise _AdmissionError("PREVIEW_SOURCE_DIGEST_INVALID") from None
    if "SEPARATE_APPROVAL_REQUIRED" not in preview.required_inputs:
        raise _AdmissionError("PREVIEW_APPROVAL_BOUNDARY_MISSING")

    expected_identity = {
        "company": basis.company,
        "supplier": basis.supplier,
        "purchase_order": basis.purchase_order,
        "purchase_order_item": basis.purchase_order_item,
        "purchase_receipt": basis.purchase_receipt,
        "purchase_receipt_item": basis.purchase_receipt_item,
        "item_code": basis.item_code,
    }
    if dict(source.identity) != expected_identity:
        raise _AdmissionError("SOURCE_IDENTITY_MISMATCH")
    required_revisions = {"purchase_order", "purchase_receipt", "related_documents"}
    if set(source.revisions) != required_revisions or any(
        not isinstance(value, str) or not value.strip() for value in source.revisions.values()
    ):
        raise _AdmissionError("SOURCE_REVISION_MISMATCH")
    expected_values = {
        "quantity": str(basis.quantity),
        "uom": basis.uom,
        "stock_uom": basis.stock_uom,
        "conversion_factor": str(basis.conversion_factor),
        "net_rate": str(basis.net_rate),
        "currency": basis.currency,
        "gross_amount": str(basis.gross_amount),
    }
    if dict(source.decisive_values) != expected_values:
        raise _AdmissionError("SOURCE_COMMERCIAL_MISMATCH")
    basis_record = _mapping(basis.record(), "basis")
    preview_record = _mapping(preview.record(), "preview")
    source_record = _mapping(source.record(), "source")
    admitted_request = _admit_insert_request(basis, insert_request)
    commercial_version = _digest(
        {
            "basis_digest": basis.bill_digest,
            "source": source.commercial_record(),
        }
    )
    return _Envelope(
        basis=basis_record,
        preview=preview_record,
        source=source_record,
        commercial_version=commercial_version,
        business_key=_key(basis.company, basis.supplier, basis.bill_reference),
        receipt_line_key=_key(basis.company, basis.purchase_receipt, basis.purchase_receipt_item),
        insert_request=admitted_request,
    )


def _admit_insert_request(
    basis: SyntheticBillingBasis, request: NativeInsertRequest | None
) -> NativeInsertRequest | None:
    """Accept a locally complete frozen insert body without revalidating commerce."""

    if request is None:
        return None
    if not isinstance(request, NativeInsertRequest):
        raise _AdmissionError("INSERT_REQUEST_INVALID")
    try:
        recovered = NativeInsertRequest.from_record(request.record())
    except (TypeError, ValueError):
        raise _AdmissionError("INSERT_REQUEST_INVALID") from None
    if (
        _native_document_local_reason(
            recovered.body,
            _mapping(basis.record(), "basis"),
            expected_name=None,
            expected_docstatus=0,
        )
        is not None
    ):
        raise _AdmissionError("INSERT_REQUEST_INVALID")
    if recovered.bill_digest != basis.bill_digest:
        raise _AdmissionError("INSERT_REQUEST_INVALID")
    return recovered


def _native_document_local_reason(
    document: Mapping[str, object],
    basis: Mapping[str, object],
    *,
    expected_name: str | None,
    expected_docstatus: int,
) -> str | None:
    """Check only local identity fields; shared validation owns financial semantics."""

    if document.get("doctype") != "Purchase Invoice":
        return "doctype"
    name = document.get("name")
    if expected_name is None:
        if name not in (None, ""):
            return "name"
    elif name != expected_name:
        return "name"
    if type(document.get("docstatus")) is not int or document["docstatus"] != expected_docstatus:
        return "docstatus"
    for field_name in ("company", "supplier", "bill_no", "bill_date"):
        if document.get(field_name) != basis.get(
            field_name if field_name != "bill_no" else "bill_reference"
        ):
            return field_name
    rows = document.get("items")
    if not isinstance(rows, (list, tuple)) or len(rows) != 1 or not isinstance(rows[0], Mapping):
        return "items"
    row = rows[0]
    for field_name, basis_field in (
        ("purchase_order", "purchase_order"),
        ("po_detail", "purchase_order_item"),
        ("purchase_receipt", "purchase_receipt"),
        ("pr_detail", "purchase_receipt_item"),
    ):
        if row.get(field_name) != basis.get(basis_field):
            return field_name
    return None


def _make_insert_binding(
    intent_id: str, intent_version: int, envelope: _Envelope
) -> dict[str, object] | None:
    request = envelope.insert_request
    if request is None:
        return None
    binding: dict[str, object] = {
        "intent_id": intent_id,
        "intent_version": intent_version,
        "commercial_version": envelope.commercial_version,
        "bill_digest": request.bill_digest,
        "request": request.record(),
    }
    binding["binding_digest"] = _digest(binding)
    return binding


def _stored_insert_binding(
    row: sqlite3.Row,
) -> tuple[dict[str, object], NativeInsertRequest]:
    raw = row["insert_binding_json"]
    if raw is None:
        raise _AdmissionError("INSERT_REQUEST_UNBOUND")
    try:
        binding = _decoded_mapping(cast(str, raw), "insert binding")
        expected_fields = {
            "intent_id",
            "intent_version",
            "commercial_version",
            "bill_digest",
            "request",
            "binding_digest",
        }
        if set(binding) != expected_fields:
            raise ValueError("insert binding fields")
        request_record = binding["request"]
        if not isinstance(request_record, Mapping):
            raise ValueError("insert binding request")
        request = NativeInsertRequest.from_record(cast(Mapping[str, object], request_record))
        core = {key: value for key, value in binding.items() if key != "binding_digest"}
        if binding["binding_digest"] != _digest(core):
            raise ValueError("insert binding digest")
        if (
            binding["intent_id"] != row["intent_id"]
            or type(binding["intent_version"]) is not int
            or binding["intent_version"] != row["intent_version"]
            or binding["commercial_version"] != row["commercial_version"]
            or binding["bill_digest"] != request.bill_digest
        ):
            raise ValueError("insert binding context")
        if _encoded(request.record()) != _encoded(request_record):
            raise ValueError("insert binding request record")
        basis = _decoded_mapping(cast(str, row["basis_json"]), "basis")
        preview = _decoded_mapping(cast(str, row["preview_json"]), "preview")
        if (
            preview.get("bill_digest") != request.bill_digest
            or _native_document_local_reason(
                request.body, basis, expected_name=None, expected_docstatus=0
            )
            is not None
        ):
            raise ValueError("insert binding local identity")
    except (RuntimeError, TypeError, ValueError, KeyError):
        raise _AdmissionError("INSERT_REQUEST_INVALID") from None
    return binding, request


def _insert_marker_matches(
    row: sqlite3.Row,
    binding: Mapping[str, object],
    request: NativeInsertRequest,
) -> bool:
    raw = row["insert_payload_json"]
    attempt_id = row["insert_attempt_id"]
    if raw is None or not isinstance(attempt_id, str) or not attempt_id:
        return False
    try:
        payload = _decoded_mapping(cast(str, raw), "insert payload")
        return (
            payload.get("attempt_kind") == "INSERT"
            and payload.get("intent_id") == row["intent_id"]
            and payload.get("intent_version") == row["intent_version"]
            and payload.get("attempt_id") == attempt_id
            and isinstance(payload.get("native_request"), Mapping)
            and isinstance(payload.get("request_binding"), Mapping)
            and _encoded(payload["native_request"]) == _encoded(request.record())
            and _encoded(payload["request_binding"]) == _encoded(binding)
        )
    except (RuntimeError, TypeError, ValueError):
        return False


def _draft_acknowledgement_envelope(
    row: sqlite3.Row,
    binding: Mapping[str, object],
    acknowledgement: NativeDraftAcknowledgement,
) -> dict[str, object]:
    attempt_id = row["insert_attempt_id"]
    if not isinstance(attempt_id, str) or not attempt_id:
        raise ValueError("insert attempt id is missing")
    binding_digest = binding.get("binding_digest")
    if not isinstance(binding_digest, str):
        raise ValueError("insert binding digest is missing")
    return {
        "attempt_id": attempt_id,
        "intent_version": row["intent_version"],
        "insert_binding_digest": binding_digest,
        "acknowledgement": acknowledgement.record(),
    }


def _stored_draft_acknowledgement(
    row: sqlite3.Row,
) -> tuple[dict[str, object], NativeInsertRequest, NativeDraftAcknowledgement]:
    raw = row["draft_readback_json"]
    if raw is None:
        raise _AdmissionError("DRAFT_ACKNOWLEDGEMENT_REQUIRED")
    try:
        envelope = _decoded_mapping(cast(str, raw), "draft acknowledgement")
    except RuntimeError:
        raise _AdmissionError("DRAFT_ACKNOWLEDGEMENT_INVALID") from None
    if "acknowledgement" not in envelope:
        raise _AdmissionError("DRAFT_ACKNOWLEDGEMENT_REQUIRED")
    try:
        expected_fields = {
            "attempt_id",
            "intent_version",
            "insert_binding_digest",
            "acknowledgement",
        }
        if set(envelope) != expected_fields:
            raise ValueError("draft acknowledgement fields")
        acknowledgement_record = envelope["acknowledgement"]
        if not isinstance(acknowledgement_record, Mapping):
            raise ValueError("draft acknowledgement record")
        acknowledgement = NativeDraftAcknowledgement.from_record(
            cast(Mapping[str, object], acknowledgement_record)
        )
        binding, request = _stored_insert_binding(row)
        if (
            envelope["attempt_id"] != row["insert_attempt_id"]
            or envelope["intent_version"] != row["intent_version"]
            or envelope["insert_binding_digest"] != binding["binding_digest"]
            or acknowledgement.insert_body_digest != request.body_digest
            or acknowledgement.draft_name != row["draft_name"]
            or not _insert_marker_matches(row, binding, request)
        ):
            raise ValueError("draft acknowledgement context")
        basis = _decoded_mapping(cast(str, row["basis_json"]), "basis")
        if (
            _native_document_local_reason(
                acknowledgement.document,
                basis,
                expected_name=acknowledgement.draft_name,
                expected_docstatus=0,
            )
            is not None
        ):
            raise ValueError("draft acknowledgement local identity")
    except _AdmissionError:
        raise
    except (RuntimeError, TypeError, ValueError, KeyError):
        raise _AdmissionError("DRAFT_ACKNOWLEDGEMENT_INVALID") from None
    return binding, request, acknowledgement


def _submit_marker_matches(
    row: sqlite3.Row,
    binding: Mapping[str, object],
    acknowledgement: NativeDraftAcknowledgement,
    request: NativeSubmitRequest,
) -> bool:
    raw = row["submit_payload_json"]
    attempt_id = row["submit_attempt_id"]
    if raw is None or not isinstance(attempt_id, str) or not attempt_id:
        return False
    try:
        payload = _decoded_mapping(cast(str, raw), "submit payload")
        return (
            payload.get("attempt_kind") == "SUBMIT"
            and payload.get("intent_id") == row["intent_id"]
            and payload.get("intent_version") == row["intent_version"]
            and payload.get("attempt_id") == attempt_id
            and isinstance(payload.get("native_request"), Mapping)
            and isinstance(payload.get("request_binding"), Mapping)
            and isinstance(payload.get("insert_acknowledgement"), Mapping)
            and _encoded(payload["native_request"]) == _encoded(request.record())
            and _encoded(payload["request_binding"]) == _encoded(binding)
            and _encoded(payload["insert_acknowledgement"]) == _encoded(acknowledgement.record())
        )
    except (RuntimeError, TypeError, ValueError):
        return False


def _expired(row: sqlite3.Row, now: str) -> bool:
    expires_at = row["approval_expires_at"]
    return expires_at is not None and _parse_time(cast(str, expires_at)) <= _parse_time(now)


def _phase(row: sqlite3.Row) -> Phase:
    if row["submitted_readback_json"] is not None:
        return "SUBMITTED_READBACK_ADMITTED"
    if row["submit_attempted_at"] is not None:
        return "SUBMIT_ATTEMPTED"
    if row["draft_readback_json"] is not None:
        return "DRAFT_READBACK_ADMITTED"
    if row["insert_attempted_at"] is not None:
        return "INSERT_ATTEMPTED"
    if row["approval_token_hash"] is not None:
        return "APPROVED"
    return "PREPARED"


def _authority_status(row: sqlite3.Row, now: str | None) -> AuthorityStatus:
    if _sqlite_true(row["effect_conflict"]):
        return "CONFLICT_HOLD"
    if row["refused_at"] is not None:
        return "REFUSED"
    if _sqlite_true(row["source_changed"]):
        return "STALE_SOURCE"
    if row["approval_token_hash"] is None:
        return "PENDING_APPROVAL"
    timestamp = now or _time(None)
    if _expired(row, timestamp):
        return "EXPIRED"
    return "APPROVED"
