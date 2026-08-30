# Award Control Tower UI — Stage 2 implementation audit

Date: 2026-08-29
Scope: Agent Workspace interaction, evidence/context closure, state-aware chat, and chart-focus regression

## Delivered

- Preserved keyboard focus for all five live chart canvases across data redraws and added a physical-key browser check for each canvas.
- Reworked the Agent Workspace around one investigation graph with role selection, concise role context, current activity, handoff/synthesis, evidence, governed decision rail, and an expandable full immutable trace.
- Added Context / Chat / Decision rail navigation with roving keyboard focus. Selecting a role filters the activity context and seeds role-aware chat requests.
- Added active/closed-case chat responses for state, historical gap, root cause, evidence, competing causes, and next action. Closed-case answers distinguish historical gaps from current state.
- Made evidence citations open and focus the matching evidence record with source, observation, supported claim, and integrity state. Unknown evidence fails closed visibly.
- Limited the primary activity feed to the latest eight events while retaining the complete trace in a disclosure. Removed duplicate workspace source cards in favor of one route ribbon.

## Files

- `workspace/index.html` — rail tabs, role context, trace disclosure, evidence status region.
- `workspace/app.js` — chart focus retention, role selection, rail navigation, chat state, trace projection, and evidence focus.
- `workspace/style.css` — compact task-oriented rail, evidence records, trace disclosure, route ribbon, focus and responsive states.
- `tests-js/scaffold.test.mjs` — Stage 2 structure, focus, evidence, chat, and copy contracts.
- `scripts/run_decision_workspace_smoke.py` — physical-key coverage for all five charts and live interaction assertions.

## Bounded Stage 2 correction

- The inherited chart-focus defect was closed by retaining/restoring the focused canvas through live redraws. The browser smoke uses physical CDP key events and verifies active canvas, metric/detail change, numeric freshness, and shared timestamp for Dashboard, queue, ERP, invoice, and external-risk charts.
- No backend architecture, live-source integration, AWS/provider call, or public action was added.

## Final bounded correction from independent award review

- Agent Workspace `Context / Chat / Decision` keyboard events are handled only by
  the nested rail tablist, call `stopPropagation`, and retain Agent Workspace
  while moving focus to the selected rail tab. Global Dashboard/Agent/Scenario
  tab handling ignores events from a nested tablist.
- Citation landing now deduplicates the primary evidence projection and focuses
  the exact durable `.evidence-record[data-evidence-id]`. The opened evidence
  drawer exposes `aria-current="true"`, a persistent `is-focused` highlight,
  source/observation/claim/integrity fields, and a visible fail-closed status
  when the durable record is absent. The closed-case probe also exercises
  `:refresh-*` evidence produced by a final state-aware chat turn.
- Chart redraws now prefer the physically focused canvas as the shared cursor
  owner, cancel stale focus restores when the canvas changes, and never steal
  focus from a button, link, form field, or rail tab during an SSE redraw. Each
  of the five canvases receives three physical ArrowRight presses while the
  live stream is active; the active canvas, metric, detail, and shared
  timestamps remain aligned.
- The private audit is regenerated only after source bytes and the final smoke
  artifact stop changing. The default package path remains local and private.

## Verification

- `npm test` — PASS (19 tests).
- `.venv/bin/python -m pytest -q tests/test_decision_workspace.py tests/integration/test_realtime_experiment.py` — PASS (socket-dependent tests skipped by environment).
- `node --check workspace/app.js` — PASS.
- `.venv/bin/ruff check scripts/run_decision_workspace_smoke.py` — PASS.
- `git diff --check` — PASS.
- Local Chrome decision-workspace smoke — PASS in **three consecutive isolated
  active-SSE runs**, including Normal → Incident → recovery, active/closed
  workspace paths, rail keyboard traversal, every displayed live and closed
  `:refresh-*` citation, missing-citation fail-closed behavior, degraded/invalid
  modes, responsive/reduced-motion checks, and three physical keys on all five
  charts.
- Smoke artifact: `artifacts/workspace/browser-smoke-v1.json`; `status=PASS`,
  `ui_flow.rail_keyboard_focus` covers all three rail transitions,
  `ui_flow.citation_focus` and `ui_flow.closed_citation_focus` report exact
  durable targets with `active_id`, `aria_current`, and `focused` all true,
  and `ui_flow.physical_chart_key_focus` contains all five canvases with
  numeric freshness and aligned shared timestamps.
- `.venv/bin/python -m mypy src scripts` — PASS (88 files).
- `.venv/bin/ruff check src scripts tests` — PASS.
- `scripts/audit_competition_package.py --check` — PASS after the final audit
  was frozen.
- `scripts/run_judge_demo.py` — PASS (five-minute local path; provider calls 0).
- `.venv/bin/python -m pytest -q` — PASS after audit regeneration; the only
  earlier failure was the expected stale-audit guard before the final freeze.
- No AWS/provider call, spend, commit, push, or publish was performed.

## Remaining risks for independent review

- Visual P3 polish and comparison against the final award reference remain
  reviewer concerns; no further copy or feature expansion was made in this
  bounded pass.
- Optional Prometheus/Grafana remains a local scaffold and is not required by
  the native workspace path.
