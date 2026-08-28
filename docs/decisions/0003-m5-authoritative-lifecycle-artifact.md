# 0003: M5 Authoritative Lifecycle Artifact

**Date:** 2026-08-27
**Status:** `REJECT_M5_REBASELINED_IMPLEMENTATION`; correction budget exhausted

The independent design gate approved this decision. The bounded implementation produced
a real local Authority-B lifecycle and passed offline/browser gates, but the final
implementation gate found that reread closure was not fail-closed: reread snapshots were
not bound to verification pre/post-state digests or to the referenced effect in the after
snapshot. Because the milestone's sole focused correction had already been used, M5
stopped without another patch. M6 and M7 are not authorized to start.

## Decision

The Decision Workspace will be driven only by a newly executed, synthetic Authority-B
lifecycle artifact. The legacy `artifacts/demo/main-case.json` approval projection is
forbidden as an M5 authority source.

The lifecycle generator executes the current repository-backed Authority-B path against
fresh temporary synthetic stores. Each controlled action has its own deterministic
decision, case version, typed parameters, intent digest, two distinct role attestations,
service-signed quorum grant, execution reservation, authoritative rereads, effect,
postcondition verification, and replay result. If the full receipt-to-invoice story uses
two controlled actions, it uses two separate intents and two separate quorum grants; the
records are never merged.

## Fail-closed rule

The workspace projector accepts a lifecycle bundle only when every displayed operational
claim is backed by an exact persisted record and all identity/digest/reference relations
validate. Missing or inconsistent records produce a typed `UNAVAILABLE` workspace with
reason codes. They never produce fallback principals, approvals, quorum, effects,
verification, replay, or final state.

## Authority separation

Advisory records may add hypotheses, gaps, explanation, and degradation status. They
cannot change lifecycle validation or supply a missing operational field. Complete
scripted and degraded-real advisory modes join the same byte-identical validated
operational lifecycle projection.

## Acceptance change

M5 passes only when:

1. a clean local runner creates the lifecycle bundle through the actual
   `QuorumAuthorizationService` and `AuthorityBControlledExecutor` path;
2. each action's intent, attestations, grant, parameters, case version, effect,
   verification, and replay references remain distinct and internally consistent;
3. zero effects exist before the second attestation for each intent;
4. replay creates zero additional effects;
5. removing or mutating any required lifecycle record makes the workspace unavailable;
6. complete and degraded advisory modes render the same operational truth;
7. browser E2E proves both valid modes and a fail-closed invalid mode;
8. all M4 safety/evidence classifications remain unchanged.

No AWS/provider call, new spending, commit, push, publication, video, or Devpost action
is authorized. Current cumulative estimated AWS cost remains `$0.1250496`.
