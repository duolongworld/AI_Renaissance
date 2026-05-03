"""
舆情情感 Agent - 专家6组

signal_type: news
Skill 域: skills/news/ + skills/data/
核心能力：新闻情感分析、社交情绪追踪、把情绪变成可交易信号

架构分层：
  - 数据获取：调用 skills/data/eastmoney_guba（东方财富股吧帖子抓取）
  - 情绪分析：调用 skills/news/market_emotion_discovery（市场情绪极端发现）
  - Agent 本身：只做编排，不硬编码任何数据获取或分析逻辑
"""

import re
from datetime import datetime
from typing import Dict, Any, List, Optional

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

from agents.base import BaseAgent
from agents.signal import Signal, bullish_signal, bearish_signal, neutral_signal
from loguru import logger


# ── 情绪分析关键词（从 market_emotion_discovery Skill 规则提取） ──────

BULLISH_KEYWORDS = [
    "利好", "大涨", "牛", "突破", "加仓", "看好", "买入",
    "反弹", "低估", "抄底", "龙头", "强势", "放量", "涨停",
    "新高", "主力", "加码", "上涨", "翻倍", "暴涨", "启动",
    "涨", "增持", "回购", "绩优", "白马", "价值", "分红",
    "业绩超预期", "订单", "扩产", "供不应求", "景气",
]

BEARISH_KEYWORDS = [
    "利空", "大跌", "熊", "破位", "减仓", "看空", "卖出",
    "暴跌", "高估", "泡沫", "跌停", "破发", "减持", "暴雷",
    "做空", "恐慌", "下跌", "腰斩", "崩盘", "套牢", "割肉",
    "跌", "亏损", "退市", "风险", "违规", "处罚", "造假",
    "暴亏", "资金链", "违约", "ST", "退",
]

# 热门帖子权重倍数
HOT_POST_WEIGHT = 1.5
# 高阅读量阈值
HIGH_READS_THRESHOLD = 1000
HIGH_READS_WEIGHT = 1.2

# 置信度配置
MAX_CONFIDENCE = 0.8
BULLISH_THRESHOLD = 0.6
BEARISH_THRESHOLD = 0.4


class NewsAgent(BaseAgent):
    """
    舆情情感 Agent（专家6组）

    编排两层 Skill：
      1. 数据获取层：skills/data/eastmoney_guba → 抓取股吧帖子原始数据
      2. 分析层：skills/news/market_emotion_discovery → 市场情绪极端发现

    Agent 本身不硬编码爬取逻辑，数据获取委托给数据层 Skill，
    情绪分析逻辑遵循 market_emotion_discovery Skill 规则。
    """

    signal_type = "news"

    def __init__(self, config: Optional[dict] = None):
        super().__init__(name="舆情情感Agent", config=config or {})
        # 加载分析层 Skill（market_emotion_discovery）
        self.load_skills_from_domain("news")
        # 加载数据获取层 Skill（eastmoney_guba）
        self.load_skills_from_domain("data")

    def analyze(self, stock_code: str) -> Signal:
        """
        分析指定股票的股吧舆情

        流程：
        1. 调用数据获取层 Skill 获取原始帖子数据
        2. 按 market_emotion_discovery Skill 规则进行情绪分析
        3. 输出标准 Signal（signal_type="news"）

        Args:
            stock_code: 股票代码，如 "600519"、"sz300757"

        Returns:
            Signal: 标准化舆情信号
        """
        code = self._normalize_code(stock_code)
        self.log(f"开始分析 {code} 的股吧舆情")
        self.log(f"已加载 Skill: {self.list_skills()}")

        # ── 第1步：数据获取（委托 skills/data/eastmoney_guba） ──
        try:
            guba_data = self._fetch_guba_data(code)
        except Exception as e:
            self.log(f"抓取股吧数据失败: {e}", level="error")
            return neutral_signal(
                confidence=0.3,
                reasoning=f"抓取股吧数据失败: {e}",
                source=self.name,
                stock_code=code,
                signal_type=self.signal_type,
                meta={
                    "output_version": "0.1",
                    "skill_name": "market_emotion_discovery",
                    "data_skill": "eastmoney_guba",
                    "owner_group": "专家6组（舆情）",
                    "target": code,
                    "needs_human_review": True,
                    "uncertainties": [f"数据抓取失败: {e}"],
                },
            )

        if guba_data.get("status") != "success" or not guba_data.get("posts"):
            self.log(f"未获取到 {code} 的股吧帖子", level="warning")
            return neutral_signal(
                confidence=0.3,
                reasoning=f"未获取到 {code} 的股吧帖子数据",
                source=self.name,
                stock_code=code,
                signal_type=self.signal_type,
                meta={
                    "output_version": "0.1",
                    "skill_name": "market_emotion_discovery",
                    "data_skill": "eastmoney_guba",
                    "owner_group": "专家6组（舆情）",
                    "target": code,
                    "needs_human_review": True,
                    "uncertainties": ["未获取到帖子数据"],
                },
            )

        posts = guba_data["posts"]
        self.log(f"数据获取层返回 {len(posts)} 条帖子")

        # ── 第2步：情绪分析（遵循 market_emotion_discovery Skill 规则） ──
        analysis = self._analyze_sentiment(posts)

        # ── 第3步：构建 Signal ──
        return self._build_signal(code, analysis)

    # ── 数据获取层（委托 skills/data/eastmoney_guba） ──────────────

    def _fetch_guba_data(self, code: str) -> Dict[str, Any]:
        """
        调用数据获取层 Skill 获取股吧帖子

        优先使用 Skill 的脚本执行数据获取，
        如果脚本不可用则回退到内嵌的轻量实现。
        """
        if not HAS_REQUESTS:
            return {
                "status": "error",
                "stock_code": code,
                "error": "requests 库未安装",
                "posts": [],
            }

        # 尝试通过 Skill 脚本获取数据
        skill_content = self.get_skill("eastmoney_guba")
        if skill_content:
            self.log("使用 skills/data/eastmoney_guba Skill 获取数据")

        # 调用 Skill 脚本中的函数
        try:
            # 动态导入 Skill 脚本
            import importlib.util
            repo_root = self._find_repo_root()
            script_path = repo_root / "skills" / "data" / "eastmoney_guba" / "scripts" / "fetch_guba.py"

            if script_path.exists():
                spec = importlib.util.spec_from_file_location("fetch_guba", str(script_path))
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)

                pages = self.config.get("pages", 2)
                fetch_content = self.config.get("fetch_content", True)
                result = mod.fetch_guba_posts(
                    stock_code=code,
                    pages=pages,
                    fetch_content=fetch_content,
                )
                self.log(f"Skill 脚本返回 {len(result.get('posts', []))} 条帖子")
                return result
        except Exception as e:
            self.log(f"Skill 脚本执行失败，回退到内嵌实现: {e}", level="warning")

        # 回退：内嵌的轻量数据获取实现
        return self._fetch_guba_fallback(code)

    def _fetch_guba_fallback(self, code: str) -> Dict[str, Any]:
        """
        内嵌的轻量数据获取（回退方案）

        当 Skill 脚本不可用时使用，逻辑与 skills/data/eastmoney_guba/scripts/fetch_guba.py 一致
        """
        from skills.data.eastmoney_guba.scripts.fetch_guba import fetch_guba_posts
        return fetch_guba_posts(
            stock_code=code,
            pages=self.config.get("pages", 2),
            fetch_content=self.config.get("fetch_content", True),
        )

    # ── 情绪分析层（遵循 market_emotion_discovery Skill 规则） ──────

    def _normalize_code(self, code: str) -> str:
        """标准化股票代码，去除市场前缀"""
        code = code.strip().upper()
        for prefix in ("SH", "SZ", "BJ"):
            if code.startswith(prefix):
                code = code[len(prefix):]
                break
        return code

    def _analyze_sentiment(self, posts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        基于 market_emotion_discovery Skill 规则的情绪分析

        分析流程（遵循 SKILL.md 第3节）：
        1. 计算情绪综合指数（关键词匹配 + 加权统计）
        2. 判断情绪状态（狂热/恐慌/中性）
        3. 判断方向和置信度（逆向逻辑：狂热→bearish，恐慌→bullish）
        4. 提取证据和风险说明
        """
        bullish_keywords = set(BULLISH_KEYWORDS)
        bearish_keywords = set(BEARISH_KEYWORDS)

        weighted_bullish = 0.0
        weighted_bearish = 0.0
        bullish_posts = []
        bearish_posts = []
        neutral_posts = []

        for post in posts:
            # 合并标题和正文进行分析
            text = post.get("title", "")
            if post.get("content"):
                text = text + " " + post["content"]

            # 计算权重
            weight = 1.0
            if post.get("source_type") == "hot":
                weight *= HOT_POST_WEIGHT
            if post.get("reads", 0) >= HIGH_READS_THRESHOLD:
                weight *= HIGH_READS_WEIGHT
            # 有正文的帖子额外加权
            if post.get("content"):
                weight *= 1.3

            # 关键词匹配
            bull_hits = sum(1 for kw in bullish_keywords if kw in text)
            bear_hits = sum(1 for kw in bearish_keywords if kw in text)

            if bull_hits > bear_hits:
                weighted_bullish += weight
                bullish_posts.append(post)
            elif bear_hits > bull_hits:
                weighted_bearish += weight
                bearish_posts.append(post)
            else:
                neutral_posts.append(post)

        # 计算情绪比例（对应 SKILL.md 第3步：情绪综合指数）
        total = weighted_bullish + weighted_bearish
        if total == 0:
            bullish_ratio = 0.5
        else:
            bullish_ratio = weighted_bullish / total
        bearish_ratio = 1.0 - bullish_ratio

        # 计算情绪极化度（SKILL.md 第3步）
        polarization = abs(bullish_ratio - bearish_ratio)

        # 判断情绪状态和方向（SKILL.md 第4步 + 第6步）
        # 逆向逻辑：狂热→bearish，恐慌→bullish
        if bullish_ratio > 0.75 and polarization > 0.4:
            # 狂热状态 → 逆向看空
            direction = "bearish"
            emotion_state = "狂热"
            confidence = 0.7 + 0.12 * (bullish_ratio - 0.75) / 0.25
        elif bearish_ratio > 0.75 and polarization > 0.4:
            # 恐慌状态 → 逆向看多
            direction = "bullish"
            emotion_state = "恐慌"
            confidence = 0.7 + 0.12 * (bearish_ratio - 0.75) / 0.25
        elif bullish_ratio > BULLISH_THRESHOLD:
            # 偏看多（直接信号，非极端）
            direction = "bullish"
            emotion_state = "偏乐观"
            confidence = 0.5 + 0.3 * (bullish_ratio - BULLISH_THRESHOLD) / (
                1.0 - BULLISH_THRESHOLD
            )
        elif bullish_ratio < BEARISH_THRESHOLD:
            # 偏看空（直接信号，非极端）
            direction = "bearish"
            emotion_state = "偏悲观"
            confidence = 0.5 + 0.3 * (BEARISH_THRESHOLD - bullish_ratio) / BEARISH_THRESHOLD
        else:
            direction = "neutral"
            emotion_state = "中性"
            confidence = 0.3 + 0.2 * (1.0 - abs(bullish_ratio - 0.5) / 0.1)

        confidence = min(round(confidence, 2), MAX_CONFIDENCE)

        # 构建信号列表（取 top 帖子标题）
        signals = []
        for p in bullish_posts[:3]:
            signals.append(f"[看多] {p.get('title', '')[:40]}")
        for p in bearish_posts[:3]:
            signals.append(f"[看空] {p.get('title', '')[:40]}")

        # 构建 reasoning
        content_count = sum(1 for p in posts if p.get("content"))
        reasoning = (
            f"共分析 {len(posts)} 条帖子"
            f"（其中 {content_count} 条含正文），"
            f"看多 {len(bullish_posts)} 条，"
            f"看空 {len(bearish_posts)} 条，"
            f"中性 {len(neutral_posts)} 条。"
            f"看多比例 {bullish_ratio:.1%}，"
            f"情绪极化度 {polarization:.1%}，"
            f"情绪状态: {emotion_state}，"
            f"方向: {direction}。"
        )

        # 判断风险等级（SKILL.md 第4.3节）
        if confidence >= 0.7 and direction != "neutral":
            risk_level = "high"
        elif confidence >= 0.5 and direction != "neutral":
            risk_level = "medium"
        else:
            risk_level = "low"

        needs_human_review = (
            confidence < 0.4
            or len(posts) < 5
            or abs(bullish_ratio - 0.5) < 0.05
        )

        # 构建 evidence（SKILL.md 第7步）
        evidence = []
        for p in sorted(
            bullish_posts + bearish_posts, key=lambda x: x.get("reads", 0), reverse=True
        )[:5]:
            sentiment = "bullish" if p in bullish_posts else "bearish"
            ev = {
                "title": p.get("title", ""),
                "reads": p.get("reads", 0),
                "replies": p.get("replies", 0),
                "author": p.get("author", ""),
                "post_time": p.get("post_time", ""),
                "sentiment": sentiment,
                "source": f"东财股吧·{p.get('source_type', '')}",
            }
            if p.get("content"):
                ev["content_summary"] = p["content"][:80] + "..."
            evidence.append(ev)

        # 计算数据时间范围
        time_range = self._calc_time_range(posts)

        return {
            "direction": direction,
            "confidence": confidence,
            "reasoning": reasoning,
            "signals": signals,
            "bullish_ratio": bullish_ratio,
            "bearish_ratio": bearish_ratio,
            "polarization": polarization,
            "emotion_state": emotion_state,
            "risk_level": risk_level,
            "needs_human_review": needs_human_review,
            "total_posts": len(posts),
            "bullish_count": len(bullish_posts),
            "bearish_count": len(bearish_posts),
            "neutral_count": len(neutral_posts),
            "evidence": evidence,
            "time_range": time_range,
        }

    def _build_signal(self, stock_code: str, analysis: Dict[str, Any]) -> Signal:
        """构建标准 Signal 对象（遵循 market_emotion_discovery Skill 输出规范）"""
        direction = analysis["direction"]
        confidence = analysis["confidence"]
        reasoning = analysis["reasoning"]
        signals = analysis["signals"]

        meta = {
            "output_version": "0.1",
            "skill_name": "market_emotion_discovery",
            "data_skill": "eastmoney_guba",
            "owner_group": "专家6组（舆情）",
            "target": stock_code,
            "period": "实时",
            "data_time_range": analysis.get("time_range", ""),
            "time_horizon": "short",
            "risk_level": analysis["risk_level"],
            "emotion_state": analysis.get("emotion_state", "中性"),
            "polarization": analysis.get("polarization", 0),
            "bullish_ratio": analysis.get("bullish_ratio", 0.5),
            "bearish_ratio": analysis.get("bearish_ratio", 0.5),
            "key_findings": [
                f"情绪状态: {analysis.get('emotion_state', '未知')}",
                f"看多帖子 {analysis['bullish_count']} 条，看空 {analysis['bearish_count']} 条，中性 {analysis['neutral_count']} 条",
                f"看多比例 {analysis['bullish_ratio']:.1%}，情绪极化度 {analysis.get('polarization', 0):.1%}",
            ],
            "evidence": analysis["evidence"],
            "risk_notes": [
                "基于标题+正文的关键词分析，置信度上限0.8",
                "热门帖子已抓取正文，最新帖子仅分析标题",
                "数据来自东方财富股吧，偏散户视角",
            ],
            "uncertainties": [
                "部分帖子仅基于标题分析，未抓取正文",
                "无法分析图片/视频内容",
                "关键词匹配可能遗漏隐含情绪",
                "情绪极端不等于立即反转，可能持续一段时间",
            ],
            "needs_human_review": analysis["needs_human_review"],
            "total_posts_analyzed": analysis["total_posts"],
            "bullish_count": analysis["bullish_count"],
            "bearish_count": analysis["bearish_count"],
            "neutral_count": analysis["neutral_count"],
        }

        if direction == "bullish":
            return bullish_signal(
                confidence=confidence,
                reasoning=reasoning,
                signals=signals,
                source=self.name,
                stock_code=stock_code,
                signal_type=self.signal_type,
                meta=meta,
            )
        elif direction == "bearish":
            return bearish_signal(
                confidence=confidence,
                reasoning=reasoning,
                signals=signals,
                source=self.name,
                stock_code=stock_code,
                signal_type=self.signal_type,
                meta=meta,
            )
        else:
            return neutral_signal(
                confidence=confidence,
                reasoning=reasoning,
                source=self.name,
                stock_code=stock_code,
                signal_type=self.signal_type,
                meta=meta,
            )

    def _calc_time_range(self, posts: List[Dict[str, Any]]) -> str:
        """根据帖子时间计算数据覆盖的时间范围"""
        now = datetime.now()
        year = now.year
        parsed_times = []
        for p in posts:
            t = p.get("post_time", "").strip()
            if not t:
                continue
            try:
                dt = datetime.strptime(t.strip(), "%m-%d %H:%M")
                dt = dt.replace(year=year)
                if dt > now:
                    dt = dt.replace(year=year - 1)
                parsed_times.append(dt)
            except ValueError:
                continue

        if not parsed_times:
            return "未知"

        earliest = min(parsed_times)
        latest = max(parsed_times)
        fmt = "%m-%d %H:%M"
        return f"{earliest.strftime(fmt)} ~ {latest.strftime(fmt)}"
