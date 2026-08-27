from agents.financial.agent import FinancialAgent


class FakeStatements:
    name = "测试三表数据源"

    def __init__(self):
        self.calls = []

    def get_financial_data(self, stock_code, report_date=None):
        self.calls.append((stock_code, report_date))
        return {
            "balance": [{"REPORT_DATE": report_date, "CONTRACT_LIAB": 100.0}],
            "income": [{"REPORT_DATE": report_date, "OPERATE_INCOME": 200.0}],
            "cashflow": [{"REPORT_DATE": report_date, "CONSTRUCT_LONG_ASSET": 50.0}],
        }


class FakeSupplement:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def get_financial_supplement(self, stock_code, report_date):
        self.calls.append((stock_code, report_date))
        return self.result


def test_financial_agent_merges_current_cninfo_fields_once_without_overriding_statements():
    statements = FakeStatements()
    supplement = FakeSupplement(
        {
            "status": "success",
            "source": {"source_name": "CNINFO", "ann_id": "1225507370"},
            "fields": {
                "order_backlog": 3_386_000_000.0,
                "depreciation_amortization": 33_448_567.18,
                "segments": {"items": []},
            },
            "field_sources": {},
        }
    )
    agent = FinancialAgent(
        config={
            "financial_data_source": statements,
            "financial_report_data_source": supplement,
            "report_date": "2026-06-30",
            "include_previous_period": True,
            "include_single_quarter_periods": True,
        }
    )

    data = agent._fetch_data("300757")

    assert statements.calls == [
        ("300757", "2026-06-30"),
        ("300757", "2026-03-31"),
        ("300757", "2025-12-31"),
    ]
    assert supplement.calls == [("300757", "2026-06-30")]
    assert data["order_backlog"] == 3_386_000_000.0
    assert data["depreciation_amortization"] == 33_448_567.18
    assert data["financial_report_supplement"]["source"]["ann_id"] == "1225507370"
    assert "financial_report_supplement" not in data["previous_period_data"]


def test_financial_agent_keeps_statement_analysis_when_cninfo_fails():
    statements = FakeStatements()
    supplement = FakeSupplement(
        {"status": "error", "fields": {}, "error": "cninfo unavailable"}
    )
    agent = FinancialAgent(
        config={
            "financial_data_source": statements,
            "financial_report_data_source": supplement,
            "report_date": "2026-06-30",
            "include_previous_period": False,
        }
    )

    data = agent._fetch_data("300757")

    assert data["balance"]
    assert data["income"]
    assert data["cashflow"]
    assert data["financial_report_supplement"]["status"] == "error"
    assert "order_backlog" not in data


def test_report_supplement_provenance_reaches_signal_meta():
    statements = FakeStatements()
    supplement = FakeSupplement(
        {
            "status": "success",
            "source": {"source_name": "CNINFO", "ann_id": "1"},
            "fields": {"depreciation_amortization": 25.0},
            "field_sources": {
                "depreciation_amortization": {"report_date": "2026-06-30", "unit": "CNY"}
            },
        }
    )
    agent = FinancialAgent(
        config={
            "financial_data_source": statements,
            "financial_report_data_source": supplement,
            "report_date": "2026-06-30",
            "include_previous_period": False,
        }
    )

    signal = agent.analyze("300757")

    assert signal.meta["financial_report_supplement"]["source"]["ann_id"] == "1"
    assert signal.meta["financial_agent_version"] == "0.3.0"
