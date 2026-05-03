"""
数据源抽象基类 — 所有行情数据源的统一接口
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional


class BaseMarketDataSource(ABC):
    """行情数据源基类，子类需实现 get_kline / get_realtime / normalize_code"""

    @abstractmethod
    def get_kline(
        self,
        code: str,
        period: str = "day",
        count: int = 300,
        fq: str = "qfq",
    ) -> List[Dict[str, Any]]:
        """
        获取K线数据

        Args:
            code: 带市场前缀的股票代码，如 sh600519
            period: day / week / month
            count: 返回条数
            fq: qfq=前复权, hfq=后复权, ""=不复权

        Returns:
            [{"date": str, "open": float, "close": float,
              "high": float, "low": float, "volume": float}, ...]
        """
        ...

    @abstractmethod
    def get_realtime(self, code: str) -> Dict[str, Any]:
        """
        获取实时行情摘要

        Returns:
            {"name": str, "current_price": float, "change_pct": float,
             "turnover_rate": float, "volume": float, ...}
        """
        ...

    @abstractmethod
    def normalize_code(self, code: str) -> str:
        """
        将用户输入的股票代码转为本数据源需要的格式

        Args:
            code: 600519 / sh600519 / SH600519

        Returns:
            数据源要求的格式，如 "sh600519"
        """
        ...
