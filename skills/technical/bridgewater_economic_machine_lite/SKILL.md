---
name: bridgewater_economic_machine_lite
description: 专家2组（指标）认领的桥水经济机器轻量化周期判断 Skill，基于增长、通胀、信用、政策、债务周期与四象限框架，输出标准 technical Signal JSON、趋势/周期倾向、风险提示与复查结果。
owner_group: 专家2组（指标）
domain: technical
status: draft
agent_created: true
version: 0.3.1-agent-only-task-aligned
---

# bridgewater_economic_machine_lite


## 0. 任务覆盖说明

本 Skill 对应“桥水（宏观逻辑的数学化与系统化）经济机器模型”任务，覆盖三条主线：

| 任务要求 | 本 Skill 覆盖方式 | 输出位置 |
|---|---|---|
| 1. 全天候策略与纯粹阿尔法策略的具体操作流程 | 将 All Weather 定义为资产配置防御层，将 Pure Alpha 定义为低相关主动判断层，但仅输出规则化判断和风控边界，不输出交易指令 | `meta.bridgewater_layers`、普通人报告、资产配置防御塔 |
| 2. 经济机器模型投资决策步骤、输入指标、模拟推演、四象限判断 | 用生产率趋势、增长、通胀、信用、政策、债务周期、市场定价与外部冲击构建宏观仪表盘，并输出四象限、债务周期、政策反应与情景矩阵 | `meta.scores`、`meta.macro_quadrant`、`meta.signal_details` |
| 3. 普通投资者防御塔、债务周期判断、个人财务原则 | 输出资产配置倾向、现金/杠杆/再平衡/风险暴露检查，不代替投资决策 | `meta.asset_allocation_tilt`、`meta.personal_finance_guardrails`、`risk_notes` |

边界：本 Skill 是判断与报告 Skill，不是数据抓取 Skill、交易执行 Skill 或投资顾问。若上游没有提供数据，本 Skill 只能输出低置信度、中性方向和人工复核要求。

## 1. Skill 定位

本 Skill 是“桥水经济机器模型”的普通投资者简化版，用于在**已有宏观数据输入**的基础上，判断当前宏观环境、债务周期位置和普通投资者的资产配置防御倾向。

本 Skill 只负责：

1. 读取用户或上游模块提供的宏观指标。
2. 判断增长、通胀、信用、政策、债务压力方向。
3. 定位增长 × 通胀四象限。
4. 判断短期债务周期与长期债务压力状态。
5. 输出标准 Signal JSON。
6. 输出普通人能理解的全天候防御塔建议。
7. 执行三次复查：数据完整性、计算一致性、结论安全性。

本 Skill 不负责：

1. 不寻找、抓取或指定外部数据源。
2. 不维护 API、数据源 registry 或抓数脚本。
3. 不执行真实交易。
4. 不登录券商账户。
5. 不读取用户隐私资产账户。
6. 不输出个股买卖点。
7. 不承诺收益，不替代投资顾问。

> 数据来源由用户、上游 data skill、研究员或系统数据层提供。本 Skill 只要求输入数据必须包含必要的指标值、日期、口径说明和来源说明；若缺失，则降置信度并触发人工复核。

---

## 2. 适用场景

当用户提出以下问题时，可以调用本 Skill：

- 当前宏观环境处于什么象限？
- 现在更像复苏、过热、衰退，还是滞胀？
- 如何用桥水经济机器模型判断市场环境？
- 当前短期债务周期处于什么阶段？
- 当前长期债务压力是否偏高？
- 普通人如何做全天候资产配置防御？
- 当前组合更怕通胀、衰退、加息，还是信用收缩？
- 帮我做一份宏观四象限报告。
- 帮我做一次全天候组合体检。

不适用场景：

- 单只股票基本面分析。
- 精确短线择时。
- 指数点位预测。
- 个股买入/卖出建议。
- 杠杆交易建议。
- 用户要求直接代替其做投资决策。

---

## 3. 输入要求

### 3.1 标准输入对象

输入可以是自然语言、表格、JSON 或上游模块传入的结构化指标。若条件允许，优先使用以下 JSON Schema：

```json
{
  "target": "US | CN | EU | JP | GLOBAL | other",
  "period": "YYYY-MM | YYYY-Qn | custom",
  "time_horizon": "short | mid | long",
  "data_mode": "user_provided | upstream_provided | mixed",
  "indicators": {
    "growth": [
      {
        "name": "PMI / GDP / industrial_production / employment / retail_sales / earnings_revision / yield_curve",
        "value": "number or text",
        "direction": "up | down | flat | unknown",
        "trend_3m": "up | down | flat | unknown",
        "trend_6m": "up | down | flat | unknown",
        "comparison": "above_baseline | below_baseline | near_baseline | unknown",
        "date": "YYYY-MM-DD or YYYY-MM",
        "source": "source name or user provided",
        "source_type": "macro_data | market_data | research_report | expert_input | unknown",
        "note": "口径说明，可空"
      }
    ],
    "inflation": [],
    "credit": [],
    "policy": [],
    "debt_cycle": [],
    "market_pricing": [],
    "productivity_trend": [],
    "external_shock": []
  },
  "portfolio_context": {
    "risk_profile": "conservative | balanced | aggressive | unknown",
    "liquidity_need": "high | medium | low | unknown",
    "current_exposure": "optional description",
    "emergency_cash_months": "number | unknown",
    "leverage_level": "low | medium | high | unknown",
    "known_liabilities_1y_3y": "optional description"
  }
}
```

### 3.2 最低可用输入

若无法提供完整 JSON，至少需要：

1. 分析对象：国家/区域/全球。
2. 分析时间窗口：月份、季度或当前。
3. 增长方向证据：PMI、GDP、就业、工业生产、零售销售、盈利修正等任一组合。
4. 通胀方向证据：CPI、核心 CPI/PCE、工资、商品、通胀预期等任一组合。
5. 信用/政策证据：利率、实际利率、信用利差、金融条件、央行表态、收益率曲线等任一组合。

若关键输入不足，仍可输出，但必须：

- `direction = "neutral"`
- `confidence <= 0.4`
- `meta.needs_human_review = true`
- 在 `meta.uncertainties` 写明缺什么。

---

## 4. 指标模块

### 4.0 生产率趋势模块 productivity_trend

用于体现经济机器模型中“长期真正增长来源”的慢变量。该模块不用于短线择时，只用于修正长期资产回报假设与长期债务周期判断。

常用证据：

- 全要素生产率或劳动生产率趋势。
- 研发投入、自动化、AI 应用、资本开支。
- 劳动参与率、人口结构、教育与技能供给。
- 制度与资本市场效率、财政纪律。
- 企业 ROIC、利润率、现金流质量等长期盈利能力证据。

判断方式：

- 生产率改善：长期增长韧性更强，长期债务压力可被部分缓冲。
- 生产率恶化：长期增长天花板下降，债务可持续性压力上升。
- 数据不足：不影响短期四象限判断，但必须写入 `uncertainties`。

### 4.1 增长模块 growth

用于判断经济增长是上行、下行还是不清晰。

常用证据：

- PMI / 新订单
- 实际 GDP 增速
- 工业生产
- 零售销售
- 就业 / 失业率
- 企业盈利修正
- 收益率曲线
- 金融条件

判断方向：

- 多数指标改善：增长上行。
- 多数指标恶化：增长下行。
- 指标接近临界值或方向冲突：增长不清晰。

### 4.2 通胀模块 inflation

用于判断通胀压力是上行、下行还是不清晰。

常用证据：

- CPI / 核心 CPI
- PCE / 核心 PCE
- 工资增速
- 油价 / 大宗商品
- 租金 / 服务价格
- 市场通胀预期

判断方向：

- 多数指标升温：通胀上行。
- 多数指标降温：通胀下行。
- 官方通胀与市场通胀预期明显背离：信号冲突，需人工复核。

### 4.3 信用模块 credit

用于判断信用环境是宽松、紧张还是不清晰。

常用证据：

- 信用利差
- 金融条件指数
- 贷款/社融/信用脉冲
- 违约率
- 银行放贷标准
- 家庭/企业偿债压力

判断方向：

- 信用利差收窄、贷款扩张、金融条件宽松：信用偏松。
- 信用利差扩大、贷款收缩、违约风险上升：信用偏紧。
- 仅有单一指标可用：禁止强判断。

### 4.4 政策模块 policy

用于判断政策环境是宽松、收紧、中性还是受约束。

常用证据：

- 政策利率
- 实际利率
- 央行资产负债表或流动性表述
- 央行会议声明
- 财政刺激/财政收缩
- 收益率曲线

判断方向：

- 降息、扩表、财政扩张、实际利率下降：政策偏宽。
- 加息、缩表、财政收缩、实际利率上升：政策偏紧。
- 增长弱但通胀高：政策受约束。

### 4.5 债务周期模块 debt_cycle

用于判断短期债务周期阶段和长期债务压力。

常用证据：

- 总债务/GDP
- 政府利息支出压力
- 家庭/企业偿债压力
- 实际利率
- 信用利差
- 央行是否被迫宽松
- 货币购买力/汇率/黄金等压力信号

判断方向：

- 债务低、信用扩张、偿债压力低：债务压力低。
- 债务高、利率高、信用收缩：债务压力上升。
- 债务高且政策被迫宽松、货币信任下降：长期债务周期风险高，必须人工复核。

### 4.6 市场定价与外部冲击模块 market_pricing / external_shock

用于判断资产价格是否已经提前反映宏观变化，以及是否存在地缘、能源、供应链、贸易政策、汇率压力等非线性冲击。

常用证据：

- 债券收益率、收益率曲线、实际利率、期限溢价。
- 美元、黄金、大宗商品、铜金比、商品期限结构。
- 股债风险溢价、信用利差、波动率。
- 能源、地缘、供应链、贸易政策、汇率管制等外部冲击。

处理规则：

- 市场定价证据只用于修正 `confidence`、`risk_level` 和资产倾向，不单独决定四象限。
- 外部冲击若会改变通胀或信用路径，必须写入 `risk_notes`。
- 若宏观数据与市场定价明显背离，必须标记 `mixed_boundary` 或降低置信度。

---

## 5. 特征处理与评分规则

### 5.1 基础评分

每个指标先转成方向分：

| 条件 | 分数 |
|---|---:|
| 明确改善 / 上行 / 宽松 | +1 |
| 明确恶化 / 下行 / 收紧 | -1 |
| 持平 / 临界 / 不明确 | 0 |
| 缺失 | 不计分，并写入 uncertainties |

注意：不同模块的“好坏方向”不同。

- 增长：上行为正，下行为负。
- 通胀：上行为正，下行为负。
- 信用：宽松为负，紧张为正。
- 政策：宽松为负，收紧为正。
- 债务压力：压力低为负，压力高为正。

### 5.2 模块分数

每个模块使用可用指标的平均分，得到：

```text
growth_score
inflation_score
credit_score
policy_score
debt_pressure_score
```

若有上游量化模块提供 `zscore`、`momentum`、`surprise` 或加权分数，可以优先使用上游分数；但本 Skill 不自行抓取或计算外部时间序列。

### 5.3 判断阈值

| 分数范围 | 解释 |
|---|---|
| `score > 0.15` | 上行 / 偏紧 / 压力上升 |
| `score < -0.15` | 下行 / 偏松 / 压力下降 |
| `-0.15 <= score <= 0.15` | 中性 / 不清晰 |

若某模块可用指标少于 2 个，或覆盖率低于 60%，该模块 `allow_strong_judgment = false`。

### 5.4 冲突处理

以下情况禁止强结论：

- 增长指标一半改善、一半恶化。
- 通胀官方数据与市场预期明显冲突。
- 信用模块只有单一指标支撑。
- 债务周期缺少债务负担或偿债压力证据。
- 政策表态与实际利率/流动性方向相反。
- 当前处于周期拐点，多个模块分数接近 0。

冲突时：

- `direction = "neutral"`
- `confidence` 下调。
- `meta.needs_human_review = true`
- `reasoning` 必须写明“信号冲突/数据不足”。

### 5.5 桥水式决策流程映射

本 Skill 采用以下顺序生成结论，避免“单指标直接推出资产建议”：

1. 建立宏观仪表盘：汇总生产率、增长、通胀、信用、政策、债务周期、市场定价与外部冲击。
2. 判断周期位置：先判断短期债务周期，再判断长期债务压力。
3. 判断增长与通胀方向：形成四象限定位。
4. 推演政策反应：判断宽松、收紧、中性或政策两难。
5. 构建情景矩阵：评估股票、债券、现金、黄金/商品、信用债在四象限中的相对风险。
6. 输出资产配置防御倾向：只输出类别倾向，不输出具体交易。
7. 复查不确定性：数据不足、信号冲突或长期债务周期风险高时，必须降置信度。

---

## 6. 四象限判断

用增长方向与通胀方向定位宏观象限：

| 象限 | 增长 | 通胀 | 解释 | 常见资产倾向 |
|---|---|---|---|---|
| Q1 Goldilocks | 上行 | 下行 | 经济变好，通胀降温 | 权益、信用资产相对友好 |
| Q2 Reflation / Overheating | 上行 | 上行 | 经济强，但物价也升 | 商品、资源、价值/周期资产相对受益，但估值资产承压 |
| Q3 Stagflation | 下行 | 上行 | 经济变差，通胀仍高 | 现金、黄金、商品、通胀资产重要；股债可能同时承压 |
| Q4 Recession / Disinflation | 下行 | 下行 | 经济和通胀都下降 | 高质量债券、现金、防御资产更重要 |
| Mixed / Boundary | 不清晰 | 不清晰 | 信号混合或处于切换期 | 保持中性，提高现金和复核频率 |

若增长或通胀任一模块 `allow_strong_judgment = false`，四象限必须标注为低置信度或边界状态。

---

## 7. 债务周期判断

### 7.1 短期债务周期

| 阶段 | 判断条件 |
|---|---|
| recovery | 增长上行 + 信用偏松 + 政策不紧 |
| overheating | 增长上行 + 通胀上行 + 政策偏紧 |
| tightening | 增长下行 + 政策偏紧 + 信用偏紧 |
| recession | 增长下行 + 通胀下行 + 信用偏紧 |
| transition | 其他混合状态或信号不足 |

### 7.2 长期债务压力

| 阶段 | 判断条件 |
|---|---|
| low_debt_expansion | 债务压力低 + 信用扩张 + 政策空间充足 |
| high_debt_boom | 债务压力上升但增长仍强 |
| debt_pressure | 债务压力高 + 信用偏紧 |
| deleveraging_or_monetary_reset | 债务压力高 + 政策被迫宽松 + 货币信任压力上升 |
| unclear | 数据不足或信号冲突 |

一旦判断为 `deleveraging_or_monetary_reset`，必须：

- `risk_level = "high"`
- `meta.needs_human_review = true`
- 输出不能给出强进攻建议。

---

## 8. 资产配置防御塔输出规则

本 Skill 只能输出资产类别倾向，不输出具体买卖指令。

允许输出：

- 权益资产：overweight / neutral / underweight
- 高质量债券：overweight / neutral / underweight
- 现金/短债：overweight / neutral / underweight
- 黄金/商品：overweight / neutral / underweight
- 通胀挂钩资产：overweight / neutral / underweight
- 信用债：overweight / neutral / underweight
- 组合应提高分散度、降低杠杆或提高现金缓冲。

禁止输出：

- 买入某只股票。
- 卖出某只股票。
- 满仓某类资产。
- 预测具体点位。
- 保证收益。
- 代替用户做最终投资决策。

### 8.1 象限到资产倾向的基础映射

| 象限 | 权益 | 高质量债券 | 现金/短债 | 黄金/商品 | 信用债 |
|---|---|---|---|---|---|
| Q1 | slight_overweight | neutral | slight_underweight | neutral | slight_overweight |
| Q2 | neutral | underweight | neutral | overweight | neutral |
| Q3 | underweight | underweight_or_neutral | overweight | overweight | underweight |
| Q4 | underweight | overweight | overweight | neutral | underweight |
| Mixed | neutral | neutral | overweight | neutral | neutral |

若置信度低于 0.4，所有进攻性 overweight 必须降为 neutral 或 slight_overweight，并说明不适合据此大幅调仓。

### 8.2 全天候策略与纯粹阿尔法策略边界

本 Skill 对两类桥水思想做不同处理：

**All Weather / 全天候防御层**

- 目标：让普通投资者不要过度暴露于单一宏观天气。
- 操作：根据四象限与债务周期输出资产类别倾向，例如权益、高质量债券、现金/短债、黄金/商品、通胀挂钩资产、信用债。
- 复查：检查组合是否过度依赖增长上行、通胀下行、利率下降或信用扩张。
- 禁止：不允许输出“满仓某类资产”或“确定性调仓”。

**Pure Alpha / 纯粹阿尔法判断层**

- 目标：把主动判断拆成小规则、小仓位、低相关假设，而不是形成单一方向赌博。
- 本 Skill 只允许输出：宏观假设、证据、风险点、置信度、需复核事项。
- 本 Skill 不允许输出：做多/做空具体品种、杠杆比例、期货/期权交易指令。
- 若用户要求主动交易建议，必须转为“假设清单 + 风险约束 + 需要进一步验证的数据”。

### 8.3 个人财务原则输出

普通投资者报告必须包含以下防误用原则，尤其在低置信度、滞胀、去杠杆或长期债务压力高时：

1. 先活下来，再追求收益：避免一次错误毁掉本金。
2. 现金流安全优先：未来 6–12 个月生活现金和 1–3 年确定支出不应暴露于高波动资产。
3. 控制杠杆：不让融资成本、保证金或固定支出决定卖出时点。
4. 规则化决策：每个宏观判断必须写明支持证据、反证指标和最大可承受损失。
5. 分散看相关性：不要把多个同周期资产误认为分散。
6. 定期再平衡：上涨后风险贡献变大的资产要复查，逻辑坏掉的资产不能用“再平衡”掩盖。
7. 四象限不是短线信号：本 Skill 只辅助资产配置和风险识别。

---

## 9. 标准输出 Signal JSON

每次必须输出符合项目 `agents.signal.Signal` 的标准 JSON。顶层字段不得替换为调试结构。

```json
{
  "direction": "bullish | bearish | neutral",
  "confidence": 0.0,
  "reasoning": "一句话说明当前象限、债务周期、主要证据和降置信度原因。",
  "signals": [
    "quadrant_position: Q1_goldilocks | Q2_reflation_overheating | Q3_stagflation | Q4_recession_disinflation | mixed_boundary",
    "short_debt_cycle: recovery | overheating | tightening | recession | transition",
    "long_debt_pressure: low_debt_expansion | high_debt_boom | debt_pressure | deleveraging_or_monetary_reset | unclear"
  ],
  "source": "bridgewater_economic_machine_lite",
  "signal_type": "technical",
  "stock_code": "",
  "weight": 1.0,
  "meta": {
    "output_version": "0.1",
    "skill_version": "0.3.1-agent-only-task-aligned",
    "skill_name": "bridgewater_economic_machine_lite",
    "owner_group": "专家2组（指标）",
    "target": "US | CN | EU | JP | GLOBAL | other",
    "period": "YYYY-MM | YYYY-Qn | current",
    "time_horizon": "mid",
    "risk_level": "low | medium | high",
    "confidence_label": "高 | 中 | 低",
    "macro_quadrant": "Q1_goldilocks | Q2_reflation_overheating | Q3_stagflation | Q4_recession_disinflation | mixed_boundary",
    "scores": {
      "growth_score": 0.0,
      "inflation_score": 0.0,
      "credit_score": 0.0,
      "policy_score": 0.0,
      "debt_pressure_score": 0.0
    },
    "asset_allocation_tilt": {
      "equities": "overweight | slight_overweight | neutral | slight_underweight | underweight",
      "high_quality_bonds": "overweight | slight_overweight | neutral | slight_underweight | underweight",
      "cash_short_bonds": "overweight | slight_overweight | neutral | slight_underweight | underweight",
      "gold_commodities": "overweight | slight_overweight | neutral | slight_underweight | underweight",
      "inflation_linked": "overweight | slight_overweight | neutral | slight_underweight | underweight",
      "credit_bonds": "overweight | slight_overweight | neutral | slight_underweight | underweight"
    },
    "key_findings": [],
    "evidence": [
      {
        "source_type": "macro_data | market_data | research_report | expert_input",
        "source_name": "用户/上游模块提供的来源说明",
        "date": "日期",
        "metric": "指标名称",
        "value": "数值或方向",
        "comparison": "与历史、基准或趋势的比较",
        "note": "该指标支持哪个判断"
      }
    ],
    "risk_notes": [],
    "uncertainties": [],
    "data_quality": {
      "missing_required": [],
      "missing_optional": [],
      "conflicting_indicators": [],
      "stale_indicators": [],
      "coverage_level": "high | medium | low"
    },
    "review_log": {
      "source_data_review": "pass | fail",
      "calculation_review": "pass | fail",
      "conclusion_review": "pass | fail"
    },
    "bridgewater_layers": {
      "all_weather_layer": "asset_allocation_defense | not_applicable",
      "pure_alpha_layer": "hypothesis_only | not_applicable",
      "productivity_trend": "improving | weakening | unclear"
    },
    "personal_finance_guardrails": [
      "cash_flow_safety",
      "no_leverage_expansion",
      "rebalance_only_after_review"
    ],
    "needs_human_review": true
  }
}
```


证据规则：所有核心判断必须写入 `meta.evidence`；每条证据至少包含 `source_type`、`source_name`、`date`、`metric`、`value`、`comparison`、`note`。没有证据支撑的内容只能写入 `meta.uncertainties`，不得进入 `meta.key_findings`。

字段约束：

- `direction` 只能是 `bullish`、`bearish`、`neutral`。
- `confidence` 必须是 0.0–1.0 的数字；本 Skill 的常规宏观判断建议上限为 0.9，除非上游系统另有统一校准。
- `signal_type` 固定为 `technical`。
- `signals` 必须是字符串列表，不能使用对象列表；详细分类放入 `meta.signal_details` 或 `meta.macro_quadrant`。
- `stock_code` 固定为空字符串 `""`。
- `source` 固定为 `bridgewater_economic_machine_lite`。
- 没有数据支撑的判断只能进入 `uncertainties`，不能写入 `key_findings`。

---

## 10. 普通人报告输出

默认情况下，Agent 必须只输出单一、可解析的标准 Signal JSON，不得在 JSON 后追加 Markdown 或自然语言报告。

如上层流程明确需要普通人可读报告，应将报告写入 `meta.user_report`，或由报告 Agent 基于标准 Signal 另行生成。建议 `meta.user_report` 使用以下结构：

1. 一句话结论。
2. 当前四象限判断。
3. 短期债务周期位置。
4. 长期债务压力判断。
5. 数据证据表。
6. 全天候防御塔建议。
7. 纯粹阿尔法假设边界：仅列假设、证据、反证，不给交易指令。
8. 普通投资者行动清单与个人财务原则。
9. 风险提示。
10. 三次复查记录。
11. 最终提醒。

表达要求：

- 避免过度专业黑话。
- 先说结论，再说证据。
- 必须说明不确定性。
- 低置信度时不得使用“明显”“确定”“强烈建议”等措辞。

错误表达：

> 当前 term premium 与 breakeven inflation 的 convexity adjustment 显示 duration beta 可能发生非线性重估。

正确表达：

> 长债的风险在上升。原因是市场对未来通胀和利率的预期还没有完全稳定，债券价格可能继续大幅波动。

---

## 11. 三次复查机制

### 11.1 第一次复查：数据完整性复查

检查：

1. 输入是否包含分析对象和时间窗口。
2. 增长、通胀、信用/政策三类核心证据是否至少各有一项。
3. 指标是否有日期。
4. 指标是否有来源说明。
5. 是否存在缺失或过旧数据。
6. 是否混用了不同国家、频率或口径。

失败处理：

- `review_log.source_data_review = "fail"`
- `confidence <= 0.4`
- `direction = "neutral"`
- `needs_human_review = true`

### 11.2 第二次复查：计算一致性复查

检查：

1. 指标方向是否转换正确。
2. 反向指标是否正确处理。
3. 模块分数是否与证据方向一致。
4. 四象限是否与增长/通胀方向一致。
5. 债务周期是否与信用/政策/债务压力证据一致。
6. 是否存在单一指标过度主导结论。

失败处理：

- 降低 `confidence`。
- 将冲突写入 `uncertainties`。
- 严重冲突时改为 `direction = "neutral"`。

### 11.3 第三次复查：结论安全性复查

检查：

1. 结论是否和证据一致。
2. 资产配置倾向是否和象限一致。
3. 是否误写成具体买卖建议。
4. 是否承诺收益。
5. 是否过度乐观或过度确定。
6. 普通人能否理解。

失败处理：

- 重写 `reasoning` 和普通人报告。
- 删除确定性交易建议。
- 添加风险提示。

---

## 12. 置信度规则

| 条件 | confidence 建议 |
|---|---:|
| 数据完整、方向一致、无明显冲突 | 0.70–0.90 |
| 数据较完整，但有少量冲突或缺失 | 0.50–0.69 |
| 数据不足、指标分歧大、政策环境不确定 | 0.30–0.49 |
| 核心数据大量缺失或结论无法判断 | 0.00–0.29 |

宏观判断存在固有不确定性，本 Skill 常规输出的 `confidence` 建议不超过 0.9；但字段本身仍遵守项目标准的 0.0–1.0 范围。

若 `confidence < 0.4`：

- 顶层 `direction` 应为 `neutral`。
- `risk_level` 至少为 `medium`。
- `needs_human_review = true`。
- 不能输出进攻性资产配置建议。

---

## 13. 安全边界

本 Skill 不允许：

1. 执行真实交易。
2. 登录券商账户。
3. 读取用户隐私资产账户。
4. 输出个股买卖点。
5. 使用未经验证的小道消息作为证据。
6. 把宏观判断包装成确定性投资建议。
7. 在数据不足时强行判断 bullish 或 bearish。
8. 将资产配置倾向写成用户必须执行的指令。

如果用户要求具体买卖，必须改为：

- 风险分析。
- 配置思路。
- 场景推演。
- 需要用户或专业投顾确认的事项。

---

## 14. 小白检查方式

拿到 Agent 输出后，只检查以下 10 项：

1. `direction` 是否只有 bullish / bearish / neutral。
2. `confidence` 是否是 0–0.9 的数字。
3. `signal_type` 是否是 technical。
4. `stock_code` 是否为空字符串。
5. 是否写了当前象限。
6. 是否写了债务周期位置。
7. 是否有 evidence，且 evidence 有 source_type、source_name、日期、指标、数值或方向。
8. 缺数据是否写进 uncertainties。
9. `needs_human_review` 是否在低置信度或冲突时为 true。
10. 是否没有出现“买入某只股票/满仓/稳赚/一定”等表述。

---

## 15. 测试样例要求

至少应测试以下场景：

1. Q1 金发姑娘：增长上行 + 通胀下行。
2. Q2 再通胀/过热：增长上行 + 通胀上行。
3. Q3 滞胀：增长下行 + 通胀上行。
4. Q4 衰退/通缩：增长下行 + 通胀下行。
5. Mixed：增长/通胀接近临界或信号冲突。
6. All Weather 防御塔：输出资产类别倾向但不输出交易指令。
7. Pure Alpha 边界：只能输出主动判断假设和反证，不输出做多/做空指令。
8. 个人财务原则：低置信度或高风险时必须提示现金流、杠杆和再平衡纪律。
9. 缺失数据：低置信度 + neutral + needs_human_review。
10. 低置信度：资产建议不得过度进攻。

