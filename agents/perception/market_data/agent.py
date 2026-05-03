"""
行情数据Agent — 获取K线、技术指标、筹码分布

数据源通过 config["source"] 指定，默认 "tencent"。
返回 Signal(direction="neutral")，所有数据在 meta 中供 research 层消费。
"""

from typing import Dict, Any, Optional

import pandas as pd
from loguru import logger

from agents.base import BaseAgent
from agents.signal import Signal, neutral_signal
from agents.perception.market_data.data_source import get_data_source, DEFAULT_SOURCE
from agents.perception.market_data import config as cfg
from agents.perception.market_data.indicators import (
    calc_ma, calc_boll, calc_rsi, calc_chip_distribution, calc_volume_ma,
)


class MarketDataAgent(BaseAgent):
    """
    行情数据Agent

    获取K线数据并计算技术指标（MA/BOLL/RSI/筹码分布），
    返回包含完整行情数据的 Signal 对象。
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(name="行情数据Agent", config=config or {})
        source_name = self.config.get("source", DEFAULT_SOURCE)
        self.data_source = get_data_source(source_name)
        self.log(f"数据源: {source_name}")

    def analyze(
        self,
        stock_code: str,
        period: str = "day",
        count: int = 300,
    ) -> Signal:
        """
        获取行情数据并计算技术指标

        Args:
            stock_code: 股票代码，如 600519 / sh600519
            period: K线周期 day/week/month
            count: K线条数

        Returns:
            Signal: direction="neutral"，meta 中包含所有行情数据
        """
        code = self.data_source.normalize_code(stock_code)
        self.log(f"获取 {code} 行情数据 (period={period}, count={count})")

        # 1. 获取前复权K线（用于技术指标）
        kline_fq = self.data_source.get_kline(code, period, count, fq="qfq")
        if not kline_fq:
            return self._error_signal(code, "获取K线数据失败")

        # 2. 获取不复权K线（用于筹码分布，真实交易价格）
        kline_nfq = self.data_source.get_kline(code, period, count, fq="")

        # 3. 获取实时行情
        realtime = self.data_source.get_realtime(code)

        # 4. 计算技术指标
        closes = pd.Series([k["close"] for k in kline_fq], dtype=float)
        ma_data = calc_ma(closes, self.config.get("ma_periods", cfg.MA_PERIODS))
        boll_data = calc_boll(
            closes,
            self.config.get("boll_period", cfg.BOLL_PERIOD),
            self.config.get("boll_std_dev", cfg.BOLL_STD_DEV),
        )
        rsi_data = calc_rsi(closes, self.config.get("rsi_periods", cfg.RSI_PERIODS))

        # 5. 计算成交量均线
        volumes = pd.Series([k["volume"] for k in kline_fq], dtype=float)
        volume_ma_data = calc_volume_ma(volumes)

        # 6. 计算筹码分布（使用不复权数据）
        chip_kline = kline_nfq if kline_nfq else kline_fq
        chip_data = calc_chip_distribution(
            chip_kline,
            self.config.get("chip_days", cfg.CHIP_DAYS),
            self.config.get("chip_bins", cfg.CHIP_PRICE_BINS),
        )

        self.log(
            f"获取到 {len(kline_fq)} 条K线，"
            f"筹码分布支撑位={chip_data['support_price']}，"
            f"压力位={chip_data['pressure_price']}"
        )

        # 7. 构建stock_info
        stock_info = self._build_stock_info(realtime, kline_fq)

        return neutral_signal(
            confidence=1.0,
            reasoning=f"获取 {code} 行情数据成功，共 {len(kline_fq)} 条K线",
            source=self.name,
            stock_code=code,
            signal_type="technical",
            meta={
                "output_version": "0.1",
                "kline": kline_fq,
                "ma": ma_data,
                "boll": boll_data,
                "rsi": rsi_data,
                "volume_ma": volume_ma_data,
                "chip": chip_data,
                "stock_info": stock_info,
                "source": self.config.get("source", DEFAULT_SOURCE),
                "period": period,
                "count": count,
            },
        )

    def _build_stock_info(
        self, realtime: Dict[str, Any], kline: list
    ) -> Dict[str, Any]:
        """构建股票基本信息"""
        info = {
            "name": "",
            "current_price": 0.0,
            "prev_close": 0.0,
            "change_pct": 0.0,
            "turnover_rate": 0.0,
            "volume": 0.0,
            "high": 0.0,
            "low": 0.0,
        }
        if realtime:
            info.update(realtime)
        elif kline:
            last = kline[-1]
            prev = kline[-2] if len(kline) >= 2 else last
            info["current_price"] = last["close"]
            info["prev_close"] = prev["close"]
            info["high"] = last["high"]
            info["low"] = last["low"]
            info["volume"] = last["volume"]
            if prev["close"] > 0:
                info["change_pct"] = round(
                    (last["close"] - prev["close"]) / prev["close"] * 100, 2
                )
        return info

    def _error_signal(self, code: str, reason: str) -> Signal:
        return neutral_signal(
            confidence=0.1,
            reasoning=reason,
            source=self.name,
            stock_code=code,
            signal_type="technical",
            meta={"error": reason, "needs_human_review": True},
        )
