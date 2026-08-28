# Milestone 4: Strands Multi-Agent Investigation and Golden v2

**Status:** Terminal `BLOCK_M4`; v4 through final v9 each failed their sole authorized real-provider gate
**Date:** 2026-08-27
**Parent design:** [`2026-08-25-the-missing-20-design.md`](2026-08-25-the-missing-20-design.md)  
**Accepted safety foundation:** [`2026-08-25-milestone-3-golden-v1-design.md`](2026-08-25-milestone-3-golden-v1-design.md)

## 1. Decision

### Final v9 terminal gate result, 2026-08-27

The final authorized `agent-contract/v9` repair moved exact evidence-ID coverage into a
harness-owned citation closure. Its implementation passed 458 Python tests, one
JavaScript test, Golden v1 16/16 with all safety counters zero, and Golden v2
safety/scripted checks.

The sole v9 Nova Pro batch was claimed as `3f9366a04770425baa3fcae16d543934`
and failed profile 01 at the evaluator boundary with `accepted synthesis does not have
complete citation closure`. The redacted outcome records 10 requests, 23,431 input
tokens, 3,360 output tokens, `$0.0294968` incremental cost, and `$0.1109336`
cumulative cost. Independent final review returned `BLOCK_M4`. The M4 mechanical patch
cycle is closed; M5–M7 cannot start, and no retry, tuning, fallback, or v10 is authorized.

### Final v8 terminal gate result, 2026-08-27

The independently approved `agent-contract/v8` fork made evidence-to-source coverage
harness-owned. After one focused correction, its offline implementation passed 445
Python tests, one JavaScript test, Golden v1 16/16 with all safety counters zero, and
Golden v2 safety/scripted checks.

The sole v8 Nova Pro batch was durably claimed and failed the first profile at the
evaluator validator with `accepted synthesis does not cover all admitted evidence`.
The redacted outcome records 9 requests, 20,823 input tokens, 2,998 output tokens,
`$0.026252` incremental cost, and `$0.0814368` cumulative cost. Independent final
review returned `BLOCK_M4`; M5–M7 cannot start, and no v8 retry, tuning, fallback, or
second provider batch is authorized.

### Final v7 terminal gate result, 2026-08-27

The independently approved `agent-contract/v7` fork moved synthesis and evaluator
protocol versions out of model output into an immutable harness-owned envelope. Its
offline implementation passed 432 Python tests, one JavaScript test, Golden v1 16/16
with all safety counters zero, Golden v2 safety/scripted checks, determinism, schema and
artifact scans, and `git diff --check`.

The durably claimed, exactly-once v7 Nova Pro batch failed on the first profile at the
evaluator validator with `accepted evaluation omits a required source`. It used 9
requests, 23,175 input tokens, and 3,371 output tokens, costing an estimated `$0.0293272`
incrementally and `$0.0551848` cumulatively. No v7 PASS artifact exists. The independent
final verdict is `BLOCK_M4`; M5–M7 cannot start, and no retry, tuning, fallback, provider
call, or v7 code change is authorized.

### Final terminal gate result, 2026-08-27

The independently approved `agent-contract/v6` product fork replaced record-level
polarity with claim-level relations. Its offline implementation passed Ruff, mypy, 418
Python tests, one JavaScript test, Golden v1 with 16/16 cases and all five safety
counters at zero, Golden v2 scripted and safety checks, deterministic replay, artifact
hygiene scans, and `git diff --check`.

The sole authorized v6 Nova Pro product run failed on the first profile at the synthesis
validator with `unsupported synthesis version`. The redacted `agent-failure/v2`
manifest records 8 requests, 20,782 input tokens, 2,885 output tokens, and estimated
cost `$0.0258576`. No promotable Bedrock PASS artifact exists. A new independent Chief
Architect confirmed `BLOCK_M4`: the real-provider attempt was consumed, M5 is not
authorized, and there is no retry, tuning, fallback, compatibility probe, second batch,
or code change under v6. Only a separately authorized material product-direction fork
may reopen M4. The governing v6 record is
`2026-08-27-milestone-4-agent-contract-v6-relation-aware-evidence-design.md`.

### Terminal gate result, 2026-08-26

The offline v4 implementation passed `make check` with 401 Python tests, Golden v1
with 16/16 cases and zero safety counters, Golden v2 scripted and safety gates,
the secret/path scan, `git diff --check`, and an independent Chief Architect review.

The single permitted real-provider run used Nova Pro through the capped Bedrock smoke
command and stopped with:

`supported action does not cover every required authoritative source`

This is a deterministic safety-boundary rejection, not an infrastructure failure.
Under the autonomous delivery-loop budget, v4 is terminally `BLOCKED`: there is no
retry, prompt tuning, commit, push, or M5 progression on that contract. The user
explicitly authorized the single architecture rebaseline on 2026-08-26. Its governing
design is `2026-08-26-milestone-4-agent-contract-v5-rebaseline-design.md`; this does not
retroactively convert the failed v4 run into evidence for v5.

Milestone 4 replaces the deterministic diagnosis stub with a real Strands Agents harness while preserving every deterministic safety boundary accepted in Golden v1.

Three specialized Strands agents investigate the same admitted case evidence in parallel. A fourth Strands agent synthesizes their structured findings. A fifth, independently prompted Strands agent evaluates the proposed conclusion against a separately assembled evidence view. Deterministic validators then decide whether the structured outputs are admissible. Only a validated `InvestigationAssessment` may enter the existing case ledger.

The latest attempted model-facing contract is the terminally blocked `agent-contract/v6`:
models supply relation-aware factual claims and exact admitted-evidence citations, while
the harness derives aggregate evidence projections and application-owned dissent.
Models do not recommend or authorize actions. The detector supplies immutable source
availability, and successful audited retrievals own knowledge provenance. Offline CI
uses a scripted Strands provider to exercise the real agent loop without network access.
The sole v6 Nova Pro proof failed and is not reusable as PASS evidence; AgentCore and M5
remain out of scope while M4 is blocked.

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
- Offline scripted-provider tests and one separately approved, tightly capped Bedrock Nova Pro verification.
- Golden v2 evidence that composes with all Golden v1 safety results.

### Out of scope

- Approval, signing, policy, executor, database mutation, shell, filesystem, browser, network, or arbitrary MCP tools inside an agent.
- Dynamic Swarm routing or an LLM-created workflow graph.
- AgentCore Runtime, Gateway, Policy, KMS, DynamoDB, Cognito, or Bedrock Knowledge Bases; these remain Milestone 6.
- Prompt self-modification or automatic promotion of model output into a golden dataset.
- Production secrets, employer data, private incidents, private runbooks, or private terminology.
- Any uncapped model invocation, provisioned throughput, or automatic fallback to another model.

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
  contradicting_evidence_ids[]
```

An investigator cannot output an approval, grant, execution instruction, arbitrary tool name, database command, or `CLOSED` state.

### Synthesis output

```text
SynthesisResult
  selected_hypothesis
  conclusion
  confidence_band
  factual_claims[]
  contradicting_evidence_ids[]
  preserved_dissent[]
    hypothesis_type
    conclusion
    evidence_ids[]
  synthesis_version
```

Synthesis must include every investigator in `preserved_dissent`, even when rejected. It may not upgrade uncertainty, remove contradicting evidence, or turn knowledge content into a current-state fact.

The model does not author `supporting_evidence_ids`, `missing_evidence_sources`, or `knowledge_citations`. The validator derives support for public serialization as the exact sorted union of every factual claim's `evidence_ids`, derives missing sources from the detector-supplied availability record, and derives knowledge citations from successful audited knowledge retrievals. An unknown, uncited, contradictory, cross-case, status-inconsistent, stale, or tampered citation fails closed before derivation.

### Deterministic source availability

The harness receives exactly one immutable status for each required authoritative source:
`FAILED_MESSAGE_QUEUE`, `ERP_RECEIPT`, `MATERIAL_DOCUMENT`, `WAREHOUSE`, and `INVOICE`.
Each entry is `AVAILABLE` or `UNAVAILABLE`. An available entry has no reason and exactly
one matching admitted evidence record; an unavailable entry has a non-empty reason and
no admitted evidence record. The persisted `DetectionGenesis` is the authority for
material-document status and reason; admitted detector evidence supplies the remaining
source facts. Public investigator and synthesis artifacts may expose the harness-derived
sorted `missing_evidence_sources`, but the model schemas reject that field as an extra.

### Deterministic knowledge provenance

`search_synthetic_knowledge` is the sole authority for knowledge citations. Each
successful search records the exact returned knowledge ID, corpus version, allowed use,
and content digest in the tool audit. Before a citation can be serialized, the harness
re-resolves the record against the frozen corpus manifest and verifies all four fields.
The public investigator result contains the unique, sorted projection of those verified
tool results. Zero successful searches produces zero citations. Failed searches,
unknown IDs, stale versions, digest mismatches, duplicate/conflicting records, and
model-authored citation fields produce no accepted citation and fail closed. The public
record contains only `knowledge_id`, `version`, `allowed_use`, and `content_digest`; it
never contains raw excerpts or local paths. Knowledge may provide procedure or
error-definition context, but never supports a current-state claim.

### Evaluator output

```text
AgentEvaluationResult
  decision: ACCEPT | REJECT | MORE_EVIDENCE
  validated_claim_ids[]
  validated_evidence_ids[]
  failed_invariants[]
  required_evidence_sources[]
  evaluator_version
```

The evaluator cannot recommend, authorize, or execute an action. The application-owned
`ActionRecommendationPolicy/v1` is the only recommendation seam; its result is adapted
into the existing domain `EvaluationResult` and then remains subject to the established
two-role approval and controlled execution workflow.

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
   - Records the exact knowledge ID, version, allowed use, and digest for every returned record in the immutable tool audit.
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

### Bedrock Nova Pro provider

- Uses the Strands Bedrock provider and Amazon Bedrock Converse API.
- Freezes Amazon Nova Pro v1 as the only Milestone 4 real-model provider.
- Uses on-demand standard inference only; provisioned throughput is forbidden.
- Sets temperature to zero and fixes maximum output tokens.
- Requires `BEDROCK_CONFIRM=1`, an allowed account and region, a request cap, and input/output token caps.
- Is invoked only by `make agent-preflight` or `make agent-smoke` with explicit confirmation.
- Rejects a second provider, cross-provider fallback, or execution after any budget is exhausted.

### Compatibility history and approved smoke

The Nova Lite v1 and Nova Pro v1 full-smoke attempts using the prior model-authored
representation are recorded as representation failures; neither is evidence for the
`agent-contract/v5` model boundary. The separate Nova Pro compatibility probe did pass
tool calling and strict Pydantic output, proving only SDK/model compatibility. The single
user-approved Nova Pro smoke against `agent-contract/v2` was executed and stopped at the
deterministic validator because a rejected investigator also reported a missing evidence
source. This is a factual v2 representation failure, not a v3 result. The single
user-approved Nova Pro smoke against `agent-contract/v3` was then executed and stopped
at the deterministic validator because a returned knowledge citation did not match the
invocation corpus. No passing smoke artifact was written, Golden v2 remains
non-promotable, and the failure is not reinterpreted as a quality pass. The user then
explicitly reopened M4 and approved `agent-contract/v4`; that representation was
terminally blocked, and the `agent-contract/v5` rebaseline is now authorized. Its
implementation and any new real-model proof remain pending.

### Pre-implementation compatibility gate

Before Luna changes product code, the user-approved gate performs only:

1. verify AWS credentials, expected account, allowed region, and Nova Pro model access without printing credentials or account identifiers;
2. freeze at most two Bedrock requests, 20,000 aggregate input tokens, and 4,000 aggregate output tokens;
3. invoke one minimal Strands agent with one audited echo/read tool;
4. require the model to call the tool and return one Pydantic structured output;
5. record model ID, region, Strands version, tool call, schema result, latency, token usage, estimated maximum cost, and credit-funded provider label in `artifacts/agent/model-compatibility.json`.

The preflight's frozen maximum estimated Nova Pro inference cost is below $0.03. If either tool calling or structured output fails, Milestone 4 implementation does not begin. There is no automatic switch to another model or a scripted-only milestone.

The accepted preflight used Strands `1.53.0` with Nova Pro in `us-west-2`, made two model requests, consumed 1,555 input and 222 output tokens, called the allowlisted tool exactly once, and returned the required Pydantic result. Nova Pro rejected the optional Bedrock `strict` tool field, so the accepted provider configuration omits that field while retaining deterministic Pydantic validation at the harness boundary. The immutable result is recorded in `artifacts/agent/model-compatibility.json`.

Official AWS documentation confirms Nova tool calling through Converse and constrained structured output from JSON schemas. Official Strands documentation confirms the Bedrock provider, Pydantic structured outputs through `structured_output_model`, custom model providers, and metrics on `AgentResult`.

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
- Knowledge citations are derived only from verified successful retrieval results and are used only for procedure or error definition.
- Proposed action matches the supported hypothesis and deterministic state rules.
- Synthesis follows detector-authoritative source availability and preserves conflicts.
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
- Human gate: any provider change, AWS invocation above the accepted caps, prompt/config promotion, or expansion of agent permissions.

### Frozen per-run budgets

- Three investigator calls, concurrent.
- One synthesis call.
- One evaluator call.
- At most one retry per failed stage.
- At most five read-tool calls per investigator, one for each required authoritative source.
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
4. Supporting and contradicting citations are mutually consistent; missing sources are derived only from authoritative availability.
5. Retryable-message support requires failed message, retry eligibility, cleared lock, exact missing quantity, and absence of a matching material document.
6. Already-posted support requires complete external message-document-effect lineage.
7. Short-shipment support requires ordered quantity above the authoritative physical receipt and matching ERP receipt.
8. Synthesis does not omit investigator dissent or invent a fourth hypothesis.
9. Supporting evidence is derived only as the exact union of factual-claim citation IDs; the model cannot independently claim support.
10. Knowledge citations are derived only from successful audited retrieval records whose ID, version, allowed use, and digest match the frozen corpus.
11. An actionable supported result covers every required authoritative source.
12. Every factual or contradicting evidence ID cited by an investigator is present in that
    investigator's successful, normalized evidence-read audit as well as its admitted allowlist.
13. Evaluator validates all selected claims and cannot allow an action when any required invariant fails.
14. The resulting `InvestigationAssessment` passes the same pure assessment validator used by write and replay paths.

The deterministic diagnosis stub remains available only as a comparison oracle and emergency local fallback. It is not silently substituted when a real model run fails, and the UI/artifact must label which diagnosis source was used.

## 11. Trace and observability contract

Each run writes a normalized, portable trace with:

- run, case, and trace IDs;
- provider, model, prompt, schema, agent-contract, knowledge, harness, and evaluator versions;
- stage start/end and outcome;
- tool name, normalized arguments, result evidence IDs, result digest, duration, and error code;
- deterministically derived successful evidence-read IDs for each investigator;
- tool-derived knowledge provenance records and the validated citation projection;
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

The scripted provider runs all four twice during offline tests and must produce byte-identical normalized results. The Bedrock provider runs all four through `agent-smoke`; every run must pass deterministic citation and assessment invariants. A failed Bedrock quality run is recorded as `FAIL` and does not fall back to a scripted `PASS`.

`artifacts/golden/golden-v2.json` clearly separates:

- `safety_regression`: Golden v1 result and counters;
- `scripted_strands_proof`: actual Strands SDK loop/tool/schema execution with frozen model events;
- `bedrock_model_proof`: the one separately approved Nova Pro smoke configuration and results, or `NOT_RUN` with reason;
- version matrix and promotion status.

`make golden-v2` is an offline composer. It reads the immutable Bedrock proof from
`artifacts/agent/bedrock-smoke-v2.json`, validates its schema and version digests, and
embeds its result without making a model or network call. When that proof is absent or
stale, the report records `bedrock_model_proof: NOT_RUN` and is not promotable.
`make agent-smoke` atomically replaces `bedrock-smoke-v2.json` only after all four real
model profiles pass, then invokes the offline composer. Tests use an isolated artifact
directory and frozen proof fixtures so they never depend on or overwrite the accepted
Bedrock evidence.

For each profile it also links, where applicable:

- `agent_run_id` and normalized trace artifact;
- investigation assessment ID and append-only event ID;
- approval and authorization IDs;
- execution attempt and receipt IDs;
- business-effect and material-document IDs;
- stored and replayed final case status;
- forbidden grant/effect counts.

The report fails if these IDs cannot be followed through the persisted ledger and authoritative enterprise history. The main profile cannot pass on a diagnosis-only artifact.

The offline `agent-contract/v5` implementation is complete only when the scripted proof,
Golden v1 regression, and all offline gates pass. The separately approved Nova Pro smoke
section remains `NOT_RUN` until the primary agent executes the single authorized run. The
earlier `agent-contract/v2`, `agent-contract/v3`, and `agent-contract/v4` smoke attempts are recorded as failed
representations and are not reused as v5 evidence. A v5 smoke requires explicit human
approval after offline implementation and independent review; it is a single bounded
verification run with no prompt correction or tuning. If it fails, stop for a human
model-selection decision.

## 13. Commands and cost controls

```bash
make agent-preflight BEDROCK_CONFIRM=1 MISSING20_AGENT_PROVIDER=bedrock
make check
make golden
make golden-v2
make agent-smoke BEDROCK_CONFIRM=1 MISSING20_AGENT_PROVIDER=bedrock
```

- `agent-preflight` is the one-time user-approved compatibility gate and writes no project business state.
- `make check`, `make golden`, and `make golden-v2` are offline and refuse network/model clients.
- `agent-smoke` defaults to refusal unless `BEDROCK_CONFIRM=1`.
- The Bedrock path verifies credentials, account, region, model, request budget, token caps, and version manifest.
- Preflight allows at most 2 requests, 20,000 input tokens, and 4,000 output tokens.
- The full four-profile smoke allows at most 40 requests, 400,000 input tokens, and 80,000 output tokens, with a maximum estimated inference cost below $0.60 at the frozen Nova Pro rates.
- A non-Bedrock provider is rejected during Milestone 4 real-model proof.
- No provisioned throughput, AgentCore resource, Knowledge Base, browser, or unrelated AWS service is authorized by this design.

## 14. Files

Expected implementation scope:

- `fixtures/knowledge/*.md`
- `fixtures/knowledge/manifest.json`
- `fixtures/prompts/agent-v1/*.md` (historical)
- `fixtures/prompts/agent-v2/*.md`
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
- `artifacts/agent/bedrock-smoke-v2.json`

Directories are added only with their first executable or evidence-bearing file. No `strands-agents-tools` dependency is needed because the project exposes only its own two audited read tools.

## 15. Test plan

### Contract and unit tests

- Strict schema rejection for extra fields and illegal state/action output.
- Evidence allowlist, case/trace, digest, and source validation.
- Model-authored knowledge citations are rejected as extra fields.
- Zero knowledge searches serializes zero citations.
- Tool-derived knowledge citations match exact corpus ID, version, allowed use, and digest.
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
- Fabricated model-authored knowledge citation.
- Stale-version, unknown-ID, wrong-use, or digest-tampered knowledge retrieval result.
- Knowledge cited as proof of current state.
- Synthesis drops contradicting evidence.
- Evaluator allows an unsafe action.
- Agent attempts a nonexistent or write-capable tool.
- First and second malformed structured outputs.
- First and second read-tool timeout.
- Budget exhaustion.
- Prompt injection text inside an evidence field cannot add tools or change system policy.

### Golden verification

- Four diagnosis profiles pass twice with scripted Strands provider under `agent-contract/v5`.
- All Golden v1 safety cases remain green.
- The separately approved Bedrock Nova Pro smoke passes all four diagnosis profiles within the frozen call and token budgets.
- The retryable Bedrock profile reaches `CLOSED` through both real approvals and effects; the safety profiles persist their case outcomes with zero forbidden grants/effects.
- Golden v2 artifact contains no secrets, absolute local paths, chain of thought, or misleading cloud claims.

## 16. Acceptance gate

Milestone 4 requires all of the following:

1. The separately approved Bedrock Nova Pro compatibility gate proves one real Strands tool call and Pydantic structured output within the sub-$0.03 cap.
2. The actual Strands SDK is installed, locked, and used by the harness.
3. Three specialized investigators run concurrently with only audited read tools.
4. Structured investigator, synthesis, and evaluator outputs pass deterministic evidence validation, including detector-authoritative source availability and retrieval-derived knowledge provenance.
5. The main profile persists the Strands assessment and reaches `CLOSED` through the existing two-role execution path.
6. Already-posted, short-shipment, and missing-evidence profiles persist the required safe outcomes with zero forbidden grants/effects.
7. No agent can access approval, signer, policy, executor, AWS, shell, filesystem, browser, or arbitrary network capabilities.
8. Scripted-provider offline tests prove the real Strands loop and are byte deterministic.
9. The separately approved Bedrock Nova Pro smoke passes all four end-to-end profile checks within the accepted request and token caps.
10. Golden v1 remains 16/16 with all five safety counters at zero.
11. Golden v2 links agent run, assessment/event, approvals, receipts, effects, and replayed outcome rather than presenting disconnected reports.
12. Golden v2 cleanly labels scripted proof, real-model proof, and unimplemented AWS proof.
13. `make check`, `make golden`, `make golden-v2`, secret/path scan, and `git diff --check` pass.
14. The independent Chief Architect returns `APPROVE` after inspecting code, tests, Bedrock output, and artifacts.

Only after this gate may the milestone be committed and pushed. Milestone 5 cannot begin on a scripted-only diagnosis result.

### Terminal v8 gate (2026-08-27)

`BLOCK_M4`. The sole durably claimed v8 Nova Pro acceptance batch failed profile 01 at
the evaluator validator with `accepted synthesis does not cover all admitted evidence`.
The claim ID is `4716bb0a0af8431387f8480a037d44e9`; the redacted outcome records 9
requests, 20,823 input tokens, 2,998 output tokens, `$0.026252` incremental estimated
cost, and `$0.0814368` cumulative estimated project cost. All post-failure offline and
safety gates passed, but no four-profile provider PASS exists. Independent final review
returned `BLOCK_M4`; therefore v8 cannot be retried or tuned and M5 cannot begin.

## 17. Review protocol

To avoid unproductive review loops:

1. One pre-implementation Chief Architect review checks only architecture, safety boundaries, real Strands use, capped-credit feasibility, Golden v2 credibility, and five-minute demo value.
2. Luna implements the approved spec in bounded slices and does not expand product scope.
3. The primary agent runs local checks and the explicitly confirmed Bedrock smoke path.
4. One post-implementation Chief Architect gate reports only material correctness, safety, real-data-flow, or competition blockers.
5. Optional polish is recorded for later and never blocks Milestone 4.
6. At most one focused correction pass is allowed before the primary agent takes over or reports a genuine blocker.

## 18. Source notes

Primary references used for this design:

- [Strands structured output](https://strandsagents.com/docs/user-guide/concepts/agents/structured-output/)
- [Strands multi-agent patterns](https://strandsagents.com/docs/user-guide/concepts/multi-agent/multi-agent-patterns/)
- [Strands Amazon Bedrock provider](https://strandsagents.com/docs/user-guide/concepts/model-providers/amazon-bedrock/)
- [Strands custom model provider](https://strandsagents.com/docs/user-guide/concepts/model-providers/custom_model_provider/)
- [Strands metrics](https://strandsagents.com/docs/user-guide/observability-evaluation/metrics/)
- [Strands tool security](https://strandsagents.com/docs/user-guide/concepts/tools/)
- [Amazon Nova tool use](https://docs.aws.amazon.com/nova/latest/userguide/tool-use.html)
- [Amazon Nova structured output](https://docs.aws.amazon.com/nova/latest/userguide/concept-chapter-servicename.html)
- [Amazon Bedrock pricing](https://aws.amazon.com/bedrock/pricing/)
- [Hackathon official rules and promotional credits](https://agentsforhumans.devpost.com/rules)
