"""
场景注册表 —— 列出所有可用的市场场景。

添加新场景只需两步：
  1. 新建一个 Python 文件（如 bear_market.py）
  2. 在这里注册
"""

from typing import Dict, Type, Optional

from agents.orchestrator.scenario_profile import ScenarioProfile, DefaultScenario
from .bull_market import BullMarketScenario
from .bear_market import BearMarketScenario
from .range_market import RangeMarketScenario

# ============================================================
# 场景注册表 —— 所有可用场景在这里登记
# ============================================================
SCENARIO_REGISTRY: Dict[str, Type[ScenarioProfile]] = {
    "bull_market": BullMarketScenario,
    "bear_market": BearMarketScenario,
    "range_market": RangeMarketScenario,
}


def get_scenario(name: str) -> Optional[ScenarioProfile]:
    """
    根据名称获取场景实例。

    参数:
        name: 场景标识名，如 "bull_market"

    返回:
        场景实例，如果找不到则返回 None

    使用示例:
        scenario = get_scenario("bull_market")
        if scenario:
            weight, reason = scenario.get_weight("technical")
    """
    scenario_cls = SCENARIO_REGISTRY.get(name)
    if scenario_cls is None:
        return None
    return scenario_cls()


def list_scenarios() -> Dict[str, str]:
    """
    列出所有可用的场景。

    返回:
        {场景标识名: 场景显示名, ...}
        例: {"bull_market": "牛市场景", "default": "默认场景（等权）"}
    """
    result = {"default": DefaultScenario().display_name}
    for name, cls in SCENARIO_REGISTRY.items():
        result[name] = cls().display_name
    return result


def create_default_scenario() -> ScenarioProfile:
    """创建默认场景实例（等权）。"""
    return DefaultScenario()
