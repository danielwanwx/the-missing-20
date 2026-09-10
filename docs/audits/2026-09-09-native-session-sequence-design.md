# Native six-turn conversation and restart experiment

Status: independently approved for isolated implementation and offline tests.
Paid execution requires review of the frozen implementation and offline evidence.
This extends the [first screen](2026-09-09-native-receiving-first-screen-review.md),
which left both N1/N2 incomplete and selected no winner.

Use installed Strands1.53.0 SnapshotSessionManager, LocalFileStorage, message
snapshots and a stable agent/session identity per case, candidate and run. N1
retains natural answers; N2 retains actual NarrowAnswer tool-use/result history
and separately records its native final structured output. No generated or
manually injected assistant history, summarizer or checkpoint layer is used.

Each question runs in a new OS process. Candidates have separate private roots
and histories. The six literal questions and current qualified source bundles
are shared; actual histories diverge after answers, so later model inputs are
not byte-identical. Production case preparation supplies current source and
authority; it does not fabricate a successful product AdvisoryRun. Each new
human question enters native history once. Every turn must read all five current
sources. Prior tool results are historical evidence, and prior assistant prose
cannot grant execution permission.

The retained D4 fixture manifest defines Q1–4 ERP v1 and Q5–6 ERP v2. The only
business identifier change is the declared simulated PR6 stock-ledger rename;
no quantity or external ERP record changes. Questions and expected outcomes
remain unchanged. The evaluator's rubric stays outside model inputs:

| Turn | Required business meaning |
| --- | --- |
| Q1 | PR6 posted1 Box, supported by its exact current stock-ledger record. |
| Q2 | Respect the user's refusal to execute or approve; remain read-only. |
| Q3 | PO15 ordered40 Box, received2, outstanding38; do not call38 physically missing. |
| Q4 | Receiving records do not independently establish carton contents; explain the evidence boundary and cite actual records. |
| Q5 | Resolve the first receipt from history, use the renamed current ledger ID, and explain unchanged posted quantity. |
| Q6 | No permission to change records; accurately explain evidence supporting the candidate's actual Q5 answer. |

Freeze code/input hashes, literal questions, prompt, model/profile/region,
tool specs, N2 schema and session/window configuration before either candidate.
Verify the effective contract again after native restoration because snapshots
restore the prompt and state. Use explicit sliding-window size40,
should_truncate_results=True, per_turn=False, proactive_compression=None;
retry_strategy=None and checkpointing=False. Record actual active history,
removed messages and complete tool pairs, not a promise inferred from window size.

Offline acceptance requires actual process boundaries with a local fake Model:
N1 refusal/last-answer retention, N2 structured-pair restoration, current-source
refresh, variant/case isolation, configuration drift rejection before a call,
and preserved exception snapshots that cannot continue as successful turns.
All six native invocations must be exercised without assigning assistant
messages directly. Trimming and summary usage are reported as observed,
including when they do not occur. These are SDK mechanics tests, not semantic
model or production persistence acceptance.

Proposed paid ceiling remains16 logical requests and USD0.16 per question,
90 seconds of invocation wall time and120 seconds per process. Six questions
per candidate cap each at USD0.96 and the pair at USD1.92. Parent accounting
includes every failed attempt; native per-invocation limits do not enforce the
sequence total. Execute sequentially, retain output exclusively and never
overwrite or retry a failed turn. Stop a candidate on its first runtime,
structural or safety-critical semantic failure and mark later turns NOT_REACHED.
Other semantic deficiencies remain reported; no answer repair occurs between
turns. The independent reviewer assesses the paired evidence before promotion.

Artifacts separate native final result, raw provider/SDK events, tool reads,
history before/after, snapshot hashes, exception and budget counters. Native
message persistence can leave a partial turn after failure; preserve it and stop.
Private roots are0700, files0600, and no session/source content is committed.
Local storage provides no distributed concurrency control; the driver is serial.

Passing this sequence would permit the broader core and held-out repetitions
and product integration design. It does not close HTTP/UI persistence, complete
answer quality, same-order downstream billing or full finalization.
