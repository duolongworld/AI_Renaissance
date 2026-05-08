"""
A股行业板块景气数据源

通过 AKShare 采集行业板块情绪指标，供舆情 Agent 调用。
对应的分析层 Skill 见 skills/news/industry_sentiment_tracker/SKILL.md

设计原则：
  - 每个 stock_code 先解析所属行业板块，再采集行业指标
  - 每个指标独立 try/except，单个指标失败不影响整体评分
  - 行业解析失败时返回 status=error，不阻塞后续个股分析
  - 整体采集控制在 15 秒内完成
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import math

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
    "industry_breadth":    0.25,  # 板块涨跌比
    "industry_fund_flow":  0.25,  # 板块资金净流入
    "industry_turnover":   0.20,  # 板块换手率异动
    "industry_limit_ratio":0.15,  # 板块涨跌停比
    "industry_rank":       0.15,  # 板块涨幅排名
}

# 情绪阶段定义（与大盘一致）
SCORE_LEVELS = [
    (0,  20,  "行业冰点", "行业极度低迷，逆向关注低估值龙头",     "40-60%", "bullish"),
    (21, 35,  "行业偏冷", "行业景气偏低，关注政策催化",           "30-50%", "bullish"),
    (36, 45,  "偏冷中性", "行业景气一般，等待信号",               "20-40%", "neutral"),
    (46, 54,  "中性均衡", "行业景气中性，精选个股",               "30-50%", "neutral"),
    (55, 65,  "偏热中性", "行业景气偏暖，注意追高风险",           "20-40%", "neutral"),
    (66, 80,  "行业偏热", "行业过热，控制仓位",                   "10-30%", "bearish"),
    (81, 100, "行业沸点", "行业极度亢奋，警惕回调，大幅减仓",     "0-20%",  "bearish"),
]


class IndustrySentimentDataSource:
    """A股行业板块景气数据源"""

    def __init__(self):
        self.name = "行业板块景气数据源"
        self._board_cache = None  # 缓存行业板块列表
        self._fund_flow_cache = None  # 缓存行业资金流
        logger.info(f"[数据源] {self.name} 初始化完成 (akshare={'可用' if AKSHARE_AVAILABLE else '不可用'})")

    def get_industry_sentiment(self, stock_code: str) -> Dict[str, Any]:
        """
        采集个股所属行业板块的景气指标并计算综合温度

        Args:
            stock_code: 股票代码（纯数字，如 300620）

        Returns:
            行业景气数据字典
        """
        if not AKSHARE_AVAILABLE:
            return self._fallback_result("akshare 未安装，无法采集行业数据")

        code = stock_code.strip().upper()
        for prefix in ("SH", "SZ", "BJ"):
            if code.startswith(prefix):
                code = code[len(prefix):]
                break

        # ── 第1步：解析行业归属 ──
        industry_name = self._resolve_industry(code)
        if not industry_name:
            logger.warning(f"[{self.name}] 无法解析 {code} 所属行业板块")
            return self._fallback_result(f"无法解析 {code} 所属行业板块")

        logger.info(f"[{self.name}] {code} 属于行业: {industry_name}")

        indicators = {}
        raw_data = {"industry_name": industry_name}

        # ── 第2步：采集行业指标 ──

        # 2.1 板块涨跌停 + 涨跌幅（从行业板块列表获取）
        try:
            board_data = self._get_board_data(industry_name)
            if board_data:
                raw_data["limit_up"] = board_data.get("limit_up", 0)
                raw_data["limit_down"] = board_data.get("limit_down", 0)
                raw_data["change_pct"] = board_data.get("change_pct", 0)
                raw_data["turnover_rate"] = board_data.get("turnover_rate", 0)

                # 涨跌停比
                lu = board_data.get("limit_up", 0)
                ld = board_data.get("limit_down", 0)
                if lu is not None and ld is not None and (lu + ld) > 0:
                    indicators["industry_limit_ratio"] = (lu / (lu + ld)) * 100
                    logger.info(f"[{self.name}] 涨停:{lu} 跌停:{ld} → 情绪分:{indicators['industry_limit_ratio']:.1f}")
        except Exception as e:
            logger.warning(f"[{self.name}] 板块涨跌停数据获取失败: {e}")

        # 2.2 板块内涨跌比（从成分股获取）
        try:
            breadth = self._get_industry_breadth(industry_name)
            raw_data["breadth"] = breadth
            if breadth is not None:
                indicators["industry_breadth"] = breadth * 100
                logger.info(f"[{self.name}] 板块上涨占比:{breadth:.1%} → 情绪分:{indicators['industry_breadth']:.1f}")
        except Exception as e:
            logger.warning(f"[{self.name}] 板块涨跌比获取失败: {e}")

        # 2.3 板块资金流
        try:
            fund_flow = self._get_industry_fund_flow(industry_name)
            raw_data["fund_flow_net"] = fund_flow
            if fund_flow is not None:
                indicators["industry_fund_flow"] = self._normalize_fund_flow(fund_flow)
                sign = "+" if fund_flow > 0 else ""
                logger.info(f"[{self.name}] 板块资金流:{sign}{fund_flow:.1f}亿 → 情绪分:{indicators['industry_fund_flow']:.1f}")
        except Exception as e:
            logger.warning(f"[{self.name}] 板块资金流获取失败: {e}")

        # 2.4 板块换手率异动
        try:
            turnover_zscore = self._get_industry_turnover(industry_name)
            raw_data["turnover_zscore"] = turnover_zscore
            if turnover_zscore is not None:
                indicators["industry_turnover"] = max(0, min(100, 50 + turnover_zscore * 16.7))
                logger.info(f"[{self.name}] 换手率Z-score:{turnover_zscore:.2f} → 情绪分:{indicators['industry_turnover']:.1f}")
        except Exception as e:
            logger.warning(f"[{self.name}] 板块换手率获取失败: {e}")

        # 2.5 板块涨幅排名
        try:
            rank_pct = self._get_industry_rank(industry_name)
            raw_data["rank_percentile"] = rank_pct
            if rank_pct is not None:
                indicators["industry_rank"] = rank_pct * 100
                logger.info(f"[{self.name}] 板块涨幅排名百分位:{rank_pct:.1%} → 情绪分:{indicators['industry_rank']:.1f}")
        except Exception as e:
            logger.warning(f"[{self.name}] 板块排名获取失败: {e}")

        # ── 第3步：综合评分 ──
        score = self._calculate_score(indicators)
        stage = self._get_stage(score)
        direction = stage["direction"]
        special_signals = self._detect_special_signals(raw_data, score)
        confidence = self._calc_confidence(score, special_signals, indicators)

        # 过滤 raw_data 中的 NaN/Inf
        raw_data = self._sanitize_dict(raw_data)

        return {
            "status": "success",
            "fetch_time": datetime.now().isoformat(),
            "industry_name": industry_name,
            "score": score,
            "stage": stage,
            "direction": direction,
            "confidence": confidence,
            "position_suggestion": stage.get("position", "30-50%"),
            "special_signals": special_signals,
            "indicators": self._sanitize_dict(indicators),
            "raw_data_summary": raw_data,
            "uncertainties": self._get_uncertainties(indicators),
        }

    # ── 行业解析 ──────────────────────────────────

    def _resolve_industry(self, stock_code: str) -> Optional[str]:
        """
        解析个股所属行业板块名称
        策略：从行业板块列表获取所有板块名，遍历查成分股找匹配
        优化：只遍历涨幅前20的板块（热门板块优先）
        """
        try:
            boards = self._load_board_list()
            if boards is None or boards.empty:
                return None

            # 板块名列（第2列）
            board_col = boards.columns[1]
            # 先试热门板块（按成交额排序，取前30）
            vol_col = boards.columns[6]  # 成交额列
            top_boards = boards.nlargest(30, vol_col)

            for _, row in top_boards.iterrows():
                board_name = str(row[board_col])
                try:
                    cons = ak.stock_board_industry_cons_em(symbol=board_name)
                    if cons is not None and not cons.empty:
                        # 代码列（第2列）
                        code_col = cons.columns[1]
                        if stock_code in cons[code_col].astype(str).tolist():
                            logger.info(f"[{self.name}] 在板块 '{board_name}' 中找到 {stock_code}")
                            return board_name
                except Exception:
                    continue

            # 如果前30没找到，再试全部（但限制前80）
            all_names = boards[board_col].tolist()
            checked = set(top_boards[board_col].tolist())
            for name in all_names[:80]:
                if name in checked:
                    continue
                try:
                    cons = ak.stock_board_industry_cons_em(symbol=name)
                    if cons is not None and not cons.empty:
                        code_col = cons.columns[1]
                        if stock_code in cons[code_col].astype(str).tolist():
                            return name
                except Exception:
                    continue

            return None
        except Exception as e:
            logger.warning(f"[{self.name}] 行业解析失败: {e}")
            return None

    def _load_board_list(self):
        """加载并缓存行业板块列表"""
        if self._board_cache is not None:
            return self._board_cache
        try:
            df = ak.stock_board_industry_name_em()
            self._board_cache = df
            return df
        except Exception as e:
            logger.warning(f"[{self.name}] 行业板块列表获取失败: {e}")
            return None

    # ── 数据采集 ──────────────────────────────────

    def _get_board_data(self, industry_name: str) -> Optional[Dict]:
        """从板块列表获取涨跌停和涨跌幅数据"""
        try:
            boards = self._load_board_list()
            if boards is None or boards.empty:
                return None
            name_col = boards.columns[1]
            row = boards[boards[name_col] == industry_name]
            if row.empty:
                return None
            row = row.iloc[0]
            return {
                "limit_up": int(row.iloc[8]) if not self._is_nan(row.iloc[8]) else 0,
                "limit_down": int(row.iloc[9]) if not self._is_nan(row.iloc[9]) else 0,
                "change_pct": float(row.iloc[4]) if not self._is_nan(row.iloc[4]) else 0,
                "turnover_rate": float(row.iloc[7]) if not self._is_nan(row.iloc[7]) else 0,
            }
        except Exception as e:
            logger.warning(f"[{self.name}] 板块数据获取失败: {e}")
            return None

    def _get_industry_breadth(self, industry_name: str) -> Optional[float]:
        """获取板块内上涨家数占比"""
        try:
            cons = ak.stock_board_industry_cons_em(symbol=industry_name)
            if cons is None or cons.empty:
                return None
            # 涨跌幅列（第5列或名为'涨跌幅'）
            change_col = cons.columns[4]
            changes = pd.to_numeric(cons[change_col], errors='coerce')
            changes = changes.dropna()
            if len(changes) == 0:
                return None
            up_count = int((changes > 0).sum())
            total = len(changes)
            return up_count / total
        except Exception as e:
            logger.warning(f"[{self.name}] 板块涨跌比获取失败: {e}")
            return None

    def _get_industry_fund_flow(self, industry_name: str) -> Optional[float]:
        """获取板块主力资金净流入（亿元）"""
        try:
            df = self._load_fund_flow()
            if df is None or df.empty:
                return None
            name_col = df.columns[1]  # 行业名称列
            row = df[df[name_col] == industry_name]
            if row.empty:
                # 模糊匹配
                for idx, r in df.iterrows():
                    if industry_name in str(r[name_col]) or str(r[name_col]) in industry_name:
                        row = df.iloc[[idx]]
                        break
            if row.empty:
                return None
            # 主力净流入列（第3列，通常为"今日主力净流入-净额"）
            fund_col = df.columns[2]
            val = float(row.iloc[0][fund_col])
            if np.isnan(val) or np.isinf(val):
                return None
            return val / 1e8  # 转为亿元
        except Exception as e:
            logger.warning(f"[{self.name}] 板块资金流获取失败: {e}")
            return None

    def _load_fund_flow(self):
        """加载并缓存行业资金流排名"""
        if self._fund_flow_cache is not None:
            return self._fund_flow_cache
        try:
            df = ak.stock_sector_fund_flow_rank(indicator="今日", sector_type="行业资金流")
            self._fund_flow_cache = df
            return df
        except Exception as e:
            logger.warning(f"[{self.name}] 行业资金流排名获取失败: {e}")
            return None

    def _get_industry_turnover(self, industry_name: str) -> Optional[float]:
        """获取板块换手率异动（Z-score）"""
        try:
            boards = self._load_board_list()
            if boards is None or boards.empty:
                return None
            # 换手率列（第8列）
            turnover_col = boards.columns[7]
            all_turnovers = pd.to_numeric(boards[turnover_col], errors='coerce').dropna()
            name_col = boards.columns[1]
            row = boards[boards[name_col] == industry_name]
            if row.empty:
                return None
            current_turnover = float(row.iloc[0][turnover_col])
            if np.isnan(current_turnover):
                return None
            # Z-score
            mean_t = all_turnovers.mean()
            std_t = all_turnovers.std()
            if std_t == 0 or np.isnan(std_t):
                return None
            zscore = (current_turnover - mean_t) / std_t
            return float(zscore)
        except Exception as e:
            logger.warning(f"[{self.name}] 板块换手率获取失败: {e}")
            return None

    def _get_industry_rank(self, industry_name: str) -> Optional[float]:
        """获取板块涨幅排名百分位"""
        try:
            boards = self._load_board_list()
            if boards is None or boards.empty:
                return None
            change_col = boards.columns[4]  # 涨跌幅列
            all_changes = pd.to_numeric(boards[change_col], errors='coerce').dropna()
            name_col = boards.columns[1]
            row = boards[boards[name_col] == industry_name]
            if row.empty:
                return None
            current_change = float(row.iloc[0][change_col])
            if np.isnan(current_change):
                return None
            # 百分位排名
            rank_pct = (all_changes < current_change).sum() / len(all_changes)
            return float(rank_pct)
        except Exception as e:
            logger.warning(f"[{self.name}] 板块排名获取失败: {e}")
            return None

    # ── 标准化函数 ──────────────────────────────────

    def _normalize_fund_flow(self, flow: float) -> float:
        """资金流标准化到 0-100"""
        # 假设 ±50亿 为极端值
        return max(0, min(100, 50 + flow / 5))

    # ── 综合评分 ──────────────────────────────────

    def _calculate_score(self, indicators: dict) -> float:
        total_weight = 0
        total_score = 0
        for key, weight in WEIGHTS.items():
            val = indicators.get(key)
            if val is not None:
                val_f = float(val)
                if not (math.isnan(val_f) or math.isinf(val_f)):
                    total_score += val_f * weight
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
        return {"name": SCORE_LEVELS[-1][2], "suggestion": SCORE_LEVELS[-1][3],
                "position": SCORE_LEVELS[-1][4], "direction": SCORE_LEVELS[-1][5]}

    def _detect_special_signals(self, raw: dict, score: float) -> list:
        signals = []
        if score >= 85:
            signals.append("行业沸点")
        if score <= 15:
            signals.append("行业冰点")

        lu = raw.get("limit_up") or 0
        if lu >= 5:
            signals.append("板块龙头异动")

        fund = raw.get("fund_flow_net")
        if fund is not None:
            if fund > 20:
                signals.append("资金大幅流入")
            elif fund < -20:
                signals.append("资金大幅流出")

        rank = raw.get("rank_percentile")
        if rank is not None:
            if rank > 0.9:
                signals.append("板块涨幅领涨")
            elif rank < 0.1:
                signals.append("板块轮动下跌")

        return signals

    def _calc_confidence(self, score, special_signals, indicators) -> float:
        available = sum(1 for v in indicators.values() if v is not None and not (isinstance(v, float) and (math.isnan(v) or math.isinf(v))))
        total = len(WEIGHTS)
        coverage = available / total if total > 0 else 0

        if score <= 20 or score >= 80:
            base = 0.65
        elif score <= 35 or score >= 65:
            base = 0.5
        else:
            base = 0.35

        signal_boost = min(len(special_signals) * 0.05, 0.15)
        coverage_penalty = 0 if coverage >= 0.5 else (0.5 - coverage) * 0.3

        return round(min(0.9, max(0.2, base + signal_boost - coverage_penalty)), 2)

    def _get_uncertainties(self, indicators: dict) -> list:
        missing = [k for k, v in indicators.items() if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v)))]
        notes = []
        if "industry_breadth" in missing:
            notes.append("板块涨跌比数据缺失")
        if "industry_fund_flow" in missing:
            notes.append("板块资金流数据缺失")
        if "industry_turnover" in missing:
            notes.append("板块换手率数据缺失")
        if "industry_limit_ratio" in missing:
            notes.append("板块涨跌停数据缺失")
        if "industry_rank" in missing:
            notes.append("板块涨幅排名缺失")
        if not notes:
            notes.append("行业景气极端不等于个股走势，可能存在背离")
        return notes

    # ── 工具函数 ──────────────────────────────────

    @staticmethod
    def _is_nan(val) -> bool:
        if val is None:
            return True
        try:
            return math.isnan(float(val)) or math.isinf(float(val))
        except (ValueError, TypeError):
            return False

    @staticmethod
    def _sanitize_dict(d: dict) -> dict:
        """递归清理字典中的 NaN/Inf 值"""
        result = {}
        for k, v in d.items():
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                result[k] = None
            elif isinstance(v, dict):
                result[k] = IndustrySentimentDataSource._sanitize_dict(v)
            elif isinstance(v, list):
                result[k] = [None if isinstance(x, float) and (math.isnan(x) or math.isinf(x)) else x for x in v]
            else:
                result[k] = v
        return result

    def _fallback_result(self, reason: str) -> Dict[str, Any]:
        return {
            "status": "error",
            "fetch_time": datetime.now().isoformat(),
            "industry_name": None,
            "score": 50.0,
            "stage": {"name": "数据不足", "suggestion": reason, "position": "30-50%", "direction": "neutral"},
            "direction": "neutral",
            "confidence": 0.3,
            "position_suggestion": "30-50%",
            "special_signals": [],
            "indicators": {},
            "raw_data_summary": {},
            "uncertainties": [reason],
        }
