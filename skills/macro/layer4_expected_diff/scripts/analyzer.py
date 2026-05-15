"""
Layer 4: 预期差信号引擎——计算"实际状态vs市场定价"的偏差

核心Alpha来源：预期差驱动。
"""

from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import numpy as np

from utils.constants import (
    SIGNAL_DECAY_PARAMS,
    SIGNAL_INTENSITY_THRESHOLDS,
)
from utils.signal_utils import (
    build_layer_signal,
    calculate_signal_intensity,
)


def analyze_expected_diff(
    layer1_output: Dict[str, Any],
    layer3_output: Dict[str, Any],
    cesi_data: Optional[Dict[str, float]] = None,
    historical_signals: Optional[List[Dict]] = None,
) -> Dict[str, Any]:
    """
    计算预期差信号。
    
    Args:
        layer1_output: Layer 1 输出（实际基本面状态）
        layer3_output: Layer 3 输出（市场定价）
        cesi_data: 花旗经济意外指数数据（可选）
            - china_cesi: 中国CESI
            - us_cesi: 美国CESI
        historical_signals: 历史信号列表（用于衰减和复核检查）
    
    Returns:
        预期差信号分析结果
    """
    # Step 1: 计算类型A信号（高频意外指数）
    type_a_signals = calculate_type_a_signals(cesi_data)
    
    # Step 2: 计算类型B信号（基本面vs市场定价）
    type_b_signals = calculate_type_b_signals(layer1_output, layer3_output)
    
    # Step 3: 计算类型C信号（跨国预期差）
    type_c_signals = calculate_type_c_signals(layer1_output, layer3_output)
    
    # Step 4: 应用信号衰减
    all_signals = apply_signal_decay(
        type_a_signals + type_b_signals + type_c_signals,
        historical_signals
    )
    
    # Step 5: 检查信号复核
    review_result = check_signal_review(all_signals, historical_signals)
    
    # 构建层输出
    layer_output = build_layer_signal(
        layer_name="layer4",
        analysis_result={
            "type_a_signals": type_a_signals,
            "type_b_signals": type_b_signals,
            "type_c_signals": type_c_signals,
            "all_signals": all_signals,
            "review_status": review_result,
        },
        direction=_determine_final_direction(all_signals),
        confidence=_calculate_final_confidence(all_signals),
        reasoning=f"有效信号数: {len([s for s in all_signals if s['intensity'] >= 50])}",
    )
    
    return {
        "type_a_signals": type_a_signals,
        "type_b_signals": type_b_signals,
        "type_c_signals": type_c_signals,
        "all_signals": all_signals,
        "review_status": review_result,
        "layer_output": layer_output,
    }


def calculate_type_a_signals(cesi_data: Optional[Dict[str, float]]) -> List[Dict]:
    """计算类型A信号：高频意外指数。"""
    signals = []
    
    if cesi_data:
        # 中国CESI
        china_cesi = cesi_data.get("china_cesi")
        if china_cesi is not None:
            intensity = abs(china_cesi) / 2 * 100  # 归一化到0-100
            signals.append({
                "type": "A",
                "name": "中国数据意外",
                "direction": "bullish" if china_cesi > 0 else "bearish",
                "raw_value": china_cesi,
                "intensity": min(100, intensity),
                "percentile": min(100, intensity),
                "validity_weeks": SIGNAL_DECAY_PARAMS["type_a"]["initial_validity_weeks"],
                "decay_type": "exponential",
                "decay_rate": SIGNAL_DECAY_PARAMS["type_a"]["weekly_decay_rate"],
            })
        
        # 美国CESI
        us_cesi = cesi_data.get("us_cesi")
        if us_cesi is not None:
            intensity = abs(us_cesi) / 2 * 100
            signals.append({
                "type": "A",
                "name": "美国数据意外",
                "direction": "bullish" if us_cesi > 0 else "bearish",
                "raw_value": us_cesi,
                "intensity": min(100, intensity),
                "percentile": min(100, intensity),
                "validity_weeks": SIGNAL_DECAY_PARAMS["type_a"]["initial_validity_weeks"],
                "decay_type": "exponential",
                "decay_rate": SIGNAL_DECAY_PARAMS["type_a"]["weekly_decay_rate"],
            })
    
    return signals


def calculate_type_b_signals(
    layer1: Dict[str, Any],
    layer3: Dict[str, Any]
) -> List[Dict]:
    """计算类型B信号：基本面vs市场定价。"""
    signals = []
    
    # 增长预期差
    china_cai = layer1.get("china_cai", {}).get("z_score", 0)
    rate_implied = layer3.get("rate_pricing", {}).get("cn_term_spread", {}).get("z_score", 0)
    growth_diff = china_cai - rate_implied
    
    if abs(growth_diff) > 0.5:
        direction = "bullish" if growth_diff > 0 else "bearish"
        intensity = abs(growth_diff) / 2 * 100
        signals.append({
            "type": "B",
            "name": "中国增长预期差",
            "direction": direction,
            "actual": china_cai,
            "implied": rate_implied,
            "diff": growth_diff,
            "intensity": min(100, intensity),
            "percentile": min(100, intensity),
            "validity_months": SIGNAL_DECAY_PARAMS["type_b"]["initial_validity_months"],
            "decay_type": "exponential",
            "decay_rate": SIGNAL_DECAY_PARAMS["type_b"]["monthly_decay_rate"],
            "related_assets": ["A股", "商品"],
        })
    
    # 通胀预期差
    china_inflation = layer1.get("china_inflation", {}).get("z_score", 0)
    # 简化：使用ERP百分位作为通胀定价代理
    erp_pct = layer3.get("valuation_pricing", {}).get("csi300_erp", {}).get("percentile", 50)
    implied_inflation = (50 - erp_pct) / 10  # ERP低=通胀预期高
    inflation_diff = china_inflation - implied_inflation
    
    if abs(inflation_diff) > 0.5:
        direction = "bullish" if inflation_diff > 0 else "bearish"
        intensity = abs(inflation_diff) / 2 * 100
        signals.append({
            "type": "B",
            "name": "中国通胀预期差",
            "direction": direction,
            "actual": china_inflation,
            "implied": implied_inflation,
            "diff": inflation_diff,
            "intensity": min(100, intensity),
            "percentile": min(100, intensity),
            "validity_months": SIGNAL_DECAY_PARAMS["type_b"]["initial_validity_months"],
            "decay_type": "exponential",
            "decay_rate": SIGNAL_DECAY_PARAMS["type_b"]["monthly_decay_rate"],
            "related_assets": ["债券", "商品"],
        })
    
    # 美国增长预期差
    us_cai = layer1.get("us_cai", {}).get("z_score", 0)
    us_rate_implied = layer3.get("rate_pricing", {}).get("us_term_spread", {}).get("z_score", 0)
    us_growth_diff = us_cai - us_rate_implied
    
    if abs(us_growth_diff) > 0.5:
        direction = "bullish" if us_growth_diff > 0 else "bearish"
        intensity = abs(us_growth_diff) / 2 * 100
        signals.append({
            "type": "B",
            "name": "美国增长预期差",
            "direction": direction,
            "actual": us_cai,
            "implied": us_rate_implied,
            "diff": us_growth_diff,
            "intensity": min(100, intensity),
            "percentile": min(100, intensity),
            "validity_months": SIGNAL_DECAY_PARAMS["type_b"]["initial_validity_months"],
            "decay_type": "exponential",
            "decay_rate": SIGNAL_DECAY_PARAMS["type_b"]["monthly_decay_rate"],
            "related_assets": ["美股"],
        })
    
    return signals


def calculate_type_c_signals(
    layer1: Dict[str, Any],
    layer3: Dict[str, Any]
) -> List[Dict]:
    """计算类型C信号：跨国预期差。"""
    signals = []
    
    # 中美增长预期差
    china_cai = layer1.get("china_cai", {}).get("z_score", 0)
    us_cai = layer1.get("us_cai", {}).get("z_score", 0)
    growth_diff = china_cai - us_cai
    
    # 中国市场定价增长 vs 美国市场定价增长
    cn_rate = layer3.get("rate_pricing", {}).get("cn_term_spread", {}).get("z_score", 0)
    us_rate = layer3.get("rate_pricing", {}).get("us_term_spread", {}).get("z_score", 0)
    pricing_diff = cn_rate - us_rate
    
    cn_us_growth_diff = growth_diff - pricing_diff
    
    if abs(cn_us_growth_diff) > 0.5:
        direction = "bullish" if cn_us_growth_diff > 0 else "bearish"
        intensity = abs(cn_us_growth_diff) / 2 * 100
        signals.append({
            "type": "C",
            "name": "中美增长预期差",
            "direction": direction,
            "actual_diff": growth_diff,
            "pricing_diff": pricing_diff,
            "net_diff": cn_us_growth_diff,
            "intensity": min(100, intensity),
            "percentile": min(100, intensity),
            "validity_months": SIGNAL_DECAY_PARAMS["type_c"]["initial_validity_months"],
            "decay_type": "exponential",
            "decay_rate": SIGNAL_DECAY_PARAMS["type_c"]["monthly_decay_rate"],
            "related_assets": ["A股", "美股"],
            "related_trades": ["超配A股/低配美股" if direction == "bullish" else "超配美股/低配A股"],
        })
    
    # 中美流动性差
    china_fci = layer1.get("china_fci", {}).get("z_score", 0)
    us_fci = layer1.get("us_fci", {}).get("z_score", 0)
    fci_diff = china_fci - us_fci
    
    if abs(fci_diff) > 1.0:
        direction = "bullish" if fci_diff < 0 else "bearish"  # 中国FCI低=宽松
        intensity = abs(fci_diff) / 2 * 100
        signals.append({
            "type": "C",
            "name": "中美流动性差",
            "direction": direction,
            "china_fci": china_fci,
            "us_fci": us_fci,
            "diff": fci_diff,
            "intensity": min(100, intensity),
            "percentile": min(100, intensity),
            "validity_months": SIGNAL_DECAY_PARAMS["type_c"]["initial_validity_months"],
            "decay_type": "exponential",
            "decay_rate": SIGNAL_DECAY_PARAMS["type_c"]["monthly_decay_rate"],
            "related_assets": ["新兴市场", "全球资本流向"],
        })
    
    return signals


def apply_signal_decay(
    signals: List[Dict],
    historical_signals: Optional[List[Dict]] = None
) -> List[Dict]:
    """应用信号衰减。"""
    now = datetime.now()
    decayed_signals = []
    
    for signal in signals:
        # 计算经过的时间
        if historical_signals:
            # 查找该信号的历史记录
            matching = [h for h in historical_signals if h.get("name") == signal.get("name")]
            if matching:
                last_date = matching[0].get("date")
                if last_date:
                    last_time = datetime.fromisoformat(last_date) if isinstance(last_date, str) else last_date
                    periods = (now - last_time).days / 7  # 假设周频
                else:
                    periods = 0
            else:
                periods = 0
        else:
            periods = 0
        
        # 计算衰减后强度
        if signal.get("decay_type") == "exponential":
            decay_rate = signal.get("decay_rate", 0.25)
            initial = signal.get("intensity", 50)
            decayed = calculate_signal_intensity(
                initial_intensity=initial,
                decay_type="exponential",
                periods_elapsed=periods,
                decay_rate=decay_rate,
            )
        else:
            decayed = signal.get("intensity", 50)
        
        decayed_signals.append({
            **signal,
            "decayed_intensity": decayed,
            "periods_elapsed": periods,
            "status": _get_signal_status(decayed),
        })
    
    return decayed_signals


def check_signal_review(
    signals: List[Dict],
    historical_signals: Optional[List[Dict]]
) -> Dict[str, Any]:
    """检查信号是否需要复核。"""
    if not historical_signals:
        return {"needs_review": False, "reason": ""}
    
    # 统计反向信号
    reverse_count = 0
    for signal in signals:
        for hist in historical_signals:
            if hist.get("name") == signal.get("name"):
                if hist.get("direction") != signal.get("direction"):
                    reverse_count += 1
                    break
    
    # 连续2周反向触发复核
    if reverse_count >= 2:
        return {
            "needs_review": True,
            "reason": "连续反向信号触发复核",
            "reverse_signals": reverse_count,
        }
    
    # 连续3周反向强制降级
    if reverse_count >= 3:
        return {
            "needs_review": True,
            "reason": "连续3周反向，信号强制降级",
            "action": "降级至弱信号",
            "reverse_signals": reverse_count,
        }
    
    return {"needs_review": False, "reason": ""}


def _determine_final_direction(signals: List[Dict]) -> str:
    """确定最终方向。"""
    bullish_count = sum(1 for s in signals if s.get("decayed_intensity", 0) >= 50 and s.get("direction") == "bullish")
    bearish_count = sum(1 for s in signals if s.get("decayed_intensity", 0) >= 50 and s.get("direction") == "bearish")
    
    if bullish_count > bearish_count:
        return "bullish"
    elif bearish_count > bullish_count:
        return "bearish"
    else:
        return "neutral"


def _calculate_final_confidence(signals: List[Dict]) -> float:
    """计算最终置信度。"""
    strong_signals = [s for s in signals if s.get("decayed_intensity", 0) >= 80]
    if len(strong_signals) >= 3:
        return 0.9
    elif len(strong_signals) >= 1:
        return 0.7
    elif signals:
        return 0.5
    else:
        return 0.3


def _get_signal_status(intensity: float) -> str:
    """获取信号状态。"""
    if intensity >= 80:
        return "强信号"
    elif intensity >= 50:
        return "有效信号"
    else:
        return "弱信号"
