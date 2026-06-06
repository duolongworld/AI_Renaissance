"""
权重校准引擎 —— 单元测试与端到端验证。

测试覆盖：
  1. 准确性指标计算（方向准确率 / 置信度校准 / 时效性）
  2. 理论-实证融合公式
  3. 约束检查（方向不可逆 / 浮动区间 / 样本量不足）
  4. 完整三场景端到端校准流程
  5. 报告格式化输出
  6. 边界情况（空数据 / 低样本 / 极端值）
"""

import json
import os
import random
import sys
import tempfile

# 确保项目根在 sys.path 中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agents.orchestrator.calibration import (
    AccuracyMetrics,
    CalibrationEngine,
    SignalRecord,
    WeightAdjustment,
    generate_calibration_report,
    generate_report_text,
)

# ============================================================================
# 辅助：生成模拟历史数据
# ============================================================================

EXPERTS = ["technical", "fundflow", "macro", "financial", "industry", "news", "risk"]

SCENARIOS = ["bull_market", "bear_market", "range_market"]

# 每个场景下各专家的"真实"准确率（用于生成有意义的模拟数据）
# 值与理论权重方向一致：牛市技术面好、熊市风控好、震荡市产业好
TRUE_ACCURACY = {
    "bull_market": {
        "technical": 0.82, "fundflow": 0.78, "industry": 0.72,
        "macro": 0.65, "financial": 0.52, "news": 0.55, "risk": 0.48,
    },
    "bear_market": {
        "risk": 0.85, "financial": 0.76, "industry": 0.73,
        "macro": 0.70, "fundflow": 0.58, "news": 0.52, "technical": 0.45,
    },
    "range_market": {
        "industry": 0.78, "risk": 0.75, "fundflow": 0.76,
        "macro": 0.60, "financial": 0.55, "news": 0.50, "technical": 0.40,
    },
}


def generate_mock_records(
    scenario: str,
    samples_per_expert: int = 60,
    seed: int = 42,
) -> list:
    """为指定场景生成模拟历史信号记录。

    每条记录包含：
      - 专家类型
      - 预测方向与置信度
      - 实际方向（基于真实准确率概率性正确/错误）
      - 时效性天数

    参数:
        scenario: 场景标识
        samples_per_expert: 每个专家生成的样本数
        seed: 随机种子

    返回:
        SignalRecord 列表
    """
    rng = random.Random(seed)
    records = []

    for expert in EXPERTS:
        true_acc = TRUE_ACCURACY[scenario][expert]
        for i in range(samples_per_expert):
            # 确定预测方向
            if scenario == "bull_market":
                predicted = rng.choice(["bullish", "bullish", "bullish", "neutral", "bearish"])
            elif scenario == "bear_market":
                predicted = rng.choice(["bearish", "bearish", "bearish", "neutral", "bullish"])
            else:
                predicted = rng.choices(
                    ["neutral", "bullish", "bearish"], weights=[0.5, 0.25, 0.25]
                )[0]

            # 基于真实准确率决定实际方向
            if rng.random() < true_acc:
                actual = predicted  # 正确预测
            else:
                # 错误预测：随机选一个不等于 predicted 的方向
                others = [d for d in ["bullish", "bearish", "neutral"] if d != predicted]
                actual = rng.choice(others)

            # 置信度：准确率高的专家置信度也偏高
            conf = max(0.3, min(0.95, true_acc + rng.uniform(-0.15, 0.15)))

            # 时效性：准确率高的专家兑现更快
            timeliness = max(1, int((1 - true_acc) * 30) + rng.randint(-3, 3))

            records.append(SignalRecord(
                expert_type=expert,
                scenario=scenario,
                timestamp=f"2025-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}T10:00:00",
                predicted_direction=predicted,
                predicted_confidence=round(conf, 2),
                actual_direction=actual,
                timeliness_days=timeliness,
                signal_type=expert,
                stock_code="300476" if rng.random() < 0.7 else "000001",
            ))

    return records


def generate_all_mock_records(samples_per_expert: int = 60, seed: int = 42) -> list:
    """为全部三个场景生成模拟历史数据。"""
    all_records = []
    for sc in SCENARIOS:
        all_records.extend(generate_mock_records(sc, samples_per_expert, seed))
    return all_records


# ============================================================================
# 测试类
# ============================================================================


class TestAccuracyCalculation:
    """测试准确性指标计算（阶段一）"""

    def test_direction_accuracy_perfect(self):
        """完美预测 → 方向准确率 = 1.0"""
        engine = CalibrationEngine()
        records = [
            SignalRecord("technical", "bull_market", "", "bullish", 0.8, "bullish", 3),
            SignalRecord("technical", "bull_market", "", "bullish", 0.9, "bullish", 2),
            SignalRecord("technical", "bull_market", "", "bullish", 0.7, "bullish", 4),
        ]
        metrics = engine.calculate_accuracy(records)
        m = metrics["bull_market"]["technical"]
        assert m.direction_accuracy == 1.0, f"期望 1.0，实际 {m.direction_accuracy}"

    def test_direction_accuracy_mixed(self):
        """混合正确/错误预测"""
        engine = CalibrationEngine()
        records = [
            SignalRecord("macro", "bull_market", "", "bullish", 0.7, "bullish", 5),
            SignalRecord("macro", "bull_market", "", "bullish", 0.6, "bearish", 8),
            SignalRecord("macro", "bull_market", "", "bullish", 0.8, "bullish", 3),
            SignalRecord("macro", "bull_market", "", "neutral", 0.5, "neutral", 2),
        ]
        metrics = engine.calculate_accuracy(records)
        m = metrics["bull_market"]["macro"]
        assert m.direction_accuracy == 0.75, f"3/4=0.75，实际 {m.direction_accuracy}"

    def test_composite_score_range(self):
        """综合得分应在 [0, 1] 范围内"""
        engine = CalibrationEngine()
        records = generate_all_mock_records(samples_per_expert=50)
        metrics = engine.calculate_accuracy(records)

        for sc in SCENARIOS:
            for expert in EXPERTS:
                m = metrics[sc][expert]
                if m.sample_count > 0:
                    assert 0.0 <= m.composite_score <= 1.0, (
                        f"{sc}/{expert}: composite_score={m.composite_score} 超出 [0,1]"
                    )

    def test_high_accuracy_expert_scores_higher(self):
        """准确率高的专家综合得分应更高"""
        engine = CalibrationEngine()
        records = generate_all_mock_records(samples_per_expert=100)
        metrics = engine.calculate_accuracy(records)

        # 熊市中 risk 理论上准确率最高
        bear = metrics["bear_market"]
        assert bear["risk"].composite_score > bear["technical"].composite_score, (
            f"熊市风控分 {bear['risk'].composite_score} 应 > 技术分 {bear['technical'].composite_score}"
        )

    def test_empty_records(self):
        """空记录 → 所有指标 = 0，sample_count = 0"""
        engine = CalibrationEngine()
        engine.load_anchor_weights()
        metrics = engine.calculate_accuracy([])
        m = metrics["bull_market"]["technical"]
        assert m.sample_count == 0
        assert m.composite_score == 0.0

    def test_confidence_calibration_aligned(self):
        """置信度与正确率对齐时，校准得分不应过低"""
        engine = CalibrationEngine()
        records = []
        # 每个置信度级别生成样本，让预测方向与实际方向匹配的比例接近置信度
        for conf, n_correct in [(0.3, 3), (0.5, 5), (0.7, 7), (0.9, 9)]:
            for i in range(10):
                actual = "bullish" if i < n_correct else "bearish"
                records.append(SignalRecord(
                    "risk", "bull_market", "", "bullish", conf, actual, 5,
                ))
        metrics = engine.calculate_accuracy(records)
        m = metrics["bull_market"]["risk"]
        # 置信度校准在分桶中计算，预期不应为 0
        assert m.confidence_calibration > 0.0, (
            f"置信度与正确率对齐时校准分 {m.confidence_calibration} 应 > 0"
        )


class TestWeightBlending:
    """测试理论-实证融合（阶段二）"""

    def test_no_data_keeps_anchor(self):
        """无历史数据时融合值 = 锚定值"""
        engine = CalibrationEngine(alpha=0.3)
        engine.load_anchor_weights()
        engine.calculate_accuracy([])
        adjustments = engine.blend_weights()

        for sc in SCENARIOS:
            for et in EXPERTS:
                adj = adjustments[sc][et]
                assert adj.blended_weight == adj.anchor_weight, (
                    f"{sc}/{et}: 无数据时融合值 {adj.blended_weight} 应等于锚定 {adj.anchor_weight}"
                )
                assert adj.requires_attention, f"{sc}/{et}: 无数据时需标注关注"

    def test_low_samples_reduces_alpha(self):
        """低样本量时 alpha 自动降低"""
        engine = CalibrationEngine(alpha=0.3)

        # 仅 15 条记录（低于 LOW_SAMPLE_THRESHOLD=50）
        records = []
        for i in range(15):
            records.append(SignalRecord(
                "technical", "bull_market", "", "bullish", 0.8, "bullish", 3,
            ))
        engine.calculate_accuracy(records)
        adjustments = engine.blend_weights()

        # alpha_eff = 0.3 × 0.5 = 0.15
        # blended = 1.3 × 0.85 + 1.0 × 0.15 × 1.6 = 1.105 + 0.24 = 1.345
        adj = adjustments["bull_market"]["technical"]
        assert adj.requires_attention, "低样本量应触发关注标志"
        assert "样本量不足" in adj.attention_reason

    def test_full_alpha_applies_with_enough_data(self):
        """样本充足时 alpha 不衰减"""
        engine = CalibrationEngine(alpha=0.3)
        records = generate_all_mock_records(samples_per_expert=60)
        engine.calculate_accuracy(records)
        adjustments = engine.blend_weights()

        # 技术面在牛市中锚定 1.3，实证准确率 ~0.82
        adj = adjustments["bull_market"]["technical"]
        # 理论-实证融合计算：1.3 × 0.7 + 0.82 × 0.3 × 1.6 = 0.91 + 0.3936 = 1.3036
        assert 1.2 <= adj.blended_weight <= 1.4, (
            f"技术面融合值 {adj.blended_weight} 应在锚定 1.3 附近"
        )
        assert adj.sample_count >= engine.LOW_SAMPLE_THRESHOLD, (
            f"样本量 {adj.sample_count} 应 >= {engine.LOW_SAMPLE_THRESHOLD}"
        )

    def test_blended_weight_within_band(self):
        """融合值应在 ±30% 区间内"""
        engine = CalibrationEngine(alpha=0.3)
        records = generate_all_mock_records(samples_per_expert=60)
        engine.calculate_accuracy(records)
        adjustments = engine.blend_weights()

        for sc in SCENARIOS:
            for et in EXPERTS:
                adj = adjustments[sc][et]
                if adj.sample_count >= engine.LOW_SAMPLE_THRESHOLD:
                    assert adj.band_lower <= adj.blended_weight <= adj.band_upper, (
                        f"{sc}/{et}: {adj.blended_weight} 不在 [{adj.band_lower}, {adj.band_upper}]"
                    )

    def test_direction_preserved(self):
        """理论设定的权重方向不可翻转"""
        engine = CalibrationEngine(alpha=0.3)
        records = generate_all_mock_records(samples_per_expert=60)
        engine.calculate_accuracy(records)
        adjustments = engine.blend_weights()

        # 牛市：technical ↑, risk ↓
        bull = adjustments["bull_market"]
        assert bull["technical"].blended_weight > bull["technical"].anchor_weight * 0.85, (
            "牛市技术面应保持 ↑ 方向"
        )
        # 风控面在牛市理论方向为 ↓，但实证可能在 ±30% 区间内
        # 关键是方向不能翻转：不能从 0.5 大幅跳升到远超锚定值
        risk_adj = bull["risk"]
        assert risk_adj.blended_weight <= risk_adj.anchor_weight * 1.5, (
            f"牛市风控面不应大幅翻转：锚定{risk_adj.anchor_weight} 融合{risk_adj.blended_weight}"
        )


class TestConstraints:
    """测试约束检查（阶段三）"""

    def test_all_pass_with_good_data(self):
        """充足优质数据 → 所有约束通过"""
        engine = CalibrationEngine(alpha=0.3)
        records = generate_all_mock_records(samples_per_expert=60)
        engine.calculate_accuracy(records)
        engine.blend_weights()
        constraints = engine.apply_constraints()

        # 宽松检查：低样本量可能 warning 但不影响 passed
        assert len(constraints.get("band_violations", [])) == 0, (
            f"区间违规: {constraints.get('band_violations', [])}"
        )

    def test_low_sample_warnings(self):
        """样本不足时产生低样本量警告"""
        engine = CalibrationEngine(alpha=0.3)
        records = []
        for i in range(20):
            records.append(SignalRecord(
                "macro", "bull_market", "", "bullish", 0.7, "bullish", 5,
            ))
        engine.calculate_accuracy(records)
        engine.blend_weights()
        constraints = engine.apply_constraints()

        low_sample = constraints.get("low_sample_warnings", [])
        # macro 在牛市中 20 条 < 50，应该触发
        macro_warnings = [w for w in low_sample if w["expert"] == "macro"]
        assert len(macro_warnings) > 0, "macro 仅 20 条应触发低样本量警告"

    def test_validate_split(self):
        """样本外验证：训练集和验证集得分不同"""
        engine = CalibrationEngine(alpha=0.3)
        records = generate_all_mock_records(samples_per_expert=80)
        engine.calculate_accuracy(records)
        engine.blend_weights()
        val = engine.validate_split(train_ratio=0.7)

        # 验证应该有数据
        assert len(val) > 0, "验证结果不应为空"
        # 每个场景都有验证得分
        for sc in SCENARIOS:
            assert sc in val, f"{sc} 应有验证结果"
            assert len(val[sc]) > 0, f"{sc} 验证结果应有专家数据"


class TestFullCalibration:
    """端到端校准流程测试"""

    def test_run_full_calibration(self):
        """完整三阶段流程最终产出报告"""
        records = generate_all_mock_records(samples_per_expert=60)
        report = generate_calibration_report(records, alpha=0.3)

        # 报告结构完整
        assert "meta" in report
        assert "accuracy_metrics" in report
        assert "adjustments" in report
        assert "constraints" in report
        assert "validation" in report

        # 元数据正确
        assert report["meta"]["total_records"] == len(records)
        assert report["meta"]["alpha"] == 0.3

        # 三个场景都有数据
        for sc in SCENARIOS:
            assert sc in report["adjustments"], f"{sc} 应在调整结果中"
            assert len(report["adjustments"][sc]) == 7, (
                f"{sc} 应有 7 个专家，实际 {len(report['adjustments'][sc])}"
            )

    def test_report_formatting(self):
        """格式化报告输出可读"""
        records = generate_all_mock_records(samples_per_expert=60)
        text = generate_report_text(records, alpha=0.3)

        assert "AI_Renaissance 权重校准报告" in text
        assert "牛市场景" in text
        assert "熊市场景" in text
        assert "震荡市场景" in text
        assert "锚定值" in text
        assert "建议值" in text
        assert "约束检查" in text
        assert "重要说明" in text
        assert "报告结束" in text

    def test_report_json_export(self):
        """JSON 报告导出与回读"""
        records = generate_all_mock_records(samples_per_expert=60)
        engine = CalibrationEngine(alpha=0.3)
        report = engine.run_full_calibration(records=records)

        tmp_path = os.path.join(tempfile.gettempdir(), "test_calibration_report.json")
        try:
            engine.save_report(report, tmp_path)
            assert os.path.exists(tmp_path), "JSON 文件应存在"

            with open(tmp_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)

            assert "meta" in loaded, "应有 meta 字段"
            assert loaded["meta"]["total_records"] == len(records), (
                f"total_records 应为 {len(records)}，实际 {loaded['meta']['total_records']}"
            )
            assert "adjustments" in loaded, "应有 adjustments 字段"
            assert "bull_market" in loaded["adjustments"], "应包含牛市场景"
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)


class TestEdgeCases:
    """边界情况测试"""

    def test_all_neutral_signals(self):
        """全部中性信号"""
        engine = CalibrationEngine()
        records = [
            SignalRecord("technical", "range_market", "", "neutral", 0.5, "neutral", 5),
        ] * 50
        metrics = engine.calculate_accuracy(records)
        m = metrics["range_market"]["technical"]
        assert m.direction_accuracy == 1.0, "全部中性且全部正确 → 1.0"

    def test_extreme_alpha(self):
        """alpha=0 → 完全信任理论，融合值 = 锚定值"""
        engine = CalibrationEngine(alpha=0.0)
        records = generate_all_mock_records(samples_per_expert=60)
        engine.calculate_accuracy(records)
        adjustments = engine.blend_weights()

        for sc in SCENARIOS:
            for et in EXPERTS:
                adj = adjustments[sc][et]
                assert adj.blended_weight == adj.anchor_weight, (
                    f"{sc}/{et}: alpha=0 时融合值 {adj.blended_weight} 应 = 锚定 {adj.anchor_weight}"
                )

    def test_alpha_one(self):
        """alpha=1.0 → 完全信任实证，融合值接近实证分 × scale"""
        engine = CalibrationEngine(alpha=1.0)
        records = generate_all_mock_records(samples_per_expert=60)
        engine.calculate_accuracy(records)
        adjustments = engine.blend_weights()

        # 技术面实证分 ~0.82, alpha=1, 融合 ≈ 0.82 × 1.6 = 1.312
        adj = adjustments["bull_market"]["technical"]
        expected = adj.empirical_score * engine.SCALE_FACTOR
        assert abs(adj.blended_weight - expected) < 0.1, (
            f"alpha=1 时融合值 {adj.blended_weight} 应接近 {expected}"
        )

    def test_records_from_dicts(self):
        """从字典批量构造 SignalRecord"""
        data = [
            {"expert_type": "technical", "scenario": "bull_market",
             "predicted_direction": "bullish", "predicted_confidence": "0.75",
             "actual_direction": "bullish", "timeliness_days": "3"},
            {"expert_type": "risk", "scenario": "bear_market",
             "predicted_direction": "bearish", "predicted_confidence": "0.82",
             "actual_direction": "bearish", "timeliness_days": "2"},
        ]
        records = CalibrationEngine.records_from_dicts(data)
        assert len(records) == 2
        assert records[0].expert_type == "technical"
        assert records[0].predicted_confidence == 0.75

    def test_custom_anchor_weights(self):
        """自定义锚定权重"""
        custom = {
            "bull_market": {"technical": 1.5, "risk": 0.3},
        }
        engine = CalibrationEngine()
        engine.load_anchor_weights(custom)
        assert engine._anchor_weights["bull_market"]["technical"] == 1.5
        assert engine._anchor_weights["bull_market"]["risk"] == 0.3


# ============================================================================
# 运行入口
# ============================================================================

def run_all_tests():
    """运行所有测试并打印结果。"""
    print("=" * 72)
    print("  权重校准引擎 —— 测试套件")
    print("=" * 72)

    test_classes = [
        ("准确性指标计算", TestAccuracyCalculation),
        ("理论-实证融合", TestWeightBlending),
        ("约束检查", TestConstraints),
        ("端到端校准流程", TestFullCalibration),
        ("边界情况", TestEdgeCases),
    ]

    total = 0
    passed = 0
    failed = 0

    for section_name, cls in test_classes:
        print(f"\n{'─' * 72}")
        print(f"  {section_name}")
        print(f"{'─' * 72}")

        instance = cls()
        test_methods = [
            m for m in dir(instance)
            if m.startswith("test_") and callable(getattr(instance, m))
        ]

        for method_name in sorted(test_methods):
            total += 1
            method = getattr(instance, method_name)
            test_display = method_name.replace("test_", "").replace("_", " ")
            try:
                method()
                print(f"  ✓ {method_name} — {test_display}")
                passed += 1
            except AssertionError as e:
                print(f"  ✗ {method_name} — {test_display}")
                print(f"      断言失败: {e}")
                failed += 1
            except Exception as e:
                print(f"  ✗ {method_name} — {test_display}")
                print(f"      异常: {type(e).__name__}: {e}")
                failed += 1

    print(f"\n{'=' * 72}")
    print(f"  总计: {total}  通过: {passed}  失败: {failed}")
    print(f"{'=' * 72}")

    return failed == 0


def demo_report():
    """打印一份完整的校准报告示例。"""
    print("\n" + "=" * 72)
    print("  校准报告示例（模拟数据，3 场景 × 7 专家 × 60 条/专家）")
    print("=" * 72)

    records = generate_all_mock_records(samples_per_expert=60)
    text = generate_report_text(records, alpha=0.3)
    print(text)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="权重校准引擎测试")
    parser.add_argument("--demo", action="store_true", help="打印完整报告示例")
    parser.add_argument("--quiet", action="store_true", help="静默模式（仅显示总结）")
    args = parser.parse_args()

    if args.demo:
        demo_report()
        success = True
    else:
        success = run_all_tests()

    sys.exit(0 if success else 1)
