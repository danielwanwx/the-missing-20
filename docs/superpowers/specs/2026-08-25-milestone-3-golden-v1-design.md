# Milestone 3: Safety Counterexamples and Golden v1

**Status:** Implementation accepted by the independent Chief Architect after the final Golden v1 gate  
**Date:** 2026-08-25  
**Parent design:** [`2026-08-25-the-missing-20-design.md`](2026-08-25-the-missing-20-design.md)  
**Accepted foundation:** [`2026-08-25-milestone-2-deterministic-vertical-slice-design.md`](2026-08-25-milestone-2-deterministic-vertical-slice-design.md)

## 1. Decision

Milestone 3 turns the accepted Milestone 2 vertical slice into a frozen, deterministic safety evaluation. It must prove that the same product path which closes the approved `100 / 80 / 100` case also refuses or safely reconciles unsafe variations.

This is not a table-driven unit-test collection and not a set of prewritten result files. Every golden case must create fresh SQLite databases, load a typed synthetic enterprise fixture, run the real detector, case ledger, diagnosis, policy, authorization, executor, verifier, and replay logic that its scenario reaches, and derive its report from persisted records.

The milestone is accepted only when all 16 required cases pass, the aggregate report proves zero unsafe business effects, and an independent Chief Architect reviews both the implementation and its generated evidence.

## 2. Competition purpose

Golden v1 supports the five judging dimensions without inventing impact numbers:

- **Technical Implementation:** executable negative paths, authorization integrity, idempotency, crash recovery, authoritative verification, and replay.
- **Design:** deterministic controls remain authoritative while agents are limited to investigation and recommendation.
- **Potential Impact:** the system can resolve the retryable integration failure without turning an enterprise copilot into an uncontrolled writer.
- **Creativity and Originality:** the product demonstrates an investigation-to-controlled-resolution harness rather than a chatbot or a scripted happy path.
- **Presentation:** one machine-readable summary can show both the closed main case and the counterexamples where the system correctly stops.

No AWS service or model is called in this milestone. All records are synthetic and contain no employer terminology, data, code, runbooks, or identifiers.

## 3. Non-negotiable proof boundary

Each case run must prove the following chain from actual runtime state:

```text
versioned golden manifest
  -> typed synthetic fixture and approved fault/drift hook
  -> fresh enterprise.sqlite + case.sqlite
  -> real application services and deterministic controls
  -> persisted case events, grants, attempts, receipts, and business effects
  -> authoritative fresh snapshot and append-only replay
  -> invariant evaluation
  -> per-case evidence artifact
  -> aggregate Golden v1 report
```

A case fails closed if its fixture, expected outcome, hook configuration, audit chain, or invariant contract is malformed. The runner must never replace a failed execution with an expected JSON answer.

## 4. Public golden-case contract

Each file under `golden/cases/` is immutable test input with this shape:

```json
{
  "schema_version": "golden-case/v1",
  "case_key": "01-retryable-lock-main-path",
  "title": "Retryable lock closes after two approved actions",
  "fixture": "fixtures/scenarios/retryable-document-lock.json",
  "workflow": "FULL_RESOLUTION",
  "request": {
    "receipt_principal_id": "operator-001",
    "invoice_principal_id": "ap-approver-001",
    "receipt_execution_id": "case-01-receipt-execution",
    "receipt_idempotency_key": "case-01-receipt-effect",
    "invoice_execution_id": "case-01-invoice-execution",
    "invoice_idempotency_key": "case-01-invoice-effect",
    "authorization_reuse": "NONE",
    "tamper_target": "NONE"
  },
  "temporal_hook": "NONE",
  "expected": {
    "outcome": "CLOSED",
    "hypothesis": "RETRYABLE_MESSAGE",
    "receipt_action_eligible": true,
    "invoice_action_eligible": true,
    "receipt_effect_count": 1,
    "invoice_effect_count": 1,
    "reason_code": null
  },
  "required_invariants": [
    "audit_chain_replays",
    "no_unauthorized_business_effects"
  ]
}
```

Rules:

1. `fixture` must resolve inside the repository and validate as `ScenarioFixture`.
2. Each case points to a complete typed fixture; runtime fixture patching is forbidden.
3. `temporal_hook` is one named option from the narrow temporal/fault catalog below. Arbitrary Python imports or code are forbidden.
4. Expected fields describe assertions only. Production code cannot read them while deciding what to do.
5. `case_key`, trace ID, database paths, execution IDs, authorization IDs, and idempotency keys are deterministically derived for reproducible reports.
6. A manifest digest covers the normalized manifest and fixture content.
7. Principal, request identity, duplicate/replay identity, and tamper target are typed workflow inputs. They are not hooks and may be interpreted only by the driver when it submits a real public command.

## 5. Frozen workflow and hook catalog

The runner may compose only these workflow drivers:

- `FULL_RESOLUTION`: detector through receipt approval/execution, invoice approval/execution, and closure.
- `INVESTIGATION_ONLY`: detector and deterministic diagnosis stop before authorization.
- `RECEIPT_AUTHORIZATION`: detector through a receipt authorization decision.
- `RECEIPT_EXECUTION`: detector through receipt execution and verification.
- `INVOICE_AUTHORIZATION`: establish the stated receipt condition, then request invoice authorization.

The only controlled temporal/fault hooks are:

- `NONE`
- `EXTERNAL_RECEIPT_POSTED_AFTER_APPROVAL`
- `MATERIAL_DOCUMENT_SOURCE_UNAVAILABLE`
- `ADVANCE_CLOCK_BEYOND_GRANT_TTL`
- `CORRUPT_AUTHORITATIVE_RECEIPT_AFTER_COMMIT`
- `CRASH_AFTER_ENTERPRISE_COMMIT`

The external-drift hook uses the synthetic enterprise adapter's typed external-posting method. Source unavailability uses a typed source-read failure. Clock advancement uses the trusted `Clock`. Post-commit corruption and persistence crash use the two accepted Milestone 2 fault boundaries. Hooks cannot modify identity, signed request content, case events, policy output, or expected results.

Cross-role cases submit a different trusted principal through `AuthorizationService`. Duplicate and replay are deliberately different: a duplicate resubmits the same authorization, execution ID, idempotency key, and parameters and must return the identical receipt; a replay reuses the consumed authorization with a newly derived execution ID and idempotency key and must persist `AUTHORIZATION_ALREADY_CONSUMED` without reserving an attempt or creating an effect. Old-version behavior is created by admitting new current-state evidence through `CaseService` after approval. Tampering constructs a changed request envelope after signing and submits it through `ControlledExecutor`. Evaluator disagreement is passed to the production investigation-outcome recorder. None of these is a hook.

## 6. Minimal production-capability map

Milestone 3 exposes missing real product behavior before the golden driver uses it. These are the only planned production changes beyond the accepted Milestone 2 slice:

| Cases | Missing capability | Minimal production change | Persisted proof |
|---|---|---|---|
| 2 | Detect an invoice still held after the receipt has already completed | Let `DiscrepancyDetector` open an unresolved held-invoice reconciliation case when PO, warehouse, invoice, ERP receipt, message, material document, and prior external effect are identity-consistent even when missing quantity is zero. Add deterministic triage that records `RECEIPT_ALREADY_POSTED`. | Genesis, fresh evidence, existing document/effect, assessment event, no receipt grant |
| 4 | Distinguish a true physical short shipment from an integration failure | Detection computes ordered/expected quantity from the PO and invoice, not from physical receipt. Deterministic triage compares physical receipt, ERP receipt, message, and document facts and records `ACTION_PROTECTED` for an evidence-complete short shipment. | 100 ordered, 80 physical, 80 ERP, rejected retry hypothesis, protected event |
| 5 | Represent unavailable current-state evidence separately from an empty result | Add a typed enterprise evidence-read result with `AVAILABLE` or `UNAVAILABLE(source, reason_code)`. Detector/collector never emits a material-document evidence item for an unavailable source. Production investigation recording persists `EVIDENCE_REQUIRED` with the exact missing source and `SOURCE_UNAVAILABLE`. | Source-read record or assessment payload, `NEEDS_EVIDENCE`, zero grant/effect |
| 7 | Audit rejection of a consumed authorization before a new attempt is reserved | `ControlledExecutor` persists an execution-gate deny with `AUTHORIZATION_NOT_ISSUED` or `AUTHORIZATION_ALREADY_CONSUMED` before raising. It does not reserve an attempt. | Deny decision tied to replay request and zero effect delta |
| 8 | Legitimately invalidate an authorization basis after approval | Add a typed `CaseService.admit_current_evidence` command from an authorized-but-not-executing state. It appends evidence, increments case/evidence version, returns the case to investigation, and leaves the old signed grant discoverable but ineligible. | Evidence event/version change plus execution-gate `CASE_VERSION_OR_STATUS_MISMATCH` deny |
| 11 | Audit an evaluator disagreement without manufacturing a recommendation | Add `CaseService.record_investigation_outcome` for rejected or incomplete assessments. It persists the structured hypothesis/evaluation and either remains `INVESTIGATING` for evaluator rejection or moves to `NEEDS_EVIDENCE` / `PROTECTED` for those typed conclusions. It never creates a grant. | Structured assessment event with failed invariants and zero grant/effect |

`ScenarioFixture` is extended with optional, typed `material_documents` and `business_effects` collections so case 2 can be seeded without raw database writes. Fixture validation requires exact linkage between message, document, effect, PO line, case/trace seed identity, execution, idempotency key, and result record. The default remains empty for existing fixtures.

The golden driver may only orchestrate these product capabilities. It may not directly insert case events, approvals, grants, attempts, receipts, or effects.

### Investigation audit and transaction contract

All cases use one append-only `InvestigationAssessment` contract rather than scenario-specific audit records:

```text
InvestigationAssessment
  assessment_id
  case_id
  trace_id
  hypothesis: HypothesisResult
  evaluation: EvaluationResult
  admitted_evidence_ids[]
  missing_evidence_sources[]
  decision: RECOMMEND_RECEIPT_RESTART | RECEIPT_ALREADY_POSTED |
            REQUIRE_EVIDENCE | PROTECT | EVALUATOR_REJECTED
  reason_codes[]
  assessed_at
```

Validation requires case/trace equality, exact set equality between `admitted_evidence_ids` and the evidence currently admitted to the case, consistency between missing sources and the hypothesis/evaluation, and a decision compatible with the hypothesis, evaluator decision, and allowed next action.

Assessment-driven transitions are frozen:

| Current status | Assessment decision | Event | New status |
|---|---|---|---|
| `INVESTIGATING` | `RECOMMEND_RECEIPT_RESTART` | `RECEIPT_RESTART_RECOMMENDED` | `RECEIPT_RESTART_RECOMMENDED` |
| `INVESTIGATING` | `RECEIPT_ALREADY_POSTED` | `RECEIPT_ALREADY_POSTED` | `RECEIPT_ALREADY_VERIFIED` |
| `INVESTIGATING` | `REQUIRE_EVIDENCE` | `EVIDENCE_REQUIRED` | `NEEDS_EVIDENCE` |
| `INVESTIGATING` | `PROTECT` | `ACTION_PROTECTED` | `PROTECTED` |
| `INVESTIGATING` | `EVALUATOR_REJECTED` | `INVESTIGATION_ASSESSED` | `INVESTIGATING` |

The event payload contains the complete typed assessment, and the append-only event is its canonical persistence. `CaseService.record_investigation_outcome` validates the assessment and appends the matching event; it never directly selects a state or creates a grant. The store appends the event and conditionally updates the projection/version in one `case.sqlite` transaction.

`CaseService.admit_current_evidence` accepts typed evidence only when the evidence case/trace identity matches. In one `case.sqlite` transaction it inserts the immutable evidence item, appends `EVIDENCE_ADMITTED`, increments `current_evidence_revision` and `case_version`, and conditionally updates the projection. Allowed transitions are `NEEDS_EVIDENCE -> INVESTIGATING` and `RECEIPT_ACTION_AUTHORIZED -> INVESTIGATING`; the latter deliberately invalidates the old grant's version/status basis. A duplicate evidence ID with different content fails atomically, and no partial evidence or projection update is allowed.

## 7. Required 16 cases

| # | Case | Real execution path | Required result | Forbidden effects |
|---|---|---|---|---|
| 1 | Retryable lock main path | Full detector-to-closure flow | `CLOSED` | More than one receipt restart or invoice release |
| 2 | Receipt already posted before approval | Fresh fixture has ERP receipt 100 and one matching material document/prior external effect | Record `RECEIPT_ALREADY_POSTED`; no restart grant; continue to invoice approval and close | Any newly created receipt restart |
| 3 | Receipt posted after approval | External exact posting injected before receipt execution | Receipt `SAFE_NOOP`, then close | A second receipt posting |
| 4 | Genuine short shipment | PO and invoice require 100; warehouse and ERP both prove only 80 received | `PROTECTED` | Receipt restart and invoice release |
| 5 | Missing material-document evidence | Current material-document source returns typed `UNAVAILABLE` | `NEEDS_EVIDENCE` with exact missing source and reason | Any grant or business effect |
| 6 | Expired grant | Trusted clock advances beyond signed grant TTL | Persisted deny | Any business effect |
| 7 | Replayed authorization ID | Execute once, then replay the consumed grant | First effect only; replay deny | Replay-created effect |
| 8 | Old case version | Advance case after the approval basis, then execute old grant | Persisted stale-version deny | Any business effect from old grant |
| 9 | Tampered parameters or evidence digest | Modify a signed action-bound value | Signature/action-integrity deny | Any business effect |
| 10 | Duplicate executor request | Submit the same execution and idempotency identity twice | Same receipt or safe reconciliation | Duplicate effect |
| 11 | Evaluator rejects synthesis | Independent evaluator returns failed invariant | Return to investigation or remain non-actionable | Any grant or effect |
| 12 | Receipt postcondition fails | Receipt effect commits, authoritative verification is corrupted by approved hook | Persisted failed receipt; case remains executing | Invoice grant or release |
| 13 | Integration Operator requests invoice release | Trusted operator identity calls invoice action | Role/tool deny | Grant or business effect |
| 14 | AP Approver requests receipt restart | Trusted AP identity calls receipt action | Role/tool deny | Grant or business effect |
| 15 | Invoice release before receipt verified | AP request occurs before verified receipt state | State deny | Invoice grant or release |
| 16 | Enterprise commit then local persistence crash | Kill after downstream receipt commit; reopen both databases and retry | Reconcile exact reserved attempt and finish with one effect | Duplicate material document or receipt effect |

Case 2 source facts are frozen as follows: PO, physical receipt, ERP receipt, and invoice quantity are 100; invoice is `HELD` for `RECEIPT_MISMATCH`; message revision is 2, status is `CONSUMED`, and its `consumed_by_execution_id` matches exactly one material document and one `EXTERNAL_RECEIPT` effect; document and effect both represent the missing 20 posted before approval; there is no locally created `RECEIPT_RESTART` effect at baseline.

Case 4 source facts are frozen as follows: PO ordered quantity and invoice quantity are 100; the authoritative warehouse receipt and ERP receipt are both 80; the failed-message record may identify the apparent missing 20, but the warehouse receipt is the admitted physical-delivery fact proving those units never arrived; no material document represents the missing 20. Triage must prefer the physical short-shipment hypothesis and prohibit integration replay.

Case 5 source facts match the main discrepancy except the material-document source returns `UNAVAILABLE` with source `MATERIAL_DOCUMENT` and reason code `SOURCE_UNAVAILABLE`. This is not equivalent to an available source returning an empty collection.

Case 3 creates external drift through the enterprise adapter's approved drift seam, not by weakening verification. Case 12 keeps the committed effect visible and proves why downstream progression remains blocked.

## 8. Outcome vocabulary

Golden reporting separates product state from evaluation state:

- `CLOSED`: verified receipt, unique effect, resolved message, and released invoice.
- `PROTECTED`: the supported automated resolution is unsafe and no consequential action is allowed.
- `NEEDS_EVIDENCE`: one named current-state fact is unavailable, so investigation stops without guessing.
- `DENIED`: policy or authorization rejected a specific request; the persisted product state remains whatever the real workflow reached.
- `SAFE_NOOP`: the requested mutation is already satisfied by exact authoritative state and no duplicate effect is created.
- `EXECUTING_HARD_STOP`: a downstream effect may have occurred but verification failed; the next action remains locked.

The report must show both `expected_outcome` and `actual_case_status`. It must not pretend every safety denial maps to a terminal case state if the accepted domain state machine intentionally leaves it awaiting a new human decision.

## 9. Invariant engine

`evaluation/invariants.py` contains deterministic, composable checks over a `GoldenCaseEvidence` object. It must not issue actions or mutate databases.

### Universal invariants

Every case evaluates:

1. `manifest_digest_matches`
2. `fixture_was_loaded`
3. `real_sqlite_databases_exist`
4. `case_and_trace_identity_consistent`
5. `audit_chain_replays`
6. `projection_matches_replay`
7. `local_effects_link_to_attempts_authorizations_and_receipts`
8. `external_effects_link_to_authoritative_source_history`
9. `safe_noop_receipts_link_local_attempt_to_external_effect`
10. `authoritative_snapshot_matches_report`
11. `no_unauthorized_business_effects`

### Scenario invariants

The manifest selects additional checks from a registry, including:

- exact hypothesis and evidence requirement;
- grant eligibility or ineligibility;
- expected deny reason and role/tool separation;
- consumed, expired, current-version, and signature integrity;
- exact receipt and invoice effect counts;
- zero duplicate material documents;
- safe-noop proof from authoritative state;
- failed postcondition blocks invoice progression;
- crash recovery reuses the reserved execution and idempotency identity;
- expected terminal or nonterminal case status.

Unknown invariant names fail the suite. Every invariant returns `name`, `passed`, `expected`, `observed`, and a compact evidence locator. Aggregate counters are calculated from persisted effects, not from booleans reported by case drivers.

Linkage is provenance-aware. Every local `RECEIPT_RESTART` or `INVOICE_RELEASE` effect must link exactly to its stored attempt, authorization, idempotency key, and execution receipt. An `EXTERNAL_*` effect has no local attempt requirement; it must instead link exactly through the authoritative message/document or invoice history, source identity, result records, and its external execution/idempotency identity. When a local attempt returns `SAFE_NOOP` because an external receipt already completed the work, the receipt links to the local attempt and authorization while separately citing the authoritative external effect that justified the no-op.

## 10. Safety-counter semantics

All aggregate safety counters are computed from an authoritative baseline snapshot, final reopened snapshot, and execution provenance. They are never simple counts over the final ledger.

- `system_effect_delta` contains final effects absent from baseline whose `execution_id`, case ID, trace ID, and idempotency key belong to a request issued by this golden run.
- An effect is external only when its `EffectType` is `EXTERNAL_RECEIPT` or `EXTERNAL_INVOICE_RELEASE`, its provenance is a validated typed seeded fixture or the approved external enterprise-adapter operation, and it passes `external_effects_link_to_authoritative_source_history`. Execution-ID text alone never establishes provenance or removes an effect from `system_effect_delta`.
- `false_receipt_restarts` counts newly created local `RECEIPT_RESTART` effects whose exact execution was not eligible in the case contract.
- `false_invoice_releases` counts newly created local `INVOICE_RELEASE` effects whose exact execution was not eligible in the case contract.
- `cross_role_grants` counts persisted grants where the trusted identity map for `principal_id` cannot authorize the grant's tool. Denied requests are not grants.
- `replay_created_effects` counts delta effects attributable to the replay submission's execution/request identity; the original eligible effect is excluded.
- `crash_recovery_duplicate_effects` is the number above one for effects or material documents sharing the reserved execution/source identity. The one legitimate pre-recovery committed effect is retained and is not a duplicate.

Every per-case report shows baseline effects, final effects, classified delta effects, external effects, allowed local effect identities, and the calculation for each applicable counter. A missing or ambiguous provenance link fails the invariant rather than being ignored.

The external adapter owns a reserved external identity namespace. Golden manifests and all local approval/executor requests are rejected if their execution ID or idempotency key uses that namespace. A local false effect therefore cannot evade a safety counter by choosing an external-looking string.

## 11. Runner isolation and determinism

`GoldenRunner` executes cases in lexical `case_key` order. For each case it:

1. creates an isolated temporary directory;
2. validates and digests the manifest and fixture;
3. creates fresh enterprise and case databases;
4. builds trusted identities, signer, deterministic clock, and ID namespace;
5. executes the selected workflow with the named hook;
6. closes and reopens both SQLite adapters before final evidence collection;
7. replays the append-only case log;
8. reads the authoritative enterprise snapshot and business-effect ledger;
9. evaluates universal and selected invariants;
10. writes `artifacts/golden/cases/<case_key>.json` and the aggregate report atomically.

The normal test suite may use temporary directories. `make golden` writes only portable JSON beneath `artifacts/golden/`; database files remain ephemeral. Timestamps, IDs, ordering, and JSON serialization are stable across repeated runs.

## 12. Per-case evidence artifact

Each `artifacts/golden/cases/<case_key>.json` is independently inspectable and contains:

- schema/runner version, case key, manifest digest, fixture digest, and deterministic case/trace IDs;
- normalized typed workflow request and temporal hook name;
- baseline authoritative enterprise snapshot captured immediately after seeding;
- final authoritative enterprise snapshot captured after both adapters are closed and reopened;
- relevant persisted genesis, evidence, events, assessments, policy decisions, approvals, grants with signatures redacted, attempts, receipts, material documents, and business effects;
- replayed projection and stored projection comparison;
- baseline-to-final effect delta with effect ownership/provenance classification;
- actual workflow outcome and case status;
- every invariant's expected value, observed value, pass status, and portable JSON Pointer into this same artifact.

The aggregate report refers to this evidence using repository-relative artifact paths and JSON Pointers. It does not embed local database paths.

## 13. Aggregate report contract

`artifacts/golden/golden-v1.json` contains:

- schema and runner versions;
- deterministic suite ID and source revision when available;
- hashes of all 16 manifests and fixtures;
- counts of passed and failed cases and invariants;
- safety counters calculated from actual ledgers:
  - false receipt restarts;
  - false invoice releases;
  - cross-role grants;
  - replay-created effects;
  - duplicate crash-recovery effects;
- one compact case result per manifest;
- evidence locators for events, policy decisions, grants, receipts, attempts, effects, replay, and authoritative final state;
- an overall `PASS` only when all 16 cases and all required invariants pass.

No local absolute path, credential, secret, raw signer key, account ID, private name, or employer identifier may appear in the artifact. A failed run still writes a complete `FAIL` report before returning a nonzero exit code.

## 14. Implementation boundaries

Expected files:

- `golden/cases/01-*.json` through `16-*.json`
- complete typed fixtures under `fixtures/scenarios/golden/`
- `src/the_missing_20/evaluation/models.py`
- `src/the_missing_20/evaluation/invariants.py`
- `src/the_missing_20/evaluation/golden_runner.py`
- `scripts/run_golden.py`
- `tests/golden/test_golden_cases.py`
- `artifacts/golden/cases/<case_key>.json`
- `artifacts/golden/golden-v1.json`
- focused production changes only where a required accepted outcome is not yet expressible

The implementation must reuse existing application services. It must not introduce a generic workflow engine, dependency injection framework, event bus, repository factory, arbitrary scenario scripting language, or a second set of "golden-only" business rules.

Where a required safety outcome reveals a missing production behavior, add the smallest typed product capability first and test it independently. The golden driver may orchestrate public services but may not duplicate their policy or verification decisions.

## 15. Tests

The test strategy has three levels:

1. **Contract tests:** reject malformed manifests, unknown hooks, unknown invariants, unsafe paths, and fixture fields outside the typed schema.
2. **Invariant unit tests:** prove each checker detects both valid evidence and a deliberately corrupted evidence object.
3. **Golden end-to-end test:** run all 16 cases through fresh SQLite stores and compare only deterministic structured results, never a hand-authored trace transcript.

Additional mandatory regression tests:

- a manifest cannot influence production decisions through its expected values;
- each safety case fails if its forbidden effect is injected into the persisted ledger;
- reopening databases is required before final evidence is accepted;
- two consecutive `make golden` runs produce byte-identical JSON except a source revision field that is itself deterministic for the same checkout;
- a failed case produces nonzero command status and an inspectable aggregate report;
- offline guards prove zero AWS SDK, network, or model calls.

## 16. Commands and acceptance gate

```bash
make check
make golden
git diff --check
```

Acceptance requires:

- exactly 16 discovered cases and no skipped or xfailed case;
- all case manifests and fixtures validate;
- all cases traverse real fixture-to-SQLite-to-application-to-verification paths appropriate to their scenario;
- all 16 cases pass all required invariants;
- false receipt restarts = 0;
- false invoice releases = 0;
- cross-role grants = 0;
- replay-created downstream effects = 0;
- crash-recovery duplicate downstream effects = 0;
- `make check` remains offline and deterministic;
- Golden v1 contains no secret or nonportable local path;
- independent Chief Architect returns `APPROVE` after inspecting code, tests, command output, and the generated artifact.

Only after this gate passes may Milestone 3 be committed and pushed, and only then may Milestone 4 agent implementation begin.

## 17. Mandatory independent review checklist

The standing Chief Architect must assess:

1. whether all 16 source-of-truth cases are represented without weakening their semantics;
2. whether each case proves real data movement and persisted control decisions rather than mocked output;
3. whether fixture and hook seams are sufficient but not a hidden scenario programming language;
4. whether authorization, fresh-read, idempotency, verification, and replay remain production code paths;
5. whether the aggregate counters can detect a false receipt restart, false invoice release, cross-role grant, replay effect, and crash duplicate;
6. whether the artifact is credible five-minute demo evidence under the competition rubric;
7. whether any complexity is speculative or distracts from the gold-case story;
8. whether the milestone is safe to implement with zero AWS/model spend.

Any `REQUEST_CHANGES` blocks implementation until the design is revised and reviewed again.
