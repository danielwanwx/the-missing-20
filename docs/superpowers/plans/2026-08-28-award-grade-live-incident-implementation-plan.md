# Award-Grade Live Incident Implementation Plan

**Design:** `docs/superpowers/specs/2026-08-28-award-grade-live-incident-agentcore-evidence-design.md`  
**Delivery model:** small independently verifiable slices; Luna implements, primary agent verifies, independent reviewer gates material milestones.

## Slice 1: Connected Normal Flow

**Status:** COMPLETE

**Goal:** A newly opened Operations page receives continuously advancing authoritative
synthetic telemetry through the backend and visibly animates the facility flow.

**Backend output:** ordered telemetry observations with unique sequence, observation time,
source stage, throughput window, queue depth, and authoritative unit counts.

**Frontend output:** connection heartbeat, moving packets, advancing time window,
event-backed sparkline, and visible source-to-ERP motion. Business counts remain accurate.

**Checks:**

- telemetry sequence advances through API/SSE;
- two consecutive browser reads observe different telemetry sequence and timestamp;
- flow animation is running only while the stream is connected and the tab is visible;
- disconnect pauses packets and chart advancement;
- reconnect reconstructs the latest authoritative state;
- no trace IDs, token counters, benchmark data, or explanatory report copy in the first viewport.

## Slice 2: Isolated Scenario Lab

**Status:** COMPLETE — independent review approved.

**Goal:** Inject a source condition outside Operations and prove that the detector, not the
button, creates the incident.

**Output:** separate Scenario Lab route, typed synthetic source event, detector observation,
and Operations transition from normal flow to a visible 80/20 discrepancy.

**Checks:** source event precedes detector event; the UI cannot directly set incident or
agent state; duplicate injection is blocked; reset creates a fresh session.

## Slice 3: Event-Backed Incident Command

**Status:** COMPLETE — independent review approved after durable provider-degradation fail-closed verification.

**Goal:** Show the actual Strands orchestrator, investigators, tools, evidence, handoffs,
synthesis, and evaluator as a dynamic mission-control workflow.

**Output:** public event bindings, active-agent graph, tool/evidence motion, advisory chat,
diagnosis/abstention/degraded states.

The Agent Workspace includes an interactive **Case Console** rather than a passive
read-only transcript. A user can ask what is happening and what should happen next, or
choose a bounded next step:

- continue the investigation;
- compare competing causes;
- retrieve missing or supporting evidence;
- explain the evaluator decision;
- prepare a structured recovery proposal.

Each choice calls the current incident API/harness and emits the corresponding public
agent, tool, evidence, handoff, synthesis, or proposal event. The console may investigate
and prepare, but approval and execution remain separate structured controls and cannot be
triggered through chat.

**Checks:** no fake typing or timer-driven completion; tool and evidence animations require
matching events; missing evidence abstains; provider degradation cannot fabricate a
diagnosis; free-text questions and every suggested action return case-specific evidence;
the user can observe the selected action in the mission-control graph; chat cannot approve
or execute and cannot mutate benchmark truth.

## Slice 4: Controlled Recovery

**Goal:** Carry an eligible diagnosis through exact two-role simulated approval, bounded
execution, authoritative verification, restored flow, and zero-effect replay.

**Checks:** agent cannot grant or execute; approval is bound to exact intent and case
version; executor rereads state; restored motion waits for verification; replay has zero
effects; missing records fail closed.

## Slice 5: Evidence Studio and Competition Proof

**Goal:** Add explicit LIVE_AGENTCORE, CAPTURED_AGENTCORE_REPLAY, and LOCAL_SCRIPTED proof,
then run the frozen four-arm twenty-case benchmark.

**Checks:** truth labels are exact; no silent fallback; cloud manifest is sanitized; spend
stays under the approved hard cap; benchmark reports all failures and deterministic raw
counts; main Operations view remains uncluttered.

## Final Gate

Run the complete five-minute path in a fresh browser session, test every button and chart,
verify API/SSE correspondence, run full automated tests and mutation checks, obtain an
independent competition review, and only then request the user's final product judgment.
