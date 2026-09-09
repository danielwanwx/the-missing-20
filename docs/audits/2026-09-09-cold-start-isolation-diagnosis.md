# Cold-start configuration isolation diagnosis

Date: 2026-09-09. Independent read-only diagnosis/design review for the clean-checkout failure reported at `85d6a15`. No implementation changes, private `.env` reads, business requests, model calls or commits were made. Other receiving-contract work was preserved.

## Finding and reproduction

**P1 confirmed: a blank optional case setting from the distributed `.env.example` breaks a credential-free live-read projection when persistent history is enabled.** This is a configuration normalization defect exposed by a test that also depends on ambient developer configuration. It is not evidence of an ERP service outage or an accounting failure.

The reported failing test is `tests/test_agent_platform.py::test_server_live_case_console_mode_selects_authorized_read_adapter`. It selects live mode, deletes only `MISSING20_ENVIRONMENT`, and constructs the server with the real repository root. The server's source factories and photo settings read that root's `.env` and overlay process environment. Thus the test can unintentionally consume developer credentials/settings and external sources, although its purpose is only adapter selection and write-disable behavior.

Code chain:

1. `.env.example:58` contains `MISSING20_CASE_ID=`. A documented clean setup that copies this template therefore differs from one with the key absent.
2. `ERPNextEvidenceSource.from_environment()` uses `values.get("MISSING20_CASE_ID", DEFAULT_CASE_ID)`. The default applies to an absent key, not an empty string. The adapter returns `case_id=""`, including its correct `NOT_CONFIGURED` response when credentials are absent.
3. The live server supplies `state_path`, enabling `OperationalHistory`; many direct `AgentPlatform` unit tests omit it and therefore do not exercise this failure.
4. `AgentPlatform._read_all()` merges `{ "case_id": "M20-ERP-LIVE", ... , **erp }`. The empty ERP value overwrites that fallback. `_observation()` correctly rejects the unscoped history record with `ValueError: case_id is required`.
5. Merely skipping `record()` is insufficient: `_projection()` and `operational_history()` also query using `_text(erp.get("case_id"), fallback)`, which preserves empty strings, and `OperationalHistory.query()` requires a case identity too.

Independent minimal reproduction used a temporary directory containing only a synthetic one-line `.env`, an entirely cleared environment (`patch.dict(..., clear=True)`), `ERPNextEvidenceSource.from_environment(...).current()` with no credentials and `_observation()` with the platform's merge pattern. No real private `.env` or network transport was used.

| Synthetic setting | Source status | History normalization result |
| --- | --- | --- |
| Key absent | NOT_CONFIGURED | Recordable under default identity |
| Empty value | NOT_CONFIGURED | `case_id is required` |
| Whitespace value | NOT_CONFIGURED | `case_id is required` |
| Explicit `M20-ISOLATED` | NOT_CONFIGURED | Recordable under explicit identity |

This reproduces the underlying failure without claiming that the entire cold-clone suite was rerun by this reviewer.

## Minimal correct repair recommendation

Normalize the optional case setting at the ERP environment-factory boundary: treat a missing, empty or whitespace-only `MISSING20_CASE_ID` as the existing `DEFAULT_CASE_ID`; retain a nonblank explicit identity. This preserves the adapter's established absent-key behavior and matches the distributed template. Do not change identifiers globally in `AgentPlatform._text()` and do not relax `OperationalHistory`'s required case validation. Both would broaden the change beyond the demonstrated defect. Do not fill the sample file with a real receiving case, remove history, swallow all `ValueError`s or mark unconfigured data as connected.

This recommendation applies to the optional environment setting for the default live-reader path. An explicitly configured receiving manifest still requires its existing exact case/PO match; do not let the fallback satisfy that manifest check or bind another case. An invalid nonempty explicit identity should retain a clear configuration/validation failure rather than silently defaulting to a different business case. This patch does not authorize a fallback for arbitrary malformed connected-source payloads.

Separately make the adapter-selection test hermetic. Intercept the relevant factories/settings or provide controlled adapters while preserving assertion of the real live-path adapter selection; prevent repository `.env` and ambient provider/receiving/model settings from being consulted. Alternatively construct a disposable minimal repository with the exact fixtures required by the server and a known public template, while clearing the relevant environment. Merely deleting `MISSING20_CASE_ID` in `os.environ` is insufficient because the factory still reads the file. Merely adding a fake valid case ID to the test hides the production bug. Require a failing-on-call external transport guard so a local developer's credentials can never turn this unit test into a provider call.

## Risk and acceptance conditions

Real impact is failure to render the expected unconfigured live-read state for a clean starter configuration; the test suite can also produce machine-dependent results. The history validation currently prevents unscoped persistence, so do not describe this as proven cross-case leakage or duplicate inventory. Broad defaulting after receipt identity validation could create such a risk; the narrow factory repair avoids changing those controls.

Acceptance before committing this optimization:

- Factory tests distinguish absent, empty, whitespace and explicit nondefault IDs with a controlled environment and public temporary file. No private config or network calls.
- Through an `AgentPlatform` with a real temporary `state_path`, the no-credential source yields a successful current projection and history query, with `NOT_CONFIGURED` source state, disabled execution, no documents and no fabricated numeric observations. Repeat reads/restart must remain scoped.
- Explicit custom case stays unchanged, and history for another case remains inaccessible through the current-case path. Existing malformed history-input rejection tests remain passing.
- The server mode-selection test remains live-read and writes-disabled, and fails on any attempted provider call. Test once with clean template settings and once with adversarial ambient configuration masked by the fixture.
- Existing receiving manifest mismatch protection still fails closed; do not change photo/recovery intent matching to accommodate the optional default.
- Run the targeted platform/source/history tests, then repeat the clean checkout's documented `make check` with credential-free template configuration. Record actual counts and exit status; do not infer full reproducibility from this isolated reproduction. Independent review should inspect the final diff before parent commit/push and remote-SHA verification.

Design verdict: approve the narrow optional-setting normalization plus hermetic-test direction. Implementation and cold-start acceptance remain pending; this report does not approve a specific patch not yet reviewed.

## Independent implemented-patch review and release verdict

Reviewed 2026-09-09 after implementation. Scope was exactly the one-line `ERPNextEvidenceSource.from_environment()` change, new `tests/test_cold_start_configuration.py`, and the server live-mode selection test in `tests/test_agent_platform.py`. Other pending receiving/UI changes were outside this verdict.

**APPROVED for this bounded optimization.** No P0/P1 defect found in the inspected patch. The environment factory now strips the optional case setting and uses the pre-existing default when empty. It does not weaken history validation or manifest equality checks. Explicit nonblank test identity remains preserved. Nonempty identifiers with outer whitespace are normalized at this configuration boundary; this is consistent with dotenv parsing rather than reassignment to another case.

The new regression exercises absent/empty/whitespace/custom settings using only a temporary synthetic file and cleared environment at factory creation. The resulting readers retain their constructed configuration; current/read calls do not reload developer configuration. A persistent platform and a second platform instance against the same state path both expose one deduplicated `NOT_CONFIGURED` observation with no documents and all metric values `None`. Keeping a scoped unavailable-state observation is legitimate observability, not invented business history or numeric success.

The server-selection test copies **only the public `.env.example`** to a temporary repository root, clears the entire process environment for server construction and projection, and keeps the required explicit `live` source selection. It intercepts `socket.socket.connect` with a failing guard. The loopback listener may bind, but an outbound provider connection would fail this test. No private `.env` is consulted by its configured repository root. This addresses the observed ambient-config dependence without hiding the production error with a made-up case setting.

Evidence reviewed: `/private/tmp/m20-cold-config-red.log` records the empty/whitespace assertion failures before the patch (two failures, absent/custom pass); `/tmp/m20-cold-config-targeted.log` contains the implementation's green targeted run. The reviewer independently executed the four new parameter cases and the changed server test: first sandbox run produced **4 passed, 1 skipped** because loopback binding was prohibited; the same command rerun with authorized local-socket permissions produced **5 passed, zero skips**, exit 0. No external provider or model call occurred.

Independent command:

```sh
PYTHONPATH=src:. .venv/bin/python -m pytest -q tests/test_cold_start_configuration.py tests/test_agent_platform.py::test_server_live_case_console_mode_selects_authorized_read_adapter
```

Release boundary: this approves the reviewed configuration/test patch for parent commit/push after its normal checks. Full clean-checkout `make check`, exact released SHA and verified remote delivery remain the parent's release gates. This result does not accept unrelated receiving contracts, live semantics, all UI paths, or the whole finalization.
