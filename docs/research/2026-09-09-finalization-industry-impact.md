# Finalization: independent warehouse and business-impact review

Reviewed 2026-09-09 (America/Los_Angeles). Code-reference HEAD: `be419eab1d5faedfecb140fde7112a5443f9cedc`. Role: independent warehouse-operations and business-impact reviewer; no implementation ownership. This report is a bounded research/design review, not live system acceptance, an accounting opinion, or production approval.

## Evidence method and conclusion

The main task owns the Research Engine run. This reviewer independently opened primary public documents through the read-only web tool; **the sources below were not collected or validated by Research Engine**. Reviewed local AGENTS, finalization handoff, R4/R3 audits, warehouse research/gap baseline and revenue causal validation. Inspected source references only to distinguish an existing downstream executor from a demonstrated photo-linked downstream chain. No model invocation, business-system write, new external readback, operator timing experiment or customer interview was performed.

Retain a **parts distributor's receiving/operations manager** as the primary user, with receiving staff supplying physical facts and finance/QA owning their decisions. This is a design inference with medium confidence, not validated product-market fit. The documented procurement, partial receiving and stock/accounting interfaces map directly to the existing implementation. A parcel station primarily handles custody, identity and delivery events, not the distributor's inventory/AP/sales ledger. A 3PL introduces client ownership, client-specific rules and WMS interfaces that the current single-company case does not establish. Consumer workflows dilute this business chain. Do not expand those segments before proving the current one.

The strongest current evidence is R4's one confirmed arrival, ERP receipt and lookup-only recovery after a lost ACK, with stable downstream notification identities. R3 demonstrates two legitimate partial receipts and stale-plan handling. **Neither audit accepts the new receiving chain through billing/fulfillment or stable multi-turn answers.** Those remain P0 acceptance gaps. Routine matching, price fetching, quantity arithmetic and native barcode entry already exist in ERP/WMS; the useful Agent hypothesis is less cross-system investigation and re-entry while preserving these controls.

## Current primary-source refresh

All links below were accessed directly on 2026-09-09. Vendor documentation establishes documented behavior, not this tenant's version/configuration or universal warehouse policy. No vendor savings percentage is adopted as our baseline.

| ID | Direct source | Verified claim and limitation |
| --- | --- | --- |
| S1 | [ERPNext Purchase Receipt](https://docs.frappe.io/erpnext/purchase-receipt) | Receipt separates accepted/rejected quantities; UOM and item fields come from masters; conversion matters. Rates come from authorized pricing configuration. `To Bill` means awaiting billing, not an existing open invoice. Native barcode entry already exists. Rolling documentation; inspect deployed settings. |
| S2 | [Microsoft inbound loads](https://learn.microsoft.com/en-us/dynamics365/supply-chain/warehousing/inbound-load-handling) | Planned inbound load, quantity registration, ledger posting and putaway are distinct. Partial registration is supported. Receiving/putaway and overreceipt behavior depend on configuration. A partial PO is not by itself evidence of a lost shipment. This is a reference workflow, not proof ERPNext implements identical states. |
| S3 | [GS1 logistics-unit identification](https://support.gs1.org/support/solutions/articles/43000734289-what-is-a-logistics-unit-and-how-is-it-identified-) | SSCC identifies a logistic unit and enables lookup of transaction information. It is not sufficient evidence of purchase price, authorized receipt, or inspected contents. The original GS1 `/standards/id-keys/sscc` URL returned a tool error; this official support page was successfully opened. |
| S4 | [ERPNext Purchase Invoice](https://docs.frappe.io/erpnext/purchase-invoice) | Records the supplier's bill/payable. Supplier bill number/date, billed quantity/rate and linked receipt matter. Invoicing an existing receipt normally clears stock-received-not-billed; `Update Stock` is an alternative path requiring care to avoid another receipt effect. A photo cannot establish a supplier bill. |
| S5 | [ERPNext Accounting Entries](https://docs.frappe.io/erpnext/accounting-entries) | Sales Order is commitment; Delivery Note affects stock/COGS in perpetual inventory; Sales Invoice posts income/receivable; Payment Entry records cash/bank movement. These are separate economic events. Product documentation does not replace enterprise revenue-recognition policy. |

Independent source inference: an image can document visible package count, labels and apparent damage within its coverage; it cannot prove concealed contents, QA measurements, supplier invoicing, carrier acceptance or payment. An identifier can retrieve applicable records; authority, uniqueness, UOM and policy must still be checked. Do not make the overbroad claim that *all* barcodes contain only identifiers: the claim here is that an SSCC or this demo identity is not purchase-price authority.

## Claim → evidence → rubric → gap → action

Rubric names below are working mappings to the handoff's five dimensions; the main task must confirm current official rules. No score is invented from this limited review.

| Claim | Evidence | Rubric | Current gap / priority | Acceptance action |
| --- | --- | --- | --- | --- |
| One physical input leads to a verified business effect | R4 audit: PO16, PR7 +1 Box, persisted uncertain intent, restart/readback, Slack/Airtable identities | Technical Implementation; Presentation | Scoped `VERIFIED_IN_DEMO`; public photo plus typed demo identity, not field proof | Preserve accepted recovery; show test-substitute label. Independently inspect new end-to-end evidence on frozen version. |
| Partial arrival is normal; remaining order is not loss | S2; R3 2/40 Box, R4 1/40 Box and no current gap | Design; Technical Implementation | Conversational reliability `FAILED`, P0 | Three repeated real-model core and held-out conversations: answer outstanding vs missing, exact UOM, refusal/correction and explicit retry decision. All attempts retained. |
| New photo receipt connects to downstream work | R4 open gates; existing `adapters/demo_executor.py` has delivery/invoice paths, while photo adapter has receipt paths | Technical Implementation; Potential Impact | Same-case connection `NOT_VERIFIED`, P0; existence of executor is not proof of photo-chain reachability | New case with documented supplier bill or valid customer demand; exact receipt-line linkage; safe quantity, authorized action, external readback. Never bill the 40 ordered boxes from a one-box receipt alone. |
| Agent reduces operational work | Existing audits lack matched control | Potential Impact | `NOT_STARTED` measurement, P1; no measured savings | Run paired protocol below; show active effort and wall time separately, including rework/failure. |
| Business value is traceable | S4/S5; causal-validation report; R4 has no invoice/revenue proof | Potential Impact; Presentation | P0 claim integrity; P1 quantified impact | Label order value/exposure, received value, billed sales and cash separately. Unsupported value stays unavailable. |
| Exceptions are closed only after their effect verifies | R3 Jira fix verified comments/transition separately; R4 readback preserves original intent | Technical Implementation; Creativity & Originality | Existing repair should not be rebuilt; full adverse matrix not accepted, P0 | Exercise ACK actually posted/unposted/unqueryable, mixed units, stale confirmation, refused action and partial SaaS failure. Unknown must not become success. |

## Minimal operational chain and responsibility boundary

Freeze one company, supplier/item/PO line, arrival identity and receiving warehouse. Explicitly select direct receipt to the final warehouse or staged receipt with a later physical transfer. Do not label a staging receipt “put away.” Required correlation fields are company, case, PO and row, SKU, receipt/stock UOM and conversion revision, arrival/package identity, observed/confirmed quantity, disposition, target warehouse, source revision and actor/authority. Batch/serial and QA prerequisites apply when the item/policy requires them.

The receiving worker confirms actual physical facts. The Agent can look up candidates, compare source versions, investigate an integration/quality discrepancy, prepare an evidence-backed proposal and explain the remaining work. Deterministic tools bind identity, quantities, permission and idempotency to the approved version. Normal authorized progression and recovery should run automatically. Unknown SKU/quantity, conflicting labels, QA disposition and consequential new billing/dispatch authority require the appropriate evidence or role; one generic manager approval must not fabricate those facts.

For the competition, prove photo/identity → partial receipt → exact stock readback → one meaningful, authorized downstream document/task → readback, plus a contrasting exception/refusal. This does not require a complete TMS, manufacturing line or 3PL product. Before production, independently verify tenant-scoped identity/roles, master-data ownership, physical arrival identifiers across cameras, concurrent workers, token expiration, rate limits, external timeouts, immutable audit retention, operational alerts, support ownership and real operator training. Demo replay success alone covers neither cross-worker races nor multi-tenant isolation.

## Same-workload measurement protocol

This is a proposed protocol, not experimental results. Existing cumulative inventory observations are not time-to-receive samples. Repeated polls and repeated requests for one arrival never increase the count of unique business cases.

1. Freeze the code, prompt/model, policy, source snapshot, roles, case definitions, deadline and success oracle before starting. Each control/treatment pair gets isolated, equivalent data and identical source-system access. Both receive the same physical-input substitute and evidence packet at `t0`. Normal human control uses existing ERP/WMS features, including barcode entry; do not force manual arithmetic/retyping that native software avoids.
2. Use six families: normal partial arrival; legal second arrival vs same-arrival replay; lost ACK already posted; lost ACK not posted/source unavailable; identity/UOM conflict; QA or supplier-bill mismatch with refusal/correction. At least three paired repetitions per family (18 pairs), distributing controls across at least three trained operators. If unavailable, report the smaller pilot and its operator limitation. Three model repeats address variability; they are not three independent customers.
3. Randomize variant/order and counterbalance control/treatment exposure to reduce learning effects. Hold out paraphrases and decisive source changes from implementation. An independent reviewer judges exact documents, quantity/UOM, permissions, explanation and recovery. Record all attempts, retry cost, corrections and abort reasons; never discard failed runs or count a diagnostic rerun as the original success.
4. Record UTC event timestamps plus monotonic duration; timer ends at verified correct terminal outcome or a predeclared timeout. Measure human active seconds from recorded interaction/review/rework intervals, not from the entire Agent wait. Parallel human intervals are summed as labor but unioned for elapsed time. Fix the definition of a touch: one substantive operator input, approval, correction or source query; record app switches separately. A typed field counts each entry/re-entry, not characters.

For pair `i`, `Hc_i` and `Ha_i` are active human minutes in control and treatment, including review and rework. `Tc_i` and `Ta_i` are wall-clock minutes from the same trigger to verified completion. Negative differences are retained.

```text
active_minutes_saved_i = Hc_i - Ha_i
paired_relative_effort_change_i = (Hc_i - Ha_i) / Hc_i  [undefined if Hc_i = 0]
aggregate_effort_reduction = (sum(Hc_i) - sum(Ha_i)) / sum(Hc_i)
safe_completion_rate = independently_verified_correct_terminal_runs / all_eligible_started_runs
unsafe_write_rate = runs_with_any_unauthorized_or_incorrect_write / all_eligible_started_runs
duplicate_effect_rate = unique_arrival_intents_with_excess_business_effects / unique_arrival_intents_tested
human_review_rate = runs_requiring_substantive_human_review / all_eligible_started_runs
fields_per_run = total_entered_or_reentered_fields / all_eligible_started_runs
cost_per_verified_case = all_attempt_compute_infra_and_review_cost / verified_correct_cases
throughput = verified_correct_cases / observation_hours
backlog_end = backlog_start + eligible_arrivals - verified_closed_cases
```

Distinguish planned necessary review from avoidable corrections. Report no-op correct dispositions separately from completed writes; both count for safe completion. A source outage remains in the intent-to-treat denominator and is labelled environment failure. Optional sensitivity analysis may exclude it only with an explicit second denominator. Missing timestamps are missing, not zero. Timeouts remain failures with lower-bound elapsed time; summarize successful-run latency separately and disclose its selection bias.

Report p50/p95 wall time (nearest-rank order statistic `ceil(p*n)`), active-human median/range, successful `n`, total `N`, timeout/failure count and per-family results. With 18 observations p95 is effectively the maximum; do not imply a stable population tail. Pair-level records and operator IDs matter more than a flattering average. No extrapolation to annual savings without a measured arrival mix, annual volume, loaded labor assumption and uncertainty/sensitivity range.

## Financial measurement and no-double-counting contract

Order value is a commitment/exposure; inventory receiving value is an asset-related amount; supplier billing is payable; customer billing is income/receivable; cash requires a separate payment event (S4/S5). R4's USD 50 is synthetic receipt value, not revenue generated or cash saved.

For an explicitly fixed horizon and matched customer-order cohort, use net billed sales excluding tax, returns and credit notes. Treatment-minus-control billed sales is **billed timing/outcome difference**, not automatically incremental economic revenue: determine whether the control later bills the same order. Earlier billing alone is acceleration; documented control cancellation due to the scoped constraint can support protected sales. Contribution margin subtracts incremental variable cost; gross margin separately uses the applicable COGS policy. Cash acceleration needs payment/bank dates; paying an AP bill is an outflow, not cash released.

```text
labor_capacity_value = sum(active_minutes_saved_i) / 60 * disclosed_loaded_hourly_rate
net_value = nonoverlapping_verified_margin_and_cost_benefits - incremental_total_agent_cost
ROI = net_value / incremental_total_agent_cost  [undefined when denominator = 0]
```

Labor capacity value is not automatically cash saving: reduced paid overtime or actual staffing spend needs evidence. Total Agent cost includes every model attempt/retry, infrastructure, human review/rework, integration/support and explicitly amortized setup. If labor is already included in a margin/cost benefit, do not add it again. Keep sensitivity scenarios separate from observed outcomes, and do not add exposure, sales, margin and cash principal together. Without matched controls and authorized source documents, ROI remains `UNAVAILABLE`; a negative result is valid.

Independent verdict: **warehouse fit is plausible; R4 recovery evidence is credible within its documented slice; whole receiving-chain acceptance and measured business improvement are withheld.** No official competition score, production claim or positive ROI can be assigned by this report. Stop source expansion here; the next useful evidence is frozen-version operator and external-system verification.
