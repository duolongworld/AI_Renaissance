# 团队分工（8 Agent + N Skill 架构）

> 各组业务职能，一句话说明白。

---

## 开发组

| 组 | 组长 | 一句话职责 | 涉及目录 |
|---|---|---|---|
| 开发1组（架构） | 荒唐 | 维护 Agent 基类、Signal 规范、Skill 注册机制、Git 工作流 | `agents/base.py`、`agents/signal.py`、`agents/registry.py` |
| 开发2组（功能） | pkm | 实现 Orchestrator Agent、仲裁引擎、推理链、主流程调度 | `agents/orchestrator/` |
| 开发3组（数据） | 过去，未来 | 统一封装所有数据源，让 Agent 只管分析不管数据从哪来 | `data_sources/` |

---

## 专家组

| 组 | 组长 | 一句话职责 | Agent | Skill 域 | signal_type |
|---|---|---|---|---|---|
| 专家1组（财务） | 简简简水粽 | 七步验证链，判断利润是真金白银还是纸面富贵 | `agents/financial/` | `skills/financial/` | financial |
| 专家2组（指标） | C曦 | 计算量价技术指标，识别趋势和背离信号 | `agents/technical/` | `skills/technical/` | technical |
| 专家3组（资金） | Tao | 追踪主力资金流向，发现聪明钱的动向 | `agents/fundflow/` | `skills/fundflow/` | fundflow |
| 专家4组（宏观） | 西西 | 解读利率/汇率/PMI 数据，判断大周期位置 | `agents/macro/` | `skills/macro/` | macro |
| 专家5组（行业） | 云水禅人 | 跟踪产业链景气度和供应链变化，捕捉行业拐点 | `agents/industry/` | `skills/industry/` | industry |
| 专家6组（舆情） | 小皮 | 分析社交情绪和新闻情感，把情绪变成可交易信号 | `agents/news_agent/` | `skills/news/` | news |
| 专家7组（风控） | 荔枝枝 | 识别尾部风险，设定仓位上限，守住不爆仓的底线 | `agents/risk/` | `skills/risk/` | risk |

---

## 支持组

| 组 | 组长 | 一句话职责 |
|---|---|---|
| 综合组（PMO） | 猫猫 | 任务拆解、进度跟踪、PR Review 排班、版本发布 |
| 气氛组（用户体验） | may | 调试 UI、Signal 可视化、文档可读性、新手友好度 |
| 公共资源部 | 小荷 | 寻找全球顶级资源，提升这个项目全球影响力 |

---

## 协作原则

1. **框架归开发1组** — 其他人不要改 `base.py`、`signal.py`、`registry.py`
2. **数据归开发3组** — Agent 只调 `data_sources/` 接口，不直接调 API
3. **Agent 各组自维护** — 每个专家组维护自己的 Agent（`agents/{domain}/`）
4. **Skill 各组自维护** — 每个专家组维护自己领域目录下的 Skill（`skills/{domain}/`）
5. **Orchestrator 归开发2组** — 仲裁逻辑、推理链、主流程调度
6. **PR 必须 Review** — 任何人提交，至少一人看过再合并
