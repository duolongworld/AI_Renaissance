# AI Renaissance 项目结构说明

## 核心架构：Skill → Agent → Signal

```
skills/           ← Skill 层：专家分析逻辑、Prompt、行业知识
    ├── financial_report_analysis/
        ├── SKILL.md          # 分析框架（七步验证链）
        ├── references/       # 参考资料
        └── scripts/         # 辅助脚本
    └── financial/
        └── cash_flow_quality_check/
            └── SKILL.md      # 新 Skill 推荐路径：skills/{domain}/{skill_name}/SKILL.md

agents/           ← Agent 层：负责调用 Skill，封装 Signal 输出
    └── research/
        └── financial_report/
            ├── agent.py      # 调用 skills/financial_report_analysis/
            └── __init__.py

debug_ui/         ← 本地联调工具：选择 Agent → 输入股票 → 查看 Signal 输出
```

**关系说明：**
- **Skill**：专家分析规则说明书。它用 Markdown 写清楚适用范围、输入材料、判断规则、证据规则和标准输出。
- **Agent**：Skill 的执行者。由开发2组在系统流程中实现，负责加载 Skill、接入数据、调用模型或规则逻辑，并封装成标准 `Signal`。
- **Signal**：系统统一读取的信号对象。顶层字段来自 `agents.signal.Signal`，证据和上下文放在 `meta` 中。
- **调试 UI**：本地联调入口，用来查看 Agent 输出的 `Signal` 是否符合规范。

---

## Skill 协作边界

专家组的交付物是专业 Skill 内容。Agent 如何调用 Skill、如何接入数据、如何汇总信号，由开发2组在系统流程中实现。开发1组负责 Skill 模板、输出规范、目录规范和联调标准。

本文件只说明结构、边界和数据流；具体怎么写 Skill，放在模板文档中：

```
docs/SKILL_TEMPLATE.md
```

Coding 工具辅助整理 Skill 时，应直接读取下面这个元 Skill，再根据用户提供的财经规则生成或检查 `SKILL.md`：

```
skills/expert_skill_authoring/SKILL.md
```

示例 Skill 可以参考：

```
skills/examples/cash_flow_quality_check/SKILL.md
```

正式 Skill 统一放在：

```
skills/{domain}/{skill_name}/SKILL.md
```

---

## Agent 调用 Skill

下面内容面向开发2组联调。专家组可以通过这一节理解 Skill 在系统中的位置。

### 示例：在 `agents/` 下创建 Agent 调用器

```python
# agents/research/xxx/agent.py
from agents.base import BaseAgent
from agents.signal import Signal, bullish_signal, bearish_signal
from pathlib import Path

class YourAgent(BaseAgent):

    def analyze(self, stock_code: str) -> Signal:
        # 1. 加载 Skill
        # 从 agents/research/xxx/agent.py 回到仓库根目录对应 parents[3]
        repo_root = Path(__file__).resolve().parents[3]
        skill_path = (
            repo_root
            / "skills" / "financial" / "cash_flow_quality_check" / "SKILL.md"
        )
        skill_content = skill_path.read_text(encoding="utf-8")

        # 2. 获取财务数据（调用开发3组封装的数据接口）
        data = self._fetch_data(stock_code)

        # 3. 调用 LLM，把 skill_content 作为 system prompt，data 作为 user message
        result = self._call_llm(skill_content, data)

        # 4. 把 LLM 输出封装成 Signal
        return self._parse_result(result, stock_code)
```

### 示例：注册到调试 UI

在 `debug_ui/app.py` 的 `AVAILABLE_AGENTS` 字典里加一行：
```python
"你的Agent名": {
    "module": "agents.research.xxx.agent",
    "class": "YourAgent",
    "owner": "你的名字",
    "description": "一句话描述",
},
```

---

## 数据流图

```
用户输入股票代码
      ↓
调试 UI（选择 Agent）
      ↓
Agent.analyze(stock_code)
      ↓
加载 skills/{domain}/{skill_name}/SKILL.md（分析框架）
      ↓
获取财务数据（开发3组封装的数据接口）
      ↓
LLM 按 Skill 框架分析 → 输出 JSON
      ↓
Agent 封装成 Signal 对象
      ↓
调试 UI 展示 Signal（方向/置信度/推理/信号列表）
```

---

*最后更新：2026-05-02*
