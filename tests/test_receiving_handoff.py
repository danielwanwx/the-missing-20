"""Deterministic delivery tests; these do not certify real SaaS effects."""

from copy import deepcopy

import pytest

from the_missing_20.adapters.receiving_handoff import HandoffJournal, receipt_event


def event():
    return {
        "tenant": "https://demo.invalid",
        "receipt": "PR-1",
        "case_id": "M20-1",
        "quantity": 1,
        "uom": "Box",
        "purchase_order": "PO-1",
    }


class Destination:
    def __init__(self):
        self.records = {}
        self.writes = 0
        self.lost_ack = False
        self.unavailable = False

    def find(self, payload, key):
        if self.unavailable:
            raise TimeoutError("private provider credential must not be stored")
        return self.records.get(key)

    def send(self, payload, key):
        self.writes += 1
        self.records[key] = {"record_id": "real-record-1", "url": "https://demo.invalid/1"}
        if self.lost_ack:
            raise TimeoutError("response lost")


def test_effect_is_read_back_once_across_restarts(tmp_path):
    target = Destination()
    journal = HandoffJournal(tmp_path / "outbox.sqlite3")
    first = journal.deliver("slack:channel-a", event(), target)
    assert first["status"] == "VERIFIED"
    restarted = HandoffJournal(tmp_path / "outbox.sqlite3")
    assert restarted.deliver("slack:channel-a", event(), target) == first
    assert target.writes == 1


def test_lost_ack_reconciles_without_resending(tmp_path):
    target = Destination()
    target.lost_ack = True
    journal = HandoffJournal(tmp_path / "outbox.sqlite3")
    assert journal.deliver("slack:a", event(), target)["status"] == "UNKNOWN"
    restarted = HandoffJournal(tmp_path / "outbox.sqlite3")
    assert restarted.deliver("slack:a", event(), target)["status"] == "VERIFIED"
    assert target.writes == 1


def test_unknown_without_record_never_resends(tmp_path):
    target = Destination()

    def failed(payload, key):
        target.writes += 1
        raise TimeoutError("not known if accepted")

    target.send = failed
    journal = HandoffJournal(tmp_path / "outbox.sqlite3")
    for _ in range(3):
        state = journal.deliver("slack:a", event(), target)
    assert state["status"] == "UNKNOWN" and target.writes == 1


def test_access_failure_is_visible_without_secrets_or_unsafe_retry(tmp_path):
    from urllib.error import HTTPError

    target = Destination()

    def rejected(payload, key):
        target.writes += 1
        raise HTTPError("https://secret.invalid/token", 401, "private token", {}, None)

    target.send = rejected
    journal = HandoffJournal(tmp_path / "outbox.sqlite3")
    state = journal.deliver("jira:case", event(), target)
    assert state["last_failure"] == {
        "phase": "send", "kind": "access_denied", "http_status": 401,
    }
    assert "secret" not in str(state) and "private" not in str(state)
    assert journal.deliver("jira:case", event(), target)["status"] == "UNKNOWN"
    assert target.writes == 1
    target.records[state["key"]] = {"record_id": "verified-after-readback"}
    state = journal.deliver("jira:case", event(), target)
    assert state["status"] == "VERIFIED" and "last_failure" not in state


def test_recovered_lookup_clears_only_obsolete_warning_without_resend(tmp_path):
    from urllib.error import HTTPError

    target = Destination()

    def uncertain(payload, key):
        target.writes += 1
        raise TimeoutError("uncertain send")

    target.send = uncertain
    journal = HandoffJournal(tmp_path / "outbox.sqlite3")
    first = journal.deliver("jira:case", event(), target)
    assert first["last_failure"]["phase"] == "send"
    assert journal.deliver("jira:case", event(), target)["last_failure"]["phase"] == "send"
    original_find = target.find

    def denied(payload, key):
        raise HTTPError("https://private.invalid", 401, "private", {}, None)

    target.find = denied
    blocked = journal.deliver("jira:case", event(), target)
    assert blocked["last_failure"]["phase"] == "lookup"
    target.find = original_find
    resumed = HandoffJournal(tmp_path / "outbox.sqlite3").deliver("jira:case", event(), target)
    assert resumed["status"] == "UNKNOWN" and "last_failure" not in resumed
    assert resumed["send_failure"]["phase"] == "send" and target.writes == 1


def test_read_outage_before_intent_does_not_write_and_can_resume(tmp_path):
    target = Destination()
    target.unavailable = True
    journal = HandoffJournal(tmp_path / "outbox.sqlite3")
    state = journal.deliver("slack:a", event(), target)
    assert state["status"] == "PENDING" and target.writes == 0
    assert "credential" not in str(state)
    target.unavailable = False
    assert journal.deliver("slack:a", event(), target)["status"] == "VERIFIED"


def test_existing_effect_in_new_runtime_is_reused(tmp_path):
    target = Destination()
    first = HandoffJournal(tmp_path / "one.sqlite3").deliver("slack:a", event(), target)
    second = HandoffJournal(tmp_path / "two.sqlite3").deliver("slack:a", event(), target)
    assert first["key"] == second["key"]
    assert second["status"] == "VERIFIED" and target.writes == 1


def test_same_receipt_changed_payload_is_not_overwritten(tmp_path):
    journal = HandoffJournal(tmp_path / "outbox.sqlite3")
    target = Destination()
    journal.deliver("slack:a", event(), target)
    with pytest.raises(ValueError, match="changed"):
        journal.deliver("slack:a", {**event(), "quantity": 2}, target)
    assert target.writes == 1


def test_two_journals_claim_only_one_write(tmp_path):
    target = Destination()
    one = HandoffJournal(tmp_path / "outbox.sqlite3")
    two = HandoffJournal(tmp_path / "outbox.sqlite3")
    original_send = target.send

    def interleaved(payload, key):
        assert two.deliver("slack:a", payload, target)["status"] == "UNKNOWN"
        original_send(payload, key)

    target.send = interleaved
    assert one.deliver("slack:a", event(), target)["status"] == "VERIFIED"
    assert target.writes == 1


def capture():
    return {
        "status": "RECEIPT_SUBMITTED",
        "id": "capture-1",
        "tenant": "https://demo.invalid",
        "purchase_order": "PO-1",
        "stock_posted": True,
        "work_item": {"case_id": "M20-1", "arrival_id": "A-1", "item_code": "M20-BOX"},
        "candidate": {"items": [{"item_code": "M20-BOX"}]},
        "receipt": {
            "name": "PR-1",
            "docstatus": 1,
            "verified_receipt": True,
            "stock_posted": True,
            "quantity": 1,
            "stock_uom": "Box",
            "url": "https://demo.invalid/app/purchase-receipt/PR-1",
            "verified_at": "2026-09-09T03:00:00+00:00",
            "stock_ledger": [
                {
                    "name": "SLE-1",
                    "voucher_type": "Purchase Receipt",
                    "voucher_no": "PR-1",
                    "voucher_detail_no": "line-1",
                    "item_code": "M20-BOX",
                    "warehouse": "Stores",
                    "company": "Demo",
                    "actual_qty": 1,
                    "is_cancelled": 0,
                }
            ],
        },
    }


def test_only_verified_stock_effect_is_eligible():
    assert receipt_event(capture())["quantity"] == 1
    for change in ({"status": "DRAFT_VERIFIED"}, {"stock_posted": False}, {"work_item": None}):
        assert receipt_event({**capture(), **change}) is None
    state = deepcopy(capture())
    state["receipt"]["stock_ledger"] = []
    assert receipt_event(state) is None
