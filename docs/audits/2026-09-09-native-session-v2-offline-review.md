# Native session v2 — offline mechanism review

Status: standards and specification/mechanics independently approved.
This is an isolated experiment, not a real-model, product or F03 acceptance.

The prospective v2 contract uses the installed Strands 1.53.0 native session
stack and evidence-appropriate tool selection. All five qualified source
payloads remain required inputs. A claim-free instruction acknowledgement may
read no tools; factual source selection and answer meaning require separate
review. Every SDK-complete record explicitly remains `NOT_EVALUATED`.
The [approved design](2026-09-09-native-session-evidence-selection-design.md)
and [primary-source research](../research/2026-09-09-native-conversation-evidence-evaluation.md)
explain this choice. No SDK upgrade, new dependency, summary layer, router,
answer repair or product integration was added.

## Frozen candidate and actual checks

| File | SHA-256 |
| --- | --- |
| native_session_sequence.py | 55428bdf2352cc2138f2a14168526744fc09132ca56bde50a8db9a200c72871c |
| test_native_session_sequence.py | f22e1f9d5d582a5a8a1de5508e32271e45330a0d62aad16eb03dc9baf629b4b1 |
| README.md | f52e0a223d3edd8e62f9fbe23cb6c93836abc658a7cf9dee26ee0332cc068cb5 |

The files are under `experiments/native-receiving-comparison/`. The worker's
Ruff formatting/check, compilation and scoped mypy checks passed. Six tests
passed across three separately retained groups: zero-read factual output;
six fresh processes for each candidate; four isolation, version, restoration
and failure-snapshot cases. These checks used a local scripted model, not
Bedrock. The execution revision was b19fad3 with uncommitted candidate files.

The primary read all twelve core result files. Each turn's `history_before`
exactly equals the preceding actual `history_after`. Both candidates recorded
source-read counts 5, 0, 1, 5, 5, 5. Q2's actual claim-free acknowledgement
survived restoration before Q3's current ERP read. Q5 returned SYN-SLE-V2.
The final answers are scripted fixtures and provide no real reasoning-quality
evidence. Native history lengths after each turn were 12/14/18/30/42/54 for N1
and 13/16/21/34/47/60 for N2.

Private evidence is retained in:

- `/private/tmp/m20-native-session-v2-preflight-58160e5-02` (exit 0);
- `/private/tmp/m20-native-session-v2-core-retry-b19fad-01` (exit 0);
- `/private/tmp/m20-native-session-v2-counterexamples-b19fad-02` (exit 0);
- `/private/tmp/m20-native-session-v2-freeze-b19fad-01/freeze-report.json`.

The freeze report preserves exact archived executed source versions. The runner
differs from the final candidate only by a type-ignore comment. The earlier
core test file differs only in an unrelated guard test's corrected v2 agent
path; its core test is unchanged. README received a subsequent documentation-only
correction, so its earlier hash in the historical freeze report remains intact.
The final README hash above is the reviewed delivery version.

## Preserved failures and independent review

The first core attempt exceeded its unchanged 45-second offline child cap
at Q3 preparation. Its empty child output and already-created PREPARED artifact
do not establish a permanent SDK deadlock. One separately bounded lifecycle
diagnostic exited successfully; one authorized retry under the original cap
then passed. Both earlier records remain under
`/private/tmp/m20-native-session-v2-core-58160e5-01` and
`/private/tmp/m20-native-session-v2-q3-lifecycle-b19fad-01`.

The first counterexample group failed because its fixture still hardcoded the
v1 agent path. That ordinary test defect was corrected to derive the v2 path;
the subsequent four-case group passed. The original failure remains at
`/private/tmp/m20-native-session-v2-counterexamples-b19fad-01`.

Independent standards review found an ambiguous README paragraph: the preserved
base runner's all-five-read failure rule was not explicitly scoped away from
v2. The documentation now names the base runner and states v2 separately.
The reviewer approved all three final hashes after that correction.

The separate specification reviewer inspected the actual twelve core artifacts,
fresh-process test implementation, unique complete tool pairs, Q5 source change,
and archived-source diffs. It found no blocking specification defect and approved
the limited offline mechanism. The primary additionally inspected the retained
counterexample outputs: invalid versions, failed predecessor and pre/post-restore
drift stopped with zero SDK/model invocations; the original partial-stream failure
retained its one SDK invocation and two model requests. No tests were repeated
solely for the type comment or README correction.

No paid v2 sequence has run at this review stage. A later paid gate must use
new private roots, freshly prepared shared inputs, unchanged literal D4
questions, separate actual histories and the already frozen limits and stop
rules. The earlier paid v1 failures remain failures. Even six successful real
turns would not close repeated complex-case, HTTP/UI, long-chat or ERP-effect
acceptance.
