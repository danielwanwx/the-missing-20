# Quality evidence boundary repair

2026-09-09. Parent f08fbb4. This is deterministic policy/source-correlation hardening, not accepted real-model reasoning or an external QA workflow execution.

Independent source inspection identified two counterfactual bugs: unavailable transfer lookup was treated as absent, and an APPROVED record's quantity was discarded. Neither explains the earlier actual diagnosis failure, whose source was complete and approved 8 against 8 held. They are separate safety-relevant source-policy defects.

Reproduction: `PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_investigation_case_sources.py -k 'requires_complete_exact or must_cover_exact' -o addopts='' -q` produced 7 failures before repair: transfer unavailable/wrong scope, approved quantities 7/9/None/string/bool all incorrectly qualified. Initial hypotheses were discarded query completeness, ignored lot scope, and lost approval quantity. All were confirmed by code and deterministic counterfactuals.

Repair: transfer presence is nullable unless the source reports COMPLETE for the exact held-lot scope. A single finite numeric approval quantity must match held inventory for that lot; bool/string/nonfinite/missing values or ambiguous duplicates cannot qualify. Explicit unapproved disposition remains DENY, insufficient evidence remains NEEDS_EVIDENCE. No model prompt, budget, expected label or authority change; source-derived flags supplement original source records.

Independent review caught two additional branch regressions; both were reproduced red before correction: zero-QA receipt-only recovery must not require QA evidence, and explicit PENDING must remain DENY even when approval quantity is missing. QA gates now apply only to positive held stock. Already-complete and invoice-only branches retain their independent conditions. Known quantity mismatch blocks the combined proposed release; partial QA release is not introduced. Multiple held lots unsupported by the singleton query remain unqualified, rather than inferring global absence.

Tests: 51 focused cases passed, independently rerun with Ruff and diff checks. Reviewer also independently checked receipt-only, pending-without-quantity, invoice-only and complete branches. Policy retains write_authority NONE; READY only permits proposing existing bounded actions under the application gate, not writing autonomously.

Intermediate complete check: 1,579 passed / 1 stale-package failure. It ran before the final reviewer branch repair and cannot certify final bytes. Static package audit was then regenerated: only workspace/app.js byte count/hash from the prior failure-label optimization and resulting audit digest changed. This is a local offline metadata refresh, not a new readiness claim. Final full-gate result recorded below after completion.

Records under `artifacts/audits/2026-09-09-quality-evidence-boundary/` preserve original and reviewer counterexamples. No real model or business-system call was needed for the source-policy regression. First-turn model reasoning, native summary/session, same-order downstream, full UI and final release remain open; F03 remains FAILED.

Final frozen-code `make check` completed successfully: 1,582 Python tests and 101 JavaScript tests, zero test failures; 233-file format check, Ruff lint and 51-file strict mypy pass. Independent backend reviewer approved the final two-file source-policy correction after rerunning its 51 focused tests and four branch checks. Independent release reviewer verified the metadata refresh is exactly the three expected hash/size/digest fields, not a readiness change. No code changed during this final run; only audit/tracker prose was appended afterward.

Artifact formatting: two pytest diagnostic whitespace-only lines were normalized after capture; assertions, failures and counts are unchanged.
