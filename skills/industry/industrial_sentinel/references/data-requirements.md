# Industrial Sentinel — 必填数据字段清单

> **设计原则**：本框架是方法论，不是黑箱工具。项目数据层或人工回填提供标准化 JSON，框架根据输入自动推理产业链景气度、拐点状态和个股类型。
>
> **数据来源要求**：每个数字必须标注来源（财报/研报/新闻/机构）和时间戳。禁止填入没有出处的数字。

---

## 一、数据字段总览

| 字段组 | 必填级别 | 作用 |
|--------|---------|------|
| **基础信息** | 必填 | 股票身份、行业归属 |
| **industry_signals** | **核心必填** | 行业景气度、产业链拐点、生命周期判定 |
| **peer_basket_signals** | 推荐 | 用多家公司财报中位数/一致趋势交叉验证行业判断 |
| **company_signals** | 推荐 | 个股类型判定，不直接参与 System A 行业判断 |
| **行业级数据表格** | **至少5项** | 产业链景气度展示 |
| **System B 个股指标** | 推荐 | 个股类型判定（成长/周期/价值/主题/混合） |
| **产业链位置** | 推荐 | 标的在产业链中的生态位 |

---

## 二、基础信息（必填）

```json
{
  "stock_code": "688XXX.SH",
  "stock_name": "某光芯片公司",
  "industry": "光通信",
  "sub_sector": "CW光源/AWG",
  "chain_position": "中游 — 光器件",
  "preset": "optical-module"
}
```

| 字段 | 说明 | 数据来源 |
|------|------|---------|
| `stock_code` | 股票代码，带交易所后缀 | — |
| `stock_name` | 公司中文名 | — |
| `industry` | 所属行业（如"光通信"） | 申万/证监会行业分类 |
| `sub_sector` | 细分赛道 | 公司年报/研报 |
| `chain_position` | 产业链位置 | 公司年报业务描述 |
| `preset` | 产业链模板名称 | 自动检测或手动指定 |

---

## 三、System A — 行业级信号（核心必填，至少填3项）

System A 判断行业景气度与拐点，只消费行业级信号；单家公司财报不能直接代表行业。

| 信号字段 | 数据类型 | 判定作用 | 数据来源建议 |
|---------|---------|---------|-------------|
| `industry_signals.industry_market_growth` | float (%) | 行业规模/需求增速 >20% → 景气上行 | 行业协会/咨询机构/券商研报 |
| `industry_signals.industry_order_growth` | float/str | 行业订单、排产或 backlog 改善 | 行业调研/产业新闻/龙头公告交叉验证 |
| `industry_signals.industry_capacity_utilization` | float (%) | 产能利用率高位或回升 → 供需改善 | 行业调研/研报 |
| `industry_signals.industry_price_yoy` | float (%) | 产品价格同比上涨 → 供需紧张 | 行业价格跟踪/研报/产业新闻 |
| `industry_signals.industry_inventory_days` | float | 行业库存天数下降 → 去库接近尾声 | 行业跟踪/渠道数据 |
| `industry_signals.industry_capex_plan` | str | 扩产计划/资本开支周期 | 行业公告/设备订单/研报 |
| `industry_signals.industry_policy_count` | int | 政策数量和密度 | 部委文件/地方政策/新闻 |
| `industry_signals.industry_penetration_rate` | float (%) | 生命周期阶段判断 | 行业白皮书/咨询机构 |

**每个信号必须附带来源：**
```json
{
  "industry_market_growth": 28.0,
  "industry_market_growth_source": "某行业报告：光模块市场规模同比+28%（来源：机构报告 2026-04-28）"
}
```

---

## 四、System A — 生命周期判定指标（核心必填，至少填3项）

```json
{
  "lifecycle_indicators": [
    {"label": "行业需求增速", "value": "28%", "trend": "↑", "source": "行业报告"},
    {"label": "行业价格趋势", "value": "同比+6%", "trend": "↑", "source": "价格跟踪"},
    {"label": "行业订单", "value": "排产环比改善", "trend": "↑", "source": "产业新闻"},
    {"label": "产能扩张", "value": "扩产进行中", "trend": "↑", "source": "行业公告"},
    {"label": "行业周期", "value": "AI算力驱动上行", "trend": "↑", "source": "LightCounting 2026-03"}
  ]
}
```

**推理规则**（框架自动执行）：
- 导入期：渗透率低 + 行业需求高速增长 + 产能爬坡中
- 成长期：行业需求较快增长 + 价格/订单改善 + 产能扩张
- 成熟期：行业增速放缓 + 格局稳定 + 产能利用率高位
- 衰退期：行业需求下滑 + 价格承压 + 产能收缩

---

## 五、行业级数据表格（至少5项，推荐8项）

展示产业链景气度的行业级数据，每项必须有来源和时间：

| 推荐指标 | 说明 | 来源 |
|---------|------|------|
| 行业需求增速 | 市场规模增长率 | 行业研报 |
| 关键材料价格 | 原材料价格趋势 | 行业新闻 |
| 产能利用率 | 行业整体产能利用率 | 调研/研报 |
| 供需缺口 | 缺口百分比 | 行业研报 |
| 竞争格局变化 | 市场份额变动 | 研报 |
| 政策催化剂 | 相关政策 | 部委文件 |
| 技术迭代 | 新一代产品渗透率 | 行业分析 |

格式：
```json
{
  "metric": "InP衬底价格",
  "value": "$2500/片",
  "yoy_change": "+200%",
  "source": "行业新闻",
  "source_url": "https://...",
  "source_type": "新闻",
  "date": "2026-02-15",
  "analysis": "价格从$800涨至$2500，AI算力需求驱动"
}
```

---

## 六、System B — 个股类型判定指标（推荐，用于个股分析）

| 字段 | 数据类型 | 判定作用 | 数据来源 |
|------|---------|---------|---------|
| `system_b_input.revenue_growth` | float | >30% → 成长型 | 财报 |
| `system_b_input.rd_ratio` | float | >5% → 技术壁垒 | 财报 |
| `system_b_input.asset_lightness` | str | "轻资产" → 扩张弹性大 | 财报 |
| `system_b_input.profit_stability` | str | "盈利稳定" → 价值型 | 财报 |

## 六补充、同业篮子验证（推荐）

多个公司的财报适合作为行业判断的交叉验证，而不是单家公司替代行业。建议至少覆盖龙头、二线、上游、下游中的 3-5 家。

| 字段 | 数据类型 | 判定作用 | 数据来源 |
|------|---------|---------|---------|
| `peer_basket_signals.revenue_growth_median` | float (%) | 同业收入增速中位数改善 → 行业需求验证 | 财报 |
| `peer_basket_signals.gross_margin_median` | float (%) | 同业毛利率同步修复 → 供需改善验证 | 财报 |
| `peer_basket_signals.inventory_days_median` | float | 同业库存天数下降 → 去库验证 | 财报 |
| `peer_basket_signals.capex_trend` | str | 扩产周期和设备订单验证 | 财报/公告 |

**推理规则**（框架自动执行）：
- 成长型：营收增速>30% + 毛利率>20% + 研发投入>5%
- 周期型：营收波动大 + 毛利率周期性变化 + 产能利用率敏感
- 价值型：营收增速<20% + 盈利稳定 + 分红率高
- 主题型：营收与特定主题强相关 + 估值脱离基本面
- 混合型：跨多个特征

---

## 七、产业链位置（推荐）

```json
{
  "chain_position": "中游 — CW光源",
  "upstream_dependency": "磷化铟衬底（某稀有金属公司/AXT）",
  "downstream_customers": "中际旭创/光迅科技",
  "value_capture": "中游利润池15-20%"
}
```

---

## 八、数据质量检查清单

填入数据后，运行验证脚本：
```bash
python scripts/validate_data.py <stock_code>
```

检查项：
- [ ] 每个数字都有 `source` 和 `date`
- [ ] System A 五态信号至少填了3项
- [ ] 行业数据表格至少5项
- [ ] 没有"待补充"或"数据缺失"的必填字段
- [ ] 时间戳格式正确（YYYY-MM-DD）
- [ ] 来源可追溯到具体文档/公告

---

## 九、CLI / 离线补数流程

```
Step 1: 生成模板
  python scripts/generate_data_template.py 688XXX.SH --industry 光通信

Step 2: 用你的AI/Agent搜索数据（按本清单要求）
  - 搜索财报：Q1 2026营收、毛利率、订单backlog
  - 搜索研报：行业需求增速、供需缺口、竞争格局
  - 搜索新闻：政策、扩产计划、价格趋势

Step 3: 填入JSON模板（每个数字标注来源+时间）

Step 4: 验证数据完整性
  python scripts/validate_data.py 688XXX.SH

Step 5: 运行分析 → 自动输出产业链景气度/拐点/周期/个股类型
  ./run.sh 688XXX.SH
```

---

## 十、数据获取降级策略

如果某些数据搜索不到：

| 缺失数据 | 处理方式 | 标注方式 |
|---------|---------|---------|
| 营收增速 | 用环比替代，或标注"数据缺失" | "Q1数据未披露，用Q4环比" |
| 毛利率 | 用往期数据推算趋势 | "基于Q4毛利率估算" |
| 订单backlog | 用pipeline或客户合作替代 | "无官方backlog，用pipeline估算" |
| 产能利用率 | 用扩产状态推断 | "扩产中→产能爬坡" |
| 行业数据 | 用相近行业数据类比 | "参考光通信行业整体数据" |

**核心原则**：宁可标注"数据缺失"，也不编造数字。框架会对"数据缺失"给出降级分析，而不是错误结论。

---

## 十一、与其他AI/Agent的协作接口

本框架的数据输入是纯JSON格式，任何AI/Agent都可以生成：

```python
# 你的Agent搜索数据后，生成如下JSON结构
{
  "stock_code": "688XXX.SH",
  "industry_signals": {
    "industry_market_growth": 28.0,
    "industry_market_growth_source": "行业报告"
  },
  "peer_basket_signals": {
    "revenue_growth_median": 18.5,
    "gross_margin_median": 24.0
  },
  "company_signals": {...},
  "industry_data": [...],
  "lifecycle_indicators": [...]
}

# 项目 Agent: 通过 data_sources 注入 runtime，返回标准 Signal/meta
# CLI 调试: 可保存到 data/688XXX.SH_real_data.json 后调用 pipeline 生成报告
```

框架不绑定任何特定数据获取工具。项目级 provider 逻辑应放在 `data_sources/`；CLI 调试或离线补数时可以用：
- web_search / kimi_search / serpapi 等通用搜索工具
- 手动搜索研报/财报
- 公司公告直接提取

只要最终生成符合本清单格式的JSON，框架就能自动分析。
