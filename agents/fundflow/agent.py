"""
资金流向 Agent - 专家3组

signal_type: fundflow
Skill 域: skills/fundflow/
核心能力：主力资金追踪、北向资金、聪明钱动向、资金拥挤度四象限诊断
"""

import sys
import os
import pandas as pd
from typing import Optional
from agents.base import BaseAgent
from agents.signal import Signal, neutral_signal
from data_sources import EastMoneyDataSource
from data_sources.tencent_technical import TencentTechnicalDataSource
from data_sources.demo_fund_flow import DemoFundFlowDataSource

# 添加项目路径便于导入 compute_state2x2_v2
PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


class FundflowAgent(BaseAgent):
    """资金流向 Agent（专家3组）"""

    signal_type = "fundflow"

    def __init__(self, config: Optional[dict] = None):
        super().__init__(name="资金流向Agent", config=config or {})
        self.em_source = EastMoneyDataSource()
        self.tencent_source = TencentTechnicalDataSource()
        self.demo_source = DemoFundFlowDataSource()  # 降级方案
        self.load_skills_from_domain("fundflow")
        self.load_skills_from_domain("data")

    def analyze(self, stock_code: str) -> Signal:
        """分析资金流向信号，包含拥挤度四象限诊断"""
        self.log(f"开始资金流向分析：{stock_code}")

        try:
            # 获取资金流数据（优先东方财富，降级到演示数据）
            self.log(f"从东方财富获取股票 {stock_code} 资金流数据...")
            fund_flow_result = self.em_source.get_fund_flow_data(stock_code, limit=120)

            # 如果东方财富失败，使用演示数据
            if fund_flow_result.get('status') != 'success':
                self.log(f"东方财富获取失败，切换到演示数据源...", level="warning")
                fund_flow_result = self.demo_source.get_fund_flow_data(stock_code, limit=120)
                self.log(f"使用演示数据（用于测试）", level="info")

            if fund_flow_result.get('status') != 'success':
                self.log(f"资金流数据获取失败: {fund_flow_result.get('error', 'unknown')}", level="error")
                return neutral_signal(
                    confidence=0.1,
                    reasoning=f"无法获取资金流数据：{fund_flow_result.get('error', 'unknown')}",
                    source=self.name,
                    stock_code=stock_code,
                    signal_type=self.signal_type,
                )

            # 获取K线数据（从腾讯）
            self.log(f"从腾讯获取股票 {stock_code} K线数据...")
            kline_result = self.tencent_source.fetch_kline(stock_code, k_type="day", num=120)

            if kline_result.get('status') != 'success':
                self.log(f"K线数据获取失败: {kline_result.get('error', 'unknown')}", level="warning")
                return neutral_signal(
                    confidence=0.1,
                    reasoning=f"无法获取K线数据：{kline_result.get('error', 'unknown')}",
                    source=self.name,
                    stock_code=stock_code,
                    signal_type=self.signal_type,
                )

            # 合并数据用于拥挤度计算
            fund_flow_records = fund_flow_result.get('recent', [])
            kline_records = kline_result.get('kline', [])

            if not fund_flow_records or not kline_records:
                self.log("数据记录为空", level="warning")
                return neutral_signal(
                    confidence=0.1,
                    reasoning="获取的资金流或K线数据为空",
                    source=self.name,
                    stock_code=stock_code,
                    signal_type=self.signal_type,
                )

            # 转换为 DataFrame 进行拥挤度分析
            df_flow = pd.DataFrame(fund_flow_records)
            df_kline = pd.DataFrame(kline_records)

            # 标准化列名（资金流数据已经是中文列名）
            df_flow['Date'] = pd.to_datetime(df_flow['日期'])
            df_flow['NetAmountMain'] = pd.to_numeric(df_flow['主力净流入-净额'], errors='coerce')

            df_kline['Date'] = pd.to_datetime(df_kline['date'])
            df_kline['Close'] = pd.to_numeric(df_kline['close'], errors='coerce')
            df_kline['Volume'] = pd.to_numeric(df_kline['volume'], errors='coerce')

            # 合并数据
            df = df_flow[['Date', 'NetAmountMain']].merge(
                df_kline[['Date', 'Close', 'Volume']],
                on='Date',
                how='left'
            )
            df = df.sort_values('Date').reset_index(drop=True)
            df = df.dropna(subset=['Close', 'Volume', 'NetAmountMain'])

            if len(df) < 30:
                self.log(f"数据不足：仅 {len(df)} 行", level="warning")
                return neutral_signal(
                    confidence=0.15,
                    reasoning=f"可用的合并数据不足 30 行，仅 {len(df)} 行",
                    source=self.name,
                    stock_code=stock_code,
                    signal_type=self.signal_type,
                )

            self.log(f"成功合并数据：{len(df)} 行")

            # 导入并执行拥挤度四象限诊断
            from skills.fundflow.crowding_state2x2.scripts.compute_state2x2_v2 import build_signal

            self.log("开始计算拥挤度四象限状态...")
            result = build_signal(stock_code, df)
            signal_data = result[0]

            # 转换为 Signal 对象
            signal = Signal(
                direction=signal_data.get("direction", "neutral"),
                confidence=signal_data.get("confidence", 0.3),
                reasoning=signal_data.get("reasoning", ""),
                signals=signal_data.get("signals", []),
                source=signal_data.get("source", "crowding_state2x2"),
                signal_type=signal_data.get("signal_type", self.signal_type),
                stock_code=stock_code,
                weight=signal_data.get("weight", 1.0),
                meta=signal_data.get("meta", {}),
            )

            self.log(f"拥挤度分析完成: {signal.direction} (confidence={signal.confidence})")
            return signal

        except Exception as e:
            self.log(f"拥挤度分析异常: {e}", level="error")
            import traceback
            self.log(traceback.format_exc(), level="debug")

            # 降级返回中性信号
            return neutral_signal(
                confidence=0.1,
                reasoning=f"资金流向分析异常: {str(e)[:100]}",
                source=self.name,
                stock_code=stock_code,
                signal_type=self.signal_type,
            )
