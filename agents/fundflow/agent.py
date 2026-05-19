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
        self.load_skills_from_domain("data")

    def analyze(self, stock_code: str, target_date: str = None) -> Signal:
        """
        资金流向分析：调用 crowding_state2x2 skill 的 build_signal() 构建信号。

        Args:
            stock_code: 股票代码，如 "600519"
            target_date: 可选目标日期 "YYYY-MM-DD"，默认取最新

        Returns:
            Signal: 标准化的资金流向信号
        """
        self.log(f"开始资金流向分析：{stock_code}")

        try:
            from skills.fundflow.crowding_state2x2.scripts.compute_state2x2_v2 import (
                load_stock_data,
                build_signal,
            )

            # 加载数据
            df = load_stock_data(stock_code)
            self.log(f"数据加载完成，共 {len(df)} 行")

            # 构建信号
            result = build_signal(stock_code, df, target_date)
            signal_dict = result[0]  # (signal_dict, flow_z, crowding_pct, df)

            # 将 skill 返回的 dict 转为标准 Signal 对象
            signal = Signal.from_dict(signal_dict)
            signal.source = self.name
            signal.signal_type = self.signal_type
            signal.stock_code = stock_code

            self.log(
                f"State2x2 诊断完成：{signal.direction} "
                f"(confidence={signal.confidence:.0%}, "
                f"state={signal.meta.get('state2x2_detail', {}).get('state_label', 'N/A')})"
            )
            return signal

        except ImportError as e:
            self.log(f"crowding_state2x2 skill 导入失败：{e}", "error")
            return neutral_signal(
                confidence=0.1,
                reasoning=f"资金流向 skill 加载失败：{e}",
                source=self.name,
                stock_code=stock_code,
                signal_type=self.signal_type,
            )

        except Exception as e:
            self.log(f"资金流向分析异常：{e}", "error")
            return neutral_signal(
                confidence=0.1,
                reasoning=f"资金流向分析失败：{e}",
                source=self.name,
                stock_code=stock_code,
                signal_type=self.signal_type,
            )
