# Independent S2 structural review

Initial candidate verdict: **BLOCKED pending one migration/scope correction.** The superseding corrected structural approval and primary frozen verification are recorded below. This reviews application user-context persistence only, against the reduced S2 design appendix. It does not establish real D4/D5 semantics or native Strands session/compression support. No model calls, business writes, server restarts or product edits were performed.

Independent checks: `pytest tests/test_dialogue_context.py tests/test_live_advisory_gateway.py tests/test_receiving_facts.py -q` passed92 tests. `pytest tests/test_agent_platform.py tests/test_ambiguous_case_platform.py -q` initially skipped five loopback-dependent tests under the sandbox; the authorized loopback rerun passed all49 with no skips. These results cover the actual persisted-restart fixtures in the selected tests, not a running user's server restart. The primary's comparison of candidate mypy errors against a frozen baseline remains a separate pending check.

## P1 unsupported schema bypasses runtime isolation

Reproduction with `PYTHONPATH=src .venv/bin/python`:

```python
from the_missing_20.adapters import dialogue_intent as d
s = d.record_request({}, 'case-1', 'FOREIGN ORIGINAL REQUEST', 't1',
                     runtime_instance_id='foreign-runtime')
s['schema_version'] = 'future/v99'
r = d.restore_state(s, case_id='case-1', runtime_instance_id='current-runtime')
assert r['requests'] == []  # Fails: foreign original request is restored.
```

`restore_state` interprets every non-current schema as legacy. That admits requests from unsupported schemas and bypasses the supplied foreign runtime identity. Its raw authority selection uses the same not-versioned branch, so a foreign runtime's refusal can also migrate. The existing invalid-schema test has no requests and misses this failure.

Minimal correction: migrate user requests only from genuinely unversioned legacy state, and reject migration when any supplied runtime identifier differs. Unsupported schemas must discard requests/references and start a new conversation. Preserve a same-case, same-runtime persisted refusal even when the context schema is unsupported/corrupt; do not preserve foreign-runtime raw authority. The existing explicitly trusted `authority_state` parameter can preserve current application refusal independently. Do not add a second authority store. Freeze same-runtime unsupported-schema, foreign-runtime unsupported-schema, unversioned foreign-runtime and ordinary unversioned migration counterexamples before correction.

## Inspected structural boundaries

The gateway takes its instance ask lock before current-state reads, saves original bounded user text before inference and failure paths, and obtains fresh sources. Model context is constructed from user requests only; the removed legacy display fallback, TypeError retry-save path and full historical constraint reinjection are absent. A bounded generic current refusal statement remains, with refusal enforced from application state separately. Current question is retained whole, input packing is at most4000 characters and omitted-request reporting combines stored and packed omissions. User request storage remains500 characters per message and twelve entries.

Conversation identity is persisted across same-case requests/restart; request/run identity is distinct. The latest valid reference-bearing group survives intervening no-reference turns, is rejoined against current source receipts, and exposes missing/multiple/ambiguous candidates. Reference provenance explicitly says runtime validation is not semantic truth or authority. No restored quantities, plans or approvals are introduced. Case/conversation checks at completion discard late results, and platform recording checks again under its lock. This remains the single-operator, single-runtime/server constraint, not distributed or authenticated multi-user isolation.

The overall shape follows the reduced design and uses existing persistence, with no new store, SDK upgrade or summarizer. Passing structural tests does not show that the model correctly resolves every reference or answers complex questions. After the migration correction, an independent re-review and the applicable frozen checks remain necessary; D4/D5 live semantics remain a later gate.

Frozen SHA256 at this review:

| File | SHA256 |
| --- | --- |
| adapters/dialogue_intent.py | 773056cc66e54e18612160b85a6bcb570bdc694f176d1d184d22312c03d1e4a4 |
| adapters/live_advisory_gateway.py | 07f4a6b97db19d23786822755c5992956ad07a36b49142424e4094f898b2ee33 |
| adapters/agent_platform.py | 8d4e257f781c847ab925bbea551e1f1d882928f47c4d72345be1ea84cdcfcace |
| adapters/ambiguous_case_platform.py | 71a08602ceb65f4216810e4b2cc260f90199c8c4bada5f380f56f783d5fbd69b |
| tests/test_dialogue_context.py | faacdd0a5df0cbb571b69abe3418d7078a592a1596daa9c3b6e8b6c5068631de |
| tests/test_live_advisory_gateway.py | c92931908621b1e443e9eb16e54bebdede0fd310d7b1c52594b8c543e782f7c7 |
| tests/test_receiving_facts.py | 37e69d81dc7aeea2c41bee80b6e1477140a2cfbbba2f1fef91fafc74d45402db |

## Corrected migration review — superseding structural verdict

**APPROVED for the bounded S2 structural implementation**, superseding the BLOCKED candidate verdict while retaining its failure history. This is not real-model D4/D5 acceptance or a finalization-complete claim; the primary's isolated full checks remain a separate release gate.

The correction distinguishes an absent schema from an unsupported schema and checks any supplied legacy runtime identity. Unsupported schemas no longer restore requests or references. A same-case, same-runtime refusal survives unsupported context schema; foreign-runtime raw refusal does not. Explicitly trusted application authority still survives independently through the existing parameter, without a new store.

Independently exercised the original future-schema/foreign-runtime counterexample and a six-case matrix crossing unsupported versus absent schema with matching, foreign and absent runtime identity. Every request/refusal outcome matched the reduced design; trusted external refusal was also retained while foreign requests remained absent. Independent regression results: **95 passed** across test_dialogue_context, test_live_advisory_gateway and test_receiving_facts; **49 passed, zero skipped** across both platform suites with authorized local loopback support. No model, ERP call or running-server restart was used. The helper correction did not change the previously reviewed gateway/platform implementations.

Current frozen hashes supersede only these two earlier rows:

- adapters/dialogue_intent.py: `23762bfc99557d3a61560f7d536cd0cd001253d3eb0857f2d687c46ef623dfd5`
- tests/test_dialogue_context.py: `989f5bd77158c4ce7dafdd8fdb896cbec6e0849a7839fa6faa5110e9e55165d5`

The other five SHA256 values in the prior table were rechecked and remain identical. The baseline/candidate mypy logs report23 errors in5 files versus17 in3 files; the primary's normalized comparison reports zero new diagnostics and six removed. This is a baseline comparison, not a claim that this expanded four-adapter type invocation is clean. The required standard type gate and complete frozen regressions should be reported separately by the primary.

## Primary frozen release verification

The corrected seven-file candidate was applied to a clean detached checkout at `6c72c4b75639589e2f7a5acbd0ced0a25f84bf3a` in `/private/tmp/m20-s2-frozen-6c72c4b`; all seven files were byte-compared with the independently reviewed main-workspace candidate. Concurrent fresh-synthesis and billing-journal work was excluded. Locked frontend dependencies were installed from the existing local npm cache. The shared project Python environment was reused; this is a clean source checkout, not a newly installed Python environment.

`make check` exited zero: **236 formatted files**, Ruff pass, required strict mypy gate **51 files clean**, **1,692 Python tests passed in 61.27s**, and **101 JavaScript tests passed with zero failures/skips**. The complete private log is `/private/tmp/m20-s2-frozen-full-check.log`. Localhost socket tests ran with the permitted loopback environment. No live model, ERP write or running-server restart was part of this command.

The additional four-adapter mypy comparison is distinct: baseline23 errors in5 files versus candidate17 errors in3 files; normalized filename/message/code comparison found zero new diagnostics and six removed. The remaining baseline adapter diagnostics are not a clean expanded type gate.

This accepts the bounded persistence/identity/reference correction for delivery. The old first-turn reasoning failure, real D4/D5 semantics, same-order downstream effects and whole-browser acceptance remain open. No native summary/session feature or SDK upgrade was added.
