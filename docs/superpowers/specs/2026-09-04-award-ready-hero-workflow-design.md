# Award-Ready Hero Workflow Design

**Status:** approved by the project owner on 2026-09-04  
**Purpose:** turn the Case Console into the single, truthful, recoverable
competition demo path.

## Decision

The only hero flow is **one Manager approval for a bounded recovery**.  Legacy
two-role material remains testable as compatibility evidence, but is not shown
as the Case Console authority model or described as the primary demo.

The primary path is:

1. A human opens a fresh scoped receipt case and explicitly starts an
   investigation.
2. A real read-only Strands investigator receives the case tuple and chooses
   from scoped evidence tools.  It may ask for further evidence or stop;
   it cannot approve, execute, or fabricate provider effects.
3. The server validates model output, persists each planned/read/finding event,
   and emits it to the UI.  Deterministic policy derives the only executable
   recovery proposal from authoritative evidence.
4. The Manager approves, rejects, or requests evidence against the exact case
   version and evidence tuple.  Only approval enables the demo-tenant executor.
5. The executor applies one idempotent effect, rereads the sources, and issues a
   durable Resolution Packet with source record IDs and provenance.

## Runtime modes

`synthetic` is a disclosed, resettable enterprise demo tenant.  `live` reads
only authorized providers and always labels provenance.  Neither mode may
silently substitute data, and external writes remain disabled unless an
explicitly selected demo tenant enables the guarded executor.

## Persistence and realtime contract

Case state is stored in a local SQLite-backed case ledger: case version,
append-only activity events, Manager decision, idempotency key, execution
receipt, and Resolution Packet survive server restart.  A case-scoped SSE feed
delivers exactly those server events to the Console; reconnects use a cursor and
must never generate client-side fake events.  Polling may refresh health but not
simulate agent activity.

## Truth boundaries

- The UI calls a diagnosis "Strands investigation" only if its persisted run
  contains an actual successful model invocation and its tool trace.
- A deterministic fallback is visibly `DEGRADED`; it cannot be presented as
  autonomous reasoning.
- Source records, tool sequence, model invocation ID, policy decision,
  approval, effect ID, and verification reread appear in the packet.
- A Manager identity in the demo is a declared demo persona, not production
  authentication.

## Acceptance criteria

1. A clean one-command startup selects source mode, initializes a fresh case,
   serves the Console, and exposes a health check.
2. Browser E2E shows event-by-event investigation activity from SSE, a human
   stop/reconnect, and restored case state after restart.
3. The hero run proves a real Strands invocation, conditionally selected source
   tools, citations/record IDs, policy gate, one Manager approval, idempotent
   effect, and source reread in one durable packet.
4. A missing, stale, contradictory, or unavailable source produces
   `NEEDS_EVIDENCE`/safe stop with no execution affordance.
5. Legacy two-role UI is not reachable from the Case Console route; all primary
   product copy and evidence packet use the Manager-only contract.
