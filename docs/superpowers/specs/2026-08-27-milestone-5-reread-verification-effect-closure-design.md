# Milestone 5 Reread–Verification–Effect Closure

**Decision:** `../../decisions/0004-m5-reread-verification-effect-closure.md`
**Status:** `REJECT_M5_CLOSURE_DESIGN`; one focused design correction exhausted

The terminal blocker is the missing exact transition-derived relation between the
decision/intent/quorum-grant case version and the later bridge-grant/execution-policy case
version after deterministic preparation transitions. No implementation was authorized.

## Loop contract

**Goal:** make every displayed fresh-read, effect, verification, and replay claim derive
from one cryptographically and referentially closed executor record chain.

**Input:** current Authority-B lifecycle generator/bundle, `ControlledExecutor` receipt
digest semantics, synthetic enterprise snapshots, and existing M5 tests/artifacts.

**Execute:** align snapshot digest generation with executor receipts; add closure
validation; add coordinated mutation tests; rebuild artifacts and browser evidence.

**Checks:** focused closure matrix, full tests, Golden v1/v2, lifecycle provenance,
complete/degraded operational equality, invalid fail-closed Chrome E2E, secret/remote
resource scans, and diff check.

**Feedback:** at most one focused correction. A second material failure stops.

**Records:** exact validation rules, mutation results, test totals, artifact digest,
browser manifest, and independent verdicts.

**Stop:** `APPROVE_M5_CLOSURE` permits M6; otherwise stop for material direction.

## Validation algorithm

For each `LifecycleAction`, resolve all referenced records by unique ID. Validate the
existing authority and execution closure, then:

1. recompute before and after snapshot digests using
   `sha256(snapshot.model_dump_json().encode()).hexdigest()`;
2. require equality with each reread's stored digest;
3. require the same values in the `ExecutionReceipt.pre_state_digest` and
   `post_state_digest` fields;
4. require receipt authorization/case/trace/execution identity closure;
5. require no current `effect_id` or current `execution_id` effect in the before snapshot;
6. locate current-execution effects in the after snapshot and require exactly one,
   byte-equivalent to the referenced `BusinessEffect` model;
7. require the following complete authority chain: decision, intent, quorum grant,
   bridge grant, attempt, execution policy, receipt, and replay all use the bundle
   case/trace and action tool; decision/intent/quorum grant share the exact case version;
   policy case version equals the bridge grant case version; typed parameters and their
   digest are identical across intent, quorum grant, bridge, attempt canonical parameters,
   and policy parameters digest;
8. apply an exact per-tool effect mapping:
   - `restart_receipt_message` requires `RECEIPT_RESTART`, source record equal to typed
     `message_id`, result IDs equal the newly created material-document IDs, receipt
     `material_document_ids` contain those exact result IDs, and receipt postconditions
     include and pass message identity/consumption, exact one source document, quantity,
     context, authority, and one-effect checks;
   - `release_invoice` requires `INVOICE_RELEASE`, source and sole result record equal the
     typed `invoice_id`, after invoice `released_by_execution_id` equal the execution,
     and receipt postconditions include and pass invoice release/link, receipt complete,
     hold cleared, context, authority, and one-effect checks;
   - in both cases effect case/trace/execution/idempotency equal the action/attempt,
     `committed_at == receipt.executed_at`, and the after snapshot contains that exact
     model once;
9. require replay `action_id`, execution ID, and idempotency key equal the action;
   `replay.receipt == verification`, `replay.receipt_digest` equal the model digest of
   that verification, `effect_delta == 0`, and replay before/after counts equal the full
   after-snapshot effect-ledger size;
10. for this generated two-action lifecycle, unconditionally require action N after
    snapshot model equality and executor-compatible digest equality with action N+1
    before snapshot, and require unique action, execution, effect, intent, and grant IDs.

Any failure raises a stable validation error; the workspace catches it and returns only
`UNAVAILABLE`, without operational panels.

## Mutation matrix

Tests start from the genuine generated artifact, mutate one relation, recompute every
attacker-controlled local and whole-bundle digest, and still require rejection:

- before/after business fact mutation;
- reread snapshot digest replacement;
- receipt pre/post digest replacement;
- effect removed, duplicated, moved to before, or replaced in after;
- effect ID/execution/case/trace/type/source/result/idempotency mutation;
- receipt execution/authorization/case/trace mutation;
- coordinated decision/intent/grant/bridge/policy case-version mutation with recomputed
  self-digests/signatures and bundle digest;
- replay action/execution/receipt digest/effect delta mutation;
- cross-action after/before continuity mutation.

## Non-goals

No advisory/provider change, new UI feature, new authorization behavior, cloud call,
spending, commit/push, publication, video, or submission.
