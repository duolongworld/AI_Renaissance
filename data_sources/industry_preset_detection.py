"""
Industry preset 检测所需的外部 provider 查询。

Skill 层只负责映射和分析；AkShare、东方财富、腾讯等真实查询放在这里。
"""

from __future__ import annotations

import json
import urllib.request
from typing import Dict, List, Optional


def query_akshare_industry(stock_code: str) -> Optional[str]:
    """通过 AkShare 查询行业分类。"""
    import akshare as ak

    code = stock_code.replace(".SH", "").replace(".SZ", "").replace(".HK", "")
    df = ak.stock_individual_info_em(symbol=code)
    if df is None or df.empty:
        return None

    for col in df["item"]:
        value = df[df["item"] == col]["value"].values[0] if col in df["item"].values else ""
        if col in ["行业", "所属行业", "申万行业", "证监会行业", "所属概念"]:
            return str(value)
    return None


def query_all_a_stock_industries() -> List[Dict[str, str]]:
    """通过 AkShare 获取 A 股代码、名称和行业列表。"""
    import akshare as ak

    stock_df = ak.stock_info_a_code_name()
    rows = []
    for _, row in stock_df.iterrows():
        code = str(row["code"])
        name = str(row["name"])
        industry = query_akshare_industry(code) or ""
        rows.append({"code": code, "name": name, "industry": industry})
    return rows


def query_eastmoney_industry(stock_code: str) -> Optional[str]:
    """通过东方财富 API 查询行业分类。"""
    if stock_code.endswith(".SH"):
        secid = f"1.{stock_code.replace('.SH', '')}"
    elif stock_code.endswith(".SZ"):
        secid = f"0.{stock_code.replace('.SZ', '')}"
    else:
        return None

    url = f"https://push2.eastmoney.com/api/qt/stock/get?secid={secid}&fields=f100,f102"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if data.get("data"):
        industry = data["data"].get("f100", "")
        if industry:
            return industry
    return None


def query_tencent_stock_name(stock_code: str) -> Optional[str]:
    """通过腾讯行情 API 查询股票名称。"""
    prefix = "sh" if stock_code.endswith(".SH") else "sz"
    code = stock_code.replace(".SH", "").replace(".SZ", "")
    url = f"https://qt.gtimg.cn/q={prefix}{code}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=10) as resp:
        content = resp.read()

    for encoding in ["gb2312", "gbk", "utf-8"]:
        try:
            text = content.decode(encoding)
        except UnicodeDecodeError:
            continue
        if "~" in text:
            parts = text.split("~")
            if len(parts) >= 3:
                return parts[1]
        break
    return None
