"""
宏观分析 Skill 工具模块

提供权重表、阈值常量、Signal构建工具等共享功能。
"""

from .constants import *
from .signal_utils import *

__all__ = [
    # 权重表
    "CHINA_CAI_WEIGHTS",
    "CHINA_FCI_WEIGHTS", 
    "US_CAI_WEIGHTS",
    "US_FCI_WEIGHTS",
    "CHINA_INFLATION_WEIGHTS",
    "US_INFLATION_WEIGHTS",
    "CHINA_POLICY_WEIGHTS",
    
    # 阈值常量
    "Z_SCORE_THRESHOLDS",
    "RISK_LEVEL_THRESHOLDS",
    "SIGNAL_INTENSITY_THRESHOLDS",
    "REFLEXIVITY_PRESSURE_THRESHOLDS",
    
    # 信号工具函数
    "build_macro_signal",
    "build_layer_signal",
    "calculate_confidence",
    "determine_risk_level",
]
