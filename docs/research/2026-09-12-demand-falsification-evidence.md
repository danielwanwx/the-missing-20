# 收货与履约调查的需求证据及反证

资料访问日：2026-09-12。原帖是自述，职业、经营规模、频率和效果没有独立验证；没有客户访谈、产品试点或因果收益测量。相对发布日期按页面显示保留，不推算精确日期。

## 结论

最直接的任务是：**运营人员需要知道哪些订单现在可以兑现、哪些受阻、还缺哪条证据，以及该由谁处理。** 已找到明确的系统库存与发运准备状态不一致、销售先承诺交期的用户陈述。这比泛称“仓库流程复杂”更具体。

但同一讨论也提出了库存可承诺量、预留、质检门槛和权限流程等常规解决方案。痛点存在不等于需要 LLM。值得验证的 Agent 工作是调查仍有歧义、来源分散或需解释上下文的异常；库存计算和明确规则应继续由原生系统与代码承担。

## 一手证据台账

| 来源与日期 | 当事人描述的任务/摩擦 | 对产品的启发 | 反证、解决办法与不能外推的内容 |
|---|---|---|---|
| [Sales committing stock before warehouse confirmation](https://www.reddit.com/r/logistics/comments/1rcmpev/sales_committing_stock_before_warehouse/)，页面显示 5mo ago | 系统显示可用，现场却已预留、还在处理或未准备发运；仓库反馈时销售已承诺交期 | 直接支持“库存状态到客户承诺”的问题，不只是人为附会客户影响 | 评论提出净可用量、QC/波次状态、预留和承诺权限。一些评论有商业身份，效果未经验证；不能断言需要 Agent 才能解决 |
| [Is anyone actually using AI to help with supply chain stuff?](https://www.reddit.com/r/supplychain/comments/1tm6jwu/is_anyone_actually_using_ai_to_help_with_supply/)，页面显示 3mo ago | 自述零配件商用 Tally，邮件/RFQ/WhatsApp/照片格式不一，人工查库存、客户价格与付款情况，想自动准备后再人工复核 | 支持非结构化输入处理、少重录、保留人复核 | 作者称原流程错误很少，主要是工作量增长；这不是“现有流程错误频出”的证据。最强需求在询价/订单录入，不直接证明我们的收货产品 |
| [How to submit purchase receipt with rejected quality inspection](https://discuss.frappe.io/t/how-to-submit-purchase-receipt-with-rejected-quality-inspection/59840)，2020-03-31 起；2021 年后续 | v12 用户无法把拒检实物正确记入仓；后续有电子板 80 接受、18 返工、2 拒收的问题 | 实物在场、质量处置与记账是不同事实；返工不是简单的接受/拒绝二值 | 2021-10-15 回复已指向可配置允许拒检提交的实现；不能把 v12 报错当作当前未修复问题。评论也提出字段与脚本联动 |
| [Stock Setting “Allow to Make Quality Inspection after Purchase / Delivery”](https://discuss.frappe.io/t/stock-setting-allow-to-make-quality-inspection-after-purchase-delivery-is-totally-unusable/147910)，2025-05-30 | 用户希望进口货先进入账上，再按物料模板进行质检，认为设置未形成完整业务动作 | 说明业务阶段如何衔接仍可能产生困惑 | 单帖无独立复现、无已验证当前版本根因；可能是配置/产品流程问题，而非 AI 推理问题 |
| [Quality Inspection Accepted and Rejected](https://discuss.frappe.io/t/quality-inspection-accepted-and-rejected/156725)，2025-11-12 | 100 瓶中 90 接受、10 拒绝，如何让仓库看到数量并分别处理 | 质量人员与库存人员之间存在信息衔接需求 | 属制造场景；不能直接外推分销商频率或客户损失，也不证明原生库存动作缺失 |
| [Wrongly labelled parts](https://forum.digikey.com/t/wrongly-labelled-parts/20367)，2022-02-24 | 订货后标签与内件不符，再订仍收到同样错误的内件 | 重复同类异常时，应把旧差异证据带入下一批复核；不能只看外标签 | 支持人员要求可读标签/产品照片和订单材料，并建议发货前复核；这证明证据需求，不证明自动视觉可识别所有内件或供应商整体缺陷率上升 |

## 原生能力是公平基线

ERPNext [Stock Settings](https://docs.frappe.io/erpnext/stock-settings) 和 [Purchase Receipt](https://docs.frappe.io/erpnext/purchase-receipt) 已有质检行为、接受/拒收与原生库存规则；[Stock Reservation](https://docs.frappe.io/erpnext/stock-reservation) 提供预留能力。真实用户任务走查应先确认这些功能是否正确配置，而不是把未配置系统作为故意弱化的对照。

Microsoft/Oracle 的具体重叠见 [能力证据](2026-09-12-ms-oracle-capability-evidence.md)。它们拥有客户影响、入库/出库协调和受权限约束的行动能力。公开资料不足以判定我们在同任务中的质量或成本优势。

## 三个候选任务的排序

| 候选任务 | 痛点证据 | Agent 必要性 | 当前项目匹配 | 判断 |
|---|---|---|---|---|
| 收货证据矛盾时，查明可履约客户与需要补充的事实 | 有直接用户陈述和原生控制依据 | 有条件：跨来源语义/上下文存在歧义时；单纯数量计算不需要 | 有 PO20 真实 ERP 历史链，当前可用性和来源时间仍需修复 | **当前首选验证** |
| 杂乱询价/订单材料转为可复核的业务单据 | 零件商自述更直接，保留人工复核意愿清楚 | 非结构化输入较适合 LLM，后续动作仍可规则化 | 不是现有完整主链；新增价格/信用/邮件边界 | 值得赛后访谈，不宜立即再转向 |
| 供应商趋势预警并提前处置受影响订单 | 重复错件案例支持复核，但没有代表性长期数据 | 趋势计算不是 LLM 工作；解释与调查可能适合 | 有观察历史模块，缺供应商批次基线和预测验证 | 保留为同一产品的后续阶段；先做当前风险监测 |

## 最能改变判断的客户验证

招募 ERPNext 实施伙伴或零件分销运营，围绕最近一次真实事件走查：原始输入是什么、分别在哪些系统、哪个事实曾不确定、谁有决定权、原生功能为何不够、哪个人工步骤最耗力。让对方先展示原流程，再展示产品，不先暗示必须使用 AI。

记录全部查找、切换、重新录入、批准、等待和返工；把模型等待与人工主动操作分开。若真实任务只是字段映射或配置缺失，应采用确定性修复。若操作人员需要反复比较不同证据并解释例外，才进一步试验 Agent。

暂停扩大功能的触发条件：第一批访谈没有近期实例，或原生配置同样清楚地完成任务；这需要重新界定问题，不等于以小样本宣布市场不存在。支持继续的证据是可核对的重复实例、允许试用的输入/系统权限、明确负责该任务的人，以及对照中实际减少的工作。当前尚未取得这些证据。
