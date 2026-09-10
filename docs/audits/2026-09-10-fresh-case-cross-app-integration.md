# Fresh-case cross-app integration — scoped acceptance

September 10, 2026. This accepts runtime wiring, retained UI evidence and isolated
case provisioning. It does not certify the remaining inspection/allocation,
dispatch/delivery, financial or dialogue acceptance.

The fresh case `M20-DIST-COMPONENT-FINAL-20260910` uses PO18, SO11 (A25,
September 11) and SO12 (B15, September 12). Initial native readback had zero
received, held, allocated, dispatched and confirmed. Historical PO17 was retained.

Actual UI arrival inputs were explicitly synthetic: LOT-A 2 cartons/20 Nos,
then LOT-B 2 cartons/18 Nos. Native submitted receipts are
`MAT-PRE-2026-00013` and `MAT-PRE-2026-00014`. Readback confirms ordered40,
received38, held38, usable0, missing2 and cartons4. These are demo transactions,
not independent physical observations.

Both events updated the same Airtable record `recqUX26BS0RpwGG2` in Distributor
Cases `tblme05Ij7n4t4bSf`, and Jira `QRC-3`. Celigo/Slack retained verified
messages `1789074429.802219` and `1789075071.552039`. Local UI displayed all
three providers VERIFIED after each event. The second event displays a verified
Jira browse link. Pending intermediate readback was retained; it was not counted
as a failed final handoff.

A Jira link omission was corrected after the first arrival. The demo service was
normally restarted with its original runtime, then the second arrival continued;
no event replay or database repair was performed. This is a repaired continuation,
not an uninterrupted frozen-source pass. Previous journal proofs were not changed.

Independent Terra review accepted the server integration, UI and provisioning;
the final Jira-origin/key link delta received a separate scoped GO. Primary
verification passed 26 focused Python tests and 22 JavaScript tests. Earlier
integration checks and their concrete corrections remain in the session evidence.
The configured private package audit also passes, but its historical readiness
label must not be interpreted as completion of this new business scenario.

Private raw snapshots are retained under
`/private/tmp/m20-final-20260910-after-arrival-*`; runtime credentials and database
are excluded from this release. GET and chat expose retained evidence only;
external writes occur on authorized event/reconciliation paths.
