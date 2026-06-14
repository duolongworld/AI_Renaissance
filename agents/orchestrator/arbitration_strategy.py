"""
Orchestrator 仲裁策略层。

本模块只负责在规则仲裁和 LLM 仲裁框架之间做运行时分支选择。
LLM 分支只搭建 AgentScope Model、Skill、MCP 的调用框架，
不在代码里写具体的多空裁决流程。
"""

from __future__ import annotations

import inspect
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol, Tuple

from agents.llm import (
    LLMConfigurationError,
    create_agentscope_formatter,
    create_agentscope_model,
    get_shared_llm_model_config,
    run_awaitable_sync,
)
from agents.orchestrator.arbitration import ArbitrationEngine, ArbitrationResult
from agents.signal import SignalBundle


class LLMArbitrationConfigurationError(RuntimeError):
    """LLM 仲裁框架配置错误。"""


class LLMArbitrationExecutionError(RuntimeError):
    """LLM 仲裁框架执行错误。"""


class ArbitrationStrategy(Protocol):
    """Orchestrator 可插拔仲裁策略接口。"""

    def arbitrate(
        self,
        signal_bundle: SignalBundle,
        execution_trace: Optional[Dict[str, Any]] = None,
    ) -> ArbitrationResult:
        """执行仲裁并返回统一结果。"""


class RuleBasedArbitrationStrategy:
    """
    包装现有固定规则仲裁引擎，保持默认行为不变。

    引擎本身已包含场景对象（scenario），策略层只透传调用。
    场景信息可通过 engine.scenario 访问。
    """

    def __init__(self, engine: ArbitrationEngine):
        self.engine = engine

    def arbitrate(
        self,
        signal_bundle: SignalBundle,
        execution_trace: Optional[Dict[str, Any]] = None,
    ) -> ArbitrationResult:
        return self.engine.arbitrate(signal_bundle, execution_trace=execution_trace)

    @property
    def scenario(self) -> Any:
        """返回当前引擎使用的场景对象。"""
        return self.engine.scenario


@dataclass
class ArbitrationSkill:
    """LLM 仲裁框架加载到的一份 Skill。"""

    name: str
    path: str
    content: str

    def to_dict(self, include_content: bool = True) -> Dict[str, Any]:
        data = {"name": self.name, "path": self.path}
        if include_content:
            data["content"] = self.content
        return data


class SkillProvider(Protocol):
    """Skill 读取接口，避免 LLM 分支直接依赖具体目录结构。"""

    def load_skills(self) -> List[ArbitrationSkill]:
        """读取并返回 LLM 仲裁需要的 Skill。"""


class ConfiguredSkillProvider:
    """从配置声明的路径加载 Skill。"""

    def __init__(self, config: Dict[str, Any], repo_root: Optional[Path] = None):
        self.config = config
        self.repo_root = repo_root or Path(__file__).resolve().parents[2]

    def load_skills(self) -> List[ArbitrationSkill]:
        skill_entries = self.config.get("skills")
        if not skill_entries:
            raise LLMArbitrationConfigurationError("llm_framework 需要配置 orchestrator.llm_arbitration.skills")

        skills = []
        for entry in skill_entries:
            name, path = self._parse_skill_entry(entry)
            if not path.exists():
                raise LLMArbitrationConfigurationError(f"Skill 文件不存在：{path}")
            content = path.read_text(encoding="utf-8")
            if not content.strip():
                raise LLMArbitrationConfigurationError(f"Skill 文件为空：{path}")
            skills.append(ArbitrationSkill(name=name, path=str(path), content=content))
        return skills

    def _parse_skill_entry(self, entry: Any) -> Tuple[str, Path]:
        if isinstance(entry, str):
            path = self._resolve_path(entry)
            return path.parent.name, path

        if isinstance(entry, dict):
            raw_path = entry.get("path")
            if not raw_path:
                raise LLMArbitrationConfigurationError("Skill 配置必须包含 path")
            path = self._resolve_path(raw_path)
            return entry.get("name") or path.parent.name, path

        raise LLMArbitrationConfigurationError("Skill 配置只支持字符串路径或包含 path 的字典")

    def _resolve_path(self, raw_path: str) -> Path:
        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            path = self.repo_root / path
        return path


class MCPToolProvider(Protocol):
    """MCP 工具注册接口。"""

    def register_tools(self, toolkit: Any) -> Dict[str, Any]:
        """把 MCP 工具注册进 AgentScope Toolkit，并返回追踪信息。"""


class ConfiguredMCPToolProvider:
    """根据配置创建 AgentScope MCP 客户端并注册工具。"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self._clients_to_close: List[Any] = []

    def register_tools(self, toolkit: Any) -> Dict[str, Any]:
        servers = self.config.get("mcp_servers")
        if not servers:
            return {"servers": [], "tools": []}

        try:
            from agentscope.mcp import HttpStatefulClient, HttpStatelessClient, StdIOStatefulClient
        except Exception as exc:
            raise LLMArbitrationConfigurationError(f"AgentScope MCP 模块不可用：{exc}") from exc

        return run_awaitable_sync(
            self._register_tools_async(
                toolkit,
                servers,
                HttpStatefulClient,
                HttpStatelessClient,
                StdIOStatefulClient,
            )
        )

    async def _register_tools_async(
        self,
        toolkit: Any,
        servers: List[Dict[str, Any]],
        http_stateful_cls: Any,
        http_stateless_cls: Any,
        stdio_cls: Any,
    ) -> Dict[str, Any]:
        registered_tools = []
        server_traces = []
        self._clients_to_close = []

        for server_config in servers:
            client = self._create_client(server_config, http_stateful_cls, http_stateless_cls, stdio_cls)
            if hasattr(client, "connect"):
                await client.connect()
                self._clients_to_close.append(client)
            try:
                tools = await client.list_tools()
            except Exception as exc:
                name = server_config.get("name", "未命名MCP")
                raise LLMArbitrationExecutionError(f"MCP 工具列表读取失败：{name}: {exc}") from exc

            server_trace = {
                "name": server_config.get("name", ""),
                "transport": server_config.get("transport", ""),
                "tool_count": len(tools),
                "tools": [],
            }

            for tool in tools:
                tool_name = getattr(tool, "name", "")
                if not tool_name:
                    continue
                callable_tool = await client.get_callable_function(
                    tool_name,
                    wrap_tool_result=True,
                    execution_timeout=server_config.get("execution_timeout"),
                )
                toolkit.register_tool_function(
                    callable_tool,
                    func_name=tool_name,
                    func_description=getattr(tool, "description", "") or f"MCP 工具：{tool_name}",
                    json_schema=getattr(tool, "inputSchema", None),
                    namesake_strategy="rename",
                )
                registered_tools.append(tool_name)
                server_trace["tools"].append(tool_name)

            server_traces.append(server_trace)

        return {"servers": server_traces, "tools": registered_tools}

    def close(self) -> None:
        """Close stateful MCP clients opened during tool registration."""
        run_awaitable_sync(self._close_clients_async())

    async def _close_clients_async(self) -> None:
        while self._clients_to_close:
            client = self._clients_to_close.pop()
            close = getattr(client, "close", None)
            if not callable(close):
                continue
            try:
                close_result = close(ignore_errors=True)
            except TypeError:
                close_result = close()
            if inspect.isawaitable(close_result):
                await close_result

    def _create_client(
        self,
        server_config: Dict[str, Any],
        http_stateful_cls: Any,
        http_stateless_cls: Any,
        stdio_cls: Any,
    ) -> Any:
        name = server_config.get("name")
        transport = server_config.get("transport")
        if not name or not transport:
            raise LLMArbitrationConfigurationError("MCP 配置必须包含 name 和 transport")

        if transport == "stdio":
            command = server_config.get("command")
            if not command:
                raise LLMArbitrationConfigurationError(f"MCP stdio 配置缺少 command：{name}")
            return stdio_cls(
                name=name,
                command=command,
                args=server_config.get("args"),
                env=server_config.get("env"),
                cwd=server_config.get("cwd"),
            )

        if transport in ("streamable_http", "sse"):
            url = server_config.get("url")
            if not url:
                raise LLMArbitrationConfigurationError(f"MCP HTTP 配置缺少 url：{name}")
            client_cls = http_stateful_cls if server_config.get("stateful") else http_stateless_cls
            return client_cls(
                name=name,
                transport=transport,
                url=url,
                headers=server_config.get("headers"),
                timeout=server_config.get("timeout", 30),
                sse_read_timeout=server_config.get("sse_read_timeout", 300),
            )

        raise LLMArbitrationConfigurationError(f"不支持的 MCP transport：{transport}")


class AgentScopeLLMArbitrationAgent:
    """AgentScope ReActAgent 的轻量包装。"""

    def __init__(self, agent: Any):
        self.agent = agent

    def run(self, payload: Dict[str, Any]) -> Any:
        try:
            from agentscope.message import Msg
        except Exception as exc:
            raise LLMArbitrationConfigurationError(f"AgentScope message 模块不可用：{exc}") from exc

        msg = Msg(
            name="OrchestratorAgent",
            role="user",
            content=json.dumps(payload, ensure_ascii=False, indent=2),
        )

        try:
            response = run_awaitable_sync(self.agent(msg))
        except Exception as exc:
            raise LLMArbitrationExecutionError(f"AgentScope ReActAgent 执行失败：{exc}") from exc

        if hasattr(response, "get_text_content"):
            return response.get_text_content()
        return response


class AgentScopeLLMArbitrationAgentFactory:
    """使用 AgentScope Model 创建 LLM 仲裁 Agent。"""

    def create(self, config: Dict[str, Any], toolkit: Any) -> AgentScopeLLMArbitrationAgent:
        try:
            from agentscope.agent import ReActAgent
        except Exception as exc:
            raise LLMArbitrationConfigurationError(f"AgentScope agent 模块不可用：{exc}") from exc

        try:
            model = create_agentscope_model(config.get("model", {}))
            formatter = create_agentscope_formatter(config.get("model", {}))
        except LLMConfigurationError as exc:
            raise LLMArbitrationConfigurationError(str(exc)) from exc
        agent = ReActAgent(
            name=config.get("agent_name", "LLMArbitrationAgent"),
            sys_prompt=build_llm_arbitration_system_prompt(),
            model=model,
            formatter=formatter,
            toolkit=toolkit,
            parallel_tool_calls=bool(config.get("parallel_tool_calls", True)),
            max_iters=int(config.get("max_iters", 6)),
        )
        return AgentScopeLLMArbitrationAgent(agent)

def build_llm_arbitration_system_prompt() -> str:
    """构建框架级系统提示，不写具体裁决规则。"""
    return (
        "你是 AI_Renaissance Orchestrator 的 LLM 仲裁框架执行器。\n"
        "你只能依据外部配置加载的 Skill、输入的专家 Signal、编排 trace 和可用 MCP 工具工作。\n"
        "本框架代码不提供固定多空评分、仓位计算或投票流程；具体裁决方法必须来自 Skill 或外部工具。\n"
        "你必须返回一个 JSON 对象，字段包括 decision、direction、confidence、position_ratio、"
        "reasoning、signals_summary、risks、reasoning_chain。\n"
        "字段取值必须兼容现有 ArbitrationResult：decision 为 buy/hold/sell/wait，"
        "direction 为 bullish/bearish/neutral，confidence 和 position_ratio 为 0 到 1 的数字。"
    )


class LLMArbitrationStrategy:
    """LLM 仲裁框架策略，只做上下文组装、工具注册、模型调用和结果校验。"""

    def __init__(
        self,
        config: Dict[str, Any],
        skill_provider: Optional[SkillProvider] = None,
        mcp_tool_provider: Optional[MCPToolProvider] = None,
        agent_factory: Optional[Any] = None,
        toolkit_factory: Optional[Callable[[], Any]] = None,
    ):
        self.config = config
        self.skill_provider = skill_provider or ConfiguredSkillProvider(config)
        self.mcp_tool_provider = mcp_tool_provider or ConfiguredMCPToolProvider(config)
        self.agent_factory = agent_factory or AgentScopeLLMArbitrationAgentFactory()
        self.toolkit_factory = toolkit_factory

    def arbitrate(
        self,
        signal_bundle: SignalBundle,
        execution_trace: Optional[Dict[str, Any]] = None,
    ) -> ArbitrationResult:
        started_at = time.perf_counter()
        trace = dict(execution_trace or {})

        skills = self.skill_provider.load_skills()
        if not skills:
            raise LLMArbitrationConfigurationError("llm_framework 至少需要加载一个仲裁 Skill")
        toolkit = self._create_toolkit()
        self._register_skill_tools(toolkit, skills)
        mcp_trace = {"servers": [], "tools": []}

        try:
            mcp_trace = self.mcp_tool_provider.register_tools(toolkit)

            agent = self.agent_factory.create(self.config, toolkit)
            payload = self._build_payload(signal_bundle, execution_trace or {}, skills, mcp_trace)
            raw_response = agent.run(payload)
            result_data = self._parse_response(raw_response)
            result = self._build_result(result_data)

            trace["llm_arbitration"] = {
                "mode": "llm_framework",
                "model": self._model_trace(),
                "skills": [skill.to_dict(include_content=False) for skill in skills],
                "mcp": mcp_trace,
                "duration_seconds": round(time.perf_counter() - started_at, 4),
                "raw_response_preview": self._preview(raw_response),
            }
            result.scope_trace = trace
            return result
        finally:
            close = getattr(self.mcp_tool_provider, "close", None)
            if callable(close):
                close()

    def _create_toolkit(self) -> Any:
        if self.toolkit_factory:
            return self.toolkit_factory()
        try:
            from agentscope.tool import Toolkit
        except Exception as exc:
            raise LLMArbitrationConfigurationError(f"AgentScope Toolkit 不可用：{exc}") from exc
        return Toolkit()

    def _register_skill_tools(self, toolkit: Any, skills: List[ArbitrationSkill]) -> None:
        skill_map = {skill.name: skill for skill in skills}

        try:
            from agentscope.message import TextBlock
            from agentscope.tool import ToolResponse
        except Exception as exc:
            raise LLMArbitrationConfigurationError(f"AgentScope tool response 模块不可用：{exc}") from exc

        def tool_text_response(text: str) -> Any:
            return ToolResponse(content=[TextBlock(type="text", text=text)])

        def list_arbitration_skills() -> Any:
            """列出 LLM 仲裁框架可读取的 Skill 名称。"""
            return tool_text_response(
                json.dumps([skill.to_dict(include_content=False) for skill in skills], ensure_ascii=False)
            )

        def get_arbitration_skill(skill_name: str) -> Any:
            """按名称读取 LLM 仲裁 Skill 内容。"""
            skill = skill_map.get(skill_name)
            if not skill:
                raise LLMArbitrationExecutionError(f"Skill 未加载：{skill_name}")
            return tool_text_response(skill.content)

        toolkit.register_tool_function(
            list_arbitration_skills,
            func_name="list_arbitration_skills",
            func_description="列出 LLM 仲裁框架已加载的 Skill",
            namesake_strategy="rename",
        )
        toolkit.register_tool_function(
            get_arbitration_skill,
            func_name="get_arbitration_skill",
            func_description="读取指定 LLM 仲裁 Skill 的完整内容",
            namesake_strategy="rename",
        )

    def _build_payload(
        self,
        signal_bundle: SignalBundle,
        execution_trace: Dict[str, Any],
        skills: List[ArbitrationSkill],
        mcp_trace: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "task": "使用外部 Skill 与 MCP 工具完成仲裁，并返回 ArbitrationResult JSON。",
            "stock_code": signal_bundle.stock_code,
            "signal_bundle": self._compact_signal_bundle(signal_bundle),
            "execution_trace": self._compact_execution_trace(execution_trace),
            "available_skills": [skill.to_dict(include_content=False) for skill in skills],
            "mcp_tools": mcp_trace,
            "required_output_schema": {
                "decision": "buy|hold|sell|wait",
                "direction": "bullish|bearish|neutral",
                "confidence": "0.0-1.0",
                "position_ratio": "0.0-1.0",
                "reasoning": "string",
                "signals_summary": "object",
                "risks": "array[string]",
                "reasoning_chain": "array[string]",
            },
        }

    def _compact_signal_bundle(self, signal_bundle: SignalBundle) -> Dict[str, Any]:
        return {
            "stock_code": signal_bundle.stock_code,
            "signal_count": len(signal_bundle.signals),
            "signals": [
                {
                    "source": signal.source,
                    "signal_type": signal.signal_type,
                    "direction": signal.direction,
                    "confidence": signal.confidence,
                    "weight": signal.weight,
                    "stock_code": signal.stock_code,
                    "signals": self._limit_list(signal.signals, 20),
                    "reasoning": self._preview_text(signal.reasoning, 1200),
                    "meta_summary": self._summarize_meta(signal.meta),
                }
                for signal in signal_bundle.signals
            ],
        }

    def _compact_execution_trace(self, execution_trace: Dict[str, Any]) -> Dict[str, Any]:
        compact_results = []
        for result in execution_trace.get("execution_results", []) or []:
            signal = result.get("signal") or {}
            compact_results.append(
                {
                    "agent_name": result.get("agent_name", ""),
                    "signal_type": result.get("signal_type", ""),
                    "status": result.get("status", ""),
                    "duration_seconds": result.get("duration_seconds", 0),
                    "error": self._preview_text(result.get("error", ""), 300),
                    "signal_direction": signal.get("direction"),
                    "signal_confidence": signal.get("confidence"),
                }
            )

        return {
            "framework": execution_trace.get("framework", ""),
            "stock_code": execution_trace.get("stock_code", ""),
            "duration_seconds": execution_trace.get("duration_seconds", 0),
            "summary": execution_trace.get("summary", {}),
            "execution_results": compact_results,
        }

    def _summarize_meta(self, meta: Dict[str, Any]) -> Dict[str, Any]:
        summary = {}
        for key, value in (meta or {}).items():
            if isinstance(value, (str, int, float, bool)) or value is None:
                summary[key] = self._preview_text(value, 300) if isinstance(value, str) else value
            elif isinstance(value, list):
                summary[key] = {
                    "type": "list",
                    "count": len(value),
                    "preview": self._preview_text(value[:3], 500),
                }
            elif isinstance(value, dict):
                summary[key] = {
                    "type": "dict",
                    "keys": list(value.keys())[:20],
                }
            else:
                summary[key] = {"type": type(value).__name__}
        return summary

    def _limit_list(self, values: List[Any], limit: int) -> List[Any]:
        if len(values) <= limit:
            return values
        return values[:limit] + [f"... truncated {len(values) - limit} items"]

    def _preview_text(self, value: Any, limit: int) -> str:
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
        if len(text) <= limit:
            return text
        return text[:limit] + f"... truncated {len(text) - limit} chars"

    def _parse_response(self, raw_response: Any) -> Dict[str, Any]:
        if isinstance(raw_response, dict):
            return raw_response

        if hasattr(raw_response, "model_dump"):
            return raw_response.model_dump()

        if not isinstance(raw_response, str):
            raise LLMArbitrationExecutionError(f"LLM 返回类型不支持：{type(raw_response).__name__}")

        text = raw_response.strip()
        if not text:
            raise LLMArbitrationExecutionError("LLM 返回为空")

        json_text = self._extract_json_text(text)
        try:
            parsed = json.loads(json_text)
        except json.JSONDecodeError as exc:
            raise LLMArbitrationExecutionError(f"LLM 返回不是合法 JSON：{exc}") from exc

        if not isinstance(parsed, dict):
            raise LLMArbitrationExecutionError("LLM JSON 返回必须是对象")
        return parsed

    def _extract_json_text(self, text: str) -> str:
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if fenced:
            return fenced.group(1)
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return text[start : end + 1]
        return text

    def _build_result(self, data: Dict[str, Any]) -> ArbitrationResult:
        required_fields = [
            "decision",
            "direction",
            "confidence",
            "position_ratio",
            "reasoning",
            "signals_summary",
            "risks",
            "reasoning_chain",
        ]
        missing = [field for field in required_fields if field not in data]
        if missing:
            raise LLMArbitrationExecutionError(f"LLM 返回缺少字段：{', '.join(missing)}")

        decision = data["decision"]
        direction = data["direction"]
        if decision not in {"buy", "hold", "sell", "wait"}:
            raise LLMArbitrationExecutionError(f"decision 非法：{decision}")
        if direction not in {"bullish", "bearish", "neutral"}:
            raise LLMArbitrationExecutionError(f"direction 非法：{direction}")

        confidence = self._validate_ratio(data["confidence"], "confidence")
        position_ratio = self._validate_ratio(data["position_ratio"], "position_ratio")
        risks = self._validate_string_list(data["risks"], "risks")
        reasoning_chain = self._validate_string_list(data["reasoning_chain"], "reasoning_chain")

        if not isinstance(data["signals_summary"], dict):
            raise LLMArbitrationExecutionError("signals_summary 必须是对象")
        if not isinstance(data["reasoning"], str):
            raise LLMArbitrationExecutionError("reasoning 必须是字符串")

        return ArbitrationResult(
            decision=decision,
            direction=direction,
            confidence=confidence,
            position_ratio=position_ratio,
            reasoning=data["reasoning"],
            signals_summary=data["signals_summary"],
            risks=risks,
            reasoning_chain=reasoning_chain,
            scope_trace={},
        )

    def _validate_ratio(self, value: Any, field_name: str) -> float:
        if not isinstance(value, (int, float)):
            raise LLMArbitrationExecutionError(f"{field_name} 必须是数字")
        ratio = float(value)
        if not 0.0 <= ratio <= 1.0:
            raise LLMArbitrationExecutionError(f"{field_name} 必须在 0 到 1 之间")
        return ratio

    def _validate_string_list(self, value: Any, field_name: str) -> List[str]:
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise LLMArbitrationExecutionError(f"{field_name} 必须是字符串数组")
        return value

    def _model_trace(self) -> Dict[str, Any]:
        model_config = self.config.get("model", {})
        return {
            "provider": model_config.get("provider", ""),
            "model_name": model_config.get("model_name", ""),
        }

    def _preview(self, raw_response: Any) -> str:
        text = raw_response if isinstance(raw_response, str) else json.dumps(raw_response, ensure_ascii=False)
        return text[:500]


def create_arbitration_strategy(config: Dict[str, Any], engine: ArbitrationEngine) -> ArbitrationStrategy:
    """根据 Orchestrator 配置创建仲裁策略。"""
    orchestrator_config = config.get("orchestrator", {}) if config else {}
    mode = orchestrator_config.get("arbitration_mode", config.get("arbitration_mode", "rule_based"))

    if mode == "rule_based":
        return RuleBasedArbitrationStrategy(engine)

    if mode == "llm_framework":
        llm_config = orchestrator_config.get("llm_arbitration", config.get("llm_arbitration", {}))
        if "model" not in llm_config:
            shared_model = get_shared_llm_model_config(config)
            if shared_model:
                llm_config = {**llm_config, "model": shared_model}
        return LLMArbitrationStrategy(llm_config)

    raise LLMArbitrationConfigurationError(f"不支持的仲裁模式：{mode}")
