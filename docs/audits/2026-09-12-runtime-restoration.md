# Runtime restoration verification

September 12, 2026, Pacific. This continues the [return-to-project audit](2026-09-12-return-to-project-review.md). The runtime correction passed focused checks and real read-only application acceptance with explicitly selected Nova Pro. Opus access and the separate multi-agent comparison remain incomplete.

| Check | Observed result | Boundary |
|---|---|---|
| AWS identity | Read-only preflight passed using the configured sandbox role and expected account | Login is valid; no credential or IAM change |
| Intended Opus 4.6 invocation | `AccessDeniedException`; no identity-based policy allows `bedrock:InvokeModel` | Login is valid; Opus access is not restored; [administrator procedure](../runbooks/opus-access.md) |
| Explicit Nova Pro invocation | Real response; 5 input / 8 output tokens, `us.amazon.nova-pro-v1:0`, Oregon | Connectivity probe, not business-answer acceptance |
| Fresh ERP before-state | `CURRENT`; 40 ordered, 40 received, 40 dispatched, 0 held, 0 missing | Read existing case only; no new ERP writes |
| Runtime isolation | SQLite backup API copied operations and retained handoff journals into a private inspection runtime | Original runtime journals preserved; local copies are not fresh SaaS reads |
| Source metadata, historical confirmation and provider errors | Implemented and independently reviewed; focused suite 88 passed, UI suite 40 passed | Synthetic regression includes payload collisions and unresolved durable outcomes; no live business replay |
| Real browser questions | Quantities/allocation and causality questions succeeded; third question failed before correction and succeeded after it | Actual Bedrock Nova calls, retained source mode; failed attempt preserved privately |
| Fresh versus retained question | Same quantity question succeeded against fresh ERP and retained evidence | Fresh read correctly reported no supplied effective time; retained answer preserved its timestamp |
| ERP after-state | Same fields and source revision as the fresh before-state | No new ERP/SaaS business effects during this inspection |

Raw provider responses, private case configuration and runtime databases remain outside Git. Public evidence uses only safe error categories and the deliberately public synthetic case identifiers.

## Changes and acceptance

Source mode now travels from projection through the agent packet and visible conversation context. Legacy metadata remains unknown; a retained snapshot is not labeled current. Historical confirmation returns the latest case projection plus separate event metadata, checks the canonical original event payload, and preserves `BLOCKED` or `UNKNOWN_OUTCOME` rather than reporting every non-null result as applied. It does not replay ERP/SaaS effects. Provider errors distinguish permission, credential and timeout categories without displaying account ARNs or scripted answers.

The browser ran `/operations?view=agent` on an isolated private runtime with handoff sync disabled. The first question established 40 received/dispatched and A25/B15, explicitly `RETAINED_AS_OF` at `2026-09-11T05:51:50.322138+00:00`. The second answer correctly declined to infer supplier fault from a shortage or all 18 units defective from a failed sample. Its citation quality was weaker: it quoted policy text rather than naming supporting records.

The third question asked whether delivery and financial records prove physical customer receipt or paid invoices. It initially returned unavailable. Saved native messages established the cause: repeated full source snapshots and tool payloads grew the first request of that turn to roughly 84.6k input tokens. The Strands 80k cumulative turn limit stopped the loop after a tool call, before a final answer. This was a history-growth defect, not a credential or business-reasoning failure.

The correction compacts restored source turns into four completed historical question/answer pairs, drops incomplete source turns, and reuses the same bound on subsequent restores. Tests cover repeated compaction and removal of old tool payloads while retaining the new snapshot. A review caught and fixed an initial version that did not count already-compacted pairs toward the limit. It does not increase token limits or introduce an LLM summarizer.

Retrying the exact third question in the preserved session through the real browser succeeded. The answer identified synthetic delivery confirmations, refused physical-receipt/payment claims, and cited `SHIPMENT-00016` through `SHIPMENT-00019`, `PUR-ORD-2026-00020`, and the two customer orders. The saved final request used 26,722 input / 217 output tokens. This response used the supplied snapshot without an additional source-tool call; it is not evidence of a new multi-agent workflow. The page visibly displayed the actual Nova model and dated retained context.

A separate fresh ERP read plus the same first question returned `CURRENT`, 40/40 and A25/B15, with the source date explicitly unspecified. Direct ERP before/after payloads and revision were identical. The ERP adapter has no independent customer receipt proof; local synthetic delivery confirmations remain a separate evidence category.

## Verification and remaining limits

- Primary acceptance: `pytest -o addopts='' tests/test_distributor_operations.py tests/test_native_receiving_dialogue.py tests/test_decision_workspace.py -q` — **88 passed**. Distributor UI Node tests — **40 passed**. These are focused regression checks, not 128 live business scenarios.
- Ruff lint and formatting on the five changed Python files passed; `git diff --check` passed. Strict mypy still reports **62 errors in nine files** for the focused entry set. The earlier comparison had 63 errors before this slice and no newly introduced normalized error messages; the repository is not type-clean.
- The real denied Opus callback returned `MODEL_ACCESS_DENIED`, no fallback and no account ARN. Missing-source and expired-login branches have isolated regression coverage, not a claim of deliberately expiring the live login.
- Conversation context is limited to four completed pairs; earlier conversational instructions can leave that window. The full current source snapshot still contributes materially to each request. This repair addresses observed history accumulation, not every possible one-turn token-limit failure.
- No independent physical delivery, paid invoices, permanent agent memory, live cross-app replay, or production accuracy claim follows from this inspection. Source badges still refer to retained accepted handoff evidence in this mode. New ERP effects were intentionally outside the acceptance scope.

The [current operations runbook](../runbooks/current-operations.md) describes the connected entry and its private configuration requirements. The [paired evaluation protocol](../research/2026-09-12-paired-evaluation-protocol.md) is a separate isolated comparison; it currently has no scored held-out results and has not been promoted into this runtime.
