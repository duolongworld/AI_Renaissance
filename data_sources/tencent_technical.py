from __future__ import annotations

"""腾讯财经 K 线数据源。

真实 HTTP 请求、响应解析和本地指标计算集中放在 data_sources，skills/data 仅保留
接口说明与薄脚本包装。
"""

import argparse
import json
import sys
from datetime import datetime
from random import randint
from typing import Any, Dict, List, Optional

try:
    import requests

    HAS_REQUESTS = True
except ImportError:  # pragma: no cover
    HAS_REQUESTS = False


FQKLINE_URL = "http://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
MKLINE_URL = "http://ifzq.gtimg.cn/appstock/app/kline/mkline"
DEFAULT_NUM = 120
DEFAULT_K_TYPE = "day"
DEFAULT_INDICATORS = "ma,boll,rsi"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}


def normalize_code(code: str) -> str:
    code = code.strip().lower().replace(".", "")
    for prefix in ("sh", "sz", "hk", "us"):
        if code.startswith(prefix):
            return code
    if code.isalpha():
        return f"us{code}"
    if code.isdigit():
        if len(code) < 6:
            return f"hk{code}"
        if code.startswith("6"):
            return f"sh{code}"
        if code.startswith(("0", "3")):
            return f"sz{code}"
    return ""


def _random(n: int = 16) -> str:
    return str(randint(10 ** (n - 1), (10**n) - 1))


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_volume(code: str, volume: Optional[float]) -> Optional[float]:
    """统一 A 股成交量为“手”。

    腾讯日 K 对主板/创业板通常返回“手”，但科创板 sh688*** 返回“股”。
    下游 technical agent 和 EastMoney 口径都按“手”消费，因此这里对科创板
    做 /100 归一，避免 debug_ui 再乘 100 时放大 100 倍。
    """
    if volume is None:
        return None
    if code.startswith("sh688"):
        return volume / 100.0
    return volume


def _volume_raw_unit(code: str) -> str:
    return "股" if code.startswith("sh688") else "手"


def fetch_kline(stock_code: str, k_type: str = DEFAULT_K_TYPE, num: int = DEFAULT_NUM) -> Dict[str, Any]:
    code = normalize_code(stock_code)
    if not code:
        return {"status": "error", "stock_code": stock_code, "error": "无法识别的股票代码", "kline": []}
    if not HAS_REQUESTS:
        return {"status": "error", "stock_code": stock_code, "error": "requests 库未安装", "kline": []}
    if k_type.startswith("m") and k_type != "month":
        return _fetch_minute(code, k_type, num)
    return _fetch_daily(code, k_type, num)


def _fetch_daily(code: str, k_type: str, num: int) -> Dict[str, Any]:
    num = min(int(num), 640)
    url = f"{FQKLINE_URL}?_var=kline_{k_type}qfq&param={code},{k_type},,,{num},qfq&r=0.{_random()}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        content = resp.text.split("=", maxsplit=1)[-1]
        data = json.loads(content)
    except Exception as exc:
        return {"status": "error", "stock_code": code, "error": str(exc), "kline": []}

    stock_data = data.get("data", {}).get(code, {})
    if f"qfq{k_type}" in stock_data:
        raw = stock_data[f"qfq{k_type}"]
    elif k_type in stock_data:
        raw = stock_data[k_type]
    else:
        return {"status": "error", "stock_code": code, "error": "K线数据不存在", "kline": []}

    kline = []
    for item in raw:
        if len(item) < 6:
            continue
        raw_volume = _to_float(item[5])
        kline.append(
            {
                "date": item[0],
                "open": _to_float(item[1]),
                "close": _to_float(item[2]),
                "high": _to_float(item[3]),
                "low": _to_float(item[4]),
                "volume": _normalize_volume(code, raw_volume),
                "volume_unit": "手",
                "volume_raw": raw_volume,
                "volume_raw_unit": _volume_raw_unit(code),
            }
        )
    return {
        "status": "success",
        "stock_code": code,
        "k_type": k_type,
        "fetch_time": datetime.now().isoformat(),
        "total": len(kline),
        "kline": kline,
    }


def _fetch_minute(code: str, k_type: str, num: int) -> Dict[str, Any]:
    period = k_type[1:]
    num = min(int(num), 320)
    url = f"{MKLINE_URL}?param={code},m{period},,{num}&_var=m{period}_today&r=0.{_random()}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        content = resp.text.split("=", maxsplit=1)[-1]
        data = json.loads(content)
    except Exception as exc:
        return {"status": "error", "stock_code": code, "error": str(exc), "kline": []}

    raw = data.get("data", {}).get(code, {}).get(f"m{period}", [])
    kline = []
    for item in raw:
        if len(item) < 6:
            continue
        dt = item[0]
        raw_volume = _to_float(item[5])
        kline.append(
            {
                "date": f"{dt[0:4]}-{dt[4:6]}-{dt[6:8]} {dt[8:10]}:{dt[10:12]}",
                "open": _to_float(item[1]),
                "close": _to_float(item[2]),
                "high": _to_float(item[3]),
                "low": _to_float(item[4]),
                "volume": _normalize_volume(code, raw_volume),
                "volume_unit": "手",
                "volume_raw": raw_volume,
                "volume_raw_unit": _volume_raw_unit(code),
            }
        )
    return {
        "status": "success",
        "stock_code": code,
        "k_type": k_type,
        "fetch_time": datetime.now().isoformat(),
        "total": len(kline),
        "kline": kline,
    }


def calc_ma(kline: List[Dict[str, Any]], periods: Optional[List[int]] = None) -> List[Dict[str, Any]]:
    periods = periods or [5, 10, 20, 60]
    closes = [item["close"] for item in kline if item.get("close") is not None]
    for i, item in enumerate(kline):
        item["ma"] = {
            f"ma{p}": round(sum(closes[i - p + 1 : i + 1]) / p, 3) if i >= p - 1 and len(closes) >= p else None
            for p in periods
        }
    return kline


def calc_boll(kline: List[Dict[str, Any]], period: int = 20, num_std: float = 2.0) -> List[Dict[str, Any]]:
    closes = [item["close"] for item in kline if item.get("close") is not None]
    for i, item in enumerate(kline):
        if i >= period - 1 and len(closes) >= period:
            window = closes[i - period + 1 : i + 1]
            middle = sum(window) / period
            variance = sum((close - middle) ** 2 for close in window) / period
            std = variance**0.5
            item["boll"] = {
                "upper": round(middle + num_std * std, 3),
                "middle": round(middle, 3),
                "lower": round(middle - num_std * std, 3),
            }
        else:
            item["boll"] = {"upper": None, "middle": None, "lower": None}
    return kline


def calc_rsi(kline: List[Dict[str, Any]], periods: Optional[List[int]] = None) -> List[Dict[str, Any]]:
    periods = periods or [6, 12, 14, 24]
    closes = [item["close"] for item in kline if item.get("close") is not None]
    changes = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    for i, item in enumerate(kline):
        rsi_values = {}
        for period in periods:
            if i < period or i > len(changes):
                rsi_values[f"rsi{period}"] = None
                continue
            window = changes[i - period : i]
            gains = [change for change in window if change > 0]
            losses = [-change for change in window if change < 0]
            avg_gain = sum(gains) / period if gains else 0
            avg_loss = sum(losses) / period if losses else 0
            rsi_values[f"rsi{period}"] = 100.0 if avg_loss == 0 else round(100 - 100 / (1 + avg_gain / avg_loss), 2)
        item["rsi"] = rsi_values
    return kline


def fetch_kline_with_indicators(
    stock_code: str,
    k_type: str = DEFAULT_K_TYPE,
    num: int = DEFAULT_NUM,
    indicators: str = DEFAULT_INDICATORS,
) -> Dict[str, Any]:
    result = fetch_kline(stock_code, k_type, num)
    if result.get("status") != "success" or not result.get("kline"):
        return result

    kline = result["kline"]
    indicator_list = [item.strip().lower() for item in indicators.split(",") if item.strip()]
    if "ma" in indicator_list:
        kline = calc_ma(kline)
    if "boll" in indicator_list:
        kline = calc_boll(kline)
    if "rsi" in indicator_list:
        kline = calc_rsi(kline)
    result["kline"] = kline
    result["indicators"] = indicator_list
    return result


class TencentTechnicalDataSource:
    """面向业务代码的腾讯财经技术行情数据源。"""

    def fetch_kline(self, stock_code: str, k_type: str = DEFAULT_K_TYPE, num: int = DEFAULT_NUM) -> Dict[str, Any]:
        return fetch_kline(stock_code, k_type, num)

    def fetch_kline_with_indicators(
        self,
        stock_code: str,
        k_type: str = DEFAULT_K_TYPE,
        num: int = DEFAULT_NUM,
        indicators: str = DEFAULT_INDICATORS,
    ) -> Dict[str, Any]:
        return fetch_kline_with_indicators(stock_code, k_type, num, indicators)


def main() -> None:
    parser = argparse.ArgumentParser(description="腾讯财经 K线数据获取 + 技术指标计算")
    parser.add_argument("--stock_code", required=True, help="股票代码（如 600519）")
    parser.add_argument("--k_type", default=DEFAULT_K_TYPE, help="K线周期：day/week/month/m1/m5/m15/m30/m60")
    parser.add_argument("--num", type=int, default=DEFAULT_NUM, help="获取K线数量")
    parser.add_argument("--indicators", default=DEFAULT_INDICATORS, help="技术指标，逗号分隔（ma,boll,rsi）")
    parser.add_argument("--raw", action="store_true", help="仅输出K线原始数据，不计算指标")
    args = parser.parse_args()

    result = fetch_kline(args.stock_code, args.k_type, args.num) if args.raw else fetch_kline_with_indicators(
        args.stock_code, args.k_type, args.num, args.indicators
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("status") != "success":
        sys.exit(1)


if __name__ == "__main__":
    main()
