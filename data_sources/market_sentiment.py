"""
A股大盘市场情绪数据源

通过 AKShare + 东财大盘股吧社区数据采集全市场情绪指标，供舆情 Agent 调用。
对应的分析层 Skill 见 skills/news/market_sentiment_tracker/SKILL.md

设计原则：每个指标独立 try/except，单个指标失败不影响整体评分。
整体采集控制在 60 秒内完成，超时返回部分数据。

v0.4: 6阶段市场情绪（无人问津/暗度陈仓/人声渐起/人声鼎沸/恐慌抛售/绝望冰点）
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

from .community_sentiment import CommunitySentimentDataSource

from loguru import logger

try:
    import akshare as ak
    import pandas as pd
    import numpy as np
    AKSHARE_AVAILABLE = True
except ImportError:
    AKSHARE_AVAILABLE = False


# 情绪评分权重配置（与 SKILL.md 对齐，v0.4 新增2个社区指标）
WEIGHTS = {
    # 量化指标（合计 0.50）
    "turnover_rate":       0.07,
    "limit_up_ratio":      0.07,
    "margin_change":       0.07,
    "north_flow":          0.06,
    "breadth":             0.06,
    "volume_ratio":        0.06,
    "rsi":                 0.06,
    "pe_percentile":       0.05,
    # 社区指标（合计 0.50）— 舆情系统以社区情绪为核心
    "discussion_volume":   0.25,
    "community_sentiment": 0.25,
}

# ── 6阶段市场情绪定义（v0.4）──────────────────────
MARKET_PHASES = [
    {
        "id": "despair_freezing",
        "name": "绝望冰点",
        "score_range": (0, 10),
        "description": "彻底绝望，无人愿意买入，讨论冻结",
        "position": "80-95%",
        "direction": "bullish",
        "icon": "🧊",
        "color": "#63b3ed",
    },
    {
        "id": "nobody_cares",
        "name": "无人问津",
        "score_range": (10, 25),
        "description": "极端冷清，无人讨论，市场被遗忘",
        "position": "70-90%",
        "direction": "bullish",
        "icon": "🕳️",
        "color": "#4a5568",
    },
    {
        "id": "panic_selling",
        "name": "恐慌抛售",
        "score_range": (10, 35),
        "description": "恐慌主导，大量抛售，讨论激烈",
        "position": "30-50%",
        "direction": "bullish",
        "icon": "⚡",
        "color": "#f6ad55",
    },
    {
        "id": "secret_accumulation",
        "name": "暗度陈仓",
        "score_range": (25, 45),
        "description": "聪明钱悄悄进场，散户沉默，暗流涌动",
        "position": "50-70%",
        "direction": "bullish",
        "icon": "🦉",
        "color": "#2d3748",
    },
    {
        "id": "voices_rising",
        "name": "人声渐起",
        "score_range": (45, 75),
        "description": "讨论逐渐增多，市场关注度上升",
        "position": "40-60%",
        "direction": "neutral",
        "icon": "📈",
        "color": "#ecc94b",
    },
    {
        "id": "climax",
        "name": "人声鼎沸",
        "score_range": (75, 100),
        "description": "全民热议，疯狂追涨，极度亢奋",
        "position": "20-40%",
        "direction": "bearish",
        "icon": "🔥",
        "color": "#e53e3e",
    },
]


class MarketSentimentDataSource:
    """A股大盘市场情绪数据源"""

    def __init__(self):
        self.name = "大盘市场情绪数据源"
        logger.info(f"[数据源] {self.name} 初始化完成 (akshare={'可用' if AKSHARE_AVAILABLE else '不可用'})")

    def get_sentiment_data(self) -> Dict[str, Any]:
        """
        采集全市场情绪指标并计算综合温度

        Returns:
            {
                "status": "success" | "error",
                "score": float,
                "stage": {id, name, icon, color, description, position, direction},
                "direction": str,
                "confidence": float,
                "indicators": {...},
                "raw_data": {...},
                "special_signals": [...],
                "community": {...},  # v0.4: 社区数据
            }
        """
        if not AKSHARE_AVAILABLE:
            return self._fallback_result("akshare 未安装，无法采集大盘数据")

        indicators: Dict[str, Any] = {}
        raw_data: Dict[str, Any] = {}
        community_data: Optional[Dict[str, Any]] = None

        # 1. 涨跌停数据
        try:
            zt, dt = self._get_limit_up_down()
            raw_data["limit_up"] = zt
            raw_data["limit_down"] = dt
            if zt is not None:
                indicators["limit_up_ratio"] = self._normalize_limit_ratio(zt, dt)
                logger.info(f"[{self.name}] 涨停:{zt} 跌停:{dt} → 情绪分:{indicators['limit_up_ratio']:.1f}")
        except Exception as e:
            logger.warning(f"[{self.name}] 涨跌停数据获取失败: {e}")

        # 2. 市场宽度
        try:
            breadth = self._get_market_breadth()
            raw_data["breadth"] = breadth
            if breadth is not None:
                indicators["breadth"] = self._normalize_breadth(breadth)
                logger.info(f"[{self.name}] 上涨占比:{breadth:.1%} → 情绪分:{indicators['breadth']:.1f}")
        except Exception as e:
            logger.warning(f"[{self.name}] 市场宽度数据获取失败: {e}")

        # 3. 北向资金
        try:
            north = self._get_north_flow()
            raw_data["north_flow"] = north
            if north is not None:
                indicators["north_flow"] = self._normalize_north_flow(north)
                sign = "+" if north > 0 else ""
                logger.info(f"[{self.name}] 北向资金:{sign}{north:.1f}亿 → 情绪分:{indicators['north_flow']:.1f}")
        except Exception as e:
            logger.warning(f"[{self.name}] 北向资金数据获取失败: {e}")

        # 4. 融资余额
        try:
            margin, margin_change = self._get_margin_balance()
            raw_data["margin"] = margin
            raw_data["margin_change"] = margin_change
            if margin_change is not None:
                indicators["margin_change"] = self._normalize_margin_change(margin_change)
                logger.info(f"[{self.name}] 融资余额:{margin:.0f}亿 变化:{margin_change:+.1f}% → 情绪分:{indicators['margin_change']:.1f}")
        except Exception as e:
            logger.warning(f"[{self.name}] 融资余额数据获取失败: {e}")

        # 5. 技术指标 (RSI)
        try:
            rsi, price_pos = self._get_technical()
            raw_data["rsi"] = rsi
            raw_data["price_position"] = price_pos
            if rsi is not None:
                indicators["rsi"] = self._normalize_rsi(rsi)
                logger.info(f"[{self.name}] RSI(14):{rsi:.1f} → 情绪分:{indicators['rsi']:.1f}")
        except Exception as e:
            logger.warning(f"[{self.name}] 技术指标计算失败: {e}")

        # 6. 社区讨论数据（v0.4 新增）
        community_source = CommunitySentimentDataSource()
        with ThreadPoolExecutor(max_workers=1) as executor:
            community_future = executor.submit(community_source.get_community_sentiment)
            try:
                community_data = community_future.result(timeout=90)
                if community_data and community_data.get("status") in ("success", "partial"):
                    aggregate = community_data["aggregate"]
                    indicators["discussion_volume"] = aggregate["discussion_volume_score"]
                    indicators["community_sentiment"] = self._normalize_community_sentiment(
                        aggregate["bullish_ratio"]
                    )
                    raw_data["community"] = community_data
                    logger.info(
                        f"[{self.name}] 社区: {aggregate['total_posts']}帖, "
                        f"热度{aggregate['discussion_volume_score']:.0f}, "
                        f"多{aggregate['bullish_ratio']:.1%}/空{aggregate['bearish_ratio']:.1%}"
                    )
            except Exception as e:
                logger.warning(f"[{self.name}] 社区数据获取超时或异常: {e}")
                community_data = None

        # 计算综合得分
        score = self._calculate_score(indicators)

        # 判定阶段（使用6阶段规则引擎）
        stage = self._determine_phase(score, community_data, raw_data)
        direction = stage["direction"]
        special_signals = self._detect_special_signals(raw_data, score, community_data)

        # 确定置信度
        confidence = self._calc_confidence(score, special_signals, indicators, community_data)

        return {
            "status": "success",
            "fetch_time": datetime.now().isoformat(),
            "score": score,
            "stage": stage,
            "direction": direction,
            "confidence": confidence,
            "indicators": indicators,
            "raw_data": raw_data,
            "special_signals": special_signals,
            "uncertainties": self._get_uncertainties(indicators),
            "community": community_data,
        }

    # ── 数据采集 ──────────────────────────────

    def _get_today_str(self, offset=0) -> str:
        d = datetime.now() - timedelta(days=offset)
        return d.strftime("%Y%m%d")

    def _get_limit_up_down(self) -> Tuple[Optional[int], Optional[int]]:
        """获取涨跌停板数据"""
        date = self._get_today_str()
        try:
            zt = ak.stock_zt_pool_em(date=date)
            zt_count = len(zt)
        except Exception:
            zt_count = None

        dt_count = None
        for func_name in ("stock_dt_pool_em", "stock_zt_pool_dtgc_em"):
            try:
                func = getattr(ak, func_name)
                dt = func(date=date)
                dt_count = len(dt)
                break
            except (AttributeError, Exception):
                continue

        if zt_count is None and dt_count is None:
            for offset in range(1, 5):
                try:
                    date = self._get_today_str(offset)
                    zt = ak.stock_zt_pool_em(date=date)
                    zt_count = len(zt)
                    for func_name in ("stock_dt_pool_em", "stock_zt_pool_dtgc_em"):
                        try:
                            func = getattr(ak, func_name)
                            dt = func(date=date)
                            dt_count = len(dt)
                            break
                        except (AttributeError, Exception):
                            continue
                    break
                except Exception:
                    continue

        return zt_count, dt_count

    def _get_market_breadth(self) -> Optional[float]:
        """获取市场涨跌比"""
        try:
            df = ak.stock_zh_index_daily(symbol="sh000001")
            if df is not None and not df.empty:
                df = df.sort_values("date", ascending=False)
                latest_close = float(df.iloc[0]["close"])
                prev_close = float(df.iloc[1]["close"]) if len(df) > 1 else latest_close
                chg_pct = (latest_close - prev_close) / prev_close * 100
                breadth = max(0.1, min(0.9, 0.5 + chg_pct / 10))
                return breadth
        except Exception as e:
            logger.warning(f"[{self.name}] 市场宽度推算失败: {e}")
        return None

    def _get_north_flow(self) -> Optional[float]:
        """获取北向资金净流入（亿元）"""
        try:
            df = ak.stock_hsgt_hist_em(symbol="沪股通")
            if df is not None and not df.empty:
                df = df.sort_values("日期", ascending=False)
                latest = df.iloc[0]
                for col in ["当日资金流入", "当日成交净买额", "净买入"]:
                    if col in df.columns:
                        val = float(latest[col])
                        if np.isnan(val) or np.isinf(val):
                            continue
                        return val / 1e8
        except Exception:
            pass
        try:
            df = ak.stock_hsgt_fund_flow_summary_em()
            if df is not None and not df.empty:
                val = float(df.iloc[0].get("当日资金流入", 0))
                if not (np.isnan(val) or np.isinf(val)):
                    return val / 1e8
        except Exception as e:
            logger.warning(f"[{self.name}] 北向资金获取失败: {e}")
        return None

    def _get_margin_balance(self) -> Tuple[Optional[float], Optional[float]]:
        """获取融资余额及变化率"""
        try:
            df = ak.stock_margin_sse(
                start_date=(datetime.now() - timedelta(days=30)).strftime("%Y%m%d"),
                end_date=self._get_today_str(),
            )
            if df is not None and not df.empty:
                # 尝试多种列名
                date_col_arr = ["信用交易日期", "交易日期", "日期", "trade_date", "date"]
                margin_col_arr = ["融资余额", "融资余额(元)", "rzye"]
                date_col = next((col for col in date_col_arr if col in df.columns), "date")
                margin_col = next((col for col in margin_col_arr if col in df.columns), "rzye")
                df = df.sort_values(date_col, ascending=False)
                latest = float(df.iloc[0][margin_col]) / 1e8
                old_val = float(df.iloc[-1][margin_col]) / 1e8 if len(df) > 5 else latest
                if np.isnan(latest) or np.isinf(latest) or np.isnan(old_val) or np.isinf(old_val):
                    return None, None
                change = (latest - old_val) / old_val * 100 if old_val > 0 else 0
                return latest, change
        except Exception as e:
            logger.warning(f"[{self.name}] 融资余额获取失败: {e}")
        return None, None

    def _get_technical(self) -> Tuple[Optional[float], Optional[float]]:
        """获取指数技术指标"""
        try:
            df = ak.stock_zh_index_daily(symbol="sh000001")
            df = df.sort_values("date", ascending=False).head(30)
            closes = df["close"].values[::-1]

            if len(closes) >= 15:
                deltas = np.diff(closes)
                pos_deltas = deltas[-14:][deltas[-14:] > 0]
                neg_deltas = deltas[-14:][deltas[-14:] < 0]
                gain = float(np.mean(pos_deltas)) if len(pos_deltas) > 0 else 0.0
                loss = float(abs(np.mean(neg_deltas))) if len(neg_deltas) > 0 else 0.0
                rs = gain / loss if loss > 0 else 100.0
                rsi = 100 - (100 / (1 + rs))
                if np.isnan(rsi) or np.isinf(rsi):
                    rsi = 50.0
            else:
                rsi = 50

            recent_high = max(closes[-20:]) if len(closes) >= 20 else max(closes)
            recent_low = min(closes[-20:]) if len(closes) >= 20 else min(closes)
            price_pos = (closes[-1] - recent_low) / (recent_high - recent_low) if recent_high != recent_low else 0.5
            return rsi, price_pos
        except Exception as e:
            logger.warning(f"[{self.name}] 技术指标计算失败: {e}")
        return None, None

    # ── 标准化函数 ──────────────────────────────

    def _normalize_limit_ratio(self, up, down):
        if up is None or down is None:
            return None
        total = up + down
        return (up / total * 100) if total > 0 else 50

    def _normalize_breadth(self, up_ratio):
        return up_ratio * 100 if up_ratio is not None else None

    def _normalize_north_flow(self, flow):
        if flow is None:
            return None
        return max(0, min(100, 50 + flow / 3))

    def _normalize_margin_change(self, change):
        if change is None:
            return None
        return max(0, min(100, 50 + change * 2.5))

    def _normalize_rsi(self, rsi):
        return max(0, min(100, rsi)) if rsi is not None else None

    def _normalize_community_sentiment(self, bullish_ratio: float) -> Optional[float]:
        """将社区看多比例映射到0-100分"""
        if bullish_ratio is None:
            return None
        return bullish_ratio * 100

    # ── 综合评分 ──────────────────────────────

    def _calculate_score(self, indicators: dict) -> float:
        total_weight = 0
        total_score = 0
        for key, weight in WEIGHTS.items():
            val = indicators.get(key)
            if val is not None:
                total_score += val * weight
                total_weight += weight
        if total_weight == 0:
            return 50.0
        return round(total_score / total_weight, 1)

    # ── 6阶段判定引擎（v0.4）──────────────────────

    def _determine_phase(
        self,
        score: float,
        community_data: Optional[Dict] = None,
        raw_data: Optional[Dict] = None,
    ) -> Dict:
        """
        判定市场阶段：社区情绪为主，量化分数为辅

        核心原则：舆情系统以社区情绪为核心判定依据
        - 极端阶段（绝望冰点/人声鼎沸）必须社区+技术双重确认
        - 社区方向（看多/看空）决定阶段方向
        - 量化分数作为辅助校验，防止社区数据失真

        优先级规则（从最具体到最通用）：
        1. 绝望冰点: score≤15 AND RSI<30 AND 讨论极冷 AND 看空>60% AND 量降
        2. 恐慌抛售: score≤35 AND 讨论激烈 AND 看空>70%
        3. 人声鼎沸: score≥75 AND RSI>70 AND 讨论极热 AND 看多>80%
        4. 暗度陈仓: score∈[20,45] AND 讨论冷 AND 聪明钱进场
        5. 无人问津: score≤25 AND 讨论极冷
        6. 人声渐起: 兜底（中间状态）

        无社区数据时保守判断，不轻易判极端阶段。
        """
        # 提取社区指标（可能为空）
        disc_vol = None
        bull_ratio = None
        bear_ratio = None
        vol_trend = "stable"

        if community_data and community_data.get("aggregate"):
            agg = community_data["aggregate"]
            disc_vol = agg.get("discussion_volume_score")
            bull_ratio = agg.get("bullish_ratio")
            bear_ratio = agg.get("bearish_ratio")
            vol_trend = agg.get("volume_trend", "stable")

        # 聪明钱指标：北向净流入或融资余额增加
        smart_money_active = False
        if raw_data:
            north = raw_data.get("north_flow")
            margin_chg = raw_data.get("margin_change")
            if (north is not None and north > 0) or (margin_chg is not None and margin_chg > 0):
                smart_money_active = True

        # RSI 硬约束（极端阶段必须有技术面佐证）
        rsi_value = raw_data.get("rsi") if raw_data else None
        rsi_oversold = rsi_value is not None and rsi_value < 30
        rsi_overbought = rsi_value is not None and rsi_value > 70

        # ── 有社区数据时：规则引擎 ──
        if disc_vol is not None and bull_ratio is not None:
            # 1. 绝望冰点（必须 RSI 超卖 + 社区冻结 + 看空主导）
            if score <= 15 and rsi_oversold and disc_vol <= 25 and bear_ratio > 0.60 and vol_trend == "declining":
                return self._build_phase_result("despair_freezing")

            # 2. 恐慌抛售（看空主导 + 讨论激烈）
            if score <= 35 and disc_vol >= 50 and bear_ratio > 0.70:
                return self._build_phase_result("panic_selling")

            # 3. 人声鼎沸（必须 RSI 超买 + 社区极度看多 + 讨论极热）
            if score >= 75 and rsi_overbought and disc_vol >= 75 and bull_ratio > 0.80:
                return self._build_phase_result("climax")

            # 4. 暗度陈仓（聪明钱进场 + 散户沉默）
            if 20 <= score <= 45 and disc_vol <= 35 and smart_money_active:
                return self._build_phase_result("secret_accumulation")

            # 5. 无人问津（讨论极冷，但不要求RSI条件）
            if score <= 25 and disc_vol <= 20:
                return self._build_phase_result("nobody_cares")

            # 6. 人声渐起（兜底：讨论有但不极端）
            if 25 <= score <= 75 and disc_vol >= 20:
                return self._build_phase_result("voices_rising")

            # 部分条件匹配时做最佳匹配
            return self._best_match_phase(score, disc_vol, bull_ratio, bear_ratio, smart_money_active, rsi_oversold, rsi_overbought)

        # ── 无社区数据：保守降级映射 ──
        return self._fallback_phase_by_score(score, smart_money_active, rsi_oversold, rsi_overbought)

    def _best_match_phase(
        self, score: float, disc_vol: float, bull_ratio: float, bear_ratio: float,
        smart_money: bool, rsi_oversold: bool, rsi_overbought: bool
    ) -> Dict:
        """
        部分条件匹配时的最佳匹配逻辑
        社区方向决定阶段方向，分数作为辅助
        """
        # 高分 + RSI超买 + 高讨论 → 人声鼎沸（放宽看多比到75%）
        if score >= 75 and rsi_overbought and disc_vol >= 65 and bull_ratio > 0.75:
            return self._build_phase_result("climax")

        # 低分 + RSI超卖 + 极低讨论 → 绝望冰点（放宽看空和量降条件）
        if score <= 15 and rsi_oversold and disc_vol <= 30:
            return self._build_phase_result("despair_freezing")

        # 低分 + 高讨论 + 看空占优 → 恐慌抛售
        if score <= 35 and disc_vol >= 50 and bear_ratio > bull_ratio:
            return self._build_phase_result("panic_selling")

        # 低中分 + 低讨论 + 聪明钱 → 暗度陈仓
        if 20 <= score <= 45 and disc_vol <= 35 and smart_money:
            return self._build_phase_result("secret_accumulation")

        # 低分 + 极低讨论 → 无人问津
        if score <= 25 and disc_vol <= 25:
            return self._build_phase_result("nobody_cares")

        # 中间分数 + 有讨论 → 人声渐起
        if 20 <= score <= 75 and disc_vol >= 20:
            return self._build_phase_result("voices_rising")

        # 最终兜底
        return self._fallback_phase_by_score(score, smart_money, rsi_oversold, rsi_overbought)

    def _fallback_phase_by_score(self, score: float, smart_money: bool = False,
                                  rsi_oversold: bool = False, rsi_overbought: bool = False) -> Dict:
        """
        纯分数降级映射（无社区数据时使用）
        保守原则：没有社区数据时不轻易判极端阶段
        """
        if score <= 10:
            # 必须RSI超卖才判绝望冰点，否则判无人问津
            if rsi_oversold:
                return self._build_phase_result("despair_freezing")
            return self._build_phase_result("nobody_cares")
        elif score <= 25:
            if smart_money:
                return self._build_phase_result("secret_accumulation")
            return self._build_phase_result("nobody_cares")
        elif score <= 35:
            if smart_money:
                return self._build_phase_result("secret_accumulation")
            return self._build_phase_result("panic_selling")
        elif score <= 45:
            if smart_money:
                return self._build_phase_result("secret_accumulation")
            return self._build_phase_result("voices_rising")
        elif score <= 75:
            return self._build_phase_result("voices_rising")
        else:
            # 必须RSI超买才判人声鼎沸，否则保守判人声渐起
            if rsi_overbought:
                return self._build_phase_result("climax")
            return self._build_phase_result("voices_rising")

    def _build_phase_result(self, phase_id: str) -> Dict:
        """根据 phase_id 构建阶段结果"""
        for phase in MARKET_PHASES:
            if phase["id"] == phase_id:
                return {
                    "id": phase["id"],
                    "name": phase["name"],
                    "icon": phase["icon"],
                    "color": phase["color"],
                    "description": phase["description"],
                    "position": phase["position"],
                    "direction": phase["direction"],
                    "suggestion": phase["description"] + "，建议仓位 " + phase["position"],
                }
        # 默认返回人声渐起
        default = MARKET_PHASES[2]
        return {
            "id": default["id"],
            "name": default["name"],
            "icon": default["icon"],
            "color": default["color"],
            "description": default["description"],
            "position": default["position"],
            "direction": default["direction"],
            "suggestion": default["description"],
        }

    # ── 特殊信号 ──────────────────────────────

    def _detect_special_signals(self, raw: dict, score: float, community_data: Optional[Dict] = None) -> list:
        signals = []
        if score >= 85:
            signals.append("顶部预警")
        if score <= 15:
            signals.append("底部信号")

        zt = raw.get("limit_up") or 0
        dt = raw.get("limit_down") or 0
        if zt >= 200:
            signals.append("情绪过热")
        if dt >= 100:
            signals.append("恐慌踩踏")

        north = raw.get("north_flow")
        if north is not None:
            if north > 150:
                signals.append("外资强烈做多")
            elif north < -150:
                signals.append("外资大幅撤离")

        change = raw.get("margin_change")
        if change is not None:
            if change > 15:
                signals.append("杠杆过高")
            elif change < -15:
                signals.append("去杠杆加速")

        # 社区相关特殊信号
        if community_data and community_data.get("aggregate"):
            agg = community_data["aggregate"]
            if agg.get("discussion_volume_score", 0) >= 90:
                signals.append("讨论极度狂热")
            if agg.get("discussion_volume_score", 0) <= 10:
                signals.append("讨论极度冷清")
            if agg.get("bullish_ratio", 0) > 0.85:
                signals.append("社区一致看多")
            if agg.get("bearish_ratio", 0) > 0.85:
                signals.append("社区一致看空")

        return signals

    # ── 置信度 ──────────────────────────────

    def _calc_confidence(self, score, special_signals, indicators, community_data=None) -> float:
        available = sum(1 for v in indicators.values() if v is not None)
        total = len(WEIGHTS)
        coverage = available / total if total > 0 else 0

        if score <= 20 or score >= 80:
            base = 0.7
        elif score <= 35 or score >= 65:
            base = 0.55
        else:
            base = 0.4

        # 特殊信号加成
        signal_boost = min(len(special_signals) * 0.05, 0.15)

        # 社区数据加成
        community_boost = 0
        if community_data and community_data.get("status") in ("success", "partial"):
            community_boost = 0.05

        # 数据覆盖度惩罚
        coverage_penalty = 0 if coverage >= 0.5 else (0.5 - coverage) * 0.3

        return round(min(0.9, max(0.2, base + signal_boost + community_boost - coverage_penalty)), 2)

    # ── 不确定性 ──────────────────────────────

    def _get_uncertainties(self, indicators: dict) -> list:
        missing = [k for k, v in indicators.items() if v is None]
        notes = []
        if "limit_up_ratio" in missing:
            notes.append("涨跌停数据缺失（可能非交易日）")
        if "breadth" in missing:
            notes.append("市场宽度数据缺失")
        if "north_flow" in missing:
            notes.append("北向资金数据缺失")
        if "margin_change" in missing:
            notes.append("融资余额数据缺失")
        if "rsi" in missing:
            notes.append("RSI 技术指标缺失")
        if "turnover_rate" in missing:
            notes.append("换手率数据缺失")
        if "pe_percentile" in missing:
            notes.append("估值百分位数据缺失")
        if "volume_ratio" in missing:
            notes.append("量比数据缺失")
        if "discussion_volume" in missing:
            notes.append("社区讨论热度数据缺失")
        if "community_sentiment" in missing:
            notes.append("社区情绪数据缺失")
        if not notes:
            notes.append("情绪极端不等于立即反转，可能持续一段时间")
        return notes

    def _fallback_result(self, reason: str) -> Dict[str, Any]:
        return {
            "status": "error",
            "fetch_time": datetime.now().isoformat(),
            "score": 50.0,
            "stage": self._build_phase_result("voices_rising"),
            "direction": "neutral",
            "confidence": 0.3,
            "indicators": {},
            "raw_data": {},
            "special_signals": [],
            "uncertainties": [reason],
            "community": None,
        }
