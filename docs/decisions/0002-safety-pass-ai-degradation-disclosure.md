# 0002: Safety Pass with AI Degradation Disclosure

**Date:** 2026-08-27
**Status:** independently approved; M4 `APPROVE_M4_DISCLOSED_DEGRADATION`
**Supersedes:** the real-AI-usefulness PASS requirement in M4 Authority Rebaseline B

## Decision

M4 is accepted when its deterministic Safety Proof and scripted synthetic advisory proof
pass, the consumed real Nova integration attempt is preserved as redacted degradation
evidence, and every product surface labels stable real Nova usefulness `NOT_PROVEN`.

This is an acceptance rebaseline, not a claim that the failed real advisory proof passed.
The real attempt remains `DEGRADED`, `ADVISORY_PROVIDER_FAILURE`, and AI Usefulness
`FAIL`. It is evidence of a connected provider path and observable fail-safe behavior
only.

## Reason

The product's safety value is independently proven: deterministic code owns evidence
integrity, classification, eligibility, policy, authorization, execution, verification,
and replay; exact distinct operator and AP-approver attestations are required before a
controlled effect. The model is explicitly advisory and its failure neither grants nor
vetoes an operational decision. Requiring one provider run to prove stable usefulness
would conflate provider reliability with the already-independent safety architecture.

The competition package will therefore show useful scripted agent behavior honestly,
show the real degraded trace honestly, and avoid unsupported claims.

## Evidence classes

| Class | Meaning | Required label |
|---|---|---|
| `PROVEN` | Deterministic tests, persisted execution evidence, or recorded real integration behavior support the claim | `PROVEN` |
| `SCRIPTED_PROOF` | Synthetic scripted Strands trace demonstrates the intended advisory experience but not stable real-model behavior | `SCRIPTED SYNTHETIC PROOF` |
| `NOT_PROVEN` | No accepted evidence supports a stable product claim | `NOT PROVEN` |

No UI, README, demo, architecture record, or submission text may collapse these classes.

## Revised M4 acceptance

M4 passes only when all conditions hold:

1. Deterministic Safety Proof is `PASS` and all Golden safety counters are zero.
2. Exact two-human approval, controlled execution, verification, crash recovery, and
   replay tests pass.
3. Scripted synthetic advisory proof is `PASS` and is visibly labeled scripted.
4. The consumed Nova attempt claim and redacted degraded outcome remain immutable and
   visible as real integration/degradation evidence.
5. Stable real Nova usefulness is `NOT_PROVEN` everywhere user-facing.
6. Golden composition reports separate safety, scripted usefulness, and real-provider
   evidence states; the degraded real result cannot become `PASS`.
7. Full offline gates, security/provenance checks, and an independent final M4 gate pass.

M4 promotion status may be `PASS_WITH_DISCLOSED_AI_DEGRADATION`; it must never be plain
`PASS` where that could imply stable real-model usefulness.

## Safety boundaries

- Agent/model output remains non-authoritative and has read-only evidence/knowledge
  capabilities.
- Deterministic policy remains the only source of operational eligibility.
- A controlled effect still requires two distinct trusted human roles over one exact
  intent digest.
- Missing, malformed, conflicting, or unavailable advisory output creates no grant and
  cannot block an otherwise valid deterministic decision.
- Provider artifacts are redacted; all scenarios and demo data are synthetic.
- No additional AWS/provider call, retry, probe, fallback, or spending is authorized.
- Current cumulative estimated AWS promotional-credit consumption is `$0.1250496`; the
  unchanged hard cap is `$0.60`.

## Milestone consequences

- **M5:** build a read-only Decision Workspace that clearly separates incident facts,
  advisory hypotheses/gaps/status, deterministic decision, two-person approvals,
  controlled effects, verification, and audit history. Complete and degraded advisory
  browser paths are required.
- **M6:** package only the existing minimum credible AWS/AgentCore integration boundary.
  Real Bedrock/Nova invocation and observable degradation may be marked proven; stable
  Nova usefulness, AgentCore deployment, Gateway, Policy, Cognito, and other unsupported
  capabilities are `NOT_PROVEN`. No new provider or AWS call is allowed.
- **M7:** produce a clean-state five-minute local demo and submission-ready private
  assets. The story distinguishes proven safety, scripted advisory value, and unproven
  stable real-model usefulness. Public release, video recording/upload, and Devpost
  submission remain human-gated.

## Loop contract

**Goal:** reach a private `ready-to-be-judged` package without overstating AI or AWS
evidence.

**Inputs:** current repository, synthetic fixtures, accepted Authority-B implementation,
existing redacted provider evidence, and this decision.

**Checks:** full repository tests, Golden v1/v2 evidence taxonomy, browser E2E for normal
and degraded paths, synthetic-only and secret scans, clean-state demo, AWS claim audit,
and independent milestone verdicts.

**Feedback:** each material milestone permits one focused correction. A second material
failure or a new authority/product direction stops the loop.

**Records:** milestone specs/plans, manifests, screenshots or local artifacts, approval
verdicts, known limitations, and competition claim matrix.

**Stop:** success is an independent `READY_TO_BE_JUDGED`; stop earlier for a new material
fork, login/MFA, budget expansion, public/destructive/legal action, or repeated material
failure.

## Non-goals

No new model-contract patch, provider attempt, AWS deployment, production data, employer
material, commit, push, publication, recorded/uploaded video, or Devpost submission.
