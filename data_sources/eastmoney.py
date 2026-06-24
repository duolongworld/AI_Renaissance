"""
东方财富数据源 - 从 FinancialReportAgent 提取的 API 调用逻辑

开发3组维护。封装东方财富公开 API，供各 Agent 调用。
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
import time
import re

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

from .base import DataSourceBase


class EastMoneyDataSource(DataSourceBase):
    """
    东方财富数据源

    封装东方财富公开 API。

    已实现：
    - 三大财务报表（资产负债表、利润表、现金流量表）
    - 资金流向数据（个股主力资金流）

    计划实现：
    - 行情数据
    """

    BASE_URL = "https://emweb.eastmoney.com/NewFinanceAnalysis"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Referer": "https://emweb.eastmoney.com/",
    }

    # 东方财富 API 端点
    EASTMONEY_HIS_HOST = "http://push2his.eastmoney.com"
    EASTMONEY_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://data.eastmoney.com/",
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

    def get_fund_flow_data(self, stock_code: str, limit: int = 120) -> Dict[str, Any]:
        """获取个股主力资金流向数据

        Args:
            stock_code: 股票代码（如 '600519'）
            limit: 返回记录数

        Returns:
            {
                "status": "success" | "error",
                "stock_code": "600519",
                "recent": [
                    {
                        "日期": "2026-06-16",
                        "主力净流入-净额": 123456.78,
                        "主力净流入-净占比": 1.23,
                        ...
                    },
                    ...
                ],
                "error": "error message" (if status == error)
            }
        """
        if not HAS_REQUESTS or not HAS_PANDAS:
            return {
                "status": "error",
                "stock_code": stock_code,
                "error": "依赖库缺失：需要 requests 和 pandas"
            }

        code, market = self._normalize_stock_code(stock_code)
        if not code:
            return {
                "status": "error",
                "stock_code": stock_code,
                "error": f"无法识别股票代码：{stock_code}"
            }

        try:
            # 从东方财富获取资金流数据
            df = self._fetch_fund_flow_from_eastmoney(code, market)

            if df is None or len(df) == 0:
                return {
                    "status": "error",
                    "stock_code": stock_code,
                    "error": f"未获取到股票 {stock_code} 的资金流数据"
                }

            # 只返回最近的 limit 条记录
            recent_records = df.head(limit).to_dict('records')

            return {
                "status": "success",
                "stock_code": stock_code,
                "count": len(recent_records),
                "recent": recent_records
            }

        except Exception as e:
            self.log(f"获取资金流数据异常：{e}", "error")
            return {
                "status": "error",
                "stock_code": stock_code,
                "error": f"东方财富 API 获取失败：{str(e)}"
            }

    def _normalize_stock_code(self, stock_code: str) -> tuple:
        """规范化股票代码，返回 (code, market)

        Returns:
            (code, market): 如 ('600519', 'sh') 或 ('000001', 'sz')
        """
        code = str(stock_code).strip()
        # 去掉市场前缀（如果有）
        if '.' in code:
            market_prefix, code = code.split('.')
            code = code.lstrip('0')
        else:
            code = code.lstrip('0')

        # 判断市场
        if code.startswith(('6', '9')):
            market = 'sh'  # 上交所
        elif code.startswith(('0', '3')):
            market = 'sz'  # 深交所
        elif code.startswith(('8', '4')):
            market = 'bj'  # 北交所
        else:
            return None, None

        return code, market

    def _fetch_fund_flow_from_eastmoney(self, code: str, market: str) -> Optional[pd.DataFrame]:
        """从东方财富获取原始资金流数据"""
        market_map = {"sh": 1, "sz": 0, "bj": 0}

        url = f"{self.EASTMONEY_HIS_HOST}/api/qt/stock/fflow/daykline/get"
        params = {
            "lmt": "0",
            "klt": "101",  # 日K
            "secid": f"{market_map.get(market, 1)}.{code}",
            "fields1": "f1,f2,f3,f7",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
            "ut": "b2884a393a59ad64002292a3e90d46a5",
            "_": int(time.time() * 1000),
        }

        try:
            resp = requests.get(
                url,
                params=params,
                headers=self.EASTMONEY_HEADERS,
                timeout=15
            )
            resp.raise_for_status()
            data_json = resp.json()

        except Exception as e:
            self.log(f"东方财富 API 请求失败：{e}", "error")
            raise

        # 解析响应
        klines = ((data_json.get("data") or {}).get("klines")) or []
        if not klines:
            raise ValueError(f"东方财富未返回资金流数据：{code}")

        # 构造 DataFrame
        rows = [item.split(",") for item in klines]
        df = pd.DataFrame(rows)

        # 设置列名
        df.columns = [
            "日期",
            "主力净流入-净额",
            "小单净流入-净额",
            "中单净流入-净额",
            "大单净流入-净额",
            "超大单净流入-净额",
            "主力净流入-净占比",
            "小单净流入-净占比",
            "中单净流入-净占比",
            "大单净流入-净占比",
            "超大单净流入-净占比",
            "收盘价",
            "涨跌幅",
        ]

        # 数据类型转换
        numeric_cols = [col for col in df.columns if col != "日期"]
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        # 按日期排序（最新在前）
        df = df.sort_values("日期", ascending=False).reset_index(drop=True)

        return df

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
