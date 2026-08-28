from __future__ import annotations

import hashlib
import json
import shutil
from copy import deepcopy
from pathlib import Path

import pytest

from the_missing_20.authority_b.models import canonical_json
from the_missing_20.competition.package import (
    M7_AUDIT_ARTIFACT_PATH,
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
    for directory in ("artifacts", "fixtures", "workspace", "docs", "scripts"):
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
    assert {item.evidence_class.value for item in first.evidence} == {
        "PROVEN",
        "SCRIPTED_PROVEN",
        "NOT_PROVEN",
    }
    assert first.audit_digest
    assert tuple(item.path for item in first.source_artifacts) == M7_SOURCE_PATHS


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
