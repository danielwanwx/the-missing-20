# Receiving implementation checkpoint — not final acceptance

This checkpoint implements missing business connections. It does **not** claim
full production readiness, a representative warehouse accuracy benchmark, or an
award guarantee. The independent whole-product verdict remains HOLD.

## Delivered code

- A scanned ERP item can be explicitly bound to the current photo digest/version.
  Confirmation rereads the item and PO; a changed version, wrong arrival, wrong
  item, damaged/ambiguous photo or stale capture cannot be silently accepted.
  The original model assessment remains unchanged. Scanning is not a stock posting.
- Jira receiving review operations reuse the durable delivery journal. Creation,
  each evidence revision and resolution have distinct operation identities.
  Uncertain writes reconcile by lookup, never blind retries. Normal partial POs,
  count candidates and ordinary photo retakes do not create incident tasks.
- The optional worker only resolves a review after fresh matching ERP receipt/SLE
  reads and verified configured receipt destinations. The Jira boundary additionally
  compares every field of the resolution with the current receipt event. It does
  not grant stock, QA, invoice or payment authority to Jira or the language model.
- Provider envelopes fail closed. Ambiguous transitions require human intervention.
  UI links distinguish Jira review actions from Airtable receiving synchronization.
- History uses actual server-ingested physical-event times when they are newer than
  the cached ERP read. Unchanged polling does not generate observations. Old stored
  observations are not rewritten; their earlier timestamp defect remains disclosed.

## Initial checkpoint verification (commit 349be34)

- Full Python regression: **1,475 passed**, zero failures/errors/skips (114.657 s).
- Frontend Node suite: **95 passed**. Includes actual handoff-label function checks.
- Targeted Ruff and whitespace checks passed; npm reports zero known vulnerabilities.
- Existing real ERP receipt `MAT-PRE-2026-00002` (1 Box), corresponding stock ledger,
  Celigo→Slack message and Airtable row were freshly reread before server restart.
  This is retained real receipt evidence, not a newly performed barcode-first receipt.
- The same readbacks passed after restart, with no duplicate receipt or destination
  effects. A real UI barcode query then produced a new history observation at
  `2026-09-09T08:07:31.099240Z`, while received inventory remained 1 Box.
- Staged-file clean-copy verification found no missing source/dependency files:
  1,471 tests passed initially; four golden tests required Git metadata absent from
  the exported index. After initializing only that temporary copy's Git metadata,
  its complete golden subset passed 44/44. No runtime databases or credentials
  were copied into this verification environment.
- Owner UI saved internal item barcode `M20-CARTON-BOX` with UOM Box. Fresh ERP API
  reread and ERP native `scan_barcode` both resolve `M20-DEMO-CARTON` / Box. This
  repairs the item-master setup gap without changing inventory or account permissions.
- Actual Jira project lookup confirms QRC and Task type availability. This read
  alone is **not** evidence of create/update/resolve success.

## Remaining release gates

1. **Closed for one normal arrival**, not the complex matrix: see the new live
   receipt and replay evidence below.
2. Verify the configured demo receiving pilot's real Jira
   create→evidence update→resolved lifecycle with the same scoped business case.
   The new isolated runtime toggle is enabled; normal receiving correctly creates
   no exception issue. This is not a real exception lifecycle acceptance.
3. Validate complex progressive batches, damaged/held goods, lost ACK and refusal
   through the real sources and current model—not solely provider doubles.
4. Prove meaningful operational comparisons. No claim of causally increased
   revenue, labor savings, mixed-SKU/UOM support or outbound picking acceptance.

Jira integration follows the vendor's
[issue and transition API](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/).
Only a scoped incremental checkpoint may be committed; do not label it a final
competition-ready release.

## New barcode-first live receipt and repairs

Case `M20-GOODS-20260909-40` uses new PO `PUR-ORD-2026-00013`, 40 Box at an
explicit synthetic demo rate of USD 50/Box. It does not amend or reuse yesterday's
order. Only the first planned 1-Box arrival was observed; the outstanding 39 is
not a loss or evidence of late delivery.

- Actual UI barcode lookup at 08:18:32Z preceded photo upload and confirmation.
- Public photo stand-in: [Box.agr.jpg](https://commons.wikimedia.org/wiki/File:Box.agr.jpg),
  Arnold Reinhold, CC BY-SA 3.0. One empty open carton does not prove contents or
  a real shipment. Original normalized digest:
  `2dc3d1ef5b4d18e22b95f85b71188b5d6b8fa377f0d94a64d857d74b8a2b077b`.
- Actual Strands/Bedrock Nova Pro analysis took 4.823 s / 5,624 tokens. It counted
  one carton without inventing an item code. Operator barcode/photo binding and
  receipt confirmation remained explicit. Browser file-upload control stalled
  for hours before upload; that is not model latency or a production UX pass.
- Capture `eab22f28333d9dbc7a4473a8fd4fb330` produced actual submitted ERP receipt
  `MAT-PRE-2026-00003`, stock ledger `9c6b6a6b13`, exactly +1 Box. Actual ERP UI
  showed the receipt, accepted quantity 1 and USD 50; it was not paid revenue.
- Slack via Celigo: message `1788961453.294629`; Airtable receiving row
  `recyfnB1E4OlEqRp5`. Their actual native web interfaces were inspected, including
  the matching PO, receipt and ledger identifiers. They are notification copies,
  not independent stock authorities.
- Fresh external readbacks passed before and after restart. Three HTTP submit
  replays retained the identical receipt/version; a repeated photo returned 400.
  The 14:29:24Z **post-replay** external readback again found exactly the same ERP
  stock effect and single Slack/Airtable destination records. No verifier wrote
  business data. See `artifacts/audits/2026-09-09-barcode-first-receiving-readback.json`
  and `2026-09-09-posted-receiving-replay.json`.

Repaired an actual mixed-snapshot bug: a locally posted receipt with an older ERP
snapshot must not appear CURRENT or enter history as zero stock. A bounded ERP
refresh is attempted, with a 30-second cooldown; unresolved conflict stays unavailable.
The old inconsistent observation is retained but excluded from charts. Later real
source outage/current transitions changed history from 7 visible points to 9
(10 raw retained rows); the later verifier therefore checks external idempotency
separately and does **not** claim unchanged history. These remain observation
baselines, not industry benchmarks or causal savings.

## Real dialogue reliability: failures retained, no simulated fallback

The repeated real three-turn checks ask: (1) is the outstanding balance missing,
(2) refuse all writes and verify whether a retry is warranted, (3) show actual
history and distinguish net change, prior mean and revenue claims.

Earlier runs exposed incomplete acquisition, cost reservation failure, unsupported
citations and missing structured output. The latter was reproduced with native
Strands `limit_total_tokens`: the original 32k invocation cap counted cumulative
full-history input and stopped before the final typed tool. The receiving synthesis
cap is now 80k total / 4×1,551 cumulative output; the separate factory ledger still
enforces USD 0.16, 250k input, 12k output, 16 requests and time bounds. SDK limit
stops report unavailable, not a fabricated answer or misleading validation failure.

Two technically complete runs (`native-limits-a`, `focused-a`) were rejected for
answer quality: old trend topics leaked into new questions, and notification
copies were called independent verification. Repairs now retain prior **human**
context but not stale assistant prose, preserve only the refusal constraint,
offer history reads for current history questions, and validate notification roles.

Latest `isolated-a` and `isolated-b` each completed **3/3 actual model turns**,
with unchanged receiving quantities and real source-based chart attachments.
`isolated-a` used one bounded validation repair in turn 2; `isolated-b` used none.
Earlier failed and quality-rejected artifacts remain alongside them. These are
two successful short sequences, not a statistical reliability claim. Minor
remaining answer-quality issues include inconsistent decimal formatting and
occasionally explaining the historical mean without stating its exact value.

Whole-product independent verdict remains **HOLD**: this evidence closes the
normal receipt/replay slice, not real complex exceptions/Jira lifecycle, a measured
manual baseline, full operator-camera holdout, or all production requirements.

Final regression for this slice: **1,501 Python tests passed**, zero failures,
errors or skips (`2026-09-09-receiving-release-regression.xml`); **95 Node tests
passed**; scoped Ruff and diff checks passed. A preceding full run retained one
failure in the durable-refusal prompt compatibility assertion, corrected and
rerun in full. The offline competition-package audit also passed with zero
provider calls; its internal readiness label is not a live whole-product verdict.

Actual page inspection still found generic investigation labels before any
investigation and a Slack-under-Invoice diagram association that does not explain
the receiving notification route accurately. They remain UX follow-up work;
neither native external screenshots nor passing tests imply every page is accepted.
