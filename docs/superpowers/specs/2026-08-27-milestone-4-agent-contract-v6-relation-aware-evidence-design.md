# Milestone 4 Agent Contract v6 Relation-Aware Evidence Fork

**Status:** Terminally `BLOCK_M4` at the sole v6 real-provider acceptance run
**Scope:** M4 evidence semantics only; no M5/M6 work, AWS run, spending, commit, or push
**Supersedes for future work:** The terminally blocked v5 contract, without reclassifying its failed real-provider result

## Terminal gate result, 2026-08-27

The independently approved v6 offline implementation passed Ruff, mypy, 418 Python
tests, one JavaScript test, Golden v1 with 16/16 cases and all five safety counters at
zero, Golden v2 scripted and safety checks, deterministic replay checks, artifact
hygiene scans, and `git diff --check`.

The sole authorized v6 Nova Pro batch then exercised the first real product profile and
failed at the synthesis validator with `unsupported synthesis version`. The redacted
`agent-failure/v2` manifest records the first profile, `synthesis` stage, 8 requests,
20,782 input tokens, 2,885 output tokens, and estimated cost `$0.0258576`, within the
40-request, 400,000-input-token, 80,000-output-token, and `$0.60` caps. No promotable
Bedrock smoke artifact was created.

The independent final Chief Architect verdict is `BLOCK_M4`. The model/validator/product
output failure consumed the only provider attempt. No retry, fallback, compatibility
probe, prompt tuning, code change, commit, push, or M5/M6 progression is authorized.
Only a separately authorized product-direction fork may reopen work.

## 1. Decision context

The sole authorized `agent-contract/v5` Nova Pro run failed at the investigator
validator with:

`supporting and contradicting evidence overlap`

The failure is deterministic and fail-closed. In v5, every evidence ID cited by any
factual claim is automatically projected into `supporting_evidence_ids`, while a second
top-level field records `contradicting_evidence_ids`. The validator requires those
record-ID sets to be disjoint. One authoritative record can contain multiple facts with
different implications for a hypothesis, so record-level polarity cannot faithfully
represent mixed evidence. The prompts also require agents to cite factual claims and
preserve conflicts, making the contract internally hostile to a legitimate model
response.

The failed output was not persisted because the smoke artifact is written atomically
only after all profiles pass, and the investigators run concurrently. The available
evidence therefore establishes the failing stage and invariant but not the exact role,
profile, or complete Nova payload. v6 must not invent those missing details.

## 2. Product fork

Adopt claim-level evidence relations while preserving the existing product outcome:
agents interpret competing explanations, deterministic application policy alone decides
action eligibility, and execution still requires two independent human approvals.

`AgentClaim` gains exactly one relation:

- `SUPPORTS_HYPOTHESIS`
- `CONTRADICTS_HYPOTHESIS`
- `CONTEXT_ONLY`

Each claim continues to contain a stable claim ID, a concise statement, and one or more
exact admitted evidence IDs. The relation describes the claim's implication for the
fixed hypothesis; it does not label an entire evidence record. The same evidence ID may
therefore appear in different claims with different relations when the cited record
contains multiple relevant facts.

The following model-authored fields are removed from investigator and synthesis output:

- `contradicting_evidence_ids`
- `supporting_evidence_ids` (already forbidden in v5)
- all action recommendation or authorization fields (already forbidden in v5)

Support, contradiction, and context projections are application-derived from validated
claims. Models cannot author a separate aggregate polarity or action result.

## 3. Contract and deterministic validation

### Investigator

Every investigator remains bound one-to-one to its fixed hypothesis and must read every
available authoritative record before returning `SUPPORTED`. Every current-state claim
must cite successfully read, admitted evidence. Knowledge remains procedural context and
cannot be cited as current-state proof.

Validation requires:

1. every claim relation is a closed enum value;
2. claim IDs are unique within the result;
3. every cited ID is admitted for the same case and trace, digest-valid, and present in
   that investigator's successful read audit;
4. `SUPPORTED` contains at least one supporting claim, no unavailable authoritative
   source, and no unresolved contradicting claim;
5. `REJECTED` cannot contain an action recommendation and may contain supporting,
   contradicting, or contextual claims as an honest evidence record;
6. `NEEDS_EVIDENCE` is allowed only when detector-owned source availability reports an
   unavailable authoritative source.

A record ID appearing in claims of different relations is valid. A duplicated claim ID,
uncited claim, unknown relation, unadmitted citation, unread citation, or integrity
failure remains invalid.

### Synthesis

Synthesis may select only the fixed hypothesis whose mapped investigator returned that
hypothesis as `SUPPORTED`. It cannot upgrade, substitute, or relabel another result.
Synthesis claims use the same relation-aware contract. The application validates every
synthesis claim against the admitted catalog and preserves all investigator outputs as
an application-owned dissent projection; synthesis does not re-author investigator
evidence sets.

The deterministic dissent projection records, for each investigator, its fixed role,
hypothesis, conclusion, confidence, and sorted claim IDs grouped by relation. This
replaces the v5 model-authored `PreservedDissent.evidence_ids` union, which discarded
claim meaning.

### Evaluator

The independent evaluator validates claim IDs, evidence IDs, required sources, and
failed invariants. `ACCEPT` still requires all selected claims and all admitted evidence
to be validated, all required source types to be listed, and no failed invariant. It
cannot recommend or authorize an action.

## 4. Conflict and action policy

`ActionRecommendationPolicy/v2` remains pure application code and may recommend
`RESTART_RECEIPT_MESSAGE` only when all existing v5 gates pass plus these v6 rules:

1. the selected retryable investigator and synthesis contain supporting claims;
2. neither contains an unresolved `CONTRADICTS_HYPOTHESIS` claim;
3. all claim relations and citations passed deterministic validation;
4. the selected investigator's coverage ledger is complete;
5. the evaluator accepted every selected claim and authoritative evidence record.

The presence of mixed-relation claims is representable, but it never silently becomes
actionable. Any selected-path contradiction produces no action with stable reason
`UNRESOLVED_CONTRADICTING_CLAIM`. Context-only claims neither prove nor contradict a
hypothesis and cannot satisfy support coverage on their own.

Short shipment, already posted, unavailable evidence, tampering, wrong role, synthesis
upgrade, incomplete reads, evaluator rejection, stale approval, and duplicate execution
retain their existing fail-closed outcomes.

## 5. Evidence coverage and public trace

The application-owned `EvidenceCoverageLedger` remains immutable and selected-
investigator scoped. Its next version records only portable metadata:

- selected role and hypothesis;
- admitted evidence IDs, source types, and content digests;
- successful selected-investigator reads;
- validated claim IDs grouped by relation;
- evaluator validation coverage;
- unresolved-conflict flag;
- policy version and stable outcome reason.

No raw evidence content, prompt secrets, credentials, local absolute paths, knowledge
excerpts, or hidden reasoning enters the public artifact. Failed real-provider runs must
write a redacted failure manifest before returning, including profile key, assigned
stage/role, validator code, request/token totals, and no model prose. This closes the v5
observability gap without weakening atomic PASS promotion.

## 6. Minimal implementation scope

Expected focused changes only:

- v6 claim relation enum and strict schemas;
- investigator and synthesis prompts/contexts;
- deterministic claim projections, dissent projection, and validators;
- `EvidenceCoverageLedger/v2` and `ActionRecommendationPolicy/v2`;
- redacted failure-manifest capture outside the promotable smoke artifact;
- scripted fixtures and targeted unit, adversarial, integration, and Golden v2 tests;
- M4 status and version documentation.

No UI, M5 monitoring, M6/AgentCore deployment, provider change, new agent permission,
production data, unrelated refactor, or product-story expansion is in scope.

## 7. Verification and Golden acceptance

Offline verification must include:

- strict rejection of legacy polarity and action fields;
- deterministic projection of support, contradiction, and context from claims;
- a regression where one evidence record supports one claim and contradicts another;
- a regression proving the mixed record is representable but cannot create an action
  while a selected-path contradiction remains unresolved;
- selected retryable, genuine-shortage, already-posted, and missing-evidence profiles;
- wrong role, synthesis upgrade, unread/unadmitted citation, tampering, evaluator
  omission/rejection, stale approval, and duplicate execution attacks;
- byte-identical scripted artifacts;
- `make check`, Golden v1 16/16 with every safety counter zero, Golden v2 scripted and
  safety PASS, secret/path/claim scan, and `git diff --check`.

Exactly one new real-provider run may occur only after a separately authorized cost gate,
all offline checks pass, and the independent implementation review approves. A model,
validator, or product-output failure consumes that run. Only a proven infrastructure
failure before the product path is exercised can qualify for separate retry authority.

M4 passes only if the capped real-provider proof passes all four profiles and a final
independent Chief Architect returns `APPROVE_M4`. Until then there is no commit, push, or
M5 progression.

## 8. Bounded governance

1. The primary orchestrator owns status, diff, tests, cost, evidence, and milestone
   acceptance throughout.
2. An independent Chief Architect reviews this design only for material blockers against
   the spec, competition requirements, Golden cases, safety boundary, and real end-to-end
   data flow.
3. Luna performs the implementation after design approval; the implementer cannot
   approve its own work.
4. One independent implementation gate follows primary inspection and offline tests.
5. At most one focused correction is allowed for a material defect. A repeated material
   failure stops and is recorded; optional polish cannot trigger another loop.
6. User involvement is reserved for a new product-direction fork, unavoidable account or
   cost/public/destructive gate, or final ready-to-be-judged product critique.

## 9. Design acceptance criteria

1. Evidence polarity is claim-level, not record-ID-level.
2. The same admitted record may be cited by claims with different relations without a
   schema or validator failure.
3. A selected-path contradicting claim always prevents an action recommendation.
4. Model-authored aggregate support, contradiction, missing-source, knowledge-provenance,
   and action fields are forbidden.
5. Application-owned projections preserve every investigator's claim meaning and dissent.
6. Existing evidence integrity, complete-read, fixed-role, coverage, evaluator, approval,
   execution, verification, and replay gates remain fail closed.
7. Failed real-provider attempts leave a redacted diagnostic and cost manifest but never
   a promotable PASS artifact.
8. The existing four-profile end-to-end outcome and Golden safety counters remain
   unchanged.
