# Skill 调试指南

> 目标：先把专家 Skill 的规则、证据和标准输出调稳定，再交给开发2组做 Agent 调用和系统联调。

当前项目设计是：

- **专家组**：负责专业 Skill 内容，包括适用范围、输入材料、判断规则、证据规则和质量检查。
- **开发1组**：负责 Skill 模板、输出规范、目录规范和联调标准。
- **开发2组**：负责 Agent 如何读取 Skill、如何接入数据、如何汇总信号、如何进入仲裁和主流程。

所以第一阶段调试重点不是写 Agent 代码，而是检查 `SKILL.md` 是否能稳定指导 AI 或规则逻辑产出标准 JSON。

---

## 一、调试对象

正式 Skill 使用统一目录：

```text
skills/{domain}/{skill_name}/SKILL.md
```

示例：

```text
skills/financial/cash_flow_quality_check/SKILL.md
skills/risk/tail_risk_warning/SKILL.md
```

示例 Skill 可以参考：

```text
skills/examples/cash_flow_quality_check/SKILL.md
```

模板说明看：

```text
docs/SKILL_TEMPLATE.md
```

---

## 二、先调三件事

### 1. 输入是否清楚

检查 Skill 是否写明：

- 必填输入是什么
- 可选输入是什么
- 数据来源是什么
- 缺少关键数据时如何处理

好的写法示例：

```text
必填输入：
- 股票代码或公司名
- 分析期间
- 净利润
- 经营活动现金流量净额
- 数据来源

缺失处理：
- 缺少净利润或经营现金流时，输出 neutral，降低 confidence，并写入 meta.uncertainties。
```

### 2. 判断规则是否可执行

检查每条规则是否写明：

- 指标
- 阈值或比较对象
- 时间窗口
- 对 `direction` 的影响
- 对 `confidence` 和 `risk_level` 的影响

不够清楚的写法：

```text
现金流不好时偏负面。
```

更清楚的写法：

```text
如果经营现金流量净额 / 净利润连续 2 个季度低于 1.0，
则 direction 倾向 bearish；
如果同时应收账款增速高于收入增速 20% 以上，
则 risk_level 至少为 medium，并降低 confidence。
```

### 3. 标准输出是否稳定

Skill 需要说明最终输出 JSON。顶层字段与 `agents.signal.Signal` 对齐：

```json
{
  "direction": "bullish | bearish | neutral",
  "confidence": 0.0,
  "reasoning": "",
  "signals": [],
  "source": "",
  "signal_type": "financial | technical | fundflow | macro | news | valuation | industry | risk",
  "stock_code": "",
  "weight": 1.0,
  "meta": {}
}
```

补充信息放在 `meta`：

```json
{
  "output_version": "0.1",
  "skill_name": "",
  "owner_group": "",
  "target": "",
  "period": "",
  "time_horizon": "short | mid | long",
  "risk_level": "low | medium | high",
  "key_findings": [],
  "evidence": [],
  "risk_notes": [],
  "uncertainties": [],
  "needs_human_review": true
}
```

---

## 三、用测试样例检查 Skill

每个 Skill 可以准备 3 类样例，让 Coding 工具或人工按 Skill 规则输出 JSON。

| 样例类型 | 目的 |
|---|---|
| 正面样例 | 看是否能输出 `bullish`，并给出正面证据 |
| 负面样例 | 看是否能输出 `bearish`，并给出风险说明 |
| 缺失样例 | 看是否能输出 `neutral`，并写明缺失数据和人工复核点 |

以现金流质量 Skill 为例：

```text
样例A：
净利润 1 亿，经营现金流 1.5 亿，应收账款增速低于收入增速。
预期：方向偏 bullish，证据写入 meta.evidence。

样例B：
净利润增长，但经营现金流连续两季低于净利润，应收账款高增。
预期：方向偏 bearish，risk_level 至少 medium。

样例C：
缺少经营现金流数据。
预期：direction 为 neutral，confidence 降低，needs_human_review 为 true。
```

---

## 四、检查清单

提交 PR 前检查：

- Skill 是否放在 `skills/{domain}/{skill_name}/SKILL.md`
- 是否说明适用范围
- 是否区分必填输入、可选输入和缺失处理
- 判断规则是否包含指标、阈值、比较对象或时间窗口
- 是否说明 `direction`、`confidence`、`risk_level` 如何产生
- 是否说明证据进入 `meta.evidence`
- 是否说明不确定性进入 `meta.uncertainties`
- 是否说明什么情况下 `meta.needs_human_review` 为 `true`
- JSON 顶层字段是否与 `agents.signal.Signal` 对齐

---

## 五、联调时如何交给开发2组

专家组提交 Skill 后，开发2组可以在 Agent 中读取对应 `SKILL.md`，把数据输入给模型或规则逻辑，再封装为 `Signal`。

开发2组联调时重点检查：

- Agent 是否读取了正确的 `SKILL.md`
- 输入数据是否覆盖 Skill 声明的必填项
- LLM 或规则逻辑输出是否能解析为标准 JSON
- `Signal` 是否通过 `direction` 和 `confidence` 校验
- `meta` 是否保留证据、风险等级、时间周期和人工复核点

---

*最后更新：2026-05-02*
