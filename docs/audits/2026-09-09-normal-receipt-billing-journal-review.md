# Independent offline normal-billing journal review

Verdict: **BLOCKED by P1 effect-identity binding.** Scope is the journal and its tests against the accepted preview and billing design/digest clarification. No model, ERP, HTTP or business writer was invoked. This is not executor or financial-closure acceptance.

Frozen SHA256:

- normal_receipt_billing_journal.py: `05eeb8b4c782d5fa34284e1c72ebbf28558d96164c618033e8ae202727142bfb`
- test_normal_receipt_billing_journal.py: `abaa5e6f9ded0eeb2eb25703dfa69c60e0abc20361c20cb72bb87975aaf0e4ee`

## Reproducible P1: known effect identity can be replaced

Using the test module's legitimate basis, preview, CommercialSource and ExactDraftReadback/ExactSubmittedReadback helpers:

1. Prepare and approve the intent, then claim its insert with the valid opaque token.
2. Admit an exact draft proof named PI-FIRST; it is admitted.
3. Admit the same proof with only draft_name changed to PI-OTHER; it is also admitted and replaces the known draft.
4. Claim submit; it is granted with PI-OTHER in the immutable submit payload.
5. Admit a submitted proof named PI-DIFFERENT; it is admitted despite differing from the draft targeted by submit.
6. Admit another submitted proof named PI-THIRD; it replaces the previously known submitted invoice. The final snapshot reports PI-THIRD.

All other company/supplier/bill/receipt/child/digest/commercial-version fields remain identical, candidate_count is1 and lookup_complete is true. This is not raw boolean proof or bypassing a constructor. `_exact_proof_reason` validates the commercial envelope but omits the already known/attempted ERP document name. The journal therefore permits contradictory effect readback to overwrite durable identity.

Minimal fix: once an exact draft is admitted, preserve that identity; reject a different draft as a conflict. Once submit is attempted, submitted proof must match the exact name in the frozen submit payload (not an overwritable current draft field). Once submitted identity is known, only that same identity may be reaffirmed. Preserve prior proof and attempt phase on rejection and prevent subsequent writes from treating the conflicting read as successful confirmation. Add before/after-submit and repeated submitted-readback counterexamples before correcting implementation. Do not silently rewrite history or infer a second invoice is the same effect solely from matching amounts and bill reference.

Reproduce offline with `PYTHONPATH=src .venv/bin/python`, `runpy.run_path('tests/test_normal_receipt_billing_journal.py')`, a temporary Path and the `_basis`, `_preview`, `_source`, `_journal`, `_approve`, `_claim_insert`, `_draft`, `_submitted` helpers. Use `dataclasses.replace` for the three names above and inspect ReadbackAdmission.admitted/reason plus the final snapshot. The reviewer obtained admitted results with reason None at every step and a granted submit.

## Other inspected boundaries and bounded checks

`BEGIN IMMEDIATE` encloses checks, markers, immutable payloads and events; returning a claim occurs only after context-manager commit, before any prospective external I/O. Insert and submit have separate durable markers, and unknown/no-hit observations do not reset them. Approval tokens are random, hashed, tied to one intent version and manager/case, consumed at insert, and invalidated by pre-insert reprepare. Reprepare refuses after an insert marker; version records retain prior envelopes. Source audit timestamps/digests are separate from the commercial fingerprint; source changes are sticky until explicit reprepare. Refusal/source-change state is orthogonal to retained effect phase. Business-key and receipt-line uniqueness address same bill and different-bill conflicts in the shared journal. These structural choices follow the design; they do not prove an external adapter's commercial testimony or freshness.

Canonical records reject non-string mapping keys and non-finite floats. Exact proof constructors enforce a real integer candidate count and boolean completeness. Records are recursively copied/frozen. The remaining identity omission above matters even with these checks.

Independent command excluding the process-race test: `pytest tests/test_normal_receipt_billing_journal.py tests/test_normal_receipt_billing_preview.py -q -k 'not two_sqlite_processes'`: **68 passed**. The initial full command stalled in the process-race test under this environment and was interrupted; no independent pass is claimed for that test. Worker-reported process-race success remains separate evidence. A corrected candidate requires rerunning the identity counterexamples and confirming its process-race result before acceptance.

The implementation is large for an offline journal, but its explicit transitions, immutable envelopes and transaction boundaries serve required failure cases. No line-count-driven rewrite is recommended during this correction. Keep the fix inside proof admission/name binding; do not expand into an ERP executor or add generic workflow infrastructure.

## Corrected identity-fence review — superseding verdict

**APPROVED for the offline journal slice.** This supersedes the earlier BLOCKED implementation verdict while retaining the original failure evidence. It does not approve an external adapter, live invoice operation, authority UI or completed business workflow.

Frozen corrected SHA256:

- normal_receipt_billing_journal.py: `e5225713687b202b1e7bdc63df53bf5ee8e0ea42be0f4852b3be56bcb204bc42`
- test_normal_receipt_billing_journal.py: `ca4baba14b5ac87509f8319a45442c5e87e021c65edae3581bbe5bc43a2536ff`

Independent combined journal/preview command now passes **71 tests**, including the actual two-process SQLite contention test, with zero skips. The corrected process test uses bounded fork/pipe polling, bounded joins and cleanup of only the processes it created. The review did not terminate any other worker or primary test process; the earlier interrupted run remains an incomplete historical run, not a pass.

Code and the new counterexamples confirm first admitted draft/submitted identity is immutable, and first submitted proof is compared with the immutable submit payload's draft_name. Name conflicts retain the original readback and effect phase, append the incoming conflicting proof to audit and persist a separate CONFLICT_HOLD. All subsequent write claims deny; reaffirming the same known identity does not clear that hold.

Independently replayed the original PI-FIRST→PI-OTHER draft replacement outside the suite: replacement is denied. After recreating the journal from the same SQLite file, PI-FIRST and conflict remain. A same-commercial source refresh and same-identity readback still cannot authorize submit, and reprepare after the insert marker remains denied. The suite separately verifies submit-target mismatch and attempts to replace known submitted identity. No source/approval reopening was found in this bounded correction.

The accepted boundary remains a durable local journal whose structured proofs are supplied by a future independently verified adapter. Its name binding is necessary evidence integrity, not proof that the ERP snapshot is authentic or complete. Current source refresh, exact accounting readback, real approval integration and all live crash/recovery effects still require their later implementation/acceptance gates. No product changes or external effects were made by the reviewer.

## Primary corrected-candidate verification

Primary independently reran the exact frozen corrected journal+preview suite:71 passed, exit0 (`/private/tmp/m20-billing-journal-primary-corrected.log`). Separate format, Ruff and strict mypy on both owned files passed. Both SHA256 values match the independent corrected review. This is a standalone offline journal; no application route, HTTP, model call, ERP effect or UI was exercised.

An earlier primary run of the pre-correction process test stalled after six test indicators and was terminated by a worker that mistook matching test-command PIDs for its own. It exited143 with no completed test result (`/private/tmp/m20-billing-journal-primary-check.log`), not a pass or an assertion failure. The worker was instructed to terminate only PIDs captured from its own launched process. The corrected bounded local fork test completed independently in both primary and reviewer runs; no portable spawn success is claimed.
