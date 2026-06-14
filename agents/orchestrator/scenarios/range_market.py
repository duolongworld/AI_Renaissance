"""
震荡市场景 —— 横盘整理中的专家权重配置。

方法论依据：
  桥水经济机器模型：增长方向与通胀方向均未形成明确趋势，
  风险溢价处于中性水平。对应桥水框架中的"均衡期"——
  多空力量暂时均衡，等待催化剂。
  权重逻辑由因子研究交叉验证（LuxAlgo、Man Group、Fama-French）。

核心理念：
  每个权重数值均附带可追溯的研究理由，用户可阅读理由后自行判断是否采纳。
"""

from typing import Dict, List, Tuple, Optional, TYPE_CHECKING

from agents.orchestrator.scenario_profile import ScenarioProfile

if TYPE_CHECKING:
    from agents.signal import Signal


class RangeMarketScenario(ScenarioProfile):
    """
    震荡市场景配置 —— 研究驱动的权重方法论。

    === 方法论来源 ===

    1. LuxAlgo 市场体制研究：ADX<20 定义震荡市（无趋势环境）。
       趋势跟踪策略在区间市场中失效——频繁的金叉死叉交替导致反复亏损。
       均值回归策略在此环境中表现最优。
    2. TradingLiteracy/Investopedia 震荡市研究：成交量指标在区间市场中
       是判断突破真伪的核心工具。假突破是震荡市最大的风险来源。
    3. Man Group 体制模型：多变量相似度框架。震荡市的结束通常由
       宏观事件或政策冲击触发，单一技术指标难以预判。
    4. 因子研究：震荡市中所有因子的方向性预测能力均显著下降，
       相对而言资金流和风险监测提供的边际价值最高。

    === 核心逻辑：突破前的守望 ===

    震荡市的本质是"多空力量的暂时均衡"。在此环境中：
      - 没有任何一方具有压倒性优势
      - 最好的策略通常是"等待"而非"预测"
      - 核心任务不是判断方向，而是准备在方向确认时快速反应
      - 资金流向是最可靠的"先遣信号"
    """

    # ============================================================
    # 基本信息
    # ============================================================

    @property
    def name(self) -> str:
        return "range_market"

    @property
    def display_name(self) -> str:
        return "震荡市场景"

    @property
    def description(self) -> str:
        return "大盘横盘整理，多空力量均衡，方向不明。" \
               "核心策略：等待突破确认，而非预判方向。" \
               "资金流向是方向选择的先行指标，技术信号可靠性最低。"

    # ============================================================
    # 基础权重表 —— 研究驱动的权重逻辑
    # ============================================================
    # 格式: {专家类型: (权重值, 权重理由)}
    #
    # 权重设计遵循"突破守望"原则：
    #   高度关注：方向选择的先行指标（资金流、风险）
    #   中性关注：等待催化剂（宏观）
    #   降低关注：方向性预测能力弱的指标（技术面、新闻）

    _BASE_WEIGHTS: Dict[str, Tuple[float, str]] = {
        "risk": (
            1.2,
            "[研究依据] 震荡市中最大的风险不是亏损，而是'在错误的方向上下了注'。"
            "风险信号在此环境中的核心价值不在于预警下跌，"
            "而在于帮助判断突破的性质——是有效突破还是假突破陷阱。"
            "LuxAlgo研究指出：假突破是震荡市最大的交易陷阱。"
        ),
        "fundflow": (
            1.2,
            "[研究依据] TradingLiteracy / Investopedia 震荡市研究一致指出："
            "成交量/资金流向是震荡市中最有效的先行指标。"
            "原理：在价格尚未突破区间之前，'聪明的资金'往往已经做出了方向选择。"
            "放量突破确认是震荡市中最可靠的交易信号，"
            "缩量突破大概率是假信号。"
        ),
        "macro": (
            1.0,
            "[研究依据] Man Group 体制转换研究：震荡市的结束往往需要一个'催化剂'——"
            "通常是宏观事件、政策变化或外部冲击。"
            "宏观组在此环境的角色不是'判断方向'而是'监测催化剂'，"
            "当宏观信号出现重大变化时，可能意味震荡市即将结束。"
        ),
        "financial": (
            0.9,
            "[研究依据] 震荡市中，财务面信号提供的是'结构性机会'而非'方向性判断'。"
            "在大盘无方向的时期，业绩分化的个股可能提供独立行情，"
            "但整体指数层面的预测贡献有限。"
        ),
        "industry": (
            1.20,
            "[研究依据] ⭐ 产业/行业分析组（专家5组）——震荡市中的'重中之重'。"
            "当大盘整体没有方向时，行业选择就是唯一且最重要的alpha来源。"
            "A股实证研究反复验证：每一轮震荡市中，行业间分化远大于行业内部，"
            "资金在不同行业间寻找结构性机会，行业轮动是回报差异的决定性因素。"
            "学术研究(Fama-French五因子+行业效应)表明：行业因素在方向不明的市场中"
            "对收益的解释力达到峰值。"
            "林奇的'投资你了解的行业'在此环境中价值最大化——"
            "深刻理解产业链的人能识别出被整体低估的优质赛道。"
            "权重大幅提高，与资金流和风险面并列震荡市最重要维度。"
        ),
        "news": (
            0.75,
            "[研究依据] 舆情组（专家6组）统一覆盖新闻监测与情绪分析。"
            "牛津大学新闻情绪研究指出：方向不明时同一则新闻可被双向解读。"
            "震荡市中情绪指标集中在'中性'区间，常态参考价值有限，"
            "但极端值（极度恐慌或贪婪）往往预示方向即将出现。"
            "合并后的权重平衡常态噪音过滤和对极端值的敏感性。"
        ),
        "technical": (
            0.5,
            "[研究依据] ⚠️ 震荡市是技术分析最容易失效的环境——"
            "LuxAlgo / TradingLiteracy 等多项研究一致指出："
            "在ADX<20的无趋势环境中，均线交叉、MACD金叉死叉等信号"
            "产生大量的'whipsaw'（反复穿越、频繁假信号）。"
            "此时技术信号的信噪比降到最低水平，是所有专家中可靠性最差的。"
            "仅在放量突破确认后才恢复技术面权重的正常水平。"
        ),
    }

    # ============================================================
    # 仓位配置 —— 震荡市仓位逻辑
    # ============================================================
    #
    # 依据：震荡市中最大的错误不是方向判断错误，
    # 而是在没有方向的市场中持有过重的仓位——这会导致
    # "死亡千刀"(death by a thousand cuts)式的持续小亏损。
    #
    # 原则："方向不明时不重仓，突破确认后再加仓。"
    # → 系数保守：0.35 × 置信度，上限硬封 0.20

    POSITION_COEFFICIENT = 0.35
    POSITION_CAP = 0.20

    # ============================================================
    # 突破阈值
    # ============================================================

    BREAKOUT_VOLUME_RATIO = 1.3  # 成交量超过均量 30% 视为放量
    BREAKOUT_PRICE_CHANGE = 2.0  # 涨跌幅超过 2% 视为突破

    # ============================================================
    # 权重计算
    # ============================================================

    def get_weight(
        self, expert_type: str, market_data: Optional[Dict] = None
    ) -> Tuple[float, str]:
        """
        获取专家权重，支持根据市场数据动态调整。

        条件逻辑（灵活化）：
          1. 出现放量突破 → 技术面权重从 0.7 升至 1.0
             理由：放量突破确认后趋势信号可靠性恢复
          2. 成交量极度萎缩 → 资金流权重降低
             理由：交投清淡时资金流信号意义不大
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

        volume_ratio = market_data.get("volume_ratio", None)
        price_change = market_data.get("price_change_pct", None)

        # ---- 条件 1：放量突破 ----
        is_breakout = (
            volume_ratio is not None and
            volume_ratio > self.BREAKOUT_VOLUME_RATIO and
            price_change is not None and
            abs(price_change) > self.BREAKOUT_PRICE_CHANGE
        )

        if is_breakout:
            if expert_type == "technical":
                adjusted_weight = 1.0  # 从 0.5 升至 1.0（突破确认后恢复可靠性）
                direction_text = "上涨" if price_change > 0 else "下跌"
                return (
                    adjusted_weight,
                    f"[{self.display_name}] 放量{direction_text}{abs(price_change):.1f}%"
                    f"（成交量{volume_ratio:.0%}），突破确认后技术信号可靠性恢复，"
                    f"权重从 {base_weight} 升至 {adjusted_weight}"
                )
            if expert_type == "fundflow":
                adjusted_weight = 1.3  # 从 1.2 升至 1.3
                return (
                    adjusted_weight,
                    f"[{self.display_name}] 放量突破确认，资金流方向选择信号全面激活，"
                    f"权重从 {base_weight} 升至 {adjusted_weight}"
                )

        # ---- 条件 2：成交量极度萎缩 ----
        if volume_ratio is not None and volume_ratio < 0.5:
            if expert_type == "fundflow":
                adjusted_weight = 0.8
                return (
                    adjusted_weight,
                    f"[{self.display_name}] 成交量萎缩至正常的 {volume_ratio:.0%}，"
                    f"交投清淡，资金流信号意义下降，权重从 {base_weight} 降至 {adjusted_weight}"
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
        震荡市仓位公式。

        公式: 置信度 × 0.4，上限 0.25
        说明:
          - 震荡市系数 0.4，比默认的 0.5 保守
          - 上限 0.25，留足空间应对方向选择
          - 方向不明时不建议重仓
        """
        if direction == "neutral":
            return (0.0, "中性方向，不持仓")

        position = confidence * self.POSITION_COEFFICIENT
        original = position
        position = min(position, self.POSITION_CAP)

        if original > self.POSITION_CAP:
            return (
                position,
                f"震荡市公式：置信度 {confidence:.2f} × {self.POSITION_COEFFICIENT} = {original:.2f}，"
                f"触及上限 {self.POSITION_CAP}，最终仓位 {position:.2f}"
            )
        else:
            return (
                position,
                f"震荡市公式：置信度 {confidence:.2f} × {self.POSITION_COEFFICIENT} = {position:.2f}"
            )

    # ============================================================
    # 场景风险
    # ============================================================

    def get_scenario_risks(self, market_data: Optional[Dict] = None) -> List[str]:
        """
        震荡市场景的特有风险提示。
        """
        risks = [
            "方向不明风险：震荡市中方向选择前不建议重仓操作",
            "假突破风险：震荡市中容易出现假突破信号，建议等待放量确认",
            "时间成本风险：震荡可能持续较长时间，持仓可能面临时间损耗",
        ]

        # 条件风险
        if market_data:
            volume_ratio = market_data.get("volume_ratio", None)
            if volume_ratio is not None and volume_ratio < 0.5:
                risks.append(
                    f"⚠️ 成交量极度萎缩（正常的 {volume_ratio:.0%}），"
                    "市场观望情绪浓厚，短期可能无明显方向"
                )

            price_change = market_data.get("price_change_pct", None)
            if (
                volume_ratio is not None and volume_ratio > self.BREAKOUT_VOLUME_RATIO and
                price_change is not None and abs(price_change) > self.BREAKOUT_PRICE_CHANGE
            ):
                direction_text = "向上" if price_change > 0 else "向下"
                risks.append(
                    f"⚠️ 放量{direction_text}突破（{price_change:+.1f}%，量比{volume_ratio:.0%}），"
                    "关注是否为有效突破，假突破风险仍存"
                )

        return risks

    def get_confidence_threshold(self) -> Optional[float]:
        """
        震荡市场景降低置信度阈值。

        依据：震荡市中各方向信号天然偏中性低置信度。
        使用默认 0.6 阈值会过度过滤信号，导致覆盖不足。
        降至 0.45 保留更多信号参与仲裁，但通过降低权重
        （技术面 0.5、新闻面 0.7）来控制噪音。

        注意：这不会降低最终置信度要求（那里仍由
        _make_decision 中的 0.5 阈值控制）。
        """
        return 0.45

    # ============================================================
    # 场景匹配（基于专家信号）
    # ============================================================

    def match_signals(self, signals: List["Signal"]) -> Tuple[float, str, Dict]:
        """
        评分制场景匹配 —— 震荡市场景（v2 升级）。

        三个条件，每条件 0-1 分，取最好的两个条件平均（top-2）：

        条件 1（宏观面中性）:
          宏观 neutral → 1.0；无宏观信号 → 0.6；非 neutral + conf<0.5 → 0.3；非 neutral + conf≥0.5 → 0

        条件 2（多空均衡）:
          完全均衡(diff=0, ≥2个方向信号) → 1.0；略有偏向(diff=1) → 0.7
          中性信号主导 → 0.8；否则 → 0

        条件 3（宏观vs风控冲突）:
          方向相反 → 1.0；一方缺失 → 0.4；方向一致 → 0

        聚合：取 top-2 条件平均
        匹配阈值：≥ 2 个条件分数 > 0.5
        """
        if not signals:
            return (0.0, "无专家信号，无法判断震荡市场景适用性", {
                "condition_scores": {},
                "condition_details": {"error": "no_signals"},
                "aggregate_method": "top_n",
                "aggregate_score": 0.0,
                "passed_threshold": False,
            })

        # ---- 条件 1：宏观组中性评分 ----
        macro = self._find_signal(signals, "macro")
        if macro is None:
            score_neutral = 0.6
            detail_neutral = "宏观组: 无信号（视为方向不明）→ 0.60"
        elif macro.direction == "neutral":
            score_neutral = 1.0
            detail_neutral = f"宏观组: neutral(conf={macro.confidence:.0%}) → 1.00"
        elif macro.confidence < 0.5:
            score_neutral = 0.3
            detail_neutral = f"宏观组: {macro.direction}(conf={macro.confidence:.0%}) 弱方向 → 0.30"
        else:
            score_neutral = 0.0
            detail_neutral = f"宏观组: {macro.direction}(conf={macro.confidence:.0%}) 明确方向 → 0"

        # ---- 条件 2：多空均衡评分 ----
        bull_cnt = self._count_direction(signals, "bullish")
        bear_cnt = self._count_direction(signals, "bearish")
        neu_cnt = self._count_direction(signals, "neutral")
        diff = abs(bull_cnt - bear_cnt)
        total_dir = bull_cnt + bear_cnt

        # 均衡条件判断
        is_balanced = (diff <= 1 and total_dir >= 2)
        is_neutral_dominant = (neu_cnt >= max(bull_cnt, bear_cnt, 1) and neu_cnt >= 3)

        if is_balanced:
            score_balance = round(max(0.0, 1.0 - diff / total_dir), 2) if total_dir > 0 else 0.0
            detail_balance = (
                f"多空均衡: 看多{bull_cnt} vs 看空{bear_cnt} vs 中性{neu_cnt}"
                f"（差值{diff}，方向信号{total_dir}个）→ {score_balance:.2f}"
            )
        elif is_neutral_dominant:
            score_balance = 0.8
            detail_balance = (
                f"中性主导: 看多{bull_cnt} vs 看空{bear_cnt} vs 中性{neu_cnt} → 0.80"
            )
        else:
            score_balance = 0.0
            detail_balance = (
                f"多空不均衡: 看多{bull_cnt} vs 看空{bear_cnt} vs 中性{neu_cnt}"
                f"（差值{diff} > 1 且无中性主导）→ 0"
            )

        # ---- 条件 3：宏观与风控冲突评分 ----
        risk = self._find_signal(signals, "risk")
        macro_dir = macro.direction if macro else None
        risk_dir = risk.direction if risk else None

        if macro_dir and risk_dir:
            if (
                (macro_dir == "bullish" and risk_dir == "bearish") or
                (macro_dir == "bearish" and risk_dir == "bullish")
            ):
                score_conflict = 1.0
                detail_conflict = f"信号冲突: 宏观{macro_dir} vs 风控{risk_dir}（典型震荡特征）→ 1.00"
            else:
                score_conflict = 0.0
                detail_conflict = f"信号一致: 宏观{macro_dir} 风控{risk_dir}，无冲突 → 0"
        elif macro_dir or risk_dir:
            score_conflict = 0.4
            missing = "风控" if risk_dir is None else "宏观"
            detail_conflict = f"信号冲突检查: {missing}缺失，无法判断 → 0.40"
        else:
            score_conflict = 0.0
            detail_conflict = "信号冲突检查: 宏观和风控均缺失 → 0"

        # ---- 聚合：取 top-2 条件平均 ----
        scores = [score_neutral, score_balance, score_conflict]
        sorted_scores = sorted(scores, reverse=True)
        top_two = sorted_scores[:2]
        aggregate = round(sum(top_two) / 2, 4)

        # 判断是否匹配：≥ 2 个条件分数 > 0.5
        passed_count = sum(1 for s in scores if s > 0.5)
        passed = passed_count >= 2

        reason_parts = []
        if score_neutral > 0.5: reason_parts.append(f"宏观方向不明({score_neutral:.2f})")
        if score_balance > 0.5: reason_parts.append(f"多空力量均衡({score_balance:.2f})")
        if score_conflict > 0.5: reason_parts.append(f"宏风控冲突({score_conflict:.2f})")

        if passed:
            reason = "震荡市场景匹配 ✓ — " + "；".join(reason_parts) + f"；top-2平均: {aggregate:.2f}"
        else:
            reason = "震荡市场景不匹配 ✗"
            if reason_parts:
                reason += " — " + "；".join(reason_parts)
            reason += f"（仅{passed_count}/3条件满足 > 0.5）"

        return (aggregate, reason, {
            "condition_scores": {"macro_neutral": score_neutral, "balanced": score_balance, "conflict": score_conflict},
            "condition_details": {"macro_neutral": detail_neutral, "balanced": detail_balance, "conflict": detail_conflict},
            "aggregate_method": "top_n",
            "aggregate_score": aggregate,
            "passed_threshold": passed,
        })
