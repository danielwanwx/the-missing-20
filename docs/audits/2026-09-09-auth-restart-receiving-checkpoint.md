# Receiving authentication and restart checkpoint

## Scope and verdict

This checkpoint resumes the existing R2 receiving case, PO `PUR-ORD-2026-00014`,
without reseeding its database or retrying the uncertain Jira creation. It is not
whole-product acceptance, production certification, or an award prediction.

Loop contract: inspect source identity → reconcile the old Jira marker → reload
credentials → verify existing receipt after controlled restart and replay → run
real read-only dialogue → review evidence and correct misleading presentation.
New independent ERP/Jira business writes remain paused for scoped confirmation
after the tool safety reviewer rejected an empty-create permission probe.

## Observed results

- Jira QRC project GET succeeds. Account permissions report browse, create,
  comment and transition capabilities. These account permissions alone do not
  prove that the token can execute each write endpoint.
- Exact marker `m20-review-ca9cbbbca32747f8156ffdea515a7a1b` returns no issue.
  The original R2 create remains UNKNOWN; it was not resent or reset.
- AWS initially returned `LoginRefreshRequired`. A fresh same-device login
  completed successfully, then STS verified `Missing20DeveloperRole` in the
  expected project account. No credentials or authorization URLs are retained.
- Controlled restart preserves one submitted `MAT-PRE-2026-00004`, one +1 Box
  stock effect, Slack message `1788965506.082209` and Airtable record
  `recgbi4HC41a3r3hQ`. ERP's later SLE name is `MAT-SLE-2026-00024`; the
  voucher, line, item, company, warehouse and quantity remain unchanged.
- Three repeated submissions preserve the same receipt and capture version 7.
  Re-uploading the posted photo is rejected with HTTP400. Fresh external GETs
  after replay verify no duplicate receipt, stock or notification effects.
- Ordered 40 Box, posted 1 Box, outstanding 39 Box. The outstanding order is
  not evidence of loss. No invoice, payment or revenue was created.

## History investigation: preserved failure, corrected test window

The first restart comparison failed against a baseline recorded at 15:17 UTC:
one historical point had become five. Inspection of the append-only history
identified DEGRADED/CONNECTED pairs at 16:45–16:46 and 17:01 UTC, all before
this session's restart. They record source outages/recovery, not four receipts.
The failed comparison remains in `2026-09-09-r2-control-receipt-readback.json`.
No assertion or historical row was changed to make it pass.

A new adjacent pre-restart baseline and controlled restart both have five
observations; the subsequent replay still has five. The new evidence is
`2026-09-09-r2-auth-refresh-restart-readback.json`. Its before/after/replay
phases passed and retain external record identities and stock semantics.

## Real Agent evidence

`2026-09-09-r2-post-auth-real-conversation.json` retains the authentication
failure; it is not a model-quality failure or a passing run.
`2026-09-09-r2-auth-restored-real-conversation.json` contains one complete
three-turn real Strands/Bedrock run: all COMPLETE, all NEEDS_EVIDENCE, no writes,
no application validation retries. The model distinguishes the one posted
arrival from the unresolved arrival, preserves refusal, and attaches actual
history. This is one sequence, not statistical reliability.

The history answer's phrase “1 Box received per observation” is ambiguous:
these are repeated snapshots of the same receipt after outages, not separate
deliveries. It correctly reports zero net change and an insufficient baseline,
but the wording still needs refinement before a polished demo. No causal labor
savings or revenue-uplift claim is supported.

## UI correction and boundaries

Actual Chrome interactions covered Dashboard → Investigation and the displayed
receiving state, source records, photo gallery and history. The Dashboard agent
rail incorrectly said “Incident detected” for an unposted receiving review.
It now says “Receiving needs review” / “Monitoring receiving”, with active
investigation and recovery states retaining priority. Empty diagnosis statistics
are hidden until a finding exists. A regression test reproduced the old label
before the change and passes afterward; all 98 Node tests pass.

This is a functional status-semantics check using the existing plain JS/CSS UI,
not a whole-interface typography, surfaces, motion, icon or performance audit.
No styling framework, animation or hidden synthetic data was added. Larger
layout changes and removing business metrics were not needed for this defect.

## Remaining gates

1. Explicit scoped approval for the new independent demo order, two one-Box
   receipts and QRC task lifecycle; never repurpose the old UNKNOWN attempt.
2. Actual same-capture Jira create → evidence comment → verified receiving
   recovery → Done, with independent external readback and restart/replay.
3. Stronger multi-turn explanations of source authority, stale-plan cause and
   snapshots versus incremental receipts; repeat complete runs without selecting
   the best turns from failures.
4. Broader physical holdout and complex quality/overreceipt/ACK-loss acceptance.
   Existing offline tests are not proof of these real external scenarios.

User-facing conclusions must not describe these remaining gates as complete.

## Independent review and incremental correction

The independent reviewer approved the scoped UI change and the receiving-only
prompt corrections, while keeping whole-product and complete answer-quality
acceptance **HOLD**. Review found no new authority or unsafe-write regression.
The prompts now explicitly require answers to each requested decision, use
source UOM, prohibit treating repeated snapshots as deliveries, and distinguish
missing financial evidence from a demonstrated financial outcome.

`2026-09-09-r2-complete-answer-real-conversation.json` retains a second complete
three-turn run. All three turns passed the runtime contract without writes or
application validation retries. Turn 1 now addresses outstanding versus missing
stock; turn 2 explicitly says retry is unnecessary. However, turn 2 still omits
the requested exact ERP receipt/ledger identifiers, and turn 3 still omits the
two comparable prior observations versus three required and the arithmetic
distinction from net change. Turn 1 should say that outstanding balance **alone
does not prove** missing stock, rather than categorically rule out missing stock.
These omissions were not relabeled as passes. The executed prompt temporarily
allowed 120 words; the final source harmonizes back to the existing structured
schema's 80-word instruction. This artifact is not exact-final-prompt acceptance.

The full offline regression in a loopback-enabled environment passed **1,526
tests, no failures/errors/skips**, in 99.958 seconds. The first sandboxed run is
retained separately: local HTTP socket permission failures and a stale package
digest prevented it passing. The digest was regenerated locally after source
changes, rather than weakening its consistency check. Targeted receiving tests
passed 113 checks, the full Node suite passed 98 checks, and Ruff/diff checks
passed. These are code checks, not evidence that Jira writes succeeded.

Restart proof preserves the eight dialogue turns present at its baseline.
The later three-turn sequences were completed after that checkpoint; this report
does not claim a fresh restart/readback proves persistence of every later turn.

Browser follow-up caught a fixture omission: the real initial diagnosis uses
`finding=NOT_EVALUATED`, not an absent finding. The first UI patch hid statistics
only in the latter case. The test was changed to the actual backend initial
state, failed, and the condition was corrected. A newly loaded Chrome page
confirmed the receiving-specific lifecycle label; the server serves the updated
JavaScript with no-store policy. An already-open older tab continued rendering
its previous code until full navigation, so it was not used as new-version proof.
After full navigation, Chrome's accessibility tree again showed “Receiving needs
review” and the live ledger sequence 314. A separate DOM selector check timed
out; therefore hidden-statistics behavior is verified by the rendering regression
test, not claimed as independently confirmed by that browser selector check.
The last initial-state refinement and 80-word prompt harmonization are covered
by the final targeted checks; the 1,526-test run preceded those small refinements.
