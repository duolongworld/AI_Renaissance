import asyncio

import pytest
try:
    from agentscope.agent import AgentBase as AgentScopeAgentBase
except ModuleNotFoundError:
    from agentscope.agents import AgentBase as AgentScopeAgentBase

from agents.agentscope_message import msg_to_signal, stock_task_to_msg
from agents.base import AgentContractError, BaseAgent
from agents.news_agent.agent import NewsAgent
from agents.signal import Signal, bullish_signal


class MockExpertAgent(BaseAgent):
    signal_type = "mock"

    def __init__(self, result=None):
        super().__init__(name="MockExpertAgent", config={})
        self.result = result

    def analyze(self, stock_code: str):
        if self.result is not None:
            return self.result
        return bullish_signal(
            confidence=0.8,
            reasoning=f"mock analyzed {stock_code}",
            signals=["mock signal"],
            source=self.name,
            stock_code=stock_code,
            signal_type=self.signal_type,
        )


class MissingAnalyzeAgent(BaseAgent):
    signal_type = "missing"


def run(coro):
    return asyncio.run(coro)


def test_base_agent_is_agentscope_native_agent():
    agent = MockExpertAgent()

    assert isinstance(agent, AgentScopeAgentBase)


def test_base_agent_can_be_called_through_agentscope_call_protocol():
    agent = MockExpertAgent()
    task_msg = stock_task_to_msg("600519", context={"source": "unit-test"})

    result_msg = run(agent(task_msg))
    signal = msg_to_signal(result_msg)

    assert isinstance(signal, Signal)
    assert signal.stock_code == "600519"
    assert signal.signal_type == "mock"
    assert signal.direction == "bullish"
    assert result_msg.name == "MockExpertAgent"


def test_base_agent_rejects_missing_analyze_implementation():
    with pytest.raises(TypeError, match="must implement analyze"):
        MissingAnalyzeAgent(name="MissingAnalyzeAgent", config={})


def test_base_agent_rejects_non_signal_expert_result():
    agent = MockExpertAgent(result={"not": "signal"})
    task_msg = stock_task_to_msg("600519")

    with pytest.raises(AgentContractError, match="expected Signal"):
        run(agent.reply(task_msg))


def test_news_agent_runs_through_agentscope_native_call_offline(fake_news_source):
    news_agent = NewsAgent(
        config={
            "pages": 1,
            "fetch_content": False,
            "guba_data_source": fake_news_source,
            "market_sentiment_source": fake_news_source,
            "industry_sentiment_source": fake_news_source,
        },
    )
    task_msg = stock_task_to_msg("600519", context={"source": "offline-news-test"})

    result_msg = run(news_agent(task_msg))
    signal = msg_to_signal(result_msg)

    assert isinstance(signal, Signal)
    assert signal.stock_code == "600519"
    assert signal.signal_type == "news"
    assert signal.source == "舆情情感Agent"
    assert signal.reasoning
    assert signal.meta["stock"]["total_posts"] == 5
