from agents.orchestrator.arbitration import ArbitrationEngine
from agents.signal import SignalBundle, bullish_signal


def test_arbitration_engine_handles_single_signal_bundle():
    bundle = SignalBundle(stock_code="000001")
    bundle.add(
        bullish_signal(
            confidence=0.8,
            reasoning="single high-confidence contract signal",
            signals=["contract"],
            source="ContractTestAgent",
            stock_code="000001",
            signal_type="financial",
        )
    )

    result = ArbitrationEngine().arbitrate(bundle)

    assert result.signals_summary["total"] == 1
    assert result.signals_summary["bullish"] == 1
    assert result.reasoning_chain
    assert result.decision in {"buy", "hold", "sell", "wait"}
