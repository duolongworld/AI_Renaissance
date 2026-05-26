"""
AI Renaissance 主入口

运行方式：
    python main.py --stock 000001
    python main.py --stock 600519,000858  # 批量分析
"""

import argparse
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from agents.orchestrator.agent import OrchestratorAgent
from loguru import logger

# 配置日志
logger.add("logs/arbitration.log", rotation="10 MB", retention="7 days")


# ── 7个专家Agent注册表 ──────────────────────────────────
# 格式：{"显示名称": {"module": "模块路径", "class": "类名", "owner": "负责组"}}
EXPERT_AGENTS = {
    "财务分析Agent": {
        "module": "agents.financial.agent",
        "class": "FinancialAgent",
        "owner": "专家1组",
        "description": "财报质量七步验证链，利润真实性分析",
        "signal_type": "financial",
    },
    "技术指标Agent": {
        "module": "agents.technical.agent",
        "class": "TechnicalAgent",
        "owner": "专家2组",
        "description": "量价技术指标、趋势识别、支撑压力位",
        "signal_type": "technical",
    },
    "资金流向Agent": {
        "module": "agents.fundflow.agent",
        "class": "FundflowAgent",
        "owner": "专家3组",
        "description": "主力资金追踪、北向资金、聪明钱动向",
        "signal_type": "fundflow",
    },
    "宏观周期Agent": {
        "module": "agents.macro.agent",
        "class": "MacroAgent",
        "owner": "专家4组",
        "description": "利率/汇率/PMI解读，大周期位置判断",
        "signal_type": "macro",
    },
    "行业景气Agent": {
        "module": "agents.industry.agent",
        "class": "IndustryAgent",
        "owner": "专家5组",
        "description": "产业链景气度、行业拐点、竞争格局",
        "signal_type": "industry",
    },
    "舆情情感Agent": {
        "module": "agents.news_agent.agent",
        "class": "NewsAgent",
        "owner": "专家6组",
        "description": "新闻情感分析、社交情绪追踪、情绪交易信号",
        "signal_type": "news",
    },
    "风险预警Agent": {
        "module": "agents.risk.agent",
        "class": "RiskAgent",
        "owner": "专家7组",
        "description": "尾部风险识别、仓位上限、守住不爆仓的底线",
        "signal_type": "risk",
    },
}


def main():
    parser = argparse.ArgumentParser(description="AI Renaissance 多智能体投资决策引擎")
    parser.add_argument("--stock", type=str, required=True, help="股票代码，多个用逗号分隔")
    parser.add_argument("--config", type=str, default="config/default.yaml", help="配置文件路径")
    parser.add_argument("--agents", type=str, default="", help="指定启用的Agent，逗号分隔（默认全部）")
    args = parser.parse_args()

    # 解析股票代码
    stock_codes = [c.strip() for c in args.stock.split(",")]
    logger.info(f"开始分析股票：{stock_codes}")

    # 加载配置
    config = load_config(args.config)

    # 初始化 Orchestrator Agent
    orchestrator = OrchestratorAgent(config=config)

    # 注册专家Agent
    enabled_agents = [a.strip() for a in args.agents.split(",") if a.strip()] if args.agents else None
    registered_count = register_experts(orchestrator, config, enabled_agents)

    if registered_count == 0:
        logger.error("没有可用的专家Agent，退出")
        sys.exit(1)

    logger.info(f"已注册 {registered_count} 个专家Agent")

    # 遍历每只股票。Orchestrator 内部会为每只股票创建独立 AgentScope 编排 scope。
    results = orchestrator.analyze_many(stock_codes)
    for stock_code in stock_codes:
        print(f"\n{'='*60}")
        print(f"📈 分析股票：{stock_code}")
        print(f"{'='*60}")

        # 输出结果
        print_result(results[stock_code])

    logger.info("分析完成")


def load_config(config_path: str) -> dict:
    """加载配置文件"""
    import yaml
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logger.warning(f"配置文件 {config_path} 不存在，使用默认配置")
        return {
            "confidence_threshold": 0.6,
            "bullish_weight": 1.0,
            "bearish_weight": 1.0,
            "risk_coefficient": 0.2,
        }


def register_experts(orchestrator: OrchestratorAgent, config: dict, enabled_agents=None) -> int:
    """
    动态注册专家Agent到Orchestrator

    Args:
        orchestrator: 编排Agent
        config: 配置字典
        enabled_agents: 指定启用的Agent列表（None=全部启用）

    Returns:
        成功注册的Agent数量
    """
    import importlib

    count = 0
    for name, info in EXPERT_AGENTS.items():
        # 如果指定了启用列表，只加载列表中的
        if enabled_agents and name not in enabled_agents:
            logger.info(f"跳过未启用的Agent：{name}")
            continue

        try:
            mod = importlib.import_module(info["module"])
            agent_class = getattr(mod, info["class"])
            agent = agent_class(config=config)
            orchestrator.register_expert(agent)
            count += 1
            logger.info(f"注册专家Agent：{name}（{info['owner']}）")
        except Exception as e:
            logger.error(f"加载专家Agent [{name}] 失败：{e}")

    return count


def print_result(result):
    """打印仲裁结果"""
    decision_emoji = {
        "buy": "🟢 建议买入",
        "sell": "🔴 建议卖出",
        "hold": "🟡 建议持有",
        "wait": "⚪ 建议观望",
    }

    direction_emoji = {
        "bullish": "📈 看多",
        "bearish": "📉 看空",
        "neutral": "➡️ 中性",
    }

    print(f"\n🎯 决策：{decision_emoji.get(result.decision, result.decision)}")
    print(f"📊 方向：{direction_emoji.get(result.direction, result.direction)}")
    print(f"📈 置信度：{result.confidence:.1%}")
    print(f"💼 建议仓位：{result.position_ratio:.0%}")

    print(f"\n📝 推理链：")
    for line in result.reasoning_chain:
        print(f"  {line}")

    if result.risks:
        print(f"\n⚠️ 风险提示：")
        for risk in result.risks:
            print(f"  {risk}")

    print(f"\n📊 信号汇总：")
    summary = result.signals_summary
    print(f"  总计：{summary.get('total', 0)}个信号")
    print(f"  看多：{summary.get('bullish', 0)}个")
    print(f"  看空：{summary.get('bearish', 0)}个")
    print(f"  中性：{summary.get('neutral', 0)}个")

    if getattr(result, "scope_trace", None):
        trace_summary = result.scope_trace.get("summary", {})
        print(f"\n🧭 编排追踪：")
        print(f"  注册Agent：{trace_summary.get('total_agents', 0)}个")
        print(f"  成功：{trace_summary.get('success_count', 0)}个")
        print(f"  失败：{trace_summary.get('failed_count', 0)}个")
        print(f"  超时：{trace_summary.get('timeout_count', 0)}个")
        print(f"  无效：{trace_summary.get('invalid_count', 0)}个")


if __name__ == "__main__":
    main()
