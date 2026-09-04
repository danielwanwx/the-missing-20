# Human-Governed Live Case Console — Implementation Plan

**Design:** `docs/superpowers/specs/2026-09-04-human-governed-live-case-console-design.md`

1. Extend `AgentPlatform` with a server-owned `human_review` projection and a
   completed-only `resolution_packet`. Emit ledger events for human start, review
   request, approval, execution, reread, and packet issuance.
2. Keep diagnosis explicit: the browser renders the case as ready but never calls
   diagnose automatically. A human-started diagnosis remains the only entry point.
3. Model evidence insufficiency as an explicit safe stop with a reason and a
   resumable review action; keep provider writes unreachable from this state.
4. Render ownership, review reason, packet, and packet evidence in the Case Console.
   Bind all visual changes to the returned projection and ledger sequences.
5. Add focused unit and browser assertions for manual start, policy stop, approval,
   verified packet issuance, chat, and live activity. Run focused Python, browser,
   and JavaScript suites.
