# bridgewater_economic_machine_lite

专家2组（指标）认领的桥水经济机器轻量化周期判断 Skill。

当前 Skill 版本：`0.3.1-agent-only-task-aligned`；项目标准输出版本：`0.1`。

## 用途

本版本是 **agent-only clean 版**：只保留 Agent 执行任务所需的 Skill 规则，不包含外部数据源寻找、API 配置、抓数脚本、source registry 或运行缓存。

## 输入前提

周期与指标数据由用户、上游数据模块、研究员或系统数据层提供。本 Skill 不负责寻找数据源，也不负责联网抓数。

## 输出

必须输出项目标准 Signal JSON，且 `signals` 为字符串列表，证据细节进入 `meta.evidence`：

- direction
- confidence
- reasoning
- signals
- source
- signal_type
- stock_code
- weight
- meta

## 状态

status: draft

建议先由专家2组（指标）审核，再进入 ready。


## 任务覆盖

本 v3 版本补齐任务文档中的三类要求：

1. 全天候策略：作为资产配置防御层输出，不做具体交易。
2. 纯粹阿尔法策略：只保留假设、证据、反证和风控边界，不输出做多/做空指令。
3. 普通投资者原则：补充现金流安全、杠杆控制、相关性分散、定期再平衡和个人风控提醒。

仍然不包含 API、FRED、source registry、抓数脚本或外部数据源寻找逻辑。


## 本地校验

本包新增 `tests/validate_signal_outputs.py`，只做本地 JSON 结构校验，不抓取外部数据。

运行方式：

```bash
python tests/validate_signal_outputs.py
```

校验范围：YAML front matter、示例输入/输出 JSON、标准 Signal 顶层字段、`meta` 必填字段、枚举值、证据字段、低置信度/缺数据规则。
