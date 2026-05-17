---
name: financial-report-analysis
description: 财报分析 Skill v2。用现金流量表和资产负债表交叉验证利润表，按七步链「利润质量/现金流匹配/需求真实性/资本开支/债务与利率敏感性/扩张质量/行业特殊口径」判断公司真实经营质量；输出符合 AI_Renaissance 标准 Signal 的 JSON。触发：财报分析、财务报表、利润质量、现金流验证、合同负债、资本开支、扩张风险、Signal。
owner_group: 专家1组（财务）
domain: financial
status: draft
---

# Financial Report Analysis

## 1. 适用范围

本 Skill 用于把上市公司三张财务报表转化为 AI Renaissance 可消费的财务 Signal。核心目标是判断下一季度净利润同比方向，MVP 指标为 `accuracy@confidence>0.7 >= 70%`。

适用：消费、制造、科技、平台、重资产、医药等非金融企业。地产、建筑、医药必须执行 Step7 行业特殊口径。银行、保险、券商等强金融属性主体暂不适用，默认输出 `direction: neutral` 且 `needs_human_review: true`。

本 Skill 只输出经营质量信号，不输出投资建议，不参与仲裁、仓位、估值或交易判断。

高研发科技公司需先识别业务阶段。半导体 IP、EDA、AI 芯片、创新药、SaaS 等公司如果同时具备高研发投入、营收高增长、合同负债增长、销售收现强、应收未显著跑赢营收等特征，应进入 `rd_commercialization` 口径。该阶段下，亏损和经营现金流为负不自动构成 `high` 红旗，应先判断是否属于研发投入向订单兑现过渡期。

## 2. 输入材料

必填输入：

| 字段 | 要求 |
|---|---|
| `company_name` | 公司名称 |
| `ticker` | 股票代码，可为空但需说明原因 |
| `period` | 报告期，如 `2026Q1` |
| `income_statement` | 利润表核心字段 |
| `balance_sheet` | 资产负债表核心字段 |
| `cash_flow_statement` | 现金流量表核心字段 |
| `source_id` | 数据来源标识，由 `data_sources/` 提供 |
| `base_period` | 同比或环比对照期 |

可选输入：同行对比、公告、研报、产业链数据、历史多期财务数据。

缺失处理：

- 三表任一缺失：输出 `direction: neutral`，`confidence <= 0.4`，`needs_human_review: true`。
- 关键字段缺失：对应步骤状态为 `unknown`，不得用行业常识或推测补数。
- 数据口径冲突：优先使用公告原文或数据组封装字段，并在 `meta.evidence` 标记冲突来源。

## 3. 分析步骤

先做 Step0 红色预警扫描，再按七步链顺序分析。详细公式、阈值和行业适配见 `references/`。

| 步骤 | 名称 | 目标 |
|---|---|---|
| Step0 | 红色预警扫描 | 先排除财务重述、收入确认变更、商誉风险、资金占用等硬风险 |
| Step1 | 利润质量 | 判断利润是否被现金支撑 |
| Step2 | 现金流匹配 | 验证销售收现、采购付现与利润表是否匹配 |
| Step3 | 需求真实性 | 用应收、存货、合同负债验证需求是否真实 |
| Step4 | 资本开支 | 判断扩产是否有真金白银投入 |
| Step5 | 债务与利率敏感性 | 检查净债务、短债结构和财务费用侵蚀 |
| Step6 | 扩张质量 | 判断资产扩张是否有订单和产能消化支撑 |
| Step7 | 行业特殊口径 | 按行业调整阈值和特殊会计处理 |

闭环判断：订单真实 -> 现金先回来 -> 应收不恶化 -> 存货/在建抬升 -> 资本开支放量 -> 债务可承受 -> 行业口径可解释。

## 4. 判断规则

`direction` 由七步状态和红色预警共同决定：

| 条件 | 输出 |
|---|---|
| 七步全部通过且 Step0 无红色预警 | `bullish`，通常 `risk_level: low` |
| 七步通过 5 项以上且核心预警不超过 2 项 | `neutral` 或弱 `bullish` |
| 七步通过不超过 3 项，或触发财务重述/收入确认变更/商誉重大减值风险 | `bearish`，`risk_level: high`，`needs_human_review: true` |
| 关键数据不足 | `neutral`，`confidence <= 0.4`，`needs_human_review: true` |

红旗项必须分层：

- 硬红旗：财务重述、收入确认重大变化、审计意见异常、资金占用、商誉重大减值、现金流断裂、短债压力明显大于现金安全垫等，保持 `high`。
- 阶段性红旗：高研发商业化过渡期的亏损、经营现金流为负、营业利润为负且财务费用为正，默认标为 `medium/watch`，除非收入、合同负债、收现、应收和现金安全垫同步恶化。
- 科技公司专用红旗：研发费用率高但收入无增长、研发费用增长显著快于收入增长、合同负债增长但收现未跟上、应收显著跑赢营收、毛利率恶化、经营现金流持续为负且现金安全垫不足。

`confidence` 必须按 `references/confidence_rules.md` 从 evidence 数量、独立性、一致性、数据可靠性反推，不允许凭直觉填写。最终 confidence 取「七步链结论强度」与「证据强度反推值」的较低者。

## 5. 标准输出

只输出 Signal JSON，不输出 Markdown 报告。顶层字段应与 `agents.signal.Signal` 对齐，证据放入 `meta`。

```json
{
  "direction": "neutral",
  "confidence": 0.62,
  "reasoning": "利润增长有现金支撑，但合同负债下滑，未来需求真实性需继续验证。",
  "signals": ["现金利润比达标", "合同负债增速弱于营收"],
  "source": "financial-report-analysis",
  "signal_type": "financial",
  "stock_code": "SZ000000",
  "weight": 1.0,
  "meta": {
    "output_version": "0.1",
    "skill_name": "financial-report-analysis",
    "owner_group": "专家1组（财务）",
    "target": "SZ000000",
    "period": "2026Q1",
    "time_horizon": "short",
    "risk_level": "medium",
    "company_name": "样例公司",
    "step_results": {},
    "red_flags": [],
    "key_findings": [],
    "evidence": [],
    "risk_notes": [],
    "uncertainties": [],
    "needs_human_review": false
  }
}
```

## 6. 质量检查

提交前必须回答三问：

1. 数据从哪来：每个关键数字是否有 `source_type/source_name/date/metric/value/comparison`。
2. 结论怎么来：每个方向判断是否能追溯到七步链步骤和阈值。
3. 系统能不能用：输出是否为可解析 JSON，顶层字段是否与 `agents.signal.Signal` 对齐，缺失数据是否降置信并在 `meta.needs_human_review` 触发人工复核。

自检清单：

- frontmatter 含 `name/description/owner_group/domain/status`。
- 6 节结构齐全。
- 不输出投资建议。
- `confidence` 来源于证据强度反推。
- 二手来源不作为核心证据，除非有官方来源交叉验证。
- 字段映射与 `data_sources/` 责任边界分离，未确认字段保留 TODO。
