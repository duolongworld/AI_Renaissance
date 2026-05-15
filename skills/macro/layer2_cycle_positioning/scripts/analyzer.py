"""
Layer 2: 周期定位——4象限 + 政策维度 + 长期债务周期

混合模式：数值计算（Z1-Z4分数）+ LLM判断（4象限定位）
"""

from typing import Dict, List, Any, Optional, Tuple
import numpy as np

from utils.constants import (
    CHINA_POLICY_WEIGHTS,
    CycleQuadrant,
    QUADRANT_ASSET_MAPPING,
    Z_SCORE_THRESHOLDS,
)
from utils.signal_utils import build_layer_signal, determine_signal_direction


def analyze_cycle_positioning(
    china_cai_score: float,
    china_inflation_score: float,
    us_cai_score: float,
    us_inflation_score: float,
    china_policy_indicators: Optional[Dict[str, Any]] = None,
    long_term_debt_cycle_status: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    分析周期定位：4象限 + 政策维度 + 长期债务周期。
    
    Args:
        china_cai_score: 中国CAI z-score
        china_inflation_score: 中国通胀得分 z-score
        us_cai_score: 美国CAI z-score
        us_inflation_score: 美国通胀得分 z-score
        china_policy_indicators: 中国政策维度指标（可选）
            - monetary_policy: DR007 vs 政策利率、降准等
            - fiscal_policy: 专项债、财政赤字率等
            - real_estate_policy: 地产政策松紧
            - regulation_event: 监管事件
        long_term_debt_cycle_status: 长期债务周期状态（可选）
            - us: "early"/"middle"/"late"
            - cn: "upward"/"stable"/"downward"
    
    Returns:
        周期定位分析结果
    
    Example:
        >>> result = analyze_cycle_positioning(
        ...     china_cai_score=0.3,
        ...     china_inflation_score=-0.2,
        ...     us_cai_score=1.1,
        ...     us_inflation_score=0.9,
        ... )
    """
    # Step 1: 确定中国4象限
    china_quadrant = determine_quadrant(
        cai_score=china_cai_score,
        inflation_score=china_inflation_score,
        country="china"
    )
    
    # Step 2: 确定美国4象限
    us_quadrant = determine_quadrant(
        cai_score=us_cai_score,
        inflation_score=us_inflation_score,
        country="us"
    )
    
    # Step 3: 计算政策维度得分
    policy_score = calculate_policy_score(china_policy_indicators)
    
    # Step 4: 应用政策调节
    adjusted_china_quadrant = apply_policy_adjustment(
        quadrant=china_quadrant,
        policy_score=policy_score
    )
    
    # Step 5: 确定长期债务周期位置
    debt_cycle = {
        "us": long_term_debt_cycle_status.get("us", "middle") if long_term_debt_cycle_status else "middle",
        "cn": long_term_debt_cycle_status.get("cn", "stable") if long_term_debt_cycle_status else "stable",
    }
    
    # Step 6: 周期一致性校验
    cycle_consistency = check_cycle_consistency(
        china_quadrant=adjusted_china_quadrant,
        us_quadrant=us_quadrant,
        debt_cycle=debt_cycle
    )
    
    # 构建层输出
    layer_output = build_layer_signal(
        layer_name="layer2",
        analysis_result={
            "china_quadrant": china_quadrant,
            "china_quadrant_adjusted": adjusted_china_quadrant,
            "us_quadrant": us_quadrant,
            "policy_score": policy_score,
            "debt_cycle": debt_cycle,
            "cycle_consistency": cycle_consistency,
        },
        direction=adjusted_china_quadrant.get("direction", "neutral"),
        confidence=0.75,
        reasoning=f"中国: {adjusted_china_quadrant['quadrant']}, 美国: {us_quadrant['quadrant']}, 政策调节: {policy_score:.1f}",
    )
    
    return {
        "china_quadrant": china_quadrant,
        "china_quadrant_adjusted": adjusted_china_quadrant,
        "us_quadrant": us_quadrant,
        "policy_score": policy_score,
        "debt_cycle": debt_cycle,
        "cycle_consistency": cycle_consistency,
        "layer_output": layer_output,
    }


def determine_quadrant(
    cai_score: float,
    inflation_score: float,
    country: str = "china"
) -> Dict[str, Any]:
    """
    根据CAI和通胀得分确定4象限。
    
    4象限定义：
    - 复苏（Recovery）: CAI > 0, 通胀下行/中性
    - 过热（Overheating）: CAI > 0, 通胀上行
    - 滞胀（Stagnation）: CAI < 0, 通胀上行
    - 衰退（Recession）: CAI < 0, 通胀下行/中性
    
    Args:
        cai_score: CAI z-score
        inflation_score: 通胀得分 z-score
        country: 国家标识 ("china" 或 "us")
    
    Returns:
        象限信息字典
    """
    # 使用0作为阈值
    cai_positive = cai_score > 0
    inflation_positive = inflation_score > 0
    
    if cai_positive and not inflation_positive:
        quadrant = CycleQuadrant.RECOVERY.value
        quadrant_cn = "复苏"
        direction = "bullish"  # 复苏利好风险资产
    elif cai_positive and inflation_positive:
        quadrant = CycleQuadrant.OVERHEATING.value
        quadrant_cn = "过热"
        direction = "bullish"  # 过热期间商品/资源受益
    elif not cai_positive and inflation_positive:
        quadrant = CycleQuadrant.STAGNATION.value
        quadrant_cn = "滞胀"
        direction = "neutral"  # 滞胀环境复杂
    else:
        quadrant = CycleQuadrant.RECESSION.value
        quadrant_cn = "衰退"
        direction = "bearish"  # 衰退期间防御为主
    
    # 受益/受损资产
    asset_mapping = QUADRANT_ASSET_MAPPING.get(quadrant, {})
    
    return {
        "quadrant": quadrant,
        "quadrant_cn": quadrant_cn,
        "cai_score": cai_score,
        "inflation_score": inflation_score,
        "direction": direction,
        "beneficial_assets": asset_mapping.get("beneficial", []),
        "harmful_assets": asset_mapping.get("harmful", []),
    }


def calculate_policy_score(
    policy_indicators: Optional[Dict[str, Any]] = None
) -> float:
    """
    计算中国政策维度综合得分。
    
    权重：货币政策0.4 + 财政政策0.3 + 地产政策0.25 + 监管事件0.05
    
    评分规则：
    - 宽松: +1
    - 中性: 0
    - 收紧: -1
    
    Args:
        policy_indicators: 政策指标字典
    
    Returns:
        加权政策得分 (-1.0 ~ +1.0)
    """
    if not policy_indicators:
        return 0.0
    
    scores = []
    weights = []
    
    # 货币政策
    if "monetary_policy" in policy_indicators:
        scores.append(_score_policy_direction(policy_indicators["monetary_policy"]))
        weights.append(CHINA_POLICY_WEIGHTS["monetary_policy"])
    
    # 财政政策
    if "fiscal_policy" in policy_indicators:
        scores.append(_score_policy_direction(policy_indicators["fiscal_policy"]))
        weights.append(CHINA_POLICY_WEIGHTS["fiscal_policy"])
    
    # 地产政策
    if "real_estate_policy" in policy_indicators:
        scores.append(_score_policy_direction(policy_indicators["real_estate_policy"]))
        weights.append(CHINA_POLICY_WEIGHTS["real_estate_policy"])
    
    # 监管事件
    if "regulation_event" in policy_indicators:
        scores.append(_score_policy_direction(policy_indicators["regulation_event"]))
        weights.append(CHINA_POLICY_WEIGHTS["regulation_event"])
    
    if not scores:
        return 0.0
    
    # 加权平均
    return sum(s * w for s, w in zip(scores, weights)) / sum(weights)


def _score_policy_direction(direction: str) -> float:
    """将政策方向转换为分数。"""
    mapping = {
        "easy": 1.0,
        "loose": 1.0,
        "宽松": 1.0,
        "neutral": 0.0,
        "中性": 0.0,
        "tight": -1.0,
        "收紧": -1.0,
    }
    return mapping.get(direction, 0.0)


def apply_policy_adjustment(
    quadrant: Dict[str, Any],
    policy_score: float,
    threshold: float = 0.5
) -> Dict[str, Any]:
    """
    应用政策维度调节。
    
    规则：
    - 政策综合得分 > +0.5：4象限受益资产信号强度+1档
    - 政策综合得分 < -0.5：4象限受益资产信号强度-1档
    - 政策得分在±0.5之间：不做幅度调节
    
    Args:
        quadrant: 原始象限信息
        policy_score: 政策得分
        threshold: 调节阈值
    
    Returns:
        调节后的象限信息
    """
    adjusted = quadrant.copy()
    
    if policy_score > threshold:
        adjustment = "+1"
        adjusted["signal_strength"] = "增强"
    elif policy_score < -threshold:
        adjustment = "-1"
        adjusted["signal_strength"] = "减弱"
    else:
        adjustment = "0"
        adjusted["signal_strength"] = "不变"
    
    adjusted["policy_adjustment"] = adjustment
    adjusted["policy_score"] = policy_score
    
    return adjusted


def check_cycle_consistency(
    china_quadrant: Dict[str, Any],
    us_quadrant: Dict[str, Any],
    debt_cycle: Dict[str, str]
) -> Dict[str, Any]:
    """
    周期一致性校验。
    
    规则：
    1. 全球周期优先：若全球（美国）与国内周期分歧，以全球周期定大方向
    2. 恐慌状态直接下调：若全球风险模块触发恐慌状态，直接下调至观望/看空
    3. 中美分化仅输出结构性信号：中美周期严重分化时，不得输出全面看涨/看空信号
    
    Args:
        china_quadrant: 中国象限
        us_quadrant: 美国象限
        debt_cycle: 债务周期状态
    
    Returns:
        校验结果
    """
    china_direction = china_quadrant.get("direction", "neutral")
    us_direction = us_quadrant.get("direction", "neutral")
    
    # 判断中美周期是否一致
    if china_direction == us_direction:
        consistency = "一致"
        final_direction = china_direction
        adjustment_note = "中美周期方向一致"
    else:
        consistency = "分化"
        # 规则1：全球周期优先
        final_direction = us_direction
        adjustment_note = "中美周期分化，以美国周期定大方向"
    
    # 规则3：中美严重分化时的限制
    if consistency == "分化":
        # 严重分化时不下达全面信号
        if china_direction != us_direction:
            final_direction = "neutral"  # 改为中性
            adjustment_note += "（分化严重，降为中性）"
    
    return {
        "consistency": consistency,
        "final_direction": final_direction,
        "adjustment_note": adjustment_note,
        "china_direction": china_direction,
        "us_direction": us_direction,
        "debt_cycle_adjustment": _get_debt_cycle_adjustment(debt_cycle),
    }


def _get_debt_cycle_adjustment(debt_cycle: Dict[str, str]) -> str:
    """
    获取长期债务周期调节建议。
    """
    adjustments = []
    
    # 美国
    if debt_cycle.get("us") == "late":
        adjustments.append("美国长期债务周期末端：提高黄金/商品权重+10-20%，降低长期名义债券权重-10%")
    elif debt_cycle.get("us") == "early":
        adjustments.append("美国长期债务周期早期：可适度增加长久期债券配置")
    
    # 中国
    if debt_cycle.get("cn") == "downward":
        adjustments.append("中国长期债务周期下行：降低长期名义债券权重-10%，提高高股息/红利资产权重+5-10%")
    elif debt_cycle.get("cn") == "upward":
        adjustments.append("中国长期债务周期上行：可适度增加长久期债券配置")
    
    return "; ".join(adjustments) if adjustments else "无特殊调节"


# =============================================================================
# LLM 调用接口（供 Agent 使用）
# =============================================================================

LLM_PROMPT_TEMPLATE = """
# Layer 2: 周期定位——4象限 + 政策维度 + 长期债务周期

## 分析任务

根据以下数据，完成周期定位分析：

### 中国经济状态
- CAI z-score: {china_cai}
- 通胀得分 z-score: {china_inflation}
- 当前象限: {china_quadrant}

### 美国经济状态
- CAI z-score: {us_cai}
- 通胀得分 z-score: {us_inflation}
- 当前象限: {us_quadrant}

### 政策维度
- 货币政策: {monetary_policy}
- 财政政策: {fiscal_policy}
- 地产政策: {real_estate_policy}
- 综合得分: {policy_score}

### 长期债务周期
- 美国: {us_debt_cycle}
- 中国: {cn_debt_cycle}

## 分析要求

1. 确认中美4象限定位是否正确
2. 评估政策调节力度
3. 评估中美周期一致性
4. 给出最终周期定位结论
5. 给出资产配置建议

## 输出格式

```json
{{
    "china_quadrant_confirmed": "复苏/过热/滞胀/衰退",
    "us_quadrant_confirmed": "复苏/过热/滞胀/衰退",
    "policy_adjustment": "+1/0/-1",
    "cycle_consistency": "一致/分化",
    "final_direction": "bullish/bearish/neutral",
    "asset_recommendation": {{
        "overweight": ["资产1", "资产2"],
        "underweight": ["资产3", "资产4"],
        "neutral": ["资产5"]
    }},
    "key_reasoning": "核心逻辑说明"
}}
```
"""


def generate_llm_prompt(
    china_cai: float,
    china_inflation: float,
    us_cai: float,
    us_inflation: float,
    policy_score: float,
    debt_cycle: Dict[str, str],
) -> str:
    """
    生成 LLM 分析提示词。
    """
    return LLM_PROMPT_TEMPLATE.format(
        china_cai=china_cai,
        china_inflation=china_inflation,
        us_cai=us_cai,
        us_inflation=us_inflation,
        monetary_policy="待评估（需读取政策文本）",
        fiscal_policy="待评估（需读取财政数据）",
        real_estate_policy="待评估（需读取地产政策）",
        policy_score=policy_score,
        us_debt_cycle=debt_cycle.get("us", "待评估"),
        cn_debt_cycle=debt_cycle.get("cn", "待评估"),
    )
