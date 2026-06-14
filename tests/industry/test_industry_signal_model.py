#!/usr/bin/env python3
"""System A industry-level signal model tests."""
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).parent.parent.parent
SKILL_DIR = REPO_ROOT / "skills" / "industry" / "industrial_sentinel"
sys.path.insert(0, str(SKILL_DIR))
sys.path.insert(0, str(SKILL_DIR / "core"))


def test_inflection_confirmed_from_industry_signals():
    """行业需求、订单、产能、价格、政策共振时应判定拐点确认。"""
    from core.system_a import determine_inflection_state_from_signals

    result, logic = determine_inflection_state_from_signals(
        {
            "industry_market_growth": 28.0,
            "industry_order_growth": 18.0,
            "industry_capacity_utilization": 88.0,
            "industry_price_yoy": 6.0,
            "industry_capex_plan": "underway",
            "industry_policy_count": 3,
            "gross_margin_median": 26.0,
        },
        min_signals_required=2,
    )

    assert result.state_code == "Confirmed"
    assert result.confidence > 0
    assert "行业需求增速" in logic
    assert "同业毛利率中位数" in logic


def test_lifecycle_intro_from_low_penetration_and_demand_improvement():
    """低渗透率叠加需求改善时，应优先识别为导入期。"""
    from core.pipeline import determine_lifecycle_from_real_data

    lifecycle = determine_lifecycle_from_real_data(
        {
            "industry_signals": {
                "industry_penetration_rate": 8.0,
                "industry_market_growth": 35.0,
                "industry_order_growth": 12.0,
                "industry_capacity_utilization": 72.0,
            }
        }
    )

    assert lifecycle["stage"] == "导入期"
    assert "渗透率" in lifecycle["desc"]


def test_lifecycle_decline_from_price_and_inventory_even_without_growth():
    """缺少行业增速时，价格下跌和库存高企也应能触发衰退期判断。"""
    from core.pipeline import determine_lifecycle_from_real_data

    lifecycle = determine_lifecycle_from_real_data(
        {
            "industry_signals": {
                "industry_price_yoy": -8.0,
                "industry_inventory_days": 85.0,
                "industry_capacity_utilization": 65.0,
            }
        }
    )

    assert lifecycle["stage"] == "衰退期"
    assert "价格" in lifecycle["desc"] or "库存" in lifecycle["desc"]
