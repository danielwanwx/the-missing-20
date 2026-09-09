"""Real loopback router with disclosed offline ERP/model doubles, not a live ERP test."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pytest
from test_photo_receiving import erp, photo, result
from test_photo_receiving_history import ReceivingTransport

from scripts.decision_workspace_server import DecisionWorkspaceServer
from the_missing_20.adapters.agent_platform import AgentPlatform
from the_missing_20.adapters.photo_receiving import PhotoReceiving

PHOTO = "/api/v1/photo-receiving"
HISTORY = "/api/v1/agent-platform/history"


def test_barcode_route_reads_current_order_and_rejects_cross_origin(pilot, tmp_path):
    from test_receiving_arrivals import service_at
    from test_receiving_barcode import BarcodeTransport, payload

    transport = BarcodeTransport()
    pilot.server.photo_receiving.db.close()
    pilot.server.photo_receiving = service_at(tmp_path / "barcode.db", transport)
    result = pilot.ok(PHOTO + "/barcode", payload())
    assert result["unit_price"] == 20 and result["inventory_changed"] is False
    assert pilot.ok(PHOTO + "/barcode", payload()) == result
    assert (
        pilot.request(PHOTO + "/barcode", payload(), headers={"Origin": "https://other.example"})[0]
        == 403
    )
    assert pilot.request(PHOTO + "/barcode", {**payload(), "format": []})[0] == 400
    assert transport.writes == transport.submits == 0


def test_history_rejects_a_rebound_external_host(pilot: PilotHTTP) -> None:
    status, payload = pilot.request(HISTORY, headers={"Host": "unrelated.example"})
    assert status == 403 and payload["error"]["code"] == "local_only"


def test_configured_arrival_photo_to_ledger_routes_and_restart(pilot: PilotHTTP, tmp_path):
    from test_receiving_arrivals import MultiReceiptTransport, scan, service_at
    from test_receiving_platform_link import EmptySaaS, Source

    transport = MultiReceiptTransport()
    path = tmp_path / "scoped-photos.db"
    pilot.server.photo_receiving.db.close()
    receiving = service_at(path, transport)
    pilot.server.photo_receiving = receiving
    pilot.server.agent_platform = AgentPlatform(
        Source(transport),
        EmptySaaS(),
        receiving=receiving,
        state_path=tmp_path / "scoped-platform.json",
    )
    assert pilot.ok(PHOTO + "/arrivals")["status"] == "CONFIGURED"
    assert pilot.request(PHOTO, {})[0] == 400
    state = pilot.ok(PHOTO, {"arrival_id": "delivery-A"})
    assert pilot.ok(PHOTO, {"arrival_id": "delivery-A"})["id"] == state["id"]
    assert pilot.ok(PHOTO + "/scan", scan())["inventory_changed"] is False
    assert pilot.ok(PHOTO + "/scan", scan())["inventory_changed"] is False
    assert transport.submits == 0
    pilot.ok(PHOTO + "/upload", {"id": state["id"], "image": photo()})
    drafted = pilot.ok(PHOTO + "/draft", {"id": state["id"]})
    finished = pilot.ok(PHOTO + "/submit", pilot.submit_payload(drafted))
    assert finished["status"] == "RECEIPT_SUBMITTED"
    receiving.db.close()
    pilot.server.photo_receiving = service_at(path, transport)
    restored = pilot.ok(PHOTO, {"arrival_id": "delivery-A"})
    assert restored["id"] == state["id"] and restored["receipt"]["name"] == "PR-1"
    pilot.ok(PHOTO + "/submit", pilot.submit_payload(drafted))
    assert transport.writes == transport.submits == 1
    assert (
        pilot.request(PHOTO + "/scan", scan(), headers={"Origin": "https://unrelated.example"})[0]
        == 403
    )
    assert pilot.request(PHOTO + "/arrivals", headers={"Host": "unrelated.example"})[0] == 403


class OfflineSource:
    def current(self) -> dict[str, object]:
        return {
            "case_id": "M20-HTTP-OFFLINE",
            "source_id": "offline-http-test",
            "status": "DEGRADED",
            "provenance": "offline_test_double",
            "received_at": "2026-09-08T10:00:00Z",
            "documents": [],
        }


@dataclass
class PilotHTTP:
    server: DecisionWorkspaceServer
    transport: ReceivingTransport

    def request(
        self,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, Any]]:
        request_headers = {"Content-Type": "application/json", **(headers or {})}
        request = Request(
            f"http://127.0.0.1:{self.server.server_port}{path}",
            data=json.dumps(payload).encode() if payload is not None else None,
            headers=request_headers,
        )
        try:
            with urlopen(request, timeout=5) as response:
                return response.status, dict(json.loads(response.read()))
        except HTTPError as error:
            return error.code, dict(json.loads(error.read()))

    def ok(self, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        status, response = self.request(path, payload)
        assert status == 200, response
        return response

    def capture(self) -> dict[str, Any]:
        created = self.ok(PHOTO, {})
        return self.ok(PHOTO + "/upload", {"id": created["id"], "image": photo()})

    def identity_payload(self, state: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": state["id"],
            "item_code": "M20-TEST",
            "expected_version": state["version"],
            "confirm_match": True,
        }

    def draft(self) -> dict[str, Any]:
        state = self.capture()
        self.ok(PHOTO + "/confirm-identity", self.identity_payload(state))
        return self.ok(PHOTO + "/draft", {"id": state["id"]})

    def submit_payload(self, state: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": state["id"],
            "receipt_name": state["draft"]["name"],
            "expected_version": state["version"],
            "confirm_received": True,
        }


@pytest.fixture
def pilot(tmp_path: Path) -> Iterator[PilotHTTP]:
    source = OfflineSource()
    platform = AgentPlatform(source, source, state_path=tmp_path / "platform.json")
    server = DecisionWorkspaceServer(
        ("127.0.0.1", 0),
        Path(__file__).resolve().parents[1],
        runtime_directory=tmp_path / "server",
        agent_platform=platform,
        live_sources_autostart=False,
    )
    server.photo_receiving.db.close()
    transport = ReceivingTransport()
    server.photo_receiving = PhotoReceiving(
        tmp_path / "photos.sqlite",
        lambda _: result(item_code=""),
        erp=erp(transport),
        drafts_enabled=True,
    )
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
    )
    thread.start()
    try:
        yield PilotHTTP(server, transport)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        server.photo_receiving.db.close()


def test_http_gallery_retake_history_and_identity_are_persisted_observations(
    pilot: PilotHTTP,
) -> None:
    empty = pilot.ok(PHOTO + "/list")
    assert empty["captures"] == [] and empty["total"] == 0
    state = pilot.capture()
    latest = pilot.ok(PHOTO + "/upload", {"id": state["id"], "image": photo("red")})
    gallery = pilot.ok(PHOTO + "/list?limit=1&offset=0")
    assert gallery["captures"] == [latest] and gallery["total"] == 1
    assert "never an additive batch" in gallery["count_semantics"]
    assert pilot.ok(PHOTO + "/list?limit=1&offset=1")["captures"] == []
    history = pilot.ok(PHOTO + "/history?id=" + state["id"])
    assert [version["image_version"] for version in history["versions"]] == [1, 2]
    assert [version["count"] for version in history["versions"]] == [2, 2]
    assert history["versions"][0]["digest"] == state["digest"]
    assert pilot.ok(PHOTO + "?id=" + state["id"]) == latest
    identity = pilot.ok(PHOTO + "/identity")
    assert identity["purchase_order"] == "PO-1" and identity["po_version"] == "v1"
    assert identity["items"][0]["item_code"] == "M20-TEST"
    assert pilot.transport.writes == pilot.transport.submits == 0


def test_http_original_retained_bytes_reopen_after_retake(pilot: PilotHTTP) -> None:
    state = pilot.capture()
    image_url = f"http://127.0.0.1:{pilot.server.server_port}{PHOTO}/image?id={state['id']}"
    with urlopen(image_url, timeout=5) as response:
        original = response.read()
        assert response.headers["Content-Type"] == "image/jpeg"
    pilot.ok(PHOTO + "/upload", {"id": state["id"], "image": photo("red")})
    with urlopen(image_url + "&image_version=1", timeout=5) as response:
        assert response.headers["Content-Type"] == "image/jpeg"
        assert response.read() == original
    with urlopen(image_url, timeout=5) as response:
        assert response.read() != original
    status, response = pilot.request(PHOTO + f"/image?id={state['id']}&image_version=99")
    assert 400 <= status < 500 and response["error"]["detail"]
    assert pilot.transport.writes == pilot.transport.submits == 0


@pytest.mark.parametrize("query", ["limit=0", "limit=51", "limit=NaN", "offset=-1", "other=1"])
def test_http_gallery_rejects_invalid_queries(pilot: PilotHTTP, query: str) -> None:
    status, response = pilot.request(PHOTO + "/list?" + query)
    assert 400 <= status < 500 and response["error"]["detail"]


@pytest.mark.parametrize("suffix", ["/list", "/history?id=unknown", "/identity"])
def test_new_photo_get_routes_keep_loopback_host_boundary(pilot: PilotHTTP, suffix: str) -> None:
    status, response = pilot.request(PHOTO + suffix, headers={"Host": "attacker.invalid"})
    assert status == 403 and response["error"]["code"] == "local_only"


@pytest.mark.parametrize(
    "change",
    [
        {"confirm_match": False},
        {"confirm_match": "true"},
        {"confirm_match": 1},
        {"expected_version": 0},
        {"expected_version": "2"},
        {"expected_version": True},
        {"item_code": "M20-WRONG"},
        {"quantity": 50},
    ],
)
def test_http_identity_requires_literal_confirmation_and_current_known_item(
    pilot: PilotHTTP, change: dict[str, Any]
) -> None:
    state = pilot.capture()
    status, response = pilot.request(
        PHOTO + "/confirm-identity", {**pilot.identity_payload(state), **change}
    )
    assert status == 400 and response["error"]["code"] == "invalid_request"
    assert pilot.ok(PHOTO + "?id=" + state["id"]) == state
    assert pilot.transport.writes == pilot.transport.submits == 0


def test_http_human_identity_preserves_original_model_evidence(pilot: PilotHTTP) -> None:
    state = pilot.capture()
    confirmed = pilot.ok(PHOTO + "/confirm-identity", pilot.identity_payload(state))
    assert confirmed["status"] == "RECEIPT_PREPARED"
    assert confirmed["analysis"]["assessment"]["item_code"] == ""
    assert confirmed["identity_confirmation"]["source"] == "explicit_human_confirmation"
    assert confirmed["candidate"]["items"][0]["item_code"] == "M20-TEST"
    assert pilot.transport.writes == 0


@pytest.mark.parametrize(
    "change",
    [
        {"confirm_received": False},
        {"confirm_received": "true"},
        {"confirm_received": 1},
        {"expected_version": 0},
        {"expected_version": "5"},
        {"expected_version": True},
        {"receipt_name": "PR-unrelated"},
        {"quantity": 50},
    ],
)
def test_http_submit_requires_literal_confirmation_exact_receipt_and_version(
    pilot: PilotHTTP, change: dict[str, Any]
) -> None:
    draft = pilot.draft()
    status, response = pilot.request(PHOTO + "/submit", {**pilot.submit_payload(draft), **change})
    assert status == 400 and response["error"]["code"] == "invalid_request"
    assert pilot.ok(PHOTO + "?id=" + draft["id"]) == draft
    assert pilot.transport.writes == 1 and pilot.transport.submits == 0


@pytest.mark.parametrize("route", ["confirm-identity", "submit"])
def test_http_confirming_routes_reject_missing_fields_and_cross_origin(
    pilot: PilotHTTP, route: str
) -> None:
    state = pilot.capture() if route == "confirm-identity" else pilot.draft()
    payload = (
        pilot.identity_payload(state)
        if route == "confirm-identity"
        else pilot.submit_payload(state)
    )
    status, response = pilot.request(
        PHOTO + "/" + route, payload, headers={"Origin": "https://attacker.invalid"}
    )
    assert status == 403 and response["error"]["code"] == "origin_not_allowed"
    payload.pop("expected_version")
    assert pilot.request(PHOTO + "/" + route, payload)[0] == 400
    assert pilot.transport.submits == 0


def test_http_success_replay_and_duplicate_photo_cannot_make_another_receipt(
    pilot: PilotHTTP,
) -> None:
    draft = pilot.draft()
    payload = pilot.submit_payload(draft)
    submitted = pilot.ok(PHOTO + "/submit", payload)
    assert submitted["status"] == "RECEIPT_SUBMITTED" and submitted["stock_posted"] is True
    assert submitted["receipt"]["docstatus"] == 1
    assert submitted["receipt"]["stock_ledger"][0]["name"] == "SLE-1"
    assert pilot.ok(PHOTO + "/submit", payload) == submitted
    duplicate = pilot.capture()
    assert duplicate["status"] == "DUPLICATE_EVIDENCE" and duplicate["duplicate_of"] == draft["id"]
    assert pilot.request(PHOTO + "/draft", {"id": duplicate["id"]})[0] == 400
    assert pilot.transport.writes == pilot.transport.submits == 1


def test_http_lost_ack_reconciliation_never_resubmits(pilot: PilotHTTP) -> None:
    draft = pilot.draft()
    pilot.transport.lose_submit_ack = True
    unknown = pilot.ok(PHOTO + "/submit", pilot.submit_payload(draft))
    assert unknown["status"] == "SUBMIT_UNKNOWN" and unknown["stock_posted"] is None
    completed = pilot.ok(PHOTO + "/submit", pilot.submit_payload(unknown))
    assert completed["status"] == "RECEIPT_SUBMITTED"
    assert pilot.ok(PHOTO + "/submit", pilot.submit_payload(completed)) == completed
    assert pilot.transport.writes == pilot.transport.submits == 1


def test_http_unknown_uncommitted_submit_only_reconciles(pilot: PilotHTTP) -> None:
    draft = pilot.draft()
    pilot.transport.reject_submit = True
    unknown = pilot.ok(PHOTO + "/submit", pilot.submit_payload(draft))
    pilot.transport.reject_submit = False
    assert pilot.ok(PHOTO + "/submit", pilot.submit_payload(unknown)) == unknown
    assert unknown["status"] == "SUBMIT_UNKNOWN" and unknown["stock_posted"] is None
    assert pilot.transport.writes == pilot.transport.submits == 1


def test_http_operational_history_uses_real_local_query_and_retains_offline_provenance(
    pilot: PilotHTTP,
) -> None:
    history = pilot.ok(HISTORY + "?" + urlencode({"limit": 1, "since": "2026-09-01T00:00:00Z"}))
    assert history["case_id"] == "M20-HTTP-OFFLINE" and len(history["points"]) == 1
    assert history["points"][0]["provenance"] == "offline_test_double"
    assert history["points"][0]["source_status"] == "DEGRADED"
    assert pilot.ok(HISTORY)["points"] == history["points"]
    assert pilot.transport.writes == pilot.transport.submits == 0


@pytest.mark.parametrize(
    "query",
    [
        "limit=0",
        "limit=501",
        "limit=-1",
        "limit=true",
        "limit=1.5",
        "limit=",
        "limit=1&limit=2",
        "unknown=1",
        "since=garbage",
        "since=2026-09-08",
        "since=2026-09-08T00%3A00%3A00",
        "since=2026-09-08T00%3A00%3A00Z&since=garbage",
    ],
)
def test_http_operational_history_rejects_invalid_or_ambiguous_queries(
    pilot: PilotHTTP, query: str
) -> None:
    status, response = pilot.request(HISTORY + "?" + query)
    assert status == 400 and response["error"]["code"] == "invalid_request"
    assert pilot.transport.writes == pilot.transport.submits == 0
