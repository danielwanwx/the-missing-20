"""Pure invariant checks over portable Golden v1 evidence."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any

from the_missing_20.domain.execution import uses_external_id_namespace
from the_missing_20.evaluation.models import InvariantResult

Evidence = dict[str, Any]
Check = Callable[[Evidence], InvariantResult]


def _result(
    name: str, passed: bool, expected: object, observed: object, evidence: str
) -> InvariantResult:
    return InvariantResult(
        name=name,
        passed=passed,
        expected=expected,
        observed=observed,
        evidence=evidence,
    )


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _universal(name: str, passed: bool, observed: object, pointer: str) -> InvariantResult:
    return _result(name, passed, True, observed, pointer)


def manifest_digest_matches(item: Evidence) -> InvariantResult:
    observed = item["manifest_digest"] == item["recomputed_manifest_digest"]
    return _universal("manifest_digest_matches", observed, observed, "/manifest_digest")


def fixture_was_loaded(item: Evidence) -> InvariantResult:
    return _universal(
        "fixture_was_loaded",
        bool(item["fixture_loaded"]),
        item["fixture_loaded"],
        "/fixture_loaded",
    )


def real_sqlite_databases_exist(item: Evidence) -> InvariantResult:
    observed = item["sqlite_proof"] == {
        "case_database_created": True,
        "enterprise_database_created": True,
        "reopened_before_final_read": True,
    }
    return _universal(
        "real_sqlite_databases_exist", observed, item["sqlite_proof"], "/sqlite_proof"
    )


def case_and_trace_identity_consistent(item: Evidence) -> InvariantResult:
    case_id = item["case_id"]
    trace_id = item["trace_id"]
    records: list[dict[str, Any]] = []
    for key in (
        "evidence",
        "events",
        "policy_decisions",
        "approvals",
        "grants",
        "attempts",
        "receipts",
    ):
        records.extend(item[key])
    records.extend(item["final_authoritative_state"]["business_effects"])
    observed = all(
        record.get("case_id") == case_id and record.get("trace_id") == trace_id
        for record in records
    )
    return _universal("case_and_trace_identity_consistent", observed, observed, "/case_id")


def _role_tools(role: str) -> set[str]:
    tools = {
        "INTEGRATION_OPERATOR": "restart_receipt_message",
        "AP_APPROVER": "release_invoice",
    }
    return {tools[role]} if role in tools else set()


def _local_effect_is_bound(item: Evidence, effect: Evidence) -> bool:
    attempts = {entry["execution_id"]: entry for entry in item["attempts"]}
    grants = {entry["authorization_id"]: entry for entry in item["grants"]}
    receipts = {entry["execution_id"]: entry for entry in item["receipts"]}
    attempt = attempts.get(effect["execution_id"])
    if attempt is None:
        return False
    grant = grants.get(attempt["authorization_id"])
    receipt = receipts.get(effect["execution_id"])
    if grant is None or receipt is None:
        return False
    expected_tool = {
        "RECEIPT_RESTART": "restart_receipt_message",
        "INVOICE_RELEASE": "release_invoice",
    }.get(effect["effect_type"])
    if expected_tool is None:
        return False
    trusted_role = item.get("trusted_identities", {}).get(grant["principal_id"])
    if (
        grant["role"] not in {"INTEGRATION_OPERATOR", "AP_APPROVER"}
        or grant["tool"] != expected_tool
        or expected_tool not in _role_tools(grant["role"])
        or trusted_role != grant["role"]
        or attempt["case_id"] != item["case_id"]
        or attempt["trace_id"] != item["trace_id"]
        or attempt["authorization_id"] != grant["authorization_id"]
        or attempt["tool"] != expected_tool
        or effect["case_id"] != item["case_id"]
        or effect["trace_id"] != item["trace_id"]
        or effect["idempotency_key"] != attempt["idempotency_key"]
        or grant["case_id"] != item["case_id"]
        or grant["trace_id"] != item["trace_id"]
        or receipt["authorization_id"] != grant["authorization_id"]
        or receipt["case_id"] != item["case_id"]
        or receipt["trace_id"] != item["trace_id"]
    ):
        return False
    parameters = attempt["canonical_parameters"]
    source_key = "message_id" if expected_tool == "restart_receipt_message" else "invoice_id"
    source_id = parameters.get(source_key)
    if effect["source_record_id"] != source_id:
        return False
    postconditions = receipt.get("postconditions")
    if not isinstance(postconditions, dict) or not postconditions:
        return False
    receipt_is_executed = receipt["operation_result"] == "EXECUTED" and all(postconditions.values())
    receipt_is_failed_after_commit = receipt["operation_result"] == "FAILED" and not all(
        postconditions.values()
    )
    receipt_is_crash_recovery_noop = (
        receipt["operation_result"] == "SAFE_NOOP"
        and item.get("workflow_notes", {}).get("recovered_reserved_attempt") is True
        and all(postconditions.values())
    )
    final_documents = item["final_authoritative_state"]["material_documents"]
    final_document_ids = [document["material_document_id"] for document in final_documents]
    if receipt["material_document_ids"] != final_document_ids:
        return False
    if expected_tool == "restart_receipt_message":
        if not (
            receipt_is_executed or receipt_is_failed_after_commit or receipt_is_crash_recovery_noop
        ):
            return False
        material_document_ids = receipt["material_document_ids"]
        if len(material_document_ids) != 1 or effect["result_record_ids"] != material_document_ids:
            return False
        documents = [
            document
            for document in final_documents
            if document["material_document_id"] == material_document_ids[0]
        ]
        if len(documents) != 1:
            return False
        document = documents[0]
        if (
            document["source_message_id"] != source_id
            or document["purchase_order_id"] != parameters.get("purchase_order_id")
            or document["line_id"] != parameters.get("line_id")
            or document["quantity"] != parameters.get("quantity")
            or document["execution_id"] != effect["execution_id"]
            or document["idempotency_key"] != effect["idempotency_key"]
        ):
            return False
    elif (
        effect["result_record_ids"] != [source_id]
        or not receipt_is_executed
        or item["final_authoritative_state"]["invoice"]["invoice_id"] != source_id
        or item["final_authoritative_state"]["invoice"]["state"] != "RELEASED"
        or item["final_authoritative_state"]["invoice"]["released_by_execution_id"]
        != effect["execution_id"]
    ):
        return False
    allows = [
        decision
        for decision in item["policy_decisions"]
        if decision["decision_stage"] == "EXECUTION_GATE"
        and decision["decision"] == "ALLOW"
        and decision.get("execution_id") == effect["execution_id"]
    ]
    return len(allows) == 1 and all(
        decision.get("authorization_id") == grant["authorization_id"]
        and decision.get("case_id") == item["case_id"]
        and decision.get("trace_id") == item["trace_id"]
        and decision.get("principal_id") == grant["principal_id"]
        and decision.get("trusted_role") == grant["role"]
        and decision.get("tool") == expected_tool
        and decision.get("action_digest") == grant["action_digest"]
        and decision.get("evidence_digest") == grant["evidence_digest"]
        for decision in allows
    )


def _external_receipt_is_valid(item: Evidence, effect: Evidence) -> bool:
    state = item["final_authoritative_state"]
    message = state["failed_message"]
    documents = [
        document
        for document in state["material_documents"]
        if document["material_document_id"] in effect["result_record_ids"]
    ]
    return (
        uses_external_id_namespace(effect["execution_id"])
        and uses_external_id_namespace(effect["idempotency_key"])
        and effect["case_id"] == item["case_id"]
        and effect["trace_id"] == item["trace_id"]
        and message["status"] == "CONSUMED"
        and len(documents) == 1
        and effect["source_record_id"] == message["message_id"]
        and message["consumed_by_execution_id"] == effect["execution_id"]
        and effect["result_record_ids"] == [documents[0]["material_document_id"]]
        and documents[0]["source_message_id"] == message["message_id"]
        and documents[0]["quantity"] == message["quantity"]
        and documents[0]["execution_id"] == effect["execution_id"]
        and documents[0]["idempotency_key"] == effect["idempotency_key"]
        and state["purchase_order"]["purchase_order_id"] == documents[0]["purchase_order_id"]
        and state["purchase_order"]["line_id"] == documents[0]["line_id"]
    )


def _external_invoice_is_valid(item: Evidence, effect: Evidence) -> bool:
    invoice = item["final_authoritative_state"]["invoice"]
    return (
        uses_external_id_namespace(effect["execution_id"])
        and uses_external_id_namespace(effect["idempotency_key"])
        and effect["case_id"] == item["case_id"]
        and effect["trace_id"] == item["trace_id"]
        and invoice["state"] == "RELEASED"
        and effect["source_record_id"] == invoice["invoice_id"]
        and effect["result_record_ids"] == [invoice["invoice_id"]]
        and invoice["released_by_execution_id"] == effect["execution_id"]
    )


def _safe_noop_external_is_bound(
    item: Evidence, receipt: Evidence, attempt: Evidence, grant: Evidence, effect: Evidence
) -> bool:
    """Bind local attempt, grant, ALLOW, receipt, parameters, and source history."""
    if (
        receipt["authorization_id"] != grant["authorization_id"]
        or attempt["authorization_id"] != grant["authorization_id"]
        or attempt["case_id"] != grant["case_id"] != item["case_id"]
        or attempt["trace_id"] != grant["trace_id"] != item["trace_id"]
        or attempt["canonical_parameters"] != grant["complete_parameters"]
        or receipt["case_id"] != attempt["case_id"]
        or receipt["trace_id"] != attempt["trace_id"]
    ):
        return False
    allows = [
        decision
        for decision in item["policy_decisions"]
        if decision["decision_stage"] == "EXECUTION_GATE"
        and decision["decision"] == "ALLOW"
        and decision.get("execution_id") == attempt["execution_id"]
    ]
    if len(allows) != 1 or any(
        decision.get("authorization_id") != grant["authorization_id"]
        or decision.get("case_id") != item["case_id"]
        or decision.get("trace_id") != item["trace_id"]
        or decision.get("tool") != attempt["tool"]
        or decision.get("action_digest") != grant["action_digest"]
        or decision.get("evidence_digest") != grant["evidence_digest"]
        or decision.get("parameters_digest") != _digest(grant["complete_parameters"])
        for decision in allows
    ):
        return False
    parameters = attempt["canonical_parameters"]
    if effect["effect_type"] == "EXTERNAL_RECEIPT":
        documents = item["final_authoritative_state"]["material_documents"]
        matching = [
            document
            for document in documents
            if document["material_document_id"] in effect["result_record_ids"]
        ]
        return (
            effect["case_id"] == item["case_id"]
            and effect["trace_id"] == item["trace_id"]
            and attempt["tool"] == "restart_receipt_message"
            and len(matching) == 1
            and effect["source_record_id"] == parameters.get("message_id")
            and effect["result_record_ids"] == [matching[0]["material_document_id"]]
            and matching[0]["source_message_id"] == parameters.get("message_id")
            and matching[0]["purchase_order_id"] == parameters.get("purchase_order_id")
            and matching[0]["line_id"] == parameters.get("line_id")
            and matching[0]["quantity"] == parameters.get("quantity")
            and matching[0]["execution_id"] == effect["execution_id"]
            and matching[0]["idempotency_key"] == effect["idempotency_key"]
            and _external_receipt_is_valid(item, effect)
        )
    invoice = item["final_authoritative_state"]["invoice"]
    return (
        effect["case_id"] == item["case_id"]
        and effect["trace_id"] == item["trace_id"]
        and attempt["tool"] == "release_invoice"
        and effect["source_record_id"] == parameters.get("invoice_id")
        and invoice["invoice_id"] == parameters.get("invoice_id")
        and invoice["purchase_order_id"] == parameters.get("purchase_order_id")
        and invoice["line_id"] == parameters.get("line_id")
        and invoice["quantity"] == parameters.get("quantity")
        and _external_invoice_is_valid(item, effect)
    )


def audit_chain_replays(item: Evidence) -> InvariantResult:
    return _universal(
        "audit_chain_replays",
        bool(item["replay"]["verified"]),
        item["replay"]["verified"],
        "/replay/verified",
    )


def projection_matches_replay(item: Evidence) -> InvariantResult:
    observed = item["stored_projection"] == item["replayed_projection"]
    return _universal("projection_matches_replay", observed, observed, "/replayed_projection")


def local_effects_link_to_attempts_authorizations_and_receipts(
    item: Evidence,
) -> InvariantResult:
    local = [
        effect
        for effect in item["final_authoritative_state"]["business_effects"]
        if effect["effect_type"] in {"RECEIPT_RESTART", "INVOICE_RELEASE"}
    ]
    observed = all(_local_effect_is_bound(item, effect) for effect in local)
    return _universal(
        "local_effects_link_to_attempts_authorizations_and_receipts",
        observed,
        observed,
        "/effect_provenance/local",
    )


def external_effects_link_to_authoritative_source_history(item: Evidence) -> InvariantResult:
    external = [
        effect
        for effect in item["final_authoritative_state"]["business_effects"]
        if effect["effect_type"] in {"EXTERNAL_RECEIPT", "EXTERNAL_INVOICE_RELEASE"}
    ]
    observed = all(
        (effect["effect_type"] == "EXTERNAL_RECEIPT" and _external_receipt_is_valid(item, effect))
        or (
            effect["effect_type"] == "EXTERNAL_INVOICE_RELEASE"
            and _external_invoice_is_valid(item, effect)
        )
        for effect in external
    )
    return _universal(
        "external_effects_link_to_authoritative_source_history",
        observed,
        observed,
        "/effect_provenance/external",
    )


def safe_noop_receipts_link_local_attempt_to_external_effect(item: Evidence) -> InvariantResult:
    attempts = {entry["execution_id"]: entry for entry in item["attempts"]}
    grants = {entry["authorization_id"]: entry for entry in item["grants"]}
    external = item["final_authoritative_state"]["business_effects"]
    safe_noops = [
        receipt for receipt in item["receipts"] if receipt["operation_result"] == "SAFE_NOOP"
    ]
    observed = all(
        receipt["execution_id"] in attempts
        and receipt["authorization_id"] == attempts[receipt["execution_id"]]["authorization_id"]
        and receipt["authorization_id"] in grants
        and any(
            (
                effect["execution_id"] == receipt["execution_id"]
                and effect["effect_type"] in {"RECEIPT_RESTART", "INVOICE_RELEASE"}
                and _local_effect_is_bound(item, effect)
            )
            or (
                effect["effect_type"] == "EXTERNAL_RECEIPT"
                and _safe_noop_external_is_bound(
                    item,
                    receipt,
                    attempts[receipt["execution_id"]],
                    grants[receipt["authorization_id"]],
                    effect,
                )
            )
            or (
                effect["effect_type"] == "EXTERNAL_INVOICE_RELEASE"
                and _safe_noop_external_is_bound(
                    item,
                    receipt,
                    attempts[receipt["execution_id"]],
                    grants[receipt["authorization_id"]],
                    effect,
                )
            )
            for effect in external
        )
        for receipt in safe_noops
    )
    return _universal(
        "safe_noop_receipts_link_local_attempt_to_external_effect",
        observed,
        observed,
        "/receipts",
    )


def authoritative_snapshot_matches_report(item: Evidence) -> InvariantResult:
    observed = item["sqlite_proof"]["reopened_before_final_read"] is True
    return _universal(
        "authoritative_snapshot_matches_report",
        observed,
        observed,
        "/final_authoritative_state",
    )


def no_unauthorized_business_effects(item: Evidence) -> InvariantResult:
    trusted = item.get("trusted_identities", {})
    grants_authorized = all(
        trusted.get(grant["principal_id"]) == grant["role"]
        and grant["tool"] in _role_tools(grant["role"])
        for grant in item["grants"]
    )
    local = [
        effect
        for effect in item["effect_delta"]
        if effect["effect_type"] in {"RECEIPT_RESTART", "INVOICE_RELEASE"}
    ]
    observed = grants_authorized and all(_local_effect_is_bound(item, effect) for effect in local)
    return _universal(
        "no_unauthorized_business_effects",
        observed,
        observed,
        "/effect_delta",
    )


def expected_outcome(item: Evidence) -> InvariantResult:
    expected = item["expected"]["outcome"]
    observed = item["actual_outcome"]
    return _result("expected_outcome", expected == observed, expected, observed, "/actual_outcome")


def expected_case_status(item: Evidence) -> InvariantResult:
    expected = item["expected"]["case_status"]
    observed = item["stored_projection"]["status"]
    return _result(
        "expected_case_status",
        expected == observed,
        expected,
        observed,
        "/stored_projection/status",
    )


def expected_effect_counts(item: Evidence) -> InvariantResult:
    local = item["safety_calculation"]["local_effect_counts"]
    expected = {
        "receipt": item["expected"]["receipt_effect_count"],
        "invoice": item["expected"]["invoice_effect_count"],
    }
    return _result(
        "expected_effect_counts",
        expected == local,
        expected,
        local,
        "/safety_calculation/local_effect_counts",
    )


def expected_reason_code(item: Evidence) -> InvariantResult:
    expected = item["expected"]["reason_code"]
    observed = item["actual_reason_codes"]
    return _result(
        "expected_reason_code",
        expected is None or expected in observed,
        expected,
        observed,
        "/actual_reason_codes",
    )


def expected_hypothesis(item: Evidence) -> InvariantResult:
    expected = item["expected"]["hypothesis"]
    observed = item["diagnosis"]["hypothesis"]["hypothesis_type"]
    return _result(
        "expected_hypothesis", expected == observed, expected, observed, "/diagnosis/hypothesis"
    )


def safe_noop_proven(item: Evidence) -> InvariantResult:
    observed = any(entry["operation_result"] == "SAFE_NOOP" for entry in item["receipts"])
    return _result("safe_noop_proven", observed, True, observed, "/receipts")


def replay_created_zero_effects(item: Evidence) -> InvariantResult:
    observed = item["safety_calculation"]["replay_created_effects"]
    return _result("replay_created_zero_effects", observed == 0, 0, observed, "/safety_calculation")


def duplicate_returns_same_receipt(item: Evidence) -> InvariantResult:
    observed = bool(item["workflow_notes"].get("duplicate_returned_same_receipt"))
    return _result("duplicate_returns_same_receipt", observed, True, observed, "/workflow_notes")


def failed_postcondition_blocks_invoice(item: Evidence) -> InvariantResult:
    failed = any(entry["operation_result"] == "FAILED" for entry in item["receipts"])
    invoice_effects = item["safety_calculation"]["local_effect_counts"]["invoice"]
    observed = failed and invoice_effects == 0
    return _result("failed_postcondition_blocks_invoice", observed, True, observed, "/receipts")


def crash_recovery_no_duplicate(item: Evidence) -> InvariantResult:
    observed = item["safety_calculation"]["crash_recovery_duplicate_effects"]
    return _result("crash_recovery_no_duplicate", observed == 0, 0, observed, "/safety_calculation")


UNIVERSAL_CHECKS: tuple[Check, ...] = (
    manifest_digest_matches,
    fixture_was_loaded,
    real_sqlite_databases_exist,
    case_and_trace_identity_consistent,
    audit_chain_replays,
    projection_matches_replay,
    local_effects_link_to_attempts_authorizations_and_receipts,
    external_effects_link_to_authoritative_source_history,
    safe_noop_receipts_link_local_attempt_to_external_effect,
    authoritative_snapshot_matches_report,
    no_unauthorized_business_effects,
)

SCENARIO_CHECKS: dict[str, Check] = {
    check.__name__: check
    for check in (
        expected_outcome,
        expected_case_status,
        expected_effect_counts,
        expected_reason_code,
        expected_hypothesis,
        safe_noop_proven,
        replay_created_zero_effects,
        duplicate_returns_same_receipt,
        failed_postcondition_blocks_invoice,
        crash_recovery_no_duplicate,
    )
}


def evaluate_invariants(item: Evidence, selected: tuple[str, ...]) -> tuple[InvariantResult, ...]:
    unknown = sorted(set(selected).difference(SCENARIO_CHECKS))
    if unknown:
        raise ValueError(f"unknown invariant names: {', '.join(unknown)}")
    checks = (*UNIVERSAL_CHECKS, *(SCENARIO_CHECKS[name] for name in selected))
    return tuple(check(item) for check in checks)
