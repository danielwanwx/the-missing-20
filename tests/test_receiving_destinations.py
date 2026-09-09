"""Provider wire contracts, using recorded-format responses and no network."""

import json
from copy import deepcopy
from threading import Event
from types import SimpleNamespace

import pytest
from test_receiving_handoff import Destination, capture

from the_missing_20.adapters.receiving_destinations import (
    AirtableReceipt,
    CeligoSlackReceipt,
    ReceivingAPI,
)
from the_missing_20.adapters.receiving_handoff import HandoffJournal, receipt_event
from the_missing_20.adapters.receiving_handoff_worker import ReceivingHandoffWorker
from the_missing_20.adapters.saas_evidence import SaaSEvidenceConfig


def api(transport):
    return ReceivingAPI(
        SaaSEvidenceConfig(
            correlation_id="M20-1",
            slack_bot_token="test",
            slack_channel_id="channel-1",
            celigo_api_token="test",
            airtable_token="test",
            airtable_base_id="base-1",
        ),
        transport=transport,
    )


def test_slack_canonical_link_is_read_back_without_resending():
    event = receipt_event(capture())

    def wire(request, timeout):
        assert request.method == "GET"
        if "auth.test" in request.full_url:
            return json.dumps({"ok": True, "user_id": "bot-user"}).encode()
        if "getPermalink" in request.full_url:
            return json.dumps({"ok": True, "permalink": "https://slack.com/record"}).encode()
        text = CeligoSlackReceipt.text(event, "key").replace(
            event["erp_url"], f"<{event['erp_url']}>"
        )
        return json.dumps(
            {"ok": True, "messages": [{"text": text, "user": "bot-user", "ts": "123.123"}]}
        ).encode()

    target = CeligoSlackReceipt(api(wire), "import-1", "connection-1")
    assert target.find(event, "key")["record_id"] == "123.123"


def test_slack_modified_message_or_wrong_author_is_not_verification():
    event = receipt_event(capture())
    for text, user in [
        (CeligoSlackReceipt.text(event, "key"), "other-user"),
        (CeligoSlackReceipt.text(event, "key") + " paid", "bot-user"),
    ]:

        def wire(request, timeout, text=text, user=user):
            return json.dumps(
                {
                    "ok": True,
                    "user_id": "bot-user",
                    "messages": [{"text": text, "user": user, "ts": "123.123"}],
                }
            ).encode()

        with pytest.raises(ValueError, match="content/author"):
            CeligoSlackReceipt(api(wire), "i", "c").find(event, "key")


@pytest.mark.parametrize(
    "payload", [None, [], "bad", {"ok": True, "user_id": "user", "messages": [None]}]
)
def test_malformed_slack_is_a_controlled_failure(payload):
    target = CeligoSlackReceipt(api(lambda *_: json.dumps(payload).encode()), "i", "c")
    with pytest.raises(ValueError):
        target.find(receipt_event(capture()), "key")


@pytest.mark.parametrize(
    "payload", [None, [], "bad", {"records": [None]}, {"records": [{"id": "r", "fields": None}]}]
)
def test_malformed_airtable_is_a_controlled_failure(payload):
    target = AirtableReceipt(api(lambda *_: json.dumps(payload).encode()), "t")
    with pytest.raises(ValueError):
        target.find(receipt_event(capture()), "key")


def test_celigo_200_with_record_error_is_not_success():
    calls = []

    def wire(request, timeout):
        calls.append(request.method)
        if request.method == "GET":
            return json.dumps(
                {
                    "_connectionId": "c",
                    "externalId": "m20-verified-receiving-slack-v1",
                    "maxAttempts": 1,
                    "http": {"relativeURI": ["chat.postMessage"], "method": ["POST"]},
                }
            ).encode()
        return json.dumps([{"statusCode": 200, "errors": [{"message": "denied"}]}]).encode()

    with pytest.raises(ValueError, match="confirm"):
        CeligoSlackReceipt(api(wire), "i", "c").send(receipt_event(capture()), "key")
    assert calls == ["GET", "POST"]


def worker(tmp_path, states, fresh):
    result = ReceivingHandoffWorker.__new__(ReceivingHandoffWorker)
    result.receiving = SimpleNamespace(
        list_captures=lambda **_: {"captures": states},
        _require_scope=lambda _: None,
        erp=SimpleNamespace(submit=lambda *_, **kwargs: deepcopy(fresh)),
    )
    result.journal = HandoffJournal(tmp_path / "outbox.sqlite3")
    target = Destination()
    target.route = "slack:a"
    result.destinations = [target]
    result.jira = None
    result.closed = Event()
    return result, target


@pytest.mark.parametrize(
    "field,value",
    [
        ("quantity", 9),
        ("stock_uom", "Nos"),
        ("stock_ledger", [{"name": "SLE-DIFFERENT"}]),
        ("url", "https://other.invalid"),
    ],
)
def test_worker_rejects_changed_authoritative_receipt(tmp_path, field, value):
    state = {**capture(), "draft": {"name": "PR-1"}}
    fresh = {**state["receipt"], field: value}
    runner, target = worker(tmp_path, [state], fresh)
    runner.tick()
    assert target.writes == 0


@pytest.mark.parametrize(
    "change",
    [
        {},
        {"actual_qty": 2},
        {"warehouse": "Other"},
        {"is_cancelled": 1},
        {"voucher_detail_no": "other-line"},
        {"company": "Other"},
    ],
)
@pytest.mark.parametrize("renamed", [False, True])
def test_erp_background_rename_requires_unchanged_stock_effect(tmp_path, change, renamed):
    state = {**capture(), "draft": {"name": "PR-1"}}
    original = {
        "name": "temporary-hash",
        "voucher_type": "Purchase Receipt",
        "voucher_no": "PR-1",
        "voucher_detail_no": "line-1",
        "item_code": "M20-BOX",
        "warehouse": "Stores",
        "company": "Demo",
        "actual_qty": 1,
        "is_cancelled": 0,
    }
    state["receipt"]["stock_ledger"] = [original]
    current_name = "MAT-SLE-00001" if renamed else original["name"]
    fresh = {**state["receipt"], "stock_ledger": [{**original, "name": current_name, **change}]}
    runner, target = worker(tmp_path, [state], fresh)
    runner.tick()
    assert target.writes == (0 if change else 1)
    assert state["receipt"]["stock_ledger"][0]["name"] == "temporary-hash"


@pytest.mark.parametrize(
    "change",
    [
        {"actual_qty": 2},
        {"voucher_no": "WRONG"},
        {"voucher_type": "Stock Entry"},
        {"item_code": "WRONG"},
    ],
)
def test_matching_ledger_still_requires_receipt_identity_and_quantity(tmp_path, change):
    state = {**capture(), "draft": {"name": "PR-1"}}
    state["receipt"]["stock_ledger"][0].update(change)
    runner, target = worker(tmp_path, [state], state["receipt"])
    runner.tick()
    assert target.writes == 0


def test_renamed_ledger_does_not_allow_duplicate_effect_rows(tmp_path):
    from the_missing_20.adapters.receiving_handoff import same_stock_effects

    row = {
        "voucher_type": "Purchase Receipt",
        "voucher_no": "PR",
        "voucher_detail_no": "line",
        "item_code": "item",
        "warehouse": "Stores",
        "company": "Demo",
        "actual_qty": 1,
        "is_cancelled": 0,
    }
    assert not same_stock_effects([row], [row, row])
    assert not same_stock_effects([row, row], [row, row])
    assert not same_stock_effects([{}], [{}])


def test_worker_skips_malformed_first_capture_and_processes_valid_second(tmp_path):
    state = {**capture(), "draft": {"name": "PR-1"}}
    malformed = deepcopy(state)
    del malformed["work_item"]["arrival_id"]
    runner, target = worker(tmp_path, [malformed, state], state["receipt"])
    runner.tick()
    assert target.writes == 1
    assert runner.journal.for_capture(state["id"])[0]["status"] == "VERIFIED"
    runner.tick()
    assert target.writes == 1


def test_changed_destination_routes_do_not_reuse_old_delivery_success(tmp_path):
    state = {**capture(), "draft": {"name": "PR-1"}}
    runner, current = worker(tmp_path, [state], state["receipt"])
    runner.receiving.arrivals = SimpleNamespace(case_id=state["work_item"]["case_id"])
    old = Destination()
    old.route = "airtable:old-table"
    runner.journal.deliver(old.route, receipt_event(state), old)
    assert runner.projection(state)["handoffs"] == []
    assert runner.sources() == []
    runner.tick()
    assert current.writes == 1
    assert [row["route"] for row in runner.projection(state)["handoffs"]] == [current.route]
    assert len(runner.sources()) == 1
    runner.tick()
    assert current.writes == 1 and old.writes == 1


@pytest.mark.parametrize(
    "change",
    [{"receipt": "bad"}, {"work_item": 4}, {"tenant": None}, {"receipt": {"stock_ledger": [None]}}],
)
def test_receipt_event_is_total_for_malformed_retained_rows(change):
    assert receipt_event({**capture(), **change}) is None
