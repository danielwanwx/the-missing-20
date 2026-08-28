# Milestone 4 Authority Rebaseline B

**Status:** `BLOCK_M4_REBASELINE_B` at the independent final gate
**Decision:** user-approved top-level authority rebaseline; this is not `agent-contract/v10`
**Scope:** M4 safety/usefulness proof and migration foundation for M5–M7

## 1. Loop contract

### Goal

Deliver a demonstrable closed loop in which Strands/Nova performs materially useful,
high-cost investigation and explanation, deterministic application code alone classifies
operational state and decides action eligibility, and two distinct humans authorize every
controlled effect. Model success, disagreement, malformed output, incomplete citations,
or provider failure must be observable but must never create a grant or veto an otherwise
valid deterministic operational decision.

### Input scope

- Current repository and synthetic Missing 20 scenarios.
- Terminal v6–v9 model-contract evidence as migration input, never as PASS evidence.
- Existing deterministic evidence integrity, source completeness, policy, authorization,
  execution verification, idempotency, and replay controls.
- Current cumulative estimated Nova cost `$0.1109336`; hard cap `$0.60`.

Employer code, incidents, runbooks, data, configuration, names, and provenance are
forbidden. No commit, push, public release, video upload, or Devpost submission is in
scope before the final user gate.

### Execute

1. Establish explicit advisory and operational authority models.
2. Run deterministic classification/policy from admitted authoritative evidence without
   consuming any model verdict.
3. Run the multi-agent investigation as a parallel, non-authoritative advisory branch.
4. Normalize any advisory outcome into an immutable status and public-safe report.
5. Join advisory and deterministic records only for display/audit; never for eligibility.
6. Continue the existing two-role approval, controlled execution, reread, verification,
   effect ledger, and replay path from the deterministic decision.
7. Prove safety independently from AI usefulness, then expose both in M5–M7.

### Feedback and stop rules

One Luna implementation and at most one focused material correction are allowed. One
bounded real Nova advisory proof is permitted after offline approval; it has no fallback,
probe, or retry batch. A provider/model failure becomes `DEGRADED` evidence and does not
fail deterministic safety. It can still fail the separate AI Usefulness Proof if no useful
real advisory trace exists. New authority boundaries stop for product direction.

Success requires both Safety Proof PASS and AI Usefulness Proof PASS, independent final
`APPROVE_M4_REBASELINE_B`, then automatic M5 entry. Human gates are login/MFA, projected
cumulative cost over `$0.60`, public/destructive/legal action, a new product fork, and the
final ready-to-be-judged decision.

## 2. Considered architectures

### A. Keep the evaluator as an operational hard gate

Rejected. v6–v9 show that provider formatting and semantic completeness can prevent a
safe deterministic decision even after mechanical metadata moves into the harness.

### B. Advisory intelligence plus deterministic authority — selected

Agents investigate and explain; deterministic code classifies facts and owns policy;
humans authorize effects. This preserves meaningful agent work and removes probabilistic
output from the operational trust root.

### C. Remove agents from the operational product

Rejected. It is safe but loses the competition's agentic differentiation, hypothesis
competition, evidence-gap discovery, knowledge retrieval, and incident-report value.

## 3. Authority matrix

| Capability | Strands/Nova | Deterministic application | Humans |
|---|---:|---:|---:|
| Competing hypotheses | propose | record/validate safe envelope | inspect |
| Knowledge retrieval | request allowlisted reads | enforce scope/provenance | inspect |
| Evidence-gap identification | propose | compute authoritative missing sources | inspect |
| Root-cause explanation/report | draft | label and persist advisory | inspect |
| Evidence identity/integrity | no authority | sole authority | inspect |
| Source completeness | no authority | sole authority | inspect |
| Operational state classification | no authority | sole authority | inspect |
| Action eligibility/policy | no authority | sole authority | inspect |
| Authorization grant | forbidden | issue only after exact quorum | two distinct roles |
| Execution/verification/replay | forbidden | sole authority | observe/escalate |

No model field, score, decision, citation, absence, exception, or timeout may appear in
the deterministic policy input type. Static types and tests must enforce this separation.

## 4. Component boundaries and data flow

```text
synthetic enterprise state
  -> deterministic detector
  -> admitted evidence + source availability + integrity digests
       |                                      |
       |                                      +-> advisory investigation branch
       |                                           investigators + knowledge reads
       |                                           synthesis/report preparation
       |                                           status + hypotheses + gaps
       |
       +-> deterministic classifier
             operational state + invariant results
             -> deterministic eligibility policy
             -> PENDING_APPROVAL / NO_ACTION / REQUIRE_EVIDENCE
             -> two distinct human approvals
             -> controlled executor
             -> authoritative reread + receipt/effect verification + replay

join for workspace/audit only:
  deterministic decision + advisory report/status + approval/execution timeline
```

The advisory branch may run before, during, or after classification. Completion order
cannot alter classification, policy, grants, effect parameters, or replay outcome.

## 5. Advisory state model

`AdvisoryInvestigation/v1` is application-owned and contains only public-safe synthetic
records:

- `advisory_id`, case/trace identity, provider/model and prompt/version digests;
- `status`: `NOT_REQUESTED`, `RUNNING`, `COMPLETE`, `PARTIAL`, `DEGRADED`, or
  `UNAVAILABLE`;
- bounded hypotheses with explanation, confidence band, supporting/contradicting admitted
  citation IDs, and investigator role;
- evidence gaps proposed by agents, plus separately computed deterministic gap matches;
- preserved disagreement/dissent;
- knowledge citations with corpus ID/version/digest and procedural-use label;
- incident-report summary;
- latency, requests, input/output tokens, estimated incremental/cumulative cost;
- stable error code and failed stage when degraded; never raw provider prose or secrets.

State transitions are monotonic:

```text
NOT_REQUESTED -> RUNNING -> COMPLETE
                         -> PARTIAL
                         -> DEGRADED
NOT_REQUESTED ----------> UNAVAILABLE
```

`COMPLETE` means all planned advisory stages returned structurally usable output.
`PARTIAL` means useful hypotheses/report content exists but one or more advisory checks
failed. `DEGRADED` means the provider path began but produced no publishable useful
report. `UNAVAILABLE` means it never began because provider/login/budget was unavailable.
None of these states grants or blocks operational action.

Malformed fields and unknown citations are omitted from the public advisory projection
and counted in `advisory_warnings`; they do not get repaired into operational facts.

## 6. Deterministic decision contract

`OperationalDecision/v1` is produced only from:

- immutable detector genesis and current authoritative rereads;
- admitted evidence identities, source types, case/trace IDs, digests, and read status;
- explicit business invariants and state-machine state;
- existing version, approval, idempotency, execution, and replay ledgers.

It contains `classification`, `eligibility`, `allowed_action`, reason codes, evidence
coverage, required approvals, case version, and decision digest. It contains no advisory
ID, hypothesis, confidence, model citation, model decision, or provider status.

Exact semantics:

1. Missing/unavailable authoritative evidence -> `REQUIRE_EVIDENCE`, no grant.
2. Genuine shortage -> `PROTECTED`, no receipt restart or invoice release.
3. Already posted -> `CLOSED`, no duplicate restart.
4. Retryable integration/document lock with all deterministic invariants satisfied ->
   `PENDING_APPROVAL` for `RESTART_RECEIPT_MESSAGE`.
5. Any stale version, tampered parameters, role mismatch, expired/replayed authorization,
   duplicate request, or failed postcondition -> no new effect.
6. Only two valid, distinct-role approvals over the exact decision/action digest can
   create a grant. Execution remains idempotent and must be verified by authoritative
   reread before `CLOSED`.

### Exact two-role authorization quorum

Architecture B replaces the legacy single-role `AuthorizationService.approve()` grant
issuance path for controlled effects. Both controlled tools use the same two-role quorum:

- exactly one `INTEGRATION_OPERATOR` attestation;
- exactly one `AP_APPROVER` attestation;
- two different trusted principal IDs;
- both attestations bind the same `authorization_intent_digest`.

The intent digest covers the immutable `OperationalDecision` digest, case and trace ID,
current case version, tool, complete typed parameters, admitted-evidence digest, and an
`expires_at` timestamp no more than five minutes after intent creation. The first valid
attestation persists `QUORUM_PENDING` only: it cannot create an `ActionGrant`, advance to
an authorized state, reserve an execution, or cause an enterprise write. The second valid
attestation creates one service-signed `QuorumActionGrant/v1` containing both approval
IDs, principal IDs, roles, decision/intent/evidence/parameter digests, version, and expiry.
The signer is application-owned; neither human approval alone is represented as a grant.

Duplicate principals, duplicate roles, cross-intent attestations, changed parameters,
changed evidence, changed case version, stale decision digest, expired intent, unknown
identity, or any rejection produce no grant. A `REJECTED` attestation closes the intent;
later approval cannot reopen it. Intent expiry or any case/evidence version change closes
it. After a grant is issued, existing reservation, signature, idempotency, postcondition,
effect-ledger, crash-recovery, and replay controls remain mandatory. Legacy one-role
grants remain readable only as historical artifacts and are rejected by the Authority-B
executor path.

The deterministic result is computed exactly once per case version and is byte-stable
under advisory permutations, omissions, failures, and completion timing.

## 7. Two-layer proof

### Safety Proof

Safety Proof is authoritative and must pass entirely offline:

- Golden v1 16/16 with all five safety counters zero;
- deterministic classifications and action eligibility for the four M4 profiles;
- metamorphic tests replacing advisory output with success, conflict, incomplete
  citations, malformed payload, timeout, exception, and absence while asserting identical
  `OperationalDecision`, grants, effects, and replay;
- two-role approval and effect verification remain mandatory;
- secret/path/private-provenance scans and byte-deterministic artifacts pass.

### AI Usefulness Proof

AI Usefulness Proof is non-authoritative and scored separately. For the main synthetic
case, a usable advisory report must show:

- at least two materially distinct competing hypotheses;
- cited support and contradiction or an explicit evidence gap per hypothesis;
- at least one allowlisted knowledge retrieval with procedural provenance;
- a likely root-cause explanation and concise incident-report summary;
- disagreement/uncertainty, latency, request/token/cost, and status visible;
- zero action, grant, approval, or execution authority in tools or output schema.

Offline scripted traces prove deterministic rendering and degraded behavior. One bounded
real Nova main-case proof is materially necessary to support the competition claim that
the advisory intelligence is genuinely model-produced. A real `PARTIAL` result may pass
only if it still satisfies every usefulness item above; `DEGRADED` or `UNAVAILABLE` does
not pass AI Usefulness Proof, while deterministic Safety Proof remains unaffected.

## 8. Failure and degraded behavior

- Model disagreement: preserve all hypotheses/dissent; deterministic decision unchanged.
- Unknown/incomplete citations: exclude them from trusted display, add warnings; decision
  unchanged.
- Malformed stage output: make no corrective provider request; mark `PARTIAL` or
  `DEGRADED` from the usable content already returned.
- Provider timeout/exception: persist redacted failure status and ledger usage; decision
  and approval flow continue.
- Missing advisory report in UI: show explicit unavailable/degraded panel alongside the
  complete deterministic decision and audit trail.
- Advisory conclusion conflicts with deterministic classification: display disagreement;
  deterministic classification controls policy and action.

## 9. Records and audit

Persist distinct immutable records:

1. `OperationalDecision/v1` and its source/invariant digest.
2. `AdvisoryInvestigation/v1`, advisory warnings, stage traces, usefulness score, and
   redacted provider status.
3. `DecisionWorkspaceSnapshot/v1`, a read-only join of operational decision, advisory,
   approval state, effects, and audit timeline.
4. Safety and AI usefulness manifests with independent PASS/FAIL status.
5. Exclusive provider attempt claim and redacted outcome, bound to prior cumulative cost.

Every UI/artifact/README/submission reference labels model output `ADVISORY — NOT AN
OPERATIONAL DECISION`. Cloud/runtime claims must be supported by saved evidence or marked
`NOT_PROVEN`.

## 10. Migration from v9

This rebaseline does not create `v10` and does not relax or reinterpret v9 as PASS.

- Preserve v6–v9 specs, claims, failures, costs, and terminal verdicts unchanged.
- Retain investigators, allowlisted read tools, knowledge provenance, concurrency, bounded
  budgets, traces, and useful relation-aware report content.
- Remove evaluator/synthesis acceptance from the path that creates an operational
  assessment or action recommendation.
- Introduce new top-level authority records and adapters; legacy v9 artifacts remain
  historical evidence only.
- Reuse existing deterministic detector, state machine, approval, authorization,
  executor, verification, and replay modules as the operational path.
- Golden v2 becomes a two-proof composition rather than a single model-gated promotion.

## 11. Frozen real-provider advisory proof

After independent offline implementation approval, exactly one real Nova proof may run
for the main synthetic profile only. It uses a distinct Authority-B claim/outcome path;
all v6–v9 provider artifacts remain immutable.

Frozen caps:

- prior cumulative estimated cost: `$0.1109336`;
- request cap: 12;
- input cap: 120,000 tokens;
- output cap: 18,000 tokens;
- per-request output cap: 1,500 tokens;
- frozen rate upper bound: `$0.1536000` incremental;
- maximum cumulative estimate: `$0.2645336`, below `$0.60`.

Pre-I/O reservations, one exclusive claim, no probe/fallback/retry batch, existing
restricted Nova Pro model, and redacted success/failure outcomes are mandatory. Each
planned investigator, synthesis, or report stage is invoked at most once. Tool-result
continuations declared by that stage are planned turns, but validator failure, malformed
structured output, timeout, or provider exception ends the stage without a corrective
model call. Provider failure records degraded behavior but cannot alter or invalidate
Safety Proof.

## 12. Exact tests and acceptance gates

1. Static/type test proves deterministic classifier/policy accepts no advisory type.
2. Advisory tools expose read-only evidence/knowledge capabilities only.
3. All advisory statuses and transitions serialize deterministically.
4. Metamorphic success/conflict/incomplete/malformed/timeout/absence cases produce the
   same operational decision, grants, effects, and replay.
5. Deterministic classification covers retryable, already-posted, shortage, and missing
   evidence profiles with exact reason codes.
6. Unknown citations and knowledge-as-current-state proof cannot enter trusted facts.
7. The first approval produces no grant/effect; only exact operator + AP-approver quorum
   creates a service-signed grant. Rejection, duplicate principal/role, cross-digest,
   expiry, stale version, idempotency, postcondition, crash recovery, and replay tests
   remain green.
8. Safety manifest and usefulness manifest cannot substitute for each other.
9. Provider claim is exclusive; historical claims/outcomes are not overwritten; cost
   reservation stays below both incremental and cumulative caps.
10. `make check`, Golden v1, Golden v2 two-proof composition, deterministic artifact
    replay, provider-shaped offline test, secret/path/private-provenance/misleading-cloud
    scans, and `git diff --check` pass.

M4 Authority B acceptance requires Safety Proof PASS, AI Usefulness Proof PASS, a
redacted bounded real advisory trace or useful PARTIAL trace, and independent
`APPROVE_M4_REBASELINE_B`. Only then may M5 start.

## 13. M5–M7 handoff contract

- M5 Decision Workspace displays incident state, hypotheses, evidence/gaps, confidence,
  disagreement, latency/cost/status, deterministic decision, approval state, and audit
  timeline with unmistakable authority labels; browser E2E covers complete and degraded
  advisory paths.
- M6 proves the minimum credible AWS/AgentCore advisory runtime with no write authority;
  unproved stretch claims are removed or labeled `NOT_PROVEN`.
- M7 produces the clean-state five-minute flow: detection -> advisory investigation ->
  deterministic decision -> human approvals -> controlled recovery -> verification and
  replay, plus submission audit and known limitations. Public release remains gated.

## 14. Terminal M4 evidence

The implementation passed its independent gate after the sole focused correction. The
post-attempt offline evidence remains green: 476 Python tests and 1 JavaScript test,
Golden v1 16/16 with all five safety counters zero, deterministic Safety Proof PASS,
scripted Strands proof PASS, and `git diff --check` PASS.

The exclusive real Nova Pro advisory attempt was then consumed once and ended
`DEGRADED` with `ADVISORY_PROVIDER_FAILURE`. It used 6 requests, 11,073 input tokens,
1,643 output tokens, and an estimated `$0.014116` incremental cost, for a cumulative
estimate of `$0.1250496`. The real AI Usefulness Proof is `FAIL`; Golden v2 is therefore
`NOT_READY`. No retry, fallback, probe, corrective provider batch, or further mechanical
patch cycle is authorized.

The new independent final Chief Architect returned `BLOCK_M4_REBASELINE_B`: deterministic
safety is proven, but the design's separate real AI Usefulness acceptance requirement is
not. Automatic M5 progression is forbidden. Continuing requires a material architecture
or product decision; it cannot be treated as another schema/version patch.
