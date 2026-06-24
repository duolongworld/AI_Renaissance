"""
演示资金流数据源 - 用于开发和测试

当网络无法连接时，使用本地演示数据进行拥挤度分析。
包含真实的数据结构和合理的演示数值。
"""

from typing import Dict, Any, List
from datetime import datetime, timedelta
import pandas as pd
from .base import DataSourceBase


class DemoFundFlowDataSource(DataSourceBase):
    """演示资金流数据源 - 提供本地测试数据"""

    def __init__(self):
        super().__init__(name="演示资金流数据源")

    def get_financial_data(self, stock_code: str, report_date: str = None) -> Dict[str, Any]:
        """未实现 - 演示源仅提供资金流数据"""
        return {}

    def get_market_data(self, stock_code: str, period: str = "daily") -> Dict[str, Any]:
        """未实现 - 演示源仅提供资金流数据"""
        return {}

    def get_fund_flow_data(self, stock_code: str, limit: int = 120) -> Dict[str, Any]:
        """获取演示资金流数据

        Returns:
            同 EastMoneyDataSource.get_fund_flow_data 的返回格式
        """
        records = self._generate_demo_data(stock_code, limit)

        return {
            "status": "success",
            "stock_code": stock_code,
            "count": len(records),
            "recent": records,
            "_source": "demo (local data for testing)"
        }

    def _generate_demo_data(self, stock_code: str, limit: int = 120) -> List[Dict[str, Any]]:
        """生成演示资金流数据

        基于股票代码生成确定性的演示数据，确保每次运行结果一致。
        """
        # 基于股票代码的伪随机种子，确保相同股票每次数据一致
        seed = sum(ord(c) for c in stock_code) % 1000

        records = []
        now = datetime.now()
        skip_count = 0

        # 生成 limit 条记录，从今天向后回溯
        for i in range(limit + skip_count):
            # 计算日期（跳过周末）
            current_date = now - timedelta(days=i)
            # 跳过周末（5=Saturday, 6=Sunday）
            if current_date.weekday() >= 5:
                skip_count += 1
                continue

            date_str = current_date.strftime("%Y-%m-%d")  # 使用标准 ISO 格式

            # 基于日期和 seed 生成伪随机值
            day_seed = (seed + i * 7) % 100

            # 主力净流入 (万元)：在 -5000 到 +5000 之间变化
            net_flow_main = (day_seed - 50) * 100 + (i % 10 - 5) * 50

            # 主力净占比 (%)：基于净流入
            flow_pct = (day_seed - 50) / 10

            # 小单/中单/大单/超大单净流入 (万元)
            small_flow = net_flow_main * 0.2 + (day_seed % 30 - 15) * 10
            medium_flow = net_flow_main * 0.3 + (day_seed % 25 - 12) * 10
            large_flow = net_flow_main * 0.25 + (day_seed % 20 - 10) * 10
            xlarge_flow = net_flow_main * 0.25 + (day_seed % 15 - 7) * 10

            # 对应的占比
            small_pct = flow_pct * 0.2
            medium_pct = flow_pct * 0.3
            large_pct = flow_pct * 0.25
            xlarge_pct = flow_pct * 0.25

            # 收盘价 (¥)：基于股票代码和日期生成
            if stock_code == "600519":  # 贵州茅台
                base_price = 1300
            elif stock_code == "000001":  # 平安银行
                base_price = 10
            else:
                base_price = 50

            close_price = base_price + (day_seed - 50) * 0.5 + (i % 20 - 10) * 0.2

            # 涨跌幅 (%)
            change_pct = (day_seed - 50) / 100 + (i % 10 - 5) / 50

            record = {
                "日期": date_str,
                "主力净流入-净额": float(net_flow_main),
                "小单净流入-净额": float(small_flow),
                "中单净流入-净额": float(medium_flow),
                "大单净流入-净额": float(large_flow),
                "超大单净流入-净额": float(xlarge_flow),
                "主力净流入-净占比": float(flow_pct),
                "小单净流入-净占比": float(small_pct),
                "中单净流入-净占比": float(medium_pct),
                "大单净流入-净占比": float(large_pct),
                "超大单净流入-净占比": float(xlarge_pct),
                "收盘价": float(close_price),
                "涨跌幅": float(change_pct),
            }
            records.append(record)

            if len(records) >= limit:
                break

        return records
