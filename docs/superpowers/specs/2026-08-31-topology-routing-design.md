# Live Control Loop Topology Routing Design

**Date:** 2026-08-31
**Status:** Approved

## Objective

Refine the Dashboard live-control-loop topology so every relationship is visually
traceable, every connection terminates at a consistent centered boundary port, and
the Queue and Invoice branches visibly identify their upstream resources.

## Selected direction

Use the approved **unified upper-arch** routing language. Connections use smooth cubic
Bézier arches instead of diagonal straight-looking segments or mixed routing styles.
The topology remains a semantic live view: existing event highlighting and selection
behavior continue to drive the same edges.

## Node model

- Add an upstream `Receipt Source` resource node for the Queue branch.
- Add an upstream `Invoice Source` resource node for the Invoice branch.
- Preserve the existing ERP-related source semantics for the middle branch.
- Keep Incident, Orchestrator, the three investigator cards, Synthesis, and the four
  deterministic lifecycle stages.
- Resource labels describe synthetic source roles and do not imply a real production
  integration.

## Port contract

- Each visible relationship attaches to one centered port on the relevant node edge.
- A node may have one centered input and one centered output when it participates in
  both directions, but it must not expose multiple offset ports for sibling routes.
- Ports sit on the node boundary. Paths must not enter a card interior or overlap its
  icon, label, badge, or status text.
- Fan-out and fan-in share their centered origin or destination visually, then separate
  outside the node boundary through route control points.

## Route contract

- Incident to Orchestrator uses a centered, smooth vertical arch.
- Orchestrator fan-out to all three investigators starts at the single centered output
  and uses symmetric upper-arch curves.
- Each resource-to-investigator relationship uses the same upper-arch curve language.
- Investigator fan-in to Synthesis ends at the single centered Synthesis input.
- Synthesis enters Safety Gate through a smooth arch.
- Safety Gate, Two-role approval, Controlled recovery, and Verification remain a clear
  ordered chain, with rounded curves and centered boundary ports.
- The Verification-to-Incident return route remains outside the node field and uses
  rounded corners consistent with the Bézier system.
- No route may cross a node or use a direct diagonal segment.

## Responsive behavior

- Desktop retains the five-layer authored topology and balanced three-column branches.
- Narrow layouts may preserve a fixed minimum topology width with horizontal viewport
  scrolling, as the current workspace does, rather than compressing paths through
  nodes.
- Port centering and route clearance must hold at both desktop and narrow breakpoints.

## Implementation boundaries

- Update only the topology markup, layout styles, routing geometry, and directly
  related tests.
- Preserve event IDs, route IDs, selection behavior, SSE behavior, and lifecycle
  semantics.
- Do not change provider boundaries, synthetic data behavior, deterministic policy,
  approvals, execution, or verification logic.

## Verification

1. Add or update focused JavaScript assertions for resource labels, centered-port
   selectors, route IDs, and Bézier routing.
2. Run `npm test`.
3. Run the decision-workspace smoke test or its proportionate topology/browser subset.
4. Inspect the rendered dashboard at desktop and narrow widths for centered endpoints,
   node clearance, curve consistency, and absence of route crossings.
5. Confirm event highlighting and agent selection still illuminate the intended path.

## Acceptance criteria

- `Receipt Source` is visibly upstream of Queue.
- `Invoice Source` is visibly upstream of Invoice.
- All topology relationships attach at centered node-boundary ports.
- Orchestrator fan-out and investigator fan-in use one shared centered endpoint per
  node rather than offset sibling ports.
- No direct diagonal-looking connection remains.
- Curves do not enter or cross any node.
- Existing live-event, selection, lifecycle, and replay behavior remains functional.
