"""
data_sources - 统一数据层（开发3组）

不套 Skill 格式，纯 Python 类/函数。
所有数据源封装在此，Agent 只管调用接口，不管数据从哪来。
"""

from .base import DataSourceBase
from .cninfo import CninfoDataSource
from .eastmoney import EastMoneyDataSource
from .eastmoney_guba import EastMoneyGubaDataSource
from .market_sentiment import MarketSentimentDataSource
from .industry_sentiment import IndustrySentimentDataSource
from .community_sentiment import CommunitySentimentDataSource
from .keywords import BULLISH_KEYWORDS, BEARISH_KEYWORDS, calc_sentiment_ratio

__all__ = [
    "CninfoDataSource",
    "DataSourceBase",
    "EastMoneyDataSource",
    "EastMoneyGubaDataSource",
    "MarketSentimentDataSource",
    "IndustrySentimentDataSource",
    "CommunitySentimentDataSource",
    "BULLISH_KEYWORDS",
    "BEARISH_KEYWORDS",
    "calc_sentiment_ratio",
]
