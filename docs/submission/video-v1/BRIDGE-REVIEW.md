# Independent review — minimal same-order bridge

**Initial verdict, superseded by the focused re-review below:** **BLOCKED for the full rehearsal.** The backend happy path has a real non-mutating proposal followed by an idempotent event execution, and attachment provenance is intentionally honest. The visible bridge still does not meet the requested full-graph experience, meaningful manager review, or durable recovery bar. This is a review of the uncommitted diff and focused tests, not proof of live ERP effects.

## Critical findings

### 1. [P0] “Dashboard” is only a renamed anchor; it does not provide the requested same-case graph

`workspace/distributor-operations.html:18` and `:23` now route Dashboard to `/operations#ops-flow-panel`. That target (`:65-83`) is the existing quantity-card and ordered-stage summary, not a relationship graph connecting receiving evidence, agent investigation, customer commitments, proposed action, native records, and readback. A judge clicking Dashboard sees the same long operations page, so the change does not satisfy the user's expectation of a real agent interaction beside a readable full graph.

**Required bounded fix:** render one compact graph from the current distributor projection inside this same-case surface, with the current case ID and matching record identifiers carried through its nodes and edges. If that graph cannot be delivered in this bridge, remove the Dashboard claim and revise the rehearsal/storyboard; changing the anchor label alone is not UX evidence.

### 2. [P0] The approval card hides the actual operation and then discards the approving manager

`workspace/distributor-operations.js:1648-1650` summarizes only event type and `evidence_ref`; it omits the quantity, lot, customer order, inspection result, shipment ID, and other typed fields that will be executed. The manager therefore cannot review the exact change before pressing **Approve and execute**. On the server, `src/the_missing_20/adapters/distributor_operations.py:529` validates `manager_id` and immediately discards it; the proposal schema at `:263-266` has no approving manager or approval timestamp. The UI nevertheless says “Manager approval recorded” at `workspace/distributor-operations.js:1999`.

**Required bounded fix:** render the exact validated proposal fields in the approval panel, then persist and return the manager identity and approval time with the proposal result. Show those values in the readback. Keep the existing operator-declared/agent-read-only labels; do not imply the agent originated the event.

### 3. [P1] A persisted proposal cannot recover into the visible approval flow after reload or interruption

The proposal row is durable, but `DistributorOperations.projection()` at `src/the_missing_20/adapters/distributor_operations.py:280-287` never reloads a pending proposal; `_with_proposal` is used only in the immediate prepare response. After a browser refresh or server restart, `preparedProposal` begins empty and the approval panel stays hidden. There is also an uncovered interruption window between `record_event(event)` at `:558` and storing the proposal result at `:566-569`: replay can no longer reliably return the completed approval result if the source revision changed after the native event.

**Required bounded fix:** expose the current pending/applied proposal from the normal projection, including its durable execution status, and make approval replay resolve through the proposal's event ID/result rather than depend on an uninterrupted request. Add focused reload and post-event interruption tests; never present a pending/unknown event projection as an applied approval.

## Checks that passed in this review

- Preparing a proposal is non-mutating in the focused service test; the happy-path duplicate approval calls the native bridge once.
- The revision hashes canonical source facts, so volatile raw provider timestamps are not currently included in the fingerprint.
- Photos are stored under the configured case, can be bound once, and are returned as `OPERATOR_ATTACHED_PHOTO` / `NOT_ANALYZED` without an image-recognition claim.
- `.venv/bin/python -m pytest -q tests/test_distributor_operations.py -k 'same_case_proposal or proposal_rejects_stale'`: **2 passed**.
- `node --test tests-js/distributor-operations.test.cjs`: **36 passed**. The new JavaScript assertions check strings/endpoints only; they do not cover proposal rendering, approval state, reload recovery, or routing behavior.

**Summary:** Standards axis: one truthfulness/provenance failure and one durability gap. Spec axis: two P0 misses—the requested graph is absent, and manager approval is not reviewable or durably attributable. No broader production refactor is needed; the fixes should stay on this filmed same-order path.

## Focused re-review — corrected bridge

**Updated verdict:** **One visible demo blocker remains before code-review clearance.** The corrected diff resolves the three original backend/structure blockers, but the post-approval graph and approval evidence become inaccurate on the automatic refresh. This is still not a live-browser or ERP-effects pass.

### Resolved in the corrected diff

- **Same-case graph:** `workspace/distributor-operations.html:65-69` now contains a dedicated dashboard graph, and `workspace/distributor-operations.js:978-1000` renders evidence, agent, commitments, approval, and ERP readback from the current projection with case and purchase-order identity.
- **Reviewable and attributable approval:** `workspace/distributor-operations.js:1681-1686` renders every validated event field relevant to execution. The server now persists `manager_id` and `approved_at`, returns approval evidence, and reprojects the latest proposal after reload.
- **Recovery:** the normal projection reloads the current proposal, and approval replay can recover a completed retained event result without starting the native event twice. The existing canonical revision continues to exclude volatile raw-source timestamps.
- **Approval quantity:** the proposal preserves the validated arrival payload, approval sends that same event through `record_event`, and the focused test proves `received` stays `0` before approval and becomes exactly `20` afterward with one `receive_arrival` bridge call. Duplicate approval does not add another call.

### Remaining blocker — post-approval refresh tells two conflicting stories

`renderPreparedProposal` reads approval evidence only from `next.approval_evidence` (`workspace/distributor-operations.js:1671-1677`). The immediate approval response has that field, but the automatic refresh at `:2043` returns the ordinary projection, where approval is nested under `prepared_proposal.approval`. The readback is therefore hidden immediately after refresh. At the same time, `renderOverview` treats any `prepared_proposal` as pending (`:986`), even when its status is `APPLIED`, so the graph changes to **“Proposal awaiting review”** after the manager has already approved and executed it.

**Required bounded fix:** derive both views from `prepared_proposal.status`. For `APPLIED`, keep the persisted manager/time/event readback visible using `prepared_proposal.approval` and `prepared_proposal.event.event_id`, and label the graph action as applied/verified. Use “awaiting review” only for `PENDING_MANAGER_APPROVAL`. Add one narrow projection-to-render test covering the automatic-refresh shape; no broader refactor or suite is needed.

Focused re-review command: `.venv/bin/python -m pytest -q tests/test_distributor_operations.py::test_same_case_proposal_is_non_mutating_then_manager_approval_applies_once tests/test_distributor_operations.py::test_proposal_rejects_stale_case_and_manual_photo_stays_unanalyzed` — **2 passed**. Browser rehearsal and native ERP readback remain separate acceptance gates.

## Final narrow re-review — status fix

**Code-review verdict:** **CLEARED for continued browser rehearsal.** No remaining code blocker was found in the requested JavaScript status scope. This clearance covers the minimal same-order bridge implementation; it is not full-rehearsal, live-source, exported-footage, or full-film acceptance.

The last visible inconsistency is corrected. `proposalActionDetail` now distinguishes `APPLIED` from `PENDING_MANAGER_APPROVAL`, so the graph reports **Approved operation applied** after execution. `approvalReadback` falls back from the immediate `approval_evidence` response to the persisted `prepared_proposal.approval` plus its event ID, preserving manager and timestamp through the automatic projection refresh. The focused JavaScript test covers the applied readback and rejects approval readback for a pending proposal. Preparing a new proposal also clears the old approval success feedback before displaying the new pending operation.

The earlier quantity conclusion remains unchanged: approval executes the exact validated proposal event, and the focused service evidence shows the sample arrival moving from `0` to exactly `20` received with one native bridge call and no duplicate execution. The primary rehearsal separately reports successful full-graph navigation with persisted approval identity/time, native A20 receipt/inspection/dispatch, cross-SaaS effects, a real Opus allocation, and two English agent turns. Those reported live results advance the rehearsal ledger but were not independently re-executed in this narrow source review.

Full-film clearance remains pending the complete rehearsal, final same-case evidence review, capture/readability checks, accurate narration, and exported runtime.
