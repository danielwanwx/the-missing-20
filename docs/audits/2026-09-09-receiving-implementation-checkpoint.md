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

## Verification

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

1. Run a fresh physical arrival with barcode **before** photo confirmation/draft,
   real Strands analysis, ERP receipt/SLE, all destination readbacks and restart.
2. Enable Jira only for the configured demo receiving pilot and verify its real
   create→evidence update→resolved lifecycle with the same scoped business case.
   The runtime toggle is intentionally still off pending live acceptance.
3. Validate complex progressive batches, damaged/held goods, lost ACK and refusal
   through the real sources and current model—not solely provider doubles.
4. Prove meaningful operational comparisons. No claim of causally increased
   revenue, labor savings, mixed-SKU/UOM support or outbound picking acceptance.

Jira integration follows the vendor's
[issue and transition API](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/).
Only a scoped incremental checkpoint may be committed; do not label it a final
competition-ready release.
