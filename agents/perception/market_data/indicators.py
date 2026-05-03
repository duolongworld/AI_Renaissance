"""
技术指标计算 — MA、BOLL、RSI、筹码分布

所有指标均从K线数据计算，不依赖外部指标API。
"""

from typing import Dict, Any, List

import numpy as np
import pandas as pd


def calc_ma(
    closes: pd.Series,
    periods: List[int] = None,
) -> Dict[str, List[float]]:
    """计算移动平均线"""
    if periods is None:
        periods = [5, 10, 20, 60, 120, 250]
    result = {}
    for p in periods:
        ma = closes.rolling(window=p, min_periods=1).mean()
        result[f"ma{p}"] = _to_list(ma)
    return result


def calc_boll(
    closes: pd.Series,
    period: int = 20,
    std_dev: int = 2,
) -> Dict[str, List[float]]:
    """计算布林带"""
    middle = closes.rolling(window=period, min_periods=1).mean()
    std = closes.rolling(window=period, min_periods=1).std()
    upper = middle + std_dev * std
    lower = middle - std_dev * std
    return {
        "upper": _to_list(upper),
        "middle": _to_list(middle),
        "lower": _to_list(lower),
    }


def calc_rsi(
    closes: pd.Series,
    periods: List[int] = None,
) -> Dict[str, List[float]]:
    """计算RSI（Wilder平滑法）"""
    if periods is None:
        periods = [6, 12, 24]
    delta = closes.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)

    result = {}
    for p in periods:
        avg_gain = gain.ewm(alpha=1 / p, min_periods=p).mean()
        avg_loss = loss.ewm(alpha=1 / p, min_periods=p).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        rsi = rsi.fillna(50.0)
        result[f"rsi{p}"] = _to_list(rsi)
    return result


def calc_chip_distribution(
    kline_data: List[Dict[str, Any]],
    days: int = 120,
    bins: int = 50,
) -> Dict[str, Any]:
    """
    计算筹码分布

    基于历史K线的成交量-价格分布模型：
    每个交易日的成交量均匀分布在 [low, high] 区间，
    并按指数衰减，近期权重更高。

    Returns:
        {
            "prices": [价位列表],
            "distribution": [对应筹码占比],
            "support_price": 支撑位（筹码最密集区间的中位数），
            "pressure_price": 压力位（上方筹码密集区间的中位数），
        }
    """
    if len(kline_data) < 5:
        return {"prices": [], "distribution": [], "support_price": 0.0, "pressure_price": 0.0}

    recent = kline_data[-days:]
    all_highs = [k["high"] for k in recent]
    all_lows = [k["low"] for k in recent]
    price_min = min(all_lows)
    price_max = max(all_highs)

    if price_max <= price_min:
        return {"prices": [], "distribution": [], "support_price": price_min, "pressure_price": price_max}

    edges = np.linspace(price_min, price_max, bins + 1)
    centers = (edges[:-1] + edges[1:]) / 2
    accum = np.zeros(bins)

    n = len(recent)
    for i, bar in enumerate(recent):
        lo, hi = bar["low"], bar["high"]
        vol = bar["volume"]
        if hi <= lo or vol <= 0:
            continue

        decay = np.exp(-3.0 * (n - 1 - i) / n)

        bar_prices = np.linspace(lo, hi, max(int((hi - lo) / (price_max - price_min) * bins), 3))
        hist, _ = np.histogram(bar_prices, bins=edges)
        count = hist.sum()
        if count > 0:
            accum += hist / count * vol * decay

    total = accum.sum()
    if total > 0:
        dist = accum / total
    else:
        dist = accum

    last_close = kline_data[-1]["close"]

    below_mask = centers < last_close
    above_mask = centers > last_close

    support_idx = np.argmax(dist * below_mask) if below_mask.any() else 0
    pressure_idx = np.argmax(dist * above_mask) if above_mask.any() else -1

    return {
        "prices": _to_list(pd.Series(centers)),
        "distribution": _to_list(pd.Series(dist)),
        "support_price": round(float(centers[support_idx]), 2),
        "pressure_price": round(float(centers[pressure_idx]), 2) if pressure_idx >= 0 else round(price_max, 2),
    }


def calc_volume_ma(
    volumes: pd.Series,
    periods: List[int] = None,
) -> Dict[str, List[float]]:
    """计算成交量均线"""
    if periods is None:
        periods = [5, 10, 20]
    result = {}
    for p in periods:
        vma = volumes.rolling(window=p, min_periods=1).mean()
        result[f"vma{p}"] = _to_list(vma)
    return result


def _to_list(series: pd.Series) -> List[float]:
    """将 pandas Series 转为 JSON 安全的 float 列表，NaN → None"""
    return [
        round(float(v), 4) if pd.notna(v) else None
        for v in series.values
    ]
