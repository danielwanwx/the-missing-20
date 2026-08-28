"""Exact two-human authorization quorum for Authority B controlled effects."""

from __future__ import annotations

import json
import os
import uuid
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING

from the_missing_20.authority_b.models import (
    REQUIRED_AUTHORITY_ROLES,
    AttestationDecision,
    AuthorizationIntent,
    OperationalDecision,
    QuorumActionGrant,
    QuorumAttestation,
    QuorumResult,
    QuorumStatus,
    canonical_json,
    digest,
)
from the_missing_20.domain.errors import AuthorizationDenied
from the_missing_20.domain.execution import (
    ReleaseInvoiceParameters,
    RestartReceiptMessageParameters,
)
from the_missing_20.domain.models import ActionTool, HumanRole
from the_missing_20.ports.clock import Clock
from the_missing_20.ports.signer import Signer

if TYPE_CHECKING:
    from the_missing_20.authority_b.executor import AuthorityBControlledExecutor


class QuorumDenied(AuthorizationDenied):
    """A quorum intent, attestation, or Authority-B grant was rejected."""


class PrincipalDirectory:
    """Immutable trusted identity-to-role mapping used by the quorum service."""

    def __init__(self, assignments: dict[str, HumanRole]) -> None:
        if len(assignments) != len(set(assignments)):
            raise ValueError("trusted principal IDs must be unique")
        self._assignments = dict(assignments)

    def resolve(self, principal_id: str) -> HumanRole:
        try:
            return self._assignments[principal_id]
        except KeyError as exc:
            raise QuorumDenied("principal is not trusted for Authority-B quorum") from exc


def _now(clock: Clock | None, value: datetime | None = None) -> datetime:
    result = value or (clock.now() if clock is not None else datetime.now(UTC))
    if result.tzinfo is None or result.utcoffset() is None:
        raise QuorumDenied("quorum timestamp must be timezone-aware")
    return result


def _parameter_model(
    tool: ActionTool,
) -> type[RestartReceiptMessageParameters | ReleaseInvoiceParameters]:
    if tool is ActionTool.RESTART_RECEIPT_MESSAGE:
        return RestartReceiptMessageParameters
    return ReleaseInvoiceParameters


class QuorumAuthorizationService:
    """Thread-safe Authority-B quorum ledger with an optional durable snapshot.

    The JSON snapshot is deliberately a projection of the same immutable records
    used by the in-memory state machine.  Every state-changing operation writes the
    complete snapshot with an atomic replace, so a new process can reload an intent,
    both attestations, its grant, and its consumed execution identity.  The optional
    path is kept explicit: callers that do not provide one still get the deterministic
    in-memory ledger used by small unit tests.
    """

    def __init__(
        self,
        *,
        principals: PrincipalDirectory | dict[str, HumanRole],
        signer: Signer,
        clock: Clock | None = None,
        ttl: timedelta = timedelta(minutes=5),
        storage_path: Path | None = None,
    ) -> None:
        self.principals = (
            principals
            if isinstance(principals, PrincipalDirectory)
            else PrincipalDirectory(principals)
        )
        self.signer = signer
        self.clock = clock
        if ttl <= timedelta(0) or ttl > timedelta(minutes=5):
            raise ValueError("quorum intent TTL must be positive and no more than five minutes")
        self.ttl = ttl
        self.storage_path = storage_path
        self._lock = Lock()
        self._intents: dict[str, AuthorizationIntent] = {}
        self._attestations: dict[str, tuple[QuorumAttestation, ...]] = {}
        self._grants: dict[str, QuorumActionGrant] = {}
        self._consumed: dict[str, tuple[str, str]] = {}
        self._load()

    def _load(self) -> None:
        """Reload a previously persisted ledger, failing closed on corruption."""

        if self.storage_path is None or not self.storage_path.exists():
            return
        try:
            payload = json.loads(self.storage_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Authority-B quorum ledger must be a JSON object")
            if payload.get("schema_version") != "authority-b-quorum-ledger/v1":
                raise ValueError("unsupported Authority-B quorum ledger version")
            intents = tuple(
                AuthorizationIntent.model_validate_json(json.dumps(item))
                for item in payload.get("intents", ())
            )
            attestations_payload = payload.get("attestations", {})
            grants = tuple(
                QuorumActionGrant.model_validate_json(json.dumps(item))
                for item in payload.get("grants", ())
            )
            consumed_payload = payload.get("consumed", {})
            if not isinstance(attestations_payload, dict) or not isinstance(consumed_payload, dict):
                raise ValueError("Authority-B quorum ledger maps are malformed")
            attestations = {
                str(intent_id): tuple(
                    QuorumAttestation.model_validate_json(json.dumps(item)) for item in values
                )
                for intent_id, values in attestations_payload.items()
            }
            consumed = {
                str(intent_id): (
                    str(value["execution_id"]),
                    str(value["idempotency_key"]),
                )
                for intent_id, value in consumed_payload.items()
            }
        except (OSError, TypeError, ValueError, KeyError) as exc:
            raise QuorumDenied("Authority-B quorum ledger is unreadable") from exc
        self._intents = {item.intent_id: item for item in intents}
        self._attestations = {
            intent_id: attestations.get(intent_id, ()) for intent_id in self._intents
        }
        if set(attestations) - set(self._intents):
            raise QuorumDenied("Authority-B quorum ledger contains an unknown intent")
        self._grants = {item.intent_id: item for item in grants}
        if set(self._grants) - set(self._intents):
            raise QuorumDenied("Authority-B quorum ledger contains an unknown grant")
        for intent_id, values in self._attestations.items():
            intent = self._intents[intent_id]
            if any(
                item.intent_id != intent_id or item.intent_digest != intent.intent_digest
                for item in values
            ):
                raise QuorumDenied("Authority-B quorum ledger contains a cross-intent attestation")
        for intent_id, grant in self._grants.items():
            intent = self._intents[intent_id]
            if (
                grant.intent_id != intent_id
                or grant.intent_digest != intent.intent_digest
                or grant.decision_digest != intent.decision_digest
                or grant.case_id != intent.case_id
                or grant.trace_id != intent.trace_id
                or grant.case_version != intent.case_version
                or grant.tool is not intent.tool
                or grant.complete_parameters != intent.complete_parameters
                or grant.parameters_digest != intent.parameters_digest
                or grant.admitted_evidence_digest != intent.admitted_evidence_digest
            ):
                raise QuorumDenied("Authority-B quorum ledger grant binding is invalid")
            signature_payload = canonical_json(grant.model_dump(mode="json", exclude={"signature"}))
            if not self.signer.verify(signature_payload, grant.signature):
                raise QuorumDenied("Authority-B quorum ledger grant signature is invalid")
        self._consumed = consumed
        if set(self._consumed) - set(self._grants):
            raise QuorumDenied("Authority-B quorum ledger contains an unknown consumption")
        if any(
            self._intents[intent_id].status is not QuorumStatus.CONSUMED
            for intent_id in self._consumed
        ):
            raise QuorumDenied("Authority-B quorum ledger consumption status is invalid")

    def _persist_locked(self) -> None:
        if self.storage_path is None:
            return
        payload = {
            "schema_version": "authority-b-quorum-ledger/v1",
            "intents": [
                item.model_dump(mode="json")
                for item in sorted(self._intents.values(), key=lambda value: value.intent_id)
            ],
            "attestations": {
                intent_id: [item.model_dump(mode="json") for item in values]
                for intent_id, values in sorted(self._attestations.items())
            },
            "grants": [
                item.model_dump(mode="json")
                for item in sorted(self._grants.values(), key=lambda value: value.intent_id)
            ],
            "consumed": {
                intent_id: {
                    "execution_id": execution_id,
                    "idempotency_key": idempotency_key,
                }
                for intent_id, (execution_id, idempotency_key) in sorted(self._consumed.items())
            },
        }
        encoded = (
            json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
        ).encode("utf-8")
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.storage_path.with_name(f".{self.storage_path.name}.{uuid.uuid4().hex}.tmp")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                descriptor = -1
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.storage_path)
            directory_descriptor = os.open(self.storage_path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            with suppress(FileNotFoundError):
                temporary.unlink()

    def create_intent(
        self,
        *,
        decision: OperationalDecision,
        complete_parameters: RestartReceiptMessageParameters | ReleaseInvoiceParameters,
        admitted_evidence_digest: str,
        intent_id: str,
        created_at: datetime | None = None,
    ) -> AuthorizationIntent:
        if decision.eligibility.value != "PENDING_APPROVAL" or decision.allowed_action is None:
            raise QuorumDenied("only a deterministic pending-approval decision can create intent")
        if admitted_evidence_digest != decision.source_digest:
            raise QuorumDenied("intent evidence digest does not match deterministic decision")
        expected_type = _parameter_model(decision.allowed_action)
        if type(complete_parameters) is not expected_type:
            raise QuorumDenied("typed parameters do not match the deterministic action")
        timestamp = _now(self.clock, created_at)
        intent = AuthorizationIntent(
            intent_id=intent_id,
            case_id=decision.case_id,
            trace_id=decision.trace_id,
            case_version=decision.case_version,
            decision_digest=decision.decision_digest,
            tool=decision.allowed_action,
            complete_parameters=complete_parameters.model_dump(mode="json"),
            parameters_digest=digest(complete_parameters.model_dump(mode="json")),
            admitted_evidence_digest=admitted_evidence_digest,
            created_at=timestamp,
            expires_at=timestamp + self.ttl,
        )
        with self._lock:
            if intent_id in self._intents:
                raise QuorumDenied("authorization intent ID is already used")
            self._intents[intent_id] = intent
            self._attestations[intent_id] = ()
            self._persist_locked()
        return intent

    def get_intent(self, intent_id: str) -> AuthorizationIntent:
        with self._lock:
            try:
                return self._intents[intent_id]
            except KeyError as exc:
                raise QuorumDenied("unknown authorization intent") from exc

    def list_attestations(self, intent_id: str) -> tuple[QuorumAttestation, ...]:
        with self._lock:
            return self._attestations.get(intent_id, ())

    def get_grant(self, intent_id: str) -> QuorumActionGrant | None:
        with self._lock:
            return self._grants.get(intent_id)

    def _expire_if_needed(self, intent: AuthorizationIntent, at: datetime) -> AuthorizationIntent:
        if (
            intent.status
            in {
                QuorumStatus.OPEN,
                QuorumStatus.QUORUM_PENDING,
            }
            and at >= intent.expires_at
        ):
            expired = intent.model_copy(update={"status": QuorumStatus.EXPIRED})
            self._intents[intent.intent_id] = expired
            self._persist_locked()
            return expired
        return intent

    def attest(
        self,
        *,
        intent: AuthorizationIntent | str,
        principal_id: str,
        decision: AttestationDecision = AttestationDecision.APPROVED,
        attestation_id: str | None = None,
        approval_id: str | None = None,
        role: HumanRole | None = None,
        intent_digest: str | None = None,
        attested_at: datetime | None = None,
    ) -> QuorumResult:
        """Record one approval/rejection and return the resulting quorum state."""

        resolved = self.get_intent(intent) if isinstance(intent, str) else intent
        if isinstance(decision, str):
            decision = AttestationDecision(decision)
        if isinstance(role, str):
            role = HumanRole(role)
        timestamp = _now(self.clock, attested_at)
        with self._lock:
            stored = self._intents.get(resolved.intent_id)
            if stored is None or stored.intent_digest != resolved.intent_digest:
                raise QuorumDenied("authorization intent is stale or tampered")
            stored = self._expire_if_needed(stored, timestamp)
            if stored.status in {
                QuorumStatus.REJECTED,
                QuorumStatus.EXPIRED,
                QuorumStatus.GRANTED,
                QuorumStatus.CONSUMED,
            }:
                raise QuorumDenied("authorization intent is closed")
            if intent_digest is not None and intent_digest != stored.intent_digest:
                raise QuorumDenied("attestation intent digest does not match")
            trusted_role = self.principals.resolve(principal_id)
            if role is not None and role is not trusted_role:
                raise QuorumDenied("attestation role does not match trusted principal")
            observed_role = trusted_role
            for prior in self._attestations[stored.intent_id]:
                if prior.principal_id == principal_id or prior.role is observed_role:
                    raise QuorumDenied("duplicate quorum principal or role")
            generated_id = attestation_id or approval_id
            if not generated_id:
                raise QuorumDenied("attestation ID is required")
            if any(item.attestation_id == generated_id for item in self._all_attestations()):
                raise QuorumDenied("attestation ID is already used")
            attestation = QuorumAttestation(
                attestation_id=generated_id,
                intent_id=stored.intent_id,
                intent_digest=stored.intent_digest,
                principal_id=principal_id,
                role=observed_role,
                decision=decision,
                attested_at=timestamp,
            )
            if decision is AttestationDecision.REJECTED:
                self._attestations[stored.intent_id] = (
                    *self._attestations[stored.intent_id],
                    attestation,
                )
                closed = stored.model_copy(update={"status": QuorumStatus.REJECTED})
                self._intents[stored.intent_id] = closed
                self._persist_locked()
                return QuorumResult(
                    status=QuorumStatus.REJECTED,
                    intent=closed,
                    attestation=attestation,
                )
            attestations = (*self._attestations[stored.intent_id], attestation)
            self._attestations[stored.intent_id] = attestations
            if len(attestations) == 1:
                pending = stored.model_copy(update={"status": QuorumStatus.QUORUM_PENDING})
                self._intents[stored.intent_id] = pending
                self._persist_locked()
                return QuorumResult(
                    status=QuorumStatus.QUORUM_PENDING,
                    intent=pending,
                    attestation=attestation,
                )
            if (
                len(attestations) != 2
                or {item.role for item in attestations} != set(REQUIRED_AUTHORITY_ROLES)
                or len({item.principal_id for item in attestations}) != 2
            ):
                raise QuorumDenied("exactly one distinct operator and AP approver are required")
            grant = self._make_grant(stored, attestations, timestamp)
            self._grants[stored.intent_id] = grant
            granted = stored.model_copy(update={"status": QuorumStatus.GRANTED})
            self._intents[stored.intent_id] = granted
            self._persist_locked()
            return QuorumResult(
                status=QuorumStatus.GRANTED,
                intent=granted,
                attestation=attestation,
                grant=grant,
            )

    def ensure_execution_available(
        self,
        grant: QuorumActionGrant,
        *,
        execution_id: str,
        idempotency_key: str,
        at: datetime | None = None,
    ) -> None:
        """Atomically admit one execution identity for a granted quorum.

        A fresh grant is admitted while ``GRANTED``.  A consumed grant is admitted
        only for the exact same execution and idempotency pair, which is the replay
        path used after a crash or a client retry.  A different pair is denied and
        cannot create a second enterprise effect.
        """

        timestamp = _now(self.clock, at)
        with self._lock:
            stored = self._grants.get(grant.intent_id)
            intent = self._intents.get(grant.intent_id)
            if (
                stored is None
                or intent is None
                or stored.grant_digest != grant.grant_digest
                or stored.intent_digest != grant.intent_digest
            ):
                raise QuorumDenied("quorum grant is stale, unknown, or tampered")
            if timestamp >= stored.expires_at and grant.intent_id not in self._consumed:
                raise QuorumDenied("quorum grant is expired")
            if intent.status is QuorumStatus.CONSUMED:
                if self._consumed.get(grant.intent_id) != (execution_id, idempotency_key):
                    raise QuorumDenied("quorum grant was already consumed by another request")
                return
            if intent.status is not QuorumStatus.GRANTED:
                raise QuorumDenied("quorum grant is not available for execution")

    def mark_consumed(
        self,
        grant: QuorumActionGrant,
        *,
        execution_id: str,
        idempotency_key: str,
        at: datetime | None = None,
    ) -> None:
        """Persist the single successful execution identity for a quorum grant."""

        _now(self.clock, at)
        with self._lock:
            stored = self._grants.get(grant.intent_id)
            intent = self._intents.get(grant.intent_id)
            if (
                stored is None
                or intent is None
                or stored.grant_digest != grant.grant_digest
                or stored.intent_digest != grant.intent_digest
            ):
                raise QuorumDenied("quorum grant is stale, unknown, or tampered")
            existing = self._consumed.get(grant.intent_id)
            if existing is not None:
                if existing != (execution_id, idempotency_key):
                    raise QuorumDenied("quorum grant was already consumed by another request")
                return
            if intent.status is not QuorumStatus.GRANTED:
                raise QuorumDenied("only a granted quorum can be consumed")
            self._consumed[grant.intent_id] = (execution_id, idempotency_key)
            self._intents[grant.intent_id] = intent.model_copy(
                update={"status": QuorumStatus.CONSUMED}
            )
            self._persist_locked()

    def consumption(self, intent_id: str) -> tuple[str, str] | None:
        """Return the immutable execution identity recorded for a consumed intent."""

        with self._lock:
            return self._consumed.get(intent_id)

    def _all_attestations(self) -> tuple[QuorumAttestation, ...]:
        return tuple(item for values in self._attestations.values() for item in values)

    def _make_grant(
        self,
        intent: AuthorizationIntent,
        attestations: tuple[QuorumAttestation, QuorumAttestation],
        issued_at: datetime,
    ) -> QuorumActionGrant:
        ordered = tuple(sorted(attestations, key=lambda item: item.role.value))
        unsigned = QuorumActionGrant(
            grant_id=f"grant:{intent.intent_id}",
            intent_id=intent.intent_id,
            intent_digest=intent.intent_digest,
            case_id=intent.case_id,
            trace_id=intent.trace_id,
            case_version=intent.case_version,
            decision_digest=intent.decision_digest,
            tool=intent.tool,
            complete_parameters=intent.complete_parameters,
            parameters_digest=intent.parameters_digest,
            admitted_evidence_digest=intent.admitted_evidence_digest,
            approval_ids=(ordered[0].attestation_id, ordered[1].attestation_id),
            principal_ids=(ordered[0].principal_id, ordered[1].principal_id),
            roles=(ordered[0].role, ordered[1].role),
            issued_at=issued_at,
            expires_at=intent.expires_at,
            signature="pending",
        )
        signature_payload = canonical_json(unsigned.model_dump(mode="json", exclude={"signature"}))
        return unsigned.model_copy(update={"signature": self.signer.sign(signature_payload)})


class AuthorityBExecutor:
    """Boundary guard rejecting historical one-role grants.

    The existing ``ControlledExecutor`` remains available for Golden v1 migration
    artifacts.  New Authority-B callers must pass a ``QuorumActionGrant`` through this
    guard before invoking any controlled write adapter.
    """

    def __init__(self, *, signer: Signer | None = None, clock: Clock | None = None) -> None:
        self.signer = signer
        self.clock = clock

    def validate_grant(self, grant: object, *, now: datetime | None = None) -> QuorumActionGrant:
        if not isinstance(grant, QuorumActionGrant):
            raise QuorumDenied("legacy one-role grant is rejected by Authority-B executor")
        timestamp = _now(self.clock, now)
        if timestamp >= grant.expires_at:
            raise QuorumDenied("quorum grant is expired")
        if grant.grant_digest != grant._computed_digest():
            raise QuorumDenied("quorum grant digest is invalid")
        if self.signer is not None:
            payload = canonical_json(grant.model_dump(mode="json", exclude={"signature"}))
            if not self.signer.verify(payload, grant.signature):
                raise QuorumDenied("quorum grant signature is invalid")
        return grant

    def execute(
        self,
        grant: object,
        *,
        controlled_executor: AuthorityBControlledExecutor,
        execution_id: str,
        idempotency_key: str,
        fail_after_reservation: bool = False,
        fail_after_enterprise_commit: bool = False,
        now: datetime | None = None,
    ) -> object:
        """Forward only to the typed controlled-recovery adapter.

        Passing an arbitrary callback here used to make the quorum boundary a
        decorative validator.  The only supported sink is the repository-backed
        adapter, which performs reservation, the synthetic enterprise mutation,
        authoritative verification, and replay-safe receipt persistence.
        """

        from the_missing_20.authority_b.executor import AuthorityBControlledExecutor

        checked = self.validate_grant(grant, now=now)
        if not isinstance(controlled_executor, AuthorityBControlledExecutor):
            raise QuorumDenied("Authority-B executor requires the typed controlled adapter")
        return controlled_executor.execute(
            checked,
            execution_id=execution_id,
            idempotency_key=idempotency_key,
            fail_after_reservation=fail_after_reservation,
            fail_after_enterprise_commit=fail_after_enterprise_commit,
        )


__all__ = [
    "AuthorityBExecutor",
    "PrincipalDirectory",
    "QuorumAuthorizationService",
    "QuorumDenied",
]
