# Independent review: receiving source and reference contract

Date: 2026-09-09. Implementation parent HEAD: `85d6a159cb2d2782bf97b758d4d87de2c7c53de8`; reviewed uncommitted implementation frozen by parent before this review. `be419eab1d5faedfecb140fde7112a5443f9cedc` was the session startup baseline, not the implementation parent.

**Approve the code scope. No P0/P1 found in this delta. Live conversation semantic acceptance is withheld and remains a separate gate.** This approves model-source qualification and reference-candidate metadata, not finalization, production readiness, the full photo-to-financial chain or a claim that prior bad answers are fixed.

Files read in full/diff: `src/the_missing_20/agents/receiving_facts.py`, changed paths in `agents/live_advisory.py`, `adapters/live_advisory_gateway.py`, `adapters/agent_platform.py`, `tests/test_receiving_facts.py`, and the frozen design `docs/research/2026-09-09-receiving-contract-finalization-design.md`. Also inspected the existing catalog creation and conversation persistence/projection to assess actual call-site compatibility.

## Safeguard review

| Boundary | Independent finding |
|---|---|
| Renamed model quantities must not bypass completeness | Satisfied. The model receives `independently_observed_quantity` only for INDEPENDENT_OBSERVATION and `receipt_confirmed_lower_bound` only for RECEIPT_CONFIRMED. Unknown basis yields null for both. The existing checker now reads `source_payloads(packet)`, so it still receives canonical `physically_arrived` rather than silently disabling its old rule. This does not improve that rule's semantic limits. |
| Original case/UI/source packet preserved | Satisfied at the production call path. Quantity transformation creates a new quantity mapping and source object; raw records are shared but not mutated. `receiving_packet` constructs fresh tool/source mappings before gateway annotation. Policy/disposition uses the original case facts. No writer or approval logic changed. |
| Explicit reference provenance and persistence | Satisfied. Newly successful gateway responses carry nested case_id, COMPLETE status, source sequence and cited receipt candidate IDs. Real platform persists this additive field; unknown legacy, failed or foreign-case metadata is rejected. Existing stored answer prose is still excluded from receiving model context. |
| Exact ledger relationship | Satisfied. Joins use actual `voucher_no` and `name`, require Purchase Receipt voucher type and admitted ERP receipt/source identity, and retain all matching stock rows. It does not infer receipt ownership from the enclosing ledger evidence label. Enclosing evidence ID, revision and observed_at remain attached. |
| Changed or plural references | Satisfied. Prior candidate set is explicitly retained; missing entries produce CHANGED with prior/current/missing sets. A two-to-one change does not become ONE_CANDIDATE. A plural citation stays MULTIPLE_CANDIDATES. Candidates explicitly carry no selection, facts or approval authority. |
| Source/policy and write separation | Satisfied. No generated verdict is added to source facts, no new write route exists, no permission is inferred from reference presence. Current unavailable sources still return through the preexisting gateway guard. |

Current receipt relations are a convenient projection of admitted source records, not an independent verification oracle. Source scope/truth still depends on the existing ERP source and catalog boundary. A citation to an enclosing ledger containing two receipts correctly yields two candidates; it does not mean the assistant selected both as an intended singular referent. The model must handle that ambiguity during semantic evaluation.

A changed ledger identifier under an unchanged receipt is rederived from current records. Historical ledger proof is not copied into candidate metadata. Source sequences are exposed for comparison, but no claim is made that an unchanged receipt candidate proves old prose remains correct.

## Independent verification

Ran:

```sh
PYTHONPATH=src:. .venv/bin/python -m pytest -q tests/test_receiving_facts.py tests/test_receiving_answer_coverage.py tests/test_receiving_advisory.py tests/test_live_advisory_gateway.py tests/test_conversation_views.py
```

Result: 117 passing test indicators, exit 0. `git diff --check` also exited 0. The new tests exercise the actual model payload, a two-turn gateway flow without prior assistant prose, wrong-case rejection, changed candidate sets, mixed enclosing-ledger relations, and real AgentPlatform restart persistence without execution/approval/diagnosis changes. This reviewer did not rerun the entire repository suite, perform a live model call or touch any external system.

The parent reports a pre-fix failing model-payload assertion and a prior 113-test run. Those reports are not substituted for this reviewer's executed verification above.

## Nonblocking documentation correction

The design says the new relation view retains “quantity/UOM context.” The emitted relation objects contain receipt/ledger IDs and source metadata only; quantities remain in the original raw source records. Clarify that wording. No need to add redundant fields or expand scope simply to match an overbroad sentence. The source records still provide the context required for actual investigation.

## Held-out release and remaining stop conditions

Implementation was frozen before this review and before the parent read the held-out questions. The independent file may now be released:

`docs/audits/2026-09-09-receiving-heldout-questions.json`

Frozen SHA256: `b36e51fa2529feeef190ae7cda4227eef9bc58b0bcc39b0716d0807c8852419f`.

Retain its questions and expected propositions unchanged during evaluation. If fixture aliases must bind to current ERP IDs, preserve the declared relations and record the binding separately. Record every attempt, latency/token/cost and independent semantic judgment. Three failures of the same mechanism stop that variant rather than authorizing retries until success.

The previous retry-answer omission and false financial-causality explanation are **not resolved by this code-review approval**. Require explicit correct answers, accurate physical-evidence basis, current exact relations, proper ambiguous-reference handling and refusal preservation in the live sequences. Correct source objects alongside incorrect model prose do not pass.

No product edits, commits, pushes, model calls or external actions were performed by this reviewer.

## Live semantic addendum: first complete post-contract R3 sequence

Reviewed after completion at `2026-09-09T22:13:03.793009+00:00`: `artifacts/audits/2026-09-09-finalization-r3-contract-after-1.json`. Internal case is `M20-GOODS-20260909-40-R3`. The artifact's `passed: true` is runtime-contract only. **Independent semantic verdict: FAILED.** No reviewer model call or external action was made; this is inspection of the complete three-turn raw record and attached history.

| Turn | Observed semantic result | Severity |
|---|---|---|
| 1 — compare quantities and missing stock | Main answer correctly reports 40 ordered, 2 received/posted and 38 outstanding, then `safe_next_step` says to verify that the remaining 38 **have been received and posted**. This presupposes completion absent from the source and contradicts the main answer. A read-only verb does not make its premise true. | P1 |
| 2 — refuse changes, verify receipt, retry | Correctly includes both current receipt/ledger pairs and explicitly says not to retry. However it changes the quantity unit to “40 units” and “2 units” when the source is Box. This loses the required business unit and fails frozen exact-UOM acceptance. It also carries an old outstanding-order explanation rather than focusing fully on the new request. | P1 for UOM |
| 3 — history, mean, temporal change, revenue | Correctly gives +2 Box and prior mean 0.67 over 3 observations, and correctly denies financial proof because billed sales/causal evidence are absent. It does not explain the arithmetic distinction requested. “200% increase” is not clearly labeled as a latest-versus-prior-mean comparison. Worse, it appends “The insufficient baseline is explained…” although the attached `received` baseline is AVAILABLE with 3 samples and minimum 3. That sentence is meta-instruction-style output, not an actual explanation. | P1 |

Source history in turn 3: four retained points, current 2, mean 2/3, difference 4/3, percent difference 200%, sample_count 3, minimum_samples 3, status AVAILABLE. The 200% value itself is not an arithmetic error; its unqualified interpretation and missing explanation are the defect. A net temporal increase from zero has no finite percentage denominator. No claim is made that the model explicitly computed a temporal 200% increase; it failed to distinguish the measures as asked.

Recorded latency: 18,756 / 25,139 / 32,751 ms. Recorded cost: USD 0.06222 / 0.0809152 / 0.096324, total USD 0.2394592. All three runtime statuses COMPLETE. Turns 2 and 3 each used one validation retry. The before artifact failed first-turn quantity/UOM validation across three internal attempts and returned no conclusion. This establishes different observed outcomes in one before/after sample; it does **not** establish a stable improvement rate or semantic success.

### Cause and evidence boundaries

- The changed source contract is inspectably better specified and remains independently acceptable as that bounded optimization. The above responses do not demonstrate it fixed conversation behavior.
- A concrete remaining enforcement seam is free-text next-step business premises: existing `validate_advisory` inspects affirmative write language, not whether a read-only suggestion presupposes an unobserved effect.
- Exact UOM checking is activated only by a particular compound ordered/received/posted request. It does not universally type every emitted numeric claim; turn 2 therefore passes despite “units.” Extending regex coverage is not a robust semantic solution.
- Turn 3 reproduces instruction-like fragments from `receiving_focus` concerning all-arrival classification and insufficient-baseline explanation. This is evidence of instruction text entering the answer; it does not prove a unique model-internal cause. Correct history values and AVAILABLE status were present in the attachment, so missing financial or inventory baseline data cannot explain the bogus insufficient-baseline sentence.
- The smallest next design investigation should separate source-derived user-facing facts and action eligibility from open-ended prose, and test whether explanation synthesis still contradicts them. Do not claim this is implemented or validated. Do not add another prompt paragraph, regex collection or same-model critic to turn this run green.

Repeat the frozen scenarios as planned and retain all results; terminate the variant on three failures of the same mechanism. Held-out runs remain a distinct gate. The original code-scope approval stands, while F03 remains FAILED.

## Completed repeated-run review and scoped release decision

All three frozen post-contract attempts were reviewed. No implementation or prompt intervention occurred between these attempts, according to the parent execution record. Only the receiving contract delta above is in this review; concurrent cold-start/configuration/empty-state changes are excluded.

### Attempt 2

Artifact: `artifacts/audits/2026-09-09-finalization-r3-contract-after-2.json`.

Turn 1 completed with correct Box quantities and no attempt-1 presupposition that the outstanding 38 were already posted. Its proposed check concerned expected delivery timing, received-goods quality incidents and current inventory; this is an acceptable read-only direction. Turn 2 failed with AGENT_UNAVAILABLE. The specific recorded cause was **SdkInvocationLimit / limit_total_tokens**, not proof of authentication failure, AWS downtime or disconnected ERP. The failed turn consumed 111,911 input tokens and 4,508 output tokens across 7 requests, USD 0.1039544. Turn 3 was not reached.

Verdict: incomplete, failed full-conversation availability. Turn 1 latency 23,710 ms, cost USD 0.064168. Whole attempted sequence's recorded cost USD 0.1681224. The generic unavailable UI is fail-closed, but the recorded budget exhaustion must remain distinguishable in the audit.

### Attempt 3

Artifact: `artifacts/audits/2026-09-09-finalization-r3-contract-after-3.json`; completed `2026-09-09T22:16:30.579503+00:00`.

All three turns completed. Turn 1 correctly distinguishes 40 ordered, 2 received/posted and 38 outstanding in Box; it names both receipt/ledger pairs. Turn 2 cites both receipt/ledger pairs and explicitly says not to retry. Its direction remains read-only. Turn 3 distinguishes first-to-latest +2 from prior mean 0.67 over 3 samples and latest-minus-mean 1.33, and correctly says unavailable net billed sales means no revenue proof. It does not repeat attempt 1's false insufficient-baseline assertion. This is **one acceptable narrow three-question factual sequence**, not a complete semantic matrix or proof of stable conversation quality. Explanation remains terse and follow-up questions are empty; zero follow-ups are schema-permitted but do not establish the separate useful-follow-up UX requirement.

Latencies: 20,333 / 16,418 / 24,158 ms. Costs: USD 0.062612 / 0.0605128 / 0.094588; total USD 0.2177128. Turn 3 used one validation retry.

### Aggregate and release ruling

| Measure | Observed result |
|---|---|
| Frozen post-contract sequences attempted | 3 |
| Complete runtime sequences | 2 of 3 |
| Narrow three-question sequences without a blocking factual defect in this independent review | 1 of 3 |
| Sequence rejected for semantic defects despite runtime COMPLETE | 1 of 3 |
| Sequence stopped by model token budget | 1 of 3 |
| Recorded post-contract cost across all three | USD 0.6252944 |
| Held-out broader semantic matrix | Not executed in these artifacts |
| F03 stable complex conversation gate | **FAILED** |

Do not present 1/3 as a general success-rate estimate: these are three repeated attempts on one R3 conversation, not an adequately sampled independent population. Their retained prior conversational context may also differ between attempts. No production ROI, framework superiority or confidence interval follows.

**Scoped release decision: APPROVE the receiving contract structure correction for isolated commit/push, with the failures and limits included.** Its independently testable behavior is improved source-basis labeling, exact receipt/ledger relations and explicit scoped reference candidates; the unchanged deterministic guard and write authority boundaries remain intact. It introduces no new writer, grant or claimed business effect. The release title/description must say this is a contract correction and must not say conversation reliability or finalization is complete. Record F03 as FAILED in the tracker. Keep all before/after artifacts including the budget failure. Do not include unrelated cold-start/configuration changes under this approval.

Verified the full-regression XML supplied by the parent: `artifacts/tests/2026-09-09-receiving-contract-full.xml` contains 1,562 tests, 0 failures, 0 errors, 0 skipped, duration 99.206 seconds. This reviewer inspected that artifact rather than rerunning the full suite; the independent 117-test run is documented above.

Stop this three-attempt variant now as planned. The evidence supports further diagnosis of free-prose contradiction and token-budget behavior, not another identical retry or a larger budget without evidence. The successful third attempt does not erase the preceding semantic and availability failures.
