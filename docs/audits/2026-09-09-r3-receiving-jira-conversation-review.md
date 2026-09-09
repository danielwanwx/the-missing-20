# R3 receiving, Jira and grounded conversation review

Date: 2026-09-09. Scope: one explicitly authorized synthetic receiving order in real demo SaaS tenants, plus open-source conversation research and narrow answer-quality repairs. This is not whole-product, production, invoice/payment, or competition-winning acceptance.

## Verified business effects

- Created `PUR-ORD-2026-00015`, case `M20-GOODS-20260909-40-R3`: 40 Box of `M20-DEMO-CARTON`, synthetic USD 50/Box. No real purchase/payment or revenue claim.
- Two public test photographs were submitted through the real photo/Strands/Bedrock route. Each identified one carton. They are test stand-ins, **not actual delivery evidence**. Missing SKU was resolved with the configured demo barcode-to-ERP mapping; this run used typed barcode evidence, not live camera decoding.
- Arrival 02 posted first as `MAT-PRE-2026-00005` (+1 Box). Arrival 01's stale PO plan was blocked with `NEEDS_REVIEW` before draft/stock mutation. After refreshed evidence it posted `MAT-PRE-2026-00006` (+1 Box).
- Fresh ERP reads verify two unique submitted receipts, exact item/warehouse/voucher-line stock effects and aggregate received quantity **2 Box**. Remaining **38 Box** is an outstanding order, not proof of loss. Each receipt has one verified Slack notification via Celigo and one Airtable receiving record.
- Three repeated submit requests per capture and duplicate-photo attempts did not create additional receipts. Restart retained the same receipts and SaaS identities. Arrival 02's after-restart readback was collected after the replay exercise; do not represent these as two isolated experiments for that arrival.
- Jira **QRC-2** was actually created for the stale-plan review, updated with capture versions 4/5/9, and closed to **Done** with a verified receipt-resolution comment. Comment IDs `10000`–`10003` and body SHA256 values match across recorded resolved/restart/replay snapshots.
- ERP asynchronously renamed stock rows from `48cf6169f9` / `c6baa76467` to `MAT-SLE-2026-00025` / `MAT-SLE-2026-00026`. Subsequent GET readbacks confirm unchanged voucher, voucher line, item, warehouse, company and +1 quantity; a name change is not a new stock effect. The later real Agent cited the current names.

Evidence: [order](../../artifacts/audits/2026-09-09-r3-demo-order.json), [interleaving](../../artifacts/audits/2026-09-09-r3-interleaving.json), [arrival 1 readbacks](../../artifacts/audits/2026-09-09-r3-arrival1-readback.json), [arrival 2 readbacks](../../artifacts/audits/2026-09-09-r3-arrival2-readback.json), [arrival 1 replay](../../artifacts/audits/2026-09-09-r3-arrival1-replay.json), [arrival 2 replay](../../artifacts/audits/2026-09-09-r3-arrival2-replay.json), [Jira identities](../../artifacts/audits/2026-09-09-r3-jira-comment-identity.json), [current arrival 1 source](../../artifacts/audits/2026-09-09-r3-final-arrival1-source.json), [current arrival 2 source](../../artifacts/audits/2026-09-09-r3-final-arrival2-source.json).

## Real defect repaired: Jira resolution acknowledgement

The original transition reached Done but its combined comment was absent from the complete comments GET. The local resolution correctly remained UNKNOWN. This observation does not establish that Jira universally ignores embedded comments; its transition API documents `update.comment.add`, and transition configuration can matter. [Official transition API](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/#api-rest-api-3-issue-issueidorkey-transitions-post).

Resolution now uses a separately journaled comment POST/readback followed by the transition/readback. An old UNKNOWN transition first attempts read-only reconciliation with its original proof. If only the proof is missing, the missing comment is independently journaled and verified; the uncertain transition is **not resent**. Regression tests cover old proof present/absent, missing embedded comments, repeated synchronization and journal restart. A repeated identical proof is rejected; distinct legitimate legacy/new proof bodies are not incorrectly treated as duplicates. [Official comment API](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-comments/#api-rest-api-3-issue-issueidorkey-comment-post).

The verifier opens separate current external reads, but reuses production matching helpers. It is not an independently implemented accounting oracle. Exact Jira comment identity/hash snapshots add a separate stability check.

## Conversation research and changes

[Five source-verified OSS options](../research/2026-09-09-conversation-oss-options.md): retain Strands; Strands Evals is the preferred optional evaluation dependency; DSPy/GEPA later for offline prompt optimization; Promptfoo an alternative runner; no LangGraph migration justified. No dependency was installed or upgraded.

Implemented within the existing runtime and bounded repair budget:

- Allow up to 160 words for compound receiving answers (1400-character schema ceiling), instead of conflicting 80-word/800-character pressure.
- Inspect source-known requested quantities/UOM, linked receipt and stock-row identifiers, and baseline comparable count/minimum. Numeric comparison accepts decimal equivalents without matching identifier substrings or decimal fragments.
- Infer a clear requested history metric even if the model omits chart selection; reuse the same metric routing as rendered history.
- Distinguish a stock entry's `voucher_no`/`name` fields from the enclosing `evidence_id` citation. Repair feedback points to already-read fields, not a prewritten answer.
- Reject duplicate follow-up questions after punctuation/case normalization; prompt for distinct, relevant, read-only suggestions after answering the current question.
- Align the read-only next-step vocabulary with the existing prompt's `verify`/`observe`; affirmative write suggestions remain rejected.
- Reject explicit open/paid/closed/held invoice claims when the receiving source says no invoice exists. Avoid unobserved customer/billing clearance claims in the receiving prompt.

These are narrow completeness/contradiction checks, not full semantic verification or measured general intelligence improvement. The three-turn transcript limit remains. Future held-out paraphrases, longer references, robust suggestion usefulness and cross-case evaluation remain necessary before broad claims.

## Failures retained, not rewritten as passes

- [Before recovery](../../artifacts/audits/2026-09-09-r3-before-recovery-conversation.json): three real runtime turns completed but omitted requested quantities, exact stock IDs or baseline minimum. Runtime success was not answer-quality acceptance.
- [Initial completeness gate](../../artifacts/audits/2026-09-09-r3-coverage-real-conversation.json): validation failure; decimal-equivalence issues were subsequently corrected with tests.
- [First final attempt](../../artifacts/audits/2026-09-09-r3-final-real-conversation.json): turn 2 failed the stock-row identifier check.
- [Source-field guidance attempt](../../artifacts/audits/2026-09-09-r3-source-fields-real-conversation.json): turn 1 failed the read-only next-step check. The prompt/check vocabulary mismatch was independently identified in code; the retained failure does not record raw rejected next-step text, so it cannot alone prove the exact generated phrase.
- [Verification-language attempt](../../artifacts/audits/2026-09-09-r3-verify-language-real-conversation.json): all three runtime turns passed, but human inspection rejected turn 3's unsupported “invoice is open” and absence-of-customer/billing-issues claims. Exact ledger IDs in turns 1/2 match subsequent external reads. The new invoice gate and source-lifecycle guidance address the observed contradiction; a passing runtime flag is explicitly not semantic approval.

The [lifecycle-aware run](../../artifacts/audits/2026-09-09-r3-lifecycle-real-conversation.json) completed three runtime turns without the earlier invoice claim, but turn 3 omitted the requested prior mean and comparable sample count. This was rejected for incomplete answering. The AVAILABLE-baseline gate now also checks those source-derived values (mean rounded to two decimals).

The [last run](../../artifacts/audits/2026-09-09-r3-baseline-real-conversation.json) passed turn 1 but failed turn 2's exact stock-row identifier requirement through the bounded attempts; it never reached turn 3. **Final complete multi-turn quality acceptance remains NOT PASSED.** Inconsistent results on the same live facts show that stronger prompts/checks alone have not established reliability. Do not select one successful run and claim stable improvement. The next useful evaluation step is compact, source-grounded record views and held-out conversation tests, not unbounded reruns until a pass or another orchestration framework.

## UI and acceptance boundary

Chrome accessibility inspection of the live R3 dashboard showed **2 of 40 Box received**, ERP 2, gap 0, no invoice, Jira/Celigo/Airtable/Slack VERIFIED, two posted photo observations, and four retained source observations **0 → 1 → 1 → 2**. The repeated 1 is a source-state observation, not a third delivery. Prior mean 0.67 and net change 2 describe different calculations. Business revenue remains unavailable rather than invented.

The actual external Jira page was opened and inspected: QRC-2 Done, original stale-PO message, subsequent prepared/submitted comments and final receipt evidence are visible. This was an accessibility/readback inspection, not a complete screenshot-based mouse acceptance of every external application. Jira comments are currently verbose machine-readable evidence and remain a presentation-polish opportunity.

The actual ERPNext page for `MAT-PRE-2026-00006` was also inspected after load: status **To Bill**, demo carton quantity 1, rejected quantity 0, USD 50 rate/amount, Stores - M20, and activity showing **Missing20 Agent** created and submitted the document. “To Bill” is the receipt's state, not proof of an existing open invoice.

No invoice was generated, no PayPal integration enabled, and no payment attempted. The user's demo invoice authorization is retained for a later scoped billing scenario; it does not justify billing all 40 ordered units when only 2 have arrived. R2's old ambiguous Jira create was not retried. No production or competition-award guarantee is made.

## Regression and independent review

Independent reviewer approved the scoped Jira/receipt recovery and the initial three bug fixes after 66 targeted tests, while explicitly withholding multi-turn quality acceptance. Subsequent live invoice hallucination was identified during manual semantic review and retained above. Final test and reviewer results follow below.

- Final exact-code full Python regression: **1543 tests, zero failures/errors/skips**, including the AVAILABLE-baseline check. [JUnit evidence](../../artifacts/tests/2026-09-09-r3-full-regression.xml). Private competition package consistency audit also passed; it made zero provider calls and is not a live business/answer-quality verdict.
- Final changed-path regression after that check: **103 passed** across receiving answer coverage, live advisory gateway and Jira; Ruff and `git diff --check` passed.
- Frontend regression: **98 passed**; no frontend code was modified in this delivery.
- Independent final recheck: 42 coverage/receiving/semantic tests plus 6 read-only-boundary tests passed; no blocking code regression found. The reviewer independently confirmed the last live sequence failed turn 2 and withheld full live answer-quality acceptance.

Additional semantic limits flagged independently: “has not yet arrived” is stronger than “not evidenced as received” when based on an outstanding PO alone; generic GL/incident suggestions have not demonstrated their usefulness; narrow invoice regex checks do not validate all financial claims. These remain evaluation targets, not accepted output qualities.

**Delivery verdict:** scoped real receiving/Jira recovery and stronger conversation validation are ready to commit; the researched OSS decision is complete. Stable complete multi-turn answers, broad complex-case coverage, invoice/payment lifecycle and production/award readiness are not demonstrated by this delivery. No baseline/ROI figure is fabricated to compensate.
