---
name: cash-flow-quality-check-example
description: 示例 Skill，用于展示如何判断公司利润是否有现金流支撑。该 Skill 仅作专家组编写参考。
owner_group: 专家1组（财务）
domain: financial
status: example
enabled: false
---

# 现金流质量检查示例 Skill

> 这是根据现有 `skills/financial_report_analysis/SKILL.md` 中“用现金流验证利润质量”的思想，抽出来的一个简化示例。它不是对原财报 Skill 的完整总结，只用于演示专家组如何按通用模板写一个更小、更容易调试的 Skill。
>
> 这是示例目录。正式提交时，请复制到类似 `skills/financial/cash_flow_quality_check/SKILL.md` 的正式目录，并根据真实 Skill 删除 `-example` 相关命名。

## 1. 适用范围

所属小组：专家1组（财务）

适用任务：
- 判断公司利润是否有现金流支撑。
- 识别利润增长但经营现金流恶化的风险。
- 为财报质量、利润质量、阶段性财务总结提供信号。

边界说明：
- 如果缺少现金流量表或利润表，输出中标记需要人工复核。
- 该 Skill 只判断现金流质量，不单独给出完整投资建议。

## 2. 输入材料

### 必填输入

- 股票代码或公司名
- 分析期间，例如年度、季度、最近四个季度
- 净利润
- 经营活动现金流量净额
- 数据来源

### 可选输入

- 营业收入
- 应收账款
- 存货
- 合同负债
- 历史同期数据
- 行业对比数据

### 缺失处理

- 如果缺少净利润或经营活动现金流量净额，输出 `direction: "neutral"`，`confidence` 不高于 0.4，并在 `meta.uncertainties` 写明缺失项。
- 如果缺少应收账款、存货或合同负债，可以继续判断现金流与利润匹配度，但需要降低 `confidence`，并标记 `meta.needs_human_review: true`。

## 3. 分析步骤

1. 明确分析对象和时间范围。
2. 计算经营现金流量净额与净利润的匹配度。
3. 检查经营现金流是否连续弱于净利润。
4. 检查应收账款和存货是否异常增长。
5. 检查合同负债是否支撑未来收入。
6. 判断利润质量是改善、恶化还是中性。
7. 输出标准 JSON。

## 4. 判断规则

- 经营现金流量净额 / 净利润连续 2 个季度高于 1.0，且应收账款增速不高于收入增速，偏正面。
- 经营现金流量净额 / 净利润连续 2 个季度低于 1.0，偏负面。
- 净利润增长但经营现金流下降，偏负面。
- 应收账款或存货增速高于收入增速 20% 以上，降低置信度并加入风险说明。
- 合同负债增长且经营现金流改善，可作为正面辅助证据。
- 数据不足时输出 `neutral`，并在 `meta.uncertainties` 中写明缺口；其中净利润或经营活动现金流量净额这类核心必填输入缺失时，`confidence` 不高于 0.4。
- 证据充分且方向一致时，`confidence` 可设为 0.8 以上。
- 证据较充分但缺少部分可选输入时，`confidence` 建议在 0.6 到 0.8。
- 其他必填输入缺失或信号冲突时，`confidence` 不高于 0.5，并设置 `meta.needs_human_review: true`。
- 如果现金流弱于利润且应收账款或存货压力同步上升，`risk_level` 至少为 `medium`；如果连续多个报告期恶化，可设为 `high`。

## 5. 标准输出

示例输出：

```json
{
  "direction": "bearish",
  "confidence": 0.72,
  "reasoning": "净利润增长但经营现金流连续弱于净利润，应收账款增速高于收入增速，利润质量存在压力。",
  "signals": [
    "经营现金流连续弱于净利润",
    "应收账款增速高于收入增速",
    "利润质量偏弱"
  ],
  "source": "cash-flow-quality-check-example",
  "signal_type": "financial",
  "stock_code": "<示例股票代码>",
  "weight": 1.0,
  "meta": {
    "output_version": "0.1",
    "skill_name": "cash_flow_quality_check",
    "owner_group": "专家1组（财务）",
    "target": "<示例公司>",
    "period": "<示例报告期>",
    "time_horizon": "mid",
    "risk_level": "medium",
    "key_findings": [
      "利润增长缺少现金流同步验证",
      "营运资金占用上升"
    ],
    "evidence": [
      {
        "source_type": "financial_report",
        "source_name": "<示例公司三季报>",
        "date": "<示例日期>",
        "metric": "经营现金流量净额 / 净利润",
        "value": "0.62",
        "comparison": "低于 1.0",
        "note": "现金流对利润支撑不足"
      }
    ],
    "risk_notes": [
      "如果应收账款后续无法回款，利润质量可能继续下降"
    ],
    "uncertainties": [
      "需要核对现金流量表口径和一次性项目影响"
    ],
    "needs_human_review": true
  }
}
```

## 6. 质量检查

输出前检查：

- 是否说明现金流与净利润的关系
- 是否检查应收账款和存货
- 是否检查合同负债
- 是否引用数据来源
- 是否把缺失数据写进 `meta.uncertainties`
- 是否输出当前项目支持的 `direction`
