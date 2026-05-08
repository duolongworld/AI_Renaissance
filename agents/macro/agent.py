"""
宏观周期 Agent - 专家4组

signal_type: macro
Skill 域: skills/macro/
核心能力：利率/汇率/PMI 解读，大周期位置判断
"""

from typing import Optional
from agents.base import BaseAgent
from agents.signal import Signal, neutral_signal


class MacroAgent(BaseAgent):
    """宏观周期 Agent（专家4组）"""

    signal_type = "macro"

    def __init__(self, config: Optional[dict] = None):
        super().__init__(name="宏观周期Agent", config=config or {})
        self.load_skills_from_domain("macro")

    def analyze(self, stock_code: str) -> Signal:
        self.log(f"开始宏观周期分析：{stock_code}")
        # TODO: 专家4组实现
        return neutral_signal(
            confidence=0.1,
            reasoning="宏观周期 Agent 待实现",
            source=self.name,
            stock_code=stock_code,
            signal_type=self.signal_type,
        )
