# Distributor handoff adapter — scoped acceptance

September 10: independent Terra review returned code GO after concrete corrections.
This is adapter and target-schema acceptance, not a connected business-loop pass.

The adapter consumes the distributor projection, reuses ReceivingAPI and
HandoffJournal, updates one Airtable case, maintains one Jira operational lifecycle
with revision evidence, and sends Celigo/Slack notices for meaningful business
progress. It preserves actual allocation references/provider usage, ERP document
facts and synthetic-input boundaries. It does not infer supplier responsibility.

Review corrections retained: normal omitted empty Airtable fields are normalized
only when the expected value is empty; immutable Jira lifecycle events satisfy the
existing journal contract; Slack identity excludes unrelated document/readback
changes; dispatch completion outranks a retained allocation decision. The new
table helper creates compatible numeric and long-text fields and rejects missing
or wrong-type existing schema. These were implementation defects, not evidence
that a new integration framework was necessary.

Primary verification: 60 focused tests passed, including existing receiving
journal coverage. Worker Ruff/formatting and three-source mypy checks passed.
One test uses an actual DistributorOperations projection with a fake ERP bridge;
offline provider tests are not real external write acceptance.

Actual authorized Airtable schema provisioning succeeded. Independent fresh API
readback found `Distributor Cases`, table `tblme05Ij7n4t4bSf`, with all 16 required
fields. Its five quantity fields are number/precision 2. Private configuration
and readback live under `/private/tmp/m20-distributor-handoff-table-20260910*`.
No business case record, Jira issue or Slack message was created by this schema
check. No ERP or model call was involved.

Remaining: connect explicit runtime configuration to event-triggered handoffs,
expose retained/read-only provider evidence in the UI and agent packet, provision
a fresh instance, and verify the actual same-order records through the full
business walkthrough. GET and chat must remain free of external writes.
