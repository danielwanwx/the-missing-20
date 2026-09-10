# Native conversation: evidence and evaluation selection

Research checked September 9, 2026. Select the installed native Strands tool
loop and session storage for a new, separately frozen comparison. Evaluate
claims, current evidence and conversation goals independently of tool count.
No runtime router, self-critic, dependency installation or paid run is selected.

N1 Q2 and N2 Q1 remain **FAILED under their original frozen rule**, with later
positions NOT_REACHED. N1's correct read-only acknowledgement does not change
that result; N2's correct ERP quantity does not repair its tool-path citation
or missing Box expression. The [first-sequence audit](../audits/2026-09-09-native-session-first-sequence-review.md)
and [alternative selection](2026-09-09-research-led-alternative-selection.md)
remain the historical record. This note proposes evaluation requirements, not
a winner, resumed failed session, product promotion or new execution approval.

## What the existing components support

| Component | Verified behavior | Fit and limit |
| --- | --- | --- |
| Strands Agents 1.53.0 native Agent/tools | Installed `strands/models/bedrock.py:342` defaults tool choice to `auto`; AWS explicitly permits text instead of a tool call. [AWS API](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_AutoToolChoice.html), [Strands tools](https://strandsagents.com/docs/user-guide/concepts/tools/) | Keep the same available read tools; let the model select relevant ones. Selection is an opportunity to retrieve evidence, not proof that the answer is complete or correct. |
| Native SnapshotSessionManager + LocalFileStorage + NullConversationManager | Already selected in the retained experiment for actual history across fresh processes. [Sessions](https://strandsagents.com/docs/user-guide/concepts/agents/session-management/), [conversation management](https://strandsagents.com/docs/user-guide/concepts/agents/conversation-management/) | Preserve this bounded continuity baseline. Persistence does not refresh external truth or validate answers; full history consumes context and input tokens. |
| Native structured output | Validates a Pydantic response shape and exposes `AgentResult.structured_output`. [Documentation](https://strandsagents.com/docs/user-guide/concepts/agents/structured-output/) | Keep format as an independent candidate dimension. A string in `citations` can still be a tool path or invented ID; schema success is not evidence validity. Evaluate the actual final structured answer. |
| Evals OutputEvaluator / FaithfulnessEvaluator | Output supports a task-specific rubric without OTel; Faithfulness examines the latest response against preceding conversation. [Output](https://strandsagents.com/docs/user-guide/evals-sdk/evaluators/output_evaluator/), [faithfulness](https://strandsagents.com/docs/user-guide/evals-sdk/evaluators/faithfulness_evaluator/) | Output can judge an acknowledgement even with zero tools. Faithfulness can diagnose unsupported claims but cannot establish current truth absent from the supplied context. |
| Evals GoalSuccessRateEvaluator | Version 1.2.0 supports whole-session evaluation and explicit human-authored `expected_assertion`, rather than only inferred goals. [Tagged source](https://raw.githubusercontent.com/strands-agents/evals/v1.2.0/src/strands_evals/evaluators/goal_success_rate_evaluator.py) | Suitable later for read-only constraint retention, source refresh and faithful last-answer recall across six turns. A judge remains fallible and cannot replace exact source checks. |
| Evals ToolSelectionAccuracyEvaluator / TrajectoryEvaluator | Tool selection scores actual calls in context; trajectory evaluates the action sequence. [Tool selection](https://strandsagents.com/docs/user-guide/evals-sdk/evaluators/tool_selection_evaluator/), [trajectory](https://strandsagents.com/docs/user-guide/evals-sdk/evaluators/trajectory_evaluator/) | Useful diagnostic dimensions after outcome evidence is checked. Neither maximizing call count nor matching one exact sequence establishes task success. |

The tool-selection documentation lists missing-call detection, but also says
there is one evaluation per actual call and that no calls can produce no
results. Therefore an empty list cannot establish correct abstention or absence
of missing reads. Evals 1.2.0's base default aggregator maps empty results to
`(0.0, False, "No evaluation outputs produced")`; that is an evaluation-coverage
result, not a semantic verdict on an acknowledgement. Preserve missing telemetry,
no applicable calls and failed output as distinct observations.
[Documentation](https://strandsagents.com/docs/user-guide/evals-sdk/evaluators/tool_selection_evaluator/),
[tagged aggregator](https://raw.githubusercontent.com/strands-agents/evals/v1.2.0/src/strands_evals/evaluators/evaluator.py).

The upstream [tool-efficiency proposal #345](https://github.com/strands-agents/evals/issues/345)
is open, not an installed evaluator. Its proposed perfect efficiency score for
zero calls would still say nothing about answer correctness. Do not adopt that
proposal as a success gate. Berkeley's [BFCL V2 relevance/irrelevance distinction](https://gorilla.cs.berkeley.edu/blogs/12_bfcl_v2_live.html)
and [V3 per-turn response/state checks](https://gorilla.cs.berkeley.edu/blogs/13_bfcl_v3_multi_turn.html)
are useful evaluation precedents, not ERP evidence or a component to install.

## Proposed evidence contract — evaluator side only

These are prospective review rules, not a production question classifier.
Freeze expectations outside agent inputs before any new run. Review both the
user's request and every claim the answer actually adds; a turn cannot obtain
an acknowledgement exemption while asserting fresh business facts.

| Answer content | Required evidence and outcome |
| --- | --- |
| Pure acknowledgement of a read-only instruction | Zero source calls and empty citations may be appropriate. The answer must preserve the instruction, introduce no fresh external factual claim, and neither perform nor claim a mutation. Continue testing retention on later turns. |
| Current ERP quantity or posting claim | Relevant successful current-version ERP read, actual returned record IDs bound to the correct case/item, and exact quantity plus UOM. A plausible remembered ID, tool name, endpoint or schema field is not a record citation. |
| Physical receiving or cross-source explanation | Relevant authoritative receiving evidence and any additional sources necessary for the specific inference. ERP posting alone cannot prove a physical count; citations must support the relationship actually asserted. |
| Refreshed answer after source change | Newly observed relevant records from the scheduled source version; superseded values must not be presented as current. Merely retaining an old faithful answer fails current-evidence evaluation. |
| Recall of the assistant's last answer or prior instruction | Actual preserved assistant/user history. New reads need not be required for explicitly historical recall; distinguish the historical statement from a claim about present source state. |
| Source unavailable or insufficient | Accurately disclose the gap and withhold unsupported conclusions. Calling all tools, obtaining errors, or citing an unrelated successful record cannot satisfy the missing evidence. |

For each factual assertion, the future frozen review should retain the source
version, scope, successful tool result and cited record/field that supports it.
Check quantities and units together; do not silently equate Box and another
UOM or accept an unverified conversion. Compare the complete final answer,
including structured citations, against those facts. Also check needed claims
that the answer omitted; an answer can be faithful to a subset and incomplete.

Required counterexamples include a correct-looking answer with no relevant
read, stale or invented record ID, tool-path citation, wrong or absent UOM,
ERP-posted quantity presented as physical proof, and a false "I checked" claim
inside an apparent acknowledgement. Include valid zero-read acknowledgements
and historical recalls so an all-tools rule cannot pass by over-fetching.
These are domain-specific test expectations, not guarantees supplied by Evals.

## Smallest suitable adoption and its cost

For the next bounded comparison, retain installed Strands 1.53.0, native
snapshots, the same read interfaces and the existing retained result artifacts.
Replace the unconditional five-source *evaluation* gate only in the newly
reviewed experiment. Use explicit outcome/evidence assertions plus independent
semantic review; keep source selection with the native model. No extra SDK is
needed to conduct this comparison, and no judge should repair the candidate's
answer, request more tools for it or rewrite its history.

If repeated evaluation later warrants automation, isolate Evals **1.2.0** and
first use OutputEvaluator with frozen reference facts/rubrics; add assertion-mode
GoalSuccessRateEvaluator for whole-session review. Faithfulness and tool/trajectory
judges are optional diagnostics, not substitutes for either. Keep deterministic
record, version and quantity/UOM checks and independent review authoritative.
The [1.2.0 exports](https://raw.githubusercontent.com/strands-agents/evals/v1.2.0/src/strands_evals/evaluators/__init__.py)
also include Equals, Contains, ToolCalled and StateEquals, but simple membership
checks do not establish that a citation entails an answer's claim.

Strands 1.53.0's installed metadata reports Apache-2.0 and Python >=3.10.
Evals 1.2.0 is Apache-2.0, Python >=3.10, and requires Strands >=1.42.0,
`strands-agents-tools>=0.1.0,<1.0.0`, OTel, Rich, Tenacity and other dependencies.
Version constraints admit 1.53.0; runtime integration remains untested here.
[Tagged package contract](https://raw.githubusercontent.com/strands-agents/evals/v1.2.0/pyproject.toml).

There is no new commercial SDK license or service subscription selected.
Native inference still consumes provider tokens and source I/O. Evals judges
invoke models; per-call judging grows with tool count, and whole-session judging
reads the accumulated conversation. Price depends on the explicitly selected
model, tokens and retries; no dollar estimate or approved judge model is assumed.
Do not rely on a default model. Freeze separate judge and candidate budgets.
Trace-based evaluators additionally need complete OTel history and unique session
attributes; persisted SDK snapshots alone are not Evals `Session` trajectories.
Fresh-process traces must preserve identity and actual final N2 output without
mixing candidates. Judge error/overflow or absent coverage is not candidate success.

## Collection and limits

This follow-up read the retained audits, installed 1.53.0 source/metadata,
official documentation and available tagged Evals source. It did not execute
Evals. Some tagged files were unavailable through web retrieval; their behavior
is described from current official docs, not claimed as a local reproduction.
The earlier Research Engine run's limitations remain documented in alternative
selection; no new Engine/model run was made under this task's no-paid-call scope.
Direct primary-source retrieval is not Engine-validated evidence. No source
payload, failed outcome, dependency, product code, test or ERP state was changed.
