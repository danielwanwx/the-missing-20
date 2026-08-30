# Private Evidence Matrix

All claims in this matrix are scoped to synthetic data and the local private package.
Evidence classes are intentionally not interchangeable.

| Claim | Evidence class | Status | What is actually demonstrated | Source |
| --- | --- | --- | --- | --- |
| Detector, deterministic policy, exact per-action quorum, controlled effects, authoritative reread, verification, and replay | `PROVEN` | PASS | A fresh local lifecycle closes two distinct actions and replay adds zero effects. | `artifacts/workspace/authority-b-lifecycle-v1.json`, `artifacts/workspace/decision-workspace-complete.json` |
| Complete read/advisory workspace and fail-closed degraded/invalid modes | `PROVEN` | PASS | Browser smoke renders complete, degraded, and unavailable views with zero remote resources; only scoped local synthetic structured controls can request recovery. | `artifacts/workspace/browser-smoke-v1.json` |
| Scripted Strands advisory with competing hypotheses, evidence gaps, citations, and uncertainty | `SCRIPTED_PROVEN` | PASS | Four synthetic profiles run twice with byte-identical traces; the orchestrator coordinates three fixed investigators, audited read tools, evidence handoffs, synthesis, and evaluation. Advisory output never enters policy. | `artifacts/golden/golden-v2.json` |
| Real Bedrock/Nova advisory integration | `PROVEN` | PARTIAL | The fresh redacted acceptance run shows three investigators, a selected likely cause, a real read-only role chat, and visible incomplete citation closure. AI-authored citation closure covered 1/5 admitted records; application validation covered 5/5. | `artifacts/aws/2026-08-30-devpost-real-acceptance.json`, `artifacts/aws/m6-proof-bundle-v1.json` |
| Real AgentCore role chat | `PROVEN` | PASS | A deployed Runtime session answered a role-specific current-state question with three citations and no prepare, approve, authorize, execute, or business-write capability. | `artifacts/aws/2026-08-30-devpost-real-acceptance.json` |
| AgentCore Runtime deployment, invocation, and observability | `PROVEN` | PASS | The redacted proof records a READY Runtime deployment, a completed invocation boundary, runtime logs, and trace-delivery status. | `artifacts/aws/2026-08-29-agentcore-runtime-proof.json`, `artifacts/aws/m6-proof-bundle-v1.json` |
| AgentCore Gateway and Policy | `NOT_PROVEN` | NOT_PROVEN | No Gateway or Policy behavior is asserted by this package. | `artifacts/aws/2026-08-29-agentcore-runtime-proof.json`, `artifacts/aws/m6-proof-bundle-v1.json` |
| Stable real Nova investigation usefulness | `NOT_PROVEN` | NOT_PROVEN | The observed real result is partial (AI 1/5, application 5/5); it is not enough to claim stable real-model usefulness. | `artifacts/agent/authority-b-usefulness-proof-v1.json`, `artifacts/aws/m6-proof-bundle-v1.json` |
| Model authority to grant, execute, verify, or replay an operational action | `PROVEN` | PASS | Advisory records carry the no-write boundary; deterministic code and two scripted simulated role principals own the local controlled effect (no auth claim). | `artifacts/agent/authority-b-advisory-v1.json`, `artifacts/workspace/authority-b-lifecycle-v1.json` |

## Reading rule

`PROVEN` means the cited record and its deterministic validators pass. It does not
mean every adjacent product capability is shipped. `SCRIPTED_PROVEN` means the local
synthetic script is reproducible, not that a real provider behaved the same way.
`NOT_PROVEN` is a deliberate disclosure, not an omission.

## Cost and provenance

The package-generation and demo commands add zero provider calls and zero AWS cost.
The separate 2026-08-30 acceptance run added an estimated `$0.0491432` for one real
multi-agent investigation and one real role chat. The cumulative known estimate is
`$0.2240576`. Transport cycles are not described as model calls. These are engineering
estimates, not an AWS invoice.
All package records are synthetic or redacted evidence. No employer/customer source,
credential, or private enterprise record is admitted.
