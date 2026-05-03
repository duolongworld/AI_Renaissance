"""
Orchestrator Agent - 编排仲裁

开发2组负责。不加载 Skill，职责：
  1. 收集7个专家Agent的Signal
  2. 权重聚合
  3. 方向判定
  4. 风险约束
  5. 推理链生成
  6. 最终报告输出

原 arbitration/engine.py 的仲裁逻辑迁移至此。
"""

from typing import List, Dict, Any, Optional
from agents.base import BaseAgent
from agents.signal import Signal, SignalBundle
from agents.orchestrator.arbitration import ArbitrationEngine, ArbitrationResult
from loguru import logger


class OrchestratorAgent(BaseAgent):
    """
    编排 Agent（开发2组）

    信号收集 → 权重聚合 → 方向判定 → 风险约束 → 推理链生成 → 最终报告
    """

    signal_type = ""  # Orchestrator 不产出 signal_type

    def __init__(self, config: Optional[dict] = None):
        super().__init__(name="OrchestratorAgent", config=config or {})
        self.engine = ArbitrationEngine(
            confidence_threshold=config.get("confidence_threshold", 0.6) if config else 0.6,
            bullish_weight=config.get("bullish_weight", 1.0) if config else 1.0,
            bearish_weight=config.get("bearish_weight", 1.0) if config else 1.0,
            risk_coefficient=config.get("risk_coefficient", 0.2) if config else 0.2,
        )
        self._expert_agents: List[BaseAgent] = []

    def register_expert(self, agent: BaseAgent):
        """注册一个专家 Agent"""
        self._expert_agents.append(agent)
        self.log(f"注册专家 Agent：{agent.name} (signal_type={agent.signal_type})")

    def analyze(self, stock_code: str) -> ArbitrationResult:
        """
        编排入口：调用所有专家 Agent，收集信号，执行仲裁

        Args:
            stock_code: 股票代码

        Returns:
            ArbitrationResult: 仲裁结果
        """
        self.log(f"开始编排分析：{stock_code}")

        # 1. 收集所有专家 Agent 的 Signal
        bundle = SignalBundle(stock_code=stock_code)
        for agent in self._expert_agents:
            try:
                signal = agent.analyze(stock_code)
                bundle.add(signal)
                self.log(f"收到 {agent.name} 信号：{signal.direction} ({signal.confidence:.0%})")
            except Exception as e:
                self.log(f"专家 {agent.name} 分析失败：{e}", "error")

        self.log(f"共收集 {len(bundle.signals)} 个信号")

        # 2. 执行仲裁
        result = self.engine.arbitrate(bundle)
        self.log(f"仲裁完成：{result.decision} / {result.direction} / {result.confidence:.0%}")

        return result
