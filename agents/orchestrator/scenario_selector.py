"""
场景选择器 —— 基于专家信号自动匹配市场场景。

方法论依据：
  桥水经济机器模型（Ray Dalio）将市场环境表达为三维度函数：
  f(经济增长方向, 通胀方向, 风险溢价水平)。场景选择器通过专家组
  Signal 的方向与置信度还原这三个维度，并映射为对应的市场场景。
  详细理论依据见开发2组 SKILL.md 第二节。

核心理念：
  不读取原始市场数据（CPI、K线、VIX 等），
  只读专家组产出的 Signal（方向 + 置信度 + 信号类型），
  将 Signal 组合映射到对应的市场场景。

分工边界：
  宏观组分析经济数据 → 产出 Signal
  风控组分析风险数据 → 产出 Signal
  场景选择器读取 Signal → 选择场景 → 仲裁引擎以对应权重融合

此设计保证各组在其专业领域内工作，不越界、不重复。

取代了旧版 regime_detector.py（从原始数据判断场景的过时方案）。
"""

from typing import Dict, List, Tuple, Optional, TYPE_CHECKING

from agents.orchestrator.scenario_profile import ScenarioProfile
from agents.orchestrator.scenarios import SCENARIO_REGISTRY, create_default_scenario, get_scenario
from loguru import logger

if TYPE_CHECKING:
    from agents.signal import Signal


class ScenarioSelector:
    """
    场景选择器 —— 从专家 Signal 中选择最匹配的市场场景。

    工作原理:
      1. 接收所有专家产出的 Signal 列表
      2. 遍历已注册的场景，调用各自的 match_signals(signals)
      3. 找出最匹配的场景 + 所有场景的判断记录
      4. 输出选择结果，附带完整理由供用户审查

    使用示例:
        selector = ScenarioSelector()

        # 从 SignalBundle 中取出 signals
        signals = signal_bundle.signals
        scenario, report = selector.select(signals)

        print(f"选中场景: {scenario.display_name}")
        print(f"选择理由: {report['reasoning']}")
    """

    def __init__(self):
        """初始化选择器，加载所有注册的场景。"""
        self._scenarios = self._load_scenarios()
        logger.info(
            f"[ScenarioSelector] 初始化完成，"
            f"已加载 {len(self._scenarios)} 个场景: "
            f"{[s.display_name for s in self._scenarios]}"
        )

    def _load_scenarios(self) -> List[ScenarioProfile]:
        """加载所有已注册的场景实例。"""
        scenarios = []
        for name, cls in SCENARIO_REGISTRY.items():
            try:
                scenario = cls()
                scenarios.append(scenario)
            except Exception as exc:
                logger.error(f"[ScenarioSelector] 加载场景 '{name}' 失败: {exc}")
        return scenarios

    # ============================================================
    # 选择入口
    # ============================================================

    def select(self, signals: List["Signal"]) -> Dict:
        """
        根据专家信号评分制选择最匹配的市场场景（v2 升级）。

        参数:
            signals: 所有专家产出的 Signal 列表。
                每个 Signal 包含 direction、confidence、signal_type、source 等字段。

        返回:
            {
                "selected_scenario": "bull_market",     # 选中的场景标识名
                "selected_display_name": "牛市场景",     # 选中场景显示名
                "confidence": 0.58,                     # 选择置信度（基于匹配分数）
                "match_score": 0.73,                    # 选中场景的匹配分数
                "reasoning": "...",                      # 完整判断理由
                "all_checks": [                          # 每个场景的评分记录
                    {
                        "scenario": "bull_market",
                        "display_name": "牛市场景",
                        "match_score": 0.73,
                        "passed_threshold": True,
                        "reason": "牛市场景匹配 ✓ — 宏观组强力看多...",
                    },
                    ...
                ],
                "fallback": False,                       # 是否降级为默认
                "ambiguous": False,                      # 是否多场景竞争
                "signal_count": len(signals),            # 信号总数
                "signal_sources": [...],                 # 信号来源清单
            }
        """
        if not signals:
            return self._fallback_result(
                "无专家信号，无法进行场景选择",
                signal_count=0,
                signal_sources=[],
            )

        signal_sources = list({s.source for s in signals}) if signals else []

        # 遍历所有场景，收集评分
        checks = []
        for scenario in self._scenarios:
            score, reason, detail = scenario.match_signals(signals)
            passed = detail.get("passed_threshold", False) if detail else False
            checks.append({
                "scenario": scenario.name,
                "display_name": scenario.display_name,
                "match_score": score,
                "passed_threshold": passed,
                "reason": reason,
                "detail": detail,
            })
            logger.debug(
                f"[ScenarioSelector] {scenario.display_name}: "
                f"score={score:.3f}, passed={passed}, reason={reason[:80]}..."
            )

        # 按匹配分数降序排列
        checks.sort(key=lambda c: c["match_score"], reverse=True)
        top = checks[0]
        top_score = top["match_score"]

        # 分数 < 0.5 → 无场景匹配，降级默认
        if top_score < 0.5:
            return self._fallback_result(
                f"所有场景匹配分数均低于阈值 0.5（最高: {top['display_name']} {top_score:.2f}）",
                all_checks=checks,
                signal_count=len(signals),
                signal_sources=signal_sources,
            )

        # 判断是否存在多场景竞争
        second_score = checks[1]["match_score"] if len(checks) > 1 else 0.0
        ambiguous = (
            second_score >= 0.5 and                              # 第二名也过阈值
            abs(top_score - second_score) < 0.15                 # 分数差距 < 0.15
        )

        # 计算选择置信度
        if ambiguous:
            confidence = round(top_score * 0.6, 2)              # 竞争 + 扣分
        elif top_score >= 0.6:
            confidence = round(top_score * 0.8, 2)              # 高质量匹配
        else:
            confidence = round(top_score * 0.6, 2)              # 弱匹配

        # 构建理由
        if ambiguous:
            conflict_names = [c["display_name"] for c in checks if c["match_score"] >= 0.5]
            reasoning = (
                f"多场景竞争（{', '.join(conflict_names)}），"
                f"分数差距 {top_score - second_score:.2f} < 0.15。"
                f"选择 {top['display_name']}（{top_score:.2f}），"
                f"建议人工确认。理由: {top['reason']}"
            )
        else:
            reasoning = (
                f"{'唯一' if second_score < 0.5 else '最高'}匹配：{top['display_name']}"
                f"（{top_score:.2f}）。理由: {top['reason']}"
            )

        return self._build_result(
            scenario_name=top["scenario"],
            display_name=top["display_name"],
            confidence=confidence,
            match_score=top_score,
            reasoning=reasoning,
            all_checks=checks,
            signal_count=len(signals),
            signal_sources=signal_sources,
            ambiguous=ambiguous,
        )

    # ============================================================
    # 便捷方法
    # ============================================================

    def select_scenario(self, signals: List["Signal"]) -> Tuple[ScenarioProfile, Dict]:
        """
        获取建议的场景实例 + 选择报告。

        返回:
            (场景实例, 选择报告字典)
            如果选择失败，返回默认场景实例。

        使用示例:
            scenario, report = selector.select_scenario(bundle.signals)
            print(f"使用场景: {scenario.display_name}")
            print(f"选择报告: {report['reasoning']}")
        """
        report = self.select(signals)
        scenario_name = report["selected_scenario"]
        scenario = get_scenario(scenario_name)
        if scenario is None:
            scenario = create_default_scenario()
        return scenario, report

    def list_available_scenarios(self) -> List[str]:
        """列出选择器可识别的场景名称。"""
        return [s.name for s in self._scenarios]

    # ============================================================
    # 内部方法
    # ============================================================

    def _build_result(
        self,
        scenario_name: str,
        display_name: str,
        confidence: float,
        match_score: float,
        reasoning: str,
        all_checks: List[Dict],
        signal_count: int,
        signal_sources: List[str],
        ambiguous: bool = False,
    ) -> Dict:
        """构建标准化的选择结果。"""
        return {
            "selected_scenario": scenario_name,
            "selected_display_name": display_name,
            "confidence": confidence,
            "match_score": match_score,
            "reasoning": reasoning,
            "all_checks": all_checks,
            "fallback": False,
            "ambiguous": ambiguous,
            "available_scenarios": self.list_available_scenarios(),
            "signal_count": signal_count,
            "signal_sources": signal_sources,
        }

    def _fallback_result(
        self,
        reason: str,
        all_checks: Optional[List[Dict]] = None,
        signal_count: int = 0,
        signal_sources: Optional[List[str]] = None,
    ) -> Dict:
        """构建降级结果（无法判断时使用默认场景）。"""
        return {
            "selected_scenario": "default",
            "selected_display_name": "默认场景（等权）",
            "confidence": 0.0,
            "match_score": 0.0,
            "reasoning": f"场景选择失败：{reason}，降级为默认等权场景",
            "all_checks": all_checks or [],
            "fallback": True,
            "ambiguous": False,
            "available_scenarios": self.list_available_scenarios(),
            "signal_count": signal_count,
            "signal_sources": signal_sources or [],
        }
