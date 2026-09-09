# Strands conversation memory: verified options and finalization decision

Checked 2026-09-09. Research/design only; no SDK upgrade or memory feature accepted as implemented. Product remains NOT_READY. Baseline main/local/remote: a600fe5461238b1ac7bffbd1c3819926c5acf544.

## Current progress and competition gap

Five accepted commits were pushed and remote-verified: rules/claims research, receiving fact/reference contract, truthful history empty state, clean-start configuration/quality repair, dashboard source authority. Independent clean-start gate passed 1,566 Python tests and 98 JavaScript tests; subsequent UI changes passed 100 JavaScript tests plus 49 submission-package tests. These are scoped checks, not full product acceptance.

Three repeated real receiving sequences produced one narrowly acceptable three-question sequence, one semantically wrong sequence, and one token-budget failure. This tiny diagnostic sample is not a population success rate. R4 confirmed one 1-Box receipt against 40 ordered, restart reconciliation without duplicate stock, and downstream collaboration readbacks. Same-order invoice/shipment/revenue continuation is not demonstrated. Historical 20-unit/42,000-dollar evidence cannot substitute for R4.

The current synthetic-case UI with real Bedrock also fails its first diagnosis: all six required tools succeed, but three candidates return NEEDS_EVIDENCE against supported RECOVERY_READY. This is a separate reasoning/validation failure before conversational history exists. Error UI incorrectly suggests provider unavailability. Full current UI smoke, real multi-turn held-outs, impact measurement, final video and final submission/free judge access remain open. No probability of winning is justified.

Official rubric has five equally weighted dimensions: technical implementation, design, potential impact, creativity/originality, presentation. Our concrete differentiation is verified cross-system effects and safe recovery; award competitiveness still needs a repeatable complete business journey, coherent UX, measured operator benefit, and a compelling accurate demo. [Rules](https://agentsforhumans.devpost.com/rules), checked earlier this session. Deadline September 14, 2026, 17:00 Pacific.

## Installed SDK and wiring

Direct installed-source/import inspection: strands-agents 1.53.0; pyproject requires >=1.53.0,<2. The optional strands-agents-tools distribution is absent; native conversation/session functionality does not require it.

Installed native capabilities include SummarizingConversationManager, proactive_compression configuration, FileSessionManager, S3SessionManager, SnapshotSessionManager, and Agent(context_manager='auto'/'agentic'). The auto facade combines summarization/proactive compression and context offloading. Existing live_advisory Agent construction selects none of these explicit options, so it uses default SlidingWindowConversationManager. It reuses the Agent within one request's acquisition/synthesis/repair phases, but constructs another Agent on the next HTTP question. Gateway retains at most three display-history turns as prompt text; receiving excludes prior assistant prose and adds source-checked receipt reference candidates.

Consequently, merely configuring a summarizer on today's short-lived Agent does not supply cross-request memory. Need stable conversation identity and restoration, or an explicit persisted bounded handoff. Existing application conversation storage is not SDK session restoration.

[Official conversation management](https://strandsagents.com/docs/user-guide/concepts/agents/conversation-management/): native sliding window is default; summarization reduces older messages, supports retaining recent messages and custom summary instructions. Compression is not an unconditional after-every-human-turn summary. [Official sessions](https://strandsagents.com/docs/user-guide/concepts/agents/session-management/): session managers persist conversation/state; current documentation recommends SnapshotSessionManager for new single-agent sessions, with repository managers retained for compatibility and orchestrators. Local 1.53.0 exports SnapshotSessionManager; compatibility must still be tested against our lifecycle.

## Upgrade findings

Live PyPI JSON and GitHub releases API checked directly after sandbox DNS failed: latest Python is 1.55.1, published 2026-09-09 21:24:09 UTC. GitHub's old sdk-python URL redirects to harness-sdk; cached releases/latest returned a TypeScript release, so it was not used as Python version evidence.

[1.54.0](https://github.com/strands-agents/harness-sdk/releases/tag/python/v1.54.0) includes cached-token accounting in context/compaction and message normalizer mutation fixes. [1.55.0](https://github.com/strands-agents/harness-sdk/releases/tag/python/v1.55.0) includes context offloading/stash/session work, experimental context exports and orphan tool-result cleanup. [1.55.1](https://github.com/strands-agents/harness-sdk/releases/tag/python/v1.55.1) includes malformed snapshot-ID filtering and context parity fixes. These are reasons to test an isolated upgrade, not evidence that upgrading fixes our semantics. Release notes mix monorepo languages: do not interpret TypeScript Node requirements as Python requirements. [PyPI](https://pypi.org/project/strands-agents/).

## Existing GitHub options

| Option | Verified capability | Decision for current task |
| --- | --- | --- |
| Native Strands conversation + session managers | Summary, recent history, persistence; already installed | First choice; minimal dependency change |
| [Semantic summarizing conversation manager](https://github.com/danilop/strands-agents-semantic-summarizing-conversation-manager) | Author repository describes summary plus exact original-message recall via semantic search; MIT | Candidate for long evidence dialogues; not tested here, adds embedding/search and stale-memory retrieval concerns |
| [Strands Mem0 tool](https://github.com/strands-agents/tools/blob/main/src/strands_tools/mem0_memory.py) | Official tools repository exposes storing/retrieving/managing Mem0 memories | Long-term memory alternative, not necessary for three-turn continuity; not installed or benchmarked |
| [Mem0 Strands example](https://github.com/mem0ai/mem0/blob/main/examples/misc/strands_agent_aws_elasticache_neptune.py) | Maintainer example integrates persistent memory with Strands | Larger storage/service surface than current need; no deployment proposed |

Repository descriptions are source-author claims, not our performance measurements. No claim of maintained-version compatibility without a pinned install test.

## Recommended design and acceptance experiment

User's incremental summary idea is sound for preserving intent and references. Separate three concerns: conversation continuity, context size, and business truth. Use native SDK session restoration for the first and native compression for the second. A compact application-owned handoff should contain user intent, unresolved questions and cited record identities/versions, not replace live ERP facts. Approval/refusal remains authoritative application state and cannot be inferred from a generated summary. Wrong prior answers must not become current facts.

Prefer an opt-in native session/summarization candidate before a third-party framework. Scope sessions by user and case with stable identifiers; serialize same-session requests; refresh tools/facts each turn. Verify snapshot restoration cannot overwrite current packet state, reuse another case's messages, or restore stale executable plans. Keep newest dialogue verbatim and compress older dialogue only when useful. An unconditional extra model summary after every short turn adds cost/latency and another lossy inference; compare it, do not assume it wins.

The observed SdkInvocationLimit / limit_total_tokens concerns cumulative input/output within an invocation, not just the largest single context. Default proactive context thresholds may never trigger before this cap. Compression calls also consume model work. Measure all calls including summaries; retain budget limits rather than raising them to hide regressions. The first-turn diagnosis failure must be diagnosed separately.

Freeze variants: existing baseline; 1.53.0 native session+summary; same design on isolated 1.55.1 only if targeted compatibility checks pass. Keep model, business tools, source records, budgets and held-out questions fixed. Verify references across four-plus turns, two receipts, changed/deleted sources, units, refusals, cross-case isolation, service restart, summary failure and cost exhaustion. Independently judge source-grounded semantics and exact external effects, not schema success. Run repeated sequences and preserve failures. No production switch, feature completion claim, or dependency upgrade until these pass independent review. The original finalization tracker remains authoritative for all other unfinished work.

## Independent installed-source review and design correction

Independent backend reviewer verified the installed APIs and identified a blocking integration detail: native SessionManager saves on message creation/AfterInvocation, while our business validation runs after invoke_async returns. A direct session plug-in would persist candidates subsequently rejected by business validation. Therefore the session+summary variant above is a design target, not the first implementation step: first isolate single-request summarization and evidence/cost tests; then design an accepted-state boundary (including failed-candidate exclusion) before enabling cross-request restoration. Do not switch on auto and persistence together as an unreviewed shortcut.

The reviewer also confirmed default summarization directly calls model.stream rather than the normal Agent loop. SDK metrics/traces may omit this work; test both application BudgetedModel ledger and invocation-limit accounting. The summary is restored as a user-role message, so original content remains untrusted context and must not become an instruction or authorization. Review was read-only; no model calls or implementation were performed.

Independent document review: approved for research accuracy and local integration design; no implementation/live-semantic approval. External version/repository checks were performed by the primary task.
