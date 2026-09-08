# System Overview

## Problem

An enterprise exception rarely has one obvious cause. In the hero case, one 20-unit
automotive controller shipment is split across operational truth: 12 units are accepted
into Stores and 8 are quality-held, while the downstream USD 42,000 customer order is
still undelivered and unbilled. ERPNext, Airtable, Celigo, Jira, and Slack expose
different fragments. Retrying the wrong thing could duplicate a receipt, release the
wrong lot, or create unsupported delivery and invoice records.

## Product

The Missing 20 is a reusable agentic incident-control platform for connected operations.
It combines a live control tower, a Strands investigation workspace, case-scoped human
conversation, deterministic action eligibility, a Manager decision gate, bounded
bounded execution, authoritative reread, and regression-tested duplicate protection.

The Dashboard answers: What changed? How large is the operational and financial risk?
Which systems disagree? The Investigation workspace answers: What did the agent read?
Which hypotheses did it test? What evidence is missing? Why is a recovery safe or why
must the system stop?

## Connected evidence

| System | Role in the hero case |
| --- | --- |
| ERPNext | Purchase order, stock availability, receipt business key, supplier invoice hold, customer Sales Order, Delivery Note, Sales Invoice, stock ledger, and GL |
| Airtable | Supplier-quality disposition for the exact lot |
| Celigo | Integration attempt and acknowledgment uncertainty |
| Jira | Exception ownership and operating ticket context |
| Slack | Human operating context and incident collaboration |

Adapters are scoped to the demo tenant and expose typed evidence records. Credentials
remain server-side. Source cards show provenance, identifiers, status, and external
links so integrations are inspectable rather than decorative logos.

## Agent loop

The Strands layer follows a hybrid investigation loop:

1. Observe the admitted incident and current case version.
2. Run the six bounded source and reconciliation tools for the admitted case.
3. Retrieve typed, read-only evidence.
4. Reconcile quantities, business keys, timestamps, and source conflicts.
5. Compare competing causes and explicit stop conditions.
6. Evaluate coverage, contradictions, uncertainty, and missing evidence.
7. Produce a structured recommendation with citations and telemetry.
8. After execution, inspect the authoritative reread and explain the verified outcome.

Multi-turn conversation uses the same case/run scope. A follow-up can depend on earlier
turns, but conversation never creates approval or write authority.

## Control loop

Deterministic policy independently reconstructs the relevant facts. It validates the
case version, source identity, evidence tuple, business-key state, quality approval,
recovery scope, and invariants. Only then does a Manager receive an approve/reject
choice for the exact packet.

Approval is bound to the plan digest and idempotency key. Execution is limited to the
isolated external ERPNext demo tenant. A fresh reread—not an optimistic API response—must prove the
postconditions before the case can be marked verified. The verified value chain keeps
booked revenue, billed revenue, estimated gross spread, and counterfactual revenue at
risk separate. Deterministic regression tests cover duplicate-effect protection; the
committed live capture proves one Manager-approved bounded execution bundle producing
the captured record set and does not claim a second same-key replay.

## Reusable platform value

The case is supply-chain specific, but the framework is not. New domains can supply:

- typed source adapters;
- incident admission and invariants;
- read-only agent tools and structured output schemas;
- deterministic eligibility policies;
- bound human-decision packets;
- narrow idempotent executors;
- authoritative verification contracts.

This separation allows the agent layer to scale in breadth without expanding its
operational authority.

## Evidence and limits

The local product path, SSE/SQLite control plane, multi-case tests, and one-Manager
decision boundary are proven in this repository. The competition hero path performs a
case-bound recovery in the dedicated ERPNext demo tenant and proves the
result with fresh provider reads; the tenant records are purpose-built synthetic
business data, not production records. AgentCore Runtime deployment,
invocation, logs, and read-only role chat are proven within redacted evidence.
Production impact, causal revenue lift, AgentCore Gateway/Policy, and stable
production-model accuracy are not claimed.

See the [interactive architecture](../architecture/the-missing-20-live-architecture.html)
and [evidence matrix](evidence-matrix.md).
