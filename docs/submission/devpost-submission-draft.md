# Devpost Submission Copy — LogisticPilot — The Missing 20

> **September 11 status: PO20 same-case fulfillment is complete.** Final video
> production and Devpost upload are in progress; this local draft is not yet the saved
> Devpost description. See the [current finalization ledger](finalization-tracker.md).


**Submission:** `1162519`
**State:** DRAFT; final video production and Devpost upload are in progress. This
file is local and unsynced; final preview and submission have not yet been completed.
**Track:** Professional Agents

This is a local draft for review. It has not been copied into Devpost and must not be
described as submitted or publicly live until the final preview gate passes.

## Core fields

| Field | Final copy |
| --- | --- |
| Project title | **LogisticPilot — The Missing 20** |
| Tagline | **Find the gap. Prove the cause. Close the loop.** |
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

The primary demonstration follows isolated case
`M20-DIST-COMPONENT-V2-20260910` on purchase order `PUR-ORD-2026-00020` through
receiving, inspection, contract allocation, fulfillment, and same-case application
readbacks. ERPNext, Airtable, Celigo, Jira, and Slack each expose a different fragment;
no single source contains a safe answer.

1. LOT-A20 records 20 parts. LOT-B18 records 18 of 20, creating a two-part shortage and
   a sample quality failure; neither entry independently proves a carton’s contents.
2. A whole-lot retest resolves the LOT-B18 hold. LOT-C2 records the two-part replacement.
3. The agent’s real English Dashboard conversation uses Strands with direct Amazon
   Bedrock Claude Opus 4.6. Deterministic code validates the customer-contract plan
   and executes only a manager-approved operation.
4. Native shipments 16–19 dispatch 20, 5, 13, and 2 parts to fulfill A25 and B15.
   Same-case Airtable, Jira, and Slack-via-Celigo readbacks are verified.
5. The final projection records 40 ordered, 40 received, and 40 dispatched. Delivery
   confirmations are synthetic demo inputs, not independent physical-receipt proof.
6. Finance stays source-backed: the PO is USD160; customer orders are USD150 and
   USD90; no invoice, payment, or revenue-recognition claim is made.

## Retained historical evidence

The separately accepted September 7 case records a 12/8 accepted-versus-held split
and a USD42,000 order-to-billing effect. Its [historical audit](../../artifacts/audits/2026-09-07-current-hero-proof.json)
and [claim matrix](evidence-matrix.md) remain available as named evidence; they are
historical evidence only; they do not change PO20 delivery, invoice, payment, or
revenue claims.

## How we built it

### Strands investigation layer

The agent layer uses the Strands Agents SDK with direct Amazon Bedrock Claude Opus
4.6 for the recorded English Dashboard conversation. It includes a bounded
orchestrator, scoped source tools, structured/typed advisory output, competing
hypotheses, synthesis and evaluator feedback, evidence handoffs, and SDK lifecycle
hooks that drive the visible Investigation flight recorder. The same case scope powers
a multi-turn evidence conversation.

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

The current recording architecture follows synthetic demo inputs—operator, scanner,
inspection, and carrier—through the Operations UI, the Python operation coordinator,
the Strands contract selector, the deterministic evidence gate, and validated ERPNext
actions. The recorded English Dashboard conversation uses Strands with direct Amazon
Bedrock Claude Opus 4.6. The coordinator sends direct
case updates to Airtable and Jira; Celigo carries the single-attempt Slack import.
Native conversation reads fresh ERP facts and retained handoff journal evidence through
an SDK session and remains read-only. AgentCore is historical evidence only.

Read the diagram from left to right:

- The Operations UI accepts the synthetic case input and optional English voice
  transcript.
- The Python operation coordinator sends versioned contract options to the read-only
  Strands selector, which uses Claude Opus 4.6 through direct AWS Bedrock transport.
- The deterministic evidence gate checks authorization, quantity, and quality before
  the application performs validated ERPNext actions and native readback.
- The coordinator sends direct same-case updates to Airtable and Jira; a single-attempt
  Celigo import carries the Slack notification.
- The native conversation session reads fresh ERP facts and retained handoff journal
  evidence through the SDK and returns read-only answers. The current 40-part case is allocated A25/B15, with
  delivery confirmations explicitly labelled synthetic.

Canonical static diagram:
`docs/architecture/distributor-operations-recording.visual-check.1440x900.light.png`

Interactive diagram:
`docs/architecture/distributor-operations-recording.html`

Specification:
`docs/architecture/distributor-operations-recording.json`

Historical diagram:
`docs/architecture/the-missing-20-live-architecture.english.jpg`

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

- PO20 fulfillment of 40 received and dispatched parts across four native shipments,
  with A25/B15 allocation and same-case cross-app readbacks.
- Synthetic delivery confirmations clearly separated from independent physical-receipt
  proof, and finance claims limited to the USD160 PO and USD150/USD90 customer orders.
- Six real Strands source/reconciliation tools, typed output, evaluator feedback, and
  22 visible SDK lifecycle events in the retained historical hero run.
- A case-scoped, English human/Agent conversation through Strands and direct Bedrock
  that cannot mutate business state.
- Retained bounded results from eight real-provider scenario variants and fifteen
  multi-turn cases, including approve, reject, deny, and insufficient-evidence
  behavior.
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
- Amazon Bedrock Claude Opus 4.6
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
