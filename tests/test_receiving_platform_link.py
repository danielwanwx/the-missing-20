"""Real platform/HTTP code, offline source/model doubles explicitly disclosed."""

from copy import deepcopy
from pathlib import Path

from test_photo_receiving import photo
from test_photo_receiving_history import submit
from test_receiving_arrivals import MultiReceiptTransport, scan, service_at

from the_missing_20.adapters.agent_platform import AgentPlatform


class Source:
    def __init__(self, transport):
        self.transport = transport
        self.case_id = "M20-ARRIVAL-TEST"

    def current(self):
        docs = [
            {
                "name": "PO-1",
                "kind": "purchase_order",
                "docstatus": 1,
                "quantity": 10,
                "uom": "Nos",
                "currency": "USD",
                "unit_rate": 20,
                "modified": "po-v1",
                "items": deepcopy(self.transport.po["items"]),
            }
        ]
        for receipt in self.transport.receipts.values():
            if receipt["docstatus"] == 1:
                qty = receipt["items"][0]["qty"]
                docs.append(
                    {
                        "kind": "purchase_receipt",
                        "name": receipt["name"],
                        "received": qty,
                        "accepted": qty,
                        "rejected": 0,
                        "modified": receipt["modified"],
                        "uom": "Nos",
                        "docstatus": 1,
                    }
                )
        return {
            "case_id": self.case_id,
            "source_id": "offline-erp",
            "status": "CONNECTED",
            "provenance": "offline-test",
            "received_at": "2026-09-08T11:00:00Z",
            "document_lifecycle": {
                "purchase_receipt": "AWAITING_RECEIPT",
                "purchase_invoice": "AWAITING_INVOICE",
            },
            "documents": docs,
        }


class EmptySaaS:
    def current(self):
        return {"sources": [], "status": "NOT_CONFIGURED"}


def test_receiving_jira_projection_is_scoped_workflow_not_stock_authority(tmp_path):
    transport = MultiReceiptTransport()
    source = Source(transport)
    receiving = service_at(tmp_path / "photos.db", transport)
    platform = AgentPlatform(source, EmptySaaS(), receiving=receiving)
    erp = source.current()
    erp["receiving_work"] = {"status": "CONFIGURED", "purchase_order": "PO-1"}
    review = {"source_id": "jira-receiving", "case_id": source.case_id,
              "purchase_order": "PO-1", "status": "UNKNOWN", "record_id": "", "url": "",
              "arrival_id": "delivery-A", "capture_id": "capture-A", "operation": "create"}
    systems = platform._systems(erp, {"sources": [review]})
    jira = next(row for row in systems if row["id"] == "jira")
    assert jira["write_state"] == "RECEIVING_REVIEW"
    assert jira["record_id"] == jira["url"] == ""
    assert jira["arrival_id"] == "delivery-A" and jira["capture_id"] == "capture-A"
    assert jira["operation"] == "create" and "not QA" in jira["authority"]
    for key in ("case_id", "purchase_order"):
        wrong = {**review, key: "another-case"}
        jira = next(row for row in platform._systems(erp, {"sources": [wrong]})
                    if row["id"] == "jira")
        assert jira["write_state"] != "RECEIVING_REVIEW"


def test_receipt_photo_and_history_share_case_after_restart(tmp_path: Path):
    transport = MultiReceiptTransport()
    receiving = service_at(tmp_path / "photos.db", transport)
    source = Source(transport)
    state_path = tmp_path / "platform.json"
    platform = AgentPlatform(source, EmptySaaS(), state_path=state_path, receiving=receiving)
    before = platform.current()
    assert before["receiving_work"]["arrivals"][0]["observed_quantity"] == 0
    receiving.scan(scan())
    first = receiving.upload(receiving.create(arrival_id="delivery-A")["id"], photo())
    after_photo = platform.current()
    work = after_photo["receiving_work"]["arrivals"][0]
    assert work["capture_id"] == first["id"] and work["posted_quantity"] is None
    assert any(event["label"] == "Handling unit scanned" for event in after_photo["activity"])
    completed = submit(receiving, receiving.draft(first["id"]))
    after = platform.current()
    work = after["receiving_work"]["arrivals"][0]
    assert work["receipt"]["name"] == completed["receipt"]["name"]
    assert work["posted_quantity"] == 2
    points = platform.operational_history()["points"]
    assert points[-1]["receiving_refs"][0]["receipt_name"] == "PR-1"
    assert points[-1]["receiving_refs"][0]["capture_id"] == first["id"]
    assert points[-1]["metrics"]["received"] == 2
    size = len(points)
    sequence = after["latest_sequence"]
    restarted = AgentPlatform(source, EmptySaaS(), state_path=state_path, receiving=receiving)
    restored = restarted.current()
    assert restored["receiving_work"]["arrivals"][0]["receipt"]["name"] == "PR-1"
    assert restored["latest_sequence"] == sequence
    assert len(restarted.operational_history()["points"]) == size
    source.case_id = "UNRELATED"
    assert restarted.current()["receiving_work"]["arrivals"] == []


def test_local_submit_cannot_publish_old_cached_erp_as_current(tmp_path):
    transport = MultiReceiptTransport()
    receiving = service_at(tmp_path / "photos.db", transport)
    source = Source(transport)
    cached = source.current()
    source.current = lambda: deepcopy(cached)
    platform = AgentPlatform(source, EmptySaaS(), receiving=receiving,
                             state_path=tmp_path / "state.json")
    platform.current()
    before = len(platform.operational_history()["points"])
    first = receiving.upload(receiving.create(arrival_id="delivery-A")["id"], photo())
    submit(receiving, receiving.draft(first["id"]))
    pending = platform.current()
    assert pending["source_freshness"]["status"] != "CURRENT"
    assert len(platform.operational_history()["points"]) == before
    cached = Source(transport).current()
    restored = platform.current()
    assert restored["source_freshness"]["status"] == "CURRENT"
    assert platform.operational_history()["points"][-1]["metrics"]["received"] == 2


def test_local_submit_invalidates_stale_erp_cache_before_projection(tmp_path):
    transport = MultiReceiptTransport()
    receiving = service_at(tmp_path / "photos.db", transport)
    source = Source(transport)
    cached = source.current()
    source.current = lambda: deepcopy(cached)
    invalidations = []

    def refresh():
        nonlocal cached
        invalidations.append(True)
        cached = Source(transport).current()

    source.invalidate_cache = refresh
    platform = AgentPlatform(source, EmptySaaS(), receiving=receiving,
                             state_path=tmp_path / "state.json")
    platform.current()
    first = receiving.upload(receiving.create(arrival_id="delivery-A")["id"], photo())
    submit(receiving, receiving.draft(first["id"]))
    projected = platform.current()
    assert invalidations == [True]
    assert projected["source_freshness"]["status"] == "CURRENT"
    assert platform.operational_history()["points"][-1]["metrics"]["received"] == 2


def test_unavailable_receipt_readback_does_not_bypass_provider_cache_each_poll(
    tmp_path, monkeypatch
):
    transport = MultiReceiptTransport()
    receiving = service_at(tmp_path / "photos.db", transport)
    source = Source(transport)
    cached = source.current()
    source.current = lambda: deepcopy(cached)
    invalidations = []
    source.invalidate_cache = lambda: invalidations.append(True)
    clock = [100.0]
    monkeypatch.setattr("the_missing_20.adapters.agent_platform.time.monotonic", lambda: clock[0])
    platform = AgentPlatform(source, EmptySaaS(), receiving=receiving,
                             state_path=tmp_path / "state.json")
    first = receiving.upload(receiving.create(arrival_id="delivery-A")["id"], photo())
    submit(receiving, receiving.draft(first["id"]))
    for _ in range(3):
        assert platform.current()["source_freshness"]["status"] == "UNAVAILABLE"
    assert invalidations == [True]
    clock[0] = 131
    assert platform.current()["source_freshness"]["status"] == "UNAVAILABLE"
    assert invalidations == [True, True]
    cached = Source(transport).current()
    assert platform.current()["source_freshness"]["status"] == "CURRENT"
    assert invalidations == [True, True]


def test_scan_progress_and_conflict_are_history_but_replay_is_not(tmp_path):
    transport = MultiReceiptTransport()
    receiving = service_at(tmp_path / "photos.db", transport)
    platform = AgentPlatform(
        Source(transport), EmptySaaS(), receiving=receiving, state_path=tmp_path / "state.json"
    )
    receiving.scan(scan())
    first = platform.operational_history()["points"]
    assert first[-1]["receiving_refs"][0]["observed_quantity"] == 1
    receiving.scan(scan())
    assert len(platform.operational_history()["points"]) == len(first)
    receiving.scan(scan(event_id="scan-2", unit="box-02"))
    second = platform.operational_history()["points"]
    assert len(second) == len(first) + 1
    assert second[-1]["receiving_refs"][0]["observed_quantity"] == 2
    receiving.scan(scan(unit="box-02"))
    third = platform.operational_history()["points"]
    assert len(third) == len(second) + 1
    assert third[-1]["receiving_refs"][0]["scan_status"] == "CONFLICT"
    assert third[-1]["receiving_refs"][0]["observed_quantity"] is None


def test_receiving_notifications_do_not_become_quality_release_authority(tmp_path):
    source = Source(MultiReceiptTransport())
    platform = AgentPlatform(source, EmptySaaS())
    erp = source.current()
    erp["receiving_work"] = {"status": "CONFIGURED", "purchase_order": "PO-1"}
    saas = {
        "sources": [
            {
                "source_id": name,
                "status": "VERIFIED",
                "case_id": source.case_id,
                "purchase_order": "PO-1",
                "record_id": name + "-record",
                "url": "https://demo.invalid/record",
            }
            for name in ("airtable-receiving", "celigo-receiving")
        ]
    }
    systems = {row["id"]: row for row in platform._systems(erp, saas)}
    nodes = {row["id"]: row for row in platform._constellation(erp, saas)["nodes"]}
    for name in ("airtable", "celigo"):
        assert systems[name]["write_state"] == "EVENT_DRIVEN_NOTIFICATION"
        assert systems[name]["status"] == nodes[name]["status"] == "VERIFIED"
        assert nodes[name]["role"] == "RECEIVING"
    correlation = platform._correlation(erp, saas)
    assert correlation["status"] != "FULLY_CORRELATED"
    assert not correlation["registry_tuple"]
    assert platform._integration_receipt(saas, correlation)["status"] != "VERIFIED"
    saas["sources"][0]["case_id"] = "OTHER"
    assert platform._systems(erp, saas)[1]["write_state"] != "EVENT_DRIVEN_NOTIFICATION"


def test_scan_conflict_emits_current_activity_without_erasing_original_observation(tmp_path):
    transport = MultiReceiptTransport()
    receiving = service_at(tmp_path / "photos.db", transport)
    source = Source(transport)
    path = tmp_path / "state.json"
    platform = AgentPlatform(source, EmptySaaS(), receiving=receiving, state_path=path)
    receiving.scan(scan())
    first = platform.current()
    assert any(row["label"] == "Handling unit scanned" for row in first["activity"])
    receiving.scan(scan(unit="box-02"))
    after = platform.current()
    conflicts = [row for row in after["activity"] if row["status"] == "CONFLICT"]
    assert len(conflicts) == 1
    assert conflicts[0]["label"] == "Scan conflict needs review"
    assert "scan-1" in conflicts[0]["detail"]
    assert after["receiving_work"]["arrivals"][0]["observed_quantity"] is None
    receiving.scan(scan(unit="box-02"))
    assert platform.current()["latest_sequence"] == after["latest_sequence"]
    restarted = AgentPlatform(source, EmptySaaS(), receiving=receiving, state_path=path)
    assert restarted.current()["latest_sequence"] == after["latest_sequence"]


def test_cross_arrival_conflict_has_history_even_without_photo_or_accepted_scan(tmp_path):
    transport = MultiReceiptTransport()
    receiving = service_at(tmp_path / "photos.db", transport)
    platform = AgentPlatform(
        Source(transport), EmptySaaS(), receiving=receiving, state_path=tmp_path / "state.json"
    )
    receiving.scan(scan())
    platform.current()
    receiving.scan(scan(arrival="delivery-B", unit="box-03"))
    current = platform.current()
    assert current["receiving_work"]["arrivals"][1]["observed_quantity"] is None
    refs = platform.operational_history()["points"][-1]["receiving_refs"]
    assert {row["arrival_id"] for row in refs} == {"delivery-A", "delivery-B"}
    assert all(row["scan_status"] == "CONFLICT" for row in refs)
