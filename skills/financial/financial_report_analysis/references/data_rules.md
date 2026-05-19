# 数据规则

## 核心原则

没有来源的数据不得进入核心判断。查不到就写 `unknown` 或 `_待补_`，不得凭行业常识、记忆或推测填数。

## 来源可信度

| 来源 | `source_type` | 可信度 | 用法 |
|---|---|---|---|
| 交易所公告原文、巨潮 PDF、上市公司公告 | `financial_report` / `announcement` | 5 | 可作为核心证据 |
| 数据组封装 API、东方财富公告数据 | `data_source` | 4-5 | 可作为核心证据，字段需与数据组口径一致 |
| westock、neodata、研报 | `data_vendor` / `research` | 3-4 | 可辅助验证 |
| 媒体、社交平台、论坛 | `news` / `social` | 1-2 | 只能作背景，不作核心证据 |

## A/B/C 三类数据

| 类型 | 定义 | 处理 |
|---|---|---|
| A 类 | 直接来自公告/API 的原始数据 | 正常引用 |
| B 类 | 基于 A 类数据计算的比率或变化率 | 标注公式和底层来源 |
| C 类 | 无法从官方渠道验证的数据 | 加警示，不作为核心判断 |

## `meta.evidence` 字段

每条证据至少包含：

```json
{
  "source_type": "financial_report",
  "source_name": "2026Q1 quarterly report",
  "date": "2026-04-30",
  "metric": "operating_cash_flow",
  "value": 123456789,
  "comparison": "yoy +18.2%",
  "note": "直接来自现金流量表"
}
```

## 计算规则

- 同比：本期对上年同期。
- 环比：本期对上一报告期。
- 金额单位必须统一，推荐使用元；展示可在 `note` 中说明亿元/万元。
- 比率分母为 0 或缺失时，不得强算，步骤状态为 `unknown`。
- 多来源冲突时，优先公告原文，其次数据组封装，最后供应商或媒体。

## 与数据组边界

本 Skill 只定义字段需求和判断逻辑，不封装数据源。字段映射、复权、公告解析、接口稳定性由 `data_sources/` 负责。`scripts/analyze_report.py` 中的 `_normalize_finance_data` 只保留接驳 TODO。
