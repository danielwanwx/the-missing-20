# Judging Map

This is an evidence map, not a submitted score claim. The five dimensions match the
official competition criteria.

| Judging dimension | Five-minute moment | Evidence and honest boundary |
| --- | --- | --- |
| Technical implementation | Steps 4–6: policy, quorum, execution, verification, replay | `PROVEN`: real local SQLite-backed application path, typed records, fail-closed mutation tests, two effects, zero replay delta. |
| Design | Step 3: advisory/operational separation | `PROVEN`: model output has no operational or write authority; deterministic policy has no advisory-shaped input. |
| Potential impact | Steps 1–4: investigate a discrepancy and choose a safe next action | Demonstrates a repeatable operations pattern on synthetic data; no production impact metric or deployment claim is made. |
| Creativity and originality | Steps 2, 5, and 7: competing investigators, per-action quorum, explicit degraded disclosure | `SCRIPTED_PROVEN` for advisory usefulness; the safety architecture is the differentiator. Stable real Nova usefulness and AgentCore are `NOT_PROVEN`. |
| Presentation | Five-stage guided replay and seven timed narration beats | The product leads the judge through one incident; dense proof stays collapsed until requested. Complete/degraded/invalid views make success, degradation, and fail-closed behavior legible. |

## What a judge should verify

1. `make judge-demo` succeeds from the current checkout and reports a clean
   regeneration rather than only reading a stale result.
2. **Start replay**, **Next**, **Previous**, and **Restart** guide the five-stage story;
   the detailed proof remains available in collapsed sections.
3. The lifecycle shows two different actions and roles, authoritative after-reads,
   verification, and replay delta `0`.
4. The degraded and invalid branches remain honest and hide fabricated operational
   state.

## Claims intentionally withheld

Do not score or repeat this package as proof of stable real Nova usefulness, AgentCore
Runtime/Gateway/Policy/Observability/deployment, production impact, production data,
or public submission readiness. Those items are explicitly `NOT_PROVEN` or pending a
human gate.
