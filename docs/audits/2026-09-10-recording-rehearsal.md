# Recording rehearsal — fresh distributor case

Status: BUSINESS REPAIRED CONTINUATION PASS; integrated recording and submission NOT READY.

The user requested that the next version be ready to record. Existing PO18 and
its failure/success evidence remain unchanged. A read-only provisioning plan and
independent code/scope review preceded this new isolated demo setup.

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

The code/runtime must be frozen before the first physical-evidence event. The
rehearsal follows the already approved component path and records every actual
input, selection, ERP result and cross-system result, including any failure.
Synthetic counts, inspection measurements and delivery confirmations are labelled
as such. No physical customer delivery, supplier blame or revenue uplift is implied.

No final video or public submission is authorized by this preparation record;
those retain the existing final-preview gate.

## Native business rehearsal started

The independent native business path is frozen at commit
`c62c3982833fc43d9f95d93ea1c8add891a8a51f` (remote main verified; actual CI
34543785580 completed successfully). The new private runtime runs on port 8906.
Its initial ERP projection was empty before the rehearsal began; that is no longer
the current state. At this checkpoint, PO19 physical events 1–19 are APPLIED, plus
one separate durable allocation retry is APPLIED. Native readback reports 40 Nos
received, 0 held, 0 missing, 0 usable, 0 allocated, 40 dispatched, and 40
explicitly synthetic delivery confirmations; customer A25 and B15 are dispatched
and no operational alerts remain open. The retry applied a draft pick quantity of
15. Event 17 (`29095525-169d-4098-aef0-ea6cd6cd22c9`) applied the native pick
quantity 15, Delivery Note 17, and shipment quantity 15; event 18
(`6dded1b1-abbf-4089-9516-64f3eba6ed3d`) pickup and event 19
(`2262fb5f-16ae-4413-8e14-bbd3a3e217eb`) delivery are APPLIED. The raw event-19
response is retained privately at `/private/tmp/m20-recording-business-events/19-delivery-b2.response.json`.
Final same-case handoffs are VERIFIED in Airtable `recWHcDEadZrLyRBI`, Jira
`QRC4`, and Slack timestamp `1789088499.513429` at 18:01 PDT. These are
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

## Dialogue gate remains open

Native dialogue candidates n2, n3, and n4 each failed first-question semantic
acceptance. Required source reads and SDK hooks were proved, but answer accuracy is
not accepted. The exact Sonnet 5 comparison made one diagnostic-only Converse
attempt and returned `AccessDeniedException`; it reported zero input/output tokens,
no inference and no semantic result. The catalog and availability metadata appeared
active/authorized, but the agreement was `NOT_AVAILABLE`, so metadata did not prove
account invocation entitlement. No fallback or promotion followed. The [dialogue
acceptance contract](2026-09-10-recording-dialogue-acceptance-contract.md) remains
the source for that gate.

This progresses independently of the failed complex-dialogue candidate, which
remains isolated and unpromoted. An uninterrupted native business path does not
by itself certify integrated conversation or final video readiness. The final
recording version still requires integrated acceptance after dialogue work;
preparation and independent slices are not treated as whole completion.
