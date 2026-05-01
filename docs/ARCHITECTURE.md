# AI Renaissance 项目结构说明

## 核心架构：Agent → Skill

```
skills/           ← Skill 层（魂）：真正的分析逻辑、Prompt、行业知识
    └── financial_report_analysis/
        ├── SKILL.md          # 分析框架（七步验证链）
        ├── references/       # 参考资料
        └── scripts/         # 辅助脚本

agents/           ← Agent 层（壳）：负责调用 Skill，封装 Signal 输出
    └── research/
        └── financial_report/
            ├── agent.py      # 调用 skills/financial_report_analysis/
            └── __init__.py

debug_ui/         ← 本地调试工具：选择 Agent → 输入股票 → 看 Signal 输出
```

**关系说明：**
- **Skill**：分析能力本体。是一份 Markdown 文档（Prompt + 规则），定义了如何分析财务数据、输出什么格式。
- **Agent**：Skill 的调用者。加载对应的 Skill 文件，把股票代码传给它，把分析结果封装成标准 `Signal` 对象返回。
- **调试 UI**：给小白用的前端，选择自己负责的 Agent，实时看 Signal 输出，验证没问题再提交 PR。

---

## 如何添加一个新的 Skill + Agent

### 第1步：在 `skills/` 下创建 Skill 文件

```
skills/your_skill/
├── SKILL.md         # 核心：分析框架、Prompt、规则
└── references/      # 参考资料（可选）
```

`SKILL.md` 模板：
```markdown
---
name: your-skill
description: 一句话描述
---

# 你的 Skill 名称

## 核心思想
（分析逻辑说明）

## 分析框架
（步骤、公式、判断规则）

## 输出格式
（Agent 需要把结果封装成什么格式）
```

### 第2步：在 `agents/` 下创建 Agent 调用它

```python
# agents/research/xxx/agent.py
from agents.base import BaseAgent
from agents.signal import Signal, bullish_signal, bearish_signal
from pathlib import Path

class YourAgent(BaseAgent):

    def analyze(self, stock_code: str) -> Signal:
        # 1. 加载 Skill
        skill_path = Path(__file__).parent.parent.parent / "skills" / "your_skill" / "SKILL.md"
        skill_content = skill_path.read_text(encoding="utf-8")

        # 2. 获取财务数据（调用东方财富 API / westock-data）
        data = self._fetch_data(stock_code)

        # 3. 调用 LLM，把 skill_content 作为 system prompt，data 作为 user message
        result = self._call_llm(skill_content, data)

        # 4. 把 LLM 输出封装成 Signal
        return self._parse_result(result, stock_code)
```

### 第3步：注册到调试 UI

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
加载 skills/xxx/SKILL.md（分析框架）
      ↓
获取财务数据（东方财富API / westock-data）
      ↓
LLM 按 Skill 框架分析 → 输出 JSON
      ↓
Agent 封装成 Signal 对象
      ↓
调试 UI 展示 Signal（方向/置信度/推理/信号列表）
```

---

*最后更新：2026-05-01*
