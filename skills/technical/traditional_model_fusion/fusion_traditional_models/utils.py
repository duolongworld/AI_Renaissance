from __future__ import annotations

import math
from datetime import datetime
from typing import Iterable, List, Optional, Sequence, Tuple

import numpy as np


def safe_float(value) -> float:
    if value is None or value == "":
        return math.nan
    try:
        return float(value)
    except Exception:
        return math.nan


def finite_or(value: float, fallback: float) -> float:
    return value if isinstance(value, (int, float)) and math.isfinite(float(value)) else fallback


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def to_iso_date(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    return str(value)


def rolling_mean(arr: np.ndarray, window: int) -> np.ndarray:
    if window <= 1:
        return arr.astype(float)
    out = np.full_like(arr, np.nan, dtype=float)
    if len(arr) < window:
        return out
    c = np.cumsum(np.insert(arr.astype(float), 0, 0.0))
    out[window - 1 :] = (c[window:] - c[:-window]) / window
    return out


def rolling_nanmean(arr: np.ndarray, window: int, min_periods: int | None = None) -> np.ndarray:
    values = arr.astype(float)
    out = np.full_like(values, np.nan, dtype=float)
    if window <= 1:
        return values
    if len(values) < window:
        return out
    required = window if min_periods is None else min_periods
    finite = np.isfinite(values)
    filled = np.where(finite, values, 0.0)
    sums = np.cumsum(np.insert(filled, 0, 0.0))
    counts = np.cumsum(np.insert(finite.astype(float), 0, 0.0))
    window_sums = sums[window:] - sums[:-window]
    window_counts = counts[window:] - counts[:-window]
    valid = window_counts >= required
    out_values = np.divide(window_sums, window_counts, out=np.full_like(window_sums, np.nan), where=window_counts > 0)
    out[window - 1 :] = np.where(valid, out_values, np.nan)
    return out


def ema(values: np.ndarray, span: int) -> np.ndarray:
    v = values.astype(float)
    out = np.full_like(v, np.nan, dtype=float)
    if len(v) == 0:
        return out
    alpha = 2.0 / (span + 1.0)
    out[0] = v[0]
    for i in range(1, len(v)):
        out[i] = alpha * v[i] + (1 - alpha) * out[i - 1]
    return out


def rsi(close: np.ndarray, window: int = 14) -> np.ndarray:
    c = close.astype(float)
    if len(c) == 0:
        return np.array([], dtype=float)
    delta = np.diff(c, prepend=c[0])
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    avg_gain = rolling_mean(gain, window)
    avg_loss = rolling_mean(loss, window)
    rs = np.where(avg_loss == 0, np.inf, avg_gain / avg_loss)
    r = 100.0 - (100.0 / (1.0 + rs))
    return r


def roc(close: np.ndarray, window: int = 12) -> np.ndarray:
    c = close.astype(float)
    out = np.full_like(c, np.nan, dtype=float)
    if len(c) <= window:
        return out
    out[window:] = (c[window:] - c[:-window]) / c[:-window] * 100.0
    return out


def bollinger(close: np.ndarray, window: int = 20, num_std: float = 2.0):
    c = close.astype(float)
    mid = rolling_mean(c, window)
    out_std = np.full_like(c, np.nan, dtype=float)
    if len(c) >= window:
        for i in range(window - 1, len(c)):
            w = c[i - window + 1 : i + 1]
            out_std[i] = float(np.nanstd(w))
    upper = mid + num_std * out_std
    lower = mid - num_std * out_std
    return mid, upper, lower


def kdj(high: np.ndarray, low: np.ndarray, close: np.ndarray, n: int = 9, k_smooth: int = 3, d_smooth: int = 3):
    h = high.astype(float)
    l = low.astype(float)
    c = close.astype(float)
    rsv = np.full_like(c, np.nan, dtype=float)
    for i in range(len(c)):
        start = max(0, i - n + 1)
        hh = np.nanmax(h[start : i + 1])
        ll = np.nanmin(l[start : i + 1])
        denom = hh - ll
        if denom == 0 or not math.isfinite(float(denom)):
            rsv[i] = 50.0
        else:
            rsv[i] = (c[i] - ll) / denom * 100.0

    k = np.full_like(c, np.nan, dtype=float)
    d = np.full_like(c, np.nan, dtype=float)
    k[0] = 50.0
    d[0] = 50.0
    for i in range(1, len(c)):
        k[i] = (k[i - 1] * (k_smooth - 1) + rsv[i]) / k_smooth
        d[i] = (d[i - 1] * (d_smooth - 1) + k[i]) / d_smooth
    j = 3 * k - 2 * d
    return k, d, j


def macd(close: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9):
    c = close.astype(float)
    ema_fast = ema(c, fast)
    ema_slow = ema(c, slow)
    dif = ema_fast - ema_slow
    dea = ema(dif, signal)
    hist = dif - dea
    return dif, dea, hist


def true_range(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    h = high.astype(float)
    l = low.astype(float)
    c = close.astype(float)
    prev_close = np.roll(c, 1)
    prev_close[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - prev_close), np.abs(l - prev_close)))
    return tr


def adx(high: np.ndarray, low: np.ndarray, close: np.ndarray, window: int = 14) -> np.ndarray:
    h = high.astype(float)
    l = low.astype(float)
    c = close.astype(float)
    if len(c) == 0:
        return np.array([], dtype=float)

    up_move = np.diff(h, prepend=h[0])
    down_move = -np.diff(l, prepend=l[0])
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    tr = true_range(h, l, c)

    atr = rolling_mean(tr, window)
    plus_di = 100.0 * rolling_mean(plus_dm, window) / np.where(atr == 0, np.nan, atr)
    minus_di = 100.0 * rolling_mean(minus_dm, window) / np.where(atr == 0, np.nan, atr)
    dx = 100.0 * np.abs(plus_di - minus_di) / np.where((plus_di + minus_di) == 0, np.nan, (plus_di + minus_di))
    adx_arr = rolling_nanmean(dx, window, min_periods=window)
    return adx_arr


def local_extrema(values: np.ndarray, lookback: int = 5) -> Tuple[List[int], List[int]]:
    """
    Return (peaks, troughs) indices using a simple windowed extrema heuristic.
    """
    v = values.astype(float)
    peaks: List[int] = []
    troughs: List[int] = []
    for i in range(lookback, len(v) - lookback):
        window = v[i - lookback : i + lookback + 1]
        if not np.isfinite(v[i]):
            continue
        if v[i] == np.nanmax(window):
            peaks.append(i)
        if v[i] == np.nanmin(window):
            troughs.append(i)
    return peaks, troughs


def detect_divergence(price: np.ndarray, indicator: np.ndarray, lookback: int = 5):
    """
    Detect simple bullish/bearish divergence using last two peaks/troughs.
    Returns dict with flags and span days.
    """
    peaks_p, troughs_p = local_extrema(price, lookback=lookback)
    peaks_i, troughs_i = local_extrema(indicator, lookback=lookback)

    bearish = False
    bullish = False
    span = 0

    if len(peaks_p) >= 2 and len(peaks_i) >= 2:
        p1, p2 = peaks_p[-2], peaks_p[-1]
        i1, i2 = peaks_i[-2], peaks_i[-1]
        if price[p2] > price[p1] and indicator[i2] < indicator[i1]:
            bearish = True
            span = abs(p2 - p1)
    if len(troughs_p) >= 2 and len(troughs_i) >= 2:
        p1, p2 = troughs_p[-2], troughs_p[-1]
        i1, i2 = troughs_i[-2], troughs_i[-1]
        if price[p2] < price[p1] and indicator[i2] > indicator[i1]:
            bullish = True
            span = max(span, abs(p2 - p1))

    return {"bearish_divergence": bearish, "bullish_divergence": bullish, "span_days": int(span)}
