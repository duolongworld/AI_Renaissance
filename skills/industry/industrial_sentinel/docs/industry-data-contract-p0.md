# Industrial Sentinel 数据 Contract v0.2

本文档定义行业组项目级数据 seam。provider、离线 fixture 与人工 JSON
都必须先转换为 `IndustryDataPacket`，再交给 Skill runtime。

## 1. 标准数据包

```json
{
  "schema_version": "industry-data/0.2",
  "target": {
    "stock_code": "300782.SZ",
    "stock_name": "卓胜微",
    "industry": "半导体",
    "sub_sector": "射频前端 / 模拟芯片",
    "preset": "ai-chip",
    "input_type": "stock_code"
  },
  "industry_signals": {},
  "peer_basket_signals": {},
  "peer_basket_meta": {},
  "company_signals": {},
  "product_industry_map": [],
  "valuation_context": {},
  "market_context": {},
  "evidence": [],
  "needs_data": [],
  "as_of_date": "2026-07-10",
  "fetched_at": "2026-07-10T09:30:00",
  "data_hash": "sha256...",
  "provider_status": {},
  "source_mode": "live | cache | mixed_cache | stale_cache | offline_harness",
  "routing": {},
  "methodology_profile": {},
  "collection_plan": {}
}
```

`market_context` 只容纳板块涨跌、资金、换手率和市场热度，不能进入 System A。
`company_signals` 只供 System B 使用，禁止回退成行业证据。

## 1.1 Profile 驱动采集计划

Skill 在分析前根据归一化目标与 preset 构建 `industry-collection-plan/0.1`：

- `routing` 记录目标同行组、实际 evidence scope、固定候选和范围阶梯；
- preset 容器为每个同行组分别配置 Methodology Profile；路由后只输出所选同行组的
  版本、参考序列、指标角色、窗口、阈值、转换规则与方法来源；
- `collection_plan.required_tasks` 是目标 readiness 的最小决策集；
- `collection_plan.optional_tasks` 只提高解释力和交叉验证能力；
- `collection_plan.ceiling` 固定允许的任务、同行与范围上限；
- `collection_plan.report_periods` 按 reference date 和法定披露截止日固定已可获得报告期；
- `collection_plan.preflight` 记录路由、Profile、候选数量、字段/来源定义、报告期以及
  provider/cache 可用性；数据可用性检查不改变配置本身是否有效。

采集任务只有事实字段、来源要求、观察期间和候选公司，禁止包含方向、置信度、
readiness 或三类行业结论。显式传入的 Profile 不合格时 fail closed 为
`framework_only`，并在 `needs_data` 中说明原因，不静默回退到其他 Profile。

## 2. Readiness

| readiness | 含义 | System A | 方向/权重 |
|---|---|---|---|
| `framework_only` | 只有标的与 preset | 不可用 | neutral / 0 |
| `system_b_only` | 公司财务合格但无行业证据 | 不可用 | neutral / 0 |
| `peer_proxy_ready` | 受控同业代理通过准入 | 可用 | confidence≤0.65，weight≤0.5 |
| `industry_ready` | 直接行业证据通过准入 | 可用 | confidence≤0.85 |
| `conflicted` | 直接行业与同业代理方向冲突 | 不可用 | neutral / 0 |

## 2.1 三类行业结论与推理轨迹

packet 模式下，所选同行组 Methodology Profile 是方向与行业阶段的唯一权威。
Skill 分别输出：

- `structural_lifecycle`：导入、成长、成熟、衰退或未判定；
- `cyclical_phase`：复苏、扩张、过热、收缩或未判定；
- `inflection_state`：拐点前、早期、已确认、后期、下行确认或未判定。

短期 peer proxy 只能支持周期景气和拐点，不能单独确定结构性生命周期。
`reasoning_trace.nodes` 为每条 evidence 分别记录来源等级、来源类型、数据日期、
报告期、raw current/previous、Profile comparison 的实际计算、准入状态、跨期状态、
contribution 与具体拒绝原因。同一字段中的有效和过期 evidence 不得合并。

拐点确认至少要求跨期晴雨表与独立中轴同时改善；证据冲突时三类结论均未判定且
Signal 为 neutral。若 contract 准入的数据无法通过所选同行组更严格的 Profile
来源、freshness、样本、覆盖率或一致率要求，最终 readiness 必须降级，不得只在
trace 中标拒绝而继续输出方向。

Profile 必须按 `peer_proxy_ready` 和 `industry_ready` 分别声明
`minimum_decision_sets`。只有配置中的必需指标与角色都存在合格跨期 evidence，
System A 才可用；任一必需晴雨表或中轴缺失时降级。同行节点逐公司保留 raw
比较和 `member_direction`，但状态投票统一采用通过覆盖率、一致率门槛后的
`peer_basket_meta.direction_by_field` 聚合方向，避免同一聚合指标同时投多种方向。

## 3. 直接行业证据

`industry_ready` 至少需要：

- 3 个有意义的行业字段；
- 覆盖至少 2 个独立维度；
- 每个字段都有同 `field_path` 的 L1/L2/L3 evidence；
- evidence 带来源日期，距离参考日不超过 90 天。

数据不足时返回“行业拐点/生命周期数据不足”，不得回退为“拐点前”。

## 4. 受控同业代理

`peer_basket_meta` 必须包含：

```json
{
  "members": [{"stock_code": "PEER001.SZ", "stock_name": "同业一"}],
  "sample_size": 3,
  "report_period": "2026-06-30",
  "previous_report_period": "2026-03-31",
  "previous_report_period_by_field": {
    "revenue_growth_median": "2025-06-30",
    "contract_liability_growth_qoq_median": "2026-03-31"
  },
  "aggregation_method": "median",
  "coverage_ratio": 1.0,
  "coverage_ratio_by_field": {},
  "agreement_ratio_by_field": {},
  "direction_by_field": {}
}
```

准入要求：

- 至少 3 家同细分行业公司，并排除目标公司；
- 当前报告期一致；流量表字段使用去年同期，余额表字段可使用上一资产负债表期，并在
  `previous_report_period_by_field` 中显式声明；同一字段的公司 evidence 期间必须一致；
- 每个候选代理字段的覆盖率和方向一致率均不低于 2/3；可选字段不足不得污染
  其他已达标字段；
- 每个代理字段至少有 3 家成员的 L1 财报 evidence；
- 至少两个独立维度同向，且至少含一个领先代理：合同负债、库存变化、
  CapEx 或在建工程变化；
- 同一维度内的多个字段先聚合成一票；合同负债兼容值、同比和环比不能重复计为
  多个独立改善维度；
- 营收和毛利率静态水平只能验证景气，不能单独确认拐点。
- 合同负债必须同时保留 provider 同比值（如有）与相邻报告期环比派生值；
  毛利率、库存天数绝对水平只作为 context，不计入“两个改善维度”。

## 5. Evidence

最终 `Signal.meta.evidence` 必须保留实际证据，而不只是数量。最小字段：

```json
{
  "field_path": "peer_basket_signals.contract_liability_growth_median",
  "scope": "peer_basket",
  "source_level": "L1",
  "source_type": "financial_report",
  "source_title": "同业财报聚合",
  "provider": "eastmoney",
  "member_stock_code": "PEER001.SZ",
  "report_period": "2026-06-30",
  "previous_report_period": "2026-03-31",
  "raw_fields": ["CONTRACT_LIAB.current", "CONTRACT_LIAB.previous"],
  "raw_values": {"CONTRACT_LIAB.current": 300, "CONTRACT_LIAB.previous": 200},
  "derivation_method": "财务报表字段或相邻报告期派生",
  "aggregation_method": "median",
  "as_of_date": "2026-07-10",
  "fetched_at": "2026-07-10T09:30:00",
  "fact_type": "contract_liability_growth_median",
  "company_code": "PEER001.SZ",
  "fact_key": "sha256-stable-identity",
  "content_hash": "sha256-content",
  "evidence_id": "ev_...",
  "revision": 1,
  "supersedes_evidence_id": null
}
```

相同来源、公司、事实类型、报告期与 URL 形成稳定 `fact_key`。内容未变化时复用原
`evidence_id`；来源修订时追加新 record、递增 `revision` 并通过
`supersedes_evidence_id` 指向旧版本，历史记录不得原地覆盖。

## 5.1 Last-Known-Good

只有 schema、target、scope 类型和逐字段 evidence 校验通过的 live packet 才能原子
更新 LKG。缓存 envelope 保存 `schema_version`、`profile_version`、`fetched_at`、
`as_of_date`、`report_period`、`provider_status`、`data_hash` 与完整 packet。

以下情况不得覆盖 LKG：空响应、schema 错误、Signal 字段缺少 evidence，以及已有
scope 含至少四个字段时字段数跌至一半以下且至少缺失两个字段。被拒绝的 live 原始
evidence 仍追加进入历史，但当次 packet 对应 scope 必须从 LKG 回填并标为
`cache`、`mixed_cache` 或 `stale_cache`。

`profile_version` 必须是路由后所选同行组 Methodology Profile 的真实版本，不能用
preset 名称代替。数据源先执行确定性的 CollectionPlan，以同一计划取得同行候选并
把实际 Profile 版本绑定到 packet；未绑定 Profile 的 packet 不得发布为 LKG。

纯缓存与混合回填必须输出 `cache_origin`，记录来源 LKG 的 hash、获取时间与 Profile
版本；`scope_provenance` 逐 scope 区分 live/cache/stale。它们原样进入 Signal meta，
使当次数据包可以反查到实际 LKG，而不是用新运行时间伪装旧数据。

Evidence history 的读—改—原子替换全程使用进程级文件锁串行化。已有 history 无法
解析或 schema 异常时 fail closed，不把损坏文件当作空历史覆盖。

## 6. 可执行 Harness

```bash
python skills/industry/industrial_sentinel/scripts/run_project_harness.py \
  --stock 300782 --fixture all --output reports/industry_harness
```

真实链路：

```text
FixtureDataAdapter
→ IndustryAgent
→ analyze_industry
→ Signal
→ AgentScope
→ OrchestratorAgent / ArbitrationEngine
→ JSON + HTML
```

fixture 数据必须标记 `offline_harness`，不能伪装成 live 数据。
Harness JSON 分别保存 `packet`、真实 `skill_result`、最终 `industry_signal`、
AgentScope trace 与仲裁结果；HTML 显式展示归一化输入、中文名、preset、数据域和消费状态。

完整 7 Agent live smoke 是非阻塞第二层检查。可将其 JSON 摘要附加到同一份 HTML：

```bash
python skills/industry/industrial_sentinel/scripts/run_project_harness.py \
  --stock 300782 --fixture all --output reports/industry_harness \
  --live-smoke-summary reports/industry_harness/live_smoke.json
```

LKG 回填按 scope/field 标记时效：行业与市场背景 90 天、同业及季度财报字段
180 天、`profit_stability` 等年度字段 450 天；混合 company packet 在
`provider_status.company_financials_by_field` 中保留逐字段 `cache/stale` 状态。
