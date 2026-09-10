# Native receiving comparison

This is an isolated first-screen experiment, not product code or semantic acceptance. It compares one native Strands `Agent.stream_async` invocation in two variants:

- `n1`: generic read-only task prompt and natural-language output.
- `n2`: the identical prompt, five source tools, frozen question, source payloads, model configuration, limits, and `retry_strategy=None`, with only a narrow `answer`/`citations` structured-output tool added by Strands.

The generic prompt requires every available source before a final answer and says unavailable evidence remains unavailable. It has no Q4 answer, case disposition, expected citation, semantic validator, repair loop, retained assistant prose, ERP writer, or product advisory orchestration/repair invocation.

## Freeze inputs offline

```sh
.venv/bin/python experiments/native-receiving-comparison/native_receiving_comparison.py \
  --output /private/tmp/native-receiving-input-freeze.json
```

The default command reserves a new `0600` file before any fixture read, reconstructs the reviewed question and qualified `model_source_payloads` once, requires all five payloads, and writes `OFFLINE_INPUT_FROZEN`. It does not construct a provider or produce an answer.

The private bundle contains the exact contextual question and qualified payloads used by both candidates, their source-file hashes, and a common manifest. The manifest records the current script SHA, revision, SDK version, actual SDK-generated source-tool schemas and N2 structured-output tool schema, Nova Pro model ID/config (`us.amazon.nova-pro-v1:0`, zero temperature, 1551 tokens, non-streaming), `us-west-2`, and the explicit `missing20-sandbox` profile. It also records the 16-request/USD0.16/90-second/120-second caps.

The frozen source payload has runtime `observed_at` values generated while reconstruction reads the fixture. A second reconstruction therefore has different payload bytes even when the three fixture files are unchanged. N1 and N2 consume the one private input bundle instead of independently rebuilding it. Before a live call, the runner verifies the bundle manifest against current code/configuration and compares the historical artifact, ERP fixture, and SaaS fixture hashes with those captured in the bundle. An edited bundle without a matching manifest, changed source files, or changed code/configuration stops before model construction.

## Counters and structural records

Tests inject a local `Model` and exercise the real native tool loop. Records retain SDK-facing requests, raw model events, tool results, usage, schema errors, terminal exceptions, and partial agent events on failure.

- `sdk_invocation_count` counts top-level `Agent.stream_async` calls.
- `logical_model_request_count` is the shared factory ledger's request count.
- `observed_provider_attempt_count` is the capturing wrapper's observed `Model.stream` entries, including a turn rejected by the ledger before delegation.
- `request_turns_containing_schema_error_history` counts later provider request turns whose accumulated SDK message history includes a native N2 schema tool error. It is not a count of invalid candidates: one invalid candidate followed by a source read and a valid typed turn produces two history-carrying turns.

This paragraph describes the preserved base first-screen runner,
`native_receiving_comparison.py`, rather than the v2 session runner below. Its wrapper cannot
prove lower-level botocore transport retries. `retry_strategy=None` disables Strands' own throttle
retry strategy. In that base runner, all five source reads are required: absent source payloads or
a final answer before the five reads produce `STRUCTURAL_FAIL`. N2's native forced-format fallback
and later schema-only turns are recorded separately. No structural status evaluates answer meaning.
The v2 session runner still requires all five qualified payloads, but records offered, read and
unread tools descriptively; a zero-tool claim-free acknowledgement can be `STRUCTURAL_COMPLETE`
with `semantic_status: NOT_EVALUATED`.

## First screen and six-turn gate

The paid N1/N2 first-screen pair has been executed and reviewed in the
[first-screen review](../../docs/audits/2026-09-09-native-receiving-first-screen-review.md).
Both candidates were incomplete, and that result selected no winner or product path. The base
first-screen command below requires independent review of the exact frozen code and bundle, one
variant, the explicit existing D4 identity, and the matching bundle:

```sh
MISSING20_AWS_REGION=us-west-2 MISSING20_AWS_PROFILE=missing20-sandbox \
.venv/bin/python experiments/native-receiving-comparison/native_receiving_comparison.py \
  --execute-model --variant n2 --manifest /private/tmp/native-receiving-input-freeze.json \
  --output /private/tmp/native-receiving-n2-live.json
```

A single candidate keeps the existing USD0.16 cap; N1 and N2 together cap at USD0.32. This command is for the subsequent approved screen only.

## Six-turn native session sequence

`native_session_sequence.py` is a separate, offline-first continuation experiment. Its accepted
v1 first-sequence code and paid archive remain preserved in Git and private evidence. The new
prospective v2 session contract changes only the generic evidence-selection policy and N2 shape:
the exact prompt permits a claim-free acknowledgement with zero tool calls, but requires current
relevant source reads before an external business claim. It has no question router, answer
evaluator, expected-answer input, repair loop, or product change. N2 uses the local
`SequenceAnswer` shape with a 1–1600-character answer and zero to eight citations; it does not
modify the older first-screen `NarrowAnswer`.

Each `prepare` command starts from the production `FrozenFixtureAgentPlatform`, records the next
literal human request once, rereads the declared frozen source, and writes one exclusive bundle.
Q1–Q4 use ERP v1; Q5–Q6 use ERP v2. All five qualified payloads must be present in every
prepared bundle, but tool selection is observed rather than forced. The runner records offered,
read and unread source tools separately from raw reads. `STRUCTURAL_COMPLETE` means the native
SDK completed under the frozen contract; every record remains
`semantic_status: NOT_EVALUATED`, including a zero-read factual claim. Independent review stays
outside the model before a later turn can proceed. The runner does not create an advisory result
or replay an earlier answer into the product path.

Each candidate turn is a separate process and restores only its own
`SnapshotSessionManager`/`LocalFileStorage` history. Its session ID and agent ID include the v2
artifact-schema identity, and v1 prepared inputs or predecessors stop before a model call. The
current candidate uses
`NullConversationManager` with proactive compression disabled: it deliberately retains the
fixed six-turn native history and lets the existing 80k native limit, 16-request/USD0.16
per-turn ledger, 90-second invocation limit, and 120-second process limit stop an overflow.
It is not a long-conversation policy, a summary, or a custom memory layer. The parent
sequence ceiling remains USD0.96 per candidate and USD1.92 for both; it serializes stages and
stops a candidate after a failed predecessor.

The preceding `SlidingWindowConversationManager(window_size=40)` baseline is retained only
as a failed private continuity observation: serial five-source reads evicted the Q2 refusal
before Q6 while retaining the Q5 answer. Its artifacts and exact source SHA are private, and
that result is not a pass or a reason to alter the question, schema, or answer. The current
runner checks prompt, model/profile configuration, source-tool and N2 schemas, native session
configuration, source/manifest/question hashes, SDK version, revision, and script hashes both
before construction and after snapshot restoration. It stores `AgentResult.message` and N2
`structured_output` as the final result separately from raw SDK/model events.

The retained sliding-window proof used a scripted model whose tool-use IDs repeated across
turns. It establishes the recorded continuity loss only; it does not establish globally unique
tool-pair behavior. The fresh-process offline proof uses turn-scoped IDs and separately requires
every persisted tool use to have exactly one unique matching result.

The public CLI does not install a fake model. Offline tests use a local protocol model in fresh
OS processes to prove a zero-tool read-only acknowledgement is restored before a following
current-ERP source read in both answer formats, as well as v1/v2 isolation and ordered tool-pair
history where pairs are present. A future v2 live turn requires an independently reviewed frozen
`PREPARED` bundle, a fresh private session root, and explicit `--execute-model`; no paid v2
sequence call is approved by this README.

The preserved [v1 first real sequence](../../docs/audits/2026-09-09-native-session-first-sequence-review.md)
ran under the former all-five-source-read requirement. N1 stopped at Q2 and N2 at Q1; later turns
remain NOT_REACHED. The real N1 restart restored its actual history, but neither candidate
completed six turns. Preserve these failures: normal tool selection, evidence sufficiency and
citation quality need separate evaluation in the prospective v2 comparison. No product promotion
follows.
