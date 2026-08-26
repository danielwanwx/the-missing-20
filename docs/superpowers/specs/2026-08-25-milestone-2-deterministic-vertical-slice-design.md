# Milestone 2 Deterministic Vertical Slice Design

**Status:** Implementation accepted by Chief Architect after five independent gate reviews
**Date:** 2026-08-25  
**Parent design:** [`2026-08-25-the-missing-20-design.md`](2026-08-25-the-missing-20-design.md)  
**Implementation plan:** [`../plans/2026-08-25-the-missing-20-implementation-plan.md`](../plans/2026-08-25-the-missing-20-implementation-plan.md)

## 1. Goal and boundary

Milestone 2 must execute the approved `100 / 80 / 100` case through a real local data path:

```text
JSON seed
  -> persistent enterprise records
  -> detector fresh reads
  -> persistent case genesis and events
  -> deterministic diagnosis
  -> Integration Operator approval
  -> signed and policy-checked receipt action
  -> persistent enterprise mutation and verification
  -> AP Approver approval
  -> signed and policy-checked invoice action
  -> persistent enterprise mutation and verification
  -> replay-derived CLOSED projection
  -> auditable demo artifact
```

“Real” means the program reads and mutates typed records in SQLite through production-shaped ports. Tests may control clocks, IDs, and fault points, but may not replace enterprise reads or writes with mock return values. All records remain synthetic. This milestone makes no AWS or model calls.

## 2. Loop contract

```text
Goal: Close one retryable receipt discrepancy through two independently authorized actions.
Input: One versioned JSON fixture and two trusted local identities.
Execute: Seed, detect, diagnose, approve, reserve, execute, verify, approve, reserve, execute, verify.
Check: Replayed case state, authoritative enterprise state, policy ledger, business-effect ledger, and invariants.
Feedback: A failed precondition denies before mutation; a postcondition failure keeps the case open; a persistence fault resumes the same execution attempt.
Record: Genesis, evidence, events, approvals, grants, policy decisions, attempts, receipts, business effects, and final artifact.
Stop: CLOSED with every invariant true, or a typed protected/failed state with zero unauthorized effects.
Human gates: The two simulated approvals use separate trusted identities; no external account or paid-service gate occurs.
```

## 3. Persistence boundaries

The slice uses two independent SQLite files so an enterprise commit can survive a case-service crash.

### `enterprise.sqlite`

Seeded from `fixtures/scenarios/retryable-document-lock.json` and authoritative for:

- purchase-order lines;
- warehouse receipts;
- failed receipt messages and their revisions;
- ERP receipt totals;
- invoices, revisions, hold reasons, and blocking holds;
- material documents;
- append-only business effects.

Receipt-message consumption, ERP `80 -> 100`, material-document creation, and business-effect insertion occur in one enterprise transaction. The source message ID and idempotency key have unique constraints. Invoice release and its business effect use the same rule.

### `case.sqlite`

Authoritative for:

- immutable detection genesis;
- admitted evidence;
- append-only case events with normalized payload JSON and payload digest;
- current case projection;
- approvals and grants;
- policy decisions;
- execution attempts and receipts.

Appending an event and conditionally updating the projection occur in one transaction. `UNIQUE(case_id, idempotency_key)` stores the command digest. An identical retry returns the recorded result; the same key with a different digest raises an idempotency conflict.

The projection is a cache, not lifecycle truth. Tests replay genesis plus ordered events and require the replayed projection to equal the stored projection.

## 4. Required audit contracts

Every record below carries `case_id` and `trace_id`:

- `DetectionGenesis`;
- `EvidenceItem`;
- `CaseEvent`;
- `Approval`;
- `ActionGrant`;
- `PolicyDecision`;
- `ExecutionAttempt`;
- `ExecutionReceipt`;
- `BusinessEffect`.

`CaseEvent` stores both canonical payload JSON and its SHA-256 digest. The digest is verified during replay. Genesis contains the fixture path, fixture digest, detection facts, initial discrepancy, initial case projection, and detector evidence references.

The following additional contracts are frozen for this milestone:

```text
PolicyDecision
  decision_id, case_id, trace_id, authorization_id?, execution_id?
  principal_id, trusted_role, tool, decision, reason_codes
  decision_stage (APPROVAL_GATE or EXECUTION_GATE)
  case_version, parameters_digest, evidence_digest, action_digest, decided_at

ExecutionAttempt
  execution_id, authorization_id, case_id, trace_id, idempotency_key
  tool, canonical_parameters, command_digest, status, reserved_at, completed_at?

BusinessEffect
  effect_id, case_id, trace_id, execution_id, idempotency_key
  effect_type, source_record_id, result_record_ids, committed_at
```

## 5. Execution-attempt protocol

The receipt and invoice actions use the same reservation protocol.

1. A role-correct approval is accepted against awaiting-approval version `N`.
2. The accepted transition creates authorized version `N+1`.
3. The grant binds the exact principal, trusted role, tool, full parameters, evidence, action digest, and case version `N+1`.
4. The first execution request opens one `case.sqlite` transaction and:
   - loads the immutable stored grant by authorization ID and uses a trusted clock; request payloads cannot supply or override either the signed grant or current time;
   - verifies signature, TTL, current case version, trusted identity, tool, complete parameters, evidence digest, and action digest;
   - records the policy allow;
   - creates the unique execution attempt;
   - moves the grant from `ISSUED` to `RESERVED`;
   - appends the execution-started event and advances the case to executing version `N+2`.
5. The downstream call always uses that attempt’s unchanged idempotency key.
6. After authoritative postconditions pass, one case transaction writes the execution receipt, marks the attempt `COMPLETED`, marks the grant `CONSUMED`, appends the verified event, and advances the projection.

Crash recovery is not a second authorization. If the enterprise commit succeeded but step 6 failed, recovery must present the same `authorization_id`, `execution_id`, idempotency key, and command digest. The service returns the existing reservation, reads the enterprise ledger, verifies authoritative state, and completes step 6. A different attempt for the reserved or consumed authorization is denied.

Recovery reloads and revalidates the stored signed grant. Caller-supplied expiry, signature, role, tool, case context, or version values are never accepted as recovery authority.

TTL remains fail closed after reservation:

- before expiry, the same reserved attempt may perform its first enterprise mutation or recover an existing effect;
- after expiry, recovery may only read and verify a business effect that already exists with the exact `execution_id` and idempotency key, then persist the missing local receipt;
- after expiry with no matching committed effect, policy records an expired deny, performs no mutation, and requires a new human approval;
- “completion after TTL” therefore means reconciling an already committed enterprise effect, never creating a new effect.

## 6. Complete action envelopes

### Receipt restart

The signed canonical parameters contain:

- failed message ID and revision;
- purchase-order ID and line ID;
- quantity `20`;
- expected error code `DOCUMENT_LOCKED_RETRYABLE`;
- expected message status `FAILED`.

The executor fresh-read selects exactly one of three outcomes:

- `EXECUTE`: the same message revision and payload identity remain failed, retry eligibility is true, the lock is cleared, and no material document exists for the source message;
- `SAFE_NOOP_STATE_DRIFT`: an externally committed 20-unit material document is uniquely linked to the same purchase-order line and source message, ERP receipt is `100`, the failed message is cleared or consumed, and exactly one corresponding business effect exists; the current attempt records drift and performs no enterprise write;
- `DENY_OR_PROTECT`: quantity, purchase-order line, or source-message identity differs; multiple documents/effects exist; the state cannot be uniquely linked; or the expected safety facts are not established.

An effect produced by the current attempt is recovered through the execution-attempt protocol, not classified as external state drift.

### Invoice release

The signed canonical parameters contain:

- invoice ID and revision;
- purchase-order ID and line ID;
- invoice quantity `100`;
- expected hold reason `RECEIPT_MISMATCH`.

The executor fresh-read selects exactly one of three outcomes:

- `EXECUTE`: the invoice remains at the signed revision, ERP receipt is `100`, the hold reason is exactly `RECEIPT_MISMATCH`, and no other blocking hold exists;
- `SAFE_NOOP_STATE_DRIFT`: authoritative history proves the same invoice was already released by an external process after ERP reached `100`, the receipt-mismatch hold is gone, and no other blocking hold exists; the current attempt performs no enterprise write;
- `DENY_OR_PROTECT`: the invoice identity, purchase-order line, quantity, or blocking-hold set differs, or the external transition cannot be verified.

An invoice release produced by the current attempt is recovered through the execution-attempt protocol. Revision drift alone never authorizes a safe no-op.

Policy recomputes canonical parameter, evidence, and action digests from stored data and verifies the signature. It never trusts digest strings merely because they appear in the grant.

## 7. Postcondition-failure protocol

Postcondition failure is an auditable terminal result for the attempt, not permission to mutate again.

1. The verifier always persists an `ExecutionReceipt`, including `operation_result=FAILED`, pre/post state digests, and the truth value of every required postcondition.
2. The attempt moves to `VERIFICATION_FAILED`.
3. If the enterprise action was invoked or a matching business effect was committed, the grant moves to `CONSUMED`; it cannot authorize another attempt or mutation.
4. The case remains in the corresponding `RECEIPT_EXECUTING` or `INVOICE_EXECUTING` state. No verified event is appended and the next approval is unavailable.
5. A later operation may re-read and re-verify the same attempt, or enter an explicit human recovery path in a later milestone. It may not perform an unconditional second enterprise mutation.

The postcondition-failure test hook must alter or expose authoritative enterprise records after the transaction. It cannot merely force the verifier to return a hard-coded false result.

## 8. Trusted identities and diagnosis seam

`IdentityContext` is created by trusted local configuration, not by the approval payload:

- `operator-001 -> INTEGRATION_OPERATOR`;
- `ap-approver-001 -> AP_APPROVER`.

Approval, policy, attempt reservation, expiry checks, enterprise commit timestamps, and receipts read time from an injected trusted `Clock`. The deterministic test adapter may advance that clock; application requests cannot submit or backdate authorization time.

Approval commands provide the principal and decision; the application service resolves the role from the trusted identity context before creating an approval or grant.

The deterministic diagnosis stub emits the same `HypothesisResult` and `EvaluationResult` contracts that Milestone 4 agents will emit. It may cite admitted evidence and recommend an action, but it has no signer, policy, store-mutation, or executor capability.

## 9. End-to-end demo proof

`make demo` creates fresh temporary database files, seeds from the JSON fixture, and runs the application services rather than constructing a final case directly. It also performs one controlled deny probe: before receipt verification, the AP identity requests invoice release. The denial is persisted, and the business-effect count must remain unchanged.

`artifacts/demo/main-case.json` contains:

- fixture path and SHA-256;
- `diagnosis_mode: deterministic_stub`;
- initial authoritative enterprise records;
- detector read evidence and digests;
- immutable genesis;
- ordered versioned event timeline;
- two approvals from distinct principals and trusted roles;
- policy allow and deny records;
- execution-attempt reservations;
- executor pre-read and post-read evidence;
- execution receipts;
- business-effect ledger;
- final authoritative enterprise records;
- invariant results with evidence references.

The command also prints a short human-readable timeline. The artifact is technical proof for later UI consumption, not a substitute for the final product experience.

## 10. End-to-end and recovery acceptance

The integration suite must start with the JSON fixture and real temporary SQLite files. It must not directly construct the final case, grant, enterprise read, business effect, or terminal projection.

Required checks:

1. The detector fresh-reads the seeded records and derives the `20` discrepancy.
2. The case reaches `CLOSED` only after two approvals from distinct, role-correct trusted identities.
3. The receipt becomes `100` before invoice release becomes eligible.
4. An early AP release attempt produces a persisted deny and zero business effects.
5. Stale case version, wrong role/tool, duplicate execution, and failed postconditions produce zero unauthorized writes.
6. Every audit record shares the same case and trace IDs.
7. Replaying genesis and event payloads reproduces the stored projection.
8. A fault injected after the enterprise receipt transaction commits but before the case receipt transaction commits terminates the first service instance.
9. New service and adapter instances reopen both database files, recover the same reserved attempt, and complete without a second material document or business effect.
10. A reserved attempt with no committed effect cannot mutate after grant expiry; a reserved attempt with an exact committed effect may only reconcile its local receipt.
11. Verified external state drift produces an explicit safe no-op and zero new business effects; ambiguous drift denies or protects.
12. Postcondition failure persists a failed receipt, consumes any used grant, keeps the case executing, and blocks the next approval.
13. `make check` remains offline, deterministic, and free of AWS/model calls.
14. `make demo` produces the artifact and a successful invariant summary from the actual run.

## 11. Golden and competition seams

Milestone 3 must vary fixture data and controlled hooks without adding scenario-specific production branches. The approved seams are:

- deterministic clock and ID factory;
- fixture records;
- state-drift hook before enterprise mutation;
- postcondition-failure hook after mutation;
- receipt-persistence fault after enterprise commit;
- trusted identity context.

No generic workflow engine, event bus, repository factory, or abstract unit-of-work framework is introduced. The two databases, typed ports, reservation protocol, and replayable audit chain are the minimum required to prove authorization, crash safety, and real data movement.

This slice directly supports the competition rubric:

- **Technical Implementation:** independent persistence, deterministic replay, idempotent recovery, and deny evidence;
- **Design:** clear separation of diagnosis, human decision, authorization, execution, and verification;
- **Potential Impact:** observable `80 -> 100` receipt recovery and `HELD -> RELEASED` invoice outcome without invented savings metrics;
- **Creativity:** an investigation-to-controlled-resolution harness instead of a chatbot or auto-write demo;
- **Presentation:** one compact timeline that exposes evidence, deny, two approvals, mutations, and verified closure.
