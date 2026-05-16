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

import asyncio
from typing import Dict, List, Optional
from agents.base import BaseAgent
from agents.agentscope_message import arbitration_result_to_msg, extract_stock_code
from agents.orchestrator.arbitration import ArbitrationEngine, ArbitrationResult
from agents.orchestrator.arbitration_strategy import create_arbitration_strategy
from agents.orchestrator.scope import AgentScopeOrchestrationRunner
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
        self.runner = AgentScopeOrchestrationRunner(config=config or {})
        self.arbitration_strategy = create_arbitration_strategy(config or {}, self.engine)
        self._expert_agents: List[BaseAgent] = []

    def register_expert(self, agent: BaseAgent):
        """注册一个专家 Agent"""
        self._expert_agents.append(agent)
        self.log(f"注册专家 Agent：{agent.name} (signal_type={agent.signal_type})")

    async def reply(self, msg):
        """AgentScope 调用入口：Msg -> analyze(stock_code) -> ArbitrationResult Msg。"""
        stock_code = extract_stock_code(msg)
        result = await asyncio.to_thread(self.analyze, stock_code)
        return arbitration_result_to_msg(result, name=self.name)

    def analyze(self, stock_code: str) -> ArbitrationResult:
        """
        编排入口：调用所有专家 Agent，收集信号，执行仲裁

        Args:
            stock_code: 股票代码

        Returns:
            ArbitrationResult: 仲裁结果
        """
        self.log(f"开始编排分析：{stock_code}")

        # 1. AgentScope 风格编排：每只股票独立作用域，并行调用所有专家 Agent
        scope = self.runner.run_stock(stock_code, self._expert_agents)
        bundle = scope.to_signal_bundle()

        for execution in scope.execution_results:
            if execution.succeeded and execution.signal:
                signal = execution.signal
                self.log(f"收到 {execution.agent_name} 信号：{signal.direction} ({signal.confidence:.0%})")
            else:
                self.log(
                    f"专家 {execution.agent_name} 执行{execution.status}：{execution.error}",
                    "error",
                )

        self.log(
            f"共收集 {len(bundle.signals)} 个信号 "
            f"(失败{scope.failed_count}，超时{scope.timeout_count}，无效{scope.invalid_count})"
        )

        # 2. 按配置选择规则仲裁或 LLM 仲裁框架
        result = self.arbitration_strategy.arbitrate(bundle, execution_trace=scope.to_dict())
        self.log(f"仲裁完成：{result.decision} / {result.direction} / {result.confidence:.0%}")

        return result

    def analyze_many(self, stock_codes: List[str]) -> Dict[str, ArbitrationResult]:
        """
        批量分析多只股票。

        每只股票仍使用独立 StockAnalysisScope，避免上下文、失败状态和 trace 串扰。
        """
        results: Dict[str, ArbitrationResult] = {}
        for stock_code in stock_codes:
            results[stock_code] = self.analyze(stock_code)
        return results
