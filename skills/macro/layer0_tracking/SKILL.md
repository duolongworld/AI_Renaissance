---
name: layer0_tracking
description: 并行追踪中美五大维度指标，识别6条传导通道的触发状态，判定中美交互层次。
owner_group: 专家4组（宏观方向）
domain: macro
status: draft
---

# Layer 0: 双经济体追踪与中美交互通道

## 执行方式

- [ ] 数值计算（Agent直接调用 `scripts/analyzer.py`，不需要LLM）
- [x] 智能分析（Agent读取本SKILL.md作为LLM提示词）
- [ ] 混合模式（数值计算 + LLM智能判断）

**说明**：本层需要 LLM 进行智能判断，主要用于：
1. 评估两国的政策宽松/收紧程度（需要解读政策信号）
2. 判断传导通道的触发状态（需要综合多因素判断）
3. 判定中美交互层次（需要定性分析）

## 适用范围

追踪中国与美国两大经济体的宏观状态，识别中美交互通道的触发状态，为后续7层流水线提供输入。

## 输入数据规范

### 必填数据

| 数据项 | 来源 | 字段名 | 说明 |
|--------|------|--------|------|
| 中国统计局制造业PMI | NBS | nbs_manufacturing_pmi | 月频 |
| 中国财新制造业PMI | Caixin | caixin_manufacturing_pmi | 月频 |
| 中国CPI同比 | NBS | cpi_yoy | 月频 |
| 中国PPI同比 | NBS | ppi_yoy | 月频 |
| 1Y LPR | PBOC | 1y_lpr | 月频 |
| 5Y LPR | PBOC | 5y_lpr | 月频 |
| DR007 | CFETS | dr007 | 日频 |
| 社融存量同比 | PBOC | tsf_yoy | 月频 |
| 10Y国债收益率 | CFETS | cn_10y_yield | 日频 |
| A股ERP | Wind | csi300_erp | 日频 |
| 美国ISM制造业PMI | ISM | us_ism_pmi | 月频 |
| 美国非农就业 | BLS | nonfarm_payrolls | 月频 |
| 美国PCE同比 | BEA | pce_yoy | 月频 |
| 美国核心PCE | BEA | core_pce_yoy | 月频 |
| 美联储政策利率 | Fed | ffr | 日频 |
| SOFR | NY Fed | sofr | 日频 |
| 10Y美债收益率 | Bloomberg | us_10y_yield | 日频 |
| 美元指数DXY | Bloomberg | dxy_index | 日频 |
| USD/CNH | HKMA | usd_cnh | 日频 |

### 可选数据

| 数据项 | 来源 | 用途 |
|--------|------|------|
| 中国MLF利率 | PBOC | 政策维度评估 |
| 中国降准幅度 | PBOC | 政策维度评估 |
| 美联储总资产 | Fed | 流动性维度 |
| VIX恐慌指数 | Bloomberg | 风险偏好评估 |
| 中美10Y利差 | 自算 | 传导通道1 |
| 美国IG/HY利差 | ICE BofA | 信用风险 |

## 分析步骤

### Step 1: 抓取数据

从 `data_sources/` 获取中美两国五大维度的最新数据。

### Step 2: 计算z-score

对每个指标计算5年滚动z-score标准化（已由 Layer 0 analyzer 内部处理）。

### Step 3: 计算跨国指标

- 中美10Y利差 = 中国10Y国债收益率 - 美国10Y国债收益率
- 美元指数（DXY）相对强弱
- USD/CNH 汇率水平

### Step 4: 检查6条传导通道

根据各通道的触发条件，判断通道是否触发及传导强度：

| 通道 | 起点变量 | 中介变量 | 终点资产 | 触发条件 |
|------|----------|----------|----------|----------|
| 1 | 中美10Y利差 | 北向资金 | A股核心资产 | 利差变化超过0.5σ |
| 2 | 美元指数DXY | 原油/铜/南华 | A股周期股 | DXY变化超过1.0σ |
| 3 | 美国实际利率 | VIX/美元流动性 | 港股/成长股 | 实际利率变化超过1.0σ |
| 4 | 中国社融脉冲 | 铁矿石/铜价 | 全球周期资产 | 社融脉冲变化超过1.0σ |
| 5 | 全球PMI | 韩国/越南出口 | 中国出口/制造业股 | 全球PMI变化超过0.5σ |
| 6 | 地缘政治事件 | VIX/CNH波动率 | 港股/CNH/半导体 | 地缘事件评分超过阈值 |

### Step 5: 判定交互层次

| 交互层次 | 判定条件 | 含义 |
|----------|----------|------|
| 对称交互 | 多个通道活跃 + 中美增长差值小 | 中美处于同一周期阶段共振 |
| 非对称传导 | 部分通道活跃 + 中美增长差值大 | 一方政策变化单向传导 |
| 反馈循环 | 多个通道活跃且相互关联 | 通道间形成闭环 |

## 判断规则

### 5维度状态评估

| 维度 | 指标 | 上行信号 | 下行信号 |
|------|------|----------|----------|
| 增长 | PMI、工业增加值 | PMI>50, z-score>0 | PMI<50, z-score<0 |
| 通胀 | CPI、PPI、PCE | 同比上升, z-score>0 | 同比下降, z-score<0 |
| 政策 | LPR、FFR、MLF | 利率下调/降准 | 利率上调/缩表 |
| 流动性 | DR007、SOFR、利差 | 利率下行、利差走阔 | 利率上行、利差收窄 |
| 市场定价 | 国债收益率、ERP | 收益率上行、ERP收窄 | 收益率下行、ERP走阔 |

### 通道触发强度评估

- **强信号**：|z-score| > 1.5σ，通道传导强度高
- **中信号**：1.0σ < |z-score| ≤ 1.5σ，通道传导强度中等
- **弱信号**：0.5σ < |z-score| ≤ 1.0σ，通道传导强度低
- **未触发**：|z-score| ≤ 0.5σ

## 标准输出

### layer_output 格式

```json
{
    "layer_name": "layer0",
    "timestamp": "2026-05-15T00:00:00",
    "analysis_result": {
        "china_5d_panel": {
            "growth": {"raw": 50.2, "z_score": 0.1, "direction": "up"},
            "inflation": {"raw": 0.3, "z_score": -1.1, "direction": "down"},
            "policy": {"raw": null, "z_score": 0, "direction": "neutral"},
            "liquidity": {"raw": 1.8, "z_score": -0.7, "direction": "easy"},
            "market_pricing": {"raw": 2.5, "z_score": -1.0, "direction": "low"}
        },
        "us_5d_panel": {
            "growth": {"raw": 52.0, "z_score": 0.4, "direction": "up"},
            "inflation": {"raw": 2.5, "z_score": 0.8, "direction": "up"},
            "policy": {"raw": 5.25, "z_score": 0, "direction": "tight"},
            "liquidity": {"raw": 5.3, "z_score": 1.0, "direction": "tight"},
            "market_pricing": {"raw": 4.2, "z_score": 1.7, "direction": "high"}
        },
        "cross_border_signals": {
            "cn_us_10y_spread": {"raw": -1.7, "z_score": -1.7, "direction": "bearish"},
            "dxy": {"raw": 105.5, "z_score": 1.3, "direction": "strong"},
            "usd_cnh": {"raw": 7.25, "z_score": 0.8, "direction": "weak"}
        },
        "channel_status": [
            {"id": 1, "name": "利差→资本流→A股", "triggered": true, "strength": 0.7, "direction": "negative"},
            {"id": 2, "name": "美元→大宗→PPI→周期股", "triggered": true, "strength": 0.6, "direction": "negative"},
            {"id": 3, "name": "美联储→风险偏好→港股", "triggered": false, "strength": 0, "direction": "neutral"},
            {"id": 4, "name": "中国信贷→全球大宗", "triggered": false, "strength": 0, "direction": "neutral"},
            {"id": 5, "name": "全球PMI→中国出口", "triggered": true, "strength": 0.4, "direction": "positive"},
            {"id": 6, "name": "地缘政治→风险溢价", "triggered": false, "strength": 0, "direction": "neutral"}
        ],
        "interaction_level": "asymmetric"
    },
    "direction": "asymmetric",
    "confidence": 0.75,
    "reasoning": "中美交互层次: 非对称传导, 活跃通道数: 3, 主要影响: 美元强势+利差收窄对A股形成压力"
}
```

## meta 字段扩展

本层输出将填充顶层 Signal 的 `meta.layer_outputs.layer0` 字段。

## 待确认事项

1. **传导强度量化方法**：各通道的触发条件和传导强度计算公式需专家4组确认
2. **交互层次判定逻辑**：对称/非对称/反馈循环的量化判定阈值需专家4组确认
3. **政策维度z-score**：政策宽松/收紧程度的量化评分方法需专家4组确认
