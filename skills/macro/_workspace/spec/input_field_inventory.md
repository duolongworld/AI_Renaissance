# Macro 流程完整输入参数清单

> **生成日期**: 2026-05-31 (修正: 补全管道断点字段 + 去重 euro_pmi + 移除 4 个框架内部字段)
> **流程范围**: `data_sources/macro_data.py` → `convert_to_agent_format()` → `MacroAgent._run_layer*()`
> **总计唯一字段**: **124** (已移除 4 个框架内部合成指标: signal_crowding_score, self_fulfilling_index, cross_framework_consensus, geopolitical_score)
> **Spec 覆盖**: 必填 ≈ 80项, 可选 ≈ 43项, 代码实现 124 项字段输出

---

## 0. Spec vs Code 对照概要

| 维度 | 数量 | 说明 |
|---|---|---|
| Spec 必填输入 (Section 2) | **80** | 核心原始输入 |
| Spec 可选输入 (Section 3) | **43** | 增强/特殊场景辅助 |
| Spec 去重合计 | **~118** | 去除跨章节重复的同一指标 |
| 代码实际输出 (blocks) | **124** | 含 computed/derived 内部字段 (已移除 4 个框架内部合成字段) |
| 代码覆盖必填项 | **~70/80 (88%)** | 10 个必填项暂无数据源 |
| 代码覆盖可选项 | **~15/43 (35%)** | 高频补充/另类/期权微笑等未接入 |
| 管道修复 (本次) | **+16 字段** | 原有采集但未映射到 Agent |

---

## 1. 分类汇总

| 类别 | 代码 | 数量 | 说明 |
|---|---|---|---|
| 真实数据源 (FRED + akshare) | `real` | **62** | API 成功时返回真实值 |
| 计算衍生 (computed) | `computed` | **10** | 从已有数据二次计算 |
| 新接入但无 fallback (管道修复) | `🔴` | **12** | 数据已采集但映射后仍无 fallback → 0.0 |
| 原有无 fallback | `🔴` | **14** | 原有 26 个中减去 12 个新增有数据源 |
| 有显式默认值 (_v default) | `🟡` | **14** | `_v()` 中设了 default |
| 有 fallback (field_defaults) | `🟢` | **20** | `_get_fallback` 中定义 |
| 动态 fallback | `🔵` | **5** | 从已有数据推导 |
| 硬编码常量 | `⚪` | **4** | neutral / None |

> **注**: 新增 12 个管道修复字段虽然已有数据源 (FRED/akshare)，但当数据源同时失效时，它们仍无 fallback 兜底 → 标记为 `🔴`。原有 26 个 `🔴` 中 8 个本次转为有数据源 (housing_starts, existing_home_sales, tips_10y_breakeven, retail_sales_yoy, personal_consumption_yoy, industrial_production_yoy, sp500_index, ccfi_index, property_sales_area_yoy, property_investment_yoy, fixed_asset_investment_yoy, auto_sales_yoy)。

---

## 2. 完整逐字段清单

### 2.1 China 区块 (46 fields, 原 41 + 5 新增)

| # | 字段名 | 数据源 | Fallback 策略 | 默认值 | 严重度 |
|---|---|---|---|---|---|
| 1 | `nbs_manufacturing_pmi` | akshare CN | ❌ 无 fallback → 0.0 | 0.0 | 🔴 |
| 2 | `caixin_manufacturing_pmi` | akshare CN | ❌ 无 fallback → 0.0 | 0.0 | 🔴 |
| 3 | `non_manufacturing_pmi` | akshare CN | ❌ 无 fallback → 0.0 | 0.0 | 🔴 |
| 4 | `industrial_added_value_yoy` | akshare CN | ❌ 无 fallback → 0.0 | 0.0 | 🔴 |
| 5 | `gdp_yoy` | FRED computed | ❌ 无 fallback → 0.0 | 0.0 | 🔴 |
| 6 | `retail_sales_yoy` | akshare CN | ❌ 无 fallback → 0.0 | 0.0 | 🔴 |
| 7 | `export_yoy_usd` | akshare CN | ❌ 无 fallback → 0.0 | 0.0 | 🔴 |
| 8 | `fixed_asset_investment_yoy` | 🆕 akshare CN | ❌ 无 fallback → 0.0 | 0.0 | 🔴 |
| 9 | `auto_sales_yoy` | 🆕 akshare CN | ❌ 无 fallback → 0.0 | 0.0 | 🔴 |
| 10 | `ccfi_index` | 🆕 akshare CN | ❌ 无 fallback → 0.0 | 0.0 | 🔴 |
| 11 | `property_sales_area_yoy` | 🆕 akshare CN | ❌ 无 fallback → 0.0 | 0.0 | 🔴 |
| 12 | `property_investment_yoy` | 🆕 akshare CN | ❌ 无 fallback → 0.0 | 0.0 | 🔴 |
| 13 | `new_order_inventory_spread` | 无数据源 | `_v(..., default=3.5)` | 3.5 | 🟡 |
| 14 | `cpi_yoy` | akshare CN | ❌ 无 fallback → 0.0 | 0.0 | 🔴 |
| 15 | `ppi_yoy` | akshare CN | ❌ 无 fallback → 0.0 | 0.0 | 🔴 |
| 16 | `core_cpi_yoy` | FRED computed | `_v(..., default=0.5)` | 0.5 | 🟡 |
| 17 | `nh_industrial_index_yoy` | 无数据源 | `_v(..., default=0.0)` | 0.0 | 🟡 |
| 18 | `nh_industrial_index` | akshare 商品 | `_v(..., default=3800.0)` | 3800.0 | 🟡 |
| 19 | `tsf_yoy` (social_financing_yoy) | akshare CN | ❌ 无 fallback → 0.0 | 0.0 | 🔴 |
| 20 | `tsf_new_bn` (social_financing_new) | akshare CN | `field_defaults: 3000` | 3000 | 🟢 |
| 21 | `m1_yoy` | akshare CN | ❌ 无 fallback → 0.0 | 0.0 | 🔴 |
| 22 | `m2_yoy` | akshare CN | ❌ 无 fallback → 0.0 | 0.0 | 🔴 |
| 23 | `corp_mid_long_loan_yoy` | akshare CN | `field_defaults: 10.0` | 10.0 | 🟢 |
| 24 | `dr007` | akshare CN | ❌ 无 fallback → 0.0 | 0.0 | 🔴 |
| 25 | `shibor_3m` | akshare CN | ❌ 无 fallback → 0.0 | 0.0 | 🔴 |
| 26 | `margin_balance` | akshare market | `_v(..., default=14800.0)` | 14800.0 | 🟡 |
| 27 | `1y_lpr` | akshare CN | ❌ 无 fallback → 0.0 | 0.0 | 🔴 |
| 28 | `5y_lpr` | akshare CN | ❌ 无 fallback → 0.0 | 0.0 | 🔴 |
| 29 | `mlf_rate` | akshare CN | `field_defaults: 2.5` | 2.5 | 🟢 |
| 30 | `repo_7d_rate` (r007) | akshare CN | `field_defaults: 1.5` | 1.5 | 🟢 |
| 31 | `reserve_cut_bp` (reserve_ratio) | akshare CN | `field_defaults: 0.0` | 0.0 | 🟢 |
| 32 | `cn_10y_yield` | akshare CN | ❌ 无 fallback → 0.0 | 0.0 | 🔴 |
| 33 | `cn_2y_yield` (≈ cn_1y_yield) | akshare CN | ❌ 无 fallback → 0.0 | 0.0 | 🔴 |
| 34 | `csi300_erp` | computed / 动态 | `dynamic: 8.0 - cn_10y_yield` | 动态 | 🟢 |
| 35 | `aa_credit_spread` | computed / 动态 | `dynamic: cn_10y + 0.65` | 动态 | 🟢 |
| 36 | `monetary_policy_direction` | 无 (NLP 未实现) | 硬编码 `"neutral"` | "neutral" | ⚪ |
| 37 | `fiscal_policy_direction` | 无 (NLP 未实现) | 硬编码 `"neutral"` | "neutral" | ⚪ |
| 38 | `real_estate_policy_direction` | 无 (NLP 未实现) | 硬编码 `"neutral"` | "neutral" | ⚪ |
| 39 | `regulation_event` | 无 (NLP 未实现) | 硬编码 `"neutral"` | "neutral" | ⚪ |
| 40 | `special_bond_progress` | akshare CN | `field_defaults: 0.0` | 0.0 | 🟢 |
| 41 | `fiscal_deficit_rate` | akshare CN | `field_defaults: -3.0` | -3.0 | 🟢 |
| 42 | `csi300_index` | akshare market | `_v(..., default=4000.0)` | 4000.0 | 🟡 |
| 43 | `csi300_forward` | 无数据源 | `_v(..., default=4000.0)` | 4000.0 | 🟡 |
| 44 | `csi300_put` | 无数据源 | `_v(..., default=100.0)` | 100.0 | 🟡 |
| 45 | `csi300_call` | 无数据源 | `_v(..., default=100.0)` | 100.0 | 🟡 |
| 46 | `pc_ratio` | 无数据源 | `_v(..., default=1.0)` | 1.0 | 🟡 |

### 2.2 US 区块 (32 fields, 原 23 + 9 新增)

| # | 字段名 | 数据源 | Fallback 策略 | 默认值 | 严重度 |
|---|---|---|---|---|---|
| 47 | `ism_manufacturing_pmi` | akshare US | ❌ 无 fallback → 0.0 | 0.0 | 🔴 |
| 48 | `ism_services_pmi` | akshare US | ❌ 无 fallback → 0.0 | 0.0 | 🔴 |
| 49 | `nonfarm_payrolls` | FRED | `_v(..., default=200000)` | 200000 | 🟡 |
| 50 | `us_unemployment_rate` | FRED | ❌ 无 fallback → 0.0 | 0.0 | 🔴 |
| 51 | `gdp_growth` | FRED YoY | ❌ 无 fallback → 0.0 | 0.0 | 🔴 |
| 52 | `retail_sales_yoy` | 🆕 FRED YoY | ❌ 无 fallback → 0.0 | 0.0 | 🔴 |
| 53 | `personal_consumption_yoy` | 🆕 FRED YoY | ❌ 无 fallback → 0.0 | 0.0 | 🔴 |
| 54 | `industrial_production_yoy` | 🆕 FRED YoY | ❌ 无 fallback → 0.0 | 0.0 | 🔴 |
| 55 | `housing_starts` | 🆕 FRED | ❌ 无 fallback → 0.0 | 0.0 | 🔴 |
| 56 | `existing_home_sales` | 🆕 FRED | ❌ 无 fallback → 0.0 | 0.0 | 🔴 |
| 57 | `initial_jobless_claims_4w_avg` | FRED | ❌ 无 fallback → 0.0 | 0.0 | 🔴 |
| 58 | `core_pce_yoy` | FRED YoY | ❌ 无 fallback → 0.0 | 0.0 | 🔴 |
| 59 | `cpi_yoy` | FRED YoY | ❌ 无 fallback → 0.0 | 0.0 | 🔴 |
| 60 | `core_cpi_yoy` | FRED YoY | ❌ 无 fallback → 0.0 | 0.0 | 🔴 |
| 61 | `eci_wage_qoq` | FRED | ❌ 无 fallback → 0.0 | 0.0 | 🔴 |
| 62 | `breakeven_5y5y` | FRED | ❌ 无 fallback → 0.0 | 0.0 | 🔴 |
| 63 | `tips_10y_breakeven` | 🆕 FRED | ❌ 无 fallback → 0.0 | 0.0 | 🔴 |
| 64 | `ffr` | FRED | ❌ 无 fallback → 0.0 | 0.0 | 🔴 |
| 65 | `fed_total_assets` | FRED | `_v(..., default=7.0)` | 7.0 (万亿) | 🟡 |
| 66 | `sofr` | FRED | ❌ 无 fallback → 0.0 | 0.0 | 🔴 |
| 67 | `effr` | FRED | ❌ 无 fallback → 0.0 | 0.0 | 🔴 |
| 68 | `m2_yoy` | FRED YoY | ❌ 无 fallback → 0.0 | 0.0 | 🔴 |
| 69 | `credit_pulse` | 🆕 无数据源 (BIS) | `field_defaults: 0.0` | 0.0 | 🟢 |
| 70 | `overseas_flow_us` | 🆕 无数据源 (TIC) | `field_defaults: 0.0` | 0.0 | 🟢 |
| 71 | `us_10y_yield` | FRED | ❌ 无 fallback → 0.0 | 0.0 | 🔴 |
| 72 | `us_2y_yield` | FRED | ❌ 无 fallback → 0.0 | 0.0 | 🔴 |
| 73 | `sp500_index` | 🆕 akshare market | ❌ 无 fallback → 0.0 | 0.0 | 🔴 |
| 74 | `sp500_erp` | computed / 动态 | `dynamic: 5.0 - us_10y_yield` | 动态 | 🟢 |
| 75 | `us_hy_spread` | FRED | ❌ 无 fallback → 0.0 | 0.0 | 🔴 |
| 76 | `us_ig_spread` | FRED | ❌ 无 fallback → 0.0 | 0.0 | 🔴 |
| 77 | `dxy_index` | akshare/FRED | ❌ 无 fallback → 0.0 | 0.0 | 🔴 |
| 78 | `cftc_dollar_net` | akshare US | `field_defaults: 0.0` | 0.0 | 🟢 |

### 2.3 Cross Border 区块 (15 fields, 原 16 - 1 框架内部)

| # | 字段名 | 数据源 | Fallback 策略 | 默认值 | 严重度 |
|---|---|---|---|---|---|
| 79 | `cn_us_10y_spread` | computed | Phase 6 计算 | 动态 | ✅ |
| 80 | `usd_cnh` | akshare market | `field_defaults: 7.2` | 7.2 | 🟢 |
| 81 | `usd_cnh_1y_forward` | 🆕 无 API (HKMA) | `field_defaults: 0.0` | 0.0 | 🟢 |
| 82 | `vix` | akshare market | ❌ 无 fallback → 0.0 | 0.0 | 🔴 |
| 83 | `euro_pmi` | akshare US | `fallback: 50.0` | 50.0 | 🟢 |
| 84 | `rmb_reer` | 🆕 无数据源 (BIS) | `field_defaults: 100.0` | 100.0 | 🟢 |
| 85 | `copper_price` | akshare 商品 | `_v(..., default=9500.0)` | 9500.0 | 🟡 |
| 86 | `gold_price` | akshare 商品 | `_v(..., default=2400.0)` | 2400.0 | 🟡 |
| 87 | `brent_oil` | akshare 商品 | `_v(..., default=85.0)` | 85.0 | 🟡 |
| 88 | `trade_surplus` | akshare CN | `field_defaults: 50.0` | 50.0 (亿美元) | 🟢 |
| 89 | `forex_reserve_change` | akshare CN | `field_defaults: 3.2` | 3.2 (万亿美元) | 🟢 |
| 90 | `pboc_mid_deviation` | 无数据源 | `_v(..., default=1.5)` | 1.5 | 🟡 |
| 91 | `cnh_cny_spread` | 无数据源 | `_v(..., default=0.05)` | 0.05 | 🟡 |
| 92 | `north_flow` | akshare market | `_v(..., default=100.0)` | 100.0 | 🟡 |
| 93 | `global_pmi` | computed | Phase 6 代理合成 | 动态 | ✅ |

### 2.4 Commodities 区块 (11 fields, 不变)

| # | 字段名 | 数据源 | Fallback 策略 | 默认值 | 严重度 |
|---|---|---|---|---|---|
| 95 | `copper_gold_ratio` | computed | `_v(..., default=0.12)` | 0.12 | 🟡 |
| 96 | `oil_gold_ratio` | 无数据源 | `_v(..., default=0.035)` | 0.035 | 🟡 |
| 97 | `copper_price` | akshare 商品 | `_v(..., default=9500.0)` | 9500.0 | 🟡 |
| 98 | `gold_price` | akshare 商品 | `_v(..., default=2400.0)` | 2400.0 | 🟡 |
| 99 | `brent_oil` | akshare 商品 | `_v(..., default=85.0)` | 85.0 | 🟡 |
| 100 | `iron_ore_price` | akshare 商品 | `_v(..., default=830.0)` | 830.0 | 🟡 |
| 101 | `iron_ore_usd` | 无数据源 | `_v(..., default=106.0)` | 106.0 | 🟡 |
| 102 | `nh_industrial_index` | akshare 商品 | `_v(..., default=3800.0)` | 3800.0 | 🟡 |
| 103 | `soybean_corn_ratio` | 无数据源 | `_v(..., default=2.4)` | 2.4 | 🟡 |
| 104 | `gold_vs_real_rate` | 无数据源 | `_v(..., default=0.0)` | 0.0 | 🟡 |
| 105 | `nh_global_pmi_ratio` | 无数据源 | `_v(..., default=76.0)` | 76.0 | 🟡 |

### 2.5 Market Pricing 区块 (11 fields, 不变)

| # | 字段名 | 数据源 | Fallback 策略 | 默认值 | 严重度 |
|---|---|---|---|---|---|
| 106 | `csi300_index` | akshare market | `_v(..., default=4000.0)` | 4000.0 | 🟡 |
| 107 | `csi300_forward` | 无数据源 | `_v(..., default=4000.0)` | 4000.0 | 🟡 |
| 108 | `csi300_put` | 无数据源 | `_v(..., default=100.0)` | 100.0 | 🟡 |
| 109 | `csi300_call` | 无数据源 | `_v(..., default=100.0)` | 100.0 | 🟡 |
| 110 | `pc_ratio` | 无数据源 | `_v(..., default=1.0)` | 1.0 | 🟡 |
| 111 | `gov_bond_10y_holding_change` | 无数据源 | `_v(..., default=0.0)` | 0.0 | 🟡 |
| 112 | `hshare_ah_spread` | 无数据源 | `_v(..., default=140.0)` | 140.0 | 🟡 |
| 113 | `copper_near` | 无数据源 | `_v(..., default=9500.0)` | 9500.0 | 🟡 |
| 114 | `copper_far` | 无数据源 | `_v(..., default=9400.0)` | 9400.0 | 🟡 |
| 115 | `oil_near` | 无数据源 | `_v(..., default=85.0)` | 85.0 | 🟡 |
| 116 | `oil_far` | 无数据源 | `_v(..., default=83.0)` | 83.0 | 🟡 |

### 2.6 Expected Diff 区块 (3 fields, 不变)

| # | 字段名 | 数据源 | Fallback 策略 | 默认值 | 严重度 |
|---|---|---|---|---|---|
| 117 | `china_surprise_index` | 无 API (Bloomberg) | `field_defaults: 0.0` | 0.0 | 🟢 |
| 118 | `us_surprise_index` | FRED (可能下架) | `field_defaults: 0.0` | 0.0 | 🟢 |
| 119 | `ff_implied_rate` | 无 API (Bloomberg) | `dynamic: ffr or 5.33` | 5.33 | 🔵 |

### 2.7 Reflexivity 区块 (6 fields, 移除 3 个框架内部字段)

| # | 字段名 | 数据源 | Fallback 策略 | 默认值 | 严重度 |
|---|---|---|---|---|---|
| 120 | `position_concentration_z` | akshare US | `field_defaults: 0.0` | 0.0 | 🟢 |
| 121 | `cftc_net_position_pct` | akshare US | `field_defaults: 0.0` | 0.0 | 🟢 |
| 122 | `etf_flow_cny_bn` | 无 API | `dynamic: north_flow` ⚠️ | north_flow | 🔵 |
| 123 | `northbound_flow_cny_bn` | akshare market | `_v(..., default=100.0)` | 100.0 | 🟡 |
| 124 | `sell_side_bearish_pct` | NLP (未实现) | `field_defaults: 30.0` | 30.0 | 🟢 |
| 125 | `buy_side_bearish_pct` | NLP (未实现) | `field_defaults: 20.0` | 20.0 | 🟢 |

> **已移除的框架内部字段** (3 个): `signal_crowding_score`, `self_fulfilling_index`, `cross_framework_consensus` — 均为 §4.5.2 反身性压力计的合成指标，由框架内部从已有原始输入计算，不属外部数据需求。详见框架文档 §4.5。

---

## 3. 本次修复：管道断点字段 (新增 16 个)

这些字段在 `fetch_macro_data()` 中已完成数据采集 + fallback，但 `convert_to_agent_format()` 此前未映射到任何 block，导致 Agent 完全不可见。

| # | 字段名 | 数据源 | 归属 Block | 说明 |
|---|---|---|---|---|
| 1 | `fixed_asset_investment_yoy` | akshare CN | China | `_fetch_akshare_cn()` 已采集 |
| 2 | `auto_sales_yoy` | akshare CN | China | `_fetch_akshare_cn()` 已采集 |
| 3 | `ccfi_index` | akshare CN | China | `_fetch_akshare_cn()` 已采集 |
| 4 | `property_sales_area_yoy` | akshare CN | China | `_fetch_akshare_cn()` 已采集 |
| 5 | `property_investment_yoy` | akshare CN | China | `_fetch_akshare_cn()` 已采集 |
| 6 | `retail_sales_yoy` | FRED YoY | US | `_fetch_fred_data()` YoY 计算 |
| 7 | `personal_consumption_yoy` | FRED YoY | US | `_fetch_fred_data()` YoY 计算 |
| 8 | `industrial_production_yoy` | FRED YoY | US | `_fetch_fred_data()` YoY 计算 |
| 9 | `housing_starts` | FRED | US | `_fetch_fred_data()` 直接采集 |
| 10 | `existing_home_sales` | FRED | US | `_fetch_fred_data()` 直接采集 |
| 11 | `tips_10y_breakeven` | FRED | US | `_fetch_fred_data()` 直接采集 |
| 12 | `sp500_index` | akshare Market | US | `_fetch_market_data()` 已采集 |
| 13 | `credit_pulse` | Fallback (BIS) | US | Phase 5 fallback 填充 |
| 14 | `overseas_flow_us` | Fallback (TIC) | US | Phase 5 fallback 填充 |
| 15 | `rmb_reer` | Fallback (BIS) | Cross Border | Phase 5 fallback 填充 |
| 16 | `usd_cnh_1y_forward` | Fallback (HKMA) | Cross Border | Phase 5 fallback 填充 |

### 同时修复的 Bug

- **`euro_pmi` 重复定义**: `cross_border` block 中同名字段出现两次 (原行 1704, 1714) → 删除重复行
- **4 个 fallback 值补充**: `overseas_flow_us`, `rmb_reer`, `usd_cnh_1y_forward` 添加至 `_FALLBACK_VALUES`

---

## 4. 真实数据源覆盖统计

| 数据源 | 字段数 | 状态 |
|---|---|---|
| **FRED API** | 24 直接 + 8 YoY = **32** | ✅ `fredapi` 已接入 |
| **akshare CN** | **32** | ✅ 已接入 (含新增 property/auto/ccfi/fixed_asset) |
| **akshare US** | **4** (ISM PMI×2, euro_pmi, CFTC) | ✅ 已接入 |
| **akshare Market** | **8** (sp500, csi300, vix, north_flow, margin, dxy, usd_cnh + sp500_index) | ✅ 已接入 |
| **akshare Commodity** | **8** (铜金银油铁大豆玉米+南华) | ✅ 已接入 |
| **NLP (未实现)** | **6** (政策文本×4, 卖方/买方报告) | ❌ 未实现 |
| **Bloomberg (无API)** | **5** (surprise×2, ff_futures, etf_flow, 远期点) | ❌ 无免费 API |
| **CFFEX/衍生品** | **11** (期货远近月, 期权, 持仓等) | ❌ 未接入 |
| **BIS/TIC** | **3** (credit_pulse, reer, overseas_flow) | ❌ 未接入 |
| **高频补充 (可选)** | **5** (耗煤, 高炉, 地铁, 30城, 货运) | ❌ 未接入 |

---

## 5. Spec 缺口清单 (建议后续补齐)

### 仍未实现的 Spec 必填项 (10 个)

| Spec 定义 | 数据源 | 优先级 |
|---|---|---|
| 标普500前瞻PE (2.5#5) | Bloomberg | 中 |
| 沪深300盈利收益率/PE (2.11#4) | Wind/akshare | 中 |
| 3Y AA中票收益率 (2.11#5) | Wind | 中 |
| 3Y国债收益率 (2.11#6) | CFETS | 中 |
| 城投债-国开债利差 (2.11#7) | Wind | 中 |
| 沪深300前瞻PE (2.11#8) | Wind | 中 |
| 中证周期/防御PE (2.11#9) | Wind | 低 |
| 公开市场操作净投放 (2.9#6) | PBOC | 中 |
| 特别国债 (2.9#9) | MoF | 中 |
| 人民币期权波动率微笑 (3.6#4) | Bloomberg | 低 |

### 仍未实现的可选项 (28 个)

高频补充 (3.1): 发电耗煤、高炉开工率、地铁客流、30城商品房、整车货运 (5)
另类 (3.2): CRB指数、WTI原油、大豆价格、玉米价格 (4)
政策文本 (3.3): 新华社/人民日报、国常会、央行报告、政治局、FOMC声明 (5) — 依赖 NLP
反身性 (3.5): 跨境资本流向BIS季度、策略资金使用规模、卖方/买方报告观点原始数据 (3)
汇率 (3.6): 人民币期权波动率微笑 (1)
期货 (3.7): 沪深300股指期货价格 (1)
衍生品/CFFEX (3.7): 大量未接入 (~9)

---

## 6. 建议优先修复

### 高优先级 🔴
1. **为仍无 fallback 的关键字段添加兜底** — 特别是 `ffr`, `us_10y_yield`, `cn_10y_yield`, `sofr`, `effr`, `dr007`, `shibor_3m`, `vix`, `dxy_index`
2. **`ff_futures_implied_rate`** — 硬编码 `5.33` 已过时，建议更新为 `4.38`
3. **`etf_flow_cny_bn`** — 标注与 `north_flow` 语义差异

### 中优先级 🟡
4. 接入 akshare 可获取的缺失指标: 公开市场操作净投放、特别国债发行进度、CSI300 PE/PB
5. `csi300_forward` / `csi300_put` / `csi300_call` / `pc_ratio` → 尝试接入 CFFEX 期权数据

### 低优先级 ⚪
6. NLP 模块 — 政策文本打分卡、研报观点提取 (Phase 2 规划)
7. BIS/TIC 数据接入 — cross-border capital flows
8. 高频补充数据 — 发电耗煤、高炉开工率、地铁客流、整车货运
