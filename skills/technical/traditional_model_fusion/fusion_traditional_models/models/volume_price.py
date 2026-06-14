from __future__ import annotations

import math
from pathlib import Path
from typing import List

import numpy as np

from ..types import OhlcvRow, Signal
from ..utils import clamp, finite_or, to_iso_date


SKILL_NAME = "volume_price_momentum_analysis"
OWNER_GROUP = "专家2组（指标）"


def _col(rows: List[OhlcvRow], key: str) -> np.ndarray:
    return np.asarray([float(rows[i].get(key, math.nan)) for i in range(len(rows))], dtype=float)


def compute_obv(close: np.ndarray, volume: np.ndarray) -> np.ndarray:
    out = np.zeros_like(close, dtype=float)
    for i in range(1, len(close)):
        if close[i] > close[i - 1]:
            out[i] = out[i - 1] + volume[i]
        elif close[i] < close[i - 1]:
            out[i] = out[i - 1] - volume[i]
        else:
            out[i] = out[i - 1]
    return out


def compute_adl(high: np.ndarray, low: np.ndarray, close: np.ndarray, volume: np.ndarray) -> np.ndarray:
    out = np.zeros_like(close, dtype=float)
    for i in range(len(close)):
        denom = high[i] - low[i]
        if denom == 0 or not math.isfinite(float(denom)):
            mfm = 0.0
        else:
            mfm = ((close[i] - low[i]) - (high[i] - close[i])) / denom
        mfv = mfm * volume[i]
        out[i] = out[i - 1] + mfv if i > 0 else mfv
    return out


def compute_cmf(high: np.ndarray, low: np.ndarray, close: np.ndarray, volume: np.ndarray, window: int = 20) -> np.ndarray:
    mfm = np.zeros_like(close, dtype=float)
    for i in range(len(close)):
        denom = high[i] - low[i]
        if denom == 0 or not math.isfinite(float(denom)):
            mfm[i] = 0.0
        else:
            mfm[i] = ((close[i] - low[i]) - (high[i] - close[i])) / denom
    mfv = mfm * volume
    out = np.full_like(close, np.nan, dtype=float)
    for i in range(window - 1, len(close)):
        v_sum = float(np.nansum(volume[i - window + 1 : i + 1]))
        if v_sum == 0:
            out[i] = 0.0
        else:
            out[i] = float(np.nansum(mfv[i - window + 1 : i + 1]) / v_sum)
    return out


def compute_vwap(high: np.ndarray, low: np.ndarray, close: np.ndarray, volume: np.ndarray) -> np.ndarray:
    tp = (high + low + close) / 3.0
    cum_v = np.cumsum(volume)
    cum_tpv = np.cumsum(tp * volume)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where(cum_v == 0, np.nan, cum_tpv / cum_v)
    return out


def _slope(values: np.ndarray, window: int = 20) -> float:
    arr = values[np.isfinite(values)]
    if len(arr) < 2:
        return 0.0
    tail = arr[-min(window, len(arr)) :]
    x = np.arange(len(tail), dtype=float)
    return float(np.polyfit(x, tail, 1)[0])


def _cmf_zone(cmf_value: float):
    if cmf_value > 0.25:
        return "strong_inflow", "强势流入"
    if cmf_value > 0.05:
        return "mild_inflow", "温和流入"
    if cmf_value >= -0.05:
        return "neutral", "中性"
    if cmf_value >= -0.25:
        return "mild_outflow", "温和流出"
    return "strong_outflow", "强势流出"


def analyze(rows: List[OhlcvRow], stock_code: str = "", target: str = "", source_name: str = "uploaded") -> Signal:
    if not rows or len(rows) < 2:
        return {
            "direction": "neutral",
            "confidence": 0.25,
            "reasoning": "OHLCV 数据不足，无法计算量价指标。",
            "signals": ["数据不足"],
            "source": SKILL_NAME,
            "signal_type": "technical",
            "stock_code": stock_code,
            "weight": 1.0,
            "meta": {
                "output_version": "0.1",
                "skill_name": SKILL_NAME,
                "owner_group": OWNER_GROUP,
                "target": target or stock_code,
                "period": "",
                "time_horizon": "mid",
                "risk_level": "high",
                "key_findings": ["数据不足"],
                "evidence": [],
                "risk_notes": ["数据不足导致结论不可用"],
                "uncertainties": ["rows 数量不足"],
                "needs_human_review": True,
            },
        }

    high = _col(rows, "high")
    low = _col(rows, "low")
    close = _col(rows, "close")
    volume = _col(rows, "volume")
    dates = [to_iso_date(r.get("date")) for r in rows]

    uncertainties: List[str] = []
    risk_notes: List[str] = []
    needs_review = False

    required_arrays = {"high": high, "low": low, "close": close, "volume": volume}
    invalid_fields = [name for name, arr in required_arrays.items() if np.isnan(arr).any()]
    if invalid_fields:
        uncertainties.append(f"必填字段存在缺失或非数字：{', '.join(invalid_fields)}。")
        needs_review = True

    zero_volume_count = int(np.sum(volume == 0))
    if zero_volume_count:
        uncertainties.append(f"存在 {zero_volume_count} 个成交量为 0 的交易日，强信号需谨慎。")
        needs_review = True

    obv = compute_obv(close, volume)
    adl = compute_adl(high, low, close, volume)
    cmf = compute_cmf(high, low, close, volume, window=20)
    vwap = compute_vwap(high, low, close, volume)

    last_close = float(close[-1])
    last_volume = float(volume[-1])
    last_obv = float(obv[-1])
    last_adl = float(adl[-1])
    last_vwap = float(vwap[-1]) if len(vwap) else math.nan
    cmf_last = float(cmf[-1]) if len(cmf) and math.isfinite(float(cmf[-1])) else 0.0
    cmf_zone, cmf_label = _cmf_zone(cmf_last)

    price_slope = _slope(close)
    obv_slope = _slope(obv)
    adl_slope = _slope(adl)
    vwap_deviation = (last_close - last_vwap) / last_vwap if math.isfinite(last_vwap) and last_vwap != 0 else 0.0

    score = 0
    sub_signals = {}
    signals: List[str] = []
    key_findings: List[str] = []

    obv_score = 1 if obv_slope > 0 and price_slope >= 0 else -1 if obv_slope < 0 and price_slope <= 0 else 0
    sub_signals["obv"] = {"direction": "bullish" if obv_score > 0 else "bearish" if obv_score < 0 else "neutral", "slope_20d": round(obv_slope, 2)}
    score += obv_score

    adl_score = 1 if adl_slope > 0 and price_slope >= 0 else -1 if adl_slope < 0 and price_slope <= 0 else 0
    sub_signals["ad_line"] = {"direction": "bullish" if adl_score > 0 else "bearish" if adl_score < 0 else "neutral", "slope_20d": round(adl_slope, 2)}
    score += adl_score

    vwap_score = 1 if vwap_deviation > 0.02 else -1 if vwap_deviation < -0.02 else 0
    sub_signals["vwap"] = {"direction": "bullish" if vwap_score > 0 else "bearish" if vwap_score < 0 else "neutral", "deviation_pct": round(vwap_deviation * 100, 2)}
    score += vwap_score

    cmf_score = 1 if cmf_last > 0.05 else -1 if cmf_last < -0.05 else 0
    sub_signals["cmf"] = {"direction": "bullish" if cmf_score > 0 else "bearish" if cmf_score < 0 else "neutral", "latest_value": round(cmf_last, 4), "zone": cmf_zone}
    score += cmf_score

    bullish_count = sum(1 for item in sub_signals.values() if item["direction"] == "bullish")
    bearish_count = sum(1 for item in sub_signals.values() if item["direction"] == "bearish")
    direction = "bullish" if score > 1 else "bearish" if score < -1 else "neutral"

    if bullish_count >= 3:
        signals.append("多指标共振偏多")
        key_findings.append("OBV/A-D/VWAP/CMF 至少 3 项偏多。")
    elif bearish_count >= 3:
        signals.append("多指标共振偏空")
        key_findings.append("OBV/A-D/VWAP/CMF 至少 3 项偏空。")
    else:
        signals.append("指标信号分化")
        key_findings.append("量价指标未形成三指标同向共振。")
        if bullish_count and bearish_count:
            uncertainties.append("存在多空指标冲突，需结合价格位置复核。")
            needs_review = True

    signals.append("价格围绕VWAP" if abs(vwap_deviation) <= 0.02 else ("价格站上VWAP" if vwap_deviation > 0 else "价格跌破VWAP"))
    signals.append(f"CMF{cmf_label}")

    if abs(cmf_last) > 0.5:
        risk_notes.append("CMF 出现极端值，需检查异常成交或口径问题。")
        needs_review = True
    if abs(vwap_deviation) > 0.05:
        risk_notes.append("收盘价相对 VWAP 偏离 >5%，短期过热/超跌风险。")
        needs_review = True

    risk_level = "high" if risk_notes else ("medium" if needs_review else "low")

    confidence = 0.45 + abs(score) * 0.1
    if max(bullish_count, bearish_count) >= 3:
        confidence += 0.1
    if needs_review:
        confidence -= 0.1
    confidence = clamp(confidence, 0.25, 0.95)

    period = f"{dates[0]} 至 {dates[-1]}" if dates else f"{len(rows)} rows"
    reasoning = f"量价指标综合：{bullish_count} 项偏多、{bearish_count} 项偏空，综合判断为 {direction}。"

    evidence_date = dates[-1] if dates else ""
    evidence = [
        {"source_type": "market_data", "source_name": source_name, "date": evidence_date, "metric": "close", "value": str(round(last_close, 4)), "comparison": "latest", "note": "最新收盘价"},
        {"source_type": "market_data", "source_name": source_name, "date": evidence_date, "metric": "volume", "value": str(round(last_volume, 4)), "comparison": "latest", "note": "最新成交量"},
        {"source_type": "market_data", "source_name": source_name, "date": evidence_date, "metric": "OBV", "value": str(round(last_obv, 4)), "comparison": f"20d slope={obv_slope:.2f}", "note": "OBV 趋势"},
        {"source_type": "market_data", "source_name": source_name, "date": evidence_date, "metric": "A/D Line", "value": str(round(last_adl, 4)), "comparison": f"20d slope={adl_slope:.2f}", "note": "A/D 趋势"},
        {"source_type": "market_data", "source_name": source_name, "date": evidence_date, "metric": "VWAP", "value": str(round(last_vwap, 4)) if math.isfinite(last_vwap) else "", "comparison": f"deviation={vwap_deviation*100:.2f}%", "note": "VWAP 偏离"},
        {"source_type": "market_data", "source_name": source_name, "date": evidence_date, "metric": "CMF(20)", "value": str(round(cmf_last, 4)), "comparison": cmf_label, "note": "资金流强弱"},
    ]

    return {
        "direction": direction,
        "confidence": round(float(confidence), 4),
        "reasoning": reasoning,
        "signals": signals,
        "source": SKILL_NAME,
        "signal_type": "technical",
        "stock_code": stock_code,
        "weight": 1.0,
        "meta": {
            "output_version": "0.1",
            "skill_name": SKILL_NAME,
            "owner_group": OWNER_GROUP,
            "target": target or stock_code,
            "period": period,
            "time_horizon": "mid",
            "risk_level": risk_level,
            "key_findings": key_findings,
            "evidence": evidence,
            "risk_notes": risk_notes,
            "uncertainties": uncertainties,
            "needs_human_review": needs_review,
            "sub_signals": sub_signals,
        },
    }

