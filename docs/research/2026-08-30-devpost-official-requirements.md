# Agents for Humans: official Devpost and AWS requirements

Verified on **2026-08-30** from first-party Devpost, Strands Agents, and AWS documentation only. This note records requirements and defensible capability boundaries; it does not record registration or submission state.

## Executive conclusions

- The submission deadline is **September 14, 2026 at 5:00 PM Pacific Time**. The judging period runs September 15 through October 8, and winners are expected around October 14. [Official Rules — Dates and Timing](https://agentsforhumans.devpost.com/rules)
- The project must be a **new Strands Agents project built during the August 10–September 14 submission period**, do real work for real people, and handle a workflow end to end rather than merely chat about it. Any pre-existing work incorporated into the project must be disclosed. [Official Rules — Project Requirements](https://agentsforhumans.devpost.com/rules)
- The required public package is: English text description, public runnable repository with README and MIT/Apache license, architecture diagram, public YouTube/Vimeo video no longer than five minutes, and AWS Builder ID. A live demo URL is optional but explicitly strengthens Technical Implementation. [Official Rules — Submission Requirements](https://agentsforhumans.devpost.com/rules)
- Stage Two uses five **equally weighted** criteria: Technical Implementation, Design, Potential Impact, Creativity & Originality, and Presentation. AgentCore deployment and/or a live demo strengthen Technical Implementation. [Official Rules — Judges & Criteria](https://agentsforhumans.devpost.com/rules)
- The best-fit track for The Missing 20 is **Professional Agents** (inference): the primary user is a supply-chain/operations professional and the product removes repetitive, judgment-heavy incident investigation and recovery work. The official track definition focuses on making professionals dramatically better at existing work. [Hackathon Overview — What to Build](https://agentsforhumans.devpost.com/)
- A defensible technical story is: **Strands Agents perform specialized, tool-assisted investigation and conversational explanation; AgentCore Runtime hosts and invokes the agent experience; deterministic application code independently owns evidence integrity, authorization, controlled recovery, and verification.** This accurately reflects both the SDK capabilities and the official warning that agent tools execute with the host process's permissions and must be audited by the developer. [Strands Tools Overview](https://strandsagents.com/docs/user-guide/concepts/tools/)

## Dates, registration, eligibility, and credits

| Item | Official requirement | Direct source |
|---|---|---|
| Submission period | Aug 10, 2026, 9:00 AM PT through Sep 14, 2026, 5:00 PM PT | [Official Rules §1](https://agentsforhumans.devpost.com/rules) |
| Judging period | Sep 15, 2026, 9:00 AM PT through Oct 8, 2026, 5:00 PM PT | [Official Rules §1](https://agentsforhumans.devpost.com/rules) |
| Winner announcement | On or around Oct 14, 2026, 2:00 PM PT | [Official Rules §1](https://agentsforhumans.devpost.com/rules) |
| Registration | Join on the hackathon website using a free Devpost account; then create the submission | [Official Rules §4](https://agentsforhumans.devpost.com/rules) |
| Eligible entrants | Adults at the age of majority where they reside; eligible teams and organizations are also permitted | [Official Rules §3](https://agentsforhumans.devpost.com/rules) |
| Excluded locations/relationships | The rules list excluded jurisdictions and conflicts, including promotion entities, their agents/families, judges, and certain affiliates | [Official Rules §3](https://agentsforhumans.devpost.com/rules) |
| AWS credit request | Registered participants may request $50 while supplies last by Sep 11, 2026 at noon PT | [Official Resources](https://agentsforhumans.devpost.com/resources) |
| Credit responsibility | Credits expire Oct 31; charges beyond promotional credits remain the entrant's responsibility | [Official Rules §4](https://agentsforhumans.devpost.com/rules) |

Eligibility is personal/legal and must be confirmed by the entrant against the full rules before final submission. This document does not make that determination.

## Project requirements

1. Build a **new** AI agent with the Strands Agents SDK.
2. Solve a real task for real people and handle it **end to end, not just chat about it**.
3. Enter one of three tracks: Everyday Agents, Professional Agents, or Good Neighbor Agents.
4. Make the project installable, consistently runnable, and truthful to the video/text depiction.
5. Disclose pre-existing code or work; the submitted work must have been built during the submission period.
6. Be authorized to use every third-party SDK, API, and dataset under its applicable terms.
7. AgentCore is optional, but official rules state it strengthens Technical Implementation.

Source: [Official Rules — Project Requirements](https://agentsforhumans.devpost.com/rules).

### Recommended track mapping for The Missing 20

**Professional Agents** is the clearest fit because the primary audience is operations and supply-chain professionals, while the product watches repetitive operational flows, investigates a specific reconciliation incident, and presents a controlled decision only when human authority is required. This is an interpretation of the official Professional Agents definition, not an official classification decision. [Hackathon Overview](https://agentsforhumans.devpost.com/) · [Official Resources — track guidance](https://agentsforhumans.devpost.com/resources)

## Submission fields and artifacts

The public rules expose the following required submission contents. The exact authenticated form labels/options are not visible on the public pages and should be rechecked in the saved Devpost draft before final submission.

| Field/artifact | Requirement | Readiness implication |
|---|---|---|
| Project text description | Explain features and functionality; overview also asks what it does, who it serves, and how it works | Write in English and lead with one concrete operations pain |
| Public repository URL | GitHub, GitLab, or Bitbucket; public for judging/testing | Must not be a private-only URL |
| Repository contents | All source, assets, setup/run instructions needed for a functional project | README must support an independent judge run |
| License | MIT or Apache license file, detectable at the top/About area | Add the actual license file and configure GitHub About metadata |
| README | Explicitly required | Surface Strands/AgentCore architecture, setup, demo path, limitations, and safety boundary |
| Architecture diagram | Explicitly required | Use a judge-readable diagram that distinguishes AI advisory work from deterministic control |
| Demo video | Maximum five minutes; public on YouTube or Vimeo | Show the working product end to end, not slides alone |
| Video pitch | Must cover the problem, target user, and why it matters | Demonstrate normal flow → incident → agent investigation/chat → human decision → controlled recovery → verification |
| AWS Builder ID | Explicitly required | Enter only in the authenticated Devpost form; do not publish credentials |
| Live demo URL | Optional; strengthens Technical Implementation | If supplied, keep it free and accessible through the judging period |
| Testing access | Free, unrestricted access through judging; private sites must provide credentials/instructions | Avoid requiring judges to configure a private AWS account if a safe hosted demo is possible |
| English | All materials must be in English or include English translations | README, description, video narration/subtitles, and testing instructions should be English |

Sources: [Hackathon Overview — What to Submit](https://agentsforhumans.devpost.com/) and [Official Rules — Submission Requirements and Testing](https://agentsforhumans.devpost.com/rules).

### Public-repository compliance checks

- Scan the repository for API keys, AWS credentials, account IDs, runtime ARNs where unnecessary, login tokens, `.env` files, and private evidence before publishing. The organizers explicitly warn entrants to protect API keys and scan the public repository. [Official update — How to actually stand out](https://agentsforhumans.devpost.com/updates/45987-how-to-actually-stand-out-in-agents-for-humans)
- Verify the MIT/Apache license is a root-level recognized license and visible in GitHub's About/repository summary.
- Verify every image, icon, font, third-party dataset, API, and copied asset has a compatible license/permission.
- Disclose any pre-August-10 code or asset incorporated into the build.
- Do not place judge credentials or secrets in the public repository. If a demo needs authentication, provide narrowly scoped testing access in Devpost testing instructions.

## Judging criteria

Stage One is a pass/fail viability check: the project must fit the theme and reasonably use the required tools/APIs/SDKs. Stage Two scores the following criteria equally. [Official Rules §6](https://agentsforhumans.devpost.com/rules)

| Criterion | Official question | What The Missing 20 must make unmistakable |
|---|---|---|
| Technical Implementation | Thorough, skillful, non-trivial Strands use; working code; live demo and/or AgentCore strengthens the score | Real specialized agents, tool calls, AgentCore deployment/invocation proof, live chat, and the full deterministic recovery loop |
| Design | Complete, coherent product rather than a technical proof of concept | A clear dashboard and Agent Workspace that guide a judge without report-like explanation overload |
| Potential Impact | Credible, specific real problem and real audience; demonstrated solution | Quantify the 20-unit reconciliation gap, operator time/risk avoided, and why controlled automation matters |
| Creativity & Originality | Creative, non-obvious Strands use and problem-domain understanding | Multi-agent incident forensics plus safe human-authorized remediation, not a generic chatbot |
| Presentation | End-to-end working video; clear problem, user, importance; easy to follow | One five-minute story with visible data flow, incident, investigation, conversation, approval, recovery, and verification |

Tie-breaking compares criteria in listed order, so Technical Implementation is also the first tie-breaker. [Official Rules §6](https://agentsforhumans.devpost.com/rules)

### Official organizer advice

The organizers explicitly advise entrants to solve one specific problem, make the agent do real work rather than merely chat, make Strands use impossible to miss in the description/Built With/video, protect keys, and treat the video as a pitch rather than a tutorial. [Official update — How to actually stand out](https://agentsforhumans.devpost.com/updates/45987-how-to-actually-stand-out-in-agents-for-humans)

They also advise one workflow completed end to end over several partial workflows, real-scenario testing, a public repo with license and README, and a five-minute problem → audience → importance → working-product story. [Official update — Time to plan your project](https://agentsforhumans.devpost.com/updates/45850-time-to-plan-your-agents-for-humans-project)

## Bonus points

- Stage Two submissions may earn **up to 0.6 additional points**, 0.2 per public builder.aws.com post, for up to three qualifying posts about the AWS build journey. [Official Rules §6](https://agentsforhumans.devpost.com/rules)
- There is inconsistent legacy wording inside the rules: the page header says it was updated on Aug 12 to remove the `#AgentsforHumans` requirement, while a later scoring paragraph still says to use a hashtag. The overview and submission section say to use **“Agents for Humans” in the title**. Safest practice: include the exact phrase “Agents for Humans” naturally in every qualifying title and recheck the current form/rules immediately before publishing. [Official Rules](https://agentsforhumans.devpost.com/rules) · [Hackathon Overview](https://agentsforhumans.devpost.com/)

## Official Strands Agents capability boundaries

### Capabilities the official SDK supports

- Agent creation/invocation, streaming responses, structured output, tools, conversation management, multi-agent patterns, session management, OpenTelemetry integration, and agent steering are documented SDK features. [Strands quickstart overview](https://strandsagents.com/docs/user-guide/quickstart/overview/)
- Tools are how an agent accesses external systems and data; the agent can select and invoke configured tools in response to a prompt. [Strands Tools Overview](https://strandsagents.com/docs/user-guide/concepts/tools/)
- Multi-agent systems support specialization, orchestration, and collaboration. Graph, Swarm, Workflow, and agents-as-tools are documented patterns. [Strands Multi-agent Patterns](https://strandsagents.com/docs/user-guide/concepts/multi-agent/multi-agent-patterns/) · [Agents as Tools](https://strandsagents.com/docs/user-guide/concepts/multi-agent/agents-as-tools/)
- Streaming emits lifecycle, message, model-stream, and tool-related events that an application can use to display progress during execution. [Strands Streaming Events](https://strandsagents.com/docs/user-guide/concepts/streaming/)
- Session managers persist conversation history, agent state, multi-agent state, shared context, and execution transitions. [Strands Session Management](https://strandsagents.com/docs/user-guide/concepts/agents/session-management/)

### Safety/authority boundary

Strands documentation states that tools execute code with the permissions of the host process and that developers must audit tool behavior for their deployment and threat model. Therefore, use of Strands does **not by itself prove** safe authorization, evidence integrity, idempotent execution, or verified recovery. Those are application responsibilities. [Strands Tools Overview — Tool Security](https://strandsagents.com/docs/user-guide/concepts/tools/)

For The Missing 20, the strongest accurate claim is:

> Strands agents autonomously coordinate specialized, read-only investigation and conversational explanation. Deterministic application controls independently validate authoritative evidence and exclusively govern action eligibility, two-role approval, controlled execution, verification, and replay.

Avoid claims that the model itself authorizes recovery, proves evidence completeness, or guarantees operational correctness unless separate evidence demonstrates those facts.

## Official Amazon Bedrock AgentCore capability boundaries

### Capabilities the official Runtime supports

- AgentCore Runtime is a secure, serverless, purpose-built hosting environment for agents/tools; it is framework-agnostic and explicitly works with Strands. It supports HTTP, WebSocket bidirectional streaming, MCP, and A2A. [AWS — Host agents or tools with AgentCore Runtime](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agents-tools-runtime.html)
- `InvokeAgentRuntime` sends a request to a Runtime endpoint, returns a streaming response, and uses a session identifier to maintain context across interactions. This directly supports an interactive chatbox backed by a deployed agent. [AWS — Invoke an AgentCore Runtime agent](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-invoke-agent.html)
- Reusing a Runtime session ID maintains conversational context and session isolation. [AWS — Use isolated sessions for agents](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-sessions.html)
- Runtime provides CloudWatch logs by default and supports metrics, traces, request/session identifiers, and enhanced OpenTelemetry observability when configured. [AWS — Configure AgentCore observability](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-configure.html) · [AWS — Runtime observability data](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-runtime-metrics.html)

### Claims AgentCore documentation does not establish on its own

Deployment to Runtime does not by itself establish that:

- every response is factually correct or fully cited;
- the model has authority to mutate business systems;
- an operational recovery is authorized, safe, idempotent, or verified;
- Gateway, Policy, Memory, Identity, or other AgentCore services are used merely because Runtime is used;
- all UI data is live production data.

Those claims require project-specific evidence. The submission should say **AgentCore Runtime** where that is what is proven, rather than the broader “AgentCore platform,” and distinguish real Runtime/Nova evidence from scripted/synthetic scenarios.

## Recommended submission narrative (fact-bounded)

1. **Problem:** supply-chain teams lose time reconciling partial message delivery across warehouse, queue, ERP, and invoice systems; unsafe automation can make the discrepancy worse.
2. **Agentic work:** a Strands orchestrator coordinates specialized read-only investigators, selects relevant tools, compares hypotheses, and returns cited findings; users can ask role-specific questions through the chatbox.
3. **Human decision:** the agent surfaces a recovery proposal only when a real decision is required.
4. **Deterministic control:** application code validates evidence, enforces policy and two-role approval, executes idempotent recovery, rereads authoritative state, verifies the effect, and supports replay.
5. **AWS proof:** the agent is hosted/invoked through Amazon Bedrock AgentCore Runtime with a real model; Runtime/session/chat evidence should be shown without exposing account identifiers or secrets.
6. **Truthful limitation:** AI findings are advisory and may be incomplete; authoritative deterministic validation is the safety boundary.

This story directly answers the theme's requirement for background autonomous work plus human surfacing at a real decision, while avoiding an unsupported claim that chat alone completes the business workflow.

## Final pre-submission checklist

- [ ] Entrant has joined the hackathon and independently confirmed eligibility.
- [ ] Professional Agents track selected.
- [ ] Project creation dates and any pre-existing material disclosed.
- [ ] Public repository contains all runnable source/assets/instructions.
- [ ] Root MIT or Apache license is detected by GitHub and visible in About.
- [ ] README and architecture diagram are included.
- [ ] Secrets/privacy/license scan passes before repository publication.
- [ ] English text description is complete.
- [ ] Five-minute-or-shorter public YouTube/Vimeo video demonstrates the working end-to-end flow and covers problem, audience, and importance.
- [ ] AWS Builder ID supplied only in the submission form.
- [ ] Live demo, if submitted, remains accessible and free through Oct 8.
- [ ] Strands Agents appears explicitly in description, Built With, architecture, README, and video.
- [ ] AgentCore Runtime and real model claims match redacted deployment/invocation evidence.
- [ ] AI advisory output and deterministic operational authority are visibly separated.
- [ ] Optional builder.aws posts use “Agents for Humans” in the title and are public before the deadline.
- [ ] Draft is submitted well before Sep 14 at 5:00 PM PT and receipt is verified.

## Primary sources

- [Agents for Humans Hackathon overview](https://agentsforhumans.devpost.com/)
- [Agents for Humans Official Rules](https://agentsforhumans.devpost.com/rules)
- [Agents for Humans Resources](https://agentsforhumans.devpost.com/resources)
- [Organizer update: How to actually stand out](https://agentsforhumans.devpost.com/updates/45987-how-to-actually-stand-out-in-agents-for-humans)
- [Organizer update: Time to plan your project](https://agentsforhumans.devpost.com/updates/45850-time-to-plan-your-agents-for-humans-project)
- [Strands Agents quickstart overview](https://strandsagents.com/docs/user-guide/quickstart/overview/)
- [Strands Agents tools](https://strandsagents.com/docs/user-guide/concepts/tools/)
- [Strands Agents multi-agent patterns](https://strandsagents.com/docs/user-guide/concepts/multi-agent/multi-agent-patterns/)
- [Strands Agents streaming](https://strandsagents.com/docs/user-guide/concepts/streaming/)
- [Strands Agents session management](https://strandsagents.com/docs/user-guide/concepts/agents/session-management/)
- [AWS: Host agents/tools with AgentCore Runtime](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agents-tools-runtime.html)
- [AWS: Invoke AgentCore Runtime](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-invoke-agent.html)
- [AWS: AgentCore Runtime sessions](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-sessions.html)
- [AWS: AgentCore observability](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-configure.html)
