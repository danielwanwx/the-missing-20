# Current distributor workspace

The current product entry is `/operations`. The older `make case-console` target exercises a separate historical path; it is not the PO20 distributor workspace.

This connected entry needs existing private ERP demo credentials, the matching distributor case configuration, and its local runtime journal. A clean clone does not contain those private records. Synthetic unit tests are not a substitute for this connected run.

## Before starting

Use the repository's existing `.venv` and local `.env`. The case JSON must reference the intended existing purchase order, customer orders, lots, warehouses and contracts. The runtime directory must belong to that same case. Keep both outside Git. For an inspection copy, use SQLite's backup API so an active WAL is included; do not copy only the database file from a running writer.

The current AWS profile chain uses `missing20-sandbox` with the login source `missing20-login`. Follow the [AWS login runbook](aws-login.md) only if identity/session validation fails. `AccessDeniedException` after successful identity validation is a model permission problem, not evidence that logging in again will fix it.

Nova Pro access was verified on September 12. Opus 4.6 still returned access denial because the sandbox role has no identity policy allowing its invocation; see the [scoped administrator recovery procedure](opus-access.md). Select the intended model explicitly; the application must not silently switch providers or invent a fallback answer.

## Inspect retained evidence with real model answers

Set `M20_CASE_CONFIG` and `M20_RUNTIME` in your terminal to the existing private case JSON and inspection runtime directory. This command requires those values rather than inventing a new case:

```sh
MISSING20_ENVIRONMENT=demo \
MISSING20_AGENT_PROVIDER=bedrock \
MISSING20_NATIVE_RECEIVING_DIALOGUE=1 \
MISSING20_DISTRIBUTOR_MODEL=nova \
MISSING20_DISTRIBUTOR_RETAINED_PROJECTION=1 \
MISSING20_DISTRIBUTOR_HANDOFF_SYNC=0 \
MISSING20_LIVE_SOURCES_AUTOSTART=0 \
MISSING20_PHOTO_AUTO_PREPARE=0 \
MISSING20_PHOTO_DRAFTS_ENABLED=0 \
MISSING20_RECEIVING_HANDOFF_ENABLED=0 \
.venv/bin/python scripts/decision_workspace_server.py \
  --host 127.0.0.1 --port 8930 \
  --runtime-directory "${M20_RUNTIME:?Set the existing private inspection runtime}" \
  --distributor-operations-config "${M20_CASE_CONFIG:?Set the matching private case JSON}"
```

Open `http://127.0.0.1:8930/operations?view=dashboard`. If retained handoff cards are needed, also supply `--distributor-handoff-config` with the existing matching private destination map while keeping handoff sync disabled. Their journal entries remain historical evidence.

Retained mode reads dated local evidence and disables new operations. Asking a question still makes a paid, real Bedrock call. It does not freshly query ERP or SaaS. Confirm that the page and answer preserve `RETAINED_AS_OF` and its date. A missing journal must show unavailable evidence, not an invented current case.

On restore, native conversations retain the latest four completed question/answer pairs as historical claims. Old source snapshots, tool payloads and incomplete source turns are omitted before a new qualified snapshot is supplied. This is bounded conversation context, not permanent memory; earlier conversational instructions may leave that window. Private failed-session evidence should be copied before a diagnostic retry when it is needed for an audit.

For current ERP verification, the application's live projection mode requires `MISSING20_DISTRIBUTOR_RETAINED_PROJECTION=0`. That mode can expose operation controls; it is not a server-wide read-only switch. During a read-only audit use only the projection GET and Ask route, and never invoke event/proposal/approval endpoints. An Ask is read-only, but its answer does not itself prove any new business effect.

## Acceptance boundary

Check the actual configured model in the response. Verify quantities and customer allocations against a separate fresh ERP read. Ask about source freshness, whether a sample failure establishes every unit is defective, and whether recorded dispatch or synthetic delivery confirmation proves physical customer receipt. Model permission denial, expired credentials and timeout should be classified unavailable states, with no provider ARN exposed and no scripted success.

PO20's historical completed state is 40 received and 40 dispatched, A25/B15. Synthetic physical observations and delivery confirmations are demo inputs. Orders of USD160, USD150 and USD90 are not invoices, payments or recognized revenue. Current inspection results and remaining failures belong in the dated audit, not in this startup procedure.
