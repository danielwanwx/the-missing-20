# Milestone 4: Strands Multi-Agent Investigation and Golden v2

**Status:** User-approved; pre-implementation compatibility gate pending  
**Date:** 2026-08-26  
**Parent design:** [`2026-08-25-the-missing-20-design.md`](2026-08-25-the-missing-20-design.md)  
**Accepted safety foundation:** [`2026-08-25-milestone-3-golden-v1-design.md`](2026-08-25-milestone-3-golden-v1-design.md)

## 1. Decision

Milestone 4 replaces the deterministic diagnosis stub with a real Strands Agents harness while preserving every deterministic safety boundary accepted in Golden v1.

Three specialized Strands agents investigate the same admitted case evidence in parallel. A fourth Strands agent synthesizes their structured findings. A fifth, independently prompted Strands agent evaluates the proposed conclusion against a separately assembled evidence view. Deterministic validators then decide whether the structured outputs are admissible. Only a validated `InvestigationAssessment` may enter the existing case ledger.

The default real-model proof uses a locally hosted Ollama model and makes no paid model or AWS call. Offline CI uses a scripted Strands model provider that exercises the actual Strands agent loop, tools, structured-output boundary, harness, and validators without network access. Amazon Bedrock and AgentCore remain explicit Milestone 6 proof paths.

## 2. User-visible outcome

After this milestone the main case runs as follows:

```text
Physical receipt 100 / ERP receipt 80 / invoice 100
  -> deterministic detector admits current-state evidence
  -> three Strands investigators run concurrently
       retryable-message investigator
       short-shipment investigator
       duplicate-posting investigator
  -> each investigator calls only allowlisted read tools
  -> deterministic citation gate rejects unsupported claims
  -> Strands synthesis preserves support, contradiction, and uncertainty
  -> independent Strands evaluator checks evidence coverage and safe next action
  -> deterministic assessment validator accepts or stops the loop
  -> existing human approval, authorization, execution, and verification path
  -> CLOSED
```

The retryable-lock profile does not stop at diagnosis. It must persist the Strands-derived assessment through `CaseService`, then use the existing real Integration Operator approval, signed authorization, executor, authoritative verification, AP approval, invoice execution, and closure path until the reopened SQLite projection is `CLOSED`.

The same harness must also persist `PROTECTED` for a genuine short shipment, `NEEDS_EVIDENCE` when a required source is unavailable, and `RECEIPT_ALREADY_POSTED` when exact authoritative history proves the receipt already completed. These safety profiles must prove zero forbidden grants and business effects after reopening and replaying the case store.

## 3. Boundaries and non-goals

### In scope

- Strands Agents SDK as the real agent runtime.
- Three concurrent read-only investigators.
- One structured synthesis agent.
- One independently assembled evaluator agent.
- Strict structured outputs and deterministic evidence validation.
- Versioned synthetic knowledge retrieval.
- Normalized execution traces and Strands metrics without chain of thought.
- Offline scripted-provider tests and zero-cost local Ollama verification.
- Golden v2 evidence that composes with all Golden v1 safety results.

### Out of scope

- Approval, signing, policy, executor, database mutation, shell, filesystem, browser, network, or arbitrary MCP tools inside an agent.
- Dynamic Swarm routing or an LLM-created workflow graph.
- AgentCore Runtime, Gateway, Policy, KMS, DynamoDB, Cognito, or Bedrock Knowledge Bases; these remain Milestone 6.
- Prompt self-modification or automatic promotion of model output into a golden dataset.
- Production secrets, employer data, private incidents, private runbooks, or private terminology.
- Any automatic Ollama model download or paid model invocation.

## 4. Chosen orchestration pattern

The harness uses an application-owned static workflow rather than Strands Swarm or a model-generated graph:

```text
asyncio.gather(
  Strands retryable investigator,
  Strands short-shipment investigator,
  Strands duplicate-posting investigator
)
  -> deterministic investigator validation
  -> Strands synthesis
  -> deterministic synthesis validation
  -> Strands evaluator with independent context assembly
  -> deterministic evaluator validation
  -> InvestigationAssessment
```

This still uses real Strands `Agent` instances as the multi-agent units while keeping concurrency, budgets, retries, stop conditions, and stage order inspectable. Strands documents Graph, Swarm, and Workflow as alternative multi-agent patterns; the fixed workflow is selected because this safety-sensitive business process must not let a model invent topology or choose a write-capable participant.

## 5. Agent contracts

All contracts extend the existing strict, frozen Pydantic base and reject unknown fields.

### Investigator output

```text
InvestigatorResult
  investigator_id
  hypothesis_type
  conclusion: SUPPORTED | REJECTED | NEEDS_EVIDENCE
  confidence_band: LOW | MEDIUM | HIGH
  factual_claims[]
    claim_id
    statement
    evidence_ids[]
  supporting_evidence_ids[]
  contradicting_evidence_ids[]
  missing_evidence_sources[]
  knowledge_citations[]
    knowledge_id
    version
    use: PROCEDURE_ONLY | ERROR_DEFINITION_ONLY
  proposed_action: restart_receipt_message | null
```

An investigator cannot output an approval, grant, execution instruction, arbitrary tool name, database command, or `CLOSED` state.

### Synthesis output

```text
SynthesisResult
  selected_hypothesis
  conclusion
  confidence_band
  factual_claims[]
  supporting_evidence_ids[]
  contradicting_evidence_ids[]
  preserved_dissent[]
    hypothesis_type
    conclusion
    evidence_ids[]
  missing_evidence_sources[]
  proposed_action
  synthesis_version
```

Synthesis must include every investigator in `preserved_dissent`, even when rejected. It may not upgrade uncertainty, remove contradicting evidence, or turn knowledge content into a current-state fact.

### Evaluator output

```text
AgentEvaluationResult
  decision: ACCEPT | REJECT | MORE_EVIDENCE
  validated_claim_ids[]
  validated_evidence_ids[]
  failed_invariants[]
  required_evidence_sources[]
  allowed_next_action
  evaluator_version
```

The evaluator cannot authorize or execute the action. Its `allowed_next_action` is only a recommendation input to the existing deterministic `InvestigationAssessment` validator.

## 6. Read-only tool boundary

Agents receive only two project-owned tools:

1. `read_admitted_evidence(evidence_id)`
   - Reads one evidence item already admitted to the current case.
   - Refuses evidence IDs outside the invocation allowlist.
   - Returns typed admitted fields, source type, record ID, observation time, and digest.
   - Never performs a new enterprise mutation or unrestricted database query.

2. `search_synthetic_knowledge(query, version)`
   - Searches only checked-in synthetic SOPs and error definitions.
   - Requires an exact knowledge-corpus version.
   - Returns knowledge IDs, versions, excerpts, and content digests.
   - Labels every result as procedural knowledge, never current-state evidence.

Each investigator receives the minimum tool scope relevant to its hypothesis. Synthesis receives validated investigator results and admitted evidence through deterministic context assembly; it does not inherit investigator tool histories. The evaluator receives a freshly assembled evidence catalog, synthesis result, and invariant checklist; it does not receive hidden chain of thought or mutable agent state.

No agent constructor has access to `AuthorizationService`, `Signer`, `LocalPolicy`, `ControlledExecutor`, `CaseStore`, raw SQLite connections, AWS clients, shell execution, file loading, automatic tool discovery, or community tool packages.

## 7. Knowledge corpus

The local corpus contains synthetic, public-safe material only:

- retryable document-lock definition;
- receipt-message recovery SOP;
- genuine short-shipment decision rule;
- duplicate-posting prevention rule;
- invoice-release prerequisite rule;
- evidence-source glossary.

Each Markdown file has a frontmatter knowledge ID, corpus version, title, allowed use, and SHA-256 content digest recorded in a manifest. Retrieval uses a deterministic local lexical ranker with stable tie-breaking. The ranker is intentionally small; vector retrieval is deferred until the Bedrock Knowledge Bases capability is proven in Milestone 6.

Knowledge may explain what a retryable lock means or what evidence should exist. It cannot prove that the current message is retryable, that the lock cleared, that goods arrived, or that a material document exists.

## 8. Model-provider architecture

The harness depends on a narrow `AgentModelFactory` port and supports two Milestone 4 providers.

### Scripted Strands provider

- Implements the official Strands custom `Model` interface.
- Produces frozen model events that call the real project tools and return strict structured output.
- Exercises the actual Strands agent loop without network or model cost.
- Is the only provider used by `make check` and deterministic Golden v2 regression.
- Is not described as an AI-quality proof or a real generative-model result.

### Ollama provider

- Uses Strands `OllamaModel` against `http://127.0.0.1:11434` by default.
- Freezes `qwen3:14b` as the proposed Milestone 4 model. The official Ollama model is 9.3 GB and advertises tool/agent capability; the current Apple Silicon machine has sufficient memory for this size.
- Does not pull a model or start a paid service automatically.
- Sets temperature to zero where supported and fixes maximum output tokens.
- Is invoked only by `make agent-smoke AGENT_CONFIRM=1`.
- Fails preflight when the server or configured model is unavailable.

Bedrock is not a fallback for a failed Ollama run. A Bedrock invocation requires a separate explicit provider, confirmation flag, account/region preflight, request cap, token cap, and user authorization in Milestone 6.

### Pre-implementation compatibility gate

Before Luna changes product code, the user must explicitly approve the approximately 9.3 GB `qwen3:14b` download. The gate then performs only:

1. start or verify the local Ollama daemon;
2. explicitly pull `qwen3:14b` once;
3. invoke one minimal Strands agent with one audited echo/read tool;
4. require the model to call the tool and return one Pydantic structured output;
5. record model tag, local digest, Ollama version, Strands version, tool call, schema result, latency, and zero-cost provider label in `artifacts/agent/model-compatibility.json`.

If either tool calling or structured output fails, Milestone 4 implementation does not begin. There is no automatic switch to another model, Bedrock, or a scripted-only milestone. One alternative local model may be proposed to the user with its size and evidence; selection remains a human gate.

Official Strands documentation confirms native Python Ollama support, Pydantic structured outputs through `structured_output_model`, custom model providers, tool/function calling, and metrics on `AgentResult`.

## 9. Loop contract and budgets

### Goal

Produce one evidence-grounded, independently evaluated `InvestigationAssessment` without giving any agent mutation authority.

### Input scope

- One case projection and trace ID.
- Evidence IDs already admitted to that case.
- One immutable knowledge-corpus version.
- Frozen prompt, model, harness, and schema versions.

### Execute

1. Assemble hypothesis-specific allowlists.
2. Invoke the three investigators concurrently.
3. Validate every investigator result.
4. Invoke synthesis once with validated results.
5. Validate synthesis and preserved dissent.
6. Invoke evaluator once with independently assembled facts.
7. Validate evaluator and build the existing assessment contract.
8. Persist only the accepted assessment through `CaseService`.

### Checks

- Schema validity.
- Exact case/trace/evidence identity.
- Every factual claim cites at least one admitted evidence ID.
- All citations belong to the invocation allowlist.
- Knowledge citations are used only for procedure or error definition.
- Proposed action matches the supported hypothesis and deterministic state rules.
- Synthesis preserves conflicts and missing evidence.
- Evaluator covers every claim and required source.
- Golden v1 safety invariants remain unchanged.

### Feedback rules

- First malformed structured output: retry that stage once with the validation summary.
- Second malformed output: stop with `AGENT_OUTPUT_INVALID`.
- Tool timeout: retry once; second timeout stops with `SOURCE_UNAVAILABLE`.
- Missing admitted evidence: stop with `NEEDS_EVIDENCE`; do not substitute knowledge.
- Unsupported claim: evaluator `REJECT`; no recommendation enters the ledger.
- Investigator disagreement with unresolved current-state facts: synthesis `NEEDS_EVIDENCE`.
- Overall harness timeout or budget exhaustion: stop with a typed failure and no grant.

### Stop conditions

- Success: one validated assessment is persisted.
- Safe stop: `PROTECTED`, `NEEDS_EVIDENCE`, evaluator rejection, schema failure after one retry, source timeout after one retry, or budget exhaustion.
- Human gate: any paid provider, model download, AWS invocation, prompt/config promotion, or expansion of agent permissions.

### Frozen per-run budgets

- Three investigator calls, concurrent.
- One synthesis call.
- One evaluator call.
- At most one retry per failed stage.
- At most four read-tool calls per investigator.
- At most two knowledge searches per investigator.
- Per-call model timeout: 45 seconds locally.
- Whole-harness timeout: 120 seconds locally.
- Maximum output tokens and total request count recorded in the run manifest.

## 10. Deterministic validation

`AgentEvidenceValidator` is the authority over all agent outputs. It validates normalized structured objects, not natural-language plausibility.

Mandatory invariants include:

1. Citation IDs are exact admitted IDs for this case and trace.
2. Every factual claim has evidence; knowledge alone cannot support a factual claim.
3. Evidence content digests still match the case store at validation time.
4. Supporting, contradicting, and missing sets are mutually consistent.
5. Retryable-message support requires failed message, retry eligibility, cleared lock, exact missing quantity, and absence of a matching material document.
6. Already-posted support requires complete external message-document-effect lineage.
7. Short-shipment support requires ordered quantity above the authoritative physical receipt and matching ERP receipt.
8. Synthesis does not omit investigator dissent or invent a fourth hypothesis.
9. Evaluator validates all selected claims and cannot allow an action when any required invariant fails.
10. The resulting `InvestigationAssessment` passes the same pure assessment validator used by write and replay paths.

The deterministic diagnosis stub remains available only as a comparison oracle and emergency local fallback. It is not silently substituted when a real model run fails, and the UI/artifact must label which diagnosis source was used.

## 11. Trace and observability contract

Each run writes a normalized, portable trace with:

- run, case, and trace IDs;
- provider, model, prompt, schema, knowledge, harness, and evaluator versions;
- stage start/end and outcome;
- tool name, normalized arguments, result evidence IDs, result digest, duration, and error code;
- structured outputs after validation;
- Strands token, latency, tool-call, and event-loop metrics when available;
- retry count, budget consumption, and stop reason;
- final assessment ID or safe-stop reason.

The artifact excludes chain of thought, hidden model reasoning, raw credentials, full local paths, signer secrets, unrestricted prompts containing sensitive data, and raw SDK event dumps. Prompt templates are separately versioned public files. Tool outputs are represented by admitted evidence IDs and digests.

## 12. Golden v2

Golden v2 composes two proof layers rather than rerunning unnecessary model calls for every authorization-only case.

### Layer A: complete deterministic safety regression

- Re-run all 16 Golden v1 cases.
- Require the same zero values for all five safety counters.
- Prove the agent integration did not weaken authorization, replay, crash recovery, or effect provenance.

### Layer B: agent-to-business-loop profiles

Run four diagnosis profiles through the Strands harness:

1. Retryable lock → accepted retryable-message assessment persisted through `CaseService` → real two-role controlled resolution → `CLOSED`.
2. Already posted → persisted `RECEIPT_ALREADY_POSTED` assessment → no receipt-restart grant/effect; invoice path may proceed only through its correct role and verifier.
3. Genuine short shipment → persisted `PROTECTED` → zero grants and business effects.
4. Material-document source unavailable → persisted `NEEDS_EVIDENCE` with exact source → zero grants and business effects.

Every profile starts from a fresh typed fixture and fresh `enterprise.sqlite` / `case.sqlite`. Final evidence is accepted only after both adapters are reconstructed, the case log replays, and the authoritative enterprise snapshot is reread.

The scripted provider runs all four twice during offline tests and must produce byte-identical normalized results. The Ollama provider runs all four through `agent-smoke`; every run must pass deterministic citation and assessment invariants. A failed Ollama quality run is recorded as `FAIL` and does not fall back to a scripted `PASS`.

`artifacts/golden/golden-v2.json` clearly separates:

- `safety_regression`: Golden v1 result and counters;
- `scripted_strands_proof`: actual Strands SDK loop/tool/schema execution with frozen model events;
- `ollama_model_proof`: real local model configuration and results, or `NOT_RUN` with reason;
- version matrix and promotion status.

`make golden-v2` is an offline composer. It reads the immutable local-model proof from
`artifacts/agent/ollama-smoke-v1.json`, validates its schema and version digests, and
embeds its result without making a model or network call. When that proof is absent or
stale, the report records `ollama_model_proof: NOT_RUN` and is not promotable.
`make agent-smoke` atomically replaces `ollama-smoke-v1.json` only after all four real
model profiles pass, then invokes the offline composer. Tests use an isolated artifact
directory and frozen proof fixtures so they never depend on or overwrite the accepted
local-model evidence.

For each profile it also links, where applicable:

- `agent_run_id` and normalized trace artifact;
- investigation assessment ID and append-only event ID;
- approval and authorization IDs;
- execution attempt and receipt IDs;
- business-effect and material-document IDs;
- stored and replayed final case status;
- forbidden grant/effect counts.

The report fails if these IDs cannot be followed through the persisted ledger and authoritative enterprise history. The main profile cannot pass on a diagnosis-only artifact.

Milestone 4 is accepted only after the real local Ollama section is `PASS`. If a compatible installed local model cannot pass after one bounded prompt correction, stop for a human model-selection decision; do not start an open-ended prompt-tuning loop.

## 13. Commands and cost controls

```bash
make agent-preflight AGENT_CONFIRM=1 MISSING20_OLLAMA_MODEL=qwen3:14b
make check
make golden
make golden-v2
make agent-smoke AGENT_CONFIRM=1 MISSING20_AGENT_PROVIDER=ollama
```

- `agent-preflight` is the one-time user-approved compatibility gate and writes no project business state.
- `make check`, `make golden`, and `make golden-v2` are offline and refuse network/model clients.
- `agent-smoke` defaults to refusal unless `AGENT_CONFIRM=1`.
- The Ollama path verifies localhost, configured model presence, request budget, and version manifest.
- It never pulls a model automatically.
- A non-Ollama provider is rejected during Milestone 4.
- No AWS or paid-model cost is authorized by this design.

## 14. Files

Expected implementation scope:

- `fixtures/knowledge/*.md`
- `fixtures/knowledge/manifest.json`
- `fixtures/prompts/agent-v1/*.md`
- `src/the_missing_20/ports/agent_model.py`
- `src/the_missing_20/ports/knowledge.py`
- `src/the_missing_20/adapters/local_knowledge.py`
- `src/the_missing_20/adapters/strands_models.py`
- `src/the_missing_20/agents/schemas.py`
- `src/the_missing_20/agents/tools.py`
- `src/the_missing_20/agents/investigators.py`
- `src/the_missing_20/agents/synthesis.py`
- `src/the_missing_20/agents/evaluator.py`
- `src/the_missing_20/agents/validation.py`
- `src/the_missing_20/agents/tracing.py`
- `src/the_missing_20/agents/harness.py`
- `src/the_missing_20/evaluation/agent_golden_runner.py`
- `scripts/run_agent_smoke.py`
- `scripts/run_agent_preflight.py`
- `scripts/run_golden_v2.py`
- `tests/unit/test_agent_schemas.py`
- `tests/unit/test_agent_evidence_validation.py`
- `tests/integration/test_strands_harness.py`
- `tests/golden/test_agent_golden_cases.py`
- `artifacts/golden/golden-v2.json`
- `artifacts/agent/model-compatibility.json`
- `artifacts/agent/ollama-smoke-v1.json`

Directories are added only with their first executable or evidence-bearing file. No `strands-agents-tools` dependency is needed because the project exposes only its own two audited read tools.

## 15. Test plan

### Contract and unit tests

- Strict schema rejection for extra fields and illegal state/action output.
- Evidence allowlist, case/trace, digest, and source validation.
- Knowledge cannot support current-state claims.
- Every unsupported or conflicting claim fails closed.
- Prompt, schema, corpus, and harness version digests are stable.
- Tool budget, timeout, malformed-output retry, and overall stop behavior.
- Agent objects cannot import or receive mutation-capable ports.

### Integration tests

- Real Strands `Agent` loop with scripted custom model provider.
- Three investigators execute concurrently rather than serially.
- Each investigator receives only its allowed read tools.
- Synthesis receives validated results, not raw hidden histories.
- Evaluator context is independently assembled.
- Assessment persistence and replay include the full structured output.
- No network, AWS, or paid provider is called by offline tests.

### Adversarial tests

- Uncited factual claim.
- Citation from another case or trace.
- Evidence digest changed after invocation.
- Knowledge cited as proof of current state.
- Synthesis drops contradicting evidence.
- Evaluator allows an unsafe action.
- Agent attempts a nonexistent or write-capable tool.
- First and second malformed structured outputs.
- First and second read-tool timeout.
- Budget exhaustion.
- Prompt injection text inside an evidence field cannot add tools or change system policy.

### Golden verification

- Four diagnosis profiles pass twice with scripted Strands provider.
- All Golden v1 safety cases remain green.
- Ollama smoke passes all four diagnosis profiles without any paid call.
- The retryable Ollama profile reaches `CLOSED` through both real approvals and effects; the safety profiles persist their case outcomes with zero forbidden grants/effects.
- Golden v2 artifact contains no secrets, absolute local paths, chain of thought, or misleading cloud claims.

## 16. Acceptance gate

Milestone 4 requires all of the following:

1. The pre-implementation `qwen3:14b` compatibility gate proves one real Strands tool call and Pydantic structured output at zero cost.
2. The actual Strands SDK is installed, locked, and used by the harness.
3. Three specialized investigators run concurrently with only audited read tools.
4. Structured investigator, synthesis, and evaluator outputs pass deterministic evidence validation.
5. The main profile persists the Strands assessment and reaches `CLOSED` through the existing two-role execution path.
6. Already-posted, short-shipment, and missing-evidence profiles persist the required safe outcomes with zero forbidden grants/effects.
7. No agent can access approval, signer, policy, executor, AWS, shell, filesystem, browser, or arbitrary network capabilities.
8. Scripted-provider offline tests prove the real Strands loop and are byte deterministic.
9. A zero-cost local Ollama model passes all four end-to-end profile checks.
10. Golden v1 remains 16/16 with all five safety counters at zero.
11. Golden v2 links agent run, assessment/event, approvals, receipts, effects, and replayed outcome rather than presenting disconnected reports.
12. Golden v2 cleanly labels scripted proof, real-model proof, and unimplemented AWS proof.
13. `make check`, `make golden`, `make golden-v2`, secret/path scan, and `git diff --check` pass.
14. The independent Chief Architect returns `APPROVE` after inspecting code, tests, Ollama output, and artifacts.

Only after this gate may the milestone be committed and pushed. Milestone 5 cannot begin on a scripted-only diagnosis result.

## 17. Review protocol

To avoid unproductive review loops:

1. One pre-implementation Chief Architect review checks only architecture, safety boundaries, real Strands use, zero-cost feasibility, Golden v2 credibility, and five-minute demo value.
2. Luna implements the approved spec in bounded slices and does not expand product scope.
3. The primary agent runs local checks and the Ollama smoke path.
4. One post-implementation Chief Architect gate reports only material correctness, safety, real-data-flow, or competition blockers.
5. Optional polish is recorded for later and never blocks Milestone 4.
6. At most one focused correction pass is allowed before the primary agent takes over or reports a genuine blocker.

## 18. Source notes

Primary references used for this design:

- [Strands structured output](https://strandsagents.com/docs/user-guide/concepts/agents/structured-output/)
- [Strands multi-agent patterns](https://strandsagents.com/docs/user-guide/concepts/multi-agent/multi-agent-patterns/)
- [Strands Ollama provider](https://strandsagents.com/docs/user-guide/concepts/model-providers/ollama/)
- [Strands custom model provider](https://strandsagents.com/docs/user-guide/concepts/model-providers/custom_model_provider/)
- [Strands metrics](https://strandsagents.com/docs/user-guide/observability-evaluation/metrics/)
- [Strands tool security](https://strandsagents.com/docs/user-guide/concepts/tools/)
- [Ollama qwen3:14b model](https://ollama.com/library/qwen3:14b)
- [Ollama streaming tool calling](https://ollama.com/blog/streaming-tool)
