# Recording dialogue acceptance contract

Frozen before new inference. Baseline code: 569f684640d131c0d66a45be01776cc26866046a.
Goal: a useful English multi-turn conversation over the same distributor order,
with correct business facts, bounded context and transparent failure evidence.
This contract is evaluator material and must not enter model context.

## Inputs and comparison

Retain the previous six-turn failed Nova Pro sequence; do not pay to reproduce
an unchanged known failure. This is a historical baseline, not a fresh paired run.
Research native SDK conversation options before creating a new candidate. Compare
at most two materially different native-context configurations on the same source
and questions, preserving raw outputs and usage. No generic critic or second
memory framework; no silent model switch.

Private frozen inputs (SHA256):
- Initial PO18 source, after four cartons / 38 counted parts:
  `m20-final-20260910-after-arrival-b-01.json`,
  `554a8bf895697edd25924118dafb26df5c114919fa9090b8eb862622f58e2aa8`.
- Current PO18 source captured read-only for this round:
  `m20-recording-current-source.json`,
  `a9c4bec5d7f8a0a235e4c0a9b4e0a7af6ddee598821cb3ee052c19f33e861f43`.
- Previously frozen seven-question sequence:
  `m20-english-dialogue-questions.json`,
  `15a6bd1e4cabbb0d6f7bfe1f7c8291f7123783812ed99ea501bffd55e5ff81c1`.

Use only admitted source fields, ordinary source projections and user questions
as model inputs. Do not insert expected answers, rubrics or reviewer verdicts.
Private snapshots, including rejected answers, remain private and preserved.

## Acceptance

The seven retained questions cover carton/part discrepancy, final inventory,
customer contracts, sample versus whole-lot quality, unsupported supplier blame,
synthetic versus physical receipt, linked external records, and finance. Require:
- Correct current quantities and units; distinguish allocation, pick, dispatch
  and recorded confirmation. A25/B15; date-first contract, priority tie-breaker.
- Original observed counts 20+18, two missing from the 40-part order, then two
  replacements. Do not invent a cause or unsupported per-carton packing rule.
- A sample failure does not prove every held item defective; cite recorded
  reinspection/release without pretending it was a real independent physical test.
- Delivery inputs are declared synthetic and do not prove actual customer receipt.
- Same-case external IDs and their roles, with no invented send or write.
- PO USD160, customer order values USD150/90; missing invoices and no payment
  proof. Order value is not recognized revenue.
- English even when asked for Chinese; UNAVAILABLE is a language safety result,
  not a successful answer-quality result.

For the selected candidate, perform three independent real-model sequences and
independent semantic review before claiming repeatable demo usefulness. Include
source-change follow-ups in a separate held-out sequence: initial source then
current source, an anaphoric follow-up, a refusal of writes, and a request to
recheck a mistaken assumption. Fresh-source precedence and history continuity
must both hold. Test source interruption and isolated case/session behavior
with focused local checks; never imply those scripted checks are real inference.

## Budget and stop rules

Keep Nova Pro as the baseline unless an exact alternative is explicitly selected.
Freeze each candidate's manager, source-delivery method and invocation limits in
its experiment record before calls. Total incremental inference estimate capped
at USD5 for this round; stop before exceeding the cap. Capture every attempt,
complete provider errors, elapsed time and input/output usage. If a mechanism
fails twice materially, stop that mechanism and return to research; do not patch
answers or keep equivalent retries. Missing AWS login blocks inference only.
No ERP effects, customer messages, payments or public release arise from dialogue
acceptance. Existing demo effects remain separately verified.

## Release gate

Only promote a candidate after independent review and real task benefit. Then
verify the normal product API/UI, preserve the old failed sessions, run relevant
checks, commit exact files, push, verify remote SHA and actual CI. Recording
readiness additionally requires the new-case business rehearsal, voice disposition,
current materials and official competition/access checks. A successful dialogue
alone is not whole-system acceptance or an award prediction.

## Source-schema clarification before new calls

Independent code/source inspection found LOT-B `expected_quantity=18` is the
planned receipt quantity, while `cartons=2` and `expected_pack_quantity=10`
declare a nominal packaging quantity of 20. Saying the receipt plan expects 18
is not itself an error. The prior turn-4 review used an overly broad interpretation
of that phrase; its finding must not be reused without this distinction.

Both candidates may use the same source-only per-lot clarification: planned
receipt quantity, declared package count, declared units per package, their
nominal product, and observed received quantity. Preserve raw records and history.
Do not insert a shortage diagnosis, supplier cause, acceptance verdict, or expected
answer. This addition is frozen before candidate inference; it addresses an
observed ambiguous domain contract, independently of context retention.

## Retained first candidate result and revised task direction

The first isolated sliding-window call completed in 4,099 ms with 7,313 input
and 350 output tokens (two requests; estimated incremental cost USD0.0069704).
It read only `read_erp_evidence`. Current final totals were correct, but the
answer did not reconcile the original 20+18 receipt and replacement chronology.
It cited a JSON response rather than actual record identifiers. This is a
semantic FAIL, not acceptance based on latency or completion status. Private
report: `/private/tmp/m20-recording-candidate-reports/run1/turn01.json`.

Inspection confirmed the complete retained physical-event chronology is in
`read_collaboration_evidence`, while all five tools share one generic model-facing
description. This is an observed discoverability gap, not evidence that the
sliding window forgot history on its first turn. The raw failed attempt remains
unchanged. No later turn of that attempt was paid for or counted as successful.

The user then requested a lightweight versioned task contract that specifies
required evidence and enforces reads, rather than relying on reminder prompts.
The next design must distinguish procedure from answers: identify necessary
sources, reconcile fresh observations, and disclose missing evidence without
encoding case quantities, supplier causes, or evaluator answers. Known workflow
context may select a contract directly; conversational references must not rely
solely on keyword matching. The native SDK interface and a small explicit policy
are preferred to a new retrieval or memory framework. This task-direction
change precedes the next implementation and real-model trial.

## Approved lightweight evidence contract candidate

Before a second paid trial, the user explicitly requested mandatory task guidance.
The revised candidate uses a versioned universal distributor core contract requiring
current ERP and retained physical-event reads each turn. Tool names and source
provenance remain separate. It does not classify conversational intent with
keywords or trust a model-selected contract to cover the question.

A minimal structured terminal answer and the existing native Strands cancellable
tool-hook pattern enforce the checklist inside the invocation: an attempted final
answer is withheld while required reads are missing, with remaining reads named
for the model. The normal API still returns an English answer. This extends the
interface design after the observed first-turn omission; it is not represented
as an unchanged matched context-manager comparison. No expected business answer,
extra reasoning model, new memory framework, or increased limits is admitted.
Missing sources and semantic errors remain failures, even if all tools were called.

Per-invocation limits remain 16 turns, 6,204 output tokens, 80,000 total tokens,
and 90 seconds. Use a distinct versioned private session from the failed trial.
Only implement contracts wired to an actual workflow; defer unused task catalogs.

## Required-read contract trial: coverage passes, semantics fail

The independently reviewed structured-terminal candidate (`n3-recording-contract`)
completed its first real Nova Pro question in 6,171 ms. Both required tools were
read: ERP and collaboration/physical history. It used 38,791 input and 429 output
tokens across three requests, with estimated incremental cost USD0.0324056.
Private report: `/private/tmp/m20-recording-candidate-reports/contract-run1/turn01.json`.

The final answer still omitted the initial 20+18 observation and two-part
replacement chronology, units, and record citations. Its reference to the initial
four cartons as an expectation did not explain the actual arrival sequence.
Current final totals were correct, but this remains semantic FAIL. The hook
demonstrated required-read enforcement; it did not demonstrate answer accuracy.
No next turn, repeat sequence, promotion, or model switch followed this failure.

The two preserved first-question trials cost an estimated USD0.039376 in total.
Do not add their ledger cumulative baselines as new spending. This is an
engineering estimate, not an AWS billing statement. Repeated equivalent trials
are stopped. The next research phase addresses evidence representation and
task-level reconciliation guidance before proposing a new mechanism.

## Source-ledger trial: source projection reduces input, semantics still fail

After the documented research/design cycle, n4 replaced verbose physical/provider
records with a deterministic, source-derived ledger and a general reconciliation
procedure. Independent review and 57 focused checks permitted only the bounded
real trial. N3 source/diagnostic files were preserved privately before revision.

The n4 first question completed in 4,892 ms, reading both required tools, with
16,952 input and 318 output tokens across two requests. Estimated incremental
cost: USD0.0145792. Report:
`/private/tmp/m20-recording-candidate-reports/ledger-run1/turn01.json`.

The answer invented nine received per package and confused two outer packages
with two units per package. It again omitted replacement chronology, record
citations and Nos. Current final scalar totals remained correct. This is FAIL;
no later turn or promotion followed. Required reads and concise typed evidence
did not establish reliable semantic reasoning by Nova Pro on this question.

Total estimated incremental cost of the three preserved diagnostic trials is
USD0.0539552. Stop prompt-equivalent retries. A stronger-model matched experiment
requires a separately recorded exact Bedrock identifier, verified availability,
pricing/budget and the unchanged admitted inputs; do not infer a model identity
from the earlier ambiguous spoken model name. Business rehearsal remains separate.

## Approved single matched Bedrock model comparison

The user previously authorized evaluating a stronger AWS model within available
credits. After n4's retained failure, the primary selected the exact active US
profile `us.anthropic.claude-sonnet-5` for one diagnostic-only first-question
comparison and announced it before invocation. This does not reinterpret the
earlier ambiguous spoken model name as an exact selection or switch the product.
Read-only AWS catalog/profile checks and official model/pricing documentation
preceded the choice. Standard rates used for the diagnostic ledger are USD3 per
million input tokens and USD15 per million output tokens. A new shared-ledger
incremental cap of USD0.25 applies to this one question; preserve the same 16-turn,
6,204-output-token, 80,000-total-token and 90-second limits. The admitted n4
source packet, question, procedure, hook and terminal schema remain unchanged.
Only provider configuration and private comparison-session identity may differ.

Use native Strands BedrockModel with SDK tool-based structured output; do not
assume support for Bedrock service-native structured-output configuration.
Preserve any compatibility error without fallback or automatic retry. Review
locally and independently before the one paid invocation. A success would permit
planning further matched evaluation, not immediate production promotion.

## Actual Sonnet 5 diagnostic result

The planned single matched comparison was attempted once with the exact
`us.anthropic.claude-sonnet-5` profile in `us-west-2`. The Bedrock `Converse`
request returned `AccessDeniedException`, with the provider error stating that the
model was not available for this account. The report records one request, zero
reported input/output tokens, zero inference cost, and no semantic result:
`/private/tmp/m20-recording-candidate-reports/sonnet5-run1/turn01.json`.

Read-only catalog and foundation-model availability metadata appeared active and
authorized, with entitlement and region available, but the agreement was
`NOT_AVAILABLE`. That metadata conflict does not establish account invocation
entitlement or a definitive reason for the denial. No fallback, retry, product
model switch, or promotion followed. Native candidates n2, n3, and n4 remain
unpromoted first-question semantic failures; required source reads and SDK hooks
were proved, but answer accuracy remains unaccepted.
