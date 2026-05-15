"""
Layer 0: 双经济体追踪分析脚本

并行追踪中美五大维度指标，识别6条传导通道的触发状态。
"""

from typing import Dict, List, Any, Tuple, Optional
import pandas as pd
import numpy as np

from utils.constants import (
    Z_SCORE_THRESHOLDS,
    TRANSMISSION_CHANNELS,
    InteractionLevel,
)
from utils.signal_utils import build_layer_signal, determine_signal_direction


def analyze_bilateral_tracking(
    china_indicators: Dict[str, float],
    us_indicators: Dict[str, float],
    cross_border_metrics: Dict[str, float],
    historical_window: int = 252 * 5,  # 5年滚动窗口
) -> Dict[str, Any]:
    """
    分析中美双经济体追踪与交互通道。
    
    Args:
        china_indicators: 中国五大维度指标
            - growth: 增长维度 (PMI, 工业增加值等)
            - inflation: 通胀维度 (CPI, PPI等)
            - policy: 政策维度 (LPR, MLF等)
            - liquidity: 流动性维度 (DR007, SHIBOR, 社融等)
            - market_pricing: 市场定价维度 (国债收益率, ERP等)
        us_indicators: 美国五大维度指标
            - growth: 增长维度 (ISM PMI, 非农等)
            - inflation: 通胀维度 (PCE, CPI等)
            - policy: 政策维度 (FFR, QE/QT等)
            - liquidity: 流动性维度 (SOFR, EFFR, 信贷脉冲等)
            - market_pricing: 市场定价维度 (UST收益率, ERP等)
        cross_border_metrics: 跨国指标
            - cn_us_10y_spread: 中美10Y利差
            - dxy_index: 美元指数
            - usd_cnh: USD/CNH汇率
        historical_window: z-score滚动窗口（日频数据天数）
    
    Returns:
        分析结果字典，包含：
        - china_5d_panel: 中国5维度指标面板（含z-score）
        - us_5d_panel: 美国5维度指标面板（含z-score）
        - cross_border_signals: 跨国差值/比值信号
        - channel_status: 6条传导通道触发状态
        - interaction_level: 交互层次判定
        - layer_output: 标准化层输出
    
    Example:
        >>> result = analyze_bilateral_tracking(
        ...     china_indicators={
        ...         "growth": {"nbs_pmi": 50.2},
        ...         "inflation": {"cpi_yoy": 0.3},
        ...         "policy": {"1y_lpr": 3.45},
        ...         "liquidity": {"dr007": 1.8},
        ...         "market_pricing": {"10y_bond_yield": 2.5},
        ...     },
        ...     us_indicators={
        ...         "growth": {"ism_pmi": 52.0},
        ...         "inflation": {"pce_yoy": 2.5},
        ...         "policy": {"ffr": 5.25},
        ...         "liquidity": {"sofr": 5.3},
        ...         "market_pricing": {"10y_ust_yield": 4.2},
        ...     },
        ...     cross_border_metrics={
        ...         "cn_us_10y_spread": -1.7,
        ...         "dxy_index": 105.5,
        ...         "usd_cnh": 7.25,
        ...     },
        ... )
    """
    # Step 1: 计算中国5维度z-score
    china_5d_panel = _calculate_china_dimensions(china_indicators)
    
    # Step 2: 计算美国5维度z-score
    us_5d_panel = _calculate_us_dimensions(us_indicators)
    
    # Step 3: 计算跨国差值/比值信号
    cross_border_signals = _calculate_cross_border_signals(
        china_5d_panel, us_5d_panel, cross_border_metrics
    )
    
    # Step 4: 检查6条传导通道触发状态
    channel_status = _check_transmission_channels(
        china_5d_panel, us_5d_panel, cross_border_signals
    )
    
    # Step 5: 判定交互层次
    interaction_level = _determine_interaction_level(
        china_5d_panel, us_5d_panel, cross_border_signals, channel_status
    )
    
    # 构建层输出
    layer_output = build_layer_signal(
        layer_name="layer0",
        analysis_result={
            "china_5d_panel": china_5d_panel,
            "us_5d_panel": us_5d_panel,
            "cross_border_signals": cross_border_signals,
            "channel_status": channel_status,
            "interaction_level": interaction_level.value,
        },
        direction=interaction_level.value,
        confidence=0.7,  # TODO: 根据数据完整性调整
        reasoning=f"中美交互层次: {interaction_level.value}, 活跃通道数: {sum(1 for c in channel_status if c['triggered'])}",
    )
    
    return {
        "china_5d_panel": china_5d_panel,
        "us_5d_panel": us_5d_panel,
        "cross_border_signals": cross_border_signals,
        "channel_status": channel_status,
        "interaction_level": interaction_level,
        "layer_output": layer_output,
    }


def _calculate_china_dimensions(
    indicators: Dict[str, Dict[str, float]]
) -> Dict[str, Any]:
    """
    计算中国5维度z-score。
    
    Returns:
        {
            "growth": {"raw": xxx, "z_score": xxx, "direction": "up/down/neutral"},
            ...
        }
    """
    dimensions = {}
    
    # 增长维度
    if "growth" in indicators and indicators["growth"]:
        raw_score = np.mean(list(indicators["growth"].values()))
        dimensions["growth"] = {
            "raw": raw_score,
            "z_score": _estimate_z_score(raw_score, mean=50, std=2),  # PMI类指标的近似z-score
            "direction": "up" if raw_score > 50 else "down",
            "indicators": indicators["growth"],
        }
    
    # 通胀维度
    if "inflation" in indicators and indicators["inflation"]:
        raw_score = np.mean(list(indicators["inflation"].values()))
        dimensions["inflation"] = {
            "raw": raw_score,
            "z_score": _estimate_z_score(raw_score, mean=2, std=1.5),  # CPI类指标的近似z-score
            "direction": "up" if raw_score > 2 else "down",
            "indicators": indicators["inflation"],
        }
    
    # 政策维度
    if "policy" in indicators and indicators["policy"]:
        # 政策宽松程度评分（需要LLM辅助解读）
        dimensions["policy"] = {
            "raw": None,  # 需要定性评估
            "z_score": 0,  # TODO: 需要政策打分卡
            "direction": "easy" if indicators["policy"].get("easing_signal") else "neutral",
            "indicators": indicators["policy"],
        }
    
    # 流动性维度
    if "liquidity" in indicators and indicators["liquidity"]:
        # DR007等银行间利率
        dr007 = indicators["liquidity"].get("dr007")
        if dr007:
            dimensions["liquidity"] = {
                "raw": dr007,
                "z_score": _estimate_z_score(dr007, mean=2.0, std=0.3),
                "direction": "tight" if dr007 > 2.2 else "easy",
                "indicators": indicators["liquidity"],
            }
    
    # 市场定价维度
    if "market_pricing" in indicators and indicators["market_pricing"]:
        bond_yield = indicators["market_pricing"].get("10y_bond_yield")
        if bond_yield:
            dimensions["market_pricing"] = {
                "raw": bond_yield,
                "z_score": _estimate_z_score(bond_yield, mean=3.0, std=0.5),
                "direction": "neutral",
                "indicators": indicators["market_pricing"],
            }
    
    return dimensions


def _calculate_us_dimensions(
    indicators: Dict[str, Dict[str, float]]
) -> Dict[str, Any]:
    """
    计算美国5维度z-score。
    """
    dimensions = {}
    
    # 增长维度
    if "growth" in indicators and indicators["growth"]:
        ism_pmi = indicators["growth"].get("ism_pmi")
        if ism_pmi:
            dimensions["growth"] = {
                "raw": ism_pmi,
                "z_score": _estimate_z_score(ism_pmi, mean=50, std=5),
                "direction": "up" if ism_pmi > 50 else "down",
                "indicators": indicators["growth"],
            }
    
    # 通胀维度
    if "inflation" in indicators and indicators["inflation"]:
        pce = indicators["inflation"].get("pce_yoy")
        if pce:
            dimensions["inflation"] = {
                "raw": pce,
                "z_score": _estimate_z_score(pce, mean=2.0, std=0.5),
                "direction": "up" if pce > 2.0 else "down",
                "indicators": indicators["inflation"],
            }
    
    # 政策维度
    if "policy" in indicators and indicators["policy"]:
        ffr = indicators["policy"].get("ffr")
        if ffr:
            dimensions["policy"] = {
                "raw": ffr,
                "z_score": 0,  # 绝对利率水平的z-score意义有限
                "direction": "tight",
                "indicators": indicators["policy"],
            }
    
    # 流动性维度
    if "liquidity" in indicators and indicators["liquidity"]:
        sofr = indicators["liquidity"].get("sofr")
        if sofr:
            dimensions["liquidity"] = {
                "raw": sofr,
                "z_score": _estimate_z_score(sofr, mean=5.0, std=0.3),
                "direction": "tight" if sofr > 5.0 else "easy",
                "indicators": indicators["liquidity"],
            }
    
    # 市场定价维度
    if "market_pricing" in indicators and indicators["market_pricing"]:
        ust_yield = indicators["market_pricing"].get("10y_ust_yield")
        if ust_yield:
            dimensions["market_pricing"] = {
                "raw": ust_yield,
                "z_score": _estimate_z_score(ust_yield, mean=2.5, std=1.0),
                "direction": "neutral",
                "indicators": indicators["market_pricing"],
            }
    
    return dimensions


def _calculate_cross_border_signals(
    china_5d: Dict[str, Any],
    us_5d: Dict[str, Any],
    cross_metrics: Dict[str, float],
) -> Dict[str, Any]:
    """
    计算跨国差值/比值信号。
    """
    signals = {}
    
    # 中美10Y利差
    if "cn_us_10y_spread" in cross_metrics:
        spread = cross_metrics["cn_us_10y_spread"]
        signals["cn_us_10y_spread"] = {
            "raw": spread,
            "z_score": _estimate_z_score(spread, mean=0, std=1.0),  # 近似
            "direction": determine_signal_direction(
                _estimate_z_score(spread, mean=0, std=1.0),
                threshold_confirm=Z_SCORE_THRESHOLDS["direction_confirm"],
                threshold_neutral=Z_SCORE_THRESHOLDS["direction_neutral"],
            ),
        }
    
    # 美元指数
    if "dxy_index" in cross_metrics:
        dxy = cross_metrics["dxy_index"]
        signals["dxy"] = {
            "raw": dxy,
            "z_score": _estimate_z_score(dxy, mean=95, std=8),
            "direction": "strong" if dxy > 100 else "weak",
        }
    
    # USD/CNH
    if "usd_cnh" in cross_metrics:
        cnh = cross_metrics["usd_cnh"]
        signals["usd_cnh"] = {
            "raw": cnh,
            "z_score": _estimate_z_score(cnh, mean=7.0, std=0.3),
            "direction": "weak" if cnh > 7.1 else "strong",
        }
    
    # 中美增长差值
    if "growth" in china_5d and "growth" in us_5d:
        cn_growth_z = china_5d["growth"].get("z_score", 0)
        us_growth_z = us_5d["growth"].get("z_score", 0)
        signals["growth_diff"] = {
            "raw": cn_growth_z - us_growth_z,
            "z_score": cn_growth_z - us_growth_z,  # 差值本身即为标准化
            "direction": determine_signal_direction(cn_growth_z - us_growth_z),
        }
    
    return signals


def _check_transmission_channels(
    china_5d: Dict[str, Any],
    us_5d: Dict[str, Any],
    cross_signals: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    检查6条传导通道触发状态。
    """
    channels = []
    
    for channel in TRANSMISSION_CHANNELS:
        channel_id = channel["id"]
        channel_name = channel["name"]
        
        # TODO: 根据各通道的触发条件判断
        # 这里使用简化逻辑
        
        if channel_id == 1:  # 利差→资本流→A股
            spread_z = cross_signals.get("cn_us_10y_sspread", {}).get("z_score", 0)
            triggered = abs(spread_z) > Z_SCORE_THRESHOLDS["direction_neutral"]
            strength = min(abs(spread_z) / 2.0, 1.0) if triggered else 0
        
        elif channel_id == 2:  # 美元→大宗→PPI→周期股
            dxy_z = cross_signals.get("dxy", {}).get("z_score", 0)
            triggered = abs(dxy_z) > Z_SCORE_THRESHOLDS["direction_neutral"]
            strength = min(abs(dxy_z) / 2.0, 1.0) if triggered else 0
        
        elif channel_id == 3:  # 美联储→风险偏好→港股
            us_policy_z = us_5d.get("policy", {}).get("z_score", 0)
            triggered = abs(us_policy_z) > Z_SCORE_THRESHOLDS["direction_neutral"]
            strength = min(abs(us_policy_z) / 2.0, 1.0) if triggered else 0
        
        elif channel_id == 4:  # 中国信贷→全球大宗
            cn_liquidity_z = china_5d.get("liquidity", {}).get("z_score", 0)
            triggered = abs(cn_liquidity_z) > Z_SCORE_THRESHOLDS["direction_neutral"]
            strength = min(abs(cn_liquidity_z) / 2.0, 1.0) if triggered else 0
        
        elif channel_id == 5:  # 全球PMI→中国出口
            global_growth_z = us_5d.get("growth", {}).get("z_score", 0)
            triggered = abs(global_growth_z) > Z_SCORE_THRESHOLDS["direction_neutral"]
            strength = min(abs(global_growth_z) / 2.0, 1.0) if triggered else 0
        
        elif channel_id == 6:  # 地缘政治→风险溢价
            # 地缘政治需要外部输入，暂时标记为未触发
            triggered = False
            strength = 0
        
        else:
            triggered = False
            strength = 0
        
        channels.append({
            "id": channel_id,
            "name": channel_name,
            "triggered": triggered,
            "strength": strength,
            "direction": "positive" if strength > 0 else "neutral",
        })
    
    return channels


def _determine_interaction_level(
    china_5d: Dict[str, Any],
    us_5d: Dict[str, Any],
    cross_signals: Dict[str, Any],
    channel_status: List[Dict],
) -> InteractionLevel:
    """
    判定中美交互层次。
    
    - 对称交互：中美处于同一周期阶段时的共振
    - 非对称传导：一方政策变化通过6条通道单向传导至另一方资产
    - 反馈循环：通道间形成闭环
    """
    # 统计活跃通道数
    active_channels = sum(1 for c in channel_status if c["triggered"])
    
    # 检查是否有双向传导（反馈循环）
    growth_diff = cross_signals.get("growth_diff", {}).get("z_score", 0)
    
    if active_channels >= 4 and abs(growth_diff) < 1.0:
        # 多个通道活跃，增长差值小 → 对称交互
        return InteractionLevel.SYMMETRIC
    elif active_channels >= 2 and abs(growth_diff) >= 1.0:
        # 有通道活跃，增长差值大 → 非对称传导
        return InteractionLevel.ASYMMETRIC
    elif active_channels >= 3:
        # 多个通道活跃 → 可能反馈循环
        return InteractionLevel.FEEDBACK_LOOP
    else:
        # 通道不活跃 → 非对称传导（默认）
        return InteractionLevel.ASYMMETRIC


def _estimate_z_score(value: float, mean: float, std: float) -> float:
    """
    估算z-score（简化版，未使用真实历史数据）。
    
    实际实现应使用滚动窗口计算真实z-score。
    """
    if std == 0:
        return 0
    return (value - mean) / std


# =============================================================================
# LLM 调用接口（供 Agent 使用）
# =============================================================================

LLM_PROMPT_TEMPLATE = """
# Layer 0: 双经济体追踪与中美交互通道

## 分析任务

根据以下数据，分析中美两国的双经济体追踪与交互通道状态：

### 中国五大维度指标
{china_data}

### 美国五大维度指标
{us_data}

### 跨国指标
{cross_data}

## 分析要求

1. 评估中国增长/通胀/政策/流动性/市场定价五个维度的当前状态
2. 评估美国增长/通胀/政策/流动性/市场定价五个维度的当前状态
3. 分析6条中美传导通道的触发状态和传导强度：
   - 通道1: 利差→资本流→A股
   - 通道2: 美元→大宗→PPI→周期股
   - 通道3: 美联储→风险偏好→港股
   - 通道4: 中国信贷→全球大宗
   - 通道5: 全球PMI→中国出口
   - 通道6: 地缘政治→风险溢价
4. 判定中美交互层次（对称交互/非对称传导/反馈循环）
5. 输出对A股和港股有影响的关键信号

## 输出格式

请以JSON格式输出分析结果：
```json
{{
    "china_assessment": {{
        "growth": "上行/下行/中性",
        "inflation": "上行/下行/中性",
        "policy": "宽松/中性/收紧",
        "liquidity": "偏松/中性/偏紧",
        "market_pricing": "正常/偏高/偏低"
    }},
    "us_assessment": {{
        "growth": "上行/下行/中性",
        "inflation": "上行/下行/中性",
        "policy": "宽松/中性/收紧",
        "liquidity": "偏松/中性/偏紧",
        "market_pricing": "正常/偏高/偏低"
    }},
    "channel_status": [
        {{"id": 1, "name": "通道名", "triggered": true/false, "strength": 0-1, "direction": "正向/负向"}}
    ],
    "interaction_level": "对称交互/非对称传导/反馈循环",
    "key_signals": ["关键信号1", "关键信号2"],
    "risk_notes": ["风险提示1"]
}}
```
"""


def generate_llm_prompt(
    china_data: Dict[str, Any],
    us_data: Dict[str, Any],
    cross_data: Dict[str, Any],
) -> str:
    """
    生成 LLM 分析提示词。
    
    供 Agent 调用 LLM 时使用。
    """
    return LLM_PROMPT_TEMPLATE.format(
        china_data=_format_dict_for_prompt(china_data),
        us_data=_format_dict_for_prompt(us_data),
        cross_data=_format_dict_for_prompt(cross_data),
    )


def _format_dict_for_prompt(data: Dict) -> str:
    """将字典格式化为可读文本。"""
    if not data:
        return "数据不足"
    lines = []
    for key, value in data.items():
        if isinstance(value, dict):
            lines.append(f"- {key}:")
            for k, v in value.items():
                lines.append(f"  - {k}: {v}")
        else:
            lines.append(f"- {key}: {value}")
    return "\n".join(lines) if lines else "数据不足"
