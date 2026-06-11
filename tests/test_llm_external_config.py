import sys
import types
from pathlib import Path

import yaml

from agents.llm import create_agentscope_model, create_llm_client
from agents.orchestrator.arbitration import ArbitrationEngine
from agents.orchestrator.arbitration_strategy import (
    AgentScopeLLMArbitrationAgent,
    ArbitrationSkill,
    ConfiguredMCPToolProvider,
    LLMArbitrationStrategy,
    RuleBasedArbitrationStrategy,
    create_arbitration_strategy,
)
from agents.signal import SignalBundle, bullish_signal


ROOT = Path(__file__).resolve().parents[1]
LLM_EXAMPLE_CONFIG = ROOT / "config" / "llm.example.yaml"
GITIGNORE = ROOT / ".gitignore"


def test_llm_example_config_uses_placeholder_values() -> None:
    config = yaml.safe_load(LLM_EXAMPLE_CONFIG.read_text(encoding="utf-8"))
    default_config = yaml.safe_load((ROOT / "config" / "default.yaml").read_text(encoding="utf-8"))
    llm_config = config["orchestrator"]["llm_arbitration"]
    model_config = config["llm"]["model"]

    assert "your-" in model_config["base_url"]
    assert model_config["api_key"].startswith("your-")
    assert set(config["llm"]) == {"model"}
    assert "model" not in llm_config
    assert config["agent_timeout_seconds"] == default_config["agent_timeout_seconds"]
    assert config["confidence_threshold"] == default_config["confidence_threshold"]


def test_private_llm_config_files_are_ignored() -> None:
    gitignore = GITIGNORE.read_text(encoding="utf-8")

    assert "config/*.private.yaml" in gitignore
    assert "config/*.private.yml" not in gitignore


def test_default_config_uses_rule_based_arbitration() -> None:
    config = yaml.safe_load((ROOT / "config" / "default.yaml").read_text(encoding="utf-8"))
    strategy = create_arbitration_strategy(config, ArbitrationEngine())

    assert isinstance(strategy, RuleBasedArbitrationStrategy)


def test_orchestrator_llm_arbitration_reuses_shared_model() -> None:
    model_config = {
        "provider": "openai_compatible",
        "model_name": "test-model",
        "base_url": "https://llm-gateway.example.com/v1",
        "api_key": "test-api-key",
    }
    strategy = create_arbitration_strategy(
        {
            "llm": {"model": model_config},
            "orchestrator": {
                "arbitration_mode": "llm_framework",
                "llm_arbitration": {
                    "skills": [{"path": "skills/orchestrator/llm_arbitration_policy/SKILL.md"}],
                    "mcp_servers": [],
                },
            },
        },
        ArbitrationEngine(),
    )

    assert strategy.config["model"] == model_config


def _install_fake_agentscope_model(monkeypatch) -> type:
    class FakeOpenAIChatModel:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def __call__(self, messages):
            self.messages = messages
            return {"content": [{"type": "text", "text": "ok"}]}

    fake_model_module = types.ModuleType("agentscope.model")
    fake_model_module.OpenAIChatModel = FakeOpenAIChatModel
    fake_model_module.DashScopeChatModel = object
    fake_model_module.OllamaChatModel = object
    monkeypatch.setitem(sys.modules, "agentscope.model", fake_model_module)
    return FakeOpenAIChatModel


def test_create_agentscope_model_accepts_local_openai_compatible_config(monkeypatch) -> None:
    _install_fake_agentscope_model(monkeypatch)

    model = create_agentscope_model(
        {
            "provider": "openai_compatible",
            "model_name": "test-model",
            "base_url": "https://llm-gateway.example.com/v1",
            "api_key": "test-api-key",
        }
    )

    assert model.kwargs["api_key"] == "test-api-key"
    assert model.kwargs["client_kwargs"]["base_url"] == "https://llm-gateway.example.com/v1"


def test_create_llm_client_uses_shared_model(monkeypatch) -> None:
    _install_fake_agentscope_model(monkeypatch)

    client = create_llm_client(
        {
            "llm": {
                "model": {
                    "provider": "openai_compatible",
                    "model_name": "test-model",
                    "base_url": "https://llm-gateway.example.com/v1",
                    "api_key": "test-api-key",
                },
            },
        }
    )

    assert client(prompt="hello", system="rules") == "ok"
    assert client.model.messages == [
        {"role": "system", "content": "rules"},
        {"role": "user", "content": "hello"},
    ]
    assert client.model.kwargs["stream"] is False


def test_create_llm_client_handles_agentscope_response_key_errors(monkeypatch) -> None:
    class FakeAgentScopeResponse:
        def __init__(self):
            self.content = "ok"

        def __getattr__(self, name):
            raise KeyError(name)

    class FakeOpenAIChatModel:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def __call__(self, messages):
            return FakeAgentScopeResponse()

    fake_model_module = types.ModuleType("agentscope.model")
    fake_model_module.OpenAIChatModel = FakeOpenAIChatModel
    fake_model_module.DashScopeChatModel = object
    fake_model_module.OllamaChatModel = object
    monkeypatch.setitem(sys.modules, "agentscope.model", fake_model_module)

    client = create_llm_client(
        {
            "llm": {
                "model": {
                    "provider": "openai_compatible",
                    "model_name": "test-model",
                    "base_url": "https://llm-gateway.example.com/v1",
                    "api_key": "test-api-key",
                },
            },
        }
    )

    assert client(prompt="hello") == "ok"


def test_create_agentscope_model_accepts_environment_variable_names(monkeypatch) -> None:
    _install_fake_agentscope_model(monkeypatch)
    monkeypatch.setenv("AI_RENAISSANCE_LLM_BASE_URL", "https://llm-gateway.example.com/v1")
    monkeypatch.setenv("AI_RENAISSANCE_LLM_API_KEY", "test-api-key")

    model = create_agentscope_model(
        {
            "provider": "openai_compatible",
            "model_name": "test-model",
            "base_url_env": "AI_RENAISSANCE_LLM_BASE_URL",
            "api_key_env": "AI_RENAISSANCE_LLM_API_KEY",
        }
    )

    assert model.kwargs["api_key"] == "test-api-key"
    assert model.kwargs["client_kwargs"]["base_url"] == "https://llm-gateway.example.com/v1"


def test_mcp_servers_are_optional_for_direct_llm_arbitration() -> None:
    assert ConfiguredMCPToolProvider({}).register_tools(toolkit=object()) == {
        "servers": [],
        "tools": [],
    }


def test_mcp_tools_are_registered_from_agentscope_async_clients(monkeypatch) -> None:
    class FakeTool:
        name = "lookup_policy"
        description = "lookup policy"
        inputSchema = {"type": "object", "properties": {}}

    class FakeHttpStatelessClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def list_tools(self):
            return [FakeTool()]

        async def get_callable_function(self, func_name, wrap_tool_result=True, execution_timeout=None):
            async def fake_callable(**kwargs):
                return {"func_name": func_name, "kwargs": kwargs}

            return fake_callable

    fake_mcp_module = types.ModuleType("agentscope.mcp")
    fake_mcp_module.HttpStatefulClient = FakeHttpStatelessClient
    fake_mcp_module.HttpStatelessClient = FakeHttpStatelessClient
    fake_mcp_module.StdIOStatefulClient = FakeHttpStatelessClient
    monkeypatch.setitem(sys.modules, "agentscope.mcp", fake_mcp_module)

    class FakeToolkit:
        def __init__(self):
            self.functions = {}
            self.schemas = {}

        def register_tool_function(self, tool_func, func_name, **kwargs):
            self.functions[func_name] = tool_func
            self.schemas[func_name] = kwargs

    toolkit = FakeToolkit()
    trace = ConfiguredMCPToolProvider(
        {
            "mcp_servers": [
                {
                    "name": "policy_mcp",
                    "transport": "streamable_http",
                    "url": "http://localhost:8000/mcp",
                }
            ],
        }
    ).register_tools(toolkit)

    assert trace == {
        "servers": [
            {
                "name": "policy_mcp",
                "transport": "streamable_http",
                "tool_count": 1,
                "tools": ["lookup_policy"],
            }
        ],
        "tools": ["lookup_policy"],
    }
    assert "lookup_policy" in toolkit.functions
    assert toolkit.schemas["lookup_policy"]["json_schema"] == {"type": "object", "properties": {}}


def test_stateful_mcp_clients_are_connected_and_closed(monkeypatch) -> None:
    events = []

    class FakeStatefulClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def connect(self):
            events.append("connect")

        async def list_tools(self):
            return []

        async def close(self, ignore_errors=True):
            events.append(("close", ignore_errors))

    fake_mcp_module = types.ModuleType("agentscope.mcp")
    fake_mcp_module.HttpStatefulClient = FakeStatefulClient
    fake_mcp_module.HttpStatelessClient = FakeStatefulClient
    fake_mcp_module.StdIOStatefulClient = FakeStatefulClient
    monkeypatch.setitem(sys.modules, "agentscope.mcp", fake_mcp_module)

    provider = ConfiguredMCPToolProvider(
        {
            "mcp_servers": [
                {
                    "name": "stateful_policy_mcp",
                    "transport": "streamable_http",
                    "url": "http://localhost:8000/mcp",
                    "stateful": True,
                }
            ],
        }
    )

    assert provider.register_tools(toolkit=object())["servers"][0]["tool_count"] == 0
    assert events == ["connect"]

    provider.close()

    assert events == ["connect", ("close", True)]


def test_llm_arbitration_strategy_closes_mcp_provider_after_run() -> None:
    class FakeSkillProvider:
        def load_skills(self):
            return [ArbitrationSkill(name="policy", path="policy", content="policy text")]

    class FakeMCPToolProvider:
        def __init__(self):
            self.close_calls = 0

        def register_tools(self, toolkit):
            return {"servers": [{"name": "fake", "tools": ["lookup_policy"]}], "tools": ["lookup_policy"]}

        def close(self):
            self.close_calls += 1

    class FakeAgent:
        def run(self, payload):
            return {
                "decision": "buy",
                "direction": "bullish",
                "confidence": 0.7,
                "position_ratio": 0.3,
                "reasoning": "policy passed",
                "signals_summary": {"total": 1, "bullish": 1, "bearish": 0, "neutral": 0},
                "risks": [],
                "reasoning_chain": ["policy passed"],
            }

    class FakeAgentFactory:
        def create(self, config, toolkit):
            return FakeAgent()

    class FakeToolkit:
        def register_tool_function(self, *args, **kwargs):
            pass

    bundle = SignalBundle(stock_code="600519")
    bundle.add(
        bullish_signal(
            confidence=0.7,
            reasoning="test signal",
            signals=["signal"],
            source="NewsAgent",
            stock_code="600519",
            signal_type="news",
        )
    )
    mcp_provider = FakeMCPToolProvider()

    result = LLMArbitrationStrategy(
        {"skills": [{"path": "unused"}]},
        skill_provider=FakeSkillProvider(),
        mcp_tool_provider=mcp_provider,
        agent_factory=FakeAgentFactory(),
        toolkit_factory=FakeToolkit,
    ).arbitrate(bundle, execution_trace={})

    assert result.decision == "buy"
    assert mcp_provider.close_calls == 1


def test_llm_arbitration_skill_tools_return_agentscope_tool_response() -> None:
    class FakeToolkit:
        def __init__(self):
            self.functions = {}

        def register_tool_function(self, tool_func, func_name, **kwargs):
            self.functions[func_name] = tool_func

    toolkit = FakeToolkit()
    strategy = LLMArbitrationStrategy({"skills": [{"path": "unused"}]})
    strategy._register_skill_tools(
        toolkit,
        [ArbitrationSkill(name="policy", path="skills/policy/SKILL.md", content="policy text")],
    )

    response = toolkit.functions["get_arbitration_skill"]("policy")

    assert response.__class__.__name__ == "ToolResponse"
    assert response.content[0]["type"] == "text"
    assert response.content[0]["text"] == "policy text"


def test_llm_arbitration_payload_compacts_heavy_signal_meta() -> None:
    bundle = SignalBundle(stock_code="600519")
    bundle.add(
        bullish_signal(
            confidence=0.7,
            reasoning="r" * 2000,
            signals=[f"signal-{index}" for index in range(30)],
            source="NewsAgent",
            stock_code="600519",
            signal_type="news",
            meta={"posts": [{"title": "x", "body": "y" * 1000} for _ in range(200)]},
        )
    )
    execution_trace = {
        "framework": "AgentScope",
        "stock_code": "600519",
        "summary": {"success_count": 1},
        "execution_results": [{"agent_name": "NewsAgent", "signal_type": "news", "status": "success", "signal": bundle.signals[0].to_dict()}],
    }

    payload = LLMArbitrationStrategy({})._build_payload(
        bundle,
        execution_trace,
        [ArbitrationSkill(name="policy", path="policy", content="content")],
        {"servers": [], "tools": []},
    )

    signal_payload = payload["signal_bundle"]["signals"][0]
    trace_payload = payload["execution_trace"]["execution_results"][0]

    assert signal_payload["reasoning"].endswith("chars")
    assert signal_payload["signals"][-1].startswith("... truncated")
    assert signal_payload["meta_summary"]["posts"]["count"] == 200
    assert "signal" not in trace_payload


def test_agentscope_llm_arbitration_agent_awaits_async_react_agent() -> None:
    class FakeResponse:
        def get_text_content(self):
            return "ok"

    class FakeReActAgent:
        async def __call__(self, msg):
            self.msg = msg
            return FakeResponse()

    react_agent = FakeReActAgent()
    result = AgentScopeLLMArbitrationAgent(react_agent).run({"task": "unit"})

    assert result == "ok"
    assert react_agent.msg.content
