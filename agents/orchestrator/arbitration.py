"""
仲裁引擎 —— 从场景对象读取权重和规则，实现松耦合多场景仲裁。

方法论依据：
  权重体系基于桥水经济机器模型（Ray Dalio）的三维度框架：
  经济增长方向、通胀方向和风险溢价水平的不同组合定义了
  三种市场场景（牛市/熊市/震荡市）。每个场景内的专家权重逻辑
  由对应场景的 ScenarioProfile 子类实现，并通过因子研究
  （QuantPedia、AQR、CEPR、LuxAlgo）交叉验证。
  详细理论依据见开发2组 SKILL.md。

Orchestrator Agent 的核心组件，职责：
  1. 信号筛选（置信度阈值，可由场景覆盖）
  2. 从场景对象获取专家权重（松耦合）
  3. 加权聚合（动态权重，附带理由）
  4. 方向判定
  5. 仓位建议（从场景对象获取公式）
  6. 风险检查（信号风险 + 场景风险，区分阻塞性与信息性）
  7. 推理链生成（含权重理由追溯，白箱可审计）
"""

from typing import List, Dict, Any, Optional, Tuple, TYPE_CHECKING
from dataclasses import dataclass, field
from agents.signal import Signal, SignalBundle, Direction
from agents.orchestrator.scenario_profile import ScenarioProfile, DefaultScenario
from loguru import logger

if TYPE_CHECKING:
    from agents.orchestrator.reasoning_chain import StandardizedReasoningChain


@dataclass
class ArbitrationResult:
    """仲裁结果 —— 数据结构不变，保持与 ricardo0wu PR #27 兼容"""
    decision: str                    # buy/hold/sell/wait
    direction: str                  # bullish/bearish/neutral
    confidence: float               # 综合置信度
    position_ratio: float          # 建议仓位 (0.0 ~ 1.0)
    reasoning: str                 # 决策推理
    signals_summary: Dict[str, int] # 信号汇总
    risks: List[str]               # 风险提示
    reasoning_chain: List[str]      # 推理链（含场景信息、权重理由）—— 保留兼容
    scope_trace: Dict[str, Any] = field(default_factory=dict)  # AgentScope 编排追踪
    standardized_chain: Optional[Any] = None  # 标准化推理链（v8 新增）
    uncertainties: List[str] = field(default_factory=list)  # 不确定性追踪（信号覆盖缺口、低置信度、场景切换等）


class ArbitrationEngine:
    """
    仲裁引擎 —— 松耦合多场景版本。

    核心改造（相对 ricardo0wu 第一版）：
      1. 权重不再写死在代码里 → 从场景对象读取
      2. 每个权重附带理由 → 支持白箱可追溯
      3. 仓位公式从场景对象获取 → 不同场景不同策略
      4. 场景特有风险自动合并 → 信号风险 + 场景风险
    """

    def __init__(
        self,
        confidence_threshold: float = 0.6,
        scenario: Optional[ScenarioProfile] = None,
    ):
        """
        初始化仲裁引擎。

        参数:
            confidence_threshold: 信号置信度筛选阈值（默认 0.6）
            scenario: 市场场景对象。如果为 None，使用 DefaultScenario（等权）
        """
        self.confidence_threshold = confidence_threshold
        self.scenario = scenario if scenario is not None else DefaultScenario()

        logger.info(
            f"[仲裁引擎] 初始化完成 - "
            f"置信度阈值:{confidence_threshold}, "
            f"场景:{self.scenario.display_name}"
        )

    def arbitrate(
        self,
        signal_bundle: SignalBundle,
        trend_direction: Optional[str] = None,
        execution_trace: Optional[Dict[str, Any]] = None,
    ) -> ArbitrationResult:
        """执行仲裁 —— 10 步流水线（含场景权重追溯）"""
        logger.info(f"[仲裁引擎] 开始仲裁，共{len(signal_bundle.signals)}个信号")

        # Step 1: 信号筛选
        # 场景可以覆盖置信度阈值（震荡市降低、熊市保持严格）
        threshold = self.scenario.get_confidence_threshold()
        if threshold is None:
            threshold = self.confidence_threshold
        if threshold != self.confidence_threshold:
            logger.info(
                f"[仲裁引擎] 场景覆盖阈值: {self.confidence_threshold} → {threshold} "
                f"({self.scenario.display_name})"
            )
        filtered_signals = signal_bundle.filter_by_confidence(threshold)
        logger.info(f"[仲裁引擎] 筛选后剩余{len(filtered_signals)}个信号")

        if not filtered_signals:
            return self._empty_result(execution_trace)

        # Step 2: 信号分类汇总
        signals_summary = self._summarize_signals(filtered_signals)

        # Step 3: 加权评分（从场景对象获取每个专家的权重 + 理由）
        bullish_score, bearish_score, weight_reasons = self._calculate_scores(
            filtered_signals
        )

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

        # Step 7: 仓位建议（从场景对象获取公式）
        position_ratio, position_formula = self._calculate_position(
            confidence, direction
        )

        # Step 8: 风险检查（信号层面 + 场景层面）
        risks = self._check_risks(filtered_signals, direction)
        risks.extend(self._check_execution_trace(execution_trace))
        # 合并场景层面的风险提示
        scenario_risks = self.scenario.get_scenario_risks()
        risks.extend(scenario_risks)

        # Step 9: 决策输出
        decision = self._make_decision(direction, confidence, position_ratio, risks)

        # Step 9.5: 收集不确定性追踪
        uncertainties = self._collect_uncertainties(
            total_signals=len(signal_bundle.signals),
            filtered_signals=filtered_signals,
            threshold=threshold,
            direction=direction,
            execution_trace=execution_trace,
        )

        # Step 10: 生成推理链（含场景信息、权重理由追溯）
        reasoning_chain = self._generate_reasoning_chain(
            signals_summary, direction, confidence,
            position_ratio, position_formula, risks,
            weight_reasons, execution_trace, uncertainties,
        )

        # Step 11: 构建标准化推理链（v8 新增 —— 共识/分歧标注 + 贡献追踪）
        standardized_chain = self._build_standardized_chain(
            filtered_signals=filtered_signals,
            direction=direction,
            confidence=confidence,
            position_ratio=position_ratio,
            position_formula=position_formula,
            risks=risks,
            weight_reasons=weight_reasons,
            execution_trace=execution_trace,
            bullish_score=bullish_score,
            bearish_score=bearish_score,
            uncertainties=uncertainties,
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
            scope_trace=execution_trace or {},
            standardized_chain=standardized_chain,
            uncertainties=uncertainties,
        )

        logger.info(
            f"[仲裁引擎] 仲裁完成 - "
            f"决策:{decision}, 方向:{direction}, "
            f"置信度:{confidence:.1%}, 仓位:{position_ratio:.0%}"
        )

        return result

    # ============================================================
    # Step 2: 信号汇总
    # ============================================================

    def _summarize_signals(self, signals: List[Signal]) -> Dict[str, int]:
        """汇总信号 —— 按方向和类型统计（逻辑不变）"""
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
                    summary["by_type"][s.signal_type] = {
                        "bullish": 0, "bearish": 0, "neutral": 0
                    }
                summary["by_type"][s.signal_type][s.direction] += 1
        return summary

    # ============================================================
    # Step 3: 加权评分（核心改造点）
    # ============================================================

    def _calculate_scores(
        self, signals: List[Signal]
    ) -> Tuple[float, float, Dict[str, Tuple[float, str]]]:
        """
        计算看多和看空得分，同时收集权重理由。

        改造前（第一版）:
          所有信号统一乘 global_bullish_weight / global_bearish_weight

        改造后（当前版本）:
          每个信号按其专家类型从场景对象获取专属权重
          权重附带理由，供推理链展示

        返回:
            (bullish_score, bearish_score, weight_reasons)
            weight_reasons 格式: {expert_type: (权重值, 权重理由)}
        """
        bullish_score = 0.0
        bearish_score = 0.0
        weight_reasons: Dict[str, Tuple[float, str]] = {}

        for s in signals:
            # 从场景获取该专家类型在当前场景下的权重
            expert_type = s.signal_type or "unknown"
            expert_weight, weight_reason = self.scenario.get_weight(expert_type)

            # 记录权重理由（同一个专家类型只记录一次）
            if expert_type not in weight_reasons:
                weight_reasons[expert_type] = (expert_weight, weight_reason)

            # 综合权重 = 信号自身置信度 × 信号自身权重 × 场景专家权重
            final_weight = s.confidence * s.weight * expert_weight

            if s.direction == "bullish":
                bullish_score += final_weight
            elif s.direction == "bearish":
                bearish_score += final_weight

        logger.debug(
            f"[仲裁引擎] 加权完成 - "
            f"看多得分:{bullish_score:.3f}, 看空得分:{bearish_score:.3f}, "
            f"涉及{len(weight_reasons)}类专家"
        )

        return bullish_score, bearish_score, weight_reasons

    # ============================================================
    # Step 4: 方向判定（逻辑不变）
    # ============================================================

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

    # ============================================================
    # Step 6: 综合置信度（逻辑不变）
    # ============================================================

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

    # ============================================================
    # Step 7: 仓位建议（核心改造点）
    # ============================================================

    def _calculate_position(
        self, confidence: float, direction: str
    ) -> Tuple[float, str]:
        """
        计算仓位建议 —— 从场景对象获取公式。

        改造前（第一版）:
          position = confidence * 0.5，硬上限 0.3

        改造后（当前版本）:
          委托给场景对象的 get_position_ratio 方法
          不同场景可以有不同的系数和上限

        返回:
            (仓位比例, 计算公式说明)
        """
        position, formula = self.scenario.get_position_ratio(confidence, direction)
        logger.debug(f"[仲裁引擎] 仓位计算 - {formula}")
        return position, formula

    # ============================================================
    # Step 8: 风险检查（信号层面逻辑基本不变，场景风险在 arbitrate 中合并）
    # ============================================================

    def _check_risks(self, signals: List[Signal], direction: str) -> List[str]:
        """信号层面的风险检查（返回所有风险，由 _make_decision 区分处理）"""
        risks = []
        blocking_risks = []  # 阻塞性风险：应阻止交易执行

        risk_signals = [s for s in signals if s.signal_type == "risk"]
        for s in risk_signals:
            if s.confidence > 0.7:
                # 风控组信号是信息性的，不阻塞决策
                # （熊市中风控组看空是正常的，不应因此阻止卖出）
                risks.append(f"🔴 风控信号: {s.reasoning}")

        if len(signals) < 3:
            blocking_risks.append("🔒 信号数量较少（<3），建议保持观望")

        summary = self._summarize_signals(signals)
        if summary["total"] > 0:
            dominant_ratio = max(
                summary["bullish"] / summary["total"],
                summary["bearish"] / summary["total"]
            )
            if dominant_ratio < 0.5:
                risks.append("⚠️ 信号方向分散，意见不统一")

        # 合并返回：阻塞性风险放在最后供 _make_decision 识别
        return risks + blocking_risks

    def _check_execution_trace(
        self, execution_trace: Optional[Dict[str, Any]]
    ) -> List[str]:
        """将编排执行完整性补充进风险提示，区分阻塞性和信息性风险。"""
        if not execution_trace:
            return []

        summary = execution_trace.get("summary", {})
        failed_count = summary.get("failed_count", 0)
        timeout_count = summary.get("timeout_count", 0)
        invalid_count = summary.get("invalid_count", 0)
        success_count = summary.get("success_count", 0)
        total_agents = summary.get("total_agents", 0)

        risks = []
        incomplete_count = failed_count + timeout_count + invalid_count
        if incomplete_count:
            risks.append(
                "编排提示："
                f"{incomplete_count} 个Agent未产出有效Signal"
                f"（失败{failed_count}，超时{timeout_count}，无效{invalid_count}）"
            )

        if total_agents and success_count < 3:
            # 🔒 阻塞性风险：有效Agent不足以做出可靠决策
            risks.append(
                "🔒 有效Agent少于3个，仲裁可靠性不足，建议观望"
            )

        return risks

    # ============================================================
    # Step 9: 决策输出（逻辑不变）
    # ============================================================

    def _make_decision(
        self,
        direction: str,
        confidence: float,
        position_ratio: float,
        risks: List[str]
    ) -> str:
        """
        做出最终决策。

        风险分类：
          🔒 阻塞性风险 → 强制 hold（信号不足、Agent大规模失败等）
          🔴 风控信号   → 信息性的，不阻塞交易（熊市中看空是正常的）
          ⚠️ 提示性风险 → 信息性的，不阻塞交易
        """
        # 🔒 阻塞性风险检查（信号不足等结构性缺陷）
        blocking_risks = [r for r in risks if "🔒" in r]
        if blocking_risks:
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

    # ============================================================
    # 不确定性追踪
    # ============================================================

    def _collect_uncertainties(
        self,
        total_signals: int,
        filtered_signals: List[Signal],
        threshold: float,
        direction: str,
        execution_trace: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """收集仲裁链路上的所有不确定性，贯穿整个分析流程。

        参照指标组的 uncertainties 设计，记录：
          - 信号覆盖不足（某些专家未产出有效 Signal）
          - 置信度刚过线（低确定性信号）
          - 场景切换（置信度阈值的动态调整）
          - 方向性信号比例偏低（多空分歧大）
          - 编排执行中的异常（Agent 失败、超时）

        Returns:
            不确定性列表，每项为自然语言描述。
        """
        uncertainties = []

        # 信号覆盖缺口
        if len(filtered_signals) < 7:
            missing = 7 - len(filtered_signals)
            uncertainties.append(
                f"专家信号覆盖不足：7 个专家组中仅 {len(filtered_signals)} 个产出有效 "
                f"Signal（缺失 {missing} 个）。可能原因：置信度过低、执行失败或超时。"
            )

        # 低置信度信号
        low_conf = [s for s in filtered_signals if s.confidence < 0.6]
        if low_conf:
            sources = [s.source or s.signal_type for s in low_conf]
            uncertainties.append(
                f"低置信度信号：{', '.join(sources)} 的置信度低于 0.6，"
                f"对应方向的确定性较弱。"
            )

        # 场景阈值覆盖
        if threshold != self.confidence_threshold:
            uncertainties.append(
                f"场景切换{self.scenario.display_name}：置信度阈值从 "
                f"{self.confidence_threshold} 调整为 {threshold}，"
                f"低置信度信号被保留以增加信息覆盖。"
            )

        # 方向性分歧评估
        bullish_n = sum(1 for s in filtered_signals if s.direction == "bullish")
        bearish_n = sum(1 for s in filtered_signals if s.direction == "bearish")
        neutral_n = sum(1 for s in filtered_signals if s.direction == "neutral")
        total_n = len(filtered_signals)
        if total_n > 0:
            dominant_ratio = max(bullish_n, bearish_n) / total_n
            if dominant_ratio < 0.6:
                uncertainties.append(
                    f"方向信号分散：看多{bullish_n}/看空{bearish_n}/中性{neutral_n}，"
                    f"主导方向仅占 {dominant_ratio:.0%}，共识度偏低。"
                )

        # 编排执行异常
        if execution_trace:
            summary = execution_trace.get("summary", {})
            failed = summary.get("failed_count", 0)
            timeout = summary.get("timeout_count", 0)
            invalid = summary.get("invalid_count", 0)
            if failed or timeout or invalid:
                uncertainties.append(
                    f"编排执行异常：{failed} 个 Agent 失败、{timeout} 个超时、"
                    f"{invalid} 个产出无效，信号完整性受{failed + timeout + invalid}个异常影响。"
                )

        return uncertainties

    # ============================================================
    # Step 10: 推理链生成（核心改造点 —— 加入场景和权重追溯）
    # ============================================================

    def _generate_reasoning_chain(
        self,
        signals_summary: Dict[str, int],
        direction: str,
        confidence: float,
        position_ratio: float,
        position_formula: str,
        risks: List[str],
        weight_reasons: Optional[Dict[str, Tuple[float, str]]] = None,
        execution_trace: Optional[Dict[str, Any]] = None,
        uncertainties: Optional[List[str]] = None,
    ) -> List[str]:
        """
        生成推理链 —— 包含场景信息和权重追溯。

        改造后新增：
          - 场景信息（名称、描述）
          - 专家权重追溯表（每个专家的权重 + 理由）
          - 仓位公式说明（从场景对象获取）
        """
        chain = []

        # ---- 场景信息 ----
        chain.append(
            f"🏷️ 仲裁场景：{self.scenario.display_name}"
        )
        chain.append(
            f"📋 场景说明：{self.scenario.description}"
        )

        # ---- 专家权重追溯（白箱可审计核心） ----
        if weight_reasons:
            chain.append("⚖️ 场景权重配置（可追溯）：")
            for expert_type, (weight_val, reason) in weight_reasons.items():
                direction_mark = "↑" if weight_val > 1.0 else "↓" if weight_val < 1.0 else "→"
                chain.append(
                    f"   {expert_type}: {weight_val:.1f} {direction_mark} 理由: {reason}"
                )

        # ---- 信号汇总 ----
        chain.append("")
        chain.append(
            f"📊 信号汇总：共{signals_summary.get('total', 0)}个信号，"
            f"看多{signals_summary.get('bullish', 0)}个，"
            f"看空{signals_summary.get('bearish', 0)}个，"
            f"中性{signals_summary.get('neutral', 0)}个"
        )

        # ---- 编排追踪 ----
        if execution_trace:
            summary = execution_trace.get("summary", {})
            chain.append(
                "🧭 编排追踪："
                f"注册{summary.get('total_agents', 0)}个Agent，"
                f"成功{summary.get('success_count', 0)}个，"
                f"失败{summary.get('failed_count', 0)}个，"
                f"超时{summary.get('timeout_count', 0)}个，"
                f"无效{summary.get('invalid_count', 0)}个"
            )

        # ---- 方向判定 ----
        direction_text = {"bullish": "看多", "bearish": "看空", "neutral": "中性"}
        chain.append(f"🎯 方向判定：{direction_text.get(direction, '未知')}")

        # ---- 置信度 ----
        confidence_level = "高" if confidence > 0.7 else "中" if confidence > 0.5 else "低"
        chain.append(f"📈 置信度：{confidence:.1%}（{confidence_level}）")

        # ---- 仓位建议（含公式说明） ----
        if position_ratio > 0:
            chain.append(f"💼 仓位建议：{position_ratio:.0%}")
            chain.append(f"   计算公式：{position_formula}")
        else:
            chain.append("💼 仓位建议：观望")

        # ---- 风险提示 ----
        if risks:
            chain.append("⚠️ 风险提示：")
            chain.extend(risks)
        else:
            chain.append("✅ 风险检查：无明显风险")

        # ---- 不确定性追踪 ----
        if uncertainties:
            chain.append("")
            chain.append("🔍 不确定性追踪：")
            for u in uncertainties:
                chain.append(f"   {u}")

        return chain

    def _build_standardized_chain(
        self,
        filtered_signals: List[Signal],
        direction: str,
        confidence: float,
        position_ratio: float,
        position_formula: str,
        risks: List[str],
        weight_reasons: Dict[str, Tuple[float, str]],
        execution_trace: Optional[Dict[str, Any]],
        bullish_score: float,
        bearish_score: float,
        uncertainties: Optional[List[str]] = None,
    ) -> "StandardizedReasoningChain":
        """构建标准化推理链（v8 新增）—— 共识/分歧标注 + 权重贡献追踪 + 不确定性追踪。

        委托给 reasoning_chain.build_standardized_chain()，
        传递仲裁过程中产生的全部结构化数据。
        """
        from agents.orchestrator.reasoning_chain import build_standardized_chain

        return build_standardized_chain(
            signals=filtered_signals,
            scenario=self.scenario,
            direction=direction,
            confidence=confidence,
            position_ratio=position_ratio,
            position_formula=position_formula,
            risks=risks,
            weight_reasons=weight_reasons,
            execution_trace=execution_trace,
            bullish_score=bullish_score,
            bearish_score=bearish_score,
            uncertainties=uncertainties or [],
        )

    # ============================================================
    # 空结果处理
    # ============================================================

    def _empty_result(
        self, execution_trace: Optional[Dict[str, Any]] = None
    ) -> ArbitrationResult:
        """空结果 —— 信号不足时的降级处理"""
        risks = ["⚠️ 有效信号不足"]
        risks.extend(self._check_execution_trace(execution_trace))
        # 即使是空结果，也包含场景信息
        risks.append(f"当前场景：{self.scenario.display_name}")

        reasoning_chain = [
            f"🏷️ 仲裁场景：{self.scenario.display_name}",
            "无有效信号，建议观望"
        ]
        if execution_trace:
            summary = execution_trace.get("summary", {})
            reasoning_chain.append(
                "🧭 编排追踪："
                f"注册{summary.get('total_agents', 0)}个Agent，"
                f"成功{summary.get('success_count', 0)}个，"
                f"失败{summary.get('failed_count', 0)}个，"
                f"超时{summary.get('timeout_count', 0)}个，"
                f"无效{summary.get('invalid_count', 0)}个"
            )

        return ArbitrationResult(
            decision="wait",
            direction="neutral",
            confidence=0.0,
            position_ratio=0.0,
            reasoning="\n".join(reasoning_chain),
            signals_summary={"total": 0, "bullish": 0, "bearish": 0, "neutral": 0},
            risks=risks,
            reasoning_chain=reasoning_chain,
            scope_trace=execution_trace or {},
            standardized_chain=None,
        )
