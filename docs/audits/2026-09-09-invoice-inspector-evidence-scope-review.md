# Invoice inspector evidence scope

Status: APPROVED for one display correction; full UI acceptance remains open.

The restored R4 workspace at `http://127.0.0.1:8897` identifies case
`M20-GOODS-20260909-40-R4` and displays1/40 Box received,39 still to receive
and0 invoices. Clicking its Invoice node previously showed both NOT YET
INVOICED and “Balanced posting: Verified”. The latter used
`ledger.assertions.debits_equal_credits`, which the existing ERP source computes
across the selected receipt, invoice and additional vouchers. Aggregate balance
cannot establish that this invoice exists or that its posting was verified.

Luna removed that single invoice-inspector metric from `workspace/app.js`.
Invoice status, value and source link remain available, as do the ERP inspector's
GL row count and debit/credit totals. No replacement verification claim or new
financial logic was introduced.

Independent review verified the exact one-line diff and the backend aggregate
provenance. Worker verification:101 JavaScript tests pass; `node --check` and
whitespace checks pass. Primary reloaded the actual R4 page and clicked Invoice:
the panel shows NOT YET INVOICED, USD0 and source WAITING, with no balanced-posting
verification label. The pre-fix screenshot and before/after DOM observations
are retained in the task's browser tool record. The in-app browser does not
support content export; no exported screenshot file is claimed.

Reviewed app SHA256:
`d99100ab466558727396a495f4f4771257e57d7c435ab735ce8e3b88b8a8f3d4`.

The original R4 runtime was resumed without reseeding, with auto-prepare paused.
Its API confirms the same case and has no normal-billing projection yet. This
check does not establish a real invoice, GL/SLE closure, new model semantics,
all-page/external-system acceptance or a completed cold-start matrix.
