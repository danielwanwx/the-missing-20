# MCP-enabled multi-SaaS quality-release demo design

**Date:** 2026-09-02
**Status:** Approved design; implementation has not started.
**Purpose:** Turn the existing ERPNext incident demo into a credible, recorded
multi-SaaS agent workflow without claiming unsupported integrations or creating
chargeable vendor subscriptions.

## Outcome

The recorded demo shows a normal incoming-goods flow, then a deliberately
ambiguous production-availability incident. The Agent reads independent systems,
forms a causal diagnosis, records a CAPA, alerts a manager, and—only after a
manager decision—makes one bounded ERPNext repair and rereads all affected
records.

The target is a quality-release synchronization failure, not a visible arithmetic
mistake:

> A supplier delivers 20 ECU controllers. ERPNext has 12 in production Stores
> and 8 in Quality Hold; the supplier invoice is held. The Supplier Quality
> Registry has an approved release for the same lot, while Celigo records a
> failed `quality.release` delivery with no ERP acknowledgement. The Agent must
> prove that the remaining 8 are safe to release, rather than incorrectly
> replaying a receipt or treating them as physically missing.

## Systems and authority boundaries

| System | Authority | Integration path | Agent permission |
| --- | --- | --- | --- |
| ERPNext | PO, receipt, physical inventory, stock transfer and payable hold; **sole write system** | Constrained Frappe REST adapter | Read by default; an isolated executor performs one allowlisted repair only after manager approval |
| Airtable Free | Supplier Quality Registry: lot, PO line, CoC/PPAP, accepted quantity, release disposition, correlation id | Airtable hosted MCP | Read during investigation; controlled registry updates only when explicitly needed |
| Celigo trial | Integration run, error, retry and acknowledgement evidence | Celigo connection/flow execution APIs | Read-only evidence; it never becomes the financial or inventory source of truth |
| Jira Free | CAPA/non-conformance record, ruled-out hypotheses, manager decision, corrective action and verification closure | Rovo MCP only if available on the tenant; otherwise Jira REST API | Create/update the dedicated case; no destructive bulk operations |
| Slack Free | Human-visible alert, investigation milestone, manager-notification and closure trace | Slack API/events; MCP is optional and must be proven before being claimed | Post only to the dedicated incident channel |
| Google Sheets (optional) | Supplier-uploaded certificate or exception sheet | Sheets API plus Drive webhook | Supplemental evidence only; never the decisive release authority |
| Notion Free (optional) | SOP/runbook and post-incident narrative | Notion hosted MCP | Read runbook and write a final report; not an operational source |

The demo says precisely: **MCP is used where a provider offers and the tenant
proves an MCP path; official API/webhook adapters are used elsewhere.** It must
never imply that ERPNext, Celigo or Slack are being accessed over MCP when they
are not.

## Correlation contract

Every cross-system fact is matched on a constrained tuple:

`(supplier_id, item_code, supplier_lot, purchase_order_line, release_correlation_id)`

The Agent must stop rather than repair when any decisive record lacks this tuple,
when the approved quantity is less than eight, when the release is expired or
rejected, when a matching ERP transfer already exists, or when the invoice
lineage does not match the receipt.

## Normal baseline

1. ERPNext: PO, receipt, inventory and payable records show 20 received and
   20 production-available; the linked invoice is not on hold.
2. Airtable: the same supplier lot has an approved release and attached
   certificate metadata.
3. Celigo: `quality.release` shows a successful delivery and ERP acknowledgement.
4. Jira: no open CAPA exists for the correlation tuple.
5. Slack: no incident alert is active.

## Incident and agent flow

1. An incident is created through the real ERPNext demo surface: 12 units remain
   in Stores, 8 remain in Quality Hold, and only the linked invoice is held.
2. Dashboard detection shows symptoms only: production shortfall, quality-held
   quantity and invoice hold. It does not display a root cause.
3. The Agent starts automatically and streams every evidence read as a dated,
   append-only activity item.
4. It reads ERPNext PO, receipt, warehouses and invoice; rules out a physical
   shortage and duplicate-payment explanation.
5. It queries the registry by the correlation tuple and confirms an approved
   release for eight units.
6. It reads Celigo execution history and confirms upstream acceptance but no
   ERP transfer acknowledgement.
7. It creates or updates one Jira CAPA with source links, hypotheses, bounded
   recommended action and verification criteria; it emits a Slack manager alert.
8. A manager approves one proposed action: transfer exactly eight units from
   Quality Hold to Stores and unhold only the linked invoice.
9. The executor performs the idempotent ERPNext repair. The Agent rereads
   ERPNext, updates Jira with the actual resulting quantities/statuses and posts
   the verified closure in Slack.

## Safety model

- No payment method, upgrade request or paid trial is used for new services.
- Siemens/Opcenter X is excluded: the trial page excludes competition use and
  its product-level conversion terms could not be safely verified.
- Dedicated credentials are least-privilege and per system. Existing ERPNext
  credentials with execution authority must not be placed in Celigo.
- Celigo may read from a dedicated ERPNext observer credential, while the
  manager-approved executor uses a separate local secret and allowlisted action.
- Agent proposals are data, not executable instructions. All tool parameters,
  correlation identifiers and mutation bounds are validated server-side.
- No SaaS credential appears in browser JavaScript, client events, logs or git.

## Evidence required for the recording

The final video must visibly show:

1. real ERPNext normal and incident records;
2. a real Airtable release record for the same immutable tuple;
3. a real Celigo run/error/retry artefact;
4. a Jira CAPA changing from investigation to approved remediation to verified
   closure;
5. a Slack alert and closure message;
6. dashboard live activity whose rows are sourced from the actual reads/actions,
   not a timer-only animation;
7. before/after ERPNext reread proving Stores = 20 and the exact invoice hold
   is removed.

## Acceptance criteria

- Every displayed investigation fact has a visible source system, object id and
  timestamp.
- A fresh incident can be triggered from ERPNext and propagates to the dashboard
  without manually editing dashboard data.
- The Agent cannot make the ERP correction before a manager decision.
- The same incident rerun is idempotent: it neither double-transfers inventory
  nor releases an unrelated invoice.
- The demo remains replayable for recording: event replay is deterministic when
  third-party systems are unavailable, and the UI labels that fallback rather
  than presenting it as live.
- Billing/settings pages for every created SaaS account are captured as proof
  that no card, upgrade or auto-conversion is enabled.

## Explicit non-goals

- Simulating a Siemens QMS, SAP Business Network or WMS tenant that does not
  exist.
- Using Jira or Slack as an inventory source of truth.
- Adding Excel/Microsoft 365 solely for a vendor logo; consumer OneDrive does
  not support the needed Graph Excel API boundary.
- Adding duplicate work trackers such as Asana alongside Jira.
