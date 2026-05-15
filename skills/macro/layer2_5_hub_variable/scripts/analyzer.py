"""
Layer 2.5: 枢纽变量分析——汇率与大宗商品传导

汇率与大宗商品是连接中美宏观的核心传导枢纽。
本层显式建模汇率与大宗商品的传导作用。
"""

from typing import Dict, List, Any, Optional
import numpy as np

from utils.constants import (
    CNH_DIRECTION_WEIGHTS,
    GlobalMacroTriangle,
    Z_SCORE_THRESHOLDS,
)
from utils.signal_utils import build_layer_signal, determine_signal_direction


def analyze_hub_variable(
    exchange_rate_data: Dict[str, float],
    commodity_data: Dict[str, float],
    interest_rate_data: Dict[str, float],
    global_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    分析枢纽变量：汇率与大宗商品传导。
    
    Args:
        exchange_rate_data: 汇率数据
            - usd_cnh: USD/CNH即期汇率
            - usd_cnh_1y_forward: USD/CNH 1年远期点
            - cnh_cny_spread: CNH-CNY价差
            - cny_rr_25d: 人民币期权25Delta Risk Reversal
            - pboc_mid_rate_deviation: 央行中间价偏离度
            - forex_reserve_change: 外储月度变化
            - trade_surplus: 贸易顺差（海关口径）
            - china_10y_yield: 中国10Y国债收益率
            - us_10y_yield: 美国10Y国债收益率
        
        commodity_data: 大宗商品数据
            - copper_gold_ratio: 铜金比
            - oil_gold_ratio: 油金比
            - iron_copper_ratio: 铁矿石/铜比
            - soybean_corn_ratio: 大豆/玉米比
            - gold_vs_real_rate: 黄金 vs 实际利率
            - nh_vs_global_pmi: 南华 vs 全球PMI
        
        interest_rate_data: 利率数据（用于宏观三角）
            - cn_policy_rate: 中国政策利率
            - us_policy_rate: 美国政策利率
            - vix: VIX恐慌指数
        
        global_context: 全球宏观背景（可选）
            - global_growth: 全球增长状态
            - global_inflation: 全球通胀状态
    
    Returns:
        枢纽变量分析结果
    
    Example:
        >>> result = analyze_hub_variable(
        ...     exchange_rate_data={
        ...         "usd_cnh": 7.25,
        ...         "cnh_cny_spread": 0.02,
        ...         "trade_surplus": 500,
        ...     },
        ...     commodity_data={
        ...         "copper_gold_ratio": 0.15,
        ...         "oil_gold_ratio": 20,
        ...     },
        ...     interest_rate_data={
        ...         "china_10y_yield": 2.5,
        ...         "us_10y_yield": 4.2,
        ...         "vix": 15,
        ...     },
        ... )
    """
    # Step 1: 计算USD/CNH方向得分
    cnh_direction = calculate_cnh_direction(exchange_rate_data)
    
    # Step 2: 计算6个商品比值信号
    commodity_signals = calculate_commodity_signals(commodity_data)
    
    # Step 3: 定位全球宏观三角
    macro_triangle = determine_macro_triangle(
        interest_rate_data, commodity_data, cnh_direction
    )
    
    # Step 4: 检查关键传导通道警报
    channel_alerts = check_channel_alerts(
        cnh_direction, commodity_signals, exchange_rate_data
    )
    
    # 构建层输出
    layer_output = build_layer_signal(
        layer_name="layer2_5",
        analysis_result={
            "cnh_direction": cnh_direction,
            "commodity_signals": commodity_signals,
            "macro_triangle": macro_triangle,
            "channel_alerts": channel_alerts,
        },
        direction=cnh_direction.get("direction", "neutral"),
        confidence=0.7,
        reasoning=f"USD/CNH方向: {cnh_direction.get('direction', 'neutral')}, 全球三角: {macro_triangle.get('triangle', 'unknown')}",
    )
    
    return {
        "cnh_direction": cnh_direction,
        "commodity_signals": commodity_signals,
        "macro_triangle": macro_triangle,
        "channel_alerts": channel_alerts,
        "layer_output": layer_output,
    }


def calculate_cnh_direction(
    data: Dict[str, float]
) -> Dict[str, Any]:
    """
    计算USD/CNH方向得分。
    
    驱动力权重：
    - 利差驱动 0.30
    - 经常账户 0.20
    - 风险偏好 0.20
    - 政策意图 0.30
    """
    if not data:
        return {"score": 0, "direction": "neutral", "confidence": 0}
    
    # 利差驱动
    cn_yield = data.get("china_10y_yield")
    us_yield = data.get("us_10y_yield")
    if cn_yield is not None and us_yield is not None:
        spread = cn_yield - us_yield
        # 利差收窄/倒挂 -> 贬值压力（得分正向）
        rate_score = -spread  # 负spread = 贬值
    else:
        rate_score = 0
    
    # 经常账户
    trade_surplus = data.get("trade_surplus")
    if trade_surplus is not None:
        # 顺差扩大 -> 升值支撑（得分负向）
        ca_score = -min(trade_surplus / 1000, 1)  # 归一化
    else:
        ca_score = 0
    
    # 风险偏好（简化版）
    cnh_cny_spread = data.get("cnh_cny_spread")
    if cnh_cny_spread is not None:
        # 价差扩大 -> 贬值压力
        risk_score = min(cnh_cny_spread / 0.1, 1) * 2  # 归一化并放大
    else:
        risk_score = 0
    
    # 政策意图（简化版，需要LLM解读）
    # 这里用外储变化作为代理
    forex_change = data.get("forex_reserve_change")
    if forex_change is not None:
        # 外储下降 -> 贬值压力
        policy_score = -min(forex_change / 100, 1) * 2
    else:
        policy_score = 0
    
    # 加权求和
    score = (
        rate_score * CNH_DIRECTION_WEIGHTS["interest_rate_spread"] +
        ca_score * CNH_DIRECTION_WEIGHTS["current_account"] +
        risk_score * CNH_DIRECTION_WEIGHTS["risk_appetite"] +
        policy_score * CNH_DIRECTION_WEIGHTS["policy_intent"]
    ) / (
        CNH_DIRECTION_WEIGHTS["interest_rate_spread"] +
        CNH_DIRECTION_WEIGHTS["current_account"] +
        CNH_DIRECTION_WEIGHTS["risk_appetite"] +
        CNH_DIRECTION_WEIGHTS["policy_intent"]
    )
    
    # 方向判定
    if score > 1.0:
        direction = "升值确认"
        direction_signal = "bullish"
    elif score < -1.0:
        direction = "贬值确认"
        direction_signal = "bearish"
    elif abs(score) <= 0.5:
        direction = "震荡/无方向"
        direction_signal = "neutral"
    else:
        direction = "偏升值" if score > 0 else "偏贬值"
        direction_signal = "neutral"
    
    return {
        "score": score,
        "direction": direction,
        "direction_signal": direction_signal,
        "components": {
            "rate_score": rate_score,
            "ca_score": ca_score,
            "risk_score": risk_score,
            "policy_score": policy_score,
        },
    }


def calculate_commodity_signals(
    data: Dict[str, float]
) -> List[Dict[str, Any]]:
    """
    计算6个商品比值信号。
    
    每个比值做z-score处理：
    - |z| > 1.5: 强信号
    - |z| > 2.0: 极强信号
    """
    signals = []
    
    # 1. 铜金比
    if "copper_gold_ratio" in data:
        ratio = data["copper_gold_ratio"]
        z_score = estimate_ratio_zscore(ratio, "copper_gold")
        signals.append({
            "id": 1,
            "name": "铜金比",
            "raw": ratio,
            "z_score": z_score,
            "signal": "强信号" if abs(z_score) > 1.5 else ("极强信号" if abs(z_score) > 2.0 else "无信号"),
            "macro_meaning": _interpret_copper_gold_ratio(z_score),
        })
    
    # 2. 油金比
    if "oil_gold_ratio" in data:
        ratio = data["oil_gold_ratio"]
        z_score = estimate_ratio_zscore(ratio, "oil_gold")
        signals.append({
            "id": 2,
            "name": "油金比",
            "raw": ratio,
            "z_score": z_score,
            "signal": "强信号" if abs(z_score) > 1.5 else ("极强信号" if abs(z_score) > 2.0 else "无信号"),
            "macro_meaning": _interpret_oil_gold_ratio(z_score),
        })
    
    # 3. 铁矿石/铜比
    if "iron_copper_ratio" in data:
        ratio = data["iron_copper_ratio"]
        z_score = estimate_ratio_zscore(ratio, "iron_copper")
        signals.append({
            "id": 3,
            "name": "铁矿石/铜比",
            "raw": ratio,
            "z_score": z_score,
            "signal": "强信号" if abs(z_score) > 1.5 else ("极强信号" if abs(z_score) > 2.0 else "无信号"),
            "macro_meaning": _interpret_iron_copper_ratio(z_score),
        })
    
    # 4. 大豆/玉米比
    if "soybean_corn_ratio" in data:
        ratio = data["soybean_corn_ratio"]
        z_score = estimate_ratio_zscore(ratio, "soybean_corn")
        signals.append({
            "id": 4,
            "name": "大豆/玉米比",
            "raw": ratio,
            "z_score": z_score,
            "signal": "强信号" if abs(z_score) > 1.5 else ("极强信号" if abs(z_score) > 2.0 else "无信号"),
            "macro_meaning": _interpret_soybean_corn_ratio(z_score),
        })
    
    # 5. 黄金 vs 实际利率
    if "gold_vs_real_rate" in data:
        ratio = data["gold_vs_real_rate"]
        z_score = estimate_ratio_zscore(ratio, "gold_real_rate")
        signals.append({
            "id": 5,
            "name": "黄金vs实际利率",
            "raw": ratio,
            "z_score": z_score,
            "signal": "强信号" if abs(z_score) > 1.5 else ("极强信号" if abs(z_score) > 2.0 else "无信号"),
            "macro_meaning": _interpret_gold_real_rate(z_score),
        })
    
    # 6. 南华 vs 全球PMI
    if "nh_vs_global_pmi" in data:
        ratio = data["nh_vs_global_pmi"]
        z_score = estimate_ratio_zscore(ratio, "nh_global_pmi")
        signals.append({
            "id": 6,
            "name": "南华vs全球PMI",
            "raw": ratio,
            "z_score": z_score,
            "signal": "强信号" if abs(z_score) > 1.5 else ("极强信号" if abs(z_score) > 2.0 else "无信号"),
            "macro_meaning": _interpret_nh_global_pmi(z_score),
        })
    
    return signals


def determine_macro_triangle(
    interest_data: Dict[str, float],
    commodity_data: Dict[str, float],
    cnh_direction: Dict[str, Any],
) -> Dict[str, Any]:
    """
    定位全球宏观三角：美元、大宗、美债。
    
    | 宏观环境 | 含义 | 最优资产 |
    |----------|------|----------|
    | 全球紧缩 | 强美元 + 弱大宗 + 高美债 | 中债长端、防御股 |
    | 全球宽松 | 弱美元 + 强大宗 + 低美债 | 周期股、大宗股、港股 |
    | 滞胀型 | 强美元 + 强大宗 + 高美债 | 黄金、短债 |
    | 通缩型 | 弱美元 + 弱大宗 + 低美债 | 利率债、高股息 |
    """
    # 简化判定逻辑
    # 美元方向
    usd_strength = 1 if cnh_direction.get("score", 0) < -0.5 else (-1 if cnh_direction.get("score", 0) > 0.5 else 0)
    
    # 大宗方向
    commodity_score = 0
    if commodity_data:
        copper_gold = commodity_data.get("copper_gold_ratio", 0)
        if copper_gold > 0.18:  # 铜金比高 = 增长乐观 = 大宗强
            commodity_score = 1
        elif copper_gold < 0.12:
            commodity_score = -1
    
    # 美债方向
    us_yield = interest_data.get("us_10y_yield", 3.0)
    if us_yield > 4.0:
        us_rate_level = 1  # 高利率
    elif us_yield < 2.5:
        us_rate_level = -1  # 低利率
    else:
        us_rate_level = 0
    
    # 判定宏观三角
    if usd_strength == 1 and commodity_score == -1 and us_rate_level == 1:
        triangle = GlobalMacroTriangle.GLOBAL_TIGHTENING.value
        best_assets = ["中债长端", "防御股", "黄金"]
    elif usd_strength == -1 and commodity_score == 1 and us_rate_level == -1:
        triangle = GlobalMacroTriangle.GLOBAL_EASING.value
        best_assets = ["周期股", "大宗股", "港股"]
    elif usd_strength == 1 and commodity_score == 1 and us_rate_level == 1:
        triangle = GlobalMacroTriangle.STAGFLATION.value
        best_assets = ["黄金", "短债"]
    elif usd_strength == -1 and commodity_score == -1 and us_rate_level == -1:
        triangle = GlobalMacroTriangle.DEFLATION.value
        best_assets = ["利率债", "高股息"]
    else:
        triangle = "mixed"  # 混合状态
        best_assets = []
    
    return {
        "triangle": triangle,
        "usd_strength": usd_strength,
        "commodity_score": commodity_score,
        "us_rate_level": us_rate_level,
        "best_assets": best_assets,
    }


def check_channel_alerts(
    cnh_direction: Dict[str, Any],
    commodity_signals: List[Dict[str, Any]],
    exchange_data: Dict[str, float],
) -> List[Dict[str, Any]]:
    """
    检查关键传导通道警报。
    """
    alerts = []
    
    # 通道2: 美元→大宗→PPI→周期股
    usd_score = cnh_direction.get("score", 0)
    if usd_score > 1.0:
        alerts.append({
            "channel_id": 2,
            "name": "美元→大宗→PPI→周期股",
            "status": "active",
            "direction": "negative",
            "detail": "美元强势对A股周期股形成压力"
        })
    elif usd_score < -1.0:
        alerts.append({
            "channel_id": 2,
            "name": "美元→大宗→PPI→周期股",
            "status": "active",
            "direction": "positive",
            "detail": "美元弱势对A股周期股形成支撑"
        })
    
    # 通道4: 中国信贷→全球大宗
    for sig in commodity_signals:
        if sig["name"] == "铁矿石/铜比" and abs(sig["z_score"]) > 1.5:
            direction = "positive" if sig["z_score"] > 0 else "negative"
            alerts.append({
                "channel_id": 4,
                "name": "中国信贷→全球大宗",
                "status": "active",
                "direction": direction,
                "detail": f"铁矿石/铜比信号异常：{sig['macro_meaning']}"
            })
    
    # 通道6: 地缘政治→风险溢价
    cnh_spread = exchange_data.get("cnh_cny_spread", 0)
    if abs(cnh_spread) > 0.05:
        alerts.append({
            "channel_id": 6,
            "name": "地缘政治→风险溢价",
            "status": "warning",
            "direction": "negative",
            "detail": "CNH-CNY价差扩大，离岸贬值压力增加"
        })
    
    return alerts


# =============================================================================
# 辅助函数
# =============================================================================

def estimate_ratio_zscore(value: float, ratio_type: str) -> float:
    """
    估算比值z-score（简化版，未使用真实历史数据）。
    """
    # 预设均值和标准差
    params = {
        "copper_gold": (0.15, 0.03),     # 铜金比
        "oil_gold": (18.0, 5.0),         # 油金比
        "iron_copper": (1.5, 0.3),       # 铁矿石/铜
        "soybean_corn": (2.5, 0.5),       # 大豆/玉米
        "gold_real_rate": (1800, 300),    # 黄金/实际利率
        "nh_global_pmi": (1.0, 0.2),      # 南华/全球PMI
    }
    
    if ratio_type in params:
        mean, std = params[ratio_type]
    else:
        mean, std = 1.0, 0.3
    
    if std == 0:
        return 0
    
    return (value - mean) / std


def _interpret_copper_gold_ratio(z_score: float) -> str:
    """解释铜金比的宏观含义。"""
    if z_score > 1.5:
        return "全球工业需求强劲，铜相对黄金表现优异"
    elif z_score < -1.5:
        return "全球工业需求疲弱，避险情绪浓厚"
    else:
        return "全球工业需求中性"


def _interpret_oil_gold_ratio(z_score: float) -> str:
    """解释油金比的宏观含义。"""
    if z_score > 1.5:
        return "通胀压力上行，原油相对黄金强势"
    elif z_score < -1.5:
        return "通胀压力下行，实际利率可能上升"
    else:
        return "通胀预期中性"


def _interpret_iron_copper_ratio(z_score: float) -> str:
    """解释铁矿石/铜比的宏观含义。"""
    if z_score > 1.5:
        return "中国地产/基建相对全球更强"
    elif z_score < -1.5:
        return "中国需求相对全球偏弱"
    else:
        return "中国vs全球需求分化不明显"


def _interpret_soybean_corn_ratio(z_score: float) -> str:
    """解释大豆/玉米比的宏观含义。"""
    if z_score > 1.5:
        return "农业通胀结构异常，可能存在供给冲击"
    elif z_score < -1.5:
        return "农产品供需正常"
    else:
        return "农业通胀无明显异常"


def _interpret_gold_real_rate(z_score: float) -> str:
    """解释黄金vs实际利率的宏观含义。"""
    if z_score > 1.5:
        return "黄金被低估，实际利率与黄金背离"
    elif z_score < -1.5:
        return "黄金涨幅超过实际利率下降幅度，避险/去美元化"
    else:
        return "黄金定价正常"


def _interpret_nh_global_pmi(z_score: float) -> str:
    """解释南华vs全球PMI的宏观含义。"""
    if z_score > 1.5:
        return "中国独立定价逻辑强化"
    elif z_score < -1.5:
        return "中国跟随全球定价"
    else:
        return "中国与全球联动正常"


# =============================================================================
# LLM 调用接口
# =============================================================================

LLM_PROMPT_TEMPLATE = """
# Layer 2.5: 枢纽变量分析——汇率与大宗商品传导

## 分析任务

分析汇率与大宗商品的传导作用，完成以下评估：

### USD/CNH方向分析
- 方向得分: {cnh_score}
- 方向: {cnh_direction}
- 组成: 利差驱动={rate}, 经常账户={ca}, 风险偏好={risk}, 政策意图={policy}

### 大宗商品信号
{commodity_signals}

### 全球宏观三角
- 三角定位: {triangle}

## 分析要求

1. 评估USD/CNH方向和驱动因素
2. 分析大宗商品比值信号的宏观含义
3. 确认全球宏观三角定位
4. 检查关键传导通道警报

## 输出格式

```json
{{
    "cnh_assessment": {{
        "direction": "升值/贬值/震荡",
        "key_drivers": ["驱动因素1", "驱动因素2"],
        "confidence": 0-1
    }},
    "commodity_assessment": {{
        "global_demand": "强劲/疲弱/中性",
        "inflation_pressure": "上行/下行/中性",
        "china_vs_global": "分化/一致"
    }},
    "triangle_confirmed": "全球紧缩/全球宽松/滞胀/通缩/混合",
    "channel_alerts": ["警报1", "警报2"],
    "key_risks": ["风险1"],
    "opportunities": ["机会1"]
}}
```
"""


def generate_llm_prompt(
    cnh_direction: Dict[str, Any],
    commodity_signals: List[Dict],
    macro_triangle: Dict[str, Any],
) -> str:
    """生成LLM分析提示词。"""
    signals_text = "\n".join([
        f"- {s['name']}: z-score={s['z_score']:.2f}, 含义={s['macro_meaning']}"
        for s in commodity_signals
    ]) if commodity_signals else "数据不足"
    
    return LLM_PROMPT_TEMPLATE.format(
        cnh_score=cnh_direction.get("score", 0),
        cnh_direction=cnh_direction.get("direction", "未知"),
        rate=cnh_direction.get("components", {}).get("rate_score", 0),
        ca=cnh_direction.get("components", {}).get("ca_score", 0),
        risk=cnh_direction.get("components", {}).get("risk_score", 0),
        policy=cnh_direction.get("components", {}).get("policy_score", 0),
        commodity_signals=signals_text,
        triangle=macro_triangle.get("triangle", "未知"),
    )
