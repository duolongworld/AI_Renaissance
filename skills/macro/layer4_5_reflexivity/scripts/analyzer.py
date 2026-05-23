"""
Layer 4.5: 反身性与元认知层（V3.1新增）

监测共识拥挤程度和框架范式稳定性，对信号强度进行三重修正。
"""

from typing import Dict, List, Any, Optional
import numpy as np

from utils.constants import (
    REFLEXIVITY_PRESSURE_WEIGHTS,
    REFLEXIVITY_PRESSURE_THRESHOLDS,
    LIFECYCLE_COEFFICIENT,
    PARADIGM_STABILITY_COEFFICIENT,
)
from utils.signal_utils import (
    build_layer_signal,
    calculate_reflexivity_coefficient,
    get_pressure_level,
)


def analyze_reflexivity(
    layer4_signals: List[Dict],
    crowding_data: Optional[Dict[str, float]] = None,
    correlation_data: Optional[Dict[str, List[float]]] = None,
    policy_text_analysis: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    分析反身性与元认知。
    
    Args:
        layer4_signals: Layer 4 输出的信号列表
        crowding_data: 反身性压力计数据（可选）
            - signal_crowding: 信号拥挤度
            - position_concentration: 仓位集中度
            - self_fulfilling_index: 自我实现指数
            - cross_framework_consensus: 跨框架一致性
        correlation_data: 范式稳定性数据（可选）
            - copper_gold_pmi_corr: 铜金比与PMI相关性
            - spread_growth_corr: 利差与增长相关性
            - erp_growth_corr: ERP与增长相关性
        policy_text_analysis: 政策框架分析（可选）
    
    Returns:
        反身性分析结果
    """
    # Step 1: 计算反身性压力计
    pressure_meter = calculate_reflexivity_pressure_meter(crowding_data)
    
    # Step 2: 判定范式稳定性
    paradigm_stability = determine_paradigm_stability(
        correlation_data, policy_text_analysis
    )
    
    # Step 3: 判定逻辑生命周期
    lifecycle = determine_logic_lifecycle(layer4_signals, crowding_data)
    
    # Step 4: 计算三重修正后信号强度
    corrected_signals = apply_triple_correction(
        layer4_signals, pressure_meter, paradigm_stability, lifecycle
    )
    
    # Step 5: 检查是否触发人类裁决接口
    human_intervention = check_human_intervention(
        pressure_meter, paradigm_stability
    )
    
    # 构建层输出
    layer_output = build_layer_signal(
        layer_name="layer4_5",
        analysis_result={
            "pressure_meter": pressure_meter,
            "paradigm_stability": paradigm_stability,
            "logic_lifecycle": lifecycle,
            "corrected_signals": corrected_signals,
            "human_intervention": human_intervention,
        },
        direction="neutral",
        confidence=0.8,
        reasoning=f"反身性压力: {pressure_meter.get('level', 'unknown')}, 范式: {paradigm_stability.get('status', 'unknown')}",
    )
    
    return {
        "pressure_meter": pressure_meter,
        "paradigm_stability": paradigm_stability,
        "logic_lifecycle": lifecycle,
        "corrected_signals": corrected_signals,
        "human_intervention": human_intervention,
        "layer_output": layer_output,
    }


def calculate_reflexivity_pressure_meter(
    data: Optional[Dict[str, float]]
) -> Dict[str, Any]:
    """
    计算反身性压力计。
    
    四大压力指标：
    1. 信号拥挤度 (0-25)
    2. 仓位集中度 (0-25)
    3. 自我实现指数 (0-25)
    4. 跨框架一致性 (0-25)
    
    满分100分。
    """
    if not data:
        return {
            "total_score": 0,
            "level": "green",
            "sub_scores": {},
            "needs_attention": False,
        }
    
    sub_scores = {}
    total_score = 0
    
    # 1. 信号拥挤度
    crowding = data.get("signal_crowding", 0)
    crowding_score = min(25, crowding / 2)  # 假设50%为满分
    sub_scores["signal_crowding"] = {
        "raw": crowding,
        "score": crowding_score,
        "level": "high" if crowding > 50 else ("medium" if crowding > 30 else "low"),
    }
    total_score += crowding_score
    
    # 2. 仓位集中度
    position = data.get("position_concentration", 0)
    position_score = min(25, abs(position) / 2 * 25)  # z-score > 2 = 满分
    sub_scores["position_concentration"] = {
        "raw": position,
        "score": position_score,
        "level": "high" if abs(position) > 2.0 else ("medium" if abs(position) > 1.5 else "low"),
    }
    total_score += position_score
    
    # 3. 自我实现指数
    self_fulfilling = data.get("self_fulfilling_index", 0)
    sf_score = min(25, self_fulfilling / 2)  # 假设60%=满分
    sub_scores["self_fulfilling_index"] = {
        "raw": self_fulfilling,
        "score": sf_score,
        "level": "high" if self_fulfilling > 60 else ("medium" if self_fulfilling > 40 else "low"),
    }
    total_score += sf_score
    
    # 4. 跨框架一致性
    consensus = data.get("cross_framework_consensus", 0)
    cf_score = min(25, consensus / 2)  # 假设70%=满分
    sub_scores["cross_framework_consensus"] = {
        "raw": consensus,
        "score": cf_score,
        "level": "high" if consensus > 70 else ("medium" if consensus > 50 else "low"),
    }
    total_score += cf_score
    
    # 判定等级
    level = get_pressure_level(total_score)
    
    return {
        "total_score": total_score,
        "level": level,
        "coefficient": calculate_reflexivity_coefficient(total_score),
        "sub_scores": sub_scores,
        "needs_attention": level in ["orange", "red"],
    }


def determine_paradigm_stability(
    correlation_data: Optional[Dict[str, List[float]]],
    policy_analysis: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    判定范式稳定性。
    
    三大代理指标：
    1. 跨资产相关性结构断裂
    2. 政策框架措辞质变
    3. 全球资本流动结构突变
    """
    triggered_count = 0
    triggers = []
    
    # 1. 相关性断裂
    if correlation_data:
        # 检查铜金比-PMI相关性是否断裂
        corr_copper_pmi = correlation_data.get("copper_gold_pmi_corr", [])
        if len(corr_copper_pmi) >= 2:
            recent = corr_copper_pmi[-1]
            past = corr_copper_pmi[-6] if len(corr_copper_pmi) >= 6 else corr_copper_pmi[0]
            if abs(recent) < 0.2 and abs(past) > 0.6:
                triggered_count += 1
                triggers.append("铜金比-PMI相关性断裂")
        
        # 检查利差-增长相关性
        corr_spread_growth = correlation_data.get("spread_growth_corr", [])
        if len(corr_spread_growth) >= 2:
            recent = corr_spread_growth[-1]
            past = corr_spread_growth[-6] if len(corr_spread_growth) >= 6 else corr_spread_growth[0]
            if abs(recent) < 0.2 and abs(past) > 0.6:
                triggered_count += 1
                triggers.append("利差-增长相关性断裂")
    
    # 2. 政策框架质变（简化判断）
    if policy_analysis:
        framework_change = policy_analysis.get("framework_change", False)
        if framework_change:
            triggered_count += 1
            triggers.append("政策框架质变")
    
    # 判定稳定性
    if triggered_count >= 2:
        status = "shift"
    elif triggered_count == 1:
        status = "shaken"
    else:
        status = "stable"
    
    return {
        "status": status,
        "coefficient": PARADIGM_STABILITY_COEFFICIENT.get(status, 1.0),
        "triggered_count": triggered_count,
        "triggers": triggers,
    }


def determine_logic_lifecycle(
    signals: List[Dict],
    crowding_data: Optional[Dict[str, float]]
) -> Dict[str, Any]:
    """
    判定逻辑生命周期。
    
    五个阶段：萌芽期、扩散期、共识期、透支期、崩塌期
    """
    if not signals:
        return {
            "stage": "embryonic",
            "coefficient": LIFECYCLE_COEFFICIENT["embryonic"],
            "confidence": 0.3,
        }
    
    # 简化判断逻辑
    # 实际实现需要更多数据支撑
    
    # 基于信号数量和拥挤度判断
    signal_count = len(signals)
    crowding = crowding_data.get("signal_crowding", 0) if crowding_data else 0
    
    if signal_count >= 5 and crowding > 70:
        stage = "beyond"
    elif signal_count >= 4 and crowding > 50:
        stage = "consensus"
    elif signal_count >= 3:
        stage = "diffusion"
    else:
        stage = "embryonic"
    
    return {
        "stage": stage,
        "coefficient": LIFECYCLE_COEFFICIENT.get(stage, 1.0),
        "confidence": 0.5,
        "signal_count": signal_count,
        "crowding": crowding,
    }


def apply_triple_correction(
    signals: List[Dict],
    pressure_meter: Dict[str, Any],
    paradigm_stability: Dict[str, Any],
    lifecycle: Dict[str, Any]
) -> List[Dict]:
    """
    应用三重修正到Layer 4信号。
    
    最终强度 = Layer 4 初始强度 × 逻辑生命周期修正 × 反身性压力修正 × 范式稳定性修正
    """
    pressure_coeff = pressure_meter.get("coefficient", 1.0)
    paradigm_coeff = paradigm_stability.get("coefficient", 1.0)
    lifecycle_coeff = lifecycle.get("coefficient", 1.0)
    
    corrected_signals = []
    for signal in signals:
        initial_intensity = signal.get("decayed_intensity", signal.get("intensity", 50))
        
        # 三重修正
        corrected = (
            initial_intensity *
            lifecycle_coeff *
            pressure_coeff *
            paradigm_coeff
        )
        
        corrected_signals.append({
            **signal,
            "initial_intensity": initial_intensity,
            "lifecycle_correction": lifecycle_coeff,
            "pressure_correction": pressure_coeff,
            "paradigm_correction": paradigm_coeff,
            "final_intensity": min(100, corrected),
            "correction_factor": lifecycle_coeff * pressure_coeff * paradigm_coeff,
        })
    
    return corrected_signals


def check_human_intervention(
    pressure_meter: Dict[str, Any],
    paradigm_stability: Dict[str, Any]
) -> Dict[str, Any]:
    """
    检查是否触发人类裁决接口。
    
    触发条件：
    1. 反身性压力得分 > 70（红色）
    2. 范式稳定性判定为"转移"
    3. 信号方向正确但压力计维持橙色以上（连续3周）
    """
    triggers = []
    
    # 条件1
    if pressure_meter.get("level") == "red":
        triggers.append("反身性压力红色")
    
    # 条件2
    if paradigm_stability.get("status") == "shift":
        triggers.append("范式转移")
    
    # 判定
    needs_intervention = len(triggers) > 0
    
    return {
        "needs_intervention": needs_intervention,
        "triggers": triggers,
        "action": "暂停Alpha执行，呈现观察结果" if needs_intervention else "正常执行",
    }
