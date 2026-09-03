# Agent Platform Case Console Design

## Goal

Replace the current diagram-heavy dashboard with a case-first agent platform.
The product must make a recorded demo legible as a real multi-SaaS investigation:
ERPNext, Airtable, Jira, Celigo, and Slack are connected systems; an autonomous
agent reads them, explains its reasoning through a live activity ledger, and
executes a bounded cross-system remediation for the Missing 20 case.

## Product contract

The primary view is one case, not a generic control room. It contains:

1. A compact case header: correlation ID, anomaly, severity, and lifecycle.
2. Five connected-system cards, one per source. Each card shows its connection
   state, most recent correlated record, last action, and a linkable evidence
   detail drawer.
3. A central Agent Console, with conversation, current intention, current tool
   call, findings, and a single action to start autonomous diagnosis.
4. A Live Activity feed ordered by immutable server events. Source reads,
   synthesis, writes, and authoritative rereads appear in that one feed.
5. A concise Recovery panel showing the remediation plan, per-system effects,
   verification, and any unresolved boundary.

There is no Route Signals view, duplicated system-health panel, duplicate trend
charts, duplicate topology, or explanatory grey-copy block. A small case
timeline may remain only when it renders events already present in the ledger.

## Systems and roles

| System | Agent read | Bounded case write | Proof in UI |
| --- | --- | --- | --- |
| ERPNext | Purchase order, receipt, quality hold, invoice hold | Update only the demo receipt/quality disposition and linked invoice hold | before/after documents and reread |
| Airtable | Release registry record | Update disposition and remediation timestamp on the correlated record | correlated record revision |
| Jira | CAPA issue associated with the correlation ID | Update CAPA status and add a bounded remediation summary | issue state and audit event |
| Celigo | Named integration flow and latest controlled run | Run the named controlled flow only | run status, source/destination counts |
| Slack | Correlated incident notices | Post a concise state transition to the controlled channel | message timestamp and reread |

All requests are server-owned. Browser payloads contain only the correlation-
scoped projection, safe summaries, record IDs, status, timing, and audit
metadata; never credentials or raw provider payloads.

## Autonomous diagnostic loop

1. Detect the correlated ERPNext hold.
2. Start an agent run from the Case Console.
3. Read the five system adapters in a declared order or in safe parallel where
   independent. Every call emits `tool.read.started` and `tool.read.completed`.
4. Produce a causal hypothesis that cites returned record IDs. The UI allows the
   user to ask why a tool was chosen or why a conclusion follows.
5. Generate the bounded remediation plan. The Agent can execute it for this
   dedicated demo correlation ID only.
6. Emit `tool.write.started` and `tool.write.completed` for each provider
   mutation, then reread all providers.
7. Mark the case `RESOLVED` only after the required authoritative postconditions
   agree; otherwise remain `BLOCKED` with the exact provider and reason.

The ledger assigns sequence numbers and idempotency keys. Replaying a run can
render past activity but cannot execute a second write.

## State model and failure behavior

`NORMAL → DETECTED → DIAGNOSING → PLAN_READY → EXECUTING → VERIFYING →
RESOLVED`, with `BLOCKED` reachable from every live phase. A source failure does
not become a fabricated success: its card turns degraded, the activity feed
records the read failure, and the agent names the dependency in its reply.

The Agent may autonomously execute only the named demo correlation ID and only
the mutations enumerated in this document. Any out-of-scope identifier is
rejected server-side and produces a visible `BLOCKED` result.

## Implementation boundaries

- Create a provider-neutral tool gateway and adapter contracts for correlated
  read, plan, execute, and verify operations.
- Keep source adapters independently testable; compose them only in a case-run
  coordinator.
- Preserve existing local synthetic lifecycle tests while adding an external
  case-console mode that never claims an external write without a provider
  result.
- Rebuild the Dashboard and Agent Workspace around the Case Console rather
  than layering another card row onto the existing diagrams.

## Acceptance tests

1. Normal case: all five cards show the current correlated source state.
2. Incident: ERPNext holds 8 of 20; the feed shows the real reads and the Agent
   forms a cited diagnosis without displaying a prefilled answer.
3. Recovery: each write is case-scoped, logged, reread, and idempotent.
4. Degraded provider: source-specific failure and `BLOCKED` remain visible.
5. Browser QA: no console errors, live activity advances from real ledger
   events, all five cards are readable at recording resolution, and removed
   diagrams are absent.
6. Safety QA: no credential reaches the browser and no second replay creates a
   provider write.
