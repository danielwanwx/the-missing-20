# Component shortage and quality live acceptance

Status: SCOPED GO for native business closure after independent final review.
Component model causality remains FAILED; overall finalization is not accepted.
This is separate from the original R4 Box order. Research and acceptance design are published in `04516b21`.

## Frozen business scenario

The provisioner was independently reviewed by Luna before native execution.
Script SHA-256: `8a4714a26a28e057df82193c7adbeb368455e8f260905d456ac6388be234b5bd`.
The authorized demo execution created dedicated batch-enabled item
`M20-DIST-COMPONENT-NOS`, PO `PUR-ORD-2026-00017` (child `4cnju12srb`),
customer orders `SAL-ORD-2026-00009` / `SAL-ORD-2026-00010` for 25/15 Nos,
and dedicated Component Inspection / Accepted warehouses. It created no receipt
or stock movement and did not change global quality settings.

LOT-A is 20 counted parts in two cartons; LOT-B is 18 counted parts in two
cartons whose nominal pack quantity is ten; LOT-C is a later two-part parcel
replacing B's shortage. The PO total is 40, not 42. There are four original
cartons and five outer packages only after the replacement. Native batches are
`M20-DIST-COMP-BATCH-A`, `M20-DIST-COMP-BATCH-B`, and `M20-DIST-COMP-BATCH-C`.

All arrival/count/inspection/carrier evidence is explicitly synthetic. The
dimension criterion is 9.90–10.10 mm. A failing sample holds its lot pending
supported disposition; it does not establish every held part is defective.
Supported full-lot inspection evidence is required to release stock from the
inspection location. No photograph, model answer, or unchanged carton count
substitutes for an inner count or physical quality test.

## Live execution and retained failures

- Provisioning succeeded; the private executed configuration is
  `/private/tmp/m20-distributor-expansion-preflight-01/component-provision-executed-01.json`.
  Runtime config is in the same directory as `component-runtime-config.json`.
  The dedicated local runtime uses port 8901 and
  `.missing20-distributor-component-20260910`.
- First LOT-A arrival event `9d5b9083-f388-41ac-8fa6-1ff82d01e785` returned
  `UNKNOWN_OUTCOME` / `ERP_WRITE_UNCONFIRMED`. The workflow did not claim any
  receipt or proceed to LOT-B. Exact request and result are retained in
  `component-lot-a-arrival-01.json`. Native readback is required before any
  continuation; an unknown response is not evidence that no native write occurred.
- Native reconciliation found exactly one draft receipt, `MAT-PRE-2026-00010`,
  with the correct PO child, 20 Nos, Batch A and inspection warehouse. PO received
  remains zero and the receipt has no stock-ledger entry. Submitting this same
  scoped draft once, without inserting or replaying arrival, reproduced HTTP 417:
  the tenant requires **Activate Serial and Batch No for Item** in Stock Settings.
  The exact request/readback/error is retained privately in
  `component-pr10-submit-same-draft-01.json`. Missing native batch-feature
  activation, not a proved missing quality inspection, explains this rejection.
  The draft remains unsubmitted. No LOT-B receipt has been attempted yet.
- The exact flag is `enable_serial_and_batch_no_for_item`. API editing returned
  403, so the already-authorized native admin UI was used to enable it. An early
  readback still showed the unsaved value; no receipt submit occurred on that
  check. After Save completed, native readback confirmed the flag is one and
  every retained quality/inspection setting is unchanged (including both Stop
  actions). Submitting the same PR10 then succeeded: 20 Nos received, PO17
  received quantity 20 and one +20 stock-ledger movement. Evidence:
  `component-batch-enabled-pr10-submit-03.json`. The local original unknown
  attempt still needs a read-only, exact-native reconciliation before LOT-B.

## Native prerequisites discovered during this run

For a new demo tenant, enable **Activate Serial / Batch No for Item** in Stock
Settings before the first batch receipt. `use_serial_batch_fields=1` alone is
insufficient. The configured service user needs Item Manager for Batch and Stock
Manager for Shipment; changing Stock Settings may require the authorized native
admin interface. Preserve the inspection and rejected/unsubmitted-QI Stop rules.
These are setup prerequisites, not a request to weaken quality acceptance.

Independent review also found that native QI Accepted alone does not establish
whole-lot coverage. The release adapter now additionally requires the persisted
QI sample size to cover the planned lot quantity; a sample-PASS report must not
release the whole lot merely because a later caller requests WHOLE_LOT.
The focused regression covers that rejected path. Live release is still pending.

## Historical outstanding acceptance (superseded by final readback below)

Establish the first native outcome, then verify real receipt/batch links,
shortage alert, numeric quality record, isolated stock, supported release without
duplicate receipt, replacement, customer allocation/dispatch and declared POD.
Use real native conversation against changed source states and independently
review both successful and failed answers. Commit/push/remote verification follows
acceptance of this slice. The R4 release does not certify this component slice.

## Inspector metadata failure and bounded continuation

- Read-only arrival reconciliation admitted the exact already-submitted PR10,
  preserving the original unknown result. LOT-B then created submitted PR11 for
  18 Nos. Actual initial receipt is four cartons / 38 Nos / two missing.
- LOT-A whole-lot inspection event `57cf0f8d-8b60-4702-87bc-ed8d174d7d05`
  created draft Stock Entry `MAT-STE-2026-00002` but no Quality Inspection.
  The exact QI-create probe returned HTTP 417 `LinkValidationError`: the native
  default `inspected_by=user` did not reference a real User. This is proved by
  `component-qi-create-exact-draft-probe-01.json`, not inferred from schema alone.
- A bounded native metadata repair used the authenticated ERP identity and
  created/submitted QI `MAT-QA-2026-00001` on that same draft. It is Accepted;
  the Stock Entry remains draft and all 38 units remain held. No receipt or
  stock movement was replayed. Evidence:
  `component-qi-authenticated-inspector-native-01.json`.
- The next UI acceptance will use a separately identified synthetic full-lot
  report after the adapter fix. The original failed event and its unsubmitted
  transfer remain visible. This is a disclosed setup repair, not evidence that
  unknown-event recovery is fully automatic. No generic retry mechanism or
  manual local-database mutation was introduced for this demo.

## Verified intermediate quality state

The inspector adapter fix passed 28 focused adapter/core tests. The actual UI
then processed a separately identified reissued LOT-A full-lot report: native
QI2 Accepted and Stock Entry3 submitted 20 Nos from Inspection to Accepted.
LOT-B sample report (diameter 10.40 mm, sample two, criterion 9.90–10.10) created
QI3 Rejected and left Stock Entry4 draft. The native state is 38 received, 20
usable/allocated, 18 held, two missing; customer demand remains 25/15.
Evidence: `component-20-usable-18-failed-2-missing-native.json`.

Real conversation evidence is retained without reclassifying failures:
- Turn1 correctly denied complete availability, but said A had no inspection
  evidence although QI1 existed after setup repair; the retained local failed
  event/quality state had not advanced. This is not a semantic pass.
- Turn2 correctly explained that sample failure does not establish all 18 units
  are defective and correctly gave customer allocation20/0 and backlog5/15.
  It incorrectly attributed the two-unit shortage to supplier short-packing.
  `component-native-turn2-causation-red-snapshot.json` preserves that failure.
  Recorded count discrepancy alone does not establish cause or responsibility;
  source evidence coverage is being qualified before another real assessment.

## Downstream continuation and retained mapper uncertainty

Supported LOT-B whole-lot reinspection and LOT-C replacement inspection released
18 and two respectively. Same PO17 now has 40 received; the initial four cartons
plus one replacement parcel are separately represented. The first customer's
20+5 parts created submitted Delivery Notes6/7 and deducted exactly25.

SO10's batch-B13 picked event `6cbc2228-ff7f-4a55-9890-288c20fa1723` submitted
Pick List6, then returned UNKNOWN for delivery creation. Exact native readback
found no DN for this customer and no related stock deduction. A controlled
mapper call for this exact submitted Pick List subsequently created only draft
DN8. No exact cause for the original uncertain response is proved; do not label
it a timeout or native validation failure. The original event is preserved.
Artifacts: `component-so10-b-pick-outcome-01.json`,
`component-so10-b-native-readback-01.json`, and
`component-so10-b-native-mapper-probe-01.json`.

A bounded adapter change will allow a new explicit picked-evidence event to
submit this exact already-verified draft, preserving all scope and ambiguity
checks and avoiding a second mapper/create. This is not automatic replay of the
original unknown event. Final acceptance of this continuation is still pending.


## Final native business readback — September 10

The exact existing DN8 draft was submitted through a new explicit picked-evidence
report after the scoped continuation fix. No second mapper/create was needed.
The retained original UNKNOWN was not blindly replayed. An earlier C2 attempt
was blocked by configured tranche sequencing; completing B13 before C2 then
succeeded. Arbitrary tranche ordering is not claimed.

| Native documents | Final effect |
| --- | --- |
| Submitted PR10 / PR11 / PR12 | Same PO17 receives 20 + 18 + 2 = 40 Nos |
| Submitted transfers SE3 / SE5 / SE6 | Supported whole-lot releases 20 + 18 + 2 |
| Retained draft transfers SE2 / SE4 | No stock effect; original repair / failed sample remain recorded |
| Submitted DN6 / DN7, Shipment4 / Shipment5 | SO9 dispatched 20 + 5 = 25 |
| Submitted DN8 / DN9, Shipment6 / Shipment7 | SO10 dispatched 13 + 2 = 15 |
| Separate declared pickup and POD events for Shipment4–7 | Synthetic delivery confirmation 25/25 and 15/15 |

Native ledger readback contains 13 stock rows and zero balance in both dedicated
Inspection and Accepted warehouses. The final projection is available, with
received40, missing0, held0, usable0, allocated0, dispatched40 and delivery_confirmed40.
It distinguishes five observed outer packages from four initially expected cartons.
A duplicate local report for Pick6 initially doubled the displayed picked count;
projection now counts the same successful native Pick List once, preserving both
reports. Fresh UI and API show picked25/15, dispatched25/15 and confirmed25/15.

Private evidence under `/private/tmp/m20-distributor-expansion-preflight-01/`:
- `component-final-native-readback-01.json`: native documents and stock ledger;
  captured before the last synthetic POD event.
- `component-final-projection-01.json`: final event history and customer projection;
  SHA-256 `a2e167ab22f69a67f3361d188556dd32bd289a62e93e5641fa15cb4d61fe2054`.

Frozen focused validation passed: 37 Python tests across distributor ERP,
distributor operations and native receiving dialogue; Ruff lint/format on all six
changed code files; mypy on both changed adapters. This is not a full-suite pass.
Native UI acceptance and independent code reviews are separate evidence.

## Model accuracy remains an open gap

Turn3 used preserved history and newly qualified current-source provenance but
still asserted supplier short-packing as certain and incorrectly described a
blocked C2 pick as picked. The complete failed snapshot is retained as
`component-native-turn3-causation-still-red-snapshot.json`. Source qualification
is correct but did not establish a semantic improvement. Do not count these
component conversation turns as passed or extrapolate an overall accuracy rate.

The next bounded comparison uses the installed Strands SDK and Nova 2 Lite with
identical prior history, newest source input and output cap, extended thinking off
initially. AWS's [Nova 2 guidance](https://docs.aws.amazon.com/nova/latest/nova2-userguide/extended-thinking.html)
documents this native model option; its claimed capability is not our acceptance
result. A private comparison script passed offline preparation only.

The user explicitly authorized the demo Nova 2 IAM policy. Automatic approval
passed on retry, but AWS rejected `iam:PutRolePolicy` for the existing
`missing20-dev` identity. No policy was changed and no Nova 2 inference succeeded.
An administrator login is pending; this is an AWS identity blocker, not a pending
user authorization. The private filename `nova2-demo-permission-applied.json`
contains the intended failed request, not proof of application.

All physical counts, quality measurements/rework, pickup and POD are synthetic.
Native ERP writes and ledger effects are real demo-tenant effects. Initial native
setup repairs, retained UNKNOWN/BLOCKED alerts and sequencing limitations remain
disclosed. This does not prove unattended production recovery, actual physical
quality testing, actual customer delivery, model causality accuracy or submission
readiness.

## Executed code hashes

- `scripts/decision_workspace_server.py`: `cbab9c7bf43a98f1e466220a879734516606bba8484bd833ed9c3b8c7a311585`
- `scripts/provision_distributor_operations.py`: `8a4714a26a28e057df82193c7adbeb368455e8f260905d456ac6388be234b5bd`
- `src/the_missing_20/adapters/distributor_erp.py`: `2409d1e41ba9a1b369ba74706385b353a41e4d814593e464da76126f9b0d791f`
- `src/the_missing_20/adapters/distributor_operations.py`: `51ac03ff1aa53783385d355c7b18f4ca260fc6c99419df35a175df69fd0b85bb`
- `tests/test_distributor_erp.py`: `45c1d3fe69a172ed0540b9f000e937719241976e4a6d378a093213a997f8b8e3`
- `tests/test_distributor_operations.py`: `ec7ffcaea17c809e34d0a00b1fcab93c2d7e9f33972f21dfba74f69017198533`


## Independent final review and release boundary

Terra High independently inspected the final native documents, stock ledger and
projection and returned scoped GO: exact PO40, SO25/15, four submitted native
DN/Shipment links, 13 ledger rows, zero scoped stock, deduplicated picks and
synthetic POD40 agree. The original inspector unknown, B13 delivery unknown and
out-of-order C2 blocked alerts remain open historical records. Consequently the
projection still has `stage=HOLD`; the final aggregate stage is not a clean green
screen despite the verified completed quantities. Alert lifecycle cleanup and
unattended generic recovery are not accepted by this release. Model causality
FAILED and pending IAM access are expressly excluded from GO.


## Nova 2 access restored and matched comparison — September 10

After the user switched the console identity, the authorized inline policy
`Missing20Nova2LiteInference` was created on `Missing20DeveloperRole`. A fresh
IAM API read matched the intended policy exactly. An actual Bedrock Converse
call under `assumed-role/Missing20DeveloperRole/missing20-dev` returned `OK.`
with 50 input / 3 output tokens and `end_turn`. The policy/access blocker is now
resolved. Evidence: `nova2-policy-verified-probe-01.json` in the private directory.

The subsequent matched Strands comparison used the retained failed conversation
history, exact newest source input, Nova2 Lite with extended thinking off and
the existing 1551 output cap. It raised `MaxTokensReachedException`; no complete
answer or semantic pass was obtained. Evidence:
`component-nova2-matched-comparison-01.json`. This is a new output-budget result,
not an IAM failure or proof that Nova2 fixes attribution. The product remains on
its existing model pending a separately evaluated configuration.


## Visible completion with retained alerts

A separately reviewed presentation change now displays `Delivery confirmed · 3
alerts to review` on the current component page. It requires positive ordered
quantity, exact matching received/dispatched/confirmed totals, zero held/missing/
usable/allocated quantities and available current source. Incomplete data or
partial delivery keeps the original stage. Backend HOLD, original alerts and
synthetic-evidence labels are preserved; this is not alert resolution.

Terra High independently returned GO. The implementation's 114 JS tests passed;
primary verification passed the 13 relevant JS tests and a fresh actual in-app
browser reload on port8901. DOM readback confirmed the new label, all three
UNKNOWN/BLOCKED alert records, declared synthetic inputs and SO9/SO10 picked,
dispatched and confirmed25/15. No new ERP write or model invocation was needed.
