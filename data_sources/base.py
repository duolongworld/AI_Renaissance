"""
数据源基类 - 所有数据源的父类

开发3组统一封装，Agent 只调接口不关心数据来源。
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from loguru import logger


class DataSourceBase(ABC):
    """
    数据源基类

    子类需要实现:
    - get_financial_data(): 获取财务数据（三张表）
    - get_market_data(): 获取行情数据
    - get_fund_flow_data(): 获取资金流向数据

    所有方法返回 dict，失败返回空 dict。
    """

    def __init__(self, name: str):
        self.name = name
        logger.info(f"[数据源] {name} 初始化完成")

    @abstractmethod
    def get_financial_data(self, stock_code: str, report_date: Optional[str] = None) -> Dict[str, Any]:
        """
        获取财务数据（资产负债表、利润表、现金流量表）

        Args:
            stock_code: 股票代码（如 600519、SZ300757）
            report_date: 报告期（如 2024-09-30），不传则自动获取最新

        Returns:
            {"balance": {...}, "income": {...}, "cashflow": {...}}
        """
        pass

    @abstractmethod
    def get_market_data(self, stock_code: str, period: str = "daily") -> Dict[str, Any]:
        """
        获取行情数据

        Args:
            stock_code: 股票代码
            period: 周期 (daily/weekly/monthly)

        Returns:
            行情数据 dict
        """
        pass

    @abstractmethod
    def get_fund_flow_data(self, stock_code: str) -> Dict[str, Any]:
        """
        获取资金流向数据

        Args:
            stock_code: 股票代码

        Returns:
            资金流向数据 dict
        """
        pass

    def normalize_code(self, code: str) -> str:
        """
        标准化股票代码

        600519 -> SH600519
        000001 -> SZ000001
        300757 -> SZ300757
        """
        code = code.strip().upper()
        if code.startswith("SH") or code.startswith("SZ"):
            return code
        if code.startswith("6"):
            return f"SH{code}"
        if code.startswith(("0", "3")):
            return f"SZ{code}"
        return ""

    def log(self, message: str, level: str = "info"):
        """统一日志"""
        getattr(logger, level)(f"[{self.name}] {message}")
