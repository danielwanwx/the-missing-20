# Simulated Enterprise Case Matrix

## Purpose

Build a competition-only, simulated automotive supplier tenant that behaves
like a real inbound-to-pay workflow. All business identities and records are
fictional, but records are created in the demo ERPNext, Airtable, Celigo,
Jira, and Slack workspaces and re-read from those systems during the demo.

The video will state that the tenant contains simulated enterprise data. It
must not imply that any customer or production workspace is involved.

## Real-world process model

The selected process is the standard incoming-quality path:

```text
Purchase order
  -> supplier ASN / batch identity
  -> ERP receipt into Quality Hold
  -> quality usage decision
  -> integration release event
  -> ERP stock transfer to Stores
  -> PO / receipt / invoice match
  -> invoice eligible for payment
```

ERPNext is authoritative for purchasing, physical stock, the submitted stock
transfer, and invoice hold state. Airtable is a clearly-labelled Supplier
Quality Registry in the demo, authoritative only for supplier quality
metadata. Celigo is authoritative only for a release-event delivery receipt.
Jira and Slack preserve CAPA and alert context; neither proves a release.

Each case is identified by the immutable tuple:

```text
case_id, supplier, item, supplier_lot, PO, Purchase Receipt, Purchase Invoice,
quantity, certificate_id, evidence_revision
```

## Demo tenant data

The tenant represents `Missing 20 Automotive Demo`, an automotive controller
supplier. It contains a supplier, ECU controller item, Stores and Quality Hold
warehouses, linked purchasing documents, quality records, integration run
records, a CAPA, and an incident channel.

Every created or modified record must be labelled `M20 DEMO` and use a stable
case ID. The seeding process is idempotent: it reads by external identity,
creates only an absent record, and reports record IDs. It must never search or
mutate records outside the M20 demo identity set.

## Case matrix

### A. Approved release was not delivered to ERP — primary recording

Baseline: 20 controllers have been received. The registry approves the held
lot for 8 units, but the ERP receipt shows 12 in Stores and 8 in Quality Hold;
the linked invoice is held. Celigo records one `quality.release` attempt
without an ERP acknowledgement.

The Agent must:

1. read PO, receipt, stock, and invoice from ERPNext;
2. validate the registry’s full tuple and quality approval;
3. read the exact Celigo receipt and establish the missing ERP acknowledgement;
4. rule out a previous transfer using the correlation/idempotency key;
5. propose exactly one transfer of 8 from Quality Hold to Stores and unhold
   only the linked invoice;
6. after Manager approval, execute the scoped demo correction;
7. re-read ERPNext’s transfer, stock, and invoice before marking verified.

### B. ERP transfer succeeded but acknowledgement was lost — duplicate guard

The same upstream symptoms exist, but ERPNext already contains the submitted
8-unit transfer bearing the correlation/idempotency key and Stores has 20.
Celigo reports a timeout or unknown acknowledgement.

The Agent must not retry the transfer. It must prove the existing ERP effect,
then only evaluate the linked invoice’s remaining hold. A generic timeout is
never authority for another stock mutation.

### C. Mixed lot / partial quality approval — hard stop

ERPNext shows 12 in Stores and 8 in Quality Hold, but the registry either
approves only 12 or has a certificate lot/revision mismatch for the held 8.

The Agent must preserve stock and invoice hold, produce an evidence request or
CAPA route, and finish `BLOCKED`. No manager approval can override this
evidence failure.

## Write boundary

Provider writes are permitted only in this isolated demo tenant and only after
the Agent has built an immutable proposal. A proposal includes record IDs,
quantity, source and target warehouse, evidence versions, manager approval,
and an idempotency key. It expires if any checked source changes.

The executor can make two ERPNext changes for Case A only:

1. submit one Material Transfer from Quality Hold to Stores;
2. invoke the standard Purchase Invoice unblock action for the linked invoice.

It cannot alter QMS evidence, PO data, the purchase receipt, amount/rate, or
make a supplier payment. Every write is followed by fresh ERP reads. `VERIFIED`
is legal only when the submitted transfer, expected stock balance, and unheld
invoice are all present in those read-backs.

## Dashboard and Agent behavior

The dashboard shows the case tuple, provider receipts, Agent plan, immutable
activity ledger, proposal, Manager approval, execution receipt, and re-read
verification. It distinguishes real demo-tenant provider activity from local
presentation state. Animations derive only from newly admitted ledger events.

The Agent may answer questions from fresh reads. It must name an unavailable,
mismatched, or stale source and remain blocked rather than infer a value.

## Acceptance gates

1. The normal baseline is independently readable in every participating
   system.
2. Each case can be seeded/replayed without duplicate business records.
3. Case A reaches verified only after exact scoped writes and ERP read-back.
4. Case B never creates a second transfer.
5. Case C never creates a stock or invoice mutation.
6. Every provider mutation carries the demo marker, proposal hash, and
   idempotency key in the audit ledger.
7. The video can show normal, incident, diagnosis, approval, execution, and
   verification without claiming production data or hidden provider effects.
