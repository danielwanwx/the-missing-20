# Native receiving N1 — six real model turns

Status: independently approved for the opt-in competition demo. This is a
real-model experiment against captured receiving sources, not full product,
repeated complex-matrix, production or ERP-effect acceptance.

The selected candidate uses installed Strands 1.53.0 native
`SnapshotSessionManager`, `LocalFileStorage` and `NullConversationManager`.
No SDK upgrade, summary generator, answer repair or additional memory framework
was needed for these six turns. N2 was deferred under the user's demo/time
priority; this is not a fresh paired comparison or proof that N1 beats N2.

## Actual sequence and independent result

Executed frozen revision: `4bd0eefc77fe29951ca1d0b07589a167a155a133`.
The runner and prompt are those in the [offline review](2026-09-09-native-session-v2-offline-review.md).
Each turn reconstructed the Agent in a fresh process. Actual persisted history
before every later turn exactly matched the preceding history after completion.
All six code/input hash checks remained unchanged.

| Turn | Human task | Actual result |
| --- | --- | --- |
| 1 | Quantity and stock record for PR6 | 1 Box; MAT-SLE-2026-00026 |
| 2 | Keep the conversation read-only | Instruction acknowledged without unnecessary source reads |
| 3 | Ordered and outstanding PO quantities | 40 Box ordered; 38 Box outstanding on PO15 |
| 4 | Does the receiving basis independently prove carton contents? | Correctly said no; omitted a concrete record citation, a retained minor defect |
| 5 | Current stock record for the receipt first discussed | Correctly resolved PR6, used the new current fixture record and kept 1 Box |
| 6 | What permission was given, and evidence for the prior answer? | No change permission; correctly cited PR6 and its current record for 1 Box |

Turn 5 changed only a declared simulated source record identifier to
`FIXTURE-SLE-R3-PR6-RENAMED`; it did not rename an actual ERP record. R3 has two
1 Box receipts, so aggregate 2 Box is not PR6's quantity. R3 evidence must not
be presented as a real R4 conversation.

Luna independently read the six actual answer/evidence records and approved
the limited demo promotion: no critical case, quantity, current-source or
authority failure. Turn 6's provider text included a delimited reasoning block;
the product integration must display only final text, preserving the private
raw response without publishing that block. This is presentation filtering,
not semantic rewriting or model feedback.

The completed sequence used 10 logical model requests, 87,803 input and 775
output tokens; the existing budget ledger estimated USD 0.0727224. Source-tool
call counts were 1, 0, 1, 1, 1, 0. History lengths after each turn were
4, 6, 10, 14, 18, 20. SDK completion remains `NOT_EVALUATED` internally;
semantic acceptance is the separate human-agent review recorded here.

## Preserved failures and costs

Private evidence roots are `/private/tmp/m20-native-session-v2-live-4bd0eef-01`
through `-04`. They contain source preparations, actual snapshots, raw process
outputs, per-turn results and review records. They are intentionally not in Git.

- Root 01: the sandbox could not reach the AWS sign-in endpoint. The first
  request failed with zero tokens and no source reads.
- Root 02: five real turns completed; turn 6 failed because AWS credentials
  expired. Cost before expiration was USD 0.0600752 (72,194 input, 725 output).
  Two answers omitted the explicit Box label; this earlier attempt remains
  separately recorded.
- Root 03: an attempted continuation incorrectly assumed the previous session
  still equalled the completed turn-5 snapshot. The SDK had already retained
  the failed turn-6 input. A setup assertion failed; orchestration mistakenly
  continued, but the runner's own snapshot check stopped before any model call.
  The session was not manually reconstructed or rewritten.
- Root 04: after the user renewed AWS login, a new empty session completed all
  six unchanged questions. This is the accepted sequence above.

Total estimated paid cost across these attempts was USD 0.1327976. This was
not an uninterrupted first-attempt pass. Long conversations, repeated scenarios,
held-out cases and the actual product interface still require their own evidence.
