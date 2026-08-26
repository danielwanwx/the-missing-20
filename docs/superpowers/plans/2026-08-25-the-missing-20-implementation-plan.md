# The Missing 20 Implementation Plan

**Status:** Accepted after independent review; implementation in progress
**Date:** 2026-08-25  
**Deadline:** 2026-09-14 at 5:00 PM PDT  
**Track:** Professional Agents  
**Repository:** <https://github.com/danielwanwx/the-missing-20>  
**Design source of truth:** [`../specs/2026-08-25-the-missing-20-design.md`](../specs/2026-08-25-the-missing-20-design.md)

## 1. Outcome

Build and publicly demonstrate one complete supply-chain exception resolution loop:

```text
physical receipt 100 + ERP receipt 80 + invoice 100
  -> deterministic discrepancy detection
  -> evidence-grounded multi-agent investigation
  -> independent evaluation
  -> Integration Operator approval
  -> safe receipt-message restart and verification
  -> AP Approver approval
  -> safe invoice release and verification
  -> CLOSED
```

The project succeeds only if the same implementation also proves that stale, replayed, cross-role, short-shipment, already-posted, and state-drift cases do not perform unauthorized writes.

## 2. Competition constraints

The official rules require a new Strands Agents project, a public MIT or Apache repository, README, architecture diagram, functional source and instructions, and a public video no longer than five minutes. AgentCore deployment and a live demo are optional but strengthen Technical Implementation. The five judging dimensions are equally weighted: Technical Implementation, Design, Potential Impact, Creativity and Originality, and Presentation.

Sources:

- [Official rules](https://agentsforhumans.devpost.com/rules)
- [Hackathon overview](https://agentsforhumans.devpost.com/)

This plan reserves September 14 for submission recovery only. The internal feature freeze is September 11.

## 3. Delivery principles

1. One vertical capability at a time. No broad scaffolding without an executable acceptance path.
2. Deterministic code owns truth, permissions, state transitions, and writes. Agents only investigate and recommend.
3. Synthetic data only. No employer code, records, terminology, screenshots, or internal documents.
4. Every model claim cites an admitted evidence ID. Missing evidence produces `NEEDS_EVIDENCE`, not a guess.
5. Every consequential action requires the correct human role, current case version, parameter-bound grant, fresh-read, idempotent execution, and verified postconditions.
6. Every milestone ends with tests, an inspectable artifact, a Git commit, and independent review.
7. Planned AWS behavior is never displayed as live behavior.
8. A feature that does not improve the five-minute story or one judging dimension is deferred.

## 4. Frozen technical choices

### Backend

- Python `3.12.13`.
- FastAPI for typed HTTP boundaries.
- Pydantic models for every command and result crossing a process boundary.
- Standard-library `sqlite3` behind repository interfaces for the local slice.
- Strands Agents SDK for investigators, synthesis, and evaluator.
- Boto3/AWS SDK adapters for DynamoDB, KMS, S3, Bedrock, and AgentCore integration.
- OpenTelemetry-compatible trace IDs propagated through case, agent, policy, and execution records.

### Frontend

- Node.js `20.18.3`.
- React, TypeScript, and Vite.
- Native fetch plus a small typed API client; no speculative state-management framework.
- Plain component CSS or CSS modules; no design-system dependency until the core workflow renders.

### Reproducibility

- `.python-version` pins `3.12.13`.
- `.nvmrc` pins `20.18.3`.
- `uv.lock` is the single Python dependency lock.
- `package-lock.json` is the frontend dependency lock.
- `.env.example` contains names and safe defaults only.
- `make bootstrap`, `make check`, `make dev`, `make demo`, `make golden`, `make agent-smoke`, and `make aws-smoke` are the supported entrypoints.

Exact library versions live in committed lockfiles so version truth is not duplicated across documentation.

## 5. Intended repository structure

```text
the-missing-20/
  src/the_missing_20/
    domain/
      models.py
      states.py
      events.py
      errors.py
    ports/
      case_store.py
      enterprise_systems.py
      knowledge.py
      signer.py
      investigator.py
    application/
      detector.py
      case_service.py
      authorization_service.py
      executor.py
      verifier.py
    adapters/
      sqlite_case_store.py
      synthetic_enterprise.py
      local_signer.py
      aws/
    agents/
      harness.py
      investigators.py
      synthesis.py
      evaluator.py
      schemas.py
    evaluation/
      golden_runner.py
      invariants.py
    api/
      app.py
      dependencies.py
      routes/
  web/
    src/
      api/
      components/
      features/case-monitor/
      features/investigation/
      features/approvals/
      features/golden-results/
  fixtures/
    scenarios/
    knowledge/
  golden/
    cases/
  tests/
    unit/
    contract/
    integration/
    golden/
  infra/
  scripts/
  artifacts/
```

Directories are created only when their first executable file is added.

## 6. Milestone sequence

### Milestone 0: Environment and repository contract

**Target:** August 25–26  
**Goal:** A clean checkout is reproducible and safe before product code begins.

#### Tasks

1. Add `.python-version`, `.nvmrc`, `.env.example`, and a local configuration model.
2. Install `uv`, resolve backend dependencies, and commit `uv.lock`.
3. Extend `package.json` only with Vite/React dependencies needed by the first UI build; regenerate `package-lock.json`.
4. Extend `Makefile` with:
   - `bootstrap`: locked installs only.
   - `check`: offline formatting, lint, types, backend tests, frontend tests/build, with no network or billable model calls.
   - `dev`: API and UI using synthetic fixtures.
   - `demo`: deterministic main-case CLI.
   - `golden`: frozen golden suite and JSON report.
   - `agent-smoke`: explicit, budget-bounded real Strands/model smoke test.
   - `aws-smoke`: preflight only until cloud adapters exist.
5. Add an AWS preflight script that refuses:
   - root credentials;
   - an unexpected account ID;
   - a region other than `us-west-2`;
   - missing resource prefix or cleanup manifest;
   - execution without an explicit confirmation flag.
6. Install AWS CLI 2.32+ and, only after user approval, configure a dedicated MFA IAM user with `aws login` temporary credentials and exact project-role assumption. Do not create long-lived API access keys; constrain the role with the project permissions boundary and remove the root bootstrap session after setup.
7. Update CI to use the locks and exact Python/Node lines.
8. Copy the retained AgentCore spike evidence into `artifacts/aws/` with a provenance note; do not copy credentials or account identifiers.
9. Run disposable, minimum-resource AWS capability probes before product code depends on them:
   - confirm AgentCore Gateway can expose one typed read tool;
   - confirm AgentCore Policy can produce inspectable allow/deny outcomes for exact tool and parameters;
   - confirm KMS signing and DynamoDB conditional-write semantics needed by grants;
   - confirm two-role identity claims can reach the policy boundary.
10. Record an AWS go/no-go matrix by August 28. Product adapters still wait until Milestone 6.

#### Files

- `.python-version`
- `.nvmrc`
- `.env.example`
- `uv.lock`
- `pyproject.toml`
- `package.json`
- `package-lock.json`
- `Makefile`
- `.github/workflows/ci.yml`
- `src/the_missing_20/config.py`
- `scripts/aws_preflight.py`
- `scripts/aws_capability_probe.py`
- `tests/unit/test_config.py`
- `tests/unit/test_aws_preflight.py`
- `artifacts/aws/capability-gate-v1.json`

#### Acceptance

```bash
make bootstrap
make check
make aws-smoke AWS_CONFIRM=0
```

- Clean checkout passes `make check`.
- The AWS smoke command performs zero mutations without explicit authorization.
- CI passes on `main`.
- The August 28 capability matrix marks every AWS control as `PROVEN`, `NOT_PROVEN`, or `UNSUITABLE`; no planned behavior is inferred from a successful Runtime invocation.

### Milestone 1: Domain contracts and state machine

**Target:** August 27  
**Goal:** Encode the approved contracts and transitions before adapters or agents.

#### Tasks

1. Implement enums and immutable models for case, evidence, hypotheses, evaluation, approval, grant, receipt, and append-only events.
2. Implement the approved state transition table.
3. Reject unknown events, stale expected versions, invalid role/action combinations, and closure without verified postconditions.
4. Add JSON serialization contract tests and a checked-in JSON example for every public model.

#### Files

- `src/the_missing_20/domain/models.py`
- `src/the_missing_20/domain/states.py`
- `src/the_missing_20/domain/events.py`
- `src/the_missing_20/domain/errors.py`
- `tests/unit/test_models.py`
- `tests/unit/test_state_machine.py`
- `tests/contract/test_json_contracts.py`
- `fixtures/contracts/*.json`

#### Acceptance

- Every transition in the spec has one positive test.
- Every forbidden transition has a negative test.
- `CLOSED` cannot be supplied by an agent or browser payload.

### Milestone 2: Deterministic main-case vertical slice

**Target:** August 28–30  
**Goal:** Complete the entire primary case locally without an LLM.

#### Tasks

1. Create the synthetic warehouse, queue, ERP receipt, and invoice fixtures.
2. Implement typed enterprise ports and the synthetic adapter.
3. Implement the deterministic detector and case creation.
4. Implement append-only SQLite events and a derived current projection with optimistic version checks.
5. Implement role-scoped approval commands.
6. Implement a local signer with the same grant envelope expected from KMS.
7. Implement deny-by-default local policy evaluation.
8. Implement receipt restart, invoice release, fresh-read, idempotency, and postcondition verification.
9. Add `make demo` that runs the approved 100/80/100 path and writes `artifacts/demo/main-case.json`.
10. Inject a persistence failure after a successful downstream receipt restart; retry must reuse the same idempotency key or become a fresh-read safe no-op.

#### Files

- `fixtures/scenarios/retryable-document-lock.json`
- `src/the_missing_20/ports/*.py`
- `src/the_missing_20/application/detector.py`
- `src/the_missing_20/application/case_service.py`
- `src/the_missing_20/application/authorization_service.py`
- `src/the_missing_20/application/executor.py`
- `src/the_missing_20/application/verifier.py`
- `src/the_missing_20/adapters/sqlite_case_store.py`
- `src/the_missing_20/adapters/synthetic_enterprise.py`
- `src/the_missing_20/adapters/local_signer.py`
- `scripts/run_demo.py`
- `tests/integration/test_main_case.py`

#### Acceptance

- The main case reaches `CLOSED` only after two role-correct approvals.
- The receipt becomes 100 before invoice release is eligible.
- Every event, grant, policy decision, and receipt shares the same case and trace IDs.
- Running the executor twice creates no duplicate business effect.
- A crash between downstream success and receipt persistence creates no duplicate business effect after recovery.

### Milestone 3: Safety counterexamples and Golden v1

**Target:** August 31  
**Goal:** Prove the product is a controlled resolution harness, not an auto-write demo.

#### Tasks

1. Encode all 16 golden cases from the design spec.
2. Implement invariant checks for action eligibility, zero unauthorized writes, terminal state, evidence requirements, role separation, and replay protection.
3. Add deterministic tests for already-posted, state drift, genuine short shipment, expired grant, replay, old version, tampered digest, cross-role action, and failed postcondition.
4. Add the crash-consistency case where the downstream write succeeds but the local execution receipt is not persisted.
5. Generate a machine-readable Golden v1 report.

#### Files

- `golden/cases/*.json`
- `src/the_missing_20/evaluation/invariants.py`
- `src/the_missing_20/evaluation/golden_runner.py`
- `tests/golden/test_golden_cases.py`
- `artifacts/golden/golden-v1.json`

#### Acceptance

```bash
make golden
```

- All 16 cases pass deterministic invariants.
- False receipt restarts: zero.
- False invoice releases: zero.
- Cross-role grants: zero.
- Replay-created downstream effects: zero.
- Crash-recovery duplicate downstream effects: zero.

### Milestone 4: Multi-agent investigation and evaluation harness

**Target:** September 1–4  
**Goal:** Replace the deterministic diagnosis stub with real Strands investigators while preserving deterministic authority.

#### Tasks

1. Define strict structured outputs for investigators, synthesis, and evaluator.
2. Implement three bounded investigators:
   - Retryable Message Investigator.
   - Short Shipment Investigator.
   - Duplicate Posting Investigator.
3. Run investigators concurrently with allowlisted read tools and bounded tool/model budgets.
4. Implement a versioned local knowledge adapter over synthetic SOPs and error definitions.
5. Implement synthesis that preserves conflicting evidence and requests missing evidence when required.
6. Implement an independent evaluator with a separately assembled evidence view.
7. Reject uncited facts and knowledge-only claims about current state.
8. Record normalized traces without chain of thought.
9. Run Golden v2 across prompt, model, and harness versions.
10. Freeze one proven model, prompt, retrieval, and harness configuration by September 4; later changes must pass the same Golden v2 suite.

#### Files

- `fixtures/knowledge/*.md`
- `src/the_missing_20/agents/schemas.py`
- `src/the_missing_20/agents/investigators.py`
- `src/the_missing_20/agents/harness.py`
- `src/the_missing_20/agents/synthesis.py`
- `src/the_missing_20/agents/evaluator.py`
- `src/the_missing_20/adapters/local_knowledge.py`
- `tests/unit/test_evidence_validation.py`
- `tests/integration/test_agent_harness.py`
- `tests/golden/test_agent_golden_cases.py`
- `artifacts/golden/golden-v2.json`

#### Acceptance

- Main case diagnosis identifies the retryable message using admitted evidence IDs.
- Genuine short shipment remains protected.
- Missing current-state evidence produces `NEEDS_EVIDENCE`.
- No agent object can call approval, signing, policy, or executor ports.
- Golden invariants remain green across at least two repeated runs.
- Offline `make check` uses mocks or frozen replay fixtures and makes no network or billable model calls.
- Real model verification runs only through `make agent-smoke` with an explicit invocation and budget limit.

### Milestone 5: Typed API and decision workspace

**Target:** September 5–7  
**Goal:** Deliver a complete product experience around the verified backend.

#### Backend endpoints

- `POST /api/demo/reset/{scenario_id}`
- `POST /api/detector/run`
- `GET /api/cases`
- `GET /api/cases/{case_id}`
- `POST /api/cases/{case_id}/investigate`
- `POST /api/cases/{case_id}/approvals`
- `POST /api/cases/{case_id}/authorizations/{authorization_id}/execute`
- `GET /api/golden/latest`

The local-only principal comes from server configuration or a dedicated demo header; the request body cannot select its own role.

#### UI sequence

1. Live exception monitor shows `Physical 100 / ERP 80 / Invoice 100`.
2. Investigation view shows three hypotheses, evidence citations, uncertainty, and evaluator outcome.
3. Integration Operator view exposes only receipt restart approval.
4. Receipt verification visibly unlocks AP approval.
5. AP view exposes only invoice release approval.
6. Final view shows verified postconditions and `CLOSED`.
7. Safety replay demonstrates state drift becoming a safe no-op.
8. Golden panel shows passed invariants without invented accuracy claims.

#### Files

- `src/the_missing_20/api/app.py`
- `src/the_missing_20/api/dependencies.py`
- `src/the_missing_20/api/routes/*.py`
- `web/src/api/*.ts`
- `web/src/features/**/*.tsx`
- `web/src/**/*.test.tsx`
- `tests/contract/test_api.py`
- `tests/integration/test_api_main_case.py`

#### Acceptance

- A fresh user can complete the main case through the UI without terminal access.
- Browser refresh reconstructs state from the backend projection.
- The UI never invents pending, approved, executed, or closed states.
- Keyboard navigation and color contrast pass the selected accessibility checks.
- A recordable end-to-end UI path exists by September 7; otherwise the UI collapses to one guided case page and removes the optional golden dashboard before AWS integration begins.

### Milestone 6: AWS proof integration and cloud adapters

**Target:** September 8–10  
**Goal:** Integrate only the AWS capabilities proven by the August 28 gate and retain evidence for every cloud claim.

#### Required P0: AgentCore Runtime

- Deploy the Strands investigation entrypoint.
- Invoke the primary synthetic case with the frozen September 4 harness configuration.
- Retain the structured diagnosis, invocation evidence, and trace ID.
- This is the minimum cloud proof required for the final video.

#### Target P1: one bounded tool and policy path

- Expose one typed read tool and, only if the August 28 gate passed, one bounded action tool through AgentCore Gateway.
- Prove one allow and at least three denies: wrong role, wrong parameter digest, and stale/expired grant.
- If the real service cannot enforce the approved contract, keep the deterministic local authorization path, label Gateway/Policy as not proven, and remove the cloud-policy claim from the video.

#### Stretch: cloud control-plane substitution

- KMS-signed grants and DynamoDB conditional writes.
- Two distinct Cognito demo identities or groups.
- Bedrock Knowledge Bases with S3 Vectors and version-filtered synthetic retrieval.
- Comprehensive OTEL trace correlation.
- Hosted live demo.

Stretch items are attempted only after P0, the local safety loop, the UI recording path, and Golden v2 are green. A local deterministic control remains authoritative whenever its cloud replacement is unproven.

#### AWS files

- `src/the_missing_20/adapters/aws/*.py`
- `infra/README.md`
- `infra/manifest.json`
- `scripts/deploy_*.py`
- `scripts/cleanup_*.py`
- `tests/aws/test_*.py`
- `artifacts/aws/*.json`

#### Acceptance

- Every service shown as live in the video has a retained proof artifact.
- Deny cases fail closed with zero downstream effects.
- `make aws-smoke` verifies account, region, identity, budget, prefix, and cleanup before mutation.
- Disposable resources are deleted after each spike unless explicitly retained for the live demo.
- P0 is complete. P1 is either proven or explicitly removed from final claims. Stretch omissions do not block submission.

### Milestone 7: Demo hardening and submission package

**Target:** September 11–13  
**Goal:** Freeze a judge-ready product and leave September 14 for recovery only.

#### Tasks

1. Freeze features on September 11.
2. Run clean-machine installation and full demo twice.
3. Run security, provenance, secret, dependency, accessibility, and browser audits.
4. Finalize README with setup, local demo, cloud proof labels, testing, architecture, and limitations.
5. Capture the five-minute video using the approved storyboard.
6. Publish the public video and optional live demo.
7. Draft and save the Devpost submission before the last day.
8. Publish at least one `builder.aws.com` article if the product is stable; a blog cannot delay the core submission.
9. Obtain final independent ERP/SAP architecture, agent safety, competition rubric, and repository reviews.
10. Tag the reviewed submission commit.

Fallback dates are binding:

- **August 28:** freeze the usable AWS control path from the capability matrix.
- **September 4:** freeze one model, prompt, retrieval, and harness configuration.
- **September 7:** require one recordable end-to-end UI path.
- A missed gate immediately cuts optional cloud substitution, golden dashboard, separate UI pages, blog posts, and hosted demo before it consumes the next milestone.

#### Acceptance

- Video is at most five minutes and shows real working behavior.
- README, architecture, source, MIT license, instructions, public URL, and video satisfy the official checklist.
- The public repository contains no secrets, confidential material, or undisclosed reused files.
- Final independent reviewer returns `ACCEPT`.

## 7. Calendar and critical path

| Date | Critical output | Cannot slip past |
|---|---|---|
| Aug 25–26 | Reproducible environment, CI, and early AWS probes | Aug 26 |
| Aug 27 | Domain/state contracts | Aug 27 |
| Aug 28 | AWS control-path go/no-go | Aug 28 |
| Aug 28–30 | Deterministic closed slice and crash recovery | Aug 30 |
| Aug 31 | Golden v1 safety suite | Aug 31 |
| Sep 1–4 | Strands harness and Golden v2 | Sep 4 |
| Sep 5–7 | Decision workspace | Sep 7 |
| Sep 8–10 | AWS proof gates and adapters | Sep 10 |
| Sep 11 | Feature freeze | Sep 11 |
| Sep 12–13 | Video, README, final audits, draft submission | Sep 13 |
| Sep 14 before 5 PM PDT | Recovery and final submission only | 5 PM PDT |

Critical path:

```text
environment
  -> domain contracts
  -> deterministic CLOSED slice
  -> safety golden suite
  -> Strands investigation
  -> product UI
  -> AWS proof integration
  -> video and submission
```

The UI may begin once stable API contracts exist. AWS spikes may run alongside UI work, but cloud adapters cannot bypass the deterministic slice.

## 8. Scope cuts, in order

If schedule pressure appears, cut in this order:

1. Multiple builder.aws.com bonus posts.
2. Optional hosted live demo; retain recorded working deployment evidence.
3. Cloud substitution beyond AgentCore Runtime and one proven bounded tool path.
4. Golden dashboard and separate UI pages; collapse to one guided case view.
5. Additional ERP exception types beyond the frozen 16 cases.
6. Visual polish not required for the five-minute story.
7. Extra analytics and trend views.

Never cut:

- Real Strands multi-agent investigation.
- The deterministic primary loop.
- Two human roles.
- Fresh-read, idempotency, grant integrity, and postcondition verification.
- Safety counterexample.
- Golden regression evidence.
- Public source, license, README, architecture, and video.

## 9. Evidence ledger

Every milestone appends one row to `artifacts/evidence-index.md`:

| Milestone | Commit | Command | Artifact | Reviewer | Result |
|---|---|---|---|---|---|
| M0 | pending | `make check` | CI run and environment report | pending | pending |
| M1 | pending | domain tests | contract report | pending | pending |
| M2 | pending | `make demo` | main-case trace | pending | pending |
| M3 | pending | `make golden` | Golden v1 | pending | pending |
| M4 | pending | agent golden suite | Golden v2 and traces | pending | pending |
| M5 | pending | browser smoke | UI recording | pending | pending |
| M6 | pending | `make aws-smoke` | AWS proof bundle | pending | pending |
| M7 | pending | final audit | submission bundle | pending | pending |

## 10. Review and execution protocol

For each milestone:

1. Implement the smallest testable slice.
2. Run local checks and record evidence.
3. Ask an independent agent to review against this plan and the design spec.
4. Fix all blocking findings.
5. Commit and push only after checks pass.
6. Proceed automatically when the reviewer returns `ACCEPT` and no account, paid service, scope, or public-submission gate is reached.
7. Ask the user only for a real decision or action-time authorization.

Implementation stops and returns to design review if:

- the main case needs a new consequential action;
- an agent would require write credentials;
- AgentCore Runtime P0 cannot host the required Strands diagnosis;
- a Gateway/Policy fallback would weaken the approved deterministic safety model;
- the demo needs confidential or non-synthetic data;
- the five-minute story cannot complete by September 7;
- a safety golden case remains red after the assigned milestone.
