#!/usr/bin/env python3
"""
V4.5 Framework Backtest - Batch Classification
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path("/root/.openclaw/workspace/skills/industrial-sentinel/core")))

from system_a import determine_lifecycle_phase, determine_inflection_state_v45
from system_b import identify_stock_type

# Historical financial data for 7 stocks across 2 years (2024, 2025)
# Format: {stock_code: {year: {metrics}}}
HISTORICAL_DATA = {
    "002463.SZ": {
        "name": "沪电股份",
        "industry": "PCB",
        2024: {
            "revenue_growth": 49.26,
            "gross_margin": 35.85,
            "net_profit_growth": 71.05,
            "rd_ratio": 5.9,
            "asset_lightness": 0.55,
            "profit_stability": 0.70,
        },
        2025: {
            "revenue_growth": 42.00,
            "gross_margin": 36.91,
            "net_profit_growth": 47.74,
            "rd_ratio": 5.5,
            "asset_lightness": 0.55,
            "profit_stability": 0.72,
        },
    },
    "300476.SZ": {
        "name": "胜宏科技",
        "industry": "PCB",
        2024: {
            "revenue_growth": 35.0,
            "gross_margin": 22.7,
            "net_profit_growth": 15.0,
            "rd_ratio": 4.2,
            "asset_lightness": 0.50,
            "profit_stability": 0.55,
        },
        2025: {
            "revenue_growth": 79.77,
            "gross_margin": 35.2,
            "net_profit_growth": 273.52,
            "rd_ratio": 4.0,
            "asset_lightness": 0.50,
            "profit_stability": 0.65,
        },
    },
    "688313.SH": {
        "name": "仕佳光子",
        "industry": "光通信",
        2024: {
            "revenue_growth": 42.4,
            "gross_margin": 26.3,
            "net_profit_growth": 200.0,
            "rd_ratio": 9.6,
            "asset_lightness": 0.65,
            "profit_stability": 0.30,
        },
        2025: {
            "revenue_growth": 98.15,
            "gross_margin": 33.06,
            "net_profit_growth": 473.25,
            "rd_ratio": 6.2,
            "asset_lightness": 0.65,
            "profit_stability": 0.45,
        },
    },
    "002428.SZ": {
        "name": "云南锗业",
        "industry": "有色金属",
        2024: {
            "revenue_growth": 15.0,
            "gross_margin": 28.5,
            "net_profit_growth": -30.0,
            "rd_ratio": 7.7,
            "asset_lightness": 0.40,
            "profit_stability": 0.35,
        },
        2025: {
            "revenue_growth": 38.89,
            "gross_margin": 21.12,
            "net_profit_growth": -62.06,
            "rd_ratio": 7.5,
            "asset_lightness": 0.40,
            "profit_stability": 0.25,
        },
    },
    "688205.SH": {
        "name": "德科立",
        "industry": "光通信",
        2024: {
            "revenue_growth": 2.8,
            "gross_margin": 30.9,
            "net_profit_growth": 9.1,
            "rd_ratio": 12.3,
            "asset_lightness": 0.60,
            "profit_stability": 0.50,
        },
        2025: {
            "revenue_growth": 10.99,
            "gross_margin": 27.46,
            "net_profit_growth": -28.77,
            "rd_ratio": 11.8,
            "asset_lightness": 0.60,
            "profit_stability": 0.40,
        },
    },
    "300308.SZ": {
        "name": "中际旭创",
        "industry": "光通信",
        2024: {
            "revenue_growth": 122.7,
            "gross_margin": 34.65,
            "net_profit_growth": 150.0,
            "rd_ratio": 5.2,
            "asset_lightness": 0.55,
            "profit_stability": 0.75,
        },
        2025: {
            "revenue_growth": 37.0,
            "gross_margin": 39.3,
            "net_profit_growth": 69.40,
            "rd_ratio": 4.0,
            "asset_lightness": 0.55,
            "profit_stability": 0.80,
        },
    },
    "688521.SH": {
        "name": "芯原股份",
        "industry": "半导体",
        2024: {
            "revenue_growth": -0.7,
            "gross_margin": 45.0,
            "net_profit_growth": -100.0,
            "rd_ratio": 53.7,
            "asset_lightness": 0.85,
            "profit_stability": 0.20,
        },
        2025: {
            "revenue_growth": 35.77,
            "gross_margin": 48.0,
            "net_profit_growth": 12.16,
            "rd_ratio": 42.8,
            "asset_lightness": 0.85,
            "profit_stability": 0.25,
        },
    },
}


def run_classification(stock_code, year, data):
    """Run V4.5 framework on historical data."""
    stock_info = HISTORICAL_DATA[stock_code]
    metrics = data
    
    real_signals = {
        "revenue_growth": metrics["revenue_growth"],
        "gross_margin": metrics["gross_margin"],
        "capacity_utilization": 85 if metrics["revenue_growth"] > 20 else 70,
        "order_backlog": 80 if metrics["revenue_growth"] > 30 else 50,
        "price_yoy": 5 if metrics["gross_margin"] > 30 else 0,
        "inventory_days": 45,
        "new_capacity": "underway" if metrics["revenue_growth"] > 20 else "stable",
        "policy_count": 2,
    }
    
    lifecycle_result = determine_lifecycle_phase(
        penetration_rate=25.0,
        revenue_growth=metrics["revenue_growth"],
        price_trend="rising" if metrics["revenue_growth"] > 20 else "stable",
    )
    lifecycle = lifecycle_result.get("phase_name", "未知")
    
    inflection = determine_inflection_state_v45(real_signals)
    
    stock_type = identify_stock_type(
        industry=stock_info["industry"],
        revenue_growth=metrics["revenue_growth"],
        rd_ratio=metrics["rd_ratio"],
        asset_lightness=metrics["asset_lightness"],
        profit_stability=metrics["profit_stability"],
    )
    
    return {
        "lifecycle": lifecycle,
        "inflection": inflection,
        "stock_type": stock_type,
    }


def main():
    print("=" * 80)
    print("Industrial Sentinel V4.5 Backtest - Framework Classification")
    print("=" * 80)
    print()
    
    results = []
    
    for stock_code, stock_data in HISTORICAL_DATA.items():
        name = stock_data["name"]
        print(f"\n{'='*60}")
        print(f"标的: {name} ({stock_code})")
        print(f"{'='*60}")
        
        for year in [2024, 2025]:
            if year not in stock_data:
                continue
            
            metrics = stock_data[year]
            result = run_classification(stock_code, year, metrics)
            
            print(f"\n  {year}年度:")
            print(f"    营收增速: {metrics['revenue_growth']:.1f}%")
            print(f"    毛利率: {metrics['gross_margin']:.1f}%")
            print(f"    净利增速: {metrics['net_profit_growth']:.1f}%")
            print(f"    → 生命周期: {result['lifecycle']}")
            print(f"    → 拐点状态: {result['inflection']}")
            print(f"    → 个股类型: {result['stock_type']}")
            
            results.append({
                "stock_code": stock_code,
                "name": name,
                "year": year,
                "revenue_growth": metrics["revenue_growth"],
                "gross_margin": metrics["gross_margin"],
                "lifecycle": result["lifecycle"],
                "inflection": result["inflection"][0].state_name if isinstance(result["inflection"], tuple) else str(result["inflection"]),
                "stock_type": result["stock_type"],
            })
    
    print("\n" + "=" * 80)
    print("统计汇总")
    print("=" * 80)
    
    lifecycle_counts = {}
    inflection_counts = {}
    type_counts = {}
    
    for r in results:
        lifecycle_counts[r["lifecycle"]] = lifecycle_counts.get(r["lifecycle"], 0) + 1
        inflection_counts[r["inflection"]] = inflection_counts.get(r["inflection"], 0) + 1
        type_counts[r["stock_type"]] = type_counts.get(r["stock_type"], 0) + 1
    
    print("\n生命周期分布:")
    for stage, count in sorted(lifecycle_counts.items()):
        print(f"  {stage}: {count}次")
    
    print("\n拐点状态分布:")
    for state, count in sorted(inflection_counts.items()):
        print(f"  {state}: {count}次")
    
    print("\n个股类型分布:")
    for t, count in sorted(type_counts.items()):
        print(f"  {t}: {count}次")
    
    return results


if __name__ == "__main__":
    results = main()
