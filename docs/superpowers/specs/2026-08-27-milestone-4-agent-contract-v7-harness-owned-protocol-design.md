# Milestone 4 Agent Contract v7 Harness-Owned Protocol Versions

**Status:** Terminal `BLOCK_M4` at the sole v7 Nova Pro acceptance batch
**Scope:** M4 protocol ownership only; no M5/M6/M7 work until M4 passes
**Product direction:** User-approved material fork from terminally blocked v6

## Terminal gate result, 2026-08-27

The v7 design and offline implementation passed independent design and implementation
gates. After the sole focused correction, Ruff, mypy, 432 Python tests, one JavaScript
test, Golden v1 with 16/16 cases and all five safety counters at zero, Golden v2 safety
and scripted checks, deterministic checks, provider-schema and artifact-hygiene scans,
and `git diff --check` passed.

The exclusive v7 attempt claim was durably created before provider I/O. The sole Nova
Pro batch then exercised the first product profile and failed at the evaluator validator
with `accepted evaluation omits a required source`. The redacted `agent-failure/v3`
record reports 9 requests, 23,175 input tokens, 3,371 output tokens, incremental cost
`$0.0293272`, and cumulative provider cost `$0.0551848`, within the `$0.60` hard cap.
No v7 PASS artifact exists and Golden v2 remains `NOT_READY`.

The independent final Chief Architect verdict is `BLOCK_M4`. The exactly-once v7 batch
and the single correction allowance are consumed. No retry, tuning, fallback, provider
call, code change, commit, push, or M5–M7 progression is authorized under this contract.
Only a newly authorized material product-direction fork may reopen M4.

## 1. Loop contract

### Goal

Preserve the real Strands investigator, synthesis, and evaluator workflow while removing
non-semantic protocol-version constants from probabilistic model output. Prove all four
synthetic profiles with exactly one separately gated Nova Pro acceptance batch and retain
every v6 fail-closed safety boundary.

### Input scope

- Current dirty M4 worktree and approved v6 relation-aware evidence design.
- Synthetic enterprise fixtures and frozen synthetic knowledge only.
- Existing Strands `1.53.0` on-demand Nova Pro provider in `us-west-2`.
- Previously recorded provider spend: `$0.0258576`.
- Total promotional-credit hard cap: `$0.60`; remaining authorization:
  `$0.5741424`.

No production or employer data, provider fallback, compatibility probe, second provider
batch, new agent permissions, M5 UI work, AgentCore deployment, commit, push, or public
action is in scope for this milestone loop.

### Execute

1. Remove synthesis and evaluator protocol-version fields from model-authored schemas.
2. Validate only semantic model output at the provider-visible boundary.
3. Stamp immutable protocol versions in application-owned stage records, trace, public
   projections, persisted assessment, Golden v2, and success/failure evidence.
4. Run all offline, adversarial, Golden, deterministic, security, and cost gates.
5. Obtain an independent implementation approval.
6. After read-only AWS identity and cumulative-budget preflight, execute exactly one v7
   Nova Pro four-profile acceptance batch.
7. Save a redacted PASS or failure manifest, rerun all local gates, and obtain an
   independent final M4 verdict.

### Feedback and stop rules

- One Luna implementation pass and at most one focused material correction.
- A second material implementation failure stops for a new product decision.
- A provider model, validator, or product-output failure consumes the v7 batch and marks
  M4 `BLOCKED`; there is no retry, tuning, fallback, or second batch.
- Infrastructure failure before the product path is exercised is recorded and returned
  to the controller; it does not silently authorize another call.
- Success requires all offline gates, all four real-provider profiles, Golden v2
  promotion, and independent `APPROVE_M4`.

### Records

Record contract/prompt/schema/harness/policy versions, schema digests, audited reads,
claim relations, coverage ledger, evaluator decision, policy decision, approvals,
receipts/effects/replay, exact request/token usage, incremental and cumulative estimated
cost, provider/model identity, reviewer verdicts, and known limitations. Never record
credentials, account identifiers, raw model prose on failure, private data, hidden
reasoning, or local absolute paths.

### Human gates

Only login/MFA, projected cumulative spend above `$0.60`, public or destructive action,
legal action, a new material product fork, or final ready-to-be-judged product judgment.

## 2. Root cause being removed

In v6, `SynthesisResult.synthesis_version` and
`AgentEvaluationResult.evaluator_version` were model-authored `NonEmptyStr` fields. Their
provider-visible JSON schemas allowed any nonempty string, while deterministic validators
later required exact application constants. The v6 synthesis prompt did not state the
required literal. Scripted fixtures injected the correct constant directly, so offline
tests could not reproduce a real model returning a different but schema-valid value.

Protocol identity is application metadata, not an evidence interpretation. Asking a
model to reproduce it adds failure probability without adding agentic value or safety.

## 3. Contract boundary

`agent-contract/v7` model-authored output contains only semantic fields.

### InvestigatorResult

Unchanged from v6:

- fixed investigator and hypothesis identity;
- conclusion and confidence;
- relation-aware factual claims with exact admitted-evidence citations.

### SynthesisResult

Contains only:

- `selected_hypothesis`;
- `conclusion`;
- `confidence_band`;
- relation-aware `factual_claims`.

`synthesis_version` is forbidden as an extra field. The provider-visible JSON schema
must contain no synthesis, contract, prompt, harness, evaluator, policy, artifact, or
trace version field.

### AgentEvaluationResult

Contains only:

- decision;
- validated claim IDs;
- validated evidence IDs;
- failed invariants;
- required evidence sources.

`evaluator_version` is forbidden as an extra field. No model may author protocol or
action authority.

Legacy version fields fail strict Pydantic validation rather than being ignored.

## 4. Harness-owned protocol envelope

The harness creates an immutable `AgentProtocolEnvelope/v1` after a stage's semantic
output passes strict schema validation. It contains:

- `agent_contract_version = agent-contract/v7`;
- `prompt_version` and prompt digest;
- `schema_digest` derived from the provider-visible semantic schemas;
- `synthesis_protocol_version = synthesis-protocol/v1`;
- `evaluator_protocol_version = evaluator-protocol/v1`;
- harness, coverage-ledger, action-policy, trace, artifact, and knowledge versions.

The envelope is never passed to, accepted from, or repaired using a model. Constants are
defined once in application code and passed explicitly to serializers/adapters; domain
assessment construction must not read a version from `AgentEvaluationResult`.

Application-owned versions appear in:

- normalized per-stage trace metadata;
- public investigator/synthesis/evaluator projections;
- persisted `EvaluationResult.evaluator_version`;
- coverage and policy records;
- Golden v2 version matrix;
- redacted provider PASS/failure manifests.

Every projection must equal the same immutable envelope. A mismatch, missing envelope,
unknown envelope version, or model-authored legacy version field fails closed.

## 5. Data and safety flow

```text
detector-owned availability + admitted synthetic evidence
  -> three fixed Strands investigators with audited reads
  -> deterministic semantic validation
  -> Strands synthesis (semantic output only)
  -> deterministic semantic validation
  -> independent Strands evaluator (semantic output only)
  -> deterministic evaluator validation
  -> harness-owned immutable protocol envelope
  -> selected-investigator coverage ledger
  -> deterministic action policy
  -> persisted assessment
  -> two-role human approval
  -> controlled execution, authoritative reread, ledger replay
```

All v6 relation-aware claim, evidence integrity, complete-read, fixed-role, synthesis
non-upgrade, dissent projection, selected-path contradiction, evaluator coverage,
deterministic action, approval, idempotency, replay, and safety-counter gates remain
unchanged.

## 6. Provider-visible and public schemas

Tests must snapshot the exact provider-visible `SynthesisResult` and
`AgentEvaluationResult` JSON schemas and prove no property name includes `version`,
`protocol`, `schema_digest`, `prompt`, `harness`, `policy`, `trace`, `artifact`, or action
authority.

Public output may include application-owned version metadata only through the immutable
envelope. Public serialization must make the ownership explicit, for example:

```json
{
  "synthesis": {"selected_hypothesis": "RETRYABLE_MESSAGE", "factual_claims": []},
  "protocol": {
    "agent_contract_version": "agent-contract/v7",
    "synthesis_protocol_version": "synthesis-protocol/v1"
  }
}
```

The public compatibility projection may retain an `evaluator_version` field required by
the existing domain record, but its value must be injected from the envelope and must
not exist in provider-visible evaluator output.

## 7. Failure behavior and observability

Structured-output parsing failures, semantic validation failures, timeouts, budget
exhaustion, and stage exceptions retain exact assigned stage/role and a stable prose-free
error code. Provider failures write a redacted manifest with profile, stage, role,
contract/envelope versions, model, requests, tokens, incremental cost, cumulative cost,
and caps. A failure artifact can never satisfy Golden promotion.

No raw provider output is persisted on failure. The absence of raw prose must not prevent
attributing failure to the parser, semantic validator, budget boundary, or application
policy.

## 8. Cumulative cost and call boundary

The v7 run is one four-profile batch with no probe or fallback. Preflight must verify:

- restricted non-root AWS identity and expected account;
- `us-west-2` and existing on-demand Nova Pro model;
- AWS mutations disabled;
- prior recorded cost exactly `$0.0258576`;
- maximum possible incremental v7 cost at or below `$0.5741424`;
- maximum possible cumulative cost at or below `$0.60`.

Keep the 40-request and 400,000-input-token caps. Set the per-request output ceiling no
higher than 1,985 tokens, making the 40-request output ceiling 79,400 tokens. At frozen
rates this bounds the configured cap combination to `$0.57408` incremental and
`$0.5999376` cumulative cost.

The current post-response token ledger is insufficient by itself because the request
that crosses a token cap has already incurred cost. Before opening each provider stream,
v7 must atomically reserve:

- one request;
- a conservative input-token upper bound no smaller than the UTF-8 byte length of the
  complete serialized provider request;
- the configured 1,985-token maximum output;
- the corresponding frozen-rate cost.

Concurrent investigators share this reservation ledger. A reservation that could make
configured or cumulative reserved cost exceed its cap is refused before network I/O.
Reported provider usage reconciles the reservation after the response; malformed usage
or usage above the conservative reservation fails closed and is recorded. Tests must
prove that the final permitted request cannot overshoot the cumulative cost boundary.

The success or failure manifest must report both actual incremental cost and cumulative
estimated project provider cost.

## 9. Offline verification

Required checks:

1. Provider-visible schemas contain no model-writable version/protocol fields.
2. Legacy synthesis/evaluator version fields are rejected as extras.
3. Application envelope values are immutable and consistent across trace, public output,
   persisted assessment, Golden artifacts, and provider manifests.
4. Missing, mismatched, or tampered envelope metadata fails closed.
5. A wrong-but-nonempty model-authored version cannot occur because no such field exists.
6. All v6 mixed-relation, contradiction, evidence, role, coverage, evaluator, policy,
   approval, execution, replay, and failure-manifest adversarial tests remain green.
7. `make check` passes Ruff, mypy, all Python tests, and JavaScript tests.
8. Golden v1 passes 16/16 with every safety counter zero.
9. Golden v2 scripted and safety proofs pass and are byte-identical.
10. Secret, local-path, private-data, hidden-reasoning, misleading-cloud-claim, and
    provider-schema scans pass.
11. `git diff --check` passes.

## 10. Real-provider and M4 acceptance

After independent offline implementation approval, exactly one capped v7 Nova Pro batch
must pass:

- retryable main path reaches `CLOSED` only after both approvals and verified effect;
- already-posted reaches its safe closed outcome with no restart;
- genuine shortage reaches `PROTECTED` with no forbidden effect;
- missing evidence reaches `REQUIRE_EVIDENCE` with no forbidden effect;
- all traces carry the same application-owned protocol envelope;
- request, token, incremental cost, and cumulative cost remain within their caps.

The primary orchestrator then reruns all offline gates and an independent Chief Architect
returns `APPROVE_M4`. Only then may the controller start M5. No commit or push occurs
before the final gate.

## 11. Bounded delivery governance

1. Primary orchestrator owns scope, diff, tests, cumulative cost, evidence, and final
   acceptance.
2. A new independent Chief Architect reviews this design for material blockers only.
3. Luna implements one bounded pass after design approval.
4. Primary inspects actual changes and executes every offline gate.
5. A different independent architect reviews implementation.
6. At most one focused material correction is permitted, followed by full revalidation.
7. Optional polish cannot trigger another loop.
8. A second material failure or new product-direction need stops for the controller.

## 12. Design acceptance

1. Models interpret evidence but cannot author protocol identity or action authority.
2. Provider-visible synthesis and evaluator schemas contain no version fields.
3. The harness owns one immutable version envelope across every durable projection.
4. Existing v6 semantic and operational safety behavior remains unchanged.
5. Offline tests include adversarial provider-schema and envelope-consistency coverage.
6. One v7 batch is bounded below the remaining cumulative promotional-credit authority.
7. M4 cannot pass without four-profile real Nova Pro evidence and an independent final
   approval.
