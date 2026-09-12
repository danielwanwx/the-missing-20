# Microsoft / Oracle：与 LogisticPilot 重叠到什么程度

访问日：2026-09-12（Pacific）。范围：官方产品文档与版本发布说明；未登录竞品租户实测，未测其准确率、时延或实施成本。本报告补充[窄市场复核](./2026-09-12-logisticpilot-market-review.md)，不把未找到的能力当作不存在。

## 判断

**大企业已经在做，而且比“供应商邮件助手”更接近我们的完整故事。** Oracle 已公开收货、入库异常、库存短缺、需求预留、跨环节工作台和审批后执行；Microsoft 已公开供应商变更到具体客户订单影响的闭环。只说“Agent 主动发现问题、串联系统、人批准”无法建立原创性。

我们可争取的是：**为一个明确使用 ERPNext 的零部件分销团队，把现场记录与系统记录的矛盾调查清楚，在质量与客户承诺约束下完成一次可验证的处理。** 这是目标用户和验证深度的切口，不是已证明的技术护城河、低价优势或大厂能力空白。

## 已有能力与可用性证据

状态口径：Microsoft 下列采购 Agent 明确为 **production-ready preview**，不称 GA；其传统库存质检是现有产品能力。Oracle 表中版本号表示对应季度更新已有详细功能、启用和权限文档，强于新闻宣布，但**本文没有逐租户验证 GA、地区、许可或默认开通情况**。Oracle 滚动目录已包含 26D，本报告不将该版本视为当前可用事实。[Oracle 功能版本目录](https://docs.oracle.com/en/cloud/saas/fusion-ai/aiafl/ai-scm.html)

| 产品 / 版本状态 | 官方文档实际承诺 | 对本项目的竞争含义与边界 |
| --- | --- | --- |
| D365 Procurement Agent；2026-08-10 文档，production-ready preview | 接收、分类供应商邮件，识别确认与变更，采购员确认后更新 PO；联合评估库存、生产和客户交付影响。[概览](https://learn.microsoft.com/en-us/dynamics365/supply-chain/procurement/procurement-agent-overview) | “模型解释、系统记录、人决定”也不是我们独有。租户需要启用和配置，不能把 preview 写成普遍已部署。 |
| D365 PO 跟催；production-ready preview | 查找未确认或迟交 PO 并生成邮件；可以配置自动发送。[跟催配置](https://learn.microsoft.com/en-us/dynamics365/supply-chain/procurement/procurement-agent-supplier-com-follow-up) | “主动”本身没有差异；要证明发现了人工基线没及时处理的具体问题。 |
| D365 Impact analysis；2026-08-24 文档，production-ready preview | 列出受影响销售、生产、转移等订单，按 planning pegging / marking 追溯；展示接受变更前后库存。接受变更后仍需重跑 planning 才形成新正式计划。[影响详情](https://learn.microsoft.com/en-us/dynamics365/supply-chain/procurement/procurement-agent-impact-analysis-review-changes) | 已能回答“短供影响哪些客户”；不能声称只有我们把上游异常连接到下游。可借鉴：清楚区分预测与已执行事实。 |
| D365 Inventory blocking；2025-08-14 现有功能文档 | 抽样质检和被阻止库存可以是不同数量；配置 Full blocking 后，少量抽检也能阻止整条 PO 数量。[库存阻止](https://learn.microsoft.com/en-us/dynamics365/supply-chain/inventory/inventory-blocking) | “抽样一件失败不能自动当作整批数量失败”是正确领域建模，但质检隔离不是新功能。 |
| Oracle Receipt Creation Assistant；26A 功能文档 | 从粘贴的交付信息创建 PO、转移、ASN、RMA 等收货，支持批次/序列，成功后显示单据与行信息并可进入交易历史；需要对应业务权限。[收货助手](https://docs.oracle.com/en/cloud/saas/readiness/scm/26a/inv26a/26A-inventory-wn-f41429.htm) | OCR/邮件提取加写入单据不能独立成为获奖理由；创建记录也不证明实物准确。 |
| Oracle Inventory Shortages Assistant；26B 功能文档 | 评估现有入库、替代品、跨库与跨组织转移，最后才采购申请；批准后执行。目前不能从推荐列表中逐项选择批准。[短缺助手](https://docs.oracle.com/en/cloud/saas/readiness/scm/26b/inv26b/26B-inventory-wn-f43055.htm) | “先找内部办法，再采购，批准后行动”已有。列表批准限制是该版本的具体边界，不代表整个 Oracle 无细粒度审批。 |
| Oracle Warehouse Operations Workspace；26B 功能文档 | 统一 stock / inbound / outbound / workforce：识别迟到和短供、处理供应商邮件、更新 PO、对齐收货与出库需求、重分配与替代方案；受组织权限和审批约束。功能开关默认 No。[仓库工作台](https://docs.oracle.com/en/cloud/saas/readiness/scm/26b/inv26b/26B-inventory-wn-f43846.htm) | **最强直接反证**：大厂已经把多个业务环节放进一个能建议、能行动的界面。我们的来源图和连接器数量不能替代任务效果。 |
| Oracle Inventory Reservation Assistant；26C 功能文档 | 主动找临近交期未完全预留、预留到迟到货源的需求，可查看、更新、删除和转移预留。该 workflow agent 每次独立处理，不保留上一请求对话信息。[主动预留](https://docs.oracle.com/en/cloud/saas/readiness/scm/26c/inv26c/26C-inventory-wn-f46475.htm) | 可研究“持续同一异常上下文”的价值；不能据此宣称所有 Oracle Agent 无记忆，也不能把我们保存聊天当作成熟案件管理。 |
| Oracle Inbound Goods Advisor；26C 功能文档 | 定时或按需匹配到货/预计到货与需求、创建 cross-dock 预留和上架建议；损坏货可由有权限的人排除。部分到货会移除 planned cross-dock 建议，且部分文档/需求类型不支持。[入库助手](https://docs.oracle.com/en/cloud/saas/readiness/scm/26c/inv26c/26C-inventory-wn-f46496.htm) | “入库直接连履约”也不是空白。具体部分到货边界可作为研究题，不能直接推导我方已优于 Oracle。 |
| Oracle Quality Inspection Standards Advisor；25C 功能文档 | 检索用户提供的质量标准，辅助抽样/检验计划；表格图片可能解释不准，要求人核对关键建议与原文。[质量标准助手](https://docs.oracle.com/en/cloud/saas/readiness/scm/25c/mfg25c/25C-mfg-wn-f39393.htm) | 仅按本工具定位，它不是收货异常执行器；但不能由此断言 Oracle 无质量工作流。诚实解释抽样与实际隔离数量是共同必需。 |
| Oracle AI Agent Studio External REST；26B 文档 | Agent 可连内部/外部 SaaS 与公共 API，配置鉴权、HTTP 操作，并可要求工具运行前人工审批。[外部 REST 工具](https://docs.oracle.com/en/cloud/saas/fusion-ai/26b/aiaas/add-external-rest-tool.html) | **不能说大厂只能读自己的 ERP、不能跨系统。** 我方目前只验证特定连接组合，尚未证明跨供应商可移植性。 |

## 评委最强的反问，以及可成立的回答

**反问：** Oracle 工作台已经处理短供、分配、审批，Agent Studio 能接外部 API；Microsoft 也有客户影响分析。你们是否只是把现成范式换成 ERPNext，再加几个漂亮按钮？

**应答必须有条件：** “我们没有发明库存管理。我们选择的是现有 ERPNext 团队仍要人工调查的一类现场异常：到货数量、包装/UOM、质检结论和客户分配记录互相矛盾。我们展示 Agent 如何查证，什么情况下必须停下，批准的是哪一版、哪一个数量的动作，以及系统是否真的完成。这个闭环是否更省事，要用同一任务的原生操作作为对照。”

没有这个对照，只能说是有工程实践价值的原型，不能说具备已验证的购买理由。已有大厂并不使方向自动失效，也不自动证明这里仍有未满足市场。

旧设计里“限制异常影响范围，让健康部分继续履约”值得保留为具体案例的验证目标。Oracle 的预留调整、排除损坏货和入库/出库协调与其重叠；**本文未核实竞品对我方同一组合案例的实际结果，因此不能宣称这种部分继续能力是行业首创，或套件只能全单停摆。** 更有说服力的演示是：指出哪批、哪份证据被隔离，说明哪些客户份额仍可执行，并展示最终数量守恒与执行读回。

## 应拿什么赢，怎样证伪

1. **异常分辨准确性。** 同一套核心处理正常分批到货、实际短收、数量到齐但质量 hold、UOM/身份冲突四类输入；逐例记录正确升级、错误升级、遗漏与 unknown。正常分批应允许不升级，未知不得变成确定结论。
2. **证据与行动一致性。** 实测留存资料不会被称为实时；源版本变化后旧批准失效；held stock 不进入可发数量；重复请求不会产生重复写入；外部系统失效时各目标状态不被一概写成成功。
3. **人实际少做什么。** 和原生 ERPNext 加现有协作工具比较同一案例的查找次数、系统切换、重新录入、总耗时与返工，计入模型等待和所有重试。没有竞品租户实测就不发表“比 Oracle 快多少”。
4. **第二场景复用成本。** 改 PO/批次/客户政策与证据数据即可完成第二个相邻案例，而无需重写编排；报告新增配置、代码、测试及人工映射量。先证明短收→质量隔离的迁移，不能由一个案例宣称通用供应链平台。

## 可借鉴的产品表达

- 首页先呈现异常、受影响需求、来源时间和下一次人类决定；证据图与工具轨迹作为展开详情。Oracle 的工作台本身已证明“统一页面”不是原创点，需靠场景清楚和事实边界赢得信任。
- 把建议、批准、写入、读回、实物确认分别显示。借鉴 Microsoft 对模拟影响与正式计划的区分，避免“系统已发运”写成“客户已收到”。
- 缩小承诺：首个支持的 ERP、单据与质量政策必须列明。低成本、即装即用、厂商中立、任意行业适用都留待实测。

商业未知仍包括：这种异常出现频率、ERPNext 目标群中协作工具组合普及度、谁有预算、定制/运维成本。公开功能文档不回答这些问题，需要真实操作者的近期任务与设计伙伴验证。
