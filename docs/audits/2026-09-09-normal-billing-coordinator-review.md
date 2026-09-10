# Normal receipt billing coordinator review

Status: independently APPROVED for the offline coordinator boundary, including
the subsequently discovered repeated-readback status correction.
Scope: compose the accepted source reader, pure source context, native request
binding and durable journal through the existing configured ERP request callable.
This candidate has not created or submitted a real invoice and is not wired to
the product HTTP/UI. Financial-effect and same-order downstream acceptance remain open.

## Implemented boundary

The trusted application resolves the case's synthetic billing basis; each
operation checks it against the journal's frozen basis. Every source read gets
a new reader. Insert and first submit compare current complete source evidence
before claiming the journal's single attempt. Transport sends the marked native
method/path/body unchanged. Only this insert's actual validated response may
bind the first draft identity. Lost insert acknowledgement does not permit
search adoption or another insert. A known-name submit is followed by exact
direct readback, including after a lost submit response; later recovery reads
instead of resubmitting.

Own-draft classification retains raw evidence and does not exempt foreign
invoices, same-bill collisions, returns or changed source facts. Submitted
readback validates against current PO/PR without requiring the normal mapper
preview to remain READY after the invoice exists. If fresh parent collection
throws, direct known-name GET is still attempted and retained, while admission
remains blocked without valid current parent evidence. Approval issuance stays
outside this coordinator in the existing application/journal boundary.

## Independent findings and correction

Standards review of the first frozen candidate found no documented-standard
violation. It noted existing strict-JSON codec duplication and small repeated
claim-envelope checks as maintenance heuristics; no new shared framework was
requested. Spec review independently ran13 integration tests successfully but
found a P1: successful reconciliation discarded the fresh source observation
used for validation. A unique marker added to the fresh PO was absent from the
entire journal history despite submitted admission.

The correction records the full fresh source, manifest, observation time and
exact direct GET through the existing journal readback-observation path before
admitting the submitted proof. It does not refresh unfiltered commercial state
or add a table. The pre-admission UNKNOWN observation expresses that the
document has not yet been admitted; the succeeding proof admission determines
the document result. Intermediate independent verification passed15 tests with
unchanged hashes. Primary review found that malformed response envelopes still
were not retained; the same correction was completed for missing data, invalid
documents, list and null JSON responses. Each is retained privately without
admitting a draft name or permitting another insert.

Final independent review passed18 integration tests and reran the original
standalone marker counterexample. The fresh PO marker now survives reopening
the journal, with one insert, one submit and `source_changed=False`. It found no
remaining P0/P1 in this scope. A reviewer harness import initially failed before
execution and was corrected; it was not a product failure.

Primary related regression passed226 preview/source/native-request/journal/
context/coordinator tests in39.02 seconds, exit0, with all12 source/test hashes
unchanged. Primary final formatting, Ruff and strict mypy also passed on both
coordinator files before commit.

Original independent failure: `/private/tmp/m20-coordinator-audit-repro-ehws_zen`.
Original independent suite: `/private/tmp/m20-coordinator-independent-40sjp7as`.
Intermediate independent suite:
`/private/tmp/m20-coordinator-corrected-independent-ljaj_yl5`.
Final independent suite: `/private/tmp/m20-coordinator-final-independent-7xwpihni`.
Independent reopened-journal marker reproduction:
`/private/tmp/m20-coordinator-final-marker-gh7wc3rh`.
Primary related regression: `/private/tmp/m20-coordinator-final-related-g9ec51_9`.

| Final file | SHA256 |
| --- | --- |
| coordinator | `aa1fd1aff879ef262946925371668150ae70a23e75c33116d375b3e40820a49f` |
| coordinator tests | `5c1806d5cf1f962d87fcaed9f5206781dfc584bb1136071e683bf860f84ef2fd` |

### Subsequent repeated-readback finding

The accepted slice was delivered as `b19fad38618a3c1ace12bd1ae842539682303629`
with matching remote SHA. A later independent counterexample found that a
successful repeated reconcile leaves `last_readback_kind=UNKNOWN`, although
`admitted=True`, the submitted phase and invoice identity remain correct. The
one insert/one submit limits remain intact. The observation's separate UNKNOWN
event updates the latest kind, while the existing reaffirmation branch does
not restore SUBMITTED. Reopening the journal preserves this discrepancy.
Evidence: `/private/tmp/m20-coordinator-reaffirm-review-jk8cbju3`.

The independently approved correction attaches the raw observation to a neutral
journal audit event inside the admission transaction, without changing status
to UNKNOWN; both successful admission paths set the latest kind to SUBMITTED.
True unknown and no-hit outcomes retain their existing behavior. Optional audit
data is strictly detached JSON, records no new authority and remains captured
when proof admission is rejected or conflicts with immutable first identity.

Independent review passed42 targeted tests and the original standalone repeated
readback/reopen counterexample. First, repeat and reopened snapshots now retain
SUBMITTED, with one insert and one submit. Events pair OBSERVED→ADMITTED and
OBSERVED→REAFFIRMED within the existing transaction. Primary related regression
passed228 tests in18.581 seconds, exit0, with all12 source/test hashes unchanged.

Independent tests: `/private/tmp/m20-atomic-readback-independent-74teqil4`.
Independent reproduction: `/private/tmp/m20-atomic-reaffirm-repro-schm76ct`.
Primary related regression: `/private/tmp/m20-billing-atomic-related-5hco1wfn`.

| Corrected file | SHA256 |
| --- | --- |
| journal | `ebb3c696a56d6d13ffe061f5da7de3661575fb8359be91d1068183d6ed829dd9` |
| coordinator | `0cfdbe164166c653f933c089b247c7355fd16fa98fde965ac694c4f4ffb9561d` |
| journal tests | `05e0015298469991d98f92563eb49fd0b2afe7a80666e01175800d4f8d400439` |
| coordinator tests | `51e81c38448c00320e821f715bd0750784ab60b9aaa7d72c0d029a1f1e6eb36c` |

## Fresh R4 evidence and remaining acceptance

At `2026-09-10T05:46:09.514925+00:00`, a separate current read completed13
allowlisted requests:12 GETs and one native mapper returning an unsaved proposal.
The disclosed synthetic bill remains1 Box / USD50 for R4 PO16 / PR7. Preview is
READY with `write_allowed=False`. No coordinator execution, approval or financial
write occurred. Full private observation:
`/private/tmp/m20-r4-billing-source-current-read-02.json`, SHA256
`8ab65dc841114c8610d2eaae1ba5d8cf7364b9be202bf412b5cb0f2a46d4e361`.

An offline call to the accepted pure context compared that observation with the
earlier actual source preflight, using the earlier bound insert request. Both
contexts are READY and their commercial records are equal despite later read
time and native mapper timing. This is actual-source comparison evidence, not
an invoice effect. Private comparison:
`/private/tmp/m20-r4-billing-two-observation-context-02.json`, SHA256
`2baa44a3f1886a09a0e632d3d6f7a2099d017bd96b748cf79fa99c61dc622dd2`.
The independent reviewer verified both private files, hashes and0600 permissions.

The frozen context's separate full Python regression remains incomplete after
its900-second envelope:1,432 passing indicators and2 skips, unchanged four-file
hashes, no reported assertion failure. The identified10,005-transaction ledger
test completed and the suite advanced; no permanent deadlock was observed.
These results cannot substitute for a completed full regression.

Next acceptance boundaries are the product's concrete bill preview and manager
action, actual same-order invoice submission/readback, complete exact-voucher
GL/SLE verification, unchanged original receipt stock evidence, and visible
restart/replay behavior. Customer fulfillment is a distinct later step.
