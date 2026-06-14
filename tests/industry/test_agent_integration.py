#!/usr/bin/env python3
"""
IndustryAgent 集成测试
验证 agent.py → runtime → pipeline → Signal 全链路
"""
import sys
import os
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

# 确保 repo root 在 path 中
REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))


# ═══════════════════════════════════════════════════
# 1. Import 链路测试
# ═══════════════════════════════════════════════════

def test_import_agent_module():
    """验证 agent 模块可正常导入"""
    from agents.industry.agent import IndustryAgent
    assert IndustryAgent is not None
    assert IndustryAgent.signal_type == "industry"


def test_import_signal_classes():
    """验证 Signal 相关类可正常导入"""
    from agents.signal import Signal, Direction, SignalType, neutral_signal
    assert Direction.BULLISH.value == "bullish"
    assert SignalType.INDUSTRY.value == "industry"
    assert callable(neutral_signal)


# ═══════════════════════════════════════════════════
# 2. Signal 契约测试
# ═══════════════════════════════════════════════════

def test_signal_from_dict_bullish():
    """Signal.from_dict 正确解析完整 bullish 信号"""
    from agents.signal import Signal

    result = {
        "direction": "bullish",
        "confidence": 0.75,
        "reasoning": "产业链景气上行",
        "signals": ["营收加速", "产能紧张", "政策催化"],
        "source": "行业景气Agent",
        "signal_type": "industry",
        "stock_code": "002916.SZ",
        "weight": 0.65,
        "meta": {
            "stock_name": "深南电路",
            "industry": "PCB",
            "preset": "pcb",
            "data_quality": "complete",
            "stock_type": "cyclical",
            "adaptive_weights": {
                "fundamental": 0.35, "valuation": 0.20,
                "technical": 0.25, "sentiment": 0.20
            },
        },
    }
    signal = Signal.from_dict(result)

    assert signal.direction == "bullish"
    assert signal.confidence == 0.75
    assert len(signal.signals) == 3
    assert signal.weight == 0.65
    assert signal.meta["stock_type"] == "cyclical"
    assert signal.meta["adaptive_weights"]["fundamental"] == 0.35
    assert "html_report" not in signal.meta


def test_signal_from_dict_neutral():
    """Signal.from_dict 正确解析 neutral 信号"""
    from agents.signal import Signal

    result = {
        "direction": "neutral",
        "confidence": 0.1,
        "reasoning": "数据缺失",
        "signals": [],
        "weight": 0.0,
        "meta": {"data_quality": "missing"},
    }
    signal = Signal.from_dict(result)
    assert signal.direction == "neutral"
    assert signal.confidence == 0.1


def test_signal_from_dict_bearish():
    """Signal.from_dict 正确解析 bearish 信号"""
    from agents.signal import Signal

    result = {
        "direction": "bearish",
        "confidence": 0.6,
        "reasoning": "产能过剩",
        "signals": ["价格下跌", "库存积压"],
        "weight": 0.4,
        "meta": {},
    }
    signal = Signal.from_dict(result)
    assert signal.direction == "bearish"


def test_signal_confidence_range_validation():
    """置信度越界应抛出 ValueError"""
    from agents.signal import Signal
    import pytest

    with pytest.raises(ValueError):
        Signal(direction="neutral", confidence=1.5, reasoning="test")

    with pytest.raises(ValueError):
        Signal(direction="neutral", confidence=-0.1, reasoning="test")


def test_signal_direction_validation():
    """非法方向应抛出 ValueError"""
    from agents.signal import Signal
    import pytest

    with pytest.raises(ValueError):
        Signal(direction="invalid", confidence=0.5, reasoning="test")


# ═══════════════════════════════════════════════════
# 3. IndustryAgent 集成测试（mock runtime）
# ═══════════════════════════════════════════════════

class TestIndustryAgent:
    """IndustryAgent 全链路测试"""

    @pytest.fixture
    def mock_runtime_success(self):
        """Mock run_industrial_sentinel 返回完整成功信号"""
        return {
            "direction": "bullish",
            "confidence": 0.72,
            "reasoning": "仕佳光子：拐点确认 | 成长期",
            "signals": ["营收增速 35.0% >= 20% 加速", "产能利用率 88.0% >= 85% 紧张"],
            "weight": 0.65,
            "meta": {
                "stock_name": "仕佳光子",
                "stock_code": "688313.SH",
                "industry": "光通信",
                "preset": "optical-module",
                "data_quality": "complete",
                "stock_type": "growth",
                "adaptive_weights": {
                    "fundamental": 0.30, "valuation": 0.35,
                    "technical": 0.20, "sentiment": 0.15,
                },
            },
        }

    @pytest.fixture
    def mock_runtime_neutral(self):
        """Mock 返回中性信号"""
        return {
            "direction": "neutral",
            "confidence": 0.15,
            "reasoning": "芯原股份：拐点前 | 导入期 — 数据不足以判定",
            "signals": [],
            "weight": 0.1,
            "meta": {
                "stock_name": "芯原股份",
                "stock_code": "688521.SH",
                "industry": "芯片设计",
                "preset": "ai-chip",
                "data_quality": "incomplete",
                "stock_type": "mixed",
                "adaptive_weights": {"fundamental": 0.25, "valuation": 0.25, "technical": 0.25, "sentiment": 0.25},
            },
        }

    def test_analyze_bullish(self, mock_runtime_success):
        """正常路径：返回 bullish Signal"""
        from agents.industry.agent import IndustryAgent

        with patch("agents.industry.agent.run_industrial_sentinel",
                   return_value=mock_runtime_success):
            agent = IndustryAgent()
            signal = agent.analyze("688313.SH")

        assert signal.direction == "bullish"
        assert signal.confidence == 0.72
        assert signal.signal_type == "industry"
        assert signal.source == "行业景气Agent"
        assert signal.stock_code == "688313.SH"
        assert len(signal.signals) == 2
        assert signal.meta["stock_type"] == "growth"
        assert signal.meta["preset"] == "optical-module"
        assert "html_report" not in signal.meta
        # adaptive_weights 应透传
        assert signal.meta["adaptive_weights"]["fundamental"] == 0.30
        assert signal.weight == 0.65

    def test_analyze_neutral(self, mock_runtime_neutral):
        """数据不足路径：返回 neutral Signal"""
        from agents.industry.agent import IndustryAgent

        with patch("agents.industry.agent.run_industrial_sentinel",
                   return_value=mock_runtime_neutral):
            agent = IndustryAgent()
            signal = agent.analyze("688521.SH")

        assert signal.direction == "neutral"
        assert signal.confidence == 0.15
        assert signal.signal_type == "industry"
        assert signal.meta["data_quality"] == "incomplete"
        assert "html_report" not in signal.meta

    def test_analyze_strips_html_report_from_runtime_meta(self, mock_runtime_success):
        """项目级 IndustryAgent 不向 Orchestrator 暴露 HTML 报告路径"""
        from agents.industry.agent import IndustryAgent

        result = dict(mock_runtime_success)
        result["meta"] = dict(mock_runtime_success["meta"])
        result["meta"]["html_report"] = "/tmp/debug_report.html"
        result["meta"]["html_path"] = "/tmp/debug_report.html"

        with patch("agents.industry.agent.run_industrial_sentinel",
                   return_value=result):
            agent = IndustryAgent()
            signal = agent.analyze("688313.SH")

        assert signal.direction == "bullish"
        assert "html_report" not in signal.meta
        assert "html_path" not in signal.meta

    def test_analyze_runtime_exception(self):
        """runtime 抛出异常：应返回降级 neutral Signal"""
        from agents.industry.agent import IndustryAgent

        with patch("agents.industry.agent.run_industrial_sentinel",
                   side_effect=RuntimeError("Skill 执行崩溃")):
            agent = IndustryAgent()
            signal = agent.analyze("000001.SZ")

        assert signal.direction == "neutral"
        assert signal.confidence == 0.1
        assert "崩溃" in signal.reasoning
        assert signal.stock_code == "000001.SZ"

    def test_analyze_import_missing(self):
        """runtime import 失败：应返回降级 neutral Signal"""
        from agents.industry.agent import IndustryAgent

        with patch("agents.industry.agent.run_industrial_sentinel", None):
            agent = IndustryAgent()
            signal = agent.analyze("000001.SZ")

        assert signal.direction == "neutral"
        assert signal.confidence == 0.1
        assert "导入失败" in signal.reasoning

    def test_analyze_empty_result(self):
        """runtime 返回空 dict：from_dict 应妥善处理"""
        from agents.industry.agent import IndustryAgent

        # from_dict 需要至少这些 key
        minimal = {
            "direction": "neutral",
            "confidence": 0.0,
            "reasoning": "",
            "signals": [],
            "weight": 0.0,
            "meta": {},
        }
        with patch("agents.industry.agent.run_industrial_sentinel",
                   return_value=minimal):
            agent = IndustryAgent()
            signal = agent.analyze("000000.SZ")

        assert signal.direction == "neutral"

    def test_analyze_invalid_runtime_signal_returns_neutral(self):
        """runtime 返回非法 Signal 字段时不应穿透主流程"""
        from agents.industry.agent import IndustryAgent

        invalid = {
            "direction": "not-a-direction",
            "confidence": "bad-confidence",
            "reasoning": "invalid payload",
            "signals": [],
            "weight": 0.0,
            "meta": {},
        }
        with patch("agents.industry.agent.run_industrial_sentinel",
                   return_value=invalid):
            agent = IndustryAgent()
            signal = agent.analyze("000000.SZ")

        assert signal.direction == "neutral"
        assert signal.confidence == 0.1
        assert signal.meta["needs_human_review"] is True
        assert "bad-confidence" in signal.meta["error"]

    def test_stock_code_passthrough(self, mock_runtime_success):
        """stock_code 未设置时 agent 应补上"""
        from agents.industry.agent import IndustryAgent

        result = dict(mock_runtime_success)
        del result["meta"]["stock_code"]  # 模拟缺少 stock_code
        result["meta"]["stock_code"] = ""

        with patch("agents.industry.agent.run_industrial_sentinel",
                   return_value=result):
            agent = IndustryAgent()
            signal = agent.analyze("002916.SZ")

        # agent 应补上 stock_code
        assert signal.stock_code == "002916.SZ"

    def test_config_and_data_passed_to_runtime(self, mock_runtime_success):
        """config 和 data_sources 数据应传递给 runtime"""
        from agents.industry.agent import IndustryAgent

        config = {"verbose": True, "data_dir": "/custom/path"}
        source_data = {
            "industry_result": {
                "status": "success",
                "industry_name": "PCB",
                "score": 62,
                "stage": {"name": "行业偏热", "direction": "bearish"},
                "direction": "bearish",
                "confidence": 0.55,
                "special_signals": ["行业偏热"],
            },
            "financial_data": {
                "balance": {"data": [{"TOTAL_ASSETS": 100, "FIXED_ASSET": 20}]},
                "income": {"data": [{"OPERATE_INCOME": 50, "OPERATE_COST": 30}]},
                "cashflow": {},
            },
            "industry_from_cache": False,
            "financial_from_cache": False,
            "degradation_reasons": [],
        }
        mock_data_source = MagicMock()
        mock_data_source.get_data.return_value = source_data
        with patch("agents.industry.agent.run_industrial_sentinel",
                   return_value=mock_runtime_success) as mock_run, \
             patch("agents.industry.agent.IndustrialSentinelDataSource",
                   return_value=mock_data_source):
            agent = IndustryAgent(config=config)
            agent.analyze("002916.SZ")

        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        assert args == ("002916.SZ",)
        assert kwargs["industry_result"] == source_data["industry_result"]
        assert kwargs["financial_data"] == source_data["financial_data"]
        assert kwargs["config"]["verbose"] is True
        assert kwargs["config"]["data_dir"] == "/custom/path"
        assert kwargs["config"]["_input_context"]["input_type"] == "stock_code"

    def test_config_injected_data_source_is_used(self, mock_runtime_success):
        """IndustryAgent 应支持像其他专家组一样通过 config 注入数据源"""
        from agents.industry.agent import IndustryAgent

        source_data = {
            "industry_result": None,
            "financial_data": None,
            "industry_from_cache": False,
            "financial_from_cache": False,
            "degradation_reasons": ["offline test"],
        }
        injected_source = MagicMock()
        injected_source.get_data.return_value = source_data

        with patch("agents.industry.agent.run_industrial_sentinel",
                   return_value=mock_runtime_success) as mock_run, \
             patch("agents.industry.agent.IndustrialSentinelDataSource") as constructor:
            agent = IndustryAgent(config={"industrial_sentinel_data_source": injected_source})
            signal = agent.analyze("999999.SZ")

        constructor.assert_not_called()
        injected_source.get_data.assert_called_once_with("999999.SZ")
        mock_run.assert_called_once()
        _, kwargs = mock_run.call_args
        assert kwargs["industry_result"] is None
        assert kwargs["financial_data"] is None
        assert kwargs["config"]["_degradation_reasons"] == ["offline test"]
        assert signal.signal_type == "industry"

    def test_stock_input_uses_agent_level_preset_fallback_when_industry_data_missing(self, mock_runtime_success):
        """行业数据缺失时，Agent 负责把本地 preset 路由降级传给 runtime。"""
        from agents.industry.agent import IndustryAgent

        source_data = {
            "industry_result": None,
            "financial_data": None,
            "industry_from_cache": False,
            "financial_from_cache": False,
            "industry_status": "missing",
            "financial_status": "missing",
            "degradation_reasons": ["offline test"],
        }
        injected_source = MagicMock()
        injected_source.get_data.return_value = source_data

        with patch("agents.industry.agent.run_industrial_sentinel",
                   return_value=mock_runtime_success) as mock_run:
            agent = IndustryAgent(config={"industrial_sentinel_data_source": injected_source})
            signal = agent.analyze("000700.SZ")

        injected_source.get_data.assert_called_once_with("000700.SZ")
        _, kwargs = mock_run.call_args
        assert kwargs["industry_result"]["status"] == "preset_only"
        assert kwargs["industry_result"]["preset"] == "robotics"
        assert kwargs["config"]["_degradation_reasons"][0] == "offline test"
        assert any("本地 preset 路由" in reason for reason in kwargs["config"]["_degradation_reasons"])
        assert signal.meta["data_source"]["industry_status"] == "preset_only"

    def test_stock_name_input_routes_to_stock_code(self, mock_runtime_success):
        """股票名称输入应先归一化为股票代码，再调用项目数据源"""
        from agents.industry.agent import IndustryAgent

        source_data = {
            "industry_result": None,
            "financial_data": None,
            "industry_from_cache": False,
            "financial_from_cache": False,
            "degradation_reasons": [],
        }
        injected_source = MagicMock()
        injected_source.get_data.return_value = source_data

        with patch("agents.industry.agent.run_industrial_sentinel",
                   return_value=mock_runtime_success) as mock_run:
            agent = IndustryAgent(config={"industrial_sentinel_data_source": injected_source})
            signal = agent.analyze("模塑科技")

        injected_source.get_data.assert_called_once_with("000700.SZ")
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        assert args == ("000700.SZ",)
        assert kwargs["config"]["_input_context"]["input_type"] == "stock_name"
        assert kwargs["config"]["_input_context"]["preset"] == "robotics"
        assert signal.meta["input_context"]["analysis_input"] == "000700.SZ"

    def test_industry_input_uses_preset_without_stock_data_source(self, mock_runtime_neutral):
        """行业词输入只选择 preset 框架，不把行业词传给个股数据源"""
        from agents.industry.agent import IndustryAgent

        injected_source = MagicMock()
        with patch("agents.industry.agent.run_industrial_sentinel",
                   return_value=mock_runtime_neutral) as mock_run:
            agent = IndustryAgent(config={"industrial_sentinel_data_source": injected_source})
            signal = agent.analyze("机器人")

        injected_source.get_data.assert_not_called()
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        assert args == ("机器人",)
        assert kwargs["industry_result"]["preset"] == "robotics"
        assert kwargs["financial_data"] is None
        assert kwargs["config"]["_input_context"]["input_type"] == "industry"
        assert any(
            "行业输入无个股财务数据" in reason
            for reason in kwargs["config"]["_degradation_reasons"]
        )
        assert signal.meta["data_source"]["industry_status"] == "preset_only"
        assert signal.meta["data_source"]["financial_status"] == "not_applicable"
        assert signal.meta["input_context"]["preset"] == "robotics"

    def test_direct_preset_input_uses_framework_only(self, mock_runtime_neutral):
        """直接输入 preset 时应跳过个股数据源，仅进入对应分析框架"""
        from agents.industry.agent import IndustryAgent

        injected_source = MagicMock()
        with patch("agents.industry.agent.run_industrial_sentinel",
                   return_value=mock_runtime_neutral) as mock_run:
            agent = IndustryAgent(config={"industrial_sentinel_data_source": injected_source})
            signal = agent.analyze("optical-module")

        injected_source.get_data.assert_not_called()
        args, kwargs = mock_run.call_args
        assert args == ("optical-module",)
        assert kwargs["industry_result"]["preset"] == "optical-module"
        assert kwargs["config"]["_input_context"]["input_type"] == "preset"
        assert signal.meta["input_context"]["preset"] == "optical-module"


# ═══════════════════════════════════════════════════
# 4. 边界条件测试
# ═══════════════════════════════════════════════════

def test_agent_name():
    """Agent 名称正确"""
    from agents.industry.agent import IndustryAgent
    agent = IndustryAgent()
    assert "行业景气" in agent.name


def test_agent_signal_type():
    """signal_type 类属性正确"""
    from agents.industry.agent import IndustryAgent
    assert IndustryAgent.signal_type == "industry"


def test_signal_to_dict_roundtrip():
    """Signal → to_dict → from_dict 往返一致性"""
    from agents.signal import Signal

    original = Signal(
        direction="bullish",
        confidence=0.8,
        reasoning="测试推理",
        signals=["s1", "s2"],
        source="测试源",
        signal_type="industry",
        stock_code="002916.SZ",
        weight=0.5,
        meta={"key": "value"},
    )
    as_dict = original.to_dict()
    restored = Signal.from_dict(as_dict)

    assert restored.direction == original.direction
    assert restored.confidence == original.confidence
    assert restored.reasoning == original.reasoning
    assert restored.signal_type == original.signal_type
    assert restored.weight == original.weight
    assert restored.meta == original.meta


def test_runtime_maps_industry_sentiment_source_fields():
    """runtime 应兼容 IndustrySentimentDataSource 的字段命名"""
    from skills.industry.industrial_sentinel.runtime import _build_real_data

    real_data = _build_real_data(
        "002916.SZ",
        industry_result={
            "status": "success",
            "industry_name": "PCB",
            "preset": "pcb",
            "score": 62.5,
            "stage": {"name": "行业偏热", "direction": "bearish"},
            "direction": "bearish",
            "confidence": 0.55,
            "special_signals": ["行业偏热"],
        },
        financial_data=None,
    )

    assert real_data["industry"] == "PCB"
    assert real_data["industry_sentiment"] == "行业偏热"
    assert real_data["industry_sentiment_score"] == 62.5
    assert real_data["industry_sentiment_direction"] == "bearish"
    assert real_data["industry_sentiment_confidence"] == 0.55
    assert real_data["preset"] == "pcb"
    assert real_data["industry_signals"]["qualitative_signals"] == ["行业偏热"]
    assert real_data["industry_signals"]["industry_lifecycle_stage"] == "行业偏热"
    assert real_data["_missing_count"] == 1


def test_runtime_agent_mode_does_not_return_html_report():
    """runtime 作为 Agent 接入口时只返回结构化 Signal 字段，不返回 HTML 路径"""
    from skills.industry.industrial_sentinel.runtime import run_industrial_sentinel

    result = run_industrial_sentinel(
        "002916.SZ",
        industry_result={
            "status": "success",
            "industry_name": "PCB",
            "signals": {
                "industry_market_growth": 28.0,
                "industry_order_growth": 18.0,
                "industry_capacity_utilization": 88.0,
                "industry_price_yoy": 6.0,
                "industry_capex_plan": "underway",
            },
        },
        financial_data=None,
        config={},
    )

    assert result["signal_type"] == "industry"
    assert "html_report" not in result.get("meta", {})
    assert "html_path" not in result.get("meta", {})


def test_runtime_caps_preset_only_confidence():
    """只命中 preset、缺少真实数据时不应输出高置信度结论"""
    from skills.industry.industrial_sentinel.runtime import run_industrial_sentinel

    result = run_industrial_sentinel(
        "机器人",
        industry_result={
            "status": "preset_only",
            "industry_name": "机器人",
            "preset": "robotics",
            "signals": {},
            "confidence": 0.0,
        },
        financial_data=None,
        config={
            "_degradation_reasons": [
                "【行业输入无个股财务数据】输入 '机器人' 已匹配 robotics 分析框架。"
            ]
        },
    )

    assert result["direction"] == "neutral"
    assert result["confidence"] <= 0.35
    assert result["weight"] <= 0.2
    assert result["meta"]["needs_data"] is True
    assert result["meta"]["data_quality"] == "missing"
    assert result["meta"]["degradation_level"] == "framework_only"
    assert result["meta"]["confidence_cap_reason"] == "framework_only_preset"


def test_runtime_caps_fully_missing_data_confidence():
    """行业和财务数据都缺失时，runtime 应低置信度降级并明确原因"""
    from skills.industry.industrial_sentinel.runtime import run_industrial_sentinel

    result = run_industrial_sentinel(
        "未知行业输入",
        industry_result=None,
        financial_data=None,
        config={"_degradation_reasons": ["offline test"]},
    )

    assert result["direction"] == "neutral"
    assert result["confidence"] <= 0.25
    assert result["weight"] <= 0.2
    assert result["meta"]["needs_data"] is True
    assert result["meta"]["data_quality"] == "missing"
    assert result["meta"]["degradation_level"] == "missing"
    assert result["meta"]["confidence_cap_reason"] == "industry_and_financial_data_missing"


def test_runtime_caps_sparse_industry_signal_confidence():
    """行业信号不足时，不能只因财务字段完整就输出高置信结论。"""
    from skills.industry.industrial_sentinel.runtime import run_industrial_sentinel

    result = run_industrial_sentinel(
        "688981.SH",
        industry_result={
            "status": "success",
            "industry_name": "AI芯片层",
            "preset": "ai-chip",
            "signals": {"industry_market_growth": 20},
            "confidence": 0.8,
        },
        financial_data={
            "revenue_growth": 0.22,
            "rd_ratio": 0.06,
            "research_expense_ratio": 0.06,
            "fixed_asset": 25_000_000_000,
            "total_asset": 100_000_000_000,
            "net_profit_parent": 8_000_000_000,
            "gross_margin": 0.28,
            "roe": 0.12,
            "debt_ratio": 0.45,
        },
        config={},
    )

    assert result["confidence"] <= 0.45
    assert result["weight"] <= 0.3
    assert result["meta"]["needs_data"] is True
    assert result["meta"]["data_quality"] == "incomplete"
    assert result["meta"]["degradation_level"] == "partial"
    assert result["meta"]["confidence_cap_reason"] == "insufficient_industry_signals"
    assert result["meta"]["industry_signal_count"] == 1
    assert result["meta"]["system_a_matched_signal_count"] >= 0


def test_system_a_prefers_industry_signals_over_company_real_signals():
    """System A 应优先使用行业级信号，避免单家公司财报污染行业判断"""
    from skills.industry.industrial_sentinel.core.pipeline import _build_system_a_signals

    real_data = {
        "industry_signals": {
            "industry_market_growth": 28.0,
            "industry_order_growth": 18.0,
            "industry_capacity_utilization": 86.0,
        },
        "peer_basket_signals": {
            "gross_margin_median": 24.0,
        },
        "real_signals": {
            "revenue_growth": -10.0,
            "gross_margin": 8.0,
        },
    }

    signals = _build_system_a_signals(real_data)

    assert signals["revenue_growth"] == 28.0
    assert signals["gross_margin"] == 24.0
    assert signals["order_backlog"] == 18.0
    assert signals["_signal_scope"]["revenue_growth"] == "industry"
    assert signals["_signal_scope"]["gross_margin"] == "peer_basket"


def test_industrial_sentinel_rejects_empty_financial_payload():
    """空三张表不应被视为财务数据获取成功"""
    from data_sources.industrial_sentinel import IndustrialSentinelDataSource

    data_source = IndustrialSentinelDataSource.__new__(IndustrialSentinelDataSource)

    assert not data_source._has_financial_payload(
        {"balance": {}, "income": {}, "cashflow": {}}
    )
    assert data_source._has_financial_payload(
        {"balance": {"data": [{"TOTAL_ASSETS": 100}]}, "income": {}, "cashflow": {}}
    )


def test_industrial_sentinel_default_cache_stays_in_data_sources():
    """复合数据源默认缓存目录应属于 data_sources，而不是写入 Skill 目录。"""
    from data_sources.industrial_sentinel import IndustrialSentinelDataSource

    data_source = IndustrialSentinelDataSource.__new__(IndustrialSentinelDataSource)
    cache_dir = data_source._find_cache_dir()
    normalized = str(cache_dir).replace("\\", "/")

    assert normalized.endswith("data_sources/data/industrial_sentinel")
    assert "skills/industry/industrial_sentinel/data" not in normalized


def test_industrial_sentinel_accepts_injected_sources(tmp_path):
    """复合数据源应允许注入底层行业/财务源，统一由 data_sources 层编排"""
    from data_sources.industrial_sentinel import IndustrialSentinelDataSource

    industry_source = MagicMock()
    industry_source.get_industry_sentiment.return_value = {
        "status": "success",
        "industry_name": "PCB",
        "score": 60,
    }
    financial_source = MagicMock()
    financial_source.get_financial_data.return_value = {
        "balance": {"data": [{"TOTAL_ASSETS": 100}]},
        "income": {},
        "cashflow": {},
    }

    data_source = IndustrialSentinelDataSource(
        industry_data_source=industry_source,
        financial_data_source=financial_source,
        cache_dir=tmp_path,
    )

    data = data_source.get_data("002916.SZ")

    industry_source.get_industry_sentiment.assert_called_once_with("002916.SZ")
    financial_source.get_financial_data.assert_called_once_with("002916")
    assert data["industry_result"]["industry_name"] == "PCB"
    assert data["financial_data"]["balance"]["data"][0]["TOTAL_ASSETS"] == 100
    assert data["industry_from_cache"] is False
    assert data["financial_from_cache"] is False


def test_industrial_sentinel_reports_missing_when_offline(tmp_path):
    """实时和缓存都失败时，data_sources 层只报告缺失，不反向依赖 Skill fallback。"""
    from data_sources.industrial_sentinel import IndustrialSentinelDataSource

    industry_source = MagicMock()
    industry_source.get_industry_sentiment.return_value = {
        "status": "error",
        "reason": "offline",
    }
    financial_source = MagicMock()
    financial_source.get_financial_data.return_value = {
        "balance": {},
        "income": {},
        "cashflow": {},
    }

    data_source = IndustrialSentinelDataSource(
        industry_data_source=industry_source,
        financial_data_source=financial_source,
        cache_dir=tmp_path,
    )

    data = data_source.get_data("000700.SZ")

    assert data["industry_result"] is None
    assert data["industry_from_cache"] is False
    assert data["industry_status"] == "missing"
    assert data["financial_status"] == "missing"
    assert data["financial_data"] is None
    assert any("行业情绪数据缺失" in reason for reason in data["degradation_reasons"])
    assert any("财务数据缺失" in reason for reason in data["degradation_reasons"])


def test_industrial_sentinel_rejects_empty_cached_financial_payload(tmp_path):
    """空财务缓存不应绕过数据缺失降级。"""
    from data_sources.industrial_sentinel import IndustrialSentinelDataSource

    industry_source = MagicMock()
    industry_source.get_industry_sentiment.return_value = None
    financial_source = MagicMock()
    financial_source.get_financial_data.return_value = None
    cache_file = tmp_path / "002916.SZ_financial_cache.json"
    cache_file.write_text(
        '{"balance": {}, "income": {}, "cashflow": {}}',
        encoding="utf-8",
    )

    data_source = IndustrialSentinelDataSource(
        industry_data_source=industry_source,
        financial_data_source=financial_source,
        cache_dir=tmp_path,
    )

    data = data_source.get_data("002916.SZ")

    assert data["financial_data"] is None
    assert data["financial_from_cache"] is False
    assert data["financial_status"] == "missing"
    assert any("财务数据缺失" in reason for reason in data["degradation_reasons"])


# ═══════════════════════════════════════════════════
# 5. Orchestrator 集成验证
# ═══════════════════════════════════════════════════

def test_signal_weight_read_by_orchestrator():
    """验证 Signal.weight 字段存在，Orchestrator 可正常读取"""
    from agents.signal import Signal

    # 模拟 Orchestrator 的 _calculate_scores 逻辑
    signal = Signal(
        direction="bullish",
        confidence=0.8,
        reasoning="test",
        weight=0.65,  # industry agent 返回的权重
    )
    weighted_confidence = signal.confidence * signal.weight
    assert abs(weighted_confidence - 0.52) < 0.01  # 0.8 * 0.65 = 0.52


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
