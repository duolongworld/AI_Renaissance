#!/usr/bin/env python3
"""
腾讯财经 K线数据获取 + 技术指标计算脚本

从 ifzq.gtimg.cn 获取股票 K线数据（OHLCV），
本地计算 MA/BOLL/RSI 技术指标，输出结构化 JSON。

支持市场：
  A股（上交所/深交所）、港股、美股

使用方式：
    python fetch_kline.py --stock_code 600519 --k_type day --num 120
    python fetch_kline.py --stock_code 00700 --k_type day --num 120
    python fetch_kline.py --stock_code AAPL --k_type day --num 120
"""

import json
import argparse
import sys
from datetime import datetime
from typing import Dict, Any, List, Optional
from random import randint

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


# ── 配置常量 ──────────────────────────────────────────

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


# ── 工具函数 ──────────────────────────────────────────

def normalize_code(code: str) -> str:
    """
    标准化股票代码为腾讯 API 格式

    A股上交所:  600519 -> sh600519, 688981 -> sh688981
    A股深交所:  000001 -> sz000001, 300750 -> sz300750
    港股:       00700  -> hk00700,  09988  -> hk09988
    美股:       AAPL   -> usaapl,   TSLA   -> ustsla

    也支持带前缀的输入: sh600519, hk00700, usaapl
    """
    code = code.strip().lower()
    # 去除美股点号 (BRK.A -> brka)
    code = code.replace(".", "")

    # 已有市场前缀，直接返回
    for prefix in ("sh", "sz", "hk", "us"):
        if code.startswith(prefix):
            return code

    # 美股：纯字母 ticker
    if code.isalpha():
        return f"us{code}"

    # 纯数字代码
    if code.isdigit():
        # 港股：5位以内数字（00700, 09988, 11 等）
        if len(code) < 6:
            return f"hk{code}"
        # A股上交所：6位数字以 6 开头（含科创板 688xxx）
        if code.startswith("6"):
            return f"sh{code}"
        # A股深交所：6位数字以 0 或 3 开头（含创业板 300xxx）
        if code.startswith(("0", "3")):
            return f"sz{code}"

    return ""


def _random(n: int = 16) -> str:
    start = 10 ** (n - 1)
    end = (10 ** n) - 1
    return str(randint(start, end))


def _to_float(val) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


# ── K线数据获取 ──────────────────────────────────────

def fetch_kline(stock_code: str, k_type: str, num: int) -> Dict[str, Any]:
    """
    从腾讯财经 API 获取 K线原始数据

    Args:
        stock_code: 股票代码
        k_type: day/week/month 或 m1/m5/m15/m30/m60
        num: 获取数量

    Returns:
        包含 kline 列表的 dict
    """
    code = normalize_code(stock_code)
    if not code:
        return {"status": "error", "stock_code": stock_code, "error": "无法识别的股票代码", "kline": []}

    if not HAS_REQUESTS:
        return {"status": "error", "stock_code": stock_code, "error": "requests 库未安装", "kline": []}

    # 分钟K线：m1/m5/m15/m30/m60，排除 month（月K）
    if k_type.startswith("m") and k_type != "month":
        return _fetch_minute(code, k_type, num)
    else:
        return _fetch_daily(code, k_type, num)


def _fetch_daily(code: str, k_type: str, num: int) -> Dict[str, Any]:
    url = (
        f"{FQKLINE_URL}?_var=kline_{k_type}qfq"
        f"&param={code},{k_type},,,{num},qfq"
        f"&r=0.{_random()}"
    )
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        content = resp.text.split("=", maxsplit=1)[-1]
        data = json.loads(content)
    except Exception as e:
        return {"status": "error", "stock_code": code, "error": str(e), "kline": []}

    stock_data = data.get("data", {}).get(code, {})
    # 股票用 qfq+周期（如 qfqday），指数直接用周期（如 day）
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
        kline.append({
            "date": item[0],
            "open": _to_float(item[1]),
            "close": _to_float(item[2]),
            "high": _to_float(item[3]),
            "low": _to_float(item[4]),
            "volume": _to_float(item[5]),
        })

    return {
        "status": "success",
        "stock_code": code,
        "k_type": k_type,
        "fetch_time": datetime.now().isoformat(),
        "total": len(kline),
        "kline": kline,
    }


def _fetch_minute(code: str, k_type: str, num: int) -> Dict[str, Any]:
    period = k_type[1:]  # m5 -> 5
    num = min(num, 320)
    url = (
        f"{MKLINE_URL}?param={code},m{period},,{num}"
        f"&_var=m{period}_today&r=0.{_random()}"
    )
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        content = resp.text.split("=", maxsplit=1)[-1]
        data = json.loads(content)
    except Exception as e:
        return {"status": "error", "stock_code": code, "error": str(e), "kline": []}

    key = f"m{period}"
    raw = data.get("data", {}).get(code, {}).get(key, [])

    kline = []
    for item in raw:
        if len(item) < 6:
            continue
        dt = item[0]
        formatted = f"{dt[0:4]}-{dt[4:6]}-{dt[6:8]} {dt[8:10]}:{dt[10:12]}"
        kline.append({
            "date": formatted,
            "open": _to_float(item[1]),
            "close": _to_float(item[2]),
            "high": _to_float(item[3]),
            "low": _to_float(item[4]),
            "volume": _to_float(item[5]),
        })

    return {
        "status": "success",
        "stock_code": code,
        "k_type": k_type,
        "fetch_time": datetime.now().isoformat(),
        "total": len(kline),
        "kline": kline,
    }


# ── 技术指标计算 ──────────────────────────────────────

def calc_ma(kline: List[Dict], periods: List[int] = None) -> List[Dict]:
    """计算简单移动平均线"""
    if periods is None:
        periods = [5, 10, 20, 60]

    closes = [item["close"] for item in kline if item.get("close") is not None]

    for i, item in enumerate(kline):
        ma_values = {}
        for p in periods:
            if i >= p - 1 and len(closes) >= p:
                window = closes[i - p + 1:i + 1]
                ma_values[f"ma{p}"] = round(sum(window) / p, 3)
            else:
                ma_values[f"ma{p}"] = None
        item["ma"] = ma_values

    return kline


def calc_boll(kline: List[Dict], period: int = 20, num_std: float = 2.0) -> List[Dict]:
    """计算布林带"""
    closes = [item["close"] for item in kline if item.get("close") is not None]

    for i, item in enumerate(kline):
        if i >= period - 1 and len(closes) >= period:
            window = closes[i - period + 1:i + 1]
            middle = sum(window) / period
            variance = sum((c - middle) ** 2 for c in window) / period
            std = variance ** 0.5
            item["boll"] = {
                "upper": round(middle + num_std * std, 3),
                "middle": round(middle, 3),
                "lower": round(middle - num_std * std, 3),
            }
        else:
            item["boll"] = {"upper": None, "middle": None, "lower": None}

    return kline


def calc_rsi(kline: List[Dict], periods: List[int] = None) -> List[Dict]:
    """计算 RSI 相对强弱指数"""
    if periods is None:
        periods = [6, 12, 14, 24]

    closes = [item["close"] for item in kline if item.get("close") is not None]

    # 计算价格变化
    changes = []
    for i in range(1, len(closes)):
        changes.append(closes[i] - closes[i - 1])

    for i, item in enumerate(kline):
        rsi_values = {}
        for p in periods:
            if i < p or i > len(changes):
                rsi_values[f"rsi{p}"] = None
                continue

            window = changes[i - p:i]
            gains = [c for c in window if c > 0]
            losses = [-c for c in window if c < 0]

            avg_gain = sum(gains) / p if gains else 0
            avg_loss = sum(losses) / p if losses else 0

            if avg_loss == 0:
                rsi_values[f"rsi{p}"] = 100.0
            else:
                rs = avg_gain / avg_loss
                rsi_values[f"rsi{p}"] = round(100 - 100 / (1 + rs), 2)

        item["rsi"] = rsi_values

    return kline


# ── 主流程 ──────────────────────────────────────────

def fetch_kline_with_indicators(
    stock_code: str,
    k_type: str = "day",
    num: int = 120,
    indicators: str = "ma,boll,rsi",
) -> Dict[str, Any]:
    """
    获取 K线数据并计算技术指标

    Args:
        stock_code: 股票代码
        k_type: K线周期
        num: 获取数量
        indicators: 需要计算的指标，逗号分隔

    Returns:
        包含 K线 + 技术指标的结构化数据
    """
    result = fetch_kline(stock_code, k_type, num)

    if result["status"] != "success":
        return result

    kline = result["kline"]
    if not kline:
        return result

    indicator_list = [i.strip().lower() for i in indicators.split(",") if i.strip()]

    if "ma" in indicator_list:
        kline = calc_ma(kline)
    if "boll" in indicator_list:
        kline = calc_boll(kline)
    if "rsi" in indicator_list:
        kline = calc_rsi(kline)

    result["kline"] = kline
    result["indicators"] = indicator_list

    return result


# ── CLI 入口 ──────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="腾讯财经 K线数据获取 + 技术指标计算")
    parser.add_argument("--stock_code", required=True, help="股票代码（如 600519）")
    parser.add_argument("--k_type", default=DEFAULT_K_TYPE,
                        help="K线周期：day/week/month/m1/m5/m15/m30/m60")
    parser.add_argument("--num", type=int, default=DEFAULT_NUM, help="获取K线数量")
    parser.add_argument("--indicators", default=DEFAULT_INDICATORS,
                        help="技术指标，逗号分隔（ma,boll,rsi）")
    parser.add_argument("--raw", action="store_true", help="仅输出K线原始数据，不计算指标")
    args = parser.parse_args()

    if args.raw:
        result = fetch_kline(args.stock_code, args.k_type, args.num)
    else:
        result = fetch_kline_with_indicators(
            args.stock_code, args.k_type, args.num, args.indicators
        )

    print(json.dumps(result, ensure_ascii=False, indent=2))

    if result["status"] != "success":
        sys.exit(1)


if __name__ == "__main__":
    main()
