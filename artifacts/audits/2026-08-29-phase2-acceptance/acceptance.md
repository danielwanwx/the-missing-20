# Phase 2 acceptance review — 2026-08-29

Final verdict after the single bounded correction: APPROVE_PHASE2

Final competition score: 90/100

The original 85/100 rejection below is retained as pre-correction evidence. The
final independent recheck confirmed that disclosures remain open across 1 Hz
operational renders and view changes, cached observations do not replay their
pulse, the 390 px layout contains all three source cards, official provenance
links cause no remote browser resource loads, unknown incident IDs remain
fail-closed, and the approval, execution, verification, and replay flow remains
intact.

## Superseding final verification

- Verdict: `APPROVE_PHASE2`
- Live-source disclosure and card identity: PASS
- One-shot observation pulse: PASS
- 390 px responsive browser smoke: PASS
- Remote browser resources and provider calls: 0
- Unknown incident lookup: HTTP 404 with no state creation
- JavaScript tests: 14/14 PASS
- Full Python suite: PASS with expected skips
- Material blockers remaining: none

## Original pre-correction review

Verdict: REJECT_PHASE2

Original competition score: 85/100

## Acceptance matrix

1. **Backend live sources — PASS.** The running `/api/v1/live-sources` returned current server-side NWS and NOAA observations with separate observed/received timestamps, freshness, provenance, route scope, `external_context_only: true`, and advisory-only risk. The event feed showed NWS sequence 7 repeated with `new_observation: false`, NOAA sequence 8 changed observation time and was `true`, then NOAA sequence 14 repeated as `false`. Browser CSP is `connect-src 'self'`; the workspace client calls only `/api/v1/live-sources` and contains no NWS/NOAA/AIS fetch.

2. **Route and freshness truth — PASS.** Current NWS returned 12 California alerts but only 4 route alerts and 2 route-high-severity alerts; the route alert records were Los Angeles/Orange/Inland Empire areas. NWS remained `CONNECTED` with a one-hour-old active alert, while NOAA station 9410660 was `CONNECTED` and 5–9 minutes old during the run. The focused San Diego exclusion and Inland Empire inclusion tests passed.

3. **Visible live-source interaction — FAIL.** The compact cards are visually clear on Dashboard and Agent Workspace, but `Source details` does not remain open. Fresh browser clicks repeatedly returned `details.open === false`. The root cause is reproducible in `workspace/app.js`: `renderLiveSources()` replaces both grids at lines 342–376, while every operational SSE event schedules `renderAll()` at lines 2308–2318. Normal telemetry therefore destroys an open disclosure about once per second. The same rebuild can replay the `.is-new` animation while the cached source snapshot still has `new_observation: true`, so the new-data pulse is not edge-triggered to a new live-source observation.

4. **Optional AIS — PASS.** API state is exact `OPTIONAL_NOT_CONFIGURED`, `observed_at: null`, and `vessel_count: 0`. The key is read only by the server adapter from `AISSTREAM_API_KEY`; `.env.example` keeps it blank; the optional `live` dependency is the real `websockets` path; no AIS call was made.

5. **Authority separation — PASS.** While external route risk was HIGH, Normal remained `HEALTHY`, 100/100/0, with only `telemetry.observed` in the operational ledger, approvals `NOT_REQUESTED`, execution `NOT_STARTED`, and zero effects. Unknown incident remained HTTP 404. No live/NWS/NOAA/AIS event entered the incident ledger.

6. **Operational E2E — PARTIAL.** Fresh UI execution with polling active passed Normal → 80/20 Incident → explicit Start → all three roles and Orchestrator → two fresh approvals per action → two controlled executions → verification → CLOSED → paced replay with `replay_effect_delta: 0`. Focused Python and JavaScript tests passed. The repository browser smoke could not reach its 390px check because `_assert_dom` rejects any external URL in the DOM; the new official provenance anchors trigger `agent DOM contains a remote URL` even though they are links, not fetched resources.

7. **Award-facing clarity — PASS.** The compact `PUBLIC ROUTE SIGNALS / Port context` strip is visually subordinate to the synthetic ERP twin, labels NWS/NOAA/AIS individually, and leaves the agent/recovery story dominant.

## Material correction

Make live-source rendering edge-triggered and state-preserving: do not rebuild the live-source grids on the 1 Hz operational render loop; preserve disclosure open state; consume `new_observation` once per new live-source cursor/event so only a real observation starts the event pulse. In the same bounded live-source acceptance change, update the smoke network gate to allow inert official provenance anchors while still failing on actual remote browser resource requests, then rerun the 390px E2E.

## Evidence

- `01-dashboard-live-public-context.png`
- `02-agent-workspace-live-context-normal.png`
- `03-closed-verified-with-live-context.png`
- Running API/event checks and browser interaction captured in this review
- JavaScript: 13/13 PASS
- Focused Python live-source/workspace/integration tests: PASS with expected skips
- Live-source-enabled browser smoke: BLOCKED (`agent DOM contains a remote URL`)
