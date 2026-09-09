# Release Evidence Matrix

> **September 9 finalization status: NOT READY.** The 20-unit / USD 42,000
> evidence below belongs to the historical September 7 scenario. The separate
> R4 photo-receiving case (PO16/PR7) proves one Box posted and recovered after a
> lost acknowledgement, with verified Airtable/Slack handoffs. It has no linked
> invoice or customer fulfillment. R3 real multi-turn receiving remains FAILED;
> the September 6 8/8 and 15/15 results do not cover that path.
> See the [current finalization ledger](finalization-tracker.md) and
> [R4 scope audit](../audits/2026-09-09-r4-automatic-receiving-recovery-review.md).


All business records in this release are purpose-built demo data. The approved hero
execution bundle writes to an isolated ERPNext demo tenant and is followed by fresh
provider reads. Evidence classes are intentionally not interchangeable.

| Claim | Evidence class | Status | What is actually demonstrated | Source |
| --- | --- | --- | --- | --- |
| Primary Dashboard → Investigation → Manager → verified recovery | `PROVEN` | PASS | One declared Manager approves or rejects the exact case-bound plan. The approved hero run performs one Manager-approved bounded execution bundle, then freshly rereads and exposes the exact Stock Entry, Sales Order, Delivery Note, Sales Invoice, Celigo receipt, and balanced ledgers. The compact manifest is SHA-256-bound to the committed raw API projection. This live capture does not claim a separate replay attempt. | `artifacts/audits/2026-09-07-current-hero-proof.json`, `artifacts/audits/2026-09-07-current-hero-live-snapshot.json`, `scripts/verify_current_release.py` |
| Legacy compatibility workspace and fail-closed degraded/invalid modes | `PROVEN` | PASS | The separate legacy browser smoke renders complete, degraded, and unavailable views with zero remote resources and scoped local synthetic controls. It is regression coverage, not the live hero execution path. | `artifacts/workspace/browser-smoke-v1.json` |
| Scripted Strands advisory with competing hypotheses, evidence gaps, citations, and uncertainty | `SCRIPTED_PROVEN` | PASS | Four synthetic profiles run twice with byte-identical traces; the orchestrator coordinates three fixed investigators, audited read tools, evidence handoffs, synthesis, and evaluation. Advisory output never enters policy. | `artifacts/golden/golden-v2.json` |
| Real Strands / Bedrock Nova investigation | `PROVEN` | PASS | Eight distinct ambiguous cases completed with all six bounded source/reconciliation tools; the matrix covers recovery-ready, deny, and needs-evidence outcomes. | `artifacts/agent/2026-09-06-hybrid-loop-8-case-real.json` |
| Real multi-turn human/Agent operation | `PROVEN` | PASS | Fifteen cases and 45 back-and-forth turns completed; the matrix includes one approved recovery and one rejected recovery while preserving read-only model authority. | `artifacts/agent/2026-09-06-human-agent-dialogue-matrix-final-v2.json` |
| Connected demo-source reads | `PROVEN` | PASS | The console reads scoped records from ERPNext, Airtable, Celigo, Jira, and Slack. The Agent packet attaches their fresh read receipts and exact record IDs to the corresponding Strands tools. These readers carry no write authority; the separate ERPNext executor owns the sole Manager-gated write path. | `src/the_missing_20/adapters/live_advisory_gateway.py`, `tests/test_live_advisory_gateway.py` |
| Current connected case through real Strands / Bedrock Nova | `PROVEN` | PASS | The live ERPNext/SaaS packet completed through six scoped read and reconciliation tools, cited the connected record IDs, returned `RECOVERY_READY`, and truthfully recorded `write_performed: false`. | `artifacts/agent/real-strands-matrix-source-driven-final.json` |
| Stable real Nova production usefulness | `NOT_PROVEN` | NOT_PROVEN | Bounded demo-set passes do not establish production accuracy, generalization, or an SLO. | `docs/submission/known-limitations.md` |
| Real AgentCore role chat | `PROVEN` | PASS | A deployed Runtime session answered a role-specific current-state question with three citations and no prepare, approve, authorize, execute, or business-write capability. | `artifacts/aws/2026-08-30-devpost-real-acceptance.json` |
| AgentCore Runtime deployment, invocation, and observability | `PROVEN` | PASS | The redacted proof records a READY Runtime deployment, a completed invocation boundary, runtime logs, and trace-delivery status. | `artifacts/aws/2026-08-29-agentcore-runtime-proof.json`, `artifacts/aws/m6-proof-bundle-v1.json` |
| AgentCore Gateway and Policy | `NOT_PROVEN` | NOT_PROVEN | No Gateway or Policy behavior is asserted by this package. | `artifacts/aws/2026-08-29-agentcore-runtime-proof.json`, `artifacts/aws/m6-proof-bundle-v1.json` |
| Nova behavior across the bounded evaluated demo set | `PROVEN` | PASS | The historical September 6 bounded evaluation passed 8/8 case variants and 15/15 multi-turn cases. This is demo-set evidence, not a production accuracy or generalization claim. | `artifacts/agent/2026-09-06-hybrid-loop-8-case-real.json`, `artifacts/agent/2026-09-06-human-agent-dialogue-matrix-final-v2.json` |
| Model authority to approve, execute, verify, or replay an operational action | `PROVEN` | PASS | Advisory records carry the no-write boundary; deterministic code and one declared Manager persona own the Manager-gated ERPNext demo-tenant execution bundle. The legacy two-role harness remains a separate, stricter regression proof. | `artifacts/audits/2026-09-07-current-hero-proof.json`, `artifacts/workspace/authority-b-lifecycle-v1.json` |

## Reading rule

`PROVEN` means the cited record and its deterministic validators pass. It does not
mean every adjacent product capability is shipped. `SCRIPTED_PROVEN` means the local
synthetic script is reproducible, not that a real provider behaved the same way.
`NOT_PROVEN` is a deliberate disclosure, not an omission.

## Cost and provenance

The package-generation and demo commands add zero provider calls and zero AWS cost.
Provider costs recorded in the cited artifacts are engineering estimates, not an AWS
invoice. Transport cycles are not described as model calls. Business inputs are
purpose-built synthetic demo records; the approved execution bundle writes to the
isolated external ERPNext demo tenant, followed by fresh provider reads. It is not a
production-data or production-impact claim. Browser and artifacts expose record
identifiers, never credentials.
