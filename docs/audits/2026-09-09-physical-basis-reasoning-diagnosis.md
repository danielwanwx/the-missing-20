# Physical-basis reasoning diagnosis: D4 question 4

**Status: semantic failure retained; no retry authorized.**

This is a read-only causal and next-experiment diagnosis of the one completed
D4 turn in `/private/tmp/m20-s2-d4-live-q4.json`, inspected at execution
revision `4706a9245f33b715442444b8520290b4f40f2c27`. It complements, rather
than repeats, the independent semantic ruling in
`docs/audits/2026-09-09-d4-live-screen-review.md`. It makes no product change,
model call, ERP/SaaS call, or business write. D4 stopped after question 4;
questions 5 and 6 were not run.

The failed question was:

> Does the receiving basis independently prove what was physically inside the cartons?

The returned `SAFE_NOOP` reason says that it *does* independently prove the
contents, that ERP and collaboration evidence confirm it, and that there are
no missing facts. That conclusion is unsupported. The source establishes
posted receipt and ledger facts; it does not establish an independent
observation of carton contents.

## Evidence inspected

| Item | Evidence |
| --- | --- |
| Run record | `/private/tmp/m20-s2-d4-live-q4.json`, SHA-256 `146b211f876b12d5e85710fccd636f647111b70e44d636141d26b1fd375412d7` |
| Frozen ERP source | `/private/tmp/m20-s2-d4-screen-v2/erp-v1.json`, SHA-256 `f9562ff5d61c1840b55a36b284b57677e78dd1e3abd89041182da89948eb65e5` |
| Frozen SaaS source | `/private/tmp/m20-s2-d4-screen-v2/saas.json`, SHA-256 `66d911222c58c57bee87be5abf9e700be7f704a6a677e81110c46eee085732fa` |
| Transition manifest | `/private/tmp/m20-s2-d4-screen-v2/manifest.json`, SHA-256 `fb099e41552ccef42376ed3b9d5a0455b2456d1ddfe0afed8ca8e1a74a1128ac` |
| Current source/agent seams | `operational_metrics.py`, `receiving_facts.py`, `receiving_advisory.py`, `live_advisory.py`, and `live_advisory_gateway.py` |

The frozen ERP record has two submitted purchase receipts, each for 1 Box,
and two linked stock-ledger rows. `MAT-PRE-2026-00006` is linked to
`MAT-SLE-2026-00026`; `MAT-PRE-2026-00005` is linked to
`MAT-SLE-2026-00025`. Those are evidence of ERP receipt posting and stock
ledger posting. The `delivery_note` strings contain `M20 PHOTO …` identifiers,
but the fixture contains no `physical_evidence` object, no image/scan result,
no operator count, and no record that maps an observation to carton contents.

The frozen SaaS data has an empty Airtable result, a pending Celigo result, a
Jira review label, and a Slack notification that repeats the ERP receipt. It
does not add a physical observation. The produced packet also has
`receiving_work.arrivals: []`.

At the metrics boundary, the absence of a verified `physical_evidence` value
causes `live_flow_metrics` to set `arrived = received` and label that value
`RECEIPT_CONFIRMED` (`src/the_missing_20/adapters/operational_metrics.py:260-318`).
That is a receipt-confirmed lower bound, deliberately not an independent
physical observation.

## What reached the model

The independent review establishes the execution revision, source hashes,
source reads, and semantic failure. The diagnostic retains tool names and
timings, but not raw model wire payloads. Therefore the exact transport bytes
cannot be proved from the artifact alone. The following is a deterministic
reconstruction from its persisted projection and the inspected production flow;
it is stronger than guessing from the final prose, but it is not a substitute
for future raw, redacted tool-transcript retention.

The artifact records all five required source reads exactly once, with zero
source-cache hits:

```text
read_control_context
read_erp_evidence
read_collaboration_evidence
read_airtable_evidence
read_celigo_evidence
```

It records four model requests, no validation retry, and a `COMPLETE` result.
Thus the failure is not explained by skipped source tools or a fallback answer.

### Contextual user prompt

`DashboardAdvisoryGateway` retained only the three prior **human** requests,
then supplied the newest question. It did not inject prior assistant prose.
The reconstructed 1,397-character context tells the model to answer only the
newest question and includes the durable read-only refusal. Its prior requests
were the receipt/ledger question, the refusal, and the ordered/outstanding
quantity question. The newest question was exactly the physical-basis question
above.

For the acquisition phase, the full contextual prompt is passed to the agent.
For the typed conclusion phase, `live_advisory._invoke` strips that wrapper and
passes the newest question alone. Neither form contains an earlier assistant
claim that could have become evidence.

### Reconstructed source-tool facts

`model_source_payloads` applies `model_receiving_source` before returning
`read_erp_evidence` to the model (`src/the_missing_20/agents/live_advisory.py:1192-1254`,
`src/the_missing_20/agents/receiving_facts.py:49-58`). For this turn it removes
the ambiguous `physically_arrived` field from the model-facing quantity map and
supplies these facts instead:

```json
{
  "physical_observation_basis": "RECEIPT_CONFIRMED",
  "quantities": {
    "independently_observed_quantity": null,
    "receipt_confirmed_lower_bound": 2.0,
    "receipt_posted_quantity": 2.0,
    "accepted_cumulative": 2.0,
    "ordered": 40.0,
    "outstanding_order_quantity": 38.0
  }
}
```

It also supplies the current receipt-to-ledger relations, including
`MAT-PRE-2026-00006 → MAT-SLE-2026-00026`. The collaboration tool has no
photo/scan records or arrivals. It exposes Slack and Jira only as journal
records with the limitation:

```text
Notification copies are not stock, QA, billing or delivery authority.
```

The control tool says the scope is read-only and forbids inventing quality or
invoice authority. The receiving system prompt separately says to distinguish
physical observations from receipt/ledger records and calls Slack, Airtable,
and Celigo notification copies. The typed-conclusion prompt says that photo
observations and notification copies do not independently prove posted stock.

Those facts are sufficient to support this bounded conclusion:

* the receipts and ledger prove a posted 2 Box receipt position;
* no independent observation of carton contents is available in this source
  scope; and
* the absence is not permission to infer a shortage, a quality defect, or a
  write.

They do **not** support the model's statement that the contents are
independently proved, its use of Slack/Jira as confirming evidence, or its
claim that no relevant information is missing.

## Plausible failure location, not a proved cause

The primary quantity transformation is working. The model did not receive the
generic `physically_arrived: 2.0` field that can look like an independent
count. It received `independently_observed_quantity: null`,
`receipt_confirmed_lower_bound: 2.0`, and `RECEIPT_CONFIRMED`.

One candidate explanation is an incomplete **claim-boundary contract** that
leaves too much semantic work to free-form synthesis:

1. The semantic negative is distributed across a nullable quantity, an enum
   name, generic prompt prose, and an empty arrival list. No source fact
   expressly says that independent carton-content evidence is absent from a
   complete current scope.
2. `M20 PHOTO …` appears as an opaque ERP `delivery_note` identifier. Without a
   typed observation record, it is not evidence of contents, but it is an easy
   lexical invitation for a model to overread the source.
3. The prompt says that ERP/ledger records “prove stock” and asks the model to
   distinguish physical observations. It does not bind `RECEIPT_CONFIRMED` to
   the concrete conclusion “receipt posting only; not independent carton
   contents.” The final prompt's notification warning is about independently
   proving *posted stock*, which is narrower than the question asked.
4. Validation covers required tool calls, citations, disposition, read-only
   behavior, selected numeric/identifier omissions, and a narrow named-system
   warning. It has no typed physical-evidence claim check. This answer did not
   name “Slack” or “Airtable” literally, so the named-system warning did not
   fire even though it called “collaboration evidence” confirming evidence.
   `receiving_answer_gaps` has no semantic rule for an unsupported independent
   physical-contents assertion.

This is not evidence that a source field was silently dropped. It establishes
an unsupported synthesis despite a qualified source view. It does not prove
that the candidate contract gap, the model, the prompt, or framework
serialization is the unique cause. The runtime's `SAFE_NOOP` disposition
remains compatible with an answer that says physical contents are not
independently established; the question's uncertainty must not be mistaken for
an operational exception or a requested write.

## Unapproved candidate safeguard

One possible future safeguard is a source-derived, domain-level
evidence-capability object in the receiving packet. It would describe what the
current scoped source can prove, rather than dictate a response to a question
or case. This is a design option for a separate gate, not an approved
implementation recommendation or a demonstrated model-reasoning repair.

For example, a generic `claim_capability` object could contain:

```json
{
  "claim_id": "physical_carton_contents",
  "status": "NOT_ESTABLISHED",
  "observation_basis": "RECEIPT_CONFIRMED",
  "observation_coverage": "NO_INDEPENDENT_OBSERVATION_RECORD",
  "supporting_evidence_ids": [],
  "posting_evidence_ids": ["MAT-PRE-2026-00005", "MAT-PRE-2026-00006", "MAT-PRE-2026-00006:ledger"],
  "supported_scope": ["receipt posting", "stock ledger posting"],
  "unsupported_scope": ["independent carton contents"]
}
```

The values must be derived from source records, not from the question or an
expected natural-language answer:

| Status | Meaning |
| --- | --- |
| `SUPPORTED` | A current, scoped independent observation explicitly covers the claim and identifies its source evidence. |
| `NOT_ESTABLISHED` | The current evidence supplied to the agent does not support the claim. `observation_coverage` says whether this is a complete negative lookup, no observation source, or another bounded reason. It never claims the physical fact is false or that no other evidence exists. Receipt/ledger facts may still support a narrower posting claim. |
| `UNKNOWN` | The source is unavailable, malformed, or internally inconsistent enough that the capability cannot safely be calculated. It must not be rendered as either proof or disproof. |

`observation_scope` must remain distinct from quantity. A verified photo or
operator count of sealed cartons can support container presence/count without
supporting their contents. A scan can support an item identity without
supporting an unobserved number of physical units. That prevents an
`INDEPENDENT_OBSERVATION` flag from becoming a blanket proof oracle.

One possible enforcement seam is a typed result field that references this
source claim, with a gateway check that it is no stronger than current source
capability. A renderer could display the source-derived boundary alongside
model prose. That may improve the reliability of a visible source fact, but it
does not prove that the prose is coherent or that the model reasoned correctly.
Earlier typed-decision failures make schema agreement insufficient as semantic
acceptance. This option must therefore be evaluated separately for
source-derived display correctness and model-generated reasoning correctness.

It would not change `expected_disposition`, create a question regex, or use a
same-model critic. It also cannot be inferred from a PHOTO identifier or a
basis boolean: any affirmative capability needs observation scope, method,
item/receipt identity, and coverage in real source records.

## Counterexamples for a future design gate

If this unapproved safeguard is later designed, offline tests should exercise
the source-to-model-payload-to-rendered-result path with deterministic runners.
They must not encode the D4 wording or force a canned response.

| Source counterexample | Expected evidence capability | Why it matters |
| --- | --- | --- |
| Current receipt-only fixture: 2 posted/received, no independent observation record | `physical_carton_contents=NOT_ESTABLISHED` with `NO_INDEPENDENT_OBSERVATION_RECORD`; receipt/ledger posting remains supported | Catches the exact q4 conflation without treating receipt equality as corroboration or claiming no external observation exists. |
| Independent counted arrival says 3 Box while receipt/ledger says 2 Box | The count claim is `SUPPORTED`; posting claim is separately supported; discrepancy remains visible | Ensures the design does not blanket-deny real independent evidence or hide conflict. |
| Verified image/operator record says two sealed cartons but contains no contents mapping | Container count may be `SUPPORTED`; carton contents remain `NOT_ESTABLISHED` | Prevents a photo presence flag from becoming content proof. |
| Source has a photo identifier or Slack notification but no resolved observation record | `NOT_ESTABLISHED` when scope is complete | Prevents opaque IDs and notification copies from being promoted to physical evidence. |
| Observation lookup is unavailable, malformed, or internally inconsistent | `UNKNOWN` | Prevents false reassurance that no physical evidence exists and preserves honest uncertainty. |
| Explicit record of inspected contents linked to the receipt/item/quantity | `SUPPORTED` only for that declared scope | Proves the contract can express a legitimate affirmative result rather than hard-coding a negative for D4. |

Such tests would need to keep any source-derived receipt-only display narrower
than the physical-content claim, preserve the refusal and `SAFE_NOOP` state,
and show that assistant prose is never persisted as evidence. They would still
not count as a general model-accuracy pass.

## Causal limits and the next bounded experiment

The most plausible immediate mechanism is unsupported model synthesis after
the qualified source view reached the agent: the source transformation removes
the ambiguous quantity, every required tool completed, and the resulting
prose still upgrades posting records to physical-content proof. That is a
useful operational diagnosis, not proof of a model-intrinsic capability limit.

One stochastic Nova Pro turn cannot distinguish among a model's interpretation
of the prompt, an unretained framework message/tool serialization detail, a
poorly exposed source capability, or the attraction of the opaque `M20 PHOTO`
identifier. The retained human-only context makes prior assistant-prose
contamination unlikely for this turn, but it does not identify a unique cause.
Q1–Q3's otherwise acceptable factual answers also do not establish that the
model can or cannot handle the physical-evidence boundary generally.

Before another paid model screen, collect only the following minimal diagnostic
evidence offline:

1. At the agent boundary, retain redacted hashes and the semantic keys of the
   actual system prompt, acquisition/final user messages, tool definitions, and
   each JSON tool response. The capture must exclude credentials and retain the
   source's frozen/simulated label. This resolves whether the deterministic
   reconstruction matches the framework input without introducing a provider
   call.
2. Inject the retained q4 structured result into the existing validation path
   against the frozen packet and confirm its current admission. Do not add a
   typed assessment, renderer, prompt, or schema to that diagnostic; those
   remain separate design-gate work.
3. If the unapproved safeguard is later selected, exercise the listed source
   counterexamples through its packet and rendering path. The variants must
   change source capability, not a magic wording of the question; held-out
   semantic questions remain independent of implementation.

Only after the boundary diagnostic and independent design review should a new,
separately frozen model experiment be considered. It must not rerun q4 merely
to obtain a favorable sample, add an expected-answer regex, route this one
question to a canned response, or use a same-model critic as evidence
validation.

## Decision

Do not retry D4 question 4 to seek a better model sample. Freeze this diagnosis
and retain the failure. The only currently supported next implementation scope
is an offline capture of the existing SDK boundary plus retained-Q4 candidate
admission reproduction, with no source, prompt, renderer, model, or schema
change. A separate independent design gate must choose any product safeguard
before it is implemented.


## Independent review — diagnostic gate and proposal limit

**The retained failure and qualified causal account are accepted; the preceding implementation Decision is not approved.** The smallest justified next step is an offline capture of the existing frozen SDK input boundary and replay of the retained Q4 candidate through the existing validation path. Keep the current model, facts, source view, prompts, budgets and validation behavior unchanged for that diagnostic. No paid call is needed to establish what a reconstructed invocation supplies to the SDK or whether the existing validator admits this candidate. An offline interception cannot recover the unretained historical transport bytes: label it reconstruction at the exact revision/SDK, not proof of the original wire transcript. Avoid describing an incompletely captured view as definitively what the model received.

The claim-capability object plus typed assessment and deterministic renderer above is a **separate, unapproved product safeguard proposal**, not an accepted model-reasoning remedy. A renderer can make one visible statement correct while the model still supplies the opposite explanation; typed field agreement alone does not prove coherent prose or complex reasoning. Earlier failed typed-decision experiments already show why successful schema/enum validation cannot be substituted for semantic accuracy. If such a safeguard is later pursued, evaluate source-derived display correctness separately from model-generated factual correctness and reasoning. Do not count a rendered answer as an independent model pass or call the D4 failure repaired.

Its source semantics also need a separate design gate. An independent quantity observation is not automatically an observation of carton contents. A capability status must be supported by actual observation scope, method, item/receipt identity and coverage records; it cannot be inferred from a boolean/basis label, a PHOTO identifier, or the frozen expected verdict. The proposal must distinguish unavailable scope, absent support within supplied evidence, and an exhaustive negative lookup. The present evidence does not prove that every proposed affirmative content-capability dimension is represented by an existing source schema. This is a reason to research the interface before implementation, not to add an oracle-shaped status.

For now, preserve the D4 stop and Q5/Q6 NOT_REACHED. First perform the bounded offline boundary/candidate-admission diagnostic, report its limits, and independently choose a genuinely distinct next experiment. A separate model-capability comparison remains an option only after its exact access/IAM authorization gate is satisfied; the pending access approval must not be bypassed by this diagnostic or by another profile. No renderer, prompt, model or source changes are approved by this independent review, and no model/ERP/IAM call was performed.
