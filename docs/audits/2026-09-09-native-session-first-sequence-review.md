# Native session: first real-model sequence

Both candidates stopped under the frozen all-five-source-read rule. Neither
completed six turns or qualifies for product promotion. This is a measured
experiment result, not an F03, HTTP/UI, approval-state or billing acceptance.

Execution used Strands1.53.0, native SnapshotSessionManager/LocalFileStorage,
NullConversationManager, Nova Pro, and the existing authorized Demo profile.
The original six literal D4 questions and source-version schedule were retained.
One production-prepared source bundle per question was shared between candidates;
their native histories and private session roots were separate. Each invocation
ran in a fresh OS process. No summary, answer repair or new IAM policy was used.

| Candidate / turn | Current tools | Observed answer | Frozen result |
| --- | --- | --- | --- |
| N1 Q1 | All five | Correct quantity1 and MAT-SLE-2026-00026; omitted explicit Box unit | STRUCTURAL_COMPLETE; unit-expression deficiency retained |
| N1 Q2 | None | Correctly acknowledged the user's read-only instruction | STRUCTURAL_FAIL; Q3–6 NOT_REACHED |
| N2 Q1 | ERP only | Correct quantity1 and current ledger ID; omitted Box; citations contained a tool path | STRUCTURAL_FAIL; Q2–6 NOT_REACHED |

N1 Q2's restored history exactly equaled Q1's actual history after the first
invocation: four messages restored, six after Q2. This demonstrates one actual
restart with real model history. It does not establish six-turn continuity,
Q4 reasoning, Q5 source refresh, or Q6 refusal/last-answer recall. N2 never
reached an actual restart. The final structured object, rather than intermediate
model text, is the N2 answer under review.

The three reached invocations used five logical model requests,18,306 input
tokens and523 output tokens; ledger-estimated cost was USD0.0163184. Each had
its own USD0.16/16-request/90-second invocation and120-second process limits.
The pair ceiling was USD1.92. No budget or runtime failure occurred. All15
frozen code/source/fixture files matched after execution. No ERP write occurred.

Private evidence is retained outside pytest cleanup under
`/private/tmp/m20-native-session-live-ecb4e34-01/`: before/after manifests, six
prepared inputs, three raw results, per-process execution records, and explicit
primary reviews with NOT_REACHED positions. Raw session/model/source content is
not published. Exact execution revision was
`ecb4e349d050a7cf531f7e74ea5a49ea521e387f`; runner SHA256 was
`e1a70fb44eeaf3bf964b01e964585b7765ff585c6afe03c1eea87045568c9d85`.

## Offline evidence and retention limitation

Before paid execution, four frozen offline tests passed, covering two complete
six-process native sequences, case/variant isolation, pre/post-restore drift,
and failure snapshots. The primary inspected twelve core results and the four
expected failure records. The independent reviewer verified static corrections,
the terminal outcome and all six real prepared bundles, and approved the limited
paid gate. It did not independently reread every core record.

The default pytest directory was subsequently removed by pytest's rotating
cleanup. Its terminal-result record survives; its original full raw tree does
not. An unchanged-code rerun with a dedicated private `--basetemp` was authorized
solely to restore retained offline evidence. Its raw tree now survives under
`/private/tmp/m20-native-session-offline-raw-ecb4e34-02/pytest-base`.
Static post-run validation checked all twelve core records, ordered tool pairs,
continuity and the expected counterexample failures. Its stdout contains all
four passing test indicators and stderr is empty, but the surrounding zsh
wrapper failed afterward by assigning its reserved `status` variable. Wrapper
exit was1; pytest's numeric exit was not separately captured. This is a retained
raw/structural observation, distinct from the first run's recorded exit0. No
third run was performed. The private post-run-validation record states these
limits explicitly.

Ruff formatting/checks and Python compilation passed. An attempted broad mypy
run included legacy/imported errors; the narrow strict dynamic-import check also
reported14 typing/export/annotation errors in experiment files. It is not a
passing type check and is separate from the passing product billing checks.
The exact tested and paid runner/tests/README are also retained in the paid
root's `frozen-code` directory before any subsequent annotation-only cleanup.

Luna subsequently corrected only annotations/casts and test imports of the same
underlying helpers/constants. Independent diff review confirmed that prompt,
schema, tools, session and runtime gate did not change. Primary formatting,
Ruff, compilation and the exact scoped mypy command now pass on both files:
`MYPYPATH=src .venv/bin/python -m mypy --follow-imports=skip --ignore-missing-imports`
followed by the two experiment paths. This does not turn the earlier broad
typing check or either paid semantic result into a pass. Post-cleanup runner
SHA256 is `d3ac8b4aa54697d2f1b454bba6901ce55c66caf37d8b598644fc10f211bb184f`;
test SHA256 is `4cfa486e8495fa3f1cabcd7f4239e2e0edfe7e95ffbf250ce26ac1eada622886`.

## Interpretation and next design

The frozen rule is overly broad for a pure instruction acknowledgement: N1 Q2
required no new external factual claim. N2 Q1's ERP retrieval also answered the
specific question, although its structured citations remain deficient. These
observations do not retroactively change either failed result. They require a
separately reviewed evaluation design that checks necessary current evidence,
faithfulness, permission retention and valid record citations independently.
No new run, winner or product promotion is authorized by this audit alone.
