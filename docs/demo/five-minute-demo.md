# The Missing 20 — Five-Minute Judge Demo

**Development status:** ready to be judged locally; video and Devpost submission are not ready.
**Data:** synthetic only.
**Runtime:** local synthetic incident API, ordered SSE ledger, Dashboard, and Agent
Workspace; no AWS/provider call is made by the demo runner.

## Before the timer

From the repository root, run:

```bash
make judge-demo
```

The command performs a clean-state regeneration in a temporary directory and validates
the persisted audit. It does not trust a stale successful JSON artifact. To inspect
the interactive UI, run:

```bash
PYTHONPATH=src .venv/bin/python scripts/decision_workspace_server.py
```

Then open the local root URL printed by the server. The initial page waits for an
explicit **Start Investigation** click; the same control is available on Dashboard and
Agent Workspace. The Dashboard receives the same ordered events as the backend and
renders every unit. Open **Agent Workspace** to watch the paced orchestrator,
investigators, tools, evidence, and handoffs. Ask the Copilot a question, prepare
**Receipt Message Restart**, approve it as the two scripted simulated role principals,
execute, and verify the 100/100 result. Then prepare the separate **Invoice Release**
action and approve it again with both simulated role principals; the final gate is
`VERIFIED · CLOSED` with no inherited quorum. After closure, **Replay Investigation**
only re-emits the existing immutable ledger; it cannot start a new operational run.
Operational controls are restricted to local synthetic state; Copilot remains advisory
and no route can write to an external system. `make m7-audit` runs the direct package
audit.

## Seven timed beats across five visual stages (5:00 maximum)

The timer is deliberately fixed and contiguous. Each step names the screen to show,
what to say, and the evidence boundary a judge should retain.

| Time | Step | Show and say | Evidence |
| --- | --- | --- | --- |
| 0:00–0:35 | 1. Detect the gap | On **Dashboard**, point to 100 warehouse records, 80 ERP records, and the 20 exact IDs held at the queue; click **Start Investigation** when ready. | `PROVEN`: local API, ordered ledger, lifecycle evidence, detector genesis. |
| 0:35–1:25 | 2. Investigate in parallel | Open **Agent Workspace**. Watch the paced ordered trace: three bounded investigators start, call tools, collect evidence, and hand results to the orchestrator. | `SCRIPTED_PROVEN`: scripted Strands trace; synthetic only. |
| 1:25–2:00 | 3. Keep AI advisory | Ask Copilot which evidence proves the gap. “The agent explains and cites; it cannot approve or execute.” | Real Nova `PROVEN` only for connectivity/degraded observability; stable usefulness `NOT_PROVEN`. |
| 2:00–2:35 | 4. Decide deterministically | Choose **Prepare recovery**. “Code checks authoritative facts and permits only a recovery that cannot create a duplicate.” | `PROVEN`: policy, case/version, source and invariant checks. |
| 2:35–3:35 | 5. Authorize and execute | Approve **Receipt Message Restart** with the two distinct simulated role principals and execute it; then prepare **Invoice Release** and approve that new intent with both principals again. “Neither AI nor one role principal can act alone, and approvals do not carry across actions.” | `PROVEN`: per-action quorum, signed grants, ControlledExecutor, two-effect ledger. |
| 3:35–4:20 | 6. Verify and replay | Show 100/100 after receipt recovery, then the final `VERIFIED · CLOSED` gate after invoice release. Optionally click **Replay Investigation** to re-emit the immutable investigation ledger; it creates no action or effect. “Each action is reread and executor replay proves no duplicate change.” | `PROVEN`: receipt/effect/snapshot closure for both actions, executor replay delta `0`, and immutable ledger replay. |
| 4:20–5:00 | 7. State the limits | Switch to `degraded`, then `invalid`. “AI can fail without weakening safety; missing authoritative evidence fails closed.” | Explicit `PROVEN`, `SCRIPTED_PROVEN`, `NOT_PROVEN`; no public submission claim. |

## Closing line

“The Missing 20 uses AI where investigation is expensive and uncertain, deterministic
policy where operational truth matters, and humans where authorization belongs. The
model can explain a path; only validated facts, policy, a fresh two-role approval for
each action, controlled execution, verification, and replay can close it.”

## Failure/degradation branch

If the advisory provider is unavailable, switch to `?mode=degraded`. The operational
projection remains the same deterministic lifecycle, while live investigation, agent
graph, hypotheses, traces, evidence, and Copilot surfaces are hidden and the failure is
labeled. If an authoritative lifecycle record is missing or invalid, switch to
`?mode=invalid`; operational panels are hidden and the page says `UNAVAILABLE`. Neither
branch invents an approval, effect, pass, or closed state.

## Operator boundary

This run card is a private judging aid. It does not authorize a provider request,
cloud deployment, public release, video upload, or Devpost submission. The final
`ready-to-be-judged` product decision is a human gate.
