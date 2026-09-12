# LogisticPilot：收货异常到客户履约的窄市场复核

资料访问日：**2026-09-12**（America/Los_Angeles）。本报告承接 [竞品复核](./2026-09-09-finalization-comparators.md) 与 [行业复核](./2026-09-09-finalization-industry-impact.md)，不评估比赛展示或生产 ROI。产品文档证明功能边界；论坛帖不能证明发生率或付费意愿。

## 结论

可信切口是：**使用 ERPNext、但收货异常仍跨采购、质检、销售分配与协作工具人工拼接的中小型零部件分销商**。买方是运营/供应链负责人；用户是收货主管或采购运营，质量和客户履约人员处理例外。反复任务是区分正常短收、缺件、质量隔离与身份/UOM 冲突，判断受影响客户，审阅方案，授权写入 ERPNext 并读回，再同步协作工具。

前景**有待验证**。大厂与 ERP 已覆盖上游异常和基础交易。可售差异只能是“跨来源判断与可审计执行”：Strands 提议，确定性计划绑定来源版本、数量/UOM、权限和幂等键，ERPNext 执行并读回。应用直接交接 Airtable/Jira，只有 Slack 走 Celigo 单次尝试路由；连接器数量非护城河。[Celigo](https://docs.celigo.com/hc/en-us/articles/226974368-Create-a-connection-to-an-application)

## 直接替代与基线

| 替代方案 | 官方已公开能力 | 对 LogisticPilot 的含义 |
| --- | --- | --- |
| Microsoft Dynamics 365 Procurement Agent | 2026 production-ready preview 会找出未确认/迟交 PO、生成跟催邮件；采购员可确认并应用供应商邮件变更，Impact analysis 评估库存、生产和客户交付。[概览](https://learn.microsoft.com/en-us/dynamics365/supply-chain/procurement/procurement-agent-overview) [跟催](https://learn.microsoft.com/en-us/dynamics365/supply-chain/procurement/procurement-agent-supplier-com-follow-up) | 已占据“供应承诺变化→下游影响”。本项目只能在 ERPNext 场景证明现场证据、质量隔离、授权执行和读回闭环。 |
| SAP Joule + Situation Handling | 缺确认或确认量不足时，SAP 可通知责任采购员；Joule 可创建最多 10 个 PO 的 supplier confirmation。2026 更广 Autonomous SCM 能力分阶段上线，不能都视为已 GA。[Quantity Deficit](https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/8308e6d301d54584a33cd04a9861bc52/ecc316567879bf45e10000000a4450e5.html) [Joule](https://help.sap.com/docs/JOULE/82a14f108cfa4d4788244d81371e072b/6f4949f8f4a5447d9df1c1931f7617be.html) [发布说明](https://news.sap.com/2026/05/more-autonomous-supply-chain/) | 企业替代已有原生语义、权限与采购关系；机会只在较轻量 ERPNext 与异构协作栈。 |
| ERPNext 现有系统基线 | Purchase Receipt 支持接受/拒收仓、批次/序列、强制质检和 Stock Ledger；v15 起可显式启用 SO/Pick List 预留，特定“SO→Material Request→PO→Purchase Receipt”链另可设置到货自动预留；Workflow 支持多级审批。[收货](https://docs.frappe.io/erpnext/purchase-receipt) [质检](https://docs.frappe.io/erpnext/user/manual/en/quality-inspection) [预留](https://docs.frappe.io/erpnext/stock-reservation) [工作流](https://docs.frappe.io/erpnext/workflows) | 现有基线有实施、运维和配置成本，且已承担核心交易。必须证明减少调查和重复录入并保留原生控制。 |
| Odoo 19（SMB 邻近替代） | 收货质量检查可按产品/数量/批次执行，失败量进入 failure location；Allocation report 可把不足的在途量优先分给 SO/MO，分配本身不移动库存。[质检](https://www.odoo.com/documentation/19.0/applications/inventory_and_mrp/quality/quality_management/quality_checks.html) [隔离](https://www.odoo.com/documentation/19.0/applications/inventory_and_mrp/quality/quality_management/failure_locations.html) [分配](https://www.odoo.com/documentation/saas-19.4/applications/inventory_and_mrp/inventory/warehouses_storage/reporting/allocation_report.html) | 表明“质检+分配”并不独特；差异只能是证据编排、安全执行和解释。 |

## 四个公开一手支持案例

这些案例支持“流程缝隙真实存在”，**不支持痛点普遍、严重或值得某个价格**。

1. **2021-09-02，ERPNext 用户：到货 2 件，每件缺组件。** 检验员将两个序列号的 QI 判为 Rejected，但用户无法在不虚假接受 QI 的前提下提交 Purchase Receipt、记录实物已在仓。[原帖](https://discuss.frappe.io/t/quality-inspection-and-purchase-receipt-rejection/79796)
2. **2023-11-15，ERPNext 用户：不合格或缺文件物料需安全隔离。** 用户描述收货后进 rejected warehouse，再由安保转入 secure room；问题解决后还要填写释放依据，并希望限制特定角色进出。[原帖](https://discuss.frappe.io/t/stock-entry-restrict-to-and-show-all-items-in-warehouse/113244)
3. **2021-08-21，分包制造用户：100 件中 96 合格、4 件可返工。** 原生 rejected 语义会让不合格料仍留在外协方，因此团队先全部接收，再手工转到 Not Good Warehouse，并寻求能区分返工与报废、保留正确报表的流程。[原帖](https://discuss.frappe.io/t/how-to-handle-rework-material/79331)
4. **2025-11-12，ERPNext 用户：100 个半成品瓶中 90 接受、10 拒绝。** 用户不知道如何在 QI 中表达部分接受/拒绝，让仓库人员看到数量并分别转入成品与拒收仓。[原帖](https://discuss.frappe.io/t/quality-inspection-accepted-and-rejected/156725)

四帖集中在实物、质量状态、返工/拒收与单据无法自然对齐；没有证明 LogisticPilot 能解决，也没有时间、差错率或经济价值基准。

## ICP、差异与商业障碍

**首批 ICP 假设：** 20–200 人、1–5 个仓点、有批次/序列或 incoming QA 的工业/MRO/电子零部件分销商；ERPNext 是库存权威，质量/工单分散在 Airtable/Jira/Slack；每周重复处理短收、拒收、返工或缺货取舍。排除纯电商、只需条码收货、要求认证 QMS，以及深度使用 D365/SAP 的企业。

**购买理由假设：** 若产品能在不绕过 ERP 权限的情况下减少多人查 PO/PR/QI/SO、转述和重复录入，才可能被购买。早期可做实施型试点或 ERPNext 合作伙伴附加模块；证据不足以定价、计算 TAM 或声称 SaaS 毛利。

**障碍：** 原生 ERP/Odoo 已能处理清楚流程；UOM、批次、仓库、优先级与角色主数据会先出错；质量释放/客户优先级需本地责任人；集成权限、版本、重试增加支持成本；大厂持续下沉异常能力；当前只有合成输入，无生产可靠性或付费证据。

## 9 月 14 日前最有信息量的验证

1. **只验证一个窄案例和一个反例。** 冻结同一 PO/批次/SO：短收或质量 hold 确实造成客户分配冲突；再给一个“正常分批到货、不应升级”的反例。方案必须引用当前 ERPNext/Airtable 证据，且 held stock 永不被分配。
2. **做 3–5 次短访谈/任务走查。** 找 ERPNext 实施商或分销运营，问最近实例、角色、所用系统、重复录入和批准人；记录事实与拒绝理由，不问引导式“你会买吗”。
3. **建立同任务人工基线。** 比较原生 PR/QI/SO reservation/Jira/Slack 与产品，记录人工时间、切换、重录、错误/重复效果和全部重试；小样本只叫可行性测试。
4. **证明边界。** 保存 Strands 建议、编译计划、授权角色、源版本、幂等键、ERPNext ID 与读回；验证相同 case ID 只产生一次 Airtable/Jira 直接交接和一次 Celigo→Slack 尝试。来源不可用就停在 unknown/needs review。
5. **设置发现阶段的停步/重定向触发器。** 若首批 3 名操作者都无近期实例，或原生 ERPNext 已同样清楚，应暂停扩建，扩大访谈或重选问题；这不等于市场无效。若多人给出实例，且零错误/重复下明显少步骤，再约设计伙伴试点。

截止日前避免：扩到通用 WMS/TMS、自动质量释放或客户承诺；把论坛帖当市场规模；用合成订单价值冒充收益；发布 TAM、价格或 ROI；以连接器/Agent 数量作为差异；闭环未稳前新增行业或 ERP。

## 明确未知

- 异常频率、人工耗时、损失、预算与采购周期未知。
- ERPNext+Airtable/Jira/Slack 组合的普及度和 Celigo 部署率未知。
- 四个论坛案例未独立验证，不能外推到当前版本或所有分销商。
- 没有真实仓库图片/扫描、真实客户承诺、生产数据、受控人工对照、稳定模型成功率、部署/支持成本或生产 ROI。
- D365/SAP 2026 功能的具体租户可用性、许可和配置依赖会变化；公开路线图不能替代逐租户验证。
