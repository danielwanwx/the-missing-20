# Award-Ready Case Console Polish Design

**Status:** approved by the project owner on 2026-09-04
**Scope:** the judge-facing Case Console and its existing real Strands workflow
**Goal:** make one truthful end-to-end case legible in a five-minute recorded demo

## Decision

The Dashboard becomes a single Case Console built around one visible sequence:

1. an operational signal exposes an unexplained discrepancy;
2. a real read-only Strands agent selects and reads scoped evidence;
3. deterministic policy converts the evidence into a bounded proposal;
4. a Manager intervenes only at the material decision boundary;
5. the local demo-tenant executor applies one idempotent recovery;
6. an authoritative reread produces an inspectable Resolution Packet.

The Console must not present several equally prominent diagrams. Existing legacy
views remain available only as compatibility or engineering evidence; they are
not part of the judge-facing hero route.

## Information architecture

The main case surface has three columns and one outcome rail.

### 1. Signal and source receipts

The left column answers, “What changed, and where did it come from?” It shows the
case identifier, the 100/80/8/12 quantity state, invoice hold, and compact source
receipts. Every source receipt exposes:

- provider name;
- source authority;
- freshness or observation time;
- record identifier;
- connected, unavailable, stale, or contradictory status.

The signal must not reveal the root cause. It should communicate an operational
symptom that justifies investigation.

### 2. Strands investigation

The center column is the visual focus. It shows only server-emitted activity from
the persisted event stream:

- run started;
- each tool selected by Strands;
- each scoped read completion;
- admitted evidence identifiers;
- competing hypotheses and eliminated alternatives;
- final advisory disposition;
- provider, model, latency, and bounded token usage in an expandable trace.

Tools not selected by the agent remain visible as “not needed,” not as completed
reads. The UI must never generate fake activity, inferred tool calls, or timed
placeholder events.

### 3. Human decision boundary

The right column appears only when deterministic policy reaches a material
decision. For the hero case it presents one exact Manager approval packet:

- post the unresolved 12-unit receipt;
- transfer the approved 8-unit quality lot;
- revalidate the linked invoice;
- bind the action to the current case version, evidence tuple, and idempotency
  key.

The Manager can approve, reject, or request evidence. Normal read-only steps run
without interruption. Missing, stale, or contradictory evidence disables
execution and changes the required action to evidence collection or safe stop.

### 4. Outcome rail

The bottom rail stays compact until execution begins. After verification it
shows `VERIFIED`, the 80-to-100 state transition, invoice release state, and a
single control that opens the Resolution Packet. It is not another dashboard.

## Resolution Packet

The packet is the business-native output of the workflow, not a model transcript.
It contains:

- case and source correlation tuple;
- admitted evidence with provider and record IDs;
- Strands tool trace and model provenance;
- deterministic policy decision;
- Manager attestation;
- approved quantities: 12 receipt units and 8 quality-transfer units;
- execution receipt and idempotency key;
- pre-state and authoritative post-state;
- verification result and timestamps.

Model prose remains advisory. It cannot grant approval, execute a provider
effect, or upgrade an unverified case to success.

## State and interaction model

The primary states are:

`SIGNAL` → `INVESTIGATING` → `PLAN_READY` → `MANAGER_REVIEW` → `EXECUTING` →
`VERIFYING` → `VERIFIED`.

Safe branches are first-class:

- `NEEDS_EVIDENCE`: required source missing or stale; no execution control;
- `PROTECT`: physical shortage or quality risk; preserve holds;
- `RECONCILE_ONLY`: provider effect already exists; prevent retry;
- `STOPPED`: operator paused the investigation; preserve evidence and cursor;
- `DEGRADED`: real Strands unavailable or validation failed; deterministic
  controls remain but no AI-success claim is shown.

The operator can inspect evidence and chat with the agent at any state. Chat uses
the same read-only source tools and current persisted case projection. A stale or
contradictory answer fails closed visibly.

## Realtime behavior

SQLite remains the durable local case ledger. The case-scoped SSE endpoint is
the only source of animated activity. The browser may animate a newly received
event, but it may not create an event, advance case state, or simulate a tool
read. Reconnection uses the last event sequence and replays only missing server
events.

New events briefly change the relevant source, agent, or outcome accent color.
Motion remains restrained: one active highlight at a time, no decorative pulses
when the stream is idle, and reduced-motion support preserves all state changes
without animation.

## Truth and provenance

The hero route may claim:

- real Bedrock Nova Pro invocation through the Strands SDK when the run record
  contains provider metadata and tool calls;
- a disclosed synthetic enterprise demo tenant;
- local idempotent execution and authoritative synthetic reread;
- Manager-governed recovery and a durable Resolution Packet.

It may not claim live external SaaS writes, production customer data, AgentCore
Gateway or Policy, or production impact without separate provider evidence.
Provider-backed reads must show their returned record IDs and provenance; fixture
data must remain explicitly labelled synthetic.

## Component boundaries

- `CaseConsoleProjection` assembles the current read model and contains no
  provider I/O.
- `CaseActivityStream` replays persisted server events by sequence.
- `StrandsInvestigationGateway` owns real read-only model/tool invocation and
  fail-closed validation.
- `DecisionPolicy` owns executable disposition and never consumes model prose as
  authority.
- `ManagerDecision` binds one human decision to one case version and packet.
- `DemoTenantExecutor` owns the bounded local effect and idempotency.
- `ResolutionPacketBuilder` owns immutable pre/post evidence and provenance.
- UI components consume these projections; they do not infer business state.

## Testing strategy

### Contract tests

- tool events reflect the exact model-selected call list;
- all citations belong to admitted evidence;
- Agent events are read-only;
- only Manager and executor events may mutate the local tenant;
- recovery scope survives post-state mutation;
- stale case versions and reused or changed idempotency keys fail closed.

### State-matrix tests

Exercise recovery-ready, recovery-complete, needs-evidence, protect,
reconcile-only, safe-noop, deny, hard-stop, provider-unavailable, validation
failure, pause/resume, duplicate execution, and restart recovery.

### Browser acceptance

- a fresh hero run visibly advances only from SSE events;
- every active highlight maps to the received event sequence;
- one Manager approval enables the exact bounded action;
- the verified packet shows 12 receipt units, 8 quality units, and 80→100;
- evidence loss removes execution affordance;
- refresh and server restart restore identical case state;
- legacy two-role controls are absent from the hero route;
- reduced-motion mode remains fully understandable.

### Real-provider acceptance

At least one recorded acceptance run must show a real Strands invocation,
provider/model provenance, conditionally selected source tools, cited evidence,
Manager approval, idempotent local execution, and verification in the same case
record. Provider failure must remain visible and must never be replaced by a
scripted success.

## Completion criteria

This polish is complete when a reviewer can understand the case, identify what
the agent actually did, see why a human was required, inspect the resulting
business artifact, and distinguish real provider activity from synthetic tenant
effects without narration or hidden context.
