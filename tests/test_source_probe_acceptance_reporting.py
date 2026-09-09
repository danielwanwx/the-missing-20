"""Mechanical probe success must not become unreviewed business acceptance."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from scripts import run_source_investigation_probe as probe
from the_missing_20.agents.live_advisory import (
    CORRELATION_TOOL_NAME,
    SOURCE_TOOL_NAMES,
    AdvisoryDisposition,
    AdvisoryUnavailable,
    AdvisoryValidationError,
    LiveAdvisoryResult,
)
from the_missing_20.config import Settings


@pytest.fixture(autouse=True)
def no_provider_factory(monkeypatch):
    factory = SimpleNamespace(config=SimpleNamespace(model_id="offline-probe-test"))
    monkeypatch.setattr(probe.DashboardAdvisoryGateway, "_factory", lambda self: factory)


def completed_run(*, reason="Timed-out attempt; retry denied per policy.", tools=None):
    return SimpleNamespace(
        result=LiveAdvisoryResult(
            disposition=AdvisoryDisposition.DENY,
            evidence_ids=("ERP-READ-4817", "ATTEMPT-551"),
            reason=reason,
            safe_next_step="Review the existing records.",
            write_performed=False,
        ),
        tool_calls=SOURCE_TOOL_NAMES + (CORRELATION_TOOL_NAME,) if tools is None else tools,
        usage={"request_count": 1},
        latency_ms=1,
        runtime_events=(),
    )


def assert_not_business_accepted(record):
    assert record["status_scope"] == "MECHANICAL_BOUNDARY_ONLY"
    assert record["basis_status"] == "NOT_VALIDATED"
    assert record["answer_quality_status"] == "NOT_REVIEWED"
    assert record["business_acceptance"] is False


def test_program_success_reports_boundary_pass_without_business_acceptance(
    monkeypatch, tmp_path, capsys
):
    packets = []

    def run(packet, **kwargs):
        packets.append(packet)
        return completed_run()

    monkeypatch.setattr(probe, "run_live_advisory", run)
    monkeypatch.setattr(probe, "_read_env_file", lambda path: {})
    monkeypatch.setattr(probe, "load_identity", lambda settings: {})
    monkeypatch.setattr(probe, "validate_identity", lambda identity, settings: None)
    output = tmp_path / "probe.json"
    monkeypatch.setattr(
        probe.sys,
        "argv",
        ["probe", "--confirm", "1", "--variant", "lost_ack", "--output", str(output)],
    )

    assert probe.main() == 0  # Compatible exit code still describes mechanical checks only.

    report = json.loads(output.read_text())
    assert report["exit_code_scope"] == "MECHANICAL_BOUNDARY_ONLY"
    assert report["boundary_status"] == "PASS"
    assert_not_business_accepted(report)
    row = report["cases"][0]
    assert row["status"] == "PASS"
    assert row["boundary_status"] == "PASS"
    assert row["expected"] == packets[0]["expected_disposition"] == "DENY"
    assert packets[0]["explanation_scope"] == "full_investigation"
    assert row["result"]["reason"] == "Timed-out attempt; retry denied per policy."
    assert_not_business_accepted(row)
    rendered = capsys.readouterr().out
    assert "boundary=PASS" in rendered
    assert "business_acceptance=false" in rendered


def test_program_with_a_failed_repetition_reports_failed_boundary(monkeypatch, tmp_path):
    runs = iter([completed_run(), completed_run(tools=())])
    monkeypatch.setattr(probe, "run_live_advisory", lambda *args, **kwargs: next(runs))
    monkeypatch.setattr(probe, "_read_env_file", lambda path: {})
    monkeypatch.setattr(probe, "load_identity", lambda settings: {})
    monkeypatch.setattr(probe, "validate_identity", lambda identity, settings: None)
    output = tmp_path / "mixed-probe.json"
    monkeypatch.setattr(
        probe.sys,
        "argv",
        [
            "probe", "--confirm", "1", "--variant", "lost_ack", "--repetitions", "2",
            "--output", str(output),
        ],
    )

    assert probe.main() == 1

    report = json.loads(output.read_text())
    assert report["boundary_status"] == "FAIL"
    assert [row["boundary_status"] for row in report["cases"]] == ["PASS", "FAIL"]
    assert_not_business_accepted(report)
    for row in report["cases"]:
        assert_not_business_accepted(row)


@pytest.mark.parametrize("failure_type", [AdvisoryValidationError, AdvisoryUnavailable])
def test_failed_run_preserves_diagnostics_and_reports_no_acceptance(monkeypatch, failure_type):
    failure = failure_type("controlled offline failure")
    failure.diagnostics = [{"stage": "validation", "failure": "controlled mismatch"}]
    failure.usage = {"request_count": 2, "incremental_cost_usd": 0.01}

    def run(*args, **kwargs):
        raise failure

    monkeypatch.setattr(probe, "run_live_advisory", run)
    row = probe._run_variant("lost_ack", 1, Settings.from_env({}))

    assert row["status"] == "FAILED"
    assert row["boundary_status"] == "FAIL"
    assert row["expected"] == "DENY"
    assert row["error"] == "controlled offline failure"
    assert row["diagnostics"] == failure.diagnostics
    assert row["usage"] == failure.usage
    assert "result" not in row
    assert_not_business_accepted(row)


@pytest.mark.parametrize(
    "variant,run,mechanical_status",
    [
        ("lost_ack", completed_run(tools=()), "INSUFFICIENT_SOURCE_COVERAGE"),
        ("uncommitted_receipt", completed_run(), "INCOMPLETE_EXPLANATION"),
    ],
)
def test_post_run_boundary_failures_are_not_promoted(monkeypatch, variant, run, mechanical_status):
    monkeypatch.setattr(probe, "run_live_advisory", lambda *args, **kwargs: run)

    row = probe._run_variant(variant, 1, Settings.from_env({}))

    assert row["status"] == mechanical_status
    assert row["boundary_status"] == "FAIL"
    assert_not_business_accepted(row)
