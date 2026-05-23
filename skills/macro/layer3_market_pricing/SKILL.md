---
name: layer3_market_pricing
description: 从市场价格反推市场已定价的内容，与Layer 1的实际基本面状态形成对照。
owner_group: 专家4组（宏观方向）
domain: macro
status: draft
---

# Layer 3: 市场定价提取

## 执行方式

- [x] 数值计算（ERP、信用利差计算）
- [x] 智能分析（LLM解读市场定价含义）
- [ ] 混合模式

## 适用范围

从市场价格反推市场已定价的内容，与 Layer 1 的实际基本面状态形成对照，为 Layer 4 预期差计算提供输入。

## 输入数据规范

### 必填数据

| 数据项 | 来源 | 字段名 | 说明 |
|--------|------|--------|------|
| 中国10Y/2Y国债收益率 | CFETS | cn_10y_yield, cn_2y_yield | 日频 |
| 美国10Y/2Y国债收益率 | Bloomberg | us_10y_yield, us_2y_yield | 日频 |
| 沪深300前瞻PE | Wind | csi300_forward_pe | 日频 |
| 标普500前瞻PE | Bloomberg | sp500_forward_pe | 日频 |
| 沪深300 ERP | Wind | csi300_erp | 日频 |
| 标普500 ERP | Bloomberg | sp500_erp | 日频 |
| AA信用利差 | Wind | aa_credit_spread | 日频 |
| HY信用利差 | ICE BofA | hy_credit_spread | 日频 |
| USD/CNH 1Y远期点 | HKMA | usd_cnh_1y_forward | 日频 |

## 分析步骤

### A. 利率市场反推

| 指标 | 中国版本 | 美国版本 | 反映内容 |
|------|----------|----------|----------|
| 期限利差 | 10Y-2Y国债 | 10Y-2Y UST | 增长预期 |

### B. 估值反推盈利预期

| 指标 | 计算方式 | 反映内容 |
|------|----------|----------|
| 前瞻PE历史百分位 | PE在5年滚动窗口的分位 | 估值乐观/悲观 |
| ERP | 盈利收益率 - 10Y国债 | 风险定价水平 |

### C. 汇率反推资本流动

| 指标 | 反映内容 |
|------|----------|
| USD/CNH 1Y远期点 | 隐含贬值预期 |

### D. 商品反推全球需求

| 指标 | 反映内容 |
|------|----------|
| 铜金比 | 全球工业需求预期 |

### E. 信用反推风险偏好

| 指标 | 反映内容 |
|------|----------|
| AA利差 | 信用风险定价 |
| HY利差 | 经济信心 |

## 标准输出

```json
{
    "layer_name": "layer3",
    "timestamp": "2026-05-15T00:00:00",
    "analysis_result": {
        "rate_pricing": {"cn_term_spread": {"value": 0.5, "interpretation": "增长预期"}},
        "valuation_pricing": {"csi300_pe_percentile": {"value": 70, "interpretation": "偏高"}},
        "expected_diff": {"growth_diff": {"actual": 0.3, "implied": 0.8, "gap": -0.5}}
    }
}
```
