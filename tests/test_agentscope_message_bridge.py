import pytest

from agents.agentscope_message import (
    AgentScopeMessageError,
    ARBITRATION_RESULT_MESSAGE_TYPE,
    EXPERT_SIGNAL_MESSAGE_TYPE,
    MESSAGE_TYPE_METADATA_KEY,
    STOCK_ANALYSIS_TASK_MESSAGE_TYPE,
    arbitration_result_to_msg,
    extract_stock_code,
    msg_to_signal,
    signal_to_msg,
    stock_task_to_msg,
)
from agents.orchestrator.arbitration import ArbitrationResult
from agents.signal import bullish_signal


class FakeMsg:
    def __init__(self, name, role, content, metadata=None):
        self.name = name
        self.role = role
        self.content = content
        self.metadata = metadata or {}


def test_stock_task_msg_carries_stock_code_and_context():
    msg = stock_task_to_msg(
        "600519",
        context={"source": "unit-test"},
        msg_class=FakeMsg,
    )

    assert extract_stock_code(msg) == "600519"
    assert msg.metadata[MESSAGE_TYPE_METADATA_KEY] == STOCK_ANALYSIS_TASK_MESSAGE_TYPE
    assert msg.metadata["task"] == "analyze_stock"
    assert msg.metadata["context"] == {"source": "unit-test"}


def test_stock_task_msg_uses_real_agentscope_msg_when_available():
    pytest.importorskip("agentscope.message")

    msg = stock_task_to_msg("600519", context={"source": "real-msg"})

    assert msg.role == "user"
    assert msg.content == "Analyze stock 600519"
    assert extract_stock_code(msg) == "600519"
    assert msg.metadata["context"] == {"source": "real-msg"}


def test_signal_round_trips_through_agentscope_msg_metadata():
    signal = bullish_signal(
        confidence=0.8,
        reasoning="contract bridge works",
        signals=["bridge"],
        source="TestAgent",
        stock_code="600519",
        signal_type="financial",
        meta={"trace": "unit"},
    )

    msg = signal_to_msg(signal, msg_class=FakeMsg)
    restored = msg_to_signal(msg)

    assert restored.to_dict() == signal.to_dict()
    assert msg.name == "TestAgent"
    assert msg.content == signal.reasoning
    assert msg.metadata[MESSAGE_TYPE_METADATA_KEY] == EXPERT_SIGNAL_MESSAGE_TYPE


def test_arbitration_result_wraps_stable_payload_and_diagnostic_trace():
    result = ArbitrationResult(
        decision="hold",
        direction="bullish",
        confidence=0.75,
        position_ratio=0.3,
        reasoning="test reasoning",
        signals_summary={"total": 1, "bullish": 1, "bearish": 0, "neutral": 0},
        risks=["sample risk"],
        reasoning_chain=["sample chain"],
        scope_trace={"summary": {"success_count": 1}},
    )

    msg = arbitration_result_to_msg(result, msg_class=FakeMsg)

    assert msg.name == "OrchestratorAgent"
    assert msg.content == "test reasoning"
    assert msg.metadata[MESSAGE_TYPE_METADATA_KEY] == ARBITRATION_RESULT_MESSAGE_TYPE
    assert msg.metadata["decision"] == "hold"
    assert msg.metadata["arbitration_result"] == {
        "decision": "hold",
        "direction": "bullish",
        "confidence": 0.75,
        "position_ratio": 0.3,
        "reasoning": "test reasoning",
        "signals_summary": {"total": 1, "bullish": 1, "bearish": 0, "neutral": 0},
        "risks": ["sample risk"],
        "reasoning_chain": ["sample chain"],
    }
    assert "scope_trace" not in msg.metadata["arbitration_result"]
    assert msg.metadata["scope_trace"]["summary"]["success_count"] == 1


def test_stock_task_msg_rejects_empty_stock_code():
    with pytest.raises(AgentScopeMessageError, match="stock_code is required"):
        stock_task_to_msg("")


def test_msg_to_signal_requires_signal_metadata():
    msg = stock_task_to_msg("600519", msg_class=FakeMsg)

    with pytest.raises(AgentScopeMessageError, match="does not contain a signal"):
        msg_to_signal(msg)


def test_msg_to_signal_wraps_malformed_signal_metadata():
    msg = FakeMsg(
        name="BadAgent",
        role="assistant",
        content="bad signal",
        metadata={"signal": {"confidence": 0.5}},
    )

    with pytest.raises(AgentScopeMessageError, match="signal metadata is invalid"):
        msg_to_signal(msg)


def test_extract_stock_code_requires_stock_code_metadata():
    signal = bullish_signal(
        confidence=0.7,
        reasoning="no stock task",
        signals=["x"],
        source="TestAgent",
        stock_code="600519",
        signal_type="financial",
    )
    msg = signal_to_msg(signal, msg_class=FakeMsg)

    with pytest.raises(AgentScopeMessageError, match="does not contain stock_code"):
        extract_stock_code(msg)
