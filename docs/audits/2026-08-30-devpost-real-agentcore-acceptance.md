# Devpost real AgentCore acceptance

Date: 2026-08-30

## Result

The deployed Amazon Bedrock AgentCore Runtime reported `READY` on its `DEFAULT`
endpoint. A fresh synthetic incident was created in an isolated local ledger and the
application ran its AgentCore provider path without fallback or retry.

Three Strands investigators completed, synthesis selected `RETRYABLE_MESSAGE`, and the
evaluator returned `ACCEPT`. The result remains deliberately `PARTIAL`: the model's
synthesis cited one of five admitted records, while deterministic application code
independently validated all five authoritative records. This preserves the project's
core authority boundary instead of repairing or overstating the model answer.

A separate role-specific question was then sent through the same real AgentCore path:

> What happened to the missing 20 units, which current evidence supports that
> conclusion, and what should the operator do next?

The `retryable_message_investigator` returned a current-case explanation with three
citations (ERP receipt, failed-message queue, and warehouse), `read_only=true`, and
`ADVISORY_NOT_OPERATIONAL_DECISION`. No recovery, approval, authorization, or business
write was available to the chat path.

## Usage and cost

| Operation | Input tokens | Output tokens | Transport cycles | Estimated cost |
| --- | ---: | ---: | ---: | ---: |
| Multi-agent investigation | 44,355 | 1,673 | 23 | $0.0408376 |
| Role chat | 8,954 | 357 | 5 | $0.0083056 |
| **New total** | **53,309** | **2,030** | **28** | **$0.0491432** |

The estimate uses the project's frozen Nova Pro rates of $0.80 per million input
tokens and $3.20 per million output tokens. Adding the prior known subtotal of
$0.1749144 yields a cumulative known estimate of `$0.2240576`. These are engineering
estimates, not an AWS invoice; transport cycles are not described as model calls.

## Public claim boundary

- **Proven:** AgentCore Runtime deployment/readiness/invocation, three-role real
  investigation, read-only role chat, application-side authoritative validation.
- **Partial:** real Nova investigation usefulness; AI citation closure is 1/5.
- **Not proven:** stable real-model usefulness, AgentCore Gateway/Policy, production
  business impact, or production data.

The public-safe machine-readable summary is
[`artifacts/aws/2026-08-30-devpost-real-acceptance.json`](../../artifacts/aws/2026-08-30-devpost-real-acceptance.json).
Runtime ARN, AWS account ID, credentials, session credentials, and the local deployment
configuration are intentionally excluded.
