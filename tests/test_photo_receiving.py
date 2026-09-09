"""Photo pilot tests use disclosed generated fixtures, not accuracy measurements."""

from __future__ import annotations

import base64
import json
import threading
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from PIL import Image

from scripts.decision_workspace_server import DecisionWorkspaceServer
from the_missing_20.adapters.demo_executor import DemoExecutionBlocked, ERPNextDemoExecutor
from the_missing_20.adapters.erpnext_source import ERPNextCredentials
from the_missing_20.adapters.photo_receiving import PhotoReceiptERP, PhotoReceiving
from the_missing_20.agents.photo_receiving import PhotoAssessment, normalize_photo


def photo(color: str = "white") -> str:
    stream = BytesIO()
    Image.new("RGB", (100, 100), color).save(stream, "PNG")
    return base64.b64encode(stream.getvalue()).decode()


def result(**changes: Any) -> dict[str, Any]:
    return {
        "assessment": {
            "visibility": "clear",
            "countable": True,
            "objects": [
                {"x": 0.2, "y": 0.5, "description": "visible item"},
                {"x": 0.8, "y": 0.5, "description": "visible item"},
            ],
            "receiving_unit": "piece",
            "item_code": "M20-TEST",
            "supplier_lot": "",
            "label_declared_quantity": None,
            "issues": [],
            "visible_condition": "no_visible_damage",
            "next_photo": "",
            **changes,
        },
        "provider": "test_double",
        "model": "test_double",
        "usage": {},
        "latency_ms": 1,
    }


class ERPTransport:
    def __init__(self) -> None:
        self.po: dict[str, Any] = {
            "name": "PO-1",
            "docstatus": 1,
            "modified": "v1",
            "company": "M20 Demo",
            "supplier": "M20 Supplier",
            "items": [
                {
                    "name": "line-1",
                    "item_code": "M20-TEST",
                    "qty": 10,
                    "received_qty": 0,
                    "rate": 20,
                    "warehouse": "M20 Stores",
                    "uom": "Nos",
                    "stock_uom": "Nos",
                    "conversion_factor": 1,
                }
            ],
        }
        self.receipt: dict[str, Any] | None = None
        self.writes = 0
        self.lose_ack = False

    def __call__(self, request: Request, timeout: float) -> bytes:
        if "Purchase%20Order/" in request.full_url:
            return json.dumps({"data": self.po}).encode()
        if request.method == "POST":
            assert request.data is not None
            assert isinstance(request.data, bytes)
            payload = json.loads(request.data)
            assert payload["docstatus"] == 0  # Never POST submitted stock.
            self.writes += 1
            self.receipt = {**payload, "name": "PR-1"}
            if self.lose_ack:
                self.lose_ack = False
                raise TimeoutError("response lost after commit")
            return json.dumps({"data": self.receipt}).encode()
        if "Purchase%20Receipt?" in request.full_url:
            return json.dumps(
                {"data": [{"name": "PR-1", "docstatus": 0}] if self.receipt else []}
            ).encode()
        return json.dumps({"data": self.receipt}).encode()


def erp(transport: ERPTransport, environment: str = "demo") -> PhotoReceiptERP:
    return PhotoReceiptERP(
        ERPNextDemoExecutor(
            ERPNextCredentials(base_url="https://demo.invalid", api_key="test", api_secret="test"),
            environment=environment,
            transport=transport,
        ),
        "PO-1",
    )


def test_draft_failure_category_is_durable_without_provider_body(tmp_path):
    transport = ERPTransport()
    delegate = erp(transport)
    store = PhotoReceiving(
        tmp_path / "errors.sqlite3", lambda _: result(), erp=delegate, drafts_enabled=True
    )
    state = store.create()
    state = store.upload(state["id"], photo())
    calls = []

    def fail(candidate, key, *, lookup_only=False):
        calls.append(lookup_only)
        if not lookup_only:
            raise DemoExecutionBlocked(
                "ERPNext rejected POST /private (417): secret person@example.com"
            )
        raise ValueError("No original receipt found")

    delegate.draft = fail
    state = store.draft(state["id"])
    assert state["provider_failure"]["code"] == "VALIDATION_REJECTED"
    assert state["provider_failure"]["http_status"] == 417
    assert state["stock_posted"] is False
    state = store.draft(state["id"])
    assert calls == [False, True]
    assert store.current(state["id"])["provider_failure"] == state["provider_failure"]
    assert "secret" not in json.dumps(state)
    assert "person@example.com" not in json.dumps(state)


@pytest.mark.parametrize(
    ("unit", "uom"), [("piece", "Nos"), ("carton", "Carton"), ("carton", "Box")]
)
def test_candidate_draft_reread_and_replay(tmp_path: Path, unit: str, uom: str) -> None:
    transport = ERPTransport()
    transport.po["items"][0].update(uom=uom, stock_uom=uom)
    calls: list[bytes] = []

    def reader(image: bytes) -> dict[str, Any]:
        calls.append(image)
        return result(receiving_unit=unit)

    service = PhotoReceiving(tmp_path / "db", reader, erp=erp(transport), drafts_enabled=True)
    session = service.create()["id"]
    candidate = service.upload(session, photo())
    assert candidate["status"] == "RECEIPT_PREPARED" and candidate["count"] == 2
    assert transport.writes == 0
    assert service.upload(session, photo()) == candidate
    assert len(calls) == 1
    completed = service.draft(session)
    assert completed["status"] == "DRAFT_VERIFIED"
    assert completed["draft"]["docstatus"] == 0 and not completed["stock_posted"]
    assert service.draft(session) == completed and transport.writes == 1
    with pytest.raises(ValueError, match="draft"):
        service.upload(session, photo("red"))
    restarted = PhotoReceiving(tmp_path / "db", reader)
    assert restarted.current(session)["draft"] == completed["draft"]


@pytest.mark.parametrize("uom", ["Carton", "Box"])
def test_visible_cartons_prepare_only_the_same_explicit_po_stock_unit(
    tmp_path: Path, uom: str
) -> None:
    transport = ERPTransport()
    transport.po["items"][0].update(uom=uom, stock_uom=uom, conversion_factor=1)
    service = PhotoReceiving(
        tmp_path / "db",
        lambda _: result(receiving_unit="carton", label_declared_quantity=50),
        erp=erp(transport),
    )
    try:
        state = service.upload(service.create()["id"], photo())
        assert state["status"] == "RECEIPT_PREPARED"
        assert state["candidate"]["quantity"] == 2
        assert state["candidate"]["items"][0] == {
            "item_code": "M20-TEST",
            "qty": 2,
            "uom": uom,
            "stock_uom": uom,
            "conversion_factor": 1,
            "rate": 20,
            "warehouse": "M20 Stores",
            "purchase_order": "PO-1",
            "purchase_order_item": "line-1",
        }
        assert service.current(state["id"]) == state
        assert not state["stock_posted"] and transport.writes == 0
        with pytest.raises(ValueError, match="not enabled"):
            service.draft(state["id"])
        assert transport.writes == 0
    finally:
        service.db.close()


@pytest.mark.parametrize(
    ("changes", "missing"),
    [
        ({"uom": "Nos", "stock_uom": "Nos"}, ""),
        ({"stock_uom": "Nos", "conversion_factor": 12}, ""),
        ({"stock_uom": "Carton"}, ""),
        ({"conversion_factor": 2}, ""),
        ({"conversion_factor": 0}, ""),
        ({"conversion_factor": None}, ""),
        ({}, "conversion_factor"),
        ({}, "stock_uom"),
    ],
)
def test_carton_receiving_never_guesses_stock_units_or_pack_conversion(
    tmp_path: Path, changes: dict[str, Any], missing: str
) -> None:
    transport = ERPTransport()
    line = transport.po["items"][0]
    line.update(uom="Box", stock_uom="Box", conversion_factor=1)
    line.update(changes)
    if missing:
        line.pop(missing)
    service = PhotoReceiving(
        tmp_path / "db",
        lambda _: result(receiving_unit="carton"),
        erp=erp(transport),
        drafts_enabled=True,
    )
    try:
        state = service.upload(service.create()["id"], photo())
        assert state["status"] == "NEEDS_REVIEW" and "candidate" not in state
        with pytest.raises(ValueError, match="not ready"):
            service.draft(state["id"])
        assert not state["stock_posted"] and transport.writes == 0
    finally:
        service.db.close()


@pytest.mark.parametrize(
    ("changes", "status"),
    [
        (
            {"countable": False, "issues": ["occlusion"], "next_photo": "Spread the items apart."},
            "NEEDS_PHOTO",
        ),
        ({"receiving_unit": "unknown"}, "NEEDS_PHOTO"),
        ({"visibility": "occluded"}, "NEEDS_PHOTO"),
        ({"visibility": "cropped"}, "NEEDS_PHOTO"),
        ({"visibility": "unclear"}, "NEEDS_PHOTO"),
        ({"receiving_unit": "carton"}, "NEEDS_REVIEW"),
        ({"visible_condition": "visible_damage"}, "NEEDS_REVIEW"),
        ({"visible_condition": "unclear"}, "NEEDS_REVIEW"),
        ({"item_code": "wrong"}, "NEEDS_REVIEW"),
        ({"item_code": ""}, "COUNT_CANDIDATE"),
    ],
)
def test_no_write_for_unclear_or_ineligible_photos(
    tmp_path: Path, changes: dict[str, Any], status: str
) -> None:
    transport = ERPTransport()
    service = PhotoReceiving(
        tmp_path / "db", lambda _: result(**changes), erp=erp(transport), drafts_enabled=True
    )
    state = service.upload(service.create()["id"], photo())
    assert state["status"] == status
    with pytest.raises(ValueError):
        service.draft(state["id"])
    assert transport.writes == 0


@pytest.mark.parametrize("raw", [b"<svg></svg>", b"not a photo", b"", b"x" * (5 * 1024 * 1024 + 1)])
def test_reject_non_images_and_oversize(raw: bytes) -> None:
    with pytest.raises(ValueError):
        normalize_photo(raw)


def test_bad_and_tiny_decodes_rejected() -> None:
    stream = BytesIO()
    Image.new("RGB", (20, 20)).save(stream, "PNG")
    with pytest.raises(ValueError):
        normalize_photo(stream.getvalue())


def test_invalid_model_count_rejected() -> None:
    value = result()["assessment"]
    value["objects"][1] = value["objects"][0]
    with pytest.raises(ValueError, match="duplicate"):
        PhotoAssessment.model_validate(value)


def test_model_must_explicitly_report_visibility(tmp_path: Path) -> None:
    returned = result()
    returned["assessment"].pop("visibility")
    with pytest.raises(ValueError, match="visibility"):
        PhotoAssessment.model_validate(returned["assessment"])
    service = PhotoReceiving(tmp_path / "db", lambda _: returned)
    try:
        state = service.upload(service.create()["id"], photo())
        assert state["status"] == "UNAVAILABLE" and "count" not in state
        assert not state["stock_posted"]
    finally:
        service.db.close()


def test_visibility_overrules_self_reported_countability(tmp_path: Path) -> None:
    service = PhotoReceiving(tmp_path / "db", lambda _: result(visibility="cropped"))
    try:
        state = service.upload(service.create()["id"], photo())
        assert state["analysis"]["assessment"]["countable"]  # Preserve original model claim.
        assert state["status"] == "NEEDS_PHOTO" and state["count"] is None
    finally:
        service.db.close()


@pytest.mark.parametrize("instruction", ["", "N/A", "No further photos needed."])
def test_retake_event_always_gives_a_usable_instruction(tmp_path: Path, instruction: str) -> None:
    service = PhotoReceiving(
        tmp_path / "db", lambda _: result(visibility="cropped", next_photo=instruction)
    )
    try:
        state = service.upload(service.create()["id"], photo())
        assert state["status"] == "NEEDS_PHOTO"
        assert "step back" in state["events"][-1]["detail"]
        assert "complete item" in state["events"][-1]["detail"]
        assert state["analysis"]["assessment"]["next_photo"] == instruction
    finally:
        service.db.close()


def test_failure_and_reshoot_do_not_accumulate_counts(tmp_path: Path) -> None:
    returned = result()

    def reader(_: bytes) -> dict[str, Any]:
        return returned

    service = PhotoReceiving(tmp_path / "db", reader)
    session = service.create()["id"]
    assert service.upload(session, photo())["count"] == 2
    returned = result(objects=[{"x": 0.5, "y": 0.5, "description": "one"}])
    state = service.upload(session, photo("red"))
    assert state["count"] == 1  # A second view is not a second arrival.
    returned = {"assessment": {"garbage": True}}
    state = service.upload(session, photo("blue"))
    assert state["status"] == "UNAVAILABLE" and "count" not in state
    assert "candidate" not in state and "analysis" not in state


def test_po_changed_between_analysis_and_draft(tmp_path: Path) -> None:
    transport = ERPTransport()
    service = PhotoReceiving(
        tmp_path / "db", lambda _: result(), erp=erp(transport), drafts_enabled=True
    )
    session = service.upload(service.create()["id"], photo())["id"]
    transport.po["modified"] = "v2"
    assert service.draft(session)["status"] == "NEEDS_REVIEW"
    assert transport.writes == 0


def test_lost_ack_retry_reconciles_one_external_draft(tmp_path: Path) -> None:
    transport = ERPTransport()
    transport.lose_ack = True
    service = PhotoReceiving(
        tmp_path / "db", lambda _: result(), erp=erp(transport), drafts_enabled=True
    )
    session = service.upload(service.create()["id"], photo())["id"]
    assert service.draft(session)["status"] == "DRAFT_UNKNOWN"
    assert service.draft(session)["status"] == "DRAFT_VERIFIED"
    assert transport.writes == 1


def test_unknown_outcome_empty_lookup_never_reissues_post(tmp_path: Path) -> None:
    transport = ERPTransport()
    transport.lose_ack = True
    service = PhotoReceiving(
        tmp_path / "db", lambda _: result(), erp=erp(transport), drafts_enabled=True
    )
    session = service.upload(service.create()["id"], photo())["id"]
    assert service.draft(session)["status"] == "DRAFT_UNKNOWN"
    committed = transport.receipt
    transport.receipt = None  # Simulate delayed visibility while the original write is in flight.
    assert service.draft(session)["status"] == "DRAFT_UNKNOWN"
    assert transport.writes == 1
    transport.receipt = committed
    transport.po["modified"] = "changed-after-write"
    assert service.draft(session)["status"] == "DRAFT_VERIFIED"
    assert transport.writes == 1


@pytest.mark.parametrize("field", ["warehouse", "uom", "stock_uom", "conversion_factor", "rate"])
def test_draft_reread_checks_full_line_identity(field: str) -> None:
    transport = ERPTransport()
    adapter = erp(transport)
    candidate = adapter.candidate(PhotoAssessment.model_validate(result()["assessment"]))
    adapter.draft(candidate, "same-key")
    assert transport.receipt is not None
    transport.receipt["items"][0][field] = "wrong"
    with pytest.raises(ValueError, match="reread"):
        adapter.draft(candidate, "same-key", lookup_only=True)


@pytest.mark.parametrize("field", ["company", "supplier", "supplier_delivery_note", "docstatus"])
def test_draft_reread_checks_header_identity(field: str) -> None:
    transport = ERPTransport()
    adapter = erp(transport)
    candidate = adapter.candidate(PhotoAssessment.model_validate(result()["assessment"]))
    adapter.draft(candidate, "same-key")
    assert transport.receipt is not None
    transport.receipt[field] = "wrong"
    with pytest.raises(ValueError, match="reread"):
        adapter.draft(candidate, "same-key", lookup_only=True)


def test_old_image_digest_cannot_render_a_new_capture(tmp_path: Path) -> None:
    service = PhotoReceiving(tmp_path / "db", lambda _: result())
    first = service.upload(service.create()["id"], photo())
    service.upload(first["id"], photo("red"))
    with pytest.raises(ValueError, match="not found"):
        service.image(first["id"], first["digest"])


@pytest.mark.parametrize(
    "changed", [{"received_qty": 10}, {"uom": "Box"}, {"stock_uom": "Box"}, {"qty": float("nan")}]
)
def test_remaining_quantity_and_uom_boundaries(tmp_path: Path, changed: dict[str, Any]) -> None:
    transport = ERPTransport()
    transport.po["items"][0].update(changed)
    service = PhotoReceiving(tmp_path / "db", lambda _: result(), erp=erp(transport))
    assert service.upload(service.create()["id"], photo())["status"] == "NEEDS_REVIEW"


def test_demo_write_requires_explicit_switch_and_demo_tenant(tmp_path: Path) -> None:
    transport = ERPTransport()
    service = PhotoReceiving(tmp_path / "db", lambda _: result(), erp=erp(transport, "production"))
    session = service.upload(service.create()["id"], photo())["id"]
    with pytest.raises(ValueError, match="not enabled"):
        service.draft(session)
    service.drafts_enabled = True
    assert service.draft(session)["status"] == "DRAFT_UNKNOWN"
    assert transport.writes == 0


def test_busy_and_restart_preserve_truth(tmp_path: Path) -> None:
    service = PhotoReceiving(tmp_path / "db", lambda _: result())
    session = service.create()
    service.work.acquire()
    with pytest.raises(ValueError, match="progress"):
        service.upload(session["id"], photo())
    service.work.release()
    service._event(session, "ANALYZING", "model running")
    restored = PhotoReceiving(tmp_path / "db", lambda _: result())
    assert restored.current(session["id"])["status"] == "UNAVAILABLE"


def test_http_upload_poll_and_image(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    server = DecisionWorkspaceServer(("127.0.0.1", 0), root, runtime_directory=tmp_path / "server")
    server.photo_receiving = PhotoReceiving(tmp_path / "http-db", lambda _: result())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}/api/v1/photo-receiving"

    def post(path: str, payload: dict[str, Any], origin: str | None = None) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if origin:
            headers["Origin"] = origin
        with urlopen(
            Request(base + path, data=json.dumps(payload).encode(), headers=headers), timeout=5
        ) as response:
            return dict(json.loads(response.read()))

    try:
        session = post("", {})
        observed = post("/upload", {"id": session["id"], "image": photo()})
        assert observed["count"] == 2 and observed["status"] == "COUNT_CANDIDATE"
        with urlopen(base + "?id=" + session["id"]) as response:
            assert json.loads(response.read()) == observed
        with urlopen(base + "/image?id=" + session["id"]) as response:
            assert response.headers["Content-Type"] == "image/jpeg"
            assert Image.open(BytesIO(response.read())).size == (100, 100)
        with pytest.raises(HTTPError) as denied:
            post("/upload", {"id": session["id"], "image": photo()}, "https://attacker.invalid")
        assert denied.value.code == 403
        with pytest.raises(HTTPError):
            post("/upload", {"id": "../../other", "image": photo()})
        with pytest.raises(HTTPError):
            post("/upload", {"id": session["id"], "image": photo(), "qty": 100})
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
