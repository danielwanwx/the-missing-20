# 0004: M5 Reread–Verification–Effect Closure

**Date:** 2026-08-27
**Status:** `REJECT_M5_CLOSURE_DESIGN`; bounded design correction exhausted

## Decision

M5 lifecycle validation must prove a closed chain for each controlled action:

`action → intent/grant/typed parameters → execution → before snapshot → receipt pre digest
→ exact effect → after snapshot → receipt post digest → verification → replay`.

The snapshot digest algorithm is exactly the one used by `ControlledExecutor` when it
creates `ExecutionReceipt`: SHA-256 of `EnterpriseSnapshot.model_dump_json()` bytes. A
different canonicalization is not equivalent.

The after snapshot must contain exactly one `BusinessEffect` whose `effect_id`,
`execution_id`, case, trace, effect type, source record, result record IDs, idempotency
key, and committed time match the bundle's referenced effect. The before snapshot must
not contain that effect. The post snapshot may contain prior actions' effects but may not
contain a second effect for the current execution.

Recomputing a reread's local digest or the unsigned bundle digest cannot repair a broken
relation to the executor-issued receipt or effect record.

## Scope

Only lifecycle validation, digest generation alignment, mutation tests, and necessary M5
records are in scope. Advisory/provider acceptance, UI direction, authorization policy,
quorum semantics, AWS, and product claims are unchanged. No provider call or new cost is
authorized; cumulative estimated cost remains `$0.1250496`.

## Acceptance

For every action:

1. before/after rereads match action identity, case/trace identity, and ordered phase;
2. reread `snapshot_digest` equals the executor-compatible digest of its snapshot;
3. before digest equals receipt `pre_state_digest` and after digest equals receipt
   `post_state_digest`;
4. receipt identity matches action execution, authorization, case, and trace;
5. before snapshot excludes the current effect; after snapshot contains exactly the
   referenced effect and no other effect for that execution;
6. referenced effect matches action/tool expectations and the verification receipt;
7. replay binds to the same action/execution/receipt and creates zero effects;
8. mutation of snapshot content, digest, effect membership/identity, receipt digest, or
   replay relation fails even after local and bundle rehashing;
9. complete/degraded/invalid browser paths and all existing gates remain green.

Case/version closure is exact: decision, intent, quorum grant, bridge grant, attempt,
execution policy, verification receipt, and replay must share the bundle case/trace and
the same action/tool chain. Decision, intent, and quorum grant must share the frozen case
version. Execution policy case version must equal the bridge grant's case version at the
execution gate. No coordinated version rewrite is accepted merely because inner digests,
signatures, or the bundle digest were recomputed.

One focused correction is permitted after independent implementation review. M6 starts
only after independent M5 approval.

## Terminal design gate

The first independent review identified case/version, exact effect/receipt/replay, and
cross-action closure gaps. The sole focused design correction resolved the effect,
receipt, replay, snapshot, and cross-action requirements, but the final review found one
remaining material ambiguity: the decision/intent/quorum-grant case version and the
bridge-grant/execution-policy case version are two unbound version groups.

`AuthorityBControlledExecutor` may legitimately advance case version through deterministic
preparation transitions before creating the bridge grant. The design did not freeze that
exact transition-derived relation. A coordinated bridge/policy version rewrite followed
by signature and bundle rehashing could therefore remain acceptable. Governance stops
this rebaseline before implementation. M5 remains unapproved; M6 and M7 did not start.
