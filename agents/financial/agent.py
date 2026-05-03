"""
财务分析 Agent - 专家1组

signal_type: financial
Skill 域: skills/financial/
核心能力：财报质量七步验证链
"""

from typing import Optional
from agents.base import BaseAgent
from agents.signal import Signal, bullish_signal, bearish_signal, neutral_signal


class FinancialAgent(BaseAgent):
    """
    财务分析 Agent（专家1组）

    加载 skills/financial/ 下所有 Skill，
    对指定股票进行深度财报分析，输出 financial 类型的 Signal。
    """

    signal_type = "financial"

    def __init__(self, config: Optional[dict] = None):
        super().__init__(name="财务分析Agent", config=config or {})
        # 启动时自动加载 financial 领域的所有 Skill
        self.load_skills_from_domain("financial")

    def analyze(self, stock_code: str) -> Signal:
        """
        分析指定股票的财报质量

        Args:
            stock_code: 股票代码

        Returns:
            标准 Signal 对象（signal_type="financial"）
        """
        self.log(f"开始财报分析：{stock_code}")

        # TODO: 专家1组实现具体分析逻辑
        # 1. 通过 data_sources 获取财务数据
        # 2. 按 Skill 规则执行七步验证链
        # 3. 封装成 Signal 返回

        return neutral_signal(
            confidence=0.1,
            reasoning="财务分析 Agent 待实现",
            source=self.name,
            stock_code=stock_code,
            signal_type=self.signal_type,
        )
