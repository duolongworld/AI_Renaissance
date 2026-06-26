from skills.financial.financial_report_analysis.scripts.analyze_report import build_signal


def _rd_commercialization_payload(**overrides):
    payload = {
        "ticker": "TEST",
        "company_name": "商业化拐点测试公司",
        "period": "2026-03-31",
        "source_type": "data_source",
        "source_name": "测试数据源",
        "income_statement_present": True,
        "balance_sheet_present": True,
        "cash_flow_statement_present": True,
        "net_profit_parent": -100.0,
        "revenue": 1000.0,
        "revenue_growth": 0.20,
        "revenue_qoq": 0.05,
        "operating_cost": 600.0,
        "operating_cash_flow": -50.0,
        "operating_cash_flow_qoq": 0.10,
        "cash_received_from_sales": 980.0,
        "contract_liability_growth": 0.10,
        "contract_liability_qoq": 0.08,
        "receivable_growth": 0.10,
        "receivable_qoq": 0.02,
        "finance_expense": 0.0,
        "operating_profit": -90.0,
        "research_expense": 300.0,
        "research_expense_growth": 0.10,
        "cash_and_equivalents_qoq": -0.10,
        "prepayment_growth": 0.05,
        "prepayment_qoq": 0.02,
        "intangible_asset_growth": 0.10,
        "intangible_asset_qoq": 0.02,
        "total_noncurrent_assets_growth": 0.10,
        "total_noncurrent_assets_qoq": 0.02,
    }
    payload.update(overrides)
    return payload


def test_rd_commercialization_inflection_turns_loss_maker_bullish_when_core_metrics_improve():
    result = build_signal(_rd_commercialization_payload())

    assert result["direction"] == "bullish"
    assert result["meta"]["risk_level"] == "medium"
    assert result["meta"]["commercial_inflection"]["status"] == "pass"
    assert "commercial_inflection: pass" in result["signals"]
    assert "商业化拐点观察偏多" in result["reasoning"]


def test_rd_commercialization_inflection_requires_cash_buffer_not_clearly_worse():
    result = build_signal(_rd_commercialization_payload(cash_and_equivalents_qoq=-0.35))

    assert result["direction"] == "neutral"
    assert result["meta"]["commercial_inflection"]["status"] == "watch"
    assert "cash_buffer" in result["meta"]["commercial_inflection"]["failed_items"]
