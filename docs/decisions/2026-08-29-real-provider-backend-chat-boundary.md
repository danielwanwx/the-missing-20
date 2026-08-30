# Decision: explicit real-provider boundary for advisory chat

**Status:** Implemented as a bounded backend seam

## Decision

The local Decision Workspace accepts one explicit advisory provider mode:

- `scripted` keeps the deterministic Strands fixture for the offline demo;
- `bedrock` routes the existing harness to Nova Pro through Strands;
- `agentcore` routes the harness to an already deployed AgentCore Runtime.

The mode is selected with `MISSING20_AGENT_PROVIDER`. A misspelled mode fails
closed. The application does not silently fall back between modes.

## Chat boundary

`POST /api/v1/incidents/{incident_id}/chat` accepts an optional allowlisted
`agent_id`: `orchestrator`, `retryable_message_investigator`,
`short_shipment_investigator`, or `duplicate_posting_investigator`. Each
investigator receives a role-specific system context and an evidence allowlist.
The question is untrusted data; prompt-injection and role-escalation attempts are
rejected before provider invocation.

A chat turn runs one read-only investigator. It cannot synthesize a decision,
prepare an intent, record approval, execute recovery, or verify an effect. The
deterministic case classifier and the exact two-role human gate remain the only
operational authority.

## Provenance and degradation

Responses and durable operation events include redacted provider provenance,
selected agent, request/token/latency metadata, budget snapshots, and stable
error codes. Prompts, raw model responses, credentials, account identifiers, and
enterprise payloads are not exposed. Missing runtime configuration, malformed
responses, provider errors, and budget violations are visible as advisory
degradation with no operational effect and no provider fallback.

AgentCore transport is lazy: creating a session or selecting the mode performs
no network call. A real invocation occurs only when a caller explicitly selects
`bedrock` or `agentcore` and submits a bounded advisory operation.
