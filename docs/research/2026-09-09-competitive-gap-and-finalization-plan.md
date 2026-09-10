# Cross-Platform Competitive Gaps and Complete Finalization Plan

2026-09-09; evaluation baseline 2b2c008839233e1c6bc6a174b61093f8e5957a3c. Research and plan, not feature acceptance or a prediction of winning. Overall status **NOT_READY**. This plan expands the requirements and acceptance interpretation in finalization-tracker and does not cancel any existing incomplete item.

## Judgment and Product Scope

We have credible partial engineering results: one physical input substituted for a sample and drove a real ERP receipt; after a lost request acknowledgment we verified an existing document and avoided duplicate inventory; business effects across different SaaS systems can be read back. We have not shown that accuracy survives continued follow-up, that complex conflicts yield stable correct business conclusions, that one new order completes its downstream chain, that the full interface is reliable, or that real operators benefit.

We cannot state “how many percent remain before winning.” Competition scoring, demo completeness, enterprise-pilot suitability, and commercial value are accepted separately. At least six independent delivery gates remain open: semantic reliability, same-case business chain, complex exceptions, complete UX, an accessible submission package, and actual value measurement. The first five directly affect competition delivery; the sixth affects potential-value evidence. Production isolation, security, and operations add another group of gates.

Recommended position: **an Agent for receiving and operational exception handling at a parts distributor**. Users are warehouse/operations managers; onsite staff provide physical facts, while QA, purchasing, and finance provide evidence within their responsibilities. The product addresses investigation, duplicate entry, and exception follow-up across ERP, integration logs, tickets, and collaboration records. This is a research-based product hypothesis with no customer interviews or paid validation.

Core questions: Which order does this shipment belong to? What evidence actually proves arrival? Which quantities are posted, awaiting inspection, usable, or still due? What effect did a timeout really produce? What step is possible now, who must supply which evidence, and did the completed step actually post? Do not frame normal partial arrival as loss, and do not treat book records as independent onsite observation.

## Evidence and Comparison Method

Label winning identity, official paraphrases of judge comments, creator descriptions, vendor documents, individual community statements, and our actual run results separately. Do not claim to have watched a video you did not watch or tested a product you did not run. Community samples help discover problems and do not represent market proportions; vendor efficiency figures are not our ROI. Public judge statements are not a complete score record from every judge.

- [Existing five AWS winning comparisons](2026-09-09-finalization-comparators.md): EcoLafaek, AegisAgent, Province, Triage, and AgentShell; winning identities have official announcements, while operating details mostly come from creator materials and lack cross-product performance tests.
- [Cross-platform awards and judging expansion](2026-09-09-cross-platform-awards-review.md): additional official Microsoft/SAP/Google statements and evidence boundaries.
- [Warehouse B2B demand and public discussions](2026-09-09-warehouse-b2b-agent-demand-review.md): original posts, bias, and industry fit.
- [Native Strands conversation research](2026-09-09-strands-conversation-memory-research.md): installed APIs, versions, and risks independently checked.
- [Accuracy and complex-task acceptance](../audits/2026-09-09-agent-accuracy-complexity-acceptance-plan.md): concrete tests and independent-judgment method.

Commercial product baselines read directly by the main task:

| Baseline | Capability actually described in the document | Meaning and limitation for us |
| --- | --- | --- |
| [Oracle 26B Warehouse Operations Workspace](https://docs.oracle.com/en/cloud/saas/readiness/scm/26b/inv26b/26B-inventory-wn-f43846.htm) | Four workspaces for inventory, outbound, inbound, and labor; exception investigation, supplier email, and operating suggestions; role permissions, current-data assumptions, and configuration prerequisites are stated | Inventory chat and exception dashboards already face mature-platform competition. We must show reduced investigation and rework in our cross-software environment; this was document verification, not a logged-in Oracle test |
| [Microsoft Supplier Communications Agent](https://www.microsoft.com/en-us/dynamics-365/blog/it-professional/2025/04/25/reimagining-supplier-communications-with-dynamics-365/) | Follow purchasing, read supplier email, extract changes, and help update orders | Routine follow-up and data entry are clear entry points; the time-share figures on its product page are vendor claims, not measurement with this project's customers |

Specific lessons from public award and demand evidence:

- **Microsoft Warehouse Picking, third place in Special Ops**: the official account explicitly says judges recognized its conversational picking scenario; the work result is a D365 work confirmation. Our acceptance must also see a real document change. [Official announcement](https://devblogs.microsoft.com/powerplatform/agent-academy-hackathon-winners/)
- **SAP Bell Equipment, third place at SAPHILA**: inbox freight documents are identified and matched, transport records are updated or created, and the ETA serves material planning. It included an audience vote and cannot be called a pure Agent judge award; there is no quote from judges specific to this work. [AFSUG](https://afsug.com/saphila/sap-btp-hackathon/), [SAP](https://news.sap.com/africa/2025/06/pwc-south-africa-crowned-winner-of-afsugs-first-african-hackathon-at-saphila-2025/?amp=1)
- **Google SalesShortcut, overall winner**: the story from input to downstream business work is complete, but the official announcement gives no work-specific scoring rationale; do not copy the creator's claims about many Agents. [Google announcement](https://cloud.google.com/blog/products/ai-machine-learning/adk-hackathon-results-winners-and-highlights?hl=en)
- The same Microsoft announcement separately reports judges' recognition of Calamity's safety design/engineering investment and Client Kick-off's clear situation and value presentation. This shows that checkable value, controls, and presentation deserve attention; it is not a general winning formula.
- **The parts-company original post** wanted mixed email/photo requirements read and combined with ERP/spreadsheets to prepare a quote, while explicitly retaining human review; **the distributor returns post** focused on ERP integration, credit reconciliation, and reducing warehouse rework; another D2C/3PL post was still looking for a practical AI use. These three examples support prioritizing concrete tasks, not the market size of automated receiving. [Parts](https://www.reddit.com/r/supplychain/comments/1tm6jwu/is_anyone_actually_using_ai_to_help_with_supply/), [returns reconciliation](https://www.reddit.com/r/supplychain/comments/1noyh08/anyone_using_aipowered_rma_automation_besides/), [3PL](https://www.reddit.com/r/supplychain/comments/1r5km5v/management_wants_to_integrate_ai_in_our_ops/)

Inference: our difference should focus on cross-system evidence conflict, verifiable execution, and recovery from uncertain responses. This does not support claiming Oracle/Microsoft lack recovery; the material provides no comparable baseline. Whether a small system combination costs less to deploy is also unmeasured.

## What We Can Solve and What We Cannot Yet Promise

| Work | Current evidence | Required delivery | Boundary |
| --- | --- | --- | --- |
| Partial receiving and record reconciliation | R3: two 1-Box observations; R4: one 1-Box observation out of 40 | Correctly distinguish received, posted, usable, awaiting inspection, and due, with links to original documents | Cannot infer inner-carton quantity, real loss, or an arrival outside the photo |
| Whether to retry after an integration timeout | R4 recovery after verifying a submitted document with a lost ACK | Give a clear retry recommendation while preserving the identity of the original document and inventory effect | Submitted, not submitted, and unverifiable states require separate tests and cannot be generalized across one another |
| Conflict investigation across QA, inventory, and logs | Current synthetic case read all tools but judgment failed | Give competing hypotheses, supporting/contradicting evidence, missing concrete business facts, and a safe next step | Do not promise complex diagnostic accuracy before reasoning is fixed |
| Downstream fulfillment or document reconciliation | Old 20-unit case has independent effects; new R4 is not closed | Same new order, real linked lines, correct quantity/UOM/permissions, and external readback | Without a supplier bill, do not create an accounts-payable document; invoicing is not cash collection or incremental revenue |
| Trend and efficiency analysis | Some synthetic/few observations; no matched operator trial | State denominator, unique business events, and historical coverage; measure active human time and rework | Do not treat polling as receipt count or promise predictive replenishment/ROI |

Out of this freeze: full WMS/TMS, 3PL multi-shipper operation, manufacturing/MES, automatic payment, unsupported demand forecasting, autonomous supplier negotiation, and unlimited open-domain complexity. Any later expansion needs new business evidence, permissions, and tests.

## Execution Order, Dependencies, and Delivery Gates

The following are planning targets as of September 9, not progress facts or a deadline guarantee. Materials, independent interface corrections, and version-compatibility experiments can run in parallel; the business loop and release depend on semantic and execution gates. After independent acceptance, each item gets its own commit, push, and remote-SHA check; failures remain recorded.

| Phase / target date | Work and responsibility | Verifiable delivery | Tracker |
| --- | --- | --- | --- |
| P0-A / September 10 | Repair first-turn business judgment; backend independent review | Freeze the original failed input; distinguish transport result, external-effect evidence, business executability, and execution authorization. Original and counterfactual questions pass without leaking an expected verdict to the model; the UI presents the error category correctly | F03/F07 |
| P0-B / September 10–11 | Main task session candidate; backend review | First test native summary evidence/cost for one request, then accepted cross-turn state recovery. A refused candidate must not become the next turn's fact; test source update/restart/concurrency/cross-case isolation. Compare with current budget, model, and business rules | F03 |
| P0-C / September 11 | Warehouse design + main-task implementation | Freeze one new-order path: onsite identity/quantity → normal partial receipt → ACK exception and readback → one downstream task with real basis → confirmed closure. A legitimate downstream task must add a business effect; do not decorate it with an unsupported invoice | F04/F05 |
| P0-D / September 11–12 | Backend/warehouse independent validation | Full complex-task matrix, existing holdout, and repeated real-model runs; preserve evidence and every failure by case. A critical wrong write, duplicate effect, wrong fact, or fake success blocks | F03/F06 |
| P0-E / September 12 17:00 internal freeze target | Product/release independent validation | All visible entry points, errors/refusals/recovery, keyboard/responsive behavior, and external links; current smoke coverage map passes; final SHA, clean-checkout quality, and live path check | F07/F09 |
| P1-V / from September 12, parallel with testing | Business-impact review + real operator | Measure active human minutes, switching/entry, rework, total latency, and all-attempt cost under the existing 18-pair protocol; without a real trial, provide only the measurement design and Agent-run data and mark value unverified | F11/F12 |
| P0-F / September 13 | Main-task materials + release review | English same-case video ≤5 minutes, current architecture/README/Devpost consistent, credentials and free judge access through the review period; label real and synthetic evidence in place | F01/F08/F10 |
| Final / September 14 12:00 internal submission target | User preview and final-submission gate | Recheck the official 17:00 PDT deadline; execute public video, external deployment, and final submission only after the concrete preview gate required by the existing process. The date does not automatically waive failures | F01/F10 |

Upgrade is not a prerequisite for the rest. Version 1.53.0 supports native summary/session; upgrade to the 1.55.1 fixes under independent experiment only after compatibility tests and same-task semantic comparison. Do not change version, model, prompt, budget, and memory strategy together and then lose causal attribution.

If same-case semantics and the same-order chain still fail on the evening of September 11, continue diagnosis while limiting the final demo scope to genuinely accepted capabilities and stating remaining gaps; this is a scope decision, not a way to mark an incomplete chain complete. Any scope reduction must appear in the tracker, diagram, video, and submission copy. Extra Agent roles, AgentCore migration, blog, forecasting, and decoration may wait; accurate facts, safe business effects, and truthful presentation may not.

## How to Ensure Precision, and What Counts as a Complex Problem

No test set can promise permanent open-domain accuracy. The deliverable is a defined support scope, source binding on every turn, deterministic business constraints, stopping the relevant action when unknown, and independent repeated acceptance. Define complexity by cross-source conflict, time/version change, entity ambiguity, permissions, failures, and interacting goals, not by character count or number of Agents.

Check separately:

1. Facts: case/SKU/document, quantity/UOM, time, and source scope are correct; deterministic calculations come from tool results.
2. Reasoning: distinguish not arrived, not posted, and QA unavailable; an unknown technical cause need not equal an unknown business effect, and neither may be treated as certain.
3. Dialogue: preserve correct references after follow-up, user correction, refusal, topic switch, four-plus turns, and restart; latest facts supersede stale values.
4. Action: accept proposal, authorization, execution, and external-effect readback separately; a summary or a single “continue” cannot create permission.
5. Experience/efficiency: answer the latest question; make necessary clarifications concrete and minimal; record why completion was impossible, human burden, total cost, and latency.

[Anthropic's Agent evaluation method](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) emphasizes examining trajectory and final environment state separately, together with code, model, and human judgment. This project uses independent fact/effect checks and semantic review; same-model self-evaluation, string containment, and valid JSON are not final proof. The external method informs design but does not replace this project's experiment.

See the accuracy-complexity plan for independent acceptance gates: cover current failures, frozen holdouts, and unseen rewrites; repeat every key continuous task three times and retain every attempt. Three stable runs support only that test set and do not estimate overall accuracy. Any wrong effect, unauthorized write, wrong case reference, unit mismatch, revived refused action, or false completion blocks; performance goals are separate and cannot be offset by an average score. After three consecutive failures with the same mechanism, stop that variant, locate the cause, and try again only with a justified new design.

## Follow-Up Gates for an Enterprise Pilot

After the competition, still require organizational and role authorization, tenant isolation, real WMS/ERP configuration adaptation, barcode and master-data governance, cross-operator deduplication/concurrency, production deployment and disaster recovery, quota and credential rotation, fresh source data, audit retention/privacy, monitoring/alerting and human takeover, trained real operators, and long-term workload measurement. Each needs pilot evidence; none can be inferred from a demo persona, localhost, or one recovery.

Delivery completion means research sources and limitations, competitive gaps, user needs, the plan, and the independent acceptance design are findable and reviewed. Completing this document does not change the product's NOT_READY status.

## Research Engine Collection and Manual Verification Record

Run directory: artifacts/research/cross-platform-demand-20260909/2026-09-09-award-winning-enterprise-ai-agents-across-aws-microsoft-google-s/. After the sandbox DNS precheck failed, the same authorized network task completed: 62 raw rows, 106 total rows including chunks, 54 eligible, 58 deduplicated contents, 48 duplicates, 5 invalid, 47 discovery-only, and 43 low-quality. Status complete_with_warnings / complete_with_review_required; 0 supported claim buckets and 4 facet-coverage warnings. Collection success therefore does not equal argument verification.

The key conclusions in this report and two independent source reports come from separately opening official originals, user posts, and local audits; do not call them Engine-verified conclusions. Third-party rankings/ROI calculators listed by the Engine are not used for this project's accuracy, winning rationale, or commercial impact. The Engine's availability_pressure conflict flag was reviewed against original chunks: one Microsoft self-reported case discusses stockout risk, while another product collection discusses reducing excess inventory; the objects and metrics differ, so this is not a true/false conflict about one proposition. Vendor benefit claims remain externally unmeasured and are not used as our benefits.

The current competition stand-out advice page still returned Internal Error in this run; do not claim to have read it. Official rules/FAQ were directly checked earlier in this session. Raw Engine collection stays in the run directory; the submission retains the summary/quality report and does not copy the full scrape into product documentation. The source set is limited and not an exhaustive market survey; there are no named item-by-item scores, customer interviews, hands-on runs of competitors, or security acceptance of competitor code.

## Independent Review Conclusion

The cross-platform/release review and warehouse/business-impact review both approved this research and execution plan, but did not approve product features as passing. When the business path is frozen, name the concrete downstream document or task, responsible role, and added effect; do not count existing R4 Slack/Airtable notifications again as a new closed loop. Count preceding turns, summaries, and failed consumption in the pre-frozen total budget. If dates slip or the demo narrows, keep incomplete original tasks in the tracker.
