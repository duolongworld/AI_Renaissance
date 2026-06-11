import pandas as pd

from data_sources.akshare import AkshareDataSource


class FakeAkshareDataSource(AkshareDataSource):
    def _request_json(self, url, params, timeout=15):
        if url.endswith("/api/qt/stock/get"):
            return {
                "data": {
                    "f57": "600519",
                    "f58": "贵州茅台",
                    "f84": 1250081601,
                    "f85": 1250081601,
                    "f127": "白酒Ⅱ",
                    "f116": 1570102490856,
                    "f117": 1570102490856,
                    "f189": "20010827",
                    "f43": 1256.0,
                }
            }
        if url.endswith("/api/qt/stock/fflow/daykline/get") and params.get("secid2"):
            return {
                "data": {
                    "klines": [
                        "2026-06-06,100,10,20,30,40,1,0.1,0.2,0.3,0.4,3300,1.0,10000,2.0",
                        "2026-06-09,200,20,40,60,80,2,0.2,0.4,0.6,0.8,3400,1.5,11000,2.5",
                    ]
                }
            }
        if url.endswith("/api/qt/stock/fflow/daykline/get"):
            return {
                "data": {
                    "klines": [
                        "2026-06-06,100,10,20,30,40,1,0.1,0.2,0.3,0.4,1200,1.0,0,0",
                        "2026-06-09,200,20,40,60,80,2,0.2,0.4,0.6,0.8,1256,-0.55,0,0",
                    ]
                }
            }
        if url.endswith("/api/qt/clist/get"):
            if params["stat"] == "1":
                return {
                    "data": {
                        "total": 1,
                        "diff": [
                            {
                                "f14": "白酒",
                                "f3": 1.2,
                                "f62": 1000,
                                "f184": 3.2,
                                "f66": 500,
                                "f69": 1.1,
                                "f72": 300,
                                "f75": 0.8,
                                "f78": -100,
                                "f81": -0.2,
                                "f84": -200,
                                "f87": -0.4,
                                "f204": "贵州茅台",
                            }
                        ],
                    }
                }
            return {
                "data": {
                    "total": 1,
                    "diff": [
                        {
                            "f14": "白酒",
                            "f109": 1.2,
                            "f164": 1000,
                            "f165": 3.2,
                            "f166": 500,
                            "f167": 1.1,
                            "f168": 300,
                            "f169": 0.8,
                            "f170": -100,
                            "f171": -0.2,
                            "f172": -200,
                            "f173": -0.4,
                            "f257": "贵州茅台",
                        }
                    ],
                }
            }
        if url.endswith("/api/data/v1/get"):
            return {
                "result": {
                    "data": [
                        {
                            "TRADE_DATE": "2026-06-09 00:00:00",
                            "BOARD_TYPE": "沪港通",
                            "MUTUAL_TYPE_NAME": "沪股通",
                            "FUNDS_DIRECTION": "北向",
                            "INDEX_NAME": "上证指数",
                            "status": 3,
                            "netBuyAmt": 10000,
                            "dayNetAmtIn": 20000,
                            "dayAmtRemain": 30000,
                            "f104": 100,
                            "f106": 10,
                            "f105": 20,
                            "INDEX_f3": 1.28,
                        },
                        {
                            "TRADE_DATE": "2026-06-09 00:00:00",
                            "BOARD_TYPE": "深港通",
                            "MUTUAL_TYPE_NAME": "深股通",
                            "FUNDS_DIRECTION": "北向",
                            "INDEX_NAME": "深证成指",
                            "status": 3,
                            "netBuyAmt": 30000,
                            "dayNetAmtIn": 40000,
                            "dayAmtRemain": 50000,
                            "f104": 120,
                            "f106": 11,
                            "f105": 21,
                            "INDEX_f3": 2.28,
                        },
                    ]
                }
            }
        raise AssertionError(f"unexpected request: {url} {params}")


def test_stock_basic_info_uses_delay_eastmoney_and_keeps_contract(monkeypatch):
    source = FakeAkshareDataSource()
    monkeypatch.setattr(
        "data_sources.akshare.ak.stock_profile_cninfo",
        lambda symbol: pd.DataFrame(
            [
                {
                    "A股简称": "贵州茅台",
                    "公司名称": "贵州茅台酒股份有限公司",
                    "所属行业": "白酒Ⅱ",
                    "上市日期": "2001-08-27",
                    "入选指数": "上证50,沪深300",
                }
            ]
        ),
    )
    monkeypatch.setattr(
        "data_sources.akshare.ak.stock_hot_keyword_em",
        lambda symbol: pd.DataFrame([{"时间": "2026-06-09", "概念名称": "白酒", "概念代码": "BK0896", "热度": 100}]),
    )

    result = source.get_stock_basic_info("SH600519")

    assert result["status"] == "success"
    assert result["stock_code"] == "600519"
    assert result["stock_name"] == "贵州茅台"
    assert result["profile"]["总市值"] == 1570102490856.0
    assert result["boards"]["入选指数"] == ["上证50", "沪深300"]
    assert result["concepts"][0]["概念名称"] == "白酒"


def test_stock_fund_flow_summary_from_delay_endpoint():
    result = FakeAkshareDataSource().get_stock_fund_flow("600519", limit=1)

    assert result["status"] == "success"
    assert result["total"] == 2
    assert result["recent"][0]["日期"] == "2026年06月09日"
    assert result["summary"]["最新主力净流入"] == 200
    assert result["summary"]["近3日主力净流入"] == 300


def test_sector_fund_flow_supports_today_and_5d_contract(monkeypatch):
    source = FakeAkshareDataSource()
    monkeypatch.setattr(
        source,
        "get_stock_basic_info",
        lambda stock_code, concept_limit=10: {
            "status": "success",
            "stock_code": "600519",
            "stock_name": "贵州茅台",
            "boards": {"行业板块": "白酒"},
            "concepts": [{"概念名称": "白酒"}],
            "profile": {},
        },
    )

    today = source.get_sector_fund_flow("600519", indicator="今日", top_n=1)
    five_days = source.get_sector_fund_flow("600519", indicator="5d", top_n=1)

    assert today["status"] == "success"
    assert today["industry_rankings"][0]["今日主力净流入-净额"] == 1000
    assert today["related_industry_rankings"][0]["名称"] == "白酒"
    assert five_days["indicator"] == "5日"
    assert five_days["industry_rankings"][0]["5日主力净流入-净额"] == 1000


def test_market_fund_flow_aggregates_northbound():
    result = FakeAkshareDataSource().get_market_fund_flow(limit=1)

    assert result["status"] == "success"
    assert result["market_main_flow"]["total"] == 2
    assert result["market_main_flow"]["recent"][0]["日期"] == "2026年06月09日"
    assert result["northbound"]["trade_date"] == "2026年06月09日"
    assert result["northbound"]["northbound_net_buy"] == 4.0
    assert result["northbound"]["northbound_net_inflow"] == 6.0
