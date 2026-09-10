# Normal receipt → supplier billing: independent design review

2026-09-09. Scope: proposed demo-only R4 normal-receipt billing path. Read-only review of the proposal and current executor, photo receiving, platform approval, handoff and role-task journals. No code changes, external writes or new authorization requests. Existing user authorization covers the scoped demo invoice test; it does not authorize real payment. This review is not invoice execution or product acceptance.

## Verdict

**Direction approved, subject to the concrete pre-write design requirements below.** Reusing PR7 without another receipt, adding a separate normal-billing executor and showing the action in the actual platform is appropriate. Do not route this through QA release or fabricate held stock. SO/DN/SI remains separate and unverified.

The proposal's single `SUBMIT_UNKNOWN` state before external insert is underspecified for two distinct writes. Automatic submission of a discovered draft also needs durable ownership and a submit-attempt fence. These must be resolved before live writes; they do not require another user approval or expanded architecture.

## Reuse map and limits

| Existing point | Useful reuse | Must not inherit |
| --- | --- | --- |
| `demo_executor.py::ERPNextDemoExecutor._request`, `_document`, `_submit_document`, `_mapped_document` | Configured ERP transport, document fetch and ERP optimistic version submission | `execute()` requires held PI and QA transfer; `_insert_and_submit()` lacks separately journaled crash boundaries; `_existing_order_effect()` has bounded first-match semantics unsuitable for invoice uniqueness |
| `photo_receiving.py::PhotoReceiving._event`, `submit`, `reconcile_next_submission` | Persist-before-effect, SQLite compare-and-set version, immutable original confirmation and lookup-only recovery after an attempted submit | Receipt's process-local work lock alone is not multi-process ownership; billing needs its own scope rather than overwriting original receipt confirmation/history |
| `receiving_handoff.py::HandoffJournal.deliver` | Stable business key, persisted immutable payload, unknown-effect reconciliation principle | Notification-specific states/verification are not accounting authority; do not use message receipt success to verify PI |
| `role_task_journal.py::RoleTaskJournal.claim/finish` | Example of `BEGIN IMMEDIATE` and fenced completion | Explicitly read-only; expired lease allows retry. Never use lease expiry to authorize a second financial write |
| `agent_platform.py::approve/execute` | Current source/digest checks and visible manager interaction pattern | Existing approval scope is `M20_DEMO_RECOVERY_AND_CUSTOMER_FULFILLMENT` and requires old quality correlation. Billing needs its own action scope and persistent token; no reuse of an old run-number approval ID |
| `erpnext_source.py::_purchase_documents`, `_ledger_evidence` | PO-linked invoice discovery and current accounting evidence | Discovery reaching its result cap is incomplete. Never interpret incomplete or unauthorized search as absence |

## Required before-write contract

1. **Frozen bill and exact amount.** Store the explicitly synthetic supplier-bill record as durable input, not only its number/date. Bind company, supplier, invoice reference/date, PO/PR and child IDs, item, Box/stock UOM/conversion, billed quantity 1, net rate USD 50, currency, tax/discount/rounding and total. Use decimal-safe currency comparison. If taxes or charges exist, USD 50 net is not automatically USD 50 payable; freeze/approve the actual total. No real supplier-issued claim is implied by this fixture.
2. **Narrow quantities.** Require submitted non-return PR7, its exact accepted line and PO16 link; inspect current returns/credits/cancelled documents and existing linked bills. For this one-line pilot, block any mixed-line/mixed-order invoice or existing partial-bill ambiguity. Cap remaining billable quantity using authoritative related transactions, not only PO ordered40 or a potentially stale billed percentage. Do not affect the other39 Box.
3. **Verify mapper output.** PR→PI mapping is an implementation candidate; confirm the deployed endpoint/schema read-only before mutation. After mapping and selecting the exact line, recompute/verify stock quantity, native PO/PR child references, company/supplier, accounts, taxes/discounts/rounding, quantity/rate/currency and `update_stock=0`. Reject any extra item/return/payment flags. Do not trust totals inherited from the original unsliced mapper document. The final ERP-calculated draft must match the approved commercial envelope before submit.
4. **Dedicated approval.** Bind a non-reusable server-issued token to action `NORMAL_RECEIPT_BILLING`, bill digest, exact plan/source revision, operator identity, case and durable intent. User refusal invalidates pending authorization. A new invoice-basis or commercial-source revision blocks a new write; reprepare/reconfirm the new plan through the platform. “Continue,” model prose or old QA approval cannot authorize billing. Demo manager identity remains demo persona assurance, not production authentication.
5. **Separate irreversible boundaries.** Minimum durable states/flags: prepared → approved → insert-attempted/unknown → exact draft verified → submit-attempted/unknown → submitted-verified; blocked/conflict/rejected remain explicit. Naming can differ, but persist whether each external write was attempted and its immutable payload/name **before** sending it. Do not hold an uncommitted DB transaction across network I/O.
6. **Concurrency claim.** Use a shared SQLite intent key and atomic compare-and-set/transaction claim before both insert and submit. At most one process may issue each first attempt. Expired ownership permits readback, never another insert/submit. Two different bill numbers targeting the same one-Box receipt must also compete on the remaining receipt-line billing scope, not just separate bill-number keys. The pilot must document that all writers use the shared runtime/journal; it cannot promise protection against an independent deployment or arbitrary concurrent manual ERP billing.
7. **Recovery semantics.** Lookup uses stable company+supplier+bill number and complete pagination; inspect all candidate PO/PR/row links, including drafts and cancelled/conflicting records. Unique exact submitted PI: verify and reuse. Unique exact draft: submit only if the original intent authorized it, current financial prerequisites still match, and **no prior submit attempt exists**. After any submit attempt, read only; a returned draft does not prove the earlier in-flight request cannot commit. No match after attempted insert remains unknown/hold, not permission to create again. Multiple candidates, incomplete queries or differing fields hold. A changed current source must not prevent readback of an already-attempted original effect, but must prevent a new write.
8. **Refusal during an in-flight effect.** Persist the stop request; perform no subsequent write, but continue readback to report any effect already committed. Do not label such an effect cancelled or roll it back implicitly. In particular, a refusal after insert may leave a draft rather than proceed to submit.

These requirements use one small billing journal and existing transport, not a new agent framework. The residual ERP concurrency race with independent writers must be disclosed and bounded by the controlled demo scope; broader guarantees need destination-enforced uniqueness/transaction rules.

## UI and Agent integration

Arrival details show synthetic bill provenance, exact proposed amount/quantity, current status, available action and reason when blocked. The Agent reads current receiving and bill facts and recommends a supported action; deterministic code creates the plan and enforces execution. Clicking confirm must go through the new platform action and persist its authority, not invoke a seed script or private executor bypass.

Keep receipt status and billing status separate: PR7 remains submitted; draft PI is not billed; unknown PI is not missing; submitted PI is not paid. Display the exact external PI link only when its identity is known, with draft/submitted status accurate. Repeated confirmation retrieves the same intent/result. Existing receipt photo, ledger and handoff links remain available. No hidden escalation into sales fulfillment or payment.

## Acceptance required for this optimization

Offline tests must cover wrong PO/PR row, item/UOM/conversion, company/supplier/currency, rate/tax/total change, already billed/returned/conflicting PI, stale/reused/cross-case approval, refusal, complete vs truncated search, and two-process claim races. Include two bill references racing for the same receipt quantity.

Crash points: before insert; insert succeeds/ACK lost; draft read verified before submit; submit succeeds/ACK lost; submit response returns error/unknown; restart at each boundary; repeated confirm and simultaneous worker/user recovery. Prove no duplicate insert or submit from resumed unknown states. Test unique mismatched draft and multiple matches, not just successful lookup. Model failure cannot bypass preparation or authorization gates.

Live demo, only after independent patch review:

- Freeze PR7/PO16 and exact line/source snapshots plus explicit synthetic bill; inspect real platform proposal and confirm through visible UI.
- Read PI `docstatus=1`, exact native PO/PR child links, supplier/company,1 Box, correct USD net/gross/tax and payable account. Verify PR/PO billed state with the deployed ERP behavior; receipt quantity remains1.
- Independently read all GL rows for this PI: correct voucher/company/party/accounts, expected payable/tax/clearing amounts, and debit=credit. Balance alone is insufficient.
- Assert **zero PI stock-ledger rows** with `update_stock=0` and unchanged PR7 stock effect (voucher/row/item/warehouse/quantity, allowing known identifier renames). This is stronger than comparing an aggregate global stock number that unrelated operations may change.
- Capture normal restart/repeated confirmation readbacks: same PI identity and same amount/GL effects, no extra stock effect. Do not reinject R4's historical receipt fault or repost receipt stock to test billing.
- Verify invoice source appears in current ERP evidence/UI and failure/unknown states remain visible. No payment entry, bank movement, delivery or sales invoice is created.

Final disposition: approve proceeding with this amended minimal design and offline implementation. Withhold external-write acceptance until the journal boundaries, exact commercial contract and concurrency tests above are implemented and independently reviewed. Existing user demo authorization remains valid; no additional approval question is needed merely to satisfy this review.

## Primary clarification for the next execution slice — review before writes

The preview's source digest identifies the complete observed evidence snapshot, including lookup scope/completeness and read metadata. It is not a business idempotency key. A refreshed lookup observation time naturally changes that audit digest without changing the bill or its commercial basis. Execution must compare the approved exact document identities, decisive commercial values and authoritative source revisions, while independently requiring a fresh complete lookup. Do not reject every refresh merely because its observation timestamp is new; do not ignore actual commercial/source-version changes either.

Likewise, the intent's own newly discovered draft is an expected transition after an attempted insert, not proof that the original approval authorized a second insert. Before the first submit, compare that exact draft with the frozen approved bill and current source prerequisites, distinguish it from other linked drafts/bills, and enforce the separate durable submit-attempt fence. Keep the original and refreshed audit snapshots. This clarification needs independent implementation review and does not approve an unimplemented executor.
