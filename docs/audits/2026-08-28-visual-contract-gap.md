# Visual Contract Gap Audit

## Verdict

The current frontend does not implement the approved visual contract. It implements the
backend behavior inside the legacy report-oriented shell. A frontend structural rebuild is
required; a CSS-only restyle cannot close the gap.

## Evidence inspected

- Current live Agent Workspace, captured in the in-app browser at 481 x 859 CSS pixels:
  `docs/audits/screenshots/current-agent-narrow.jpg`.
- Current desktop render produced by the same application:
  `artifacts/audits/2026-08-28/post-final/dashboard-live.png` and
  `artifacts/audits/2026-08-28/post-final/agent-live.png`.
- Approved visual targets, all 1487 x 1058 pixels:
  `docs/design/references/dashboard-target.png`,
  `docs/design/references/agent-investigation-target.png`, and
  `docs/design/references/agent-operations-target.png`.
- Current source: `workspace/index.html`, `workspace/style.css`, and `workspace/app.js`.

## Root cause

The implementation sequence treated the UI as an output surface for backend milestones.
New capabilities were appended to the existing card hierarchy instead of replacing that
hierarchy with the approved command-center composition.

The source makes the drift explicit:

1. `workspace/index.html` places a large `incident-hero`, a `truth-strip`, and explanatory
   `section-heading` blocks above the actual operational views.
2. Dashboard and Agent Workspace are both composed from repeated generic `panel`,
   `panel-heading`, and `panel-label` containers. This creates a report/card rhythm.
3. The Agent Workspace places the graph, operation feed, chat, and recovery controls in
   vertically stacked cards. The target uses a single spatial system: supply state on the
   left, an agent operations graph in the center, and decision/activity rails on the right.
4. Provenance and safety language is rendered as first-class page copy. The target reveals
   detailed evidence on interaction and reserves the first viewport for current state.
5. The implementation preserved event correctness but did not define a visual projection
   contract for each event. The result is real data presented as text records rather than
   real data changing a visible operational map.

## Material gaps

| Area | Approved target | Current implementation | Severity |
| --- | --- | --- | --- |
| Information architecture | One-screen operations command center | Narrative hero followed by report sections | P1 |
| Dashboard | Full-width live flow, trend line, agent rail, three compact operational panes | Large text hero, generic cards, tall supply-path report | P1 |
| Agent Workspace | Supply rail + central agent graph + Copilot/activity rail + timeline | Card grid with a static hierarchy and long text feed | P1 |
| Data visualization | Flow lines, active nodes, confidence movement, lifecycle timeline | Counts and status expressed mainly as labels and paragraphs | P1 |
| Text density | Labels only where they identify state or action | Repeated headings, explanations, badges, traces, and citations | P1 |
| Interaction | Click a node to inspect; chat and recovery remain in the spatial workflow | Evidence and operations consume permanent page space | P2 |
| Responsive behavior | Preserve the command model with drawers and horizontal graph overflow | Collapse into a long report stack | P2 |

## What must be preserved

The frontend rebuild must not replace or simulate the working product core:

- authoritative REST snapshots and SSE event ordering;
- the 100 / 80 / 20 source discrepancy;
- actual Harness investigator, tool, evidence, handoff, synthesis, and evaluation events;
- Case Console free-text and bounded action API calls;
- two-role approval, controlled execution, verification, replay, and fail-closed behavior;
- durable provider-degradation blocking.

## Decision

Rebuild `workspace/index.html`, the view-level render functions in `workspace/app.js`, and
the visual system in `workspace/style.css`. Retain the existing API client, state model,
event reducers, safety checks, and server contracts behind a new visual projection layer.

