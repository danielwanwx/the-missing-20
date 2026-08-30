# The Missing 20 — Live Control Loop UI Rebaseline

Date: 2026-08-29
Status: approved visual direction; implementation pending

## 1. Outcome

Rebuild Dashboard and Agent Workspace as two views of one live incident lifecycle. The experience must show real event movement, an incident forming, automatic agent investigation, human interaction, controlled recovery, and verified return to normal. It must not read like a static report.

The selected visual targets are the three user-provided dark control-tower canvases:

- Dashboard follows the supply-chain flow and live control-tower composition.
- Agent Workspace follows the central orchestrator, investigator network, synthesis, safety, approval, recovery, verification, chat, and activity composition.
- Existing colors, Phosphor icon library, typography, and dark visual language remain; the topology and information hierarchy are restructured.

## 2. Product Story

The five-minute judge journey is one continuous system:

1. Live enterprise and public-source telemetry flows through the Dashboard.
2. A real source condition or explicit demo injection creates a measurable discrepancy.
3. The detector creates an incident automatically.
4. The orchestrator activates three investigator roles.
5. Investigators call bounded tools, return evidence, and hand findings to synthesis.
6. The operator can select an agent and ask role-specific questions.
7. Deterministic controls evaluate safety and action eligibility.
8. Two distinct human roles approve each controlled effect.
9. Recovery executes, authoritative state is reread, and verification closes the loop.
10. The same Dashboard flow visibly returns to healthy values.

No view may invent a second lifecycle or use independent display-only numbers.

## 3. Shared Truth Model

Both views consume the same snapshot plus ordered SSE event ledger.

### Authoritative data

- Warehouse, queue, ERP, invoice counts
- Incident identity and lifecycle state
- Agent, tool, evidence, synthesis, and evaluator events
- Recovery preparation, approvals, execution, verification, and replay
- NWS, NOAA, and optional AIS observations

### Truth boundaries

- Public-route observations are context, not enterprise causality.
- Nova advisory status and citation coverage remain separate from application-side validation.
- AI never grants, authorizes, or executes recovery.
- Decorative animation cannot advance state. Every meaningful pulse must correspond to an SSE event or live-source sample.
- If the stream disconnects, motion pauses and the UI says disconnected.

## 4. Dashboard

### 4.1 Primary composition

The first viewport is diagram-first:

- Compact top navigation and live connection indicator
- Left rail with active agents only when an incident exists
- Large horizontal flow: Warehouse → Message Queue → ERP → Invoice
- Animated record particles moving along component-to-component paths
- Exact quantities attached to nodes, not explained in prose
- A live series directly below the flow showing expected, recorded, and gap
- Three compact lower panels: incident history, component health graph, reconciliation chart

The current duplicate system-status, flow-state, provenance, and explanatory cards are removed from the primary viewport. Provenance remains available from a compact details drawer.

### 4.2 Live state

- Healthy: cyan/lime record pulses traverse the full path.
- Degrading: affected edge slows and backlog accumulates visibly.
- Incident: the failed node and edge turn coral; failed-unit particles divert into a visible backlog branch; the gap series grows.
- Recovery: approved effects pulse lime from control loop back into the affected component.
- Verified: all 100 records reconnect across the entire path and the incident moves to history.

### 4.3 Incident entry

The Dashboard contains one compact `Live / Inject incident` demo control. It is not a duplicate navigation button. It calls the existing scenario API and is disabled when the authoritative lifecycle does not permit injection.

On detection, the Dashboard automatically exposes `Open investigation` once. Navigation in the top bar remains the normal way to switch views.

### 4.4 External signals

NWS, NOAA, and optional AIS are drawn as source nodes feeding a route-risk detector. New samples create short source-to-detector pulses. They never connect directly to a root-cause claim without admitted enterprise evidence.

## 5. Agent Workspace

### 5.1 Closed-loop topology

Replace the current radial fan-in with an explicit loop:

`Incident packet → Orchestrator → Investigator roles → Synthesis → Safety Gate → Two-role Approval → Controlled Recovery → Verification → Operational flow`

Three source groups feed the investigators:

- Queue logs, dead-letter records, consumer configuration
- ERP receipts, warehouse scans, material documents
- Invoice state, duplicate-posting records, policy facts

Every connector terminates on visible component ports. The verification edge returns to the operational flow so the graph visibly closes.

### 5.2 Agent roles and statuses

Visible roles:

- Orchestrator
- Receipt Retry Investigator
- Shipment Evidence Investigator
- Duplicate Posting Investigator
- Synthesis

Valid statuses derive from the event ledger:

- MONITORING
- TRIGGERED
- INVESTIGATING
- WAITING FOR EVIDENCE
- HANDOFF
- COMPLETE
- DEGRADED

`IDLE` is not the main healthy-state message. In healthy state, the orchestrator displays `MONITORING`, while investigators remain visually quiet until activated.

Selecting an agent highlights only its evidence and handoff path, filters live activity, changes the chat role, and displays its latest task in a compact popover or rail state.

### 5.3 Event-driven motion

- telemetry/source sample: blue pulse
- incident detection: coral pulse
- tool call/evidence returned: cyan pulse
- handoff/synthesis: violet-to-cyan pulse
- approval/recovery: amber/lime pulse
- verification/closed loop: lime pulse completing the full return path

The event feed and topology share the same event sequence. Pulses are not generated on timers without data.

### 5.4 Right rail

Only one rail section is expanded at a time:

- Context: selected agent, current task, one hypothesis, latest evidence count
- Chat: compact conversation, citations, role-specific suggested question
- Decision: proposed action, safety result, quorum, execute/verify state

Live Activity becomes a collapsible bottom drawer. Full immutable trace, provenance, token totals, protocol versions, zero-value counters, waiting explanations, and repeated status badges are not shown by default.

Healthy state shows only:

- `Monitoring live sources`
- current source freshness
- `Run incident demo` action

### 5.5 Chat boundary

Chat sends the selected role and current incident to the existing backend endpoint. Responses must show:

- responding role
- concise answer
- evidence citations
- visible refusal when asked to approve, authorize, or execute

Chat is enabled only when a real incident context exists. Healthy-state prompts explain how to start the incident demo without fabricating an answer.

## 6. Scenario Lab

Scenario Lab remains an advanced source-condition console. It is not required for the primary judge path.

- Normal, Incident, Recovery derive from the same authoritative session state.
- It can show source adapters and sample timestamps.
- It must not contain an alternate incident lifecycle.

## 7. Copy Reduction

Keep labels that answer one of four questions only:

1. What is happening?
2. Where is it happening?
3. Who or what is working?
4. What action is available next?

Remove:

- repeated `live`, `expected`, `synthetic`, `trace`, and protocol explanations
- sentences restating visible quantities
- empty `none yet`, `waiting`, and zero-counter grids
- duplicate navigation CTAs
- persistent technical disclosure text from the primary canvas

Required truth disclosures remain adjacent to the AI result and are expressed as compact facts:

- Nova advisory coverage
- application validation coverage
- deterministic recovery authority

## 8. Responsive Behavior

- Desktop ≥ 1280px: complete canvas and rail visible.
- Tablet 768–1279px: rail becomes an overlay drawer; topology remains a single scrollable canvas.
- Mobile < 768px: Dashboard flow becomes a vertical sequence; Agent Workspace becomes staged cards with the same lifecycle order. No overlapping nodes or clipped connectors.

## 9. Failure Handling

- SSE disconnect: freeze event-driven motion, show `Disconnected`, retain last authoritative snapshot.
- Unknown incident: fail closed; no operational success claims.
- Provider failure: show degraded advisory, preserve deterministic controls.
- Missing lifecycle record: display unverified/missing; never fabricate approvals, execution, or closure.
- Public source unavailable: mark that source unavailable without blocking enterprise detection.

## 10. Implementation Boundaries

Primary files:

- `workspace/index.html`
- `workspace/style.css`
- `workspace/app.js`
- `scripts/decision_workspace_server.py` only if the existing API lacks a required projection
- focused JS/Python tests and browser smoke

Do not change the authority model, recovery semantics, AWS runtime, evidence catalog, or provider contract as part of this UI rebaseline.

## 11. Acceptance Gates

### Visual fidelity

- Dashboard and Agent Workspace visibly match the selected Canvas compositions at a comparable desktop viewport.
- No loose connector ends, accidental line crossings, overlapping labels, or unexplained empty regions.
- Right-rail copy is materially reduced.

### Real-time behavior

- Browser begins in a visibly live healthy state.
- Ordered SSE samples visibly move through the Dashboard.
- Incident injection creates 80/20 state through the API and detector.
- The Agent Workspace activates roles according to real ledger events.
- Tool, evidence, handoff, synthesis, approval, recovery, and verification pulses correspond to recorded event sequence IDs.
- Recovery returns the Dashboard to 100/0/100/100 without reload.

### Interaction

- Every visible primary button has a meaningful state transition or panel.
- Selecting every Agent changes graph highlight, context, activity, and chat role.
- Role chat answers current-case questions with citations and refuses operational authority.
- Keyboard focus, reduced motion, disconnected stream, and narrow viewport are tested.

### Truth and competition review

- Nova advisory and deterministic application facts remain separate.
- No static demo-only success claim appears without artifact evidence.
- Independent judge completes Normal → Incident → Investigation → Chat → two quorums → Recovery → Verified.
- Full Python, JS, lint, type, browser smoke, package audit, and five-minute demo gates pass.

## 12. Delivery Sequence

1. Rebuild shared event-to-visual projection and component ports.
2. Rebuild Dashboard composition and real-time incident transition.
3. Rebuild Agent Workspace closed-loop topology and statuses.
4. Collapse and simplify the right rail.
5. Verify chat, two-role recovery, and return-to-normal.
6. Run visual comparison, browser E2E, and independent competition review.
