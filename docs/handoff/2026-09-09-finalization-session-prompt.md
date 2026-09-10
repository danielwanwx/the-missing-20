# The Missing 20: Complete Handoff Prompt for the Next Stage

Handoff date: 2026-09-09. The text below can be handed to a new session as a whole.
This is a work instruction and the baseline as of handoff, not a full-product acceptance report or the competition rules rechecked online in this round.

---

## Your Task and Delivery Goal

You are taking over the next-stage finalization of **The Missing 20**. Do not start over, write only a polished plan, or assume the previous owner completed the full business path.

First research the competition, notable work, and industry needs comprehensively, objectively, and from primary sources; then use current code, real runs, and external-system evidence to judge the gaps; define a design, test, and independent-review plan; and continue fixing, integrating, and testing within existing authorization until there is a clear submit-ready version or an accurate list of blockers you cannot solve yourself.

The goal is for judges to understand and verify that, after the user supplies one necessary physical input, a real Strands Agent can investigate, link, process, and verify business work across isolated business software; normal steps advance automatically, while unclear identity, insufficient evidence, rule conflicts, or important decisions require a person. The value is less duplicate entry and cross-system investigation, fewer errors and lower handling cost, and better fulfillment. It is not a chatty report or an animation that jumps numbers.

Judge these separately: **competition eligibility, competitiveness against comparable work, demonstrable business loop, production deployability, and real commercial benefit**. They are different conclusions. Do not promise a win, treat test-environment invoice totals as new revenue, or call partial test success production-ready.

## 1. Workspace, Versions, and Reading Order

- Repository: /Users/danielwan/Documents/Hackathon/Agents-for-Humans/the-missing-20
- GitHub：`https://github.com/danielwanwx/the-missing-20`
- Branch: main.
- Most recently verified product-fix baseline: aa4966e9ee86a84595d9d23b31d5fd8b711d5aaa. At handoff, local HEAD matched origin/main. This handoff file may be in a later documentation commit; check Git again at startup and do not hard-revert to this SHA.
- Fully read the currently applicable AGENTS.md and relevant skills first. Use Loop Engineering as appropriate; use available skills for research, diagnosis, design, code review, UI/architecture diagrams without claiming to have called a skill that does not exist.
- There are many old untracked research/test artifacts and local run stores. Determine ownership item by item, preserve user work, and do not run git add ., force reset, overwrite databases, or globally delete sessions.
- The user's browser may still be on the old receiving workspace at 8893. The most recently verified R3 is 8896 and R4 is 8897. Check processes, launch arguments, run directories, and API case_id first; do not infer the newest environment from an open page.

Read in this order (all paths below are relative to the repository):

1. docs/audits/2026-09-09-r4-automatic-receiving-recovery-review.md: latest facts and failure boundaries, taking precedence over old “all passed” wording.
2. docs/audits/2026-09-09-r3-receiving-jira-conversation-review.md: the prior round's Jira, receiving, and conversation issues.
3. docs/research/2026-09-08-warehouse-workflow-gap-baseline.md, 2026-09-08-warehouse-operations-primary-research.md, 2026-09-08-operational-history-benchmark-design.md.
4. docs/research/2026-09-08-photo-to-work-design.md, 2026-09-08-scan-to-work-upgrade-proposal.md, 2026-09-07-integrated-upgrade-proposal.md.
5. docs/research/2026-09-09-conversation-oss-options.md, 2026-09-08-multi-agent-primary-source-review.md, 2026-09-07-revenue-efficiency-causal-validation.md.
6. docs/research/2026-09-03-official-competition-rubric-check.md, 2026-09-07-submission-and-winner-readme-benchmark.md, 2026-09-08-winner-direction-comparison.md.
7. docs/submission/, README, the current architecture diagram, and existing release/evidence files.

Some historical material exists only in local untracked directories and may be absent from a new remote checkout. Check what exists first; if something is missing, record that and reconstruct only from available source, committed evidence, or official sources. Do not imagine content. Gaps described in old research may already be fixed, so recheck each one instead of mechanically repeating the old work.

## 2. Actual State at Handoff: Do Not Confuse the Three Cases

### R4 New Photo Receiving: Only a Limited Slice Passed This Round

- Case: M20-GOODS-20260909-40-R4; PO: PUR-ORD-2026-00016.
- Synthetic test order for 40 Box at USD 50/Box; only **1 Box** was confirmed received and posted, while the other 39 are outstanding order quantity, not proven loss.
- Capture: 1cbc0f589421cef6c5c828536bb14a53; real Purchase Receipt: MAT-PRE-2026-00007.
- Used a publicly available single-box photo at tests/fixtures/photo_receiving/p05.jpg, with real Strands/Bedrock analysis, a demo QR identity, and explicit simulated operator confirmation. This does not prove physical transport, a real camera-video scan, or the quantity inside a sealed carton that was not visible.
- After ERP really submitted successfully, the diagnosis dropped one ACK at the application boundary; state persisted as SUBMIT_UNKNOWN. A normal service restart automatically verified the original document read-only and recovered to RECEIPT_SUBMITTED without submitting inventory again.
- Real Airtable record rec0RfqlevwmdoLgt and Slack message 1788986162.337109 through Celigo; restart, three duplicate requests, duplicate-photo tests, and external readback produced no duplicate business effect.
- Links from Dashboard/photo details to ERP, Airtable, and Slack were opened with the mouse and checked against specific records; this is not acceptance of every page screenshot or every feature.
- R4 has only one real historical observation and no sufficient historical baseline; there is no new invoice, shipment, sales invoicing, or revenue-lift proof for this order. Normal receiving does not force-create a Jira exception.
- This slice was independently approved; final code passed Python **1,550** tests and frontend **98** tests. This does not establish reliable complex multi-turn semantics for the real model.

R4 evidence: artifacts/audits/2026-09-09-r4-{demo-order,real-lost-ack,replay,restart-handoffs}.json and artifacts/tests/2026-09-09-r4-shipped-regression.xml.
Note that readback.before_restart is **after the first recovery and before the second restart**, not a pre-failure snapshot.

### R3 Conversation: Still a Critical Failure

- Case: M20-GOODS-20260909-40-R3; PO15; PR5 and PR6 1 Box each, 2/40 Box total.
- The real Agent performed cross-source reads and a three-question continuous conversation, but a run could pass the runtime contract while its business answer was wrong: it omitted whether to retry and confused inventory trends with evidence needed to prove benefit.
- Source compaction, an additional same-model critic, and typed-decision restrictions were tried; independent review failed, and the final version failed the first question three times in a row. **All of these conversation experiments were withdrawn and never shipped.**
- Do not transfer the old 8/8 and 15/15 scores to this new photo-receiving, multi-turn problem; JSON/schema/keyword hits are not semantic correctness.
- Some conversation artifact filenames contain r4, but the actual JSON case_id is R3; use the internal field.
- Required failures to read: artifacts/audits/2026-09-09-r4-answer-diagnostic-v2.json and 2026-09-09-r4-typed-decisions-final.json. Do not pile on the same prompt, regex, and self-evaluator again.

### Old 20-Unit Order Fulfillment: Evidence Remains Independent

Old submission documents describe a 12/8 split, a USD 42,000 sales order, Delivery Note, Sales Invoice, and related results. This may be useful evidence from an existing independent scenario, but **it does not mean the new R3/R4 photo flow is connected to those business effects**. Check its version, sources, actual execution path, and proof scope before using it.
In particular, inspect the old “latest,” “passed,” and “only write path” wording in docs/submission/judging-map.md, known-limitations.md, and devpost-submission-draft.md; it may be stale after the photo-receiving extension.

## 3. Phase One: Recheck Competition and Winning-Work Benchmarks

The user's “DevCourse” may mean Devpost in context. Confirm from existing competition evidence first and do not get stuck on the typo.

Entries to recheck live:

- Competition home: https://agentsforhumans.devpost.com/
- Rules: https://agentsforhumans.devpost.com/rules
- FAQ: https://agentsforhumans.devpost.com/details/faqs
- Organizer advice: https://agentsforhumans.devpost.com/updates/45987-how-to-actually-stand-out-in-agents-for-humans
- Recent official winners announcement for a related competition: https://aws-agent-hackathon.devpost.com/updates/38140-congratulations-to-the-winners-of-the-aws-ai-agent-global-hackathon

**Historical record, not a currently confirmed fact:** the local 2026-09-07 research record says the deadline was 17:00 Pacific on 2026-09-14, judging through October 8, results expected October 14, and five equally weighted areas: Technical Implementation, Design, Potential Impact, Creativity & Originality, and Presentation; it also lists Strands, English explanation, public code with an MIT/Apache license, an architecture diagram, Builder ID, and a video up to five minutes. Reopen the official pages to check the year, dates, timezone, exact requirements, and changes. Do not merely repeat the old document.

The research output must answer:

1. What hard eligibility, track, SDK/AWS use, materials, access, and licensing requirements are current, and which have evidence of being satisfied?
2. If this edition has not ended, do not invent “past champions of this competition.” Distinguish the same event, related AWS/Strands events, other enterprise-agent competitions, and commercial products.
3. Confirm identities from official winners announcements, then read project pages, public code, and demos. Start with old research leads such as EcoLafaek, AegisAgent, Province, AgentShell, and AI-driven multi-agent fraud alert triage, without assuming they remain the best comparisons.
4. Build deep comparisons for 4–6 relevant works/products rather than listing dozens: target user, starting input, what the Agent does autonomously, tools and external effects, required human review, failure recovery, UX, reproducibility, measurement, strengths, and weaknesses.
5. Label creator statements, vendor case marketing, third-party discussion, and your code/hands-on verification separately. Do not turn an inference into “judges awarded it for this reason.”
6. Identify our strengths, weaknesses, useful lessons, and complexity not worth copying as a **claim → evidence → rubric → gap → action** map.

Attach direct sources, access date, credibility, and limitations to important conclusions. State honestly when a repository or video is inaccessible; a search snippet cannot replace key evidence.

## 4. Phase Two: Industry Reality and Quantifiable Impact

Judge one clear ICP deeply: is a parts-distributor warehouse receiving Manager still the best main path? Treat parcel stations, 3PL, and toC only as fit comparisons, without unbounded expansion near submission.

Study the actual daily chain: PO/ASN → partial arrival and scan/photo → identity/UOM/batch match → receiving/quality inspection/putaway → inventory and order allocation → picking/hand-off → linked billing and reconciliation → exception ticket/collaboration → verified closure. What master data, roles, documents, permissions, onsite facts, and system events are needed?

Prioritize ERPNext, mature ERP/WMS/TMS, GS1, logistics/accounting documents, and verifiable industry cases; use practitioner discussions to find friction and state sample bias. Answer:

- Which steps are already sufficient with software rules/RPA, why is an LLM needed, and which information requires cross-system reasoning rather than a visible 100−80 calculation?
- What can a photo infer? Is a barcode only an identifier or does it provide price? Which authorized master data supplies price/unit conversion instead of visual guesswork?
- What supports financial entry? A photo cannot prove that a supplier invoiced, QA released, a customer signed, or payment occurred.
- Which steps can run automatically at low risk, which require added evidence/authorization, and how should model planning cooperate with deterministic execution boundaries rather than stopping every step for a person?
- Where will production fail most often: identity and permissions, idempotency, concurrency, old data, cross-document mismatch, replay, supplier quotas, human-review burden, observability, or recovery?

Build measurable business hypotheses: active human time on the same task, Agent total time/p50/p95, manually entered fields, touches, cost per exception, error/duplicate-posting rate, evidence-round count, necessary human-review rate, throughput, backlog, and completion rate.
Define revenue/gross margin/cash flow/order value/value protected/model cost separately and never mix them. Measure with comparison tasks and equal workload; state formulas, assumptions, data sources, and sensitivity. Without a production pilot, do not claim a production-measured lift. ROI is a hypothesis to test, not a positive number to invent.

Separate three benchmarks: same-company historical operating baseline with the same denominator, public industry reference, and Agent versus human/old-process task comparison. The mean of cumulative inventory snapshots is not receiving speed or an industry-efficiency baseline; repeated polling is not a new sample. Charts must show unit, time window, sample size, source, comparability, and missing state. Public/synthetic references cannot masquerade as our operating history.

## 5. Phase Three: Check the Gaps and Freeze the Design

First create one authoritative task-and-evidence ledger, with requirement, current state, case/code version, evidence, gap cause, business risk, acceptance condition, priority, dependency, owner role, estimated effort, and submission date for every item.
At minimum distinguish: NOT_STARTED / IMPLEMENTED_NOT_VERIFIED / VERIFIED_IN_DEMO / FAILED / BLOCKED / DEFERRED. A written spec is not implementation; a passing unit test is not an external-write pass; a source read is not proof that the Agent used it.

Order P0/P1/P2 by value, risk, and dependency before the competition, prioritizing:

1. A real multi-turn Agent that stably answers complex business questions with correct current evidence, accepts human refusal/correction, and does not treat an old assistant output as current fact.
2. Complete the missing link for one new order: physical input → receipts → downstream document/task → necessary approval → exact external effect → readback.
3. Correctly distinguish normal partial flow from complex exceptions, while the frontend synchronizes real state and useful trends/baselines.
4. Cold start, expired authorization, disconnect, restart, replay, and demo stability; expand modules and packaging afterward.

Also maintain two explicit lists: the closed loop required for this competition submission, and engineering/organizational conditions required before a production pilot. Production suitability does not mean rebuilding an entire enterprise platform before the deadline; low-relevance security long tails must not displace the main path, but credential protection, authorization checks, idempotency, and error display cannot be omitted.

Design files must state: current and target architecture, objects/units/identifiers, state machine, event and source-version contract, actual responsibility of each Agent role, handoffs, tool contract, necessary human review, read/write permissions, transaction/idempotency/recovery, history and metric definitions, dialogue/UI data contract, migration compatibility, failure presentation, rollback, test matrix, and stop conditions.

Reuse Strands; add specialist/memory/evals/other open-source components only when evidence shows value. Do not mechanically create one Agent per SaaS or migrate frameworks to hide evidence-modeling problems. For new dependencies, confirm license, pinned version, maintenance, privacy/service cost, and integration measurement. Before a model upgrade, verify permitted models, actual SDK compatibility, and cost without bypassing AWS permissions.

After design self-check and independent review pass, continue implementation within authorization without asking the user step by step again. If direction, cost, or external permissions materially change, pause only the affected step, present concrete choices, and continue independent work.

## 6. Required Validation Matrix

### Business and Physical Inputs

- Normal one-batch and partial receiving: do not misreport an unexpired remaining PO quantity as lost; each batch adds only the quantity represented by a real record.
- Multi-angle/same photo, repeated scan, refresh, disconnect, and restart: one physical-arrival identity produces only its intended business effect.
- Wrong SKU, wrong PO line, box/piece conversion, mixed SKU, occluded/low-quality photo, label conflict, or unknown barcode: do not guess identity or price and force a posting.
- Submitted-with-lost-ACK and never-submitted branches, stale confirmation/version, source conflict, concurrency, and partial SaaS failure: determine the current state first; do not blindly retry a write.
- Quality hold and later compliant release, added evidence, refusal, correction, and recovery: necessary human review appears accurately, and rejection does not continue writing silently.
- Invoice/reconciliation/fulfillment in the new receiving chain: create documents only for supported quantity and amount; do not treat draft, order, receipt, invoiced state, and cash as the same result. Never trigger real payment.

### Agent and Multi-Turn Interaction

Cover at least sessions for state comparison, basis follow-up, denial of the initial assumption, refusal of execution, new evidence, continued investigation, a request for a historical chart, an impact question, a retry question, case switching, and source interruption.
Freeze core scenarios and an independent holdout; run each key conversation with a real model at least three times. Report every attempt, failure, latency, token count, and cost rather than only the best run. Let state and failure mechanisms determine quantity and complexity; do not make unlimited calls without purpose.

Check answer completeness, numeric/UOM/identifier correctness, source freshness, reasoning that distinguishes competing causes, correct chart denominators, useful clickable follow-ups, and direct answers to important questions. When data does not exist, explain exactly what is missing rather than saying only “need more information.”

Use deterministic checks for identity, scope, quantity, permission, execution, and evidence closure; use independent semantic review for explanation quality. An LLM judge is not the sole truth; do not repeat this round's unreliable same-model critic and force it into production.

### Frontend and External Systems

Operate Dashboard, Investigation, photo/scan entry, chat, charts, approvals, links, and error recovery fully with a real mouse. Capture screenshots page by page and inspect key states; every clickable element must have understandable behavior, real parameters/evidence, or a clear disabled reason.
Also inspect actual external pages participating in the path, including ERPNext, Airtable, Celigo, Jira, and Slack, and check object, quantity, status, and link; do not only screenshot the dashboard or show a green connection light.

Do not lose the user's preferences: light gray/silver-white, Geist-style font, clear contrast, necessary solid highlights; simple modules, few nested frames, thin accurate connections; use direct links where possible, keep lines out of text, and use no glowing dots at both ends. Do not add headings, gray explanations, or framework labels with no operating value.
Keep the backend's real features, menus, and necessary metrics. Prioritize the main screen, with explanation and detail on demand; dynamic changes must come from external events or actual tool execution, not manufactured traffic, and a success label must not appear before its stage.

### Independent High-Standard Review

Use reviewers/subagents independent of the implementer (this task explicitly authorizes that use) for warehouse operations, Strands/backend engineering, product design, commercial impact, and release reproducibility. If slots are limited, review in rounds; the main task must not pretend to be an independent judge.
Give them frozen versions, scenarios, judgment rules, and raw evidence without demanding a high score. Mark whether each conclusion comes from actual operation, code reading, or inference, and list blocking defects and retest results.
Score with the current official dimensions and explain confidence, marking unscorable when needed; the project's internal scale is not an official score. Severe business errors, fabricated success, duplicate posting, permission overreach, and unreachable key flows outrank attractive screenshots and average scores.

## 7. Competition Schedule, Materials, and Finalization Coordination

Create docs/submission/finalization-tracker.md (or update an equivalent existing file rather than duplicating ledgers) to manage:

- Official deadline, timezone, verification time, organizer changes, duration of judge access, planned freeze, and submission buffer.
- Actual state of the current Devpost draft/entry; old material records submission 1162519, which must be verified in the authorized account and must not be assumed submitted.
- README, accurate readable static architecture diagram, English project explanation, dependencies/licenses, image rights, environment template, reproducible startup and judge path, evidence matrix, known limitations, and release code version.
- Video script/story/storyboard/recording-material readiness. **Make the actual final recording after the business path is frozen**; do not spend large effort first on a promotion that cannot be reproduced.
- Public repository, usable demo/test package, free judge access, account/quota/trial duration, expired credentials, test data, and failure fallback path.
- Status, owner, blocker, next step, and acceptance evidence for every item. Adjust required scope daily based on time remaining; if the competition date changes, recalculate rather than following an old “there is still time” judgment.

Validate the product with one coherent story understandable in five minutes: real input → normal processing → an unexpected state with no initial answer → Agent cross-system cause-finding/evidence gathering → necessary human review or refusal → precise business action → external record/trend/bounded impact proof.
Do not stitch fragments from different orders, run modes, or versions into one continuous loop without proof.

## 8. Permissions, Runtime, and Failure Handling

The user has authorized real orders, tickets, receipts, updates, related invoice tests, and real model calls within the project's demo scope; **real payment is prohibited**. New paid subscriptions, purchases, production data/operations, expanded IAM, or destructive deletion require renewed confirmation. Use only configured and approved demo targets.
Do not request permission repeatedly for every step. Human involvement is required for a verification code, actual user login, or a new material boundary. Never put passwords, tokens, OTP codes, private OAuth callbacks, database contents, or session contents in chat, reports, or Git.

Existing local run directories: .missing20-goods-20260909-r3 and .missing20-goods-20260909-r4. They are machine-local state and not in Git; verify before reuse.
Example startup commands used (first check ports and current processes to avoid duplicate instances):

```sh
.venv/bin/python scripts/run_goods_workspace.py --runtime-directory .missing20-goods-20260909-r4 --port 8897 --enable-handoffs --pause-auto-prepare
PYTHONPATH=src:. .venv/bin/python -m pytest -q
npm test
```

Local tests need temporary HTTP ports allowed; a sandbox Operation not permitted is not a business failure. AWS has historically produced expired login links and invalid request; generate a current authentication request rather than reopening an old link or deleting every account session.
Before handoff, Missing20DeveloperRole received AccessDenied for bedrock:ListFoundationModels, while the configured Nova Pro call worked; do not treat catalog permission failure as all model-call failure or change IAM blindly. Recheck current state.

Main entry points: agents/live_advisory.py, agents/receiving_advisory.py, agents/photo_receiving.py, agents/role_delegation.py; adapters/live_advisory_gateway.py, photo_receiving.py, receiving_draft_worker.py, receiving_handoff*.py, receiving_destinations.py, receiving_jira.py, demo_executor.py; scripts/decision_workspace_server.py and workspace/.
Resolve actual paths from src/the_missing_20/ and read the code first; do not infer feature completion from filenames.

scripts/diagnostics/prepare_receiving_lost_ack.py **really writes and deliberately drops an ACK**. Use it only with a newly created, configured, isolated single-box test store; do not rerun it against R4 to “fix” anything. Read the script before any read/replay test to confirm its boundary. Tests must not overwrite retained success or failure evidence.

## 9. Execution Loop and Stop Conditions

Follow: goal → input → small step → check → adjust from failure → record → decide whether to stop.

- If a key source is missing: check official sources, code, or the real API; if it remains missing, mark unknown and do not fill the gap with a guess.
- Regression failure: locate the cause, make the smallest fix, rerun the original failure and related regressions; do not delete assertions or hide failure to get green.
- Three consecutive failures for the same model problem: retain raw records, stop ineffective retries, and use an evidence-based diagnosis or alternative; do not pause unrelated work.
- If an independent reviewer finds P0/P1: fix it and request a retest, not merely reply “noted.”
- After each independently accepted optimization: stage, commit, and push precisely; verify the remote SHA. Do not make only a local commit, force-push, or include unrelated changes.
- Release, video, and final-submission actions follow current authorization and any explicit final-preview gate in the applicable skill; being prepared does not mean formally submitted.

A successful terminal state requires: a clear version, official hard-requirement list, actual evidence for one business chain, core complex matrix and real multi-turn tests, page-by-page/external-system acceptance, independent review and defect-closure record, reproducible startup, and materials-ready checklist. If blockers remain, report actual status only; do not use “all passed,” “production-grade,” or “guaranteed winner.”

## 10. What You Ultimately Deliver to the User

1. A reliable-source comparison of the competition, industry, and notable work that directly guides tradeoffs.
2. A current capability and gap ledger that clearly states what is retained, improved, or abandoned and why.
3. An implementable design, test matrix, impact-validation plan, and independent-review plan.
4. Actually fixed and integrated code, real external business records, and complete success/failure test evidence.
5. Frontend and external-system operation records and key screenshots that show the Agent's work and business results.
6. README, architecture diagram, Devpost copy, video story, and competition schedule tracker completed or accurately marked with gaps.
7. Independent judge conclusions, open risks, current submission and remote-push proof; state clearly whether it is ready to submit, conditionally ready, or not ready, and why.

Start by checking repository and runtime state and reading the latest R4 audit and related historical material, then research official rules, notable work, and industry comparisons; do not begin by piling up UI or again claiming the whole product is complete.
