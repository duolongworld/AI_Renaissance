import math
import random
import sys
import unittest
from pathlib import Path


FUSION_ROOT = Path(__file__).resolve().parents[2] / "skills" / "technical" / "traditional_model_fusion"
if str(FUSION_ROOT) not in sys.path:
    sys.path.insert(0, str(FUSION_ROOT))

from fusion_traditional_models.fusion import fuse_signals  # noqa: E402
from fusion_traditional_models.models.oscillator import analyze as analyze_osc  # noqa: E402
from fusion_traditional_models.models.trend_application import analyze as analyze_trend_app  # noqa: E402
from fusion_traditional_models.models.trend_tracking import analyze as analyze_trend  # noqa: E402
from fusion_traditional_models.models.volume_price import analyze as analyze_volume  # noqa: E402


def _signal(direction: str, confidence: float, *, risk_level: str = "low", needs_review: bool = False):
    return {
        "direction": direction,
        "confidence": float(confidence),
        "reasoning": "",
        "signals": [],
        "source": "x",
        "signal_type": "technical",
        "stock_code": "000001",
        "weight": 1.0,
        "meta": {
            "risk_level": risk_level,
            "needs_human_review": needs_review,
            "uncertainties": [],
            "sub_signals": {},
            "target": "000001",
            "period": "2026-01-01 至 2026-05-01",
        },
    }


def _make_rows(n: int, seed: int = 7):
    random.seed(seed)
    rows = []
    price = 100.0
    for i in range(n):
        price = max(1.0, price + 0.05 + (random.random() - 0.5) * 0.8)
        rows.append(
            {
                "date": f"2026-01-{(i % 28) + 1:02d}",
                "open": price * (1.0 + (random.random() - 0.5) * 0.002),
                "high": price * 1.005,
                "low": price * 0.995,
                "close": price,
                "volume": float(1_000_000 + int((random.random() - 0.5) * 200_000)),
            }
        )
    return rows


class TestFusionLogic(unittest.TestCase):
    def test_all_bullish_outputs_bullish(self):
        model_signals = {
            "advanced_trend_tracking_system": _signal("bullish", 0.85),
            "volume_price_momentum_analysis": _signal("bullish", 0.85),
            "oscillator_check": _signal("bullish", 0.85),
            "trend_application_dulling_divergence": _signal("bullish", 0.65),
        }
        out = fuse_signals(model_signals, threshold=0.6)
        self.assertEqual(out["fused_signal"]["direction"], "bullish")

    def test_adx_gate_downweights_trend(self):
        trend = _signal("neutral", 0.2)
        trend["reasoning"] = "ADX<20，判定为震荡环境，趋势模块输出 neutral（门控）。"
        trend["meta"]["sub_signals"] = {"adx14": {"gate": "ranging"}}
        model_signals = {
            "advanced_trend_tracking_system": trend,
            "volume_price_momentum_analysis": _signal("bullish", 0.9),
            "oscillator_check": _signal("bullish", 0.7),
            "trend_application_dulling_divergence": _signal("neutral", 0.4, risk_level="medium", needs_review=True),
        }
        out = fuse_signals(model_signals, threshold=0.6)
        self.assertTrue(any(g.get("gate") == "adx_ranging_downweight_trend" for g in out["validation_report"]["gates_triggered"]))

    def test_conflict_reported_and_neutral_when_vote_small(self):
        model_signals = {
            "advanced_trend_tracking_system": _signal("bullish", 0.9),
            "volume_price_momentum_analysis": _signal("bullish", 0.9),
            "oscillator_check": _signal("bearish", 0.9),
            "trend_application_dulling_divergence": _signal("neutral", 0.4),
        }
        out = fuse_signals(model_signals, threshold=0.6)
        self.assertEqual(out["fused_signal"]["direction"], "neutral")
        self.assertGreaterEqual(len(out["validation_report"]["conflicts"]), 1)

    def test_high_risk_propagates_to_fused(self):
        model_signals = {
            "advanced_trend_tracking_system": _signal("neutral", 0.3, risk_level="medium", needs_review=True),
            "volume_price_momentum_analysis": _signal("bullish", 0.8),
            "oscillator_check": _signal("neutral", 0.4, risk_level="medium", needs_review=True),
            "trend_application_dulling_divergence": _signal("neutral", 0.3, risk_level="high", needs_review=True),
        }
        out = fuse_signals(model_signals, threshold=0.6)
        self.assertEqual(out["fused_signal"]["meta"]["risk_level"], "high")
        self.assertTrue(out["fused_signal"]["meta"]["needs_human_review"])


class TestModelOutputs(unittest.TestCase):
    def test_volume_price_schema_minimal(self):
        sig = analyze_volume(_make_rows(10), stock_code="000001", target="t", source_name="x.csv")
        self.assertIn("direction", sig)
        self.assertIn("confidence", sig)
        self.assertIsInstance(sig["meta"], dict)

    def test_oscillator_requires_30(self):
        sig = analyze_osc(_make_rows(20))
        self.assertEqual(sig["direction"], "neutral")
        self.assertTrue(sig["meta"]["needs_human_review"])

    def test_trend_requires_60(self):
        sig = analyze_trend(_make_rows(40))
        self.assertEqual(sig["direction"], "neutral")
        self.assertTrue(sig["meta"]["needs_human_review"])

    def test_trend_app_requires_30(self):
        sig = analyze_trend_app(_make_rows(20))
        self.assertEqual(sig["direction"], "neutral")
        self.assertTrue(sig["meta"]["needs_human_review"])

    def test_volume_price_marks_missing_volume(self):
        rows = _make_rows(80)
        rows[-1]["volume"] = math.nan
        sig = analyze_volume(rows)
        self.assertTrue(sig["meta"]["needs_human_review"])
        self.assertIn("volume", " ".join(sig["meta"].get("uncertainties", [])))

