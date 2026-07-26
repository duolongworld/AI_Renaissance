"""
风险预警 Agent - 专家7组

signal_type: risk
Skill 域: skills/risk/
核心能力：尾部风险识别、仓位上限、守住不爆仓的底线

注意：风险预警 Agent 也输出 Signal，参与仲裁博弈。

实现说明（骨架版 v1）：
  本 Agent 加载并执行 skills/risk/ 下三份 Skill 的规则，输出真实 Signal：
    - liquidity_risk_factor_monitoring  → 流动性风险（含「流动性一票否决权」）
    - valuation_bubble_monitor          → 估值泡沫
    - risk_control_framework            → 六维风控框架
  采用「手写 Python 规则 + 现有数据源」的方式（与舆情 Agent 一致，全项目暂无 LLM 层）。
  第一步只落地有真值数据的规则；缺失数据（个股 OHLCV/换手率/PE 分位/股息率/巴菲特/VIX 等）
  的规则按 Skill 的降级条款跳过，并如实写入 meta.uncertainties，不伪造结论。
"""

from typing import Optional, Dict, Any, List

from agents.base import BaseAgent
from agents.signal import Signal, bearish_signal
from data_sources import (
    AkshareDataSource,
    MarketSentimentDataSource,
    IndustrySentimentDataSource,
)


# 风险等级序（用于取 max）
_RISK_ORDER = {"low": 0, "medium": 1, "high": 2}


def _max_risk(*levels: str) -> str:
    """返回风险等级的较高者"""
    best = "low"
    for lv in levels:
        if _RISK_ORDER.get(lv, 0) > _RISK_ORDER.get(best, 0):
            best = lv
    return best


class RiskAgent(BaseAgent):
    """风险预警 Agent（专家7组）"""

    signal_type = "risk"

    def __init__(self, config: Optional[dict] = None):
        super().__init__(name="风险预警Agent", config=config or {})
        # 加载 skills/risk/ 下三份 Skill（流动性 / 估值泡沫 / 风控框架）
        self.load_skills_from_domain("risk")

        # 注入数据源（config 优先，便于测试用假数据源；否则兜底实例化）
        self.akshare_source = (
            self.config.get("akshare_source") or AkshareDataSource()
        )
        self.market_sentiment_source = (
            self.config.get("market_sentiment_source") or MarketSentimentDataSource()
        )
        self.industry_sentiment_source = (
            self.config.get("industry_sentiment_source") or IndustrySentimentDataSource()
        )

    # ══════════════════════════════════════════════════════════
    # 主编排
    # ══════════════════════════════════════════════════════════

    def analyze(self, stock_code: str) -> Signal:
        """
        编排三份 Skill 对应的三组子分析，聚合后输出标准 Signal。
        """
        code = stock_code.strip()
        self.log(f"开始风险预警分析：{code}")
        self.log(f"已加载 Skill: {self.list_skills()}")

        liq = self._analyze_liquidity(code)
        val = self._analyze_valuation(code)
        framework = self._analyze_risk_framework(code)

        return self._build_combined_signal(code, liq, val, framework)

    # ── 统一降级模板 ──────────────────────────────────────────

    @staticmethod
    def _error_result(dimension: str, reason: str) -> Dict[str, Any]:
        """子分析失败/数据缺失时的统一降级返回（与舆情 Agent 一致）"""
        return {
            "status": "error",
            "dimension": dimension,
            "direction": "neutral",
            "confidence": 0.3,
            "reasoning": reason,
            "score": 50.0,
            "risk_level": "low",
            "signals": [],
            "indicators": {},
            "uncertainties": [reason],
        }

    # ══════════════════════════════════════════════════════════
    # 子分析一：流动性风险（liquidity_risk_factor_monitoring，基础模式）
    # ══════════════════════════════════════════════════════════

    def _analyze_liquidity(self, stock_code: str) -> Dict[str, Any]:
        """
        基础模式落地：
          - 规则13 市场踩踏代理（全市场跌停家数 + 北向资金流出）
          - 资金流向（个股主力净流入，规则11 的代理）
        跳过（无个股 OHLCV/换手率/成交额）：规则1-5、12（记 uncertainties）。
        产出 liquidity_outlook + risk_level，并据此判断是否触发「流动性一票否决权」。
        """
        try:
            uncertainties: List[str] = [
                "流动性规则1-5、12 依赖个股 OHLCV/换手率/成交额，当前数据源未提供，已跳过",
                "增强模式规则4/9/10/11（Level-2/持仓/大单）数据不可用，已跳过",
            ]
            signals: List[str] = []
            risk_level = "low"
            outlook = "neutral"

            # 规则13 代理 A：全市场跌停家数（来自大盘情绪数据源的 raw_data）
            limit_down = None
            limit_up = None
            market = self.market_sentiment_source.get_sentiment_data()
            if isinstance(market, dict) and market.get("status") == "success":
                raw = market.get("raw_data", {}) or {}
                limit_down = raw.get("limit_down")
                limit_up = raw.get("limit_up")
                if limit_down is not None:
                    signals.append(f"全市场跌停 {limit_down} 家 / 涨停 {limit_up} 家")
            else:
                uncertainties.append("大盘情绪数据获取失败，规则13跌停家数代理不可用")

            # 规则13 代理 B：北向资金流出（来自 akshare 大盘资金流）
            north_inflow = None
            try:
                mflow = self.akshare_source.get_market_fund_flow()
                if isinstance(mflow, dict) and mflow.get("status") == "success":
                    north_inflow = (mflow.get("northbound", {}) or {}).get(
                        "northbound_net_inflow"
                    )
            except Exception as e:  # noqa: BLE001
                uncertainties.append(f"北向资金代理获取失败：{e}")

            # 个股主力净流入（规则11 机构资金流出的近似）
            stock_main_inflow = None
            try:
                sflow = self.akshare_source.get_stock_fund_flow(stock_code)
                if isinstance(sflow, dict) and sflow.get("status") == "success":
                    stock_main_inflow = (sflow.get("summary", {}) or {}).get(
                        "近5日主力净流入"
                    )
                    if stock_main_inflow is not None:
                        signals.append(f"个股近5日主力净流入 {stock_main_inflow}")
            except Exception as e:  # noqa: BLE001
                uncertainties.append(f"个股资金流获取失败：{e}")

            # ── 规则13 触发判定（市场踩踏代理）──
            crash_hard = (
                limit_down is not None and limit_down > 100
                and north_inflow is not None and north_inflow < 0
            )
            crash_soft = limit_down is not None and limit_down > 100

            if crash_hard:
                outlook, risk_level = "negative", "high"
                signals.append("规则13硬触发：跌停>100家且北向净流出，疑似全市场流动性枯竭")
                confidence = 0.75
            elif crash_soft:
                outlook, risk_level = "negative", "medium"
                signals.append("规则13软预警：全市场跌停>100家，疑似市场恐慌")
                confidence = 0.65
            elif stock_main_inflow is not None and stock_main_inflow < 0:
                outlook, risk_level = "negative", "medium"
                signals.append("个股主力资金持续净流出，流动性边际转弱")
                confidence = 0.55
            else:
                outlook, risk_level = "neutral", "low"
                signals.append("基础流动性代理未触发预警")
                confidence = 0.45

            direction = "bearish" if outlook == "negative" else "neutral"

            return {
                "status": "success",
                "dimension": "liquidity",
                "direction": direction,
                "confidence": confidence,
                "reasoning": "；".join(signals),
                "risk_level": risk_level,
                "liquidity_outlook": outlook,
                "signals": signals,
                "indicators": {
                    "limit_down": limit_down,
                    "north_net_inflow": north_inflow,
                    "stock_main_inflow_5d": stock_main_inflow,
                },
                "uncertainties": uncertainties,
            }
        except Exception as e:  # noqa: BLE001
            self.log(f"流动性分析异常：{e}", level="error")
            return self._error_result("liquidity", f"流动性分析异常：{e}")

    # ══════════════════════════════════════════════════════════
    # 子分析二：估值泡沫（valuation_bubble_monitor）
    # ══════════════════════════════════════════════════════════

    def _analyze_valuation(self, stock_code: str) -> Dict[str, Any]:
        """
        估值核心数据（指数 PE 分位 / 股息率 / 无风险利率 / 巴菲特指标）当前完全缺失。
        按 Skill 的「指数 PE TTM 也缺失」降级分支：输出 neutral、低置信、需人工复核。
        诚实降级，不伪造估值结论。
        """
        try:
            reason = (
                "估值核心数据缺失（PE分位/股息率/无风险利率/巴菲特指标均无数据源），"
                "估值维度第一步未启用，按 Skill 降级为中性"
            )
            return {
                "status": "skipped",
                "dimension": "valuation",
                "direction": "neutral",
                "confidence": 0.3,
                "reasoning": reason,
                "score": 50.0,
                "risk_level": "low",
                "signals": ["估值维度数据缺失，未启用"],
                "indicators": {},
                "uncertainties": [reason],
                "needs_human_review": True,
            }
        except Exception as e:  # noqa: BLE001
            return self._error_result("valuation", f"估值分析异常：{e}")

    # ══════════════════════════════════════════════════════════
    # 子分析三：六维风控框架（risk_control_framework）
    # ══════════════════════════════════════════════════════════

    def _analyze_risk_framework(self, stock_code: str) -> Dict[str, Any]:
        """
        落地六维中有真值的维度：
          - 信号4 资金流向：个股主力 + 北向（akshare）
          - 信号5 情绪极值：大盘情绪 score（market_sentiment）
          - 信号2 杠杆热度：融资余额变化率（market_sentiment）
        跳过（记 uncertainties）：
          - 信号1 盈利-债务差（需财报深加工）
          - 信号3 估值泡沫（PE分位缺失）
          - 信号6 全球流动性约束（VIX/美债缺失）
        """
        try:
            uncertainties: List[str] = [
                "信号1盈利-债务差（需财报深加工）、信号3估值泡沫（PE分位缺失）、"
                "信号6全球流动性约束（VIX/美债缺失）第一步未启用，已跳过",
            ]
            signals: List[str] = []
            bearish_hits = 0
            bullish_hits = 0
            active_dims = 0

            market = self.market_sentiment_source.get_sentiment_data()
            sentiment_score = None
            margin_change = None
            if isinstance(market, dict) and market.get("status") == "success":
                sentiment_score = market.get("score")
                raw = market.get("raw_data", {}) or {}
                margin_change = raw.get("margin_change")

                # 信号5 情绪极值：score>80 过热(风险↑)，score<20 冰点(风险↓)
                if sentiment_score is not None:
                    active_dims += 1
                    if sentiment_score >= 80:
                        bearish_hits += 1
                        signals.append(f"信号5情绪过热：大盘情绪温度 {sentiment_score:.0f}/100")
                    elif sentiment_score <= 20:
                        bullish_hits += 1
                        signals.append(f"信号5情绪冰点：大盘情绪温度 {sentiment_score:.0f}/100（逆向偏多）")
                    else:
                        signals.append(f"信号5情绪中性：温度 {sentiment_score:.0f}/100")

                # 信号2 杠杆热度：融资余额快速上升=过热；快速下降=被动去杠杆(风险)
                if margin_change is not None:
                    active_dims += 1
                    if margin_change > 5:
                        bearish_hits += 1
                        signals.append(f"信号2杠杆过热：融资余额变化 {margin_change:+.1f}%")
                    elif margin_change < -10:
                        bearish_hits += 1
                        signals.append(f"信号2被动去杠杆：融资余额变化 {margin_change:+.1f}%（强制维持风险）")
                    else:
                        signals.append(f"信号2杠杆温和：融资余额变化 {margin_change:+.1f}%")
            else:
                uncertainties.append("大盘情绪数据获取失败，信号2/5未启用")

            # 信号4 资金流向
            try:
                sflow = self.akshare_source.get_stock_fund_flow(stock_code)
                if isinstance(sflow, dict) and sflow.get("status") == "success":
                    active_dims += 1
                    main5 = (sflow.get("summary", {}) or {}).get("近5日主力净流入")
                    if main5 is not None:
                        if main5 < 0:
                            bearish_hits += 1
                            signals.append(f"信号4资金流出：近5日主力净流入 {main5}")
                        else:
                            bullish_hits += 1
                            signals.append(f"信号4资金流入：近5日主力净流入 {main5}")
                else:
                    uncertainties.append("个股资金流获取失败，信号4未启用")
            except Exception as e:  # noqa: BLE001
                uncertainties.append(f"信号4资金流异常：{e}")

            if active_dims == 0:
                return self._error_result(
                    "framework", "六维框架可用维度全部取数失败，未启用"
                )

            # 综合方向：看空命中多→bearish；看多命中多→neutral/偏多
            if bearish_hits >= 2:
                direction, risk_level, confidence = "bearish", "high", 0.7
            elif bearish_hits == 1:
                direction, risk_level, confidence = "bearish", "medium", 0.55
            elif bullish_hits >= 2:
                direction, risk_level, confidence = "neutral", "low", 0.5
            else:
                direction, risk_level, confidence = "neutral", "low", 0.45

            return {
                "status": "success",
                "dimension": "framework",
                "direction": direction,
                "confidence": confidence,
                "reasoning": "；".join(signals) if signals else "六维框架未触发明显风险",
                "risk_level": risk_level,
                "signals": signals,
                "indicators": {
                    "sentiment_score": sentiment_score,
                    "margin_change_pct": margin_change,
                    "active_dims": active_dims,
                    "bearish_hits": bearish_hits,
                    "bullish_hits": bullish_hits,
                },
                "uncertainties": uncertainties,
            }
        except Exception as e:  # noqa: BLE001
            self.log(f"六维框架分析异常：{e}", level="error")
            return self._error_result("framework", f"六维框架分析异常：{e}")

    # ══════════════════════════════════════════════════════════
    # 聚合 + 流动性一票否决
    # ══════════════════════════════════════════════════════════

    def _build_combined_signal(
        self,
        stock_code: str,
        liq: Dict[str, Any],
        val: Dict[str, Any],
        framework: Dict[str, Any],
    ) -> Signal:
        """
        聚合三组子分析：
          1. 以六维框架方向为主信号；流动性/估值做 boost/penalty 修正。
          2. 流动性一票否决权：liquidity risk=high 且 outlook=negative 时，
             强制最终方向不为 bullish（本 Agent 不产 bullish，等价于压到 bearish/neutral），
             并标记 veto_authority.active=true。
        """
        # 汇总不确定性
        all_uncertainties: List[str] = []
        for part in (liq, val, framework):
            all_uncertainties.extend(part.get("uncertainties", []))

        # 主信号：六维框架
        direction = framework.get("direction", "neutral")
        confidence = framework.get("confidence", 0.4)
        risk_level = framework.get("risk_level", "low")

        # 流动性修正
        liq_dir = liq.get("direction", "neutral")
        if liq_dir != "neutral" and direction != "neutral":
            if liq_dir == direction:
                confidence = min(0.9, confidence + 0.05)
            else:
                confidence = max(0.2, confidence - 0.08)
        elif liq_dir == "bearish" and direction == "neutral":
            # 流动性看空、框架中性 → 偏向谨慎
            direction = "bearish"
            confidence = max(confidence, liq.get("confidence", 0.5))

        risk_level = _max_risk(risk_level, liq.get("risk_level", "low"))

        # ── 流动性一票否决权 ──
        veto_active = (
            liq.get("risk_level") == "high"
            and liq.get("liquidity_outlook") == "negative"
        )
        veto = {
            "active": bool(veto_active),
            "condition": "liquidity risk_level=high AND liquidity_outlook=negative",
            "downstream_instruction": "抑制所有 bullish 信号，直至流动性恢复",
        }
        if veto_active:
            direction = "bearish"
            risk_level = "high"
            confidence = max(confidence, 0.7)

        # 仓位建议（风险越高 → 仓位越低）
        position_advice = self._position_advice(risk_level)

        # 汇总 signals / reasoning
        signals: List[str] = []
        for tag, part in (("流动性", liq), ("估值", val), ("框架", framework)):
            for s in part.get("signals", [])[:2]:
                signals.append(f"[{tag}] {s}")
        if veto_active:
            signals.insert(0, "[否决] 流动性一票否决权生效：流动性危机，已抑制看多")

        reasoning = (
            f"风控综合：{direction.upper()}（risk_level={risk_level}）。"
            f"主信号取六维框架（{framework.get('reasoning', '')}）；"
            f"流动性维度（{liq.get('reasoning', '')}）；"
            f"估值维度（{val.get('reasoning', '')}）。"
            f"仓位建议：{position_advice}。"
        )
        if veto_active:
            reasoning += "【流动性一票否决权生效，所有看多信号被抑制】"

        needs_review = bool(
            veto_active
            or val.get("needs_human_review")
            or risk_level == "high"
        )

        meta: Dict[str, Any] = {
            "output_version": "1.0",
            "skill_name": "risk_agent_skeleton_v1",
            "owner_group": "专家7组（风控）",
            "target": stock_code,
            "risk_level": risk_level,
            "liquidity_outlook": liq.get("liquidity_outlook", "neutral"),
            "veto_authority": veto,
            "position_advice": position_advice,
            "data_mode": "basic",
            "dimensions": {
                "liquidity": {
                    "status": liq.get("status"),
                    "direction": liq.get("direction"),
                    "risk_level": liq.get("risk_level"),
                    "indicators": liq.get("indicators", {}),
                },
                "valuation": {
                    "status": val.get("status"),
                    "direction": val.get("direction"),
                },
                "framework": {
                    "status": framework.get("status"),
                    "direction": framework.get("direction"),
                    "risk_level": framework.get("risk_level"),
                    "indicators": framework.get("indicators", {}),
                },
            },
            "uncertainties": all_uncertainties,
            "needs_human_review": needs_review,
        }

        # 本 Agent 只产出 bearish / neutral（风控天职是预警，不主动看多）
        if direction == "bearish":
            return bearish_signal(
                confidence=confidence,
                reasoning=reasoning,
                signals=signals,
                source=self.name,
                stock_code=stock_code,
                signal_type=self.signal_type,
                meta=meta,
            )
        # neutral：直接用 Signal 以携带 signals/meta（neutral_signal 会清空 signals）
        return Signal(
            direction="neutral",
            confidence=confidence,
            reasoning=reasoning,
            signals=signals,
            source=self.name,
            stock_code=stock_code,
            signal_type=self.signal_type,
            meta=meta,
        )

    # ── 仓位建议 ──────────────────────────────────────────────

    @staticmethod
    def _position_advice(risk_level: str) -> str:
        """根据风险等级给出粗略仓位上限建议"""
        if risk_level == "high":
            return "≤30%（高风险，建议显著降低仓位）"
        if risk_level == "medium":
            return "30%-60%（中风险，控制仓位、保留对冲）"
        return "60%-80%（低风险，正常仓位）"
