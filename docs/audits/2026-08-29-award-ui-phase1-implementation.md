# Award Control Tower UI — Stage 1 implementation audit

Date: 2026-08-29
Scope: authoritative Dashboard scenario truth and four coordinated live diagrams

## Delivered

- Dashboard scenario state now comes from the server scenario catalog and the
  authoritative incident snapshot.  A rejected transition stays visible in an
  inline alert with the current state and a recovery action; no transition is
  silently ignored.
- The Dashboard has four visible diagram stories: order-flow topology,
  expected/recorded/gap reconciliation, queue/ERP/invoice health small
  multiples, and an external route-risk timeline for NWS, NOAA, and optional
  AIS observations.
- Enterprise charts consume the ordered incident SSE telemetry ledger.  The
  route-risk chart consumes the server-owned live-source event cursor.  A
  chart only pulses when a new server sequence arrives; no random values,
  browser third-party fetches, or decorative wall-clock samples are used.
- Pointer and keyboard selection share one selected time/entity across the
  diagrams and expose value, unit, source, observed/received time, and
  freshness in the focused detail line.  Missing history and unavailable AIS
  are rendered honestly.
- Topology nodes are keyboard-selectable, edge width/speed reflect current
  server quantities, and reduced-motion/hidden/disconnected states pause
  event-driven motion.

## Files

- `workspace/index.html` — four-diagram Dashboard structure, source detail,
  scenario error region, and non-interactive resolved rows.
- `workspace/app.js` — scenario transition handling, live-source event cursor,
  Canvas diagrams, shared selection, and topology interaction.
- `workspace/style.css` — control-tower layout, responsive breakpoints,
  data-bound flow motion, focus states, and motion gates.
- `tests-js/scaffold.test.mjs` — deterministic structure/data-binding and
  scenario-error coverage.
- `scripts/run_decision_workspace_smoke.py` — API/SSE browser acceptance for
  density projection, bounded anomaly access, responsive copy, and reduced
  motion.

## Bounded Stage 1 correction

- Replaced 100 record-level Dashboard buttons with one API-backed,
  non-interactive density strip.  Incident mode exposes at most six
  keyboard-accessible anomaly selectors and the authoritative record detail;
  no unit is removed from the underlying collection.
- Dashboard agent icons are status-only and the active incident row is a
  non-interactive status row.  The top navigation remains the only Dashboard
  route into Agent Workspace.
- Removed duplicate Dashboard provenance copy from the primary surface while
  retaining exact source, timestamp, and status details in the Agent Workspace
  disclosures.  Dashboard primary-surface copy is below 180 words at all
  tested widths.
- Selected-point freshness now derives numerically from
  `received_at - observed_at` when the source omits an explicit freshness
  value.  Topology counts are labelled `dispatched`, `backlog`, `posted`, and
  `completed`/`expected` according to the API state.
- Reduced-motion acceptance now disables the animated flow packet pseudo
  element itself, not only its parent line.

## Verification

- `node --check workspace/app.js` — PASS
- `npm test` — PASS (18 tests)
- `.venv/bin/ruff check scripts/run_decision_workspace_smoke.py` — PASS
- `git diff --check` — PASS
- Local Chrome decision-workspace smoke — PASS for the real API/SSE path,
  normal/incident/recovery flows, bounded anomaly interaction,
  degraded/invalid modes, mobile layout, reduced-motion, and no remote browser
  resources.  Dashboard word counts: 152 (1440), 138 (1280), 138 (768), and
  131 (390).  Reduced-motion pseudo-element animation name: `none`.
- Smoke artifact: `artifacts/workspace/browser-smoke-v1.json`.

## Remaining bounded notes

- The external route chart can show a truthful single-observation state before
  a second source event arrives; it does not infer a trend from missing data.
- Optional Prometheus/Grafana remains a local scaffold and is not required by
  the native Dashboard path.
- No AWS/model provider call, public push, deployment, or commit was made.
