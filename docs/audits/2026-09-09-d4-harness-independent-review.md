# D4 diagnostic harness independent review

## Conversation reporter candidate

Verdict: **BLOCKED by a missing-evidence false-positive check.** Scope currently covers only `scripts/diagnostics/verify_receiving_conversation.py` and `tests/test_verify_receiving_conversation.py`. The frozen-source HTTP server is not yet reviewed. No model, ERP, IAM or external mutation was invoked.

Independent `pytest tests/test_verify_receiving_conversation.py -q`: **11 passed**. Candidate SHA256:

- reporter: `0a6985e86ca3c9f50d9267e16fa583be7a27517113e37e6058dafe0f7fab0f72`
- tests: `06491a017e2140782b3a40e8f6d94dabaf05006c589e68500e39c5e76fb6b353`

### P1: missing persisted context evidence can still finish COMPLETE

Reproduction: load the test module with runpy, create `FixtureGateway(('one','two','three','four'), context_turns=(99,99,99,99))`, and wrap its callback to remove `human_requests` from every returned projection. Run `run_diagnostic` into a new temporary output path. Actual result: status COMPLETE and runtime_status COMPLETE, despite impossible context counts and no persisted user-request evidence.

`context_matches_persisted_state` is added only if human_requests is a list and persisted requests_omitted is an integer. Missing or malformed fields skip the check rather than fail it. This contradicts the requirement that unknown continuity evidence cannot become a pass. Make those production persistence fields explicit required checks, validate nonnegative/nonboolean omitted counts and valid request entries, and then reconcile context+omitted counts. Verify the newest persisted original question is the one just sent; a stored length alone does not establish that this request was saved. Add absent/malformed fields and dishonest counts as regressions. Do not implement a fallback inferred transcript to manufacture proof.

### Inspected positive boundaries and limits

The output is reserved with O_EXCL and mode0600 before any HTTP request, then checkpointed with flush/fsync. Existing output causes no requests. Successful public responses are retained in full; HTTP/transport errors retain available safe bodies/usage, stop the segment, mark later questions NOT_REACHED and produce a nonzero CLI exit. Unknown usage remains null rather than a false zero. Attachments are optional unless explicitly required. Questions follow the real endpoint's question-only contract and500-character bound; no new-conversation command is fabricated. Case/conversation identity and optional expected restart conversation ID are checked. Runtime COMPLETE explicitly leaves semantics pending.

The writer updates its reserved file in place; fsync checkpoints are not an atomic crash-proof journal during truncate/rewrite. Full successful response retention supports post hoc inspection, while bounded/redacted HTTP error bodies do not guarantee capture of every provider detail or usage field in an arbitrarily large error. These are diagnostic limitations, not reasons to add a generic telemetry framework. Keep the correction local to required context-evidence validation.

The script is longer than a minimal probe because it handles segmented reports, runtime checks and failure retention. No arbitrary line-count rewrite is requested. It must still be tested with the actual forthcoming HTTP harness before any six-turn paid screen; this review does not authorize that call or certify source-transition semantics.

## Frozen-source server independent review

**APPROVED for the offline production-HTTP harness slice.** This separate approval does not resolve the reporter's earlier P1 or authorize the complete paid sequence. Reviewed only serve_frozen_receiving_dialogue.py and test_frozen_receiving_dialogue_server.py plus the constructor paths they invoke.

Independent tests with authorized local loopback: **4 passed, zero skipped**. The tests send real local HTTP requests through the production handler, gateway and AgentPlatform, using an explicitly marked offline runner and local source files. They demonstrate source rereads, the exact ledger rename with unchanged voucher/quantity, retained original questions/refusal/reference identity, default provider-unconfigured behavior and unavailable-source zero-runner behavior. The restart fixture recreates server/platform objects in the same OS process; an actual CLI stop/start remains the primary's pending offline gate, not a result of these tests.

Independently checked both v1/v2 ERP fixtures and SaaS file in `/private/tmp/m20-s2-d4-screen-v2`: each passes the reader's declared contract without changing source files. Malformed JSON/schema/read-only declarations fail locally before a source fallback or model call. An unavailable declared source retains the production SOURCE_UNAVAILABLE guard and saves the human request without invoking the runner. Startup itself invokes no model.

The harness injects both readers and an executor-free AgentPlatform, uses a fresh empty isolated configuration root and requires a harness marker for resume. It does not load the project .env. The base server still constructs inert photo/automatic-investigation support, but ERP writer credentials and enabled receiving/manifest/handoff configuration are rejected before construction; the empty runtime has no queued work and automatic investigation is disabled. Independently checked representative inherited ERP secret, manifest, auto-prepare and handoff environment values: all are rejected before runtime/source construction. Settings.from_env reads environment values without credential-file or provider access; real model access remains explicit --execute-model. No model profile or authentication stack is changed.

POST is restricted to the existing ask route, with no fixture-change, approval, receiving, execute or auto-enable endpoint. The packet adds truthful frozen/simulated provenance while preserving source facts and the normal receiving contract. `external_calls=0` is a reader implementation property, not a measured interception of arbitrary future code; the selected injected code path contains no external-reader call. No general financial or UI acceptance follows.

Frozen SHA256:

- serve_frozen_receiving_dialogue.py: `e29043bebd54b0403ddd658dee05cd8f8eae1adfcf0018da931fdaaf5b6fa3b8`
- test_frozen_receiving_dialogue_server.py: `9180c68fb6b07bcc277d09f1a9f5e5127e66b75a14ec2b461e51a5b57d4084a1`

Known import-following mypy baseline diagnostics remain separate from this bounded behavioral approval. The primary should retain its baseline comparison and required isolated checks; this reviewer does not label a failing broad import type-check clean.

The primary subsequently supplied `/private/tmp/m20-s2-d4-offline-process-proof.json` for two distinct CLI processes using the same reviewed server SHA and private runtime. Independent inspection confirms retained projection evidence for stable conversation identity, persisted refusal/questions, and AGENT_UNAVAILABLE with model disabled across the process boundary. This supplements the same-process tests with a primary-executed actual process restart. It establishes persistence under disabled inference, not paid-model continuity semantics, and does not resolve the reporter P1.

## Corrected reporter and bounded screen gate

**Reporter correction APPROVED; one frozen six-question D4 screen is permitted**, with per-turn review and the stop conditions below. This supersedes only the reporter's earlier BLOCKED candidate verdict. It does not establish S2 live semantic acceptance or broader D4/D5 coverage.

Independent reporter suite: **16 passed**. The original missing-human_requests/context99 reproduction now fails at the baseline after one GET and before any ask. Required persisted schema/runtime/case/conversation identity, nonboolean nonnegative omission counts, bounded complete request entries and exact current saved question are explicitly checked on response and post-state. Context+omitted reconciliation is mandatory, rather than conditionally skipped when evidence is missing. The fresh initial empty context/request-list exception is limited to the baseline, where no current question has yet been persisted.

Independently applied the corrected persisted-context validator to all six before/answer/after projections in the primary's actual two-process proof. Both initial fresh and resumed production shapes validate. This confirms native-field compatibility without inventing a new endpoint or populating missing context evidence. The report remains runtime-only; HTTP failure tails, private output reservation and per-turn evidence remain as previously inspected.

Corrected SHA256:

- verify_receiving_conversation.py: `311f19ae1f78c7b77cc576632a03a3cdda8595403fc992fabedfabd9832625ae`
- test_verify_receiving_conversation.py: `06fdf871bc8b6b42c65c6141c721e258cd5fac23a31ee5e0db64ddd419cc48c8`

Together with the separately approved server SHA and offline real-process restart proof, this permits the **one** original frozen six-question manifest in `/private/tmp/m20-s2-d4-screen-v2`. Run one question per reporter invocation into distinct private reports so the primary can inspect each answer before proceeding; require the established conversation ID on subsequent segments. Restart the harness process before question5 and switch only to the declared v2 ledger-rename fixture. Preserve exact manifest/questions/source hashes, refusal, quantity and receipt identity; no question substitutions or repeat attempts. Existing single-workflow Nova Pro per-question USD0.16/request/token caps and the six-question maximum remain fixed. Stop on runtime failure or safety-critical semantic failure and mark remaining sequence positions not reached in the aggregate report. A single-question reporter cannot infer the unreached tail of the overall six-question sequence, so orchestration must preserve that sequence-level fact explicitly.

The reviewer performed no paid/model call or source mutation. D5, repeated sequences, general changed-reference disappearance handling and full UI/business acceptance remain outside this approval.
