# Dual-Plane Live Architecture Design

**Date:** 2026-08-31
**Status:** Approved

## Objective

Replace the mixed control-loop topology with a legible architecture view that
separates deterministic supply-chain truth from AI investigation. A judge should
immediately understand what runs the business, what the agents may inspect, and where
human-controlled deterministic authority begins.

## Selected composition

Use the approved **stacked dual-plane** composition:

1. deterministic supply-chain data plane at the top;
2. Incident and Evidence API boundary in the middle;
3. Agent investigation plane below the boundary;
4. deterministic control chain after agent synthesis;
5. authoritative verification returning to the supply-chain data plane.

The planes use different routing languages. The supply-chain plane uses aligned,
orthogonal architecture lines. The Agent plane uses restrained curves for fan-out and
fan-in. Curvature communicates agent coordination rather than decorating every edge.

## Deterministic supply-chain data plane

- Show `Warehouse`, `Queue`, `ERP`, and `Invoice` in one ordered horizontal flow.
- Use cyan, straight, orthogonal routing with rounded 90-degree corners only where a
  bend is required.
- Keep a single centered port per visible relationship on each node boundary.
- Preserve synthetic-data disclosure and avoid implying production integration.
- This plane represents authoritative operational state, not agent-generated state.

## Incident and Evidence API boundary

- Place one explicit boundary band between the two planes.
- Show `Incident` and `Evidence API` as the only downward bridge from supply-chain
  state into agent investigation.
- The Evidence API is read-only from the Agent plane.
- Do not draw an Agent edge directly to Warehouse, Queue, ERP, Invoice, approval,
  execution, or verification.
- Preserve existing event and evidence semantics behind the visual projection.

## Agent investigation plane

- Place `Orchestrator` above three investigator nodes: Receipt Retry, Shipment
  Evidence, and Duplicate Posting.
- Use a single centered Orchestrator output and a single centered input per
  investigator.
- Use restrained cubic curves for the Orchestrator fan-out.
- Route all investigator outputs into one centered Synthesis input with restrained
  fan-in curves; the aligned middle route may remain straight.
- Agent edges express advisory coordination only.

## Deterministic control chain

- Route Synthesis into `Safety Gate` as a proposal, not an authorization.
- Show `Safety Gate → Two-role approval → Controlled recovery → Verification` as a
  separate deterministic horizontal chain.
- Use straight or orthogonal lines for this chain, visually matching the supply-chain
  data plane rather than the Agent plane.
- Route Verification back to the supply-chain plane through an outside return rail.
- Preserve the exact two-role, controlled-execution, verification, and replay truth
  boundaries already implemented.

## Visual hierarchy

- Label the upper zone `DETERMINISTIC SUPPLY CHAIN`.
- Label the lower advisory zone `AGENT INVESTIGATION`.
- Label the post-synthesis chain `DETERMINISTIC CONTROL`.
- Use cyan for authoritative data/control routes and lime for advisory Agent routes.
- Use background zoning and whitespace before adding explanatory copy.
- Keep node labels and statuses readable without route overlap.

## Responsive behavior

- Desktop shows the complete stacked architecture without clipping.
- Narrow layouts preserve a fixed minimum diagram width with horizontal scrolling
  rather than collapsing routes through nodes.
- Plane order, centered ports, boundary semantics, and route clearance must remain
  unchanged at the narrow breakpoint.

## Implementation boundaries

- Update topology markup, styling, client-side route geometry, and directly related
  tests.
- Preserve event IDs, route selection, SSE behavior, lifecycle behavior, synthetic
  data, policy, approvals, execution, verification, and replay semantics.
- Do not add a provider call, external integration, or write authority.

## Verification

1. Assert the three labeled zones and the Incident/Evidence API boundary in JavaScript
   tests.
2. Assert centered ports, orthogonal deterministic routes, curved Agent fan-out/fan-in,
   and absence of node intersections.
3. Run `npm test` and `git diff --check`.
4. Run the complete decision-workspace browser smoke.
5. Inspect desktop and narrow layouts in the browser.
6. Confirm event highlighting, agent selection, lifecycle controls, and return-loop
   semantics remain intact.

## Acceptance criteria

- The top row reads as Warehouse → Queue → ERP → Invoice without Agent involvement.
- Incident and Evidence API form the only visible bridge into Agent investigation.
- The Agent network is visually distinct and uses restrained free curves only where
  coordination branches or converges.
- Synthesis cannot be mistaken for execution authority.
- The deterministic control chain is visually separate from the Agent plane.
- Verification visibly returns to authoritative supply-chain state.
- No route crosses a node, label, icon, badge, or status.
- Existing behavior and truthful AWS/synthetic-data boundaries remain unchanged.
