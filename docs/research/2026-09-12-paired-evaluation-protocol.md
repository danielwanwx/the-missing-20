# Receiving evidence comparison: preregistered protocol

Prepared September 12, 2026. Status: implementation preparation, **no scored runs yet**. This protocol makes the accepted [product thesis](2026-09-12-product-thesis-and-judge-review.md) executable. Candidate source hashes and exact held-out inputs must be frozen before scored calls.

## Question and limits

Does independent receiving/quality and fulfillment/contract investigation improve a constrained receiving decision enough to justify an additional coordinator? Compare a rules/form baseline, one Strands investigator, and a fixed native Strands Graph. This is a small engineering selection exercise, not a claim of production accuracy, customer validation, or novelty over enterprise products.

All cases are explicitly synthetic, immutable snapshots. Real Bedrock calls on those snapshots are not live external retrieval or ERP execution. A separate same-case live application check is required for any promoted change. The existing completed ERP order is preserved.

## Fixed model and resources

The September 12 identity check passed. A minimal Opus 4.6 invocation returned `AccessDeniedException`; Nova Pro returned a real response (5 input / 8 output tokens). Select Nova explicitly for both candidates; do not implement fallback or describe Opus as restored.

| Setting | Single investigator | Two specialists and coordinator |
|---|---|---|
| Model | `us.amazon.nova-pro-v1:0`, `us-west-2`, temperature 0, standard inference | Identical for every node |
| Provider request ceiling | 8 total | 3 receiving + 3 fulfillment + 2 coordinator; 8 total |
| Input token ceiling | 32,000 total | 12,000 + 12,000 + 8,000 |
| Output token ceiling | 6,000 total | 2,000 per node |
| Per-request output ceiling | 1,024 | 1,024 |
| Estimated cost ceiling | USD 0.06 per workflow | USD 0.06 per workflow across all nodes |
| Wall-clock ceiling | 180 seconds | 180 seconds across the graph |
| Prior conversation | None | None |
| Actions | Read-only | Read-only |

The complete experiment has a USD 3 estimated model-cost ceiling, including development calls, failures and scored attempts. Reserve budget before requests; record unknown-usage failures conservatively. Each workflow gets its own identical resource allowance; a separate durable experiment ledger accumulates all attempts and must not be reset to obtain more spend. Graph nodes share an atomic allowance or strictly disjoint allocations whose sum cannot exceed it. No paid LLM judge is included. Local Codex implementation/review usage is separate and is not described as Bedrock spend.

Strands 1.53.0 `Limits` is a supplementary turn-boundary guard, not a native hard input-token limit. The provider boundary must reserve a conservative serialized-request upper bound before a call and reconcile reported usage afterward. The Graph's combined input/output limits are 14,000 / 14,000 / 10,000 tokens. Record reservation estimates separately from actual provider tokens; any discovered underestimation invalidates the claimed strict budget check and requires a fix before continuing.

The pricing basis is USD 0.80 per million standard input tokens and USD 3.20 per million standard output tokens. The public [AWS Oregon price list](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonBedrock/current/us-west-2/index.json), version `20260911124408`, published `2026-09-11T12:44:08Z`, was queried directly on September 12: `USW2-NovaPro-input-tokens` is USD 0.0008 per 1K and `USW2-NovaPro-output-tokens` is USD 0.0032 per 1K. Budget cache input conservatively at the uncached rate; report actual cached usage separately if present. These are estimated token charges, not an AWS invoice or an account-wide spending limit.

## Candidate boundary

The single agent can retrieve the same union of records available to the specialists. Partition the Graph by receiving/quality and customer fulfillment/contracts, declaring any overlap. Retrieval parameters must affect the returned records. Neither candidate receives a duplicate full snapshot in its prompt, precomputed feasible plan, retained model answer, expected verdict, or evaluation rubric.

Both specialist results must exist, match case and snapshot identity, and cite records actually returned to that actor before the coordinator runs. A typed record extract can be checked deterministically; an inferred interpretation is not made true merely by having a valid record ID. The coordinator receives validated observations and labeled interpretations. No approval or execution tool is available.

The rules/form baseline reports mechanically computable quantities and unresolved questions with the same source access. Preserve the operator investigation it would require. Do not score its writing style or invent measurements of human time saved.

## Cases and freezing

Use four development cases for wiring: a completed simple case, split receipt with pending quality evidence, missing unit conversion, and ambiguous acknowledgement. Development examples and expected outcomes are separate files. They do not enter scored results.

After candidate code and schemas are frozen, author eight held-out inputs independently of implementation tuning: normal partial receipt; confirmed shortage; sample hold versus all-units defect; wrong-lot quality evidence; missing unit conversion; posted receipt with lost acknowledgement; conflicting stale version; unavailable authoritative evidence. These families are declared now; exact quantities, record IDs, questions and answer keys are frozen separately afterward. Include allocation pressure and an unsupported causal-attribution request within these cases.

Run eight cases × two model candidates × two repetitions = **32 paid model workflow starts**, alternating candidate order by case and repetition. Also execute and score the deterministic rules/form baseline once on each held-out case: eight non-model executions, for 40 planned scored executions in total. Its deterministic repeatability is checked locally; no human-speed measurement is implied. A model workflow may make several provider requests. Record starts, not just successful answers. Preserve every failure and timeout. Stop expansion after two occurrences of the same failure mechanism, investigate, and label any changed candidate as a new version; do not tune against held-out answers and reuse them as untouched evaluation.

## Evaluation and selection

Use the actual Strands Evals package with a custom deterministic evaluator for case/snapshot identity, exact business quantities and units, expected eligibility or missing-evidence state, citation membership and actor scope, source coverage, and prohibited approval/execution fields. A blank or generic defer is not automatically correct.

Export randomized candidate labels for blinded agent-assisted semantic review of directness, contradiction recognition, unsupported causal attribution, appropriate uncertainty, and prose implying approval or completed execution. A reviewer separate from the implementation may provide another model judgment, but this is not independent human ground truth or calibrated human labels. Generic LLM judge scores cannot establish ERP truth. Keep semantic disagreements and mechanical scores distinct.

Record source/code/config hashes; model/provider IDs; per-actor tool calls and returned record IDs; input/output/cache tokens; estimated cost; latency; answer and classified failure; reviewer decisions. Source coverage is evaluated against each actor's declared access, not a fictitious universal sequence.

Promotion requires zero critical business/authority errors; at least two different difficult cases improved in both repetitions without regressions elsewhere; and compliance with the frozen resource limits. If the single agent already succeeds on all cases, retain the Graph only for a repeated, material efficiency improvement. Otherwise keep the simpler verified candidate. A failed comparison is a useful selection result, not permission to claim multi-agent benefit.

## Dependency preparation

An isolated environment at `/private/tmp/m20-evals-venv` successfully resolved and installed `strands-agents==1.53.0` and `strands-agents-evals==1.2.0`. Evals also installed `strands-agents-tools==0.8.8` transitively. All three package metadata entries declare Apache-2.0. Imports of GraphBuilder, Case, Experiment, Evaluator, EvaluationData and EvaluationOutput passed; the last two live in `strands_evals.types`. The main application environment and dependency lock were not changed. These import checks are not evaluator execution or a real Graph run; those remain implementation acceptance work.
