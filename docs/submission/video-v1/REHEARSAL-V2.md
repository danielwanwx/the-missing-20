# V2 recording rehearsal — live acceptance ledger

Status: SAME-ORDER BUSINESS REHEARSAL PASSED. Full-film capture and synthesis are not complete; the remaining recording gates are listed below. The user approved the minimal same-order bridge after the first live inspection exposed separate dashboard and distributor workflows.

## Scope and boundaries

Rehearse the actual UI, English conversation, source evidence, proposed action, approval, execution and native readback before recording. Preserve completed PO19. New isolated case target: `M20-DIST-COMPONENT-V2-20260910`. Code implementation uses supervised Terra High. All acceptance is scoped to the filmed path, not a claim of defect-free production behavior.

## Initial live observations (historical; superseded by the live run below)

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

## Complex-case continuation

- LOT-B's two cartons contained a declared 18 parts instead of 20. The application raised `PARTS_SHORTAGE` for 2 and `QUALITY_EVIDENCE_REQUIRED` for 18. Native receipt: `MAT-PRE-2026-00020`.
- A 2-piece sample at 10.3 mm produced rejected inspection `MAT-QA-2026-00015` and held all 18 LOT-B parts. No inference that all 18 pieces were defective was made.
- Third real English question: “All four original cartons have arrived. Can we now fulfill the remaining five parts for the first customer and fifteen for the second? Explain the shortage and quality constraints in three short sentences.” The answer correctly distinguished 4 cartons from 38 received parts, 2 missing, 18 held and zero usable; it explicitly distinguished sample failure from proof that every held unit was defective. It was longer than the requested three short sentences, so concision is not a passed claim.
- The native Strands snapshot contains 6 persisted messages: 3 user and 3 assistant messages, after the full-page navigations and intervening operational events. Snapshot remains private under the V2 runtime's `distributor-native-sessions` directory.
- Declared whole-lot reinspection of 18 pieces at 10 mm produced accepted `MAT-QA-2026-00016`, release `MAT-STE-2026-00017` and a real Opus-selected A5/B13 plan. A5 correctly used the permitted final-remainder exception to its minimum dispatch quantity.
- Replacement LOT-C arrived as one carton containing 2 parts: `MAT-PRE-2026-00021`. Missing quantity became zero. Accepted inspection `MAT-QA-2026-00017` and release `MAT-STE-2026-00018` made all remaining stock usable. The next real Opus selection added only B2 while retaining existing prepared commitments. Three unique selection records total an application-estimated USD0.0704165; chat and Codex usage are excluded.
- Browser approval dispatched A's remaining 5 as `MAT-DN-2026-00019` / `SHIPMENT-00017`, and B's first 13 as `MAT-DN-2026-00020` / `SHIPMENT-00018`. Last B2 dispatch is executing. The current completed dispatch total is 38, not 40, until its result is verified.
- Airtable's actual expanded V2 record independently showed 38 received, 18 held, 2 missing, 20 dispatched and 20 recorded delivery confirmations during the quality-hold phase, with matching native record links. Dashboard screenshot inspection confirmed visible shortage and quality-stage highlights; photo expansion also rendered the actual image.
- Release evidence: `a8c5fa6c65eabc93abac7146059097bff6a1ff67` matches remote `main`. GitHub's actual Actions page shows [CI run 85](https://github.com/danielwanwx/the-missing-20/actions/runs/34563848269) completed successfully in 2m48s. CLI lacked authentication and the connector returned no runs; the native GitHub page supplied the CI verification.

Remaining at this checkpoint: final B2 dispatch; pickup and delivery confirmations for shipments 17, 18 and the final shipment; final native SaaS/ERP state; optional AWS request correlation or truthful application-trace fallback; architecture/shot-plan alignment and film clearance.

Record exact case/document IDs, real prompts and answers, model usage, proposal provenance, approval and execution results, and same-case source readback. Retain failures. Check actual exported footage for readability and English content. Replace script outcome placeholders only from those results. Do not count historical evidence, local tests or a partial UI pass as full rehearsal completion.


## Final shipment checkpoint

- All four picks and native dispatches completed through the approved browser flow: A20 / DN18 / Shipment16; A5 / DN19 / Shipment17; B13 / DN20 / Shipment18; B2 / DN21 / Shipment19. Full document prefixes are retained in the event sections and source links.
- Pickup and explicit synthetic delivery confirmations completed for Shipments16,17,18. Shipment19 pickup completed as event `V2-20260910-carrier-b2`; its final delivery proposal is being prepared. At this checkpoint the verified total is 40 dispatched and 38 delivery-confirmed.
- Native Airtable detail view independently shows 40 received, zero held, zero missing, 40 dispatched and 38 confirmations. Native Jira QRC-5 shows Done with the matching PO20 and A25/B15 allocation records. Exception resolution is distinct from final delivery confirmation.
- Native ERP customer B order `SAL-ORD-2026-00016` shows To Bill, 15 Nos at USD6, total USD90, advance paid USD0. Order value is not invoiced or recognized revenue. No invoice was created by this rehearsal.


## Final acceptance — PO20 business loop

- Final approved event `V2-20260910-delivery-b2` completed for `SHIPMENT-00019`. Actual browser Activity retains all 19 events. Current dashboard: **40 ordered, 40 received, 40 dispatched, 40 synthetic delivery-confirmed, zero held, zero missing, zero open alerts**. A fulfilled 25; B fulfilled 15. The final dashboard screenshot was visually inspected, including the completed stage graph and same-case identifiers.
- Actual Airtable expanded record `rec5JyeUJ1iFbNbSO` was refreshed after final execution: **40 / 0 / 0 / 40 / 40** for received / held / missing / dispatched / confirmations. Native Jira `QRC-5` remains Done. Actual Slack web UI shows the matching final quantities in [the final Celigo-coordinated update](https://miss-20.slack.com/archives/C0BUNV20J6Q/p1789105956484039).
- Native ERP A order `SAL-ORD-2026-00015` independently shows 25 Nos / USD150 / To Bill / USD0 advance. B order shows 15 Nos / USD90 / To Bill / USD0 advance. Final native delivery note `MAT-DN-2026-00021` shows 2 Nos / USD12 / To Bill. These are submitted operational records and order values, not payment or recognized revenue.
- Three real English dialogue turns and three real Bedrock Opus contract selections passed the factual checks described above. A retained historical answer reflects its original quality-hold state; it must not be presented as a fresh answer after final completion. No additional inference was spent on final carrier/delivery events.
- See `SOL-REVIEW-V2.md` for the independent final journal audit. Focused tests and successful CI remain scoped code evidence; the native UI run supplies business acceptance.

## Remaining recording gates

1. Preserve this completed PO20 case. The rehearsal inspected UI states but did not produce continuous raw video of every transition. Do not manufacture a pending incident from the completed state. A fresh externally written recording case requires its own explicit scope authorization; the existing approval covered V2.
2. Replace the old architecture presentation's Nova Pro / AgentCore wording with the truthful four-step diagram specified in `STORYBOARD-V2.md`; current runtime is Strands with Bedrock Opus 4.6.
3. AWS logging is enabled and API-verified, but Chrome still reports a signed-out session and no invocation event has been correlated. Use the storyboard's truthful application-trace alternative unless exact request telemetry is verified. Do not film the settings page as execution proof.
4. Final capture must establish readable crops, actual click/approval transitions, real English dialogue, photo provenance, and the impact ending. Optional microphone dictation has not been accepted as a recording claim. Full video/audio composition and exported-film review are still outstanding.

The completed rehearsal supports proceeding to a scoped recording session; it does not certify a finished film, production reliability, or a competition award.


## AWS login recheck and real-time recording preference

Chrome was freshly navigated to CloudWatch after the user reported missing20-dev login. The console now confirms that IAM identity; the prior signed-out condition is superseded. The invocation log group loads, but its Log streams panel explicitly denies `logs:DescribeLogStreams` on `/missing20/demo/bedrock-invocations`. No request event has yet been read or correlated. Administrator assistance is requested for log-group read access; no IAM change was performed in this recheck.

The storyboard now requires continuous real-time typing, waiting, and answer capture, with actual ERP/SaaS evidence. A fresh V3 write scope remains awaiting explicit approval. No new external business records or paid model calls were made in this planning update.
