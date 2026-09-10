from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from multiprocessing import get_context
from multiprocessing.connection import Connection
from multiprocessing.synchronize import Event
from pathlib import Path
from threading import Barrier
from types import MappingProxyType
from typing import cast

import pytest

from the_missing_20.adapters.normal_receipt_billing_journal import (
    ACTION_NORMAL_RECEIPT_BILLING,
    AttemptClaim,
    BillingIntentJournal,
    CommercialSource,
    ExactDraftReadback,
    PrepareResult,
    ReadbackObservation,
)
from the_missing_20.adapters.normal_receipt_billing_native_request import (
    NativeDraftAcknowledgement,
    NativeInsertRequest,
    NativeSubmittedReadback,
)
from the_missing_20.adapters.normal_receipt_billing_preview import (
    BillingPreview,
    ExactIds,
    SyntheticBillingBasis,
)

NOW = datetime(2026, 9, 9, 22, 0, tzinfo=UTC)
MANAGER = "m20-demo-manager"


def _basis(
    *,
    case_id: str = "M20-R4-BILL-1",
    bill_reference: str = "SUP-BILL-R4-0001",
    purchase_receipt: str = "MAT-PRE-2026-00007",
    purchase_receipt_item: str = "068bbdr0mb",
    source_revision: str = "r4-read-1",
) -> SyntheticBillingBasis:
    return SyntheticBillingBasis(
        case_id=case_id,
        company="Missing 20 Automotive Demo",
        supplier="M20 Controller Systems Ltd.",
        bill_reference=bill_reference,
        bill_date="2026-09-09",
        purchase_order="PUR-ORD-2026-00016",
        purchase_order_item="458j82kp8e",
        purchase_receipt=purchase_receipt,
        purchase_receipt_item=purchase_receipt_item,
        item_code="M20-DEMO-CARTON",
        source_revision=source_revision,
        posting_date="2026-09-09",
        credit_to="Creditors - M20",
        expense_account="Stock Received But Not Billed - M20",
    )


def _preview(basis: SyntheticBillingBasis, *, source_digest: str = "a" * 64) -> BillingPreview:
    return BillingPreview(
        source_digest=source_digest,
        bill_digest=basis.bill_digest,
        exact_ids=ExactIds(
            case_id=basis.case_id,
            purchase_order=basis.purchase_order,
            purchase_order_item=basis.purchase_order_item,
            purchase_receipt=basis.purchase_receipt,
            purchase_receipt_item=basis.purchase_receipt_item,
        ),
        quantity=basis.quantity,
        uom=basis.uom,
        stock_uom=basis.stock_uom,
        conversion_factor=basis.conversion_factor,
        net_amount=basis.net_amount,
        gross_amount=basis.gross_amount,
        required_inputs=(
            "DISCLOSED_SYNTHETIC_BILL",
            "COMPLETE_SCOPED_RELATED_DOCUMENT_READ",
            "NATIVE_PR_TO_PI_MAPPER",
            "SEPARATE_APPROVAL_REQUIRED",
        ),
        status="READY",
        reasons=(),
        read_only=True,
        write_allowed=False,
        source=MappingProxyType(
            {
                "read_only": True,
                "source_revision": basis.source_revision,
                "observed_at": "2026-09-09T21:10:00Z",
            }
        ),
    )


def _source(
    basis: SyntheticBillingBasis,
    *,
    revision: str = "source-v1",
    audit_snapshot_digest: str = "audit-snapshot-v1",
    observed_at: str = "2026-09-09T21:10:00Z",
    net_rate: str = "50",
) -> CommercialSource:
    return CommercialSource(
        identity={
            "company": basis.company,
            "supplier": basis.supplier,
            "purchase_order": basis.purchase_order,
            "purchase_order_item": basis.purchase_order_item,
            "purchase_receipt": basis.purchase_receipt,
            "purchase_receipt_item": basis.purchase_receipt_item,
            "item_code": basis.item_code,
        },
        revisions={
            "purchase_order": revision,
            "purchase_receipt": revision,
            "related_documents": revision,
        },
        decisive_values={
            "quantity": "1",
            "uom": "Box",
            "stock_uom": "Box",
            "conversion_factor": "1",
            "net_rate": net_rate,
            "currency": "USD",
            "gross_amount": net_rate,
        },
        audit_snapshot_digest=audit_snapshot_digest,
        observed_at=observed_at,
    )


def _journal(tmp_path: Path) -> BillingIntentJournal:
    return BillingIntentJournal(tmp_path / "normal-billing.sqlite3")


def _approve(
    journal: BillingIntentJournal,
    intent_id: str,
    *,
    basis: SyntheticBillingBasis,
    expires_at: datetime | None = None,
    expected_version: int = 1,
) -> str:
    approval = journal.approve(
        intent_id,
        case_id=basis.case_id,
        manager_id=MANAGER,
        expires_at=expires_at or NOW + timedelta(minutes=10),
        now=NOW,
    )
    assert approval.granted is True
    assert approval.action == ACTION_NORMAL_RECEIPT_BILLING
    assert approval.case_id == basis.case_id
    assert approval.manager_id == MANAGER
    assert approval.intent_version == expected_version
    assert approval.token
    return approval.token


def _claim_insert(
    journal: BillingIntentJournal,
    intent_id: str,
    basis: SyntheticBillingBasis,
    token: str,
    *,
    worker_id: str = "worker-a",
) -> AttemptClaim:
    return journal.claim_insert(
        intent_id,
        case_id=basis.case_id,
        manager_id=MANAGER,
        approval_token=token,
        worker_id=worker_id,
        now=NOW,
    )


def _process_claim(
    database: str,
    intent_id: str,
    case_id: str,
    approval_token: str,
    worker_id: str,
    start: Event,
    result: Connection,
) -> None:
    try:
        journal = BillingIntentJournal(database)
        if not start.wait(timeout=10):
            result.send((False, "START_TIMEOUT"))
            return
        claim = journal.claim_insert(
            intent_id,
            case_id=case_id,
            manager_id=MANAGER,
            approval_token=approval_token,
            worker_id=worker_id,
            now=NOW,
        )
        result.send((claim.granted, claim.reason))
    except BaseException as error:
        result.send((False, f"WORKER_ERROR:{type(error).__name__}"))
        raise
    finally:
        result.close()


def _process_open_legacy_schema(database: str, start: Event, result: Connection) -> None:
    try:
        if not start.wait(timeout=10):
            result.send((False, "START_TIMEOUT"))
            return
        BillingIntentJournal(database)
        result.send((True, None))
    except BaseException as error:
        result.send((False, type(error).__name__))
        raise
    finally:
        result.close()


def _draft(
    basis: SyntheticBillingBasis, commercial_version: str, *, name: str = "ACC-PINV-0001"
) -> ExactDraftReadback:
    return ExactDraftReadback(
        draft_name=name,
        company=basis.company,
        supplier=basis.supplier,
        bill_reference=basis.bill_reference,
        purchase_receipt=basis.purchase_receipt,
        purchase_receipt_item=basis.purchase_receipt_item,
        bill_digest=basis.bill_digest,
        commercial_version=commercial_version,
        candidate_count=1,
        lookup_complete=True,
        audit_snapshot_digest="draft-readback-v1",
        observed_at="2026-09-09T22:01:00Z",
    )


def _readback(kind: str) -> ReadbackObservation:
    return ReadbackObservation(
        kind=kind,
        audit_snapshot_digest=f"{kind.lower()}-readback-v1",
        observed_at="2026-09-09T22:01:00Z",
        details={"lookup_scope": "complete-company-supplier-bill-reference"},
    )


def _insert_request(
    basis: SyntheticBillingBasis, *, remarks: str = "bound-native-request-v1"
) -> NativeInsertRequest:
    return NativeInsertRequest(
        method="POST",
        path="/api/resource/Purchase%20Invoice",
        bill_digest=basis.bill_digest,
        body={
            "doctype": "Purchase Invoice",
            "name": None,
            "docstatus": 0,
            "company": basis.company,
            "supplier": basis.supplier,
            "bill_no": basis.bill_reference,
            "bill_date": basis.bill_date,
            "currency": basis.currency,
            "credit_to": basis.credit_to,
            "update_stock": 0,
            "is_return": 0,
            "is_paid": 0,
            "items": [
                {
                    "item_code": basis.item_code,
                    "purchase_order": basis.purchase_order,
                    "po_detail": basis.purchase_order_item,
                    "purchase_receipt": basis.purchase_receipt,
                    "pr_detail": basis.purchase_receipt_item,
                }
            ],
            "remarks": remarks,
        },
    )


def _acknowledged_draft(
    request: NativeInsertRequest,
    *,
    name: str = "ACC-PINV-0001",
    remarks: str = "bound-native-request-v1",
) -> NativeDraftAcknowledgement:
    body = dict(request.body)
    body.update(
        {
            "name": name,
            "docstatus": 0,
            "owner": "demo@example.test",
            "creation": "2026-09-09 22:00:00.000000",
            "modified": "2026-09-09 22:00:00.000000",
            "remarks": remarks,
        }
    )
    return NativeDraftAcknowledgement(
        insert_body_digest=request.body_digest,
        draft_name=name,
        document=body,
    )


def _submitted_readback(
    acknowledgement: NativeDraftAcknowledgement,
) -> NativeSubmittedReadback:
    document = dict(acknowledgement.document)
    document["docstatus"] = 1
    return NativeSubmittedReadback(
        draft_name=acknowledgement.draft_name,
        draft_document_digest=acknowledgement.document_digest,
        document=document,
    )


def test_read_only_ready_preview_is_evidence_not_write_permission(tmp_path: Path) -> None:
    basis = _basis()
    preview = _preview(basis)
    source = _source(basis)
    journal = _journal(tmp_path)

    prepared = journal.prepare(basis, preview, source)

    assert prepared.accepted is True
    assert prepared.created is True
    assert prepared.snapshot.phase == "PREPARED"
    assert prepared.snapshot.authority_status == "PENDING_APPROVAL"
    assert prepared.snapshot.insert_attempted is False
    assert prepared.snapshot.submit_attempted is False
    assert prepared.snapshot.business_idempotency_key != preview.source_digest
    assert prepared.snapshot.frozen_basis["gross_amount"] == "50"
    assert journal.bound_insert_request(prepared.intent_id) is None
    assert journal.acknowledged_draft(prepared.intent_id) is None
    denied = journal.claim_insert(
        prepared.intent_id,
        case_id=basis.case_id,
        manager_id=MANAGER,
        approval_token="not-an-approval",
        worker_id="worker-a",
        now=NOW,
    )
    assert denied.granted is False
    assert denied.reason == "INSERT_REQUEST_UNBOUND"

    mismatched = journal.prepare(basis, replace(preview, bill_digest="b" * 64), source)
    assert mismatched.accepted is False
    assert mismatched.reason == "PREVIEW_BASIS_MISMATCH"


def test_commercial_source_preserves_exact_mapping_keys() -> None:
    source = CommercialSource(
        identity={"company": "M20", " company": "different"},
        revisions={"purchase_receipt": "r1"},
        decisive_values={},
        audit_snapshot_digest="audit-v1",
        observed_at="2026-09-09T21:10:00Z",
    )

    assert dict(source.identity) == {"company": "M20", " company": "different"}


def test_approval_is_server_generated_bound_and_nonreusable(tmp_path: Path) -> None:
    basis = _basis()
    other_basis = _basis(
        case_id="M20-R4-BILL-2",
        bill_reference="SUP-BILL-R4-0002",
        purchase_receipt="MAT-PRE-2026-00008",
        purchase_receipt_item="068bbdr0mc",
    )
    journal = _journal(tmp_path)
    prepared = journal.prepare(
        basis, _preview(basis), _source(basis), insert_request=_insert_request(basis)
    )
    other_prepared = journal.prepare(
        other_basis,
        _preview(other_basis),
        _source(other_basis),
        insert_request=_insert_request(other_basis),
    )

    token = _approve(journal, prepared.intent_id, basis=basis)
    repeated = journal.approve(
        prepared.intent_id,
        case_id=basis.case_id,
        manager_id=MANAGER,
        expires_at=NOW + timedelta(minutes=10),
        now=NOW,
    )
    assert repeated.granted is False
    assert repeated.reason == "APPROVAL_ALREADY_ISSUED"
    assert repeated.token is None

    cross_case = journal.claim_insert(
        other_prepared.intent_id,
        case_id=other_basis.case_id,
        manager_id=MANAGER,
        approval_token=token,
        worker_id="worker-b",
        now=NOW,
    )
    stale_case = journal.claim_insert(
        prepared.intent_id,
        case_id="M20-R4-WRONG-CASE",
        manager_id=MANAGER,
        approval_token=token,
        worker_id="worker-b",
        now=NOW,
    )
    assert cross_case.granted is False
    assert cross_case.reason == "APPROVAL_REQUIRED"
    assert stale_case.granted is False
    assert stale_case.reason == "CASE_MISMATCH"

    claimed = _claim_insert(journal, prepared.intent_id, basis, token)
    assert claimed.granted is True
    assert claimed.attempt_kind == "INSERT"
    assert claimed.idempotency_key == prepared.snapshot.business_idempotency_key
    assert claimed.payload["basis"]["gross_amount"] == "50"
    with pytest.raises(TypeError):
        cast(dict[str, object], claimed.payload)["basis"] = {}


def test_refusal_keeps_known_effect_phase_and_blocks_next_write(tmp_path: Path) -> None:
    basis = _basis()
    journal = _journal(tmp_path)
    prepared = journal.prepare(
        basis, _preview(basis), _source(basis), insert_request=_insert_request(basis)
    )
    token = _approve(journal, prepared.intent_id, basis=basis)

    journal.refuse(
        prepared.intent_id,
        case_id=basis.case_id,
        manager_id=MANAGER,
        reason="manager stopped the bill",
        now=NOW,
    )
    denied = _claim_insert(journal, prepared.intent_id, basis, token)
    assert denied.granted is False
    assert denied.reason == "REFUSED"

    second_basis = _basis(
        case_id="M20-R4-BILL-2",
        bill_reference="SUP-BILL-R4-0002",
        purchase_receipt="MAT-PRE-2026-00008",
        purchase_receipt_item="068bbdr0mc",
    )
    second = journal.prepare(
        second_basis,
        _preview(second_basis),
        _source(second_basis),
        insert_request=_insert_request(second_basis),
    )
    second_token = _approve(journal, second.intent_id, basis=second_basis)
    inserted = _claim_insert(journal, second.intent_id, second_basis, second_token)
    assert inserted.granted is True
    journal.refuse(
        second.intent_id,
        case_id=second_basis.case_id,
        manager_id=MANAGER,
        reason="stop while insert may be in flight",
        now=NOW,
    )

    admitted = journal.admit_insert_acknowledgement(
        second.intent_id, _acknowledged_draft(_insert_request(second_basis))
    )
    submit = journal.claim_submit(
        second.intent_id,
        case_id=second_basis.case_id,
        manager_id=MANAGER,
        worker_id="worker-a",
        now=NOW,
    )
    assert admitted.admitted is True
    assert admitted.snapshot.insert_attempted is True
    assert admitted.snapshot.phase == "DRAFT_READBACK_ADMITTED"
    assert admitted.snapshot.authority_status == "REFUSED"
    assert submit.granted is False
    assert submit.reason == "REFUSED"


def test_audit_refresh_does_not_change_commercial_version_but_source_change_blocks_writes(
    tmp_path: Path,
) -> None:
    basis = _basis()
    source = _source(basis)
    journal = _journal(tmp_path)
    prepared = journal.prepare(
        basis, _preview(basis), source, insert_request=_insert_request(basis)
    )
    token = _approve(journal, prepared.intent_id, basis=basis)

    observation_refresh = _source(
        basis,
        audit_snapshot_digest="audit-snapshot-v2",
        observed_at="2026-09-09T21:20:00Z",
    )
    refreshed = journal.refresh_source(prepared.intent_id, observation_refresh, now=NOW)
    assert refreshed.commercial_changed is False
    assert refreshed.snapshot.source_changed is False
    assert refreshed.snapshot.commercial_version == prepared.snapshot.commercial_version
    assert refreshed.snapshot.audit_snapshot_digest == "audit-snapshot-v2"
    assert _claim_insert(journal, prepared.intent_id, basis, token).granted is True

    changed_basis = _basis(
        case_id="M20-R4-BILL-2",
        bill_reference="SUP-BILL-R4-0002",
        purchase_receipt="MAT-PRE-2026-00008",
        purchase_receipt_item="068bbdr0mc",
    )
    changed = journal.prepare(
        changed_basis,
        _preview(changed_basis),
        _source(changed_basis),
        insert_request=_insert_request(changed_basis),
    )
    changed_token = _approve(journal, changed.intent_id, basis=changed_basis)
    changed_source = _source(
        changed_basis,
        revision="source-v2",
        audit_snapshot_digest="audit-snapshot-v3",
        observed_at="2026-09-09T21:25:00Z",
        net_rate="51",
    )
    source_change = journal.refresh_source(changed.intent_id, changed_source, now=NOW)
    assert source_change.commercial_changed is True
    assert source_change.snapshot.source_changed is True
    assert source_change.snapshot.authority_status == "STALE_SOURCE"
    blocked = _claim_insert(journal, changed.intent_id, changed_basis, changed_token)
    assert blocked.granted is False
    assert blocked.reason == "COMMERCIAL_SOURCE_CHANGED"


def test_source_change_still_permits_old_effect_readback_but_never_a_next_write(
    tmp_path: Path,
) -> None:
    basis = _basis()
    journal = _journal(tmp_path)
    prepared = journal.prepare(
        basis, _preview(basis), _source(basis), insert_request=_insert_request(basis)
    )
    token = _approve(journal, prepared.intent_id, basis=basis)
    assert _claim_insert(journal, prepared.intent_id, basis, token).granted is True

    journal.refresh_source(
        prepared.intent_id,
        _source(basis, revision="source-v2", net_rate="51"),
        now=NOW,
    )
    readback = journal.admit_insert_acknowledgement(
        prepared.intent_id, _acknowledged_draft(_insert_request(basis))
    )
    submit = journal.claim_submit(
        prepared.intent_id,
        case_id=basis.case_id,
        manager_id=MANAGER,
        worker_id="worker-a",
        now=NOW,
    )
    assert readback.admitted is True
    assert readback.snapshot.source_changed is True
    assert readback.snapshot.phase == "DRAFT_READBACK_ADMITTED"
    assert submit.granted is False
    assert submit.reason == "COMMERCIAL_SOURCE_CHANGED"


def test_two_sqlite_processes_fence_same_bill_and_connections_fence_receipt_line(
    tmp_path: Path,
) -> None:
    database = tmp_path / "normal-billing.sqlite3"
    basis = _basis()
    journal = BillingIntentJournal(database)
    prepared = journal.prepare(
        basis, _preview(basis), _source(basis), insert_request=_insert_request(basis)
    )
    token = _approve(journal, prepared.intent_id, basis=basis)
    context = get_context("fork")
    start = context.Event()
    parent_a, child_a = context.Pipe(duplex=False)
    parent_b, child_b = context.Pipe(duplex=False)
    process_a = context.Process(
        target=_process_claim,
        args=(
            str(database),
            prepared.intent_id,
            basis.case_id,
            token,
            "worker-a",
            start,
            child_a,
        ),
    )
    process_b = context.Process(
        target=_process_claim,
        args=(
            str(database),
            prepared.intent_id,
            basis.case_id,
            token,
            "worker-b",
            start,
            child_b,
        ),
    )
    try:
        process_a.start()
        process_b.start()
        child_a.close()
        child_b.close()
        start.set()
        assert parent_a.poll(15)
        assert parent_b.poll(15)
        claims = (parent_a.recv(), parent_b.recv())
        process_a.join(timeout=5)
        process_b.join(timeout=5)
        assert process_a.exitcode == 0
        assert process_b.exitcode == 0
    finally:
        start.set()
        for process in (process_a, process_b):
            if process.is_alive():
                process.terminate()
            process.join(timeout=5)
        for pipe in (child_a, child_b, parent_a, parent_b):
            pipe.close()
    assert sum(claim[0] for claim in claims) == 1
    assert sum(claim[1] == "INSERT_ALREADY_ATTEMPTED" for claim in claims) == 1

    line_a = _basis(
        case_id="M20-R4-BILL-2",
        bill_reference="SUP-BILL-R4-0002",
        purchase_receipt="MAT-PRE-2026-00008",
        purchase_receipt_item="068bbdr0mc",
    )
    line_b = replace(line_a, bill_reference="SUP-BILL-R4-0003")
    line_database = tmp_path / "normal-billing-line-race.sqlite3"
    line_barrier = Barrier(2)
    line_journal_a = BillingIntentJournal(line_database)
    line_journal_b = BillingIntentJournal(line_database)

    def prepare(pair: tuple[BillingIntentJournal, SyntheticBillingBasis]) -> PrepareResult:
        local, candidate = pair
        line_barrier.wait(timeout=5)
        return local.prepare(
            candidate,
            _preview(candidate),
            _source(candidate),
            insert_request=_insert_request(candidate),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = (
            pool.submit(prepare, (line_journal_a, line_a)),
            pool.submit(prepare, (line_journal_b, line_b)),
        )
        results = [future.result(timeout=15) for future in futures]
    assert sum(result.accepted for result in results) == 1
    assert sum(result.reason == "RECEIPT_LINE_CONFLICT" for result in results) == 1

    accepted = next(result for result in results if result.accepted)
    winning_basis = line_a if accepted.snapshot.bill_reference == line_a.bill_reference else line_b
    line_journal = BillingIntentJournal(line_database)
    line_token = _approve(line_journal, accepted.intent_id, basis=winning_basis)
    assert (
        _claim_insert(line_journal, accepted.intent_id, winning_basis, line_token).granted is True
    )


def test_restart_unknown_no_hit_and_submitted_readback_never_reopen_attempts(
    tmp_path: Path,
) -> None:
    database = tmp_path / "normal-billing.sqlite3"
    basis = _basis()
    first = BillingIntentJournal(database)
    prepared = first.prepare(
        basis, _preview(basis), _source(basis), insert_request=_insert_request(basis)
    )
    token = _approve(first, prepared.intent_id, basis=basis)

    before_insert_restart = BillingIntentJournal(database)
    insert = _claim_insert(before_insert_restart, prepared.intent_id, basis, token)
    assert insert.granted is True
    assert insert.attempt_kind == "INSERT"

    after_insert_restart = BillingIntentJournal(database)
    after_insert_restart.record_no_hit(prepared.intent_id, _readback("NO_HIT"), now=NOW)
    repeated_insert = _claim_insert(after_insert_restart, prepared.intent_id, basis, token)
    assert repeated_insert.granted is False
    assert repeated_insert.reason == "INSERT_ALREADY_ATTEMPTED"

    acknowledgement = _acknowledged_draft(_insert_request(basis))
    draft = after_insert_restart.admit_insert_acknowledgement(prepared.intent_id, acknowledgement)
    assert draft.admitted is True
    before_submit_restart = BillingIntentJournal(database)
    submit = before_submit_restart.claim_submit(
        prepared.intent_id,
        case_id=basis.case_id,
        manager_id=MANAGER,
        worker_id="worker-a",
        now=NOW,
    )
    assert submit.granted is True
    assert submit.attempt_kind == "SUBMIT"

    after_submit_restart = BillingIntentJournal(database)
    after_submit_restart.record_unknown(prepared.intent_id, _readback("UNKNOWN"), now=NOW)
    admitted_again = after_submit_restart.admit_draft_readback(
        prepared.intent_id, _draft(basis, prepared.snapshot.commercial_version)
    )
    repeated_submit = after_submit_restart.claim_submit(
        prepared.intent_id,
        case_id=basis.case_id,
        manager_id=MANAGER,
        worker_id="worker-b",
        now=NOW,
    )
    submitted = after_submit_restart.admit_submitted_readback(
        prepared.intent_id, _submitted_readback(acknowledgement)
    )
    assert admitted_again.admitted is True
    assert repeated_submit.granted is False
    assert repeated_submit.reason == "SUBMIT_ALREADY_ATTEMPTED"
    assert submitted.admitted is True
    assert submitted.snapshot.phase == "SUBMITTED_READBACK_ADMITTED"
    assert submitted.snapshot.submit_attempted is True
    assert submitted.snapshot.last_readback_kind == "SUBMITTED"


def test_six_step_effect_identity_repro_holds_and_preserves_first_readbacks(
    tmp_path: Path,
) -> None:
    basis = _basis()
    journal = _journal(tmp_path)
    prepared = journal.prepare(
        basis, _preview(basis), _source(basis), insert_request=_insert_request(basis)
    )
    token = _approve(journal, prepared.intent_id, basis=basis)

    # 1. Mark the only insert attempt.  2. Admit its first bound native draft.
    assert _claim_insert(journal, prepared.intent_id, basis, token).granted is True
    first_draft = _acknowledged_draft(_insert_request(basis), name="PI-FIRST")
    first = journal.admit_insert_acknowledgement(prepared.intent_id, first_draft)
    assert first.admitted is True

    # 3. A conflicting draft must not replace the first durable identity/evidence.
    conflicting_draft = journal.admit_insert_acknowledgement(
        prepared.intent_id,
        _acknowledged_draft(_insert_request(basis), name="PI-OTHER"),
    )
    assert conflicting_draft.admitted is False
    assert conflicting_draft.reason == "DRAFT_ACKNOWLEDGEMENT_CONFLICT"
    assert conflicting_draft.snapshot.draft_name == "PI-FIRST"
    assert conflicting_draft.snapshot.effect_conflict is True
    assert conflicting_draft.snapshot.authority_status == "CONFLICT_HOLD"
    draft_events = journal.history(prepared.intent_id)
    assert draft_events[-2].kind == "INSERT_ACKNOWLEDGEMENT_ADMITTED"
    assert draft_events[-2].payload["acknowledgement"]["draft_name"] == "PI-FIRST"
    assert draft_events[-1].kind == "DRAFT_ACKNOWLEDGEMENT_CONFLICT"
    assert draft_events[-1].payload["incoming_proof"]["draft_name"] == "PI-OTHER"
    reaffirmed_draft = journal.admit_insert_acknowledgement(prepared.intent_id, first_draft)
    assert reaffirmed_draft.admitted is True
    assert reaffirmed_draft.snapshot.effect_conflict is True

    # 4. The immutable submit payload must still name the first exact draft.
    submit = journal.claim_submit(
        prepared.intent_id,
        case_id=basis.case_id,
        manager_id=MANAGER,
        worker_id="worker-a",
        now=NOW,
    )
    assert submit.granted is False
    assert submit.reason == "EFFECT_IDENTITY_CONFLICT"

    # A separate uncompromised intent establishes the post-submit identity steps.
    second_basis = _basis(
        case_id="M20-R4-BILL-2",
        bill_reference="SUP-BILL-R4-0002",
        purchase_receipt="MAT-PRE-2026-00008",
        purchase_receipt_item="068bbdr0mc",
    )
    second = journal.prepare(
        second_basis,
        _preview(second_basis),
        _source(second_basis),
        insert_request=_insert_request(second_basis),
    )
    second_token = _approve(journal, second.intent_id, basis=second_basis)
    assert _claim_insert(journal, second.intent_id, second_basis, second_token).granted is True
    second_draft = _acknowledged_draft(_insert_request(second_basis), name="PI-FIRST")
    assert journal.admit_insert_acknowledgement(second.intent_id, second_draft).admitted is True
    second_submit = journal.claim_submit(
        second.intent_id,
        case_id=second_basis.case_id,
        manager_id=MANAGER,
        worker_id="worker-a",
        now=NOW,
    )
    assert second_submit.granted is True
    assert second_submit.payload["draft_name"] == "PI-FIRST"

    # 5. Admit only the submitted identity named by that frozen submit payload.
    first_submitted_proof = _submitted_readback(second_draft)
    first_submitted = journal.admit_submitted_readback(second.intent_id, first_submitted_proof)
    assert first_submitted.admitted is True

    # 6. A later different submitted identity is a readback conflict, never replacement.
    conflicting_document = dict(first_submitted_proof.document)
    conflicting_document["name"] = "PI-THIRD"
    conflicting_submitted = journal.admit_submitted_readback(
        second.intent_id,
        NativeSubmittedReadback(
            draft_name="PI-THIRD",
            draft_document_digest=second_draft.document_digest,
            document=conflicting_document,
        ),
    )
    assert conflicting_submitted.admitted is False
    assert conflicting_submitted.reason == "SUBMITTED_DRAFT_DOCUMENT_MISMATCH"
    assert conflicting_submitted.snapshot.submitted_invoice_name == "PI-FIRST"
    assert conflicting_submitted.snapshot.effect_conflict is True
    assert conflicting_submitted.snapshot.authority_status == "CONFLICT_HOLD"
    submitted_events = journal.history(second.intent_id)
    assert submitted_events[-2].kind == "SUBMITTED_READBACK_ADMITTED"
    assert submitted_events[-2].payload["submitted_readback"]["draft_name"] == "PI-FIRST"
    assert submitted_events[-1].kind == "SUBMITTED_READBACK_CONFLICT"
    assert submitted_events[-1].payload["incoming_proof"]["draft_name"] == "PI-THIRD"
    reaffirmed_submitted = journal.admit_submitted_readback(
        second.intent_id,
        first_submitted_proof,
    )
    assert reaffirmed_submitted.admitted is True
    assert reaffirmed_submitted.snapshot.effect_conflict is True


def test_submitted_readback_must_match_the_frozen_submit_draft_name(tmp_path: Path) -> None:
    basis = _basis()
    journal = _journal(tmp_path)
    prepared = journal.prepare(
        basis, _preview(basis), _source(basis), insert_request=_insert_request(basis)
    )
    token = _approve(journal, prepared.intent_id, basis=basis)
    assert _claim_insert(journal, prepared.intent_id, basis, token).granted is True
    acknowledgement = _acknowledged_draft(_insert_request(basis), name="PI-FIRST")
    assert (
        journal.admit_insert_acknowledgement(prepared.intent_id, acknowledgement).admitted is True
    )
    submit = journal.claim_submit(
        prepared.intent_id,
        case_id=basis.case_id,
        manager_id=MANAGER,
        worker_id="worker-a",
        now=NOW,
    )
    assert submit.granted is True
    assert submit.payload["draft_name"] == "PI-FIRST"

    mismatched_document = dict(_submitted_readback(acknowledgement).document)
    mismatched_document["name"] = "PI-DIFFERENT"
    mismatched = journal.admit_submitted_readback(
        prepared.intent_id,
        NativeSubmittedReadback(
            draft_name="PI-DIFFERENT",
            draft_document_digest=acknowledgement.document_digest,
            document=mismatched_document,
        ),
    )
    assert mismatched.admitted is False
    assert mismatched.reason == "SUBMITTED_DRAFT_DOCUMENT_MISMATCH"
    assert mismatched.snapshot.submitted_invoice_name is None
    assert mismatched.snapshot.effect_conflict is True
    assert mismatched.snapshot.authority_status == "CONFLICT_HOLD"


def test_expiry_and_invalid_draft_proof_never_authorize_a_repeat_attempt(tmp_path: Path) -> None:
    basis = _basis()
    journal = _journal(tmp_path)
    prepared = journal.prepare(
        basis, _preview(basis), _source(basis), insert_request=_insert_request(basis)
    )
    token = _approve(
        journal,
        prepared.intent_id,
        basis=basis,
        expires_at=NOW + timedelta(seconds=1),
    )
    expired = journal.claim_insert(
        prepared.intent_id,
        case_id=basis.case_id,
        manager_id=MANAGER,
        approval_token=token,
        worker_id="worker-a",
        now=NOW + timedelta(seconds=2),
    )
    assert expired.granted is False
    assert expired.reason == "APPROVAL_EXPIRED"

    second_basis = _basis(
        case_id="M20-R4-BILL-2",
        bill_reference="SUP-BILL-R4-0002",
        purchase_receipt="MAT-PRE-2026-00008",
        purchase_receipt_item="068bbdr0mc",
    )
    second = journal.prepare(
        second_basis,
        _preview(second_basis),
        _source(second_basis),
        insert_request=_insert_request(second_basis),
    )
    second_token = _approve(journal, second.intent_id, basis=second_basis)
    assert _claim_insert(journal, second.intent_id, second_basis, second_token).granted is True
    invalid = journal.admit_draft_readback(
        second.intent_id,
        replace(_draft(second_basis, second.snapshot.commercial_version), candidate_count=2),
    )
    submit = journal.claim_submit(
        second.intent_id,
        case_id=second_basis.case_id,
        manager_id=MANAGER,
        worker_id="worker-a",
        now=NOW,
    )
    assert invalid.admitted is False
    assert invalid.reason == "DRAFT_READBACK_NOT_UNIQUE"
    assert submit.granted is False
    assert submit.reason == "DRAFT_ACKNOWLEDGEMENT_REQUIRED"


def test_explicit_reprepare_versions_unattempted_intent_and_invalidates_old_token(
    tmp_path: Path,
) -> None:
    basis = _basis()
    preview = _preview(basis)
    source = _source(basis)
    journal = _journal(tmp_path)
    prepared = journal.prepare(basis, preview, source, insert_request=_insert_request(basis))
    old_token = _approve(journal, prepared.intent_id, basis=basis)
    journal.refuse(
        prepared.intent_id,
        case_id=basis.case_id,
        manager_id=MANAGER,
        reason="reprepare with a fresh confirmation",
        now=NOW,
    )

    replacement_source = _source(
        basis,
        revision="source-v2",
        audit_snapshot_digest="audit-snapshot-v2",
        observed_at="2026-09-09T22:05:00Z",
    )
    reprepared = journal.reprepare(
        prepared.intent_id,
        basis,
        preview,
        replacement_source,
        insert_request=_insert_request(basis),
        now=NOW,
    )
    assert reprepared.accepted is True
    assert reprepared.snapshot.intent_version == 2
    assert reprepared.snapshot.phase == "PREPARED"
    assert reprepared.snapshot.authority_status == "PENDING_APPROVAL"
    old_token_claim = _claim_insert(journal, prepared.intent_id, basis, old_token)
    assert old_token_claim.granted is False
    assert old_token_claim.reason == "APPROVAL_REQUIRED"

    new_token = journal.approve(
        prepared.intent_id,
        case_id=basis.case_id,
        manager_id=MANAGER,
        expires_at=NOW + timedelta(minutes=10),
        now=NOW,
    )
    assert new_token.granted is True
    assert new_token.intent_version == 2
    assert new_token.token is not None
    assert _claim_insert(journal, prepared.intent_id, basis, new_token.token).granted is True
    blocked = journal.reprepare(
        prepared.intent_id,
        basis,
        preview,
        replacement_source,
        insert_request=_insert_request(basis),
        now=NOW,
    )
    assert blocked.accepted is False
    assert blocked.reason == "INSERT_ALREADY_ATTEMPTED"
    assert [event.kind for event in journal.history(prepared.intent_id)] == [
        "PREPARED",
        "APPROVED",
        "REFUSED",
        "REPREPARED",
        "APPROVED",
        "INSERT_ATTEMPT_MARKED",
    ]


def test_history_keeps_immutable_basis_preview_and_source_versions(tmp_path: Path) -> None:
    basis = _basis()
    preview = _preview(basis)
    source = _source(basis)
    journal = _journal(tmp_path)
    prepared = journal.prepare(basis, preview, source)
    journal.refresh_source(
        prepared.intent_id,
        _source(basis, audit_snapshot_digest="audit-snapshot-v2"),
        now=NOW,
    )

    snapshot = journal.get(prepared.intent_id)
    history = journal.history(prepared.intent_id)
    assert snapshot.frozen_basis["gross_amount"] == "50"
    assert snapshot.frozen_preview["bill_digest"] == basis.bill_digest
    assert [event.kind for event in history] == ["PREPARED", "SOURCE_REFRESHED"]
    assert history[-1].payload["audit_snapshot_digest"] == "audit-snapshot-v2"
    with pytest.raises(TypeError):
        snapshot.frozen_basis["gross_amount"] = "999"  # type: ignore[index]


def test_unbound_or_corrupt_insert_binding_cannot_approve_or_claim(tmp_path: Path) -> None:
    basis = _basis()
    journal = _journal(tmp_path)
    unbound = journal.prepare(basis, _preview(basis), _source(basis))

    approval = journal.approve(
        unbound.intent_id,
        case_id=basis.case_id,
        manager_id=MANAGER,
        expires_at=NOW + timedelta(minutes=10),
        now=NOW,
    )
    assert approval.granted is False
    assert approval.reason == "INSERT_REQUEST_UNBOUND"
    assert unbound.snapshot.insert_attempted is False

    bound = journal.prepare(
        _basis(
            case_id="M20-R4-BILL-2",
            bill_reference="SUP-BILL-R4-0002",
            purchase_receipt="MAT-PRE-2026-00008",
            purchase_receipt_item="068bbdr0mc",
        ),
        _preview(
            _basis(
                case_id="M20-R4-BILL-2",
                bill_reference="SUP-BILL-R4-0002",
                purchase_receipt="MAT-PRE-2026-00008",
                purchase_receipt_item="068bbdr0mc",
            )
        ),
        _source(
            _basis(
                case_id="M20-R4-BILL-2",
                bill_reference="SUP-BILL-R4-0002",
                purchase_receipt="MAT-PRE-2026-00008",
                purchase_receipt_item="068bbdr0mc",
            )
        ),
        insert_request=_insert_request(
            _basis(
                case_id="M20-R4-BILL-2",
                bill_reference="SUP-BILL-R4-0002",
                purchase_receipt="MAT-PRE-2026-00008",
                purchase_receipt_item="068bbdr0mc",
            )
        ),
    )
    database = tmp_path / "normal-billing.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE normal_receipt_billing_intents SET insert_binding_json = ? WHERE intent_id = ?",
            (json.dumps({"not": "a bound native request"}), bound.intent_id),
        )
    corrupt = journal.approve(
        bound.intent_id,
        case_id=bound.snapshot.case_id,
        manager_id=MANAGER,
        expires_at=NOW + timedelta(minutes=10),
        now=NOW,
    )
    assert corrupt.granted is False
    assert corrupt.reason == "INSERT_REQUEST_INVALID"
    assert journal.get(bound.intent_id).insert_attempted is False


def test_bound_request_is_durable_before_approval_and_claim_returns_only_that_request(
    tmp_path: Path,
) -> None:
    basis = _basis()
    request = _insert_request(basis)
    journal = _journal(tmp_path)
    prepared = journal.prepare(
        basis,
        _preview(basis),
        _source(basis),
        insert_request=request,
    )
    token = _approve(journal, prepared.intent_id, basis=basis)

    request_body = request.record()["body"]
    assert isinstance(request_body, dict)
    request_body["bill_no"] = "MUTATED-CALLER"
    claim = _claim_insert(journal, prepared.intent_id, basis, token)
    assert claim.granted is True
    assert claim.payload["native_request"]["body"]["bill_no"] == basis.bill_reference
    assert claim.payload["request_binding"]["intent_version"] == 1
    assert (
        claim.payload["request_binding"]["commercial_version"]
        == prepared.snapshot.commercial_version
    )

    reopened = BillingIntentJournal(tmp_path / "normal-billing.sqlite3")
    history = reopened.history(prepared.intent_id)
    assert history[0].payload["insert_binding"]["request"]["body_digest"] == request.body_digest
    assert (
        history[-1].payload["payload"]["native_request"]["body"]["bill_no"] == basis.bill_reference
    )


def test_same_source_different_bound_body_requires_a_new_version_and_invalidates_old_token(
    tmp_path: Path,
) -> None:
    basis = _basis()
    first_request = _insert_request(basis, remarks="mapper-remarks-a")
    second_request = _insert_request(basis, remarks="mapper-remarks-b")
    journal = _journal(tmp_path)
    prepared = journal.prepare(
        basis,
        _preview(basis),
        _source(basis),
        insert_request=first_request,
    )
    old_token = _approve(journal, prepared.intent_id, basis=basis)

    repeated = journal.prepare(
        basis,
        _preview(basis),
        _source(basis),
        insert_request=second_request,
    )
    assert repeated.accepted is False
    assert repeated.reason == "REPREPARE_REQUIRED"

    journal.refuse(
        prepared.intent_id,
        case_id=basis.case_id,
        manager_id=MANAGER,
        reason="bind a newly validated body",
        now=NOW,
    )
    reprepared = journal.reprepare(
        prepared.intent_id,
        basis,
        _preview(basis),
        _source(basis, audit_snapshot_digest="audit-snapshot-v2"),
        insert_request=second_request,
        now=NOW,
    )
    assert reprepared.accepted is True
    assert reprepared.snapshot.intent_version == 2
    assert (
        _claim_insert(journal, prepared.intent_id, basis, old_token).reason == "APPROVAL_REQUIRED"
    )
    new_token = _approve(journal, prepared.intent_id, basis=basis, expected_version=2)
    new_claim = _claim_insert(journal, prepared.intent_id, basis, new_token)
    assert new_claim.granted is True
    assert new_claim.payload["native_request"]["body"]["remarks"] == "mapper-remarks-b"


def test_unknown_insert_never_adopts_a_business_search_candidate_or_allows_submit(
    tmp_path: Path,
) -> None:
    basis = _basis()
    request = _insert_request(basis)
    journal = _journal(tmp_path)
    prepared = journal.prepare(
        basis,
        _preview(basis),
        _source(basis),
        insert_request=request,
    )
    token = _approve(journal, prepared.intent_id, basis=basis)
    assert _claim_insert(journal, prepared.intent_id, basis, token).granted is True

    journal.record_unknown(prepared.intent_id, _readback("UNKNOWN"), now=NOW)
    candidate = _draft(basis, prepared.snapshot.commercial_version, name="PI-CANDIDATE")
    adopted = journal.admit_draft_readback(prepared.intent_id, candidate)
    submit = journal.claim_submit(
        prepared.intent_id,
        case_id=basis.case_id,
        manager_id=MANAGER,
        worker_id="worker-a",
        now=NOW,
    )
    assert adopted.admitted is False
    assert adopted.reason == "INSERT_ACKNOWLEDGEMENT_REQUIRED"
    assert submit.granted is False
    assert submit.reason == "DRAFT_ACKNOWLEDGEMENT_REQUIRED"
    assert (
        _claim_insert(journal, prepared.intent_id, basis, token).reason
        == "INSERT_ALREADY_ATTEMPTED"
    )


def test_acknowledged_draft_binds_the_original_attempt_and_submit_timeout_is_read_only(
    tmp_path: Path,
) -> None:
    basis = _basis()
    request = _insert_request(basis)
    journal = _journal(tmp_path)
    prepared = journal.prepare(
        basis,
        _preview(basis),
        _source(basis),
        insert_request=request,
    )
    token = _approve(journal, prepared.intent_id, basis=basis)
    insert = _claim_insert(journal, prepared.intent_id, basis, token)
    assert insert.attempt_id

    acknowledgement = _acknowledged_draft(request)
    admitted = journal.admit_insert_acknowledgement(prepared.intent_id, acknowledgement)
    assert admitted.admitted is True
    assert admitted.snapshot.draft_name == acknowledgement.draft_name
    submit = journal.claim_submit(
        prepared.intent_id,
        case_id=basis.case_id,
        manager_id=MANAGER,
        worker_id="worker-a",
        now=NOW,
    )
    assert submit.granted is True
    assert submit.payload["native_request"]["body"]["doc"] == acknowledgement.document

    reopened = BillingIntentJournal(tmp_path / "normal-billing.sqlite3")
    admitted_submitted = reopened.admit_submitted_readback(
        prepared.intent_id,
        _submitted_readback(acknowledgement),
    )
    assert admitted_submitted.admitted is True
    assert admitted_submitted.snapshot.submitted_invoice_name == acknowledgement.draft_name
    retry = reopened.claim_submit(
        prepared.intent_id,
        case_id=basis.case_id,
        manager_id=MANAGER,
        worker_id="worker-b",
        now=NOW,
    )
    assert retry.granted is False
    assert retry.reason == "SUBMIT_ALREADY_ATTEMPTED"


def test_read_only_bound_request_and_acknowledged_draft_accessors_survive_restart(
    tmp_path: Path,
) -> None:
    basis = _basis()
    request = _insert_request(basis)
    journal = _journal(tmp_path)
    prepared = journal.prepare(
        basis,
        _preview(basis),
        _source(basis),
        insert_request=request,
    )

    bound = journal.bound_insert_request(prepared.intent_id)
    assert bound is not None
    assert bound.record() == request.record()
    assert journal.acknowledged_draft(prepared.intent_id) is None
    token = _approve(journal, prepared.intent_id, basis=basis)
    assert _claim_insert(journal, prepared.intent_id, basis, token).granted is True
    acknowledgement = _acknowledged_draft(request)
    assert (
        journal.admit_insert_acknowledgement(prepared.intent_id, acknowledgement).admitted is True
    )

    reopened = BillingIntentJournal(tmp_path / "normal-billing.sqlite3")
    reopened_bound = reopened.bound_insert_request(prepared.intent_id)
    reopened_acknowledgement = reopened.acknowledged_draft(prepared.intent_id)

    assert reopened_bound is not None
    assert reopened_bound.record() == request.record()
    assert reopened_acknowledgement is not None
    assert reopened_acknowledgement.record() == acknowledgement.record()
    with pytest.raises(TypeError):
        reopened_bound.body["bill_no"] = "MUTATED"  # type: ignore[index]


def test_read_only_accessors_reject_corrupt_bound_or_acknowledged_evidence(tmp_path: Path) -> None:
    basis = _basis()
    request = _insert_request(basis)
    journal = _journal(tmp_path)
    prepared = journal.prepare(
        basis,
        _preview(basis),
        _source(basis),
        insert_request=request,
    )
    database = tmp_path / "normal-billing.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE normal_receipt_billing_intents SET insert_binding_json = ? WHERE intent_id = ?",
            (json.dumps({"corrupt": "binding"}), prepared.intent_id),
        )
    with pytest.raises(ValueError, match="INSERT_REQUEST_INVALID"):
        journal.bound_insert_request(prepared.intent_id)

    second = BillingIntentJournal(tmp_path / "second.sqlite3")
    second_prepared = second.prepare(
        basis,
        _preview(basis),
        _source(basis),
        insert_request=request,
    )
    token = _approve(second, second_prepared.intent_id, basis=basis)
    assert _claim_insert(second, second_prepared.intent_id, basis, token).granted is True
    assert (
        second.admit_insert_acknowledgement(
            second_prepared.intent_id, _acknowledged_draft(request)
        ).admitted
        is True
    )
    with sqlite3.connect(tmp_path / "second.sqlite3") as connection:
        connection.execute(
            "UPDATE normal_receipt_billing_intents SET draft_readback_json = ? WHERE intent_id = ?",
            (json.dumps({}), second_prepared.intent_id),
        )
    with pytest.raises(ValueError, match="DRAFT_ACKNOWLEDGEMENT_REQUIRED"):
        second.acknowledged_draft(second_prepared.intent_id)


def test_audit_evidence_is_durable_but_does_not_change_the_commercial_fingerprint(
    tmp_path: Path,
) -> None:
    basis = _basis()
    initial = replace(
        _source(basis),
        audit_evidence={
            "source_read": {"related_documents": [{"name": "ACC-PINV-0001"}]},
            "direct_known_document": {"name": "ACC-PINV-0001", "docstatus": 0},
        },
    )
    journal = _journal(tmp_path)
    prepared = journal.prepare(
        basis,
        _preview(basis),
        initial,
        insert_request=_insert_request(basis),
    )
    reopened = BillingIntentJournal(tmp_path / "normal-billing.sqlite3")
    refreshed = replace(
        initial,
        audit_snapshot_digest="audit-snapshot-v2",
        observed_at="2026-09-09T22:05:00Z",
        audit_evidence={
            "source_read": {"related_documents": [{"name": "ACC-PINV-0001"}]},
            "direct_known_document": {"name": "ACC-PINV-0001", "docstatus": 0},
            "pagination_stats": {"pages": 2},
        },
    )

    refresh = reopened.refresh_source(prepared.intent_id, refreshed, now=NOW)
    events = reopened.history(prepared.intent_id)

    assert initial.commercial_record() == refreshed.commercial_record()
    assert initial.record() != refreshed.record()
    assert refresh.commercial_changed is False
    assert refresh.snapshot.source_changed is False
    frozen_audit = refresh.snapshot.frozen_source["audit_evidence"]
    assert frozen_audit["source_read"]["related_documents"][0]["name"] == "ACC-PINV-0001"
    prepared_audit = events[0].payload["source"]["audit_evidence"]
    assert prepared_audit["direct_known_document"]["docstatus"] == 0
    assert events[-1].kind == "SOURCE_REFRESHED"
    refreshed_audit = events[-1].payload["audit_evidence"]
    assert refreshed_audit["pagination_stats"]["pages"] == 2
    with pytest.raises(TypeError):
        cast(dict[str, object], initial.audit_evidence)["source_read"] = {}


def test_two_processes_upgrade_legacy_schema_once_without_hanging(tmp_path: Path) -> None:
    database = tmp_path / "legacy-normal-billing.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE normal_receipt_billing_intents (intent_id TEXT PRIMARY KEY)"
        )

    context = get_context("fork")
    start = context.Event()
    parent_a, child_a = context.Pipe(duplex=False)
    parent_b, child_b = context.Pipe(duplex=False)
    processes = (
        context.Process(target=_process_open_legacy_schema, args=(str(database), start, child_a)),
        context.Process(target=_process_open_legacy_schema, args=(str(database), start, child_b)),
    )
    try:
        for process in processes:
            process.start()
        child_a.close()
        child_b.close()
        start.set()
        assert parent_a.poll(10)
        assert parent_b.poll(10)
        assert parent_a.recv() == (True, None)
        assert parent_b.recv() == (True, None)
        for process in processes:
            process.join(timeout=5)
            assert process.exitcode == 0
    finally:
        start.set()
        for process in processes:
            if process.is_alive():
                process.terminate()
            process.join(timeout=5)
        for pipe in (child_a, child_b, parent_a, parent_b):
            pipe.close()

    with sqlite3.connect(database) as connection:
        columns = [
            row[1]
            for row in connection.execute("PRAGMA table_info(normal_receipt_billing_intents)")
        ]
    assert columns.count("insert_binding_json") == 1
