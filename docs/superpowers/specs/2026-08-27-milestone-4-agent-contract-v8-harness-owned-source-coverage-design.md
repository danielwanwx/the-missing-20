# Milestone 4 Agent Contract v8 Harness-Owned Source Coverage

**Status:** `APPROVE_V8_DESIGN` — independent Chief Architect found no material blocker
**Scope:** M4 evaluator/source-coverage boundary only; no M5/M6/M7 until M4 passes
**Product direction:** User-approved material fork from terminally blocked v7

## 1. Loop contract

### Goal

Keep the independent Strands evaluator responsible for semantic judgment while moving
evidence-to-authoritative-source coverage entirely into deterministic harness code. Pass
all four synthetic profiles in exactly one v8 Nova Pro batch without weakening any v7
evidence, policy, approval, execution, replay, attempt, or cumulative-cost gate.

### Input scope

- Current v7 worktree, v7 harness-owned protocol envelope, and v6 relation-aware claims.
- Detector-owned source availability and admitted synthetic evidence.
- Existing on-demand Nova Pro provider in `us-west-2` under the restricted non-root role.
- Recorded cumulative provider cost: `$0.0551848`.
- Total promotional-credit hard cap: `$0.60`; remaining authorization:
  `$0.5448152`.

No production/employer data, provider fallback, compatibility probe, second v8 batch,
new permissions, M5 UI, AgentCore deployment, commit, push, or public action is in scope
for this M4 loop.

### Execute

1. Remove `required_evidence_sources` from model-authored evaluator output.
2. Validate evaluator semantic decisions, selected claim IDs, admitted evidence IDs, and
   failed invariants.
3. Derive a stable, application-owned `validated_source_types` projection from exact
   evaluator-validated evidence IDs joined to admitted evidence source types.
4. Combine that projection with detector-owned source availability to enforce complete
   five-source coverage for `ACCEPT`.
5. Persist the derived projection through public output, trace, coverage ledger, policy,
   assessment evidence, Golden v2, and provider evidence.
6. Pass all offline and independent gates, then run exactly one durably claimed v8 Nova
   Pro four-profile batch.

### Checks

- Provider-visible evaluator schema contains no source-set, availability, version,
  protocol, action, policy, provenance, or aggregate coverage field.
- `ACCEPT` covers every selected synthesis claim and every admitted evidence ID.
- All five authoritative detector source entries are present exactly once and `AVAILABLE`.
- Derived source types equal all five required authoritative source types.
- Missing/unavailable, duplicate-source, unknown evidence, unread evidence, tampering,
  dissent conflict, failed invariant, evaluator rejection, and incomplete validation fail
  closed.
- Existing Golden, safety, determinism, security, provider-schema, attempt, and cost gates
  remain green.

### Feedback and stop rules

- One Luna implementation pass and at most one focused material correction.
- A second material implementation failure or new product-direction need stops.
- A v8 provider model, validator, or product-output failure consumes the exclusive batch
  and returns terminal `BLOCK_M4`; no retry, tuning, fallback, or second batch.
- Success requires four-profile real-provider PASS, Golden v2 promotion, post-run local
  gates, and independent `APPROVE_M4`.

### Records

Record semantic evaluator output, harness-derived source projection, source availability,
protocol envelope, evidence/claim coverage, policy result, approvals/effects/replay,
attempt claim, requests/tokens, incremental and cumulative costs, manifests, and reviewer
verdicts. Never record credentials, account identifiers, private data, raw failure prose,
hidden reasoning, or local paths.

### Human gates

Only login/MFA, projected cumulative cost above `$0.60`, public/destructive/legal action,
a new material product fork, or final ready-to-be-judged judgment.

## 2. Root cause being removed

In v7, `AgentEvaluationResult.required_evidence_sources` asked Nova to reproduce a
deterministic set already owned by the detector and admitted evidence catalog. The
provider-visible schema allowed arbitrary strings, while the validator later required
all five application constants. The sole v7 batch reached the evaluator and failed with
`accepted evaluation omits a required source` even though the evaluator separately
returned validated evidence IDs.

Source coverage is a join over application-owned records, not a semantic judgment:

```text
validated evidence ID
  -> exact admitted EvidenceItem
  -> detector-owned EvidenceSourceType
  -> stable unique sorted source projection
```

The evaluator still decides whether claims and evidence support the synthesis. The
harness decides whether that accepted semantic result covers the required authoritative
catalog.

## 3. Considered approaches

### A. Prompt Nova to list all five sources

Rejected. It retains duplicated deterministic authority and makes acceptance depend on
copying constants correctly.

### B. Harness-owned evidence-to-source projection

Selected. It preserves the independent evaluator's semantic role and derives coverage
from exact validated IDs already required by the safety contract.

### C. Remove the independent evaluator

Rejected. It reduces competition credibility and eliminates a useful semantic dissent
gate without being necessary to remove deterministic metadata.

## 4. Model-authored evaluator contract

`agent-contract/v8` keeps the v7 investigator and synthesis semantic contracts.
`AgentEvaluationResult` contains only:

- `decision`;
- `validated_claim_ids`;
- `validated_evidence_ids`;
- `failed_invariants`.

The following are forbidden as extra model-authored fields:

- `required_evidence_sources`;
- `validated_source_types`;
- source availability or missing-source projections;
- versions, protocols, schema digests, prompts, harness metadata, policy results;
- action recommendations or authorization.

The provider-visible JSON schema must not contain any property name representing a
source set, availability, protocol identity, aggregate evidence coverage, or action
authority.

## 5. Deterministic source coverage projection

After strict evaluator parsing, the harness builds immutable
`EvaluatorSourceCoverage/v1` from:

- detector-owned `SourceAvailabilitySet`;
- admitted `EvidenceItem` records;
- `AgentEvaluationResult.validated_evidence_ids`;
- current case and trace identity;
- content-integrity validation.

For every validated evidence ID, the harness resolves exactly one admitted record and
projects its `EvidenceSourceType`. `validated_source_types` is the unique tuple sorted by
the enum value. The model cannot supply, reorder, add, or remove this projection.

The coverage record contains:

- exact sorted validated evidence IDs;
- exact sorted validated authoritative source types;
- the five detector availability entries;
- `all_admitted_evidence_validated`;
- `all_required_sources_available`;
- `all_required_sources_validated`;
- stable coverage version and reason code.

Knowledge-base records never count as authoritative source coverage. An unknown,
cross-case, duplicate, stale, tampered, or non-admitted validated ID fails before
projection.

## 6. ACCEPT and fail-closed rules

An evaluator `ACCEPT` is admissible only when every condition is true:

1. every selected synthesis claim ID is validated exactly once;
2. every admitted evidence ID is validated exactly once;
3. every required source has exactly one detector availability entry;
4. all five required sources are `AVAILABLE`;
5. each available source maps to exactly one admitted evidence record;
6. `validated_source_types` equals the stable set of all five required authoritative
   source types;
7. no failed invariant is present;
8. evidence case, trace, source identity, and content digest remain valid;
9. the harness-owned protocol envelope is valid and consistent.

`MORE_EVIDENCE` is required when detector availability marks any authoritative source
unavailable. `REJECT` or `MORE_EVIDENCE` never produces an action. Complete source
coverage alone never selects a hypothesis or authorizes action.

## 7. Data flow and persisted records

```text
detector availability + admitted evidence catalog
  -> fixed investigators with audited reads
  -> semantic synthesis
  -> independent semantic evaluator
       decision + validated claim IDs + validated evidence IDs + failed invariants
  -> deterministic EvaluatorSourceCoverage/v1
  -> harness protocol envelope
  -> selected-investigator coverage ledger
  -> deterministic action policy
  -> assessment + two-role approval + controlled effect + reread + replay
```

The same immutable `EvaluatorSourceCoverage` is included in:

- evaluator public projection as explicitly application-owned metadata;
- normalized evaluator stage and top-level trace;
- selected-investigator coverage ledger/evaluator validation flags;
- action-policy input and no-action reason;
- Golden v2 run artifact and provider PASS/failure evidence.

The existing domain `EvaluationResult` need not gain a model-facing field. Durable agent
evidence and trace carry the richer source projection, while domain validation continues
to use exact validated evidence IDs and harness-injected evaluator version.

## 8. Protocol and version boundary

The harness-owned envelope advances to:

- `agent-contract/v8`;
- `evaluator-protocol/v2`;
- `harness-v5`;
- a new semantic schema digest;
- `evaluator-source-coverage/v1`.

Synthesis remains semantic-only and retains its application-owned protocol version.
Prompt changes advance to `agent-v4` only if evaluator instructions change. Every public,
trace, Golden, attempt, and outcome projection must match one immutable v8 envelope.

## 9. Exclusive v8 attempt and cumulative cost

Preserve all v6 and v7 claims/outcomes unchanged. v8 uses new, non-overwriting artifact
paths and schemas for:

- durable exclusive v8 attempt claim;
- redacted v8 success proof;
- redacted v8 failure outcome.

The v8 claim is created with exclusive durable semantics after read-only AWS/cost
preflight and before Nova I/O. Existing, incomplete, failed, or successful v8 claims
refuse every later launch before provider I/O. Golden promotion accepts only a v8 PASS
artifact bound to the exact durable v8 claim and envelope.

Prior cumulative cost is `$0.0551848`; remaining incremental authority is `$0.5448152`.
Keep the 40-request and 400,000-input-token caps. Set maximum output to 70,240 tokens and
per-request output to at most 1,756 tokens. At frozen rates:

```text
400,000 * $0.80/M + 70,240 * $3.20/M = $0.544768 incremental
$0.0551848 + $0.544768 = $0.5999528 cumulative
```

The concurrency-safe pre-I/O reservation ledger must use the updated prior/caps and
retain conservative complete-request input bounds. Any possible reservation above the
incremental or cumulative cap is refused before provider I/O. Actual success/failure
evidence reports incremental v8 and cumulative project cost.

## 10. Offline verification

Required tests and gates:

1. Provider evaluator schema excludes source-set/availability/version/action metadata.
2. Legacy `required_evidence_sources` and model-authored `validated_source_types` fail as
   extras.
3. Stable source projection is derived only from validated admitted evidence IDs.
4. Evidence ordering cannot change the projection or byte-normalized artifact.
5. Unknown, duplicate, cross-case, stale, tampered, and knowledge-only IDs fail closed.
6. `ACCEPT` requires every selected claim, admitted ID, available required source, and
   derived required source type, with zero failed invariants.
7. Missing/unavailable source forces `MORE_EVIDENCE` and no action.
8. All v6/v7 claim, read, role, dissent, protocol-envelope, policy, approval, execution,
   replay, attempt, manifest, and cost tests remain green.
9. Concurrent v8 attempt claims produce one winner; prior v6/v7 evidence is unchanged.
10. `make check`, Golden v1 16/16 with zero safety counters, Golden v2 safety/scripted,
    byte determinism, provider-schema scan, secret/path/private-data/hidden-reasoning and
    misleading-cloud scans, and `git diff --check` pass.

## 11. Real-provider and final M4 acceptance

After independent implementation approval, exactly one v8 Nova Pro batch must prove:

- retryable main path reaches `CLOSED` only after two approvals and verified effect;
- already-posted safely closes without restart;
- genuine shortage reaches `PROTECTED` without forbidden effect;
- missing evidence reaches `REQUIRE_EVIDENCE` without forbidden effect;
- evaluator semantic output and deterministic source projection agree on all profiles;
- one immutable v8 envelope and attempt identity spans the proof;
- incremental and cumulative cost remain within caps.

After the batch, rerun every offline gate. A new independent Chief Architect returns
`APPROVE_M4` or `BLOCK_M4`. Only `APPROVE_M4` permits automatic M5 entry.

## 12. Bounded governance

1. Primary orchestrator owns scope, diff, tests, attempts, cumulative cost, evidence, and
   milestone acceptance.
2. A new independent Chief Architect reviews v8 design for material blockers only.
3. Luna performs one bounded implementation pass after approval.
4. Primary inspects actual changes and runs all offline gates.
5. A different independent architect executes implementation gate.
6. At most one focused material correction is allowed; a second material failure stops.
7. Exactly one v8 provider batch is permitted; a product-path failure stops without
   tuning, fallback, probe, retry, or code change.
8. Optional polish cannot reopen a gate.

## 13. Design acceptance

1. The evaluator makes semantic judgments but cannot author deterministic source sets.
2. Evidence-to-source coverage is application-derived, stable, traceable, and fail closed.
3. `ACCEPT` still requires all claims, all admitted evidence, five available sources,
   five derived validated source types, and no failed invariant.
4. Missing/unavailable evidence never becomes actionable.
5. Every v7 safety, envelope, exactly-once, and cost boundary remains effective.
6. The sole possible v8 batch is bounded below the remaining cumulative credit cap.
7. M4 cannot pass without all four real-provider profiles and independent final approval.

## 14. Terminal v8 result — `BLOCK_M4`

The independent implementation gate returned `APPROVE_IMPLEMENTATION` after the one
permitted focused correction. The sole v8 Nova Pro acceptance batch was then durably
claimed as `4716bb0a0af8431387f8480a037d44e9` and consumed. It failed the first profile at
the evaluator deterministic boundary with `accepted synthesis does not cover all
admitted evidence` (`AGENT_VALIDATION_ERROR`).

The redacted `agent-failure/v4` outcome records 9 requests, 20,823 input tokens, 2,998
output tokens, `$0.026252` incremental estimated cost, and `$0.0814368` cumulative
estimated project cost for `us.amazon.nova-pro-v1:0`. Post-failure offline gates passed:
445 Python tests, 1 JavaScript test, Golden v1 16/16 with all safety counters zero,
Golden v2 safety/scripted PASS with Bedrock `NOT_RUN`, 47 focused tests, and
`git diff --check`.

The final independent Chief Architect returned `BLOCK_M4`. The v8 attempt may not be
retried or tuned, and M5 may not begin. The recommended material product fork is v9:
keep semantic claim judgment and failed invariants with the evaluator, but make exact
evidence-ID coverage harness-owned by deriving the citation closure of independently
accepted synthesis claims and validating that closure against the admitted catalog,
identity, integrity, relations, source availability, and policy gates.
