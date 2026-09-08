from __future__ import annotations

from pathlib import Path

from scripts.decision_workspace_server import DecisionWorkspaceServer
from the_missing_20.adapters.external_source_change import ExternalSourceChangeDetector
from the_missing_20.experiment.events import PublicEventType
from the_missing_20.experiment.session import ExperimentRegistry

ROOT = Path(__file__).resolve().parents[1]


def test_detector_emits_only_after_an_external_semantic_version_changes() -> None:
    detector = ExternalSourceChangeDetector()
    baseline = {
        "sequence": 1,
        "status": "CONNECTED",
        "changed_at": "2026-09-07T01:00:00+00:00",
        "documents": [{"name": "PR-1", "status": "PARTIAL_QUALITY_HOLD"}],
    }

    assert detector.observe("erpnext", baseline) is None
    assert detector.observe("erpnext", {**baseline, "received_at": "later"}) is None

    changed = {
        **baseline,
        "sequence": 2,
        "changed_at": "2026-09-07T01:05:00+00:00",
        "documents": [{"name": "PR-1", "status": "RECEIVED"}],
    }
    event = detector.observe("erpnext", changed)

    assert event == {
        "source_id": "erpnext",
        "source_sequence": 2,
        "status": "CONNECTED",
        "changed_at": "2026-09-07T01:05:00+00:00",
        "record_ids": ["PR-1"],
        "change_count": 1,
    }
    assert detector.observe("erpnext", changed) is None


def test_detector_counts_only_the_records_that_actually_changed() -> None:
    detector = ExternalSourceChangeDetector()
    baseline = {
        "sequence": 1,
        "status": "CONNECTED",
        "documents": [
            {"name": "PO-1", "status": "SUBMITTED"},
            {"name": "PI-1", "status": "PAYMENT_HOLD"},
        ],
    }
    detector.observe("erpnext", baseline)

    event = detector.observe(
        "erpnext",
        {
            **baseline,
            "sequence": 2,
            "documents": [
                {"name": "PO-1", "status": "SUBMITTED"},
                {"name": "PI-1", "status": "OPEN"},
            ],
        },
    )

    assert event is not None
    assert event["record_ids"] == ["PI-1"]
    assert event["change_count"] == 1


def test_server_bridges_a_new_provider_version_into_the_active_ledger(tmp_path: Path) -> None:
    registry = ExperimentRegistry(
        ROOT,
        data_directory=tmp_path / "registry",
        periodic_telemetry_enabled=False,
    )
    server = object.__new__(DecisionWorkspaceServer)
    server.registry = registry
    server.external_source_changes = ExternalSourceChangeDetector()
    try:
        baseline = {"sequence": 1, "status": "CONNECTED", "documents": []}
        server.observe_external_change("erpnext", baseline)
        assert not any(
            event.event_type is PublicEventType.EXTERNAL_SOURCE_CHANGED
            for event in registry.get("missing-20-normal").events_since()
        )

        server.observe_external_change(
            "erpnext",
            {
                "sequence": 2,
                "status": "CONNECTED",
                "changed_at": "2026-09-07T01:05:00+00:00",
                "documents": [{"name": "PR-1", "status": "RECEIVED"}],
            },
        )
        events = [
            event
            for event in registry.get("missing-20-normal").events_since()
            if event.event_type is PublicEventType.EXTERNAL_SOURCE_CHANGED
        ]
        assert len(events) == 1
        assert events[0].payload["source_id"] == "erpnext"
        assert events[0].payload["trigger"]["kind"] == "external_source_change"
    finally:
        registry.close()
