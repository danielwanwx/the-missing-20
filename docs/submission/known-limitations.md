# Known Limitations — Release Review

> **September 9 finalization status: NOT READY.** The 20-unit / USD 42,000
> evidence below belongs to the historical September 7 scenario. The separate
> R4 photo-receiving case (PO16/PR7) proves one Box posted and recovered after a
> lost acknowledgement, with verified Airtable/Slack handoffs. It has no linked
> invoice or customer fulfillment. R3 real multi-turn receiving remains FAILED;
> the September 6 8/8 and 15/15 results do not cover that path.
> See the [current finalization ledger](finalization-tracker.md) and
> [R4 scope audit](../audits/2026-09-09-r4-automatic-receiving-recovery-review.md).


The limitations below are part of the acceptance boundary and are shown deliberately.

| Area | Disposition | Consequence |
| --- | --- | --- |
| Historical Nova usefulness | September 6 bounded-set evidence only; new receiving FAILED | Real Strands/Nova passed 8/8 case variants and 15/15 multi-turn cases. This does not establish production accuracy, generalization, or an SLO. |
| AgentCore Runtime | `PROVEN` within the redacted boundary | The proof records Runtime deployment, invocation, and runtime logs. Trace delivery is a partial configuration warning; this is not a general service-level SLO claim. |
| AgentCore Gateway and Policy | `NOT_PROVEN` | No Gateway or Policy behavior is evidenced or claimed. |
| Cost accounting | Engineering estimate only | Per-run and matrix estimates are recorded in the cited artifacts. Transport cycles are not described as model calls. This is not an AWS invoice. |
| Advisory authority | Hard boundary | Models cannot classify state, grant, execute, verify, replay, or change policy. A provider failure is visible as `DEGRADED`; it does not fabricate content or write. |
| Production impact | Not measured | Five SaaS tenants contain purpose-built demo records, not customer production records. Delivery, billing, and USD 42,000 are observed demo-tenant accounting facts; causal revenue uplift, savings, reliability, and customer outcomes are not claimed. |
| External change transport | Poll + semantic versioning | The demo detects changes through bounded read-only polling, not provider webhooks. Unchanged polls retain their source sequence and create no UI motion; a semantic provider change creates one ordered `external.source.changed` ledger event. |
| Workspace controls | Isolated demo-tenant controls | Advisory tools remain read-only. Historical recovery uses a bound Manager decision. Receiving separately binds operator confirmation to one receipt and journals Airtable/Slack handoffs and relevant Jira exception updates. Demo personas are not production authentication or independent-human proof. |
| Runtime topology | Two proven paths | The historical case matrices and local UI use direct Strands Bedrock transport. AgentCore Runtime deployment/invocation is separate redacted evidence; the package does not imply the local UI currently routes through that Runtime. |
| Final release | Pending human gate | A source-repository push does not authorize a public video, hosted demo, or Devpost submission. |
| Credentials and data | Excluded | No credentials, employer/customer data, private incident, runbook, or confidential provenance is in scope. |

## Degraded behavior is a product feature

The provider failure is not silently converted into a successful AI claim. The system
keeps deterministic operational truth available, shows the advisory branch as
degraded, and exposes the missing usefulness evidence. If authoritative lifecycle
records are missing or invalid, the workspace fails closed and hides operational
state.

## Next evidence needed

Current demo finalization, receiving tests and related invoice tests are authorized by the
handoff. The current ledger tracks them. New subscriptions, production data/operations,
IAM expansion and destructive deletion require separate authorization. Final public
video/demo/Devpost release retains its preview gate; no real payment is allowed.
