"""
共享情绪分析关键词与计算函数

供 agent 层和数据源层共用，避免关键词和情绪计算逻辑重复定义。
"""

from typing import Any, Dict, List, Set


# ── 看多关键词 ──────────────────────────────
BULLISH_KEYWORDS = [
    "利好", "大涨", "牛", "突破", "加仓", "看好", "买入",
    "反弹", "低估", "抄底", "龙头", "强势", "放量", "涨停",
    "新高", "主力", "加码", "上涨", "翻倍", "暴涨", "启动",
    "涨", "增持", "回购", "绩优", "白马", "价值", "分红",
    "业绩超预期", "订单", "扩产", "供不应求", "景气",
]

# ── 看空关键词 ──────────────────────────────
BEARISH_KEYWORDS = [
    "利空", "大跌", "熊", "破位", "减仓", "看空", "卖出",
    "暴跌", "高估", "泡沫", "跌停", "破发", "减持", "暴雷",
    "做空", "恐慌", "下跌", "腰斩", "崩盘", "套牢", "割肉",
    "跌", "亏损", "退市", "风险", "违规", "处罚", "造假",
    "暴亏", "资金链", "违约", "ST", "退",
]


def calc_sentiment_ratio(
    posts: List[Dict[str, Any]],
    bullish_kw: Set[str],
    bearish_kw: Set[str],
    hot_weight: float = 1.5,
    high_reads_threshold: int = 1000,
    high_reads_weight: float = 1.2,
    content_weight: float = 1.3,
) -> Dict[str, Any]:
    """
    通用帖子情绪分析，计算多空比例与极化度。

    Args:
        posts: 帖子列表，每个帖子需含 title 字段，可选 content/source_type/reads
        bullish_kw: 看多关键词集合
        bearish_kw: 看空关键词集合
        hot_weight: 热门帖子权重倍数
        high_reads_threshold: 高阅读量阈值
        high_reads_weight: 高阅读量权重倍数
        content_weight: 有正文的帖子权重倍数

    Returns:
        {
            "bullish_ratio": float,
            "bearish_ratio": float,
            "polarization": float,
            "weighted_bullish": float,
            "weighted_bearish": float,
            "bullish_count": int,
            "bearish_count": int,
            "neutral_count": int,
            "bullish_posts": list,
            "bearish_posts": list,
            "neutral_posts": list,
        }
    """
    weighted_bullish = 0.0
    weighted_bearish = 0.0
    bullish_posts = []
    bearish_posts = []
    neutral_posts = []

    for post in posts:
        text = post.get("title", "")
        if post.get("content"):
            text = text + " " + post["content"]

        weight = 1.0
        if post.get("source_type") == "hot":
            weight *= hot_weight
        if post.get("reads", 0) >= high_reads_threshold:
            weight *= high_reads_weight
        if post.get("content"):
            weight *= content_weight

        bull_hits = sum(1 for kw in bullish_kw if kw in text)
        bear_hits = sum(1 for kw in bearish_kw if kw in text)

        if bull_hits > bear_hits:
            weighted_bullish += weight
            bullish_posts.append(post)
        elif bear_hits > bull_hits:
            weighted_bearish += weight
            bearish_posts.append(post)
        else:
            neutral_posts.append(post)

    total = weighted_bullish + weighted_bearish
    bullish_ratio = weighted_bullish / total if total > 0 else 0.5
    bearish_ratio = 1.0 - bullish_ratio
    polarization = abs(bullish_ratio - bearish_ratio)

    return {
        "bullish_ratio": bullish_ratio,
        "bearish_ratio": bearish_ratio,
        "polarization": polarization,
        "weighted_bullish": weighted_bullish,
        "weighted_bearish": weighted_bearish,
        "bullish_count": len(bullish_posts),
        "bearish_count": len(bearish_posts),
        "neutral_count": len(neutral_posts),
        "bullish_posts": bullish_posts,
        "bearish_posts": bearish_posts,
        "neutral_posts": neutral_posts,
    }
