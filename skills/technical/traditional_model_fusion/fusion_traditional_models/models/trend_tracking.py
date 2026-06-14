from __future__ import annotations

import math
from typing import List

import numpy as np

from ..types import OhlcvRow, Signal
from ..utils import adx, clamp, macd, rolling_mean, to_iso_date


SKILL_NAME = "advanced_trend_tracking_system"
OWNER_GROUP = "专家2组（技术分析）"


def _col(rows: List[OhlcvRow], key: str) -> np.ndarray:
    return np.asarray([float(rows[i].get(key, math.nan)) for i in range(len(rows))], dtype=float)


def analyze(rows: List[OhlcvRow], stock_code: str = "", target: str = "", source_name: str = "uploaded") -> Signal:
    if not rows or len(rows) < 60:
        return {
            "direction": "neutral",
            "confidence": 0.25,
            "reasoning": "数据不足（<60 根），无法完整计算趋势系统（ADX/MA/MACD）。",
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
                "risk_notes": ["数据不足"],
                "uncertainties": ["rows<60"],
                "needs_human_review": True,
            },
        }

    high = _col(rows, "high")
    low = _col(rows, "low")
    close = _col(rows, "close")
    dates = [to_iso_date(r.get("date")) for r in rows]
    evidence_date = dates[-1] if dates else ""

    uncertainties: List[str] = []
    risk_notes: List[str] = []
    needs_review = False
    signals: List[str] = []
    key_findings: List[str] = []

    adx14 = adx(high, low, close, window=14)
    last_adx = float(adx14[-1]) if len(adx14) else math.nan
    if not math.isfinite(last_adx):
        uncertainties.append("ADX 计算结果为空/非数值，可能是数据口径问题。")
        needs_review = True
        signals.append("ADX不可用，趋势环境无法确认")
        key_findings.append("ADX不可用：趋势模块不参与方向确认。")
        return {
            "direction": "neutral",
            "confidence": 0.15,
            "reasoning": "ADX不可用，无法区分趋势/震荡环境，趋势模块输出 neutral。",
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
                "period": f"{dates[0]} 至 {dates[-1]}",
                "time_horizon": "mid",
                "risk_level": "high",
                "key_findings": key_findings,
                "evidence": [
                    {"source_type": "market_data", "source_name": source_name, "date": evidence_date, "metric": "ADX(14)", "value": "", "comparison": "unavailable", "note": "ADX计算不可用，不能触发震荡门控"},
                ],
                "risk_notes": ["趋势环境未确认，需人工复核。"],
                "uncertainties": uncertainties,
                "needs_human_review": True,
                "sub_signals": {"adx14": {"latest_value": None, "gate": "unavailable"}},
            },
        }

    # Gate: ADX < 20 => ranging -> neutral
    if last_adx < 20:
        signals.append(f"ADX={last_adx:.1f}<20 震荡环境，趋势信号门控为 neutral")
        key_findings.append("ADX<20：按规范禁止趋势方向交易信号。")
        return {
            "direction": "neutral",
            "confidence": 0.2,
            "reasoning": "ADX<20，判定为震荡环境，趋势模块输出 neutral（门控）。",
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
                "period": f"{dates[0]} 至 {dates[-1]}",
                "time_horizon": "mid",
                "risk_level": "low",
                "key_findings": key_findings,
                "evidence": [
                    {"source_type": "market_data", "source_name": source_name, "date": evidence_date, "metric": "ADX(14)", "value": f"{last_adx:.2f}", "comparison": "<20", "note": "环境门控：震荡"},
                ],
                "risk_notes": [],
                "uncertainties": uncertainties,
                "needs_human_review": needs_review,
                "sub_signals": {"adx14": {"latest_value": round(last_adx, 2), "gate": "ranging"}},
            },
        }

    # Baseline MA(60)
    ma60 = rolling_mean(close.astype(float), 60)
    last_ma60 = float(ma60[-1]) if len(ma60) else math.nan
    last_close = float(close[-1])
    above_ma60 = math.isfinite(last_ma60) and last_close >= last_ma60

    # Momentum MACD
    dif, dea, hist = macd(close, 12, 26, 9)
    macd_bull = dif[-1] > dea[-1]
    macd_bear = dif[-1] < dea[-1]

    # Direction logic (simplified):
    direction = "neutral"
    score = 0
    if above_ma60:
        score += 1
        signals.append("价格站上MA(60)")
    else:
        score -= 1
        signals.append("价格低于MA(60)")
    if macd_bull:
        score += 1
        signals.append("MACD 多头（DIF>DEA）")
    elif macd_bear:
        score -= 1
        signals.append("MACD 空头（DIF<DEA）")

    if score >= 2:
        direction = "bullish"
        key_findings.append("趋势环境有效（ADX>=20），方向与动能一致偏多。")
    elif score <= -2:
        direction = "bearish"
        key_findings.append("趋势环境有效（ADX>=20），方向与动能一致偏空。")
    else:
        direction = "neutral"
        key_findings.append("趋势环境有效但方向/动能不一致，保持中性。")
        needs_review = True
        uncertainties.append("趋势方向与动能信号不一致，建议人工复核。")

    # SAR/Ichimoku defense: v0.1 implement as risk notes only (no full calc)
    risk_notes.append("v0.1：SAR/Ichimoku 作为防守层仅输出风险提示，未做完整形态判读。")
    needs_review = True

    # Confidence: transition band ADX 20-25 -> downweight
    confidence = 0.7 if direction != "neutral" else 0.45
    if 20 <= last_adx < 25:
        confidence *= 0.5
        signals.append("ADX处于过渡区(20-25)，按规范降权")
    if needs_review:
        confidence -= 0.1
    confidence = clamp(confidence, 0.25, 0.92)

    risk_level = "medium" if needs_review else "low"

    evidence = [
        {"source_type": "market_data", "source_name": source_name, "date": evidence_date, "metric": "ADX(14)", "value": f"{last_adx:.2f}", "comparison": ">=20", "note": "趋势环境有效"},
        {"source_type": "market_data", "source_name": source_name, "date": evidence_date, "metric": "MA(60)", "value": "" if not math.isfinite(last_ma60) else f"{last_ma60:.4f}", "comparison": "Price vs MA60", "note": "方向基准"},
        {"source_type": "market_data", "source_name": source_name, "date": evidence_date, "metric": "MACD(DIF,DEA,HIST)", "value": f"{float(dif[-1]):.4f},{float(dea[-1]):.4f},{float(hist[-1]):.4f}", "comparison": "DIF ? DEA", "note": "动能判定"},
    ]

    period = f"{dates[0]} 至 {dates[-1]}" if dates else ""
    reasoning = f"ADX={last_adx:.1f}，MA60与MACD打分={score}，输出 {direction}。"

    return {
        "direction": direction,
        "confidence": round(float(confidence), 4),
        "reasoning": reasoning,
        "signals": signals[:12],
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
            "sub_signals": {
                "adx14": {"latest_value": round(last_adx, 2)},
                "ma60": {"latest_value": round(last_ma60, 4) if math.isfinite(last_ma60) else None, "above": bool(above_ma60)},
                "macd": {"dif": round(float(dif[-1]), 4), "dea": round(float(dea[-1]), 4), "hist": round(float(hist[-1]), 4)},
            },
        },
    }
