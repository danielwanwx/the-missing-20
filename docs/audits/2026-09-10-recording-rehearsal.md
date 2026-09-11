# Recording rehearsal — PO19 business case

Status: BUSINESS REPAIRED CONTINUATION PASS; READY TO RECORD V1 as a bounded
completed-case walkthrough. Public video, judge access, upload, and submission are
still incomplete.

The user requested that the next version be ready to record. Existing PO18 and
its failure/success evidence remain unchanged. The v1 scope is a recorded
completed-case walkthrough plus one clearly labelled previously captured real
English Bedrock answer from the PO18 diagnostic reports, kept separate from the
PO19 state. No new inventory events, live inference, or full clean-case rehearsal
is required.

Provisioned on September 10 using the existing component-quality provisioner:
- Instance: `RECORDING-20260910`.
- Case: `M20-DIST-COMPONENT-RECORDING-20260910`.
- Purchase Order: `PUR-ORD-2026-00019`.
- Customer A: `SAL-ORD-2026-00013`, 25 Nos, USD150, earlier promise.
- Customer B: `SAL-ORD-2026-00014`, 15 Nos, USD90, higher tie-break priority.
- PO amount: 40 Nos at USD4, USD160.

The provisioner creates/reuses exact demo master records and submits the new
marked PO/SOs with readback. It creates no receipt, invoice, payment, or external
notification. Address/contact masters are shared demo identities; new warehouse,
batch, order and shipment-prefix identities are instance scoped. Private runtime
configuration and raw readbacks remain outside Git.

The code/runtime was frozen before the physical-evidence events. The recorded
case follows the approved component path and retains every actual input, selection,
ERP result and cross-system result, including its failure and repair. Synthetic
counts, inspection measurements and delivery confirmations are labelled as such.
No physical customer delivery, supplier blame or revenue uplift is implied. V1
walks through these existing records and does not create or replay inventory events.

No final video or public submission has been completed; those remain separate
final-preview and access gates.

## Recorded business case and v1 scope

The independent native business path is frozen at commit
`c62c3982833fc43d9f95d93ea1c8add891a8a51f` (remote main verified; actual CI
34543785580 completed successfully). The new private runtime runs on port 8906.
Its initial ERP projection was empty before the rehearsal began; that is no longer
the current state. At this checkpoint, PO19 physical events 1–19 are APPLIED, plus
one separate durable allocation retry is APPLIED. Native readback reports 40 Nos
received, 0 held, 0 missing, 0 usable, 0 allocated, 40 dispatched, and 40
explicitly synthetic delivery confirmations; customer A25 and B15 are dispatched
and no operational alerts remain open. The final B2 remainder is 2 parts. Event 17
(`29095525-169d-4098-aef0-ea6cd6cd22c9`) applied the native pick with Pick List
`STO-PICK-2026-00015`, Delivery Note `MAT-DN-2026-00017`, and shipment
`SHIPMENT-00015`; event 18 (`6dded1b1-abbf-4089-9516-64f3eba6ed3d`) pickup and
event 19 (`2262fb5f-16ae-4413-8e14-bbd3a3e217eb`) delivery are APPLIED. The raw
event-19 response is retained privately at
`/private/tmp/m20-recording-business-events/19-delivery-b2.response.json`.
Final same-case handoffs are VERIFIED in Airtable `recWHcDEadZrLyRBI`, Jira
`QRC-4`, and Slack timestamp `1789088499.513429` at 18:01 PDT. These are
synthetic demo records and do not establish physical delivery, invoice, payment,
or revenue.

The earlier event-12 checkpoint remains preserved history: it reported 40 received,
held 0, usable 2, dispatched 38, and 20 synthetic confirmations, with A25/B13
dispatched while inspection and release were APPLIED and B2 allocation remained
PENDING with no B2 pick. The earlier event-6 Slack readback remains historical
state: received 38, held 18, missing 2, dispatched 20, and confirmed 20 Nos.
The later events and retry supersede those business counts without erasing that
failure checkpoint. The reviewed runtime was restarted on the same case and port
after event 16 (session `70363`), making this an explicit repaired continuation
rather than a clean uninterrupted recording pass. No journal edit or physical
event replay was performed; the retry and later events are recorded actions.

## V1 English dialogue check

The Opus 4.6 comparison passed Q1–Q4 semantic review. Q5 reached the 3,072-token
capacity fix but retains known detail errors in its external-record timeline and
count, so it is excluded from the v1 hero path; show direct linked records instead
of asking the model to enumerate many Slack milestones. V1 can show one clearly
labelled previously captured real English Bedrock answer from the PO18 Q1–Q4
diagnostic reports, such as the answer about synthetic delivery confirmations and
physical customer receipt. Label it as PO18 diagnostic evidence, not a live PO19
query. It is not a live query in the recording. A live agent question is optional
and requires separate authorization and budget. Do not claim a full seven-question
continuous pass. The Chinese adversarial Q7 is out of scope for this English-only v1
and does not block it; preserve that historical language-following failure in the [dialogue
acceptance contract](2026-09-10-recording-dialogue-acceptance-contract.md).

The latest attempted live query was rejected before model invocation because its
3,072-token reservation exceeded the remaining runtime cap; it incurred no model
charge and does not block the recorded v1 scope.

This progresses independently of the failed Nova Pro complex-dialogue candidate,
which remains isolated and unpromoted. The recorded business path and clearly
labelled captured English answer are sufficient for the bounded v1 recording scope;
they do not imply whole-system production reliability. Public video, judge access,
upload, and submission remain separate unfinished gates.
