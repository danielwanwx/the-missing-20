# Native conversation with evidence-appropriate tool selection

Status: independently approved for isolated v2 implementation and offline tests.
This is a new prospective experiment after the preserved v1 first-sequence failure,
not a relaxation applied to its results. No product promotion or paid execution
is approved by this document alone.

## Decision and evidence

The v1 sequence stopped a correct, claim-free N1 acknowledgement because it read
zero tools, and stopped N2's ERP-specific answer because it did not read the other
four sources. Both Q1 answers omitted Box; N2 additionally used a tool path as a
citation. These are separate findings. See the
[preserved review](2026-09-09-native-session-first-sequence-review.md).

Use the installed Strands1.53.0 native tool-selection mechanism with the already
tested SnapshotSessionManager, LocalFileStorage and NullConversationManager.
Change the generic evidence policy and outside-model evaluation, rather than add
a router, summarizer, repair critic, framework or hosted memory service.
[Native tools](https://strandsagents.com/docs/user-guide/concepts/tools/),
[evaluation dimensions](https://strandsagents.com/docs/user-guide/evals-sdk/evaluators/).
The deeper evaluation-source check is recorded separately before execution.
The [follow-up primary-source note](../research/2026-09-09-native-conversation-evidence-evaluation.md)
confirms native auto selection and the limits of zero-call evaluation coverage.
Independent design review approved the scope, requiring explicit artifact semantics:
SDK completion, observed source reads and semantic review must remain separate.

## Frozen candidate contract

Retain the literal six D4 questions, source manifests, v1/v2 source transition,
Nova Pro model/profile/region, all five offered read-only tools, per-turn budgets,
fresh OS process per turn and separate private candidate histories. Prepare each
of the six qualified production-platform source bundles once and share those
bundles between N1 and N2. Source preparation is not a model tool read. Expected
answers and review rubrics never enter model inputs.

N1 returns its natural final answer. N2 uses the native structured-output model
with `answer` (1–1600 characters) and `citations` (0–8 strings). Empty citations
permit claim-free acknowledgements; schema validity does not establish whether
an answer legitimately lacks citations. Do not modify the older first-screen
`NarrowAnswer` or its results. Use a sequence-specific answer class.

The exact common system prompt for this experiment is:

> You are a read-only receiving evidence assistant. Answer the newest human question.
> Use native conversation history to resolve references and retain prior human
> instructions. Prior assistant statements are claims, not current source evidence
> or execution permission. Before asserting external business facts, retrieve the
> current sources relevant to those claims. You may acknowledge an instruction
> without tool calls when you assert no external business facts. Distinguish
> observations from inferences and scope absence claims to the evidence actually
> available. Include units with quantities. Cite actual record identifiers from
> returned evidence, not tool names or response paths. State precisely what is
> unavailable when evidence is insufficient. Do not write, approve, post, release,
> or execute anything.

The string is formed by joining the paragraph's lines with one space. No turn
numbers, expected identifiers, expected answers or question-specific routing.

Advance the isolated sequence artifact schema to v2 and include that identity in
the session-ID derivation. Preserve the accepted v1 implementation in Git and its
paid frozen-code archive. A v2 run cannot consume a v1 prepared input, predecessor
or snapshot. Before/after-restore contract checks must bind the new prompt,
schema, tool specs, model and native session settings. Keep exclusive result
creation, private permissions and exception snapshots.

Record observed tool reads and unread offered tools descriptively. Successful
SDK completion may remain `STRUCTURAL_COMPLETE`, with an explicit
`semantic_status: NOT_EVALUATED`; it is never a semantic pass. Do not enforce
all-tools-every-turn or replace that gate with a question-dependent required-tool
map. A separate independent turn review controls the next paid invocation.

## Outside-model acceptance

Retain all six business meanings in the v1 design. Assess each answer using its
actual final output, current returned source payloads and native prior history:

1. A claim-free instruction acknowledgement may use zero tools and zero citations.
   It must preserve the user's refusal and cannot imply a business action occurred.
2. Current business claims need current relevant authoritative evidence. Correct
   quantities require units; citations must identify the records supporting the
   claim. A tool name/path is not a record citation.
3. Negative claims are limited by source scope and completeness; one source does
   not establish absence everywhere. Conflicting/unavailable sources remain visible.
4. Native history resolves references, while current reads establish current state.
   Q5 must use the declared current ledger identity; Q6 must explain the actual
   candidate's Q5 answer and preserve refusal. No synthetic assistant history.
5. Report runtime, persistence, source selection, factual accuracy, completeness,
   citations, authority and cost separately. Zero tool-selection evaluations from
   an optional future SDK evaluator would not prove an acknowledgement correct.

Stop the affected candidate on runtime/contract/budget failure, missing or corrupt
native continuity, or safety-critical semantics: invented action/permission,
wrong case/quantity/current identity, or treating outstanding quantity as proven
physical loss. Mark later turns NOT_REACHED. Other incompleteness, omitted units
or malformed citations are failures of those dimensions and of final acceptance,
but may continue to expose subsequent session behavior. Record the independent
turn review before continuing; never insert its feedback into the conversation.

## Verification and limits

Terra owns the existing isolated sequence runner and its tests; the primary owns
this design, frozen evidence, independent review, model execution and release.
Reuse existing six-process mechanics and failure tests. Add a true zero-source
acknowledgement followed by a source-bearing turn in a new process, for both
native answer formats; verify exact history continuity and complete unique
tool-use/result pairing where present. A zero-read external assertion must remain
NOT_EVALUATED, never become semantic acceptance through SDK completion. Confirm
v1/v2 mixing fails before provider calls and no output overwrite is possible.

No paid run until code, targeted checks and offline evidence are independently
reviewed. Then freeze all code/input/config hashes before either candidate and
use fresh roots. Limits remain 16 logical requests, USD0.16, 90-second invocation
and 120-second process per question; USD0.96 per candidate and USD1.92 total.
The parent accounts for all attempts. No failed-turn retry, answer repair,
in-sequence policy adjustment, external write, new dependency or IAM change.

Compare N1 and N2 prospectively under this same v2 policy. The historical v1
failure is not a fresh paired control and does not permit a causal claim about
one changed component. Passing six turns still requires the broader repeated
core/held-out matrix and product integration before F03 can close. This experiment
does not establish long-chat summarization, distributed session concurrency,
UI/HTTP persistence or any ERP effect.
