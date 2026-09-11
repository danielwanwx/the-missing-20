# PO19 distributor recording runbook

**Status: READY TO RECORD V1 as a bounded completed-case walkthrough.** Public
video, judge access, upload, and submission are still incomplete. This is a 4:30
English voiceover and screen-action template for the existing recorded
`RECORDING-20260910` case. It walks through completed PO19 evidence and shows one
clearly labelled previously captured real English Bedrock answer from the PO18
diagnostic reports; it creates no new inventory events, live inference, or
full-case replay.

The current PO19 state has physical events 1–19 APPLIED plus one separate durable
allocation retry. Native readback reports 40 received, 0 held, 0 missing, 0 usable,
0 allocated, 40 dispatched, and 40 explicitly synthetic delivery confirmations,
with A25 and B15 dispatched and no operational alerts open. The final B2 remainder
is 2 parts: event 17 (`29095525-169d-4098-aef0-ea6cd6cd22c9`) applied Pick List
`STO-PICK-2026-00015`, Delivery Note `MAT-DN-2026-00017`, and shipment
`SHIPMENT-00015`; event 18 (`6dded1b1-abbf-4089-9516-64f3eba6ed3d`) pickup and
event 19 (`2262fb5f-16ae-4413-8e14-bbd3a3e217eb`) delivery are APPLIED. Final
same-case handoffs are VERIFIED in Airtable `recWHcDEadZrLyRBI`, Jira `QRC-4`, and
Slack timestamp `1789088499.513429` at 18:01 PDT. All counts and confirmations
are synthetic demo records and do not establish physical delivery, invoice,
payment, or revenue.

The earlier event-12 checkpoint remains historical: 40 received, held 0, usable 2,
dispatched 38, and 20 synthetic confirmations, with A25/B13 dispatched while
inspection and release were APPLIED and B2 allocation remained PENDING with no B2
pick. The reviewed runtime was restarted on the same case after event 16 (session
`70363`), so the current result is a repaired continuation rather than a clean
uninterrupted take.
See the [live rehearsal audit](../audits/2026-09-10-recording-rehearsal.md) for the
authoritative current state. Verify every ID and quantity against the current page
before capture; the business records are already applied and must not be replayed.

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

Use exactly one existing case in one recording. The recorded PO19 business state is
the only v1 target; its repaired continuation has a final business readback, but it
is not a clean uninterrupted take. Its mapping is:

| Field | Recorded value (verification only) | Recording rule |
| --- | --- | --- |
| Instance | `RECORDING-20260910` | Confirm the namespace on the current page; do not combine it with PO18. |
| Case | `M20-DIST-COMPONENT-RECORDING-20260910` | Show only after the current source readback matches. |
| Purchase order | `PUR-ORD-2026-00019` | Show with the current source link. |
| Customer A | `SAL-ORD-2026-00013`, 25 Nos, USD150 | Show with the current order readback. |
| Customer B | `SAL-ORD-2026-00014`, 15 Nos, USD90 | Show with the current order readback. |
| Purchase-order amount | 40 Nos at USD4, USD160 | Treat as source-backed order value, never revenue. |

Before recording:

1. Start the approved private runtime and open `/operations`. Confirm the runtime
   uses `RECORDING-20260910`; do not combine it with PO18 or any historical runtime.
2. Read the operations endpoint once. Confirm the current case, PO, customer orders,
   unit, final quantities, and applied state. The [live rehearsal audit](../audits/2026-09-10-recording-rehearsal.md)
   records the repaired continuation; do not call it a clean uninterrupted take.
3. Confirm the page exposes the current source links, contract terms, finance fields,
   and same-case handoff panel. Do not click event controls or replay an applied
   event. A missing or unavailable source must stay visibly missing or unavailable.
4. Confirm there is no payment or invoice-creation action. Confirm model metadata
   says `us.anthropic.claude-opus-4-6-v1` for new operations answers. Launch the
   operations server with `MISSING20_DISTRIBUTOR_MODEL=opus46`; historical Nova
   allocation records retain their original model attribution. See the
   [model-upgrade audit](../audits/2026-09-10-opus-model-upgrade.md) for the
   remaining language and conversation acceptance limits. This metadata check does
   not authorize a new inference call.
5. Select one previously captured real English Bedrock answer from the PO18 Opus
   Q1–Q4 diagnostic reports and label it visibly as “PO18 diagnostic answer —
   captured, not a live PO19 query.” A live agent question is optional and requires
   separate authorization and budget; it is not a v1 gate.
6. Start capture and a timer. Record the case ID, code/runtime revision, browser URL,
   current source readback, and captured-answer report in private notes. Keep
   credentials, raw sessions, and the runtime database out of the video.

## Timed narration and visible actions

The target is **4:30**, leaving a 30-second buffer under the five-minute limit. The
voiceover below is intentionally short; use the preflight and stop rules for detailed
evidence limits rather than repeating disclaimers during every step.

| Time | Visible action and narration |
| --- | --- |
| 0:00–0:25 | **Open the problem.** Show the recorded PO19 case summary. Say: “A warehouse manager has one customer promise and several systems to reconcile. I need to know what arrived, what was released, and what the records support.” Read the single disclosure above. |
| 0:25–0:55 | **Read the completed arrival history.** Show the recorded lot rows and event history: four initial cartons, LOT-A 20 Nos and LOT-B 18 Nos, followed by the separate LOT-C replacement of 2 Nos. Say: “The application keeps the recorded receipt sequence and replacement evidence visible instead of collapsing it into one unexplained total.” |
| 0:55–1:25 | **Show quality evidence.** Open the recorded LOT-B sample failure and whole-lot reinspection/release. Say: “The sample failure held the lot; the later supported whole-lot result released it. These are synthetic inspection inputs and do not prove every part was physically tested.” |
| 1:25–1:55 | **Show the contract decision.** Display the date-first terms and the recorded A25/B15 allocations. Say: “The earlier promise drives the sequence, while priority breaks a tie. The visible plan is separate from the application readback that followed.” Do not ask an additional model question here. |
| 1:55–2:30 | **Show completed ERP effects.** Open the current receipt, pick lists, Delivery Notes, and Shipments. Point to A25 and B15 and the final B2 remainder of 2 parts. Show Pick List `STO-PICK-2026-00015`, Delivery Note `MAT-DN-2026-00017`, and Shipment `SHIPMENT-00015`; do not click event controls or replay an event. |
| 2:30–3:00 | **Show direct linked records.** Open the same-case Airtable record `recWHcDEadZrLyRBI`, Jira issue `QRC-4`, and Slack/Celigo timestamp `1789088499.513429`. Say: “These links retain operating evidence for the same case. They add context; they do not establish physical delivery or supplier responsibility.” Do not ask the model to enumerate Slack milestones. |
| 3:00–3:25 | **Show simple finance.** Open the commercial panel. Say: “The purchase order is USD160; customer orders are USD150 and USD90. Invoice groups and payment records are missing, so order value is not revenue.” |
| 3:25–4:05 | **Show one captured English answer.** Show a previously captured real English Bedrock answer from the PO18 Opus Q1–Q4 diagnostic reports that says recorded synthetic delivery confirmations do not prove physical customer receipt. Label the frame “PO18 diagnostic answer — captured, not a live PO19 query.” Do not request new inference. |
| 4:05–4:30 | **Close the case.** Return to the current source summary. Say: “The workflow makes the customer promise, evidence, allocation, and ERP effects reviewable. This walkthrough shows recorded demo evidence; it does not claim physical delivery, invoice, payment, or revenue.” Stop capture without creating a new event. |

## V1 recording gate

The business evidence is already recorded: physical events 1–19 and one separate
allocation retry are APPLIED. The final native readback is 40 received, 0 held, 0
missing, 0 usable, 0 allocated, 40 dispatched, and 40 explicitly synthetic delivery
confirmations, with A25/B15 dispatched and no open alerts. Final same-case handoffs
are VERIFIED. The reviewed runtime restarted after event 16, so the business
history is a repaired continuation. V1 does not require another inventory event,
event replay, or full clean-case rehearsal.

The recording includes one clearly labelled captured PO18 English Bedrock answer
about synthetic delivery evidence and physical receipt. Opus 4.6 passed Q1–Q4
semantic review. Q5 reached the 3,072-token capacity fix but retains known
external-record timeline and count errors; keep it out of the hero path and show the direct linked
records instead. Do not request new inference for v1. A live agent question is
optional and requires separate authorization and budget. The Chinese adversarial Q7
is out of scope for this English-only v1 and is retained only as historical
language-following failure evidence. Do not claim a full seven-question continuous
pass.

The latest live-query attempt was rejected before model invocation because its
3,072-token reservation exceeded the remaining runtime cap; it incurred no model
charge and does not block the recorded v1 scope.

The earlier event-12 raw-validation and model-rationale failures remain preserved
history. The separate retry and subsequent native fulfillment events resolve the
earlier B2-pending state in the business readback, but the runtime restart after
event 16 makes this a repaired continuation. The [live rehearsal audit](../audits/2026-09-10-recording-rehearsal.md)
and [readiness audit](../audits/2026-09-10-recording-readiness-gaps.md) remain the
authorities for current status. Public video, judge access, upload, and submission
are separate unfinished gates.

## Stop, preserve, and report

Stop the recording if the case is not the selected namespace, the current page does
not match the recorded readback, quantities or units change without an event, a held
lot becomes dispatchable without qualifying evidence, the Agent invents a cause,
date-first allocation is wrong, a source is shown as zero instead of missing or
unavailable, a link opens another case, any event control is clicked, a duplicate
POST or unexpected write occurs, or any invoice, payment, physical-receipt,
supplier-blame, or revenue claim appears.

At the stop point, save the timestamp, case ID, endpoint response, source/document
IDs, exact question and answer, and failure category in the private acceptance
directory. Preserve the raw response and screenshot, mark the video **incomplete**,
and do not repair the runtime or replay an event while recording. A repaired
continuation is a new attempt and must be labelled as such.

After the captured English answer is selected and clearly labelled, compare the
private notes with the [recording rehearsal audit](../audits/2026-09-10-recording-rehearsal.md),
[recording dialogue contract](../audits/2026-09-10-recording-dialogue-acceptance-contract.md),
and [readiness audit](../audits/2026-09-10-recording-readiness-gaps.md). Only after
that review should the public video URL be added to the Devpost draft or submitted
to the competition.
