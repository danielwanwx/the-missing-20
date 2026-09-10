# English operations integration

Status: implemented; scoped verification is recorded in the corresponding audit.

## Goal and source

Align the current distributor workspace with the approved silver/white, Geist,
solid-state design. Keep the real PO18 case, quantities, events, ERP documents,
commercial values and external records visible and distinguish historical evidence
from current commitments. Product-authored answers and interface text are English,
including when the operator asks in another language.

## Bounded changes

- Give native and legacy model answers an English instruction and deterministic
  output-language check. A rejected answer produces an English unavailable result,
  not a fabricated successful translation. Preserve input comprehension and IDs.
- Include current commercial evidence and the initial receiving/inspection events
  in the distributor conversation source. Do not use expected test answers as facts.
- Render a connected business-stage view with current stock and cumulative
  fulfillment labelled separately. Active exceptions highlight affected stages;
  resolved evidence remains accessible without claiming an active incident.
- Compare observed quantities with the same order's configured targets. Label
  units, case and comparison scope. Missing comparable history or industry data
  is unavailable, not a made-up baseline or a savings claim.
- Distinguish the last recorded contract selection from a current zero-quantity
  plan after fulfillment. Preserve source links and financial missing states.
- Provide explicit English dictation and read/stop-answer controls. Dictation
  populates the input and does not submit it. Unsupported or denied capabilities
  keep typing available. No automatic microphone activation or playback.

Browser-native speech follows the documented language settings and capability
limits: [recognition language](https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition/lang)
and [utterance language](https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesisUtterance/lang),
checked September 10, 2026. This is browser speech, not a claim of a Bedrock audio model.

## Verification and stop rules

Focused tests cover English output, an input asking for Chinese output, follow-up,
language violation, source scope, held/partial/completed/unavailable states,
missing benchmarks and speech lifecycle. Browser checks use the current 8903
workspace and isolated state fixtures without additional inventory writes.
Read-only real model checks retain complete attempts and evaluate quantities,
causal uncertainty, source freshness and language separately. UI/API success is
not sufficient for semantic acceptance. Hardware speech input remains unverified
unless actually exercised with a microphone.

Each accepted slice gets independent review, exact-file commit/push, remote SHA
verification and actual CI. Preserve private historical evidence and all failure
records. Repository language inventory determines the remaining translation scope;
this design does not claim that inventory or translation is already complete.
