# Agent Workspace Phase 2 rebaseline audit

Date: 2026-08-29
Scope: Agent Workspace presentation and interaction surfaces only.

## Result

The workspace now presents an explicit, port-to-port control loop:

`Incident packet → Orchestrator → investigator roles → Synthesis → Safety Gate → two-role approval → controlled recovery → Verification → Incident packet`

The visible investigator roles are Receipt Retry, Shipment Evidence, and Duplicate Posting. Their source groups, event-driven ledger pulses, handoffs, safety state, and verification return are rendered from the ordered session ledger. Healthy state is `MONITORING`; the healthy rail exposes source freshness and one incident-demo action without inventing a chat answer.

The Context, Chat, and Decision rail remains single-panel at a time, while Live Activity is a collapsed drawer. Incident chat continues to use the backend role identifier and renders admitted citations plus the deterministic authority refusal for approval or execution requests.

The incident controls now consult the authoritative scenario catalog and lifecycle. When the catalog owns a genuinely active incident, Dashboard and Workspace show `Resume active incident` and open that persisted run; a verified/closed catalog run is labeled `View completed investigation`, never active. `Inject incident`/`Run incident demo` is enabled only when the catalog reports the Normal boundary and an admitted Incident transition.

Investigator status is monotonic across the ordered operational ledger: later copilot messages can add conversation context but cannot regress HANDOFF or COMPLETE. DEGRADED remains fail-closed.

Persisted closed/verified runs retain their completed investigator, synthesis, safety, two-role approval, controlled-recovery, and verification states even when the current SSE window contains only later telemetry. Live Activity uses the persisted ledger rows when present and falls back to `Current stream` without inventing an incident history.

## Files

- `workspace/index.html` — closed-loop graph nodes, ports, lifecycle, rail panels, healthy action, and activity drawer.
- `workspace/style.css` — graph routing, event/selection/muted states, responsive layout, reduced-motion behavior, and rail styling.
- `workspace/app.js` — ledger-derived statuses and pulses, graph routing, role selection/filtering, rail exclusivity, catalog-gated incident controls, resume action, chat and citation projection.
- `tests-js/scaffold.test.mjs` — focused structural coverage for the workspace, catalog/lifecycle CTA truth, monotonic role status, and persisted closed-lifecycle projection.

The final topology pass keeps the canvas intentionally sparse: three compact source nodes, one incident badge, three evenly spaced investigator nodes, centered Synthesis, and a four-stage recovery row. Each semantic edge is rendered as a port-to-port cubic Bézier; the verification return is the sole wide outer arc. The desktop geometry contract samples the paths to guard against card-interior hits, crossings, and control-point direction reversals.

## Verification

- `npm test` — 30/30 passed.
- `.venv/bin/python -m pytest -q tests/test_decision_workspace.py tests/integration/test_realtime_experiment.py` — passed; expected integration skips remained.
- `node --check workspace/app.js` — passed.
- `git diff --check` — passed.
- Browser smoke — closed/verified catalog history rendered `View completed investigation` (not an active resume) on Dashboard and Workspace; an active catalog rendered `Resume active incident`; Normal-boundary catalog rendered `Run incident demo`; resumed closed lifecycle showed all investigators and control stages `COMPLETE` with persisted event history; role citation and authority refusal left the selected investigator `COMPLETE`.

## Truth and risk notes

The demo remains local synthetic data. Nova remains advisory (`1/5` citation closure), application validation remains `5/5`, and recovery authority remains deterministic. No AWS/provider or backend authority changes were made. The existing shared demo process can retain a previously active scenario between browser runs; the UI now surfaces that state and does not silently reset it or advertise a rejected transition.
