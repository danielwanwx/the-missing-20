# Fresh distributor case acceptance contract

Preparation only; no new ERP records or model comparison are claimed here.

Use a new explicit instance namespace, preserving historical PO17 and its runtime.
Default provisioning remains unchanged. Instance-specific identities include PO
line marker, sales-order markers, warehouses, batches, case ID and shipment
prefixes. Existing item, customers and quality parameter may be reused.
Discover a PO only by its exact instance marker; ignore other instance markers,
and block duplicate or malformed matches. Independent design review: scoped GO.

## Fixed customer terms

| Customer | Quantity | Promise | Priority | Minimum | Partial | Final remainder |
|---|---:|---|---:|---:|---|---|
| A | 25 Nos | September 11, 2026 | 2 | 10 Nos | Allowed | Allowed |
| B | 15 Nos | September 12, 2026 | 1 | 5 Nos | Allowed | Allowed |

Use explicit UTC timestamps in the actual configuration. The earlier promise
outranks customer priority. Native tranches remain A/LOT-A/20,
A/LOT-B/5, B/LOT-B/13 and B/LOT-C/2. Date and quantity expectations below are
acceptance criteria, not additional instructions injected into model inputs.

## One uninterrupted demonstration

1. Record four cartons with an explicitly synthetic internal count of 38 Nos:
   20 in LOT-A, 18 in LOT-B. Carton arrival does not prove all 40 parts arrived.
2. Record inspection evidence. Held quantities cannot be dispatched. A supported
   whole-lot pass releases LOT-A; the agent selects A20/B0 from current contracts.
3. Record LOT-B's quality failure and later supported whole-lot reinspection.
   Release permits A5/B13: A's final remainder exception is explicit.
4. Record the 2-Nos replacement LOT-C against LOT-B shortage, then its inspection.
   B's final remainder exception permits B2. No cause of shortage is invented.
5. Record actual demo ERP picks, dispatch and shipments. Customer totals must
   be A25/B15. Clearly labelled synthetic delivery input may create recorded
   delivery confirmation; it is not independent physical proof of delivery.
6. Open the same-case Airtable record, Jira task and Slack messages. Verify that
   facts and decisions update existing records and that unchanged replay creates
   no extra effect. Close only reconciled operational conditions; retain unknown
   responsibility or unresolved native-operation uncertainty.
7. Show source-backed order and available invoice/payment values. Missing invoice
   remains missing; order value is not revenue. No payment is performed.

Capture each input, current source readback, actual model selection, native
document IDs, destination readbacks and elapsed duration. Retain failures and
developer interventions; a repaired continuation is not an uninterrupted pass.

## Dialogue check

Use native history and freshly read facts for carton/part distinction, customer
impact, contract rationale, changed inspection/replacement evidence, refusal and
synthetic-versus-physical delivery. Evaluate exact numbers and completeness
independently. The proposed stronger-model comparison is capped at USD 5 and
awaits the user's exact model-name clarification; Nova Pro stays the baseline.
No model is promoted solely on schema validity or a single good answer.
