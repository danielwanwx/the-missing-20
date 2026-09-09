# Receiving delivery — independent end-to-end review

Date: 2026-09-09 (America/Los_Angeles)
Scope: existing photo/barcode → ERP receiving → Celigo/Slack and Airtable handoff → operational history and current Agent evidence. This is a read-only review. It is not production certification, a complete platform acceptance, or an award prediction.

## Disposition

**HOLD for the claimed complete physical-to-business loop.** Several bounded components and one earlier one-Box receipt are genuinely evidenced, but the current real record does not prove barcode-before-photo-before-receipt causality, and the receiving Jira exception lifecycle is not yet accepted.

**Checkpoint disposition:** the barcode-to-current-photo binding, Jira fail-closed journaled lifecycle, forward timestamp selection, and corrected Jira UI labels are acceptable as implemented/tested checkpoints. They are suitable to preserve in the submission branch, but they are not substitutes for the two missing live causal acceptances above.

## What is supported by retained evidence

- The retained external verifier records one submitted ERP receipt, `MAT-PRE-2026-00002`, for 1 Box on `PUR-ORD-2026-00012-1`, with a matching +1 stock-ledger effect. It also records one verified Slack notification via Celigo and one verified Airtable row, then the same provider keys after restart. The verifier itself reports zero business writes. See `artifacts/agent/2026-09-08-live-receiving-handoff-readback.json`.
- The local receiving store retains the corresponding capture, human identity confirmation, receipt, and two later barcode lookups. The handoff journal retains exactly one verified row for each of the two configured receipt-notification destinations.
- The handoff implementation requires a submitted receipt and stock-ledger reread before notification (`src/the_missing_20/adapters/receiving_handoff.py:20-71`; `receiving_handoff_worker.py:101-152`). Unknown provider writes become lookup-only, and the worker rechecks the full stock effect before a new notification.
- Barcode lookup is read-only, case/arrival/order-line scoped, validates product mappings against ERP, and does not infer quantity from a common product code (`src/the_missing_20/adapters/receiving_barcode.py:36-114`). Public optical development evaluation is separately approved at 14 correct / 2 abstain / 0 wrong / 0 runtime errors, not as live camera or warehouse accuracy.
- The newly added confirmation path can now bind one selected barcode evidence ID to the current photo digest and image version, re-resolve that code against the current ERP item and PO, and retain the model's original output (`photo_receiving.py:807-899`). This is a sound implementation boundary, but it was added after the retained one-Box transaction and therefore does not change that transaction's provenance.
- A current operator/API checkpoint reports that ERPNext now retains barcode `M20-CARTON-BOX` with UOM `Box` on `M20-DEMO-CARTON`, and that ERPNext's native `scan_barcode` resolves it back to that item/UOM. This closes the earlier empty-master-data setup problem, but this review did not perform the external read itself and no new receipt is attributed to that barcode; preserve the resulting GET payload in the final acceptance artifact.
- The forward history-timestamp correction now chooses the newest server-ingested scan/conflict/barcode/photo timestamp instead of backdating physical evidence to a cached ERP read (`src/the_missing_20/adapters/operational_history.py:245-288`). Its focused physical-evidence tests pass.
- Focused non-HTTP review suite after the barcode-binding and Jira additions: **160 passed** across operational history, barcode, Jira, handoff, destination, and platform-link tests. HTTP tests could not bind a loopback socket in this review sandbox; that environment denial is not counted as a product regression and prior full-suite evidence is kept separate.

## Blocking findings

### P0 — The retained real transaction is not a barcode → photo → ERP chain

The real receipt was posted around 03:36 UTC. The two retained barcode observations were created later, around 06:30 and 06:40 UTC. The capture still records `identity_confirmation.source = explicit_human_confirmation`; the barcode evidence did not authorize or identify that receipt. The browser artifact likewise says its barcode run requested no stock write.

That is a limitation of the retained evidence, not the latest code path. The current implementation stores barcode results by tenant/case/arrival (`photo_receiving.py:666-735`) and can bind a selected result to the exact current photo digest/image version during explicit identity confirmation, after a fresh ERP barcode and PO-version check (`photo_receiving.py:807-899`). The browser passes the selected evidence only when arrival and item still match (`workspace/photo-receiving.js:415-424`). No retained real transaction has exercised this new causal path yet.

Required acceptance: use a fresh arrival and scan a configured code before any draft or submit; bind the selected identity observation to the durable capture/photo version (or preserve an explicit operator selection); then take the photo, create/re-read the draft, explicitly approve the exact receipt, submit, reread the receipt/ledger, and verify the same downstream keys. A later scan must not be presented as input to an earlier receipt.

### P0 — Jira create/update/resolve is implemented locally but not yet an accepted destination lifecycle

The older evidence adapter still supplies only the existing Jira GET observation (`src/the_missing_20/adapters/saas_evidence.py:482-561`). A new receiving-specific writer is now integrated behind the explicit `jira_receiving_enabled` runtime switch (`receiving_handoff_worker.py:41-51,132-209`). It creates a case/capture-scoped Task only for `NEEDS_REVIEW`, adds immutable revision comments, and attempts resolution only after a fresh exact ERP receipt/stock-effect reread and both receipt-notification destinations are verified (`receiving_jira.py:104-167`). The earlier malformed-envelope and partial-resolution comparison defects were corrected: provider structures fail as `ValueError`, and every `receipt_event` field must match before even the resolution comment is journaled (`receiving_jira.py:18-29,66-111,183-274`). Direct provider-contract tests cover malformed responses, lost acknowledgements, duplicate identity, per-field resolution mutations, and ambiguous Done transitions.

This is not live acceptance. The current real handoff configuration does not enable or scope the Jira route, the one-Box artifact contains no new receiving issue/comment/Done readback, and the focused tests do not exercise a real worker/provider lifecycle.

The initial judge-facing provenance regression in this new integration has been corrected. `handoffLabel` now classifies Jira before generic destinations and gives verified create/comment/resolve distinct opened/evidence-updated/resolved labels; unknown Jira effects are not presented as verified (`workspace/photo-receiving.js:199-205,286-296`). The executable DOM-independent regression checks all three Jira operations plus Airtable (`tests-js/photo-background-updates.test.mjs:10-19`), and the focused Node file passed 4/4 in this independent review.

Required acceptance: enable only the dedicated demo project and run one real scoped exception through create → evidence revision → authoritative ERP recovery → Done reread → restart, proving no duplicate issue/comment/transition. Retain provider IDs and timestamps.

### P1 — Existing retained history still contains pre-fix causal timestamps

The forward code fix is sound in the focused tests, but the append-only real database still contains barcode-bearing history points whose `observed_at` precedes their barcode records: history rows 9/10 are about 06:30:25 and 06:39:51, while their barcode observations are about 06:30:55 and 06:40:18. Those old rows are deliberately not rewritten.

Required acceptance: create one new physical event after the fix and verify the stored point time is at or after its server ingestion/observation time, unchanged polling creates no point, and the UI orders it correctly. Keep the old rows with an explicit software-timestamp limitation or revision record; do not silently edit them into apparent original facts.

### P1 — Real Agent quality is mixed, not a complete acceptance

The retained Strands/Bedrock conversation does demonstrate source tools, exact ERP/SaaS/barcode citations, and read-only behavior. Turn 8 accurately reports the ERP item, category, UOM, price, and that barcode identification did not post stock. However, turns 3 and 4 incorrectly describe a prior-observation-mean difference as temporal growth. Later turns correct that calculation, but turn 9 still says there was no historical data to compare while citing eight operational-history evidence IDs. The correct safety conclusion does not erase the internally false rationale.

Required acceptance: run a preregistered fresh set covering normal partial receipt, barcode/photo mismatch, duplicate/lost-ACK, quality/damage stop, over-receipt, and Jira resolution. Score answer facts, citations, stop decisions, writes, and provider effects separately; retain failures. Do not treat one corrected follow-up as overall Agent reliability.

## Evidence boundaries that must remain visible

- The successful one-Box photo was a public development image plus explicit human SKU confirmation, not a real commercial shipment.
- The current barcode camera/video artifact uses synthetic video and reports `camera_hardware_tested: false` and `stock_write_requested: false`.
- Operational history is retained observation-time history, not a complete ERP event ledger, industry benchmark, labor study, or causal ROI proof.
- Local SQLite idempotency is appropriate for the bounded single-deployment demo; `receiving_handoff.py` explicitly does not claim distributed exactly-once delivery.
- Passing unit/contract tests does not replace a fresh real Jira lifecycle, a fresh post-barcode receipt, or a fresh external readback.

## Minimum path to bounded delivery acceptance

1. Enable the bounded Jira route and perform one real create→comment→resolve→readback lifecycle.
2. Provision one fresh isolated arrival and execute scan→photo→explicit approval→ERP receipt/SLE→Celigo/Slack+Airtable (+ Jira when exceptional) in causal order.
3. Confirm the post-fix history timestamp and dedup behavior on that event, preserving the older limitation.
4. Run fresh Agent questions before and after each state change and score the original answers; no unsupported invoice, quality, revenue, delivery, or completion claims.
5. Save provider IDs, timestamps, source versions, UI screenshots, and zero-duplicate restart readback in one acceptance artifact.

Until those gates pass, the supported statement is: **one earlier human-confirmed one-Box receipt and its two notification copies are real and replay-safe in the bounded demo; barcode-to-photo binding and the Jira lifecycle now exist in code but are not yet proven as one complete real transaction.**
