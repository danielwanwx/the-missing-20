# Research-led alternatives for the receiving agent

Verified September9,2026 Pacific. Decision: pause expansion of the unfinished
billing journal, preserve its candidate and failures, and compare native
components against explicit task outcomes. No framework migration, new model,
ERP write or product-quality improvement is established by this research.

The current failure has three distinct dimensions: continuity across turns;
unsupported reasoning over available records; and durable execution across an
ERP acknowledgment loss. A component solving one does not automatically solve
the others. After D4's wrong physical-proof answer, an offline reconstruction
showed qualified source facts reach the reconstructed SDK boundary. This is not
the historical request wire capture. It does not support treating memory loss
as the established cause or summarization as the first repair for that error.

## Candidate decisions

| Candidate | Verified mechanism and fit | Decision / experiment |
| --- | --- | --- |
| Installed Strands1.53 native Agent/tool loop | Ordinary tools and schema tool coexist initially; forced-output fallback later restricts tools. Current two-phase acquisition/synthesis is application policy. No extra dependency is needed for this mechanism. [Documentation](https://strandsagents.com/docs/user-guide/concepts/agents/structured-output/) | First reasoning experiment: dedicated receiving question/answer loop, natural output versus narrow structured output, identical source/model/budget. Remove the cross-domain task burden in an isolated candidate rather than add answer exceptions. No semantic gain yet. |
| Native Strands summary + session | Native conversation compression and session persistence already exist; simply enabling persistence can also retain rejected candidates before application validation. [Conversation management](https://strandsagents.com/docs/user-guide/concepts/agents/conversation-management/), [sessions](https://strandsagents.com/docs/user-guide/concepts/agents/session-management/) | Keep as a separate continuity/long-context candidate after the short reasoning screen. Measure raw recent-turn retention, source refresh, rejected-answer isolation, restart and summarization usage. Do not label it a Q4 fix. |
| Google ADK context compaction | Official docs offer turn-interval/overlap and token-based retention. These are useful comparison patterns, but ADK App/Runner/session interfaces are a different runtime, not a Strands plug-in. [Docs](https://adk.dev/context/compaction/), [source](https://github.com/google/adk-python/blob/main/src/google/adk/apps/compaction.py) | Borrow the retention/trigger comparison, not a runtime migration solely for summary. Issue5194 reports a background compaction/session timestamp race on1.18.0; it is closed, not evidence that current ADK is broken. [Author report and discussion](https://github.com/google/adk-python/issues/5194) |
| Strands Evals / NVIDIA NeMo Agent Toolkit | Evals supports task experiments, output/trajectory/interaction evaluation and multi-turn simulation. NeMo has an explicit Strands integration with Bedrock support and profiling. Neither makes an incorrect answer correct merely by installation. [Evals](https://github.com/strands-agents/evals), [NeMo1.8 integration](https://docs.nvidia.com/nemo/agent-toolkit/1.8/components/integrations/frameworks.html) | Prefer Strands Evals for the later repeated conversation comparison; consider NeMo if cross-framework profiling is actually needed. Do not install both runners for the same small first screen. Keep exact business invariants and independent semantic review; an LLM judge is not sole truth. |
| Frappe/ERPNext native transaction boundary | PR→PI mapping and native document validation are reusable. A unique external key can be enforced in the ERP database. Native supplier bill duplicate validation is instead an optional SELECT-based check and does not establish atomic concurrent deduplication. [PR mapper](https://raw.githubusercontent.com/frappe/erpnext/version-15/erpnext/stock/doctype/purchase_receipt/purchase_receipt.py), [PI validation](https://raw.githubusercontent.com/frappe/erpnext/version-15/erpnext/accounts/doctype/purchase_invoice/purchase_invoice.py), [unique field schema](https://raw.githubusercontent.com/frappe/frappe/version-15/frappe/database/schema.py) | Potentially the largest simplification, because the effect and unique key share a transaction. Actual configured API identity returned false for create permission on Custom Field, Server Script and Workflow. No schema was changed. This route is currently unavailable through that identity, not disproved for the tenant or other deployments. |
| DBOS Python / Temporal Python | Both persist workflow progress. DBOS now documents local SQLite, while Temporal adds its own service/worker. An external step/activity may execute again when its effect happened before its result was checkpointed. Stable workflow IDs do not remove that window. [DBOS architecture](https://docs.dbos.dev/architecture), [connections](https://docs.dbos.dev/python/tutorials/database-connection), [Temporal maintainer discussion](https://community.temporal.io/t/execution-guarantees-of-activities/3405) | Run the smaller DBOS SQLite prototype with a persistent fake ERP, comparing absence/presence of a target-side unique key across the same crash. Measure effects and identities, not just workflow SUCCESS. Temporal remains an alternative if long-lived multi-service orchestration warrants the service cost. |

Apache Beam was also checked: its documented RunInference/data-pipeline focus
fits batch/stream processing, not this immediate conversation or two-write ERP
failure. This is a fit judgment for the current gap, not a claim that Apache
projects cannot support agents. [Official ML overview](https://beam.apache.org/documentation/ml/overview/).

Task decomposition and small, well-documented tool interfaces are supported by
[Anthropic's engineering guide](https://www.anthropic.com/engineering/building-effective-agents).
Its [context engineering guide](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
also distinguishes compaction, notes and focused agents, and cautions against
growing lists of brittle prompt exceptions. These are vendor engineering
recommendations, not a benchmark showing which candidate wins on our model.

## Reproducibility and costs

Official PyPI metadata was fetched directly for this selection: DBOS2.31.1,
Python>=3.10, uploaded Sep8; wheel SHA256
`5c32840683cbb10727d30d208d8e1eb3ccaec7ed881776e5bf9d89cb32d7583c`.
Its package README still emphasizes Postgres while current connection docs also
describe SQLite; the actual pinned package must be tested. [Package metadata](https://pypi.org/pypi/dbos/json).
Strands Evals1.2.0, Python>=3.10, uploaded Aug21, depends on Strands>=1.42.0
and also the tools distribution. Therefore it is not a zero-dependency toggle;
isolate dependency resolution before adoption. [Metadata](https://pypi.org/pypi/strands-agents-evals/json).

Strands/Evals/ADK/NeMo repositories report Apache-2.0; Frappe, DBOS and Temporal
report MIT, while ERPNext reports GPLv3. Use native ERP APIs; no upstream ERP
source is being copied into this repository by these experiments. Moving
branches and latest docs are discovery/inspection evidence, not pinned runtime
compatibility. Only installed1.53 and the forthcoming pinned DBOS experiment
have local execution scope. No subscription, hosted service or new model was
activated. Nova2's specific IAM approval remains pending.

## Current loop and acceptance

The [native comparison design](../audits/2026-09-09-native-receiving-comparison-design.md)
defines N1/N2's frozen inputs, budget, source coverage, leakage prevention and
independent review. One first-screen success merely permits the six-turn,
source-change and restart sequence; complete core and held-out repetitions
remain required. Candidate prompts are frozen together before either result.

The DBOS experiment is an isolated comparison of replay with and without
target-side idempotency, not a real ERP prototype. It cannot prove current
Frappe supports the key or replace approval/source/GL/SLE verification. Choose
adoption only after measuring what code and operational requirements it removes.

Two failed correction cycles for one mechanism trigger reassessment; the
existing stricter real-model stop remains. A new plan must name a different
mechanism and supporting evidence. Ordinary coding defects receive bounded
fixes; research is not a reason to abandon a sound approach after one typo.

## Collection and limits

Research Engine ran first from its canonical source checkout. Sandbox DNS
preflight failed; authorized network-enabled collection then completed with
warnings. Artifacts:
`/private/tmp/m20-research-led-options-20260909/2026-09-09-reusable-open-source-mechanisms-for-an-existing-python-strands-b/`.
It produced34 raw /40 total rows,9 eligible rows,3 invalid rows,28 discovery-only
rows and8 duplicate rows. It supported zero claim buckets and missed all five
required facets; its loop stopped for interactive recovery. Its eligible rows
were third-party summaries and do not support the technical decisions above.

Direct official web/source retrieval by primary and delegated researchers is
separate fallback evidence, not Engine-validated research. Maintainer and issue
reports guide counterexamples; their existence is not our reproduction of the
reported defect. Local source inspection verifies available interfaces, not
model semantics. Actual ERP read-only capability results are retained privately
at `/private/tmp/m20-erp-native-capability-read-02.json`; the01 file preserves
the separate sandbox DNS failure. Three successful GETs, zero mutations. No
current configured identity escalation followed those false permission results.

## Native ERP follow-up after the actual DBOS comparison

The independently accepted experiment observed two fake effects without a unique
target key and one with it, despite both recovered workflows reporting SUCCESS.
DBOS is therefore not selected for billing integration at this stage.

Official Frappe v15's REST `create_doc` calls `new_doc(...).insert()` without an
external-intent idempotency contract. Purchase Invoice uses naming-series
autoname; naming clears a caller-supplied name outside prompt/import modes.
The optional supplier bill check is a pre-insert query, not an atomic unique
claim. These interfaces do not supply the target property demonstrated by DBOS
variant B. [REST implementation](https://github.com/frappe/frappe/blob/version-15/frappe/api/v1.py),
[naming source](https://github.com/frappe/frappe/blob/version-15/frappe/model/naming.py),
[PI metadata](https://github.com/frappe/erpnext/blob/version-15/erpnext/accounts/doctype/purchase_invoice/purchase_invoice.json),
[PI validation](https://github.com/frappe/erpnext/blob/version-15/erpnext/accounts/doctype/purchase_invoice/purchase_invoice.py).

Choose the native API plus the existing single-attempt journal for ordinary
acknowledged creation, persist its exact server name/returned draft and then
perform one submission with exact readback. A lost insert response without a
durably bound name remains read-only: matching business fields cannot prove
this attempt owns that draft. A lost submit response has an already known name
for read-only reconciliation. This is our integration inference and explicit
availability tradeoff, not a provider exactly-once guarantee. The
[submit handler](https://github.com/frappe/frappe/blob/version-15/frappe/client.py)
takes a document; it does not turn an ambiguous prior insert into an identified
effect. [Revised design](../audits/2026-09-09-normal-billing-executor-design.md).

## Native session selection after the first reasoning screen

The actual N1/N2 screen improved the physical-evidence conclusion, but both
answers remained incomplete. It did not test persisted assistant history.
The proposed human-only six-turn driver was stopped before implementation:
Q6 asks about the assistant's last answer, so that driver would omit the very
history it claimed to test. No paid call used that proposal.

Select installed Strands1.53.0 `SnapshotSessionManager` with `LocalFileStorage`
for the isolated single-agent sequence. Current official documentation recommends
this path for new single-agent sessions; FileSessionManager remains supported
for repository-format compatibility, Graph/Swarm and bidirectional use, which
this experiment does not need. `save_latest_on="message"` saves after each
message and again after invocation. This is continuity, not business-effect
idempotency. [Official session documentation, checked September9](https://strandsagents.com/docs/user-guide/concepts/agents/session-management/).

Installed-source inspection found that snapshots restore actual messages,
agent/manager/model state and the system prompt. N2's answer survives as its
actual structured tool-use arguments and paired tool result; the final
`AgentResult.structured_output` must also be retained in the turn artifact.
Restore is not configuration validation: check the frozen contract before
construction and the effective configuration after initialization, before any
model call. These details require actual separate-process offline proof.

The initial native window40 policy actually failed six-process testing: serial
five-tool reads caused Q2's refusal to be evicted before Q6, despite preserving
Q5's answer. Select native NullConversationManager as the replacement bounded
full-history baseline, with unchanged budgets and overflow stopping the run.
This trades higher input cost for retention; actual N1/N2 tests remain required.
Summarization is a separate future candidate. Persistence alone proves neither
compression nor factual retention. [Conversation management](https://strandsagents.com/docs/user-guide/concepts/agents/conversation-management/).

Strands Evals' simulated actor is useful for later exploratory conversations,
but dynamic model-generated questions add calls and do not replace this fixed
six-question, source-change, fresh-process driver. No extra evaluation package,
SDK upgrade, summary model or hosted memory service is selected here.

Independent design review permits isolated offline implementation, with
post-restore configuration checks, preserved partial failures and measured
window retention required. A separately reviewed paid gate follows offline
verification; no six-turn, product UI or F03 acceptance is implied.

## Tool selection after the first real session sequence

The [frozen sequence result](../audits/2026-09-09-native-session-first-sequence-review.md)
stopped N1 at Q2 and N2 at Q1 under the unconditional five-source rule. N1
correctly acknowledged a read-only instruction without tools; N2 fetched ERP
and gave the correct quantity/ledger ID, but used a tool path as its citation.
The failure records and later NOT_REACHED positions remain unchanged.

The native SDK lets the model choose tools according to the request; it also
supports direct programmatic calls. Those are different execution choices.
Requiring every tool for an acknowledgement overrides normal selection without
adding relevant evidence. [Official tools overview, checked September9](https://strandsagents.com/docs/user-guide/concepts/tools/).

Strands Evals provides tool-selection, output/faithfulness and whole-session
evaluators. Its tool-selection evaluator assesses individual calls in context,
including unnecessary calls; zero calls can yield no evaluations, so it cannot
alone establish that an acknowledgement is correct or required evidence was
not skipped. A later integration would need the output and session dimensions
as well, with an explicitly budgeted judge model. No evaluator was installed or
run in this screen. [Tool selection](https://strandsagents.com/docs/user-guide/evals-sdk/evaluators/tool_selection_evaluator/),
[evaluation levels](https://strandsagents.com/docs/user-guide/evals-sdk/evaluators/).

Berkeley's BFCL separates relevance/irrelevance detection from multi-turn and
memory tasks. This supports testing whether a tool is necessary rather than
maximizing the number of calls. It is a benchmark design reference, not an ERP
integration component or proof about our model.
[BFCL V4 methodology](https://gorilla.cs.berkeley.edu/blogs/15_bfcl_v4_web_search.html).

Proposed next comparison: preserve native snapshots and fresh processes; use
ordinary native tool selection, distinguish instruction acknowledgement from
external factual claims, and independently require current relevant source
evidence and valid record citations for those claims. Freeze the revised prompt,
evidence rubric and failure rules before a new run. Do not continue the failed
session, convert tool names into fabricated citations, or use the old failed
screen as a fresh paired control. A custom router, summarizer or new runtime
does not address the failure demonstrated here.
