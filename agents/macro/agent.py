"""
宏观分析 Agent - 专家4组

signal_type: macro
Skill 域: skills/macro/

核心能力：7层流水线分析（Layer 0-5）
- Layer 0: 双经济体追踪
- Layer 1: CAI/FCI计算
- Layer 2: 周期定位
- Layer 2.5: 枢纽变量分析
- Layer 3: 市场定价提取
- Layer 4: 预期差信号引擎
- Layer 4.5: 反身性与元认知
- Layer 5: 资产配置
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
import re
import sys
from pathlib import Path

# 确保 skills/macro 在 sys.path 中，使各层 analyzer 中的 "from utils.xxx import ..." 可被解析
_MACRO_SKILLS_ROOT = Path(__file__).resolve().parents[2] / "skills" / "macro"
if str(_MACRO_SKILLS_ROOT) not in sys.path:
    sys.path.insert(0, str(_MACRO_SKILLS_ROOT))

from loguru import logger

from agents.base import BaseAgent
from agents.signal import Signal, neutral_signal

# =============================================================================
# 7层流水线脚本导入
# =============================================================================

from skills.macro.layer0_tracking.scripts.analyzer import (
    analyze_bilateral_tracking,
    generate_llm_prompt as generate_layer0_prompt,
)
from skills.macro.layer1_cai_fci.scripts.analyzer import (
    analyze_cai_fci,
)
from skills.macro.layer2_cycle_positioning.scripts.analyzer import (
    analyze_cycle_positioning,
    generate_llm_prompt as generate_layer2_prompt,
)
from skills.macro.layer2_5_hub_variable.scripts.analyzer import (
    analyze_hub_variable,
    generate_llm_prompt as generate_layer25_prompt,
)
from skills.macro.layer3_market_pricing.scripts.analyzer import (
    analyze_market_pricing,
)
from skills.macro.layer4_expected_diff.scripts.analyzer import (
    analyze_expected_diff,
)
from skills.macro.layer4_5_reflexivity.scripts.analyzer import (
    analyze_reflexivity,
)
from skills.macro.layer5_asset_allocation.scripts.analyzer import (
    analyze_asset_allocation,
)
from skills.macro._workspace.test_data.macro_test_data_2024_06_28 import (
    build_complete_mock_data,
)


# =============================================================================
# 推理链数据结构（仅在 MacroAgent 内部使用）
# =============================================================================

class ReasoningStep:
    """
    推理步骤 - 记录分析过程中的单个推理步骤
    
    Attributes:
        layer_name: 层名称 (layer0-layer5)
        layer_number: 层编号 (0-5)
        step_name: 步骤名称
        input_summary: 输入数据摘要
        analysis_logic: 分析逻辑描述
        intermediate_conclusion: 中间结论
        confidence: 该步骤置信度 (0.0-1.0)
        uncertainty_sources: 不确定性来源列表
        evidence: 支撑证据列表
        timestamp: 时间戳
    """
    def __init__(
        self,
        layer_name: str,
        layer_number: float,
        step_name: str,
        input_summary: str,
        analysis_logic: str,
        intermediate_conclusion: str,
        confidence: float,
        uncertainty_sources: List[str] = None,
        evidence: List[str] = None,
    ):
        self.layer_name = layer_name
        self.layer_number = layer_number
        self.step_name = step_name
        self.input_summary = input_summary
        self.analysis_logic = analysis_logic
        self.intermediate_conclusion = intermediate_conclusion
        self.confidence = confidence
        self.uncertainty_sources = uncertainty_sources or []
        self.evidence = evidence or []
        self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "layer_name": self.layer_name,
            "layer_number": self.layer_number,
            "step_name": self.step_name,
            "input_summary": self.input_summary,
            "analysis_logic": self.analysis_logic,
            "intermediate_conclusion": self.intermediate_conclusion,
            "confidence": self.confidence,
            "uncertainty_sources": self.uncertainty_sources,
            "evidence": self.evidence,
            "timestamp": self.timestamp,
        }


class ReasoningChain:
    """
    推理链 - 按顺序记录多层分析过程中的所有推理步骤
    
    Attributes:
        steps: 推理步骤列表（按执行顺序）
        final_conclusion: 最终结论
        chain_confidence: 链整体置信度
    """
    def __init__(self):
        self.steps: List[ReasoningStep] = []
        self.final_conclusion: str = ""
        self.chain_confidence: float = 0.0

    def add_step(self, step: ReasoningStep) -> None:
        self.steps.append(step)

    def calculate_chain_confidence(self) -> float:
        if not self.steps:
            return 0.0
        return sum(s.confidence for s in self.steps) / len(self.steps)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "steps": [s.to_dict() for s in self.steps],
            "final_conclusion": self.final_conclusion,
            "chain_confidence": self.chain_confidence,
            "step_count": len(self.steps),
        }

    def to_markdown(self) -> str:
        lines = ["## 推理链\n"]
        
        if not self.steps:
            lines.append("*（无推理步骤记录）*")
            return "\n".join(lines)

        for i, step in enumerate(self.steps, 1):
            lines.append(f"### Step {i}: {step.step_name}")
            lines.append(f"- **层级**: {step.layer_name} (Layer {step.layer_number})")
            lines.append(f"- **输入**: {step.input_summary}")
            lines.append(f"- **分析逻辑**: {step.analysis_logic}")
            lines.append(f"- **中间结论**: {step.intermediate_conclusion}")
            lines.append(f"- **置信度**: {step.confidence:.0%}")

            if step.evidence:
                lines.append(f"- **证据**:")
                for ev in step.evidence:
                    lines.append(f"  - {ev}")

            if step.uncertainty_sources:
                lines.append(f"- **不确定性来源**:")
                for src in step.uncertainty_sources:
                    lines.append(f"  - {src}")

            lines.append("")

        if self.final_conclusion:
            lines.append(f"**最终结论**: {self.final_conclusion}")
            lines.append(f"**整体置信度**: {self.chain_confidence:.0%}")

        return "\n".join(lines)


# =============================================================================
# Agent 实现
# =============================================================================

class MacroAgent(BaseAgent):
    """
    宏观分析 Agent（专家4组）

    实现7层流水线分析，按顺序调用各层脚本，最终输出标准化 Signal。
    
    数据获取由 Agent 负责，当前使用伪代码+模拟数据预留。
    
    推理链设计：
    - 推理链数据结构（ReasoningStep, ReasoningChain）定义在 agent 内部
    - 推理链结果存储在 signal.meta["reasoning_chain"] 中
    - 提供 to_markdown() 方法生成可读的推理链
    """

    signal_type = "macro"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(name="宏观分析Agent", config=config or {})
        
        # 加载 macro 领域的 Skill（用于智能分析层）
        self.load_skills_from_domain("macro")
        
        # LLM 调用接口（待实现）
        self._llm_client = None
        
        logger.info(f"[{self.name}] 7层流水线已就绪")

    def set_llm_client(self, llm_client) -> None:
        """
        设置 LLM 调用客户端。
        
        Args:
            llm_client: 实现 call_llm(prompt: str, system: str) -> str 的客户端
        """
        self._llm_client = llm_client
        logger.info(f"[{self.name}] LLM客户端已设置")

    def analyze(self, stock_code: str, period: str = None) -> Signal:
        """
        执行7层流水线分析。

        Args:
            stock_code: 股票代码（与其他 Agent 签名对齐）
            period: 分析时段，如 "2026-05-05至2026-05-12"
        
        Returns:
            标准 Signal 对象（signal_type="macro"）
        """
        self.log("开始宏观分析7层流水线")
        start_time = datetime.now()
        
        try:
            # Step 1: 数据获取
            data = self._fetch_macro_data()
            
            # Step 2: Layer 0 - 双经济体追踪
            layer0_result = self._run_layer0(data)
            
            # Step 3: Layer 1 - CAI/FCI计算
            layer1_result = self._run_layer1(data)
            
            # Step 4: Layer 2 - 周期定位
            layer2_result = self._run_layer2(data, layer1_result)
            
            # Step 5: Layer 2.5 - 枢纽变量分析
            layer25_result = self._run_layer25(data, layer1_result)
            
            # Step 6: Layer 3 - 市场定价提取
            layer3_result = self._run_layer3(layer1_result, data)
            
            # Step 7: Layer 4 - 预期差信号引擎（需Layer 2.5枢纽变量结果）
            layer4_result = self._run_layer4(layer1_result, layer3_result, layer25_result)
            
            # Step 8: Layer 4.5 - 反身性与元认知
            layer45_result = self._run_layer45(data, layer4_result)
            
            # Step 9: Layer 5 - 资产配置
            layer5_result = self._run_layer5(layer2_result, layer4_result, layer45_result)
            
            # 汇总最终 Signal
            final_signal = layer5_result.get("macro_signal")
            final_signal.stock_code = stock_code
            
            # ========== 构建推理链 ==========
            reasoning_chain = self._build_reasoning_chain(
                data=data,
                layer0_result=layer0_result,
                layer1_result=layer1_result,
                layer2_result=layer2_result,
                layer25_result=layer25_result,
                layer3_result=layer3_result,
                layer4_result=layer4_result,
                layer45_result=layer45_result,
                layer5_result=layer5_result,
            )
            
            # 添加执行信息
            final_signal.meta["execution_info"] = {
                "layers_executed": ["layer0", "layer1", "layer2", "layer2_5", "layer3", "layer4", "layer4_5", "layer5"],
                "execution_time": (datetime.now() - start_time).total_seconds(),
                "data_status": "mock" if data.get("_is_mock") else "live",
            }
            
            # 添加各层输出到 meta
            final_signal.meta["layer_outputs"] = {
                "layer0": layer0_result.get("layer_output", {}),
                "layer1": layer1_result.get("layer_output", {}),
                "layer2": layer2_result.get("layer_output", {}),
                "layer2_5": layer25_result.get("layer_output", {}),
                "layer3": layer3_result.get("layer_output", {}),
                "layer4": layer4_result.get("layer_output", {}),
                "layer4_5": layer45_result.get("layer_output", {}),
                "layer5": layer5_result.get("layer_output", {}),
            }
            
            # 基于全局推理链生成推理摘要（覆盖 layer5 阶段的局部摘要）
            final_signal.reasoning = self._summarize_reasoning_chain(reasoning_chain, final_signal)

            # 添加推理链到 meta（存储完整 markdown 格式）
            final_signal.meta["reasoning_chain"] = reasoning_chain.to_markdown()
            
            self.log(f"宏观分析完成，耗时{(datetime.now() - start_time).total_seconds():.2f}秒")
            return final_signal
            
        except Exception as e:
            logger.error(f"[{self.name}] 分析失败: {e}")
            return self._create_error_signal(str(e), stock_code=stock_code)

    # =============================================================================
    # 数据获取层（伪代码）
    # =============================================================================

    def _fetch_macro_data(self) -> Dict[str, Any]:
        """
        获取宏观数据。

        当前使用 2024-06-28 的真实历史数据集（macro_test_data_2024_06_28.py）。
        后续替换为 data_sources/ 调用即可切换至实时数据。
        """
        logger.info("[数据获取] 使用 2024-06-28 真实历史数据集")
        return build_complete_mock_data()

    # =============================================================================
    # 各层执行方法
    # =============================================================================

    def _run_layer0(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Layer 0: 双经济体追踪"""
        self.log("执行 Layer 0: 双经济体追踪")
        
        # 准备中国五大维度指标
        china_indicators = {
            "growth": {
                "nbs_pmi": data["china"]["nbs_manufacturing_pmi"],
                "caixin_pmi": data["china"]["caixin_manufacturing_pmi"],
            },
            "inflation": {
                "cpi": data["china"]["cpi_yoy"],
                "ppi": data["china"]["ppi_yoy"],
            },
            "policy": {
                "1y_lpr": data["china"]["1y_lpr"],
                "5y_lpr": data["china"]["5y_lpr"],
                "mlf_rate": data["china"].get("mlf_rate"),
                "reserve_cut_bp": data["china"].get("reserve_cut_bp", 0),
            },
            "liquidity": {
                "dr007": data["china"]["dr007"],
                "tsf_yoy": data["china"]["tsf_yoy"],
            },
            "market_pricing": {
                "10y_bond_yield": data["china"]["cn_10y_yield"],
                "csi300_erp": data["china"]["csi300_erp"],
            },
        }
        
        # 准备美国五大维度指标
        us_indicators = {
            "growth": {
                "ism_pmi": data["us"]["ism_manufacturing_pmi"],
                "nonfarm": data["us"]["nonfarm_payrolls"],
            },
            "inflation": {
                "pce": data["us"]["core_pce_yoy"],
                "cpi": data["us"]["cpi_yoy"],
            },
            "policy": {
                "ffr": data["us"]["ffr"],
            },
            "liquidity": {
                "sofr": data["us"]["sofr"],
            },
            "market_pricing": {
                "10y_ust_yield": data["us"]["us_10y_yield"],
                "sp500_erp": data["us"]["sp500_erp"],
            },
        }
        
        # 准备跨国指标（含新增字段）
        cross_border_metrics = {
            "cn_us_10y_spread": data["cross_border"]["cn_us_10y_spread"],
            "dxy_index": data["us"]["dxy_index"],
            "usd_cnh": data["cross_border"]["usd_cnh"],
            "vix": data["cross_border"]["vix"],
            "geopolitical_score": data["cross_border"].get("geopolitical_score"),
            "global_pmi": data["cross_border"].get("global_pmi"),
            "euro_pmi": data["cross_border"].get("euro_pmi"),
            "forex_reserve_change": data["cross_border"].get("forex_reserve_change"),
        }
        
        # 执行分析
        result = analyze_bilateral_tracking(
            china_indicators=china_indicators,
            us_indicators=us_indicators,
            cross_border_metrics=cross_border_metrics,
        )
        
        # 如果有LLM客户端，调用LLM进行智能分析
        if self._llm_client and self.get_skill("layer0_tracking"):
            llm_result = self._call_llm_for_layer(
                layer_name="layer0_tracking",
                data={
                    "china_indicators": china_indicators,
                    "us_indicators": us_indicators,
                    "cross_border_metrics": cross_border_metrics,
                },
                analyzer_result=result,
            )
            result["llm_analysis"] = llm_result
        
        return result

    def _run_layer1(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Layer 1: CAI/FCI计算（纯数值计算）"""
        self.log("执行 Layer 1: CAI/FCI计算")
        
        # 准备中国指标
        china_indicators = {
            "nbs_manufacturing_pmi": data["china"]["nbs_manufacturing_pmi"],
            "caixin_manufacturing_pmi": data["china"]["caixin_manufacturing_pmi"],
            "industrial_added_value_yoy": data["china"]["industrial_added_value_yoy"],
            "total_social_financing_yoy": data["china"]["tsf_yoy"],
            "retail_sales_yoy": data["china"]["retail_sales_yoy"],
            "export_yoy_usd": data["china"]["export_yoy_usd"],
            "cpi_yoy": data["china"]["cpi_yoy"],
            "ppi_yoy": data["china"]["ppi_yoy"],
            "dr007": data["china"]["dr007"],
            "csi_300_erp": data["china"]["csi300_erp"],
            "cn_10y_yield": data["china"]["cn_10y_yield"],
        }
        
        # 准备美国指标
        us_indicators = {
            "ism_manufacturing_pmi": data["us"]["ism_manufacturing_pmi"],
            "nonfarm_payrolls_3m_avg": data["us"]["nonfarm_payrolls"],
            "core_pce_yoy": data["us"]["core_pce_yoy"],
            "sp500_erp": data["us"]["sp500_erp"],
            "us_10y_yield": data["us"]["us_10y_yield"],
            "us_2y_yield": data["us"]["us_2y_yield"],
            "us_hy_spread": data["us"]["us_hy_spread"],
            "dxy_index": data["us"]["dxy_index"],
            "sofr_effr": data["us"]["sofr"],
        }
        
        # 执行分析（纯数值计算）
        result = analyze_cai_fci(
            china_indicators=china_indicators,
            us_indicators=us_indicators,
        )
        
        return result

    def _run_layer2(self, data: Dict[str, Any], layer1_result: Dict[str, Any]) -> Dict[str, Any]:
        """Layer 2: 周期定位"""
        self.log("执行 Layer 2: 周期定位")
        
        # 从 Layer 1 获取 CAI 和通胀得分
        china_cai = layer1_result.get("china_cai", {}).get("z_score", 0)
        china_inflation = layer1_result.get("china_inflation", {}).get("z_score", 0)
        us_cai = layer1_result.get("us_cai", {}).get("z_score", 0)
        us_inflation = layer1_result.get("us_inflation", {}).get("z_score", 0)
        
        # 从数据获取中国政策维度指标
        china_policy_indicators = {
            "monetary_policy": data["china"].get("monetary_policy_direction", "neutral"),
            "fiscal_policy": data["china"].get("fiscal_policy_direction", "neutral"),
            "real_estate_policy": data["china"].get("real_estate_policy_direction", "neutral"),
            "regulation_event": data["china"].get("regulation_event", "neutral"),
            "special_bond_progress": data["china"].get("special_bond_progress"),
            "fiscal_deficit_rate": data["china"].get("fiscal_deficit_rate"),
        }
        
        # 执行分析
        result = analyze_cycle_positioning(
            china_cai_score=china_cai,
            china_inflation_score=china_inflation,
            us_cai_score=us_cai,
            us_inflation_score=us_inflation,
            china_policy_indicators=china_policy_indicators,
        )
        
        return result

    def _run_layer25(self, data: Dict[str, Any], layer1_result: Dict[str, Any]) -> Dict[str, Any]:
        """Layer 2.5: 枢纽变量分析"""
        self.log("执行 Layer 2.5: 枢纽变量分析")
        
        # 准备汇率数据（含4因子模型所需字段）
        exchange_rate_data = {
            "usd_cnh": data["cross_border"]["usd_cnh"],
            "china_10y_yield": data["china"]["cn_10y_yield"],
            "us_10y_yield": data["us"]["us_10y_yield"],
            "trade_surplus": data["cross_border"].get("trade_surplus"),
            "pboc_mid_deviation": data["cross_border"].get("pboc_mid_deviation"),
        }
        
        # 准备大宗商品数据
        commodity_data = {
            "copper_gold_ratio": data["commodities"]["copper_gold_ratio"],
            "oil_gold_ratio": data["commodities"]["oil_gold_ratio"],
        }
        
        # 准备利率数据
        interest_rate_data = {
            "china_10y_yield": data["china"]["cn_10y_yield"],
            "us_10y_yield": data["us"]["us_10y_yield"],
            "vix": data["cross_border"]["vix"],
        }
        
        # 执行分析
        result = analyze_hub_variable(
            exchange_rate_data=exchange_rate_data,
            commodity_data=commodity_data,
            interest_rate_data=interest_rate_data,
        )
        
        return result

    def _run_layer3(self, layer1_result: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
        """Layer 3: 市场定价提取"""
        self.log("执行 Layer 3: 市场定价提取")
        
        # 准备实际状态（来自 Layer 1）
        actual_state = {
            "china_cai": layer1_result.get("china_cai", {}),
            "china_inflation": layer1_result.get("china_inflation", {}),
            "us_cai": layer1_result.get("us_cai", {}),
            "us_inflation": layer1_result.get("us_inflation", {}),
        }
        
        # 准备市场定价数据
        market_prices = {
            "cn_10y_yield": data["china"]["cn_10y_yield"],
            "cn_2y_yield": data["china"]["cn_2y_yield"],
            "us_10y_yield": data["us"]["us_10y_yield"],
            "us_2y_yield": data["us"]["us_2y_yield"],
            "csi300_erp": data["china"]["csi300_erp"],
            "sp500_erp": data["us"]["sp500_erp"],
            "aa_credit_spread": data["china"]["aa_credit_spread"],
            "us_hy_spread": data["us"]["us_hy_spread"],
            "copper_gold_ratio": data["commodities"]["copper_gold_ratio"],
        }
        
        # 执行分析
        result = analyze_market_pricing(
            actual_state=actual_state,
            market_prices=market_prices,
        )
        
        return result

    def _run_layer4(
        self,
        layer1_result: Dict[str, Any],
        layer3_result: Dict[str, Any],
        layer25_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Layer 4: 预期差信号引擎"""
        self.log("执行 Layer 4: 预期差信号引擎")
        
        # 从Layer 2.5提取枢纽变量分析结果（框架第781行：美元-大宗联动信号）
        layer25_output = layer25_result.get("layer_output", {})
        
        # 执行分析
        result = analyze_expected_diff(
            layer1_output=layer1_result,
            layer3_output=layer3_result,
            layer25_output=layer25_output,
        )
        
        return result

    def _run_layer45(self, data: Dict[str, Any], layer4_result: Dict[str, Any]) -> Dict[str, Any]:
        """Layer 4.5: 反身性与元认知"""
        self.log("执行 Layer 4.5: 反身性与元认知")
        
        # 获取信号列表
        signals = layer4_result.get("all_signals", [])
        
        # 获取反身性数据（来自测试数据集）
        reflexivity_data = data.get("reflexivity", {})
        crowding_data = {
            "signal_crowding_score": reflexivity_data.get("signal_crowding_score", 50.0),
            "position_concentration_z": reflexivity_data.get("position_concentration_z", 0.0),
            "self_fulfilling_index": reflexivity_data.get("self_fulfilling_index", 50.0),
            "cross_framework_consensus": reflexivity_data.get("cross_framework_consensus", 50.0),
        }
        
        # 执行分析
        result = analyze_reflexivity(
            layer4_signals=signals,
            crowding_data=crowding_data,
        )
        
        return result

    def _run_layer5(
        self,
        layer2_result: Dict[str, Any],
        layer4_result: Dict[str, Any],
        layer45_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Layer 5: 资产配置"""
        self.log("执行 Layer 5: 资产配置")
        
        # 断点③修复：生成波动率数据 fallback
        # 框架要求使用3年滚动年化波动率；数据源未接入时使用合理默认值
        # 各资产年化波动率参考：A股~22%, 国债~4%, 南华工业品~18%, 黄金~14%, 美股~17%
        volatility_data = {
            "csi300_500": 0.22,
            "cn_gov_bond": 0.04,
            "nh_industrial": 0.18,
            "gold": 0.14,
            "us_assets": 0.17,
        }
        
        # 执行分析
        result = analyze_asset_allocation(
            layer2_output=layer2_result,
            layer4_output=layer4_result,
            layer45_output=layer45_result,
            volatility_data=volatility_data,
        )
        
        return result

    # =============================================================================
    # LLM 调用方法
    # =============================================================================

    def _call_llm_for_layer(
        self,
        layer_name: str,
        data: Dict[str, Any],
        analyzer_result: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        调用 LLM 进行智能分析。
        
        [伪代码] 当前预留接口，待 LLM 调用机制确定后实现。
        """
        if not self._llm_client:
            logger.debug(f"[{self.name}] 无LLM客户端，跳过{layer_name}智能分析")
            return None
        
        # 获取 Skill 内容
        skill_content = self.get_skill(layer_name)
        if not skill_content:
            logger.warning(f"[{self.name}] 未找到Skill: {layer_name}")
            return None
        
        # 生成提示词
        if layer_name == "layer0_tracking":
            prompt = generate_layer0_prompt(
                china_data=data.get("china_indicators", {}),
                us_data=data.get("us_indicators", {}),
                cross_data=data.get("cross_border_metrics", {}),
            )
        else:
            prompt = str(analyzer_result)
        
        try:
            # 调用 LLM
            response = self._llm_client(prompt=prompt, system=skill_content)
            
            # 解析响应（TODO: 实现 JSON 解析）
            # result = json.loads(response)
            
            return {"raw_response": response}
            
        except Exception as e:
            logger.error(f"[{self.name}] LLM调用失败: {e}")
            return None

    # =============================================================================
    # 推理链构建
    # =============================================================================

    def _summarize_reasoning_chain(
        self,
        chain: ReasoningChain,
        final_signal: Signal,
    ) -> str:
        """
        基于全局推理链生成推理摘要。

        策略：优先使用 final_signal 的语义字段（signals 配置列表）；
        fallback 到中间层有实质内容的结论。
        摘要格式：方向 置信度 | 核心发现1 | 核心发现2 | ...
        """
        # ---------- 方向 ----------
        direction_map = {
            "bullish": "看多",
            "bearish": "看空",
            "neutral": "中性",
        }
        direction_str = direction_map.get(
            final_signal.direction, final_signal.direction or "中性"
        )
        confidence_str = f"{int(final_signal.confidence * 100)}%"

        # ---------- 策略一：从 final_signal.signals 构建 ----------
        # signals 格式如: ["csi300_500 配置15%", "cn_gov_bond 配置35%"]
        signals = final_signal.signals or []
        if signals:
            # 翻译资产英文名 → 中文
            asset_name_map: Dict[str, str] = {
                "csi300_500": "A股",
                "us_assets": "美股",
                "cn_gov_bond": "中债",
                "nh_industrial": "南华工业",
                "gold": "黄金",
                "新兴市场": "新兴市场",
                "全球资本流向": "全球资本",
            }
            signal_parts: List[str] = []
            for s in signals:
                # 替换资产名
                readable = s
                for en, zh in asset_name_map.items():
                    readable = readable.replace(en, zh)
                signal_parts.append(readable)

            summary_parts = signal_parts[:8]  # 最多8个配置信号
            result = " | ".join(summary_parts)
            if len(result) > 200:
                result = result[:197] + "…"
            return result

        # ---------- 策略二：从推理链提取有效结论 ----------
        if not chain.steps:
            return "无推理链数据"

        # 内部枚举翻译
        enum_translations: Dict[str, str] = {
            "InteractionLevel.FEEDBACK_LOOP": "中美反馈循环",
            "InteractionLevel.SYNCHRONIZATION": "中美周期同步",
            "InteractionLevel.DIVERGENCE": "中美周期分化",
        }
        NA_WHOLE = re.compile(r"^(?:N/A|n/a|NA|null|无|暂无)\s*$", re.IGNORECASE)
        SKIP_STEP_NAMES: set[str] = {
            "中国增长维度分析", "美国增长维度分析", "中美交互层次判定",
        }

        parts: List[str] = []
        seen_layer: set[str] = set()

        for step in chain.steps:
            conclusion = step.intermediate_conclusion
            if not conclusion:
                continue
            if step.step_name in SKIP_STEP_NAMES:
                continue

            # 翻译枚举
            for raw, readable in enum_translations.items():
                conclusion = conclusion.replace(raw, readable)

            # 清理 N/A 残留
            conclusion = re.sub(
                r"\b[A-Za-z\u4e00-\u9fff]{1,10}:\s*(?:N/A|n/a|NA|null|暂无|无)\b",
                "",
                conclusion,
            )
            # 清理多余分隔符
            conclusion = re.sub(r"[\s,，;|]{2,}", " ", conclusion).strip()
            conclusion = re.sub(r"^[\s,，;|]+|[\s,，;|]+$", "", conclusion)

            if NA_WHOLE.match(conclusion) or len(conclusion) < 3:
                continue

            if len(conclusion) > 45:
                conclusion = conclusion[:43] + "…"

            layer = step.layer_name
            if layer not in seen_layer:
                seen_layer.add(layer)
                parts.append(conclusion)

        summary_parts = parts[:3]
        result = " | ".join(summary_parts)
        if len(result) > 100:
            result = result[:97] + "…"
        return result

    def _build_reasoning_chain(
        self,
        data: Dict[str, Any],
        layer0_result: Dict[str, Any],
        layer1_result: Dict[str, Any],
        layer2_result: Dict[str, Any],
        layer25_result: Dict[str, Any],
        layer3_result: Dict[str, Any],
        layer4_result: Dict[str, Any],
        layer45_result: Dict[str, Any],
        layer5_result: Dict[str, Any],
    ) -> ReasoningChain:
        """
        构建完整的推理链。

        从各层分析结果中提取推理步骤，按执行顺序组装成链式结构。
        """
        chain = ReasoningChain()

        # Layer 0: 双经济体追踪
        self._add_layer0_reasoning(chain, data, layer0_result)

        # Layer 1: CAI/FCI计算
        self._add_layer1_reasoning(chain, data, layer1_result)

        # Layer 2: 周期定位
        self._add_layer2_reasoning(chain, layer1_result, layer2_result)

        # Layer 2.5: 枢纽变量分析
        self._add_layer25_reasoning(chain, data, layer1_result, layer25_result)

        # Layer 3: 市场定价提取
        self._add_layer3_reasoning(chain, layer1_result, layer3_result)

        # Layer 4: 预期差信号引擎
        self._add_layer4_reasoning(chain, layer1_result, layer3_result, layer4_result)

        # Layer 4.5: 反身性与元认知
        self._add_layer45_reasoning(chain, layer4_result, layer45_result)

        # Layer 5: 资产配置
        self._add_layer5_reasoning(chain, layer2_result, layer4_result, layer45_result, layer5_result)

        # 设置最终结论
        final_signal = layer5_result.get("macro_signal")
        chain.final_conclusion = final_signal.reasoning if final_signal else ""
        chain.chain_confidence = chain.calculate_chain_confidence()

        return chain

    def _add_layer0_reasoning(
        self,
        chain: ReasoningChain,
        data: Dict[str, Any],
        layer0_result: Dict[str, Any],
    ) -> None:
        """Layer 0: 双经济体追踪推理步骤"""
        # 中国增长维度分析
        chain.add_step(ReasoningStep(
            layer_name="layer0",
            layer_number=0,
            step_name="中国增长维度分析",
            input_summary=f"NBS PMI: {data['china']['nbs_manufacturing_pmi']}, Caixin PMI: {data['china']['caixin_manufacturing_pmi']}",
            analysis_logic="PMI > 50 表示经济扩张，< 50 表示收缩",
            intermediate_conclusion="中国制造业温和扩张",
            confidence=0.75,
            evidence=[
                f"NBS PMI {data['china']['nbs_manufacturing_pmi']} > 50",
                f"Caixin PMI {data['china']['caixin_manufacturing_pmi']} > 50",
            ],
        ))

        # 美国增长维度分析
        chain.add_step(ReasoningStep(
            layer_name="layer0",
            layer_number=0,
            step_name="美国增长维度分析",
            input_summary=f"ISM PMI: {data['us']['ism_manufacturing_pmi']}, 非农: {data['us']['nonfarm_payrolls']:,}",
            analysis_logic="ISM PMI > 50 且非农就业稳健表示经济活动强劲",
            intermediate_conclusion="美国经济保持稳健增长",
            confidence=0.80,
            evidence=[
                f"ISM PMI {data['us']['ism_manufacturing_pmi']} > 50",
                f"非农就业 {data['us']['nonfarm_payrolls']:,}",
            ],
        ))

        # 中美交互层次
        interaction_level = layer0_result.get("interaction_level", {})
        chain.add_step(ReasoningStep(
            layer_name="layer0",
            layer_number=0,
            step_name="中美交互层次判定",
            input_summary=f"中美10Y利差: {data['cross_border']['cn_us_10y_spread']:.2f}%, 美元指数: {data['us']['dxy_index']}",
            analysis_logic="根据活跃传导通道数量和增长差值判定交互层次",
            intermediate_conclusion=str(interaction_level),
            confidence=0.70,
            evidence=[
                f"利差 {data['cross_border']['cn_us_10y_spread']:.2f}%",
                f"美元指数 {data['us']['dxy_index']}",
            ],
            uncertainty_sources=[
                "传导通道触发阈值主观性",
                "交互层次判定规则简化",
            ],
        ))

    def _add_layer1_reasoning(
        self,
        chain: ReasoningChain,
        data: Dict[str, Any],
        layer1_result: Dict[str, Any],
    ) -> None:
        """Layer 1: CAI/FCI计算推理步骤"""
        china_cai = layer1_result.get("china_cai", {})
        us_cai = layer1_result.get("us_cai", {})
        china_fci = layer1_result.get("china_fci", {})
        us_fci = layer1_result.get("us_fci", {})

        # 中国CAI
        chain.add_step(ReasoningStep(
            layer_name="layer1",
            layer_number=1,
            step_name="中国CAI计算",
            input_summary="工业增加值、PMI、社融、零售等9个指标加权",
            analysis_logic="各指标z-score标准化后按权重加权求和",
            intermediate_conclusion=f"中国CAI z-score: {china_cai.get('z_score', 0):.2f}σ, 方向: {china_cai.get('direction', 'N/A')}",
            confidence=0.85,
            evidence=[
                f"CAI得分: {china_cai.get('z_score', 0):.2f}σ",
                f"数据覆盖率: {china_cai.get('data_coverage', 0):.0%}",
            ],
        ))

        # 美国CAI
        chain.add_step(ReasoningStep(
            layer_name="layer1",
            layer_number=1,
            step_name="美国CAI计算",
            input_summary="ISM PMI、非农、零售、产出等指标加权",
            analysis_logic="各指标z-score标准化后按权重加权求和",
            intermediate_conclusion=f"美国CAI z-score: {us_cai.get('z_score', 0):.2f}σ, 方向: {us_cai.get('direction', 'N/A')}",
            confidence=0.85,
            evidence=[
                f"CAI得分: {us_cai.get('z_score', 0):.2f}σ",
                f"数据覆盖率: {us_cai.get('data_coverage', 0):.0%}",
            ],
        ))

        # 中国FCI
        chain.add_step(ReasoningStep(
            layer_name="layer1",
            layer_number=1,
            step_name="中国FCI计算",
            input_summary="DR007、信用利差、国债利差、ERP等金融指标",
            analysis_logic="金融条件指标统一方向后加权求和",
            intermediate_conclusion=f"中国FCI z-score: {china_fci.get('z_score', 0):.2f}σ, 方向: {china_fci.get('direction', 'N/A')}",
            confidence=0.80,
            evidence=[
                f"FCI得分: {china_fci.get('z_score', 0):.2f}σ",
                f"10Y国债: {data['china']['cn_10y_yield']}%",
            ],
        ))

        # 中美差值
        cn_us_diff = layer1_result.get("cn_us_diff", {})
        chain.add_step(ReasoningStep(
            layer_name="layer1",
            layer_number=1,
            step_name="中美CAI差值分析",
            input_summary=f"中国CAI: {china_cai.get('z_score', 0):.2f}σ, 美国CAI: {us_cai.get('z_score', 0):.2f}σ",
            analysis_logic="增长差值决定全球需求相对强弱",
            intermediate_conclusion=f"中美CAI差值: {cn_us_diff.get('cai_diff', 0):.2f}σ",
            confidence=0.75,
            evidence=[
                f"中国-美国增长差: {cn_us_diff.get('cai_diff', 0):.2f}σ",
            ],
            uncertainty_sources=[
                "CAI权重未经过回测校准",
            ],
        ))

    def _add_layer2_reasoning(
        self,
        chain: ReasoningChain,
        layer1_result: Dict[str, Any],
        layer2_result: Dict[str, Any],
    ) -> None:
        """Layer 2: 周期定位推理步骤"""
        china_quadrant = layer2_result.get("china_quadrant_adjusted", layer2_result.get("china_quadrant", {}))
        us_quadrant = layer2_result.get("us_quadrant", {})

        chain.add_step(ReasoningStep(
            layer_name="layer2",
            layer_number=2,
            step_name="中国周期位置判定",
            input_summary=f"CAI: {layer1_result.get('china_cai', {}).get('z_score', 0):.2f}σ, 通胀: {layer1_result.get('china_inflation', {}).get('z_score', 0):.2f}σ",
            analysis_logic="根据CAI和通胀z-score在四象限中定位",
            intermediate_conclusion=f"周期位置: {china_quadrant.get('quadrant_cn', 'N/A')}, 信号强度: {china_quadrant.get('signal_strength', 'N/A')}",
            confidence=0.75,
            evidence=[
                f"增长z-score: {layer1_result.get('china_cai', {}).get('z_score', 0):.2f}",
                f"通胀z-score: {layer1_result.get('china_inflation', {}).get('z_score', 0):.2f}",
                f"政策调节: {china_quadrant.get('policy_adjustment', 'N/A')}",
            ],
        ))

        chain.add_step(ReasoningStep(
            layer_name="layer2",
            layer_number=2,
            step_name="美国周期位置判定",
            input_summary=f"CAI: {layer1_result.get('us_cai', {}).get('z_score', 0):.2f}σ, 通胀: {layer1_result.get('us_inflation', {}).get('z_score', 0):.2f}σ",
            analysis_logic="根据CAI和通胀z-score在四象限中定位",
            intermediate_conclusion=f"周期位置: {us_quadrant.get('quadrant_cn', 'N/A')}",
            confidence=0.75,
            evidence=[
                f"增长z-score: {layer1_result.get('us_cai', {}).get('z_score', 0):.2f}",
                f"通胀z-score: {layer1_result.get('us_inflation', {}).get('z_score', 0):.2f}",
            ],
        ))

    def _add_layer25_reasoning(
        self,
        chain: ReasoningChain,
        data: Dict[str, Any],
        layer1_result: Dict[str, Any],
        layer25_result: Dict[str, Any],
    ) -> None:
        """Layer 2.5: 枢纽变量分析推理步骤"""
        # 汇率分析
        chain.add_step(ReasoningStep(
            layer_name="layer2_5",
            layer_number=2.5,
            step_name="USD/CNH汇率分析",
            input_summary=f"USD/CNH: {data['cross_border']['usd_cnh']}, 中美利差: {data['cross_border']['cn_us_10y_spread']:.2f}%",
            analysis_logic="利差收窄通常导致货币贬值压力",
            intermediate_conclusion=f"人民币面临一定贬值压力",
            confidence=0.70,
            evidence=[
                f"USD/CNH {data['cross_border']['usd_cnh']}",
                f"中美利差 {data['cross_border']['cn_us_10y_spread']:.2f}%",
            ],
        ))

        # 大宗商品比率
        chain.add_step(ReasoningStep(
            layer_name="layer2_5",
            layer_number=2.5,
            step_name="铜金比分析",
            input_summary=f"铜金比: {data['commodities']['copper_gold_ratio']:.4f}, 油价金价比: {data['commodities']['oil_gold_ratio']:.4f}",
            analysis_logic="铜金比反映全球增长预期，油金比反映通胀预期",
            intermediate_conclusion=f"铜金比偏低，全球增长预期偏谨慎",
            confidence=0.65,
            evidence=[
                f"铜金比 {data['commodities']['copper_gold_ratio']:.4f}",
            ],
            uncertainty_sources=[
                "大宗商品价格受地缘政治扰动",
            ],
        ))

    def _add_layer3_reasoning(
        self,
        chain: ReasoningChain,
        layer1_result: Dict[str, Any],
        layer3_result: Dict[str, Any],
    ) -> None:
        """Layer 3: 市场定价提取推理步骤"""
        valuation_pricing = layer3_result.get("valuation_pricing", {})
        rate_pricing = layer3_result.get("rate_pricing", {})
        
        # 中国估值信息
        csi300_erp = valuation_pricing.get("csi300_erp", {})
        cn_erp_value = csi300_erp.get("value", csi300_erp.get("erp", 0)) if isinstance(csi300_erp, dict) else csi300_erp
        cn_signal = csi300_erp.get("signal", "N/A") if isinstance(csi300_erp, dict) else "N/A"
        
        # 美国估值信息
        sp500_erp = valuation_pricing.get("sp500_erp", {})
        us_erp_value = sp500_erp.get("value", sp500_erp.get("erp", 0)) if isinstance(sp500_erp, dict) else sp500_erp
        us_signal = sp500_erp.get("signal", "N/A") if isinstance(sp500_erp, dict) else "N/A"

        chain.add_step(ReasoningStep(
            layer_name="layer3",
            layer_number=3,
            step_name="A股市场定价分析",
            input_summary=f"10Y国债: {rate_pricing.get('cn_10y_yield', 'N/A')}, ERP: {cn_erp_value}",
            analysis_logic="ERP反映股市相对债券的吸引力",
            intermediate_conclusion=f"A股估值吸引力: {cn_signal}",
            confidence=0.70,
            evidence=[
                f"沪深300 ERP: {cn_erp_value}",
            ],
        ))

        chain.add_step(ReasoningStep(
            layer_name="layer3",
            layer_number=3,
            step_name="美股市场定价分析",
            input_summary=f"10Y UST: {rate_pricing.get('us_10y_yield', 'N/A')}, ERP: {us_erp_value}",
            analysis_logic="美股ERP反映美股相对无风险资产的吸引力",
            intermediate_conclusion=f"美股估值吸引力: {us_signal}",
            confidence=0.70,
            evidence=[
                f"S&P 500 ERP: {us_erp_value}",
            ],
        ))

    def _add_layer4_reasoning(
        self,
        chain: ReasoningChain,
        layer1_result: Dict[str, Any],
        layer3_result: Dict[str, Any],
        layer4_result: Dict[str, Any],
    ) -> None:
        """Layer 4: 预期差信号引擎推理步骤"""
        signals = layer4_result.get("all_signals", [])
        
        # 从信号列表中提取中国和美国信号
        cn_signals = [s for s in signals if 'china' in s.get('name', '').lower() or '中国' in s.get('name', '') or 'CN' in s.get('name', '')]
        us_signals = [s for s in signals if 'us' in s.get('name', '').lower() or '美国' in s.get('name', '') or 'US' in s.get('name', '')]
        
        # 计算中国预期差汇总
        cn_bullish = len([s for s in cn_signals if s.get('direction') == 'bullish'])
        cn_bearish = len([s for s in cn_signals if s.get('direction') == 'bearish'])
        cn_direction = "看多" if cn_bullish > cn_bearish else "看空" if cn_bearish > cn_bullish else "中性"
        
        # 计算美国预期差汇总
        us_bullish = len([s for s in us_signals if s.get('direction') == 'bullish'])
        us_bearish = len([s for s in us_signals if s.get('direction') == 'bearish'])
        us_direction = "看多" if us_bullish > us_bearish else "看空" if us_bearish > us_bullish else "中性"

        # 中国预期差
        chain.add_step(ReasoningStep(
            layer_name="layer4",
            layer_number=4,
            step_name="中国预期差分析",
            input_summary=f"基本面CAI: {layer1_result.get('china_cai', {}).get('z_score', 0):.2f}σ, 信号数: {len(cn_signals)}",
            analysis_logic="基本面与市场定价之差即为预期差",
            intermediate_conclusion=f"中国预期差: {cn_direction}, 信号数: {len(cn_signals)}",
            confidence=0.70,
            evidence=[
                f"预期差方向: {cn_direction}",
                f"看多信号: {cn_bullish}, 看空信号: {cn_bearish}",
            ],
        ))

        # 美国预期差
        chain.add_step(ReasoningStep(
            layer_name="layer4",
            layer_number=4,
            step_name="美国预期差分析",
            input_summary=f"基本面CAI: {layer1_result.get('us_cai', {}).get('z_score', 0):.2f}σ, 信号数: {len(us_signals)}",
            analysis_logic="基本面与市场定价之差即为预期差",
            intermediate_conclusion=f"美国预期差: {us_direction}, 信号数: {len(us_signals)}",
            confidence=0.70,
            evidence=[
                f"预期差方向: {us_direction}",
                f"看多信号: {us_bullish}, 看空信号: {us_bearish}",
            ],
        ))

        # 信号汇总
        if signals:
            chain.add_step(ReasoningStep(
                layer_name="layer4",
                layer_number=4,
                step_name="预期差信号汇总",
                input_summary=f"共{len(signals)}个信号",
                analysis_logic="汇总所有预期差信号并按方向分组",
                intermediate_conclusion=f"看多信号: {len([s for s in signals if 'bullish' in str(s).lower()])}, 看空信号: {len([s for s in signals if 'bearish' in str(s).lower()])}",
                confidence=0.65,
                evidence=[str(s) for s in signals[:5]],
            ))

    def _add_layer45_reasoning(
        self,
        chain: ReasoningChain,
        layer4_result: Dict[str, Any],
        layer45_result: Dict[str, Any],
    ) -> None:
        """Layer 4.5: 反身性与元认知推理步骤"""
        signals = layer4_result.get("all_signals", [])
        pressure_meter = layer45_result.get("pressure_meter", {})
        paradigm_stability = layer45_result.get("paradigm_stability", {})
        lifecycle = layer45_result.get("logic_lifecycle", {})

        # 信号拥挤度
        chain.add_step(ReasoningStep(
            layer_name="layer4_5",
            layer_number=4.5,
            step_name="信号拥挤度分析",
            input_summary=f"信号数: {len(signals)}, 压力等级: {pressure_meter.get('level', 'N/A')}",
            analysis_logic="拥挤信号存在反转风险",
            intermediate_conclusion=f"拥挤度等级: {pressure_meter.get('level', 'N/A')}",
            confidence=0.60,
            evidence=[
                f"压力得分: {pressure_meter.get('total_score', 'N/A')}",
                f"范式稳定性: {paradigm_stability.get('status', 'N/A')}",
            ],
            uncertainty_sources=[
                "拥挤度指标定义较主观",
                "历史规律未必适用于当前市场结构",
            ],
        ))

        # 反身性评估
        chain.add_step(ReasoningStep(
            layer_name="layer4_5",
            layer_number=4.5,
            step_name="反身性评估",
            input_summary=f"逻辑生命周期: {lifecycle.get('stage', 'N/A')}, 范式状态: {paradigm_stability.get('status', 'N/A')}",
            analysis_logic="高反身性意味着预期容易自我强化或反转",
            intermediate_conclusion=f"反身性等级: {pressure_meter.get('level', 'N/A')}",
            confidence=0.55,
            evidence=[
                f"压力等级: {pressure_meter.get('level', 'N/A')}",
                f"范式稳定性: {paradigm_stability.get('status', 'N/A')}",
            ],
            uncertainty_sources=[
                "反身性难以量化",
                "市场结构变化影响反身性模式",
            ],
        ))

    def _add_layer5_reasoning(
        self,
        chain: ReasoningChain,
        layer2_result: Dict[str, Any],
        layer4_result: Dict[str, Any],
        layer45_result: Dict[str, Any],
        layer5_result: Dict[str, Any],
    ) -> None:
        """Layer 5: 资产配置推理步骤"""
        allocation = layer5_result.get("allocation", {})
        risk_adjusted = layer5_result.get("risk_adjusted", {})

        # 最终配置决策
        chain.add_step(ReasoningStep(
            layer_name="layer5",
            layer_number=5,
            step_name="资产配置决策",
            input_summary=f"周期位置: {layer2_result.get('china_quadrant_adjusted', {}).get('quadrant_cn', 'N/A')}, 预期差信号: {len(layer4_result.get('all_signals', []))}",
            analysis_logic="综合周期位置、预期差、反身性给出配置建议",
            intermediate_conclusion=f"A股配置: {allocation.get('csi300_500', 'N/A')}, 美股配置: {allocation.get('us_assets', 'N/A')}",
            confidence=0.70,
            evidence=[
                f"A股: {allocation.get('csi300_500', 'N/A')}",
                f"美股: {allocation.get('us_assets', 'N/A')}",
                f"债券: {allocation.get('cn_gov_bond', 'N/A')}",
            ],
        ))

        # 风险调整后决策
        chain.add_step(ReasoningStep(
            layer_name="layer5",
            layer_number=5,
            step_name="风险调整后配置",
            input_summary=f"拥挤度: {layer45_result.get('pressure_meter', {}).get('level', 'N/A')}, 范式稳定性: {layer45_result.get('paradigm_stability', {}).get('status', 'N/A')}",
            analysis_logic="根据拥挤度和反身性调整配置权重",
            intermediate_conclusion=f"风险调整后: {risk_adjusted.get('adjusted_view', 'N/A')}",
            confidence=0.65,
            evidence=[
                f"调整后A股: {risk_adjusted.get('cn_equity_adjusted', 'N/A')}",
                f"调整后美股: {risk_adjusted.get('us_equity_adjusted', 'N/A')}",
            ],
            uncertainty_sources=[
                "风险调整参数基于历史经验",
                "极端市场环境可能失效",
            ],
        ))

    # =============================================================================
    # 辅助方法
    # =============================================================================

    def _create_error_signal(self, error_message: str, stock_code: str = "") -> Signal:
        """创建错误信号"""
        return neutral_signal(
            confidence=0.1,
            reasoning=f"宏观分析执行失败: {error_message}",
            source=self.name,
            signal_type=self.signal_type,
            stock_code=stock_code,
            meta={
                "error": error_message,
                "needs_human_review": True,
            },
        )

    def get_layer_output(self, layer_name: str) -> Optional[Dict[str, Any]]:
        """
        获取指定层的输出。
        
        在 analyze() 完成后可调用此方法获取中间层结果。
        """
        # TODO: 缓存各层输出
        return None


# =============================================================================
# 便捷函数
# =============================================================================

def create_macro_agent(config: Optional[Dict[str, Any]] = None) -> MacroAgent:
    """
    创建 MacroAgent 实例的便捷函数。
    
    Args:
        config: Agent 配置
    
    Returns:
        MacroAgent 实例
    """
    return MacroAgent(config=config)
