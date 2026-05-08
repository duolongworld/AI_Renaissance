"""
A股大盘市场情绪数据源

通过 AKShare 采集全市场情绪指标，供舆情 Agent 调用。
对应的分析层 Skill 见 skills/news/market_sentiment_tracker/SKILL.md

设计原则：每个指标独立 try/except，单个指标失败不影响整体评分。
整体采集控制在 30 秒内完成，超时返回部分数据。
"""

from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple
import threading

from loguru import logger

try:
    import akshare as ak
    import pandas as pd
    import numpy as np
    AKSHARE_AVAILABLE = True
except ImportError:
    AKSHARE_AVAILABLE = False


# 情绪评分权重配置（与 SKILL.md 对齐）
WEIGHTS = {
    "turnover_rate":   0.15,  # 换手率异动
    "limit_up_ratio":  0.15,  # 涨跌停比
    "margin_change":   0.15,  # 融资余额变化
    "north_flow":      0.12,  # 北向资金
    "breadth":         0.13,  # 涨跌比（市场宽度）
    "volume_ratio":    0.10,  # 量比/成交额变化
    "rsi":             0.10,  # RSI 技术指标
    "pe_percentile":   0.10,  # 估值历史百分位
}

# 情绪阶段定义
SCORE_LEVELS = [
    (0,  20,  "极度恐慌", "冰点区域，逆向布局信号",           "50-70%", "bullish"),
    (21, 35,  "冷淡悲观", "情绪低迷，逢低关注低估值",         "40-60%", "bullish"),
    (36, 45,  "偏冷中性", "持仓为主，关注结构性机会",         "30-50%", "neutral"),
    (46, 54,  "中性均衡", "精选个股，减少频繁操作",           "30-50%", "neutral"),
    (55, 65,  "偏热乐观", "控制加仓节奏，注意风险",           "20-40%", "neutral"),
    (66, 80,  "情绪偏热", "逐步减仓，锁定部分利润",           "20-30%", "bearish"),
    (81, 100, "极度亢奋", "沸点区域，警惕顶部，大幅降低仓位", "10-20%", "bearish"),
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
                "stage": {...},
                "direction": str,
                "confidence": float,
                "indicators": {...},
                "raw_data": {...},
                "special_signals": [...],
                ...
            }
        """
        if not AKSHARE_AVAILABLE:
            return self._fallback_result("akshare 未安装，无法采集大盘数据")

        indicators = {}
        raw_data = {}

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

        # 计算综合得分
        score = self._calculate_score(indicators)
        stage = self._get_stage(score)
        direction = stage["direction"]
        special_signals = self._detect_special_signals(raw_data, score)

        # 确定置信度
        confidence = self._calc_confidence(score, special_signals, indicators)

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
        # stock_dt_pool_em 可能不存在于新版 akshare，尝试多种接口
        for func_name in ("stock_dt_pool_em", "stock_zt_pool_dtgc_em"):
            try:
                func = getattr(ak, func_name)
                dt = func(date=date)
                dt_count = len(dt)
                break
            except (AttributeError, Exception):
                continue

        # 如果涨跌停都拿不到，尝试前几个交易日
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
        """获取市场涨跌比（简化方案：用上证指数涨跌推算）"""
        try:
            # 简化方案：获取上证指数最新涨跌幅，推算市场宽度
            # 涨跌幅 > 0 约对应上涨占比 > 50%
            df = ak.stock_zh_index_daily(symbol="sh000001")
            if df is not None and not df.empty:
                df = df.sort_values("date", ascending=False)
                latest_close = float(df.iloc[0]["close"])
                prev_close = float(df.iloc[1]["close"]) if len(df) > 1 else latest_close
                chg_pct = (latest_close - prev_close) / prev_close * 100
                # 简化映射：涨跌幅 -3% ~ +3% → 上涨占比 20% ~ 80%
                breadth = max(0.1, min(0.9, 0.5 + chg_pct / 10))
                return breadth
        except Exception as e:
            logger.warning(f"[{self.name}] 市场宽度推算失败: {e}")
        return None

    def _get_north_flow(self) -> Optional[float]:
        """获取北向资金净流入（亿元）"""
        try:
            # 新版 akshare 使用 stock_hsgt_hist_em
            df = ak.stock_hsgt_hist_em(symbol="沪股通")
            if df is not None and not df.empty:
                df = df.sort_values("日期", ascending=False)
                latest = df.iloc[0]
                # 尝试多种列名
                for col in ["当日资金流入", "当日成交净买额", "净买入"]:
                    if col in df.columns:
                        val = float(latest[col])
                        if np.isnan(val) or np.isinf(val):
                            continue
                        return val / 1e8
        except Exception:
            pass
        try:
            # 备用接口
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
                # 防止 NaN/Inf
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
                # 防止 NaN/Inf
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

    def _get_stage(self, score: float) -> dict:
        for lo, hi, name, suggestion, position, direction in SCORE_LEVELS:
            if lo <= score <= hi:
                return {
                    "name": name,
                    "suggestion": suggestion,
                    "position": position,
                    "direction": direction,
                }
        return SCORE_LEVELS[-1][2:]

    def _detect_special_signals(self, raw: dict, score: float) -> list:
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

        return signals

    def _calc_confidence(self, score, special_signals, indicators) -> float:
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

        # 数据覆盖度惩罚
        coverage_penalty = 0 if coverage >= 0.5 else (0.5 - coverage) * 0.3

        return round(min(0.9, max(0.2, base + signal_boost - coverage_penalty)), 2)

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
        if not notes:
            notes.append("情绪极端不等于立即反转，可能持续一段时间")
        return notes

    def _fallback_result(self, reason: str) -> Dict[str, Any]:
        return {
            "status": "error",
            "fetch_time": datetime.now().isoformat(),
            "score": 50.0,
            "stage": {"name": "数据不足", "suggestion": reason, "position": "30-50%", "direction": "neutral"},
            "direction": "neutral",
            "confidence": 0.3,
            "indicators": {},
            "raw_data": {},
            "special_signals": [],
            "uncertainties": [reason],
        }
