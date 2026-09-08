# As-Built Architecture

The Missing 20 is an evidence-first incident-control loop. Agents investigate;
deterministic code decides whether an effect is admissible; a Manager retains the
release decision; the executor proves the result with a fresh reread.

Open the validated architecture artifact:

- [Interactive architecture](the-missing-20-live-architecture.html)
- [Architecture source](the-missing-20-live-architecture-showcase.json)
- [Light review capture](the-missing-20-live-architecture.visual-check.1440x900.light.png)

## Runtime path

1. **Observe.** ERPNext, Airtable, Celigo, Jira, and Slack adapters expose scoped,
   read-only evidence for the current demo tenant.
2. **Detect.** The control plane admits an incident only from typed source facts and
   publishes ordered events over SSE.
3. **Investigate.** A Strands orchestrator runs the six bounded source and reconciliation tools, reconciles conflicting
   records, compares causes, and emits structured findings plus evaluator feedback.
4. **Control.** Deterministic policy independently checks the case version, evidence
   tuple, business keys, recovery scope, and invariants. Model output is not policy
   input.
5. **Decide.** The primary UI records one declared Manager decision bound to the plan
   digest and current case version. Rejecting the plan creates no effect.
6. **Execute.** The isolated ERPNext demo-tenant executor accepts one scoped
   idempotency key and applies only the approved quality-release and customer
   fulfillment scope. The resulting chain is bound to its Stock Entry, Sales Order,
   Delivery Note, and Sales Invoice; stale or conflicting requests are refused.
7. **Verify.** Fresh ERPNext and integration-receipt reads must prove 20 available,
   20 delivered, the customer order completed, USD 42,000 billed, balanced Stock/GL
   entries, and the exact Celigo receipt. Deterministic tests cover idempotent replay;
   the committed live capture proves one Manager-approved bounded execution bundle
   producing the captured record set and does not claim a live replay.
8. **Explain.** The Dashboard and Investigation views project the same ledger, live
   source parameters, Agent telemetry, human decision, and resolution packet.

## Authority boundaries

| Boundary | May do | May not do |
| --- | --- | --- |
| Strands / Nova advisory | Read scoped evidence, call approved tools, compare hypotheses, explain uncertainty | Approve, mutate enterprise state, mark a case verified |
| Deterministic policy | Validate facts, invariants, scope, and recovery eligibility | Invent missing evidence or inherit a model conclusion |
| Manager gate | Approve or reject the current bound plan | Approve a stale case version or a different scope |
| Controlled executor | Apply the approved idempotent scope in the isolated external ERPNext demo tenant | Perform an arbitrary write or silently retry a different effect |
| Verifier | Reread authoritative state and close only proven postconditions | Treat an optimistic response as completion |

## Evidence status

| Capability | Current status |
| --- | --- |
| Live local incident API, ordered SSE, SQLite ledger, source projections | **PROVEN** |
| Primary single-Manager, case-bound ERPNext demo-tenant recovery and rejection paths | **PROVEN** |
| Bounded live execution bundle, authoritative reread, verified closure | **PROVEN** |
| Idempotent replay behavior | **PROVEN** in deterministic regression; not separately replayed in the committed live capture |
| Strands source-tool investigation, structured synthesis, evaluation, telemetry | **PROVEN** in the controlled local/real-provider test matrix |
| AgentCore Runtime deployment, real invocation, logs, read-only role chat | **PROVEN** within redacted evidence |
| Stable Nova usefulness across production incidents | **NOT PROVEN**; no such claim is made |
| AgentCore Gateway / Policy | **NOT PROVEN**; no such claim is made |
| Production business impact or production enterprise data | **NOT PROVEN**; all competition cases are synthetic |

## Two approval models, deliberately separated

The current competition experience follows the product decision: one Manager reviews
and releases one tightly bound recovery packet. The repository also contains a legacy
Authority-B lifecycle harness with exact two-role, per-action attestations. That harness
remains useful security regression evidence, but it is not shown as if the primary UI
requires two people. This distinction prevents the documentation from contradicting
the product judges actually operate.
