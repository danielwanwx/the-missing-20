# Finalization: source-grounded comparator and product-design review

Access date: **2026-09-09**, America/Los_Angeles. Scope: five relevant projects from a related prior AWS competition, current rubric, and the local R3/R4 audit record. This is bounded research and an independent documentary product-design review, not a live acceptance run, official score, or forecast of winning.

## Evidence discipline and selection

The [official AWS AI Agent Global Hackathon announcement](https://aws-agent-hackathon.devpost.com/updates/38140-congratulations-to-the-winners-of-the-aws-ai-agent-global-hackathon) confirms EcoLafaek first, AegisAgent second, Province third, AI-Driven Multi-Agent Triage the AgentCore category winner, and AgentShell the Strands category winner. These are **not winners of the ongoing Agents for Humans event**. Selection favors physical input, fragmented evidence, operational decisions, and inspectable effects over superficial domain similarity.

Evidence labels used below:

- **O — official:** reliable for award identity and published requirements; organizer praise is not a technical audit.
- **A — author:** entrant description, repository README or marketing page; verifies what is claimed, not that it works.
- **I — inspected:** content actually retrieved this session, distinguishing repository inventory/README from executable source or operation.
- **L — local audit:** our historical evidence and limitations, read this session; not a new external readback.
- **R — recommendation/inference:** our assessment, not a statement about judges' private reasoning.

The [current official rules](https://agentsforhumans.devpost.com/rules) still show September 14, 2026, 5:00 PM PDT deadline and five equally weighted criteria: Technical Implementation, Design, Potential Impact, Creativity & Originality, Presentation. Design concerns a coherent complete product; Presentation concerns an understandable working end-to-end demonstration. A working public package and truthful depiction matter even if judges choose not to run it. Current eligibility and full submission compliance are managed in the parent finalization review; this report does not certify them.

## Five cases

### EcoLafaek — physical evidence to useful spatial output

**A:** Citizens submit waste photos and GPS; authorities consume analyses. Nova-Pro classifies images; an agent selects SQL, chart, map and browser tools. Human contribution supplies location/evidence; moderation exists. Outputs are reports and visualizations, not verified cleanup. Offline caching, rate-limit feedback and tool-sequencing fixes are described; cleanup resolution and before/after verification appear under future work. The entrant reports 50+ reports, 3+ users and 25+ interactions without a reproducible measurement protocol. Its UI story connects a simple capture to a visible map. [Entrant page](https://devpost.com/software/ecolafaek)

**I:** The [current landing page](https://www.ecolafaek.com/) loads through text retrieval and links a separate dashboard; its map remained loading in that extraction. This is not live-map operation or a usage-count verification. The entrant-linked repository could not be retrieved; the embedded video fetch failed. No code or interactive workflow was validated.

**R:** Apply its clear input/output relationship to one carton and one ERP receipt. Avoid maps, citizen features and speculative analytics unrelated to receiving. Our recovery proof addresses a different, valuable boundary: confirmed external action after an uncertain response.

### AegisAgent — ambiguity becomes a reviewable decision artifact

**A:** Insurance reviewers upload photos, invoices, forms and policy PDFs. Evidence curation, clause retrieval and adversarial review feed a cited decision packet with objections and clarification checklist. Blocking missing evidence pauses the process and returns a resume packet. Tools include EXIF/invoice/PDF processing and FAISS policy search. The described effect is a recommendation/download package, not claim payment. Human input resolves evidence gaps. Batch output is current; progressive streaming and a formal synthetic evaluation harness are future work. Real-data scarcity is admitted; no externally verified accuracy or ROI is supplied. [Entrant page](https://devpost.com/software/aegisagent-an-insurance-claim-app-fully-developed-by-kiro)

**I:** The linked [App Runner endpoint](https://3vhp3hyhxz.us-east-1.awsapprunner.com/) returned HTML. No artifacts were uploaded or inference invoked. No repository link appeared in the retrieved project page; its embedded video fetch failed. Reproducibility and restart semantics remain unverified.

**R:** Borrow explicit missing-proof/resume artifacts. Do not copy an adversarial critic merely because the narrative is convincing: our R4 same-model critic already failed independent semantic review. Concrete source contracts and measured corrections must justify any additional model role.

### Province — document input becomes an inspectable form

**A:** Taxpayers provide conversational answers and W-2/1099 documents. Intake, planning, form mapping and review agents extract data, retrieve rules, calculate and populate PDFs. Bedrock, Lambda, DynamoDB and S3 support processing and cached mappings. A document/form workspace and versioned PDFs make output inspectable. Users supply missing facts; the exact final authorization/e-filing boundary is not established. Iterative mapping repairs and form versioning are described, not transaction replay recovery. The prominently reported success is **21/21 filled fields**; it does not prove universal tax accuracy or audited speed improvement. [Entrant page](https://devpost.com/software/province)

**I:** No repository link appeared in the retrieved page; the [linked product site](https://www.provincetax.com/) and embedded video failed retrieval. No filing, calculation or source code was independently exercised.

**R:** Borrow a preview tied to exact source fields and document version. For our product, show receiving confirmation, resulting submitted receipt and current readback together. Avoid broad financial accuracy claims, arbitrary document generation, or treating completed form fields as proof of a completed regulated transaction.

### AI-driven multi-agent fraud alert triage — explicit routing and durable output

**A:** Compliance analysts start with alerts, enriched from Athena account/customer/transaction data. Triage combines historical/allowlist rules with model assessment, then dismisses, queues or escalates. Investigation analyzes relationships; reporting stores structured SAR summaries in S3 for compliance review. A React UI collects analyst feedback. Durable report generation is described; legal submission and funds movement are not demonstrated. Inter-agent communication and JSON reliability are stated challenges; lost-response recovery is unspecified. The page claims up to 60% false-positive reduction in pilots, but supplies no denominator, dataset, control, uncertainty or evaluation protocol. [Entrant page](https://devpost.com/software/ai-driven-multi-agent-fraud-alert-triage-system)

**I:** No public repository or live-demo link appeared in the retrieved page. The embedded Vimeo fetch failed. We did not validate the system or its impact claim.

**R:** Borrow the understandable choice between routine handling and exceptional investigation, followed by a durable business record. Avoid one service per agent, autonomous feedback calibration, or additional streaming infrastructure unless measured need exists. A normal partial receipt should not become a manufactured exception for dramatic effect.

### AgentShell — agent-selected action is visible

**A:** A user requests help through a camera conversation; Strands chooses camera-prefixed MCP tools for vision, speech, listening and movement. ONVIF/go2rtc and AWS voice/vision services produce physical responses. Human instructions drive the example visitor workflow. Sequential execution mitigates tool conflicts, but durable crash/replay behavior is not established. Hardware-cost comparisons are not controlled operating-cost measurements. [Entrant page](https://devpost.com/software/agent-shell)

**I/A:** The [public repository](https://github.com/marcosanyo/AgentShell) exposes MIT license, dependency manifest/lockfile, environment sample, Dockerfile and startup documentation. README explicitly limits Alexa to the Developer Console simulator and says authorization mechanisms are planned, despite broad security wording elsewhere. It supplies a specific two-camera scenario and troubleshooting. This is **repository/README inspection, not code verification**: source-directory and raw-source requests failed. No code executed. Embedded video retrieval also failed.

**R:** Borrow observable tool choice and a precise judge path, not hardware or voice. For us, the equivalent is changed evidence causing a changed safe action, then the exact external record changing. Keep limitations next to the demonstration claim rather than only in a separate appendix.

## What is and is not established by the comparison

The selected projects communicate clear input, work and output patterns. That is a descriptive observation, not a causal explanation of their awards. The public evidence does not support a fair numeric head-to-head ranking: most comparator code and demos were unavailable to this retrieval, and none was run. Their self-reported metrics cannot be used as baselines for our warehouse task.

The bounded retrieval failures are also not proof that those projects are currently broken. Web extraction may fail independently of browser availability. We did not bypass access controls, install their dependencies, run untrusted code, call their models, or mutate their services. For EcoLafaek's repository and all five videos, the attempted links were the GitHub/iframe links on the cited entrant pages. AgentShell source attempts were its `strands_agent` directory and `core.py` / `agentcore_app.py` on raw GitHub; a secondary read-only local fetch failed DNS. Further retrieval is not required to adopt the narrow documented patterns above.

## Independent design/presentation assessment of our baseline

**L:** This assessment read the complete [R4 audit](../audits/2026-09-09-r4-automatic-receiving-recovery-review.md) and [R3 audit](../audits/2026-09-09-r3-receiving-jira-conversation-review.md), plus the handoff and September 3/7/8 competition research. It did not inspect current UI pixels or reproduce the audits' provider calls. R4 supersedes earlier conversational acceptance language: experiments were reverted and whole-product acceptance remains withheld.

| Claim → current evidence | Rubric relevance | Gap and risk | Action and observable acceptance |
| --- | --- | --- | --- |
| Recovery is real → R4 records one submitted receipt, uncertain ACK, restart lookup and unchanged ERP/Airtable/Slack identities | Technical Implementation; Design | Powerful proof is buried in diagnostic terminology; user could mistake uncertainty for permission to retry | P0: show one human-readable state history: confirmation, submission uncertain, verifying existing record, receipt verified. On a retry question explicitly answer whether a write retry is safe, with current source evidence. Verify no second effect. |
| User starts from physical evidence → R4 public photo, typed QR and explicit simulated confirmation | Design; Presentation | Viewer may infer real camera scanning or contents recognition | P0: disclose substitute input visibly at its use; show identifier and confirmed quantity/UOM before the effect. Actual camera trial, if performed, gets separate evidence. |
| Agent handles operations questions → R3/R4 real conversations include incomplete retry answers and financial misinterpretation | Technical Implementation; Design | Empty validated output and fluent wrong output both block task completion | P0: acceptance requires complete answers to the actual operator question, fresh case-specific facts and refusal/correction handling; three repeated core conversations plus held-out scenarios and independent semantics. Schema success alone fails this gate. |
| Remaining PO quantity is understood → R4 shows 1/40 Box, 39 outstanding, no gap | Potential Impact; Creativity | A dramatic “missing 39” narrative would be false; ERP observation alone does not prove physical loss | P0: keep ordered, evidenced received, posted and outstanding distinct in prose, chart and agent answer. Test normal partial arrival versus contradictory arrival evidence. |
| A closed business chain exists → R4 has receipt and notifications; no invoice/dispatch/billing for this case | Design; Presentation | Cutting in the old 20-unit sales story fabricates continuity | P0: freeze one chosen case, version and sequence. Either complete an authorized justified downstream path for that case or narrow the stated result to receiving. Every displayed outcome must link to that case's real evidence. |
| Impact is measurable → R4 has one historical observation; R3 repeated state observations are not deliveries | Potential Impact | Inventory trend and demo invoice dollars do not prove saved labor or new revenue | P1: matched manual/agent task measurement with active time, total time, touches, errors and model cost; report sample size and limits. Show insufficient history honestly. |
| Product is usable → R4 gallery external links and R3 selected external pages were inspected | Design | These checks omit whole-page lifecycle and error-state acceptance | P0: mouse-walk every reachable action on frozen version; capture state changes and external object identities. Test correction, refusal, reload and interrupted connection, not just happy-path green statuses. |
| Package is reproducible → historical audits describe local runtime and retained tests | Technical Implementation; Presentation | Local success does not establish free judge access or clean-clone operation | P0: run documented default path from a clean checkout, separate replay/live claims, verify assets and exact commands, record release SHA and access longevity. |

**Independent verdict:** Design and Presentation are **not ready for full acceptance** on the documentary baseline. Confidence is high about the explicitly recorded gaps, low about visual polish because no current screenshot or mouse session was performed here. A numeric score would imply evidence we do not have. R4's recoverable external effect is worth preserving; it does not cancel the conversation and continuity blockers.

## Design decisions to carry into implementation review

1. Retain the receiving-manager focus. Make the first screen answer which order, what arrived, what the agent checked, what changed externally and whether the human must act. Integration counts are secondary evidence.
2. Separate the source-backed decision artifact from the conversational explanation. The explanation may be flexible; case identity, source version, quantities, uncertainty and allowed next actions must be explicit and independently checkable. This is a design recommendation, not approval of the reverted typed-decision experiment.
3. Show one meaningful alternative cause or correction. The same outstanding quantity can reflect expected later arrival, uncertain posting, identity conflict or quality hold. Demonstrate which evidence changes the answer and why; keep deterministic quantity/accounting checks out of model discretion.
4. Keep the established silver/light-gray UI and useful metrics. Prefer one current outcome and a directly accessible evidence trail; do not add nested cards, decorative agent topology or a new visualization stack to repair semantic failure.
5. Reuse Strands and existing execution journals. Any specialist, memory or evaluation dependency needs a bounded failure it fixes and comparison evidence. Prior-winner agent counts supply no engineering justification.
6. Freeze the actual story only after acceptance. A short candidate sequence is input → routine receipt → uncertain acknowledgement → autonomous source verification → operator asks whether to retry → correct grounded answer → exact ERP/SaaS records. This proves receiving recovery only. Add later financial steps solely if independently supported on the same case.

Completion boundary: the five-case source-grounded research and documentary design critique are complete. Implementation, current UI acceptance, live semantics, final video, formal submission and production readiness are outside this report's verified scope.
