# Detection-triggered Agent Investigation — independent competition review

Date: 2026-08-29
Reviewer: independent competition judge
Scope: current dirty worktree, local synthetic API/SSE/browser only
Verdict: **APPROVE**

## Review contract

Goal: verify that deterministic detection, not a browser Start control, launches one bounded multi-agent investigation while preserving the existing human-controlled recovery boundary.

Inputs: current repository, isolated temporary runtime, loopback HTTP, headless Chrome, scripted local Strands harness, and injected live-source test doubles. No AWS/provider call, spend, commit, push, or publish occurred.

Stop rule: only a reproducible defect that could misstate automatic investigation, duplicate a run, or create an effect without the existing authority boundary may block.

## Exact acceptance results

| # | Acceptance | Result | Current-run evidence |
|---|---|---|---|
| 1 | One `POST /api/v1/scenarios` with `incident` completes the multi-agent harness without `/start` | **PASS** | Browser request recorder captured one scenario POST and no request containing `/start`. The resulting ledger contains three investigator starts, tool/evidence events, three handoffs, synthesis, and `evaluation.completed`. |
| 2 | Durable order `source.condition.injected < incident.detected < investigation.started` | **PASS** | Fresh isolated API proof: event indexes `1 < 2 < 3`, sequences are contiguous `1..71`, and the lifecycle records occur exactly in the required order. |
| 3 | Duplicate/reopen creates exactly one start; incomplete run resumes safely | **PASS** | Focused integration tests passed. A separate crash-window proof persisted only source, detection, and start, reopened the same directory, completed evaluation, retained exactly one `investigation.started`, and produced zero effects. |
| 4 | No visible manual Start; running/completed process is legible; Replay only after completion | **PASS** | Fresh Chrome: zero visible buttons matching `Start investigation`; early Replay was hidden. The live Agent Workspace showed Orchestrator `INVESTIGATING`, two investigators `RUNNING`, one `WAITING`, tool/evidence activity, then three `COMPLETE` roles and `Ready for decision`; only then Replay became visible. |
| 5 | No grant/effect before approval; two-role gate and ControlledExecutor unchanged | **PASS** | Fresh post-evaluation snapshot remained `approval.status=NOT_REQUESTED`, required roles were `INTEGRATION_OPERATOR` and `AP_APPROVER`, and `execution.effects=[]`. Focused two-role test rejected execution before quorum, retained no effect after one role, granted only after the second role, and produced one idempotent controlled effect. |
| 6 | NWS/NOAA/AIS context cannot trigger a confirmed incident or recovery | **PASS** | The live-source registry is a separate read-only advisory boundary; all 16 live-source tests passed, including route-risk classification, degraded/optional AIS, and poller behavior. No live-source adapter owns or calls detector, scenario allocation, decision, grant, or execution paths. |
| 7 | Provider/advisory failure is fail-visible and has no effect | **PASS** | Focused degraded test passed: `provider.degraded` plus `workflow.blocked` remains terminal, chat cannot rerun the harness, recovery preparation is denied, and no effect is created. UI JS contract tests also passed for degraded-mode removal of advisory controls and preservation of the deterministic gate. |

## Browser/API proof

The fresh isolated run reached `evaluation.completed` with 71 contiguous events and exactly one `investigation.started`. The browser loaded only loopback resources, raised no console warning/error, and rendered three distinct investigator roles with their own tool/evidence/handoff state.

Screenshots:

- `artifacts/audits/2026-08-29-detection-triggered-agent-investigation-review/01-normal-dashboard.png`
- `artifacts/audits/2026-08-29-detection-triggered-agent-investigation-review/02-auto-agent-investigation.png`
- `artifacts/audits/2026-08-29-detection-triggered-agent-investigation-review/03-completed-agent-investigation.png`

Machine-readable proof:

- `artifacts/audits/2026-08-29-detection-triggered-agent-investigation-review/focused-browser-api-proof.json`

## Commands and outcomes

- Focused Python acceptance set: **PASS** (`6 passed, 2 environment skips`, plus all 16 live-source cases passed in the same invocation).
- `npm test`: **PASS, 19/19**.
- Fresh isolated Chrome/API proof: **PASS**.
- Crash-window persisted reopen proof: **PASS**, one start, one completed evaluation, zero effects.

The legacy full browser-smoke script initially reported a fresh-scenario mismatch because its re-entry assertion compared an early DOM prefix with a later authoritative snapshot while automatic handoff was actively appending events. The focused proof demonstrates that this is a smoke synchronization defect, not a product-state defect: the DOM prefix and later snapshot are both contiguous, ordered projections of the same durable ledger. The smoke assertion should compare prefix containment or wait for a stable terminal cursor; it does not block this product-stage approval.

## Final competition verdict

**APPROVE.** Detection now causes a real, visible multi-agent investigation automatically. The implementation remains exactly-once and crash-resumable, keeps predictive public sources advisory, fails visibly on advisory/provider degradation, and preserves the deterministic two-role/ControlledExecutor boundary before any effect.

## Superseding smoke verification

The legacy full browser smoke was subsequently corrected to treat the live SSE
DOM as an authoritative contiguous prefix while the automatic handoff is still
advancing, then compare terminal UI state against the final durable cursor. The
new `artifacts/workspace/browser-smoke-v1.json` is `status=PASS` and records:

- `ui_flow.investigation_auto_handoff=true`;
- `ui_flow.manual_start_control_absent=true`;
- `ui_flow.paced_investigation=true`;
- `ui_flow.final_gate_closed=true` and `replay_effect_delta=0`;
- loopback-only browser resources, contiguous authoritative ledger behavior,
  and zero provider calls in each recorded view.

The earlier smoke caveat is therefore fully superseded. There is no remaining
product or test-harness caveat on this stage, and the verdict remains
**APPROVE**.
