#!/usr/bin/env python3
"""
Industrial Sentinel Pipeline 端到端测试
测试标的: 深南电路 (002916.SZ)

验证项:
    1. Pipeline 生成完整 HTML 文件
    2. HTML 包含产业链结构卡片
    3. HTML 包含 System A: 生命周期 + 拐点状态（五态模型，无评分）
    4. HTML 包含 System B: 个股类型判定（成长/周期/价值/主题/混合）
    5. HTML 包含数据溯源表（来源+时间戳）
    6. 执行时间 < 60 秒
"""

import os
import sys
import time
from pathlib import Path
import pytest

SKILL_DIR = Path(__file__).parent.parent.parent / "skills" / "industry" / "industrial_sentinel"
sys.path.insert(0, str(SKILL_DIR))
sys.path.insert(0, str(SKILL_DIR / "core"))


def test_pipeline():
    """运行端到端测试并输出报告"""

    from core.pipeline import run_pipeline

    print("=" * 70)
    print("Industrial Sentinel Pipeline 端到端测试")
    print("=" * 70)
    print(f"测试标的: 深南电路 (002916.SZ)")
    print(f"目标耗时: < 60 秒")
    print()

    start = time.time()
    try:
        output_path = run_pipeline("002916.SZ")
        elapsed = time.time() - start
    except Exception as e:
        print(f"\n❌ Pipeline 执行失败: {e}")
        import traceback
        traceback.print_exc()
        pytest.fail(f"Pipeline 执行失败: {e}")

    if not os.path.exists(output_path):
        print(f"\n❌ 输出文件不存在: {output_path}")
        pytest.fail(f"输出文件不存在: {output_path}")

    with open(output_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    tests = [
        {
            "name": "HTML 文件生成",
            "check": lambda: len(html_content) > 5000,
            "detail": lambda: f"文件大小 {len(html_content)} 字节",
        },
        {
            "name": "产业链结构卡片",
            "check": lambda: "产业链结构" in html_content and "上游" in html_content,
            "detail": lambda: "包含产业链结构卡片",
        },
        {
            "name": "System A — 生命周期判定",
            "check": lambda: "生命周期" in html_content,
            "detail": lambda: "包含生命周期判定模块",
        },
        {
            "name": "System A — 拐点状态（五态模型，无评分）",
            "check": lambda: "产业链拐点" in html_content and "产业拐点指数" not in html_content,
            "detail": lambda: "包含五态拐点判定，不含评分数字",
        },
        {
            "name": "System B — 个股类型判定",
            "check": lambda: "System B" in html_content or "个股类型" in html_content,
            "detail": lambda: "包含个股类型判定模块",
        },
        {
            "name": "System B — 无交易计划",
            "check": lambda: "交易计划" not in html_content and "止盈" not in html_content,
            "detail": lambda: "不含交易计划和止盈策略",
        },
        {
            "name": "数据溯源表",
            "check": lambda: "来源" in html_content and "时间" in html_content,
            "detail": lambda: "包含数据溯源表",
        },
        {
            "name": "执行时间",
            "check": lambda: elapsed < 60,
            "detail": lambda: f"实际耗时 {elapsed:.2f} 秒 {'✅ 通过' if elapsed < 60 else '❌ 超时'}",
        },
    ]

    print()
    print("-" * 70)
    print("验证结果")
    print("-" * 70)

    passed = 0
    failed = 0

    for test in tests:
        try:
            ok = test["check"]()
            detail = test["detail"]()
            if ok:
                print(f"  ✅ [通过] {test['name']}")
                print(f"        {detail}")
                passed += 1
            else:
                print(f"  ❌ [失败] {test['name']}")
                print(f"        {detail}")
                failed += 1
        except Exception as e:
            print(f"  ❌ [异常] {test['name']}: {e}")
            failed += 1

    print()
    print("=" * 70)
    print(f"测试汇总: {passed}/{len(tests)} 通过, {failed}/{len(tests)} 失败")
    print(f"执行耗时: {elapsed:.2f} 秒")
    print(f"输出文件: {output_path}")
    print("=" * 70)

    assert failed == 0, f"Pipeline 验证失败: {passed}/{len(tests)} 通过"


if __name__ == "__main__":
    test_pipeline()
