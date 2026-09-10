# DBOS recovery comparison: accepted mechanism experiment

Verdict: APPROVED for the isolated DBOS 2.31.1 / SQLite experiment only. No
product integration, real ERP idempotency or same-order financial closure is
accepted. The reviewed result rejects using workflow recovery alone as proof
that an external effect occurs once.

Both variants commit a persistent fake-ERP effect, then exit their child process
with code 97 before DBOS checkpoints the step result. A separate process calls
`DBOS.launch()` and waits for native recovery of the pending workflow. It does
not manually rerun the workflow or step. A third process invokes the completed
workflow ID. The variants use the same intent/workflow IDs and separate stores.

| Variant | After crash | After native recovery | Completed-ID replay |
| --- | --- | --- | --- |
| A: no target unique key | 1 attempt / 1 effect | 2 attempts / 2 effects, record 2 | unchanged |
| B: target unique intent key | 1 attempt / 1 effect | 2 attempts / 1 effect, original record 1 | unchanged |

Both workflows report SUCCESS. B's unique key exists only in the fake ERP.
These observations support reusing a recovery engine where appropriate while
separately establishing the external system's effect contract. They do not
justify replacing the current billing journal. The current API identity's
three false create-permission results do not establish tenant-wide limitations
or grant a different identity permission to change its schema.

## Verification and retained failures

- Primary frozen-script test: 3 tests passed in 3.827s; formatter and Ruff clean.
- Independent reviewer: 3 tests passed in 3.782s; checked distinct crash,
  recovery and replay PIDs, actual SQLite persistence and native recovery calls.
- Primary fresh hash-locked environment: actual CLI comparison exited 0 with
  unchanged before/after SHA for script, tests, README and dependency lock.
  Runtime: `/private/tmp/m20-dbos-reviewed-primary-01/runtime`; execution record:
  `/private/tmp/m20-dbos-reviewed-primary-01/execution.json`.
- Independent actual 1ms timeout probe retained started/timed_out records, owned
  child PID 69831 and exit -15 under
  `/private/tmp/m20-dbos-2311-probe/independent-timeout-75p5kxj9`. It produced no
  comparison summary. The README now distinguishes successful summaries from
  failed-phase logs; this final change is documentation only.
- The initial lock incorrectly hashed only DBOS, enabling pip's hash enforcement
  while omitting transitive hashes. Primary reproduced fresh-install failure.
  Terra corrected only the lock and README: all 11 resolved wheels are hashed,
  binary-only installation is explicit, and support is scoped to CPython 3.12
  on macOS arm64. A new isolated environment installed successfully and passed
  `pip check`; it was used for the primary CLI comparison above. Original failed
  and successful installation records remain under
  `/private/tmp/m20-dbos-2311-probe/`.

Reviewed script SHA256:
`b4fff979d3ac970415148df0cba48a0feaa81c72bc807d85760166d61dae6a50`.
Reviewed test SHA256:
`26becdb103e334ad851379e13ce7ccb1dd3b2ee2f10a1e1e4e061182743ff57c`.
Reviewed lock SHA256:
`e4ee69e6f066a9bf1d0f611b4662b593792ce519c083be947a631726213a468a`.
The original unaccepted journal expansion remains preserved and paused. No
product dependency, ERP document, model configuration or IAM policy changed.
