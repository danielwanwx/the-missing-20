# Private Submission Draft — The Missing 20

**State:** `PRIVATE_READY_TO_BE_JUDGED`
**Submission state:** `NOT_READY_TO_SUBMIT`
**Audience:** internal product/judge review only. Do not publish or submit.
**Data:** synthetic only.

## One-line pitch

The Missing 20 helps an operations team investigate a supply-chain discrepancy with
bounded multi-agent reasoning, then closes only the actions that deterministic policy,
two distinct human roles, controlled execution, authoritative verification, and replay
can prove safe.

## What the private package demonstrates

The five-minute guided path starts with a synthetic 20-unit discrepancy, shows competing
advisory hypotheses and evidence gaps, keeps model output explicitly advisory, derives
separate deterministic decisions for receipt restart and invoice release, obtains an
exact per-action two-role quorum, executes controlled effects, rereads authoritative
state, verifies postconditions, and replays without creating a second effect.

The read-only Decision Workspace exposes complete, provider-degraded, and
fail-closed/unavailable views. It intentionally has no write control.

## Truthful evidence statement

The local deterministic lifecycle is `PROVEN`. The four-profile scripted advisory
trace is `SCRIPTED_PROVEN` and synthetic. The previously consumed real Nova record is
`PROVEN` only for connectivity and degraded-outcome observability; stable real Nova
usefulness is `NOT_PROVEN`. Every AgentCore capability is `NOT_PROVEN`. Model output is
`ADVISORY — NOT AN OPERATIONAL DECISION` and has `NO WRITE AUTHORITY`.

## Why this is useful

Most operations assistants stop at a plausible explanation. This prototype keeps the
high-cost investigation separate from the operational trust root: an investigator
can surface alternatives and missing evidence, but it cannot silently convert a
plausible narrative into a write. That separation makes failure visible and gives a
human a compact, auditable decision surface.

## Private review state

The package is ready for a human to judge locally. It is not a public release, not a
video, not a Devpost entry, and not a claim of deployed AgentCore. No new AWS/provider
call is part of this package; the cumulative estimated prior cost remains `$0.1250496`
against a `$0.60` hard cap.

## Suggested judge path

Run `make judge-demo`, open the local read-only workspace, choose **Start replay**, and follow
[`docs/demo/five-minute-demo.md`](../demo/five-minute-demo.md). Use
[`evidence-matrix.md`](evidence-matrix.md), [`judging-map.md`](judging-map.md), and
[`known-limitations.md`](known-limitations.md) to distinguish demonstrated behavior
from explicit gaps.
