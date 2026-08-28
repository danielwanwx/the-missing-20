# Milestone 5 Authoritative Lifecycle Rebaseline

**Decision:** `../../../decisions/0003-m5-authoritative-lifecycle-artifact.md`
**Status:** proposed for independent design gate

## Loop contract

**Goal:** replace the rejected legacy approval projection with a deterministic, auditable
workspace generated from actual local Authority-B quorum and controlled execution.

**Input:** synthetic main-case fixture, current Authority-B classifier/quorum/executor,
SQLite case store, synthetic enterprise adapter, frozen M4 evidence, and M5 UI shell.
The legacy main-case demo artifact may be retained historically but cannot be imported by
the new lifecycle generator or projector.

**Execute:** run a clean local lifecycle; persist its exact operational records; validate
the bundle fail closed; join advisory display modes only after validation; render valid
complete/degraded and invalid/unavailable browser states.

**Check:** identity and digest closure, zero pre-quorum effects, distinct intent closure,
authoritative rereads, postconditions, effect ledger, replay zero delta, mutation/deletion
matrix, complete/degraded operational equality, browser E2E, full tests and Golden gates.

**Feedback:** at most one focused implementation correction. A second material defect or
new authority boundary stops.

**Record:** lifecycle artifact, validation manifest, browser manifest/screenshots,
test totals, known limitations, and independent verdicts.

**Stop:** independent `APPROVE_M5_REBASELINED`, or stop for repeated failure/material
fork/human gate.

## Lifecycle runner

The runner creates fresh temporary enterprise and case databases and executes the main
synthetic discrepancy through production application adapters:

1. detect and admit authoritative evidence;
2. classify the retryable receipt-message state deterministically;
3. create receipt-restart intent A with exact typed parameters;
4. attest intent A as distinct Integration Operator and AP Approver principals;
5. prove no grant/effect after the first attestation;
6. execute grant A only through `AuthorityBControlledExecutor`, including reservation,
   fresh reread, effect ledger, verification, and replay;
7. reread the updated authoritative facts and deterministically derive invoice-release
   eligibility;
8. create a separate invoice-release intent B with its own case version, parameters, and
   digest; obtain a separate exact two-role quorum and execute/verify/replay it;
9. persist the final state and every source record used by the workspace.

If the current deterministic contract cannot legitimately derive or execute action B,
the runner stops rather than inventing closure. The valid workspace may then honestly
show the verified receipt-recovery boundary as its final proven state; displaying CLOSED
requires exact verified invoice-release evidence.

## Lifecycle bundle

`AuthorityBLifecycleDemo/v1` contains canonical, typed collections:

- scenario and fixture digest;
- detected case and admitted evidence identities/digest;
- deterministic decisions;
- authorization intents;
- attestations grouped by exact intent;
- signed quorum grants;
- execution attempts and policy decisions;
- authoritative before/after snapshots;
- business effects and verification receipts;
- replay requests/results and effect deltas;
- final case/enterprise state;
- stable references and a whole-bundle digest.

The bundle contains no advisory fields. It is written atomically from a successful run.

## Fail-closed projection

The projector validates before returning any operational panel:

- supported schema and canonical bundle digest;
- synthetic fixture identity and evidence integrity;
- decision/intent/grant/action/case-version/parameter/evidence digest closure;
- two distinct required principals and roles for every grant;
- grant signature, TTL at execution, and unique consumption;
- attempt/policy/effect/verification references;
- authoritative before/after state matching the asserted effect and postconditions;
- replay identity and zero new effects;
- final state derived from records, never supplied as a default.

On any failure it returns `WorkspaceAvailability/v1` with `status=UNAVAILABLE`, stable
reason codes, and no operational decision, human-control, execution, verification,
replay, or final-state payload. The browser shows the unavailable reason without filling
any missing lifecycle value.

## Advisory join and UI

The valid operational projection is built once. Complete scripted and degraded real
advisory modes are joined afterward and must have identical operational projection
digests. Advisory display retains the three evidence classes and non-authoritative label.

The unavailable browser mode is driven by a deliberately incomplete test bundle. It must
show `OPERATIONAL EVIDENCE UNAVAILABLE`, the reason code, and no approval/grant/PASS/
CLOSED claims. The server remains GET-only and local.

## Exact tests

- clean runner produces at least one real Authority-B quorum-controlled verified effect;
- first attestation produces zero grant/effect;
- separate actions never share an intent/grant/parameter digest;
- complete and degraded modes have byte-identical operational projection digest;
- delete/mutate each intent, attestation, grant, signature, version, parameters, attempt,
  effect, verification, replay, or final state and assert `UNAVAILABLE`;
- legacy main-case artifact import/reference scan returns zero;
- browser complete/degraded/unavailable DOM assertions and screenshots pass;
- no active write control, remote resource, secret, or unsupported AI/AWS claim;
- full `make check`, Golden v1/v2, workspace build, Chrome smoke, and diff check pass.

## Non-goals

No live approval UI, production identity, cloud deployment, provider call, new cost,
legacy artifact reinterpretation, commit/push, publication, recording, or submission.
