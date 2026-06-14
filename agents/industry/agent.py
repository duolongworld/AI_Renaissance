"""
行业景气 Agent - 专家5组

signal_type: industry
Skill 域: skills/industry/
核心能力：产业链景气度、行业拐点、竞争格局

数据获取原则（与项目规则对齐）：
- 真实 fetching / parsing / provider 逻辑放在 data_sources/ 层
- Agent 只调用 data_sources 接口，不直接联网抓数
- 当前使用 data_sources.industrial_sentinel.IndustrialSentinelDataSource
  （封装 IndustrySentiment + EastMoney，带缓存降级）
"""

from pathlib import Path
from typing import Optional
from agents.base import BaseAgent
from agents.signal import Signal, neutral_signal

try:
    from skills.industry.industrial_sentinel.runtime import run_industrial_sentinel
except Exception:
    run_industrial_sentinel = None

# 项目共用复合数据源（data_sources/ 层封装，带缓存降级）
try:
    from data_sources.industrial_sentinel import IndustrialSentinelDataSource
except Exception:
    IndustrialSentinelDataSource = None


SUPPORTED_INDUSTRY_PRESETS = {
    "ai-energy",
    "ai-chip",
    "semiconductor-equipment",
    "storage",
    "optical-module",
    "ai-infrastructure",
    "pcb",
    "ai-model",
    "robotics",
    "generic",
}


def _normalize_industry_input(raw_input: str) -> dict:
    """Classify user input before calling data sources or the Skill runtime."""
    value = str(raw_input or "").strip()
    context = {
        "raw_input": value,
        "analysis_input": value,
        "data_source_input": value,
        "input_type": "stock_code",
        "preset": None,
        "use_data_source": True,
    }
    if not value:
        context["input_type"] = "unknown"
        context["use_data_source"] = False
        return context

    try:
        from skills.industry.industrial_sentinel.core.auto_detect_preset import (
            _is_stock_code,
            _normalize_a_stock_code,
            _resolve_input,
            auto_detect_preset,
            match_preset_by_industry,
        )
    except Exception:
        return context

    lowered = value.lower()
    data_dir = (
        Path(__file__).resolve().parents[2]
        / "skills"
        / "industry"
        / "industrial_sentinel"
        / "data"
    )

    if lowered in SUPPORTED_INDUSTRY_PRESETS:
        context.update(
            {
                "input_type": "preset",
                "preset": lowered,
                "use_data_source": False,
            }
        )
        return context

    if _is_stock_code(value):
        normalized_code = _normalize_a_stock_code(value.upper())
        context["analysis_input"] = normalized_code
        context["data_source_input"] = normalized_code
        context["preset"] = auto_detect_preset(
            normalized_code,
            data_dir,
            allow_provider_lookup=False,
        )
        return context

    resolved = _resolve_input(value)
    if _is_stock_code(resolved):
        context.update(
            {
                "analysis_input": resolved,
                "data_source_input": resolved,
                "input_type": "stock_name",
                "stock_name": value,
                "preset": auto_detect_preset(
                    resolved,
                    data_dir,
                    allow_provider_lookup=False,
                ),
            }
        )
        return context

    preset = (
        auto_detect_preset(value, data_dir, allow_provider_lookup=False)
        or match_preset_by_industry(value)
    )
    context.update(
        {
            "input_type": "industry" if preset else "unknown",
            "preset": preset,
            "use_data_source": False,
        }
    )
    return context


def _build_preset_only_industry_result(raw_input: str, preset: str) -> dict:
    """Build a framework-only industry payload from local preset routing."""
    industry_name = raw_input
    try:
        from skills.industry.industrial_sentinel.core.pipeline import load_preset_yaml

        yaml_data = load_preset_yaml(preset)
        if isinstance(yaml_data, dict):
            industry_name = yaml_data.get("industry_name") or yaml_data.get("chain_name") or industry_name
    except Exception:
        pass

    return {
        "status": "preset_only",
        "industry_name": industry_name,
        "preset": preset,
        "signals": {},
        "confidence": 0.0,
        "source": "local_preset_routing",
    }


class IndustryAgent(BaseAgent):
    """行业景气 Agent（专家5组）"""

    signal_type = "industry"

    def __init__(self, config: Optional[dict] = None):
        super().__init__(name="行业景气Agent", config=config or {})
        self.load_skills_from_domain("industry")
        self.load_skills_from_domain("data")
        # 复用数据源实例，避免每次 analyze 都新建
        self._data_source = (
            self.config.get("industrial_sentinel_data_source")
            or self.config.get("data_source")
        )
        if self._data_source is not None:
            return
        if IndustrialSentinelDataSource is not None:
            try:
                self._data_source = IndustrialSentinelDataSource(
                    industry_data_source=self.config.get("industry_sentiment_source"),
                    financial_data_source=(
                        self.config.get("industry_financial_data_source")
                        or self.config.get("financial_data_source")
                    ),
                    cache_dir=self.config.get("industrial_sentinel_cache_dir"),
                )
            except Exception as e:
                self.log(f"数据源初始化失败：{e}", level="warning")

    def analyze(self, stock_code: str) -> Signal:
        """运行 industrial_sentinel skill，返回行业景气度 Signal。

        1. 先将输入归一化为股票代码、股票名称、行业词或 preset
        2. 个股输入从 data_sources.industrial_sentinel 获取原始数据
        3. 将原始 dict 传给 runtime.run_industrial_sentinel() 进行分析
        4. 将返回的 dict 通过 Signal.from_dict() 包装为标准 Signal
        5. Signal.from_dict 异常时返回 neutral_signal 并标记 needs_human_review
        """
        input_context = _normalize_industry_input(stock_code)
        analysis_input = input_context["analysis_input"]
        self.log(
            f"开始行业景气分析：{stock_code} "
            f"(input_type={input_context['input_type']}, preset={input_context.get('preset') or 'auto'})"
        )

        if run_industrial_sentinel is None:
            return neutral_signal(
                confidence=0.1,
                reasoning="industrial_sentinel runtime 导入失败",
                source=self.name,
                stock_code=stock_code,
                signal_type=self.signal_type,
                meta={"needs_human_review": True, "error": "runtime import failed"},
            )

        # ── Step 1: 从 data_sources 层获取数据（封装了缓存降级） ──
        industry_result = None
        financial_data = None
        degradation_reasons = []
        data_source_meta = {}

        ds = self._data_source
        if input_context.get("preset") and not input_context["use_data_source"]:
            if input_context["input_type"] == "industry":
                framework_only_reason = (
                    f"【行业输入无个股财务数据】输入 '{stock_code}' 已匹配 "
                    f"{input_context['preset']} 分析框架；由于未提供具体股票代码，"
                    "不会拉取单家公司财务数据，结论仅代表框架级判断。"
                )
            else:
                framework_only_reason = (
                    f"【preset 输入无个股财务数据】输入 '{stock_code}' 直接使用 "
                    f"{input_context['preset']} 分析框架；由于未提供具体股票代码，"
                    "不会拉取单家公司财务数据，结论仅代表框架级判断。"
                )
            industry_result = {
                "status": "preset_only",
                "industry_name": (
                    stock_code if input_context["input_type"] == "industry" else ""
                ),
                "preset": input_context["preset"],
                "signals": {},
                "confidence": 0.0,
            }
            degradation_reasons.append(framework_only_reason)
            data_source_meta = {
                "industry_from_cache": False,
                "financial_from_cache": False,
                "industry_status": "preset_only",
                "financial_status": "not_applicable",
                "degradation_reasons": degradation_reasons,
            }
        elif not input_context["use_data_source"]:
            degradation_reasons.append(
                f"【输入无法识别】无法将 '{stock_code}' 识别为股票代码、股票名称、行业词或 preset。"
            )
            data_source_meta = {
                "industry_from_cache": False,
                "financial_from_cache": False,
                "industry_status": "missing",
                "financial_status": "not_applicable",
                "degradation_reasons": degradation_reasons,
            }

        if ds is not None and input_context["use_data_source"]:
            try:
                data = ds.get_data(input_context["data_source_input"])
                industry_result = data.get("industry_result")
                financial_data = data.get("financial_data")
                degradation_reasons = data.get("degradation_reasons", [])
                data_source_meta = {
                    "industry_from_cache": data.get("industry_from_cache", False),
                    "financial_from_cache": data.get("financial_from_cache", False),
                    "industry_status": data.get("industry_status", "missing"),
                    "financial_status": data.get("financial_status", "missing"),
                    "degradation_reasons": degradation_reasons,
                }
                if (
                    not industry_result
                    and input_context.get("preset")
                    and input_context.get("preset") != "generic"
                ):
                    industry_result = _build_preset_only_industry_result(
                        stock_code,
                        input_context["preset"],
                    )
                    preset_reason = (
                        f"【行业情绪数据缺失】无法获取 {stock_code} 的实时行业板块景气数据，"
                        f"已降级到本地 preset 路由：{input_context['preset']}。"
                        "该结果只用于选择分析框架，不代表真实行业景气度。"
                    )
                    degradation_reasons.append(preset_reason)
                    data_source_meta["industry_status"] = "preset_only"
                    data_source_meta["degradation_reasons"] = degradation_reasons
                if industry_result and industry_result.get("status") == "preset_only":
                    self.log("行业情绪数据不可用，已降级到本地 preset 路由", level="warning")
                elif industry_result:
                    self.log("行业情绪数据获取成功")
                else:
                    self.log("行业情绪数据不可用", level="warning")
                if financial_data:
                    self.log("财务数据获取成功")
                else:
                    self.log("财务数据不可用", level="warning")
            except Exception as exc:
                self.log(f"IndustrialSentinelDataSource 获取失败：{exc}", level="error")
                degradation_reasons.append(
                    f"【数据源异常】IndustrialSentinelDataSource 获取失败：{exc}"
                )
                data_source_meta = {
                    "industry_from_cache": False,
                    "financial_from_cache": False,
                    "industry_status": "error",
                    "financial_status": "error",
                    "degradation_reasons": degradation_reasons,
                }
        elif input_context["use_data_source"]:
            self.log("IndustrialSentinelDataSource 不可用", level="warning")
            degradation_reasons.append(
                "【数据源不可用】IndustrialSentinelDataSource 未初始化，无法获取实时行业与财务数据。"
            )
            data_source_meta = {
                "industry_from_cache": False,
                "financial_from_cache": False,
                "industry_status": "missing",
                "financial_status": "missing",
                "degradation_reasons": degradation_reasons,
            }
        else:
            self.log(
                "行业/preset 输入不请求个股数据源，仅使用 preset 框架与传入数据判断",
                level="info",
            )

        # ── Step 2: 调用 runtime 进行分析（只传数据 dict，不接触网络/磁盘） ──
        # 把降级原因通过 config 透传给 runtime，让 runtime 在 reasoning 中展示
        config_with_hints = dict(self.config)
        if degradation_reasons:
            config_with_hints["_degradation_reasons"] = degradation_reasons
        config_with_hints["_input_context"] = dict(input_context)
        try:
            result = run_industrial_sentinel(
                analysis_input,
                industry_result=industry_result,
                financial_data=financial_data,
                config=config_with_hints,
            )
        except Exception as exc:
            self.log(f"industrial_sentinel 执行失败：{exc}", level="error")
            return neutral_signal(
                confidence=0.1,
                reasoning=f"industrial_sentinel 执行异常: {exc}",
                source=self.name,
                stock_code=stock_code,
                signal_type=self.signal_type,
                meta={"needs_human_review": True, "error": str(exc)},
            )

        # ── Step 3: 构造 Signal（异常时返回 neutral_signal + needs_human_review） ──
        raw_result = result
        try:
            # 防御性预处理：先浅拷贝避免修改 caller 的 dict，再确保关键字段有效
            result = dict(result)
            result["confidence"] = max(0.0, min(1.0, float(result.get("confidence", 0.25) or 0.25)))
            if result.get("direction") not in ("bullish", "bearish", "neutral"):
                result["direction"] = "neutral"
            signal = Signal.from_dict(result)
        except Exception as exc:
            self.log(f"Signal 构造异常：{exc}", level="error")
            return neutral_signal(
                confidence=0.1,
                reasoning=f"Signal 构造异常: {exc}",
                source=self.name,
                stock_code=stock_code,
                signal_type=self.signal_type,
                meta={"needs_human_review": True, "error": str(exc), "raw_result": raw_result},
            )

        signal.source = self.name
        signal.signal_type = self.signal_type
        signal.stock_code = stock_code

        # 把数据源元信息写入 meta，便于 Orchestrator 追踪
        signal.meta.pop("html_report", None)
        signal.meta.pop("html_path", None)
        signal.meta["input_context"] = input_context
        signal.meta["data_source"] = data_source_meta

        return signal
