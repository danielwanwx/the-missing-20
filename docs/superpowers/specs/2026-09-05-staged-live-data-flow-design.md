# Staged Live Data Flow Design

## Goal

Make the Dashboard visibly behave like a live operational system without presenting a decorative front-end animation as real data. A healthy demo run must progress through Warehouse, Message Queue, ERP, and Invoice in observable batches. An incident run must use the same producer but stop 20 units before ERP, after which the existing Agent investigation workflow begins.

## User-facing design

- Remove the horizontal connector line elements between the four operational nodes. The nodes remain ordered left to right, but each is an independent live instrument.
- Keep the separate vertical evidence-source links because they express data provenance rather than throughput.
- Each operational node shows its cumulative stage quantity as the dominant number.
- A new authoritative stage observation causes the relevant number to roll upward, the node surface to change briefly to its source color, and its status icon to update. Motion is never the sole signal.
- The reconciliation chart appends the same stage observation immediately. It must build point by point instead of rendering a completed flat history on initial load.
- The event rail receives the corresponding ledger event at the same time and follows the newest event at the bottom.
- In the incident scenario, Warehouse and Message Queue reach 100, ERP and Invoice stop at 80, Queue exposes the 20-unit exception, and only then does the incident become visible to the Agent workflow.

## Source architecture

The synthetic enterprise remains the authoritative demo environment. A staged-flow producer advances one deterministic batch per interval and commits the observation to the existing durable incident ledger before it becomes visible in the browser.

Each observation contains:

- `flow_run_id`
- `observation_index`
- `batch_id`
- `stage_counts.warehouse`
- `stage_counts.message_queue`
- `stage_counts.erp`
- `stage_counts.invoice`
- `unit_counts.total`
- `unit_counts.erp_recorded`
- `unit_counts.queue_failed`
- `captured_at`
- `authoritative: true`

The normal demo advances in 20-unit batches until all stage counts reach 100. The incident demo advances through the same sequence, but the final 20-unit batch remains in the Message Queue and never increments ERP or Invoice. The producer must be deterministic, restart-safe, and derived from persisted observation index rather than browser time.

## Timing

- Default demo interval: 1.5 seconds.
- The first observation is committed before the scenario response is returned.
- Stage movement is staggered by persisted observations, not `setTimeout` calls in the UI.
- Tests may inject a zero-delay clock/driver; production demo behavior retains the visible interval.

## Truth boundaries

- JavaScript never invents stage quantities or advances the flow independently.
- CSS animation may interpolate between the previous and newly received authoritative value, but the displayed destination value must come from the ledger event.
- Existing inventory truth (`100 expected`, `80 recorded`, `20 gap`) and recovery verification remain unchanged.
- Direct incident deep links replay available authoritative history. They do not fabricate an unseen healthy baseline.

## Components

### Staged flow producer

Extends the existing telemetry publisher with deterministic per-stage cumulative counts. It owns progression and persistence only; it does not own incident diagnosis.

### Dashboard projection

Reads `stage_counts` from telemetry history, chooses the latest authoritative observation, and projects one quantity per operational node. When older payloads omit `stage_counts`, it falls back to the existing snapshot counts without animation.

### Node transition treatment

Uses interruptible CSS transitions on number opacity/transform and node background. Dynamic numbers use tabular figures. Reduced-motion mode updates values and color instantly.

### Reconciliation chart

Consumes the same ordered points. During a live run it appends one point per observation and does not backfill future stage values.

## Failure handling

- If the stream disconnects, progression stops visually and the existing paused state remains visible.
- Reconnection resumes from the durable SSE cursor without replaying node animations twice.
- Duplicate ledger events are ignored by sequence/idempotency key.
- Missing or malformed stage counts fall back to the last valid authoritative projection.

## Test seams

The approved public seams are:

1. Scenario API and event stream: a normal run emits monotonically increasing persisted stage counts; an incident run ends at `100 / 100 / 80 / 80` with a 20-unit queue exception.
2. Browser Dashboard: operational nodes contain no horizontal throughput connector elements and update only after new SSE observations.
3. Reconnection: a refreshed browser resumes the same persisted progression without counter regression or duplicate events.
4. Accessibility: reduced-motion mode preserves state/color/label feedback and changing numbers remain stable with tabular numerals.

## Non-goals

- No front-end-only fake counter loop.
- No random quantities or random timing.
- No change to manager authority, recovery policy, Agent diagnosis, or external SaaS evidence contracts.
- No decorative particles or lines passing through operational node content.

## Acceptance criteria

- The healthy path visibly grows from its first batch to 100 using ledger-backed observations.
- The incident path visibly grows and then stops at a 20-unit pre-ERP discrepancy.
- Dashboard nodes, chart, and event rail show the same observation within one render cycle.
- No horizontal line or particle exists between Warehouse, Message Queue, ERP, and Invoice.
- Refresh/reconnect cannot move a stage counter backward.
- Existing JavaScript, Python, browser-geometry, and private competition-audit checks pass.
