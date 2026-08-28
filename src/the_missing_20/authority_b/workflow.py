"""Closed Authority-B loop joining deterministic authority and advisory display."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from the_missing_20.authority_b.advisory import AdvisoryOrchestrator
from the_missing_20.authority_b.classifier import (
    DeterministicDecisionLedger,
    classify_operational_state,
)
from the_missing_20.authority_b.models import (
    AdvisoryInvestigation,
    DecisionWorkspaceSnapshot,
    OperationalDecision,
    ProofStatus,
    QuorumStatus,
)
from the_missing_20.authority_b.workspace import build_workspace_snapshot
from the_missing_20.domain.models import Case, EvidenceItem


@dataclass(frozen=True, slots=True)
class AuthorityBRun:
    """The read-only join returned to a workspace or audit exporter."""

    operational_decision: OperationalDecision
    advisory: AdvisoryInvestigation
    workspace: DecisionWorkspaceSnapshot

    def public(self) -> dict[str, Any]:
        return self.workspace.model_dump(mode="json")


def run_authority_b(
    *,
    case: Case,
    evidence: tuple[EvidenceItem, ...] | list[EvidenceItem],
    source_availability: object | None = None,
    deterministic_invariants: dict[str, bool] | None = None,
    advisory_execute: Callable[[], Any] | None = None,
    orchestrator: AdvisoryOrchestrator | None = None,
    decision_ledger: DeterministicDecisionLedger | None = None,
    advisory_now: datetime | None = None,
    advisory_gap_sources: Iterable[str] = (),
    approval_state: QuorumStatus = QuorumStatus.OPEN,
    approval_ids: Iterable[str] = (),
    effects: Iterable[dict[str, Any]] = (),
    timeline: Iterable[dict[str, Any]] = (),
    safety_proof_status: ProofStatus | None = None,
    ai_usefulness_proof_status: ProofStatus | None = None,
) -> AuthorityBRun:
    """Run detector-owned decision and model-owned advisory branch independently."""

    records = tuple(evidence)
    if not records:
        raise ValueError("Authority-B workflow requires admitted evidence")
    # The case contract intentionally does not carry trace identity; the detector
    # evidence does, and the deterministic branch derives it before any advisory
    # callable is allowed to run.
    observed_trace = records[0].trace_id
    decision = classify_operational_state(
        records,
        case=case,
        trace_id=observed_trace,
        source_availability=source_availability,
        invariants=deterministic_invariants,
        ledger=decision_ledger,
    )
    advisory = (orchestrator or AdvisoryOrchestrator()).run(
        case_id=case.case_id,
        trace_id=decision.trace_id,
        case_version=case.case_version,
        execute=advisory_execute,
        now=advisory_now,
        deterministic_evidence_gaps=advisory_gap_sources,
        admitted_evidence_ids=(item.evidence_id for item in records),
    )
    workspace = build_workspace_snapshot(
        operational_decision=decision,
        advisory=advisory,
        approval_state=approval_state,
        approval_ids=approval_ids,
        effects=effects,
        timeline=timeline,
        safety_proof_status=safety_proof_status,
        ai_usefulness_proof_status=ai_usefulness_proof_status,
    )
    return AuthorityBRun(
        operational_decision=decision,
        advisory=advisory,
        workspace=workspace,
    )


__all__ = ["AuthorityBRun", "run_authority_b"]
