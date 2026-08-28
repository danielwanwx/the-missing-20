# Milestone 4 Agent Contract v5 Implementation Plan

**Design:** `../specs/2026-08-26-milestone-4-agent-contract-v5-rebaseline-design.md`
**Owner:** Luna implementation worker; primary agent owns review and acceptance
**Status:** Offline gates passed; terminally `BLOCKED` by the sole v5 real-provider run

## Loop contract

**Goal:** Replace model-authored action authority with a deterministic,
selected-investigator evidence-coverage policy while preserving the real Strands
multi-agent diagnosis and existing human-gated execution workflow.

**Input scope:** Current uncommitted M4 v4 implementation, approved v5 design, synthetic
fixtures/knowledge, existing domain invariants, tests, and Golden runners.

**Non-goals:** M5/M6 work, UI, AgentCore deployment, production data, unrelated refactor,
AWS calls, commit, or push.

## Slice 1: Contract and prompt boundary

1. Bump contract, schema, prompt, harness, evaluator, and artifact versions where the
   version is part of the changed contract.
2. Remove model-authored action fields from investigator, synthesis, and evaluator
   schemas and every prompt/context/fixture.
3. Require supported investigators to read the complete authoritative source set and
   state that agents cannot recommend, authorize, or execute actions.
4. Add strict tests proving old action fields fail schema validation.

**Check:** schema, prompt, and structured-output tests pass; no model-authored action
field remains outside backward-compatible historical artifacts/docs.

## Slice 2: Selected-investigator coverage ledger

1. Add immutable hypothesis-to-fixed-investigator mapping.
2. Add application-owned source coverage records and `EvidenceCoverageLedger`.
3. Build the ledger only from detector availability, admitted evidence, the selected
   investigator's successful audited reads, integrity validation, and evaluator output.
4. Reject synthesis upgrade, substitution, or relabeling of rejected/uncertain
   investigator results.
5. Serialize normalized ledger metadata to trace/public Golden v2 output without raw
   contents or local paths.

**Check:** tests cover complete selected coverage, rejected/unrelated coverage,
missing/failed reads, wrong role, synthesis upgrade, tampering, and deterministic
serialization.

## Slice 3: Deterministic action recommendation

1. Add pure `ActionRecommendationPolicy/v1` and stable no-action reason codes.
2. Verify the model-selected retryable diagnosis against existing deterministic domain
   invariants without invoking the legacy oracle to select or repair a hypothesis.
3. Derive `RESTART_RECEIPT_MESSAGE` only when every approved v5 gate passes.
4. Adapt the policy result into the existing domain evaluation/assessment so both human
   approvals remain mandatory before controlled execution.

**Check:** accepted retryable case produces exactly one recommendation; coverage alone,
unsupported diagnosis, evaluator rejection, missing/tampered evidence, conflict, short
shipment, and already-posted profiles produce no action.

## Slice 4: Harness, Golden v2, and regressions

1. Carry selected read coverage, ledger, policy version, result, and reason through the
   harness, normalized trace, assessment persistence, and Golden v2 artifact.
2. Update scripted provider fixtures without using the legacy oracle during real-model
   execution.
3. Keep Golden v1 safety invariants unchanged.
4. Add adversarial tests for every v5 acceptance rule.

**Offline checks:**

- targeted agent tests;
- `make check`;
- `make golden` (16/16, all safety counters zero);
- `make golden-v2` (safety/scripted pass, real provider not yet run);
- byte-identical scripted runs;
- secret/absolute-path/misleading-cloud-claim scan;
- `git diff --check`.

## Review and correction budget

1. Luna performs one implementation pass.
2. Primary agent inspects the actual diff and runs all offline gates.
3. One independent Chief Architect implementation review checks only v5 correctness,
   safety, real Strands use, and competition credibility.
4. At most one focused Luna correction is allowed for a material defect.
5. If offline gates then pass, run exactly one capped Nova Pro end-to-end proof.
6. A material real-provider failure stops M4; a pass proceeds to one final independent
   `APPROVE_M4` gate.

No commit, push, or M5 progression occurs before final approval.
