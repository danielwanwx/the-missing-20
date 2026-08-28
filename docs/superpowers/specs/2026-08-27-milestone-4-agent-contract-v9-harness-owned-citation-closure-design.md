# Milestone 4 Agent Contract v9 Harness-Owned Citation Closure

**Status:** `APPROVE_V9_DESIGN` — independent Chief Architect found no material blocker
**Scope:** final authorized mechanical M4 repair; M5–M7 remain gated on `APPROVE_M4`
**Product direction:** user-approved v9; no v10 patch cycle after a real-provider failure

## 1. Loop contract

### Goal

Keep Nova responsible for independent semantic claim judgment while removing its final
deterministic set-copy task. The harness derives exact evidence-ID coverage as the
citation closure of synthesis claims independently accepted by the evaluator. Exactly
one v9 Nova Pro batch must pass all four synthetic Golden profiles before M5 begins.

### Input scope

- The current v8 worktree and its relation-aware claims, harness-owned protocol/source
  coverage, safety gates, and immutable provider-attempt history.
- Detector-owned source availability and admitted synthetic evidence only.
- Existing restricted, non-root Nova Pro path in `us-west-2`.
- Prior cumulative estimated provider cost `$0.0814368`; total hard cap `$0.60`;
  remaining authority `$0.5185632`.

No production data, fallback provider, compatibility probe, additional permissions,
commit, push, publication, M5 work before `APPROVE_M4`, or v10 repair is in scope.

### Execute

1. Remove `validated_evidence_ids` from the model-authored evaluator schema and prompt.
2. Retain evaluator `decision`, exact semantic `validated_claim_ids`, and
   `failed_invariants`.
3. Resolve each validated claim ID to exactly one already-validated synthesis claim.
4. Derive the stable evidence citation closure as the sorted unique union of those
   claims' exact `evidence_ids`.
5. Validate the closure against the full admitted catalog, case/trace identity, content
   integrity, claim relations, detector availability, source coverage, ledger, and policy.
6. Persist the harness-owned closure through assessment, trace, ledger, policy, Golden,
   attempt, and provider evidence.

### Checks

- Provider-visible evaluator schema contains no evidence-ID/source/version/protocol/
  policy/action aggregate field.
- `ACCEPT` requires every synthesis claim ID exactly once, zero failed invariants, and a
  derived citation closure equal to the admitted evidence catalog.
- Every claim citation is admitted, identity-bound, digest-valid, relation-valid, and
  attributable to a successfully read authoritative record.
- Unknown/duplicate claim IDs, uncited claims, missing/unadmitted/cross-case/stale/
  tampered evidence, unresolved contradiction, unavailable sources, incomplete source
  coverage, policy mismatch, or failed invariants prevent action.
- Existing safety, Golden, deterministic, provider-shaped, attempt, security, and cost
  gates stay green.

### Feedback, records, and stop

One Luna pass and at most one focused material correction are allowed. Record immutable
protocol, semantic evaluator output, harness citation closure, derived source coverage,
policy/approval/effect/replay evidence, exclusive attempt, requests/tokens/cost, redacted
outcome, and independent gates. Exactly one v9 provider batch is allowed. Provider or
product failure returns terminal `BLOCK_M4`; no retry, tuning, fallback, v10 proposal, or
automatic patch follows. Success requires four-profile provider PASS, all post-run gates,
and independent `APPROVE_M4`.

Human gates remain login/MFA, projected cumulative cost above `$0.60`, public,
destructive, legal, post-v9 architecture/product direction, and final product judgment.

## 2. Root cause and selected boundary

v8 correctly moved evidence-to-source projection into the harness, but still required
Nova to reproduce the complete admitted evidence-ID set. The sole batch reached the
evaluator and returned `ACCEPT` with incomplete IDs, causing the deterministic validator
to fail. Exact evidence coverage is already encoded in validated synthesis citations:

```text
semantic evaluator validates claim IDs
  -> resolve validated synthesis claims
  -> union each claim.evidence_ids
  -> stable exact citation closure
  -> admitted catalog + identity + integrity + relation + availability checks
```

The evaluator determines which claims are semantically valid. It does not restate the
mechanically implied evidence set.

## 3. Considered approaches

### A. Harness citation closure from validated claims — selected

The evaluator returns semantic claim IDs; the harness derives their citation union.
This is the smallest v8-compatible change and keeps every existing fail-closed gate.

### B. Evaluator returns only invalid claim IDs

This also permits deterministic complement and closure derivation, but reverses the
contract's meaning and broadens migration risk without improving the Golden proof.

### C. Accept incomplete model evidence IDs

Rejected. A subset rule could hide uncited admitted or contradictory evidence and would
weaken the explicit all-evidence safety contract.

## 4. Model-authored evaluator contract

`AgentEvaluationResult` v9 contains only:

- `decision`;
- `validated_claim_ids`;
- `failed_invariants`.

`validated_evidence_ids`, `required_evidence_sources`, `validated_source_types`, source
availability, provenance/coverage aggregates, versions, protocol, policy, authorization,
and actions are forbidden extra fields and absent from the provider JSON schema.

For `ACCEPT`, `validated_claim_ids` must be a duplicate-free exact match for all synthesis
claim IDs and `failed_invariants` must be empty. For `REJECT`, the IDs may be a valid
subset but no action is possible. An unavailable authoritative source deterministically
requires `MORE_EVIDENCE`; when all required sources are available, `MORE_EVIDENCE` is
invalid.

## 5. Harness-owned `EvaluatorCitationClosure/v1`

After strict evaluator parsing and synthesis validation, the harness creates an immutable
record containing:

- case and trace identity;
- sorted validated claim IDs;
- sorted unique derived evidence IDs;
- stable claim-to-evidence entries ordered by claim ID, each preserving relation and
  sorted citation IDs;
- `all_synthesis_claims_validated`;
- `all_admitted_evidence_covered`;
- identity, integrity, relation, availability, and protocol consistency flags;
- a deterministic reason code.

Derivation uses only the validated synthesis object and admitted application records.
Each validated claim ID must resolve exactly once. Every citation must resolve to one
admitted record with matching case/trace, nonempty source identity, unchanged digest, an
authoritative source, and a detector availability entry. Duplicate or unknown claim IDs,
duplicate admitted IDs, invalid relations, and unknown, stale, tampered, knowledge-only,
or cross-context citations fail before a closure is created.

The closure evidence IDs feed `EvaluatorSourceCoverage/v2`; source types remain the
stable unique projection of closure evidence joined to admitted records. Neither record
is model-authored.

## 6. Fail-closed acceptance and policy

An `ACCEPT` can become actionable only if all are true:

1. evaluator validates every synthesis claim exactly once and reports no invariant;
2. citation closure equals the complete admitted evidence-ID catalog;
3. synthesis and selected investigator claim relations pass existing support,
   contradiction, dissent, and selected-role checks;
4. every admitted record passes case, trace, identity, digest, authoritative-source,
   successful-read, and detector-availability validation;
5. all five required sources are present exactly once and available;
6. harness protocol, closure, source coverage, ledger, assessment, and trace agree;
7. deterministic action policy returns the sole allowed recommendation;
8. existing two-role approval, execution, reread, receipt, effect, and replay gates pass.

Any failure produces no action. Complete closure cannot select a hypothesis, repair a
claim, override dissent, or authorize an effect.

## 7. Data flow and compatibility

```text
admitted evidence + detector availability
  -> fixed investigators and audited reads
  -> validated relation-aware synthesis
  -> independent evaluator: decision + validated claim IDs + failed invariants
  -> harness EvaluatorCitationClosure/v1
  -> harness EvaluatorSourceCoverage/v2
  -> coverage ledger -> deterministic policy
  -> assessment -> approvals -> controlled effect -> reread -> replay
```

Public evaluator output may display closure/source coverage only under explicit
application-owned keys. Domain assessment `validated_evidence_ids` is populated from the
closure, not model output. Trace and Golden artifacts bind the evaluator result, closure,
source coverage, and protocol without recording model prose or hidden reasoning.

## 8. Protocol, attempt, and cost boundary

Advance the immutable envelope to `agent-contract/v9`, `evaluator-protocol/v3`,
`harness-v6`, `evaluator-citation-closure/v1`, and `evaluator-source-coverage/v2` with a
new semantic schema digest and prompt version. Preserve all v6–v8 attempt/outcome files.
Use distinct v9 claim, success, and failure paths; the exclusive claim is created after
read-only preflight and before any Nova I/O.

Keep 40 requests and 400,000 input tokens. With prior cost `$0.0814368`, cap output at
62,676 tokens and 1,566 per request:

```text
400,000 * $0.80/M + 62,676 * $3.20/M = $0.5205632
```

That exceeds the remaining `$0.5185632`. Use the aligned conservative maximum of
62,040 output tokens and 1,551 per request:

```text
400,000 * $0.80/M + 62,040 * $3.20/M = $0.5185280
$0.0814368 + $0.5185280 = $0.5999648
```

Use the conservative exact caps above; any reservation that could exceed either cap is
refused before provider I/O. Actual success/failure records incremental and cumulative
estimated cost.

## 9. Verification and gates

Offline gates must cover schema exclusion, legacy-field rejection, exact claim lookup,
stable citation closure, byte determinism, all fail-closed adversarial cases, policy and
ledger consistency, historical attempt immutability, concurrent v9 claim exclusivity,
cost arithmetic, secret/path/private-data/hidden-reasoning/misleading-cloud scans,
`make check`, Golden v1 16/16 with zero safety counters, Golden v2 safety/scripted, and
`git diff --check`.

After independent `APPROVE_IMPLEMENTATION`, exactly one v9 Nova Pro batch must pass all
four profiles: retryable closes only after approvals/effect verification; already-posted
closes without restart; genuine shortage becomes protected without forbidden effect;
missing evidence requires evidence without forbidden effect. Then all offline gates run
again and a new independent architect returns `APPROVE_M4` or `BLOCK_M4`.

Only `APPROVE_M4` permits automatic M5 entry. `BLOCK_M4` ends the M4 mechanical patch
cycle and returns the architecture/product decision to the user.

## 10. Design acceptance

1. AI no longer authors deterministic evidence or source sets.
2. Semantic claim acceptance remains independently model-owned.
3. Exact evidence coverage is mechanically derived, immutable, auditable, and complete.
4. Every existing evidence, relation, dissent, source, policy, approval, execution,
   replay, attempt, security, and cost boundary remains fail closed.
5. One v9 real-provider batch is the final mechanical M4 attempt.

## 11. Terminal v9 result — `BLOCK_M4`

The sole v9 Nova Pro acceptance batch was durably claimed as
`3f9366a04770425baa3fcae16d543934` and consumed. Profile 01 failed at the evaluator
boundary with `accepted synthesis does not have complete citation closure`
(`AGENT_VALIDATION_ERROR`). The redacted `agent-failure/v5` manifest records 10
requests, 23,431 input tokens, 3,360 output tokens, `$0.0294968` incremental estimated
cost, and `$0.1109336` cumulative estimated project cost for
`us.amazon.nova-pro-v1:0`.

Post-failure verification passed: 458 Python tests, 1 JavaScript test, Golden v1 16/16
with all safety counters zero, Golden v2 safety/scripted PASS with Bedrock `NOT_RUN`,
57 focused tests, and `git diff --check`. No provider PASS artifact exists.

The final independent Chief Architect returned `BLOCK_M4`. Under the explicit final-v9
governance boundary, the M4 mechanical patch cycle is closed: no retry, tuning, fallback,
v10 proposal or implementation, and no M5 entry. The remaining decision is architectural
and product-level: retain an LLM as a hard safety-gate authority, or reposition it as
non-authoritative assistance behind deterministic and/or human judgment.
