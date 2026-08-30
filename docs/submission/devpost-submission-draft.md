# Devpost Submission Draft — The Missing 20

**State:** `DEVPOST DRAFT CREATED — NOT PUBLIC / NOT SUBMITTED`

Devpost draft: `submission 1162519` under the official Agents for Humans Hackathon.
Project overview is saved; project details remain intentionally incomplete until the
required public demo video is available. Public repository version: commit `a4df5bf`.

This is a field-ready English draft for the Agents for Humans Devpost form. Replace
the marked placeholders only after the repository, video, and testing access have
passed the final release gate. Never paste AWS credentials, account identifiers,
runtime ARNs, or session tokens into Devpost or this repository.

## Submission fields

| Devpost field | Draft value |
| --- | --- |
| Project title | **The Missing 20 — Agents for Humans** |
| Track | **Professional Agents** |
| Short tagline | **Find the gap. Prove the cause. Close it safely.** |
| Repository URL | `https://github.com/danielwanwx/the-missing-20` |
| Demo video | `[PASTE PUBLIC YOUTUBE/VIMEO URL — five minutes or less]` |
| Live demo URL | `[OPTIONAL: PASTE PUBLIC, FREE, JUDGE-ACCESSIBLE URL]` |
| AWS Builder ID | `[ENTER DIRECTLY IN THE AUTHENTICATED DEVPOST FORM; DO NOT STORE HERE]` |

## Project description

Operations teams lose time when a supply-chain handoff does not reconcile. The
warehouse says 100 units shipped; the ERP says 80; the missing 20 may be a retryable
message, a physical short shipment, or a duplicate-posting problem. A plausible answer
is not enough: an unsafe recovery can create a second discrepancy.

The Missing 20 turns that incident into a guided, inspectable workflow. A Strands
orchestrator coordinates three specialized investigators. Each investigator uses
audited read-only tools to inspect the synthetic queue, ERP, shipment, and invoice
evidence, then hands competing hypotheses, citations, uncertainty, and missing
evidence back to the orchestrator. An Incident Copilot lets an operator ask a current-
state question and understand the team's reasoning.

The AI is intentionally advisory. Deterministic application code independently owns
authoritative evidence validation, state classification, action eligibility, policy,
and the write boundary. When a recovery is eligible, two distinct simulated role
principals must approve that exact action. `ControlledExecutor` then applies a bounded,
idempotent synthetic effect, rereads authoritative state, verifies the postcondition,
and proves that replay adds zero effects. Neither the model nor one role can approve
or execute an operational action.

## What the judge can see

1. The Dashboard receives an ordered live API/SSE trace: 100 expected, 80 recorded,
   and the exact 20-unit gap.
2. Agent Workspace shows the Strands orchestrator, three investigator roles, audited
   tool calls, evidence handoffs, hypotheses, and the read-only chat.
3. The operator asks why the gap exists and sees the evidence boundary rather than a
   hidden model claim.
4. Deterministic policy prepares a safe receipt restart, then a separate invoice
   release intent; each requires its own two-role quorum.
5. Controlled recovery closes the gap, verification reaches 100/100, and replay
   produces no duplicate effect.

The five-minute video should follow this order: problem and user, live discrepancy,
parallel investigation, conversational explanation, human decision, controlled
recovery, verification, and the explicit degraded/fail-closed behavior.

## How AWS and Strands are used

**Strands Agents SDK** provides the agent layer: a fixed orchestrator, three
specialized investigators, audited read tools, structured outputs, synthesis/evaluation,
streaming lifecycle events, evidence handoffs, and role-specific conversation. This
is multi-agent investigation and explanation, not a chatbot placed in front of a
database.

**Amazon Bedrock Nova Pro through AgentCore Runtime** is the real advisory integration
boundary. The redacted proof records a READY direct-code Runtime deployment, a real
invocation, runtime logs, a completed read-only role chat, and an authority-boundary
refusal. The deployed path exposes no business-write tool.

The real Nova investigation is reported honestly as `PARTIAL`: three investigators
completed, AI-authored citation coverage was 1/5 admitted records, and deterministic
application validation independently covered 5/5. The product labels stable real-Nova
usefulness `NOT_PROVEN`. AgentCore Gateway and Policy are not claimed. All business
records and scenarios are synthetic, and no production business impact is claimed.

## Built with

- Strands Agents SDK
- Amazon Bedrock Nova Pro
- Amazon Bedrock AgentCore Runtime
- Python 3.12, SQLite, and ordered Server-Sent Events
- Vanilla JavaScript/CSS and Phosphor Icons

## Run and test locally

Requirements: Python 3.12+, Node.js 20+, and `uv`.

```bash
uv venv .venv
make bootstrap PYTHON=.venv/bin/python
make check
make golden
make golden-v2
make workspace-smoke
make judge-demo
```

To open the interactive product:

```bash
PYTHONPATH=src .venv/bin/python scripts/decision_workspace_server.py
```

Open the printed local URL, click **Start Investigation**, and follow Dashboard →
Agent Workspace → Copilot → Prepare → two role approvals → Execute → Verify → Replay.
The default path is local, synthetic, and makes no provider call. `?mode=degraded`
shows advisory-provider failure without weakening deterministic safety; `?mode=invalid`
shows the fail-closed view when authoritative lifecycle evidence is unavailable.

## Evidence and limitations

- Local detection, deterministic policy, per-action quorum, controlled effects,
  authoritative reread, verification, and replay: **PROVEN** with synthetic data.
- Scripted Strands investigation and agent experience: **SCRIPTED_PROVEN** and
  reproducible locally.
- AgentCore Runtime deployment, invocation, observability, and read-only role chat:
  **PROVEN** within the redacted evidence boundary.
- Real Nova advisory usefulness: **PARTIAL**; AI citations 1/5, application validation
  5/5; stable usefulness remains **NOT_PROVEN**.
- AgentCore Gateway/Policy and production impact: **NOT_PROVEN / not claimed**.
- The local role principals are scripted test identities, not independent human
  authentication. No external system is writable from the demo.

Machine-readable proof and the complete claim boundary are in
[`docs/submission/evidence-matrix.md`](evidence-matrix.md) and
[`artifacts/aws/2026-08-30-devpost-real-acceptance.json`](../../artifacts/aws/2026-08-30-devpost-real-acceptance.json).

## Pre-existing work and release notes

The repository provenance ledger records the project foundation and any prior
conceptual influence in [`docs/provenance.md`](../provenance.md). Before submitting,
the entrant must confirm eligibility and disclose any material pre-submission work
required by the official rules. The final public package must include the source,
README, MIT license, architecture diagram, English description, and a public video no
longer than five minutes. The repository already exists publicly; the reviewed local
changes still require a deliberate push. Video upload, live hosting, and Devpost
submission remain separate release actions.

## One-paragraph closing pitch

The Missing 20 uses agents where investigation is uncertain and expensive, and
deterministic controls where operational truth matters. Strands investigators explain
what may have happened; the application validates what is actually admissible; two
roles decide; `ControlledExecutor` performs only the bounded approved effect; and
verification plus replay prove the result. The model can help an operator understand
the incident, but it cannot quietly turn a plausible story into a business write.
