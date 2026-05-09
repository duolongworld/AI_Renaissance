---
name: market-sentiment-tracker
description: A股大盘市场情绪综合评分，通过8维量化指标+2维社区指标加权评分，判定6阶段市场情绪（无人问津/暗度陈仓/人声渐起/人声鼎沸/恐慌抛售/绝望冰点），输出0-100情绪温度和仓位建议，作为大盘级别逆向信号。
owner_group: 专家6组（舆情）
domain: news
status: draft
---

# 大盘市场情绪温度计 Skill

## 1. 适用范围

所属小组：专家6组（舆情）

适用任务：
- 判断 A 股大盘整体情绪冷热程度，输出 0-100 综合情绪温度
- 识别大盘所处的6阶段情绪状态，给出仓位参考
- 为个股舆情分析提供大盘背景参照（"大气候"）
- 检测特殊情绪信号（顶部预警、底部信号、社区一致看多/看空等）
- 适用于沪深全市场、创业板、科创板等大盘级别情绪评估

边界说明：
- 本 Skill 产出的是大盘情绪面辅助信号，不单独构成交易建议
- 情绪极端不等于立即反转，极端情绪可能持续一段时间
- 社区数据来源存在代表性偏差（东财股吧偏散户），需在 `meta.uncertainties` 说明
- 数据源存在延迟（融资余额 T+1、开户数月度等），需在 `meta.uncertainties` 说明
- 本 Skill 不替代风控层的仓位管理，仅作为情绪面输入

## 2. 输入材料

### 数据来源

| 数据接口 | 执行数据源 | 提供内容 |
|---|---|---|
| AKShare 全市场接口 | `data_sources/market_sentiment.py` | 涨跌停数、市场宽度、北向资金、融资余额、技术指标等 |
| 东财大盘股吧 | `data_sources/community_sentiment.py` | 上证指数吧+创业板吧帖子、讨论热度、多空比例 |

### 必填输入（自动采集）

- 涨跌停板数据：今日涨停家数、跌停家数
- 市场宽度数据：上涨家数 / 下跌家数占比
- 北向资金数据：当日净流入额（亿元）
- 融资余额数据：融资余额及 20 日变化率
- 技术指标：上证指数 RSI(14)、价格相对 20 日高低点位置

### 社区指标（v0.4 新增）

- 讨论热度：大盘股吧帖子总量映射到0-100分
- 社区情绪倾向：看多/看空比例映射到0-100分
- 讨论量趋势：升温/降温/平稳

### 可选输入

- 成交额/换手率变化率
- 市盈率/市净率历史百分位
- 新增开户数/基金申赎数据
- 百度/微信搜索指数
- 个人投资者调查数据（CCTV/中证报）

### 缺失处理

- 如果涨跌停和市场宽度数据均缺失（非交易时间），输出 `direction: "neutral"`，`confidence` 不高于 0.3，标注"非交易时间，无法获取实时市场数据"
- 如果社区数据获取失败，退化为纯分数映射阶段，权重自动归一化到可用指标
- 如果可选输入缺失，可以继续分析，权重自动归一化到可用指标

## 3. 分析步骤

1. **采集量化市场数据**：通过 `data_sources/market_sentiment.py` 自动获取可用的市场指标

2. **采集社区讨论数据**：通过 `data_sources/community_sentiment.py` 获取大盘股吧讨论热度

3. **逐指标标准化**：将每个原始指标映射到 0-100 分
   - 涨跌停比：涨停数/(涨停+跌停) × 100
   - 市场宽度：上涨家数占比 × 100
   - 北向资金：(50 + 净流入/3) 限制在 [0, 100]
   - 融资变化率：(50 + 变化率×2.5) 限制在 [0, 100]
   - RSI：直接使用（0-100）
   - 讨论热度：直接使用 community_sentiment 计算结果
   - 社区情绪倾向：看多比例 × 100

4. **加权综合评分**：按权重计算综合情绪温度
   | 指标 | 权重 |
   |---|---|
   | 涨跌停比 | 0.12 |
   | 市场宽度 | 0.10 |
   | 融资余额变化 | 0.12 |
   | 北向资金 | 0.10 |
   | RSI | 0.08 |
   | 换手率异动 | 0.12 |
   | 量比/成交额变化 | 0.08 |
   | 估值百分位 | 0.08 |
   | **讨论热度** | **0.10** |
   | **社区情绪倾向** | **0.10** |
   - 可用指标权重自动归一化

5. **判定市场阶段**：根据综合温度 + 社区指标匹配6阶段（见4.1）

6. **检测特殊信号**：顶部预警、底部信号、恐慌踩踏、社区一致看多/看空等

7. **输出标准 JSON**

## 4. 判断规则

### 4.1 市场阶段判定（6阶段）

优先级从高到低（先匹配最具体的条件）：

| 优先级 | 阶段 | 条件 | direction | 说明 |
|---|---|---|---|---|
| 1 | 绝望冰点 🧊 | score≤15 AND 讨论热度≤25 AND 看空>60% AND 趋势降温 | `bullish` | 彻底绝望，讨论冻结，逆向看多 |
| 2 | 恐慌抛售 ⚡ | score≤40 AND 讨论热度≥50 AND 看空>75% | `bullish` | 恐慌主导，激烈讨论，逆向看多 |
| 3 | 人声鼎沸 🔥 | score≥65 AND 讨论热度≥70 AND 看多>75% | `bearish` | 全民追涨，逆向看空 |
| 4 | 暗度陈仓 🦉 | score∈[15,40] AND 讨论热度≤35 AND 聪明钱进场 | `bullish` | 聪明钱悄悄进场，散户沉默 |
| 5 | 无人问津 🕳️ | score≤20 AND 讨论热度≤20 | `bullish` | 极端冷清，市场被遗忘 |
| 6 | 人声渐起 📈 | score∈[35,60] AND 讨论热度≥30 | `neutral` | 中间状态，关注度上升 |

**聪明钱判断**：北向资金净流入 > 0 OR 融资余额变化率 > 0

**无社区数据降级**：纯按 score 范围映射，结合聪明钱指标判断"暗度陈仓"。

### 4.2 置信度规则

- **0.8-1.0**：情绪极端明确（温度<20或>80），且 ≥2 个特殊信号支持
- **0.6-0.8**：情绪偏极端（温度<35或>65），或有 1 个特殊信号支持
- **0.4-0.6**：情绪有倾向但不强烈，特殊信号不足
- **<0.4**：数据不足或指标矛盾，使用 `neutral`
- 有社区数据时额外 +0.05 置信度加成

### 4.3 特殊信号规则

| 信号 | 触发条件 | direction 影响 |
|---|---|---|
| 顶部预警 | 温度 ≥ 85 | 加强 `bearish` |
| 底部信号 | 温度 ≤ 15 | 加强 `bullish` |
| 情绪过热 | 涨停数 ≥ 200 | 加强 `bearish` |
| 恐慌踩踏 | 跌停数 ≥ 100 | 加强 `bullish` |
| 外资强烈做多 | 北向净流入 > 150 亿 | 加强 `bullish` |
| 外资大幅撤离 | 北向净流出 > 150 亿 | 加强 `bearish` |
| 杠杆过高 | 融资余额 20 日增幅 > 15% | 加强 `bearish` |
| 去杠杆 | 融资余额 20 日降幅 > 15% | 风险提示 |
| 讨论极度狂热 | 讨论热度 ≥ 90 | 加强 `bearish` |
| 讨论极度冷清 | 讨论热度 ≤ 10 | 加强 `bullish` |
| 社区一致看多 | 看多比例 > 85% | 加强 `bearish` |
| 社区一致看空 | 看空比例 > 85% | 加强 `bullish` |

### 4.4 时间周期

- 大盘情绪温度基于日频数据 → `short`（影响天到数周）
- 融资余额趋势、估值百分位 → `mid`（影响数周到数月）
- 社区讨论热度 → `short`（实时变化）
- 综合输出取 `short`

## 5. 标准输出

### 绝望冰点示例

```json
{
  "direction": "bullish",
  "confidence": 0.78,
  "reasoning": "大盘情绪温度 12.5/100，处于绝望冰点阶段。跌停 128 家，社区讨论热度 8/100，看空比例 68%，讨论量趋势降温。历史上类似冰点后 1 月上涨概率 > 65%，逆向看多。",
  "signals": [
    "🧊 绝望冰点，温度 12.5/100",
    "跌停 128 家，恐慌踩踏信号",
    "社区看空 68%，讨论冻结"
  ],
  "source": "market_sentiment_tracker",
  "signal_type": "news",
  "stock_code": "",
  "weight": 1.0,
  "meta": {
    "output_version": "0.4",
    "skill_name": "market_sentiment_tracker",
    "owner_group": "专家6组（舆情）",
    "target": "A股大盘",
    "period": "实时",
    "time_horizon": "short",
    "risk_level": "high",
    "phase": "despair_freezing",
    "phase_name": "绝望冰点",
    "phase_icon": "🧊",
    "sentiment_score": 12.5,
    "position_suggestion": "80-95%",
    "special_signals": ["底部信号", "恐慌踩踏", "讨论极度冷清"],
    "indicators": {
      "limit_up_ratio": 5.0,
      "breadth": 12.0,
      "margin_change": 10.0,
      "north_flow": 15.0,
      "rsi": 22.0,
      "discussion_volume": 8.0,
      "community_sentiment": 32.0
    },
    "community": {
      "total_posts": 35,
      "discussion_volume_score": 8.0,
      "bullish_ratio": 0.32,
      "bearish_ratio": 0.68,
      "polarization": 0.36,
      "volume_trend": "declining"
    },
    "uncertainties": [],
    "needs_human_review": false
  }
}
```

### 暗度陈仓示例

```json
{
  "direction": "bullish",
  "confidence": 0.65,
  "reasoning": "大盘情绪温度 28.3/100，处于暗度陈仓阶段。讨论热度 22/100（散户沉默），但北向资金净流入 45 亿，融资余额周增 3.2%，聪明钱悄悄进场。",
  "signals": [
    "🦉 暗度陈仓，温度 28.3/100",
    "北向净流入 45 亿，聪明钱进场",
    "讨论热度低，散户沉默"
  ],
  "source": "market_sentiment_tracker",
  "signal_type": "news",
  "stock_code": "",
  "weight": 1.0,
  "meta": {
    "output_version": "0.4",
    "skill_name": "market_sentiment_tracker",
    "owner_group": "专家6组（舆情）",
    "target": "A股大盘",
    "period": "实时",
    "time_horizon": "short",
    "risk_level": "medium",
    "phase": "secret_accumulation",
    "phase_name": "暗度陈仓",
    "phase_icon": "🦉",
    "sentiment_score": 28.3,
    "position_suggestion": "50-70%",
    "special_signals": ["外资强烈做多"],
    "indicators": {
      "limit_up_ratio": 35.0,
      "breadth": 38.0,
      "margin_change": 58.0,
      "north_flow": 65.0,
      "rsi": 32.0,
      "discussion_volume": 22.0,
      "community_sentiment": 45.0
    },
    "community": {
      "total_posts": 95,
      "discussion_volume_score": 22.0,
      "bullish_ratio": 0.45,
      "bearish_ratio": 0.55,
      "polarization": 0.10,
      "volume_trend": "stable"
    },
    "uncertainties": ["换手率数据缺失", "估值百分位数据缺失"],
    "needs_human_review": false
  }
}
```

## 6. 质量检查

输出前检查：

- 是否明确标注情绪温度和6阶段状态
- `direction` 是否符合逆向逻辑（冰点/暗度陈仓→bullish，鼎沸→bearish）
- `confidence` 是否与情绪极端程度和特殊信号数量匹配
- 特殊信号是否正确触发
- 社区数据缺失时是否正确降级
- 各指标原始值和标准化值是否合理
- `meta.uncertainties` 是否说明缺失数据
- `signal_type` 是否为 `news`
- `stock_code` 是否为空（大盘不针对个股）
- `meta.needs_human_review` 是否在数据严重不足时设为 `true`
