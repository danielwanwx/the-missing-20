from __future__ import annotations

import hashlib
import json
import shutil
from copy import deepcopy
from pathlib import Path

import pytest

from scripts.run_decision_workspace_smoke import _replay_immutable_projection
from the_missing_20.authority_b.models import canonical_json
from the_missing_20.competition.package import (
    M7_AUDIT_ARTIFACT_PATH,
    M7_REQUIRED_BROWSER_EVENT_TYPES,
    M7_SOURCE_PATHS,
    M7PackageError,
    M7PrivateAudit,
    build_private_audit,
    load_private_audit,
    regenerate_clean_state,
    write_private_audit,
)

ROOT = Path(__file__).resolve().parents[2]


def _copy_package_inputs(destination: Path) -> None:
    for directory in (
        "artifacts",
        "fixtures",
        "workspace",
        "docs",
        "scripts",
        "src",
        "tests",
    ):
        shutil.copytree(ROOT / directory, destination / directory)


def _resign(payload: dict[str, object]) -> None:
    unsigned = {key: value for key, value in payload.items() if key != "audit_digest"}
    payload["audit_digest"] = hashlib.sha256(canonical_json(unsigned).encode("utf-8")).hexdigest()


def test_m7_private_audit_is_truthful_and_byte_stable() -> None:
    first = build_private_audit(ROOT)
    second = build_private_audit(ROOT)

    assert first == second
    assert first.package_status == "PRIVATE_READY_TO_BE_JUDGED"
    assert first.ready_to_be_judged is True
    assert first.ready_to_submit is False
    assert first.public_release is False
    assert first.synthetic_only is True
    assert len(first.seven_step_story) == 7
    assert first.seven_step_story[0].start_seconds == 0
    assert first.seven_step_story[-1].end_seconds == 300
    assert first.cost_boundary.prior_cumulative_estimated_cost_usd == "0.1749144"
    assert first.cost_boundary.runtime_known_token_cost_usd == "0.0489352"
    assert first.cost_boundary.runtime_acceptance_cost_usd == "0.0009296"
    assert first.cost_boundary.cumulative_estimated_cost_usd == "0.1749144"
    assert first.cost_boundary.authority_boundary_chat_cost_status == "NOT_RECORDED_EXCLUDED"
    assert {item.evidence_class.value for item in first.evidence} == {
        "PROVEN",
        "SCRIPTED_PROVEN",
        "NOT_PROVEN",
    }
    assert first.audit_digest
    assert tuple(item.path for item in first.source_artifacts) == M7_SOURCE_PATHS


def test_browser_smoke_allows_local_synthetic_recovery_controls(tmp_path: Path) -> None:
    _copy_package_inputs(tmp_path)
    path = tmp_path / "artifacts/workspace/browser-smoke-v1.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    modes = payload["modes"]
    assert isinstance(modes, list)
    for mode in modes:
        assert isinstance(mode, dict)
        mode["active_write_controls"] = 1
    path.write_text(json.dumps(payload), encoding="utf-8")

    audit = build_private_audit(tmp_path)

    assert audit.status == "PASS"


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("status", "LIVE", "not PASS"),
        ("remote_resources", 1, "unsafe browser capability"),
        ("provider_calls", 1, "provider call"),
        ("local_synthetic_commands", False, "local synthetic"),
        ("write_scope", "remote", "write scope"),
    ),
)
def test_browser_smoke_safety_boundary_fails_closed(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    _copy_package_inputs(tmp_path)
    path = tmp_path / "artifacts/workspace/browser-smoke-v1.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    modes = payload["modes"]
    assert isinstance(modes, list) and isinstance(modes[0], dict)
    modes[0][field] = value
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(M7PackageError, match=message):
        build_private_audit(tmp_path)


def test_browser_smoke_server_boundary_fails_closed(tmp_path: Path) -> None:
    _copy_package_inputs(tmp_path)
    path = tmp_path / "artifacts/workspace/browser-smoke-v1.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict) and isinstance(payload["server"], dict)
    payload["server"]["write_scope"] = "remote"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(M7PackageError, match="server write scope"):
        build_private_audit(tmp_path)


@pytest.mark.parametrize("field", ("incident", "event_ledger", "views"))
def test_browser_smoke_required_proof_deletion_fails_closed(tmp_path: Path, field: str) -> None:
    _copy_package_inputs(tmp_path)
    path = tmp_path / "artifacts/workspace/browser-smoke-v1.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    del payload[field]
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(M7PackageError):
        build_private_audit(tmp_path)


@pytest.mark.parametrize("mutation", ("start", "end", "anchor", "ordering"))
def test_browser_smoke_replay_boundary_tamper_fails_closed(tmp_path: Path, mutation: str) -> None:
    _copy_package_inputs(tmp_path)
    path = tmp_path / "artifacts/workspace/browser-smoke-v1.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict) and isinstance(payload["event_ledger"], dict)
    event_ledger = payload["event_ledger"]
    start = event_ledger["open_replay_sequence_start"]
    end = event_ledger["open_replay_sequence_end"]
    observed_types = event_ledger["observed_event_types"]
    observed_sequences = event_ledger["observed_sequences"]
    assert isinstance(start, int) and isinstance(end, int)
    assert isinstance(observed_types, list) and isinstance(observed_sequences, list)
    if mutation == "start":
        event_ledger["open_replay_sequence_start"] = start + 1
    elif mutation == "end":
        event_ledger["open_replay_sequence_end"] = end + 1
    elif mutation == "anchor":
        detected_index = observed_types.index("incident.detected")
        observed_types[detected_index] = "agent.started"
    else:
        source_index = observed_types.index("source.condition.injected")
        detected_index = observed_types.index("incident.detected")
        observed_types[source_index], observed_types[detected_index] = (
            observed_types[detected_index],
            observed_types[source_index],
        )
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(M7PackageError, match="replay|anchor|detection"):
        build_private_audit(tmp_path)


def test_browser_smoke_replay_sequence_evidence_deletion_fails_closed(tmp_path: Path) -> None:
    _copy_package_inputs(tmp_path)
    path = tmp_path / "artifacts/workspace/browser-smoke-v1.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict) and isinstance(payload["event_ledger"], dict)
    del payload["event_ledger"]["open_replay_sequences"]
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(M7PackageError, match="replay sequence evidence"):
        build_private_audit(tmp_path)


def test_replay_immutable_projection_allows_only_telemetry_growth() -> None:
    before = {
        "projection_sequence": 67,
        "timestamp": "2026-08-28T00:01:07Z",
        "telemetry": {"history": [{"sequence": 4, "unit_counts": {"queue_failed": 20}}]},
        "events": [
            {"sequence": 3, "event_type": "investigation.started"},
            {"sequence": 67, "event_type": "evaluation.completed"},
        ],
        "activity": [
            {"sequence": 3, "event_type": "investigation.started"},
            {"sequence": 67, "event_type": "evaluation.completed"},
        ],
        "replay": {"latest_sequence": 67, "replay_safe": True},
        "execution": {"status": "NOT_STARTED", "effects": []},
    }
    after = {
        **before,
        "projection_sequence": 68,
        "timestamp": "2026-08-28T00:01:08Z",
        "telemetry": {
            "history": [
                {"sequence": 4, "unit_counts": {"queue_failed": 20}},
                {"sequence": 68, "unit_counts": {"queue_failed": 20}},
            ]
        },
        "events": [
            *before["events"],
            {"sequence": 68, "event_type": "telemetry.observed"},
        ],
        "activity": [
            *before["activity"],
            {"sequence": 68, "event_type": "telemetry.observed"},
        ],
        "replay": {"latest_sequence": 68, "replay_safe": True},
    }
    assert _replay_immutable_projection(before) == _replay_immutable_projection(after)

    mutated = {
        **after,
        "execution": {"status": "COMPLETE", "effects": [{"effect_type": "MUTATION"}]},
    }
    assert _replay_immutable_projection(before) != _replay_immutable_projection(mutated)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("two_role_quorum", False, "two-role quorum"),
        ("controlled_executor", False, "ControlledExecutor"),
        ("verification", False, "verification"),
        ("replay", False, "replay"),
    ),
)
def test_browser_smoke_lifecycle_proof_tamper_fails_closed(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    _copy_package_inputs(tmp_path)
    path = tmp_path / "artifacts/workspace/browser-smoke-v1.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict) and isinstance(payload["event_ledger"], dict)
    payload["event_ledger"][field] = value
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(M7PackageError, match=message):
        build_private_audit(tmp_path)


@pytest.mark.parametrize("event_type", M7_REQUIRED_BROWSER_EVENT_TYPES)
def test_browser_smoke_required_event_deletion_fails_closed(
    tmp_path: Path, event_type: str
) -> None:
    _copy_package_inputs(tmp_path)
    path = tmp_path / "artifacts/workspace/browser-smoke-v1.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict) and isinstance(payload["event_ledger"], dict)
    event_ledger = payload["event_ledger"]
    for field in ("required_event_types", "observed_event_types"):
        values = event_ledger[field]
        assert isinstance(values, list)
        values.remove(event_type)
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(M7PackageError):
        build_private_audit(tmp_path)


@pytest.mark.parametrize("field", ("required_event_types", "observed_event_types"))
def test_browser_smoke_unknown_event_replacement_fails_closed(tmp_path: Path, field: str) -> None:
    _copy_package_inputs(tmp_path)
    path = tmp_path / "artifacts/workspace/browser-smoke-v1.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict) and isinstance(payload["event_ledger"], dict)
    values = payload["event_ledger"][field]
    assert isinstance(values, list)
    values[:] = [
        "agent.unknown" if event_type == "agent.handoff" else event_type for event_type in values
    ]
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(M7PackageError):
        build_private_audit(tmp_path)


def test_m7_private_audit_loads_with_digest_and_source_validation(tmp_path: Path) -> None:
    _copy_package_inputs(tmp_path)
    audit = write_private_audit(tmp_path)
    loaded = load_private_audit(tmp_path)

    assert loaded == audit
    assert (tmp_path / M7_AUDIT_ARTIFACT_PATH).read_text(encoding="utf-8").endswith("\n")
    assert (
        M7PrivateAudit.model_validate_json((tmp_path / M7_AUDIT_ARTIFACT_PATH).read_bytes())
        == audit
    )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("status", "BLOCKED"),
        ("package_status", "READY_TO_SUBMIT"),
        ("ready_to_submit", True),
        ("public_release", True),
    ),
)
def test_rehashed_readiness_mutation_fails_closed(
    tmp_path: Path, field: str, value: object
) -> None:
    _copy_package_inputs(tmp_path)
    write_private_audit(tmp_path)
    path = tmp_path / M7_AUDIT_ARTIFACT_PATH
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    payload[field] = value
    _resign(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(M7PackageError):
        load_private_audit(tmp_path)


def test_rehashed_evidence_mutation_fails_closed(tmp_path: Path) -> None:
    _copy_package_inputs(tmp_path)
    write_private_audit(tmp_path)
    path = tmp_path / M7_AUDIT_ARTIFACT_PATH
    baseline = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(baseline, dict)
    evidence = baseline["evidence"]
    assert isinstance(evidence, list)
    evidence[4]["evidence_class"] = "PROVEN"
    evidence[4]["status"] = "PASS"
    _resign(baseline)
    path.write_text(json.dumps(baseline), encoding="utf-8")

    with pytest.raises(M7PackageError):
        load_private_audit(tmp_path)


def test_rehashed_timeline_mutation_fails_closed(tmp_path: Path) -> None:
    _copy_package_inputs(tmp_path)
    write_private_audit(tmp_path)
    path = tmp_path / M7_AUDIT_ARTIFACT_PATH
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    steps = payload["seven_step_story"]
    assert isinstance(steps, list)
    steps[2]["start_seconds"] = 84
    _resign(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(M7PackageError):
        load_private_audit(tmp_path)


def test_changed_provenance_or_overclaim_fails_closed(tmp_path: Path) -> None:
    _copy_package_inputs(tmp_path)
    path = tmp_path / "docs/submission/evidence-matrix.md"
    content = path.read_text(encoding="utf-8")
    path.write_text(
        content.replace("`NOT_PROVEN` | NOT_PROVEN", "`PROVEN` | PASS"), encoding="utf-8"
    )

    with pytest.raises(M7PackageError, match="overclaims real Nova usefulness"):
        build_private_audit(tmp_path)


def test_missing_source_fails_closed(tmp_path: Path) -> None:
    _copy_package_inputs(tmp_path)
    (tmp_path / M7_SOURCE_PATHS[0]).unlink()

    with pytest.raises(M7PackageError):
        build_private_audit(tmp_path)


def test_clean_state_regeneration_matches_private_package() -> None:
    persisted = load_private_audit(ROOT)
    regenerated = regenerate_clean_state(ROOT)

    assert regenerated.audit_digest == persisted.audit_digest
    assert regenerated.source_artifacts == persisted.source_artifacts


def test_audit_source_list_is_not_mutable_by_shallow_copy() -> None:
    baseline = build_private_audit(ROOT)
    payload = deepcopy(baseline.model_dump(mode="json"))
    payload["source_artifacts"].pop()

    with pytest.raises(ValueError):
        M7PrivateAudit.model_validate(payload)
