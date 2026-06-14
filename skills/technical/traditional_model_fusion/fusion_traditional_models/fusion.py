from __future__ import annotations

import itertools
from dataclasses import asdict
from typing import Dict, List, Tuple

from .types import ModelRun, Signal
from .utils import clamp


DEFAULT_WEIGHTS = {
    "advanced_trend_tracking_system": 0.35,
    "volume_price_momentum_analysis": 0.30,
    "oscillator_check": 0.25,
    "trend_application_dulling_divergence": 0.10,
}


def _signed(direction: str) -> int:
    if direction == "bullish":
        return 1
    if direction == "bearish":
        return -1
    return 0


def _risk_penalty(risk_level: str, needs_review: bool) -> float:
    penalty = 1.0
    if risk_level == "high":
        penalty *= 0.6
    elif risk_level == "medium":
        penalty *= 0.8
    if needs_review:
        penalty *= 0.6
    return penalty


def _agreement_matrix(runs: List[ModelRun]) -> Dict[str, Dict[str, bool]]:
    matrix: Dict[str, Dict[str, bool]] = {}
    for a in runs:
        matrix[a.name] = {}
        for b in runs:
            matrix[a.name][b.name] = (a.signal.get("direction") == b.signal.get("direction"))
    return matrix


def fuse_signals(
    model_signals: Dict[str, Signal],
    *,
    threshold: float = 0.6,
    base_weights: Dict[str, float] | None = None,
) -> Dict[str, object]:
    """
    Fuse four model signals into:
    - fused_signal (Signal JSON)
    - model_signals (with vote/weights)
    - validation_report (agreement/conflicts/gates/thresholds)
    """
    base_weights = dict(DEFAULT_WEIGHTS if base_weights is None else base_weights)

    gates_triggered: List[Dict[str, object]] = []
    conflicts: List[Dict[str, object]] = []

    # Extract for gating decisions.
    trend = model_signals.get("advanced_trend_tracking_system")
    osc = model_signals.get("oscillator_check")

    # Effective weights start as base.
    effective = dict(base_weights)

    # Gate 1: ADX<20 => trend output neutral and should downweight trend contribution.
    if trend:
        trend_meta = trend.get("meta") or {}
        adx_gate = (((trend_meta.get("sub_signals") or {}).get("adx14") or {}).get("gate")) if isinstance(trend_meta, dict) else None
        if adx_gate == "unavailable":
            gates_triggered.append(
                {
                    "gate": "adx_unavailable_no_trend_confirmation",
                    "reason": "趋势模块 ADX 不可用，趋势方向不参与确认",
                    "effective_weight": effective.get("advanced_trend_tracking_system", 0.0),
                }
            )
        if adx_gate == "ranging" or trend.get("direction") == "neutral" and "ADX<20" in (trend.get("reasoning") or ""):
            effective["advanced_trend_tracking_system"] = min(effective.get("advanced_trend_tracking_system", 0.0), 0.2)
            gates_triggered.append(
                {
                    "gate": "adx_ranging_downweight_trend",
                    "reason": "趋势模块判定震荡环境（ADX<20），趋势权重降到<=0.2",
                    "effective_weight": effective["advanced_trend_tracking_system"],
                }
            )

    # Gate 2: oscillator conflicts => force fused neutral/low confidence.
    force_neutral = False
    if osc and isinstance(osc.get("meta"), dict) and bool((osc["meta"]).get("needs_human_review")):
        # Only force neutral when oscillator itself says it has conflicts.
        if any("冲突" in u for u in ((osc["meta"]).get("uncertainties") or [])):
            force_neutral = True
            gates_triggered.append(
                {
                    "gate": "oscillator_conflict_force_neutral",
                    "reason": "震荡类指标多空冲突且 needs_human_review=true，融合层强制 neutral",
                }
            )

    # Vote computation.
    runs: List[ModelRun] = []
    total_vote = 0.0
    for name, sig in model_signals.items():
        base_w = float(base_weights.get(name, 0.0))
        eff_w = float(effective.get(name, base_w))
        direction = sig.get("direction", "neutral")
        confidence = float(sig.get("confidence", 0.0) or 0.0)
        meta = sig.get("meta") if isinstance(sig.get("meta"), dict) else {}
        risk_level = (meta or {}).get("risk_level", "medium")
        needs_review = bool((meta or {}).get("needs_human_review", False))
        adj = confidence * _risk_penalty(str(risk_level), needs_review)
        vote = eff_w * _signed(str(direction)) * adj
        notes: List[str] = []
        if eff_w != base_w:
            notes.append(f"weight gated: {base_w:.2f} -> {eff_w:.2f}")
        if needs_review:
            notes.append("needs_human_review=true (penalty applied)")
        if str(risk_level) in ("high", "medium"):
            notes.append(f"risk_level={risk_level} (penalty applied)")
        runs.append(ModelRun(name=name, signal=sig, base_weight=base_w, effective_weight=eff_w, vote=vote, notes=notes))
        total_vote += vote

    # Conflicts (pairwise).
    for a, b in itertools.combinations(runs, 2):
        da = a.signal.get("direction")
        db = b.signal.get("direction")
        if da in ("bullish", "bearish") and db in ("bullish", "bearish") and da != db:
            conflicts.append(
                {
                    "models": [a.name, b.name],
                    "directions": [da, db],
                    "notes": "方向冲突：一个看多一个看空",
                }
            )

    # Decide fused direction.
    if force_neutral:
        fused_direction = "neutral"
    else:
        fused_direction = "bullish" if total_vote >= threshold else "bearish" if total_vote <= -threshold else "neutral"

    # Confidence mapping: use magnitude of total_vote and model agreement.
    agreement = _agreement_matrix(runs)
    agreement_score = sum(1 for r in runs if r.signal.get("direction") == fused_direction) / max(1, len(runs))
    fused_conf = clamp(0.35 + min(1.0, abs(total_vote) / max(threshold, 1e-6)) * 0.35 + agreement_score * 0.2, 0.2, 0.92)
    if force_neutral:
        fused_conf = min(fused_conf, 0.45)

    # Risk aggregation: promote risk if any model says high/needs review.
    needs_review_any = any(bool((r.signal.get("meta") or {}).get("needs_human_review", False)) for r in runs if isinstance(r.signal.get("meta"), dict))
    risk_levels = [str((r.signal.get("meta") or {}).get("risk_level", "medium")) for r in runs if isinstance(r.signal.get("meta"), dict)]
    fused_risk = "high" if "high" in risk_levels else ("medium" if needs_review_any or "medium" in risk_levels else "low")

    # Compose fused Signal JSON.
    fused_signal: Signal = {
        "direction": fused_direction,
        "confidence": round(float(fused_conf), 4),
        "reasoning": f"加权投票 total_vote={total_vote:.4f}, threshold={threshold:.2f} => {fused_direction}。",
        "signals": [
            f"total_vote={total_vote:.4f}",
            f"threshold={threshold:.2f}",
            f"gates_triggered={len(gates_triggered)}",
            f"conflicts={len(conflicts)}",
        ],
        "source": "traditional_model_fusion_v0_1",
        "signal_type": "technical",
        "stock_code": str((next(iter(model_signals.values()), {}) or {}).get("stock_code", "")),
        "weight": 1.0,
        "meta": {
            "output_version": "0.1",
            "skill_name": "traditional_model_fusion_v0_1",
            "owner_group": "专家2组（指标）",
            "target": str((next(iter(model_signals.values()), {}) or {}).get("meta", {}).get("target", "")) if model_signals else "",
            "period": str((next(iter(model_signals.values()), {}) or {}).get("meta", {}).get("period", "")) if model_signals else "",
            "time_horizon": "mid",
            "risk_level": fused_risk,
            "key_findings": [
                "融合输出包含总信号 + 子信号 + 交叉验证报告。",
                "采用门控（ADX/冲突）+ 加权投票。",
            ],
            "evidence": [],
            "risk_notes": [],
            "uncertainties": [],
            "needs_human_review": bool(needs_review_any or force_neutral),
            "sub_signals": {
                "total_vote": total_vote,
                "threshold": threshold,
                "agreement_score": agreement_score,
            },
        },
    }

    out_model_signals = [
        {
            "name": r.name,
            "signal": r.signal,
            "base_weight": r.base_weight,
            "effective_weight": r.effective_weight,
            "vote": r.vote,
            "notes": r.notes,
        }
        for r in runs
    ]

    validation_report = {
        "agreement_matrix": agreement,
        "conflicts": conflicts,
        "gates_triggered": gates_triggered,
        "final_thresholds": {
            "threshold": threshold,
            "base_weights": base_weights,
            "effective_weights": effective,
        },
        "total_vote": total_vote,
    }

    return {"fused_signal": fused_signal, "model_signals": out_model_signals, "validation_report": validation_report}
