# The Missing 20 Award-Grade Live Incident and AgentCore Evidence Design

**Status:** Approved product direction, frozen implementation specification  
**Date:** 2026-08-28  
**Scope:** Judge-facing live experience, real AgentCore proof, and synthetic impact benchmark

## Decision

The Missing 20 will be presented as a live incident product, not as an audit report.
The canonical story is:

`normal operation -> source incident -> automatic detection -> visible agent investigation -> evaluated diagnosis -> deterministic authorization -> recovery -> verified normal flow`

The product has four deliberately separated surfaces:

1. **Operations** continuously shows the authoritative facility data flow.
2. **Scenario Lab** injects a synthetic source-system condition without directly changing
   any detector, agent, diagnosis, approval, or recovery state.
3. **Incident Command** shows the event-driven investigation and bounded human control.
4. **Evidence Studio** presents cloud provenance, benchmark results, limitations, and
   reproducible proof after the product story is understood.

The main experience must make the system legible through motion and state changes. It
must not ask judges to infer the product from implementation labels, trace identifiers,
token counts, or explanatory gray text.

## Product Truth Boundaries

The demo uses synthetic enterprise data. Real cloud execution does not make the business
incident real. The following labels are mandatory and must never be conflated:

- `Synthetic facility simulator · Connected` means the local ordered event stream is
  connected.
- `Live AgentCore invocation` means the displayed advisory was produced by a current
  AgentCore Runtime invocation.
- `Captured AgentCore execution · not live` means a sanitized artifact from a previous
  real invocation is being replayed.
- `Local scripted advisory` means no cloud model produced the advisory.
- Approval actors are `simulated role principals`; the local demo must not claim two
  independently authenticated humans.
- `Restored` means the synthetic records reconcile after the bounded synthetic effect.
  It does not prove production recovery or business impact.

Stable real Nova usefulness is proven only if the frozen acceptance cases pass. A
provider failure, malformed response, incomplete citations, or evaluator rejection is
shown as advisory degradation. It cannot fabricate or block deterministic operational
truth.

## One Causal Event Chain

Every visible operational state is derived from a single ordered event ledger.

1. Scenario Lab publishes a source-system event.
2. The synthetic adapter changes only authoritative source state.
3. The detector observes that state through its normal polling or stream path.
4. The detector emits the incident event.
5. The orchestrator reacts to the incident event and emits public agent lifecycle events.
6. Investigators issue allowlisted read-only tool calls and return evidence references.
7. Synthesis and evaluation produce a diagnosis, an abstention, or a visible degraded
   advisory state.
8. Deterministic policy independently determines action eligibility.
9. Two distinct simulated role principals approve the exact action intent, parameters,
   and case version.
10. ControlledExecutor rereads authoritative state, performs the bounded synthetic
    effect, verifies postconditions, records the effect ledger, and proves replay adds
    zero effects.
11. Operations renders restored flow only after the verified source-state event.

The browser may interpolate motion between accepted events. It may not invent counts,
agent activity, tool calls, evidence, diagnosis, approval, execution, or restoration.

## Frozen State Machine

The public lifecycle is:

`NORMAL -> DISCREPANCY_DETECTED -> INVESTIGATING -> SYNTHESIZING -> DIAGNOSED | ABSTAINED -> AWAITING_APPROVAL -> EXECUTING -> VERIFYING -> RESTORED | SAFE_NOOP | FAILED_CLOSED`

Required rules:

- A detector event, not a UI click, causes `DISCREPANCY_DETECTED`.
- Diagnosis is absent until synthesis and evaluation complete.
- Missing required evidence ends in `ABSTAINED` with no recovery eligibility.
- A duplicate or already recovered incident ends in deterministic `SAFE_NOOP`.
- Provider failure is visible and cannot create an operational grant.
- A closed incident cannot relaunch. Replaying it produces zero additional effects.
- Refresh or reconnect reconstructs the lifecycle from the event ledger without
  inventing intermediate state.

## Surface 1: Operations

Operations is the default route and must feel alive within the first second.

### Healthy state

- Packets continuously traverse the source, queue, ERP, and settlement nodes.
- Node heartbeats and a moving present-time cursor communicate connectivity even when
  values are flat.
- Counts and charts change only when API or SSE events change.
- The first viewport contains the flow, current business counts, and connection state.
- It contains no benchmark table, trace ID, token count, ARN, evidence classification,
  architecture explanation, or cost breakdown.

### Incident state

- Eighty records continue through the normal path.
- The affected twenty records visually stop at their actual failing boundary.
- The anomaly node changes state from the detector event, not from the injection click.
- The same surface reveals a concise incident command layer; it does not navigate the
  judge into an unrelated report.
- The primary action becomes `Open investigation`.

### Recovery state

- Only the approved affected records resume movement.
- Recovery motion begins after the verified execution event.
- The flow returns to normal only after the source records reconcile.

### Copy and density

- Keep only one compact truth label: `Synthetic facility simulator · Connected`.
- A component gets one heading, one value or state, and at most one primary action.
- Status text uses short nouns or states: `Healthy`, `Investigating`, `Needs approval`,
  `Restored`, `Safe noop`, `Failed closed`.
- Explanations belong in details, tooltips, Evidence Studio, and documentation.
- Do not use decorative synthetic numbers or perpetual activity that implies work.

## Surface 2: Scenario Lab

Scenario Lab is the only source-condition control surface. It is visually and
architecturally isolated from Operations.

The first frozen judge case is `Retryable queue lock`, which causes twenty valid unit
records to stop before ERP admission while eighty continue.

Scenario Lab must:

- begin from a complete healthy experiment session;
- publish one typed source event with a unique event ID and synthetic provenance;
- show the source system that emitted it;
- disable repeated injection for the same active session;
- provide explicit reset by creating a new isolated session, never by rewriting history;
- never set incident, agent, diagnosis, approval, execution, or recovery state directly.

Additional benchmark cases are selectable only in Scenario Lab or Evidence Studio. They
must not clutter the five-minute default path.

## Surface 3: Incident Command

Incident Command is the agent product. It combines a mission-control visualization, a
bounded conversational copilot, and structured decision controls.

### Mission-control visualization

The graph displays the orchestrator, investigators, tools, evidence return paths,
synthesis, evaluator, deterministic policy, approval, executor, and verification.

Public events drive each visual transition:

- `agent.started` activates the exact agent node;
- `tool.started` sends a pulse from that agent to the exact tool;
- `tool.completed` returns an evidence packet with admitted evidence IDs;
- `handoff.completed` moves the accepted result to the next actor;
- `synthesis.completed` exposes the candidate diagnosis;
- `evaluation.accepted` advances to diagnosis;
- `evaluation.rejected` visibly blocks or revises the candidate;
- `policy.eligible` reveals the structured action proposal;
- approval, execution, verification, and replay events advance only their own stages.

There is no fake typing, time-based completion, decorative tool call, or private
chain-of-thought. Public progress language may state bounded facts such as `Reading queue
evidence`, `Comparing hypotheses`, and `Checking cited records` only when supported by
the corresponding public event.

### Incident Copilot

The copilot uses the current incident session and Strands advisory boundary. Users can:

- ask what happened and which source state changed;
- ask for competing hypotheses;
- ask for evidence supporting or contradicting a claim;
- ask what evidence is missing;
- ask why the evaluator accepted or rejected a result;
- ask the system to prepare an eligible recovery proposal.

Free text and reliable suggested questions are available. Chat can perform extra
read-only investigation, but every added model call receives a separate ledger event,
request budget, and cost record. Chat cannot approve or execute.

### Human control

Operational controls appear only after deterministic policy identifies an eligible
bounded action. The visible stages are:

`Prepare -> Approve -> Execute -> Verify`

The exact action, parameters, case version, source digest, and two-role quorum remain
bound throughout the lifecycle. Missing authoritative records fail closed and display
missing or unverified state. The UI must never manufacture approvers, grants, verification
passes, closed state, or replay success.

## Surface 4: Evidence Studio

Evidence Studio is the proof surface, not the landing page. It contains two tabs:
`Cloud execution` and `Benchmark`.

### Cloud execution record

Each real or captured AgentCore run shows:

- execution mode;
- capture timestamp;
- exact model and AWS Region;
- source and deployment digests;
- request, session, trace, and invocation references;
- investigator, tool, and admitted evidence events;
- synthesis and evaluator outcomes;
- latency, input/output tokens, and cost estimate;
- sanitized manifest hash;
- limitations and failed cases.

Sensitive credentials, raw provider payloads containing secrets, employer data, and
private runbooks are never captured or rendered.

### Benchmark record

The benchmark uses a frozen SHA-256-addressed corpus of twenty synthetic incidents:

- eight diagnosable cases across at least three root-cause classes;
- four legitimate evidence-shortage cases;
- four duplicate safe-noop cases;
- four missing-evidence abstention cases.

Each case defines gold root cause, admissible evidence IDs, required evidence IDs,
expected abstention or action class, and forbidden recommendation.

Four controlled arms run against the same corpus:

1. deterministic sequential triage;
2. single Nova agent;
3. full Strands multi-agent harness;
4. full harness without evaluator.

Scoring is deterministic. No LLM judge scores its own output.

Frozen success gates:

- full harness exact root-cause accuracy at least `17/20`;
- full harness improves by at least two cases over the single-agent arm;
- evidence precision at least `0.90` and recall at least `0.85`, with raw counts shown;
- all four missing-evidence cases abstain;
- all four duplicate cases safe-noop;
- zero policy-violating recommendations;
- zero false-permit recommendations;
- deterministic authority invariant passes `20/20`;
- the evaluator prevents or corrects at least one unsupported result;
- every failure is published; there is no cherry-picking.

Report exact root-cause match separately from abstention quality. Report warm and cold
advisory latency p50/p95, calls per correct decision-ready result, token-estimated model
cost, estimated Runtime/CloudWatch cost, and settled cost as separate fields. Do not
translate latency into unsupported human-time savings.

## AgentCore and Nova Deployment Proof

The real advisory slice is deployed to Amazon Bedrock AgentCore Runtime using Strands.
The deployment boundary contains only non-authoritative advisory capabilities:

- competing-hypothesis generation;
- read-only knowledge retrieval;
- evidence-gap identification;
- likely root-cause explanation;
- incident-report preparation.

Deterministic local code exclusively owns evidence integrity and source completeness,
state classification, action eligibility, policy, authorization, execution,
verification, and replay.

The deployment must produce:

1. a source digest and sanitized deployment manifest;
2. an AgentCore Runtime identity and Region;
3. one successful invocation trace or an honestly disclosed failed/degraded result;
4. CloudWatch or AgentCore observability evidence;
5. a redacted request/result event manifest;
6. an explicit model, token, latency, and estimated-cost record;
7. a teardown or disabled-runtime record when the proof is finished.

No live AWS call is attempted until offline gates, cost preflight, credentials, model
access, and the frozen request manifest pass. There is no silent fallback and no retry
loop. A failed live run is preserved as evidence and requires a deliberate decision
before any additional paid call.

## Cost Contract

- Existing cumulative provider estimate: `$0.1250496`.
- Absolute cumulative promotional-credit hard cap: `$0.60`.
- Target stop before new execution exceeds cumulative `$0.50`.
- Worst-case authorized implementation estimate for real proof and benchmark: `$0.48`.
- Every provider call must be pre-counted and post-recorded.
- Any projected cumulative spend above `$0.60` requires new human authorization.
- Optional AgentCore, CloudWatch, or benchmark work that does not improve a frozen gate is
  deferred.

## Reliability and Motion Gates

The following are release blockers:

- SSE disconnect does not stop data packets, counters, or agent-work animation.
- Reconnect or refresh cannot reconstruct the same ordered lifecycle.
- Duplicate or reordered event IDs change the rendered final state.
- Scenario injection changes a detector or agent state directly.
- Counts, diagnosis, or recovery change without an authoritative event.
- A captured execution is presented as a current live cloud run.
- A local scripted result is presented as Nova output.
- Missing evidence produces a confident diagnosis or recovery proposal.
- Replay creates any additional effect.
- Reduced-motion or hidden-tab behavior implies continuing operational progress.

Motion may preserve directional current and node heartbeat while connected. When the
stream disconnects, operational motion pauses and only a neutral reconnect indicator may
continue.

## End-to-End Acceptance Scenarios

### A. Healthy flow

Open Operations, observe one complete real event cycle, verify counts and topology from
API/SSE, refresh, and confirm the same authoritative state is reconstructed.

### B. Golden incident and recovery

Start healthy, inject `Retryable queue lock` from Scenario Lab, observe automatic
detection, complete investigation and evaluation, converse with the copilot, approve the
exact action using two distinct simulated role principals, execute, verify restored
source records, and prove replay adds zero effects.

### C. Missing evidence

Inject a case with a required source unavailable. The agent may expose hypotheses and
gaps but must end in abstention, with no recovery eligibility.

### D. Duplicate incident

Replay the same source condition after closure. The detector and deterministic lifecycle
must end in safe-noop with zero effects.

### E. Provider degradation

Use a frozen degraded artifact or controlled provider failure. The UI displays degraded
advisory state, preserves deterministic operational truth, and does not invent a
diagnosis.

### F. AgentCore proof

Run the single authorized live proof, verify its AgentCore invocation and trace artifacts,
sanitize the record, and render it in Evidence Studio with exact provenance and cost.

### G. Benchmark

Run all four arms over the frozen corpus, preserve every output and failure, calculate
deterministic metrics, and render the comparison without affecting the main Operations
experience.

## Five-Minute Judge Path

- `0:00-0:25` normal moving facility flow;
- `0:25-0:45` inject source condition in Scenario Lab;
- `0:45-2:15` automatic detection and visible multi-agent investigation;
- `2:15-2:45` evaluated diagnosis or explicit abstention logic;
- `2:45-4:00` deterministic decision, two-role simulated approval, bounded execution,
  and verification;
- `4:00-4:30` restored operational flow;
- `4:30-5:00` AgentCore provenance, benchmark headline, and one honest limitation.

The recorded pitch uses a captured successful cloud execution if one exists. The demo
must not depend on live cloud latency or availability. Live invocation remains available
as optional judge proof and is never substituted silently.

## Claim Language

Submission claims use exactly these evidence classes:

- `PROVEN`: validated artifact demonstrates the stated deterministic or real cloud fact.
- `SYNTHETIC BENCHMARK`: result comes from the frozen controlled synthetic corpus.
- `MODELED`: extrapolated value or business impact assumption.
- `NOT_PROVEN`: stable production usefulness, production business impact, human-time
  savings, production security/compliance, or independent-human authorization not
  demonstrated by the package.

The project may state that it reduces the investigation surface and automates a synthetic
incident workflow. It may not claim production labor savings or revenue protection
without real user or operational evidence.

## Implementation Order

1. Freeze public event vocabulary, lifecycle reducer, and scenario boundary.
2. Refactor Operations to derive every state from API/SSE and remove report copy.
3. Build isolated Scenario Lab and golden incident source event.
4. Bind Incident Command visualization and copilot to public harness events.
5. Bind deterministic approval, execution, verification, and replay to authoritative
   lifecycle records.
6. Add explicit live, captured, and scripted execution modes.
7. Produce AgentCore deployment and observability evidence under the cost contract.
8. Freeze and run the four-arm twenty-case benchmark.
9. Add Evidence Studio, submission documents, and limitations.
10. Run end-to-end browser, mutation, provenance, cost, and five-minute demo gates.

Each material stage is implemented by Luna and reviewed once by an independent Chief
Architect or competition judge. At most one bounded correction is allowed per stage.
Optional polish is deferred; only a reproducible defect that can falsely claim detection,
agent work, authorization, execution, verification, cloud provenance, or benchmark
success may block progression.

## Definition of Done

This design is complete only when:

- a judge sees live normal data before reading any explanation;
- an isolated source incident automatically becomes a visible investigation;
- the agent workflow is real, event-backed, conversational, and bounded;
- missing evidence, duplicates, evaluator rejection, and provider degradation remain
  visibly safe;
- controlled recovery closes end to end and replay has zero effects;
- real AgentCore provenance is either positively demonstrated or honestly shown as
  degraded, never implied;
- the twenty-case benchmark passes the frozen gates or publishes its failures;
- the public story, README, architecture, demo, and evidence matrix use the same names,
  claims, and limitations;
- the full path is reproducible without employer or customer data.
