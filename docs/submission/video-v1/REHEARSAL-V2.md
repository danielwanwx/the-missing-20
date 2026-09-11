# V2 recording rehearsal — live acceptance ledger

Status: IN PROGRESS. Full film is not cleared for recording or synthesis. The user approved the minimal same-order bridge after the first live inspection exposed separate dashboard and distributor workflows.

## Scope and boundaries

Rehearse the actual UI, English conversation, source evidence, proposed action, approval, execution and native readback before recording. Preserve completed PO19. New isolated case target: `M20-DIST-COMPONENT-V2-20260910`. Code implementation uses supervised Terra High. All acceptance is scoped to the filmed path, not a claim of defect-free production behavior.

## Initial live observations

| Recording point | Actual observation | Acceptance |
| --- | --- | --- |
| Existing `/operations` on port 8906 | PO19: 40 received, 40 dispatched, A25/B15, zero holds/shortage; synthetic confirmations visible | Existing completed-state display inspected; not new execution |
| Dashboard navigation | Navigates to independent scripted 100-unit baseline; no distributor case connection | FAIL: same-order bridge required |
| Investigation tab | Opens normally but shows independent monitoring state | Navigation checked; same-order incident pending |
| Photo entry | Count from photo opens photo-assisted receiving dialog with upload and evidence disclosures | Entry checked; no same-case upload/recognition accepted |
| Operations conversation | Retained `Request failed (500)` and empty conversation | NOT PASSED; old budget block does not establish current cause |
| Airtable | Actual linked PO19 record opens, case matches, 40 received/dispatched, zero held/missing | Read-only existing-record check passed |
| Jira | QRC-4 opens with matching PO19 case, Done status and retained execution evidence | Read-only existing-record check passed; raw JSON is dense for film |
| ERP native UI | Initially 503 Updating; later recovered to sign-in | Browser login needed; no native-document UI pass yet |
| ERP API | Initial maintenance rejection; subsequent read-only provision preflight passed | Connectivity recovered; no new case created |
| AWS identity | STS confirmed missing20-dev in us-west-2; console accessible | Identity check passed, not invocation proof |
| AWS invocation logs | Previously disabled; demo log group created; role creation rejected by AWS IAM | NOT ENABLED; administrator role step pending |
| Architecture presentation | Present button works; diagram still names Nova Pro and AgentCore proof | Interaction checked; content must match final runtime |
| Slack/Celigo native views | Not freshly inspected for V2 | PENDING |
| Approval, fulfillment, multi-turn model results | New same-case path not yet available | PENDING |

## Approved direction and pending gates

- User approved extending the existing distributor surface to retain case identity, a readable source-backed graph, evidence context and actual manager approval. Do not route distributor actions through unrelated generic quality/invoice recovery.
- Read-only chat remains read-only; operator evidence and agent recommendations must have truthful labels. A model response is not proof that an external action happened.
- Independent dry-plan review found fresh V2 provisioning scoped to separate PO/SO markers, two warehouses and three batches. Existing PO19 is not modified. Read preflight succeeded.
- Automatic approval review initially rejected fresh ERP provisioning because explicit authorization for its external records/payload was not established. The user then explicitly approved the $160 purchase order, A25/$150 and B15/$90 customer orders, isolated warehouses/batches, subsequent simulated operational events and demo SaaS updates. The approved retry succeeded: `PUR-ORD-2026-00020`, `SAL-ORD-2026-00015`, `SAL-ORD-2026-00016`. Private provision receipt: `/private/tmp/m20-v2-provision-execute.json`; configuration: `/private/tmp/m20-v2-config.json`. This resolves the provisioning approval block. Operational events have not yet been exercised.
- Current AWS identity cannot create the Bedrock logging role or set log retention. The new `/missing20/demo/bedrock-invocations` log group exists, but logging is not enabled. Administrator assistance was requested. No new model inference was performed in this preflight.
- Chrome reused the user's existing ERP login and displayed the native PO19 document (40 Nos, USD160). AWS root sign-in is open in Chrome for the user, as requested.
- Independent first bridge review blocked acceptance on the absence of a full same-case graph, incomplete approval field/manager evidence, and proposal reload/recovery. Corrections are in progress; see `BRIDGE-REVIEW.md`. Passing focused tests did not clear these gates.

## Completion checks

## V2 live run — first dispatch

- Fresh runtime: port 8907, `/private/tmp/m20-v2-runtime`, PO20 and customer orders 15/16. No PO19 operational writes.
- LOT-A arrival: 2 cartons, 20 Nos, evidence `V2-20260910-arrival-a`. Reviewed exact proposal fields and executed through the browser approval control. Native receipt `MAT-PRE-2026-00019` independently opened in Chrome: 20 Nos at USD4, USD80, V2 inspection warehouse, submitted by Missing20 Agent.
- Whole-lot inspection: diameter 10 mm within 9.9–10.1; evidence `V2-20260910-inspection-a`, report `V2-QI-A-PASS`. Native `MAT-QA-2026-00014` and release `MAT-STE-2026-00015`; 20 usable and zero held.
- Real allocation selector: `bedrock / us.anthropic.claude-opus-4-6-v1`, date-first contract allocation A20/B0. Application-retained selector usage: 1 request, 1,285 input and 543 output tokens, estimated USD0.022. This is one selection's usage, not aggregate rehearsal/account spend.
- Browser question 1: “Which customer can we ship to now, how many parts can ship, and which contract terms justify that decision?” Answer identified customer A, 20 Nos, earliest promise, minimum 10, partial delivery permission, quality release and draft Pick List `STO-PICK-2026-00016`.
- Browser question 2: “For that same customer, does the draft Pick List prove dispatch or delivery? Answer in no more than three short sentences and name the next evidence needed.” Answer retained the customer context and correctly denied dispatch/delivery proof from a draft pick. Both actual answers were English. Markdown currently appears as literal markers in the answer paragraph; narration/crops must reflect actual output until presentation is improved.
- Pick evidence `V2-20260910-picked-a20` approved in browser. Native delivery `MAT-DN-2026-00018` independently opened: A20 at USD6, USD120, V2 accepted warehouse, submitted by Missing20 Agent. Shipment `SHIPMENT-00016` exists. Delivery confirmation is still pending.
- First same-case cross-app readback: Airtable `rec5JyeUJ1iFbNbSO`, Jira `QRC-5`, Slack via Celigo message `1789101250.720899`. All three returned VERIFIED links. Jira was independently opened and its case ID/receipt/20 received/20 held initial state matched the first receipt.
- Corrected JavaScript verified after a full document navigation using a new query string: graph says “Approved operation applied”; approving manager and timestamp persist. Earlier anchor-only navigation was not a full reload and is not counted as pending-proposal reload acceptance. A full pending-proposal reload check remains to run.
- AWS logging role `Missing20BedrockDemoLogging` created through the authorized administrator console. Initial validation failed immediately after role creation; selecting the propagated existing role succeeded. CLI `get-model-invocation-logging-configuration` independently confirms text delivery to `/missing20/demo/bedrock-invocations`. Invocation records have not yet been inspected: missing20-dev lacks `logs:DescribeLogStreams`, and the administrator browser signed out during the requested account switch.
- Python module suite: `python -m pytest tests/test_distributor_operations.py -q` passed 45 tests. Bare `pytest` initially failed collection because `scripts` was absent from its import path; the module invocation resolved that runner issue. Terra reports 37 JavaScript tests passing. These are scoped checks, not full rehearsal acceptance.

- Follow-up acceptance: pickup proposal survived a full document navigation with a changed query string and retained its exact shipment/evidence fields. Approval then completed. Explicit delivery evidence `V2-20260910-delivery-a20` completed for `SHIPMENT-00016`: current totals are 20 received, 20 dispatched, 20 synthetically delivery-confirmed, 20 missing, zero held/usable.
- Photo upload and click-to-expand passed in the actual Chrome UI. Asset `tests/fixtures/photo_receiving/p05.jpg` is the existing public illustrative box fixture, retained as an operator attachment. It shows one open box; no parts count, QR decoding, quality result or actual warehouse provenance is inferred from it. LOT-B's 2 cartons/18 parts are separate declared simulation inputs. This photo cannot support a narrated automatic extraction claim. LOT-B receipt approval is executing; full case remains incomplete.
- Primary verification: 45 Python tests, 37 JavaScript tests, Ruff lint, Ruff format check and `git diff --check` passed. SOL cleared the corrected bridge code for continued rehearsal, preserving all full-film gates.

Remaining: LOT-B count/quality exception and release, replacement LOT-C, remaining A5/B15 fulfillment, fresh native SaaS final-state views, AWS request correlation, accurate architecture and final recording approval.

Record exact case/document IDs, real prompts and answers, model usage, proposal provenance, approval and execution results, and same-case source readback. Retain failures. Check actual exported footage for readability and English content. Replace script outcome placeholders only from those results. Do not count historical evidence, local tests or a partial UI pass as full rehearsal completion.
