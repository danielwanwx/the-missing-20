# Fresh 40-part distributor loop — acceptance evidence

Case: `M20-DIST-COMPONENT-FINAL-20260910`, PO18 and customer orders SO11/SO12.
The final fresh HTTP source returned available=true, DELIVERY_CONFIRMED:
40 received, 40 dispatched, 40 declared synthetic delivery confirmations,
zero missing/held, and customer totals A25/B15. These are actual demo-tenant ERP
transactions and recorded synthetic physical inputs, not production operations
or independent proof of real customer receipt.

## Actual business sequence

Nineteen events recorded the original four cartons/38 Nos, A whole-lot inspection,
A20 partial shipment and confirmation, B failed sample and whole-lot reinspection,
A5/B13 dispatch, the 2-Nos replacement and inspection, B2 dispatch, and remaining
transport confirmations. The replacement used a separate fifth outer package;
the original expected carton count remains four. Quality and shortage alerts
were resolved using the matching follow-up evidence; history was preserved.

Native evidence: receipts13–15; quality inspections6–9; picks8–11; delivery
notes10–13; shipments8–11; stock entries7–10. Document identity and stock admission
come from the ERP adapter readback, not from model prose. The failed sample does
not establish that all 18 parts were defective; supplier responsibility remains
unproved.

Independent real-model review accepted three Nova Pro selections: A20/B0,
A5/B13 after the first dispatch, and B2 as the permitted final remainder.
Each used exact SO11/SO12 contract references. Total observed usage was 3,157
input and 854 output tokens over three requests; incremental engineering cost
estimate USD0.0052584. This is not an AWS invoice or a multi-turn-chat acceptance.

Commercial source/UI acceptance: PO line USD160; SO lines USD150/90; purchase
and both sales invoice groups MISSING. No invoice/payment was created and no
order amount was labelled realized revenue.

## Retained failures and limits

The initial Jira evidence link was absent and corrected. A later GET exposed
legacy-priority ERP allocation readback conflicting with the new date-first
contract; the shared compiler fixed that mismatch. Three normal service restarts
loaded these fixes and the finance feature into the same runtime. No native
business event was replayed to repair state and no runtime database was edited.
One incomplete inspection form was rejected before any native write, then submitted
with the missing batch field filled. This is a repaired continuation, not a
frozen uninterrupted first pass.

CI failure34532525611 was a pre-body browser readiness dereference; its focused
reproduction and one-line guard passed, then CI34533153849 succeeded. Finance
release97f4ac1 independently passed CI34534138248. Earlier failures stay retained.

Final raw source: `/private/tmp/m20-final-20260910-final-live-readback-01.json`.
Individual raw and retained snapshots are private under the same prefix. Runtime
DBs, credentials and raw sessions are excluded from Git. Stronger-model identity
confirmation, complex multi-turn checks, a final frozen rehearsal and public
submission materials remain open. No award or submission readiness is claimed.

## Final independent check and replay

Independent Terra review returned scoped GO: 19/19 events and 26/26 native
operations APPLIED; all five quality/shortage alerts resolved with their evidence
references retained. Final provider journal entries were read back at 22:01 UTC
against 40 dispatched/40 recorded confirmations and no open operational alerts:
Airtable `recqUX26BS0RpwGG2`, Jira `QRC-3` Done, and Slack via Celigo
`1789077710.190049`. The Jira closure explicitly does not establish supplier
responsibility or physical delivery. The reviewer checked exact retained provider
payloads/readback evidence; it did not make an additional independent provider call.

Primary replayed the exact final delivery event ID/payload once through the normal
HTTP route. Result remained DELIVERY_CONFIRMED with 40/40/40 and 19 events.
The entire 47-row external handoff journal stayed byte-identical under sorted
serialization (SHA256 `0679a0d0c204e2b042e8e2be3e6fcfbd7d38980c118ebf6edd538b12a67192e4`).
No additional native event or external handoff effect was recorded. Raw replay
proof is `/private/tmp/m20-final-20260910-replay-verification.json`.

Primary also opened the actual Airtable record and Jira page in the browser.
Airtable showed one Distributor Cases record with 40 received/dispatched/recorded
confirmations and linked native documents; Jira showed QRC-3 Done and its explicit
no-responsibility/no-physical-proof statement. The final Slack permalink was also
opened in authenticated Chrome and its exact message timestamp verified. Its
visible text identifies this case and PO18 and labels the evidence synthetic;
it does not display the final quantity40. The generic OPERATIONAL_DISPATCH_RECORDED
label and 'No allocation decision retained' wording remain a notification
presentation limitation. Final quantities are verified in Airtable, Jira and the
backend readbacks, not asserted to be visible in that Slack message.
