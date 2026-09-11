"""Focused HTTP boundary checks for optional distributor handoffs."""

from __future__ import annotations

import json
from copy import deepcopy
from types import SimpleNamespace
from typing import Any, cast

from scripts.decision_workspace_server import (
    DecisionWorkspaceHandler,
    _distributor_handoff_from_private_config,
    _distributor_native_packet,
)
from the_missing_20.adapters.saas_evidence import SaaSEvidenceConfig, SaaSEvidenceSource


def projection(**changes: object) -> dict[str, object]:
    result: dict[str, object] = {
        "available": True,
        "case_id": "M20-DIST-HANDOFF-A",
        "case_label": "Synthetic distributor handoff",
        "synthetic_input": True,
        "quantities": {
            "ordered": 40,
            "received": 20,
            "usable": 20,
            "held": 0,
            "missing": 20,
            "allocated": 20,
            "dispatched": 0,
            "delivery_confirmed": 0,
            "uom": "Nos",
            "cartons": 2,
        },
        "lots": [],
        "allocations": [],
        "documents": [],
        "shipments": [],
        "events": [],
        "alerts": [],
    }
    result.update(changes)
    return result


class Operations:
    def __init__(self) -> None:
        self.current = projection()
        self.events: list[dict[str, object]] = []
        self.reconciliations: list[str] = []
        self.questions: list[str] = []

    def projection(self) -> dict[str, object]:
        return deepcopy(self.current)

    def record_event(self, event: dict[str, object]) -> dict[str, object]:
        self.events.append(event)
        return deepcopy(self.current)

    def reconcile_receive_arrival(self, event_id: str) -> dict[str, object]:
        self.reconciliations.append(event_id)
        return deepcopy(self.current)

    def approve_event_proposal(self, request: dict[str, object]) -> dict[str, object]:
        self.events.append(request)
        return deepcopy(self.current)

    def ask(self, question: str) -> dict[str, object]:
        self.questions.append(question)
        return {**deepcopy(self.current), "conversation": {"status": "COMPLETE"}}


class Journal:
    def __init__(self) -> None:
        self.rows = [
            {
                "route": "airtable-distributor:base:table",
                "status": "VERIFIED",
                "updated_at": "2026-09-10T12:00:00+00:00",
                "evidence": {
                    "provider": "Airtable",
                    "record_id": "rec-A",
                    "url": "https://airtable.example/rec-A",
                },
            },
            {
                "route": "jira-distributor:DEMO:comment",
                "status": "PENDING",
                "updated_at": "2026-09-10T12:01:00+00:00",
                "last_failure": {"phase": "lookup", "kind": "provider_unavailable"},
            },
        ]
        self.cases: list[str] = []

    def for_capture(self, case_id: str) -> list[dict[str, object]]:
        self.cases.append(case_id)
        return self.rows if case_id == "M20-DIST-HANDOFF-A" else []


class Handoff:
    def __init__(self, *, fail: bool = False) -> None:
        self.journal = Journal()
        self.calls: list[dict[str, object]] = []
        self.fail = fail

    def sync(self, current: dict[str, object]) -> dict[str, object]:
        self.calls.append(deepcopy(current))
        if self.fail:
            raise OSError("provider unavailable")
        return {"status": "CURRENT"}


def handler(operations: Operations, handoff: Handoff | None) -> tuple[Any, list[object]]:
    current = cast(Any, object.__new__(DecisionWorkspaceHandler))
    current.server = SimpleNamespace(
        distributor_operations=operations,
        distributor_handoff=handoff,
    )
    sent: list[object] = []
    current._send_json = lambda _status, value: sent.append(value)
    return current, sent


def result(sent: list[object]) -> dict[str, object]:
    outer = cast(dict[str, object], sent[-1])
    return cast(dict[str, object], outer["distributor_operations"])


def test_event_and_reconcile_sync_only_after_the_valid_erp_result() -> None:
    operations, outbound = Operations(), Handoff()
    current, sent = handler(operations, outbound)

    current._v1_post("/api/v1/distributor-operations/events", {"event_id": "arrival-A"})
    current._v1_post("/api/v1/distributor-operations/reconcile-receive", {"event_id": "arrival-A"})

    assert operations.events == [{"event_id": "arrival-A"}]
    assert operations.reconciliations == ["arrival-A"]
    assert len(outbound.calls) == 2
    assert result(sent)["handoffs"] == [
        {
            "case_id": "M20-DIST-HANDOFF-A",
            "route": "airtable-distributor:base:table",
            "status": "VERIFIED",
            "record_id": "rec-A",
            "url": "https://airtable.example/rec-A",
            "evidence": {
                "provider": "Airtable",
                "record_id": "rec-A",
                "url": "https://airtable.example/rec-A",
            },
            "updated_at": "2026-09-10T12:00:00+00:00",
            "retained": True,
        },
        {
            "case_id": "M20-DIST-HANDOFF-A",
            "route": "jira-distributor:DEMO:comment",
            "status": "PENDING",
            "record_id": "",
            "url": "",
            "evidence": {},
            "updated_at": "2026-09-10T12:01:00+00:00",
            "retained": True,
            "last_failure": {"phase": "lookup", "kind": "provider_unavailable"},
        },
    ]


def test_get_and_ask_only_return_retained_handoffs_without_syncing() -> None:
    operations, outbound = Operations(), Handoff()
    current, sent = handler(operations, outbound)

    current._v1_get("/api/v1/distributor-operations", {})
    current._v1_post("/api/v1/distributor-operations/ask", {"question": "What changed?"})

    assert outbound.calls == []
    assert operations.questions == ["What changed?"]
    assert len(cast(list[object], result(sent)["handoffs"])) == 2


def test_provider_failure_keeps_the_erp_response_and_retained_failure_visible() -> None:
    operations, outbound = Operations(), Handoff(fail=True)
    current, sent = handler(operations, outbound)

    current._v1_post("/api/v1/distributor-operations/events", {"event_id": "arrival-A"})

    assert operations.events == [{"event_id": "arrival-A"}]
    assert len(outbound.calls) == 1
    handoffs = cast(list[dict[str, object]], result(sent)["handoffs"])
    assert handoffs[1]["status"] == "PENDING"
    assert handoffs[1]["last_failure"] == {"phase": "lookup", "kind": "provider_unavailable"}


def test_sync_safety_flag_keeps_retained_handoffs_visible_after_approval() -> None:
    operations, outbound = Operations(), Handoff()
    current, sent = handler(operations, outbound)
    current.server.distributor_handoff_sync_enabled = False

    current._v1_post(
        "/api/v1/distributor-operations/approve-proposal",
        {"proposal_id": "recovered-arrival"},
    )

    assert outbound.calls == []
    assert len(cast(list[object], result(sent)["handoffs"])) == 2


def test_packet_keeps_only_matching_case_provider_readbacks_as_retained() -> None:
    packet = _distributor_native_packet(
        {
            **projection(),
            "handoffs": [
                {
                    "case_id": "M20-DIST-HANDOFF-A",
                    "route": "airtable-distributor:base:table",
                    "status": "VERIFIED",
                    "record_id": "rec-A",
                    "url": "https://airtable.example/rec-A",
                    "evidence": {
                        "provider": "Airtable",
                        "record_id": "rec-A",
                        "url": "https://airtable.example/rec-A",
                    },
                    "updated_at": "2026-09-10T12:00:00+00:00",
                    "retained": True,
                },
                {
                    "case_id": "M20-OTHER",
                    "route": "celigo-distributor:import:channel",
                    "status": "VERIFIED",
                    "record_id": "other",
                    "url": "https://slack.example/other",
                    "updated_at": "2026-09-10T12:00:00+00:00",
                    "retained": True,
                },
            ],
        }
    )

    sources = cast(dict[str, object], cast(dict[str, object], packet["tool_payload"])["sources"])
    airtable = cast(dict[str, object], sources["read_airtable_evidence"])
    celigo = cast(dict[str, object], sources["read_celigo_evidence"])
    assert airtable["status"] == "RETAINED"
    assert airtable["freshness"] == "RETAINED_NOT_REFRESHED"
    assert airtable["records"] == [
        {
            "case_id": "M20-DIST-HANDOFF-A",
            "route": "airtable-distributor:base:table",
            "status": "VERIFIED",
            "record_id": "rec-A",
            "url": "https://airtable.example/rec-A",
            "evidence": {
                "provider": "Airtable",
                "record_id": "rec-A",
                "url": "https://airtable.example/rec-A",
            },
            "updated_at": "2026-09-10T12:00:00+00:00",
            "retained": True,
        }
    ]
    assert celigo["status"] == "UNAVAILABLE" and celigo["records"] == []


def test_packet_does_not_treat_a_pending_handoff_without_evidence_as_a_source() -> None:
    packet = _distributor_native_packet(
        {
            **projection(),
            "handoffs": [
                {
                    "case_id": "M20-DIST-HANDOFF-A",
                    "route": "jira-distributor:DEMO:comment",
                    "status": "PENDING",
                    "evidence": {},
                    "updated_at": "2026-09-10T12:01:00+00:00",
                    "retained": True,
                    "last_failure": {"phase": "lookup", "kind": "provider_unavailable"},
                }
            ],
        }
    )

    sources = cast(dict[str, object], cast(dict[str, object], packet["tool_payload"])["sources"])
    collaboration = cast(dict[str, object], sources["read_collaboration_evidence"])
    assert collaboration["status"] == "UNAVAILABLE"
    assert collaboration["records"] == []
    assert collaboration["retained_physical_events"] == []


def test_private_handoff_config_must_match_the_configured_provider_scope(tmp_path) -> None:
    private = {
        "airtable_base_id": "base-a",
        "airtable_table_id": "table-a",
        "celigo_connection_id": "connection-a",
        "celigo_import_id": "import-a",
        "jira_project_key": "DEMO",
        "jira_receiving_enabled": True,
        "slack_channel_id": "channel-a",
    }
    path = tmp_path / "private-handoff.json"
    path.write_text(json.dumps(private), encoding="utf-8")
    evidence = SaaSEvidenceSource(
        SaaSEvidenceConfig(
            correlation_id="M20-A",
            airtable_base_id="base-a",
            jira_project_key="DEMO",
            jira_base_url="https://demo.atlassian.net",
            slack_channel_id="channel-a",
        )
    )

    handoff = _distributor_handoff_from_private_config(path, evidence=evidence, runtime=tmp_path)

    assert handoff.airtable.route == "airtable-distributor:base-a:table-a"
    private["slack_channel_id"] = "other-channel"
    path.write_text(json.dumps(private), encoding="utf-8")
    try:
        _distributor_handoff_from_private_config(path, evidence=evidence, runtime=tmp_path)
    except ValueError as error:
        assert "destination scope" in str(error)
    else:  # pragma: no cover - the mismatch is a required admission boundary
        raise AssertionError("mismatched private provider scope was accepted")
