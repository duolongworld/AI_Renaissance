"""
Layer 0: 双经济体追踪分析脚本

并行追踪中美五大维度指标，识别6条传导通道的触发状态。
"""

from typing import Dict, List, Any, Tuple, Optional
import pandas as pd
import numpy as np
from datetime import datetime

from utils.constants import (
    Z_SCORE_THRESHOLDS,
    TRANSMISSION_CHANNELS,
    InteractionLevel,
)
from utils.signal_utils import build_layer_signal, determine_signal_direction


# =============================================================================
# 政策打分卡（框架原文 V3.x 第1117-1130行）
# 5项×0-2分，满分10分；≥7=强转向，5-6=边际宽松，≤4=无转向
# =============================================================================

_POLICY_SCORING_RULES = {
    "media_wording": {
        # 官方媒体措辞变化（新华社/人民日报）
        "strong_positive": ["超常规", "历史性", "前所未有"],   # +2
        "positive": ["积极", "有力", "加大力度", "充分发力"],    # +1
        "neutral": [],                                          # 0
        "negative": ["稳健", "审慎"],                           # -1
        "strong_negative": [],                                  # -2
    },
    "state_council": {
        # 国常会频次与议题
        "strong_positive": [],   # +2：连续2次以上聚焦经济
        "positive": [],          # +1：频次增加
        "neutral": [],           # 0：常规频次
    },
    "pboc_statement": {
        # 央行货政报告措辞
        "strong_positive": ["充分发力", "超常规"],  # +2
        "positive": ["加大力度"],                   # +1
        "neutral": ["稳健"],                        # 0
        "negative": ["审慎", "克制"],               # -1
    },
    "top_meeting": {
        # 高层会议信号
        "strong_positive": ["超常规"],              # +2
        "positive": ["政治局会议提及"],              # +1
        "neutral": [],                              # 0
    },
    "policy_implementation": {
        # 政策落地节奏
        "strong_positive": [],   # +2：连续2次以上落地
        "positive": [],          # +1：单次落地
        "neutral": [],           # 0：无新政策
    },
}

_POLICY_TRIGGER_THRESHOLDS = {
    "strong_turn": 7,    # 总分≥7：强转向预期
    "marginal": 5,       # 5-6：边际宽松
    # ≤4：无转向
}


def calculate_policy_score_from_text(
    media_keywords: Optional[List[str]] = None,
    state_council_freq_change: int = 0,   # 相对正常的频次变化：+2/+1/0/-1
    pboc_keywords: Optional[List[str]] = None,
    top_meeting_signal: str = "none",       # "super" / "mentioned" / "none"
    implementation_count: int = 0,          # 当期落地政策次数：0/1/2+
) -> Dict[str, Any]:
    """
    根据政策文本/数据计算政策预期打分卡。

    Args:
        media_keywords: 官方媒体近期的政策相关关键词列表
        state_council_freq_change: 国常会频次相对变化（+2/+1/0/-1）
        pboc_keywords: 央行货政报告/公告关键词列表
        top_meeting_signal: 高层会议信号（"super"/"mentioned"/"none"）
        implementation_count: 当期新政策落地次数（0/1/2+）

    Returns:
        {
            "total_score": int,          # 0-10
            "level": str,                 # "strong_turn"/"marginal"/"no_turn"
            "adjustment": int,            # 调节幅度：+1/0/-1
            "items": {
                "media_wording": int,
                "state_council": int,
                "pboc_statement": int,
                "top_meeting": int,
                "implementation": int,
            }
        }
    """
    scores = {}

    # 1. 官方媒体措辞
    if media_keywords:
        kw_str = "".join(media_keywords)
        if any(k in kw_str for k in _POLICY_SCORING_RULES["media_wording"]["strong_positive"]):
            scores["media_wording"] = 2
        elif any(k in kw_str for k in _POLICY_SCORING_RULES["media_wording"]["positive"]):
            scores["media_wording"] = 1
        elif any(k in kw_str for k in _POLICY_SCORING_RULES["media_wording"]["negative"]):
            scores["media_wording"] = -1
        else:
            scores["media_wording"] = 0
    else:
        scores["media_wording"] = 0

    # 2. 国常会频次
    if state_council_freq_change >= 2:
        scores["state_council"] = 2
    elif state_council_freq_change == 1:
        scores["state_council"] = 1
    elif state_council_freq_change <= -1:
        scores["state_council"] = -1
    else:
        scores["state_council"] = 0

    # 3. 央行措辞
    if pboc_keywords:
        kw_str = "".join(pboc_keywords)
        if any(k in kw_str for k in _POLICY_SCORING_RULES["pboc_statement"]["strong_positive"]):
            scores["pboc_statement"] = 2
        elif any(k in kw_str for k in _POLICY_SCORING_RULES["pboc_statement"]["positive"]):
            scores["pboc_statement"] = 1
        elif any(k in kw_str for k in _POLICY_SCORING_RULES["pboc_statement"]["negative"]):
            scores["pboc_statement"] = -1
        else:
            scores["pboc_statement"] = 0
    else:
        scores["pboc_statement"] = 0

    # 4. 高层会议信号
    if top_meeting_signal == "super":
        scores["top_meeting"] = 2
    elif top_meeting_signal == "mentioned":
        scores["top_meeting"] = 1
    else:
        scores["top_meeting"] = 0

    # 5. 政策落地节奏
    if implementation_count >= 2:
        scores["implementation"] = 2
    elif implementation_count == 1:
        scores["implementation"] = 1
    else:
        scores["implementation"] = 0

    total = sum(scores.values())
    total = max(0, min(10, total))  # 限制在0-10

    if total >= _POLICY_TRIGGER_THRESHOLDS["strong_turn"]:
        level = "strong_turn"
        adjustment = 1
    elif total >= _POLICY_TRIGGER_THRESHOLDS["marginal"]:
        level = "marginal"
        adjustment = 0
    else:
        level = "no_turn"
        adjustment = -1

    return {
        "total_score": total,
        "level": level,
        "adjustment": adjustment,
        "items": scores,
    }


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
    
    # 政策维度（使用框架原文打分卡 V3.x）
    if "policy" in indicators and indicators["policy"]:
        p = indicators["policy"]
        # 优先使用量化打分卡结果
        policy_score_result = p.get("score_result")
        if policy_score_result:
            raw = policy_score_result["total_score"]
            z_score = (raw - 5) / 2.5  # 以5为均值、2.5为标准差的标准化
            direction_map = {"strong_turn": "easy", "marginal": "easy", "no_turn": "neutral"}
            direction = direction_map.get(policy_score_result["level"], "neutral")
        else:
            # 降级：使用宽松信号标记
            raw = None
            z_score = 0
            direction = "easy" if p.get("easing_signal") else "neutral"
        dimensions["policy"] = {
            "raw": raw,
            "z_score": z_score,
            "direction": direction,
            "indicators": p,
            "score_detail": policy_score_result,
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
    
    # 地缘政治评分（通道6专用）
    # 框架内部计算变量 — 基于 NLP 事件追踪 / 地缘风险评估
    # 当前 NLP 模块未就绪时使用中性默认值 5.0
    # TODO: 接入 NLP 管道, 通过分析新华社/人民日报/FOMC 声明生成动态评分
    geo_score = cross_metrics.get("geopolitical_score")
    if geo_score is None:
        geo_score = 5.0  # 中性默认，无地缘冲击
    signals["geopolitical"] = {
        "raw": geo_score,
        "z_score": (geo_score - 5.0) / 2.5,  # 以5为均值、2.5为标准差
        "direction": "negative" if geo_score > 5.0 else "neutral",
    }
    
    # 全球PMI（通道5备用数据）
    if "global_pmi" in cross_metrics:
        g_pmi = cross_metrics["global_pmi"]
        signals["global_pmi"] = {
            "raw": g_pmi,
            "z_score": _estimate_z_score(g_pmi, mean=50, std=2),
            "direction": "positive" if g_pmi > 50 else "negative",
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

        # 框架原文分级阈值（requirement.md 第79-90行）：
        #   通道1/5: 0.5σ 触发（更敏感）
        #   通道2/3/4: 1.0σ 触发
        #   通道6: 地缘事件评分超过阈值
        _CHANNEL_TRIGGER_THRESHOLDS = {
            1: 0.5,   # 利差→资本流→A股
            2: 1.0,   # 美元→大宗→PPI→周期股
            3: 1.0,   # 美联储→风险偏好→港股
            4: 1.0,   # 中国信贷→全球大宗
            5: 0.5,   # 全球PMI→中国出口
            6: None,  # 地缘事件，独立打分
        }

        if channel_id == 1:  # 利差→资本流→A股
            spread_z = cross_signals.get("cn_us_10y_spread", {}).get("z_score", 0)
            threshold = _CHANNEL_TRIGGER_THRESHOLDS[1]
            triggered = abs(spread_z) > threshold
            strength = min(abs(spread_z) / 2.0, 1.0) if triggered else 0
            # 利差走阔（正z）→ 北向流入 → 正向；利差收窄（负z）→ 负向
            direction = "positive" if spread_z > 0 else ("negative" if spread_z < 0 else "neutral")

        elif channel_id == 2:  # 美元→大宗→PPI→周期股
            dxy_z = cross_signals.get("dxy", {}).get("z_score", 0)
            threshold = _CHANNEL_TRIGGER_THRESHOLDS[2]
            triggered = abs(dxy_z) > threshold
            strength = min(abs(dxy_z) / 2.0, 1.0) if triggered else 0
            # 美元强势（正z）→ 大宗承压 → 负向A股周期股
            direction = "negative" if dxy_z > 0 else ("positive" if dxy_z < 0 else "neutral")

        elif channel_id == 3:  # 美联储→风险偏好→港股
            # 美国实际利率 = TIPS收益率（近似用市场定价维度）
            us_real_rate_z = us_5d.get("market_pricing", {}).get("z_score", 0)
            threshold = _CHANNEL_TRIGGER_THRESHOLDS[3]
            triggered = abs(us_real_rate_z) > threshold
            strength = min(abs(us_real_rate_z) / 2.0, 1.0) if triggered else 0
            direction = "negative" if us_real_rate_z > 0 else ("positive" if us_real_rate_z < 0 else "neutral")

        elif channel_id == 4:  # 中国信贷→全球大宗
            # 社融脉冲（近似用流动性维度 z-score）
            cn_credit_z = china_5d.get("liquidity", {}).get("z_score", 0)
            threshold = _CHANNEL_TRIGGER_THRESHOLDS[4]
            triggered = abs(cn_credit_z) > threshold
            strength = min(abs(cn_credit_z) / 2.0, 1.0) if triggered else 0
            # 社融扩张（正z）→ 全球大宗正需求 → 正向
            direction = "positive" if cn_credit_z > 0 else ("negative" if cn_credit_z < 0 else "neutral")

        elif channel_id == 5:  # 全球PMI→中国出口
            global_growth_z = us_5d.get("growth", {}).get("z_score", 0)
            threshold = _CHANNEL_TRIGGER_THRESHOLDS[5]
            triggered = abs(global_growth_z) > threshold
            strength = min(abs(global_growth_z) / 2.0, 1.0) if triggered else 0
            # 全球PMI高（正z）→ 中国出口正增长 → 正向
            direction = "positive" if global_growth_z > 0 else ("negative" if global_growth_z < 0 else "neutral")

        elif channel_id == 6:  # 地缘政治→风险溢价
            # 地缘评分由框架内部生成 (NLP + 事件追踪), 数据层不提供
            geopolitical_score = cross_signals.get("geopolitical", {}).get("raw", 5.0)
            triggered = geopolitical_score > 5.0  # 框架：评分超过阈值
            strength = geopolitical_score / 10.0 if triggered else 0
            direction = "negative" if triggered else "neutral"

        else:
            triggered = False
            strength = 0
            direction = "neutral"

        channels.append({
            "id": channel_id,
            "name": channel_name,
            "triggered": triggered,
            "strength": strength,
            "direction": direction,
            "threshold_used": _CHANNEL_TRIGGER_THRESHOLDS.get(channel_id),
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
