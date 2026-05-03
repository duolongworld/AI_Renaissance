# Agent矩阵 - 8 Agent + N Skill 架构

> 8 个 Agent，每个专家组维护自己的 Agent 和 Skill
> 每个 Agent 可动态加载自己领域的 N 个 Skill
> 所有 Agent 输出标准 Signal，由 Orchestrator Agent 统一编排仲裁

---

## 架构总览

```
Orchestrator Agent（编排，开发2组）
    │
    ├── 财务分析 Agent（专家1组）── skills/financial/  ── signal_type: financial
    ├── 技术指标 Agent（专家2组）── skills/technical/  ── signal_type: technical
    ├── 资金流向 Agent（专家3组）── skills/fundflow/   ── signal_type: fundflow
    ├── 宏观周期 Agent（专家4组）── skills/macro/      ── signal_type: macro
    ├── 行业景气 Agent（专家5组）── skills/industry/   ── signal_type: industry
    ├── 舆情情感 Agent（专家6组）── skills/news/       ── signal_type: news
    └── 风险预警 Agent（专家7组）── skills/risk/       ── signal_type: risk
```

---

## Agent 详细矩阵

### 🎯 Orchestrator Agent

| 属性 | 值 |
|------|-----|
| 目录 | `agents/orchestrator/` |
| 负责团队 | 开发2组 |
| signal_type | —（不输出 Signal，输出 ArbitrationResult） |
| 加载 Skill | 否 |
| 核心职责 | 信号收集 → 权重聚合 → 方向判定 → 风险约束 → 推理链生成 → 最终报告 |
| 核心文件 | `agent.py`、`arbitration.py` |

---

### 📊 财务分析 Agent

| 属性 | 值 |
|------|-----|
| 目录 | `agents/financial/` |
| 负责团队 | 专家1组 |
| signal_type | `financial` |
| Skill 目录 | `skills/financial/` |
| 核心能力 | 七步验证链（看现金→看需求→看业绩→看产能→看扩张→看扩张风险→看利率敏感度） |

**已有 Skill：**

| Skill | 目录 | 状态 |
|-------|------|------|
| 财报分析 | `skills/financial/financial_report_analysis/` | ✅ 已实现 |
| 现金流质量检查 | `skills/examples/cash_flow_quality_check/` | 📝 示例 |

**待开发 Skill：**

| Skill | 说明 | 优先级 |
|-------|------|--------|
| 营运资金分析 | 应收/存货/预付款综合 | P1 |
| 盈利能力分析 | 毛利率/净利率/ROE | P1 |
| 合同负债趋势 | 先行指标 | P1 |
| 资本开支信号 | 扩张周期 | P1 |
| 负债风险评估 | 有息负债/杠杆率 | P1 |

---

### 📈 技术指标 Agent

| 属性 | 值 |
|------|-----|
| 目录 | `agents/technical/` |
| 负责团队 | 专家2组 |
| signal_type | `technical` |
| Skill 目录 | `skills/technical/` |
| 核心能力 | 趋势识别、量价分析、动量信号 |

**待开发 Skill：**

| Skill | 说明 | 优先级 |
|-------|------|--------|
| 均线趋势判定 | MA/EMA 趋势方向 | P0 |
| MACD 信号 | 金叉死叉 | P0 |
| RSI 超买超卖 | 超买超卖区间 | P1 |
| 成交量异动 | 量价配合 | P1 |
| 趋势强度 | ADX 等 | P2 |
| 支撑压力位 | 价位识别 | P2 |
| K 线形态 | 形态识别 | P3 |

---

### 💰 资金流向 Agent

| 属性 | 值 |
|------|-----|
| 目录 | `agents/fundflow/` |
| 负责团队 | 专家3组 |
| signal_type | `fundflow` |
| Skill 目录 | `skills/fundflow/` |
| 核心能力 | 主力资金追踪、北向资金、聪明钱动向 |

**待开发 Skill：**

| Skill | 说明 | 优先级 |
|-------|------|--------|
| 主力净流入 | 主力资金净额 | P0 |
| 连续净流入 | N日连续净流入 | P1 |
| 北向资金 | 沪深港通 | P1 |
| 超大单流向 | 大资金分析 | P2 |
| 散户比例 | 筹码分布 | P2 |

---

### 🌍 宏观周期 Agent

| 属性 | 值 |
|------|-----|
| 目录 | `agents/macro/` |
| 负责团队 | 专家4组 |
| signal_type | `macro` |
| Skill 目录 | `skills/macro/` |
| 核心能力 | 利率/汇率/PMI 解读，大周期位置判断 |

**待开发 Skill：**

| Skill | 说明 | 优先级 |
|-------|------|--------|
| 美联储政策 | 利率决议解读 | P1 |
| 国内政策 | 政策文件解读 | P1 |
| 汇率监控 | 人民币汇率 | P1 |
| 通胀预期 | CPI/PPI | P2 |
| 地缘事件 | 国际事件评估 | P2 |

---

### 🏭 行业景气 Agent

| 属性 | 值 |
|------|-----|
| 目录 | `agents/industry/` |
| 负责团队 | 专家5组 |
| signal_type | `industry` |
| Skill 目录 | `skills/industry/` |
| 核心能力 | 产业链景气度、行业拐点、竞争格局 |

**待开发 Skill：**

| Skill | 说明 | 优先级 |
|-------|------|--------|
| 行业对比 | 同行业公司对比 | P1 |
| 行业轮动 | 行业强弱分析 | P2 |
| 产业链联动 | 上下游分析 | P2 |
| 竞争格局 | 市场份额 | P3 |

---

### 📰 舆情情感 Agent

| 属性 | 值 |
|------|-----|
| 目录 | `agents/news_agent/` |
| 负责团队 | 专家6组 |
| signal_type | `news` |
| Skill 目录 | `skills/news/` |
| 核心能力 | 新闻情感分析、社交情绪追踪 |

**已有 Skill：**

| Skill | 目录 | 状态 |
|-------|------|------|
| 市场情绪发现 | `skills/news/market_emotion_discovery/` | ✅ 已实现 |

**待开发 Skill：**

| Skill | 说明 | 优先级 |
|-------|------|--------|
| 新闻情感分类 | 正面/负面/中性 | P1 |
| 公告解读 | 重大公告影响 | P1 |
| 研报摘要 | 券商观点提取 | P2 |
| 热点追踪 | 市场热点 | P2 |

---

### ⚠️ 风险预警 Agent

| 属性 | 值 |
|------|-----|
| 目录 | `agents/risk/` |
| 负责团队 | 专家7组 |
| signal_type | `risk` |
| Skill 目录 | `skills/risk/` |
| 核心能力 | 尾部风险识别、仓位上限、守住底线 |
| 特殊说明 | 也输出 Signal，参与仲裁博弈 |

**待开发 Skill：**

| Skill | 说明 | 优先级 |
|-------|------|--------|
| 财务异常检测 | 财报异常 | P1 |
| 商誉减值风险 | 商誉风险 | P1 |
| 股权质押 | 质押比例 | P1 |
| 仓位管理 | 信号强度→仓位 | P1 |
| 解禁压力 | 限售股解禁 | P2 |
| 尾部风险 | 极端事件 | P2 |

---

## 数据层（开发3组）

| 数据源 | 目录 | 状态 |
|--------|------|------|
| 东方财富 API | `data_sources/eastmoney.py` | ✅ 财务数据已实现 |
| 行情数据 | `data_sources/` | 📝 待实现 |
| 资金流向 | `data_sources/` | 📝 待实现 |

---

## Agent 命名规范

```
agents/
├── orchestrator/             # 编排 Agent
│   ├── __init__.py
│   ├── agent.py              # OrchestratorAgent
│   └── arbitration.py        # ArbitrationEngine
│
├── {domain}/                 # 专家 Agent（domain = financial/technical/...）
│   ├── __init__.py
│   └── agent.py              # {Domain}Agent
│
├── base.py                   # BaseAgent（含 Skill 加载）
├── signal.py                 # Signal / SignalBundle
└── registry.py               # SkillRegistry
```

## Skill 命名规范

```
skills/{domain}/{skill_name}/SKILL.md
```

示例：
```
skills/financial/financial_report_analysis/SKILL.md
skills/technical/ma_trend_check/SKILL.md
skills/risk/tail_risk_warning/SKILL.md
```

---

## Signal 标准输出

```python
from agents.signal import Signal, bullish_signal

# 方式1：直接创建
signal = Signal(
    direction="bullish",
    confidence=0.85,
    reasoning="Q3合同负债同比增长200%，下游需求旺盛",
    signals=["合同负债+200%", "经营现金流反超净利润"],
    source="财务分析Agent",
    signal_type="financial",
    stock_code="688521",
    weight=1.0,
    meta={"quarter": "Q3", "year": 2024}
)

# 方式2：便捷函数
signal = bullish_signal(
    confidence=0.85,
    reasoning="...",
    signals=["信号1", "信号2"],
    source="财务分析Agent",
    stock_code="688521",
    signal_type="financial",
    meta={"growth_rate": 2.0}
)
```

---

*最后更新：2026-05-03*
