"""
A股大盘社区讨论情绪数据源

通过东财大盘股吧（上证指数吧 + 创业板吧）采集社区讨论数据，
计算讨论热度、多空比例、极化度等指标，供舆情 Agent 调用。

复用 eastmoney_guba.py 的 fetch_and_parse_page() 函数。

设计原则：单个数据源失败不影响整体输出，优雅降级。
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from loguru import logger

from .eastmoney_guba import fetch_and_parse_page
from .keywords import BULLISH_KEYWORDS, BEARISH_KEYWORDS, calc_sentiment_ratio

try:
    import numpy as np
    NP_AVAILABLE = True
except ImportError:
    NP_AVAILABLE = False


# 大盘股吧代码
MARKET_BOARD_CODES = {
    "上证指数": "zssh000001",
    "创业板指": "zssz399006",
}

# 抓取页数（每页约20条帖子）
DEFAULT_PAGES = 3


class CommunitySentimentDataSource:
    """大盘社区讨论情绪数据源"""

    def __init__(self):
        self.name = "大盘社区讨论情绪数据源"
        self._bullish_kw = set(BULLISH_KEYWORDS)
        self._bearish_kw = set(BEARISH_KEYWORDS)
        logger.info(f"[数据源] {self.name} 初始化完成")

    def get_community_sentiment(self, pages: int = DEFAULT_PAGES) -> Dict[str, Any]:
        """
        采集大盘级社区讨论数据

        Returns:
            {
                "status": "success" | "partial" | "error",
                "fetch_time": str,
                "sources": {
                    "eastmoney_guba": {
                        "boards": [...],
                        "total_posts": int,
                    }
                },
                "aggregate": {
                    "total_posts": int,
                    "total_reads": int,
                    "total_replies": int,
                    "discussion_volume_score": float,  # 0-100
                    "bullish_ratio": float,
                    "bearish_ratio": float,
                    "polarization": float,
                    "volume_trend": str,  # "rising"/"stable"/"declining"
                },
                "raw_data": {...},
            }
        """
        all_posts: List[Dict[str, Any]] = []
        seen_ids = set()
        board_results = {}
        errors = []

        for board_name, board_code in MARKET_BOARD_CODES.items():
            try:
                posts = self._fetch_board_posts(board_name, board_code, pages)
                new_posts = [p for p in posts if p["post_id"] not in seen_ids]
                for p in new_posts:
                    seen_ids.add(p["post_id"])
                all_posts.extend(new_posts)
                board_results[board_name] = {
                    "code": board_code,
                    "posts_fetched": len(new_posts),
                }
                logger.info(
                    f"[{self.name}] {board_name}({board_code}) 获取 {len(new_posts)} 条帖子"
                )
            except Exception as e:
                logger.warning(f"[{self.name}] {board_name} 抓取失败: {e}")
                board_results[board_name] = {"code": board_code, "error": str(e)}
                errors.append(f"{board_name}: {e}")

        if not all_posts:
            return self._error_result(errors or ["未获取到任何帖子"])

        # 计算情绪比例
        sentiment = calc_sentiment_ratio(
            all_posts, self._bullish_kw, self._bearish_kw
        )

        # 计算讨论热度
        total_reads = sum(p.get("reads", 0) for p in all_posts)
        total_replies = sum(p.get("replies", 0) for p in all_posts)
        volume_score = self._calculate_discussion_volume_score(
            len(all_posts), total_reads, total_replies
        )

        # 讨论量趋势（简化：基于帖子回复/阅读比推断活跃度）
        volume_trend = self._estimate_volume_trend(all_posts)

        status = "success" if not errors else "partial"

        return {
            "status": status,
            "fetch_time": datetime.now().isoformat(),
            "sources": {
                "eastmoney_guba": {
                    "boards": board_results,
                    "total_posts": len(all_posts),
                }
            },
            "aggregate": {
                "total_posts": len(all_posts),
                "total_reads": total_reads,
                "total_replies": total_replies,
                "discussion_volume_score": volume_score,
                "bullish_ratio": round(sentiment["bullish_ratio"], 3),
                "bearish_ratio": round(sentiment["bearish_ratio"], 3),
                "polarization": round(sentiment["polarization"], 3),
                "volume_trend": volume_trend,
            },
            "raw_data": {
                "bullish_count": sentiment["bullish_count"],
                "bearish_count": sentiment["bearish_count"],
                "neutral_count": sentiment["neutral_count"],
                "weighted_bullish": round(sentiment["weighted_bullish"], 2),
                "weighted_bearish": round(sentiment["weighted_bearish"], 2),
            },
        }

    # ── 内部方法 ──────────────────────────────

    def _fetch_board_posts(
        self, board_name: str, board_code: str, pages: int
    ) -> List[Dict[str, Any]]:
        """抓取大盘板块股吧帖子"""
        all_posts = []
        for page in range(1, pages + 1):
            url = f"https://guba.eastmoney.com/list,{board_code}_{page}.html"
            try:
                posts = fetch_and_parse_page(url)
                for p in posts:
                    p["board_name"] = board_name
                    p["board_code"] = board_code
                all_posts.extend(posts)
            except Exception as e:
                logger.warning(
                    f"[{self.name}] {board_name} 第{page}页抓取失败: {e}"
                )
        return all_posts

    def _calculate_discussion_volume_score(
        self, total_posts: int, total_reads: int, total_replies: int
    ) -> float:
        """
        计算讨论热度分数 (0-100)

        映射逻辑（基于大盘股吧日常帖量）：
        - 0-50帖  → 0-20分  (极冷)
        - 50-200帖 → 20-40分 (冷)
        - 200-500帖 → 40-60分 (正常)
        - 500-1000帖 → 60-80分 (热)
        - >1000帖 → 80-100分 (极热)
        """
        if total_posts <= 0:
            return 0.0

        # 帖量分段线性映射
        if total_posts <= 50:
            score = total_posts / 50 * 20
        elif total_posts <= 200:
            score = 20 + (total_posts - 50) / 150 * 20
        elif total_posts <= 500:
            score = 40 + (total_posts - 200) / 300 * 20
        elif total_posts <= 1000:
            score = 60 + (total_posts - 500) / 500 * 20
        else:
            score = 80 + min((total_posts - 1000) / 1000 * 20, 20)

        # 互动量加成（阅读+回复异常高时适当提分）
        if total_reads > 50000 or total_replies > 500:
            score = min(100, score + 5)

        return round(max(0, min(100, score)), 1)

    def _estimate_volume_trend(self, posts: List[Dict[str, Any]]) -> str:
        """
        估算讨论量趋势

        简化逻辑：比较热门帖和最新帖的互动量比
        - 热门帖互动远大于最新帖 → declining（话题在降温）
        - 最新帖互动接近热门帖 → rising（话题在升温）
        - 差异不大 → stable
        """
        hot_posts = [p for p in posts if p.get("source_type") == "hot"]
        latest_posts = [p for p in posts if p.get("source_type") != "hot"]

        if not hot_posts or not latest_posts:
            # 没有区分热度类型时，按回复量中位数判断
            if len(posts) < 5:
                return "stable"
            replies = [p.get("replies", 0) for p in posts]
            replies_sorted = sorted(replies, reverse=True)
            top_half_avg = sum(replies_sorted[: len(replies_sorted) // 2]) / max(
                len(replies_sorted) // 2, 1
            )
            bottom_half_avg = sum(replies_sorted[len(replies_sorted) // 2 :]) / max(
                len(replies_sorted) - len(replies_sorted) // 2, 1
            )
            if bottom_half_avg == 0:
                return "declining"
            ratio = top_half_avg / bottom_half_avg
            if ratio > 3:
                return "declining"
            elif ratio < 1.5:
                return "rising"
            return "stable"

        hot_avg_replies = sum(p.get("replies", 0) for p in hot_posts) / len(hot_posts)
        latest_avg_replies = sum(p.get("replies", 0) for p in latest_posts) / len(
            latest_posts
        )

        if hot_avg_replies == 0:
            return "stable"

        ratio = latest_avg_replies / hot_avg_replies
        if ratio > 0.6:
            return "rising"
        elif ratio < 0.3:
            return "declining"
        return "stable"

    def _error_result(self, errors: List[str]) -> Dict[str, Any]:
        return {
            "status": "error",
            "fetch_time": datetime.now().isoformat(),
            "sources": {},
            "aggregate": {
                "total_posts": 0,
                "total_reads": 0,
                "total_replies": 0,
                "discussion_volume_score": 0.0,
                "bullish_ratio": 0.5,
                "bearish_ratio": 0.5,
                "polarization": 0.0,
                "volume_trend": "stable",
            },
            "raw_data": {},
            "errors": errors,
        }
