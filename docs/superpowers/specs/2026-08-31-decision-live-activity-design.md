# Decision Execution and Live Activity Design

Date: 2026-08-31

## Goal

Make the recovery decision visibly and truthfully progress after the user selects Execute. The interface must prove that the backend is reading authoritative sources, applying a bounded recovery, and verifying the result. It must not simulate progress with timers, looping animation, or invented log entries.

## Current Problem

The current decision request is synchronous. The browser waits while the server performs the recovery and then receives one final snapshot. Live Activity is collapsed during that wait, so the user sees no intermediate state. A subsequent pending action can also replace the completed action quickly, making Execute appear to have changed nothing.

The current approval model also requires two specialized roles. For this demo, that governance cost obscures the core story. The approved design uses one human role named `Manager` while preserving the rule that an agent cannot authorize its own production change.

## User-Facing Workflow

The recovery lifecycle is:

1. **Read** — the system reads Queue, ERP, and Invoice state.
2. **Investigate** — agents form hypotheses and return evidence through read-only tools.
3. **Policy** — deterministic code classifies the incident and prepares a versioned, immutable recovery intent.
4. **Manager** — one Manager approves that exact intent.
5. **Execute** — the server accepts the approved intent and starts a bounded asynchronous worker.
6. **Apply** — the worker performs the idempotent recovery action, such as replaying a failed receipt message or releasing an eligible invoice.
7. **Verify** — the worker reads authoritative state again and checks the recovery postconditions.
8. **Closed** — the incident closes only after verification succeeds.

Agents remain advisory. Deterministic policy creates the operational decision, Manager supplies the sole human approval, and the controlled worker owns mutations.

## Manager Approval

The Decision panel exposes one `Approve as Manager` action. Manager approves an immutable intent containing:

- the exact recovery tool and action;
- the bounded Queue, ERP, or Invoice records in scope;
- the expected case version;
- the idempotency key;
- the deterministic policy result;
- the safety-stop and verification conditions.

Approval cannot authorize a different action, a broader record set, a stale case version, or an action rejected by deterministic policy. Any material change requires a newly prepared intent and a new Manager approval.

## Asynchronous Execution Contract

`POST /api/v1/incidents/{incident_id}/decisions` with `command: "execute"` validates the approved intent, reserves execution idempotently, starts the recovery worker, and returns `202 Accepted` without waiting for recovery completion.

The response contains the incident identity, intent ID, execution ID, accepted status, and the latest durable event sequence. Repeated submission with the same idempotency key returns the existing execution identity and never creates a second effect.

The worker emits durable events at the actual operation boundaries. The minimum execution vocabulary is:

- `execution.accepted`
- `execution.started`
- `source.read.started`
- `source.read.completed`
- `policy.checked`
- `effect.started`
- `effect.completed`
- `verification.started`
- `verification.completed`
- `execution.completed`

Failure events use the corresponding failed status and include a bounded error code and safety-stop reason. Events must not expose credentials, prompts, or unrestricted payloads.

Every UI-visible activity row is derived from a persisted backend event. The client does not manufacture progress events.

## Decision Panel States

The four visible stages become:

1. Prepare
2. Manager
3. Execute
4. Verify

The status badge progresses through:

`NOT PREPARED → AWAITING MANAGER → APPROVED → EXECUTING → APPLYING RECOVERY → VERIFYING → VERIFIED · CLOSED`

The Execute button disables immediately after acceptance and shows the current execution state. Completion does not disappear merely because another possible action exists; the completed intent remains visible, and any next action is presented separately as not prepared.

## Persistent Live Activity Rail

The right rail keeps Decision in its upper section. Selecting Execute automatically opens Live Activity beneath it.

The feed includes both durable business events and actual read operations:

- Queue, ERP, and Invoice reads;
- evidence returned by read-only tools;
- deterministic policy checks;
- Manager approval;
- execution acceptance and worker start;
- committed recovery effects;
- authoritative verification reads and results.

New events enter at the top, slide down quickly into place, and receive one short highlight. Existing rows move downward. There is no looping animation and no replay disguised as live execution. Each row shows the operation, result, timestamp, and, when available, bounded metadata such as duration, record count, execution ID, or request ID.

Evidence Returned and Full Immutable Trace remain expandable below the main feed. The default feed stays concise; the trace preserves the complete durable sequence.

## Streaming and Recovery

The existing server-sent event connection remains the transport. Each event carries a monotonically increasing sequence. The client persists its latest rendered sequence and resumes from that cursor after a disconnect or reload.

While disconnected, Live Activity displays `PAUSED` and stops motion. After reconnection, missing persisted events are inserted in sequence and marked as recovered history, not presented as events that occurred at the moment of reconnection.

## Error Handling

- **Policy rejection:** show `BLOCKED`; do not start a worker.
- **Stale case version:** show `STALE INTENT`; require Prepare and Manager approval again.
- **Execution failure:** show `EXECUTION FAILED`; preserve all committed events and the bounded safety-stop reason.
- **Stream loss:** show `PAUSED`; resume from the durable cursor.
- **Verification failure:** show `VERIFICATION FAILED`; never show Closed.
- **Duplicate Execute:** return the reserved execution and create no duplicate effect.

Errors remain visible in both the Decision panel and Live Activity. The topology animation may reflect an active event, but it is never the only representation of state.

## Implementation Boundaries

The change should preserve the existing incident ledger, SSE transport, snapshot projection, and controlled recovery services. The focused implementation areas are:

- replace two-role approval projection and controls with one Manager approval;
- split execution acceptance from worker completion;
- persist operation-level read, effect, and verification events;
- project intermediate execution states in snapshots;
- keep Live Activity open during execution and animate newly received rows;
- retain completed intent context when a later decision becomes available.

No new polling subsystem, fabricated client-side narrative, or unrelated topology redesign is in scope.

## Testing and Acceptance

Automated coverage must verify:

- one Manager approval grants the exact prepared intent;
- an unapproved, stale, or policy-rejected intent cannot execute;
- Execute returns promptly with an accepted execution identity;
- the worker produces ordered durable operation events;
- duplicate Execute calls are idempotent;
- successful recovery progresses through Execute and Verify to `VERIFIED · CLOSED`;
- execution and verification failures remain truthful and do not close the incident;
- SSE reconnect resumes from the last sequence without gaps or duplicate rows;
- Live Activity opens automatically and renders only persisted events;
- a new event enters from the top and receives a one-time highlight;
- refresh reconstructs Decision and Live Activity from durable backend state.

The browser smoke test must exercise the complete Manager approval and Execute path while observing at least one Queue/ERP/Invoice read, one committed effect, and one verification result in Live Activity.
