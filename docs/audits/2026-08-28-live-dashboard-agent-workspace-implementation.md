# Live Dashboard and Agent Workspace Implementation

**Date:** 2026-08-28
**Scope:** Live Digital Twin + Agent Mission Control redesign

## Delivered

- The local workspace now opens on a normal, healthy 100-unit flow and keeps the same
  authoritative session while switching between Dashboard and Agent Workspace.
- Normal, Incident, Recovery, and Golden Incident controls call the local experiment API.
  They do not mutate business state in the browser. Incident mode exposes the governed
  80-record ERP path plus the 20 records stopped at Message Queue; recovery remains
  locked until the existing Authority B lifecycle allows it. Re-entering Incident or
  Golden Incident after Recovery creates a fresh persisted incident ledger, while
  Recovery continues to point to the newest verified closed run.
- Dashboard metrics, sparklines, timeline marks, unit movement, connection state, and
  agent activity are derived from the authoritative snapshot and ordered public ledger.
  Ambient node heartbeats and path current communicate connectivity only. Disconnects,
  hidden tabs, and reduced-motion preferences pause work-like motion.
- Agent Workspace shows the Orchestrator, three investigators, tool-call edges, evidence
  returns, handoffs, copilot citations, and the structured Prepare -> Approve -> Execute
  -> Verify rail. Chat remains advisory and cannot authorize or execute recovery.
- Primary surfaces use compact status labels and move detailed safety/provenance context
  to an on-demand trace drawer.
- Added an optional Prometheus/Grafana profile under `observability/`. The native product
  remains zero-dependency; the optional profile scrapes the local `/metrics` endpoint and
  opens Grafana separately when available. Both optional ports bind to loopback and the
  datasource/dashboard directories are mounted explicitly.

## Files

- `workspace/index.html`, `workspace/app.js`, `workspace/style.css`
- `scripts/decision_workspace_server.py`, `scripts/run_decision_workspace_smoke.py`
- `src/the_missing_20/experiment/session.py`
- `src/the_missing_20/adapters/synthetic_enterprise.py`
- `fixtures/scenarios/healthy-flow.json`
- `tests/integration/test_realtime_experiment.py`, `tests-js/scaffold.test.mjs`
- `observability/`

## Verification

- `git diff --check`
- Python syntax compilation with the repository runtime
- `npm test` (11/11)
- Full Python suite (all tests passed after regenerating the private audit)
- `scripts/run_decision_workspace_smoke.py` against the local server, covering Normal,
  Incident 80/20, Agent Workspace, approvals, recovery, and verification

No AWS/provider call, public push, deployment, or external data was used. Grafana is
intentionally optional and is not part of the native judge path.
