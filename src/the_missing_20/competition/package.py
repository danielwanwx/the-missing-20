"""Fail-closed offline audit for the private M7 competition package.

This module is intentionally a read-only composition boundary.  It validates the
already-proven local lifecycle and M6 evidence, checks the private demo documents and
static workspace for unsafe claims or external resources, and emits a canonical audit
manifest.  It never imports an AWS SDK and never opens a network connection.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, Final, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from the_missing_20.authority_b.aws_proof import (
    M6_AGENTCORE_CAPABILITIES,
    M6_PROOF_ARTIFACT_PATH,
    M6ProofError,
    load_m6_aws_proof,
)
from the_missing_20.authority_b.lifecycle import LIFECYCLE_ARTIFACT_PATH, load_lifecycle_bundle
from the_missing_20.authority_b.models import canonical_json
from the_missing_20.authority_b.workspace_demo import (
    DecisionWorkspaceDemo,
    WorkspaceMode,
)

M7_SCHEMA_VERSION: Final[str] = "M7PrivateCompetitionAudit/v1"
M7_AUDIT_ARTIFACT_PATH: Final[str] = "artifacts/submission/private-audit-v1.json"
M7_GENERATED_AT: Final[str] = "2026-08-27T00:00:00Z"
M7_TOTAL_DURATION_SECONDS: Final[int] = 300
M7_CUMULATIVE_COST_USD: Final[str] = "0.1250496"
M7_COST_CAP_USD: Final[str] = "0.60"

# This is an auditor-owned contract, not a claim supplied by the browser smoke
# artifact. The event ledger may contain additional implementation events, but
# it must always preserve this minimum live agent/lifecycle trace.
M7_REQUIRED_BROWSER_EVENT_TYPES: Final[tuple[str, ...]] = (
    "investigation.started",
    "agent.started",
    "tool.started",
    "tool.completed",
    "evidence.returned",
    "agent.handoff",
    "synthesis.completed",
    "evaluation.completed",
    "copilot.message",
    "recovery.prepared",
    "approval.requested",
    "approval.recorded",
    "execution.started",
    "execution.completed",
    "verification.completed",
)

M7_DEMO_PATH: Final[str] = "docs/demo/five-minute-demo.md"
M7_SPEC_PATH: Final[str] = (
    "docs/superpowers/specs/2026-08-27-milestone-7-private-competition-package-design.md"
)
M7_PLAN_PATH: Final[str] = (
    "docs/superpowers/plans/2026-08-27-milestone-7-private-competition-package-implementation-plan.md"
)
M7_AUDIT_RECORD_PATH: Final[str] = "docs/audits/2026-08-28-independent-product-audit.md"
M7_SUBMISSION_PATHS: Final[tuple[str, ...]] = (
    "docs/submission/evidence-matrix.md",
    "docs/submission/judging-map.md",
    "docs/submission/known-limitations.md",
    "docs/submission/private-submission-draft.md",
)
M7_SCRIPT_PATHS: Final[tuple[str, ...]] = (
    "scripts/audit_competition_package.py",
    "scripts/run_judge_demo.py",
)
M7_WORKSPACE_PATHS: Final[tuple[str, ...]] = (
    "workspace/app.js",
    "workspace/index.html",
    "workspace/style.css",
)
M7_RUNTIME_PROOF_PATHS: Final[tuple[str, ...]] = (
    "src/the_missing_20/experiment/session.py",
    "tests/contract/test_experiment_session_recovery.py",
)
M7_ARTIFACT_PATHS: Final[tuple[str, ...]] = (
    "artifacts/agent/authority-b-advisory-v1.json",
    "artifacts/agent/authority-b-failure-v1.json",
    "artifacts/agent/authority-b-usefulness-proof-v1.json",
    "artifacts/golden/golden-v2.json",
    M6_PROOF_ARTIFACT_PATH,
    "artifacts/workspace/authority-b-lifecycle-v1.json",
    "artifacts/workspace/browser-smoke-v1.json",
    "artifacts/workspace/decision-workspace-complete.json",
    "artifacts/workspace/decision-workspace-degraded.json",
)
M7_SOURCE_PATHS: Final[tuple[str, ...]] = tuple(
    sorted(
        (
            M7_DEMO_PATH,
            M7_PLAN_PATH,
            M7_SPEC_PATH,
            M7_AUDIT_RECORD_PATH,
            *M7_SUBMISSION_PATHS,
            *M7_SCRIPT_PATHS,
            *M7_WORKSPACE_PATHS,
            *M7_RUNTIME_PROOF_PATHS,
            *M7_ARTIFACT_PATHS,
        )
    )
)

# These reviewed, safety-critical bytes are already anchored by M6.  Rehashing them
# in a mutated package cannot turn a changed deterministic proof into accepted input.
M7_FIXED_SOURCE_DIGESTS: Final[Mapping[str, str]] = {
    "artifacts/golden/golden-v2.json": (
        "d275470cfe5748105630f22d3c08c9c962001cf3957e62735b63d8b406352e69"
    ),
    M6_PROOF_ARTIFACT_PATH: ("063aa1bc07d1f26930e3e16b8801a6e10c5708fb294eb97d77e6a9fee843e492"),
    "artifacts/workspace/authority-b-lifecycle-v1.json": (
        "670b525cc5bfd9f673fd63de660a44d9db5ae000ce2cecb49fc053cacf4d7512"
    ),
}

M7_SOURCE_ROLES: Final[Mapping[str, str]] = {
    M7_DEMO_PATH: "FIVE_MINUTE_DEMO",
    M7_SPEC_PATH: "M7_DESIGN_SPEC",
    M7_PLAN_PATH: "M7_IMPLEMENTATION_PLAN",
    M7_AUDIT_RECORD_PATH: "INDEPENDENT_PRODUCT_AUDIT",
    "docs/submission/evidence-matrix.md": "EVIDENCE_MATRIX",
    "docs/submission/judging-map.md": "JUDGING_MAP",
    "docs/submission/known-limitations.md": "KNOWN_LIMITATIONS",
    "docs/submission/private-submission-draft.md": "PRIVATE_SUBMISSION_DRAFT",
    "scripts/audit_competition_package.py": "PACKAGE_AUDITOR",
    "scripts/run_judge_demo.py": "JUDGE_DEMO_RUNNER",
    "workspace/app.js": "READ_ONLY_WORKSPACE_SCRIPT",
    "workspace/index.html": "READ_ONLY_WORKSPACE_HTML",
    "workspace/style.css": "READ_ONLY_WORKSPACE_STYLE",
    "src/the_missing_20/experiment/session.py": "EXPERIMENT_SESSION_RUNTIME",
    "tests/contract/test_experiment_session_recovery.py": "EXPERIMENT_CRASH_RECOVERY_TEST",
    "artifacts/agent/authority-b-advisory-v1.json": "REAL_ADVISORY_STATUS",
    "artifacts/agent/authority-b-failure-v1.json": "REAL_PROVIDER_DEGRADED_OUTCOME",
    "artifacts/agent/authority-b-usefulness-proof-v1.json": "REAL_USEFULNESS_DISCLOSURE",
    "artifacts/golden/golden-v2.json": "GOLDEN_V2",
    M6_PROOF_ARTIFACT_PATH: "M6_EXISTING_EVIDENCE_PROOF",
    "artifacts/workspace/authority-b-lifecycle-v1.json": "M5_LIFECYCLE",
    "artifacts/workspace/browser-smoke-v1.json": "M5_BROWSER_SMOKE",
    "artifacts/workspace/decision-workspace-complete.json": "M5_COMPLETE_WORKSPACE",
    "artifacts/workspace/decision-workspace-degraded.json": "M5_DEGRADED_WORKSPACE",
}


class M7PackageError(ValueError):
    """The private competition package is missing, unsafe, or contradictory."""


class M7EvidenceClass(StrEnum):
    PROVEN = "PROVEN"
    SCRIPTED_PROVEN = "SCRIPTED_PROVEN"
    NOT_PROVEN = "NOT_PROVEN"


class M7Model(BaseModel):
    """Strict immutable base for the audit's public JSON contract."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True, allow_inf_nan=False)


class M7SourceArtifact(M7Model):
    path: Annotated[str, Field(min_length=1)]
    sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    bytes_count: int = Field(gt=0)
    role: Annotated[str, Field(min_length=1)]


class M7DemoStep(M7Model):
    step_id: Literal[
        "detect_gap",
        "agent_investigation",
        "advisory_boundary",
        "deterministic_policy",
        "quorum_execution",
        "verification_replay",
        "limits_human_gate",
    ]
    ordinal: int = Field(ge=1, le=7)
    title: Annotated[str, Field(min_length=1)]
    start_seconds: int = Field(ge=0, le=M7_TOTAL_DURATION_SECONDS)
    end_seconds: int = Field(ge=0, le=M7_TOTAL_DURATION_SECONDS)
    artifact_refs: tuple[Annotated[str, Field(min_length=1)], ...] = Field(min_length=1)
    evidence_class: M7EvidenceClass

    @model_validator(mode="after")
    def duration_is_positive(self) -> M7DemoStep:
        if self.end_seconds <= self.start_seconds:
            raise ValueError("M7 demo step must have a positive duration")
        return self


class M7EvidenceRecord(M7Model):
    evidence_id: Annotated[str, Field(min_length=1)]
    claim: Annotated[str, Field(min_length=1)]
    evidence_class: M7EvidenceClass
    status: Literal["PASS", "DEGRADED", "NOT_PROVEN"]
    scope: Annotated[str, Field(min_length=1)]
    source_refs: tuple[Annotated[str, Field(min_length=1)], ...] = Field(min_length=1)
    operational_authority: Literal[False] = False
    write_authority: Literal[False] = False


class M7AcceptanceCheck(M7Model):
    check_id: Annotated[str, Field(min_length=1)]
    status: Literal["PASS"] = "PASS"
    detail: Annotated[str, Field(min_length=1)]
    source_refs: tuple[Annotated[str, Field(min_length=1)], ...] = Field(min_length=1)


class M7CostBoundary(M7Model):
    prior_cumulative_estimated_cost_usd: Annotated[str, Field(pattern=r"^\d+(?:\.\d+)?$")]
    cumulative_estimated_cost_usd: Annotated[str, Field(pattern=r"^\d+(?:\.\d+)?$")]
    hard_cap_usd: Annotated[str, Field(pattern=r"^\d+(?:\.\d+)?$")]
    new_provider_calls: Literal[0] = 0
    new_aws_cost_usd: Literal["0"] = "0"


class M7PrivateAudit(M7Model):
    schema_version: Literal["M7PrivateCompetitionAudit/v1"] = "M7PrivateCompetitionAudit/v1"
    generated_at: Literal["2026-08-27T00:00:00Z"] = "2026-08-27T00:00:00Z"
    status: Literal["PASS"] = "PASS"
    package_status: Literal["PRIVATE_READY_TO_BE_JUDGED"] = "PRIVATE_READY_TO_BE_JUDGED"
    ready_to_be_judged: Literal[True] = True
    ready_to_submit: Literal[False] = False
    public_release: Literal[False] = False
    synthetic_only: Literal[True] = True
    advisory_write_authority: Literal[False] = False
    total_duration_seconds: Literal[300] = 300
    seven_step_story: tuple[M7DemoStep, ...] = Field(min_length=7, max_length=7)
    evidence: tuple[M7EvidenceRecord, ...] = Field(min_length=6)
    checks: tuple[M7AcceptanceCheck, ...] = Field(min_length=1)
    source_artifacts: tuple[M7SourceArtifact, ...] = Field(min_length=len(M7_SOURCE_PATHS))
    cost_boundary: M7CostBoundary
    human_gate: Literal["FINAL_PRODUCT_JUDGMENT_PENDING"] = "FINAL_PRODUCT_JUDGMENT_PENDING"
    audit_digest: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] = ""

    @model_validator(mode="after")
    def contract_is_closed(self) -> M7PrivateAudit:
        source_paths = tuple(item.path for item in self.source_artifacts)
        if source_paths != M7_SOURCE_PATHS:
            raise ValueError("M7 source ledger is incomplete or unordered")
        for source_item in self.source_artifacts:
            if source_item.role != M7_SOURCE_ROLES.get(source_item.path):
                raise ValueError("M7 source role is not approved")
            fixed = M7_FIXED_SOURCE_DIGESTS.get(source_item.path)
            if fixed is not None and source_item.sha256 != fixed:
                raise ValueError("M7 safety-critical source digest is not approved")
        source_set = set(source_paths)

        def check_refs(refs: tuple[str, ...]) -> None:
            if any(ref.split("#", 1)[0] not in source_set for ref in refs):
                raise ValueError("M7 source reference is outside the source ledger")

        for step in self.seven_step_story:
            check_refs(step.artifact_refs)
        for evidence in self.evidence:
            check_refs(evidence.source_refs)
            if evidence.operational_authority or evidence.write_authority:
                raise ValueError("M7 evidence cannot grant authority")
        for check in self.checks:
            check_refs(check.source_refs)

        expected_steps = (
            ("detect_gap", 1, 0, 35, M7EvidenceClass.PROVEN),
            ("agent_investigation", 2, 35, 85, M7EvidenceClass.SCRIPTED_PROVEN),
            ("advisory_boundary", 3, 85, 120, M7EvidenceClass.PROVEN),
            ("deterministic_policy", 4, 120, 155, M7EvidenceClass.PROVEN),
            ("quorum_execution", 5, 155, 215, M7EvidenceClass.PROVEN),
            ("verification_replay", 6, 215, 260, M7EvidenceClass.PROVEN),
            ("limits_human_gate", 7, 260, 300, M7EvidenceClass.NOT_PROVEN),
        )
        observed_steps = tuple(
            (
                item.step_id,
                item.ordinal,
                item.start_seconds,
                item.end_seconds,
                item.evidence_class,
            )
            for item in self.seven_step_story
        )
        if observed_steps != expected_steps:
            raise ValueError("M7 seven-step story is not the approved contiguous timeline")

        expected_evidence = {
            "deterministic_lifecycle": (M7EvidenceClass.PROVEN, "PASS"),
            "workspace_fail_closed": (M7EvidenceClass.PROVEN, "PASS"),
            "scripted_advisory": (M7EvidenceClass.SCRIPTED_PROVEN, "PASS"),
            "real_nova_integration": (M7EvidenceClass.PROVEN, "DEGRADED"),
            "stable_real_nova_usefulness": (M7EvidenceClass.NOT_PROVEN, "NOT_PROVEN"),
            "agentcore_capabilities": (M7EvidenceClass.NOT_PROVEN, "NOT_PROVEN"),
            "advisory_authority_boundary": (M7EvidenceClass.PROVEN, "PASS"),
        }
        observed_evidence = {
            item.evidence_id: (item.evidence_class, item.status) for item in self.evidence
        }
        if observed_evidence != expected_evidence:
            raise ValueError("M7 evidence disposition is incomplete or contradictory")
        for evidence_item in self.evidence:
            lowered = evidence_item.claim.lower()
            if evidence_item.evidence_id == "real_nova_integration" and not (
                "connectivity" in evidence_item.scope.lower()
                and "degraded" in evidence_item.scope.lower()
            ):
                raise ValueError("real Nova evidence scope must be connectivity/degradation only")
            if evidence_item.evidence_id == "stable_real_nova_usefulness" and (
                evidence_item.evidence_class is not M7EvidenceClass.NOT_PROVEN
                or evidence_item.status != "NOT_PROVEN"
                or ("not proven" not in lowered and "not_proven" not in lowered)
            ):
                raise ValueError("stable real Nova usefulness must remain NOT_PROVEN")
            if evidence_item.evidence_id == "agentcore_capabilities" and (
                evidence_item.evidence_class is not M7EvidenceClass.NOT_PROVEN
                or evidence_item.status != "NOT_PROVEN"
                or ("not proven" not in lowered and "not_proven" not in lowered)
            ):
                raise ValueError("AgentCore capabilities must remain NOT_PROVEN")

        expected_check_ids = {
            "clean_state_regeneration",
            "seven_step_story",
            "lifecycle_safety",
            "workspace_modes",
            "m6_evidence_boundary",
            "browser_safety",
            "experiment_crash_recovery",
            "truth_boundary_scan",
            "private_release_gate",
        }
        if {item.check_id for item in self.checks} != expected_check_ids:
            raise ValueError("M7 acceptance check set is incomplete")
        if (
            self.cost_boundary.prior_cumulative_estimated_cost_usd != M7_CUMULATIVE_COST_USD
            or self.cost_boundary.cumulative_estimated_cost_usd != M7_CUMULATIVE_COST_USD
            or self.cost_boundary.hard_cap_usd != M7_COST_CAP_USD
            or self.cost_boundary.new_provider_calls != 0
            or self.cost_boundary.new_aws_cost_usd != "0"
        ):
            raise ValueError("M7 cost boundary is contradictory")
        if self.audit_digest:
            expected = _audit_digest(self)
            if self.audit_digest != expected:
                raise ValueError("M7 audit digest mismatch")
        return self


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _audit_digest(audit: M7PrivateAudit) -> str:
    return hashlib.sha256(
        canonical_json(audit.model_dump(mode="json", exclude={"audit_digest"})).encode("utf-8")
    ).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise M7PackageError(f"M7 source is missing or malformed: {path}") from exc
    if not isinstance(value, dict):
        raise M7PackageError(f"M7 source must be a JSON object: {path}")
    return value


def _read_sources(repository_root: Path) -> tuple[M7SourceArtifact, ...]:
    result: list[M7SourceArtifact] = []
    for relative in M7_SOURCE_PATHS:
        path = repository_root / relative
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise M7PackageError(f"M7 source is missing: {relative}") from exc
        try:
            source_text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise M7PackageError(f"M7 source is not UTF-8: {relative}") from exc
        if _REMOTE_URL.search(source_text):
            raise M7PackageError(f"M7 source contains a remote URL: {relative}")
        if _SECRET.search(source_text):
            raise M7PackageError(f"M7 source contains secret-like text: {relative}")
        result.append(
            M7SourceArtifact(
                path=relative,
                sha256=_sha_bytes(raw),
                bytes_count=len(raw),
                role=M7_SOURCE_ROLES[relative],
            )
        )
    return tuple(result)


def _load_workspace(path: Path) -> DecisionWorkspaceDemo:
    try:
        value = DecisionWorkspaceDemo.model_validate_json(path.read_bytes())
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise M7PackageError(f"M7 workspace artifact is missing or invalid: {path}") from exc
    return value


def _validate_experiment_crash_recovery(repository_root: Path) -> None:
    """Run the public-session crash proof before accepting a ready audit.

    This is intentionally an offline runtime check.  It injects each documented
    persistence fault into the local Authority-B adapter, retries the same public
    command after reopening the session, and verifies that the durable event marker
    and enterprise effect are each idempotent.  It also proves that a durable chat
    turn can be reopened and retried without rerunning read tools or changing any
    operational state.  A checked-in self-claim cannot make M7 ready if either path
    regresses.
    """

    from unittest.mock import patch  # noqa: PLC0415

    from the_missing_20.application.executor import (  # noqa: PLC0415
        SimulatedPersistenceFault,
    )
    from the_missing_20.authority_b.executor import (  # noqa: PLC0415
        AuthorityBControlledExecutor,
    )
    from the_missing_20.experiment.events import PublicEventType  # noqa: PLC0415
    from the_missing_20.experiment.session import ExperimentSession  # noqa: PLC0415

    def operational_state_bytes(data_directory: Path) -> tuple[bytes | None, ...]:
        """Capture durable state that chat is not allowed to mutate."""

        return tuple(
            (data_directory / filename).read_bytes()
            if (data_directory / filename).exists()
            else None
            for filename in (
                "enterprise.sqlite",
                "case.sqlite",
                "quorum-ledger.json",
            )
        )

    def chat_contract(response: Mapping[str, Any], *, phase: str) -> tuple[Any, ...]:
        intent = response.get("intent")
        message = response.get("message")
        citations = response.get("citations")
        if (
            not isinstance(intent, str)
            or not intent
            or not isinstance(message, str)
            or not message
            or not isinstance(citations, list)
            or not all(isinstance(item, str) for item in citations)
            or response.get("read_only") is not True
        ):
            raise M7PackageError(f"M7 chat {phase} response is not a read-only durable contract")
        return intent, message, tuple(citations), True

    for failure_flag in ("fail_after_reservation", "fail_after_enterprise_commit"):
        try:
            with tempfile.TemporaryDirectory(prefix="missing20-m7-crash-") as raw_directory:
                data_directory = Path(raw_directory)
                session = ExperimentSession(repository_root, data_directory=data_directory)
                prepared = session.decision_command(
                    {
                        "command": "prepare_recovery",
                        "tool": "restart_receipt_message",
                        "idempotency_key": f"m7-crash:{failure_flag}:prepare",
                    }
                )
                intent_id = str(prepared["approval"]["intent_id"])
                prepared_case_version = int(prepared["case_version"])
                for principal, suffix in (
                    ("integration-operator", "operator"),
                    ("ap-approver", "ap"),
                ):
                    session.decision_command(
                        {
                            "command": "approve",
                            "intent_id": intent_id,
                            "principal_id": principal,
                            "idempotency_key": f"m7-crash:{failure_flag}:{suffix}",
                        }
                    )

                original_execute = AuthorityBControlledExecutor.execute
                calls = 0

                def fail_once(
                    *args: Any,
                    _failure_flag: str = failure_flag,
                    _original_execute: Any = original_execute,
                    **kwargs: Any,
                ) -> Any:
                    nonlocal calls
                    calls += 1
                    if calls == 1:
                        kwargs[_failure_flag] = True
                    return _original_execute(*args, **kwargs)

                execute_key = f"m7-crash:{failure_flag}:execute"
                with patch.object(AuthorityBControlledExecutor, "execute", new=fail_once):
                    try:
                        session.decision_command(
                            {
                                "command": "execute",
                                "intent_id": intent_id,
                                "idempotency_key": execute_key,
                            }
                        )
                    except SimulatedPersistenceFault:
                        pass
                    else:
                        raise M7PackageError(f"M7 crash proof did not inject {failure_flag}")
                    # The public command is retried by a fresh process/session, not
                    # by the object that held the pre-crash in-memory caches.
                    del session
                    session = ExperimentSession(repository_root, data_directory=data_directory)
                    retry = session.decision_command(
                        {
                            "command": "execute",
                            "intent_id": intent_id,
                            "idempotency_key": execute_key,
                        }
                    )

                started = tuple(
                    event
                    for event in session.events_since()
                    if event.event_type is PublicEventType.EXECUTION_STARTED
                )
                effects = session.enterprise.read_snapshot().business_effects
                if (
                    calls != 3
                    or retry.get("execution", {}).get("verified") is not True
                    or retry.get("execution", {}).get("replay_effect_delta") != 0
                    or len(retry.get("execution", {}).get("effects", [])) != 1
                    or len(effects) != 1
                    or len(started) != 1
                    or started[0].case_version != prepared_case_version
                ):
                    raise M7PackageError(
                        f"M7 crash proof failed after reload for {failure_flag}: retry was not "
                        "a truthful single-effect verification"
                    )
        except M7PackageError:
            raise
        except Exception as exc:
            raise M7PackageError(
                f"M7 crash proof failed after reload for {failure_flag}: {exc}"
            ) from exc

    try:
        with tempfile.TemporaryDirectory(prefix="missing20-m7-chat-") as raw_directory:
            data_directory = Path(raw_directory)
            session = ExperimentSession(repository_root, data_directory=data_directory)
            question = "Where did the missing units go?"
            idempotency_key = "m7-chat:exact-retry"
            durable_before = operational_state_bytes(data_directory)
            events_before = session.events_since()
            first = session.chat_command(question, idempotency_key=idempotency_key)
            first_contract = chat_contract(first, phase="first-turn")
            durable_after_first = operational_state_bytes(data_directory)
            events_after_first = session.events_since()
            first_tool_events = tuple(
                event
                for event in events_after_first
                if event.event_type is PublicEventType.TOOL_STARTED
            )
            first_evidence_events = tuple(
                event
                for event in events_after_first
                if event.event_type is PublicEventType.EVIDENCE_RETURNED
            )
            first_chat_events = tuple(
                event
                for event in events_after_first
                if event.event_type is PublicEventType.CHAT_MESSAGE
            )
            if (
                durable_after_first != durable_before
                or len(events_after_first) <= len(events_before)
                or not first_tool_events
                or not first_evidence_events
                or len(first_chat_events) != 1
            ):
                raise M7PackageError(
                    "M7 chat first-turn proof did not show read tools/evidence without "
                    "operational mutation"
                )

            del session
            session = ExperimentSession(repository_root, data_directory=data_directory)
            events_before_retry = session.events_since()
            durable_before_retry = operational_state_bytes(data_directory)
            retry = session.chat_command(question, idempotency_key=idempotency_key)
            retry_contract = chat_contract(retry, phase="exact-retry")
            events_after_retry = session.events_since()
            durable_after_retry = operational_state_bytes(data_directory)
            retry_tool_events = tuple(
                event
                for event in events_after_retry
                if event.event_type is PublicEventType.TOOL_STARTED
            )
            if (
                retry_contract != first_contract
                or events_after_retry != events_before_retry
                or durable_after_retry != durable_before_retry
                or len(retry_tool_events) != len(first_tool_events)
            ):
                raise M7PackageError(
                    "M7 chat exact-retry proof did not preserve the read-only response "
                    "without extra tools or operational state changes"
                )
    except M7PackageError:
        raise
    except Exception as exc:
        raise M7PackageError(f"M7 chat reload proof failed: {exc}") from exc


def _validate_browser_smoke(value: Mapping[str, Any]) -> None:
    if value.get("schema_version") != "decision-workspace-browser-smoke/v1":
        raise M7PackageError("M7 browser smoke schema is invalid")
    if value.get("status") != "PASS":
        raise M7PackageError("M7 browser smoke is not PASS")
    if value.get("synthetic_only") is not True:
        raise M7PackageError("M7 browser smoke is not synthetic-only")
    network = value.get("network")
    if not isinstance(network, dict) or network.get("remote_resources") != 0:
        raise M7PackageError("M7 browser smoke records a remote resource")
    if network.get("provider_calls") != 0:
        raise M7PackageError("M7 browser smoke records a provider call")
    incident = value.get("incident")
    if not isinstance(incident, dict):
        raise M7PackageError("M7 browser smoke incident proof is missing")
    if not isinstance(incident.get("incident_id"), str) or not incident.get("incident_id"):
        raise M7PackageError("M7 browser smoke incident identity is missing")
    initial_counts = incident.get("initial_counts")
    final_counts = incident.get("final_counts")
    if initial_counts != {"total": 100, "erp_recorded": 80, "queue_failed": 20}:
        raise M7PackageError("M7 browser smoke does not prove the initial 100/80/20 state")
    if final_counts != {"total": 100, "erp_recorded": 100, "queue_failed": 0}:
        raise M7PackageError("M7 browser smoke does not prove the final 100/100/0 state")
    server = value.get("server")
    if not isinstance(server, dict):
        raise M7PackageError("M7 browser smoke server boundary is missing")
    if server.get("local_synthetic_commands") is not True:
        raise M7PackageError("M7 browser smoke server is not local synthetic-only")
    if server.get("provider_calls") is not False:
        raise M7PackageError("M7 browser smoke server records a provider call")
    if server.get("write_scope") != "local_synthetic_only":
        raise M7PackageError("M7 browser smoke server write scope is not local synthetic-only")
    if server.get("advisory_tools_read_only") is not True:
        raise M7PackageError("M7 browser smoke advisory tools are not read-only")
    event_ledger = value.get("event_ledger")
    if not isinstance(event_ledger, dict):
        raise M7PackageError("M7 browser smoke event ledger proof is missing")
    required_ledger_flags = {
        "actual_agent_events": "actual agent events",
        "sse_live": "live SSE",
        "ordered_sequence_advance": "ordered SSE sequence advancement",
        "two_role_quorum": "two-role quorum",
        "controlled_executor": "ControlledExecutor",
        "verification": "verification",
        "replay": "replay",
    }
    for field, label in required_ledger_flags.items():
        if event_ledger.get(field) is not True:
            raise M7PackageError(f"M7 browser smoke does not prove {label}")
    if event_ledger.get("bound_failed_unit_ids") != 20:
        raise M7PackageError("M7 browser smoke does not bind the twenty failed units")
    if event_ledger.get("exactly_once_effects") != 1:
        raise M7PackageError("M7 browser smoke does not prove one exactly-once effect")
    if event_ledger.get("exactly_once_effects_per_action") != 1:
        raise M7PackageError("M7 browser smoke does not prove per-action idempotency")
    if event_ledger.get("business_effects") != 2:
        raise M7PackageError("M7 browser smoke does not prove both controlled effects")
    if event_ledger.get("final_gate_closed") is not True:
        raise M7PackageError("M7 browser smoke does not prove the closed final gate")
    if event_ledger.get("replay_effect_delta") != 0:
        raise M7PackageError("M7 browser smoke replay changed the effect count")
    if (
        event_ledger.get("open_replay_sequence_start") != 2
        or event_ledger.get("open_replay_sequence_end") != 66
        or event_ledger.get("open_replay_paced") is not True
        or event_ledger.get("open_replay_api_bytes_unchanged") is not True
    ):
        raise M7PackageError(
            "M7 browser smoke does not prove open-incident replay drained without mutation"
        )
    observed_sequences = event_ledger.get("observed_sequences")
    if not isinstance(observed_sequences, list) or len(observed_sequences) < 2:
        raise M7PackageError("M7 browser smoke is missing observed SSE sequences")
    if any(not isinstance(item, int) or item < 1 for item in observed_sequences):
        raise M7PackageError("M7 browser smoke observed an invalid SSE sequence")
    if observed_sequences != list(range(observed_sequences[0], observed_sequences[-1] + 1)):
        raise M7PackageError("M7 browser smoke SSE sequence is not contiguous")
    observed_types = event_ledger.get("observed_event_types")
    required_types = event_ledger.get("required_event_types")
    if not isinstance(observed_types, list) or not isinstance(required_types, list):
        raise M7PackageError("M7 browser smoke event type proof is missing")
    if required_types != list(M7_REQUIRED_BROWSER_EVENT_TYPES):
        raise M7PackageError("M7 browser smoke required event contract is invalid")
    if any(event_type not in observed_types for event_type in M7_REQUIRED_BROWSER_EVENT_TYPES):
        raise M7PackageError("M7 browser smoke omitted a required agent or lifecycle event")
    modes = value.get("modes")
    if not isinstance(modes, list) or [item.get("mode") for item in modes] != [
        "complete",
        "degraded",
        "invalid",
    ]:
        raise M7PackageError("M7 browser smoke mode coverage is incomplete")
    for mode in modes:
        if not isinstance(mode, dict) or mode.get("status") != "PASS":
            raise M7PackageError("M7 browser smoke mode is not PASS")
        if mode.get("ui_driven") is not True:
            raise M7PackageError("M7 browser smoke mode was not exercised by the browser")
        if mode.get("remote_resources") != 0:
            raise M7PackageError("M7 browser smoke exposes an unsafe browser capability")
        if mode.get("provider_calls") != 0:
            raise M7PackageError("M7 browser smoke records a provider call")
        if mode.get("local_synthetic_commands") is not True:
            raise M7PackageError("M7 browser smoke is not local synthetic-only")
        if mode.get("write_scope") != "local_synthetic_only":
            raise M7PackageError("M7 browser smoke write scope is not local synthetic-only")
        if mode.get("console_errors") != []:
            raise M7PackageError("M7 browser smoke contains console errors")
        mode_name = mode.get("mode")
        if mode_name == "complete" and (
            mode.get("ready_marker") is not True or mode.get("advisory_status") != "COMPLETE"
        ):
            raise M7PackageError("M7 complete browser mode lacks its ready/advisory proof")
        if mode_name == "degraded" and (
            mode.get("ready_marker") is not True
            or mode.get("advisory_status") != "DEGRADED"
            or mode.get("dom_units") != 100
        ):
            raise M7PackageError("M7 degraded browser mode lacks its live degraded proof")
        if mode_name == "invalid" and (
            mode.get("ready_marker") is not False
            or mode.get("operational_claims_hidden") is not True
        ):
            raise M7PackageError("M7 invalid browser mode lacks its fail-closed proof")
    views = value.get("views")
    if not isinstance(views, list) or {
        item.get("view") for item in views if isinstance(item, dict)
    } != {
        "dashboard",
        "agent",
    }:
        raise M7PackageError("M7 browser smoke view coverage is incomplete")
    for view in views:
        if not isinstance(view, dict) or view.get("status") != "PASS":
            raise M7PackageError("M7 browser smoke view is not PASS")
        if view.get("ui_driven") is not True or view.get("sse_live") is not True:
            raise M7PackageError("M7 browser smoke view is not driven by live SSE UI state")
        if view.get("ready_marker") is not True:
            raise M7PackageError("M7 browser smoke view is missing its ready marker")
        if view.get("api_units") != 100 or view.get("dom_units") != 100:
            raise M7PackageError("M7 browser smoke view does not render exactly 100 units")
        start = view.get("sequence_start")
        end = view.get("sequence_end")
        samples = view.get("sequence_samples")
        if (
            not isinstance(start, int)
            or not isinstance(end, int)
            or end <= start
            or samples != observed_sequences
        ):
            raise M7PackageError("M7 browser smoke view does not preserve ordered SSE evidence")
        if view.get("console_errors") != []:
            raise M7PackageError("M7 browser smoke view contains console errors")
        if view.get("view") == "agent":
            citations = view.get("copilot_citations")
            if not isinstance(citations, int) or isinstance(citations, bool) or citations < 1:
                raise M7PackageError(
                    "M7 browser smoke agent view does not preserve live Copilot citations"
                )
            if view.get("execute_hidden") is not True:
                raise M7PackageError(
                    "M7 browser smoke closed agent view leaves execute control visible"
                )
    ui_flow = value.get("ui_flow")
    if not isinstance(ui_flow, dict):
        raise M7PackageError("M7 browser smoke UI flow proof is missing")
    required_ui_actions = {
        "dashboard_loaded",
        "agent_workspace_opened",
        "investigation_start_control",
        "paced_investigation",
        "copilot_queried",
        "recovery_prepared",
        "operator_approved",
        "ap_approved",
        "controlled_executor",
        "verified",
    }
    if any(ui_flow.get(action) is not True for action in required_ui_actions):
        raise M7PackageError("M7 browser smoke UI flow is incomplete")
    if ui_flow.get("replay_effect_delta") != 0:
        raise M7PackageError("M7 browser smoke UI replay changed the effect count")
    required_two_action_flow = {
        "invoice_prepared",
        "invoice_operator_approved",
        "invoice_ap_approved",
        "final_gate_closed",
        "closed_url_no_relaunch",
        "immutable_ledger_replay",
    }
    if any(ui_flow.get(action) is not True for action in required_two_action_flow):
        raise M7PackageError("M7 browser smoke UI flow omits the second action or final gate")
    degraded_mode = next(
        (item for item in modes if isinstance(item, dict) and item.get("mode") == "degraded"),
        None,
    )
    if degraded_mode is None or any(
        degraded_mode.get(field) is not True
        for field in (
            "investigation_hidden",
            "hypotheses_hidden",
            "traces_hidden",
            "evidence_hidden",
            "copilot_hidden",
            "controls_disabled",
        )
    ):
        raise M7PackageError(
            "M7 browser smoke does not prove degraded advisory surfaces are hidden"
        )
    mobile = value.get("mobile_responsive")
    if not isinstance(mobile, dict):
        raise M7PackageError("M7 browser smoke mobile proof is missing")
    viewport = mobile.get("viewport")
    body_scroll_width = mobile.get("body_scroll_width")
    document_scroll_width = mobile.get("document_scroll_width")
    flow_scroll_width = mobile.get("flow_scroll_width")
    flow_client_width = mobile.get("flow_client_width")
    mobile_values = (
        viewport,
        body_scroll_width,
        document_scroll_width,
        flow_scroll_width,
        flow_client_width,
    )
    if any(not isinstance(item, int) or isinstance(item, bool) for item in mobile_values):
        raise M7PackageError("M7 browser smoke mobile metrics are invalid")
    viewport_int = cast(int, viewport)
    body_scroll_width_int = cast(int, body_scroll_width)
    document_scroll_width_int = cast(int, document_scroll_width)
    flow_scroll_width_int = cast(int, flow_scroll_width)
    flow_client_width_int = cast(int, flow_client_width)
    if (
        viewport_int != 390
        or body_scroll_width_int > 390
        or document_scroll_width_int > 390
        or flow_scroll_width_int <= flow_client_width_int
    ):
        raise M7PackageError("M7 browser smoke does not prove the 390px responsive boundary")


_REMOTE_URL = re.compile(r"https?://(?!127\.0\.0\.1|localhost)", re.IGNORECASE)
_SECRET = re.compile(
    r"AKIA[0-9A-Z]{16}|-----BEGIN .*PRIVATE KEY-----|aws_secret_access_key|"
    r"(?:secret|password|token)\s*[:=]\s*['\"][^'\"]+['\"]",
    re.IGNORECASE,
)
_UNSAFE_REAL_NOVA = re.compile(
    r"stable\s+real\s+nova[^\n.]{0,80}(?<!not\s)\b(?:proven|pass|verified|useful|validated)\b",
    re.IGNORECASE,
)
_UNSAFE_AGENTCORE = re.compile(
    r"agentcore[^\n.]{0,100}(?<!not\s)\b(?:proven|pass|verified|deployed|working)\b",
    re.IGNORECASE,
)


def _validate_package_text(repository_root: Path) -> None:
    text_paths = (
        M7_DEMO_PATH,
        M7_SPEC_PATH,
        M7_PLAN_PATH,
        M7_AUDIT_RECORD_PATH,
        *M7_SUBMISSION_PATHS,
        *M7_SCRIPT_PATHS,
        *M7_WORKSPACE_PATHS,
    )
    for relative in text_paths:
        try:
            text = (repository_root / relative).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise M7PackageError(f"M7 package text is unreadable: {relative}") from exc
        if _REMOTE_URL.search(text):
            raise M7PackageError(f"M7 package contains a remote URL: {relative}")
        if _SECRET.search(text):
            raise M7PackageError(f"M7 package contains secret-like text: {relative}")
        if _UNSAFE_REAL_NOVA.search(text):
            raise M7PackageError(f"M7 package overclaims real Nova usefulness: {relative}")
        if _UNSAFE_AGENTCORE.search(text):
            raise M7PackageError(f"M7 package overclaims AgentCore: {relative}")
        if "DISNEY" in text.upper() or "LINKEDIN" in text.upper():
            raise M7PackageError(f"M7 package contains prohibited provenance text: {relative}")


def _validate_lifecycle_and_workspaces(repository_root: Path) -> tuple[str, str]:
    try:
        lifecycle = load_lifecycle_bundle(
            repository_root, path=repository_root / LIFECYCLE_ARTIFACT_PATH
        )
    except (OSError, TypeError, ValueError) as exc:
        raise M7PackageError("M7 lifecycle artifact is invalid") from exc
    if lifecycle.final_state.case.status.value != "CLOSED":
        raise M7PackageError("M7 lifecycle does not end CLOSED")
    if len(lifecycle.actions) != 2 or len(lifecycle.effects) != 2:
        raise M7PackageError("M7 lifecycle does not contain the two controlled actions/effects")
    if any(item.effect_delta != 0 for item in lifecycle.replays):
        raise M7PackageError("M7 lifecycle replay created an effect")

    complete = _load_workspace(
        repository_root / "artifacts/workspace/decision-workspace-complete.json"
    )
    degraded = _load_workspace(
        repository_root / "artifacts/workspace/decision-workspace-degraded.json"
    )
    if complete.mode is not WorkspaceMode.COMPLETE or degraded.mode is not WorkspaceMode.DEGRADED:
        raise M7PackageError("M7 workspace modes are contradictory")
    if complete.case.status != "CLOSED" or degraded.case.status != "CLOSED":
        raise M7PackageError("M7 workspace does not expose the validated closed case")
    if complete.human_control.controls_enabled or degraded.human_control.controls_enabled:
        raise M7PackageError("M7 workspace exposes an active control")
    if complete.execution.replay_effect_delta != 0 or degraded.execution.replay_effect_delta != 0:
        raise M7PackageError("M7 workspace replay delta is nonzero")
    if complete.advisory.status != "COMPLETE" or len(complete.advisory.hypotheses) != 3:
        raise M7PackageError("M7 complete workspace lacks the scripted advisory trace")
    if degraded.advisory.status != "DEGRADED" or degraded.advisory.hypotheses:
        raise M7PackageError("M7 degraded workspace fabricates advisory content")
    if complete.advisory.authority_label != "ADVISORY — NOT AN OPERATIONAL DECISION":
        raise M7PackageError("M7 complete workspace advisory label is missing")
    return lifecycle.case_id, lifecycle.trace_id


def _validate_m6(repository_root: Path) -> None:
    try:
        proof = load_m6_aws_proof(repository_root)
    except (M6ProofError, OSError, TypeError, ValueError) as exc:
        raise M7PackageError("M7 M6 evidence boundary is invalid") from exc
    if proof.status != "PASS" or proof.acceptance_status != "PASS_WITH_DISCLOSED_AI_DEGRADATION":
        raise M7PackageError("M7 M6 acceptance status is contradictory")
    if proof.advisory_write_authority:
        raise M7PackageError("M7 M6 proof grants advisory write authority")
    real = proof.real_provider_integration
    if (
        real.status != "PROVEN"
        or real.outcome_status != "DEGRADED"
        or real.stable_real_usefulness != "NOT_PROVEN"
        or real.scope != "CONNECTIVITY_AND_DEGRADATION_OBSERVABILITY"
        or real.operational_authority
        or real.write_authority
    ):
        raise M7PackageError("M7 real Nova integration boundary is contradictory")
    for capability in proof.capabilities:
        if capability.capability_id in M6_AGENTCORE_CAPABILITIES and (
            capability.status != "NOT_PROVEN"
            or capability.evidence_class != "NOT_PROVEN"
            or capability.write_authority
            or capability.operational_authority
        ):
            raise M7PackageError("M7 AgentCore capability is overclaimed")
    if (
        proof.cost_boundary.new_provider_calls != 0
        or proof.cost_boundary.new_aws_cost_usd != "0"
        or proof.cost_boundary.cumulative_estimated_cost_usd != M7_CUMULATIVE_COST_USD
    ):
        raise M7PackageError("M7 cost boundary records new spend")


def _build_steps() -> tuple[M7DemoStep, ...]:
    return (
        M7DemoStep(
            step_id="detect_gap",
            ordinal=1,
            title="Detect the synthetic 20-EA discrepancy",
            start_seconds=0,
            end_seconds=35,
            artifact_refs=(
                "artifacts/workspace/authority-b-lifecycle-v1.json#evidence",
                "artifacts/workspace/decision-workspace-complete.json#case",
            ),
            evidence_class=M7EvidenceClass.PROVEN,
        ),
        M7DemoStep(
            step_id="agent_investigation",
            ordinal=2,
            title="Investigate with bounded competing hypotheses",
            start_seconds=35,
            end_seconds=85,
            artifact_refs=(
                "artifacts/golden/golden-v2.json#/scripted_strands_proof",
                "artifacts/workspace/decision-workspace-complete.json#advisory",
            ),
            evidence_class=M7EvidenceClass.SCRIPTED_PROVEN,
        ),
        M7DemoStep(
            step_id="advisory_boundary",
            ordinal=3,
            title="Keep AI advisory and disclose degradation",
            start_seconds=85,
            end_seconds=120,
            artifact_refs=(
                M6_PROOF_ARTIFACT_PATH + "#real_provider_integration",
                "artifacts/workspace/decision-workspace-degraded.json#advisory",
            ),
            evidence_class=M7EvidenceClass.PROVEN,
        ),
        M7DemoStep(
            step_id="deterministic_policy",
            ordinal=4,
            title="Decide from authoritative facts and policy",
            start_seconds=120,
            end_seconds=155,
            artifact_refs=(
                "artifacts/workspace/authority-b-lifecycle-v1.json#decisions",
                "artifacts/workspace/decision-workspace-complete.json#deterministic_decisions",
            ),
            evidence_class=M7EvidenceClass.PROVEN,
        ),
        M7DemoStep(
            step_id="quorum_execution",
            ordinal=5,
            title="Authorize and execute with an exact two-role quorum",
            start_seconds=155,
            end_seconds=215,
            artifact_refs=(
                "artifacts/workspace/authority-b-lifecycle-v1.json#attestations",
                "artifacts/workspace/authority-b-lifecycle-v1.json#effects",
            ),
            evidence_class=M7EvidenceClass.PROVEN,
        ),
        M7DemoStep(
            step_id="verification_replay",
            ordinal=6,
            title="Verify authoritative state and replay safely",
            start_seconds=215,
            end_seconds=260,
            artifact_refs=(
                "artifacts/workspace/authority-b-lifecycle-v1.json#rereads",
                "artifacts/workspace/authority-b-lifecycle-v1.json#verifications",
                "artifacts/workspace/authority-b-lifecycle-v1.json#replays",
            ),
            evidence_class=M7EvidenceClass.PROVEN,
        ),
        M7DemoStep(
            step_id="limits_human_gate",
            ordinal=7,
            title="Disclose limits and leave the final gate to a human",
            start_seconds=260,
            end_seconds=300,
            artifact_refs=(
                M6_PROOF_ARTIFACT_PATH + "#capabilities",
                M7_DEMO_PATH,
            ),
            evidence_class=M7EvidenceClass.NOT_PROVEN,
        ),
    )


def _build_evidence() -> tuple[M7EvidenceRecord, ...]:
    return (
        M7EvidenceRecord(
            evidence_id="deterministic_lifecycle",
            claim=(
                "The deterministic lifecycle closes two distinct synthetic actions with "
                "verification and replay."
            ),
            evidence_class=M7EvidenceClass.PROVEN,
            status="PASS",
            scope=(
                "local detection, policy, exact quorum, ControlledExecutor, authoritative "
                "reread, effect ledger, verification, and replay"
            ),
            source_refs=(
                "artifacts/workspace/authority-b-lifecycle-v1.json",
                M6_PROOF_ARTIFACT_PATH + "#lifecycle",
            ),
        ),
        M7EvidenceRecord(
            evidence_id="workspace_fail_closed",
            claim=(
                "The read/advisory workspace renders complete, degraded, and invalid "
                "fail-closed modes; only scoped local synthetic structured controls can "
                "request recovery."
            ),
            evidence_class=M7EvidenceClass.PROVEN,
            status="PASS",
            scope=(
                "local browser smoke with zero remote resources and provider calls, "
                "local synthetic recovery scope, and explicit unavailable state"
            ),
            source_refs=(
                "artifacts/workspace/browser-smoke-v1.json",
                "artifacts/workspace/decision-workspace-complete.json",
                "artifacts/workspace/decision-workspace-degraded.json",
            ),
        ),
        M7EvidenceRecord(
            evidence_id="scripted_advisory",
            claim="The scripted advisory trace is SCRIPTED_PROVEN and synthetic only.",
            evidence_class=M7EvidenceClass.SCRIPTED_PROVEN,
            status="PASS",
            scope=(
                "four deterministic profiles with competing hypotheses, gaps, citations, "
                "and uncertainty"
            ),
            source_refs=(
                "artifacts/golden/golden-v2.json",
                "artifacts/workspace/decision-workspace-complete.json#advisory",
            ),
        ),
        M7EvidenceRecord(
            evidence_id="real_nova_integration",
            claim=(
                "Real Nova integration is PROVEN only for connectivity and degraded observability."
            ),
            evidence_class=M7EvidenceClass.PROVEN,
            status="DEGRADED",
            scope=(
                "connectivity and degraded-outcome observability only; no stable usefulness claim"
            ),
            source_refs=(
                M6_PROOF_ARTIFACT_PATH + "#real_provider_integration",
                "artifacts/agent/authority-b-failure-v1.json",
            ),
        ),
        M7EvidenceRecord(
            evidence_id="stable_real_nova_usefulness",
            claim="Stable real Nova usefulness is NOT_PROVEN.",
            evidence_class=M7EvidenceClass.NOT_PROVEN,
            status="NOT_PROVEN",
            scope="the consumed real attempt degraded before stable useful advisory output",
            source_refs=(
                M6_PROOF_ARTIFACT_PATH + "#claims/real-usefulness",
                "artifacts/agent/authority-b-usefulness-proof-v1.json",
            ),
        ),
        M7EvidenceRecord(
            evidence_id="agentcore_capabilities",
            claim="All AgentCore capabilities are NOT_PROVEN.",
            evidence_class=M7EvidenceClass.NOT_PROVEN,
            status="NOT_PROVEN",
            scope=(
                "no AgentCore Runtime, Gateway, Policy, Observability, or deployment proof "
                "is included"
            ),
            source_refs=(M6_PROOF_ARTIFACT_PATH + "#capabilities",),
        ),
        M7EvidenceRecord(
            evidence_id="advisory_authority_boundary",
            claim="Model output is advisory only and has NO WRITE AUTHORITY.",
            evidence_class=M7EvidenceClass.PROVEN,
            status="PASS",
            scope=(
                "advisory output is display/audit content only; deterministic policy and "
                "scoped local synthetic controls use simulated role principals; no "
                "authentication or independent-human claim"
            ),
            source_refs=(
                "artifacts/agent/authority-b-advisory-v1.json",
                "artifacts/workspace/authority-b-lifecycle-v1.json#grants",
            ),
        ),
    )


def _build_checks() -> tuple[M7AcceptanceCheck, ...]:
    return (
        M7AcceptanceCheck(
            check_id="clean_state_regeneration",
            detail=(
                "The judge runner regenerates lifecycle, M6 proof, and workspaces in a "
                "temporary clean state and compares the resulting audit."
            ),
            source_refs=(M7_SCRIPT_PATHS[1], M7_SPEC_PATH),
        ),
        M7AcceptanceCheck(
            check_id="seven_step_story",
            detail="Exactly seven contiguous steps cover 0–300 seconds.",
            source_refs=(M7_DEMO_PATH, M7_SPEC_PATH),
        ),
        M7AcceptanceCheck(
            check_id="lifecycle_safety",
            detail=(
                "The validated lifecycle is CLOSED, contains two distinct controlled "
                "effects, and replays with zero effect delta."
            ),
            source_refs=("artifacts/workspace/authority-b-lifecycle-v1.json",),
        ),
        M7AcceptanceCheck(
            check_id="workspace_modes",
            detail=(
                "Complete, degraded, and invalid workspace behavior is explicitly "
                "represented; advisory tools remain read-only while structured controls "
                "are scoped to the local synthetic experiment."
            ),
            source_refs=("artifacts/workspace/browser-smoke-v1.json",),
        ),
        M7AcceptanceCheck(
            check_id="m6_evidence_boundary",
            detail=(
                "M6 preserves real Nova degradation and marks stable usefulness and all "
                "AgentCore capabilities NOT_PROVEN."
            ),
            source_refs=(M6_PROOF_ARTIFACT_PATH,),
        ),
        M7AcceptanceCheck(
            check_id="browser_safety",
            detail=(
                "Headless local smoke records zero remote resources and provider calls, "
                "local synthetic command scope, and no console errors."
            ),
            source_refs=("artifacts/workspace/browser-smoke-v1.json",),
        ),
        M7AcceptanceCheck(
            check_id="experiment_crash_recovery",
            detail=(
                "The offline runtime proof injects reservation and post-commit crashes, "
                "then retries the same public command after reopening ExperimentSession "
                "to prove one marker, one effect, truthful verification, and zero replay "
                "delta; durable chat is reopened and retried without new tools or writes."
            ),
            source_refs=(
                "src/the_missing_20/experiment/session.py",
                "tests/contract/test_experiment_session_recovery.py",
            ),
        ),
        M7AcceptanceCheck(
            check_id="truth_boundary_scan",
            detail=(
                "Private package text contains no secret-like material, remote resource, "
                "prohibited provenance, or overclaim."
            ),
            source_refs=(M7_SPEC_PATH, M7_SUBMISSION_PATHS[0], M7_SCRIPT_PATHS[0]),
        ),
        M7AcceptanceCheck(
            check_id="private_release_gate",
            detail=(
                "The package is PRIVATE_READY_TO_BE_JUDGED and explicitly not ready to "
                "submit or publish."
            ),
            source_refs=("docs/submission/private-submission-draft.md", M7_SPEC_PATH),
        ),
    )


def build_private_audit(repository_root: Path) -> M7PrivateAudit:
    """Build one truthful M7 audit from current local bytes without external I/O."""

    root = repository_root.resolve()
    try:
        _validate_package_text(root)
        _validate_lifecycle_and_workspaces(root)
        _validate_m6(root)
        _validate_browser_smoke(_read_json(root / "artifacts/workspace/browser-smoke-v1.json"))
        _validate_experiment_crash_recovery(root)
        sources = _read_sources(root)
        audit = M7PrivateAudit(
            seven_step_story=_build_steps(),
            evidence=_build_evidence(),
            checks=_build_checks(),
            source_artifacts=sources,
            cost_boundary=M7CostBoundary(
                prior_cumulative_estimated_cost_usd=M7_CUMULATIVE_COST_USD,
                cumulative_estimated_cost_usd=M7_CUMULATIVE_COST_USD,
                hard_cap_usd=M7_COST_CAP_USD,
            ),
        )
        object.__setattr__(audit, "audit_digest", _audit_digest(audit))
        return audit
    except M7PackageError:
        raise
    except (M6ProofError, OSError, TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        raise M7PackageError(f"M7 package audit blocked: {exc}") from exc


def load_private_audit(repository_root: Path, *, path: Path | None = None) -> M7PrivateAudit:
    """Load and recompute a persisted audit; a rehashed stale result cannot pass."""

    root = repository_root.resolve()
    artifact_path = path or root / M7_AUDIT_ARTIFACT_PATH
    try:
        candidate = M7PrivateAudit.model_validate_json(artifact_path.read_bytes())
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise M7PackageError("M7 private audit is missing, malformed, or invalid") from exc
    expected = build_private_audit(root)
    if candidate != expected:
        raise M7PackageError("M7 private audit is stale or does not match current package bytes")
    return candidate


def write_private_audit(repository_root: Path, *, output: Path | None = None) -> M7PrivateAudit:
    """Build and persist one canonical private audit artifact."""

    root = repository_root.resolve()
    audit = build_private_audit(root)
    destination = output or root / M7_AUDIT_ARTIFACT_PATH
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(canonical_json(audit.model_dump(mode="json")) + "\n", encoding="utf-8")
    return audit


def regenerate_clean_state(repository_root: Path) -> M7PrivateAudit:
    """Regenerate deterministic inputs in a temporary copy and return its audit.

    This is deliberately kept here so the judge runner and tests use the same clean
    state semantics.  The temporary copy receives no credentials and no network access.
    """

    root = repository_root.resolve()
    with tempfile.TemporaryDirectory(prefix="missing20-m7-clean-") as raw_directory:
        clean_root = Path(raw_directory)
        for directory in (
            "artifacts",
            "fixtures",
            "workspace",
            "docs",
            "scripts",
            "src",
            "tests",
        ):
            source = root / directory
            if source.is_dir():
                shutil.copytree(source, clean_root / directory)
        # Importing the existing local builders is safe: they use synthetic SQLite and
        # fixed local artifacts only.  No AWS/provider client is created by these calls.
        from the_missing_20.authority_b.aws_proof import write_m6_aws_proof  # noqa: PLC0415
        from the_missing_20.authority_b.lifecycle import write_lifecycle_bundle  # noqa: PLC0415
        from the_missing_20.authority_b.workspace_demo import (  # noqa: PLC0415
            WorkspaceMode,
            write_decision_workspace,
        )

        write_lifecycle_bundle(clean_root)
        write_m6_aws_proof(clean_root)
        for mode in (WorkspaceMode.COMPLETE, WorkspaceMode.DEGRADED):
            write_decision_workspace(
                clean_root,
                mode=mode,
                output=clean_root / f"artifacts/workspace/decision-workspace-{mode.value}.json",
            )
        return build_private_audit(clean_root)


__all__ = [
    "M7_AUDIT_ARTIFACT_PATH",
    "M7_ARTIFACT_PATHS",
    "M7_CUMULATIVE_COST_USD",
    "M7_COST_CAP_USD",
    "M7_DEMO_PATH",
    "M7_AUDIT_RECORD_PATH",
    "M7_FIXED_SOURCE_DIGESTS",
    "M7_SCHEMA_VERSION",
    "M7_SOURCE_PATHS",
    "M7PrivateAudit",
    "M7PackageError",
    "build_private_audit",
    "load_private_audit",
    "regenerate_clean_state",
    "write_private_audit",
]
