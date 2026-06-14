from __future__ import annotations

"""统一 OHLCV 行情数据源。

数据获取实现集中在 data_sources：
- CSV 标准 OHLCV 加载；
- EastMoney K 线；
- Tencent Technical 兜底。

skills/data 仅描述接口和提供薄包装，不承载核心获取/解析逻辑。
"""

import csv
import math
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

from data_sources.tencent_technical import fetch_kline as fetch_tencent_kline


OhlcvRow = Dict[str, Any]


def safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def load_ohlcv_csv(path: str | Path) -> List[OhlcvRow]:
    rows: List[OhlcvRow] = []
    p = Path(path)
    with p.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"date", "high", "low", "close", "volume"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"missing required columns: {', '.join(sorted(missing))}")
        for row in reader:
            item: OhlcvRow = {
                "date": (row.get("date") or "").strip(),
                "open": safe_float(row.get("open")) if "open" in (reader.fieldnames or []) else math.nan,
                "high": safe_float(row.get("high")),
                "low": safe_float(row.get("low")),
                "close": safe_float(row.get("close")),
                "volume": safe_float(row.get("volume")),
            }
            for optional_key in ("amount", "turnover", "money", "turnover_rate"):
                if optional_key in (reader.fieldnames or []):
                    item[optional_key] = safe_float(row.get(optional_key))
            rows.append(item)
    return rows


@dataclass(frozen=True)
class EastMoneyConfig:
    ut: str
    timeout_s: float = 15.0
    verify_ssl: bool = True


def _eastmoney_secid(code: str) -> str:
    c = code.strip()
    if c.startswith(("6", "688")):
        return f"1.{c}"
    if c.startswith(("0", "3")):
        return f"0.{c}"
    if c.startswith(("8", "4")):
        return f"116.{c}"
    return f"1.{c}"


def fetch_ohlcv_eastmoney(
    code: str,
    start: str,
    end: str,
    *,
    freq: str = "D",
    adjust: str = "none",
    config: EastMoneyConfig,
) -> Tuple[List[OhlcvRow], List[str]]:
    uncertainties: List[str] = []
    if adjust != "none":
        uncertainties.append("复权口径尚未统一定稿；当前实现仅保证 none（不复权）口径稳定。")

    klt_map = {"D": 101, "W": 102, "M": 103}
    secid = _eastmoney_secid(code)
    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    params = {
        "secid": secid,
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": str(klt_map.get(freq.upper(), 101)),
        "fqt": "0",
        "beg": start.replace("-", ""),
        "end": end.replace("-", ""),
        "ut": config.ut,
    }
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"}
    resp = requests.get(url, params=params, headers=headers, timeout=config.timeout_s, verify=config.verify_ssl)
    resp.raise_for_status()
    klines = ((resp.json() or {}).get("data") or {}).get("klines") or []

    rows: List[OhlcvRow] = []
    for item in klines:
        parts = str(item).split(",")
        if len(parts) < 6:
            continue
        row: OhlcvRow = {
            "date": parts[0],
            "open": safe_float(parts[1]),
            "close": safe_float(parts[2]),
            "high": safe_float(parts[3]),
            "low": safe_float(parts[4]),
            "volume": safe_float(parts[5]),
        }
        if len(parts) > 6:
            row["amount"] = safe_float(parts[6])
        if len(parts) > 10:
            row["turnover_rate"] = safe_float(parts[10])
        rows.append(row)

    if not rows:
        uncertainties.append("EastMoney 返回空 klines（可能是代码不支持、日期范围无交易日或接口变化）。")
    return rows, uncertainties


def load_rows_from_code(code: str, start: str, end: str, *, freq: str = "D", adjust: str = "none") -> Tuple[List[OhlcvRow], List[str]]:
    uncertainties: List[str] = []
    ut = os.environ.get("EASTMONEY_UT", "").strip()
    if ut:
        try:
            rows, u = fetch_ohlcv_eastmoney(code, start, end, freq=freq, adjust=adjust, config=EastMoneyConfig(ut=ut))
            if rows:
                u.append(f"行情来源：eastmoney:{code}")
                return rows, u
            uncertainties.extend(u)
            uncertainties.append("EastMoney 未返回有效行情，切换 Tencent Technical 数据源兜底。")
        except Exception as exc:
            uncertainties.append(f"EastMoney 行情拉取失败：{type(exc).__name__}: {exc}；切换 Tencent Technical 数据源兜底。")
    else:
        uncertainties.append("未配置 EASTMONEY_UT，使用 data_sources.tencent_technical 行情数据源。")

    rows, tencent_uncertainties = fetch_ohlcv_tencent(code, start, end, freq=freq, adjust=adjust)
    uncertainties.extend(tencent_uncertainties)
    return rows, uncertainties


def fetch_ohlcv_tencent(
    code: str,
    start: str = "",
    end: str = "",
    *,
    freq: str = "D",
    adjust: str = "none",
    limit: Optional[int] = None,
) -> Tuple[List[OhlcvRow], List[str]]:
    uncertainties: List[str] = []
    if adjust not in {"none", "qfq"}:
        uncertainties.append("Tencent 行情兜底当前只支持前复权/不复权近似口径；hfq 请求已按腾讯默认 qfq 数据处理。")
    elif adjust == "none":
        uncertainties.append("Tencent 行情接口默认返回 qfq/前复权日线，可能与 EastMoney none 口径存在差异。")

    result = fetch_tencent_kline(code, _tencent_k_type(freq), limit or _estimate_tencent_limit(start, end, freq=freq))
    if result.get("status") != "success":
        return [], [f"Tencent 行情拉取失败：{result.get('error') or 'unknown error'}"]

    rows = [_normalize_tencent_row(item) for item in result.get("kline") or []]
    rows = [row for row in rows if row is not None]
    rows = _filter_rows_by_date(rows, start, end)
    if not rows:
        uncertainties.append("Tencent 返回空 K 线或按 start/end 过滤后为空。")
    else:
        uncertainties.append(f"行情来源：tencent_technical:{result.get('stock_code') or code}")
    return rows, uncertainties


def _tencent_k_type(freq: str) -> str:
    return {"D": "day", "W": "week", "M": "month"}.get((freq or "D").upper(), "day")


def _estimate_tencent_limit(start: str, end: str, *, freq: str = "D") -> int:
    default_limit = 240 if (freq or "D").upper() == "D" else 180
    try:
        start_dt = datetime.strptime(start, "%Y-%m-%d")
        end_dt = datetime.strptime(end, "%Y-%m-%d")
    except (TypeError, ValueError):
        return default_limit
    days = max((end_dt - start_dt).days + 1, 1)
    if (freq or "D").upper() == "D":
        return min(max(int(days * 0.9) + 30, 80), 640)
    if (freq or "D").upper() == "W":
        return min(max(int(days / 7) + 8, 60), 640)
    return min(max(int(days / 30) + 6, 48), 640)


def _normalize_tencent_row(item: Dict[str, Any]) -> Optional[OhlcvRow]:
    close = safe_float(item.get("close"))
    high = safe_float(item.get("high"))
    low = safe_float(item.get("low"))
    volume = safe_float(item.get("volume"))
    if close is None or high is None or low is None or volume is None:
        return None
    open_value = safe_float(item.get("open"))
    row: OhlcvRow = {"date": str(item.get("date") or ""), "open": close if open_value is None else open_value, "high": high, "low": low, "close": close, "volume": volume}
    for key in ("amount", "turnover", "money", "turnover_rate", "volume_unit", "volume_raw", "volume_raw_unit"):
        value = safe_float(item.get(key))
        if key in {"volume_unit", "volume_raw_unit"}:
            if item.get(key):
                row[key] = str(item.get(key))
        elif value is not None:
            row[key] = value
    return row


def _filter_rows_by_date(rows: List[OhlcvRow], start: str, end: str) -> List[OhlcvRow]:
    if not start and not end:
        return rows
    return [row for row in rows if (not start or str(row.get("date") or "")[:10] >= start) and (not end or str(row.get("date") or "")[:10] <= end)]


class MarketOhlcvDataSource:
    def load_csv(self, path: str | Path) -> List[OhlcvRow]:
        return load_ohlcv_csv(path)

    def load_rows_from_code(self, code: str, start: str, end: str, *, freq: str = "D", adjust: str = "none") -> Tuple[List[OhlcvRow], List[str]]:
        return load_rows_from_code(code, start, end, freq=freq, adjust=adjust)
