from __future__ import annotations

from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier, RLock
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import pytest

from the_missing_20.adapters.normal_receipt_billing_coordinator import (
    CoordinatorOperationResult,
    NormalReceiptBillingCoordinator,
)
from the_missing_20.adapters.normal_receipt_billing_journal import BillingIntentJournal
from the_missing_20.adapters.normal_receipt_billing_preview import SyntheticBillingBasis
from the_missing_20.adapters.normal_receipt_billing_source import (
    ERPRequest,
    NormalReceiptBillingSourceRead,
    NormalReceiptBillingSourceReader,
)

MAPPER_PATH = (
    "/api/method/erpnext.stock.doctype.purchase_receipt.purchase_receipt.make_purchase_invoice"
)
INSERT_PATH = "/api/resource/Purchase%20Invoice"
SUBMIT_PATH = "/api/method/frappe.client.submit"
MANAGER = "m20-demo-manager"


def _basis(
    *, case_id: str = "M20-R4-BILL-1", source_revision: str = "r4-read-1"
) -> SyntheticBillingBasis:
    return SyntheticBillingBasis(
        case_id=case_id,
        company="Missing 20 Automotive Demo",
        supplier="M20 Controller Systems Ltd.",
        bill_reference="SUP-BILL-R4-0001",
        bill_date="2026-09-09",
        purchase_order="PUR-ORD-2026-00016",
        purchase_order_item="458j82kp8e",
        purchase_receipt="MAT-PRE-2026-00007",
        purchase_receipt_item="068bbdr0mb",
        item_code="M20-DEMO-CARTON",
        source_revision=source_revision,
        posting_date="2026-09-09",
        credit_to="Creditors - M20",
        expense_account="Stock Received But Not Billed - M20",
    )


def _purchase_order() -> dict[str, Any]:
    basis = _basis()
    return {
        "doctype": "Purchase Order",
        "name": basis.purchase_order,
        "docstatus": 1,
        "modified": "2026-09-09 13:33:06.587269",
        "company": basis.company,
        "supplier": basis.supplier,
        "currency": "USD",
        "discount_amount": 0,
        "rounding_adjustment": 0,
        "taxes": [],
        "items": [
            {
                "doctype": "Purchase Order Item",
                "name": basis.purchase_order_item,
                "item_code": basis.item_code,
                "qty": 40,
                "uom": "Box",
                "stock_uom": "Box",
                "conversion_factor": 1,
                "rate": 50,
                "net_rate": 50,
                "amount": 2000,
                "net_amount": 2000,
                "stock_qty": 40,
                "received_qty": 1,
                "returned_qty": 0,
            }
        ],
    }


def _purchase_receipt() -> dict[str, Any]:
    basis = _basis()
    return {
        "doctype": "Purchase Receipt",
        "name": basis.purchase_receipt,
        "docstatus": 1,
        "modified": "2026-09-09 13:33:06.525238",
        "company": basis.company,
        "supplier": basis.supplier,
        "currency": "USD",
        "discount_amount": 0,
        "rounding_adjustment": 0,
        "is_return": 0,
        "taxes": [],
        "items": [
            {
                "doctype": "Purchase Receipt Item",
                "name": basis.purchase_receipt_item,
                "item_code": basis.item_code,
                "qty": 1,
                "received_qty": 1,
                "rejected_qty": 0,
                "uom": "Box",
                "stock_uom": "Box",
                "conversion_factor": 1,
                "received_stock_qty": 1,
                "stock_qty": 1,
                "returned_qty": 0,
                "rate": 50,
                "net_rate": 50,
                "amount": 50,
                "net_amount": 50,
                "purchase_order": basis.purchase_order,
                "purchase_order_item": basis.purchase_order_item,
            }
        ],
    }


def _mapped_invoice() -> dict[str, Any]:
    basis = _basis()
    return {
        "doctype": "Purchase Invoice",
        "name": None,
        "docstatus": 0,
        "company": basis.company,
        "supplier": basis.supplier,
        "credit_to": basis.credit_to,
        "posting_date": basis.posting_date,
        "currency": "USD",
        "update_stock": 0,
        "is_return": 0,
        "is_paid": 0,
        "paid_amount": 0,
        "write_off_amount": 0,
        "discount_amount": 0,
        "rounding_adjustment": 0,
        "taxes": [],
        "grand_total": 50,
        "items": [
            {
                "doctype": "Purchase Invoice Item",
                "item_code": basis.item_code,
                "qty": 1,
                "received_qty": 1,
                "rejected_qty": 0,
                "uom": "Box",
                "stock_uom": "Box",
                "conversion_factor": 1,
                "rate": 50,
                "net_rate": 50,
                "amount": 50,
                "net_amount": 50,
                "stock_qty": 1,
                "expense_account": basis.expense_account,
                "purchase_order": basis.purchase_order,
                "po_detail": basis.purchase_order_item,
                "purchase_receipt": basis.purchase_receipt,
                "pr_detail": basis.purchase_receipt_item,
            }
        ],
    }


def _related_invoice(
    name: str,
    *,
    bill_reference: str = "OTHER-BILL",
    receipt: str = "MAT-PRE-OTHER",
    receipt_item: str = "pr-other",
    docstatus: int = 0,
) -> dict[str, Any]:
    document = _mapped_invoice()
    document.update(name=name, docstatus=docstatus, bill_no=bill_reference, bill_date="2026-09-09")
    rows = document["items"]
    assert isinstance(rows, list)
    assert isinstance(rows[0], dict)
    rows[0].update(purchase_receipt=receipt, pr_detail=receipt_item)
    return document


def _receipt_return() -> dict[str, Any]:
    document = _purchase_receipt()
    document.update(
        name="MAT-PRE-RETURN-00001",
        is_return=1,
        return_against=_basis().purchase_receipt,
    )
    rows = document["items"]
    assert isinstance(rows, list)
    assert isinstance(rows[0], dict)
    rows[0].update(qty=-1, received_qty=-1, stock_qty=-1, received_stock_qty=-1)
    return document


@dataclass(frozen=True, slots=True)
class _Call:
    path: str
    method: str
    payload: object | None


class _FakeERP:
    """A local mutable ERPRequest fake that also exercises SourceReader discovery."""

    def __init__(self) -> None:
        self.purchase_order = _purchase_order()
        self.purchase_receipt = _purchase_receipt()
        self.mapped_invoice = _mapped_invoice()
        self.invoices: dict[str, dict[str, Any]] = {}
        self.receipts: dict[str, dict[str, Any]] = {}
        self.insert_calls = 0
        self.submit_calls = 0
        self.direct_get_calls = 0
        self.lose_insert_ack = False
        self.lose_submit_ack = False
        self.insert_response_override: object | None = None
        self.use_insert_response_override = False
        self.after_submit: Callable[[], None] | None = None
        self.calls: list[_Call] = []
        self._lock = RLock()

    def __call__(self, path: str, *, method: str = "GET", payload: object | None = None) -> object:
        with self._lock:
            self.calls.append(_Call(path, method, deepcopy(payload)))
            return self._respond(path, method=method, payload=payload)

    def _respond(self, path: str, *, method: str, payload: object | None) -> object:
        parsed = urlparse(path)
        decoded_path = unquote(parsed.path)
        basis = _basis()
        if decoded_path == f"/api/resource/Purchase Order/{basis.purchase_order}":
            return {"data": deepcopy(self.purchase_order)}
        if decoded_path == f"/api/resource/Purchase Receipt/{basis.purchase_receipt}":
            return {"data": deepcopy(self.purchase_receipt)}
        if path == MAPPER_PATH:
            return {"message": deepcopy(self.mapped_invoice)}
        if decoded_path == "/api/resource/Purchase Invoice":
            if method == "POST":
                return self._insert(payload)
            return self._discover(parsed.query, self.invoices)
        if decoded_path == "/api/resource/Purchase Receipt":
            return self._discover(parsed.query, self.receipts)
        if decoded_path.startswith("/api/resource/Purchase Invoice/"):
            self.direct_get_calls += 1
            name = decoded_path.removeprefix("/api/resource/Purchase Invoice/")
            return {"data": deepcopy(self.invoices.get(name))}
        if decoded_path.startswith("/api/resource/Purchase Receipt/"):
            name = decoded_path.removeprefix("/api/resource/Purchase Receipt/")
            return {"data": deepcopy(self.receipts.get(name))}
        if path == SUBMIT_PATH:
            return self._submit(payload)
        raise AssertionError(f"unexpected request: {method} {path}")

    def _discover(self, query: str, documents: dict[str, dict[str, Any]]) -> object:
        offset = int(parse_qs(query).get("limit_start", ["0"])[0])
        names = sorted(documents)
        return {"data": [{"name": name} for name in names[offset : offset + 50]]}

    def _insert(self, payload: object | None) -> object:
        assert isinstance(payload, dict)
        self.insert_calls += 1
        name = f"ACC-PINV-2026-{self.insert_calls:05d}"
        document = deepcopy(payload)
        document.update(
            name=name,
            docstatus=0,
            owner="coordinator@example.test",
            creation="2026-09-09 22:00:00.000000",
            modified="2026-09-09 22:00:00.000000",
        )
        self.invoices[name] = document
        if self.lose_insert_ack:
            raise RuntimeError("insert acknowledgement lost")
        if self.use_insert_response_override:
            return deepcopy(self.insert_response_override)
        return {"data": deepcopy(document)}

    def _submit(self, payload: object | None) -> object:
        assert isinstance(payload, dict)
        document = payload.get("doc")
        assert isinstance(document, dict)
        name = document.get("name")
        assert isinstance(name, str)
        self.submit_calls += 1
        submitted = self.invoices[name]
        submitted["docstatus"] = 1
        submitted["modified"] = "2026-09-09 22:05:00.000000"
        if self.after_submit is not None:
            self.after_submit()
        if self.lose_submit_ack:
            raise RuntimeError("submit acknowledgement lost")
        return {"message": deepcopy(submitted)}


class _FailingSourceReader(NormalReceiptBillingSourceReader):
    def read(self, basis: SyntheticBillingBasis) -> NormalReceiptBillingSourceRead:
        raise RuntimeError("fresh source unavailable")


class _ToggleReaderFactory:
    def __init__(self) -> None:
        self.fail = False

    def __call__(self, request: ERPRequest) -> NormalReceiptBillingSourceReader:
        return (
            _FailingSourceReader(request)
            if self.fail
            else NormalReceiptBillingSourceReader(request)
        )


def _components(
    tmp_path: Path,
    fake: _FakeERP,
    resolver: Callable[[str], SyntheticBillingBasis] | None = None,
) -> tuple[BillingIntentJournal, NormalReceiptBillingCoordinator, Path]:
    database = tmp_path / "normal-billing.sqlite3"
    journal = BillingIntentJournal(database)
    return (
        journal,
        NormalReceiptBillingCoordinator(
            journal,
            resolver or (lambda case_id: _basis(case_id=case_id)),
            fake,
        ),
        database,
    )


def _coordinator(
    tmp_path: Path,
    fake: _FakeERP,
    resolver: Callable[[str], SyntheticBillingBasis] | None = None,
) -> NormalReceiptBillingCoordinator:
    return _components(tmp_path, fake, resolver)[1]


def _approved(
    coordinator: NormalReceiptBillingCoordinator,
    journal: BillingIntentJournal,
) -> tuple[str, str]:
    prepared = coordinator.prepare(_basis().case_id)
    assert prepared.context is not None and prepared.context.ready is True
    assert prepared.prepared is not None and prepared.prepared.accepted is True
    approval = journal.approve(
        prepared.prepared.intent_id,
        case_id=_basis().case_id,
        manager_id=MANAGER,
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    assert approval.granted is True and approval.token is not None
    return prepared.prepared.intent_id, approval.token


def test_red_real_source_context_must_admit_a_prepared_journal_intent(tmp_path: Path) -> None:
    fake = _FakeERP()
    coordinator = _coordinator(tmp_path, fake)

    result = coordinator.prepare(_basis().case_id)

    assert result.context is not None
    assert result.context.ready is True
    assert result.prepared is not None
    assert result.prepared.accepted is True


def test_nominal_insert_restart_submit_and_exact_known_readback(tmp_path: Path) -> None:
    fake = _FakeERP()
    journal, coordinator, database = _components(tmp_path, fake)
    intent_id, token = _approved(coordinator, journal)

    inserted = coordinator.insert(
        intent_id,
        case_id=_basis().case_id,
        manager_id=MANAGER,
        approval_token=token,
        worker_id="insert-worker",
    )

    assert inserted.claim is not None and inserted.claim.granted is True
    assert inserted.admission is not None and inserted.admission.admitted is True
    assert inserted.snapshot.draft_name == "ACC-PINV-2026-00001"
    assert fake.insert_calls == 1

    restarted = NormalReceiptBillingCoordinator(
        BillingIntentJournal(database), lambda case_id: _basis(case_id=case_id), fake
    )
    submitted = restarted.submit(
        intent_id,
        case_id=_basis().case_id,
        manager_id=MANAGER,
        worker_id="submit-worker",
    )

    assert submitted.claim is not None and submitted.claim.granted is True
    assert submitted.admission is not None and submitted.admission.admitted is True
    assert submitted.snapshot.submitted_invoice_name == "ACC-PINV-2026-00001"
    assert fake.insert_calls == 1
    assert fake.submit_calls == 1
    assert fake.direct_get_calls >= 2


def test_submitted_readback_retains_current_raw_source_and_direct_document(tmp_path: Path) -> None:
    fake = _FakeERP()
    journal, coordinator, _ = _components(tmp_path, fake)
    intent_id, token = _approved(coordinator, journal)
    inserted = coordinator.insert(
        intent_id,
        case_id=_basis().case_id,
        manager_id=MANAGER,
        approval_token=token,
        worker_id="insert-worker",
    )
    assert inserted.admission is not None and inserted.admission.admitted is True
    fake.after_submit = lambda: fake.purchase_order.update(audit_marker="after-submit")

    submitted = coordinator.submit(
        intent_id,
        case_id=_basis().case_id,
        manager_id=MANAGER,
        worker_id="submit-worker",
    )

    assert submitted.admission is not None and submitted.admission.admitted is True
    event = next(
        event
        for event in journal.history(intent_id)
        if event.kind == "UNKNOWN"
        and isinstance(event.payload.get("details"), Mapping)
        and event.payload["details"].get("stage") == "submitted_readback_observation"
    )
    details = event.payload["details"]
    assert isinstance(details, Mapping)
    evidence = details["evidence"]
    assert isinstance(evidence, Mapping)
    source = evidence["source_read"]
    assert isinstance(source, Mapping)
    purchase_order = source["purchase_order"]
    assert isinstance(purchase_order, Mapping)
    assert purchase_order["audit_marker"] == "after-submit"
    assert source["evidence_manifest"]
    direct = evidence["direct_known_document"]
    assert isinstance(direct, Mapping)
    assert direct["name"] == "ACC-PINV-2026-00001"
    assert direct["docstatus"] == 1


def test_lost_insert_acknowledgement_cannot_adopt_or_repeat_insert(tmp_path: Path) -> None:
    fake = _FakeERP()
    journal, coordinator, _ = _components(tmp_path, fake)
    intent_id, token = _approved(coordinator, journal)
    fake.lose_insert_ack = True

    first = coordinator.insert(
        intent_id,
        case_id=_basis().case_id,
        manager_id=MANAGER,
        approval_token=token,
        worker_id="insert-worker",
    )
    retry = coordinator.insert(
        intent_id,
        case_id=_basis().case_id,
        manager_id=MANAGER,
        approval_token=token,
        worker_id="other-worker",
    )
    submit = coordinator.submit(
        intent_id,
        case_id=_basis().case_id,
        manager_id=MANAGER,
        worker_id="submit-worker",
    )

    assert first.claim is not None and first.claim.granted is True
    assert first.snapshot.insert_attempted is True
    assert first.snapshot.draft_name is None
    assert first.snapshot.last_readback_kind == "UNKNOWN"
    assert retry.claim is None and retry.reason == "INSERT_ALREADY_ATTEMPTED"
    assert submit.reason == "DRAFT_ACKNOWLEDGEMENT_REQUIRED"
    assert fake.insert_calls == 1
    assert fake.submit_calls == 0
    assert len(fake.invoices) == 1
    assert journal.acknowledged_draft(intent_id) is None


@pytest.mark.parametrize(
    ("envelope", "stage"),
    [
        (
            {
                "data": {
                    "doctype": "Purchase Invoice",
                    "name": "ACC-PINV-UNTRUSTED",
                    "docstatus": 0,
                    "company": "Wrong Company",
                }
            },
            "insert_acknowledgement",
        ),
        ({"message": "missing data"}, "insert_response"),
        ({"data": []}, "insert_response"),
        ({"data": None}, "insert_response"),
    ],
    ids=("invalid_mapping", "missing_data", "list_data", "null_data"),
)
def test_malformed_or_invalid_insert_acknowledgement_envelope_is_retained_without_retry(
    tmp_path: Path,
    envelope: object,
    stage: str,
) -> None:
    fake = _FakeERP()
    journal, coordinator, _ = _components(tmp_path, fake)
    intent_id, token = _approved(coordinator, journal)
    fake.insert_response_override = envelope
    fake.use_insert_response_override = True

    first = coordinator.insert(
        intent_id,
        case_id=_basis().case_id,
        manager_id=MANAGER,
        approval_token=token,
        worker_id="insert-worker",
    )
    retry = coordinator.insert(
        intent_id,
        case_id=_basis().case_id,
        manager_id=MANAGER,
        approval_token=token,
        worker_id="other-worker",
    )

    assert first.claim is not None and first.claim.granted is True
    assert first.admission is None
    assert first.snapshot.draft_name is None
    assert retry.reason == "INSERT_ALREADY_ATTEMPTED"
    assert fake.insert_calls == 1
    event = next(
        event
        for event in journal.history(intent_id)
        if event.kind == "UNKNOWN"
        and isinstance(event.payload.get("details"), Mapping)
        and event.payload["details"].get("stage") == stage
    )
    details = event.payload["details"]
    assert isinstance(details, Mapping)
    evidence = details["evidence"]
    assert isinstance(evidence, Mapping)
    response = evidence["insert_response"]
    assert isinstance(response, Mapping)
    if isinstance(envelope, Mapping) and isinstance(envelope.get("data"), list):
        expected_data = envelope["data"]
        assert isinstance(expected_data, list)
        assert response["envelope"] == {"data": tuple(expected_data)}
    else:
        assert response["envelope"] == envelope


def test_lost_submit_acknowledgement_reconciles_without_resubmit(tmp_path: Path) -> None:
    fake = _FakeERP()
    journal, coordinator, _ = _components(tmp_path, fake)
    intent_id, token = _approved(coordinator, journal)
    inserted = coordinator.insert(
        intent_id,
        case_id=_basis().case_id,
        manager_id=MANAGER,
        approval_token=token,
        worker_id="insert-worker",
    )
    assert inserted.admission is not None and inserted.admission.admitted is True
    fake.lose_submit_ack = True

    first = coordinator.submit(
        intent_id,
        case_id=_basis().case_id,
        manager_id=MANAGER,
        worker_id="submit-worker",
    )
    replay = coordinator.submit(
        intent_id,
        case_id=_basis().case_id,
        manager_id=MANAGER,
        worker_id="other-submit-worker",
    )

    assert first.claim is not None and first.claim.granted is True
    assert first.admission is not None and first.admission.admitted is True
    assert first.reason is None
    assert first.snapshot.submitted_invoice_name == "ACC-PINV-2026-00001"
    assert replay.claim is None
    assert replay.admission is not None and replay.admission.admitted is True
    assert fake.insert_calls == 1
    assert fake.submit_calls == 1


def test_submit_marker_attempts_direct_get_when_fresh_reconcile_source_throws(
    tmp_path: Path,
) -> None:
    fake = _FakeERP()
    factory = _ToggleReaderFactory()
    database = tmp_path / "normal-billing.sqlite3"
    journal = BillingIntentJournal(database)
    coordinator = NormalReceiptBillingCoordinator(
        journal,
        lambda case_id: _basis(case_id=case_id),
        fake,
        reader_factory=factory,
    )
    intent_id, token = _approved(coordinator, journal)
    inserted = coordinator.insert(
        intent_id,
        case_id=_basis().case_id,
        manager_id=MANAGER,
        approval_token=token,
        worker_id="insert-worker",
    )
    assert inserted.admission is not None and inserted.admission.admitted is True
    direct_count_at_marker: list[int] = []

    def fail_reconcile_source() -> None:
        direct_count_at_marker.append(fake.direct_get_calls)
        factory.fail = True

    fake.after_submit = fail_reconcile_source
    submitted = coordinator.submit(
        intent_id,
        case_id=_basis().case_id,
        manager_id=MANAGER,
        worker_id="submit-worker",
    )

    assert submitted.claim is not None and submitted.claim.granted is True
    assert submitted.admission is None
    assert submitted.snapshot.submit_attempted is True
    assert submitted.snapshot.submitted_invoice_name is None
    assert submitted.snapshot.last_readback_kind == "UNKNOWN"
    assert submitted.reason is not None and "SOURCE_READ_RuntimeError" in submitted.reason
    assert direct_count_at_marker == [fake.direct_get_calls - 1]
    assert fake.submit_calls == 1


@pytest.mark.parametrize("block", ["foreign_bill", "receipt_return", "source_changed"])
def test_acknowledged_draft_still_blocks_submit_on_fresh_source(tmp_path: Path, block: str) -> None:
    fake = _FakeERP()
    journal, coordinator, _ = _components(tmp_path, fake)
    intent_id, token = _approved(coordinator, journal)
    inserted = coordinator.insert(
        intent_id,
        case_id=_basis().case_id,
        manager_id=MANAGER,
        approval_token=token,
        worker_id="insert-worker",
    )
    assert inserted.admission is not None and inserted.admission.admitted is True
    if block == "foreign_bill":
        fake.invoices["ACC-PINV-FOREIGN-00001"] = _related_invoice(
            "ACC-PINV-FOREIGN-00001",
            bill_reference=_basis().bill_reference,
        )
    elif block == "receipt_return":
        fake.receipts["MAT-PRE-RETURN-00001"] = _receipt_return()
    else:
        fake.purchase_order["modified"] = "2026-09-09 23:00:00.000000"

    submitted = coordinator.submit(
        intent_id,
        case_id=_basis().case_id,
        manager_id=MANAGER,
        worker_id="submit-worker",
    )

    assert submitted.claim is None
    assert fake.submit_calls == 0
    if block == "source_changed":
        assert submitted.reason == "COMMERCIAL_SOURCE_CHANGED"
        assert submitted.snapshot.source_changed is True
    else:
        assert submitted.context is not None and submitted.context.ready is False
        assert submitted.snapshot.last_readback_kind == "UNKNOWN"


@pytest.mark.parametrize("block", ["foreign_bill", "receipt_return", "source_changed"])
def test_fresh_source_blocks_before_insert_without_transport(tmp_path: Path, block: str) -> None:
    fake = _FakeERP()
    journal, coordinator, _ = _components(tmp_path, fake)
    intent_id, token = _approved(coordinator, journal)
    if block == "foreign_bill":
        fake.invoices["ACC-PINV-FOREIGN-00001"] = _related_invoice(
            "ACC-PINV-FOREIGN-00001",
            bill_reference=_basis().bill_reference,
        )
    elif block == "receipt_return":
        fake.receipts["MAT-PRE-RETURN-00001"] = _receipt_return()
    else:
        fake.purchase_order["modified"] = "2026-09-09 23:00:00.000000"

    result = coordinator.insert(
        intent_id,
        case_id=_basis().case_id,
        manager_id=MANAGER,
        approval_token=token,
        worker_id="insert-worker",
    )

    assert result.claim is None
    assert fake.insert_calls == 0
    if block == "source_changed":
        assert result.reason == "COMMERCIAL_SOURCE_CHANGED"
        assert result.snapshot.source_changed is True
    else:
        assert result.context is not None and result.context.ready is False
        assert result.snapshot.last_readback_kind == "UNKNOWN"


def test_case_and_frozen_basis_mismatch_do_not_read_or_write(tmp_path: Path) -> None:
    fake = _FakeERP()
    journal, coordinator, _ = _components(tmp_path, fake)
    intent_id, token = _approved(coordinator, journal)
    before = len(fake.calls)

    wrong_case = coordinator.insert(
        intent_id,
        case_id="M20-WRONG-CASE",
        manager_id=MANAGER,
        approval_token=token,
        worker_id="insert-worker",
    )
    changed_basis = NormalReceiptBillingCoordinator(
        journal,
        lambda case_id: _basis(case_id=case_id, source_revision="different-source-revision"),
        fake,
    ).insert(
        intent_id,
        case_id=_basis().case_id,
        manager_id=MANAGER,
        approval_token=token,
        worker_id="insert-worker",
    )

    assert wrong_case.reason == "CASE_MISMATCH"
    assert changed_basis.reason == "FROZEN_BASIS_MISMATCH"
    assert len(fake.calls) == before
    assert fake.insert_calls == 0


def test_shared_journal_claim_race_sends_one_insert(tmp_path: Path) -> None:
    fake = _FakeERP()
    journal, coordinator, _ = _components(tmp_path, fake)
    intent_id, token = _approved(coordinator, journal)
    barrier = Barrier(2)

    def claim(worker_id: str) -> CoordinatorOperationResult:
        barrier.wait(timeout=5)
        return coordinator.insert(
            intent_id,
            case_id=_basis().case_id,
            manager_id=MANAGER,
            approval_token=token,
            worker_id=worker_id,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(claim, "race-one")
        second = pool.submit(claim, "race-two")
        results = [first.result(timeout=5), second.result(timeout=5)]

    granted = [result for result in results if result.claim is not None and result.claim.granted]
    assert len(granted) == 1
    assert fake.insert_calls == 1
    assert journal.get(intent_id).insert_attempted is True
