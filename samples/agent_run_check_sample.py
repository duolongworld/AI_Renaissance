"""本地 Agent 运行检查样例。"""

from __future__ import annotations

import argparse
import importlib
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agents.signal import Signal


@dataclass(frozen=True)
class AgentSpec:
    key: str
    label: str
    module: str
    class_name: str
    implemented: bool


@dataclass
class AgentRun:
    key: str
    status: str
    elapsed_seconds: float
    signal: Signal | None = None
    error: str = ""


# 这个列表只服务当前样例；正式 Agent 注册仍以项目主流程为准。
AGENT_SPECS = {
    "financial": AgentSpec("financial", "财务", "agents.financial.agent", "FinancialAgent", False),
    "technical": AgentSpec("technical", "技术", "agents.technical.agent", "TechnicalAgent", False),
    "fundflow": AgentSpec("fundflow", "资金", "agents.fundflow.agent", "FundflowAgent", False),
    "macro": AgentSpec("macro", "宏观", "agents.macro.agent", "MacroAgent", False),
    "industry": AgentSpec("industry", "行业", "agents.industry.agent", "IndustryAgent", False),
    "news": AgentSpec("news", "舆情", "agents.news_agent.agent", "NewsAgent", True),
    "risk": AgentSpec("risk", "风险", "agents.risk.agent", "RiskAgent", False),
}


SAMPLE_AGENT_CONFIG = {
    "pages": 1,
    "fetch_content": False,
}

TABLE_SEPARATOR = "-" * 120


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="逐个运行专家 Agent，并打印 Signal 摘要。"
    )
    parser.add_argument("--stock", required=True, help="股票代码，例如 600519")
    parser.add_argument(
        "--agents",
        default=",".join(AGENT_SPECS),
        help="要检查的 Agent key，多个用英文逗号分隔。默认检查全部。",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="显示 Agent 运行日志。",
    )
    return parser.parse_args()


def select_agent_specs(agent_keys: str) -> list[AgentSpec]:
    selected = []
    unknown = []

    for raw_key in agent_keys.split(","):
        key = raw_key.strip()
        if not key:
            continue
        spec = AGENT_SPECS.get(key)
        if spec is None:
            unknown.append(key)
        else:
            selected.append(spec)

    if unknown:
        valid = ", ".join(AGENT_SPECS)
        raise ValueError(f"Unknown agent key(s): {', '.join(unknown)}. Valid keys: {valid}")
    if not selected:
        raise ValueError("No agents selected.")

    return selected


def load_agent(spec: AgentSpec, config: dict[str, Any]):
    module = importlib.import_module(spec.module)
    agent_class = getattr(module, spec.class_name)
    return agent_class(config=config)


def run_agent(spec: AgentSpec, stock_code: str, config: dict[str, Any]) -> AgentRun:
    start = time.perf_counter()
    try:
        agent = load_agent(spec, config)
        signal = agent.analyze(stock_code)
        elapsed = time.perf_counter() - start
        if not isinstance(signal, Signal):
            return AgentRun(
                key=spec.key,
                status="invalid",
                elapsed_seconds=elapsed,
                error=f"Expected Signal, got {type(signal).__name__}",
            )
        return AgentRun(
            key=spec.key,
            status="ok",
            elapsed_seconds=elapsed,
            signal=signal,
        )
    except Exception as exc:
        elapsed = time.perf_counter() - start
        return AgentRun(
            key=spec.key,
            status="failed",
            elapsed_seconds=elapsed,
            error=str(exc),
        )


def shorten(text: str, max_len: int = 56) -> str:
    text = " ".join((text or "").split())
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def spec_name(spec: AgentSpec) -> str:
    return f"{spec.label}({spec.key})"


def signal_type_text(signal_type: str) -> str:
    labels = {
        "financial": "财务",
        "technical": "技术",
        "fundflow": "资金",
        "macro": "宏观",
        "industry": "行业",
        "news": "舆情",
        "risk": "风险",
    }
    label = labels.get(signal_type)
    return f"{label}({signal_type})" if label else signal_type


def direction_text(direction: str) -> str:
    labels = {
        "bullish": "看多",
        "bearish": "看空",
        "neutral": "中性",
    }
    label = labels.get(direction)
    return f"{label}({direction})" if label else direction


def signal_summary(signal: Signal, implemented: bool) -> str:
    if not implemented:
        return shorten(signal.reasoning)

    if signal.signal_type == "news":
        total = signal.meta.get("total_posts_analyzed", 0)
        bullish = signal.meta.get("bullish_count", 0)
        bearish = signal.meta.get("bearish_count", 0)
        neutral = signal.meta.get("neutral_count", 0)
        return (
            f"基于帖子标题和列表指标，分析 {total} 条帖子，"
            f"看多 {bullish} 条，看空 {bearish} 条，中性 {neutral} 条"
        )

    return shorten(signal.reasoning)


def disable_agent_logs() -> None:
    try:
        from loguru import logger
    except ModuleNotFoundError:
        return
    logger.remove()


def print_run_header(stock_code: str, specs: list[AgentSpec], args: argparse.Namespace) -> None:
    print("Agent 运行检查样例")
    print(f"股票代码: {stock_code}")
    print(f"检查对象: {', '.join(spec_name(spec) for spec in specs)}")
    print("说明: 只检查 Agent 运行状态和 Signal 摘要，不做仲裁或最终决策")
    print()


def print_results(runs: list[AgentRun]) -> None:
    header = (
        f"{'Agent':<16} {'运行状态':<8} {'实现状态':<8} {'耗时':>7} "
        f"{'信号类型':<15} {'方向':<16} {'置信度':>6}  推理摘要"
    )
    print(header)
    print(TABLE_SEPARATOR)

    for run in runs:
        if run.signal is None:
            run_status = "失败" if run.status == "failed" else "无效"
            print(
                f"{run.key:<16} {run_status:<8} {'-':<8} {run.elapsed_seconds:>6.2f}s "
                f"{'-':<15} {'-':<16} {'-':>6}  {shorten(run.error)}"
            )
            continue

        signal = run.signal
        spec = AGENT_SPECS.get(run.key)
        implemented = spec.implemented if spec else True
        implementation_state = "已实现" if implemented else "待实现"
        direction = direction_text(signal.direction) if implemented else "-"
        confidence = f"{signal.confidence:>5.0%}" if implemented else "     -"
        signal_type = signal_type_text(signal.signal_type)

        print(
            f"{spec_name(spec) if spec else run.key:<16} {'成功':<8} {implementation_state:<8} "
            f"{run.elapsed_seconds:>6.2f}s {signal_type:<15} {direction:<16} "
            f"{confidence:>6}  {signal_summary(signal, implemented)}"
        )

    ok_count = sum(1 for run in runs if run.status == "ok")
    failed_count = sum(1 for run in runs if run.status == "failed")
    invalid_count = sum(1 for run in runs if run.status == "invalid")
    print()
    print(f"汇总: 成功={ok_count}, 失败={failed_count}, 无效={invalid_count}")


def main() -> int:
    args = parse_args()
    if not args.verbose:
        disable_agent_logs()

    try:
        specs = select_agent_specs(args.agents)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    print_run_header(args.stock, specs, args)
    runs = [run_agent(spec, args.stock, SAMPLE_AGENT_CONFIG) for spec in specs]
    print_results(runs)

    return 1 if any(run.status != "ok" for run in runs) else 0


if __name__ == "__main__":
    raise SystemExit(main())
