# English operations integration review

Status: scoped interface/chat-language verification passed; structured-output follow-up verified locally; final remote CI pending. This is a scoped interface/language review,
not a successful complex-conversation or submission-readiness declaration.

## Changes under review

The current distributor page uses the approved silver/white styling. It presents
current stock separately from cumulative receipt, pick, dispatch and recorded
confirmation facts. Active exceptions link from the affected stage to their
matching evidence; resolved alerts remain accessible as history. The last
retained allocation decision is distinct from a current zero-additional plan.
Customer targets and observed quantities form a case-scoped comparison; any
missing customer commitment makes that comparison unavailable. Historical,
industry and savings baselines are explicitly unavailable.

Chat is near the top with an Ask agent anchor. Native document details remain
available in a scrollable list. Browser-native English dictation populates the
question without submitting; read/stop controls require an explicit action.
Changing or clearing an answer cancels active speech. Visible-only polling is
30 seconds, does not overlap reads, and reports the last successful source refresh.
Configured source failure differs from an unconfigured workspace and retains
case identity, disables actions and offers Retry without current-data claims.

Native and legacy model-authored prose passes an English/Latin-script display
boundary. Latin names and typographic punctuation remain supported; non-Latin
output is rejected rather than translated or shown as successful. This is not a
linguistic classifier for every language using Latin letters. The model prompt
requires English independently of input language. Existing native session history
survives the exact prior-prompt migration; unknown restored prompts are rejected.
Private raw SDK snapshots can retain rejected output before display validation.
They are not published product answers and are not included in the release.

The native distributor source packet now includes current financial evidence,
the retained allocation decision and up to 64 physical events with explicit
history completeness metadata. These facts are source-derived, not answer keys.

## Independent review and corrections

Independent backend review accepted the English/source boundary. Primary also
compared the migrated prompt with the actual prior Git source using AST evaluation;
they matched. An initially reported trailing-space migration concern was disproved
and explicitly withdrawn by both reviewers.

Independent UI review found two defects: partial missing commitments were omitted
from the denominator, and replaced answers could continue speaking stale content.
Both were fixed, regression-checked and accepted on re-review. Primary browser
inspection additionally found source-unavailable was labelled unconfigured; the
current source-state correction is separately exercised in the synthetic fixture.

## Retained real-model failures

Six HTTP turns were attempted in the same real Nova Pro session against PO18.
The seventh planned language-override question was not run in that sequence:

| Turn | Observed outcome | Wall time |
| --- | --- | --- |
| 1 | Current 40-part totals correct, but initial 38/40 explanation wrong and unsupported alternatives introduced | 36.53 s |
| 2 | A25/B15 and date-first contract explanation correct | 97.32 s |
| 3 | UNAVAILABLE after successful source reads, no terminal answer retained | 54.82 s |
| 4 | Synthetic-versus-physical distinction stated, but original expected quantity incorrectly described as 18 | 60.85 s |
| 5 | UNAVAILABLE | 56.92 s |
| 6 | HTTP 500; response body was not retained by the diagnostic client | 38.80 s |

These attempts fail complex-conversation acceptance. Independent inspection found
all 19 events available on turn 1; its failure was reasoning/evidence selection,
not absence of the original 20+18 counts and later two-part replacement. Turn 3
had no final answer to reject for language. The wrapper discarded the underlying
exception type, so its precise failure cause is unproved. Growing repeated source
snapshots are a demonstrated risk: retained provider input counts included 23,408,
68,023, 90,755 and 124,248. This does not establish a specific context-limit cause.
The application must not claim this conversation is fixed or uninterrupted.
Raw attempts are private under `/private/tmp/m20-english-dialogue-acceptance`.

Two separate minimal synthetic language probes used actual Bedrock Nova Pro.
Both raw model responses contained Han characters despite the instruction. The
first probe had an additional diagnostic file-permission mistake that prevented
it from reaching display validation. The corrected second probe reached the actual
boundary and returned `NativeReceivingDialogueError: native receiving answer
violated English-only output`; no Chinese answer was returned to the product.
No invoice follow-up or business effect occurred. Observed incremental engineering
estimates were USD0.0009696 and USD0.0009776, not AWS billing statements. Raw reports
are private under `/private/tmp/m20-english-language-probe`.

## Historical representation

The archived candidate source containing six Han regex characters is normalized
to equivalent Unicode escapes, preserving regex behavior. It is not rerun or
newly accepted. Its original Git blob is `95ed2f60d0b82b10441a9ab9fb2842564f6c6931`.
Original SHA256: `90e68f01350c8c2f4bbb0043978bf214b5fb974f499d387afdcc2a0944be126a`.
Normalized SHA256: `51b83439c08fb8ba3107b24dd722452bc3e286125e134071bb393025fe7ddb6f`.
Historical raw evidence remains distinct from translated documentation and
reproduced presentation images.

## Final local verification

`make check PYTHON=.venv/bin/python` exited 0: 1,986 Python tests, 131
JavaScript tests, formatting/lint and mypy (51 source files) passed. Browser
inspection covered the real PO18 completed case and separately labelled read-only
fixtures for active inspection failure, partial dispatch, missing comparison target
and configured source failure. The problem node links to its alert evidence; Retry
is available for source failure. The business event count remained 19.

All tracked UTF-8 text files have zero literal Han characters after translation
and equivalent Unicode-escape normalization. A local Vision OCR pass succeeded
for 121/121 tracked images; its only reliable multi-character Han match was the
old architecture capture, now replaced by an English browser capture. Low-confidence
isolated OCR artifacts were reviewed separately. OCR can miss small or faint text.
Private/untracked historical records and raw model snapshots were not rewritten;
this is not a claim that every historical file on disk contains no Chinese.

The new capture reproduces the historical architecture, not new evidence of
complex-conversation acceptance. English architecture labels were shortened to fit
nodes while details retain their meaning. Hardware microphone capture and audible
playback remain unverified; automated voice lifecycle checks passed.

The private competition package audit also passed using the repository Python
runtime. Its historical PRIVATE_READY_TO_BE_JUDGED status does not override the
failed current complex-conversation evaluation.

Final independent read-only review returned GO for this scoped release, with no
blocking defect. It specifically rechecked configured source failure versus
unconfigured state, English rejection, and the retained semantic-failure claims.

## Structured-output follow-up

A final inventory identified two more displayed model-prose outlets beyond chat:
allocation rationale and photo visibility/assessment prose. They were not guarded
in the first commit, so its scoped GO does not establish universal agent-output
coverage. They are corrected with the same English instruction and rejection
boundary, preserving literal source identifiers. First slice: `d2f6200eb78fe08c9fc79fa52fc6fac8ab29ac59`,
pushed and remote SHA verified.

First-slice CI34539605310 completed SUCCESS. The follow-up preserves original
item and lot identifiers, including non-Latin source identifiers; English-only
applies to model-authored explanatory prose, not rewriting source evidence.
Primary verification passed 172 focused tests across allocation, photo, operations,
native conversation and advisory. The first local attempt could not bind the HTTP
test socket; the loopback-enabled rerun exited 0. Ruff check/format and diff checks
passed. No additional paid inference or business writes were performed.

Independent cross-reviews returned GO for both allocation and photo changes.
The local demo runtime was restarted with these changes, preserving its existing
case and session storage.
