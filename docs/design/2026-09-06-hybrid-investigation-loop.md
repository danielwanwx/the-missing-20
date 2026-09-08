# Hybrid Investigation Loop

## Objective

Turn the same visible operational symptom—an apparent 20-unit reconciliation gap—into a reusable, evidence-bound investigation system that can distinguish recoverable process failures from conditions that must stop, escalate, or take no action.

## Loop contract

- **Inputs:** incident identity, scoped ERP/WMS/queue/collaboration records, control policy, prior decisions, and authoritative post-action rereads.
- **State:** case version, evidence ledger, source freshness, hypotheses, tool trace, advisory disposition, policy decision, approval, execution receipt, and verification result.
- **Observe:** independent source tools retrieve only scoped records. SDK lifecycle hooks capture redacted model/tool timing and trace correlation.
- **Orient:** the Strands agent selects evidence adaptively and returns typed findings. The production validation harness can run three independent investigators, synthesis, and an independent evaluator.
- **Decide:** deterministic policy joins evidence and owns action authority. It may recover, stop for missing/conflicting evidence, require one manager approval, or declare that no action is needed.
- **Act:** only approved, bounded, idempotent operations are available. The model never receives a general-purpose write tool.
- **Verify:** authoritative rereads must prove the intended business state and the absence of duplicate effects before the case can close.
- **Stop conditions:** unresolved/conflicting evidence, physical shortage, unavailable lookup, stale case version, duplicate/idempotency conflict, failed verification, or completion.

## Counterfactual case matrix

| Case | Same visible symptom, different hidden truth | Correct behavior |
| --- | --- | --- |
| Uncommitted receipt | 12 units are staged but absent from ERP; 8 are in an approved quality lot | Propose a bounded 12+8 recovery, require manager approval, execute once, reread, verify |
| Lost acknowledgement | ERP already contains the receipt but an integration acknowledgement is absent | Do not repost; repair/reconcile the acknowledgement path |
| Wrong quality lot | The apparent remainder is tied to an ineligible quality lot | Stop; do not transfer the wrong inventory |
| Lookup unavailable | A required authoritative source cannot be read | Stop for evidence; never infer a write from partial data |
| Physical shortage | Warehouse evidence proves the units never arrived | Stop and open an operational shortage path; do not manufacture inventory |
| Transfer already present | The intended transfer is already recorded | No duplicate write; return an idempotent no-op/reconciliation result |
| Evidence conflict | Two authoritative records disagree on quantity or identity | Stop for cross-source resolution; surface the exact conflict |
| Normal complete | All systems already agree and no exception remains | Close with no approval and no mutation |

## Why this is deeper than an SDK demo

The model is one reasoning component inside an application-owned control loop. Strands provides model-driven tool selection, structured output, lifecycle hooks, trace metadata, and multi-agent investigation primitives. The application supplies the domain evidence contract, deterministic authority boundary, approval policy, idempotent executor, authoritative verification, replayable case state, and counterfactual evaluation matrix.

Graph or Swarm orchestration can be introduced when a case needs durable branching or specialist handoffs, but it is not used merely to increase agent count. The current three-investigator → synthesis → evaluator harness is the stronger default for this decision because it preserves independent evidence review while deterministic code retains transaction authority.

## Acceptance evidence

- All eight counterfactuals must produce their expected disposition under the real Strands/Bedrock runtime.
- Each model/tool call must produce correlated, redacted hook telemetry.
- Unsafe or unresolved variants must have zero business writes and zero unnecessary manager touches.
- Recoverable variants must remain bounded, idempotent, manager-gated when necessary, and authoritatively verified.
- The dashboard must expose the selected case, source reads, live hook/tool activity, policy state, approval requirement, effect receipt, and verification state from backend events rather than a timer-only animation.
