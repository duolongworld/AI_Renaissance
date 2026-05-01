from agents.research.financial.cash_flow.agent import CashFlowAgent
from arbitration.engine import ArbitrationEngine
from agents.signal import SignalBundle


def test_cash_flow_agent_returns_signal():
    agent = CashFlowAgent(config={})
    signal = agent.analyze("000001")

    assert signal.source == "现金流验证Agent"
    assert signal.direction in {"bullish", "bearish", "neutral"}


def test_arbitration_engine_handles_single_signal_bundle():
    agent = CashFlowAgent(config={})
    signal = agent.analyze("000001")
    bundle = SignalBundle(stock_code="000001")
    bundle.add(signal)

    result = ArbitrationEngine().arbitrate(bundle)

    assert result.signals_summary["total"] == 1
    assert result.decision in {"buy", "hold", "sell", "wait"}
