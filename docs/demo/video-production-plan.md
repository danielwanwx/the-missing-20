# Video Production Plan

## Creative direction

Tell one operational story, not a feature tour. The viewer should feel the system move
from normal operations to ambiguity, investigation, a necessary human decision, and
verified recovery. Keep the product full-screen; use captions only for facts the UI
cannot communicate quickly.

## Capture plan

Record at 1920×1080, 60 fps, browser zoom 90–100%, with the pointer enlarged slightly.
Hide bookmarks, notifications, account identifiers, terminals containing credentials,
and unrelated tabs. Use the light UI throughout the product sequence.

Capture these clips separately:

1. **Normal baseline, 12–15 s:** live sequence and event rail visibly changing.
2. **Incident injection, 20–25 s:** one deliberate click, then the Dashboard changes.
3. **Source inspection, 25–30 s:** ERPNext, Airtable, Celigo, risk and exposure.
4. **Two-turn conversation, 25–35 s:** first question plus one context-dependent follow-up.
5. **Agent run, 50–65 s:** stages, selected tools, hooks, evidence and evaluator state.
6. **Manager gate, 20–25 s:** show both human choices; approve the hero run.
7. **Execution and reread, 25–35 s:** wait for verified state; show the authoritative
   document, ledger, and integration receipt.
8. **Architecture, 15–20 s:** slow pan or cursor trace across the authority boundary.
9. **Verified closing frame, 8–10 s.**

Record the voice-over after picture lock. Keep product audio muted. Use cuts on actions;
avoid speed ramps during evidence or decision states. A subtle 105–115% crop may focus
the active panel, but never crop away the live status or human gate.

## Edit structure

- **0:00–0:50 — Stakes:** normal flow, incident, five-system disagreement.
- **0:50–2:35 — Intelligence:** live impact, evidence conversation, Strands loop.
- **2:35–4:10 — Control:** deterministic eligibility, Manager decision, verified effect.
- **4:10–4:50 — Platform:** reusable architecture and closing value.

Use lower-thirds only for these four phrases:

- `5 systems · 1 evidence graph`
- `Strands investigates · policy controls`
- `Human review when necessary`
- `Authoritative reread · verified effect`

## Recording runbook

1. Start from a clean healthy demo tenant.
2. Confirm the first paint shows the light loading state, never the legacy dark shell.
3. Confirm `LIVE`, sequence, event count, and charts update for at least ten seconds.
4. Confirm the incident control produces a fresh incident ID.
5. Confirm AWS credentials before choosing a real-provider take; otherwise record the
   controlled local run and disclose it accurately.
6. Rehearse the two chat questions so the follow-up depends on the first answer.
7. Approve only after the plan is ready. Do not cut around an incorrect state.
8. Capture the final verified resolution packet. Do not imply a second live replay.
9. Remove any take containing credentials, account IDs, personal email, or tokens.

## Quality gate before upload

- Total duration is no more than five minutes.
- Every narration claim is visible or linked to a named evidence artifact.
- No static state is labeled live; the 90-day chart is labeled historical.
- No Manager controls or outcome text appear before their lifecycle state.
- No external system is implied writable unless the isolated demo executor is enabled.
- Architecture labels remain readable on a laptop screen at 1080p.
- Captions are manually corrected for `Strands`, `AgentCore`, `ERPNext`, `Celigo`, and
  `idempotency`.
- End card includes project name, one-sentence value, repository URL, and synthetic-data
  disclosure.
