"""
data_sources - 统一数据层（开发3组）

不套 Skill 格式，纯 Python 类/函数。
所有数据源封装在此，Agent 只管调用接口，不管数据从哪来。
"""

from .base import DataSourceBase
from .akshare import AkshareDataSource
from .cninfo import CninfoDataSource
from .eastmoney import EastMoneyDataSource
from .eastmoney_guba import EastMoneyGubaDataSource
from .market_sentiment import MarketSentimentDataSource
from .industry_sentiment import IndustrySentimentDataSource

__all__ = [
    "CninfoDataSource",
    "DataSourceBase",
    "AkshareDataSource",
    "EastMoneyDataSource",
    "EastMoneyGubaDataSource",
    "MarketSentimentDataSource",
    "IndustrySentimentDataSource",
]
