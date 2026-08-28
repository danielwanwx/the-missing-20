"""Read-only Decision Workspace join for Authority B."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from the_missing_20.authority_b.models import (
    ADVISORY_AUTHORITY_LABEL,
    AdvisoryInvestigation,
    DecisionWorkspaceSnapshot,
    OperationalDecision,
    ProofStatus,
    QuorumStatus,
)


def build_workspace_snapshot(
    *,
    operational_decision: OperationalDecision,
    advisory: AdvisoryInvestigation | None = None,
    approval_state: QuorumStatus = QuorumStatus.OPEN,
    approval_ids: Iterable[str] = (),
    effects: Iterable[Mapping[str, Any]] = (),
    timeline: Iterable[Mapping[str, Any]] = (),
    safety_proof_status: ProofStatus | None = None,
    ai_usefulness_proof_status: ProofStatus | None = None,
    snapshot_id: str | None = None,
) -> DecisionWorkspaceSnapshot:
    """Join records without allowing advisory fields to influence the decision."""

    stamp = operational_decision.decision_digest[:16]
    return DecisionWorkspaceSnapshot(
        snapshot_id=snapshot_id or f"workspace:{operational_decision.case_id}:{stamp}",
        case_id=operational_decision.case_id,
        trace_id=operational_decision.trace_id,
        case_version=operational_decision.case_version,
        operational_decision=operational_decision,
        advisory=advisory,
        approval_state=approval_state,
        approval_ids=tuple(sorted(set(approval_ids))),
        effects=tuple(effects),
        timeline=tuple(timeline),
        safety_proof_status=safety_proof_status,
        ai_usefulness_proof_status=ai_usefulness_proof_status,
        authority_label=ADVISORY_AUTHORITY_LABEL,
    )


__all__ = ["build_workspace_snapshot"]
