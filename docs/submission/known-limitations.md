# Known Limitations — Release Review

> **September 10 finalization status: core R4 demo verified; submission NOT READY.**
> The same PO16/PR7 receiving case now has a submitted supplier invoice, PI8:
> 1 Box / USD 50, balanced ERP accounting, unchanged stock and no payment.
> Six actual UI turns using native Strands history passed independent semantic
> review. This is one bounded demo, not the full repeated complex-case matrix.
> Customer fulfillment, final video/materials and judge-access packaging remain open.
> Historical 20-unit / USD 42,000 and September 6 results below retain their own scope.
> See the [current finalization ledger](finalization-tracker.md) and
> [R4 business and conversation audit](../audits/2026-09-10-r4-billing-native-dialogue-review.md).


The limitations below are part of the acceptance boundary and are shown deliberately.

| Area | Disposition | Consequence |
| --- | --- | --- |
| Historical Nova usefulness | Historical September 6 bounded set; new R4 one-sequence demo verified | Real Strands/Nova passed 8/8 case variants and 15/15 multi-turn cases. This does not establish production accuracy, generalization, or an SLO. |
| AgentCore Runtime | `PROVEN` within the redacted boundary | The proof records Runtime deployment, invocation, and runtime logs. Trace delivery is a partial configuration warning; this is not a general service-level SLO claim. |
| AgentCore Gateway and Policy | `NOT_PROVEN` | No Gateway or Policy behavior is evidenced or claimed. |
| Native receiving conversation | One six-turn real R4 UI sequence | Uses native SDK snapshot history and current sources before/after supplier billing. Structured citation attachments, long-chat compression and repeated held-out acceptance remain open. |
| Supplier billing | Same R4 receipt, one disclosed synthetic USD 50 bill | PI8 is submitted/unpaid; actual GL/SLE checked independently. The app financial badge remains unautomated. This does not close the remaining 39 Box or customer fulfillment. |
| Re-reading the submitted invoice | Known repeat-reconciliation defect | PI8 passed the business validator again, but generated ERP metadata changed its raw digest and triggered a retained review hold. Its submission and accounting remain proved; the current UI reports the later reconciliation problem. Journal recovery is deferred. |
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
