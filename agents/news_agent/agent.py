"""
舆情情感 Agent - 专家6组

signal_type: news
Skill 域: skills/news/ + skills/data/
核心能力：大盘情绪温度 + 行业景气热度 + 个股舆情分析，统一编排输出

架构分层：
  - 大盘情绪：skills/news/market_sentiment_tracker → 0-100 温度计 + 仓位建议
  - 行业景气：skills/news/industry_sentiment_tracker → 行业板块景气热度
  - 个股舆情：skills/news/market_emotion_discovery → 个股股吧情绪分析
  - 数据获取：data_sources/market_sentiment.py + data_sources/industry_sentiment.py + data_sources/eastmoney_guba.py
  - Agent 本身：编排大盘→行业→个股三层分析，统一输出
"""

from datetime import datetime
from typing import Dict, Any, List, Optional

from agents.base import BaseAgent
from agents.signal import Signal, bullish_signal, bearish_signal, neutral_signal
from data_sources import EastMoneyGubaDataSource, MarketSentimentDataSource, IndustrySentimentDataSource
from data_sources.keywords import BULLISH_KEYWORDS, BEARISH_KEYWORDS, calc_sentiment_ratio
import math


# ── 个股情绪分析关键词（共享模块 data_sources/keywords.py） ──────
# BULLISH_KEYWORDS / BEARISH_KEYWORDS 已从共享模块导入

# 置信度配置
MAX_CONFIDENCE = 0.8
BULLISH_THRESHOLD = 0.6
BEARISH_THRESHOLD = 0.4


class NewsAgent(BaseAgent):
    """
    舆情情感 Agent（专家6组）

    编排三层分析（先大盘再行业后个股）：
      1. 大盘情绪温度：skills/news/market_sentiment_tracker → 全市场冷热
      2. 行业景气热度：skills/news/industry_sentiment_tracker → 行业板块景气
      3. 个股舆情分析：skills/news/market_emotion_discovery → 个股情绪极端发现

    输出顺序：大盘背景 → 行业景气 → 个股详情，让用户先看大气候再看个股。
    """

    signal_type = "news"

    def __init__(self, config: Optional[dict] = None):
        super().__init__(name="舆情情感Agent", config=config or {})
        # 加载分析层 Skill（market_sentiment_tracker + industry_sentiment_tracker + market_emotion_discovery）
        self.load_skills_from_domain("news")
        # 加载数据接口说明 Skill（eastmoney_guba, cninfo）
        self.load_skills_from_domain("data")

        # 数据源
        self.guba_data_source = (
            self.config.get("guba_data_source") or EastMoneyGubaDataSource()
        )
        self.market_sentiment_source = (
            self.config.get("market_sentiment_source") or MarketSentimentDataSource()
        )
        self.industry_sentiment_source = (
            self.config.get("industry_sentiment_source") or IndustrySentimentDataSource()
        )

        # 默认关闭正文抓取：东财反爬严格
        self._fetch_content = self.config.get("fetch_content", False)

    def analyze(self, stock_code: str) -> Signal:
        """
        统一编排：先大盘情绪，再行业景气，后个股舆情

        Args:
            stock_code: 股票代码

        Returns:
            Signal: 包含大盘+行业+个股三层信息的综合信号
        """
        code = self._normalize_code(stock_code)
        self.log(f"开始分析 {code}（先大盘→行业→个股）")
        self.log(f"已加载 Skill: {self.list_skills()}")

        # ── 第1步：大盘情绪温度 ──
        market_result = self._analyze_market_sentiment()

        # ── 第2步：行业景气热度 ──
        industry_result = self._analyze_industry_sentiment(code)

        # ── 第3步：个股舆情分析 ──
        stock_result = self._analyze_stock_sentiment(code)

        # ── 第4步：综合编排输出 ──
        return self._build_combined_signal(code, market_result, industry_result, stock_result)

    # ══════════════════════════════════════════
    # 大盘情绪温度（market_sentiment_tracker）
    # ══════════════════════════════════════════

    def _analyze_market_sentiment(self) -> Dict[str, Any]:
        """大盘情绪温度分析（遵循 market_sentiment_tracker Skill 规则）"""
        self.log("采集大盘情绪数据...")
        try:
            data = self.market_sentiment_source.get_sentiment_data()
            if data.get("status") == "success":
                self.log(f"大盘情绪温度: {data['score']}/100，阶段: {data['stage']['name']}")
            else:
                self.log(f"大盘情绪数据获取失败: {data.get('stage', {}).get('suggestion', '')}", level="warning")
            return data
        except Exception as e:
            self.log(f"大盘情绪分析异常: {e}", level="error")
            return {
                "status": "error",
                "score": 50.0,
                "stage": {"name": "数据不足", "suggestion": str(e), "position": "30-50%", "direction": "neutral"},
                "direction": "neutral",
                "confidence": 0.3,
                "indicators": {},
                "raw_data": {},
                "special_signals": [],
                "uncertainties": [f"大盘数据获取异常: {e}"],
            }

    # ══════════════════════════════════════════
    # 行业景气热度（industry_sentiment_tracker）
    # ══════════════════════════════════════════

    def _analyze_industry_sentiment(self, stock_code: str) -> Dict[str, Any]:
        """行业景气热度分析（遵循 industry_sentiment_tracker Skill 规则）"""
        self.log(f"采集 {stock_code} 所属行业景气数据...")
        try:
            data = self.industry_sentiment_source.get_industry_sentiment(stock_code)
            if data.get("status") == "success":
                self.log(f"行业景气: {data.get('industry_name', '未知')} 温度 {data['score']}/100，阶段: {data['stage']['name']}")
            else:
                self.log(f"行业景气数据获取失败: {data.get('stage', {}).get('suggestion', '')}", level="warning")
            return data
        except Exception as e:
            self.log(f"行业景气分析异常: {e}", level="error")
            return {
                "status": "error",
                "industry_name": None,
                "score": 50.0,
                "stage": {"name": "数据不足", "suggestion": str(e), "position": "30-50%", "direction": "neutral"},
                "direction": "neutral",
                "confidence": 0.3,
                "position_suggestion": "30-50%",
                "special_signals": [],
                "indicators": {},
                "raw_data_summary": {},
                "uncertainties": [f"行业数据获取异常: {e}"],
            }

    # ══════════════════════════════════════════
    # 个股舆情分析（market_emotion_discovery）
    # ══════════════════════════════════════════

    def _analyze_stock_sentiment(self, code: str) -> Dict[str, Any]:
        """个股舆情分析（遵循 market_emotion_discovery Skill 规则）"""
        self.log(f"采集 {code} 的股吧数据...")
        try:
            guba_data = self._fetch_guba_data(code)
        except Exception as e:
            self.log(f"抓取股吧数据失败: {e}", level="error")
            return {
                "status": "error",
                "direction": "neutral",
                "confidence": 0.3,
                "reasoning": f"抓取股吧数据失败: {e}",
                "signals": [],
                "emotion_state": "数据不足",
                "risk_level": "low",
                "needs_human_review": True,
                "evidence": [],
                "uncertainties": [f"数据抓取失败: {e}"],
            }

        if guba_data.get("status") != "success" or not guba_data.get("posts"):
            self.log(f"未获取到 {code} 的股吧帖子", level="warning")
            return {
                "status": "error",
                "direction": "neutral",
                "confidence": 0.3,
                "reasoning": f"未获取到 {code} 的股吧帖子",
                "signals": [],
                "emotion_state": "数据不足",
                "risk_level": "low",
                "needs_human_review": True,
                "evidence": [],
                "uncertainties": ["未获取到帖子数据"],
            }

        posts = guba_data["posts"]
        self.log(f"获取到 {len(posts)} 条帖子，开始情绪分析")
        analysis = self._analyze_sentiment(posts)
        analysis["status"] = "success"
        analysis["time_range"] = self._calc_time_range(posts)
        return analysis

    def _fetch_guba_data(self, code: str) -> Dict[str, Any]:
        skill_content = self.get_skill("eastmoney_guba")
        if skill_content:
            self.log("已加载 eastmoney_guba 数据接口说明 Skill")

        result = self.guba_data_source.get_posts(
            stock_code=code,
            pages=self.config.get("pages", 2),
            fetch_content=self._fetch_content,
        )
        self.log(f"股吧数据源返回 {len(result.get('posts', []))} 条帖子")
        return result

    # ── 情绪分析逻辑（遵循 market_emotion_discovery Skill 规则） ──────

    def _normalize_code(self, code: str) -> str:
        code = code.strip().upper()
        for prefix in ("SH", "SZ", "BJ"):
            if code.startswith(prefix):
                code = code[len(prefix):]
                break
        return code

    def _analyze_sentiment(self, posts: List[Dict[str, Any]]) -> Dict[str, Any]:
        bullish_keywords = set(BULLISH_KEYWORDS)
        bearish_keywords = set(BEARISH_KEYWORDS)

        # 使用共享情绪计算函数
        ratios = calc_sentiment_ratio(posts, bullish_keywords, bearish_keywords)
        bullish_ratio = ratios["bullish_ratio"]
        bearish_ratio = ratios["bearish_ratio"]
        polarization = ratios["polarization"]
        bullish_posts = ratios["bullish_posts"]
        bearish_posts = ratios["bearish_posts"]

        if bullish_ratio > 0.75 and polarization > 0.4:
            direction = "bearish"
            emotion_state = "狂热"
            confidence = 0.7 + 0.12 * (bullish_ratio - 0.75) / 0.25
        elif bearish_ratio > 0.75 and polarization > 0.4:
            direction = "bullish"
            emotion_state = "恐慌"
            confidence = 0.7 + 0.12 * (bearish_ratio - 0.75) / 0.25
        elif bullish_ratio > BULLISH_THRESHOLD:
            direction = "bullish"
            emotion_state = "偏乐观"
            confidence = 0.5 + 0.3 * (bullish_ratio - BULLISH_THRESHOLD) / (1.0 - BULLISH_THRESHOLD)
        elif bullish_ratio < BEARISH_THRESHOLD:
            direction = "bearish"
            emotion_state = "偏悲观"
            confidence = 0.5 + 0.3 * (BEARISH_THRESHOLD - bullish_ratio) / BEARISH_THRESHOLD
        else:
            direction = "neutral"
            emotion_state = "中性"
            confidence = 0.3 + 0.2 * (1.0 - abs(bullish_ratio - 0.5) / 0.1)

        confidence = min(round(confidence, 2), MAX_CONFIDENCE)

        # 信号列表（精简为 top 2 + top 2）
        signals = []
        for p in bullish_posts[:2]:
            signals.append(f"[看多] {p.get('title', '')[:40]}")
        for p in bearish_posts[:2]:
            signals.append(f"[看空] {p.get('title', '')[:40]}")

        reasoning = (
            f"分析 {len(posts)} 条帖子，"
            f"看多 {len(bullish_posts)} 条，看空 {len(bearish_posts)} 条。"
            f"看多比例 {bullish_ratio:.1%}，极化度 {polarization:.1%}，"
            f"情绪: {emotion_state}，方向: {direction}。"
        )

        if confidence >= 0.7 and direction != "neutral":
            risk_level = "high"
        elif confidence >= 0.5 and direction != "neutral":
            risk_level = "medium"
        else:
            risk_level = "low"

        needs_human_review = confidence < 0.4 or len(posts) < 5

        # 精选 evidence：看多、看空各取 top 3（按阅读量排序）
        evidence = []
        for p in sorted(bullish_posts, key=lambda x: x.get("reads", 0), reverse=True)[:3]:
            evidence.append({
                "title": p.get("title", ""),
                "reads": p.get("reads", 0),
                "sentiment": "bullish",
                "source": f"东财股吧·{p.get('source_type', '')}",
            })
        for p in sorted(bearish_posts, key=lambda x: x.get("reads", 0), reverse=True)[:3]:
            evidence.append({
                "title": p.get("title", ""),
                "reads": p.get("reads", 0),
                "sentiment": "bearish",
                "source": f"东财股吧·{p.get('source_type', '')}",
            })

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
            "neutral_count": ratios["neutral_count"],
            "evidence": evidence,
        }

    # ══════════════════════════════════════════
    # 综合信号构建
    # ══════════════════════════════════════════

    def _build_combined_signal(
        self,
        stock_code: str,
        market_result: Dict[str, Any],
        industry_result: Dict[str, Any],
        stock_result: Dict[str, Any],
    ) -> Signal:
        """
        构建综合信号：大盘温度 + 行业景气 + 个股舆情

        输出顺序：先大盘再行业后个股，让用户先看大气候
        """
        # ── 大盘部分 ──
        market_score = market_result.get("score", 50.0)
        market_stage = market_result.get("stage", {})
        market_direction = market_result.get("direction", "neutral")
        market_confidence = market_result.get("confidence", 0.3)
        market_signals = market_result.get("special_signals", [])
        market_indicators = market_result.get("indicators", {})
        market_uncertainties = market_result.get("uncertainties", [])
        market_raw = market_result.get("raw_data", {})

        # ── 行业部分 ──
        industry_name = industry_result.get("industry_name")
        industry_score = industry_result.get("score", 50.0)
        industry_stage = industry_result.get("stage", {})
        industry_direction = industry_result.get("direction", "neutral")
        industry_confidence = industry_result.get("confidence", 0.3)
        industry_signals = industry_result.get("special_signals", [])
        industry_indicators = industry_result.get("indicators", {})
        industry_raw = industry_result.get("raw_data_summary", {})
        industry_uncertainties = industry_result.get("uncertainties", [])
        industry_position = industry_result.get("position_suggestion", "30-50%")
        has_industry = industry_result.get("status") == "success" and industry_name is not None

        # ── 个股部分 ──
        stock_direction = stock_result.get("direction", "neutral")
        stock_confidence = stock_result.get("confidence", 0.3)
        stock_reasoning = stock_result.get("reasoning", "")
        stock_signals = stock_result.get("signals", [])
        stock_emotion = stock_result.get("emotion_state", "未知")
        stock_risk = stock_result.get("risk_level", "low")
        stock_evidence = stock_result.get("evidence", [])
        stock_uncertainties = stock_result.get("uncertainties", [])
        stock_ratio = stock_result.get("bullish_ratio", 0.5)
        stock_polarization = stock_result.get("polarization", 0)
        stock_total = stock_result.get("total_posts", 0)

        # ── 综合方向：以个股为主，行业做修正，大盘做背景 ──
        combined_direction = stock_direction
        combined_confidence = stock_confidence

        # 行业和个股方向一致时提升置信度，矛盾时降低
        if has_industry and industry_direction != "neutral" and stock_direction != "neutral":
            if industry_direction == stock_direction:
                combined_confidence = min(0.9, combined_confidence + 0.05)
            else:
                combined_confidence = max(0.2, combined_confidence - 0.08)

        # 大盘和个股方向一致时提升，矛盾时降低（影响小于行业）
        if market_direction != "neutral" and stock_direction != "neutral":
            if market_direction == stock_direction:
                combined_confidence = min(0.9, combined_confidence + 0.03)
            else:
                combined_confidence = max(0.2, combined_confidence - 0.05)

        # 构建综合 reasoning
        reasoning_parts = [
            f"【大盘】情绪温度 {market_score}/100，{market_stage.get('name', '未知')}，"
            f"建议仓位 {market_stage.get('position', '30-50%')}。",
        ]
        if has_industry:
            reasoning_parts.append(
                f"【行业·{industry_name}】景气温度 {industry_score}/100，"
                f"{industry_stage.get('name', '未知')}，建议仓位 {industry_position}。"
            )
        reasoning_parts.append(f"【个股 {stock_code}】{stock_reasoning}")
        reasoning = "".join(reasoning_parts)

        # 合并 signals：大盘→行业→个股
        all_signals = []
        if market_signals:
            all_signals.append(f"[大盘] {market_stage.get('name', '')}，温度{market_score}")
            for sig in market_signals[:2]:
                all_signals.append(f"[大盘] {sig}")
        if has_industry and industry_signals:
            all_signals.append(f"[行业·{industry_name}] {industry_stage.get('name', '')}，温度{industry_score}")
            for sig in industry_signals[:2]:
                all_signals.append(f"[行业] {sig}")
        all_signals.extend(stock_signals[:4])

        # 综合风险等级
        risk_level = max(
            stock_risk,
            "high" if market_score > 80 or market_score < 20 else
            "medium" if market_score > 65 or market_score < 35 else "low",
            "high" if has_industry and (industry_score > 80 or industry_score < 20) else
            "medium" if has_industry and (industry_score > 65 or industry_score < 35) else "low",
            key=lambda x: {"low": 0, "medium": 1, "high": 2}.get(x, 0)
        )

        meta = {
            "output_version": "0.3",
            "owner_group": "专家6组（舆情）",
            "target": stock_code,
            "period": "实时",
            "time_horizon": "short",
            "risk_level": risk_level,
            "needs_human_review": stock_result.get("needs_human_review", False) or market_confidence < 0.3,
            # ── 大盘情绪 ──
            "market": {
                "skill_name": "market_sentiment_tracker",
                "score": market_score,
                "phase": market_stage.get("id", ""),  # v0.4: 6阶段id
                "phase_name": market_stage.get("name", "未知"),  # v0.4: 阶段中文名
                "phase_icon": market_stage.get("icon", ""),  # v0.4: 阶段图标
                "stage": market_stage.get("name", "未知"),
                "direction": market_direction,
                "confidence": market_confidence,
                "position_suggestion": market_stage.get("position", "30-50%"),
                "special_signals": market_signals,
                "indicators": market_indicators,
                "raw_data_summary": {
                    k: (None if (isinstance(v, float) and (math.isnan(v) or math.isinf(v))) else v)
                    for k, v in market_raw.items()
                    if v is not None and k in ("limit_up", "limit_down", "breadth", "north_flow", "margin", "margin_change", "rsi")
                },
                "uncertainties": market_uncertainties,
                "community": market_result.get("community", {}).get("aggregate") if market_result.get("community") else None,
            },
            # ── 行业景气 ──
            "industry": {
                "skill_name": "industry_sentiment_tracker",
                "industry_name": industry_name,
                "score": industry_score,
                "stage": industry_stage.get("name", "未知") if isinstance(industry_stage, dict) else "未知",
                "direction": industry_direction,
                "confidence": industry_confidence,
                "position_suggestion": industry_position,
                "special_signals": industry_signals,
                "indicators": industry_indicators,
                "raw_data_summary": {
                    k: (None if (isinstance(v, float) and (math.isnan(v) or math.isinf(v))) else v)
                    for k, v in industry_raw.items()
                    if v is not None
                },
                "uncertainties": industry_uncertainties,
            } if has_industry else None,
            # ── 个股舆情 ──
            "stock": {
                "skill_name": "market_emotion_discovery",
                "data_skill": "eastmoney_guba",
                "direction": stock_direction,
                "confidence": stock_confidence,
                "emotion_state": stock_emotion,
                "bullish_ratio": round(stock_ratio, 3),
                "polarization": round(stock_polarization, 3),
                "total_posts": stock_total,
                "bullish_count": stock_result.get("bullish_count", 0),
                "bearish_count": stock_result.get("bearish_count", 0),
                "evidence": stock_evidence,
                "data_time_range": stock_result.get("time_range", ""),
                "uncertainties": stock_uncertainties,
            },
        }

        # 构建 Signal
        if combined_direction == "bullish":
            return bullish_signal(
                confidence=combined_confidence,
                reasoning=reasoning,
                signals=all_signals,
                source=self.name,
                stock_code=stock_code,
                signal_type=self.signal_type,
                meta=meta,
            )
        elif combined_direction == "bearish":
            return bearish_signal(
                confidence=combined_confidence,
                reasoning=reasoning,
                signals=all_signals,
                source=self.name,
                stock_code=stock_code,
                signal_type=self.signal_type,
                meta=meta,
            )
        else:
            return neutral_signal(
                confidence=combined_confidence,
                reasoning=reasoning,
                source=self.name,
                stock_code=stock_code,
                signal_type=self.signal_type,
                meta=meta,
            )

    def _calc_time_range(self, posts: List[Dict[str, Any]]) -> str:
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
