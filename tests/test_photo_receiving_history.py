"""Offline receiving-history and explicit-submit contracts; no provider writes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.request import Request

import pytest
from test_photo_receiving import ERPTransport, erp, photo, result

from the_missing_20.adapters.photo_receiving import PhotoReceiving
from the_missing_20.agents.photo_receiving import PhotoAssessment


class ReceivingTransport(ERPTransport):
    def __init__(self) -> None:
        super().__init__()
        self.po.update(currency="USD", conversion_rate=1)
        self.submits = 0
        self.lose_submit_ack = False
        self.reject_submit = False
        self.ledger: list[dict[str, Any]] = []

    def __call__(self, request: Request, timeout: float) -> bytes:
        if "frappe.client.submit" in request.full_url:
            assert request.data is not None and self.receipt is not None
            payload = json.loads(request.data)
            assert payload["doc"]["name"] == self.receipt["name"]
            self.submits += 1
            if self.reject_submit:
                raise TimeoutError("request did not commit")
            self.receipt.update(docstatus=1, modified="pr-v2")
            line = self.receipt["items"][0]
            self.ledger = [
                {
                    "name": "SLE-1",
                    "voucher_type": "Purchase Receipt",
                    "voucher_no": "PR-1",
                    "voucher_detail_no": line["name"],
                    "item_code": line["item_code"],
                    "warehouse": line["warehouse"],
                    "actual_qty": line["qty"],
                    "is_cancelled": 0,
                    "company": self.receipt["company"],
                }
            ]
            if self.lose_submit_ack:
                self.lose_submit_ack = False
                raise TimeoutError("response lost after commit")
            return json.dumps({"message": self.receipt}).encode()
        if "Stock%20Ledger%20Entry?" in request.full_url:
            return json.dumps({"data": self.ledger}).encode()
        response = super().__call__(request, timeout)
        if request.method == "POST" and self.receipt is not None:
            self.receipt.update(modified="pr-v1")
            self.receipt["items"][0]["name"] = "pr-line-1"
        return response


def prepared(tmp_path: Path) -> tuple[PhotoReceiving, ReceivingTransport, dict[str, Any]]:
    transport = ReceivingTransport()
    service = PhotoReceiving(
        tmp_path / "photos.sqlite", lambda _: result(), erp=erp(transport), drafts_enabled=True
    )
    capture = service.upload(service.create()["id"], photo())
    return service, transport, service.draft(capture["id"])


def submit(service: PhotoReceiving, state: dict[str, Any], **changes: Any) -> dict[str, Any]:
    arguments = {
        "receipt_name": state["draft"]["name"],
        "expected_version": state["version"],
        "confirm_received": True,
        **changes,
    }
    return service.submit(state["id"], **arguments)


def test_retake_history_and_gallery_survive_restart_without_summing(tmp_path: Path) -> None:
    service = PhotoReceiving(tmp_path / "photos.sqlite", lambda _: result())
    first = service.upload(service.create()["id"], photo())
    original = service.image(first["id"], first["digest"])
    latest = service.upload(first["id"], photo("red"))
    assert latest["image_version"] == 2 and latest["count"] == 2
    assert latest["version"] > first["version"]
    service.db.close()
    restarted = PhotoReceiving(tmp_path / "photos.sqlite", lambda _: result())
    gallery = restarted.list_captures(limit=1)
    assert gallery["total"] == 1 and gallery["captures"] == [latest]
    assert "never" in gallery["count_semantics"]
    history = restarted.history(first["id"])
    assert [state["image_version"] for state in history["versions"]] == [1, 2]
    assert history["versions"][0]["digest"] == first["digest"]
    assert restarted.historical_image(first["id"], 1) == original
    with pytest.raises(ValueError, match="Photo not found"):
        restarted.image(first["id"], first["digest"])


def test_same_photo_in_another_capture_is_not_a_second_receipt(tmp_path: Path) -> None:
    service, transport, first = prepared(tmp_path)
    second = service.upload(service.create()["id"], photo())
    assert second["status"] == "DUPLICATE_EVIDENCE"
    assert second["duplicate_of"] == first["id"]
    with pytest.raises(ValueError, match="not ready"):
        service.draft(second["id"])
    assert transport.writes == 1 and transport.submits == 0


@pytest.mark.parametrize("limit,offset", [(0, 0), (51, 0), (1, -1), (True, 0), (1, 1.5)])
def test_gallery_bounds(tmp_path: Path, limit: Any, offset: Any) -> None:
    service = PhotoReceiving(tmp_path / "photos.sqlite", lambda _: result())
    with pytest.raises(ValueError):
        service.list_captures(limit=limit, offset=offset)


def test_submit_requires_exact_current_user_confirmation_and_verifies_stock(tmp_path: Path) -> None:
    service, transport, state = prepared(tmp_path)
    for changes in (
        {"confirm_received": False},
        {"confirm_received": "true"},
        {"receipt_name": "PR-unrelated"},
        {"expected_version": 0},
    ):
        with pytest.raises(ValueError):
            submit(service, state, **changes)
    assert transport.submits == 0 and transport.writes == 1
    completed = submit(service, state)
    assert completed["status"] == "RECEIPT_SUBMITTED" and completed["stock_posted"]
    assert completed["receipt"]["docstatus"] == 1
    assert completed["receipt"]["stock_ledger"][0]["name"] == "SLE-1"
    assert submit(service, state) == completed
    service.db.close()
    restarted = PhotoReceiving(
        tmp_path / "photos.sqlite", lambda _: result(), erp=erp(transport), drafts_enabled=True
    )
    assert submit(restarted, state) == completed
    assert transport.submits == 1 and transport.writes == 1


def test_submit_lost_ack_reconciles_original_receipt_after_restart(tmp_path: Path) -> None:
    service, transport, state = prepared(tmp_path)
    transport.lose_submit_ack = True
    unknown = submit(service, state)
    assert unknown["status"] == "SUBMIT_UNKNOWN" and not unknown["stock_posted"]
    transport.po["modified"] = "po-after-submission"
    transport.po["items"][0]["received_qty"] = 10
    service.db.close()
    restarted = PhotoReceiving(
        tmp_path / "photos.sqlite", lambda _: result(), erp=erp(transport), drafts_enabled=True
    )
    completed = submit(restarted, unknown)
    assert completed["status"] == "RECEIPT_SUBMITTED"
    assert transport.submits == 1 and transport.writes == 1


def test_uncommitted_unknown_outcome_never_submits_again(tmp_path: Path) -> None:
    service, transport, state = prepared(tmp_path)
    transport.reject_submit = True
    unknown = submit(service, state)
    assert unknown["status"] == "SUBMIT_UNKNOWN"
    transport.reject_submit = False
    retried = submit(service, unknown)
    assert retried["status"] == "SUBMIT_UNKNOWN" and not retried["stock_posted"]
    assert transport.submits == 1 and transport.writes == 1
    assert retried == unknown  # Unchanged lookup does not invent more business events.


@pytest.mark.parametrize("target", ["po", "draft", "configured_po"])
def test_changed_identity_stops_before_submit(tmp_path: Path, target: str) -> None:
    service, transport, state = prepared(tmp_path)
    if target == "po":
        transport.po["modified"] = "po-v2"
    elif target == "draft":
        assert transport.receipt is not None
        transport.receipt["modified"] = "pr-other-version"
    else:
        assert service.erp is not None
        service.erp.purchase_order = "PO-other"
    stopped = submit(service, state)
    assert stopped["status"] == "NEEDS_REVIEW" and not stopped["stock_posted"]
    assert transport.submits == 0 and transport.writes == 1


def test_authoritative_commercial_fields_preserved_without_derived_tax_totals() -> None:
    transport = ReceivingTransport()
    transport.po.update(
        currency="EUR",
        conversion_rate=1.2,
        tc_name="PO terms",
        terms="Net 30",
        taxes_and_charges="EU VAT",
        taxes=[
            {
                "charge_type": "On Net Total",
                "account_head": "VAT - M20",
                "description": "VAT",
                "rate": 20,
                "tax_amount": 40,
                "total": 240,
                "name": "po-tax-row",
            }
        ],
    )
    candidate = erp(transport).candidate(PhotoAssessment.model_validate(result()["assessment"]))
    assert candidate["currency"] == "EUR" and candidate["conversion_rate"] == 1.2
    assert candidate["terms"] == "Net 30" and candidate["tc_name"] == "PO terms"
    assert candidate["taxes"][0]["rate"] == 20
    assert "tax_amount" not in candidate["taxes"][0] and "name" not in candidate["taxes"][0]


@pytest.mark.parametrize("rate", [None, 0, -1, float("nan"), float("inf")])
def test_missing_or_invalid_po_price_never_becomes_invented_money(rate: Any) -> None:
    transport = ReceivingTransport()
    transport.po["items"][0]["rate"] = rate
    with pytest.raises(ValueError, match="rate"):
        erp(transport).candidate(PhotoAssessment.model_validate(result()["assessment"]))


@pytest.mark.parametrize(
    "changed",
    [
        {"voucher_no": "PR-other"},
        {"voucher_detail_no": "line-other"},
        {"item_code": "M20-other"},
        {"warehouse": "Other warehouse"},
        {"company": "Other company"},
        {"is_cancelled": 1},
        {"actual_qty": 1},
        {"actual_qty": -2},
        {"actual_qty": float("nan")},
    ],
)
def test_unrelated_or_inexact_ledger_never_verifies_stock(
    tmp_path: Path, changed: dict[str, Any]
) -> None:
    service, transport, state = prepared(tmp_path)
    transport.lose_submit_ack = True
    unknown = submit(service, state)
    transport.ledger[0].update(changed)
    unverified = submit(service, unknown)
    assert unverified["status"] == "SUBMIT_UNKNOWN" and unverified["stock_posted"] is None
    assert "receipt" not in unverified and transport.submits == 1 and transport.writes == 1


@pytest.mark.parametrize("kind", ["empty", "duplicate", "truncated"])
def test_incomplete_or_duplicate_ledger_never_verifies_stock(tmp_path: Path, kind: str) -> None:
    service, transport, state = prepared(tmp_path)
    transport.lose_submit_ack = True
    unknown = submit(service, state)
    transport.ledger *= {"empty": 0, "duplicate": 2, "truncated": 101}[kind]
    assert submit(service, unknown)["status"] == "SUBMIT_UNKNOWN"
    assert transport.submits == 1


@pytest.mark.parametrize(
    "change",
    [
        {"currency": "EUR"},
        {"conversion_rate": 2},
        {"is_return": 1},
        {"doctype": "Stock Entry"},
        {"supplier_delivery_note": "another capture"},
    ],
)
def test_changed_draft_business_identity_is_not_submitted(
    tmp_path: Path, change: dict[str, Any]
) -> None:
    service, transport, state = prepared(tmp_path)
    assert transport.receipt is not None
    transport.receipt.update(change)
    assert submit(service, state)["status"] == "NEEDS_REVIEW"
    assert transport.submits == 0


@pytest.mark.parametrize("disabled", ["switch", "tenant"])
def test_submit_cannot_bypass_demo_write_scope(tmp_path: Path, disabled: str) -> None:
    service, transport, state = prepared(tmp_path)
    if disabled == "switch":
        service.drafts_enabled = False
        with pytest.raises(ValueError, match="not enabled"):
            submit(service, state)
    else:
        service.erp = erp(transport, environment="production")
        assert submit(service, state)["status"] == "NEEDS_REVIEW"
    assert transport.submits == 0


@pytest.mark.parametrize(
    "change",
    [
        {"discount_amount": 10},
        {"taxes": [{"charge_type": "Actual", "account_head": "Freight", "tax_amount": 20}]},
        {"conversion_rate": float("inf")},
        {"name": "PO-unrelated"},
    ],
)
def test_unsupported_commercial_allocation_or_wrong_po_is_not_guessed(
    change: dict[str, Any],
) -> None:
    transport = ReceivingTransport()
    transport.po.update(change)
    with pytest.raises(ValueError):
        erp(transport).candidate(PhotoAssessment.model_validate(result()["assessment"]))


def test_storage_bound_does_not_destroy_prior_evidence(tmp_path: Path, monkeypatch: Any) -> None:
    service = PhotoReceiving(tmp_path / "photos.sqlite", lambda _: result())
    state = service.upload(service.create()["id"], photo())
    monkeypatch.setattr("the_missing_20.adapters.photo_receiving.MAX_STORED_PHOTO_BYTES", 1)
    with pytest.raises(ValueError, match="storage limit"):
        service.upload(state["id"], photo("red"))
    assert service.current(state["id"]) == state
    assert len(service.history(state["id"])["versions"]) == 1


def test_previous_schema_migrates_only_retained_image_without_inventing_history(
    tmp_path: Path,
) -> None:
    service = PhotoReceiving(tmp_path / "photos.sqlite", lambda _: result())
    state = service.upload(service.create()["id"], photo())
    for key in ("version", "image_version", "count_semantics"):
        state.pop(key)
    service.db.execute("DROP TABLE capture_images")
    service.db.execute("UPDATE captures SET state=? WHERE id=?", (json.dumps(state), state["id"]))
    service.db.commit()
    service.db.close()
    restarted = PhotoReceiving(tmp_path / "photos.sqlite", lambda _: result())
    history = restarted.history(state["id"])
    assert len(history["versions"]) == 1
    assert history["versions"][0]["digest"] == state["digest"]


def test_retake_to_failed_assessment_preserves_original_count_as_history_only(
    tmp_path: Path,
) -> None:
    service = PhotoReceiving(tmp_path / "photos.sqlite", lambda _: result())
    state = service.upload(service.create()["id"], photo())
    service.reader = lambda _: result(visibility="occluded", countable=False, objects=[])
    latest = service.upload(state["id"], photo("red"))
    assert latest["count"] is None and latest["status"] == "NEEDS_PHOTO"
    history = service.history(state["id"])["versions"]
    assert history[0]["count"] == 2 and history[1]["count"] is None


def test_two_instances_cannot_submit_same_confirmation_twice(tmp_path: Path) -> None:
    service, transport, state = prepared(tmp_path)
    other = PhotoReceiving(
        tmp_path / "photos.sqlite", lambda _: result(), erp=erp(transport), drafts_enabled=True
    )
    assert service.erp is not None
    original_preflight = service.erp.submission_document

    def concurrent_preflight(*args: Any, **kwargs: Any) -> dict[str, Any]:
        document = original_preflight(*args, **kwargs)
        assert submit(other, state)["status"] == "RECEIPT_SUBMITTED"
        return document

    service.erp.submission_document = concurrent_preflight  # type: ignore[method-assign]
    with pytest.raises(ValueError, match="Capture changed"):
        submit(service, state)
    assert transport.submits == 1 and transport.writes == 1
    assert service.current(state["id"])["status"] == "RECEIPT_SUBMITTED"


def test_human_missing_identity_is_separate_from_model_and_revalidates_to_submit(
    tmp_path: Path,
) -> None:
    transport = ReceivingTransport()
    service = PhotoReceiving(
        tmp_path / "photos.sqlite",
        lambda _: result(item_code=""),
        erp=erp(transport),
        drafts_enabled=True,
    )
    state = service.upload(service.create()["id"], photo())
    options = service.receiving_identity()
    assert options["purchase_order"] == "PO-1" and options["items"][0]["item_code"] == "M20-TEST"
    confirmed = service.confirm_identity(
        state["id"], item_code="M20-TEST", expected_version=state["version"], confirm_match=True
    )
    assert confirmed["analysis"]["assessment"]["item_code"] == ""
    assert confirmed["identity_confirmation"]["source"] == "explicit_human_confirmation"
    assert confirmed["candidate"]["items"][0]["item_code"] == "M20-TEST"
    assert transport.writes == 0
    service.db.close()
    restarted = PhotoReceiving(
        tmp_path / "photos.sqlite",
        lambda _: result(item_code=""),
        erp=erp(transport),
        drafts_enabled=True,
    )
    draft = restarted.draft(state["id"])
    assert submit(restarted, draft)["status"] == "RECEIPT_SUBMITTED"
    assert transport.writes == transport.submits == 1


@pytest.mark.parametrize(
    "change",
    [
        {"item_code": "M20-OTHER"},
        {"visible_condition": "visible_damage"},
        {"visibility": "occluded"},
        {"countable": False},
        {"receiving_unit": "unknown"},
        {"issues": ["label conflict"]},
    ],
)
def test_identity_confirmation_cannot_bypass_photo_conflicts(
    tmp_path: Path, change: dict[str, Any]
) -> None:
    transport = ReceivingTransport()
    service = PhotoReceiving(
        tmp_path / "photos.sqlite",
        lambda _: result(**{"item_code": "", **change}),
        erp=erp(transport),
        drafts_enabled=True,
    )
    state = service.upload(service.create()["id"], photo())
    with pytest.raises(ValueError):
        service.confirm_identity(
            state["id"], item_code="M20-TEST", expected_version=state["version"], confirm_match=True
        )
    assert transport.writes == 0


def test_identity_confirmation_requires_current_explicit_known_item_and_retake_clears_it(
    tmp_path: Path,
) -> None:
    transport = ReceivingTransport()
    service = PhotoReceiving(
        tmp_path / "photos.sqlite", lambda _: result(item_code=""), erp=erp(transport)
    )
    state = service.upload(service.create()["id"], photo())
    arguments = {
        "item_code": "M20-TEST",
        "expected_version": state["version"],
        "confirm_match": True,
    }
    for change in (
        {"confirm_match": "true"},
        {"expected_version": 0},
        {"item_code": "M20-MISSING"},
    ):
        with pytest.raises(ValueError):
            service.confirm_identity(state["id"], **{**arguments, **change})
    service.confirm_identity(state["id"], **arguments)
    latest = service.upload(state["id"], photo("red"))
    assert "identity_confirmation" not in latest and "candidate" not in latest
    assert latest["status"] == "COUNT_CANDIDATE"
