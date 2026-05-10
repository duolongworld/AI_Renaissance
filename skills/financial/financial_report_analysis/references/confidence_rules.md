# Confidence 反推规则

`confidence` 必须由证据质量反推，不允许直接凭七步通过数或主观确信填写。

## 四个维度

| 维度 | 0 分 | 1 分 | 2 分 |
|---|---|---|---|
| 证据数量 | 少于 3 条关键证据 | 3-5 条 | 6 条以上，覆盖三表 |
| 独立性 | 单一来源 | 两类来源 | 三类以上来源，含公告原文 |
| 一致性 | 核心证据互相冲突 | 大体一致但有解释项 | 方向一致且能闭环 |
| 可靠性 | 主要为媒体/估算 | 混合来源 | 主要为公告/API 原始数据 |

总分 0-8 分，先映射基础置信度：

| 总分 | confidence 上限 |
|---|---|
| 0-2 | 0.4 |
| 3-4 | 0.55 |
| 5-6 | 0.7 |
| 7 | 0.8 |
| 8 | 0.9 |

## 强制降档

- 任一三表缺失：`confidence <= 0.4`。
- 核心指标来自 C 类数据：`confidence <= 0.55`。
- Step0 触发财务重述、收入确认重大变更、商誉重大减值风险：`confidence <= 0.65` 且 `needs_human_review: true`。
- 七步链结论与证据强度冲突时，取较低值。

## 输出要求

`meta.confidence_breakdown` 必须写明：

```json
{
  "evidence_count_score": 2,
  "independence_score": 2,
  "consistency_score": 1,
  "reliability_score": 2,
  "total_score": 7,
  "cap": 0.8,
  "final_confidence": 0.74,
  "reason": "三表证据充分，但合同负债与营收方向存在轻微背离"
}
```
