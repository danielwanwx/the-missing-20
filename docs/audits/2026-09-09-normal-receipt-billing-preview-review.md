# Independent pure billing preview review

Verdict: **BLOCKED — P1 corrections required.** Scope is only `normal_receipt_billing_preview.py` and its test file against the normal-billing design and R4 read-only preflight. No product edits, model calls or ERP writes were made. The existing suite passed 28 tests; this does not establish the commercial contract.

Reproduction: run `.venv/bin/python -m pytest tests/test_normal_receipt_billing_preview.py -q`. For the counterexamples below, use `PYTHONPATH=src .venv/bin/python`, load fixtures with `n = runpy.run_path('tests/test_normal_receipt_billing_preview.py')`, obtain fresh `_purchase_receipt()`, `_mapped_invoice()` or `_related()` fixtures, apply each listed mutation independently, then call `n['_valid_preview'](purchase_receipt=pr)`, `mapped_invoice=invoice`, or `related_documents_read=read` as appropriate. These are local fixture checks with no external effects.

| Priority / boundary | Exact independent mutation | Actual outcome / required outcome |
| --- | --- | --- |
| P1 authority | Unmodified fixture | READY has `read_only=True` but `write_allowed=True`; pure preview must not grant write authority without the separate approval/execution boundary |
| P1 receipt source | PR `is_return=1` | READY; require HOLD for returned receipt |
| P1 conversion | PR first item `conversion_factor=99` | READY; require exact source/bill conversion agreement |
| P1 child identity | PR first item `purchase_order='WRONG'` | READY; require exact child PO and PO-row link |
| P1 remaining quantity | Submitted linked invoice `name='PI-PARTIAL'`, `bill_no='OTHER'`, item `qty=0.5` | READY for another full Box; partial bill ambiguity must HOLD |
| P1 existing draft | Linked invoice with different bill number, name PI-OTHER and docstatus0, qty1 | READY; existing linked draft must block duplicate preparation |
| P1 malformed bill | Linked submitted different-reference invoice, item qty None or -1 | Both READY; missing/negative billed quantity must HOLD, not become zero or increase remaining allowance |
| P1 lookup authority | Related read `scope={'company':'WRONG','purchase_receipt':'OTHER'}` | READY; require explicit correct query scope and completeness before absence can be established |
| P1 digest binding | Compare default source_digest with wrong-scope read above, and separately read `observed_at='CHANGED'` | Both unchanged; bind the authoritative lookup envelope, not only documents/revision |
| P1 native mapped fields | Mapper `credit_to='WRONG'`; item `expense_account='WRONG', stock_qty=999` | READY; account identities and stock quantity must match frozen native/source contract |
| P1 unknown flags | Mapper `update_stock=None` | READY; require known zero, not truthiness treating unknown as false |
| P1 malformed handling | Mapper item `qty=float('nan')` | Raises ValueError from digest generation; return a deterministic HOLD without treating malformed evidence as usable |

The private deployed source `/private/tmp/m20-r4-pr7-billing-source.json` independently confirms PR7 has **no header purchase_order**. Its exact item carries purchase_order and purchase_order_item, item M20-DEMO-CARTON, quantity1 Box and conversion1. The implementation incorrectly requires the nonexistent header field while permitting a missing child link. Tests instead supply the invented header relationship and M20-ECU-CTRL. Align fixtures to the actual native child relationship; PO ordered quantity is40, not the test's1. Do not change the pilot bill quantity from1 or the other39 outstanding.

Additional source checks raised by the primary review agree with code inspection: missing source stock UOM is accepted; PO/PR currency, rate and conversion are not validated; missing PR child PO detail is accepted. Mapper net/gross checks alone do not verify the underlying commercial source. Freeze source values and verify accounts, stock quantity, explicit zero tax/discount/rounding/payment flags consistently with the narrow pilot.

The builder does not mutate input documents, and generated previews currently expose only an immutable proxy around scalar source-revision metadata. Those properties are useful but cannot compensate for READY on wrong or incomplete financial evidence. This is not an executor review and does not approve any insert, submit, payment or full closure. Correct the scoped counterexamples, demonstrate their failures before correction and passes after correction, then independently reassess the revised slice. No separate private repro artifact was created; the exact reproducible mutations are recorded above, and the deployed snapshot remains private.

## Corrected candidate re-review

Verdict remains **BLOCKED**. Independently ran the revised suite: **52 passed**. Replayed the original return flag, conversion, child PO, wrong account/stock quantity, unknown update_stock, NaN, wrong scope and existing partial/draft/missing/negative billed quantity counterexamples; all now HOLD with write_allowed false. Missing source stock_uom and purchase_order_item also HOLD. A changed lookup observation time now changes source_digest. The actual private PO40/PR1/native mapper snapshots validate READY without write authority, using an explicit synthetic bill basis and its posting_date matched to the native mapper. No ERP document was changed to invent supplier bill fields: those remain independently supplied synthetic input. This verifies the repaired native shape, not live readiness or completeness of a new lookup.

Three remaining counterexamples prevent approval:

The primary preserved this reviewed candidate locally before the next correction at `/private/tmp/m20-billing-preview-reviewed-v2/`: module SHA256 `906a0d29175b9a6be542bdf7346cfa16f9892e9533fae1451765f8227dbdf2d3`, test SHA256 `2a94b4760e5a161128640405031595214881c247cab749c62a3f1f89bceedffd`. This is an unaccepted candidate archive, not a shipped product revision.

1. **P1 contradictory completeness:** `read=n['_related'](); read['pagination']['complete']=False; read['pagination_complete']=True`; `_valid_preview(related_documents_read=read)` returns READY. Every supplied completeness declaration must agree; one true alias must not override an explicit partial result.
2. **Malformed document status:** `pr=n['_purchase_receipt'](); pr['docstatus']=True`; `_valid_preview(purchase_receipt=pr)` returns READY because Python equality accepts True as1. Require the known numeric status without boolean aliases, consistently for submitted source headers.
3. **P1 known native receipt return ignored:** `ret=n['_purchase_receipt'](); ret.update(name='RETURN-1', is_return=1, return_against=n['_basis']().purchase_receipt); ret['items'][0]['qty']=-1`; `_valid_preview(related_documents_read=n['_related'](ret))` returns READY. Native Purchase Receipt returns use header return_against and child PO links; they do not require PI-style child purchase_receipt/pr_detail. `_linked_rows` silently skips this known return. The original design explicitly requires related receipt returns to block the pilot.

The next adapter gate must also make lookup coverage explicit: COMPLETE must cover receipt-line invoices/drafts/credits and native receipt returns, plus company/supplier bill-reference collisions on other receipts. A merely exact-PR filtered lookup cannot prove no bill-number conflict outside that PR. The current scope values identify the target but do not themselves declare those query coverage guarantees. Do not infer coverage from a documents list or claim the constructed test envelope is a fresh authoritative search.

## Documentation cross-check

The frozen-regression report accurately distinguishes the original failed combined command from completed check components. Private logs confirm233 formatted files, Ruff success, strict mypy51 files,1,613 Python tests in67.86seconds, the missing @zxing/library error, and subsequently101 JS tests with zero failures/skips. No fresh Python environment or real-model acceptance is claimed. Tracker additions retain this scope and keep billing/continuity unaccepted.

The S2 clarification correctly supersedes native-session wording with application dialogue_intent continuity and retains independent D4/D5 gates. The source-digest clarification correctly separates an audit snapshot from an idempotency key and preserves the submit-attempt fence; it approves no executor. The preflight appendix matches private PO/PR shape and the retained discovery summary (one PI, seven PR, no linked results). That summary is explicitly acknowledged not to contain every inspected parent payload, so it supports a preparatory report rather than independently reproducible final external acceptance. These documentation updates do not overclaim product completion; they may proceed separately from the blocked preview implementation.

## Final bounded correction review — superseding verdict

**APPROVED for this pure read-only preview slice.** This supersedes the candidate BLOCKED verdicts above while retaining their failure evidence. It does not approve an adapter's real lookup coverage, a durable billing executor, a manager authorization, or any financial write/full closure.

Frozen SHA256:

- `src/the_missing_20/adapters/normal_receipt_billing_preview.py`: `21ec05497ef76b8f39c9fef5dad023c4265d7df061a727effd9cbfd39a6fc8de`
- `tests/test_normal_receipt_billing_preview.py`: `1f3ce8d4c831caeee765cf9d977dc45ee90f1bfba4656b0823bc39bdc0557560`

Independent `.venv/bin/python -m pytest tests/test_normal_receipt_billing_preview.py -q`: **58 passed**. Independently replayed the retained return/conversion/wrong-child/wrong-account/stock-quantity/unknown-flag/NaN/wrong-scope/malformed-status and existing partial/draft/unknown/negative quantity cases: all HOLD without write authority. Replayed contradictory pagination in both directions and a present unknown alias: all HOLD. The known native PR return now HOLDs using its native header reference and PO child shape. Removing each required coverage declaration independently also HOLDs.

Code inspection confirms source docstatus uses finite numeric validation excluding booleans, every supplied pagination declaration must agree with explicit complete pagination, and native receipt returns are examined before PI-style child matching. The lookup contract now requires explicit complete coverage for `receipt_line_invoices`, `receipt_returns`, and `bill_reference_collisions`. Those are caller attestations that a future adapter must prove; this pure function does not perform searches or manufacture source completeness.

The unchanged private PO40/PR1/native mapper documents again produced READY with `write_allowed=False` using the explicit synthetic basis and matching native posting date. No missing supplier-bill field was inserted into ERP evidence. The supplied related envelope in this check was a declared test input, not a new live search. Source/bill digest separation and the previously verified nonmutation boundary remain intact. No product files were edited or external/model operations performed during this review.
