# Agent 开发指南

> 面向各专家组。每个专家组维护自己的 Agent 和 Skill。
> 核心任务：实现 `analyze()` 方法，返回标准 `Signal`。

---

## 一、8 Agent + N Skill 架构

每个专家组负责1个 Agent，Agent 动态加载自己领域的 Skill，输出标准 Signal。

```
agents/
├── base.py                   # Agent 基类（开发1组维护）
├── signal.py                 # Signal 格式（开发1组维护）
├── registry.py               # Skill 注册表（开发1组维护）
├── orchestrator/             # 编排 Agent（开发2组）
├── financial/                # 你在这里 ← 专家1组
├── technical/                # 你在这里 ← 专家2组
├── fundflow/                 # 你在这里 ← 专家3组
├── macro/                    # 你在这里 ← 专家4组
├── industry/                 # 你在这里 ← 专家5组
├── news_agent/               # 你在这里 ← 专家6组
└── risk/                     # 你在这里 ← 专家7组
```

---

## 二、Agent 与 Skill 的关系

- **Skill**：专家写的分析规则说明书，放在 `skills/{domain}/{skill_name}/SKILL.md`
- **Agent**：自动加载自己领域下的所有 Skill，按 Skill 规则分析，输出 Signal
- **数据**：通过 `data_sources/` 统一获取，不直接调 API

```python
# Agent 启动时自动加载
self.load_skills_from_domain("financial")  # 加载 skills/financial/ 下所有 SKILL.md

# 分析时使用 Skill
skill_content = self.get_skill("financial_report_analysis")
# 按 Skill 规则分析数据...
```

---

## 三、Agent 模板

每个专家 Agent 基本结构：

```python
# agents/{domain}/agent.py

from typing import Optional
from agents.base import BaseAgent
from agents.signal import Signal, bullish_signal, bearish_signal, neutral_signal


class YourAgent(BaseAgent):
    """你的 Agent 描述（专家X组）"""

    signal_type = "your_signal_type"  # financial/technical/fundflow/macro/industry/news/risk

    def __init__(self, config: Optional[dict] = None):
        super().__init__(name="你的Agent名", config=config or {})
        # 启动时自动加载自己领域的所有 Skill
        self.load_skills_from_domain("your_domain")

    def analyze(self, stock_code: str) -> Signal:
        """
        核心分析逻辑

        1. 获取数据（通过 data_sources）
        2. 按 Skill 规则分析
        3. 封装成标准 Signal 返回
        """
        self.log(f"开始分析：{stock_code}")

        try:
            # 1. 获取数据
            data = self._fetch_data(stock_code)

            # 2. 按 Skill 规则分析
            result = self._analyze_with_skill(data, stock_code)

            # 3. 封装 Signal
            return self._build_signal(result, stock_code)

        except Exception as e:
            return neutral_signal(
                confidence=0.1,
                reasoning=f"分析出错：{str(e)}",
                source=self.name,
                stock_code=stock_code,
                signal_type=self.signal_type,
            )

    def _fetch_data(self, stock_code: str) -> dict:
        """从数据层获取数据"""
        data_source = self.config.get("data_source")
        if data_source:
            return data_source.get_financial_data(stock_code)
        return {}

    def _analyze_with_skill(self, data: dict, stock_code: str) -> dict:
        """按 Skill 规则分析"""
        # TODO: 实现你的分析逻辑
        return {"direction": "neutral", "confidence": 0.1, "reasoning": "待实现"}

    def _build_signal(self, result: dict, stock_code: str) -> Signal:
        """封装成标准 Signal"""
        direction = result.get("direction", "neutral")
        confidence = result.get("confidence", 0.5)
        reasoning = result.get("reasoning", "")
        signals = result.get("signals", [])

        kwargs = {
            "confidence": confidence,
            "reasoning": reasoning,
            "signals": signals,
            "source": self.name,
            "stock_code": stock_code,
            "signal_type": self.signal_type,
            "weight": result.get("weight", 1.0),
            "meta": result.get("meta", {}),
        }

        if direction == "bullish":
            return bullish_signal(**kwargs)
        elif direction == "bearish":
            return bearish_signal(**kwargs)
        else:
            return neutral_signal(
                confidence=kwargs["confidence"],
                reasoning=kwargs["reasoning"],
                source=kwargs["source"],
                stock_code=kwargs["stock_code"],
                signal_type=kwargs["signal_type"],
                meta=kwargs["meta"],
            )
```

---

## 四、__init__.py 模板

```python
# agents/{domain}/__init__.py

from .agent import YourAgent

__all__ = ["YourAgent"]
```

---

## 五、Signal 对象详解

所有 Agent 必须返回 `Signal` 对象：

```python
from agents.signal import Signal

signal = Signal(
    direction="bullish",       # "bullish" | "bearish" | "neutral"
    confidence=0.85,          # 0.0 ~ 1.0
    reasoning="为什么看多",    # 文字说明
    signals=["信号1", "信号2"],  # 具体信号列表
    source="财务分析Agent",    # Agent 名称
    signal_type="financial",  # 信号类型
    stock_code="000001",      # 股票代码
    weight=1.0,              # 权重（仲裁用）
    meta={"key": "value"}     # 额外数据
)
```

### 便捷函数（推荐）

```python
from agents.signal import bullish_signal, bearish_signal, neutral_signal

signal = bullish_signal(
    confidence=0.8, reasoning="...", signals=["..."],
    source="你的Agent", stock_code="000001",
    signal_type="financial",
)
```

### 置信度参考

- **0.9+**：非常确定（合同负债+200%）
- **0.7~0.9**：比较确定（净利润增长30%）
- **0.5~0.7**：有可能（技术指标金叉）
- **<0.5**：不确定，返回 `neutral`

---

## 六、Skill 加载机制

### 自动加载（推荐）

Agent 启动时自动加载整个领域的 Skill：

```python
def __init__(self, config=None):
    super().__init__(name="财务分析Agent", config=config or {})
    self.load_skills_from_domain("financial")
    # 自动扫描 skills/financial/ 下所有 */SKILL.md
```

### 手动加载

```python
self.load_skill("skills/financial/financial_report_analysis/SKILL.md")
```

### 使用 Skill

```python
skill_content = self.get_skill("financial_report_analysis")
# 把 skill_content 作为 system prompt，数据作为 user message 发给 LLM
```

---

## 七、数据获取

所有数据通过 `data_sources/` 获取，不直接调 API：

```python
from data_sources import EastMoneyDataSource

data_source = EastMoneyDataSource()

# 获取三张表
financial_data = data_source.get_financial_data("600519")

# 获取行情
market_data = data_source.get_market_data("600519")

# 获取资金流向
fund_flow = data_source.get_fund_flow_data("600519")
```

Agent 通过 config 注入数据源：

```python
data_source = EastMoneyDataSource()
agent = FinancialAgent(config={"data_source": data_source})
```

---

## 八、如何测试

### 直接运行

```python
from agents.financial import FinancialAgent
from data_sources import EastMoneyDataSource

data_source = EastMoneyDataSource()
agent = FinancialAgent(config={"data_source": data_source})
signal = agent.analyze("600519")
print(signal)
```

### 集成到主程序

```python
from agents.orchestrator import OrchestratorAgent
from agents.financial import FinancialAgent
from agents.technical import TechnicalAgent
# ... 其他 Agent

orchestrator = OrchestratorAgent()
orchestrator.register_expert(FinancialAgent(config={...}))
orchestrator.register_expert(TechnicalAgent(config={...}))
# ... 注册其他专家

result = orchestrator.analyze("600519")
print(result.decision, result.direction, result.confidence)
```

---

## 九、常见问题

### Q1: Skill 和 Agent 是什么关系？

**A**: Skill 是专家写的分析规则（Markdown），Agent 是执行者（Python 代码）。Agent 加载 Skill，按 Skill 规则分析数据，输出 Signal。一个 Agent 可以加载多个 Skill。

### Q2: 数据从哪来？

**A**: 通过 `data_sources/` 统一获取，不直接调 API。开发3组维护数据层，你只需在 config 里传入 data_source。

### Q3: 风险Agent也输出Signal吗？

**A**: 是的。风险预警 Agent（专家7组）也输出标准 Signal，参与 Orchestrator Agent 的仲裁博弈。风险偏负面用 `bearish`，仅监控提示用 `neutral`。

### Q4: Orchestrator 怎么用我的 Agent？

**A**: 通过 `orchestrator.register_expert(agent)` 注册，Orchestrator 会自动调用你的 `analyze()` 方法收集信号。

---

*最后更新：2026-05-03*
