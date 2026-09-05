# Live Operations Command Map Implementation Plan

Source spec: `docs/superpowers/specs/2026-09-05-live-operations-command-map-design.md`

## Public seams

- Browser-visible Dashboard and Investigation DOM at `/?view=dashboard|agent`.
- Ordered `/api/v1/agent-platform/events` SSE projection.
- Existing snapshot, telemetry, diagnosis, approval, execution, and verification HTTP endpoints.
- Existing JavaScript and Python end-to-end test entry points.

## Slice 1 — Information architecture and contrast

1. Add failing static/browser assertions for two primary tabs, hidden Demo Controls, readable Signal/tool/event colors, and absence of theme leakage on Investigation.
2. Replace the primary Scenario Lab tab with a presenter-only Demo Controls drawer.
3. Scope light command-canvas styles to both active views without overlay leakage.
4. Run focused static and browser tests.

## Slice 2 — Flow-first Dashboard

1. Add failing assertions that incident Dashboard keeps the live topology and time-series chart visible and does not render the full Agent topology.
2. Replace the incident-only console/legacy-dashboard swap with a single command-map composition.
3. Bind topology values and status to the current snapshot and SaaS evidence.
4. Add a compact Agent lifecycle bar and deep link to the same incident in Investigation.
5. Run focused tests.

## Slice 3 — Minimal connector routing

1. Add failing geometry tests for straight-eligible edges, exact boundary endpoints, node-interior avoidance, and duplicate-pair rejection.
2. Implement one-port-per-direction node geometry and straight-first route selection.
3. Use one cubic only for genuinely offset or obstructed edges.
4. Remove redundant Dashboard source-to-Agent edges and endpoint dots.
5. Run connector tests and capture a focused topology screenshot.

## Slice 4 — Streaming chart and event rail

1. Add failing browser assertions for Expected/Recorded/Gap series, ascending visual event order, newest-at-bottom behavior, and one newest-row announcement.
2. Reuse authoritative telemetry/reconciliation helpers in the incident Dashboard.
3. Add NOW cursor and event annotations from ordered sequence data.
4. Append event rows incrementally, auto-scroll only at the live edge, and pause follow mode after manual review.
5. Animate only on new sequence; implement reduced-motion and reconnect freeze states.
6. Run focused tests.

## Slice 5 — Investigation Workspace

1. Add failing assertions that Investigation owns the Agent topology, tool/evidence stream, chat, hypotheses, and Manager gate but not the deterministic supply-chain map.
2. Remove the duplicated business-flow diagram and adapt the existing graph to multi-SaaS evidence relationships.
3. Preserve diagnosis, chat, approval, execution, verification, and packet actions.
4. Apply the shared light visual system and readable typography.
5. Run focused tests.

## Slice 6 — End-to-end and visual QA

1. Exercise Normal → Incident → Investigation → Manager approval → bounded recovery → independent verification.
2. Confirm Dashboard chart, topology, event rail, and Agent status share the same incident and sequence.
3. Test reconnect, replay, degraded provider, reduced motion, keyboard focus, and responsive stacking.
4. Capture Normal, incident-forming, investigating, manager-review, and verified screenshots at 1440 × 1024.
5. Compare the selected visual target and implementation in one combined image; fix visible P0–P2 defects.
6. Regenerate the private competition audit and run JavaScript, Python, and browser suites.
7. Require `design-qa.md` to end with `final result: passed`.
