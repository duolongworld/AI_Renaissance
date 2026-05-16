import importlib

import pytest
from agentscope.agent import AgentBase as AgentScopeAgentBase

from agents.signal import Signal
from main import EXPERT_AGENTS


@pytest.mark.parametrize("agent_name,agent_info", EXPERT_AGENTS.items())
def test_registered_expert_agent_can_run_offline(agent_name, agent_info, offline_config):
    module = importlib.import_module(agent_info["module"])
    agent_class = getattr(module, agent_info["class"])
    agent = agent_class(config=offline_config(agent_info["signal_type"]))

    assert isinstance(agent, AgentScopeAgentBase)
    signal = agent.analyze("000001")

    assert isinstance(signal, Signal)
    assert agent.signal_type == agent_info["signal_type"]
    assert signal.stock_code == "000001"
    assert signal.signal_type == agent_info["signal_type"]
    assert signal.source
    assert signal.direction in {"bullish", "bearish", "neutral"}
    assert 0.0 <= signal.confidence <= 1.0
    assert signal.reasoning
    assert isinstance(signal.signals, list)
    assert isinstance(signal.meta, dict)
