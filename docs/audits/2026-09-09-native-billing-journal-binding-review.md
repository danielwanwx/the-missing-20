# Durable binding for the native acknowledged-invoice path

Independent code review accepts this journal prerequisite, following correction
and re-review of its [native proof dependency](2026-09-09-native-billing-request-proof-review.md).
The dependency was delivered as `3d2c8ba`, with exact remote SHA agreement.
Neither component performs external requests by itself.

The journal stores one complete insert request bound to the intent, version,
commercial source and disclosed bill before approval or an insert claim. It
durably marks each attempt before returning its payload. A bound, acknowledged
draft stores the exact server name and complete document; the first submit
claim derives its full `{doc: ...}` request from that saved draft. A missing
insert response remains unknown: generic matching-field readback cannot
establish ownership. A submit attempt can never be claimed again.

Refusal, stale commercial facts and identity conflicts block later writes while
preserving earlier attempts and evidence. The first acknowledged identity and
document digest remain immutable. Legacy unbound rows remain readable but
cannot issue write authority. One nullable SQLite column is migrated under
BEGIN IMMEDIATE; historical version bindings remain in existing journal events.
The newly unused legacy submitted-proof type and helper were removed.

This is a trusted adapter boundary. Types and digests cannot prove where an
HTTP response came from. The future coordinator must admit only its own actual
insert response, refresh commercial facts and the known draft before submission,
and establish exact invoice/GL/SLE closure afterward. No matching-field search
may be promoted into acknowledged ownership.

Primary verification of the final four-file candidate passed1,853 Python tests
in63.79 seconds, with all before/after file hashes unchanged. Independent review
passed37 targeted cases, including actual two-process insert competition and
schema migration, plus two-connection receipt-line competition. Primary and
worker Ruff format/check and strict mypy passed. The full run retained four
fork deprecation warnings; it completed normally without a timeout.

An earlier pre-freeze run had two legacy-proof expectation failures and hung
in the thread/barrier part of the competition test. Native stack sampling and
open-file inspection localized that wait; they did not establish an exact
SQLite deadlock cause. The test now initializes its independent connections
before the contested operation and bounds its barrier/future waits. An owned,
bounded three-case regression passed, followed by the complete focused and full
runs. The original failed run and paused implementation were preserved.

Frozen journal SHA256:
`9a94c73519e61637f497027749213077e4fbd5f99120f17046c2f6ad22173e10`.
Journal test SHA256:
`9253d11be0a90272e1f5d14d1ff1abb24af65139ffee6a58b71a527e6d82e882`.
Full regression: `/private/tmp/m20-billing-final-python-eyrundxh/`.
Paused source archive:
`/private/tmp/m20-paused-journal-before-accepted-replacement-01/`.
Only the four exact reviewed source/test files replaced that candidate.

F05 remains open: no coordinator, real PI, exact GL/SLE closure, downstream
fulfillment or UI path is delivered here. F03 conversation quality is independent.
