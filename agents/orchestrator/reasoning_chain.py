"""
标准化推理链 —— 结构化共识/分歧标注与权重贡献追踪。

设计目标：
  将推理链从纯文本列表升级为结构化数据，支持：
    1. 共识标注 —— 哪些专家形成一致意见
    2. 分歧标注 —— 谁在反对、为什么
    3. 权重贡献追踪 —— 每个专家对最终得分的贡献占比
    4. 风险分类 —— 区分阻塞性/信息性/场景风险
    5. 白箱可审计 —— 从输入 Signal 到最终决策的完整链路可追溯

向后兼容：
  ArbitrationResult.reasoning_chain: List[str] 保持不变
  ArbitrationResult.standardized_chain: Optional[StandardizedReasoningChain] 新增

使用方式：
    from agents.orchestrator.reasoning_chain import build_standardized_chain
    chain = build_standardized_chain(
        signals=filtered_signals,
        scenario=self.scenario,
        direction="bullish",
        confidence=0.95,
        position_ratio=0.40,
        position_formula="0.60 × 0.95 = 0.57 → cap 0.40",
        risks=["🔴 风控告警: ...", "⚠️ 信号方向分散"],
        weight_reasons={"technical": (1.3, "理由...")},
        execution_trace={...},
    )
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from agents.signal import Signal


# ============================================================================
# 数据模型
# ============================================================================


@dataclass
class ExpertContribution:
    """单个专家信号对最终决策的贡献追踪。

    每行记录一个专家信号从输入到贡献的完整链路：
      Signal → 场景权重应用 → 最终得分贡献 → 归一化占比

    Attributes:
        source: 专家来源标识（如 "技术分析Agent"）
        signal_type: 信号类型（如 "technical"、"macro"）
        direction: 信号方向（bullish/bearish/neutral）
        confidence: 信号自身置信度（0.0-1.0）
        signal_weight: 信号自身权重（Agent 层面）
        expert_weight: 场景赋予该专家类型的权重
        effective_weight: 综合权重 = confidence × signal_weight × expert_weight
        contribution: 对最终同方向得分的绝对贡献值
        contribution_ratio: 贡献占比 = contribution / same_direction_total
        is_top_contributor: 是否为该方向的最大贡献者
        reasoning: 专家推理摘要（截断至 120 字）
    """

    source: str
    signal_type: str
    direction: str
    confidence: float
    signal_weight: float
    expert_weight: float
    effective_weight: float
    contribution: float
    contribution_ratio: float
    is_top_contributor: bool = False
    reasoning: str = ""


@dataclass
class ConsensusAnalysis:
    """共识与分歧分析。

    基于 7 个专家信号的方向分布，识别：
      - 共识（多数意见方向，占比 ≥ 50%）
      - 分歧（持有相反方向的专家）
      - 无共识（最大方向占比 < 50%）
      - 严重分歧（两个方向占比各 ≥ 40%）

    Attributes:
        consensus_direction: 共识方向（bullish/bearish/neutral/"none"）
        consensus_ratio: 共识方向占比（0.0-1.0）
        consensus_experts: 形成共识的专家列表 [{source, signal_type, direction, confidence}]
        divergent_experts: 持有异议的专家列表（同上格式）
        neutral_experts: 保持中立的专家列表（同上格式）
        divergence_type: 分歧类型
            - "none"      无分歧（一方占绝对主导）
            - "mild"      轻微分歧（少数异议但占比 < 40%）
            - "strong"    严重分歧（两个方向各 ≥ 40%）
            - "no_consensus"  无明确共识（最大方向 < 50%）
        analysis: 分歧分析文本说明
    """

    consensus_direction: str = "none"            # bullish/bearish/neutral/none
    consensus_ratio: float = 0.0
    consensus_experts: List[Dict] = field(default_factory=list)
    divergent_experts: List[Dict] = field(default_factory=list)
    neutral_experts: List[Dict] = field(default_factory=list)
    divergence_type: str = "none"                # none / mild / strong / no_consensus
    analysis: str = ""


@dataclass
class DirectionAnalysis:
    """方向判定分解 —— 展示从信号到方向的量化推理过程。

    Attributes:
        bullish_score: 加权看多总分
        bearish_score: 加权看空总分
        total_score: 总分（看多 + 看空）
        bullish_ratio: 看多占比
        bearish_ratio: 看空占比
        determined_direction: 判定方向（bullish/bearish/neutral）
        determination_rule: 判定规则说明
        count_bonus: 信号数量奖励
        base_confidence: 基础置信度
        final_confidence: 最终综合置信度
    """

    bullish_score: float = 0.0
    bearish_score: float = 0.0
    total_score: float = 0.0
    bullish_ratio: float = 0.0
    bearish_ratio: float = 0.0
    determined_direction: str = "neutral"
    determination_rule: str = ""
    count_bonus: float = 0.0
    base_confidence: float = 0.0
    final_confidence: float = 0.0


@dataclass
class RiskAnalysis:
    """风险分析 —— 按类别区分阻塞性、信息性和场景风险。

    Attributes:
        blocking_risks: 阻塞性风险（导致 hold 决策）
        informational_risks: 信息性风险（供参考，不阻塞交易）
        scenario_risks: 场景固有风险（由场景对象提供）
        summary: 风险评估总结
        has_blocking: 是否存在阻塞性风险
    """

    blocking_risks: List[str] = field(default_factory=list)
    informational_risks: List[str] = field(default_factory=list)
    scenario_risks: List[str] = field(default_factory=list)
    summary: str = ""
    has_blocking: bool = False


@dataclass
class StandardizedReasoningChain:
    """标准化推理链 —— 从输入到决策的完整白箱链路。

    结构化的推理链包含六大模块：
      1. scenario_info     场景信息（名称、描述、覆盖阈值等）
      2. consensus          共识/分歧分析
      3. contributions      专家贡献追踪（每专家一行）
      4. direction_analysis 方向判定分解（看多分/看空分/占比/规则）
      5. position_logic     仓位计算逻辑（公式/系数/上限/应用）
      6. risk_analysis      风险分析（阻塞性/信息性/场景风险分类）
      7. final_decision     最终决策摘要

    此结构可直接序列化为 JSON 供外部系统（PDF 生成器等）消费，
    也可通过 format_for_display() 生成人类可读的文本展示。
    """

    # 1. 场景信息
    scenario_info: Dict[str, Any] = field(default_factory=dict)

    # 2. 共识/分歧
    consensus: Optional[ConsensusAnalysis] = None

    # 3. 专家贡献追踪
    contributions: List[ExpertContribution] = field(default_factory=list)

    # 4. 方向判定
    direction_analysis: Optional[DirectionAnalysis] = None

    # 5. 仓位逻辑
    position_logic: Dict[str, Any] = field(default_factory=dict)

    # 6. 风险分析
    risk_analysis: Optional[RiskAnalysis] = None

    # 7. 最终决策
    final_decision: Dict[str, Any] = field(default_factory=dict)

    # 8. 不确定性追踪
    uncertainties: List[str] = field(default_factory=list)

    # 契约标注
    skill_contract: str = "skills/orchestrator/arbitration-methodology/SKILL.md"

    # 元数据
    generated_at: str = ""
    signal_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典（可直接 JSON 化）。"""
        return {
            "scenario_info": self.scenario_info,
            "consensus": {
                "consensus_direction": self.consensus.consensus_direction,
                "consensus_ratio": self.consensus.consensus_ratio,
                "consensus_experts": self.consensus.consensus_experts,
                "divergent_experts": self.consensus.divergent_experts,
                "neutral_experts": self.consensus.neutral_experts,
                "divergence_type": self.consensus.divergence_type,
                "analysis": self.consensus.analysis,
            } if self.consensus else None,
            "contributions": [
                {
                    "source": c.source,
                    "signal_type": c.signal_type,
                    "direction": c.direction,
                    "confidence": c.confidence,
                    "signal_weight": c.signal_weight,
                    "expert_weight": c.expert_weight,
                    "effective_weight": round(c.effective_weight, 4),
                    "contribution": round(c.contribution, 4),
                    "contribution_ratio": round(c.contribution_ratio, 4),
                    "is_top_contributor": c.is_top_contributor,
                    "reasoning": c.reasoning,
                }
                for c in self.contributions
            ],
            "direction_analysis": {
                "bullish_score": round(self.direction_analysis.bullish_score, 4),
                "bearish_score": round(self.direction_analysis.bearish_score, 4),
                "total_score": round(self.direction_analysis.total_score, 4),
                "bullish_ratio": round(self.direction_analysis.bullish_ratio, 4),
                "bearish_ratio": round(self.direction_analysis.bearish_ratio, 4),
                "determined_direction": self.direction_analysis.determined_direction,
                "determination_rule": self.direction_analysis.determination_rule,
                "count_bonus": round(self.direction_analysis.count_bonus, 4),
                "base_confidence": round(self.direction_analysis.base_confidence, 4),
                "final_confidence": round(self.direction_analysis.final_confidence, 4),
            } if self.direction_analysis else None,
            "position_logic": self.position_logic,
            "risk_analysis": {
                "blocking_risks": self.risk_analysis.blocking_risks,
                "informational_risks": self.risk_analysis.informational_risks,
                "scenario_risks": self.risk_analysis.scenario_risks,
                "summary": self.risk_analysis.summary,
                "has_blocking": self.risk_analysis.has_blocking,
            } if self.risk_analysis else None,
            "final_decision": self.final_decision,
            "uncertainties": self.uncertainties,
            "skill_contract": self.skill_contract,
            "meta": {
                "generated_at": self.generated_at,
                "signal_count": self.signal_count,
            },
        }

    def to_json(self, indent: int = 2) -> str:
        """序列化为 JSON 字符串。"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


# ============================================================================
# 构建函数
# ============================================================================


def build_standardized_chain(
    signals: List[Signal],
    scenario,
    direction: str,
    confidence: float,
    position_ratio: float,
    position_formula: str,
    risks: List[str],
    weight_reasons: Optional[Dict[str, Tuple[float, str]]] = None,
    execution_trace: Optional[Dict[str, Any]] = None,
    bullish_score: float = 0.0,
    bearish_score: float = 0.0,
    uncertainties: Optional[List[str]] = None,
) -> StandardizedReasoningChain:
    """从仲裁数据构建完整的标准化推理链。

    Args:
        signals: 参与仲裁的信号列表
        scenario: 场景对象（ScenarioProfile 子类实例）
        direction: 最终判定方向
        confidence: 最终综合置信度
        position_ratio: 建议仓位比例
        position_formula: 仓位计算公式说明
        risks: 风险提示列表
        weight_reasons: {expert_type: (权重值, 理由)}
        execution_trace: 编排执行追踪
        bullish_score: 加权看多得分
        bearish_score: 加权看空得分

    Returns:
        完整的 StandardizedReasoningChain 对象
    """
    from datetime import datetime

    chain = StandardizedReasoningChain()
    chain.generated_at = datetime.now().isoformat()
    chain.signal_count = len(signals)
    weight_reasons = weight_reasons or {}

    # ---- 1. 场景信息 ----
    chain.scenario_info = _build_scenario_info(scenario)

    # ---- 2. 共识/分歧分析 ----
    chain.consensus = _build_consensus_analysis(signals, direction)

    # ---- 3. 专家贡献追踪 ----
    chain.contributions = _build_contributions(signals, weight_reasons, direction)

    # ---- 4. 方向判定 ----
    chain.direction_analysis = _build_direction_analysis(
        bullish_score, bearish_score, direction, confidence, len(signals)
    )

    # ---- 5. 仓位逻辑 ----
    chain.position_logic = _build_position_logic(scenario, confidence, direction, position_ratio, position_formula)

    # ---- 6. 风险分析 ----
    chain.risk_analysis = _build_risk_analysis(risks, scenario)

    # ---- 7. 最终决策 ----
    chain.final_decision = _build_final_decision(
        direction, confidence, position_ratio, chain.consensus
    )

    # ---- 8. 不确定性追踪 + 契约标注 ----
    chain.uncertainties = list(uncertainties or [])

    return chain


# ============================================================================
# 各模块构建函数
# ============================================================================


def _build_scenario_info(scenario) -> Dict[str, Any]:
    """构建场景信息。"""
    return {
        "name": getattr(scenario, "name", "unknown"),
        "display_name": getattr(scenario, "display_name", "未知"),
        "description": getattr(scenario, "description", ""),
        "confidence_threshold": getattr(scenario, "confidence_threshold", None),
        "position_coefficient": getattr(scenario, "POSITION_COEFFICIENT", None),
        "position_cap": getattr(scenario, "POSITION_CAP", None),
    }


def _build_consensus_analysis(
    signals: List[Signal],
    final_direction: str,
) -> ConsensusAnalysis:
    """构建共识与分歧分析。

    规则：
      - 共识方向 = 信号数量最多的方向
      - 共识占比 ≥ 50% → 有共识
      - 两个方向各 ≥ 40% → 严重分歧
      - 最大方向 < 50% → 无共识
    """
    if not signals:
        return ConsensusAnalysis(
            consensus_direction="none",
            analysis="无信号，无法进行共识分析",
        )

    total = len(signals)
    bullish_signals = [s for s in signals if s.direction == "bullish"]
    bearish_signals = [s for s in signals if s.direction == "bearish"]
    neutral_signals = [s for s in signals if s.direction == "neutral"]

    n_bullish = len(bullish_signals)
    n_bearish = len(bearish_signals)
    n_neutral = len(neutral_signals)

    # 找出占比最大的方向
    direction_counts = {"bullish": n_bullish, "bearish": n_bearish, "neutral": n_neutral}
    consensus_dir = max(direction_counts, key=direction_counts.get)  # type: ignore
    consensus_n = direction_counts[consensus_dir]
    consensus_ratio = consensus_n / total if total > 0 else 0

    # 分歧判定
    bull_ratio = n_bullish / total if total > 0 else 0
    bear_ratio = n_bearish / total if total > 0 else 0

    if consensus_ratio >= 0.5:
        # 有明确共识
        if bull_ratio >= 0.4 and bear_ratio >= 0.4:
            divergence_type = "strong"
            analysis = (
                f"严重分歧：看多{n_bullish}个({bull_ratio:.0%})与看空{n_bearish}个({bear_ratio:.0%})"
                f"均占显著比例。虽然{consensus_dir}方向占多，但分歧不容忽视。"
            )
        elif (consensus_dir == "bullish" and n_bearish > 0) or (consensus_dir == "bearish" and n_bullish > 0):
            divergence_type = "mild"
            opponent_n = n_bearish if consensus_dir == "bullish" else n_bullish
            analysis = (
                f"{consensus_dir}方向形成共识（{consensus_n}/{total}，{consensus_ratio:.0%}），"
                f"有{opponent_n}个专家持相反意见。"
            )
        else:
            divergence_type = "none"
            analysis = (
                f"高度共识：所有方向性信号均一致（{consensus_dir}方向 {consensus_n}/{total}）。"
            )
    else:
        divergence_type = "no_consensus"
        analysis = (
            f"无明确共识：{consensus_dir}方向占比 {consensus_ratio:.0%} < 50%，"
            f"看多{n_bullish}/看空{n_bearish}/中性{n_neutral}。建议保持观望。"
        )

    # 构建专家列表
    def _expert_dict(s: Signal) -> Dict:
        return {
            "source": s.source,
            "signal_type": s.signal_type,
            "direction": s.direction,
            "confidence": s.confidence,
            "reasoning": s.reasoning[:120] if s.reasoning else "",
        }

    consensus_experts = [_expert_dict(s) for s in signals if s.direction == consensus_dir]
    # 持有异议 = 与共识方向相反（不包含中性）
    opponent_dir = "bearish" if consensus_dir == "bullish" else "bullish"
    divergent_experts = [_expert_dict(s) for s in signals if s.direction == opponent_dir]
    neutral_experts = [_expert_dict(s) for s in neutral_signals]

    return ConsensusAnalysis(
        consensus_direction=consensus_dir,
        consensus_ratio=round(consensus_ratio, 4),
        consensus_experts=consensus_experts,
        divergent_experts=divergent_experts,
        neutral_experts=neutral_experts,
        divergence_type=divergence_type,
        analysis=analysis,
    )


def _build_contributions(
    signals: List[Signal],
    weight_reasons: Dict[str, Tuple[float, str]],
    final_direction: str,
) -> List[ExpertContribution]:
    """构建专家贡献追踪列表。

    对每个信号计算：
      effective_weight = confidence × signal_weight × expert_weight
      contribution = effective_weight（同方向信号才有贡献）
      contribution_ratio = contribution / same_direction_total

    贡献占比仅在同方向信号之间计算。
    中性信号无贡献。
    """
    if not signals:
        return []

    contributions = []

    # 计算每个信号的 effective_weight
    for s in signals:
        expert_type = s.signal_type or "unknown"
        expert_weight, _ = weight_reasons.get(expert_type, (1.0, ""))
        effective = s.confidence * s.weight * expert_weight

        contributions.append({
            "signal": s,
            "expert_type": expert_type,
            "expert_weight": expert_weight,
            "effective_weight": effective,
        })

    # 计算看多和看空方向的总贡献
    bullish_total = sum(
        c["effective_weight"] for c in contributions
        if c["signal"].direction == "bullish"
    )
    bearish_total = sum(
        c["effective_weight"] for c in contributions
        if c["signal"].direction == "bearish"
    )

    # 找出看多/看空方向的最大贡献者
    bullish_contribs = [c for c in contributions if c["signal"].direction == "bullish"]
    bearish_contribs = [c for c in contributions if c["signal"].direction == "bearish"]

    max_bullish_idx = max(
        range(len(bullish_contribs)),
        key=lambda i: bullish_contribs[i]["effective_weight"],
    ) if bullish_contribs else None
    max_bearish_idx = max(
        range(len(bearish_contribs)),
        key=lambda i: bearish_contribs[i]["effective_weight"],
    ) if bearish_contribs else None

    # 标记最大贡献者
    for i, c in enumerate(bullish_contribs):
        if i == max_bullish_idx:
            c["is_top"] = True
    for i, c in enumerate(bearish_contribs):
        if i == max_bearish_idx:
            c["is_top"] = True

    # 构建 ExpertContribution 列表
    result = []
    for c in contributions:
        s = c["signal"]
        is_top = c.get("is_top", False)

        if s.direction == "bullish":
            contrib = c["effective_weight"]
            ratio = contrib / bullish_total if bullish_total > 0 else 0
        elif s.direction == "bearish":
            contrib = c["effective_weight"]
            ratio = contrib / bearish_total if bearish_total > 0 else 0
        else:
            contrib = 0.0
            ratio = 0.0

        result.append(ExpertContribution(
            source=s.source,
            signal_type=s.signal_type,
            direction=s.direction,
            confidence=s.confidence,
            signal_weight=s.weight,
            expert_weight=c["expert_weight"],
            effective_weight=round(c["effective_weight"], 4),
            contribution=round(contrib, 4),
            contribution_ratio=round(ratio, 4),
            is_top_contributor=is_top,
            reasoning=s.reasoning[:120] if s.reasoning else "",
        ))

    return result


def _build_direction_analysis(
    bullish_score: float,
    bearish_score: float,
    direction: str,
    confidence: float,
    signal_count: int,
) -> DirectionAnalysis:
    """构建方向判定分解。"""
    total = bullish_score + bearish_score
    bullish_ratio = bullish_score / total if total > 0 else 0
    bearish_ratio = bearish_score / total if total > 0 else 0

    # 回溯判定规则
    if bullish_ratio > 0.6:
        rule = f"看多占比 {bullish_ratio:.1%} > 60%，判定 bullish"
    elif bearish_ratio > 0.6:
        rule = f"看空占比 {bearish_ratio:.1%} > 60%，判定 bearish"
    else:
        rule = f"看多 {bullish_ratio:.1%} / 看空 {bearish_ratio:.1%} 均 ≤ 60%，判定 neutral"

    # 基础置信度
    if direction == "bullish":
        base_conf = bullish_score / (bullish_score + bearish_score + 0.01)
    elif direction == "bearish":
        base_conf = bearish_score / (bullish_score + bearish_score + 0.01)
    else:
        if bullish_score + bearish_score > 0:
            ratio_gap = abs(bullish_score - bearish_score) / (bullish_score + bearish_score)
            base_conf = ratio_gap * 0.5
        else:
            base_conf = 0.3

    count_bonus = min(signal_count * 0.02, 0.2)

    return DirectionAnalysis(
        bullish_score=round(bullish_score, 4),
        bearish_score=round(bearish_score, 4),
        total_score=round(total, 4),
        bullish_ratio=round(bullish_ratio, 4),
        bearish_ratio=round(bearish_ratio, 4),
        determined_direction=direction,
        determination_rule=rule,
        count_bonus=round(count_bonus, 4),
        base_confidence=round(min(base_conf, 1.0), 4),
        final_confidence=round(confidence, 4),
    )


def _build_position_logic(
    scenario,
    confidence: float,
    direction: str,
    position_ratio: float,
    position_formula: str,
) -> Dict[str, Any]:
    """构建仓位计算逻辑。"""
    return {
        "coefficient": getattr(scenario, "POSITION_COEFFICIENT", "unknown"),
        "cap": getattr(scenario, "POSITION_CAP", "unknown"),
        "formula": position_formula,
        "applied": {
            "confidence": round(confidence, 4),
            "direction": direction,
            "result_position": round(position_ratio, 4),
        },
        "note": "仓位由场景对象中的 position_formula 计算，不同场景有不同的系数和上限",
    }


def _build_risk_analysis(
    risks: List[str],
    scenario,
) -> RiskAnalysis:
    """构建风险分析，按类别分类。"""
    blocking = []
    informational = []
    scenario_risks = []

    for r in risks:
        if "🔒" in r:
            blocking.append(r)
        elif any(marker in r for marker in ["🔴", "⚠️"]):
            informational.append(r)
        else:
            # 无法分类的归入信息性
            informational.append(r)

    # 合并场景层面的风险
    scenario_risks = getattr(scenario, "get_scenario_risks", lambda: [])()

    # 生成总结
    if blocking:
        summary = f"存在 {len(blocking)} 个阻塞性风险，决策可能被 hold"
    elif informational:
        summary = f"存在 {len(informational)} 个信息性风险提示，供参考"
    else:
        summary = "无显著风险"

    if scenario_risks:
        summary += f"，含 {len(scenario_risks)} 个场景固有风险"

    return RiskAnalysis(
        blocking_risks=blocking,
        informational_risks=informational,
        scenario_risks=scenario_risks,
        summary=summary,
        has_blocking=len(blocking) > 0,
    )


def _build_final_decision(
    direction: str,
    confidence: float,
    position_ratio: float,
    consensus: Optional[ConsensusAnalysis],
) -> Dict[str, Any]:
    """构建最终决策摘要。"""
    direction_map = {"bullish": "看多", "bearish": "看空", "neutral": "中性"}
    confidence_level = "高" if confidence > 0.7 else "中" if confidence > 0.5 else "低"

    if direction == "bullish" and confidence > 0.5:
        action = "buy" if position_ratio > 0.2 else "hold"
    elif direction == "bearish" and confidence > 0.5:
        action = "sell"
    else:
        action = "wait"

    decision_summary = {
        "action": action,
        "direction": direction,
        "direction_display": direction_map.get(direction, "未知"),
        "confidence": round(confidence, 4),
        "confidence_level": confidence_level,
        "position_ratio": round(position_ratio, 4),
    }

    if consensus:
        decision_summary["consensus_quality"] = {
            "type": consensus.divergence_type,
            "ratio": consensus.consensus_ratio,
            "note": consensus.analysis,
        }

    return decision_summary


# ============================================================================
# 展示格式化
# ============================================================================


def format_standardized_chain(chain: StandardizedReasoningChain) -> str:
    """将标准化推理链格式化为可读的文本输出。

    用于控制台打印或日志输出。
    """
    lines = []
    sep = "─" * 64

    # ---- 场景信息 ----
    si = chain.scenario_info
    lines.append(f"【场景】{si.get('display_name', '未知')}")
    lines.append(f"  {si.get('description', '')}")
    if si.get("confidence_threshold") is not None:
        lines.append(f"  覆盖置信度阈值: {si['confidence_threshold']}")
    lines.append("")

    # ---- 共识/分歧 ----
    if chain.consensus:
        c = chain.consensus
        lines.append(f"【共识分析】")
        lines.append(f"  共识方向: {c.consensus_direction} ({c.consensus_ratio:.0%})")
        lines.append(f"  分歧类型: {c.divergence_type}")
        lines.append(f"  {c.analysis}")

        if c.consensus_experts:
            names = [e["signal_type"] for e in c.consensus_experts]
            lines.append(f"  共识专家组: {', '.join(names)}")
        if c.divergent_experts:
            names = [e["signal_type"] for e in c.divergent_experts]
            lines.append(f"  异议专家组: {', '.join(names)}")
        if c.neutral_experts:
            names = [e["signal_type"] for e in c.neutral_experts]
            lines.append(f"  中立专家组: {', '.join(names)}")
        lines.append("")

    # ---- 专家贡献追踪 ----
    if chain.contributions:
        lines.append(f"【权重贡献追踪】")
        lines.append(
            f"  {'专家':<8} {'方向':<6} {'置信':>5} {'场景权重':>7} "
            f"{'有效权重':>7} {'贡献':>7} {'占比':>6} {'备注'}"
        )
        lines.append(f"  {'─'*8} {'─'*6} {'─'*5} {'─'*7} {'─'*7} {'─'*7} {'─'*6} {'─'*12}")

        for c in chain.contributions:
            dir_emoji = {"bullish": "📈", "bearish": "📉", "neutral": "➡️"}.get(c.direction, "  ")
            notes = ""
            if c.is_top_contributor:
                notes = "★ 最大贡献者"
            elif c.direction == "neutral":
                notes = "未贡献方向分"
            elif c.expert_weight < 1.0:
                notes = f"降权({c.expert_weight})"
            elif c.expert_weight > 1.0:
                notes = f"提权({c.expert_weight})"

            contrib_str = f"{c.contribution:.3f}" if c.contribution > 0 else "—"
            ratio_str = f"{c.contribution_ratio:.0%}" if c.contribution_ratio > 0 else "—"

            lines.append(
                f"  {c.signal_type:<8} {dir_emoji:<6} {c.confidence:>4.0%} "
                f"{c.expert_weight:>7.2f} {c.effective_weight:>7.3f} "
                f"{contrib_str:>7} {ratio_str:>6} {notes}"
            )
        lines.append("")

    # ---- 方向判定 ----
    if chain.direction_analysis:
        da = chain.direction_analysis
        lines.append(f"【方向判定】")
        lines.append(f"  看多得分: {da.bullish_score:.3f}  |  看空得分: {da.bearish_score:.3f}")
        lines.append(f"  看多占比: {da.bullish_ratio:.1%}  |  看空占比: {da.bearish_ratio:.1%}")
        lines.append(f"  判定规则: {da.determination_rule}")
        lines.append(f"  基础置信度: {da.base_confidence:.1%} + 信号量奖励: {da.count_bonus:.1%}")
        lines.append(f"  → 最终置信度: {da.final_confidence:.1%}")
        lines.append("")

    # ---- 仓位逻辑 ----
    pl = chain.position_logic
    if pl:
        lines.append(f"【仓位计算】")
        lines.append(f"  系数: {pl.get('coefficient', '?')}  |  上限: {pl.get('cap', '?')}")
        lines.append(f"  公式: {pl.get('formula', '')}")
        lines.append(f"  → 建议仓位: {pl.get('applied', {}).get('result_position', 0):.0%}")
        lines.append("")

    # ---- 风险分析 ----
    if chain.risk_analysis:
        ra = chain.risk_analysis
        lines.append(f"【风险分析】")
        lines.append(f"  总结: {ra.summary}")
        if ra.blocking_risks:
            lines.append(f"  🔒 阻塞性风险 ({len(ra.blocking_risks)}):")
            for r in ra.blocking_risks:
                lines.append(f"    {r}")
        if ra.informational_risks:
            lines.append(f"  信息性风险 ({len(ra.informational_risks)}):")
            for r in ra.informational_risks:
                lines.append(f"    {r}")
        if ra.scenario_risks:
            lines.append(f"  场景风险 ({len(ra.scenario_risks)}):")
            for r in ra.scenario_risks:
                lines.append(f"    {r}")
        lines.append("")

    # ---- 最终决策 ----
    fd = chain.final_decision
    lines.append(f"【最终决策】")
    lines.append(f"  操作: {fd.get('action', '?')}")
    lines.append(f"  方向: {fd.get('direction_display', fd.get('direction', '?'))}")
    lines.append(f"  置信度: {fd.get('confidence', 0):.1%} ({fd.get('confidence_level', '?')})")
    lines.append(f"  仓位: {fd.get('position_ratio', 0):.0%}")
    lines.append("")

    # ---- 不确定性追踪 ----
    if chain.uncertainties:
        lines.append(f"【不确定性追踪】")
        for u in chain.uncertainties:
            lines.append(f"  🔍 {u}")
        lines.append("")

    # ---- 契约标注 ----
    lines.append(f"【输出契约】{chain.skill_contract}")

    return "\n".join(lines)
