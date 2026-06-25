"""
A股行业板块景气数据源

通过 HTTP 直连东方财富公开 API 采集行业板块情绪指标，供舆情 Agent 调用。
对应的分析层 Skill 见 skills/news/industry_sentiment_tracker/SKILL.md

设计原则：
  - 每个 stock_code 先解析所属行业板块，再采集行业指标
  - 每个指标独立 try/except，单个指标失败不影响整体评分
  - 行业解析失败时返回 status=error，不阻塞后续个股分析
  - 整体采集控制在 15 秒内完成
  - HTTP 直连替代 AkShare，绕过代理阻断 + 指数退避重试
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import math
import time

from loguru import logger

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    import pandas as pd
    import numpy as np
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False


# ── 东方财富 API 配置 ────────────────────────────
_EASTMONEY_API_HOST = "https://push2.eastmoney.com/api/qt/clist/get"
_EASTMONEY_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://data.eastmoney.com/",
}
_API_TIMEOUT = 15
_MAX_RETRIES = 3
_RETRY_BACKOFF = 2.0  # 秒

# 公用 API token
_EASTMONEY_UT = "bd1d9ddb04089700cf9c27f6f7426281"


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
        self._session = None
        status = "HTTP直连" if HAS_REQUESTS else "不可用(缺少requests)"
        logger.info(f"[数据源] {self.name} 初始化完成 ({status})")

    def _get_session(self):
        """获取可复用的 requests.Session（绕过系统代理）"""
        if self._session is None and HAS_REQUESTS:
            self._session = requests.Session()
            self._session.trust_env = False  # 绕过代理
        return self._session

    # ── HTTP 底层：指数退避重试 ────────────────────

    @staticmethod
    def _fetch_eastmoney(params: dict, timeout: int = _API_TIMEOUT) -> Optional[dict]:
        """调用东方财富 API，自动重试"""
        last_error = None
        session = requests.Session()
        session.trust_env = False

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                resp = session.get(
                    _EASTMONEY_API_HOST,
                    params=params,
                    headers=_EASTMONEY_HEADERS,
                    timeout=timeout,
                )
                resp.raise_for_status()
                data = resp.json()
                if data and data.get("data") is not None:
                    return data["data"]
                return None
            except Exception as e:
                last_error = e
                if attempt < _MAX_RETRIES:
                    wait = _RETRY_BACKOFF * attempt
                    logger.debug(f"[Industry] API重试 {attempt}/{_MAX_RETRIES}, 等待{wait}s: {e}")
                    time.sleep(wait)
        logger.warning(f"[Industry] API调用失败(重试{_MAX_RETRIES}次): {last_error}")
        return None

    def get_industry_sentiment(self, stock_code: str) -> Dict[str, Any]:
        """
        采集个股所属行业板块的景气指标并计算综合温度

        Args:
            stock_code: 股票代码（纯数字，如 300620）

        Returns:
            行业景气数据字典
        """
        if not HAS_REQUESTS or not HAS_PANDAS:
            return self._fallback_result("缺少 requests/pandas 依赖，无法采集行业数据")

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

            name_col = boards.columns[1]
            # 先试热门板块（按成交额排序，取前30）
            vol_col_idx = list(boards.columns).index("成交额") if "成交额" in boards.columns else 6
            top_boards = boards.nlargest(30, boards.columns[vol_col_idx])

            for _, row in top_boards.iterrows():
                board_name = str(row[name_col])
                try:
                    cons = self._fetch_board_constituents(board_name)
                    if cons is not None and not cons.empty:
                        code_col = cons.columns[1]
                        if stock_code in cons[code_col].astype(str).tolist():
                            logger.info(f"[{self.name}] 在板块 '{board_name}' 中找到 {stock_code}")
                            return board_name
                except Exception:
                    continue

            # 如果前30没找到，再试全部（但限制前80）
            all_names = boards[name_col].tolist()
            checked = set(top_boards[name_col].tolist())
            for name in all_names[:80]:
                if name in checked:
                    continue
                try:
                    cons = self._fetch_board_constituents(name)
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
        """加载并缓存行业板块列表（HTTP 直连替代 AkShare）"""
        if self._board_cache is not None:
            return self._board_cache
        try:
            data = self._fetch_eastmoney({
                "pn": "1", "pz": "200", "po": "1", "np": "1",
                "ut": _EASTMONEY_UT, "fltt": "2", "invt": "2",
                "fid": "f3", "fs": "m:90+t:2",
                "fields": "f2,f3,f4,f12,f14,f20,f104,f105,f152,f16,f128,f136",
            })
            if data is None or not data.get("diff"):
                return None

            rows = []
            for item in data["diff"]:
                rows.append({
                    "序号": len(rows) + 1,
                    "板块名称": item.get("f14", ""),
                    "板块代码": item.get("f12", ""),
                    "最新价": self._safe_float(item.get("f2")),
                    "涨跌幅": self._safe_float(item.get("f3")),
                    "总市值": self._safe_float(item.get("f20")),
                    "成交额": self._safe_float(item.get("f16")),
                    "换手率": self._safe_float(item.get("f152")),
                    "上涨家数": int(self._safe_float(item.get("f104")) or 0),
                    "下跌家数": int(self._safe_float(item.get("f105")) or 0),
                    "领涨股票": item.get("f128", ""),
                    "领涨涨幅": self._safe_float(item.get("f136")),
                })
            df = pd.DataFrame(rows)
            self._board_cache = df
            return df
        except Exception as e:
            logger.warning(f"[{self.name}] 行业板块列表获取失败: {e}")
            return None

    # ── 数据采集 ──────────────────────────────────

    def _fetch_board_constituents(self, board_name: str) -> Optional[pd.DataFrame]:
        """
        获取行业板块成分股列表（HTTP 直连替代 AkShare）
        通过板块名称查找对应板块代码，再查询成分股
        """
        try:
            # 1. 从缓存的板块列表找到板块代码
            boards = self._load_board_list()
            if boards is None or boards.empty:
                return None
            name_col = boards.columns[1]
            matching = boards[boards[name_col] == board_name]
            if matching.empty:
                logger.warning(f"[{self.name}] 未找到板块: {board_name}")
                return None
            board_code = str(matching.iloc[0]["板块代码"])

            # 2. 查询成分股
            data = self._fetch_eastmoney({
                "pn": "1", "pz": "500", "po": "1", "np": "1",
                "ut": _EASTMONEY_UT, "fltt": "2", "invt": "2",
                "fid": "f3", "fs": f"b:{board_code}",
                "fields": "f2,f3,f4,f5,f6,f12,f14,f20",
            })
            if data is None or not data.get("diff"):
                return None

            rows = []
            for item in data["diff"]:
                rows.append({
                    "序号": len(rows) + 1,
                    "代码": item.get("f12", ""),
                    "名称": item.get("f14", ""),
                    "最新价": self._safe_float(item.get("f2")),
                    "涨跌幅": self._safe_float(item.get("f3")),
                    "涨跌额": self._safe_float(item.get("f4")),
                    "成交量": self._safe_float(item.get("f5")),
                    "成交额": self._safe_float(item.get("f6")),
                    "总市值": self._safe_float(item.get("f20")),
                })
            return pd.DataFrame(rows)
        except Exception as e:
            logger.warning(f"[{self.name}] 成分股查询失败({board_name}): {e}")
            return None

    @staticmethod
    def _safe_float(val) -> Optional[float]:
        """安全转换为 float，处理 None/不可解析的值"""
        if val is None:
            return None
        try:
            v = float(val)
            return None if math.isnan(v) or math.isinf(v) else v
        except (ValueError, TypeError):
            return None

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
            up_count = int(row["上涨家数"]) if not self._is_nan(row["上涨家数"]) else 0
            down_count = int(row["下跌家数"]) if not self._is_nan(row["下跌家数"]) else 0
            return {
                "limit_up": up_count,
                "limit_down": down_count,
                "change_pct": float(row["涨跌幅"]) if not self._is_nan(row["涨跌幅"]) else 0,
                "turnover_rate": float(row["换手率"]) if not self._is_nan(row["换手率"]) else 0,
            }
        except Exception as e:
            logger.warning(f"[{self.name}] 板块数据获取失败: {e}")
            return None

    def _get_industry_breadth(self, industry_name: str) -> Optional[float]:
        """获取板块内上涨家数占比"""
        try:
            cons = self._fetch_board_constituents(industry_name)
            if cons is None or cons.empty:
                return None
            changes = pd.to_numeric(cons["涨跌幅"], errors='coerce')
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
            name_col = "板块名称"
            row = df[df[name_col] == industry_name]
            if row.empty:
                for idx, r in df.iterrows():
                    if industry_name in str(r[name_col]) or str(r[name_col]) in industry_name:
                        row = df.iloc[[idx]]
                        break
            if row.empty:
                return None
            val = float(row.iloc[0]["主力净流入-净额"])
            if np.isnan(val) or np.isinf(val):
                return None
            return val / 1e8  # 转为亿元
        except Exception as e:
            logger.warning(f"[{self.name}] 板块资金流获取失败: {e}")
            return None

    def _load_fund_flow(self):
        """加载并缓存行业资金流排名（HTTP 直连替代 AkShare）"""
        if self._fund_flow_cache is not None:
            return self._fund_flow_cache
        try:
            data = self._fetch_eastmoney({
                "pn": "1", "pz": "200", "po": "1", "np": "1",
                "ut": _EASTMONEY_UT, "fltt": "2", "invt": "2",
                "fid": "f62", "fs": "m:90+t:2",
                "fields": "f2,f3,f4,f12,f14,f62,f66,f69,f72,f75,f78,f81,f84,f87",
            })
            if data is None or not data.get("diff"):
                return None

            rows = []
            for item in data["diff"]:
                rows.append({
                    "序号": len(rows) + 1,
                    "板块名称": item.get("f14", ""),
                    "主力净流入-净额": self._safe_float(item.get("f62")),
                    "涨跌幅": self._safe_float(item.get("f3")),
                })
            df = pd.DataFrame(rows)
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
            all_turnovers = pd.to_numeric(boards["换手率"], errors='coerce').dropna()
            name_col = boards.columns[1]
            row = boards[boards[name_col] == industry_name]
            if row.empty:
                return None
            current_turnover = float(row.iloc[0]["换手率"])
            if np.isnan(current_turnover):
                return None
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
            all_changes = pd.to_numeric(boards["涨跌幅"], errors='coerce').dropna()
            name_col = boards.columns[1]
            row = boards[boards[name_col] == industry_name]
            if row.empty:
                return None
            current_change = float(row.iloc[0]["涨跌幅"])
            if np.isnan(current_change):
                return None
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
