# Real-Time Dashboard and Agent Workspace Implementation Plan

**Date:** 2026-08-28  
**Status:** Approved for implementation  
**Design source:** `docs/superpowers/specs/2026-08-28-dashboard-agent-workspace-redesign.md`

## Outcome

Deliver a judge-ready local product with two persistent views, **Dashboard** and
**Agent Workspace**, driven by one authoritative synthetic incident session. The exact
100 supply units, the Missing 20 anomaly, every agent/tool/handoff event, both human
approvals, the controlled effect, and the final 100/100 verification must be observable
through the application API and ordered event ledger.

The browser may animate a state transition only after receiving the corresponding API
snapshot or ledger event. Disconnecting the API stops progression and shows a visible
disconnected state.

## Non-Negotiable Boundaries

- Synthetic data only. Do not use private employer code, data, incidents, or runbooks.
- No new AWS or model-provider calls and no new spend.
- Do not claim stable real-Nova usefulness; preserve the existing disclosed-degradation
  language where provider status is shown.
- Deterministic code owns evidence integrity, action eligibility, authorization,
  execution, verification, and replay.
- Chat may investigate and prepare; it may not authorize or execute.
- Do not commit, push, publish, upload a video, or submit to Devpost during implementation.
- No unrelated refactor, dependency expansion, or optional polish loop.

## Vertical Slice 1: Authoritative Unit Truth

### Files

- `src/the_missing_20/domain/enterprise.py`
- `src/the_missing_20/ports/enterprise.py` if the port is separate
- `src/the_missing_20/adapters/synthetic_enterprise.py`
- focused unit and integration tests under `tests/`

### Work

1. Add a strict `SupplyUnit` model with stable unit identity, order/line identity,
   authoritative stage, status, source-message identity, and revision.
2. Persist 100 deterministic unit records in the synthetic enterprise database.
3. Seed units 001 through 080 as ERP-recorded and units 081 through 100 as stopped at the
   failed message queue.
4. Expose `list_units()` through the enterprise boundary.
5. Bind failed-message evidence to the exact 20 unit IDs.
6. In the approved recovery transaction, update exactly those 20 unit rows in the same
   transaction as the aggregate ERP quantity and effect record.
7. Reject unknown IDs, duplicate IDs, wrong cardinality, stale revisions, and repeated
   effects.

### Acceptance

- Before recovery: 100 stable IDs, 80 recorded, 20 stopped.
- After recovery: the same 100 IDs, all recorded, zero missing.
- Exactly one effect is recorded and replay produces no duplicate effect.
- A failed transaction cannot partially change units or aggregate quantities.

## Vertical Slice 2: Durable Experiment Session and Public Event Ledger

### Files

- new package `src/the_missing_20/experiment/`
- existing detector, agent harness, Authority B, executor, and verification seams
- focused tests under `tests/`

### Work

1. Introduce a durable local `ExperimentSession` with one incident ID, one trace ID, the
   case store, enterprise state, and a per-session lock.
2. Add a typed append-only `PublicIncidentEvent` ledger with a monotonic sequence separate
   from case version.
3. Emit events from actual operations, not timers: detection, investigation, agent start,
   tool start/completion, evidence return, handoff, synthesis, proposal, approval,
   execution, and verification.
4. Preserve event identity, case version, actor, status, timestamp, correlation IDs, and a
   redacted display payload.
5. Make replay from any accepted sequence deterministic and idempotent.

### Acceptance

- Concurrent investigator events receive unique server-assigned ordered sequences.
- Replaying the same ledger yields the same incident projection.
- An event gap, duplicate, or identity mismatch fails closed.
- Provider degradation appears as advisory status and never creates or blocks an
  operational grant.

## Vertical Slice 3: Local Experiment API and Streaming

### Files

- `scripts/decision_workspace_server.py`
- new API/session helpers under `src/the_missing_20/experiment/`
- server and integration tests under `tests/`

### Endpoints

- `GET /api/v1/incidents`
- `GET /api/v1/incidents/{incident_id}`
- `GET /api/v1/incidents/{incident_id}/units`
- `GET /api/v1/incidents/{incident_id}/events` using server-sent events
- `POST /api/v1/incidents/{incident_id}/chat`
- `POST /api/v1/incidents/{incident_id}/decisions`

### Work

1. Return incident ID, trace ID, case version, and projection sequence on every response.
2. Support SSE resume through `Last-Event-ID` or an explicit sequence query.
3. Serialize all state-changing commands under the session lock.
4. Add idempotency keys and immutable decision identity to POST commands.
5. Keep free-text chat read-only; accept approvals only as structured, role-bound decision
   commands.
6. Return explicit disconnected, stale-version, duplicate-command, missing-approval, and
   verification-failure responses.

### Acceptance

- Snapshot plus events reconstructs the same state as a fresh snapshot.
- Reconnect resumes after the last accepted sequence without inventing activity.
- Two approvals must bind to the same intent, case version, and parameter summary.
- The controlled executor cannot run with chat text, one approval, or a stale version.

## Vertical Slice 4: Shared Client Store and Dashboard

### Files

- `workspace/index.html`
- `workspace/app.js`
- `workspace/style.css`
- locally bundled visualization/icon dependencies only if already available or clearly
  necessary
- `tests-js/` and browser smoke tests

### Work

1. Create a shared client store that hydrates from the incident and unit endpoints, then
   applies ordered SSE events.
2. Add persistent `Dashboard / Agent Workspace` navigation without resetting the session.
3. Render the live business path from Warehouse to Message Queue to ERP to Invoice.
4. Render exactly 100 addressable unit elements from API unit records. Cluster visually
   when needed, but keep exact IDs and counts inspectable.
5. Drive queue anomaly, topology health, reconciliation series, incident state, and active
   investigator count from API data.
6. Stop unit motion and agent activity when the stream is disconnected or a sequence gap
   is detected.
7. Remove report-oriented cards, token/cost counters, redundant gray captions, and
   unexplained tags from the primary experience.

### Acceptance

- DOM and API both report 100 total, 80 recorded, 20 stopped before recovery.
- No business-state timer advances units or incident state.
- Selecting the incident opens Agent Workspace with the same incident and sequence.
- API shutdown visibly stops live motion.

## Vertical Slice 5: Agent Workspace and Incident Copilot

### Files

- `workspace/index.html`
- `workspace/app.js`
- `workspace/style.css`
- experiment chat/orchestration service
- JS, Python, and browser tests

### Work

1. Render the Orchestrator and three investigators as the central product surface.
2. Project agent status, tool calls, evidence packets, handoffs, synthesis, and proposal
   from ledger events.
3. Let selecting an agent or tool filter the activity and evidence views.
4. Add Incident Copilot with suggested prompts and free text. Stream responses together
   with cited evidence IDs and agent/tool events.
5. Add structured proposal and approval controls outside chat.
6. Display the deterministic safety gate, two-role approval, controlled recovery,
   verification, and replay as connected states.
7. Keep scripted advisory experience, deterministic safety proof, and unproven stable
   real-Nova usefulness visibly distinct without turning the screen into a disclaimer.

### Acceptance

- All three investigators, their actual tools, evidence, and handoff are visible from
  authoritative events.
- Chat answers cite evidence and cannot authorize or execute.
- Two distinct roles approve the same immutable action before execution becomes eligible.
- The exact Missing 20 units move only after the executor-completed event.
- Verification displays 100/100 and a single effect only after backend confirmation.

## Vertical Slice 6: End-to-End and Visual Quality Gates

### Automated scenario

1. Start the local experiment server.
2. Load Dashboard and assert 100 API-backed unit elements with 80/20 state.
3. Open Agent Workspace and start/inspect the investigation.
4. Assert three investigator starts, tool events, evidence returns, and synthesis handoff.
5. Ask a Copilot question and assert evidence citations.
6. Prepare recovery and record approvals from two distinct roles.
7. Execute once and verify exact 20-unit transition.
8. Assert API and DOM both show 100/100, one effect, and replay delta zero.
9. Return to Dashboard and assert the repaired path persists.

### Negative scenarios

- API disconnect freezes live motion.
- SSE duplicate or gap does not advance projection.
- Stale decision version is rejected.
- One approval or mismatched intent cannot execute.
- Repeated execution does not duplicate the effect.
- Provider-degraded state is truthful and does not affect deterministic authority.

### Required gates

- Focused Python and JS tests for each slice.
- Full Python suite and `npm test`.
- Golden v1, Golden v2, Safety Proof, workspace smoke, and judge demo gates.
- Browser E2E at the target viewport.
- Visual comparison of each built page with its approved target image.
- Root `design-qa.md` ending with `final result: passed`.
- Independent Chief Architect implementation review.
- Independent competition-judge review of product clarity, visible agent value, demo
  credibility, and honest capability claims.

## Implementation Governance

Implementation proceeds in bounded milestones. Luna owns the assigned code changes. The
primary agent reviews diffs and runs tests. An independent Chief Architect reviews each
material milestone. At most one focused correction is allowed per milestone; optional
polish is deferred. A reproducible defect that can falsely show authorization, execution,
verification, real-time activity, or provider capability is blocking.

