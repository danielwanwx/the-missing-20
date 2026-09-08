# Design QA — Agent Observability Console v4

## Scope and coverage

| Area | Result | Evidence |
| --- | --- | --- |
| Typography | Passed | Geist Sans owns hierarchy; Geist Mono is restricted to IDs, metrics, timestamps, and tool names. |
| Surfaces | Passed | The interface uses a silver canvas, one dark run strip, and restrained white work surfaces rather than nested floating cards. |
| Information architecture | Passed | The page reads in operational order: incident → run metrics → source truth → Strands loop → human gate → verified outcome. |
| Backend coverage | Passed | Runtime, latency, tool count, evidence count, token volume, incremental cost, sources, hypotheses, tool ledger, events, chat, approval, execution, and outcome remain represented. |
| Motion | Passed | Motion is bound to new ledger events and the current agent stage; reduced-motion behavior is preserved. |
| Interaction | Passed | Dashboard routing, Investigation routing, source details, module focus/arrange/reset, agent chat, approval, execution, and demo controls remain available. |
| Responsive behavior | Passed | The 12-column command canvas collapses to one column; run metrics, source truth, and loop stages reflow without hiding data. |

## Findings resolved

| Severity | Finding | Resolution |
| --- | --- | --- |
| High | The prior redesign compressed the backend into three generic cards and did not explain why Strands was necessary. | Added a six-stage live agent loop and surfaced real Bedrock/Strands run telemetry at the top of the workspace. |
| High | The incident looked like a trivial `100 → 80` arithmetic problem. | Dashboard framing now states that five systems disagree; Investigation exposes the 12-unit receipt ambiguity, 8-unit quality branch, four competing hypotheses, and evidence-backed elimination. |
| High | Critical operational proof was visually subordinate or below the fold. | Runtime, latency, tools, evidence, tokens, cost, confidence, and manager state are now primary scan targets. |
| Medium | Signals and source receipts were presented as unrelated nested cards. | Consolidated them into one source-truth scan line with separators and stable authority colors. |
| Medium | Tool names were truncated in a two-column grid. | Returned the Agent ledger to one full-width column so every selected tool remains readable. |
| Medium | Manager decision content overlapped at desktop widths. | Rebuilt the decision module as a vertical evidence → scope → approval flow. |
| Medium | Event rows appeared as clipped fragments. | The Dashboard rail now advances through the latest six complete rows while retaining the authoritative total count. |
| Low | Excessive radii and shadows made the console feel generic. | Reduced radii, removed decorative nesting, and limited strong elevation to the current run and active modules. |

## Considered but rejected

- Installing arbitrary third-party “design prompt” packs: rejected because visual authority without repository context can erase product behavior. The implementation instead applies the actionable principles from the official Anthropic frontend-design guidance to this product’s actual DOM and runtime state.
- A pure topology hero: rejected because a diagram alone does not prove Agent execution. The topology is now subordinate to stage state, run telemetry, tool calls, evidence, and human authority.
- A full dark theme: rejected because the video submission needs reliable text and chart legibility. The dark treatment is isolated to the current-run control strip.
- Decorative gradients and ambient animation: rejected because source arrivals and trace transitions already provide meaningful motion.

## Verification

- `node --check workspace/app.js`: passed.
- `npm test`: 38/38 passed.
- `PYTHONPATH=. .venv/bin/pytest -q tests/test_agent_platform_browser.py`: 3/3 passed.
- `git diff --check`: passed.
- In-app browser inspection at 1280 × 720: Dashboard and Investigation inspected in the active 20-unit incident state; no node-label obstruction, metric loss, decision overlap, or disconnected primary control was observed.

final result: passed
