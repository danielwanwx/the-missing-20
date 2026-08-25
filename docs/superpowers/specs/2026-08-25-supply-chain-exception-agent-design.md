# Supply Chain Exception Resolution Agent Design

**Status:** Ready for user review  
**Date:** 2026-08-25  
**Implementation strategy:** Hybrid vertical slice  
**Competition:** AWS Agents for Humans Hackathon 2026

## 1. Decision and source of truth

This specification freezes Architecture v4.2 as the authoritative product direction.

The primary demo is a synthetic receipt-processing failure that creates an ERP goods-to-invoice mismatch. The system investigates the mismatch, obtains two role-specific human approvals, performs two tightly bounded actions, verifies the authoritative state after each action, and closes the case only when the receipt and invoice states are both correct.

This decision supersedes the earlier comparison report where it recommended a genuine short shipment as the primary demo and a single consequential action. Genuine short shipment and already-posted receipt are retained only as safety counterexamples. Price-change, supplier-claim, payment, write-off, and generalized ERP workflows are outside this implementation.

## 2. Product definition

### One-sentence pitch

CloseLoop detects when physical receipt, ERP receipt, and invoice records disagree, uses evidence-grounded agents to determine why, and carries the case through controlled human approval and verified recovery.

### Plain-language explanation

A warehouse received 100 items, but the accounting system shows only 80. CloseLoop checks what happened to the missing 20, shows the evidence to the right employees, performs only the exact actions they approve, and verifies that the systems agree before it declares the problem solved.

### Target users

- Integration Operator responsible for failed warehouse-to-ERP messages.
- Accounts Payable Approver responsible for invoice-release decisions.
- Finance, procurement, and warehouse leaders monitoring unresolved receipt and invoice exceptions.

### Product outcome

The product turns a fragmented manual investigation into an audit-ready case with one of three honest outcomes:

1. `CLOSED`: receipt is complete, invoice is released, and post-action verification passed.
2. `PROTECTED`: a dangerous or duplicate action was prevented and the case was safely routed.
3. `NEEDS_EVIDENCE`: the system cannot establish a safe action and asks for a specific missing fact.

## 3. Scope

### In scope

- One synthetic SAP-shaped primary scenario.
- Deterministic discrepancy detection.
- Three bounded root-cause hypotheses.
- Multi-agent evidence collection and synthesis using Strands Agents SDK.
- A versioned vector knowledge base containing synthetic SOPs, error semantics, and recovery rules.
- An independent evaluator that accepts, rejects, or requests more evidence.
- Two human roles and two exact action tools.
- Signed, short-lived, case-version-bound action authorization.
- Fresh-read, idempotent execution and post-action verification.
- Append-only case history and visible agent/tool traces.
- A synthetic golden dataset covering the main flow and safety failures.
- Local deterministic operation plus a separately verified AWS execution path.

### Out of scope

- Real SAP, employer, customer, warehouse, invoice, runbook, or incident data.
- Autonomous payment, invoice posting, write-off, PO change, supplier claim, or supplier communication.
- Arbitrary tool execution or free-form SQL.
- A general ERP control tower supporting unrelated exception families.
- Probabilistic ETA prediction, price forecasting, or revenue claims.
- FlowPulse source reuse unless an explicit file-level provenance entry is added first.

## 4. Primary synthetic case

### Authoritative facts

- Purchase order quantity: 100 units.
- Warehouse physical receipt: 100 units.
- ERP goods receipt: 80 units.
- Supplier invoice: 100 units.
- The second 20-unit receipt message is in a synthetic failed-message queue.
- Failure classification: `DOCUMENT_LOCKED_RETRYABLE`.
- The temporary lock has cleared.
- The original message remains retry-eligible.
- No material document exists for the missing 20 units.
- The invoice is held because ERP receipt and invoice quantity do not agree.

### Intended resolution

1. The system detects the 20-unit discrepancy and opens a versioned case.
2. Three investigators test retryable-lock, genuine-short-shipment, and already-posted hypotheses.
3. The synthesis agent produces a cited conclusion and proposed action.
4. The independent evaluator verifies evidence coverage and safety invariants.
5. The Integration Operator approves `restart_receipt_message` for the exact failed message.
6. The executor fresh-reads all relevant state, restarts the original message, and verifies ERP receipt equals 100 with exactly one business effect.
7. The AP Approver approves `release_invoice` for the exact invoice.
8. The executor fresh-reads receipt and invoice state, releases the hold, and verifies the invoice is `RELEASED`.
9. The deterministic application service records `CLOSED`.

### Safety counterexamples

#### Counterexample A: already posted before approval

Evidence shows the missing 20 units already have a material document. The evaluator rejects restart, no action grant is created, and deterministic verification routes the case directly to invoice approval if ERP receipt is already 100.

#### Counterexample B: state changes after approval

After approval but before execution, another process posts the receipt. The executor's fresh read turns the requested restart into a safe no-op, verifies ERP receipt equals 100, records the state drift, and continues without creating a duplicate receipt.

#### Counterexample C: genuine short shipment

Evidence proves only 80 units physically arrived. The system must not restart a message or release the invoice. It records `PROTECTED` and explains which operational process must resolve the shortage outside this prototype.

#### Counterexample D: stale authorization

The approval is expired, already consumed, signed for an older case version, or bound to different parameters. The policy and executor reject it without a downstream write.

## 5. Architecture

### Components

1. **Synthetic Enterprise Systems**
   - Warehouse/EWM-shaped receipt service.
   - Failed-message/qRFC-shaped queue service.
   - ERP goods-receipt service.
   - Invoice service.
   - All services expose typed synthetic APIs and deterministic fixtures.

2. **Exception Detector**
   - Compares physical receipt, ERP receipt, and invoice records.
   - Emits a typed exception fact only when deterministic thresholds and age rules are met.
   - The Case Application Service validates that fact, creates the versioned case, and starts investigation.
   - Does not guess root cause.

3. **Investigation Harness**
   - Runs three bounded investigators in parallel.
   - Provides only allowlisted read tools and versioned evidence.
   - Requires every factual claim to reference admitted evidence.

4. **Knowledge Infrastructure**
   - Stores synthetic SOPs, error definitions, retry rules, role policies, and examples.
   - Every retrieved item carries document ID, version, effective date, and source class.
   - Knowledge supports interpretation; it cannot prove current runtime state.

5. **Synthesis Agent**
   - Compares the three hypotheses.
   - Produces a structured diagnosis, rejected alternatives, missing evidence, proposed action, and citations.
   - Has no write credentials.

6. **Independent Evaluator**
   - Receives the structured diagnosis and an independently assembled evidence view.
   - Checks citation integrity, causal consistency, action eligibility, duplication risk, and missing evidence.
   - Returns `ACCEPT`, `REJECT`, or `MORE_EVIDENCE` as structured output.
   - Cannot write case state, grant approval, or invoke actions.

7. **Deterministic Case Application Service**
   - Validates all agent/evaluator schemas.
   - Owns state transitions and append-only case events.
   - Writes evaluator outcomes to the case ledger after deterministic validation.
   - Exposes the read projection and role-scoped approval commands.

8. **Decision Workspace**
   - Shows discrepancy, hypothesis comparison, cited evidence, evaluator result, allowed action, and expected postconditions.
   - Never fabricates lifecycle state in the browser.
   - Presents only the action authorized for the signed-in role.

9. **Authorization Service**
   - Accepts only a validated human approval tied to the current case version.
   - Produces a KMS-signed action grant containing principal, role, authorization ID, case version, tool, complete parameters, evidence digest, action digest, issued time, and expiry.
   - Does not expose its signing permission to agents, UI, or executor clients.

10. **Policy Gateway**
    - Validates identity, role, exact tool, complete parameter set, case version, digest, TTL, and one-time authorization ID.
    - Denies by default.

11. **Deterministic Executor and Verifier**
    - Is the only component with synthetic downstream write credentials.
    - Fresh-reads authoritative state before every action.
    - Executes an idempotent action or safe no-op.
    - Fresh-reads again and proves explicit postconditions.
    - Returns a structured execution receipt; it cannot directly mark a case closed.

12. **Case and Evaluation Store**
    - Stores append-only events, current projections, approvals, grants, receipts, and golden-run results.
    - Uses conditional writes to reject stale case versions and replayed authorization IDs.

### Core data flow

```text
synthetic enterprise facts
  -> deterministic detector
  -> deterministic case application service
  -> versioned case
  -> three read-only investigators + knowledge retrieval
  -> synthesis
  -> independent evaluator
  -> deterministic case transition
  -> role-specific human approval
  -> signed action grant
  -> policy decision
  -> fresh-read / execute or no-op / fresh-read verify
  -> execution receipt
  -> deterministic case transition
  -> next approval or final outcome
```

## 6. Authority matrix

| Component | Read evidence | Propose diagnosis | Append case event | Approve action | Sign grant | Execute write | Close case |
|---|---:|---:|---:|---:|---:|---:|---:|
| Investigators | Yes | Partial | No | No | No | No | No |
| Synthesis Agent | Yes | Yes | No | No | No | No | No |
| Independent Evaluator | Yes | Accept/reject recommendation | No | No | No | No | No |
| Case Application Service | Yes | No | Yes | No | No | No | Yes, after verification |
| Decision Workspace | Projection only | No | No | No | No | No | No |
| Integration Operator | Presented evidence | No | Via approval API | Receipt restart only | No | No | No |
| AP Approver | Presented evidence | No | Via approval API | Invoice release only | No | No | No |
| Authorization Service | Current approved case | No | Authorization record | Validates existing approval | Yes | No | No |
| Policy Gateway | Grant and current context | No | Policy decision | No | No | No | No |
| Executor/Verifier | Current downstream state | No | Execution receipt | No | No | Yes | No |

No model, agent, browser component, or user-supplied payload is authoritative for current enterprise state or lifecycle transitions.

## 7. State model

### Main states

```text
OPEN -> INVESTIGATING

INVESTIGATING
  ├─ NEEDS_EVIDENCE -> typed evidence admitted -> INVESTIGATING
  ├─ PROTECTED -> terminal
  ├─ RECEIPT_ALREADY_VERIFIED -> AWAITING_INVOICE_APPROVAL
  └─ RECEIPT_RESTART_RECOMMENDED
       -> AWAITING_RECEIPT_APPROVAL
       -> RECEIPT_ACTION_AUTHORIZED
       -> RECEIPT_EXECUTING
       -> RECEIPT_VERIFIED
       -> AWAITING_INVOICE_APPROVAL
       -> INVOICE_ACTION_AUTHORIZED
       -> INVOICE_EXECUTING
       -> CLOSED
```

### Transition rules

- `NEEDS_EVIDENCE` resumes only after a typed evidence item is admitted and the case version increments.
- `PROTECTED` is used when a consequential action is unsafe or the supported workflow cannot resolve the case.
- A rejected or expired approval never advances state.
- An accepted approval advances only through the authorization service.
- An execution result advances only after deterministic postcondition validation.
- `CLOSED` requires ERP receipt `100`, no duplicate material document, failed message cleared or safely consumed, and invoice state `RELEASED`.
- Every command carries an idempotency key and expected case version.

## 8. Core contracts

### Case

- `case_id`
- `case_version`
- `scenario_id`
- `status`
- `discrepancy`
- `current_evidence_revision`
- `created_at`
- `updated_at`

### Evidence item

- `evidence_id`
- `case_id`
- `subject`
- `source_type`
- `source_record_id`
- `observed_at`
- `content_digest`
- `admitted_fields`
- `provenance`

### Hypothesis result

- `hypothesis_type`
- `conclusion`
- `confidence_band`
- `supporting_evidence_ids`
- `contradicting_evidence_ids`
- `missing_evidence`

### Evaluation result

- `decision`
- `validated_evidence_ids`
- `failed_invariants`
- `allowed_next_action`
- `evaluator_version`
- `trace_id`

### Approval

- `approval_id`
- `case_id`
- `case_version`
- `principal_id`
- `role`
- `tool`
- `parameters_digest`
- `decision`
- `decided_at`

### Action grant

- `authorization_id`
- `case_id`
- `case_version`
- `principal_id`
- `role`
- `tool`
- `complete_parameters`
- `evidence_digest`
- `action_digest`
- `issued_at`
- `expires_at`
- `signature`

### Execution receipt

- `execution_id`
- `authorization_id`
- `pre_state_digest`
- `operation_result`
- `post_state_digest`
- `postconditions`
- `material_document_ids`
- `executed_at`
- `trace_id`

## 9. Agent and evaluation design

### Investigators

1. **Retryable Message Investigator** checks queue state, lock state, retry eligibility, message identity, and missing material document.
2. **Short Shipment Investigator** checks physical receipt, handling-unit events, packing evidence, and delivered quantity.
3. **Duplicate Posting Investigator** checks ERP material documents, idempotency keys, and prior executions.

The orchestration harness runs all three with bounded budgets and allowlisted tools. A result without cited admitted evidence is invalid.

### Synthesis

The synthesis step ranks hypotheses but must preserve dissenting evidence. It cannot convert a knowledge-base statement into a current-state fact. If two hypotheses remain plausible, it must request evidence rather than select the more fluent explanation.

### Evaluation flywheel

- Every golden case contains input facts, expected hypothesis, expected action eligibility, expected terminal state, and invariants.
- Agent traces, tool results, evaluator decisions, and final outcomes are recorded by version.
- Regression runs compare actual structured outputs with expected invariants.
- Candidate failures may become new golden cases only after human review.
- Prompt, model, orchestration, retrieval, and policy changes must pass the same golden suite.
- The system does not claim self-improvement from unreviewed production output.

### Required golden cases

1. Retryable lock, safe restart, receipt verified, invoice released.
2. Receipt already posted before approval; no restart grant.
3. Receipt posted after approval; executor safe no-op.
4. Genuine short shipment; receipt restart and invoice release both denied.
5. Missing material-document evidence; request evidence.
6. Expired grant.
7. Replayed authorization ID.
8. Old case version.
9. Tampered parameter or evidence digest.
10. Duplicate executor request.
11. Evaluator disagrees with synthesis.
12. Post-action receipt verification fails; invoice approval remains locked.
13. Integration Operator requests `release_invoice`; no grant and zero downstream writes.
14. AP Approver requests `restart_receipt_message`; no grant and zero downstream writes.
15. AP Approver requests invoice release before `RECEIPT_VERIFIED`; no grant and zero downstream writes.

## 10. Error handling

- Tool timeout: retry at most once; a second failure enters `NEEDS_EVIDENCE` with reason code `SOURCE_UNAVAILABLE` and stops the loop without substituting model knowledge.
- Missing source: return `NEEDS_EVIDENCE` with the exact missing record.
- Malformed agent output: reject at schema boundary and rerun once with the validation error.
- Second malformed output: stop the agent loop and record `AGENT_OUTPUT_INVALID`.
- Evaluator rejection: return to investigation with failed invariants; do not generate a grant.
- Case-version conflict: reload current projection and require a fresh human decision.
- Expired/replayed grant: deny and append a security event.
- Downstream state drift: perform safe no-op or block according to the fresh-read rule.
- Postcondition failure: keep the case open, prohibit the next approval, and surface the execution receipt.
- AWS component unavailable: preserve the local deterministic path and label the cloud path unavailable; never display simulated AWS success as live proof.

## 11. AWS architecture and proof matrix

| Capability | Planned use | Status on 2026-08-25 | Required proof |
|---|---|---|---|
| AgentCore Runtime | Host Strands investigation entrypoint | Runtime deployment and basic invocation proven; product structured diagnosis not yet proven | Successful structured diagnosis invocation |
| Bedrock model | Investigator, synthesis, evaluator calls | Basic model invocation proven | Versioned structured-output run |
| AgentCore Gateway | Expose typed read/action tools | Not proven | Real tool discovery and invocation trace |
| AgentCore Policy | Role/tool/parameter authorization | Not proven | One allow and at least three deny traces |
| KMS | Sign action grants | Not proven | Signature validation and tamper rejection |
| DynamoDB | Case projection, ledger indexes, grants | Not proven | Conditional-write and replay-rejection tests |
| Amazon Cognito | Separate operator and AP demo identities and groups | Not proven | Distinct role-scoped approvals |
| Bedrock Knowledge Bases + S3 Vectors | Versioned SOP retrieval | Not proven | Citation-bearing retrieval with version filter |
| AgentCore Observability / OTEL | Agent, tool, policy, execution trace | Not proven | End-to-end trace tied to a golden case |
| S3 | Synthetic documents and evidence fixtures | Source-upload path proven | Versioned synthetic evidence objects |

The project will not describe a planned AWS control as implemented until its proof artifact passes review.

## 12. Local development architecture

### Runtime choices

- Python 3.12 for domain logic, deterministic services, Strands integration, and API.
- FastAPI for local typed HTTP contracts and decision commands.
- React, TypeScript, and Vite for the monitoring and decision workspace.
- SQLite for the first deterministic slice; the storage interface must also support DynamoDB without changing domain logic.
- Local synthetic JSON fixtures for enterprise systems; cloud adapters implement the same interfaces.
- Two explicit local fixture identities mirror the Cognito groups for offline tests; they are accepted only in local/test mode.
- Pytest, Ruff, mypy, and Node tests as mandatory checks.

### Environment requirements

- Node.js 20.x.
- Python 3.12.x from a reproducible project bootstrap, not an undocumented global interpreter.
- Repository version files pin the exact Python and Node patch releases used by CI and the demo.
- AWS CLI v2.
- AWS IAM Identity Center/SSO with short-lived credentials; root access keys are prohibited.
- Default AWS region: `us-west-2`.
- GitHub CLI for repository operations.
- Docker is optional until a concrete test requires it; the project will not introduce container infrastructure merely for parity with FlowPulse.

### Environment acceptance

- A fresh checkout can create `.venv`, install locked dependencies, and run `make check`.
- Python dependencies use a committed lock file; frontend dependencies use the committed `package-lock.json`; every Make target installs from those locks.
- `make dev` starts the API and UI with synthetic fixtures.
- `make demo` runs the deterministic main case without AWS credentials.
- `make golden` runs all golden cases and produces a machine-readable report.
- `make aws-smoke` is explicit, opt-in, and refuses root credentials. Before creating or changing a real resource it validates the expected AWS account, `us-west-2`, the approved budget ceiling, a dedicated resource prefix, and a recorded cleanup plan, then requires user authorization.
- Secrets remain in ignored local configuration or AWS SSO sessions.

## 13. Implementation workflow

Each phase follows this loop contract:

```text
Goal: produce one inspectable vertical capability.
Input: approved spec, synthetic fixtures, current repository state.
Execute: implement the smallest slice, then its integration.
Check: unit, contract, state-machine, golden, and user-facing smoke tests.
Feedback: repair the failing boundary; do not broaden scope.
Record: decision log, proof artifact, test output, and provenance update.
Stop: acceptance passes, or a human/AWS capability gate is reached.
Human gates: account changes, paid deployment, public publishing, consequential demo actions, and scope changes.
```

### Phase 0: Spec and environment freeze

- Freeze this specification and Architecture v4.2 mapping.
- Add dependency locks and reproducible bootstrap.
- Install and verify AWS CLI v2 and SSO path after human approval.
- Add project commands and CI skeleton.
- Produce the state-machine and AWS-proof test manifests.

Acceptance:

- Clean checkout passes all scaffold checks.
- No ambiguous product action remains.
- Reviewer accepts the authority matrix and main case.

### Phase 1: Deterministic closed slice

- Implement synthetic enterprise adapters.
- Implement detector, case aggregate, append-only events, approvals, grants, executor, and verifier.
- Complete the main flow without an LLM.
- Pass already-posted, state-drift, stale-version, expired-grant, replay, and postcondition-failure tests.

Acceptance:

- Main case reaches `CLOSED` only after both approvals and verified postconditions.
- Every prohibited path performs zero unauthorized downstream writes.

### Phase 2: Investigation and evaluation harness

- Implement Strands investigators, orchestration, synthesis, retrieval, and independent evaluator.
- Bind all factual statements to admitted evidence IDs.
- Implement golden runner and trace records.

Acceptance:

- All required golden cases pass deterministic invariants.
- False receipt restart and false invoice release are both zero in the frozen golden set.

### Phase 3: AWS control chain

- Deploy Runtime and typed tools.
- Validate Gateway and Policy behavior before depending on them.
- Integrate KMS, DynamoDB, two identities, knowledge retrieval, and OTEL incrementally.
- Delete disposable spike resources after each bounded test.

Acceptance:

- A real end-to-end trace shows investigation, policy decision, approval-bound action, and verification.
- Deny cases visibly fail closed.
- Cloud cost remains within the approved budget.

If Gateway or Policy cannot enforce the required contract, implementation stops for architecture review. The project will not replace a failed real control with a UI-only simulation.

### Phase 4: Decision workspace and competition demo

- Build the live case monitor, evidence view, approval views, action receipt, and golden-results panel.
- Make the primary business conflict understandable without SAP terminology.
- Prepare architecture evidence, README, Devpost copy, and video.

Acceptance:

- A first-time viewer can explain the problem, agent contribution, human decision, safe action, and verified outcome after the five-minute demo.
- The UI contains no fabricated lifecycle or cloud status.

### Phase 5: Final hardening

- Run security, provenance, accessibility, browser, repository, cost, and submission audits.
- Obtain final independent architecture and competition review.
- Freeze the public repository and submission evidence.

## 14. Five-minute demo storyboard

| Time | Scene | Required proof |
|---|---|---|
| 0:00–0:30 | Control tower detects warehouse 100 versus ERP 80 | Deterministic live case record |
| 0:30–1:20 | Agent handoff and three parallel hypotheses | Real agent/tool trace |
| 1:20–2:10 | Evidence and SOP citations converge on retryable message | Evidence IDs and versioned sources |
| 2:10–2:40 | Independent evaluator rejects unsafe alternatives | Structured evaluator result |
| 2:40–3:25 | Operator approves restart; fresh-read, execution, receipt verification | Signed grant, policy decision, receipt |
| 3:25–4:05 | AP approves invoice release; final verification closes case | Separate principal and execution receipt |
| 4:05–4:35 | State-drift counterexample becomes safe no-op | Deny/no-op trace and no duplicate posting |
| 4:35–5:00 | Golden results, impact, and architecture close | Test report and AWS proof labels |

## 15. Quality and competition acceptance

### Technical implementation

- Real AgentCore Runtime use is demonstrated.
- Tool interfaces, state transitions, approvals, authorization, execution, and verification are typed and testable.
- Agent output cannot bypass deterministic controls.

### Design

- The UI leads with the business discrepancy and resolution status.
- Evidence, uncertainty, human decision, and execution result remain visually distinct.
- The main path is understandable without knowing qRFC, LUW, or GR/IR terminology.

### Impact

- Demo metrics are direct workflow facts: case age, manual handoffs, protected amount, resolution-ready time, and verified terminal state.
- No fabricated accuracy, savings percentage, revenue, or production adoption claim is allowed.

### Creativity and originality

- The differentiator is the complete diagnosis-to-verified-recovery harness across operational and financial evidence.
- The project is not presented as AI three-way matching, a chatbot, or generic ERP automation.

### Presentation

- The primary path finishes within 4:05, leaving time for one safety counterexample and proof summary.
- Every cloud claim visible in the video has a retained proof artifact.

## 16. Security and privacy

- Synthetic data only.
- No employer/customer identifiers, code, screenshots, schemas, incidents, or runbooks.
- No raw chain of thought is stored or displayed.
- Prompt and tool inputs are bounded and redacted before tracing.
- All write tools are deny-by-default and parameter-bound.
- Approval and execution are separate operations.
- Grants are short-lived and single-use.
- The executor validates fresh state and postconditions.
- The system has no payment tool.

## 17. Provenance

The repository is a new MIT-licensed competition project. FlowPulse currently provides conceptual influence only. Before any FlowPulse file, component, visual asset, or test fixture is reused, `docs/provenance.md` must record the original repository, commit, path, license, destination, modification, and reason.

Architecture ideas such as evidence envelopes, independent evaluation, append-only history, human approval, and post-action verification may be reimplemented from first principles without claiming that FlowPulse is part of the submission.

## 18. Final stop conditions

Implementation is ready for submission only when:

- The deterministic main case and all frozen safety cases pass.
- The independent evaluator cannot authorize actions.
- Both approvals are identity- and role-specific.
- Unauthorized, stale, expired, replayed, or drifted actions create no duplicate business effect.
- `CLOSED` is derived only from fresh verified state.
- AWS proof labels distinguish live, recorded, and planned behavior.
- The public repository contains no confidential source or undisclosed reused file.
- An independent reviewer accepts the final system against the competition rubric.
