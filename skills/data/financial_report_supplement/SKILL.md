---
name: financial-report-supplement
description: 从巨潮定期报告正文与表格提取订单、产能、分部、产品线和折旧摊销，作为 FinancialAgent 三表分析的官方补充证据。真实获取与解析位于 data_sources/financial_report_supplement.py。
owner_group: 开发3组（数据）
domain: data
status: draft
---

# 巨潮财报补充数据接口

## 1. 适用范围

本接口为 FinancialAgent 补齐东财三表中没有的官方披露字段：已签订单、在手订单、产能规划/利用率、分部、产品线、折旧摊销。数据只来自巨潮法定定期报告，不作投资判断。

边界：

- 订单范围必须原样保留；“某客户”或“某业务板块”订单不得冒充公司全部订单。
- 产能规划可以是定性文本；未披露产能利用率时保持缺失。
- PDF 表格解析失败时，仍返回正文中可提取的字段并记录 warning。
- 巨潮整体失败不得中断东财三表分析。

## 2. 执行数据源

```text
data_sources/cninfo.py                         # 巨潮报告查找、下载与缓存
data_sources/financial_report_supplement.py    # 字段提取与来源记录
```

```python
from data_sources import FinancialReportSupplementDataSource

source = FinancialReportSupplementDataSource()
result = source.get_financial_supplement("300757", "2026-06-30")
```

## 3. 输入参数

| 参数 | 类型 | 说明 |
|---|---|---|
| `stock_code` | string | 6 位 A 股代码，允许带交易所后缀 |
| `report_date` | string | `YYYY-MM-DD`，仅支持 03-31 / 06-30 / 09-30 / 12-31 |

`resolve_latest_report_date(stock_code)` 按当日可能已披露的报告期由新到旧试取，只有巨潮返回报告本体才确认该报告期。

## 4. 输出格式

```json
{
  "status": "success",
  "stock_code": "300757",
  "report_date": "2026-06-30",
  "source": {
    "source_type": "official_filing",
    "source_name": "CNINFO",
    "ann_id": "1225507370",
    "ann_date": "20260826",
    "pdf_url": "..."
  },
  "fields": {
    "signed_orders": 1261000000.0,
    "order_backlog": 3386000000.0,
    "capacity_expansion_plan": "...",
    "segments": {},
    "product_lines": [],
    "depreciation_amortization": 33448567.18
  },
  "field_sources": {
    "signed_orders": {
      "unit": "CNY",
      "scope": "same_customer_group",
      "evidence": "...",
      "report_page": 11
    }
  },
  "missing_fields": ["capacity_utilization"],
  "warnings": []
}
```

`status` 为 `success` / `partial` / `error`。失败时 `fields` 和 `field_sources` 稳定返回空字典，`error` 说明原因。

## 5. 数据获取流程

1. 报告期映射为 annual / q1 / h1 / q3。
2. 通过 `CninfoDataSource` 取报告本体及本地 PDF/Markdown 路径。
3. 从正文提取订单和产能原文，从 PDF 表格提取分部、产品线、折旧摊销。
4. 每个字段附加公告 ID、日期、链接、单位、范围、页码和证据片段。
5. FinancialAgent 只合并当期补充字段；历史期三表不触发额外 PDF 解析。

## 6. 质量检查

- 数值统一转为元/比率，原单位与范围在 `field_sources` 中可追溯。
- 折旧摊销仅从“现金流量表补充资料”表取当期金额，避免误取会计政策或资产明细表。
- 分部收入优先使用“对外交易收入”，避免重复计入分部间交易。
- 当前只补证据，不新增方向或置信度阈值。
