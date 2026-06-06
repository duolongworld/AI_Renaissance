"""
牛市场景 —— 上升趋势中的专家权重配置。

方法论依据：
  桥水经济机器模型：增长上升 + 通胀温和 + 风险溢价压缩。
  对应桥水框架中的"扩张期"——趋势跟随策略占优。
  权重逻辑由因子研究交叉验证（QuantPedia、AQR、LuxAlgo、CEPR）。

核心理念：
  每个权重数值均附带可追溯的研究理由，用户可阅读理由后自行判断是否采纳。
"""

from typing import Dict, List, Tuple, Optional, TYPE_CHECKING

from agents.orchestrator.scenario_profile import ScenarioProfile

if TYPE_CHECKING:
    from agents.signal import Signal


class BullMarketScenario(ScenarioProfile):
    """
    牛市场景配置 —— 研究驱动的权重方法论。

    === 方法论来源 ===

    本场景权重逻辑基于以下研究框架：
    1. LuxAlgo 市场体制研究：趋势市场(ADX>40)中趋势跟踪策略表现最优，
       均值回归策略失效。移动平均线、MACD 等趋势指标在单边市场中信号可靠性最高。
    2. QuantPedia/学术因子研究：动量因子(UMD)在牛市中有稳定正收益；
       价值因子(HML)牛市中收益接近零，呈反周期特征。
    3. 桥水全天候框架：增长上升+通胀温和 = 股票最优，趋势+动量策略占优。
    4. AQR研究：动量策略收益呈正偏态分布，在趋势市中能有效捕捉持续方向性移动。
    5. Man Group体制模型：多变量相似度框架验证了趋势持续性在体制识别中的重要性。

    === 核心逻辑 ===

    牛市的本质是"趋势的自我强化"——价格持续突破阻力位，
    逢低买入是主导策略。因此：
      - 趋势跟踪/动量（技术面）→ 核心驱动力，权重最高
      - 增量资金流入（资金流）→ 趋势的燃料，权重提高
      - 风险信号误报率高（"牛市中每一次回调都是买入机会"）→ 权重降低
      - 财务基本面滞后于价格（季度数据 vs 实时价格）→ 权重降低
      - 情绪容易过度乐观（牛市尾部风险积累）→ 适度降低防狂热
    """

    # ============================================================
    # 基本信息
    # ============================================================

    @property
    def name(self) -> str:
        return "bull_market"

    @property
    def display_name(self) -> str:
        return "牛市场景"

    @property
    def description(self) -> str:
        return "大盘处于上升趋势，市场情绪乐观，资金持续流入。" \
               "本场景下技术面和资金流信号权重提高，风险信号权重降低。"

    # ============================================================
    # 基础权重表 —— 研究驱动的权重逻辑
    # ============================================================
    # 格式: {专家类型: (权重值, 权重理由)}
    #
    # 权重设计遵循"因子→场景"翻译框架：
    #   学术/机构研究中对不同市场体制下各因子有效性的结论
    #   → 翻译为7个专家组在这个场景下的权重
    # ============================================================

    _BASE_WEIGHTS: Dict[str, Tuple[float, str]] = {
        "technical": (
            1.3,
            "[研究依据] LuxAlgo / AQR / Man Group 等多项研究一致表明："
            "在趋势明确的市场中（ADX>40），趋势跟踪策略是表现最优的策略类别。"
            "动量因子在牛市中有稳定的正收益。"
            "技术面分析方法（均线、MACD、一目均衡等）在此环境中的信号可靠性达到峰值。"
            "核心策略是'顺势而为'——追随趋势而非预测转折。"
        ),
        "fundflow": (
            1.2,
            "[研究依据] 牛市本质上是增量资金驱动的趋势行情。"
            "资金流向是判断行情持续性的先行指标——资金的持续流入为上涨提供燃料，"
            "资金流出（尤其是机构级别的流出）往往是趋势衰竭的早期预警。"
            "在趋势市场中，成交量确认的突破信号是可靠性最高的买入信号之一。"
        ),
        "macro": (
            1.0,
            "[研究依据] 在已确立的牛市趋势中，宏观环境的变化已充分计入价格。"
            "宏观经济数据的边际变化（如PMI回升0.5%）对趋势中的市场影响有限。"
            "宏观组在此阶段的边际贡献不在于'判断方向'（方向已由趋势决定），"
            "而在于'监测政策拐点'——当宏观政策开始收紧时，这是重要的风险信号。"
            "因此保持中性权重，监控转折而非主导判断。"
        ),
        "industry": (
            1.05,
            "[研究依据] 产业/行业分析组（专家5组）负责跟踪产业链景气度和供应链变化。"
            "A股市场'行业轮动'是每轮牛市的核心特征——"
            "不同的行业和板块在牛市的启动期、主升期、末端期交替领涨。"
            "林奇(Peter Lynch)方法论：理解公司所处的行业是选股的第一前提，"
            "'投资你了解的行业'是其最著名的原则。"
            "选对行业对收益的贡献远超选对个股——"
            "赛道选择是牛市中最重要的决策之一。"
            "权重适度提高，但牛市中水涨船高效应会降低行业精选的边际收益。"
        ),
        "financial": (
            0.7,
            "[研究依据] QuantPedia 因子研究表明：价值因子(HML)在牛市中的平均收益接近零。"
            "这不是说财务面不重要，而是说在趋势驱动的牛市中，"
            "财务基本面（PE、ROE、盈利增速等）的边际预测能力显著下降。"
            "原因：① 季报频率严重滞后于日线级别的价格变化；"
            "② 牛市情绪会使得市场对好消息过度反应、对坏消息忽视。"
            "但注意：财务面在牛市末端（估值极端时）的作用会急剧上升。"
        ),
        "news": (
            0.7,
            "[研究依据] 舆情组（专家6组）统一覆盖新闻监测与情绪分析。"
            "牛津大学新闻情绪研究 + SentimenTrader/IBD 情绪追踪共同表明："
            "牛市中舆情信号存在双向噪音——利好消息过度放大形成确认偏误，"
            "情绪指标出现'过早警告'（RSI在牛市中途就进入超买但趋势持续数月）。"
            "降低权重以减少被'报喜不报忧'和'过早过热警告'双向误导。"
            "但保留对极端值（恐慌/贪婪指数>90）的无条件关注。"
        ),
        "risk": (
            0.5,
            "[研究依据] CEPR 风险定价研究：在牛市（好的经济体状态）中，"
            "高风险资产被期望提供高回报，风险溢价处于压缩状态。"
            "这导致风险模型的假警报率升高——每一次正常的技术性回调"
            "都可能触发风险预警，但并非真正的系统性风险事件。"
            "大幅降低权重以过滤假警报，但对尾部风险信号保持无条件关注。"
        ),
    }

    # ============================================================
    # 仓位配置 —— 牛市仓位逻辑
    # ============================================================
    #
    # 依据：牛市是'顺势而为'的环境，趋势的持续性意味着
    # 适度提高仓位以捕捉趋势收益是合理的。但上限必须保留，
    # 因为牛市尾部往往是最危险的——人人都在买的时候，风险在积累。
    #
    # 巴菲特的仓位哲学：'别人贪婪时我恐惧'
    # → 牛市可以提高仓位，但永远保留安全边际。
    # ============================================================

    # 牛市仓位系数：积极但不激进
    POSITION_COEFFICIENT = 0.60
    POSITION_CAP = 0.40  # 最大仓位 40%——牛市可以比默认(30%)更积极，但绝不滿仓

    # ============================================================
    # 权重计算（融合逻辑核心）
    # ============================================================

    def get_weight(
        self, expert_type: str, market_data: Optional[Dict] = None
    ) -> Tuple[float, str]:
        """
        获取专家权重，支持根据市场数据动态调整。

        条件逻辑（灵活化的体现）：
          1. RSI > 80 过热 → 技术面权重从 1.2 降至 0.8
             理由：超买状态下趋势信号可靠性下降
          2. 成交量萎缩 20% 以上 → 资金流权重从 1.1 降至 0.9
             理由：缩量上涨不可持续，资金推动力减弱
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

        # ---- 条件 1：RSI 严重过热 → 动量策略面临回调风险 ----
        rsi = market_data.get("rsi", None)
        if rsi is not None and rsi > 80:
            if expert_type == "technical":
                adjusted_weight = 0.8  # 从 1.3 大幅降至 0.8
                return (
                    adjusted_weight,
                    f"[{self.display_name}] RSI={rsi} 严重超买，"
                    f"趋势跟踪策略在此阶段面临显著的均值回归风险。"
                    f"学术研究表明动量因子在过度延伸后容易出现回撤，"
                    f"权重从 {base_weight} 降至 {adjusted_weight}"
                )
            if expert_type == "news":
                adjusted_weight = 0.4  # 舆情组包含情绪分析，极端过热时大幅降权
                return (
                    adjusted_weight,
                    f"[{self.display_name}] RSI={rsi} 情绪极度亢奋，"
                    f"SentimenTrader研究表明极端情绪值是反向指标，"
                    f"权重从 {base_weight} 降至 {adjusted_weight}"
                )

        # ---- 条件 2：成交量萎缩 → 资金推动力减弱 ----
        volume_ratio = market_data.get("volume_ratio", None)
        if volume_ratio is not None and volume_ratio < 0.8:
            if expert_type == "fundflow":
                adjusted_weight = 0.9  # 从 1.2 降至 0.9
                return (
                    adjusted_weight,
                    f"[{self.display_name}] 成交量萎缩至正常的 {volume_ratio:.0%}，"
                    f"缩量上涨是趋势衰竭的经典预警信号，"
                    f"表示增量资金推动力减弱，权重从 {base_weight} 降至 {adjusted_weight}"
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
        牛市仓位公式。

        公式: 置信度 × 0.6，上限 0.4
        说明:
          - 牛市系数 0.6 高于默认的 0.5，体现积极仓位管理
          - 上限 0.4 而非默认的 0.3，留出更多操作空间
          - 但仍保留安全边际，不满仓
        """
        if direction == "neutral":
            return (0.0, "中性方向，不持仓")

        position = confidence * self.POSITION_COEFFICIENT
        original = position
        position = min(position, self.POSITION_CAP)

        if original > self.POSITION_CAP:
            return (
                position,
                f"牛市公式：置信度 {confidence:.2f} × {self.POSITION_COEFFICIENT} = {original:.2f}，"
                f"触及上限 {self.POSITION_CAP}，最终仓位 {position:.2f}"
            )
        else:
            return (
                position,
                f"牛市公式：置信度 {confidence:.2f} × {self.POSITION_COEFFICIENT} = {position:.2f}"
            )

    # ============================================================
    # 场景风险
    # ============================================================

    def get_scenario_risks(self, market_data: Optional[Dict] = None) -> List[str]:
        """
        牛市场景的特有风险提示。
        """
        risks = [
            "牛市追高风险：上升趋势中容易在高位追入，需确认回调支撑后再进场",
            "假突破风险：牛市中技术指标容易出现假突破信号，建议结合成交量验证",
            "过度乐观风险：市场情绪高涨时容易忽视基本面恶化信号",
        ]

        # 条件风险
        if market_data:
            rsi = market_data.get("rsi", None)
            if rsi is not None and rsi > 80:
                risks.append(
                    f"⚠️ 当前 RSI={rsi} 严重超买，短期回调风险显著增大"
                )
            volume_ratio = market_data.get("volume_ratio", None)
            if volume_ratio is not None and volume_ratio < 0.8:
                risks.append(
                    f"⚠️ 成交量萎缩至正常的 {volume_ratio:.0%}，上涨动能可能衰竭"
                )

        return risks

    # ============================================================
    # 场景匹配（基于专家信号）
    # ============================================================

    def match_signals(self, signals: List["Signal"]) -> Tuple[float, str, Dict]:
        """
        评分制场景匹配 —— 牛市场景（v2 升级）。

        三个条件，每条件 0-1 分，简单平均聚合：

        条件 1（宏观面看多）: 基于宏观组置信度的方向评分
          宏观组 bullish + conf≥0.5 → score=conf；conf<0.5 → conf×0.6；非 bullish → 0

        条件 2（风控面可控）: 基于风控组置信度的方向评分
          风控组 bullish + conf≥0.5 → score=conf；conf<0.5 → conf×0.6；非 bullish → 0
          风控组缺失 → 0.3（部分分，覆盖不足但不否决）

        条件 3（整体信号偏多）: 基于多空数量比的方向评分
          看多数量 / (看多+看空)，仅当看多>看空有效

        聚合：score = (c1 + c2 + c3) / 3
        匹配阈值：score >= 0.5
        """
        if not signals:
            return (0.0, "无专家信号，无法判断牛市场景适用性", {
                "condition_scores": {},
                "condition_details": {"error": "no_signals"},
                "aggregate_method": "average",
                "aggregate_score": 0.0,
                "passed_threshold": False,
            })

        # ---- 条件 1：宏观组看多评分 ----
        macro = self._find_signal(signals, "macro")
        score_macro = self._confidence_score(macro, "bullish")

        if macro is None:
            detail_macro = "宏观组: 无信号 → 0"
        elif macro.direction == "bullish" and macro.confidence >= 0.5:
            detail_macro = f"宏观组: bullish(conf={macro.confidence:.0%}) → {score_macro:.2f}"
        elif macro.direction == "bullish":
            detail_macro = f"宏观组: bullish(conf={macro.confidence:.0%}) 低于阈值，降权 → {score_macro:.2f}"
        else:
            detail_macro = f"宏观组: {macro.direction}(conf={macro.confidence:.0%}) 方向错误 → 0"

        # ---- 条件 2：风控组风险可控评分 ----
        risk = self._find_signal(signals, "risk")
        score_risk = self._confidence_score(risk, "bullish")
        if risk is None:
            score_risk = 0.3
            detail_risk = "风控组: 无信号（覆盖不足）→ 0.30"
        elif risk.direction == "bullish" and risk.confidence >= 0.5:
            detail_risk = f"风控组: bullish(conf={risk.confidence:.0%}) → {score_risk:.2f}"
        elif risk.direction == "bullish":
            detail_risk = f"风控组: bullish(conf={risk.confidence:.0%}) 低于阈值，降权 → {score_risk:.2f}"
        else:
            detail_risk = f"风控组: {risk.direction}(conf={risk.confidence:.0%}) 非可控 → 0"

        # ---- 条件 3：整体信号偏多评分 ----
        score_bias = self._direction_ratio_score(signals, "bullish")
        bull_cnt = self._count_direction(signals, "bullish")
        bear_cnt = self._count_direction(signals, "bearish")
        neu_cnt = self._count_direction(signals, "neutral")
        detail_bias = (
            f"整体信号: 看多{bull_cnt} vs 看空{bear_cnt} vs 中性{neu_cnt}"
            f"{' → ' + f'{score_bias:.2f}' if score_bias > 0 else ' → 0（看空不弱于看多）'}"
        )

        # ---- 聚合 ----
        aggregate = round((score_macro + score_risk + score_bias) / 3, 4)
        passed = aggregate >= 0.5

        reason_parts = []
        if score_macro >= 0.5: reason_parts.append(f"宏观组强力看多({score_macro:.2f})")
        elif score_macro > 0: reason_parts.append(f"宏观组弱看多({score_macro:.2f})")
        if score_risk >= 0.5: reason_parts.append(f"风控组风险可控({score_risk:.2f})")
        elif score_risk > 0: reason_parts.append(f"风控组信号偏弱({score_risk:.2f})")
        if score_bias >= 0.7: reason_parts.append(f"整体信号显著偏多({score_bias:.2f})")
        elif score_bias > 0: reason_parts.append(f"整体信号略偏多({score_bias:.2f})")

        if passed:
            reason = "牛市场景匹配 ✓ — " + "；".join(reason_parts) + f"；综合: {aggregate:.2f}"
        else:
            reason = "牛市场景不匹配 ✗"
            if reason_parts:
                reason += " — " + "；".join(reason_parts)
            reason += f"；综合: {aggregate:.2f}"

        return (aggregate, reason, {
            "condition_scores": {"macro_bullish": score_macro, "risk_controlled": score_risk, "signal_bias": score_bias},
            "condition_details": {"macro_bullish": detail_macro, "risk_controlled": detail_risk, "signal_bias": detail_bias},
            "aggregate_method": "average",
            "aggregate_score": aggregate,
            "passed_threshold": passed,
        })
