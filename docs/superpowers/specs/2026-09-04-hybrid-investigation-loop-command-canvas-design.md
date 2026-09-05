# Hybrid Investigation Loop and Borderless Command Canvas

**Date:** 2026-09-04

**Status:** Approved for implementation

**Scope:** One award-grade, provider-backed demo path plus the dashboard and Agent Workspace surfaces that expose it.

## 1. Objective

Turn The Missing 20 into a credible enterprise agent platform demonstration rather than a scripted dashboard. The same visible run must:

1. begin with normal activity in real demo SaaS tenants;
2. surface an indirect operational anomaly without revealing its cause;
3. let a Strands agent choose and execute the investigation across systems;
4. expose the agent's tool activity, evidence, hypotheses, and uncertainty in real time;
5. stop once for Manager approval only when a consequential write is ready;
6. execute an allowlisted, idempotent recovery;
7. independently reread authoritative records;
8. close with a durable Resolution Packet.

The data may be created for the competition, but the provider interactions, record identifiers, timestamps, API responses, state transitions, approval, write, and reread must be real within the controlled demo environment. No customer production data is required or claimed.

## 2. Research Basis

The design follows a consistent pattern across current official guidance:

- Anthropic distinguishes deterministic workflows from agents that dynamically choose actions and recommends the simplest architecture that is sufficient for the task. An orchestrator-worker pattern is useful when the necessary sources cannot be predicted in advance.
- Microsoft and Google recommend combining model-directed reasoning with deterministic workflow stages, explicit human checkpoints, persisted state, observability, and evaluation.
- OpenAI's Agents SDK makes tool approval, resumable run state, MCP approval, and end-to-end traces first-class concepts.
- Amazon Bedrock AgentCore Gateway provides a common tool surface, identity and policy enforcement, policy sessions, and structured observability.
- ServiceNow separates autonomous playbook activities from collaborative activities that pause for human review, and exposes task progress and decision logs during agent execution.

The dashboard direction borrows interaction principles, not a literal visual clone:

- NVIDIA Personal AI Router emphasizes a compact job-to-node relationship and progressive disclosure of detailed performance.
- Grafana separates view and edit modes, supports custom and automatic layouts, and allows expandable, draggable, and resizable panels.
- Datadog supports free-form real-time screenboards, collapsible groups, tabs, and full-screen widget inspection.
- Kibana uses collapsible sections, full-screen focus, grid snapping, and keyboard-accessible moving and resizing.

Primary references:

- https://www.anthropic.com/engineering/building-effective-agents
- https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
- https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns
- https://learn.microsoft.com/en-us/agent-framework/workflows/human-in-the-loop
- https://docs.cloud.google.com/architecture/choose-design-pattern-agentic-ai-system
- https://docs.cloud.google.com/vertex-ai/generative-ai/docs/agent-engine/evaluate
- https://openai.github.io/openai-agents-python/human_in_the_loop/
- https://openai.github.io/openai-agents-python/tracing/
- https://openai.github.io/openai-agents-python/mcp/
- https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy-core-concepts.html
- https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-configure.html
- https://www.servicenow.com/docs/r/build-workflows/workflow-studio/configure-agentic-playbooks.html
- https://www.servicenow.com/docs/r/build-workflows/workflow-studio/ai-agent-as-activity.html
- https://docs.nvidia.com/local-ai/nvpair/getting-started/
- https://grafana.com/docs/grafana/latest/visualizations/dashboards/build-dashboards/create-dashboard/
- https://docs.datadoghq.com/dashboards/
- https://www.elastic.co/docs/explore-analyze/dashboards/arrange-panels
- https://d3js.org/d3-shape/link
- https://developer.mozilla.org/en-US/docs/Web/Performance/Guides/Animation_performance_and_frame_rate

## 3. Chosen Architecture

Use one **Hybrid Investigation Loop** instead of a theatrical swarm of SaaS-specific agents.

### 3.1 Model-owned responsibilities

The Strands Investigation Orchestrator may:

- interpret an incident objective;
- select from allowlisted read tools;
- decide which sources should be read next;
- run independent reads concurrently;
- create and revise competing hypotheses;
- identify missing or contradictory evidence;
- ask the user a targeted question when the systems cannot supply essential context;
- produce a typed diagnosis candidate and bounded recovery proposal;
- answer questions about the current run without mutating provider state.

### 3.2 Application-owned responsibilities

Deterministic components own:

- source authentication and credential scoping;
- record correlation and evidence admission;
- event ordering and persistence;
- freshness calculation;
- policy evaluation;
- approval state;
- mutation allowlists;
- idempotency;
- execution limits;
- authoritative postcondition verification;
- closure and Resolution Packet integrity.

The model cannot assert that a write happened, approve its own plan, supply a target status, manufacture evidence, or mark a case resolved.

### 3.3 Runtime shape

```text
Provider events / scheduled polling
              |
              v
       Incident detector
              |
              v
  Strands Investigation Orchestrator
       |         |          |
       +---------+----------+
        typed read-only tools
       |     |      |      |      |
   ERPNext Airtable Celigo Jira  Slack
              |
              v
 Evidence registry + hypothesis ledger
              |
              v
 Deterministic policy and recovery compiler
              |
              v
     Manager approval checkpoint
              |
              v
      Idempotent bounded executor
              |
              v
 Independent provider reread and verifier
              |
              v
         Resolution Packet
```

The same orchestrator boundary used by the local console must run in AgentCore Runtime for the final proof. At least one provider tool in the hero run must be invoked through AgentCore Gateway and produce policy and trace attribution. The remaining provider tools use the same typed adapter contracts through official APIs or trustworthy MCP servers. The UI and Resolution Packet state the actual transport for every tool rather than labeling every integration as MCP.

## 4. Demo SaaS Roles

The hero case uses controlled demo tenants and provider-backed records:

| System | Role | Authority in the case |
|---|---|---|
| ERPNext | Purchase receipt, stock movement, invoice and inventory record | Financial and inventory posting authority |
| Airtable | Quality release registry | Quality disposition authority |
| Celigo | Integration flow run, acknowledgement and retry state | Cross-system delivery authority |
| Jira | Exception/CAPA work item | Investigation and remediation work authority |
| Slack | Shift context and final operational notification | Human context and communication evidence |

Every admitted provider observation uses a common envelope:

```json
{
  "evidence_id": "stable digest",
  "provider": "erpnext|airtable|celigo|jira|slack",
  "record_type": "provider-native type",
  "record_id": "provider-native identifier",
  "authority": "business meaning owned by this record",
  "source_updated_at": "provider timestamp",
  "observed_at": "UTC ingestion timestamp",
  "freshness": "fresh|stale|unknown",
  "transport": "api|mcp|webhook|poll",
  "payload_digest": "canonical digest",
  "redacted_projection": {}
}
```

Credentials, tokens, unrelated tenant records, and raw personal content are never placed in the event stream or model context.

## 5. Hero Case

### 5.1 Normal state

ERPNext shows a valid order, receipt progression, invoice state, and inventory. Airtable contains the corresponding quality decision. Celigo has successful integration history. Jira has no active CAPA for the tuple. Slack contains ordinary shift context. The dashboard displays these movements without an incident.

### 5.2 Injected anomaly

The presenter creates the anomaly from the ERPNext-facing demo workflow. The visible symptom is an invoice or downstream document completing while inventory reconciliation diverges. The UI does not expose the missing twenty as the cause.

The actual fault is that a quality release exists, but the expected integration acknowledgement or retry never propagated the released receipt into the authoritative ERP state. The case remains ambiguous until the agent correlates the provider records.

### 5.3 Competing hypotheses

The agent must consider and test at least:

1. duplicate posting;
2. quality hold still active;
3. release approved but not propagated;
4. warehouse quantity mismatch;
5. invoice-before-receipt ordering;
6. integration acknowledgement recorded but ERP business key missing.

The selected hypothesis must cite supporting evidence and the evidence that rejected viable alternatives. A confidence value without these citations is insufficient.

### 5.4 Recovery

The recovery compiler translates the diagnosis into the smallest allowlisted action set. For the hero case it stages the exact missing receipt/reconciliation action for twenty units, references the existing business tuple, and refuses to create a duplicate when the provider business key already exists.

Manager approval applies to the complete compiled plan. It does not approve arbitrary future tool use. The grant expires and is bound to case version, action digest, tool identity, quantity, and demo tenant.

### 5.5 Closure

After execution, a fresh adapter instance rereads ERPNext and the relevant integration state. Closure requires all defined postconditions, including the expected quantity, provider business key, invoice relationship, and absence of a duplicate effect. Only then may the case emit `VERIFIED` and construct the Resolution Packet.

## 6. State Model and Human Control

```text
NORMAL
  -> INCIDENT_DETECTED
  -> INVESTIGATING
  -> EVIDENCE_INCOMPLETE | DIAGNOSIS_READY
  -> AWAITING_MANAGER
  -> REJECTED | EXECUTING
  -> VERIFYING
  -> VERIFIED | VERIFICATION_FAILED
```

Read-only investigation proceeds automatically. The user may pause or resume it, inspect any admitted evidence item, and ask the agent about the current state.

The workflow stops when:

- a consequential provider write is ready;
- a provider communication would represent the user or company;
- required evidence is missing, stale after refresh, or contradictory;
- the proposed action exceeds the allowlist or quantity bound;
- provider identity, demo-tenant scope, case version, or action digest does not match;
- verification fails.

There is exactly one normal Manager approval checkpoint in the hero path. Further human input is requested only when a failure changes the facts or the proposed action.

## 7. Event and Observability Contract

All backend and frontend consumers use one ordered incident event stream. Each event includes:

- global monotonic sequence;
- incident ID and case version;
- event type and phase;
- UTC timestamp;
- provider and tool identity when applicable;
- evidence IDs, never secrets;
- trace, session, and parent span identifiers;
- sanitized summary for UI display;
- immutable payload digest.

Required event families:

- `provider.observation.received`
- `incident.detected`
- `investigation.started|paused|resumed`
- `tool.read.started|succeeded|failed`
- `evidence.admitted|stale|conflict`
- `hypothesis.created|supported|rejected|selected`
- `diagnosis.ready`
- `approval.requested|granted|rejected|expired`
- `execution.started|effect_applied|deduplicated|failed`
- `verification.started|succeeded|failed`
- `resolution.packet.created`

SSE clients reconnect with the last processed event ID. The server replays later events or emits a typed reset when the cursor is invalid. A missing deep-linked incident falls back to a registered normal state and an explicit notice; it never renders an empty dashboard.

## 8. Borderless Command Canvas

### 8.1 Typography

- Primary interface: Geist Sans.
- Identifiers, timestamps, tool calls and compact telemetry: Geist Mono.
- Primary titles use weights 500-600.
- All-caps text is limited to short machine states and identifiers.
- Repeated gray explanations and micro-headings are removed.

The fonts are served locally with explicit fallbacks so the recorded demo does not depend on a third-party font request.

### 8.2 Surface hierarchy

The page is a dark borderless canvas. It does not use visible panel outlines. Separation comes from:

- surface tone;
- ambient shadow;
- a restrained inset highlight;
- spacing;
- focus and live-state light.

Persistent regions:

1. compact global header;
2. incident status ribbon;
3. left Signal Stream module;
4. central Investigation Canvas;
5. right Agent Console.

Top-level modules may float, expand and move. Diagram nodes are atomic objects, not containers. A node displays only its icon or name, current state, and at most one critical value. Evidence details open in a separate anchored popover or focus surface. There are no source-group frames, agent-area frames, or cards nested inside diagram nodes.

### 8.3 Layout control

- View Mode is the default and locks geometry.
- Arrange Mode enables dragging and resizing of top-level modules only.
- Modules move freely during the gesture and snap to invisible alignment guides on release.
- The selected layout is stored locally and can be reset.
- Keyboard movement, keyboard resizing, Escape cancellation, and visible focus states are supported.
- Below the desktop breakpoint, modules stack and Arrange Mode is disabled.

### 8.4 Progressive disclosure

- Clicking a provider node opens its current evidence popover.
- Clicking a hypothesis opens supporting, contradicting and missing evidence.
- Expanding a module enters Focus View without losing run state or scroll position.
- Closing Focus View returns the module to the saved geometry.
- Chat stays available while another module is focused.

## 9. Diagram Geometry and Motion

Connectors render below nodes and never enter node interiors.

- aligned endpoints use straight lines;
- offset endpoints use one direction-aware cubic Bezier segment;
- horizontal flows use horizontal endpoint tangents;
- vertical flows use vertical endpoint tangents;
- stroke width is 1-1.25 pixels;
- endpoint dots are not rendered;
- glow is subtle and bounded;
- paths recompute after module geometry settles.

Motion is event-driven, not decorative:

| Event | Visible response |
|---|---|
| Provider observation | Source name and module receive one short bloom |
| Tool read starts | One light segment travels from Agent to source |
| Evidence returns | Segment travels back; log row enters from below |
| Hypothesis rejected | Hypothesis fades to neutral/coral and moves out of focus |
| Hypothesis selected | Selected diagnosis receives one lime confirmation transition |
| Approval requested | Manager node and incident ribbon turn amber |
| Execution verified | A single lime pass completes the path; the UI becomes quiet |

Typical interaction transitions are 180-280 ms. A path traversal may take 600-900 ms. Repeated permanent pulsing, thick neon strokes, bouncing cards, endpoint lights, and fake log loops are prohibited. Motion primarily changes `transform`, `opacity`, and SVG stroke properties. `prefers-reduced-motion` replaces traversal with immediate color and text state changes.

## 10. Agent Console

The console combines live activity and conversation without exposing private chain-of-thought.

Visible activity contains:

- time;
- provider and tool;
- concise intent;
- outcome;
- evidence ID or error classification;
- latency for every completed tool call.

The user may ask:

- what the agent is testing;
- which sources have been read;
- why a hypothesis was rejected;
- which evidence is missing or stale;
- why the system stopped;
- what the proposed action changes;
- how the final result was verified.

Answers must be grounded in the current incident ledger. Chat cannot claim a provider effect that is absent from the ledger and cannot bypass the approval or execution boundary.

## 11. Failure Behavior

| Condition | Required behavior |
|---|---|
| ERPNext, Airtable or Celigo lacks required evidence | Block diagnosis or execution and identify the missing authority |
| Jira unavailable | Continue only if Jira is not needed to prove the operational root cause; leave CAPA incomplete and fail hero-run acceptance |
| Slack unavailable | Continue diagnosis; mark final notification pending rather than sent and fail hero-run acceptance |
| Provider records conflict | Admit both, show the conflict, and return to investigation |
| Evidence is stale | Attempt a bounded refresh; stop if freshness cannot be established |
| SSE disconnects | Resume from cursor without creating another incident |
| Browser reloads during approval | Restore the same pending approval and case version |
| Execute is repeated | Return the original result for the same idempotency key |
| Provider write partially fails | Record the observed effect, stop further writes, and require reconciliation |
| Verification fails | Emit `VERIFICATION_FAILED`; do not create a success packet |
| Model or AgentCore is unavailable | Display explicit degradation; never substitute a scripted diagnosis silently |

## 12. Test and Acceptance Plan

The existing unit, contract, browser and real-Strands suites remain required. The implementation adds or strengthens these end-to-end cases:

1. normal provider-backed movement with no incident;
2. quality release not propagated to ERP;
3. duplicate posting considered and rejected;
4. provider delay followed by successful refresh;
5. optional source outage with explicit degradation;
6. required source outage with a safe stop;
7. conflicting provider records;
8. stale evidence refresh success and failure;
9. Manager rejection;
10. Manager approval, browser reload and resume;
11. repeated Execute with no duplicate effect;
12. successful write followed by an initial failed verification;
13. chat questions during every workflow phase;
14. event-driven color, log and connector behavior;
15. module expand, close, drag, resize, persist and reset;
16. reduced-motion and keyboard operation;
17. same-path AgentCore Runtime and policy trace attribution;
18. ERPNext UI anomaly injection through verified Resolution Packet.

The award demo path passes only when:

- ERPNext, Airtable, Celigo, Jira and Slack expose provider-native record IDs in one run;
- each material diagnosis claim cites admitted evidence;
- viable alternative hypotheses have explicit rejection evidence;
- exactly one ordinary Manager approval occurs;
- there are no provider writes before approval;
- the bounded effect occurs once after approval;
- an identical retry is deduplicated;
- a fresh authoritative reread proves every closure postcondition;
- the Resolution Packet contains source, approval, execution and verification references;
- AgentCore Runtime and Gateway attribution come from the same logical run rather than an unrelated proof invocation;
- the frontend visibly reflects the event ledger without relying on looping animation.

## 13. Implementation Boundaries

This iteration may refactor the dashboard and investigation surfaces, event projection, connector wrappers, run persistence and end-to-end tests needed by this design. It must preserve the existing safety boundaries and unrelated competition artifacts.

It will not:

- create a general-purpose dashboard builder;
- make diagram nodes arbitrarily draggable;
- introduce a multi-agent swarm without a measured need;
- send or store real customer data;
- claim that a demo tenant is a production workspace;
- silently replace unavailable provider data with fixtures;
- add decorative diagrams or explanatory copy that does not help the operator decide or act.

## 14. Delivery Sequence

1. Stabilize provider-backed normal and incident projections.
2. Unify the typed event and evidence envelopes.
3. Place the existing Strands investigation behind the chosen runtime/tool boundary.
4. Enforce the single Manager gate, bounded executor and independent verifier.
5. rebuild Dashboard and Agent Workspace as the Borderless Command Canvas;
6. bind every visible transition to ledger/SSE events;
7. add layout persistence, focus surfaces and accessibility behavior;
8. run the full unit, contract, browser, real-model and live-provider matrix;
9. capture the final provider-backed hero run and Resolution Packet.

This order keeps visual polish attached to verified backend truth and prevents a convincing animation from masking an incomplete technical path.
