# Demo Tenant Closed-Loop Design

## Goal

Deliver a truthful, recordable automotive quality-release demo in which a live
ERPNext incident is investigated across Airtable, Celigo, Jira, and Slack; a
Manager approves a constrained remedy; the Agent executes it only in the
dedicated M20 demo tenant; and fresh provider reads verify the outcome.

## Authority and boundaries

All provider writes are restricted to M20 demo resources. The executor refuses
to run unless `MISSING20_ENVIRONMENT=demo`, provider credentials are present,
and every document/case identifier has the `M20` demo scope. Browser clients
never receive credentials. The server records a local immutable execution
ledger, but provider reads are the authority for final status.

The only ERPNext write actions are:

1. Idempotent Material Transfer from the case's Quality Hold warehouse to
   Stores for the validated quantity.
2. Unblocking the exact case Purchase Invoice after the transfer read-back.

No user, supplier, configuration, or non-M20 document may be created, changed,
or deleted by the executor.

## Evidence contract

Every case has a canonical tuple:

`case_id, purchase_order, purchase_receipt, purchase_invoice, supplier_lot,
certificate_id, quantity, evidence_revision`.

ERPNext is authoritative for PO, receipt, transfer, and invoice status.
Airtable is authoritative for the quality-release registry. Celigo is
authoritative only for its own run receipt. Jira and Slack are contextual
journals and never prove a release. A Celigo flow being enabled is control-plane
state, not a receipt.

Celigo must create a run receipt containing the complete canonical tuple, a
run ID, a terminal success status, and ERP acknowledgement. The Agent treats
missing, failed, mismatched, or control-plane-only Celigo evidence as a hard
block.

## Agent lifecycle

1. A normal provider read shows the submitted PO, received inventory, quality
   registry, and inactive incident state.
2. A real M20 ERPNext receipt with rejected quantity and invoice hold appears.
3. The Agent reads all sources, emits server-owned live activity, correlates
   the tuple, and either creates a guarded plan or blocks with a precise reason.
4. A Manager grants one explicit approval to the plan, bound to the tuple,
   provider state hash, idempotency key, and permitted actions.
5. The executor re-reads ERPNext and rejects stale state, then performs the
   transfer and invoice unblock exactly once.
6. Celigo sends the case notification and exposes an exact run receipt.
7. The verifier freshly reads ERPNext, Airtable, Celigo, Jira, and Slack. It
   marks the case `VERIFIED` only when all hard conditions pass.

## Cases

| Case | Condition | Expected result |
| --- | --- | --- |
| A | Approved lot A release had not reached ERP | Agent proposes and completes guarded recovery. |
| B | Integration delivery acknowledgement lost; retry is attempted | Duplicate protection rejects retry and preserves one transfer. |
| C | Certificate/lot conflicts with ERP tuple | Hard block; no provider write. |
| D | Certificate is expired | Hard block; no provider write. |

Case A uses existing real ERPNext documents `PUR-ORD-2026-00011`,
`MAT-PRE-2026-00001`, and `ACC-PINV-2026-00007`. B--D remain clearly labelled
M20 demo cases and are seeded before their executions.

## Components

- `ERPNextDemoExecutor`: validates environment/scope, re-reads documents,
  submits one Material Transfer, unblocks the invoice, and returns redacted
  action receipts.
- `CeligoRunReceiptSource`: reads only the configured demo integration's Jobs
  and validates terminal run evidence against the canonical tuple.
- `AgentPlatform`: changes from globally read-only to an explicit
  `demo_guarded` capability model; diagnosis, plan, approval, execute, and
  verify are separate server actions.
- Workspace UI: renders provider-backed activity and action state; it does not
  invent completion from animation or a flow-enabled flag.

## Failure handling

Execution is refused for stale approval, unavailable provider reads, incomplete
or mismatched tuples, a non-terminal Celigo job, a duplicate idempotency key,
or any document outside the M20 demo scope. A post-write read failure leaves
the result `VERIFYING`, never `VERIFIED`. Re-running the same approved action
returns its existing provider receipt rather than creating another transfer.

## Verification

- Unit tests cover scope guards, tuple matching, stale approval, duplicate
  execution, provider failure, and verification transitions.
- HTTP tests cover normal → incident → diagnose → approve → execute → verify.
- Live smoke tests use only the dedicated M20 demo accounts and verify API
  responses without exposing credentials.
- The recording script demonstrates A's normal, incident, diagnosis, approval,
  execution, and verification stages, then shows B--D blocking safely.
