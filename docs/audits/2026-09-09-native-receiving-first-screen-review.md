# Native receiving first screen: useful boundary result, incomplete acceptance

Independent verdict: both candidates correctly deny that the frozen receiving
records independently prove carton contents. Neither fully passes Q4: N1 lacks
actual record citations; N2 cites a tool name and its final structured answer
lacks a supporting explanation. Keep both as candidates for a separately frozen
six-turn evaluation. No winner, product integration or finalization pass follows.

The actual run used existing Nova Pro and Strands1.53.0, one native invocation
per candidate, the same human context and five qualified source payloads. No
application repair, critic, generated summary, ERP call or IAM change occurred.

| Observed result | N1 natural output | N2 answer/citations schema |
| --- | --- | --- |
| Logical model requests | 2 | 2 |
| Input / output tokens | 7,117 / 278 | 7,482 / 256 |
| Cost USD | 0.0065832 | 0.0068048 |
| Elapsed seconds | 3.664 | 2.974 |
| Source tools read | all 5 | all 5 |
| Native format fallback / schema-error-history turns | 0 / 0 | 0 / 0 |

Total actual cost was USD0.013388 against the frozen USD0.32 pair cap. These
are single observations, not reliable latency estimates or a causal comparison
with the historical custom-pipeline D4 failure. The candidates also simplify
the answering task boundary; this run cannot isolate which removed component
explains the difference. The core physical-evidence failure is improved in this
sample, while citations, explanation and multi-turn reliability remain open.

## Verification and preserved corrections

Primary and independent reviewer each passed the final seven offline tests.
Formatter, Ruff and scoped mypy passed; the latter follows imports as skipped
and allows subclassing Any because of unavailable Strands stubs. This is not the
product's strict/full regression. Tests exercise the native loop, all-source
coverage, forced formatting and invalid schema, answer exclusion, immutable
output reservation, altered-input rejection and partial-failure evidence.

Pre-freeze review corrected top-level invocation/model-request terminology,
missing code/model/tool-schema manifest fields, partial SDK event loss on an
exception, and Pydantic output serialization. All-source completion is explicit
in the common generic instruction. No paid call used the earlier version.
Independent review then reproduced one invalid schema response appearing in two
later request histories. The field is now honestly named
`request_turns_containing_schema_error_history`; the counterexample is retained
in tests and private review evidence. The semantic prompt/schema did not change
between freeze01 and freeze02.

The original reconstruction generates five `observed_at` values. Both candidates
therefore consume one frozen private bundle. Independent reconstruction verified
the same question and all facts, with only those timestamps differing. The final
02 bundle preserves the complete 01 input, including timestamps. Its compact
canonical input SHA256 is
`6bdf1840a4ebd80259eee492d85409a087ad34da125d04c0cde97fea0230605e`.
The source files, code and configuration were checked before model construction;
the execution audit confirms all tracked experiment inputs remained unchanged.
Earlier frozen artifacts remain preserved and explicitly superseded.

Reviewed runner SHA256:
`31554348a7775553bcd13b961bbe85187db4bec0078cbe3b0fcbaf299a972114`.
Reviewed tests SHA256:
`0f408310296a0ed4c819459bac6c701bfdf91b4e203ca636cd4dacd86537c711`.
Execution revision: `be226623628161e36d6c098d5e68a6b471907b8a` plus those
frozen isolated experiment files. Private raw results and before/after hashes:
`/private/tmp/m20-native-receiving-live-be226623-01/`.
The [public summary](../../artifacts/audits/2026-09-09-native-receiving-first-screen-summary.json)
contains measurements and acceptance limits, not private source payloads or
intermediate model text. Concatenated diagnostic `natural_text` must not be
displayed as a product final answer; final-answer extraction should use the
native result boundary in any later integration.

The six-turn source-change/restart sequence, broader core and held-out repeats,
and same-order downstream effects remain unaccepted. This result does not close
F03 or F05. No extra Q4 retry or question-specific citation/answer repair is
authorized by this review record.
