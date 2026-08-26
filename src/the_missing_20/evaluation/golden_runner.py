"""Execute Golden v1 through fresh SQLite stores and production application services."""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from pydantic import JsonValue

from the_missing_20.adapters.clocks import ManualClock
from the_missing_20.adapters.local_signer import LocalSigner
from the_missing_20.adapters.sqlite_case_store import SQLiteCaseStore
from the_missing_20.adapters.synthetic_enterprise import SyntheticEnterprise
from the_missing_20.application.authorization_service import (
    AuthorizationService,
    LocalPolicy,
    TrustedIdentities,
)
from the_missing_20.application.case_service import CaseService
from the_missing_20.application.detector import DiscrepancyDetector
from the_missing_20.application.diagnosis import diagnose_retryable_message
from the_missing_20.application.executor import ControlledExecutor, SimulatedPersistenceFault
from the_missing_20.domain.errors import AuthorizationDenied
from the_missing_20.domain.execution import (
    ReleaseInvoiceParameters,
    RestartReceiptMessageParameters,
)
from the_missing_20.domain.models import (
    ActionTool,
    EvaluationDecision,
    EvidenceItem,
    EvidenceProvenance,
    EvidenceSourceType,
    HumanRole,
    HypothesisResult,
    InvestigationAssessment,
    InvestigationDecision,
)
from the_missing_20.evaluation.invariants import evaluate_invariants
from the_missing_20.evaluation.models import (
    AuthorizationReuse,
    GoldenManifest,
    GoldenOutcome,
    InvoiceRequestStage,
    TamperTarget,
    TemporalHook,
)

BASE_TIME = datetime(2026, 8, 25, 17, 0, tzinfo=UTC)
RUNNER_VERSION = "golden-runner/v1"


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def crash_recovery_duplicate_count(
    effects: tuple[Any, ...], documents: tuple[Any, ...], *, execution_id: str, source_id: str
) -> int:
    """Count duplicate ledger rows by reserved execution or reserved source."""
    # A recovery duplicate is identified by either side of the reserved identity.  Grouping
    # only by source misses two effects with the same execution and different sources; grouping
    # only by execution misses the converse.  Filter each record once with OR, so a record that
    # matches both identities is not counted twice.
    matching_effects = tuple(
        effect
        for effect in effects
        if effect.effect_type.value == "RECEIPT_RESTART"
        and (effect.execution_id == execution_id or effect.source_record_id == source_id)
    )
    matching_documents = tuple(
        document
        for document in documents
        if document.execution_id == execution_id or document.source_message_id == source_id
    )
    return sum(max(0, len(records) - 1) for records in (matching_effects, matching_documents))


def _local_effect_identity(effect: Any) -> dict[str, str]:
    """Return the complete identity used to authorize one local business effect."""
    return {
        "effect_type": effect.effect_type.value,
        "execution_id": effect.execution_id,
        "idempotency_key": effect.idempotency_key,
        "source_record_id": effect.source_record_id,
    }


def _allowed_local_effect_identities(
    manifest: GoldenManifest, baseline: Any
) -> dict[str, list[dict[str, str]]]:
    """Build the exact local effect identities permitted by the typed case contract.

    The expected local-effect count is the per-case contract for what this run may create.
    A count of zero permits no local identity, even when an authorization was issued for a
    safe-noop path.  A count of one permits the request's exact execution and idempotency
    identities plus the typed source record selected by the corresponding public action
    parameters.  This keeps the safety counter independent from an action-eligibility
    boolean alone.
    """
    allowed: dict[str, list[dict[str, str]]] = {"receipt": [], "invoice": []}
    if manifest.expected.receipt_effect_count == 1:
        allowed["receipt"] = [
            {
                "effect_type": "RECEIPT_RESTART",
                "execution_id": manifest.request.receipt_execution_id,
                "idempotency_key": manifest.request.receipt_idempotency_key,
                "source_record_id": baseline.failed_message.message_id,
            },
        ]
    if manifest.expected.invoice_effect_count == 1:
        allowed["invoice"] = [
            {
                "effect_type": "INVOICE_RELEASE",
                "execution_id": manifest.request.invoice_execution_id,
                "idempotency_key": manifest.request.invoice_idempotency_key,
                "source_record_id": baseline.invoice.invoice_id,
            },
        ]
    return allowed


def _false_effect_calculation(
    effect_delta: tuple[Any, ...],
    allowed_identities: dict[str, list[dict[str, str]]],
) -> dict[str, dict[str, Any]]:
    """Classify every local delta effect against its exact allowed identity."""
    calculations: dict[str, dict[str, Any]] = {}
    for label, effect_type in (
        ("receipt", "RECEIPT_RESTART"),
        ("invoice", "INVOICE_RELEASE"),
    ):
        observed = [
            _local_effect_identity(effect)
            for effect in effect_delta
            if effect.effect_type.value == effect_type
        ]
        allowed = list(allowed_identities[label])
        outside_allowed = [identity for identity in observed if identity not in allowed]
        calculations[label] = {
            "allowed_identities": allowed,
            "observed_identities": observed,
            "outside_allowed_identities": outside_allowed,
            "false_count": len(outside_allowed),
        }
    return calculations


def _json(value: object) -> dict[str, Any]:
    return json.loads(value.model_dump_json())  # type: ignore[attr-defined,no-any-return]


def _atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


class GoldenRunner:
    def __init__(self, repository_root: Path, artifact_root: Path) -> None:
        self.repository_root = repository_root.resolve()
        self.artifact_root = artifact_root

    def discover(self) -> tuple[Path, ...]:
        return tuple(sorted((self.repository_root / "golden/cases").glob("*.json")))

    def load_manifest(self, path: Path) -> GoldenManifest:
        manifest = GoldenManifest.model_validate_json(path.read_text(encoding="utf-8"))
        if path.stem != manifest.case_key:
            raise ValueError("manifest filename must equal case_key")
        fixture = (self.repository_root / manifest.fixture).resolve()
        if not fixture.is_relative_to(self.repository_root) or not fixture.is_file():
            raise ValueError("fixture must be an existing repository-relative file")
        return manifest

    def run_all(self) -> dict[str, Any]:
        paths = self.discover()
        if len(paths) != 16:
            raise ValueError(f"Golden v1 requires exactly 16 cases; discovered {len(paths)}")
        case_reports: list[dict[str, Any]] = []
        for path in paths:
            manifest = self.load_manifest(path)
            with tempfile.TemporaryDirectory(prefix=f"golden-{manifest.case_key}-") as raw:
                report = self.run_case(manifest, Path(raw))
            _atomic_json(self.artifact_root / "cases" / path.name, report)
            case_reports.append(report)
        counters = {
            key: sum(report["safety_calculation"][key] for report in case_reports)
            for key in (
                "false_receipt_restarts",
                "false_invoice_releases",
                "cross_role_grants",
                "replay_created_effects",
                "crash_recovery_duplicate_effects",
            )
        }
        failed_invariants = sum(
            not invariant["passed"] for report in case_reports for invariant in report["invariants"]
        )
        passed_cases = sum(report["status"] == "PASS" for report in case_reports)
        result = {
            "schema_version": "golden-suite/v1",
            "runner_version": RUNNER_VERSION,
            "suite_id": _digest(
                [
                    (report["case_key"], report["manifest_digest"], report["fixture_digest"])
                    for report in case_reports
                ]
            ),
            "source_revision": self._source_revision(),
            "status": (
                "PASS"
                if passed_cases == 16
                and failed_invariants == 0
                and all(v == 0 for v in counters.values())
                else "FAIL"
            ),
            "case_count": 16,
            "passed_case_count": passed_cases,
            "failed_case_count": 16 - passed_cases,
            "failed_invariant_count": failed_invariants,
            "safety_counters": counters,
            "cases": [
                {
                    "case_key": report["case_key"],
                    "status": report["status"],
                    "actual_outcome": report["actual_outcome"],
                    "actual_case_status": report["stored_projection"]["status"],
                    "manifest_digest": report["manifest_digest"],
                    "fixture_digest": report["fixture_digest"],
                    "artifact": f"artifacts/golden/cases/{report['case_key']}.json",
                    "evidence": {
                        "events": "/events",
                        "policy_decisions": "/policy_decisions",
                        "attempts": "/attempts",
                        "receipts": "/receipts",
                        "effects": "/final_authoritative_state/business_effects",
                        "replay": "/replay",
                    },
                }
                for report in case_reports
            ],
        }
        _atomic_json(self.artifact_root / "golden-v1.json", result)
        return result

    def run_case(self, manifest: GoldenManifest, work_directory: Path) -> dict[str, Any]:
        work_directory.mkdir(parents=True, exist_ok=True)
        fixture_path = (self.repository_root / manifest.fixture).resolve()
        normalized_manifest = manifest.model_dump(mode="json")
        manifest_digest = _digest(normalized_manifest)
        fixture_digest = _file_digest(fixture_path)
        case_id = f"case-{manifest.case_key}"
        trace_id = f"trace-{manifest.case_key}"
        enterprise_path = work_directory / "enterprise.sqlite"
        case_path = work_directory / "case.sqlite"
        enterprise = SyntheticEnterprise.seed_from_fixture(enterprise_path, fixture_path)
        baseline = enterprise.read_snapshot()
        if manifest.temporal_hook is TemporalHook.MATERIAL_DOCUMENT_SOURCE_UNAVAILABLE:
            enterprise.set_material_document_source_unavailable("SOURCE_UNAVAILABLE")
        store = SQLiteCaseStore(case_path)
        clock = ManualClock(BASE_TIME)
        signer = LocalSigner(b"golden-v1-local-key-not-for-production")
        identities = TrustedIdentities(
            {
                "operator-001": HumanRole.INTEGRATION_OPERATOR,
                "ap-approver-001": HumanRole.AP_APPROVER,
            }
        )
        services = self._services(store, enterprise, clock, signer, identities)
        detected, evidence = DiscrepancyDetector(enterprise, store, clock).detect(
            case_id=case_id,
            trace_id=trace_id,
            fixture_path=fixture_path,
        )
        hypothesis, evaluation = diagnose_retryable_message(evidence, trace_id=trace_id)
        if manifest.request.evaluator_rejects:
            evaluation = evaluation.model_copy(
                update={
                    "decision": EvaluationDecision.REJECT,
                    "failed_invariants": ("independent_evaluator_disagrees",),
                    "allowed_next_action": None,
                }
            )
        decision, reason_codes = self._assessment_decision(
            hypothesis=hypothesis,
            evaluation_decision=evaluation.decision,
            missing_sources=hypothesis.missing_evidence,
            evaluator_rejects=manifest.request.evaluator_rejects,
        )
        assessment = InvestigationAssessment(
            assessment_id=f"assessment-{manifest.case_key}",
            case_id=case_id,
            trace_id=trace_id,
            hypothesis=hypothesis,
            evaluation=evaluation,
            admitted_evidence_ids=tuple(sorted(item.evidence_id for item in evidence)),
            missing_evidence_sources=hypothesis.missing_evidence,
            decision=decision,
            reason_codes=reason_codes,
            assessed_at=clock.now(),
        )
        case, _ = services["cases"].record_investigation_outcome(
            assessment=assessment,
            expected_version=detected.case_version,
            idempotency_key=f"assessment:{manifest.case_key}",
        )
        workflow_notes: dict[str, Any] = {}
        actual_outcome = self._outcome_after_assessment(decision)
        if decision is InvestigationDecision.RECOMMEND_RECEIPT_RESTART:
            actual_outcome, workflow_notes, store, enterprise = self._run_action_workflow(
                manifest=manifest,
                case=case,
                store=store,
                enterprise=enterprise,
                clock=clock,
                signer=signer,
                identities=identities,
                baseline=baseline,
                case_id=case_id,
                trace_id=trace_id,
                case_path=case_path,
                enterprise_path=enterprise_path,
            )
        elif decision is InvestigationDecision.RECEIPT_ALREADY_POSTED:
            actual_outcome = self._finish_invoice(
                manifest, case, store, enterprise, clock, signer, identities
            )

        database_proof = {
            "enterprise_database_created": enterprise_path.is_file(),
            "case_database_created": case_path.is_file(),
            "reopened_before_final_read": False,
        }
        del store, enterprise
        store = SQLiteCaseStore(case_path)
        enterprise = SyntheticEnterprise(enterprise_path)
        database_proof["reopened_before_final_read"] = True
        final_snapshot = enterprise.read_snapshot()
        stored = store.get_case(case_id)
        replayed = store.replay_case(case_id)
        events = store.list_events(case_id)
        decisions = store.list_policy_decisions(case_id)
        approvals = store.list_approvals(case_id)
        grants = store.list_grants(case_id)
        attempts = store.list_attempts(case_id)
        receipts = store.list_receipts(case_id)
        baseline_ids = {effect.effect_id for effect in baseline.business_effects}
        effect_delta = tuple(
            effect
            for effect in final_snapshot.business_effects
            if effect.effect_id not in baseline_ids
        )
        baseline_document_ids = {
            document.material_document_id for document in baseline.material_documents
        }
        material_document_delta = tuple(
            document
            for document in final_snapshot.material_documents
            if document.material_document_id not in baseline_document_ids
        )
        local_receipt_count = sum(e.effect_type.value == "RECEIPT_RESTART" for e in effect_delta)
        local_invoice_count = sum(e.effect_type.value == "INVOICE_RELEASE" for e in effect_delta)
        allowed_local_effect_identities = _allowed_local_effect_identities(manifest, baseline)
        false_effect_calculation = _false_effect_calculation(
            effect_delta, allowed_local_effect_identities
        )
        trusted_roles = {
            "operator-001": "INTEGRATION_OPERATOR",
            "ap-approver-001": "AP_APPROVER",
        }
        authorized_tools = {
            "INTEGRATION_OPERATOR": {"restart_receipt_message"},
            "AP_APPROVER": {"release_invoice"},
        }
        cross_role = sum(
            trusted_roles.get(grant.principal_id) != grant.role.value
            or grant.tool.value not in authorized_tools.get(grant.role.value, set())
            for grant in grants
        )
        replay_execution_id = f"{manifest.request.receipt_execution_id}-replay"
        replay_effects = sum(e.execution_id == replay_execution_id for e in effect_delta)
        reserved_attempt = next(
            (
                attempt
                for attempt in attempts
                if attempt.tool is ActionTool.RESTART_RECEIPT_MESSAGE
                and attempt.execution_id == manifest.request.receipt_execution_id
            ),
            None,
        )
        reserved_execution_ids = (
            {reserved_attempt.execution_id} if reserved_attempt is not None else set()
        )
        reserved_sources = (
            {str(reserved_attempt.canonical_parameters["message_id"])}
            if reserved_attempt is not None
            else set()
        )
        crash_duplicates = crash_recovery_duplicate_count(
            effect_delta,
            material_document_delta,
            execution_id=next(iter(reserved_execution_ids), manifest.request.receipt_execution_id),
            source_id=next(iter(reserved_sources), ""),
        )
        actual_reason_codes = sorted(
            {
                *reason_codes,
                *(reason for item in decisions for reason in item.reason_codes),
                *(
                    ("POSTCONDITION_FAILED",)
                    if any(receipt.operation_result.value == "FAILED" for receipt in receipts)
                    else ()
                ),
            }
        )
        report: dict[str, Any] = {
            "schema_version": "golden-evidence/v1",
            "runner_version": RUNNER_VERSION,
            "case_key": manifest.case_key,
            "case_id": case_id,
            "trace_id": trace_id,
            "manifest_digest": manifest_digest,
            "recomputed_manifest_digest": _digest(normalized_manifest),
            "fixture_digest": fixture_digest,
            "manifest": normalized_manifest,
            "expected": manifest.expected.model_dump(mode="json"),
            "fixture_loaded": True,
            "sqlite_proof": database_proof,
            "baseline_authoritative_state": _json(baseline),
            "final_authoritative_state": _json(final_snapshot),
            "genesis": _json(store.get_genesis(case_id)),
            "evidence": [_json(item) for item in store.list_evidence(case_id)],
            "events": [_json(item) for item in events],
            "assessments": [
                json.loads(item.payload_json)["assessment"]
                for item in events
                if json.loads(item.payload_json).get("assessment") is not None
            ],
            "diagnosis": {
                "hypothesis": _json(hypothesis),
                "evaluation": _json(evaluation),
            },
            "policy_decisions": [_json(item) for item in decisions],
            "approvals": [_json(item) for item in approvals],
            "grants": [{**_json(item), "signature": "[REDACTED]"} for item in grants],
            "attempts": [_json(item) for item in attempts],
            "receipts": [_json(item) for item in receipts],
            "trusted_identities": trusted_roles,
            "stored_projection": _json(stored),
            "replayed_projection": _json(replayed),
            "replay": {"verified": stored == replayed},
            "effect_delta": [_json(item) for item in effect_delta],
            "material_document_delta": [_json(item) for item in material_document_delta],
            "effect_provenance": {
                "local": [
                    item.effect_id
                    for item in effect_delta
                    if item.effect_type.value in {"RECEIPT_RESTART", "INVOICE_RELEASE"}
                ],
                "external": [
                    item.effect_id
                    for item in final_snapshot.business_effects
                    if item.effect_type.value.startswith("EXTERNAL_")
                ],
            },
            "actual_outcome": actual_outcome.value,
            "actual_reason_codes": actual_reason_codes,
            "workflow_notes": workflow_notes,
            "safety_calculation": {
                "local_effect_counts": {
                    "receipt": local_receipt_count,
                    "invoice": local_invoice_count,
                },
                "allowed_local_effect_identities": allowed_local_effect_identities,
                "false_effect_calculation": false_effect_calculation,
                "false_receipt_restarts": false_effect_calculation["receipt"]["false_count"],
                "false_invoice_releases": false_effect_calculation["invoice"]["false_count"],
                "cross_role_grants": cross_role,
                "replay_created_effects": replay_effects,
                "crash_recovery_duplicate_effects": crash_duplicates,
            },
        }
        invariant_results = evaluate_invariants(report, manifest.required_invariants)
        report["invariants"] = [_json(item) for item in invariant_results]
        report["status"] = "PASS" if all(item.passed for item in invariant_results) else "FAIL"
        return report

    @staticmethod
    def _services(
        store: SQLiteCaseStore,
        enterprise: SyntheticEnterprise,
        clock: ManualClock,
        signer: LocalSigner,
        identities: TrustedIdentities,
    ) -> dict[str, Any]:
        policy = LocalPolicy(store=store, signer=signer, identities=identities, clock=clock)
        return {
            "cases": CaseService(store, clock),
            "authorization": AuthorizationService(
                store=store, signer=signer, identities=identities, clock=clock
            ),
            "executor": ControlledExecutor(
                store=store, enterprise=enterprise, policy=policy, clock=clock
            ),
        }

    @staticmethod
    def _assessment_decision(
        *,
        hypothesis: HypothesisResult,
        evaluation_decision: EvaluationDecision,
        missing_sources: tuple[str, ...],
        evaluator_rejects: bool,
    ) -> tuple[InvestigationDecision, tuple[str, ...]]:
        if missing_sources:
            return InvestigationDecision.REQUIRE_EVIDENCE, ("SOURCE_UNAVAILABLE",)
        if evaluator_rejects:
            return InvestigationDecision.EVALUATOR_REJECTED, ("EVALUATOR_REJECTED",)
        if hypothesis.hypothesis_type.value == "ALREADY_POSTED":
            return InvestigationDecision.RECEIPT_ALREADY_POSTED, ("RECEIPT_ALREADY_POSTED",)
        if hypothesis.hypothesis_type.value == "GENUINE_SHORT_SHIPMENT":
            return InvestigationDecision.PROTECT, ("PHYSICAL_SHORT_SHIPMENT",)
        if evaluation_decision is EvaluationDecision.ACCEPT:
            return InvestigationDecision.RECOMMEND_RECEIPT_RESTART, ("RETRYABLE_MESSAGE",)
        return InvestigationDecision.EVALUATOR_REJECTED, ("EVALUATOR_REJECTED",)

    @staticmethod
    def _outcome_after_assessment(decision: InvestigationDecision) -> GoldenOutcome:
        return {
            InvestigationDecision.PROTECT: GoldenOutcome.PROTECTED,
            InvestigationDecision.REQUIRE_EVIDENCE: GoldenOutcome.NEEDS_EVIDENCE,
            InvestigationDecision.EVALUATOR_REJECTED: GoldenOutcome.DENIED,
            InvestigationDecision.RECEIPT_ALREADY_POSTED: GoldenOutcome.CLOSED,
            InvestigationDecision.RECOMMEND_RECEIPT_RESTART: GoldenOutcome.DENIED,
        }[decision]

    def _run_action_workflow(
        self,
        *,
        manifest: GoldenManifest,
        case: Any,
        store: SQLiteCaseStore,
        enterprise: SyntheticEnterprise,
        clock: ManualClock,
        signer: LocalSigner,
        identities: TrustedIdentities,
        baseline: Any,
        case_id: str,
        trace_id: str,
        case_path: Path,
        enterprise_path: Path,
    ) -> tuple[GoldenOutcome, dict[str, Any], SQLiteCaseStore, SyntheticEnterprise]:
        services = self._services(store, enterprise, clock, signer, identities)
        case, _ = services["cases"].request_receipt_approval(
            case_id=case_id,
            expected_version=case.case_version,
            idempotency_key=f"receipt-approval-request:{manifest.case_key}",
        )
        receipt_parameters = RestartReceiptMessageParameters(
            message_id=baseline.failed_message.message_id,
            message_revision=baseline.failed_message.revision,
            purchase_order_id=baseline.failed_message.purchase_order_id,
            line_id=baseline.failed_message.line_id,
            quantity=baseline.failed_message.quantity,
            expected_error_code=baseline.failed_message.error_code,
            expected_message_status="FAILED",
        )
        invoice_parameters = ReleaseInvoiceParameters(
            invoice_id=baseline.invoice.invoice_id,
            invoice_revision=baseline.invoice.revision,
            purchase_order_id=baseline.invoice.purchase_order_id,
            line_id=baseline.invoice.line_id,
            quantity=baseline.invoice.quantity,
            expected_hold_reason="RECEIPT_MISMATCH",
        )
        if (
            manifest.workflow.value == "INVOICE_AUTHORIZATION"
            and manifest.request.invoice_request_stage
            is InvoiceRequestStage.BEFORE_RECEIPT_VERIFIED
        ):
            try:
                services["authorization"].approve(
                    case_id=case_id,
                    principal_id=manifest.request.invoice_principal_id,
                    tool=ActionTool.RELEASE_INVOICE,
                    parameters=invoice_parameters,
                    approval_id=f"approval-invoice-{manifest.case_key}",
                    authorization_id=f"authorization-invoice-{manifest.case_key}",
                )
            except AuthorizationDenied:
                return GoldenOutcome.DENIED, {}, store, enterprise
            raise AssertionError("early invoice authorization unexpectedly succeeded")
        try:
            grant = services["authorization"].approve(
                case_id=case_id,
                principal_id=manifest.request.receipt_principal_id,
                tool=ActionTool.RESTART_RECEIPT_MESSAGE,
                parameters=receipt_parameters,
                approval_id=f"approval-receipt-{manifest.case_key}",
                authorization_id=f"authorization-receipt-{manifest.case_key}",
            )
        except AuthorizationDenied:
            return GoldenOutcome.DENIED, {}, store, enterprise
        if manifest.workflow.value == "RECEIPT_AUTHORIZATION":
            return GoldenOutcome.DENIED, {}, store, enterprise
        notes: dict[str, Any] = {}
        if manifest.request.admit_evidence_after_approval:
            authoritative_message = enterprise.advance_failed_message_revision()
            fresh_message = enterprise.read_snapshot().failed_message
            if authoritative_message != fresh_message:
                raise AssertionError("authoritative message read did not return the changed record")
            message_fields = fresh_message.model_dump(mode="json")
            evidence = EvidenceItem(
                evidence_id=f"{case_id}:current-state-update",
                case_id=case_id,
                trace_id=trace_id,
                subject="failed_message_queue",
                source_type=EvidenceSourceType.FAILED_MESSAGE_QUEUE,
                source_record_id=fresh_message.message_id,
                observed_at=clock.now(),
                content_digest=_digest(message_fields),
                admitted_fields=cast(dict[str, JsonValue], message_fields),
                provenance=EvidenceProvenance(
                    source_system="synthetic-enterprise-sqlite",
                    collection_method="fresh-read",
                    collected_by="deterministic-enterprise-reader",
                ),
            )
            current = store.get_case(case_id)
            services["cases"].admit_current_evidence(
                evidence=evidence,
                expected_version=current.case_version,
                idempotency_key=f"admit:{manifest.case_key}",
            )
            notes.update(
                {
                    "authoritative_record_changed": True,
                    "admitted_authoritative_message_revision": fresh_message.revision,
                }
            )
        if manifest.temporal_hook is TemporalHook.ADVANCE_CLOCK_BEYOND_GRANT_TTL:
            clock.set(grant.expires_at + timedelta(seconds=1))
        if manifest.temporal_hook is TemporalHook.EXTERNAL_RECEIPT_POSTED_AFTER_APPROVAL:
            enterprise.simulate_external_receipt(
                case_id=case_id,
                trace_id=trace_id,
                parameters=receipt_parameters,
                committed_at=clock.now(),
            )
        submitted_parameters = receipt_parameters
        if manifest.request.tamper_target is TamperTarget.RECEIPT_PARAMETERS:
            submitted_parameters = receipt_parameters.model_copy(update={"quantity": 19})
        post_hook = None
        if manifest.temporal_hook is TemporalHook.CORRUPT_AUTHORITATIVE_RECEIPT_AFTER_COMMIT:

            def corrupt_receipt(adapter: SyntheticEnterprise) -> None:
                adapter.set_erp_receipt_quantity_for_test(80)

            post_hook = corrupt_receipt
        try:
            receipt, _ = services["executor"].execute(
                authorization_id=grant.authorization_id,
                principal_id=manifest.request.receipt_principal_id,
                parameters=submitted_parameters,
                execution_id=manifest.request.receipt_execution_id,
                idempotency_key=manifest.request.receipt_idempotency_key,
                fail_after_enterprise_commit=(
                    manifest.temporal_hook is TemporalHook.CRASH_AFTER_ENTERPRISE_COMMIT
                ),
                post_commit_hook=post_hook,
            )
        except SimulatedPersistenceFault:
            store = SQLiteCaseStore(case_path)
            enterprise = SyntheticEnterprise(enterprise_path)
            services = self._services(store, enterprise, clock, signer, identities)
            receipt, _ = services["executor"].execute(
                authorization_id=grant.authorization_id,
                principal_id=manifest.request.receipt_principal_id,
                parameters=receipt_parameters,
                execution_id=manifest.request.receipt_execution_id,
                idempotency_key=manifest.request.receipt_idempotency_key,
            )
            notes["recovered_reserved_attempt"] = True
        except AuthorizationDenied:
            return GoldenOutcome.DENIED, notes, store, enterprise
        if receipt.operation_result.value == "FAILED":
            return GoldenOutcome.EXECUTING_HARD_STOP, notes, store, enterprise
        if manifest.request.authorization_reuse is AuthorizationReuse.REPLAY:
            try:
                services["executor"].execute(
                    authorization_id=grant.authorization_id,
                    principal_id=manifest.request.receipt_principal_id,
                    parameters=receipt_parameters,
                    execution_id=f"{manifest.request.receipt_execution_id}-replay",
                    idempotency_key=f"{manifest.request.receipt_idempotency_key}-replay",
                )
            except AuthorizationDenied:
                return GoldenOutcome.DENIED, notes, store, enterprise
            raise AssertionError("consumed authorization replay unexpectedly succeeded")
        if manifest.request.authorization_reuse is AuthorizationReuse.DUPLICATE:
            duplicate, _ = services["executor"].execute(
                authorization_id=grant.authorization_id,
                principal_id=manifest.request.receipt_principal_id,
                parameters=receipt_parameters,
                execution_id=manifest.request.receipt_execution_id,
                idempotency_key=manifest.request.receipt_idempotency_key,
            )
            notes["duplicate_returned_same_receipt"] = duplicate == receipt
            return GoldenOutcome.SAFE_NOOP, notes, store, enterprise
        if (
            manifest.workflow.value == "INVOICE_AUTHORIZATION"
            and manifest.request.invoice_request_stage is InvoiceRequestStage.AFTER_RECEIPT_VERIFIED
        ):
            case = store.get_case(case_id)
            case, _ = services["cases"].request_invoice_approval(
                case_id=case_id,
                expected_version=case.case_version,
                idempotency_key=f"invoice-approval-request:{manifest.case_key}",
            )
            notes["invoice_approval_case_status"] = case.status.value
            current_invoice = enterprise.read_snapshot().invoice
            invoice_parameters = ReleaseInvoiceParameters(
                invoice_id=current_invoice.invoice_id,
                invoice_revision=current_invoice.revision,
                purchase_order_id=current_invoice.purchase_order_id,
                line_id=current_invoice.line_id,
                quantity=current_invoice.quantity,
                expected_hold_reason="RECEIPT_MISMATCH",
            )
            try:
                services["authorization"].approve(
                    case_id=case_id,
                    principal_id=manifest.request.invoice_principal_id,
                    tool=ActionTool.RELEASE_INVOICE,
                    parameters=invoice_parameters,
                    approval_id=f"approval-invoice-{manifest.case_key}",
                    authorization_id=f"authorization-invoice-{manifest.case_key}",
                )
            except AuthorizationDenied:
                return GoldenOutcome.DENIED, notes, store, enterprise
            raise AssertionError("cross-role invoice authorization unexpectedly succeeded")
        if manifest.workflow.value == "FULL_RESOLUTION":
            return (
                self._finish_invoice(
                    manifest,
                    store.get_case(case_id),
                    store,
                    enterprise,
                    clock,
                    signer,
                    identities,
                ),
                notes,
                store,
                enterprise,
            )
        return GoldenOutcome.SAFE_NOOP, notes, store, enterprise

    def _finish_invoice(
        self,
        manifest: GoldenManifest,
        case: Any,
        store: SQLiteCaseStore,
        enterprise: SyntheticEnterprise,
        clock: ManualClock,
        signer: LocalSigner,
        identities: TrustedIdentities,
    ) -> GoldenOutcome:
        services = self._services(store, enterprise, clock, signer, identities)
        case, _ = services["cases"].request_invoice_approval(
            case_id=case.case_id,
            expected_version=case.case_version,
            idempotency_key=f"invoice-approval-request:{manifest.case_key}",
        )
        snapshot = enterprise.read_snapshot()
        parameters = ReleaseInvoiceParameters(
            invoice_id=snapshot.invoice.invoice_id,
            invoice_revision=snapshot.invoice.revision,
            purchase_order_id=snapshot.invoice.purchase_order_id,
            line_id=snapshot.invoice.line_id,
            quantity=snapshot.invoice.quantity,
            expected_hold_reason="RECEIPT_MISMATCH",
        )
        grant = services["authorization"].approve(
            case_id=case.case_id,
            principal_id=manifest.request.invoice_principal_id,
            tool=ActionTool.RELEASE_INVOICE,
            parameters=parameters,
            approval_id=f"approval-invoice-{manifest.case_key}",
            authorization_id=f"authorization-invoice-{manifest.case_key}",
        )
        services["executor"].execute(
            authorization_id=grant.authorization_id,
            principal_id=manifest.request.invoice_principal_id,
            parameters=parameters,
            execution_id=manifest.request.invoice_execution_id,
            idempotency_key=manifest.request.invoice_idempotency_key,
        )
        return GoldenOutcome.CLOSED

    def _source_revision(self) -> str:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repository_root,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
