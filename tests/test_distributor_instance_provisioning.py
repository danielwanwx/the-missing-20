"""Offline identity and exact-marker checks for fresh component provisioning."""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from scripts.provision_distributor_operations import (
    COMPANY,
    COMPONENT_CASE_ID,
    COMPONENT_MARKER,
    COMPONENT_PO_MARKER,
    COMPONENT_UNIT_RATE,
    ProvisioningBlocked,
    _component_identities,
    _component_plan,
    _component_purchase_order,
    _sales_order,
)


def _plan(instance: str | None = None) -> dict[str, object]:
    return _component_plan(
        supplier="M20 Supplier",
        date="2026-09-10",
        purchase_order="PUR-ORD-FRESH",
        purchase_order_item="PO-ITEM-FRESH",
        instance=instance,
    )


def test_default_component_plan_stays_on_existing_identity_and_terms() -> None:
    plan = _plan()
    assert plan["case_id"] == COMPONENT_CASE_ID
    assert plan["marker"] == COMPONENT_MARKER
    assert plan["warehouses"] == {
        "accepted": "REQUIRES_PROVISION_COMPONENT_ACCEPTED_WAREHOUSE",
        "quarantine": "REQUIRES_PROVISION_COMPONENT_INSPECTION_WAREHOUSE",
    }
    assert [row["batch_no"] for row in plan["receipt_plans"]] == [
        "M20-DIST-COMP-BATCH-A",
        "M20-DIST-COMP-BATCH-B",
        "M20-DIST-COMP-BATCH-C",
    ]
    assert "allocation_policy" not in plan
    assert plan["allocations"] == [
        {
            "customer_order": "REQUIRES_PROVISION_COMPONENT_ORDER_25",
            "requested_quantity": 25,
            "priority": 1,
        },
        {
            "customer_order": "REQUIRES_PROVISION_COMPONENT_ORDER_15",
            "requested_quantity": 15,
            "priority": 2,
        },
    ]


def test_fresh_namespaces_are_disjoint_and_keep_native_tranches() -> None:
    one, two = _plan("FRESH40"), _plan("FRESH41")
    one_ids = _component_identities("FRESH40")
    two_ids = _component_identities("FRESH41")
    assert set(one_ids.values()).isdisjoint(set(two_ids.values()))
    assert one["marker"] != COMPONENT_MARKER
    assert one["warehouses"] == {
        "accepted": "M20 Distributor Component FRESH40 Accepted",
        "quarantine": "M20 Distributor Component FRESH40 Inspection",
    }
    assert [row["batch_no"] for row in one["receipt_plans"]] == [
        "M20-DIST-COMP-FRESH40-BATCH-A",
        "M20-DIST-COMP-FRESH40-BATCH-B",
        "M20-DIST-COMP-FRESH40-BATCH-C",
    ]
    assert (
        one["pick_tranches"]
        == two["pick_tranches"]
        == [
            {
                "customer_order": "REQUIRES_PROVISION_COMPONENT_ORDER_25",
                "lot": "LOT-A",
                "quantity": 20,
            },
            {
                "customer_order": "REQUIRES_PROVISION_COMPONENT_ORDER_25",
                "lot": "LOT-B",
                "quantity": 5,
            },
            {
                "customer_order": "REQUIRES_PROVISION_COMPONENT_ORDER_15",
                "lot": "LOT-B",
                "quantity": 13,
            },
            {
                "customer_order": "REQUIRES_PROVISION_COMPONENT_ORDER_15",
                "lot": "LOT-C",
                "quantity": 2,
            },
        ]
    )


def test_fresh_contract_terms_make_date_precede_customer_priority() -> None:
    plan = _plan("FRESH40")
    assert plan["allocation_policy"] == {"version": "v1"}
    assert plan["allocations"] == [
        {
            "customer_order": "REQUIRES_PROVISION_COMPONENT_ORDER_25",
            "requested_quantity": 25,
            "priority": 2,
            "promised_delivery_at": "2026-09-11T09:00:00+00:00",
            "customer_priority": 2,
            "partial_dispatch": True,
            "minimum_dispatch_quantity": 10,
            "allow_final_remainder": True,
        },
        {
            "customer_order": "REQUIRES_PROVISION_COMPONENT_ORDER_15",
            "requested_quantity": 15,
            "priority": 1,
            "promised_delivery_at": "2026-09-12T09:00:00+00:00",
            "customer_priority": 1,
            "partial_dispatch": True,
            "minimum_dispatch_quantity": 5,
            "allow_final_remainder": True,
        },
    ]


class SalesOrderClient:
    def __init__(self, existing: Mapping[str, object] | None = None) -> None:
        self.existing = existing
        self.created: Mapping[str, object] | None = None

    def _request(self, path: str, *, method: str = "GET", payload: object = None) -> object:
        if path.startswith("/api/resource/Sales%20Order") and method == "GET":
            return {"data": [] if self.existing is None else [{"name": self.existing["name"]}]}
        if path == "/api/resource/Sales%20Order" and method == "POST":
            assert isinstance(payload, Mapping)
            self.created = {**payload, "name": "SO-FRESH", "docstatus": 0}
            return {"data": self.created}
        if path == "/api/method/frappe.client.submit" and method == "POST":
            assert self.created is not None
            self.created = {**self.created, "docstatus": 1}
            return {"message": self.created}
        raise AssertionError(path)

    def _document(self, doctype: str, name: str) -> Mapping[str, object]:
        assert doctype == "Sales Order"
        if self.existing is not None:
            return self.existing
        assert self.created is not None and self.created["name"] == name
        return self.created


def _sales_order_existing(delivery_date: str) -> dict[str, object]:
    marker = f"{_component_identities('FRESH40')['marker']} CUSTOMER-2"
    return {
        "name": "SO-FRESH",
        "doctype": "Sales Order",
        "docstatus": 1,
        "company": COMPANY,
        "customer": "CUST-FRESH",
        "po_no": marker,
        "delivery_date": delivery_date,
        "items": [
            {
                "item_code": "M20-DIST-COMPONENT-NOS",
                "qty": 25,
                "uom": "Nos",
                "stock_uom": "Nos",
                "conversion_factor": 1,
                "warehouse": "M20 Distributor Component FRESH40 Accepted",
                "rate": 6.0,
                "delivery_date": delivery_date,
            }
        ],
    }


def test_new_instance_sales_order_uses_promise_date_but_keeps_transaction_date() -> None:
    client = SalesOrderClient()
    _sales_order(
        client,  # type: ignore[arg-type]
        customer={"name": "CUST-FRESH"},
        warehouse="M20 Distributor Component FRESH40 Accepted",
        quantity=25,
        priority=2,
        date="2026-09-10",
        item_code="M20-DIST-COMPONENT-NOS",
        uom="Nos",
        marker_prefix=_component_identities("FRESH40")["marker"],
        unit_rate=6.0,
        delivery_date="2026-09-11",
    )
    assert client.created is not None
    assert client.created["transaction_date"] == "2026-09-10"
    assert client.created["delivery_date"] == "2026-09-11"
    assert client.created["items"] == [
        {
            "item_code": "M20-DIST-COMPONENT-NOS",
            "description": "M20 DIST COMPONENT FRESH40 SYNTHETIC CUSTOMER-2",
            "qty": 25,
            "uom": "Nos",
            "stock_uom": "Nos",
            "conversion_factor": 1,
            "warehouse": "M20 Distributor Component FRESH40 Accepted",
            "rate": 6.0,
            "delivery_date": "2026-09-11",
        }
    ]


def test_new_instance_sales_order_rejects_a_wrong_promise_date_on_readback() -> None:
    with pytest.raises(ProvisioningBlocked, match="synthetic scope"):
        _sales_order(
            SalesOrderClient(_sales_order_existing("2026-09-10")),  # type: ignore[arg-type]
            customer={"name": "CUST-FRESH"},
            warehouse="M20 Distributor Component FRESH40 Accepted",
            quantity=25,
            priority=2,
            date="2026-09-10",
            item_code="M20-DIST-COMPONENT-NOS",
            uom="Nos",
            marker_prefix=_component_identities("FRESH40")["marker"],
            unit_rate=6.0,
            delivery_date="2026-09-11",
        )


def _purchase_order(
    name: str, marker: str, *, extra_component_line: bool = False
) -> dict[str, object]:
    items: list[dict[str, object]] = [
        {
            "name": f"{name}-ITEM",
            "item_code": "M20-DIST-COMPONENT-NOS",
            "description": marker,
            "qty": 40,
            "uom": "Nos",
            "stock_uom": "Nos",
            "conversion_factor": 1,
            "rate": COMPONENT_UNIT_RATE,
            "warehouse": "M20 Distributor Component FRESH40 Inspection",
        }
    ]
    if extra_component_line:
        items.append({**items[0], "name": f"{name}-OTHER", "description": "other instance"})
    return {
        "name": name,
        "doctype": "Purchase Order",
        "docstatus": 1,
        "company": COMPANY,
        "supplier": "M20 Supplier",
        "currency": "USD",
        "items": items,
    }


class PurchaseOrderClient:
    def __init__(self, documents: Mapping[str, Mapping[str, object]]) -> None:
        self.documents = dict(documents)
        self.posts = 0

    def _request(self, path: str, *, method: str = "GET", payload: object = None) -> object:
        assert path.startswith("/api/resource/Purchase%20Order")
        if method == "GET":
            return {
                "data": [
                    {"name": name, "docstatus": row["docstatus"]}
                    for name, row in self.documents.items()
                ]
            }
        self.posts += 1
        raise AssertionError("existing exact marker must not create a purchase order")

    def _document(self, doctype: str, name: str) -> Mapping[str, object]:
        assert doctype == "Purchase Order"
        return self.documents[name]


def test_exact_instance_po_discovery_ignores_history_and_is_idempotent() -> None:
    marker = _component_identities("FRESH40")["po_marker"]
    client = PurchaseOrderClient(
        {
            "PUR-ORD-PO17": _purchase_order("PUR-ORD-PO17", COMPONENT_PO_MARKER),
            "PUR-ORD-FRESH40": _purchase_order("PUR-ORD-FRESH40", marker),
        }
    )
    for _ in range(2):
        order, line = _component_purchase_order(
            client,  # type: ignore[arg-type]
            supplier="M20 Supplier",
            inspection_warehouse="M20 Distributor Component FRESH40 Inspection",
            date="2026-09-10",
            instance="FRESH40",
        )
        assert order["name"] == "PUR-ORD-FRESH40" and line["name"] == "PUR-ORD-FRESH40-ITEM"
    assert client.posts == 0


@pytest.mark.parametrize("documents", ["duplicate", "malformed"])
def test_exact_instance_po_rejects_duplicate_or_malformed_matches(documents: str) -> None:
    marker = _component_identities("FRESH40")["po_marker"]
    source: dict[str, Mapping[str, object]] = {
        "PUR-ORD-FRESH40": _purchase_order(
            "PUR-ORD-FRESH40", marker, extra_component_line=documents == "malformed"
        )
    }
    if documents == "duplicate":
        source["PUR-ORD-FRESH40-SECOND"] = _purchase_order("PUR-ORD-FRESH40-SECOND", marker)
    with pytest.raises(ProvisioningBlocked, match="ambiguous|malformed"):
        _component_purchase_order(
            PurchaseOrderClient(source),  # type: ignore[arg-type]
            supplier="M20 Supplier",
            inspection_warehouse="M20 Distributor Component FRESH40 Inspection",
            date="2026-09-10",
            instance="FRESH40",
        )


@pytest.mark.parametrize("instance", ["fresh40", "FRESH_40", ""])
def test_instance_requires_a_canonical_namespace(instance: str) -> None:
    with pytest.raises(ProvisioningBlocked, match="instance"):
        _component_identities(instance)
