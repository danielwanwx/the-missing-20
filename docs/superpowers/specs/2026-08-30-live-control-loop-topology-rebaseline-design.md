# Live Control Loop Topology Rebaseline

Date: 2026-08-30
Status: approved for implementation

## Objective

Replace the current visually tangled Agent Workspace topology with a sparse,
hierarchical, symmetric control loop. Curves must communicate topology, not decorate
it. The diagram remains driven by the existing authoritative incident lifecycle and
does not add mock state, timers, provider calls, or operational authority.

## Five-layer composition

1. **Incident:** one compact incident capsule centered on the entry axis.
2. **Coordination:** one compact Orchestrator node centered below it.
3. **Investigation:** three equal investigator nodes in one symmetric row: Receipt
   Retry, Shipment Evidence, and Duplicate Posting.
4. **Synthesis:** one compact Synthesis node centered below the investigator row.
5. **Deterministic control:** four equal nodes on one row: Safety Gate, Two-role
   Approval, Controlled Recovery, and Verification.

Queue, ERP, and Invoice must not remain as large competing topology nodes. If their
evidence-source identity is needed, show it as three small ports attached to the
investigator layer, without explanatory body copy.

## Geometry contract

- Reduce ordinary topology-node footprints by approximately 25–35% from the current
  desktop presentation while retaining at least 40×40 interactive hit areas.
- Increase the visible clear gap between adjacent node bounds.
- Use one vertical center axis for Incident, Orchestrator, and Synthesis.
- Use equal-width grid columns for the three investigators and four control nodes.
- Main flow is top-to-bottom. Every ordinary edge is a monotonic cubic Bézier curve.
- Orchestrator fan-out leaves from three distinct bottom ports and enters three
  investigator top ports. Investigator fan-in leaves from three bottom ports and
  enters three distinct Synthesis top ports.
- The deterministic chain runs left-to-right across the control row.
- Verification return uses one dedicated outer-right corridor and returns to the
  Incident entry without crossing nodes or ordinary routes.
- No edge may cross an unrelated node, another edge outside a named shared endpoint,
  or a label. No straight polyline fallback is allowed on desktop.
- Pulse animation follows the exact SVG path. Inactive edges remain visible at low
  contrast; the selected or current path alone receives the lime emphasis.

## Content contract

- Nodes show only icon, short name, and state badge.
- Remove mission descriptions, tool/evidence counts, handoff prose, and decorative
  microcopy from the topology canvas. Detailed evidence remains available in the
  existing Context, Chat, and Decision panels.
- Preserve keyboard selection, click-to-role context, truthful lifecycle states,
  reduced-motion behavior, and disconnect motion pause.

## Copilot density contract

- Keep one compact heading for the selected agent. Remove the duplicate `Role context`
  chip when the heading already names that role.
- An answer card contains only the role name, a concise answer, and short evidence
  chips. Do not expose full case-prefixed evidence IDs in the primary surface; render
  human labels such as `ERP receipt`, `Failed message`, and `Warehouse`, with the
  complete immutable ID retained in the chip's accessible label and click-through
  evidence detail.
- Replace the large `Next Step` panel with one compact action row. Show only actions
  that are currently available. Hide disabled or irrelevant actions instead of
  explaining them with multiple lines of microcopy.
- Keep at most two suggested-question chips, each no longer than three words in the
  English UI. Remove the duplicated role prompt strip above the input.
- Use one single-line desktop composer with one `Ask` button. The composer may grow
  when the user's question wraps, but explanatory placeholder prose must remain short.
- `Live activity` and `Evidence returned` stay collapsed by default and expose detail
  only on deliberate expansion.

## Responsive behavior

- At desktop widths, preserve the authored topology and avoid crossings.
- At narrow widths, keep the same semantic order in a horizontally scrollable canvas;
  do not recompute a different topology or collapse routes through nodes.
- Verify at the current browser width, 1440×900, and 1920×1080.

## Dashboard topology alignment

- Apply the same sparse geometry language to the Dashboard supply-flow diagram.
- Warehouse, Message Queue, ERP, and Invoice occupy four equal columns with smaller
  cards and larger clear gaps. Ports share one optical rail and every connector meets
  the visible component boundary without a gap.
- Keep exactly one main supply-flow route and one queue anomaly branch. Do not render
  duplicate route lines, repeated topology cards, or decorative edges.
- Remove the redundant `Open investigation` feature button because Agent Workspace is
  already a primary navigation tab. Preserve one clear incident state and the existing
  top-level view navigation.
- Remove instructional microcopy below the supply-flow canvas when direct node
  selection and the visible exception state already communicate the interaction.
- Keep the live quantities and unit-density animation; geometry changes must not turn
  the Dashboard into a static report.

## Acceptance gates

- Existing live API/SSE data, agent selection, chat, approvals, recovery, and replay
  behavior remain unchanged.
- Route tests prove cubic paths, monotonic flow, distinct ports, no node intersection,
  and no route crossing outside named endpoints.
- Browser evidence covers idle, active incident, completed investigation, and closed
  verification states.
- `npm test`, focused browser smoke, Python tests, lint/type checks, and
  `git diff --check` pass.

## Archify reference

`docs/design/live-control-loop-archify.workflow.json` records the reduced topology and
single main path. Archify's workflow renderer currently exits with an unclassified
render error for this multi-lane control-loop candidate, so it is a topology reference,
not a claimed delivered Archify HTML artifact. The production implementation must meet
the explicit geometry and browser acceptance gates above.
