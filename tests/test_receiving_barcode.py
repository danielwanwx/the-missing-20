"""Barcode identity contracts; disclosed ERP doubles, not a live optical claim."""

import json
from urllib.parse import unquote, urlparse

import pytest
from test_photo_receiving import erp, photo, result
from test_receiving_arrivals import MultiReceiptTransport, manifest, scan, service_at

from the_missing_20.adapters.photo_receiving import PhotoReceiving
from the_missing_20.adapters.receiving_barcode import validate_code


class BarcodeTransport(MultiReceiptTransport):
    def __init__(self):
        super().__init__()
        self.item = {
            "name": "M20-TEST",
            "modified": "item-v1",
            "stock_uom": "Nos",
            "item_name": "Demo carton",
            "item_group": "Demo",
            "barcodes": [{"barcode": "8413000065504", "uom": "Nos"}],
        }
        self.native = {"item_code": "M20-TEST", "barcode": "8413000065504", "uom": "Nos"}
        self.reads = []

    def __call__(self, request, timeout):
        path = unquote(urlparse(request.full_url).path)
        self.reads.append(path)
        if "/Item/" in path:
            assert request.method == "GET"
            return json.dumps({"data": self.item}).encode()
        if "scan_barcode" in path:
            assert request.method == "GET"
            return json.dumps({"message": self.native}).encode()
        return super().__call__(request, timeout)


def payload(code="8413000065504", format="ean_13", arrival_id="delivery-A"):
    return dict(code=code, format=format, arrival_id=arrival_id)


@pytest.mark.parametrize(
    "code,format",
    [
        ("8413000065504", "ean_13"),
        ("036000291452", "upc_a"),
        ("box-01", "qr_code"),
        ("M20-TEST", "code_128"),
    ],
)
def test_supported_codes_preserve_identity(code, format):
    assert validate_code(code, format) == code


@pytest.mark.parametrize(
    "code,format",
    [
        ("8413000065505", "ean_13"),
        ("036000291453", "upc_a"),
        ("https://evil.example", "qr_code"),
        ("x\x1dy", "code_128"),
        ("x", []),
        (123, "manual"),
        ("x" * 101, "manual"),
        ("", "manual"),
    ],
)
def test_invalid_input_is_rejected(code, format):
    with pytest.raises(ValueError):
        validate_code(code, format)


def test_product_is_identity_not_quantity_and_replay_is_durable(tmp_path):
    transport = BarcodeTransport()
    path = tmp_path / "barcode.db"
    service = service_at(path, transport)
    first = service.barcode(payload())
    assert first["unit_price"] == 20 and first["price_basis"] == "PURCHASE_ORDER_LINE"
    assert first["quantity_basis"] == "REQUIRES_PHYSICAL_QUANTITY"
    assert first["inventory_changed"] is False and "quantity" not in first
    assert service.barcode(payload()) == first
    assert service.arrivals.scans("delivery-A")["quantity"] == 0
    assert transport.writes == transport.submits == 0
    service.db.close()
    service = service_at(path, transport)
    assert service.barcode(payload()) == first
    work = service.receiving_work(service.arrivals.case_id, "PO-1")
    assert work["arrivals"][0]["barcode_matches"] == [first]
    assert work["arrivals"][1]["barcode_matches"] == []
    transport.po["items"][0]["rate"] = 25
    transport.po["modified"] = "v2"
    second = service.barcode(payload())
    assert second["evidence_id"] != first["evidence_id"] and second["unit_price"] == 25


def test_scanned_item_is_explicitly_bound_to_current_photo_before_receipt(tmp_path):
    transport = BarcodeTransport()
    path = tmp_path / "barcode.db"
    service = service_at(path, transport)
    match = service.barcode(payload())
    service.reader = lambda _: result(item_code="")
    photo_state = service.upload(service.create(arrival_id="delivery-A")["id"], photo())
    confirmed = service.confirm_identity(
        photo_state["id"],
        item_code="M20-TEST",
        expected_version=photo_state["version"],
        confirm_match=True,
        barcode_evidence_id=match["evidence_id"],
    )
    binding = confirmed["identity_confirmation"]
    assert binding["source"] == "operator_confirmed_barcode_photo"
    assert binding["digest"] == photo_state["digest"]
    assert binding["image_version"] == photo_state["image_version"]
    assert binding["barcode_evidence_id"] == match["evidence_id"]
    assert confirmed["analysis"]["assessment"]["item_code"] == "", "do not rewrite model output"
    assert transport.writes == 0
    service.db.close()
    service = service_at(path, transport)
    draft = service.draft(photo_state["id"])
    posted = service.submit(
        draft["id"],
        receipt_name=draft["draft"]["name"],
        expected_version=draft["version"],
        confirm_received=True,
    )
    assert posted["status"] == "RECEIPT_SUBMITTED"
    assert transport.writes == transport.submits == 1


@pytest.mark.parametrize("change", ["other_arrival", "item_version", "po_version", "unknown"])
def test_barcode_photo_binding_rejects_wrong_or_changed_evidence(tmp_path, change):
    transport = BarcodeTransport()
    service = service_at(tmp_path / "db", transport)
    match = service.barcode(
        payload(arrival_id="delivery-B" if change == "other_arrival" else "delivery-A")
    )
    service.reader = lambda _: result(item_code="")
    state = service.upload(service.create(arrival_id="delivery-A")["id"], photo())
    if change == "item_version":
        transport.item["modified"] = "item-v2"
    if change == "po_version":
        transport.po["modified"] = "po-v2"
    with pytest.raises(ValueError, match="Barcode|barcode"):
        service.confirm_identity(
            state["id"],
            item_code="M20-TEST",
            expected_version=state["version"],
            confirm_match=True,
            barcode_evidence_id="not-found" if change == "unknown" else match["evidence_id"],
        )
    assert "identity_confirmation" not in service.current(state["id"])
    assert transport.writes == 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("uom", "Box"),
        ("conversion_factor", 2),
        ("rate", None),
        ("rate", float("inf")),
        ("rate", True),
        ("warehouse", "Other"),
    ],
)
def test_changed_order_terms_fail_closed(tmp_path, field, value):
    transport = BarcodeTransport()
    transport.po["items"][0][field] = value
    service = service_at(tmp_path / "db", transport)
    with pytest.raises(ValueError):
        service.barcode(payload())
    assert transport.writes == 0


def test_native_conflict_and_duplicate_mapping_rejected(tmp_path):
    transport = BarcodeTransport()
    service = service_at(tmp_path / "db", transport)
    transport.native["item_code"] = "OTHER"
    with pytest.raises(ValueError, match="conflicts"):
        service.barcode(payload())
    transport.item["barcodes"] *= 2
    with pytest.raises(ValueError, match="uniquely"):
        service.barcode(payload())


def test_unique_carton_uses_existing_deduplicated_receiving_chain(tmp_path):
    transport = BarcodeTransport()
    service = service_at(tmp_path / "db", transport)
    found = service.barcode(payload("box-01", "qr_code"))
    assert found["kind"] == "handling_unit"
    service.scan(scan())
    service.scan(scan("new-camera-frame"))
    assert service.arrivals.scans("delivery-A")["quantity"] == 1
    service.scan(scan("second-carton", unit="box-02"))
    state = service.upload(service.create(arrival_id="delivery-A")["id"], photo())
    drafted = service.draft(state["id"])
    finished = service.submit(
        state["id"],
        receipt_name=drafted["draft"]["name"],
        expected_version=drafted["version"],
        confirm_received=True,
    )
    assert finished["status"] == "RECEIPT_SUBMITTED"
    assert transport.writes == transport.submits == 1


def test_same_carton_cannot_be_admitted_to_another_case_even_before_scanning(tmp_path):
    transport = BarcodeTransport()
    path = tmp_path / "db"
    first = service_at(path, transport)
    other_manifest = manifest()
    other_manifest["case_id"] = "OTHER"
    with pytest.raises(ValueError, match="already bound"):
        PhotoReceiving(path, lambda _: result(), erp=erp(transport), manifest=other_manifest)
    assert first.db.execute("SELECT count(*) FROM receiving_manifests").fetchone()[0] == 1
    first.db.close()
    restarted = service_at(path, transport)
    assert restarted.scan(scan())["status"] == "RECORDED"
    assert transport.writes == 0


def test_barcode_capacity_preserves_replay_without_silent_history_loss(tmp_path):
    transport = BarcodeTransport()
    path = tmp_path / "db"
    service = service_at(path, transport)
    first = service.barcode(payload())
    for index in range(2, 21):
        transport.po["modified"] = f"v{index}"
        service.barcode(payload())
    transport.po["modified"] = "v21"
    with pytest.raises(ValueError, match="limit"):
        service.barcode(payload())
    transport.po["modified"] = "v1"
    assert service.barcode(payload()) == first
    service.db.close()
    service = service_at(path, transport)
    assert service.barcode(payload()) == first
    assert len(service._barcode_reads(service.arrivals.resolve("delivery-A"))) == 20


@pytest.mark.parametrize("method", ["manual", "camera", "video", "hid"])
def test_scan_preserves_explicit_input_method(tmp_path, method):
    service = service_at(tmp_path / "db", BarcodeTransport())
    response = service.scan({**scan(), "observation_method": method, "barcode_format": "qr_code"})
    assert response["event"]["observation_method"] == method
    assert service.arrivals.scans("delivery-A")["events"][0]["barcode_format"] == "qr_code"
