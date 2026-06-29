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


def _with_single_quarter_cashflow(payload, *, current_cashflow, previous_cashflow):
    payload = dict(payload)
    payload["operating_cash_flow"] = current_cashflow
    payload["single_quarter_metrics"] = {
        "current_quarter": {"operating_cash_flow": current_cashflow},
        "previous_quarter": {"operating_cash_flow": previous_cashflow},
    }
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


def test_rd_commercialization_inflection_blocks_borderline_orders_when_profit_margin_is_thin():
    result = build_signal(
        _rd_commercialization_payload(
            net_profit_parent=20.0,
            operating_cash_flow=30.0,
            cash_received_from_sales=1100.0,
            contract_liability_qoq=-0.001,
        )
    )

    assert result["direction"] == "neutral"
    inflection = result["meta"]["commercial_inflection"]
    assert inflection["status"] == "watch"
    assert "contract_liability_borderline_with_thin_profit" in inflection["protection_flags"]


def test_rd_commercialization_inflection_blocks_severe_cashflow_or_receivable_pressure():
    result = build_signal(
        _rd_commercialization_payload(
            revenue_growth=0.52,
            revenue_qoq=0.80,
            contract_liability_qoq=0.18,
            cash_and_equivalents_qoq=0.56,
            operating_cash_flow_qoq=-8.0,
            receivable_growth=1.78,
        )
    )

    assert result["direction"] == "neutral"
    inflection = result["meta"]["commercial_inflection"]
    assert inflection["status"] == "watch"
    assert "operating_cash_flow_qoq_collapse" in inflection["protection_flags"]
    assert "receivable_growth_outpaces_revenue" in inflection["protection_flags"]


def test_rd_commercialization_inflection_does_not_block_when_cashflow_turns_positive():
    result = build_signal(
        _with_single_quarter_cashflow(
            _rd_commercialization_payload(operating_cash_flow_qoq=-2.0),
            current_cashflow=80.0,
            previous_cashflow=-100.0,
        )
    )

    assert result["direction"] == "bullish"
    inflection = result["meta"]["commercial_inflection"]
    assert inflection["status"] == "pass"
    assert "operating_cash_flow_qoq_collapse" not in inflection["protection_flags"]


def test_rd_commercialization_inflection_blocks_when_cashflow_turns_negative():
    result = build_signal(
        _with_single_quarter_cashflow(
            _rd_commercialization_payload(operating_cash_flow_qoq=-2.0),
            current_cashflow=-50.0,
            previous_cashflow=100.0,
        )
    )

    assert result["direction"] == "neutral"
    inflection = result["meta"]["commercial_inflection"]
    assert inflection["status"] == "watch"
    assert "operating_cash_flow_qoq_collapse" in inflection["protection_flags"]
    assert "operating_cash_flow_qoq_collapse" in inflection["blocking_protection_flags"]


def test_rd_commercialization_inflection_blocks_when_negative_cash_outflow_expands():
    result = build_signal(
        _with_single_quarter_cashflow(
            _rd_commercialization_payload(operating_cash_flow_qoq=-1.0),
            current_cashflow=-180.0,
            previous_cashflow=-100.0,
        )
    )

    assert result["direction"] == "neutral"
    inflection = result["meta"]["commercial_inflection"]
    assert inflection["status"] == "watch"
    assert "operating_cash_flow_qoq_collapse" in inflection["protection_flags"]
    assert "operating_cash_flow_qoq_collapse" in inflection["blocking_protection_flags"]


def test_rd_commercialization_inflection_blocks_when_receivables_only_outpace_revenue():
    result = build_signal(
        _with_single_quarter_cashflow(
            _rd_commercialization_payload(receivable_growth=0.90),
            current_cashflow=120.0,
            previous_cashflow=80.0,
        )
    )

    assert result["direction"] == "neutral"
    inflection = result["meta"]["commercial_inflection"]
    assert inflection["status"] == "watch"
    assert "receivable_growth_outpaces_revenue" in inflection["protection_flags"]
    assert "receivable_growth_outpaces_revenue" in inflection["blocking_protection_flags"]


def test_non_core_depreciation_gap_does_not_directly_block_direction_when_core_chain_is_strong():
    result = build_signal(
        {
            "ticker": "TEST",
            "company_name": "非核心缺口测试公司",
            "period": "2026-03-31",
            "source_type": "data_source",
            "source_name": "测试数据源",
            "income_statement_present": True,
            "balance_sheet_present": True,
            "cash_flow_statement_present": True,
            "net_profit_parent": 120.0,
            "revenue": 1000.0,
            "revenue_growth": 0.25,
            "operating_cost": 600.0,
            "operating_cash_flow": 125.0,
            "cash_received_from_sales": 980.0,
            "contract_liability_growth": 0.10,
            "receivable_growth": 0.10,
            "finance_expense": 15.0,
            "operating_profit": 100.0,
            "goodwill": 0.0,
            "equity_parent": 1000.0,
        }
    )

    assert result["meta"]["step_results"]["capex"] == "unknown"
    assert result["direction"] == "bullish"
    assert "非核心数据缺口" in result["reasoning"]
