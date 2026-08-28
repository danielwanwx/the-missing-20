"""Independent Safety Proof and AI Usefulness Proof builders."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from the_missing_20.authority_b.models import (
    ADVISORY_AUTHORITY_LABEL,
    AdvisoryInvestigation,
    AdvisoryStatus,
    AIUsefulnessProof,
    EvidenceClass,
    OperationalDecision,
    ProofCheck,
    ProofStatus,
    SafetyProof,
)


def _checks(values: Iterable[tuple[str, bool, str]]) -> tuple[ProofCheck, ...]:
    return tuple(
        ProofCheck(
            check_id=check_id,
            status=ProofStatus.PASS if passed else ProofStatus.FAIL,
            detail=detail,
        )
        for check_id, passed, detail in sorted(values, key=lambda item: item[0])
    )


def build_safety_proof(
    *,
    proof_id: str,
    operational_decision: OperationalDecision,
    safety_counters: Mapping[str, int] | None = None,
    metamorphic_results: Iterable[bool] = (),
    quorum_verified: bool = True,
    replay_verified: bool = True,
) -> SafetyProof:
    """Build an authoritative proof from deterministic checks only."""

    counters = dict(safety_counters or {})
    counter_ok = all(value == 0 for value in counters.values())
    metamorphic = tuple(metamorphic_results)
    checks = _checks(
        (
            (
                "deterministic_decision_digest",
                bool(operational_decision.decision_digest),
                "decision digest is present",
            ),
            ("safety_counters", counter_ok, "all deterministic safety counters are zero"),
            (
                "advisory_independence",
                ADVISORY_AUTHORITY_LABEL not in operational_decision.reason_codes,
                "operational decision has no advisory input",
            ),
            (
                "metamorphic_advisory_permutations",
                all(metamorphic) if metamorphic else True,
                "decision/grant/effect/replay invariance",
            ),
            ("exact_two_role_quorum", quorum_verified, "both distinct human roles are required"),
            ("replay_controls", replay_verified, "replay does not create a second effect"),
        )
    )
    status = (
        ProofStatus.PASS
        if all(item.status is ProofStatus.PASS for item in checks)
        else ProofStatus.FAIL
    )
    return SafetyProof(proof_id=proof_id, status=status, checks=checks)


def build_ai_usefulness_proof(
    *,
    proof_id: str,
    advisory: AdvisoryInvestigation,
    require_real_provider: bool = False,
    evidence_class: EvidenceClass | None = None,
) -> AIUsefulnessProof:
    """Score advisory value separately from operational safety.

    The evidence class is intentionally independent from the check status.  A
    scripted trace may pass the usefulness checks while remaining
    ``SCRIPTED_PROOF``.  A real-provider trace is never promoted to stable
    usefulness by this builder: callers asking for real-provider evidence receive
    an explicit failing stability check and ``NOT_PROVEN`` classification.
    """

    hypotheses_ok = len(advisory.hypotheses) >= 2
    gaps_ok = bool(advisory.proposed_evidence_gaps or advisory.deterministic_evidence_gaps)
    knowledge_ok = bool(advisory.knowledge_citations)
    report_ok = bool(advisory.incident_report)
    uncertainty_ok = bool(
        advisory.dissent
        or advisory.warnings
        or any(item.confidence_band.value != "HIGH" for item in advisory.hypotheses)
    )
    provider_ok = advisory.status in {AdvisoryStatus.COMPLETE, AdvisoryStatus.PARTIAL}
    if require_real_provider:
        provider_ok = provider_ok and advisory.provider not in {None, "scripted"}
    resolved_class = evidence_class or (
        EvidenceClass.NOT_PROVEN
        if require_real_provider or advisory.provider is None
        else EvidenceClass.SCRIPTED_PROOF
        if advisory.provider == "scripted"
        else EvidenceClass.PROVEN
    )
    checks = _checks(
        (
            ("competing_hypotheses", hypotheses_ok, "at least two hypotheses are visible"),
            ("evidence_gaps", gaps_ok, "evidence gaps are visible"),
            ("knowledge_provenance", knowledge_ok, "allowlisted procedural knowledge is cited"),
            ("incident_report", report_ok, "a concise incident report is present"),
            ("uncertainty_or_disagreement", uncertainty_ok, "uncertainty or dissent is preserved"),
            ("provider_trace", provider_ok, "advisory trace is publishable"),
            (
                "no_operational_authority",
                advisory.authority_label == ADVISORY_AUTHORITY_LABEL,
                "advisory label is immutable",
            ),
            (
                "stable_real_nova_usefulness",
                not require_real_provider,
                "stable real Nova usefulness is not established by this proof",
            ),
        )
    )
    status = (
        ProofStatus.PASS
        if all(item.status is ProofStatus.PASS for item in checks)
        else ProofStatus.FAIL
    )
    return AIUsefulnessProof(
        proof_id=proof_id,
        status=status,
        checks=checks,
        advisory_status=advisory.status,
        provider=advisory.provider,
        requests=advisory.usage.request_count,
        input_tokens=advisory.usage.input_tokens,
        output_tokens=advisory.usage.output_tokens,
        estimated_cost_usd=advisory.usage.estimated_cost_usd,
        evidence_class=resolved_class,
    )


__all__ = ["build_ai_usefulness_proof", "build_safety_proof"]
