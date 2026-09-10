# Contract allocation slice — September 10

Status: scoped GO for implementation, synthetic inputs with a real model, and UI
rendering. This is not acceptance of the new 40-part native ERP business chain.

The opt-in v1 policy compiles date-first allocations, using customer priority as
a tie-breaker and explicit partial/minimum/final-remainder terms. A real Strands
selector chooses the exact supplied plan or defers. Quantities and lot capacity
remain application-calculated. The decision is checkpointed before native
preparation; reads and chat do not trigger this selector. Legacy cases retain
their previous configuration behavior.

Independent Terra review initially rejected incomplete/duplicate contract
references and insufficient exact native-lot binding. Both were repaired and
regression-tested. Re-review returned code GO and then scoped evidence GO.
Supported native tranches remain configured; arbitrary ERP allocation is not
claimed.

## Evidence

- Primary: 98 Python tests passed across distributor operations/allocation/ERP
  and the M7 package; 118 JavaScript tests passed. Final UI-only wording polish
  passed its 17 focused JavaScript tests.
- Six changed Python files pass Ruff and formatting. Three implementation
  modules pass mypy; the repository's 51-file strict type gate passes.
  An additional server-wide mypy check reports five existing errors, reproduced
  against baseline 93cd887. They are outside the configured strict gate and not
  introduced by this slice.
- Real Nova Pro attempt 02 used the exact final source hashes and included the
  native tranche SYN-A-25 / 20 / SYN-LOT-A. The model selected the exact plan and
  both references, explaining the earlier promised date despite lower customer
  priority. One request: 1,016 input / 248 output tokens, 2,809 ms, estimated
  incremental USD 0.0016064. ERP and SaaS calls: zero.
- Attempt 01 is retained separately: 978 input / 286 output tokens, 3,081 ms,
  estimated USD 0.0016976. Combined estimate USD 0.003304 is not an AWS invoice.
  The SDK output limit is not a strict per-response cap, as attempt 01 shows.
- Private raw inputs/results are retained under
  `/private/tmp/m20-contract-allocation-20260910`; they are not public artifacts.
- Primary browser verification used a clearly labelled fake-service fixture,
  "UI verification fixture — no external writes", on localhost:8902. Terms,
  rationale and selection render, with explicit separation from execution.
  Final text reads "Contract policy v1 · Planned additional quantity 15 Box".
  This Box fixture is a renderer check, not the new 40-part business demo.

## Still open

Fresh same-case native ERP preparation and downstream fulfillment, operational
alert closure, actual Airtable/Jira/Slack records, complex multi-turn semantic
acceptance and final submission materials remain separate work. No stronger
Bedrock model has been promoted by this change.
