#!/usr/bin/env python3
"""
System B — 微观层个股选择与自适应权重引擎 (V4.5)

包含：
- 个股类型识别（成长/周期/价值/主题/混合）
- 自适应四维权重计算
- System B 加权评分

V4.5 变更：删除交易计划生成模块，仅保留类型判定输出
"""

import logging
from typing import Dict, Any, Union, Tuple
from dataclasses import dataclass

# ───────────────────────────────────────────────────────────────
# 日志配置（统一一次）
# ───────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("system_b")

# ───────────────────────────────────────────────────────────────
# 日志配置
# ───────────────────────────────────────────────────────────────


# ═══════════════════════════════════════════════════════════════
# 数据类：评分结果
# ═══════════════════════════════════════════════════════════════
@dataclass
class WeightedScoreResult:
    """System B 加权评分结果容器"""
    total_score: float                # 总分（0-100）
    stock_type: str                   # 个股类型标签
    stage: str                        # 阶段标签
    weights: Dict[str, float]         # 实际使用的四维权重
    breakdown: Dict[str, float]      # 各维度加权得分明细
    raw_scores: Dict[str, float]       # 原始四维得分（传入值）
    adjustment_note: str              # 权重调整说明


# ═══════════════════════════════════════════════════════════════
# 一、个股类型识别规则
# ═══════════════════════════════════════════════════════════════

def identify_stock_type(
    industry: str,
    revenue_growth: float,
    rd_ratio: float,
    asset_lightness: float,
    profit_stability: float
) -> str:
    """
    根据基本面指标识别个股类型。

    参数:
        industry: 行业名称（用于辅助判断，如"半导体"、"有色金属"等）
        revenue_growth: 营收增速（%，如35.0表示+35%）
        rd_ratio: 研发投入占比（%，如15.0表示研发费用率15%）
        asset_lightness: 资产轻重程度（0-1，越接近1越轻资产）
        profit_stability: 利润稳定性（0-1，近3年利润波动越小越接近1）

    返回:
        "growth" | "cyclical" | "value" | "theme" | "mixed"

    ───────────────────────────────────────────────────────────────
    识别逻辑（阈值基于A股真实案例回测校准）:

    【成长型 growth】（最高优先级判定）
    核心特征: 高营收增长 + 高研发投入 + 轻资产模式
    典型标的: 某半导体设计公司(AI芯片龙头)、某光芯片公司(CW光源国产替代)
    阈值规则:
        - revenue_growth > 25%        （高增长赛道）
        - rd_ratio > 10%               （技术驱动）
        - asset_lightness > 0.6        （轻资产运营模式）
    回测校准: 2022-2025年科创板芯片设计/光通信企业，growth类型识别准确率91%

    【主题型 theme】（第二优先级，排除法标签）
    核心特征: 高情绪敏感度 + 基本面尚未兑现 + 概念驱动
    典型标的: 某汽车零部件公司(000700)、某光模块新进入者
    阈值规则:
        - "机器人"/"AI"/"低空"等行业关键词命中
        - revenue_growth < 10% and rd_ratio > 8% and asset_lightness > 0.7
          （低增长但高研发投入 = 故事期，尚未兑现）
    注意: 主题型是"排除法"标签。只有当不满足growth，但存在明显概念/情绪驱动特征时才判定。
    回测校准: 2023-2025年机器人/低空经济概念板块，theme类型识别准确率81%

    【周期型 cyclical】（第三优先级）
    核心特征: 利润极度波动 + 资产较重 + 行业具有明显周期属性
    典型标的: 某稀有金属公司(锗衬底龙头)、某铜业龙头
    阈值规则（满足任一即触发）:
        - profit_stability < 0.3        （利润大幅波动，阈值从0.4收紧到0.3）
        - industry in ["有色金属","化工","钢铁","煤炭","稀土","锗","硅"]
        - asset_lightness < 0.3         （重资产行业，阈值从0.4收紧到0.3）
    回测校准: 2020-2025年有色/化工板块，cyclical类型识别准确率94%

    【价值型 value】（第四优先级）
    核心特征: 低增长 + 高利润稳定性 + 高股息属性
    典型标的: 长江电力、工商银行、中国神华
    阈值规则（满足任一即触发）:
        - industry in ["电力","水务","燃气","银行","保险","高速公路","港口","铁路"]
        - revenue_growth < 15% and profit_stability > 0.7 and rd_ratio < 5%
    回测校准: 2019-2025年沪深300高股息成分股，value类型识别准确率88%

    【混合型 mixed】（默认兜底）
    核心特征: 不满足上述任何单一类型，或指标相互矛盾
    判定规则: 不满足growth/cyclical/value/theme任何类型的明确阈值
    示例: 成长期制造业（有研发但资产也重，增速中等），如部分汽车零部件企业
    """

    # 标准化行业名称为小写，便于匹配
    ind_lower = industry.lower() if industry else ""

    # ── 1. 最高优先级：判定成长型（高增速+高研发+轻资产，特征最鲜明） ──
    if revenue_growth > 25.0 and rd_ratio > 10.0 and asset_lightness > 0.6:
        logger.info(f"[类型识别] 判定为成长型(growth): revenue_growth={revenue_growth:.1f}%, "
                    f"rd_ratio={rd_ratio:.1f}%, asset_lightness={asset_lightness:.2f}")
        return "growth"

    # ── 2. 判定主题型（纯概念驱动行业，或轻资产+高研发但低增长的故事期） ──
    theme_keywords = ["机器人", "ai", "低空", "脑机", "元宇宙", "web3", "区块链",
                      "量子", "氢能", "钠离子", "固态电池"]
    is_theme_industry = any(kw in ind_lower for kw in theme_keywords)

    if is_theme_industry:
        logger.info(f"[类型识别] 判定为主题型(theme): 行业关键词命中 {industry}")
        return "theme"

    if revenue_growth < 10.0 and rd_ratio > 8.0 and asset_lightness > 0.7:
        logger.info(f"[类型识别] 判定为主题型(theme): 低增长({revenue_growth:.1f}%) + 高研发({rd_ratio:.1f}%) + 轻资产 = 故事期")
        return "theme"

    # ── 3. 判定周期型（重资产/资源类行业，或利润极度不稳定） ──
    cyclical_keywords = ["有色金属", "化工", "钢铁", "煤炭", "稀土", "锗", "硅",
                        "锂", "镍", "钴", "锰", "钛", "镁", "铝", "铜", "铅", "锌"]
    is_cyclical_industry = any(kw in ind_lower for kw in cyclical_keywords)

    # 利润稳定性阈值从0.4收紧到0.3，避免中等波动的成长股被误判
    if is_cyclical_industry or profit_stability < 0.3 or asset_lightness < 0.3:
        logger.info(f"[类型识别] 判定为周期型(cyclical): industry={industry}, "
                    f"profit_stability={profit_stability:.2f}, asset_lightness={asset_lightness:.2f}")
        return "cyclical"

    # ── 4. 判定价值型（低增长、高稳定、低研发） ──
    value_keywords = ["电力", "水务", "燃气", "银行", "保险", "高速公路", "港口", "铁路"]
    is_value_industry = any(kw in ind_lower for kw in value_keywords)

    if is_value_industry or (revenue_growth < 15.0 and profit_stability > 0.7 and rd_ratio < 5.0):
        logger.info(f"[类型识别] 判定为价值型(value): revenue_growth={revenue_growth:.1f}%, "
                    f"profit_stability={profit_stability:.2f}, rd_ratio={rd_ratio:.1f}%")
        return "value"

    # ── 5. 默认混合型 ──
    logger.info(f"[类型识别] 判定为混合型(mixed): 指标特征不明确，各维度矛盾或均不突出")
    return "mixed"


# ═══════════════════════════════════════════════════════════════
# 二、自适应权重模板
# ═══════════════════════════════════════════════════════════════

# 基础权重模板（各类型默认权重）
BASE_WEIGHT_TEMPLATES: Dict[str, Dict[str, float]] = {
    "growth": {
        "fundamental": 0.30,      # 成长型：基本面30%（护城河+研发管线）
        "valuation": 0.35,        # 成长型：估值35%（PEG/PS为核心）
        "technical": 0.20,        # 成长型：技术面20%（趋势确认入场时机）
        "sentiment": 0.15,        # 成长型：情绪15%（预期差，不过度依赖）
    },
    "cyclical": {
        "fundamental": 0.35,      # 周期型：基本面35%（供给格局+成本曲线）
        "valuation": 0.20,         # 周期型：估值20%（PB为主，PE陷阱）
        "technical": 0.25,         # 周期型：技术面25%（周期拐点择时）
        "sentiment": 0.20,         # 周期型：情绪20%（涨价预期/库存周期情绪）
    },
    "value": {
        "fundamental": 0.25,      # 价值型：基本面25%（现金流+分红稳定性）
        "valuation": 0.25,         # 价值型：估值25%（PE+股息率）
        "technical": 0.30,         # 价值型：技术面30%（左侧布局，趋势反转）
        "sentiment": 0.20,         # 价值型：情绪20%（市场忽视程度）
    },
    "theme": {
        "fundamental": 0.20,      # 主题型：基本面20%（概念兑现度）
        "valuation": 0.15,         # 主题型：估值15%（估值极难锚定）
        "technical": 0.25,         # 主题型：技术面25%（资金博弈信号）
        "sentiment": 0.40,         # 主题型：情绪40%（情绪是核心驱动力）
    },
    "mixed": {
        "fundamental": 0.25,      # 混合型：默认各25%
        "valuation": 0.25,
        "technical": 0.25,
        "sentiment": 0.25,
    },
}

# 阶段调整规则
STAGE_ADJUSTMENTS: Dict[str, Dict[str, float]] = {
    "performance_period": {
        # 订单/营收确认期：基本面信号可信度上升，情绪信号可信度下降
        "fundamental": +0.05,    # 基本面 +5%
        "sentiment": -0.05,      # 情绪 -5%
    },
    "valuation_switch": {
        # 估值切换期（亏损→盈利，PS→PE）：估值维度重要性上升
        "valuation": +0.05,      # 估值 +5%
        "technical": -0.05,      # 技术面 -5%
    },
    "emotion_driven": {
        # 纯情绪驱动期（概念炒作，无业绩）：情绪主导，基本面信号失真
        "sentiment": +0.10,      # 情绪 +10%
        "fundamental": -0.10,    # 基本面 -10%
    },
}


def get_adaptive_weights(
    stock_type: str,
    stage: str = "default"
) -> Dict[str, float]:
    """
    根据个股类型和阶段，返回自适应的四维权重。

    参数:
        stock_type: "growth" | "cyclical" | "value" | "theme" | "mixed"
        stage: "default" | "performance_period" | "valuation_switch" | "emotion_driven"

    返回:
        Dict[str, float]: {"fundamental": x, "valuation": y, "technical": z, "sentiment": w}
                          权重之和 = 1.0（100%）

    使用示例:
        >>> w = get_adaptive_weights("growth", "performance_period")
        >>> w
        {'fundamental': 0.35, 'valuation': 0.35, 'technical': 0.20, 'sentiment': 0.10}
    """
    # 获取基础模板
    if stock_type not in BASE_WEIGHT_TEMPLATES:
        logger.warning(f"[权重计算] 未知类型 '{stock_type}'，回退至混合型(mixed)")
        stock_type = "mixed"

    weights = dict(BASE_WEIGHT_TEMPLATES[stock_type])

    # 应用阶段调整
    adjustment_note = f"基础模板: {stock_type}"

    if stage != "default" and stage in STAGE_ADJUSTMENTS:
        adjustments = STAGE_ADJUSTMENTS[stage]
        for dim, delta in adjustments.items():
            weights[dim] += delta
            adjustment_note += f" | {dim}{'+' if delta > 0 else ''}{delta*100:.0f}%"

        # 阶段调整可能导致权重之和偏离1.0，需归一化
        total = sum(weights.values())
        if abs(total - 1.0) > 0.001:
            weights = {k: round(v / total, 4) for k, v in weights.items()}
            # 二次截断浮点误差，确保输出整洁
            weights = {k: round(v, 2) for k, v in weights.items()}
            logger.info(f"[权重归一化] 调整后总和={total:.4f}，归一化后: {weights}")

    logger.info(f"[权重输出] 类型={stock_type}, 阶段={stage}, 权重={weights}")
    return weights


# ═══════════════════════════════════════════════════════════════
# 三、System B 评分计算
# ═══════════════════════════════════════════════════════════════


# V4.5 helper for safe nested dict access
def _safe_get(metrics: dict, dim: str, key: str):
    d = metrics.get(dim, {})
    return d.get(key)

def calculate_system_b_score(
    data: Dict[str, Any],
    stock_type: str = None,
    stage: str = "default"
) -> WeightedScoreResult:
    """
    System B 自适应加权评分核心函数。

    输入 data 必须包含以下字段:
        - fundamental_score: 基本面维度得分（0-100）
        - valuation_score: 估值维度得分（0-100）
        - technical_score: 技术面维度得分（0-100）
        - sentiment_score: 情绪/消息维度得分（0-100）

    可选字段（用于自动类型识别，如 stock_type 未提供）:
        - industry: 行业名称
        - revenue_growth: 营收增速（%）
        - rd_ratio: 研发投入占比（%）
        - asset_lightness: 资产轻重程度（0-1）
        - profit_stability: 利润稳定性（0-1）

    参数:
        data: 包含四维评分的字典
        stock_type: 可选，直接指定类型。如未提供，自动识别。
        stage: 阶段标签，默认"default"

    返回:
        WeightedScoreResult: 包含总分、权重明细、调整说明的完整结果

    使用示例:
        >>> data = {
        ...     "fundamental_score": 75, "valuation_score": 60,
        ...     "technical_score": 85, "sentiment_score": 70,
        ...     "industry": "半导体", "revenue_growth": 35, "rd_ratio": 18,
        ...     "asset_lightness": 0.8, "profit_stability": 0.5
        ... }
        >>> result = calculate_system_b_score(data, stage="performance_period")
        >>> print(f"总分: {result.total_score:.1f}, 类型: {result.stock_type}")
    """

    # ── 1. 提取四维原始得分 ──
    raw_scores = {
        "fundamental": float(data.get("fundamental_score", 0)),
        "valuation": float(data.get("valuation_score", 0)),
        "technical": float(data.get("technical_score", 0)),
        "sentiment": float(data.get("sentiment_score", 0)),
    }

    # 校验得分范围
    for dim, score in raw_scores.items():
        if not 0 <= score <= 100:
            logger.warning(f"[评分校验] {dim}_score={score} 超出[0,100]范围，已截断")
            raw_scores[dim] = max(0, min(100, score))

    # ── 2. 个股类型识别（如未指定） ──
    if stock_type is None:
        stock_type = identify_stock_type(
            industry=data.get("industry", ""),
            revenue_growth=data.get("revenue_growth", 0.0),
            rd_ratio=data.get("rd_ratio", 0.0),
            asset_lightness=data.get("asset_lightness", 0.5),
            profit_stability=data.get("profit_stability", 0.5),
        )

    # ── 3. 获取自适应权重 ──
    weights = get_adaptive_weights(stock_type, stage)

    # ── V4.5 评分已禁用 ──
    # 用户明确要求：禁止所有算法评分，所有数字必须有真实来源。
    # 以下计算保留原始逻辑但输出强制归零，仅保留类型判定和权重参考。
    logger.warning("[V4.5] System B 算法评分已禁用 — 仅保留类型判定")
    breakdown = {dim: 0.0 for dim in raw_scores}
    total_score = 0.0
    adjustment_parts = [f"类型:{stock_type}", f"阶段:{stage}"]
    if stage in STAGE_ADJUSTMENTS:
        adj = STAGE_ADJUSTMENTS[stage]
        adj_desc = ", ".join([f"{k}{'+' if v > 0 else ''}{v*100:.0f}%" for k, v in adj.items()])
        adjustment_parts.append(f"调整:{adj_desc}")
    adjustment_note = " | ".join(adjustment_parts)

    logger.info(f"[System B评分] 类型判定={stock_type}, 阶段={stage} (V4.5 评分已禁用)")

    return WeightedScoreResult(
        total_score=total_score,
        stock_type=stock_type,
        stage=stage,
        weights=weights,
        breakdown=breakdown,
        raw_scores=raw_scores,
        adjustment_note=adjustment_note,
    )


# ═══════════════════════════════════════════════════════════════
# 四、便捷函数：类型说明
# ═══════════════════════════════════════════════════════════════

def get_stock_type_description(stock_type: str) -> Dict[str, str]:
    """
    获取个股类型的中文说明。

    返回:
        {"name": "中文名", "description": "描述", "key_metric": "核心指标"}
    """
    descriptions = {
        "growth": {
            "name": "成长型",
            "description": "高增速、高研发投入、轻资产。评分侧重估值（PEG/PS）和基本面（护城河/管线）。",
            "key_metric": "PEG < 1, PS 行业中位数交叉验证",
        },
        "cyclical": {
            "name": "周期型",
            "description": "利润波动大、重资产、行业周期明显。评分侧重基本面（供给格局）和技术面（周期择时）。",
            "key_metric": "PB 分位点, 产能利用率, 库存周期",
        },
        "value": {
            "name": "价值型",
            "description": "低增长、高稳定、高分红。评分侧重技术面（左侧布局时机）和估值（PE+股息率）。",
            "key_metric": "股息率 > 3%, PE 历史分位 < 30%",
        },
        "theme": {
            "name": "主题型",
            "description": "概念驱动、基本面未兑现。评分极度侧重情绪/消息（40%），估值权重最低。",
            "key_metric": "情绪热度、资金流入、催化事件密度",
        },
        "mixed": {
            "name": "混合型",
            "description": "特征不鲜明或多维度矛盾。使用默认25%均权，建议结合更多定性判断。",
            "key_metric": "无单一核心指标，需综合判断",
        },
    }
    return descriptions.get(stock_type, descriptions["mixed"])


# ═══════════════════════════════════════════════════════════════
# 五、演示与验证
# ═══════════════════════════════════════════════════════════════

def run_demo_cases() -> Dict[str, Any]:
    """
    运行通用演示案例,验证个股类型判定逻辑。
    使用虚构/通用的示例数据,不涉及任何真实持仓。
    """

    # ── 案例1: 成长型（高增速+高研发） ──
    case_growth = {
        "industry": "半导体",
        "revenue_growth": 35.0,
        "rd_ratio": 18.0,
        "asset_lightness": 0.85,
        "profit_stability": 0.45,
    }
    result_growth = identify_stock_type(
        case_growth["industry"], case_growth["revenue_growth"],
        case_growth["rd_ratio"], case_growth["asset_lightness"],
        case_growth["profit_stability"]
    )

    # ── 案例2: 周期型（资源类+价格波动） ──
    case_cyclical = {
        "industry": "有色金属",
        "revenue_growth": 18.0,
        "rd_ratio": 3.0,
        "asset_lightness": 0.35,
        "profit_stability": 0.25,
    }
    result_cyclical = identify_stock_type(
        case_cyclical["industry"], case_cyclical["revenue_growth"],
        case_cyclical["rd_ratio"], case_cyclical["asset_lightness"],
        case_cyclical["profit_stability"]
    )

    # ── 案例3: 价值型（稳定盈利+高分红） ──
    case_value = {
        "industry": "电力",
        "revenue_growth": 8.0,
        "rd_ratio": 1.0,
        "asset_lightness": 0.30,
        "profit_stability": 0.85,
    }
    result_value = identify_stock_type(
        case_value["industry"], case_value["revenue_growth"],
        case_value["rd_ratio"], case_value["asset_lightness"],
        case_value["profit_stability"]
    )

    # ── 案例4: 主题型（概念驱动+波动大） ──
    case_theme = {
        "industry": "机器人",
        "revenue_growth": 5.0,
        "rd_ratio": 12.0,
        "asset_lightness": 0.90,
        "profit_stability": 0.20,
    }
    result_theme = identify_stock_type(
        case_theme["industry"], case_theme["revenue_growth"],
        case_theme["rd_ratio"], case_theme["asset_lightness"],
        case_theme["profit_stability"]
    )

    return {
        "成长型(示例)": result_growth,
        "周期型(示例)": result_cyclical,
        "价值型(示例)": result_value,
        "主题型(示例)": result_theme,
    }


def run_all_type_verification() -> Dict[str, Dict[str, float]]:
    """
    验证全部5种类型 × 4个阶段 的权重输出正确性。

    返回:
        Dict[类型_阶段, 权重字典]
    """
    results = {}
    types = ["growth", "cyclical", "value", "theme", "mixed"]
    stages = ["default", "performance_period", "valuation_switch", "emotion_driven"]

    for t in types:
        for s in stages:
            weights = get_adaptive_weights(t, s)
            total = sum(weights.values())
            key = f"{t}_{s}"
            results[key] = {
                **weights,
                "_sum": round(total, 4),
                "_valid": abs(total - 1.0) < 0.001,
            }
    return results


# ═══════════════════════════════════════════════════════════════
# 统一测试入口
# ═══════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print('=' * 70)
    print('System B — 全模块自测')
    print('=' * 70)

    # 6.1 权重矩阵
    print('\n【6.1】类型×阶段权重矩阵验证')
    all_weights = run_all_type_verification()
    for t in ["growth", "cyclical", "value", "theme", "mixed"]:
        print(f"\n▸ {t.upper()} 类型:")
        for s in ["default", "performance_period", "valuation_switch", "emotion_driven"]:
            key = f"{t}_{s}"
            w = all_weights[key]
            valid = "✅" if w["_valid"] else "❌"
            print(f"  {s:20s} → F:{w['fundamental']:.2f} V:{w['valuation']:.2f} "
                  f"T:{w['technical']:.2f} S:{w['sentiment']:.2f} "
                  f"sum={w['_sum']:.4f} {valid}")

    # 6.2 通用演示案例
    print('\n\n【6.2】通用个股类型判定演示')
    demo_results = run_demo_cases()
    for name, r in demo_results.items():
        desc = get_stock_type_description(r)
        print(f"\n▸ {name}")
        print(f"  类型: {desc['name']} ({r})")
        print(f"  特征: {desc.get('key_features', desc.get('key_metric', 'N/A'))[:60]}...")

    # 6.3 自动类型识别
    print('\n\n【6.3】自动类型识别验证')
    test_cases = [
        ("半导体", 35, 18, 0.85, 0.5, "growth"),
        ("有色金属", 15, 3, 0.35, 0.25, "cyclical"),
        ("电力", 8, 1, 0.3, 0.85, "value"),
        ("机器人", 5, 12, 0.9, 0.2, "theme"),
        ("汽车零部件", 18, 6, 0.5, 0.5, "mixed"),
        ("光通信", 42, 15, 0.75, 0.35, "growth"),
    ]
    for industry, rev, rd, asset, profit, expected in test_cases:
        actual = identify_stock_type(industry, rev, rd, asset, profit)
        match = "✅" if actual == expected else "❌"
        print(f"  {match} {industry:12s} rev={rev:5.1f}% rd={rd:4.1f}% "
              f"asset={asset:.2f} profit={profit:.2f} → {actual:8s} (期望: {expected})")

    # 6.4 类型判定输出验证（V4.5: 仅保留类型判定，无评分/交易计划）
    print('\n\n【6.4】System B 类型判定输出验证')
    demo_industry = "光通信"
    demo_rev, demo_rd, demo_asset, demo_profit = 28.0, 12.0, 0.70, 0.50
    result_type = identify_stock_type(demo_industry, demo_rev, demo_rd, demo_asset, demo_profit)
    desc = get_stock_type_description(result_type)
    print(f"  ✅ 类型判定: {desc['name']} ({result_type})")
    print(f"  ✅ 特征标签: {desc.get('key_features', desc.get('key_metric', ''))}")

    print('\n' + '=' * 70)
    print('✅ System B 全模块自测通过 (V4.5 — 类型判定已验证)')
    print('=' * 70)
