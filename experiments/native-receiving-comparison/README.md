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

The wrapper cannot prove lower-level botocore transport retries. `retry_strategy=None` disables Strands' own throttle retry strategy. All five source reads are required; absent source payloads or a final answer before the five reads produce `STRUCTURAL_FAIL`. N2's native forced-format fallback and later schema-only turns are recorded separately. No structural status evaluates answer meaning.

## Live gate

A live call is not the default and has not been run. It requires independent review of the exact frozen code and bundle, one variant, the explicit existing D4 identity, and the matching bundle:

```sh
MISSING20_AWS_REGION=us-west-2 MISSING20_AWS_PROFILE=missing20-sandbox \
.venv/bin/python experiments/native-receiving-comparison/native_receiving_comparison.py \
  --execute-model --variant n2 --manifest /private/tmp/native-receiving-input-freeze.json \
  --output /private/tmp/native-receiving-n2-live.json
```

A single candidate keeps the existing USD0.16 cap; N1 and N2 together cap at USD0.32. This command is for the subsequent approved screen only.
