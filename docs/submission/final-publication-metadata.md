# Final publication metadata — LogisticPilot — The Missing 20

Status: prepared for review. The video is not published, and the Devpost entry is not
submitted.

This file is the final copy source for a public video and Devpost form. It reflects the
completed PO20 same-case demo only. Historical PO18/PO19 records remain historical
evidence and must not be used as the primary story.

## Local publication assets

Upload these repository-local JPEGs to Devpost after final preview:

| Use | Exact local upload path |
| --- | --- |
| Devpost 3:2 hero | `docs/submission/media/logisticpilot-devpost-hero-3x2.jpg` |
| Gallery: Dashboard | `docs/submission/media/logisticpilot-gallery-dashboard-3x2.jpg` |
| Gallery: Agent conversation | `docs/submission/media/logisticpilot-gallery-agent-3x2.jpg` |
| Gallery: Architecture | `docs/submission/media/logisticpilot-gallery-architecture-3x2.jpg` |

Each JPEG is 1500 × 1000 pixels (3:2). The final normalized MP4 is a local artifact,
not a repository asset and not yet a public video:

`/Users/danielwan/Documents/Hackathon/Agents-for-Humans/the-missing-20-film/composition/renders/logisticpilot-final-picture-lock-264.1s.mp4`

It is 264.2 seconds, 1920 × 1080, H.264/AAC. Upload or publish it only after the final
video review in the checklist below.

## YouTube metadata

### Title

**LogisticPilot — Find the Missing 20 and Close the Fulfillment Loop**

### Description

When 40 parts arrive across several lots, a warehouse manager must reconcile a
shortage, a sample quality failure, customer commitments, and records spread across
ERPNext, Airtable, Jira, Slack, and Celigo. LogisticPilot makes that work reviewable:
Strands and direct Amazon Bedrock Claude Opus 4.6 explain the evidence in English;
deterministic application controls validate the plan; a manager approves the supported
operation; and the application reads back the resulting business records.

This recorded demo follows isolated case `M20-DIST-COMPONENT-V2-20260910` on
`PUR-ORD-2026-00020`. LOT-A20 records 20 parts. LOT-B18 records 18 of 20, including a
two-part shortage and sample failure; a whole-lot retest resolves the hold. LOT-C2
records the two-part replacement. Shipments 16–19 dispatch 20, 5, 13, and 2 parts to
fulfill A25 and B15. Same-case Airtable, Jira, and Slack-via-Celigo readbacks are
shown.

All business inputs and delivery confirmations are synthetic demo records. They are
not independent proof of physical receipt by a customer. The PO is USD160; customer
orders are USD150 and USD90. The demo makes no invoice, payment, or revenue-recognition
claim.

Source code and documentation: https://github.com/danielwanwx/the-missing-20

### Tags

`LogisticPilot`, `The Missing 20`, `AI agents`, `Strands Agents SDK`, `Amazon Bedrock`,
`Claude Opus 4.6`, `supply chain`, `warehouse operations`, `ERPNext`, `human in the loop`,
`agentic workflow`, `fulfillment`

## Devpost field map

| Devpost field | Exact value or action |
| --- | --- |
| Project name | `LogisticPilot — The Missing 20` |
| Tagline | `Find the gap. Prove the cause. Close the loop.` |
| Track | `Professional Agents` |
| Project description | Paste the reviewed copy from [`devpost-submission-draft.md`](devpost-submission-draft.md). |
| Repository | `https://github.com/danielwanwx/the-missing-20` |
| Video | Paste the public YouTube or Vimeo URL only after the final exported film has been reviewed. The video must be five minutes or shorter. |
| Live demo | Leave blank unless a stable, freely accessible demo is independently verified through the judging period. |
| AWS Builder ID | Enter in Devpost only. Do not add an account email or Builder ID to the repository. |
| Testing instructions | Paste the exact instructions below. |
| Built with | Select or enter the tags listed below. |

### Testing instructions

Clone the repository and run the credential-free quality gate:

```bash
git clone https://github.com/danielwanwx/the-missing-20.git
cd the-missing-20
cp .env.example .env
make bootstrap
make check
```

For a local read-only product view, run `make case-console` and open
`http://127.0.0.1:8765`. Startup and source inspection do not require cloud
credentials. The recorded PO20 case uses a private isolated demo tenant and is not a
public hosted test environment. Do not configure external credentials or replay its
business events to evaluate the submission.

Read the current case, evidence boundary, and architecture in the README and these
repository records:

- [`video-v1/REHEARSAL-V2.md`](video-v1/REHEARSAL-V2.md) for the scoped PO20 rehearsal.
- [`video-v1/SOL-REVIEW-V2.md`](video-v1/SOL-REVIEW-V2.md) for the independent PO20
  journal review.
- [`../architecture/distributor-operations-recording.html`](../architecture/distributor-operations-recording.html)
  for the interactive current architecture.

The agent is advisory and read-only. A real Bedrock conversation requires an authorized
AWS configuration; it must not be treated as a required public test step or as a path
to operate the private demo tenant.

### Built-with tags

- Strands Agents SDK
- Amazon Bedrock
- Claude Opus 4.6
- Amazon Bedrock AgentCore Runtime (separately proven)
- Python
- Pydantic
- SQLite
- Server-Sent Events
- Vanilla JavaScript
- ERPNext / Frappe Cloud
- Airtable
- Celigo
- Jira
- Slack

AgentCore Runtime is separately proven as a deployment and invocation boundary. Do not
describe it as the current Dashboard execution path.

## Final submission checklist

### Video and public access

- [ ] Export the final English video and verify it is five minutes or shorter.
- [ ] Review the exported video at normal playback speed for readable case, lot,
  shipment, approval, and source-readback details.
- [ ] Verify the video uses the PO20 story only: `M20-DIST-COMPONENT-V2-20260910` /
  `PUR-ORD-2026-00020`, 40 ordered/received/dispatched, and A25/B15 through
  Shipments 16–19.
- [ ] Keep the photo language truthful: it is a manual attachment with no recognition,
  count, QR, quality, or provenance extraction claim.
- [ ] State that delivery confirmations are synthetic and do not prove physical receipt.
- [ ] State the USD160 PO and USD150/USD90 customer-order values without claiming an
  invoice, payment, or recognized revenue.
- [ ] Upload the final video as public or unlisted according to the competition's
  access rules, then verify it plays without creator login.
- [ ] Paste the verified public video URL into Devpost.

### Devpost and repository

- [ ] Paste the current Devpost description and the exact field values above.
- [ ] Confirm the title is `LogisticPilot — The Missing 20` and the tagline is
  `Find the gap. Prove the cause. Close the loop.`
- [ ] Confirm the Professional Agents track and Builder ID in the Devpost form.
- [ ] Paste the testing instructions without exposing credentials or private runtime
  paths.
- [ ] Select the built-with tags above. Do not list Nova Pro. Do not imply that
  AgentCore Runtime powers the current Dashboard.
- [ ] Confirm the public repository, README, MIT license, current architecture links,
  and video URL all open from a signed-out browser.
- [ ] Run `make check` from a clean checkout and record the result for final review.
- [ ] Use Devpost preview to confirm English copy, links, video embed, and attachments.
- [ ] Complete the entrant attestations and submit only after the final preview passes.

### Claims to preserve

- [ ] The recorded English Dashboard conversation uses Strands with direct Amazon
  Bedrock Claude Opus 4.6 and remains advisory/read-only.
- [ ] Deterministic application code validates quantities and evidence, and an explicit
  manager approval gates a supported operation.
- [ ] Airtable, Jira, and Slack-via-Celigo readbacks belong to the same PO20 case.
- [ ] Historical cases stay labeled historical and are not presented as PO20 evidence.
