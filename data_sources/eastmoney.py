"""
东方财富数据源 - 从 FinancialReportAgent 提取的 API 调用逻辑

开发3组维护。封装东方财富公开 API，供各 Agent 调用。
"""

from typing import Dict, Any, Optional
from datetime import datetime

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

from .base import DataSourceBase


class EastMoneyDataSource(DataSourceBase):
    """
    东方财富数据源

    封装东方财富 NewFinanceAnalysis API，提供：
    - 三大财务报表（资产负债表、利润表、现金流量表）
    - 行情数据
    - 资金流向数据
    """

    BASE_URL = "https://emweb.eastmoney.com/NewFinanceAnalysis"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Referer": "https://emweb.eastmoney.com/",
    }

    def __init__(self):
        super().__init__(name="东方财富数据源")

    def get_financial_data(self, stock_code: str, report_date: Optional[str] = None) -> Dict[str, Any]:
        """获取三大财务报表"""
        eastmoney_code = self.normalize_code(stock_code)
        if not eastmoney_code:
            self.log(f"无法识别股票代码：{stock_code}", "error")
            return {}

        if report_date is None:
            report_date = self._get_latest_report_date()

        if not HAS_REQUESTS:
            self.log("requests 库未安装，无法获取数据", "error")
            return {}

        urls = {
            "balance":   f"{self.BASE_URL}/zcfzbAjaxNew?companyType=4&reportDateType=0&reportType=1&dates={report_date}&code={eastmoney_code}",
            "income":    f"{self.BASE_URL}/lrbAjaxNew?companyType=4&reportDateType=0&reportType=1&dates={report_date}&code={eastmoney_code}",
            "cashflow":  f"{self.BASE_URL}/xjllbAjaxNew?companyType=4&reportDateType=0&reportType=1&dates={report_date}&code={eastmoney_code}",
        }

        results = {}
        for sheet_name, url in urls.items():
            try:
                resp = requests.get(url, headers=self.HEADERS, timeout=10)
                resp.raise_for_status()
                results[sheet_name] = resp.json()
                self.log(f"获取{sheet_name}数据成功：{eastmoney_code}")
            except Exception as e:
                self.log(f"获取{sheet_name}数据失败：{e}", "error")
                results[sheet_name] = {}

        return results

    def get_market_data(self, stock_code: str, period: str = "daily") -> Dict[str, Any]:
        """获取行情数据"""
        eastmoney_code = self.normalize_code(stock_code)
        if not eastmoney_code:
            return {}

        # TODO: 开发3组实现行情数据接口
        self.log(f"行情数据接口待实现：{eastmoney_code}")
        return {}

    def get_fund_flow_data(self, stock_code: str) -> Dict[str, Any]:
        """获取资金流向数据"""
        eastmoney_code = self.normalize_code(stock_code)
        if not eastmoney_code:
            return {}

        # TODO: 开发3组实现资金流向接口
        self.log(f"资金流向接口待实现：{eastmoney_code}")
        return {}

    def _get_latest_report_date(self) -> str:
        """根据当前日期推算最新可用报告期"""
        today = datetime.now()
        if today >= datetime(today.year + 1, 4, 30):
            return f"{today.year}-12-31"
        elif today >= datetime(today.year, 10, 31):
            return f"{today.year}-09-30"
        elif today >= datetime(today.year, 8, 31):
            return f"{today.year}-06-30"
        elif today >= datetime(today.year, 4, 30):
            return f"{today.year}-03-31"
        else:
            return f"{today.year - 1}-12-31"
