# The Missing 20 — Five-Minute Judge Demo

**Development status:** ready to be judged locally; video and Devpost submission are not ready.
**Data:** synthetic only.
**Runtime:** local read-only Decision Workspace; no AWS/provider call is made by the
demo runner.

## Before the timer

From the repository root, run:

```bash
make judge-demo
```

The command performs a clean-state regeneration in a temporary directory and validates
the persisted audit. It does not trust a stale successful JSON artifact. To inspect
the read-only UI, run:

```bash
PYTHONPATH=src .venv/bin/python scripts/decision_workspace_server.py
```

Then open the local root URL printed by the server. Choose **Start replay** and use
**Next** to let the product lead the story. The five visual stages cover detection,
agent investigation, safety policy, human approval, and verified recovery. Use the
collapsed proof sections only when a judge asks for technical evidence. The server
exposes only GET routes and no active write control. `make m7-audit` runs the direct
package audit.

## Seven timed beats across five visual stages (5:00 maximum)

The timer is deliberately fixed and contiguous. Each step names the screen to show,
what to say, and the evidence boundary a judge should retain.

| Time | Step | Show and say | Evidence |
| --- | --- | --- | --- |
| 0:00–0:35 | 1. Detect the gap | Click **Start replay**. “The warehouse expects 100 units, while ERP records 80. The system catches the missing 20 before changing anything.” | `PROVEN`: lifecycle evidence and detector genesis. |
| 0:35–1:25 | 2. Investigate in parallel | Click **Next**. “Three bounded investigators compare a retryable message, a genuine short shipment, and a duplicate posting.” | `SCRIPTED_PROVEN`: four-profile scripted Strands trace; synthetic only. |
| 1:25–2:00 | 3. Keep AI advisory | Briefly open **Investigation & safety decision**. “Agents explain likely causes, but they cannot grant or execute an action. The real Nova failure remains visible.” | Real Nova `PROVEN` only for connectivity/degraded observability; stable usefulness `NOT_PROVEN`. |
| 2:00–2:35 | 4. Decide deterministically | Return to the replay and click **Next**. “Code checks authoritative facts and permits only a recovery that cannot create a duplicate.” | `PROVEN`: policy, case/version, source and invariant checks. |
| 2:35–3:35 | 5. Authorize and execute | Click **Next**. “Every controlled step needs two different roles. Neither AI nor one person can act alone.” | `PROVEN`: quorum, signed grant, ControlledExecutor, effect ledger. |
| 3:35–4:20 | 6. Verify and replay | Click **Next**. “The system rereads the result, verifies the missing records, closes the case, and proves a second run makes no duplicate change.” | `PROVEN`: receipt/effect/snapshot closure and replay delta `0`. |
| 4:20–5:00 | 7. State the limits | Switch to `degraded`, then `invalid`. “AI can fail without weakening safety; missing authoritative evidence fails closed.” | Explicit `PROVEN`, `SCRIPTED_PROVEN`, `NOT_PROVEN`; no public submission claim. |

## Closing line

“The Missing 20 uses AI where investigation is expensive and uncertain, deterministic
policy where operational truth matters, and humans where authorization belongs. The
model can explain a path; only validated facts, policy, two-role approval, controlled
execution, verification, and replay can close it.”

## Failure/degradation branch

If the advisory provider is unavailable, switch to `?mode=degraded`. The operational
projection remains the same deterministic lifecycle, while hypotheses and incident
report content disappear and the failure is labeled. If an authoritative lifecycle
record is missing or invalid, switch to `?mode=invalid`; operational panels are hidden
and the page says `UNAVAILABLE`. Neither branch invents an approval, effect, pass, or
closed state.

## Operator boundary

This run card is a private judging aid. It does not authorize a provider request,
cloud deployment, public release, video upload, or Devpost submission. The final
`ready-to-be-judged` product decision is a human gate.
