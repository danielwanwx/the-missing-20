# Fresh synthesis context: implementation checks

Status: FAILED / STOPPED / WITHDRAWN after the one independently reviewed live screen. The implementation inspection and initial blockers below are retained as history.

The initial helper filtered out all user text and rebuilt a history beginning with an assistant tool call. That does not satisfy Nova v1's first-message contract: the [official Messages API overview](https://docs.aws.amazon.com/nova/latest/userguide/invoke.html), directly checked September9, requires the first message to have the user role. The correction must preserve the actual original acquisition user request, without inventing tool execution or adding an answer hint. Removing intermediate model prose does not require removing the original user request.

The helper must also preserve original parallel tool-call grouping/order while filtering excluded blocks, require successful matching tool results, and keep tool-use identifiers valid across the complete history. Tests using only a fake Agent are insufficient to establish the emitted Bedrock request format; intercept the real SDK request formatter without network access. These checks precede any paid model screening.

The experiment still uses the existing canonical sources, same model/system prompt/synthesis instruction/schema and shared factory ledger/deadline. Only its first candidate is evaluated; there is no repair sequence. Normal product behavior remains unchanged. Initial RED tests and implementation progress are not semantic acceptance, and the previous failed effect-view variant remains stopped.

## Independent candidate review

Verdict: **BLOCKED for paid screening**, pending two bounded corrections. Reviewer performed no model invocation, network operation or business write. Independently ran `.venv/bin/python -m pytest tests/test_fresh_synthesis_context.py -q`: **13 passed**. This count is this file alone; it does not contradict the worker's larger focused suite.

Frozen candidate SHA256:

- live_advisory.py: `6090a7f7e064494b091d094e986d572a34b41b8ad3c35d852b9f72d4ab87ffca`
- fresh_synthesis_context.py: `25747da4d8d2b191da41e556c6e50b8a2917591d09478580483041957a29c48a`
- probe_fresh_synthesis_context.py: `743e2a0783f54b372a230a96304a9608737dffc24ae3428d46058f47fe068647`
- test_fresh_synthesis_context.py: `fbc4c4e9cbeeb4148d4bfc732e7c1024bb01d51f3fc3230d800c2cee00d9ee78`

**P1: duplicate completed tool-use IDs accepted.** The helper checks only pending IDs, then removes an ID on completion. Reuse of that ID in a later source pair is accepted and advertised as provenance_pairs_valid. Reproduction without external calls: load the test module with runpy under PYTHONPATH=src; obtain `_payloads()` and `_messages(payloads)`; change the second completed source's toolUseId and matching toolResult.toolUseId to the first source's ID; call `build_fresh_synthesis_context` with the fixture required/prohibited names. Actual result: no error, provenance_pairs_valid=True. Require global ID uniqueness across observed admitted history, not merely pending uniqueness. Add the counterexample; the real formatter test's set equality currently hides multiplicity, so also verify unique IDs and pair cardinality/order.

**P1: malformed first structured candidate is dropped.** In `_invoke`, a raw mapping rejected by `LiveAdvisoryResult.model_validate` creates AdvisoryValidationError without retaining that mapping. The private probe extracts only validation diagnostics' candidate, so this failure produces no first candidate despite the diagnostic's capture claim. Preserve the raw structured value in an explicitly unvalidated private diagnostic field, never as accepted model memory or public advice, and test the probe's failure artifact and final ledger. The reviewer supports the primary's concern based on the actual branch; no malformed candidate was submitted to a model.

Positive checks: offline probe reconstruction gives source payloads and original question exactly equal to `/private/tmp/m20-effect-view-live-01.json`; the withdrawn effect view is absent. Source payload equality/hashes cover original results including exact tool text bytes, and the original initial user request and parallel tool groups are retained. Canonical expected-answer keys and authority tools are excluded; no summary/helper inference is present. The new Agent uses the same factory/ledger, the existing synthesis instructions/schema and a remaining whole-run deadline, and diagnostic validation failure skips application repair. The single-workflow gateway factory retains the original USD0.16 caps. The probe writes its final ledger on ordinary captured failures and uses mode0600/O_EXCL.

Capture limits must remain explicit: a provider failure before structured data exists cannot supply a nonexistent candidate; early acquisition failure has no fresh context yet. A known fresh context should be attached on subsequent failure branches. Output is exclusively created only after inference; the initial existence check is not a reservation. For the planned unique private path this is not a business-write hazard, but it cannot promise artifact durability against a concurrent file creator or process death. Do not call all failure evidence complete without verifying the relevant branches. No screening authorization is granted by this blocked review.

## Corrected candidate independent review — one screening permitted

Superseding verdict: **APPROVED FOR ONE BOUNDED ORIGINAL-QUESTION SCREEN**, under the existing USD0.16 run cap and single-workflow configuration. This is diagnostic permission, not product release, semantic acceptance or permission to repeat until successful. The earlier blocked candidate and failed effect-view experiment remain preserved above and in their separate audit.

Independent `pytest tests/test_fresh_synthesis_context.py -q`: **17 passed**. Replayed the exact prior completed-ID-reuse counterexample; the helper now rejects it. The helper tracks global observed tool-use and result IDs, rather than only pending IDs. The actual SDK formatter test includes the final appended synthesis user message, checks ordered pair IDs and unique cardinality, and intercepts the SDK's native ValidationException retry with a local fake client. No provider request was made by this reviewer.

The malformed raw structured mapping now has a separate private UNVALIDATED capture, retained through the diagnostic wrapper with context and usage, while normal advisory errors do not expose it. Tests exercise schema failure, standard-path exclusion and private probe artifact/ledger recording. This capture is of the first structured value exposed by the run boundary; it is not a claim to capture every hidden provider/SDK intermediate response. Application semantic repair remains disabled for the diagnostic.

Offline artifact `/private/tmp/m20-fresh-context-reviewed-v3-20260909-offline.json` has model_sources and question exactly equal to `/private/tmp/m20-effect-view-live-01.json`. No effect view or expected verdict is restored. Code retains the existing system/synthesis instructions, schema, model factory and shared ledger/deadline; no helper inference or writer is introduced. The existing per-run dollar/request/token ceilings remain unchanged. SDK-native request normalization/retry is demonstrated, not a new application candidate repair; ledger request counts should not be presented as an independently measured count of every underlying HTTP attempt.

Use a new unique private output path for the one screen, retain all available failure evidence and actual ledger, then stop for independent factual/authority/next-step assessment. No broader experiment follows automatically from runtime COMPLETE.

Frozen SHA256 for this approval:

- live_advisory.py: `90e68f01350c8c2f4bbb0043978bf214b5fb974f499d387afdcc2a0944be126a`
- fresh_synthesis_context.py: `1db0b6b4e935f4726489a3cb991c169f756ec02b0ae48c53f47e0cfd12602203`
- probe_fresh_synthesis_context.py: `f25b94ff7f43cdf38f2c46f93bb8c2d91a97cfeaa95fa527afa14e83483ef8fb`
- test_fresh_synthesis_context.py: `579bec1362bb486e7182609629601ab76fcbffd370768f42b33735cfdc956cd0`

## Independent actual screening verdict — FAILED, stop remedy

Read the private `/private/tmp/m20-fresh-synthesis-live-01.json` after the authorized single screening. It returned AdvisoryValidationError with one NEEDS_EVIDENCE candidate. Usage: five logical requests,20,943 input tokens,1,358 output tokens,USD0.0211 and zero budget errors. Context telemetry records six admitted results (five source readers plus reconciliation), one retained original user block, two omitted assistant-prose blocks, no blocked correlation and the shared90-second deadline. Those fields establish that the intended context-removal treatment ran; they do not expose hidden model reasoning. No writer ran.

The candidate still asks to investigate the timeout and check whether the attempt was processed. The frozen source already supplies a complete scoped lookup of the attempted business key with no match, plus exact-lot approved quantity and a complete absent transfer. The answer identifies no actual missing prerequisite, omits the decisive quantity partition, and does not adjudicate the supplied competing explanations. It therefore fails on source use and reasoning independently of its rejected enum. Runtime validation correctly rejected it; a safe absence of writes is not sufficient business accuracy.

**Final experiment verdict: FAILED. Stop the fresh-context remedy and do not repeat this variant.** Support archiving the experimental diff/evidence and restoring only its owned product changes without touching accepted parallel work. The earlier one-screen approval is exhausted, not release approval. No repair was run, so this is not an equal-workload latency/cost comparison with prior eight-request repaired runs.

This result weakens the hypothesis that retained acquisition assistant prose alone caused the original diagnosis failure: removing it did not fix the first candidate. It does not establish that context never matters or that one model cannot solve any such case. A next step may be a separately designed model-capability comparison, holding the original complete source packet, question, schema, authority boundary and workflow constant, and independently scoring record identity, quantities, effect-versus-transport reasoning and next step. Freeze the alternate model's supported configuration and explicit cost envelope before authorization; do not silently raise the current budget, add an expected enum, append rescue paragraphs or use a same-model critic. Include counterexamples such as present/absent/unavailable destination and exact/mismatched QA before any broader acceptance claim. This review proposes that distinct mechanism; it authorizes no additional live call.

## Withdrawal and retained evidence

Primary archived the exact reviewed candidate and original synthetic-source offline/live reports under `artifacts/audits/2026-09-09-fresh-synthesis-context/`, with a SHA manifest. The tracked live_advisory entry point was restored byte-for-byte from accepted `adc4689`; the three experiment-owned new source/probe/test files were removed from active paths. Other workers' changes were preserved. No fresh-synthesis feature remains enabled or merged. Primary corrected focused checks passed17+29 tests (46); an earlier primary test command named two nonexistent test paths and exited4 before running tests, then the correct existing suites were run.

The initial automatic-approval rejection misclassified the outgoing original synthetic fixture as real ERP evidence. Inspection of all five model sources and their hardcoded fixture origin resolved it; the identical command was then approved and executed once. No data-transfer workaround or extra model request was used. The user has since explicitly reaffirmed authorization to send actual competition-demo ERP/SaaS evidence to Bedrock for ongoing testing.
