# Private Evidence Matrix

All claims in this matrix are scoped to synthetic data and the local private package.
Evidence classes are intentionally not interchangeable.

| Claim | Evidence class | Status | What is actually demonstrated | Source |
| --- | --- | --- | --- | --- |
| Detector, deterministic policy, exact per-action quorum, controlled effects, authoritative reread, verification, and replay | `PROVEN` | PASS | A fresh local lifecycle closes two distinct actions and replay adds zero effects. | `artifacts/workspace/authority-b-lifecycle-v1.json`, `artifacts/workspace/decision-workspace-complete.json` |
| Complete read/advisory workspace and fail-closed degraded/invalid modes | `PROVEN` | PASS | Browser smoke renders complete, degraded, and unavailable views with zero remote resources; only scoped local synthetic structured controls can request recovery. | `artifacts/workspace/browser-smoke-v1.json` |
| Scripted Strands advisory with competing hypotheses, evidence gaps, citations, and uncertainty | `SCRIPTED_PROVEN` | PASS | Four synthetic profiles run twice with byte-identical traces; advisory output never enters policy. | `artifacts/golden/golden-v2.json` |
| Real Bedrock/Nova integration boundary | `PROVEN` | DEGRADED | The consumed record proves provider connectivity and observable degraded handling only. | `artifacts/aws/m6-proof-bundle-v1.json`, `artifacts/agent/authority-b-failure-v1.json` |
| Stable real Nova investigation usefulness | `NOT_PROVEN` | NOT_PROVEN | The real attempt did not produce a stable useful advisory trace; no positive claim is made. | `artifacts/agent/authority-b-usefulness-proof-v1.json`, `artifacts/aws/m6-proof-bundle-v1.json` |
| AgentCore Runtime, Gateway, Policy, Observability, and deployment | `NOT_PROVEN` | NOT_PROVEN | No AgentCore capability is evidenced by this offline package. | `artifacts/aws/m6-proof-bundle-v1.json` |
| Model authority to grant, execute, verify, or replay an operational action | `PROVEN` | PASS | Advisory records carry the no-write boundary; deterministic code and two scripted simulated role principals own the local controlled effect (no auth claim). | `artifacts/agent/authority-b-advisory-v1.json`, `artifacts/workspace/authority-b-lifecycle-v1.json` |

## Reading rule

`PROVEN` means the cited record and its deterministic validators pass. It does not
mean every adjacent product capability is shipped. `SCRIPTED_PROVEN` means the local
synthetic script is reproducible, not that a real provider behaved the same way.
`NOT_PROVEN` is a deliberate disclosure, not an omission.

## Cost and provenance

The package adds zero provider calls and zero AWS cost. The previously consumed real
Nova estimate is `$0.014116`, cumulative estimate `$0.1250496`, and hard cap `$0.60`.
All package records are synthetic or redacted evidence. No employer/customer source,
credential, or private enterprise record is admitted.
