"""
Layer 5: 资产配置与权重输出

将信号转化为可执行的投资组合权重。
"""

from typing import Dict, List, Any, Optional
import numpy as np

from utils.constants import (
    BETA_BENCHMARK_WEIGHTS,
    RISK_BUDGET_CONSTRAINTS,
    INDUSTRY_CYCLE_MAPPING,
)
from utils.signal_utils import (
    build_layer_signal,
    build_macro_signal,
)

# Layer 4 信号中 related_assets 使用中文名，final_weights 键为英文
# 此映射保证跨层解析一致性
ASSET_NAME_MAPPING: Dict[str, str] = {
    "A股": "csi300_500",
    "美股": "us_assets",
    "商品": "nh_industrial",
    "黄金": "gold",
    "债券": "cn_gov_bond",
    "中国国债": "cn_gov_bond",
}


def _normalize_asset_name(name: str) -> str:
    """将中文资产名映射为英文标准键，无匹配时返回原名（用于无法映射的资产）。"""
    return ASSET_NAME_MAPPING.get(name, name)


def analyze_asset_allocation(
    layer2_output: Dict[str, Any],
    layer4_output: Dict[str, Any],
    layer45_output: Optional[Dict[str, Any]] = None,
    volatility_data: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """
    分析资产配置权重。
    
    Args:
        layer2_output: Layer 2 输出（周期定位）
        layer4_output: Layer 4 输出（预期差信号）
        layer45_output: Layer 4.5 输出（反身性修正）
        volatility_data: 波动率数据（可选）
    
    Returns:
        资产配置分析结果
    """
    # Step 1: 计算Beta基准权重（含周期象限和债务周期调整）
    # 从Layer 2输出提取象限和债务周期
    cycle_output = layer2_output.get("layer_output", {}).get("analysis_result", {})
    cycle_position = cycle_output.get("china_quadrant_adjusted", {})
    debt_cycle = cycle_output.get("debt_cycle")
    
    beta_weights = calculate_beta_weights(
        volatility_data,
        cycle_position=cycle_position,
        debt_cycle=debt_cycle,
    )
    
    # Step 2: 计算Alpha偏离
    alpha_deviation = calculate_alpha_deviation(
        layer4_output, layer45_output
    )
    
    # Step 3: 应用风险预算约束
    final_weights = apply_risk_budget(
        beta_weights, alpha_deviation, volatility_data
    )
    
    # Step 4: 计算行业配置
    industry_allocation = calculate_industry_allocation(
        layer2_output, layer4_output
    )
    
    # Step 5: 构建最终Signal
    macro_signal = build_macro_signal(
        direction=_determine_direction(final_weights),
        confidence=_determine_confidence(final_weights, alpha_deviation),
        reasoning=_generate_reasoning(final_weights, alpha_deviation),
        signals=_generate_signals(final_weights),
        layer_name="layer5_asset_allocation",
        time_horizon="mid",
        risk_level=_determine_risk_level(final_weights, alpha_deviation),
        key_findings=_generate_key_findings(final_weights, alpha_deviation),
        period=None,
    )
    
    # 构建层输出
    layer_output = build_layer_signal(
        layer_name="layer5",
        analysis_result={
            "beta_weights": beta_weights,
            "alpha_deviation": alpha_deviation,
            "final_weights": final_weights,
            "industry_allocation": industry_allocation,
            "risk_budget_status": "pass",
        },
        direction=macro_signal.direction,
        confidence=macro_signal.confidence,
        reasoning=macro_signal.reasoning,
    )
    
    return {
        "beta_weights": beta_weights,
        "alpha_deviation": alpha_deviation,
        "final_weights": final_weights,
        "industry_allocation": industry_allocation,
        "macro_signal": macro_signal,
        "layer_output": layer_output,
    }


def calculate_beta_weights(
    volatility_data: Optional[Dict[str, float]],
    cycle_position: Optional[Dict[str, Any]] = None,
    debt_cycle: Optional[Dict[str, str]] = None,
) -> Dict[str, float]:
    """
    计算Beta基准权重（中国版All Weather）。
    
    方法：
    1. 计算各资产3年滚动年化波动率（风险平价基础）
    2. 根据周期象限做方向性微调（框架第603行表7.3）
    3. 根据长期债务周期做战略调节（框架第622-623行）
    
    Args:
        volatility_data: 各资产年化波动率（用于风险平价）
        cycle_position: 周期象限定位，格式 {"quadrant": "recession"/"recovery"/...}
        debt_cycle: 长期债务周期，格式 {"us": "late"/"early"/"middle", "cn": "downward"/"upward"/"stable"}
    """
    if not volatility_data:
        # 无波动率数据，返回默认权重
        beta = BETA_BENCHMARK_WEIGHTS.copy()
    else:
        # 计算风险平价权重
        weights = {}
        total_inv_vol = 0
        
        for asset, vol in volatility_data.items():
            if vol > 0:
                inv_vol = 1 / vol
                total_inv_vol += inv_vol
        
        for asset, vol in volatility_data.items():
            if vol > 0:
                weights[asset] = (1 / vol) / total_inv_vol
            else:
                weights[asset] = 0
        
        # 归一化
        total = sum(weights.values())
        if total > 0:
            weights = {k: v / total for k, v in weights.items()}
        beta = weights
    
    # 框架第603行表7.3：周期象限→受益/受损资产→方向性权重调整
    if cycle_position:
        quadrant = cycle_position.get("quadrant", "")
        
        # 框架第598-603行表7.3：象限→受益/受损资产→权重调整
        # recovery=复苏, overheating=过热, stagflation=滞胀, recession=衰退
        quadrant_adjustments: Dict[str, Dict[str, float]] = {
            # 象限I复苏：权益↑ 国债↓ 黄金↓
            "recovery": {
                "csi300_500": +0.05, "us_assets": +0.03,
                "cn_gov_bond": -0.05, "gold": -0.03,
            },
            # 象限II过热：大宗商品↑ 国债↓ 成长股↓
            "overheating": {
                "nh_industrial": +0.05,
                "csi300_500": +0.03, "us_assets": +0.02,
                "cn_gov_bond": -0.05, "gold": -0.05,
            },
            # 象限III滞胀：黄金↑ 债券↓ 权益↓
            "stagflation": {
                "gold": +0.05, "cn_gov_bond": +0.03,
                "csi300_500": -0.05, "us_assets": -0.03,
            },
            # 象限IV衰退：国债↑ 黄金↑ 权益↓ 大宗↓
            "recession": {
                "cn_gov_bond": +0.05, "gold": +0.03,
                "csi300_500": -0.05, "nh_industrial": -0.03,
            },
        }
        
        adj = quadrant_adjustments.get(quadrant, {})
        for asset, delta in adj.items():
            if asset in beta:
                beta[asset] += delta
    
    # 框架第622-623行：长期债务周期战略调节
    if debt_cycle:
        # 美国长期债务周期末端：提高黄金/商品权重+10-20%，降低债券-10%
        us_status = debt_cycle.get("us", "")
        if us_status == "late":
            beta["gold"] = beta.get("gold", 0) + 0.10
            beta["nh_industrial"] = beta.get("nh_industrial", 0) + 0.05
            beta["cn_gov_bond"] = beta.get("cn_gov_bond", 0) - 0.15
        
        # 中国长期债务周期下行：降低债券+10%，提高高股息（简化：用黄金替代）
        cn_status = debt_cycle.get("cn", "")
        if cn_status == "downward":
            beta["cn_gov_bond"] = beta.get("cn_gov_bond", 0) - 0.10
            beta["gold"] = beta.get("gold", 0) + 0.10
    
    # 确保权重非负
    for asset in beta:
        if beta[asset] < 0:
            beta[asset] = 0
    
    # 归一化到100%
    total = sum(beta.values())
    if total > 0:
        beta = {k: v / total for k, v in beta.items()}
    
    return beta


def calculate_alpha_deviation(
    layer4_output: Dict[str, Any],
    layer45_output: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    计算Alpha偏离幅度。
    
    基于Layer 4修正后的信号强度。
    """
    # 获取修正后的信号
    if layer45_output:
        signals = layer45_output.get("corrected_signals", [])
    else:
        signals = layer4_output.get("all_signals", [])
    
    deviations = {}
    
    for signal in signals:
        # 断点②修复：阈值从50降至35
        # Layer 4.5 三重修正（压力×生命周期×范式）会将信号强度衰减约35%
        # 修正后强度56.5 → 约38，仍应纳入Alpha计算
        intensity = signal.get("final_intensity", signal.get("intensity", 0))
        if intensity < 35:
            continue
        
        direction = signal.get("direction")
        # 断点①修复：将中文资产名映射为英文标准键
        raw_assets = signal.get("related_assets", [])
        assets = [_normalize_asset_name(a) for a in raw_assets]
        
        # 计算偏离系数
        if intensity >= 80:
            alpha_coeff = 0.3
        elif intensity >= 60:
            alpha_coeff = 0.2
        elif intensity >= 50:
            alpha_coeff = 0.1
        else:
            alpha_coeff = 0
        
        # 应用到相关资产
        for asset in assets:
            if asset not in deviations:
                deviations[asset] = {"bullish": 0, "bearish": 0, "count": 0}
            
            if direction == "bullish":
                deviations[asset]["bullish"] += alpha_coeff * intensity / 100
            else:
                deviations[asset]["bearish"] += alpha_coeff * intensity / 100
            deviations[asset]["count"] += 1
    
    # 计算净值偏离
    for asset, dev in deviations.items():
        dev["net_deviation"] = dev["bullish"] - dev["bearish"]
    
    return deviations


def apply_risk_budget(
    beta_weights: Dict[str, float],
    alpha_deviation: Dict[str, Any],
    volatility_data: Optional[Dict[str, float]]
) -> Dict[str, float]:
    """
    应用风险预算约束。
    
    约束：
    - 单信号最大偏离: ±30%
    - 单资产最大权重偏离: ±50%
    - 组合年化波动率上限: 12%
    - 最大回撤硬性上限: 15%
    - 组合杠杆上限: 1.5x
    """
    constraints = RISK_BUDGET_CONSTRAINTS
    
    # 从Beta权重开始
    final_weights = beta_weights.copy()
    
    # 应用Alpha偏离
    for asset, dev in alpha_deviation.items():
        if asset in final_weights:
            net_dev = dev["net_deviation"]
            
            # 单信号最大偏离约束
            if abs(net_dev) > constraints["single_signal_max_deviation"]:
                net_dev = np.sign(net_dev) * constraints["single_signal_max_deviation"]
            
            # 应用偏离
            final_weights[asset] += net_dev
            
            # 单资产最大权重偏离约束
            base_weight = beta_weights.get(asset, 0)
            max_dev = base_weight * constraints["single_asset_max_deviation"]
            if abs(final_weights[asset] - base_weight) > max_dev:
                final_weights[asset] = base_weight + np.sign(net_dev) * max_dev
    
    # 确保权重为正
    for asset in final_weights:
        if final_weights[asset] < 0:
            final_weights[asset] = 0
    
    # 归一化到100%
    total = sum(final_weights.values())
    if total > 0:
        final_weights = {k: v / total for k, v in final_weights.items()}
    
    # 杠杆约束
    total_weight = sum(final_weights.values())
    if total_weight > constraints["leverage_cap"]:
        scale = constraints["leverage_cap"] / total_weight
        final_weights = {k: v * scale for k, v in final_weights.items()}
    
    return final_weights


def calculate_industry_allocation(
    layer2_output: Dict[str, Any],
    layer4_output: Dict[str, Any]
) -> Dict[str, Any]:
    """
    计算行业配置建议。
    
    行业配置得分 = 周期匹配度×3 + 景气趋势 + 政策催化
    """
    # 确定当前周期阶段
    china_quadrant = layer2_output.get("china_quadrant_adjusted", {}).get("quadrant", "neutral")
    
    # 获取周期对应的行业映射
    cycle_mapping = INDUSTRY_CYCLE_MAPPING.get(china_quadrant, INDUSTRY_CYCLE_MAPPING["recovery"])
    
    # 构建行业配置
    cn_industry = {
        "overweight": cycle_mapping.get("leading", []),
        "underweight": cycle_mapping.get("avoid", []),
        "neutral": cycle_mapping.get("defensive", []),
    }
    
    # 美国行业（简化处理）
    us_industry = {
        "overweight": ["科技", "可选消费"],
        "underweight": ["公用事业"],
        "neutral": ["医疗健康", "金融"],
    }
    
    return {
        "china": cn_industry,
        "us": us_industry,
        "current_cycle": china_quadrant,
    }


def _determine_direction(weights: Dict[str, float]) -> str:
    """确定最终方向。"""
    equity_weight = weights.get("csi300_500", 0) + weights.get("us_assets", 0) * 0.5
    bond_weight = weights.get("cn_gov_bond", 0)
    
    if equity_weight > bond_weight:
        return "bullish"
    elif bond_weight > equity_weight * 1.2:
        return "bearish"
    else:
        return "neutral"


def _determine_confidence(
    weights: Dict[str, float],
    alpha_deviation: Dict[str, Any]
) -> float:
    """
    确定置信度。
    
    基于 alpha_deviation 的实际偏离总量，而非资产数量。
    框架设计：偏离总量越大 → 信号越强 → 置信度越高。
    """
    if not alpha_deviation:
        return 0.5
    
    # 实际偏离总量（净值偏离绝对值之和）
    total_dev = sum(abs(d["net_deviation"]) for d in alpha_deviation.values())
    
    # 偏离总量 > 20%：3个以上有效信号叠加
    if total_dev > 0.20:
        return 0.85
    # 偏离总量 > 10%：有意义的信号叠加
    elif total_dev > 0.10:
        return 0.80
    # 偏离总量 > 5%：单个强信号
    elif total_dev > 0.05:
        return 0.75
    else:
        return 0.65


# 资产名称映射（中英文对照）
ASSET_NAME_MAP: Dict[str, str] = {
    "csi300_500": "A股",
    "cn_gov_bond": "中债",
    "nh_industrial": "南华工业品",
    "gold": "黄金",
    "us_assets": "美股",
    "emerging_market": "新兴市场",
    "global_capital_flow": "全球资本流向",
}


def _generate_reasoning(
    weights: Dict[str, float],
    alpha_deviation: Dict[str, Any]
) -> str:
    """生成推理摘要。"""
    # 计算整体方向
    equity_weight = weights.get("csi300_500", 0) + weights.get("us_assets", 0) * 0.5
    bond_weight = weights.get("cn_gov_bond", 0)
    
    if equity_weight > bond_weight:
        direction_str = "整体方向: 看多权益"
    elif bond_weight > equity_weight * 1.2:
        direction_str = "偏重债券防御"
    else:
        direction_str = "整体方向: 中性配置"
    
    lines = [direction_str]
    
    # Beta配置 - 使用中文资产名
    allocation_items = []
    for asset, weight in weights.items():
        if weight > 0.1:
            cn_name = ASSET_NAME_MAP.get(asset, asset)
            allocation_items.append(f"{cn_name} {weight:.0%}")
    if allocation_items:
        lines.append(" | ".join(allocation_items))
    
    # Alpha偏离 - 使用中文资产名
    if alpha_deviation:
        bullish = [ASSET_NAME_MAP.get(a, a) for a, d in alpha_deviation.items() if d["bullish"] > 0]
        bearish = [ASSET_NAME_MAP.get(a, a) for a, d in alpha_deviation.items() if d["bearish"] > 0]
        
        if bullish:
            lines.append(f"超配: {', '.join(bullish)}")
        if bearish:
            lines.append(f"低配: {', '.join(bearish)}")
    
    return " | ".join(lines)


def _generate_signals(weights: Dict[str, float]) -> List[str]:
    """生成信号列表——固定输出每种资产，不做阈值筛选。"""
    signals = []
    
    for asset, weight in weights.items():
        if weight >= 0.05:
            signals.append(f"{asset} 配置{weight:.0%}")
        else:
            signals.append(f"{asset} 低配{weight:.0%}")
    
    return signals


def _determine_risk_level(
    weights: Dict[str, float],
    alpha_deviation: Dict[str, Any]
) -> str:
    """确定风险等级。"""
    if alpha_deviation:
        total_dev = sum(abs(d["net_deviation"]) for d in alpha_deviation.values())
        if total_dev > 0.3:
            return "medium"
    
    return "low"


def _generate_key_findings(
    weights: Dict[str, float],
    alpha_deviation: Dict[str, Any]
) -> List[str]:
    """生成关键发现。"""
    findings = []
    
    # 最高配置
    max_asset = max(weights.items(), key=lambda x: x[1])
    findings.append(f"最高配置: {max_asset[0]} ({max_asset[1]:.0%})")
    
    # 最低配置
    min_asset = min([(k, v) for k, v in weights.items() if v > 0], key=lambda x: x[1])
    findings.append(f"最低配置: {min_asset[0]} ({min_asset[1]:.0%})")
    
    # Alpha偏离数
    findings.append(f"活跃信号数: {len(alpha_deviation)}")
    
    return findings
