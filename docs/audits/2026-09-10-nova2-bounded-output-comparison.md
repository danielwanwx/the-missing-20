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
1. “请重新核对这两张客户订单：分别已拣、已发、已签收及剩余待发是多少？不要把拣货当成发货。”
2. “那为什么页面还保留三个告警？这能证明客户还没有收到货吗？哪些是实际系统记录，哪些只是演示输入？”
3. “根据目前的记录，可以向供应商断言原来两件短缺一定是他们少装，而且之前隔离的18件全部有缺陷吗？还缺什么证据？”

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
