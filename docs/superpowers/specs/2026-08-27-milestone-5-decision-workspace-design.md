# Milestone 5 Decision Workspace

**Status:** proposed for independent design gate
**Authority:** M4 `APPROVE_M4_DISCLOSED_DEGRADATION`

## Loop contract

**Goal:** deliver a local, browser-visible Decision Workspace that makes the complete
synthetic incident, non-authoritative agent contribution, deterministic decision,
two-human authorization, controlled recovery, verification, and replay understandable
without fabricating live AI or cloud state.

**Inputs:** current Authority-B records, Golden artifacts, synthetic main-case fixture,
the frozen real degraded Nova evidence, and decision 0002. No network, provider call,
production data, employer material, or browser-authenticated external system is allowed.

**Execute:** create one deterministic workspace artifact, serve it through a minimal
local read-only HTTP application, render it as a single responsive decision surface,
and verify complete plus degraded views in headless Chrome.

**Checks:** artifact schema/identity, evidence taxonomy, authority labels, no browser-
derived lifecycle, no write route, accessibility landmarks, responsive rendering,
complete/degraded browser smoke, full repository and Golden gates.

**Feedback:** one focused material correction is allowed. A second material failure or
new authority/product direction stops the milestone.

**Records:** M5 artifact, browser-smoke manifest, test results, independent verdict, and
known limitations.

**Stop:** independent `APPROVE_M5`, or stop for a material fork/repeated failure/human
gate. No publication is part of M5.

## Product experience

The workspace is a single case-focused page designed for a five-minute walkthrough:

1. **Incident header:** warehouse expected 100, ERP received 80, missing 20, case status,
   deterministic eligibility, and verification status.
2. **Evidence bar:** `PROVEN`, `SCRIPTED SYNTHETIC PROOF`, and `NOT PROVEN` summary with
   the real Nova outcome visibly `DEGRADED` and stable usefulness `NOT PROVEN`.
3. **Agent investigation:** three competing scripted hypotheses, evidence gaps,
   confidence/disagreement, knowledge citations, latency/token/cost metadata, and the
   immutable advisory label. The degraded view instead shows the redacted provider
   failure and never invents hypotheses.
4. **Deterministic decision:** admitted authoritative sources, exact reason codes,
   allowed action, policy status, and decision digest. This panel is visually primary
   and never reads an agent verdict as an input.
5. **Human control:** distinct Integration Operator and AP Approver stages, exact quorum
   state, and explicit statement that no effect occurs after only one approval.
6. **Execution proof:** fresh read, controlled effect, postcondition verification,
   idempotency/replay result, and final authoritative state.
7. **Audit timeline:** ordered immutable records linking detection through replay.

## Architecture and data flow

`scripts/build_decision_workspace.py` composes a versioned, deterministic JSON artifact
from existing application/Authority-B models and Golden evidence. It offers two modes:

- `complete`: uses the existing scripted synthetic advisory projection and labels it
  `SCRIPTED SYNTHETIC PROOF`;
- `degraded`: uses the frozen real Nova degraded record and labels stable usefulness
  `NOT PROVEN`.

The artifact owns every displayed lifecycle fact. Static browser code receives JSON and
renders it; it cannot infer transitions, sign grants, approve, execute, or mutate storage.
A small standard-library local server exposes only `GET /`, static assets, `GET /api/
workspace?mode=complete|degraded`, and `GET /healthz`. All non-GET methods return 405.

The UI is dependency-light vanilla HTML/CSS/JavaScript so the locked project remains
offline-reproducible. It uses semantic landmarks, keyboard-readable disclosure blocks,
high-contrast status chips, and a compact desktop/mobile layout. There are no functional
approval buttons in M5; the page displays persisted approval evidence rather than
simulating human actions.

## Artifact contract

`DecisionWorkspaceDemo/v1` contains:

- synthetic case identity and discrepancy metrics;
- `evidence_taxonomy` with the three exact evidence classes;
- advisory mode/status/authority label/hypotheses/gaps/citations/usage/warnings;
- deterministic decision classification/eligibility/action/reason/source digest;
- exact approval roles, quorum state, and approval/effect boundary;
- execution, verification, replay, and final-state summaries;
- ordered audit entries with record type, evidence class, and stable reference;
- `claims` array that maps every visible product/AWS claim to evidence class;
- artifact digest over canonical content.

Unknown/missing required fields fail page loading with an explicit unavailable state.
The browser never silently substitutes sample values.

## Browser acceptance

A bounded headless-Chrome smoke starts the local server, loads both modes, waits for a
`data-workspace-ready=true` marker, captures local screenshots, and asserts through the
rendered DOM:

- all three evidence labels are visible;
- advisory output is labeled non-authoritative;
- degraded mode contains `DEGRADED` and `NOT PROVEN`, with no fabricated hypothesis;
- deterministic action and both human roles remain visible in either advisory mode;
- verification and replay evidence are visible;
- no active control can invoke approval or execution;
- no console error, failed resource, remote URL, or secret-like value appears.

The smoke writes a deterministic redacted manifest. Screenshots remain local artifacts
and are not uploaded.

## Acceptance

M5 requires full offline gates, Golden v1/v2 unchanged, deterministic complete/degraded
workspace artifacts, Chrome smoke PASS for both modes, synthetic-only/provenance checks,
and independent `APPROVE_M5`. M6 may start only after approval.

## Non-goals

No live approval UI, authentication, AgentCore deployment, new AWS/provider proof,
external analytics, production integration, commit/push, publication, video, or Devpost.
