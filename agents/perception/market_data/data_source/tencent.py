"""
腾讯自选股数据源 — K线、实时行情
"""

import json
from typing import Dict, Any, List, Optional

import requests
from loguru import logger

from agents.perception.market_data.data_source.base import BaseMarketDataSource
from agents.perception.market_data import config as cfg


class TencentDataSource(BaseMarketDataSource):
    """腾讯自选股 API 数据源"""

    KLINE_FQ_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    KLINE_NFQ_URL = "https://web.ifzq.gtimg.cn/appstock/app/kline/kline"
    REALTIME_URL = "https://qt.gtimg.cn/q="

    def get_kline(
        self,
        code: str,
        period: str = "day",
        count: int = 300,
        fq: str = "qfq",
    ) -> List[Dict[str, Any]]:
        if fq in ("qfq", "hfq"):
            url = self.KLINE_FQ_URL
            param = f"{code},{period},,,{count},{fq}"
        else:
            url = self.KLINE_NFQ_URL
            param = f"{code},{period},,,{count},,"

        try:
            resp = requests.get(
                url, params={"param": param},
                headers=cfg.HEADERS, timeout=cfg.REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f"[TencentDataSource] 获取K线失败: {e}")
            return []

        return self._parse_kline(data, code, period)

    def get_realtime(self, code: str) -> Dict[str, Any]:
        url = f"{self.REALTIME_URL}{code}"
        try:
            resp = requests.get(url, headers=cfg.HEADERS, timeout=cfg.REQUEST_TIMEOUT)
            resp.raise_for_status()
            return self._parse_realtime(resp.text, code)
        except Exception as e:
            logger.error(f"[TencentDataSource] 获取实时行情失败: {e}")
            return {}

    def normalize_code(self, code: str) -> str:
        code = code.strip().lower()
        for prefix in ("sh", "sz", "bj"):
            if code.startswith(prefix):
                return code
        pure = code.lstrip("0") or code
        if code.startswith("6"):
            return f"sh{code}"
        if code.startswith(("0", "3")):
            return f"sz{code}"
        if code.startswith(("8", "4")):
            return f"bj{code}"
        return code

    # ── 内部解析 ──────────────────────────────────────

    def _parse_kline(
        self, data: dict, code: str, period: str
    ) -> List[Dict[str, Any]]:
        stock_data = data.get("data", {}).get(code, {})
        # 腾讯API的key: qfq→qfqday, hfq→hfqday, 不复权→day/week/month
        keys_to_try = [f"qfq{period}", f"hfq{period}", period]
        raw_list = []
        for key in keys_to_try:
            raw_list = stock_data.get(key, [])
            if raw_list:
                break
        if not raw_list:
            return []

        result = []
        for item in raw_list:
            # 腾讯K线格式: [date, open, close, high, low, volume] 或 [date, open, close, high, low, volume, amount]
            if len(item) < 6:
                continue
            result.append({
                "date": item[0],
                "open": float(item[1]),
                "close": float(item[2]),
                "high": float(item[3]),
                "low": float(item[4]),
                "volume": float(item[5]),
            })
        return result

    def _parse_realtime(self, text: str, code: str) -> Dict[str, Any]:
        """
        解析 qt.gtimg.cn 返回的实时行情
        格式: v_sh600519="字段1~字段2~..."
        """
        prefix = f"v_{code}="
        for line in text.strip().split(";"):
            line = line.strip()
            if not line.startswith(prefix):
                continue
            raw = line[len(prefix):].strip('"').strip("'")
            fields = raw.split("~")
            if len(fields) < 50:
                continue

            try:
                current_price = float(fields[3])
                prev_close = float(fields[4])
                change_pct = (
                    (current_price - prev_close) / prev_close * 100
                    if prev_close > 0 else 0.0
                )
                return {
                    "name": fields[1],
                    "code": fields[2],
                    "current_price": current_price,
                    "prev_close": prev_close,
                    "open": float(fields[5]),
                    "volume": float(fields[6]),
                    "turnover_rate": float(fields[38]) if fields[38] else 0.0,
                    "change_pct": round(change_pct, 2),
                    "high": float(fields[33]) if fields[33] else 0.0,
                    "low": float(fields[34]) if fields[34] else 0.0,
                }
            except (ValueError, IndexError):
                continue

        return {}
