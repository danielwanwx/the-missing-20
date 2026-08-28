# Milestone 4 Agent Contract v9 Implementation Plan

**Design:** `../specs/2026-08-27-milestone-4-agent-contract-v9-harness-owned-citation-closure-design.md`
**Status:** implementation approved; sole provider batch failed; final `BLOCK_M4`

## Goal

Implement the final authorized M4 mechanical repair: remove model-authored evidence-ID
sets, derive immutable exact citation closure from independently validated synthesis
claims, retain every fail-closed safety boundary, and prepare one distinct v9 provider
acceptance path under a `$0.60` cumulative hard cap.

## Implementation slices

1. Contract and prompt: reduce `AgentEvaluationResult` to decision, validated claim IDs,
   and failed invariants; reject all legacy deterministic metadata.
2. Deterministic closure: add `EvaluatorCitationClosure/v1`, stable claim-to-citation
   entries, exact admitted-catalog checks, and identity/integrity/relation/availability/
   protocol validation.
3. Propagation: source coverage v2, assessment, trace, ledger, policy, public/Golden
   artifacts, and deterministic scripted profiles consume closure evidence IDs only.
4. Envelope: advance v9 contract/evaluator/harness/prompt/closure/source-coverage versions
   and bind every projection to the same immutable protocol.
5. Attempt and budget: preserve v6–v8 artifacts; add exclusive v9 claim plus distinct
   success/failure paths; freeze 40 requests, 400,000 input, 62,040 output, 1,551 output
   per request, `$0.0814368` prior, and `$0.5185632` incremental cap.
6. Verification: adversarial closure/schema/attempt/cost tests, complete existing suite,
   Golden v1/v2 offline gates, determinism/security/artifact scans, and diff hygiene.

## Feedback and stop rules

Luna owns one bounded implementation pass. Primary inspects the actual diff and runs all
gates. One independent implementation review may authorize at most one focused material
correction. A second defect or a new product fork stops. No AWS is allowed before final
`APPROVE_IMPLEMENTATION`. The v9 provider batch is exclusive and final; failure ends the
M4 patch cycle without v10.

## Primary offline verification

- `make check`: Ruff and mypy PASS; 458 Python tests and 1 JavaScript test PASS.
- Golden v1: 16/16 PASS with all five safety counters zero.
- Golden v2 offline: safety PASS, scripted PASS, Bedrock `NOT_RUN`, promotion not ready
  until the exclusive provider batch.
- Focused v9/closure/attempt/failure/policy/protocol/integration suite: 57 PASS.
- Provider evaluator schema exposes only `decision`, `validated_claim_ids`, and
  `failed_invariants`; deterministic evidence/source/protocol/action fields are absent.
- Secret/path scan and `git diff --check`: PASS.
- No AWS/network/provider call, commit, push, or M5 work occurred in implementation.

## Independent implementation gate

`APPROVE_IMPLEMENTATION`. The reviewer found no material blocker and independently
confirmed 35 focused tests plus `git diff --check`, the semantic-only provider schema,
fail-closed harness citation closure, distinct unclaimed v9 attempt path, and cumulative
cost enforcement.

## Provider preflight state

The first read-only STS preflight returned AWS CLI status 255 for profile
`missing20-sandbox`. No model call occurred and the exclusive v9 claim, success, and
failure paths remain absent. The batch therefore remains wholly unconsumed and may start
only after the user completes the unavoidable AWS login/MFA gate.

## Real-provider and final M4 gate

- Login recovered and the repeated read-only preflight passed with zero model calls.
- Exclusive claim: `3f9366a04770425baa3fcae16d543934`.
- Sole v9 Nova Pro batch: consumed; profile 01 failed at evaluator validation with
  `accepted synthesis does not have complete citation closure`.
- Redacted outcome: `agent-failure/v5`, 10 requests, 23,431 input tokens, 3,360 output
  tokens, `$0.0294968` incremental and `$0.1109336` cumulative estimated cost.
- Post-failure gates: 458 Python and 1 JavaScript PASS; Golden v1 16/16 with all safety
  counters zero; Golden v2 safety/scripted PASS and Bedrock `NOT_RUN`; focused 57 PASS;
  `git diff --check` PASS.
- Independent final gate: `BLOCK_M4`. The M4 patch cycle is closed. No retry, tuning,
  fallback, v10, or M5 progression is authorized.
