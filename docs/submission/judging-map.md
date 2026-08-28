# Judging Map

This is an evidence map, not a submitted score claim. The five dimensions match the
official competition criteria.

| Judging dimension | Five-minute moment | Evidence and honest boundary |
| --- | --- | --- |
| Technical implementation | Steps 4–6: policy, quorum, execution, verification, replay | `PROVEN`: real local SQLite-backed application path, typed records, fail-closed mutation tests, two effects, zero replay delta. |
| Design | Step 3: advisory/operational separation | `PROVEN`: model output has no operational or write authority; deterministic policy has no advisory-shaped input. |
| Potential impact | Steps 1–4: investigate a discrepancy and choose a safe next action | Demonstrates a repeatable operations pattern on synthetic data; no production impact metric or deployment claim is made. |
| Creativity and originality | Steps 2, 5, and 7: competing investigators, per-action quorum, explicit degraded disclosure | `SCRIPTED_PROVEN` for advisory usefulness; the safety architecture is the differentiator. Stable real Nova usefulness and AgentCore are `NOT_PROVEN`. |
| Presentation | Live Dashboard, Agent Workspace, and seven timed narration beats | The product leads the judge from the 100/80/20 gap through visible agent work, evidence-backed Copilot answers, human approval, controlled recovery, and 100/100 verification. |

## What a judge should verify

1. `make judge-demo` succeeds from the current checkout and reports a clean
   regeneration rather than only reading a stale result.
2. The Dashboard renders exactly 100 API-backed unit records and the Agent Workspace
   exposes actual tool calls, evidence IDs, handoffs, and ordered event sequence.
3. The lifecycle shows two different actions and roles, authoritative after-reads,
   verification, and replay delta `0`.
4. Copilot cannot approve or execute; local synthetic recovery requires two distinct
   roles and fails closed when the live stream or authoritative lifecycle is absent.

## Claims intentionally withheld

Do not score or repeat this package as proof of stable real Nova usefulness, AgentCore
Runtime/Gateway/Policy/Observability/deployment, production impact, production data,
or public submission readiness. Those items are explicitly `NOT_PROVEN` or pending a
human gate.
