"""
仲裁引擎 - 从 arbitration/engine.py 迁移

Orchestrator Agent 的核心组件，职责：
  1. 信号筛选（置信度阈值）
  2. 加权聚合
  3. 方向判定
  4. 仓位建议
  5. 风险检查
  6. 推理链生成
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from agents.signal import Signal, SignalBundle, Direction
from loguru import logger


@dataclass
class ArbitrationResult:
    """仲裁结果"""
    decision: str                    # buy/hold/sell/wait
    direction: str                  # bullish/bearish/neutral
    confidence: float               # 综合置信度
    position_ratio: float          # 建议仓位 (0.0 ~ 1.0)
    reasoning: str                 # 决策推理
    signals_summary: Dict[str, int] # 信号汇总
    risks: List[str]               # 风险提示
    reasoning_chain: List[str]      # 推理链


class ArbitrationEngine:
    """
    仲裁引擎

    Orchestrator Agent 的核心仲裁逻辑。
    收集7个专家Agent的信号，执行10步仲裁流程。
    """

    def __init__(
        self,
        confidence_threshold: float = 0.6,
        bullish_weight: float = 1.0,
        bearish_weight: float = 1.0,
        risk_coefficient: float = 0.2,
    ):
        self.confidence_threshold = confidence_threshold
        self.bullish_weight = bullish_weight
        self.bearish_weight = bearish_weight
        self.risk_coefficient = risk_coefficient

        logger.info(
            f"[仲裁引擎] 初始化完成 - "
            f"置信度阈值:{confidence_threshold}, "
            f"多空权重:{bullish_weight}/{bearish_weight}"
        )

    def arbitrate(
        self,
        signal_bundle: SignalBundle,
        trend_direction: Optional[str] = None,
    ) -> ArbitrationResult:
        """执行仲裁"""
        logger.info(f"[仲裁引擎] 开始仲裁，共{len(signal_bundle.signals)}个信号")

        # Step 1: 信号筛选
        filtered_signals = signal_bundle.filter_by_confidence(self.confidence_threshold)
        logger.info(f"[仲裁引擎] 筛选后剩余{len(filtered_signals)}个信号")

        if not filtered_signals:
            return self._empty_result()

        # Step 2: 信号分类汇总
        signals_summary = self._summarize_signals(filtered_signals)

        # Step 3: 加权评分
        bullish_score, bearish_score = self._calculate_scores(filtered_signals)

        # Step 4: 方向判定
        direction = self._determine_direction(bullish_score, bearish_score)

        # Step 5: 趋势一致性检查
        if trend_direction and direction != trend_direction:
            logger.warning(
                f"[仲裁引擎] 信号方向({direction})与趋势({trend_direction})不一致"
            )
            if direction == "bearish" and trend_direction == "bullish":
                if max(s.confidence for s in filtered_signals) < 0.8:
                    direction = "neutral"

        # Step 6: 综合置信度
        confidence = self._calculate_confidence(
            filtered_signals, direction, bullish_score, bearish_score
        )

        # Step 7: 仓位建议
        position_ratio = self._calculate_position(confidence, direction)

        # Step 8: 风险检查
        risks = self._check_risks(filtered_signals, direction)

        # Step 9: 决策输出
        decision = self._make_decision(direction, confidence, position_ratio, risks)

        # Step 10: 生成推理链
        reasoning_chain = self._generate_reasoning_chain(
            signals_summary, direction, confidence, position_ratio, risks
        )

        result = ArbitrationResult(
            decision=decision,
            direction=direction,
            confidence=confidence,
            position_ratio=position_ratio,
            reasoning="\n".join(reasoning_chain),
            signals_summary=signals_summary,
            risks=risks,
            reasoning_chain=reasoning_chain,
        )

        logger.info(
            f"[仲裁引擎] 仲裁完成 - "
            f"决策:{decision}, 方向:{direction}, "
            f"置信度:{confidence:.1%}, 仓位:{position_ratio:.0%}"
        )

        return result

    def _summarize_signals(self, signals: List[Signal]) -> Dict[str, int]:
        """汇总信号"""
        summary = {
            "total": len(signals),
            "bullish": 0,
            "bearish": 0,
            "neutral": 0,
            "by_type": {},
        }
        for s in signals:
            summary[s.direction] += 1
            if s.signal_type:
                if s.signal_type not in summary["by_type"]:
                    summary["by_type"][s.signal_type] = {"bullish": 0, "bearish": 0, "neutral": 0}
                summary["by_type"][s.signal_type][s.direction] += 1
        return summary

    def _calculate_scores(self, signals: List[Signal]) -> tuple:
        """计算看多和看空得分"""
        bullish_score = 0.0
        bearish_score = 0.0

        for s in signals:
            weighted_confidence = s.confidence * s.weight
            if s.direction == "bullish":
                bullish_score += weighted_confidence * self.bullish_weight
            elif s.direction == "bearish":
                bearish_score += weighted_confidence * self.bearish_weight

        return bullish_score, bearish_score

    def _determine_direction(self, bullish_score: float, bearish_score: float) -> str:
        """判定方向"""
        total = bullish_score + bearish_score
        if total == 0:
            return "neutral"

        bullish_ratio = bullish_score / total
        bearish_ratio = bearish_score / total

        if bullish_ratio > 0.6:
            return "bullish"
        elif bearish_ratio > 0.6:
            return "bearish"
        else:
            return "neutral"

    def _calculate_confidence(
        self,
        signals: List[Signal],
        direction: str,
        bullish_score: float,
        bearish_score: float
    ) -> float:
        """计算综合置信度"""
        count_bonus = min(len(signals) * 0.02, 0.2)

        if direction == "bullish":
            base_confidence = bullish_score / (bullish_score + bearish_score + 0.01)
        elif direction == "bearish":
            base_confidence = bearish_score / (bullish_score + bearish_score + 0.01)
        else:
            if bullish_score + bearish_score > 0:
                ratio = abs(bullish_score - bearish_score) / (bullish_score + bearish_score)
                base_confidence = ratio * 0.5
            else:
                base_confidence = 0.3

        confidence = min(base_confidence + count_bonus, 0.95)
        return confidence

    def _calculate_position(self, confidence: float, direction: str) -> float:
        """计算仓位建议"""
        if direction == "neutral":
            return 0.0

        position = confidence * 0.5
        position = min(position, 0.3)

        if direction == "neutral":
            position = 0.0

        return position

    def _check_risks(self, signals: List[Signal], direction: str) -> List[str]:
        """风险检查"""
        risks = []

        risk_signals = [s for s in signals if s.signal_type == "risk"]
        for s in risk_signals:
            if s.confidence > 0.7:
                risks.append(f"⚠️ {s.reasoning}")

        if len(signals) < 3:
            risks.append("⚠️ 信号数量较少，建议谨慎")

        summary = self._summarize_signals(signals)
        if summary["total"] > 0:
            dominant_ratio = max(
                summary["bullish"] / summary["total"],
                summary["bearish"] / summary["total"]
            )
            if dominant_ratio < 0.5:
                risks.append("⚠️ 信号方向分散，意见不统一")

        return risks

    def _make_decision(
        self,
        direction: str,
        confidence: float,
        position_ratio: float,
        risks: List[str]
    ) -> str:
        """做出最终决策"""
        high_risk = any("⚠️" in r for r in risks)

        if high_risk and direction != "neutral":
            return "hold"

        if direction == "bullish" and confidence > 0.5:
            if position_ratio > 0.2:
                return "buy"
            else:
                return "hold"
        elif direction == "bearish" and confidence > 0.5:
            return "sell"
        else:
            return "wait"

    def _generate_reasoning_chain(
        self,
        signals_summary: Dict[str, int],
        direction: str,
        confidence: float,
        position_ratio: float,
        risks: List[str]
    ) -> List[str]:
        """生成推理链"""
        chain = []

        chain.append(
            f"📊 信号汇总：共{signals_summary.get('total', 0)}个信号，"
            f"看多{signals_summary.get('bullish', 0)}个，"
            f"看空{signals_summary.get('bearish', 0)}个，"
            f"中性{signals_summary.get('neutral', 0)}个"
        )

        direction_text = {"bullish": "看多", "bearish": "看空", "neutral": "中性"}
        chain.append(f"🎯 方向判定：{direction_text.get(direction, '未知')}")

        confidence_level = "高" if confidence > 0.7 else "中" if confidence > 0.5 else "低"
        chain.append(f"📈 置信度：{confidence:.1%}（{confidence_level}）")

        if position_ratio > 0:
            chain.append(f"💼 仓位建议：{position_ratio:.0%}")
        else:
            chain.append("💼 仓位建议：观望")

        if risks:
            chain.append("⚠️ 风险提示：")
            chain.extend(risks)
        else:
            chain.append("✅ 风险检查：无明显风险")

        return chain

    def _empty_result(self) -> ArbitrationResult:
        """空结果"""
        return ArbitrationResult(
            decision="wait",
            direction="neutral",
            confidence=0.0,
            position_ratio=0.0,
            reasoning="没有足够的有效信号",
            signals_summary={"total": 0, "bullish": 0, "bearish": 0, "neutral": 0},
            risks=["⚠️ 有效信号不足"],
            reasoning_chain=["无有效信号，建议观望"],
        )
