"""Business identity tests, not photo accuracy or live ERP acceptance."""

import json
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from urllib.parse import parse_qs, unquote, urlparse

import pytest
from test_photo_receiving import ERPTransport, erp, photo, result
from test_photo_receiving_history import submit

from the_missing_20.adapters.photo_receiving import PhotoReceiving


class MultiReceiptTransport(ERPTransport):
    """Stores independent receipts; the older single-document fake hid duplicates."""

    def __init__(self):
        super().__init__()
        self.po.update(currency="USD", conversion_rate=1)
        self.receipts = {}
        self.ledger = []
        self.submits = 0
        self.lose_submit_ack = False

    def __call__(self, request, timeout):
        url = urlparse(request.full_url)
        path = unquote(url.path)
        if "Purchase Order/" in path:
            return json.dumps({"data": self.po}).encode()
        if "frappe.client.submit" in path:
            doc = self.receipts[json.loads(request.data)["doc"]["name"]]
            self.submits += 1
            doc.update(docstatus=1, modified="submitted")
            line = doc["items"][0]
            self.po["items"][0]["received_qty"] += line["qty"]
            self.ledger.append(
                {
                    "name": f"SLE-{self.submits}",
                    "voucher_type": "Purchase Receipt",
                    "voucher_no": doc["name"],
                    "voucher_detail_no": line["name"],
                    "item_code": line["item_code"],
                    "warehouse": line["warehouse"],
                    "actual_qty": line["qty"],
                    "company": doc["company"],
                    "is_cancelled": 0,
                }
            )
            if self.lose_submit_ack:
                self.lose_submit_ack = False
                raise TimeoutError("committed but ACK lost")
            return json.dumps({"message": doc}).encode()
        if path.endswith("Purchase Receipt") and request.method == "POST":
            self.writes += 1
            doc = json.loads(request.data)
            doc.update(name=f"PR-{self.writes}", modified="draft")
            doc["items"][0]["name"] = f"line-{self.writes}"
            self.receipts[doc["name"]] = doc
            return json.dumps({"data": doc}).encode()
        if "/Purchase Receipt/" in path:
            return json.dumps({"data": self.receipts[path.rsplit("/", 1)[1]]}).encode()
        rows = self.ledger if "Stock Ledger Entry" in path else list(self.receipts.values())
        filters = json.loads(parse_qs(url.query)["filters"][0])
        for field, operator, value in filters:
            assert operator == "="
            rows = [row for row in rows if row.get(field) == value]
        return json.dumps({"data": rows}).encode()


def manifest():
    return {
        "case_id": "M20-ARRIVAL-TEST",
        "purchase_order": "PO-1",
        "arrivals": [
            {
                "arrival_id": "delivery-A",
                "purchase_order_item": "line-1",
                "item_code": "M20-TEST",
                "uom": "Nos",
                "warehouse": "M20 Stores",
                "handling_unit_ids": ["box-01", "box-02"],
                "origin": "demo_scan",
            },
            {
                "arrival_id": "delivery-B",
                "purchase_order_item": "line-1",
                "item_code": "M20-TEST",
                "uom": "Nos",
                "warehouse": "M20 Stores",
                "handling_unit_ids": ["box-03", "box-04"],
                "origin": "demo_scan",
            },
        ],
    }


def service_at(path, transport, **kwargs):
    return PhotoReceiving(
        path,
        lambda _: result(),
        erp=erp(transport),
        drafts_enabled=True,
        manifest=manifest(),
        **kwargs,
    )


def test_photo_automatically_prepares_but_never_posts_receipt(tmp_path):
    transport = MultiReceiptTransport()
    service = service_at(tmp_path / "db", transport, auto_prepare=True)
    state = service.upload(service.create(arrival_id="delivery-A")["id"], photo())
    assert state["status"] == "DRAFT_VERIFIED"
    assert transport.writes == 1 and transport.submits == 0
    assert transport.ledger == []
    assert not state["stock_posted"]
    service.prepare_next_draft()
    assert transport.writes == 1


def test_restart_prepares_persisted_candidate_once_and_leaves_posting_to_human(tmp_path):
    transport = MultiReceiptTransport()
    path = tmp_path / "db"
    service = service_at(path, transport)
    state = service.upload(service.create(arrival_id="delivery-A")["id"], photo())
    assert state["status"] == "RECEIPT_PREPARED"
    service.db.close()
    restarted = service_at(path, transport, auto_prepare=True)
    restarted.prepare_next_draft()
    assert restarted.current(state["id"])["status"] == "DRAFT_VERIFIED"
    restarted.prepare_next_draft()
    assert transport.writes == 1 and transport.submits == 0


def test_unclear_photo_and_unbound_receiving_cannot_auto_draft(tmp_path):
    transport = MultiReceiptTransport()
    service = service_at(tmp_path / "db", transport, auto_prepare=True)
    service.reader = lambda _: result(visibility="occluded")
    state = service.upload(service.create(arrival_id="delivery-A")["id"], photo())
    service.prepare_next_draft()
    assert state["status"] != "DRAFT_VERIFIED"
    assert transport.writes == 0
    with pytest.raises(ValueError, match="manifest"):
        PhotoReceiving(
            tmp_path / "other",
            lambda _: result(),
            erp=erp(transport),
            drafts_enabled=True,
            auto_prepare=True,
        )


def test_auto_draft_unknown_after_lost_ack_reconciles_on_restart_without_rewrite(tmp_path):
    transport = MultiReceiptTransport()
    service = service_at(tmp_path / "db", transport, auto_prepare=True)
    original = service.erp.draft

    def lost_ack(*args, **kwargs):
        original(*args, **kwargs)
        raise TimeoutError("ERP committed but reply was lost")

    service.erp.draft = lost_ack
    state = service.upload(service.create(arrival_id="delivery-A")["id"], photo())
    assert state["status"] == "DRAFT_UNKNOWN" and transport.writes == 1
    service.db.close()
    restarted = service_at(tmp_path / "db", transport, auto_prepare=True)
    restarted.prepare_next_draft()
    assert restarted.current(state["id"])["status"] == "DRAFT_VERIFIED"
    assert transport.writes == 1 and transport.submits == 0


def test_two_auto_draft_workers_issue_only_one_external_create(tmp_path):
    transport = MultiReceiptTransport()
    first = service_at(tmp_path / "db", transport)
    state = first.upload(first.create(arrival_id="delivery-A")["id"], photo())
    first.auto_prepare = True
    second = service_at(tmp_path / "db", transport, auto_prepare=True)

    def advance(service):
        with suppress(ValueError):
            service.prepare_next_draft()

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(advance, (first, second)))
    assert first.current(state["id"])["status"] == "DRAFT_VERIFIED"
    assert transport.writes == 1 and transport.submits == 0


def test_pending_photo_cannot_silently_switch_erp_order(tmp_path):
    transport = MultiReceiptTransport()
    service = PhotoReceiving(tmp_path / "db", lambda _: result(), erp=erp(transport))
    initial = service.create()
    service.erp.purchase_order = "PO-other"
    transport.po["name"] = "PO-other"
    state = service.upload(initial["id"], photo())
    assert state["status"] == "NEEDS_REVIEW"
    assert "candidate" not in state
    assert transport.writes == 0


def test_different_view_reopen_and_restart_use_one_arrival_action(tmp_path):
    transport = MultiReceiptTransport()
    service = service_at(tmp_path / "db", transport)
    first = service.create(arrival_id="delivery-A")
    observed = service.upload(first["id"], photo())
    # Reopening a delivery is not a new accounting operation.
    second = service.create(arrival_id="delivery-A")
    assert second["id"] == first["id"]
    retake = service.upload(second["id"], photo("red"))
    assert retake["image_version"] == 2
    completed = submit(service, service.draft(second["id"]))
    assert completed["status"] == "RECEIPT_SUBMITTED"
    service.db.close()
    restarted = service_at(tmp_path / "db", transport)
    assert restarted.create(arrival_id="delivery-A")["receipt"] == completed["receipt"]
    with pytest.raises(ValueError, match="draft"):
        restarted.upload(first["id"], photo("blue"))
    assert transport.writes == transport.submits == 1
    assert observed["work_item"]["case_id"] == "M20-ARRIVAL-TEST"


def test_second_real_arrival_with_same_sku_can_receive(tmp_path):
    transport = MultiReceiptTransport()
    service = service_at(tmp_path / "db", transport)
    names = []
    for arrival, color in [("delivery-A", "white"), ("delivery-B", "red")]:
        state = service.upload(service.create(arrival_id=arrival)["id"], photo(color))
        completed = submit(service, service.draft(state["id"]))
        assert completed["status"] == "RECEIPT_SUBMITTED"
        names.append(completed["receipt"]["name"])
    assert names == ["PR-1", "PR-2"]
    assert transport.po["items"][0]["received_qty"] == 4


def test_lost_ack_reopens_original_arrival_after_restart(tmp_path):
    transport = MultiReceiptTransport()
    service = service_at(tmp_path / "db", transport)
    state = service.upload(service.create(arrival_id="delivery-A")["id"], photo())
    transport.lose_submit_ack = True
    unknown = submit(service, service.draft(state["id"]))
    assert unknown["status"] == "SUBMIT_UNKNOWN"
    service.db.close()
    restarted = service_at(tmp_path / "db", transport)
    recovered = submit(restarted, restarted.create(arrival_id="delivery-A"))
    assert recovered["status"] == "RECEIPT_SUBMITTED"
    assert transport.writes == transport.submits == 1


@pytest.mark.parametrize("committed", [True, False])
def test_worker_reconciles_confirmed_unknown_submit_without_resending(tmp_path, committed):
    transport = MultiReceiptTransport()
    service = service_at(tmp_path / "db", transport)
    state = service.upload(service.create(arrival_id="delivery-A")["id"], photo())
    draft = service.draft(state["id"])
    if committed:
        transport.lose_submit_ack = True
    else:
        service.erp.submit = lambda *a, **kw: (_ for _ in ()).throw(TimeoutError("not sent"))
    unknown = submit(service, draft)
    assert unknown["status"] == "SUBMIT_UNKNOWN"
    service.db.close()
    restarted = service_at(tmp_path / "db", transport)
    for _ in range(3):
        restarted.reconcile_next_submission()
    recovered = restarted.current(state["id"])
    assert recovered["status"] == ("RECEIPT_SUBMITTED" if committed else "SUBMIT_UNKNOWN")
    assert transport.writes == 1 and transport.submits == int(committed)


def test_worker_never_invents_a_first_receiving_confirmation(tmp_path):
    transport = MultiReceiptTransport()
    service = service_at(tmp_path / "db", transport, auto_prepare=True)
    state = service.upload(service.create(arrival_id="delivery-A")["id"], photo())
    service.reconcile_next_submission()
    assert service.current(state["id"])["status"] == "DRAFT_VERIFIED"
    assert transport.submits == 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("physical_receiving_confirmation", None),
        ("draft", []),
        ("candidate", None),
        ("work_item", "invalid"),
    ],
)
def test_reconciliation_skips_malformed_intent_and_progresses_next_record(tmp_path, field, value):
    transport = MultiReceiptTransport()
    service = service_at(tmp_path / "db", transport)
    captures = []
    for arrival, color in [("delivery-A", "white"), ("delivery-B", "red")]:
        state = service.upload(service.create(arrival_id=arrival)["id"], photo(color))
        draft = service.draft(state["id"])
        transport.lose_submit_ack = True
        captures.append(submit(service, draft))
    bad, good = sorted(captures, key=lambda state: state["id"])
    bad[field] = value
    service.db.execute("UPDATE captures SET state=? WHERE id=?", (json.dumps(bad), bad["id"]))
    service.db.commit()
    service.db.close()
    restarted = service_at(tmp_path / "db", transport)
    restarted.reconcile_next_submission()
    restarted.reconcile_next_submission()
    assert restarted.current(bad["id"])["status"] == "SUBMIT_UNKNOWN"
    assert restarted.current(good["id"])["status"] == "RECEIPT_SUBMITTED"
    assert transport.submits == transport.writes == 2


def test_same_box_cannot_be_registered_in_two_arrivals(tmp_path):
    data = manifest()
    data["arrivals"][1]["handling_unit_ids"] = ["box-02", "box-03"]
    with pytest.raises(ValueError, match="handling unit"):
        PhotoReceiving(
            tmp_path / "db", lambda _: result(), erp=erp(MultiReceiptTransport()), manifest=data
        )


def test_case_manifest_cannot_be_rebound_after_restart(tmp_path):
    transport = MultiReceiptTransport()
    service_at(tmp_path / "db", transport).db.close()
    data = manifest()
    data["arrivals"][0]["handling_unit_ids"] = ["different-1", "different-2"]
    with pytest.raises(ValueError, match="changed"):
        PhotoReceiving(tmp_path / "db", lambda _: result(), erp=erp(transport), manifest=data)


def test_photo_count_or_item_cannot_overwrite_registered_arrival(tmp_path):
    service = service_at(tmp_path / "db", MultiReceiptTransport())
    service.reader = lambda _: result(objects=[{"x": 0.5, "y": 0.5, "description": "one"}])
    state = service.upload(service.create(arrival_id="delivery-A")["id"], photo())
    assert state["status"] == "NEEDS_REVIEW" and "candidate" not in state


def test_configured_pilot_requires_known_arrival(tmp_path):
    service = service_at(tmp_path / "db", MultiReceiptTransport())
    for key in (None, "made-up"):
        with pytest.raises(ValueError, match="arrival"):
            service.create(arrival_id=key)


def scan(event_id="scan-1", arrival="delivery-A", unit="box-01"):
    return {
        "source_event_id": event_id,
        "arrival_id": arrival,
        "handling_unit_id": unit,
        "occurred_at": "2026-09-08T09:00:00+00:00",
    }


def test_scan_redelivery_and_same_physical_unit_do_not_add(tmp_path):
    transport = MultiReceiptTransport()
    service = service_at(tmp_path / "db", transport)
    first = service.scan(scan())
    assert service.scan(scan()) == first
    service.scan(scan(event_id="scan-2"))
    service.db.close()
    restarted = service_at(tmp_path / "db", transport)
    evidence = restarted.receiving_work("M20-ARRIVAL-TEST", "PO-1")
    assert evidence["arrivals"][0]["observed_quantity"] == 1
    assert evidence["arrivals"][0]["posted_quantity"] is None
    assert transport.writes == transport.submits == 0
    assert restarted.receiving_work("OTHER-CASE", "PO-1")["arrivals"] == []


def test_cross_case_conflict_response_does_not_return_original_case_payload(tmp_path):
    path = tmp_path / "db"
    transport = MultiReceiptTransport()
    original = service_at(path, transport)
    capture = original.create(arrival_id="delivery-A")
    original.scan(scan())
    before = original.current(capture["id"])["version"]
    other_manifest = manifest()
    other_manifest["case_id"] = "OTHER-CASE"
    other_manifest["arrivals"][0]["arrival_id"] = "other-arrival"
    other_manifest["arrivals"][0]["handling_unit_ids"] = ["other-01", "other-02"]
    other_manifest["arrivals"] = other_manifest["arrivals"][:1]
    other = PhotoReceiving(
        path,
        lambda _: result(),
        erp=erp(transport),
        drafts_enabled=True,
        manifest=other_manifest,
    )
    response = other.scan(scan(arrival="other-arrival", unit="other-01"))
    assert response == {
        "status": "CONFLICT",
        "source_event_id": "scan-1",
        "inventory_changed": False,
    }
    assert original.current(capture["id"])["version"] == before + 1
    work = other.receiving_work("OTHER-CASE", "PO-1")["arrivals"][0]
    assert work["scans"]["status"] == "CONFLICT"
    assert work["scans"]["events"] == []
    assert work["scans"]["conflicts"][0]["source_event_id"] == "scan-1"
    assert "box-01" not in json.dumps(work)
    assert "M20-ARRIVAL-TEST" not in json.dumps(work)


def test_changed_event_payload_preserves_conflict_and_blocks_draft(tmp_path):
    transport = MultiReceiptTransport()
    service = service_at(tmp_path / "db", transport)
    service.scan(scan())
    changed = service.scan(scan(unit="box-02"))
    assert changed["status"] == "CONFLICT"
    assert changed["event"]["handling_unit_id"] == "box-01"
    state = service.upload(service.create(arrival_id="delivery-A")["id"], photo())
    assert state["status"] == "NEEDS_REVIEW" and transport.writes == 0
    assert (
        service.receiving_work("M20-ARRIVAL-TEST", "PO-1")["arrivals"][0]["observed_quantity"]
        is None
    )


def test_scan_then_photo_is_same_observation_not_sum(tmp_path):
    service = service_at(tmp_path / "db", MultiReceiptTransport())
    service.scan(scan())
    service.scan(scan(event_id="scan-2", unit="box-02"))
    service.upload(service.create(arrival_id="delivery-A")["id"], photo())
    evidence = service.receiving_work("M20-ARRIVAL-TEST", "PO-1")
    assert evidence["arrivals"][0]["observed_quantity"] == 2


def test_two_service_instances_resolve_same_operation(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    transport = MultiReceiptTransport()
    one, two = (service_at(tmp_path / "db", transport) for _ in range(2))
    with ThreadPoolExecutor(max_workers=2) as executor:
        states = list(
            executor.map(lambda service: service.create(arrival_id="delivery-A"), [one, two])
        )
    assert states[0]["id"] == states[1]["id"]
    assert one.list_captures()["total"] == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"handling_unit_id": "M20-TEST"},
        {"occurred_at": "2026-09-08T09:00:00"},
        {"arrival_id": "unknown"},
    ],
)
def test_invalid_scan_never_changes_business_state(tmp_path, changes):
    service = service_at(tmp_path / "db", MultiReceiptTransport())
    with pytest.raises(ValueError):
        service.scan({**scan(), **changes})
    assert (
        service.receiving_work("M20-ARRIVAL-TEST", "PO-1")["arrivals"][0]["observed_quantity"] == 0
    )


def test_removing_manifest_cannot_downgrade_receipt_identity(tmp_path):
    service_at(tmp_path / "db", MultiReceiptTransport()).db.close()
    with pytest.raises(ValueError, match="manifest is required"):
        PhotoReceiving(
            tmp_path / "db",
            lambda _: result(),
            erp=erp(MultiReceiptTransport()),
            drafts_enabled=True,
        )


def test_conflicting_scan_during_erp_preflight_invalidates_confirmation(tmp_path):
    transport = MultiReceiptTransport()
    service = service_at(tmp_path / "db", transport)
    service.scan(scan())
    captured = service.upload(service.create(arrival_id="delivery-A")["id"], photo())
    draft = service.draft(captured["id"])
    original = service.erp.submission_document

    def concurrent_change(*args):
        document = original(*args)
        service.scan(scan(unit="box-02"))
        return document

    service.erp.submission_document = concurrent_change
    with pytest.raises(ValueError, match="changed"):
        submit(service, draft)
    assert transport.submits == 0
    assert not service.current(captured["id"]).get("submit_attempted")


@pytest.mark.parametrize("other_arrival", ["delivery-A", "different-arrival"])
def test_cross_case_event_conflict_invalidates_original_work(tmp_path, other_arrival):
    transport = MultiReceiptTransport()
    path = tmp_path / "db"
    original = service_at(path, transport)
    original.scan(scan())
    captured = original.upload(original.create(arrival_id="delivery-A")["id"], photo())
    draft = original.draft(captured["id"])
    other_manifest = manifest()
    other_manifest["case_id"] = "other-case"
    other_manifest["arrivals"][0]["arrival_id"] = other_arrival
    other_manifest["arrivals"] = other_manifest["arrivals"][:1]
    other_manifest["arrivals"][0]["handling_unit_ids"] = ["other-01", "other-02"]
    other = PhotoReceiving(
        path, lambda _: result(), erp=erp(transport), drafts_enabled=True, manifest=other_manifest
    )
    lookup = original.erp.submission_document

    def concurrent_change(*args):
        document = lookup(*args)
        event = scan()
        event["arrival_id"] = other_arrival
        event["handling_unit_id"] = "other-01"
        assert other.scan(event)["status"] == "CONFLICT"
        return document

    original.erp.submission_document = concurrent_change
    with pytest.raises(ValueError, match="changed"):
        submit(original, draft)
    assert transport.submits == 0
    assert original.arrivals.scans("delivery-A")["status"] == "CONFLICT"


def test_scan_after_submit_intent_keeps_scan_and_verified_receipt(tmp_path):
    transport = MultiReceiptTransport()
    path = tmp_path / "db"
    first = service_at(path, transport)
    second = service_at(path, transport)
    captured = first.upload(first.create(arrival_id="delivery-A")["id"], photo())
    draft = first.draft(captured["id"])
    original = first.erp.submit

    def scan_during_write(*args, **kwargs):
        second.scan(scan())
        return original(*args, **kwargs)

    first.erp.submit = scan_during_write
    completed = submit(first, draft)
    assert completed["status"] == "RECEIPT_SUBMITTED"
    assert completed["stock_posted"] is True
    assert any("Scan recorded" in item["detail"] for item in completed["events"])
    repeated = submit(first, draft)
    assert repeated["receipt"] == completed["receipt"]
    assert transport.submits == 1


def test_starting_instance_cannot_overwrite_interleaved_submission(tmp_path, monkeypatch):
    import the_missing_20.adapters.photo_receiving as module

    transport = MultiReceiptTransport()
    path = tmp_path / "db"
    first = service_at(path, transport)
    captured = first.upload(first.create(arrival_id="delivery-A")["id"], photo())
    draft = first.draft(captured["id"])
    connect = module.sqlite3.connect

    class Cursor:
        def __init__(self, original):
            self.original = original

        def fetchall(self):
            rows = self.original.fetchall()
            assert submit(first, draft)["status"] == "RECEIPT_SUBMITTED"
            return rows

    class Connection:
        def __init__(self, original):
            self.original = original

        def __getattr__(self, key):
            return getattr(self.original, key)

        def execute(self, query, *args):
            cursor = self.original.execute(query, *args)
            return (
                Cursor(cursor) if query == "SELECT state, digest, image FROM captures" else cursor
            )

    monkeypatch.setattr(module.sqlite3, "connect", lambda *a, **k: Connection(connect(*a, **k)))
    second = service_at(path, transport)
    assert second.current(captured["id"])["status"] == "RECEIPT_SUBMITTED"
    assert second.current(captured["id"])["receipt"]["name"] == "PR-1"
    assert transport.submits == 1
