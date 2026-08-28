# 0005: M5 Preparation-Transition Version Chain

**Date:** 2026-08-27
**Status:** accepted; `APPROVE_M5`

## Decision

The M5 lifecycle bundle will persist the actual `CaseEvent` records created by
`AuthorityBControlledExecutor` preparation transitions and bind their exact version chain
between each quorum grant and its bridge/execution policy.

For the frozen synthetic two-action lifecycle:

- receipt restart begins in `INVESTIGATING` and requires exactly
  `RECEIPT_RESTART_RECOMMENDED → RECEIPT_APPROVAL_REQUESTED →
  RECEIPT_APPROVAL_ACCEPTED`;
- invoice release begins in `RECEIPT_VERIFIED` and requires exactly
  `INVOICE_APPROVAL_REQUESTED → INVOICE_APPROVAL_ACCEPTED`.

Each event advances one version. The first event's `prior_version` equals the quorum
grant/intent/decision case version; adjacent prior/new versions and statuses must join;
the final event's `new_version` equals the bridge grant and execution-policy case version.
No missing, extra, reordered, duplicated, or different event is accepted.

Every persisted preparation record includes action/intent identity, event ID and type,
prior/new version, prior/new status, idempotency key, payload digest, and an event digest
computed over the full canonical `CaseEvent` JSON. The event must also exist exactly once
in the bundle's append-only case-event collection.

This version chain is validated together with the already approved intent/grant,
parameters, attempt, reread, effect, receipt, verification, and replay closure. Re-signing
or rehashing attacker-controlled artifacts cannot replace the fixed event sequence and
state-machine-derived versions.

## Scope and acceptance

Only preparation-event persistence, version-chain validation, combined integrity tests,
and artifact regeneration are allowed. UI direction, advisory/provider acceptance,
authorization policy, AWS, and cost are unchanged.

Acceptance requires invalid offset, missing, extra, reordered, substituted, duplicated,
cross-intent, synchronized bridge/policy rewrite, event-digest rewrite, and whole-bundle
rehash attacks to fail closed. Full M4/M5 offline, provenance, and browser gates remain
green. No AWS/provider call or new spending is authorized; cumulative estimate remains
`$0.1250496`.

## Final gate record

- Independent design gate: `APPROVE_M5_TRANSITION_CLOSURE_DESIGN`.
- The one allowed focused correction closed a reproduced coordinated re-sign/rehash
  attack by binding intent, attestations, quorum grant, bridge grant, preparation events,
  execution attempt, policy, receipt/effect, rereads, and replay to one unexpired
  authorization window.
- Primary final gates: Ruff PASS; mypy PASS across 102 source files; 499 Python tests
  PASS with 1 managed-sandbox loopback skip; 1 JavaScript test PASS; Golden v1 16/16
  with all five safety counters zero; Golden v2
  `PASS_WITH_DISCLOSED_AI_DEGRADATION`; lifecycle/workspace artifact build PASS;
  complete/degraded/invalid headless-Chrome smoke PASS; `git diff --check` PASS.
- The independent implementation reviewer reran the original expired-grant attack and
  confirmed it now fails closed. Final verdict: `APPROVE_M5`.
