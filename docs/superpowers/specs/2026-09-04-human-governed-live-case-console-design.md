# Human-Governed Live Case Console Design

**Status:** approved by the project owner on 2026-09-04  
**Scope:** make the case console visibly human-governed while preserving autonomous,
read-only investigation and deterministic recovery controls.

## Goal

The primary demo must show a person directing an agent rather than a backend job
silently finishing. The person starts a case, can ask questions and can pause or
stop the workflow. The agent may independently gather and compare evidence. Only
an action that changes the authoritative business state, crosses a policy threshold,
or lacks sufficient evidence waits for human review.

## Interaction contract

| Stage | Owner | Visible UI behavior |
| --- | --- | --- |
| Incident detected | Control plane | Case enters `READY_FOR_REVIEW`; no diagnosis starts in the background. |
| Start investigation | Human | The user presses **Start investigation**; the ordered activity ledger visibly receives plan, source-read, and reasoning events. |
| Evidence gathering and hypothesis comparison | Agent | Agent reads allowed sources autonomously and publishes its current plan, findings, and evidence IDs. Human may ask questions or stop the run. |
| Missing, stale, or contradictory evidence | Agent + human | Agent stops in `NEEDS_EVIDENCE`, names the missing or conflicting fact, and exposes a **Resume after evidence** action. |
| Material recovery | Human | A Manager must approve a proposal bound to the evidence tuple and current case version. |
| Effect and reread verification | Agent/control plane | The guarded executor performs only the approved synthetic effect, rereads sources, and reports verified or unresolved. |

No UI animation may invent activity. A rendered event must originate from a
server-ledger event; browser polling must not create events.

## Product additions

1. Replace automatic diagnosis on incident display with an explicit human-started
   operation. The button wording must make the ownership clear.
2. Project a `human_review` object in every case response: `required`, `reason`,
   `action`, and `can_stop`. Use it to make the decision point unambiguous in the UI.
3. Produce a `resolution_packet` only after a verified close. It contains the case
   tuple, finding, deterministic guard disposition, evidence record IDs, Manager
   approval, executed synthetic effect IDs, pre/post state, and independent reread
   receipt. It is a business artifact, not an LLM summary.
4. Render the packet in the console and keep an immutable packet ID in the activity
   ledger. The existing question box remains available throughout read-only stages.

## Safety and truth boundaries

- Autonomous reads are permitted only through the existing scoped evidence readers.
- The Strands advisory remains non-authoritative and cannot approve or execute.
- Human approval is necessary for the synthetic ERP effect, but not for routine reads.
- A `NEEDS_EVIDENCE` or policy block never offers an execute action.
- The packet labels all evidence and effects as synthetic/demo when that is their
  actual provenance; it must not imply an external production write.

## Acceptance checks

1. First display of an incident remains `READY_FOR_REVIEW`/`IDLE` until a user
   presses Start investigation.
2. A user-started investigation appends actual ordered plan/read/reasoning events
   and reaches `PLAN_READY` only when deterministic correlation is complete.
3. A Manager approval is required for the executor; the synthetic recovery verifies
   by reread before a packet exists.
4. A missing/mismatched tuple returns `NEEDS_EVIDENCE` or a blocked stop without a
   recovery proposal or packet.
5. Browser E2E proves buttons, chat, live event rendering, approval and packet data
   are all sourced from API responses.
