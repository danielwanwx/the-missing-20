# Offline native billing request — independent review

Initial verdict: **BLOCKED by one P1 source/preview binding gap**. Scope is only the shared validator extension, pure native insert request binder, and its tests; no journal, coordinator, UI or ERP effects were reviewed here.

Frozen SHA-256 values:

- preview: `9d3ab2e063e33f2bb22117017f58f5881313542761e528c8eb54476377704054`
- native request: `b2a5860f9e6cd652a4e52b8bed7b3b0ea3d6b529887f7cf746987ef18f382084`
- native request tests: `7c370d9832ccba819a440cdd2d0123fe5e1656aa1e450feec6a748961648427d`

Independent `PYTHONPATH=src:. .venv/bin/python -m pytest -q tests/test_normal_receipt_billing_native_request.py tests/test_normal_receipt_billing_preview.py tests/test_normal_receipt_billing_source.py`: **165 passed**. The prior 58 preview tests remain unchanged and passing. Shared MAPPED validation preserves existing mapper behavior; new DRAFT/SUBMITTED paths require exact identity/status and bound bill fields. The binder rejects failed raw bill values before cloning, adds only disclosed bill fields, freezes nested JSON, rejects non-finite JSON/invalid keys and allowlists the insert method/path. No transport or journal is called.

## P1: READY for one source tuple can bind a different raw body

The binder checks preview status/bill_digest, then validates supplied commercial values, but never compares preview.source_digest with the supplied PO/PR/mapper/related source. It does not accept related lookup evidence, so it cannot establish that the READY result admitted this source tuple. This is an accidental stale-input/cross-snapshot correctness problem within trusted code, not a claim that arbitrary in-process callers are hostile or that the pure helper has already written an invoice.

Exact offline repro:

```sh
PYTHONPATH=src:. .venv/bin/python - <<'PYCODE'
import runpy
n = runpy.run_path('tests/test_normal_receipt_billing_native_request.py')
mapper = n['_mapped_invoice']()
old_preview = n['_preview'](mapper)
po = n['_purchase_order']()
po['modified'] = 'SOURCE-CHANGED'
mapper['remarks'] = 'DIFFERENT-RAW-MAPPER'
request = n['bind_native_insert_request'](
    n['_basis'](), purchase_order=po,
    purchase_receipt=n['_purchase_receipt'](),
    mapper_document=mapper, preview=old_preview,
)
print(old_preview.status, request.body['remarks'])
PYCODE
```

Observed: `READY DIFFERENT-RAW-MAPPER`. Neither changed raw input was admitted by old_preview. A changed related-document state cannot be checked at this API at all. This falls short of the approved “READY raw mapper before exact immutable binding” contract.

Smallest correction: pass complete related_documents_read with the same supplied source tuple and reuse validate_billing_preview to establish current READY and exact source_digest equality to the supplied preview; alternatively accept one complete source-read object and bind its validated tuple cohesively. Do not duplicate commercial rules or invent a new authorization store. Add stale mapper, PO/PR revision and related-read mismatch tests, including current incomplete/known collision evidence, plus an unchanged complete tuple success. The helper remains a pure binding step; journal version/token and later fresh-before-I/O checks are still required in their own slices.

No product code changed and no model/ERP/external calls were made. Do not proceed to journal binding on this candidate until the focused correction is independently reviewed.


## Corrected candidate — independent APPROVED offline slice

Supersedes the source-binding P1 above, preserving its failed evidence. Final SHA-256: preview `9d3ab2e063e33f2bb22117017f58f5881313542761e528c8eb54476377704054`; request `3f170301f373789f127848a9690c3e934103bb44a63ae0886d4b77800f7fc144`; tests `cdab35d2ecb21779ff942f3734b31e9e8888b99241cf22321e050c9734a5e10a`. Independently verified actual file hashes and ran the same three test files: **170 passed** (12 binding, 58 unchanged preview, 100 source).

The binder now requires the complete related-read envelope, calls the accepted full preview over the exact supplied PO/PR/mapper/related tuple, requires both detached/current READY/read-only/no-write previews, and compares source_digest, bill_digest and exact_ids before cloning. This closes accidental detached-preview reuse without duplicating commercial rules or introducing a new authority store.

Independent direct adversarial calls separately mutated PO.modified, PR.modified, mapper.remarks and related.source_revision after obtaining a READY preview; all four now reject with a source-digest mismatch. Current INCOMPLETE related lookup and a current existing same-bill invoice also reject because the recomputed preview is not READY. No request is returned for any of these cases.

Additionally used the complete saved actual R4 source preflight artifact `/private/tmp/m20-r4-billing-source-live-preflight-01.json` entirely offline. Reconstructed its disclosed synthetic basis and recomputed the full preview from all raw documents/envelope, then bound the request: READY, bill_no SUP-BILL-R4-0001, bill_date2026-09-09, one native invoice item, update_stock0. Deep comparison confirmed the source tuple unchanged. No transport was called, and no supplier bill fields were invented in the original native mapper.

**No remaining P0/P1 found in this frozen pure substage.** Shared validation and immutable native insert binding are accepted for subsequent journal integration design/implementation within the already approved offline boundary. This request value is not approval, durable attempt proof, provider truth or permission to send itself. The pending journal must bind it to intent/version/token and persist exact request bytes before I/O; coordinator, HTTP/UI and external effects remain unaccepted.
