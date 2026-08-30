# Detection-triggered Agent Investigation

Date: 2026-08-29
Status: Approved

## Decision

An ordinary Scenario Lab incident automatically and idempotently starts the
bounded multi-agent investigation immediately after all of these facts are
durable:

1. the synthetic enterprise source transaction has committed;
2. `source.condition.injected` is present in the ordered public ledger;
3. the deterministic detector has fresh-read the enterprise systems;
4. case genesis and admitted evidence are committed atomically; and
5. `incident.detected` is present in the ordered public ledger.

The browser does not create an incident and does not start the harness. It only
injects the synthetic source condition in Scenario Lab and observes the
authoritative state. The Agent Workspace opens the already-running or completed
investigation.

## Safety boundary

- Agents remain advisory and cannot create operational grants.
- Predictive NWS, NOAA, and AIS context never starts recovery or a confirmed
  discrepancy incident by itself.
- Deterministic policy, exact two-role approval, ControlledExecutor,
  authoritative reread, verification, and replay remain unchanged.
- Repeated source commands and process recovery must not create a second
  investigation run.
- Provider or agent failure becomes a visible degraded advisory state and
  produces no operational effect.

## Acceptance

- A single `POST /api/v1/scenarios {"scenario":"incident"}` is sufficient to
  produce ordered source, detection, investigation, investigator/tool,
  synthesis, and evaluation events without any `/start` request.
- `source.condition.injected < incident.detected < investigation.started` in
  the durable sequence.
- Exactly one `investigation.started` exists for an incident after duplicate
  commands, refresh, and persisted-session reopen.
- The primary UI exposes no manual Start action. It presents live investigation
  state, opens Agent Workspace, and offers Replay only after completion.
- No execution occurs before deterministic eligibility and the required human
  quorum.
