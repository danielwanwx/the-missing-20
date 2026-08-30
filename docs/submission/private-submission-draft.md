# Private Submission Draft — The Missing 20

**State:** `PRIVATE_READY_TO_BE_JUDGED`
**Submission state:** `NOT_READY_TO_SUBMIT` — field-ready, still private
**Audience:** internal product/judge review only. Do not publish or submit.
**Data:** synthetic only.

The complete field-by-field English draft is in
[`devpost-submission-draft.md`](devpost-submission-draft.md). This document keeps
the internal evidence narrative and release boundary.

## One-line pitch

The Missing 20 helps an operations team investigate a supply-chain discrepancy with
bounded multi-agent reasoning, then closes only the actions that deterministic policy,
two distinct simulated role principals, controlled execution, authoritative verification, and replay
can prove safe.

## What the private package demonstrates

The five-minute guided path starts with a synthetic 20-unit discrepancy, shows competing
advisory hypotheses and evidence gaps, keeps model output explicitly advisory, derives
separate deterministic decisions for receipt restart and invoice release, obtains an
exact per-action two-role quorum, executes controlled effects, rereads authoritative
state, verifies postconditions, and replays without creating a second effect.

The local product exposes a live Dashboard and Agent Workspace. Its Copilot is
read-only and advisory. Separate operational controls can affect only the local
synthetic experiment, require an exact two-role quorum from scripted simulated
principals (the demo client has no authentication), and execute through the
deterministic `ControlledExecutor`; no external write is available. The configured
real AgentCore Runtime path is separately evidenced and remains read-only.

Strands is visible in the hero path: one orchestrator coordinates three fixed
investigators, audited read tools, structured findings, evidence handoffs, and
synthesis/evaluation. The real Runtime proof additionally includes a role-specific
read-only chat and an explicit refusal to prepare, approve, authorize, or execute.

## Truthful evidence statement

The local deterministic lifecycle is `PROVEN`. The four-profile scripted advisory
trace is `SCRIPTED_PROVEN` and synthetic. The redacted real run is `PROVEN` for the
AgentCore Runtime deployment/invocation/observability boundary and `PARTIAL` for Nova
advisory usefulness (AI citation coverage 1/5; application validation 5/5). Stable
real Nova usefulness is `NOT_PROVEN`; AgentCore Gateway and Policy are `NOT_PROVEN`.
Role chat is real-provider-backed but read-only. Model output is
`ADVISORY — NOT AN OPERATIONAL DECISION` and has `NO WRITE AUTHORITY`.

## Why this is useful

Most operations assistants stop at a plausible explanation. This prototype keeps the
high-cost investigation separate from the operational trust root: an investigator
can surface alternatives and missing evidence, but it cannot silently convert a
plausible narrative into a write. That separation makes failure visible and gives a
human a compact, auditable decision surface.

## Private review state

The package is ready for a human to judge locally. It is not a public release, not a
video, and not a Devpost entry. The redacted proof includes a deployed AgentCore
Runtime boundary; it does not claim Gateway, Policy, stable model usefulness, or
production business impact. The separate 2026-08-30 acceptance run added an estimated
`$0.0491432` for one real multi-agent investigation and one real read-only role chat.
The cumulative known engineering estimate is `$0.2240576`; transport cycles are not
described as model calls. The hard cap remains `$0.60`.

## Suggested judge path

Run `make judge-demo`, open the local Dashboard, then follow the live unit path into
Agent Workspace, Copilot, two-role approval, controlled recovery, and verification as described in
[`docs/demo/five-minute-demo.md`](../demo/five-minute-demo.md). Use
[`evidence-matrix.md`](evidence-matrix.md), [`judging-map.md`](judging-map.md), and
[`known-limitations.md`](known-limitations.md) to distinguish demonstrated behavior
from explicit gaps.
