# Approved competition completion scope — September 10

User aligned each item in conversation. Target: complete and submit by September
12, not wait for the September 14 17:00 PDT official deadline. This is a delivery
target, not a guarantee of an award or a statement of acceptance.

## Frozen scope

1. Versioned structured customer contracts: promised date first, customer priority
   as tie-breaker; explicit partial-shipment and minimum-batch terms. The real
   Strands agent selects a feasible allocation with contract evidence. Arithmetic
   and execution checks stay deterministic. New physical evidence is supplied by
   people/devices or explicitly synthetic demo events, never invented by the agent.
2. Resolve shortage, quality and uncertain-operation alerts from matching verified
   evidence. Preserve history. Fulfillment completion and supplier responsibility
   investigation have separate lifecycles.
3. Native session history plus fresh sources and calculated facts. Demonstrate
   normal/exception conversations covering carton versus parts, customer impact,
   contract choice, new evidence, refusal and synthetic versus physical delivery.
   Correct quantities, authority, execution state and provenance are required;
   minor wording imperfections are acceptable. No new memory framework.
4. Finance is simple source-backed purchasing/order/invoice amounts and payment
   status. Do not expand automated financial reconciliation, sales billing or
   payments. Missing documents stay missing. Order value is not recognized revenue.
5. Show actual delegated steps, human interventions, measured demo duration and
   business outcomes. Savings percentages require a matched measured comparison.
6. One coherent 40-part case: four cartons/38 parts, quality hold, contract-based
   partial shipment, inspection/replacement, fulfillment, exception closure and
   simple finance. ERP, Airtable, Jira and Slack via existing Celigo integration
   must show linked actual demo records and verified writes, not connection badges.
   Update existing case records; notify only meaningful changes. Keep unknown
   responsibility open. User explicitly authorized these scoped demo notifications.

## Delivery order and checks

- September 10–11: contract-aware allocation, exception resolution and linked
  external records. Reuse native ERP and existing SaaS transports/journals.
- September 11: new-case UI walkthrough without developer-side repair, targeted
  real-model conversations, external record readbacks; prepare materials alongside.
- By September 12: current English README/architecture/Devpost text, public video
  at most five minutes and usable judge instructions/access. Final public video,
  hosted exposure and Devpost submission retain the agreed user preview gate.

Each slice: inspect existing behavior → bounded design → Terra High/Luna Max
implementation → focused tests → independent review → real acceptance where
applicable → exact-file commit/push/remote SHA verification. CI green is a code
gate, not model or business acceptance. Preserve all failed attempts and unrelated
local data. Avoid framework migration, production hardening and extra scenarios.

## Starting evidence and open seams

- Main `93cd887`: remote CI succeeded; isolated check passed 1,935 Python and
  114 JavaScript tests. Final synthetic fixture update passed its four HTTP tests.
- Distributor allocation currently sorts configured numeric priority and prepares
  picks automatically; this is not an agent contract decision.
- Existing receiving handoffs have actual Airtable, Jira, Celigo/Slack transports,
  journaled writes and readbacks, but consume photo-receiving capture state. The
  new component operations case is not yet wired to those destinations.
- Historical PO16/PO17 acceptance and failed model responses retain their original
  scope. A new uninterrupted cross-app scenario remains to be accepted.

Status: APPROVED_SCOPE / IMPLEMENTATION_IN_PROGRESS. No new business acceptance
is claimed by this document.
