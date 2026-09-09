# Cross-platform enterprise awards: independent source review

Accessed 2026-09-09. Supplements the [prior AWS comparator review](2026-09-09-finalization-comparators.md); these are separate competitions, not winners of our current competition. Microsoft and SAP provide comparators outside Devpost; Google provides a different sponsor/ecosystem although its entries also use Devpost.

## Bounded research contract

Goal: three relevant, source-grounded comparisons with award identity, attributed evaluation, business loop, complexity and applicable action. Input: public organizer publications and linked author materials only. Execute: locate → open → distinguish identity/evaluation/implementation claims → compare → record limitations. Checks: official identity for each included award; no inferred judge quotes, no measured benefit without measurement, no production-readiness conclusion from an award. Missing original evaluation becomes an explicit gap. Stop after three useful cases with disclosed source limits. No service calls, dependency execution, account changes or product implementation.

Evidence labels: **O** organizer-confirmed fact; **E** organizer's report of judges' evaluation, not a named judge transcript; **A** entrant's account; **R** this reviewer's inference/recommendation. Public repository documentation was read, but no comparator code was executed. None of these comparisons verifies a live deployment.

## 1. Warehouse Picking Agent — Microsoft Agent Academy, Special Ops third

**O/E:** Microsoft's June 18, 2026 announcement identifies the Special Ops third-place project by `granjan7779`. It describes reading outbound pick work and confirming work in Dynamics 365 through MCP, including work-line identity, license plate, quantity and work type. It explicitly reports that judges valued the business case for conversational picking as an alternative to specialized devices. This is attributable organizer reporting, not an individually named judge quote. [Microsoft announcement](https://devblogs.microsoft.com/powerplatform/agent-academy-hackathon-winners/)

**A/documentation inspected:** The linked repository documents two principal tools, `readOpenLines` and `confirmWork`, an Azure-hosted Node MCP bridge, D365 OAuth and session handling. It requires an authorized D365 environment and Azure setup; its README includes placeholder clone instructions and a broad D365 permission setup. These are documented requirements, not verified security or reproducibility guarantees. [Public repository](https://github.com/granjan7779/rj-mcp-d365-server-2) (publication date not exposed; accessed September 9).

**Business loop:** warehouse user → open work retrieval → chosen work/quantity → D365 work confirmation. The primary business effect is operational record confirmation, not merely a generated explanation. This is outbound picking, whereas our verified case is inbound receiving; identities and write semantics cannot be copied blindly.

**R — useful lesson:** A short, concrete operational job can be award-relevant without a large agent topology. Our analogous demo should expose the order/receipt identity, confirmed quantity/UOM, allowed action and exact resulting record. Preserve correction and refusal. Test changed or missing identity before writing and independently verify existing record after an uncertain acknowledgement.

**Complexity/limits:** the documented bridge is relatively narrow, but enterprise authentication and consequential confirmation are substantial. Neither announcement nor inspected README establishes human approval behavior, exactly-once effects, restart recovery or measured replacement of hardware. Do not assert these are absent in the product; they remain unverified here. No reason to add voice or D365 to our implementation simply to resemble this winner.

## 2. Bell Equipment — SAPHILA 2025 shipment automation, third place

**O:** AFSUG's event page identifies Bell Equipment as third, and explains that finalists presented to an audience whose voting contributed to the result. Thus this is not a purely judge-scored Agent award. It is a relevant enterprise automation comparator. [AFSUG result and finalist resources](https://afsug.com/saphila/sap-btp-hackathon/) (2025 event; page undated).

**O, reported implementation:** SAP's June 2025 news article describes scheduled inbox monitoring for shipping documents, OCR/classification and document-specific processing, then matching existing shipment records to update them or creating new ones. ETA updates support materials planning and shortage intervention. SAP Build Process Automation and CAP are named. [SAP News](https://news.sap.com/africa/2025/06/pwc-south-africa-crowned-winner-of-afsugs-first-african-hackathon-at-saphila-2025/?amp=1)

**Evaluation boundary:** The same SAP report attributes a general evaluation emphasis on innovative use of BTP services to Olaf Winkler and identifies SAP product managers' judging participation. It does not supply Bell-specific judge wording or a numeric score. AFSUG confirms placement; neither placement nor organizer benefit language proves achieved cost savings. The linked presentation request returned a cache miss, so no slide/video claims are included.

**R — useful lesson:** Start with an actual incoming operational artifact, reconcile it against existing identity, then make the business consequence inspectable. Our receiving photo/identifier → existing order/receipt → verified posting is a comparable chain. A changed ETA is not a received unit, just as 39 still ordered is not evidence of 39 lost units. Keep those meanings explicit.

**Complexity/limits:** scheduled ingestion, OCR, several document paths and update-or-create logic add reliability burden. Borrow identity-first reconciliation and an actionable planning signal, not another mailbox or polling service. Unknown acknowledgement still needs a read-before-retry rule; this source does not establish Bell's idempotency behavior, physical truth verification, human escalation or production performance. Our acceptance must independently test those properties instead of treating an award as evidence.

## 3. SalesShortcut — Google ADK Hackathon Grand Prize

**O:** Google Cloud's September 2, 2025 winner announcement confirms SalesShortcut, by Merdan Durdyyev and Sergazy Nurbavliyev, as Grand Prize. Its description covers lead generation, research, proposal and outreach. The article has general praise for winners' execution/ADK knowledge, but no project-specific judge reasoning, named judge quote or published project score. [Google announcement](https://cloud.google.com/blog/products/ai-machine-learning/adk-hackathon-results-winners-and-highlights?hl=en)

**A:** Entrants describe Maps-based lead discovery, specialist research, tailored proposals, voice calls/email, tracking and appointment scheduling. They claim 34 agents, five Cloud Run services, A2A, review/refinement and human oversight, and identify coordination, data consistency and parallelism as challenges. The enumerated agent subtypes sum to 32 rather than 34; do not use the headline count as an audited architecture fact. Claimed deal closure and production readiness are not independently demonstrated by this review. [Entrant description](https://devpost.com/software/salesshortcut) (date not exposed; accessed September 9).

**R — useful lesson:** A viewer can understand the progression from a business input to a consequential next step. For us, keep the whole visible sequence on one selected case. Do not substitute old commercial proof for a new receiving result. Show the agent's research changing its next allowed action and preserve the resulting external identity.

**Complexity/limits:** this broad prospecting system is a poor implementation template for our bounded warehouse task. Its many services/agents and outbound communications create independent failure and authorization obligations. No comparator latency, cost, conversion, retry or task-quality benchmark was reproduced; agent count is not a target or a reason to extend scope.

## What the official evaluation evidence actually permits

The Microsoft announcement explicitly reports judges valuing Calamity Agent's safety and engineering, and Client Kick-off Skill's clear scenario/value presentation. These are organizer-attributed observations, not verbatim named-judge testimony. Alongside its Warehouse Picking assessment, they support inspecting usefulness, controls and comprehensible demonstration; they do not establish universal winner preferences. [Microsoft announcement](https://devblogs.microsoft.com/powerplatform/agent-academy-hackathon-winners/)

Google supplied award identity without specific judge reasons. SAP supplied identity, voting context and a general evaluator statement, without Bell-specific evaluation. No invented scores, causal winning formula or forecast is warranted.

## Synthesis for our next review loop

| Inference from comparison | Our measurable acceptance action | Complexity to avoid |
| --- | --- | --- |
| A narrow operational effect can carry a clear business case | One operator question, case identity, allowed action, actual source result and uncertainty/recovery explanation remain consistent through reload | Adding agent roles to match winner counts |
| Incoming artifacts matter when tied to authoritative records | Distinguish observed physical quantity, confirmed quantity, posted receipt, remaining order and quality hold on the same case | Treating OCR/photo output or an ETA as settled inventory truth |
| Documentation is part of delivery but not execution evidence | Keep credential-free inspection, live provider-dependent agent paths and historical proof separately testable | Calling a replay a live demo or award copy a production audit |
| Reported judging values include practical work and clear explanation | An independent warehouse reviewer can explain what changed and whether to retry without reading internal traces | More decorative topology or marketing metrics before semantic acceptance |

This bounded comparison is complete. No actual public end-user adoption discussion was established for these three products; comments/likes or organizer congratulations are not usability validation. SAP's newer invoice-reconciliation entrant article was found, but its runner-up identity was only self/colleague asserted in retrieved materials, so it was excluded from the three official-identity comparisons. Implementation acceptance, full smoke, live diagnosis and final submission remain independent work.
