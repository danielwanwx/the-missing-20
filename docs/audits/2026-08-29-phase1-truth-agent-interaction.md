# Phase 1: Truth Boundary and Agent Interaction

**Date:** 2026-08-29
**Scope:** bounded frontend/API interaction correction

## Delivered

- Incident reads are lookup-only. An unknown incident ID returns `404 incident_not_found`
  and does not create a session, ledger, or runtime directory. Only the explicit Scenario
  Lab transition allocates a new synthetic incident.
- Dashboard keeps one visible investigation launch path in Agent Workspace. Redundant
  dashboard launch, replay, and “view all” controls remain only as hidden compatibility
  hooks for existing automation and do not create a second user path.
- Each investigator card is a real control. Selecting it updates the active role context,
  chat target, filtered activity feed, and source-to-investigator-to-orchestrator route.
  Orchestrator selection returns to team mode. Role mission, task, tools, evidence,
  hypothesis, and status are projected only from the current session ledger/advisory data.
- Graph links are positioned from component edge ports after layout, remain continuous
  through resize, and expose selection/event pulses without inventing business metrics.
  Existing reduced-motion, hidden-tab, and disconnected-stream safeguards remain active.

## Verification

- Unknown-incident API regression: `404`, no session/ledger/runtime directory.
- Focused integration suite: `.venv/bin/python -m pytest -q tests/integration/test_realtime_experiment.py`.
- Frontend unit suite: `npm test`.
- JavaScript syntax: `node --check workspace/app.js`.
- Browser smoke: `scripts/run_decision_workspace_smoke.py` (fresh artifact records the
  Normal → Incident → Agent Workspace Start → investigator selection → approval → execute
  → verify → replay path, plus invalid/degraded modes).
- `git diff --check` and repository lint/type checks where applicable.

No AWS/provider call, external data source, spend, commit, push, or publication is part of
this phase. NWS/NOAA and optional AISStream integration remain a separate integration
milestone; the current workspace continues to use the authoritative local synthetic API.
