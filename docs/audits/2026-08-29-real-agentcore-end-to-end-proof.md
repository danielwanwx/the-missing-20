# Real AgentCore end-to-end proof

Date: 2026-08-29

## Outcome

The Missing 20 completed a real AWS Bedrock AgentCore Runtime and Nova Pro advisory run against the synthetic supply-chain incident. Three specialist investigators completed, synthesis selected `RETRYABLE_MESSAGE`, and the evaluator returned `ACCEPT`.

The advisory result is deliberately reported as `PARTIAL`: the AI-authored synthesis cited 1 of the 5 admitted evidence records. The application independently validated all 5 authoritative records. The product does not insert missing citations into Nova's answer and does not claim that Nova validated every source.

The defensible product claim is:

> Real Nova agents investigated and identified the likely cause; deterministic application controls independently validated authoritative evidence and exclusively governed recovery.

## Real interaction proof

- Role chat used the deployed AgentCore runtime and returned a read-only current-state explanation with three authoritative citations.
- An operational request was classified as an authority-boundary question and explicitly refused preparation, approval, authorization, and execution.
- A prompt-injection attempt was rejected locally with HTTP 400 before the provider boundary.
- No agent or chat endpoint received business-write authority.

## Operational closure

The deterministic path prepared two separate recovery actions. Each required its own exact two-role quorum. The controlled executor restored ERP quantity to 100, reduced the retry queue to 0, released the invoice, and closed the incident. Verification passed and replay produced zero additional effects.

## Usage and disclosure

The recorded multi-agent investigation used 44,356 input tokens and 1,674 output tokens. The recorded role chat used 8,925 input tokens and 298 output tokens. The separate acceptance invocation recorded an estimated $0.0009296. At the repository's frozen Nova Pro price constants, the known token subtotal is $0.0489352 plus that acceptance invocation, or $0.0498648. Transport cycles without token totals and the authority-boundary chat without token totals are excluded; the known cumulative subtotal is at least $0.1749144, so this is an engineering estimate rather than an AWS invoice.

The redacted machine-readable evidence is in `artifacts/aws/2026-08-29-agentcore-runtime-proof.json`. AWS account IDs, request IDs, runtime session IDs, callback data, and credentials are not retained.
