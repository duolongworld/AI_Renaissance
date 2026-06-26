from pathlib import Path
from types import SimpleNamespace

from agents.financial import FINANCIAL_AGENT_VERSION
from agents.financial.backtests.run_backtest import (
    ALL_DATA_DATES,
    actual_direction,
    build_report,
    calculate_metrics,
    render_markdown_report,
    run_financial_agent,
    standalone_quarter_value,
)


def test_required_data_dates_include_q1_needed_to_derive_prior_year_q2():
    assert "2023-03-31" in ALL_DATA_DATES


def test_backtest_assets_are_outside_runtime_skill_directory():
    assert not Path("skills/financial/financial_report_analysis/backtest").exists()
    assert Path("agents/financial/backtests/sample_pool_v1.csv").exists()
    assert Path("agents/financial/backtests/run_backtest.py").exists()


def test_build_report_records_shareable_backtest_metadata():
    report = build_report(
        [{"company_name": "样本公司", "ticker": "000001.SZ", "subsector_id": "1"}],
        [],
        cache_path=Path("output/financial_backtest/financial_statements_cache_v1.json"),
        label_threshold=0.10,
        report_path=Path("agents/financial/backtests/records/financial_agent_backtest_latest.md"),
    )

    record = report["backtest_record"]

    assert record["backtest_date"] == report["generated_at"][:10]
    assert record["financial_agent_version"] == FINANCIAL_AGENT_VERSION
    assert record["executed_by"] == "简简简水粽"
    assert record["sample_pool"] == "agents/financial/backtests/sample_pool_v1.csv"
    assert record["backtest_period"] == "2024Q1 至 2025Q4 信号，2024Q2 至 2026Q1 验证"
    assert record["result_report"] == "agents/financial/backtests/records/financial_agent_backtest_latest.md"


def test_actual_direction_treats_loss_narrowing_as_bullish():
    result = actual_direction(
        next_quarter_net_profit=-400.0,
        prior_year_same_quarter_net_profit=-1000.0,
        next_quarter_revenue=10_000.0,
    )

    assert result["direction"] == "bullish"
    assert result["normalized_change"] == 0.6


def test_standalone_quarter_value_derives_q2_from_cumulative_reports():
    statements = {
        ("000001", "2024-03-31"): {
            "income": {"data": [{"PARENT_NETPROFIT": 100.0}]}
        },
        ("000001", "2024-06-30"): {
            "income": {"data": [{"PARENT_NETPROFIT": 260.0}]}
        },
    }

    value = standalone_quarter_value(
        statements,
        "000001",
        "2024-06-30",
        "income",
        "PARENT_NETPROFIT",
    )

    assert value == 160.0


def test_calculate_metrics_uses_strict_high_confidence_threshold():
    records = [
        {"evaluable": True, "confidence": 0.71, "correct": True},
        {"evaluable": True, "confidence": 0.80, "correct": False},
        {"evaluable": True, "confidence": 0.70, "correct": True},
        {"evaluable": False, "confidence": 0.90, "correct": False},
    ]

    metrics = calculate_metrics(records)

    assert metrics["evaluable_samples"] == 3
    assert metrics["high_confidence_samples"] == 2
    assert metrics["coverage_high_confidence"] == 2 / 3
    assert metrics["accuracy_high_confidence"] == 0.5
    assert metrics["accuracy_all"] == 2 / 3


def test_run_financial_agent_calls_agent_analyze_for_prediction():
    class FakeAgent:
        def __init__(self):
            self.config = {}
            self.calls = []

        def analyze(self, ticker):
            self.calls.append((ticker, self.config["report_date"]))
            return SimpleNamespace(
                direction="neutral",
                confidence=0.6,
                reasoning="test",
                signals=[],
                source="财务分析Agent",
                signal_type="financial",
                stock_code=ticker,
                timestamp="",
                weight=1.0,
                meta={},
                to_dict=lambda: {
                    "direction": "neutral",
                    "confidence": 0.6,
                    "reasoning": "test",
                    "signals": [],
                    "source": "财务分析Agent",
                    "signal_type": "financial",
                    "stock_code": ticker,
                    "timestamp": "",
                    "weight": 1.0,
                    "meta": {},
                },
            )

    agent = FakeAgent()
    signal = run_financial_agent(agent, "000001", "2024-03-31")

    assert agent.calls == [("000001", "2024-03-31")]
    assert signal["direction"] == "neutral"


def test_markdown_report_contains_required_sections_and_uses_chinese_labels():
    report = {
        "generated_at": "2026-06-26T00:00:00",
        "methodology": {"signal_window": "2024Q1-2025Q4"},
        "sample_pool": [{"company_name": "样本公司", "ticker": "000001.SZ"}],
        "metrics": {
            "total_samples": 1,
            "evaluable_samples": 1,
            "high_confidence_samples": 1,
            "coverage_high_confidence": 1.0,
            "accuracy_high_confidence": 1.0,
            "accuracy_all": 1.0,
        },
        "group_metrics": {},
        "confidence_buckets": [],
        "confusion_matrix": {},
        "misses": [
            {
                "company_name": "不应出现在误判分析中的公司",
                "miss_category": "中性偏置",
                "miss_cause": "七步链的混合信号被压缩为中性。",
            }
        ],
        "iteration_recommendations": ["补齐订单数据"],
        "limitations": ["当前历史数据不是公告时点快照"],
    }

    markdown = render_markdown_report(report)

    assert "# FinancialAgent 全样本回测报告" in markdown
    assert "## 回测口径说明" in markdown
    assert "## 样本池" in markdown
    assert "## 回测结果" in markdown
    assert "## 误判分析" in markdown
    assert "## FinancialAgent 迭代建议" in markdown
    assert "看多" in markdown
    assert "bullish" not in markdown
    assert "bearish" not in markdown
    assert "neutral" not in markdown
    assert "不应出现在误判分析中的公司" not in markdown
    assert "| 中性偏置 | 1 |" in markdown
