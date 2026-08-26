from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError

from the_missing_20.adapters.sqlite_case_store import SQLiteCaseStore
from the_missing_20.adapters.synthetic_enterprise import SyntheticEnterprise
from the_missing_20.application.diagnosis import diagnose_retryable_message
from the_missing_20.domain.enterprise import BusinessEffect, EnterpriseSnapshot, ScenarioFixture
from the_missing_20.domain.errors import InvalidEventPayload
from the_missing_20.domain.execution import EffectType
from the_missing_20.domain.models import EvidenceItem
from the_missing_20.evaluation.golden_runner import (
    GoldenRunner,
    _allowed_local_effect_identities,
    _false_effect_calculation,
    crash_recovery_duplicate_count,
)
from the_missing_20.evaluation.invariants import evaluate_invariants
from the_missing_20.evaluation.models import GoldenManifest, GoldenOutcome

ROOT = Path(__file__).resolve().parents[2]


def test_golden_v1_runs_all_real_sqlite_cases(tmp_path: Path) -> None:
    result = GoldenRunner(ROOT, tmp_path / "artifacts").run_all()

    assert result["status"] == "PASS"
    assert result["case_count"] == 16
    assert result["passed_case_count"] == 16
    assert result["failed_invariant_count"] == 0
    assert result["safety_counters"] == {
        "false_receipt_restarts": 0,
        "false_invoice_releases": 0,
        "cross_role_grants": 0,
        "replay_created_effects": 0,
        "crash_recovery_duplicate_effects": 0,
    }
    reports = sorted((tmp_path / "artifacts/cases").glob("*.json"))
    assert len(reports) == 16
    for path in reports:
        report = json.loads(path.read_text(encoding="utf-8"))
        assert report["sqlite_proof"]["reopened_before_final_read"] is True
        assert report["replay"]["verified"] is True
        assert all(item["passed"] for item in report["invariants"])
        assert "/Users/" not in path.read_text(encoding="utf-8")
        assert "golden-v1-local-key" not in path.read_text(encoding="utf-8")


def test_investigation_assessment_is_complete_and_replay_validated(tmp_path: Path) -> None:
    runner = GoldenRunner(ROOT, tmp_path / "artifacts")
    manifest = runner.load_manifest(ROOT / "golden/cases/01-retryable-lock-main-path.json")
    work = tmp_path / "work"
    report = runner.run_case(manifest, work)

    assessment_event = next(
        event for event in report["events"] if event["event"] == "RECEIPT_RESTART_RECOMMENDED"
    )
    payload = json.loads(assessment_event["payload_json"])
    assert payload == {"assessment": report["assessments"][0]}

    empty_payload = "{}"
    empty_digest = hashlib.sha256(empty_payload.encode()).hexdigest()
    with sqlite3.connect(work / "case.sqlite") as connection:
        event_json = dict(assessment_event)
        event_json["payload_json"] = empty_payload
        event_json["payload_digest"] = empty_digest
        connection.execute(
            "UPDATE case_events SET payload_json = ?, event_json = ? WHERE event_id = ?",
            (empty_payload, json.dumps(event_json), assessment_event["event_id"]),
        )

    with pytest.raises(InvalidEventPayload, match="assessment event payload is incomplete"):
        SQLiteCaseStore(work / "case.sqlite").replay_case(report["case_id"])


def test_replay_rejects_tampered_assessment_evidence_ids(tmp_path: Path) -> None:
    runner = GoldenRunner(ROOT, tmp_path / "artifacts")
    manifest = runner.load_manifest(ROOT / "golden/cases/01-retryable-lock-main-path.json")
    work = tmp_path / "work"
    report = runner.run_case(manifest, work)
    event = next(
        item for item in report["events"] if item["event"] == "RECEIPT_RESTART_RECOMMENDED"
    )
    payload = json.loads(event["payload_json"])
    assessment = payload["assessment"]
    assessment["admitted_evidence_ids"] = ["tampered-evidence"]
    assessment["evaluation"]["validated_evidence_ids"] = ["tampered-evidence"]
    payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    event_json = {
        **event,
        "payload_json": payload_json,
        "payload_digest": hashlib.sha256(payload_json.encode()).hexdigest(),
    }
    with sqlite3.connect(work / "case.sqlite") as connection:
        connection.execute(
            "UPDATE case_events SET payload_json = ?, event_json = ? WHERE event_id = ?",
            (payload_json, json.dumps(event_json), event["event_id"]),
        )
    with pytest.raises(InvalidEventPayload, match="assessment"):
        SQLiteCaseStore(work / "case.sqlite").replay_case(report["case_id"])


def test_crash_duplicate_count_catches_same_source_different_execution(tmp_path: Path) -> None:
    runner = GoldenRunner(ROOT, tmp_path / "artifacts")
    manifest = runner.load_manifest(ROOT / "golden/cases/16-crash-recovery.json")
    runner.run_case(manifest, tmp_path / "work")
    snapshot = SyntheticEnterprise(tmp_path / "work" / "enterprise.sqlite").read_snapshot()
    effect = next(
        item for item in snapshot.business_effects if item.effect_type.value == "RECEIPT_RESTART"
    )
    document = snapshot.material_documents[0]
    duplicate_effect = effect.model_copy(
        update={"effect_id": "duplicate-effect", "execution_id": "different-execution"}
    )
    duplicate_document = document.model_copy(
        update={"material_document_id": "duplicate-document", "execution_id": "different-execution"}
    )
    assert (
        crash_recovery_duplicate_count(
            (effect, duplicate_effect),
            (document, duplicate_document),
            execution_id=effect.execution_id,
            source_id=effect.source_record_id,
        )
        > 0
    )

    same_execution_different_source = effect.model_copy(
        update={"effect_id": "same-execution-different-source", "source_record_id": "other-source"}
    )
    assert (
        crash_recovery_duplicate_count(
            (effect, same_execution_different_source),
            (document,),
            execution_id=effect.execution_id,
            source_id=effect.source_record_id,
        )
        == 1
    )


def test_eligible_case_extra_execution_is_a_false_effect(tmp_path: Path) -> None:
    runner = GoldenRunner(ROOT, tmp_path / "artifacts")
    manifest = runner.load_manifest(ROOT / "golden/cases/01-retryable-lock-main-path.json")
    report = runner.run_case(manifest, tmp_path / "work")
    baseline = SyntheticEnterprise(tmp_path / "work" / "enterprise.sqlite").read_snapshot()
    allowed = _allowed_local_effect_identities(manifest, baseline)

    final = report["final_authoritative_state"]
    local_effect = next(
        BusinessEffect.model_validate_json(json.dumps(item))
        for item in final["business_effects"]
        if item["effect_type"] == "RECEIPT_RESTART"
    )
    extra = local_effect.model_copy(
        update={
            "effect_id": "eligible-case-extra-execution",
            "execution_id": "case-01-unexpected-receipt-execution",
            "idempotency_key": "case-01-unexpected-receipt-effect",
        }
    )
    calculation = _false_effect_calculation((local_effect, extra), allowed)

    assert calculation["receipt"]["false_count"] == 1
    assert calculation["receipt"]["outside_allowed_identities"] == [
        {
            "effect_type": "RECEIPT_RESTART",
            "execution_id": "case-01-unexpected-receipt-execution",
            "idempotency_key": "case-01-unexpected-receipt-effect",
            "source_record_id": local_effect.source_record_id,
        }
    ]


def test_safe_noop_case_exact_receipt_identity_is_still_false(tmp_path: Path) -> None:
    runner = GoldenRunner(ROOT, tmp_path / "artifacts")
    manifest = runner.load_manifest(ROOT / "golden/cases/03-receipt-posted-after-approval.json")
    report = runner.run_case(manifest, tmp_path / "work")
    baseline = EnterpriseSnapshot.model_validate_json(
        json.dumps(report["baseline_authoritative_state"])
    )
    allowed = _allowed_local_effect_identities(manifest, baseline)

    existing_effect = next(
        BusinessEffect.model_validate_json(json.dumps(item))
        for item in report["final_authoritative_state"]["business_effects"]
        if item["effect_type"] == "INVOICE_RELEASE"
    )
    injected_receipt = existing_effect.model_copy(
        update={
            "effect_id": "safe-noop-case-injected-receipt",
            "effect_type": EffectType.RECEIPT_RESTART,
            "execution_id": manifest.request.receipt_execution_id,
            "idempotency_key": manifest.request.receipt_idempotency_key,
            "source_record_id": baseline.failed_message.message_id,
        }
    )
    calculation = _false_effect_calculation((injected_receipt,), allowed)

    assert report["safety_calculation"]["false_receipt_restarts"] == 0
    assert calculation["receipt"]["allowed_identities"] == []
    assert calculation["receipt"]["false_count"] == 1


def test_case_two_rejects_a_ten_unit_external_document() -> None:
    source = json.loads(
        (ROOT / "fixtures/scenarios/golden/receipt-already-posted.json").read_text(encoding="utf-8")
    )
    source["material_documents"][0]["quantity"] = 10
    with pytest.raises(ValidationError, match="exact message quantity"):
        ScenarioFixture.model_validate_json(json.dumps(source))


def test_case_two_diagnosis_rejects_a_ten_unit_admitted_document(tmp_path: Path) -> None:
    runner = GoldenRunner(ROOT, tmp_path / "artifacts")
    manifest = runner.load_manifest(ROOT / "golden/cases/02-receipt-already-posted.json")
    report = runner.run_case(manifest, tmp_path / "work")
    evidence = [EvidenceItem.model_validate_json(json.dumps(item)) for item in report["evidence"]]
    material_index = next(
        index
        for index, item in enumerate(evidence)
        if item.source_type.value == "MATERIAL_DOCUMENT"
    )
    material = evidence[material_index]
    documents = list(cast(list[dict[str, Any]], material.admitted_fields["material_documents"]))
    documents[0] = {**documents[0], "quantity": 10}
    corrupted_material = material.model_copy(
        update={
            "admitted_fields": {
                **material.admitted_fields,
                "material_documents": documents,
            }
        }
    )
    evidence[material_index] = corrupted_material

    hypothesis, _ = diagnose_retryable_message(tuple(evidence), trace_id=report["trace_id"])
    assert hypothesis.hypothesis_type.value != "ALREADY_POSTED"


@pytest.mark.parametrize("field", ["case_id", "trace_id"])
def test_diagnosis_rejects_external_history_context_mismatch(tmp_path: Path, field: str) -> None:
    runner = GoldenRunner(ROOT, tmp_path / "artifacts")
    manifest = runner.load_manifest(ROOT / "golden/cases/02-receipt-already-posted.json")
    report = runner.run_case(manifest, tmp_path / "work")
    evidence = [EvidenceItem.model_validate_json(json.dumps(item)) for item in report["evidence"]]
    material_index = next(
        index
        for index, item in enumerate(evidence)
        if item.source_type.value == "MATERIAL_DOCUMENT"
    )
    material = evidence[material_index]
    effects = list(cast(list[dict[str, Any]], material.admitted_fields["business_effects"]))
    effects[0] = {**effects[0], field: "tampered-context"}
    evidence[material_index] = material.model_copy(
        update={"admitted_fields": {**material.admitted_fields, "business_effects": effects}}
    )
    hypothesis, _ = diagnose_retryable_message(tuple(evidence), trace_id=report["trace_id"])
    assert hypothesis.hypothesis_type.value != "ALREADY_POSTED"


def test_case_thirteen_reaches_invoice_gate_and_has_distinct_denial_from_case_fifteen(
    tmp_path: Path,
) -> None:
    runner = GoldenRunner(ROOT, tmp_path / "artifacts")
    case_thirteen = runner.load_manifest(
        ROOT / "golden/cases/13-operator-requests-invoice-release.json"
    )
    case_fifteen = runner.load_manifest(
        ROOT / "golden/cases/15-invoice-release-before-receipt-verified.json"
    )
    first = runner.run_case(case_thirteen, tmp_path / "case-thirteen")
    second = runner.run_case(case_fifteen, tmp_path / "case-fifteen")

    assert first["stored_projection"]["status"] == "AWAITING_INVOICE_APPROVAL"
    assert first["actual_reason_codes"] == [
        "ALL_CHECKS_PASSED",
        "RETRYABLE_MESSAGE",
        "ROLE_NOT_AUTHORIZED",
    ]
    assert second["stored_projection"]["status"] == "AWAITING_RECEIPT_APPROVAL"
    assert second["actual_reason_codes"] == ["CASE_STATUS_NOT_ELIGIBLE", "RETRYABLE_MESSAGE"]


def test_case_eight_admits_changed_authoritative_message_with_fresh_provenance(
    tmp_path: Path,
) -> None:
    runner = GoldenRunner(ROOT, tmp_path / "artifacts")
    manifest = runner.load_manifest(ROOT / "golden/cases/08-old-case-version.json")
    report = runner.run_case(manifest, tmp_path / "work")
    current = next(
        item for item in report["evidence"] if item["evidence_id"].endswith("current-state-update")
    )

    assert report["workflow_notes"] == {
        "admitted_authoritative_message_revision": 4,
        "authoritative_record_changed": True,
    }
    assert current["source_type"] == "FAILED_MESSAGE_QUEUE"
    assert current["source_record_id"] == "RECEIPT-MESSAGE-020"
    assert current["admitted_fields"]["revision"] == 4
    assert current["provenance"] == {
        "collected_by": "deterministic-enterprise-reader",
        "collection_method": "fresh-read",
        "source_system": "synthetic-enterprise-sqlite",
    }


def test_expected_values_cannot_influence_production_decisions(tmp_path: Path) -> None:
    runner = GoldenRunner(ROOT, tmp_path / "artifacts")
    manifest = runner.load_manifest(ROOT / "golden/cases/01-retryable-lock-main-path.json")
    misleading = manifest.model_copy(
        update={
            "expected": manifest.expected.model_copy(
                update={"outcome": GoldenOutcome.PROTECTED, "case_status": "PROTECTED"}
            )
        }
    )

    report = runner.run_case(misleading, tmp_path / "work")

    assert report["actual_outcome"] == "CLOSED"
    assert report["stored_projection"]["status"] == "CLOSED"
    assert report["status"] == "FAIL"


def test_two_runs_are_byte_identical(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    GoldenRunner(ROOT, first).run_all()
    GoldenRunner(ROOT, second).run_all()

    first_files = sorted(path.relative_to(first) for path in first.rglob("*.json"))
    second_files = sorted(path.relative_to(second) for path in second.rglob("*.json"))
    assert first_files == second_files
    assert all((first / path).read_bytes() == (second / path).read_bytes() for path in first_files)


def test_unknown_hook_and_extra_manifest_fields_fail_closed() -> None:
    source = json.loads(
        (ROOT / "golden/cases/01-retryable-lock-main-path.json").read_text(encoding="utf-8")
    )
    source["temporal_hook"] = "ARBITRARY_PYTHON"
    source["python_callback"] = "malicious.module:run"
    with pytest.raises(ValidationError):
        GoldenManifest.model_validate(source)


def test_fixture_fields_outside_typed_schema_fail_closed() -> None:
    source = json.loads(
        (ROOT / "fixtures/scenarios/retryable-document-lock.json").read_text(encoding="utf-8")
    )
    source["raw_sql"] = "UPDATE invoices SET state = 'RELEASED'"
    with pytest.raises(ValidationError):
        ScenarioFixture.model_validate(source)


def test_fixture_path_cannot_escape_repository(tmp_path: Path) -> None:
    runner = GoldenRunner(ROOT, tmp_path)
    source = json.loads(
        (ROOT / "golden/cases/01-retryable-lock-main-path.json").read_text(encoding="utf-8")
    )
    source["fixture"] = "../../outside.json"
    manifest_path = tmp_path / "01-retryable-lock-main-path.json"
    manifest_path.write_text(json.dumps(source), encoding="utf-8")
    with pytest.raises(ValueError, match="repository-relative"):
        runner.load_manifest(manifest_path)


def test_unknown_invariant_name_fails_closed() -> None:
    with pytest.raises(ValueError, match="unknown invariant"):
        evaluate_invariants({}, ("not_a_real_invariant",))


def test_unauthorized_effect_injection_is_detected(tmp_path: Path) -> None:
    runner = GoldenRunner(ROOT, tmp_path / "artifacts")
    manifest = runner.load_manifest(ROOT / "golden/cases/04-genuine-short-shipment.json")
    report = runner.run_case(manifest, tmp_path / "work")
    corrupted = copy.deepcopy(report)
    corrupted["effect_delta"].append(
        {
            "effect_id": "false-effect",
            "case_id": report["case_id"],
            "trace_id": report["trace_id"],
            "execution_id": "unauthorized-execution",
            "idempotency_key": "unauthorized-effect",
            "effect_type": "RECEIPT_RESTART",
            "source_record_id": "RECEIPT-MESSAGE-020",
            "result_record_ids": ["false-document"],
            "committed_at": "2026-08-25T17:00:00Z",
        }
    )

    results = evaluate_invariants(corrupted, ())

    unauthorized = next(item for item in results if item.name == "no_unauthorized_business_effects")
    assert unauthorized.passed is False


def test_local_receipt_effect_requires_exact_document_and_executed_receipt(
    tmp_path: Path,
) -> None:
    runner = GoldenRunner(ROOT, tmp_path / "artifacts")
    manifest = runner.load_manifest(ROOT / "golden/cases/01-retryable-lock-main-path.json")
    report = runner.run_case(manifest, tmp_path / "work")

    corrupted = copy.deepcopy(report)
    receipt_effect = next(
        effect
        for effect in corrupted["final_authoritative_state"]["business_effects"]
        if effect["effect_type"] == "RECEIPT_RESTART"
    )
    receipt_effect["result_record_ids"] = []
    result = next(
        item
        for item in evaluate_invariants(corrupted, ())
        if item.name == "local_effects_link_to_attempts_authorizations_and_receipts"
    )
    assert result.passed is False

    corrupted = copy.deepcopy(report)
    receipt = next(
        receipt
        for receipt in corrupted["receipts"]
        if receipt["execution_id"] == "case-01-receipt-execution"
    )
    receipt["operation_result"] = "SAFE_NOOP"
    result = next(
        item
        for item in evaluate_invariants(corrupted, ())
        if item.name == "local_effects_link_to_attempts_authorizations_and_receipts"
    )
    assert result.passed is False


def test_local_invoice_effect_requires_exact_invoice_result(tmp_path: Path) -> None:
    runner = GoldenRunner(ROOT, tmp_path / "artifacts")
    manifest = runner.load_manifest(ROOT / "golden/cases/01-retryable-lock-main-path.json")
    report = runner.run_case(manifest, tmp_path / "work")
    corrupted = copy.deepcopy(report)
    invoice_effect = next(
        effect
        for effect in corrupted["final_authoritative_state"]["business_effects"]
        if effect["effect_type"] == "INVOICE_RELEASE"
    )
    invoice_effect["result_record_ids"] = []

    result = next(
        item
        for item in evaluate_invariants(corrupted, ())
        if item.name == "local_effects_link_to_attempts_authorizations_and_receipts"
    )
    assert result.passed is False


@pytest.mark.parametrize(
    "case_key",
    [
        "02-receipt-already-posted",
        "03-receipt-posted-after-approval",
        "04-genuine-short-shipment",
        "05-missing-material-document-evidence",
        "06-expired-grant",
        "07-replayed-authorization",
        "08-old-case-version",
        "09-tampered-parameters",
        "10-duplicate-executor-request",
        "11-evaluator-rejects-synthesis",
        "12-receipt-postcondition-fails",
        "13-operator-requests-invoice-release",
        "14-ap-requests-receipt-restart",
        "15-invoice-release-before-receipt-verified",
        "16-crash-recovery",
    ],
)
def test_every_safety_case_detects_a_forbidden_persisted_effect(
    tmp_path: Path, case_key: str
) -> None:
    runner = GoldenRunner(ROOT, tmp_path / "artifacts")
    manifest = runner.load_manifest(ROOT / "golden/cases" / f"{case_key}.json")
    work = tmp_path / case_key
    report = runner.run_case(manifest, work)
    effect_type = "INVOICE_RELEASE" if case_key.startswith("12-") else "RECEIPT_RESTART"
    execution_id = f"forbidden-{case_key}"
    with sqlite3.connect(work / "enterprise.sqlite") as connection:
        connection.execute(
            "INSERT INTO business_effects VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                f"effect-{execution_id}",
                report["case_id"],
                report["trace_id"],
                execution_id,
                f"idempotency-{execution_id}",
                effect_type,
                "FORBIDDEN-SOURCE",
                json.dumps(["FORBIDDEN-RESULT"]),
                "2026-08-25T17:30:00+00:00",
            ),
        )
    injected = SyntheticEnterprise(work / "enterprise.sqlite").read_snapshot().business_effects[-1]
    corrupted = copy.deepcopy(report)
    corrupted["final_authoritative_state"]["business_effects"].append(
        injected.model_dump(mode="json")
    )
    corrupted["effect_delta"].append(injected.model_dump(mode="json"))

    results = evaluate_invariants(corrupted, ())

    unauthorized = next(item for item in results if item.name == "no_unauthorized_business_effects")
    assert unauthorized.passed is False


def test_every_universal_invariant_rejects_corrupted_evidence(tmp_path: Path) -> None:
    runner = GoldenRunner(ROOT, tmp_path / "artifacts")
    main_manifest = runner.load_manifest(ROOT / "golden/cases/01-retryable-lock-main-path.json")
    drift_manifest = runner.load_manifest(
        ROOT / "golden/cases/03-receipt-posted-after-approval.json"
    )
    main = runner.run_case(main_manifest, tmp_path / "main")
    drift = runner.run_case(drift_manifest, tmp_path / "drift")

    def rejects(report: dict[str, Any], name: str) -> None:
        result = next(item for item in evaluate_invariants(report, ()) if item.name == name)
        assert result.passed is False, name

    corrupted = copy.deepcopy(main)
    corrupted["recomputed_manifest_digest"] = "0" * 64
    rejects(corrupted, "manifest_digest_matches")

    corrupted = copy.deepcopy(main)
    corrupted["fixture_loaded"] = False
    rejects(corrupted, "fixture_was_loaded")

    corrupted = copy.deepcopy(main)
    corrupted["sqlite_proof"]["case_database_created"] = False
    rejects(corrupted, "real_sqlite_databases_exist")

    corrupted = copy.deepcopy(main)
    corrupted["evidence"][0]["trace_id"] = "wrong-trace"
    rejects(corrupted, "case_and_trace_identity_consistent")

    corrupted = copy.deepcopy(main)
    corrupted["replay"]["verified"] = False
    rejects(corrupted, "audit_chain_replays")

    corrupted = copy.deepcopy(main)
    corrupted["replayed_projection"]["status"] = "PROTECTED"
    rejects(corrupted, "projection_matches_replay")

    corrupted = copy.deepcopy(main)
    corrupted["attempts"] = []
    rejects(corrupted, "local_effects_link_to_attempts_authorizations_and_receipts")

    corrupted = copy.deepcopy(drift)
    external = next(
        item
        for item in corrupted["final_authoritative_state"]["business_effects"]
        if item["effect_type"] == "EXTERNAL_RECEIPT"
    )
    external["result_record_ids"] = ["wrong-document"]
    rejects(corrupted, "external_effects_link_to_authoritative_source_history")

    corrupted = copy.deepcopy(drift)
    corrupted["final_authoritative_state"]["business_effects"] = [
        item
        for item in corrupted["final_authoritative_state"]["business_effects"]
        if item["effect_type"] != "EXTERNAL_RECEIPT"
    ]
    rejects(corrupted, "safe_noop_receipts_link_local_attempt_to_external_effect")

    corrupted = copy.deepcopy(drift)
    external = next(
        item
        for item in corrupted["final_authoritative_state"]["business_effects"]
        if item["effect_type"] == "EXTERNAL_RECEIPT"
    )
    external["trace_id"] = "tampered-trace"
    rejects(corrupted, "safe_noop_receipts_link_local_attempt_to_external_effect")

    corrupted = copy.deepcopy(main)
    corrupted["sqlite_proof"]["reopened_before_final_read"] = False
    rejects(corrupted, "authoritative_snapshot_matches_report")

    corrupted = copy.deepcopy(main)
    corrupted["effect_delta"].append(
        {
            "effect_id": "unauthorized-effect",
            "case_id": main["case_id"],
            "trace_id": main["trace_id"],
            "execution_id": "unauthorized-execution",
            "idempotency_key": "unauthorized-idempotency",
            "effect_type": "INVOICE_RELEASE",
            "source_record_id": "INV-10001",
            "result_record_ids": ["INV-10001"],
            "committed_at": "2026-08-25T17:30:00Z",
        }
    )
    rejects(corrupted, "no_unauthorized_business_effects")


def test_golden_runner_has_no_cloud_model_or_network_client_imports() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "src/the_missing_20/evaluation").glob("*.py")
    )
    for forbidden in ("boto3", "botocore", "requests", "httpx", "openai", "bedrock"):
        assert f"import {forbidden}" not in source
        assert f"from {forbidden}" not in source


def test_failed_case_still_writes_complete_aggregate_report(tmp_path: Path) -> None:
    class MisleadingExpectationRunner(GoldenRunner):
        def load_manifest(self, path: Path) -> GoldenManifest:
            manifest = super().load_manifest(path)
            if manifest.case_key == "01-retryable-lock-main-path":
                return manifest.model_copy(
                    update={
                        "expected": manifest.expected.model_copy(
                            update={
                                "outcome": GoldenOutcome.PROTECTED,
                                "case_status": "PROTECTED",
                            }
                        )
                    }
                )
            return manifest

    result = MisleadingExpectationRunner(ROOT, tmp_path / "artifacts").run_all()

    assert result["status"] == "FAIL"
    assert result["case_count"] == 16
    assert result["failed_case_count"] == 1
    aggregate = json.loads((tmp_path / "artifacts/golden-v1.json").read_text(encoding="utf-8"))
    assert aggregate == result
    assert len(aggregate["cases"]) == 16
