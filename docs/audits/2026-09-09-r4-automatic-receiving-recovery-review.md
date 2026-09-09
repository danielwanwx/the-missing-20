# R4: automatic recovery of a confirmed receiving intent

Date: 2026-09-09. **Scoped recovery slice accepted; whole product not accepted.**

## Delivery contract

The task is a physical-input-to-business-effect workflow, not simulated changing
numbers. This slice addresses a specific break: ERP successfully posts a receipt,
but the application loses its response and retains `SUBMIT_UNKNOWN`. After a
normal server restart, the platform must recover the existing effect and deliver
its configured downstream records without another stock submission.

Existing authority is required. The background worker cannot invent physical
receipt confirmation, create a first submission, release quality stock, invoice,
dispatch, or pay. Pausing automatic draft preparation does not pause readback of
an already-confirmed uncertain submission.

## Actual test and evidence

| Boundary | Observed result |
| --- | --- |
| Demo order | `M20-GOODS-20260909-40-R4`, `PUR-ORD-2026-00016`, 40 Box, synthetic USD 50/Box |
| Physical-input substitute | Public single-carton photo `p05.jpg`, real Strands/Bedrock analysis, typed demo QR identifier, explicit operator identity and receipt confirmation |
| ERP effect | `MAT-PRE-2026-00007`, one submitted receipt, +1 Box, exact PO line and stock-ledger linkage |
| Injected failure | Actual ERP submit succeeded; diagnostic discarded its application response once; capture remained durably `SUBMIT_UNKNOWN` |
| Recovery | Ordinary server startup recovered `RECEIPT_SUBMITTED` by lookup only; no second submission |
| Slack through Celigo | Existing message `1788986162.337109` verified by destination readback |
| Airtable | Existing record `rec0RfqlevwmdoLgt` verified by destination readback |
| Second restart and replay | Three repeat submission requests retained the same receipt/version 8; duplicate photo returned HTTP 400; fresh external reads found unchanged effects |
| Dashboard | 1/40 Box received and posted, 39 outstanding, no current gap, no invoice; one genuine history observation, not a fabricated baseline |

Raw evidence:

- [Fresh demo order](../../artifacts/audits/2026-09-09-r4-demo-order.json).
- [Actual submit followed by injected lost ACK](../../artifacts/audits/2026-09-09-r4-real-lost-ack.json).
- [Replay assertions](../../artifacts/audits/2026-09-09-r4-replay.json).
- [Actual ERP and SaaS readbacks](../../artifacts/audits/2026-09-09-r4-restart-handoffs.json).

The readback artifact's `before_restart` phase is **after the first automatic
recovery and before a second restart**. It must not be misrepresented as the
pre-fault state; that state is in the lost-ACK artifact. Verification compares
exact business effects and retains both posting-time and current stock-ledger IDs;
it does not infer the cause of any identifier change.

Mouse inspection also opened the dashboard photo gallery and followed its ERP
link to the actual Purchase Receipt. ERP displayed the submitted one-Box line,
USD 50, Stores-M20, and Missing20 Agent creation/submission activity. The same
gallery's Airtable link opened the exact R4 detail record, displaying PO16, PR7,
stock ledger `00f1927e91`, quantity 1.00 Box, and `RECEIVED`. Its Slack link opened
the real workspace; choosing Slack's "open this link in your browser" displayed
the exact R4 receipt notification with matching PO, receipt and ledger IDs.
These were real mouse-driven browser checks, not a complete screenshot-based
acceptance of every page.

## Implementation and independent review

`reconcile_next_submission()` fairly selects a persisted uncertain submission,
validates its original confirmation binding, and reuses the original submission
version. The existing `submit_attempted` branch forces lookup-only recovery.
Malformed legacy intents remain untouched and do not starve valid records.

Independent reviewer `receiving_auth_restart_review` approved this limited
adapter/worker/test/diagnostic change after read-only inspection and 8 targeted
passing tests. It explicitly did **not** approve the entire business loop.

### Final retained-code regression

- `PYTHONPATH=src:. .venv/bin/python -m pytest -q`: **1,550 passed**, zero errors,
  failures or skips; exit 0. [JUnit result](../../artifacts/tests/2026-09-09-r4-shipped-regression.xml).
- `npm test`: **98 passed**, zero failures or skips; exit 0.
- Ruff on the changed Python files and `git diff --check`: passed.
- After the final-code service restart, the external `after_replay` readback
  passed again at `2026-09-09T21:03:13Z`, with unchanged receipt and destination IDs.

An initial test invocation lacked the repository import path. A subsequent run
was blocked by sandbox restrictions on local HTTP sockets. The final run used
the correct import path and allowed local test ports; it passed without changing
assertions or skipping those tests. Passing software tests do not constitute
semantic acceptance of live model answers.

## Rejected conversation experiments — not shipped

Live receiving conversation was tested against the real R3 case (PO15, two
posted one-Box receipts), even where artifact filenames contain `r4`.
Several prompt/source compaction, same-model critic, and typed-decision variants
were tried. None established stable multi-turn business-answer quality.

- A three-turn runtime-contract pass still omitted the retry decision and gave
  an incorrect financial-evidence explanation. The independent reviewer rejected
  it: numeric/schema checks are not semantic verification.
- A separate model critic was inconsistent, including rejection of equivalent
  rounded values and acceptance of missing answers.
- The last typed-decision variant failed all three recorded validation attempts on its first
  question. The gateway correctly displayed no conclusion rather than an
  unvalidated answer. This was nevertheless a usability regression.

Evidence: [last failed real run](../../artifacts/audits/2026-09-09-r4-typed-decisions-final.json)
and [runtime pass requiring semantic rejection](../../artifacts/audits/2026-09-09-r4-answer-diagnostic-v2.json).
All four conversation-related production/test files were restored to the
pre-experiment commit `5cf67620003183d74cd5ceef6e679b1a238be120`. Experimental critic
source was removed. Neither a failed critic nor new typed-decision gates ship.
R3 and R4 services were restarted with the retained code.

## Open acceptance gates

1. **Real multi-turn Agent reliability:** exact quantities/UOM, distinguishing
   outstanding order from loss, linked receipt/SLE citations, explicit refusal
   and retry answers, meaningful baselines, and financial limits must all pass
   repeated independent semantic review. This gate remains failed.
2. **Photo-linked downstream business completion:** this new R4 case has no
   supplier invoice, customer dispatch, customer billing, or demonstrated revenue
   uplift. A notification in Slack/Airtable is not that financial chain.
3. **Complex matrix:** partial arrivals, missing ACK, QA freeze/release, changed
   order/SKU, requests for evidence, refusal and resume need one consistent
   current-version live acceptance record; this slice covers only part of it.
4. **Physical trial and history:** a public photo plus typed QR is an explicit
   test substitute, not actual shipment proof or camera/barcode-video acceptance.
   R4 has one real historical observation, insufficient for a comparative baseline.
5. **UX:** every page and relevant external business screen still needs complete
   operator acceptance. This turn verified the receiving gallery's ERP, Airtable
   and Slack paths, not every action or all lifecycle states.

No real payment was performed. Do not label this result production-ready,
end-to-end complete, measured revenue improvement, or guaranteed to win a prize.
The loop-engineering review gate prevented an unproven conversation experiment
from shipping and separated repeatable business-effect evidence from model prose.
