# Judging Map

> **September 9 finalization status: NOT READY.** The 20-unit / USD 42,000
> evidence below belongs to the historical September 7 scenario. The separate
> R4 photo-receiving case (PO16/PR7) proves one Box posted and recovered after a
> lost acknowledgement, with verified Airtable/Slack handoffs. It has no linked
> invoice or customer fulfillment. R3 real multi-turn receiving remains FAILED;
> the September 6 8/8 and 15/15 results do not cover that path.
> See the [current finalization ledger](finalization-tracker.md) and
> [R4 scope audit](../audits/2026-09-09-r4-automatic-receiving-recovery-review.md).


This is an evidence map, not a submitted score claim. The five dimensions match the
official competition criteria.

| Judging dimension | Five-minute moment | Evidence and honest boundary |
| --- | --- | --- |
| Technical implementation | Steps 2–6: connected reads, Strands investigation, policy, Manager gate, execution, verification | `PROVEN`: five connected demo-source readers feed a real Bedrock Nova investigation through six bounded tools; typed policy owns a Manager-gated ERPNext demo-tenant recovery, independent Celigo receipt verification, and authoritative reread. Duplicate protection is proven separately by deterministic regression, not claimed as a second live replay. AgentCore Runtime deployment remains a separately proven deployment boundary, not the latest UI execution path. |
| Design | Step 3: advisory/operational separation | `PROVEN`: model output has no operational or write authority; deterministic policy has no advisory-shaped input. |
| Potential impact | Steps 1–4: investigate a discrepancy and choose a safe next action | Demonstrates a repeatable operations pattern for supply-chain teams: reconcile a 20-unit shipment split across receipt, quality, and customer-fulfillment states; reduce investigation burden; and prevent unsafe duplicate recovery. All scenarios are synthetic; no production impact metric is claimed. |
| Creativity and originality | Steps 2, 5, and 7: cross-system reconciliation, hybrid autonomy, explicit degraded disclosure | `PROVEN` on the bounded demo set: 8/8 real-model variants and 15/15 multi-turn cases. The model investigates and explains; deterministic policy knows when to stop; a Manager intervenes only at the write boundary. |
| Presentation | Live Dashboard, Investigation workspace, and seven timed narration beats | The product leads the judge from a 20-unit shipment split 12 accepted / 8 quality-held and a blocked USD 42,000 order through visible agent work, evidence-backed answers, one case-bound Manager decision, controlled recovery, and verified 20/20 delivery and billing. |

## What a judge should verify

1. `make judge-demo` succeeds from the current checkout, verifies the manifest's
   SHA-256 binding to the raw live API capture, and checks cross-source release invariants.
2. The Dashboard renders the exact 20-unit API-backed order state and the Investigation workspace
   exposes actual Strands tool calls, evidence IDs, handoffs, and ordered event sequence.
3. The primary lifecycle shows one declared Manager approve or reject the bound plan,
   followed by scoped ERPNext demo-tenant effects, authoritative after-reads,
   independent Celigo receipt verification. Deterministic tests separately cover replay safety.
4. The real Agent is read-only and cannot approve or execute. The legacy two-role
   Authority-B harness is regression evidence, not a second primary product flow.

## Claims intentionally withheld

Do not score or repeat this package as proof of production-model accuracy, AgentCore
Gateway or Policy behavior, production impact, production data, or public submission
readiness. The latest UI path uses direct Strands Bedrock transport; AgentCore Runtime
deployment/invocation/observability are proven separately within the redacted boundary.
