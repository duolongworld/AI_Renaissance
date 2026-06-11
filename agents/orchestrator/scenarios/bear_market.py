"""
熊市场景 —— 下降趋势中的专家权重配置。

方法论依据：
  桥水经济机器模型：风险溢价扩张阶段。增长方向可能下降或上升
  （滞胀或衰退），但风险溢价扩张是共同特征。对应桥水框架中的
  "收缩期"——风险控制优先于收益获取。
  权重逻辑由因子研究交叉验证（QuantPedia、AQR 动量崩溃、CEPR）。

核心理念：
  每个权重数值均附带可追溯的研究理由，用户可阅读理由后自行判断是否采纳。
"""

from typing import Dict, List, Tuple, Optional, TYPE_CHECKING

from agents.orchestrator.scenario_profile import ScenarioProfile

if TYPE_CHECKING:
    from agents.signal import Signal


class BearMarketScenario(ScenarioProfile):
    """
    熊市场景配置 —— 研究驱动的权重方法论。

    === 方法论来源 ===

    1. QuantPedia 因子表现研究：价值(HML)、盈利(RMW)、投资(CMA)因子
       在熊市中收益高度正显著，牛市收益接近零。
       规模因子(SMB)是熊市中唯一亏损的非市场因子。
    2. 动量崩溃(momentum crash)研究：AQR等多项研究证实，
       动量策略最大回撤集中发生在熊市反弹期。
    3. CEPR 风险定价研究：熊市中风险溢价扩张，风险管理从附属品升级为核心能力。
    4. 格雷厄姆价值投资：熊市中安全边际是生存的关键。
    5. 达里奥原则：'最重要的是知道什么时候不该冒险'。

    === 核心逻辑：防御金字塔 ===

    底层（最高权重）：风险控制 + 财务安全 → 确保生存
    中层（中性权重）：宏观政策监测 → 捕捉转折  
    顶层（最低权重）：趋势和情绪信号 → 防误判
    """

    # ============================================================
    # 基本信息
    # ============================================================

    @property
    def name(self) -> str:
        return "bear_market"

    @property
    def display_name(self) -> str:
        return "熊市场景"

    @property
    def description(self) -> str:
        return "大盘处于下降趋势，风险溢价扩张，防御是第一原则。" \
               "本场景采用'防御金字塔'权重模型——风控和财务面为底座，" \
               "宏观监测为中层，趋势和情绪信号降权防误判。"

    # ============================================================
    # 基础权重表（占位初稿，后续迭代）
    # ============================================================
    # 格式: {专家类型: (权重值, 权重理由)}
    # ⚠️ 权重值均为占位，后续需多轮迭代调优

    _BASE_WEIGHTS: Dict[str, Tuple[float, str]] = {
        "risk": (
            1.6,
            "[研究依据] CEPR / Bridgewater / 巴菲特原则一致性："
            "熊市的本质是风险溢价扩张——在坏的体制状态中，资产价格下跌不是因为"
            "基本面恶化，而是因为风险溢价要求升高。风险控制在熊市中从'可选辅助'"
            "升级为'核心能力'。巴菲特的'别人贪婪我恐惧'在此环境中应翻译为："
            "'在熊市中，活下来是第一原则，收益是第二原则'。"
            "学术研究表明，所有因子中风险意识在熊市中提供的保护效果最为显著。"
        ),
        "financial": (
            1.2,
            "[研究依据] QuantPedia 因子研究：价值因子(HML)在熊市中的收益高度正显著，"
            "而在牛市中收益接近零——呈典型的反周期防御特征。"
            "格雷厄姆的安全边际理论在熊市中得到最充分的验证："
            "具有真实盈利能力、现金流充裕、低负债的企业，"
            "在下行市场中具备更强的抗跌性和更快的恢复能力。"
            "财务基本面的防御效果在熊市中达到最大值。"
        ),
        "macro": (
            1.1,
            "[研究依据] 熊市中宏观政策的作用被显著放大。"
            "降息、量化宽松、财政刺激等政策信号可能成为趋势反转的催化剂。"
            "2008年、2020年等历史熊市均表明：宏观政策的转向往往是熊市结束的最早信号。"
            "适度提高权重以捕捉政策拐点，但需注意政策传导存在时滞。"
        ),
        "fundflow": (
            0.9,
            "[研究依据] 熊市中资金流向需要精细区分："
            "'逃命式流出'（缩量阴跌）是趋势延续信号；"
            "'恐慌式放量'（放量暴跌）可能是阶段性底部信号；"
            "'抄底式流入'（低位放量反弹）是反转候选信号。"
            "资金流向在熊市中的信号价值存在不对称性——"
            "放量信号比缩量信号更有分析价值。"
        ),
        "industry": (
            1.10,
            "[研究依据] 产业/行业分析组（专家5组）跟踪产业链景气度和供应链变化。"
            "行业的'防御属性'在熊市中得到最充分的验证——"
            "必选消费、公用事业等刚性需求行业在熊市中抗跌性显著，"
            "而周期性和可选消费行业往往首当其冲。"
            "巴菲特/芒格的'护城河(moat)'理论：竞争优势强的行业龙头"
            "在下行周期中不仅活得更久，还能借机扩张市场份额。"
            "供应链分析在熊市中尤为关键——上游成本压力传导、"
            "下游需求萎缩速度、库存去化周期长短，直接决定企业生存能力。"
            "权重提高以强化行业维度的防御属性判断。"
        ),
        "news": (
            0.65,
            "[研究依据] 舆情组（专家6组）统一覆盖新闻监测与情绪分析。"
            "行为金融学研究表明熊市中存在'负面信息放大效应'——"
            "投资者对负面新闻的反应强度是正面新闻的2-3倍。"
            "同时AAII情绪长期追踪表明极端恐惧值可能持续数周才见底，"
            "情绪指标在熊市中是不稳定的反向指标。"
            "合并降权以避免'恐慌传染'和'过早乐观'的双重误导。"
        ),
        "technical": (
            0.5,
            "[研究依据] ⚠️ 动量崩溃(momentum crash)是熊市最重要的学术发现之一。"
            "AQR/Cliff Asness 等多项研究证实：当市场从恐慌底部快速反弹时，"
            "动量策略会系统性产生错误买入信号——这是动量策略最大和最集中的回撤来源。"
            "2008年10月-11月、2020年3月-4月均为典型案例。"
            "在熊市中，技术信号的价值不在于'跟趋势'，而在于'识别极端超卖后的反弹'，"
            "因此仅在特定条件下（RSI<30）才提高技术面权重。"
        ),
    }

    # ============================================================
    # 仓位配置 —— 熊市仓位逻辑
    # ============================================================
    #
    # 依据：熊市中仓位控制是第一位的风险管理工具。
    # 历史数据反复证明：熊市中最大的亏损来源不是选错方向，
    # 而是仓位过重导致的不可逆损失。
    #
    # 原则："熊市中要么轻仓，要么不做。"
    # → 公式保守：系数 0.25 × 置信度，上限硬封 0.15
    # → 即使7个专家一致看多，熊市中也不應超过15%仓位
    # ============================================================

    POSITION_COEFFICIENT = 0.25
    POSITION_CAP = 0.15

    # ============================================================
    # 风险阈值
    # ============================================================

    # 熊市中 RSI 超卖阈值
    RSI_OVERSOLD = 30  # RSI < 30 视为超卖，可能触发反弹

    # ============================================================
    # 权重计算
    # ============================================================

    def get_weight(
        self, expert_type: str, market_data: Optional[Dict] = None
    ) -> Tuple[float, str]:
        """
        获取专家权重，支持根据市场数据动态调整。

        条件逻辑（灵活化）：
          1. RSI < 30 超卖 → 技术面信号可能出现反弹→ 略微提高
             理由：极端超卖时技术信号可能捕捉到底部背离
          2. 成交量骤增（恐慌抛售）→ 资金流权重提高
             理由：放量下跌可能是恐慌见底的信号
          3. 其他专家保持基础权重
        """
        # 获取基础权重
        if expert_type in self._BASE_WEIGHTS:
            base_weight, base_reason = self._BASE_WEIGHTS[expert_type]
        else:
            return (1.0, f"未注册的专家类型 '{expert_type}'，使用默认权重 1.0")

        # 没有市场数据，直接返回基础权重
        if not market_data:
            return (base_weight, f"[{self.display_name}] {base_reason}")

        # ---- 条件 1：RSI 严重超卖 → 动量崩溃后的反弹窗口 ----
        rsi = market_data.get("rsi", None)
        if rsi is not None and rsi < self.RSI_OVERSOLD:
            if expert_type == "technical":
                adjusted_weight = 0.8  # 从 0.5 升至 0.8（超卖反弹窗口）
                return (
                    adjusted_weight,
                    f"[{self.display_name}] RSI={rsi} 严重超卖，"
                    f"历史数据表明极端超卖后技术性反弹概率显著升高，"
                    f"此时技术信号的方向判断价值恢复，"
                    f"权重从 {base_weight} 升至 {adjusted_weight}"
                )

        # ---- 条件 2：恐慌抛售（成交量骤增 + 价格下跌） ----
        volume_ratio = market_data.get("volume_ratio", None)
        price_change = market_data.get("price_change_pct", None)
        if (
            volume_ratio is not None and volume_ratio > 1.5 and
            price_change is not None and price_change < -3.0
        ):
            if expert_type == "fundflow":
                adjusted_weight = 1.2  # 从 0.9 升至 1.2
                return (
                    adjusted_weight,
                    f"[{self.display_name}] 放量下跌（跌幅{price_change:.1f}%，"
                    f"成交量{volume_ratio:.0%}），恐慌抛售往往是阶段性底部的特征，"
                    f"资金流信号在此环境下具有前瞻性价值，"
                    f"权重从 {base_weight} 升至 {adjusted_weight}"
                )

        # 无条件触发，返回基础权重
        return (base_weight, f"[{self.display_name}] {base_reason}")

    def get_all_weights(
        self, market_data: Optional[Dict] = None
    ) -> Dict[str, Tuple[float, str]]:
        """一次获取全部专家权重及理由。"""
        result = {}
        for expert_type in self._BASE_WEIGHTS:
            result[expert_type] = self.get_weight(expert_type, market_data)
        return result

    # ============================================================
    # 仓位计算
    # ============================================================

    def get_position_ratio(self, confidence: float, direction: str) -> Tuple[float, str]:
        """
        熊市仓位公式。

        公式: 置信度 × 0.3，上限 0.2
        说明:
          - 熊市系数 0.3 远低于默认的 0.5，体现保守仓位管理
          - 上限 0.2，严格控制风险敞口
          - 即使看多信号很强也不满仓
        """
        if direction == "neutral":
            return (0.0, "中性方向，不持仓")

        position = confidence * self.POSITION_COEFFICIENT
        original = position
        position = min(position, self.POSITION_CAP)

        if original > self.POSITION_CAP:
            return (
                position,
                f"熊市公式：置信度 {confidence:.2f} × {self.POSITION_COEFFICIENT} = {original:.2f}，"
                f"触及上限 {self.POSITION_CAP}，最终仓位 {position:.2f}"
            )
        else:
            return (
                position,
                f"熊市公式：置信度 {confidence:.2f} × {self.POSITION_COEFFICIENT} = {position:.2f}"
            )

    # ============================================================
    # 场景风险
    # ============================================================

    def get_scenario_risks(self, market_data: Optional[Dict] = None) -> List[str]:
        """
        熊市场景的特有风险提示。
        """
        risks = [
            "趋势下行风险：熊市中逆势操作风险极大，建议以防守为主",
            "虚假反弹风险：熊市中容易出现短暂的反弹陷阱，确认反转前勿追涨",
            "流动性风险：熊市中部分个股流动性下降，可能无法及时出货",
        ]

        # 条件风险
        if market_data:
            rsi = market_data.get("rsi", None)
            if rsi is not None and rsi < self.RSI_OVERSOLD:
                risks.append(
                    f"⚠️ 当前 RSI={rsi} 严重超卖，可能出现技术性反弹，但趋势未确认反转前谨慎抄底"
                )
            volume_ratio = market_data.get("volume_ratio", None)
            price_change = market_data.get("price_change_pct", None)
            if (
                volume_ratio is not None and volume_ratio > 1.5 and
                price_change is not None and price_change < -3.0
            ):
                risks.append(
                    f"⚠️ 恐慌性抛售（跌幅 {price_change:.1f}%，放量 {volume_ratio:.0%}），"
                    "可能接近阶段性底部，但需等待企稳信号"
                )

        return risks

    # ============================================================
    # 场景匹配（基于专家信号）
    # ============================================================

    def match_signals(self, signals: List["Signal"]) -> Tuple[float, str, Dict]:
        """
        评分制场景匹配 —— 熊市场景（v2 升级）。

        与牛市场景对称，三个条件每条件 0-1 分，简单平均聚合：

        条件 1（宏观面看空）: 基于宏观组置信度的方向评分
          宏观组 bearish + conf≥0.5 → score=conf；conf<0.5 → conf×0.6；非 bearish → 0

        条件 2（风控面告警）: 基于风控组置信度的方向评分
          风控组 bearish + conf≥0.5 → score=conf；conf<0.5 → conf×0.6；非 bearish → 0
          风控组缺失 → 0.3（部分分，覆盖不足但不否决）

        条件 3（整体信号偏空）: 基于多空数量比的方向评分
          看空数量 / (看多+看空)，仅当看空>看多有效

        聚合：score = (c1 + c2 + c3) / 3
        匹配阈值：score >= 0.5
        """
        if not signals:
            return (0.0, "无专家信号，无法判断熊市场景适用性", {
                "condition_scores": {},
                "condition_details": {"error": "no_signals"},
                "aggregate_method": "average",
                "aggregate_score": 0.0,
                "passed_threshold": False,
            })

        # ---- 条件 1：宏观组看空评分 ----
        macro = self._find_signal(signals, "macro")
        score_macro = self._confidence_score(macro, "bearish")

        if macro is None:
            detail_macro = "宏观组: 无信号 → 0"
        elif macro.direction == "bearish" and macro.confidence >= 0.5:
            detail_macro = f"宏观组: bearish(conf={macro.confidence:.0%}) → {score_macro:.2f}"
        elif macro.direction == "bearish":
            detail_macro = f"宏观组: bearish(conf={macro.confidence:.0%}) 低于阈值，降权 → {score_macro:.2f}"
        else:
            detail_macro = f"宏观组: {macro.direction}(conf={macro.confidence:.0%}) 方向错误 → 0"

        # ---- 条件 2：风控组风险告警评分 ----
        risk = self._find_signal(signals, "risk")
        score_risk = self._confidence_score(risk, "bearish")
        if risk is None:
            score_risk = 0.3
            detail_risk = "风控组: 无信号（覆盖不足）→ 0.30"
        elif risk.direction == "bearish" and risk.confidence >= 0.5:
            detail_risk = f"风控组: bearish(conf={risk.confidence:.0%}) → {score_risk:.2f}"
        elif risk.direction == "bearish":
            detail_risk = f"风控组: bearish(conf={risk.confidence:.0%}) 低于阈值，降权 → {score_risk:.2f}"
        else:
            detail_risk = f"风控组: {risk.direction}(conf={risk.confidence:.0%}) 非告警 → 0"

        # ---- 条件 3：整体信号偏空评分 ----
        score_bias = self._direction_ratio_score(signals, "bearish")
        bull_cnt = self._count_direction(signals, "bullish")
        bear_cnt = self._count_direction(signals, "bearish")
        neu_cnt = self._count_direction(signals, "neutral")
        detail_bias = (
            f"整体信号: 看空{bear_cnt} vs 看多{bull_cnt} vs 中性{neu_cnt}"
            f"{' → ' + f'{score_bias:.2f}' if score_bias > 0 else ' → 0（看多不弱于看空）'}"
        )

        # ---- 聚合 ----
        aggregate = round((score_macro + score_risk + score_bias) / 3, 4)
        passed = aggregate >= 0.5

        reason_parts = []
        if score_macro >= 0.5: reason_parts.append(f"宏观组强力看空({score_macro:.2f})")
        elif score_macro > 0: reason_parts.append(f"宏观组弱看空({score_macro:.2f})")
        if score_risk >= 0.5: reason_parts.append(f"风控组风险告警({score_risk:.2f})")
        elif score_risk > 0: reason_parts.append(f"风控组信号偏弱({score_risk:.2f})")
        if score_bias >= 0.7: reason_parts.append(f"整体信号显著偏空({score_bias:.2f})")
        elif score_bias > 0: reason_parts.append(f"整体信号略偏空({score_bias:.2f})")

        if passed:
            reason = "熊市场景匹配 ✓ — " + "；".join(reason_parts) + f"；综合: {aggregate:.2f}"
        else:
            reason = "熊市场景不匹配 ✗"
            if reason_parts:
                reason += " — " + "；".join(reason_parts)
            reason += f"；综合: {aggregate:.2f}"

        return (aggregate, reason, {
            "condition_scores": {"macro_bearish": score_macro, "risk_alert": score_risk, "signal_bias": score_bias},
            "condition_details": {"macro_bearish": detail_macro, "risk_alert": detail_risk, "signal_bias": detail_bias},
            "aggregate_method": "average",
            "aggregate_score": aggregate,
            "passed_threshold": passed,
        })
