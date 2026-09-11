# Contract allocation recovery audit — 2026-09-10

Status: **live allocation recovery, native dispatch, and declared synthetic
delivery continuation PASS; recording and submission remain NOT READY.** This audit records the
current PO19 state and the recovery boundary. It is not a claim of complete
business acceptance, reliable complex dialogue, or recording readiness.

## Preserved pre-recovery state

Before recovery, the fresh PO19 rehearsal had 16 retained physical input events, events 1–16
`APPLIED`. That native readback was **40 Nos received, 0 held, 2 usable,
38 dispatched, and 38 recorded synthetic delivery confirmations**. Customer A
has 25 dispatched and customer B has 13 dispatched. The remaining two usable
Nos are the B2 remainder. Allocation selection is still `PENDING`, the page is
on `HOLD`, and no B2 pick, delivery note, shipment, or confirmation has been
created.

The 38 delivery confirmations are declared synthetic inputs. Native ERP
documents and readbacks are demo-tenant evidence; they do not prove physical
customer delivery. The current state is a continuation of the rehearsal, not a
clean uninterrupted recording take.

Before the recovery call, the first two SQLite snapshots were preserved at the
event-12 pending checkpoint in
`/private/tmp/m20-recording-before-allocation-recovery-20260910/`:
`distributor-operations.sqlite3` and `distributor-handoffs.sqlite3`. The raw
request/response records for events 1–16 remain under
`/private/tmp/m20-recording-business-events/`. These private files are the
preservation boundary and are not public evidence. A second two-database
snapshot was preserved after event 16 and before the reviewed restart at
`/private/tmp/m20-recording-before-restart-event16-20260910/`.

## What the pending decision means

Contract policy v1 compiles quantities from the current ERP facts and the
configured customer terms. The application computes the plan; the model does
not author quantities. At this checkpoint the executable rows are:

| Customer contract | Dispatched | Current remainder | New candidate | Eligibility |
| --- | ---: | ---: | ---: | --- |
| A25 | 25 Nos | 0 Nos | 0 Nos | `NO_DISPATCH_REMAINING` |
| B15 | 13 Nos | 2 Nos | 2 Nos | `FINAL_REMAINDER_ALLOWED` |

The B row has a configured minimum of 5 Nos, but its two Nos complete that
contract's remaining quantity and its terms allow a final remainder. The A row
is not a candidate reference because no dispatch remains. A valid selection
therefore contains the exact current plan ID and B's exact customer-order
reference; it cannot include A merely because A is present in the plan.

This is an **executable contract source eligibility** decision, not a fixed
answer inserted for this case. The native Strands selector receives the
application-calculated plan and may select that supplied plan or defer. It may
return the exact candidate references and a bounded English rationale, but it
cannot change quantities, contract terms, lot capacity, or perform an ERP
write. The deterministic boundary then validates the plan ID and the complete,
unique set of executable references before preparation.

The retained event-12 decision reports a completed-A minimum violation and is
`PENDING`. An exact original reference mismatch is plausible from that
validation context, but the raw original model selection is not retained in
the live record. The mismatch is therefore **not proven** and must not be
reported as the historical model's exact output or as a confirmed root cause.
The bounded retained rationale is evidence of a failed decision, not a
business fact.

## Independent backend review

I reviewed the current Terra backend diff against
`c62c3982833fc43d9f95d93ea1c8add891a8a51f` in the requested allocation,
operations, agent, server, and operations-test files. The scoped verdict is
**GO**:

- Candidate reference validation derives its accepted set from rows with
  `new_quantity > 0`, preserving A0/B2 behavior and final-remainder terms.
- A retry row is committed before selector or native work. Replaying the same
  `retry_id` returns its retained result and does not call native preparation
  again.
- A retry is stored in `allocation_retries`; it does not append a physical
  inspection, arrival, pick, or delivery event. The later picked event remains
  the boundary that submits the prepared pick, delivery note, and shipment.
- The original pending alert resolves only after the configured preparation
  outcomes succeed for the matching pending event. A blocked or unknown native
  outcome leaves the alert open or places the projection on hold.
- The new API accepts only `retry_id` and `pending_event_id`, uses the existing
  loopback/same-origin boundary, and follows the existing handoff-sync path.

The focused offline checks passed: 40 distributor-operations tests, 2
allocation tests, and 6 handoff-server tests (48 total). Terra's independent
UI re-review also passed 36 Node tests after the initial UI review returned
NO-GO; the corrected UI is recorded at the frozen JavaScript digest
`f15c5…225`. Main Ruff/check-format checks passed. `git diff --check` also
passed. These checks use local bridges and do not establish that the current
demo tenant has completed the recovery.

## Retry boundary and residual risk

The recovery endpoint is
`/api/v1/distributor-operations/reselect-pending-allocation`. It re-reads the
current ERP source, recompiles the candidate plan, invokes the native Strands
selector when configured, and may prepare the exact configured B2 native pick
after a valid selection. That action is a durable allocation retry, not a fake
inspection or replacement physical event. It must not be narrated as new
quality evidence or as proof that two parts were physically inspected.

If the selector or native call returns an unknown outcome, the durable retry
remains held and is not automatically invoked again. This protects against
duplicate native writes, while leaving reconciliation as an explicit future
operation. The completed recovery and downstream readbacks are recorded below;
rare unknown-outcome reconciliation remains outside this scoped acceptance.

The initial UI review was **NO-GO** and the scoped correction then received
Terra's independent GO after 36 Node tests. That UI result does not accept the
live recovery or the whole recording. The native conversation gate is also
open: n3 read the required sources but omitted material chronology, and n4
used a source ledger yet still invented or confused packaging facts. Their
hooks/read-coverage evidence does not establish complex-dialogue accuracy. See
the [dialogue acceptance contract](2026-09-10-recording-dialogue-acceptance-contract.md).

The reviewed runtime was restarted on the same case and port 8906 after the
event-16 snapshot: the previous server process (19342) was stopped and reviewed
session 70363 was restored. This makes the current rehearsal an explicit
repaired continuation rather than an uninterrupted first pass. The recovery
request was initiated once and completed, as recorded below.

## Preserved interim checkpoint — before native completion

The UI initiated one recovery request with retry ID
`eb24473d-d726-48fa-ba9d-c9738bbb2282` for pending event
`cf1bd0cd-2b8f-40eb-b565-d232e48d342d`. The Reviewing pending allocation button
was disabled while the request was in flight. The read-only journal checkpoint
is `SELECTED`: the bounded Nova Pro selector returned the supplied plan with a
rationale that B/SO14 is a feasible dispatch candidate, using 1,149 input and
187 output tokens in one request over 2,309 ms. The estimated incremental
inference cost is USD0.0015176; this is an engineering estimate, not an AWS
invoice.

At this interim checkpoint, native B2 preparation was still in flight with
`result_json` NULL. No native operation was yet `APPLIED`; this checkpoint
alone did not prove native completion. The selector result demonstrates only the
bounded contract-selection benefit. It does not repair the failed n3/n4
complex-dialogue trials or establish conversation accuracy.

## Completed live recovery and native dispatch

The one UI recovery action completed `APPLIED`. Nova Pro selected
`cap-53ee6a62b0e5b00dc89c` with exactly `SAL-ORD-2026-00014` as its contract
reference. The native `prepare_pick` result returned draft Pick List
`STO-PICK-2026-00015`. The origin allocation alert resolved, all six case alerts
were resolved, and the physical-event count remained 16. The UI displayed the
verified preparation result separately from dispatch.

The primary then used the actual operation form to submit the declared
synthetic B2 pick, event `29095525-169d-4098-aef0-ea6cd6cd22c9`, for customer
order `SAL-ORD-2026-00014`, `LOT-C`, and 2 Nos. This subsequent physical input
event completed `APPLIED`, with `submit_pick`, `submit_delivery_note`, and
`create_shipment` all `APPLIED`. Native records are Pick List
`STO-PICK-2026-00015`, Delivery Note `MAT-DN-2026-00017`, and Shipment
`SHIPMENT-00015`. Its immediate readback reported 40 received, 40 dispatched,
0 usable, 0 held, 0 missing, and 38 synthetic delivery confirmations.

The same UI form then recorded explicit synthetic pickup event
`6dded1b1-abbf-4089-9516-64f3eba6ed3d` and delivery event
`2262fb5f-16ae-4413-8e14-bbd3a3e217eb`, both for `SHIPMENT-00015`.
Both completed `APPLIED`. Final physical-input count is 19, plus the separate
allocation retry. Final readback is **40 Nos received, 40 dispatched, and
40 declared synthetic delivery confirmations; A25/B15; 0 held, missing,
usable, or awaiting allocation; no active alerts**. All four shipments have
separate pickup and delivery evidence. This is a repaired continuation with
one server restart, not an uninterrupted first pass or proof of physical delivery.

Private preserved results are `17-allocation-recovery.response.json` and
`17-picked-b2.request.json` / `17-picked-b2.response.json` under the event
directory above. The recovery result is an action, not a seventeenth physical
event; the B2 pick is physical input event 17. This proves the scoped recovery
and downstream dispatch, not complex dialogue accuracy or recording readiness.

## Sources

- [Strands Agents hooks](https://strandsagents.com/docs/user-guide/concepts/agents/hooks/), accessed 2026-09-10. The SDK documents typed lifecycle callbacks, including `BeforeToolCallEvent`, for validation, guardrails, and tool interception. Hook coverage is an execution-control capability; it is not a semantic acceptance result.
- [Recording dialogue acceptance contract](2026-09-10-recording-dialogue-acceptance-contract.md), local evidence for the failed n3 and n4 semantic trials and their preserved private reports.
- [Recording readiness gaps](2026-09-10-recording-readiness-gaps.md) and [recording rehearsal](2026-09-10-recording-rehearsal.md), local current-case gate and rehearsal status.
