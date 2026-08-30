# Detection-triggered Agent Investigation — implementation record

Date: 2026-08-29
Status: implementation complete; primary verification recorded below

## Behavior changed

- Scenario Lab's ordinary `incident` allocation enables detector-triggered
  handoff. Once `incident.detected` is durable, the session starts the local
  multi-agent harness without a browser `/start` request.
- The handoff is idempotent. A repeated source command, a refresh, and a
  `ExperimentRegistry` reopen reuse the same source, case, and run ledger;
  they cannot append a second `investigation.started` event.
- The legacy incident `/start` route remains a compatibility boundary, but the
  primary Agent Workspace no longer renders a manual Start button or attaches a
  click listener to one. Replay remains available only after evaluation.
- The deterministic detector still owns incident creation. Agents remain
  advisory; external NWS/NOAA/AIS context cannot trigger a confirmed incident,
  grant, execution, or recovery.

## Verification

- `tests/integration/test_realtime_experiment.py` covers one scenario POST
  without `/start`, strict source/detection/handoff ordering, duplicate source
  idempotency, persisted reopen, and no execution before approval.
- `npm test` passed after the primary UI change.
- `pytest -q tests/integration/test_realtime_experiment.py` passed (with the
  suite's existing environment skips).

No AWS/provider call, spend, commit, push, or publication was performed.
