# Dashboard source authority — independent product review

Date: 2026-09-09. Reviewer: independent competition/product reviewer. Scope: app.js source selection and legacy unit cleanup; no approval of overall finalization.

## Verdict

APPROVED for the limited flow/event authority correction and obsolete unit-surface cleanup. No P0/P1 regression found within those changed surfaces. Overall product remains NOT READY: the no-credential diagnosis stops safely, the complete workspace smoke still has a failed historical contract, the initial normal-mode defects below were subsequently closed in the appended retest. This is not acceptance of the complete agent recovery loop.

## Candidate and execution

Candidate app.js SHA-256: `960247e75a9cfb9a3842c9c097cd0441565392a0fbd64713a8cbcedddba716ee`. Copied candidate app.js, degraded-dashboard, scaffold and goods-semantics tests into the isolated public cold checkout `/private/tmp/m20-finalization-cold-20260909-release85d6`; no private .env or runtime copied. Independent `make test-js`: **99 passed, 0 failed**, exit 0. Raw log: `/private/tmp/m20-source-authority-js-final.log`. The additional goods-semantics regression executes rendering functions with a foreign selection, verifies identity/children/ARIA/count removal and inspector closure, then restores the normal surface. This is an isolated DOM fixture, not a live business observation.

Own no-credential server: loopback 8919, isolated runtime `.missing20-source-authority-review`. Browser: real Chrome controls through CUA. R4 server 8897 inspected read-only; no approval or business mutation performed. Screenshots are preserved as native tool images in this review conversation (not claimed as standalone repository artifacts).

## Observed coverage

| Action / observation | Actual outcome |
|---|---|
| Open default normal dashboard | Expected 100 / recorded 100 / gap 0; recent events exactly one normal baseline. No platform event rail leakage. |
| Click Inject incident | Title 20 units need reconciliation; expected 100 / receipt posted 88 / receipt unresolved 12; Warehouse 100 / Queue 12 / ERP 88 / invoice 0 held. Four platform events for the same synthetic case. |
| Open Investigation | Case M20-PO-4817: arrived 100, available case balance 80, QA hold 8, receipt unresolved 12, invoice held. Matches API and dashboard distinction between posting and availability. |
| Click Authorize diagnosis with no credentials | BLOCKED / Agent unavailable; Retry real Agent and manager retry-required state. No diagnosis/recovery plan released; safe stop. Reject/approve/execute controls cannot be reached in this configuration and were not falsely claimed exercised. |
| Return dashboard | Flow remains 100 / 88 / 12, platform event rail grows to 9 with unavailable-agent evidence. DOM read confirmed unit count 0, anomaly count 0, empty unit detail, hidden strip and closed hidden inspector. |
| Demo Controls → Normal | Flow restores 100 / 100 / 0 and one baseline event, excluding prior nine incident events. |
| R4 current dashboard | Title 1 of 40 Box received, expected 40 / receipt posted 1 / receipt unresolved 0; normal partial receiving is healthy. History shows received 1 Box, case balance 1 Box, still to receive 39 Box, net billed sales unavailable. Actual source history remains visible. No synthetic replay claimed as R4 reproduction. |

Same-version read-only snapshots are retained in `/private/tmp/m20-source-authority-review/`: `normal-platform.json`, `normal-scenarios.json`, `incident-platform.json`, `incident-legacy.json`, `normal-return-platform.json`, `r4-platform.json`. Synthetic case provenance is `synthetic-demo-fixture` with `LOCAL_SYNTHETIC_ONLY`, not live enterprise evidence. R4 snapshot SHA-256: `d8829d35dfab900f4c405128bd4d6323f4fc3b0c4f145ef7ad8546cc1767aed7`.

## Remaining substantive defects and limitations

1. **P1, existing normal-mode scope leakage outside changed event/flow surfaces:** after incident diagnosis fails and the user returns to Normal, the healthy normal flow and baseline event are accompanied by `Agent unavailable · retry required` and Business impact `LEDGER 9` from the previously selected platform case. Do not claim the entire dashboard now uses one source authority. Reset/scope these surfaces and add an actual mode-transition test before full dashboard acceptance.
2. **P1, existing normal queue label:** Normal displays `Message Queue, 100 unresolved, HEALTHY` while the top-level gap is 0 and ERP/invoice totals are 100. A warehouse viewer cannot interpret 100 as unresolved in a fully accounted baseline. Preserve the actual queue meaning and use an appropriate label; do not alter receipt-unresolved quantities to mask it.
3. No-credential diagnosis cannot progress to human reject/approve or confirmed execution. This review confirms safe stop and navigation only. A scripted substitute was not introduced, no external model call was made, and R4 was not used for a real write. These human-control paths need separate supported-runtime acceptance.
4. Full prior workspace-smoke remains failed; the current 99 JS result does not replace that gate, a new smoke contract, clean-clone end-to-end evidence or remaining business objectives.

## P1 correction and independent closure retest

The implementation owner corrected only app.js authority selection for agent state, Business impact sequence and queue semantics. I copied the new file into the same isolated clone and repeated real Chrome interaction: Normal → Inject incident (run-2) → Open Investigation → Authorize diagnosis → safe-stop unavailable → Dashboard → Demo Controls → Normal.

Final Normal showed **Monitoring**, **LEDGER 1** in Business impact and **seq 1** in flow, **Message Queue 100 published / HEALTHY**, expected 100 / recorded 100 / gap 0 and exactly one baseline event. Incident still showed 100 arrived / 88 posted / 12 receipt unresolved, and its failure remained visible only while that case was selected. Both initial P1 findings are **CLOSED** by the observed transition. Original findings above are retained as review history.

Independent make test-js rerun: **99 passed / 0 failed**, exit 0; log `/private/tmp/m20-source-authority-js-closure.log`. The final candidate app.js hash is recorded in the review tool output. Final verdict: **APPROVED for this bounded source-authority optimization**, including the P1 corrections. Full smoke, live model recovery and overall finalization remain separate gates. This no-credential Agent-unavailable result is not the separate real Bedrock NEEDS_EVIDENCE validation failure reported by the implementation owner at port 8898; this reviewer did not independently exercise that runtime. Own server 8919 stopped after verification.

## README claim correction review

Independently reviewed the final README diff. **APPROVED** for the factual correction: credential-free startup and synthetic source inspection are distinguished from provider-backed Agent actions, the old complete offline Dashboard → Manager → verification promise is removed, and judge-demo is correctly bounded to historical proof. This matches the reviewer's observed startup, source navigation and unavailable diagnosis safe stop. Conversation was not separately exercised during this UI review; its provider requirement is not represented here as an independently completed conversation test.

The revised README retains the functionality and setup steps, explicitly states that the default browser path is not a complete offline Agent demonstration, and preserves the failed workspace-smoke gate and pending replacement acceptance. Its independent make-check statement matches the separate cold-start review. It makes no all-finalization-pass claim. The regenerated private hash audit and focused package tests are owned by the implementation owner; this paragraph does not independently attest their execution.

## Final regression addition

Reviewed the added degraded-dashboard test: it executes renderDashboardAgentStatus with a retained foreign case at sequence 47, BLOCKED/AGENT_VALIDATION_FAILED state, and no selected platform authority. It asserts Monitoring, zero normal events and a hidden investigation button. This directly protects the independently observed mode-return bug rather than only checking source text. No product change since the browser-approved candidate. Approved.

Implementation-owner reported final results: **100 JS tests passed** (`/tmp/m20-dashboard-authority-js-final.log`), **49 focused package tests passed**, and m7check passed; private audit digest prefix `76504ad` changed for README hashing only. These final aggregate/package results are attributed to the implementation owner. The independent reviewer personally reran the preceding 99-test candidate and completed the browser transition retest.
