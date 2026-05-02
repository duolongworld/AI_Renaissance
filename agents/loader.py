"""Discover, resolve, and instantiate Agent classes under the agents package."""

import importlib
import inspect
from pathlib import Path
from typing import Dict, Iterable, List, Tuple, Type

from agents.base import BaseAgent, DataAgent


def _iter_agent_modules() -> Iterable[str]:
    """Yield every importable agent.py module under agents/."""
    agents_root = Path(__file__).resolve().parent
    project_root = agents_root.parent

    for path in sorted(agents_root.rglob("agent.py")):
        relative = path.relative_to(project_root).with_suffix("")
        yield ".".join(relative.parts)


def discover_agent_classes() -> Tuple[Dict[str, Type[BaseAgent]], Dict[str, str]]:
    """
    Return discovered agents and unambiguous short-name aliases.

    Returns:
        canonical_agents: canonical_key -> Agent class
        aliases: short_name -> canonical_key
    """
    canonical_agents: Dict[str, Type[BaseAgent]] = {}
    short_name_index: Dict[str, List[str]] = {}

    for module_name in _iter_agent_modules():
        module = importlib.import_module(module_name)
        canonical_key = module_name.removeprefix("agents.").removesuffix(".agent")

        for _, obj in inspect.getmembers(module, inspect.isclass):
            if obj.__module__ != module_name:
                continue
            if not issubclass(obj, BaseAgent) or obj in (BaseAgent, DataAgent):
                continue

            canonical_agents[canonical_key] = obj
            short_name = canonical_key.split(".")[-1]
            short_name_index.setdefault(short_name, []).append(canonical_key)
            break

    aliases = {
        short_name: canonical_keys[0]
        for short_name, canonical_keys in short_name_index.items()
        if len(canonical_keys) == 1
    }
    return canonical_agents, aliases


def list_available_agents() -> List[str]:
    """List canonical agent names and unambiguous short names."""
    canonical_agents, aliases = discover_agent_classes()
    available = set(canonical_agents.keys())
    available.update(aliases.keys())
    return sorted(available)


def load_agents(enabled_agents: List[str] = None) -> List[BaseAgent]:
    """
    Load enabled Agent instances.

    Args:
        enabled_agents: Agent names to enable.
            - None or empty list: load all discovered agents.
            - Supports short names like cash_flow and canonical keys like
              research.financial.cash_flow.
    """
    canonical_agents, aliases = discover_agent_classes()

    if enabled_agents is None:
        selected_names = list(canonical_agents.keys())
    else:
        if not isinstance(enabled_agents, list):
            raise ValueError("agents 配置必须是字符串列表")
        selected_names = enabled_agents or list(canonical_agents.keys())

    loaded_agents: List[BaseAgent] = []
    loaded_keys = set()

    for agent_name in selected_names:
        if not isinstance(agent_name, str):
            raise ValueError("agents 列表中的条目必须是字符串")

        canonical_key = aliases.get(agent_name, agent_name)
        if canonical_key not in canonical_agents:
            available_agents = ", ".join(list_available_agents())
            raise ValueError(f"未知 Agent: {agent_name}。可用 Agent: {available_agents}")
        if canonical_key in loaded_keys:
            continue

        agent_class = canonical_agents[canonical_key]
        loaded_agents.append(agent_class(config={}))
        loaded_keys.add(canonical_key)

    return loaded_agents
