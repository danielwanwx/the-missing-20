# Dashboard Phase 1 rebaseline audit

Date: 2026-08-29
Scope: sections 3, 4, 7, 8, 9, and 11 of the approved live control-loop UI spec.

## Delivered

- Reworked the Dashboard first viewport into a dark control-tower layout with an active-agent rail, dominant Warehouse → Queue → ERP → Invoice flow, visible ports, event particles, active edge pulses, expected/recorded/gap quantities, compact incidents, component health graph, and reconciliation detail.
- Bound visual states to the existing snapshot and ordered SSE event stream. Healthy, incident (100/80/20), and recovery states continue to update without reload; disconnect remains fail-closed and freezes live movement.
- Added one compact `Live / Inject incident` Dashboard action using the existing scenario API and authoritative disabled state. The existing Scenario Lab control remains available for the workspace workflow.
- Collapsed NWS, NOAA, and optional AIS into advisory source nodes feeding the route-risk detector; provenance stays behind details.
- Kept Agent Workspace, reduced-motion, responsive behavior, and existing API/provider boundaries intact.

## Verification

- `npm test` — 25 passed.
- `.venv/bin/python -m pytest -q tests/test_decision_workspace.py tests/integration/test_realtime_experiment.py` — 51 passed, 6 skipped.
- `.venv/bin/python scripts/run_decision_workspace_smoke.py` — PASS (real API, Agent Workspace, approvals, recovery).
- `node --check workspace/app.js` — PASS.
- `git diff --check` — PASS.

## Files in scope

`workspace/index.html`, `workspace/style.css`, `workspace/app.js`, and `tests-js/scaffold.test.mjs`.
