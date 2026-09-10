# R4 remaining-39 distributor live acceptance

Status: **VERIFIED_IN_DEMO — scoped R4 receiving, fulfillment and declared
synthetic delivery.** This record does not certify the component-quality slice or
the entire product. Research/design was independently reviewed and published in
commit `04516b21c36634ccb36ca392828fef14a6c2a767`.

## Scope and evidence boundary

Real native writes target the existing authorized demo ERPNext 16.34.2 tenant.
Physical arrival, picking and carrier/POD observations are declared synthetic.
PO `PUR-ORD-2026-00016` has a 40 Box line, child `458j82kp8e`. The previous
`MAT-PRE-2026-00007` / `ACC-PINV-2026-00008` cover 1 Box. This follow-on covers
only the other 39 Box, in the dedicated `M20 Distributor R4 Accepted - M20`
warehouse. Customer orders `SAL-ORD-2026-00007` and `SAL-ORD-2026-00008` request
24 and 15 Box. Intended partial picking/dispatch is 20, 4 and 15 Box.

No real carrier booking, customer message, payment or new invoice is included.
Planned allocation is not native Stock Reservation, which remains disabled.

## Retained failed attempts and researched corrections

1. Initial provisioning created the two scoped warehouses, then native Customer
   validation rejected the group node `All Customer Groups`. Readback found the
   existing leaves `Demo Customer Group` and `United States`. The corrected
   provisioner reused the warehouses and successfully created the scoped
   customers, sales orders, addresses and contacts. Luna independently reviewed
   the correction. One local sandbox DNS failure made no ERP request; the
   subsequent authorized network execution succeeded.
2. The first UI arrival created submitted Purchase Receipt
   `MAT-PRE-2026-00008`, 20 Box. Native SO-to-Pick-List mapping then returned two
   candidate locations: 6 Box in shared Stores plus 18 in the dedicated location,
   where actual stock was 20. The adapter refused that ambiguous mapping.
   Installed v16 source confirms `parent_warehouse` and `pick_manually` support
   retaining an explicitly selected location, while native picked-stock
   validation still applies. The correction selects only the dedicated location
   and preserves the 20/4/15 quantities. Luna independently reviewed it; native
   downstream acceptance is recorded below.
3. A parallel native readback timed out under the existing eight-second transport
   timeout. Retrying read-only evidence collection with independent result
   capture does not change the product transport or hide the failed attempt.
4. UI polling can replace an answer with an empty conversation projection.
   The observed display defect was corrected and checked across later polls;
   native conversation success alone did not count as a visible UI pass.
5. After the warehouse correction, actual picked evidence continued from PR8
   without another receipt: Pick List `STO-PICK-2026-00001` completed and
   `MAT-DN-2026-00003` submitted 20 Box. Shipment creation then refused duplicate
   candidate Delivery Notes. The native v16 `create_delivery_with_so` saves its
   draft before returning it; the adapter had inserted another copy. Thus
   `MAT-DN-2026-00002` remains a draft from this failed attempt, while DN3 is the
   one submitted dispatch. The correction must submit the native saved document
   directly and resume only the missing Shipment step. No second dispatch is
   justified. [Installed-version native source](https://github.com/frappe/erpnext/blob/v16.34.2/erpnext/stock/doctype/pick_list/pick_list.py).
6. After PR9 received the other 19 Box, the default native mapper could satisfy
   SO7's remaining 4 entirely from shared Stores and therefore returned no scoped
   row to filter. A read-only native probe with serialized `target_doc` containing
   `parent_warehouse` returned exactly the scoped 4 Box. The adapter now supplies
   this supported input before mapping. Subsequent actual 4-Box picking and the
   pending first Shipment completed, with no duplicate receipt or dispatch.
7. Slow-input UI inspection found five-second refreshes clearing an unsubmitted
   Shipment/evidence form. A separate customer-display check showed global
   delivery-confirmed 15 after the synthetic B POD, but its order row still said
   delivery pending. These visible defects are not native inventory failures;
   form retention and projection of existing per-Shipment customer evidence are
   under correction before final UI acceptance.
8. The fourth real Bedrock turn failed semantic acceptance: after all 39 Box
   dispatched and customer B's 15 confirmed, it repeated the earlier 20-dispatched,
   B-unallocated state. The displayed source was current; native history is
   retained in `r4-native-turn4-stale-red.json`, SHA-256
   `6c6c30e62a504c40442684b266195b39aa07d933f902cd6985b9f05cc321c9ca`.
   Current-evidence refresh across a persistent conversation is being diagnosed.
   The first three successful answers do not override this failure.

### Source-refresh correction

Inspection of retained native history showed turn4 used no tools. The runner
rebuilt fresh tool closures each turn but sent only the human question, leaving
the model free to answer from an old tool result. Installed Strands 1.53.0
supports native `Messages` input. The correction appends one user message with
the complete current qualified source JSON plus the newest question; the JSON is
explicitly evidence, not instructions. The existing session, frozen system prompt,
history and read-only tools remain intact. No summary model or new framework was
introduced. Current evidence availability is assured by this wire shape; correct
reasoning still requires actual model review.

Runner SHA-256 `fc807378fb2cd4b0741cb076e2c508313290041493c80dc5612a320bc2c60934`;
test SHA-256 `d3a26eee7aa17e0952ccb582732d433f24204558e8141288d72142fc33ead91a`.
A no-tool second-turn regression failed before the change and passed afterward.
All five focused native dialogue tests passed. Luna independently reviewed the
change and gave GO for the real-provider rerun; semantic acceptance remains
separate. Native mechanisms:
[Agent Messages input](https://github.com/strands-agents/harness-sdk/blob/main/strands-py/src/strands/agent/agent.py),
[Snapshot session persistence](https://github.com/strands-agents/harness-sdk/blob/main/strands-py/src/strands/session/snapshot_session_manager.py).

Private evidence directory:
`/private/tmp/m20-distributor-expansion-preflight-01/` (0700; JSON/log files 0600).
It retains provisioning attempts, exact mapper response, first-arrival journal,
readbacks and model responses. The initial ten-file implementation snapshot is
`/private/tmp/m20-distributor-r4-frozen-01/`, manifest SHA-256
`1c830510caffe0e9c84333ea62460f44ac03a31da6df17f87081cb9642a7977f`.

## Current model evidence

The first native readback is now verified in
`r4-first-receipt-native-readback-02.json`: submitted PR8 has 20 Box against the
same PO child; stock entry `a1f2627846` adds 20 to the dedicated warehouse. The
parent PO reports 21 received, shared Stores remains 6, and old PR7/PI8 remain
submitted at 1 Box each. Opening the app's receipt link in the native ERP UI
also shows 20 accepted, zero rejected, the scoped warehouse and `To Bill`.

One retained successful query uses native Strands and Bedrock
`us.amazon.nova-pro-v1:0`, region `us-west-2`, session
`m20-native-receiving-n1-fe3ed14f6d2d46b0e2b82d6d`. Asked which customers can
receive the current arrival, what remains outstanding and whether goods have
shipped or arrived, it correctly states 20 Box allocated to SO7, SO7 short 4,
the second arrival of 19 outstanding, and zero dispatched/delivery-confirmed.
The response is recorded in `r4-native-question-01-response.json`. A second
question asks about “the other customer” without restating its identifier; the
same native session correctly identifies SO8, demand 15, allocation zero and
the same PO16. That response is in `r4-native-question-02-response.json`.
These two responses pass the current limited semantic check. They do not yet
constitute an accuracy rate. Luna independently reviewed both historical
responses against their included source projection and reported GO.

A third question was entered through the actual `/operations` page after 20 Box
dispatch. It asked whether the situation had changed and why the customer had
not received the goods. The same native conversation correctly updated its
answer to 20 dispatched and zero delivery-confirmed, distinguishing absent
confirmation from proof of actual customer receipt. The corrected page displayed
`bedrock · us.amazon.nova-pro-v1:0` and retained the answer through subsequent
five-second polls. Native snapshot `r4-native-after-ui-turn3.json` has SHA-256
`4026ab5409d2976a01da1382ef08a7bafd03e1bb7d68b859cb6c1cad4761239b`.

## Native outbound acceptance

Seventeen native records and all five scoped stock-ledger entries were read back
without errors. `r4-outbound-native-readback.json` SHA-256 is
`5e4674cb439acad6ef72f55d26b14e3a178498249c4ab7b810b569b1582beaa2`;
`r4-outbound-native-verified.json` contains the independent assertions.

| Customer order | Quantity | Pick List | Submitted Delivery Note | Submitted Shipment |
| --- | ---: | --- | --- | --- |
| SO7 (24 total) | 20 | STO-PICK-2026-00001 | MAT-DN-2026-00003 | SHIPMENT-00003 |
| SO7 (24 total) | 4 | STO-PICK-2026-00003 | MAT-DN-2026-00005 | SHIPMENT-00002 |
| SO8 (15 total) | 15 | STO-PICK-2026-00002 | MAT-DN-2026-00004 | SHIPMENT-00001 |

New receipts PR8/PR9 are 20/19 against the original PO child. The parent PO has
40 received; the follow-on has 39. Native customer-order delivered quantities
are 24/15. Scoped ledger movements are +20,+19,-20,-15,-4, leaving zero;
shared Stores remains 6. The old one-Box receipt and invoice remain submitted
at one. DN2 remains an unsubmitted failed-attempt draft with no stock movement.
The operational alerts cleared after supported continuation. Native shipments
are `Submitted`; this is not physical delivery proof or customer billing.

## Final scope and limitations

An intermediate live-page check correctly showed B15 confirmed and A24 pending.
Historic activity is hydrated from retained typed event payloads. A slow-input
check preserved Shipment3, its evidence ID and input focus across multiple
five-second refreshes, then submitted its synthetic pickup once. A separate
final-review browser tab was used after the earlier tab navigated away; no
cause for that navigation has been established.

All three synthetic pickup/POD pairs now pass exact customer mapping: A received
24/24 across Shipment2 (4) and Shipment3 (20); B received 15/15 on Shipment1.
The live page shows these numeric counts and uses Box in historical count rows.
Private final projection `r4-all-pod-projection-01.json` SHA-256
`19c0ad9e36a3c4afa44bbab9ccbeb8e0fc8ec77fa664a74de28fc41f3b0ed10e`
passed independent assertions for 39 total and exact 24/15 shipment mappings.
All three earlier native-operation alerts are retained as resolved.

The corrected fifth real UI turn stayed in the original native session and
reported A24 (20+4) and B15 from the current snapshot. Private native history
`r4-native-turn5-fresh-source-green.json` has SHA-256
`92a9663020aafe952e14b98a9a0100707c3a24e6a34a2466bed29784c80d66cd`.
Luna independently gave semantic GO for that specific answer.

Turn6 correctly reported zero missing but gave an unclear proof explanation.
It remains retained in `r4-native-turn6-evidence-boundary-red.json`, SHA-256
`dea68d2be51e14de56585bfd1cee2d826c5c0ded81e4f5d7873dff23b2699bc1`.
Inspection found the source packet itself called synthetic POD “physical evidence”.
The packet now explicitly qualifies recorded test events separately from native
PO/PR/SLE inventory accounting. No quantities, expected answers or evaluation
rubric were injected by that correction.

Turn7 repeated the same question and correctly reported zero missing and that
synthetic pickup/POD cannot prove real customer receipt. Its private snapshot
`r4-native-turn7-qualified-provenance.json` has SHA-256
`65dbd88242f56ac46d424fc1b1e8965d1869924dfd151edabb70445b0e949210`.
Luna gave scoped numeric/provenance GO. A minor explanation defect remains:
the answer partly uses customer delivery to explain inbound completion; these
are separate facts. Field-name/English quotations also need later wording polish.
These limitations are retained under the user's demo-first scope, with no broad
accuracy or complete-product semantic claim.

Independent review gave GO for the R4 native business path and native current-source
message mechanism. Relevant working checks passed: 27 distributor core/adapter
tests (including the separately unaccepted component work), five native dialogue
tests, and 12 UI tests. They are focused checks, not a whole-repo or production
certificate. The release index excludes unfinished component adapter/provisioning/
reconciliation changes. No payments, real carrier booking, new customer billing
or physical-world delivery is certified.

The exact release index was exported to the private directory
`/private/tmp/m20-r4-release-index-ijctlekw` and its three relevant Python suites
passed all 25 tests independently of the unstaged component code. This verifies
the staged slice's internal integration; native/UI/model evidence remains the
separately scoped evidence recorded above.
