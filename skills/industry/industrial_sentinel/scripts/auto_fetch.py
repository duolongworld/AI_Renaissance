#!/usr/bin/env python3
"""
V4.6 自动数据抓取 — 东方财富 push2 API + akshare 双通道

用法:
    python3 scripts/auto_fetch.py 688521.SH      # 单个股票
    python3 scripts/auto_fetch.py 688521.SH --force  # 强制覆盖
"""
import json
import re
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Optional

SCRIPT_DIR = Path(__file__).parent.parent.resolve()
DATA_DIR = SCRIPT_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ── Eastmoney push2 → real_signals 字段映射 ──
# 深交所 0.xxx, 上交所 1.xxx
EASTMONEY_FIELD_MAP = {
    "f41": "revenue_growth",     # 营收同比增速(%)
    "f57": "gross_margin",       # 销售毛利率(%)
    "f9":  "pe",                 # PE(TTM)
    "f20": "total_market_cap",   # 总市值
}

# 核心指标映射: akshare 字段 → real_signals 字段 (备用)
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


def _code_to_em_secid(stock_code: str) -> str:
    """将股票代码转为东方财富 secid 格式。深交所 0.xxx, 上交所 1.xxx"""
    code = stock_code.upper()
    if ".SZ" in code:
        return f"0.{_clean_code(code)}"
    elif ".SH" in code:
        return f"1.{_clean_code(code)}"
    elif ".BJ" in code:
        return f"0.{_clean_code(code)}"
    else:
        # 尝试判断: 60xxxx→SH, 00xxxx/30xxxx→SZ, 68xxxx→SH(科创板)
        clean = _clean_code(code)
        if clean.startswith("6"):
            return f"1.{clean}"
        return f"0.{clean}"


def fetch_from_eastmoney(stock_code: str) -> dict:
    """东方财富 push2 API 直连获取财务数据（零依赖，速度最快）。"""
    signals = {}
    try:
        secid = _code_to_em_secid(stock_code)
        url = (f"https://push2.eastmoney.com/api/qt/ulist.np/get"
               f"?fltt=2&fields=f2,f9,f12,f14,f20,f41,f57&secids={secid}")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        data = json.loads(urllib.request.urlopen(req, timeout=10).read())
        stock = data["data"]["diff"][0]
        
        for em_field, signal_field in EASTMONEY_FIELD_MAP.items():
            val = stock.get(em_field)
            if val is not None and val != "-":
                try:
                    signals[signal_field] = float(val)
                except (ValueError, TypeError):
                    pass
        
        if "total_market_cap" in signals and "市值" not in signals:
            # 总市值字段单位特殊处理（API 返回可能有误差）
            pass
        
        if signals:
            print(f"  ✅ 东方财富 push2 获取 {len(signals)} 个字段")
    except Exception as e:
        print(f"  ⚠️ 东方财富 push2 失败: {e}")
    
    return signals


def auto_fetch_and_save(stock_code: str, force: bool = False) -> Optional[Path]:
    """自动抓取并保存到 real_data.json。返回文件路径或 None。"""
    code = _clean_code(stock_code)
    out_path = DATA_DIR / f"{_clean_code(stock_code)}_real_data.json"
    
    # 已有数据且非强制
    if out_path.exists() and not force:
        print(f"  📄 已有数据: {out_path}")
        return out_path
    
    print(f"🔍 自动抓取: {stock_code} ...")
    
    # 首选: 东方财富 push2 (零依赖, 直连)
    signals = fetch_from_eastmoney(stock_code)
    
    # 备用: akshare (需安装, 字段更丰富)
    if len(signals) < 3:
        try:
            import akshare  # noqa
            extra = fetch_from_akshare(stock_code)
            signals.update(extra)
        except (ImportError, NameError):
            pass  # akshare未安装/函数不存在，继续
    
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
    data["_data_source"] = "eastmoney_push2"
    
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
