# Milestone 4 Agent Contract v5 Architecture Rebaseline

**Status:** Terminally `BLOCKED` at the v5 real-provider acceptance gate
**Scope:** M4 only; no M5/M6 work, deployment, commit, push, or additional AWS run

## 1. Problem

### Terminal gate result, 2026-08-26

The approved v5 implementation passed `make check` with 409 Python tests, Golden v1
with 16/16 cases and zero safety counters, Golden v2 scripted and safety gates, the
secret/path scan, `git diff --check`, and the independent implementation review.

The single permitted v5 Nova Pro run stopped at the deterministic validator with:

`supporting and contradicting evidence overlap`

This is a core evidence-consistency failure, not an infrastructure failure. The final
independent Chief Architect decision is `BLOCK_M4`. There is no retry, prompt tuning,
code change, commit, push, or M5 progression. The authorized architecture rebaseline
has been consumed; only an explicit new user-directed product fork may reopen work.

The sole real Nova Pro run under `agent-contract/v4` stopped at the correct safety
boundary because one investigator proposed an action without citing all five required
authoritative sources. The defect is architectural: a specialist diagnosis model was
also being asked to decide whether an operational action was safe.

M4 is rebaselined once so models interpret evidence while application-owned policy
alone decides whether an accepted diagnosis is eligible to become an action
recommendation.

## 2. Considered approaches

### A. Prompt every investigator to cite all sources

Rejected. This keeps action authority inside a probabilistic response and makes safety
depend on prompt compliance.

### B. Validate model-authored actions against the union of all agents

Rejected. Reads from an unrelated or rejected investigator could incorrectly complete
the selected hypothesis's coverage.

### C+. Separate diagnosis from action eligibility

Selected. Agents diagnose, cite, preserve dissent, synthesize, and evaluate. A
deterministic policy derives the only possible action recommendation from the selected
investigator's audited coverage and validated case state. The existing two-role human
approval and controlled executor remain unchanged.

## 3. Contract boundary

`agent-contract/v5` removes all action fields from model-authored output:

- `InvestigatorResult.proposed_action`
- `SynthesisResult.proposed_action`
- `AgentEvaluationResult.allowed_next_action`

Old action fields fail strict schema validation as extras. Agents may emit only:

- hypothesis and conclusion;
- confidence;
- cited factual claims and contradictions;
- preserved dissent;
- evaluator decision, validated claims/evidence, failed invariants, and required
  sources.

Prompts state that agents never recommend, authorize, or execute an action. A supported
investigator must read all five authoritative evidence records before returning a
supported conclusion. Knowledge remains procedural context and cannot prove current
case state.

## 4. Evidence coverage ledger

The harness builds an immutable `EvidenceCoverageLedger` after synthesis selects a
hypothesis. It is application-owned and never accepted from a model.

For each required source it records:

- source type;
- detector availability;
- admitted evidence ID and content digest;
- whether the selected investigator successfully read that exact ID;
- whether integrity, case, trace, and source identity validation passed;
- whether the evaluator validated that exact evidence ID.

The ledger also records the selected investigator, hypothesis, complete-coverage flag,
conflict flag, and a stable policy version. Selection uses one immutable mapping:
`RETRYABLE_MESSAGE -> retryable_message_investigator`,
`GENUINE_SHORT_SHIPMENT -> short_shipment_investigator`, and
`ALREADY_POSTED -> duplicate_posting_investigator`. The mapped investigator must itself
return that exact fixed hypothesis with `SUPPORTED`. Synthesis may preserve or reject
that finding but cannot upgrade, substitute, or relabel a rejected or uncertain
investigator into a supported result. Coverage from rejected, uncertain, substituted,
or unrelated investigators cannot satisfy the ledger. Missing, duplicate, stale,
malformed, error-bearing, or tampered records fail closed.

The ledger is serialized into the normalized trace and Golden v2 artifact without raw
evidence contents, local paths, secrets, hidden reasoning, or knowledge excerpts.

## 5. Deterministic action recommendation policy

`ActionRecommendationPolicy/v1` is a pure application policy. It returns
`RESTART_RECEIPT_MESSAGE` only when every condition is true:

1. synthesis selects `RETRYABLE_MESSAGE` with `SUPPORTED`;
2. the immutable hypothesis-to-role mapping selects the retryable investigator, which
   itself returned `RETRYABLE_MESSAGE` with `SUPPORTED`; synthesis did not upgrade,
   substitute, or relabel that investigator result;
3. all five authoritative sources are available and admitted exactly once;
4. the selected retryable investigator successfully read every required record;
5. evidence integrity, case, trace, source identity, and retryable-message domain
   invariants pass;
6. synthesis preserves all investigator outcomes and has no unresolved conflicting
   current-state claim;
7. evaluator returns `ACCEPT`, validates every selected claim and every admitted
   evidence ID, lists every required source, and reports no failed invariant;
8. the evidence coverage ledger is complete.

Every other state returns no action plus a stable machine-readable reason. Reading all
sources without a supported diagnosis is insufficient. The policy verifies the model's
selected diagnosis; it must not call the legacy oracle to select, repair, or replace a
failed diagnosis.

The policy result is adapted into the existing domain `EvaluationResult` and
`InvestigationAssessment`. Only then may the established workflow request two human
approvals. No agent receives approval, signing, execution, AWS, shell, filesystem,
browser, or arbitrary network capability.

## 6. Data flow

```text
detector-admitted evidence
  -> three Strands investigators with audited read tools
  -> deterministic investigator validation
  -> Strands synthesis with preserved dissent
  -> independent Strands evaluator
  -> selected-investigator EvidenceCoverageLedger
  -> ActionRecommendationPolicy/v1
  -> persisted assessment
  -> two-role human approvals
  -> controlled execution, verification, and replay
```

Strands remains material to the product: agents retrieve procedural knowledge,
investigate competing hypotheses, interpret evidence, synthesize disagreement, and
independently evaluate the diagnosis. Deterministic code controls only the safety
transition from accepted diagnosis to action recommendation.

## 7. Failure behavior

- Missing or unavailable source -> `REQUIRE_EVIDENCE`, no action.
- Failed or malformed read audit -> fail closed, no action.
- Unsupported or conflicting diagnosis -> no action.
- Selected investigator lacks complete read coverage -> no action.
- Evaluator rejection or incomplete validation -> `EVALUATOR_REJECTED`, no action.
- Short shipment -> `PROTECT`, no action.
- Already posted -> `RECEIPT_ALREADY_POSTED`, no action.
- Retryable diagnosis satisfying every deterministic gate -> recommendation only;
  execution still requires both human approvals.

## 8. Implementation scope

Expected focused changes:

- strict v5 schemas and public serializers;
- investigator, synthesis, and evaluator prompts/contexts;
- evidence coverage ledger and deterministic action policy;
- harness validation, assessment adapter, normalized trace, and Golden v2 metadata;
- scripted fixtures and targeted unit, adversarial, integration, and Golden tests;
- M4 spec/status documentation.

No UI, M5 monitoring, M6 AgentCore deployment, product-scope expansion, unrelated
refactor, or production data is in scope.

## 9. Verification loop

**Goal:** Prove one evidence-grounded real Strands diagnosis can safely reach the
existing human-gated recovery path without model-authored action authority.

**Input scope:** Synthetic fixtures, frozen synthetic knowledge corpus, v5 prompts,
current deterministic domain workflow, and the existing capped Nova Pro provider.

**Checks:**

- Ruff, mypy, full Python/JS tests;
- Golden v1 16/16 with all safety counters zero;
- Golden v2 safety and scripted proofs;
- deterministic byte-identical scripted runs;
- secret, local-path, and misleading-cloud-claim scan;
- `git diff --check`;
- independent architecture/code review;
- exactly one capped real-provider run only after every offline gate passes.

**Feedback budget:** One Luna implementation pass and at most one focused correction.
No repeated prompt-tuning or AWS retry loop.

**Records:** Contract version, prompt/schema/harness digests, audited reads, derived
knowledge citations, coverage ledger, policy outcome/reason, evaluator result, human
approvals, receipts/effects, and replayed final state.

**Stop conditions:**

- success: all offline gates, the single real-provider run, and independent final
  review pass;
- failure: a material real-provider or safety failure marks M4 `BLOCKED` and stops M5;
- human gate: only credentials/MFA, spending beyond the already approved promo cap,
  public/destructive action, or a new product-direction fork.

## 10. Acceptance

1. All model-authored action fields are absent and rejected if supplied.
2. Only the selected investigator's successful audited reads populate coverage.
3. The selected hypothesis maps one-to-one to its fixed investigator, that investigator
   returned the same hypothesis with `SUPPORTED`, and synthesis cannot upgrade or
   substitute a rejected or uncertain result.
4. Complete coverage alone never creates an action.
5. The deterministic policy recommends only restart for an accepted, supported,
   conflict-free retryable diagnosis.
6. Missing evidence, failed reads, tampering, dissent conflicts, evaluator rejection,
   short shipment, and duplicate posting produce no action.
7. Golden v2 contains zero forbidden grants/effects and reaches `CLOSED` only after
   both human approvals.
8. Offline gates and an independent implementation review pass.
9. One capped Nova Pro run passes all four profiles under unchanged request, token,
   timeout, and cost budgets.
10. The final independent Chief Architect returns `APPROVE_M4` before commit, push, or
   M5 progression.
