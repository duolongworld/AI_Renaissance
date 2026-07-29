"""
Macro Data Source - 宏观数据统一采集层 (专家4组)

整合 FRED API (美国宏观) + akshare (中国宏观) + 第三方行情数据，
为 7 层流水线 (Layer 0-5) 提供原始输入数据。

设计原则：
- 每个指标独立 try/except，单个指标失败不影响整体
- 无法获取的字段用 fallback 值填充，标记 data_source="fallback"
- 所有返回数据统一标注来源 (fred / akshare / fallback / computed)

依赖: pip install fredapi akshare pandas
"""

from __future__ import annotations

import os
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import datetime, date, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from loguru import logger

# 加载 .env 文件中的环境变量（若存在）
load_dotenv()

# ── 全局 API 超时配置 ──
FRED_TIMEOUT = 40      # FRED 单次 API 调用超时（秒）
AKSHARE_TIMEOUT = 30   # akshare 单次函数调用超时（秒）
MARKET_TIMEOUT = 25    # 行情数据超时（秒）

# ── 全局目标日期 (历史日期截断) ──
_TARGET_DATE: Optional[str] = None  # 格式 YYYY-MM-DD，由 fetch_macro_data() 设置

def _get_latest_by_date(df: "pd.DataFrame", date_cols: Optional[List[str]] = None) -> Any:
    """
    根据全局 _TARGET_DATE 截断 DataFrame 到历史日期，返回最新一行。
    - 若 _TARGET_DATE 已设置，筛选 date_col ≤ _TARGET_DATE
    - 若未设置，直接取 df.iloc[-1]
    """
    if not HAS_PANDAS or df is None or df.empty:
        return None
    if _TARGET_DATE is None:
        return df.iloc[-1]
    
    if date_cols is None:
        date_cols = ["日期", "date", "Date", "DATE", "报告期", "月份", "时间", "指标名称",
                     "trade_date", "day", "report_date", "统计时间", "TRADE_DATE"]
    
    # 找到实际存在的日期列
    date_col = None
    for col in date_cols:
        if col in df.columns:
            date_col = col
            break
    if date_col is None:
        return df.iloc[-1]
    
    # 日期比较：统一转为 YYYYMM 数字格式进行比较
    try:
        date_series = df[date_col].astype(str)
        # 规范化: "2026年05月份"→"202605", "202501"→"202501", "2025-06-01"→"20250601"
        normalized = date_series.str.replace(r'[年月日\-份]', '', regex=True)
        target_normalized = _TARGET_DATE.replace('-', '')
        mask = normalized <= target_normalized
        filtered = df[mask]
        if not filtered.empty:
            # 取最新的一行：按规范化日期排序后取最大值
            try:
                filtered_dates = filtered[date_col].astype(str).str.replace(r'[年月日\-份]', '', regex=True)
                max_idx = filtered_dates.astype(int).idxmax()
                return filtered.loc[max_idx]
            except Exception:
                return filtered.iloc[-1]
    except Exception:
        pass
    return df.iloc[-1]

# ── 超时封装器 ──
_TP_EXECUTOR = ThreadPoolExecutor(max_workers=1)

def _call_with_timeout(fn: Callable, timeout: float, label: str = "") -> Any:
    """在独立线程中执行 callable，超过 timeout 秒抛异常。"""
    future = _TP_EXECUTOR.submit(fn)
    try:
        return future.result(timeout=timeout)
    except FutureTimeoutError:
        logger.warning(f"[TIMEOUT] {label or fn.__name__} 超时 ({timeout}s)，跳过")
        raise TimeoutError(f"{label or fn.__name__} timeout after {timeout}s")
    except Exception:
        raise

# ═══════════════════════════════════════════════════════════════
# FRED API 令牌桶限速器
# ═══════════════════════════════════════════════════════════════
# FRED 免费 tier: 120 req/min = 2 req/s
# 使用令牌桶算法：容量 120 令牌，填充速率 2 令牌/秒
# - 允许短时突发（冷启动可立刻发 120 个请求）
# - 长期严格限制平均速率
# - burst 用完后按填充速率稳定放行

class FredRateLimiter:
    """FRED API 令牌桶限速器（线程安全）"""

    def __init__(self, capacity: float = 120.0, refill_rate: float = 2.0):
        """
        Args:
            capacity:   桶容量（令牌数），= FRED 每分钟请求上限
            refill_rate: 填充速率（令牌/秒），= capacity / 60
        """
        self._capacity = float(capacity)
        self._refill_rate = float(refill_rate)
        self._tokens = float(capacity)  # 当前令牌数，初始满桶
        self._last_refill = datetime.now()
        self._lock = threading.Lock()
        # 统计
        self.total_requests = 0
        self.total_waited = 0.0     # 累计等待时间（秒）
        self.total_429_retries = 0  # 429 重试次数

    def _refill(self) -> None:
        """按时间差补充令牌（调用方必须持有锁）"""
        now = datetime.now()
        elapsed = (now - self._last_refill).total_seconds()
        if elapsed > 0:
            self._tokens = min(self._capacity, self._tokens + elapsed * self._refill_rate)
            self._last_refill = now

    def acquire(self) -> float:
        """获取 1 个令牌。若当前无令牌则阻塞等待，返回实际等待秒数。"""
        with self._lock:
            self._refill()
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                self.total_requests += 1
                return 0.0
            # 令牌不足，计算需要等待的时间
            needed = 1.0 - self._tokens
            wait = needed / self._refill_rate
            self._tokens = 0.0
            self.total_requests += 1
            self.total_waited += wait
            return wait

    def report_429(self) -> float:
        """遇到 429 Too Many Requests 时调用。
        消耗 10 令牌作为惩罚并返回建议等待秒数。"""
        with self._lock:
            self._refill()
            penalty = min(self._tokens, 10.0)
            self._tokens -= penalty
            if self._tokens < 0:
                self._tokens = 0.0
            self.total_429_retries += 1
            wait = (10.0 - penalty) / self._refill_rate
            return max(wait, 1.0)

    @property
    def stats(self) -> Dict[str, Any]:
        with self._lock:
            self._refill()
            return {
                "tokens_available": round(self._tokens, 1),
                "capacity": self._capacity,
                "refill_rate": self._refill_rate,
                "total_requests": self.total_requests,
                "total_waited_seconds": round(self.total_waited, 1),
                "total_429_retries": self.total_429_retries,
            }

# 全局 FRED 限速器实例
_fred_limiter = FredRateLimiter(capacity=120.0, refill_rate=2.0)

try:
    import pandas as pd
    import numpy as np
    HAS_PANDAS = True
except ImportError:
    pd = None  # type: ignore[assignment]
    np = None  # type: ignore[assignment]
    HAS_PANDAS = False

try:
    from fredapi import Fred
    HAS_FREDAPI = True
except ImportError:
    Fred = None  # type: ignore[assignment]
    HAS_FREDAPI = False

try:
    import akshare as ak
    HAS_AKSHARE = True
except ImportError:
    ak = None  # type: ignore[assignment]
    HAS_AKSHARE = False

# ── API Key 配置 ──────────────────────────────────────────────
# 通过环境变量 FRED_API_KEY 或 .env 文件读取，不再硬编码 token
_FRED_API_KEY = os.getenv("FRED_API_KEY", "")

if not _FRED_API_KEY:
    _FRED_API_KEY_MISSING_MSG = (
        "FRED_API_KEY 未设置。请执行以下任一操作：\n"
        "  1. 复制 .env.example 为 .env，填入真实的 FRED API key\n"
        "  2. 设置环境变量: export FRED_API_KEY=your_key_here\n"
        "FRED 数据源将不可用，其他数据源不受影响。"
    )
else:
    _FRED_API_KEY_MISSING_MSG = ""

# ── FRED Series ID 映射表 ─────────────────────────────────────
# 所有可从 FRED 获取的字段及其对应的 Series ID
FRED_SERIES_MAP: Dict[str, str] = {
    # -- 美国增长 --
    # 注: ISM PMI 数据已于 2016 年从 FRED 移除，改由 akshare 获取
    # ism_manufacturing_pmi / ism_services_pmi → _fetch_akshare_us()
    "nonfarm_payrolls":           "PAYEMS",         # All Employees, Total Nonfarm (需算 MoM)
    "us_unemployment_rate":       "UNRATE",         # Unemployment Rate
    "gdp":                        "GDP",            # Gross Domestic Product (季频)
    "retail_sales":               "RSXFS",          # Retail Sales Ex Food Services (需算 YoY)
    "personal_consumption":       "PCE",            # Personal Consumption Expenditures
    "industrial_production":      "INDPRO",         # Industrial Production Index (需算 YoY)
    "housing_starts":             "HOUST",          # Housing Starts
    "initial_jobless_claims_4w":  "IC4WSA",         # 4-Week Moving Avg of Initial Claims
    # -- 美国通胀 --
    "core_pce":                   "PCEPILFE",       # Core PCE (需算 YoY)
    "cpi":                        "CPIAUCSL",       # CPI All Urban (需算 YoY)
    "core_cpi":                   "CPILFESL",       # Core CPI (需算 YoY)
    "eci_wage":                   "ECIWAG",         # ECI Wages & Salaries (季频, 需算 QoQ)
    "breakeven_5y5y":             "T5YIFR",         # 5Y5Y Forward Breakeven
    "tips_10y_breakeven":         "T10YIE",         # 10Y Breakeven Inflation
    # -- 美国流动性 --
    "sofr":                       "SOFR",           # Secured Overnight Financing Rate
    "effr":                       "DFF",            # Effective Federal Funds Rate
    "ffr":                        "FEDFUNDS",       # Fed Funds Rate (target, monthly avg)
    "fed_total_assets":           "WALCL",          # Fed Total Assets (周频)
    "us_m2":                      "M2SL",           # M2 Money Stock (需算 YoY)
    # -- 美国市场定价 --
    "us_10y_yield":               "DGS10",          # 10Y Treasury Yield
    "us_2y_yield":                "DGS2",           # 2Y Treasury Yield
    "us_ig_spread":               "BAMLC0A0CM",     # ICE BofA US Corporate Master OAS
    "us_hy_spread":               "BAMLH0A0HYM2",   # ICE BofA US High Yield OAS
    # -- 全球 --
    "dxy_broad":                  "DTWEXBGS",       # Broad Dollar Index
    # -- 其他可选 --
    "us_citi_surprise":           "CESIUSD",        # Citi Economic Surprise Index (US) - 可能下架
    "existing_home_sales":        "EXHOSLUSM495S",  # Monthly Supply of Existing Homes
}
# ── Fallback 默认值 ──────────────────────────────────────────
_FALLBACK_VALUES: Dict[str, Any] = {
    # 美国意外指数 — 中性值 0
    "us_surprise_index": 0.0,
    # 中国意外指数 — 中性值 0
    "china_surprise_index": 0.0,
    # 地缘政治评分 — 框架内部计算变量，不在数据层提供
    # 由 Layer 0 基于 NLP + 事件追踪生成，详见 _extract_cross_border_signals()
    # 欧元区 PMI — 荣枯线 (已有 akshare 实时源，此处仅兜底)
    "euro_pmi": 50.0,
    # CFTC 净头寸占比 — 中性
    "cftc_net_position_pct": 0.0,
    # 卖方看空占比 — 历史均值 (框架内部 NLP 计算)
    "sell_side_bearish_pct": 30.0,
    # 买方看空占比 — 历史均值 (框架内部 NLP 计算)
    "buy_side_bearish_pct": 20.0,
    # 信贷脉冲 — 中性
    "credit_pulse": 0.0,
    # 海外资金流入美股 — 中性
    "overseas_flow_us": 0.0,
    # 人民币 REER — 中性 100
    "rmb_reer": 100.0,
    # USD/CNH 1Y 远期点 — 无预设
    "usd_cnh_1y_forward": 0.0,
    # FF 隐含利率 — 动态，见 _dynamic_fallback
    # sp500_erp — 动态
    # csi300_erp — 动态
    # aa_credit_spread — 动态: cn_10y_yield + 0.65
    # global_pmi — Phase 6 代理合成 (US ISM + CN NBS + Euro PMI)
    # fiscal_deficit — 年度参数，akshare 可获取财政收入
    # special_bond — akshare bond_local_government_issue_cninfo
}
# ── FRED API 调用封装（超时 + 令牌桶限速 + 429 重试） ──
_MAX_FRED_RETRIES = 2
def _call_fred(fn: Callable[[], Any], label: str = "") -> Any:
    """一次 FRED API 调用：先申请令牌（必要时等待），再超时执行，遇到 429 自动重试。"""
    for attempt in range(_MAX_FRED_RETRIES + 1):
        # 1. 令牌桶限速 — 若桶空则阻塞等待
        wait = _fred_limiter.acquire()
        if wait > 0:
            actual_wait = min(wait, 5.0)
            print(f"  [fred limiter] 等待 {actual_wait:.1f}s (桶空, 速率={_fred_limiter.stats['refill_rate']} tok/s)", flush=True)
            time.sleep(actual_wait)
        # 2. 执行调用（带超时）
        try:
            return _call_with_timeout(fn, FRED_TIMEOUT, label)
        except FutureTimeoutError:
            raise
        except Exception as e:
            err_msg = str(e).lower()
            # FRED 429 限流 → 标记惩罚 + 重试
            if "too many requests" in err_msg or "429" in err_msg or "exceeded rate" in err_msg:
                penalty_wait = _fred_limiter.report_429()
                if attempt < _MAX_FRED_RETRIES:
                    logger.warning(f"[FRED] 429 rate limited ({label}), 重试 {attempt+2}/{_MAX_FRED_RETRIES+1}, 等待 {penalty_wait:.1f}s")
                    time.sleep(penalty_wait)
                    continue
            raise
    raise RuntimeError(f"FRED {label} failed after {_MAX_FRED_RETRIES+1} attempts")
class MacroDataSource:
    """宏观数据统一采集器"""
    def __init__(self, fred_api_key: Optional[str] = None):
        self.name = "宏观数据源"
        self._fred: Optional[Any] = None
        self._fred_ok = False
        self._ak_ok = HAS_AKSHARE and pd is not None
        if HAS_FREDAPI and Fred is not None:
            try:
                key = fred_api_key or _FRED_API_KEY
                self._fred = Fred(api_key=key)
                self._fred_ok = True
                logger.info(f"[{self.name}] FRED API 初始化成功")
            except Exception as e:
                logger.warning(f"[{self.name}] FRED API 初始化失败: {e}")
        else:
            logger.warning(f"[{self.name}] fredapi 未安装，FRED 数据不可用")
        if self._ak_ok:
            logger.info(f"[{self.name}] akshare 可用")
        else:
            logger.warning(f"[{self.name}] akshare 不可用")
    # ═══════════════════════════════════════════════════════════
    # 主入口
    # ═══════════════════════════════════════════════════════════
    def fetch_macro_data(self, target_date: Optional[str] = None) -> Dict[str, Any]:
        """
        获取所有宏观原始输入数据。
        Args:
            target_date: 目标日期 (YYYY-MM-DD)，默认今天。
                         用于 FRED 历史数据截断和 akshare 日期过滤。
        Returns:
            {
                "status": "success" | "partial" | "error",
                "fetch_time": str,
                "fields": { field_name: { "value": ..., "source": "...", ... } },
                "missing_fields": [...],
                "fallback_fields": [...],
            }
        """
        if target_date is None:
            target_date = datetime.now().strftime("%Y-%m-%d")
        self._target_date = target_date  # 保存以便各阶段使用
        global _TARGET_DATE
        _TARGET_DATE = target_date  # 供所有 akshare 取数函数读取，用于历史日期截断
        logger.info(f"[{self.name}] 开始采集宏观数据 (target={target_date})")
        print(f"[macro_data] Phase 0: start {target_date}", flush=True)
        fields: Dict[str, Dict[str, Any]] = {}
        missing: List[str] = []
        fallback_fields: List[str] = []
        # ── Phase 1: FRED 美国数据 ──
        print(f"[macro_data] Phase 1: FRED US...", flush=True)
        if self._fred_ok:
            self._fetch_fred_data(fields, missing, fallback_fields, target_date)
        else:
            for key in FRED_SERIES_MAP:
                self._apply_fallback(key, fields, missing, fallback_fields)
        print(f"[macro_data] Phase 1: done ({len(fields)} fields)", flush=True)
        # ── Phase 1.5: akshare 美国数据 (ISM PMI 等不在 FRED 的数据) ──
        print(f"[macro_data] Phase 1.5: akshare US...", flush=True)
        if self._ak_ok:
            self._fetch_akshare_us(fields, missing, fallback_fields)
        print(f"[macro_data] Phase 1.5: done", flush=True)
        # ── Phase 2: akshare 中国数据 ──
        print(f"[macro_data] Phase 2: akshare CN...", flush=True)
        if self._ak_ok:
            self._fetch_akshare_cn(fields, missing, fallback_fields)
        print(f"[macro_data] Phase 2: done ({len(fields)} fields)", flush=True)
        # ── Phase 3: 市场行情数据 (akshare / yfinance) ──
        print(f"[macro_data] Phase 3: market data...", flush=True)
        self._fetch_market_data(fields, missing, fallback_fields)
        print(f"[macro_data] Phase 3: done ({len(fields)} fields)", flush=True)
        # ── Phase 4: 商品数据 ──
        print(f"[macro_data] Phase 4: commodities...", flush=True)
        if self._ak_ok:
            self._fetch_commodity_data(fields, missing, fallback_fields)
        print(f"[macro_data] Phase 4: done ({len(fields)} fields)", flush=True)
        # ── Phase 4.5: 补充数据源 (PBOC中间价、期权限、期货等) ──
        print(f"[macro_data] Phase 4.5: supplementary...", flush=True)
        if self._ak_ok:
            self._fetch_supplementary_data(fields, missing, fallback_fields)
        print(f"[macro_data] Phase 4.5: done ({len(fields)} fields)", flush=True)
        # ── Phase 5: 剩余无法获取的字段 fallback ──
        print(f"[macro_data] Phase 5: fallbacks...", flush=True)
        self._fill_remaining_fallbacks(fields, missing, fallback_fields)
        print(f"[macro_data] Phase 5: done", flush=True)
        # ── Phase 6: 二次计算衍生指标 ──
        print(f"[macro_data] Phase 6: derived...", flush=True)
        self._compute_derived(fields)
        print(f"[macro_data] Phase 6: done", flush=True)
        status = "success"
        if fallback_fields:
            status = "partial"
        if missing:
            status = "partial"
        logger.info(
            f"[{self.name}] 采集完成: {len(fields)} 字段, "
            f"{len(fallback_fields)} fallback, {len(missing)} 缺失"
        )
        # 输出限速器统计
        stats = _fred_limiter.stats
        print(f"[macro_data] FRED limiter: {stats['total_requests']} requests, "
              f"waited {stats['total_waited_seconds']:.1f}s, "
              f"429 retries={stats['total_429_retries']}, "
              f"tokens left={stats['tokens_available']:.1f}", flush=True)
        return {
            "status": status,
            "fetch_time": datetime.now().isoformat(),
            "fields": fields,
            "missing_fields": missing,
            "fallback_fields": fallback_fields,
        }
    # ═══════════════════════════════════════════════════════════
    # Phase 1: FRED 美国数据
    # ═══════════════════════════════════════════════════════════
    def _fetch_fred_data(
        self,
        fields: Dict[str, Dict[str, Any]],
        missing: List[str],
        fallback_fields: List[str],
        target_date: Optional[str] = None,
    ):
        """从 FRED 批量获取美国宏观数据。若提供 target_date，按 observation_end 截断。"""
        fred = self._fred
        if fred is None:
            return
        # ── 直接取值型 ──
        fred_count = len(FRED_SERIES_MAP)
        for i, (field, series_id) in enumerate(FRED_SERIES_MAP.items()):
            if i % 2 == 0:
                print(f"  [fred] {i+1}/{fred_count}...", flush=True)
            try:
                if target_date:
                    series = _call_fred(
                        lambda sid=series_id, td=target_date: fred.get_series(sid, observation_end=td),
                        f"FRED.{series_id}")
                else:
                    series = _call_fred(
                        lambda sid=series_id: fred.get_series(sid),
                        f"FRED.{series_id}")
                if series.empty:
                    self._apply_fallback(field, fields, missing, fallback_fields)
                    continue
                latest = float(series.iloc[-1])
                if not np.isfinite(latest):
                    self._apply_fallback(field, fields, missing, fallback_fields)
                    continue
                # 根据不同字段做不同处理
                if field == "nonfarm_payrolls":
                    # PAYEMS 是总量，需要取 MoM 变化
                    if len(series) >= 2:
                        prev = float(series.iloc[-2])
                        value = round(latest - prev, 0)
                    else:
                        value = latest
                elif field in ("gdp", "retail_sales", "personal_consumption",
                               "industrial_production", "core_pce", "cpi",
                               "core_cpi", "us_m2"):
                    # 需算 YoY — 存原始值，后续统一计算
                    value = round(latest, 4)
                elif field == "eci_wage":
                    # 季频，算 QoQ
                    if len(series) >= 2:
                        prev = float(series.iloc[-2])
                        qoq = (latest - prev) / prev * 100 if prev != 0 else 0.0
                        value = round(qoq, 2)
                    else:
                        value = round(float(series.iloc[-1]), 2)
                elif field in ("us_10y_yield", "us_2y_yield", "us_ig_spread",
                               "us_hy_spread", "sofr", "effr", "ffr",
                               "dxy_broad"):
                    value = round(latest, 2)
                elif field in ("us_unemployment_rate", "tips_10y_breakeven",
                               "breakeven_5y5y", "initial_jobless_claims_4w",
                               "housing_starts", "existing_home_sales"):
                    value = round(latest, 4)
                else:
                    value = round(latest, 4)
                fields[field] = {
                    "value": value,
                    "source": "fred",
                    "series_id": series_id,
                    "latest_date": str(series.index[-1].date()),
                }
            except Exception as e:
                logger.warning(f"[{self.name}] FRED {field} ({series_id}) 获取失败: {e}")
                self._apply_fallback(field, fields, missing, fallback_fields)
        # ── 计算 YoY (处理存了原始值的字段) ──
        yoy_fields = {
            "gdp": "gdp_yoy",
            "retail_sales": "retail_sales_yoy",
            "personal_consumption": "personal_consumption_yoy",
            "industrial_production": "industrial_production_yoy",
            "core_pce": "core_pce_yoy",
            "cpi": "cpi_yoy",
            "core_cpi": "core_cpi_yoy",
            "us_m2": "us_m2_yoy",
        }
        for raw_field, yoy_field in yoy_fields.items():
            series_id = FRED_SERIES_MAP.get(raw_field)
            if not series_id:
                continue
            try:
                if target_date:
                    series = _call_fred(
                        lambda sid=series_id, td=target_date: fred.get_series(sid, observation_end=td),
                        f"FRED.{series_id}(YoY)")
                else:
                    series = _call_fred(
                        lambda sid=series_id: fred.get_series(sid),
                        f"FRED.{series_id}(YoY)")
                if len(series) >= 13:  # 至少 13 个月数据才能算 YoY
                    current = float(series.iloc[-1])
                    year_ago = float(series.iloc[-13])
                    if year_ago != 0:
                        yoy = round((current - year_ago) / year_ago * 100, 2)
                    else:
                        yoy = 0.0
                else:
                    yoy = 0.0
                fields[yoy_field] = {
                    "value": yoy,
                    "source": "fred_computed",
                    "series_id": series_id,
                    "computation": "YoY%",
                }
            except Exception as e:
                logger.warning(f"[{self.name}] {yoy_field} YoY 计算失败: {e}")
                self._apply_fallback(yoy_field, fields, missing, fallback_fields)
        # ── 特殊处理: fed_total_assets (周频) ──
        try:
            if target_date:
                walcl = _call_fred(
                    lambda td=target_date: fred.get_series("WALCL", observation_end=td),
                    "FRED.WALCL")
            else:
                walcl = _call_fred(
                    lambda: fred.get_series("WALCL"),
                    "FRED.WALCL")
            if not walcl.empty:
                fields["fed_total_assets"] = {
                    "value": round(float(walcl.iloc[-1]) / 1e6, 2),  # 百万→万亿
                    "source": "fred",
                    "series_id": "WALCL",
                    "unit": "trillion_usd",
                    "latest_date": str(walcl.index[-1].date()),
                }
        except Exception:
            self._apply_fallback("fed_total_assets", fields, missing, fallback_fields)
    # ═══════════════════════════════════════════════════════════
    # Phase 1.5: akshare 美国数据 (FRED 不覆盖的指标)
    # ═══════════════════════════════════════════════════════════
    def _fetch_akshare_us(
        self,
        fields: Dict[str, Dict[str, Any]],
        missing: List[str],
        fallback_fields: List[str],
    ):
        """通过 akshare 获取 FRED 不覆盖的美国 / 全球宏观数据"""
        # ISM 制造业 PMI
        self._try_akshare(
            "ism_manufacturing_pmi", fields, missing, fallback_fields,
            lambda: _fetch_ism_pmi()
        )
        # ISM 非制造业 (服务业) PMI
        self._try_akshare(
            "ism_services_pmi", fields, missing, fallback_fields,
            lambda: _fetch_ism_non_pmi()
        )
        # 欧元区制造业 PMI
        self._try_akshare(
            "euro_pmi", fields, missing, fallback_fields,
            lambda: _fetch_euro_pmi()
        )
        # CFTC 美元净头寸
        self._try_akshare(
            "cftc_net_position_pct", fields, missing, fallback_fields,
            lambda: _fetch_cftc_dollar_net()
        )
    # ═══════════════════════════════════════════════════════════
    # Phase 2: akshare 中国数据
    # ═══════════════════════════════════════════════════════════
    def _fetch_akshare_cn(
        self,
        fields: Dict[str, Dict[str, Any]],
        missing: List[str],
        fallback_fields: List[str],
    ):
        """通过 akshare 获取中国宏观数据"""
        # ── PMI ──
        self._try_akshare(
            "nbs_manufacturing_pmi", fields, missing, fallback_fields,
            lambda: _fetch_pmi_official()
        )
        self._try_akshare(
            "caixin_manufacturing_pmi", fields, missing, fallback_fields,
            lambda: _fetch_caixin_pmi()
        )
        self._try_akshare(
            "non_manufacturing_pmi", fields, missing, fallback_fields,
            lambda: _fetch_non_mfg_pmi()
        )
        # ── 增长 ──
        self._try_akshare(
            "industrial_production_yoy_cn", fields, missing, fallback_fields,
            lambda: _fetch_cn_indicator("industrial_production")
        )
        self._try_akshare(
            "fixed_asset_investment_yoy", fields, missing, fallback_fields,
            lambda: _fetch_cn_indicator("fixed_asset_investment")
        )
        self._try_akshare(
            "retail_sales_yoy_cn", fields, missing, fallback_fields,
            lambda: _fetch_cn_indicator("retail_sales")
        )
        self._try_akshare(
            "exports_yoy_cn", fields, missing, fallback_fields,
            lambda: _fetch_cn_indicator("exports")
        )
        # ── 信用 ──
        self._try_akshare(
            "social_financing_yoy", fields, missing, fallback_fields,
            lambda: _fetch_cn_indicator("social_financing")
        )
        self._try_akshare(
            "social_financing_new", fields, missing, fallback_fields,
            lambda: _fetch_social_financing_new()
        )
        self._try_akshare(
            "corporate_loan_yoy", fields, missing, fallback_fields,
            lambda: _fetch_corporate_loan_yoy()
        )
        self._try_akshare(
            "m1_yoy_cn", fields, missing, fallback_fields,
            lambda: _fetch_cn_money_supply("m1")
        )
        self._try_akshare(
            "m2_yoy_cn", fields, missing, fallback_fields,
            lambda: _fetch_cn_money_supply("m2")
        )
        # ── 通胀 ──
        self._try_akshare(
            "cpi_yoy_cn", fields, missing, fallback_fields,
            lambda: _fetch_cn_cpi()
        )
        self._try_akshare(
            "ppi_yoy_cn", fields, missing, fallback_fields,
            lambda: _fetch_cn_ppi()
        )
        # ── 政策利率 ──
        self._try_akshare(
            "lpr_1y", fields, missing, fallback_fields,
            lambda: _fetch_lpr("1Y")
        )
        self._try_akshare(
            "lpr_5y", fields, missing, fallback_fields,
            lambda: _fetch_lpr("5Y")
        )
        self._try_akshare(
            "mlf_rate", fields, missing, fallback_fields,
            lambda: _fetch_mlf_rate()
        )
        self._try_akshare(
            "reserve_ratio", fields, missing, fallback_fields,
            lambda: _fetch_reserve_ratio()
        )
        self._try_akshare(
            "cn_10y_yield", fields, missing, fallback_fields,
            lambda: _fetch_cn_bond_yield("10Y")
        )
        self._try_akshare(
            "cn_1y_yield", fields, missing, fallback_fields,
            lambda: _fetch_cn_bond_yield("1Y")
        )
        self._try_akshare(
            "cn_3y_yield", fields, missing, fallback_fields,
            lambda: _fetch_cn_bond_yield("3Y")
        )
        # ── 流动性 ──
        self._try_akshare(
            "shibor_3m", fields, missing, fallback_fields,
            lambda: _fetch_shibor()
        )
        self._try_akshare(
            "dr007", fields, missing, fallback_fields,
            lambda: _fetch_dr007()
        )
        self._try_akshare(
            "r007", fields, missing, fallback_fields,
            lambda: _fetch_r007()
        )
        # ── 地产 ──
        self._try_akshare(
            "property_sales_area_yoy", fields, missing, fallback_fields,
            lambda: _fetch_cn_indicator("property_sales")
        )
        self._try_akshare(
            "property_investment_yoy", fields, missing, fallback_fields,
            lambda: _fetch_cn_indicator("property_investment")
        )
        # ── 其他 ──
        self._try_akshare(
            "ccfi_index", fields, missing, fallback_fields,
            lambda: _fetch_ccfi()
        )
        self._try_akshare(
            "auto_sales_yoy", fields, missing, fallback_fields,
            lambda: _fetch_cn_indicator("auto_sales")
        )
        self._try_akshare(
            "foreign_reserves", fields, missing, fallback_fields,
            lambda: _fetch_foreign_reserves()
        )
        self._try_akshare(
            "trade_surplus_cn", fields, missing, fallback_fields,
            lambda: _fetch_trade_surplus()
        )
        # ── 财政数据 ──
        self._try_akshare(
            "fiscal_deficit", fields, missing, fallback_fields,
            lambda: _fetch_fiscal_revenue()
        )
        self._try_akshare(
            "special_bond", fields, missing, fallback_fields,
            lambda: _fetch_special_bond_progress()
        )
        # ── 公开市场操作 ──
        self._try_akshare(
            "omo_net_injection", fields, missing, fallback_fields,
            lambda: _fetch_omo_net_injection()
        )
        # ── 债市 ──
        self._try_akshare(
            "cn_aa_3y_yield", fields, missing, fallback_fields,
            lambda: _fetch_aa_bond_yield("3Y")
        )
        self._try_akshare(
            "cn_cdic_3y_yield", fields, missing, fallback_fields,
            lambda: _fetch_cdic_bond_yield("3Y")
        )
    # ═══════════════════════════════════════════════════════════
    # Phase 3: 市场行情
    # ═══════════════════════════════════════════════════════════
    def _fetch_market_data(
        self,
        fields: Dict[str, Dict[str, Any]],
        missing: List[str],
        fallback_fields: List[str],
    ):
        """获取股票指数、VIX 等行情数据"""
        # S&P 500
        self._try_akshare(
            "sp500_index", fields, missing, fallback_fields,
            lambda: _fetch_global_index("sp500")
        )
        # CSI 300
        self._try_akshare(
            "csi300_index", fields, missing, fallback_fields,
            lambda: _fetch_csi300()
        )
        # VIX
        self._try_akshare(
            "vix", fields, missing, fallback_fields,
            lambda: _fetch_vix()
        )
        # 北向资金
        self._try_akshare(
            "north_flow", fields, missing, fallback_fields,
            lambda: _fetch_north_flow()
        )
        # 融资余额
        self._try_akshare(
            "margin_balance", fields, missing, fallback_fields,
            lambda: _fetch_margin_balance()
        )
        # 美元指数 (DXY, narrow)
        self._try_akshare(
            "dxy", fields, missing, fallback_fields,
            lambda: _fetch_global_index("dxy")
        )
        # USD/CNH 离岸人民币
        self._try_akshare(
            "usd_cnh", fields, missing, fallback_fields,
            lambda: _fetch_usd_cnh()
        )
        # CSI300 PE/PB 估值
        self._try_akshare(
            "csi300_pe", fields, missing, fallback_fields,
            lambda: _fetch_csi300_pe()
        )
        self._try_akshare(
            "csi300_pb", fields, missing, fallback_fields,
            lambda: _fetch_csi300_pb()
        )
        # CSI300 股指期货主力连续
        self._try_akshare(
            "csi300_futures_price", fields, missing, fallback_fields,
            lambda: _fetch_csi300_futures()
        )
        # HSI 恒生指数 (for AH spread)
        self._try_akshare(
            "hsi_index", fields, missing, fallback_fields,
            lambda: _fetch_global_index("hsi")
        )
    # ═══════════════════════════════════════════════════════════
    # Phase 4: 商品数据
    # ═══════════════════════════════════════════════════════════
    def _fetch_commodity_data(
        self,
        fields: Dict[str, Dict[str, Any]],
        missing: List[str],
        fallback_fields: List[str],
    ):
        """获取大宗商品价格"""
        commodities = [
            ("copper_price",    "LME铜",    "futures_lme"),
            ("gold_price",      "COMEX金",  "futures_comex"),
            ("wti_price",       "WTI原油",  "futures_nymex"),
            ("brent_price",     "布伦特油", "futures_ice"),
            ("iron_ore_price",  "DCE铁矿",  "futures_dce"),
            ("soybean_price",   "CBOT大豆", "futures_cbot"),
            ("corn_price",      "CBOT玉米", "futures_cbot"),
        ]
        for field, name, source_key in commodities:
            self._try_akshare(
                field, fields, missing, fallback_fields,
                lambda f=field, n=name: _fetch_commodity(f, n),
            )
        # 南华工业品指数
        self._try_akshare(
            "nh_industrial_index", fields, missing, fallback_fields,
            lambda: _fetch_nh_industrial()
        )
    # ═══════════════════════════════════════════════════════════
    # Phase 4.5: 补充数据源
    # ═══════════════════════════════════════════════════════════
    def _fetch_supplementary_data(
        self,
        fields: Dict[str, Dict[str, Any]],
        missing: List[str],
        fallback_fields: List[str],
    ):
        """获取补充数据：PBOC中间价、期权、期货持仓等"""
        # PBOC 中间价偏离度
        self._try_akshare(
            "pboc_midpoint", fields, missing, fallback_fields,
            lambda: _fetch_pboc_midpoint()
        )
        # CNH-CNY 价差原始数据
        self._try_akshare(
            "cny_spot", fields, missing, fallback_fields,
            lambda: _fetch_cny_spot()
        )
        # FF 隐含利率 (CME FedWatch)
        self._try_akshare(
            "ff_futures_implied_rate", fields, missing, fallback_fields,
            lambda: _fetch_ff_implied_from_cme()
        )
        # ETF 资金流
        self._try_akshare(
            "etf_flow_cny_bn", fields, missing, fallback_fields,
            lambda: _fetch_etf_flow_cn()
        )
        # 国债期货持仓变化
        try:
            result = _call_with_timeout(_fetch_cffex_bond_futures, AKSHARE_TIMEOUT, "cffex_bond_futures")
            if result:
                for k, v in result.items():
                    if v is not None:
                        fields[k] = {"value": v, "source": "akshare_cffex"}
        except Exception as e:
            logger.debug("[macro_data] fetch failed: {}".format(e))
        # 期权 P/C ratio
        try:
            result = _call_with_timeout(_fetch_csi300_option_data, AKSHARE_TIMEOUT, "csi300_option")
            if result:
                for k, v in result.items():
                    if v is not None:
                        fields[k] = {"value": v, "source": "akshare_option"}
        except Exception as e:
            logger.debug("[macro_data] fetch failed: {}".format(e))
    # ═══════════════════════════════════════════════════════════
    # Phase 5: 剩余 fallback
    # ═══════════════════════════════════════════════════════════
    def _fill_remaining_fallbacks(
        self,
        fields: Dict[str, Dict[str, Any]],
        missing: List[str],
        fallback_fields: List[str],
    ):
        """为尚未获取到的必填/可选字段填 fallback
        注意: global_pmi 由 Phase 6 _compute_derived 代理合成, 不在此处 fallback
        """
        all_expected = set(_FALLBACK_VALUES.keys()) | {
            "credit_pulse", "overseas_flow_us", "ff_futures_implied_rate",
            "sell_side_bearish_pct",
            "buy_side_bearish_pct", "etf_flow_cny_bn",
            "china_surprise_index", "us_surprise_index",
            "fiscal_deficit", "special_bond",
            "usd_cnh_1y_forward",
            "rmb_reer",
            # 新增: 不在 _FALLBACK_VALUES 中但需兜底的字段
            "omo_net_injection", "csi300_pe", "csi300_pb",
            "cn_3y_yield", "cn_aa_3y_yield", "cn_cdic_3y_yield",
            "csi300_futures_price", "hsi_index",
            "wti_price", "soybean_price", "corn_price",
        }
        for field in all_expected:
            if field in fields:
                continue
            self._apply_fallback(field, fields, missing, fallback_fields)
    # ═══════════════════════════════════════════════════════════
    # Phase 6: 二次计算
    # ═══════════════════════════════════════════════════════════
    def _compute_derived(self, fields: Dict[str, Dict[str, Any]]) -> None:
        """从已有原始数据计算衍生指标"""
        data = self._as_value_dict(fields)
        # 中美 10Y 利差
        us_10y = data.get("us_10y_yield")
        cn_10y = data.get("cn_10y_yield")
        if us_10y is not None and cn_10y is not None:
            fields["cn_us_10y_spread"] = {
                "value": round(cn_10y - us_10y, 4),
                "source": "computed",
                "computation": "cn_10y_yield - us_10y_yield",
            }
        # S&P 500 ERP ≈ 1/PE(TTM) - 10Y
        sp500 = data.get("sp500_index")
        if us_10y is not None:
            # 优先用实际 PE 数据，否则用近似值
            sp500_pe = data.get("sp500_pe")
            if sp500_pe and sp500_pe > 0:
                ey = round(100.0 / sp500_pe, 2)
                estimated_erp = round(ey - us_10y, 2)
                comp_note = f"100/PE({sp500_pe}) - us_10y"
            else:
                estimated_erp = round(5.0 - us_10y, 2)  # 1/20 = 5%
                comp_note = "5.0% - us_10y_yield (PE≈20 近似)"
            fields["sp500_erp"] = {
                "value": estimated_erp,
                "source": "computed_approx",
                "computation": comp_note,
            }
        # CSI300 ERP ≈ 1/PE(TTM) - 10Y 国债
        csi300_pe = data.get("csi300_pe")
        if cn_10y is not None:
            if csi300_pe and csi300_pe > 0:
                ey = round(100.0 / csi300_pe, 2)
                estimated_cn_erp = round(ey - cn_10y, 2)
                comp_note = f"100/PE({csi300_pe}) - cn_10y"
            else:
                estimated_cn_erp = round(8.0 - cn_10y, 2)  # 1/12.5 ≈ 8%
                comp_note = "8.0% - cn_10y_yield (PE≈12.5 近似)"
            fields["csi300_erp"] = {
                "value": estimated_cn_erp,
                "source": "computed_approx",
                "computation": comp_note,
            }
        # AA 信用利差 — 优先用真实 AA 债收益率，否则 cn_10y + 0.65
        aa_3y = data.get("cn_aa_3y_yield")
        if aa_3y is not None and cn_10y is not None:
            fields["aa_credit_spread"] = {
                "value": round(aa_3y - cn_10y, 2),
                "source": "computed",
                "computation": "cn_aa_3y_yield - cn_10y_yield",
            }
        elif cn_10y is not None:
            fields["aa_credit_spread"] = {
                "value": round(cn_10y + 0.65, 2),
                "source": "computed_approx",
                "computation": "cn_10y_yield + 0.65%",
            }
        # 城投-国开债利差
        cdic_3y = data.get("cn_cdic_3y_yield")
        cn_3y = data.get("cn_3y_yield")
        if cdic_3y is not None and cn_3y is not None:
            fields["city_invest_spread"] = {
                "value": round(cdic_3y - cn_3y, 2),
                "source": "computed",
                "computation": "cn_cdic_3y_yield - cn_3y_yield",
            }
        elif cn_3y is not None:
            # fallback: 典型利差约 80bp
            fields["city_invest_spread"] = {
                "value": round(cn_3y + 0.80, 2),
                "source": "computed_approx",
                "computation": "cn_3y_yield + 0.80% (典型利差近似)",
            }
        # 铜金比
        copper = data.get("copper_price")
        gold = data.get("gold_price")
        if copper and gold and gold != 0:
            fields["copper_gold_ratio"] = {
                "value": round(copper / gold, 4),
                "source": "computed",
                "computation": "copper_price / gold_price",
            }
        # 油金比 (WTI优先)
        wti = data.get("wti_price")
        brent = data.get("brent_price")
        oil = wti if wti else brent
        if oil and gold and gold != 0:
            fields["oil_gold_ratio"] = {
                "value": round(oil / gold, 4),
                "source": "computed",
                "computation": f"oil_price / gold_price",
            }
        # 大豆玉米比
        soybean = data.get("soybean_price")
        corn = data.get("corn_price")
        if soybean and corn and corn != 0:
            fields["soybean_corn_ratio"] = {
                "value": round(soybean / corn, 4),
                "source": "computed",
                "computation": "soybean_price / corn_price",
            }
        # 铁矿石美元价 (CNY价 / 汇率)
        iron_ore_cny = data.get("iron_ore_price")
        usd_cnh = data.get("usd_cnh")
        if iron_ore_cny and usd_cnh and usd_cnh != 0:
            fields["iron_ore_usd"] = {
                "value": round(iron_ore_cny / usd_cnh, 2),
                "source": "computed",
                "computation": f"iron_ore_price / usd_cnh",
            }
        # AH 价差 (H股折价率)
        csi300 = data.get("csi300_index")
        hsi = data.get("hsi_index")
        if csi300 and hsi and hsi != 0:
            # AH溢价指数 ≈ CSI300 / (HSI * usd_cnh / 7.8) * 100
            rate = usd_cnh if usd_cnh else 7.2
            ah_spread = round(csi300 / (hsi * rate / 7.8), 2)
            fields["hshare_ah_spread"] = {
                "value": ah_spread,
                "source": "computed",
                "computation": f"csi300 / (hsi * {rate} / 7.8)",
            }
        # CRB 代理指数 (等权大宗篮子)
        commodity_prices = {
            "wti_price": wti,
            "brent_price": brent,
            "copper_price": copper,
            "gold_price": gold,
            "soybean_price": soybean,
            "corn_price": corn,
        }
        valid_prices = {k: v for k, v in commodity_prices.items() if v and v > 0}
        if len(valid_prices) >= 3:
            # 等权平均后归一化到 100 基准
            avg = sum(valid_prices.values()) / len(valid_prices)
            # 简单基准归一化: 铜~9000, 油~80, 金~2400
            # 使用各品种历史中枢归一化
            norms = {
                "wti_price": 80.0, "brent_price": 85.0, "copper_price": 9000.0,
                "gold_price": 2000.0, "soybean_price": 1200.0, "corn_price": 500.0,
            }
            normalized_sum = 0.0
            count = 0
            for k, v in valid_prices.items():
                norm = norms.get(k, 100.0)
                if norm > 0:
                    normalized_sum += v / norm * 100.0
                    count += 1
            if count > 0:
                fields["crb_proxy_index"] = {
                    "value": round(normalized_sum / count, 2),
                    "source": "computed",
                    "computation": f"等权大宗篮子归一化 (n={count})",
                }
        # 全球制造业 PMI 代理合成
        if "global_pmi" not in fields:
            us_ism = data.get("ism_manufacturing_pmi")
            cn_nbs = data.get("nbs_manufacturing_pmi")
            euro = data.get("euro_pmi") or 50.0
            if us_ism is not None and cn_nbs is not None:
                proxy_pmi = round(
                    us_ism * 0.30 + cn_nbs * 0.30 + euro * 0.20 + 50.0 * 0.20, 2
                )
                fields["global_pmi"] = {
                    "value": proxy_pmi,
                    "source": "computed_proxy",
                    "computation": (
                        f"US_ISM({us_ism})*0.30 + CN_NBS({cn_nbs})*0.30 "
                        f"+ Euro({euro})*0.20 + RoW(50)*0.20"
                    )
                }
        # 期限利差
        us_2y = data.get("us_2y_yield")
        if us_10y is not None and us_2y is not None:
            fields["us_term_spread_10y2y"] = {
                "value": round(us_10y - us_2y, 4),
                "source": "computed",
                "computation": "us_10y - us_2y",
            }
        cn_1y = data.get("cn_1y_yield")
        if cn_10y is not None and cn_1y is not None:
            fields["cn_term_spread_10y1y"] = {
                "value": round(cn_10y - cn_1y, 4),
                "source": "computed",
                "computation": "cn_10y - cn_1y",
            }
        # 南华工业品指数 YoY (当历史数据可用时)
        nh = data.get("nh_industrial_index")
        if nh is not None:
            # 简单占位: 若无历史对比数据，yoy 无法计算
            # 若 fields 中已有 nh_industrial_index_yoy 则保留
            if "nh_industrial_index_yoy" not in fields:
                fields["nh_industrial_index_yoy"] = {
                    "value": 0.0,
                    "source": "computed_placeholder",
                    "computation": "需历史数据对比，当前占位 0.0",
                }
        # 新订单-库存剪刀差 (从 PMI 提子指数，若不可得则默认)
        if "new_order_inventory_spread" not in fields:
            fields["new_order_inventory_spread"] = {
                "value": 3.5,
                "source": "computed_default",
                "computation": "PMI 新订单-产成品库存 (默认3.5)",
            }
        # CSI300 股指期货基差
        futures_price = data.get("csi300_futures_price")
        if futures_price and csi300 and csi300 > 0:
            basis = round((futures_price - csi300) / csi300 * 100, 2)
            fields["csi300_futures_basis"] = {
                "value": basis,
                "source": "computed",
                "computation": f"(futures({futures_price}) - spot({csi300})) / spot * 100",
            }
            # 期货价格作为 csi300_forward
            if "csi300_forward" not in fields:
                fields["csi300_forward"] = {
                    "value": futures_price,
                    "source": "akshare_cffex",
                    "computation": "CSI300 股指期货主力连续合约价格",
                }
        # pboc_mid_deviation: 优先用真实 PBOC 中间价
        usd_cnh_val = data.get("usd_cnh")
        pboc_mid = data.get("pboc_midpoint")
        if pboc_mid and usd_cnh_val and pboc_mid > 0:
            deviation = round((usd_cnh_val - pboc_mid) / pboc_mid * 100, 2)
            fields["pboc_mid_deviation"] = {
                "value": deviation,
                "source": "computed",
                "computation": f"(USDCNH({usd_cnh_val}) - PBOC_mid({pboc_mid})) / PBOC_mid",
            }
        elif usd_cnh_val is not None:
            dxy_val = data.get("dxy_index")
            if dxy_val and dxy_val > 0 and "pboc_mid_deviation" not in fields:
                mid_est = round(dxy_val * 0.07, 2)
                deviation = round((usd_cnh_val - mid_est) / mid_est * 100, 2)
                fields["pboc_mid_deviation"] = {
                    "value": deviation,
                    "source": "computed_approx",
                    "computation": f"(usd_cnh({usd_cnh_val}) - mid_est({mid_est})) / mid_est",
                }
        # cnh_cny_spread: 优先用真实 CNY 即期
        cny_spot = data.get("cny_spot")
        if cny_spot and usd_cnh_val and cny_spot > 0:
            spread = round(usd_cnh_val - cny_spot, 4)
            fields["cnh_cny_spread"] = {
                "value": spread,
                "source": "computed",
                "computation": f"USDCNH({usd_cnh_val}) - USDCNY({cny_spot})",
            }
        elif usd_cnh_val and "cnh_cny_spread" not in fields:
            cny_est = usd_cnh_val - 0.02
            fields["cnh_cny_spread"] = {
                "value": round(usd_cnh_val - cny_est, 4),
                "source": "computed_approx",
                "computation": f"USDCNH({usd_cnh_val}) - USDCNY_est({round(cny_est,4)})",
            }
    # ═══════════════════════════════════════════════════════════
    # 工具方法
    # ═══════════════════════════════════════════════════════════
    def _try_akshare(
        self,
        field: str,
        fields: Dict[str, Dict[str, Any]],
        missing: List[str],
        fallback_fields: List[str],
        fetcher,
    ):
        """安全执行 akshare 取数，失败时 fallback。所有调用均受超时保护。"""
        try:
            result = _call_with_timeout(fetcher, AKSHARE_TIMEOUT, f"ak.{field}")
            if result is not None:
                fields[field] = {
                    "value": result,
                    "source": "akshare",
                }
                return
        except Exception as e:
            logger.debug(f"[{self.name}] akshare {field} 失败: {e}")
        self._apply_fallback(field, fields, missing, fallback_fields)
    def _apply_fallback(
        self,
        field: str,
        fields: Dict[str, Dict[str, Any]],
        missing: List[str],
        fallback_fields: List[str],
    ):
        """应用 fallback 值"""
        val = self._get_fallback(field, fields)
        if val is None:
            missing.append(field)
            return
        fields[field] = {
            "value": val,
            "source": "fallback",
        }
        fallback_fields.append(field)
    def _get_fallback(
        self,
        field: str,
        fields: Dict[str, Dict[str, Any]],
    ):
        """获取字段的 fallback 值（支持动态计算）"""
        data = self._as_value_dict(fields)
        # 固定值
        if field in _FALLBACK_VALUES:
            val = _FALLBACK_VALUES[field]
            if val is not None:
                return val
        # 动态 fallback
        dynamic_fallbacks = {
            "ff_futures_implied_rate": lambda d: d.get("ffr", 5.33),
            "sp500_erp": lambda d: (
                round(5.0 - d["us_10y_yield"], 2)
                if d.get("us_10y_yield") else None
            ),
            "csi300_erp": lambda d: (
                round(8.0 - d["cn_10y_yield"], 2)
                if d.get("cn_10y_yield") else None
            ),
            "aa_credit_spread": lambda d: (
                round(d["cn_10y_yield"] + 0.65, 2)
                if d.get("cn_10y_yield") else None
            ),
            "etf_flow_cny_bn": lambda d: d.get("north_flow"),
        }
        if field in dynamic_fallbacks:
            try:
                result = dynamic_fallbacks[field](data)
                if result is not None:
                    return result
            except Exception as e:
                logger.debug("[macro_data] fetch failed: {}".format(e))
        # 最后兜底
        field_defaults = {
            "credit_pulse": 0.0,
            "overseas_flow_us": 0.0,
            "cftc_net_position_pct": 0.0,
            "sell_side_bearish_pct": 30.0,
            "buy_side_bearish_pct": 20.0,
            "euro_pmi": 50.0,
            "mlf_rate": 2.5,
            "r007": 1.5,
            "reserve_ratio": 0.0,
            "fiscal_deficit": -3.0,
            "special_bond": 0.0,
            "usd_cnh": 7.2,
            "usd_cnh_1y_forward": 0.0,
            "foreign_reserves": 3.2,
            "trade_surplus_cn": 50.0,
            "rmb_reer": 100.0,
            "corporate_loan_yoy": 10.0,
            "china_surprise_index": 0.0,
            "us_surprise_index": 0.0,
            "social_financing_new": 3000,
            # 新增 fallback
            "omo_net_injection": 0.0,
            "csi300_pe": 12.5,
            "csi300_pb": 1.4,
            "cn_3y_yield": 1.5,
            "cn_aa_3y_yield": 2.8,
            "cn_cdic_3y_yield": 2.5,
            "csi300_futures_price": 4000.0,
            "hsi_index": 22000.0,
            "wti_price": 80.0,
            "soybean_price": 1200.0,
            "corn_price": 500.0,
        }
        return field_defaults.get(field)
    def _as_value_dict(
        self, fields: Dict[str, Dict[str, Any]]
    ):
        """将 fields 转为 {name: value} 的简单 dict"""
        return {
            k: v["value"]
            for k, v in fields.items()
            if isinstance(v, dict) and "value" in v
        }
    # ═══════════════════════════════════════════════════════════
    # 便捷方法
    # ═══════════════════════════════════════════════════════════
    def get_single_field(self, field_name: str) -> Optional[float]:
        """获取单个字段的值"""
        result = self.fetch_macro_data()
        f = result.get("fields", {}).get(field_name, {})
        return f.get("value")
    def get_field_metadata(self, field_name: str) -> Optional[Dict[str, Any]]:
        """获取单个字段的完整元数据"""
        result = self.fetch_macro_data()
        return result.get("fields", {}).get(field_name)
    def get_all_fields(self) -> Dict[str, float]:
        """获取所有字段的值 (简版)"""
        result = self.fetch_macro_data()
        return self._as_value_dict(result.get("fields", {}))
# ═══════════════════════════════════════════════════════════
# 底层数据获取函数 (akshare)
# ═══════════════════════════════════════════════════════════
def _fetch_pmi_official() -> Optional[float]:
    """获取官方制造业 PMI — akshare: macro_china_pmi → 制造业-指数"""
    df = ak.macro_china_pmi()
    if df is not None and not df.empty:
        latest = _get_latest_by_date(df)
        for col in ["制造业-指数", "制造业PMI", "制造业"]:
            if col in df.columns:
                v = _safe_float(latest.get(col))
                if v is not None:
                    return v
        return _safe_float(latest.iloc[1]) if len(df.columns) > 1 else None
    return None
def _fetch_caixin_pmi() -> Optional[float]:
    """获取财新制造业 PMI — akshare: macro_china_cx_pmi_yearly"""
    try:
        df = ak.macro_china_cx_pmi_yearly()
        if df is not None and not df.empty:
            latest = _get_latest_by_date(df)
            for col in df.columns:
                if "PMI" in str(col) or "实际" in str(col) or "今值" in str(col):
                    v = _safe_float(latest.get(col))
                    if v is not None:
                        return v
            return _safe_float(latest.iloc[-1]) if len(df.columns) > 0 else None
    except Exception as e:
        logger.debug("[macro_data] fetch failed: {}".format(e))
    return None
def _fetch_non_mfg_pmi() -> Optional[float]:
    """获取非制造业 PMI"""
    df = ak.macro_china_pmi()
    if df is not None and not df.empty:
        latest = _get_latest_by_date(df)
        for col in ["非制造业-指数", "非制造业PMI", "非制造业商务活动指数"]:
            if col in df.columns:
                v = _safe_float(latest.get(col))
                if v is not None:
                    return v
    return None
def _fetch_cn_indicator(indicator: str) -> Optional[float]:
    """通用中国宏观指标获取 — 每指标独立调用 akshare 真实接口"""
    try:
        if indicator == "industrial_production":
            df = ak.macro_china_industrial_production_yoy()
            if df is not None and not df.empty:
                return _safe_float(_get_latest_by_date(df).iloc[-1]) if len(df.columns) > 0 else None
        elif indicator == "fixed_asset_investment":
            df = ak.macro_china_gdzctz()
            if df is not None and not df.empty:
                latest = _get_latest_by_date(df)
                # 框架定义: 固定资产投资累计同比 → 取 "同比增长" 列（非自年初累计）
                if "同比增长" in df.columns:
                    v = _safe_float(latest.get("同比增长"))
                    if v is not None:
                        return v
                return _safe_float(latest.iloc[-1]) if len(df.columns) > 0 else None
        elif indicator == "retail_sales":
            df = ak.macro_china_consumer_goods_retail()
            if df is not None and not df.empty:
                return _safe_float(_get_latest_by_date(df).iloc[-1]) if len(df.columns) > 0 else None
        elif indicator == "exports":
            df = ak.macro_china_trade_balance()
            if df is not None and not df.empty:
                for col in df.columns:
                    if "出口" in str(col):
                        v = _safe_float(_get_latest_by_date(df).get(col))
                        if v is not None:
                            return v
        elif indicator == "social_financing":
            df = ak.macro_china_shrzgm()
            if df is not None and not df.empty:
                latest = _get_latest_by_date(df)
                if "社会融资规模增量" in df.columns:
                    v = _safe_float(latest.get("社会融资规模增量"))
                    if v is not None:
                        return v
                return _safe_float(latest.iloc[-1]) if len(df.columns) > 0 else None
        # gdp: 优先 ak.macro_china_gdp_yearly
        elif indicator == "gdp":
            df = ak.macro_china_gdp_yearly()
            if df is not None and not df.empty:
                return _safe_float(_get_latest_by_date(df).iloc[-1]) if len(df.columns) > 0 else None
    except Exception as e:
        logger.debug("[macro_data] fetch failed: {}".format(e))
    return None
def _fetch_cn_money_supply(ms_type: str) -> Optional[float]:
    """获取中国货币供应量"""
    try:
        df = ak.macro_china_money_supply()
        if df is not None and not df.empty:
            latest = _get_latest_by_date(df)
            # 框架定义: M1同比/M2同比 → 列名 "货币(M1)-同比增长" / "货币和准货币(M2)-同比增长"
            col_map = {"m1": "货币(M1)-同比增长", "m2": "货币和准货币(M2)-同比增长"}
            col = col_map.get(ms_type)
            if col and col in df.columns:
                return _safe_float(latest.get(col))
            # 降级：尝试从列名匹配
            for c in df.columns:
                if ms_type.upper() in str(c).upper() and "同比" in str(c):
                    return _safe_float(latest.get(c))
    except Exception as e:
        logger.debug("[macro_data] fetch failed: {}".format(e))
    return None
def _fetch_cn_cpi() -> Optional[float]:
    """获取中国 CPI 同比"""
    try:
        df = ak.macro_china_cpi_monthly()
        if df is not None and not df.empty:
            latest = _get_latest_by_date(df)
            for col in df.columns:
                if "同比" in str(col):
                    return _safe_float(latest.get(col))
            return _safe_float(latest.iloc[-1])
    except Exception as e:
        logger.debug("[macro_data] fetch failed: {}".format(e))
    return None
def _fetch_cn_ppi() -> Optional[float]:
    """获取中国 PPI 同比"""
    try:
        df = ak.macro_china_ppi_yearly()
        if df is not None and not df.empty:
            latest = _get_latest_by_date(df)
            return _safe_float(latest.iloc[-1])
    except Exception as e:
        logger.debug("[macro_data] fetch failed: {}".format(e))
    return None
def _fetch_lpr(term: str) -> Optional[float]:
    """获取 LPR 利率"""
    try:
        df = ak.macro_china_lpr()
        if df is not None and not df.empty:
            latest = _get_latest_by_date(df)
            col = f"LPR_{term}"
            if col in df.columns:
                return _safe_float(latest.get(col))
            for c in df.columns:
                if term in str(c):
                    return _safe_float(latest.get(c))
    except Exception as e:
        logger.debug("[macro_data] fetch failed: {}".format(e))
    return None
def _fetch_cn_bond_yield(term: str) -> Optional[float]:
    """获取中国国债收益率
    Args:
        term: "10Y","3Y","1Y","5Y","2Y"
    """
    col_map = {"10Y": "10年期", "3Y": "3年期", "1Y": "1年期", "5Y": "5年期", "2Y": "2年期"}
    target_col = col_map.get(term, term + "年期")
    # 方式1: akshare bond_china_yield
    try:
        df = ak.bond_china_yield()
        if df is not None and not df.empty:
            latest = _get_latest_by_date(df)
            for col in [target_col, term, term.replace("Y", "")]:
                if col in df.columns:
                    v = _safe_float(latest.get(col))
                    if v is not None:
                        return v
            # 模糊匹配: 列名包含 term 数字
            term_num = term.replace("Y", "")
            for col in df.columns:
                if term_num in str(col) and ("年期" in str(col) or "年" in str(col)):
                    v = _safe_float(latest.get(col))
                    if v is not None:
                        return v
    except Exception as e:
        logger.debug(f"[macro_data] bond_china_yield({term}) 失败: {e}")
    # 方式2: ChinaBond 官网估值
    try:
        today = datetime.now().strftime("%Y%m%d")
        url = f"https://yield.chinabond.com.cn/cbweb-mn/yield_main?workDate={today}&locale=zh_CN"
        resp = __import__('requests').get(url, timeout=10, headers={
            "User-Agent": "Mozilla/5.0"})
        if resp.status_code == 200:
            data = resp.json()
            # 简单从 JSON 中尝试提取
            import re
            text = str(data)
            pattern = rf'"{term_num}年.*?":\s*([\d.]+)'
            m = re.search(pattern, text)
            if m:
                v = float(m.group(1))
                if 0.5 < v < 10.0:
                    return round(v, 4)
    except Exception as e:
        logger.debug("[macro_data] fetch failed: {}".format(e))
    return None
def _fetch_shibor() -> Optional[float]:
    """获取 SHIBOR 3M"""
    try:
        df = ak.rate_interbank(market="上海银行间同业拆放利率", indicator="Shibor")
        if df is not None and not df.empty:
            latest = _get_latest_by_date(df)
            for col in df.columns:
                if "3个月" in str(col) or "3M" in str(col):
                    return _safe_float(latest.get(col))
    except Exception as e:
        logger.debug("[macro_data] fetch failed: {}".format(e))
    return None
def _fetch_dr007() -> Optional[float]:
    """获取 DR007"""
    try:
        df = ak.rate_interbank(market="存款类机构质押式回购加权利率", indicator="DR007")
        if df is not None and not df.empty:
            latest = _get_latest_by_date(df)
            return _safe_float(latest.iloc[-1]) if len(df.columns) > 0 else None
    except Exception as e:
        logger.debug("[macro_data] fetch failed: {}".format(e))
    return None
def _fetch_ccfi() -> Optional[float]:
    """获取 CCFI 运价指数"""
    try:
        df = ak.ship_index_ccfi()
        if df is not None and not df.empty:
            latest = _get_latest_by_date(df)
            for col in df.columns:
                if "综合" in str(col) or "CCFI" in str(col).upper():
                    return _safe_float(latest.get(col))
            return _safe_float(latest.iloc[-1]) if len(df.columns) > 0 else None
    except Exception as e:
        logger.debug("[macro_data] fetch failed: {}".format(e))
    return None
def _fetch_global_index(index_name: str) -> Optional[float]:
    """获取全球指数
    akshare index_global_hist 为主，yfinance 为 fallback (仅 HSI/SP500)
    """
    symbol_map = {
        "sp500": ".INX",
        "dxy": "DX-Y.NYB",
        "hsi": "HSI",
    }
    symbol = symbol_map.get(index_name)
    # 方式1: akshare index_global_hist
    if symbol:
        try:
            df = ak.index_global_hist(symbol=symbol)
            if df is not None and not df.empty:
                for col in ["收盘", "close", "最新价"]:
                    if col in df.columns:
                        v = _safe_float(_get_latest_by_date(df).get(col))
                        if v is not None:
                            return v
        except Exception as e:
            logger.debug(f"[macro_data] index_global_hist({index_name}) 失败: {e}")
    # 方式2: yfinance fallback (for HSI, SP500)
    yf_map = {"hsi": "^HSI", "sp500": "^GSPC"}
    yf_symbol = yf_map.get(index_name)
    if yf_symbol:
        try:
            import yfinance as yf
            ticker = yf.Ticker(yf_symbol)
            hist = ticker.history(period="5d")
            if hist is not None and not hist.empty:
                return round(float(hist["Close"].iloc[-1]), 2)
        except Exception as e:
            logger.debug(f"[macro_data] yfinance({index_name}) 失败: {e}")
    return None
def _fetch_csi300() -> Optional[float]:
    """获取沪深 300"""
    try:
        df = ak.stock_zh_index_daily(symbol="sh000300")
        if df is not None and not df.empty:
            return _safe_float(_get_latest_by_date(df)["close"])
    except Exception as e:
        logger.debug("[macro_data] fetch failed: {}".format(e))
    try:
        df = ak.index_zh_a_hist(symbol="000300", period="daily")
        if df is not None and not df.empty:
            return _safe_float(_get_latest_by_date(df)["收盘"])
    except Exception as e:
        logger.debug("[macro_data] fetch failed: {}".format(e))
    return None
def _fetch_vix() -> Optional[float]:
    """获取 VIX"""
    try:
        df = ak.index_vix()
        if df is not None and not df.empty:
            latest = _get_latest_by_date(df)
            return _safe_float(latest.iloc[-1]) if len(df.columns) > 0 else None
    except Exception as e:
        logger.debug("[macro_data] fetch failed: {}".format(e))
    return None
def _fetch_north_flow() -> Optional[float]:
    """获取北向资金净流入 (亿元)"""
    try:
        df = ak.stock_hsgt_hist_em(symbol="沪股通")
        if df is not None and not df.empty:
            df = df.sort_values("日期", ascending=False)
            latest = _get_latest_by_date(df)
            for col in ["当日资金流入", "当日成交净买额"]:
                if col in df.columns:
                    v = _safe_float(latest.get(col))
                    if v is not None:
                        return round(v / 1e8, 2)
    except Exception as e:
        logger.debug("[macro_data] fetch failed: {}".format(e))
    return None
def _fetch_margin_balance() -> Optional[float]:
    """获取融资余额 (亿元)"""
    try:
        df = ak.stock_margin_sse(
            start_date=(datetime.now() - timedelta(days=10)).strftime("%Y%m%d"),
            end_date=datetime.now().strftime("%Y%m%d"),
        )
        if df is not None and not df.empty:
            date_col = next((c for c in df.columns if "日期" in str(c)), df.columns[0])
            margin_col = next(
                (c for c in df.columns if "融资余额" in str(c) or "rzye" in str(c)),
                df.columns[-1],
            )
            df = df.sort_values(date_col, ascending=False)
            v = _safe_float(_get_latest_by_date(df)[margin_col])
            if v is not None:
                return round(v / 1e8, 2)
    except Exception as e:
        logger.debug("[macro_data] fetch failed: {}".format(e))
    return None
def _fetch_commodity(field: str, name: str) -> Optional[float]:
    """获取商品期货价格"""
    symbol_map = {
        "copper_price": ("LME铜", "LMCI"),      # 近似
        "gold_price": ("COMEX金", "GC"),
        "wti_price": ("WTI原油", "CL"),
        "brent_price": ("布伦特油", "B"),
        "iron_ore_price": ("DCE铁矿", "I"),
        "soybean_price": ("CBOT大豆", "S"),
        "corn_price": ("CBOT玉米", "C"),
    }
    if field not in symbol_map:
        return None
    try:
        # 尝试用 akshare 期货接口
        fname, _ = symbol_map[field]
        if field == "copper_price":
            df = ak.futures_foreign_hist(symbol="LME铜")
        elif field == "gold_price":
            df = ak.futures_foreign_hist(symbol="COMEX黄金")
        elif field == "wti_price":
            df = ak.futures_foreign_hist(symbol="NYMEX原油")
        elif field == "brent_price":
            df = ak.futures_foreign_hist(symbol="布伦特原油")
        elif field == "iron_ore_price":
            df = ak.futures_hist_em(symbol="铁矿石主连")
        elif field == "soybean_price":
            df = ak.futures_foreign_hist(symbol="CBOT大豆")
        elif field == "corn_price":
            df = ak.futures_foreign_hist(symbol="CBOT玉米")
        else:
            return None
        if df is not None and not df.empty:
            # 扩展列名匹配: 外盘期货用英文列名, 国内期货用中文列名
            for col in ["收盘价", "close", "最新价", "收盘", "Close", "CLOSE"]:
                if col in df.columns:
                    return _safe_float(_get_latest_by_date(df)[col])
            # 降级: 取最后一列
            return _safe_float(_get_latest_by_date(df).iloc[-1])
    except Exception as e:
        logger.debug(f"[macro_data] commodity({field}) 失败: {e}")
    return None
def _fetch_nh_industrial() -> Optional[float]:
    """获取南华工业品指数 — akshare 当前版本无南华指数专用接口，返回 None 由 fallback 兜底"""
    return None
def _fetch_ism_pmi() -> Optional[float]:
    """获取美国 ISM 制造业 PMI (via akshare)"""
    try:
        df = ak.macro_usa_ism_pmi()
        if df is not None and not df.empty:
            latest = _get_latest_by_date(df)
            for col in ["今值", "现值"]:
                if col in df.columns:
                    v = _safe_float(latest.get(col))
                    if v is not None:
                        return v
            return _safe_float(latest.iloc[-1]) if len(df.columns) > 0 else None
    except Exception as e:
        logger.debug("[macro_data] fetch failed: {}".format(e))
    return None
def _fetch_ism_non_pmi() -> Optional[float]:
    """获取美国 ISM 非制造业 PMI (via akshare)"""
    try:
        df = ak.macro_usa_ism_non_pmi()
        if df is not None and not df.empty:
            latest = _get_latest_by_date(df)
            for col in ["今值", "现值"]:
                if col in df.columns:
                    v = _safe_float(latest.get(col))
                    if v is not None:
                        return v
            return _safe_float(latest.iloc[-1]) if len(df.columns) > 0 else None
    except Exception as e:
        logger.debug("[macro_data] fetch failed: {}".format(e))
    return None
def _fetch_reserve_ratio() -> Optional[float]:
    """获取中国存款准备金率 (大型金融机构最新)"""
    try:
        df = ak.macro_china_reserve_requirement_ratio()
        if df is not None and not df.empty:
            latest = _get_latest_by_date(df)  # 按生效时间倒序，第一行即最新
            v = _safe_float(latest.get("大型金融机构-调整后"))
            if v is not None:
                return v
    except Exception as e:
        logger.debug("[macro_data] fetch failed: {}".format(e))
    return None
def _fetch_foreign_reserves() -> Optional[float]:
    """获取中国外汇储备 (亿美元)"""
    try:
        df = ak.macro_china_foreign_exchange_gold()
        if df is not None and not df.empty:
            # 取最后一个有效值
            for idx in range(len(df) - 1, -1, -1):
                v = _safe_float(df.iloc[idx].get("国家外汇储备"))
                if v is not None and v > 0:
                    return v  # 单位: 亿美元
    except Exception as e:
        logger.debug("[macro_data] fetch failed: {}".format(e))
    return None
def _fetch_trade_surplus() -> Optional[float]:
    """获取中国贸易顺差 (亿美元) — akshare: macro_china_trade_balance"""
    try:
        df = ak.macro_china_trade_balance()
        if df is not None and not df.empty:
            latest = _get_latest_by_date(df)
            v = _safe_float(latest.get("今值"))
            if v is not None:
                return v  # 单位: 亿美元
    except Exception as e:
        logger.debug("[macro_data] fetch failed: {}".format(e))
    return None
def _fetch_euro_pmi() -> Optional[float]:
    """获取欧元区制造业 PMI — akshare: macro_euro_manufacturing_pmi"""
    try:
        df = ak.macro_euro_manufacturing_pmi()
        if df is not None and not df.empty:
            latest = _get_latest_by_date(df)
            v = _safe_float(latest.get("今值"))
            if v is not None:
                return v
    except Exception as e:
        logger.debug("[macro_data] fetch failed: {}".format(e))
    return None
def _fetch_r007() -> Optional[float]:
    """获取 R007 回购利率"""
    try:
        df = ak.repo_rate_query()
        if df is not None and not df.empty:
            df_sorted = df.sort_values("date", ascending=False)
            latest = _get_latest_by_date(df_sorted)
            v = _safe_float(latest.get("FR007"))
            if v is not None:
                return v
    except Exception as e:
        logger.debug("[macro_data] fetch failed: {}".format(e))
    return None
def _fetch_corporate_loan_yoy() -> Optional[float]:
    """获取企业中长期贷款同比增速 — akshare: macro_rmb_loan → 新增人民币贷款-同比"""
    try:
        df = ak.macro_rmb_loan()
        if df is not None and not df.empty:
            latest = _get_latest_by_date(df)
            raw = latest.get("新增人民币贷款-同比", "")
            if isinstance(raw, str) and "%" in raw:
                return _safe_float(raw.replace("%", ""))
            v = _safe_float(raw)
            if v is not None:
                return v
    except Exception as e:
        logger.debug("[macro_data] fetch failed: {}".format(e))
    return None
def _fetch_social_financing_new() -> Optional[float]:
    """获取社会融资规模增量 (亿元) — akshare: macro_china_shrzgm → 社会融资规模增量"""
    try:
        df = ak.macro_china_shrzgm()
        if df is not None and not df.empty:
            latest = _get_latest_by_date(df)
            v = _safe_float(latest.get("社会融资规模增量"))
            if v is not None:
                return v  # 单位: 亿元
    except Exception as e:
        logger.debug("[macro_data] fetch failed: {}".format(e))
    return None
def _fetch_special_bond_progress() -> Optional[float]:
    """获取专项债发行进度 (百分比)
    通过 akshare bond_local_government_issue_cninfo 获取地方债发行数据,
    筛选债券简称含"专项债券"的记录, 累加当年实际发行总量,
    然后按以下逻辑估算进度:
    - 2024年专项债额度约 3.9万亿 (39000亿)
    - 2025年专项债额度约 4.4万亿 (44000亿)
    - 2026年额度近似延续 4.4万亿
    进度 = YTD实际发行累计 / 年度额度 * 100
    若无法获取数据, 返回 None 触发 fallback.
    """
    try:
        now = datetime.now()
        year = now.year
        # 年初至今
        start_date = f"{year}0101"
        end_date = now.strftime("%Y%m%d")
        df = ak.bond_local_government_issue_cninfo(
            start_date=start_date, end_date=end_date
        )
        if df is None or df.empty:
            return None
        # 筛选专项债券
        mask = df["债券简称"].astype(str).str.contains("专项债券|专项债", na=False)
        special_df = df[mask]
        if special_df.empty:
            return None
        # 累加实际发行总量 (亿元)
        total_issued = 0.0
        for col in ["实际发行总量", "实际发行量"]:
            if col in special_df.columns:
                total_issued = pd.to_numeric(special_df[col], errors="coerce").sum()
                break
        if total_issued <= 0:
            return None
        # 年度额度 (亿元) — 根据年份近似
        quota_map = {2024: 39000.0, 2025: 44000.0, 2026: 44000.0}
        annual_quota = quota_map.get(year, 44000.0)
        progress = round(total_issued / annual_quota * 100, 1)
        return progress
    except Exception as e:
        logger.debug("[macro_data] fetch failed: {}".format(e))
    return None
def _fetch_fiscal_revenue() -> Optional[float]:
    """获取中国财政赤字率近似值 (百分比)
    通过 akshare macro_china_czsr 获取财政收入累计值 (亿元),
    结合近似 GDP 数据估算赤字率:
    赤字率 ≈ -3.0% (中国近年预算目标, 年度稳定参数)
    由于财政支出 (czzc) 无直接 akshare 接口,
    且赤字率是年度预算参数 (3月上两会公布),
    此处返回预算目标值作为基准。
    后续如有实时财政收支数据可升级为动态计算。
    Falls back to annual budget target.
    """
    try:
        df = ak.macro_china_czsr()
        if df is not None and not df.empty:
            latest = _get_latest_by_date(df)
            # 获取最近月份累计财政收入
            for col in ["累计", "累计值"]:
                v = _safe_float(latest.get(col))
                if v is not None and v > 0:
                    # 用财政收入 / 近似GDP估算, 但更稳定的做法是返回预算值
                    # 此处仅确认数据可达性, 赤字率为年度参数
                    break
    except Exception as e:
        logger.debug("[macro_data] fetch failed: {}".format(e))
    # 财政赤字率 = GDP占比, 中国近年约 -2.8% ~ -3.2%
    # 2024年目标 3.0%, 2025年目标 4.0%
    now = datetime.now()
    year = now.year
    deficit_map = {2024: 3.0, 2025: 4.0, 2026: 4.0}
    return deficit_map.get(year, 3.0)
def _fetch_cftc_dollar_net() -> Optional[float]:
    """获取 CFTC 美元净头寸"""
    try:
        df = ak.macro_usa_cftc_nc_holding()
        if df is not None and not df.empty:
            latest = _get_latest_by_date(df)  # 最新日期在最后
            v = _safe_float(latest.get("美元-净仓位"))
            if v is not None:
                return v
    except Exception as e:
        logger.debug("[macro_data] fetch failed: {}".format(e))
    return None
def _fetch_usd_cnh() -> Optional[float]:
    """获取 USD/CNH 离岸人民币汇率"""
    try:
        df = ak.forex_hist_em(
            symbol="USDCNH",
            start_date=(datetime.now() - timedelta(days=10)).strftime("%Y%m%d"),
            end_date=datetime.now().strftime("%Y%m%d"),
        )
        if df is not None and not df.empty:
            latest = _get_latest_by_date(df)
            for col in ["最新价", "收盘"]:
                if col in df.columns:
                    v = _safe_float(latest.get(col))
                    if v is not None:
                        return v
            return _safe_float(latest.iloc[-1]) if len(df.columns) > 0 else None
    except Exception as e:
        logger.debug(f"[macro_data] usd_cnh 方式1 失败: {e}")
    # 备选: 中行外汇牌价
    try:
        df = ak.currency_boc_sina()
        if df is not None and not df.empty:
            latest = _get_latest_by_date(df)
            for col in ["中行折算价", "折算价", "现汇买入"]:
                if col in df.columns:
                    v = _safe_float(latest.get(col))
                    if v is not None and 5 < v < 9:
                        return v
            # 最后一个尝试: 现汇买卖均值
            buy = _safe_float(latest.get("现汇买入"))
            sell = _safe_float(latest.get("现汇卖出"))
            if buy is not None and sell is not None:
                avg = round((buy + sell) / 2 / 100, 4)
                if 5 < avg < 9:
                    return avg
    except Exception as e:
        logger.debug(f"[macro_data] usd_cnh 方式2 失败: {e}")
    return None
def _fetch_mlf_rate() -> Optional[float]:
    """获取 MLF 中期借贷便利利率 (1Y)
    数据源: akshare macro_china_mlf_rate (PBOC 公布)
    错误修正: 之前误用 macro_china_lpr (贷款报价利率 ≈3.1%)
              MLF 才是中期借贷便利利率 (≈2.0%)
    """
    # 方式1: akshare 直取 MLF 利率
    try:
        if hasattr(ak, 'macro_china_mlf_rate'):
            df = ak.macro_china_mlf_rate()
            if df is not None and not df.empty:
                latest = df.iloc[-1] if len(df) > 0 else _get_latest_by_date(df)
                for col in ["利率", "MLF利率", "中标利率", "操作利率"]:
                    if col in df.columns:
                        v = _safe_float(latest.get(col))
                        if v is not None and 1.0 < v < 5.0:
                            return v
                # 取最后一列数值
                v = _safe_float(latest.iloc[-1]) if len(df.columns) > 0 else None
                if v is not None and 1.0 < v < 5.0:
                    return v
    except Exception as e:
        logger.debug(f"[macro_data] MLF 方式1 失败: {e}")
    # 方式2: 用 1Y LPR - 1.0% 近似 (LPR=MLF+银行加点，加点通常~1.0%)
    try:
        df = ak.macro_china_lpr()
        if df is not None and not df.empty:
            latest = df.iloc[-1] if len(df) > 0 else _get_latest_by_date(df)
            for col in ["1年期", "一年期", "LPR1Y"]:
                if col in df.columns:
                    v = _safe_float(latest.get(col))
                    if v is not None:
                        # LPR = MLF + spread(~1.0%), 反推 MLF ≈ LPR - 1.0
                        mlf_approx = round(v - 1.0, 2)
                        if 1.5 < mlf_approx < 3.0:
                            logger.info(f"[macro_data] MLF 使用 LPR 反推: {v} -> {mlf_approx}")
                            return mlf_approx
    except Exception as e:
        logger.debug(f"[macro_data] MLF 方式2 失败: {e}")
    return None
# ── 新增: 公开市场操作、债市、估值、期货 ──────────────────────
def _fetch_omo_net_injection() -> Optional[float]:
    """获取央行公开市场操作周度净投放 (亿元)
    通过 akshare macro_china_gksccz 获取正/逆回购操作记录，
    计算最近一周的净投放量 = 逆回购投放 - 逆回购到期。
    """
    try:
        df = ak.macro_china_gksccz()
        if df is None or df.empty:
            return None
        # 按日期排序取最近5个交易日
        if "操作日期" in df.columns or "日期" in df.columns:
            date_col = next((c for c in df.columns if "日期" in str(c)), df.columns[0])
            df = df.sort_values(date_col, ascending=False)
        # 取最近 5 行进行聚合
        recent = df.head(5)
        net = 0.0
        # 正回购: 回笼; 逆回购: 投放
        for _, row in recent.iterrows():
            amount = 0.0
            for col in ["交易量", "投放量", "操作量"]:
                if col in df.columns:
                    v = _safe_float(row.get(col))
                    if v is not None:
                        amount = v
                        break
            direction = ""
            for col in ["操作方向", "方向", "正/逆回购"]:
                if col in df.columns:
                    direction = str(row.get(col))
                    break
            # 逆回购 = 净投放 (+), 正回购 = 净回笼 (-)
            if "逆回购" in direction or "回购" in str(row.get("正/逆回购", "")):
                net += amount
            elif "正回购" in direction:
                net -= amount
            else:
                net += amount  # 默认投放
        return round(net, 2)
    except Exception as e:
        logger.debug("[macro_data] fetch failed: {}".format(e))
    return None
def _fetch_csi300_pe() -> Optional[float]:
    """获取沪深300 PE_TTM (市盈率) — akshare: stock_zh_index_value_csindex"""
    try:
        df = ak.stock_zh_index_value_csindex(symbol="000300")
        if df is not None and not df.empty:
            latest = _get_latest_by_date(df)
            for col in df.columns:
                if "PE" in str(col).upper() or "市盈率" in str(col):
                    v = _safe_float(latest.get(col))
                    if v is not None:
                        return v
            return _safe_float(latest.iloc[-1]) if len(df.columns) > 0 else None
    except Exception as e:
        logger.debug(f"[macro_data] csi300_pe 失败: {e}")
    return None
def _fetch_csi300_pb() -> Optional[float]:
    """获取沪深300 PB (市净率) — akshare: stock_zh_index_value_csindex"""
    try:
        df = ak.stock_zh_index_value_csindex(symbol="000300")
        if df is not None and not df.empty:
            latest = _get_latest_by_date(df)
            for col in df.columns:
                if "PB" in str(col).upper() or "市净率" in str(col):
                    v = _safe_float(latest.get(col))
                    if v is not None:
                        return v
            return _safe_float(latest.iloc[-1]) if len(df.columns) > 0 else None
    except Exception as e:
        logger.debug(f"[macro_data] csi300_pb 失败: {e}")
    return None
def _fetch_csi300_futures() -> Optional[float]:
    """获取沪深300股指期货主力连续合约价格 (CFFEX IF)
    通过 akshare futures_zh_daily_sina 获取 IF0 连续合约收盘价。
    """
    try:
        df = ak.futures_zh_daily_sina(symbol="IF0")
        if df is not None and not df.empty:
            latest = _get_latest_by_date(df)
            for col in ["close", "收盘价", "收盘"]:
                if col in df.columns:
                    v = _safe_float(latest.get(col))
                    if v is not None:
                        return v
            return _safe_float(latest.iloc[-1]) if len(df.columns) > 0 else None
    except Exception as e:
        logger.debug(f"[macro_data] csi300_futures 方式1 失败: {e}")
    # 备选: 期货主力连续
    try:
        df = ak.futures_main_sina(symbol="IF")
        if df is not None and not df.empty:
            latest = _get_latest_by_date(df)
            for col in ["close", "收盘价", "收盘"]:
                if col in df.columns:
                    return _safe_float(latest.get(col))
            return _safe_float(latest.iloc[-1]) if len(df.columns) > 0 else None
    except Exception as e:
        logger.debug(f"[macro_data] csi300_futures 方式2 失败: {e}")
    return None
def _fetch_aa_bond_yield(term: str) -> Optional[float]:
    """获取 AA 级中短期票据收益率
    通过 akshare bond_china_close_return 获取中债 AA 级收益率曲线。
    """
    try:
        df = ak.bond_china_close_return(
            symbol="中短期票据AA",
            period=term.replace("Y", ""),
            start_date=(datetime.now() - timedelta(days=10)).strftime("%Y%m%d"),
            end_date=datetime.now().strftime("%Y%m%d"),
        )
        if df is not None and not df.empty:
            latest = _get_latest_by_date(df)
            for col in df.columns:
                if "收益率" in str(col) or "到期" in str(col):
                    v = _safe_float(latest.get(col))
                    if v is not None:
                        return v
            return _safe_float(latest.iloc[-1]) if len(df.columns) > 0 else None
    except Exception as e:
        logger.debug("[macro_data] fetch failed: {}".format(e))
    # 备选: 直接用 bond_china_yield 系列
    try:
        df = ak.bond_china_yield()
        if df is not None and not df.empty:
            latest = _get_latest_by_date(df)
            for col in df.columns:
                if "AA" in str(col) and "中短期" in str(col):
                    v = _safe_float(latest.get(col))
                    if v is not None:
                        return v
    except Exception as e:
        logger.debug("[macro_data] fetch failed: {}".format(e))
    return None
def _fetch_cdic_bond_yield(term: str) -> Optional[float]:
    """获取城投债 (AA+) 收益率
    通过 akshare bond_china_close_return 获取中债城投债收益率曲线。
    """
    try:
        df = ak.bond_china_close_return(
            symbol="城投债AA+",
            period=term.replace("Y", ""),
            start_date=(datetime.now() - timedelta(days=10)).strftime("%Y%m%d"),
            end_date=datetime.now().strftime("%Y%m%d"),
        )
        if df is not None and not df.empty:
            latest = _get_latest_by_date(df)
            for col in df.columns:
                if "收益率" in str(col) or "到期" in str(col):
                    v = _safe_float(latest.get(col))
                    if v is not None:
                        return v
            return _safe_float(latest.iloc[-1]) if len(df.columns) > 0 else None
    except Exception as e:
        logger.debug("[macro_data] fetch failed: {}".format(e))
    # 备选: bond_china_yield
    try:
        df = ak.bond_china_yield()
        if df is not None and not df.empty:
            latest = _get_latest_by_date(df)
            for col in df.columns:
                if "城投" in str(col) and ("AA+" in str(col) or "AA" in str(col)):
                    v = _safe_float(latest.get(col))
                    if v is not None:
                        return v
    except Exception as e:
        logger.debug("[macro_data] fetch failed: {}".format(e))
    return None
# ═══════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════
def _safe_float(value: Any) -> Optional[float]:
    """安全转换为浮点数"""
    if value is None:
        return None
    try:
        v = float(value)
        if not np.isfinite(v):
            return None
        return v
    except (ValueError, TypeError):
        return None
# ═══════════════════════════════════════════════════════════
# 模块级便捷函数
# ═══════════════════════════════════════════════════════════
def fetch_macro_data(target_date: Optional[str] = None) -> Dict[str, Any]:
    """模块级便捷函数：获取所有宏观数据"""
    source = MacroDataSource()
    return source.fetch_macro_data(target_date)
def fetch_macro_values(target_date: Optional[str] = None) -> Dict[str, float]:
    """模块级便捷函数：只返回 {字段名: 数值}"""
    source = MacroDataSource()
    return source.get_all_fields()
# ═══════════════════════════════════════════════════════════
# 数据桥接：将扁平 fields 转为 MacroAgent 期望的嵌套格式
# ═══════════════════════════════════════════════════════════
def convert_to_agent_format(raw_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    将 fetch_macro_data() 返回的扁平 fields 结构
    转换为 MacroAgent._fetch_macro_data() 期望的嵌套 dict 格式。
    Args:
        raw_result: fetch_macro_data() 的返回值
    Returns:
        与 build_complete_mock_data() 同结构的嵌套 dict
    """
    fields = raw_result.get("fields", {})
    # 提取值，构建简单 key->value 映射
    raw: Dict[str, float] = {}
    for k, v in fields.items():
        if isinstance(v, dict) and "value" in v:
            raw[k] = v["value"]
    def _v(*keys: str, default: Any = 0.0) -> Any:
        """从 raw 中取第一个存在的值"""
        for k in keys:
            if k in raw and raw[k] is not None:
                return raw[k]
        return default
    data: Dict[str, Any] = {
        "_is_mock": False,
        "_report_date": raw_result.get("fetch_time", ""),
        "_data_sources": f"实时: FRED({raw_result.get('fallback_fields', [])}个fallback)",
    }
    # ── 中国数据 ──
    data["china"] = {
        # 增长
        "nbs_manufacturing_pmi": _v("nbs_manufacturing_pmi"),
        "caixin_manufacturing_pmi": _v("caixin_manufacturing_pmi"),
        "non_manufacturing_pmi": _v("non_manufacturing_pmi"),
        "industrial_added_value_yoy": _v("industrial_production_yoy_cn"),
        "gdp_yoy": _v("gdp_yoy"),
        "retail_sales_yoy": _v("retail_sales_yoy_cn"),
        "export_yoy_usd": _v("exports_yoy_cn"),
        "fixed_asset_investment_yoy": _v("fixed_asset_investment_yoy"),
        "auto_sales_yoy": _v("auto_sales_yoy"),
        "ccfi_index": _v("ccfi_index"),
        "property_sales_area_yoy": _v("property_sales_area_yoy"),
        "property_investment_yoy": _v("property_investment_yoy"),
        "new_order_inventory_spread": _v("new_order_inventory_spread", default=3.5),
        # 通胀
        "cpi_yoy": _v("cpi_yoy_cn"),
        "ppi_yoy": _v("ppi_yoy_cn"),
        "core_cpi_yoy": _v("core_cpi_yoy", default=0.5),
        "nh_industrial_index_yoy": _v("nh_industrial_index_yoy", default=0.0),
        "nh_industrial_index": _v("nh_industrial_index", default=3800.0),
        # 信用/流动性
        "tsf_yoy": _v("social_financing_yoy"),
        "tsf_new_bn": _v("social_financing_new"),
        "m1_yoy": _v("m1_yoy_cn"),
        "m2_yoy": _v("m2_yoy_cn"),
        "corp_mid_long_loan_yoy": _v("corporate_loan_yoy"),
        "dr007": _v("dr007"),
        "shibor_3m": _v("shibor_3m"),
        "margin_balance": _v("margin_balance", default=14800.0) * 1e8,
        # 政策
        "1y_lpr": _v("lpr_1y"),
        "5y_lpr": _v("lpr_5y"),
        "mlf_rate": _v("mlf_rate"),
        "repo_7d_rate": _v("r007"),
        "reserve_cut_bp": _v("reserve_ratio"),
        "omo_net_injection": _v("omo_net_injection", default=0.0),
        # 市场定价
        "cn_10y_yield": _v("cn_10y_yield"),
        "cn_2y_yield": _v("cn_1y_yield"),  # 近似: 1Y ≈ 短端
        "cn_3y_yield": _v("cn_3y_yield"),
        "csi300_erp": _v("csi300_erp"),
        "csi300_pe": _v("csi300_pe", default=12.5),
        "csi300_pb": _v("csi300_pb", default=1.4),
        "aa_credit_spread": _v("aa_credit_spread"),
        "city_invest_spread": _v("city_invest_spread", default=3.0),
        # Layer 2 政策维度（当前无 NLP，默认中性）
        "monetary_policy_direction": "neutral",
        "fiscal_policy_direction": "neutral",
        "real_estate_policy_direction": "neutral",
        "regulation_event": "neutral",
        "special_bond_progress": _v("special_bond"),    # akshare bond_local_government_issue_cninfo
        "fiscal_deficit_rate": _v("fiscal_deficit"),    # 年度预算参数 (akshare macro_china_czsr)
        # Layer 3 衍生品
        "csi300_index": _v("csi300_index", default=4000.0),
        "csi300_forward": _v("csi300_forward", default=4000.0),
        "csi300_futures_basis": _v("csi300_futures_basis", default=0.0),
        "csi300_put": _v("csi300_put", default=100.0),
        "csi300_call": _v("csi300_call", default=100.0),
        "pc_ratio": _v("pc_ratio", default=1.0),
    }
    # ── 美国数据 ──
    data["us"] = {
        "ism_manufacturing_pmi": _v("ism_manufacturing_pmi"),
        "ism_services_pmi": _v("ism_services_pmi"),
        "nonfarm_payrolls": _v("nonfarm_payrolls", default=200000),
        "us_unemployment_rate": _v("us_unemployment_rate"),
        "gdp_growth": _v("gdp_yoy"),
        "retail_sales_yoy": _v("retail_sales_yoy"),
        "personal_consumption_yoy": _v("personal_consumption_yoy"),
        "industrial_production_yoy": _v("industrial_production_yoy"),
        "housing_starts": _v("housing_starts"),
        "existing_home_sales": _v("existing_home_sales"),
        "initial_jobless_claims_4w_avg": _v("initial_jobless_claims_4w"),
        "core_pce_yoy": _v("core_pce_yoy"),
        "cpi_yoy": _v("cpi_yoy"),
        "core_cpi_yoy": _v("core_cpi_yoy"),
        "eci_wage_qoq": _v("eci_wage"),
        "breakeven_5y5y": _v("breakeven_5y5y"),
        "tips_10y_breakeven": _v("tips_10y_breakeven"),
        "ffr": _v("ffr"),
        "fed_total_assets": _v("fed_total_assets", default=7.0) * 1e12,
        "sofr": _v("sofr"),
        "effr": _v("effr"),
        "m2_yoy": _v("us_m2_yoy"),
        "credit_pulse": _v("credit_pulse"),
        "overseas_flow_us": _v("overseas_flow_us"),
        "us_10y_yield": _v("us_10y_yield"),
        "us_2y_yield": _v("us_2y_yield"),
        "sp500_index": _v("sp500_index"),
        "sp500_erp": _v("sp500_erp"),
        "us_hy_spread": _v("us_hy_spread"),
        "us_ig_spread": _v("us_ig_spread"),
        "dxy_index": _v("dxy", "dxy_broad"),
        "cftc_dollar_net": _v("cftc_net_position_pct"),
    }
    # ── 跨国数据 ──
    data["cross_border"] = {
        "cn_us_10y_spread": _v("cn_us_10y_spread"),
        "usd_cnh": _v("usd_cnh"),
        "usd_cnh_1y_forward": _v("usd_cnh_1y_forward"),
        "vix": _v("vix"),
        "euro_pmi": _v("euro_pmi"),
        "rmb_reer": _v("rmb_reer"),
        "copper_price": _v("copper_price", default=9500.0),
        "gold_price": _v("gold_price", default=2400.0),
        "brent_oil": _v("brent_price", default=85.0),
        "wti_oil": _v("wti_price", default=80.0),
        "trade_surplus": _v("trade_surplus_cn"),
        "forex_reserve_change": _v("foreign_reserves"),
        "pboc_mid_deviation": _v("pboc_mid_deviation", default=1.5),
        "cnh_cny_spread": _v("cnh_cny_spread", default=0.05),
        "north_flow": _v("north_flow", default=100.0),
        "global_pmi": _v("global_pmi"),
    }
    # ── 大宗商品 ──
    data["commodities"] = {
        "copper_gold_ratio": _v("copper_gold_ratio", default=0.12),
        "oil_gold_ratio": _v("oil_gold_ratio", default=0.035),
        "copper_price": _v("copper_price", default=9500.0),
        "gold_price": _v("gold_price", default=2400.0),
        "brent_oil": _v("brent_price", default=85.0),
        "wti_oil": _v("wti_price", default=80.0),
        "iron_ore_price": _v("iron_ore_price", default=830.0),
        "iron_ore_usd": _v("iron_ore_usd", default=106.0),
        "nh_industrial_index": _v("nh_industrial_index", default=3800.0),
        "soybean_corn_ratio": _v("soybean_corn_ratio", default=2.4),
        "soybean_price": _v("soybean_price", default=1200.0),
        "corn_price": _v("corn_price", default=500.0),
        "gold_vs_real_rate": _v("gold_vs_real_rate", default=0.0),
        "nh_global_pmi_ratio": _v("nh_global_pmi_ratio", default=76.0),
        "crb_proxy_index": _v("crb_proxy_index", default=280.0),
    }
    # ── 市场定价 ──
    data["market_pricing"] = {
        "csi300_index": _v("csi300_index", default=4000.0),
        "csi300_forward": _v("csi300_forward", default=4000.0),
        "csi300_futures_basis": _v("csi300_futures_basis", default=0.0),
        "csi300_put": _v("csi300_put", default=100.0),
        "csi300_call": _v("csi300_call", default=100.0),
        "pc_ratio": _v("pc_ratio", default=1.0),
        "gov_bond_10y_holding_change": _v("gov_bond_10y_holding_change", default=0.0),
        "hshare_ah_spread": _v("hshare_ah_spread", default=140.0),
        "copper_near": _v("copper_price", default=9500.0),
        "copper_far": _v("copper_far", default=9400.0),
        "oil_near": _v("wti_price", "brent_price", default=85.0),
        "oil_far": _v("oil_far", default=83.0),
    }
    # ── 预期差 ──
    data["expected_diff"] = {
        "china_surprise_index": _v("china_surprise_index"),
        "us_surprise_index": _v("us_surprise_index"),
        "ff_implied_rate": _v("ff_futures_implied_rate", "ffr"),
    }
    # ── 反身性 ──
    data["reflexivity"] = {
        "position_concentration_z": _v("cftc_net_position_pct"),
        "cftc_net_position_pct": _v("cftc_net_position_pct"),
        "etf_flow_cny_bn": _v("etf_flow_cny_bn"),
        "northbound_flow_cny_bn": _v("north_flow"),
        "sell_side_bearish_pct": _v("sell_side_bearish_pct"),
        "buy_side_bearish_pct": _v("buy_side_bearish_pct"),
    }
    return data
def fetch_agent_data(target_date: Optional[str] = None) -> Dict[str, Any]:
    """
    直接返回 MacroAgent 可消费的嵌套格式数据。
    相当于 fetch_macro_data() + convert_to_agent_format()。
    Args:
        target_date: 目标日期 (YYYY-MM-DD)
    Returns:
        与 build_complete_mock_data() 同结构的嵌套 dict
    """
    raw = fetch_macro_data(target_date)
    return convert_to_agent_format(raw)
# ═══════════════════════════════════════════════════════════
# 补充数据源函数 (Phase 7+ 新增)
# ═══════════════════════════════════════════════════════════
def _fetch_pboc_midpoint() -> Optional[float]:
    """获取 PBOC 美元中间价"""
    if not HAS_AKSHARE:
        return None
    try:
        df = ak.currency_boc_sina(symbol="美元")
        if df is not None and not df.empty and "中行折算价" in df.columns:
            v = _safe_float(_get_latest_by_date(df)["中行折算价"])
            if v and v > 0:
                return v
    except Exception as e:
        logger.debug("[macro_data] fetch failed: {}".format(e))
    try:
        # fallback: 外汇牌价
        df = ak.fx_spot_quote()
        if df is not None and not df.empty:
            for col in ["中间价", "折算价", "价格"]:
                if col in df.columns:
                    v = _safe_float(_get_latest_by_date(df)[col])
                    if v and 5 < v < 9:
                        return v
    except Exception as e:
        logger.debug("[macro_data] fetch failed: {}".format(e))
    return None
def _fetch_cny_spot() -> Optional[float]:
    """获取境内 CNY 即期汇率"""
    if not HAS_AKSHARE:
        return None
    try:
        df = ak.currency_boc_sina(symbol="美元")
        if df is not None and not df.empty and "现汇买入" in df.columns:
            buy = _safe_float(_get_latest_by_date(df)["现汇买入"])
            sell = _safe_float(_get_latest_by_date(df)["现汇卖出"])
            if buy and sell and buy > 0:
                return round((buy + sell) / 2, 4)
    except Exception as e:
        logger.debug("[macro_data] fetch failed: {}".format(e))
    try:
        df = ak.fx_spot_quote()
        if df is not None and not df.empty:
            for col in df.columns:
                v = _safe_float(_get_latest_by_date(df)[col])
                if v and 5 < v < 9:
                    return v
    except Exception as e:
        logger.debug("[macro_data] fetch failed: {}".format(e))
    return None
def _fetch_pboc_mid_deviation() -> Optional[float]:
    """计算 PBOC 中间价偏离度 (pips)"""
    mid = _fetch_pboc_midpoint()
    cnh = None
    try:
        df = ak.fx_spot_quote()
        if df is not None and not df.empty:
            for col in df.columns:
                v = _safe_float(_get_latest_by_date(df)[col])
                if v and 6 < v < 8:
                    cnh = v
                    break
    except Exception as e:
        logger.debug("[macro_data] fetch failed: {}".format(e))
    if mid and cnh and mid > 0:
        return round((cnh - mid) / mid * 100, 2)
    return None
def _fetch_cnh_cny_spread() -> Optional[float]:
    """计算 CNH-CNY 价差 (%)"""
    cny = _fetch_cny_spot()
    cnh = None
    try:
        df = ak.fx_spot_quote()
        if df is not None and not df.empty:
            for col in df.columns:
                v = _safe_float(_get_latest_by_date(df)[col])
                if v and 6 < v < 8:
                    cnh = v
                    break
    except Exception as e:
        logger.debug("[macro_data] fetch failed: {}".format(e))
    if cny and cnh:
        return round((cnh - cny) / cny * 100, 2)
    return None
def _fetch_ff_implied_from_cme() -> Optional[float]:
    """
    从 CME FedWatch 工具或简单规则估算 FF 隐含利率。
    降级: 使用 EFFR + 市场利差估算。
    """
    if not HAS_AKSHARE:
        return None
    # 尝试从 akshare 获取联邦基金期货
    try:
        df = ak.futures_foreign_hist(symbol="ZQ")  # 30-Day Fed Funds futures
        if df is not None and not df.empty:
            latest_close = _safe_float(_get_latest_by_date(df).get("收盘价", _get_latest_by_date(df).get("close", None)))
            if latest_close and latest_close > 0:
                # ZQ 报价 = 100 - rate → rate = 100 - price
                implied = round(100.0 - latest_close, 2)
                if 0 < implied < 10:
                    return implied
    except Exception as e:
        logger.debug(f"[macro_data] ff_implied ZQ 失败: {e}")
    # 备选: CME FedWatch 概率加权推算 — 当前 akshare 无可用接口，降级为动态 fallback
    return None
def _fetch_etf_flow_cn() -> Optional[float]:
    """获取中国股票ETF资金流 (亿元)"""
    if not HAS_AKSHARE:
        return None
    try:
        df = ak.fund_etf_fund_info_em()
        if df is not None and not df.empty:
            # 尝试找资金流相关列
            for col in ["净流入", "资金流向", "fund_flow"]:
                if col in df.columns:
                    total = _safe_float(df[col].sum())
                    if total:
                        return round(total / 1e8, 2)  # 转为亿元
    except Exception as e:
        logger.debug("[macro_data] fetch failed: {}".format(e))
    return None
def _fetch_cffex_bond_futures() -> Optional[Dict[str, float]]:
    """获取中金所国债期货数据 (10Y 主力合约)"""
    if not HAS_AKSHARE:
        return None
    try:
        df = ak.futures_zh_daily_sina(symbol="T")  # 10Y 国债期货
        if df is not None and not df.empty and len(df) >= 2:
            latest = _get_latest_by_date(df)
            prev = df.iloc[-2]
            price = _safe_float(latest.get("close", latest.get("收盘价")))
            prev_price = _safe_float(prev.get("close", prev.get("收盘价")))
            if price and prev_price:
                return {
                    "gov_bond_10y_holding_change": round(price - prev_price, 2),
                }
    except Exception as e:
        logger.debug("[macro_data] fetch failed: {}".format(e))
    return None
def _fetch_csi300_option_data() -> Optional[Dict[str, float]]:
    """获取沪深300期权 P/C ratio 相关数据"""
    if not HAS_AKSHARE:
        return None
    try:
        df = ak.option_finance_board(symbol="沪深300ETF期权")
        if df is not None and not df.empty:
            call_vol = 0.0
            put_vol = 0.0
            if "认购成交量" in df.columns:
                call_vol = _safe_float(df["认购成交量"].sum()) or 0.0
            if "认沽成交量" in df.columns:
                put_vol = _safe_float(df["认沽成交量"].sum()) or 0.0
            if put_vol > 0:
                pc = round(put_vol / call_vol, 2) if call_vol > 0 else 1.0
                return {"pc_ratio": pc}
    except Exception as e:
        logger.debug("[macro_data] fetch failed: {}".format(e))
    return None

