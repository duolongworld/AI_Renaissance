#!/usr/bin/env python3
"""
数据回填工具 — 将搜索到的数据项自动回填到 *_real_data.json

用法:
    python3 scripts/fill_data.py <stock_code> --field revenue_growth --value 35.0 --source "2025Q4财报"
    python3 scripts/fill_data.py <stock_code> --batch items.json

field 与 real_data 路径对应:
    revenue_growth      → real_signals.revenue_growth
    gross_margin        → real_signals.gross_margin
    order_backlog       → real_signals.order_backlog
    capacity_utilization→ real_signals.capacity_utilization
    price_yoy           → real_signals.price_yoy
    inventory_days      → real_signals.inventory_days
    rd_ratio            → real_signals.rd_ratio
    net_profit_parent   → real_signals.net_profit_parent
    stock_name          → 顶层 stock_name
    industry            → 顶层 industry
"""

import json
import re
import sys
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

SCRIPT_DIR = Path(__file__).parent.parent.resolve()
DATA_DIR = SCRIPT_DIR / "data"

# field → JSON path 映射
FIELD_TO_PATH = {
    # 顶层字段
    "stock_name": "stock_name",
    "industry": "industry",
    "sub_industry": "sub_industry",
    "preset": "preset",
    "chain_position": "chain_position",
    # real_signals 字段
    "revenue_growth": "real_signals.revenue_growth",
    "gross_margin": "real_signals.gross_margin",
    "order_backlog": "real_signals.order_backlog",
    "capacity_utilization": "real_signals.capacity_utilization",
    "price_yoy": "real_signals.price_yoy",
    "inventory_days": "real_signals.inventory_days",
    "rd_ratio": "real_signals.rd_ratio",
    "research_expense_ratio": "real_signals.research_expense_ratio",
    "net_profit_parent": "real_signals.net_profit_parent",
    "revenue": "real_signals.revenue",
    "operating_cash_flow": "real_signals.operating_cash_flow",
    "fixed_asset": "real_signals.fixed_asset",
    "total_asset": "real_signals.total_asset",
    "capex_plan": "real_signals.capex_plan",
    # V4.6 新增: 结构转型 + 趋势 + 行业验证字段
    "segment_data": "real_signals.segment_data",
    "gross_margin_history": "real_signals.gross_margin_history",
    "market_share": "real_signals.market_share",
    "major_customer_orders": "real_signals.major_customer_orders",
    "inflection_signals": "real_signals.inflection_signals",
    "lifecycle_signals": "real_signals.lifecycle_signals",
    # V4.6 新增: A股可获取的替代指标
    "contract_liability": "real_signals.contract_liability",
    "fixed_asset_turnover": "real_signals.fixed_asset_turnover",
}

# ========== capex_plan 枚举校验 ==========
CAPEX_PLAN_VALID = {"underway", "planned", "none", "aggressive"}
CAPEX_PLAN_VALUES_HELP = """
  capex_plan 必须为以下枚举值之一:
    "underway"   — 扩产进行中（已公告、已在建）
    "planned"    — 扩产计划已公告但未开工
    "none"       — 近期无扩产计划
    "aggressive" — 激进扩产（规模超预期、节奏加快）
  示例: --field capex_plan --value underway
""" 


def _set_nested(data: dict, path: str, value: Any):
    """按 '.' 分隔路径设置嵌套字典值。"""
    keys = path.split(".")
    current = data
    for key in keys[:-1]:
        if key not in current:
            current[key] = {}
        current = current[key]
    current[keys[-1]] = value


def _load_or_create(stock_code: str) -> Dict[str, Any]:
    """加载现有 real_data 或创建模板。"""
    candidates = [
        DATA_DIR / f"{stock_code}_real_data.json",
        DATA_DIR / f"{stock_code.upper()}_real_data.json",
    ]
    for path in candidates:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)

    # 创建模板
    code = stock_code.upper()
    base_code = re.sub(r"\.(SH|SZ|BJ|HK)$", "", code)
    return {
        "stock_code": code,
        "stock_name": base_code,
        "industry": "数据缺失",
        "preset": "generic",
        "generated_at": datetime.now().strftime("%Y-%m-%d"),
        "real_signals": {},
        "industry_data": [],
    }


def fill_field(
    stock_code: str,
    field: str,
    value: Any,
    source: str = "",
    source_date: str = "",
    source_url: str = "",
    save: bool = True,
) -> Dict[str, Any]:
    """回填单个字段到 real_data。

    Args:
        stock_code: 股票代码
        field: 字段名（见 FIELD_TO_PATH）
        value: 值（自动转换数字）
        source: 数据来源描述
        source_date: 数据日期
        source_url: 来源 URL
        save: 是否保存到文件

    Returns:
        更新后的 data dict
    """
    data = _load_or_create(stock_code)

    # 解析字段路径
    path = FIELD_TO_PATH.get(field, field)
    if "." not in path and path not in ("stock_name", "industry", "sub_industry", "preset", "chain_position"):
        path = f"real_signals.{field}"

    # 值转换
    if isinstance(value, str):
        # 尝试转数字
        v = value.strip().replace("%", "").replace(",", "")
        try:
            value = float(v)
            if value == int(value):
                value = int(value)
        except ValueError:
            pass

    # capex_plan 枚举校验
    if field == "capex_plan" and isinstance(value, str):
        v = value.strip().lower()
        if v not in CAPEX_PLAN_VALID:
            print(f"⚠️  警告: capex_plan='{value}' 不是有效枚举值")
            print(CAPEX_PLAN_VALUES_HELP)
            # 尝试中文→枚举映射
            cn_map = {"进行中": "underway", "已规划": "planned", "规划中": "planned",
                      "无": "none", "激进": "aggressive", "扩产": "underway"}
            v = cn_map.get(v, v)
            if v in CAPEX_PLAN_VALID:
                value = v
                print(f"   已自动转换: '{value}' → '{v}'")
            else:
                print(f"   无法自动转换，将使用原始值（可能无法匹配拐点判定）")
    
    # 写入
    _set_nested(data, path, value)

    # 写入 source 信息
    if field not in ("stock_name", "industry", "stock_code", "preset"):
        rs = data.setdefault("real_signals", {})
        source_key = f"{field}_source"
        if source:
            rs[source_key] = source
        if source_date:
            rs[f"{field}_date"] = source_date
        if source_url:
            rs[f"{field}_url"] = source_url

    # 更新缺失计数
    rs = data.get("real_signals", {})
    core_fields = ["revenue_growth", "gross_margin", "order_backlog",
                   "capacity_utilization", "price_yoy", "inventory_days",
                   "contract_liability", "fixed_asset_turnover"]
    missing = sum(1 for f in core_fields if rs.get(f) is None)
    data["_missing_count"] = missing
    data["_last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")

    if save:
        out_path = DATA_DIR / f"{stock_code.upper()}_real_data.json"
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"✅ 已写入: {out_path}")
        print(f"   {field} = {value}")
        if source:
            print(f"   来源: {source}")

    return data


def fill_batch(stock_code: str, items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """批量回填多个字段。

    Args:
        stock_code: 股票代码
        items: [{field: "revenue_growth", value: 35.0, source: "..."}, ...]
    """
    data = _load_or_create(stock_code)
    for item in items:
        data = fill_field(
            stock_code,
            item["field"],
            item.get("value"),
            source=item.get("source", ""),
            source_date=item.get("date", ""),
            source_url=item.get("url", ""),
            save=False,
        )
    # 最终保存
    out_path = DATA_DIR / f"{stock_code.upper()}_real_data.json"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"✅ 批量回填完成: {out_path} ({len(items)} 项)")
    return data


def _auto_run_pipeline(stock_code: str):
    """自动重新运行 pipeline 生成报告"""
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from core.pipeline import run_pipeline
        print(f"\\n🔄 自动重新运行 pipeline: {stock_code}")
        result = run_pipeline(stock_code)
        if result:
            print(f"✅ 报告已生成: {result}")
        else:
            print("⚠️  pipeline 返回空路径")
    except Exception as e:
        print(f"⚠️  自动重跑失败（不影响数据回填）: {e}")
    
def show_missing(stock_code: str) -> List[str]:
    """显示缺失字段列表。"""
    data = _load_or_create(stock_code)
    rs = data.get("real_signals", {})
    core_fields = ["revenue_growth", "gross_margin", "order_backlog",
                   "capacity_utilization", "price_yoy", "inventory_days",
                   "contract_liability", "fixed_asset_turnover",
                   "rd_ratio", "net_profit_parent"]
    missing = [f for f in core_fields if rs.get(f) is None]
    filled = [f for f in core_fields if rs.get(f) is not None]

    print(f"📊 {stock_code} 数据状态:")
    print(f"  已填充: {len(filled)}/{len(core_fields)}")
    if filled:
        for f in filled:
            print(f"    ✅ {f} = {rs[f]}")
    if missing:
        for f in missing:
            print(f"    ❌ {f} 缺失")
    return missing


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="数据回填工具")
    parser.add_argument("stock_code", help="股票代码")
    parser.add_argument("--field", help="要回填的字段名")
    parser.add_argument("--value", help="字段值")
    parser.add_argument("--source", default="", help="数据来源")
    parser.add_argument("--date", default="", help="数据日期")
    parser.add_argument("--url", default="", help="来源URL")
    parser.add_argument("--batch", help="批量回填的 JSON 文件路径")
    parser.add_argument("--show", action="store_true", help="显示缺失字段")
    parser.add_argument("--auto-run", action="store_true", help="回填后自动重新运行 pipeline 生成报告")

    args = parser.parse_args()

    if args.show:
        show_missing(args.stock_code)
        sys.exit(0)
    
    # 执行回填
    if args.batch:
        with open(args.batch, "r", encoding="utf-8") as f:
            items = json.load(f)
        fill_batch(args.stock_code, items)
    elif args.field and args.value is not None:
        fill_field(
            args.stock_code, args.field, args.value,
            source=args.source, source_date=args.date, source_url=args.url,
        )
    else:
        parser.print_help()
        sys.exit(1)
    
    # P2-1: 自动重新运行 pipeline
    if args.auto_run:
        _auto_run_pipeline(args.stock_code)
