# Independent Competition Judge Audit — 2026-08-29

## Verdict

**66/100 — Stage One pass, Stage Two not award-ready.** The product has a strong,
memorable safety architecture and a genuinely interactive local event-driven demo, but
one truth-boundary defect is disqualifying for publication: an arbitrary unknown
`incident_id` is accepted as a live 100/80/20 incident and can launch the full agent
harness. This must fail closed before recording or sharing the demo.

## Current judging basis

The official competition uses five equally weighted Stage Two criteria: Technical
Implementation, Design, Potential Impact, Creativity & Originality, and Presentation.
Stage One is pass/fail for theme/tool viability. The official overview says agents
should do real work end to end; AgentCore and a live demo strengthen Technical
Implementation but are not mandatory.

This audit expands those official dimensions into the following 100-point rubric:

| Dimension | Weight | Score |
| --- | ---: | ---: |
| Human value | 18 | 14 |
| Agentic depth: orchestration, tools, handoffs | 18 | 13 |
| Real-time/data credibility | 14 | 7 |
| Usability/interactivity | 14 | 9 |
| AWS/Strands relevance | 12 | 5 |
| Safety/governance | 12 | 9 |
| Demo clarity | 7 | 5 |
| Technical evidence/honesty | 5 | 4 |
| **Total** | **100** | **66** |

## Fresh E2E matrix

| Step | Result | Evidence |
| --- | --- | --- |
| Healthy Dashboard | PASS: real sequence advanced; 100/100/0 visible | `01-dashboard-healthy.png` |
| Scenario Lab Normal/Recovery | PASS with weak feedback; source selection changes state | `02-scenario-lab-normal.png` |
| Metrics link | PASS: opens Prometheus text in a new tab with per-incident counts | Live browser observation |
| Golden Incident | PASS: injects a new run and starts the paced harness | Live browser observation |
| Incident Dashboard | PASS: 100/80/20, queue IDs, chart and health agree | `03-dashboard-incident.png` |
| Unit record selection | PASS after expanding `Inspect a record`; selection alone is visually silent | `04-unit-control-no-observable-result.png`, `15-unit-inspector-open.png` |
| Dashboard agent/incident cards | FAIL: agent rail buttons, incident cards, and `View all` have no distinct result | Live DOM/URL observation |
| Open investigation/View all agents | PASS: navigates to Agent Workspace | Live DOM/URL observation |
| Three agent selection | PASS: pressed state and activity filter change per investigator | `05-agent-workspace-ready.png` |
| Case actions and suggested questions | PASS: case-specific, cited answers | `06-copilot-citations.png` |
| Free-form chat | PARTIAL: answered the safe next step but ignored the requested ERP count | Live conversation observation |
| Prepare recovery | PASS: immutable intent and two-role gate created; execution remains disabled | `07-two-role-approval-gate.png` |
| First approval only | PASS: `1 of 2 approved`; execute disabled | Live DOM observation |
| Second approval and receipt execution | PASS: execute enabled only after quorum; verified 100/100/0 | Live DOM observation |
| Independent invoice approval | PASS: approvals do not carry; second quorum required | Live DOM observation |
| Final closure and replay | PASS: `VERIFIED · CLOSED`; replay paced; final truth restored; zero effect in smoke | `08-verified-closed.png`, `09-replay-in-progress.png`, `browser-smoke-fresh.json` |
| Degraded mode | FUNCTIONAL PASS / COMMUNICATION WEAK: agent surface disabled, but first viewport still reads healthy/live without a prominent degraded label | `12-degraded-fail-closed.png` |
| Invalid mode | PASS fail-closed; operational claims hidden; `Reconnect` gives no failure feedback | `13-invalid-fail-closed.png` |
| Unknown incident ID | **P0 FAIL**: `does-not-exist` becomes a live incident and launches agents | `14-unknown-id-accepted-as-live-incident.png` |
| Keyboard/accessibility basics | PASS basics: skip link focuses `main-content`; focus-visible, reduced-motion, aria-live and alert semantics present | Live DOM observation; `workspace/style.css`, `workspace/index.html` |
| Mobile smoke | PASS containment at 390px; flow intentionally scrolls inside its region | `browser-smoke-fresh.json` |
| Provider/network boundary | PASS: fresh smoke reports `provider_calls: 0`, `remote_resources: 0` | `browser-smoke-fresh.json` |

## Findings

### P0

1. **Unknown IDs fabricate authoritative-looking incidents.** Reproduction:
   `/?view=agent&scenario=incident&incident_id=does-not-exist` renders LIVE, 100 expected,
   80 ERP, 20 queue, enables Start Investigation, and advances to a completed three-agent
   trace. `ExperimentRegistry.get()` creates a session for every syntactically valid
   unknown ID, while GET routes call it as a lookup. Read-only GET/deep-link access must
   return 404/unavailable unless the incident already exists; creation must remain only
   behind the Scenario Lab transition that persists source injection and detection.

### P1

1. Before investigation, Compare causes/Show evidence/Explain/Ask are enabled. Clicking
   Compare causes silently launches the whole investigation and removes Start
   Investigation. That is a second, mislabeled start path (`10-...png`).
2. Every Copilot request reruns all three investigators. In the audited run, each agent
   grew from 6 to 42 tool operations and the ledger grew from roughly 72 to 549 events;
   replay then took about 55 seconds. This looks like event-volume inflation rather than
   efficient case conversation.
3. Dashboard agent buttons, active-incident cards, and `View all` are semantic buttons
   with no distinct result. Either wire them to selection/filter/navigation or render
   them as non-interactive status.
4. Citation chips mostly highlight themselves; they do not expose the cited evidence
   payload, provenance fields, or admitted-record detail.
5. Free-form chat is a bounded intent router but is presented as open chat. A compound
   question asking ERP count plus next step received only the next-step answer.
6. Degraded mode is functionally safe but visually under-labeled above the fold. The
   screen says LIVE FLOW, LIVE, HEALTHY; the advisory degradation is only discoverable
   in low-prominence footer text/disabled navigation.
7. Invalid-mode Reconnect retries into the same state without an observable attempt,
   timestamp, or error result.

### P2

1. Scenario Lab is very sparse and its status sentence remains generic after selection.
2. Reconciliation window exposes a combobox with only one option.
3. Suggested `Compare causes` duplicates the primary case action.
4. Unit selection is invisible until the separate disclosure is opened; add selected
   state or auto-open the inspector.

## Competitive comparison

The closest public AWS winners set a higher evidence bar. EcoLafaek combined a public
full-stack product, real users/reports, Nova Pro, AgentCore, multimodal input and five-
tool autonomous chaining. AegisAgent paired specialized evidence/policy/compliance
agents with a transparent decision packet. Province paired a plain-language journey
with a concrete 21/21 form-mapping result. The Missing 20 is stronger than many demos
on governance, idempotency and replay, but weaker on proven model usefulness, AgentCore,
real-world data/impact, and currently on URL truth integrity.

## Bounded remediation sequence

1. Make incident GET/deep links lookup-only and add an unknown-ID fail-closed browser test.
2. Disable all case/chat actions until investigation completes; keep one explicit start path.
3. Stop rerunning the full harness for ordinary chat; answer from the admitted case, and
   launch a bounded investigator only when the question truly requires new work.
4. Remove/wire dead Dashboard controls, open evidence citations into actual record detail,
   and make degraded/reconnect feedback explicit.
5. Directional award gap: obtain one stable, positive Strands/Nova/AgentCore trace and one
   credible user/time outcome. Keep the existing synthetic disclosures.

## Public sources

- Official overview and judging criteria: https://agentsforhumans.devpost.com/
- Official rules: https://agentsforhumans.devpost.com/rules
- Official comparable AWS winner announcement: https://aws-agent-hackathon.devpost.com/updates/38140-congratulations-to-the-winners-of-the-aws-ai-agent-global-hackathon
- EcoLafaek: https://devpost.com/software/ecolafaek
- AegisAgent: https://devpost.com/software/aegisagent-an-insurance-claim-app-fully-developed-by-kiro
- Province: https://devpost.com/software/province

Research Engine trace: `research-summary.json` (the automated run had connector and
duplicate warnings; official Devpost pages were separately verified). Fresh browser
smoke: `browser-smoke-fresh.json`.
