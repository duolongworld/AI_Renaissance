from datetime import date

import pytest

from data_sources.financial_report_supplement import (
    FinancialReportSupplementDataSource,
    extract_financial_report_supplement,
)


REPORT_TEXT = """
测试公司2026年半年度报告全文
11
截至本报告披露日，尚未确认收入的在手订单金额约33.86亿元。
截至本报告披露日，公司光电子及半导体业务板块在手订单金额约24.52亿元。
公司本报告期内已收到同一集团客户累计高达约12.61亿元的订单。
测试公司2026年半年度报告全文
24
公司按照客户需求节奏相应匹配扩产节奏。
在不断提升现有德国、爱沙尼亚、中国生产/组装基地产能的基础上，公司计划增设新的生产/组装基地。
现金流量表补充资料
"""


TABLES = [
    {
        "pdf_page": 19,
        "text": "测试公司2026年半年度报告全文\n18\n",
        "tables": [[
            ["", "营业收入", "营业成本", "毛利率", "营业收入比上年同期增减", "营业成本比上年同期增减", "毛利率比上年同期增减"],
            ["光伏设备及整\n体解决方案", "82,984,888.85", "55,913,459.42", "32.62%", "-53.93%", "-59.76%", "9.76%"],
            ["光电子及半导\n体封测设备", "488,228,395.38", "278,730,609.42", "42.91%", "952.17%", "820.81%", "8.14%"],
        ]],
    },
    {
        "pdf_page": 106,
        "text": "测试公司2026年半年度报告全文\n105\n",
        "tables": [[
            ["补充资料", "本期金额", "上期金额"],
            ["固定资产折旧、油气资产折\n耗、生产性生物资产折旧", "11,402,488.69", "10,682,020.16"],
            ["使用权资产折旧", "2,058,951.25", "666,250.93"],
            ["无形资产摊销", "19,832,493.00", "8,811,535.10"],
            ["长期待摊费用摊销", "154,634.24", "154,634.24"],
        ]],
    },
    {
        "pdf_page": 116,
        "text": "测试公司2026年半年度报告全文\n115\n",
        "tables": [[
            ["项目", "罗博分部", "斐控分部", "分部间抵销", "合计"],
            ["营业收入", "257,941,484.56", "515,776,367.52", "-165,237,740.32", "608,480,111.76"],
            ["其中：对外交易收入", "99,124,998.98", "509,355,112.78", "", "608,480,111.76"],
        ]],
    },
    {
        "pdf_page": 117,
        "text": "测试公司2026年半年度报告全文\n116\n",
        "tables": [[
            ["营业利润/(亏损)", "-32,237,914.90", "38,012,785.75", "1,088,340.69", "6,863,211.54"],
        ]],
    },
]


def test_extracts_orders_capacity_tables_and_depreciation_with_provenance():
    result = extract_financial_report_supplement(REPORT_TEXT, TABLES)
    fields = result["fields"]

    assert fields["order_backlog"] == 3_386_000_000.0
    assert fields["order_backlog_breakdown"] == [
        {"scope": "光电子及半导体业务板块", "value": 2_452_000_000.0}
    ]
    assert fields["signed_orders"] == 1_261_000_000.0
    assert "新的生产/组装基地" in fields["capacity_expansion_plan"]
    assert fields["depreciation_amortization"] == pytest.approx(33_448_567.18)
    assert fields["product_lines"][1]["gross_margin"] == pytest.approx(0.4291)
    assert fields["segments"]["items"][0] == {
        "name": "罗博分部",
        "external_revenue": 99_124_998.98,
        "operating_profit": -32_237_914.90,
    }
    assert fields["segments"]["consolidated"]["operating_profit"] == 6_863_211.54
    assert result["field_sources"]["signed_orders"]["scope"] == "same_customer_group"
    assert result["warnings"] == ["已签订单为特定客户范围披露，不代表公司全部已签订单。"]


def test_report_kind_and_latest_candidates_are_deterministic():
    assert FinancialReportSupplementDataSource.report_kind("2026-06-30") == (2026, "h1")
    assert FinancialReportSupplementDataSource.candidate_report_dates(date(2026, 8, 27))[:2] == [
        "2026-06-30",
        "2026-03-31",
    ]


def test_failed_report_lookup_is_not_cached():
    class RecoveringCninfo:
        def __init__(self):
            self.calls = 0

        def get_periodic_report(self, stock_code, year, kind):
            self.calls += 1
            if self.calls == 1:
                return {"status": "error", "error": "not published yet"}
            return {"status": "success", "report": {"ann_id": "later"}}

    cninfo = RecoveringCninfo()
    source = FinancialReportSupplementDataSource(cninfo, table_reader=lambda _: [])

    assert source._fetch_report("300757", "2026-06-30")["status"] == "error"
    assert source._fetch_report("300757", "2026-06-30")["status"] == "success"
    assert cninfo.calls == 2


def test_data_source_reads_cninfo_file_and_returns_stable_error(tmp_path):
    md_path = tmp_path / "report.md"
    md_path.write_text(REPORT_TEXT, encoding="utf-8")

    class FakeCninfo:
        def get_periodic_report(self, stock_code, year, kind):
            return {
                "status": "success",
                "report": {
                    "ann_id": "1",
                    "ann_date": "20260826",
                    "title": "2026年半年度报告",
                    "md_path": str(md_path),
                    "pdf_path": str(tmp_path / "report.pdf"),
                    "pdf_url": "https://example.test/report.pdf",
                },
            }

    table_reads = []
    source = FinancialReportSupplementDataSource(
        FakeCninfo(), table_reader=lambda path: table_reads.append(path) or TABLES
    )
    result = source.get_financial_supplement("300757.SZ", "2026-06-30")
    cached = source.get_financial_supplement("300757.SZ", "2026-06-30")

    assert result["status"] == "success"
    assert result["source"]["ann_id"] == "1"
    assert result["field_sources"]["order_backlog"]["report_date"] == "2026-06-30"
    assert cached is result
    assert len(table_reads) == 1

    invalid = source.get_financial_supplement("300757", "2026-05-31")
    assert invalid["status"] == "error"
    assert invalid["fields"] == {}
