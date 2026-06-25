---
name: valuation_bubble_monitor
description: 估值泡沫风险预警分析。基于动态股权风险溢价(ERP)、巴菲特指标(Buffett Indicator)和反弹高位/顶部过滤器，对市场整体估值水平进行泡沫识别、低估机会识别与短期误判防护。当需要判断某个市场是偏贵、合理还是偏低估，或低估信号是否被短期过热抵消时触发。支持"简化模式"（仅需指数PE分位数和股息率）和"完整模式"（含无风险利率和巴菲特指标），根据可用数据自动降级。
owner_group: 专家7组（风控）
domain: valuation
status: draft
version: 0.6
last_updated: 2026-06-23
git_branch: skill/valuation-bubble-monitor
---

# 估值泡沫风险预警分析

> **架构映射**
> - 本 Skill 路径：`skills/valuation/valuation_bubble_monitor/SKILL.md`
> - 对应 Agent 目录：`agents/research/valuation/bubble_monitor/`（开发2组实现）
> - 参考文档：`references/valuation_bubble_model.md`
> - 与 Agent 矩阵中现有估值 Agent（PE/PB/PS/PEG/Cycle）的区别：本 Skill 面向**市场整体估值泡沫识别**，而非个股估值分位。现有估值 Agent 输出个股估值高低信号，本 Skill 输出市场级泡沫预警信号，可被风控层 Agent（仓位管理、黑天鹅预警等）引用。

## 1. 适用范围

所属小组：专家7组（风控）

适用任务：
- 判断目标市场（美股、A股、港股等）整体估值水平是否偏高或偏低
- 识别市场是否存在泡沫风险或错杀机会
- 为资产配置、仓位调整提供估值维度的风险提示

适合分析对象：
- 市场指数（标普500、沪深300、恒生指数等）
- 不适用于个股估值判断

适合时间周期：
- 中期（数周到数月）：适用于仓位调整决策
- 长期（数月到数年）：适用于战略资产配置

与 Agent 矩阵中其他估值 Skill 的关系：
- 现有估值 Agent（PE/PB/PS/PEG/Cycle）聚焦**个股估值分位**，判断单只股票是贵还是便宜
- 本 Skill 聚焦**市场整体泡沫识别**，判断整个市场是否存在系统性估值风险
- 两者互补：个股估值 Agent 判断选股，本 Skill 判断择时/仓位
- 本 Skill 的信号可被风控层 Agent（仓位管理、黑天鹅预警等）引用

边界说明：
- 本 Skill 输出的是市场整体估值判断，不构成个股投资建议
- 单一估值指标不足以作为交易依据，必须结合其他维度（技术面、资金面、基本面）综合判断
- 当历史数据不足 5 年，或市场结构发生根本性变化（如注册制改革、交易制度改革）时，结论需要人工复核
- ERP 和巴菲特指标均存在均值漂移问题，滚动窗口参数需定期（建议每季度）重算
- 本 Skill 面向市场指数级别分析，`stock_code` 留空，标的名称写在 `meta.target` 中
- **动态校准要求**：`meta.last_calibrated_date` 记录参数最后校准日期，若距今超过 90 天，必须在 `meta.uncertainties` 中标注"参数可能过期，建议重算"

## 2. 输入材料

### 2.1 必填输入

- 标的：市场名称（如"美股"、"A股"）或指数代码（如"^GSPC"、"000300.SS"）
- 时间范围：分析时点（默认为最新交易日）
- 核心数据材料（以下三项至少提供其中一项）：
  - 指数点位（收盘价）+ **指数市盈率（PE TTM）**：用于简化模式
  - 无风险利率（10 年期国债收益率）：用于完整 ERP 模式（**可选增强项**，见 2.2 节）
  - 市场盈利预测：可由指数市盈率倒推替代

> **运行模式自动选择**：
> - **简化模式**（默认）：仅需指数 PE TTM + 股息率，启用"纯 PE 分位数 + 股息率"简化估值模型（见 3.A 节）。
> - **完整模式**：在简化模式基础上额外提供无风险利率 + 巴菲特指标，启用 Damodaran 隐含 ERP 模型（见 3 节原完整步骤）。
> - 若仅提供无风险利率而缺少 GDP（无法算巴菲特指标），仍可运行简化 ERP 计算；巴菲特指标降级为"可选增强项"。

- 数据来源：东方财富（akshare `*_em` 系列接口）、中证指数公司（`stock_zh_index_value_csindex`）

### 2.2 可选增强输入

> 以下输入为**可选增强项**，缺失时不强制输出 neutral，而是按缺失程度降低 confidence 并切换到相应简化路径。

| 输入项 | 缺失时的处理 |
|-------|------------|
| 无风险利率（10年期国债收益率） | 切换至简化模式；若坚持 ERP 计算，对 A股允许使用固定假设值 1.7%（当前中债10年收益率近似值），对美股使用 4.4%，在 `meta.uncertainties` 中标注"无风险利率使用固定假设，非实时" |
| 股市总市值 / GDP（巴菲特指标） | 巴菲特指标信号跳过；仅使用 ERP/PE 分位数判断，在 `meta.uncertainties` 中标注"巴菲特指标不可用，已跳过" |
| 席勒市盈率（Shiller P/E） | 跳过；`confidence` 降低 0.05 |
| 市场拥挤度指标 | 跳过；`confidence` 降低 0.05 |
| 保证金债务水平 | 跳过 |
| 市场宽度指标（上涨家数/下跌家数） | 跳过 |
| 指数 20/60 日涨跌幅、距离 60 日高点比例、相对 20/60 日均线偏离度 | 顶部过滤器降级为不可用，bullish 信号 `confidence` 不得超过 0.65，需设 `needs_human_review: true` |
| 反弹过程中的成交额/换手率、融资余额、北向资金或主力资金方向 | 跳过；`confidence` 降低 0.1 |
| 动量/过热指标（RSI、Bollinger %B、上涨家数占比、强势股占比等） | 跳过；`confidence` 降低 0.05 |
| 历史类似时期对比 | 跳过 |
| 专家人工判断 | 跳过 |
| **liquidity_risk_signal** | 流动性风险 Skill 的原始输出 JSON，用于执行**流动性否决逻辑**（见 4.5 极端事件熔断逻辑中的"流动性危机否决"条款）。缺失时跳过否决检查 |

### 2.3 缺失处理

- **仅缺少无风险利率**：不输出 neutral，改为使用固定假设值（A股 1.7%、美股 4.4%），在 `meta.uncertainties` 中标注，`confidence` 降低 0.1。
- **仅缺少 GDP / 巴菲特指标**：跳过巴菲特指标信号，仅用 ERP Z-score 或 PE 分位数判断，`confidence` 降低 0.1。
- **同时缺少无风险利率和 GDP**：自动切换简化模式（PE 分位数 + 股息率），`confidence` 基础值 0.5-0.65，`meta.uncertainties` 写明"使用简化模式"。
- **指数 PE TTM 也缺失**：无法分析，输出 `direction: "neutral"`，`confidence: 0.3`，`needs_human_review: true`，写明关键数据完全缺失。
- **盈利预测数据缺失**：使用指数市盈率倒推近似盈利，在 `meta.uncertainties` 中说明，`confidence` 降低 0.1。
- **可选增强输入缺失**：按上表处理，继续分析。

### 自动化免责声明注入

以下规则在 `build_signal_output` 中**自动执行**，无需人工触发：

- **2026 年宏观特殊性声明**：如果当前分析时间处于 2025-2026 年周期，且 `needs_human_review` 不为 `True`，则在 `meta.uncertainties` 数组末尾自动追加：
  > `"2026年宏观环境特殊性：当前处于高波动地缘/利率周期，历史回测数据的有效性可能降低，建议结合实时新闻研判。"`
  
  目的：作为兜底提示，防止模型在特殊年份盲目自信。如果 `needs_human_review` 已经为 `True`（说明已有其他风险触发人工复核），则不重复追加，避免噪音。

## 3. 分析步骤

### 3.A 简化模式（数据管道可获取，推荐默认路径）

当无风险利率或 GDP 数据不可用时，自动进入简化模式，使用以下替代指标：

**步骤一：PE 历史分位数判断**

- 获取指数最新 PE TTM（akshare `stock_index_pe_lg` 或等效接口）
- 计算当前 PE 在近 5 年（约 1250 个交易日）历史分布中的分位数
- 分位判断规则：

| PE 分位数 | direction | 含义 | confidence 基础值 |
|-----------|-----------|------|-----------------|
| < 20% 分位（极低估） | bullish | 历史性低估区域 | 0.65-0.75 |
| 20%-40% 分位（偏低估） | bullish | 性价比偏高 | 0.55-0.65 |
| 40%-60% 分位（中性） | neutral | 估值处于常态区间 | 0.50-0.60 |
| 60%-80% 分位（偏贵） | bearish | 性价比降低 | 0.55-0.65 |
| > 80% 分位（极贵） | bearish | 历史性高估区域 | 0.65-0.75 |

**补充：EPS 动量修正系数（v0.5新增）**

> **背景**：简化模式仅依赖 PE 分位数判断估值高低，在盈利急剧变化时产生滞后偏差。
> 例如：2020年Q1疫情，EPS骤降导致PE被动飙升，简化模式误判为"极贵"而看空，
> 但实际上是大类资产错杀机会（需要结合盈利预期修正）。

**计算步骤**：

1. 计算当季 EPS 同比变化率（EPS YoY）：
   - 数据来源：通过 akshare 指数 PE 和点位倒推 EPS 的季度同比
   - 计算公式：`EPS_YoY = (EPS_current_quarter / EPS_same_quarter_last_year) - 1`
   - 若 EPS 季度数据不可得，允许使用 `g`（步骤三中定义的3年EPS复合增长率）作为近似替代
   - 若两者均不可得，跳过本修正，在 `meta.uncertainties` 中标注"EPS动量修正系数数据不可用"

2. 修正规则（仅当 PE 分位数 > 80% 时生效；PE 分位数 ≤ 80% 时不修正）：

| PE 分位数 | EPS YoY | 修正后 direction | confidence 调整 | meta.risk_notes 写入 |
|-----------|----------|------------------|---------------------|---------------------|
| > 80%（极贵） | < -5%（盈利大幅下滑） | 降级为 neutral | 基础值 × 0.8（上限0.6） | "PE高估主要由盈利下滑驱动，非纯粹情绪泡沫，需区分对待" |
| > 80%（极贵） | > +10%（盈利强劲） | 强化 bearish | 基础值 +0.1（上限0.9） | "PE高估由盈利强劲支撑，但估值仍处历史极贵区域，泡沫风险高" |
| > 80%（极贵） | -5% ~ +10% | 不变 | 不变 | 无 |
| ≤ 80% | 任意 | 不变 | 不变 | 无 |

**输出要求**：
- 若触发修正（EPS YoY < -5% 且 PE > 80%），必须在 `meta.risk_notes` 中写入说明
- 若 EPS YoY 数据不可用，在 `meta.uncertainties` 中记录"EPS动量修正系数数据不可用，未执行盈利衰退型高PE识别"
- 修正后的 direction 和 confidence 作为后续步骤的输入（修正后的方向参与股息率共振验证）

**示例**：
- 2015年6月：PE分位85%，EPS_YoY = +15%
  → 强化 bearish，confidence 0.75 → 0.85，判定为"真正的泡沫"
- 2020年Q1：PE分位88%，EPS_YoY = -25%
  → 降级为 neutral，confidence 0.75 × 0.8 = 0.60，判定为"盈利衰退型高PE，非纯粹泡沫"

**步骤二：股息率辅助验证**

- 获取指数股息率（Dividend Yield，akshare 可获取）
- 与历史均值对比：
  - 股息率显著低于历史均值（< 均值 × 0.7）→ 支持 bearish 信号
  - 股息率显著高于历史均值（> 均值 × 1.3）→ 支持 bullish 信号
  - 如两者共振，confidence 提高 0.05-0.10

**步骤三：名义盈利增长率 g（简化模式用法）**

- 简化模式中 g 不参与显式 ERP 计算，但可用于判断 PE 估值合理性参考上界
- g 来源改为：**滚动 3 年指数 EPS 复合增长率**（= 用指数 PE 和点位倒推 EPS，3 年 CAGR）
  - 计算公式：`g = (EPS_now / EPS_3y_ago)^(1/3) - 1`
  - 若 EPS 历史数据可通过 akshare 获取（如 `stock_index_pe_lg`），优先使用
  - 若不可得，允许使用固定假设 3%（全球长期默认），并在 `meta.uncertainties` 中标注"g 使用默认假设 3%，非实时 EPS CAGR"
- **不再使用 GDP 增速作为 g**（GDP 滞后、需全市场遍历，数据管道不友好）

**步骤四：顶部过滤器 + 熔断检查**

- 与完整模式相同，执行 4.4 短期顶部/反弹高位过滤器
- 与完整模式相同，执行 4.5 极端事件熔断逻辑（含流动性危机否决）

**简化模式输出标注**：
- `meta.valuation_mode: "simplified"`（简化模式标记）
- `meta.uncertainties` 写入："简化模式运行：仅使用 PE 分位数 + 股息率，未计算完整 ERP 和巴菲特指标，结论可信度低于完整模式"

---

按下面步骤分析（**完整模式**）：

1. **明确分析对象和时间范围**：确认目标市场、指数、分析时点。
2. **检查输入数据是否足够，确定运行模式**：
   - 若无风险利率或 GDP 均不可用 → 切换 **简化模式**（见 3.A 节），跳过步骤3-4
   - 若无风险利率可用但 GDP 不可用 → 仅计算 ERP，跳过巴菲特指标
   - 若均可用 → 完整模式
3. **计算隐含股权风险溢价（Implied ERP）**：
   - 基于 Damodaran 前瞻性隐含 ERP 模型，使用盈利收益率法
   - 盈利收益率 E/P = 1/PE（百分比）
   - 隐含回报率 = E/P + g（g 为名义盈利增长率）
   - 隐含 ERP = 隐含回报率 - 无风险利率
   - 如果缺少精确盈利预期，使用指数市盈率倒推近似盈利（需在 uncertainties 中标注）
   - **名义盈利增长率 g 的来源**：优先使用**滚动 3 年指数 EPS 复合增长率**（`g = (EPS_now / EPS_3y_ago)^(1/3) - 1`，通过 akshare 指数 PE 历史数据倒推），替代原来的滞后 GDP 增速；若 EPS 历史数据不可得，允许使用 3% 全球长期默认值，并在 `meta.uncertainties` 中注明"g 使用默认假设 3%"。
4. **计算巴菲特指标（Buffett Indicator）**（可选增强，数据可用时执行）：
   - 巴菲特指标 = (股市总市值 / GDP) × 100%
   - 市值和 GDP 必须使用同一币种
   - 若 GDP 数据不可用，跳过本步骤，在 `meta.uncertainties` 中标注"巴菲特指标不可用，已跳过"
5. **历史标准化处理（Z-score）**：
   - 对 ERP 计算 Z-score：Z = (当前值 - 滚动历史均值) / 滚动历史标准差
   - 滚动窗口：基于 2021-2026 最新 5 年滚动数据（约 1250 个交易日）
   - 如果历史数据不足 5 年，使用全部可用数据计算，并在 uncertainties 中标注
6. **生成基础估值方向**：
   - 完整模式：根据 ERP Z-score 和巴菲特指标的信号，先生成基础估值方向。
   - 简化模式：根据 PE 分位数 + 股息率共振生成基础估值方向（见 3.A 节）。
7. **执行短期顶部/反弹高位过滤器**：对基础 bullish 信号进行技术面和资金面反证检查。若市场已经在短期快速反弹、接近阶段高位，且出现市场宽度或资金流背离，则不得直接输出中期 bullish，必须降级为 neutral 或提示顶部风险。
8. **多维共振验证**：结合两个估值指标和顶部过滤器的信号强度，确认结论的可信度。单一估值低估信号不构成充分择时依据。
9. **极端事件熔断检查**：检查恐慌指数是否触发 Black Swan 熔断阈值——美股使用 VIX，A股使用沪深300 QVIX，港股使用 VHSI（恒指波幅指数）。如果触发，强制降级 confidence 和设置 needs_human_review。同时检查 20 日滚动涨幅是否触发软预警。
10. **标注不确定性和人工复核点**：写明数据缺失、近似计算、结构性变化等需要注意的地方。
11. **输出标准 JSON**：按照 `agents.signal.Signal` 格式输出，包含 `last_calibrated_date` 字段。

## 4. 判断规则

### 4.1 隐含 ERP Z-score 判断规则

| ERP Z-score | direction | 信号含义 | confidence 范围 |
|---|---|---|---|
| Z < -2 | bearish | 泡沫预警：股票相对债券失去性价比，市场过热 | 0.6-0.9 |
| -2 ≤ Z < -1 | bearish | 偏贵关注：性价比降低，需警惕 | 0.5-0.7 |
| -1 ≤ Z ≤ +1 | neutral | 中性合理：估值处于常态区间 | 0.5-0.7 |
| +1 < Z ≤ +2 | bullish | 偏宜关注：性价比提升，值得关注 | 0.5-0.7 |
| Z > +2 | bullish | 错杀/黄金坑：极度悲观，可能是底部区域 | 0.6-0.9 |

**规则说明**：
- Z-score < -2 时，如果同时巴菲特指标 > 100%，confidence 可以提高到 0.8-0.9
- Z-score > +2 时，如果同时巴菲特指标 < 75%，confidence 可以提高到 0.8-0.9
- 如果缺少历史数据无法计算 Z-score，仅使用 ERP 绝对值判断时，confidence 降低 0.2
- **Z-score 均值漂移动态调整**：2024-2026 年全球利率环境发生显著变化——美国10年期国债收益率从 2020 年的 ~0.9% 上升至 2026 年的 ~4.4%，中国10年期从 ~3.2% 降至 ~1.75%。无风险利率的系统性变化导致 ERP 均值发生结构性漂移：**高利率环境下 ERP 均值下移**（分母变大），低利率环境下 ERP 均值上移。因此，Z-score 计算必须基于 **2021-2026 滚动窗口**，而非更早的历史数据，以避免将 2015-2020 低利率时期的 ERP 均值应用于当前高利率环境。每季度需审查一次窗口参数，并在 `meta.uncertainties` 中记录漂移调整说明。

### 4.2 巴菲特指标判断规则

| 巴菲特指标 | direction | 信号含义 | confidence 范围 |
|---|---|---|---|
| < 75% | bullish | 低估：市值低于实体经济规模 | 0.6-0.8 |
| 75% - 100% | bullish | 合理偏低估：处于合理区间 | 0.5-0.7 |
| 100% - 150% | bearish | 过热：市值显著超过实体经济 | 0.5-0.7 |
| > 150% | bearish | 极端泡沫：完全脱离基本面 | 0.7-0.9 |

**规则说明**：
- 不同市场的估值中枢存在差异，跨市场比较时需谨慎
- **A股适配**：根据 2026 年市场结构，若直接融资比例显著提升（如超过社会融资规模的 30%），阈值可适度调整，但不再默认上浮。2025 年 A 股直接融资比例约 25%，仍低于成熟市场水平，巴菲特指标中枢可暂维持全球标准阈值（75%/150%），无需上浮。若后续直接融资比例出现系统性跃升，需重新校准阈值并在 `meta.last_calibrated_date` 中更新。**程序化说明**：该直接融资比例需每年由专家7组更新一次，若未更新则沿用最近校准值，并在 `meta.uncertainties` 中提示"直接融资比例阈值可能未更新"。
- **港股适配**：港股巴菲特指标受南下资金持续流入影响，定价权逐步从外资向南移。需结合人民币汇率预期进行修正：若人民币处于贬值预期通道，南下资金购买力增强，巴菲特指标可能被动抬高（港币计价市值上升），此时阈值可适度上浮 10-15 个百分点；若人民币处于升值预期，则维持标准阈值。修正因子需在 `meta.uncertainties` 中标注。**程序化说明**：默认不考虑人民币汇率预期修正。如需修正，由人工输入修正因子（+10%～+15%），`confidence` 降低 0.1，`meta.uncertainties` 记录修正幅度与依据。

### 4.3 多维共振验证规则

| ERP 信号 | 巴菲特指标 | 微观辅助信号 | direction | confidence | risk_level |
|---|---|---|---|---|---|
| 🔴 泡沫预警 (Z < -2) | 🔴 极端泡沫 (>150%) | 确认 | bearish | 0.9-1.0 | high |
| 🔴 泡沫预警 (Z < -2) | 🟡 过热 (100%-150%) | 确认 | bearish | 0.8-0.9 | medium |
| 🔴 泡沫预警 (Z < -2) | 🟢/🟡 | 未确认 | bearish | 0.6-0.7 | medium |
| 🟡 偏贵 (-2 ≤ Z < -1) | 🔴 极端泡沫 (>150%) | 确认 | bearish | 0.8-0.9 | high |
| 🟡 偏贵 (-2 ≤ Z < -1) | 🟡 过热 (100%-150%) | 确认 | bearish | 0.7-0.8 | medium |
| 🟡 偏贵 (-2 ≤ Z < -1) | 🟢/🟡 | 未确认 | bearish | 0.5-0.6 | low |
| 🔵 黄金坑 (Z > +2) | 🟢 低估 (<75%) | 确认 | bullish | 0.8-0.9 | medium |
| 🟢 中性 (-1 ≤ Z ≤ +1) | 🟢/🟡 | 无关紧要 | neutral | 0.5-0.7 | low |

**规则说明**：
- 微观辅助信号包括：席勒市盈率、市场拥挤度、保证金债务水平、市场宽度背离等
- 如果微观辅助信号与宏观信号矛盾，confidence 降低 0.1-0.2，在 `meta.uncertainties` 中写明矛盾点
- 如果缺少微观辅助信号，confidence 降低 0.1，在 `meta.uncertainties` 中说明

### 4.4 短期顶部/反弹高位过滤器

本 Skill 是估值风险模型，不是单纯择时模型。估值低估只能说明中长期风险收益比改善，不能自动推出未来数周继续上涨。为避免 2022 年 6 月上旬 A 股这类“估值仍低但反弹接近阶段高点”的误判，必须增加顶部过滤器。

#### 4.4.1 触发条件

当基础估值方向为 `bullish` 时，检查以下短期顶部风险因子：

| 因子 | 触发阈值 | 含义 |
|---|---|---|
| `index_return_20d` | > +8% | 短期反弹过快，估值低估已被部分修复 |
| `index_return_60d` | > +15% | 中期反弹幅度过大，接近阶段性兑现区 |
| `distance_to_60d_high` | ≤ 3% | 指数接近 60 日高点或阶段高点 |
| `ma20_deviation` | > +6% | 明显偏离 20 日均线，短期超买 |
| `rsi14` | > 70 | 动量过热 |
| `market_breadth_divergence` | true | 指数上涨但上涨家数、强势股占比或新高家数走弱 |
| `turnover_surge_without_breadth` | true | 成交额放大但宽度未同步扩散，疑似分歧放量 |
| `fund_flow_divergence` | true | 北向资金、融资余额或主力资金与指数上涨背离 |

触发判定：
- 触发 ≥ 2 个因子：启动顶部过滤器。
- 触发 ≥ 3 个因子，或同时出现 `market_breadth_divergence` 与 `fund_flow_divergence`：强顶部过滤。
- 如果 A股/港股市场缺失上述技术面和资金面输入，且基础方向为 `bullish`，则按 PE 分位数分级调整 confidence 封顶值（见下表），并设置 `needs_human_review: true`。

| PE 分位数 | confidence 封顶值 | 处理逻辑 |
|-----------|------------------|----------|
| < 20%（极低估/偏低估） | 0.75 | 极低估时允许更高置信度，优先输出 bullish，顶部过滤器仅作参考 |
| 20%-40%（偏低估） | 0.65 | 维持原封顶 |
| 40%-60%（中性） | 0.55 | 适当降低 |
| > 60%（偏贵/极贵） | 0.50 | 技术面缺失时严格限制，避免追涨 |

**设计原则**：估值越便宜，对缺失的技术面数据的容忍度越高。极端低估区域（PE分位 < 20%）即使缺少技术面确认，仍可输出中等偏高的 bullish 置信度。

#### 4.4.2 过滤器效果

| 基础估值方向 | 顶部过滤器 | 最终 direction | confidence 处理 | risk_level |
|---|---|---|---|---|
| bullish | 未触发 | bullish | 按估值共振规则计算 | medium |
| bullish | 触发 | neutral | cap 到 0.45-0.55 | medium |
| bullish | 强触发 | neutral 或 bearish | cap 到 0.35-0.50 | medium/high |
| neutral | 触发 | neutral | 降低 0.1 | medium |
| bearish | 触发 | bearish | 可提高 0.05-0.10 | high |

输出要求：
- `signals` 必须包含 `"估值低估但短期反弹高位过滤器触发"` 或类似短句。
- `reasoning` 必须写明基础估值方向和顶部过滤器如何改变最终方向。
- `meta.risk_notes` 必须写入 `"估值低估不等于短期可追涨，等待回撤或宽度/资金确认"`。
- `meta.uncertainties` 必须写明缺失或使用的顶部过滤器输入。
- 建议在 `meta.market_state_filter` 中记录：

```json
{
  "triggered": true,
  "strength": "normal | strong",
  "flags": [],
  "adjustment": "bullish_to_neutral | bullish_to_bearish | none",
  "reason": ""
}
```

#### 4.4.3 A股 2022 年 6 月误判防护

当分析对象为 A股宽基指数，且分析日期处在 2022 年 4 月底至 7 月初这类政策/复工驱动反弹窗口时，如果出现以下组合：

```text
ERP Z-score > +1
巴菲特指标 < 100%
但 index_return_20d > +8% 或 index_return_60d > +15%
且 指数接近阶段高点 / 市场宽度背离 / 资金流背离 任一成立
```

不得输出高置信度 `bullish`。应输出：
- `direction: "neutral"`
- `confidence: 0.45-0.55`
- `risk_level: "medium"`
- `needs_human_review: true`

这类结论含义是：估值层面仍不贵，但短期追涨胜率不足，仓位层应等待回撤、二次放量确认或市场宽度修复。

### 4.5 极端事件熔断逻辑

**硬熔断（Black Swan）**：

当以下任一条件满足时，触发硬熔断：
- VIX 指数 > 40（美股极端恐慌）
- 沪深300 QVIX > 50（A股极端恐慌）
- VHSI（恒指波幅指数）> 45（港股极端恐慌）
- 发生已知的极端地缘政治事件（战争爆发、重大制裁、全球性疫情等）

> **地缘政治事件熔断说明**：地缘政治事件（战争、重大制裁、疫情等）无法由行情数据自动识别，需由新闻舆情 Agent 或人工标记传入 `external_blackswan_trigger` 参数；默认不启用此项检查。仅当 `external_blackswan_trigger = true` 时，才将地缘政治事件纳入硬熔断判定。

硬熔断后的处理：
- **强制设置** `confidence = 0.3`，`needs_human_review = True`
- `direction` 仍按 ERP Z-score 和巴菲特指标正常计算，但标注为"熔断状态"
- `meta.uncertainties` 中必须写入：`"Black Swan 熔断触发：VIX={vix值}/QVIX={qvix值}/VHSI={vhsi值}，极端市场环境下模型可靠性极低"`
- `meta.risk_notes` 中增加：`"极端事件熔断生效，所有信号仅供参考，必须由人工判断决定操作"`

**软预警（灰犀牛→黑天鹅过渡）**：

当以下条件满足时，触发软预警（仅设置 human review，不强制修改 confidence）：
- VIX 的 **20 日滚动涨幅 > 50%**（即 `(当前值 - 20日前值) / 20日前值 > 0.5`）
- 沪深300 QVIX 的 **20 日滚动涨幅 > 50%**
- VHSI 的 **20 日滚动涨幅 > 50%**（港股）
- 即使绝对值未达到硬熔断阈值（如 VIX 从 20 涨到 35），涨幅过快本身即构成风险信号

软预警后的处理：
- **仅设置** `needs_human_review = True`（不强制修改 `confidence`，保持原估值逻辑）
- `meta.uncertainties` 中写入：`"恐慌指数短期激增（VIX/QVIX/VHSI 20日涨幅>50%），市场波动率环境发生结构性突变，建议人工复核"`
- `meta.circuit_breaker` 中增加 `surge_warning: true` 和 `surge_pct` 字段记录涨幅百分比
- 如果软预警和硬熔断同时触发，硬熔断优先（软预警不再重复写入）

> **港股恐慌指数说明**：港股恒生指数使用 VHSI（恒指波幅指数）作为恐慌指数，硬熔断阈值 >45，20日涨幅 >50% 触发软预警。若无 VHSI 数据，则仅依赖全球 VIX 作为参考，并在 `meta.uncertainties` 中说明"VHSI 数据不可用，仅以 VIX 作为港股恐慌指数参考，判断精度可能受限"。

---

**流动性危机否决（Liquidity Veto）**：⚠️ 新增硬熔断规则（v0.4）

> 此条款与流动性风险 Skill 对接，解决"估值看多 vs 流动性看空"的系统死锁问题。

**触发条件**（需外部输入 `liquidity_risk_signal`）：
- `liquidity_risk_signal.risk_level == "high"` **且**
- `liquidity_risk_signal.liquidity_outlook == "negative"`

**执行逻辑**：
- 无论 ERP Z-score 或 PE 分位数多么极端（包括 Z > +2 的"黄金坑"信号），**强制将 `direction` 降级为 `"neutral"`**
- **`confidence` 封顶为 0.35**（不超过）
- 在 `meta` 中设置 `veto_reason: "流动性危机期间，估值信号延迟生效"`
- 在 `meta.circuit_breaker` 中增加 `liquidity_veto: true`
- 在 `signals` 中加入：`"流动性危机否决生效，估值看多信号暂缓，等待流动性恢复"`
- 在 `meta.risk_notes` 中加入：`"当前处于流动性危机状态（流动性 Skill 输出 high/negative），估值信号被标记为 deferred（延迟生效）。仅当 liquidity_risk_level 降至 medium 及以下时，本估值信号恢复有效"`
- `meta.uncertainties` 中写入：`"流动性否决机制触发（Liquidity Veto）：外部流动性风险信号为 high/negative，估值判断暂时失效"`

**否决与其他熔断的优先级**：
- Black Swan 硬熔断 > 流动性危机否决 > 软预警
- 若同时触发 Black Swan 和流动性否决，以 Black Swan 为主，同时追加 `liquidity_veto: true`

**缺失处理**：若 `liquidity_risk_signal` 未传入，跳过此项检查，不输出否决信号。

---

**系统仲裁规则（与流动性 Skill 的联动）**：

下表记录估值 Skill 与流动性 Skill 联动时的最终仲裁逻辑，供仲裁层和下游 Agent 参考：

| 场景 | 流动性 Skill 输出 | 估值 Skill 内部判断 | 估值 Skill 最终输出 | 系统仲裁方向 |
|------|-----------------|-------------------|-------------------|------------|
| 流动性危机（如2024年1月） | risk_level: high, outlook: negative | direction: bullish | direction: neutral（被否决），confidence ≤ 0.35，信号标记 deferred | **强制 neutral / bearish，估值信号 deferred** |
| 正常市场且估值极低 | risk_level: low, outlook: positive | direction: bullish, confidence: 0.8 | direction: bullish（正常输出） | **共振看多，正常 bullish** |
| 流动性良好但估值泡沫 | risk_level: low, outlook: positive | direction: bearish, confidence: 0.9 | direction: bearish（正常输出） | **共振看空，正常 bearish** |

---

**Neutral 信号细化规则**：

当 `direction = "neutral"` 时，`signals` 数组**必须**包含具体的信号冲突或中性原因，不能留空。分两种情况：

1. **信号矛盾型 neutral**：两个核心指标方向相反时
   - `signals` 必须包含：`"ERP 看涨信号（Z={z_val}）"` 和 `"巴菲特看跌信号（{buf_val}%）"`（或反之）
   - `reasoning` 必须写明矛盾原因：如"ERP Z-score 显示估值偏低，但巴菲特指标显示市场过热，信号矛盾导致中性判断"

2. **信号中性型 neutral**：两个核心指标均在中间区间时
   - `signals` 必须包含：`"ERP Z-score 处于[-1,+1]常态区间"` 和 `"巴菲特指标处于[75%,150%]合理区间"`
   - `reasoning` 写明：如"两个指标均未发出极端信号，估值处于常态区间"

### 4.6 从财经判断翻译成 Skill 规则

**财经判断**：
```
当股票市场的隐含ERP低于历史均值2个标准差以上，且巴菲特指标超过150%时，
市场存在明显泡沫风险，应该降低权益仓位。
```

**翻译成 Skill 规则**：

```text
指标1：隐含ERP Z-score
阈值：< -2
direction：bearish
confidence：0.7-0.9；如果巴菲特指标同时 > 150%，提高到 0.9-1.0
risk_level：medium；如果巴菲特指标同时 > 150%，升为 high
evidence：记录分析日期、ERP当前值、ERP历史均值、ERP Z-score、数据来源
needs_human_review：如果历史数据不足5年或市场发生结构性变化，设为 true

指标2：巴菲特指标
阈值：> 150%
direction：bearish
confidence：0.7-0.9；如果ERP Z-score同时 < -2，提高到 0.9-1.0
risk_level：high
evidence：记录分析日期、市值、GDP、巴菲特指标值、数据来源
needs_human_review：如果GDP数据存在明显时滞，设为 true

共振规则：
条件：ERP Z-score < -2 且 巴菲特指标 > 150%
direction：bearish
confidence：0.9-1.0
risk_level：high
needs_human_review：如果缺少微观辅助信号，设为 true
```

**财经判断**：
```
当隐含ERP远高于历史均值，且巴菲特指标低于75%时，
市场可能过度悲观，是逆向布局的机会。
```

**翻译成 Skill 规则**：

```text
指标1：隐含ERP Z-score
阈值：> +2
direction：bullish
confidence：0.7-0.9；如果巴菲特指标同时 < 75%，提高到 0.8-0.9
risk_level：medium（市场可能继续下跌，虽是机会但仍有风险）
evidence：记录分析日期、ERP当前值、ERP历史均值、ERP Z-score、数据来源

指标2：巴菲特指标
阈值：< 75%
direction：bullish
confidence：0.6-0.8；如果ERP Z-score同时 > +2，提高到 0.8-0.9
risk_level：medium
evidence：记录分析日期、市值、GDP、巴菲特指标值、数据来源

共振规则：
条件：ERP Z-score > +2 且 巴菲特指标 < 75%
direction：bullish
confidence：0.8-0.9
risk_level：medium
needs_human_review：如果市场存在流动性危机等极端事件，设为 true
```

## 5. 标准输出

最终输出 JSON，顶层字段与当前项目 `agents.signal.Signal` 对齐。

```json
{
  "direction": "bullish | bearish | neutral",
  "confidence": 0.0,
  "reasoning": "",
  "signals": [],
  "source": "valuation_bubble_monitor",
  "signal_type": "valuation",
  "stock_code": "",
  "weight": 1.0,
  "meta": {
    "output_version": "0.5",
    "skill_name": "valuation_bubble_monitor",
    "owner_group": "专家7组（风控）",
    "target": "",
    "period": "",
    "time_horizon": "mid | long",
    "risk_level": "low | medium | high",
    "valuation_mode": "simplified | full",
    "pe_percentile": null,
    "last_calibrated_date": "",
    "veto_reason": null,
    "key_findings": [],
    "evidence": [
      {
        "source_type": "market_data | macro_data | research_report | expert_input",
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
    "needs_human_review": false,
    "market_state_filter": {
      "triggered": false,
      "strength": "normal | strong",
      "flags": [],
      "adjustment": "none | bullish_to_neutral | bullish_to_bearish",
      "reason": ""
    },
    "circuit_breaker": {
      "triggered": false,
      "reason": "",
      "vix": null,
      "qvix": null,
      "surge_warning": false,
      "surge_pct": null,
      "liquidity_veto": false
    }
  }
}
```

### 各字段如何产生

- **direction**：
  - 完整模式：由 ERP Z-score 和巴菲特指标通过判断规则（第 4 节）联合确定。两个指标共振时取一致方向；矛盾时输出 `neutral`，`signals` 必须包含冲突原因。
  - 简化模式：由 PE 分位数 + 股息率共振确定。
  - 流动性否决激活时：强制降级为 `"neutral"`，无论原始信号方向。
- **confidence**：由共振程度决定。两个指标共振确认时 0.8-1.0；单一指标信号时 0.5-0.7；数据缺失或信号矛盾时 0.3-0.5。Black Swan 熔断时强制 0.3。流动性否决激活时封顶 0.35。
- **reasoning**：简明推理摘要，写明估值核心指标值、是否共振、最终方向判断。neutral 时必须写明矛盾原因或否决原因。
- **signals**：最核心的 2-4 条信号短句。**neutral 时必须包含具体冲突原因**，不能留空。流动性否决激活时必须包含否决原因。
- **source**：固定写 `"valuation_bubble_monitor"`。
- **signal_type**：固定写 `"valuation"`。
- **stock_code**：本 Skill 面向市场指数级别分析，留空。标的名称写在 `meta.target` 中。
- **weight**：先填 1.0，后续由仲裁层决定。

### Agent 调用说明

开发2组在实现对应 Agent 时，按以下流程调用本 Skill：

1. **加载 Skill**：读取 `skills/valuation/valuation_bubble_monitor/SKILL.md` 作为 system prompt
2. **获取数据**：通过 `scripts/fetch_data.py` 从东方财富（akshare `*_em` 接口）获取指数点位、市盈率、无风险利率、市值、GDP 等数据
3. **调用 LLM 或规则逻辑**：将 Skill 内容和输入数据传给模型，按判断规则输出 JSON
4. **防御性校验与封装 Signal**：
   a. 在执行 `Signal.from_dict()` 之前，对 `signals` 字段做防御性校验：
      - **类型校验**：如果 `signals` 是字符串（`str`），强制转换为单元素数组 `[signal_str]`
      - **空值校验**：如果 `signals` 为空列表或解析失败，**且** `direction` 不为 `neutral`，则强制设置 `signals = ["估值信号生成失败，已降级为中性"]` 并将 `direction` 降级为 `neutral`
      - **严禁因 `signals` 格式错误导致整个 Agent 流程崩溃**，必须 fallback 到安全状态
   b. 使用 `Signal.from_dict()` 解析 JSON，出错时 fallback 到 `neutral_signal()`
5. **注册到调试 UI**：在 `debug_ui/app.py` 的 `AVAILABLE_AGENTS` 中添加条目

对应 Agent 实现目录：`agents/research/valuation/bubble_monitor/`

### meta 各字段如何产生

- **valuation_mode**：`"simplified"` 表示简化模式（PE 分位数 + 股息率），`"full"` 表示完整模式（ERP + 巴菲特指标）。
- **time_horizon**：估值均值回归通常需要数周到数月，默认 `"mid"`；如果是战略资产配置场景，设为 `"long"`。
- **risk_level**：由共振强度和极端程度决定。极端泡沫/黄金坑为 `"high"`；偏贵/偏宜为 `"medium"`；中性为 `"low"`。
- **veto_reason**：仅在流动性否决激活时填写，固定值 `"流动性危机期间，估值信号延迟生效"`；否则为 `null`。
- **last_calibrated_date**：记录模型参数（Z-score 窗口、巴菲特指标阈值等）最后一次校准的日期。**维护要求**：每次修改阈值或滚动窗口参数时必须更新此字段；运行时若距今超过 90 天，在 `uncertainties` 中标注参数可能过期。
- **key_findings**：最重要的 1-5 条结论短句，从估值指标和共振判断中提取。
- **evidence**：每条证据记录 source_type（数据来源类型）、source_name（数据源名称）、date（日期）、metric（指标名）、value（指标值）、comparison（对比说明）、note（解读）。
- **risk_notes**：风险提示和行动建议，从预警分级规则中提取。
- **uncertainties**：数据缺失、口径不一致、市场结构性变化等不确定因素。
- **needs_human_review**：当数据缺失、信号矛盾、市场结构性变化、缺少微观辅助信号验证、Black Swan 熔断触发、或流动性否决激活时，设为 `true`。
- **market_state_filter**：记录短期顶部/反弹高位过滤器状态。若估值基础方向为 bullish 但过滤器触发，必须记录触发因子、强度和方向调整。
- **circuit_breaker**：记录极端事件熔断状态。`triggered` 是否触发，`reason` 触发原因，`vix`/`qvix` 当前恐慌指数值，`surge_warning` 是否触发软预警（VIX/QVIX/VHSI 20日涨幅>50%），`surge_pct` 软预警触发时的涨幅百分比，**`liquidity_veto`** 是否触发流动性危机否决（默认 `false`）。

### 输出示例

**示例1：泡沫预警（双指标共振）**

```json
{
  "direction": "bearish",
  "confidence": 0.9,
  "reasoning": "美股标普500隐含ERP Z-score为-2.5，处于历史极低水平，股票相对债券失去性价比；巴菲特指标为168%，远超150%极端泡沫阈值。两个指标共振确认泡沫风险。",
  "signals": [
    "隐含ERP Z-score < -2，泡沫预警",
    "巴菲特指标 > 150%，极端泡沫",
    "双指标共振确认，高确信度泡沫风险"
  ],
  "source": "valuation_bubble_monitor",
  "signal_type": "valuation",
  "stock_code": "",
  "weight": 1.0,
  "meta": {
    "output_version": "0.5",
    "skill_name": "valuation_bubble_monitor",
    "owner_group": "专家7组（风控）",
    "target": "美股/标普500",
    "period": "2026-05-04",
    "time_horizon": "mid",
    "risk_level": "high",
    "valuation_mode": "full",
    "last_calibrated_date": "2026-04-30",
    "veto_reason": null,
    "key_findings": [
      "隐含ERP Z-score为-2.5，市场严重过热",
      "巴菲特指标168%，处于极端泡沫区域",
      "双指标共振确认，泡沫风险可信度高"
    ],
    "evidence": [
      {
        "source_type": "market_data",
        "source_name": "东方财富/新浪财经",
        "date": "2026-05-04",
        "metric": "隐含ERP Z-score",
        "value": "-2.5",
        "comparison": "低于历史均值2.5个标准差",
        "note": "股票相对债券失去性价比，市场过热"
      },
      {
        "source_type": "macro_data",
        "source_name": "东方财富/美联储经济数据",
        "date": "2026-Q1",
        "metric": "巴菲特指标",
        "value": "168%",
        "comparison": "超过150%极端泡沫阈值",
        "note": "市值完全脱离实体经济基本面"
      }
    ],
    "risk_notes": [
      "高确信度泡沫风险，建议逐步降低权益仓位至60-70%",
      "增加防御性资产配置（债券、黄金）",
      "考虑使用对冲工具（股指期货、期权）"
    ],
    "uncertainties": [
      "2026年宏观环境特殊性：当前处于高波动地缘/利率周期，历史回测数据的有效性可能降低，建议结合实时新闻研判。"
    ],
    "needs_human_review": false,
    "circuit_breaker": {
      "triggered": false,
      "reason": "",
      "vix": 22.5,
      "qvix": null,
      "surge_warning": false,
      "surge_pct": null,
      "liquidity_veto": false
    }
  }
}
```

**示例2：估值合理（中性，信号一致中性）**

```json
{
  "direction": "neutral",
  "confidence": 0.6,
  "reasoning": "美股标普500隐含ERP Z-score为-0.3，处于历史常态区间；巴菲特指标为92%，处于合理范围。两个指标均未发出极端信号，估值处于常态区间。",
  "signals": [
    "ERP Z-score 处于[-1,+1]常态区间（Z=-0.3）",
    "巴菲特指标处于[75%,150%]合理区间（92%）",
    "两个指标均未发出极端信号，估值均衡"
  ],
  "source": "valuation_bubble_monitor",
  "signal_type": "valuation",
  "stock_code": "",
  "weight": 1.0,
  "meta": {
    "output_version": "0.5",
    "skill_name": "valuation_bubble_monitor",
    "owner_group": "专家7组（风控）",
    "target": "美股/标普500",
    "period": "2026-05-04",
    "time_horizon": "mid",
    "risk_level": "low",
    "last_calibrated_date": "2026-04-30",
    "key_findings": [
      "隐含ERP Z-score为-0.3，中性合理",
      "巴菲特指标92%，处于合理区间"
    ],
    "evidence": [
      {
        "source_type": "market_data",
        "source_name": "东方财富/新浪财经",
        "date": "2026-05-04",
        "metric": "隐含ERP Z-score",
        "value": "-0.3",
        "comparison": "处于[-1,+1]常态区间",
        "note": "估值合理"
      },
      {
        "source_type": "macro_data",
        "source_name": "东方财富/美联储经济数据",
        "date": "2026-Q1",
        "metric": "巴菲特指标",
        "value": "92%",
        "comparison": "低于100%合理阈值",
        "note": "市值与实体经济基本匹配"
      }
    ],
    "risk_notes": [],
    "uncertainties": [
      "缺少微观辅助信号（席勒P/E、市场拥挤度等）验证",
      "2026年宏观环境特殊性：当前处于高波动地缘/利率周期，历史回测数据的有效性可能降低，建议结合实时新闻研判。"
    ],
    "needs_human_review": false,
    "circuit_breaker": {
      "triggered": false,
      "reason": "",
      "vix": 18.3,
      "qvix": null,
      "surge_warning": false,
      "surge_pct": null
    }
  }
}
```

**示例3：黄金坑（双指标共振看多）**

```json
{
  "direction": "bullish",
  "confidence": 0.85,
  "reasoning": "沪深300隐含ERP Z-score为+2.3，远高于历史均值，市场极度悲观；巴菲特指标为62%，低于75%低估阈值。两个指标共振确认逆向买入机会。",
  "signals": [
    "隐含ERP Z-score > +2，黄金坑预警",
    "巴菲特指标 < 75%，市场低估",
    "双指标共振确认，逆向买入机会"
  ],
  "source": "valuation_bubble_monitor",
  "signal_type": "valuation",
  "stock_code": "",
  "weight": 1.0,
  "meta": {
    "output_version": "0.5",
    "skill_name": "valuation_bubble_monitor",
    "owner_group": "专家7组（风控）",
    "target": "A股/沪深300",
    "period": "2026-05-04",
    "time_horizon": "mid",
    "risk_level": "medium",
    "last_calibrated_date": "2026-04-30",
    "key_findings": [
      "隐含ERP Z-score为+2.3，市场极度悲观",
      "巴菲特指标62%，处于低估区域",
      "双指标共振确认，存在逆向买入机会"
    ],
    "evidence": [
      {
        "source_type": "market_data",
        "source_name": "东方财富/中证指数公司",
        "date": "2026-05-04",
        "metric": "隐含ERP Z-score",
        "value": "+2.3",
        "comparison": "高于历史均值2.3个标准差",
        "note": "股票相对债券性价比极高"
      },
      {
        "source_type": "macro_data",
        "source_name": "东方财富/国家统计局",
        "date": "2025",
        "metric": "巴菲特指标",
        "value": "62%",
        "comparison": "低于75%低估阈值",
        "note": "市值低于实体经济规模"
      }
    ],
    "risk_notes": [
      "市场可能继续下跌（左侧布局风险）",
      "建议分批建仓，优先选择质量因子高的标的",
      "注意控制仓位，避免单次重仓"
    ],
    "uncertainties": [
      "市场可能存在流动性危机等极端事件导致继续下跌",
      "2026年宏观环境特殊性：当前处于高波动地缘/利率周期，历史回测数据的有效性可能降低，建议结合实时新闻研判。"
    ],
    "needs_human_review": false,
    "circuit_breaker": {
      "triggered": false,
      "reason": "",
      "vix": null,
      "qvix": 25.8,
      "surge_warning": false,
      "surge_pct": null
    }
  }
}
```

**示例4：信号矛盾型 Neutral**

```json
{
  "direction": "neutral",
  "confidence": 0.4,
  "reasoning": "A股沪深300隐含ERP Z-score为+1.5，显示估值偏低；但巴菲特指标为125%，显示市场过热。ERP 看涨信号与巴菲特看跌信号矛盾，输出中性判断。",
  "signals": [
    "ERP 看涨信号（Z=+1.5，估值偏低）",
    "巴菲特看跌信号（125%，过热区间）",
    "信号矛盾，方向不确定"
  ],
  "source": "valuation_bubble_monitor",
  "signal_type": "valuation",
  "stock_code": "",
  "weight": 1.0,
  "meta": {
    "output_version": "0.5",
    "skill_name": "valuation_bubble_monitor",
    "owner_group": "专家7组（风控）",
    "target": "A股/沪深300",
    "period": "2026-05-04",
    "time_horizon": "mid",
    "risk_level": "medium",
    "last_calibrated_date": "2026-04-30",
    "key_findings": [
      "ERP Z-score +1.5，偏向低估",
      "巴菲特指标 125%，偏向过热",
      "双指标方向矛盾，信号不可靠"
    ],
    "evidence": [
      {
        "source_type": "market_data",
        "source_name": "东方财富/中证指数公司",
        "date": "2026-05-04",
        "metric": "隐含ERP Z-score",
        "value": "+1.5",
        "comparison": "高于历史均值1.5个标准差",
        "note": "估值偏低，性价比提升"
      },
      {
        "source_type": "macro_data",
        "source_name": "东方财富/国家统计局",
        "date": "2025",
        "metric": "巴菲特指标",
        "value": "125%",
        "comparison": "处于100%-150%过热区间",
        "note": "市值显著超过实体经济"
      }
    ],
    "risk_notes": [
      "信号矛盾，建议维持当前仓位，等待方向明确"
    ],
    "uncertainties": [
      "ERP与巴菲特指标信号方向矛盾",
      "缺少微观辅助信号验证"
    ],
    "needs_human_review": true,
    "circuit_breaker": {
      "triggered": false,
      "reason": "",
      "vix": null,
      "qvix": 28.5,
      "surge_warning": false,
      "surge_pct": null
    }
  }
}
```

**示例5：Black Swan 熔断**

```json
{
  "direction": "bearish",
  "confidence": 0.3,
  "reasoning": "美股标普500隐含ERP Z-score为-2.8，巴菲特指标175%。但VIX指数达45.2，触发Black Swan熔断，强制降级confidence，所有信号仅供参考。",
  "signals": [
    "隐含ERP Z-score < -2，泡沫预警",
    "巴菲特指标 > 150%，极端泡沫",
    "Black Swan 熔断触发（VIX=45.2），信号仅供参考"
  ],
  "source": "valuation_bubble_monitor",
  "signal_type": "valuation",
  "stock_code": "",
  "weight": 1.0,
  "meta": {
    "output_version": "0.5",
    "skill_name": "valuation_bubble_monitor",
    "owner_group": "专家7组（风控）",
    "target": "美股/标普500",
    "period": "2026-05-04",
    "time_horizon": "mid",
    "risk_level": "high",
    "last_calibrated_date": "2026-04-30",
    "key_findings": [
      "VIX=45.2，触发Black Swan熔断",
      "ERP Z-score -2.8，巴菲特指标175%，模型信号指向泡沫",
      "极端市场环境下模型可靠性极低，必须人工判断"
    ],
    "evidence": [
      {
        "source_type": "market_data",
        "source_name": "东方财富/新浪财经",
        "date": "2026-05-04",
        "metric": "隐含ERP Z-score",
        "value": "-2.8",
        "comparison": "低于历史均值2.8个标准差",
        "note": "股票相对债券失去性价比，市场严重过热"
      },
      {
        "source_type": "macro_data",
        "source_name": "东方财富/美联储经济数据",
        "date": "2026-Q1",
        "metric": "巴菲特指标",
        "value": "175%",
        "comparison": "超过150%极端泡沫阈值",
        "note": "市值完全脱离实体经济基本面"
      },
      {
        "source_type": "market_data",
        "source_name": "东方财富/新浪财经",
        "date": "2026-05-04",
        "metric": "VIX",
        "value": "45.2",
        "comparison": "超过40的熔断阈值",
        "note": "极端恐慌，模型可靠性极低"
      }
    ],
    "risk_notes": [
      "极端事件熔断生效，所有信号仅供参考，必须由人工判断决定操作",
      "VIX>40 表明市场进入恐慌模式，常规估值模型可能完全失效",
      "建议等待市场波动率回落后再重新评估"
    ],
    "uncertainties": [
      "Black Swan 熔断触发：VIX=45.2，极端市场环境下模型可靠性极低"
    ],
    "needs_human_review": true,
    "circuit_breaker": {
      "triggered": true,
      "reason": "VIX=45.2 > 40，触发Black Swan熔断",
      "vix": 45.2,
      "qvix": null,
      "surge_warning": false,
      "surge_pct": null
    }
  }
}
```

## 6. 质量检查

输出前检查：

- [ ] 是否有明确 `direction`（只能是 bullish / bearish / neutral 之一）
- [ ] `confidence` 是否在 0.0 到 1.0
- [ ] 是否写明 `signal_type`: "valuation"
- [ ] 是否有至少一条核心 `signals`
- [ ] 当 `direction = "neutral"` 时，`signals` 是否包含具体冲突原因（不能为空或仅写"中性"）
- [ ] 是否有证据来源（`meta.evidence` 至少一条核心估值指标）
- [ ] 是否标注时间周期（`meta.time_horizon`）
- [ ] 缺失数据是否写进 `meta.uncertainties`
- [ ] 是否需要人工复核（`meta.needs_human_review`）
- [ ] `meta.valuation_mode` 是否正确标注运行模式（simplified / full）
- [ ] 完整模式：两个指标信号是否经过共振验证
- [ ] 完整模式：`reasoning` 是否写明了 ERP Z-score 值和巴菲特指标值
- [ ] 简化模式：`reasoning` 是否写明了 PE 分位数和股息率
- [ ] `meta.last_calibrated_date` 是否已填写
- [ ] 是否检查了极端事件熔断（VIX/QVIX/VHSI）
- [ ] `meta.circuit_breaker.triggered` 是否正确反映熔断状态
- [ ] 是否检查了恐慌指数增速预警（VIX/QVIX/VHSI 20日涨幅 > 50% 时 `surge_warning` 是否标注）
- [ ] **是否检查了流动性危机否决（Liquidity Veto）**：若 `liquidity_risk_signal` 已传入且满足 high/negative 条件，`direction` 是否已降级为 neutral，`confidence` 是否封顶 0.35，`meta.circuit_breaker.liquidity_veto` 是否为 true
- [ ] **若触发流动性否决，`meta.veto_reason` 是否填写，`signals` 是否包含否决原因**
- [ ] 2025-2026年周期内，是否自动注入了宏观特殊性免责声明到 `meta.uncertainties`
- [ ] 当基础方向为 bullish 时，是否执行了短期顶部/反弹高位过滤器
- [ ] 如果顶部过滤器触发，是否将高置信度 bullish 降级为 neutral 或 bearish，并写入 `meta.market_state_filter`
- [ ] `signals` 字段是否通过防御性校验（非空、为数组类型）
- [ ] 名义盈利增长率 g 是否注明来源；若使用默认值 3%，是否在 `meta.uncertainties` 中标注；是否已切换为 EPS CAGR（不再使用 GDP 增速）
- [ ] 无风险利率缺失时，是否使用固定假设值并在 `uncertainties` 中标注（不再强制输出 neutral）
- [ ] 巴菲特指标缺失时，是否在 `uncertainties` 中标注"已跳过"（不再强制输出 neutral）
- [ ] 港股市场是否正确使用 VHSI；若 VHSI 不可用，是否在 `meta.uncertainties` 中说明
- [ ] 地缘政治事件熔断是否仅由外部 `external_blackswan_trigger` 参数触发（非自动识别）
- [ ] A 股直接融资比例是否每年更新；若未更新，是否在 `meta.uncertainties` 中提示
- [ ] 港股人民币汇率修正是否由人工输入，且 `confidence` 降低 0.1 并记录依据

---

## 测试样例

### 样例A（正面/看多）

```text
场景：A股沪深300
隐含ERP Z-score: +2.3
巴菲特指标: 62%
微观辅助信号: 席勒P/E处于历史低位
VIX/QVIX: QVIX=22（正常）

预期：
direction: bullish
confidence: 0.8-0.9
risk_level: medium
key_findings 包含"黄金坑"和"低估"相关描述
evidence 包含 ERP 和巴菲特指标各一条
circuit_breaker.triggered: false
```

### 样例B（负面/看空）

```text
场景：美股标普500
隐含ERP Z-score: -2.5
巴菲特指标: 168%
微观辅助信号: 市场宽度开始背离，保证金债务创新高
VIX: 22（正常）

预期：
direction: bearish
confidence: 0.9-1.0
risk_level: high
key_findings 包含"泡沫预警"和"极端泡沫"相关描述
risk_notes 包含降低仓位建议
circuit_breaker.triggered: false
needs_human_review: false
```

### 样例C（缺失数据）

```text
场景：港股恒生指数
隐含ERP Z-score: 无法计算（历史数据不足5年）
巴菲特指标: 98%
微观辅助信号: 无
VIX/QVIX/VHSI: 无数据

预期：
direction: neutral
confidence: 0.3-0.4
risk_level: low
meta.uncertainties 包含"历史数据不足"和"缺少微观辅助信号"和"VHSI 数据不可用"
signals 必须包含具体中性原因（如"ERP数据缺失无法判断方向"、"巴菲特指标98%处于合理区间"）
needs_human_review: true
```

### 样例D（信号矛盾）

```text
场景：A股沪深300
隐含ERP Z-score: +1.8（偏宜）
巴菲特指标: 135%（过热）
微观辅助信号: 无

预期：
direction: neutral
confidence: 0.35-0.45
signals 包含 "ERP 看涨信号" 和 "巴菲特看跌信号" 的具体矛盾描述
reasoning 明确写明矛盾原因
needs_human_review: true
```

### 样例E（Black Swan 熔断）

```text
场景：美股标普500
隐含ERP Z-score: -2.8
巴菲特指标: 175%
VIX: 48

预期：
direction: bearish（按指标计算）
confidence: 0.3（强制降级）
circuit_breaker.triggered: true
circuit_breaker.reason: "VIX=48 > 40，触发Black Swan熔断"
circuit_breaker.surge_warning: false（硬熔断优先，不重复写入软预警）
needs_human_review: true
uncertainties 包含"Black Swan 熔断触发"相关说明
evidence 包含 ERP、巴菲特指标、VIX 各一条
```

### 样例F（A股反弹高位过滤，2022-06-10 回归防护）

```text
场景：A股沪深300 / 上证指数联动观察
分析日期：2022-06-10
隐含ERP Z-score: +2.3
巴菲特指标: 68.4%
QIVX: 22（正常）
顶部过滤器输入：
  - index_return_20d: +9.5%
  - index_return_60d: +16.0%
  - distance_to_60d_high: 2.5%
  - turnover_surge_without_breadth: true
  - market_breadth_divergence: true

预期：
direction: neutral
confidence: 0.45-0.55
risk_level: medium
signals 必须包含"ERP/巴菲特估值看多"和"短期反弹高位过滤器触发"
reasoning 必须说明：估值低估信号被短期反弹过热和宽度背离抵消，不适合输出高置信度 bullish
meta.market_state_filter.triggered: true
meta.market_state_filter.adjustment: "bullish_to_neutral"
needs_human_review: true
risk_notes 包含"估值低估不等于短期可追涨"
```

### 样例G（简化模式 + 流动性否决，v0.4 新增）

```text
场景：A股沪深300，免费数据管道（无法获取实时无风险利率和总市值/GDP）
PE TTM分位数: 近5年 18%（极低估区域）
股息率: 3.2%（高于历史均值 × 1.35，支持bullish）
liquidity_risk_signal: { risk_level: "high", liquidity_outlook: "negative" }
QVIX: 35（未触发硬熔断）

预期：
meta.valuation_mode: "simplified"
基础方向（未否决前）: bullish（PE 分位18% + 股息率共振确认）
流动性否决触发后：
  direction: "neutral"（强制降级）
  confidence: 0.35（封顶）
  meta.circuit_breaker.liquidity_veto: true
  meta.veto_reason: "流动性危机期间，估值信号延迟生效"
  signals 包含: "流动性危机否决生效，估值看多信号暂缓，等待流动性恢复"
  needs_human_review: true
  uncertainties 包含: "简化模式运行：仅使用 PE 分位数 + 股息率"
  uncertainties 包含: "流动性否决机制触发（Liquidity Veto）"
```

### 样例H（简化模式 + 正常市场，v0.4 新增）

```text
场景：A股沪深300，仅有 PE TTM 和股息率数据
PE TTM分位数: 近5年 25%（偏低估）
股息率: 2.8%（接近历史均值 × 1.15，轻度支持bullish）
liquidity_risk_signal: 未传入（缺失）
QVIX: 22（正常）

预期：
meta.valuation_mode: "simplified"
direction: "bullish"
confidence: 0.55-0.65（简化模式基础值偏低）
risk_level: "medium"
uncertainties 包含: "简化模式运行：仅使用 PE 分位数 + 股息率，未计算完整 ERP 和巴菲特指标"
meta.circuit_breaker.liquidity_veto: false（未传入否决信号，跳过检查）
needs_human_review: false（无异常）
```

---

## 更新记录

| 日期 | 版本 | 修改内容 | 作者 |
|-----|------|---------|------|
| 2026-06-22 | **0.5** | **简化模式新增EPS动量修正系数**（PE分位>80%时结合EPS_YoY判断是否为盈利衰退型高PE，避免疫情式误判；`meta.pe_percentile` 字段加入JSON输出供极端估值熔断引用；样例补充EPS修正演示） | 专家7组 |
| 2026-06-23 | **0.6** | **4.4.1 顶部过滤器触发判定优化**：将数据缺失时固定 confidence 封顶 0.65 的逻辑，升级为按 PE 分位数分级的动态封顶表（< 20% → 0.75；20%-40% → 0.65；40%-60% → 0.55；> 60% → 0.50），体现"估值越便宜对缺失技术数据容忍度越高"的设计原则 | 专家7组 |

---

*最后更新：2026-06-23*
*维护者：专家7组（风控）*
*版本：v0.6*

