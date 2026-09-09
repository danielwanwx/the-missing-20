# Independent ledger scope review

Date: 2026-09-09. Compared working-tree changes against HEAD `55d7522511f193a880dfa01ae1532f21e2e04fef`.
Scope only: `src/the_missing_20/adapters/investigation_case_sources.py` and `tests/test_investigation_case_sources.py`. Concurrent relationship-view, billing and session changes are excluded.

**Initial verdict: REQUEST CHANGES, one P1. No P0 demonstrated.** Main branch ordering and absent/unknown behavior are correct, but the new scope matcher admits malformed non-string PO/ASN identities as authoritative scope.

## Executed verification

Independently ran `PYTHONPATH=src:. .venv/bin/python -m pytest -q tests/test_investigation_case_sources.py`: 76 passing indicators, exit 0. Also ran direct in-memory counterfactuals through production packet construction, correlation and policy, without a model call or external effects:

| Counterfactual | Observed |
|---|---|
| Completed OPEN invoice, wrong ledger PO | NEEDS_EVIDENCE |
| Fully accounted PAYMENT_HOLD invoice, wrong ledger PO | NEEDS_EVIDENCE |
| Completed OPEN invoice, unrelated historical attempt PO | RECOVERY_COMPLETE |
| Fully accounted PAYMENT_HOLD invoice, unrelated historical attempt PO | RECOVERY_READY |

Asserted input source objects remained equal to deep copies after correlation/policy calls. Code inspection confirms strict pagination boolean, missing/blank identifiers and bool/zero line handling, scoped matching records and issues, and nullable business-key presence. No expected verdict enters source observations; new fields expose identity-match facts, with policy checks remaining application-owned. No writer or model-budget changes are in this diff.

## P1: malformed PO identifiers can satisfy the new authority boundary

`_scope_value_matches` rejects None, booleans and differing types, but accepts equal non-string objects. Line numbers already have a separate positive-integer validator; this helper is used for PO IDs and ASN/shipment IDs, whose source contract expects nonblank strings.

Independent reproducer: start from `investigation_packet()` sources, assign integer `0` consistently to invoice.po, purchase_order.id, ledger_read.po, every current ledger record.po, and the integration attempt.po. Correlation returns `ledger_scope_matches=True`; policy returns **RECOVERY_READY**. Equality of malformed identities is not evidence that an authoritative PO scope was established. Equal lists/dictionaries also pass the helper by inspection.

Minimal required fix: make `_scope_value_matches` require both operands to be nonblank strings and exact equality; continue using `_line_scope_matches` for positive integer lines. Add regressions for non-string PO and ASN values (integer and containers), not just empty strings and bool lines. Do not stringify malformed identities, as that would fabricate valid-looking scope values.

The repro is an invalid-source counterfactual, not evidence of a live ERP mutation or exploited authorization. It is still a blocking contract defect because this slice's purpose is to reject ambiguous/invalid authority before recovery eligibility.

## Boundaries

This report does not certify full source validation, live model semantic reliability or provider writes. The tested wrong-scope branches are safe, and existing tests exercise same-key foreign PO, missing fields and completed/invoice-only ordering. Approval can be issued after the one new counterexample is fixed and independently rerun, with the final candidate's required broader checks supplied separately.

No product edits, commits, model calls or external reads/writes were performed by this reviewer.

## Final re-review after P1 correction

**Final verdict: APPROVE the two-file ledger-scope slice. The initial P1 is closed; no remaining P0/P1 found within this reviewed delta.** This final ruling supersedes the initial request-changes verdict while retaining its counterexample as the audit trail.

Inspected the corrected `_scope_value_matches`: both operands must now be nonblank strings with exact equality. Positive integer line handling remains separate. Independently reran the original malformed-PO experiment for integer 0, empty list and empty dictionary across invoice/PO/ledger/records/attempt. All three now produce `ledger_scope_matches=False`, business-key presence `None`, and `NEEDS_EVIDENCE`.

Independently ran the full target file: **82 passing test indicators, exit 0**, including six added PO/ASN malformed-identifier regressions and the existing completed/invoice-only ordering tests. Changed-file Ruff lint passed; Ruff format check reported two files already formatted. The prior wrong-ledger and wrong-attempt branch findings remain covered and passing.

Approved for isolated staging/commit/push of `investigation_case_sources.py` and its tests with this review record, subject to the parent's required release checks. This approval does not extend to concurrent model relationship views, billing, session persistence, actual provider writes or live Agent semantic acceptance. No reviewer product edits, external actions or commits were performed.
