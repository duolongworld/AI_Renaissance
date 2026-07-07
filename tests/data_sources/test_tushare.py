"""
Tushare 数据源单元测试

覆盖基类接口（financial / market / fund_flow）和便捷方法的契约。
"""
import pandas as pd

from data_sources.tushare_source import TushareDataSource


class FakeTushareDataSource(TushareDataSource):
    """模拟 Tushare 数据源，通过覆盖 _get_pro 注入假 pro_api。"""

    _FIXTURES = {
        "stock_basic": pd.DataFrame(
            [
                {
                    "ts_code": "600519.SH",
                    "name": "贵州茅台",
                    "area": "贵州",
                    "industry": "白酒",
                    "list_date": "20010827",
                    "market": "主板",
                    "exchange": "SSE",
                    "is_hs": "N",
                    "list_status": "L",
                }
            ]
        ),
        "income": pd.DataFrame(
            [
                {
                    "ts_code": "600519.SH",
                    "ann_date": "20260401",
                    "end_date": "20260331",
                    "report_type": "1",
                    "comp_type": "1",
                    "total_revenue": 45000000000.0,
                    "revenue": 44000000000.0,
                    "oper_cost": 5000000000.0,
                    "operate_profit": 35000000000.0,
                    "total_profit": 34800000000.0,
                    "income_tax": 8700000000.0,
                    "n_income": 26100000000.0,
                    "n_income_attr_p": 26000000000.0,
                    "basic_eps": 20.8,
                    "diluted_eps": 20.8,
                    "total_revenue_yoy": 15.5,
                    "operate_profit_yoy": 12.0,
                    "n_income_yoy": 10.2,
                    "basic_eps_yoy": 8.5,
                }
            ]
        ),
        "balancesheet": pd.DataFrame(
            [
                {
                    "ts_code": "600519.SH",
                    "ann_date": "20260401",
                    "end_date": "20260331",
                    "report_type": "1",
                    "comp_type": "1",
                    "total_assets": 320000000000.0,
                    "total_liab": 40000000000.0,
                    "total_hldr_eqy_exc_min_int": 280000000000.0,
                    "total_cur_assets": 180000000000.0,
                    "total_cur_liab": 30000000000.0,
                    "money_cap": 80000000000.0,
                    "accounts_receiv": 0.0,
                    "inventories": 35000000000.0,
                    "notes_receiv": 0.0,
                    "accounts_payable": 2000000000.0,
                    "goodwill": 0.0,
                    "total_assets_yoy": 10.0,
                    "total_hldr_eqy_exc_min_int_yoy": 8.0,
                }
            ]
        ),
        "cashflow": pd.DataFrame(
            [
                {
                    "ts_code": "600519.SH",
                    "ann_date": "20260401",
                    "end_date": "20260331",
                    "report_type": "1",
                    "comp_type": "1",
                    "c_fr_sale_sg": 50000000000.0,
                    "n_cashflow_act": 20000000000.0,
                    "n_cashflow_inv_act": -5000000000.0,
                    "n_cashflow_fin_act": -15000000000.0,
                    "free_cashflow": 18000000000.0,
                    "n_cashflow_act_yoy": 5.0,
                }
            ]
        ),
        "daily": pd.DataFrame(
            [
                {
                    "ts_code": "600519.SH",
                    "trade_date": "20260706",
                    "open": 1800.0,
                    "high": 1825.0,
                    "low": 1795.0,
                    "close": 1815.0,
                    "pre_close": 1805.0,
                    "change": 10.0,
                    "pct_chg": 0.55,
                    "vol": 3500000,
                    "amount": 6352500000.0,
                },
                {
                    "ts_code": "600519.SH",
                    "trade_date": "20260707",
                    "open": 1815.0,
                    "high": 1835.0,
                    "low": 1810.0,
                    "close": 1825.0,
                    "pre_close": 1815.0,
                    "change": 10.0,
                    "pct_chg": 0.55,
                    "vol": 3200000,
                    "amount": 5840000000.0,
                },
            ]
        ),
        "moneyflow": pd.DataFrame(
            [
                {
                    "ts_code": "600519.SH",
                    "trade_date": "20260707",
                    "buy_elg_amount": 500000000.0,
                    "buy_lg_amount": 300000000.0,
                    "buy_md_amount": 200000000.0,
                    "buy_sm_amount": 100000000.0,
                    "sell_elg_amount": 400000000.0,
                    "sell_lg_amount": 350000000.0,
                    "sell_md_amount": 250000000.0,
                    "sell_sm_amount": 100000000.0,
                    "net_mf_amount": 0.0,
                    "net_elg_amount": 100000000.0,
                    "net_lg_amount": -50000000.0,
                    "net_md_amount": -50000000.0,
                    "net_sm_amount": 0.0,
                }
            ]
        ),
    }

    def __init__(self, token: str = "fake_token_for_test"):
        super().__init__(token=token)

    def _get_pro(self):
        """返回模拟的 pro_api 对象。"""
        return _FakeTusharePro()


class _FakeTusharePro:
    """模拟 tushare.pro_api 对象。"""

    def stock_basic(self, ts_code=None, **kwargs):
        df = FakeTushareDataSource._FIXTURES["stock_basic"]
        if ts_code:
            df = df[df["ts_code"] == ts_code]
        return df

    def income(self, ts_code=None, **kwargs):
        df = FakeTushareDataSource._FIXTURES["income"]
        if ts_code:
            df = df[df["ts_code"] == ts_code]
        return df

    def balancesheet(self, ts_code=None, **kwargs):
        df = FakeTushareDataSource._FIXTURES["balancesheet"]
        if ts_code:
            df = df[df["ts_code"] == ts_code]
        return df

    def cashflow(self, ts_code=None, **kwargs):
        df = FakeTushareDataSource._FIXTURES["cashflow"]
        if ts_code:
            df = df[df["ts_code"] == ts_code]
        return df

    def daily(self, ts_code=None, **kwargs):
        df = FakeTushareDataSource._FIXTURES["daily"]
        if ts_code:
            df = df[df["ts_code"] == ts_code]
        return df

    def moneyflow(self, ts_code=None, **kwargs):
        df = FakeTushareDataSource._FIXTURES["moneyflow"]
        if ts_code:
            df = df[df["ts_code"] == ts_code]
        return df

    def query(self, api_name, **kwargs):
        """兼容 query 通用调用（token_status 校验使用）。"""
        if api_name == "stock_basic":
            return self.stock_basic(**kwargs)
        raise ValueError(f"unknown api: {api_name}")


# ------------------------------------------------------------------
# 构造函数 / token 管理
# ------------------------------------------------------------------

def test_constructor_with_token():
    source = TushareDataSource(token="test_token")
    assert source.has_token() is True


def test_constructor_without_token_respects_env(monkeypatch):
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    source = TushareDataSource(token=None)
    assert source.has_token() is False


def test_constructor_with_env_token(monkeypatch):
    monkeypatch.setenv("TUSHARE_TOKEN", "env_token")
    source = TushareDataSource()
    assert source.has_token() is True


def test_constructor_token_priority(monkeypatch):
    """构造参数 token 优先于环境变量。"""
    monkeypatch.setenv("TUSHARE_TOKEN", "env_token")
    source = TushareDataSource(token="constructor_token")
    assert source._token == "constructor_token"


# ------------------------------------------------------------------
# 股票代码转换
# ------------------------------------------------------------------

def test_to_ts_code_6_digit_sh():
    source = FakeTushareDataSource()
    assert source._to_ts_code("600519") == "600519.SH"
    assert source._to_ts_code("688981") == "688981.SH"


def test_to_ts_code_6_digit_sz():
    source = FakeTushareDataSource()
    assert source._to_ts_code("000001") == "000001.SZ"
    assert source._to_ts_code("300750") == "300750.SZ"


def test_to_ts_code_with_prefix():
    source = FakeTushareDataSource()
    assert source._to_ts_code("SH600519") == "600519.SH"
    assert source._to_ts_code("SZ000001") == "000001.SZ"


def test_to_ts_code_native_format():
    source = FakeTushareDataSource()
    assert source._to_ts_code("600519.SH") == "600519.SH"


def test_to_ts_code_invalid():
    source = FakeTushareDataSource()
    assert source._to_ts_code("999999") == ""
    assert source._to_ts_code("abc") == ""


# ------------------------------------------------------------------
# 基类接口契约
# ------------------------------------------------------------------

def test_get_financial_data_contract():
    result = FakeTushareDataSource().get_financial_data("600519", report_date="20260331")

    assert result["status"] == "success"
    assert result["source"] == "tushare"
    assert result["dataset"] == "financial_data"
    assert result["stock_code"] == "600519.SH"
    assert result["end_date"] == "20260331"

    income = result["income"]
    assert len(income) == 1
    assert income[0]["total_revenue"] == 45000000000.0
    assert income[0]["basic_eps"] == 20.8

    balance = result["balance"]
    assert len(balance) == 1
    assert balance[0]["total_assets"] == 320000000000.0

    cashflow = result["cashflow"]
    assert len(cashflow) == 1
    assert cashflow[0]["n_cashflow_act"] == 20000000000.0
    assert cashflow[0]["free_cashflow"] == 18000000000.0


def test_get_financial_data_without_report_date():
    result = FakeTushareDataSource().get_financial_data("600519")

    assert result["status"] == "success"
    assert result["end_date"] is not None


def test_get_financial_data_with_invalid_code():
    result = FakeTushareDataSource().get_financial_data("invalid")

    assert result["status"] == "error"
    assert "无法识别股票代码" in result["error"]


def test_get_market_data_contract():
    result = FakeTushareDataSource().get_market_data("600519", period="daily")

    assert result["status"] == "success"
    assert result["source"] == "tushare"
    assert result["dataset"] == "market_data"
    assert result["total"] == 2
    assert result["records"][0]["close"] == 1815.0
    assert result["records"][1]["close"] == 1825.0


def test_get_market_data_unsupported_period():
    result = FakeTushareDataSource().get_market_data("600519", period="weekly")

    assert result["status"] == "error"
    assert "daily" in result["error"]


def test_get_fund_flow_data_contract():
    result = FakeTushareDataSource().get_fund_flow_data("600519")

    assert result["status"] == "success"
    assert result["source"] == "tushare"
    assert result["dataset"] == "fund_flow_data"
    assert result["total"] == 1
    assert result["records"][0]["net_mf_amount"] == 0.0


# ------------------------------------------------------------------
# 便捷方法
# ------------------------------------------------------------------

def test_get_stock_basic():
    result = FakeTushareDataSource().get_stock_basic("600519")

    assert result["status"] == "success"
    assert result["dataset"] == "stock_basic"
    assert result["info"]["name"] == "贵州茅台"
    assert result["info"]["industry"] == "白酒"
    assert result["info"]["area"] == "贵州"


# ------------------------------------------------------------------
# 错误场景
# ------------------------------------------------------------------

def test_no_token_returns_error():
    source = TushareDataSource(token=None)
    # 清除环境变量避免干扰
    if hasattr(source, "_token"):
        source._token = None

    result = source.get_market_data("600519")

    assert result["status"] == "error"
    assert "未配置 Tushare token" in result["error"]
    assert "tushare.pro" in result["error"]


# ------------------------------------------------------------------
# NaN 处理
# ------------------------------------------------------------------

def test_financial_data_nan_to_none():
    source = FakeTushareDataSource()
    source._FIXTURES["income"] = pd.DataFrame(
        [
            {
                "ts_code": "600519.SH",
                "ann_date": "20260401",
                "end_date": "20260331",
                "total_revenue": float("nan"),
                "n_income": 100.0,
            }
        ]
    )

    result = source.get_financial_data("600519")

    assert result["income"][0]["total_revenue"] is None
    assert result["income"][0]["n_income"] == 100.0
