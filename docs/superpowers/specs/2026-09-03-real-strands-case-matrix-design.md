# Real Strands Case Matrix

## Goal

Measure the real Bedrock-backed Strands agent across normal, incident, safety, and
recovery conditions without overwriting the historical provider-attempt artifacts.
The deliverable is a versioned report containing real model answers, tool traces,
usage, latency, deterministic rubric scores, and source provenance.

## Public seams under test

1. A batch CLI takes a selected case packet and produces one independent,
   read-only Strands run record.
2. Each Strands turn calls the single admitted-evidence tool before answering;
   the tool returns only the packet scoped to that case.
3. A report endpoint/artifact exposes per-case answer quality, safety verdict,
   provider traffic, and aggregate results without credentials or raw tokens.

## Inputs

- The 16 existing immutable golden case packets are the source of complex
  normal, incident, safety, and recovery scenarios.
- The current live M20 recovery is a separate `live-recovery` case. It reads
  the existing local dashboard projection, which in turn reads ERPNext,
  Airtable, Celigo, Jira, and Slack.
- The model may receive only the admitted case packet through a read-only
  tool. It never receives credentials or a write-capable provider tool.

## Batch loop

Goal: complete every selected case and make failures inspectable.

1. Load a case packet and its expected deterministic outcome.
2. Start a fresh real Strands/Nova Pro agent with a decorated, read-only
   `read_case_evidence` tool.
3. Ask an incident-specific or normal-operation question and record every
   model request, tool call, response, latency, and metered usage.
4. Apply deterministic checks: tool-first behavior, no claimed write,
   expected safety disposition, required evidence references, and concise
   answer structure.
5. Persist one redacted case result and an aggregate summary.
6. On a provider failure, record a failed case and continue with the next
   independent case. On a budget or rate-limit trip, stop cleanly and report
   the exact completed prefix; never silently retry.

## Coverage

- Normal: current verified recovery; already-posted receipt; completed
  crash-recovery.
- Incident / diagnosis: retryable integration lock; genuine short shipment;
  missing material-document evidence.
- Authorization and integrity: expired/replayed grants, tampered parameters,
  duplicate executor requests, and premature invoice release.
- Guardrail and resilience: evaluator rejection, postcondition failure, and
  crash recovery.
- Conversation red team: duplicate release request, unsupported invoice
  request, and provenance request for each relevant case.

The existing sixteen packets define the initial matrix. Additional case packets
can be added without changing the runner contract.

## Safety and cost

The user authorized broad coverage, but the runner retains a circuit breaker:
per-run maximum tokens, requests, and time are recorded and enforce a stop on
unexpected provider behavior. These are safety controls, not a reduced test
scope. Each batch has a fresh immutable ID and must not alter historical
`bedrock-attempt-claim` or failure artifacts.

## Records and acceptance

The runner writes a redacted `real-strands-matrix` artifact with:

- case ID, case class, expected outcome, prompt, answer, and rubric result;
- model / provider / transport, tool call sequence, latency, token usage, and
  estimated cost;
- a source label distinguishing `live` from fixture-backed evidence;
- aggregate completion, pass/fail counts, safety failures, and limitations.

Acceptance requires that every completed case has a real Nova Pro provider
record and a tool trace, that no case reports an unauthorized write, and that
every failed rubric check is explicit. The dashboard remains unchanged in this
scope; wiring the report into the dashboard is a follow-up product change.
