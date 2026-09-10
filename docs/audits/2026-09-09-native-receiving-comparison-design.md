# Native Strands receiving comparison

Status: proposed isolated experiment, not a product change or semantic pass.
The user requested research-led alternative selection instead of further
patches to the failed advisory loop. Main remains `8306a89`; the unfinished
journal-binding candidate is frozen separately and is not a dependency here.

## Question and mechanism

Can a task-focused native Strands loop answer the receiving question more
accurately than the retained custom acquisition/finalization pipeline, without
adding question-specific answer checks? Current D4 failed at Q4 despite its
model-facing input containing the qualified physical observation basis. That
supports investigating reasoning/task design, not assuming memory loss.

Installed Strands1.53.0 supports ordinary tools and a structured output tool in
the initial invocation. It restricts tools during a later forced-output fallback
after an unstructured end-turn. The product's two top-level invocations are an
application choice, not an unconditional SDK requirement. The existing
`_EvidenceCompletionHook` addresses early finalization; bypassing that risk would
not count as an improvement. [Native structured output documentation](https://strandsagents.com/docs/user-guide/concepts/agents/structured-output/).

Candidate N1 uses one native invocation, consumed through `Agent.stream_async`
to retain intermediate outputs, with the existing case-scoped,
read-only source payloads and natural-language output. Candidate N2 uses the same
single-invocation task, tools, source payloads, model and budgets, with a narrow
answer/citations schema. Neither carries the cross-domain recovery/disposition
schema, repair loop, critic or a generated summary. This is an architectural
screen of a dedicated answering component; it does not establish which removed
piece caused any difference from the historical pipeline. N1 versus N2 isolates
the response-format choice within that candidate architecture.

The rationale is to test a simpler task boundary using existing SDK primitives,
consistent with task routing and clear tool contracts in [Anthropic's engineering
guide](https://www.anthropic.com/engineering/building-effective-agents). These
recommendations are hypotheses for this model, not evidence of improved results.

## Fixed first screen

- Reuse the preserved D4 Q4 question, bounded prior human intent and qualified
  current source packet through the reviewed reconstruction helper. Never pass
  the retained failed answer or expected answer to either candidate model.
- Freeze exact input hashes, candidate system prompt, tool descriptions, output
  schema, installed SDK and script SHA before calls. Use the existing NovaPro
  factory/profile/price ledger and existing D4 caps; no model change, new IAM,
  silent cap increase or new service. Record the actual caps in the manifest.
- Freeze the identical prompt/tool/source/history bytes for both candidates at
  the same time, before either run. Do not use N1's answer to alter N2. Each is
  limited to16 logical model requests and USD0.16; both together at most USD0.32.
  Preserve the existing advisory90-second wall deadline and outer120-second
  process bound, plus existing input/output token caps recorded in the manifest.
  One top-level SDK invocation is not one model request.
- Inspect and freeze N2's native schema retry/fallback behavior before live use.
  Record every raw candidate and count every request against the same budget;
  native repair cannot be hidden as a first-answer success. Application semantic
  repair remains disabled. If SDK behavior cannot be bounded or captured, the
  candidate does not pass the offline gate.
- Installed1.53 has no separate schema retry count: invalid schema returns a
  native tool error and further model decisions are bounded by explicit Limits
  and the shared factory ledger. It permits one forced-format fallback after
  an untyped end-turn; a further forced end-turn errors. Set `retry_strategy=None`
  for both candidates to disable SDK throttling retries. Preserve and report any
  provider transport retry separately from logical model requests. Consume the
  native event stream to retain each model message, tool result, schema event,
  usage and terminal error; recording only the final AgentResult is insufficient.
- Each candidate gets one first screen, with every native model request, tool
  read, usage, cost, elapsed time, raw answer, terminal error and missing-source
  outcome retained. Reserve distinct private output files before any invocation.
- Tools serve the same qualified source JSON as the current model-facing
  payloads, scoped to the frozen case. They cannot call ERP or write anything.
  Require all five D4 source reads before accepting the screen as complete.
  An early final or forced-output fallback that prevents those reads is a
  structural failure; retain it and stop, without repairing the candidate.
- A generic task instruction asks the model to answer the newest question using
  source evidence, resolve references using prior human context, distinguish
  observations from inferences, cite records and identify unavailable evidence.
  It contains no Q4 expected answer, case-specific exception, stock disposition
  label or authorization. Freeze it before the first candidate.
- Scripted tests establish native tool execution, early-final/incomplete-read
  reporting, output reservation, exception/usage recording and exclusion of
  retained answers. They cannot establish answer accuracy.

## Decision and continuation

An independent reviewer assesses directness, evidence support, exact record/UOM
identity, scope and invented claims. Required answer for this specific evidence:
receipt/stock records establish recorded receiving; this packet does not contain
an independent observation of carton contents. This rubric stays outside model
inputs. Format validity or a matching phrase is not semantic acceptance.

The preserved custom-pipeline D4 result is a historical failed baseline, not a
contemporaneous paired run. It is not rerun merely to obtain a better score.
Neither new candidate wins on a single Q4 success. A viable candidate proceeds
to the complete six-turn/source-change/restart sequence, then the frozen broader
core and untouched held-out cases with required repetitions. All attempts count.
No product integration or finalization acceptance occurs at this first screen.

If both native candidates fail the same semantic boundary, stop them and return
to the distinct model-capability route or evidence/task-design research. Do not
add a Q4 regex, output template or same-model critic. Native summarization remains
a separate long-context experiment; it is not credited with correcting reasoning
over facts already present. Nova2 access remains subject to the existing specific
  IAM approval, which has not been given.

## Independent design gate

Independent reviewer approved isolated implementation and offline verification,
with shared-input freezing, explicit16-request/USD0.16 caps per candidate,
USD0.32 total, intermediate SDK retry visibility, all-five-source coverage and
actual-input answer-leakage tests. Those corrections are incorporated above.
The reviewer found the native task-focused architecture distinct from the
withdrawn fresh-synthesis context edit, while retaining the confounded historical
comparison limitation. Live screening requires review of the actual frozen
implementation, manifest and offline results. No live call is approved merely
by this design record.
