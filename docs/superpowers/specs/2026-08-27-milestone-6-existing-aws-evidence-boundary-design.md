# Milestone 6 Existing AWS Evidence Boundary

**Status:** approved for bounded implementation
**Authority:** M5 `APPROVE_M5` and the accepted Authority-B rebaseline
**Scope:** local, byte-stable proof composition from existing redacted artifacts only

## Loop contract

**Goal:** provide a truthful M6 integration proof bundle that makes the minimum AWS /
AgentCore boundary auditable without creating a cloud resource, invoking a provider, or
claiming an unproven AgentCore capability.

**Inputs:** the already-approved synthetic M5 lifecycle bundle, Golden v2, the frozen
redacted Authority-B preflight/attempt/failure/advisory/usefulness records, and the
synthetic fixture digest used by the lifecycle validator. No new source data is
admitted. No network, AWS, provider, employer, or production material is in scope.

**Execute:** validate every input at its public contract, verify fixed byte digests,
cross-check identity/status/cost relations, and compose a canonical
`M6AWSProofBundle/v1`. A read-only workspace panel may display the bundle's claims.

**Checks:** source existence and schema, fixed source digests, lifecycle validation,
scripted Golden proof, real-provider degraded integration evidence, cost/request caps,
truth-boundary claim scan, proof digest, mutation fail-closed behavior, and local
browser smoke. The builder never creates an AWS client.

**Feedback:** one focused material correction is allowed. A malformed, contradictory,
or digest-mismatched source fails closed. A second reproducible material defect stops
the milestone; optional AgentCore deployment, SDK, IaC, or presentation polish is
deferred.

**Stop:** independent M6 implementation approval, or stop/report on missing evidence,
source contradiction, budget expansion, new permission, or public/destructive action.

## Authority and evidence boundary

| Capability or claim | Status | Evidence class | Authority |
| --- | --- | --- | --- |
| Local deterministic lifecycle, policy, quorum, execution, verification, replay | `PROVEN` | `PROVEN` | deterministic application |
| Scripted Strands investigation trace | `SCRIPTED_PROVEN` | `SCRIPTED_PROVEN` | advisory only |
| Real Bedrock/Nova connectivity and degraded-outcome observability | `PROVEN` | `PROVEN` (integration only) | advisory only |
| Stable real Nova usefulness | `NOT_PROVEN` | `NOT_PROVEN` | none |
| AgentCore Runtime/Gateway/Policy/Observability/deployment | `NOT_PROVEN` | `NOT_PROVEN` | none |

The advisory branch has no write authority. It cannot classify an operational state,
grant an action, invoke a controlled executor, verify an effect, or change replay
semantics. `PROVEN` for provider integration means only that the previously consumed
redacted attempt and its degraded result are internally consistent and observable; it
does not mean that the provider produced useful investigation content.

## Input and digest contract

The proof is composed from these repository-relative sources and their reviewed raw
SHA-256 bytes:

- `artifacts/golden/golden-v2.json`;
- `artifacts/agent/authority-b-preflight-v1.json`;
  `authority-b-attempt-claim-v1.json`; `authority-b-failure-v1.json`;
  `authority-b-advisory-v1.json`; `authority-b-usefulness-proof-v1.json`;
- `artifacts/workspace/authority-b-lifecycle-v1.json`;
- `fixtures/scenarios/retryable-document-lock.json`.

The builder records every source digest and requires it to equal the fixed approved
anchor. It also validates the source's declared schema. A missing file, malformed JSON,
unknown schema, byte change, invalid nested contract, or inconsistent cross-source
identity raises a proof error. Rehashing a changed source cannot make it acceptable.

The bundle is canonical JSON (`sort_keys`, compact separators, no NaN) with a final
newline. `proof_digest` is SHA-256 over the canonical bundle excluding that field.
Loading rechecks both the bundle digest and every source anchor.

## Cross-source acceptance semantics

The bundle is promotable only when all of the following are true:

1. The lifecycle bundle validates through the existing deterministic validator, ends in
   `CLOSED`, contains the two distinct actions/effects, and proves zero-effect replay.
2. Golden v2 has deterministic safety `PASS`, four byte-identical scripted profiles,
   and a scripted advisory `PASS`; its promotion metadata explicitly says a plain pass
   does not imply real-provider usefulness.
3. The Authority-B preflight is a read-only `PASS` with zero provider calls and no
   compatibility probe; its model/region match the consumed attempt.
4. The attempt claim is the frozen Authority-B claim with the reviewed prior cost and
   request/token caps. The redacted real outcome is `DEGRADED`, carries a provider
   failure, matches the advisory identity, and stays under the frozen incremental and
   cumulative budget.
5. The advisory record has the immutable non-authoritative label and no hypotheses,
   citations, incident report, or operational grant after failure. The usefulness proof
   remains `FAIL` / `NOT_PROVEN` and explicitly has `operational_authority: false`.
6. The capability table contains explicit `NOT_PROVEN` records for every AgentCore
   capability and an explicit `NOT_PROVEN` record for stable real Nova usefulness.
7. Every claim has a source reference and an evidence class. Advisory/provider claims
   cannot be labeled operational authority, write authority, or stable usefulness.
8. The bundle records zero new provider/AWS calls and zero new cost; the existing
   cumulative estimate remains `0.1250496` USD and the hard cap remains `0.60` USD.

## Artifact and workspace contract

`artifacts/aws/m6-proof-bundle-v1.json` is the only M6 proof artifact. It contains the
source digest ledger, deterministic lifecycle proof, scripted advisory proof, real
provider integration/degradation proof, explicit AgentCore capability dispositions,
cost/request boundary, claim ledger, and canonical proof digest.

The Decision Workspace may display a read-only M6 integration panel sourced from this
artifact. The panel must preserve all three evidence classes, display real integration
as degraded/observed, display stable usefulness and AgentCore as `NOT PROVEN`, and
repeat that model output is advisory with no write authority. It must not add an
approval or execution control or derive an operational decision from the panel.

## Tests and non-goals

Unit tests cover valid composition, byte stability, missing/malformed source,
source-digest mismatch, contradictory status/cost/identity, bundle rehash mutation,
and claim-scan violations. Workspace/browser smoke covers the complete, degraded, and
fail-closed views and asserts no remote resource or active control.

M6 does not install or invoke AgentCore, deploy infrastructure, make an AWS/provider
call, spend credit, add permissions, introduce authentication, publish, commit, push,
record a video, submit Devpost, or claim stable real Nova usefulness.
