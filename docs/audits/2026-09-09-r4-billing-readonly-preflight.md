# R4 same-order billing: read-only preflight

Status: PREVIEW_VERIFIED, NOT_EXECUTED. No invoice insert, submit, delivery, sales invoice or payment occurred in this check. Original receipt and its lost-ACK evidence remain intact.

A fresh local platform read at 2026-09-09T23:34:33.543491+00:00 reports case M20-GOODS-20260909-40-R4, CURRENT, PO PUR-ORD-2026-00016, receipt MAT-PRE-2026-00007, 1 Box accepted and 39 Box outstanding. Supplier invoice is AWAITING_INVOICE; no customer order/delivery/sales invoice is configured. The physical basis is RECEIPT_CONFIRMED, not an independent observation of carton contents.

The primary agent then directly read the ERP receipt: submitted, company Missing 20 Automotive Demo, supplier M20 Controller Systems Ltd., receipt child 068bbdr0mb linked to PO child 458j82kp8e, item M20-DEMO-CARTON, 1 Box, stock UOM Box, conversion1, rate/net/gross USD50, warehouse Stores - M20. Private complete document snapshot is retained locally, not published as a credential-bearing runtime dump.

The deployed make_purchase_invoice endpoint was called only to map a proposed document, with filtered_children=[068bbdr0mb]. It returned an unnamed, uninserted Purchase Invoice: docstatus0, update_stock0, exact PR/PO child links, qty1 Box, net/gross USD50, no taxes or discount, Creditors - M20 payable and Stock Received But Not Billed - M20 expense/clearing account. This confirms endpoint compatibility and a concrete proposal; it does not authorize or prove an invoice effect. Preparation must refresh these inputs before any approved write.

Primary references checked September9: [ERPNext Purchase Invoice](https://docs.frappe.io/erpnext/purchase-invoice) explains Update Stock and upstream document billing; [maintainer version-15 mapper](https://github.com/frappe/erpnext/blob/version-15/erpnext/stock/doctype/purchase_receipt/purchase_receipt.py) supports filtered receipt children, pending quantity calculation and native row references. Deployed preview, rather than assumed branch parity, supports the endpoint compatibility finding.

Remaining: explicitly synthetic supplier bill input, independently reviewed durable insert/submit boundaries and dedicated approval; visible platform integration; PI/GL and unchanged PR/SLE external verification; restart/repeat checks. Customer fulfillment remains a separate unfinished part of the same-order acceptance plan. No payment is planned.

## Additional source-shape checks

The primary subsequently fetched PO16 directly: submitted, USD, exact child 458j82kp8e, item M20-DEMO-CARTON, ordered/stock quantity40 Box, conversion1, rate/net rate50. The receipt links its PO on the child row; PR7 has no header-level `purchase_order`. Tests must preserve this distinction rather than invent a one-Box PO or require a nonexistent receipt header link.

Read-only parent-resource discovery scoped by company and supplier, without a creation-date or document-status exclusion, returned one Purchase Invoice and seven Purchase Receipts, each below the requested first-page limit100. Reading those parent documents found no invoice child linked to PR7 and no receipt return against PR7. This was a preparatory observation, not durable uniqueness or permission to insert. The related-document adapter must refresh complete searches, inspect bill-number conflicts as well as exact receipt-line effects, and preserve unknown status on incomplete reads. Existing least-privilege integration uses parent discovery because direct child-table REST access is denied; no permission was expanded.

Private local aids: `/private/tmp/m20-r4-po16-billing-source.json` and `/private/tmp/m20-r4-billing-related-preflight.json`. The latter retains the scope/counts and matching-document result, not every inspected parent payload; final external acceptance must retain sufficient decisive readback evidence. No invoice mutation occurred.
