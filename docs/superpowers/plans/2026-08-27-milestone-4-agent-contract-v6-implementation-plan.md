# Milestone 4 Agent Contract v6 Implementation Record

**Design:** `../specs/2026-08-27-milestone-4-agent-contract-v6-relation-aware-evidence-design.md`
**Owner:** Luna implementation worker
**Status:** Offline implementation approved; final real-provider gate returned terminal `BLOCK_M4`

## Scope completed

- Bumped the agent contract to `agent-contract/v6` and changed model claims to require
  one closed relation enum: `SUPPORTS_HYPOTHESIS`, `CONTRADICTS_HYPOTHESIS`, or
  `CONTEXT_ONLY`.
- Removed model-authored aggregate polarity, dissent, availability, provenance, and
  action fields from investigator and synthesis outputs.
- Added deterministic claim/evidence projections and an application-owned relation-aware
  dissent projection.
- Bumped the application policy to `action-policy/v2` and the immutable ledger to
  `coverage-ledger/v2`, including selected claim groups, conflict state, and stable
  outcome reason.
- Added `artifacts/agent/bedrock-failure-manifest-v2.json` as a redacted Bedrock
  failure/cost manifest. It records profile, assigned stage/role, validator code, and
  budget totals without model prose or raw evidence.
- Updated v3 prompts, scripted payloads, Golden v2 version metadata, and focused
  relation-aware regression tests.

## Offline verification target

The primary orchestrator must inspect the dirty diff and run the complete offline gates:
`make check`, Golden v1, Golden v2 scripted/safety, secret/path/claim scans, and
`git diff --check`. No AWS/provider call, spending, commit, push, or M5 progression is
part of this implementation pass.

## Review boundary

An independent Chief Architect owns the implementation gate. Only a material defect may
consume the single bounded correction allowance; optional polish does not reopen the
loop.
