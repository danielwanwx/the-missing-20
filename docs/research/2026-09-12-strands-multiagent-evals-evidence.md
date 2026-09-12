# Strands multi-agent and evaluation evidence for the final hackathon decision

**Checked:** 2026-09-12 (America/Los_Angeles)

**Scope:** official Strands and Devpost sources plus read-only inspection of this checkout and its two local virtual environments. No package install, model invocation, ERP call, or external write was performed.

## Decision

Do not add a Swarm, Graph, or evaluation badge merely to increase the visible Strands feature count. The current `/operations` implementation contains a historically verified real single-agent Strands conversation and a separate one-turn Strands plan selector. The latest September 12 runtime audit, however, recorded an `AccessDenied` failure for the selected Bedrock model and no new successful answer; this research did not invoke it. When it runs, the model sees an application-built snapshot that includes precomputed fulfillment facts and, when present, the feasible allocation plan. Its tools return copied payloads already loaded into memory, and the same complete payload is embedded in the current-turn user message. A tool-call trace therefore demonstrates a real Strands loop over application-qualified data; it does **not** demonstrate that the agent independently fetched external systems or that its tool calls were necessary to reach the answer.

The smallest defensible multi-agent addition is an isolated, read-only paired experiment: one single-agent investigator versus a fixed two-specialist Graph on the same held-out source snapshots, with all source facts available only through tools, an equal total model budget, external answer keys, and domain plus trajectory scoring. Promote the Graph into `/operations` only if it fixes a measured cross-source failure at acceptable cost and latency. A Swarm is a worse fit for this test because autonomous handoffs add a variable that the product does not need; the workflow has two known independent evidence questions and one guarded join.

This work can improve the official **Technical Implementation** score only if the implementation is working and non-trivial, and it can help **Potential Impact** only if the measured behavior addresses a real operator failure. The same rubric also gives equal attention to complete product design, originality, and clear end-to-end presentation; framework breadth alone does not satisfy those criteria. The verified submission deadline is **Monday, September 14, 2026 at 5:00 p.m. Pacific Time**. [Official rules](https://agentsforhumans.devpost.com/rules) · [official overview and judging criteria](https://agentsforhumans.devpost.com/)

## What is installed and what is only documented

| Item | Local evidence | Meaning |
|---|---|---|
| Main `.venv` | `strands-agents==1.53.0`; import of `strands.multiagent` exposes `GraphBuilder` and `Swarm` | Core native Graph/Swarm APIs are available without another package. `uv.lock` also pins 1.53.0. |
| `.agentcore-venv` | `strands-agents==1.54.0` | This second environment is not evidence that the main application runs 1.54.0. |
| `strands-agents-tools` | Not installed in either inspected Strands listing | The Python-only dynamic `strands_tools.graph` tool shown in the Graph guide is unavailable locally. It is not needed for a statically built `GraphBuilder` experiment. |
| `strands-agents-evals` / `strands_evals` | **Not installed** in the main `.venv`; metadata lookup fails and `import strands_evals` raises `ModuleNotFoundError` | Official Evals documentation describes available software, not current project behavior. No current artifact should be called a Strands Evals result. |
| Project dependency contract | `pyproject.toml` requires `strands-agents>=1.53.0,<2`; it does not declare Strands Evals or Strands tools | Adding Evals would be a dependency change and still needs an isolated compatibility check. |

PyPI currently lists `strands-agents` **1.55.1** (released 2026-09-09) and `strands-agents-evals` **1.2.0** (released 2026-08-21). The official docs are rolling documentation and may describe behavior newer than the locked 1.53.0 runtime. The relevant agents-as-tools delegation feature did arrive in 1.53.0, but any implementation must be checked against installed signatures and behavior rather than copied blindly from current docs. [Agents package](https://pypi.org/project/strands-agents/) · [Evals package](https://pypi.org/project/strands-agents-evals/)

## Current implementation truth

1. `scripts/decision_workspace_server.py::_distributor_native_packet` builds a compact `distributor_operations` packet from the already-materialized projection. It includes quantities, computed fulfillment facts, documents, shipments, retained events and handoffs. It also inserts `feasible_contract_allocation_plan` when the application has one.
2. `src/the_missing_20/adapters/native_receiving_dialogue.py::_source_tools` builds real Strands tools, but each tool returns a deep copy of a payload captured before invocation and discards its natural-language query. `_current_source_message` also serializes the complete payload set into the user message. These are qualified snapshot readers, not independent live SaaS/ERP queries.
3. The native dialogue uses `SnapshotSessionManager` and restores real conversation history. It is deliberately read-only and says not to execute operations. This is meaningful session continuity, but it is a single-agent session rather than multi-agent durability.
4. `src/the_missing_20/agents/distributor_allocation.py::select_contract_plan` is a separate bounded, structured Strands turn. The application compiles the candidate quantities; the model may return the supplied plan ID or `DEFER`; deterministic validation in `DistributorOperations` rejects a mismatched ID, invalid rationale, or incorrect contract references. The model is a constrained selector, not the allocation calculator.
5. `src/the_missing_20/agents/role_delegation.py` is genuine older multi-agent work: a coordinator exposes `consult_receiving`, `consult_inventory`, and `consult_quality`; each consultation creates its own source-scoped Strands `Agent`, persists a fenced task record, and validates literal observations against admitted evidence. However, it is an application-owned agents-as-tools harness, not `Graph` or `Swarm`. It is enabled by `MISSING20_AGENT_WORKFLOW=roles` only in the broader Dashboard advisory path, and that path requires `source_investigation` evidence. The current native distributor `/operations` ask route and its allocation selector are wired separately. Do not present the old role harness as the current `/operations` architecture.

## Official capabilities that matter

- **Graph:** native Python `GraphBuilder` constructs a deterministic directed workflow of agents, custom nodes, or nested orchestrators. It supports conditional edges, shared state, cycles, and execution/node limits. This is the right native shape when the experiment should always run two known evidence partitions before one join. Python scheduling details matter: current docs describe incoming-edge OR semantics and state accumulation unless revisit reset is configured. [Graph guide](https://strandsagents.com/docs/user-guide/concepts/multi-agent/graph/)
- **Swarm:** agents autonomously hand off through an injected handoff tool and share mutable context, with explicit handoff and iteration limits. This is suitable when the next specialist cannot be fixed in advance. It adds avoidable variance to the proposed two-part reconciliation. [Swarm guide](https://strandsagents.com/docs/user-guide/concepts/multi-agent/swarm/)
- **Agents as tools:** an `Agent` can be passed directly in a parent's tools, customized with `.as_tool()`, or wrapped with `@tool` for full control. Direct passing accepts one string input and returns text; delegated mode can return the specialist result as the parent result and stop the parent loop, with documented constraints. This is closest to the existing role harness, but a model-decided consultation can be skipped and is less controlled for an ablation. [Agents as tools](https://strandsagents.com/docs/user-guide/concepts/multi-agent/agents-as-tools/)
- **Interrupts:** Graph and Swarm can interrupt before a node or inside a node and resume from interrupt response content. This is useful for later approval-bearing workflows; it is unnecessary in the proposed read-only quality experiment. [Interrupts](https://strandsagents.com/docs/user-guide/concepts/interrupts/)
- **Durability:** sessions can restore messages, agent state, conversation manager state, interrupt/model state, and multi-agent execution state. For Python Graph/Swarm, current docs say to use a repository-based session manager on the orchestrator; `SnapshotSessionManager` does not support Graph/Swarm, and child agents must not have their own session managers. Persistence does not itself make side effects exactly once, so any future action node still needs application idempotency and readback. [Session management](https://strandsagents.com/docs/user-guide/concepts/agents/session-management/)

## Minimum fair experiment: single investigator versus two specialists

### Hypothesis

For cross-system cases where ERP quantities, integration acknowledgements, quality state, and operator events can disagree, two independently scoped specialists plus a coordinator reduce unsupported causal claims and missed contradictions compared with one agent, without exceeding a frozen system-level token/cost cap.

### Frozen variants

| Control | Single-agent baseline | Two-specialist candidate |
|---|---|---|
| Input | Same newest operator question and same immutable, versioned source snapshot | Identical question and snapshot |
| Source exposure | Source facts only through the five read tools; remove the full JSON snapshot from the prompt for this experiment | Specialist A owns receiving/quality: ERP receipt and lot records, quality evidence, and physical observations. Specialist B owns customer fulfillment: sales orders/contracts, existing reservations, and relevant integration/collaboration evidence. Partition by business responsibility; intentional overlap is allowed but must be declared and measured. The union equals the baseline's access. |
| Reasoning | One Strands agent reads and returns the typed answer | Static Graph: two specialist nodes run independently; an application-owned join proceeds only when both required typed results exist, carry the identical case/snapshot identity, and pass source/observation validation. The coordinator then sees only those validated observations and returns the same typed answer schema. |
| Model/config | Same provider model, inference settings, prompt policy, and no prior session memory | Same provider model/settings for all three calls and no prior session memory |
| Budget | One fixed system-level token and dollar cap | Split the identical total cap across A, B, and coordinator; record per-node and total usage |
| Authority | Read-only; no execution tools | Read-only; no execution tools or approval inference |

Do not include `feasible_contract_allocation_plan`, a retained model decision, expected verdict, rubric, or evaluator explanation in either model input. Application-computed raw quantities and explicit candidate choices may be included when arithmetic is outside the intended reasoning task. Ground truth stays in a separate held-out manifest.

Freeze twelve case families before running: four development cases for wiring and rubric repair, then eight untouched scored cases spanning lost acknowledgement versus true absence, partial receipt, quality hold versus proven defect, stale collaboration state, two-order allocation pressure, completed/simple cases where delegation should add no value, missing evidence, and one adversarial causal-attribution request. Run each of the eight scored cases twice per variant in alternating order: **32 real workflow runs**. Development runs do not enter the score. This is still a small engineering pilot: it can choose a deadline candidate but cannot establish production accuracy, statistical significance, or a stable population-level advantage. Fewer runs reduce coverage further; they do not create the pilot boundary by themselves.

### Scores and stop rule

Use deterministic, domain-owned assertions where the expected result is mechanically computable: exact quantities and state codes, cited record-ID membership and scope, case/snapshot identity, required specialist-result presence, prohibited tool use, and zero write/approval values in structured action fields. Use blinded semantic review for contradiction recognition, whether uncertainty is appropriate, unsupported causal attribution, directness, whether an answer or defer decision is justified, and any free-form wording that implies an action completed or approval existed. Calibrate any LLM judge against human labels and retain disagreements. The answer key, scorer, and review rubric must not appear in prompts.

Trajectory scores should answer narrower questions: were required sources actually called, did the specialist stay inside its source partition, were prohibited tools absent, and did the final answer follow validated observations? The existing readers discard `query`, so tool-parameter accuracy is not informative until parameters affect retrieval. Likewise, because the current prompt embeds every source, `ToolCalled` is not evidence of necessary retrieval unless the experiment removes that duplicate channel.

Record end-to-end latency, total input/output/cached tokens, estimated cost, model/provider IDs, tool sequence, per-node failure, and answer score. Promotion requires a predeclared material accuracy improvement on the difficult subset, no regression on simple cases, zero authority/write violations, and acceptable latency/cost for the recorded demo. If the two-specialist candidate merely calls more models, produces the same answer, or wins only when given more total tokens, reject it and keep the single agent.

## How Strands Evals could be used, without overstating it

The official Evals SDK supports output, trace, tool, and session-oriented evaluation; deterministic evaluators such as equality/containment/tool-called/state checks; LLM judges; simulations; and custom evaluators. Its quickstart installs a separate `strands-agents-evals` package and exposes the `strands-evals` CLI. [Evals quickstart](https://strandsagents.com/docs/user-guide/evals-sdk/quickstart/)

For this experiment:

- Use a custom deterministic evaluator for domain invariants and citation closure. This remains the promotion gate because generic language judges cannot establish ERP truth.
- Use `TrajectoryEvaluator` only for the declared action/tool sequence and with a task-specific rubric. Official guidance describes it as an LLM-as-judge evaluator and provides exact, in-order, and any-order scoring helpers; its score is advisory and incurs a judge-model call. [Trajectory evaluator](https://strandsagents.com/docs/user-guide/evals-sdk/evaluators/trajectory_evaluator/)
- Use tool selection evaluation only if a test actually allows the agent to choose among useful and irrelevant tools. The official evaluator judges each tool call independently; trace/session identifiers must keep spans from different cases separate. Map each trace to the specific actor and that actor's permitted tool set before scoring, rather than treating the union of every agent's tools as every actor's choices. Fixed Graph fan-out should instead use deterministic source-coverage assertions. [Tool selection evaluator](https://strandsagents.com/docs/user-guide/evals-sdk/evaluators/tool_selection_evaluator/)

### Real and offline boundaries

| Claim | What would substantiate it | What would not |
|---|---|---|
| Real multi-agent run | Each specialist and coordinator actually invokes the configured provider through Strands on a frozen case | A scripted model, mocked response, static role labels, or replayed JSON |
| Real external retrieval | A tool queries the named external system during that invocation and records source identity/version/read status | Calling a tool that returns a payload captured before the invocation; embedding that same payload in the prompt |
| Offline trajectory evaluation | Stored agent traces are mapped and scored without rerunning the agent | Calling it a fresh agent benchmark |
| LLM-judge evaluation | A separate evaluator model scores stored output/trajectory | Treating the judge result as independent business truth or as a rerun of the agent |
| Real ERP outcome | After an authorized action, authoritative ERP records are read back and exact effects are verified | This read-only experiment, a proposed plan, tool-call success, or an evaluator score |
| Durable multi-agent recovery | A Graph/Swarm session is interrupted or process-killed and resumes from orchestrator persistence under the documented manager constraints | The current single-agent `SnapshotSessionManager`, or the older role-task journal alone |

## Source status and confidence

All twelve URLs below were opened or searched on 2026-09-12. Devpost is authoritative for this competition. Strands documentation and PyPI project pages are first-party/maintainer-controlled primary sources, but the docs are rolling and can lead the project's locked runtime. Local installed metadata and source are authoritative for what this checkout can import today.

1. [Devpost official rules and deadline](https://agentsforhumans.devpost.com/rules)
2. [Devpost requirements and judging criteria](https://agentsforhumans.devpost.com/)
3. [PyPI: strands-agents](https://pypi.org/project/strands-agents/)
4. [PyPI: strands-agents-evals](https://pypi.org/project/strands-agents-evals/)
5. [Strands Graph guide](https://strandsagents.com/docs/user-guide/concepts/multi-agent/graph/)
6. [Strands Swarm guide](https://strandsagents.com/docs/user-guide/concepts/multi-agent/swarm/)
7. [Strands agents-as-tools guide](https://strandsagents.com/docs/user-guide/concepts/multi-agent/agents-as-tools/)
8. [Strands session management](https://strandsagents.com/docs/user-guide/concepts/agents/session-management/)
9. [Strands interrupts](https://strandsagents.com/docs/user-guide/concepts/interrupts/)
10. [Strands Evals quickstart](https://strandsagents.com/docs/user-guide/evals-sdk/quickstart/)
11. [Strands trajectory evaluator](https://strandsagents.com/docs/user-guide/evals-sdk/evaluators/trajectory_evaluator/)
12. [Strands tool-selection evaluator](https://strandsagents.com/docs/user-guide/evals-sdk/evaluators/tool_selection_evaluator/)
