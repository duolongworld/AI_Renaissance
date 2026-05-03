"""
资金流向 Agent - 专家3组

signal_type: fundflow
Skill 域: skills/fundflow/
核心能力：主力资金追踪、北向资金、聪明钱动向
"""

from typing import Optional
from agents.base import BaseAgent
from agents.signal import Signal, neutral_signal


class FundflowAgent(BaseAgent):
    """资金流向 Agent（专家3组）"""

    signal_type = "fundflow"

    def __init__(self, config: Optional[dict] = None):
        super().__init__(name="资金流向Agent", config=config or {})
        self.load_skills_from_domain("fundflow")

    def analyze(self, stock_code: str) -> Signal:
        self.log(f"开始资金流向分析：{stock_code}")
        # TODO: 专家3组实现
        return neutral_signal(
            confidence=0.1,
            reasoning="资金流向 Agent 待实现",
            source=self.name,
            stock_code=stock_code,
            signal_type=self.signal_type,
        )
