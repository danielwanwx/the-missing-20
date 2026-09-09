# Real two-arrival receiving regression

## Scope and actual effects

This is an intentionally staged concurrency test in the authorized synthetic demo tenant, not a naturally occurring warehouse incident or production certification. The original normal case (PO13 / PR3) remains untouched. R2 uses PO `PUR-ORD-2026-00014`, forty **Box**, USD50 per Box as an explicit synthetic contract price, with two disjoint preplanned one-Box arrivals. No invoice, payment or revenue was created.

Both original public photos were analyzed by real Strands/Bedrock. Arrival01 used [Box.agr.jpg](https://commons.wikimedia.org/wiki/File:Box.agr.jpg), Arnold Reinhold, CC BY-SA 3.0. Arrival02 used [Cardboard_box.jpg](https://commons.wikimedia.org/wiki/File:Cardboard_box.jpg), MrBeastRapper, CC BY-SA 4.0. The source/byte manifest is retained in the earlier public-photo research. They represent visible carton observations, not proof of actual delivery, hidden contents or a production count-accuracy benchmark.

| Step | Observed result |
| --- | --- |
| Both arrivals: original photo + real ERP barcode lookup | Each model returned one visible carton; operator confirmation bound identity to the exact PO line and photo version. No stock posted. |
| Arrival02 explicit draft and confirmation | PR `MAT-PRE-2026-00004`, docstatus 1, one Box; SLE `95c80e0ebe`, voucher detail `cu1jg5mk13`. |
| Arrival02 handoff | Celigo → Slack and Airtable journal readbacks VERIFIED; a later zero-write external GET readback confirms the same PR/SLE and provider record IDs. |
| Arrival01 draft after Arrival02 changed PO | `NEEDS_REVIEW`, version 4, **no draft attempt, draft document or stock write**. Original photo and candidate retained. |
| Jira creation | UNKNOWN; not accepted. The original provider exception was swallowed by the old journal, so its exact outcome cannot be reconstructed. |
| Jira diagnostic | A later deliberately invalid empty create request returned HTTP401 `Unauthorized; scope does not match`. It cannot create an issue and proves current write authorization is inadequate, **not** that the original exact request had no effect. |

Runtime is `.missing20-goods-20260909-r2`, port8895. `--pause-auto-prepare` only controls this explicit interleaving; normal runtime default is unchanged. No state was reseeded, journal reset, approval bypassed or uncertain external write blindly retried.

## Defects found and corrected

1. The receiving classifier examined reconciled posted stock but ignored another unposted arrival in `NEEDS_REVIEW`. It rejected three reasonable model candidates. The classifier now includes explicit unresolved arrival states; ordinary intake remains normal. Unknown future states fail closed. ERP quantities remain unchanged.
2. A history question could distract the model from the unresolved arrival. The typed synthesis now receives a compact copy of current arrival facts and explicit case-versus-chart semantics, not an expected verdict or fabricated evidence. All failed real runs are preserved; a passing focused run alone does not establish stable multi-turn quality.
3. The handoff journal hid provider failures behind perpetual “checking delivery”. New diagnostics retain only phase/category/HTTP status, without bodies, tokens or personal data. Recovered lookup warnings clear without permitting resend of an UNKNOWN write. Original send uncertainty remains recorded.
4. Receiving views showed incident confidence/manager-gate copy and fictional invoice→Slack connectivity. Receiving source buttons now remain individually inspectable without those false routes; unresolved arrivals visibly require review without manufacturing a stock gap. Jira is a capture/arrival-scoped workflow record, not stock, QA or receipt-notification authority.

## Acceptance boundaries

- `artifacts/audits/2026-09-09-real-receiving-interleaving.json` contains the actual API transitions and immutable observations.
- `2026-09-09-real-stale-order-conversation*.json` retains the complete attempted-run denominator, including policy and model validation failures. Never combine their best turns into a claimed passing end-to-end run.
- The full regression suite is an offline code/browser contract check; it does not substitute for external Jira acceptance or actual-model quality.
- Historical source observations are internal descriptive baselines, not industry benchmarks or measured labor savings. There is no causal revenue uplift proof.

## Required next action

The Atlassian security page requires a fresh eight-digit code sent to the authorized Shrik Gmail account. After write authorization is restored, look up the exact old Jira marker first. If absent, preserve this uncertain attempt; a fresh independent case can test automated issue creation, or an explicitly disclosed operator reconciliation can test recovery. Neither is permission to silently resend the old UNKNOWN.

Whole-product release remains **HOLD** until real exception create/update/resolve, post-recovery external readbacks, replay after restart, and robust complex multi-turn dialogue pass independent review. Damage/quality-release/overreceipt and a physical operator holdout remain separate acceptance cases. No prize outcome is guaranteed.

## Independent final code and focused-model review

**Code disposition: APPROVE for this bounded checkpoint.** The receiving classifier now fails closed for unknown arrival states, elevates only the explicit unresolved states to `NEEDS_EVIDENCE`, retains the exact arrival/photo evidence, and does not alter posted ERP quantities. The browser uses an array boundary before inspecting arrivals, removes incident confidence/manager-gate semantics from evidence-only receiving, and keeps the unresolved state visible without manufacturing a stock gap. Jira receiving rows are case/PO scoped and now retain arrival, capture and operation identity; their role is `RECEIVING_REVIEW`, not receipt notification, QA or stock authority.

The journal correction preserves exactly-once caution. A successful absent lookup clears only an obsolete lookup-phase warning. It does not change `UNKNOWN` to `PENDING`, does not resend, and retains a separate prior send failure when one was actually observed. Verified readback clears the current warning without rewriting the old provider attempt. The old R2 record still has no reconstructed failure cause, as required. Independent targeted reruns passed **73 Python tests** across advisory/platform/handoff/Jira and **18 Node tests** across receiving semantics and background handoff display.

The focused real-model artifact, `artifacts/audits/2026-09-09-real-stale-order-history-focus.json`, is a valid **single-turn safety and grounding pass**, not a complex-sequence pass. It is `COMPLETE`, read all six relevant sources, returned `NEEDS_EVIDENCE`, performed no write, attached the actual one-point history, distinguished one submitted arrival from the arrival needing review, and correctly refused to interpret the 39 unreceived Boxes as loss or revenue improvement. The attached baseline explicitly reports `INSUFFICIENT_DATA`; it does not invent a benchmark.

Its judge-facing explanation is still incomplete. The answer says to inspect Arrival 01 but does not state the retained causal fact that Arrival 02's posting changed the PO version and made Arrival 01's pre-draft candidate stale. It also does not tell the user in prose that only one historical observation exists, so no trend/baseline comparison can yet be made. The prior complex three-turn attempts still fail on their third history turn. Preserve those failures: this focused success closes neither repeated complex-dialogue stability nor Jira acceptance.

**Final scoped disposition:** suitable to commit as a fail-closed classifier, evidence projection, UI-honesty and observability correction. Whole-product status remains **HOLD**. The next accepted evidence must be either exact-marker reconciliation of the original Jira outcome or a fresh independently scoped Jira create, followed by same-capture evidence update/recovery/Done readback and restart/replay; then a complete multi-turn Agent run must explain the stale-version cause and the insufficient-history boundary directly.

## Later facts-focused three-turn and external-read checkpoint

`artifacts/audits/2026-09-09-real-stale-order-conversation-facts-focus.json` supersedes the earlier single-turn quality limitation, but not the retained failure denominator. All three real Nova Pro turns are `COMPLETE`, return `NEEDS_EVIDENCE`, and have `write_performed = false`. They use five current source reads on the first two questions and add the actual operational-history reader on the third. Total recorded latency is 57.097 seconds, total incremental metered cost is USD 0.164424, and the second turn required one bounded application validation retry.

- Turn 1 correctly identifies Arrival 01's PO-change review, Arrival 02's one posted unit and the 39-unit outstanding order balance without calling the balance lost stock.
- Turn 2 preserves the explicit refusal, says external task records cannot authorize stock and requests refreshed PO/receiving evidence. It is safe but incomplete: the question asks which external records actually exist, while the prose does not explicitly distinguish the verified Slack/Airtable copies from the unverified Jira `UNKNOWN` attempt.
- Turn 3 correctly reports one received Box, 39 outstanding Boxes, an insufficient historical baseline, no proof of loss or revenue improvement, and the unresolved Arrival 01. Its attached history contains exactly one retained observation and marks every requested comparison `INSUFFICIENT_DATA`; it does not fabricate a trend or benchmark.

This is **APPROVE as one complete facts-focused complex sequence**. Earlier policy/citation/history failures remain in the denominator, so it is not evidence of repeat statistical reliability. The remaining Turn 2 omission is a judge-facing answer-completeness gap, not an unsafe-write or factual-authority failure.

`artifacts/audits/2026-09-09-r2-control-receipt-readback.json` independently records a zero-write external GET check for control Arrival 02: exactly one submitted `MAT-PRE-2026-00004`, one uncancelled +1 Box stock-ledger effect with matching voucher/line/company/item/warehouse semantics, and the verified Slack-via-Celigo and Airtable provider record IDs. It contains only `before_restart`; it must not be cited as restart/replay proof. It contains no verified Jira record and does not resolve the Arrival 01 exception.

The retained full-regression XML reports **1,526 tests, zero failures/errors/skips** in 118.958 seconds (`artifacts/tests/2026-09-09-r2-release-regression.xml`), and the reported full Node suite is **97/97**. These checks support committing the incremental classifier, journal diagnostics, source projection and UI changes. They do not override the external Jira/MFA gate.

The earlier R2 regression's single failure was a stale private-package digest, not an application assertion; subsequent 1,525-test and final 1,526-test runs passed. The final checkpoint also reports Ruff, private-audit `--check`, and all 97 Node tests passing. A fresh operator screenshot of the port 8895 Investigation view displays `REVIEW REQUIRED` and explicitly says posted stock is unchanged. This UI inspection supports the corrected presentation, but it is not a Jira provider readback.

### Incremental commit verdict

**APPROVE for the scoped incremental commit; whole-product release remains HOLD.** The demonstrated gains are a real two-arrival stale-snapshot stop, a verified control receipt and its two notification copies, honest no-resend handling for the unresolved Jira write, and one complete read-only complex Agent sequence. Still required are fresh Jira write authorization, exact-marker reconciliation of the old `UNKNOWN`, one real create/update/recovery/Done lifecycle, restart/replay duplicate checks, and a further complex run that explicitly enumerates verified versus unverified collaboration records. No award outcome is implied.
