"""
Layer 3: 市场定价提取——从市场价格反推市场已定价的内容

混合模式：数值计算（ERP、信用利差等）+ LLM解读（市场定价含义）
"""

import math
from typing import Dict, List, Any, Optional
import numpy as np

from utils.constants import Z_SCORE_THRESHOLDS
from utils.signal_utils import build_layer_signal


def analyze_market_pricing(
    actual_state: Dict[str, Any],
    market_prices: Dict[str, float],
    historical_percentiles: Optional[Dict[str, List[float]]] = None,
) -> Dict[str, Any]:
    """
    从市场价格反推市场已定价的内容。
    
    Args:
        actual_state: 实际基本面状态（来自Layer 1）
            - china_cai: 中国CAI z-score
            - china_inflation: 中国通胀得分 z-score
            - us_cai: 美国CAI z-score
            - us_inflation: 美国通胀得分 z-score
        
        market_prices: 市场定价数据
            - cn_10y_yield: 中国10Y国债收益率
            - cn_2y_yield: 中国2Y国债收益率
            - us_10y_yield: 美国10Y国债收益率
            - us_2y_yield: 美国2Y国债收益率
            - cn_1y_irs: 中国1Y IRS
            - us_ffw: Fed Funds Futures隐含利率
            - csi300_pe: 沪深300 PE
            - csi300_forward_pe: 沪深300前瞻PE
            - sp500_pe: 标普500 PE
            - sp500_forward_pe: 标普500前瞻PE
            - csi300_erp: 沪深300 ERP
            - sp500_erp: 标普500 ERP
            - aa_credit_spread: AA信用利差
            - hy_credit_spread: HY信用利差
            - usd_cnh_1y_forward: USD/CNH 1Y远期点
            - copper_gold_ratio: 铜金比
        
        historical_percentiles: 历史分位数据（可选）
    
    Returns:
        市场定价分析结果
    """
    # Step 1: 利率市场反推
    rate_pricing = extract_rate_pricing(market_prices)
    
    # Step 2: 估值市场反推
    valuation_pricing = extract_valuation_pricing(market_prices, historical_percentiles)
    
    # Step 3: 汇率市场反推
    fx_pricing = extract_fx_pricing(market_prices)
    
    # Step 4: 商品市场反推
    commodity_pricing = extract_commodity_pricing(market_prices)
    
    # Step 5: 信用市场反推
    credit_pricing = extract_credit_pricing(market_prices, historical_percentiles)
    
    # Step 6: 预期差计算（实际状态 vs 市场定价）
    expected_diff = calculate_expected_diff(
        actual_state, rate_pricing, valuation_pricing, fx_pricing, commodity_pricing
    )
    
    # 构建层输出
    layer_output = build_layer_signal(
        layer_name="layer3",
        analysis_result={
            "rate_pricing": rate_pricing,
            "valuation_pricing": valuation_pricing,
            "fx_pricing": fx_pricing,
            "commodity_pricing": commodity_pricing,
            "credit_pricing": credit_pricing,
            "expected_diff": expected_diff,
        },
        direction="neutral",
        confidence=0.75,
        reasoning="市场定价提取完成",
    )
    
    return {
        "rate_pricing": rate_pricing,
        "valuation_pricing": valuation_pricing,
        "fx_pricing": fx_pricing,
        "commodity_pricing": commodity_pricing,
        "credit_pricing": credit_pricing,
        "expected_diff": expected_diff,
        "layer_output": layer_output,
    }


def extract_rate_pricing(market_prices: Dict[str, float]) -> Dict[str, Any]:
    """
    从利率市场反推增长/通胀/政策预期。
    """
    pricing = {}
    
    # 中国期限利差
    cn_10y = market_prices.get("cn_10y_yield")
    cn_2y = market_prices.get("cn_2y_yield")
    if cn_10y is not None and cn_2y is not None:
        cn_spread = cn_10y - cn_2y
        pricing["cn_term_spread"] = {
            "value": cn_spread,
            "interpretation": "增长预期" if cn_spread > 0.3 else ("衰退定价" if cn_spread < 0 else "中性"),
            "z_score": estimate_spread_zscore(cn_spread, "cn"),
        }
    
    # 美国期限利差
    us_10y = market_prices.get("us_10y_yield")
    us_2y = market_prices.get("us_2y_yield")
    if us_10y is not None and us_2y is not None:
        us_spread = us_10y - us_2y
        pricing["us_term_spread"] = {
            "value": us_spread,
            "interpretation": "增长预期" if us_spread > 0 else ("衰退定价" if us_spread < -0.5 else "中性"),
            "z_score": estimate_spread_zscore(us_spread, "us"),
        }
    
    # 中国隐含政策预期
    cn_irs = market_prices.get("cn_1y_irs")
    if cn_irs is not None:
        # IRS隐含的降息次数
        implied_cuts = max(0, (2.0 - cn_irs) / 0.25)  # 假设政策利率2.0%，每次降息25BP
        pricing["cn_implied_policy"] = {
            "value": implied_cuts,
            "interpretation": f"隐含{implied_cuts:.1f}次降息",
        }
    
    return pricing


def extract_valuation_pricing(
    market_prices: Dict[str, float],
    historical: Optional[Dict[str, List[float]]]
) -> Dict[str, Any]:
    """
    从估值市场反推盈利预期。
    """
    pricing = {}
    
    # 沪深300前瞻PE历史百分位
    csi300_fwd_pe = market_prices.get("csi300_forward_pe")
    if csi300_fwd_pe is not None:
        if historical and "csi300_forward_pe" in historical:
            percentile = calculate_percentile(csi300_fwd_pe, historical["csi300_forward_pe"])
        else:
            percentile = estimate_pe_percentile(csi300_fwd_pe, "csi300")
        
        pricing["csi300_pe_percentile"] = {
            "value": percentile,
            "interpretation": "偏高" if percentile > 80 else ("偏低" if percentile < 20 else "中性"),
        }
    
    # 标普500前瞻PE历史百分位
    sp500_fwd_pe = market_prices.get("sp500_forward_pe")
    if sp500_fwd_pe is not None:
        if historical and "sp500_forward_pe" in historical:
            percentile = calculate_percentile(sp500_fwd_pe, historical["sp500_forward_pe"])
        else:
            percentile = estimate_pe_percentile(sp500_fwd_pe, "sp500")
        
        pricing["sp500_pe_percentile"] = {
            "value": percentile,
            "interpretation": "偏高" if percentile > 80 else ("偏低" if percentile < 20 else "中性"),
        }
    
    # A股ERP
    csi300_erp = market_prices.get("csi300_erp")
    if csi300_erp is not None:
        if historical and "csi300_erp" in historical:
            percentile = calculate_percentile(csi300_erp, historical["csi300_erp"])
        else:
            percentile = estimate_erp_percentile(csi300_erp)
        
        pricing["csi300_erp"] = {
            "value": csi300_erp,
            "percentile": percentile,
            "interpretation": "ERP极高=市场过度悲观" if percentile > 80 else ("ERP极低=过度乐观" if percentile < 20 else "ERP中性"),
        }
    
    # 美股ERP
    sp500_erp = market_prices.get("sp500_erp")
    if sp500_erp is not None:
        if historical and "sp500_erp" in historical:
            percentile = calculate_percentile(sp500_erp, historical["sp500_erp"])
        else:
            percentile = estimate_erp_percentile(sp500_erp)
        
        pricing["sp500_erp"] = {
            "value": sp500_erp,
            "percentile": percentile,
            "interpretation": "ERP极高=市场过度悲观" if percentile > 80 else ("ERP极低=过度乐观" if percentile < 20 else "ERP中性"),
        }
    
    return pricing


def extract_fx_pricing(market_prices: Dict[str, float]) -> Dict[str, Any]:
    """
    从汇率市场反推资本流动预期。
    """
    pricing = {}
    
    # USD/CNH 1Y远期点
    forward_point = market_prices.get("usd_cnh_1y_forward")
    if forward_point is not None:
        # 正值=市场定价人民币贬值
        implied_depreciation = forward_point * 100  # 转换为百分比
        pricing["cnh_forward_pricing"] = {
            "value": implied_depreciation,
            "interpretation": f"隐含{implied_depreciation:.1f}%贬值预期",
            "direction": "bearish_cnh" if implied_depreciation > 0 else "bullish_cnh",
        }
    
    return pricing


def extract_commodity_pricing(market_prices: Dict[str, float]) -> Dict[str, Any]:
    """
    从商品市场反推全球需求预期。
    """
    pricing = {}
    
    # 铜金比
    copper_gold = market_prices.get("copper_gold_ratio")
    if copper_gold is not None:
        if copper_gold > 0.18:
            interpretation = "市场定价全球工业需求强劲"
        elif copper_gold < 0.12:
            interpretation = "市场定价全球工业需求疲弱"
        else:
            interpretation = "市场定价全球工业需求中性"
        
        pricing["copper_gold"] = {
            "value": copper_gold,
            "interpretation": interpretation,
        }
    
    return pricing


def extract_credit_pricing(
    market_prices: Dict[str, float],
    historical: Optional[Dict[str, List[float]]]
) -> Dict[str, Any]:
    """
    从信用市场反推风险偏好。
    """
    pricing = {}
    
    # AA信用利差
    aa_spread = market_prices.get("aa_credit_spread")
    if aa_spread is not None:
        if historical and "aa_credit_spread" in historical:
            percentile = calculate_percentile(aa_spread, historical["aa_credit_spread"])
        else:
            percentile = estimate_spread_percentile(aa_spread, "aa")
        
        pricing["aa_credit_spread"] = {
            "value": aa_spread,
            "percentile": percentile,
            "interpretation": "利差走阔=市场定价信用风险上升" if percentile > 70 else "利差收窄=信用风险偏好良好",
        }
    
    # HY信用利差
    hy_spread = market_prices.get("hy_credit_spread")
    if hy_spread is not None:
        if historical and "hy_credit_spread" in historical:
            percentile = calculate_percentile(hy_spread, historical["hy_credit_spread"])
        else:
            percentile = estimate_spread_percentile(hy_spread, "hy")
        
        pricing["hy_credit_spread"] = {
            "value": hy_spread,
            "percentile": percentile,
            "interpretation": "HY利差极阔=市场定价经济衰退" if percentile > 80 else "HY利差正常",
        }
    
    return pricing


def calculate_expected_diff(
    actual_state: Dict[str, Any],
    rate_pricing: Dict[str, Any],
    valuation_pricing: Dict[str, Any],
    fx_pricing: Dict[str, Any],
    commodity_pricing: Dict[str, Any],
) -> Dict[str, Any]:
    """
    计算预期差：实际状态 vs 市场定价。
    """
    diff = {}
    
    # 增长预期差
    actual_growth = actual_state.get("china_cai", {}).get("z_score", 0)
    rate_implied_growth = rate_pricing.get("cn_term_spread", {}).get("z_score", 0)
    if actual_growth != 0 or rate_implied_growth != 0:
        growth_diff = actual_growth - rate_implied_growth
        diff["growth_diff"] = {
            "actual": actual_growth,
            "implied": rate_implied_growth,
            "gap": growth_diff,
            "interpretation": "实际强于定价" if growth_diff > 0.5 else ("实际弱于定价" if growth_diff < -0.5 else "基本一致"),
        }
    
    # ERP预期差
    actual_cn_erp = actual_state.get("china_cai", {}).get("z_score", 0)
    implied_cn_erp = valuation_pricing.get("csi300_erp", {}).get("percentile", 50)
    if actual_cn_erp != 0:
        erp_diff = implied_cn_erp - 50  # 与中性50%比
        diff["cn_erp_diff"] = {
            "actual_cai": actual_cn_erp,
            "implied_erp_percentile": implied_cn_erp,
            "interpretation": "A股定价过度悲观" if erp_diff > 20 else ("A股定价过度乐观" if erp_diff < -20 else "ERP中性"),
        }
    
    return diff


# =============================================================================
# 辅助函数
# =============================================================================

def estimate_spread_zscore(spread: float, country: str) -> float:
    """估算利差z-score。"""
    params = {
        "cn": (0.5, 0.3),
        "us": (0.5, 1.0),
    }
    mean, std = params.get(country, (0.5, 0.5))
    return (spread - mean) / std if std != 0 else 0


def estimate_pe_percentile(pe: float, market: str) -> float:
    """估算PE历史百分位（简化版）。"""
    params = {
        "csi300": (12.0, 15.0, 20.0),  # 低,中,高
        "sp500": (15.0, 18.0, 22.0),
    }
    low, mid, high = params.get(market, (10.0, 15.0, 20.0))
    
    if pe <= low:
        return 15
    elif pe >= high:
        return 85
    else:
        return 30 + (pe - low) / (high - low) * 40


def estimate_erp_percentile(erp: float) -> float:
    """估算ERP历史百分位（简化版）。"""
    # 假设ERP均值5%，标准差2%
    mean, std = 5.0, 2.0
    z = (erp - mean) / std if std != 0 else 0
    # 转换为百分位（math.erf 与 scipy.stats.norm.cdf 数学等价）
    return min(100, max(0, 0.5 * (1 + math.erf(z / math.sqrt(2))) * 100))


def estimate_spread_percentile(spread: float, spread_type: str) -> float:
    """估算信用利差历史百分位。"""
    params = {
        "aa": (0.5, 0.3),
        "hy": (3.5, 1.0),
    }
    mean, std = params.get(spread_type, (1.0, 0.5))
    z = (spread - mean) / std if std != 0 else 0
    return min(100, max(0, 0.5 * (1 + math.erf(z / math.sqrt(2))) * 100))


def calculate_percentile(value: float, historical: List[float]) -> float:
    """计算历史百分位。"""
    if not historical:
        return 50
    count = sum(1 for v in historical if v <= value)
    return count / len(historical) * 100
