# Agentic Investigation Loop

## Goal

Make the Missing 20 dashboard demonstrate an autonomous but evidence-bound
cross-SaaS agent: it observes changing provider evidence, plans its own
investigation, gathers evidence, reasons over what is and is not proven, and
accepts human steering without pretending to repair external systems.

The recording must make these capabilities legible in one case-first screen:

- the Agent's current goal and ordered investigation plan;
- real provider reads and their provenance;
- the evidence relationship behind the current conclusion;
- agentic state transitions driven by ledger events rather than decorative
  timers;
- human questions answered only from a fresh bounded evidence read;
- a hard, visible boundary between a recovery plan and an external mutation.

## Scope

This iteration adds the agent-run projection, event model, and case-console
presentation. It stays within the reviewer-approved read-only execution scope.

It does not add ERPNext, Airtable, Jira, Celigo, or Slack writes. It does not
show a simulated provider write, approval, verification, or recovery as a live
provider effect.

## Agent run model

Each automatic investigation receives an immutable `run_id`. The server owns
the lifecycle and appends all agent events to the existing server-owned,
deduplicated activity ledger.

```text
OBSERVING -> PLANNING -> GATHERING -> REASONING -> PLAN_READY
                                                \-> BLOCKED
```

`VERIFIED` is reserved for a later capability: it requires an authenticated
provider mutation and a separate external read-back satisfying every
postcondition. It is unreachable in this build.

### States

| State | Server behavior | Visible UI behavior |
| --- | --- | --- |
| `OBSERVING` | A new provider evidence signature is admitted. | The matching evidence node receives one arrival pulse. |
| `PLANNING` | The Agent creates a bounded list of required reads from known correlation gaps. | The left plan advances to the active task. |
| `GATHERING` | The Agent invokes the narrow ERPNext and SaaS readers. | A tool-call event and source read result appear in the ledger. |
| `REASONING` | The Agent evaluates the quality hold, lineage, provenance role, and tuple completeness. | The conclusion and evidence constellation update. |
| `PLAN_READY` | A conclusion is supported but no provider write is attempted. | The guard states why a recovery remains a plan. |
| `BLOCKED` | Required source evidence is degraded, absent, or incomplete. | The guard is amber and names only the missing identifiers. |

## Evidence policy

The Agent must use explicit evidence roles:

| Provider | Role | Permitted use |
| --- | --- | --- |
| ERPNext | Authoritative operational evidence | Receipt, invoice, hold state, and quantity facts. |
| Airtable | Release registry evidence | Correlation and release metadata only when tuple fields match. |
| Celigo | Control-plane / exact run receipt when available | Flow enabled is not a causal execution receipt. |
| Jira | Journal | CAPA context; never release proof. |
| Slack | Journal | Incident context; never release proof. |

The full tuple remains: case ID, PO, receipt, invoice, supplier lot,
certificate ID, quantity, and evidence revision. Missing values produce
`PARTIAL_CORRELATION`, not a release decision.

## Console design

The case console uses distinct visual grammars so plan and reasoning are not
confused:

- **Left / Autonomous Plan:** an ordered four-step sequence. One task is
  `ACTIVE`; completed, queued, and blocked tasks have concise state labels.
- **Right / Live Evidence:** a constellation of source nodes surrounding one
  guarded conclusion. It is not a list. Each node carries a short provider and
  state label only.
- **Center conclusion:** changes only from server evidence: cyan while
  gathering, amber for blocked/partial evidence, lime only for a future fully
  verified condition. This scope must never display a false green release.
- **Human steering:** a compact question box. A question creates an
  `agent.evidence.question_answered` event and receives a fresh evidence-bound
  response. It neither changes a provider nor overrides the Agent's facts.
- **Guard:** a concise `WRITE DISABLED` label and non-actionable recovery
  prerequisite. No gray explanatory paragraphs or simulated buttons.

## Real-time behavior

Animations are projections of newly admitted immutable ledger events:

- Provider evidence signature admitted: pulse the matching constellation node
  once and animate a small packet toward the conclusion.
- `PLANNING` / `GATHERING`: move the active marker on the ordered plan.
- `REASONING`: update the conclusion confidence and status color.
- `BLOCKED`: amber guard pulse, with the shortest possible missing-field list.
- No new ledger event: no new pulse or fabricated movement.

The client keys animations by global ledger sequence so refreshes and repeated
polls cannot replay an event as new activity.

## API additions

`GET /api/v1/agent-platform` returns a display-safe projection including:

- `agent_run`: run identifier, state, active step, confidence, and evidence
  gaps;
- `plan`: ordered steps with their statuses;
- `evidence_constellation`: source nodes, authority roles, and server ledger
  sequences that caused their current state;
- `activity`: the unified immutable ledger;
- `execution`: `available: false` and `WRITE_DISABLED`.

`POST /api/v1/agent-platform/diagnose` creates one automatic read-only agent
run. It accepts no provider command.

`POST /api/v1/agent-platform/ask` accepts a bounded text question, performs a
fresh read-only evidence pass, and returns a display-safe answer plus its
ledger event.

## Error handling

- A source error transitions the run to `BLOCKED`, names the degraded source,
  and preserves prior evidence as historical rather than current proof.
- Missing correlation fields remain visible as field names, never inferred
  values.
- Repeated diagnosis starts do not create competing active runs; either the
  same open run is continued or a completed run remains immutable and a new
  run is explicitly created.
- Any attempt to invoke a provider write route remains unreachable and returns
  a typed write-disabled response.

## Acceptance tests

1. A diagnosis produces a run ID and the ordered `OBSERVING` through
   `PLAN_READY` or `BLOCKED` events.
2. Provider events have monotonically increasing global ledger sequences and
   deduplicated source signatures.
3. A degraded source yields `BLOCKED`, not a causal conclusion.
4. Jira, Slack, and enabled Celigo flow status never elevate release
   confidence by themselves.
5. A human question causes only fresh read events and an answer event; it
   cannot mutate the plan's facts or invoke a provider write.
6. The browser renders a constellation, no crossed structural lines, and only
   pulses nodes for newly admitted ledger sequences.
7. The UI displays `WRITE DISABLED` and never displays `VERIFIED` for the
   read-only build.
