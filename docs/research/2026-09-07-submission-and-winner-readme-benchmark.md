# Agents for Humans submission and winner presentation benchmark

**Verified:** 2026-09-07 (America/Los_Angeles)
**Scope:** first-party Agents for Humans Devpost pages, official AWS/Strands documentation, the official AWS AI Agent Global Hackathon winner announcement, and the winners' own Devpost pages/repositories. No secondary commentary was used.

## Executive answer

The submission deadline is **September 14, 2026 at 5:00 PM Pacific Time**. A compliant submission needs a new Strands Agents project, an English description, a public functional repository with README and detectable MIT or Apache license, an architecture diagram, a public YouTube/Vimeo working-demo video no longer than five minutes, and an AWS Builder ID. A hosted live-demo URL is optional, but the rules separately require free judge access to a website, functioning demo, or test build through the end of judging on October 8. Judges are not required to run the project, so the Devpost page, images, and video must stand on their own. [Official Rules](https://agentsforhumans.devpost.com/rules) · [Overview](https://agentsforhumans.devpost.com/)

Stage One is pass/fail for theme fit and reasonable use of the required SDK. Stage Two scores five criteria equally: Technical Implementation, Design, Potential Impact, Creativity & Originality, and Presentation. A live demo and/or AgentCore deployment strengthens Technical Implementation, and the listed criterion order is also the tie-break order. [Official Rules — Judges & Criteria](https://agentsforhumans.devpost.com/rules)

For **The Missing 20**, the content direction is already strong: one specific Professional Agents problem, explicit Strands use, a complete investigation-to-verified-closure flow, a labeled authority boundary, and honest limitations. At the time of this baseline, the immediate submission risk was release packaging rather than narrative invention: the public GitHub README was stale, locally referenced hero screenshots and the newest architecture artifacts were untracked, and the documented cold-start prerequisites omitted `uv` and `make`. Those findings are the input to the release work, not a claim about the final pushed commit.

## 1. Current official requirements

| Area | Verified official requirement | Submission consequence |
| --- | --- | --- |
| Timing | Submission period ends **Sep 14, 2026, 5:00 PM PT**; judging runs Sep 15–Oct 8; winners are expected around Oct 14. | Freeze and submit several hours early; after the deadline the entry cannot normally be substantively changed. |
| New work | The project must be newly created during Aug 10–Sep 14. Standard frameworks, libraries, starter templates, and AI coding assistants are allowed; other pre-existing work incorporated into the project must be disclosed. | Keep the provenance disclosure concise and complete. Do not describe older work as newly built. |
| Required SDK/theme | Build a new AI agent with **Strands Agents** that does real work for real people and handles a task end to end rather than only chatting about it. | Name Strands in the opening, architecture, Built With, and demo; show tool use and a completed outcome. |
| Track | One project may enter only one track; track choice should follow the primary user. | **Professional Agents** is the defensible selection for operations professionals doing repetitive, judgment-heavy incident work. This is a project recommendation, not an organizer classification. |
| Functionality | The project must install and run consistently on its intended platform and behave as depicted in the submission. | All claims in README, Devpost, screenshots, and video must match the exact release commit and mode being shown. |
| Third parties/IP/data | Entrants need authorization for integrated SDKs, APIs, and data and must respect IP/privacy rights. The FAQ recommends synthetic/anonymized/public data instead of real sensitive data. | Retain the synthetic/demo-data disclosure and verify asset/data licenses and permissions. |
| Text | English description explaining features and functionality; the overview says what it does, who it is for, and how it works. | Lead with the operator problem and end-to-end outcome in plain language, then explain the implementation. |
| Repository | Public GitHub/GitLab/Bitbucket URL containing all source, assets, setup instructions, README, and a real MIT or Apache license file visible/detectable in the repository About area. | A stale public branch, broken images, missing assets, or undocumented prerequisites are submission defects even if the local build is excellent. |
| Architecture | Architecture diagram is mandatory. The FAQ asks it to show user input/interface, the Strands agentic loop, tools/integrations, AWS services, and output. | Upload one static, readable diagram to Devpost and keep the same diagram in the repository; interactive HTML may supplement it, not replace it. |
| Video | Public YouTube/Vimeo, **maximum five minutes**, working-project demonstration plus pitch covering the problem, target user, and why it matters. Camera appearance is not required. | Record one self-contained end-to-end story; do not rely on judges running the repo to understand the result. |
| Testing access | Provide a website, functioning demo, or test build, free and unrestricted through Oct 8. A live hosted demo link is optional and improves Technical Implementation. Judges may elect not to test. | The local/test-build path must be genuinely runnable; a hosted path is valuable only if stable, safe, and free for judges. |
| Identity | AWS Builder ID is required; the FAQ says the form asks for the email used to create it. | Enter it only in the authenticated form; do not publish it as a credential. |
| Bonus | Stage Two entries may earn 0.2 per qualifying public builder.aws post, up to 0.6. | Treat as optional after the core submission is frozen. See ambiguity below before choosing the title wording. |

Sources: [Official Rules](https://agentsforhumans.devpost.com/rules), [Overview](https://agentsforhumans.devpost.com/), [FAQ](https://agentsforhumans.devpost.com/details/faqs), [Resources](https://agentsforhumans.devpost.com/resources), [Pro tips for your project](https://agentsforhumans.devpost.com/updates/46174-pro-tips-for-your-project), and [Time to plan your project](https://agentsforhumans.devpost.com/updates/45850-time-to-plan-your-agents-for-humans-project).

### Material ambiguity to handle conservatively

The rules header says an August 12 update removed the `#AgentsforHumans` requirement for bonus posts, while a later paragraph still says to use a hashtag. The overview/organizer update says to put **“Agents for Humans”** in the title. Safest course: use the exact phrase “Agents for Humans” naturally in each qualifying title, do not depend on the hashtag, and recheck the authenticated submission form and rules immediately before publication. [Official Rules](https://agentsforhumans.devpost.com/rules) · [Organizer stand-out guidance](https://agentsforhumans.devpost.com/updates/45987-how-to-actually-stand-out-in-agents-for-humans)

## 2. What the judging criteria demand from the package

| Criterion | What the official rubric asks | Evidence the package should surface |
| --- | --- | --- |
| Technical Implementation | Thorough, skillful Strands use; genuine effort; working, non-trivial implementation. Live demo and/or AgentCore deployment strengthens the score. | A named agent/tool topology, an actual tool trace, structured outputs, source evidence, failure behavior, and a precise statement of which path uses direct Strands versus AgentCore Runtime. |
| Design | A complete, coherent product experience rather than a technical proof of concept. | One judge journey with clear state changes, human decision point, recovery result, and understandable error/degraded states. |
| Potential Impact | A credible, specific real problem for a real audience, actually addressed by what is demonstrated. | The 20-unit 12-accepted / 8-quality-held split, the blocked downstream order, the operations role, concrete work eliminated or risk prevented, and bounded demo metrics. Avoid production ROI claims without production data. |
| Creativity & Originality | A creative, non-obvious Strands use plus real problem-space understanding. | The distinctive hybrid: autonomous cross-system evidence reconciliation, explicit uncertainty, human-controlled authority, deterministic effect verification, and replay. |
| Presentation | Clear end-to-end video; problem, user, importance; easy to follow. | A five-minute narrative that shows the product working rather than narrating architecture slides for most of the runtime. |

Technical Implementation is also the first tie-breaker because ties are resolved using the listed criteria in order. [Official Rules](https://agentsforhumans.devpost.com/rules)

The organizers reinforce the same priorities: one real, specific problem; one workflow end to end; Strands use made impossible to miss; a cold-runnable public repo; verified claims; protected API keys; and a pitch rather than a tutorial. [How to actually stand out](https://agentsforhumans.devpost.com/updates/45987-how-to-actually-stand-out-in-agents-for-humans) · [Pro tips](https://agentsforhumans.devpost.com/updates/46174-pro-tips-for-your-project) · [Planning guidance](https://agentsforhumans.devpost.com/updates/45850-time-to-plan-your-agents-for-humans-project)

## 3. Official prior-winner presentation benchmark

There cannot yet be winners for the current event because submissions remain open. The nearest official precedent is the 2025 AWS AI Agent Global Hackathon. Award status comes from the organizer's [official winner announcement](https://aws-agent-hackathon.devpost.com/updates/38140-congratulations-to-the-winners-of-the-aws-ai-agent-global-hackathon). Technical details below are entrant claims on their Devpost pages/repositories, not independent validation, and that earlier competition had different rules.

| Official winner | Useful presentation pattern | What to borrow; what not to infer |
| --- | --- | --- |
| [EcoLafaek — 1st Place](https://devpost.com/software/ecolafaek) | Opens with a locally grounded human problem and quantified scale, then follows citizen photo/GPS input through multimodal analysis and multi-tool outputs such as maps/charts. It includes a labeled architecture, live links, documentation links, challenges/solutions, current usage claims, and impact metrics. | Borrow the sequence **human pain → input → autonomous tool work → inspectable operational output → impact evidence**. Do not copy its breadth or treat page claims as audited facts. Its linked repository was not retrievable during this check, so it is not a reliable cold-start benchmark. |
| [AegisAgent — 2nd Place](https://devpost.com/software/aegisagent-an-insurance-claim-app-fully-developed-by-kiro) | Explains distinct evidence-curation, policy-interpretation, and compliance-review roles; the orchestrator can pause for missing evidence and later resume; the product emits a cited decision packet rather than only a chat response. | Borrow specialist responsibilities, explicit blocking evidence gaps, and a durable resolution artifact. The page did not expose a public repository link during this check, so use it for narrative/architecture patterns only. |
| [Province — 3rd Place](https://devpost.com/software/province) | States the user's cost/confusion, demonstrates a concrete document-to-form workflow, names agent responsibilities and tools, shows data flow, and reports validation outcomes alongside challenges and solutions. | Borrow stepwise “what happens” examples and measurable verification. Avoid unsupported superlatives; metrics need a visible method or bounded test context. No public repository link was visible on the checked page. |
| [AI-driven multi-agent fraud alert triage — Best AgentCore Implementation](https://devpost.com/software/ai-driven-multi-agent-fraud-alert-triage-system) | Presents a clean three-stage operational chain: triage, investigation, report; combines rules with model assessment; and ends in a structured SAR artifact stored for compliance review. | Closest enterprise presentation analogue: show hybrid deterministic/LLM responsibilities and end in a durable business artifact. Its implementation/impact figures remain entrant claims. |
| [AgentShell — Best Strands SDK Implementation](https://devpost.com/software/agent-shell) | Centers one memorable Strands idea, names each MCP tool, presents the exact see/think/speak/listen flow, documents security boundaries and limitations, and gives an exact demo scenario. Its [public repository](https://github.com/marcosanyo/AgentShell) has a root MIT license, lockfile/package manifest, sample environment configuration, Dockerfile, setup/start scripts, docs, project tree, quick start, deployment/test commands, and troubleshooting. | Strongest README/repository benchmark: make the agent's autonomous tool selection inspectable, provide one copyable judge path, and state current limitations next to the relevant claim. Do not treat hardware-heavy setup as a model for The Missing 20's simpler default replay. |
| [Drishti AI Navigator — Best Nova Act Integration](https://devpost.com/software/drishti-ai-navigator) | The page shows user journey, architecture layers, data flow, security, human takeover, challenges, and metrics. Its [public repository](https://github.com/akashtalole/Drishti-AI-Navigator-App) has a root Apache-2.0 license, frontend/backend split, Dockerfile, environment template, architecture, setup, usage, project tree, and API reference. | Borrow explicit human-intervention and data-flow documentation. Do **not** copy the page's extremely broad claim set. The checked README's clone command points to a different repository name, illustrating why a clean-clone test matters even for a winning project. |

### Cross-winner patterns that recur

1. **Specific human stakes appear before cloud inventory.** The better pages make a judge understand the user and pain before listing services.
2. **The autonomous loop is concrete.** They name agent roles, tools, triggering input, intermediate work, and the output/effect.
3. **Architecture is explanatory, not decorative.** It shows components and how data/actions cross boundaries.
4. **A visible artifact or physical/business effect closes the loop.** Examples include maps/charts, a coverage packet, a filled tax form, a SAR, or a camera action.
5. **Challenges and limitations improve credibility.** Strong pages say what failed, how it was corrected, and what remains future work.
6. **Repository readiness is operational.** Root license, environment template, pinned dependencies/lockfile, runnable commands, project map, and troubleshooting are more valuable than repository size.

These are descriptive patterns, not proof that any one pattern caused an award.

## 4. Recommended README contract for The Missing 20

Use this order so a judge can understand the product before reaching implementation detail:

1. **Title, one-line promise, and 2–3 sentence plain-language summary:** who (supply-chain/operations professional), repeated pain (cross-system receipt discrepancy), what the agent does, and the verified outcome.
2. **One hero screenshot or short GIF plus “what changes”:** 20 units split 12 accepted / 8 quality-held → investigation → Manager decision → verified 20/20 delivery and exact billed outcome. Keep business labels visible.
3. **Judge quick start:** one default, offline/synthetic, no-credential path with exact prerequisites and copy/paste commands. Put AWS/live modes after the default path.
4. **End-to-end walkthrough:** Detect → Investigate → Ask → Decide → Recover → Verify/Replay. State which steps are autonomous and which are deterministic/human-controlled.
5. **Architecture image and short explanation:** user/UI, Strands loop, agents/tools, data sources, AWS/AgentCore, output, and the deterministic authority boundary.
6. **How Strands and AWS are used:** name actual SDK constructs, tool responsibilities, runtime/invocation boundary, and what AgentCore services are and are not used.
7. **Evidence and evaluation:** bounded matrices, demo-tenant evidence, failure modes, and links to machine-readable artifacts. Explain what the numbers measure.
8. **Repository map and verification commands:** source, tests, workspace, agent runtime, artifacts, and docs; one full quality command plus targeted commands.
9. **Security, privacy, limitations, and provenance:** synthetic/purpose-built data, no secrets, advisory-vs-authority split, pre-existing work disclosure, and unsupported claims explicitly excluded.
10. **License and links:** MIT license, Devpost, public video once available, optional live demo, architecture, and deeper docs.

This structure directly implements the organizer's request for plain language, explicit Strands usage, and setup instructions that let a stranger start cold. [Pro tips](https://agentsforhumans.devpost.com/updates/46174-pro-tips-for-your-project)

AWS's maintained [sample Strands agent with AgentCore repository](https://github.com/aws-samples/sample-strands-agent-with-agentcore) is a useful official packaging reference independent of contest winners: it puts purpose, features, architecture/component mapping, quick start, project tree, deployment links, focused documentation, infrastructure-as-code, and license at the repository front door. Borrow that information hierarchy, not its project-specific infrastructure.

### Current README strengths

- The release opening should identify the exact 20-unit, 12-accepted / 8-quality-held operations incident and five-source disagreement.
- “What a judge sees in five minutes” already supplies a strong end-to-end spine.
- Strands investigation and deterministic authority are explicitly separated.
- The README includes setup, screenshots, architecture, evaluation boundaries, limitations, provenance, and a root MIT license.
- Claims about Gateway/Policy and production impact are appropriately excluded.

### Current README/repository release risks

1. **P0 — Public branch is stale.** The public [GitHub repository](https://github.com/danielwanwx/the-missing-20) currently says Strands agents “will” perform work and says it does not yet claim a deployed AgentCore implementation or agent-driven competition demo. That directly conflicts with the current local README and Devpost draft. Push a reviewed, internally consistent release commit before submission and verify the rendered public page in a logged-out browser.
2. **P0 — README images and newest architecture are not yet tracked.** The locally referenced `artifacts/audits/2026-09-06-next-level/01-dashboard-live.png`, `03-investigation-plan-ready.png`, and the `the-missing-20-submission-v5` architecture files were untracked at review time. A pushed README would therefore render broken links unless the chosen public assets are deliberately added.
3. **P0 — No clean-clone proof yet.** The README lists Python and Node as prerequisites, but `make bootstrap` also requires `uv` and the workflow assumes `make`. Add every prerequisite or provide a wrapper; then run the exact documented path from a new temporary clone with no local `.env`, caches, runtime DB, or installed dependencies.
4. **P0 — Architecture upload needs a canonical static image.** Devpost explicitly asks for an architecture diagram and the FAQ describes its contents. Select one PNG/SVG that is readable at Devpost width, commit it, embed it in README, and upload that same file. Keep HTML/JSON as supplemental proof.
5. **P0 — Release-set sprawl.** The working tree currently contains many modified/untracked test artifacts and screenshots. Curate the public evidence set; do not publish every transient backend run or browser profile. Ensure every linked artifact is tracked and every unlinked sensitive/transient artifact is ignored.
6. **P0 — Secret/privacy scan must cover the release commit.** `.env`, local runtime state, virtual environments, Node modules, and browser QA profiles are ignored, and a narrow tracked-file scan found no credential-shaped value outside the scanner definitions. That is not a complete release audit. Scan the actual staged commit for AWS keys, private keys, tokens, account IDs/ARNs, cookies, PII, and tenant data immediately before push. The organizer explicitly warns about exposed keys. [Stand-out guidance](https://agentsforhumans.devpost.com/updates/45987-how-to-actually-stand-out-in-agents-for-humans)
7. **P1 — Compress the above-fold story.** Preserve the precise safety boundary, but put one business outcome and the fastest judge action before the long integration explanation. Official guidance asks for plain language, not a feature list.
8. **P1 — Keep “same path” claims exact.** The local materials correctly say the latest UI uses direct Strands transport and AgentCore Runtime is separately proven. Repeat that wording in the static diagram, Devpost, and video; do not visually imply the live UI routes through Runtime unless it actually does.
9. **P1 — Add troubleshooting around the default path.** AgentShell's winning repository makes failure diagnosis part of the README. Document expected startup output, port, one known-good first action, AWS-disabled behavior, and the clean stop/reset procedure.
10. **P1 — Make operational proof easy to locate.** Link the bounded evaluation command/results and observability evidence beside the relevant capability rather than burying them in a general artifacts directory. Official Strands guidance treats production operation, telemetry, and repeatable evaluation as distinct concerns; document only the parts actually implemented. [Operating agents in production](https://strandsagents.com/docs/user-guide/deploy/operating-agents-in-production/) · [Strands observability](https://strandsagents.com/docs/user-guide/observability-evaluation/observability/) · [Strands evaluation quickstart](https://strandsagents.com/docs/user-guide/evals-sdk/quickstart/)

## 5. Architecture explanation: minimum useful content

The official FAQ's required explanatory set is: **user interface/input → Strands core and agentic loop → tools/integrations → AWS services → output**. [Architecture FAQ](https://agentsforhumans.devpost.com/details/faqs)

For this project, the canonical diagram should add one essential project-specific distinction:

```text
Operator / Dashboard
        ↓ event admission
Discrepancy detector
        ↓
Strands orchestrator → scoped read tools → ERPNext / Airtable / Celigo / Jira / Slack
        ↓ hypotheses, evidence gaps, recommendation (advisory)
Investigation workspace / Manager decision
        ↓ exact approved packet
Deterministic policy + bounded executor → authoritative reread → verify → replay
```

Label **Amazon Bedrock Nova Pro** as the model used by Strands, and label **AgentCore Runtime** only on the separately proven hosted path unless the hero UI is actually routed through it. Official AWS documentation says Runtime hosts agent/tool code, supports Strands, and can be invoked with streaming responses; that does not by itself prove that any particular UI call used Runtime. [AgentCore Runtime overview](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agents-tools-runtime.html) · [Use Strands with AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/using-any-agent-framework.html) · [InvokeAgentRuntime](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-invoke-agent.html)

The authority boundary is technically defensible. Strands documentation says tools extend the agent beyond text and execute with the host process's permissions, so tool behavior must be audited for the deployment and threat model. Showing deterministic policy and bounded write tools is therefore relevant architecture, not incidental implementation detail. [Strands tools and tool security](https://strandsagents.com/docs/user-guide/concepts/tools/)

If session or observability claims appear, make them exact: AgentCore supports session IDs for contextual interactions but the client backend must maintain user-to-session mapping; default service metrics/logs and custom OTEL traces have distinct setup requirements. [AgentCore sessions](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-sessions.html) · [AgentCore observability](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-configure.html)

## 6. Recommended Devpost content pattern

Use Devpost's native story headings and keep the first screen legible without opening the repository:

- **One-sentence tagline:** concrete outcome, not a stack summary.
- **Inspiration / problem:** one real operator, one repeated discrepancy, one reason the task is risky or expensive.
- **What it does:** the six-step hero flow, written as visible user/system behavior.
- **How we built it:** Strands roles/tools, Nova model, data adapters, deterministic authority, AgentCore proof boundary, UI/event flow.
- **Architecture:** upload/embed the canonical static diagram and add a 5–7 sentence reading guide.
- **Challenges:** cross-system key/quantity reconciliation, probabilistic evidence synthesis, idempotent recovery, and source-version/freshness handling; explain the solved mechanism.
- **Accomplishments:** bounded evidence only—case matrices, dialogue tests, demo-tenant closure, reread/replay, and current AgentCore deployment/invocation proof.
- **What we learned:** why agentic investigation belongs upstream of deterministic authority.
- **What's next:** production authentication, broader connectors, production evaluation/impact—clearly future, not current.
- **Built With:** include `Strands Agents`, `Amazon Bedrock Nova Pro`, and `Amazon Bedrock AgentCore Runtime` explicitly, plus the implementation stack.
- **Try it out:** public repository, public video, and optional stable live demo.

Prior winners consistently use this progression, but the current organizers add a stronger requirement: a judge should understand what was built from the description plus video, and Strands is one of the first things reviewed. [Pro tips](https://agentsforhumans.devpost.com/updates/46174-pro-tips-for-your-project)

## 7. Video guidance to preserve for the later production pass

Only requirements and evidenced presentation patterns are recorded here; the prior winner videos were not reviewed shot-by-shot.

- Hard compliance: public YouTube/Vimeo; no more than five minutes; working demo; state the problem, who it serves, and why it matters. [Official Rules](https://agentsforhumans.devpost.com/rules)
- Organizer direction: treat it as a pitch, not a tutorial; lead with the problem, show the solution working, and make Strands visible. [Stand-out guidance](https://agentsforhumans.devpost.com/updates/45987-how-to-actually-stand-out-in-agents-for-humans)
- Recommended story: **problem/user (20–30s) → detect (30s) → Strands investigation/tool trace (75–90s) → evidence conversation and human decision (45–60s) → bounded recovery, reread, verification, replay (75–90s) → architecture/impact/limitations close (30–45s)**.
- Make the model/tool activity observable, but keep the operator's business state on screen; avoid spending the video on raw logs.
- Show one failure/degraded-state beat only if it can fit without weakening the complete success path.
- Prior winner pages commonly embed a video, show a labeled architecture, and spell out the exact demo scenario. AgentShell is the clearest example: the story enumerates the trigger, autonomous camera/tool selection, physical conversation loop, and current limitations. [AgentShell project page](https://devpost.com/software/agent-shell)
- Official winner pages embed these public videos, which can be used later for structural benchmarking: [EcoLafaek video](https://www.youtube.com/watch?v=ZWKOsdWfSsA), [Province video](https://www.youtube.com/watch?v=_ipE3EZEw40), and [AgentShell video](https://www.youtube.com/watch?v=Wt0n9WLfi5o). Their inclusion here does **not** mean their editing, timing, accessibility, or claim quality was reviewed shot-by-shot.

Because judges may rely solely on the submitted media, every critical claim should be visible or stated in the video rather than deferred to deep documentation. [Official Rules — Testing](https://agentsforhumans.devpost.com/rules)

## 8. Release gate before submission

### Must pass

- [ ] Recheck the official Rules, Overview, FAQ, and authenticated form on submission day.
- [ ] Confirm entrant eligibility and Professional Agents selection.
- [ ] Confirm the disclosure covers any non-standard pre-existing work.
- [ ] Create one reviewed release commit; ensure the public default branch shows the new README and current source.
- [ ] Commit every README image and the canonical static architecture diagram; verify them in logged-out GitHub.
- [ ] Verify root MIT/Apache license is detected in GitHub About.
- [ ] Run a clean-clone cold start using only README instructions and a blank environment.
- [ ] Run all documented quality gates from that clone and record the release commit SHA.
- [ ] Scan staged/tracked content for secrets, identifiers, PII, private tenant data, browser profiles, and incompatible assets.
- [ ] Verify default mode needs no credentials, or document narrowly scoped judge credentials/testing instructions without committing secrets.
- [ ] Cross-check every number and capability across README, Devpost, architecture, evidence matrix, and video.
- [ ] Keep direct-Strands UI and separate AgentCore Runtime claims visually and verbally distinct.
- [ ] Supply a public, playable YouTube/Vimeo URL under five minutes.
- [ ] Submit early and verify Devpost receipt before 5:00 PM PT.

### Optional after the core gate

- [ ] Stable live hosted demo with free judge access through Oct 8.
- [ ] Up to three qualifying public builder.aws posts, after resolving title wording against the current form/rules.

## 9. Confidence and unverified items

- **High confidence:** deadline, required artifacts, public-license/repo rules, architecture contents, video constraints, judging criteria, and judge-testing discretion; all were visible on current official pages on 2026-09-07.
- **Medium confidence:** cross-winner presentation patterns. Award status is official, but implementation and metrics are entrant-authored and were not independently audited.
- **Not verified:** exact authenticated Devpost field labels/options, saved-draft completeness, actual playability/editing quality of prior winner videos, and future availability of every prior winner live link.
- **Current-event winners:** none can exist yet; any claim otherwise is false as of this check.
- **Rules can change:** the rules explicitly reserve amendment rights. Final release must recheck the official pages rather than relying only on this report.

## Primary sources

### Current competition

- [Agents for Humans overview](https://agentsforhumans.devpost.com/)
- [Official Rules](https://agentsforhumans.devpost.com/rules)
- [FAQ](https://agentsforhumans.devpost.com/details/faqs)
- [Resources](https://agentsforhumans.devpost.com/resources)
- [Pro tips for your project](https://agentsforhumans.devpost.com/updates/46174-pro-tips-for-your-project)
- [How to actually stand out](https://agentsforhumans.devpost.com/updates/45987-how-to-actually-stand-out-in-agents-for-humans)
- [Time to plan your project](https://agentsforhumans.devpost.com/updates/45850-time-to-plan-your-agents-for-humans-project)

### Official technical documentation

- [Strands Agents quickstart/overview](https://strandsagents.com/docs/user-guide/quickstart/overview/)
- [Strands tools and tool security](https://strandsagents.com/docs/user-guide/concepts/tools/)
- [Strands graph multi-agent pattern](https://strandsagents.com/docs/user-guide/concepts/multi-agent/graph/)
- [Strands multi-agent patterns](https://strandsagents.com/docs/user-guide/concepts/multi-agent/multi-agent-patterns/)
- [Operating Strands agents in production](https://strandsagents.com/docs/user-guide/deploy/operating-agents-in-production/)
- [Strands observability](https://strandsagents.com/docs/user-guide/observability-evaluation/observability/)
- [Strands evaluation SDK quickstart](https://strandsagents.com/docs/user-guide/evals-sdk/quickstart/)
- [AgentCore Runtime overview](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agents-tools-runtime.html)
- [Use Strands with AgentCore Runtime](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/using-any-agent-framework.html)
- [Invoke an AgentCore Runtime agent](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-invoke-agent.html)
- [AgentCore isolated sessions](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-sessions.html)
- [AgentCore observability](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-configure.html)
- [AgentCore Runtime security best practices](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-security-best-practices.html)
- [Official AgentCore Strands sample](https://github.com/awslabs/agentcore-samples/tree/main/03-integrations/agentic-frameworks/strands-agents)
- [Official AWS sample Strands agent with AgentCore](https://github.com/aws-samples/sample-strands-agent-with-agentcore)

### Official prior winner sources

- [Official 2025 AWS AI Agent Global Hackathon winner announcement](https://aws-agent-hackathon.devpost.com/updates/38140-congratulations-to-the-winners-of-the-aws-ai-agent-global-hackathon)
- [EcoLafaek](https://devpost.com/software/ecolafaek)
- [AegisAgent](https://devpost.com/software/aegisagent-an-insurance-claim-app-fully-developed-by-kiro)
- [Province](https://devpost.com/software/province)
- [AI-driven multi-agent fraud alert triage](https://devpost.com/software/ai-driven-multi-agent-fraud-alert-triage-system)
- [AgentShell](https://devpost.com/software/agent-shell) and [repository](https://github.com/marcosanyo/AgentShell)
- [Drishti AI Navigator](https://devpost.com/software/drishti-ai-navigator) and [repository](https://github.com/akashtalole/Drishti-AI-Navigator-App)
