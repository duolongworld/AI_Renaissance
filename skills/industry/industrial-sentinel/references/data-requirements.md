# Industrial Sentinel V4.5 — 必填数据字段清单

> **设计原则**：本框架是方法论，不是黑箱工具。你需要用你自己的AI/Agent搜索数据，填入JSON模板，框架根据填入的数据自动推理出产业链景气度、拐点状态和个股类型。
>
> **数据来源要求**：每个数字必须标注来源（财报/研报/新闻/机构）和时间戳。禁止填入没有出处的数字。

---

## 一、数据字段总览

| 字段组 | 必填级别 | 作用 |
|--------|---------|------|
| **基础信息** | 必填 | 股票身份、行业归属 |
| **System A 五态信号** | **核心必填** | 判定产业链拐点（五态模型） |
| **System A 生命周期指标** | **核心必填** | 判定产业链生命周期阶段 |
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

## 三、System A — 五态拐点信号（核心必填，至少填3项）

五态拐点模型需要以下信号来判断产业链处于哪个阶段：

| 信号字段 | 数据类型 | 判定作用 | 数据来源建议 |
|---------|---------|---------|-------------|
| `real_signals.revenue_growth` | float (%) | 营收增速 >20% → 景气上行 | 最新季报/年报 |
| `real_signals.gross_margin` | float (%) | 毛利率修复 → 供需改善 | 最新季报/年报 |
| `real_signals.order_backlog` | str/float | 订单backlog或pipeline | 业绩会/公告 |
| `real_signals.capacity_utilization` | str | 产能利用率/扩产状态 | 调研/新闻 |
| `real_signals.price_yoy` | str | 产品价格同比变化 | 行业新闻/研报 |
| `real_signals.inventory_days` | float | 库存天数下降 → 需求好转 | 财报 |
| `real_signals.capex_plan` | str | 扩产计划/资本开支 | 财报/新闻 |
| `real_signals.policy_count` | int | 政策数量 | 部委文件/新闻 |
| `real_signals.net_loss_yoy_improvement` | float | 亏损收窄幅度 | 财报 |

**每个信号必须附带来源：**
```json
{
  "revenue_growth": 45.2,
  "revenue_growth_source": "某光芯片公司2026Q1财报：营收同比+45.2%（来源：公司公告 2026-04-28）"
}
```

---

## 四、System A — 生命周期判定指标（核心必填，至少填3项）

```json
{
  "lifecycle_indicators": [
    {"label": "营收增速", "value": "45%", "trend": "↑", "source": "2026Q1财报"},
    {"label": "毛利率修复", "value": "从18%→25%", "trend": "↑", "source": "2026Q1财报"},
    {"label": "订单backlog", "value": "$100M+", "trend": "↑", "source": "CEO业绩会 2026-04-30"},
    {"label": "产能扩张", "value": "扩产50%", "trend": "↑", "source": "公司公告 2026-03"},
    {"label": "行业周期", "value": "AI算力驱动上行", "trend": "↑", "source": "LightCounting 2026-03"}
  ]
}
```

**推理规则**（框架自动执行）：
- 导入期：营收增速>50% + 毛利率低/亏损 + 产能爬坡中
- 成长期：营收增速20-50% + 毛利率修复 + 产能扩张
- 成熟期：营收增速<20% + 毛利率稳定 + 产能利用率高位
- 衰退期：营收下滑 + 毛利率压缩 + 产能收缩

---

## 五、行业级数据表格（至少5项，推荐8项）

展示产业链景气度的行业级数据，每项必须有来源和时间：

| 推荐指标 | 说明 | 来源 |
|---------|------|------|
| Q1 2026 Revenue | 公司最新季度营收 | 财报 |
| Gross Margin | 毛利率及同比变化 | 财报 |
| Order Backlog | 订单储备 | 业绩会/公告 |
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

## 九、使用流程

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
  "real_signals": {
    "revenue_growth": 45.2,
    "revenue_growth_source": "2026Q1财报"
  },
  "industry_data": [...],
  "lifecycle_indicators": [...]
}

# 保存到 data/688XXX.SH_real_data.json
# 然后调用本框架的 pipeline 自动生成报告
```

框架不绑定任何特定数据获取工具。你可以用：
- web_search / kimi_search / serpapi 等通用搜索工具
- akshare / tushare
- 手动搜索研报/财报
- 公司公告直接提取

只要最终生成符合本清单格式的JSON，框架就能自动分析。
