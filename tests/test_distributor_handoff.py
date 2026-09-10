"""Scoped distributor cross-app handoff tests with no provider access."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from test_distributor_erp import NativeERP
from test_distributor_erp import r4_config as native_r4_config
from test_distributor_operations import _r4_arrival

from the_missing_20.adapters.distributor_erp import DistributorERP
from the_missing_20.adapters.distributor_handoff import (
    AirtableDistributorCase,
    DistributorHandoff,
    distributor_event,
    milestone,
)
from the_missing_20.adapters.distributor_operations import DistributorOperations
from the_missing_20.adapters.receiving_handoff import HandoffJournal


def projection(**changes: object) -> dict[str, object]:
    current: dict[str, object] = {
        "available": True,
        "case_id": "M20-DIST-R4-FOLLOW-ON",
        "case_label": "R4 remaining 39 Box",
        "synthetic_input": True,
        "parent_purchase_order": {
            "name": "PUR-ORD-2026-00016",
            "ordered": 40,
            "received": 40,
            "outside_case_received": 1,
            "uom": "Box",
        },
        "quantities": {
            "ordered": 39,
            "received": 20,
            "held": 0,
            "missing": 19,
            "dispatched": 0,
            "delivery_confirmed": 0,
            "uom": "Box",
        },
        "allocations": [
            {
                "customer_order": "SO-R4-PRIORITY",
                "requested_quantity": 24,
                "allocated": 20,
                "backordered": 4,
                "dispatched": 0,
            }
        ],
        "allocation_decision": {
            "status": "SELECTED",
            "plan_id": "alloc-2026-09-10-a",
            "state_revision": "state-07",
            "contract_refs": ["SO-R4-PRIORITY", "SO-R4-STANDARD"],
            "rationale": "Earliest contractual promise is served first.",
            "plan": {"version": "m20-contract-allocation/v1"},
            "provider": {"model": "nova-pro", "request_count": 1},
            "usage": {"total_tokens": 623},
        },
        "documents": [
            {
                "kind": "Purchase Receipt",
                "name": "PR-R4-20",
                "status": "Submitted",
                "url": "https://erp.invalid/app/purchase-receipt/PR-R4-20",
            },
            {
                "kind": "Purchase Order",
                "name": "PUR-ORD-2026-00016",
                "status": "Submitted",
                "url": "https://erp.invalid/app/purchase-order/PUR-ORD-2026-00016",
            },
        ],
        "events": [{"event_id": "arrival-20", "item_code": "M20-DEMO-CARTON"}],
        "alerts": [{"code": "PARTS_SHORTAGE", "status": "OPEN"}],
    }
    current.update(changes)
    return current


class Destination:
    def __init__(self, route: str, *, fail: bool = False) -> None:
        self.route, self.fail = route, fail
        self.records: dict[str, dict[str, str]] = {}
        self.sends: list[tuple[dict[str, Any], str]] = []

    def find(self, event: dict[str, Any], key: str) -> dict[str, Any] | None:
        if self.fail:
            raise OSError("provider unavailable")
        return self.records.get(key)

    def send(self, event: dict[str, Any], key: str) -> None:
        if self.fail:
            raise OSError("provider unavailable")
        self.sends.append((event, key))
        self.records[key] = {"record_id": f"{self.route}-{len(self.sends)}"}


class JiraDestination(Destination):
    def lookup(self, event: dict[str, Any]) -> dict[str, Any] | None:
        lifecycle = event.get("lifecycle")
        if lifecycle != "operational-exception" or not self.records:
            return None
        return {"key": "DIST-1"}


def handoff(
    tmp_path: Path, *, airtable_fail: bool = False
) -> tuple[DistributorHandoff, Destination, JiraDestination, Destination]:
    airtable = Destination("airtable", fail=airtable_fail)
    jira = JiraDestination("jira")
    slack = Destination("slack")
    return (
        DistributorHandoff(
            HandoffJournal(tmp_path / "handoffs.sqlite3"),
            airtable=airtable,
            jira=jira,
            slack=slack,
        ),
        airtable,
        jira,
        slack,
    )


def test_current_revision_updates_one_case_and_reuses_one_exception(tmp_path: Path) -> None:
    sync, airtable, jira, slack = handoff(tmp_path)
    first = sync.sync(projection())
    assert first["status"] == "CURRENT"
    assert len(airtable.sends) == 1
    assert len(jira.sends) == 2  # stable case task, then this revision's evidence comment
    assert len(slack.sends) == 1

    assert sync.sync(projection())["destinations"] == first["destinations"]
    assert len(airtable.sends) == 1
    assert len(jira.sends) == 2
    assert len(slack.sends) == 1

    revised_exception = projection(
        quantities={
            "ordered": 39,
            "received": 24,
            "held": 0,
            "missing": 15,
            "dispatched": 20,
            "delivery_confirmed": 0,
            "uom": "Box",
        },
    )
    assert sync.sync(revised_exception)["status"] == "CURRENT"
    assert len(jira.sends) == 3  # same task; a second immutable evidence comment

    revised = projection(
        quantities={
            "ordered": 39,
            "received": 39,
            "held": 0,
            "missing": 0,
            "dispatched": 20,
            "delivery_confirmed": 0,
            "uom": "Box",
        },
        alerts=[],
    )
    assert sync.sync(revised)["status"] == "CURRENT"
    assert len(airtable.sends) == 3
    assert len(jira.sends) == 5  # reconciliation evidence + precise transition, no new issue
    assert len(slack.sends) == 3  # shortage reduction and recovery are distinct milestones
    assert jira.sends[-2][0]["resolution"] == (
        "Recorded operational exception condition is reconciled in current ERP facts; this does "
        "not establish supplier responsibility or physical delivery."
    )

    healthy_revision = projection(
        case_label="R4 recovery recorded",
        quantities=revised["quantities"],
        alerts=[],
    )
    assert sync.sync(healthy_revision)["status"] == "CURRENT"
    assert len(jira.sends) == 6  # revision comment only; the exact resolve is retained
    assert len(slack.sends) == 3


def test_unavailable_projection_has_no_provider_write(tmp_path: Path) -> None:
    sync, airtable, jira, slack = handoff(tmp_path)
    assert sync.sync(projection(available=False)) == {"status": "UNAVAILABLE", "destinations": []}
    assert not airtable.sends and not jira.sends and not slack.sends


def test_provider_failure_is_visible_without_a_fabricated_completion(tmp_path: Path) -> None:
    sync, _airtable, _jira, _slack = handoff(tmp_path, airtable_fail=True)
    result = sync.sync(projection())
    record = result["destinations"][0]
    assert record["status"] == "PENDING"
    assert record["last_failure"] == {"phase": "lookup", "kind": "provider_unavailable"}
    assert all(row.get("status") != "COMPLETED" for row in result["destinations"])


def test_event_preserves_exact_selector_and_erp_identifiers() -> None:
    event = distributor_event(projection())
    assert event is not None
    decision = event["allocation_decision"]
    assert isinstance(decision, dict)
    assert decision["provider"] == {"model": "nova-pro", "request_count": 1}
    assert decision["usage"] == {"total_tokens": 623}
    assert event["parent_purchase_order"] == projection()["parent_purchase_order"]
    assert event["item_identifiers"] == {
        "item_code": "M20-DEMO-CARTON",
        "purchase_order": "PUR-ORD-2026-00016",
    }
    assert event["documents"] == projection()["documents"]


def test_event_reads_parent_po_and_item_from_actual_distributor_projection(tmp_path: Path) -> None:
    native = DistributorERP(NativeERP())  # type: ignore[arg-type]

    class Bridge:
        def read_case(self, config: Mapping[str, object]) -> Mapping[str, object]:
            return native.read_case(config)

        def apply_operation(
            self, config: Mapping[str, object], operation: Mapping[str, object], event_id: str
        ) -> Mapping[str, object]:
            return native.apply_operation(config, operation, event_id)

    service = DistributorOperations(
        tmp_path / "actual-projection.sqlite3", native_r4_config(), Bridge()
    )
    service.record_event(_r4_arrival("arrival-r4-20", "R4-ARRIVAL-20", 20))
    service.record_event(_r4_arrival("arrival-r4-19", "R4-ARRIVAL-19", 19))
    event = distributor_event(service.projection())
    assert event is not None
    assert event["parent_purchase_order"] == {
        "name": "PUR-ORD-2026-00016",
        "ordered": 40,
        "received": 40,
        "outside_case_received": 1,
        "uom": "Box",
    }
    assert event["item_identifiers"] == {
        "item_code": "M20-DEMO-CARTON",
        "purchase_order": "PUR-ORD-2026-00016",
    }


def test_completion_milestone_wins_over_retained_selected_decision() -> None:
    current = projection(
        quantities={
            "ordered": 39,
            "received": 39,
            "held": 0,
            "missing": 0,
            "dispatched": 39,
            "delivery_confirmed": 0,
            "uom": "Box",
        },
        alerts=[{"code": "OLD_SHORTAGE", "status": "RESOLVED"}],
    )
    event = distributor_event(current)
    assert event is not None
    assert milestone(event) == "OPERATIONAL_DISPATCH_RECORDED"


class AirtableAPI:
    def __init__(self) -> None:
        self.config = SimpleNamespace(airtable_base_id="base-1")
        self.rows: list[dict[str, Any]] = []
        self.methods: list[str] = []

    def request(
        self, _provider: str, path: str, *, payload: object = None, method: str | None = None
    ) -> object:
        verb = method or ("POST" if payload is not None else "GET")
        self.methods.append(verb)
        if verb == "GET":
            return {"records": self.rows}
        assert isinstance(payload, dict)
        fields = payload["fields"]
        assert isinstance(fields, dict)
        if verb == "POST":
            self.rows[:] = [{"id": "rec-1", "fields": fields}]
        else:
            assert verb == "PATCH" and path.endswith("/rec-1")
            self.rows[:] = [{"id": "rec-1", "fields": fields}]
        return {"id": "rec-1"}


def test_airtable_case_target_creates_then_patches_the_same_case() -> None:
    api = AirtableAPI()
    target = AirtableDistributorCase(api, "tbl-distributor")  # type: ignore[arg-type]
    event = distributor_event(projection())
    assert event is not None and target.find(event, "one") is None
    target.send(event, "one")
    assert target.find(event, "one")["record_id"] == "rec-1"
    revised = distributor_event(projection(case_label="R4 current fulfillment"))
    assert revised is not None and target.find(revised, "two") is None
    target.send(revised, "two")
    assert api.methods.count("POST") == 1
    assert api.methods.count("PATCH") == 1
    assert (
        json.loads(api.rows[0]["fields"]["Parent Purchase Order"])["name"] == "PUR-ORD-2026-00016"
    )


def test_airtable_empty_alert_readback_is_verified_but_nonempty_mismatch_is_not(
    tmp_path: Path,
) -> None:
    api = AirtableAPI()
    target = AirtableDistributorCase(api, "tbl-distributor")  # type: ignore[arg-type]
    cleared = distributor_event(projection(alerts=[]))
    assert cleared is not None
    fields = target.fields(cleared)
    api.rows[:] = [
        {
            "id": "rec-1",
            "fields": {
                key: value for key, value in fields.items() if key != "Open Operational Alerts"
            },
        }
    ]
    verified = HandoffJournal(tmp_path / "cleared.sqlite3").deliver(
        target.route, cleared, target, business_key="cleared"
    )
    assert verified["status"] == "VERIFIED"

    open_event = distributor_event(projection())
    assert open_event is not None
    assert target.find(open_event, "open") is None
