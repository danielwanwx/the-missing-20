# Milestone 5 Decision Workspace Implementation Plan

**Design:** `../specs/2026-08-27-milestone-5-decision-workspace-design.md`
**Status:** `APPROVE_M5`; M6 authorized

1. Add typed workspace-demo artifact composition from existing synthetic and frozen
   evidence records, with canonical digest and fail-closed validation.
2. Add read-only local HTTP routes and static responsive workspace assets.
3. Render complete scripted and real-degraded advisory modes with immutable authority and
   evidence labels, deterministic policy, two-role quorum, execution, verification, and
   replay panels.
4. Add unit/contract/security tests plus headless-Chrome E2E for both modes and a redacted
   smoke manifest.
5. Run focused tests, full `make check`, Golden v1/v2, browser smoke, provenance/secret/
   remote-resource scan, and `git diff --check`.
6. Obtain independent implementation and M5 milestone gates; permit at most one focused
   material correction.

No AWS/network/provider call, commit, push, public action, or unrelated refactor.

## Gate record

- Independent design gate: `APPROVE_M5_DESIGN`.
- Primary offline gates after the bounded browser-smoke correction: Ruff/mypy PASS;
  482 Python tests PASS with 1 managed-sandbox loopback skip; 1 JavaScript test PASS;
  Golden v1 16/16 with all five safety counters zero; Golden v2
  `PASS_WITH_DISCLOSED_AI_DEGRADATION`; complete/degraded artifact builds PASS;
  local headless-Chrome smoke PASS for both modes; `git diff --check` PASS.
- Independent implementation gate: `REJECT_M5_IMPLEMENTATION`.

Material blockers:

1. The workspace collapses two legacy sequential approvals for different actions, case
   versions, and parameter digests into one Authority-B exact two-role quorum over a
   claimed shared intent. That is not supported by the source artifact and violates the
   accepted authorization semantics.
2. Missing lifecycle inputs do not fail closed. The projection supplies fallback
   principals/approval IDs, approved/granted state, verification/replay PASS, zero replay
   effects, and CLOSED state rather than requiring authoritative persisted records.

The prior focused correction was consumed fixing the headless-Chrome smoke termination.
Governance therefore forbids another implementation correction in this milestone turn.
M5 is not approved; M6 and M7 may not start. Continuing requires a new material decision
about how to source an honest Authority-B lifecycle demonstration.

## Approved rebaseline

Decision 0003 and the authoritative-lifecycle rebaseline spec supersede the rejected
projection approach. The new bounded implementation must generate its source bundle by
actually running Authority-B quorum and controlled execution, validate every lifecycle
claim fail closed, and prove valid complete/degraded plus invalid/unavailable browser
modes. This begins a new one-correction budget authorized by the user.

## Focused correction evidence

- Complete, degraded, and invalid browser smoke now render the persisted replay proof;
  invalid mode explicitly renders `UNAVAILABLE` and hides operational panels.
- Lifecycle mutation/deletion coverage now exercises every required record category:
  intent, attestation, grant, signature, version, parameters, attempt, effect,
  verification, replay, and final state. Each candidate fails bundle validation and
  projects as `UNAVAILABLE` with no operational payload.
- Focused verification: 24 tests collected, 23 passed, 1 managed-sandbox loopback skip;
  Ruff, JavaScript syntax, and `git diff --check` passed; local headless-Chrome smoke
  passed complete + degraded + invalid. No AWS/provider/network call was made.

## Rebaseline terminal gate

- Independent rebaseline design gate: `APPROVE_M5_REBASELINE_DESIGN`.
- Primary final evidence: Ruff/mypy PASS; 485 Python tests PASS with 1 managed-sandbox
  loopback skip; 1 JavaScript test PASS; Golden v1 16/16 with all five counters zero;
  Golden v2 `PASS_WITH_DISCLOSED_AI_DEGRADATION`; lifecycle artifact and complete/
  degraded workspace builds PASS; headless Chrome complete/degraded/invalid PASS;
  `git diff --check` PASS.
- Independent implementation gate: `REJECT_M5_REBASELINED_IMPLEMENTATION`.

Material blocker: lifecycle validation checks reread identity and phase but does not bind
the before/after snapshot digests to the verification receipt's exact pre/post-state
digests, nor prove the referenced effect exists in the after snapshot. A coordinated
reread mutation with recomputed local and bundle digests can therefore be accepted while
the workspace displays fresh-read PASS. The mutation matrix omitted this linkage case.

The sole focused correction was already consumed. Governance forbids another patch in
this milestone turn. M5 remains unapproved; M6 and M7 did not start. Continuing requires
a new material authorization to rebaseline reread/verification/effect closure.

## Accepted closure and final M5 gate

Decisions 0004 and 0005 supersede the earlier terminal text above. The accepted
implementation binds authoritative before/after snapshots, verification receipt,
effect ledger, replay, and the exact state-machine preparation/version chain. Its one
focused correction also binds the complete lifecycle chronology to the unexpired intent,
quorum-grant, and bridge-grant authorization window.

Final evidence: Ruff PASS; mypy PASS across 102 source files; 499 Python tests PASS with
1 managed-sandbox loopback skip; 1 JavaScript test PASS; Golden v1 16/16 with all safety
counters zero; Golden v2 `PASS_WITH_DISCLOSED_AI_DEGRADATION`; lifecycle and complete/
degraded workspace builds PASS; headless Chrome complete/degraded/invalid PASS; and
`git diff --check` PASS. The independent reviewer reproduced the prior expired-grant
attack and confirmed it now fails closed. Final verdict: `APPROVE_M5`.
