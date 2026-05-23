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
    layer25_output: Optional[Dict[str, Any]] = None,
    cesi_data: Optional[Dict[str, float]] = None,
    historical_signals: Optional[List[Dict]] = None,
) -> Dict[str, Any]:
    """
    计算预期差信号。
    
    Args:
        layer1_output: Layer 1 输出（实际基本面状态）
        layer3_output: Layer 3 输出（市场定价）
        layer25_output: Layer 2.5 输出（枢纽变量：全球三角、USD/CNH方向、铜金比）
        cesi_data: 花旗经济意外指数数据（可选）
        historical_signals: 历史信号列表（用于衰减和复核检查）
    
    Returns:
        预期差信号分析结果
    """
    # Step 1: 计算类型A信号（高频意外指数）
    type_a_signals = calculate_type_a_signals(cesi_data)
    
    # Step 2: 计算类型B信号（基本面vs市场定价）
    type_b_signals = calculate_type_b_signals(layer1_output, layer3_output)
    
    # Step 3: 计算类型C信号（跨国预期差，含Layer 2.5枢纽变量信号）
    type_c_signals = calculate_type_c_signals(layer1_output, layer3_output, layer25_output)
    
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
    layer3: Dict[str, Any],
    layer25_output: Optional[Dict[str, Any]] = None,
) -> List[Dict]:
    """
    计算类型C信号：跨国预期差。
    
    框架设计（requirement.md 第773-781行）：
    - 跨国预期差（中美增长/流动性等）
    - 美元-大宗联动信号（Layer 2.5全球宏观三角状态切换）
    - USD/CNH贬值压力信号
    """
    signals = []
    
    # Layer 2.5 枢纽变量输出（框架第982-984行列出的三条直接信号）
    if layer25_output:
        macro_triangle = layer25_output.get("macro_triangle", {})
        cnh_direction = layer25_output.get("cnh_direction", {})
        commodity_signals = layer25_output.get("commodity_signals", [])
        
        # 信号1：全球宏观三角（框架第982行）
        triangle = macro_triangle.get("triangle")
        if triangle in ("global_tightening", "global_easing", "stagflation", "deflation"):
            # 全球紧缩三角：整体降低风险资产、增加黄金
            if triangle == "global_tightening":
                direction = "bearish"
                triangle_signal = "全球紧缩三角：外资流出、新兴市场承压"
                related_assets = ["csi300_500", "us_assets"]
                related_assets_zh = ["A股", "美股"]
            elif triangle == "global_easing":
                direction = "bullish"
                triangle_signal = "全球宽松三角：外资流入、风险资产受益"
                related_assets = ["csi300_500", "nh_industrial"]
                related_assets_zh = ["A股", "商品"]
            elif triangle == "stagflation":
                direction = "neutral"
                triangle_signal = "滞胀三角：黄金最优、风险资产承压"
                related_assets = ["gold"]
                related_assets_zh = ["黄金"]
            else:  # deflation
                direction = "neutral"
                triangle_signal = "通缩三角：债券和高股息最优"
                related_assets = ["cn_gov_bond"]
                related_assets_zh = ["债券"]
            
            # 铜金比z-score作为强度代理（框架第668行：|z|>1.5强信号）
            copper_gold_signal = next(
                (s for s in commodity_signals if s.get("name") == "铜金比"), {}
            )
            copper_gold_z = abs(copper_gold_signal.get("z_score", 0))
            # z>2.0→极强信号强度100, z>1.5→强信号强度80
            if copper_gold_z > 2.0:
                intensity = 100.0
            elif copper_gold_z > 1.5:
                intensity = 80.0
            else:
                intensity = 50.0
            
            signals.append({
                "type": "C",
                "name": "美元-大宗联动信号",
                "source": "Layer 2.5 全球宏观三角",
                "direction": direction,
                "triangle": triangle,
                "macro_meaning": triangle_signal,
                "intensity": intensity,
                "percentile": intensity,
                "validity_months": SIGNAL_DECAY_PARAMS["type_c"]["initial_validity_months"],
                "decay_type": "exponential",
                "decay_rate": SIGNAL_DECAY_PARAMS["type_c"]["monthly_decay_rate"],
                "related_assets": related_assets_zh,
            })
        
        # 信号2：USD/CNH贬值压力（框架第984行）
        cnh_score = cnh_direction.get("score", 0)
        if abs(cnh_score) > 0.5:
            # score<0 → 贬值压力 → bearish for A股/港股, bullish for gold
            if cnh_score < -0.5:
                direction = "bearish"
                cnh_signal = "人民币贬值压力：港股和外资重仓股承压、出口股和黄金受益"
                related_assets = ["港股", "外资重仓股", "黄金", "出口股"]
            else:
                direction = "bullish"
                cnh_signal = "人民币升值压力：外资重仓股受益、黄金承压"
                related_assets = ["外资重仓股", "黄金"]
            
            intensity = min(100, abs(cnh_score) / 1.0 * 60 + 40)
            signals.append({
                "type": "C",
                "name": "USD/CNH汇率信号",
                "source": "Layer 2.5 汇率分析",
                "direction": direction,
                "cnh_score": cnh_score,
                "macro_meaning": cnh_signal,
                "intensity": intensity,
                "percentile": intensity,
                "validity_months": SIGNAL_DECAY_PARAMS["type_c"]["initial_validity_months"],
                "decay_type": "exponential",
                "decay_rate": SIGNAL_DECAY_PARAMS["type_c"]["monthly_decay_rate"],
                "related_assets": related_assets,
            })
        
        # 信号3：铜金比极端低位+增长信号（框架第983行）
        copper_gold_signal = next(
            (s for s in commodity_signals if s.get("name") == "铜金比"), {}
        )
        copper_gold_z = copper_gold_signal.get("z_score", 0)
        if copper_gold_z < -1.5:
            # 铜金比极端低位 → 周期股相对防御股被低估
            # 需要叠加增长信号（Layer 1 CAI > 0）才有效
            china_cai = layer1.get("china_cai", {}).get("z_score", 0)
            if china_cai > 0:
                direction = "bullish"
                signal_text = f"铜金比极端低估(z={copper_gold_z:.2f})，叠加中国CAI确认增长，周期股超配"
                related_assets = ["周期股", "防御股"]
            else:
                direction = "neutral"
                signal_text = f"铜金比极端低估(z={copper_gold_z:.2f})，但增长信号不足，不构成周期股信号"
                related_assets = []
            
            intensity = min(100, abs(copper_gold_z) * 30)
            if related_assets:
                signals.append({
                    "type": "C",
                    "name": "铜金比极端低估信号",
                    "source": "Layer 2.5 大宗商品信号",
                    "direction": direction,
                    "copper_gold_z": copper_gold_z,
                    "china_cai": china_cai,
                    "macro_meaning": signal_text,
                    "intensity": intensity,
                    "percentile": intensity,
                    "validity_months": SIGNAL_DECAY_PARAMS["type_c"]["initial_validity_months"],
                    "decay_type": "exponential",
                    "decay_rate": SIGNAL_DECAY_PARAMS["type_c"]["monthly_decay_rate"],
                    "related_assets": related_assets,
                })
    
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
