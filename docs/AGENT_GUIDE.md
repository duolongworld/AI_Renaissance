# Agent 开发指南

> 面向开发2组或负责 Agent 实现的成员。核心任务是实现 `analyze()` 方法，并返回标准 `Signal`。

---

## 一、目录结构

每个 Agent 都有自己的文件夹，按分类放置：

```
agents/
├── perception/          # 感知层（数据获取）
│   └── 你的Agent名/
│       ├── __init__.py
│       ├── config.py    # 配置文件
│       └── agent.py     # 核心逻辑（你写这里）
│
├── research/            # 研究层（信号生成）
│   └── 你的Agent名/
│       └── ...
│
└── risk/               # 风控层
    └── ...
```

---

## 二、Agent 与 Skill 的关系

当前协作方式里，专家组把专业分析规则写入：

```text
skills/{domain}/{skill_name}/SKILL.md
```

开发2组或负责 Agent 实现的成员，在 `agents/` 中实现调用逻辑：

1. 读取对应的 `SKILL.md`。
2. 获取或接收数据输入。
3. 调用模型、规则逻辑或本地计算。
4. 把结果封装成标准 `Signal`。

这样专家组可以专注专业判断规则，Agent 实现可以专注数据流、调用方式和工程稳定性。

---

## 三、最简 Agent 模板

可以从下面这个模板起步，根据实际 Skill、数据源和业务逻辑调整。

```python
# agents/research/你的分类/你的Agent名/agent.py

from pathlib import Path

from agents.base import BaseAgent
from agents.signal import Signal, neutral_signal


class YourAgent(BaseAgent):
    """你的 Agent 描述"""

    def __init__(self, config: dict):
        super().__init__(name="你的Agent名", config=config)
        repo_root = self._find_repo_root()
        self.skill_path = (
            repo_root
            / "skills" / "你的domain" / "你的skill_name" / "SKILL.md"
        )

    def analyze(self, stock_code: str) -> Signal:
        """
        Agent 的职责：
        1. 读取专家组维护的 SKILL.md
        2. 获取或接收开发3组封装的数据
        3. 调用模型、规则逻辑或本地计算
        4. 把结果封装成标准 Signal
        """
        skill_content = self._load_skill()
        data = self._fetch_data(stock_code)
        result = self._call_skill(skill_content, data)
        return self._to_signal(result, stock_code)

    def _load_skill(self) -> str:
        return self.skill_path.read_text(encoding="utf-8")

    def _find_repo_root(self) -> Path:
        for parent in Path(__file__).resolve().parents:
            if (parent / "skills").exists() and (parent / "agents").exists():
                return parent
        raise RuntimeError("找不到项目根目录")

    def _fetch_data(self, stock_code: str) -> dict:
        """从开发3组封装的数据接口获取输入。"""
        return self.config["data_provider"].get_financial_data(stock_code)

    def _call_skill(self, skill_content: str, data: dict) -> dict:
        """按 Skill 规则调用 LLM 或本地规则逻辑，返回标准 JSON 字典。"""
        return self.config["llm_client"].analyze(skill_content, data)

    def _to_signal(self, result: dict, stock_code: str) -> Signal:
        try:
            return Signal.from_dict({**result, "stock_code": stock_code})
        except Exception as exc:
            return neutral_signal(
                confidence=0.1,
                reasoning=f"Skill 输出无法解析为 Signal：{exc}",
                source=self.name,
                stock_code=stock_code,
            )

    def batch_analyze(self, stock_codes: list) -> list:
        """批量分析（可选实现）"""
        return [self.analyze(code) for code in stock_codes]
```

---

## 四、配置文件模板

```python
# agents/research/你的分类/你的Agent名/config.py

CONFIG = {
    # Agent基本信息
    "name": "你的Agent名",
    "version": "0.1",
    "author": "你的名字",

    # 分析参数
    "param1": 100,              # 参数1说明
    "param2": 0.05,             # 参数2说明

    # 置信度阈值
    "confidence_threshold": 0.6,  # 低于此值不输出信号

    # 股票范围（可选）
    "stocks": ["000001", "600519"],  # 分析哪些股票
}
```

---

## 五、__init__.py 模板

```python
# agents/research/你的分类/你的Agent名/__init__.py

from .agent import YourAgent

__all__ = ["YourAgent"]
```

---

## 六、Signal 对象详解

Agent 需要返回 `Signal` 对象，格式如下：

```python
from agents.signal import Signal

signal = Signal(
    direction="bullish",       # 需要是 "bullish" | "bearish" | "neutral"
    confidence=0.85,          # 需要在 0.0 ~ 1.0 之间
    reasoning="为什么看多",    # 需要写文字说明
    signals=["信号1", "信号2"],  # 可选：检测到的具体信号列表
    source="你的Agent名",      # 需要写 Agent 名称
    signal_type="financial",   # 可选：信号类型
    stock_code="000001",      # 可选：股票代码
    weight=1.0,              # 可选：权重（仲裁层用）
    meta={"key": "value"}      # 可选：额外数据
)
```

### 便捷函数（推荐用这个）

```python
from agents.signal import bullish_signal, bearish_signal, neutral_signal

# 看多信号
signal = bullish_signal(
    confidence=0.8,
    reasoning="...",
    signals=["...", "..."],
    source="你的Agent",
    stock_code="000001"
)

# 看空信号
signal = bearish_signal(...)

# 中性信号
signal = neutral_signal(...)
```

---

## 七、常见数据类型与计算

### 6.1 涨跌幅计算

```python
def calculate_change_pct(current, previous):
    """计算涨跌幅"""
    if previous == 0:
        return 0.0
    return (current - previous) / abs(previous)
```

### 6.2 同比增长率

```python
def calculate_yoy_growth(current, last_year):
    """计算同比增长率"""
    if last_year == 0:
        return 0.0
    return (current - last_year) / abs(last_year)
```

### 6.3 均线计算

```python
import pandas as pd

def calculate_ma(prices: list, window: int) -> float:
    """计算简单移动平均"""
    if len(prices) < window:
        return 0.0
    return sum(prices[-window:]) / window
```

---

## 八、如何测试你的 Agent

### 方法1：直接运行

```python
# test_your_agent.py
from agents.research.你的分类.你的Agent名.agent import YourAgent
from agents.research.你的分类.你的Agent名.config import CONFIG

# 创建Agent
agent = YourAgent(CONFIG)

# 测试单只股票
signal = agent.analyze("000001")
print(signal)

# 测试批量
signals = agent.batch_analyze(["000001", "600519"])
for s in signals:
    print(s)
```

运行：
```bash
cd AIRenaissance
python test_your_agent.py
```

### 方法2：集成到主程序

修改 `main.py` 中的 `collect_signals()` 函数，添加你的Agent：

```python
# main.py 中找到 collect_signals() 函数

# 添加你的Agent
from agents.research.你的分类.你的Agent名.agent import YourAgent

agent = YourAgent(config={})
signal = agent.analyze(stock_code)
bundle.add(signal)
```

---

## 九、常见问题

### Q1: 我不会 Python 怎么办？

**A**: 可以先从已有 Agent 示例读起，再让 Coding 工具辅助解释代码。负责 Agent 实现的成员重点理解三件事：读取输入、调用 Skill 或规则逻辑、返回 `Signal`。

### Q2: 数据从哪里来？

**A**: 项目会提供统一的数据接口，你可以：
- 调用 `perception/` 下的数据Agent
- 使用开发3组封装的数据源
- 在联调早期用示例数据测试逻辑

### Q3: 置信度怎么定？

**A**: 经验法则：
- 0.9+：非常确定（如合同负债+200%）
- 0.7~0.9：比较确定（如净利润增长30%）
- 0.5~0.7：有可能（如技术指标金叉）
- <0.5：不确定，建议返回 `neutral`

### Q4: 如何处理错误？

**A**: 用 `try...except` 包裹你的逻辑：

```python
def analyze(self, stock_code: str) -> Signal:
    try:
        # 你的逻辑
        return signal
    except Exception as e:
        # 出错时返回中性信号
        return neutral_signal(
            confidence=0.1,
            reasoning=f"分析出错：{str(e)}",
            source=self.name,
            stock_code=stock_code,
        )
```

### Q5: 如何调试？

**A**: 用 `self.log()` 打印日志：

```python
def analyze(self, stock_code: str) -> Signal:
    self.log(f"开始分析 {stock_code}")
    # ...
    self.log(f"计算结果：{result}")
    return signal
```

---

## 十、任务认领流程

1. **在群里说**：「我要做 [某类] Agent」
2. **创建Issue**：在GitHub上创建Issue，格式：
   ```markdown
   ## Agent名称
   [你的名字]的[某类]Agent

   ## 分析逻辑
   简要描述你的分析思路

   ## 预计完成
   Week X
   ```
3. **开发**：按本文档指引开发
4. **提交**：Fork → 开发 → PR
5. **集成**：由开发2组或项目维护者把 Agent 接入主流程

---

## 十一、完整示例：现金流验证 Agent

```python
# agents/research/financial/cash_flow/agent.py

from pathlib import Path

from agents.base import BaseAgent
from agents.signal import Signal, neutral_signal


class CashFlowAgent(BaseAgent):
    """现金流验证 Agent：调用现金流质量 Skill，封装 Signal。"""

    def __init__(self, config: dict):
        super().__init__(name="现金流验证Agent", config=config)
        repo_root = self._find_repo_root()
        self.skill_path = (
            repo_root
            / "skills" / "financial" / "cash_flow_quality_check" / "SKILL.md"
        )

    def analyze(self, stock_code: str) -> Signal:
        skill_content = self.skill_path.read_text(encoding="utf-8")
        financial_data = self.config["data_provider"].get_financial_data(stock_code)
        result = self.config["llm_client"].analyze(skill_content, financial_data)

        try:
            return Signal.from_dict({**result, "stock_code": stock_code})
        except Exception as exc:
            return neutral_signal(
                confidence=0.1,
                reasoning=f"现金流 Skill 输出无法解析为 Signal：{exc}",
                source=self.name,
                stock_code=stock_code,
                signal_type="financial",
            )

    def _find_repo_root(self) -> Path:
        for parent in Path(__file__).resolve().parents:
            if (parent / "skills").exists() and (parent / "agents").exists():
                return parent
        raise RuntimeError("找不到项目根目录")
```

---

**最后**：有任何问题，在群里@我！
