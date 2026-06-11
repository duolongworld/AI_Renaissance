"""
Orchestrator Agent —— 编排仲裁入口

开发2组负责。以桥水经济机器模型为统一方法论框架，
基于专家组 Signal 自动选择市场场景（牛市/熊市/震荡市），
将对应场景的专家权重配置加载至仲裁引擎，完成信号融合与决策输出。
详细方法论见开发2组 SKILL.md。

核心职责：
  1. 收集 7 个专家 Agent 的 Signal
  2. 基于 Signal 自动选择市场场景（ScenarioSelector）
  3. 场景权重加载至仲裁引擎（ArbitrationEngine）
  4. 加权聚合与方向判定
  5. 风险约束（区分阻塞性/信息性风险）
  6. 仓位建议
  7. 推理链生成（含权重追溯，白箱可审计）
  8. 最终报告输出

原 arbitration/engine.py 的仲裁逻辑已迁移至此。
"""

import asyncio
from typing import Dict, List, Optional
from agents.base import BaseAgent
from agents.agentscope_message import arbitration_result_to_msg, extract_stock_code
from agents.orchestrator.arbitration import ArbitrationEngine, ArbitrationResult
from agents.orchestrator.arbitration_strategy import create_arbitration_strategy
from agents.orchestrator.scope import AgentScopeOrchestrationRunner
from agents.orchestrator.scenarios import get_scenario, create_default_scenario, list_scenarios
from agents.orchestrator.scenario_selector import ScenarioSelector
from loguru import logger


class OrchestratorAgent(BaseAgent):
    """
    编排 Agent（开发2组）

    信号收集 → 权重聚合 → 方向判定 → 风险约束 → 推理链生成 → 最终报告
    """

    signal_type = ""  # Orchestrator 不产出 signal_type

    def __init__(self, config: Optional[dict] = None):
        super().__init__(name="OrchestratorAgent", config=config or {})

        cfg = config or {}

        # -------------------------------------------------------
        # 场景初始化 —— 松耦合多场景仲裁的核心入口
        #
        # 优先级:
        #   1. 手动指定: config["scenario"] = "bull_market"
        #   2. 自动选择: analyze() 收集完专家信号后由 ScenarioSelector 判断
        #   3. 默认等权: 以上两者都没有时使用 DefaultScenario
        #
        # 场景选择基于专家组 Signal 而非原始市场数据，
        # 保证各组做各组最专业的事，不越界不重复。
        # -------------------------------------------------------
        self._manual_scenario_name = cfg.get("scenario")   # None = 未手动指定
        self._auto_select_enabled = cfg.get("auto_select_scenario", True)

        # 创建默认场景（analyze 时可能被自动选择覆盖）
        scenario = create_default_scenario()
        if self._manual_scenario_name:
            loaded = get_scenario(self._manual_scenario_name)
            if loaded:
                scenario = loaded
                logger.info(f"[Orchestrator] 手动指定场景: {scenario.display_name}")
            else:
                logger.warning(
                    f"[Orchestrator] 未找到场景 '{self._manual_scenario_name}'，"
                    f"可用场景: {list(list_scenarios().keys())}，回退到默认等权"
                )

        self.engine = ArbitrationEngine(
            confidence_threshold=cfg.get("confidence_threshold", 0.6),
            scenario=scenario,
        )
        self.runner = AgentScopeOrchestrationRunner(config=cfg)
        self.arbitration_strategy = create_arbitration_strategy(cfg, self.engine)
        self._expert_agents: List[BaseAgent] = []

        # 场景选择器 —— 基于专家 Signal 自动选择场景
        self._selector = ScenarioSelector()
        logger.info(
            f"[Orchestrator] 场景选择器已就绪，"
            f"可识别场景: {self._selector.list_available_scenarios()}"
        )

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
        编排入口：调用所有专家 Agent，收集信号，选择场景，执行仲裁。

        Args:
            stock_code: 股票代码

        场景选择优先级:
            1. 手动指定 (config["scenario"]) → 无视专家信号
            2. 自动选择 (默认开启) → 收集完专家信号后由 ScenarioSelector 判断
            3. 默认等权 → 以上两者都没有

        Returns:
            ArbitrationResult: 仲裁结果（含场景选择报告）
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

        # ---- 自动场景选择（基于专家信号） ----
        selection_report = None
        if (
            not self._manual_scenario_name           # 无手动指定
            and self._auto_select_enabled             # 自动选择已开启
            and len(bundle.signals) > 0               # 有专家信号
        ):
            scenario, selection_report = self._selector.select_scenario(bundle.signals)
            self.engine.scenario = scenario  # 动态切换场景
            self.log(
                f"场景选择 → {scenario.display_name} "
                f"(置信度: {selection_report['confidence']:.0%})"
            )
            if selection_report.get("fallback"):
                self.log(f"⚠️ 场景选择降级: {selection_report['reasoning']}", "warning")

        # 2. 按配置选择规则仲裁或 LLM 仲裁框架
        result = self.arbitration_strategy.arbitrate(bundle, execution_trace=scope.to_dict())

        # 3. 将场景选择报告附加到结果中（可追溯）
        if selection_report:
            if result.scope_trace:
                result.scope_trace["scenario_selection"] = selection_report

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
