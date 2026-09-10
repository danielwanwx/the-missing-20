# Native six-turn conversation and restart experiment

Status: independently approved for isolated implementation and offline tests.
The initial window40 policy failed actual six-process continuity testing; the
selected replacement is native NullConversationManager for this bounded sequence.
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
not byte-identical. Production case preparation supplies the current qualified
source bundle; its detailed case authority remains audit-only. The model sees
the current control tool's fixed read-only policy and the literal Q2 refusal
in native history. This does not test dynamic product approval-state integration
or fabricate a successful product AdvisoryRun. Each new
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
restore the prompt and state. Use explicit NullConversationManager,
retry_strategy=None and checkpointing=False. Preserve full native history and
stop on context overflow; do not enlarge budgets or silently trim. Record actual
active history and complete tool pairs, rather than inferring continuity from
the manager name. This is a bounded six-turn baseline, not a long-chat policy.

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

## Preserved capacity failure and revised selection

The initial explicit SlidingWindowConversationManager policy used window40,
should_truncate_results=True, per_turn=False and no proactive compression.
An actual six-process N1 run with valid serial acquisition of all five tools
produced histories of12,24,36,36,36,36 messages. Cumulative removed-message
counts were0,0,0,12,24,36. Q6's first SDK-facing request retained the real Q5
answer but had lost Q2's refusal. Q5 also read the renamed v2 ledger source;
older v1 tool results remained historical. Thus persistence worked while the
chosen capacity policy failed the required continuity gate.

The exact window40 runner SHA256 was
`b79f6a5b9ac40de0003948233f4a3817db07150b4cdd0d796090a977cc376c4b`.
Its code and all six prepared/turn records remain privately preserved under
`/private/tmp/m20-native-session-window-2d77/`, including a hashed
`continuity-failure.json`. No paid model call used this policy.
That older fake model reused tool IDs across turns. The recorded eviction is
an observed capacity failure, not proof of a globally unique, provider-valid
six-turn tool history. The corrected Null experiment separately checks ordered,
unique tool-use/result consumption; these evidence limits are not interchangeable.

Independent review conditionally approved explicit native NullConversationManager
after this failure was demonstrated. Installed1.53 source and the
[official conversation guide](https://strandsagents.com/docs/user-guide/concepts/agents/conversation-management/)
confirm that it keeps full history and re-raises reactive overflow. Its higher
input cost and old/new evidence coexistence remain measured risks. It adds no
summary call, custom memory or arbitrary window increase. The replacement must
still pass actual six-process N1/N2 retention and fresh-source tests before the
paid gate; the failed policy is retained, not relabeled successful.
