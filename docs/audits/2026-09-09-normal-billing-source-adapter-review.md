# Independent normal-billing source adapter review

Verdict: **BLOCKED by P1 incomplete native evidence promoted to complete coverage.** Reviewed normal_receipt_billing_source.py and its tests against the approved narrow reader design. No ERP/model call or product modification was performed. Independent combined source/preview tests: **71 passed** on the current candidate.

Candidate SHA256: adapter `fa75eee167b736be1ad592f689c7afc4e05928cd360333f472790105a5108d3c`; tests `4f62f443c693b06ff26f0b8898735f7824175157f9763af7dd00f741bf7366f3`.

## P1: missing association fields can produce COMPLETE and READY

Offline reproduction using the test module loaded by runpy under PYTHONPATH=src:

```python
doc = n['_related_invoice']('PI-MALFORMED')
doc['items'] = [{}]
fake = n['_FakeERP'](invoice_pages={0: ['PI-MALFORMED']},
                     invoices={'PI-MALFORMED': doc})
result = n['NormalReceiptBillingSourceReader'](fake).read(n['_basis']())
```

Actual result: related status COMPLETE, all three coverage flags true, preview READY. The listed/fetched PI has valid outer identity/company/supplier/docstatus, but no child receipt/PO association evidence. `_validate_children` only requires mappings. The pure preview then treats missing association keys as nonmatching, silently excluding a potentially linked bill.

A second bounded reproduction leaves normal child fields intact but deletes doc['bill_no'] from a discovered related PI. It likewise returns COMPLETE/READY. This adapter has not established a complete supplier-reference read, so an absent field cannot automatically mean no collision. Verify the deployed native optional-field representation and distinguish explicitly absent/unlinked values from missing evidence. A provider contract that intentionally omits null fields must be demonstrated and modeled explicitly rather than inferred ad hoc.

Minimal correction: validate the native fields needed to classify every discovered related PI/PR before claiming the corresponding coverage. Require enough child identity/link and parent bill/return evidence to decide target association; allow known explicit null/empty optional links under the verified native schema. Missing/malformed evidence must produce incomplete/HOLD, retaining the raw parent and failure manifest. Apply the rule to related documents, not the intentionally unnamed unsaved mapper's synthetic supplier-bill fields. Add these two counterexamples before correction; do not broaden into an executor or repeat all financial calculations in the reader.

## Positive boundaries and limits

The reader uses exact PO/PR resource names, the allowlisted read-only native PR-to-PI mapper, and company/supplier parent discovery for all PI/PR statuses with no date filter. Queries use stable name ordering, offsets, bounded pages/documents and explicit terminal short pages. Duplicate/repeated/out-of-order pages, denied fetches, mismatched parent identity/scope and bounds produce incomplete coverage. Fetches retain the raw related parent before its validation. The own-draft invoice is not filtered, and other-PR bill collisions and native returns are included. Deep copies detach source payloads from transport inputs; preview remains write_allowed false.

Elapsed and response-size guards are explicitly post-read/between-call bounds, not cancellation of an in-flight synchronous transport or a wire-byte cap. The manifest honestly states that distinction. Snapshot hashing preserves exact string keys and includes raw request/response/query evidence. A future phase-aware executor must still separate its own immutable journal-bound draft from unrelated source changes; this reader must continue retaining it unchanged.

No large framework is needed to fix the blocker. Keep one injected transport reader and add only native evidence completeness validation. Independent approval is withheld until a corrected candidate rejects the missing-field reproductions while continuing to accept actual native PO40/PR1/mapper evidence and legitimate explicit-null unrelated links. No live read-only preflight is accepted by this review yet.


## Independent correction re-review — still BLOCKED

Frozen adapter SHA-256 `d6d911a244c73ef51cbeeed825d0e19a76709cb1122169de3d131598805a9dc7`; test SHA-256 `f697f05708bf442082a064f82ea36f8cd7c0aa0a14594ed97a63c12681aead1e`. Independently ran `PYTHONPATH=src:. .venv/bin/python -m pytest -q tests/test_normal_receipt_billing_source.py tests/test_normal_receipt_billing_preview.py`: **73 passed**. Original missing-field examples are now covered by the passing regression tests. Explicit null association/bill fields are intentionally distinguishable from absent unknown fields.

**Remaining P1: field presence without field type still certifies incomplete native evidence.** `_require_declared_field` accepts mapping, list, numeric and boolean association or bill references. The preview resolver returns those raw objects; comparisons simply treat them as unequal. A malformed record is therefore silently classified as unrelated and the adapter declares complete coverage/READY. This is the same completeness boundary as the original blocker, not an expansion of financial scope.

Exact bounded repro command (no network):

```sh
PYTHONPATH=src:. .venv/bin/python - <<'PYCODE'
import runpy
n = runpy.run_path('tests/test_normal_receipt_billing_source.py')
for field in ['bill_no', 'purchase_receipt', 'pr_detail']:
    for value in [{}, [], 7, True]:
        doc = n['_related_invoice']('PI-MALFORMED')
        target = doc if field == 'bill_no' else doc['items'][0]
        target[field] = value
        fake = n['_FakeERP'](
            invoice_pages={0: ['PI-MALFORMED']},
            invoices={'PI-MALFORMED': doc},
        )
        result = n['NormalReceiptBillingSourceReader'](fake).read(n['_basis']())
        print(field, repr(value), result.related_documents_read['status'], result.preview.status)
PYCODE
```

All twelve preview outcomes were READY during independent execution. Required correction: admitted bill/association fields must have a known nullable-string representation; reject unknown types before asserting complete coverage. Validate all supplied aliases so one acceptable alias cannot hide a malformed or contradictory companion. The declared alias groups currently match preview `_value` resolver keys (bill_no/supplier_invoice_no; purchase_order/po_no; po_detail/purchase_order_item; purchase_receipt/receipt; pr_detail/purchase_receipt_item). That parity is positive, but aliases are not independent evidence of the deployed API schema; native saved-parent shape must remain the source of truth. Do not tighten the unsaved mapper into requiring a synthetic supplier bill reference. No product files changed and no live calls were made. Stop for the focused correction/review gate; no source-adapter acceptance yet.


## Native-source-informed amended design gate

**APPROVED TO IMPLEMENT the decision-specific correction below; current implementation remains BLOCKED pending re-review.** Independently inspected `/private/tmp/m20-r4-persisted-pi-native-schema-read.json`. Its existing PI7 has a string bill reference, is_return=0, and child links to other PO11/PR1; native po_detail/pr_detail are absent. This is read-only schema evidence, not creation of a new invoice. Requiring those absent row IDs to exclude an explicitly different PR was unnecessarily strict. Absence must remain absence in retained source; no inferred nulls or synthesized row IDs.

Reviewed Terra's amended contract directly:

- Validate every supplied decisive alias before branching: only null, empty string, or a non-whitespace string; reject mappings, lists, numbers, booleans and whitespace-only strings. Preserve exact bytes. All non-null aliases must agree. Null plus a valid string is consistent with preview `_value`; empty plus a nonempty value conflicts because empty is a non-null resolver value. Validate even aliases on otherwise unrelated rows.
- PI bill-reference group is always declared and validated independently of receipt scope, preserving supplier-wide same-bill detection. Known is_return is required; supplied return_against is validated. Each child must declare the PR-parent group. Explicit null/empty or an exact other PR establishes non-target receipt scope without requiring row IDs. Target PR requires a declared nonempty PR-line identity; unknown line yields incomplete coverage. Target PR plus target line also requires declared PO and PO-line groups; known mismatches remain visible and preview HOLD, while unknown groups make coverage incomplete. Actual native PI7 is therefore admissible without inventing its missing row IDs.
- PR uses native return structure. Known non-return rows do not require irrelevant child identities, but supplied aliases remain checked. A direct return_against target PR is sufficient for conservative HOLD. With unknown/empty header, child-only exclusion requires a nonempty child list and complete nonempty PO/PO-line identities for every child; any target PO/line holds, otherwise explicit nonmatching identities can exclude. Empty children must not produce vacuous complete coverage. A known different return parent is useful exclusion evidence, but a positively target-matching child still holds rather than being discarded.

Required frozen regressions include the original missing/malformed cases; every decisive alias with mapping/list/number/bool/whitespace; conflicting aliases including empty+valid; valid null+string and identical aliases; actual other-PR shape without row IDs; target-PR missing/null/empty line identity; supplier same-bill-other-PR collision; direct target PR-return header without invented child fields; other return header plus positive target child; unknown return header with missing identities and with empty children. Preserve raw retrieved parents before admission and keep the mapper/basis authority boundary unchanged. No broad schema framework or new executor is required. This review authorizes the focused implementation, not READY acceptance, live read preflight, or external effects.


## Final independent re-review — APPROVED for bounded read-only preflight

This verdict supersedes the code blockers above for exactly the corrected source/test files, preserving all failed history. Adapter SHA-256: `d098b11d887986c21f2d6acc74ee13263ac313f5b6ddec8e097fad801e29e4f4`. Tests SHA-256: `1636aa01817c0797495767cca76889dd5c9053fa28391b6eaf525581cd551daf`. Independently checked both hashes after testing. **No remaining P0/P1 found in the reviewed scope.** Approval permits the proposed actual R4 read-only source preflight; it does not approve invoice insertion/submission, executor wiring, or end-to-end billing closure.

Independent command `PYTHONPATH=src:. .venv/bin/python -m pytest -q tests/test_normal_receipt_billing_source.py tests/test_normal_receipt_billing_preview.py` passed **158 tests** (100 source + 58 preview). Independent direct runpy reproductions outside pytest also confirmed:

| Counterexample | Corrected result |
|---|---|
| Original missing bill reference | INCOMPLETE / HOLD |
| Original `items=[{}]` PI | INCOMPLETE / HOLD |
| All twelve earlier bill_no / purchase_receipt / pr_detail mapping, list, integer, boolean variants | INCOMPLETE / HOLD |
| Target PR with missing exact PR-line identity | INCOMPLETE / HOLD |
| Return with unknown header and empty children | INCOMPLETE / HOLD |
| Direct target return header with no child identities | COMPLETE / HOLD |
| Other return header but positively matching target PO/line child | COMPLETE / HOLD |

The implementation validates every present alias before receipt-scope decisions, rejects unknown types and disagreement, and preserves nullable/empty semantics consistent with the preview resolver. It never normalizes an absent field into null. Actual other-PR identity allows missing native row IDs; target-PR identity requires a known target/non-target line. Supplier bill collision coverage remains independent of receipt exclusion. Known returns are retained for preview HOLD rather than filtered out; unknown child-only return scope is incomplete, including empty-list vacuity. Exact PO/PR/mapper validation, all-status bounded parent pagination, raw evidence retention, source digest construction and absence of writer authority remain as reviewed above.

Additionally injected the **actual saved private PO16 (40 Box), PR7 (1 Box), native unnamed mapper, and existing native PI7** into the same reader's fake transport. Inputs came from `/private/tmp/m20-r4-po16-billing-source.json`, `/private/tmp/m20-r4-pr7-billing-source.json`, `/private/tmp/m20-r4-pr7-invoice-mapper-preview.json`, and `/private/tmp/m20-r4-persisted-pi-native-schema-read.json`. Used the explicit synthetic test bill basis, with its disclosed posting_date aligned to the saved mapper; did not fabricate ERP bill fields or child identities. Result: COMPLETE / READY, `write_allowed=False`, no reasons. Deep comparison confirmed all four input documents unchanged. This establishes saved-native-shape compatibility, not current external lookup coverage: the subsequent authorized read-only preflight must establish that with real complete pagination/read evidence.

No model, ERP or other external calls were made by this reviewer, and no product files were edited. The bounded source adapter is ready for its next read-only gate. The financial executor and UI acceptance remain separate work.


## Actual R4 read-only preflight — independent acceptance

**APPROVED for the source-read slice.** Independently inspected `/private/tmp/m20-r4-billing-source-live-preflight-01.json`, SHA-256 `589f6d570898999a5e00411a9565e67b6465fbace0450b9d2a9de5e4fb6ea00c`, permissions 0600, observation `2026-09-10T01:50:47.681208+00:00`. No reviewer external calls were needed. The actual artifact confirms COMPLETE related coverage, READY preview, all three coverage flags true and `write_allowed=False`.

The full manifest contains 13 successful requests and zero failures: 12 GETs and one exact native `purchase_receipt.make_purchase_invoice` mapper POST for PR7/child `068bbdr0mb`. There is no insert, submit, update, delete or payment request. Company/supplier-scoped, all-status discovery returned one PI parent (PI7) and seven PR parents (PR1–PR7), each on a short terminal first page of size 50. Every discovered parent was subsequently fetched; eight full related documents are retained. Independently checked raw manifest response equality against retained PO, PR, mapper and all eight related documents, and checked every related parent company/supplier identity. The existing PI7 belongs to other PO11/PR1 with a different supplier bill reference. All seven observed PRs are non-returns. No candidate matches the explicit R4 synthetic bill or target PR line.

Actual PO16 is 40 Box at USD50; PR7 is a submitted non-return 1 Box on exact PO child `458j82kp8e` and receipt child `068bbdr0mb`. The native mapper is an unnamed, unsaved docstatus0 PI, quantity1 Box, stock conversion1, amount50 USD, posting_date 2026-09-09, update_stock0, exact PO/PR child links, Creditors - M20 and Stock Received But Not Billed - M20. The disclosed bill `SUP-BILL-R4-0001` remains a separate `synthetic_only=true` basis; it was not fabricated into the ERP mapper. The actual mapper date matches the explicit basis without alteration.

Independently recomputed the snapshot digest from basis, raw PO/PR/mapper, related documents and complete manifest: it matches `00e5f4e4aad4042e369e030c3a9a03a26e8c384828ff9eb54ee0dafb7d36676f`. The preview additionally binds its own full source digest and synthetic bill digest, as previously reviewed. This confirms actual native source compatibility and this observed complete lookup, within the configured demo company/supplier and finite read bounds.

No business write was requested by the captured adapter trace; the mapper result is explicitly unsaved. This read-only artifact is not a before/after GL/SLE execution audit and does not prove invoice financial closure. The source adapter's implementation and bounded actual read preflight are accepted; executor, app approval, invoice effects and visible end-to-end acceptance remain separate gates.
