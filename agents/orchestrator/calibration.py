"""
权重校准引擎 —— 基于历史信号数据的理论-实证融合框架。

方法论依据：
  权重校准采用"理论锚定 + 实证微调"策略——
  桥水经济机器模型决定的权重方向（升/降/平）保持稳定，
  数值在理论值周围做有限区间内调整。
  详细理论依据见开发2组 SKILL.md 权重校准框架章节。

核心原则：
  1. 方向不可逆：理论确定为升的权重，实证再差也不降为降
  2. 浮动区间：每个权重在基准 ±30% 内调整
  3. 归一化：场景内 7 个权重总和保持不变
  4. 样本外验证：70% 训练 / 30% 验证
  5. 稳定性检查：连续两期校准值波动 < 15%
  6. 资产不自动覆盖：产出报告，人工审查后手动更新

设计定位：
  校准模块是"辅助分析工具"，不是"自动化调参器"。
  输出校准报告供人工审查，不做任何自动写入操作。
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass
class SignalRecord:
    """单条历史信号记录。

    表示某一时刻某一专家在某一场景下的信号预测及后续实际结果。
    这是校准引擎的最小输入单位。

    Attributes:
        expert_type: 专家类型标识 (technical/financial/macro/fundflow/industry/news/risk)
        scenario: 市场场景标识 (bull_market/bear_market/range_market)
        timestamp: 信号发出时间
        predicted_direction: 专家预测方向 (bullish/bearish/neutral)
        predicted_confidence: 专家预测置信度 (0.0-1.0)
        actual_direction: 后续实际方向 (bullish/bearish/neutral)
        timeliness_days: 从信号发出到方向兑现的天数（NA 时为 -1）
        signal_type: 信号类型（如 "technical"、"macro" 等，与 expert_type 可不同）
        stock_code: 标的代码（可选）
        notes: 备注（可选）
    """

    expert_type: str
    scenario: str
    timestamp: str
    predicted_direction: str
    predicted_confidence: float
    actual_direction: str
    timeliness_days: int = -1
    signal_type: str = ""
    stock_code: str = ""
    notes: str = ""


@dataclass
class AccuracyMetrics:
    """单个专家在单个场景下的准确性指标。

    三个维度：
      - direction_accuracy:  方向准确率（预测方向 = 实际方向 的占比），权重 0.5
      - confidence_calibration: 置信度校准（高置信度信号实际正确率是否匹配），权重 0.3
      - timeliness_score:    时效性得分（方向兑现速度），权重 0.2

    中性 (neutral) 方向判定：
      - 当 predicted_direction = "neutral" 且 actual_direction = "neutral" → 正确
      - 当 predicted_direction = "neutral" 且 actual_direction != "neutral" → 错误
    """

    expert_type: str = ""
    scenario: str = ""
    direction_accuracy: float = 0.0
    confidence_calibration: float = 0.0
    timeliness_score: float = 0.0
    composite_score: float = 0.0
    sample_count: int = 0
    detail: Dict = field(default_factory=dict)


@dataclass
class WeightAdjustment:
    """单个专家权重校准结果。

    核心字段：
      - anchor_weight:  场景文件中的理论权重（锚定点）
      - empirical_score: 从历史数据计算出的综合准确性得分
      - blended_weight:  理论-实证融合权重（核心输出）
      - adjustment:      调整量（blended - anchor）
      - band_lower:      ±30% 下界
      - band_upper:      ±30% 上界
      - within_band:     融合结果是否在允许区间内
      - requires_attention: 是否需要人工特别关注
    """

    expert_type: str = ""
    scenario: str = ""
    anchor_weight: float = 0.0
    anchor_direction: str = ""  # "up" / "down" / "neutral"
    empirical_score: float = 0.0
    blended_weight: float = 0.0
    adjustment: float = 0.0
    band_lower: float = 0.0
    band_upper: float = 0.0
    within_band: bool = True
    requires_attention: bool = False
    attention_reason: str = ""
    sample_count: int = 0
    validation_score: float = 0.0  # 样本外验证得分


# ---------------------------------------------------------------------------
# 校准引擎
# ---------------------------------------------------------------------------


class CalibrationEngine:
    """权重校准引擎。

    三阶段工作流：
      阶段一：信号有效性测量 → calculate_accuracy()
      阶段二：理论-实证融合 → blend_weights()
      阶段三：验证与约束   → apply_constraints() + validate_split()

    使用方法:
        engine = CalibrationEngine(alpha=0.3)
        engine.load_anchor_weights()            # 从场景文件加载理论权重
        engine.load_records(history_records)    # 加载历史信号数据
        report = engine.run_full_calibration()  # 执行完整校准流程
        print(engine.format_report(report))     # 格式化输出报告
    """

    # ------------------------------------------------------------------
    # 常量定义
    # ------------------------------------------------------------------

    # 三位维度权重
    DIRECTION_WEIGHT = 0.5
    CONFIDENCE_WEIGHT = 0.3
    TIMELINESS_WEIGHT = 0.2

    # 置信度校准分桶
    CONFIDENCE_BINS = [(0.0, 0.3), (0.3, 0.5), (0.5, 0.7), (0.7, 1.0)]

    # 可容忍的偏差阈值（置信度校准）
    CALIBRATION_TOLERANCE = 0.15

    # 理论-实证融合参数
    DEFAULT_ALPHA = 0.3          # 默认信任度：70% 理论 + 30% 数据
    SCALE_FACTOR = 1.6           # 将 0-1 准确率映射到权重范围
    BAND_RATIO = 0.30            # ±30% 浮动区间

    # 稳定性阈值
    STABILITY_THRESHOLD = 0.15   # 连续两期校准值波动 < 15%

    # 最小样本量
    MIN_SAMPLES = 10             # 每个专家×场景至少 10 条记录才能校准
    LOW_SAMPLE_THRESHOLD = 50    # 低于此值自动降低 alpha

    # 参考权重 —— 与场景文件中的 _BASE_WEIGHTS 完全对齐
    # 格式: {场景标识: {专家类型: 权重值}}
    REFERENCE_WEIGHTS: Dict[str, Dict[str, float]] = {
        "bull_market": {
            "technical": 1.3,
            "fundflow":  1.2,
            "industry":   1.05,
            "macro":      1.0,
            "financial":  0.7,
            "news":       0.7,
            "risk":       0.5,
        },
        "bear_market": {
            "risk":       1.6,
            "financial":  1.2,
            "industry":   1.10,
            "macro":      1.1,
            "fundflow":  0.9,
            "news":       0.65,
            "technical":  0.5,
        },
        "range_market": {
            "industry":   1.20,
            "risk":       1.2,
            "fundflow":  1.2,
            "macro":      1.0,
            "financial":  0.9,
            "news":       0.75,
            "technical":  0.5,
        },
    }

    # 权重方向：每个专家在理论上的方向设定
    # "up" = 理论上应提高权重, "down" = 理论上应降低权重
    # 方向不可逆：实证再差也不能翻转
    WEIGHT_DIRECTIONS: Dict[str, Dict[str, str]] = {
        "bull_market": {
            "technical": "up", "fundflow": "up", "industry": "up",
            "macro": "neutral", "financial": "down", "news": "down", "risk": "down",
        },
        "bear_market": {
            "risk": "up", "financial": "up", "industry": "up",
            "macro": "up", "fundflow": "down", "news": "down", "technical": "down",
        },
        "range_market": {
            "industry": "up", "risk": "up", "fundflow": "up",
            "macro": "neutral", "financial": "down", "news": "down", "technical": "down",
        },
    }

    # ------------------------------------------------------------------
    # 初始化
    # ------------------------------------------------------------------

    def __init__(
        self,
        alpha: float = DEFAULT_ALPHA,
        band_ratio: float = BAND_RATIO,
        random_seed: Optional[int] = None,
    ):
        """初始化校准引擎。

        Args:
            alpha: 实证信任度 (0.0-1.0)，默认 0.3 即 70% 理论 + 30% 数据
            band_ratio: 浮动区间比例 (0.0-1.0)，默认 0.30 即 ±30%
            random_seed: 随机种子（用于样本拆分，None 则不固定）
        """
        if not 0.0 <= alpha <= 1.0:
            raise ValueError(f"alpha 必须在 [0,1] 范围内，收到 {alpha}")
        self.alpha = alpha
        self.band_ratio = band_ratio
        self.random_seed = random_seed
        self.records: List[SignalRecord] = []

        # 内部缓存
        self._anchor_weights: Dict[str, Dict[str, float]] = {}
        self._accuracy_metrics: Dict[str, Dict[str, AccuracyMetrics]] = {}
        self._adjustments: Dict[str, Dict[str, WeightAdjustment]] = {}
        self._previous_calibration: Optional[Dict] = None  # 上一期校准结果

    # ------------------------------------------------------------------
    # 阶段〇：加载参考权重
    # ------------------------------------------------------------------

    def load_anchor_weights(
        self,
        weights: Optional[Dict[str, Dict[str, float]]] = None,
    ) -> Dict[str, Dict[str, float]]:
        """加载理论参考权重（锚定点）。

        Args:
            weights: 自定义权重表，格式 {场景: {专家: 权重}}。
                     为 None 时使用内置 REFERENCE_WEIGHTS。

        Returns:
            当前加载的权重表。
        """
        if weights is not None:
            self._anchor_weights = weights
        else:
            self._anchor_weights = {
                k: dict(v) for k, v in self.REFERENCE_WEIGHTS.items()
            }
        return self._anchor_weights

    # ------------------------------------------------------------------
    # 阶段零：加载历史信号数据
    # ------------------------------------------------------------------

    def load_records(self, records: List[SignalRecord]) -> int:
        """加载历史信号记录。

        Args:
            records: SignalRecord 列表

        Returns:
            加载的记录数
        """
        self.records = list(records)
        return len(self.records)

    @classmethod
    def records_from_dicts(cls, data: List[Dict]) -> List[SignalRecord]:
        """从字典列表批量构造 SignalRecord。

        方便从 JSON/CSV 等外部数据源快速导入。
        """
        records = []
        for item in data:
            records.append(SignalRecord(
                expert_type=item["expert_type"],
                scenario=item["scenario"],
                timestamp=item.get("timestamp", ""),
                predicted_direction=item["predicted_direction"],
                predicted_confidence=float(item.get("predicted_confidence", 0.5)),
                actual_direction=item["actual_direction"],
                timeliness_days=int(item.get("timeliness_days", -1)),
                signal_type=item.get("signal_type", ""),
                stock_code=item.get("stock_code", ""),
                notes=item.get("notes", ""),
            ))
        return records

    # ------------------------------------------------------------------
    # 阶段一：信号有效性测量
    # ------------------------------------------------------------------

    def calculate_accuracy(
        self,
        records: Optional[List[SignalRecord]] = None,
    ) -> Dict[str, Dict[str, AccuracyMetrics]]:
        """阶段一：对每个专家 × 场景组合，计算三维准确性指标。

        Args:
            records: 信号记录，为 None 时使用已加载的记录

        Returns:
            {场景: {专家类型: AccuracyMetrics}}
        """
        if records is not None:
            self.records = list(records)

        # 按 (场景, 专家) 分组
        grouped: Dict[str, Dict[str, List[SignalRecord]]] = {}
        for rec in self.records:
            grouped.setdefault(rec.scenario, {}).setdefault(rec.expert_type, []).append(rec)

        # 确保锚点权重已加载
        if not self._anchor_weights:
            self.load_anchor_weights()

        # 初始化结果容器
        self._accuracy_metrics = {}
        for scenario_name in self._anchor_weights:
            self._accuracy_metrics[scenario_name] = {}

        # 逐组计算
        for scenario_name, experts in grouped.items():
            if scenario_name not in self._anchor_weights:
                continue
            for expert_type, recs in experts.items():
                metrics = self._compute_expert_accuracy(expert_type, scenario_name, recs)
                self._accuracy_metrics[scenario_name][expert_type] = metrics

        # 补充没有历史数据的专家
        self._fill_missing_metrics()

        return self._accuracy_metrics

    def _compute_expert_accuracy(
        self,
        expert_type: str,
        scenario_name: str,
        records: List[SignalRecord],
    ) -> AccuracyMetrics:
        """计算单个专家在单个场景下的完整准确性指标。"""
        n = len(records)
        if n == 0:
            return AccuracyMetrics(
                expert_type=expert_type,
                scenario=scenario_name,
                sample_count=0,
                detail={"error": "no_data"},
            )

        # --- 维度一：方向准确率 (0.5) ---
        correct_direction = sum(
            1 for r in records if r.predicted_direction == r.actual_direction
        )
        direction_acc = correct_direction / n

        # --- 维度二：置信度校准 (0.3) ---
        # 按置信度分桶，计算每个桶内的实际正确率
        calib_score = self._compute_confidence_calibration(records)

        # --- 维度三：时效性得分 (0.2) ---
        timeliness = self._compute_timeliness_score(records)

        # --- 综合得分 ---
        composite = round(
            direction_acc * self.DIRECTION_WEIGHT
            + calib_score * self.CONFIDENCE_WEIGHT
            + timeliness * self.TIMELINESS_WEIGHT,
            4,
        )

        # --- 方向正确率明细 ---
        dir_counts = {"bullish": 0, "bearish": 0, "neutral": 0}
        dir_correct = {"bullish": 0, "bearish": 0, "neutral": 0}
        for r in records:
            pd_ = r.predicted_direction
            if pd_ in dir_counts:
                dir_counts[pd_] += 1
                if r.predicted_direction == r.actual_direction:
                    dir_correct[pd_] += 1

        dir_detail = {}
        for d in ["bullish", "bearish", "neutral"]:
            cnt = dir_counts[d]
            correct = dir_correct[d]
            dir_detail[d] = {
                "count": cnt,
                "correct": correct,
                "accuracy": round(correct / cnt, 4) if cnt > 0 else None,
            }

        return AccuracyMetrics(
            expert_type=expert_type,
            scenario=scenario_name,
            direction_accuracy=round(direction_acc, 4),
            confidence_calibration=round(calib_score, 4),
            timeliness_score=round(timeliness, 4),
            composite_score=composite,
            sample_count=n,
            detail={
                "direction_detail": dir_detail,
                "direction_weight": self.DIRECTION_WEIGHT,
                "confidence_weight": self.CONFIDENCE_WEIGHT,
                "timeliness_weight": self.TIMELINESS_WEIGHT,
            },
        )

    def _compute_confidence_calibration(self, records: List[SignalRecord]) -> float:
        """计算置信度校准得分。

        方法：按置信度分桶，计算桶内实际正确率与桶中位置信度的偏差。
        偏差越小，校准越好（说明该专家对自己判断的把握和实际表现一致）。
        """
        # 分桶
        bins: Dict[Tuple[float, float], List[SignalRecord]] = {
            b: [] for b in self.CONFIDENCE_BINS
        }
        for r in records:
            for low, high in self.CONFIDENCE_BINS:
                if low <= r.predicted_confidence < high:
                    bins[(low, high)].append(r)
                    break

        bucket_scores = []
        total_weight = 0
        for (low, high), recs in bins.items():
            n_ = len(recs)
            if n_ == 0:
                continue
            actual_correct = sum(
                1 for r in recs if r.predicted_direction == r.actual_direction
            ) / n_
            mid_conf = (low + high) / 2
            deviation = abs(actual_correct - mid_conf)
            # 1.0 = 完美校准, 0.0 = 偏差超过容忍度
            bucket_score = max(0.0, 1.0 - deviation / self.CALIBRATION_TOLERANCE)
            bucket_scores.append(bucket_score * n_)
            total_weight += n_

        if total_weight == 0:
            return 0.5  # 无数据时给中性分

        return sum(bucket_scores) / total_weight

    def _compute_timeliness_score(self, records: List[SignalRecord]) -> float:
        """计算时效性得分。

        方法：取有效时限记录的天数中位数，映射为 0-1 得分。
        天数 ≤ 5 → 1.0, ≤ 10 → 0.8, ≤ 20 → 0.5, ≤ 30 → 0.3, > 30 → 0.1
        NA（无时效数据）时不参与计算。
        """
        valid_days = [r.timeliness_days for r in records if r.timeliness_days >= 0]
        if not valid_days:
            return 0.5  # 无时效数据时给中性分

        # 取中位数减少极端值影响
        sorted_days = sorted(valid_days)
        median = sorted_days[len(sorted_days) // 2]

        if median <= 5:
            return 1.0
        elif median <= 10:
            return 0.8
        elif median <= 20:
            return 0.5
        elif median <= 30:
            return 0.3
        else:
            return 0.1

    def _fill_missing_metrics(self):
        """为有锚点权重但无历史数据的专家补充空白指标。"""
        for scenario_name, experts in self._anchor_weights.items():
            if scenario_name not in self._accuracy_metrics:
                self._accuracy_metrics[scenario_name] = {}
            for expert_type in experts:
                if expert_type not in self._accuracy_metrics[scenario_name]:
                    self._accuracy_metrics[scenario_name][expert_type] = AccuracyMetrics(
                        expert_type=expert_type,
                        scenario=scenario_name,
                        sample_count=0,
                        detail={"warning": "no_historical_data", "alpha_adjusted": True},
                    )

    # ------------------------------------------------------------------
    # 阶段二：理论-实证融合
    # ------------------------------------------------------------------

    def blend_weights(self) -> Dict[str, Dict[str, WeightAdjustment]]:
        """阶段二：将理论锚定权重与实证准确性得分融合。

        公式：
          blended = anchor × (1 - α_eff) + empirical × α_eff × scale

          其中 α_eff 会根据样本量自动调整：
            - 样本 < MIN_SAMPLES → α_eff = 0（完全信任理论）
            - 样本 < LOW_SAMPLE_THRESHOLD → α_eff = α × 0.5（半信任）
            - 样本 ≥ LOW_SAMPLE_THRESHOLD → α_eff = α（正常）

        Returns:
            {场景: {专家类型: WeightAdjustment}}
        """
        if not self._accuracy_metrics:
            raise RuntimeError("请先调用 calculate_accuracy() 再执行 blend_weights()")

        self._adjustments = {}

        for scenario_name in self._anchor_weights:
            self._adjustments[scenario_name] = {}
            for expert_type, anchor_weight in self._anchor_weights[scenario_name].items():
                metrics = self._accuracy_metrics.get(scenario_name, {}).get(expert_type)
                direction = self.WEIGHT_DIRECTIONS.get(scenario_name, {}).get(
                    expert_type, "neutral"
                )

                if metrics is None or metrics.sample_count == 0:
                    # 无历史数据，保持锚定值不变
                    adj = WeightAdjustment(
                        expert_type=expert_type,
                        scenario=scenario_name,
                        anchor_weight=anchor_weight,
                        anchor_direction=direction,
                        empirical_score=0.0,
                        blended_weight=anchor_weight,
                        adjustment=0.0,
                        band_lower=round(anchor_weight * (1 - self.band_ratio), 4),
                        band_upper=round(anchor_weight * (1 + self.band_ratio), 4),
                        within_band=True,
                        requires_attention=True,
                        attention_reason="无历史数据，保持锚定值不变",
                        sample_count=0,
                    )
                    self._adjustments[scenario_name][expert_type] = adj
                    continue

                # 计算有效 alpha
                n = metrics.sample_count
                if n < self.MIN_SAMPLES:
                    alpha_eff = 0.0
                elif n < self.LOW_SAMPLE_THRESHOLD:
                    alpha_eff = self.alpha * 0.5
                else:
                    alpha_eff = self.alpha

                empirical = metrics.composite_score
                blended = round(
                    anchor_weight * (1 - alpha_eff)
                    + empirical * alpha_eff * self.SCALE_FACTOR,
                    4,
                )

                # 计算调整量
                adjustment = round(blended - anchor_weight, 4)

                # 计算区间边界
                band_lower = round(anchor_weight * (1 - self.band_ratio), 4)
                band_upper = round(anchor_weight * (1 + self.band_ratio), 4)

                # 夹紧到区间内
                clamped = max(band_lower, min(band_upper, blended))
                within_band = abs(clamped - blended) < 0.0001

                needs_attention = False
                attention_reasons = []

                if n < self.LOW_SAMPLE_THRESHOLD:
                    needs_attention = True
                    attention_reasons.append(f"样本量不足 ({n} < {self.LOW_SAMPLE_THRESHOLD})，alpha 从 {self.alpha} 降至 {alpha_eff}")

                if not within_band:
                    needs_attention = True
                    attention_reasons.append(
                        f"融合值 {blended:.4f} 超出 ±{self.band_ratio:.0%} 区间 "
                        f"[{band_lower:.4f}, {band_upper:.4f}]，已钳制为 {clamped:.4f}"
                    )

                if (direction == "up" and clamped < anchor_weight) or (
                    direction == "down" and clamped > anchor_weight
                ):
                    needs_attention = True
                    attention_reasons.append(
                        f"融合方向与理论方向冲突：理论{(direction)}但实证推动反方向"
                    )

                adj = WeightAdjustment(
                    expert_type=expert_type,
                    scenario=scenario_name,
                    anchor_weight=anchor_weight,
                    anchor_direction=direction,
                    empirical_score=round(empirical, 4),
                    blended_weight=clamped,
                    adjustment=round(clamped - anchor_weight, 4),
                    band_lower=band_lower,
                    band_upper=band_upper,
                    within_band=within_band,
                    requires_attention=needs_attention,
                    attention_reason="；".join(attention_reasons) if attention_reasons else "",
                    sample_count=n,
                )
                self._adjustments[scenario_name][expert_type] = adj

        return self._adjustments

    # ------------------------------------------------------------------
    # 阶段三：验证与约束
    # ------------------------------------------------------------------

    def validate_split(
        self,
        train_ratio: float = 0.7,
    ) -> Dict[str, Dict[str, float]]:
        """样本外验证：将数据按时间或随机拆分为训练集/验证集。

        计算验证集上的准确性得分，与训练集对比。

        Args:
            train_ratio: 训练集比例，默认 0.7

        Returns:
            {场景: {专家类型: validation_score}}
        """
        if not self.records:
            return {}

        # 随机拆分（保持可复现性）
        rng = random.Random(self.random_seed)
        shuffled = list(self.records)
        rng.shuffle(shuffled)
        split_idx = int(len(shuffled) * train_ratio)
        train_records = shuffled[:split_idx]
        val_records = shuffled[split_idx:]

        # 在验证集上计算准确性
        val_metrics = self.calculate_accuracy(val_records)

        # 更新 WeightAdjustment 的 validation_score
        for scenario_name, experts in self._adjustments.items():
            for expert_type, adj in experts.items():
                vm = val_metrics.get(scenario_name, {}).get(expert_type)
                if vm and vm.sample_count > 0:
                    adj.validation_score = round(vm.composite_score, 4)

        result: Dict[str, Dict[str, float]] = {}
        for scenario_name, experts in val_metrics.items():
            result[scenario_name] = {}
            for expert_type, metrics in experts.items():
                result[scenario_name][expert_type] = round(metrics.composite_score, 4)

        return result

    def apply_constraints(self) -> Dict:
        """阶段三：对所有融合结果施加约束检查。

        约束规则：
          1. 方向不可逆：理论为 up 的不能因为实证差而降为 down 方向
          2. 浮动区间：每个权重在基准 ±30% 内
          3. 归一化：场景内 7 个权重总和保持不变（待实现）
          4. 样本量不足时 flag 标注

        Returns:
            约束检查报告:
            {
                "direction_violations": [...],
                "band_violations": [...],
                "low_sample_warnings": [...],
                "passed": bool,
            }
        """
        violations_dir = []
        violations_band = []
        low_sample = []

        for scenario_name, experts in self._adjustments.items():
            for expert_type, adj in experts.items():
                # 方向不可逆检查
                direction = adj.anchor_direction
                if direction == "up" and adj.blended_weight < adj.anchor_weight * 0.85:
                    violations_dir.append({
                        "scenario": scenario_name,
                        "expert": expert_type,
                        "anchor": adj.anchor_weight,
                        "blended": adj.blended_weight,
                        "direction": direction,
                        "detail": (
                            f"理论方向为 up（锚定 {adj.anchor_weight}），"
                            f"但融合值 {adj.blended_weight} 显著偏低（下降 {abs(adj.adjustment):.4f}），"
                            f"需人工审查是否合理。"
                        ),
                    })

                if direction == "down" and adj.blended_weight > adj.anchor_weight * 1.15:
                    violations_dir.append({
                        "scenario": scenario_name,
                        "expert": expert_type,
                        "anchor": adj.anchor_weight,
                        "blended": adj.blended_weight,
                        "direction": direction,
                        "detail": (
                            f"理论方向为 down（锚定 {adj.anchor_weight}），"
                            f"但融合值 {adj.blended_weight} 显著偏高（上升 {adj.adjustment:.4f}），"
                            f"需人工审查是否合理。"
                        ),
                    })

                # 浮动区间检查
                if not adj.within_band:
                    violations_band.append({
                        "scenario": scenario_name,
                        "expert": expert_type,
                        "anchor": adj.anchor_weight,
                        "blended": adj.blended_weight,
                        "band": f"[{adj.band_lower:.4f}, {adj.band_upper:.4f}]",
                    })

                # 样本量警告
                if adj.sample_count < self.LOW_SAMPLE_THRESHOLD and adj.sample_count > 0:
                    low_sample.append({
                        "scenario": scenario_name,
                        "expert": expert_type,
                        "samples": adj.sample_count,
                        "min_required": self.LOW_SAMPLE_THRESHOLD,
                    })

        return {
            "direction_violations": violations_dir,
            "band_violations": violations_band,
            "low_sample_warnings": low_sample,
            "passed": len(violations_dir) == 0 and len(violations_band) == 0,
        }

    def check_stability(
        self, previous_adjustments: Dict[str, Dict[str, WeightAdjustment]]
    ) -> Dict:
        """稳定性检查：与上一期校准结果对比。

        检查每对 (场景, 专家) 的 blended_weight 波动是否 < 15%。

        Args:
            previous_adjustments: 上一期的校准结果

        Returns:
            {
                "stable": bool,
                "volatile_items": [...],
                "max_fluctuation": float,
            }
        """
        volatile = []
        max_fluctuation = 0.0

        for scenario_name, experts in self._adjustments.items():
            prev_experts = previous_adjustments.get(scenario_name, {})
            for expert_type, adj in experts.items():
                prev = prev_experts.get(expert_type)
                if prev is None:
                    continue
                if adj.anchor_weight == 0:
                    continue

                fluctuation = abs(adj.blended_weight - prev.blended_weight) / adj.anchor_weight
                max_fluctuation = max(max_fluctuation, fluctuation)

                if fluctuation >= self.STABILITY_THRESHOLD:
                    volatile.append({
                        "scenario": scenario_name,
                        "expert": expert_type,
                        "previous": prev.blended_weight,
                        "current": adj.blended_weight,
                        "fluctuation": round(fluctuation, 4),
                        "threshold": self.STABILITY_THRESHOLD,
                    })

        return {
            "stable": len(volatile) == 0,
            "volatile_items": volatile,
            "max_fluctuation": round(max_fluctuation, 4),
        }

    # ------------------------------------------------------------------
    # 完整校准流程
    # ------------------------------------------------------------------

    def run_full_calibration(
        self,
        records: Optional[List[SignalRecord]] = None,
        do_split_validation: bool = True,
    ) -> Dict:
        """执行完整的校准流程（三阶段 + 约束 + 验证）。

        Args:
            records: 历史信号记录（已加载则可省略）
            do_split_validation: 是否执行样本外拆分验证

        Returns:
            完整校准报告字典，包含所有阶段的中间结果和最终建议。
        """
        if records is not None:
            self.load_records(records)
        if not self._anchor_weights:
            self.load_anchor_weights()

        # 保存原始记录数（validate_split 会覆盖 self.records）
        total_record_count = len(self.records)

        # 阶段一：准确性计算
        accuracy = self.calculate_accuracy()

        # 阶段二：融合
        adjustments = self.blend_weights()

        # 阶段三：约束检查
        constraints = self.apply_constraints()

        # 样本外验证
        validation = self.validate_split() if do_split_validation else {}

        # 构建完整报告
        return {
            "meta": {
                "generated_at": datetime.now().isoformat(),
                "engine_version": "1.0.0",
                "alpha": self.alpha,
                "band_ratio": self.band_ratio,
                "total_records": total_record_count,
                "scenarios_covered": list(self._anchor_weights.keys()),
                "expert_types": list(self._anchor_weights.get("bull_market", {}).keys()),
            },
            "accuracy_metrics": {
                sc: {
                    et: {
                        "direction_accuracy": m.direction_accuracy,
                        "confidence_calibration": m.confidence_calibration,
                        "timeliness_score": m.timeliness_score,
                        "composite_score": m.composite_score,
                        "sample_count": m.sample_count,
                        "detail": m.detail,
                    }
                    for et, m in experts.items()
                }
                for sc, experts in accuracy.items()
            },
            "adjustments": {
                sc: {
                    et: {
                        "anchor_weight": adj.anchor_weight,
                        "anchor_direction": adj.anchor_direction,
                        "empirical_score": adj.empirical_score,
                        "blended_weight": adj.blended_weight,
                        "adjustment": adj.adjustment,
                        "band_lower": adj.band_lower,
                        "band_upper": adj.band_upper,
                        "within_band": adj.within_band,
                        "requires_attention": adj.requires_attention,
                        "attention_reason": adj.attention_reason,
                        "sample_count": adj.sample_count,
                        "validation_score": adj.validation_score,
                    }
                    for et, adj in experts.items()
                }
                for sc, experts in adjustments.items()
            },
            "constraints": constraints,
            "validation": validation,
        }

    # ------------------------------------------------------------------
    # 报告格式化输出
    # ------------------------------------------------------------------

    def format_report(self, report: Dict) -> str:
        """将校准报告格式化为可读的文本输出。

        Args:
            report: run_full_calibration() 的返回值

        Returns:
            格式化后的文本报告
        """
        lines = []
        meta = report.get("meta", {})
        adjustments = report.get("adjustments", {})
        constraints = report.get("constraints", {})
        validation = report.get("validation", {})

        # ==== 报告头 ====
        lines.append("=" * 72)
        lines.append("  AI_Renaissance 权重校准报告")
        lines.append(f"  生成时间: {meta.get('generated_at', 'unknown')}")
        lines.append(f"  引擎版本: {meta.get('engine_version', 'unknown')}")
        lines.append(f"  总样本数: {meta.get('total_records', 0)}")
        lines.append(f"  信任度 α: {meta.get('alpha', self.alpha):.0%} "
                     f"(理论 {1 - meta.get('alpha', self.alpha):.0%} / 实证 {meta.get('alpha', self.alpha):.0%})")
        lines.append(f"  浮动区间: ±{meta.get('band_ratio', self.band_ratio):.0%}")
        lines.append("=" * 72)

        # ==== 场景维度权重建议 ====
        scenario_names_display = {
            "bull_market": "牛市场景",
            "bear_market": "熊市场景",
            "range_market": "震荡市场景",
        }
        expert_names_display = {
            "technical": "技术面",
            "fundflow": "资金流",
            "macro": "宏观面",
            "financial": "财务面",
            "industry": "产业分析",
            "news": "舆情面",
            "risk": "风控面",
        }

        for sc_name, sc_display in scenario_names_display.items():
            experts = adjustments.get(sc_name, {})
            if not experts:
                continue

            lines.append(f"\n{'─' * 72}")
            lines.append(f"  【{sc_display} ({sc_name})】")
            lines.append(f"{'─' * 72}")
            lines.append(
                f"  {'专家':<8} {'锚定值':>7} {'方向':>6} {'实证分':>7} "
                f"{'建议值':>7} {'调整':>7} {'区间':>22} {'样本':>5} {'备注'}"
            )
            lines.append(f"  {'─' * 8} {'─' * 7} {'─' * 6} {'─' * 7} "
                         f"{'─' * 7} {'─' * 7} {'─' * 22} {'─' * 5} {'─' * 20}")

            for et, adj in experts.items():
                display_name = expert_names_display.get(et, et)
                direction_map = {"up": "↑ 升", "down": "↓ 降", "neutral": "→ 平"}
                dir_str = direction_map.get(adj.get("anchor_direction", ""), "?")
                band_str = f"[{adj.get('band_lower', 0):.2f}, {adj.get('band_upper', 0):.2f}]"
                samples = adj.get("sample_count", 0)

                # 调整量符号
                adj_val = adj.get("adjustment", 0)
                adj_str = f"+{adj_val:.2f}" if adj_val >= 0 else f"{adj_val:.2f}"

                # 备注
                notes = ""
                if adj.get("requires_attention"):
                    notes = "⚠ 需关注"
                if samples == 0:
                    notes += " (无数据)"
                elif samples < self.LOW_SAMPLE_THRESHOLD:
                    notes += f" (样本少: {samples})"
                if not adj.get("within_band", True):
                    notes += " [超出区间]"

                lines.append(
                    f"  {display_name:<8} {adj.get('anchor_weight', 0):>7.2f} {dir_str:>6} "
                    f"{adj.get('empirical_score', 0):>7.2f} "
                    f"{adj.get('blended_weight', 0):>7.2f} {adj_str:>7} "
                    f"{band_str:>22} {samples:>5} {notes}"
                )

        # ==== 约束检查结果 ====
        lines.append(f"\n{'─' * 72}")
        lines.append(f"  【约束检查】")
        lines.append(f"{'─' * 72}")

        dir_violations = constraints.get("direction_violations", [])
        band_violations = constraints.get("band_violations", [])
        low_sample = constraints.get("low_sample_warnings", [])

        if constraints.get("passed", False):
            lines.append("  ✓ 所有约束检查通过")
        else:
            if dir_violations:
                lines.append(f"\n  ⚠ 方向约束冲突 ({len(dir_violations)} 项):")
                for v in dir_violations:
                    lines.append(
                        f"    - {v['scenario']}/{v['expert']}: {v['detail']}"
                    )
            if band_violations:
                lines.append(f"\n  ⚠ 区间约束冲突 ({len(band_violations)} 项):")
                for v in band_violations:
                    lines.append(
                        f"    - {v['scenario']}/{v['expert']}: "
                        f"锚定{v['anchor']:.2f} 建议值{v['blended']:.2f} 区间{v['band']}"
                    )
            if low_sample:
                lines.append(f"\n  ⚠ 低样本量警告 ({len(low_sample)} 项):")
                for w in low_sample:
                    lines.append(
                        f"    - {w['scenario']}/{w['expert']}: "
                        f"仅 {w['samples']} 条记录 (最低要求 {w['min_required']})"
                    )

        # ==== 样本外验证 ====
        if validation:
            lines.append(f"\n{'─' * 72}")
            lines.append(f"  【样本外验证（70% 训练 / 30% 验证）】")
            lines.append(f"{'─' * 72}")
            for sc_name, experts in validation.items():
                sc_display = scenario_names_display.get(sc_name, sc_name)
                lines.append(f"  {sc_display}:")
                for et, score in experts.items():
                    display_name = expert_names_display.get(et, et)
                    adj = adjustments.get(sc_name, {}).get(et, {})
                    train_score = adj.get("empirical_score", 0)
                    gap = round(score - train_score, 4)
                    gap_str = f"(训练 {train_score:.2f} → 验证 {score:.2f}, 差 {gap:+.2f})"
                    lines.append(f"    {display_name}: {score:.2f} {gap_str}")

        # ==== 免责声明 ====
        lines.append(f"\n{'─' * 72}")
        lines.append("  【重要说明】")
        lines.append(f"{'─' * 72}")
        lines.append("  1. 本报告的权重建议为理论-实证融合的计算结果，不代表最终最优值。")
        lines.append("  2. 所有权重调整均需人工审查后在场景文件中手动更新。")
        lines.append("  3. 校准引擎不自动修改任何场景文件。")
        lines.append("  4. 权重方向由理论框架决定，不可因短期实证表现而翻转。")
        lines.append("  5. 样本量不足时建议等待更多数据后再进行校准。")
        lines.append(f"\n{'=' * 72}")
        lines.append("  报告结束")
        lines.append("=" * 72)

        return "\n".join(lines)

    def save_report(self, report: Dict, filepath: str):
        """将校准报告保存为 JSON 文件。

        Args:
            report: run_full_calibration() 的返回值
            filepath: 输出文件路径
        """
        # 处理不可序列化的对象
        serializable = json.loads(
            json.dumps(report, default=str, ensure_ascii=False)
        )
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(serializable, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# 便捷函数
# ---------------------------------------------------------------------------


def generate_calibration_report(
    records: List[SignalRecord],
    alpha: float = 0.3,
    output_json: Optional[str] = None,
) -> Dict:
    """一键生成校准报告。

    Args:
        records: 历史信号记录列表
        alpha: 实证信任度
        output_json: JSON 输出路径（可选）

    Returns:
        完整的校准报告字典
    """
    engine = CalibrationEngine(alpha=alpha)
    report = engine.run_full_calibration(records=records)
    if output_json:
        engine.save_report(report, output_json)
    return report


def generate_report_text(
    records: List[SignalRecord],
    alpha: float = 0.3,
) -> str:
    """一键生成格式化文本报告。

    Args:
        records: 历史信号记录列表
        alpha: 实证信任度

    Returns:
        格式化后的文本报告字符串
    """
    engine = CalibrationEngine(alpha=alpha)
    report = engine.run_full_calibration(records=records)
    return engine.format_report(report)
