"""
开发2组使用的 AgentScope 风格编排作用域。

本模块保持现有项目 Agent 契约不变：
已注册的专家 Agent 仍然暴露 analyze(stock_code)，并返回 Signal。
编排层负责每只股票的作用域隔离、并发扇出、超时控制、失败隔离，
以及供仲裁和调试使用的执行追踪。
"""

from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from loguru import logger

from agents.agentscope_message import (
    AgentScopeMessageError,
    msg_to_signal,
    stock_task_to_msg,
)
from agents.base import AgentContractError, BaseAgent
from agents.signal import Signal, SignalBundle


@dataclass
class AgentExecutionResult:
    """单个专家 Agent 在股票分析作用域内的执行追踪。"""

    agent_name: str
    signal_type: str
    status: str
    started_at: str
    finished_at: str
    duration_seconds: float
    signal: Optional[Signal] = None
    error: str = ""

    @property
    def succeeded(self) -> bool:
        return self.status == "success" and self.signal is not None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "signal_type": self.signal_type,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_seconds": round(self.duration_seconds, 4),
            "error": self.error,
            "signal": self.signal.to_dict() if self.signal else None,
        }


@dataclass
class StockAnalysisScope:
    """单只股票的一次独立编排作用域。"""

    stock_code: str
    config: Dict[str, Any] = field(default_factory=dict)
    run_id: str = field(default_factory=lambda: uuid4().hex)
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    finished_at: str = ""
    framework: str = "AgentScope"
    execution_results: List[AgentExecutionResult] = field(default_factory=list)

    @property
    def duration_seconds(self) -> float:
        if not self.finished_at:
            return 0.0
        started = datetime.fromisoformat(self.started_at)
        finished = datetime.fromisoformat(self.finished_at)
        return (finished - started).total_seconds()

    @property
    def success_count(self) -> int:
        return sum(1 for result in self.execution_results if result.succeeded)

    @property
    def failed_count(self) -> int:
        return sum(1 for result in self.execution_results if result.status == "failed")

    @property
    def timeout_count(self) -> int:
        return sum(1 for result in self.execution_results if result.status == "timeout")

    @property
    def invalid_count(self) -> int:
        return sum(1 for result in self.execution_results if result.status == "invalid")

    @property
    def signals(self) -> List[Signal]:
        return [result.signal for result in self.execution_results if result.succeeded]

    def finish(self, execution_results: List[AgentExecutionResult]) -> None:
        self.execution_results = execution_results
        self.finished_at = datetime.now().isoformat()

    def to_signal_bundle(self) -> SignalBundle:
        bundle = SignalBundle(stock_code=self.stock_code)
        for signal in self.signals:
            bundle.add(signal)
        return bundle

    def to_dict(self) -> Dict[str, Any]:
        total = len(self.execution_results)
        return {
            "run_id": self.run_id,
            "framework": self.framework,
            "stock_code": self.stock_code,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_seconds": round(self.duration_seconds, 4),
            "summary": {
                "total_agents": total,
                "success_count": self.success_count,
                "failed_count": self.failed_count,
                "timeout_count": self.timeout_count,
                "invalid_count": self.invalid_count,
            },
            "execution_results": [result.to_dict() for result in self.execution_results],
        }


class AgentScopeOrchestrationRunner:
    """
    OrchestratorAgent 的专家扇出运行器。

    通过 BaseAgent 继承的 AgentBase.__call__() 调用专家，并保持项目
    业务契约仍然是 analyze(stock_code) -> Signal。
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        orchestration_config = self.config.get("orchestration", {})
        self.agent_timeout_seconds = float(
            orchestration_config.get(
                "agent_timeout_seconds",
                self.config.get("agent_timeout_seconds", 30.0),
            )
        )
        logger.info(
            "[AgentScopeRunner] 初始化完成 - "
            f"timeout={self.agent_timeout_seconds}s"
        )

    def run_stock(self, stock_code: str, agents: List[BaseAgent]) -> StockAnalysisScope:
        """在独立作用域内运行一只股票的所有已注册专家 Agent。"""
        scope = StockAnalysisScope(
            stock_code=stock_code,
            config=self.config,
        )
        results = self._run_coroutine_sync(self._run_agents(scope, agents))
        scope.finish(results)
        return scope

    async def _run_agents(
        self,
        scope: StockAnalysisScope,
        agents: List[BaseAgent],
    ) -> List[AgentExecutionResult]:
        tasks = [self._run_one_agent(scope, agent) for agent in agents]
        if not tasks:
            return []
        return await asyncio.gather(*tasks)

    async def _run_one_agent(
        self,
        scope: StockAnalysisScope,
        agent: BaseAgent,
    ) -> AgentExecutionResult:
        started_at = datetime.now().isoformat()
        start_time = time.perf_counter()
        try:
            signal = await asyncio.wait_for(
                self._analyze_agent(scope, agent),
                timeout=self.agent_timeout_seconds,
            )
            duration = time.perf_counter() - start_time
            finished_at = datetime.now().isoformat()

            if not isinstance(signal, Signal):
                return AgentExecutionResult(
                    agent_name=agent.name,
                    signal_type=agent.signal_type,
                    status="invalid",
                    started_at=started_at,
                    finished_at=finished_at,
                    duration_seconds=duration,
                    error=f"Agent 返回 {type(signal).__name__}，预期为 Signal",
                )

            if not signal.stock_code:
                signal.stock_code = scope.stock_code

            return AgentExecutionResult(
                agent_name=agent.name,
                signal_type=agent.signal_type,
                status="success",
                started_at=started_at,
                finished_at=finished_at,
                duration_seconds=duration,
                signal=signal,
            )
        except asyncio.TimeoutError:
            duration = time.perf_counter() - start_time
            return AgentExecutionResult(
                agent_name=agent.name,
                signal_type=agent.signal_type,
                status="timeout",
                started_at=started_at,
                finished_at=datetime.now().isoformat(),
                duration_seconds=duration,
                error=f"Agent 执行超过 {self.agent_timeout_seconds:.2f}s 后超时",
            )
        except Exception as exc:
            duration = time.perf_counter() - start_time
            status = (
                "invalid"
                if isinstance(exc, (AgentContractError, AgentScopeMessageError))
                else "failed"
            )
            return AgentExecutionResult(
                agent_name=agent.name,
                signal_type=agent.signal_type,
                status=status,
                started_at=started_at,
                finished_at=datetime.now().isoformat(),
                duration_seconds=duration,
                error=str(exc),
            )

    async def _analyze_agent(self, scope: StockAnalysisScope, agent: BaseAgent) -> Signal:
        """Invoke one expert through its native AgentScope __call__."""
        task_msg = stock_task_to_msg(
            scope.stock_code,
            context={
                "scope_run_id": scope.run_id,
                "agent_name": agent.name,
                "signal_type": agent.signal_type,
            },
        )
        result_msg = await agent(task_msg)
        return msg_to_signal(result_msg)

    def _run_coroutine_sync(self, coroutine):
        """
        从同步项目入口运行异步编排协程。

        Flask 和 CLI 通常没有正在运行的事件循环。如果未来调用方在已有
        事件循环中调用 OrchestratorAgent，则在辅助线程中创建独立循环，
        以保持同步公开 API 不变。
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coroutine)

        result_holder: Dict[str, Any] = {}
        error_holder: Dict[str, BaseException] = {}

        def runner() -> None:
            try:
                result_holder["result"] = asyncio.run(coroutine)
            except BaseException as exc:  # pragma: no cover - 防御性路径
                error_holder["error"] = exc

        thread = threading.Thread(target=runner, daemon=True)
        thread.start()
        thread.join()

        if "error" in error_holder:
            raise error_holder["error"]
        return result_holder["result"]
