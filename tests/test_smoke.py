from agents.financial.agent import FinancialAgent
from agents.orchestrator.arbitration import ArbitrationEngine
from agents.signal import SignalBundle, bullish_signal


def test_financial_agent_returns_signal():
    agent = FinancialAgent(config={})
    signal = agent.analyze("000001")

    assert signal.source == "财务分析Agent"
    assert signal.signal_type == "financial"
    assert signal.direction in {"bullish", "bearish", "neutral"}


def test_arbitration_engine_handles_single_signal_bundle():
    bundle = SignalBundle(stock_code="000001")
    bundle.add(
        bullish_signal(
            confidence=0.8,
            reasoning="single high-confidence smoke signal",
            signals=["smoke"],
            source="SmokeTestAgent",
            stock_code="000001",
            signal_type="financial",
        )
    )

    result = ArbitrationEngine().arbitrate(bundle)
    expected_summary = "📊 信号汇总：共1个信号，看多1个，看空0个，中性0个"

    assert result.signals_summary["total"] == 1
    assert result.reasoning_chain[0] == expected_summary
    assert result.decision in {"buy", "hold", "sell", "wait"}
