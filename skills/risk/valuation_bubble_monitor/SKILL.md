---
name: valuation_bubble_monitor
description: 估值泡沫风险预警分析。基于动态股权风险溢价(ERP)、巴菲特指标(Buffett Indicator)和反弹高位/顶部过滤器，对市场整体估值水平进行泡沫识别、低估机会识别与短期误判防护。当需要判断某个市场是偏贵、合理还是偏低估，或低估信号是否被短期过热抵消时触发。支持"简化模式"（仅需指数PE分位数和股息率）和"完整模式"（含无风险利率和巴菲特指标），根据可用数据自动降级。v0.8.0（两创专项修复）：消除科创板PE接口文档自相矛盾、重定两创PE分位口径、盈利动能改用成分股财报EPS、中区间景气度修正受流动性板块否决约束、板块级ERP/巴菲特指标近似、滚动高风险日计数熔断、流动性否决支持segments维度、单日≥4.5%暴涨回撤过滤器。v0.9.0（7/10镜像压力测试修复）：顶部过滤器新增"派发型顶部"分支（高PE分位+高位+单日大阴+天量收阴+冲高回落，跌亦触发）；趋势反转确认层"背离"改为双向绝对值（指数跌·宽度强这一反向背离亦可触发）并解除"必须bullish"前置约束；流动性否决/板块联动新增"黄白线(等权-加权)双向背离"与"板块资金迁徙/抱团瓦解"信号源；单日暴涨回撤过滤器与派发顶部分支互补。v1.0.0（双因子仪表盘漏洞修复）：§4.4.4暴涨过滤器新增假突破形态判定（长上影+高振幅→direction_detail=neutral_caution+follow_up_events）；§4.5新增板块级信号优先级规则（final_risk_level=max(宽基,segments)）；§2.3科创50PE取数改为csindex与ETF PC双路径并行（偏差>10%标注）；新增§4.6跨日事件组合识别（meta.follow_up_events，假突破→派发顶confidence+0.15）；新增§4.7双Skill仪表盘置信度合成规则（min(liquidity×0.5+valuation×0.5,0.95)，否决封顶0.35）；新增direction_detail子状态字段（neutral_veto/neutral_caution/bearish_strong等，向后兼容）。
owner_group: 专家7组（风控）
domain: valuation
status: draft
version: 1.0.1
last_updated: 2026-07-11
git_branch: skill/valuation-bubble-monitor
---

# 估值泡沫风险预警分析

> **架构映射**
> - 本 Skill 路径：`skills/valuation/valuation_bubble_monitor/SKILL.md`
> - 对应 Agent 目录：`agents/research/valuation/bubble_monitor/`（开发2组实现）
> - 参考文档：`references/valuation_bubble_model.md`
> - 与 Agent 矩阵中现有估值 Agent（PE/PB/PS/PEG/Cycle）的区别：本 Skill 面向**市场整体估值泡沫识别**，而非个股估值分位。

## 1. 适用范围

所属小组：专家7组（风控）

适用任务：
- 判断目标市场（美股、A股、港股等）整体估值水平是否偏高或偏低
- 识别市场是否存在泡沫风险或错杀机会
- 为资产配置、仓位调整提供估值维度的风险提示

适合分析对象：
- 市场指数（标普500、沪深300、恒生指数、**创业板指 399006、科创50 000688 等两创板块指数，v0.8.0重点**）
- 不适用于个股估值判断

适合时间周期：
- 中期（数周到数月）：适用于仓位调整决策
- 长期（数月到数年）：适用于战略资产配置

与 Agent 矩阵中其他估值 Skill 的关系：
- 现有估值 Agent 聚焦**个股估值分位**
- 本 Skill 聚焦**市场整体泡沫识别**

边界说明：
- 本 Skill 输出的是市场整体估值判断，不构成个股投资建议
- 单一估值指标不足以作为交易依据，必须结合其他维度（技术面、资金面、基本面）综合判断
- 当历史数据不足 5 年，或市场结构发生根本性变化（如注册制改革、交易制度改革）时，结论需要人工复核
- ERP 和巴菲特指标均存在均值漂移问题，滚动窗口参数需定期（建议每季度）重算
- 本 Skill 面向市场指数级别分析，`stock_code` 留空，标的名称写在 `meta.target` 中
- **动态校准要求**：`meta.last_calibrated_date` 记录参数最后校准日期，若距今超过 90 天，必须在 `meta.uncertainties` 中标注"参数可能过期，建议重算"
- **v0.7 关键约束**：`neutral` 仅表示估值指标实际处于中性区间；核心估值输入缺失时不得伪装为中性判断，必须标记为 `"inconclusive"`
- **⚠️ v0.8.0 两创约束（P0-3）**：科创板（000688）存在权威 PE 取数路径（`stock_zh_index_value_csindex` 中证编制代码 / 上交所官方），**严禁**输出"无理想代理→inconclusive"的结论；接口缺口时改用 ETF PC 估值或成分股等权 PE 兜底，而非直接 inconclusive。
- **⚠️ v0.9.0 顶部方向偏置修复（P0-7）**：原顶部过滤器（RSI>70 / ma20偏离>25% / 单日涨>5%）只抓"加速上涨尖顶"，对"高位天量、冲高回落、放量收阴"的派发型顶部失明（7/10 两创单日大跌 −4.4%~−5.5% 却零触发）。v0.9.0 顶部过滤器新增"派发型顶部"分支（高PE分位+高位+单日大阴+天量收阴+冲高回落），**跌亦触发**。
- **⚠️ v0.9.0 趋势反转层修复（P1-9/P1-6复核）**：原"趋势反转确认层"需处于 bullish 前置且"背离"隐含"指数涨、宽度弱"单向。v0.9.0 改为：① 解除"必须 bullish"前置约束；② "宽度背离"重定义为双向绝对值（|指数收益 − 等权/宽度收益| 达阈值即触发，无论方向），覆盖 7/10"指数跌·宽度强"这一最危险的派发顶部反向背离。
- **⚠️ v1.0.0 假突破左侧预警（P0）**：§4.4.4 暴涨过滤器仅输出 surge_to_neutral 但不检查上影线形态。v1.0.0 新增：若暴涨过滤器触发且 upper_shadow_ratio > 0.5，追加 direction_detail="neutral_caution" 并写入 follow_up_events（false_breakout），为次日派发提供跨日事件组合基础。
- **⚠️ v1.0.0 板块信号优先级（P0）**：segments.*.risk_level=high 与宽基 risk_level=medium 并存时无消解规则。v1.0.0 新增：final_risk_level = max(宽基 risk_level, max(segments.*.risk_level))，板块级 high 覆盖宽基 medium。
- **⚠️ v1.0.0 PE双路径并行（P3）**：原 csindex→上交所→ETF PC→等权PE 串行回退链耗时。v1.0.0 改为 csindex 与 ETF PC 并行主路径，取先返回者，偏差>10%标注。
- **⚠️ v1.0.0 direction_detail 子状态（P1）**：新增 direction_detail 字段（neutral_veto/neutral_caution/neutral_waiting/bearish_warning/bearish_strong），向后兼容，解决 neutral 内涵不同但下游无法区分。

### 1.6 方向语义与数据不足状态（v0.7新增）

（同 v0.7.3，略）

## 2. 输入材料

### 2.1 必填输入

- 标的：市场名称（如"美股"、"A股"）或指数代码（如"^GSPC"、"000300.SS"、**"399006"创业板指、"000688"科创50，v0.8.0重点**）
- 时间范围：分析时点（默认为最新交易日）
- 核心数据材料（以下三项至少提供其中一项）：
  - 指数点位（收盘价）+ **指数市盈率（PE TTM）**：用于简化模式
  - 无风险利率（10 年期国债收益率）：用于完整 ERP 模式
  - 市场盈利预测：可由指数市盈率倒推替代

> **运行模式自动选择**：同 v0.7.3

- 数据来源：东方财富（akshare `*_em` 系列接口）、中证指数公司（`stock_zh_index_value_csindex`，**覆盖中证系指数，含科创50 000688 中证编制代码，v0.8.0明确**）、乐咕乐股（`stock_index_pe_lg`，固定中文名白名单）。指数 PE 接口覆盖范围与代理回退规则见 §3.A

### 2.2 可选增强输入

（同 v0.7.3，新增以下行：）

| 输入项 | 缺失时的处理 |
|-------|------------|
| **两创板块级 ERP/巴菲特近似输入（v0.8.0新增）** | 板块自由现金流收益率 vs 10Y国债、板块市值/板块GDP贡献，缺失则跳过板块级完整模式，退回简化模式并在 uncertainties 标注 |
| **liquidity_risk_signal（含 segments 维度，v0.8.0）** | 用于执行流动性否决（含板块级），缺失时跳过否决检查 |

### 2.3 缺失处理

（同 v0.7.3，新增 v0.8.0 两创 PE 接口缺口处理：）

- **科创板 PE 接口缺口（v0.8.0 修订，P0-3；v1.0.0 改为双路径并行）**：若 `stock_zh_index_value_csindex` 对 000688 因命名/代码映射问题偶发取不到，**不得**直接标记 `inconclusive` 放弃。
  
  **⚠️ v1.0.0 双路径并行修订（P3，提升实时性）**：
  原 v0.8.0 串行回退链（csindex→上交所→ETF PC→等权PE）改为并行主路径：
  - **主路径A**：csindex 直连（`stock_zh_index_value_csindex("000688")`）
  - **主路径B**：ETF PC 估值（588000等，价格/成分股加权净值）
  - 两条路径**同时发起请求**，取先返回者作为主结果
  - 若两者均返回：
    - 偏差 ≤ 10%：取均值作为 consensus，confidence +0.05，`proxy_used = false`
    - 偏差 > 10%：取 csindex 结果（权威优先），`uncertainties` 标注"双路径PE偏差>10%，建议人工复核"
  - 若仅一条返回：使用该结果，`proxy_used = (路径B时 true)`
  - 若两者均失败：继续三级回退链 ③上交所官方 PE → ④成分股等权 PE
  - 仅当①②③④均不可得，才标记 `inconclusive`，且 `confidence ≤ 0.25`、`needs_human_review=true`

### 2.4 数据契约与覆盖率（v0.7新增，v0.8.0 补两创）

（同 v0.7.3，新增 `pe_ttm_segment` 板块维度字段）

**覆盖率字段**：

```json
"meta": {
  "signal_state": "valid | inconclusive | deferred",
  "decision_status": "ok | blocked_missing_core_valuation | stale_cache_used | liquidity_deferred | black_swan_degraded",
  "data_completeness_score": 0.0,
  "rule_coverage_score": 0.0,
  "core_metrics_available": {
    "index_close": false,
    "pe_ttm_current": false,
    "pe_ttm_history": false,
    "dividend_yield_current": false,
    "risk_free_rate": false,
    "buffett_indicator": false,
    "market_state_filter_inputs": false
  }
}
```

### 自动化免责声明注入

（同 v0.7.3）

## 3. 分析步骤

### 3.A 简化模式（数据管道可获取，推荐默认路径）

当无风险利率或 GDP 数据不可用时，自动进入简化模式，使用以下替代指标：

**步骤一：PE 历史分位数判断**

- 获取指数最新 PE TTM（akshare `stock_index_pe_lg` 或等效接口）
- 计算当前 PE 在近 5 年历史分布中的分位数

> **⚠️ 指数 PE 接口覆盖范围与代理回退规则（v0.7.1 重要补充，v0.8.0 修订 P0-3）**
>
> 免费 akshare 接口对指数 PE 的覆盖**并不完整**，调用前必须先确认目标指数是否被支持：
>
> | 接口 | 覆盖范围 | 不覆盖（会报错） |
> |------|---------|----------------|
> | `stock_zh_index_value_csindex(symbol=...)` | **仅中证指数公司发布的指数**（沪深300、中证500/1000、**科创50 对应中证代码 000688 等**） | 深交所自有指数（创业板指 399006、深证成指等）→ **HTTP 404** |
> | `stock_index_pe_lg(symbol=...)` | 固定白名单：上证50、沪深300、上证380、**创业板50**、中证500、上证180、深证红利、深证100、中证1000、上证红利、中证100、中证800 | 白名单外的任何名称（"创业板指""科创50""399006"）→ **KeyError** |
>
> **关键陷阱**：`stock_index_pe_lg` 入参是固定中文名；传代码必然 KeyError。白名单含"创业板50"不含"创业板指"。
>
> **⚠️ v0.8.0 重大修订（P0-3，消除文档自相矛盾）**：
> 原文档在接口覆盖表中称 `stock_zh_index_value_csindex` "覆盖科创50 对应中证代码"，却在代理回退规则中称"科创50 → 暂无理想代理，标记 inconclusive"。
> 这是**文档内部不一致**，且会将最高风险板块推向最低置信度信号。v0.8.0 明确：
> 1. **科创50（000688）存在权威 PE 取数路径**：`stock_zh_index_value_csindex(symbol="000688")` 或上交所官方接口可直接获取，**不得**再写"暂无理想代理→inconclusive"。
> 2. 创业板指（399006，深交所）无免费直连 PE，但可用 **创业板50（399673）代理**（原规则保留）。
> 3. 若 csindex 对 000688 因代码映射偶发失败，按 §2.3 回退链（重试→上交所→ETF PC 估值→成分股等权 PE），**严禁直接 inconclusive**。
>
> **代理回退规则（v0.8.0修订）**：

> 1. 创业板指 → 创业板50 `399673`（成分高度重叠，同源代理）；
> 2. **科创50 → 优先 `stock_zh_index_value_csindex("000688")` 直连；失败则用科创50ETF（588000等）的 PC 估值 或 板块成分股等权 PE**（v0.8.0新增，删除原"暂无理想代理"错误结论）；
> 3. 使用代理时，`signal_state` 仍取 `valid`，但必须置 `meta.proxy_used = true`，`data_authenticity_score` 打折（建议 ≤0.70），confidence 自然被压低；
> 4. 若连合理代理都不存在（①②③④均失败），才按原降级路径输出 `signal_state=inconclusive`，**不得**用代理硬凑。

> **PE 分位口径优先级（v0.7.2 新增，v0.8.0 重定两创口径，P1-4）**
>
> 1. **优先口径（v0.8.0 按板块差异化）**：
>    - **科创板（2019年开板，历史短，且含2020-2021半导体牛市泡沫样本）**：优先使用 **"发布以来分位"**（since_inception），暴露真实泡沫；近5年分位因含泡沫期会**显著偏高/失真**，仅作参考。
>    - **创业板（近5年含2020-2021新能源/半导体顶部）**：优先使用 **"近3年分位"**（3y）；发布以来分位作补充。
>    - **主板/宽基（沪深300等）**：维持"近5年滚动分位"（与流动性 Skill 口径一致）。
> 2. 若首选口径数据不足，使用备选口径，并在 `meta.uncertainties` 标注。
> 3. 两个口径均可用时，取**均值作为 consensus**，confidence +0.05。
> 4. 在 `meta` 中以 `pe_percentile_window` 字段标明实际采用的口径（`"5y" | "3y" | "since_inception" | "consensus"`）。
>    **v0.8.0 强制**：两创必须显式标注窗口，禁止模糊"近5年"掩盖真实泡沫。

- 分位判断规则：（同 v0.7.3 分位表）

**补充：EPS 动量修正系数（v0.5新增，v0.8.0 修订 P1-5）**

**计算步骤（v0.8.0 修订）**：

1. 计算当季 EPS 同比变化率（EPS YoY）：
   - **v0.8.0 主数据源：成分股实际财报 EPS 同比（优先）**。对指数成分股取最新季报/年报的 EPS，按市值加权计算板块 EPS YoY，直接来自财报数据（akshare `stock_financial_abstract` / `stock_indicator` 等），**避免点位倒推**。
   - 若财报数据不可得，**允许**用指数 PE 和点位倒推 EPS 作为兜底（原方法），但须在 `meta.uncertainties` 标注"EPS为点位倒推，受价格扰动"。
   - 计算公式：`EPS_YoY = (EPS_current_quarter / EPS_same_quarter_last_year) - 1`

2. 修正规则（仅当 PE 分位数 > 80% 时生效；≤80% 不修正）：（同 v0.7.3）

**输出要求**：（同 v0.7.3）

**示例**：（同 v0.7.3）

**补充：中区间景气度修正（v0.7.2 新增，v0.8.0 受流动性板块否决约束，P1-6）**

修正规则（PE 分位 ∈ [40%, 80%) 时生效；≥80% 走 EPS 动量修正）：

（分位表同 v0.7.3）

> **⚠️ v0.8.0 流动性约束（P1-6，避免高景气叙事延迟风险）**：
> 当接收到 `liquidity_risk_signal` 且该板块（通过 `segments.chinext` / `segments.star` 或宽基）已输出 `risk_level=high AND liquidity_outlook=negative`，**且**该板块宽度崩溃（ADR<0.6）时：
> - 中区间景气度修正**不得**将 bullish/neutral 降级为"乐观 neutral"以抵消流动性否定；
> - 若原方向为 neutral，须维持 **"高风险 neutral + 强人工复核"**（`needs_human_review=true`，`risk_notes` 写明"流动性危机下高景气不可覆盖否决"），confidence 封顶 0.50；
> - 若原方向为 bullish，直接输出 **bearish**（与流动性否决一致）。
> 即：流动性否决优先级高于中区间景气度修正，防止 7/6–7/8 创业板"PE 70-75% + EPS +34% → neutral"抵消流动性 negative 信号。

**补充：盈利动能衰减修正（v0.7.3新增，v0.8.0 修订 P1-5）**

**触发条件（v0.8.0 修订）**（同时满足）：
  - EPS 同比增速（EPS YoY）**环比下滑超过 10 个百分点**（当前增速 - 前值增速 ≤ -10%）
    **或（v0.8.0新增）** 绝对增速跌破 **20%**（连续2期下滑 或 单期 < 20%）
  - 且 PE 分位数 > **60%**（偏贵区间）
  > v0.8.0 修订理由（P1-5）：原仅看"环比下滑>10pp"会漏判"从+60%→+45%（仍高增但是拐点）"；新增"绝对增速跌破20%"与"连续2期下滑"捕捉盈利增速拐点，且 EPS 改用成分股财报（非点位倒推），规避 7/9 点位暴涨放大 EPS 的失真。

**修正逻辑**：
  - 若原方向为 `bullish` 或 `neutral`，**强制降级为 `bearish`**
  - 若原方向已为 `bearish`，**`confidence` 提升 0.15**（上限0.95）
  - `confidence` 基础值 **下调 0.20**
  - `meta.risk_notes` 中写入："盈利动能衰减修正触发：EPS增速骤降/跌破20%，高估值失去基本面支撑"

**步骤二：股息率辅助验证**（同 v0.7.3）

**步骤三：名义盈利增长率 g（简化模式用法）**（同 v0.7.3，v0.8.0 注明 g 优先用成分股财报 EPS CAGR）

**步骤四：顶部过滤器 + 熔断检查**（同 v0.7.3，新增 §4.4.4 暴涨后回撤过滤器）

**简化模式输出标注**：（同 v0.7.3）

---

完整模式步骤（同 v0.7.3，v0.8.0 新增板块级 ERP/巴菲特近似，见 §3.B）

### 3.B 板块级完整模式近似（v0.8.0新增，P2-3）

> 背景：完整模式依赖全市场"市值/GDP"（巴菲特指标）与无风险利率的 ERP。两创作为子板块无独立的"市值/GDP"概念，原文档未定义两创板块级完整模式，导致两创被夹在"完整模式无板块巴菲特指标、简化模式无PE接口"之间。v0.8.0 定义板块级近似。

**板块级 ERP 近似**：
- 板块自由现金流收益率 = 板块成分股自由现金流之和 / 板块总市值
- 板块 ERP ≈ 板块自由现金流收益率 - 10Y 国债收益率
- 若板块 FCF 数据不可得，退回简化模式（PE分位 + 股息率）。

**板块级巴菲特指标近似**：
- 板块市值 / 板块 GDP 贡献（用板块营收占全市场营收比 × 全市场GDP 近似板块经济贡献）
- 或：板块市值 / 全市场GDP（作为下限近似）
- 仅作辅助，阈值参考全市场标准（75%/150%），但在 uncertainties 标注"板块级近似，非全市场口径"。

**执行**：板块级完整模式仅在 FCF 与板块 GDP 贡献均可得时运行；否则退回简化模式并在 uncertainties 标注。

## 4. 判断规则

### 4.1 隐含 ERP Z-score 判断规则（同 v0.7.3）

### 4.2 巴菲特指标判断规则（同 v0.7.3）

### 4.3 多维共振验证规则（同 v0.7.3）

### 4.4 短期顶部/反弹高位过滤器

#### 4.4.1 触发条件（同 v0.7.3）

#### 4.4.2 过滤器效果（同 v0.7.3，含趋势反转确认层）

**趋势反转确认层（v0.7.2 新增）**：
（同 v0.7.3，v0.8.0 明确该层对两创（创业板指/科创50）同等适用，且触发时不受中区间景气度修正干扰）

#### 4.4.3 A股 2022 年 6 月误判防护（同 v0.7.3）

#### 4.4.3.1 派发型顶部分支（v0.9.0新增，P0-7，针对 7/10 型）

> 背景：原顶部过滤器（RSI>70 / ma20偏离>25% / 单日涨>5%）只建模"加速上涨的尖顶"。真实顶部常以"高位天量、冲高回落、放量收阴"的派发形态出现（7/10 创业板指 −4.37%、科创50 −5.53%，权重股历史天量派发），因"不是暴涨"而零触发，方向偏置导致对派发顶失明。

**触发条件（满足全部即判派发型顶部，direction 强制降级）**：
- 板块 PE 分位（按 §3.A 口径，科创板 since_inception / 创业板 3y）> **75%**（处于偏贵/极贵区间）
- 且 价格处于高位：距 60 日高点 ≤ 15% 或 近 20 日涨幅 > +8%
- 且 当日**收阴**且单日跌幅 > **3%**（"大涨后高位大阴"）
- 且 量能异常：当日成交量 > 近 20 日均量 × 1.5（天量派发）
- 且 出现冲高回落：upper_shadow_ratio = (最高-收盘)/(最高-最低) > 0.6，或 盘中曾涨 > +2% 但最终收阴

**执行逻辑**：
- 不依赖"单日涨>5%"的原有上涨条件，**跌亦触发**
- 若基础方向为 bullish/neutral：强制降级为 **bearish**（与流动性否决一致），`confidence` 提升 0.15（上限0.95）
- 若基础方向已 bearish：维持，但 `signals` 追加"派发型顶部确认：高位天量收阴+冲高回落，主力派发"
- `meta.market_state_filter` 写入 `triggered: true, strength: "strong", adjustment: "bullish_to_bearish"`（原bullish时）
- `needs_human_review: true`

**与 §4.4.4 暴涨后回撤过滤器的关系**：§4.4.4 管"暴涨次日追高风险"（涨后），本分支管"高位放量收阴的派发当下"（跌中），两者互补覆盖尖峰 V 型全周期。

#### 4.4.3.2 趋势反转确认层——双向背离修复（v0.9.0修订，P1-9 / P1-6复核）

> 背景：原 §4.4.2 趋势反转确认层前置约束"irection 须为 bullish"且"宽度背离"隐含"指数涨、宽度弱"单向。7/10 出现反向背离"指数跌(−4.4%)、宽度强(3700+涨)+资金流背离(抱团撤离)"，本是最强派发/接盘顶部信号，却因不匹配单向模式漏判。

**v0.9.0 修订**：
1. **解除"必须 bullish"前置约束**：只要处于 `bullish` 或 `neutral`（且 PE 分位偏高），即进入反转确认扫描；不再因高景气走 neutral 而直接关闭该层（修复 P1-6 复核）。
2. **"宽度背离"重定义为双向绝对值**：
   `breadth_divergence = |指数当日收益 − 等权/宽度代理收益|`（或 |加权指数收益 − 黄白线(等权)收益|，见 §4.5 联动）
   - 触发阈值：`breadth_divergence > 2%`（双向，无论指数红/绿）
   - 原"指数涨、宽度弱"（如 7/8）与 7/10"指数跌、宽度强"**均**命中
3. **联动信号源扩展**：除原"宽度(ADR)背离 + 资金流背离"外，新增：
   - 黄白线双向背离（加权-等权 gap 绝对值 > 1.5%，来自流动性 Skill `segments.*.yellow_white_divergence`）
   - 板块资金迁徙/抱团瓦解（硬科技净流出 + 低位方向净流入，来自流动性 Skill 因子 D）
   - 任一背离信号 + 资金流背离 + PE 分位偏高 → 触发趋势反转确认，direction 强化为 bearish。

**效果**：7/10 型"指数跌·宽度强·抱团撤离"将被正确识别为派发顶部反转，而非"个股普涨的安全日"。

#### 4.4.4 暴涨后回撤风险过滤器（v0.8.0新增，P1-7）

> 背景：2026/7/9 科创50 +8.41%、创业板指 +4.49%，单日暴力反弹。原顶部过滤器（RSI>70/ma20偏离>25%/单日>5%）与流动性规则12在放量普涨日可能同时"不触发"或"误触发"，导致风控"失语"。v0.8.0 新增独立于顶部过滤器的专项过滤器。

**触发条件**（满足任一即触发）：
- 板块单日涨幅 ≥ **4.5%**（如 7/9 科创50 +8.41%，v1.0.1 从 >5% 下调以覆盖两创中阳假突破）
- 且 近 5 日该板块波动率（已实现波动）> 历史 90 分位

**执行逻辑**：
- 不依赖顶部过滤器的"≥2因子"门槛，单日 ≥4.5% 即激活。
- 输出专项信号："单日暴涨≥4.5%，短期回撤风险高，不建议追高，观察量能持续性"
- `direction` 处理：
  - 若基础方向为 bullish：降级为 **neutral**（封顶 confidence 0.50），`risk_notes` 写明"暴涨后不追高，等待量能确认与回撤"
  - 若基础方向已为 neutral/bearish：维持，但 `risk_notes` 追加"暴涨后波动放大，警惕追高"
- `needs_human_review: true`
- `meta.market_state_filter.adjustment` 写入 `"surge_to_neutral"`（若原bullish）
- 该过滤器与流动性否决、趋势反转确认层独立运行，互不覆盖（除非流动性否决已激活则优先否决）。

**⚠️ v1.0.0 假突破形态补充（P0，与流动性Skill规则14.5联动）**：

当暴涨过滤器触发时，追加检查上影线形态：
- 若 `upper_shadow_ratio = (最高-收盘)/(最高-最低) > 0.5`（长上影，主力试出货）
  或 上影线长度 > 实体长度 × 2

则追加执行：
- `direction_detail`: **"neutral_caution"**（禁止追高，允许持仓观察）
- `meta.market_state_filter.adjustment` 追加写入 **"surge_to_caution"**（与原 "surge_to_neutral" 并列标记）
- `meta.risk_notes` 追加："假突破形态特征：长上影+高振幅，次日派发风险高"
- `meta.follow_up_events` 追加：`{ "event_type": "false_breakout", "event_date": "当日", "event_detail": "高位暴涨+长上影假突破", "expiry_date": "次日" }`
- 若次日出现 §4.4.3.1 派发型顶部分支触发 → 触发跨日事件组合（见 §4.6），confidence +0.15

> **与流动性Skill规则14.5的关系**：两者独立运行但逻辑互补。流动性Skill规则14.5 管流动性维度（量能/换手），本补充管估值维度（PE分位/ERP）。两者可同时触发，direction_detail 均为 neutral_caution，signals 各自标注来源。

### 4.5 极端事件熔断逻辑

**硬熔断（Black Swan）**：（同 v0.7.3）

**软预警（灰犀牛→黑天鹅过渡）**：（同 v0.7.3）

**连续高位熔断（风险累积预警，v0.8.0修订 P2-4）**：

当同一标的（或指数）连续多个交易日处于 `risk_level = "high"` 时，触发风险累积熔断：

**触发条件（v0.8.0修订）**：
  - **原规则（宽基/低波动）**：连续 **3个交易日**（含当日）输出 `risk_level = "high"`
  - **v0.8.0 高波动板块修订（P2-4）**：对创业板指/科创50 等高波动板块，将"连续3日"刚性要求改为**滚动 N 日高风险日计数**：
    - 近 **5 个交易日**内 `risk_level = "high"` 的日数 **≥ 3 日** 即触发（捕捉尖峰 V 型中的累积风险，如 7/6–7/9 先跌后暴力反弹的非连续 high）
    - 该计数基于实际输出，不要求连续。

**执行逻辑**：
  - 触发后，强制将 `confidence` 封顶值提升至 **0.95**
  - `signals` 中强制追加："高风险连续累积预警，崩盘概率呈几何级上升，建议强制减仓"
  - `meta` 中新增字段 `consecutive_high_risk_days`（宽基）与 `rolling_high_risk_days_5d`（板块，v0.8.0）

**流动性危机否决（Liquidity Veto，v0.8.0 支持板块维度，P0-4）**：

> 此条款与流动性风险 Skill 对接。

**触发条件**（需外部输入 `liquidity_risk_signal`，v0.9.0 支持 segments 与新探测量）：
- **宽基否决**：`liquidity_risk_signal.risk_level == "high"` **且** `liquidity_risk_signal.liquidity_outlook == "negative"`
- **板块否决（v0.8.0新增，P0-4）**：`liquidity_risk_signal.segments.chinext` 或 `segments.star` 中任一为 `risk_level=="high" AND liquidity_outlook=="negative"` → 该板块估值信号被否决（即便宽基未报 high，防止主板护盘稀释两创风险）
- **⚠️ v0.9.0 板块否决信号源扩展（P0-4/P0-8 复核，消除放量普涨钝化）**：`segments.*` 的 high/negative 现在由流动性 Skill v1.1.0 按**双向**探测量置位，包含：
  - 天量派发断崖（distribution_top_crash）
  - 黄白线(等权-加权)双向背离（`segments.*.yellow_white_divergence == true`，即 |gap|>1.5%）
  - 板块资金迁徙/抱团瓦解（`segments.*.capital_rotation_alert == true`）
  - 板块级 H6（板块放量收阴）
  - 板块级代理B 成交萎缩（v1.0.0 保留）
  - 即：即便 7/10"放量普涨 + 个股红火"，只要两创权重天量派发/黄白线背离/抱团瓦解任一命中，板块否决即激活，估值信号强制 neutral/deferred。

**执行逻辑**：
- 无论 ERP Z-score 或 PE 分位数多么极端，强制将 `direction` 降级为 `"neutral"`
- `confidence` 封顶为 0.35
- `meta.circuit_breaker.liquidity_veto: true`（宽基）或 `liquidity_veto_segment: "chinext" | "star"`（板块，v0.8.0）
- 在 `signals` 中加入："流动性危机否决生效（板块：X），估值看多信号暂缓，等待流动性恢复"
- `meta.risk_notes` 写入："当前处于流动性危机状态（流动性 Skill 板块级输出 high/negative），估值信号被标记为 deferred"
- **（v0.8.0新增，P1-6联动）**：板块否决激活时，中区间景气度修正（§3.A）不得将其覆盖为乐观 neutral，必须维持高风险 neutral/bearish

**否决与其他熔断的优先级**：
- Black Swan 硬熔断 > 流动性危机否决（含板块） > 软预警

**缺失处理**：若 `liquidity_risk_signal` 未传入，跳过此项检查，不输出否决信号。

---

**系统仲裁规则（与流动性 Skill 的联动，v0.8.0 补板块列）**：

| 场景 | 流动性 Skill 输出 | 估值 Skill 内部判断 | 估值 Skill 最终输出 | 系统仲裁方向 |
|------|-----------------|-------------------|-------------------|------------|
| 流动性危机（全市场） | risk=high, outlook=negative | direction=bullish | direction:neutral（被否决） | 强制 neutral/bearish |
| **两创局部危机（v0.8.0新增）** | segments.star=high/negative（宽基未high） | direction:bullish | **板块估值 neutral（板块否决）** | 板块强制 neutral/deferred |
| 正常市场且估值极低 | risk=low, outlook=positive | direction:bullish | direction:bullish | 共振看多 |
| 流动性良好但估值泡沫 | risk=low, outlook=positive | direction:bearish | direction:bearish | 共振看空 |

**⚠️ v1.0.0 板块级信号优先级（P0，与流动性Skill §4.3.1 对齐）**：

当 `liquidity_risk_signal.segments.*.risk_level = "high"` 与宽基 `risk_level = "medium"` 并存时：
- `final_risk_level = max(宽基 risk_level, max(segments.*.risk_level))`
- 即：板块级 high 覆盖宽基 medium，最终 risk_level 不低于板块最高级
- `segments.*.risk_level = "high"` 时，该板块估值信号 risk_level 不低于 "high"
- 估值Skill 读取 `liquidity_risk_signal` 时**必须同时扫描** `risk_level` 和 `segments.chinext/star`
- 若 `segments.*` 字段缺失，以 `"medium"` / `"neutral"` 保守填充并跳过该维度否决检查
- **7/10 实证**：宽基 medium + segments.star=high → final_risk_level=high（不再漏判板块级崩盘）

---

**Neutral 信号细化规则**：（同 v0.7.3）

**⚠️ v1.0.0 direction_detail 子状态（P1，向后兼容）**：

新增 `direction_detail` 字段，在 `direction` 基础上细化子状态：

| 场景 | direction | direction_detail |
|------|-----------|-----------------|
| 流动性否决激活 | neutral | `neutral_veto` |
| 暴涨过滤器+假突破形态（§4.4.4 v1.0.0补充） | neutral | `neutral_caution` |
| signal_state = inconclusive | neutral | `neutral_waiting` |
| 单一维度看空（仅估值 bearish） | bearish | `bearish_warning` |
| 双重共振看空（估值+流动性同时 bearish） | bearish | `bearish_strong` |
| 正常看多 | bullish | `null` |

> 向后兼容：`direction_detail` 为可选字段，下游不消费时退化为原 `direction` 三值逻辑。

### 4.5.1 跨日事件组合识别（v1.0.0新增，P1）

> **背景**：7/9 假突破 → 7/10 派发顶，逐日独立判断导致置信度低估。需跨日事件组合机制。

**meta.follow_up_events 字段**：

```json
"follow_up_events": [
  {
    "event_type": "false_breakout | surge_breakout | distribution_top | volume_anomaly | breadth_collapse",
    "event_date": "YYYY-MM-DD",
    "event_detail": "事件描述",
    "expiry_date": "YYYY-MM-DD"
  }
]
```

**事件写入时机（估值Skill）**：

| 触发规则 | event_type | 说明 |
|---------|-----------|------|
| §4.4.4 暴涨过滤器+假突破形态 | `false_breakout` | 高位暴涨+长上影 |
| §4.4.4 暴涨过滤器（无假突破） | `surge_breakout` | 单日暴涨≥4.5% |
| §4.4.3.1 派发型顶部 | `distribution_top` | 高位天量收阴+冲高回落 |

**跨日事件组合置信度提升规则**：

| 前日事件 | 当日信号 | 置信度提升 |
|---------|---------|-----------|
| `false_breakout` | §4.4.3.1 派发型顶部 | **+0.15**（上限0.95） |
| `surge_breakout` | 流动性否决激活 | +0.10 |

**执行逻辑**：
1. 每日运行时，先检查 `meta.follow_up_events` 中是否有未过期事件
2. 若前日事件与当日信号匹配组合，`confidence` 直接提升（受 0.95 上限约束）
3. `signals` 追加："跨日事件组合：前日[事件类型] + 当日[信号类型]，置信度提升+X"
4. 匹配后从 `follow_up_events` 移除（已消费）；超期自动移除

### 4.5.2 双Skill仪表盘置信度合成规则（v1.0.0新增，P1）

> 与流动性Skill §4.7 对齐，两份Skill各保留一份以确保双边一致。

**合成公式**：

```
final_confidence = min(liquidity_confidence × 0.5 + valuation_confidence × 0.5, 0.95)
```

**封顶规则**：

| 优先级 | 条件 | 封顶值 |
|--------|------|--------|
| 1 | 流动性否决激活 | **0.35** |
| 2 | 任一 Skill 的 signal_state/analysis_state = "inconclusive" | **0.45** |
| 3 | 极端估值熔断触发（本Skill §4.5） | **不受否决封顶约束**（进攻型预警例外） |
| 4 | 默认上限 | **0.95** |

**方向合成规则**：

| 流动性 direction | 估值 direction | 仪表盘 final_direction | direction_detail |
|-----------------|---------------|----------------------|-----------------|
| bearish | bearish | bearish | `bearish_strong` |
| bearish | neutral | bearish | `bearish_warning` |
| neutral | bearish | bearish | `bearish_warning` |
| neutral（否决） | bullish | neutral | `neutral_veto` |
| positive | bullish | bullish | `null` |
| neutral | neutral | neutral | 取更保守者 |

### 4.6 从财经判断翻译成 Skill 规则（同 v0.7.3）

## 5. 标准输出

最终输出 JSON（v1.0.0，在 v0.9.0 schema 基础上新增 direction_detail / follow_up_events 字段）：

```json
{
  "direction": "bullish | bearish | neutral",
  "direction_detail": "neutral_veto | neutral_caution | neutral_waiting | bearish_warning | bearish_strong | null",
  "confidence": 0.0,
  "reasoning": "",
  "signals": [],
  "source": "valuation_bubble_monitor",
  "signal_type": "valuation",
  "stock_code": "",
  "weight": 1.0,
  "meta": {
    "output_version": "1.0",
    "skill_name": "valuation_bubble_monitor",
    "owner_group": "专家7组（风控）",
    "target": "",
    "period": "",
    "time_horizon": "mid | long",
    "risk_level": "low | medium | high",
    "valuation_mode": "simplified | full | segment_full",
    "signal_state": "valid | inconclusive | deferred",
    "decision_status": "ok | blocked_missing_core_valuation | stale_cache_used | liquidity_deferred | black_swan_degraded",
    "data_completeness_score": 0.0,
    "rule_coverage_score": 0.0,
    "follow_up_events": [],
    "confidence_breakdown": {
      "confidence_valuation": 0.0,
      "data_authenticity_score": 0.0,
      "data_completeness_score": 0.0,
      "coverage_cap": 0.0,
      "confidence_final": 0.0
    },
    "core_metrics_available": {
      "index_close": false,
      "pe_ttm_current": false,
      "pe_ttm_history": false,
      "dividend_yield_current": false,
      "risk_free_rate": false,
      "buffett_indicator": false,
      "market_state_filter_inputs": false
    },
    "pe_percentile": null,
    "pe_percentile_window": "5y | 3y | since_inception | consensus",
    "pe_ttm_segment": {
      "chinext": { "pe_percentile": null, "pe_percentile_window": "", "proxy_used": false },
      "star": { "pe_percentile": null, "pe_percentile_window": "", "proxy_used": false, "source": "csindex | etf_pc | equal_weight_pe" }
    },
    "proxy_used": false,
    "proxy_note": "",
    "last_calibrated_date": "",
    "veto_reason": null,
    "veto_segment": null,
    "key_findings": [],
    "evidence": [],
    "risk_notes": [],
    "uncertainties": [],
    "needs_human_review": false,
    "market_state_filter": {
      "triggered": false,
      "strength": "normal | strong",
      "flags": [],
      "adjustment": "none | bullish_to_neutral | bullish_to_bearish | surge_to_neutral | surge_to_caution",
      "reason": ""
    },
    "circuit_breaker": {
      "triggered": false,
      "reason": "",
      "vix": null,
      "qvix": null,
      "surge_warning": false,
      "surge_pct": null,
      "liquidity_veto": false,
      "liquidity_veto_segment": null
    }
  }
}
```

### 各字段如何产生

（同 v0.7.3，新增：）
- **pe_percentile_window**：两创必须显式标注（科创板 since_inception / 创业板 3y），禁止模糊"近5年"。
- **pe_ttm_segment**：板块级 PE 分位与取数来源（star 须标注 csindex/etf_pc/equal_weight_pe）。
- **veto_segment / circuit_breaker.liquidity_veto_segment**：记录板块否决维度。
- **market_state_filter.adjustment = "surge_to_neutral"**：单日≥4.5%暴涨回撤过滤器触发时写入。

### Agent 调用说明（同 v0.7.3）

### meta 各字段如何产生（同 v0.7.3，含 v0.8.0 板块字段）

### 输出示例

**示例1：泡沫预警（双指标共振）**（同 v0.7.3）

**示例2：估值合理（中性）**（同 v0.7.3）

**示例3：黄金坑（双指标共振看多）**（同 v0.7.3）

**示例4：信号矛盾型 Neutral**（同 v0.7.3）

**示例5：Black Swan 熔断**（同 v0.7.3）

**示例6：科创板 PE 接口缺口回退（v0.8.0新增 P0-3）**

```json
{
  "direction": "bearish",
  "confidence": 0.62,
  "reasoning": "科创50 PE TTM分位（发布以来）达82%，处于历史极贵区域；csindex直连偶发失败，改用588000 ETF的PC估值（价格/成分股加权净值）作为代理，data_authenticity打折。盈利动能衰减修正触发（EPS YoY从+24.5%骤降至+9.2%，绝对增速跌破20%）。",
  "signals": [
    "科创50 PE发布以来分位82%，历史极贵",
    "盈利动能衰减修正触发：EPS增速腰斩",
    "PE接口缺口已用ETF PC估值兜底（非inconclusive）"
  ],
  "source": "valuation_bubble_monitor",
  "signal_type": "valuation",
  "stock_code": "",
  "weight": 1.0,
  "meta": {
    "output_version": "0.8",
    "skill_name": "valuation_bubble_monitor",
    "owner_group": "专家7组（风控）",
    "target": "A股/科创50",
    "period": "2026-07-02",
    "time_horizon": "mid",
    "risk_level": "high",
    "valuation_mode": "simplified",
    "signal_state": "valid",
    "decision_status": "ok",
    "data_completeness_score": 0.80,
    "rule_coverage_score": 0.70,
    "pe_percentile": 82.0,
    "pe_percentile_window": "since_inception",
    "pe_ttm_segment": {
      "star": { "pe_percentile": 82.0, "pe_percentile_window": "since_inception", "proxy_used": true, "source": "etf_pc" }
    },
    "proxy_used": true,
    "proxy_note": "csindex(000688)直连失败，改用科创50ETF(588000) PC估值兜底，data_authenticity ≤0.70",
    "key_findings": [
      "科创50发布以来PE分位82%，真实泡沫高于近5年口径",
      "盈利动能衰减，高估值失去基本面支撑"
    ],
    "evidence": [
      { "source_type": "market_data", "source_name": "科创50ETF PC估值", "date": "2026-07-02", "metric": "PE发布以来分位", "value": "82%", "comparison": "历史极贵", "note": "科创板历史短，发布以来口径更暴露泡沫" }
    ],
    "risk_notes": [ "科创板估值处于历史极贵，建议减仓", "盈利增速腰斩，泡沫风险高" ],
    "uncertainties": [ "PE接口缺口用ETF PC估值兜底，非直连，真实性打折" ],
    "needs_human_review": false,
    "circuit_breaker": { "triggered": false, "reason": "", "vix": null, "qvix": null, "surge_warning": false, "surge_pct": null, "liquidity_veto": false, "liquidity_veto_segment": null }
  }
}
```

**示例7：两创局部流动性否决（v0.8.0新增 P0-4/P1-6）**

```text
场景：A股/创业板指 399006
分析日期：2026-07-08
PE TTM分位（近3年）：72%（偏贵）
EPS YoY：+34%（高增长）
liquidity_risk_signal.segments.chinext: { risk_level: "high", liquidity_outlook: "negative" }
（宽基 liquidity_risk_signal: risk=medium, outlook=neutral，未触发宽基否决）
市场宽度：ADR≈0.14（超3700只下跌，广度崩溃）

预期：
- 中区间景气度修正本欲将 bearish→neutral（PE72%+EPS+34%）
- 但 liquidity_risk_signal.segments.chinext = high/negative 且 宽度崩溃 → 板块否决激活（P0-4/P1-6）
- direction: "neutral"（板块否决强制，非乐观neutral）
- confidence: 0.35（封顶）
- meta.circuit_breaker.liquidity_veto_segment: "chinext"
- meta.veto_reason: "流动性危机否决生效（板块：创业板）：当前两创局部流动性危机，估值信号暂缓"
- signals 包含："流动性危机否决生效（板块：创业板），估值看多信号暂缓，等待流动性恢复"
- meta.risk_notes 包含："高景气叙事不得覆盖两创局部流动性否决"
- needs_human_review: true
```

**示例8：单日暴涨回撤过滤器（v0.8.0新增 P1-7）**

```text
场景：A股/科创50 000688
分析日期：2026-07-09
科创50单日：+8.41%（≥4.5%触发）
近5日已实现波动率：>历史90分位
基础方向（PE/ERP）：bullish

预期：
- 暴涨后回撤风险过滤器触发（§4.4.4）
- direction: "neutral"（surge_to_neutral）
- confidence: 0.50（封顶）
- meta.market_state_filter.adjustment: "surge_to_neutral"
- signals 包含："单日暴涨≥4.5%，短期回撤风险高，不建议追高，观察量能持续性"
- meta.risk_notes 包含："暴涨后波动放大，警惕追高，等待量能确认与回撤"
- needs_human_review: true
```

**示例9：派发型顶部 + 板块否决（v0.9.0新增 P0-7/P0-4，7/10 实证）**

```text
场景：A股/创业板指 399006 + 科创50 000688
分析日期：2026-07-10
创业板指：−4.37%（冲高回落）；科创50：−5.53%（尾盘杀跌）
板块 PE 分位：创业板(近3年)≈78%、科创50(发布以来)≈80%（偏贵）
量能：两创权重股（兆易创新等）历史天量收阴，板块成交>20日均×1.5
黄白线：加权弱、等权强，gap≈−2%（双向背离）
资金：硬科技净流出近百亿、商业航天净流入>140亿（抱团瓦解）
liquidity_risk_signal.segments.star/chinext：high/negative（distribution_top_crash + 黄白线背离 + 资金迁徙）

预期：
- §4.4.3.1 派发型顶部分支命中（高位+大阴+天量收阴+冲高回落）→ direction 强制 bearish
- §4.4.3.2 趋势反转确认层：解除 bullish 前置，双向背离（指数跌·宽度强）命中 → 强化 bearish
- 流动性板块否决激活（segments 由 v1.1.0 新探测量置位）→ direction 已 bearish，维持并标记 liquidity_veto_segment
- 最终：direction="bearish"，risk_level="high"，confidence 上限封顶
- signals 包含："派发型顶部：两创权重天量派发+黄白线背离+抱团瓦解，7/10 放量普涨型崩盘，严禁在派发顶加仓"
- needs_human_review: true
```

**示例10：双向背离反转（v0.9.0新增 P1-9，7/10 反向背离）**

```text
场景：A股/科创50 000688
分析日期：2026-07-10
基础方向：neutral（高景气 EPS+34% 走 neutral，原 P1-6 会关闭反转层）
宽度：超3700只上涨（ADR 极高，原"指数涨·宽度弱"单向模式不触发）
指数：科创50 −5.53%（指数跌、宽度强 = 反向背离）
资金：抱团撤离硬科技

预期（v0.9.0 修订后）：
- 趋势反转层解除"必须 bullish"前置 → neutral 仍进入扫描
- 宽度背离重定义为双向绝对值：|指数−5.53% − 等权+1.2%| ≈ 6.7% > 2% → 命中
- 资金流背离（抱团撤离）同命中 → 趋势反转确认触发，direction 强化 bearish
- 不再因"高景气 neutral"漏判 7/10 派发顶
```

---

## 6. 质量检查

（保留 v0.7.3 全部项，新增 v0.8.0 两创专项项：）

- [ ] 是否检查了流动性危机否决（Liquidity Veto）
- [ ] **（v0.8.0新增）是否检查 `liquidity_risk_signal.segments.chinext/star` 板块维度否决；命中时是否对对应板块估值信号降级为neutral并标记 `liquidity_veto_segment`**
- [ ] **（v0.8.0新增）科创板（000688）是否不再输出"无理想代理→inconclusive"；接口缺口是否按回退链（csindex→上交所→ETF PC估值→成分股等权PE）兜底**
- [ ] **（v0.8.0新增）两创 `pe_percentile_window` 是否显式标注（科创板 since_inception / 创业板 3y），禁止模糊"近5年"**
- [ ] **（v0.8.0新增）盈利动能衰减修正是否新增"绝对增速跌破20%/连续2期下滑"触发；EPS是否优先用成分股财报而非点位倒推**
- [ ] **（v0.8.0新增）中区间景气度修正在板块流动性否决+宽度崩溃时是否被约束（不得覆盖为乐观neutral）**
- [ ] **（v0.8.0新增）单日涨幅≥4.5%板块是否触发暴涨后回撤风险过滤器（surge_to_neutral）**
- [ ] **（v0.8.0新增）连续高位熔断对两创是否用"近5日≥3日high"滚动计数替代"连续3日"**
- [ ] 若 PE 分位采用代理或非近5年口径，是否在 `meta.pe_percentile_window` 标明
- [ ] 若使用代理指数（创业板指→创业板50），是否置 `meta.proxy_used=true` 且填写 `meta.proxy_note`
- [ ] **（v1.0.0新增）`direction_detail` 是否与 `direction` 一致（neutral→neutral_*，bearish→bearish_*，bullish→null）**
- [ ] **（v1.0.0新增）流动性否决激活时 `direction_detail` 是否为 `neutral_veto`**
- [ ] **（v1.0.0新增）双重共振看空时 `direction_detail` 是否为 `bearish_strong`**
- [ ] **（v1.0.0新增）§4.4.4 暴涨过滤器触发时是否检查 upper_shadow_ratio；假突破形态是否写入 `follow_up_events`**
- [ ] **（v1.0.0新增）跨日事件组合匹配时 confidence 是否正确提升（+0.10/+0.15，上限0.95）**
- [ ] **（v1.0.0新增）板块级 vs 宽基冲突时 `final_risk_level` 是否取 max(宽基, segments)**
- [ ] **（v1.0.0新增）科创50 PE 是否采用双路径并行（csindex + ETF PC）；偏差>10%是否标注**

---

## 测试样例

（保留 v0.7.3 样例A–H，新增示例6/7/8 见上文 §5）

---

## 更新记录

| 日期 | 版本 | 修改内容 | 作者 |
|-----|------|---------|------|
| 2026-06-22 | 0.5 | 简化模式新增EPS动量修正系数 | 专家7组 |
| 2026-06-23 | 0.6 | 4.4.1 顶部过滤器触发判定优化 | 专家7组 |
| 2026-06-25 | 0.7 | 新增数据不足状态语义、数据契约、覆盖率字段 | 专家7组 |
| 2026-06-27 | 0.7.1 | 一致性修复（12项） | 专家7组 |
| 2026-06-28 | 0.7.1 | §3.A 新增指数 PE 接口覆盖范围与代理回退规则 | 专家7组 |
| 2026-06-28 | 0.7.2 | 中区间景气度修正、趋势反转确认、PE分位口径优先级 | 专家7组 |
| 2026-07-02 | 0.7.3 | 盈利动能衰减修正、连续高位熔断 | 专家7组 |
| **2026-07-10** | **0.8.0** | **两创专项修复（基于2026/7/6–7/9压力测试）**：【P0-3】消除科创板PE接口文档自相矛盾，明确000688权威取数路径（csindex/上交所），删除"无理想代理→inconclusive"错误结论，缺口改用ETF PC估值/成分股等权PE兜底；【P1-4】重定两创PE分位口径（科创板发布以来/创业板近3年），强制标注`pe_percentile_window`；【P1-5】盈利动能衰减修正新增"绝对增速跌破20%/连续2期下滑"触发，EPS优先用成分股财报（非点位倒推）；【P1-6】中区间景气度修正受板块流动性否决约束（否决+宽度崩溃时不得覆盖为乐观neutral）；【P2-3】新增板块级ERP/巴菲特指标近似（§3.B）；【P2-4】连续高位熔断对两创改用"近5日≥3日high"滚动计数；【P0-4】流动性否决支持`segments`板块维度，两创局部危机独立否决；【P1-7】新增单日≥4.5%暴涨回撤风险过滤器（§4.4.4） | 专家7组 |
| **2026-07-10** | **0.9.0** | **7/10 镜像压力测试修复（基于2026/7/10"放量普涨式两创崩盘"）**：【P0-7】顶部过滤器新增"派发型顶部分支"（高PE分位+高位+单日大阴+天量收阴+冲高回落，跌亦触发），消除原"只抓暴涨尖顶"方向偏置；【P1-9/P1-6复核】趋势反转确认层"背离"改为双向绝对值（指数跌·宽度强这一反向背离亦可触发）并解除"必须bullish"前置约束；【P0-4/P0-8复核】流动性否决/板块联动信号源扩展为"天量派发断崖+黄白线双向背离+板块资金迁徙/抱团瓦解+板块级H6+板块代理B"，消除放量普涨钝化（与流动性 v1.1.0 对齐）；【P1-8/P1-10】消费流动性 Skill 的"板块资金迁徙"与"黄白线双向背离"字段 | 专家7组 |
| **2026-07-11** | **1.0.1** | **§4.4.4暴涨过滤器涨幅阈值修正（与流动性Skill v1.2.1规则14.5同步）**：【P1】§4.4.4 暴涨后回撤过滤器涨幅触发阈值由 `>5%` 下调至 `≥4.5%`，覆盖两创板块4-5%中阳假突破场景。与流动性Skill规则14.5保持对齐。示例和changelog同步更新 | 专家7组 |

---

*最后更新：2026-07-11*
*维护者：专家7组（风控）*
*版本：v1.0.1*
