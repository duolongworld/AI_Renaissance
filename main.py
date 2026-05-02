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

from agents import load_agents
from agents.signal import SignalBundle
from arbitration.engine import ArbitrationEngine
from loguru import logger

# 配置日志
logger.add("logs/arbitration.log", rotation="10 MB", retention="7 days")


def main():
    parser = argparse.ArgumentParser(description="AI Renaissance 多智能体投资决策引擎")
    parser.add_argument("--stock", type=str, required=True, help="股票代码，多个用逗号分隔")
    parser.add_argument("--config", type=str, default="config/default.yaml", help="配置文件路径")
    args = parser.parse_args()

    # 解析股票代码
    stock_codes = [c.strip() for c in args.stock.split(",")]
    logger.info(f"开始分析股票：{stock_codes}")

    # 加载配置文件
    config = load_config(args.config)

    # 初始化仲裁引擎
    engine = ArbitrationEngine(
        confidence_threshold=config.get("confidence_threshold", 0.6),
        bullish_weight=config.get("bullish_weight", 1.0),
        bearish_weight=config.get("bearish_weight", 1.0),
    )

    # 遍历每只股票
    for stock_code in stock_codes:
        print(f"\n{'='*60}")
        print(f"📈 分析股票：{stock_code}")
        print(f"{'='*60}")

        # 收集所有Agent的信号
        signal_bundle = collect_signals(stock_code, config)

        # 执行仲裁
        result = engine.arbitrate(signal_bundle, trend_direction=None)

        # 输出结果
        print_result(result)

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
            "agents": [],  # 要启用的Agent列表
        }


def collect_signals(stock_code: str, config: dict) -> SignalBundle:
    """Collect signals from all enabled agents."""
    from agents.signal import SignalBundle

    bundle = SignalBundle(stock_code=stock_code)
    enabled_agents = config.get("agents")

    try:
        agents = load_agents(enabled_agents=enabled_agents)
    except Exception as e:
        logger.error(f"加载Agent列表失败：{e}")
        return bundle

    for agent in agents:
        try:
            signal = agent.analyze(stock_code)
            bundle.add(signal)
            logger.info(f"[{signal.source}] 信号已收集：{signal.direction} ({signal.confidence:.1%})")
        except Exception as e:
            logger.error(f"[{agent.name}] 信号收集失败：{e}")

    return bundle


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


if __name__ == "__main__":
    main()
