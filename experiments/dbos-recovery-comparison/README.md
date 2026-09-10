# DBOS SQLite crash-recovery comparison

This is an isolated local mechanism experiment. It does not import the product,
call an ERP, use credentials, invoke a model, or make a financial decision.

The comparison measures one narrow lost-checkpoint window. A DBOS `@step` writes
to an independent fake-ERP SQLite database, commits and closes that database,
then its child process exits with code `97` before DBOS can checkpoint the step
return. A fresh process launches the same DBOS application, with the same
external intent and workflow ID, so DBOS recovers the pending workflow. A third
process invokes that completed workflow ID again to verify that the completed
step is not run again.

`A-no-unique-intent-key` gives the fake ERP no unique key. Recovery therefore
performs two fake effects for two attempts. `B-unique-intent-key` gives the fake
ERP a unique `intent_id`; its second attempt reads and returns the original exact
fake record after the unique-key conflict. The experiment intentionally does not
require A to have one effect.

The official [DBOS architecture documentation](https://docs.dbos.dev/architecture)
describes checkpointed workflow/step recovery and says a step that fails before
its checkpoint must be safe to retry. The current [Python database-connection
guide](https://docs.dbos.dev/python/tutorials/database-connection) documents
SQLite as a supported default for prototyping and testing, while recommending
Postgres for production. This probe actually launched DBOS 2.31.1 against its
SQLite system database; it makes no claim that a production deployment can avoid
Postgres or that a workflow result verifies a real ERP effect.

## Fixed local dependency set

`requirements.lock.txt` is a complete hash-checked wheel lock for the exact
resolved packages used for this probe. It is valid only for **CPython 3.12 on
macOS arm64**: it records the downloaded macOS-arm64 wheels (and the resolved
universal wheels), so it must not be used as a cross-platform lock. The verified
DBOS wheel is
`dbos-2.31.1-py3-none-any.whl` with SHA-256
`5c32840683cbb10727d30d208d8e1eb3ccaec7ed881776e5bf9d89cb32d7583c`.

All installed packages, pip cache, wheel, pip install report, and SQLite files
belong under `/private/tmp/m20-dbos-2311-probe/`; no project dependency file is
changed. The observed installation used Python 3.12.13. The SDK requires Python
3.10 or newer.

```sh
PROBE_ROOT=/private/tmp/m20-dbos-2311-probe
.venv/bin/python -m venv "$PROBE_ROOT/venv-py312"
PIP_CACHE_DIR="$PROBE_ROOT/pip-cache" "$PROBE_ROOT/venv-py312/bin/python" -m pip install \
  --require-hashes \
  --report "$PROBE_ROOT/install-report.json" \
  -r experiments/dbos-recovery-comparison/requirements.lock.txt
"$PROBE_ROOT/venv-py312/bin/python" -m pip check
```

For a fresh direct-wheel verification, download `dbos==2.31.1` only into
`$PROBE_ROOT/wheels`, run `shasum -a 256` over the wheel, and compare it to the
hash above before installing it. The original successful install record is kept
at `/private/tmp/m20-dbos-2311-probe/install-report.json`.

## Run and inspect

```sh
PROBE_ROOT=/private/tmp/m20-dbos-2311-probe
RUNTIME_DIR=$(mktemp -d "$PROBE_ROOT/comparison.XXXXXX")
"$PROBE_ROOT/venv-py312/bin/python" \
  experiments/dbos-recovery-comparison/dbos_recovery_comparison.py \
  compare --runtime-dir "$RUNTIME_DIR" --timeout-seconds 20
cat "$RUNTIME_DIR/all-comparisons-result.json"

"$PROBE_ROOT/venv-py312/bin/python" \
  experiments/dbos-recovery-comparison/test_dbos_recovery_comparison.py
```

Every crash, recovery, and replay phase is a parent-owned `Popen` child. The
parent records its PID in each result, waits with an explicit timeout no greater
than 30 seconds, and terminates or kills only that child if it times out. Each
successful comparison preserves `comparison-result.json` under its supplied
temporary runtime directory, including attempt count, fake effect row count,
returned identity, final workflow status, and phase PID/exit-code records.
Failed or timed-out phases preserve `phase-attempts.jsonl` and child output logs;
they do not produce a successful comparison summary.

The first successful run observed:

| Fake-ERP contract | After crash | After DBOS recovery | After same-ID replay |
| --- | --- | --- | --- |
| A: no unique intent key | 1 attempt, 1 effect | 2 attempts, 2 effects, returns record 2 | still 2 attempts, 2 effects |
| B: unique intent key | 1 attempt, 1 effect | 2 attempts, 1 effect, returns original record 1 | still 2 attempts, 1 effect |

Both recovered workflows reached `SUCCESS`. That outcome only records DBOS's
workflow state in this local experiment. It is not evidence of financial
closure, approval, payment, real-document validation, or a production ERP
contract.
