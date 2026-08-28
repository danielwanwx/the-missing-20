# Milestone 7 Private Competition Package

**Status:** approved for bounded implementation
**Authority:** M6 `APPROVE_M6_EXISTING_EVIDENCE_BOUNDARY`
**Scope:** private, offline demo and submission-audit package; no operational behavior changes

## Loop contract

**Goal:** produce a private package that a judge can run from a clean checkout and
understand in five minutes how the system moves from a synthetic discrepancy through
advisory investigation, deterministic policy, two-role authorization, controlled
execution, verification, and replay.

**Inputs:** the independently validated M5 lifecycle and Decision Workspace artifacts,
the M6 existing-evidence proof, Golden v2, the local read-only workspace assets, and
synthetic fixtures. No provider call, AWS call, network resource, employer material,
credential, or public submission is in scope.

**Execute:** freeze the seven-step story and evidence taxonomy in documentation, add a
local judge-demo runner with a clean-state regeneration check, add a fail-closed package
audit, and persist a redacted private audit manifest. The package is a judge-facing
read path only; it does not add controls or change the executor.

**Checks:** package source and digest checks, lifecycle/workspace validation, M6 proof
validation, Golden v2 safety and scripted-proof status, complete/degraded/invalid
browser-smoke manifest, five-minute timeline bounds, static secret/remote-resource
scan, and mutation tests that cannot promote a claim or readiness state by merely
re-signing a package digest.

**Feedback:** one focused material correction is allowed for a reproducible audit or
story defect. Optional wording, visual polish, deployment, and submission-platform
work are deferred. A second material defect stops M7 and is reported as a root-cause
blocker.

**Records:** this design, the implementation plan, the private audit manifest, the
five-minute demo script, the evidence matrix, the judging map, known limitations, and
the independent M7 gate record.

**Stop:** success is `PRIVATE_READY_TO_BE_JUDGED` with a passing clean-state check.
The package deliberately never reports `READY_TO_SUBMIT`, never publishes, and never
uploads a video or Devpost entry.

## Authority boundary

The advisory branch is useful intelligence, not an operational authority. It may
produce competing hypotheses, knowledge retrieval, evidence gaps, uncertainty, and an
incident-report draft. It cannot classify operational state, grant an action, approve
an action, call `ControlledExecutor`, verify an effect, or alter replay semantics.

Deterministic code owns evidence identity and completeness, state classification,
policy eligibility, authorization, execution, verification, and replay. Controlled
effects require the distinct `INTEGRATION_OPERATOR` and `AP_APPROVER` roles for each
action. The Decision Workspace exposes no active write controls.

The package uses three non-interchangeable evidence classes:

| Class | Meaning in this package |
| --- | --- |
| `PROVEN` | Deterministic local lifecycle and the already-consumed real Nova connectivity/degraded-observability record are validated. The latter does not prove usefulness. |
| `SCRIPTED_PROVEN` | Four-profile, byte-identical synthetic Strands advisory trace and complete workspace projection pass offline checks. |
| `NOT_PROVEN` | Stable real Nova usefulness and every AgentCore capability remain unproven. They must not be described as working. |

All advisory and provider records carry `ADVISORY — NOT AN OPERATIONAL DECISION` and
`write_authority: false`. `PROVEN` on the real provider row is scoped only to
connectivity and degraded-outcome observability.

## Seven-step acceptance semantics

`docs/demo/five-minute-demo.md` defines exactly seven contiguous steps from `0` to
`300` seconds. The audit requires the exact step IDs, no overlap or gap, and total
duration at most five minutes. A clean-state check regenerates the lifecycle, M6
proof, and complete/degraded workspace in a temporary repository before accepting the
persisted private audit. A stale successful artifact therefore cannot satisfy the
gate by itself.

The required story is:

1. detect the synthetic 20-EA discrepancy;
2. show advisory competing hypotheses and evidence gaps;
3. separate advisory confidence/disagreement from operational truth;
4. show deterministic policy and per-action eligibility;
5. show the exact two-role quorum and controlled effects;
6. show authoritative reread, verification, and zero-effect replay;
7. disclose evidence classes, real-Nova degradation, AgentCore limits, and the human gate.

## Audit contract

`M7PrivateCompetitionAudit/v1` is canonical JSON with a digest over all fields except
`audit_digest`. It records the reviewed source ledger, seven-step timeline, evidence
matrix, acceptance checks, frozen cost boundary, and explicit private-only state.

The loader recomputes the complete expected audit from current source bytes and rejects
missing, malformed, changed, contradictory, or unapproved inputs. It also rejects:

- fewer or more than seven story steps, non-contiguous times, or a duration over 300s;
- a workspace that is not complete/degraded/invalid fail-closed as appropriate;
- a lifecycle that is not `CLOSED`, lacks the two distinct action effects, or has a
  nonzero replay effect delta;
- M6 evidence that promotes stable real Nova usefulness or any AgentCore capability;
- claims that grant advisory or provider write/operational authority;
- a package marked public, submitted, or ready-to-submit;
- remote resource URLs, secret-like material, or non-synthetic provenance in package files.

The audit records zero new provider/AWS calls and zero new cost. The prior cumulative
estimate remains `$0.1250496` against the `$0.60` hard cap. This M7 scope cannot change
that budget.

## Non-goals and human gate

M7 does not install or invoke AgentCore, call AWS/Bedrock/Nova, add credentials or
permissions, expose a mutation endpoint, alter policy/execution code, publish a
repository, upload a video, submit Devpost, or make a legal/product claim. Final
`ready-to-be-judged` product judgment remains a human gate; until then the package is
private and explicitly not ready to submit.
