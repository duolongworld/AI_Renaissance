# AI Renaissance

> 以多智能体架构，让AI时代的财富平权成为可能

财富不该是信息差的专利。

Medallion Fund 三十年年化 66%，但它只服务于最少数人——门槛 1000 万美元，还长期封盘。华尔街最锋利的武器，从来不会递到普通人手里。不是因为技术做不到，而是因为利润来自信息差，信息差一旦平权，alpha 就消失了。

但 AI 改变了这件事的逻辑。

当大模型把信息获取的边际成本压到接近零，当多智能体系统把机构级的研究能力封装成可复用的基础设施，信息差不再是一道墙——它变成了一条通道。能产生连接的人，就可以穿过这条通道。

AI Renaissance 要做的，不是再造一座封闭的量化圣殿。而是把圣殿的门打开。

---

## 愿景：财富平权，认知先行

我们相信三件事：

**一、趋势是最顶级的杠杆。**

短期波动是噪音，长期趋势是信号。一个人如果能在 2009 年看清移动互联网的趋势，在 2023 年看清 AI 算力的趋势，根本不需要做任何复杂交易——只需要在趋势起点买入，然后耐心等待。最大的 alpha 不是来自某个因子的微弱优势，而是来自对大趋势的早期识别和坚定持有。

**二、信号是趋势的脉搏。**

趋势不是猜出来的，是验证出来的。合同负债暴增 200% 是信号，经营现金流反超利润是信号，资本开支放量是信号，产业链预付款激增是信号——每一个信号都是趋势在财务报表上留下的脚印。读懂这些脚印，就能在趋势被所有人看到之前，提前站上去。

**三、认知才是真正的财富。**

给你一个代码和给你一套验证逻辑，后者值一万倍。因为代码会过期，逻辑可以复用。AI Renaissance 产出的不只是冷冰冰的买卖信号，更是一次完整的认知升级——为什么这笔交易值得做，背后的逻辑链是什么，风险在哪、确定性在哪。当你理解了这些，你就不再需要任何人告诉你该买什么。

---

## 核心命题

投资决策的复杂度已经超出了单智能体的能力边界。但投资决策的本质，从未改变——在趋势的早期，用信号验证它，然后坐上去。

一个人类投资者能同时追踪多少变量？五十？一百？而市场每天产生的有效信号维度是万级的。传统量化的做法是用统计压缩维度——主成分分析、因子正交化、信息比率筛选——本质是在做减法。减法意味着信息损失，信息损失意味着与趋势失之交臂。

我们的做法完全相反：**不是压缩维度，而是扩充认知。**

用一组专业化智能体，每个 Agent 只做一件事——但做到极致。有的只盯资金流向，有的只读财报原文，有的只解析产业趋势拐点，有的只监测情绪极端值。它们各自产出信号，在中央仲裁层碰撞、博弈、达成共识或对冲。这不是一个模型在做决策，而是一个认知生态系统在做决策。

而这个生态系统的产出，不仅是交易指令，更是一份可理解、可验证、可学习的决策推理链——让你不仅知道 what，更理解 why。

---

## 架构：8 Agent + N Skill + 数据层

```
┌──────────────────────────────────────────────────────────────────┐
│                  Orchestrator Agent（编排 Agent）                  │
│     信号收集 → 权重聚合 → 方向判定 → 风险约束 → 推理链生成        │
│                        开发2组负责                                  │
└───────┬──────┬───────┬───────┬───────┬───────┬───────┬──────────┘
        │      │       │       │       │       │       │
   ┌────┴─┐ ┌──┴──┐ ┌──┴──┐ ┌──┴──┐ ┌──┴──┐ ┌──┴──┐ ┌──┴──┐
   │财务  │ │技术  │ │资金  │ │宏观  │ │行业  │ │舆情  │ │风险  │
   │Agent │ │Agent │ │Agent │ │Agent │ │Agent │ │Agent │ │Agent │
   │专家1 │ │专家2 │ │专家3 │ │专家4 │ │专家5 │ │专家6 │ │专家7 │
   ├──────┤ ├──────┤ ├──────┤ ├──────┤ ├──────┤ ├──────┤ ├──────┤
   │financial│technical│fundflow│ macro │industry│ news │ risk │
   │Skill    │Skill    │Skill   │Skill  │Skill   │Skill │Skill │
   └──┬───┘ └──┬───┘ └──┬───┘ └──┬───┘ └──┬───┘ └──┬───┘ └──┬───┘
      │        │        │        │        │        │        │
      └────────┴────────┴────────┴────────┴────────┴────────┘
                               │
                               ▼
   ┌──────────────────────────────────────────────────────────────┐
   │ 每个专家 Agent 的运行关系                                      │
   │ 读取 skills/{domain}/：专家判断规则、证据规则、Signal 输出规则  │
   │ 读取 skills/data/：数据怎么调用、返回什么、失败怎么表示          │
   │ 调用 data_sources/：真实抓取、解析清洗、标准化返回               │
   │ 输出标准 Signal：direction / confidence / reasoning / meta      │
   └──────────────────────────────────────────────────────────────┘
```

**8 个 Agent + N 个 Skill + 数据说明/执行分层，从信号到认知：**

### 🎯 Orchestrator Agent（编排）— 开发2组

不加载 Skill，负责：信号收集 → 权重聚合 → 方向判定 → 风险约束 → 推理链生成 → 最终报告。

### 📊 财务分析 Agent — 专家1组

| 属性 | 值 |
|------|-----|
| signal_type | `financial` |
| Skill 目录 | `skills/financial/` |
| 核心能力 | 七步验证链：看现金→看需求→看业绩→看产能→看扩张→看扩张风险→看利率敏感度 |

### 📈 技术指标 Agent — 专家2组

| 属性 | 值 |
|------|-----|
| signal_type | `technical` |
| Skill 目录 | `skills/technical/` |
| 核心能力 | 趋势识别、量价分析、动量信号、支撑压力位 |

### 💰 资金流向 Agent — 专家3组

| 属性 | 值 |
|------|-----|
| signal_type | `fundflow` |
| Skill 目录 | `skills/fundflow/` |
| 核心能力 | 主力资金追踪、北向资金、聪明钱动向 |

### 🌍 宏观周期 Agent — 专家4组

| 属性 | 值 |
|------|-----|
| signal_type | `macro` |
| Skill 目录 | `skills/macro/` |
| 核心能力 | 利率/汇率/PMI 解读，大周期位置判断 |

### 🏭 行业景气 Agent — 专家5组

| 属性 | 值 |
|------|-----|
| signal_type | `industry` |
| Skill 目录 | `skills/industry/` |
| 核心能力 | 产业链景气度、行业拐点、竞争格局 |

### 📰 舆情情感 Agent — 专家6组

| 属性 | 值 |
|------|-----|
| signal_type | `news` |
| Skill 目录 | `skills/news/` |
| 核心能力 | 新闻情感分析、社交情绪追踪、把情绪变成可交易信号 |

### ⚠️ 风险预警 Agent — 专家7组

| 属性 | 值 |
|------|-----|
| signal_type | `risk` |
| Skill 目录 | `skills/risk/` |
| 核心能力 | 尾部风险识别、仓位上限、守住不爆仓的底线 |
| 特殊说明 | 也输出 Signal，参与仲裁博弈 |

---

## 当前状态（2026-05-11）

项目还在早期建设阶段，README 前面的内容是目标架构，不代表所有能力都已经完成。

| 模块 | 当前状态 |
|------|----------|
| Agent / Signal 基础框架 | 已有 AgentScope-native `BaseAgent`、统一 `Signal`、专家 Agent 目录和主流程注册表 |
| Orchestrator | 已有编排 Agent 和仲裁引擎，可以收集专家 Signal 并跑通初步仲裁流程 |
| 舆情 Agent | 已有初步实现，能编排大盘情绪、行业景气和东方财富股吧数据，输出舆情类 Signal |
| 财务/技术/资金/宏观/行业/风险 Agent | 目前主要是接入骨架和占位输出，专业判断逻辑还需要各专家组继续补齐 |
| 数据层 | 已有东方财富、股吧、巨潮、AkShare、市场情绪等数据源模块，字段稳定性和覆盖范围仍需联调 |
| CI | 已接入依赖检查、pytest、compileall、专家 Agent 契约检查、Orchestrator 仲裁契约检查、AgentScope 消息桥检查和 BaseAgent 原生调用检查 |
| AgentScope | `BaseAgent` 已继承 AgentScope `AgentBase`；Orchestrator 通过 AgentScope `Msg` 调用专家 Agent，并可把仲裁结果包装为 AgentScope `Msg` |

近期更现实的目标是：先让各专家 Agent 以离线可测的方式稳定返回 `Signal`，再逐步补齐专业规则、数据源和仲裁逻辑。

---

## 与传统量化的根本区别

| 维度 | 传统量化 | AI Renaissance |
|------|----------|----------------|
| 信息处理 | 压缩维度，因子筛选 | 扩充认知，多Agent并行感知 |
| 信号来源 | 量价数据为主 | 全域信息（财报原文/产业链/地缘/情绪/另类） |
| 决策机制 | 单模型输出 | 7个专家Agent博弈 + 编排Agent仲裁 |
| Alpha来源 | 因子溢价/统计套利 | 趋势识别 + 信号验证 + 认知带宽差 |
| 输出物 | 交易指令（黑箱） | 交易指令 + 推理链（白箱） |
| 用户关系 | 你只需要执行 | 你理解了才执行 |
| 目标 | 赚钱 | 赚钱 + 让你学会自己赚钱 |

---

## 哲学：慢慢变富

巴菲特说过，没有人愿意慢慢变富。但事实是——慢慢变富是最确定的变富方式。

我们不信短线暴利，不信高频厮杀，不信零和博弈里能持续赢。我们信的是：

**在趋势的早期站上去，用信号反复验证它，然后耐心持有。**

Medallion 的秘密从来不是某个公式，而是一个组织——一群顶尖大脑各自做自己最擅长的事，在一个框架下协作。AI Renaissance 做的是同一件事，但有一个根本不同：

**Medallion 的门是关着的。我们的门是开着的。**

我们给你的不是鱼，也不是渔，而是整片海的认知地图。

---

## 快速开始

### 不同角色先看什么

- 新成员：先看 `docs/GIT_WORKFLOW.md`、`docs/CODING_AGENT_GUIDE.md` 和 `samples/README.md`
- 专家组：先看 `docs/ANALYSIS_SKILL_TEMPLATE.md`、`skills/examples/cash_flow_quality_check/SKILL.md`、`skills/expert_skill_authoring/SKILL.md`
- 开发1组：关注 Agent 基类、Skill 注册机制、Signal 规范、目录规范
- 开发2组：关注 Orchestrator Agent、仲裁引擎、信号汇总、主流程调度
- 开发3组：先看 `docs/DATA_SKILL_TEMPLATE.md`，关注 `data_sources/` 数据源封装和 `skills/data/` 数据接口说明

### 核心术语

- **Skill**：专家写的分析规则说明书，放在 `skills/{domain}/{skill_name}/SKILL.md`
- **Agent**：每个专家组的执行者，动态加载自己领域的 Skill，输出标准 Signal
- **Signal**：系统统一读取的标准信号单，包含 direction/confidence/reasoning/signals/meta
- **Orchestrator**：编排 Agent，收集7个专家信号，执行仲裁，生成最终报告
- **数据层**：`data_sources/` 放真实数据获取代码，`skills/data/` 说明调用参数、返回字段和失败格式；Agent 按说明调用数据源

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 运行测试

```bash
python -m pytest -q
```

测试包含专家 Agent 契约检查、Orchestrator 仲裁契约检查、AgentScope 消息桥检查和 BaseAgent 原生调用检查。它们只确认注册的专家 Agent 可以离线跑通、返回标准 `Signal`，基础仲裁结果保持结构稳定，并且专家 Agent 可以通过 AgentScope `Msg` 边界传递 `Signal`；不验证业务判断是否正确。

### 3. 运行主流程

```bash
python main.py --stock 000001
```

主流程会将股票任务包装成 AgentScope `Msg`，通过专家 Agent 继承自 `BaseAgent` 的 AgentScope `__call__()` 收集 `Signal`，再交给 Orchestrator 仲裁。

### 4. 检查 Agent 接入状态

```bash
python samples/agent_run_check_sample.py --stock 600519
```

这个样例逐个运行专家 Agent，打印运行状态和 `Signal` 摘要。详细说明见 `samples/README.md`。

### 5. Skill 编写

专家组交付专业 Skill 内容；各 Agent 自动加载自己领域的 Skill。开发1组负责 Skill 模板、输出规范、目录规范和联调标准。

参考 `docs/ANALYSIS_SKILL_TEMPLATE.md`，新专家分析 Skill 放在：

```text
skills/{domain}/{skill_name}/SKILL.md
```

---

## 项目结构

```
AIRenaissance/
├── agents/                        # 8 Agent 扁平结构
│   ├── __init__.py
│   ├── base.py                    # Agent 基类（含 Skill 加载）
│   ├── signal.py                  # 统一信号格式
│   ├── registry.py                # Skill 注册机制
│   ├── orchestrator/              # 编排 Agent（开发2组）
│   │   ├── __init__.py
│   │   ├── agent.py               # Orchestrator Agent
│   │   └── arbitration.py         # 仲裁引擎
│   ├── financial/                 # 财务分析 Agent（专家1组）
│   │   ├── __init__.py
│   │   └── agent.py
│   ├── technical/                 # 技术指标 Agent（专家2组）
│   │   ├── __init__.py
│   │   └── agent.py
│   ├── fundflow/                  # 资金流向 Agent（专家3组）
│   │   ├── __init__.py
│   │   └── agent.py
│   ├── macro/                     # 宏观周期 Agent（专家4组）
│   │   ├── __init__.py
│   │   └── agent.py
│   ├── industry/                  # 行业景气 Agent（专家5组）
│   │   ├── __init__.py
│   │   └── agent.py
│   ├── news_agent/                # 舆情情感 Agent（专家6组）
│   │   ├── __init__.py
│   │   └── agent.py
│   └── risk/                      # 风险预警 Agent（专家7组）
│       ├── __init__.py
│       └── agent.py
│
├── data_sources/                  # 数据执行层（开发3组）
│   ├── __init__.py
│   ├── base.py                    # 数据源基类
│   ├── eastmoney.py               # 东方财富财报数据源
│   └── eastmoney_guba.py          # 东方财富股吧数据源
│
├── skills/                        # Skill 目录（专家分析 + 数据接口说明）
│   ├── data/                      # 数据接口说明 Skill（开发3组）
│   │   └── eastmoney_guba/
│   │       └── SKILL.md
│   ├── financial/                 # 财务类 Skill（专家1组）
│   │   └── financial_report_analysis/
│   │       └── SKILL.md
│   ├── technical/                 # 技术类 Skill（专家2组）
│   ├── fundflow/                  # 资金类 Skill（专家3组）
│   ├── macro/                     # 宏观类 Skill（专家4组）
│   ├── industry/                  # 行业类 Skill（专家5组）
│   ├── news/                      # 舆情类 Skill（专家6组）
│   │   └── market_emotion_discovery/
│   │       └── SKILL.md
│   ├── risk/                      # 风控类 Skill（专家7组）
│   ├── examples/                  # 示例 Skill
│   └── expert_skill_authoring/    # 写 Skill 的 Skill
│
├── docs/                          # 文档
│   ├── GIT_WORKFLOW.md
│   ├── CODING_AGENT_GUIDE.md
│   ├── ANALYSIS_SKILL_TEMPLATE.md
│   ├── DATA_SKILL_TEMPLATE.md
│   ├── AGENT_MATRIX.md
│   ├── AGENT_GUIDE.md
│   ├── ARCHITECTURE.md
│   └── TEAM.md
│
├── samples/                       # 本地开发和联调用样例
│   ├── README.md
│   └── agent_run_check_sample.py
│
├── tests/                         # 基础测试、专家 Agent 契约检查、Orchestrator 仲裁契约检查和 AgentScope 边界检查
│   ├── test_base_agent_agentscope.py
│   ├── test_agentscope_message_bridge.py
│   ├── test_arbitration_contract.py
│   ├── test_expert_agent_contract.py
│   └── test_orchestrator_scope.py
│
├── .github/                       # PR 模板和 CI 工作流
│   ├── PULL_REQUEST_TEMPLATE.md
│   └── workflows/
│       └── ci.yml
│
├── main.py                        # 入口
├── requirements.txt
└── README.md
```

---

## 团队协作

### 组职责（一句话版）

| 组 | 组长 | 核心职责 |
|---|---|---|
| 开发1组（架构） | 荒唐 | 维护 Agent 基类、Signal 规范、Skill 注册机制、Git 工作流 |
| 开发2组（功能） | pkm | 实现 Orchestrator Agent、仲裁引擎、信号汇总、推理链生成、主流程调度 |
| 开发3组（数据） | 过去，未来 | 统一封装数据源（data_sources/），维护数据接口说明（skills/data/），让 Agent 只管编排和分析 |
| 专家1组（财务） | 简简简水粽 | 维护财务分析 Agent，编写 financial 类 Skill，七步验证链 |
| 专家2组（指标） | C曦 | 维护技术指标 Agent，编写 technical 类 Skill，趋势识别 |
| 专家3组（资金） | Tao | 维护资金流向 Agent，编写 fundflow 类 Skill，聪明钱追踪 |
| 专家4组（宏观） | 西西 | 维护宏观周期 Agent，编写 macro 类 Skill，大周期判断 |
| 专家5组（行业） | 云水禅人 | 维护行业景气 Agent，编写 industry 类 Skill，行业拐点 |
| 专家6组（舆情） | 小皮 | 维护舆情情感 Agent，编写 news 类 Skill，情绪交易信号 |
| 专家7组（风控） | 荔枝枝 | 维护风险预警 Agent，编写 risk 类 Skill，守住底线 |
| 综合组（PMO） | 猫猫 | 任务拆解、进度跟踪、PR Review 排班、版本发布 |
| 气氛组（用户体验） | may | 调试 UI、Signal 可视化、文档可读性、新手友好度 |
| 公共资源部 | 小荷 | 寻找全球顶级资源，提升这个项目全球影响力 |

### 协作规则

- **框架归开发1组** — 其他人不要改 `base.py`、`signal.py`、`registry.py`
- **数据归开发3组** — 真实抓取逻辑进入 `data_sources/`；`skills/data/` 只说明调用参数、返回字段和失败格式，Agent 不散落硬编码外部 API
- **Skill 各组自维护** — 每个专家组维护自己领域目录下的 Skill
- **Agent 各组自维护** — 每个专家组维护自己的 Agent 实现
- **Orchestrator 归开发2组** — 仲裁逻辑、推理链、主流程调度
- **PR 必须 Review** — 任何人提交，至少一人看过再合并

---

## License

[Apache License 2.0](LICENSE)

---

## 第一步

不是交易。是观察与理解。

先让7个专家 Agent 跑起来，持续产出信号，但只记录、不执行。积累信号与实际市场走势的对照数据，验证每个 Agent 的独立预测能力，校准编排 Agent 的博弈参数。同时，推理链开始生成——每一条信号背后，都有一条完整的"为什么"。

**只有当你理解了"为什么"，这笔交易才值得做。**

我们信仰信号，但更信仰理解。信号让你这次做对，理解让你次次做对。

---

> **AI Renaissance — Trend as Leverage, Signal as Pulse, Cognition as Wealth.**
