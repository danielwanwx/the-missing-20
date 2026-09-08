# Ambiguous Receipt and Quality Investigation Design

**Status:** approved for implementation by the project owner on 2026-09-03
**Scope:** replace the demo's single `100 expected / 80 recorded` explanation with a
production-shaped, disclosed-synthetic purchase-to-pay investigation.
**Evidence basis:** [submission and winner README benchmark](../../research/2026-09-07-submission-and-winner-readme-benchmark.md).

## Goal

Make the five-minute recorded demo prove why an agent is needed. The visible signal is
simple—100 units physically arrived, 80 are production-available, and the linked
invoice is held—but the source of the gap is not presented as known. The agent must
join independent evidence to choose a safe, minimal recovery and prove its outcome.

The system remains a **production-shaped synthetic demonstration**. It may use real
read-only provider calls where configured, but it must never claim customer data,
production integrations, or live financial processing.

## Primary recorded path

One purchase order, `PO-4817`, contains 100 ECU controllers represented by two
line-level investigation branches:

- **80 accepted and available:** already present in ERPNext `Stores`.
- **8 quality-controlled units:** physically received in `Quality Hold`; the supplier
  quality record says the precise lot is approved, but its release event has no
  acknowledged ERP transfer.
- **12 standard-receipt units:** a receipt-posting event with immutable business key
  `RCPT-4817-L2-001` has a retryable/unknown integration result. The error record is
  not evidence that the ERP write failed.

The invoice bills 100 and is held under a named matching rule. The initial dashboard
shows only the consequence: `100 arrived / 80 available / 8 quality hold / 12 receipt
unresolved / invoice held`. It does not reveal the cause.

The recorded success branch is deliberately specific:

1. ERP reads prove no receipt exists for `RCPT-4817-L2-001`.
2. Supplier-quality evidence proves the exact 8-unit lot is approved and unexpired.
3. Integration evidence proves the quality release and 12-unit receipt are pending,
   without claiming their writes failed.
4. A single Manager approves a proposal bound to the two exact actions and evidence
   versions.
5. The controlled executor posts one idempotent 12-unit receipt and one idempotent
   8-unit quality-to-stores transfer, revalidates the invoice, and re-reads the
   authoritative state.
6. The final view proves 100 available, no duplicate receipt, and the corresponding
   invoice hold resolved.

## Required counterfactuals

The same visible opening signal must exercise two safe-stop outcomes in regression
tests, not in the main video:

| Case | Hidden authoritative fact | Required result |
| --- | --- | --- |
| Already committed / response lost | ERP already contains `RCPT-4817-L2-001` or the quality transfer idempotency key | Reconcile the integration record; do not retry or double-post. |
| Quality not eligible | The exact lot is pending, rejected, expired, or mismatched | Preserve the quality and invoice holds; create no recovery proposal. |

These cases prove the Agent is evidence-led rather than replaying a fixed script.

## Architecture and ownership

| Boundary | Owns | Demo behavior |
| --- | --- | --- |
| ERPNext-shaped system of record | PO, receipt, stock buckets, stock ledger, invoice and hold state | The only write target. Every recovery is idempotent and followed by a reread. |
| Supplier Quality Registry | lot identity, inspection disposition, approved quantity and expiry | Read-only evidence during investigation. Label an Airtable fallback as a supplier-quality registry, never as Siemens Opcenter. |
| Integration control plane | trace key, event ID, attempt lineage, error/timeout status, idempotency key | Read-only evidence. A retryable status means outcome unknown until the ERP business-key lookup. |
| Slack | notification and Manager approval/audit record | Collaboration evidence only; no claim that Slack authorizes ERP writes. |
| Strands/Nova advisory agent | source selection, evidence interpretation, hypothesis comparison and user-facing explanation | Read-only. It cannot approve, decide authoritative state, or execute effects. |
| Deterministic control plane | eligibility, exact proposal, approval binding, execution, reread and verification | Enforces the actual safety rule and writes only to the synthetic ERP-shaped store. |

## Agent investigation contract

The live activity panel displays a bounded chain rather than decorative animation:

1. Read the PO line's match level, invoice hold code, receipt history and current stock.
2. Read warehouse/ASN evidence to establish physical arrival.
3. Read the quality record using `(supplier, item, lot, PO line)` and validate the
   exact quantity and expiry.
4. Read the integration record by correlation/trace key and its immutable business
   key.
5. Re-read ERP by each business/idempotency key before proposing a retry or transfer.
6. Publish an evidence-cited explanation, alternatives ruled out, and a bounded
   proposed action packet.

Every UI event must carry source, record ID, correlation ID, observed timestamp and
status. A failed or stale source is rendered as failed/stale; it cannot silently fall
back to scripted evidence.

## UI and video narrative

The dashboard should prioritise three things only:

- an opening operational picture (`100 arrived / 80 available / invoice held`);
- a visible evidence stream as the agent reads each source and rules out hypotheses;
- the before/after proof after manager approval.

The Agent workspace can show the causal branch card and chat follow-ups such as “Why
not retry?” and “Which record proves the quality lot is safe?” The answers must expose
the same admitted evidence IDs used by the advisory result. Security edge-case screens,
generic topology diagrams and explanatory grey microcopy are excluded from the primary
recording path.

## Error handling and truth boundaries

- External write adapters remain disabled unless an explicitly configured synthetic
  ERP executor is in use; no dashboard element may imply a provider write.
- Source unavailability produces `NEEDS_EVIDENCE` and visibly marks the relevant
  source stale/unavailable.
- A model answer that lacks admitted evidence, reports a write, or selects a
  disposition incompatible with deterministic guard facts is rejected as
  `VALIDATION_FAILED`.
- “Unknown integration outcome” is a first-class state; it cannot be represented as
  `failed write` without a business-key reread.

## Acceptance tests

1. **Normal run:** 100 available; receipt and transfer keys present once; invoice not
   held; source events reach the SSE ledger.
2. **Primary incident:** 80 available, 8 quality hold, 12 uncertain receipt, held
   invoice. The Agent makes all required reads and produces a cited proposal.
3. **Primary recovery:** one Manager approval permits exactly the 12-unit receipt and
   8-unit transfer. Rereads prove 100 available, resolved hold and no duplicate keys.
4. **Unknown-outcome counterfactual:** existing receipt/transfer key causes reconcile
   only; executor effect count remains zero.
5. **Quality-stop counterfactual:** invalid quality evidence causes no proposal/effect
   and preserves the invoice hold.
6. **Advisory integrity:** real Strands runs call the admitted source tools, cite only
   returned IDs and claim no writes. Provider errors fail closed.
7. **Browser E2E:** Dashboard and Agent Workspace receive ordered, source-labelled
   state changes and all displayed action states reflect API responses.

## Deliberate exclusions

- No claim that every logical source is an MCP integration; use MCP only where
  genuinely connected and call other boundaries API/webhook-backed.
- No need to reproduce every ERP vendor's exact hold code or UI. The demo labels the
  records synthetic and names the configured matching rule.
- No live payment, external stock, Slack, Airtable, Celigo or ERPNext mutation is
  required for the judge video.
