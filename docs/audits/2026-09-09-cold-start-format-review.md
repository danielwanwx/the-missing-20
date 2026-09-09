# Independent cold-start formatting review

Date: 2026-09-09. Frozen comparison parent: `f9438727c39d9b7b00159dd878ff430c20df16f0`.

**APPROVE the 38-file Python formatting-only scope plus the separately reviewed runtime-neutral typing correction in receiving_advisory.py. No P0/P1 found in that scope.** This is not approval of the two separate semantic Python changes, JavaScript empty-state changes, full cold-start acceptance, live provider behavior or F03 conversation reliability.

## Method and independent result

Read tracked working-tree diff names, retrieved each original Python file directly with `git show HEAD:<path>`, parsed original and current source using Python `ast.parse`, and compared `ast.dump(..., include_attributes=False)` byte-for-byte. This does not rely on the implementer's saved pre-format AST assertion. No diagnostic script was imported or executed; particularly `prepare_receiving_lost_ack.py` was parsed as source text only, so the review made no ERP write or model call.

At the first freeze, 41 tracked Python files differed from HEAD: 39 had identical complete ASTs and two had declared behavioral/test changes. A subsequent mypy fix adds a third AST-different file, `receiving_advisory.py`, independently reviewed below as runtime-neutral. The final approved counts are 38 strictly AST-equivalent files plus that one typing-only correction. The two behavior/test changes remain separately reviewed:

- `src/the_missing_20/adapters/erpnext_source.py`: blank/whitespace case ID now falls back to DEFAULT_CASE_ID.
- `tests/test_agent_platform.py`: isolated environment/root and explicit network guard for the live-adapter selection test.

Both exceptions match the parent's declared scope and are assigned to the other independent reviewer; they are not mislabeled formatting here. The JavaScript change is outside this review. New/untracked files are not covered by this HEAD-to-tracked-file comparison.

AST equality includes literal string values. Thus the two reported long-string splits did not insert/delete whitespace or change the actual strings. All expressions, calls, imports, argument values, assertions and control structures in the 39 equal files are preserved. AST comparison intentionally ignores source line/column locations, comments and textual formatting; it does not imply every possible tool dependent on physical line numbers is unchanged. No such change was demonstrated in this scope.

## Executed checks

- `.venv/bin/ruff format --check` on the 39 formatting-only paths: **39 files already formatted**, exit 0.
- `.venv/bin/ruff format --check src tests scripts`: **233 files already formatted**, exit 0.
- `.venv/bin/ruff check src tests scripts`: **All checks passed**, exit 0.
- `git diff --check`: exit 0.

An additional broad `.venv/bin/ruff check .` passed. The broader-than-Makefile `.venv/bin/ruff format --check .` reported four unformatted paths outside the project's `src tests scripts` lint target, including AgentCore runtime files and local audit artifacts. That command did not pass and is not represented as a passing gate. These paths were not edited by this reviewer, and the Makefile lint scope above passed. Do not expand this approved patch to sweep unrelated/local files into Git.

The parent is running `make check` separately. Its final results and the semantic review remain required for the combined cold-start release. This reviewer did not rerun a full suite for an AST-equivalent formatting patch or execute actual ERP diagnostics.

## Final approved strictly AST-equivalent paths

- `scripts/decision_workspace_server.py`
- `scripts/diagnostics/exercise_receiving_interleaving.py`
- `scripts/diagnostics/prepare_receiving_lost_ack.py`
- `scripts/diagnostics/verify_barcode_browser.py`
- `scripts/diagnostics/verify_barcode_dialogue.py`
- `scripts/diagnostics/verify_receiving_conversation.py`
- `scripts/diagnostics/verify_receiving_handoff.py`
- `scripts/diagnostics/verify_receiving_jira.py`
- `scripts/diagnostics/verify_receiving_replay.py`
- `scripts/provision_goods_demo.py`
- `scripts/run_goods_workspace.py`
- `src/the_missing_20/adapters/agent_platform.py`
- `src/the_missing_20/adapters/ambiguous_case_platform.py`
- `src/the_missing_20/adapters/conversation_views.py`
- `src/the_missing_20/adapters/live_advisory_gateway.py`
- `src/the_missing_20/adapters/operational_history.py`
- `src/the_missing_20/adapters/operational_metrics.py`
- `src/the_missing_20/adapters/photo_receiving.py`
- `src/the_missing_20/adapters/receiving_draft_worker.py`
- `src/the_missing_20/adapters/receiving_handoff.py`
- `src/the_missing_20/adapters/receiving_jira.py`
- `src/the_missing_20/agents/live_advisory.py`
- `src/the_missing_20/agents/role_delegation.py`
- `tests/test_advisory_context_regressions.py`
- `tests/test_conversation_views.py`
- `tests/test_evidence_completion_hook.py`
- `tests/test_goods_receiving_provision_scope.py`
- `tests/test_live_advisory_gateway.py`
- `tests/test_operational_history.py`
- `tests/test_photo_receiving_concurrent_upload.py`
- `tests/test_receiving_advisory.py`
- `tests/test_receiving_answer_coverage.py`
- `tests/test_receiving_arrivals.py`
- `tests/test_receiving_handoff.py`
- `tests/test_receiving_jira.py`
- `tests/test_receiving_platform_link.py`
- `tests/test_role_delegation.py`
- `tests/test_source_probe_acceptance_reporting.py`

## Delivery boundary

The formatting portion may be staged with the independently reviewed cold-start repair only after its own semantic review and required checks pass. Preserve the two AST-changing files as intentional behavior/test-isolation changes in the commit description rather than presenting all 41 files as no-op formatting. Do not include unrelated untracked runtime data, diagnostic artifacts or secrets. No code was edited and no commit/push was performed by this reviewer.


## Supplemental freeze: mypy cast correction

After the first formatting freeze, `make check` exposed two typing errors in `receiving_answer_gaps`. Independently reviewed the only extra changes in `src/the_missing_20/agents/receiving_advisory.py`: importing `typing.cast`, wrapping count `v` as `cast(int, v)`, and wrapping mean as `cast(float, mean)`. Both wrappers are inside the existing short-circuit guards: all counts have exact type int, or mean has exact type float/int. No condition, literal, evaluation branch or checker obligation changed. `typing.cast` returns its value unchanged; it does not convert the integer mean to a float or change rounding.

Performed a second structural check: remove only the `typing.cast` import and the two identity wrappers from the current AST, then compare with HEAD's complete AST. **Equal.** Thus no other semantic change is hidden among that file's formatting edits. This is explicitly a typing correction, not strictly identical AST, and must be described accurately in the commit.

Executed `tests/test_receiving_answer_coverage.py`: 11 passing test indicators, exit 0. Changed-file Ruff lint and format checks also passed. Approve this bounded runtime-neutral typing correction. The full Make check rerun remains the parent's release gate; this review does not erase its previous failure or assert the rerun's outcome before completion.
