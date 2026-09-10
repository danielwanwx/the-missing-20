# Normal receiving billing executor — proposed next boundary

Status: design draft; no executor implementation or invoice effect accepted. Dependencies: reviewed source adapter and actual R4 read-only preflight. Scope: disclosed synthetic supplier bill for R4 PO16/PR7, 1 Box at USD50, no stock update and no payment. Existing journal and pure preview stay authoritative boundaries. This is not the legacy QA-release invoice-unblock path.

One operation coordinator should compose the existing configured request callable, a fresh source reader per read, and BillingIntentJournal. Public prepare returns a detached proposal; approval uses the journal's action/case/manager/version token. Execute consumes only a server-bound intent and token, never arbitrary client-supplied ERP documents or endpoints. Model prose cannot authorize writes. HTTP/UI wiring is a subsequent independently reviewed slice; first implement and verify the coordinator with injected transport.

Before first insert, reread the complete source and compare decisive commercial identity, PO/PR revisions and relevant related-document state against the frozen approved intent. Preserve full raw snapshots separately from normalized commercial comparison. If approval is stale/refused/expired or sources are incomplete/conflicting, stop before the journal claim. Mark insert in the journal before the one POST /api/resource/Purchase%20Invoice. Construct the document from the verified native mapper plus disclosed bill reference/date, preserving native PO/PR child links, quantity, UOM, accounts and no-stock-update flags. Freeze the actual outgoing payload or its complete deterministic reconstruction before I/O. Do not call legacy _insert_and_submit, which joins two effects without these fences.

Treat the POST acknowledgment only as a candidate identity. Always read the resulting exact document and use complete company/supplier related discovery to establish uniqueness. If acknowledgment is lost or malformed, discover the frozen supplier bill and target receipt-line identity. Zero hits or incomplete lookup stays unknown with the insert fence closed; multiple or contradictory hits stays conflict. No automatic reinsert. First admitted exact name must match the immutable journal identity and can never be replaced by a different readback.

An exact own draft is an expected state transition, not a new manager approval or permission to ignore unrelated changes. Keep it in raw source evidence. Only after proving its journal-bound name, bill digest, exact native child/commercial values and complete unique lookup may the coordinator classify that own document separately from unrelated source changes for the first submit comparison. All foreign documents, returns, same-bill collisions, changed commercial facts and incomplete reads still block. Reusing the pre-insert source hash by assertion is forbidden. Approval expiry or refusal after insert prevents submit while retaining readback ability.

Mark the first submit attempt durably before the one native submit request. Read back even after a transport timeout. Never repeat submit after its marker; recover by reads of the original exact invoice. Observe and report document acceptance separately from financial-effect verification. Require docstatus1, exact frozen party/bill/PO/PR/native child, quantity1 Box, amount50 USD, update_stock0 and no mixed lines/credits/returns. Verify GL entries by exact invoice voucher, party/account and debit/credit amounts, not balance alone. Verify no invoice SLE and unchanged original PR7 stock entries. If those reads are incomplete or wrong, financial closure remains unverified; do not invent success or reopen write fences.

Required offline counterexamples before implementation: two concurrent execute requests share one durable marker/POST; insert timeout with zero/one/two candidates; submit timeout then submitted readback; restart in both unknown phases; renamed/conflicting draft identity; stale approval/source, refusal between phases; expected own draft vs additional foreign bill/return; malformed/partial exact lookup; wrong native child, amount/UOM/account, mixed line and update_stock; failed GL/SLE verification. Assert exact permitted network effects and no payment endpoints. Tests use injected transport and isolated journals, never existing R4 runtime databases.

A later actual external acceptance uses a reviewed frozen proposal and the already authorized demo invoice scope. Show the concrete synthetic bill and proposal in the product, obtain the application's explicit manager action, then verify the actual same-order invoice/GL/SLE result and restart/reconfirm no duplicates. Do not conflate a CLI coordinator test, a draft invoice or this design with visible end-to-end closure. Customer fulfillment remains a distinct next stage with its own same-order source basis.

## Design-review corrections pending a final implementation gate

The existing journal does not yet freeze the native request body. Extend its prepare/claim boundary minimally: the validated insert document must be bound to the frozen intent before approval, and each claim must atomically persist the exact allowlisted method/path/body before returning it to the transport. A transport sends that saved body unchanged; it cannot remap after the marker. Native submission is POST `/api/method/frappe.client.submit` with `{doc: exact_validated_draft_document}`, not a made-up name-only API. The submit claim must similarly validate and freeze the exact draft body and immutable known name in its transaction. How to share existing native commercial validation without duplicating it remains an explicit design item before implementation.

Define own-effect classification as a pure function over the complete new raw source and the original intent. It may remove exactly one fully proven journal-bound own draft from the *comparison view*, never from raw evidence. Compare the remaining related state to the original baseline. It must run before `refresh_source`, because that API durably records a detected change; do not flag a known expected transition and then clear a sticky hold. PO/PR revisions remain strictly unchanged before first submit in this initial design. If ERP draft insertion changes them, stop and retain the draft plus evidence; do not silently waive revisions or infer which changes are expected. Any relaxation requires a concrete observed transition and independent review. This admits a safe draft-only limitation rather than promising untested automatic submission.

Financial verification uses complete exact-voucher GL reads: for this no-tax USD50 basis, Stock Received But Not Billed debit50 and Creditors credit50; the payable credit must identify the exact supplier, while the debit need not carry supplier-party metadata. Account/company/currency come from the admitted native mapper and basis. Reject unexpected extra, tax, stock, reversed or cancelled rows and unknown lookup coverage. Exact-voucher SLE lookup must be complete and empty for the PI. Compare PR7 stock-entry identities, quantities and values to its captured baseline; a shared warehouse's total balance is not the equality target.

## Implementation contract proposal

This section is a design proposal only. It introduces no executor, transport,
write, or live-call authorization.

### Bound request and journal boundary

Use one immutable `BoundNativeRequest` record with `method`, `path`, `body`,
`body_digest`, `commercial_version`, and `bill_digest`. It canonicalizes and
freezes the complete JSON body. The only allowed records are:

- insert: `POST /api/resource/Purchase%20Invoice` with the full validated
  Purchase Invoice document;
- submit: `POST /api/method/frappe.client.submit` with
  `{ "doc": exact_validated_draft_document }`.

The journal stores the insert request and digest with the intent version during
`prepare` or `reprepare`, before `approve` can issue a token. New unbound
intents are denied approval with `INSERT_REQUEST_UNBOUND`. Existing offline
rows remain readable, but `claim_insert` denies them and a transport never
receives a request from them.

`claim_insert` accepts no body or mapper input. In its existing immediate
transaction it loads the version-bound record, rechecks its digest and
allowlist, writes that exact record into the insert-attempt evidence with the
marker, then returns the frozen request. The transport accepts only that
returned request and sends its method, path, and body unchanged. Thus it has
no place to remap a claim into a later mapper result.

Persist the bound insert request in both the current intent and its immutable
version evidence. A reprepare must bind a new request before it can be
approved; it cannot edit the request associated with an old version.

### Shared native commercial validation

Extract the preview's existing source/PO/PR/native-invoice checks into one pure
validator with an explicit document state: `MAPPED`, `DRAFT`, or `SUBMITTED`.
It retains the existing commercial checks for the exact PO/PR rows, quantity,
UOM, amount, accounts, no-stock-update, no tax, no credit/return, and no mixed
line. State changes only the required invoice name and `docstatus`:
`MAPPED` is unnamed draft `0`, `DRAFT` is the exact known name at `0`, and
`SUBMITTED` is that exact name at `1`.

The validator also receives the expected synthetic bill fields. The raw mapper
must first be admitted unchanged by the existing preview; it does not gain a
new null-field relaxation. Only then does the binding step clone that admitted
mapper, add the disclosed `bill_no` and `bill_date`, and call the same
validator with those exact expected fields. Draft and submitted readback
require them. The existing preview delegates to this validator for its mapper
check, so the coordinator does not copy commercial rules.

### Frozen-body pre-insert comparison

This is retained for the later coordinator stage and is not implemented by the
offline binding/shared-validator substage. That substage stores the raw bound
body and its digest without attempting a fresh-source comparison.

Before an insert claim, the coordinator obtains a new complete source read and
reconstructs the candidate from its fresh native mapper with the same two
disclosed bill fields. It validates that candidate and compares it with the
already-bound raw insert body. The bound raw body is never replaced after
approval.

The observed R4 mapper evidence permits one narrowly defined comparison
projection: omit top-level `posting_time` only when both bodies have an exact
integer (not boolean) `set_posting_time` equal to `0`. The raw frozen body,
raw fresh body, their full digests, and the projection digests remain in
evidence. No other field, including `modified`, child values, `__onload`, or
any key that is merely believed volatile, is ignored. Any other difference,
or failure of the condition, stops before the journal claim. The projection
checks freshness; it does not authorize rebuilding or replacing the frozen
outgoing request.

The coordinator separately requires unchanged `CommercialSource` identity,
PO/PR revisions, and decisive values. A source or payload mismatch follows the
existing source-stop path and cannot be repaired after the insert fence.

### Draft and submit binding

After insert, the complete unique exact-draft readback is validated with the
same `DRAFT` validator before admission. Extend the admitted draft record with
the canonical exact draft document and its digest, bound to the first admitted
draft name. A different later name or document digest enters conflict hold
while preserving the first evidence.

`claim_submit` accepts no request body. Inside its immediate transaction it
constructs the sole submit request from the persisted exact draft document,
checks that `doc.name` equals the immutable admitted draft name, saves the
complete submit request with the submit-attempt marker, and returns it. A
submitted readback must name-match that saved draft and pass the shared
`SUBMITTED` validator. No name-only submit and no remapped body are admitted.

Own-effect classification stays a pure pre-`refresh_source` operation over the
complete new raw source and the original bound evidence. It may remove exactly
one fully proven own draft only from its comparison view. The raw evidence is
never removed, and any remaining foreign document, return, collision, source
revision, or payload mismatch holds future writes.

The SQLite journal can bind immutable records supplied by the trusted
coordinator; it does not establish that an arbitrary in-process caller or an
external provider made a truthful effect. That limit remains explicit in
executor results and tests.
