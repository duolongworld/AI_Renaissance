"""
端到端验证：7专家Signal → 场景选择 → 仲裁 → 推理报告

以 300476（胜宏科技）为标的，模拟三种市场场景，
走完整 analyze() 流程，验证架构可用性。

7个专家组严格对齐 TEAM.md 定义：
  1. 财务组 (financial)  2. 技术组 (technical)   3. 资金组 (fundflow)
  4. 宏观组 (macro)      5. 产业分析组 (industry) 6. 舆情组 (news)
  7. 风控组 (risk)

胜宏科技（Champion Asia）—— PCB/HDI 制造商，创业板科技股，
具有高成长性、较高波动性的特征，对电子产业周期和5G/AI需求敏感。
"""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.base import BaseAgent
from agents.orchestrator.agent import OrchestratorAgent
from agents.signal import Signal


class ScenarioMockAgent(BaseAgent):
    def __init__(self, name: str, signal_type: str, direction: str,
                 confidence: float, reasoning: str, signals_list: list = None):
        super().__init__(name=name, config={})
        self.signal_type = signal_type
        self._direction = direction
        self._confidence = confidence
        self._reasoning = reasoning
        self._signals = signals_list or []

    def analyze(self, stock_code: str) -> Signal:
        return Signal(
            direction=self._direction, confidence=self._confidence,
            reasoning=self._reasoning, source=self.name,
            signal_type=self.signal_type,
            stock_code=stock_code, signals=self._signals,
        )


# ================================================================
# 场景一：牛市场景
# ================================================================

def build_bull_market_agents():
    """牛市——AI需求爆发推动PCB订单增长"""
    return [
        # 1. 财务组
        ScenarioMockAgent("财务组", "financial", "neutral", 0.68,
            "2026Q1营收¥18.2亿(+28% YoY)，净利润¥3.6亿(+25% YoY)，"
            "受益于AI服务器HDI订单放量。PE=38x处于行业中位偏高，"
            "但高增速(PEG≈1.5)有一定支撑。综合判断：基本面强劲但估值不便宜。",
            ["营收+28%", "利润+25%", "PE 38x"]),
        # 2. 技术组
        ScenarioMockAgent("技术组", "technical", "bullish", 0.78,
            "胜宏科技日线站上60日均线(¥42.5)，均线多头排列(MA5>MA20>MA60)，"
            "MACD金叉红柱放大，OBV持续走高显示增量资金入场。"
            "综合判断：技术面量价配合，趋势向上确认。",
            ["均线多头排列", "MACD金叉", "OBV上升"]),
        # 3. 资金组
        ScenarioMockAgent("资金组", "fundflow", "bullish", 0.75,
            "近5日北向资金净流入胜宏科技¥2.8亿，主力资金净流入占比38%，"
            "两融余额稳步上升至4.2亿(+12% MoM)。"
            "综合判断：机构资金持续加仓，资金面支撑强劲。",
            ["北向资金流入", "主力净买入", "两融上升"]),
        # 4. 宏观组
        ScenarioMockAgent("宏观组", "macro", "bullish", 0.82,
            "2026年5月PMI回升至50.8，连续3个月扩张；"
            "国家大基金三期5000亿投资落地；AI算力基建政策持续加码。"
            "综合判断：经济温和复苏+产业政策红利，宏观面利多。",
            ["PMI连续扩张", "大基金三期", "AI基建政策"]),
        # 5. 产业分析组
        ScenarioMockAgent("产业分析组", "industry", "bullish", 0.72,
            "全球PCB产值2026年预计+8.5% YoY，AI服务器HDI板需求增速达35%；"
            "胜宏科技在全球HDI市场份额从4.2%升至5.8%，进入全球前十。"
            "上游铜箔价格平稳(-2%)，成本端压力可控。"
            "综合判断：行业景气上行，公司份额提升，产业面利多。",
            ["PCB产值+8.5%", "HDI需求+35%", "份额升至5.8%"]),
        # 6. 舆情组
        ScenarioMockAgent("舆情组", "news", "bullish", 0.60,
            "近期密集利好：英伟达GB300供应链认证通过，华为AI服务器PCB订单加码，"
            "泰国新工厂开工；股吧讨论热度上升，散户情绪偏乐观(68)。"
            "但需注意中美科技摩擦升温可能影响出口情绪。"
            "综合判断：舆情偏多但需关注尾部风险叙事。",
            ["英伟达认证", "华为订单", "泰国工厂", "散户情绪68"]),
        # 7. 风控组
        ScenarioMockAgent("风控组", "risk", "bullish", 0.72,
            "创业板波动率指数22.5（历史中位），信用利差95bp正常，"
            "电子板块Beta值1.3——风险环境中性偏乐观。"
            "综合判断：系统性风险可控，高Beta但无系统性风险。",
            ["波动率正常", "信用利差平稳", "系统性风险低"]),
    ]


# ================================================================
# 场景二：熊市场景
# ================================================================

def build_bear_market_agents():
    """熊市——AI投资退潮，PCB产能过剩，中美科技战升级"""
    return [
        ScenarioMockAgent("财务组", "financial", "bearish", 0.65,
            "Q2指引大幅下调：预计营收¥14亿(-22% YoY)，产能利用率降至62%；"
            "存货周转天数从68天升至95天，去库存压力加大。"
            "综合判断：基本面快速恶化，业绩下修风险显著。",
            ["Q2指引-22%", "产能利用率骤降", "存货积压"]),
        ScenarioMockAgent("技术组", "technical", "bearish", 0.72,
            "跌破60日均线(¥38.0)，均线空头排列，MACD死叉绿柱放大，"
            "日线形成头肩顶形态，颈线位¥35已破。成交量萎缩至日均55%。"
            "综合判断：技术面全面转空，缩量下跌无承接。",
            ["均线空头排列", "MACD死叉", "头肩顶破位"]),
        ScenarioMockAgent("资金组", "fundflow", "bearish", 0.68,
            "北向资金连续8日净流出累计¥5.6亿，主力净流出占比52%；"
            "两融余额骤降至2.8亿(-33% MoM)。"
            "综合判断：资金加速撤离，未见止跌信号。",
            ["北向资金流出", "主力净卖出", "两融骤降"]),
        ScenarioMockAgent("宏观组", "macro", "bearish", 0.78,
            "PMI降至48.2，电子信息产品出口-12% YoY；中美科技战升级，"
            "多家中资PCB企业被新增入实体清单。"
            "综合判断：宏观+产业周期双重下行，宏观面偏空。",
            ["PMI<50", "电子出口-12%", "实体清单"]),
        ScenarioMockAgent("产业分析组", "industry", "bearish", 0.70,
            "全球PCB产能过剩率升至12%（前值7%），价格战加剧；"
            "日本/东南亚PCB厂商降价抢单，HDI板ASP下降8% QoQ。"
            "胜宏科技泰国工厂投产延迟，新增产能面临消化压力。"
            "综合判断：行业周期见顶，竞争格局恶化，产业面偏空。",
            ["产能过剩12%", "ASP下降8%", "泰国厂延迟"]),
        ScenarioMockAgent("舆情组", "news", "bearish", 0.62,
            "利空消息集中：多家券商下调评级至'减持'，目标价从¥55降至¥30；"
            "大股东公告减持1.5%股本；美国对华PCB加征25%关税提案通过。"
            "股吧负面帖占比78%，散户恐慌情绪蔓延。"
            "综合判断：舆情全面偏空，市场信心崩塌。",
            ["券商下调评级", "大股东减持", "关税加征"]),
        ScenarioMockAgent("风控组", "risk", "bearish", 0.82,
            "创业板波动率飙升至35.2，电子板块Beta升至1.8；"
            "PCB行业信用利差扩大至210bp，汇率贬至7.38。"
            "综合判断：系统性+行业风险叠加，启动防御模式。",
            ["波动率>30", "Beta升至1.8", "行业信用利差扩大"]),
    ]


# ================================================================
# 场景三：震荡市场景
# ================================================================

def build_range_market_agents():
    """震荡市——AI主题消化涨幅，行业等待Q2财报验证"""
    return [
        ScenarioMockAgent("财务组", "financial", "neutral", 0.62,
            "Q1业绩符合预期(营收¥18亿+30% YoY)，Q2指引维持不变；"
            "但市场担忧AI订单持续性，对PE=35x是否合理存在分歧。"
            "综合判断：基本面稳固但缺少新向上催化剂。",
            ["Q1符合预期", "估值分歧"]),
        ScenarioMockAgent("技术组", "technical", "neutral", 0.55,
            "在¥38-¥44区间震荡16个交易日，布林带显著收窄，"
            "MACD在零轴附近反复交叉，成交量萎缩至日均60%。"
            "综合判断：无方向，箱体整理中，等待突破。",
            ["箱体震荡16日", "布林带收窄", "地量"]),
        ScenarioMockAgent("资金组", "fundflow", "neutral", 0.52,
            "近10日北向资金小幅净流出¥0.8亿，主力买卖比≈1.05接近平衡，"
            "两融余额维持在3.5亿上下。"
            "综合判断：资金面多空均衡，等待催化剂。",
            ["北向小幅流出", "主力买卖平衡"]),
        ScenarioMockAgent("宏观组", "macro", "neutral", 0.58,
            "PMI在49.8-50.3之间窄幅波动（连续2个月），"
            "电子产业周期处于'去库存尾部+新需求萌发'的模糊阶段。"
            "综合判断：宏观方向不明，经济在稳态中寻找方向。",
            ["PMI窄幅波动", "行业周期模糊"]),
        ScenarioMockAgent("产业分析组", "industry", "neutral", 0.56,
            "PCB行业整体平稳，但细分领域分化明显：AI服务器HDI需求仍强，"
            "消费电子PCB需求疲弱。上游铜箔价格小幅波动±2%。"
            "综合判断：行业分化格局，整体方向不明，需关注细分赛道。",
            ["AI需求强", "消费电子弱", "铜价平稳"]),
        ScenarioMockAgent("舆情组", "news", "neutral", 0.50,
            "近期新闻多空交织：华为追加AI服务器订单(利好)，"
            "英伟达延迟交付GPU可能影响配套PCB需求(中性偏空)，"
            "日本PCB厂商降价抢单(竞争压力)。散户情绪指数48中性。"
            "综合判断：舆情面方向分歧，无主导性情绪。",
            ["华为追加订单", "英伟达延迟交付", "日本竞争"]),
        ScenarioMockAgent("风控组", "risk", "neutral", 0.52,
            "创业板波动率22-26之间窄幅震荡，信用利差正常范围，"
            "Beta值1.4居中——风险水平正常，无明显方向性预警。"
            "综合判断：风险环境中性。",
            ["波动率中位", "信用利差正常"]),
    ]


# ================================================================
# 报告输出
# ================================================================

STOCK_CODE = "300476"
STOCK_NAME = "胜宏科技（300476）"

def print_section(title: str):
    print(); print("=" * 70); print(f"  {title}"); print("=" * 70)

def print_subsection(title: str):
    print(); print(f"  ▸ {title}"); print("  " + "-" * 66)


def run_scenario_test(name: str, agents: list, config: dict):
    print_section(f"场景: {name}")
    orchestrator = OrchestratorAgent(config=config)
    for agent in agents:
        orchestrator.register_expert(agent)

    print_subsection("7个专家组 Signal 清单")
    for agent in agents:
        signal = agent.analyze(STOCK_CODE)
        emoji = {"bullish": "📈", "bearish": "📉", "neutral": "➡️"}
        print(f"  {emoji.get(signal.direction, '  ')} "
              f"[{agent.signal_type:12s}] {agent.name} "
              f"方向={signal.direction:7s}  置信度={signal.confidence:.0%}")
        print(f"     {signal.reasoning[:100]}...")

    result = orchestrator.analyze(STOCK_CODE)

    print_section("📊 仲裁推理链（完整可追溯）")

    selection = result.scope_trace.get("scenario_selection", {}) if result.scope_trace else {}
    if selection and not selection.get("fallback"):
        print_subsection("🏷️ 场景选择（基于7个专家组Signal自动判断）")
        print(f"  选中场景: {selection.get('selected_display_name')}")
        print(f"  选择置信度: {selection.get('confidence'):.0%}")
        print(f"  信号来源: {selection.get('signal_sources', 'N/A')}")
        print(f"  选择理由: {selection.get('reasoning')}")
        print()
        print(f"  各场景匹配评分（v2 评分制）:")
        for check in selection.get("all_checks", []):
            score = check.get("match_score", 0)
            passed = check.get("passed_threshold", False)
            bar = "🟢" * min(int(score * 10), 10) + "⚪" * max(0, 10 - int(score * 10))
            status = "✓ 通过阈值" if passed else "✗ 未通过"
            print(f"    {bar} {check['display_name']}: {score:.2f} {status}")
            print(f"            {check['reason'][:120]}...")
    elif selection and selection.get("fallback"):
        print_subsection("⚠️ 场景选择降级")
        print(f"  原因: {selection.get('reasoning')}")
    else:
        print_subsection("⚖️ 场景选择")
        print(f"  当前场景: {orchestrator.engine.scenario.display_name}")

    print_subsection("📊 信号汇总")
    summary = result.signals_summary
    if summary:
        print(f"  总信号数: {summary.get('total', 0)}")
        print(f"  看多: {summary.get('bullish', 0)}  看空: {summary.get('bearish', 0)}  中性: {summary.get('neutral', 0)}")
        by_type = summary.get("by_type", {})
        if by_type:
            print(); print(f"  按类型分布:")
            for sig_type, counts in by_type.items():
                bullish = counts.get("bullish", 0)
                bearish = counts.get("bearish", 0)
                neutral = counts.get("neutral", 0)
                bar = "🟢" * bullish + "🔴" * bearish + "⚪" * neutral
                print(f"    {sig_type:12s} | {bar}  看多{bullish} 看空{bearish} 中性{neutral}")

    trace = result.scope_trace
    if trace:
        exec_summary = trace.get("summary", {})
        if exec_summary:
            print_subsection("🔍 执行追踪")
            print(f"  总Agent数: {exec_summary.get('total_agents', 0)}")
            print(f"  成功: {exec_summary.get('success_count', 0)}  "
                  f"失败: {exec_summary.get('failed_count', 0)}  "
                  f"超时: {exec_summary.get('timeout_count', 0)}  "
                  f"无效: {exec_summary.get('invalid_count', 0)}")

    print_subsection("🧠 完整推理链")
    chain = result.reasoning_chain
    if chain:
        for step in chain:
            print(f"  {step}")

    # ---- v8 标准化推理链展示 ----
    if result.standardized_chain:
        from agents.orchestrator.reasoning_chain import format_standardized_chain
        print_subsection("🔬 标准化推理链（共识/分歧/贡献追踪）")
        print(format_standardized_chain(result.standardized_chain))

    print_subsection("🎯 最终决策")
    print(f"  标的: {STOCK_NAME}")
    print(f"  决策: {result.decision.upper()}")
    print(f"  方向: {result.direction}")
    print(f"  综合置信度: {result.confidence:.0%}")
    print(f"  建议仓位: {result.position_ratio:.0%}")

    if result.risks:
        print_subsection("⚠️ 风险清单")
        for i, risk in enumerate(result.risks, 1):
            marker = "🔒 阻塞" if "🔒" in risk else "  提示"
            text = risk.replace("🔒 ", "")
            print(f"  {i}. [{marker}] {text}")


# ================================================================
# 主程序
# ================================================================
if __name__ == "__main__":
    print()
    print("╔" + "═" * 68 + "╗")
    print("║" + "  AI_Renaissance Orchestrator 端到端验证报告".center(60) + "║")
    print("║" + f"  标的: {STOCK_NAME}".center(62) + "║")
    print("║" + f"  7个专家组对齐 TEAM.md 架构".center(58) + "║")
    print("╚" + "═" * 68 + "╝")

    run_scenario_test("牛市场景（自动选择）",
        build_bull_market_agents(),
        config={"confidence_threshold": 0.6, "agent_timeout_seconds": 5})

    run_scenario_test("熊市场景（自动选择）",
        build_bear_market_agents(),
        config={"confidence_threshold": 0.6, "agent_timeout_seconds": 5})

    run_scenario_test("震荡市场景（自动选择）",
        build_range_market_agents(),
        config={"confidence_threshold": 0.6, "agent_timeout_seconds": 5})

    # 对比测试
    print_section("手动指定 vs 自动选择 对比")
    print(f"\n  震荡市信号 + 手动指定牛市 → 验证场景切换对决策的影响\n")

    orch_m = OrchestratorAgent(config={"scenario": "bull_market", "confidence_threshold": 0.6})
    for a in build_range_market_agents(): orch_m.register_expert(a)
    r_m = orch_m.analyze(STOCK_CODE)
    print(f"  🔧 手动牛市 → {orch_m.engine.scenario.display_name}")
    print(f"     决策: {r_m.decision} / {r_m.direction} / 仓位 {r_m.position_ratio:.0%}")

    orch_a = OrchestratorAgent(config={"confidence_threshold": 0.6})
    for a in build_range_market_agents(): orch_a.register_expert(a)
    r_a = orch_a.analyze(STOCK_CODE)
    sel = (r_a.scope_trace or {}).get("scenario_selection", {})
    print(f"  🤖 自动选择 → {sel.get('selected_display_name', 'N/A')}")
    print(f"     决策: {r_a.decision} / {r_a.direction} / 仓位 {r_a.position_ratio:.0%}")

    print("\n" + "=" * 70)
    print("  ✅ 端到端验证完成")
    print("=" * 70)
