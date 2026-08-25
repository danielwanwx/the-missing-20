# ADR 0001: Create a New Competition Repository

Status: Accepted
Date: 2026-08-24

## Context

The project builds on lessons from an earlier incident-response prototype, but the competition requires a new project and clear disclosure of pre-existing work. The new product also has a different business domain, authority model, synthetic data model, and user experience.

## Decision

Create a new MIT-licensed repository. Begin with no copied FlowPulse application code. Record conceptual influence immediately and require file-level provenance before any later reuse.

All enterprise systems and fixtures will be newly implemented with synthetic data. No employer or customer material is permitted.

## Consequences

- Git history clearly identifies competition-period work.
- Reuse requires an explicit, reviewable decision.
- Some prior implementation ideas may be reimplemented from first principles to preserve a clean boundary.
