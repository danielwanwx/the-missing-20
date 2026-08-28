# Milestone 5 Preparation-Transition Version Chain

**Decision:** `../../decisions/0005-m5-preparation-transition-version-chain.md`
**Status:** proposed for independent design gate

## Loop contract

**Goal:** close the only remaining M5 integrity gap by proving the exact state-machine
event chain from quorum-grant version to bridge/policy version, integrated with the full
reread/effect/receipt/replay closure.

**Input:** actual case events emitted by the clean synthetic lifecycle runner, existing
Authority-B action records, decision 0004 closure rules, and current M5 artifacts/tests.

**Execute:** persist typed preparation records and all referenced case events; validate
the fixed per-action chain and combined closure; add coordinated attack tests; rebuild
workspace/browser artifacts.

**Check:** reproducible integrity attacks only, full tests, Golden v1/v2, lifecycle and
artifact provenance, complete/degraded/invalid Chrome E2E, and diff check.

**Feedback:** one focused implementation correction. Reviewers must not block on optional
formal hardening; only a reproducible defect that can falsely claim authorization,
execution, or verification success is material.

**Stop:** `APPROVE_M5`; otherwise report one root-cause-level combined solution rather
than another single-field fork.

## Records

Add `LifecyclePreparationTransition/v1`:

- `action_id`, `intent_id`, and `event_id`;
- exact `TransitionEvent`;
- `before_version`, `after_version`;
- `before_status`, `after_status`;
- `idempotency_key`, `payload_digest`, `event_digest`.

The bundle also persists the referenced `CaseEvent` models. The preparation projection is
derived from those events; it is not independently trusted. `event_digest` is SHA-256 of
canonical JSON for the complete event model.

Each `LifecycleAction` references an ordered tuple of preparation transition IDs.

## Exact chain validation

For each action:

1. decision, intent, and quorum grant share case, trace, tool, decision digest, evidence
   digest, typed parameters, and case version;
2. every referenced preparation transition resolves to one unique persisted `CaseEvent`,
   and every field plus full-event digest matches;
3. preparation IDs are unique globally and the action references all and only the events
   whose idempotency keys use `authority-b:{intent_id}:`;
4. first `before_version == grant.case_version`; every next before version/status equals
   the previous after version/status; each after version is before + 1;
5. exact generated sequences are:
   - receipt: recommended, request, accept, from `INVESTIGATING` to
     `RECEIPT_ACTION_AUTHORIZED`;
   - invoice: request, accept, from `RECEIPT_VERIFIED` to
     `INVOICE_ACTION_AUTHORIZED`;
6. final `after_version == bridge.case_version == execution policy.case_version`;
7. the immediately following execution-start event uses that version, same case/trace/
   action namespace, and advances it once; attempt/policy/receipt then close to that
   execution identity;
8. the complete version/event proof is validated before reread/effect/receipt/replay
   closure and before any workspace operational PASS projection.

The validator rejects unrelated case events in the preparation subset but preserves them
in the full audit collection.

## Combined mutation matrix

Tests mutate the genuine artifact and recompute all attacker-controlled digests/signatures:

- bridge and policy version with valid or invalid offsets;
- missing, extra, reordered, duplicated, substituted, or cross-intent preparation event;
- event before/after version or status;
- idempotency, payload, or full-event digest;
- execution-start discontinuity;
- coordinated transition/bridge/policy rewrite;
- every snapshot/receipt/effect/replay relation from decision 0004.

Every case must make lifecycle load fail and workspace return `UNAVAILABLE` without
authorization/execution/verification claims.

## Non-goals

No UI redesign, agent/provider work, cloud call, new cost, policy change, production data,
commit/push, publication, video, or submission.
