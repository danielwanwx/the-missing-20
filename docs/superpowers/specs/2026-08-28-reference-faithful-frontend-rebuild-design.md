# Reference-Faithful Frontend Rebuild

## Status

Approved direction: structural frontend rebuild. The three supplied images are the visual
contract, not loose inspiration.

## Source visual truth

- Dashboard: `docs/design/references/dashboard-target.png`
- Investigation workspace: `docs/design/references/agent-investigation-target.png`
- Agent operations and recovery: `docs/design/references/agent-operations-target.png`

All source images are 1487 x 1058. Desktop QA uses the same viewport and incident state.

## Product objective

A judge should understand the product in ten seconds without reading a report:

1. one hundred units enter the supply flow;
2. twenty stop between the queue and ERP;
3. three investigators activate and collect evidence;
4. the orchestrator converges on a supported cause;
5. the user can ask questions or prepare a controlled recovery;
6. two approvals unlock execution;
7. verification restores the flow to one hundred units.

## Selected composition

### Dashboard

Recreate the composition of `dashboard-target.png`:

- 60 px top navigation with product name, Dashboard and Agent Workspace tabs, and live
  connection state;
- 144 px left agent rail showing the orchestrator and investigators with event-driven
  breathing status;
- the main upper region is a supply-chain flow from Warehouse to Message Queue to ERP to
  Invoice, with the normal path, the red discrepancy branch, and moving packets;
- an event-backed reconciliation trend occupies the area directly below the flow;
- the lower region contains exactly three operational panes: Active Incident, System
  Health, and Reconciliation;
- explanatory hero copy, truth strips, technical provenance copy, trace IDs, and generic
  report headings are removed from the primary viewport.

### Agent Workspace

Use `agent-operations-target.png` as the primary structure and
`agent-investigation-target.png` for the investigation detail language:

- left rail: current supply state, limited to Warehouse, Queue, ERP, and Invoice;
- center: Orchestrator surrounded by investigator nodes, live tool calls, evidence returns,
  handoffs, Safety Gate, Two-role Approval, Controlled Recovery, and Verification;
- right upper rail: Case Console conversation, cited evidence count, and bounded next-step
  controls;
- right lower rail: ordered live activity driven by the event ledger;
- bottom: reconciliation timeline and replay controls;
- hypothesis confidence and evidence matrix appear in a contextual drawer opened from the
  agent graph. They do not occupy the default first viewport;
- approval and execution remain separate controls. Chat may investigate and prepare, but
  cannot approve or execute.

### Scenario Lab

Scenario creation remains isolated from both operational views. It uses a compact control
surface for Normal, Inject Incident, Recovery, and Golden Incident. It must not resemble an
incident report and cannot directly mutate UI state.

## Visual language

- Background: near-black green, matching the references.
- Primary operational state: electric lime.
- Agent/tool/evidence activity: cyan.
- Incident and blocked flow: coral red.
- Investigation alternatives: amber and violet only when required by the confidence view.
- Typography: compact sans-serif UI with tabular numerals. Headings describe a visible
  object, never explain the product.
- Icons: one consistent outline icon library. No emoji, handcrafted icon SVGs, or text
  glyph substitutes.
- Surfaces use borders only for structure and state. Generic elevated report cards are
  removed.
- Buttons use a 0.96 pressed scale and have at least a 40 x 40 desktop hit area.

## Text budget

The default desktop viewport may contain only:

- product and navigation labels;
- entity names and current numeric values;
- incident name and detection time;
- agent/tool/action names and terse current status;
- chart legends and axis values;
- Case Console messages and explicit user actions.

Evidence IDs, trace IDs, provider labels, test-mode disclosures, deterministic-policy
explanations, and detailed provenance move to an inspector drawer or About/Proof surface.
No section receives a subtitle merely to explain what the visible graphic already shows.

## Event-to-visual projection

| Authoritative signal | Required visual response |
| --- | --- |
| `telemetry.observed` | Advance chart time, packet position, throughput and entity counts |
| `source.condition.injected` | Queue changes to incident state; red branch begins |
| `incident.detected` | Incident row appears and Agent Workspace call-to-action activates |
| `investigation.started` | Orchestrator pulse and investigator fan-out begin |
| `agent.started/completed` | Corresponding node changes state and breathing indicator |
| `tool.started/completed` | Tool edge animates; tool node shows running/completed state |
| `evidence.returned` | Evidence travels back to its investigator and updates evidence count |
| `agent.handoff` | Handoff edge moves from investigator to synthesis/orchestrator |
| `synthesis.*` | Central synthesis state and hypothesis confidence update |
| `evaluation.completed` | Safety Gate displays accepted, abstained, or blocked |
| `recovery.prepared` | Recovery proposal appears; approval path remains locked |
| `approval.recorded` | Exact role node changes to approved |
| `execution.*` | Controlled Recovery node animates only during real execution |
| `verification.completed` | Flow returns to 100 / 100, closes the loop, and marks verified |
| `provider.degraded` | Advisory graph stops, turns degraded, and all advisory actions disable |

Animations must derive from new ledger events or live telemetry changes. CSS may animate a
currently active state, but timers may not invent business progress.

## Architecture boundary

Keep the existing backend and session safety model. Split the frontend into three layers:

1. authoritative state and SSE reducer;
2. visual projection selectors that turn state/events into dashboard and agent graph view
   models;
3. renderers for Dashboard, Agent Workspace, drawers, and Scenario Lab.

The rebuild may replace the existing view markup and CSS. It must not duplicate business
rules in presentation code or loosen backend authorization.

## Responsive behavior

- At 1180 px and above, preserve the desktop spatial composition.
- From 768 to 1179 px, keep the central graph intact with horizontal overflow; move the
  right rail into a slide-over drawer.
- Below 768 px, present a focused operational summary and separate full-screen Flow,
  Agents, Copilot, and Timeline tabs. Do not stack every desktop panel into one report.
- Reduced-motion mode stops decorative travel while retaining color, state, and position
  cues.

## Acceptance gates

1. Same-state screenshots at 1487 x 1058 are compared directly with all three targets.
2. No P0, P1, or P2 design-QA difference remains.
3. Dashboard and Agent Workspace first viewports follow the target region proportions and
   contain no explanatory report blocks.
4. Normal, incident, investigation, evidence return, decision, approval, recovery,
   verification, degraded, disconnected, and narrow-screen states are browser tested.
5. Every visible dynamic business transition is traceable to the REST snapshot or ordered
   SSE ledger.
6. Existing Python, JavaScript, safety, audit, and browser end-to-end gates continue to
   pass.
7. An independent competition judge can identify the incident, agent work, evidence,
   human gate, and recovery outcome without reading supporting documentation.

