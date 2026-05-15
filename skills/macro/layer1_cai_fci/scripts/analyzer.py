"""
Layer 1: 状态识别——CAI/FCI 合成指标

纯数值计算层，直接调用本脚本计算中国/美国版CAI和FCI。
不需要LLM分析。
"""

from typing import Dict, List, Any, Optional, Tuple
import numpy as np

from utils.constants import (
    CHINA_CAI_WEIGHTS,
    CHINA_FCI_WEIGHTS,
    US_CAI_WEIGHTS,
    US_FCI_WEIGHTS,
    CHINA_INFLATION_WEIGHTS,
    US_INFLATION_WEIGHTS,
    Z_SCORE_THRESHOLDS,
)
from utils.signal_utils import build_layer_signal


# =============================================================================
# 主要分析函数
# =============================================================================

def analyze_cai_fci(
    china_indicators: Dict[str, float],
    us_indicators: Dict[str, float],
    historical_data: Optional[Dict[str, List[float]]] = None,
) -> Dict[str, Any]:
    """
    计算中国/美国版 CAI（实时活动指数）和 FCI（金融条件指数）。
    
    Args:
        china_indicators: 中国指标数据
            - industrial_added_value_yoy: 工业增加值同比
            - caixin_manufacturing_pmi: 财新制造业PMI
            - nbs_manufacturing_pmi: 统计局制造业PMI
            - total_social_financing_yoy: 社融存量同比
            - credit_impulse_12m: 信贷脉冲（12M滚动）
            - commercial_housing_sales_yoy: 商品房销售面积同比
            - real_estate_investment_yoy: 地产开发投资同比
            - retail_sales_yoy: 社会消费品零售同比
            - passenger_car_sales_yoy: 乘用车销量同比
            - export_yoy_usd: 出口同比（美元计）
            - ccfi_index: CCFI运价指数
            - power_consumption_yoy: 发电耗煤同比
            - blast_furnace_rate: 高炉开工率
            - metro_passenger_flow: 地铁客流
            - dr007_shibor_3m: DR007/SHIBOR 3M
            - cn_1y_10y_spread: 1Y-10Y国债利差
            - aa_credit_spread: AA信用利差
            - cny_reer: 人民币REER
            - csi_300_erp: A股ERP
            - core_cpi_yoy: 核心CPI同比
            - ppi_yoy: PPI同比
            - nh_industrial_index_yoy: 南华工业品指数同比
            - core_cpi_3m_change: 核心CPI 3M变化
            - ppi_3m_change: PPI 3M变化
            - nh_industrial_3m_change: 南华工业品 3M变化
        
        us_indicators: 美国指标数据
            - ism_manufacturing_pmi: ISM制造业PMI
            - ism_services_pmi: ISM服务业PMI
            - nonfarm_payrolls_3m_avg: 非农就业（3M均值）
            - industrial_production_yoy: 工业生产指数同比
            - retail_sales_yoy: 零售销售同比
            - personal_consumption_yoy: 个人消费支出同比
            - new_housing_starts: 新屋开工
            - existing_home_sales: 成屋销售
            - initial_jobless_claims_4w: 初申失业金人数（4W均值）
            - credit_pulse: 信贷脉冲
            - sofr_effr: SOFR/EFFR
            - us_2y_10y_spread: 2Y-10Y UST利差
            - us_hy_spread: US HY利差
            - dxy_index: 美元指数
            - sp500_erp: S&P 500 ERP
            - core_pce_yoy: 核心PCE同比
            - eci_wage_growth: ECI工资增速
            - breakeven_5y5y: 5Y5Y通胀互换
            - core_pce_3m_change: 核心PCE 3M变化
            - eci_3m_change: ECI 3M变化
            - breakeven_5y5y_3m_change: 5Y5Y Breakeven 3M变化
        
        historical_data: 历史数据（用于计算真实z-score，可选）
            - 如果提供，使用真实滚动窗口计算z-score
            - 如果不提供，使用默认参数估算
    
    Returns:
        分析结果字典
    
    Example:
        >>> result = analyze_cai_fci(
        ...     china_indicators={
        ...         "nbs_manufacturing_pmi": 50.2,
        ...         "caixin_manufacturing_pmi": 51.0,
        ...         "total_social_financing_yoy": 9.5,
        ...         "cpi_yoy": 0.3,
        ...         "ppi_yoy": -2.5,
        ...         "dr007": 1.8,
        ...         "csi_300_erp": 5.2,
        ...     },
        ...     us_indicators={
        ...         "ism_manufacturing_pmi": 52.0,
        ...         "nonfarm_payrolls_3m_avg": 180000,
        ...         "core_pce_yoy": 2.8,
        ...         "sp500_erp": 2.1,
        ...     },
        ... )
    """
    # 计算中国版CAI
    china_cai = calculate_china_cai(china_indicators, historical_data)
    
    # 计算中国版FCI
    china_fci = calculate_china_fci(china_indicators, historical_data)
    
    # 计算中国通胀得分
    china_inflation = calculate_china_inflation_score(china_indicators, historical_data)
    
    # 计算美国版CAI
    us_cai = calculate_us_cai(us_indicators, historical_data)
    
    # 计算美国版FCI
    us_fci = calculate_us_fci(us_indicators, historical_data)
    
    # 计算美国通胀得分
    us_inflation = calculate_us_inflation_score(us_indicators, historical_data)
    
    # 计算中美差值
    cn_us_diff = {
        "cai_diff": china_cai["z_score"] - us_cai["z_score"],
        "fci_diff": china_fci["z_score"] - us_fci["z_score"],
        "inflation_diff": china_inflation["z_score"] - us_inflation["z_score"],
    }
    
    # 构建层输出
    layer_output = build_layer_signal(
        layer_name="layer1",
        analysis_result={
            "china_cai": china_cai,
            "china_fci": china_fci,
            "china_inflation": china_inflation,
            "us_cai": us_cai,
            "us_fci": us_fci,
            "us_inflation": us_inflation,
            "cn_us_diff": cn_us_diff,
        },
        direction="neutral",  # 数值计算层不输出方向
        confidence=0.8,
        reasoning=f"中国CAI: {china_cai['z_score']:.2f}σ, FCI: {china_fci['z_score']:.2f}σ; 美国CAI: {us_cai['z_score']:.2f}σ, FCI: {us_fci['z_score']:.2f}σ",
    )
    
    return {
        "china_cai": china_cai,
        "china_fci": china_fci,
        "china_inflation": china_inflation,
        "us_cai": us_cai,
        "us_fci": us_fci,
        "us_inflation": us_inflation,
        "cn_us_diff": cn_us_diff,
        "layer_output": layer_output,
    }


# =============================================================================
# 中国版CAI计算
# =============================================================================

def calculate_china_cai(
    indicators: Dict[str, float],
    historical_data: Optional[Dict[str, List[float]]] = None,
) -> Dict[str, Any]:
    """
    计算中国版CAI（Current Activity Indicator）。
    
    CAI回答"经济现在好不好"，正值表示经济活动高于历史平均水平。
    
    计算方法：
    1. 每个指标做z-score标准化
    2. 按权重表加权求和
    3. 输出z-score分数
    """
    weighted_sum = 0.0
    total_weight = 0.0
    component_scores = {}
    
    for indicator_name, weight in CHINA_CAI_WEIGHTS.items():
        if indicator_name in indicators and indicators[indicator_name] is not None:
            value = indicators[indicator_name]
            
            # 计算z-score
            if historical_data and indicator_name in historical_data:
                z_score = calculate_z_score_from_history(value, historical_data[indicator_name])
            else:
                z_score = estimate_z_score(value, indicator_name)
            
            weighted_sum += z_score * weight
            total_weight += weight
            component_scores[indicator_name] = {
                "raw": value,
                "z_score": z_score,
                "weight": weight,
            }
    
    # 归一化
    final_score = weighted_sum / total_weight if total_weight > 0 else 0.0
    
    # 确定方向标签
    if final_score > Z_SCORE_THRESHOLDS["direction_confirm"]:
        direction = "上行"
    elif final_score < -Z_SCORE_THRESHOLDS["direction_confirm"]:
        direction = "下行"
    elif abs(final_score) <= Z_SCORE_THRESHOLDS["direction_neutral"]:
        direction = "中性"
    else:
        direction = "偏上行" if final_score > 0 else "偏下行"
    
    return {
        "score": final_score,
        "z_score": final_score,
        "direction": direction,
        "data_coverage": total_weight,
        "component_scores": component_scores,
    }


# =============================================================================
# 中国版FCI计算
# =============================================================================

def calculate_china_fci(
    indicators: Dict[str, float],
    historical_data: Optional[Dict[str, List[float]]] = None,
) -> Dict[str, Any]:
    """
    计算中国版FCI（Financial Conditions Index）。
    
    FCI回答"金融环境松还是紧"，正值表示金融条件偏紧。
    
    注意：所有指标统一为"越高越紧"方向。
    """
    weighted_sum = 0.0
    total_weight = 0.0
    component_scores = {}
    
    for indicator_name, weight in CHINA_FCI_WEIGHTS.items():
        if indicator_name in indicators and indicators[indicator_name] is not None:
            value = indicators[indicator_name]
            
            # 方向统一化
            # DR007/SHIBOR: 越高越紧 ✓
            # 利差: 越高越松，需要反转
            # 信用利差: 越高越紧 ✓
            # REER: 越高越紧 ✓
            # ERP: 越高越紧 ✓
            
            if indicator_name == "cn_1y_10y_spread":
                # 利差反转：越高越松
                value = -value
            
            # 计算z-score
            if historical_data and indicator_name in historical_data:
                z_score = calculate_z_score_from_history(value, historical_data[indicator_name])
            else:
                z_score = estimate_z_score(value, indicator_name)
            
            weighted_sum += z_score * weight
            total_weight += weight
            component_scores[indicator_name] = {
                "raw": value,
                "z_score": z_score,
                "weight": weight,
            }
    
    # 归一化
    final_score = weighted_sum / total_weight if total_weight > 0 else 0.0
    
    # 确定方向标签
    if final_score > Z_SCORE_THRESHOLDS["direction_confirm"]:
        direction = "偏紧"
    elif final_score < -Z_SCORE_THRESHOLDS["direction_confirm"]:
        direction = "偏松"
    elif abs(final_score) <= Z_SCORE_THRESHOLDS["direction_neutral"]:
        direction = "中性"
    else:
        direction = "略紧" if final_score > 0 else "略松"
    
    return {
        "score": final_score,
        "z_score": final_score,
        "direction": direction,
        "data_coverage": total_weight,
        "component_scores": component_scores,
    }


# =============================================================================
# 中国通胀得分计算
# =============================================================================

def calculate_china_inflation_score(
    indicators: Dict[str, float],
    historical_data: Optional[Dict[str, List[float]]] = None,
) -> Dict[str, Any]:
    """
    计算中国通胀得分（独立于CAI/FCI）。
    
    采用水平+动量双维度合成。
    得分 = 水平z-score × 0.5 + 动量z-score × 0.5
    """
    # 水平维度
    level_components = ["core_cpi_yoy", "ppi_yoy", "nh_industrial_index_yoy"]
    level_sum = 0.0
    level_count = 0
    
    for name in level_components:
        if name in indicators and indicators[name] is not None:
            value = indicators[name]
            if historical_data and name in historical_data:
                z = calculate_z_score_from_history(value, historical_data[name])
            else:
                z = estimate_z_score(value, name)
            level_sum += z
            level_count += 1
    
    level_z = level_sum / level_count if level_count > 0 else 0.0
    
    # 动量维度
    momentum_components = ["core_cpi_3m_change", "ppi_3m_change", "nh_industrial_3m_change"]
    momentum_sum = 0.0
    momentum_count = 0
    
    for name in momentum_components:
        if name in indicators and indicators[name] is not None:
            value = indicators[name]
            if historical_data and name in historical_data:
                z = calculate_z_score_from_history(value, historical_data[name])
            else:
                z = estimate_z_score(value, name)
            momentum_sum += z
            momentum_count += 1
    
    momentum_z = momentum_sum / momentum_count if momentum_count > 0 else 0.0
    
    # 合成
    final_score = level_z * 0.5 + momentum_z * 0.5
    
    if final_score > Z_SCORE_THRESHOLDS["direction_confirm"]:
        direction = "上行"
    elif final_score < -Z_SCORE_THRESHOLDS["direction_confirm"]:
        direction = "下行"
    elif abs(final_score) <= Z_SCORE_THRESHOLDS["direction_neutral"]:
        direction = "中性"
    else:
        direction = "偏上行" if final_score > 0 else "偏下行"
    
    return {
        "score": final_score,
        "z_score": final_score,
        "level_z": level_z,
        "momentum_z": momentum_z,
        "direction": direction,
    }


# =============================================================================
# 美国版CAI计算
# =============================================================================

def calculate_us_cai(
    indicators: Dict[str, float],
    historical_data: Optional[Dict[str, List[float]]] = None,
) -> Dict[str, Any]:
    """
    计算美国版CAI。
    
    注意：美国版CAI权重需回测校准，当前使用等权重。
    """
    weighted_sum = 0.0
    total_weight = 0.0
    component_scores = {}
    
    for indicator_name, weight in US_CAI_WEIGHTS.items():
        if indicator_name in indicators and indicators[indicator_name] is not None:
            value = indicators[indicator_name]
            
            if historical_data and indicator_name in historical_data:
                z_score = calculate_z_score_from_history(value, historical_data[indicator_name])
            else:
                z_score = estimate_z_score(value, indicator_name)
            
            weighted_sum += z_score * weight
            total_weight += weight
            component_scores[indicator_name] = {
                "raw": value,
                "z_score": z_score,
                "weight": weight,
            }
    
    final_score = weighted_sum / total_weight if total_weight > 0 else 0.0
    
    if final_score > Z_SCORE_THRESHOLDS["direction_confirm"]:
        direction = "上行"
    elif final_score < -Z_SCORE_THRESHOLDS["direction_confirm"]:
        direction = "下行"
    elif abs(final_score) <= Z_SCORE_THRESHOLDS["direction_neutral"]:
        direction = "中性"
    else:
        direction = "偏上行" if final_score > 0 else "偏下行"
    
    return {
        "score": final_score,
        "z_score": final_score,
        "direction": direction,
        "data_coverage": total_weight,
        "component_scores": component_scores,
    }


# =============================================================================
# 美国版FCI计算
# =============================================================================

def calculate_us_fci(
    indicators: Dict[str, float],
    historical_data: Optional[Dict[str, List[float]]] = None,
) -> Dict[str, Any]:
    """
    计算美国版FCI。
    """
    weighted_sum = 0.0
    total_weight = 0.0
    component_scores = {}
    
    for indicator_name, weight in US_FCI_WEIGHTS.items():
        if indicator_name in indicators and indicators[indicator_name] is not None:
            value = indicators[indicator_name]
            
            # 方向统一化
            # SOFR/EFFR: 越高越紧 ✓
            # 利差: 越高越松，需要反转
            # HY利差: 越高越紧 ✓
            # DXY: 越高越紧 ✓
            # ERP: 越高越紧 ✓
            
            if indicator_name == "us_2y_10y_spread":
                value = -value
            
            if historical_data and indicator_name in historical_data:
                z_score = calculate_z_score_from_history(value, historical_data[indicator_name])
            else:
                z_score = estimate_z_score(value, indicator_name)
            
            weighted_sum += z_score * weight
            total_weight += weight
            component_scores[indicator_name] = {
                "raw": value,
                "z_score": z_score,
                "weight": weight,
            }
    
    final_score = weighted_sum / total_weight if total_weight > 0 else 0.0
    
    if final_score > Z_SCORE_THRESHOLDS["direction_confirm"]:
        direction = "偏紧"
    elif final_score < -Z_SCORE_THRESHOLDS["direction_confirm"]:
        direction = "偏松"
    elif abs(final_score) <= Z_SCORE_THRESHOLDS["direction_neutral"]:
        direction = "中性"
    else:
        direction = "略紧" if final_score > 0 else "略松"
    
    return {
        "score": final_score,
        "z_score": final_score,
        "direction": direction,
        "data_coverage": total_weight,
        "component_scores": component_scores,
    }


# =============================================================================
# 美国通胀得分计算
# =============================================================================

def calculate_us_inflation_score(
    indicators: Dict[str, float],
    historical_data: Optional[Dict[str, List[float]]] = None,
) -> Dict[str, Any]:
    """
    计算美国通胀得分。
    """
    # 水平维度
    level_components = ["core_pce_yoy", "eci_wage_growth", "breakeven_5y5y"]
    level_sum = 0.0
    level_count = 0
    
    for name in level_components:
        if name in indicators and indicators[name] is not None:
            value = indicators[name]
            if historical_data and name in historical_data:
                z = calculate_z_score_from_history(value, historical_data[name])
            else:
                z = estimate_z_score(value, name)
            level_sum += z
            level_count += 1
    
    level_z = level_sum / level_count if level_count > 0 else 0.0
    
    # 动量维度
    momentum_components = ["core_pce_3m_change", "eci_3m_change", "breakeven_5y5y_3m_change"]
    momentum_sum = 0.0
    momentum_count = 0
    
    for name in momentum_components:
        if name in indicators and indicators[name] is not None:
            value = indicators[name]
            if historical_data and name in historical_data:
                z = calculate_z_score_from_history(value, historical_data[name])
            else:
                z = estimate_z_score(value, name)
            momentum_sum += z
            momentum_count += 1
    
    momentum_z = momentum_sum / momentum_count if momentum_count > 0 else 0.0
    
    # 合成
    final_score = level_z * 0.5 + momentum_z * 0.5
    
    if final_score > Z_SCORE_THRESHOLDS["direction_confirm"]:
        direction = "上行"
    elif final_score < -Z_SCORE_THRESHOLDS["direction_confirm"]:
        direction = "下行"
    elif abs(final_score) <= Z_SCORE_THRESHOLDS["direction_neutral"]:
        direction = "中性"
    else:
        direction = "偏上行" if final_score > 0 else "偏下行"
    
    return {
        "score": final_score,
        "z_score": final_score,
        "level_z": level_z,
        "momentum_z": momentum_z,
        "direction": direction,
    }


# =============================================================================
# 辅助函数
# =============================================================================

def calculate_z_score_from_history(
    value: float,
    historical_values: List[float],
    window: int = None,
) -> float:
    """
    从历史数据计算真实z-score。
    
    Args:
        value: 当前值
        historical_values: 历史值序列（应已排序，最新在后）
        window: 滚动窗口大小（默认使用全部历史）
    
    Returns:
        z-score
    """
    if len(historical_values) < 2:
        return 0.0
    
    if window:
        values = historical_values[-window:]
    else:
        values = historical_values
    
    mean = np.mean(values)
    std = np.std(values)
    
    if std == 0:
        return 0.0
    
    return (value - mean) / std


def estimate_z_score(value: float, indicator_name: str) -> float:
    """
    估算z-score（使用预设参数，未使用真实历史数据）。
    
    实际实现应使用真实滚动窗口计算。
    """
    # 预设参数：均值和标准差
    params = {
        # 中国CAI指标
        "industrial_added_value_yoy": (6.0, 3.0),
        "caixin_manufacturing_pmi": (50.5, 1.5),
        "nbs_manufacturing_pmi": (50.0, 1.0),
        "total_social_financing_yoy": (10.0, 2.0),
        "credit_impulse_12m": (0.0, 5.0),
        "commercial_housing_sales_yoy": (0.0, 10.0),
        "real_estate_investment_yoy": (5.0, 5.0),
        "retail_sales_yoy": (8.0, 3.0),
        "passenger_car_sales_yoy": (0.0, 10.0),
        "export_yoy_usd": (5.0, 8.0),
        "ccfi_index": (1000.0, 200.0),
        "power_consumption_yoy": (5.0, 5.0),
        "blast_furnace_rate": (65.0, 5.0),
        "metro_passenger_flow": (100.0, 10.0),
        
        # 中国FCI指标
        "dr007_shibor_3m": (2.0, 0.3),
        "cn_1y_10y_spread": (0.5, 0.3),
        "aa_credit_spread": (0.5, 0.2),
        "cny_reer": (100.0, 5.0),
        "csi_300_erp": (3.0, 1.0),
        
        # 中国通胀指标
        "cpi_yoy": (2.0, 1.5),
        "ppi_yoy": (0.0, 3.0),
        "nh_industrial_index_yoy": (0.0, 10.0),
        "core_cpi_yoy": (1.5, 1.0),
        "core_cpi_3m_change": (0.0, 0.5),
        "ppi_3m_change": (0.0, 1.5),
        "nh_industrial_3m_change": (0.0, 5.0),
        
        # 美国CAI指标
        "ism_manufacturing_pmi": (52.0, 5.0),
        "ism_services_pmi": (55.0, 5.0),
        "nonfarm_payrolls_3m_avg": (150000.0, 50000.0),
        "industrial_production_yoy": (2.0, 3.0),
        "retail_sales_yoy": (4.0, 3.0),
        "personal_consumption_yoy": (2.5, 2.0),
        "new_housing_starts": (1300.0, 200.0),
        "existing_home_sales": (500.0, 100.0),
        "initial_jobless_claims_4w": (250000.0, 50000.0),
        "credit_pulse": (0.0, 3.0),
        
        # 美国FCI指标
        "sofr_effr": (5.0, 0.5),
        "us_2y_10y_spread": (0.0, 1.0),
        "us_hy_spread": (3.5, 1.0),
        "dxy_index": (95.0, 8.0),
        "sp500_erp": (2.0, 1.0),
        
        # 美国通胀指标
        "core_pce_yoy": (2.0, 0.5),
        "eci_wage_growth": (3.0, 0.5),
        "breakeven_5y5y": (2.0, 0.3),
        "core_pce_3m_change": (0.5, 0.3),
        "eci_3m_change": (0.75, 0.3),
        "breakeven_5y5y_3m_change": (0.0, 0.2),
    }
    
    if indicator_name in params:
        mean, std = params[indicator_name]
    else:
        # 默认参数
        mean, std = 0.0, 1.0
    
    if std == 0:
        return 0.0
    
    return (value - mean) / std
