# Award Control Tower UI — Phase 1 independent review

Date: 2026-08-29
Reviewer: independent award-level product and UX acceptance reviewer
Scope: read-only review of Stage 1 in `2026-08-29-award-control-tower-ui-design.md`
Verdict: **REJECT_PHASE1**

## Executive verdict

Phase 1 now has a credible control-tower foundation. The fresh browser path keeps the server catalog, URL, selected scenario, hero, gap, and action state aligned; the four required diagram stories are present and fed by the local API/SSE and server-owned public-source cursor; the shared keyboard cursor works; all tested widths avoid page-level horizontal overflow; and the browser console is clean.

It is not yet acceptable against the approved Stage 1 contract because the Dashboard still exposes **100 tiny record buttons**, contains **302 visible words** at desktop instead of the 180-word maximum, keeps multiple role/incident affordances that duplicate the authoritative Agent Workspace navigation, and does not actually stop the topology packet animation under `prefers-reduced-motion`. The selected telemetry detail also reports `freshness unavailable`, and the topology labels one backlog value as generic `records`, weakening the data story. These are reproducible P1 defects, not optional polish.

No P0 defect was reproduced in the corrected worktree.

## Evidence reviewed

- Approved design: `docs/superpowers/specs/2026-08-29-award-control-tower-ui-design.md`
- Prior benchmark/audit: `docs/audits/2026-08-29-award-ui-review.md`
- Implementation record: `docs/audits/2026-08-29-award-ui-phase1-implementation.md`
- Fresh browser evidence: `artifacts/audits/2026-08-29-award-ui-phase1-review/browser-phase1-evidence.json`
- Fresh screenshots:
  - `artifacts/audits/2026-08-29-award-ui-phase1-review/dashboard-normal-1440.png`
  - `artifacts/audits/2026-08-29-award-ui-phase1-review/dashboard-incident-1440.png`
  - `artifacts/audits/2026-08-29-award-ui-phase1-review/dashboard-normal-1280.png`
  - `artifacts/audits/2026-08-29-award-ui-phase1-review/dashboard-normal-768.png`
  - `artifacts/audits/2026-08-29-award-ui-phase1-review/dashboard-normal-390.png`
- Existing full browser smoke: `artifacts/workspace/browser-smoke-v1.json`
- User references: the three dark control-tower / agent-operations screenshots named by the approved design as visual truth.

## Acceptance matrix

| Area | Result | Reproduced evidence |
|---|---|---|
| Authoritative scenario truth | PASS | Fresh Normal showed `missing-20-normal`, Normal selected, `All 100 units are accounted for`; UI `Inject incident` changed URL to `scenario=incident&incident_id=missing-20-001-run-1`, hero to `20 units stopped before ERP`, gap to 20, and state to `Attention needed`. Unknown incident returned 404 `incident_not_found` without changing the catalog. |
| Four professional diagram stories | PASS | Exactly four stories are visible: topology; reconciliation; one grouped flow-health small-multiple story; external route-risk timeline. Incident screenshot shows real 100/80/20 changes across topology and charts. |
| API/SSE provenance | PASS | Enterprise series read the ordered telemetry ledger; external risk reads `/api/v1/live-sources/events`; fresh browser resource ledger had zero third-party requests; full smoke records live SSE sequence changes and provider calls 0. |
| Honest history | PASS | A fresh Normal state rendered `Insufficient live history` rather than inventing a trend. Incident transition created a second authoritative point and then rendered lines. AIS unavailable/single-observation states are explicit in code. |
| Shared cursor and keyboard | PARTIAL | ArrowLeft on the reconciliation canvas updated all three cursor labels to `15:37:11` and the shared detail line. The detail included metric, value, unit, source, observed and received times, but freshness was `unavailable`. |
| Dashboard copy/control economy | FAIL | 302 visible words at 1440/1280/768, 289 at 390; 100 record-level buttons plus three role buttons remain visible. Approved maximum is 180 words and the spec explicitly requires a density strip instead of 100 tiny controls. |
| Reduced motion | FAIL | With CDP emulating `prefers-reduced-motion: reduce`, `.flow-link-line::after` retained `animation-name: packet-travel` and duration `0.65s`. The media rule targets the parent line, not the animated pseudo-element. |
| Responsive layout | PASS with P2 notes | Page scroll width equaled viewport width at 390, 768, 1280, and 1440. The 390 flow owns its horizontal scroll. Visual density and type size remain weaker than the references. |
| Console/network | PASS | No browser warning/error in all four fresh width probes; no direct external browser resources. |
| Regression gates | PASS | JavaScript 16/16; focused Python 50 passed, 6 socket-dependent skips; full local Chrome smoke PASS; `git diff --check` PASS. |

## Reproducible P1 findings

### P1.1 — The record visualization is still 100 inaccessible micro-buttons

The approved design explicitly requires a non-interactive density strip plus an accessible anomaly/detail list. Fresh DOM inspection found 100 `button[data-unit-id]` controls. At 1440 each is approximately 10×4 px; at 390 each is approximately 6×4 px. They are neither viable pointer targets nor useful keyboard controls, and their hidden numeric labels contribute roughly 100 words to the Dashboard.

Impact: failed interaction, accessibility, copy-economy, and reference-fidelity requirements in one place.

### P1.2 — Dashboard information density is still report-like

Fresh visible-word counts were 302 at 1440/1280/768 and 289 at 390, exceeding the approved 180-word ceiling by 61–68%. The Dashboard also keeps three clickable agent-role cards and an active-incident entry in addition to the authoritative top navigation. These repeat the Agent Workspace path instead of reserving Dashboard controls for data inspection.

Impact: the first fold reads as a collection of labels/status/report fragments rather than the compact visual operations surface shown in the references.

### P1.3 — Reduced-motion mode does not stop the data packet

The flow pulse is implemented on `.flow-link-line::after`, but the reduced-motion rule disables animation on `.flow-link-line`. In an emulated reduced-motion browser the pseudo-element still computed `packet-travel / 0.65s`.

Impact: violates the explicit motion contract and WCAG-oriented motion preference handling.

### P1.4 — Shared detail is not fully truthful and topology semantics are ambiguous

Keyboard selection correctly synchronized all chart cursors, but the detail line ended with `freshness unavailable` even though observed and received timestamps were available and identical. The normal topology also renders `Message Queue 0 records`; the incident topology renders `Message Queue 20 records`. These are backlog/exception values, not end-to-end message throughput, and generic `records` makes the flow look internally contradictory. In the incident screenshot Invoice is shown as 100 after ERP is 80 without a label that distinguishes invoice expectation from completion.

Impact: a judge cannot reliably tell whether a number is throughput, backlog, expected quantity, or completed quantity—the exact confusion the control-tower redesign was intended to remove.

## One bounded correction package

**Package name: Dashboard truth-and-density closure**

1. Replace all 100 record buttons with one non-interactive density strip driven by the same unit collection. Keep a concise anomaly list or the existing `Inspect a record` disclosure for record-level access; do not expose 100 primary controls.
2. Make Dashboard role icons status-only. Keep the top navigation as the sole Agent Workspace route. Make the active-incident row either a true in-place detail selector or non-interactive; do not add another workspace CTA.
3. Reduce visible Dashboard copy to at most 180 words at 1440 and 390. Remove repeated LIVE/source/provenance explanations from the primary surface; retain exact IDs and timestamps in details.
4. Disable animation on `.flow-link-line::after` in reduced-motion mode and verify the computed pseudo-element animation name is `none`.
5. Derive numeric freshness from `received_at - observed_at` when the source does not provide `freshness_seconds`; a selected point must never say `freshness unavailable` when both timestamps exist.
6. Give each topology count an explicit semantic label: Warehouse `dispatched`, Queue `backlog`, ERP `posted`, Invoice `completed` (or `expected` if it truly represents the document expectation). Do not show Invoice completion above ERP posting without an explicit alternate-flow explanation.

### Exact acceptance checks for Luna

1. Fresh browser Normal → Incident still produces catalog/URL/hero/control agreement and no console errors.
2. `document.querySelectorAll('#dashboard-view button[data-unit-id]').length === 0`.
3. Dashboard contains exactly one accessible density strip and a bounded anomaly/detail list; no unit is lost from the underlying API evidence.
4. Only the top navigation routes to Agent Workspace from Dashboard.
5. Visible Dashboard word count is `<= 180` at 390, 768, 1280, and 1440.
6. Under `prefers-reduced-motion: reduce`, `getComputedStyle(flowLine, '::after').animationName === 'none'`.
7. ArrowLeft/ArrowRight/Home/End on every chart updates one shared timestamp across reconciliation, flow health, external context, and concise detail; the detail includes metric, value, unit, source, observed, received, and numeric freshness.
8. Normal labels read `dispatched / backlog / posted / completed-or-expected`; Incident labels preserve those semantics and the visual quantities are causally understandable.
9. All four stories remain API/SSE-driven, render honest insufficient-history/unavailable states, and never create timer-randomized chart values.
10. 390/768/1280/1440 retain no page-level horizontal overflow; browser console/network and JS/Python/full smoke gates remain clean.

## Non-blocking P2/P3 notes

- P2: visual direction is substantially closer to the references, especially the glowing flow line, alert branch, and coordinated dark palette. It still has weaker first-fold composition: the reference uses tighter vertical packing, larger chart signals, and fewer labels.
- P2: several primary labels remain around 0.48–0.55rem and are visibly smaller/lower contrast than the reference. Raise only operationally important labels; do not add explanatory text.
- P2: at 768 the navigation becomes icon-only while the main content remains desktop-dense. It is technically usable but visually less self-explanatory than the reference.
- P3: the normal route-risk panel is honest but visually sparse when only one NWS/NOAA observation exists. Keep the honest state; do not manufacture history.

## Final decision

**REJECT_PHASE1**

The core architecture and four-diagram data story are sound. One bounded truth-and-density correction should be sufficient; no new product direction, backend refactor, AWS call, or visual redesign is required.

---

## Correction verification — final read-only rerun

Date: 2026-08-29
Evidence: `artifacts/audits/2026-08-29-award-ui-phase1-review/browser-phase1-correction-evidence-v3.json`
Screenshots: `artifacts/audits/2026-08-29-award-ui-phase1-review/correction-v2-dashboard-*.png`
Correction verdict: **REJECT_PHASE1**

The bounded correction fixed nine of the ten exact acceptance checks. One reproducible P1 remains: real keyboard focus is lost when the first chart selection redraws the live canvases, so the remaining charts do not receive physical keyboard events.

### Exact-check results

| # | Exact acceptance check | Result | Fresh evidence |
|---|---|---|---|
| 1 | Fresh Normal → Incident preserves authoritative catalog/URL/hero/control truth | PASS | Isolated server started Normal at `missing-20-normal`; UI Inject changed the URL to `scenario=incident&incident_id=missing-20-001-run-1`, selected Incident, changed the hero to `20 units stopped before ERP`, gap to 20, and state to `Attention needed`. Console remained empty. |
| 2 | No record-level unit buttons | PASS | `button[data-unit-id] === 0` at 390/768/1280/1440 and in Incident. |
| 3 | One density strip, bounded detail, no evidence loss | PASS | Exactly one `role=img` density strip with 100 non-interactive span cells; full smoke still reports 100 API units and 100 projected units. |
| 4 | Only top navigation routes to Agent Workspace | PASS | Dashboard-local route candidates 0; agent rail is status-only; active incident is non-button. |
| 5 | Dashboard visible words <= 180 | PASS | Normal: 141 at 768/1280/1440, 134 at 390. Incident: 153 at 1440. |
| 6 | Reduced-motion stops the packet pseudo-element | PASS | Emulated `prefers-reduced-motion: reduce` computed `.flow-link-line::after` as `animationName: none`, `animationDuration: 0s`. |
| 7 | Every chart supports physical keyboard shared selection with numeric freshness | **FAIL (P1)** | The first physical End key reached `dashboard-chart`, selected `Gap · 20 units`, synchronized all three labels, and produced `0s old`. That redraw moved focus back to `tab-scenario`. Subsequent focus attempts on queue, ERP, invoice, and external canvases were displaced before key delivery; their key event logs were empty and detail stayed on Gap. |
| 8 | Topology count semantics are explicit and causally understandable | PASS | Normal: dispatched 100 / backlog 0 / posted 100 / completed 100. Incident: dispatched 100 / backlog 20 / posted 80 / expected 100. |
| 9 | Four stories remain real API/SSE driven and honest | PASS | Topology, reconciliation, grouped health, and external context all visible. Incident chart metadata held two authoritative enterprise points and three server-owned external points. Repository full smoke recorded `sse_live: true`, zero remote browser resources, and zero provider calls. |
| 10 | Responsive, console/network, and regression gates | PASS | No page-level overflow at 390/768/1280/1440; console empty at all widths; JS 18/18; focused Python 50 passed with 6 socket-dependent skips; full local Chrome smoke PASS; `git diff --check` PASS. |

### Remaining reproducible P1

**P1 — Live redraw evicts chart keyboard focus.**

The chart interaction handler itself works: the first physical keyboard event selects a point, synchronizes all cursor labels, and shows numeric freshness. The resulting `selectSharedPoint()` redraw calls resize/repaint the canvases and the focused element becomes `tab-scenario`. Because the live surface can redraw between `focus()` and the next physical key, the queue, ERP, invoice, and external charts did not receive their keys in the fresh CDP run.

This is not a cosmetic accessibility note. It breaks the approved shared keyboard-control contract on the live product and makes four of five chart canvases unreliable for keyboard users.

### One final bounded correction

Preserve chart focus across data-only redraws. Prefer not assigning `canvas.width` / `canvas.height` when the backing size is unchanged. If a redraw must replace or resize the focused canvas, capture its ID and restore focus without scrolling after the paint. Add one physical-key browser regression that iterates reconciliation, queue, ERP, invoice, and external canvases during an active SSE incident and proves for each:

1. the canvas receives End and ArrowLeft;
2. the concise detail changes to that chart's metric;
3. all shared cursor labels show the same selected timestamp;
4. freshness is numeric;
5. focus remains on the selected canvas after redraw.

No other Stage 1 work should block approval.
