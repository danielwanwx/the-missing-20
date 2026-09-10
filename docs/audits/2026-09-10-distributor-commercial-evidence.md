# Distributor commercial evidence — scoped acceptance

This is the approved simple read-only finance scope. It adds current PO/SO
line quantities, rates, net amounts, currencies and document statuses, plus
exactly linked purchase/sales invoice evidence. It creates no invoice or payment,
does not query Payment Entry, and does not infer revenue or cash from order value.

Invoices are found using bounded child relations and reread against company,
party, order, source-line and item identity. Invoice grand totals and outstanding
amounts are explicitly invoice-level. Empty complete queries yield MISSING;
read/schema failures yield UNAVAILABLE, without blocking physical operations.

Independent Terra reviews accepted backend and UI. Primary verified 52 focused
Python tests and 24 focused JavaScript tests; independent full Node suite passed
125 tests. Changed Python sources passed mypy and Ruff/format; package audit
remained unchanged and passing at its historical scoped acceptance level.

Actual read-only ERP acceptance for PO18/SO11/SO12 returned CURRENT:
- Purchase: 40 Nos at USD4, line net amount USD160, received38.
- A: 25 Nos at USD6, line net amount USD150.
- B: 15 Nos at USD6, line net amount USD90.
- Purchase invoice and both sales invoice groups: MISSING.

No finance writes occurred. Private actual readback is
`/private/tmp/m20-final-20260910-financial-readback-01.json`.

Actual UI acceptance after a normal same-runtime restart displayed CURRENT:
USD160/150/90, exact PO18/SO11/SO12 links, and all three invoice groups MISSING.
The operations page remained ready with 38 dispatched; A's native order status
had progressed to To Bill. No earlier event was replayed. Page rendering clearly
labels sales line amounts as order values, not revenue.
