# Autonomous Milestone Delivery Loop

**Status:** User-approved operating model
**Applies to:** Milestones 4, 5, and 6
**Product owner:** Weixiang Wan
**Delivery owner:** Primary Codex orchestrator

## 1. Decision

The product owner acts as the product-direction owner and final judge, not as a code,
specification, or milestone reviewer. The agent team owns the complete engineering loop:

```text
product direction
  -> specialist specification
  -> independent architecture gate
  -> implementation plan
  -> Luna implementation
  -> primary code and test review
  -> real end-to-end verification
  -> independent domain and competition review
  -> milestone evidence record
  -> next milestone
```

The orchestrator does not pause for routine user approval between these stages. It
returns to the product owner only when a human gate is unavoidable or when the product is
ready to be judged as a complete experience.

## 2. Agent responsibilities

| Role | Responsibility | Cannot do |
|---|---|---|
| Primary orchestrator | Own scope, sequencing, evidence, cost limits, and final acceptance | Delegate final accountability |
| Specification agent | Convert product direction into typed behavior, safety rules, and acceptance tests | Implement or approve its own specification |
| ERP/SAP domain architect | Validate supply-chain realism, data lineage, exception semantics, and business value | Weaken evidence requirements to simplify a demo |
| System architect | Review boundaries, failure modes, security, AWS fit, and milestone readiness | Review its own implementation |
| Planner | Break an approved specification into bounded, testable slices | Expand product scope |
| Luna implementer | Implement only the approved slice and its tests | Commit, push, call AWS, or alter product direction |
| QA and E2E verifier | Run deterministic, adversarial, restart/replay, browser, and real-provider checks | Convert a failed check into a narrative PASS |
| Competition judge | Score demo clarity, technical depth, originality, impact, and five-minute presentation readiness | Approve while a material blocker remains |

One agent may perform only one authority role within a gate. The implementer never
approves its own work. The orchestrator inspects actual changes and evidence instead of
accepting agent summaries.

## 3. Milestone loop

Every milestone uses the same bounded contract.

### Goal

Produce one user-visible, end-to-end capability with executable proof rather than a
partial subsystem or disconnected report.

### Input scope

- Approved product direction and existing specifications.
- Public-safe synthetic ERP, warehouse, integration, invoice, and logistics data.
- Existing repository code, tests, AWS credit, and competition requirements.
- No employer code, incidents, data, runbooks, credentials, or internal terminology.

### Execute

1. A specification agent writes the milestone contract and acceptance tests.
2. Domain and system architects independently review it.
3. The planner produces small implementation slices with explicit ownership.
4. Luna implements one slice at a time.
5. The primary orchestrator inspects the diff and runs local gates.
6. QA runs realistic end-to-end and adversarial flows from fresh state.
7. Approved real-provider or browser proof runs only after offline gates pass.
8. Domain, architecture, and competition reviewers issue final milestone verdicts.
9. The orchestrator records evidence and advances automatically when every gate passes.

### Checks

- Specification and version consistency.
- Unit, type, lint, integration, Golden, restart, and replay tests.
- Real data movement through persisted state, not UI-only simulation.
- Real model/cloud/browser proof where the milestone claims it.
- Secret, local-path, privacy, cost, and destructive-action scans.
- No material P0/P1 finding from independent reviewers.
- No unsupported product, AWS, performance, or safety claim.

### Feedback rules

- Each milestone has one initial specification and at most one architecture-reviewed
  revision. An architecture rebaseline consumes that same single revision; it does not
  create a new revision budget.
- Each implementation slice permits one focused Luna correction, followed by primary
  verification.
- Failed real-provider output caused by duplicated model authority: move that authority
  to the deterministic tool or application boundary only when the change preserves the
  product outcome and safety model and the milestone's one specification revision remains.
- Each accepted contract permits one real-provider or browser run. A second run is
  allowed only when recorded infrastructure failure proves the product path was never
  exercised; model, validator, or product-output failure consumes the run.
- A material failure after these budgets marks the milestone `BLOCKED` with evidence.
  Agents may not reinterpret it as PASS, start another tactic, commit or push it as
  complete, or advance to a dependent milestone.
- Optional polish never blocks a milestone and is recorded for final hardening.

### Records

Each milestone leaves one evidence bundle containing:

- approved specification and implementation plan;
- source and dependency version matrix;
- test and Golden results;
- real-provider/browser trace and bounded cost record where applicable;
- reviewer verdicts and resolved material findings;
- demo path, screenshots, and known limitations;
- commit and remote link only after the final gate passes.

### Stop conditions

Success means every acceptance gate passes and the user-visible capability can be
demonstrated from clean state. Failure means a human gate is required, the product
direction must change, the cost boundary would be exceeded, or the required external
capability is unavailable. A milestone that exhausts its specification, correction, or
real-provider attempt budget stops as `BLOCKED`; the user is contacted only when
resolution requires a product-direction decision, external account action, or expanded
cost or authority.

## 4. Human gates

The product owner is involved only for:

- product audience, problem, business value, or demo-story changes;
- login, MFA, CAPTCHA, account ownership, or credential entry that no agent can perform;
- public submission, legal attestation, payment, or spending outside an already approved
  promotional-credit cap;
- destructive or irreversible external action;
- a genuine fork where two viable product directions create materially different user
  outcomes;
- final ready-to-judge delivery.

Routine specifications, plans, code changes, test repairs, naming inside existing product
direction, implementation trade-offs, and reviewer comments are not human gates.

## 5. Milestone boundaries

### Milestone 4: trustworthy agent diagnosis loop

Deliver a real Strands multi-agent investigation that turns synthetic enterprise facts
into an evidence-grounded assessment, persists it, passes human approval and controlled
execution, rereads authoritative state, replays the ledger, and reaches the correct
closed or protected outcome. Golden v1 and Golden v2 must pass, including one bounded
real-model proof.

### Milestone 5: live operations and decision workspace

Deliver the user-facing live flow: continuously changing supply-chain nodes, automatic
incident detection, visible agent handoff, evidence-linked diagnosis, human decision,
controlled action, and post-action recovery in one coherent interface. The primary
scenario and safety counterexamples must be reproducible from fresh synthetic data.

### Milestone 6: AWS proof and competition package

Deploy the accepted workflow on the minimum credible AWS/AgentCore architecture, prove
the services actually used, connect end-to-end observability, and finish the public
repository, architecture evidence, five-minute demo, video script, screenshots, and
Devpost submission material. Unsupported AWS features are labeled `NOT_PROVEN` rather
than simulated.

## 6. Ready-to-judge contract

The product owner receives the next review only when all of the following are true:

1. One documented command or URL starts the complete demo.
2. The main Missing 20 case runs from live detection to verified recovery.
3. Genuine shortage, missing evidence, stale approval, and duplicate execution stop
   safely and are visible in the product.
4. Golden suites and independent reviewers pass with no material blocker.
5. The deployed/cloud claims match saved traces and cost records.
6. The interface tells the five-minute story without requiring code explanation.
7. The public repository contains no secrets, private data, absolute local paths, or
   misleading claims.
8. A competition judge can understand the problem, agentic differentiation, safety,
   business impact, and result from the demo alone.

At that point the product owner judges the experience and product direction. They are
not asked to review implementation details or reconcile agent feedback.
