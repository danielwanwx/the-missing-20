# Distributor receiving, quality and customer fulfillment

Status: research/design independently reviewed GO on `a1948b6`; implementation
and external acceptance are separate, not implied by this document. Luna reviewed
this design and the acceptance contract; the primary agent reviewed the companion
industry evidence report. Primary sources accessed
September 10, 2026. The user's scope is an observable competition-demo business
loop, including complex exceptions, with existing demo-system write authority.

## Native workflow selected

Use the installed ERPNext through its existing transport and native document
mappers. Do not migrate the application to a second ERP or add a generic agent
workflow framework. ERPNext already supplies the business documents; Strands
native history is already integrated for evidence-based conversation.

| Business stage | Native capability and evidence boundary |
| --- | --- |
| Expected vs actual arrival | A Purchase Receipt references the PO and its child row. Received, accepted and rejected quantities are distinct; rejected inventory has a separate warehouse. A PO remaining quantity is not a loss finding. [PR documentation](https://docs.frappe.io/erpnext/purchase-receipt) |
| Cartons vs parts | Maintain parts in a stock UOM such as Nos, with an explicit purchase-pack conversion. Packaging counts do not override observed part counts. [Purchasing UOM](https://docs.frappe.io/erpnext/purchasing-in-different-unit) |
| Inspection | Record incoming/outgoing Quality Inspection parameters and readings. Native numeric/formula checks support acceptance criteria. A visual suspicion, a sample measurement, and a whole-lot release are different evidence. [QI documentation](https://docs.frappe.io/erpnext/quality-inspection) |
| Traceability | Use a properly configured batched item for batch inventory. Preserve batch links into stock/delivery records rather than claiming traceability from free text alone. [Batch documentation](https://docs.frappe.io/erpnext/batch) |
| Allocation | Sales Orders represent customer demand. Native Stock Reservation supports SO/Pick List allocation; automatic purchase reservation specifically depends on SO → Material Request → PO links and the relevant settings. Do not claim the old standalone PO has that link. [Reservation](https://docs.frappe.io/erpnext/stock-reservation) |
| Picking | The native Pick List proposes inventory locations; picking completion requires actual picked quantities/scans. Creating the list does not prove picking occurred. [Pick List](https://docs.frappe.io/erpnext/pick-list) |
| Dispatch | Native SO/Pick List mapping creates Delivery Notes, including partial deliveries. Submitted DN stock movements prove system dispatch accounting, not customer receipt. [Delivery Note](https://docs.frappe.io/erpnext/delivery-note) |
| Transport and receipt | Shipment tracks the DN, parcels and carrier information. Its creation alone proves neither pickup nor delivery. The current repository has no carrier credentials; test carrier/POD inputs must be explicitly synthetic. [Shipment](https://docs.frappe.io/erpnext/shipment), [v15 schema](https://github.com/frappe/erpnext/blob/version-15/erpnext/stock/doctype/shipment/shipment.json) |

Cross-check: Microsoft's warehouse quality workflow generates inspection/movement
work from receiving events and routes stock after inspection results; inventory
can be blocked during quality review. This supports automating system processing
without pretending software replaces physical measurement.
[Microsoft quality processes](https://learn.microsoft.com/en-us/dynamics365/supply-chain/inventory/quality-management-for-warehouses-processes),
[quality orders](https://learn.microsoft.com/en-us/dynamics365/supply-chain/inventory/quality-orders).

ERPNext source is GPL-3.0; this design consumes the existing ERP service's native
API rather than copying its implementation into this repository. Local adapter
code remains independently authored. [ERPNext license](https://github.com/frappe/erpnext/blob/version-15/license.txt).

## Current implementation constraints

Code inspection found native SO → DN/Sales Invoice mapping and readback in
`adapters/demo_executor.py`; its historical quality-release wrapper also unblocks
an invoice and transfers rejected stock, so that wrapper is unsuitable for normal
R4 fulfillment. Its authenticated transport/mapping pattern can be reused.

R4's retained manifest describes only one arrival and is immutable. Its submitted
PO16/PR7/PI8 item is `M20-DEMO-CARTON`, stock UOM Box, conversion one. Preserve
those facts. A follow-on operation can receive the remaining 39 Box against PO16,
but cannot relabel those historical Box as counted internal parts. Add a correctly
configured parts/lot demo case for the inner-shortage and quality sequence.

No Pick List, Stock Reservation, carrier or proof-of-delivery implementation is
currently present in this repository. Existing photo vision explicitly avoids
inferring internal quality. These are implementation gaps, not hidden SDK flags.

Live read-only preflight confirms ERPNext 16.34.2 / Frappe 16.33.1, PO16 received
1 of 40 Box and a shared Stores bin containing 6 Box. That shared balance is not
R4 provenance. The follow-on 39 Box must use a new scoped warehouse, with customer
orders totaling 39; the old PR7 unit remains explicitly outside that new outbound
allocation. Forbidden DocType-meta/child-table reads are access gaps, not proof
that the parent transaction APIs do not work. The earlier v15 source review is
reference only; implementation must check the installed v16 schema/source.

The parent-API preflight initially found Batch and Shipment denied. The native
permission screen identifies Item Manager for Batch and Stock Manager for
Shipment. Those two roles were added to the existing demo agent under the user's
existing demo-permissions authorization; both API reads now succeed. No global
quality setting was relaxed. Stock Reservation remains disabled, so this slice
must label customer assignment as planned allocation unless a later native
reservation is actually verified. The tenant's rejected or unsubmitted quality
inspection action remains `Stop`.

## Frozen demonstration scenarios

Direct distributor support cases corroborate the wrong-inner-part branch. In
[DigiKey's March 2021 thread](https://forum.digikey.com/t/wrong-component-sent-in-an-order/12692),
a customer reports a bag labeled for a 16-pin part containing a different 20-pin
part. Support identifies a nearby shelf item and the customer later reports a
replacement in transit. This is a firsthand customer report with support replies,
not independent proof of the root cause or a defect rate. In a
[February 2022 thread](https://forum.digikey.com/t/wrongly-labelled-parts/20367),
a customer reports the same label/content mismatch again after reordering;
support requests readable package and product markings and the relevant order
evidence. Our design inference: do not blindly reorder after a mismatch; retain
the actual inner marking and inspect the replacement against that discrepancy.
DigiKey's [order-issue workflow](https://forum.digikey.com/t/how-do-i-handle-return-or-order-issues-with-digikey/13991)
explicitly separates wrong quantity/product, damage/defect and late arrival.
These three pages were opened on September 10, 2026.

All new physical/inspection/carrier inputs are explicitly synthetic; native ERP
effects are real writes to the existing authorized demo tenant.

1. **R4 follow-on:** receive 20 and then 19 Box against the remaining PO16 line,
   into a dedicated location. Customer orders request 24 and 15 Box. Automatic
   allocation and pick preparation follow usable arrivals; matching picked and
   carrier events drive dispatch and delivery tracking. PR7's original 1 Box
   remains intact. The PO then shows 40 received, while this outbound case covers
   precisely the new 39 Box.
2. **Component shortage and inspection:** a separate batch-enabled Nos item has
   demand for 40 parts, packaged as four cartons of ten. All four cartons arrive,
   but observed lots contain 20 and 18 parts. The first lot conforms; a measured
   sample of the second is 10.40 mm against the synthetic 9.90–10.10 mm criterion.
   Hold the second lot's 18 parts pending disposition; do not call all 18 defective.
   Show two missing parts and customer-order impact (demand 25 + 15). A supported
   full-lot reinspection/rework result can release the 18; a later two-part
   replacement fills the shortage. Allocation resumes from new evidence.
3. **Boundary observations:** wrong SKU, unrecognized lot, missing inner count,
   conflicting event ID and delivery without matching shipment/POD evidence
   produce specific alerts or input rejection. They create no unsupported stock
   or delivery claim. These are targeted examples, not a production accuracy rate.

## Automation contract

Goal: one input event causes all currently justified software steps, manager
alerts and current-source explanations without repetitive manager approval.
The standing demo policy fixes case, item/UOM, accepted/rejected locations,
customer priority/partial-delivery rules and allowed action types.

Inputs are identified scan/count, packing-list, inspection, picked-quantity and
carrier/POD events. Each retains source, time, document/lot identity and whether
it is simulated. Missing future physical events are awaited automatically; they
must not be manufactured from an earlier photo or an optimistic status.

The system automatically compares facts, separates usable/held stock, identifies
affected customer orders, records exceptions and advances eligible native ERP
documents. A manager alert states the lot, observed defect/shortage, affected
quantity/orders, evidence, action already taken and what evidence is still due.
Possible causes remain hypotheses until packing, transport or inspection evidence
establishes the cause. A shortage does not establish theft or supplier fault.

Automatic release requires the configured evidence; a sample failure may hold a
lot, but it does not measure every unit as defective. Missing/failed quality cannot
be converted into a pass by an LLM. The software can resume after a new supported
inspection result without another manager clicking through the same paperwork.

No real carrier booking, payment, external customer communication or public
publishing is introduced by this slice. Existing private demo records stay private.

## Acceptance and stop rules

- Preserve the old R4 evidence; validate same PO/child links for follow-on receipts.
- Compare separate carton, observed-parts, accepted, held, missing, allocated,
  dispatched and delivery-confirmed quantities; conserve quantities across events.
- Use only usable stock for customer fulfillment; show backorders and impacted
  customers after a quality hold or shortage.
- Demonstrate normal remaining arrival, complete cartons with missing parts,
  inspection failure/lot hold, correction/replacement and resumed fulfillment.
  Additional wrong-item/unknown-lot and unsupported-delivery inputs must not
  silently become normal stock or a customer receipt.
- Verify focused rule/integration checks, the actual interface, exact native ERP
  records and a small set of real model multi-turn questions. Scripted physical
  or carrier evidence is never called a real shipment or sensor demonstration.
- One independent review per complete slice, then commit, push and remote SHA
  verification. No full reliability matrix or production platform rewrite.
- If a native API rejects the researched approach, preserve the failed payload
  privately, inspect the installed schema/source and choose the smallest supported
  route. Do not add layers of case-specific exceptions or hide the failure.

Industry-specific source cases and the synthetic scenario rationale are retained
separately in `2026-09-10-distributor-receiving-exception-evidence.md`.
