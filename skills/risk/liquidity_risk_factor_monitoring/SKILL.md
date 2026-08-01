---
name: liquidity_risk_factor_monitoring
description: A股流动性风险因子监测与数据真实性保障Skill。监控股票的流动性风险因子，识别流动性恶化信号，并通过六层数据真实性保障体系确保数据的可信度。支持基础模式（日频OHLCV + 涨跌停数据）和增强模式（含Level-2/持仓/大单数据）。新增规则13市场踩踏代理预警和流动性一票否决权声明。
owner_group: 专家7组（风控）
domain: risk
status: draft
version: 0.8
last_updated: 2026-06-22
git_branch: skill/liquidity-risk-factor-monitoring
---

# 流动性风险因子监测Skill

> 本Skill由**专家7组（风控）**负责维护，重点关注流动性风险和数据真实性两大核心能力。
>
> **核心价值**：确保进入量化模型的数据是真实、完整、未被操纵的，同时识别流动性恶化信号。
>
> **版本说明**：v0.8 在v0.7基础上，新增以下关键更新：
> 1. **规则13补充H6子规则（v0.8新增）**：放量暴跌（流动性虹吸），覆盖"指数涨、个股崩"的缩量依赖盲区（如2026-03-20场景）
> 2. **规则12补充涨跌家数比宽度代理（v0.8新增）**：基础模式下利用东方财富 get_limit_list 接口获取涨跌家数比（ADR），替代 market_breadth_divergence
> 3. **新增4.4.2极端估值熔断（v0.8新增）**：当外部估值信号 extreme bearish 但流动性尚可时，强制上调 risk_level 至 high（领先预警）
> 4. **JSON输出新增 proxy_indicators_used 字段（v0.8新增）**：记录具体使用的代理指标和数据模式，提升可解释性与审计合规性
> 5. v0.7原有功能（Data Availability、规则13原缩量触发、一票否决权）全部保留

---

## 零、数据可用性声明（Data Availability，v0.7新增）

### 基础模式与增强模式定义

本Skill按数据可用性分为两个运行模式：

| 模式 | 触发条件 | 可用规则 | 说明 |
|-----|---------|---------|------|
| **基础模式**（默认） | 仅有日频 OHLCV + 涨跌停数据 | 规则1、2、3、5、6、7、12、**13**（新增） | 免费数据管道可完全支持 |
| **增强模式** | 额外提供 Level-2 / 持仓数据 / 大单数据 | 基础模式全部规则 + 规则4、9、10、11 | 需付费数据源（Level-2、机构资金流） |

### 增强模式规则标注

以下规则标记为 **`ENHANCED_ONLY`**，在基础模式下**必须直接跳过**：

| 规则 | 标记 | 所需数据 | 跳过时的处理 |
|-----|------|---------|------------|
| 规则4：行业相对流动性差 | `ENHANCED_ONLY` | 行业日均成交额数据库（需全市场遍历） | 直接跳过；在 `meta.uncertainties` 中记录"规则4已跳过（行业均值数据不可用）" |
| 规则9：持仓流动性覆盖率 | `ENHANCED_ONLY` | 当前持仓市值（需持仓系统接入） | 直接跳过；记录"规则9已跳过（持仓数据不可用）" |
| 规则10：日内流动性集中度 | `ENHANCED_ONLY` | 分钟级分时数据 | 直接跳过；记录"规则10已跳过（分钟级数据不可用）" |
| 规则11：机构资金流出预警 | `ENHANCED_ONLY` | 大单买卖数据（东方财富大单接口） | 直接跳过；记录"规则11已跳过（大单数据不可用）" |

### 跳过规则的输出要求

> **强制规则（v0.7）**：当增强模式数据缺失时，**禁止**在 `meta.advanced_metrics` 中输出填充了 `0` 或 `null` 的字段（因为下游系统可能误将 `0` 解读为"指标正常"）。
>
> 正确做法：
> - 从 `meta.advanced_metrics` 的输出中**完全移除**未计算的字段
> - 在 `meta.advanced_metrics.available_indicators` 中列出实际计算的指标名称
> - 在 `meta.uncertainties` 中记录："进阶数据缺失，规则X已跳过"

### 规则13 可用性说明

规则13（市场踩踏代理预警）属于**基础模式**，通过以下免费代理指标近似触发：
- **代理指标A**：全市场跌停家数（东方财富 `get_limit_list` 接口可获取）
- **代理指标B**：目标指数（如沪深300）的成交额是否 < 20日均值 × 0.6（指数 K线数据，akshare 可获取）

---

## 一、适用范围

### 1.1 基本信息

| 项目 | 内容 |
|-----|------|
| 所属小组 | 专家7组（风控） |
| 负责方向 | 量化风控、流动性风险、数据真实性保障 |
| Skill名称 | liquidity_risk_factor_monitoring |
| Skill路径 | `skills/risk/liquidity_risk_factor_monitoring/SKILL.md` |

### 1.2 适用任务

- **流动性风险识别**：识别个股或组合的流动性恶化信号，评估卖出难度和冲击成本
- **选股风控**：在纳入股票池前评估流动性风险，避免纳入流动性枯竭标的
- **持仓监控**：持续监控持仓股票的流动性状况，及时预警流动性恶化
- **量化模型数据校验**：验证进入模型的数据是否真实、完整、未被操纵
- **跨源数据一致性验证**：对比多个数据源，识别伪造或异常数据

### 1.3 适用对象

- A股全市场股票（主板、创业板、科创板、北交所）
- 行业指数、宽基指数
- 自选股池、持仓组合

### 1.4 适用时间周期

| 周期 | 用途 | 说明 |
|-----|------|------|
| **日频监控** | 盘后更新当日流动性因子 | 识别短期异动 |
| **周频回顾** | 评估流动性趋势变化 | 提前预警 |
| **事件触发** | 重大利好/利空后立即检查 | 捕捉事件冲击 |

### 1.5 边界说明

- 本Skill重点关注**数据真实性**，确保进入分析的数据可信
- 本Skill提供流动性因子**校验和评估**（由因子Agent计算，本Skill负责验证和使用）
- 流动性风险评级仅作为风险提示，不直接转成交易建议
- 当数据真实性验证失败时，输出警告并标记需要人工复核，但**继续提供基于可信源的流动性分析**
- 本Skill负责调用因子Agent获取计算结果，本Skill不重复计算因子

---

## 二、输入材料

### 2.1 必填输入

| 输入项 | 说明 | 数据来源 |
|-------|------|---------|
| 标的 | 股票代码 / 股票池列表 | 用户输入 |
| 时间范围 | 最近N个交易日（建议N≥20） | 用户输入 |
| 日频行情数据 | OHLCV数据 | 行情数据Agent |
| 成交量数据 | 分时、日频成交量 | 资金流向Agent |
| 数据来源 | 至少2个数据源 | 东方财富/Tushare/Wind/AkShare |

### 2.2 可选输入

| 输入项 | 说明 | 用途 |
|-------|------|------|
| 分钟级分时数据 | 日内流动性分析 | 精细化分析 |
| 盘口数据 | 买卖队列、委托量 | 流动性深度 |
| Level-2行情数据 | 买一/卖一报价、委托量、逐笔成交 | 实际买卖价差、冲击成本 |
| 持仓信息 | 当前持仓市值、行业分类 | 持仓卖出天数 |
| 历史流动性指标 | 趋势对比 | 趋势判断 |
| 行业平均流动性 | 横向对比 | 相对强弱 |
| 指数成分股权重 | 冲击成本计算 | 组合层面分析 |
| 公告信息 | 停复牌、配股等 | 事件影响 |
| 机构资金流向 | 大单净流入、主力资金流向 | 机构行为监测 |
| 价格位置与动量 | 20/60日涨跌幅、距60日高点、均线偏离、RSI | 区分健康流动性与高位分发 |
| 量价背离指标 | 放量滞涨、长上影、收盘位置、宽度背离 | 识别反弹高位出货风险 |

> **⚠️ 数据分层说明（v0.5新增）**：本Skill指标分为**基础层**（仅需日频OHLCV）和**进阶层**（需要Level-2或持仓数据）。基础层指标可独立运行，进阶层指标为可选增强，缺失时不影响基础判定。

### 2.3 缺失处理

采用双维度独立处理：

| 缺失情况 | 处理方式 | 对流动性置信度的影响 | 对数据可信度的影响 |
|---------|---------|---------------------|-------------------|
| 缺少至少2个数据源 | 输出`neutral`，标注无法交叉验证 | 无法跨源验证，data_confidence ≤ 0.3 | 无法评估，数据可信度 = 0.3 |
| 日频数据不足20日 | 降低`confidence_liquidity`，标注窗口不足 | `confidence_liquidity` × 0.7 | 无直接影响 |
| 行情与资金流来源不一致 | 标记`needs_human_review: true`，继续分析 | `confidence_liquidity` × 0.5 | 降低 data_confidence |

> **说明**：流动性置信度和数据可信度作为**两个独立维度**计算，最终综合评级时合并处理。

---

## 三、分析步骤

### 3.1 第一阶段：数据真实性验证（六层保障）

按以下层级逐层验证数据：

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    六层数据真实性保障体系                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  第一层：数据来源可信性验证                                                   │
│  ├── 数据源白名单验证（Wind/Tushare/东方财富）                                │
│  ├── API签名验证（HMAC-SHA256）                                              │
│  └── 端点URL验证                                                             │
│                                      ↓                                        │
│  第二层：数据传输完整性校验                                                   │
│  ├── 数据包哈希验证（SHA-256）                                                │
│  ├── 校验和验证（CRC32）                                                     │
│  └── 时间戳校验（NTP同步）                                                   │
│                                      ↓                                        │
│  第三层：存储完整性保障                                                       │
│  ├── 哈希链完整性验证                                                        │
│  ├── WORM存储验证                                                            │
│  └── 增量备份验证                                                            │
│                                      ↓                                        │
│  第四层：跨源交叉验证 ⭐核心                                                   │
│  ├── 多源一致性检测（偏差<2%）                                               │
│  ├── 加权投票机制                                                            │
│  └── 异常源标记隔离（保留多数源分析）                                         │
│                                      ↓                                        │
│  第五层：数据操纵检测                                                         │
│  ├── 成交量操纵（突增/对倒/收盘竞价）                                         │
│  ├── 价格操纵（突刺/收盘价）                                                  │
│  └── 波动率异常                                                              │
│                                      ↓                                        │
│  第六层：端到端数据溯源                                                       │
│  ├── 数据血缘追踪                                                            │
│  ├── 操作审计日志                                                            │
│  └── 完整性验证报告                                                          │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

**⚠️ 关键改进（v0.4）**：第四层跨源验证中，当单一数据源异常时，不再拒绝分析，而是**保留多数可信源继续分析**，同时输出"数据争议"警告。

### 3.2 第二阶段：流动性风险分析

> **⚠️ 职责说明**：以下因子由**因子Agent计算**，本Skill负责调用、接收并验证使用。

**从因子Agent获取以下流动性因子**：

#### 基础层指标（仅需日频OHLCV）

| 因子字段名 | 说明 | 用途 |
|-----------|------|------|
| `daily_avg_turnover` | 日均成交额（万元） | 绝对流动性 |
| `avg_turnover_rate` | 平均换手率（%） | 相对流动性 |
| `amihud_illiquidity` | Amihud非流动性因子 | 非流动性度量 |
| `roll_effective_spread` | Roll有效价差 | 有效价差估计 |
| `closing_volume_ratio` | 收盘占比 | 收盘操纵检测 |

#### 进阶层指标（需Level-2 / 持仓数据，v0.5新增）

| 因子字段名 | 说明 | 用途 | 数据要求 |
|-----------|------|------|---------|
| `quoted_spread` | 实际买卖价差（卖一价-买一价，元） | 精确交易成本 | Level-2 |
| `best_bid_volume` | 买一委托量（手） | 订单簿深度 | Level-2 |
| `best_ask_volume` | 卖一委托量（手） | 订单簿深度 | Level-2 |
| `market_depth_ratio` | 委托量/成交量 | 深度充裕度 | Level-2 |
| `impact_cost_per_million` | 每百万元成交额的均价偏移（%） | 冲击成本 | Level-2逐笔 |
| `days_to_liquidate` | 持仓市值/(日均成交额×安全系数) | 持仓卖出天数 | 持仓数据 |
| `volume_concentration_cv` | 日内每30分钟成交量变异系数 | 日内分布均匀性 | 分钟级分时 |
| `idle_period_ratio` | 成交量低于阈值时段占比 | 流动性真空 | 分钟级分时 |
| `institutional_net_inflow` | 大单净流入占成交额比例（%） | 机构资金流向 | 大单数据 |
| `large_trade_proportion` | 大单成交量占全量比例（%） | 交易结构 | 大单数据 |

> **公式参考**（由因子Agent计算）：
> - **Amihud因子**：`ILLIQ = (1/D) × Σ(|R_d| / VOLD_d)`（收益率绝对值除以成交额）
> - **Roll价差**：`Roll = 2 × sqrt(-Cov(ΔP_t, ΔP_{t-1}))`
> - **收盘占比**：`收盘成交量 / 全天成交量`
> - **实际买卖价差**：`quoted_spread = ask_price_1 - bid_price_1`
> - **冲击成本**：`impact_cost_per_million = |Σ(price_i × vol_i) / Σ(vol_i) - mid_price| × (1,000,000 / Σ(vol_i × price_i)) × 100%`
> - **持仓卖出天数**：`days_to_liquidate = position_value / (daily_avg_turnover × 0.25)`，安全系数0.25表示不消耗超过日均成交额25%的单日卖出量
> - **日内成交量集中度**：将交易日按30分钟分段，计算各段成交量，`volume_concentration_cv = std(volumes) / mean(volumes)`
> - **流动性真空比**：`idle_period_ratio = count(volume_i < threshold) / total_periods`，阈值取全日均值的20%

**流动性风险识别**：

1. 横向对比：个股 vs 行业平均 vs 指数平均
2. 纵向趋势：近N日因子变化斜率
3. 事件关联：重大事项前后变化
4. 极端情况：涨跌停、停牌、流动性枯竭
5. 持仓维度：当前持仓的可变现能力（v0.5新增）
6. 深度维度：瞬时冲击成本和委托量充足性（v0.5新增）

### 3.3 第三阶段：信号输出

1. 汇总数据真实性验证结果（独立维度）
2. 综合流动性风险评级（独立维度）
3. 输出结构化Signal（包含两个独立维度的置信度）
4. 标记具体关注信号点和风险放大因子
5. 输出与外部框架对接的放大器字段

---

## 四、判断规则

### 4.1 数据真实性判断规则

#### 4.1.1 六层验证权重

综合得分采用加权平均计算：

| 验证层级 | 权重 | 说明 |
|---------|-----|------|
| 第一层：来源可信 | 0.15 | 数据源授权与API验证 |
| 第二层：传输完整 | 0.10 | 哈希与校验和验证 |
| 第三层：存储可靠 | 0.10 | 哈希链与WORM存储 |
| 第四层：跨源验证 ⭐ | 0.30 | 多源一致性（核心） |
| 第五层：操纵检测 | 0.25 | 异常模式识别 |
| 第六层：溯源追踪 | 0.10 | 数据血缘完整性 |

> 各层得分范围为 0.0-1.0，综合得分 = Σ(层得分 × 权重)

#### 4.1.2 验证规则表

| 验证层级 | 验证项目 | 阈值 | 失败处理 | 数据可信度影响 |
|---------|---------|------|---------|---------------|
| **来源可信** | 数据源白名单 | 至少1个官方/授权源 | 拒绝使用，标记高风险 | data_confidence × 0.3 |
| **来源可信** | API签名验证 | HMAC验证通过 | 标记警告，输出neutral | data_confidence × 0.5 |
| **传输完整** | SHA-256哈希 | 必须匹配 | 拒绝数据 | data_confidence × 0.2 |
| **传输完整** | CRC32校验和 | 必须匹配 | 标记警告 | data_confidence × 0.7 |
| **存储可靠** | 哈希链完整性 | 100%完整 | 标记高风险 | data_confidence × 0.3 |
| **跨源一致** | 多源偏差 | <2%为一致 | 纳入投票 | - |
| **跨源一致** | 多源偏差 | 2%-10%为警告 | 降低权重，标记警告 | data_confidence × 0.6 |
| **跨源一致** | 多源偏差 | >10%为**单一源异常** | 剔除异常源，保留多数源继续分析，输出"数据争议"警告 | 以剩余可信源重新计算 |
| **跨源一致** | 多源偏差 | >10%为**多源分歧** | 无法确定可信源，输出neutral，要求人工复核 | data_confidence ≤ 0.2 |
| **跨源一致** | 投票置信度 | ≥0.7为有效共识 | 标记需人工复核 | data_confidence × 0.6 |
| **操纵检测** | 操纵预警数量 | ≥2个预警 | 触发风险放大器，risk_level +1档 | data_confidence × 0.4 |
| **端到端溯源** | 数据血缘完整性 | 必须可追溯 | 标记警告 | data_confidence × 0.5 |

**⚠️ 关键改进（v0.4）**：跨源验证中区分"单一源异常"和"多源分歧"：
- **单一源异常**：剔除该源，基于剩余可信源继续分析，输出警告但不拒绝
- **多源分歧**：无法确定真相，输出neutral，要求人工复核

#### 4.1.3 跨源投票置信度计算

```
投票置信度 = Σ(有效票权重) / Σ(总权重)

其中：
  - 有效票：偏差 < 10% 的数据源
  - 各源权重见 8.1 节数据源信任权重
  - 置信度 ≥ 0.7 视为有效共识
```

#### 4.1.4 综合数据真实性评级

| 等级 | 得分范围 | 含义 | 处理方式 |
|-----|---------|------|---------|
| A级 | ≥ 0.8 | 数据可信度高 | 直接使用 |
| B级 | 0.6-0.8 | 数据可用但需关注 | 谨慎使用，输出提示 |
| C级 | 0.4-0.6 | 数据存疑 | 以可信源为主分析，输出"数据争议"警告 |
| D级 | < 0.4 | 数据严重存疑 | 无法确定可信源时拒绝，单一源问题时以可信源分析 |

### 4.2 流动性风险判断规则

#### ⚠️ 阈值说明（v0.4新增）

以下规则阈值基于以下原则设定：
- **阈值来源**：历史回测结果（详见附录十一的回测报告摘要）
- **暂定标注**：部分阈值标记"待回测校准"，后续版本将补充完整混淆矩阵
- **相对指标**：规则3等使用相对斜率，消除量纲影响

#### 规则1：流动性枯竭预警

```
条件：
  - 日均成交额 < max(1000万元, 总市值的0.05%)
  - 且 换手率 < 0.5%
  - 且 持续 ≥ 5个交易日

阈值依据：
  - 1000万元绝对阈值：保证最小流动性，避免小市值股票误判
  - 0.05%市值阈值：针对大盘股，参考沪深300成分股日均成交额分布的5%分位数
  - ⚠️ 待回测校准：不同市值分段可能需要不同比例（小盘股建议0.1%，大盘股0.03%）

"持续"定义（v0.4新增）：
  - 连续5个自然交易日满足条件
  - 中断处理：若某日条件不满足，计数器重置为0
  - 不包含涨跌停当日（该日成交额异常放大）

输出：
  - liquidity_outlook: "negative"
  - risk_level: "high"
  - confidence_liquidity: 0.85
```

#### 规则2：流动性急剧恶化

```
条件：
  - 日均成交额较前20日均值下降 > 50%

阈值依据：
  - 50%下降阈值：参考2015年股灾期间流动性枯竭股票的成交额衰减分布
  - ⚠️ 待回测校准：需验证是否考虑市场整体流动性调整（个股/市场比值）
  - 计算时使用成交量而非成交额（排除价格因素干扰）

"持续"定义：
  - 单日触发即可判定，不要求连续
  - 连续触发时confidence可适当上调（+0.05/日，最高0.95）

输出：
  - liquidity_outlook: "negative"
  - risk_level: "high"
  - confidence_liquidity: 0.80
```

#### 规则3：流动性持续收缩

```
条件：
  - 近20日换手率趋势持续下降
  - **相对斜率** < -0.05（即斜率/均值 < -5%）

⚠️ 关键改进（v0.4）：从绝对斜率改为相对斜率

计算说明：
  使用相对斜率消除量纲影响：

  1. 计算相对换手率序列：
     y'_i = y_i / ȳ  （标准化到均值的百分比）

  2. 线性回归：
     slope_relative = Σ(t_i - t̄)(y'_i - ȳ') / Σ(t_i - t̄)²

  3. 预警判断：
     - slope_relative < -0.05（换手率相对均值持续下降5%以上）
     - 需同时满足 t统计量 < -2（统计显著性）

阈值依据：
  - -0.05相对斜率：参考A股个股换手率均值回归特性
  - ⚠️ 待回测校准：不同行业可能需要不同阈值

"持续下降"定义（v0.4明确）：
  - 线性回归斜率为负
  - 且 t统计量绝对值 > 2（95%置信度）
  - 不要求每日环比下降，而是整体趋势向下

不适用情况：
  - 数据窗口不足20日（见2.3缺失处理）
  - 期间存在涨跌停（该日换手率异常）

输出：
  - liquidity_outlook: "negative"
  - risk_level: "medium"
  - confidence_liquidity: 0.65
```

#### 规则4：行业相对流动性差

```
条件：
  - **优先指标**：个股日均成交额 < 行业日均成交额 × 0.3
  - **辅助指标**：个股换手率 < 行业平均换手率 × 0.5
  - 且 持续 ≥ 10个交易日

⚠️ 关键改进（v0.4）：优先使用成交额而非换手率

阈值依据：
  - 成交额30%分位：消除行业换手率基准差异（银行vs半导体）
  - 换手率50%分位：作为辅助验证，仅在成交额接近阈值时参考
  - ⚠️ 待回测校准：不同行业可能需要不同阈值

设计原因：
  - 银行股换手率低（0.2%）但成交额可能很高，不应误判为流动性差
  - 半导体股票换手率高（3%）但成交额可能中等，需综合判断

行业分类颗粒度（v0.5明确）：
  - 一级分类：申万一级行业（31个），用于快速筛选
  - 二级分类：申万二级行业（134个），用于规则4的基准对比
  - 更细颗粒度（中信三级行业）：在有足够样本时可选使用
  - 动态更新：行业均值按月滚动计算（近60个交易日），月初第一个交易日更新
  - ⚠️ 同一行业内市值差异仍大（如银行行业内，招商银行vs无锡银行差异显著）
    建议在二级行业基础上叠加市值分段校准

"持续"定义：
  - 连续10个交易日满足条件
  - 中断处理：若某日不满足，计数器重置为0

不适用情况：
  - 新股上市前20日（自然低成交额期）
  - 停牌后复牌初期

输出：
  - liquidity_outlook: "negative"
  - risk_level: "medium"
  - confidence_liquidity: 0.60
```

#### 规则5：涨跌停后流动性异常

```
条件：
  - 涨跌停后第二个交易日
  - 成交量 < 涨跌停前5日均量的30%

适用边界（v0.4明确）：
  - 个股涨跌停（非连续涨跌停）
  - 停牌后复牌首日
  - 涨跌停类型：首次涨跌停（非连续）

不适用情况：
  - 连续涨跌停（转而适用规则1-2的流动性枯竭判断）
  - 新股上市首日（成交量自然放大）
  - ST/*ST股票（见下方调整）

ST/*ST股票调整：
  - 涨跌幅限制为5%，原30%阈值调整为25%
  - 原因：5%涨跌停的成交量异常模式与10%不同

"第二个交易日"的连续判断（v0.4新增）：
  - 若第二个交易日仍涨跌停：重新判断是否为连续涨跌停
  - 若判断为连续涨跌停：适用规则1-2，不适用本规则
  - 若判断为非连续（中间有恢复）：仍适用本规则

输出：
  - liquidity_outlook: "negative"
  - risk_level: "medium"
  - confidence_liquidity: 0.70
```

#### 规则6：收盘操纵预警

```
条件：
  - 收盘前30分钟成交量占比 > 50%
  - 且 其他时段成交量稀少（任意30分钟时段成交量 < 全天5%）

说明：
  - 本规则识别收盘操纵行为，但不直接判定流动性风险
  - 收盘操纵是流动性风险的**间接信号**

输出：
  - liquidity_outlook: "neutral"
  - risk_level: "medium"
  - confidence_liquidity: 0.55
  - meta.risk_notes: ["收盘流动性异常", "疑似收盘操纵"]
  - 触发风险放大器（见4.5节）
```

#### 规则7：流动性良好

```
条件：
  - 日均成交额 > 1亿元
  - 且 (换手率 > 1% 或 relative_liquidity_by_value > 1.5)
  - 且 无操纵预警
  - 且 数据真实性 ≥ B级
  - 且 未触发规则12（高流动性分发/放量滞涨预警）

说明：
  - 数据真实性要求本规则与数据质量挂钩
  - 若数据存疑，即使流动性指标良好也输出neutral
  - 本规则只说明"可交易性较好/卖出冲击较低"，不代表价格方向看涨
  - 若没有价格位置、资金流和量价背离输入，不能把本规则单独映射为高置信度 bullish

输出：
  - liquidity_outlook: "positive"
  - direction: "neutral"（默认；仅代表流动性风险低，不代表价格上涨）
  - risk_level: "low"
  - confidence_liquidity: 0.75
  - signals: ["流动性良好，但不构成价格看多信号"]
```

#### ⚠️ 规则8已重构为风险放大器（v0.4）

**原规则8定位**：独立输出direction和risk_level

**新规则8定位**：作为风险放大器，不替代流动性判断

```
触发条件：
  - 数据操纵检测发现异常
  - 预警数量 ≥ 2个

放大器效果（v0.4）：
  - 不改变基本流动性评级（direction/liquidity_outlook保持不变）
  - 将 risk_level 上调一级（low→medium, medium→high）
  - 将 confidence_liquidity 降低 0.1（最低0.3）
  - 输出 manipulation_alert: true

放大器因素列表：
  - bid_ask_spread_widened：买卖价差扩大
  - market_depth_dropped：市场深度下降
  - self_dealing_detected：对倒交易检测
  - closing_price_manipulation：收盘价操纵
  - volume_surge：成交量突增

示例：
  - 基础判断：liquidity_outlook=positive, risk_level=low
  - 触发放大器：risk_level→medium, confidence_liquidity×0.9
```

#### 规则9：持仓流动性覆盖率预警（v0.5新增）

```
条件（需持仓数据）：
  - days_to_liquidate > 5天
  - 或 impact_cost_per_million > 0.5%

数据要求：
  - 持仓市值：当前持仓的市场价值
  - 日均成交额：近20日平均
  - 安全系数：0.25（单日卖出不超过日均成交额的25%）

计算公式：
  days_to_liquidate = 持仓市值 / (日均成交额 × 0.25)

阈值依据：
  - 5天卖出期：机构通常设定3-5天的紧急平仓窗口
    超过5天意味着在紧急情况下无法快速退出
  - 0.5%冲击成本：每卖出100万元导致均价偏移超过0.5%
    参考A股中盘股的冲击成本分布90分位数
  - ⚠️ 待回测校准：不同市值分段可能需要不同安全系数
    （超大盘0.30，中盘0.25，小盘0.15）

分级输出：
  - days_to_liquidate > 10 或 impact_cost > 1.0%：
    → risk_level: "high", confidence_liquidity: 0.85
  - days_to_liquidate > 5 或 impact_cost > 0.5%：
    → risk_level: "medium", confidence_liquidity: 0.70
  - days_to_liquidate > 3 或 impact_cost > 0.3%：
    → risk_level: "low"（不触发本规则，但记录在risk_notes中）

输出：
  - liquidity_outlook: "negative"（high/medium时）或保持原判定（low时）
  - meta.risk_notes: ["持仓流动性覆盖不足，理论卖出天数=X天"]
  - meta.advanced_metrics.days_to_liquidate: X.X
  - meta.advanced_metrics.impact_cost_per_million: X.XX%

缺失处理：
  - 若无持仓数据：跳过本规则，不影响其他规则判定
  - 若无Level-2数据：仅计算days_to_liquidate（基于日频数据），跳过impact_cost
```

#### 规则10：日内流动性集中度预警（v0.5新增）

```
条件（需分钟级分时数据）：
  - volume_concentration_cv > 1.5（日内成交量分布极不均匀）
  - 且 idle_period_ratio > 0.5（超过一半的时段成交量低于阈值）

计算方法：
  1. 将交易日按30分钟分段（A股: 9:30-11:30, 13:00-15:00 → 8个时段）
  2. 计算每段成交量，得到序列 [v1, v2, ..., v8]
  3. volume_concentration_cv = std(v) / mean(v)
  4. idle_period_ratio = count(vi < 0.2 × daily_mean / 8) / 8

阈值依据：
  - CV > 1.5：正常交易日CV约0.6-1.0，超过1.5表示流动性集中在极少数时段
  - idle_period_ratio > 0.5：超过一半时段几乎无法交易
  - ⚠️ 待回测校准：需区分正常开盘/收盘集中与异常集中

设计目的：
  - 识别"虚假流动性"——全天成交额看似正常，但仅集中在开盘和收盘
  - 中间时段无法成交，实际流动性远低于日均数据暗示的水平

输出：
  - liquidity_outlook: "negative"
  - risk_level: "medium"
  - confidence_liquidity: 0.60
  - meta.risk_notes: ["日内流动性分布不均，CV=X.XX，真空时段占比=X%"]

缺失处理：
  - 若无分钟级分时数据：跳过本规则，不影响其他规则判定
  - 若仅有5分钟级数据：调整分段为48个时段，阈值不变
```

#### 规则11：机构资金流出预警（v0.5新增）

```
条件（需大单资金流向数据）：
  - institutional_net_inflow < -5%（连续3日大单净流出）
  - 且 large_trade_proportion < 20%（大单交易占比萎缩）

阈值依据：
  - -5%净流出：参考A股主力资金流出预警的常用阈值
  - 20%大单占比：正常交易日大单占比约25-40%
    低于20%表示机构参与度严重下降
  - ⚠️ 待回测校准：需验证与后续流动性恶化的领先关系

设计目的：
  - 机构离场往往先于流动性枯竭
  - 大单流出 + 小单成交萎缩 = 机构撤退、散户接盘的典型风险模式

输出：
  - liquidity_outlook: "negative"
  - risk_level: "medium"
  - confidence_liquidity: 0.55
  - meta.risk_notes: ["机构资金连续X日净流出，大单占比萎缩至X%"]

缺失处理：
  - 若无大单数据：跳过本规则，不影响其他规则判定
  - 若仅有单日数据：需至少3日数据方可触发
```

#### 规则12：高流动性分发/放量滞涨预警（v0.6新增）

```
条件（需价格位置、成交额/换手率和至少一种资金或宽度输入）：
  - 流动性表面良好：
      daily_avg_turnover > 1亿元
      或 relative_liquidity_by_value > 1.5
  - 且 价格处于反弹高位或短期过热：
      index_return_20d > +8%
      或 stock_return_20d > +12%
      或 distance_to_60d_high <= 3%
      或 ma20_deviation > +6%
  - 且 至少满足以下任一分发/背离信号：
      volume_surge_without_price_progress = true（成交额放大但价格不再有效创新高）
      market_breadth_divergence = true（指数/个股上涨但宽度走弱）
      institutional_net_inflow < -3% 连续3日
      large_trade_proportion 下降至 < 20%
      close_position_in_range < 0.4 且 upper_shadow_ratio > 0.4（冲高回落）

  **基础模式宽度背离代理指标（v0.8新增）**：
  当 market_breadth_divergence 字段因数据缺失而无法直接计算时，
  使用以下代理指标近似判断（利用东方财富 get_limit_list 接口获取涨跌家数）：

  代理指标：涨跌家数比（Advance/Decline Ratio, ADR）
    计算：adr = 当日上涨家数 / 当日下跌家数
    阈值：adr < 0.6（即上涨不足下跌的60%）
  
  触发条件（满足以下全部时，判定 market_breadth_divergence = true）：
    - adr < 0.6
    - 且 对应指数（沪深300/创业板指等）当日涨幅 > 0.5%
  
  示例：
    2026-03-20，全市场上涨660家 / 下跌4700家 ≈ 0.14 < 0.6，
    但创业板指涨1.30%
    → 判定为 market_breadth_divergence = true，规则12可正确触发

  数据来源：东方财富 get_limit_list 接口（返回涨跌停及涨跌家数统计），基础模式免费可用。
  若 get_limit_list 接口不可用，则跳过此代理，在 meta.uncertainties 中记录"宽度背离代理指标（涨跌家数比）数据不可用"。

设计目的：
  - 识别"流动性好但风险上升"的顶部/分发场景
  - 避免把高成交额、较高换手率机械解读为 bullish
  - 适配 2022年6月上旬 A股反弹后接近阶段高点、随后7月初转跌的误判场景

分级输出：
  - 若仅触发高位 + 1个背离信号：
    → liquidity_outlook: "neutral"
    → direction: "neutral"
    → risk_level: "medium"
    → confidence_liquidity: 0.60
  - 若触发高位 + 2个及以上背离信号，或机构资金连续流出：
    → liquidity_outlook: "negative"
    → direction: "bearish"
    → risk_level: "medium"
    → confidence_liquidity: 0.70
  - 若同时出现机构资金流出、放量滞涨、宽度背离三项：
    → liquidity_outlook: "negative"
    → direction: "bearish"
    → risk_level: "high"
    → confidence_liquidity: 0.80

输出要求：
  - signals 必须包含 "高流动性分发预警" 或 "放量滞涨预警"
  - meta.risk_notes 必须写入 "流动性充足不代表价格安全，可能处于反弹高位分发阶段"
  - meta.distribution_risk 记录触发状态、因子和方向覆盖：

    {
      "triggered": true,
      "level": "watch | medium | high",
      "factors": [],
      "overrides_positive_liquidity": true
    }

缺失处理：
  - 若价格位置和资金/宽度数据均缺失：不得把规则7输出映射为 bullish，direction 默认为 neutral，needs_human_review: true
  - 若仅缺资金流但已有价格高位 + 放量滞涨/宽度背离：可触发 medium，不触发 high
```

#### 规则13：市场性流动性枯竭预警（全市场踩踏闸门，v0.7新增）

> **数据可用性**：属于**基础模式**，通过免费代理指标近似触发（无需全市场成交额聚合接口）。

```
背景说明：
  - v0.6 缺失全市场踩踏识别，是最致命的盲区之一
  - 由于免费管道无法直接获取全市场总成交额聚合值，
    改用以下两个代理指标近似触发

代理指标A：全市场跌停家数
  - 数据来源：东方财富 get_limit_list 接口（跌停家数公开统计）
  - 阈值：全市场跌停家数 > 100 家（主板+创业板+科创板合计）

代理指标B：目标指数成交额萎缩
  - 数据来源：akshare 指数 K线（日频成交额，免费可获取）
  - 计算：目标指数（沪深300 / 上证综指等）当日成交额 < 20日均值 × 0.6

触发逻辑（两个代理指标同时满足）：
  条件：全市场跌停家数 > 100
  且：目标指数成交额 < 20日均值 × 0.6

**H6 放量暴跌（流动性虹吸，v0.8新增）**：
  > **背景**：规则13原有触发条件依赖指数量能萎缩（缩量），
  > 无法覆盖"放量出逃"场景（如2026-03-20：
  > 全市场成交额放量至2.3万亿，但超4700只个股下跌，
  > 主力资金净流出399亿，原有缩量条件导致漏判）。

  触发条件（三个条件同时满足）：
    ① market_total_turnover > 近20日均值 × 1.2（显著放量）
    ② market_breadth_down_ratio > 75%（超75%个股下跌）
    ③ 主力资金净流出 > 500亿元 **或** 北向资金净流出 > 100亿元

  逻辑解释：
    - 放量但极少数权重股上涨（虹吸效应），中小盘资金被抽干
    - 实际流动性已崩溃，即便总成交额放大
    - 属于"虚假流动性"：表面成交活跃，实则资金集中出逃

  数据来源：
    - 条件①：目标指数（沪深300/上证综指）K线成交额，akshare 可获取
    - 条件②：遍历全市场涨跌家数（akshare get_limit_list 接口，免费）
    - 条件③：东方财富 get_main_flow（大盘资金流向接口，免费）
      或 北向资金接口（akshare `stock_hsgt_north_net_flow_em`）

  分级输出（H6单独触发，未同时满足原缩量条件时）：
    → liquidity_outlook: "negative"
    → risk_level: "high"
    → confidence_liquidity: 0.70
    → needs_human_review: true（强制）
    → signals 中写："放量暴跌预警（H6）：成交额放大但市场宽度崩溃，流动性虹吸效应，主力/北向资金大幅流出"
    → meta.risk_notes 写入："放量出逃场景：总成交额虽放大，但超75%个股下跌，资金集中流向权重股或出逃，实际流动性已崩溃"

  与原规则13的关系：
    - H6 和原缩量触发（跌停家数+指数量能萎缩）为**并列关系**，任一触发即激活市场踩踏预警
    - 若 H6 和原条件同时触发：confidence_liquidity 取 max(0.75, 0.70) = 0.75，方向均为 high/negative，无冲突
    - H6 触发时，meta.market_crash_proxy 中新增字段 `trigger_type: "volume_surge_crash"`

分级输出：
  - 仅满足跌停家数 > 100（指数量能未萎缩）：
    → 软预警，liquidity_outlook: "negative"
    → risk_level: "medium"
    → confidence_liquidity: 0.65
    → needs_human_review: true
    → signals 中写："全市场跌停家数异常（>100家），疑似市场恐慌"

  - 同时满足两个代理指标：
    → 硬触发，liquidity_outlook: "negative"
    → risk_level: "high"
    → confidence_liquidity: 0.75
    → needs_human_review: true（强制）
    → signals 中写："市场踩踏代理预警：跌停家数>100且指数量能萎缩>40%，疑似全市场流动性枯竭"
    → meta.risk_notes 写入："市场踩踏闸门触发，全市场流动性可能急剧枯竭，建议立即停止所有买入操作"

阈值依据：
  - 跌停家数 > 100：参考A股历史极端事件，2015年股灾、2024年1月微盘暴跌期间跌停家数均超过100家
  - 指数成交额 < 20日均值 × 0.6：40%以上的萎缩意味着市场主动流动性被抽干（参与者选择不交易）
  - ⚠️ 待回测校准：跌停家数阈值可能需按市场分段（主板 vs 全市场）分别校准

局限性说明（必须写入 meta.uncertainties）：
  - "规则13使用代理指标（跌停家数 + 指数量能），无法等价替代全市场成交额聚合，可能存在漏判"
  - "该规则是全市场踩踏的近似识别，精度受代理指标质量限制，建议结合人工复核"

缺失处理：
  - 若 get_limit_list 接口不可用：仅用指数量能代理（单指标），降级为软预警，confidence_liquidity = 0.50
  - 若指数 K线不可用：仅用跌停家数代理，降级为软预警，confidence_liquidity = 0.55
  - 若两个代理指标均不可用：跳过本规则，在 meta.uncertainties 中记录"规则13已跳过（代理指标数据不可用）"

输出（同时满足两个代理指标时）：
  - liquidity_outlook: "negative"
  - risk_level: "high"
  - confidence_liquidity: 0.75
  - needs_human_review: true
  - meta.risk_notes: ["市场踩踏闸门触发，全市场流动性可能急剧枯竭"]
  - meta.market_crash_proxy: {
      "triggered": true,
      "limit_down_count": <实际跌停家数>,
      "index_volume_ratio": <当日成交额 / 20日均值>,
      "trigger_level": "hard | soft",
      "proxy_note": "代理指标，非全市场成交额直接观测"
    }
```

### 4.3 多规则冲突处理

当多条规则同时触发时：

```
处理原则：
  1. 以最高风险的规则为主导
  2. confidence取各规则的**最大值**（而非平均或最小）
  3. 操纵检测（规则8）作为放大器叠加在其他规则之上
  4. 规则12优先覆盖规则7：高流动性分发风险触发时，不允许输出"流动性良好→bullish"
  5. 规则13优先级最高（v0.7新增）：市场踩踏代理预警触发（hard）时，覆盖所有其他规则输出，
     强制 risk_level = "high"，liquidity_outlook = "negative"

方向语义明确规则（v0.7新增）：
  - 当规则12（高流动性分发）触发时：
    → 即便规则7（流动性良好）同时触发
    → 最终 liquidity_outlook 必须取 "negative"（规则12的值）
    → 不得因为规则7存在而将 liquidity_outlook 保持为 "positive" 或 "neutral"
    → 最终 direction 取 "neutral" 或 "bearish"（按规则12分级）
    → 原则：流动性充足是客观事实，但分发行为表明市场参与者已在利用该流动性出货

  - 当规则13（市场踩踏，hard）触发时：
    → 覆盖规则7、规则4、规则12 的 liquidity_outlook
    → 强制 liquidity_outlook = "negative"，risk_level = "high"

计算逻辑：
  - risk_level = max(各规则risk_level) + 操纵放大器加成
  - confidence = max(各规则confidence) + 操纵放大器惩罚
  - liquidity_outlook = 按上述方向语义规则确定（不简单取最高风险规则）

示例：
  - 规则7（positive, low）+ 规则12（negative, medium）同时触发：
    → liquidity_outlook = "negative"（规则12强制覆盖）
    → direction = "neutral"（规则12最低分级输出）
    → risk_level = "medium"
    → confidence = max(0.75, 0.60) = 0.75

  - 规则1（high）+ 规则6（medium）：
    → risk_level = high
    → confidence = max(0.85, 0.55) = 0.85
    → liquidity_outlook = negative
```

### 4.4 综合评级规则

```
最终评级 = 数据真实性评级 × 流动性风险评级

决策逻辑：
  - 如果数据真实性为D级（<0.4）且多源分歧：
    → 输出neutral，拒绝使用数据
    → 输出manipulation_warning，要求人工复核

  - 如果数据真实性为C级（0.4-0.6）或单一源异常：
    → 继续分析，但输出"数据争议"警告
    → confidence_final 使用加权计算（见4.4.1）

  - 如果流动性风险为high且数据真实性为A级：
    → 输出bearish/negative并标注高置信度

  - 如果流动性风险为high但数据真实性不足A级：
    → 输出neutral并降低confidence
    → 仍输出风险信号，但标注数据可信度不足
```

---

### 4.4.1 流动性一票否决权声明（v0.7新增）

> **系统级仲裁规则**：本声明供下游仲裁层、风控 Agent 和估值 Skill 引用。

**核心规则**：

当本Skill输出以下状态时：
```
risk_level = "high"
liquidity_outlook = "negative"
```

**下游仲裁层应执行以下操作**（强制，不可绕过）：

1. **抑制所有 bullish 类估值/择时信号**，直至流动性恢复（即本Skill输出降级为 risk_level ≤ "medium" 或 liquidity_outlook 改善为 "neutral"/"positive"）
2. 所有来自估值 Skill、技术面 Skill 的 `direction: "bullish"` 信号，强制标记为 `deferred`（延迟生效）
3. 系统最终输出方向降级为 `"neutral"` 或 `"bearish"`
4. 在仲裁层输出的 `meta.arbitration_notes` 中写入：`"流动性Skill一票否决权生效：当前流动性危机状态，所有看多信号已被抑制"`

**否决权生效场景对照（v0.7新增）**：

| 场景 | 流动性 Skill 输出 | 估值 Skill 输出 | 仲裁层最终方向 | 备注 |
|------|----------------|---------------|--------------|------|
| 流动性危机（如2024年1月）| risk=high, outlook=negative | direction=bullish | **neutral / bearish（否决）** | 估值信号标记 deferred |
| 正常市场且估值极低 | risk=low, outlook=positive | direction=bullish | **bullish（共振看多）** | 正常输出 |
| 流动性良好但估值泡沫 | risk=low, outlook=positive | direction=bearish | **bearish（共振看空）** | 正常输出 |
| 流动性中性 | risk=medium, outlook=neutral | direction=bullish | **neutral（降级审慎）** | 中性状态不否决，但降置信度 |

**否决权解除条件**：
- 本Skill输出 risk_level 降至 "medium" 及以下，且 liquidity_outlook 改善为 "neutral" 或 "positive"
- 或连续 3 个交易日规则1（流动性枯竭）和规则13（市场踩踏）均未触发

---

### 4.4.2 极端估值熔断（Valuation Circuit Breaker，v0.8新增）

> **系统级仲裁规则**：本规则供下游仲裁层、风控 Agent 和估值 Skill 引用。
> 与 4.4.1 流动性一票否决权互为补充：前者解决"流动性差但估值看多"死锁，本规则解决"流动性好但估值极度泡沫"的滞后短板。

**核心规则**：

当**外部估值信号**传入且满足以下条件时：

```
估值信号满足以下任一：
  - valuation_signal.direction == "bearish" 且 valuation_signal.meta.risk_level == "high"
  - 或 valuation_signal.meta.pe_percentile > 85%（仅简化模式可用）

且 本Skill输出：
  - risk_level == "low" 或 "medium"（流动性尚未崩溃）
  - liquidity_outlook == "positive" 或 "neutral"
```

**仲裁层应执行以下操作**（强制，不可绕过）：

1. **强制上调最终 risk_level 至 "high"**（即便流动性尚未恶化）
2. 在仲裁层输出的 `meta.arbitration_notes` 中写入：
   `"极端估值熔断触发：PE分位>85% + 流动性尚可 → 建议提前减仓，避免流动性恶化时踩踏"`
3. 在 `signals` 中加入：
   `"极端估值泡沫 + 流动性尚可 → 提前预警，建议逐步降低仓位"`
4. 该场景下，即便流动性 Skill 输出 `risk_level = "low"`，**系统最终 risk_level 强制为 "high"**（领先指标，在流动性恶化前提前预警）

**熔断触发场景对照（v0.8新增）**：

| 场景 | 估值 Skill 输出 | 流动性 Skill 输出 | 仲裁层最终 risk_level | 备注 |
|------|---------------|-----------------|--------------|------|
| 超级泡沫顶部（如2015年6月上旬） | direction=bearish, risk=high, PE>90% | risk=low, outlook=positive | **high（熔断触发）** | 流动性尚未恶化，但估值极度泡沫，提前预警 |
| 流动性危机 + 估值泡沫 | direction=bearish, risk=high | risk=high, outlook=negative | **high（双重确认）** | 流动性否决 + 估值熔断同时生效 |
| 正常市场 | direction=bullish, risk=low | risk=low, outlook=positive | **low** | 无熔断，正常输出 |
| 流动性良好但估值略贵 | direction=bearish, risk=medium | risk=low, outlook=positive | **medium** | 估值看空但非极端，不触发熔断 |

**熔断的数据来源**：
- 估值 Skill 的 `meta.pe_percentile` 字段（简化模式）或 `risk_level`（完整模式）
- 若估值 Skill 未传入 `meta.pe_percentile`，则仅依赖 `risk_level == "high"` 判断

**与流动性一票否决权的关系**：
- 流动性否决权：流动性 high/negative → 抑制估值 bullish（防御型）
- 极端估值熔断：估值 high/bearish + 流动性 low/medium → 强制上调 risk_level（进攻型预警）
- 两者互为补充，覆盖"危机已发生"和"泡沫顶部尚未崩溃"两种场景

---

### 4.5 置信度计算模型

#### ⚠️ 关键改进（v0.4）：从乘法模型改为加权加法模型

**原模型问题**：
```
confidence_final = adjusted_liquidity_confidence × data_authenticity_score
```
- 数据真实性很低时，即使流动性明显恶化，最终置信度也极低
- 暗示"数据可疑时流动性恶化也不可信"——但数据可疑本身是强烈风险信号

**新模型**：双维度独立 + 加权合并

```
confidence_final = w_liquidity × confidence_liquidity + w_data × data_confidence

其中：
  - w_liquidity = 0.7（流动性置信度权重）
  - w_data = 0.3（数据可信度权重）
  - confidence_liquidity：流动性规则置信度（0.0-1.0）
  - data_confidence：数据真实性得分（0.0-1.0）

下界保护：
  - confidence_final ≥ 0.15
  - 当data_confidence < 0.3时，设置confidence_final = 0.15（极低但不拒绝）
```

#### 4.5.1 计算步骤

**第一步：计算流动性置信度**
- 基础置信度 = 触发规则输出的置信度
- 如有数据缺失，按 2.3 节系数调整
- 如触发操纵检测放大器，额外惩罚 0.1

**第二步：计算数据可信度得分**
- 按 4.1.1 节权重计算六层加权平均
- 操纵检测预警 ≥ 2 时，该层得分 ≤ 0.3
- C级数据仍可参与计算（见特殊处理）

**第三步：计算最终置信度**
```
confidence_final = 0.7 × adjusted_liquidity_confidence + 0.3 × data_confidence
```

#### 4.5.2 权重设计依据（v0.4新增）

| 权重 | 值 | 设计理由 |
|-----|-----|---------|
| w_liquidity | 0.7 | 流动性风险是本Skill的核心输出，应占主导 |
| w_data | 0.3 | 数据可信度作为辅助校验，确保分析可靠性 |

**⚠️ 待回测校准**：权重比例需通过历史回测验证最优组合，建议测试范围 [0.6/0.4] ~ [0.8/0.2]

#### 4.5.3 特殊处理

| 情况 | 处理方式 |
|-----|---------|
| `data_confidence` < 0.3（多源分歧） | 强制 `confidence_final = 0.15`，`needs_human_review: true` |
| `data_confidence` 在 0.3-0.4（C级，单一源异常） | 继续分析，输出"数据争议"警告 |
| 操纵检测触发（规则8） | `risk_level` +1，`confidence_liquidity` -0.1（最低0.3） |
| 最低置信度下界 | `confidence_final` ≥ 0.15 |

---

## 五、标准输出

### 5.1 JSON输出格式

```json
{
  "direction": "bullish | bearish | neutral",
  "confidence": 0.0,
  "reasoning": "",
  "signals": [],
  "source": "liquidity_risk_factor_monitoring",
  "signal_type": "risk",
  "stock_code": "",
  "weight": 1.0,
  "meta": {
    "output_version": "0.7",
    "skill_name": "liquidity_risk_factor_monitoring",
    "owner_group": "专家7组（风控）",
    "target": "",
    "period": "",
    "time_horizon": "short | mid | long",
    "risk_level": "low | medium | high",
    "data_mode": "basic | enhanced",

    "liquidity_outlook": "positive | negative | neutral",
    "confidence_breakdown": {
      "liquidity_confidence": 0.0,
      "data_confidence": 0.0,
      "weight_liquidity": 0.7,
      "weight_data": 0.3,
      "final_confidence": 0.0
    },

    "veto_authority": {
      "active": false,
      "condition": "risk_level=high AND liquidity_outlook=negative",
      "downstream_instruction": "抑制所有 bullish 信号，直至流动性恢复"
    },

    "market_crash_proxy": {
      "triggered": false,
      "limit_down_count": null,
      "index_volume_ratio": null,
      "trigger_level": "none | soft | hard",
      "trigger_type": "none | short_volume | volume_surge_crash",
      "proxy_note": ""
    },

    "manipulation_amplifier": {
      "activated": false,
      "level": 0,
      "factors": [],
      "risk_level_boost": 0
    },

    "liquidity_amplifier": {
      "activated": false,
      "level": 0,
      "factors": []
    },

    "distribution_risk": {
      "triggered": false,
      "level": "none | watch | medium | high",
      "factors": [],
      "overrides_positive_liquidity": false
    },

    "data_authenticity": {
      "overall_score": 0.0,
      "grade": "A | B | C | D",
      "dispute_type": "none | single_source | multi_source",
      "layer_results": {
        "source_trust": {
          "passed": true,
          "score": 0.0,
          "details": "",
          "trusted_sources": [],
          "all_sources": []
        },
        "transmission_integrity": {
          "passed": true,
          "score": 0.0,
          "data_age_seconds": 0,
          "details": ""
        },
        "storage_integrity": {
          "passed": true,
          "score": 0.0,
          "hash_chain_valid": true,
          "worm_storage_valid": true,
          "details": ""
        },
        "cross_source_validation": {
          "passed": true,
          "score": 0.0,
          "confidence": 0.0,
          "details": "",
          "sources_used": [],
          "deviations": {},
          "reference_value": 0.0
        },
        "manipulation_detection": {
          "passed": true,
          "score": 0.0,
          "alerts": [],
          "manipulation_types": [],
          "severity": 0
        },
        "lineage_traceability": {
          "passed": true,
          "score": 0.0,
          "lineage_complete": true,
          "details": ""
        }
      }
    },

    "liquidity_metrics": {
      "daily_avg_turnover": 0.0,
      "avg_turnover_rate": 0.0,
      "liquidity_ratio": 0.0,
      "amihud_illiquidity": 0.0,
      "roll_effective_spread": 0.0,
      "closing_volume_ratio": 0.0,
      "industry_avg_turnover": 0.0,
      "industry_avg_turnover_value": 0.0,
      "relative_liquidity_by_turnover": 0.0,
      "relative_liquidity_by_value": 0.0,
      "trend_slope": 0.0,
      "trend_slope_relative": 0.0,
      "trend_t_statistic": 0.0
    },

    "advanced_metrics": {
      "data_tier": "basic | enhanced",
      "available_indicators": []
    },

    "key_findings": [],
    "evidence": [
      {
        "source_type": "market_data | fund_flow",
        "source_name": "",
        "date": "",
        "metric": "",
        "value": "",
        "comparison": "",
        "note": ""
      }
    ],
    "proxy_indicators_used": {
      "data_mode": "basic | enhanced",
      "market_breadth": "",
      "market_crash_trigger": "",
      "distribution_divergence": "",
      "skipped_enhanced_rules": [],
      "notes": ""
    },

    "risk_notes": [],
    "warnings": [],
    "uncertainties": [],
    "needs_human_review": true
  }
}
```

> **⚠️ advanced_metrics 输出规则（v0.7强制）**：
> - 当 `data_tier = "basic"` 时，`advanced_metrics` 中除 `data_tier` 和 `available_indicators` 外，**不得输出任何字段**（包括值为 0 或 null 的字段）。
> - 仅当某指标实际计算后，才将其加入 `available_indicators` 列表并输出对应字段。
> - 未计算的字段必须在 `meta.uncertainties` 中以"进阶数据缺失，规则X已跳过"形式记录。

### 5.2 字段说明

#### 核心方向字段（v0.4更新）

| 字段 | 中文含义 | 说明 |
|-----|---------|------|
| `direction` | 信号方向 | bullish/bearish/neutral（兼容旧框架） |
| `liquidity_outlook` | 流动性展望 | positive/negative/neutral（v0.4新增，语义更清晰） |

**语义说明**：
- `liquidity_outlook` 表示"流动性状况的预期"，不暗示股价方向
- `positive` = 流动性有利，`negative` = 流动性不利
- 下游消费方应使用 `liquidity_outlook` 而非 `direction`

#### 置信度分解字段（v0.4新增）

| 字段 | 中文含义 | 说明 |
|-----|---------|------|
| `confidence_breakdown.liquidity_confidence` | 流动性置信度 | 来自规则计算的独立置信度 |
| `confidence_breakdown.data_confidence` | 数据可信度 | 来自六层验证的独立置信度 |
| `confidence_breakdown.final_confidence` | 最终置信度 | 加权合并结果 |

#### 风险放大器字段（v0.4新增）

| 字段 | 中文含义 | 用途 |
|-----|---------|------|
| `manipulation_amplifier` | 操纵检测放大器 | 标识操纵风险对流动性的放大效应 |
| `liquidity_amplifier` | 流动性放大器 | **与外部框架（信用利差）对接的标准字段** |
| `distribution_risk` | 高流动性分发风险 | 标识高成交额/高换手率是否被高位分发、放量滞涨或资金流出覆盖 |

#### 数据真实性字段（v0.4更新）

| 字段 | 中文含义 | 说明 |
|-----|---------|------|
| `data_authenticity.dispute_type` | 争议类型 | 区分"单一源异常"和"多源分歧" |
| `manipulation_detection.severity` | 操纵严重度 | 0-3级，用于放大器强度 |

---

## 六、质量检查

### 6.1 输出前检查清单

- [ ] 是否有明确 `liquidity_outlook`（positive/negative/neutral）
- [ ] `confidence` 是否在 0.15 到 1.0 范围内
- [ ] 是否写明 `signal_type: "risk"`
- [ ] 是否有至少一条核心 `signals`
- [ ] `confidence_breakdown` 是否完整（liquidity_confidence + data_confidence + final）
- [ ] 是否完成跨源交叉验证并标注 dispute_type
- [ ] 是否完成至少1项操纵检测
- [ ] 是否有证据来源（market_data或fund_flow）
- [ ] 是否标注时间周期 `time_horizon`
- [ ] 缺失数据是否写进 `meta.uncertainties`
- [ ] 是否需要人工复核 `needs_human_review`
- [ ] 是否有操纵预警且设置了 `manipulation_amplifier`
- [ ] 是否输出 `liquidity_amplifier`（供外部框架使用）
- [ ] 如果规则7触发，是否确认未触发规则12；否则不得输出 bullish
- [ ] 如果价格位置/资金/宽度数据缺失，是否将"流动性良好"限制为 neutral 并要求人工复核
- [ ] **`meta.data_mode` 是否正确标注（basic / enhanced）**（v0.7新增）
- [ ] **ENHANCED_ONLY 规则（4、9、10、11）在基础模式下是否已直接跳过**（v0.7新增）
- [ ] **`meta.advanced_metrics` 是否符合 v0.7 输出规则：基础模式下不输出任何 0 或 null 的进阶字段**（v0.7新增）
- [ ] **是否检查了规则13（市场踩踏代理预警）**：是否查询全市场跌停家数 + 目标指数量能（v0.7新增）
- [ ] **若规则13触发，`meta.market_crash_proxy` 是否正确填写**（v0.7新增）
- [ ] **若 risk_level=high 且 liquidity_outlook=negative，`meta.veto_authority.active` 是否为 true**（v0.7新增）
- [ ] **规则7与规则12同时触发时，`liquidity_outlook` 是否取 negative（规则12覆盖）**（v0.7新增）
- [ ] 若有进阶数据，是否在 `meta.advanced_metrics.available_indicators` 中列出实际计算的指标
- [ ] 若触发规则9-11，是否在 `risk_notes` 中记录详细数据
- [ ] 若触发规则12，是否输出 `distribution_risk` 并写明高流动性分发风险

### 6.2 Skill提交检查（参考GIT_WORKFLOW.md）

- [ ] Skill路径符合 `skills/risk/liquidity_risk_factor_monitoring/SKILL.md`
- [ ] 只修改了本次任务相关的Skill或文档
- [ ] 没有修改 `agents/signal.py`、`agents/base.py` 或仲裁层代码
- [ ] 写清楚了必填输入、可选输入和缺失处理
- [ ] 写清楚了证据规则和人工复核条件

---

## 七、测试样例

> **⚠️ 置信度计算说明（v0.4）**：最终置信度 = `0.7 × confidence_liquidity + 0.3 × data_confidence`

### 样例A：流动性良好场景（正面）

```
输入：
  - 股票代码：600519（贵州茅台）
  - 日均成交额：5亿元
  - 换手率：0.8%
  - 行业平均换手率：0.5%
  - 行业平均成交额：2亿元
  - 跨源数据：Wind与Tushare偏差<1%，投票置信度1.0
  - 操纵检测：无预警

计算过程：
  1. 流动性置信度 = 0.75（规则7基础）
  2. 数据可信度 = 1.0（A级）
  3. 最终置信度 = 0.7 × 0.75 + 0.3 × 1.0 = 0.825

预期输出：
  - liquidity_outlook: "positive"
  - direction: "neutral"
  - confidence: 0.83
  - risk_level: "low"
  - signals: ["流动性良好，但不构成价格看多信号"]
  - meta.confidence_breakdown.liquidity_confidence: 0.75
  - meta.confidence_breakdown.data_confidence: 1.0
  - meta.confidence_breakdown.final_confidence: 0.83
  - meta.data_authenticity.overall_score: 1.0
  - meta.data_authenticity.grade: "A"
```

### 样例B：流动性枯竭场景（负面）

```
输入：
  - 股票代码：002XXX（某小盘股）
  - 日均成交额：500万元
  - 换手率：0.3%
  - 持续时间：7个交易日
  - 跨源数据：Wind与Tushare偏差0.5%，投票置信度0.95

计算过程：
  1. 流动性置信度 = 0.85（规则1基础）
  2. 数据可信度 = 0.95（A级）
  3. 最终置信度 = 0.7 × 0.85 + 0.3 × 0.95 = 0.88

预期输出：
  - liquidity_outlook: "negative"
  - direction: "bearish"
  - confidence: 0.88
  - risk_level: "high"
  - signals: ["流动性枯竭预警"]
  - meta.confidence_breakdown.liquidity_confidence: 0.85
  - meta.confidence_breakdown.data_confidence: 0.95
  - meta.data_authenticity.grade: "A"
```

### 样例C：数据操纵预警场景（v0.4更新）

```
输入：
  - 股票代码：300XXX（某创业板股票）
  - 成交量突增：超历史均值6倍（Z-Score > 5）
  - 对倒交易：买卖不平衡度92%（> 90%）
  - 收盘操纵：收盘成交量占比55%（> 50%）
  - 跨源数据：东方财富与Tushare数据偏差12%（> 10%）

计算过程（v0.4改进）：
  1. 流动性置信度：
     - 规则6触发（收盘操纵预警）：confidence_liquidity = 0.55
     - 操纵放大器激活：risk_level +1，confidence_liquidity -0.1
     - adjusted_liquidity_confidence = 0.45
  2. 数据可信度：
     - 跨源验证：单一源异常（东方财富偏差12%），剔除后Tushare可信
     - data_confidence = 0.6（C级，以剩余可信源计算）
     - ⚠️ 不同于v0.3的0.2（D级）：v0.4保留可信源继续分析
  3. 最终置信度 = 0.7 × 0.45 + 0.3 × 0.6 = 0.495

预期输出（v0.4）：
  - liquidity_outlook: "neutral"
  - direction: "bearish"
  - confidence: 0.50
  - risk_level: "medium"  # 规则6基础medium，操纵放大器+1不变
  - signals: ["数据操纵预警", "跨源数据争议（单一源异常）"]
  - meta.confidence_breakdown.liquidity_confidence: 0.45
  - meta.confidence_breakdown.data_confidence: 0.60
  - meta.manipulation_amplifier.activated: true
  - meta.manipulation_amplifier.level: 2
  - meta.manipulation_amplifier.factors: ["self_dealing_detected", "closing_price_manipulation", "volume_surge"]
  - meta.data_authenticity.overall_score: 0.60
  - meta.data_authenticity.grade: "C"
  - meta.data_authenticity.dispute_type: "single_source"
  - meta.warnings: ["单一数据源异常，以剩余可信源分析"]
  - meta.needs_human_review: true
```

### 样例D：多源分歧场景（v0.4新增）

```
输入：
  - 股票代码：600XXX
  - Wind数据：日均成交额1.5亿
  - Tushare数据：日均成交额5000万
  - AkShare数据：日均成交额1.2亿
  - 偏差：Wind vs Tushare = 67%，Wind vs AkShare = 20%
  - ⚠️ 无法确定哪个源可信

计算过程：
  1. 流动性置信度：
     - 规则1触发（成交额触发枯竭预警）
     - 但数据源分歧，无法确定真实成交额
     - confidence_liquidity = 0.85（但需大幅降低）
  2. 数据可信度：
     - dispute_type = "multi_source"
     - data_confidence = 0.2（多源分歧，D级）
  3. 最终置信度：
     - data_confidence < 0.3，强制 confidence_final = 0.15

预期输出：
  - liquidity_outlook: "neutral"
  - direction: "neutral"
  - confidence: 0.15
  - risk_level: "high"
  - signals: ["多源数据严重分歧"]
  - meta.confidence_breakdown.liquidity_confidence: 0.85
  - meta.confidence_breakdown.data_confidence: 0.20
  - meta.confidence_breakdown.final_confidence: 0.15
  - meta.data_authenticity.grade: "D"
  - meta.data_authenticity.dispute_type: "multi_source"
  - meta.warnings: ["多源数据严重分歧，无法确定可信源"]
  - meta.needs_human_review: true
```

### 样例E：操纵检测作为放大器（v0.4新增）

```
输入：
  - 股票代码：002XXX
  - 日均成交额：3亿元（流动性良好，触发规则7）
  - 但同时检测到收盘操纵（规则6）

计算过程：
  1. 基础判断（规则7）：
     - liquidity_outlook = "positive"
     - risk_level = "low"
     - confidence_liquidity = 0.75
  2. 操纵放大器激活（规则8）：
     - risk_level: low → medium
     - confidence_liquidity: 0.75 - 0.1 = 0.65
  3. 数据可信度 = 0.9（A级）
  4. 最终置信度 = 0.7 × 0.65 + 0.3 × 0.9 = 0.725

预期输出：
  - liquidity_outlook: "positive"
  - direction: "neutral"
  - confidence: 0.73
  - risk_level: "medium"  # 从low提升到medium
  - signals: ["流动性良好", "收盘操纵预警"]
  - meta.manipulation_amplifier.activated: true
  - meta.manipulation_amplifier.level: 1
  - meta.manipulation_amplifier.risk_level_boost: 1
  - meta.warnings: ["检测到操纵行为，建议关注"]

说明：
  - 虽然流动性本身良好，但操纵检测提升了风险等级
  - 这与v0.3不同：v0.3中操纵检测会覆盖其他规则输出
```

### 样例F：持仓流动性覆盖不足（v0.5新增）

```
输入：
  - 股票代码：002XXX
  - 日均成交额：2000万元（流动性尚可，规则7不触发）
  - 当前持仓市值：8000万元
  - impact_cost_per_million：0.65%（每百万冲击成本偏高）
  - 机构资金连续5日净流出，日均净流出率-8%
  - 大单占比：12%（低于20%阈值）
  - 跨源数据：Wind与Tushare偏差<1%，A级

计算过程：
  1. 持仓卖出天数 = 8000 / (2000 × 0.25) = 16天（>10天阈值）
  2. 规则9触发：risk_level=high, confidence_liquidity=0.85
  3. 规则11触发：risk_level=medium, confidence_liquidity=0.55
  4. 多规则冲突：取最高风险 → risk_level=high, confidence=max(0.85, 0.55)=0.85
  5. 数据可信度 = 1.0（A级）
  6. 最终置信度 = 0.7 × 0.85 + 0.3 × 1.0 = 0.895

预期输出：
  - liquidity_outlook: "negative"
  - direction: "bearish"
  - confidence: 0.90
  - risk_level: "high"
  - signals: ["持仓流动性覆盖不足", "机构资金持续流出"]
  - meta.advanced_metrics.days_to_liquidate: 16.0
  - meta.advanced_metrics.impact_cost_per_million: 0.65
  - meta.advanced_metrics.institutional_net_inflow: -8.0
  - meta.advanced_metrics.large_trade_proportion: 12.0
  - meta.advanced_metrics.data_tier: "enhanced"
  - meta.risk_notes: [
      "持仓流动性覆盖不足，理论卖出天数=16天",
      "机构资金连续5日净流出，大单占比萎缩至12%"
    ]

说明：
  - 虽然日均成交额2000万看似尚可，但持仓8000万占日均成交额400%
  - 机构持续流出进一步确认流动性恶化趋势
  - 这个组合在日常选股中容易被忽略，是v0.5的核心增强价值
```

### 样例G：高流动性分发/反弹高位误判防护（v0.6新增）

```
输入：
  - 股票代码：600519（或A股大盘样例股）
  - 分析日期：2022-06-10
  - 日均成交额：5亿元（流动性良好）
  - 换手率：0.8%
  - relative_liquidity_by_value：2.5
  - index_return_20d：+9.5%
  - distance_to_60d_high：2.5%
  - volume_surge_without_price_progress：true
  - market_breadth_divergence：true
  - 跨源数据：Wind与Tushare偏差<1%，A级

计算过程：
  1. 规则7基础条件满足：表面流动性良好
  2. 规则12触发：反弹高位 + 放量滞涨/宽度背离
  3. 规则12覆盖规则7，不允许输出 bullish
  4. liquidity_outlook = "negative"（规则12强制覆盖，v0.7方向语义规则）
  5. 流动性置信度 = 0.70
  6. 数据可信度 = 1.0
  7. 最终置信度 = 0.7 × 0.70 + 0.3 × 1.0 = 0.79

预期输出：
  - liquidity_outlook: "negative"
  - direction: "bearish"
  - confidence: 0.79
  - risk_level: "medium"
  - signals: ["高流动性分发预警", "放量滞涨预警"]
  - meta.distribution_risk.triggered: true
  - meta.distribution_risk.overrides_positive_liquidity: true
  - meta.risk_notes 包含 "流动性充足不代表价格安全，可能处于反弹高位分发阶段"
  - meta.needs_human_review: true
  - meta.data_mode: "basic"
  - meta.advanced_metrics: { "data_tier": "basic", "available_indicators": [] }（无进阶字段）

说明：
  - 该样例用于防止 2022年6月上旬 A股反弹高位被误判为 bullish。
  - 高成交额在顶部区域可能代表分发而不是健康买盘。
  - v0.7验证规则12 + 规则7冲突时方向语义：liquidity_outlook = negative。
```

### 样例H：市场踩踏代理预警（v0.7新增，硬触发）

```
输入：
  - 分析目标：A股沪深300
  - 分析日期：2024-02-05（模拟极端下跌日）
  - 全市场跌停家数：287家（超过100家阈值）
  - 沪深300当日成交额：3500亿元
  - 沪深300近20日成交额均值：7200亿元
  - 成交额比率：3500 / 7200 = 0.486（< 0.6，满足代理指标B）
  - 数据模式：基础模式（仅有日频 + 跌停数据）

计算过程：
  1. 代理指标A：跌停家数 287 > 100，✓ 触发
  2. 代理指标B：0.486 < 0.6，✓ 触发
  3. 两个代理指标同时满足 → 硬触发
  4. 规则13输出：risk_level = "high"，confidence_liquidity = 0.75
  5. 数据可信度 = 0.95（A级，Wind + akshare 一致）
  6. 最终置信度 = 0.7 × 0.75 + 0.3 × 0.95 = 0.81
  7. veto_authority.active = true（risk=high + outlook=negative）

预期输出：
  - liquidity_outlook: "negative"
  - direction: "bearish"
  - confidence: 0.81
  - risk_level: "high"
  - signals: ["市场踩踏代理预警：跌停家数>100且指数量能萎缩>40%，疑似全市场流动性枯竭"]
  - meta.data_mode: "basic"
  - meta.market_crash_proxy: {
      "triggered": true,
      "limit_down_count": 287,
      "index_volume_ratio": 0.486,
      "trigger_level": "hard",
      "proxy_note": "代理指标，非全市场成交额直接观测"
    }
  - meta.veto_authority: {
      "active": true,
      "condition": "risk_level=high AND liquidity_outlook=negative",
      "downstream_instruction": "抑制所有 bullish 信号，直至流动性恢复"
    }
  - meta.uncertainties: ["规则13使用代理指标（跌停家数 + 指数量能），无法等价替代全市场成交额聚合，可能存在漏判"]
  - meta.risk_notes: ["市场踩踏闸门触发，全市场流动性可能急剧枯竭，建议立即停止所有买入操作"]
  - needs_human_review: true
  - meta.advanced_metrics: { "data_tier": "basic", "available_indicators": [] }

说明：
  - v0.7最核心的新增用例：解决全市场踩踏盲区
  - 通过免费代理指标近似识别，避免依赖不可获取的全市场成交额聚合接口
  - 一票否决权声明被激活，告知下游仲裁层抑制估值看多信号
```

### 样例I：基础模式增强规则跳过验证（v0.7新增）

```
输入：
  - 股票代码：002XXX（某中盘股）
  - 数据可用性：仅日频OHLCV（无持仓/分钟/大单数据）
  - 日均成交额：800万元
  - 换手率：0.3%
  - 持续时间：6个交易日

计算过程：
  1. data_mode = "basic"（无进阶数据）
  2. 规则4（ENHANCED_ONLY）：直接跳过，记录 uncertainties
  3. 规则9（ENHANCED_ONLY）：直接跳过，记录 uncertainties
  4. 规则10（ENHANCED_ONLY）：直接跳过，记录 uncertainties
  5. 规则11（ENHANCED_ONLY）：直接跳过，记录 uncertainties
  6. 规则1触发：成交额800万<1000万阈值，换手率0.3%<0.5%，持续6天
     → risk_level = "high"，confidence_liquidity = 0.85
  7. 数据可信度 = 0.9（A级）
  8. 最终置信度 = 0.7 × 0.85 + 0.3 × 0.9 = 0.865

预期输出：
  - liquidity_outlook: "negative"
  - direction: "bearish"
  - confidence: 0.87
  - risk_level: "high"
  - meta.data_mode: "basic"
  - meta.advanced_metrics: {
      "data_tier": "basic",
      "available_indicators": []
      // ⚠️ 不得输出 days_to_liquidate: null 或 institutional_net_inflow: 0 等占位字段
    }
  - meta.uncertainties: [
      "进阶数据缺失，规则4（行业相对流动性）已跳过",
      "进阶数据缺失，规则9（持仓流动性覆盖率）已跳过",
      "进阶数据缺失，规则10（日内流动性集中度）已跳过",
      "进阶数据缺失，规则11（机构资金流出预警）已跳过"
    ]

说明：
  - v0.7核心验证：基础模式下增强规则静默跳过，不输出误导性占位值
  - advanced_metrics 中不存在任何 null/0 的进阶字段
```
```

---

## 八、数据源白名单

### 8.1 信任权重

| 等级 | 数据源 | 信任权重 | 类型 |
|-----|-------|---------|------|
| P0 | Wind万得 | 1.0 | 官方 |
| P0 | Tushare Pro | 0.9 | 授权 |
| P1 | 东方财富 | 0.85 | 授权 |
| P2 | AkShare | 0.7 | 社区 |
| P3 | Baostock | 0.65 | 社区 |

### 8.2 跨源验证阈值

| 偏差范围 | 判定 | 处理 |
|---------|------|------|
| < 2% | 一致 | 纳入投票 |
| 2% - 10% | 基本一致 | 降低权重 |
| > 10% | **单一源异常** | 剔除该源，保留其余源继续分析，输出警告 |
| > 10% 且无共识 | **多源分歧** | 无法确定可信源，输出neutral，要求人工复核 |

---

## 九、操纵检测模式

| 检测类型 | 检测指标 | 预警阈值 | 时间窗口 | 说明 |
|---------|---------|---------|---------|------|
| 成交量突增 | Z-Score | > 5倍标准差 | 过去20日 | 超常放量 |
| 对倒交易 | 买卖不平衡度 | > 90% | 当日 | 左手倒右手 |
| 收盘操纵 | 收盘30分钟成交量占比 | > 50% | 当日尾盘 | 收盘价人为控制 |
| 价格突刺 | 价格偏离均线Z-Score | > 3 | 过去20日 | 异常价格 |

**买卖不平衡度计算公式**：

```
买卖不平衡度 = |买入成交量 - 卖出成交量| / (买入成交量 + 卖出成交量) × 100%

# 预警阈值说明
- > 90%: 高度可疑，存在大量对倒交易
- 70%-90%: 中度可疑，建议关注
- < 70%: 正常范围
```

**Z-Score 计算公式**：

```
Z = (当前值 - 均值) / 标准差

其中：
  - 均值：过去20个交易日的滚动均值
  - 标准差：过去20个交易日的滚动标准差
```

**操纵严重度计算**：

```
severity = min(3, floor(alert_count / 2))

其中：
  - alert_count: 操纵预警数量
  - severity: 0-3级
  - 2个预警 → severity=1
  - 4个预警 → severity=2
  - 6个及以上 → severity=3
```

---

## 十、附录：流动性因子计算公式

> **⚠️ 以下公式由因子Agent计算，本Skill负责调用和消费**

### Amihud非流动性因子

```
ILLIQ = (1/D) × Σ(|R_d| / VOLD_d)

其中：
  D：交易日天数
  R_d：日收益率（百分比，如 0.02 表示 2%）
  VOLD_d：日成交额（元）

说明：
  - 值越大表示流动性越差（非流动性越高）
  - 注意：是收益率绝对值除以成交额，而非"1除以|R|再除成交额"
```

### Roll有效价差

```
Roll = 2 × sqrt(-Cov(ΔP_t, ΔP_{t-1}))

其中：
  ΔP_t：价格变动
  取负协方差绝对值
```

### 相对流动性

```
# 换手率基准（辅助指标）
Relative_Liquidity_Turnover = Stock_Turnover_Rate / Industry_Avg_Turnover_Rate

# 成交额基准（优先指标，v0.4新增）
Relative_Liquidity_Value = Stock_Avg_Turnover_Value / Industry_Avg_Turnover_Value
```

### 相对斜率（v0.4新增）

```
# 相对换手率趋势斜率（消除量纲影响）

1. 标准化：
   y'_i = y_i / ȳ  （当前换手率 / 近20日均值）

2. 线性回归斜率：
   slope_relative = Σ(t_i - t̄)(y'_i - ȳ') / Σ(t_i - t̄)²

3. t统计量：
   t = slope_relative / SE(slope_relative)
   其中 SE 为斜率的标准误

4. 预警条件：
   slope_relative < -0.05 AND |t| > 2
```

### 实际买卖价差（v0.5新增）

```
quoted_spread = ask_price_1 - bid_price_1

其中：
  ask_price_1：卖一价（最优卖价）
  bid_price_1：买一价（最优买价）

说明：
  - 比Roll估计更准确，尤其在存在趋势或操纵时
  - 需Level-2数据支持
  - 可计算相对价差：quoted_spread / mid_price × 100%
    mid_price = (ask_price_1 + bid_price_1) / 2
```

### 冲击成本（v0.5新增）

```
impact_cost_per_million = |VWAP - mid_price_before| / mid_price_before × (1,000,000 / trade_value) × 100%

简化计算（日频）：
  1. 以每笔成交计算实际成交价与成交前中间价的偏差
  2. 按成交金额加权平均得到单笔冲击成本
  3. 推算至百万元成交额的等效冲击

日频替代计算（无逐笔数据时）：
  impact_cost_proxy = amihud_illiquidity × 1,000,000
  （即Amihud因子 × 百万元）

说明：
  - 实际计算需要Level-2逐笔数据
  - Amihud因子可作为近似替代（相关性通常>0.8）
```

### 持仓卖出天数（v0.5新增）

```
days_to_liquidate = position_value / (daily_avg_turnover × safety_factor)

其中：
  position_value：当前持仓市值（元）
  daily_avg_turnover：近20日日均成交额（元）
  safety_factor：安全系数，默认0.25

安全系数说明：
  - 0.25表示假设单日卖出量不超过日均成交额的25%
  - 超过此比例将显著推高冲击成本
  - 按市值分段的建议值：
    - 超大盘（>5000亿）：0.30
    - 大盘（1000-5000亿）：0.25
    - 中盘（100-1000亿）：0.20
    - 小盘（<100亿）：0.15
```

### 日内流动性集中度（v0.5新增）

```
volume_concentration_cv = std(volumes_per_period) / mean(volumes_per_period)

其中：
  volumes_per_period：将交易日按30分钟分段的成交量序列
  A股交易时段：9:30-11:30（4段）+ 13:00-15:00（4段）= 8个时段

idle_period_ratio = count(v_i < threshold) / total_periods

其中：
  threshold = 0.2 × daily_avg_volume / total_periods
  即每时段成交量低于全天均值的20%

说明：
  - CV正常范围约0.6-1.0（开盘收盘集中是正常现象）
  - CV > 1.5表示异常集中，中间时段严重缺乏流动性
  - idle_period_ratio > 0.5表示超过一半时段几乎无法正常交易
```

---

## 十一、附录：阈值回测依据（v0.4新增）

### 11.1 阈值设计原则

每个规则阈值的设定遵循以下原则：

| 原则 | 说明 |
|-----|------|
| 历史回测 | 参考A股历史极端事件（如2015年股灾、2018年熊市）的流动性数据分布 |
| 统计分布 | 参考各指标的百分位数分布（5%、10%、25%分位等） |
| 行业差异 | 考虑不同行业的流动性特征差异 |
| 待回测校准 | 标注"⚠️ 待回测校准"的阈值需在生产环境回测验证 |

### 11.2 各规则阈值依据

#### 规则1：流动性枯竭

| 指标 | 阈值 | 依据 |
|-----|------|------|
| 绝对成交额 | ≥1000万元 | 参考沪深300成分股日均成交额分布的1%分位 |
| 市值比例 | 0.05% | 参考小市值股票日均成交额分布的5%分位 |
| 换手率 | <0.5% | 参考全市场换手率的10%分位 |
| 持续时间 | ≥5日 | 参考流动性枯竭后的自然恢复周期 |

⚠️ **待回测校准**：建议对不同市值分段进行分层测试：
- 超大盘（>5000亿）：0.02%
- 大盘（1000-5000亿）：0.03%
- 中盘（100-1000亿）：0.05%
- 小盘（<100亿）：0.10%

#### 规则2：流动性急剧恶化

| 指标 | 阈值 | 依据 |
|-----|------|------|
| 成交额下降 | >50% | 参考2015年7月股灾期间流动性枯竭股票的成交额衰减中位数 |

⚠️ **待回测校准**：
- 需验证是否考虑市场整体流动性调整（个股/市场比值）
- 建议与规则1同步回测，优化阈值组合

#### 规则3：流动性持续收缩

| 指标 | 阈值 | 依据 |
|-----|------|------|
| 相对斜率 | <-0.05 | 参考A股个股换手率均值回归特性 |
| t统计量 | >2 | 95%置信度要求 |

⚠️ **待回测校准**：
- 不同行业可能需要不同阈值
- 建议与趋势跟踪策略同步优化

#### 规则4：行业相对流动性

| 指标 | 阈值 | 依据 |
|-----|------|------|
| 成交额分位 | <30% | 优先指标，消除行业差异 |
| 换手率分位 | <50% | 辅助指标，参考行业中性选股实践 |

⚠️ **待回测校准**：
- 不同行业可能需要不同阈值（尤其是银行vs科技）
- 建议按GICS行业分类分层测试

### 11.3 回测验证计划

| 时间 | 内容 | 负责 |
|-----|------|------|
| v0.4发布后 | 在历史数据上测试各规则阈值的准确性 | 专家7组 |
| v0.5 | 根据回测结果校准阈值 | 专家7组 |
| v0.6 | 提供完整混淆矩阵（Precision/Recall/F1） | 专家7组 |

---

## 十二、与外部框架的衔接（v0.4新增）

### 12.1 信用利差框架对接

本Skill输出 `liquidity_amplifier` 字段，供信用利差Skill消费：

```json
"liquidity_amplifier": {
  "activated": true,
  "level": 2,
  "factors": ["bid_ask_spread_widened", "market_depth_dropped"],
  "description": "流动性恶化作为信用利差风险放大器"
}
```

**level映射规则**：

| risk_level | amplifier.level | 说明 |
|------------|-----------------|------|
| low | 0 | 无放大效应 |
| medium | 1 | 轻度放大 |
| high | 2 | 中度放大 |
| high + 操纵检测 | 3 | 重度放大 |

**factors可能值**：

| factor | 说明 |
|--------|------|
| bid_ask_spread_widened | 买卖价差扩大 |
| market_depth_dropped | 市场深度下降 |
| self_dealing_detected | 对倒交易检测 |
| closing_price_manipulation | 收盘价操纵 |
| volume_surge | 成交量突增 |
| limit_up_down_lock | 涨跌停锁仓 |

### 12.2 放大器使用示例

```
信用利差Skill接收到 liquidity_amplifier：

输入：
  - 基础信用利差风险等级：medium
  - liquidity_amplifier.level = 2

处理：
  - 最终风险等级 = medium + amplifier boost
  - amplifier.level=2 → 风险等级 +1 → high

输出：
  - 最终risk_level: high
  - reasoning: "信用利差风险叠加流动性恶化放大效应"
```

---

## 十三、Git协作说明

### 分支命名

```
skill/liquidity-risk-factor-monitoring
```

### 提交流程

```bash
# 1. 从develop创建分支
git checkout develop
git pull origin develop
git checkout -b skill/liquidity-risk-factor-monitoring

# 2. 修改文件
# ... 修改 SKILL.md ...

# 3. 提交
git add skills/risk/liquidity_risk_factor_monitoring/SKILL.md
git commit -m "feat(v0.4): 重构置信度模型、修复逻辑缺陷、增加外部接口"

# 4. 推送
git push origin skill/liquidity-risk-factor-monitoring

# 5. 创建PR
# 目标分支: develop
```

### PR模板

```markdown
## 类型

Skill / Agent / Fix / Feature

## 做了什么

- v0.4重构：置信度从乘法改为加权加法模型
- 修复规则阈值缺乏依据问题，增加回测依据说明
- 明确"持续"定义和中断处理逻辑
- 区分"数据争议"与"数据拒绝"
- 将规则8重构为风险放大器
- 行业流动性优先使用成交额
- 澄清方向语义，增加liquidity_outlook字段
- 增加liquidity_amplifier标准接口

## 如何测试

说明测试方式或提供的测试样例

## 影响范围

- liquidity_risk_factor_monitoring Skill
- 可能影响消费该Skill输出的其他Agent（如信用利差框架）

## Checklist

- [ ] Skill路径符合规范
- [ ] 输入输出格式正确
- [ ] 判断规则完整
- [ ] 包含测试样例（含v0.4新增样例D/E）
- [ ] 质量检查通过
```

---

## 更新记录

| 日期 | 版本 | 修改内容 | 作者 |
|-----|------|---------|------|
| 2026-05-07 | 0.1 | 初始版本：六层数据真实性保障 + 流动性风险监测 | 专家7组 |
| 2026-05-07 | 0.2 | 修复规则一致性、置信度计算、边界说明和量化定义问题 | 专家7组 |
| 2026-05-07 | 0.3 | 修正Amihud公式、统一置信度计算体系、重写测试样例、添加加权细节 | 专家7组 |
| 2026-05-08 | 0.4 | **重构置信度模型**（乘法→加权加法）、修复规则阈值依据、明确边界条件、区分数据争议类型、将规则8改为放大器、行业流动性优先成交额、澄清方向语义、增加liquidity_amplifier接口 | 专家7组 |
| 2026-05-08 | 0.5 | **补充机构级进阶指标**：持仓卖出天数（规则9）、日内流动性集中度（规则10）、机构资金流向（规则11）、订单簿深度、实际买卖价差、冲击成本；明确行业分类颗粒度（申万二级）；新增advanced_metrics JSON字段；新增样例F | 专家7组 |
| 2026-06-13 | 0.6 | 新增规则12：高流动性分发/放量滞涨预警；修正规则7语义，流动性良好默认不再映射为价格 bullish；新增样例G用于2022年6月反弹高位误判防护 | 专家7组 |
| 2026-06-22 | **0.7** | **Data Availability 章节**（基础/增强模式定义，ENHANCED_ONLY标注）；**新增规则13**（市场踩踏代理预警：跌停家数+指数量能，基础模式可用）；**新增4.4.1流动性一票否决权声明**（系统仲裁规则，risk=high时抑制下游bullish信号）；**明确规则12 vs 规则7冲突时方向语义**（liquidity_outlook必须取negative）；advanced_metrics 强制禁止输出未计算的占位字段；新增样例H（市场踩踏硬触发）、样例I（基础模式跳过验证） | 专家7组 |
| 2026-06-22 | **0.8** | **规则13补充H6子规则**（放量暴跌/流动性虹吸：market_total_turnover>20日均量×1.2 且 market_breadth_down_ratio>75% 且主力资金净流出>500亿）；**规则12补充涨跌家数比宽度代理**（ADR=上涨家数/下跌家数<0.6 且指数涨幅>0.5%时判定宽度背离）；**新增4.4.2极端估值熔断**（Valuation Circuit Breaker：外部估值信号extreme bearish + 流动性low/medium时，强制上调risk_level至high）；**JSON输出新增proxy_indicators_used字段**（记录具体代理指标来源，提升可解释性与审计合规性）；v0.7原有功能全部保留 | 专家7组 |

---

*最后更新：2026-06-22*
*维护者：专家7组（风控）*
*版本：v0.8*
