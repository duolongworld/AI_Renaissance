# 专家 Skill 通用模板

> 这是一份给专家组参照使用的 Skill 模板。开发1组维护模板结构，专家组负责填充专业分析逻辑。

当前项目中，Skill 是分析能力本体，Agent 是调用 Skill 并封装标准 `Signal` 的外壳。专家组现阶段先聚焦写 Skill，把判断逻辑、证据规则和输出格式调稳定。

本模板是开发1组提供的第一阶段 v0.1 规范，用于统一专家组 Skill 的目录、结构和输出。后续阶段如系统能力演进，再由开发1组发布新版规范。

职责分工：

- 专家组负责专业 Skill 内容：适用范围、输入材料、分析步骤、判断规则、证据规则。
- 开发2组负责 Agent 调用 Skill、数据流、信号汇总、仲裁逻辑和主流程调度。
- 开发1组负责 Skill 模板、输出规范、目录规范和联调标准。

---

## 推荐目录

正式 Skill 放在：

```text
skills/{domain}/{skill_name}/SKILL.md
```

示例：

```text
skills/financial/cash_flow_quality_check/SKILL.md
skills/technical/ma_trend_check/SKILL.md
skills/risk/tail_risk_warning/SKILL.md
```

怎么理解这条路径：

- `skills/`：项目里统一存放 Skill 的目录。
- `{domain}`：Skill 所属领域，用英文目录名表示，例如 `financial` 表示财务，`risk` 表示风控。
- `{skill_name}`：Skill 的英文名，用小写字母和下划线，例如 `cash_flow_quality_check`。
- `SKILL.md`：固定文件名，里面写具体分析框架。

---

## SKILL.md 模板

使用方式：

1. 先确定自己的领域和 Skill 英文名。
2. 在 `skills/` 下新建目录，例如 `skills/financial/cash_flow_quality_check/`。
3. 在这个目录里新建文件 `SKILL.md`。
4. 把下面整段模板复制进 `SKILL.md`。
5. 把方括号里的内容替换成自己的专业分析逻辑。

字段里的英文值可以先照抄。下面会给中文解释。

专家组主要填写三块内容：

- `适用范围`
- `输入材料`
- `判断规则`

除非开发1组更新模板版本，否则尽量保持目录规范、字段名和标准输出结构不变。

````markdown
---
name: [skill-name]
description: [一句话说明这个 Skill 做什么、什么时候使用。写清楚触发场景。]
owner_group: [专家X组（方向）]
domain: [financial | technical | fundflow | macro | news | valuation | industry | risk]
status: draft
---

# [Skill 中文名称]

## 1. 适用范围

所属小组：[专家X组（方向）]

适用任务：
- [这个 Skill 解决什么问题]
- [适合分析什么对象，例如个股、行业、指数、宏观变量]
- [适合什么时间周期，例如季度、年度、最近N天]

边界说明：
- [哪些输入不足时需要人工复核]
- [哪些结论只作为风险提示，不直接转成交易建议]

## 2. 输入材料

### 必填输入

- 标的：公司名 / 股票代码 / 行业 / 指数
- 时间范围：季度 / 年度 / 最近N天
- 核心数据材料：[财报 / 公告 / 行情 / 资金 / 舆情 / 宏观数据等]
- 数据来源：说明来自公告、财报、行情源、新闻、人工输入等

### 可选输入

- 人工补充观点
- 截图
- 研报摘要
- 新闻链接
- 历史同期数据
- 行业对比数据

### 缺失处理

- 如果必填输入缺失，输出 `direction: "neutral"`，降低 `confidence`，在 `meta.uncertainties` 写明缺什么，并把 `meta.needs_human_review` 设为 `true`。
- 如果可选输入缺失，可以继续分析，但需要在 `meta.uncertainties` 中说明可能影响。

## 3. 分析步骤

按下面步骤分析：

1. 明确分析对象、时间范围和数据来源。
2. 检查输入数据是否足够。
3. 提取关键事实和指标。
4. 判断事实对应的方向：看多、看空或中性。
5. 给出证据和证据来源。
6. 标注不确定性和人工复核点。
7. 输出标准 JSON。

## 4. 判断规则

写清楚本 Skill 的专业判断规则。

每条规则尽量写清楚：

- 判断指标
- 阈值或比较对象
- 时间窗口
- 对 `direction` 的影响
- 对 `confidence`、`risk_level` 的影响

示例：

- 如果经营现金流 / 净利润连续 2 个季度低于 1.0，偏负面。
- 如果合同负债同比增长且经营现金流改善，偏正面。
- 如果指标互相矛盾，输出 `neutral`，并在 `meta.uncertainties` 写明矛盾点。
- 如果证据不足，降低 `confidence`，并把 `meta.needs_human_review` 设为 `true`。

### 从财经判断翻译成 Skill 规则

财经专家可以先用自然语言写判断，再把它翻译成规则。示例：

```text
财经判断：
经营现金流连续两季低于净利润，利润质量偏弱。
```

翻译成 Skill 规则：

```text
指标：经营现金流量净额 / 净利润
阈值：连续 2 个季度低于 1.0
direction：bearish（看空）
confidence：0.6-0.8；如果同时应收账款高增，可以提高到 0.8 附近
risk_level：medium；如果连续多个报告期恶化，可以升为 high
evidence：记录报告期、指标值、财报来源和对比结论
needs_human_review：如果现金流口径或一次性项目不清楚，设为 true
```

## 5. 标准输出

最终输出 JSON，顶层字段与当前项目 `agents.signal.Signal` 对齐。当前代码已经支持的字段放在顶层；给开发2组后续仲裁、展示、追溯使用的补充字段，先放在 `meta` 中。

这里的 `meta` 是 Skill 输出的一部分，不是可有可无的附注。第一阶段 v0.1 规范中，证据、风险等级、时间周期、关键发现、不确定性和人工复核点统一放在 `meta` 中。

Skill 里需要写清楚这些信息如何产生：

- 证据从哪里来
- 风险等级如何判断
- 时间周期如何判断
- 关键发现如何提取
- 什么情况下需要人工复核

Agent 读取 Skill 后，会按这些规则生成 JSON；开发2组做汇总和仲裁时，也会读取 `meta` 里的证据和上下文。后续阶段如系统能力演进需要新增字段，由开发1组更新 `output_version`，并同步给各专家组。

```json
{
  "direction": "bullish | bearish | neutral",
  "confidence": 0.0,
  "reasoning": "",
  "signals": [],
  "source": "",
  "signal_type": "financial | technical | fundflow | macro | news | valuation | industry | risk",
  "stock_code": "",
  "weight": 1.0,
  "meta": {
    "output_version": "0.1",
    "skill_name": "",
    "owner_group": "",
    "target": "",
    "period": "",
    "time_horizon": "short | mid | long",
    "risk_level": "low | medium | high",
    "key_findings": [],
    "evidence": [
      {
        "source_type": "financial_report | announcement | market_data | fund_flow | macro_data | industry_data | news | social_media | research_report | expert_input",
        "source_name": "",
        "date": "",
        "metric": "",
        "value": "",
        "comparison": "",
        "note": ""
      }
    ],
    "risk_notes": [],
    "uncertainties": [],
    "needs_human_review": true
  }
}
```

说明：

- `direction` 表示方向，只能是 `bullish`（看多）、`bearish`（看空）、`neutral`（中性）。当前代码暂不支持 `risk_warning` 作为方向。
- 风险类 Skill 使用 `signal_type: "risk"`；如果风险偏负面，用 `direction: "bearish"`，如果只是监控提示，用 `direction: "neutral"`。
- `confidence` 范围是 0.0 到 1.0。
- `signals` 写最核心的信号短句，便于调试 UI 展示。
- `reasoning` 写简明推理摘要，详细证据放到 `meta.evidence`。

## 字段中英对照

| 字段 | 中文含义 | 填写说明 |
|---|---|---|
| `direction` | 方向 | `bullish` 看多；`bearish` 看空；`neutral` 中性 |
| `confidence` | 置信度 | 0.0 到 1.0，越高表示越确定 |
| `reasoning` | 推理摘要 | 用一小段话说明为什么得出这个结论 |
| `signals` | 核心信号 | 放最重要的短句，例如“经营现金流弱于净利润” |
| `source` | 信号来源 | 谁产出这个信号，通常写 Skill 名或 Agent 名 |
| `signal_type` | 信号类型 | `financial` 财务；`technical` 技术指标；`fundflow` 资金；`macro` 宏观；`news` 新闻舆情；`valuation` 估值；`industry` 行业；`risk` 风控 |
| `stock_code` | 股票代码 | 没有股票代码时可以留空或写标的名称到 `meta.target` |
| `weight` | 权重 | 先填 1.0，后续由仲裁层决定是否使用 |
| `meta` | 证据包/上下文包 | 放证据、风险等级、时间周期、人工复核点等 |
| `time_horizon` | 时间周期 | `short` 短期；`mid` 中期；`long` 长期 |
| `risk_level` | 风险等级 | `low` 低；`medium` 中；`high` 高 |
| `evidence` | 证据 | 记录来源、日期、指标、数值和说明 |
| `uncertainties` | 不确定性 | 数据缺失、口径不一致、需要复核的地方 |
| `needs_human_review` | 是否需要人工复核 | `true` 是；`false` 否 |

## `source_type` 来源类型

`source_type` 用来说明证据来自哪里。第一阶段可以使用下表里的值；如果确实需要新增来源类型，在 Skill 中写清楚中文含义即可，后续由开发1组统一整理。

| source_type | 中文含义 | 示例 |
|---|---|---|
| `financial_report` | 财报 | 年报、季报、资产负债表、现金流量表 |
| `announcement` | 公告 | 交易所公告、公司公告、重大事项公告 |
| `market_data` | 行情数据 | 价格、成交量、换手率、技术指标 |
| `fund_flow` | 资金流数据 | 主力资金、北向资金、龙虎榜 |
| `macro_data` | 宏观数据 | 利率、汇率、PMI、CPI |
| `industry_data` | 行业数据 | 产业链价格、供需、库存、开工率 |
| `news` | 新闻 | 财经新闻、公司新闻、政策新闻 |
| `social_media` | 社交舆情 | 股吧、雪球、微博、社区讨论 |
| `research_report` | 研报 | 券商研报、机构观点 |
| `expert_input` | 人工输入 | 专家组人工补充的判断或材料 |

## `domain`、`source`、`source_type` 的区别

这三个名字容易混，可以先这样记：

| 字段 | 一句话解释 | 例子 |
|---|---|---|
| `domain` | 我这个 Skill 属于哪个专家领域 | `financial` 表示财务 Skill |
| `source` | 谁产出了这个信号 | `cash_flow_quality_check` |
| `source_type` | 某条证据来自什么材料 | `financial_report` 表示财报证据 |

例如：财务组写的现金流 Skill，`domain` 是 `financial`；这个 Skill 输出的信号 `source` 是 `cash_flow_quality_check`；证据来自三季报，所以证据里的 `source_type` 是 `financial_report`。

## 方向、置信度、风险等级怎么判断

### `direction` 方向映射

- 正面改善、趋势确认、风险缓解：`bullish`（看多）
- 负面恶化、风险暴露、质量下降：`bearish`（看空）
- 数据不足、信号冲突、仅监控提示：`neutral`（中性）
- 风险提示不要新增 `risk_warning` 方向；使用 `signal_type: "risk"` 和 `meta.risk_notes` 表达。

### `confidence` 置信度分档

- `0.8 - 1.0`：证据充分，多个证据方向一致。
- `0.6 - 0.8`：证据较充分，但存在少量不确定性。
- `0.4 - 0.6`：证据有限、口径不完整或信号互相矛盾。
- `< 0.4`：证据不足，一般使用 `neutral`，并标记人工复核。

财经例子：

- 连续多个报告期现金流和利润方向一致，置信度可以较高。
- 只有一期数据，或者缺少同行对比，置信度应降低。
- 财报数据和新闻口径冲突时，置信度应降低并写入 `meta.uncertainties`。

### `risk_level` 风险等级分档

- `low`：有影响，但暂时不改变主要判断。
- `medium`：需要关注，可能影响置信度或后续仓位。
- `high`：可能推翻判断，或需要优先人工复核。

财经例子：

- 普通毛利率波动，可能是 `low` 或 `medium`。
- 应收账款和存货同步异常增长，通常至少是 `medium`。
- 财务造假嫌疑、债务违约风险、重大诉讼风险，通常是 `high`。

### `time_horizon` 时间周期例子

- 财报质量、资金趋势通常偏 `mid`（中期）。
- 宏观周期、行业供需格局通常偏 `long`（长期）。
- 新闻事件、舆情冲击、短期资金异动通常偏 `short`（短期）。

## 6. 质量检查

输出前检查：

- 是否有明确 `direction`
- `confidence` 是否在 0.0 到 1.0
- 是否写明 `signal_type`
- 是否有至少一条核心 `signals`
- 是否有证据来源
- 是否标注时间周期
- 缺失数据是否写进 `meta.uncertainties`
- 是否需要人工复核
````

## meta 字段怎么写

`meta` 是给上层系统继续使用的结构化信息。专家组写 Skill 时，需要在分析规则里说明这些字段怎么得到。

再次强调：写 Skill 不是写某一次分析结果，而是写一套“未来每次分析都怎么生成这些字段”的规则。

### `meta.evidence`：证据

证据回答的是：“为什么得出这个判断？”

每条证据尽量写清楚：

- 数据或信息来源
- 日期或报告期
- 指标名称
- 指标数值
- 与什么标准或历史数据对比
- 这条证据说明了什么

示例：

```json
{
  "source_type": "financial_report",
  "source_name": "2024Q3 财报",
  "date": "2024-10-30",
  "metric": "经营现金流量净额 / 净利润",
  "value": "0.62",
  "comparison": "低于 1.0",
  "note": "现金流对利润支撑不足"
}
```

### `meta.time_horizon`：时间周期

时间周期回答的是：“这个判断主要影响多长时间？”

- `short`（短期）：新闻、舆情、短期资金流、事件冲击，通常是天到数周。
- `mid`（中期）：季度财报、行业景气度、资金趋势，通常是数周到数月。
- `long`（长期）：商业模式、产业周期、宏观周期、竞争格局，通常是数月到数年。

### `meta.risk_level`：风险等级

风险等级回答的是：“这个问题严重到什么程度？”

- `low`（低）：有影响，但暂时不改变主要判断。
- `medium`（中）：需要关注，可能影响结论置信度或仓位。
- `high`（高）：可能推翻原判断，或需要优先人工复核。

### `meta.key_findings`：关键发现

关键发现是最重要的 1-5 条结论短句，便于开发2组和调试 UI 快速扫描。

示例：

```json
[
  "经营现金流连续弱于净利润",
  "应收账款增速高于收入增速",
  "利润质量存在压力"
]
```

### `meta.uncertainties`：不确定性

不确定性回答的是：“哪些地方还不能确定？”

常见情况：

- 数据来源不完整
- 不同数据源口径不一致
- 缺少最新一期数据
- 存在一次性项目影响
- 需要人工确认公告原文

### `meta.needs_human_review`：是否需要人工复核

当数据缺失、结论冲突、风险等级较高、或证据来自低可信来源时，建议设为 `true`。

---

## 各专家组优先完成三块

每个专家组可以先保持模板结构不变，优先完成：

- `适用范围`
- `输入材料`
- `判断规则`

如果需要，也可以补充 `分析步骤`、`证据规则` 和 `质量检查`。标准输出结构保持一致，便于开发2组后续联调和汇总。
