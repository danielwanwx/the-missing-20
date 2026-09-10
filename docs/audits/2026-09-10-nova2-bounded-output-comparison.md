# Nova 2 bounded output comparison

Frozen before invocation on September 10, 2026. Baseline: the retained Nova Pro
turn3 incorrectly inferred supplier packing responsibility and described a
blocked pick as complete. Nova2 at the same 1551 output cap stopped with
MaxTokensReachedException and did not produce a complete accepted answer.

Next candidate changes only the per-request output ceiling to 4096. Keep exact
turn2 history (including erroneous assistant claims), exact turn3 newest source
and question, native prompt/tools, temperature0, extended thinkingOFF, total
output6204 and total tokens80000. One paid invocation; preserve any failure.
No expected-answer hints enter the model input. No product promotion from a
truncated answer. If this candidate also cannot produce an accurate full answer,
reassess native configuration/context design before any further equivalent retry.

Acceptance: distinguish observations from unproved supplier/transit attribution;
state A25 complete and B15 pending at this frozen source state; distinguish the
blocked C2 pick from a submitted pick; state that physical evidence is declared
synthetic, not independently measured by the agent. Read-only comparison must
produce no ERP effects. This single case cannot certify broad multi-turn or
complex-task accuracy; independent review and held-out questions follow any GO.

The [Strands agent-loop documentation](https://strandsagents.com/docs/user-guide/concepts/agents/agent-loop/)
documents max-token interruption; [AWS Nova2 configuration](https://docs.aws.amazon.com/nova/latest/nova2-userguide/extended-thinking.html)
supports disabling extended thinking. No new framework or SDK upgrade is required
for this bounded experiment. Existing product budgets remain unchanged.


## Result and independent review

FAIL / do not promote. Nova2 completed with end_turn in11.162 seconds, using
12,453 input and1,519 output tokens (13,972 total), no tool calls. It correctly
said supplier responsibility is unproved and C2 remains to pick, but incorrectly
said SO10 has only2 units left to dispatch. The frozen source has requested15,
picked13, dispatched0, confirmed0:2 remain to pick and15 remain to dispatch.
Terra High independently confirmed this material error. The retained private
artifact is `component-nova2-output4096-comparison-01.json`. The output cap change
is not promoted. Product model and budgets remain unchanged.

## Reassessment: explicit fulfillment facts

[ERPNext Pick List](https://docs.frappe.io/erpnext/pick-list) records completed
picking; [Delivery Note](https://docs.frappe.io/erpnext/delivery-note) submission
creates stock ledger entries. Thus picked quantities cannot be subtracted from
customer demand to calculate remaining dispatch. The current raw packet leaves
this distinction and arithmetic to the model.

The next candidate is a reusable domain fact projection, not another reasoning
budget increase: derive remaining_to_pick=requested-picked,
remaining_to_dispatch=requested-dispatched, and remaining_delivery_confirmation=
requested-delivery_confirmed separately from current admitted quantities, with
Nos/Box UOM and actual customer order IDs. Missing, invalid or inconsistent
counts remain unknown rather than zero; never treat picked as dispatched.
Preserve raw facts, history, prompt, provenance and failed events. This is
read-only application arithmetic, not a summary of an assistant answer.

Strands already supports per-turn context and tools. Its
[context injection documentation](https://strandsagents.com/docs/user-guide/concepts/plugins/context-injector/)
describes current-fact injection; adding a second framework cannot define ERP
business semantics for us. Reuse the existing native per-turn source seam, with
no new SDK dependency or custom memory store. Compare current NovaPro and Nova2
against the same enriched frozen source, then independent review before any
product promotion. Any improved model must also pass a held-out multi-turn
question set; this one corrected example is insufficient.


### Prospective paired and held-out acceptance

Two maximum comparison invocations use the same enriched captured turn3 source:
NovaPro at1551, Nova2 at4096, both temperature0/thinkingOFF and unchanged history.
This measures configurations, not an equal-budget model ranking. Prefer the
existing product model if both are accurate; do not migrate simply because a
new model is available. A failure to finish is a failure, not inferred correctness.

Before any UI paid hold-out, freeze three follow-up questions against actual
current final40/POD40 source, retaining the existing failed native history:
1. Original prompt (Chinese; exact Unicode escapes): `\u201c\u8bf7\u91cd\u65b0\u6838\u5bf9\u8fd9\u4e24\u5f20\u5ba2\u6237\u8ba2\u5355\uff1a\u5206\u522b\u5df2\u62e3\u3001\u5df2\u53d1\u3001\u5df2\u7b7e\u6536\u53ca\u5269\u4f59\u5f85\u53d1\u662f\u591a\u5c11\uff1f\u4e0d\u8981\u628a\u62e3\u8d27\u5f53\u6210\u53d1\u8d27\u3002\u201d` English meaning: Recheck the two customer orders: how much is picked, shipped, signed for, and remaining to ship? Do not treat picking as shipping.
2. Original prompt (Chinese; exact Unicode escapes): `\u201c\u90a3\u4e3a\u4ec0\u4e48\u9875\u9762\u8fd8\u4fdd\u7559\u4e09\u4e2a\u544a\u8b66\uff1f\u8fd9\u80fd\u8bc1\u660e\u5ba2\u6237\u8fd8\u6ca1\u6709\u6536\u5230\u8d27\u5417\uff1f\u54ea\u4e9b\u662f\u5b9e\u9645\u7cfb\u7edf\u8bb0\u5f55\uff0c\u54ea\u4e9b\u53ea\u662f\u6f14\u793a\u8f93\u5165\uff1f\u201d` English meaning: Why does the page still retain three alerts? Can that prove the customers have not received the goods? Which entries are actual system records and which are demo input?
3. Original prompt (Chinese; exact Unicode escapes): `\u201c\u6839\u636e\u76ee\u524d\u7684\u8bb0\u5f55\uff0c\u53ef\u4ee5\u5411\u4f9b\u5e94\u5546\u65ad\u8a00\u539f\u6765\u4e24\u4ef6\u77ed\u7f3a\u4e00\u5b9a\u662f\u4ed6\u4eec\u5c11\u88c5\uff0c\u800c\u4e14\u4e4b\u524d\u9694\u79bb\u768418\u4ef6\u5168\u90e8\u6709\u7f3a\u9677\u5417\uff1f\u8fd8\u7f3a\u4ec0\u4e48\u8bc1\u636e\uff1f\u201d` English meaning: Based on the current records, can we tell the supplier that the original two-unit shortfall was definitely their short packing, and that all 18 previously isolated units are defective? What evidence is still missing?

Expected facts stay outside model input: final orders25/15 fully dispatched and
synthetic-POD confirmed, remaining0/0; original unknown/blocked events retained
without undoing later admitted completion; real ERP vs synthetic physical proof;
no proved supplier responsibility; sample failure does not establish all18
physically defective. No ERP writes or message sends are authorized by a model
answer. These are representative hold-outs, not a general accuracy guarantee.


## Enriched-source paired result

Both initial attempts stopped at AssumeRole with ExpiredToken, before inference;
retained `component-fulfillment-novapro-01.json` / `component-fulfillment-nova2-01.json`
show no answer and zero model usage. AWS CLI login was refreshed under
missing20-dev. No IAM policy expansion was needed. The resumed -02 files contain
the actual paid comparisons, sharing history hash98f9537d…717ce and enriched
source hashde7b4f92…ba8ff7.

- NovaPro1551: end_turn,6.908s,15,372 input /728 output tokens. Correctly separates
  SO10 picked13, remaining pick2 and remaining dispatch15; supplier attribution
  is unproved. It does not explicitly restate synthetic physical provenance and
  uses generic “units” rather than the source Nos; retain these rubric omissions.
- Nova24096: end_turn,15.574s,12,568 input /1,806 output tokens. Still wrongly
  gives remaining dispatch2, asserts supplier responsibility and invents five
  held parts despite held0. FAIL / rejected configuration.

Continue with existing NovaPro only for the prospectively frozen read-only UI
hold-outs. This avoids a model migration or production budget increase. The
paired example's omissions are not retroactively marked as a full rubric pass;
full source-candidate acceptance requires independent assessment of the next
real conversation sequence and disclosure of those omissions.


## Real UI hold-outs and scoped acceptance

The actual NovaPro product route reused the original native session on8901 with
the source helper candidate. Snapshots are retained privately as
`component-native-turn4-fulfillment-holdout.json`,
`component-native-turn5-provenance-holdout.json`, and
`component-native-turn6-causality-holdout.json`.

Independent Terra High review verified exact message-prefix continuity8→10→12;
prior failed answers were not erased. Turn4 correctly separated picked,
dispatched and recorded POD at25/25/25 and15/15/15, remaining dispatch0/0.
Turn6 correctly rejected supplier responsibility and the assertion that all18
held parts were defective, asking for packing/custody and physical-test evidence.
Turn5 FAILED: despite correctly rejecting alerts as proof of non-receipt, it
inferred customers “should have received” the goods from synthetic POD and
blurred native accounting with declared physical event records.

The reviewer independently accepts only the pure read-only fulfillment arithmetic
and its source-packet integration. Source facts are verifiably improved; this
scope does not promote a new model or certify full model semantics. Whole
conversation acceptance remains blocked by turn5. Generic units wording and the
paired answer's omitted C2-block/provenance details remain disclosed.

Final focused26 Python tests passed (distributor operations plus native dialogue),
Ruff formatting/lint passed for both source/test files, and the independent code
review confirmed the final consistency guards. No ERP event/write, new model
factory, output-budget change, alternate memory layer or Nova2 promotion occurred.


## Next bounded source-contract check: confirmation evidence basis

The next source candidate attaches the evidence basis to each order's delivery
confirmation quantity. Global provenance alone did not prevent the turn5 error.
`delivery_confirmed` remains a recorded quantity, with an adjacent evidence object
that identifies synthetic/recorded/unspecified events and explicitly leaves
independent physical receipt NOT_VERIFIED. This derives provenance from the
existing synthetic_input source field; it cannot establish new physical facts.
No system-prompt patch, answer rewrite, model upgrade or budget increase.

Freeze one real UI question before the change is executed:
4. Original prompt (Chinese; exact Unicode escapes): `\u201c\u8bf7\u6838\u5bf9\u521a\u624d\u2018\u5ba2\u6237\u5e94\u8be5\u5df2\u7ecf\u6536\u5230\u8d27\u2019\u8fd9\u53e5\u8bdd\uff1a\u5f53\u524d\u6bcf\u5f20\u8ba2\u5355\u7684\u7b7e\u6536\u6570\u91cf\u662f\u4ec0\u4e48\u6027\u8d28\u7684\u8bc1\u636e\uff1f\u80fd\u636e\u6b64\u786e\u8ba4\u771f\u5b9e\u5ba2\u6237\u6536\u8d27\u5417\uff1f\u8bf7\u5206\u522b\u8bf4\u660e\u7cfb\u7edf\u5b8c\u6210\u72b6\u6001\u4e0e\u73b0\u5b9e\u6536\u8d27\u8bc1\u660e\u3002\u201d` English meaning: Check the earlier statement that the customers should have received the goods: what kind of evidence is the signed-for quantity for each order? Can it confirm real customer receipt? Explain system completion and real-world receipt proof separately.
Acceptance requires25/15 recorded synthetic confirmation quantities, no assertion
of real customer receipt, and separation from actual native DN/stock effects.
Retain existing native session, including turn5 failure. One initial paid check;
a failure triggers a fresh design reassessment rather than repeated wording edits.


## Confirmation-basis result and limited acceptance

The real UI turn7 used the same NovaPro model, original session and budgets after
adding per-order confirmation evidence. Private snapshot:
`component-native-turn7-confirmation-basis.json`. The exact turn6 twelve-message
prefix is retained in fourteen messages, including the failed turn5 answer.

The answer correctly explains that recorded confirmation is synthetic, is not
sensor/carrier/customer-receipt evidence and cannot establish real receipt. It
requires independent signed receipt or carrier proof and distinguishes system
completion from physical receipt. It does not repeat the per-order25/15 amounts
or identify native DN/stock effects, so it is not a full prospective-rubric pass.
The independent reviewer grants scoped GO to the source-contract repair and
immediate physical-provenance correction under the user's demo-first boundary.
Turn5 remains FAILED; no general model certification or model migration is made.

Final primary29 focused Python tests and implementation Ruff format/lint passed;
independent code and actual-answer review passed the stated limited scope.
Executed SHA-256:
- `scripts/decision_workspace_server.py`: `73ad9243043465aa869a7aa1cebcab9a38b87a8709df725fb52faacf6a96aa0f`
- `tests/test_distributor_operations.py`: `65d2836ec96572764b27b3ecd90f586442e012c096b4a595e3b9974645654bf8`

Current product stays on NovaPro with its original1551 output cap. Nova2 access
is available but the tested Nova2 configurations are rejected for this case.
The business path, source arithmetic and explicit evidence basis are accepted
separately; broad complex-task accuracy and submission readiness remain open.
