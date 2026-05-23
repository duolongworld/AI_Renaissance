"""
宏观分析 Skill Signal 构建工具

提供标准化的 Signal 构建函数，供各层分析使用。
"""

from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from dataclasses import asdict

from agents.signal import Signal, Direction


# =============================================================================
# 常量
# =============================================================================

SKILL_NAME = "macro-analysis-skill"
OWNER_GROUP = "专家4组（宏观方向）"
TARGET = "全球宏观周期定位与资产配置"
OUTPUT_VERSION = "0.1"


# =============================================================================
# Signal 构建函数
# =============================================================================

def build_macro_signal(
    direction: str,
    confidence: float,
    reasoning: str,
    signals: List[str],
    layer_name: str,
    time_horizon: str = "mid",
    risk_level: str = "low",
    key_findings: List[str] = None,
    evidence: List[Dict] = None,
    risk_notes: List[str] = None,
    uncertainties: List[str] = None,
    needs_human_review: bool = False,
    meta_extra: Dict[str, Any] = None,
    period: str = None,
) -> Signal:
    """
    构建宏观分析 Skill 的标准 Signal 格式。
    
    这是宏观分析 Skill 的顶层输出格式，与 agents.signal.Signal 对齐，
    并在 meta 中包含各层详细信息。
    
    Args:
        direction: 信号方向 (bullish/bearish/neutral)
        confidence: 置信度 (0.0 ~ 1.0)
        reasoning: 推理过程摘要
        signals: 具体信号列表
        layer_name: 来源层名称 (e.g., "layer5_asset_allocation")
        time_horizon: 时间周期 (short/mid/long)
        risk_level: 风险等级 (low/medium/high)
        key_findings: 关键发现列表
        evidence: 证据列表
        risk_notes: 风险说明列表
        uncertainties: 不确定性列表
        needs_human_review: 是否需要人工复核
        meta_extra: 额外的 meta 信息
        period: 分析时段 (e.g., "2026-05-05至2026-05-12")
    
    Returns:
        Signal 对象
    
    Example:
        >>> signal = build_macro_signal(
        ...     direction="bullish",
        ...     confidence=0.75,
        ...     reasoning="中国CAI上行，A股 ERP处于历史高位",
        ...     signals=["中国增长预期差+", "A股 ERP极端低估"],
        ...     layer_name="layer5_asset_allocation",
        ...     time_horizon="mid",
        ...     risk_level="medium",
        ... )
    """
    # 验证 direction
    valid_directions = ["bullish", "bearish", "neutral"]
    if direction not in valid_directions:
        raise ValueError(f"direction must be one of {valid_directions}, got {direction}")
    
    # 验证 confidence
    if not 0.0 <= confidence <= 1.0:
        raise ValueError(f"confidence must be between 0.0 and 1.0, got {confidence}")
    
    # 构建 meta 字段
    meta = {
        "output_version": OUTPUT_VERSION,
        "skill_name": SKILL_NAME,
        "owner_group": OWNER_GROUP,
        "target": TARGET,
        "period": period or _get_current_period(),
        "time_horizon": time_horizon,
        "risk_level": risk_level,
        "key_findings": key_findings or [],
        "evidence": evidence or [],
        "risk_notes": risk_notes or [],
        "uncertainties": uncertainties or [],
        "needs_human_review": needs_human_review,
        "layer_outputs": {},
    }
    
    # 合并额外的 meta 信息
    if meta_extra:
        meta.update(meta_extra)
    
    return Signal(
        direction=direction,
        confidence=confidence,
        reasoning=reasoning,
        signals=signals,
        source=f"macro/{layer_name}",
        signal_type="macro",
        stock_code="",  # 宏观分析无特定股票
        weight=1.0,
        meta=meta,
    )


def build_layer_signal(
    layer_name: str,
    analysis_result: Dict[str, Any],
    direction: str = None,
    confidence: float = None,
    reasoning: str = None,
    signals: List[str] = None,
) -> Dict[str, Any]:
    """
    构建单个层的输出结果。
    
    各层的输出结果存储在顶层 Signal 的 meta.layer_outputs 中。
    
    Args:
        layer_name: 层名称 (e.g., "layer0", "layer1", "layer2")
        analysis_result: 该层的分析结果字典
        direction: 该层的方向判断（可选）
        confidence: 该层的置信度（可选）
        reasoning: 该层的推理摘要（可选）
        signals: 该层的具体信号列表（可选）
    
    Returns:
        层输出字典
    
    Example:
        >>> layer_output = build_layer_signal(
        ...     layer_name="layer1",
        ...     analysis_result={
        ...         "china_cai": 0.3,
        ...         "china_fci": -0.5,
        ...         "us_cai": 1.1,
        ...         "us_fci": 0.7,
        ...     },
        ...     direction="neutral",
        ...     confidence=0.8,
        ... )
    """
    output = {
        "layer_name": layer_name,
        "timestamp": datetime.now().isoformat(),
        "analysis_result": analysis_result,
    }
    
    if direction is not None:
        output["direction"] = direction
    if confidence is not None:
        output["confidence"] = confidence
    if reasoning is not None:
        output["reasoning"] = reasoning
    if signals is not None:
        output["signals"] = signals
    
    return output


def build_evidence(
    source_type: str,
    source_name: str,
    date: str,
    metric: str,
    value: Any,
    comparison: str = None,
    note: str = None,
) -> Dict[str, Any]:
    """
    构建证据字典。
    
    Args:
        source_type: 证据来源类型 (macro_data/market_data/fund_flow/etc.)
        source_name: 证据来源名称
        date: 数据日期
        metric: 指标名称
        value: 指标值
        comparison: 与什么的对比
        note: 额外说明
    
    Returns:
        证据字典
    
    Example:
        >>> evidence = build_evidence(
        ...     source_type="macro_data",
        ...     source_name="中国统计局制造业PMI",
        ...     date="2026-05-01",
        ...     metric="PMI",
        ...     value="50.5",
        ...     comparison="高于荣枯线50",
        ...     note="连续3个月扩张",
        ... )
    """
    return {
        "source_type": source_type,
        "source_name": source_name,
        "date": date,
        "metric": metric,
        "value": str(value),
        "comparison": comparison or "",
        "note": note or "",
    }


# =============================================================================
# 置信度计算函数
# =============================================================================

def calculate_confidence(
    base_confidence: float,
    data_completeness: float = 1.0,
    signal_consistency: float = 1.0,
) -> float:
    """
    计算最终置信度。
    
    计算公式: confidence = base_confidence × data_completeness × signal_consistency
    
    Args:
        base_confidence: 基础置信度 (0.0 ~ 1.0)
        data_completeness: 数据完整性系数 (0.0 ~ 1.0)，1.0=无缺失，0.8=部分缺失
        signal_consistency: 信号一致性系数 (0.0 ~ 1.0)，1.0=同向，0.6=冲突严重
    
    Returns:
        最终置信度 (0.0 ~ 1.0)
    
    Example:
        >>> conf = calculate_confidence(
        ...     base_confidence=0.9,
        ...     data_completeness=0.9,
        ...     signal_consistency=0.8,
        ... )
        >>> round(conf, 2)
        0.65
    """
    confidence = base_confidence * data_completeness * signal_consistency
    return max(0.0, min(1.0, confidence))  # 截断到 [0.0, 1.0]


def determine_confidence_base(
    signal_intensity_percentile: float,
) -> float:
    """
    根据信号强度百分位确定基础置信度。
    
    Args:
        signal_intensity_percentile: 信号强度百分位 (0.0 ~ 100.0)
    
    Returns:
        基础置信度
    """
    if signal_intensity_percentile >= 80:
        return 0.9
    elif signal_intensity_percentile >= 60:
        return 0.7
    elif signal_intensity_percentile >= 50:
        return 0.5
    else:
        return 0.3


# =============================================================================
# 风险等级判定函数
# =============================================================================

def determine_risk_level(
    vix_spike: float = 0,
    vix_level: float = 0,
    csi300_drop: float = 0,
    northbound_outflow: float = 0,
    sahm_rule: float = None,
    liquidity_crisis: bool = False,
    policy_change: bool = False,
    black_swan: bool = False,
) -> str:
    """
    判定风险等级。
    
    Args:
        vix_spike: VIX单日攀升幅度
        vix_level: VIX绝对水平
        csi300_drop: 沪深300单日跌幅（%）
        northbound_outflow: 北向资金单日净流出（亿）
        sahm_rule: Sahm Rule衰退指标（可选）
        liquidity_crisis: 是否发生流动性危机
        policy_change: 是否发生重大政策变化
        black_swan: 是否发生黑天鹅事件
    
    Returns:
        风险等级 (low/medium/high)
    """
    # 特殊高风险情形
    if sahm_rule is not None and sahm_rule >= 0.5:
        return "high"
    if liquidity_crisis:
        return "high"
    if policy_change:
        return "high"
    if black_swan:
        return "high"
    
    # 重度冲击
    if (vix_spike >= 10 or vix_level >= 30 or 
        csi300_drop >= 5.0 or northbound_outflow >= 200):
        return "high"
    
    # 轻度冲击
    if (vix_spike > 0 or csi300_drop > 0 or northbound_outflow > 0):
        return "medium"
    
    return "low"


# =============================================================================
# 信号强度计算函数
# =============================================================================

def calculate_signal_intensity(
    initial_intensity: float,
    decay_type: str = "exponential",
    periods_elapsed: int = 0,
    decay_rate: float = None,
    initial_validity: int = None,
) -> float:
    """
    计算衰减后的信号强度。
    
    支持指数衰减和线性衰减。
    
    Args:
        initial_intensity: 初始信号强度 (0.0 ~ 1.0 或 0 ~ 100)
        decay_type: 衰减类型 ("exponential" 或 "linear")
        periods_elapsed: 经过的周期数
        decay_rate: 衰减率（指数衰减用，如0.25表示每周衰减25%）
        initial_validity: 初始有效期（周期数）
    
    Returns:
        衰减后的信号强度
    
    Example:
        >>> # 指数衰减：初始80%，经过2个月，每月衰减20%
        >>> intensity = calculate_signal_intensity(
        ...     initial_intensity=0.80,
        ...     decay_type="exponential",
        ...     periods_elapsed=2,
        ...     decay_rate=0.20,
        ... )
        >>> round(intensity, 3)
        0.512
    """
    if decay_type == "exponential":
        if decay_rate is None:
            raise ValueError("exponential decay requires decay_rate")
        # 剩余比例 = (1 - decay_rate) ^ periods_elapsed
        remaining_ratio = (1 - decay_rate) ** periods_elapsed
        return initial_intensity * remaining_ratio
    
    elif decay_type == "linear":
        if initial_validity is None:
            raise ValueError("linear decay requires initial_validity")
        # 线性衰减
        remaining_ratio = max(0, 1 - periods_elapsed / initial_validity)
        return initial_intensity * remaining_ratio
    
    else:
        raise ValueError(f"Unknown decay_type: {decay_type}")


def determine_signal_direction(
    z_score: float,
    threshold_confirm: float = 1.0,
    threshold_neutral: float = 0.5,
) -> str:
    """
    根据 z-score 判定信号方向。
    
    Args:
        z_score: z-score 值
        threshold_confirm: 方向确认阈值（默认1.0）
        threshold_neutral: 中性阈值（默认0.5）
    
    Returns:
        方向 (bullish/bearish/neutral)
    """
    if z_score >= threshold_confirm:
        return "bullish"
    elif z_score <= -threshold_confirm:
        return "bearish"
    elif abs(z_score) <= threshold_neutral:
        return "neutral"
    else:
        # 中间地带，根据正负判断方向但不确认
        return "bullish" if z_score > 0 else "bearish"


# =============================================================================
# 反身性压力修正函数
# =============================================================================

def calculate_reflexivity_coefficient(
    pressure_score: float,
    green_max: float = 30,
    yellow_max: float = 50,
    orange_max: float = 70,
) -> float:
    """
    计算反身性压力修正系数。
    
    Args:
        pressure_score: 反身性压力综合得分 (0 ~ 100)
        green_max: 绿色上限（默认30）
        yellow_max: 黄色上限（默认50）
        orange_max: 橙色上限（默认70）
    
    Returns:
        修正系数 (0.25 ~ 1.0)
    """
    if pressure_score <= green_max:
        return 1.0  # 绿色
    elif pressure_score <= yellow_max:
        return 0.75  # 黄色
    elif pressure_score <= orange_max:
        return 0.50  # 橙色
    else:
        return 0.25  # 红色


def get_pressure_level(
    pressure_score: float,
    green_max: float = 30,
    yellow_max: float = 50,
    orange_max: float = 70,
) -> str:
    """
    获取反身性压力等级。
    
    Returns:
        压力等级 (green/yellow/orange/red)
    """
    if pressure_score <= green_max:
        return "green"
    elif pressure_score <= yellow_max:
        return "yellow"
    elif pressure_score <= orange_max:
        return "orange"
    else:
        return "red"


# =============================================================================
# 辅助函数
# =============================================================================

def _get_current_period() -> str:
    """获取当前时间段字符串（本周）。"""
    now = datetime.now()
    # 计算本周一
    monday = now - timedelta(days=now.weekday())
    sunday = monday + timedelta(days=6)
    return f"{monday.strftime('%Y-%m-%d')}至{sunday.strftime('%Y-%m-%d')}"


def merge_layer_outputs(
    layer_outputs: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    合并多个层的输出。
    
    Args:
        layer_outputs: 各层输出列表
    
    Returns:
        合并后的层输出字典
    """
    merged = {}
    for layer_output in layer_outputs:
        layer_name = layer_output.get("layer_name", "unknown")
        merged[layer_name] = layer_output
    return merged


def validate_signal(signal: Signal) -> List[str]:
    """
    校验 Signal 的有效性，返回错误列表。
    
    Args:
        signal: 待校验的 Signal 对象
    
    Returns:
        错误列表，空列表表示校验通过
    """
    errors = []
    
    # 方向校验
    if signal.direction not in ["bullish", "bearish", "neutral"]:
        errors.append(f"Invalid direction: {signal.direction}")
    
    # 置信度校验
    if not 0.0 <= signal.confidence <= 1.0:
        errors.append(f"Invalid confidence: {signal.confidence}")
    
    # meta 必需字段校验
    required_meta_fields = [
        "output_version", "skill_name", "owner_group", 
        "target", "period", "time_horizon", "risk_level"
    ]
    for field in required_meta_fields:
        if field not in signal.meta:
            errors.append(f"Missing meta field: {field}")
    
    return errors


# =============================================================================
# 标准化信号输出模板构建函数
# =============================================================================

def build_standard_output(
    global_cycle_position: str,
    us_cycle_position: str,
    cn_cycle_position: str,
    cn_us_interaction: str,
    global_triangle: str,
    expected_diff_signals: List[Dict],
    csi300_signal: Dict,
    sp500_signal: Dict,
    asset_weights: Dict,
    cn_industry_allocation: Dict,
    us_industry_allocation: Dict,
    core_logic: str,
    tail_risk: str,
    signal_validity: Dict,
    disclaimer: str = "本信号仅供参考，不构成投资建议。",
) -> Dict[str, Any]:
    """
    构建标准化信号输出模板（15项）。
    
    详见需求文档 5.3 节。
    
    Args:
        global_cycle_position: 全球周期最终定位
        us_cycle_position: 美国周期最终定位
        cn_cycle_position: 国内周期最终定位
        cn_us_interaction: 中美周期联动判定
        global_triangle: Layer 2.5全球宏观三角定位
        expected_diff_signals: 预期差信号汇总
        csi300_signal: A股信号方向
        sp500_signal: 美股信号方向
        asset_weights: 资产配置权重
        cn_industry_allocation: A股行业配置
        us_industry_allocation: 美股行业配置
        core_logic: 核心依据
        tail_risk: 尾部风险提示
        signal_validity: 信号有效性评级
        disclaimer: 合规免责声明
    
    Returns:
        15项标准化输出字典
    """
    return {
        "1_global_cycle_position": global_cycle_position,
        "2_us_cycle_position": us_cycle_position,
        "3_cn_cycle_position": cn_cycle_position,
        "4_cn_us_interaction": cn_us_interaction,
        "5_global_triangle": global_triangle,
        "6_expected_diff_signals": expected_diff_signals,
        "7_csi300_signal": csi300_signal,
        "8_sp500_signal": sp500_signal,
        "9_asset_weights": asset_weights,
        "10_cn_industry_allocation": cn_industry_allocation,
        "11_us_industry_allocation": us_industry_allocation,
        "12_core_logic": core_logic,
        "13_tail_risk": tail_risk,
        "14_signal_validity": signal_validity,
        "15_disclaimer": disclaimer,
    }
