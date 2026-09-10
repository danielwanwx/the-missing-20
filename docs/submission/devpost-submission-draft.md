# Devpost Submission Copy — The Missing 20

> **September 9 finalization status: NOT READY.** The 20-unit / USD 42,000
> evidence below belongs to the historical September 7 scenario. The separate
> R4 photo-receiving case (PO16/PR7) proves one Box posted and recovered after a
> lost acknowledgement, with verified Airtable/Slack handoffs. It has no linked
> invoice or customer fulfillment. R3 real multi-turn receiving remains FAILED;
> the September 6 8/8 and 15/15 results do not cover that path.
> See the [current finalization ledger](finalization-tracker.md) and
> [R4 scope audit](../audits/2026-09-09-r4-automatic-receiving-recovery-review.md).


**Submission:** `1162519`
**State:** DRAFT, 3/5 steps done in authenticated Devpost on September 9; video empty; current-path acceptance and copy revision pending
**Track:** Professional Agents

The saved Devpost description has not yet been synchronized with these scope corrections.

## Core fields

| Field | Final copy |
| --- | --- |
| Project title | **The Missing 20 — Agents for Humans** |
| Tagline | **Find the gap. Prove the cause. Close it safely.** |
| Repository | `https://github.com/danielwanwx/the-missing-20` |
| Video | Public YouTube/Vimeo URL, maximum five minutes — pending final production |
| Live demo | Optional; do not add until stable and freely accessible through October 8 |
| AWS Builder ID | Enter directly in Devpost; never store the account email in the repository |

## Inspiration

Supply-chain incidents rarely live in one system. A warehouse sees the physical
shipment, an ERP owns financial and inventory truth, an integration platform records
attempts and acknowledgements, a quality registry owns the lot disposition, and the
actual operating context is scattered across tickets and chat. A person can spend
hours joining those fragments—and a careless retry can duplicate inventory or create
an unsupported invoice.

We built The Missing 20 for the moment when the visible number is only a symptom. The
goal is not to replace the operator with an unconstrained model. It is to let an agent
perform the uncertain evidence work, stop for a human when a consequential decision is
ready, and then prove the business effect against authoritative systems.

## What it does

The hero case follows a 20-unit automotive controller shipment. Twelve units are
accepted into Stores and eight are quality-held, while a downstream USD 42,000
customer order is still undelivered and unbilled. ERPNext, Airtable, Celigo, Jira, and
Slack each expose a different fragment; no single source contains a safe answer.

The Missing 20 runs the incident through one inspectable loop:

1. An external demo-system change advances a semantic source version and the ordered
   event ledger. The Dashboard does not generate decorative traffic.
2. A Strands agent runs six bounded read/reconciliation tools, compares competing
   causes, and streams its evidence, SDK hooks, latency, tokens, and typed result.
3. The operator asks multi-turn questions and opens the exact source records cited by
   the Agent.
4. Deterministic application code reconstructs the business facts and decides whether
   any bounded recovery is admissible.
5. One Manager approves or rejects a packet bound to the current case, evidence tuple,
   plan digest, scope, source versions, and idempotency key.
6. The guarded executor performs only the approved ERPNext demo-tenant write.
7. Fresh ERPNext and Celigo reads verify the outcome. Deterministic regression tests
   separately cover duplicate-effect protection; the live capture proves one
   Manager-approved bounded execution bundle producing the captured record set.

The verified result is concrete: 20/20 units delivered, Sales Order
`SAL-ORD-2026-00006`, Delivery Note `MAT-DN-2026-00001`, Sales Invoice
`ACC-SINV-2026-00006`, USD 42,000 observed billed revenue, balanced Stock/GL entries,
and an independently correlated Celigo receipt.

![The Missing 20 architecture](https://raw.githubusercontent.com/danielwanwx/the-missing-20/main/docs/architecture/the-missing-20-live-architecture.english.jpg)

## How we built it

### Strands investigation layer

The agent layer uses the Strands Agents SDK with Amazon Bedrock Nova Pro. It includes
a bounded orchestrator, scoped source tools, structured/typed advisory output,
competing hypotheses, synthesis and evaluator feedback, evidence handoffs, and SDK
lifecycle hooks that drive the visible Investigation flight recorder. The same case
scope powers a multi-turn evidence conversation.

The historical September 6 real-provider evaluation covers 8/8 ambiguous case variants and 15/15
multi-turn cases (45 dialogue turns), including recovery-ready, reconcile-only, deny,
needs-evidence, Manager approve, and Manager reject paths.

### Deterministic control layer

Model output is treated as untrusted advisory data. Deterministic code independently
owns evidence integrity, state classification, action eligibility, policy, approval
binding, execution, verification, and replay. The model has no tool that can approve,
write, or mark a case verified.

The historical recovery execution path is restricted to exact M20-scoped records in an isolated
ERPNext demo tenant. It requires a current policy-approved packet plus one bound Manager
decision. A successful API response is not enough: authoritative rereads, accounting
invariants, a cross-system receipt, and idempotency checks must pass before closure.

### Live product and runtime

Python and Pydantic implement the domain contracts and adapters. SQLite stores the
durable ordered event ledger. REST plus Server-Sent Events project the same backend
state into the Dashboard and Investigation workspace. The browser exposes source
parameters, record IDs, external links, agent-tool activity, conversation, human
decision, and the final Resolution Packet.

The current local hero UI uses direct Strands Bedrock transport. Amazon Bedrock
AgentCore Runtime is separately proven through a READY direct-code deployment, a real
invocation, runtime logs, read-only role chat, and an authority-boundary refusal. We do
not imply that the local UI currently routes through that Runtime, and we do not claim
AgentCore Gateway or Policy.

## Architecture

The architecture is designed around one non-negotiable boundary: probabilistic
investigation must never silently become operational authority.

Read the diagram from left to right:

- Operations Command Center admits a case and renders ordered backend state.
- Decision Workspace API coordinates source versions, durable case state, and SSE.
- Strands retrieves evidence from ERPNext, Airtable, Celigo, Jira, and Slack and calls
  Nova Pro for evidence-grounded investigation.
- Deterministic Policy validates the facts and creates an eligible bounded plan.
- Manager Gate preserves the consequential human decision.
- Guarded Executor performs the exact idempotent ERPNext demo-tenant execution bundle.
- Independent Verifier rereads authoritative state, checks Celigo and accounting
  evidence, and records a durable Resolution Packet.

Canonical static diagram:
`docs/architecture/the-missing-20-live-architecture.english.jpg`

Interactive diagram:
`docs/architecture/the-missing-20-live-architecture.html`

## Challenges we ran into

### A plausible model answer is not operational proof

Early versions could explain a discrepancy but did not adequately separate a model
recommendation from a safe business action. We introduced a typed advisory contract,
independent deterministic policy, a case-bound Manager decision, and an executor that
cannot accept arbitrary model-generated operations.

### Multiple systems can be individually correct and collectively misleading

Quantity alone was too shallow. We had to reconcile business keys, supplier lot,
source revision, physical scans, integration acknowledgement, quality disposition,
customer fulfillment, Stock Ledger, and GL. The Agent now compares alternative causes
and states exactly which evidence would make it stop.

### “Live” can still look mocked

Auto-incrementing counters made an earlier dashboard feel animated rather than real.
We replaced them with semantic source versioning: unchanged external reads create no
event and no visual movement; an actual source or workflow transition produces one
ordered event that every view consumes.

### Completion must survive refresh and restart

A convincing demo cannot lose its Agent run, approval, conversation, or Resolution
Packet when the browser or server restarts. The event ledger and persisted verified
run restore the same authoritative state instead of reconstructing a cosmetic success.

## Accomplishments that we are proud of

- A real Manager-gated write to an external ERPNext demo tenant, followed by fresh
  document, Stock Ledger, and GL reads.
- A historical order-to-billing outcome (no cash collection proof) with exact Sales Order, Delivery Note, Sales
  Invoice, Celigo receipt, and observed USD 42,000 billing evidence.
- Six real Strands source/reconciliation tools, typed output, evaluator feedback, and
  22 visible SDK lifecycle events in the verified hero run.
- Multi-turn, evidence-cited human/Agent conversation that cannot mutate business
  state.
- Eight real-provider scenario variants and fifteen multi-turn cases, including
  approve, reject, deny, and insufficient-evidence behavior.
- Fail-closed degraded and invalid states plus regression-tested idempotency.
- A responsive product UI and an independently validated interactive architecture.

These are bounded demo-environment results. We do not claim production accuracy,
production customer impact, or causal incremental revenue.

## What we learned

The strongest role for an enterprise agent is not “make every decision.” It is to make
expensive evidence work fast, visible, and reviewable. LLMs are valuable where the path
is uncertain: choosing tools, comparing hypotheses, finding contradictions, and
explaining what remains unknown. Deterministic systems are essential where truth and
authority matter: eligibility, accounting invariants, approval scope, effects, and
verification.

We also learned that human-in-the-loop should not mean stopping after every step. The
Agent investigates autonomously and asks for a person only at the consequential
boundary. “Know when to stop” is both a product behavior and a safety property.

## What's next

- Add production authentication and independently verified Manager identities.
- Replace bounded polling with signed provider webhooks where available.
- Add more ERP and integration connectors behind the same typed evidence contracts.
- Run longitudinal production-style evaluations for accuracy, latency, cost, and
  operator time saved.
- Measure business impact with a controlled baseline before making causal ROI claims.
- Route the product UI through AgentCore Runtime only after that hosted path passes the
  same evidence and authority tests.

## Built with

- Strands Agents SDK
- Amazon Bedrock Nova Pro
- Amazon Bedrock AgentCore Runtime
- ERPNext / Frappe Cloud
- Airtable, Celigo, Jira, and Slack
- Python 3.12, Pydantic, SQLite, and Server-Sent Events
- Vanilla JavaScript/CSS and Phosphor Icons

## Evidence and limitations

The complete claim-to-proof mapping is in the public
[release evidence matrix](https://github.com/danielwanwx/the-missing-20/blob/main/docs/submission/evidence-matrix.md). Purpose-built synthetic
business records are used across the demo services; credentials are excluded from the
repository. Production accuracy, AgentCore Gateway/Policy, production data, and causal
revenue uplift are explicitly not claimed.
