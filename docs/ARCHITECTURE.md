# AI Renaissance 项目架构说明

## 核心架构：8 Agent + N Skill + 数据层

```
┌──────────────────────────────────────────────────────────────────┐
│                  Orchestrator Agent（编排 Agent）                  │
│     信号收集 → 权重聚合 → 方向判定 → 风险约束 → 推理链生成        │
└───────┬──────┬───────┬───────┬───────┬───────┬───────┬──────────┘
        │      │       │       │       │       │       │
   ┌────┴─┐ ┌──┴──┐ ┌──┴──┐ ┌──┴──┐ ┌──┴──┐ ┌──┴──┐ ┌──┴──┐
   │财务  │ │技术  │ │资金  │ │宏观  │ │行业  │ │舆情  │ │风险  │
   │Agent │ │Agent │ │Agent │ │Agent │ │Agent │ │Agent │ │Agent │
   └──┬───┘ └──┬───┘ └──┬───┘ └──┬───┘ └──┬───┘ └──┬───┘ └──┬───┘
      │        │        │        │        │        │        │
   ┌──┴────────┴────────┴────────┴────────┴────────┴────────┴───┐
   │            data_sources（数据执行层） + skills/data（数据接口说明）      │
   └──────────────────────────────────────────────────────────────┘
```

**三个核心层次：**

| 层 | 说明 | 目录 |
|---|---|---|
| Agent 层 | 8 个 Agent，每个专家组维护自己的 Agent | `agents/{domain}/` |
| Skill 层 | N 个 Skill，每个专家组维护自己领域的 Skill | `skills/{domain}/` |
| 数据层 | `data_sources/` 执行真实数据获取；`skills/data/` 描述数据接口说明 | `data_sources/`、`skills/data/` |

---

## Agent 架构

### Agent 基类（开发1组维护）

`agents/base.py` — `BaseAgent` 提供：
- 继承 AgentScope `AgentBase`，为专家 Agent 统一实现 `reply()` / `observe()` / `handle_interrupt()`
- `signal_type` 类属性：标识 Agent 输出的信号类型
- `load_skill()` / `load_skills_from_domain()`：动态加载 Skill
- `list_skills()` / `get_skill()`：Skill 管理
- `analyze()` 项目业务接口：子类必须实现并返回 `Signal`
- `pre_analyze()` / `post_analyze()` / `run()`：模板方法模式

### Skill 注册机制（开发1组维护）

`agents/registry.py` — `SkillRegistry` 提供：
- `scan_domain()` / `scan_all()`：扫描 Skill 目录
- `register()` / `load_skill()`：注册和加载
- `get_skills_by_domain()`：按领域查询
- 全局单例 `get_registry()`

### Orchestrator Agent（开发2组维护）

`agents/orchestrator/` 包含：
- `agent.py`：OrchestratorAgent — 编排入口
- `arbitration.py`：ArbitrationEngine — 10步仲裁引擎

**编排流程：**
1. 调用7个专家Agent的 `analyze()`，收集 Signal
2. 信号筛选（置信度阈值过滤）
3. 加权聚合（按 signal_type 权重）
4. 方向判定（多空比率 > 0.6）
5. 风险约束（风险Agent信号折扣）
6. 推理链生成（信号汇总 → 方向 → 置信度 → 仓位 → 风险）
7. 输出 `ArbitrationResult`

### 7 个专家 Agent

每个专家 Agent 结构相同：
```
agents/{domain}/
├── __init__.py
└── agent.py      # {Domain}Agent(BaseAgent)
```

Agent 启动时自动加载 `skills/{domain}/` 下所有 Skill。

---

## Skill 架构

### 目录规范

```text
skills/{domain}/{skill_name}/SKILL.md
```

7 个领域对应 7 个专家组的 signal_type：
- `financial` → 专家1组 → `financial`
- `technical` → 专家2组 → `technical`
- `fundflow` → 专家3组 → `fundflow`
- `macro` → 专家4组 → `macro`
- `industry` → 专家5组 → `industry`
- `news` → 专家6组 → `news`
- `risk` → 专家7组 → `risk`

### Skill 加载流程

```
Agent.__init__()
    ↓
self.load_skills_from_domain("financial")
    ↓
扫描 skills/financial/ 下所有 */SKILL.md
    ↓
每个 SKILL.md 读取内容，存入 self._skills
    ↓
Agent.analyze() 时通过 self.get_skill(name) 获取内容
```

### Skill 模板

专家分析 Skill 详见 `docs/ANALYSIS_SKILL_TEMPLATE.md`。
数据接口说明 Skill 详见 `docs/DATA_SKILL_TEMPLATE.md`。

---

## 数据层架构

### 设计原则

- **执行代码放在 `data_sources/`**，负责请求、解析、编码、异常处理和结构化返回
- **数据接口说明放在 `skills/data/`**，说明输入参数、输出字段、失败格式和数据边界
- **开发3组统一维护**，Agent 依据数据接口说明调用数据源，不散落硬编码外部 API

### 目录结构

```
data_sources/
├── __init__.py
├── base.py           # DataSourceBase（基类）
├── eastmoney.py      # EastMoneyDataSource（东方财富财报）
└── eastmoney_guba.py # EastMoneyGubaDataSource（东方财富股吧）
```

```text
skills/data/
└── eastmoney_guba/
    ├── SKILL.md      # 股吧帖子数据接口说明
    └── scripts/
        └── fetch_guba.py  # CLI 调试包装器，核心逻辑在 data_sources/
```

### 基类接口

```python
class DataSourceBase(ABC):
    def get_financial_data(stock_code, report_date) -> dict  # 三张表
    def get_market_data(stock_code, period) -> dict           # 行情
    def get_fund_flow_data(stock_code) -> dict                # 资金流向
    def normalize_code(code) -> str                           # 代码标准化
```

---

## 数据流图

```
用户输入股票代码
      ↓
OrchestratorAgent.analyze(stock_code)
      ↓
┌─── 并行调用 7 个专家 Agent ───┐
│                               │
│ FinancialAgent.analyze()      │──→ 加载 skills/financial/ Skill
│ TechnicalAgent.analyze()      │──→ 加载 skills/technical/ Skill
│ FundflowAgent.analyze()       │──→ 加载 skills/fundflow/  Skill
│ MacroAgent.analyze()          │──→ 加载 skills/macro/     Skill
│ IndustryAgent.analyze()       │──→ 加载 skills/industry/  Skill
│ NewsAgent.analyze()           │──→ 加载 skills/news/      Skill
│                               │──→ 读取 skills/data/      数据接口说明
│ RiskAgent.analyze()           │──→ 加载 skills/risk/      Skill
│                               │
│    每个 Agent 通过 data_sources 获取数据
│    按 Skill 规则分析 → 输出 Signal
└───────────────────────────────┘
      ↓
SignalBundle（7 个 Signal）
      ↓
ArbitrationEngine.arbitrate()
  ├── 信号筛选（置信度阈值）
  ├── 加权聚合
  ├── 方向判定
  ├── 风险约束
  └── 推理链生成
      ↓
ArbitrationResult
  ├── decision (buy/hold/sell/wait)
  ├── direction (bullish/bearish/neutral)
  ├── confidence
  ├── position_ratio
  ├── reasoning
  ├── risks
  └── reasoning_chain
```

---

## 与旧架构的变化

| 维度 | 旧架构（50+ Agent） | 新架构（8 Agent + N Skill） |
|------|---------------------|---------------------------|
| Agent 数量 | 50+ 个细粒度 Agent | 8 个 Agent（1 编排 + 7 专家） |
| Agent 结构 | 四层（感知/研究/风控/认知） | 扁平化，每组1个Agent |
| 感知层 | 9 个独立数据 Agent | 合并到 data_sources/ 数据执行层，数据接口说明放入 skills/data/ |
| 风控层 | 6 个风控 Agent | 专家7组 RiskAgent，输出Signal参与博弈 |
| 认知层 | 4 个推理 Agent | 合并到 Orchestrator Agent |
| 仲裁 | arbitration/engine.py | agents/orchestrator/arbitration.py |
| Skill 加载 | Agent 硬编码 Skill 路径 | 动态加载 + 全局注册表 |
| 数据获取 | Agent 内直接调 API | Agent 调 data_sources/，skills/data/ 描述数据接口说明 |

---

*最后更新：2026-05-03*
