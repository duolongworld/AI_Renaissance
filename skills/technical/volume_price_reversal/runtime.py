"""Runtime adapter for the volume-price reversal technical skill."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional


def run_volume_price_reversal(
    stock_code: str,
    rows: List[Dict[str, Any]],
    data_status: str,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Execute deterministic volume-price reversal rules and return Signal-like dict."""
    config = config or {}
    uncertainties: List[str] = []
    evidence: List[Dict[str, Any]] = []
    if len(rows) < 60:
        uncertainties.append("历史数据不足 60 日，量价背离/反转信号可信度降低。")

    if not rows:
        return _neutral_skill_result(
            "缺少 OHLCV 行情，无法完成量价背离与反转分析。",
            weight=float(config.get("volume_price_reversal_weight", 0.35)),
            confidence=0.2,
            meta={"needs_human_review": True, "uncertainties": ["缺少行情数据"]},
        )

    latest = rows[-1]
    prev = rows[-2] if len(rows) >= 2 else latest
    close = _to_float(latest.get("close")) or 0.0
    prev_close = _to_float(prev.get("close")) or close
    volume = _to_float(latest.get("volume")) or 0.0
    high = _to_float(latest.get("high")) or close
    low = _to_float(latest.get("low")) or close
    open_value = _to_float(latest.get("open")) or close

    recent_20 = rows[-20:] if len(rows) >= 20 else rows
    prev_20 = rows[-21:-1] if len(rows) >= 21 else rows[:-1]
    prev_60 = rows[-61:-1] if len(rows) >= 61 else rows[:-1]
    volumes_20 = [_to_float(r.get("volume")) or 0.0 for r in prev_20 if _to_float(r.get("volume")) is not None]
    volumes_60 = [_to_float(r.get("volume")) or 0.0 for r in prev_60 if _to_float(r.get("volume")) is not None]
    avg_volume_20 = sum(volumes_20) / len(volumes_20) if volumes_20 else volume
    std_volume_60 = _stddev(volumes_60) or max(avg_volume_20 * 0.25, 1.0)
    vol_surp = (volume - avg_volume_20) / std_volume_60 if std_volume_60 else 0.0
    latest_volume_meta = _volume_display_meta(volume, config, allow_decimal=latest.get("volume_raw_unit") == "股")
    avg_volume_20_meta = _volume_display_meta(avg_volume_20, config, allow_decimal=any(r.get("volume_raw_unit") == "股" for r in prev_20))

    closes = [_to_float(r.get("close")) or 0.0 for r in recent_20]
    high_20 = max(closes) if closes else close
    low_20 = min(closes) if closes else close
    is_new_high = close >= high_20 and len(recent_20) >= 10
    is_new_low = close <= low_20 and len(recent_20) >= 10
    day_return = (close - prev_close) / prev_close if prev_close else 0.0
    volume_ratio_20 = volume / avg_volume_20 if avg_volume_20 else 1.0

    full_range = max(high - low, 0.0)
    body = abs(close - open_value)
    upper_shadow = high - max(open_value, close)
    lower_shadow = min(open_value, close) - low
    range_ratio = full_range / prev_close if prev_close else 0.0
    upper_shadow_ratio = upper_shadow / full_range if full_range else 0.0
    lower_shadow_ratio = lower_shadow / full_range if full_range else 0.0
    long_upper_shadow = upper_shadow >= body * 2 and upper_shadow_ratio >= 0.5 and range_ratio >= 0.03
    long_lower_shadow = lower_shadow >= body * 2 and lower_shadow_ratio >= 0.5 and range_ratio >= 0.03
    is_doji = bool(full_range and body / full_range < 0.1 and upper_shadow_ratio >= 0.3 and lower_shadow_ratio >= 0.3)

    amount = _latest_amount(latest, config)
    avg_amount_20 = _average_amount(rows[-20:], config)
    amount_threshold = _amount_threshold(stock_code)
    needs_human_review = False
    if amount is None:
        uncertainties.append("成交额字段缺失，绝对成交额过滤器未执行。")
    elif amount < amount_threshold:
        uncertainties.append("绝对成交额不足，VolSurp 信号可能失真。")
    if avg_amount_20 is not None and avg_amount_20 < amount_threshold * 0.5:
        reasoning = "长期成交额低于分市场阈值的一半，量价反转框架不适用。"
        return _neutral_skill_result(
            reasoning,
            weight=float(config.get("volume_price_reversal_weight", 0.35)),
            confidence=0.25,
            meta={
                "needs_human_review": True,
                "risk_level": "high",
                "time_horizon": "short",
                "uncertainties": uncertainties + [reasoning],
                "evidence": evidence,
            },
        )

    direction = "neutral"
    confidence = 0.35
    risk_level = "medium"
    signals: List[str] = []
    key_findings: List[str] = []

    if is_doji:
        confidence = 0.45
        signals.append("十字星犹豫：实体极小且上下影线较长，等待次日方向选择")
        key_findings.append("高位/低位十字星，多空胶着，等待次日方向选择。")
    elif is_new_high and vol_surp < -1:
        direction = "bearish"
        confidence = 0.62 + (0.05 if vol_surp < -1.5 else 0.0)
        signals.append(f"形态一·顶背离：20日新高但缩量，VolSurp {vol_surp:.2f}")
    elif is_new_low and vol_surp < -1:
        direction = "bullish"
        confidence = 0.62 + (0.05 if vol_surp < -1.5 else 0.0)
        risk_level = "low"
        signals.append(f"形态二·底背离：20日新低但缩量，VolSurp {vol_surp:.2f}")
    elif day_return >= 0.05 and volume_ratio_20 >= 1.5 and long_upper_shadow:
        direction = "bearish"
        confidence = 0.82 if upper_shadow_ratio > 0.7 else 0.75
        risk_level = "high"
        signals.append(f"形态三·量价齐升乏力：涨幅 {day_return:.2%}，放量 {volume_ratio_20:.2f}x，长上影")
        key_findings.append("巨量长上影线信号须关注 A 股 T+1 与尾盘执行约束。")
    elif day_return <= -0.05 and volume_ratio_20 >= 1.5 and long_lower_shadow:
        direction = "bullish"
        confidence = 0.78 if lower_shadow_ratio > 0.7 else 0.70
        signals.append(f"形态四·量价齐跌衰竭：跌幅 {day_return:.2%}，放量 {volume_ratio_20:.2f}x，长下影")
        key_findings.append("放量大跌后承接信号受 T+1 制度约束，需预留次日波动缓冲。")
    else:
        signals.append("无明确量价背离或反转形态触发")
        if abs(day_return) >= 0.05 and -1 <= vol_surp <= 1:
            uncertainties.append("价格大幅波动但量能无明显异常，反转信号可信度偏低。")

    if amount is not None and amount < amount_threshold:
        confidence = max(0.2, confidence - 0.1)
    if len(rows) < 60:
        confidence = min(confidence, 0.3 if direction == "neutral" else 0.55)
        needs_human_review = True

    evidence.extend(
        [
            {
                "source_type": "market_data",
                "source_name": data_status,
                "date": latest.get("date", ""),
                "metric": "VolSurp（异常成交量 Z 分数）",
                "value": round(vol_surp, 4),
                "comparison": f"今日成交量 {latest_volume_meta['display']} vs 20日均量 {avg_volume_20_meta['display']}",
                "note": _volume_surprise_note(vol_surp),
            },
            {
                "source_type": "market_data",
                "source_name": data_status,
                "date": latest.get("date", ""),
                "metric": "日涨跌幅 / 20日位置",
                "value": f"{day_return:.2%}",
                "comparison": f"20日高点 {high_20:.4f} / 低点 {low_20:.4f}",
                "note": "价格处于20日新高/新低位置" if is_new_high or is_new_low else "",
            },
            {
                "source_type": "market_data",
                "source_name": data_status,
                "date": latest.get("date", ""),
                "metric": "影线占振幅",
                "value": {"upper_shadow_ratio": round(upper_shadow_ratio, 4), "lower_shadow_ratio": round(lower_shadow_ratio, 4)},
                "comparison": "长影线需满足影线≥实体2倍、影线/振幅≥50%、振幅/昨收≥3%",
                "note": _shadow_note(upper_shadow_ratio, lower_shadow_ratio, long_upper_shadow, long_lower_shadow),
            },
        ]
    )

    reasoning = "；".join(signals)
    if uncertainties:
        reasoning += "；不确定性：" + "；".join(uncertainties[:2])
    return {
        "skill_name": "volume_price_reversal",
        "direction": direction,
        "confidence": _clamp(confidence),
        "reasoning": reasoning,
        "signals": signals,
        "weight": float(config.get("volume_price_reversal_weight", 0.35)),
        "meta": {
            "skill_name": "volume_price_reversal",
            "output_version": "0.1-runtime",
            "time_horizon": "short",
            "risk_level": risk_level,
            "key_findings": key_findings,
            "evidence": evidence,
            "metrics": {
                "day_return": day_return,
                "latest_volume": volume,
                "latest_volume_display": latest_volume_meta["display"],
                "latest_volume_shares": latest_volume_meta["shares"],
                "avg_volume_20": avg_volume_20,
                "avg_volume_20_display": avg_volume_20_meta["display"],
                "avg_volume_20_shares": avg_volume_20_meta["shares"],
                "volume_unit": latest_volume_meta["unit"],
                "volume_share_multiplier": latest_volume_meta["share_multiplier"],
                "volume_ratio_20": volume_ratio_20,
                "vol_surp": vol_surp,
                "amount": amount,
                "avg_amount_20": avg_amount_20,
                "amount_threshold": amount_threshold,
            },
            "uncertainties": uncertainties,
            "needs_human_review": needs_human_review,
        },
    }


def _neutral_skill_result(reasoning: str, weight: float, confidence: float, meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {"skill_name": "volume_price_reversal", "direction": "neutral", "confidence": _clamp(confidence), "reasoning": reasoning, "signals": [reasoning], "weight": weight, "meta": {"skill_name": "volume_price_reversal", **(meta or {})}}


def _to_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _stddev(values: List[float]) -> float:
    clean = [v for v in values if v is not None]
    if len(clean) < 2:
        return 0.0
    mean = sum(clean) / len(clean)
    variance = sum((value - mean) ** 2 for value in clean) / (len(clean) - 1)
    return math.sqrt(max(variance, 0.0))


def _latest_amount(row: Dict[str, Any], config: Dict[str, Any]) -> Optional[float]:
    amount = _to_float(row.get("amount") or row.get("turnover") or row.get("money"))
    if amount is not None:
        return amount
    close = _to_float(row.get("close"))
    volume = _to_float(row.get("volume"))
    if close is None or volume is None:
        return None
    return close * volume * float(config.get("volume_amount_multiplier", 100.0))


def _average_amount(rows: List[Dict[str, Any]], config: Dict[str, Any]) -> Optional[float]:
    clean = [amount for amount in (_latest_amount(row, config) for row in rows) if amount is not None]
    return sum(clean) / len(clean) if clean else None


def _amount_threshold(stock_code: str) -> float:
    code = (stock_code or "").strip()
    if code.startswith(("688", "300")):
        return 50_000_000.0
    if code.startswith(("83", "87", "92")):
        return 20_000_000.0
    return 100_000_000.0


def _volume_display_meta(volume: float, config: Dict[str, Any], *, allow_decimal: bool = False) -> Dict[str, Any]:
    share_multiplier = float(config.get("volume_amount_multiplier", 100.0))
    configured_unit = str(config.get("volume_unit", "")).strip()
    if configured_unit:
        unit = configured_unit
    elif abs(share_multiplier - 100.0) < 1e-9:
        unit = "手"
    elif abs(share_multiplier - 1.0) < 1e-9:
        unit = "股"
    else:
        unit = f"原始单位×{share_multiplier:g}股"
    shares = volume * share_multiplier
    if unit == "手":
        hand_display = f"{volume:,.2f}" if allow_decimal and abs(volume - round(volume)) >= 1e-9 else f"{volume:,.0f}"
        display = f"{hand_display}手（{shares:,.0f}股）"
    elif unit == "股":
        display = f"{volume:,.0f}股"
    else:
        display = f"{volume:,.0f}{unit}（折合{shares:,.0f}股）"
    return {"raw": volume, "unit": unit, "share_multiplier": share_multiplier, "shares": shares, "display": display}


def _volume_surprise_note(vol_surp: float) -> str:
    if vol_surp > 3:
        return "巨量：极端放量，量能远超正常水平，方向需结合 K 线形态判断。"
    if vol_surp > 2:
        return "爆量：今日成交量显著高于均量，配合大涨/大跌时反转概率上升。"
    if vol_surp > 1:
        return "温和放量：成交量适度增加，多空换手活跃度提升。"
    if vol_surp < -1.5:
        return "地量：极端缩量，市场惜售/惜买达到极致。"
    if vol_surp < -1:
        return "缩量：成交量明显萎缩，配合创新高/新低时触发顶/底背离观察。"
    return ""


def _shadow_note(upper_shadow_ratio: float, lower_shadow_ratio: float, long_upper_shadow: bool, long_lower_shadow: bool) -> str:
    if long_upper_shadow:
        return f"{'极端长上影线' if upper_shadow_ratio > 0.7 else '标准长上影线'}：全天波动中较大比例被抛压打回，构成潜在顶部反转信号。"
    if long_lower_shadow:
        return f"{'极端长下影线' if lower_shadow_ratio > 0.7 else '标准长下影线'}：全天波动中较大比例被买盘拉回，构成潜在底部承接信号。"
    return ""


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    if math.isnan(value) or math.isinf(value):
        return lower
    return max(lower, min(upper, value))
