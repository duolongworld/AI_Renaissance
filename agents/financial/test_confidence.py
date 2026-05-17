from skills.financial.financial_report_analysis.scripts.analyze_report import build_signal
from agents.financial.agent import FinancialAgent


class FakeFinancialDataSource:
    name = "测试数据源"

    def __init__(self):
        self.calls = []

    def get_financial_data(self, stock_code, report_date=None):
        self.calls.append((stock_code, report_date))
        return {
            "income": [{"REPORT_DATE": report_date, "OPERATE_INCOME": 1.0}],
            "balance": [{"REPORT_DATE": report_date, "CONTRACT_LIAB": 1.0}],
            "cashflow": [{"REPORT_DATE": report_date, "NETCASH_OPERATE": 1.0}],
        }


def test_confidence_exceeds_07_when_neutral_conclusion_is_well_supported():
    result = build_signal(
        {
            "ticker": "TEST",
            "company_name": "测试科技公司",
            "period": "2026Q1",
            "source_type": "data_source",
            "source_name": "测试数据源",
            "income_statement_present": True,
            "balance_sheet_present": True,
            "cash_flow_statement_present": True,
            "net_profit_parent": -100.0,
            "revenue": 1000.0,
            "revenue_growth": 0.8,
            "operating_cost": 650.0,
            "operating_cash_flow": -80.0,
            "cash_received_from_sales": 1200.0,
            "contract_liability_growth": 1.2,
            "contract_liability_qoq": 0.35,
            "receivable_growth": 0.2,
            "receivable_qoq": 0.04,
            "finance_expense": 10.0,
            "operating_profit": -90.0,
            "research_expense": 300.0,
            "research_expense_growth": 0.5,
            "cash_and_equivalents_qoq": -0.05,
            "prepayment_growth": 1.8,
            "prepayment_qoq": 0.6,
            "intangible_asset_growth": 0.7,
            "intangible_asset_qoq": 0.4,
            "total_noncurrent_assets_growth": 0.5,
            "total_noncurrent_assets_qoq": 0.25,
        }
    )

    assert result["direction"] == "neutral"
    assert result["confidence"] > 0.7
    assert result["meta"]["confidence_breakdown"]["trend_confirmation"]["confirmations"]


def test_financial_agent_fetches_extra_period_for_single_quarter_qoq():
    data_source = FakeFinancialDataSource()
    agent = FinancialAgent(
        config={
            "financial_data_source": data_source,
            "report_date": "2026-03-31",
        }
    )

    data = agent._fetch_data("300000")

    assert data_source.calls == [
        ("300000", "2026-03-31"),
        ("300000", "2025-12-31"),
        ("300000", "2025-09-30"),
    ]
    assert data["previous_report_date"] == "2025-12-31"
    assert data["previous_previous_report_date"] == "2025-09-30"
    assert data["previous_period_data"]
    assert data["previous_previous_period_data"]


def test_income_and_cashflow_qoq_are_derived_from_single_quarter_amounts():
    result = build_signal(
        {
            "ticker": "TEST",
            "company_name": "单季拆分测试",
            "period": "2026-03-31",
            "source_type": "data_source",
            "source_name": "测试数据源",
            "balance": [{"CONTRACT_LIAB": 100.0, "ACCOUNTS_RECE": 50.0}],
            "income": [
                {
                    "REPORT_DATE": "2026-03-31",
                    "OPERATE_INCOME": 120.0,
                    "OPERATE_COST": 72.0,
                    "RESEARCH_EXPENSE": 12.0,
                    "PARENT_NETPROFIT": 10.0,
                }
            ],
            "cashflow": [
                {
                    "REPORT_DATE": "2026-03-31",
                    "NETCASH_OPERATE": 30.0,
                    "SALES_SERVICES": 132.0,
                }
            ],
            "previous_period_data": {
                "income": [
                        {
                            "REPORT_DATE": "2025-12-31",
                            "OPERATE_INCOME": 400.0,
                            "OPERATE_COST": 300.0,
                            "RESEARCH_EXPENSE": 40.0,
                        }
                ],
                "cashflow": [
                    {
                        "REPORT_DATE": "2025-12-31",
                        "NETCASH_OPERATE": 100.0,
                        "SALES_SERVICES": 420.0,
                    }
                ],
            },
            "previous_previous_period_data": {
                "income": [
                    {
                        "REPORT_DATE": "2025-09-30",
                        "OPERATE_INCOME": 300.0,
                        "OPERATE_COST": 220.0,
                        "RESEARCH_EXPENSE": 32.0,
                    }
                ],
                "cashflow": [
                    {
                        "REPORT_DATE": "2025-09-30",
                        "NETCASH_OPERATE": 70.0,
                        "SALES_SERVICES": 330.0,
                    }
                ],
            },
        }
    )

    meta = result["meta"]
    qoq_metrics = meta["single_quarter_metrics"]

    assert qoq_metrics["current_quarter"]["revenue"] == 120.0
    assert qoq_metrics["previous_quarter"]["revenue"] == 100.0
    assert qoq_metrics["current_quarter"]["gross_margin"] == 0.4
    assert qoq_metrics["previous_quarter"]["gross_margin"] == 0.2
    assert qoq_metrics["qoq"]["revenue_qoq"] == 0.2
    assert qoq_metrics["qoq"]["research_expense_qoq"] == 0.5
    assert qoq_metrics["qoq"]["gross_margin_qoq"] == 1.0
    assert qoq_metrics["qoq"]["operating_cash_flow_qoq"] == 0.0
    assert not [
        gap
        for gap in meta["data_gaps"]
        if gap["area"] == "sequential_trend" and gap["field"] in qoq_metrics["qoq"]
    ]
