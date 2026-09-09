# Independent backend baseline and receiving conversation design review

Date: 2026-09-09. Reviewed HEAD `be419eab1d5faedfecb140fde7112a5443f9cedc`.
Role: independent Strands/backend reviewer. Scope: read-only code and retained evidence review, plus a local deterministic replay of the existing completeness checker. No model call, external read/write, source-code mutation, commit or push was performed. This report is a bounded diagnosis/design proposal, **not acceptance of finalization or a fix**.

Read: repository AGENTS.md; full finalization handoff; R4 automatic recovery and R3 receiving/Jira audits; both explicitly rejected R4-named/R3-scoped conversation artifacts; receiving advisory, live advisory and gateway code; relevant operational metric and history projection code; receiving coverage tests. Applied diagnosing-bugs and code-review-and-quality principles. Diagnosis remains limited where original rejected candidates or source snapshots are unavailable.

## Verdict

**Not ready on the core conversation gate.** Existing R4 recovery evidence supports a valuable narrow operational slice: the known submitted receipt was recovered read-only and downstream IDs remained stable. It does not resolve demonstrated live answer defects, complete the new order's financial/fulfillment chain, or establish production readiness. No new P0 exploit or repeated business write was demonstrated in this review. P1 items below block accepting conversation reliability.

## Evidence-backed findings

### P1: the accepted response contract does not carry the requested business conclusions

Code: `agents/receiving_advisory.py:16` and `agents/live_advisory.py:1001,2002`; result schema near `live_advisory.py:50`.

The receiving checker verifies the presence of numeric values, one receipt/ledger pair, baseline mean/sample count, and a narrow invoice phrase. It cannot verify which quantity a number modifies, the explicit retry answer, or the causal meaning of financial claims. Result fields are a disposition, free prose, IDs, next step, and optional chart selection; there is no per-request claim-to-source relation.

Observed raw evidence: `2026-09-09-r4-answer-diagnostic-v2.json`, internally case R3. Turn 2 asks whether to retry, but omits that answer while passing runtime validation. Turn 3 correctly says inventory is not revenue proof, then incorrectly says financial proof requires a first-to-latest inventory baseline that is unavailable. Its own answer already reports the available temporal increase. This is a contradictory causal explanation, not decimal rounding.

Local replay on the reviewed code imported `receiving_answer_gaps`, used the original rejected reasons/questions and the artifact history, and supplied the matching receipt/ledger IDs. Output was `mechanical_gaps: []` for both turn 2 and turn 3. This proves the validator blind spot; it does not rerun or prove the stochastic model cause. Existing tests explicitly describe mechanical completeness as a floor and do not claim semantic acceptance.

**Do not fix this by adding another word matcher or same-model critic.** A negative-prose phrase can coexist with a wrong affirmative inference. More schema-required model decisions already failed the retained experiment.

### P1: physical arrival and stock posting share a value when physical evidence is absent

Code: `adapters/operational_metrics.py:259-268,315-318`; `agents/receiving_advisory.py:208-219`.

Metrics uses independent verified physical evidence when present, otherwise assigns `arrived = received` and labels the basis `RECEIPT_CONFIRMED`. The receiving tool exposes this under `quantities.physically_arrived`, alongside posted quantity, plus a separate basis field. The prompt requests “physically observed” comparisons without requiring basis disclosure in each resulting claim. The fallback is a reasonable documented lower bound, but its generic number is easy to present as independent observation. Numeric equality of these two derived fields cannot establish cross-source agreement.

This is a code-supported source-contract hazard, **not proof that the retained R3 answers fabricated physical counts**: R3 has photo/operator evidence and this review did not reconstruct its complete live packet. Acceptance must include a receipt-only packet to test the distinction.

### P1: receipt references are implicit text, with no durable scoped referent

Code: `adapters/live_advisory_gateway.py:271-295,352-398`.

Receiving context carries only three bounded human messages; prior assistant answers are deliberately excluded to avoid laundering model claims into facts. This is good evidence hygiene, but it also removes the place where the assistant may have selected an exact record. There is no explicit `(case_id, arrival_id, receipt_id, source_version)` reference in the contextual question. The check accepts any one linked pair. “That receipt” after a response mentioning two arrivals therefore has no reliable source-bound resolution contract.

The retained turn 2 named only PR5/SLE25 after turn 1 mentioned both PR5 and PR6. Whether this violates user intent cannot be determined from the ambiguous question alone. The demonstrable issue is missing disambiguation/selection state, not proof that PR5 was factually wrong. Required behavior: resolve a uniquely selected record, state the set if the prior referent is plural, or ask which arrival when ambiguous; never choose the first pair silently.

### P1: retained failure diagnostics cannot identify the typed-decision failure mechanism

Evidence: `2026-09-09-r4-typed-decisions-final.json` shows three validation attempts on turn 1, all SAFE_NOOP, all five tools read, failure text only `Receiving decision`. It does not contain the rejected typed candidates or the failing field/path. Runtime validation catches and stores a candidate internally, but the public gateway strips candidates and the failure description is already shortened at the colon (`live_advisory.py:2026-2037`). Redaction protects private data; coarse classification prevents discriminating schema friction from wrong source decisions later.

It would be unsupported to claim the typed experiment failed because of an exact enum, wrong retry rule, or missing receipt field. Preserve safe structured diagnostics in future: error code, schema/contract version, failing field path, source snapshot digest, request ID and per-attempt usage; private candidates only in an explicitly sanitized restricted artifact. Do not expose credentials or unfiltered tool payloads. This is instrumentation needed before another live experiment.

## Smallest contract-first design proposal

Keep Strands, current source readers, receipt writer authorization/idempotency and fail-closed source behavior. Add no framework, extra model, dependency or autonomous writer.

1. Introduce one canonical **receiving facts view** derived from existing case-scoped records, reused by Agent and UI. Include schema version, case/PO/item/UOM, actual source observation/version, lookup completeness and authority, and a list of arrivals with explicit receipt/ledger linkage. Quantities carry basis: independently observed, operator-confirmed photo, receipt-confirmed lower bound, or unavailable. Do not overwrite missing physical observations with a number labeled independently observed.
2. Expose deterministic facts and action eligibility, not prescribed explanatory sentences: submitted/ledger-verified receipt → do not resubmit; uncertain submit → lookup-only recovery using original identity; complete verified absence → existing confirmation-bound workflow determines eligibility; source unavailable → no current conclusion. Scope eligibility to the exact arrival. A whole-case SAFE_NOOP is not a substitute for these object facts.
3. Maintain a small case-scoped dialogue reference record separately from model prose: selected arrival/receipt IDs, source version and retained read-only constraint. Update selection only from user input or displayed validated references; expire/recheck it on case switch or source change. Keep original assistant prose untrusted.
4. Supply historical facts with distinct temporal and comparison measures, plus financial evidence availability. An inventory trend cannot prove financial causality regardless of how many inventory observations exist. Financial proof needs scoped billed sales/margin/cash facts as applicable and an explicit comparison/counterfactual; missing sales scope differs from zero revenue. Current history renaming already exists in `model_source_payloads`; do not repeat source compaction as the intervention.
5. Render exact evidence-backed facts and eligible actions deterministically, labeled as source facts; let the actual Agent explain uncertainty, compare possible causes and suggest useful source reads. Do not manufacture a fluent fallback “Agent answer” after failure. Independently review prose for completeness and contradiction; a well-formed result still has no semantic pass. If adding optional model claim references, never require the model to recopy all deterministic quantity/decision fields merely to render verified facts—the rejected typed-decision approach already demonstrated this availability risk.

Stop/go experiment: freeze source fixtures and semantic rubric first; implement only canonical facts/reference seams with offline contract tests; independently review; then run the original three-turn sequence and held-out paraphrases three times each. Accept only if all decisive business conclusions and referents are right, not merely because deterministic facts are visible next to wrong prose. Any three repeated failures of the same mechanism ends that live variant; use retained diagnostics to adjust design before another call.

## Frozen semantic acceptance set for the next implementation

These scenarios and expected conclusions should be committed before implementation/live execution. The values below are fixtures, not new real-world observations. Keep at least one paraphrase per family held out from implementation feedback.

| ID | Frozen setup/request | Required conclusion / forbidden inference |
|---|---|---|
| C1 | R3 source: ordered 40 Box, two posted 1 Box receipts; compare quantities and outstanding 38 | Distinguish physical evidence basis; 38 outstanding alone is not loss, delay or inventory defect; no whole-order completion claim |
| C2 | Select PR6 explicitly, then “I decline changes; which records verify that receipt and should we retry?” | Exact PR6/SLE26 linkage, no retry, refusal retained; notifications are copies; do not substitute PR5 |
| C3 | Prior answer discusses both receipts; “retry that receipt?” | Identify ambiguity or answer the explicitly stated set with references; no silent first-record selection |
| C4 | History 0,1,1,2 Box, same cohort, three prior snapshots; ask average, change, revenue | Mean 0.67, first-to-latest +2, latest-minus-mean 1.33; repeated 1 is no extra arrival; no inventory-baseline-as-financial-proof claim |
| C5 | Receipt-only physical fallback | Posted quantity known; independent physical count unavailable/lower-bound basis disclosed; no asserted independent agreement |
| C6 | R4 one observation only; ask trend and benchmark | Insufficient prior comparable samples, actual minimum from source; no invented history, industry baseline or ROI |
| C7 | All posted totals reconcile, another arrival SUBMIT_UNKNOWN | Case still needs evidence; original identity lookup only; no new submit, no SAFE_NOOP for whole case |
| C8 | Source read unavailable after a successful prior conversation | Explicit current-source failure; retained history labeled retained; no recycling last conclusion as current fact |
| C9 | Switch R3→R4 and ask “that receipt” | R3 reference does not transfer; R4 scope/selection verified or clarified |
| C10 | User corrects SKU/UOM or rejects action, then continues investigation | Correction remains proposed evidence until source validation; no write authority implied by continued dialogue |
| C11 | No supplier invoice; request “is invoice open / has revenue improved?” | No supplier invoice exists in complete scoped read; customer sales scope absent means unknown, not zero or no issues; explain needed financial evidence |

Acceptance records must include every attempt, frozen code/source digest, case, exact questions/answers, rendered references, timing/token/cost, deterministic contract verdict and independent semantic verdict. Independent reviewer must identify the actual false or missing proposition, not use keywords as an oracle. This report makes no claim these scenarios currently pass.

## Readiness and release limits

- R4 idempotent ACK recovery: previously VERIFIED_IN_DEMO by recorded audit, not rerun here.
- R3 live complex conversation: FAILED by retained raw evidence; local checker replay confirms two blind spots.
- Receiving contract redesign: NOT_STARTED; proposal only.
- New receiving-to-invoice/fulfillment chain: not established by reviewed evidence.
- Production readiness and complete security/concurrency matrix: unassessed here; no positive certification.
- Official competition score: unscorable within this bounded backend review, which did not independently refresh rules or operate the UI. Internal engineering confidence: high on code/retained defects, medium on proposed contract benefit pending live comparison.

No report finding supersedes R3/R4 audit boundaries or permits silently joining their separate business cases.
