# Video reference research: awarded agent demos and the PO19 storyboard

**Research date:** 2026-09-10
**Scope:** Three awarded AI-agent submissions were checked against an official
organizer winner announcement and the team’s public project or video link. The
goal was to extract useful story structure for a professional, English, five-minute
maximum video for The Missing 20. This is a bounded reference review, not a ranking
of video quality.

The linked YouTube pages returned cache misses in the available web reader and the
VendorGuard Drive file required sign-in. I did not claim to have watched those
videos or read a transcript. Observations below come from the organizer’s written
winner announcement and the team project or repository page; playback-specific
claims are marked unavailable.

## Official current-contest guidance

The [official Agents for Humans rules](https://agentsforhumans.devpost.com/rules)
require a new Strands Agents project that does real work for real people and handles
the task end to end. The video must be public on YouTube or Vimeo, no longer than
five minutes, and include both a working-project demonstration and a pitch covering
the problem, the intended user, and why it matters. The rules also require a public
repository with a README, an MIT or Apache license, an architecture diagram, and an
AWS Builder ID. English materials or an English translation are required. A live
demo is optional, although the rules say it strengthens the technical-implementation
score; judges may rely on the submitted text, images, and video.

The same rules define the practical stand-out target through five equally weighted
criteria: thorough Strands implementation, a coherent product experience, a
credible real-world impact case, creative problem understanding, and an end-to-end
presentation that is easy to follow. The [official event page](https://agentsforhumans.devpost.com/)
frames the tracks around repetitive work for a real person or community and an agent
that carries the work through to a useful outcome. A separate [official AWS
Developers/Devpost tips post](https://www.linkedin.com/posts/devpost_hackathon-tips-for-beginners-activity-7496622903258570752-7btV)
was located, but its detailed tips are presented as an image in the available
rendering; no advice was inferred from that image.

## Awarded reference 1: EcoLafaek

[AWS AI Agent Global Hackathon’s official winner announcement](https://aws-agent-hackathon.devpost.com/updates/38140-congratulations-to-the-winners-of-the-aws-ai-agent-global-hackathon)
names **EcoLafaek** the first-place winner. The [team’s public Devpost project](https://devpost.com/software/ecolafaek)
describes a mobile waste-reporting input, Bedrock image analysis, a public dashboard,
and an autonomous chat path that chains multiple tools for SQL, charts, maps, and
web content. The project also publishes an [architecture page](https://docs.ecolafaek.com/architecture.html)
and a live-demo link. The Devpost page exposes a YouTube embed, but the playback URL
and transcript were not retrievable here.

**Source-supported pattern:** a concrete community problem is introduced before the
technical stack, then the product is described as a visible path from capture to
agent reasoning to a public result. The project page makes the mobile input,
dashboard, live demo, and architecture inspectable in the same story.

**Safe transfer:** open The Missing 20 with the warehouse manager’s reconciliation
problem, show the current frontend as the single control surface, then follow one
recorded case through evidence, decision, ERP effect, and cross-app readbacks. The
lesson is about showing a consequence and its evidence together; it is not evidence
that EcoLafaek’s video used any particular edit or pacing.

## Awarded reference 2: VendorGuard

The [Microsoft Agent Academy Hackathon winner announcement](https://devblogs.microsoft.com/powerplatform/agent-academy-hackathon-winners/)
names **VendorGuard** first place in the Operative track and says it was the
highest-scoring entry overall. The organizer describes a written cross-app path:
contract PDF arrival triggers Power Automate, a Dataverse record, extraction, a
Teams notification, an orchestrator, four specialist agents, and a stored compliance
report that can be queried. The organizer links the team’s [public demo file](https://drive.google.com/file/d/17-Y30hhX2ZBwbPJKSK8ul-wcw1BraLUy/view),
but that file required sign-in and no transcript was available.

**Source-supported pattern:** one trigger, a short chain of named systems, and one
business output make the cross-app story legible. The organizer’s “under two
minutes” statement is reported as the organizer’s description, not independently
measured here.

**Safe transfer:** show one PO19 case ID across the frontend, ERP documents, Airtable,
Jira, and the Slack/Celigo handoff. Name each system’s role and show the resulting
record rather than narrating every internal tool call. Keep the direct Airtable and
Jira handoffs distinct from Slack through Celigo, as the current architecture and
readbacks require.

## Awarded reference 3: Warehouse Picking Agent

The same [official Microsoft winner announcement](https://devblogs.microsoft.com/powerplatform/agent-academy-hackathon-winners/)
names **Warehouse Picking Agent** third place in the Special Ops track. It describes
a custom MCP server that connects an agent to Dynamics 365 warehouse work, with
tools for reading open pick lines and confirming warehouse work. The team’s [public
repository](https://github.com/granjan7779/rj-mcp-d365-server-2) documents the
visible path as Warehouse User (Teams/App) → Azure AI Foundry or Copilot Studio
agent → MCP server → D365 SCM, including `readOpenLines` and `confirmWork`. The
organizer links a [public YouTube demo](https://www.youtube.com/watch?feature=youtu.be&v=XXu6rNQmKAo);
the web reader returned a cache miss, so no playback or transcript claim is made.

**Source-supported pattern:** the user surface, agent boundary, integration layer,
and system of record are named explicitly. The story makes the read operation and
the state-changing confirmation separate, which helps a reviewer understand where
the agent ends and the business system begins.

**Safe transfer:** show the current frontend first, then the contract-selection and
allocation explanation, then the deterministic ERP write and its readback. Show
the external handoff links after the ERP result. Do not describe the Missing 20
agent as directly writing Airtable, Jira, or Slack; the application owns those
handoffs and the current source labels Slack as Celigo-mediated.

## What is observed versus inferred

| Evidence level | Finding | Recording consequence |
| --- | --- | --- |
| Observed in organizer pages and project text | Awarded projects make one real user problem and one end-to-end outcome concrete. | Start with the warehouse manager’s decision, then show the evidence path. |
| Observed in project descriptions | Strong examples name the input surface, agent boundary, connected systems, and output record. | Use the current UI, ERP document IDs, and same-case Airtable/Jira/Slack links as anchors. |
| Inference for this submission | A short, verifiable slice is easier to judge than a tour of every component. | Keep one PO19 case and spend time on the visible state change and readback. |
| Not established by this review | The linked demos’ exact pacing, narration, edit style, or viewer response. | Do not say a winner used a particular cut, cadence, or voiceover technique. |
| Current project evidence boundary | PO19 is a recorded repaired continuation; the PO18 Opus Q1–Q4 English answer is a separate captured diagnostic. | Label the PO18 clip visibly and never present it as a live PO19 answer. |

The canonical timed storyboard is [the V1 video storyboard](video-v1/STORYBOARD.md).
It covers the frontend and cross-app path without creating another inventory event or
paid model call; use it as the single source for scene order and timing.

## Capture checks

- Keep the current `RECORDING-20260910` namespace and one browser case visible when
  switching to each external record. Hold each linked record long enough to show its
  case correlation, but do not enumerate Slack milestones.
- Keep all captions and narration in English. Use the current architecture image and
  the direct linked records; do not add a Chinese screenshot or translate an
  inaccessible reference video.
- Keep credentials, raw SDK sessions, and private runtime files out of the frame.
  Verify the page before capture and do not click applied-event controls.
- The recorded PO19 path is a repaired continuation after a runtime restart. The
  video may present its final readbacks as a recorded continuation, but must not call
  it a clean uninterrupted take or a full seven-question model pass.
- After capture, separately verify the public YouTube/Vimeo URL, repository access,
  README/license/architecture links, and Devpost fields. Those are submission and
  judge-access checks, not evidence to invent in the video.

## Retrieval limitations

The organizer winner pages and written project descriptions were reachable on
2026-09-10. EcoLafaek’s page exposed a YouTube embed without a retrievable playback
URL; the VendorGuard Drive link required sign-in; Warehouse Picking Agent’s YouTube
URL returned a cache miss. No transcript was available for these references in the
research environment. The research therefore supports story facts, system-boundary
patterns, and the storyboard above, but does not support claims about the winners’
spoken wording, editing, pacing, or audience reaction.
