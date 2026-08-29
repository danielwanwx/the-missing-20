# Reference-Faithful Frontend Rebuild Plan

**Spec:** `docs/superpowers/specs/2026-08-28-reference-faithful-frontend-rebuild-design.md`
**Visual targets:** `docs/design/references/*.png`
**Implementation owner:** Luna worker. Primary agent owns review, browser verification, and acceptance.

## Phase 1: Freeze the projection boundary

- Inventory the existing REST/SSE state and event reducers used by Dashboard, Agent
  Workspace, Scenario Lab, chat, approval, execution, verification, and replay.
- Add visual projection selectors for supply flow, agent graph, activity timeline,
  hypotheses, evidence, and recovery lifecycle.
- Preserve all backend calls, IDs, event ordering, fail-closed checks, and deep links.
- Add JavaScript contract tests proving visual state is derived from authoritative state and
  ledger events rather than timers.

## Phase 2: Rebuild Dashboard

- Replace the report hero, truth strip, explanatory headings, and generic card stack.
- Build the 1487 x 1058 desktop composition from `dashboard-target.png`.
- Use Canvas for the live flow paths and reconciliation charts.
- Use the local Phosphor icon font for entity and agent icons.
- Bind packet movement, entity counts, alert branch, incident state, agent status, and chart
  points to the existing snapshot and SSE reducer.
- Preserve click-through to Agent Workspace and scenario deep-link state.

## Phase 3: Rebuild Agent Workspace

- Build the supply-state rail, central operations graph, Copilot rail, live activity rail,
  and reconciliation timeline from `agent-operations-target.png`.
- Project actual investigator, tool, evidence, handoff, synthesis, evaluation, recovery,
  approval, execution, and verification events onto the graph.
- Keep Case Console free text and bounded next actions functional.
- Move hypothesis confidence and evidence matrix into an interaction drawer based on
  `agent-investigation-target.png`.
- Keep approval and execution separate; degraded cases stay durably fail-closed.

## Phase 4: Responsive and state coverage

- Preserve desktop geometry at 1180 px and above.
- Use a right-rail drawer and horizontal graph overflow for tablet.
- Use Flow, Agents, Copilot, and Timeline sub-tabs for narrow screens instead of report
  stacking.
- Implement connected, disconnected, normal, incident, investigating, ready, awaiting
  approval, executing, verified, replay, degraded, and invalid states.
- Honor reduced motion without hiding state changes.

## Phase 5: Verification and design QA

- Run Python integration, JavaScript, Ruff, mypy, syntax, and diff checks.
- Run the real local API/SSE browser path from Normal through incident, investigation,
  Case Console, recovery preparation, approvals, execution, and verification.
- Capture Dashboard and Agent Workspace at exactly 1487 x 1058 in matching incident states.
- Compare each implementation capture directly with its source visual.
- Fix all P0/P1/P2 findings and write root `design-qa.md` with `final result: passed`.
- Obtain independent competition-judge approval before handoff.

