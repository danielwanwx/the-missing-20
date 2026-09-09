# Receiving contract correction — frozen incremental design

2026-09-09; implementation parent baseline 85d6a159 (startup baseline be419eab). This implements one seam of F03, not whole finalization. Independent backend reviewer approved the direction subject to four safeguards incorporated below. Existing failed prose and source observations remain evidence; new model-input structure does not itself prove semantic improvement.

## Loop contract

Goal: model tools distinguish independent physical observations from receipt-derived lower bounds, expose exact current receipt/ledger relationships, and preserve prior source references without admitting prior assistant claims as facts. Inputs: current scoped ERP catalog, case quantities/basis, last explicitly scoped successful conversation entry. No new framework, model, writer, provider permission or dependency. Check fixtures at the actual model payload and gateway boundary; then current R3/R4 real-model sequences and independent semantic review. Stop a live variant after three repeated failures; retain all attempts, do not weaken validators or loop until a lucky pass.

## Architecture and compatibility

Current: physical metric falls back to posted quantity; an adjacent basis flag must qualify a generic `physically_arrived`. Prior receiving context excludes assistant prose but loses which records its answer referenced. Target: retain internal case/UI quantities unchanged, transform only receiving model inputs into unambiguous basis-specific quantities and current record relations. Existing source tools, source freshness gates, policy classification, confirmation/version binding, lookup-only unknown recovery and SaaS journals are unchanged. No migration of databases; new conversation metadata is additive. Legacy entries lacking explicit case/status are unavailable for reference carryover.

Physical values: `independently_observed_quantity` only for INDEPENDENT_OBSERVATION, `receipt_confirmed_lower_bound` only for RECEIPT_CONFIRMED; unknown basis has neither value. Never sum candidate photo counts into confirmed inventory. The original physical aggregate remains internal for deterministic guards and UI compatibility. Quantity completeness reads canonical internal sources so renamed model fields cannot disable it. Actual physical semantics remain an independent prose-review gate.

Relations: derive from every current catalog stock row, join `voucher_no` to an admitted ERP receipt identity, keep underlying row ID, enclosing evidence ID, revision and observation time; quantity/UOM remain in the unchanged source records. Enclosing `:ledger` is a citation, not the underlying ledger ID or guaranteed receipt ID. Unmatched/malformed rows are excluded; associations carry source records, never invented independent-verification assertions.

Dialogue references: successful persisted turns gain explicit case ID/status/source sequence. Prior cited IDs produce a set of candidate current receipt references, never a selected record or prior answer truth. If some/all prior candidates are absent now, expose stale/mixed status and original/current sets; never silently reduce two to one. Case switch rejects prior references. User rejection persists through the existing human-intent mechanism; no inferred execution authority. Agent must still reread current tools before answering.

## Tests and live acceptance

Offline: receipt-derived vs independent vs unknown basis; unchanged source/UI packet; quantity completeness still detects omissions; all receipts/rows retained without cross-voucher matching; current IDs after ledger rename; legacy/wrong-case/failed prior entries; plural references and partial disappearance; current-source failure. Existing lifecycle and recovery tests must retain behavior.

Frozen core semantics: C1–C11 in the independent backend baseline. Separate held-out questions are reviewer-owned and withheld until implementation freeze. Critical real conversations repeat three times; use original three-question sequence and held-out variations, preserve every failed attempt and usage. Real external changes are not necessary for this read-only contract experiment; current R3/R4 source snapshots plus source-modified offline fixtures cover different mechanisms without mutating preserved cases.

Acceptance requires explicit retry answer, accurate numbers/UOM/identifiers, correct missing-vs-outstanding and financial-causality explanation, useful read-only follow-ups and no cross-case leakage. Schema/numeric passes remain only runtime checks. If corrected source semantics do not fix prose, mark F03 FAILED and diagnose independently instead of claiming success. Rollback is a normal isolated revert of this accepted commit, without touching runtime databases or historical evidence.

## Remaining design dependencies

The same-new-order supplier/customer chain, QA/refusal execution, phone/camera physical trial, production identities and full UI matrix remain separate F05–F13 gates. Before any supplier invoice test the source bill must be explicitly synthetic and supplied/authorized; receipt amount alone does not establish a supplier-issued bill. No real payment. The final five-minute narrative and public release await the full acceptance conditions in the tracker.
