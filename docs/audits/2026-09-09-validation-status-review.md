# Validation failure presentation: scoped acceptance

2026-09-09, parent baseline 3b7cbc9. This change fixes failure classification, not model accuracy or product readiness.

Reproduction before fix: `PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_ambiguous_case_platform.py -k validation_failure_reports_answer_review -q` failed because a VALIDATION_FAILED result said to retry after provider availability. `node --test --test-name-pattern='selected case distinguishes' tests-js/degraded-dashboard.test.mjs` failed with Agent unavailable instead of answer review. An initial pytest entrypoint attempt lacked repository PYTHONPATH and failed collection; the corrected command above reproduced the actual bug.

Ranked hypotheses: backend shared generic summary; frontend combined validation/provider status; retry presentation obscured diagnosis. All three code paths were confirmed. Source policy and model behavior were not changed.

Fix: new validation failures display business-validation review in the summary, conclusion and activity. Dashboard distinguishes validation from unavailable runs. Investigation runtime no longer suppresses known provider identity solely because validation failed; manual retry is labelled Retry investigation. Generic unavailable runs do not invent provider recovery as the only remedy. No automatic retry, authority or approval changes.

Verification: 134 targeted Python tests passed with loopback permission (the sandbox run passed applicable tests but skipped three HTTP tests); 101 JavaScript tests passed; Ruff lint/format passed. Regression verifies SQLite reopen retains accurate failure classification, SAFE_STOP/no available execution, and Manager approval is rejected.

Mouse verification on isolated port 8899 replays the advisory from `artifacts/audits/2026-09-09-current-ui/02-diagnosis-failure.json` through current application recording. It is NOT a new model run or successful diagnosis. Opened Investigation and Run details: business-validation summary, ANSWER NEEDS REVIEW, VALIDATION FAILED and SAFE STOP present; retry is manual, no approve action. No ERP writes or new inference. Existing 8898 runtime contains old persisted summary text, which remains historical; this change does not rewrite historical events.

Independent code reviewer approved the four code/test files for this scoped fix, no P0/P1 safety regression. P2 retained: dashboard runtime identity may show generic Strands for failed runs while Investigation can display a supplied model name. Failed-advisory metrics may omit latency/tool counts in existing public payloads; screenshot metrics are historical replay, not fresh performance. No full UI or model semantic acceptance claimed.

Artifacts: `artifacts/audits/2026-09-09-validation-status/` includes targeted check output and screenshot. Screenshot is an intermediate local failure-replay view, not final demo proof. The original reasoning failure remains open, as do newly discovered QA transfer-completeness/approval-quantity counterfactuals. Next optimization must independently repair those source-policy boundaries before a new fact-view model experiment.
