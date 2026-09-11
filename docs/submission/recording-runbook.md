# Fresh distributor recording runbook

**Status: BUSINESS REPAIRED CONTINUATION PASS — integrated recording and submission
NOT READY.** No final recording has been completed or accepted. This is a 4:30
English voiceover and screen-action template for the fresh `RECORDING-20260910`
namespace. The current PO19 rehearsal has physical events 1–19 APPLIED plus one
separate durable allocation retry. Native readback reports 40 received, 0 held,
0 missing, 0 usable, 0 allocated, 40 dispatched, and 40 explicitly synthetic
delivery confirmations, with A25 and B15 dispatched and no operational alerts
open. The retry applied a draft pick quantity of 15; event 17
(`29095525-169d-4098-aef0-ea6cd6cd22c9`) applied native pick quantity 15, Delivery
Note 17, and shipment quantity 15; event 18
(`6dded1b1-abbf-4089-9516-64f3eba6ed3d`) pickup and event 19
(`2262fb5f-16ae-4413-8e14-bbd3a3e217eb`) delivery are APPLIED. Final same-case
handoffs are VERIFIED in Airtable `recWHcDEadZrLyRBI`, Jira `QRC4`, and Slack
timestamp `1789088499.513429` at 18:01 PDT. All counts and confirmations are
synthetic demo records and do not establish physical delivery, invoice, payment,
or revenue.

The earlier event-12 checkpoint remains historical: 40 received, held 0, usable 2,
dispatched 38, and 20 synthetic confirmations, with A25/B13 dispatched while
inspection and release were APPLIED and B2 allocation remained PENDING with no B2
pick. The reviewed runtime was restarted on the same case after event 16 (session
`70363`), so the current result is a repaired continuation rather than a clean
uninterrupted take.
See the [live rehearsal audit](../audits/2026-09-10-recording-rehearsal.md) for the
authoritative current state. Fill actual case, document, and external-record IDs
into the final script only after integrated readback and dialogue review.

## The story to tell

The warehouse manager has a customer promise to protect, but the answer is split
across cartons, quality records, ERP documents, customer orders, and collaboration
systems. The manager needs to know what can ship now, which customer is affected,
and what evidence is still missing without guessing a shortage cause or creating a
duplicate stock effect.

The Agent reads the current ERP, inspection, contract, and linked external evidence;
compares the available plans; and explains what the evidence supports. Deterministic
application code owns quantities, permissions, execution, and readback. The recording
must show that distinction through the visible plan, records, and final source state.

Open with one concise disclosure and do not repeat it in every narration step:

> “This is a demo: carton counts, inspection measurements, and delivery confirmations
> are simulated inputs. The ERP and linked Airtable, Jira, and Slack records are real
> records in an isolated demo tenant. We do not claim physical customer receipt,
> supplier responsibility, payment, or revenue uplift.”

## Case selection and preflight

Use exactly one case in one recording. The current PO19 rehearsal is the only target;
its repaired continuation has a final business readback, but it is not a clean take
or integrated recording acceptance. Its private mapping is:

| Field | Prepared value (verification only) | Recording rule |
| --- | --- | --- |
| Instance | `RECORDING-20260910` | Do not describe preparation as acceptance. |
| Case | `M20-DIST-COMPONENT-RECORDING-20260910` | Copy into the script only after the fresh case is accepted. |
| Purchase order | `PUR-ORD-2026-00019` | Show only after an actual current-source readback. |
| Customer A | `SAL-ORD-2026-00013`, 25 Nos, USD150 | Show only after the order is read back in the accepted rehearsal. |
| Customer B | `SAL-ORD-2026-00014`, 15 Nos, USD90 | Show only after the order is read back in the accepted rehearsal. |
| Purchase-order amount | 40 Nos at USD4, USD160 | Treat as source-backed order value, never revenue. |

Before recording:

1. Start the approved private runtime and open `/operations`. Confirm the runtime
   uses `RECORDING-20260910`; do not combine it with PO18 or any historical runtime.
2. Read the operations endpoint once. Confirm the current case, PO, customer orders,
   unit, and current state. The [live rehearsal audit](../audits/2026-09-10-recording-rehearsal.md)
   records the repaired continuation and remaining recording/dialogue gates; do not
   call it a clean accepted recording result.
3. Confirm the page exposes the current source links, event controls, contract terms,
   finance fields, and same-case handoff panel. A missing or unavailable source must
   stay visibly missing or unavailable.
4. Confirm there is no payment or invoice-creation action. Confirm model metadata
   says `Nova Pro`; do not promote a different model in this recording.
5. Start capture and a timer. Record the case ID, code/runtime revision, browser URL,
   and initial source readback in private notes. Keep credentials, raw sessions, and
   the runtime database out of the video.
6. After the fresh rehearsal is independently accepted, replace the prepared-value
   table above with the exact accepted IDs in the private recording notes. Until then,
   captions and narration must use “the prepared fresh case,” never “completed PO19.”

## Timed narration and visible actions

The target is **4:30**, leaving a 30-second buffer under the five-minute limit. The
voiceover below is intentionally short; use the preflight and stop rules for detailed
evidence limits rather than repeating disclaimers during every step.

| Time | Visible action and narration |
| --- | --- |
| 0:00–0:25 | **Open the problem.** Show the accepted fresh case summary after the rehearsal gate passes. Say: “A warehouse manager has one customer promise and several systems to reconcile. I need to know what arrived, what is safe to ship, and which customer should be served first.” Read the single disclosure above. |
| 0:25–0:55 | **Read the arrival.** Show the receipt and lot rows: four cartons, LOT-A 20 Nos and LOT-B 18 Nos, 38 of 40 recorded. Say: “The Agent connects the current receipt and order, while the application keeps recorded quantity separate from the two still due.” Point to the PO and source link. |
| 0:55–1:20 | **Show quality as a gate.** Open the inspection alert and its evidence. Say: “The lot is held until its quality evidence qualifies release. A sample failure narrows what can ship; it does not prove every held part is defective.” Show scope, measurement, and coverage. |
| 1:20–1:55 | **Ask for the first contract decision.** In the same native case conversation, ask: “Which customer receives the first feasible dispatch, and why?” Show the date-first contract rows and returned plan. Say: “The earlier promise selects A20 and B0. Priority breaks a tie; it does not replace the promised date. This is a selected plan, not proof that ERP has executed it.” |
| 1:55–2:25 | **Add current evidence.** Show the supported whole-lot reinspection for LOT-B, then ask: “What changes after this evidence?” Show the updated plan A5/B13 and its partial/final-remainder terms. Keep the explanation tied to the recorded inspection, not to an invented supplier cause. |
| 2:25–2:45 | **Show the replacement.** Show LOT-C as the separate two-part replacement and its inspection evidence. Say: “The replacement supplies B’s permitted final remainder, B2. That records a business effect; it does not explain who caused the original shortfall.” |
| 2:45–3:15 | **Show native fulfillment.** After the rehearsal gate passes, open the current ERP receipt, picks, Delivery Notes, and Shipments. Narrate the exact accepted readback for A25/B15; do not use the PO18 fallback outcome for PO19 or infer completion from a green connection badge. |
| 3:15–3:40 | **Show the linked work.** Open the same-case Airtable, Jira, and Slack/Celigo records. Say: “The handoffs retain linked status and evidence for this case. They add operating context; they do not establish supplier responsibility.” Show record IDs and retained verification timestamps. |
| 3:40–4:00 | **Show simple finance.** Open the commercial panel. Say: “The purchase order is USD160; customer orders are USD150 and USD90. Invoice groups are missing, so the screen does not turn missing into zero or unpaid. No payment action exists, and order value is not revenue.” |
| 4:00–4:20 | **Ask the physical-proof question.** Ask: “Does a synthetic delivery confirmation prove the customer physically received the parts?” Show the current Nova Pro answer or explicit unavailable state. A successful answer must say no and identify the missing physical evidence. Mention the delivery boundary once here, where it matters. |
| 4:20–4:30 | **Close the case.** Return to the current source summary. Say: “The workflow makes the customer promise, evidence, allocation, and ERP effects reviewable. The fresh rehearsal is accepted only if every displayed ID and quantity matches its readback.” Stop capture after the final source refresh. |

## Fresh-rehearsal acceptance gate

Do not fill the prepared IDs into public copy or call PO19 complete until the
rehearsal records all required events and passes independent checks. The current
business rehearsal is a repaired continuation: physical events 1–19 and one
separate allocation retry are APPLIED; the final native readback is 40 received,
0 held, 0 missing, 0 usable, 0 allocated, 40 dispatched, and 40 synthetic delivery
confirmations, with A25/B15 dispatched and no open alerts. Final same-case handoffs
are VERIFIED. The required evidence still includes the 38/40 arrival, quality hold
and supported release, A20/B0 selection, A5/B13 reinspection result, LOT-C B2
replacement, A25/B15 dispatch, linked same-case handoffs, and source-backed
finance. The reviewed runtime restarted after event 16, so the business result is
not a clean uninterrupted recording acceptance. The fresh audit remains the
authority for accepted case IDs and status.

The dialogue gate is also open: native candidates n2, n3, and n4 each failed their
first-question semantic review. Required source reads and SDK hooks were proved, but
answer accuracy was not accepted. The single exact Sonnet 5 diagnostic attempt
returned `AccessDeniedException`; it reported zero input/output tokens, no inference,
and no semantic result. Read-only catalog and foundation-model availability metadata
appeared active and authorized, with entitlement and region available, but agreement
was `NOT_AVAILABLE`; that metadata conflict does not establish invocation entitlement
or a definitive denial reason. No fallback or promotion followed.

The earlier event-12 raw-validation and model-rationale failures remain preserved
history. The separate retry and subsequent native fulfillment events resolve the
earlier B2-pending state in the business readback, but the runtime restart after
event 16 makes this a repaired continuation. There is no clean uninterrupted
recording pass, and the failed n2/n3/n4 dialogue gate remains open.

For a completed PO18 recording, use the exact PO18 case only and narrate A20 as the
historical allocation question. Do not present PO18's A20 as a current zero-plan
state, and do not mix PO18 IDs with the `RECORDING-20260910` IDs in one video. The
retained PO18 evidence is documented in the [final component-loop audit](../audits/2026-09-10-final-component-loop-acceptance.md),
the [R4 billing/native audit](../audits/2026-09-10-r4-billing-native-dialogue-review.md),
and the [finalization ledger](finalization-tracker.md).

## Stop, preserve, and report

Stop the recording if the case is not the selected namespace, a prepared value is
presented as an accepted result, quantities or units change without an event, a held
lot becomes dispatchable without qualifying evidence, the Agent invents a cause,
date-first allocation is wrong, a source is shown as zero instead of missing or
unavailable, a link opens another case, a duplicate POST or unexpected write occurs,
or any invoice, payment, physical-receipt, supplier-blame, or revenue claim appears.

At the stop point, save the timestamp, case ID, endpoint response, source/document
IDs, exact question and answer, and failure category in the private acceptance
directory. Preserve the raw response and screenshot, mark the video **incomplete**,
and do not repair the runtime or replay an event while recording. A repaired
continuation is a new attempt and must be labelled as such.

After a clean fresh rehearsal, compare the private notes with the [recording
rehearsal audit](../audits/2026-09-10-recording-rehearsal.md), [recording dialogue
contract](../audits/2026-09-10-recording-dialogue-acceptance-contract.md), and
[fresh rehearsal preparation](../audits/2026-09-10-recording-rehearsal.md). Only
after that review should the public video URL be added to the Devpost draft or
submitted to the competition.
