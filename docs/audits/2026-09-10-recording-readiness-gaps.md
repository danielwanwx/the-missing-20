# Recording readiness gaps — 2026-09-10

This is the v1 recording and submission gate for the already recorded PO19 business
case. It uses the current repository README, submission tracker, Devpost draft, and
the latest component/dialogue audits. **READY TO RECORD V1 as a bounded completed-case
walkthrough; public video, judge access, upload, and submission are still NOT DONE.**
The accepted PO18 run is retained as historical fallback evidence. V1 uses the
recorded PO19 business case plus one clearly labelled previously captured real
English Bedrock answer from the PO18 diagnostic reports; that answer is model
evidence, not a live PO19 result. V1 does not require new inventory events, live
inference, or an expensive full-case rehearsal.

## Gate result

**READY TO RECORD V1 for the bounded business walkthrough; P0: public video, judge
access, upload, and submission remain incomplete.** The current PO19 page
reports 40 received, 40 dispatched, and 40 explicitly synthetic delivery
confirmations, with customer allocation A25/B15 and no open operational alerts.
The business state is a recorded repaired continuation with a restart, not a clean
uninterrupted first pass. No new inventory event is needed for this v1 walkthrough.
The accepted PO18 business chain remains historical fallback evidence. See the
[component acceptance audit](2026-09-10-final-component-loop-acceptance.md).

The earlier Nova Pro complex dialogue remains a historical failed candidate. In
the six-turn check, one contract turn was correct, but the initial 38/40 explanation was
wrong, two turns returned `UNAVAILABLE`, the synthetic-delivery turn failed to
distinguish LOT-B's planned receipt of 18 from the nominal 20-part capacity
implied by two cartons at 10 each, and the last turn returned HTTP 500 without a
retained body. The planned receipt quantity of 18 is not itself wrong; the
evidence distinction was missing. The audit says the required source records
were available; the failures were reasoning/evidence selection. See the
[English operations integration review](2026-09-10-english-operations-integration-review.md).

A first isolated sliding-window dialogue trial also failed: it completed in
4,099 ms with 7,313 input tokens and got the current total of 40 correct, but
omitted the initial 20+18 receipt and two-part replacement chronology and read
only `read_erp_evidence`. This is a trial diagnostic, not recording evidence.
The recorded PO19 business case is a repaired continuation. Physical events 1–19
are APPLIED, and one separate durable allocation retry is APPLIED. Native readback
reports 40 received, 0 held, 0 missing, 0 usable, 0 allocated, 40 dispatched, and
40 explicitly synthetic delivery confirmations; customer A25 and B15 are
dispatched and no operational alerts remain open. The final B2 remainder is 2
parts: event 17 (`29095525-169d-4098-aef0-ea6cd6cd22c9`) applied pick list
`STO-PICK-2026-00015`, Delivery Note `MAT-DN-2026-00017`, and shipment
`SHIPMENT-00015`; event 18 (`6dded1b1-abbf-4089-9516-64f3eba6ed3d`) pickup and
event 19 (`2262fb5f-16ae-4413-8e14-bbd3a3e217eb`) delivery are APPLIED. The raw
event-19 response is retained privately at
`/private/tmp/m20-recording-business-events/19-delivery-b2.response.json`.
Final same-case handoffs are VERIFIED in Airtable `recWHcDEadZrLyRBI`, Jira
`QRC-4`, and Slack timestamp `1789088499.513429` at 18:01 PDT. These are
synthetic demo records and do not establish physical delivery, invoice, payment,
or revenue.

The earlier event-12 checkpoint remains preserved history: it reported 40 received,
held 0, usable 2, dispatched 38, and 20 synthetic confirmations, with A25/B13
dispatched while inspection and release were APPLIED and B2 allocation remained
PENDING with no B2 pick. The earlier event-6 Slack readback also remains historical:
received 38, held 18, missing 2, dispatched 20, and confirmed 20 Nos. The later
events and retry supersede those business counts without erasing that failure
checkpoint. The reviewed runtime was restarted on the same case after event 16
(session `70363`), so this is an explicit repaired continuation rather than a
clean uninterrupted recording pass.

Native dialogue candidates n2, n3, and n4 remain historical failed trials. The
explicit Opus 4.6 comparison passed Q1–Q4 semantic review. Q5 reached the 3,072
token capacity fix but retains known detail errors in its external-record timeline
and count, so it is outside the v1 hero path; show direct linked records instead of
asking the model to enumerate many Slack milestones. The Chinese adversarial Q7 is
out of scope for this English-only v1 and does not block it; preserve its historical
language-following failure without claiming a full seven-question continuous pass.
The exact Sonnet 5 comparison made one diagnostic-only Converse attempt and returned
`AccessDeniedException`; it reported zero input/output tokens, no inference and no
semantic result. The catalog and availability metadata appeared active/authorized,
but the agreement was `NOT_AVAILABLE`, so metadata did not prove account invocation
entitlement. No fallback or promotion followed. See the
[dialogue acceptance contract](2026-09-10-recording-dialogue-acceptance-contract.md).

The saved Devpost record still has no video URL. The local draft points to the
recorded PO19 case while retaining historical evidence. The recorded Opus 4.6 Q1–Q4
answers from the PO18 diagnostic reports provide a real English answer for the
bounded walkthrough; label it as captured PO18 Bedrock evidence rather than a live
PO19 query. No new inference is required for v1. A live agent question is optional
and requires a separately authorized budget. The remaining submission work is synchronized materials, public video,
judge-access, upload, and submission checks.
The latest live-query attempt was rejected before model invocation because its
3,072-token reservation exceeded the remaining runtime cap; it incurred no model
charge and does not block this recorded v1 scope.

## Official hard gates checked on 2026-09-10

The authoritative sources are the [official rules](https://agentsforhumans.devpost.com/rules),
the [official FAQ](https://agentsforhumans.devpost.com/details/faqs), the
[official dates](https://agentsforhumans.devpost.com/details/dates), and the
organizer's [stand-out guidance](https://agentsforhumans.devpost.com/updates/45987-how-to-actually-stand-out-in-agents-for-humans).
All were accessed 2026-09-10.

V1 recording readiness is separate from submission and access readiness. The
public video, functioning project or test-build access, final package/access
verification for the public repository/README and visible MIT or Apache license,
Builder ID, upload, and final submission remain outstanding; this audit makes no
award or full-seven-question claim.

| Gate | Exact requirement | Current state / recording implication |
|---|---|---|
| Deadline | Submission closes **September 14, 2026 at 5:00 PM PDT** (September 15, 00:00 UTC). Judging runs September 15, 9:00 AM PDT through October 8, 5:00 PM PDT. | The repository's September 12 freeze is an internal target, not the official deadline. Preserve buffer for upload and access testing. |
| New project and Strands | Build a new AI agent with **Strands Agents** during the submission period, doing real work end-to-end, and install/run consistently as depicted. Pre-existing work must be disclosed. | Name Strands in the description, Built With, architecture, and video. The recorded English answer uses the explicit Bedrock Opus 4.6 path; do not present the separate AgentCore Runtime proof as the UI's runtime path. |
| Public code | Public GitHub/GitLab/Bitbucket repository containing source, assets, and setup instructions; README required. | The repo is intended to be public. Recheck the final remote repository from a clean browser and make the recorded PO19 walkthrough the primary README path. |
| License | A visible **MIT or Apache** license is required in the repository and its About section. | The README claims project source code is MIT. Third-party photo fixtures retain their individual CC/public-domain terms and attribution, so check the public asset and attribution presentation before submission. |
| Architecture | Diagram must show user input/interface, Strands agent loop, tools/integrations, AWS services, and output. | The English architecture asset exists. Recheck that the diagram and caption describe the recorded PO19 walkthrough and do not mix historical IDs or counts. |
| Video | A public YouTube or Vimeo video, **maximum five minutes**, showing a working demo and explaining the problem, who it is for, and why it matters. Slides, screen recording, and voiceover are allowed. | The URL is still pending. Record the working bounded flow, upload publicly, play it from a clean browser, and confirm duration before entering the URL. |
| AWS / Strands setup | AWS account and Strands Agents SDK are required to enter. AgentCore is encouraged and can strengthen Technical Implementation, but is not required. | Current direct Bedrock/Strands path is eligible if shown accurately. Do not claim Gateway/Policy or AgentCore UI routing that was not proven. |
| Builder ID | An AWS Builder ID is required on the submission. | Enter the Builder ID email directly in Devpost; do not put an account email in the repository or video. |
| Judge access | Provide a website, functioning demo, or test build. Access must be free and unrestricted through judging; if private, put login credentials in testing instructions. Judges may rely only on submitted text, images, and video. | Test the exact public URL/repo and instructions as a fresh judge. A developer-only local loop is insufficient evidence of access. |
| English | Submission materials and demo materials must be English, or have an English translation. | Keep all visible labels, README, architecture, testing instructions, and voiceover English. The current image audit found the known historical Chinese architecture capture and its replacement; do not reintroduce the old asset. |

The rules also describe an optional **$50 AWS Promotional Credit** request. The
request form deadline is September 11, 2026 at 12:00 PM PT, while supplies last;
credits expire October 31 and any extra charges remain the entrant's
responsibility. This is an account-support option, not a submission gate.
The optional Builder Journey bonus can add up to 0.6 points if the public
builder.aws post is live before the deadline and uses “Agents for Humans” in its
title. It should not displace the P0 recording work.

## P0 recording checklist

- [ ] Record the existing completed **PO19** story: 40 parts received/dispatched, A25/B15, synthetic delivery confirmations, and no invoice/payment claim. Keep the accepted PO18 run labelled as historical fallback evidence.
- [ ] Verify the current page and private readback; do not create new inventory events, replay applied events, or run a full clean-case rehearsal for v1. Label the business history as a repaired continuation with a restart.
- [ ] Show the recorded contract decisions and native readbacks, including exact quantities and record identifiers. Use direct Airtable/Jira/backend evidence for final quantity 40; the Slack notification does not visibly prove the final total.
- [ ] Show one clearly labelled previously captured real English Bedrock answer from the PO18 Opus Q1–Q4 diagnostic reports about synthetic delivery evidence and physical receipt. Label it as PO18 diagnostic evidence, not a live PO19 answer. No new inference is required; a live agent question is optional and separately authorized. Exclude Q5's known external-record detail errors and the out-of-scope Chinese stress test from the hero path.
- [ ] Show Strands doing real work and name it in the video, description, and Built With. Keep model advice, deterministic policy, verification, and execution boundaries visible.
- [ ] Synchronize the public README, architecture, testing instructions, and Devpost copy with the recorded PO19 walkthrough. Keep the accepted PO18 run and old 20-unit story clearly labelled as historical fallback evidence before recording.
- [ ] Verify the public repository, visible MIT/Apache license, third-party fixture attribution, and clean setup from a separate browser. Scan the public tree for API keys before submission, as the organizer advises.
- [ ] Produce an English YouTube/Vimeo video under five minutes, test playback without local-only state, and ensure the opening states the problem, audience, and concrete value.
- [ ] Verify free judge access through October 8, 2026, including any required login credentials and a deterministic reset/test path.

## Current gaps that affect competitiveness

The strongest competitive evidence is a specific operations problem with real
cross-system work: the Strands agent coordinates quality and fulfillment
exceptions across ERP, Airtable, Jira, and Slack, while deterministic controls
keep quantities, approvals, provenance, and synthetic evidence explicit. This
supports the official criteria for Technical Implementation, Design, Potential
Impact, Creativity, and Presentation.

The same criteria are exposed by the present gaps:

- **Presentation and design:** the video is missing and the saved Devpost copy
  is stale. A judge must be able to follow one complete current story without
  reconciling two case versions.
- **Technical credibility:** Opus 4.6 passed Q1–Q4 semantic review, while Q5
  retains external-record detail errors after the capacity fix. Use one bounded
  captured English answer and show direct linked records; do not imply production-grade
  seven-turn conversational accuracy. The business history is repaired, so
  preserve that limitation in narration.
- **Impact claims:** delivery confirmations are synthetic, invoices and
  payment are missing, and the order values are not revenue. Avoid ROI or
  physical-receipt claims. The current source values are PO $160 and SO $150/
  $90; they are not the historical $42,000 figure.
- **Responsibility claims:** the model's shortage explanation was unreliable;
  do not attribute supplier responsibility or causality in the recording.
- **AWS story:** AgentCore is optional. A precise Strands/Bedrock description
  is stronger than claiming unproven AgentCore Gateway, Policy, or UI routing.

## Material contradiction: historical 12/8 versus current 25/15

These are deliberately different evidence cases. The accepted PO18 chain is the
historical fallback; the recorded PO19 case is the active v1 walkthrough with a
repaired business continuation. Keep them separate in the submission.

| Material | Historical case | Current recording case |
|---|---|---|
| Customer quantities | 20 units: 12 accepted and 8 held | Recorded PO19: 40 parts received/dispatched/synthetic-confirmed, with customer allocations A25 and B15 |
| Commercial story | Historical downstream order shown as $42,000 | Prepared PO19 source values are PO $160 and SO $150/$90; invoice groups are missing and there is no payment |
| Evidence status | Historical architecture/demo evidence | PO19 has a repaired continuation through events 1–19 plus one separate applied retry; final business readback and a clearly labelled captured PO18 English Opus Q1–Q4 answer are available for v1 |
| Recording rule | Keep as a clearly labeled historical appendix only | Walk through the recorded PO19 evidence with the captured answer clearly labelled as prior Bedrock evidence; use PO18 only as clearly labelled fallback evidence |

Mixing “12 accepted/8 held” with “A25/B15” makes the business result
unverifiable and weakens both Design and Presentation. The final recording
should open and close on the recorded PO19 case with the captured English answer
clearly labelled; PO18 and any retained
historical screenshot must be captioned as fallback evidence and never used to
support the current recording case's quantities or commercial outcomes.
