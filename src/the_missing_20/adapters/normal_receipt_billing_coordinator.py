"""Narrow transport coordinator for one accepted normal-receipt bill intent.

The coordinator composes the already-admitted source/context, journal, and
native request boundaries.  It owns no approval issuance, provider search
ownership, or financial-closure decision.  Every external write follows a
journal marker, and every recovery path is read-only.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, cast
from urllib.parse import quote

from the_missing_20.adapters.normal_receipt_billing_context import (
    NormalReceiptBillingContext,
    build_normal_receipt_billing_context,
)
from the_missing_20.adapters.normal_receipt_billing_journal import (
    AttemptClaim,
    BillingIntentJournal,
    IntentSnapshot,
    PrepareResult,
    ReadbackAdmission,
    ReadbackObservation,
)
from the_missing_20.adapters.normal_receipt_billing_native_request import (
    NativeDraftAcknowledgement,
    NativeInsertRequest,
    NativeSubmitRequest,
    validate_native_draft_acknowledgement,
    validate_native_submitted_readback,
)
from the_missing_20.adapters.normal_receipt_billing_preview import SyntheticBillingBasis
from the_missing_20.adapters.normal_receipt_billing_source import (
    ERPRequest,
    NormalReceiptBillingSourceRead,
    NormalReceiptBillingSourceReader,
)

_PURCHASE_INVOICE_PATH = "/api/resource/Purchase%20Invoice"

BasisResolver = Callable[[str], SyntheticBillingBasis]
ReaderFactory = Callable[[ERPRequest], NormalReceiptBillingSourceReader]
_DirectKind = Literal["NO_HIT", "UNKNOWN"]


def _canonical(value: object) -> object:
    """Make only strict JSON material comparable and journal-observable."""

    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("coordinator mapping keys must be strings")
            result[key] = _canonical(item)
        return result
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("coordinator values must be finite")
        return value
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    raise ValueError(f"unsupported coordinator value: {type(value).__name__}")


def _same_json(left: object, right: object) -> bool:
    try:
        return json.dumps(_canonical(left), sort_keys=True, separators=(",", ":")) == json.dumps(
            _canonical(right), sort_keys=True, separators=(",", ":")
        )
    except (TypeError, ValueError):
        return False


def _nonempty_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


@dataclass(frozen=True, slots=True)
class CoordinatorPrepareResult:
    """The fresh read context and, only when it is ready, journal preparation."""

    context: NormalReceiptBillingContext | None
    prepared: PrepareResult | None
    reason: str | None


@dataclass(frozen=True, slots=True)
class CoordinatorOperationResult:
    """One bounded operation result; a claim never establishes provider truth."""

    snapshot: IntentSnapshot
    context: NormalReceiptBillingContext | None
    claim: AttemptClaim | None
    admission: ReadbackAdmission | None
    reason: str | None


@dataclass(frozen=True, slots=True)
class _DirectRead:
    document: Mapping[str, object] | None
    kind: _DirectKind | None
    detail: str | None


class NormalReceiptBillingCoordinator:
    """Compose the fixed source, journal, and native request contracts.

    ``resolve_basis`` is trusted application code: a caller provides only a
    case identifier, and the coordinator checks its result against the
    journal's frozen basis before it reads or marks an existing intent.
    """

    def __init__(
        self,
        journal: BillingIntentJournal,
        resolve_basis: BasisResolver,
        request: ERPRequest,
        *,
        reader_factory: ReaderFactory = NormalReceiptBillingSourceReader,
    ) -> None:
        self._journal = journal
        self._resolve_basis = resolve_basis
        self._request = request
        self._reader_factory = reader_factory

    def prepare(self, case_id: str) -> CoordinatorPrepareResult:
        """Read one current source observation and prepare its immutable envelope."""

        basis = self._new_basis(case_id)
        if basis is None:
            return CoordinatorPrepareResult(None, None, "BASIS_RESOLUTION_FAILED")
        try:
            source_read = self._read(basis)
            context = build_normal_receipt_billing_context(basis, source_read)
        except Exception as error:
            return CoordinatorPrepareResult(None, None, self._error_reason("SOURCE_READ", error))
        if not context.ready:
            return CoordinatorPrepareResult(
                context, None, context.hold_reason or "CONTEXT_NOT_READY"
            )
        assert context.commercial_source is not None
        assert context.source_insert_request is not None
        prepared = self._journal.prepare(
            basis,
            context.preview,
            context.commercial_source,
            insert_request=context.source_insert_request,
        )
        return CoordinatorPrepareResult(context, prepared, prepared.reason)

    def insert(
        self,
        intent_id: str,
        *,
        case_id: str,
        manager_id: str,
        approval_token: str,
        worker_id: str,
        now: datetime | None = None,
    ) -> CoordinatorOperationResult:
        """Mark and make the one frozen insert, admitting only its own response."""

        snapshot, basis, reason = self._intent_basis(intent_id, case_id)
        if basis is None:
            return self._result(snapshot, reason=reason)
        if not _nonempty_text(manager_id):
            return self._result(snapshot, reason="MANAGER_INVALID")
        if not _nonempty_text(worker_id):
            return self._result(snapshot, reason="WORKER_INVALID")
        if not isinstance(approval_token, str):
            return self._result(snapshot, reason="APPROVAL_TOKEN_INVALID")
        if snapshot.insert_attempted:
            # A lost insert acknowledgement never authorizes a business-field
            # search or another insert attempt.
            return self._result(snapshot, reason="INSERT_ALREADY_ATTEMPTED")

        try:
            request = self._journal.bound_insert_request(intent_id)
            acknowledgement = self._journal.acknowledged_draft(intent_id)
        except (RuntimeError, ValueError) as error:
            return self._result(snapshot, reason=self._error_reason("JOURNAL_EVIDENCE", error))
        if request is None:
            return self._result(snapshot, reason="INSERT_REQUEST_REQUIRED")
        if acknowledgement is not None:
            return self._result(snapshot, reason="INSERT_ACKNOWLEDGEMENT_ALREADY_PRESENT")

        source_read, context, blocked = self._ready_context(
            intent_id,
            snapshot,
            basis,
            request=request,
            stage="insert",
            now=now,
        )
        if blocked is not None:
            return blocked
        assert source_read is not None and context is not None

        claim = self._journal.claim_insert(
            intent_id,
            case_id=case_id,
            manager_id=manager_id,
            approval_token=approval_token,
            worker_id=worker_id,
            now=now,
        )
        if not claim.granted:
            return self._result(
                self._journal.get(intent_id), context=context, claim=claim, reason=claim.reason
            )
        marked_request = self._marked_insert_request(claim, request)
        if marked_request is None:
            return self._hold(
                intent_id,
                snapshot,
                "UNKNOWN",
                source_read=source_read,
                context=context,
                claim=claim,
                stage="insert_marker",
                detail="INSERT_MARKER_REQUEST_INVALID",
                now=now,
            )

        try:
            response = self._request(
                marked_request.path,
                method=marked_request.method,
                payload=marked_request.record()["body"],
            )
        except Exception as error:
            return self._hold(
                intent_id,
                snapshot,
                "UNKNOWN",
                source_read=source_read,
                context=context,
                claim=claim,
                stage="insert_response",
                detail=self._error_reason("INSERT_TRANSPORT", error),
                now=now,
            )

        document = self._response_data(response)
        if document is None:
            return self._hold(
                intent_id,
                snapshot,
                "UNKNOWN",
                source_read=source_read,
                context=context,
                claim=claim,
                stage="insert_response",
                detail="INSERT_RESPONSE_MALFORMED",
                insert_response=self._insert_response_audit(response),
                now=now,
            )
        try:
            purchase_order, purchase_receipt = self._parents(source_read)
            acknowledgement = validate_native_draft_acknowledgement(
                basis,
                purchase_order=purchase_order,
                purchase_receipt=purchase_receipt,
                insert_request=marked_request,
                document=document,
            )
        except (TypeError, ValueError) as error:
            return self._hold(
                intent_id,
                snapshot,
                "UNKNOWN",
                source_read=source_read,
                context=context,
                claim=claim,
                stage="insert_acknowledgement",
                detail=self._error_reason("INSERT_ACKNOWLEDGEMENT", error),
                insert_response=self._insert_response_audit(response),
                now=now,
            )

        admission = self._journal.admit_insert_acknowledgement(intent_id, acknowledgement)
        return self._result(
            admission.snapshot,
            context=context,
            claim=claim,
            admission=admission,
            reason=admission.reason,
        )

    def submit(
        self,
        intent_id: str,
        *,
        case_id: str,
        manager_id: str,
        worker_id: str,
        now: datetime | None = None,
    ) -> CoordinatorOperationResult:
        """Mark one submit and always reconcile its exact known name afterwards."""

        snapshot, basis, reason = self._intent_basis(intent_id, case_id)
        if basis is None:
            return self._result(snapshot, reason=reason)
        if not _nonempty_text(manager_id):
            return self._result(snapshot, reason="MANAGER_INVALID")
        if not _nonempty_text(worker_id):
            return self._result(snapshot, reason="WORKER_INVALID")
        if snapshot.submit_attempted:
            return self._reconcile(intent_id, snapshot, basis, now=now)

        try:
            request = self._journal.bound_insert_request(intent_id)
            acknowledgement = self._journal.acknowledged_draft(intent_id)
        except (RuntimeError, ValueError) as error:
            return self._result(snapshot, reason=self._error_reason("JOURNAL_EVIDENCE", error))
        if request is None:
            return self._result(snapshot, reason="INSERT_REQUEST_REQUIRED")
        if acknowledgement is None:
            return self._result(snapshot, reason="DRAFT_ACKNOWLEDGEMENT_REQUIRED")

        source_read, context, blocked = self._ready_context(
            intent_id,
            snapshot,
            basis,
            request=request,
            acknowledgement=acknowledgement,
            stage="submit",
            now=now,
        )
        if blocked is not None:
            return blocked
        assert source_read is not None and context is not None

        claim = self._journal.claim_submit(
            intent_id,
            case_id=case_id,
            manager_id=manager_id,
            worker_id=worker_id,
            now=now,
        )
        if not claim.granted:
            return self._result(
                self._journal.get(intent_id), context=context, claim=claim, reason=claim.reason
            )

        marked_request = self._marked_submit_request(claim, acknowledgement)
        transport_reason: str | None = None
        if marked_request is None:
            transport_reason = "SUBMIT_MARKER_REQUEST_INVALID"
        else:
            try:
                # The journal-marked full draft is sent without remapping or mutation.
                self._request(
                    marked_request.path,
                    method=marked_request.method,
                    payload=marked_request.record()["body"],
                )
            except Exception as error:
                transport_reason = self._error_reason("SUBMIT_TRANSPORT", error)

        reconciled = self._reconcile(
            intent_id,
            self._journal.get(intent_id),
            basis,
            transport_reason=transport_reason,
            now=now,
        )
        return CoordinatorOperationResult(
            snapshot=reconciled.snapshot,
            context=context,
            claim=claim,
            admission=reconciled.admission,
            # A direct validated readback resolves an otherwise lost submit ACK.
            # When it cannot do so, its NO_HIT/UNKNOWN reason is more useful than
            # the transient transport symptom and retains the read-only fence.
            reason=reconciled.reason,
        )

    def reconcile(
        self,
        intent_id: str,
        *,
        case_id: str,
        now: datetime | None = None,
    ) -> CoordinatorOperationResult:
        """Read back only the known acknowledged name after a submit marker."""

        snapshot, basis, reason = self._intent_basis(intent_id, case_id)
        if basis is None:
            return self._result(snapshot, reason=reason)
        return self._reconcile(intent_id, snapshot, basis, now=now)

    def _new_basis(self, case_id: str) -> SyntheticBillingBasis | None:
        if not _nonempty_text(case_id):
            return None
        try:
            basis = self._resolve_basis(case_id)
        except Exception:
            return None
        if not isinstance(basis, SyntheticBillingBasis) or basis.case_id != case_id:
            return None
        return basis

    def _intent_basis(
        self, intent_id: str, case_id: str
    ) -> tuple[IntentSnapshot, SyntheticBillingBasis | None, str | None]:
        snapshot = self._journal.get(intent_id)
        if case_id != snapshot.case_id:
            return snapshot, None, "CASE_MISMATCH"
        basis = self._new_basis(snapshot.case_id)
        if basis is None or not _same_json(basis.record(), snapshot.frozen_basis):
            return snapshot, None, "FROZEN_BASIS_MISMATCH"
        return snapshot, basis, None

    def _read(self, basis: SyntheticBillingBasis) -> NormalReceiptBillingSourceRead:
        # A new reader deliberately resets source timing/manifest state for each operation.
        return self._reader_factory(self._request).read(basis)

    def _ready_context(
        self,
        intent_id: str,
        snapshot: IntentSnapshot,
        basis: SyntheticBillingBasis,
        *,
        request: NativeInsertRequest,
        acknowledgement: NativeDraftAcknowledgement | None = None,
        stage: str,
        now: datetime | None,
    ) -> tuple[
        NormalReceiptBillingSourceRead | None,
        NormalReceiptBillingContext | None,
        CoordinatorOperationResult | None,
    ]:
        """Build the same-observation context and record a sticky pre-write hold."""

        try:
            source_read = self._read(basis)
        except Exception as error:
            return (
                None,
                None,
                self._hold(
                    intent_id,
                    snapshot,
                    "UNKNOWN",
                    source_read=None,
                    stage=f"{stage}_source_read",
                    detail=self._error_reason("SOURCE_READ", error),
                    now=now,
                ),
            )
        direct: _DirectRead | None = None
        if acknowledgement is not None:
            direct = self._direct_get(acknowledgement.draft_name)
            if direct.kind is not None:
                return (
                    source_read,
                    None,
                    self._hold(
                        intent_id,
                        snapshot,
                        direct.kind,
                        source_read=source_read,
                        stage=f"{stage}_known_draft_read",
                        detail=direct.detail or "DIRECT_DRAFT_READ_FAILED",
                        now=now,
                    ),
                )
        try:
            context = build_normal_receipt_billing_context(
                basis,
                source_read,
                stored_insert_request=request,
                acknowledgement=acknowledgement,
                direct_known_document=None if direct is None else direct.document,
            )
        except Exception as error:
            return (
                source_read,
                None,
                self._hold(
                    intent_id,
                    snapshot,
                    "UNKNOWN",
                    source_read=source_read,
                    stage=f"{stage}_source_context",
                    detail=self._error_reason("SOURCE_CONTEXT", error),
                    now=now,
                ),
            )
        if not context.ready:
            return (
                source_read,
                context,
                self._hold(
                    intent_id,
                    snapshot,
                    "UNKNOWN",
                    source_read=source_read,
                    context=context,
                    stage=f"{stage}_context",
                    detail=context.hold_reason or "CONTEXT_NOT_READY",
                    now=now,
                ),
            )
        assert context.commercial_source is not None
        refreshed = self._journal.refresh_source(intent_id, context.commercial_source, now=now)
        if refreshed.snapshot.source_changed:
            return (
                source_read,
                context,
                self._result(
                    refreshed.snapshot,
                    context=context,
                    reason="COMMERCIAL_SOURCE_CHANGED",
                ),
            )
        return source_read, context, None

    def _reconcile(
        self,
        intent_id: str,
        snapshot: IntentSnapshot,
        basis: SyntheticBillingBasis,
        *,
        transport_reason: str | None = None,
        now: datetime | None,
    ) -> CoordinatorOperationResult:
        """Validate a submitted direct GET without running draft eligibility again."""

        if not snapshot.submit_attempted:
            return self._result(snapshot, reason="SUBMIT_ATTEMPT_REQUIRED")
        try:
            acknowledgement = self._journal.acknowledged_draft(intent_id)
        except (RuntimeError, ValueError) as error:
            return self._result(snapshot, reason=self._error_reason("JOURNAL_EVIDENCE", error))
        if acknowledgement is None:
            return self._result(snapshot, reason="DRAFT_ACKNOWLEDGEMENT_REQUIRED")
        try:
            source_read = self._read(basis)
        except Exception as error:
            # A submit marker requires an exact-name GET even when fresh parent
            # collection failed.  Its document remains inadmissible without
            # current PO/PR validation.
            direct = self._direct_get(acknowledgement.draft_name)
            return self._hold(
                intent_id,
                snapshot,
                "UNKNOWN",
                source_read=None,
                direct_document=direct.document,
                stage="reconcile_source",
                detail=self._details(
                    transport_reason,
                    self._error_reason("SOURCE_READ", error),
                    direct.detail,
                ),
                now=now,
            )
        direct = self._direct_get(acknowledgement.draft_name)
        if direct.kind is not None:
            return self._hold(
                intent_id,
                snapshot,
                direct.kind,
                source_read=source_read,
                stage="submitted_direct_read",
                detail=self._details(
                    transport_reason,
                    direct.detail or "SUBMITTED_DIRECT_READ_FAILED",
                ),
                now=now,
            )
        assert direct.document is not None
        try:
            purchase_order, purchase_receipt = self._parents(source_read)
            proof = validate_native_submitted_readback(
                basis,
                purchase_order=purchase_order,
                purchase_receipt=purchase_receipt,
                draft=acknowledgement,
                document=direct.document,
            )
        except (TypeError, ValueError) as error:
            return self._hold(
                intent_id,
                snapshot,
                "UNKNOWN",
                source_read=source_read,
                direct_document=direct.document,
                stage="submitted_validation",
                detail=self._details(
                    transport_reason,
                    self._error_reason("SUBMITTED_READBACK", error),
                ),
                now=now,
            )
        # This neutral journal event retains the complete current source and
        # exact direct GET that validated the proof.  It is deliberately not a
        # commercial refresh: the acknowledged PI belongs in raw source, and
        # observing it cannot alter readback state or grant proof authority.
        admission = self._journal.admit_submitted_readback(
            intent_id,
            proof,
            audit_evidence=self._submitted_readback_audit(
                source_read,
                direct.document,
                transport_reason=transport_reason,
            ),
        )
        return self._result(admission.snapshot, admission=admission, reason=admission.reason)

    def _direct_get(self, name: str) -> _DirectRead:
        try:
            response = self._request(
                f"{_PURCHASE_INVOICE_PATH}/{quote(name, safe='')}",
                method="GET",
            )
        except Exception as error:
            return _DirectRead(None, "UNKNOWN", self._error_reason("DIRECT_GET", error))
        if not isinstance(response, Mapping) or "data" not in response:
            return _DirectRead(None, "UNKNOWN", "DIRECT_GET_MALFORMED")
        data = response["data"]
        if data is None:
            return _DirectRead(None, "NO_HIT", "DIRECT_GET_NO_HIT")
        if not isinstance(data, Mapping):
            return _DirectRead(None, "UNKNOWN", "DIRECT_GET_MALFORMED")
        return _DirectRead(cast(Mapping[str, object], data), None, None)

    def _marked_insert_request(
        self, claim: AttemptClaim, stored: NativeInsertRequest
    ) -> NativeInsertRequest | None:
        if (
            claim.attempt_kind != "INSERT"
            or not _nonempty_text(claim.attempt_id)
            or not isinstance(claim.payload, Mapping)
            or claim.payload.get("attempt_kind") != "INSERT"
            or claim.payload.get("attempt_id") != claim.attempt_id
        ):
            return None
        raw = claim.payload.get("native_request")
        if not isinstance(raw, Mapping):
            return None
        try:
            marked = NativeInsertRequest.from_record(cast(Mapping[str, object], raw))
        except (TypeError, ValueError):
            return None
        if not _same_json(raw, marked.record()) or not _same_json(marked.record(), stored.record()):
            return None
        return marked

    def _marked_submit_request(
        self, claim: AttemptClaim, acknowledgement: NativeDraftAcknowledgement
    ) -> NativeSubmitRequest | None:
        if (
            claim.attempt_kind != "SUBMIT"
            or not _nonempty_text(claim.attempt_id)
            or not isinstance(claim.payload, Mapping)
            or claim.payload.get("attempt_kind") != "SUBMIT"
            or claim.payload.get("attempt_id") != claim.attempt_id
        ):
            return None
        try:
            request = NativeSubmitRequest.from_draft(acknowledgement)
        except (TypeError, ValueError):
            return None
        raw = claim.payload.get("native_request")
        if not isinstance(raw, Mapping) or not _same_json(raw, request.record()):
            return None
        return request

    @staticmethod
    def _response_data(response: object) -> Mapping[str, object] | None:
        if not isinstance(response, Mapping) or "data" not in response:
            return None
        data = response["data"]
        return cast(Mapping[str, object], data) if isinstance(data, Mapping) else None

    @staticmethod
    def _insert_response_audit(response: object) -> Mapping[str, object]:
        """Wrap the decoded response without treating any of it as provider proof."""

        return {"envelope": response}

    @staticmethod
    def _parents(
        source_read: NormalReceiptBillingSourceRead,
    ) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
        if not isinstance(source_read.purchase_order, Mapping):
            raise ValueError("current purchase order is malformed")
        if not isinstance(source_read.purchase_receipt, Mapping):
            raise ValueError("current purchase receipt is malformed")
        return (
            cast(Mapping[str, Any], source_read.purchase_order),
            cast(Mapping[str, Any], source_read.purchase_receipt),
        )

    def _record(
        self,
        intent_id: str,
        kind: _DirectKind,
        observation: ReadbackObservation,
        *,
        now: datetime | None,
    ) -> IntentSnapshot:
        if kind == "NO_HIT":
            return self._journal.record_no_hit(intent_id, observation, now=now)
        return self._journal.record_unknown(intent_id, observation, now=now)

    def _hold(
        self,
        intent_id: str,
        snapshot: IntentSnapshot,
        kind: _DirectKind,
        *,
        source_read: NormalReceiptBillingSourceRead | None,
        stage: str,
        detail: str,
        context: NormalReceiptBillingContext | None = None,
        direct_document: Mapping[str, object] | None = None,
        insert_response: Mapping[str, object] | None = None,
        claim: AttemptClaim | None = None,
        now: datetime | None,
    ) -> CoordinatorOperationResult:
        """Persist one read-only hold with its source or fallback observation."""

        observation = (
            self._fallback_observation(snapshot, stage, detail, direct_document)
            if source_read is None
            else self._observation(
                kind,
                source_read,
                context=context,
                direct_document=direct_document,
                insert_response=insert_response,
                stage=stage,
                reason=detail,
            )
        )
        recorded = self._record(intent_id, kind, observation, now=now)
        return self._result(recorded, context=context, claim=claim, reason=detail)

    @staticmethod
    def _observation(
        kind: _DirectKind,
        source_read: NormalReceiptBillingSourceRead,
        *,
        context: NormalReceiptBillingContext | None = None,
        direct_document: Mapping[str, object] | None = None,
        insert_response: Mapping[str, object] | None = None,
        stage: str,
        reason: str,
    ) -> ReadbackObservation:
        if context is not None:
            evidence: object = context.audit.record()
            if insert_response is not None:
                assert isinstance(evidence, dict)
                evidence["insert_response"] = insert_response
        else:
            evidence = NormalReceiptBillingCoordinator._raw_source_evidence(
                source_read,
                direct_document=direct_document,
                insert_response=insert_response,
            )
        return ReadbackObservation(
            kind=kind,
            audit_snapshot_digest=source_read.snapshot_digest,
            observed_at=source_read.observed_at,
            details={"stage": stage, "reason": reason, "evidence": evidence},
        )

    @staticmethod
    def _raw_source_evidence(
        source_read: NormalReceiptBillingSourceRead,
        *,
        direct_document: Mapping[str, object] | None = None,
        insert_response: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        """Return strict-JSON source material shared by holds and successful reads."""

        return {
            "source_read": {
                "purchase_order": source_read.purchase_order,
                "purchase_receipt": source_read.purchase_receipt,
                "mapped_invoice": source_read.mapped_invoice,
                "related_documents_read": source_read.related_documents_read,
                "evidence_manifest": source_read.evidence_manifest,
                "observed_at": source_read.observed_at,
                "snapshot_digest": source_read.snapshot_digest,
                "preview": source_read.preview.record(),
            },
            "direct_known_document": direct_document,
            "insert_response": insert_response,
        }

    @classmethod
    def _submitted_readback_audit(
        cls,
        source_read: NormalReceiptBillingSourceRead,
        direct_document: Mapping[str, object],
        *,
        transport_reason: str | None,
    ) -> dict[str, object]:
        return {
            "stage": "submitted_readback_observation",
            "reason": cls._details(transport_reason, "SUBMITTED_READBACK_OBSERVED"),
            **cls._raw_source_evidence(source_read, direct_document=direct_document),
        }

    @staticmethod
    def _fallback_observation(
        snapshot: IntentSnapshot,
        stage: str,
        reason: str,
        direct_document: Mapping[str, object] | None,
    ) -> ReadbackObservation:
        return ReadbackObservation(
            kind="UNKNOWN",
            audit_snapshot_digest=snapshot.audit_snapshot_digest,
            observed_at=datetime.now(UTC).isoformat(),
            details={
                "stage": stage,
                "reason": reason,
                "direct_known_document": direct_document,
            },
        )

    @staticmethod
    def _details(*parts: str | None) -> str:
        return ";".join(part for part in parts if part) or "RECONCILIATION_UNKNOWN"

    @staticmethod
    def _error_reason(prefix: str, error: Exception) -> str:
        return f"{prefix}_{type(error).__name__}"

    @staticmethod
    def _result(
        snapshot: IntentSnapshot,
        *,
        context: NormalReceiptBillingContext | None = None,
        claim: AttemptClaim | None = None,
        admission: ReadbackAdmission | None = None,
        reason: str | None = None,
    ) -> CoordinatorOperationResult:
        return CoordinatorOperationResult(snapshot, context, claim, admission, reason)
