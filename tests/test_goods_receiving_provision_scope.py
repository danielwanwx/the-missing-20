import copy
import json
from urllib.parse import parse_qs, urlparse

import pytest

from scripts.provision_goods_demo import ITEM, MARKER, first_receiving_manifest
from scripts.provision_goods_demo import provision as provision_order


def provision(client, **kwargs):
    return provision_order(client, business_date="2026-09-08", **kwargs)


def order():
    return {
        "name": "PO-SERVER-ID",
        "docstatus": 1,
        "transaction_date": "2026-09-08",
        "company": "Missing 20 Automotive Demo",
        "currency": "USD",
        "items": [
            {
                "name": "actual-row-123",
                "item_code": ITEM,
                "qty": 40,
                "rate": 50,
                "uom": "Box",
                "stock_uom": "Box",
                "conversion_factor": 1,
                "warehouse": "Stores - M20",
                "description": MARKER,
            }
        ],
    }


def test_scope_uses_actual_server_row_and_plans_only_first_batch():
    scope = first_receiving_manifest(order())
    assert scope["purchase_order"] == "PO-SERVER-ID"
    assert scope["arrivals"][0]["purchase_order_item"] == "actual-row-123"
    assert len(scope["arrivals"][0]["handling_unit_ids"]) == 10
    assert len(scope["arrivals"]) == 1  # No invented quality-location or future arrivals.


@pytest.mark.parametrize(
    "field,value",
    [("uom", "Nos"), ("conversion_factor", 12), ("warehouse", "Other"), ("name", ""), ("qty", 20)],
)
def test_wrong_unit_row_or_order_cannot_create_scope(field, value):
    data = order()
    data["items"][0][field] = value
    with pytest.raises(ValueError):
        first_receiving_manifest(data)


class ActualSchemaERP:
    """The deployed PO has no remarks field; its item description is stored."""

    _environment = "demo"

    def __init__(self):
        self.orders = []
        self.creates = 0
        self.submits = 0
        self.server_date = "2026-09-08"

    def _document(self, doctype, name):
        if doctype == "Item":
            return {"stock_uom": "Box", "is_stock_item": 1}
        if name == "PUR-ORD-2026-00011":
            return {"company": "Missing 20 Automotive Demo", "supplier": "M20 Supplier"}
        return copy.deepcopy(next(row for row in self.orders if row["name"] == name))

    def _request(self, path, *, method="GET", payload=None):
        if method == "POST":
            assert "remarks" not in payload
            self.creates += 1
            stored = copy.deepcopy(payload)
            stored.setdefault("transaction_date", self.server_date)
            stored.update(name="PO-REAL-SCHEMA", docstatus=0)
            stored["items"][0]["name"] = "server-line"
            self.orders.append(stored)
            return {"data": stored}
        filters = json.loads(parse_qs(urlparse(path).query)["filters"][0])
        assert all(row[0] != "remarks" for row in filters), "Field not permitted: remarks"
        if "/Item?" in path:
            return {"data": [{"name": ITEM}]}
        return {"data": [{"name": row["name"]} for row in self.orders]}

    def _submit_document(self, document):
        self.submits += 1
        next(row for row in self.orders if row["name"] == document["name"])["docstatus"] = 1


def test_creation_uses_erp_default_date_not_host_utc():
    client = ActualSchemaERP()
    provision(client)
    assert client.orders[0]["transaction_date"] == "2026-09-08"
    assert client.orders[0]["schedule_date"] == "2026-09-08"


def test_unexpected_erp_business_date_stops_before_submit():
    client = ActualSchemaERP()
    client.server_date = "2026-09-09"
    with pytest.raises(ValueError, match="date"):
        provision(client)
    assert client.submits == 0


def test_submitted_wrong_date_order_is_not_reused_as_receiving_scope():
    client = ActualSchemaERP()
    doc = order()
    doc.update(supplier="M20 Supplier", transaction_date="2026-09-09")
    client.orders = [doc]
    with pytest.raises(ValueError, match="date"):
        provision(client)
    assert client.creates == client.submits == 0


def test_postsubmit_changed_date_cannot_issue_a_verified_manifest():
    client = ActualSchemaERP()
    submit = client._submit_document

    def changing_submit(document):
        submit(document)
        client.orders[0]["transaction_date"] = "2026-09-09"

    client._submit_document = changing_submit
    with pytest.raises(ValueError, match="not verified"):
        provision(client)


def test_cancelled_order_is_preserved_and_one_amendment_is_reused():
    client = ActualSchemaERP()
    original = order()
    original.update(docstatus=2, supplier="M20 Supplier", transaction_date="2026-09-09")
    client.orders.append(original)
    first = provision(client)
    second = provision(client)
    assert client.orders[0]["docstatus"] == 2
    assert client.orders[1]["amended_from"] == original["name"]
    assert first["purchase_order"] == second["purchase_order"]
    assert client.creates == client.submits == 1


def test_actual_po_schema_and_rerun_reuse_one_order():
    client = ActualSchemaERP()
    first = provision(client)
    second = provision(client)
    assert first["purchase_order"] == second["purchase_order"] == "PO-REAL-SCHEMA"
    assert client.creates == 1


def test_single_carton_photo_scope_does_not_pretend_ten_arrived():
    scope = first_receiving_manifest(order(), first_batch_size=1)
    assert scope["arrivals"][0]["handling_unit_ids"] == ["M20-CARTON-001"]


@pytest.mark.parametrize("changed", ["company", "supplier", "description"])
def test_changed_final_order_cannot_be_submitted(changed):
    client = ActualSchemaERP()
    doc = order()
    doc.update(docstatus=0, supplier="M20 Supplier")
    client.orders = [doc]
    read = client._document
    count = 0

    def changing_read(doctype, name):
        nonlocal count
        result = read(doctype, name)
        if name == doc["name"]:
            count += 1
            if count >= 2:
                target = result["items"][0] if changed == "description" else result
                target[changed] = "CHANGED"
        return result

    client._document = changing_read
    with pytest.raises(ValueError):
        provision(client)
    assert client.creates == client.submits == 0


@pytest.mark.parametrize("case", ["truncated", "multiple", "wrong_marker", "multiline"])
def test_ambiguous_discovery_never_creates_or_submits(case):
    client = ActualSchemaERP()
    doc = order()
    doc.update(docstatus=0, supplier="M20 Supplier")
    if case == "truncated":
        client.orders = [dict(doc, name=f"PO-{n}") for n in range(50)]
    elif case == "multiple":
        client.orders = [doc, dict(doc, name="PO-SECOND")]
    elif case == "wrong_marker":
        doc["items"][0]["description"] = "Other work"
        client.orders = [doc]
    else:
        doc["items"].append(copy.deepcopy(doc["items"][0]))
        client.orders = [doc]
    with pytest.raises(ValueError):
        provision(client)
    assert client.creates == client.submits == 0


def test_new_pilot_preserves_old_order_and_has_disjoint_physical_ids():
    client = ActualSchemaERP()
    old = order()
    old.update(supplier="M20 Supplier")
    client.orders = [copy.deepcopy(old)]
    client.server_date = "2026-09-09"
    kwargs = dict(business_date="2026-09-09", first_batch_size=1, case_id="M20-GOODS-20260909-40")
    first = provision_order(client, **kwargs)
    second = provision_order(client, **kwargs)
    assert client.orders[0] == old
    assert first["purchase_order"] == second["purchase_order"] != old["name"]
    assert client.creates == client.submits == 1
    old_units = first_receiving_manifest(old)["arrivals"][0]["handling_unit_ids"]
    new_units = first["receiving_manifest"]["arrivals"][0]["handling_unit_ids"]
    assert new_units == ["M20-GOODS-20260909-40-001"]
    assert not set(old_units).intersection(new_units)


@pytest.mark.parametrize(
    "case_id", ["other", "M20-GOODS-20260230-40", "M20-GOODS-20260909-400", None]
)
def test_invalid_new_case_cannot_touch_erp(case_id):
    client = ActualSchemaERP()
    with pytest.raises(ValueError):
        provision_order(client, business_date="2026-09-09", case_id=case_id)
    assert client.creates == client.submits == 0


def test_new_case_cannot_bind_old_order_or_unrecognized_marker():
    with pytest.raises(ValueError):
        first_receiving_manifest(order(), case_id="M20-GOODS-20260909-40")
    client = ActualSchemaERP()
    invalid = order()
    invalid["items"][0]["description"] = "M20-GOODS-20260230-40 - SYNTHETIC TEST ORDER"
    client.orders = [invalid]
    with pytest.raises(ValueError):
        provision_order(client, business_date="2026-09-09", case_id="M20-GOODS-20260909-40")
    assert client.creates == client.submits == 0


def test_case_date_mismatch_stops_before_any_erp_access():
    client = ActualSchemaERP()

    def forbidden(*args, **kwargs):
        pytest.fail("Mismatched dates must not reach the ERP")

    client._document = forbidden
    client._request = forbidden
    with pytest.raises(ValueError, match="case date"):
        provision_order(client, business_date="2026-09-09", case_id="M20-GOODS-20260910-40")
    assert client.creates == client.submits == 0
