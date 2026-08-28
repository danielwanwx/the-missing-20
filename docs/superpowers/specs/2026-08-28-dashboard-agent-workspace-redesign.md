# The Missing 20 Dashboard and Agent Workspace Redesign

**Status:** Approved direction, awaiting written-spec review  
**Date:** 2026-08-28

## Purpose

Replace the current report-style replay with a working incident product. A judge should
understand within seconds that the system detected a twenty-unit reconciliation gap,
launched a multi-agent investigation, collected evidence, prepared a controlled recovery,
and required explicit human approval before any effect.

The product has two persistent views:

1. **Dashboard** for live operational awareness.
2. **Agent Workspace** for investigation, conversation, decision, and recovery.

Both views share one incident session and one event stream. Changing views must not reset
the investigation.

## Visual Targets

- Dashboard target: `assets/dashboard-target.png`
- Agent Workspace target: `assets/agent-workspace-target.png`

The existing black-green surface, electric lime verified state, cyan agent activity, and
coral anomaly state remain the product language. The redesign removes token counters,
cost counters, generic KPI cards, repeated gray explanations, and long report prose from
the primary experience.

## Product Structure

The persistent header contains only the product name, the `Dashboard / Agent Workspace`
switch, the current incident identity, and a compact connection or demo-source status.

### Dashboard

The Dashboard is the default entry point. It contains:

- A live supply-chain flow from Warehouse to Message Queue to ERP to Invoice.
- Moving units that make the discrepancy visible as `100 -> 80 + 20 missing`.
- A selected active incident and one primary action, `Open Agent Investigation`.
- A compact topology showing source health and the affected queue.
- A reconciliation chart showing expected, recorded, and missing units over time.
- A small persistent indicator showing which investigators are working.

The Dashboard does not explain the full investigation. Selecting the incident or its
primary action opens the same incident in Agent Workspace.

### Agent Workspace

The Agent Workspace makes the agent system the main product surface.

- A compact supply-chain column preserves business context.
- The central Agent Operations Map displays the Orchestrator and three investigators:
  Message Recovery, Shipment Evidence, and Duplicate Posting.
- Tool calls animate outward to Queue Logs, ERP Records, Warehouse Scan, Invoice Match,
  and the versioned Knowledge Base.
- Evidence packets animate back to the investigator that requested them.
- Handoffs into synthesis, deterministic safety checks, two-role approval, controlled
  recovery, and verification are visible as one connected loop.
- Selecting any agent or tool filters the activity stream and evidence trail.
- A replay scrubber lets a judge move between detection, investigation, decision,
  approval, execution, and verification without losing the live-state model.

### Incident Copilot

The right-side Incident Copilot is connected to the current Strands session. It is not a
decorative chat transcript.

The user may:

- Ask where the twenty units went.
- Ask why a hypothesis was selected or rejected.
- Request the evidence behind a claim.
- Ask for competing explanations or missing evidence.
- Ask the system to prepare a recovery proposal.

Responses stream as agent, tool, evidence, and handoff events. Suggested questions make
the competition demo reliable, while free-text input remains available.

The Copilot may investigate, explain, compare hypotheses, and prepare an action. It may
not authorize or execute a recovery. Approval is accepted only through the structured
decision control bound to the deterministic Authority B lifecycle.

## Agent and Tool Architecture

The existing `strands-agents` installation and current Python harness remain the core.
The three existing investigator roles continue to run in parallel, followed by synthesis
and evaluation. Their current read-only tools remain allowlisted:

- `read_admitted_evidence`
- `search_synthetic_knowledge`

A conversational Orchestrator sits above the existing harness. It receives the incident
snapshot and the user's question, then chooses a bounded operation:

- Read the current incident or agent trace.
- Ask one investigator for a focused explanation.
- Run or inspect the fixed parallel investigation.
- Compare validated hypotheses.
- Retrieve evidence or Knowledge Base citations.
- Prepare a recovery proposal.

FlowPulse's Agent Team Chat provides the design precedent for conversation identity,
bounded context, routing, handoff records, idempotency, evidence references, tool budgets,
and human gates. The Missing 20 implementation reuses those concepts in its Python domain
model rather than copying the FlowPulse interface wholesale.

Agent autonomy is deliberately bounded. Agents decide which read-only path can answer the
question and may investigate in parallel. Deterministic code remains the sole authority
for evidence integrity, policy, approval validity, execution eligibility, effects,
verification, and replay.

## Shared Event Model

Dashboard and Agent Workspace subscribe to the same incident event stream. The minimum
public event vocabulary is:

- `incident.detected`
- `investigation.started`
- `agent.started`
- `tool.started`
- `tool.completed`
- `evidence.returned`
- `agent.handoff`
- `synthesis.completed`
- `recovery.prepared`
- `approval.requested`
- `approval.recorded`
- `execution.started`
- `execution.completed`
- `verification.completed`
- `provider.degraded`
- `workflow.blocked`

Each event carries the incident ID, trace ID, case version, sequence number, timestamp,
actor, status, and redacted display payload. Server-sent events provide live delivery;
the client reconnects with the last accepted sequence number and can replay from the
authoritative ledger.

The application must distinguish three modes without turning the hero into a disclaimer:

- Scripted synthetic demonstration.
- Real provider connected.
- Provider degraded or unavailable.

The mode appears as a compact status control with details available on demand. The UI
must never label scripted output as a successful live Nova run.

## End-to-End Interaction

1. The Dashboard shows 100 units entering the flow and 80 recorded downstream.
2. The Message Queue node emits a twenty-unit anomaly and creates an incident.
3. `Open Agent Investigation` switches to the same incident in Agent Workspace.
4. The Orchestrator launches the three investigators in parallel.
5. Tool calls and evidence returns update the operations map and Copilot in real time.
6. The user asks follow-up questions and inspects cited evidence.
7. Synthesis prepares a recovery proposal; deterministic checks determine eligibility.
8. Two distinct authorized roles approve the same immutable action intent.
9. ControlledExecutor performs the approved synthetic recovery.
10. Verification confirms `100 / 100` and no duplicate effect.
11. Returning to Dashboard shows the repaired path and resolved incident without reset.

## Failure Behavior

- Provider timeout, malformed output, or unavailable model becomes a visible degraded
  advisory state. It cannot create or block an operational grant.
- Missing or stale evidence blocks proposal eligibility and highlights the broken edge.
- A stale case version rejects the action and refreshes the current incident projection.
- A disconnected event stream reconnects and resumes from the last sequence number.
- Missing approval, mismatched intent, or failed verification stops the flow at the
  corresponding gate. No success animation is shown.
- Free-text conversation is treated as untrusted input and cannot invoke write tools.

## Implementation Boundaries

The first implementation changes only the existing local web product and its supporting
Python service. It does not add unrelated incidents, production credentials, private ERP
data, public deployment, or a new provider experiment.

The visual target is implemented with native product components and a suitable graph or
chart library. Generated mockups are references, not images embedded as the application.
All visible controls on the core demo path must work.

## Verification

### Automated

- Unit tests for event ordering, resume behavior, routing, tool allowlists, and chat
  idempotency.
- Contract tests for every public event and decision payload.
- Tests proving chat cannot approve or execute an action.
- Tests for provider-degraded, missing-evidence, stale-version, and invalid-approval paths.
- Browser tests for Dashboard, Agent Workspace, tab switching, agent filtering, chat,
  evidence inspection, decision preparation, approval, recovery, and verification.
- Visual checks at desktop and narrow layouts with no overflow or clipped controls.

### Required end-to-end proof

One deterministic synthetic run must execute the complete path from anomaly detection to
verified `100 / 100` recovery. The proof must include the event ledger, agent and tool
activity, immutable decision intent, two-role quorum, execution receipt, verification
receipt, and final Dashboard state.

### Acceptance

- A first-time judge can identify the business problem and the active agents within five
  seconds.
- Agent work is shown through real events, tool calls, evidence, and handoffs rather than
  explanatory paragraphs.
- The user can ask a question and receive a grounded response tied to the visible incident.
- Dashboard and Agent Workspace remain synchronized across navigation.
- No advisory output can bypass deterministic policy or human approval.
- The complete demo can be understood and completed in under three minutes.

