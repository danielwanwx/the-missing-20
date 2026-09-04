# Real Agent Dashboard Optimization — Implementation Plan

**Design source:** `docs/superpowers/specs/2026-09-03-real-agent-dashboard-optimization-design.md`

## 1. Advisory contracts and validation

Create `agents/live_advisory.py` with a strict Pydantic response model and a
small service boundary. The contract owns the allowed dispositions, exact
citations, read-only status, failure types, and redacted provider metadata.
It validates that all cited IDs were actually returned by a source tool, that
no write was performed or claimed, and that the source/control tool trace is
complete. Add unit tests before connecting a model.

## 2. Source-scoped real Strands turn

Extend the real-matrix module to split each packet into ERP, Airtable, Celigo,
collaboration, and control-context payloads. Replace the single generic tool
with those named read-only tools. Use the existing BedrockNovaProFactory and
Strands structured-output support. The application, rather than prose parsing,
will validate the model result and record all tool calls and provider usage.

## 3. Matrix regression

Keep Golden outcomes, expected values, invariants, and post-execution effects
outside every model-visible tool payload. Update the deterministic rubric for
the structured contract. Add targeted unit tests for no-leakage and validation
failures, then run all 16 fixture cases plus the real live recovery case.

## 4. Fail-closed Dashboard gateway

Introduce a gateway owned by the local server that builds a fresh live packet,
runs the advisory service, and returns a stable response envelope. Replace only
the `/api/v1/agent-platform/ask` route; do not alter diagnose/approve/execute/
verify controls. Missing credentials, budgets, timeouts, invalid model output,
or provider errors return `AGENT_UNAVAILABLE` or `VALIDATION_FAILED`, never
the old `AgentPlatform.answer` fallback.

## 5. Compact real-agent UI

Adapt the existing chat renderer to show a real-agent card: availability,
disposition, cited source IDs, tool/source trace, and latency. Keep prose
minimal and clearly show unavailable state. No browser animation or Agent label
may be emitted without a returned gateway response.

## 6. Verification

- Focused Python tests for contract, source isolation, gateway failures, and
  route separation.
- Focused JS tests for real-agent / unavailable response rendering.
- Rerun the no-leak 17-case real matrix with its safety circuit breaker.
- Run the local dashboard smoke: successful real chat, forced unavailable chat,
  and assertions that chat did not mutate the deterministic recovery state.
- Run Ruff and the relevant existing test suites. Record unrelated pre-existing
  full-suite failures separately rather than masking them.
