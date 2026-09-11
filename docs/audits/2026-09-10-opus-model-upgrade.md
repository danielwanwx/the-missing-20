# Opus 4.6 operations model upgrade

Status: model-switch implementation reviewed; bounded business-answer improvement
demonstrated. Continuous seven-question acceptance is not claimed.

## Scope

The user requested a stronger Bedrock model before further framework changes.
The operations dialogue and contract-allocation selector can explicitly select
`us.anthropic.claude-opus-4-6-v1` with
`MISSING20_DISTRIBUTOR_MODEL=opus46`. Unconfigured launches retain Nova; the
recording runtime explicitly selects Opus. The original main dialogue prompt, source
delivery and conversation manager remain unchanged. Photo extraction and the
separate legacy receiving/advisory gateway are outside this change.

Each operation creates a fresh model factory and budget ledger. Opus has a
separate persisted conversation namespace; existing Nova sessions retain their
identity. Invalid model selections fail rather than falling back.

## Access and cost evidence

Initial tiny Converse calls to Sonnet 4.6 and Opus 4.6 returned successfully.
The first approved case comparison subsequently failed before inference because
the account lacked the Anthropic use-case form. AWS documents that initial calls
can temporarily succeed while access is being established. A successful tiny
call was therefore insufficient evidence of stable model access.

The one-time form was submitted with the truthful independent hackathon project
name, public repository URL and demo use description. The API returned HTTP 201,
and readback confirmed the form existed. The public usage-based Opus agreement
request returned HTTP 202; later availability readback reported AVAILABLE.
No provisioned capacity was purchased. Subsequent inference still returned the
use-case propagation error, so further calls were paused for the stated interval.

AWS's public offer rate card for Oregon reports USD 5.50 per million regional
input tokens and USD 27.50 per million regional output tokens. Usage-based
estimates are not a billing statement or proof of credit eligibility.
The user explicitly approved sending the retained demo ERP snapshot and seven
questions to Bedrock in `us-west-2`, using the `missing20-dev` profile, with
USD 3 total for this comparison. The diagnostic aggregate cap is separate from
the product's per-operation budget; spending must be summed across test turns.

## Verification boundary

Independent implementation and capacity reviews passed. Fifty-one focused budget
and operations tests passed; the final configured-spend-cap wiring additionally
passed all 43 operations tests. Ruff and formatting checks passed. These are
offline checks and do not establish answer accuracy. The initial access failures
returned no answer and reported zero model tokens.

Compare the retained failed first question using the existing isolated N4
candidate, then prefer a model-only comparison on the original main N1 runtime.
Preserve every result and keep the answer oracle outside model input. Do not
promote the previously failed N4 framework merely because its model changes.
Recording readiness and repeatable multi-turn acceptance remain separate gates.

## Real comparison results

After propagation, isolated N4 first-question inference passed its bounded
semantic review (USD 0.121022). More importantly, the original main N1 runtime
with only the model changed passed questions 1–4: carton/part chronology, customer
allocation, sample versus whole-lot quality, and limits of supplier attribution
and physical-delivery evidence. Those four calls cost USD 1.293105.

Continuous question 5 reached the original 1,551-token response limit and failed
with `MaxTokensReachedException` (USD 0.635019). Its partial session is preserved;
it was not continued or counted as a passing answer. Opus alone was then given
a larger explicit response capacity while Nova's default remained 1,551. The
generic budget boundary permits explicit overrides up to 4,096 tokens and still
enforces the configured ledger limit.

A fresh-session question-5 capacity test completed with 1,847 output tokens
(USD 0.169675). Capacity passed, but semantic review did not: the answer counted
18 Jira interactions where the source had 19, and associated a Slack message
with a reinspection that occurred later. Actual linked IDs and the distinction
between completed fulfillment and unresolved responsibility were correct.
The first video should show the linked records directly rather than ask the
model to reconstruct every external message's contents and timing.

A separate two-turn finance test answered question 6 correctly (USD 0.136763).
Question 7 asked for Chinese; its financial substance was correct, but its Chinese
output was rejected by the existing English-only guard (USD 0.2538305). This is
a model language-following failure with a functioning output guard, not a
successful English answer. The user then clarified that all recording/test
questions for this submission version must be English: this adversarial language
test is outside the V1 recording gate and must not block that scoped delivery.

Total recorded diagnostic inference before final UI verification:
**USD 2.609415**, leaving **USD 0.390585** of the approved USD 3. No ERP
mutations or external notifications were performed by these dialogue tests.
Reports remain private in `/private/tmp/m20-recording-candidate-reports/`.

## V1 recording scope

The user prioritizes a first submission now over broader reliability or new
features. V1 is an English walkthrough of the completed PO19 business case,
showing actual demo-tenant receipts, inspection/hold/release evidence, customer
contracts, native shipment documents, declared synthetic confirmations, and
same-case Airtable/Jira/Slack records. It is a repaired completed-case walkthrough,
not a claim of an uninterrupted first-pass autonomous run. Final live UI checking
is separate from the preserved PO18 comparison above.

The final English UI question initially returned HTTP 500 before any assistant
response was persisted. Offline reconstruction confirmed a 63,195-byte request required a conservative
USD 0.4320525 input/output reservation, exceeding the remaining-spend cap of
USD 0.39. The request stopped before model inference and added no inference cost.
This failure is not a verified live answer and must not be substituted with a
canned answer. The failed user-only session was archived, and the recording
runtime retains its normal USD 3 per-operation cap without another inference.

V1 may use clearly labeled previously captured real English Bedrock answers
alongside the completed-case walkthrough. Those PO18 diagnostic answers must not
be presented as live answers about PO19. A new live question is optional and
outside the exhausted comparison budget; it is not a gate for this scoped
walkthrough. After restoring the normal runtime cap, a fresh browser view returned LIVE SOURCE
for PO19 with 40 received, 40 dispatched, 40 synthetic confirmations and zero
active alerts; the chat was empty and no new inference was requested. Initial
source loading was slow, so allow it to finish before capture. Video
recording/upload, final submission, and judge access have not been completed by
this model upgrade.

## Sources

- [AWS model-access setup and propagation](https://docs.aws.amazon.com/bedrock/latest/userguide/model-access.html)
- [AWS Opus 4.6 model card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-opus-4-6.html)
- [AWS model agreement offer API](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_ListFoundationModelAgreementOffers.html)
