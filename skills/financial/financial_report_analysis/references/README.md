# References

本目录由 v1 的「财报指标详解.md」拆分重写而来，作为 Renaissance 版 `financial-report-analysis` v2 的方法论索引。旧文件中的指标、阈值、数据溯源和风险规则已拆分到以下文件，便于按需加载。

| 文件 | 用途 |
|---|---|
| `framework.md` | 七步链指标、公式、阈值、红色预警和附加工具 |
| `industry_adaptations.md` | 消费、制造、科技、平台、重资产、地产建筑、医药等行业适配 |
| `data_rules.md` | 数据溯源、A/B/C 数据分层、字段口径和反幻觉规则 |
| `confidence_rules.md` | `confidence` 反推规则，响应“不允许凭直觉填写”约束 |
| `lessons_learned.md` | PDF 抽取、租赁准则、预收/预付混淆、二手数据等已知陷阱 |

使用顺序：先读 `framework.md`，再按行业读取 `industry_adaptations.md`，最后用 `data_rules.md` 和 `confidence_rules.md` 校验输出。
