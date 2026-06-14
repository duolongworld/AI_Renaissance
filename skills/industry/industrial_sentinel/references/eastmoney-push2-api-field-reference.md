# 东方财富字段映射参考

> 本文只记录字段含义，真实 provider 调用、解析和缓存必须放在项目 `data_sources/`。该数据只能进入 `company_signals` 或同业篮子汇总，不能由单家公司直接驱动 System A。

## 已验证字段

| 字段 | 含义 | 示例值 | 用途 |
|------|------|--------|------|
| `f41` | 营收同比增速 (%) | 52.72 | `company_signals.revenue_growth` 或同业汇总后的 `peer_basket_signals.revenue_growth_median` |
| `f57` | 毛利率 (%) | 55.85 | `company_signals.gross_margin` 或同业汇总后的 `peer_basket_signals.gross_margin_median` |
| `f9` | PE (TTM) | 85.39 | System B 估值参考 |
| `f45` | 净利润同比 (%) | 注意基期效应可能导致极端值 | 参考，不直接填入 |
| `f40` | 营业收入 (万元) | 季度或 TTM 口径 | 辅助验证 |
| `f20` | 总市值 | — | System B 规模参考 |

## 注意事项

- 深交所代码用 `0.` 前缀，上交所用 `1.`
- `f45` 净利润同比在扭亏场景下会出现极端值（数十万%），建议填入 `system_b_input` 但不要直接用于拐点判定
- 数据实时性为交易日级别，非季报精准数据，但方向可靠
- 所有通过项目数据层获取的数据应标注来源为 "东方财富行情数据"
