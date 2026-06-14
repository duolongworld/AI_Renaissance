"""
场景基类 —— 规定每个市场场景必须能回答的 6 个问题。

方法论依据：
  桥水经济机器模型（Ray Dalio）将市场环境定义为三个维度的函数：
  f(经济增长方向, 通胀方向, 风险溢价水平)。
  这三个维度映射为三种基础场景：牛市（扩张期）、熊市（收缩期）、
  震荡市（均衡期）。详细理论依据见开发2组 SKILL.md。

设计原则：
  这是仲裁引擎松耦合的核心——引擎只问固定问题，场景提供不同答案。
  添加新场景只需继承本类并实现所有方法，引擎代码无需任何修改。
"""

from typing import Dict, List, Tuple, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from agents.signal import Signal


class ScenarioProfile:
    """
    场景基类 —— 所有市场场景的"空白表格"模板。

    每个子类（牛市、熊市、震荡市等）必须实现下面全部方法。
    仲裁引擎只通过这套接口与场景对话，不关心具体是哪个场景。
    """

    # ============================================================
    # 问题 1：你是谁？
    # ============================================================

    @property
    def name(self) -> str:
        """
        场景唯一标识名，如 "bull_market"。
        用于配置引用和日志追踪。
        """
        raise NotImplementedError("子类必须实现 name")

    @property
    def display_name(self) -> str:
        """
        场景中文显示名，如 "牛市场景"。
        用于输出给用户看的推理链。
        """
        raise NotImplementedError("子类必须实现 display_name")

    @property
    def description(self) -> str:
        """
        场景一句话描述，说明这个场景下市场的主要特征。
        例："大盘处于上升趋势，市场情绪乐观，资金持续流入"
        """
        raise NotImplementedError("子类必须实现 description")

    # ============================================================
    # 问题 2：每个专家的权重怎么定？（融合逻辑的核心）
    # ============================================================

    def get_weight(self, expert_type: str, market_data: Optional[Dict] = None) -> Tuple[float, str]:
        """
        获取指定专家在当前场景下的权重及理由。

        参数:
            expert_type: 专家类型标识，如 "technical"、"financial"、"macro" 等
            market_data: 当前市场数据（可选），用于条件判断逻辑，如 RSI、成交量等

        返回:
            (权重值, 权重理由)
            例: (1.2, "趋势明确向上，技术信号可靠性高")

        这是融合逻辑的核心入口。子类必须实现这个方法，
        权重的每一个数字都必须附带可追溯的理由。
        """
        raise NotImplementedError("子类必须实现 get_weight")

    def get_all_weights(self, market_data: Optional[Dict] = None) -> Dict[str, Tuple[float, str]]:
        """
        一次性获取所有注册专家的权重及理由。

        参数:
            market_data: 当前市场数据（可选）

        返回:
            {expert_type: (权重值, 权重理由), ...}
            例: {"technical": (1.2, "趋势向上..."), "financial": (0.8, "财务信号滞后...")}
        """
        raise NotImplementedError("子类必须实现 get_all_weights")

    # ============================================================
    # 问题 3：仓位怎么算？
    # ============================================================

    def get_position_ratio(self, confidence: float, direction: str) -> Tuple[float, str]:
        """
        根据置信度和方向计算建议仓位比例。

        参数:
            confidence: 仲裁后的综合置信度 (0.0 ~ 1.0)
            direction: 信号方向 ("bullish" / "bearish" / "neutral")

        返回:
            (仓位比例, 计算公式说明)
            例: (0.36, "置信度 0.6 × 牛市系数 0.6 = 0.36")

        注意:
            - neutral 方向必须返回 0.0
            - 结果必须在 [0.0, 1.0] 范围内
        """
        raise NotImplementedError("子类必须实现 get_position_ratio")

    # ============================================================
    # 问题 4：这个场景下需要特别注意什么风险？
    # ============================================================

    def get_scenario_risks(self, market_data: Optional[Dict] = None) -> List[str]:
        """
        返回该场景特有的风险提示清单。

        参数:
            market_data: 当前市场数据（可选），用于触发条件风险

        返回:
            风险提示字符串列表
            例: ["牛市追高风险：RSI 超买，短期回调概率增大"]

        注意:
            这些是场景层面的宏观风险。
            信号层面的具体风险由仲裁引擎的 _check_risks 处理。
        """
        raise NotImplementedError("子类必须实现 get_scenario_risks")

    # ============================================================
    # 问题 5：场景特有的置信度阈值（可选覆盖）
    # ============================================================

    def get_confidence_threshold(self) -> Optional[float]:
        """
        返回该场景推荐的置信度阈值，用于信号筛选。

        返回 None 表示使用引擎默认阈值（0.6）。

        某些场景中信号天然偏中性低置信度（如震荡市），
        可以降低阈值以避免过度过滤导致信号不足。

        返回:
            推荐阈值（0.0 ~ 1.0），或 None（使用默认）
            例: 0.45  → 震荡市中降低阈值，保留更多信号
        """
        return None  # 默认不覆盖

    # ============================================================
    # 问题 6：基于专家信号的场景匹配（场景选择核心）
    # ============================================================

    def match_signals(self, signals: List["Signal"]) -> Tuple[float, str, Dict]:
        """
        对当前专家信号组合进行评分制场景匹配（v2 升级）。

        从二元（匹配/不匹配）升级为 0-1 分数制：
        - 每个条件根据信号方向和置信度计算 0-1 分（而非 True/False）
        - 多个条件的分数按场景特有规则聚合（简单平均 / top-N 平均）
        - 返回综合匹配度和逐条件分解，支持白箱审计

        设计原则:
          - 不读取原始市场数据（CPI、K线、VIX 等）——那是专家组的事
          - 只读专家组产出的 Signal（方向 + 置信度 + 信号类型）
          - 每个场景定义自己的条件评分公式和聚合规则

        参数:
            signals: 所有专家产出的 Signal 列表。
                每个 Signal 包含 direction、confidence、signal_type、source 等字段。

        返回:
            (匹配分数 0.0-1.0, 综合判断理由, 详细分解)
            详细分解字段:
              - "condition_scores": {条件名: 分数}
              - "condition_details": {条件名: 判据说明}
              - "aggregate_method": "average" | "top_n" 聚合方式
              - "aggregate_score": 聚合后的综合分数
              - "passed_threshold": bool 是否满足匹配阈值

            例: (0.73, "三条件全部满足，综合匹配度 0.73",
                 {"condition_scores": {"macro": 0.75, "risk": 0.65, "bias": 0.80},
                  "condition_details": {...},
                  "aggregate_method": "average",
                  "aggregate_score": 0.73,
                  "passed_threshold": True})

        如果 signals 为空，返回 (0.0, "无专家信号，无法判断", {})。
        """
        raise NotImplementedError("子类必须实现 match_signals")

    # ============================================================
    # 工具方法
    # ============================================================

    @staticmethod
    def _find_signal(signals: List["Signal"], signal_type: str) -> Optional["Signal"]:
        """按 signal_type 查找信号。"""
        for s in signals:
            if s.signal_type == signal_type:
                return s
        return None

    @staticmethod
    def _count_direction(signals: List["Signal"], direction: str) -> int:
        """统计指定方向的信号数量。"""
        return sum(1 for s in signals if s.direction == direction)

    @staticmethod
    def _confidence_score(signal: Optional["Signal"], target_direction: str) -> float:
        """
        基于信号置信度的方向匹配评分。

        评分逻辑:
          - 信号存在且方向匹配 + conf >= 0.7  → conf (0.7-1.0)
          - 信号存在且方向匹配 + conf >= 0.5  → conf (0.5-0.7)
          - 信号存在且方向匹配 + conf >= 0.3  → conf × 0.6 (0.18-0.30)
          - 方向不匹配或无信号              → 0.0
        """
        if signal is None:
            return 0.0
        if signal.direction != target_direction:
            return 0.0
        if signal.confidence >= 0.5:
            return signal.confidence
        if signal.confidence >= 0.3:
            return signal.confidence * 0.6
        return 0.0

    @staticmethod
    def _direction_ratio_score(signals: List["Signal"], target_direction: str) -> float:
        """
        基于多空信号数量比的方向评分。

        计算公式: target_direction_count / (bullish_count + bearish_count)
        - target 方向信号越多、对手方向越少，分数越高
        - 例: bull=4, bear=1 → 4/5 = 0.80
        - 例: bull=2, bear=1 → 2/3 = 0.67
        - target <= opponent → 0.0
        - 无方向信号 → 0.0
        """
        bullish = sum(1 for s in signals if s.direction == "bullish")
        bearish = sum(1 for s in signals if s.direction == "bearish")
        total = bullish + bearish
        if total == 0:
            return 0.0
        target_count = bullish if target_direction == "bullish" else bearish
        opponent_count = bearish if target_direction == "bullish" else bullish
        if target_count <= opponent_count:
            return 0.0
        return target_count / total

    def to_dict(self) -> Dict:
        """将场景基本信息转为字典，供输出展示用。"""
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
        }

    def __repr__(self) -> str:
        return f"<ScenarioProfile: {self.display_name}>"


class DefaultScenario(ScenarioProfile):
    """
    默认场景 —— 所有专家等权，保持向后兼容。

    当没有指定场景时使用此默认值。
    权重全部为 1.0，即不调整任何专家的影响力。
    """

    @property
    def name(self) -> str:
        return "default"

    @property
    def display_name(self) -> str:
        return "默认场景（等权）"

    @property
    def description(self) -> str:
        return "未指定市场场景，所有专家等权处理"

    DEFAULT_WEIGHTS: Dict[str, Tuple[float, str]] = {
        "financial":  (1.0, "默认等权，未指定场景"),
        "technical":  (1.0, "默认等权，未指定场景"),
        "macro":      (1.0, "默认等权，未指定场景"),
        "news":       (1.0, "默认等权，未指定场景"),
        "fundflow":  (1.0, "默认等权，未指定场景"),
        "industry":   (1.0, "默认等权，未指定场景"),
        "risk":       (1.0, "默认等权，未指定场景"),
    }

    def get_weight(self, expert_type: str, market_data: Optional[Dict] = None) -> Tuple[float, str]:
        if expert_type in self.DEFAULT_WEIGHTS:
            return self.DEFAULT_WEIGHTS[expert_type]
        return (1.0, f"未知专家类型 '{expert_type}'，使用默认等权")

    def get_all_weights(self, market_data: Optional[Dict] = None) -> Dict[str, Tuple[float, str]]:
        return dict(self.DEFAULT_WEIGHTS)

    def get_position_ratio(self, confidence: float, direction: str) -> Tuple[float, str]:
        if direction == "neutral":
            return (0.0, "中性方向，不持仓")
        position = min(confidence * 0.5, 0.3)
        return (position, f"默认公式：置信度 {confidence:.2f} × 0.5 = {position:.2f}，上限 0.3")

    def get_scenario_risks(self, market_data: Optional[Dict] = None) -> List[str]:
        return []

    def match_signals(self, signals: List["Signal"]) -> Tuple[float, str, Dict]:
        if not signals:
            return (0.0, "无专家信号，无法判断", {})
        return (0.3, "默认场景总是可用（降级模式）", {
            "condition_scores": {},
            "condition_details": {"fallback": "无匹配场景，降级为默认等权"},
            "aggregate_method": "fallback",
            "aggregate_score": 0.3,
            "passed_threshold": False,
        })
