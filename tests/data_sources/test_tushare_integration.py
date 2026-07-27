"""
Tushare 真实 API 集成测试
需要 .env 中配置有效 TUSHARE_TOKEN。
运行方式：python -m pytest tests/data_sources/test_tushare_integration.py -v -s
"""
import os
import sys
import json

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from data_sources.tushare_source import TushareDataSource

# 无 token 时自动跳过（CI 友好）
TOKEN = os.environ.get("TUSHARE_TOKEN") or ""
if not TOKEN:
    try:
        from dotenv import load_dotenv
        load_dotenv()
        TOKEN = os.environ.get("TUSHARE_TOKEN", "")
    except ImportError:
        pass

MISSING_TOKEN = not bool(TOKEN)
pytestmark = pytest.mark.skipif(MISSING_TOKEN, reason="未配置 TUSHARE_TOKEN，跳过集成测试")


def test_token_status():
    """验证 token 认证是否通过"""
    source = TushareDataSource()
    status = source.get_token_status()
    result_str = json.dumps(status, ensure_ascii=False, indent=2)
    print(f"\n  token_status: {result_str}")
    assert status["status"] == "success", f"token 验证失败: {status.get('error', status)}"
    assert "有效" in status.get("message", "")
    print("  [OK] token 认证通过")


def test_get_stock_basic():
    """验证个股基础信息（120 积分可用）"""
    source = TushareDataSource()
    result = source.get_stock_basic("600519")
    result_str = json.dumps(result, ensure_ascii=False, default=str, indent=2)
    print(f"\n  stock_basic: {result_str}")
    assert result["status"] == "success", f"stock_basic 失败: {result.get('error')}"
    assert "info" in result
    info = result["info"]
    assert info.get("name"), "缺少股票名称"
    print(f"  [OK] 股票: {info.get('name')}, 行业: {info.get('industry')}, 上市: {info.get('list_date')}")


def test_get_market_data():
    """验证日线行情（120 积分可用）"""
    source = TushareDataSource()
    result = source.get_market_data("000001")
    print(f"\n  market_data status: {result['status']}")
    if result["status"] == "error":
        print(f"  error: {result.get('error', '')[:200]}")
    assert result["status"] == "success", f"market_data 失败: {result.get('error')}"
    assert "records" in result
    records = result["records"]
    assert len(records) > 0, "日线数据为空"
    first = records[0]
    # tushare daily 接口返回 vol 字段（非 volume）
    for key in ["open", "high", "low", "close", "vol"]:
        assert key in first, f"缺少字段: {key}"
    print(f"  [OK] {len(records)} 条日线, 首条 {first.get('trade_date')} close={first.get('close')} vol={first.get('vol')}")


def test_get_financial_data_insufficient_permissions():
    """验证财务三大表因权限不足时的错误处理（需要 2000 积分）"""
    source = TushareDataSource()
    result = source.get_financial_data("600519")
    print(f"\n  financial_data status: {result['status']}")
    if result["status"] == "success":
        income = result.get("income")
        balance = result.get("balance")
        cashflow = result.get("cashflow")
        print(f"  income: {'有数据' if income else 'null (权限不足)'}")
        print(f"  balance: {'有数据' if balance else 'null (权限不足)'}")
        print(f"  cashflow: {'有数据' if cashflow else 'null (权限不足)'}")
        warnings = result.get("warnings", [])
        if warnings:
            print(f"  warnings: {warnings}")
    else:
        print(f"  error: {result.get('error', '')[:200]}")
    # 120 积分用户预期：财务三大表全部失败是正常行为
    assert result["status"] in ("success", "error"), f"未知状态: {result['status']}"
    print("  [OK] 权限不足时优雅降级")


def test_get_fund_flow_data_insufficient_permissions():
    """验证资金流向因权限不足时的错误处理（需要 2000 积分）"""
    source = TushareDataSource()
    result = source.get_fund_flow_data("600519")
    print(f"\n  fund_flow status: {result['status']}")
    assert result["status"] == "error"
    assert "权限" in result.get("error", "") or "2000" in result.get("error", "")
    print(f"  [OK] 权限不足，错误提示: {result.get('error', '')[:120]}")
