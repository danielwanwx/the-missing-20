# The Missing 20 — Five-Minute Demo Script

> Historical September 7 storyboard only. Current receiving finalization is not
> accepted; do not join R4 photo/PR7 footage to this separate 20-unit billing case.
> See [current tracker](../submission/finalization-tracker.md). Final recording waits
> for the frozen business path.

**Target length:** 4:35–4:50.
**Primary path:** Dashboard → Investigation → Manager decision → verified closure.
**Disclosure:** all enterprise records are purpose-built demo data. The hero path reads
and writes an isolated ERPNext/Frappe Cloud tenant, invokes Strands/Nova, and reads
correlated SaaS records; AgentCore Runtime remains separate redacted deployment proof.

## Story in one sentence

Five enterprise systems disagree about twenty units; a Strands agent correlates the
evidence, a deterministic control plane constrains the remedy, one Manager keeps the
stop-or-release decision, and an authoritative reread proves whether the fix worked.

## Timed script

| Time | Screen and action | Spoken narration |
| --- | --- | --- |
| 0:00–0:25 | Open **Dashboard** in the healthy baseline. Show current source state; unchanged records should remain still. | “Supply-chain teams rarely have one source of truth. ERP, integration, quality, ticketing, and collaboration tools each hold part of the answer. The Missing 20 turns those disconnected facts into one live, human-controlled investigation loop.” |
| 0:25–0:50 | Open the linked ERPNext record, apply the prepared demo exception, and return to the Dashboard. | “Twenty controllers physically arrived. Twelve entered Stores and eight remain quality-held, while a USD 42,000 customer order is still undelivered and unbilled. That is the symptom—not the diagnosis. The external demo-tenant source change is what advances this Dashboard and its ordered backend ledger.” |
| 0:50–1:20 | Point to live movement, system states, working capital, the held USD 42,000 customer order, and the scrolling event feed. Click one source node to expose its parameters and external-system link. | “ERPNext records the receipt and customer order. Airtable carries the exact-lot quality disposition. Celigo carries an integration attempt and independent receipt. Jira and Slack add operating context, but cannot prove the root cause. USD 42,000 remains explicitly labeled as counterfactual revenue at risk—not revenue earned.” |
| 1:20–1:45 | Click **Investigation**. Ask: “Why is this not a physical shortage, and what must be reread before any retry?” | “Before starting a model run, an operator can question the evidence agent. The answer is case-scoped, cites the source records it used, and has no approval or write capability.” |
| 1:45–2:35 | Click **Authorize diagnosis**. Let the trace advance. Highlight Observe → Retrieve → Reconcile → Evaluate → Decide, bounded source tools, SDK hooks, and changing metrics. | “Now the Strands loop runs six bounded read and reconciliation tools for this case. It reconciles business keys and quantities, tests competing causes, records tool calls and evaluator feedback, and streams every state transition. This is not a pre-baked animation—the visible sequence, events, tools, latency, tokens, and evidence all come from the backend run.” |
| 2:35–3:10 | Expand the diagnosis and evidence. Ask a follow-up such as: “What exact recovery scope is safe, and what would make you stop?” | “The agent rules out physical shortage and duplicate receipt, proves that the exact eight-unit lot is eligible for release, and binds the remaining customer fulfillment scope. It also explains the stop conditions: stale evidence, a conflicting business key, an unapproved lot, or an incomplete ledger read. The model recommends; deterministic policy independently decides whether the packet is admissible.” |
| 3:10–3:35 | Show **Manager decision**. Briefly show Reject as an available human path, then choose **Approve & execute** for the hero run. | “The system knows when to stop for a human. One Manager reviews a packet bound to this case version, evidence tuple, plan digest, scope, and idempotency key. Reject creates no effect. Approve writes only the exact M20-scoped records in the isolated ERPNext demo tenant.” |
| 3:35–4:10 | Watch execution and verification. Return to Dashboard when it reaches verified. Open the Sales Invoice from the metric inspector. | “The executor applies the bounded eight-unit quality release, resumes the exact customer order, and creates its delivery and sales invoice. The case closes only after fresh ERPNext document, stock-ledger, GL, and Celigo receipt reads verify the effects. USD 42,000 now changes from revenue at risk to observed billed revenue.” |
| 4:10–4:35 | Show the interactive architecture for 15–20 seconds. | “The reusable pattern is the product: connectors and read tools on the left; Strands investigation and AgentCore advisory runtime in the middle; deterministic policy, Manager authority, idempotent execution, reread, and an immutable evidence ledger on the right. No model write authority crosses that boundary.” |
| 4:35–4:50 | End on the verified Dashboard. | “The Missing 20 uses agents where investigation is uncertain, deterministic controls where truth matters, and human review only when a consequential decision is ready. Find the gap. Prove the cause. Close it safely.” |

## Required visible proof

- The live sequence changes only when an actual source/workflow event occurs. Do not
  create extra events to satisfy a recording count.
- Clicking a system opens real identifiers, source status, and an external-system link.
- The Investigation run visibly changes tools, hooks, stage, latency, token, evidence,
  and confidence fields.
- At least two conversational turns remain visible and cite case evidence.
- The Manager controls are absent before a plan is ready and appear only at the gate.
- Verification shows the authoritative before/after state. Describe replay safety as
  deterministic regression coverage, not as a second live attempt.
- After returning to the healthy Dashboard, Investigation still opens the verified
  run, six-tool trace, conversation, approval, source receipts, and Resolution Packet.
- The architecture stays on screen long enough to read the authority boundary.

## Backup branch

If the real provider is unavailable, do not pretend the model completed. Show the
visible degraded state and say: “The advisory layer is unavailable, so the system does
not invent a diagnosis or unlock recovery.” Show any local controlled fallback explicitly as a separate synthetic path.
Do not spend the primary video switching through every negative mode.

## Claims to avoid

- Do not describe synthetic records as production customer data.
- Do not claim AgentCore Gateway or Policy.
- Do not claim stable production Nova accuracy from one acceptance run.
- Do not say the primary UI requires two approvers. The legacy Authority-B regression
  harness is separate from the one-Manager competition interaction.
