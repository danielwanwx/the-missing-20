# Real Agent Dashboard Optimization

## Goal

Replace the dashboard's deterministic chat answer path with a real, read-only
Strands/Nova Pro advisory agent that can inspect admitted SaaS evidence and
return a validated, source-cited decision. The dashboard must never present a
deterministic fallback as an AI-agent result.

## Scope and ordering

This is one vertical change with two ordered milestones:

1. Improve the real agent's evidence retrieval and structured decision
   contract, then rerun the existing 17-case, no-outcome-leakage matrix.
2. Expose the same bounded real-agent turn through the dashboard chat API and
   UI, including provenance and fail-closed availability state.

The existing recovery controls remain deterministic and separately authorized.
The new chat agent is advisory and read-only; it cannot approve, execute,
restart, release, or write to an external provider.

## Architecture

### Evidence boundary

Each agent turn receives only case-scoped, pre-decision facts through five
separate allowlisted read tools:

- `read_erp_evidence`: ERP document state and transfer or invoice identifiers.
- `read_airtable_evidence`: exception and reconciliation records.
- `read_celigo_evidence`: integration flow/run state.
- `read_collaboration_evidence`: Jira and Slack escalation evidence.
- `read_control_context`: request principal, temporal condition, guard status,
  and policy constraints at decision time.

The tools return evidence IDs and source payloads, never expected outcomes,
post-execution effects, credentials, or write handles. The live case uses the
same source categories, with unavailable sources represented explicitly rather
than inferred.

### Decision contract

The real model must call `read_control_context` and every source relevant to
the request before proposing a decision. It emits a typed advisory record:

- `disposition`: one of `RECOVERY_COMPLETE`, `PROTECT`, `NEEDS_EVIDENCE`,
  `DENY`, `SAFE_NOOP`, or `HARD_STOP`.
- `evidence_ids`: non-empty exact IDs drawn from tool output.
- `reason`: concise, evidence-grounded explanation.
- `safe_next_step`: read-only or deterministic-control handoff only.
- `write_performed`: always `false`.

The application validates the enum, tool trace, exact cited IDs, and no-write
assertion. Invalid, incomplete, or provider-failed output becomes an explicit
`AGENT_UNAVAILABLE` / `VALIDATION_FAILED` response, not a best-effort answer.

### Dashboard integration

`/api/v1/agent-platform/ask` becomes the real-agent gateway. Its response adds
agent mode, provider provenance, source-tool trace, structured advisory result,
latency, and availability state. The existing deterministic `AgentPlatform`
answer method is not used as a fallback.

The chat UI renders a compact result card: disposition, source chips, cited
IDs, and real-time status. It removes explanatory filler and labels unavailable
state plainly. Existing approval/execution buttons remain tied to the
deterministic control plane and must not be triggered by chat.

## Failure handling and safety

- Missing source data produces `NEEDS_EVIDENCE` only when that conclusion is
  supported by control context; malformed source data fails validation.
- Provider authentication, timeout, budget, or transport failure returns
  `AGENT_UNAVAILABLE` and a retry instruction. There is no deterministic or
  synthetic conversational fallback.
- A proposed privileged action, untraceable evidence ID, or unsupported
  disposition fails closed.
- Per-turn provider budget and timeout remain bounded and observable.
- Existing immutable Golden artifacts and historical provider-attempt claims
  are never modified.

## Tests and acceptance

1. Unit tests prove source-tool payload separation, exact evidence-ID
   validation, no-write enforcement, and failure mapping.
2. The real 17-case matrix is rerun with no expected result, invariant, or
   post-execution outcome exposed to the model.
3. Acceptance target: every case calls required tools; zero unauthorized-write
   claims; all provider/validation failures are explicit; and the rubric pass
   rate materially improves from the 2/17 baseline without weakening checks.
4. A local dashboard smoke test proves one real chat response, one explicit
   unavailable response, and that chat cannot invoke execute/approve routes.

## Non-goals

- No autonomous external writes from the model.
- No UI-only simulation of source calls or agent activity.
- No claim that a regression run is award-ready unless the recorded result
  satisfies the acceptance criteria above.
