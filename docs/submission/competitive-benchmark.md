# Competition Benchmark

Research date: 2026-08-27.

## Official 2026 bar

The [Agents for Humans competition page](https://agentsforhumans.devpost.com/) and
[official rules](https://agentsforhumans.devpost.com/rules) use five equally weighted
criteria:

1. Technical Implementation
2. Design
3. Potential Impact
4. Creativity and Originality
5. Presentation

The required submission surface includes a public repository with an MIT or Apache
license, a README, an architecture diagram, and a public demonstration video no longer
than five minutes. A live demo is optional but can strengthen Technical Implementation.
The 2026 [project gallery](https://agentsforhumans.devpost.com/project-gallery) has not
yet been published, so there are no current entrants that can be responsibly ranked.

## Comparable AWS winners

The closest public benchmark is the official
[2025 AWS AI Agent Global Hackathon winner announcement](https://aws-agent-hackathon.devpost.com/updates/38140-congratulations-to-the-winners-of-the-aws-ai-agent-global-hackathon).

| Project | What judges could immediately see | Lesson for The Missing 20 |
| --- | --- | --- |
| [EcoLafaek — 1st place](https://devpost.com/software/ecolafaek) | A live civic product, multimodal reporting, maps, search, multi-tool AgentCore workflow, public documentation, and visible usage | Lead with the human problem and working product; keep architecture evidence behind the story |
| [AegisAgent — 2nd place](https://devpost.com/software/aegisagent-an-insurance-claim-app-fully-developed-by-kiro) | Evidence curation, policy interpretation, adversarial review, pause/resume, citations, and a deployed decision packet | Our closest conceptual peer; make agent investigation and bounded human decision visually obvious |
| [Province — 3rd place](https://devpost.com/software/province) | A plain-language tax journey, document extraction, multi-agent workflow, and a concrete 21/21 form-mapping result | Show one memorable end-to-end outcome instead of asking judges to read internal implementation detail |

## Current competitive position

### Stronger than typical demos

- Deterministic separation between probabilistic investigation and write authority.
- Exact per-action two-role quorum instead of a vague “human in the loop.”
- Fresh authoritative rereads, idempotent effects, postcondition verification, replay,
  and adversarial mutation tests.
- Explicit complete, degraded, and fail-closed states.

### Below the public winner bar

- Stable useful Nova-produced investigation is not proven.
- AgentCore deployment is not implemented.
- All business data and impact evidence are synthetic.
- The public video and public live deployment do not yet exist.

## Presentation strategy

The product should not open as an audit report. The judge-facing path is:

1. Detect the 20-unit discrepancy.
2. Let agents compare plausible causes and surface evidence.
3. Show deterministic policy selecting an eligible recovery action.
4. Show two distinct roles approving that exact action.
5. Apply the bounded synthetic recovery and verify that the records reconcile.

Detailed digests, claim classes, AWS evidence boundaries, and the immutable audit trail
remain available as proof, but they are secondary to this five-step story.
