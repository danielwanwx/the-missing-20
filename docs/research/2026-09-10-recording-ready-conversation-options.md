# Recording-ready native conversation options

Checked September 10, 2026. This is research and an experiment design only. It
does not change the product model, authorize a paid invocation, or accept the
failed complex conversation.

## Current failure and invariant

The accepted English interface audit records a six-turn Nova Pro attempt against
PO18. Turn 1 had all 19 events but gave an unsupported 38/40 explanation; turn
3 produced no terminal answer after successful reads; turns 5 and 6 failed.
Provider input rose from 23,408 to 124,248 tokens. The exact cause of the turn-3
failure is unproved, but repeated full source snapshots are a demonstrated
context-growth risk. The problem is not solved by treating a prior assistant
answer or a summary as operational truth.

Every candidate therefore keeps these boundaries:

- Current external facts come only from the qualified source tool result for the
  current request. Retained dialogue can resolve a human reference but cannot
  override a fresh source.
- The native session remains read-only and case/conversation scoped. No
  conversation state grants execution authority.
- Failed, malformed, English-rejected, or incomplete answers are retained as
  failed evidence, never promoted to an accepted fact or silently retried into
  success.
- The seven-question oracle stays outside model input. It is an independent
  evaluation, not an expected-answer prompt.

## Installed capability and constraints

The repository pins `strands-agents >=1.53.0,<2`; the installed version is
1.53.0. It already exports `SnapshotSessionManager`,
`SlidingWindowConversationManager`, and
`SummarizingConversationManager`. The current adapter instead explicitly uses
`NullConversationManager` plus `SnapshotSessionManager(save_latest_on="message")`.
It persists a full JSON source snapshot inside every human message and then
offers the same qualified sources as tools. That is the direct explanation for
duplicated retained source context; it is not proof of the semantic error.

Official Strands documentation identifies sliding window as the normal
history-reduction manager and says it preserves valid tool-use/result
boundaries. It can manage before every model call and reduce large tool results
on overflow. [Conversation management](https://strandsagents.com/docs/user-guide/concepts/agents/conversation-management/)
The same documentation describes summarization as replacing older messages and
keeping a configurable recent tail; by default it uses the main model, so it is
an additional inference and a lossy model-authored artifact. The official
context-management page also says auto/agentic modes compose offloading, and
durable offloaded content needs explicit durable storage when sessions are used.
[Context management](https://strandsagents.com/docs/user-guide/concepts/context-management/)
Sessions are a distinct SDK feature and need lifecycle compatibility tests.
[Session management](https://strandsagents.com/docs/user-guide/concepts/agents/session-management/)

PyPI lists 1.55.1 as current, while this repository has 1.53.0. An SDK upgrade
is an isolated compatibility experiment, not part of the first comparison.
[strands-agents release history](https://pypi.org/project/strands-agents/)
The installed 1.53.0 distribution metadata declares Apache-2.0. All three
compared options reuse that installed SDK, so the first experiment adds no
dependency or new license surface.

The model is also not an open setting in this product: `BedrockNovaProConfig`
rejects any identifier other than `us.amazon.nova-pro-v1:0`. The prior
matched Nova2 comparison was rejected for a material fulfillment error. The
repository contains no configured model named “Sunny2”; do not infer that phrase
means Sonnet, Nova2, access entitlement, or a permitted production switch.
Memory/source design must be evaluated independently of a model change.

## Compared native alternatives

| Candidate | Mechanism | Benefit | Material limitation | Decision |
| --- | --- | --- | --- | --- |
| Retained baseline | Current `NullConversationManager`; persist every full source snapshot and tool result. | Exact prior messages are available. | Duplicates large current sources across turns; token growth is already observed. | Retain only as the control. |
| Bounded fresh-source/history | Replace the null manager with a native `SlidingWindowConversationManager`; persist a bounded recent dialogue/tool tail, but put only the new human question in the persisted message. Require a current source-tool read for each business-fact answer. | Materially cuts the duplicate snapshot and bounds history without a second inference. Fresh facts arrive through the current tool result. | Older references can fall out of the window; trimming must preserve tool pairs and cannot validate model semantics. | **First experiment.** |
| Native summarizing | Use `SummarizingConversationManager` with the same fresh-source rule. | Preserves an older conversational outline after reduction. | Summary is lossy, model-authored, consumes another model call, and is restored as context rather than authority. Current `save_latest_on="message"` can persist a candidate before display validation. | Reserve as the only possible second, materially different candidate. |

Neither `context_manager="auto"` nor `"agentic"` is the first experiment:
they add offloading and, for agentic mode, model-directed retention decisions.
That is a larger mechanism than needed to test the observed duplicate-source
failure.

## Recommended minimal experiment

Run a private, read-only **native bounded fresh-source/history** candidate on
installed 1.53.0:

1. Use the existing case/conversation-derived snapshot ID and the existing five
   read-only source tools. Do not add a framework, model, source, or write path.
2. Use `SlidingWindowConversationManager(window_size=8,
   should_truncate_results=True, per_turn=True)`. Do not pin the first message:
   today it contains mutable source data. The configuration is frozen for the
   comparison; tune it only after recording this result.
3. Replace the persisted full-source human prompt with the newest question and
   an instruction to read current qualified sources before asserting business
   facts. Tool closures supply only the current packet for that request. Do not
   inject the complete packet separately.
4. Preserve the existing display/English rejection and private permissions.
   Retain failed raw SDK sessions as untrusted dialogue evidence: they do not become
   business facts or execution authority. Do not require a new accepted-state store
   or transaction layer as a precondition for this experiment.
5. Record the private raw/display answer, tool trace, aggregate provider usage,
   terminal state, elapsed time, session message count, source and question hashes,
   and implementation/schema hashes. Do not claim a trim count unless the SDK
   exposes one. No output-budget increase, retry loop, or model substitution is
   part of this experiment.

This is deliberately a context/source-transport change, not another prompt
critique. It cannot repair the first-turn semantic error by itself; the frozen
evaluation tests whether it avoids the demonstrated growth/failure mechanism
while preserving source-grounded dialogue.

## Evidence-policy follow-up after candidate turn 1

The first bounded candidate turn completed in about four seconds with one
`read_erp_evidence` call. It correctly read final accounting quantities but did
not read the recorded physical-event history, which is retained under
`read_collaboration_evidence`. It therefore could not support the historical
part of the compound question. This is a source-discoverability failure, not
proof that the sliding window lost the 19 events.

The next bounded patch should add a versioned JSON-shaped evidence-policy
mapping. Generic distributor chat selects a universal `distributor_core_v1`
contract requiring `read_erp_evidence` and `read_collaboration_evidence`; it is
not selected by keywords or by the model. Each existing tool receives a
source-specific model-facing description: ERP is current accounting and native
documents, while collaboration is the retained chronology of arrivals,
inspection, replacement, allocation, pick, shipment and recorded delivery
confirmation. Keep the existing tool names and source payload partition; do
not copy physical events into the ERP payload.

Known UI workflows can explicitly select extension contracts: discrepancy,
label, quality, allocation and delivery extend the core; finance is ERP; and
cross-app adds Airtable and Celigo. Free-text chat stays on the universal core.
A model-selected task contract is not sufficient because its selection cannot
be independently validated.

Enforcement should reuse the SDK's `BeforeToolCallEvent` hook pattern already
used by the repository's advisory evidence-completion hook. The current native
conversation ends in free text, so a hook cannot intercept an `end_turn`
answer. For this patch, a deterministic bounded acquisition checklist plus a
post-turn required-read rejection ensures that no answer is delivered without
the contract's fresh reads. If this still materially fails, the next interface
change can use a small structured terminal-answer tool, allowing the native
hook to cancel finalization until required reads complete. That is a stronger
but separate change; it is not needed to define the first policy experiment.

The candidate diagnostic manifest should include the exact native limits
(`turns=16`, `output_tokens=6204`, `total_tokens=80000`, wall timeout 90
seconds), candidate/session schema versions, source and question hashes, and
SHA-256 hashes of the adapter, packet builder, and runner. It must retain error
body/detail privately when provided and record aggregate ledger usage on both
success and failure.

## Frozen seven-turn acceptance

Use the same real case, current source-packet shape, model, temperature, tool
set, and per-request budgets for historical baseline and candidate. The
[frozen evaluator contract](../audits/2026-09-10-recording-dialogue-acceptance-contract.md)
defines the exact seven questions and expected evidence outside the model
context. It covers the initial 20+18/40 receipt and two replacement parts, final
inventory, A25/B15 date-first allocation, sample versus whole-lot quality,
unsupported causality, synthetic versus physical delivery, external records,
and finance. It also fixes the Chinese-language request as an English-output
check. Do not add the evaluator document, its answer requirements, or reviewer
verdicts to a source tool or human prompt.

For all seven turns, acceptance requires a terminal English answer, a relevant
fresh-source read before any external-business assertion, exact quantity/UOM/ID
facts, no unsupported causality or physical-delivery claim, no write effect, and
no cross-case source. Any `UNAVAILABLE`, HTTP 500, English-boundary rejection,
incorrect required fact, or invented cause fails the sequence. It also fails if
candidate input tokens grow monotonically with retained full source snapshots
instead of remaining bounded by the configured window and current read.

The old failed Nova Pro sequence is the historical control; do not pay to
reproduce it. Run the selected candidate for three independent real-model
seven-turn sequences, within the frozen USD5 incremental estimate cap, and
preserve every raw private attempt including failures. Add the specified
source-change holdout separately: initial 38-part source, then the current
source, followed by an anaphoric recheck and a write refusal. It must show both
fresh-source precedence and continuity. Focused local checks cover source
interruption and case/session isolation; they do not count as real inference.
Independently review semantics and source traces before a promotion claim. A
single successful sequence is recording evidence only, not general model
quality. Do not start the summarizing or SDK-upgrade branch until this candidate
has a recorded material failure or passes independent review.

## Contract-run failure and next input-interface decision

The n3 contract run is a second material first-turn failure. It completed on
the same model in 6.171 seconds after successful `read_erp_evidence` and
`read_collaboration_evidence` calls, consuming 38,791 input tokens, 429 output
tokens, three provider requests, and USD 0.0324056 incremental cost. The
required-read hook therefore proved *coverage*, but not reasoning quality. Its
answer correctly repeated the final 40/0/0/40/40 accounting values, yet treated
the initial four packages as merely expected, described five observed packages,
and omitted the recorded initial 20 + 18 Nos and the later 2-Nos replacement.
It gave neither `Nos` nor record citations. Preserve the raw private report at
`/private/tmp/m20-recording-candidate-reports/contract-run1/turn01.json` as a
failed attempt; do not retry n3 with the same payload and checklist.

One plausible contributor is the source interface. The physical history
is currently a roughly 20k-character raw event collection inside
`read_collaboration_evidence`, combined with roughly 7k characters of retained
Jira material. The ERP result separately holds the lot basis needed to explain
the apparent conflict: for a lot, planned receipt quantity, declared outer
package count, declared units per package, declared nominal package quantity,
and observed receipt quantity are distinct fields. In this case the raw facts
support two initial arrivals of 20 and 18 Nos in four outer packages, followed
by a linked 2-Nos replacement in a fifth package. A raw event does not itself
contain every lot-basis field. The model must therefore discover, join, and
order verbose data before it can answer a simple reconciliation question.

The next candidate should be a **versioned, source-only physical reconciliation
ledger**, supplied by the existing collaboration tool in place of duplicate raw
physical-event and retained-Jira detail. It is not a case-specific answer,
summary, blame conclusion, or evaluator oracle. It is a deterministic
projection whose rows retain source event/document identifiers and state only:

- event time and event ID; business step; lot; unit of measure; current source
  status; and the relevant native evidence/document ID;
- for an arrival, the separately labelled planned quantity, observed quantity,
  declared outer-package count, units per package, and declared nominal-package
  quantity;
- a source-recorded replacement relationship when present, without inferring a
  cause; and
- explicit chronological groups containing only arithmetic totals and their
  member event IDs, such as initial arrivals and later replacements.

ERP current accounting remains a separate required read. Retained Jira status
is a compact, separately labelled provider envelope: it must never masquerade
as physical evidence, and its absence must not make a current physical ledger
unavailable. The full raw projection and raw retained provider records remain
available for private audit and the product's existing read paths, but are not
duplicated in the model-facing core response. This follows the normal event
record distinction between what happened, when it happened, and the business
step/context; GS1 describes a collection of events as a picture of a process
over time and requires event time, lot/object identity, location, business
step, and disposition for traceability events. [GS1 EPCIS/CBV implementation
guideline](https://www.gs1.org/standards/epcis-and-cbv-implementation-guideline/current-standardd)
and [GS1 Global Traceability Standard](https://www.gs1.org/standards/gs1-global-traceability-standard/current-standard)
support the field separation, not any conclusion about this case.

The versioned reconciliation task contract should contain the following fixed,
general procedure before the model sees the ledger. It is a lightweight
knowledge contract, not a keyword router and not a natural-language
expected-answer prompt:

1. Read current ERP accounting and the physical reconciliation ledger.
2. State the UOM and keep package counts separate from stock quantities.
3. List original arrival rows chronologically; distinguish planned and observed
   receipt from declared nominal package quantity.
4. State recorded replacement rows separately from original arrivals, preserving
   their relationship and IDs.
5. Reconcile only the current totals supported by ERP, cite returned record IDs,
   and scope any missing evidence or causality claim to the cited sources.

For an explicit distributor-reconciliation workflow, this contract can be
selected by workflow context. Free-form distributor chat should use this core
ledger contract as its safe default rather than an untestable model-selected or
keyword-selected task classifier. Other workflows need separately designed
contracts only when they are actually wired; do not add an unused seven-topic
catalog. The existing required-tool hook remains useful for freshness, but it
is not treated as a reasoning guarantee.

This source/interface candidate is materially different from the two failed
runs: it changes the information representation and supplies a deterministic
reconciliation procedure, rather than changing the same prompt, window, or
tool-read checklist. It is also bounded: no new persistence layer, retrieval
system, provider, model call, write path, or answer template. Before any paid
turn, focused tests must prove every ledger ID/field derives from a raw current
source, group arithmetic is reproducible, a replacement link is source-backed,
missing physical history is honestly unavailable, and raw/provider provenance
is retained outside the compact model payload. The first paid test, if approved,
is one fresh, private turn with the same model and limits. It must distinguish
the initial 4 packages/38 Nos from the declared 40-Nos nominal package total,
identify the recorded 2-Nos replacement as the fifth package, use `Nos` and
source identifiers, give current accounting accurately, and avoid causal or
custody claims. Those checks stay in the evaluator, never in the candidate
input.

| Next alternative | Why it is insufficient now | Decision |
| --- | --- | --- |
| Repeat n3 with a stronger checklist, more prompt wording, or the same raw sources | Both required tools were already read; the failure is the join and chronology burden in their payloads. | Reject. |
| Native summarization or automatic/offloaded context | It transforms evidence with another model decision and can lose provenance while leaving the first-turn raw source interface unchanged. | Defer. |
| Deterministic reconciliation ledger plus fixed procedure | Makes the relevant source distinctions and chronology explicit while preserving IDs, provenance, and factual limits. | **Run next, after local derivation tests and approval.** |
| Larger or different model | Confounds model capacity with a demonstrably poor input interface; no alternate model is configured or authorized. | Consider only after the ledger candidate is evaluated. |
| Case-specific answer template or evaluator-derived facts | Would hide the reasoning failure and turn the evaluation into model context. | Reject. |

Amazon Nova's official tool guidance makes this interface change preferable to
another prose-only instruction: tool schemas must explicitly convey exact
functionality and differentiators, tool results are returned as structured JSON
for the model to incorporate, and workflow sequencing belongs in the system
prompt. [Nova tool definition](https://docs.aws.amazon.com/nova/latest/userguide/tool-use-definition.html),
[Nova tool use](https://docs.aws.amazon.com/nova/latest/userguide/tool-use.html),
and [Nova advanced prompting](https://docs.aws.amazon.com/nova/latest/nova2-userguide/advanced-prompting-techniques.html)
also recommend concise schemas and discrete multistep workflows. A native
summarizing manager is not an adequate substitute because it adds a lossy
model-authored transformation and may discard IDs. A larger model remains an
unapproved, confounded experiment: evaluate this lean, source-preserving
interface first; do not infer a permitted model from the earlier “Sunny2”
remark or change the Nova Pro factory automatically.

The same principle is present in the official Strands SDK source: a tool's
human-readable description is part of its model-facing specification and is
intended to explain when it should be used. [Strands Python SDK tool
interface](https://github.com/strands-agents/sdk-python/blob/main/AGENTS.md)
The contract should therefore make both the tool's purpose and the returned
field semantics clear, rather than relying on a broad title such as
"collaboration evidence."

## Subsequent experiment disposition

The proposals and permission states above record their respective design
checkpoints. N4 was subsequently tested and failed semantic acceptance: required
reads succeeded, but packaging quantities and chronology were still wrong.
The user-authorized stronger-model comparison then attempted one exact Sonnet 5
Converse call. AWS rejected account invocation; no inference or semantic result
was obtained. Neither candidate was promoted. See the
[recorded acceptance results](../audits/2026-09-10-recording-dialogue-acceptance-contract.md)
for the preserved failures, actual access error, and remaining gate. Source
representation remains a hypothesis about a contributor, not a proven sole
cause or an accepted accuracy fix.
