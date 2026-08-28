# As-Built Architecture

This diagram describes the implementation in this repository. It intentionally excludes
unimplemented AgentCore, DynamoDB, Cognito, and KMS components.

```mermaid
flowchart LR
    ES["Synthetic enterprise records<br/>ERP · warehouse · queue · invoice"]
    D["Discrepancy detector<br/>100 expected · 80 recorded · 20 missing"]
    K["Read-only synthetic knowledge<br/>runbooks · evidence"]
    A["Strands agent harness<br/>competing hypotheses · synthesis · evaluation"]
    N["Amazon Bedrock Nova Pro<br/>degraded integration evidence"]
    W["Guided decision workspace<br/>complete · degraded · fail-closed replay"]
    P["Deterministic policy<br/>evidence integrity · action eligibility"]
    H["Exact two-role quorum<br/>per-action synthetic attestations"]
    X["Controlled executor<br/>fresh read · bounded effect · idempotency"]
    V["Verifier and replay<br/>postconditions · zero-effect replay"]
    L[("SQLite case and effect ledger")]

    ES -->|read synthetic records| D
    D -.->|read-only case context| A
    K -.->|retrieve guidance| A
    A -.->|advisory model calls| N
    A -.->|hypotheses and uncertainty| W

    D -->|admitted evidence| P
    P -->|eligible action intent| H
    H -->|signed local grant| X
    X -->|synthetic bounded effect| ES
    X -->|execution receipt| V
    ES -->|fresh authoritative reread| V
    V -->|verification and replay record| L
    L -->|persisted lifecycle proof| W

    subgraph AUTH["Deterministic write-authority boundary"]
        P
        H
        X
        V
        L
    end
```

## Evidence boundary

| Component | Current evidence |
| --- | --- |
| Detection, policy, exact quorum, execution, verification, and replay | Proven locally with synthetic data |
| Strands multi-agent orchestration and tools | Implemented; useful hero trace is scripted synthetic proof |
| Amazon Bedrock Nova Pro | Connectivity and degraded-outcome observability only |
| Stable useful real-provider investigation | Not proven |
| AgentCore Runtime, Gateway, Policy, Observability, or deployment | Not implemented and not claimed |

## Authority rule

Agent output can propose hypotheses, retrieve knowledge, identify evidence gaps, and
prepare an explanation. It cannot classify authoritative state, authorize an action,
execute an effect, verify a result, or replay an operation. Those responsibilities stay
inside deterministic code and require exact two-role approval before any synthetic
effect is applied.
