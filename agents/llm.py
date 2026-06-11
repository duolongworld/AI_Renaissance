"""Shared LLM configuration and client helpers."""

from __future__ import annotations

import asyncio
import inspect
import os
from typing import Any, Dict, Optional, Protocol


class LLMConfigurationError(RuntimeError):
    """LLM configuration error."""


class LLMExecutionError(RuntimeError):
    """LLM execution error."""


class PromptLLMClient(Protocol):
    """Minimal prompt client contract for expert Agents."""

    def __call__(self, prompt: str, system: str = "") -> str:
        """Run a prompt and return text."""

    def call_llm(self, prompt: str, system: str = "") -> str:
        """Named alias for callers that prefer an explicit method."""


class SimpleLLMClient:
    """Thin text client over an AgentScope chat model."""

    def __init__(self, model: Any):
        self.model = model

    @classmethod
    def from_model_config(cls, model_config: Dict[str, Any]) -> "SimpleLLMClient":
        config = dict(model_config)
        config.setdefault("stream", False)
        return cls(create_agentscope_model(config))

    def __call__(self, prompt: str, system: str = "") -> str:
        messages = self._build_messages(prompt=prompt, system=system)
        response = self.model(messages)
        return self._response_to_text(response)

    def call_llm(self, prompt: str, system: str = "") -> str:
        return self(prompt=prompt, system=system)

    def _build_messages(self, prompt: str, system: str = "") -> list[dict[str, str]]:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return messages

    def _response_to_text(self, response: Any) -> str:
        response = run_awaitable_sync(response)

        if inspect.isasyncgen(response):
            return asyncio.run(self._collect_stream_response(response))

        if isinstance(response, str):
            return response

        get_text_content = self._safe_getattr(response, "get_text_content")
        if callable(get_text_content):
            return get_text_content()

        content = response.get("content") if isinstance(response, dict) else self._safe_getattr(response, "content")
        text = self._content_to_text(content)
        if text is not None:
            return text

        if response is None:
            raise LLMExecutionError("LLM returned empty response")
        return str(response)

    async def _collect_stream_response(self, response: Any) -> str:
        chunks = []
        async for chunk in response:
            chunks.append(self._response_to_text(chunk))
        return "".join(chunks)

    def _content_to_text(self, content: Any) -> Optional[str]:
        if content is None:
            return None
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, str):
                    parts.append(block)
                    continue
                if isinstance(block, dict):
                    value = block.get("text") or block.get("content")
                    if value:
                        parts.append(str(value))
                    continue
                value = self._safe_getattr(block, "text") or self._safe_getattr(block, "content")
                if value:
                    parts.append(str(value))
            return "".join(parts)
        return str(content)

    def _safe_getattr(self, value: Any, attr: str, default: Any = None) -> Any:
        try:
            return getattr(value, attr)
        except (AttributeError, KeyError):
            return default


def create_llm_client(config: Dict[str, Any], model_config: Optional[Dict[str, Any]] = None) -> SimpleLLMClient:
    """Create a prompt client from explicit or shared project LLM config."""
    resolved_model_config = model_config or get_shared_llm_model_config(config)
    if not resolved_model_config:
        raise LLMConfigurationError("LLM client requires llm.model or an explicit model_config")
    return SimpleLLMClient.from_model_config(resolved_model_config)


def run_awaitable_sync(value: Any) -> Any:
    """Resolve an AgentScope async return value from the project's sync runtime."""
    if not inspect.isawaitable(value):
        return value

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(value)

    raise LLMExecutionError("Cannot synchronously wait for LLM result inside a running event loop")


def get_shared_llm_model_config(config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Return the shared LLM model config, if present."""
    llm_config = (config or {}).get("llm", {})
    return llm_config.get("model")


def create_agentscope_model(model_config: Dict[str, Any]) -> Any:
    """Create an AgentScope chat model from config."""
    if not model_config:
        raise LLMConfigurationError("LLM model config is required")

    provider = model_config.get("provider", "").lower()
    model_name = model_config.get("model_name")
    if not provider or not model_name:
        raise LLMConfigurationError("LLM model config must include provider and model_name")

    api_key = _resolve_config_value(model_config, "api_key", "api_key_env")
    generate_kwargs = model_config.get("generate_kwargs")
    client_kwargs = model_config.get("client_kwargs", {}).copy()
    base_url = _resolve_config_value(model_config, "base_url", "base_url_env")
    stream = model_config.get("stream")
    if base_url:
        client_kwargs["base_url"] = base_url

    try:
        from agentscope.model import DashScopeChatModel, OllamaChatModel, OpenAIChatModel
    except Exception as exc:
        raise LLMConfigurationError(f"AgentScope model module is unavailable: {exc}") from exc

    common_kwargs = {}
    if stream is not None:
        common_kwargs["stream"] = bool(stream)

    if provider == "ollama":
        return OllamaChatModel(
            model_name=model_name,
            host=model_config.get("host"),
            options=model_config.get("options"),
            generate_kwargs=generate_kwargs,
            **common_kwargs,
        )

    if provider == "dashscope":
        if not api_key:
            raise LLMConfigurationError("DashScope model config is missing api_key")
        return DashScopeChatModel(
            model_name=model_name,
            api_key=api_key,
            generate_kwargs=generate_kwargs,
            base_http_api_url=base_url,
            **common_kwargs,
        )

    if provider in ("openai", "openai_compatible"):
        if not api_key:
            raise LLMConfigurationError("OpenAI model config is missing api_key")
        return OpenAIChatModel(
            model_name=model_name,
            api_key=api_key,
            client_kwargs=client_kwargs or None,
            generate_kwargs=generate_kwargs,
            **common_kwargs,
        )

    raise LLMConfigurationError(f"Unsupported LLM provider: {provider}")


def create_agentscope_formatter(model_config: Dict[str, Any]) -> Any:
    """Create an AgentScope formatter for a model provider."""
    provider = model_config.get("provider", "").lower()
    try:
        from agentscope.formatter import DashScopeChatFormatter, OllamaChatFormatter, OpenAIChatFormatter
    except Exception as exc:
        raise LLMConfigurationError(f"AgentScope formatter module is unavailable: {exc}") from exc

    if provider == "dashscope":
        return DashScopeChatFormatter()
    if provider in ("openai", "openai_compatible"):
        return OpenAIChatFormatter()
    return OllamaChatFormatter()


def _expand_env_value(value: Optional[str]) -> Optional[str]:
    if not value:
        return value
    if value.startswith("${") and value.endswith("}"):
        return os.environ.get(value[2:-1])
    return value


def _resolve_config_value(config: Dict[str, Any], value_key: str, env_key: str) -> Optional[str]:
    env_name = config.get(env_key)
    if env_name:
        return os.environ.get(env_name)
    return _expand_env_value(config.get(value_key))
