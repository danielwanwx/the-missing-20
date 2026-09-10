# Accepted billing source context and journal accessors

This slice connects one source observation to the existing invoice request and
journal contracts. It contains no ERP transport or UI integration and does not
establish a real invoice, GL or stock-ledger effect.

Before an insert acknowledgement, the unfiltered source must produce a READY
preview. After an acknowledgement has been stored, the comparison view may
exclude exactly one invoice only when its name, full document and bound request
match that acknowledgement and a fresh direct-name read. All original source
documents, coverage and read evidence remain in the immutable audit record.
Foreign invoices, duplicates, returns, incomplete scope and document mismatches
still prevent submission. POST/GET document equality is a conservative condition,
not a universal Frappe API guarantee.

The commercial fingerprint follows the journal's existing exact field contract.
Document ordering and observation/pagination audit changes do not invalidate
approval; business document and PO/PR revision changes do. The journal stores
optional raw audit evidence outside that fingerprint and exposes two read-only
accessors through its existing strict stored-request/ACK parsers.

Independent review found a P1 in the initial candidate: the builder's expanded
field maps produced `ready=True` but failed actual `journal.prepare()` with
SOURCE_IDENTITY_MISMATCH. The builder was corrected without relaxing journal
admission. The new seam test executes context→prepare→approve→insert marker→ACK→
own-draft comparison→refresh, including audit-only stability and sticky business
revision changes. This correction was independently accepted.

Verification of the final four-file candidate:

- 208 related preview/source/request/journal/context tests passed.
- 32 independent context/journal tests passed in a retained private base directory.
- Primary verified formatting, Ruff and strict mypy on all four files in a detached
  copy based on `ecb4e349d050a7cf531f7e74ea5a49ea521e387f`.
- The first broader Python run timed out at180 seconds; no full-regression pass
  is claimed from it. A focused existing golden case produced a passing test
  indicator but its wrapper reached60 seconds. The corresponding prior baseline
  case exited0 in30.24 seconds. The diagnostic full run also reached180 seconds,
  after132 passing test indicators and no reported assertion failure; its code
  hashes were unchanged. These incomplete runs are not full acceptance.
- A third full run reached its900-second envelope and was stopped by its owning
  wrapper (exit-9), again with all four hashes unchanged and no reported assertion
  failure. Raw output advanced beyond73%; this is still incomplete, not a pass.
  Independent read-only diagnosis located a completed bottleneck in
  `test_ledger_tail_ends_at_latest_sequence_beyond_replay_limit`:10,005 individual
  durable SQLite appends. The test subsequently completed and the suite advanced;
  no permanent deadlock was observed. The retained sink stack does not establish
  a session-lock cycle or diagnose interpreter shutdown. Evidence:
  `/private/tmp/m20-context-final-python-ecb4e34-03`.

Independent evidence: `/private/tmp/m20-context-corrected-review-628y_3_x`.
Primary frozen copy: `/private/tmp/m20-context-accepted-ecb4e34`.
Broad timeout evidence: `/private/tmp/m20-context-final-python-ecb4e34-01`.

| File | SHA256 |
| --- | --- |
| context | `7d38c83be8dd7e4b0be21c28306e534c76d93325f9ac4fb71293995df4567218` |
| journal | `859afb3f3819ce7c89b09ed157ac0948074c10233eb2823ad18cb438eddfb112` |
| context tests | `38e79777cd92dca78765c80247b1749f23beba488dc81c29249e6d48191229a1` |
| journal tests | `77fa8911d87a848977c3668cf52efa5da5e9f026a1ceea61205c0cc1de5b5ca8` |

The accepted deliverable is this pure context/accessor boundary. A trusted
coordinator must still connect actual source reads, committed attempt markers,
native ERP requests and readbacks. Full finalization and same-order downstream
closure remain open.
