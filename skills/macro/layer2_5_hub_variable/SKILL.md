---
name: layer2_5_hub_variable
description: 显式建模汇率与大宗商品的传导作用，连接中美宏观，定位全球宏观三角。
owner_group: 专家4组（宏观方向）
domain: macro
status: draft
---

# Layer 2.5: 枢纽变量分析——汇率与大宗商品传导

## 执行方式

- [ ] 数值计算
- [x] 智能分析（需要LLM解读汇率驱动因素、大宗商品信号含义）
- [ ] 混合模式

**说明**：本层需要 LLM 进行智能判断：
1. 解读USD/CNH方向的多重驱动因素
2. 判断大宗商品比值异常的宏观含义
3. 确认全球宏观三角定位

## 适用范围

分析汇率与大宗商品的枢纽传导作用，为 Layer 4 预期差信号引擎提供输入。

## 输入数据规范

### 必填数据

| 数据项 | 来源 | 字段名 | 说明 |
|--------|------|--------|------|
| USD/CNH即期汇率 | HKMA | usd_cnh | 日频 |
| 中美10Y利差 | 自算 | cn_us_10y_spread | 日频 |
| 中国贸易顺差 | 海关 | trade_surplus | 月频 |
| CNH-CNY价差 | HKMA | cnh_cny_spread | 日频 |
| 外储月度变化 | SAFE | forex_reserve_change | 月频 |
| LME铜价 | Bloomberg | copper_price | 日频 |
| COMEX黄金价格 | Bloomberg | gold_price | 日频 |
| DCE铁矿石价格 | DCE | iron_ore_price | 日频 |
| CBOT大豆/玉米价格 | CBOT | soybean_corn_ratio | 日频 |

### 可选数据

| 数据项 | 来源 | 用途 |
|--------|------|------|
| USD/CNH 1Y远期点 | HKMA | 人民币贬值预期 |
| 人民币期权波动率微笑 | Bloomberg | 尾部风险 |
| WTI原油价格 | Bloomberg | 通胀预期 |
| 央行中间价偏离度 | PBOC | 政策意图 |

## 分析步骤

### 子模块A: USD/CNH汇率分析

驱动力权重：
- 利差驱动 0.30：中美10Y利差
- 经常账户 0.20：中国贸易顺差
- 风险偏好 0.20：VIX、CNH波动率
- 政策意图 0.30：中间价、外储变化

方向判定：
- 得分 > +1.0σ：升值趋势确认
- 得分 < -1.0σ：贬值趋势确认
- 得分在±0.5σ之间：震荡/无方向

### 子模块B: 大宗商品比值信号

| # | 比值 | 计算方式 | 宏观含义 |
|---|------|----------|----------|
| 1 | 铜金比 | LME铜/现货黄金 | 铜金比上升=全球增长乐观 |
| 2 | 油金比 | 布伦特/现货黄金 | 油金比上升=通胀压力上行 |
| 3 | 铁矿石/铜比 | DCE铁矿石/LME铜 | 比值上升=中国地产/基建相对更强 |
| 4 | 大豆/玉米比 | CBOT大豆/CBOT玉米 | 比值异常=供给冲击或天气风险 |
| 5 | 黄金vs实际利率 | 现货黄金/10Y TIPS收益率 | 背离=避险/去美元化 |
| 6 | 南华vs全球PMI | 南华工业品指数同比/全球PMI | 背离=中国独立定价逻辑 |

### 子模块C: 全球宏观三角

| 宏观环境 | 美元 | 大宗 | 美债收益率 | 最优资产 |
|----------|------|------|------------|----------|
| 全球紧缩 | 强 | 弱 | 高 | 中债长端、防御股 |
| 全球宽松 | 弱 | 强 | 低 | 周期股、大宗股、港股 |
| 滞胀型 | 强 | 强 | 高 | 黄金、短债 |
| 通缩型 | 弱 | 弱 | 低 | 利率债、高股息 |

## 标准输出

```json
{
    "layer_name": "layer2_5",
    "timestamp": "2026-05-15T00:00:00",
    "analysis_result": {
        "cnh_direction": {
            "score": 0.8,
            "direction": "偏升值",
            "components": {
                "rate_score": 0.3,
                "ca_score": -0.2,
                "risk_score": 0.1,
                "policy_score": 0.6
            }
        },
        "commodity_signals": [
            {"id": 1, "name": "铜金比", "z_score": 1.2, "macro_meaning": "全球工业需求偏强"}
        ],
        "macro_triangle": {
            "triangle": "global_easing",
            "usd_strength": -1,
            "commodity_score": 1,
            "us_rate_level": -1,
            "best_assets": ["周期股", "大宗股", "港股"]
        },
        "channel_alerts": [
            {"channel_id": 2, "status": "active", "direction": "positive"}
        ]
    },
    "direction": "bullish",
    "confidence": 0.7,
    "reasoning": "全球宽松三角确认，美元弱势+大宗强势"
}
```

## 待确认事项

1. **汇率方向得分中间区间处理规则**：±0.5σ 到 ±1.0σ 之间的处理方式
2. **大宗商品比值的历史分位计算方法**
