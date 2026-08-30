# Phase 1 acceptance review — 2026-08-29

Verdict: REJECT_PHASE1

## Material blocker

The running demo on `127.0.0.1:8765` is not serving the corrected worktree. A fresh unknown deep link for `phase1-does-not-exist` rendered a live 100/80/20 incident with `Start Investigation`, and the local API subsequently returned `HTTP/1.0 200 OK` with a newly materialized `incident.detected` event at sequence 1. This violates the required fail-closed boundary and can falsely present generated incident data as registered state.

Evidence: `00-running-8765-unknown-incident-fabricated.png`.

## Corrected worktree evidence

An isolated server from the current worktree on port 8877 rendered the same unknown ID as `Stream unavailable`, `PAUSED`, sequence `—`, and no operational quantities. The fresh browser smoke returned PASS and records: HTTP 404 `incident_not_found`, no session, no runtime directory, single visible investigation start, role selection and route highlighting, two-role quorum, controlled execution, verification, replay effect delta 0, degraded and invalid fail-closed states, mobile width 390, and provider calls 0.

Evidence:

- `02-unknown-incident-fail-closed.png`
- `03-pre-investigation-single-start.png`
- `04-investigation-running.png`
- `05-selected-shipment-route.png`
- `browser-smoke-v1.json`

Focused checks: JavaScript 13/13 PASS; Python workspace/integration suite PASS with expected skips.

## Bounded correction

Restart the port-8765 demo process from the current worktree, then rerun the same unknown-ID browser/API check before showing or recording the product.
