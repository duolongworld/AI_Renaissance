"""
风险预警 Agent 单元测试

用假数据源（通过 config 注入）离线验证 RiskAgent 的规则与聚合逻辑：
  - 正常市场 → neutral
  - 市场踩踏（跌停>100 + 北向流出）→ 流动性一票否决权生效，bearish/high
  - 情绪过热 + 杠杆过热 + 资金流出 → 六维框架 bearish
  - 数据源异常 → 不崩溃，降级
"""

from agents.risk.agent import RiskAgent
from agents.signal import Signal


class FakeMarketSentiment:
    def __init__(self, score=50.0, limit_up=30, limit_down=10, margin_change=0.0, status="success"):
        self._score = score
        self._limit_up = limit_up
        self._limit_down = limit_down
        self._margin_change = margin_change
        self._status = status

    def get_sentiment_data(self):
        if self._status != "success":
            return {"status": "error"}
        return {
            "status": "success",
            "score": self._score,
            "direction": "neutral",
            "raw_data": {
                "limit_up": self._limit_up,
                "limit_down": self._limit_down,
                "margin_change": self._margin_change,
            },
        }


class FakeAkshare:
    def __init__(self, north=10.0, stock_main5=5.0, status="success"):
        self._north = north
        self._stock_main5 = stock_main5
        self._status = status

    def get_market_fund_flow(self, limit=20):
        if self._status != "success":
            return {"status": "error"}
        return {"status": "success", "northbound": {"northbound_net_inflow": self._north}}

    def get_stock_fund_flow(self, stock_code, limit=20):
        if self._status != "success":
            return {"status": "error"}
        return {"status": "success", "summary": {"近5日主力净流入": self._stock_main5}}


class FakeIndustry:
    def get_industry_sentiment(self, stock_code):
        return {"status": "success"}


def _make_agent(market, akshare):
    return RiskAgent(config={
        "market_sentiment_source": market,
        "akshare_source": akshare,
        "industry_sentiment_source": FakeIndustry(),
    })


def test_normal_market_neutral():
    """正常市场：低跌停、资金流入、情绪中性 → neutral，无否决"""
    agent = _make_agent(FakeMarketSentiment(), FakeAkshare())
    sig = agent.analyze("600519")
    assert isinstance(sig, Signal)
    assert sig.direction == "neutral"
    assert sig.signal_type == "risk"
    assert sig.meta["veto_authority"]["active"] is False
    assert sig.meta["risk_level"] == "low"


def test_market_crash_triggers_veto():
    """市场踩踏：跌停>100 且北向净流出 → 流动性一票否决，bearish/high"""
    agent = _make_agent(
        FakeMarketSentiment(limit_down=150, limit_up=5),
        FakeAkshare(north=-80.0, stock_main5=-20.0),
    )
    sig = agent.analyze("600519")
    assert sig.direction == "bearish"
    assert sig.meta["risk_level"] == "high"
    assert sig.meta["veto_authority"]["active"] is True
    assert sig.meta["liquidity_outlook"] == "negative"
    assert sig.meta["needs_human_review"] is True
    assert any("否决" in s for s in sig.signals)


def test_framework_bearish_on_overheat():
    """情绪过热 + 杠杆过热 + 资金流出 → 六维框架 bearish"""
    agent = _make_agent(
        FakeMarketSentiment(score=88.0, margin_change=8.0),
        FakeAkshare(stock_main5=-15.0),
    )
    sig = agent.analyze("600519")
    assert sig.direction == "bearish"
    assert sig.meta["risk_level"] in ("medium", "high")


def test_confidence_in_range_and_uncertainties():
    """置信度合法 + 缺失数据如实写入 uncertainties"""
    agent = _make_agent(FakeMarketSentiment(), FakeAkshare())
    sig = agent.analyze("600519")
    assert 0.0 <= sig.confidence <= 1.0
    joined = " ".join(sig.meta["uncertainties"])
    assert "估值" in joined  # 估值维度缺失被记录
    assert sig.meta["dimensions"]["valuation"]["status"] == "skipped"


def test_data_source_failure_degrades_gracefully():
    """数据源全失败：不崩溃，降级为可用结果"""
    agent = _make_agent(
        FakeMarketSentiment(status="error"),
        FakeAkshare(status="error"),
    )
    sig = agent.analyze("600519")
    assert isinstance(sig, Signal)
    assert sig.direction in ("neutral", "bearish")
    assert 0.0 <= sig.confidence <= 1.0
