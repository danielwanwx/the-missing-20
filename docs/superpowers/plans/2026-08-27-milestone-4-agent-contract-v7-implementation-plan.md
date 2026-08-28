# Milestone 4 Agent Contract v7 Implementation Record

**Design:** `../specs/2026-08-27-milestone-4-agent-contract-v7-harness-owned-protocol-design.md`
**Owner:** Luna implementation worker
**Status:** Offline implementation approved; final exactly-once provider gate returned terminal `BLOCK_M4`

## Bounded scope

- Removed model-authored synthesis and evaluator protocol-version fields.
- Added the immutable `AgentProtocolEnvelope/v1` and propagated it through the public
  run, normalized trace, stage traces, coverage ledger, action recommendation,
  persisted domain evaluation compatibility field, and Golden v2 version matrix.
- Kept the v6 relation-aware claims, fixed roles, audited reads, evaluator coverage,
  deterministic action policy, approval, idempotency, and replay gates unchanged.
- Added a pre-request, concurrency-safe token/cost reservation ledger with UTF-8
  serialized-request bounds, frozen Nova rates, reconciliation, and fail-closed usage
  validation.  The v7 caps are 40 requests, 400,000 input tokens, 79,400 output
  tokens, and 1,985 output tokens per request.
- Updated the offline Bedrock smoke configuration to the v7 output ceiling.  No AWS
  or provider call was made by this implementation pass.
- Preserved the v6 `bedrock-failure-manifest-v2.json` artifact and moved v7 provider
  outcomes to versioned `bedrock-smoke-v3.json` and `bedrock-failure-manifest-v3.json`
  paths.  The sole v7 provider batch is now consumed by a durable exclusive-create
  claim at `artifacts/agent/bedrock-attempt-claim-v1.json`; an existing, failed, or
  incomplete claim refuses every later launch before provider I/O.

## Verification target

The primary orchestrator must inspect the actual dirty diff and run focused adversarial
tests, `make check`, Golden v1, Golden v2 scripted/safety, schema/envelope/cost scans,
and `git diff --check`.  A real Nova Pro batch remains a separately gated action and is
not part of this implementation pass.

## Luna pass evidence

- Ruff format/check: PASS; mypy strict: PASS.
- Python suite: 425 passed; JavaScript suite: 1 passed.
- Golden v1: 16/16 PASS with all five safety counters at zero.
- Golden v2: safety and scripted proofs PASS; Bedrock `NOT_RUN`; overall `NOT_READY`.
- Default reservation arithmetic: 40 requests, 400,000 input-token bound, and 79,400
  output-token bound reserve `$0.57408` incremental and `$0.5999376` cumulative,
  below the `$0.5741424` incremental and `$0.60` cumulative hard caps.
- No AWS, network, provider, commit, push, or public action was performed.

## Focused correction evidence

- Added offline sequential, concurrent, incomplete-claim, v6-preservation, loser
  provider-path, and v7 Golden proof-identity tests.
- Focused provider-claim, failure-manifest, and protocol tests: 19 passed.
- The v7 claim record is fsync-backed, contains only fixed contract/envelope and cost
  metadata, and is never overwritten or removed.  PASS/failure outcomes are separate
  redacted artifacts; Golden v2 accepts only a matching v7 PASS artifact plus claim.

## Bounded correction rule

One focused material correction is permitted after the independent implementation
review.  A second material defect or a new product-direction question stops this loop
for controller direction.  Optional polish is out of scope.
