# Independent Judge AgentCore Browser E2E

Date: 2026-08-30

Environment: `http://127.0.0.1:8767/` at a 1440 × 1000 desktop viewport

Incident created: `missing-20-001-run-3`

Trace: `trace:missing-20-001-run-3`
Method: independent visible-browser clicks first; the primary human report was read only after this run was closed and replayed.

## Verdict

**CONDITIONALLY READY — not competition-ready while one operational-visual P1 and one provider-evidence P1 remain.**

The authoritative lifecycle passed end to end. One fresh incident reached the real 100/80/20 state, three investigators completed, evidence was admitted, two independently prepared actions each required both role principals, both effects executed, the system reread 100/0/100 truth, verification closed the incident, and replay added zero effects.

The judge-facing UI nevertheless becomes internally contradictory after replay: the headline and topology remain healthy at 100/0/100 while the primary reconciliation and flow-health charts settle back to the replayed incident values of recorded 80, gap 20, queue 20, and ERP 80. Separately, the persisted record proves AgentCore-shaped metadata for chat, but the fresh three-investigator run records only `mode: agentcore`; it does not persist transport/provider metadata on its own completion events. A competition claim that this particular fresh investigation invoked AWS is therefore not independently closed by the incident record alone.

## Exact browser path and acceptance matrix

| Surface | Actual click/action | Observed result | Verdict |
|---|---|---|---|
| Healthy Dashboard | Open root | 100 expected, 100 recorded, 0 gap; live SSE sequence advanced; no active incident | PASS |
| Dashboard nodes | Click Warehouse, Message Queue, ERP, and Invoice | Each selected node replaced the inline inspection detail; Invoice showed 100 records, source, observed/received timestamps, and freshness | PASS |
| Exceptions | Click **Inspect exceptions** | Healthy state showed “All records posted” | PASS |
| Scenario Lab | Inspect Normal, Inject incident, Recovery, Golden, Metrics | Controls reflected the persisted catalog. Recovery was required to leave the prior completed boundary; then Normal became available | PASS |
| Fresh scenario | Click **Recovery → Normal → Inject incident** | Exactly one fresh incident, `missing-20-001-run-3`, was created | PASS |
| Incident Dashboard | Observe after injection | 100 expected, 80 ERP recorded, 20 queue backlog, invoice held; external route data remained advisory | PASS |
| Exception record | Expand exceptions and click unit `PO-10001-10-unit-081` | Authoritative record displayed `QUEUE FAILED`; after recovery the same record displayed ERP recorded, revision 2 | PASS |
| Investigation visibility | Open Agent Workspace immediately after the Dashboard check | Investigation had already completed; all three roles were `COMPLETE`, safety was complete, and approval was monitoring | PARTIAL — pacing risk |
| Receipt Retry | Click role node | Role context and selected graph path changed | PASS |
| Shipment Evidence | Click role node | Role context and selected graph path changed | PASS |
| Duplicate Posting | Click role node | Role context and selected graph path changed | PASS |
| Orchestrator | Click role node | Team context showed six tool results and 15 evidence records | PASS |
| Evidence drawer | Click **Evidence returned** | Five initial admitted records rendered with IDs, source, observation, support, and digest integrity | PASS |
| Free-form chat | Ask once: “Which evidence proves the likely cause, and what provider/runtime handled this investigation?” | Grounded RETRYABLE_MESSAGE answer plus five citations; provider/runtime portion was ignored | PARTIAL |
| Deterministic/quick comparison | Click **Compare causes** | Returned RETRYABLE_MESSAGE supported; shortage and already-posted rejected, with five evidence citations | PASS |
| Prepare receipt recovery | Click **Prepare recovery** | Immutable Receipt Message Restart intent, Case v1 | PASS |
| First quorum | Click Integration Operator, then AP Approver | Execute remained disabled until both distinct roles approved | PASS |
| First execution | Click **Execute** | Queue became 0, ERP 100; authoritative refresh evidence showed consumed queue message | PASS |
| Prepare invoice release | Click **Prepare Invoice Release** | New intent and Case v6; previous approvals did not carry | PASS |
| Second quorum | Click both role approvals again | Fresh exact-action quorum accepted | PASS |
| Second execution | Click **Execute** | `VERIFIED · CLOSED`; topology 100/0/100/100; 20 admitted records after rereads | PASS |
| Replay | Click **Replay Investigation** | Persisted API reports replay safe and effect delta 0 | PASS operationally / FAIL visually |
| Final Dashboard | Return to Dashboard and wait five seconds | Headline/nodes remained healthy 100/0/100, but charts remained at replayed 80/20 incident values | FAIL — P1 |

Key screenshots were captured during the browser run for healthy Dashboard, active 80/20 Dashboard, Agent Workspace with citations/evidence, verified Decision state, and the contradictory post-replay Dashboard.

## Persisted provider and operational truth

Read-only inspection of `/api/v1/incidents/missing-20-001-run-3` after closure confirmed:

- `unit_counts = { total: 100, erp_recorded: 100, queue_failed: 0 }`
- `execution.verified = true`
- two controlled effects
- `execution.replay_effect_delta = 0`
- `replay.replayed = true`
- `replay.replay_safe = true`
- `trace_id = trace:missing-20-001-run-3`

The initial investigation ledger records:

- `investigation.started` with `mode: agentcore` and three investigators
- three `agent.started` events with `mode: agentcore`
- three completed investigator stages
- synthesis selected `RETRYABLE_MESSAGE` with conclusion `SUPPORTED`

Provider metadata persisted on the completed chat events:

- provider: `agentcore`
- model: `agentcore-runtime`
- transport: `agentcore_invoke_agent_runtime`
- region: `us-west-2`
- runtime configured: true
- status: `COMPLETE`
- authority: `ADVISORY_NOT_OPERATIONAL_DECISION`
- read-only: true
- request count: 7
- cumulative estimate: `$0.0814368`
- incremental estimate: `$0.00`
- remaining recorded cumulative allowance: `$0.5185632`

Important boundary: the three fresh investigator completion events do **not** carry this provider metadata. The local incident record proves AgentCore mode and proves provider metadata for chat, but by itself does not prove the transport boundary for this specific fresh investigation execution.

## Material reproducible defects

### P1 — Replay corrupts the live chart projection after verified closure

Reproduction:

1. Complete both controlled actions until `VERIFIED · CLOSED`.
2. Click **Replay Investigation**.
3. Return to Dashboard and wait at least five seconds.

Observed stable contradiction:

- headline: `All 100 units are accounted for`
- totals/nodes: expected 100, recorded 100, gap 0; Queue 0; ERP 100
- queue chart: 20
- ERP chart: 80
- reconciliation chart latest point: recorded 80, gap 20
- persisted API truth: queue 0, ERP 100, replay effect delta 0

Replay is operationally safe, but the primary dashboard presents replayed historical points as the current live tail. A judge cannot tell whether the incident is actually closed.

### P1 — Fresh investigation provider transport is not independently attributable from its persisted completion records

The fresh investigator events persist `mode: agentcore`, but only later chat completion events contain provider, model, transport, region, cost, and authority metadata. This leaves the central competition claim dependent on adjacent chat evidence or server/operator testimony. Persist provider metadata, invocation identity, and status on the investigation/synthesis run record itself, while preserving the advisory/no-authority boundary.

## Non-blocking observations

- The fresh investigation completed before the judge could move from Dashboard to Agent Workspace. This makes a real run appear static (`0 active`) unless the workspace is opened almost immediately.
- The free-form answer was grounded and cited all five records but ignored the explicit provider/runtime clause. Cause comparison was substantially more responsive.
- Scenario Lab helper text remained “Select a source condition” after a selection. This is minor.

## Comparison with the primary human report

Read after completing the independent run: `docs/audits/2026-08-30-human-browser-agentcore-e2e.md`.

Agreement:

- authoritative detection, evidence, two-action quorum, effects, verification, and zero-effect replay all work;
- real-run pacing is too fast for the judge story;
- free-form chat can be grounded yet insufficiently responsive;
- AI authority remains correctly advisory and partial.

Additional independent finding:

- the primary report marked replay PASS based on effect delta. This run additionally checked the post-replay visual state and found the stable 100/0 operational truth versus 80/20 chart contradiction.
- the primary report summarizes provider metadata at the incident level; this run traced its location and found it on chat completion events, not the fresh investigator completion events.

## Competition-readiness decision

**HOLD for the two P1 corrections above.** No authority-model, product-direction, AWS, or schema expansion is required beyond making replayed history visually distinct from current truth and persisting the already-known provider boundary on the investigation record. The governed operational loop itself is accepted.

## Post-fix Gate

Date: 2026-08-30
Scope: final bounded read-only review of the current diff, refreshed smoke artifact, and focused-test evidence; **no new AWS/provider call**.

### Final verdict

**READY.** The final provider-truth P1 is closed. Observed-call health now requires returned proof, successful provider statuses, and a nonfailed completion event. Investigator post-response validation failures retain the actual returned invocation attribution while durably recording it as degraded/failed.

### Gate matrix

| Gate | Evidence | Result |
|---|---|---|
| Replay retains the 80/20 incident history | `chartTelemetryPoints()` copies `state.telemetry`; it does not rewrite persisted observations | PASS |
| Replay terminal projection returns to authoritative verified truth | For a closed, verified snapshot after replay drain, the client appends a projection-only point from `snapshot.unit_counts`, marked `source: authoritative-verified-state` and `authoritative: true` | PASS |
| Terminal point reaches all Dashboard consumers | Reconciliation series/points, queue/ERP/invoice sparklines, metric telemetry, and Agent reconciliation timeline all consume `chartTelemetryPoints(snapshot)` | PASS |
| Focused replay test | `npm test`: 34/34 passed, including `replay dashboard charts append the authoritative verified close`; it asserts history `[80]` becomes `[80,100]`, gap `[20,0]`, and source telemetry remains unchanged | PASS |
| Refreshed smoke artifact | `artifacts/workspace/browser-smoke-v1.json` is `PASS`, final API counts are 100/0, final gate is closed, replay effect delta is 0, five live citations and ten closed citations focus exact records | PASS, but no explicit terminal-chart field is retained in the artifact |
| Successful invocation attribution is returned by the adapter and persisted | `AgentCoreRuntimeModel` clears stale metadata, records `invocation_proof: returned` only after `invoke_agent_runtime` returns, takes invocation identity only from response fields, and the harness/event sink carries the allowlisted metadata into completion events | PASS |
| No configuration inference masquerades as invocation proof | `actual_provider_metadata()` reads adapter state; harness traces begin without configured provenance; `_provider_attribution()` no longer derives provider, transport, or invocation ID from factory configuration or operation ID | PASS |
| Pre-response failures do not prove an observed/completed call | The focused transport-failure and precompletion-event tests retain failure context without provider, transport, invocation ID, or returned proof; `provider_truth()` ignores lifecycle markers | PASS |
| Returned-but-invalid failures do not mark calls observed/complete | `provider_truth()` requires `invocation_proof: returned`, `status: COMPLETE`, `invocation_status: COMPLETED`, and a completion event whose status is not failed/degraded/error/blocked. The new returned-invalid test proves `calls_observed` remains false for degraded/failed metadata | PASS |
| Returned invocation proof survives every durable failure path | `_record_post_response_provider_failure()` marks adapter metadata degraded, attaches it to structured-output, role, hypothesis, provenance, and retry-validation exceptions, and the harness persists that actual attribution. The new role-validation test asserts returned invocation ID/proof plus `DEGRADED`/`FAILED` and redaction | PASS |
| Smoke waits for the newly submitted chat turn | It records the previous assistant count, waits for Copilot idle, and examines only newly appended non-pending assistant nodes | PASS |
| Smoke retains a strong grounded-answer assertion | `_copilot_response_expression()` requires `RETRYABLE_MESSAGE`, the exact missing quantity `20`, and the canonical failed-message, ERP-receipt, and warehouse evidence IDs in the newly appended response | PASS |
| Topology remains compact and intentional | Ports are scoped to 5 px; route-contract coverage asserts cubic, monotonic paths and node-interior clearance; the timeline positioning correction removes the detached cyan artifact without changing topology semantics | PASS |

### Commands and artifacts reviewed

- current `git diff HEAD --` across the adapter, harness, investigator/synthesis/evaluator runners, session event projection, Dashboard, topology CSS, smoke harness, and focused tests
- primary-provided final verification: `npm test` **34/34**, provider-focused Python **17 passed**, full lint/type checks passed, browser smoke **PASS**
- refreshed `artifacts/workspace/browser-smoke-v1.json` — top-level `PASS`
- final bounded diff review — both previously identified provider-truth branches are corrected and directly covered by focused regression tests

A no-provider browser deep-link attempt could not reuse the earlier closed run because the current server no longer exposed that incident ledger. No new incident was created, consistent with this gate's prohibition on provider calls. The deterministic replay projection was therefore assessed from the actual diff, focused executable test, and refreshed scripted smoke rather than by fabricating another provider run.

### Remaining bounded blockers

None.

The final competition-readiness verdict is **READY**. No P0/P1 remains in this gate.

## 2026-08-30 Full Calibration Gate

Scope: one independent human-browser calibration of the existing real AgentCore incident `missing-20-001-run-2`; no new incident and no additional chat/provider call.

### Verdict

**READY.** The existing incident completed the full governed loop and reconciled cleanly after replay. No reproducible P0/P1 remains.

### Browser acceptance

| Check | Observed result | Verdict |
|---|---|---|
| Existing chat answer | Explicitly states `RETRYABLE_MESSAGE is SUPPORTED`, 100 expected / 80 ERP / 20 queue, and cites `case:missing-20-001-run-2:failed-message`, `:erp-receipt`, and `:warehouse` | PASS |
| Chat authority boundary | Directs the operator to prepare Receipt Message Restart for two-role approval and states chat is read-only and cannot approve or execute autonomously | PASS |
| Investigator roles | Clicked Receipt Retry, Shipment Evidence, and Duplicate Posting; each became the selected graph role and retained `COMPLETE` | PASS |
| Workspace surfaces | Opened Context, Chat, Decision, and Evidence returned; the evidence drawer exposed five admitted records before recovery | PASS |
| Receipt recovery | Prepared Receipt Message Restart; Execute remained gated until Integration Operator and AP Approver independently approved; execution verified ERP 100 / queue 0 | PASS |
| Invoice recovery | Prepared a distinct Invoice Release intent at Case v6; prior approvals did not carry; both roles approved again; execution reached `VERIFIED · CLOSED` | PASS |
| Replay | Replay visibly entered `Replaying Investigation…`, drained back to `Replay Investigation`, retained `replay_safe: true`, and added zero effects | PASS |
| Post-replay Dashboard | Headline reports all 100 units accounted for; expected 100, recorded 100, gap 0; queue chart 0, ERP chart 100, invoice chart 100. The reconciliation line preserves the historical 80/20 segment and terminates at authoritative 100/0 | PASS |
| Provider health | `/healthz` reports `provider_mode: agentcore`, `provider_configured: true`, and `provider_calls: true` | PASS |
| Persisted invocation proof | Three investigator, synthesis, evaluation, and existing chat completion records carry distinct returned invocation IDs with provider `COMPLETE` / invocation `COMPLETED`; incident is `CLOSED`, verified, 100/0, replay-safe, effect delta 0 | PASS |

Final screenshots captured during this gate show the verified closed Agent Workspace and the reconciled post-replay Dashboard at the desktop viewport.

### Material blockers

None. **READY.**
