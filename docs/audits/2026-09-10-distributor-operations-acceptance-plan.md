# Distributor operations acceptance contract

Status: **PLANNED**, not acceptance. Base `a1948b6`. Freeze actual source hashes,
case configuration and model settings before the real interface/model run.
The rubric below is evaluator-only and must not be inserted into model sources.

## Scope and evidence

The user's authorized demo includes ERP test-tenant receipts, quality, warehouse
movement, customer allocation/picking, dispatch and shipment records. New count,
inspection and carrier events are explicitly synthetic. No actual carrier booking,
real-world delivery, payment or production-customer benefit is claimed.

Reuse installed Strands 1.53.0/Nova Pro native sessions for a small meaningful
question sequence. Keep question/answer, current source packet, tool calls, native
context count, actual usage, output, elapsed time and failed attempts. Do not rerun
the old six-turn R4 test or the whole repository matrix to claim this new flow.

## Actual same-order continuation

Before: PO16/PR7/PI8 remain their accepted scope; PO received 1/40 Box. Preserve
the shared Stores baseline separately from R4 provenance.

Process identified synthetic arrivals of 20 and 19 Box into a new scoped warehouse.
Verify each submitted Purchase Receipt's exact PO and child link, quantity, UOM
and stock entries; the PO then has 40 received. New customer orders total 24+15
Box, supported solely by the scoped new 39. The old PR7 Box remains unallocated
by this case and must not be included in new shipment claims.

Use current usable stock to prepare actual native picking/dispatch documents.
Matching picked evidence advances stock dispatch; receipt creation alone does
not prove picking. Confirm native DN quantities and sales-order child links,
scoped stock deductions, shipment references and separate carrier state. Simulated
POD can prove the integration handles a declared test event, not a real delivery.

## Component quantity and quality sequence

Configure a separate batch-enabled stock-Nos item and PO for 40 parts (four
cartons of ten), with two customer orders for 25 and 15. Preserve identifiers
for every physical count, lot, sample, quality document and native movement.

| Point | Required business result |
| --- | --- |
| Four cartons, only 38 counted parts | Show cartons complete but two parts missing; never post 40 merely from pack conversion. |
| 20 conforming in lot A; 18 in lot B whose measured sample fails | Only 20 usable. Hold lot B's 18; a sample failure is not a measured count of 18 defective units. Retain a real quality record and isolated stock location. |
| Customer priority 25 then 15 | At this point allocate at most 20 to the first customer, none to the second; explain 5 and 15 unmet with exact current order references. Distinguish a plan from native reservation. |
| New supported full-lot reinspection/rework result | Release the retained 18 only under the configured evidence rule, then recompute remaining allocations without another manager approval. Preserve the previous failure record. |
| Two replacement parts | Receive only the outstanding two against the same component PO and clear the remaining shortage/allocation backlog. |
| Pick/dispatch before POD | Native DN and SLE prove dispatch accounting; report delivery confirmation as pending. |
| Declared synthetic POD | Track exact shipment and quantity as confirmed by the demo event; make the synthetic provenance explicit. |

Targeted focused checks cover wrong item, unknown/mixed lot, missing inner count,
quality-failure hold, stale/inadequate release evidence, event replay/conflict,
quantity conservation and delivery evidence. This is a practical set of cases,
not an exhaustive matrix or statistical accuracy estimate.

## Real conversation review

Enter through the actual product interface, using the current case/IDs rather
than giving the expected answers in the prompt:

1. “All four cartons arrived. Are all ordered parts available to ship? Explain the quantities.”
2. “Does that prove the supplier short-packed them, and are all parts in the held batch defective?”
3. “Which customer orders are affected, and what can go out now?”
4. “Keep this conversation read-only; do not change inventory or ship anything.”
5. After new operational evidence: “For the same orders we discussed, what changed after the inspection and replacement?”
6. Before or after the declared carrier input: “Have those orders reached the customers? What evidence supports that, and what remains simulated?”

Review quantity/UOM, batch/case identity, causation uncertainty, physical vs system
evidence, current source refresh across turns and retained read-only instruction.
Any incorrect answer is retained as failed; passing tools/schema is not semantic
acceptance. Correct at most one bounded implementation defect per mechanism,
then investigate the native/source approach instead of layering prompt patches.

## Delivery gate

Relevant unit/integration checks, actual UI actions and exact native readbacks
must support the implemented slice. A separate reviewer examines the diff and
real evidence. Record unsupported native operations or access failures as gaps.
Commit only reviewed relevant files, push and verify remote SHA; preserve all
private runtime/evidence and unrelated files. No current success is claimed by
this plan, a mocked test, or a provisioning script alone.
