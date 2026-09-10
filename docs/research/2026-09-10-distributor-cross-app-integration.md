# Same-order distributor cross-app integration

Approved product behavior: the actual distributor case, not the historical photo
case, updates Airtable/Jira and sends meaningful scoped demo Slack notices.
Implementation and external acceptance are pending.

## Reuse and current evidence

`ReceivingAPI`, `HandoffJournal`, Jira ADF/transition patterns and the existing
Celigo Slack import provide native transport, durable attempt identity and
readback. Do not install another agent/integration framework. The existing photo
worker remains unchanged; it cannot be wired to arbitrary distributor data by
fabricating a photo receipt.

September 10 read-only preflight: existing Airtable base schema, configured Celigo
import, Slack identity and configured Jira project search returned valid data.
Jira `/myself` returned 401 while the required project search succeeded; this does
not establish an expired project connection. No records or messages were written.

Native API references checked September 10:
- [Airtable API guidance](https://support.airtable.com/articles/7735693959-managing-api-call-limits-in-airtable)
  documents batching and `performUpsert` for finding/creating/updating records.
- [Jira issue API](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/)
  separates issue edits from workflow transitions. Use actual available transitions,
  not a hardcoded status ID; retain the existing separate comment/readback pattern.

## Small integration boundary

Input: current verified case projection, retained agent allocation decision,
contract references, native documents and explicit physical-evidence basis.
Consume semantic business revisions, not timestamps or unchanged polls.

- Airtable: one case summary keyed by case ID in an explicitly scoped distributor
  table. Store PO/item/unit, received/held/missing/dispatched/recorded-confirmed
  quantities, customer impact, agent decision references, Jira and ERP links.
  Update that record on meaningful changes; keep history in the existing journal.
- Jira: create an operational exception task when evidence shows a shortage or
  quality/fulfillment problem. Add evidence and decisions to that same task as work
  proceeds. Resolve only from the specific reconciled condition. Supplier
  responsibility remains unknown unless independent evidence establishes it;
  an explicitly open responsibility investigation must not close with fulfillment.
- Slack via Celigo: scoped demo milestone messages for actionable exception,
  material allocation/recovery and verified completion. Include case/PO and exact
  links. No message per chat turn, GET or unchanged refresh. No external customer
  messages or real carrier booking.

The agent supplies the actual allocation choice and rationale. Structured fields
come from authoritative calculations, not model-generated arithmetic. Do not
claim all text was model-written when a deterministic template was used.

Use the existing journal with explicit case/revision business keys. A provider
failure is retained per destination without undoing a verified ERP effect. An
unknown write is reconciled by readback, not blindly resent. This is a bounded
demo integration, not a general cross-provider transaction platform.

Expose exact provider record IDs/URLs/status/readback times in the distributor UI
and fresh read-only agent source packet; replace current case `UNAVAILABLE` only
when actual evidence exists. Do not inherit another case's source badges.

## Acceptance

One new same-order walkthrough must show initial discrepancy, updated customer
allocation, supported quality/replacement progress and operational resolution in
the actual provider pages. Repeating the unchanged event/poll must not add another
case/task/message. Disconnecting one source must be visible and must not produce
a fabricated completion. Original photo handoffs and read-only chat stay intact.
No broad reliability matrix or new framework is required for this slice.

## Independent design review

Terra High returned scoped GO before implementation. Required distinctions:
Airtable identity is case ID; Jira creation identity is case plus exception
lifecycle, never each revision; revision keys apply to journaled updates and
messages. Preserve the actual selector decision ID, selected compiled plan and
policy version, contract references and rationale; DEFER is not an allocation.
Name the resolved operational condition precisely. Fulfillment milestones must
not silently resolve a retained unknown operation or responsibility investigation.
Provider preflight is not case-specific external acceptance.
