# Independent clean-checkout release review

Date: 2026-09-09. Public cloned commit: `85d6a159cb2d2782bf97b758d4d87de2c7c53de8`.
Checkout: `/private/tmp/m20-finalization-cold-20260909-release85d6`.
Role: independent release/reproducibility reviewer. No application code changed.

**Verdict: default installation/start is reproducible with local sandbox allowances, but the documented full quality gate and browser smoke FAIL.** Three distinct release defects are recorded below. This does not reverse acceptance of the preceding limited documentation correction, and does not prove live receiving, real model answers or current external business closure.

## Exact execution and scope

Cloned the public GitHub repository into a new directory and verified its full SHA. Read README quick start, `.env.example`, Makefile, server mode selection and smoke entry point. Copied only `.env.example` to `.env`; no existing private configuration/runtime was copied. Bootstrap used the lockfile and `npm ci --ignore-scripts`. Runtime/test commands cleared inherited environment except PATH/HOME and pointed both AWS credential/config files to `/dev/null`, with instance metadata disabled. No provider credentials were configured and no live business/model operation was requested.

Environment: Python 3.12.13, Node 20.18.3, npm 10.8.2, locked Ruff 0.16.4. `uv` was already installed, matching the README prerequisite. No new subscription or tool upgrade was performed.

| Step | Outcome |
| --- | --- |
| Public clone / SHA | PASS, exact commit above |
| Initial `make bootstrap` | Sandbox failure: uv default cache could not open `.cache/uv/sdists-v9/.git` |
| Bootstrap with temporary uv/npm caches | Sandbox DNS failure fetching Python wheel after retries |
| Same bootstrap with authorized network permissions | PASS; isolated caches under `/private/tmp`; npm reports 5 packages installed, 0 vulnerabilities |
| `make check` | FAIL at first Ruff format check: 39 files require formatting; subsequent make dependencies not reached |
| `make judge-demo` | PASS; validates retained historical 20-unit/42,000-billed snapshot, no fresh provider reads |
| `make case-console`, port 8919 | Initial sandbox socket failure; allowed run starts. Root HTTP 200; correct `/api/v1/agent-platform` HTTP 200, schema `missing20-agent-platform/v2`, provenance `synthetic-demo-fixture`, provider writes `LOCAL_SYNTHETIC_ONLY` |
| `make workspace-smoke` | Initial sandbox socket failure; allowed run FAILS existing dashboard 180-word limit, observed 227 |
| Independent `make typecheck test test-js` after preserved lint failure | Mypy PASS, 51 source files; pytest 1 FAILED / 1549 passed in 59.49 seconds. Make stops before JS |
| Separate `make test-js` | PASS: 98 tests, 0 failed/skipped |

An exploratory GET to `/api/v1/platform` returned 404; source inspection identified the correct route above. This reviewer typo is not a product defect. Smoke regenerates its normal fixture workspace outputs **only in the temporary clone**; no primary-repository artifacts were overwritten. Its early failure means later smoke assertions were not exercised. The clone's tracked tree remained clean after execution. The owned server was stopped through its own process session with Ctrl-C (exit 130), and port 8919 had no listener afterward. Smoke owns and closes its temporary server/browser profile; other user servers were not touched.

## P1: documented quality gate stops on 39 formatting failures

`make check` stops at `ruff format --check src tests scripts`, reporting 39 files would be reformatted and 191 already formatted. No formatting was applied, no exclusions added, and no assertion deleted. Exact files:

```text
scripts/decision_workspace_server.py
scripts/diagnostics/exercise_receiving_interleaving.py
scripts/diagnostics/prepare_receiving_lost_ack.py
scripts/diagnostics/verify_barcode_browser.py
scripts/diagnostics/verify_barcode_dialogue.py
scripts/diagnostics/verify_receiving_conversation.py
scripts/diagnostics/verify_receiving_handoff.py
scripts/diagnostics/verify_receiving_jira.py
scripts/diagnostics/verify_receiving_replay.py
scripts/provision_goods_demo.py
scripts/run_goods_workspace.py
src/the_missing_20/adapters/agent_platform.py
src/the_missing_20/adapters/ambiguous_case_platform.py
src/the_missing_20/adapters/conversation_views.py
src/the_missing_20/adapters/live_advisory_gateway.py
src/the_missing_20/adapters/operational_history.py
src/the_missing_20/adapters/operational_metrics.py
src/the_missing_20/adapters/photo_receiving.py
src/the_missing_20/adapters/receiving_draft_worker.py
src/the_missing_20/adapters/receiving_handoff.py
src/the_missing_20/adapters/receiving_jira.py
src/the_missing_20/agents/live_advisory.py
src/the_missing_20/agents/receiving_advisory.py
src/the_missing_20/agents/role_delegation.py
tests/test_advisory_context_regressions.py
tests/test_conversation_views.py
tests/test_evidence_completion_hook.py
tests/test_goods_receiving_provision_scope.py
tests/test_live_advisory_gateway.py
tests/test_operational_history.py
tests/test_photo_receiving_concurrent_upload.py
tests/test_receiving_advisory.py
tests/test_receiving_answer_coverage.py
tests/test_receiving_arrivals.py
tests/test_receiving_handoff.py
tests/test_receiving_jira.py
tests/test_receiving_platform_link.py
tests/test_role_delegation.py
tests/test_source_probe_acceptance_reporting.py
```

Acceptance: use the locked formatter on the reviewed release change, inspect that only layout changes, then rerun the unmodified full gate. A formatter pass alone is insufficient: later lint/type/test failures remain possible.

## P1: cold no-credential test fails current source projection

Failing test: `tests/test_agent_platform.py::test_server_live_case_console_mode_selects_authorized_read_adapter`, line 237. It selects live-source mode, removes the environment-mode override, constructs the server with the clean example configuration, and calls `server.agent_platform.current()`.

```text
AgentPlatform.current (agent_platform.py:2456)
→ _read_all (agent_platform.py:1871)
→ OperationalHistory.record (operational_history.py:412)
→ _observation (operational_history.py:255)
→ _label(..., "case_id", required=True) (operational_history.py:107)
ValueError: case_id is required
```

Observed input to `_label` is `None`. This is evidence that the no-credential current projection is not handled by this path, not proof of its exact intended fallback contract. Fix the missing-source projection/history admission boundary rather than supplying private tenant state to make the clean test pass. Retest the original test and default environment, then the full gate. No live tenant or actual provider call is needed to reproduce this failure.

## P1: default dashboard exceeds its existing presentation contract

Failure occurs in `scripts/run_decision_workspace_smoke.py:1057–1061`: baseline `visible_word_count > 180`. Observed count: **227**. The browser was reached successfully after socket permission was allowed. The selected surface includes the new goods input and expanded historical metrics; no later workflow pass may be inferred.

Actual extracted text below is whitespace-normalized for readability; the original unmodified extraction including whitespace is preserved in the smoke log. This is text inspection, not a new human visual-design score:

```text
Skip to operations
The Missing 20
Dashboard Investigation Count from photo Demo Controls
LIVE FLOW LIVE seq 1
All 100 units are accounted for
Live Inject incident Healthy
Live movement 0 changed records 100 expected 100 RECORDED 0 gap 1 ledger seq
Recent events 5 events
15:10:01 Control plane Supplier quality read Lot LOT-4817-QA covers 8 held units.
15:10:01 ERPNext Authoritative source baseline
0 new records · Warehouse 100 · Queue 100 · ERP 100 · Invoice 100
Latest · 15:10:01
Goods Photograph goods
Photograph a delivery to identify it and prepare receiving.
Business impact SUPPLIER ACTIVE INVOICE OPEN ORDER —
Order stock coverage 100.0% Revenue at risk — Issued for delivery — Billed revenue —
PO · receipt · quality · customer order · delivery · customer invoice · GL LEDGER 4
Trends & internal baseline Window Refresh
Controlled scenario · connected business history is separate
Received — Building baseline · 0/3 prior observations
Case balance — Building baseline · 0/3 prior observations
Quality hold — Building baseline · 0/3 prior observations
Invoice hold — Building baseline · 0/3 prior observations
Still to receive — Building baseline · 0/3 prior observations
Net billed sales — Building baseline · 0/3 prior observations
This measure is not available from the connected records.
Receipt posting LIVE Warehouse ERP posted Exception
Risk to billed revenue LIVE Working capital risk Supplier invoice hold Billed revenue
Risk, output & OEE 90 DAYS Risk score Schedule OEE
Monitoring
```

Acceptance: reconcile the intended current information hierarchy with the retained contract, preserving useful metrics and operation reachability. Do not simply hide the failure, increase the threshold without design justification, or remove meaningful business information to chase a count. Rerun the full browser smoke after the actual fix; it stopped early in this review.

## Retained raw evidence

All raw logs below remain local in `/private/tmp`; paths are reproducible investigation aids, not promised public release artifacts. This report preserves results and exact decisive failures in committed text. No private credentials occur in the printed results.

| Filename under `/private/tmp` | SHA-256 |
| --- | --- |
| `m20-finalization-cold-bootstrap.log` | `f92777326f9f52f680e567738665db202b708815aba8faf89b4e8b751fe5dd8c` |
| `m20-finalization-cold-bootstrap-tmp-cache.log` | `7f703861f8dbd1b03f1f0b8c5c068fe5e63d4988e1516f37b15ac512f389786f` |
| `m20-finalization-cold-bootstrap-network.log` | `f989e1493ee4e560ddaeb77ec0491f836c619a5211d2fa8d3243153f59e95d08` |
| `m20-finalization-cold-check.log` | `14370e6a523f12a20647f6a2821f3e91d56d44dd875ff9172d8b64ca3a68967a` |
| `m20-finalization-cold-judge.log` | `f61147d13ef89644a1037414d076a81a0a3113b4cba06ac78b27c1f71b1849ac` |
| `m20-finalization-cold-server.log` | `7044a4897b4a661471521ecb9d42093a18c380c3b1110426402380e700bdc018` |
| `m20-finalization-cold-server-allowed.log` | `6eb57c8b260b200521309fb17189b61b06d4011ab08490ef37a03cba1d439f88` |
| `m20-finalization-cold-smoke.log` | `65636636bd4691f51e0d6a5993432142ee75df0827574605ddb337b5cf6f7adc` |
| `m20-finalization-cold-smoke-allowed.log` | `444d7a4077f79802d28b3c2d09f38c20be59eedc292dae4564e4997564e860f2` |
| `m20-finalization-cold-remaining-checks.log` | `7cde343160fab5fb33a436ff82b2b78ef05775a23325a2780d47cfbd90de8e3e` |
| `m20-finalization-cold-js.log` | `2c0a6faa0ede7baee9f6c36d0408f18c66a2081b1c8c7fb91c2427c25989415e` |

Final scope: public code downloads and installs; synthetic default server starts; historical manifest validates; full documented checks and browser journey require fixes. Receiving live setup, current cloud access, camera input, external record writes and repeatable Agent semantics were not evaluated by this offline checkout. **Full release remains NOT READY.**

## Subsequent independent empty-state design review

The primary agent proposed replacing the six unavailable historical metrics only for the synthetic case without business-history observations. Reviewed `workspace/operations-history.js` render/refresh logic, its HTML and existing unit tests. Current render sets the synthetic status label but still unconditionally renders six metric radios whose baseline helper defaults to 0/3. A single specific empty state is a clearer and more accurate representation.

**Design approved, implementation not yet accepted.** Restrict it to `SYNTHETIC_CASE` with no valid business observations, not every empty filtered time window. Keep title, Window, Refresh and the controlled-scenario disclosure. Clear stale metrics/chart/samples/detail values and close empty details on case transition. Preserve real data, source-unavailable recovery, radio keyboard operation and sample inspection. Test synthetic→real one/multiple observations→synthetic transitions, unavailable-source retry and window changes; rerun the complete original smoke with the 180-word threshold unchanged. No new framework is justified.

## Candidate implementation review — limited approval

Reviewed exactly the eight added lines in `workspace/operations-history.js`; copied only that candidate file into the existing clean checkout. SHA-256: `0d7cc66377a376b6be01c69c842628fecfbcca60bdbab2076865423c467beafb`. No other cloned source or smoke assertion changed.

The original complete `make workspace-smoke` was rerun with allowed local socket/browser permissions. It passed the former dashboard-word-count location and continued, but **failed later**, so it is not a full smoke pass:

```text
authoritative incident transition failed:
{'incident': 'Incident M20-PO-4817', 'recorded': '88', 'gap': '12',
 'failed': 20, 'scenario_error': '', 'selected': 'incident', 'control_disabled': True}
```

Retained `/private/tmp/m20-finalization-cold-smoke-candidate.log`, SHA-256 `c7a53e672fea8a692e772f21fe2e2c12828cc9850cca1d04c4f993f6bee87981`. This later business-transition failure is outside the empty-state change; its cause is not established by this review. Subsequent smoke assertions remain unexecuted.

Visible Chrome mouse/keyboard inspection through CUA covered:

- Candidate synthetic server 8919: one controlled-scenario empty message, no six spurious 0/3 metric cards; Refresh remains enabled and preserves the empty state. Window successfully selects All retained. Title and controls remain visible. Screenshot inspected for this limited layout.
- Existing R4 server 8897: current page still shows one source observation, six real metric choices, Received 1 Box and Still to receive 39 Box. Mouse-selected Still to receive, then its sample. Details displayed 39 Box, `erpnext-missing20`, PO `PUR-ORD-2026-00016` and receipt `MAT-PRE-2026-00007`. Window All retained preserves that observation. Net billed sales remains unavailable. This is UI inspection of the current retained projection, not a new independent ERP readback or write.

A separate local Node VM/minimal DOM fixture executed the actual candidate renderer and mocked only DOM/fetch. Nine checks passed: synthetic empty; real one; real multiple; radio keyboard selection; real→synthetic clearing details; unavailable source; successful retry; synthetic status with actual points preserved; real history outside the selected window remaining non-synthetic. Eight mocked requests occurred. These are isolated software fixtures, not business observations or real-browser state-switch coverage. Fixture script `/private/tmp/m20-history-candidate-fixture.cjs` SHA-256 `0a0993a2b73160f70de4893a951f346c116d3431b6e1188bc6dac3498d017e11`; result `/private/tmp/m20-history-candidate-fixture.json` SHA-256 `bc096bb032380723d336296c1d3de8209b901f240c5721cfb97ee98cfd48d38e`.

**Approve the scoped synthetic-history empty-state implementation.** It removes misleading nonexistent baselines without hiding real points or raising the existing threshold. Current whole-dashboard visual acceptance, browser outage/case-switch testing, the later incident-transition failure and complete smoke remain open. The separate isolated 8919 server was stopped via its own session; R4 service was left running. No model call, confirmation, external record mutation or real payment was performed by this acceptance.

## Final independent no-credential quality-gate retest

Fetched public commit `0c01eaa1e9189cfc8b75328804549c3811ac3e6e` and reused the isolated checkout, its example-only `.env` and locked dependencies. The previously reviewed history file exactly matched this public commit (same SHA above). Ordinary checkout nevertheless rejected the local change; preserved it in a path-specific local stash, then performed an ordinary detached checkout successfully. The generated dashboard screenshot was separately copied to `/private/tmp/m20-cold-candidate-dashboard-preserved.png` and retained. No forced checkout/reset, private config or runtime import occurred. Initial sandbox DNS and checkout/old-base patch refusals were not product defects; patch application only proceeded after successful `git apply --check` on the correct public base.

Applied only the primary agent's reviewed Python diff, saved as `/private/tmp/m20-finalization-python-candidate.patch` (SHA-256 `3c738106aad32b31bbd365e30affb9ff9ff10473a3c27851cf22542bf856636f`), plus new `tests/test_cold_start_configuration.py` (SHA-256 `c1d6b5e3406a80f6c02a47cccb3dc14db80eade6b76ba5e1d1ebc1f56ed2d91b`). All 42 candidate Python files were byte-compared to the primary working tree: zero mismatches. The reviewer made no candidate corrections.

Independently ran the original complete `make check`, with inherited runtime credentials cleared and local test-socket permissions allowed. **Exit 0**:

- Ruff format: **233 files already formatted**.
- Ruff lint: **all checks passed**.
- Mypy: **51 source files, no issues**.
- Python: **1566 passed in 60.82 seconds**, no failures/skips.
- JavaScript: **98 passed**, no failures/skips.

Raw log: `/private/tmp/m20-finalization-cold-candidate-make-check.log`; SHA-256 `53c07f42944abecaae51ad8c9bd01da8fc945acbc28ec112f6cec0e63afe3040`. `git diff --check` also passed in this candidate checkout.

**The formatting and no-credential test failures are closed for this exact candidate. Approve its cold-start quality-gate acceptance.** This run does not close the separately retained later full-browser-smoke incident-transition failure, real-model semantics, full current UI or downstream business-chain gates. Prior failed runs remain above. Commit/push and remote SHA proof belong to the primary delivery step after this review; no reviewer commit was made.
