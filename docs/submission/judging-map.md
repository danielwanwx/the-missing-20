# Judging Map

This is an evidence map, not a submitted score claim. The five dimensions match the
official competition criteria.

| Judging dimension | Five-minute moment | Evidence and honest boundary |
| --- | --- | --- |
| Technical implementation | Steps 2–6: Strands investigation, policy, quorum, execution, verification, replay | `PROVEN`: real local SQLite-backed application path, typed records, fail-closed mutation tests, two effects, zero replay delta. Strands orchestrator + three investigators, audited tools, structured handoffs, and the redacted AgentCore Runtime deployment/invocation/role-chat proof are visible; Nova usefulness remains `PARTIAL`. |
| Design | Step 3: advisory/operational separation | `PROVEN`: model output has no operational or write authority; deterministic policy has no advisory-shaped input. |
| Potential impact | Steps 1–4: investigate a discrepancy and choose a safe next action | Demonstrates a repeatable operations pattern for supply-chain teams: reconcile a 20-unit gap, reduce investigation burden, and prevent unsafe duplicate recovery. All scenarios are synthetic; no production impact metric is claimed. |
| Creativity and originality | Steps 2, 5, and 7: competing investigators, per-action quorum, explicit degraded disclosure | `SCRIPTED_PROVEN` for the reproducible advisory path; the redacted real run is `PARTIAL` (AI citations 1/5, application validation 5/5). AgentCore Runtime deployment/invocation/observability are `PROVEN`; Gateway, Policy, and stable real Nova usefulness remain `NOT_PROVEN`. |
| Presentation | Live Dashboard, Agent Workspace, and seven timed narration beats | The product leads the judge from the 100/80/20 gap through visible agent work, evidence-backed Copilot answers, scripted simulated role-principal approval, controlled recovery, and 100/100 verification. |

## What a judge should verify

1. `make judge-demo` succeeds from the current checkout and reports a clean
   regeneration rather than only reading a stale result.
2. The Dashboard renders exactly 100 API-backed unit records and the Agent Workspace
   exposes actual Strands tool calls, evidence IDs, handoffs, and ordered event sequence.
3. The lifecycle shows two different actions and roles, authoritative after-reads,
   verification, and replay delta `0`.
4. The real role chat is read-only and cannot approve or execute; local synthetic
   recovery requires two distinct simulated role principals and fails closed when the
   live stream or authoritative lifecycle is absent.

## Claims intentionally withheld

Do not score or repeat this package as proof of stable real Nova usefulness, AgentCore
Gateway or Policy behavior, production impact, production data, or public submission
readiness. Runtime deployment, invocation, and observability are proven only within
the redacted evidence boundary; stable model usefulness and production outcomes are
explicitly `NOT_PROVEN` or pending a human gate.
