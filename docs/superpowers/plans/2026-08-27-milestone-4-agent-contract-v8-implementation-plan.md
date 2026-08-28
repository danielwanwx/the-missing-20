# Milestone 4 Agent Contract v8 Implementation Record

**Design:** `../specs/2026-08-27-milestone-4-agent-contract-v8-harness-owned-source-coverage-design.md`
**Owner:** Luna implementation worker
**Status:** implementation approved; sole real-provider batch failed; final `BLOCK_M4`

## Bounded scope

- Removed the model-authored evaluator source-set field from `AgentEvaluationResult`.
- Added immutable `EvaluatorSourceCoverage/v1`, derived only from detector-owned source
  availability, admitted authoritative evidence, and exact evaluator validated IDs.
- Propagated the coverage projection through evaluator public output, normalized stage and
  top-level trace, coverage ledger, action policy input/reasons, and Golden/provider result
  envelopes without adding model authority.
- Advanced the active harness contract to `agent-contract/v8`, evaluator protocol to
  `evaluator-protocol/v2`, harness to `harness-v5`, and evaluator prompt assets to `agent-v4`.
- Added distinct v8 provider attempt, success, and failure paths.  Existing v6/v7 claim and
  outcome artifacts are preserved and are never overwritten.
- Updated the frozen v8 budget to 40 requests, 400,000 input tokens, 70,240 output tokens,
  1,756 output tokens per request, `$0.0551848` prior cost, and `$0.5448152` incremental cap.

## Verification target

The primary orchestrator must inspect the dirty diff, run focused adversarial source-coverage
tests plus `make check`, Golden v1/v2 safety and scripted proofs, provider-schema and artifact
hygiene scans, and `git diff --check`.  No AWS or provider call is part of this implementation
pass.

## Bounded correction rule

One focused material correction is permitted after the independent implementation review.  A
second material defect or a new product-direction question stops this loop for controller
direction.  Optional polish is out of scope.

## Offline implementation gate result

- Initial independent gate: `REJECT_IMPLEMENTATION` because unavailable authoritative
  sources blocked `ACCEPT` but did not deterministically require `MORE_EVIDENCE`.
- Sole focused correction: the validator now requires `MORE_EVIDENCE` whenever any
  authoritative source is unavailable and rejects it when all sources are available;
  focused adversarial tests cover both boundaries.
- Primary verification after correction: `make check` passed with 445 Python tests and
  1 JavaScript test; Golden v1 passed 16/16 with every safety counter zero; Golden v2
  safety and scripted suites passed with Bedrock `NOT_RUN`; `git diff --check` passed.
- Final independent gate: `APPROVE_IMPLEMENTATION`.

## Real-provider and final M4 gate

- Read-only identity and frozen-cost preflight: PASS with zero model calls.
- Exclusive v8 attempt claim: `4716bb0a0af8431387f8480a037d44e9`.
- Sole Nova Pro batch: consumed and failed profile `01-retryable-lock-main-path` at the
  evaluator validator with `accepted synthesis does not cover all admitted evidence`.
- Redacted outcome: `agent-failure/v4`, 9 requests, 20,823 input tokens, 2,998 output
  tokens, `$0.026252` incremental and `$0.0814368` cumulative estimated cost.
- Post-failure verification: 445 Python and 1 JavaScript tests passed; Golden v1 passed
  16/16 with all safety counters zero; Golden v2 safety/scripted passed and Bedrock was
  `NOT_RUN`; 47 focused tests and `git diff --check` passed.
- Independent final gate: `BLOCK_M4`. No retry, tuning, second v8 batch, or M5 entry is
  permitted. Recommended next product fork: harness-owned evidence-ID citation closure.
