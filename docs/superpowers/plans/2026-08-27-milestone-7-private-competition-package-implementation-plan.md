# Milestone 7 Private Competition Package Implementation Plan

**Design:** [`2026-08-27-milestone-7-private-competition-package-design.md`](../specs/2026-08-27-milestone-7-private-competition-package-design.md)
**Status:** `READY_TO_BE_JUDGED_PRIVATE`; final human product gate pending

1. Freeze the seven-step, five-minute judge story and the three-class evidence matrix
   in the demo and submission documentation.
2. Add a typed, canonical `M7PrivateCompetitionAudit/v1` builder/loader that validates
   M5 lifecycle/workspace, M6 existing-evidence proof, browser smoke, source files,
   advisory boundaries, and readiness state.
3. Add `scripts/audit_competition_package.py` with safe `--write` and default
   fail-closed `--check` modes. The script must never import an AWS client or make a
   network call.
4. Add `scripts/run_judge_demo.py`; its default check regenerates the deterministic
   lifecycle and workspaces in a temporary clean state before comparing the persisted
   audit and printing the seven-step run card.
5. Add mutation tests for re-signed audit status/readiness/evidence changes, source
   deletion/change, bad timeline boundaries, unsafe claims, stale workspace proof, and
   clean-state regeneration.
6. Expose only offline `m7-audit` and `judge-demo` Make targets and update README with
   the private boundary and truthful evidence disclosures.
7. Run focused M7 tests, full offline checks, Golden v1/v2, lifecycle/workspace/M6
   builds, browser smoke where available, package audit, and `git diff --check`.

## Gate record

- Independent design gate: `APPROVE_M7_DESIGN` is required before implementation.
- Implementation gate: independent review checks only material correctness, package
  provenance, five-minute story, truthful evidence boundaries, fail-closed mutation
  behavior, and absence of external side effects.
- One focused material correction is allowed. A second reproducible material defect
  stops M7; optional polish remains deferred.

## Explicit non-goals

No AWS/provider/network call, new spend, AgentCore deployment, credential handling,
operational behavior change, active UI control, public release, commit, push, video,
or Devpost submission.

## Final independent gate

- `make check`: Ruff/mypy PASS across 110 source files; 529 Python tests PASS with
  1 managed-sandbox loopback skip; 1 JavaScript test PASS.
- Golden v1: 16/16 PASS with all five safety counters zero. Golden v2:
  `PASS_WITH_DISCLOSED_AI_DEGRADATION`.
- M5 lifecycle/workspace, M6 existing-evidence proof, and complete/degraded/invalid
  local browser smoke: PASS.
- M7 private audit and clean-state judge demo: PASS with seven contiguous steps ending
  at exactly 5:00; final audit digest
  `2fc488b2e2e2119efbf81e8176f37684986238369a4012efe42cf709edf4689a`.
- New provider/AWS calls: 0. New cost: `$0`. Cumulative estimate remains `$0.1250496`.
- Independent competition verdict: `READY_TO_BE_JUDGED_PRIVATE`. Publication,
  commit/push, video, and Devpost remain human-gated and were not performed.
