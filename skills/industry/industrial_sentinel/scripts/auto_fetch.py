#!/usr/bin/env python3
"""
V4.6 自动数据抓取 — 用 akshare 自动获取财务数据，写入 real_data.json

用法:
    python3 scripts/auto_fetch.py 688521.SH      # 单个股票
    python3 scripts/auto_fetch.py 688521.SH --force  # 强制覆盖
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

SCRIPT_DIR = Path(__file__).parent.parent.resolve()
DATA_DIR = SCRIPT_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# 核心指标映射: akshare 字段 → real_signals 字段
FIELD_MAP = {
    "revenue_growth": "营业总收入同比增长率",
    "gross_margin": "销售毛利率",
    "net_profit_parent": "归属母公司净利润",
    "rd_ratio": "研发费用/营业总收入",
    "contract_liability": "合同负债",
    "inventory_days": "存货周转天数",
    "fixed_asset_turnover": "固定资产周转率",
}


def _clean_code(stock_code: str) -> str:
    """去后缀, 保留6位数字"""
    return re.sub(r"\.(SH|SZ|BJ|HK)$", "", stock_code.upper())


def fetch_from_akshare(stock_code: str) -> dict:
    """用 akshare 获取个股财务数据, 返回 real_signals dict。"""
    code = _clean_code(stock_code)
    signals = {}
    
    try:
        import akshare as ak
    except ImportError:
        print("⚠️ akshare 未安装。pip install akshare")
        return signals
    
    # 方式1: stock_individual_info_em — 基础指标
    try:
        df = ak.stock_individual_info_em(symbol=code)
        if df is not None and not df.empty:
            row = dict(zip(df["item"], df["value"]))
            
            # 提取可用字段
            for field, cn_name in FIELD_MAP.items():
                if cn_name in row:
                    val = str(row[cn_name]).replace("%", "").replace(",", "")
                    try:
                        signals[field] = float(val)
                    except ValueError:
                        pass
            
            if signals:
                print(f"  ✅ akshare 获取 {len(signals)} 个字段")
    except Exception as e:
        print(f"  ⚠️ akshare stock_individual_info_em 失败: {e}")
    
    # 方式2: 补充 — 同花顺财务摘要
    if len(signals) < 3:
        try:
            df2 = ak.stock_financial_abstract_ths(symbol=code, indicator="按报告期")
            if df2 is not None and not df2.empty:
                latest = df2.iloc[-1] if len(df2) > 0 else None
                if latest is not None:
                    for col in latest.index:
                        col_lower = str(col).lower()
                        if "营收" in col_lower and "增长" in col_lower and "revenue_growth" not in signals:
                            try: signals["revenue_growth"] = float(str(latest[col]).replace("%",""))
                            except: pass
                        if "毛利" in str(col) and "gross_margin" not in signals:
                            try: signals["gross_margin"] = float(str(latest[col]).replace("%",""))
                            except: pass
                    print(f"  ✅ 同花顺补充 {len(signals)} 个字段")
        except Exception as e:
            print(f"  ⚠️ 同花顺摘要失败: {e}")
    
    return signals


def auto_fetch_and_save(stock_code: str, force: bool = False) -> Optional[Path]:
    """自动抓取并保存到 real_data.json。返回文件路径或 None。"""
    code = _clean_code(stock_code)
    out_path = DATA_DIR / f"{stock_code.upper()}_real_data.json"
    
    # 已有数据且非强制
    if out_path.exists() and not force:
        print(f"  📄 已有数据: {out_path}")
        return out_path
    
    print(f"🔍 自动抓取: {stock_code} ...")
    signals = fetch_from_akshare(stock_code)
    
    if not signals:
        print("  ❌ 未能获取任何数据")
        return None
    
    # 加载原有数据（如有）, 合并
    if out_path.exists():
        with open(out_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {
            "stock_code": stock_code.upper(),
            "stock_name": code,
            "industry": "数据缺失",
            "preset": "generic",
            "real_signals": {},
            "industry_data": [],
        }
    
    data["real_signals"].update(signals)
    data["_last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    data["_data_source"] = "akshare_auto"
    
    # 计算缺失计数
    core_fields = ["revenue_growth", "gross_margin", "order_backlog",
                   "capacity_utilization", "price_yoy", "inventory_days",
                   "contract_liability", "fixed_asset_turnover"]
    rs = data.get("real_signals", {})
    data["_missing_count"] = sum(1 for f in core_fields if rs.get(f) is None)
    
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"  ✅ 已保存: {out_path} ({len(signals)} 字段, 缺失 {data['_missing_count']}/{len(core_fields)})")
    return out_path


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="自动数据抓取")
    parser.add_argument("stock_code", help="股票代码")
    parser.add_argument("--force", action="store_true", help="强制覆盖")
    args = parser.parse_args()
    
    result = auto_fetch_and_save(args.stock_code, args.force)
    if result:
        print(f"\n✅ 完成: {result}")
    else:
        print("\n❌ 抓取失败")
        sys.exit(1)
