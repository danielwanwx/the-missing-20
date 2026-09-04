# Ambiguous Receipt and Quality Investigation — Implementation Plan

**Design:** `docs/superpowers/specs/2026-09-03-ambiguous-receipt-quality-investigation-design.md`  
**Outcome:** a disclosed-synthetic, source-correlated 100-unit incident with a
recorded 80/8/12 opening state, a real advisory investigation boundary, deterministic
recovery and two safe-stop counterfactuals.

## 1. Establish a versioned case fixture

**Ownership:** domain and synthetic-enterprise adapters.

- Add a case fixture that represents `PO-4817`, item/lot identity, 80 available,
  8 quality-held and 12 receipt-unknown units. Preserve existing one-line cases.
- Represent independent source projections: warehouse/ASN scan, quality disposition,
  integration trace/attempt lineage, ERP receipt key lookup, stock buckets and invoice
  hold reason.
- Give every projected record an immutable source record ID, correlation ID,
  observed timestamp and business/idempotency key.
- Define the three branches as fixture inputs, never as UI-only switches:
  primary (absent receipt + eligible quality release), already-committed, and
  quality-ineligible.

**Tests:** invariant tests prevent a synthetic receipt or transfer being repeated for
the same idempotency key and verify that each projection uses the shared correlation
tuple.

## 2. Expose read-only correlated evidence

**Ownership:** live source/advisory adapters and local workspace server.

- Extend the agent-platform projection with the admitted source evidence fields and
  scenario state; retain read-only provider boundaries.
- Add source calls for match/hold, warehouse evidence, quality evidence, integration
  lineage and ERP business-key reread. Each must return only the current fixture's
  evidence IDs.
- Reject advisory responses that cite unreturned evidence, claim effects, omit required
  sources or choose an action incompatible with deterministic facts.
- Emit source-read and decision events through the ordered ledger/SSE path.

**Tests:** gateway/unit tests cover admitted citation closure, unavailable source,
ambiguous integration outcome, and no-write claim validation.

## 3. Bind deterministic recovery to the primary fixture

**Ownership:** demo executor, case store and scenario lifecycle.

- Build one exact proposal packet: idempotent 12-unit receipt plus idempotent 8-unit
quality-to-stores transfer, each tied to current evidence versions.
- Keep Manager as the single visible approval role. Approval authorizes only the packet
  hash, scenario version and two declared effects.
- Execute only when the primary branch's guard facts are true; otherwise return a
  reconcile-only / safe-stop result without changing state.
- After execution, reread receipt keys, stock buckets, invoice hold and integration
  status before closing the incident.

**Tests:** primary recovery reaches 100 available exactly once; existing business key
causes zero effects; ineligible quality evidence causes zero effects; replay remains
zero-effect.

## 4. Refocus Dashboard and Agent Workspace

**Ownership:** workspace client and browser smoke tests.

- Replace the generic 100/80 label with a concise source-backed opening: `100 arrived`,
  `80 available`, `8 quality hold`, `12 receipt unresolved`, `Invoice held`.
- Render a chronological evidence stream with source badge, correlation ID, source
  record ID and observed time; animate only actual SSE events.
- Add visible hypothesis/decision cards: do-not-retry until ERP key lookup, exact
  recovery plan, manager approval, and verified reread. Remove diagram/explanatory
  content that does not advance the recorded story.
- Make counterfactual selection an explicit scenario/testing control but keep it out of
  the main video path.

**Tests:** browser tests assert source-labelled state transitions and state from API/SSE,
not local animation; existing dashboard paths remain functional.

## 5. Validate the real advisory path and judge replay

**Ownership:** case matrix, smoke scripts and release evidence.

- Run the primary incident and both counterfactuals through the real Strands/Nova
  read-only advisory route with conservative request/cost caps.
- Score source-call coverage, citation validity, safe disposition and no-write claim.
  Do not score post-execution `RECOVERY_COMPLETE` before the executor has run.
- Run focused Python tests, browser smoke, `npm test`, ruff and diff checks; report
  pre-existing global failures separately if any remain.
- Capture one normal, incident, investigation and verified-recovery screenshot/video
  rehearsal for later judge review; redact credentials and label data synthetic.

## Order of execution

1. Domain fixture plus invariants.
2. Source projections and advisory contract.
3. Deterministic proposal/execution/re-read.
4. UI/event-stream projection.
5. Focused, browser and real-provider verification.

## Completion criteria

- The primary story is discoverable only from source evidence, not a seeded root-cause
  label.
- Each branch produces the correct action class: recover, reconcile-only or safe-stop.
- The Agent demonstrably performs read-only evidence acquisition and can explain its
  decision using returned IDs.
- The manager-visible action causes a verifiable, idempotent synthetic ERP outcome.
- The browser tells the story in five minutes without claiming external production
  writes or presenting decorative activity as live data.
