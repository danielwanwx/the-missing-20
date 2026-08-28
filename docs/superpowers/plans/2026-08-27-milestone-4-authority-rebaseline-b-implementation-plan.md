# Milestone 4 Authority Rebaseline B Implementation Plan

**Design:** `../specs/2026-08-27-milestone-4-authority-rebaseline-b-design.md`
**Status:** `BLOCK_M4_REBASELINE_B`; automatic M5 progression forbidden

## Goal

Replace model-gated operational assessment with two independent records: a materially
useful but non-authoritative advisory investigation, and a deterministic operational
decision that alone enters the exact two-role authorization, execution, verification,
and replay path.

## Bounded slices and ownership

Luna owns the Authority-B implementation across the files required by these slices while
preserving all existing v6–v9 artifacts and unrelated user changes.

1. **Authority records**
   - Add `AdvisoryInvestigation/v1`, advisory status/warnings/hypotheses/gaps/report and
     cost/latency records.
   - Add `OperationalDecision/v1` and deterministic classifier input/output types with no
     advisory dependency.
   - Add independent Safety and AI Usefulness proof manifests.

2. **Deterministic decision path**
   - Adapt the existing detector/diagnosis/state-machine facts into exact retryable,
     already-posted, genuine-shortage, and require-evidence classifications.
   - Derive action eligibility and parameters without importing any agent/advisory type.
   - Persist one byte-stable decision per case version.

3. **Advisory orchestration**
   - Reuse fixed Strands investigators, allowlisted evidence/knowledge reads, useful
     synthesis and trace collection.
   - Normalize complete, partial, degraded, and unavailable outcomes; malformed or
     conflicting output cannot raise through or alter deterministic processing.
   - Remove evaluator/synthesis acceptance as an operational prerequisite.
   - Disable corrective model calls after malformed/validator/timeout/provider failure.

4. **Exact two-role quorum**
   - Add immutable authorization intent/attestation/service-signed quorum grant models.
   - Require distinct Integration Operator and AP Approver principals over one exact
     intent digest; first approval produces no grant or state/effect.
   - Reject rejection/expiry/stale version/evidence/parameters/digest, duplicate
     principal/role, legacy grant, replay, and postcondition violations.
   - Preserve reservation, idempotency, crash recovery, verification, and effect ledger.

5. **Artifacts and Golden composition**
   - Build a read-only workspace snapshot joining advisory, operational decision,
     approvals, effects, and timeline with explicit authority labels.
   - Golden v2 reports Safety Proof and AI Usefulness Proof separately; neither can
     substitute for the other.
   - Preserve historical provider records and add distinct Authority-B attempt/outcome
     paths and cost envelope.

6. **Tests and records**
   - Add metamorphic advisory success/conflict/incomplete/malformed/timeout/absence tests
     proving identical decisions/grants/effects/replay.
   - Add classifier, status transition, usefulness scoring, quorum, provider-shaped,
     exclusive claim, cost, security, and deterministic artifact tests.
   - Update the implementation record with exact results and known limitations.

## Verification

- Full `make check`, Golden v1, Golden v2 offline, relevant deterministic replay and
  provider-shaped tests, secret/path/private-provenance/misleading-cloud scans, and
  `git diff --check`.
- Primary inspects actual files/diff and data flow.
- New independent Chief Architect returns `APPROVE_IMPLEMENTATION` or one material
  correction request. A second material failure stops.
- Only after approval may the distinct, single main-case Nova advisory proof run.

## Non-goals

No v10 contract, M5 UI, AWS deployment, public artifacts, commit/push, production data,
or unrelated refactor is part of this implementation pass.

## Primary offline evidence

- `make check`: Ruff and mypy PASS; 476 Python tests and 1 JavaScript test PASS.
- Focused Authority-B unit and controlled-executor integration suites: 18 PASS.
- Golden v1: 16/16 PASS with all five safety counters zero.
- Golden v2: deterministic Safety Proof PASS and scripted Strands proof PASS; the
  distinct real Authority-B AI Usefulness Proof remains `NOT_RUN`, so promotion is
  correctly `NOT_READY` before the frozen provider attempt.
- `git diff --check`: PASS.
- Before the real proof, no Authority-B AWS/network/provider call or incremental cost
  occurred.
- The sole focused correction connected the exact quorum grant to the repository-backed
  `ControlledExecutor`, added grant/effect/verification/replay metamorphic coverage, and
  added the distinct no-retry Authority-B provider proof and promotion path.
- Independent Chief Architect final implementation gate: `APPROVE_IMPLEMENTATION`.

## Real advisory proof outcome

- Read-only AWS identity and frozen-budget preflight: PASS with zero provider calls.
- The exclusive Authority-B attempt was consumed exactly once; no fallback, probe,
  corrective call, or retry batch is permitted.
- Nova Pro outcome: `DEGRADED`; `ADVISORY_PROVIDER_FAILURE`; AI Usefulness Proof `FAIL`.
- Usage: 6 requests, 11,073 input tokens, 1,643 output tokens, `$0.014116` estimated
  incremental cost; cumulative estimate `$0.1250496` against the `$0.60` hard cap.
- Post-attempt `make check`: Ruff/mypy PASS, 476 Python tests and 1 JavaScript test PASS.
- Post-attempt Golden v1: 16/16 PASS with all five safety counters zero.
- Post-attempt Golden v2: Safety Proof PASS and scripted Strands PASS, but `NOT_READY`
  because the required real AI Usefulness Proof did not pass.
- `git diff --check`: PASS.
- Independent final Chief Architect: `BLOCK_M4_REBASELINE_B`. Deterministic Safety Proof
  passed, but the required real AI Usefulness Proof failed. Automatic M5 progression is
  forbidden; no additional provider attempt or patch cycle is authorized.

## Approved degradation-acceptance implementation pass

**Status:** implementation complete; independent decision gate pending

The user-approved material acceptance rebaseline is recorded in
`docs/decisions/0002-safety-pass-ai-degradation-disclosure.md`.  This bounded pass
implements the evidence taxonomy and Golden promotion semantics without making a
provider call or changing the consumed real attempt:

- Deterministic safety remains a hard-gated `PROVEN` Safety Proof.
- The four-profile scripted trace is labeled `SCRIPTED_PROOF` and must pass.
- The immutable Authority-B claim, redacted advisory, degraded outcome, and failed
  usefulness record are validated together; missing, mismatched, or tampered records
  fail closed.
- Real integration/degradation is labeled `PROVEN` only as an observed provider-path
  behavior.  Stable real Nova usefulness remains `NOT_PROVEN`, and its underlying
  outcome remains `DEGRADED` with `usefulness_status=FAIL`.
- A valid composition promotes only as
  `PASS_WITH_DISCLOSED_AI_DEGRADATION`; no real-provider path can produce a plain
  usefulness `PASS` under this acceptance.

Verification for this bounded pass:

- Focused Authority-B and Golden tests: 13 passed.
- Full `make check`: 478 Python tests passed; 1 JavaScript test passed; Ruff and mypy
  passed.
- Golden v1: 16/16 passed with all five safety counters zero.
- Golden v2: `PASS_WITH_DISCLOSED_AI_DEGRADATION`; Safety Proof `PASS`, scripted proof
  `PASS`, real Nova outcome `DEGRADED`, stable real Nova usefulness `NOT_PROVEN`.
- No AWS/network/provider call, retry, probe, fallback, commit, or push occurred.

## Focused implementation correction: frozen evidence anchor

The independent implementation gate identified one material integrity gap: the
consumed provider records only carried self-digests, so a coordinated rewrite could
recompute those digests.  The bounded correction adds the source-controlled
`authority-b-frozen-evidence/v1` anchor with byte-level SHA-256 values for the exact
claim, failure outcome, advisory, and usefulness records.  Golden promotion now
validates all four anchors before parsing and accepting the degraded evidence.

- Exact bundle: `PASS_WITH_DISCLOSED_AI_DEGRADATION` remains promotable.
- Coordinated mutation plus self-rehash: fails closed as `NOT_RUN` evidence.
- Full `make check`: 479 Python tests passed; 1 JavaScript test passed; Ruff and mypy
  passed.
- Focused Golden/Authority-B tests: 14 passed.
- No AWS/network/provider call or artifact retry occurred.
