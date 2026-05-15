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

# =============================================================================
# Agent 实现
# =============================================================================

class MacroAgent(BaseAgent):
    """
    宏观分析 Agent（专家4组）

    实现7层流水线分析，按顺序调用各层脚本，最终输出标准化 Signal。
    
    数据获取由 Agent 负责，当前使用伪代码+模拟数据预留。
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

    def analyze(self, query: str = None, period: str = None) -> Signal:
        """
        执行7层流水线分析。

        Args:
            query: 分析查询（可选，用于决定分析重点）
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
            layer2_result = self._run_layer2(layer1_result)
            
            # Step 5: Layer 2.5 - 枢纽变量分析
            layer25_result = self._run_layer25(data, layer1_result)
            
            # Step 6: Layer 3 - 市场定价提取
            layer3_result = self._run_layer3(layer1_result, data)
            
            # Step 7: Layer 4 - 预期差信号引擎
            layer4_result = self._run_layer4(layer1_result, layer3_result)
            
            # Step 8: Layer 4.5 - 反身性与元认知
            layer45_result = self._run_layer45(layer4_result)
            
            # Step 9: Layer 5 - 资产配置
            layer5_result = self._run_layer5(layer2_result, layer4_result, layer45_result)
            
            # 汇总最终 Signal
            final_signal = layer5_result.get("macro_signal")
            
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
            
            self.log(f"宏观分析完成，耗时{(datetime.now() - start_time).total_seconds():.2f}秒")
            return final_signal
            
        except Exception as e:
            logger.error(f"[{self.name}] 分析失败: {e}")
            return self._create_error_signal(str(e))

    # =============================================================================
    # 数据获取层（伪代码）
    # =============================================================================

    def _fetch_macro_data(self) -> Dict[str, Any]:
        """
        获取宏观数据。
        
        [伪代码] 当前使用模拟数据，预留真实数据获取接口。
        
        TODO: 实现真实数据获取
        1. 调用 data_sources/macro_indicators.py 获取真实数据
        2. 或直接调用 akshare 库获取宏观数据
        3. 补充完整的中国/美国宏观指标数据
        """
        logger.info("[数据获取] 使用模拟数据（TODO: 实现真实数据获取）")
        
        # 模拟数据
        data = {
            "_is_mock": True,
            
            # ===== 中国数据 =====
            "china": {
                # 增长维度
                "nbs_manufacturing_pmi": 50.2,
                "caixin_manufacturing_pmi": 51.0,
                "industrial_added_value_yoy": 6.5,
                "gdp_yoy": 5.3,
                "retail_sales_yoy": 8.5,
                "export_yoy_usd": 5.0,
                
                # 通胀维度
                "cpi_yoy": 0.3,
                "ppi_yoy": -2.5,
                
                # 信用维度
                "tsf_yoy": 9.5,
                "m1_yoy": 5.0,
                "m2_yoy": 10.5,
                
                # 政策维度
                "1y_lpr": 3.45,
                "5y_lpr": 4.20,
                "dr007": 1.8,
                
                # 市场定价
                "cn_10y_yield": 2.52,
                "cn_2y_yield": 2.05,
                "csi300_erp": 5.2,
                "aa_credit_spread": 0.65,
            },
            
            # ===== 美国数据 =====
            "us": {
                # 增长维度
                "ism_manufacturing_pmi": 52.0,
                "nonfarm_payrolls": 180000,
                "us_unemployment_rate": 3.9,
                "gdp_growth": 2.5,
                
                # 通胀维度
                "core_pce_yoy": 2.8,
                "cpi_yoy": 3.4,
                
                # 政策维度
                "ffr": 5.25,
                "fed_total_assets": 7400000000000,
                
                # 流动性维度
                "sofr": 5.30,
                "m2_yoy": -3.0,
                
                # 市场定价
                "us_10y_yield": 4.25,
                "us_2y_yield": 4.95,
                "sp500_erp": 2.1,
                "us_hy_spread": 3.8,
                "dxy_index": 105.5,
            },
            
            # ===== 跨国指标 =====
            "cross_border": {
                "cn_us_10y_spread": -1.73,  # 2.52 - 4.25
                "usd_cnh": 7.25,
                "vix": 15.0,
                "copper_price": 9500,
                "gold_price": 2350,
                "brent_oil": 85,
            },
            
            # ===== 大宗商品 =====
            "commodities": {
                "copper_gold_ratio": 9500 / 2350,  # ≈ 0.04
                "oil_gold_ratio": 85 / 2350,  # ≈ 0.036
                "copper_price": 9500,
                "gold_price": 2350,
                "iron_ore_price": 120,
            },
            
            # ===== Layer 4.5 反身性数据（可选）=====
            "reflexivity": {
                "signal_crowding": 35,
                "position_concentration": 1.2,  # z-score
                "self_fulfilling_index": 45,
                "cross_framework_consensus": 55,
            },
        }
        
        return data

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
        
        # 准备跨国指标
        cross_border_metrics = {
            "cn_us_10y_spread": data["cross_border"]["cn_us_10y_spread"],
            "dxy_index": data["us"]["dxy_index"],
            "usd_cnh": data["cross_border"]["usd_cnh"],
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

    def _run_layer2(self, layer1_result: Dict[str, Any]) -> Dict[str, Any]:
        """Layer 2: 周期定位"""
        self.log("执行 Layer 2: 周期定位")
        
        # 从 Layer 1 获取 CAI 和通胀得分
        china_cai = layer1_result.get("china_cai", {}).get("z_score", 0)
        china_inflation = layer1_result.get("china_inflation", {}).get("z_score", 0)
        us_cai = layer1_result.get("us_cai", {}).get("z_score", 0)
        us_inflation = layer1_result.get("us_inflation", {}).get("z_score", 0)
        
        # 执行分析
        result = analyze_cycle_positioning(
            china_cai_score=china_cai,
            china_inflation_score=china_inflation,
            us_cai_score=us_cai,
            us_inflation_score=us_inflation,
        )
        
        return result

    def _run_layer25(self, data: Dict[str, Any], layer1_result: Dict[str, Any]) -> Dict[str, Any]:
        """Layer 2.5: 枢纽变量分析"""
        self.log("执行 Layer 2.5: 枢纽变量分析")
        
        # 准备汇率数据
        exchange_rate_data = {
            "usd_cnh": data["cross_border"]["usd_cnh"],
            "china_10y_yield": data["china"]["cn_10y_yield"],
            "us_10y_yield": data["us"]["us_10y_yield"],
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

    def _run_layer4(self, layer1_result: Dict[str, Any], layer3_result: Dict[str, Any]) -> Dict[str, Any]:
        """Layer 4: 预期差信号引擎"""
        self.log("执行 Layer 4: 预期差信号引擎")
        
        # 执行分析
        result = analyze_expected_diff(
            layer1_output=layer1_result,
            layer3_output=layer3_result,
        )
        
        return result

    def _run_layer45(self, layer4_result: Dict[str, Any]) -> Dict[str, Any]:
        """Layer 4.5: 反身性与元认知"""
        self.log("执行 Layer 4.5: 反身性与元认知")
        
        # 获取信号列表
        signals = layer4_result.get("all_signals", [])
        
        # 获取反身性数据
        reflexivity_data = {}  # TODO: 从 data 获取
        
        # 执行分析
        result = analyze_reflexivity(
            layer4_signals=signals,
            crowding_data=reflexivity_data,
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
        
        # 执行分析
        result = analyze_asset_allocation(
            layer2_output=layer2_result,
            layer4_output=layer4_result,
            layer45_output=layer45_result,
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
    # 辅助方法
    # =============================================================================

    def _create_error_signal(self, error_message: str) -> Signal:
        """创建错误信号"""
        return neutral_signal(
            confidence=0.1,
            reasoning=f"宏观分析执行失败: {error_message}",
            source=self.name,
            signal_type=self.signal_type,
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
