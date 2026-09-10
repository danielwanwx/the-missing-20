# Contract allocation source readback correction

The fresh PO18 case exposed a real integration failure after LOT-A's whole-lot
inspection. Nova Pro selected A20/B0 under the approved promise-date policy;
Stock Entry7, Quality Inspection6 and Pick List8 were successfully recorded.
The following GET nevertheless became unavailable. Its raw failure is retained
at `/private/tmp/m20-final-20260910-after-inspection-a-01.json`.

Read-only diagnosis found native documents valid. The ERP snapshot still used
the legacy numeric-priority loop, deriving B15/A5, while retained operations
correctly used date-first A20/B0. The unchanged merge consistency check rejected
the conflict. This was a source-policy integration defect, not a model error.

Contract-v1 snapshots now reuse the existing deterministic allocation compiler
with verified current lots and native dispatched amounts. Legacy mode retains
its prior priority loop. No model invocation, native write, event replay,
database repair or weakened merge check is part of this correction.

Primary and independent review passed 49 ERP/operations tests, including A20/B0,
A25/B13, A25/B15 and final40 dispatch conservation. Ruff format/check and the
changed source's mypy passed. Independent Terra review returned scoped GO.

After a normal restart with the same runtime, a fresh primary HTTP readback
returned available=true: received38, usable20, held18, missing2, A20/B0 allocated,
zero dispatched. Native inspection/release/pick preparation was not repeated.
Evidence: `/private/tmp/m20-final-20260910-after-contract-readback-fix.json`.
This repairs a continuation; full delivery and financial/dialogue acceptance
remain separate unfinished checks.
