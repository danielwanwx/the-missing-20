# Unified Operations / Investigation Refactoring Design

Status: complete proposal, pending overall review; this round completed the real backend baseline and design without changing the current frontend. It follows the selected silver/white, Geist, solid-color node, low-explanation, necessary-human-review direction.

## 1. Basis and Boundaries

Based on this round's actual review and real Strands backend runs, without expanding the number of SaaS systems or introducing a second business logic. Dashboard answers “what is happening in the business now”; Investigation answers “why, what was found, and what do I need to decide.” They are two views of the same case/run.

Real baseline on 2026-09-05: Bedrock Nova Pro / Strands, three successful model runs, investigation about 2.9s, pre-fix Q&A 4.426s, post-fix Q&A 4.173s; the HTTP path completed manager approval, synthetic recovery, and readback. Eight model requests, 16,649 input tokens, 1,000 output tokens, estimated engineering cost $0.0165192. External business-system writes were 0; recovery used isolated local synthetic data.

Quality limitation: all three runs only read control_context and ERP; on the question about the 12/8 split and blind-retry risk, they repeated that manager approval was required without answering fully. The current input still preloads expected_disposition, so this baseline is not an acceptance of independent investigation capability.

## 2. Option Selection

Compare three directions:

1. **Recommended: keep Dashboard and rebuild a same-source Investigation.** Remove the old page and two fact sources within the minimum necessary scope while protecting existing visual investment.
2. Put everything into Dashboard: fewer page switches, but monitoring, dialogue, review, and evidence crowd each other and recreate the current density problem.
3. Rewrite the frontend framework wholesale: it could provide a clearer engineering structure, but migration risk is high at this stage and it would not automatically solve split backend state.

Choose option 1. Extract the existing native JavaScript incrementally by module and do not migrate frameworks at the same time. A view under independent development must not become a third source of truth.

## 3. Two Views, One Page Framework

Keep the shared header to the brand, Operations / Investigation switch, case selector, run mode, and connection state. Put Demo Controls in a secondary menu. Remove the hidden legacy workspace that routes could still reactivate.

### Operations (Current Dashboard)

- The first screen has one business-status sentence, such as “Invoice INV-4817 needs reconciliation”; before investigation, do not state the root cause “20 stopped before ERP.”
- Four independent business nodes: Warehouse, Integration, ERP inventory, and Invoice. Connect only necessary node boundaries and keep lines out of text areas; no decorative line across the main flow is needed yet.
- State units for totals, available quantity, and pending quantity explicitly; Invoice shows status and affected-document count, not 80 invoices when the value is 80 units.
- One continuous timeline: cumulative receipts, available inventory, unresolved quantity; if throughput is shown, use a separate units/min label. Distinguish batches with markers, and do not clear them periodically or reset them with a timer.
- Event list on the right: newest at the bottom, with a follow switch; scrolling upward pauses live updates automatically and shows “N new / Resume live.”
- Keep one case-status entry at the bottom: “Investigating / Needs your review / Verified → Open investigation.”
- Put SaaS connection health in a connection drawer; show a case-evidence node only when linked to the current case, never mixing VERIFIED from another case.

### Investigation

Desktop first-screen layout:

```text
Same-case header: INV-4817 | Investigating | Real Strands | Demo business data
┌──────────────────────────────┬──────────────────────────┐
│ Investigation progress / current question │ Agent conversation │
│ Tools being queried, returned evidence     │ Ongoing session and inline citations │
│ Hypotheses + support/opposition/missing evidence │ Explicit human question when needed │
├──────────────────────────────┤                          │
│ Current decision (only when needed)        │                          │
│ 12 receipt + 8 quality        │                          │
│ [Approve & execute] [Hold]    │                          │
├──────────────────────────────┴──────────────────────────┤
│ Outcome: completed action, post-readback result, Resolution Packet │
└─────────────────────────────────────────────────────────┘
```

This describes information layout; it does not require visible borders. Use white surfaces, light shadows, and whitespace for the concrete visual treatment.

- Prioritize the question “what is being investigated now” in the main area; do not lead with a huge Agent sphere.
- The SaaS topology is an expandable auxiliary view, with one source-activity row by default; do not show fake activity for tools that were not called.
- Clicking an evidence citation opens a side drawer with a safe projection of provider raw fields, record ID, revision, observed_at, source link, and which hypothesis it supports or refutes. When the drawer occupies the conversation area, provide a clear return action; do not nest another node layer inside a node.
- Show manager decisions only when a plan exists and policy passes. List the exact action, quantity, object, and risk; approve this scope once and execute, with automatic backend readback. Reapprove after new evidence or a scope change.
- Collapse Outcome before execution; after execution retain time, effect record, approval binding, and before/after comparison. Do not display fixed 0.94/0.99.

### All States Use One Skeleton

| State | Main area | Conversation / human involvement |
| --- | --- | --- |
| Normal | Current business and recent evidence, with no fake incident diagram | Ask about live status |
| Detected | Symptom, scope, latest source change | Investigate directly when the automatic read policy is enabled; can stop |
| Investigating | Plan and real per-tool progress | Ask about progress; no step-by-step approval needed |
| Needs evidence | Which record is missing, who can provide it, when to retry | Fill automatically if the system can; otherwise ask one clear question |
| Awaiting approval | Verified conclusion and bounded recovery plan | One manager approval or Hold |
| Executing / Verifying | Exact completed action, pending readback items | No premature “verified” or second approval button |
| Verified | Persisted outcome credential | Ask why it completed and cite readback records |
| Paused / Failed | Preserve original evidence and explain pause/failure | Clear Resume/Retry, with no silent degradation |

## 4. Single Source of Truth and Event Contract

Add an application-level OperationsProjection that wraps/replaces the old registry UI read entry point; Case Console no longer manages the same business case in parallel with legacy ExperimentSession. Synthetic and live adapters implement the same domain contract, but source identity must never be conflated.

```text
Source adapters → Evidence registry / case store → OperationsProjection
                                            ├→ Dashboard
                                            ├→ Investigation
                                            └→ Resolution Packet
```

The projection must contain: schema_version, case_id, run_id, case_version, projection_sequence, business_state, agent_state, connection_state, evidence, plan, approval, execution, verification, and mode. Connection online, model available, and business healthy are three independent states.

Event contract: event_id, case_id, run_id, sequence, occurred_at, received_at, type, source, tool_call_id, evidence_ids, and sanitized_summary. Partition sequence by case/run; changing case must not reuse the old maximum sequence. The client accepts only identity-matching updates and does not invent business transitions.

Minimum real events: source.changed, incident.detected, agent.started, tool.started, tool.succeeded, tool.failed, hypothesis.updated, plan.ready, human.required, approval.granted, execution.started/completed, verification.started/completed/failed, run.paused, and agent.failed.

After recovery, the projection reads back from the same persistent source; the frontend must not overwrite inventory numbers based on execution.status. Reconnect using Last-Event-ID and reload a snapshot when a version gap is found. Store source time and collection time separately, display them in the user's timezone, and label the timezone.

## 5. Investigation Capabilities Required in the Backend

- Inputs contain only symptoms, business identifiers, raw evidence, and permission/policy boundaries. Remove business expected_disposition and solved root causes; the evaluator may hold the truth.
- Strands selects reads as needed; tools receive explicit case/record queries and call adapters instead of always reading a solved snapshot. Every return includes revision, evidence ID, and freshness.
- Policy decides whether an action is allowed and the model proposes diagnostic candidates; store them separately, and do not disguise a failure as Agent completion.
- Cause explanation and safe_next_step are separate fields; answer the question directly with citations and unknowns, rather than merely repeating approval rules.
- Persist sessions by case/run; cross-turn references such as “that shipment just mentioned” have explicit context; keep them separate from writes. Show plan and evidence summaries, not hidden chain-of-thought.
- Pause/cancel isolates downstream effects of in-flight calls; an old run cannot advance a new run. Test the stop boundary independently rather than changing only UI state.
- The current real baseline proves only constrained advisory and local effects; frontend labels must distinguish Real model / Synthetic business data / External reads / Local writes.

## 6. Visual and Interaction Specification

- Reuse the existing local Geist font. Use a silver-gray background, pure-white modules, and dark blue-black body text; regular text 14–16px, supporting information 12–13px, key quantities 24–32px.
- Use blue/cyan/purple/orange/green for sources without dark/light double sidebars; give states their own text/icon and never rely on color alone.
- Target 4.5:1 contrast for body text and 3:1 for key graphics; avoid residual translucent dark backgrounds.
- Lines 1–1.5px, endpoints touching the center of node edges; use straight lines when possible and small-radius/smooth curves when turning is necessary. No glowing endpoint dots and no looping light animation to claim that a tool is working.
- Briefly emphasize new data for 120–220ms; do not fake-flash when there is no new event. Under reduced motion, remove movement while retaining state updates.
- Modules support Focus; only Arrange mode allows dragging, with keyboard move and Reset; save layout preference locally without changing business state.
- Keep investigation and conversation in two columns at 1440/1280; at small and medium widths stack them with the current question/action first, then evidence, while keeping chat reachable. Do not reveal the old diagram at any breakpoint.

## 7. Implementation Slices

1. Data and routing: one projection, case/run identity, new normal-state skeleton, and removal of reachable legacy routes; first add cross-page numeric-consistency tests.
2. Real backend: remove answer leakage, add real tool events, answer quality, pause and version isolation; then connect the frontend to that event stream.
3. Investigation components: CaseHeader, InvestigationProgress, EvidenceDrawer, CaseChat, ManagerReview, and Outcome; tune spacing and lines last, without letting the diagram dictate the domain model.
4. Business real-time simulation and linkage: synthetic systems produce persistent receipt/posting/invoice events, and curves consume only events that occurred; associate SaaS sources explicitly by case.
5. Browser acceptance: from source anomaly through real investigation, necessary review, effect readback, and Dashboard synchronization, record evidence from the same run instead of stitching together successful fragments.

## 8. Acceptance Matrix

Cover at least normal/no action, 12 missing receipt + 8 approved, ERP posted but receipt lost, quality awaiting approval, evidence changed after approval, duplicate check after write timeout, human stop, and stream reconnect. Check business results and disabled actions for each; do not only match copy.

Key gates:

- After backend VERIFIED, the next projection update must keep inventory, gap, and invoice consistent across both pages; refresh remains consistent.
- When the real model is unavailable, do not claim Agent completion; retry recovery has a clear state.
- Three cases with the same appearance but different root causes must produce different correct investigations without preloaded truth hints.
- Tool start/complete events reach the frontend when the actual call happens; after a source disconnect, do not continue to pretend “LIVE.”
- Each approval binds plan digest, case version, demo tenant, and scope; readback runs automatically and stops only when evidence is missing.
- With no approval, a paused run, a late old-run result, or new evidence, emit no unauthorized write.
- Expanded evidence reaches the actual record and citation; the resolution credential's execution.approval_id is present and exact.
- Multi-turn questions directly answer the user, and the frontend does not overwrite conversation history; numbers and judgments have openable citations.
- Default and desktop-breakpoint screenshots are readable, the keyboard completes the main flow, and scrolling the event list upward is not stolen.

## 9. Self-Check

This proposal does not confuse “all 20 are missing postings” with “12 missing postings + 8 quality-held inventory”; the latter is the main case. Normal state no longer disables chat or falls back to the old framework. Keep one manager approval while all other reads and verification proceed automatically; do not auto-approve new external permissions, hide model failure, or claim production data. No new third-party platform or frontend-framework replacement is required.

## 10. Second Refinement Round: Backend Quality and Investigation Visuals

This section refines the optimization requested by the user; it is not an implemented result. On 2026-09-05 the current page at 8765 was read again: it had recovered to VERIFIED while the model remained AGENT UNAVAILABLE; the independent backend run in this round did not change that historical page. The narrow-window Signals gray-green block, large topology circle, and repeated states remain. Screenshots and review notes are in docs/audits/2026-09-05-investigation-refinement.md.

### 10.1 Do Not Use Policy Answers as a Substitute for Model Investigation

Split implementation responsibility by boundary; do not rewrite every system at once:

1. agents/live_advisory.py: create investigation inputs and outputs without answer hints. Remove expected_disposition, expected_safe_next_step, solved diagnosis, and test-answer temporal_hook from what the model can see. Keep evaluation truth only in the evaluator; retain permissions, approval requirements, and budget. Tests must inspect the complete model-visible payload, not only prompt text.
2. Tool adapter layer: tools accept case and record query parameters and read the corresponding source record, relation key, and version at call time. No result, source unavailable, and version conflict are different outcomes. Remove the absolute “each tool may be read only once” rule; reread when a new version or different parameter exists and budget allows. Do not force every source call just to look multi-agent.
3. Investigation output: findings[], hypotheses[], missing_evidence[], proposed_actions[], answer, citations[]. Link every conclusion to an evidence ID; allow “cannot confirm at this time.” A policy validator independently checks basis and authorization for proposed actions; do not insert a correct label into the model as its answer.
4. live_advisory_gateway.py: investigation and Q&A use the same case/run session but do not share a “return only safe_next_step” question template. Retain per-turn session and retrieval records. A cause question must explain the cause, a progress question must describe facts not yet returned, and a repair-result question must cite effect readback.
5. Server and event storage: tool wrappers publish persistent events when a call actually starts, returns, or fails; the page receives them immediately instead of a batch after the whole turn. Project run state, business state, and connection state separately. A model failure must not be presented as Agent success through historical-rule recovery.

The main-case investigation must not prescribe a fixed order, but must obtain enough evidence: invoice anomaly → check PO/ASN/ERP → identify the pending 12 units and quality-held 8 units → inspect the unknown integration-write outcome → confirm by business key whether ERP has posted → verify quality approval for the exact batch → form a bounded action → one manager approval → idempotent execution → authoritative readback. If ERP already has a record, do not post again; if QA has not approved, do not move quality-held inventory.

### 10.2 Apply Investigation Color and Density to Concrete Tokens

Keep the silver/white direction and do not layer on a third theme. Under a light theme, replace the component's original dark-background rules instead of continually adding higher-priority overrides.

| Use | Value | Scope |
| --- | --- | --- |
| Page background | #F3F5F7 | One canvas, without green tint |
| Module | #FFFFFF | White surface, light shadow, no outer border |
| Body text | #17212B | Main conclusions and numbers; about 16.29:1 contrast |
| Secondary content | #52606D | Required time/record IDs; about 6.46:1 contrast |
| Primary action/activity | #1D4ED8 | Start, continue, submit; about 6.70:1 with white text |
| ERP / Airtable / Celigo / Jira / Slack | #0E7490 / #1D4ED8 / #6D28D9 / #C2410C / #15803D | Independent solid-color nodes or lines, not the whole module background; minimum about 5.02:1 with white text |

These ratios are solid-color sRGB contrast calculations; they do not mean the current page or full accessibility acceptance has passed. Solid colors can coexist with high readability; do not use rainbow gradients, glowing text, gray-green number bars, or pale-yellow buttons with white text. Source color expresses “where it came from”; state text and icons express “what happened.”

Reduce the first screen to a compact case header, current investigation question/evidence, and persistent chat; show the decision area only when review is needed. Condense Signals into a compact business summary instead of repeating five platforms' static list. Collapse topology by default into Source activity, rather than making a huge Agent circle and spokes to every SaaS the visual centerpiece. Keep the user's requested expand/focus behavior.

Use the same layout for normal and abnormal states; after completion replace dead controls with an outcome credential instead of retaining three rows of disabled buttons. When preserving model failure history, write “Local recovery verified / Agent run failed” and do not show a vague “0.99.”

### 10.3 Self-Defined Delivery Gates, Not a Promise of Winning

The [official rules](https://agentsforhumans.devpost.com/rules) were checked on 2026-09-05: technical, design, impact, originality, and presentation are equally weighted; they emphasize a complete product experience and non-trivial Strands implementation. The following are this project's internal acceptance standards, not official score thresholds.

- Eight business and recovery scenarios, at least three real model runs each, 24 total; record every result rather than selecting the best. Normal, missing receipt + releasable quality, posted-but-lost receipt, QA not approved, physical short shipment, evidence conflict/insufficiency, post-approval version change, and post-timeout duplicate check. Test pause and stream reconnect as cross-scenario fault cases.
- Judge root cause, required evidence coverage, citation truth, action/stop correctness, and multi-turn answers together; do not compare disposition only. Any wrong write or false verified blocks delivery; if a business judgment still fails, retain the failure and rerun the affected group after correction.
- Compare the resolvable cases, source-read count, and human-intervention count with a rules baseline under identical inputs and tools. Do not claim rules can never solve the case; show the actual gain from Agent cross-source association, targeted follow-up, and absorption of unstructured evidence.
- From a normal page the user triggers a symptom, sees the current question and real tool activity, opens evidence, asks follow-ups, approves when needed, and sees the result change on both pages for the same run. Three complete browser journeys show no state split; refresh and reconnect do not roll back.
- Inspect the investigation UI at 1440, 1280, and the current narrow window; body/data use the size and contrast requirements in section 6; the keyboard completes the main actions. Target tool start/end visibility within 1 second and same-page readback within 2 seconds on a local healthy network; record measurements rather than assuming the target.
- Report measured impact only: recovery quantity, released invoice blockage, avoided duplicate postings, time/model cost/human intervention. Do not invent a savings percentage when business value is unmeasured.

Implementation order: unify projection and real investigation inputs → same-source tool events and Q&A → Investigation layout and tokens → 24 backend tests and browser closure. Static styling may proceed during backend testing, but do not call the page complete before the same-source contract is connected. Do not add SaaS or Agent count.

## 11. Implementation Notes After KB Review

Later user requirements were compared further with KB Diagnosis/validation-first/flywheel material and authoritative sources; the release evidence boundary is in [Submission and winner README benchmark](../../research/2026-09-07-submission-and-winner-readme-benchmark.md). Before implementation include: reuse the existing deep-harness components rather than building a third; give the evaluator real raw evidence; separate source online from evidence sufficiency; make checker failure trigger targeted supplementary reads; express compound causes and unknown causes; derive the outcome credential's before-state from a real snapshot. The 90/4/6 variant reporting 80/8/12 was reproduced by an isolated probe.

Enable multiple Agents only when comparison evidence supports them, rather than assigning one by SaaS count. Keep the runtime investigation/action loop separate from the offline failure → golden → regression → release loop; do not treat report quality scores as execution permission or upgrade every run into a 17-validator pipeline. This supplement remains review and design; no application code has been implemented.
