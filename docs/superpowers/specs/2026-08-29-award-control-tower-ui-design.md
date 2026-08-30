# Award Control Tower UI Design

Date: 2026-08-29
Status: Approved by product owner
Source audit: `docs/audits/2026-08-29-award-ui-review.md`
Visual targets:

- `artifacts/design-qa/reference-dashboard.png` when available; otherwise the user-supplied control-tower screenshots in the originating Codex task are the visual truth.
- `artifacts/audits/2026-08-29-award-ui-review/01-dashboard-normal.png`
- `artifacts/audits/2026-08-29-award-ui-review/04-agent-live-replay.png`

## Loop contract

Goal: turn the current product into an award-facing live supply-chain control tower that makes the data gap, agent investigation, governed action, and verified recovery understandable without reading a report.

Input scope: `workspace/`, the existing decision-workspace API/SSE endpoints, current tests and browser-smoke scripts, synthetic enterprise fixtures, and already implemented NWS/NOAA/AIS advisory sources.

Non-goals:

- No new AWS or model calls.
- No public deployment, commit, push, or submission.
- No new product direction, ERP integration, or unrelated backend refactor.
- No fabricated business data, random chart motion, or direct browser requests to third parties.

Checks: authoritative scenario agreement; real API/SSE-driven chart updates; browser interaction inventory; chat/citation fixtures; responsive and keyboard checks; full Python/JS/browser gates; visual QA against the selected control-tower references.

Feedback: each implementation stage gets one consolidated independent review and at most one focused correction. Optional polish is deferred.

Records: implementation audit, browser screenshots, browser-smoke manifest, `design-qa.md`, and final independent score.

Stop: no P0/P1 findings, `design-qa.md` says `final result: passed`, all regression gates pass, and the strict award rubric reaches at least 88/100. Product owner retains final acceptance.

## Product model

Dashboard answers one question:

> Where is flow breaking, what is the operational impact, and is the agent system handling it?

Agent Workspace answers a different question:

> What are the agents investigating, what evidence supports the conclusion, and what governed action can a human approve?

Scenario Lab stays separate and controls only synthetic demo state. All surfaces derive state from the authoritative server catalog.

## Stage 1: Live Control Tower

### Authoritative scenario truth

- Dashboard, Scenario Lab, URL, selected scenario control, current incident, and action availability must agree.
- A rejected transition must show an inline error with the authoritative current state and a recovery action.
- No click may fail silently.

### Four coordinated diagrams

All diagrams use the same API/SSE cursor and a shared selected time/entity.

1. Live order-flow topology
   - Warehouse to Queue to ERP to Invoice.
   - Edge width represents throughput.
   - Pulse speed represents newly observed event rate.
   - A red branch represents the missing quantity.
   - Node badges expose backlog and freshness.

2. Reconciliation trend
   - Expected, recorded, and gap over sampled history.
   - Incident and recovery markers share the same time axis.
   - Honest insufficient-history state; no decorative flat series.

3. Flow-health small multiples
   - Queue backlog or lag.
   - ERP posting rate.
   - Invoice completion rate.
   - Aligned time axes and shared cursor make cause and downstream impact comparable.

4. External route-risk timeline
   - NWS severity bands.
   - NOAA water level and threshold.
   - Optional AIS vessel count or explicit unavailable state.
   - Clearly labeled `External context`; never imply enterprise causality.

### Diagram interaction contract

- Hover and keyboard focus expose timestamp, value, unit, source, observed time, received time, and freshness.
- Click/focus selection updates topology, all time-series cursors, and one concise detail panel.
- A new cursor may trigger one new-data pulse; unchanged cursors must not replay motion.
- Reduced-motion mode preserves state changes without continuous pulses.
- Dynamic numbers use tabular figures.

### Dashboard copy and controls

- Maximum 180 visible words excluding chart axes and technical details.
- Merge System Status and System Health.
- Remove the one-option time selector.
- Remove duplicate Agent Workspace CTAs; top navigation remains authoritative.
- Replace 100 tiny record buttons with a non-interactive density strip plus an accessible anomaly/detail list.
- Resolved incident rows open real historical cases or render as non-interactive rows.
- Condense footer to one provenance pill; IDs remain in technical details.

## Stage 2: Agent Workspace and interaction closure

### Investigation graph

- Keep one prominent graph: Orchestrator plus three distinct investigator roles.
- Show current tool call, evidence count, handoff, and synthesis state.
- Clicking a role selects it, updates the role panel, filters activity, and seeds role-aware chat context.
- During an active/replayed incident, show a compact competing-hypothesis plot and evidence-coverage matrix.

### Right rail

- Organize as Context, Chat, and Decision sections/tabs rather than one report-like stack.
- Keep only the latest eight activity events; full immutable trace is expandable.
- Use human evidence labels in the primary UI; exact IDs are copyable in the evidence drawer.
- Condense repeated source cards to one incident-relevant external-risk ribbon linking back to Dashboard.

### Chat and evidence

- Active and closed cases must answer current state, historical gap, root cause, evidence, alternatives, and next action correctly.
- Closed cases must distinguish historical missing units from the current reconciled state.
- Citation clicks open the evidence drawer, focus the matching evidence, and show source, observation, supported claim, and integrity state.
- Missing evidence fails closed with a visible message.

### Control rules

- Keep deterministic Prepare, two-role Approval, Execute, Verify, and Replay controls.
- Do not surface disabled future stages as primary buttons.
- Merge duplicate suggested questions and case actions.
- Every enabled control must produce navigation, state change, expanded detail, or a response.
- Top tabs and chart cursor support keyboard arrows with visible focus.
- Core targets are at least 44 by 44 pixels on touch and 40 by 40 pixels on dense desktop.

## Acceptance matrix

1. Fresh Normal to Incident to Investigation to Approval to Execution to Verification to Recovery to Normal works end to end with catalog, URL, controls, and hero in agreement.
2. Four Dashboard diagrams render at desktop and update only from real API/SSE cursor changes.
3. Cross-panel selection works by pointer and keyboard.
4. Three investigators, tools, evidence, handoff, safety gate, human gate, controlled action, and verification are visibly legible.
5. Active and closed chat fixtures return concise, grammatical, cited, state-correct answers.
6. Every displayed citation opens and focuses its evidence.
7. Representative control inventory contains no dead or false affordance.
8. Dashboard stays under 180 words and Agent Workspace under 350 words.
9. 390, 768, 1280, and 1440 pixel widths have no horizontal overflow; touch/focus/reduced-motion checks pass.
10. Enterprise flow remains labeled synthetic; external sources remain advisory; no direct third-party browser requests occur.
11. Python, JavaScript, browser E2E, console, unknown-ID, degraded/fail-closed, approval/execution/verification/replay, and remote-resource tests pass.
12. The Golden judge path completes in five minutes without typing.
