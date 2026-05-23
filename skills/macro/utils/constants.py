"""
宏观分析 Skill 常量定义

包含各层分析所需的权重表、阈值、枚举值等常量。
"""

from typing import Dict, List
from enum import Enum


# =============================================================================
# Layer 名称枚举
# =============================================================================

class LayerName(Enum):
    """7层流水线各层名称"""
    LAYER0_TRACKING = "layer0_tracking"
    LAYER1_CAI_FCI = "layer1_cai_fci"
    LAYER2_CYCLE = "layer2_cycle_positioning"
    LAYER25_HUB = "layer2_5_hub_variable"
    LAYER3_PRICING = "layer3_market_pricing"
    LAYER4_EXPECTED_DIFF = "layer4_expected_diff"
    LAYER45_REFLEXIVITY = "layer4_5_reflexivity"
    LAYER5_ALLOCATION = "layer5_asset_allocation"


class CycleQuadrant(Enum):
    """美林时钟四象限"""
    RECOVERY = "recovery"      # 复苏
    OVERHEATING = "overheating"  # 过热
    STAGNATION = "stagnation"    # 滞胀
    RECESSION = "recession"      # 衰退


class InteractionLevel(Enum):
    """中美交互层次"""
    SYMMETRIC = "symmetric"           # 对称交互
    ASYMMETRIC = "asymmetric"         # 非对称传导
    FEEDBACK_LOOP = "feedback_loop"   # 反馈循环


class PolicyDirection(Enum):
    """政策方向"""
    EASY = "easy"       # 宽松
    NEUTRAL = "neutral" # 中性
    TIGHT = "tight"     # 收紧


class ReflexivityPressure(Enum):
    """反身性压力等级"""
    GREEN = "green"   # 低压力
    YELLOW = "yellow" # 中压力
    ORANGE = "orange" # 高压力
    RED = "red"       # 极高压


class ParadigmStability(Enum):
    """范式稳定性"""
    STABLE = "stable"           # 稳定
    SHAKEN = "shaken"           # 动摇
    SHIFT = "shift"             # 转移


class LogicLifecycle(Enum):
    """逻辑生命周期"""
    EMBRYONIC = "embryonic"     # 萌芽期
    DIFFUSION = "diffusion"     # 扩散期
    CONSENSUS = "consensus"     # 共识期
    BEYOND = "beyond"           # 透支期
    COLLAPSE = "collapse"       # 崩塌期


class GlobalMacroTriangle(Enum):
    """全球宏观三角"""
    GLOBAL_TIGHTENING = "global_tightening"  # 全球紧缩
    GLOBAL_EASING = "global_easing"          # 全球宽松
    STAGFLATION = "stagflation"              # 滞胀
    DEFLATION = "deflation"                  # 通缩


# =============================================================================
# Layer 1: CAI/FCI 权重表
# =============================================================================

# 中国版 CAI（Current Activity Indicator）权重表
# 来源：需求文档 7.2 节
CHINA_CAI_WEIGHTS: Dict[str, float] = {
    # 实体活动（权重合计 0.52）
    "industrial_added_value_yoy": 0.15,  # 工业增加值同比
    "caixin_manufacturing_pmi": 0.08,    # 财新制造业PMI
    "nbs_manufacturing_pmi": 0.07,       # 统计局制造业PMI
    
    # 信用流动（权重合计 0.30）
    "total_social_financing_yoy": 0.18,  # 社融存量同比
    "credit_impulse_12m": 0.12,          # 信贷脉冲（12M滚动）
    
    # 地产链（权重合计 0.13）
    "commercial_housing_sales_yoy": 0.08,  # 商品房销售面积同比
    "real_estate_investment_yoy": 0.05,     # 地产开发投资同比
    
    # 消费（权重合计 0.10）
    "retail_sales_yoy": 0.06,      # 社会消费品零售同比
    "passenger_car_sales_yoy": 0.04,  # 乘用车销量同比
    
    # 外需（权重合计 0.07）
    "export_yoy_usd": 0.05,      # 出口同比（美元计）
    "ccfi_index": 0.02,         # CCFI运价指数
    
    # 高频补充（权重合计 0.10）
    "power_consumption_yoy": 0.04,  # 发电耗煤同比
    "blast_furnace_rate": 0.03,     # 高炉开工率
    "metro_passenger_flow": 0.03,   # 地铁客流（10城合计）
}

# 中国版 FCI（Financial Conditions Index）权重表
# 方向统一为"越高越紧"
CHINA_FCI_WEIGHTS: Dict[str, float] = {
    "dr007_shibor_3m": 0.20,   # 银行间流动性松紧
    "cn_1y_10y_spread": 0.15,  # 收益率曲线斜率（正=宽松预期）
    "aa_credit_spread": 0.20,   # 信用利差（宽=紧）
    "cny_reer": 0.15,          # 汇率松紧（高=紧）
    "csi_300_erp": 0.30,      # 股权风险溢价（高=金融条件紧）
}

# 美国版 CAI 权重表（需回测校准）
# 来源：需求文档 7.2 节
US_CAI_WEIGHTS: Dict[str, float] = {
    # 需回测校准，先使用等权重
    "ism_manufacturing_pmi": 0.11,
    "ism_services_pmi": 0.11,
    "nonfarm_payrolls_3m_avg": 0.11,
    "industrial_production_yoy": 0.11,
    "retail_sales_yoy": 0.11,
    "personal_consumption_yoy": 0.11,
    "new_housing_starts": 0.11,
    "existing_home_sales": 0.11,
    "initial_jobless_claims_4w": 0.11,
    "credit_pulse": 0.01,  # 权重较小，需回测校准
}

# 美国版 FCI 权重表
US_FCI_WEIGHTS: Dict[str, float] = {
    "sofr_effr": 0.15,           # 联邦基金利率
    "us_2y_10y_spread": 0.15,    # 收益率曲线斜率
    "us_hy_spread": 0.20,        # 高收益债利差
    "dxy_index": 0.15,           # 美元指数
    "sp500_erp": 0.35,           # 标普500股权风险溢价
}

# 中国通胀得分权重（水平 + 动量双维度合成）
CHINA_INFLATION_WEIGHTS: Dict[str, float] = {
    # 水平维度
    "core_cpi_yoy": 0.17,
    "ppi_yoy": 0.17,
    "nh_industrial_index_yoy": 0.17,
    # 动量维度
    "core_cpi_3m_change": 0.17,
    "ppi_3m_change": 0.17,
    "nh_industrial_3m_change": 0.17,
}

# 美国通胀得分权重
US_INFLATION_WEIGHTS: Dict[str, float] = {
    # 水平维度
    "core_pce_yoy": 0.25,
    "eci_wage_growth": 0.17,
    "breakeven_5y5y": 0.08,
    # 动量维度
    "core_pce_3m_change": 0.25,
    "eci_3m_change": 0.17,
    "breakeven_5y5y_3m_change": 0.08,
}

# 中国政策维度权重表
CHINA_POLICY_WEIGHTS: Dict[str, float] = {
    "monetary_policy": 0.40,   # 货币政策
    "fiscal_policy": 0.30,    # 财政政策
    "real_estate_policy": 0.25,  # 地产政策
    "regulation_event": 0.05,  # 监管事件
}


# =============================================================================
# Layer 2.5: 汇率分析权重表
# =============================================================================

# USD/CNH 方向得分权重
CNH_DIRECTION_WEIGHTS: Dict[str, float] = {
    "interest_rate_spread": 0.30,   # 利差驱动
    "current_account": 0.20,         # 经常账户
    "risk_appetite": 0.20,          # 风险偏好
    "policy_intent": 0.30,          # 政策意图
}


# =============================================================================
# Layer 4.5: 反身性压力计权重
# =============================================================================

# 反身性压力计四项指标权重（各25%，满分100分）
REFLEXIVITY_PRESSURE_WEIGHTS: Dict[str, float] = {
    "signal_crowding": 0.25,       # 信号拥挤度
    "position_concentration": 0.25,  # 仓位集中度
    "self_fulfilling_index": 0.25,   # 信号自我实现指数
    "cross_framework_consensus": 0.25,  # 跨框架一致性
}


# =============================================================================
# z-score 标准化参数
# =============================================================================

Z_SCORE_WINDOW: int = 5 * 252  # 5年滚动窗口（日频数据）

Z_SCORE_THRESHOLDS: Dict[str, float] = {
    "strong_signal": 1.5,    # 强信号阈值
    "very_strong_signal": 2.0,  # 极强信号阈值
    "direction_confirm": 1.0,    # 方向确认阈值
    "direction_neutral": 0.5,    # 中性阈值
}


# =============================================================================
# 置信度计算参数
# =============================================================================

CONFIDENCE_BASE_THRESHOLDS: List[float] = [0.80, 0.60, 0.50, 0.0]
CONFIDENCE_BASE_VALUES: List[float] = [0.9, 0.7, 0.5, 0.3]

SIGNAL_INTENSITY_THRESHOLDS: Dict[str, float] = {
    "strong_signal": 80.0,   # 强信号（≥80%分位）
    "effective_signal": 50.0,  # 有效信号（50%-80%分位）
    "weak_signal": 0.0,        # 弱信号（<50%分位）
}

# 信号强度与 Alpha 偏离系数映射
SIGNAL_TO_ALPHA_COEFFICIENT: Dict[str, float] = {
    "strong_signal": 0.3,     # 强度≥80%，偏离系数0.3
    "medium_strong": 0.2,      # 强度60%-80%，偏离系数0.2
    "weak": 0.1,              # 强度50%-60%，偏离系数0.1
    "invalid": 0.0,           # 强度<50%，不产生偏离
}


# =============================================================================
# 风险等级判定参数
# =============================================================================

RISK_LEVEL_THRESHOLDS: Dict[str, Dict] = {
    "low": {
        "vix_spike": 10,        # VIX单日攀升上限
        "csi300_drop": 3.0,     # 沪深300单日跌幅上限（%）
        "northbound_outflow": 100,  # 北向资金单日净流出上限（亿）
    },
    "high": {
        "vix_spike": 10,        # VIX单日攀升下限
        "vix_level": 30,         # VIX绝对水平下限
        "csi300_drop": 5.0,     # 沪深300单日跌幅下限（%）
        "northbound_outflow": 200,  # 北向资金单日净流出下限（亿）
    },
}

# Sahm Rule 衰退预警阈值
SAHM_RULE_THRESHOLD: float = 0.5


# =============================================================================
# 反身性压力等级阈值
# =============================================================================

REFLEXIVITY_PRESSURE_THRESHOLDS: Dict[str, float] = {
    "green_max": 30,    # 绿色上限
    "yellow_max": 50,   # 黄色上限
    "orange_max": 70,   # 橙色上限
    "red_min": 70,      # 红色下限
}

# 反身性压力修正系数
REFLEXIVITY_PRESSURE_COEFFICIENT: Dict[str, float] = {
    "green": 1.0,
    "yellow": 0.75,
    "orange": 0.50,
    "red": 0.25,
}


# =============================================================================
# 范式稳定性修正系数
# =============================================================================

PARADIGM_STABILITY_COEFFICIENT: Dict[str, float] = {
    "stable": 1.0,
    "shaken": 0.7,
    "shift": 0.0,  # 仅维持Beta
}


# =============================================================================
# 逻辑生命周期修正系数
# =============================================================================

LIFECYCLE_COEFFICIENT: Dict[str, float] = {
    "embryonic": 1.0,
    "diffusion": 0.9,
    "consensus": 0.6,
    "beyond": 0.3,
    "collapse": 0.0,
}


# =============================================================================
# Layer 5: 资产配置参数
# =============================================================================

# Beta 基准权重（中国版 All Weather）
BETA_BENCHMARK_WEIGHTS: Dict[str, float] = {
    "csi300_500": 0.15,      # A股（沪深300+中证500）
    "cn_gov_bond": 0.35,      # 中国国债
    "nh_industrial": 0.15,    # 南华工业品
    "gold": 0.15,            # 黄金
    "us_assets": 0.20,       # 美元资产
}

# 风险预算约束
RISK_BUDGET_CONSTRAINTS: Dict[str, float] = {
    "beta_volatility_cap": 0.08,     # Beta层年化波动率上限 8%
    "alpha_volatility_cap": 0.12,    # Alpha层年化波动率上限 12%
    "single_signal_max_deviation": 0.30,   # 单信号最大偏离 ±30%
    "single_asset_max_deviation": 0.50,     # 单资产最大权重偏离 ±50%
    "max_drawdown_hard_cap": 0.15,         # 最大回撤硬性上限 15%
    "leverage_cap": 1.5,                    # 组合杠杆上限 1.5x
}


# =============================================================================
# 信号衰减参数
# =============================================================================

SIGNAL_DECAY_PARAMS: Dict[str, Dict] = {
    # 类型A：高频意外（2-4周有效期）
    "type_a": {
        "initial_validity_weeks": 4,
        "weekly_decay_rate": 0.25,
    },
    # 类型B：基本面vs定价（1-3个月有效期）
    "type_b": {
        "initial_validity_months": 3,
        "monthly_decay_rate": 0.20,
    },
    # 类型C：跨国预期差（1-3个月有效期）
    "type_c": {
        "initial_validity_months": 3,
        "monthly_decay_rate": 0.15,
    },
}


# =============================================================================
# 中美传导通道定义
# =============================================================================

TRANSMISSION_CHANNELS: List[Dict] = [
    {
        "id": 1,
        "name": "利差→资本流→A股",
        "start": "中美10Y利差",
        "mediator": "北向资金净流入",
        "end": "A股核心资产",
        "layers": ["layer0", "layer1"],
    },
    {
        "id": 2,
        "name": "美元→大宗→PPI→周期股",
        "start": "DXY美元指数",
        "mediator": "原油/铜/南华工业品",
        "end": "A股周期股、PPI",
        "layers": ["layer2_5"],
    },
    {
        "id": 3,
        "name": "美联储→风险偏好→港股",
        "start": "美国实际利率TIPS",
        "mediator": "VIX、美元流动性",
        "end": "港股、长久期成长股",
        "layers": ["layer0", "layer1"],
    },
    {
        "id": 4,
        "name": "中国信贷→全球大宗",
        "start": "中国社融脉冲",
        "mediator": "铁矿石、铜价",
        "end": "全球周期资产",
        "layers": ["layer1", "layer2_5"],
    },
    {
        "id": 5,
        "name": "全球PMI→中国出口",
        "start": "全球制造业PMI",
        "mediator": "韩国/越南出口同比",
        "end": "中国出口、制造业股",
        "layers": ["layer0"],
    },
    {
        "id": 6,
        "name": "地缘政治→风险溢价",
        "start": "中美关系事件",
        "mediator": "VIX、CNH波动率",
        "end": "港股、CNH、半导体",
        "layers": ["layer0", "layer2_5"],
    },
]


# =============================================================================
# 行业轮动映射
# =============================================================================

INDUSTRY_CYCLE_MAPPING: Dict[str, Dict] = {
    "recovery": {      # 复苏周期
        "leading": ["钢铁", "有色", "建材", "银行", "非银金融", "可选消费"],
        "defensive": ["消费", "医药"],
        "avoid": ["高估值成长", "纯主题板块"],
    },
    "overheating": {  # 扩张周期
        "leading": ["新能源", "工业机械", "半导体设备", "出口链"],
        "defensive": ["银行"],
        "avoid": ["强周期资源类（高位兑现）"],
    },
    "stagflation": {  # 滞胀周期
        "leading": ["上游资源", "农业", "黄金"],
        "defensive": ["公用事业", "消费必选"],
        "avoid": ["高杠杆成长", "地产链"],
    },
    "recession": {     # 衰退周期
        "leading": ["公用事业", "必选消费", "高股息红利资产"],
        "defensive": ["高分红红利资产"],
        "avoid": ["强周期", "可选消费", "科技成长"],
    },
}


# =============================================================================
# 四象限资产映射
# =============================================================================

QUADRANT_ASSET_MAPPING: Dict[str, Dict] = {
    "recovery": {  # 复苏
        "beneficial": ["权益", "信用债", "周期股"],
        "harmful": ["长久期国债", "黄金"],
    },
    "overheating": {  # 过热
        "beneficial": ["大宗商品", "上游资源", "通胀保值债"],
        "harmful": ["长久期国债", "成长股"],
    },
    "stagflation": {  # 滞胀
        "beneficial": ["黄金", "短债", "必选消费"],
        "harmful": ["权益", "信用债", "长久期国债"],
    },
    "recession": {  # 衰退
        "beneficial": ["长久期国债", "利率债", "高股息"],
        "harmful": ["权益", "大宗商品", "周期股"],
    },
}
