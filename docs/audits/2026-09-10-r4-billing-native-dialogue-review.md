# R4 receiving, supplier billing and native conversation

Status: **VERIFIED_IN_DEMO**. Code, real operator path, six model answers and
the exact financial/stock evidence received independent approval.
This is one competition-demo path, not overall finalization or production acceptance.

## Same-order business result

The retained R4 photo-receiving case is `M20-GOODS-20260909-40-R4`, purchase
order `PUR-ORD-2026-00016`, receipt `MAT-PRE-2026-00007`. The earlier accepted
photo/receipt/lost-ACK/handoff evidence remains scoped by its
[original audit](2026-09-09-r4-automatic-receiving-recovery-review.md).

On September 10, the primary operated the actual billing UI: prepare, approve,
execute, renew expired approval for the acknowledged draft, and execute its
single submit. ERPNext invoice **ACC-PINV-2026-00008** is now submitted
(`docstatus=1`), for **1 Box / USD 50**, against disclosed synthetic supplier
bill `SUP-BILL-R4-0001`. Bill date is September 9; posting date is September 10.
It links the same PO/PR and exact child rows `458j82kp8e` / `068bbdr0mb`.
Its own invoice child is `9tj5ke29dn`. No new receipt or replacement invoice
was created during recovery.

Read-only ERP verification found exactly two active USD general-ledger rows:
`Stock Received But Not Billed - M20` debit 50 and `Creditors - M20` credit 50.
The supplier is `M20 Controller Systems Ltd.`. The invoice has no stock-ledger
entries (`update_stock=0`), and the receipt's existing `MAT-SLE-2026-00027`
entry is unchanged: 1 Box / USD 50 stock value. The bill remains unpaid,
with USD 50 outstanding and `is_paid=0`. This is not revenue or payment.

The actual ERP browser showed the invoice as Unpaid, and its View → Accounting
Ledger page showed the two entries and balanced USD 50 totals. The local UI
showed `SUBMITTED READBACK ADMITTED` and linked the exact invoice. Screenshots
were inspected inline in the working conversation. The app's separate financial
badge remains `NOT VERIFIED`; the GL/SLE check here is an external acceptance
check, not an implemented automatic financial-verification badge.

Private raw evidence: `/private/tmp/m20-r4-visible-billing-acceptance-01/`,
including `before-pr-sle.json`, `financial-readback.json`, `financial-review.json`
and preserved hold/expiry diagnoses. Complete scoped GL/SLE queries and their
raw pages were saved before acceptance assertions.

## Actual product conversation

Installed Strands 1.53.0 native snapshot sessions now back the opt-in receiving
chat before and after a supplier invoice exists. Native history keeps the
human conversation; each factual turn retrieves current source evidence.
It uses the existing Bedrock Nova Pro model and five read-only source tools.
No summary framework, model upgrade or new dependency was added.

The actual R4 interface completed these six turns, in order:

| Task | Observed answer |
| --- | --- |
| Receipt quantity and stock record | PR7: 1 Box, MAT-SLE-2026-00027 |
| Remain read-only | Acknowledged without an unnecessary source read |
| Ordered/outstanding and whether lost | PO16: 40 Box ordered, 39 outstanding; loss not proved |
| Whether receipt/photo proves carton contents | No independent proof; cited PR7 and retained photo identity |
| Invoice for the receipt first discussed; payment/stock effect | Correctly resolved PR7 → PI8, unpaid, no new stock from linking the bill |
| Retained authority and evidence for prior answer | No change permission; cited the same PO/PR/PI |

All questions were entered through the UI. Persisted context counts were
0, 1, 2, 3, 4, 5. The six turns used 10 logical model requests, 98,672 input
tokens and 993 output tokens, estimated USD **0.0821152**. Model-turn elapsed
times were 2.829, 1.131, 2.474, 3.502, 3.189 and 2.883 seconds; these are not
full operator task times or a workload benchmark. Code hashes remained unchanged
through this sequence. Private evidence is
`/private/tmp/m20-r4-native-ui-acceptance-02/`.

Minor wording remains: Q5/Q6 combined native status “Unpaid” with the catalog's
“Open” label; Q6 included a catalog ledger alias alongside exact document IDs.
Native chat does not generate structured citation attachments. Model completion
is explicitly `NOT_EVALUATED`; these particular answers receive separate review.

## Failures retained and corrections

- Crossing midnight invalidated the old posting-date basis. A new real native
  mapper preview used September 10, preserving bill date, quantity and amount.
- The first insert succeeded, but raw Frappe POST/GET representations differed
  in temporary metadata and unset posting-time formatting. The comparison now
  ignores only those observed presentation differences after the unchanged
  full business validations; raw ACKs/documents/digests remain retained.
- Approval expired while that defect was investigated. Same-manager renewal
  now applies only to the acknowledged, unsubmitted original draft. Its insert
  marker stays set; submit still checks current commercial evidence.
- A final restart after approval expiry correctly retained the submitted invoice.
  Clicking the UI's read-only Reconcile then exposed an unresolved repeat-read
  defect: PI8 again passed the submitted business validator, but generated ERP
  metadata changed its full-document digest. The journal recorded
  `SUBMITTED_IDENTITY_CONFLICT` and retained a review hold. The already submitted
  invoice, its financial proof and the six accepted conversation turns remain
  valid; the current UI must distinguish that completed submission from the
  later reconciliation hold. Raw evidence is retained in
  `terminal-expiry-readback.json` under the billing evidence directory above.
  No ERP write or historical journal mutation was used to clear it. Repeat-read
  equivalence and recovery are deferred under the user's demo-first scope.
- The first UI chat attempt took the legacy route after invoice creation and
  failed validation. It produced no displayed answer or retained conversation
  completion. Its cost was not available from persisted UI state; it is not
  counted as zero. Evidence remains in `m20-r4-native-ui-acceptance-01`.
- That legacy packet incorrectly used 40 ordered Box as invoice quantity. The
  native post-invoice packet now receives the current PI's own header and item
  facts, including 1 Box, USD 50, supplier bill number, status, payment fields
  and exact PO/PR links. Missing PI sources stop before model invocation.

The [separate captured-source N1 experiment](2026-09-10-native-session-v2-real-model-review.md)
retains its own six-turn results, authentication failures and costs. Those are
not substituted for this actual R4 UI sequence.

## Checks and operating boundary

Billing context/journal/coordinator/HTTP: **58 passed**, including original-draft
renewal and no repeat insert. Native dialogue and related receiving, ERP-source,
platform and gateway suites passed; two socket tests skipped. Frontend tests
previously passed 101 cases; node syntax and the final CSS/diff checks passed.
Ruff formatting/lint passed. Scoped changed-code type checks found no new
errors; existing imported-module type errors remain. The earlier bounded full
Python regression timed out, so no full current-suite pass is claimed.

The later terminal-expiry projection received an independent review and four
HTTP tests passed. Its real expired GET passed; the subsequent UI reconciliation
failed as described above. That failure is not counted as a passing recovery test.
The final presentation-only correction also passed four HTTP tests and Luna's
independent review. A fresh real UI read showed `HOLD`, the retained submitted
lifecycle, PI8's link, and an explicit explanation of the later reconciliation
mismatch. No action or financial-verification success was fabricated.

Luna independently approved the billing/UI changes and renewal. Terra independently
approved the final post-invoice native source mapping and unavailable-source
handling; the earlier native session integration also received Luna's review.
Luna then independently inspected all six actual R4 answers/current source packet
and the raw PI/GL/SLE evidence, approving the limited demo with the noted citation
wording defect. This review did not run another model or infer success from tests.

Current local demo launch uses the retained R4 runtime, current private bill basis,
`--enable-normal-billing` and `MISSING20_NATIVE_RECEIVING_DIALOGUE=1`.
Native sessions live in that runtime's private `native-receiving-sessions` folder.
The admitted basis is retained as `normal-billing-source.json` in the same private
runtime, so restarting this demo does not depend on a temporary-file location.
After checking/stopping the previous owned listener, resume with:

```sh
MISSING20_NATIVE_RECEIVING_DIALOGUE=1 \
MISSING20_NORMAL_BILLING_SOURCE_READ="$PWD/.missing20-goods-20260909-r4/normal-billing-source.json" \
.venv/bin/python scripts/run_goods_workspace.py \
  --runtime-directory .missing20-goods-20260909-r4 --port 8897 \
  --enable-handoffs --pause-auto-prepare --enable-normal-billing
```

It is an opt-in single-operator demo, not a portable provisioned tenant. Do not
repeat preparation against this already billed receipt; inspect PI8 through its
ERP link. The later reconciliation hold remains recorded in the private runtime.
Customer fulfillment, repeated held-out complex cases, automatic GL verification,
long-chat compression, final recording/materials and judge-access packaging remain
outside this acceptance. The 39 outstanding Box are not a closed purchase order.
